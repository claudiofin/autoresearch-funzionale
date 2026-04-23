"""
Critic - Agente di revisione per analisi funzionale automatica.

Analizza i report del fuzzer, la specifica e il contesto del progetto per generare
feedback strutturato che l'Analyst può usare per migliorare la specifica.

Il Critic adotta un approccio "Red Team": cerca attivamente buchi logici,
edge case non gestiti, decisioni UX ambigue e FLUSSI MANCANTI.

Usage:
    python src/critic.py --fuzz-report output/fuzz_report.json --spec output/spec/spec.md --machine output/spec/spec_machine.json --context output/context/project_context.md
"""

import os
import sys
import json
import argparse
from datetime import datetime

# ---------------------------------------------------------------------------
# LLM Client (opzionale - se non disponibile, usa analisi statica)
# ---------------------------------------------------------------------------

def get_llm_client():
    """Crea client LLM. Returns None se LLM_API_KEY non è settato."""
    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key:
        return None, None
    
    try:
        from openai import OpenAI
    except ImportError:
        return None, None
    
    from config import LLM_CONFIG, DEFAULT_PROVIDER
    
    provider = os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER)
    
    if provider in LLM_CONFIG:
        base_url = os.getenv("LLM_BASE_URL", LLM_CONFIG[provider]["base_url"])
        model = os.getenv("LLM_MODEL", LLM_CONFIG[provider]["model"])
    else:
        base_url = os.getenv("LLM_BASE_URL")
        model = os.getenv("LLM_MODEL")
        if not base_url or not model:
            return None, None
    
    return OpenAI(api_key=api_key, base_url=base_url), model


def call_llm_critic(fuzz_report: dict, spec_text: str, machine: dict, context_text: str = "") -> dict:
    """Chiama l'LLM per un'analisi critica approfondita.
    
    Args:
        fuzz_report: Report del fuzzer
        spec_text: Testo della specifica
        machine: Macchina a stati
        context_text: Contesto del progetto (per rilevare flussi mancanti)
    """
    client, model = get_llm_client()
    if not client:
        return None
    
    # Prepara il prompt
    fuzz_summary = json.dumps(fuzz_report.get("summary", {}), indent=2)
    bugs = json.dumps(fuzz_report.get("bugs", []), indent=2)
    
    states = machine.get("states", {})
    state_names = list(states.keys())
    transitions_list = []
    for state_name, state_config in states.items():
        for event, target in state_config.get("on", {}).items():
            if isinstance(target, dict):
                target_state = target.get("target", "")
            else:
                target_state = target
            transitions_list.append(f"{state_name} --{event}--> {target_state}")
    
    # Costruisci il prompt con contesto opzionale
    context_section = ""
    if context_text:
        context_section = f"""
## Project Context (Original Requirements)
{context_text[:4000]}
"""
    
    prompt = f"""You are a ruthless QA Engineer and UX Reviewer. Your job is to find flaws in this functional specification.

## Fuzz Test Results
{fuzz_summary}

## Bugs Found by Fuzzer
{bugs}

## Current Specification (excerpt)
{spec_text[:3000]}

## State Machine Summary
States ({len(state_names)}): {', '.join(state_names[:20])}{'...' if len(state_names) > 20 else ''}
Initial: {machine.get('initial', 'unknown')}
Transitions ({len(transitions_list)}):
{chr(10).join(f'- {t}' for t in transitions_list[:30])}
{'...' if len(transitions_list) > 30 else ''}
{context_section}
Your task: Analyze and provide critical feedback in JSON format:
{{
  "critical_issues": [
    {{
      "id": "CRIT-001",
      "category": "logic|ux|error_handling|security|performance|missing_flow",
      "description": "Clear description of the issue",
      "affected_states": ["state1", "state2"],
      "severity": "critical|high|medium",
      "suggestion": "How to fix it"
    }}
  ],
  "ux_decisions_needed": [
    {{
      "id": "UX-001",
      "question": "What should happen when...?",
      "context": "Current behavior is ambiguous because...",
      "options": ["Option A", "Option B", "Option C"]
    }}
  ],
  "edge_cases_to_add": [
    {{
      "id": "EC-NEW-001",
      "scenario": "Description of the edge case",
      "expected_behavior": "What should happen",
      "priority": "high|medium|low"
    }}
  ],
  "missing_flows": [
    {{
      "id": "FLOW-001",
      "flow_name": "Name of the missing flow",
      "description": "What this flow should do",
      "business_reason": "Why this is required based on project context",
      "suggested_states": ["state1", "state2"],
      "suggested_transitions": [
        {{"from": "state1", "to": "state2", "event": "EVENT_NAME"}}
      ]
    }}
  ],
  "recommendations": [
    "General recommendation 1",
    "General recommendation 2"
  ]
}}

Be thorough. Look for:
1. Missing error handling paths
2. Ambiguous user flows
3. Security concerns (data exposure, auth bypass)
4. Performance issues (unnecessary API calls, missing caching)
5. UX problems (confusing states, missing feedback)
6. Edge cases the fuzzer might have missed
7. **MISSING FLOWS**: Compare the project context with the current state machine. Are there any features or flows described in the context that are completely absent from the state machine? (e.g., if the app has login but no auth flow exists, if it has search but no search states)
"""
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a QA Engineer. Respond only with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=8192
        )
        
        content = response.choices[0].message.content.strip()
        # Estrai JSON dal response
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        return json.loads(content)
    
    except Exception as e:
        print(f"⚠️  LLM critic failed: {e}")
        return None


