"""
Completeness validator per analisi funzionale automatica.
Verifica che i flussi obbligatori siano presenti nella specifica.
Se mancano, rigenera con prompt aggressivo.

LLM È OBBLIGATORIO: Il sistema richiede LLM_API_KEY settato.
Nessun fallback pattern library.

USO:
    python run.py completeness --spec output/spec.md --machine output/spec_machine.json --context output/project_context.md --fix
"""

import os
import sys
import json
import re
import argparse
from pathlib import Path
from datetime import datetime

import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import LLM_CONFIG, DEFAULT_PROVIDER

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

OUTPUT_DIR = "./output"


# ---------------------------------------------------------------------------
# LLM Client (Obbligatorio)
# ---------------------------------------------------------------------------

def get_llm_client():
    """Crea client LLM. ERRORE se LLM_API_KEY non è settato."""
    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key:
        print("❌ ERRORE: LLM_API_KEY non è settato.")
        print("   Il sistema richiede un LLM per funzionare.")
        print("   Esporta la chiave: export LLM_API_KEY='la-tua-chiave'")
        sys.exit(1)
    
    try:
        from openai import OpenAI
    except ImportError:
        print("❌ ERRORE: openai non installato.")
        print("   Installa: pip install openai")
        sys.exit(1)
    
    # Provider da env var (default: openai)
    provider = os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER)
    
    # URL e modello da config o env var
    if provider in LLM_CONFIG:
        base_url = os.getenv("LLM_BASE_URL", LLM_CONFIG[provider]["base_url"])
        model = os.getenv("LLM_MODEL", LLM_CONFIG[provider]["model"])
    else:
        # Custom provider - richiede env vars
        base_url = os.getenv("LLM_BASE_URL")
        model = os.getenv("LLM_MODEL")
        if not base_url or not model:
            print(f"❌ ERRORE: Provider '{provider}' non riconosciuto.")
            print(f"   Provider disponibili: {', '.join(LLM_CONFIG.keys())}")
            print("   Oppure setta LLM_BASE_URL e LLM_MODEL manualmente.")
            sys.exit(1)
    
    return OpenAI(api_key=api_key, base_url=base_url), model


