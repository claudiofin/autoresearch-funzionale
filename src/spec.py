"""
Spec generator per analisi funzionale automatica.
Legge project_context.md e genera spec.md con diagrammi PlantUML e macchina a stati XState.

APPROCCIO ITERATIVO:
- Iterazione 1: genera da zero
- Iterazioni successive: modifica la macchina esistente basandosi su:
  - Suggerimenti dell'analista (stati/transizioni mancanti)
  - Feedback del critic (critical issues da correggere)
  - Validator errors (dead-end states, unreachable states)

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
from pathlib import Path
from datetime import datetime

import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import LLM_CONFIG, DEFAULT_PROVIDER

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TIME_BUDGET = 300

# ---------------------------------------------------------------------------
# XState State Machine Generator
# ---------------------------------------------------------------------------

def generate_base_machine() -> dict:
    """Genera una macchina a stati base vuota."""
    return {
        "id": "appFlow",
        "initial": "app_idle",
        "context": {"user": None, "errors": [], "retryCount": 0},
        "states": {}
    }


# ---------------------------------------------------------------------------
# PlantUML Diagram Generators
# ---------------------------------------------------------------------------

def generate_plantuml_statechart(machine: dict) -> str:
    """Convert XState machine to PlantUML state diagram (flat layout)."""
    lines = ["@startuml", ""]
    
    # Initial transition
    lines.append(f'    [*] --> {machine["initial"]}')
    lines.append("")
    
    for state_name, state_config in machine["states"].items():
        entry_actions = state_config.get("entry", [])
        exit_actions = state_config.get("exit", [])
        
        # State with notes
        if entry_actions or exit_actions:
            lines.append(f'    state "{state_name}" {{')
            if entry_actions:
                lines.append(f'        note: Entry: {", ".join(entry_actions)}')
            if exit_actions:
                lines.append(f'        note: Exit: {", ".join(exit_actions)}')
        else:
            lines.append(f'    state "{state_name}"')
        
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
    
    # Final states
    lines.extend(["    [*] <-- cancelled", "    [*] <-- success", "@enduml"])
    return "\n".join(lines)


def generate_plantuml_sequence(flows: list) -> str:
    """Generate PlantUML sequence diagrams from actual flows."""
    if not flows:
        lines = [
            "@startuml", "",
            "participant User", "participant Interface", "participant Backend", "participant Database", "",
            "User -> Interface: START",
            "Interface -> Interface: showLoadingIndicator()",
            "Interface -> Backend: Request", "",
            "alt Success",
            "    Backend --> Interface: 200 OK",
            "    Interface -> Interface: showSuccessMessage()",
            "    Interface --> User: Display Result",
            "else Error",
            "    Backend --> Interface: 4xx/5xx Error",
            "    Interface -> Interface: showErrorMessage()",
            "    Interface --> User: Display Error",
            "else Timeout",
            "    Interface -> Interface: showTimeoutMessage()",
            "    Interface --> User: Display Timeout",
            "end", "", "@enduml"
        ]
        return "\n".join(lines)
    
    all_diagrams = []
    for flow in flows:
        lines = ["@startuml", "", f"== {flow['name'].replace('_', ' ').title()} ==", ""]
        lines.extend([
            "participant User", "participant Interface", "participant Backend", "participant Database", ""
        ])
        
        steps = flow.get("steps", [])
        for i, step in enumerate(steps):
            trigger = step.get("trigger", "")
            action = step.get("action", "")
            outcome = step.get("expected_outcome", "")
            error = step.get("error_scenario", "")
            
            if i == 0:
                lines.append(f"User -> Interface: {trigger}")
            else:
                lines.append(f"User -> Interface: {trigger}")
            
            if "POST" in action or "GET" in action or "PUT" in action or "DELETE" in action:
                lines.append(f"Interface -> Backend: {action}")
                lines.append(f"Backend -> Database: query")
                lines.append(f"Database --> Backend: result")
            
            if error:
                lines.append(f"")
                lines.append(f"alt Success")
                lines.append(f"    Backend --> Interface: {outcome}")
                lines.append(f"    Interface --> User: Display Result")
                lines.append(f"else Error")
                lines.append(f"    Backend --> Interface: {error}")
                lines.append(f"    Interface --> User: Show Error")
                lines.append(f"end")
            else:
                lines.append(f"    Backend --> Interface: {outcome}")
                lines.append(f"    Interface --> User: Display Result")
            
            lines.append("")
        
        lines.append("@enduml")
        all_diagrams.append("\n".join(lines))
    
    return "\n\n".join(all_diagrams)


# ---------------------------------------------------------------------------
# LLM Client - APPROCCIO ITERATIVO
# ---------------------------------------------------------------------------

def call_llm_spec(context_text: str, analyst_suggestions: dict = None, 
                  existing_machine: dict = None, critic_feedback: dict = None,
                  max_retries: int = 3) -> dict:
    """Chiama l'LLM per generare/modificare la specifica funzionale.
    
    APPROCCIO ITERATIVO:
    - Se esiste una macchina esistente, la passiamo all'LLM
    - L'LLM deve MODIFICARE la macchina, non rigenerarla
    - I suggerimenti dell'analista indicano cosa aggiungere
    - Il feedback del critic indica cosa correggere
    """
    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key:
        print("❌ ERRORE: LLM_API_KEY non è settato.")
        sys.exit(1)
    
    provider = os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER)
    
    if provider in LLM_CONFIG:
        base_url = os.getenv("LLM_BASE_URL", LLM_CONFIG[provider]["base_url"])
        model = os.getenv("LLM_MODEL", LLM_CONFIG[provider]["model"])
    else:
        base_url = os.getenv("LLM_BASE_URL")
        model = os.getenv("LLM_MODEL")
        if not base_url or not model:
            print(f"❌ ERRORE: Provider '{provider}' non riconosciuto.")
            sys.exit(1)
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
    except ImportError:
        print("❌ ERRORE: openai non installato.")
        sys.exit(1)
    
    # Tronca contesto
    max_context = 4000
    if len(context_text) > max_context:
        lines = context_text.split("\n")
        important = [l for l in lines if l.startswith("##") or l.startswith("###") or l.startswith("-") or l.startswith("|")]
        context_text = "\n".join(important[:100])
        if len(context_text) > max_context:
            context_text = context_text[:max_context]
    
    # Costruisci sezione macchina esistente (se c'è)
    existing_section = ""
    if existing_machine:
        existing_states = list(existing_machine.get("states", {}).keys())
        existing_transitions = []
        for state_name, state_config in existing_machine.get("states", {}).items():
            for event, target in state_config.get("on", {}).items():
                existing_transitions.append(f"    {state_name} --{event}--> {target}")
        
        existing_section = f"""

