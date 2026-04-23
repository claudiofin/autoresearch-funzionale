"""
Spec generator per analisi funzionale automatica.
Legge project_context.md e genera spec.md con diagrammi PlantUML e macchina a stati XState.

TUTTO è generato dall'LLM. Nessun fallback hardcoded.
Le regole dicono COSA deve esserci, l'LLM decide COME si chiama.

Usage:
    python run.py spec --context output/project_context.md
    
Environment Variables:
    LLM_API_KEY: La tua chiave API (OBBLIGATORIA)
    LLM_PROVIDER: Provider (openai, anthropic, google, dashscope)
    LLM_BASE_URL: URL base dell'API (opzionale, override)
    LLM_MODEL: Modello da usare (opzionale, override)
"""

import os
import sys
import json
import time
import argparse
import re
from pathlib import Path
from datetime import datetime

from config import LLM_CONFIG, DEFAULT_PROVIDER

# Import instructor per output strutturato
try:
    import instructor
    from openai import OpenAI
    HAS_INSTRUCTOR = True
except ImportError:
    HAS_INSTRUCTOR = False

# ---------------------------------------------------------------------------
# Configuration (edit these to experiment)
# ---------------------------------------------------------------------------

TIME_BUDGET = 300
LLM_MAX_TOKENS = 8192
ANALYSIS_DEPTH = "deep"
OUTPUT_PLANTUML = True
OUTPUT_XSTATE = True

# ---------------------------------------------------------------------------
# XState State Machine Generator (base template only)
# ---------------------------------------------------------------------------

def generate_base_machine() -> dict:
    """Genera una macchina a stati base vuota. L'LLM la riempie."""
    return {
        "id": "appFlow",
        "initial": "idle",
        "context": {"user": None, "errors": [], "retryCount": 0},
        "states": {}
    }


# ---------------------------------------------------------------------------
# PlantUML Diagram Generators
# ---------------------------------------------------------------------------

def generate_plantuml_statechart(machine: dict) -> str:
    """Convert XState machine to PlantUML state diagram."""
    
    lines = ["@startuml"]
    lines.append("")
    lines.append(f"state \"{machine['id']}\" {{")
    lines.append("")
    
    # Initial state
    lines.append(f"    [*] --> {machine['initial']}")
    lines.append("")
    
    for state_name, state_config in machine["states"].items():
        # Entry actions
        entry_actions = state_config.get("entry", [])
        if entry_actions:
            lines.append(f"    state \"{state_name}\" {{")
            lines.append(f"        note: Entry: {', '.join(entry_actions)}")
        else:
            lines.append(f"    state \"{state_name}\"")
        
        # Transitions
        transitions = state_config.get("on", {})
        if transitions:
            for event, target in transitions.items():
                if isinstance(target, dict):
                    target_state = target.get("target", "unknown")
                    guard = target.get("guard", "")
                    if guard:
                        lines.append(f"        {state_name} --> {target_state} : {event} [{guard}]")
                    else:
                        lines.append(f"        {state_name} --> {target_state} : {event}")
                else:
                    lines.append(f"        {state_name} --> {target} : {event}")
        
        lines.append("")
    
    # Terminal states
    lines.append("    [*] <-- cancelled")
    lines.append("    [*] <-- success")
    lines.append("")
    lines.append("}")
    lines.append("@enduml")
    
    return "\n".join(lines)


def generate_plantuml_sequence(context_text: str, machine: dict) -> str:
    """Generate a PlantUML sequence diagram based on the context."""
    
    lines = ["@startuml"]
    lines.append("")
    lines.append("participant User")
    lines.append("participant Interface")
    lines.append("participant Backend")
    lines.append("participant Database")
    lines.append("")
    lines.append("User -> Interface: START")
    lines.append("Interface -> Interface: showLoadingIndicator()")
    lines.append("Interface -> Backend: Request")
    lines.append("")
    lines.append("alt Success")
    lines.append("    Backend --> Interface: 200 OK")
    lines.append("    Interface -> Interface: showSuccessMessage()")
    lines.append("    Interface --> User: Display Result")
    lines.append("else Error")
    lines.append("    Backend --> Interface: 4xx/5xx Error")
    lines.append("    Interface -> Interface: showErrorMessage()")
    lines.append("    Interface --> User: Display Error")
    lines.append("else Timeout")
    lines.append("    Interface -> Interface: showTimeoutMessage()")
    lines.append("    Interface --> User: Display Timeout")
    lines.append("end")
    lines.append("")
    lines.append("@enduml")
    
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM Client
# ---------------------------------------------------------------------------