def static_critic_analysis(fuzz_report: dict, machine: dict) -> dict:
    """Analisi critica statica (senza LLM)."""
    
    critical_issues = []
    ux_decisions = []
    edge_cases = []
    recommendations = []
    
    summary = fuzz_report.get("summary", {})
    bugs = fuzz_report.get("bugs", [])
    
    # Analizza dead-end states
    dead_end_bugs = [b for b in bugs if b.get("type") == "dead_end_state"]
    for bug in dead_end_bugs:
        critical_issues.append({
            "id": f"CRIT-{len(critical_issues)+1:03d}",
            "category": "logic",
            "description": bug["description"],
            "affected_states": [bug.get("state", "unknown")],
            "severity": "critical",
            "suggestion": f"Add a transition from '{bug.get('state', 'unknown')}' to handle the dead-end (e.g., retry, go back, or show error)"
        })
    
    # Analizza unreachable states
    unreachable = fuzz_report.get("unreachable_states", [])
    for state in unreachable:
        critical_issues.append({
            "id": f"CRIT-{len(critical_issues)+1:03d}",
            "category": "logic",
            "description": f"State '{state}' is unreachable from initial state",
            "affected_states": [state],
            "severity": "high",
            "suggestion": f"Either add a transition path to '{state}' or remove it if unused"
        })
    
    # Analizza unknown targets
    unknown_bugs = [b for b in bugs if b.get("type") == "unknown_target"]
    for bug in unknown_bugs:
        critical_issues.append({
            "id": f"CRIT-{len(critical_issues)+1:03d}",
            "category": "logic",
            "description": bug["description"],
            "affected_states": [bug.get("from_state", "unknown")],
            "severity": "critical",
            "suggestion": f"Fix the transition target to point to a valid state"
        })
    
    # UX decisions basate sugli stati di loading
    states = machine.get("states", {})
    loading_states = [s for s in states.keys() if "loading" in s.lower()]
    if loading_states:
        ux_decisions.append({
            "id": f"UX-{len(ux_decisions)+1:03d}",
            "question": "What should the user see during loading states?",
            "context": f"There are {len(loading_states)} loading states ({', '.join(loading_states[:3])}...)",
            "options": ["Skeleton screens", "Loading spinner with progress", "Static placeholder", "Shimmer effect"]
        })
    
    # Edge cases basati sugli stati di errore
    error_states = [s for s in states.keys() if "error" in s.lower() or "timeout" in s.lower()]
    if error_states:
        edge_cases.append({
            "id": f"EC-NEW-{len(edge_cases)+1:03d}",
            "scenario": "User is in error state and tries to retry",
            "expected_behavior": "Should show retry button with exponential backoff",
            "priority": "high"
        })
        edge_cases.append({
            "id": f"EC-NEW-{len(edge_cases)+1:03d}",
            "scenario": "Multiple consecutive errors occur",
            "expected_behavior": "After 3 failures, show 'contact support' option",
            "priority": "high"
        })
    
    # Recommendations
    if summary.get("total_errors", 0) > 0:
        recommendations.append(f"Fix {summary['total_errors']} structural errors before proceeding")
    if summary.get("unreachable_states", 0) > 0:
        recommendations.append(f"Review {summary['unreachable_states']} unreachable states - they may indicate missing flows")
    if summary.get("structural_loops", 0) > 0:
        recommendations.append(f"Verify {summary['structural_loops']} structural loops are intentional (not infinite loops)")
    
    if not recommendations:
        recommendations.append("Specification looks solid. Consider adding more edge cases for production readiness.")
    
    return {
        "critical_issues": critical_issues,
        "ux_decisions_needed": ux_decisions,
        "edge_cases_to_add": edge_cases,
        "recommendations": recommendations
    }