MACCHINA A STATI ESISTENTE (NON RIMUOVERE STATI, SOLO AGGIUNGERE/CORREGGERE):
Stati attuali ({len(existing_states)}): {', '.join(existing_states[:20])}
Transizioni attuali ({len(existing_transitions)}):
{chr(10).join(existing_transitions[:30])}

ISTRUZIONI:
- MANTIENI tutti gli stati esistenti
- AGGIUNGI i nuovi stati dai suggerimenti dell'analista
- CORREGGI le transizioni per risolvere i dead-end states
- NON RIMUOVERE mai uno stato esistente
"""
    
    # Costruisci sezione suggerimenti analista
    suggestions_section = ""
    if analyst_suggestions:
        states = analyst_suggestions.get("states", [])
        transitions = analyst_suggestions.get("transitions", [])
        edge_cases = analyst_suggestions.get("edge_cases", [])
        events = analyst_suggestions.get("events", [])
        suggestions_section = f"""

SUGGERIMENTI DELL'ANALISTA (DEVI INCLUDERE QUESTI):
- {len(states)} stati suggeriti: {', '.join(s['name'] for s in states[:15])}
- {len(transitions)} transizioni suggerite
- {len(edge_cases)} edge case da gestire
- {len(events)} eventi da supportare: {', '.join(e['name'] for e in events[:10])}