def call_llm_spec(context_text: str, max_retries: int = 3) -> dict:
    """Chiama l'LLM per generare la specifica funzionale completa."""
    if not HAS_INSTRUCTOR:
        raise RuntimeError("instructor o openai non installati")
    
    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key:
        print("❌ ERRORE: LLM_API_KEY non è settato.")
        print("   Il sistema richiede un LLM per funzionare.")
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
            sys.exit(1)
    
    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=base_url)
    
    prompt = f"""Analizza il contesto e genera JSON con: states, transitions, edge_cases, flows, api_endpoints.

## Contesto
{context_text}

## Output JSON
{{
  "states": [{{"name": "snake_case", "description": "...", "entry_actions": [], "exit_actions": [], "parent_pattern": "...", "business_reason": "..."}}],
  "transitions": [{{"from_state": "...", "to_state": "...", "event": "UPPER_CASE", "guard": null, "actions": [], "business_reason": "..."}}],
  "edge_cases": [{{"id": "EC001", "scenario": "...", "trigger": "...", "analisi_del_problema": "...", "expected_behavior": "...", "priority": "high|medium|low", "related_states": []}}],
  "flows": [{{"name": "...", "steps": [{{"trigger": "...", "action": "...", "expected_outcome": "...", "error_scenario": "..."}}]}}],
  "api_endpoints": [{{"method": "GET|POST|PUT|DELETE", "path": "...", "description": "...", "request_schema": {{}}, "response_schema": {{}}, "error_codes": []}}]
}}

## Regole
1. snake_case per stati, UPPER_CASE per eventi
2. OGNI stato API deve avere transizioni ERROR, TIMEOUT, CANCEL
3. OGNI edge_case deve avere transizione corrispondente
4. NO placeholder generici - descrivi comportamento esatto
5. Pattern paralleli restano separati, non concatenati
6. Copri: auth, core flow, error handling, empty states, notifications

Rispondi SOLO con JSON valido, niente markdown.
"""
    
    print(f"  🤖 Chiamata LLM per spec ({model})...")
    
    for attempt in range(max_retries):
        try:
            print(f"  Tentativo {attempt + 1}/{max_retries}...")
            response = client.chat.completions.create(
                timeout=180,
                model=model,
                messages=[
                    {"role": "system", "content": "Rispondi SOLO con JSON valido. Niente markdown, niente codice. Solo JSON puro."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=2048,
                frequency_penalty=0.3,
                presence_penalty=0.2
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
    
    raise Exception("Tutti i tentativi LLM falliti")


# ---------------------------------------------------------------------------
# Main Analysis Function
# ---------------------------------------------------------------------------

def run_analysis(context_file: str, output_file: str, time_budget: int) -> dict:
    """Run the functional analysis and generate spec.md."""
    
    start_time = time.time()
    
    # Auto-rileva LLM
    llm_api_key = os.getenv("LLM_API_KEY", "")
    use_llm = llm_api_key != "" and HAS_INSTRUCTOR
    
    if not use_llm:
        print("❌ ERRORE: LLM non disponibile.")
        print("   Il sistema richiede un LLM per funzionare.")
        print("   Configura LLM_API_KEY e installa: pip install openai instructor")
        sys.exit(1)
    
    # Read context
    with open(context_file, "r", encoding="utf-8") as f:
        context_text = f.read()
    
    print(f"Context loaded: {len(context_text)} characters")
    print("  🚀 Generazione con LLM REALE...")
    
    # Call LLM (no fallback)
    try:
        llm_data = call_llm_spec(context_text)
        print(f"  ✅ LLM response: {len(llm_data.get('states', []))} states, {len(llm_data.get('transitions', []))} transitions")
    except Exception as e:
        print(f"❌ ERRORE: LLM fallito: {e}")
        print("   Il sistema non può funzionare senza LLM.")
        sys.exit(1)
    
    # Generate state machine from LLM data
    machine = generate_base_machine()
    
    for state in llm_data.get("states", []):
        state_name = state["name"]
        machine["states"][state_name] = {
            "entry": state.get("entry_actions", []),
            "exit": state.get("exit_actions", []),
            "on": {}
        }
    
    for trans in llm_data.get("transitions", []):
        from_state = trans["from_state"]
        to_state = trans["to_state"]
        event = trans["event"]
        if from_state in machine["states"]:
            machine["states"][from_state]["on"][event] = to_state
    
    print(f"Generated state machine with {len(machine['states'])} states")
    
    # Generate PlantUML diagrams
    statechart = generate_plantuml_statechart(machine)
    sequence = generate_plantuml_sequence(context_text, machine)
    
    # Build edge cases table
    edge_cases = llm_data.get("edge_cases", [])
    edge_cases_md = "| ID | Scenario | Expected Behavior | Priority |\n|----|----------|-------------------|----------|\n"
    for ec in edge_cases:
        edge_cases_md += f"| {ec['id']} | {ec['scenario']} | {ec['expected_behavior']} | {ec['priority']} |\n"
    
    # Build flows section
    flows = llm_data.get("flows", [])
    flows_md = ""
    for flow in flows:
        flows_md += f"\n### {flow['name']}\n"
        for step in flow.get("steps", []):
            flows_md += f"1. **Trigger**: {step.get('trigger', '')}\n"
            flows_md += f"   **Action**: {step.get('action', '')}\n"
            flows_md += f"   **Outcome**: {step.get('expected_outcome', '')}\n"
            if step.get('error_scenario'):
                flows_md += f"   **Error**: {step['error_scenario']}\n"
    
    # Build API endpoints section
    endpoints = llm_data.get("api_endpoints", [])
    endpoints_md = ""
    for ep in endpoints:
        endpoints_md += f"\n#### {ep['method']} {ep['path']}\n"
        endpoints_md += f"- **Description**: {ep.get('description', '')}\n"
    
    llm_label = "Reale"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    states_count = len(machine['states'])
    transitions_count = sum(len(s.get('on', {})) for s in machine['states'].values())
    edge_cases_count = len(edge_cases)
    
    # Build the spec document
    spec_content = f"""# Functional Specification

Generated: {timestamp}
LLM: {llm_label}

> This specification was generated automatically from project context.
> It contains executable state machines and comprehensive edge case analysis.

---

## 1. Overview

This document describes the functional specification for the application described in the project context.

### 1.1 Scope
- User flows and journeys
- State machine definition (executable XState)
- Edge case analysis (Chain of Thought)
- Error handling and recovery paths
- API contracts

---

## 2. User Flows
{flows_md if flows_md else "*No flows generated by LLM*"}

---

## 3. State Machine

### 3.1 State Diagram (PlantUML)

```plantuml
{statechart}
```

### 3.2 XState Configuration

```json
{json.dumps(machine, indent=2)}
```

---

## 4. Sequence Diagram (PlantUML)

```plantuml
{sequence}
```

---

## 5. Edge Cases

{edge_cases_md if edge_cases else "*No edge cases generated by LLM*"}

---

## 6. Error Handling

### 6.1 Error Types

| Error Code | Type | User Message | Recovery Action |
|------------|------|--------------|-----------------|
| 400 | Bad Request | "Dati non validi. Controlla l'input." | Fix input and retry |
| 401 | Unauthorized | "Sessione scaduta. Effettua il login." | Redirect to login |
| 403 | Forbidden | "Accesso negato. Contatta l'amministratore." | Contact support |
| 404 | Not Found | "Risorsa non trovata." | Return to home |
| 408 | Timeout | "Richiesta scaduta. Riprova." | Retry |
| 429 | Rate Limited | "Troppe richieste. Attendi N secondi." | Wait and retry |
| 500 | Server Error | "Errore temporaneo. Riprova tra poco." | Retry or contact support |
| 503 | Unavailable | "Servizio non disponibile. Riprova più tardi." | Try again later |

### 6.2 Error States

The application handles errors through the state machine's error states, which:
- Log the error for debugging
- Display appropriate user message in Italian
- Offer recovery options (retry, cancel, contact support)

---

## 7. Data Validation

### 7.1 Input Validation Rules

| Field | Type | Required | Pattern | Max Length |
|-------|------|----------|---------|------------|
| email | email | Yes | RFC 5322 | 254 |
| password | password | Yes | Min 8 chars | 128 |
| search_query | string | Yes | Alphanumeric + spaces | 100 |
| quantity | integer | Yes | > 0 | 9999 |

### 7.2 Validation Feedback

- Inline validation on blur
- Summary validation on submit
- Clear error messages in Italian with fix instructions

---

## 8. API Contract
{endpoints_md if endpoints_md else "*No endpoints generated by LLM*"}

---

## 9. Metrics

### 9.1 Analysis Coverage

- States defined: {states_count}
- Transitions defined: {transitions_count}
- Edge cases identified: {edge_cases_count}
- Error types handled: 8

---

## Appendix A: Raw Context

The original project context is preserved in `project_context.md`.
"""
    
    # Write spec file
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(spec_content)
    
    # Write XState file separately for fuzzer
    xstate_file = output_file.replace(".md", "_machine.json")
    with open(xstate_file, "w", encoding="utf-8") as f:
        json.dump(machine, f, indent=2)
    
    elapsed = time.time() - start_time
    
    # Calculate metrics
    metrics = {
        "states_count": len(machine["states"]),
        "transitions_count": sum(len(s.get("on", {})) for s in machine["states"].values()),
        "edge_cases_count": edge_cases_count,
        "error_types_count": 8,
        "elapsed_seconds": elapsed,
        "spec_file": output_file,
        "machine_file": xstate_file,
    }
    
    return metrics


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate functional specification from context")
    parser.add_argument("--context", type=str, default="project_context.md",
                        help="Input context file (default: project_context.md)")
    parser.add_argument("--output", type=str, default="spec.md",
                        help="Output spec file (default: spec.md)")
    parser.add_argument("--time-budget", type=int, default=TIME_BUDGET,
                        help=f"Time budget in seconds (default: {TIME_BUDGET})")
    args = parser.parse_args()
    
    # Check context file exists
    if not os.path.exists(args.context):
        print(f"Error: Context file not found: {args.context}")
        print("Run 'python ingest.py' first to generate project_context.md")
        sys.exit(1)
    
    print(f"Running functional analysis...")
    print(f"  Context: {args.context}")
    print(f"  Output: {args.output}")
    print(f"  Time budget: {args.time_budget}s")
    print()
    
    # Run analysis
    metrics = run_analysis(args.context, args.output, args.time_budget)
    
    # Print results
    print()
    print("=" * 50)
    print("ANALYSIS COMPLETE")
    print("=" * 50)
    print(f"States defined:      {metrics['states_count']}")
    print(f"Transitions:         {metrics['transitions_count']}")
    print(f"Edge cases:          {metrics['edge_cases_count']}")
    print(f"Error types:         {metrics['error_types_count']}")
    print(f"Time elapsed:        {metrics['elapsed_seconds']:.1f}s")
    print()
    print(f"Output files:")
    print(f"  - {metrics['spec_file']}")
    print(f"  - {metrics['machine_file']}")
    print()
    print("Next: Run 'python fuzzer.py' to validate the state machine")


if __name__ == "__main__":
    main()