def print_critic_report(report: dict):
    """Stampa il report del critic."""
    
    print("\n" + "=" * 60)
    print("CRITIC REVIEW REPORT")
    print("=" * 60)
    
    issues = report.get("critical_issues", [])
    ux = report.get("ux_decisions_needed", [])
    edges = report.get("edge_cases_to_add", [])
    missing = report.get("missing_flows", [])
    recs = report.get("recommendations", [])
    
    print(f"\n🔴 CRITICAL ISSUES ({len(issues)}):")
    for issue in issues:
        print(f"  [{issue['id']}] {issue['description']}")
        print(f"    Category: {issue['category']} | Severity: {issue['severity']}")
        print(f"    Suggestion: {issue['suggestion']}")
        print()
    
    print(f"\n🤔 UX DECISIONS NEEDED ({len(ux)}):")
    for decision in ux:
        print(f"  [{decision['id']}] {decision['question']}")
        print(f"    Context: {decision['context']}")
        print(f"    Options: {', '.join(decision['options'])}")
        print()
    
    print(f"\n📋 EDGE CASES TO ADD ({len(edges)}):")
    for ec in edges:
        print(f"  [{ec['id']}] {ec['scenario']}")
        print(f"    Expected: {ec['expected_behavior']} | Priority: {ec['priority']}")
        print()
    
    if missing:
        print(f"\n🚨 MISSING FLOWS ({len(missing)}):")
        for flow in missing:
            print(f"  [{flow['id']}] {flow['flow_name']}")
            print(f"    Description: {flow['description']}")
            print(f"    Business reason: {flow.get('business_reason', 'N/A')}")
            if flow.get('suggested_states'):
                print(f"    Suggested states: {', '.join(flow['suggested_states'])}")
            if flow.get('suggested_transitions'):
                for t in flow['suggested_transitions']:
                    print(f"    Suggested transition: {t.get('from', '?')} --{t.get('event', '?')}--> {t.get('to', '?')}")
        print()
    
    print(f"\n💡 RECOMMENDATIONS ({len(recs)}):")
    for rec in recs:
        print(f"  - {rec}")
    
    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Critic - Revisione critica specifica funzionale")
    parser.add_argument("--fuzz-report", type=str, default="output/fuzz_report.json",
                        help="Fuzz report JSON file")
    parser.add_argument("--spec", type=str, default="output/spec/spec.md",
                        help="Spec file for context")
    parser.add_argument("--machine", type=str, default="output/spec/spec_machine.json",
                        help="State machine JSON file")
    parser.add_argument("--context", type=str, default=None,
                        help="Project context file (for missing flow detection)")
    parser.add_argument("--output", type=str, default="output/critic_feedback.json",
                        help="Output JSON file (default: output/critic_feedback.json)")
    parser.add_argument("--use-llm", action="store_true",
                        help="Force LLM usage even if static analysis is available")
    args = parser.parse_args()
    
    # Carica fuzz report
    if not os.path.exists(args.fuzz_report):
        print(f"⚠️  Fuzz report not found: {args.fuzz_report}")
        print("   Creating empty report...")
        fuzz_report = {"summary": {}, "bugs": [], "unreachable_states": []}
    else:
        with open(args.fuzz_report, "r", encoding="utf-8") as f:
            fuzz_report = json.load(f)
    
    # Carica spec
    spec_text = ""
    if os.path.exists(args.spec):
        with open(args.spec, "r", encoding="utf-8") as f:
            spec_text = f.read()
    
    # Carica context (opzionale)
    context_text = ""
    if args.context and os.path.exists(args.context):
        with open(args.context, "r", encoding="utf-8") as f:
            context_text = f.read()
        print(f"📄 Context loaded: {len(context_text)} chars")
    
    # Carica machine
    if not os.path.exists(args.machine):
        print(f"Error: Machine file not found: {args.machine}")
        sys.exit(1)
    with open(args.machine, "r", encoding="utf-8") as f:
        machine = json.load(f)
    
    print(f"🧐 Critic analyzing...")
    print(f"   Fuzz bugs: {len(fuzz_report.get('bugs', []))}")
    print(f"   Spec size: {len(spec_text)} chars")
    print(f"   States: {len(machine.get('states', {}))}")
    
    # Prova LLM prima se richiesto o se ci sono bug
    llm_result = None
    if args.use_llm or fuzz_report.get("summary", {}).get("bugs_found", 0) > 0 or context_text:
        print(f"\n  🤖 Trying LLM critic...")
        llm_result = call_llm_critic(fuzz_report, spec_text, machine, context_text)
    
    # Fallback su analisi statica
    if llm_result:
        print(f"  ✅ LLM critic succeeded")
        report = llm_result
    else:
        print(f"  📊 Using static critic analysis")
        report = static_critic_analysis(fuzz_report, machine)
    
    # Aggiungi metadata
    report["metadata"] = {
        "timestamp": datetime.now().isoformat(),
        "method": "llm" if llm_result else "static",
        "fuzz_report_used": os.path.exists(args.fuzz_report),
        "spec_used": os.path.exists(args.spec),
        "context_used": bool(context_text),
    }
    
    print_critic_report(report)
    
    # Salva output
    output_file = args.output
    os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else ".", exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    
    print(f"\n📄 Critic feedback saved: {output_file}")
    
    # Count critical issues
    critical_count = len(report.get("critical_issues", []))
    sys.exit(0 if critical_count == 0 else 1)


if __name__ == "__main__":
    main()