AZIONI RICHIESTE:
1. Aggiungi TUTTI gli stati suggeriti che non esistono già
2. Aggiungi le transizioni suggerite
3. Gestisci gli edge case con stati di errore appropriati
"""
    
    # Costruisci sezione critic feedback
    critic_section = ""
    if critic_feedback:
        critical = critic_feedback.get("summary", {}).get("critical_issues", [])
        if critical:
            critic_section = f"""

CRITICAL ISSUES DA CORREGGERE (PRIORITÀ ALTA):
{chr(10).join(f'- {c}' for c in critical[:10])}

AZIONI RICHIESTE:
- Correggi OGNI critical issue sopra
- Aggiungi transizioni di uscita per dead-end states
- Connetti stati non raggiungibili allo stato iniziale
"""
    
    # Determina se è iterativo o da zero
    is_iterative = existing_machine is not None and len(existing_machine.get("states", {})) > 0
    
    if is_iterative:
        task = "MODIFICA la macchina a stati esistente. NON rigenerare da zero."
    else:
        task = "Genera una nuova macchina a stati dal contesto."
    
    prompt = f"""{task}

Contesto del progetto:
{context_text}
{existing_section}
{suggestions_section}
{critic_section}

Rispondi SOLO con JSON valido:

{{
  "states": [{{"name": "snake_case", "description": "...", "entry_actions": [], "exit_actions": []}}],
  "transitions": [{{"from_state": "...", "to_state": "...", "event": "UPPER_CASE", "guard": null}}],
  "edge_cases": [{{"id": "EC001", "scenario": "...", "trigger": "...", "expected_behavior": "...", "priority": "high"}}],
  "flows": [{{"name": "...", "steps": [{{"trigger": "...", "action": "...", "expected_outcome": "...", "error_scenario": "..."}}]}}],
  "api_endpoints": [{{"method": "GET", "path": "...", "description": "..."}}]
}}