def call_llm_detect_patterns(context_text: str, max_retries: int = 3) -> dict:
    """Chiama l'LLM per analizzare il contesto e generare i flussi obbligatori."""
    client, model = get_llm_client()
    
    prompt = f"""You are a Senior Product Manager. Analyze this project context and generate a list of MANDATORY flows that MUST be included in the functional specification.

## Project Context

{context_text}

## Your Task

Analyze the context and identify ALL the flows that are essential for this product. For each flow, specify:
- The states that MUST exist
- The transitions that MUST exist
- Why this flow is important (business reason)

## Response Format

Respond ONLY with valid JSON (no markdown, no code blocks):

{{
  "mandatory_flows": [
    {{
      "id": "flow_identifier",
      "description": "Human readable description",
      "business_reason": "Why this flow is critical",
      "required_states": ["state1", "state2"],
      "required_transitions": [
        {{"from": "state1", "to": "state2", "event": "EVENT_NAME"}}
      ],
      "optional_states": ["optional_state1"],
      "optional_transitions": [
        {{"from": "state1", "to": "optional_state1", "event": "OPTIONAL_EVENT"}}
      ]
    }}
  ]
}}

## Rules

1. Be specific to the project context - don't generate generic flows
2. Include authentication flows if the app has login
3. Include empty/error states if the app has search or forms
4. Include success states for any purchase/group/transaction flow
5. Include notification/alert flows if mentioned
6. Be comprehensive - missing a critical flow is worse than having an extra one
"""
    
    print(f"  🤖 Chiamata LLM per pattern detection ({model})...")
    
    for attempt in range(max_retries):
        try:
            print(f"  Tentativo {attempt + 1}/{max_retries}...")
            response = client.chat.completions.create(
                timeout=120,
                model=model,
                messages=[
                    {"role": "system", "content": "Sei un Senior Product Manager. Rispondi SOLO con JSON valido, senza markdown."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=4096,
            )
            
            content = response.choices[0].message.content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            data = json.loads(content)
            return data
            
        except Exception as e:
            print(f"  Tentativo {attempt + 1} fallito: {e}")
            continue
    
    print("❌ ERRORE: Tutti i tentativi LLM falliti.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Completeness Check
# ---------------------------------------------------------------------------

def check_spec_completeness(spec_file: str, machine_file: str, mandatory_flows: dict) -> dict:
    """Verifica la completezza della specifica rispetto ai flussi obbligatori."""
    
    results = {}
    
    # Read files
    with open(spec_file, "r", encoding="utf-8") as f:
        spec_text = f.read()
    
    with open(machine_file, "r", encoding="utf-8") as f:
        machine = json.load(f)
    
    states = set(machine.get("states", {}).keys())
    transitions = []
    for state_name, state_config in machine.get("states", {}).items():
        for event, target in state_config.get("on", {}).items():
            if isinstance(target, dict):
                target_state = target.get("target", "")
            else:
                target_state = target
            transitions.append((state_name, target_state, event))
    
    # Check each mandatory flow
    for flow_id, flow_def in mandatory_flows.items():
        missing_states = []
        missing_transitions = []
        
        # Check required states
        for state in flow_def.get("required_states", []):
            if state not in states:
                missing_states.append(state)
        
        # Check required transitions
        for trans in flow_def.get("required_transitions", []):
            from_s = trans.get("from") if isinstance(trans, dict) else trans[0]
            to_s = trans.get("to") if isinstance(trans, dict) else trans[1]
            event = trans.get("event") if isinstance(trans, dict) else trans[2]
            found = any(
                f == from_s and t == to_s and e == event
                for f, t, e in transitions
            )
            if not found:
                missing_transitions.append(f"{from_s} --{event}--> {to_s}")
        
        is_complete = len(missing_states) == 0 and len(missing_transitions) == 0
        
        results[flow_id] = {
            "description": flow_def.get("description", flow_id),
            "complete": is_complete,
            "missing_states": missing_states,
            "missing_transitions": missing_transitions,
        }
    
    return results


def generate_fix_prompt(results: dict, context_text: str) -> str:
    """Genera un prompt aggressivo per correggere i flussi mancanti."""
    
    missing_flows = [fid for fid, r in results.items() if not r["complete"]]
    
    prompt = f"""URGENT: Your previous specification is MISSING critical flows. You MUST add these flows NOW.

## Missing Flows (MUST ADD ALL):

"""
    for fid in missing_flows:
        r = results[fid]
        prompt += f"\n### {r['description']} ({fid})\n"
        if r["missing_states"]:
            prompt += f"Missing states: {', '.join(r['missing_states'])}\n"
        if r["missing_transitions"]:
            prompt += f"Missing transitions: {', '.join(r['missing_transitions'])}\n"
    
    prompt += f"""
## Project Context

{context_text}

## YOUR TASK

Generate ONLY the missing states and transitions as JSON. Do NOT regenerate the entire spec.

Respond with JSON:
{{
  "additional_states": [
    {{"name": "state_name", "description": "...", "entry_actions": [], "exit_actions": []}}
  ],
  "additional_transitions": [
    {{"from_state": "...", "to_state": "...", "event": "..."}}
  ]
}}

CRITICAL: You MUST include ALL missing states and transitions listed above. This is not optional.
"""
    return prompt


def call_llm_fix(context_text: str, results: dict, max_retries: int = 3) -> dict:
    """Chiama l'LLM per generare solo i flussi mancanti."""
    client, model = get_llm_client()
    
    prompt = generate_fix_prompt(results, context_text)
    
    print(f"  🤖 Chiamata LLM per fix ({model})...")
    
    for attempt in range(max_retries):
        try:
            print(f"  Tentativo {attempt + 1}/{max_retries}...")
            response = client.chat.completions.create(
                timeout=120,
                model=model,
                messages=[
                    {"role": "system", "content": "Sei un Senior Product Manager. Rispondi SOLO con JSON valido, senza markdown."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=4096,
            )
            
            content = response.choices[0].message.content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            data = json.loads(content)
            return data
            
        except Exception as e:
            print(f"  Tentativo {attempt + 1} fallito: {e}")
            continue
    
    print("❌ ERRORE: Tutti i tentativi LLM falliti.")
    sys.exit(1)


def apply_fix(machine: dict, fix_data: dict) -> dict:
    """Applica i fix alla macchina a stati."""
    
    # Add missing states
    for state in fix_data.get("additional_states", []):
        state_name = state["name"]
        if state_name not in machine["states"]:
            machine["states"][state_name] = {
                "entry": state.get("entry_actions", []),
                "exit": state.get("exit_actions", []),
                "on": {}
            }
            print(f"  ✅ Added state: {state_name}")
    
    # Add missing transitions
    for trans in fix_data.get("additional_transitions", []):
        from_state = trans["from_state"]
        to_state = trans["to_state"]
        event = trans["event"]
        if from_state in machine["states"]:
            machine["states"][from_state]["on"][event] = to_state
            print(f"  ✅ Added transition: {from_state} --{event}--> {to_state}")
        else:
            print(f"  ⚠️  Warning: from_state '{from_state}' not found")
    
    return machine


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Completeness validator (LLM required)")
    parser.add_argument("--spec", type=str, default="output/spec.md",
                        help="Spec file to check")
    parser.add_argument("--machine", type=str, default="output/spec_machine.json",
                        help="State machine file to check")
    parser.add_argument("--context", type=str, default="output/project_context.md",
                        help="Context file for dynamic pattern detection")
    parser.add_argument("--fix", action="store_true",
                        help="Automatically fix missing flows")
    parser.add_argument("--output-report", type=str, default=None,
                        help="Output JSON report file (default: output/completeness_report.json)")
    args = parser.parse_args()
    
    # Default report path
    if args.output_report is None:
        args.output_report = os.path.join(OUTPUT_DIR, "completeness_report.json")
    
    # Check files exist
    for f in [args.spec, args.machine, args.context]:
        if not os.path.exists(f):
            print(f"Error: File not found: {f}")
            sys.exit(1)
    
    # Read context
    with open(args.context, "r", encoding="utf-8") as f:
        context_text = f.read()
    
    # Detect patterns using LLM (no fallback)
    print("=" * 60)
    print("PATTERN DETECTION (LLM Required)")
    print("=" * 60)
    
    llm_data = call_llm_detect_patterns(context_text)
    mandatory_flows = {}
    for flow in llm_data.get("mandatory_flows", []):
        mandatory_flows[flow["id"]] = {
            "description": flow["description"],
            "business_reason": flow.get("business_reason", ""),
            "required_states": flow.get("required_states", []),
            "required_transitions": flow.get("required_transitions", []),
            "optional_states": flow.get("optional_states", []),
            "optional_transitions": flow.get("optional_transitions", []),
        }
    print(f"  Detected {len(mandatory_flows)} mandatory flows from LLM")
    
    if not mandatory_flows:
        print("\n⚠️  No mandatory flows detected. The LLM couldn't identify any patterns.")
        print("  Try adding more descriptive content to your context file.")
        return
    
    # Check completeness
    print("\n" + "=" * 60)
    print("COMPLETENESS CHECK")
    print("=" * 60)
    
    results = check_spec_completeness(args.spec, args.machine, mandatory_flows)
    
    all_complete = True
    for flow_id, result in results.items():
        status = "✅ COMPLETE" if result["complete"] else "❌ MISSING"
        print(f"\n{status}: {result['description']}")
        if not result["complete"]:
            all_complete = False
            if result["missing_states"]:
                print(f"  Missing states: {', '.join(result['missing_states'])}")
            if result["missing_transitions"]:
                print(f"  Missing transitions: {', '.join(result['missing_transitions'])}")
    
    # Calcola statistiche pre-fix
    missing_count = sum(1 for r in results.values() if not r["complete"])
    total_flows = len(results)
    
    if all_complete:
        print("\n🎉 All mandatory flows are present!")
        # Scrivi report anche se tutto è completo
        report = {
            "timestamp": datetime.now().isoformat(),
            "total_flows": total_flows,
            "complete_flows": total_flows,
            "missing_flows": 0,
            "fix_applied": False,
            "fix_success": None,
            "flows_fixed": [],
            "flows_still_missing": [],
            "details": results
        }
        os.makedirs(os.path.dirname(args.output_report), exist_ok=True)
        with open(args.output_report, "w") as f:
            json.dump(report, f, indent=2)
        print(f"  Report: {args.output_report}")
        return
    
    print(f"\n⚠️  {missing_count} flows missing")
    
    # Statistiche pre-fix
    pre_fix_missing = {fid: r for fid, r in results.items() if not r["complete"]}
    
    if args.fix:
        print("\n" + "=" * 60)
        print("AUTOMATIC FIX")
        print("=" * 60)
        
        # Call LLM to generate fix
        fix_data = call_llm_fix(context_text, results)
        
        # Read and apply fix
        with open(args.machine, "r") as f:
            machine = json.load(f)
        
        machine = apply_fix(machine, fix_data)
        
        # Write updated machine
        with open(args.machine, "w") as f:
            json.dump(machine, f, indent=2)
        
        print(f"\n✅ Fix applied to {args.machine}")
        
        # Re-check
        print("\n" + "=" * 60)
        print("RE-CHECK")
        print("=" * 60)
        
        results_after = check_spec_completeness(args.spec, args.machine, mandatory_flows)
        
        all_complete = True
        flows_fixed = []
        flows_still_missing = []
        
        for flow_id, result in results_after.items():
            status = "✅ COMPLETE" if result["complete"] else "❌ MISSING"
            print(f"\n{status}: {result['description']}")
            if not result["complete"]:
                all_complete = False
                flows_still_missing.append(flow_id)
            elif flow_id in pre_fix_missing:
                flows_fixed.append(flow_id)
        
        if all_complete:
            print("\n🎉 All mandatory flows are now present!")
        else:
            print(f"\n⚠️  {len(flows_still_missing)} flows still missing. Manual intervention required.")
        
        # Scrivi report con metriche
        report = {
            "timestamp": datetime.now().isoformat(),
            "total_flows": total_flows,
            "complete_flows": total_flows - len(flows_still_missing),
            "missing_flows": len(flows_still_missing),
            "fix_applied": True,
            "fix_success": all_complete,
            "flows_fixed": flows_fixed,
            "flows_still_missing": flows_still_missing,
            "details": results_after
        }
        os.makedirs(os.path.dirname(args.output_report), exist_ok=True)
        with open(args.output_report, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\n  Report: {args.output_report}")
        print(f"  Flows fixati: {len(flows_fixed)}/{missing_count}")
    else:
        # Nessuna fix richiesta - scrivi report solo con lo stato
        report = {
            "timestamp": datetime.now().isoformat(),
            "total_flows": total_flows,
            "complete_flows": total_flows - missing_count,
            "missing_flows": missing_count,
            "fix_applied": False,
            "fix_success": None,
            "flows_fixed": [],
            "flows_still_missing": list(pre_fix_missing.keys()),
            "details": results
        }
        os.makedirs(os.path.dirname(args.output_report), exist_ok=True)
        with open(args.output_report, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\n  Report: {args.output_report}")


if __name__ == "__main__":
    main()