Regole:
1. JSON valido 100% - nessun testo fuori
2. snake_case stati, UPPER_CASE eventi
3. Ogni stato API ha ERROR, TIMEOUT, CANCEL
4. Copri: auth, core flow, error handling, empty states
5. Stato iniziale: app_idle (DEVE esistere)
6. Ogni stato deve avere almeno una transizione in uscita (no dead-end)
7. Tutti gli stati devono essere raggiungibili da app_idle
"""
    
    print(f"  🤖 Chiamata LLM per spec ({model}), contesto: {len(context_text)} chars...")
    if existing_machine:
        print(f"  📦 Macchina esistente: {len(existing_machine.get('states', {}))} stati")
    
    for attempt in range(max_retries):
        try:
            print(f"  Tentativo {attempt + 1}/{max_retries}...")
            response = client.chat.completions.create(
                timeout=180,
                model=model,
                messages=[
                    {"role": "system", "content": "Sei un Product Manager esperto di macchine a stati. Rispondi SOLO con JSON valido. Inizia con { e termina con }. Nessun markdown, nessun testo extra."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=8192,  # Aumentato per gestire macchine più grandi
            )
            
            content = response.choices[0].message.content.strip()
            
            # Estrai JSON
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            start = content.find("{")
            end = content.rfind("}")
            if start >= 0 and end > start:
                content = content[start:end+1]
            
            data = json.loads(content)
            print(f"  ✅ LLM ha restituito {len(json.dumps(data))} chars di JSON valido")
            return data
            
        except json.JSONDecodeError as e:
            print(f"  Tentativo {attempt + 1} fallito (JSON invalido): {e}")
            try:
                start = content.find("{")
                end = content.rfind("}")
                if start >= 0 and end > start:
                    partial = content[start:end+1]
                    data = json.loads(partial)
                    print(f"  ✅ JSON estratto: {len(partial)} chars")
                    return data
            except:
                pass
            continue
        except Exception as e:
            print(f"  Tentativo {attempt + 1} fallito: {e}")
            continue
    
    print("❌ ERRORE: Tutti i tentativi LLM falliti.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Main Analysis Function - APPROCCIO ITERATIVO
# ---------------------------------------------------------------------------

def run_analysis(context_file: str, output_file: str, time_budget: int, 
                 analyst_suggestions: dict = None, 
                 existing_machine_file: str = None,
                 critic_feedback: dict = None) -> dict:
    """Run the functional analysis and generate spec.md.
    
    APPROCCIO ITERATIVO:
    1. Carica la macchina esistente (se esiste)
    2. Passala all'LLM con suggerimenti e critic feedback
    3. L'LLM modifica la macchina invece di rigenerarla
    """
    
    start_time = time.time()
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Read context
    with open(context_file, "r", encoding="utf-8") as f:
        context_text = f.read()
    
    # Carica la macchina esistente (se c'è)
    existing_machine = None
    if existing_machine_file and os.path.exists(existing_machine_file):
        with open(existing_machine_file, "r", encoding="utf-8") as f:
            existing_machine = json.load(f)
        print(f"  📦 Macchina esistente caricata: {len(existing_machine.get('states', {}))} stati")
    
    print(f"Context loaded: {len(context_text)} characters")
    if analyst_suggestions:
        print(f"  📋 Analyst suggestions: {len(analyst_suggestions.get('states', []))} states, {len(analyst_suggestions.get('transitions', []))} transitions")
    if critic_feedback:
        critical = critic_feedback.get("summary", {}).get("critical_issues", [])
        print(f"  🚨 Critic feedback: {len(critical)} critical issues")
    print("  🚀 Generazione con LLM...")
    
    # Call LLM (approccio iterativo)
    try:
        llm_data = call_llm_spec(
            context_text, 
            analyst_suggestions=analyst_suggestions,
            existing_machine=existing_machine,
            critic_feedback=critic_feedback
        )
        print(f"  ✅ LLM: {len(llm_data.get('states', []))} states, {len(llm_data.get('transitions', []))} transitions")
    except Exception as e:
        print(f"❌ ERRORE: LLM fallito: {e}")
        print("   Il sistema non può funzionare senza LLM.")
        sys.exit(1)
    
    # Merge con la macchina esistente (se c'è)
    if existing_machine:
        # Inizia dalla macchina esistente
        machine = existing_machine.copy()
        machine["states"] = dict(existing_machine.get("states", {}))
        
        # Aggiungi nuovi stati dai suggerimenti LLM
        for state in llm_data.get("states", []):
            state_name = state["name"]
            if state_name not in machine["states"]:
                machine["states"][state_name] = {
                    "entry": state.get("entry_actions", []),
                    "exit": state.get("exit_actions", []),
                    "on": {}
                }
            else:
                # Aggiorna stato esistente con nuove entry/exit actions
                existing_entry = machine["states"][state_name].get("entry", [])
                new_entry = state.get("entry_actions", [])
                machine["states"][state_name]["entry"] = list(set(existing_entry + new_entry))
                
                existing_exit = machine["states"][state_name].get("exit", [])
                new_exit = state.get("exit_actions", [])
                machine["states"][state_name]["exit"] = list(set(existing_exit + new_exit))
        
        # Aggiungi nuove transizioni
        for trans in llm_data.get("transitions", []):
            from_state = trans["from_state"]
            to_state = trans["to_state"]
            event = trans["event"]
            if from_state in machine["states"]:
                machine["states"][from_state]["on"][event] = to_state
    else:
        # Genera da zero
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
    
    # Fix: if LLM used 'idle' instead of 'app_idle', normalize
    if "idle" in machine["states"] and machine["initial"] == "app_idle":
        machine["states"]["app_idle"] = machine["states"].pop("idle")
        for state_config in machine["states"].values():
            for event, target in list(state_config.get("on", {}).items()):
                if target == "idle":
                    state_config["on"][event] = "app_idle"
    
    # Fix: ensure app_idle exists
    if "app_idle" not in machine["states"]:
        machine["states"]["app_idle"] = {"entry": [], "exit": [], "on": {}}
    
    print(f"Generated state machine: {len(machine['states'])} states")
    
    # Build sections
    edge_cases = llm_data.get("edge_cases", [])
    edge_cases_md = "| ID | Scenario | Expected | Priority |\n|----|----------|----------|----------|\n"
    for ec in edge_cases:
        edge_cases_md += f"| {ec['id']} | {ec['scenario']} | {ec['expected_behavior']} | {ec['priority']} |\n"
    
    flows = llm_data.get("flows", [])
    
    # Generate diagrams
    statechart = generate_plantuml_statechart(machine)
    sequence = generate_plantuml_sequence(flows)
    flows_md = ""
    for flow in flows:
        flows_md += f"\n### {flow['name']}\n"
        for step in flow.get("steps", []):
            flows_md += f"1. **Trigger**: {step.get('trigger', '')}\n"
            flows_md += f"   **Action**: {step.get('action', '')}\n"
            flows_md += f"   **Outcome**: {step.get('expected_outcome', '')}\n"
            if step.get('error_scenario'):
                flows_md += f"   **Error**: {step['error_scenario']}\n"
    
    endpoints = llm_data.get("api_endpoints", [])
    endpoints_md = ""
    for ep in endpoints:
        endpoints_md += f"\n#### {ep['method']} {ep['path']}\n"
        endpoints_md += f"- **Description**: {ep.get('description', '')}\n"
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    states_count = len(machine['states'])
    transitions_count = sum(len(s.get('on', {})) for s in machine['states'].values())
    edge_cases_count = len(edge_cases)
    
    # Build spec
    spec_content = f"""# Specifica Funzionale

Generato: {timestamp}

> Specifica generata automaticamente dal contesto del progetto.

---

## 1. Panoramica

### 1.1 Scope
- Flussi utente
- Macchina a stati (XState eseguibile)
- Analisi edge case
- Gestione errori
- Contratti API

---

## 2. Flussi Utente
{flows_md if flows_md else "*Nessun flusso generato*"}

---

## 3. Macchina a Stati

### 3.1 Diagramma Stati (PlantUML)

```plantuml
{statechart}
```

### 3.2 Configurazione XState

```json
{json.dumps(machine, indent=2)}
```

---

## 4. Diagramma Sequenza (PlantUML)

```plantuml
{sequence}
```

---

## 5. Edge Cases

{edge_cases_md if edge_cases else "*Nessun edge case generato*"}

---

## 6. Gestione Errori

### 6.1 Tipi di Errore

| Codice | Tipo | Messaggio Utente | Azione |
|--------|------|------------------|--------|
| 400 | Bad Request | "Dati non validi." | Correggi input |
| 401 | Unauthorized | "Sessione scaduta." | Login |
| 403 | Forbidden | "Accesso negato." | Contatta support |
| 404 | Not Found | "Risorsa non trovata." | Torna alla home |
| 408 | Timeout | "Richiesta scaduta." | Riprova |
| 429 | Rate Limited | "Troppe richieste." | Attendi |
| 500 | Server Error | "Errore temporaneo." | Riprova |
| 503 | Unavailable | "Servizio non disponibile." | Riprova dopo |

### 6.2 Stati di Errore

La macchina a stati gestisce gli errori attraverso stati dedicati che:
- Registrano l'errore per il debug
- Mostrano messaggi appropriati in italiano
- Offrono opzioni di recupero (retry, cancel, contact support)

---

## 7. Validazione Dati

### 7.1 Regole di Validazione

| Campo | Tipo | Obbligatorio | Pattern | Max Length |
|-------|------|--------------|---------|------------|
| email | email | Sì | RFC 5322 | 254 |
| password | password | Sì | Min 8 chars | 128 |
| search_query | string | Sì | Alfanumerico + spazi | 100 |
| quantity | integer | Sì | > 0 | 9999 |

### 7.2 Feedback Validazione

- Validazione inline al blur
- Validazione summary all'invio
- Messaggi chiari in italiano con istruzioni

---

## 8. Contratto API
{endpoints_md if endpoints_md else "*Nessun endpoint generato*"}

---

## 9. Metriche

### 9.1 Copertura Analisi

- Stati definiti: {states_count}
- Transizioni definite: {transitions_count}
- Edge case identificati: {edge_cases_count}
- Tipi errore gestiti: 8

---

## Appendice A: Contesto Originale

Il contesto originale del progetto è in `project_context.md`.
"""
    
    # Write spec
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(spec_content)
    
    # Write XState
    xstate_file = output_file.replace(".md", "_machine.json")
    with open(xstate_file, "w", encoding="utf-8") as f:
        json.dump(machine, f, indent=2)
    
    elapsed = time.time() - start_time
    
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
    parser.add_argument("--context", type=str, default="output/context/project_context.md",
                        help="Input context file")
    parser.add_argument("--output", type=str, default="output/spec/spec.md",
                        help="Output spec file")
    parser.add_argument("--time-budget", type=int, default=TIME_BUDGET,
                        help="Time budget in seconds")
    parser.add_argument("--suggestions", type=str, default=None,
                        help="Analyst suggestions JSON file")
    parser.add_argument("--machine", type=str, default=None,
                        help="Existing machine JSON file (for iterative approach)")
    parser.add_argument("--critic-feedback", type=str, default=None,
                        help="Critic feedback JSON file")
    args = parser.parse_args()
    
    if not os.path.exists(args.context):
        print(f"Error: Context file not found: {args.context}")
        print("Run 'python ingest.py' first")
        sys.exit(1)
    
    # Load analyst suggestions if provided
    analyst_suggestions = None
    if args.suggestions and os.path.exists(args.suggestions):
        with open(args.suggestions, "r", encoding="utf-8") as f:
            analyst_suggestions = json.load(f)
        print(f"  📋 Analyst suggestions loaded: {args.suggestions}")
    
    # Load critic feedback if provided
    critic_feedback = None
    if args.critic_feedback and os.path.exists(args.critic_feedback):
        with open(args.critic_feedback, "r", encoding="utf-8") as f:
            critic_feedback = json.load(f)
        print(f"  🚨 Critic feedback loaded: {args.critic_feedback}")
    
    print(f"Running functional analysis...")
    print(f"  Context: {args.context}")
    print(f"  Output: {args.output}")
    print(f"  Time budget: {args.time_budget}s")
    print()
    
    metrics = run_analysis(
        args.context, 
        args.output, 
        args.time_budget, 
        analyst_suggestions=analyst_suggestions,
        existing_machine_file=args.machine,
        critic_feedback=critic_feedback
    )
    
    print()
    print("=" * 50)
    print("ANALISI COMPLETATA")
    print("=" * 50)
    print(f"Stati definiti:      {metrics['states_count']}")
    print(f"Transizioni:         {metrics['transitions_count']}")
    print(f"Edge cases:          {metrics['edge_cases_count']}")
    print(f"Tipi errore:         {metrics['error_types_count']}")
    print(f"Tempo:               {metrics['elapsed_seconds']:.1f}s")
    print()
    print(f"File output:")
    print(f"  - {metrics['spec_file']}")
    print(f"  - {metrics['machine_file']}")


if __name__ == "__main__":
    main()