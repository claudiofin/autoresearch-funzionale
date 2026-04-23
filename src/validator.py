"""
Validatore automatico della macchina a stati XState.

Rileva:
- Dead-end states (stati senza transizioni in uscita)
- Stati non raggiungibili dallo stato iniziale
- Transizioni a stati non definiti
- Cicli infiniti potenziali

Usage:
    python src/validator.py --machine output/spec/spec_machine.json
"""

import os
import sys
import json
import argparse
from collections import deque


def load_machine(machine_file: str) -> dict:
    """Carica la macchina a stati dal file JSON."""
    with open(machine_file, "r", encoding="utf-8") as f:
        return json.load(f)


def find_dead_end_states(machine: dict) -> list[dict]:
    """Trova stati senza transizioni in uscita (tranne stati finali)."""
    dead_ends = []
    states = machine.get("states", {})
    
    # Stati che possono essere finali (per convenzione)
    final_keywords = ["success", "ready", "complete", "done", "finished"]
    
    for state_name, state_config in states.items():
        transitions = state_config.get("on", {})
        
        if not transitions:
            # Verifica se è uno stato finale legittimo
            is_final = any(kw in state_name.lower() for kw in final_keywords)
            
            if not is_final:
                dead_ends.append({
                    "state": state_name,
                    "issue": "NO_EXIT_TRANSITIONS",
                    "description": f"Stato '{state_name}' non ha transizioni in uscita. L'utente resta bloccato.",
                    "suggestion": _suggest_exit_transitions(state_name)
                })
    
    return dead_ends


def _suggest_exit_transitions(state_name: str) -> str:
    """Suggerisce transizioni di uscita basate sul nome dello stato."""
    name = state_name.lower()
    
    if "error" in name or "fail" in name:
        return "Aggiungi: RIPROVA → stato di loading, ANNULLA → stato iniziale"
    elif "loading" in name:
        return "Aggiungi: ANNULLA → stato precedente, TIMEOUT → stato errore"
    elif "empty" in name or "vuoto" in name:
        return "Aggiungi: AGGIORNA → stato di loading, TORNA_INDIETRO → stato iniziale"
    elif "timeout" in name:
        return "Aggiungi: RIPROVA → stato di loading, ANNULLA → stato iniziale"
    elif "session" in name or "auth" in name:
        return "Aggiungi: RIAUTENTICAZIONE → stato di loading, ESCI → stato iniziale"
    else:
        return "Aggiungi almeno una transizione di uscita appropriata"


def find_unreachable_states(machine: dict) -> list[dict]:
    """Trova stati non raggiungibili dallo stato iniziale."""
    states = machine.get("states", {})
    initial = machine.get("initial", "")
    
    if not initial or initial not in states:
        return [{"issue": "INVALID_INITIAL", "description": f"Stato iniziale '{initial}' non trovato"}]
    
    # BFS per trovare tutti gli stati raggiungibili
    reachable = set()
    queue = deque([initial])
    reachable.add(initial)
    
    while queue:
        current = queue.popleft()
        if current in states:
            transitions = states[current].get("on", {})
            for event, target in transitions.items():
                if isinstance(target, dict):
                    target = target.get("target", target)
                if target not in reachable:
                    reachable.add(target)
                    queue.append(target)
    
    unreachable = []
    for state_name in states:
        if state_name not in reachable:
            unreachable.append({
                "state": state_name,
                "issue": "UNREACHABLE",
                "description": f"Stato '{state_name}' non è raggiungibile dallo stato iniziale '{initial}'"
            })
    
    return unreachable


def find_invalid_transitions(machine: dict) -> list[dict]:
    """Trova transizioni che puntano a stati non definiti."""
    states = machine.get("states", {})
    invalid = []
    
    for state_name, state_config in states.items():
        transitions = state_config.get("on", {})
        for event, target in transitions.items():
            if isinstance(target, dict):
                target = target.get("target", "")
            
            if target and target not in states:
                invalid.append({
                    "from_state": state_name,
                    "event": event,
                    "target": target,
                    "issue": "INVALID_TARGET",
                    "description": f"Transizione '{event}' da '{state_name}' punta a '{target}' che non esiste"
                })
    
    return invalid


def find_potential_infinite_loops(machine: dict) -> list[dict]:
    """Trova potenziali cicli infiniti (A→B→A senza uscita)."""
    states = machine.get("states", {})
    loops = []
    
    for state_name, state_config in states.items():
        transitions = state_config.get("on", {})
        for event, target in transitions.items():
            if isinstance(target, dict):
                target = target.get("target", "")
            
            if target and target in states:
                # Verifica se c'è una transizione inversa
                target_transitions = states[target].get("on", {})
                for reverse_event, reverse_target in target_transitions.items():
                    if isinstance(reverse_target, dict):
                        reverse_target = reverse_target.get("target", "")
                    
                    if reverse_target == state_name:
                        # Ciclo trovato: state_name ↔ target
                        # Verifica se almeno uno dei due ha un'uscita
                        has_exit_from_source = len(transitions) > 1
                        has_exit_from_target = len(target_transitions) > 1
                        
                        if not has_exit_from_source or not has_exit_from_target:
                            loops.append({
                                "cycle": [state_name, target],
                                "issue": "POTENTIAL_INFINITE_LOOP",
                                "description": f"Ciclo bidirezionale: {state_name} ↔ {target}. Uno dei due stati non ha altre uscite."
                            })
    
    return loops


def validate_machine(machine_file: str) -> dict:
    """Esegue tutte le validazioni sulla macchina a stati."""
    machine = load_machine(machine_file)
    
    results = {
        "machine_id": machine.get("id", "unknown"),
        "initial_state": machine.get("initial", "unknown"),
        "total_states": len(machine.get("states", {})),
        "total_transitions": sum(
            len(s.get("on", {})) for s in machine.get("states", {}).values()
        ),
        "dead_end_states": find_dead_end_states(machine),
        "unreachable_states": find_unreachable_states(machine),
        "invalid_transitions": find_invalid_transitions(machine),
        "potential_loops": find_potential_infinite_loops(machine),
    }
    
    # Calcola score di qualità
    issues_count = (
        len(results["dead_end_states"]) +
        len(results["unreachable_states"]) +
        len(results["invalid_transitions"]) +
        len(results["potential_loops"])
    )
    
    total_states = results["total_states"]
    if total_states > 0:
        results["quality_score"] = max(0, 100 - (issues_count * 15))
    else:
        results["quality_score"] = 0
    
    results["is_valid"] = (
        len(results["invalid_transitions"]) == 0 and
        len(results["unreachable_states"]) == 0
    )
    
    return results


def print_report(results: dict):
    """Stampa un report leggibile dei risultati."""
    print("\n" + "=" * 60)
    print("VALIDAZIONE MACCHINA A STATI")
    print("=" * 60)
    print(f"Machine ID:        {results['machine_id']}")
    print(f"Stato iniziale:    {results['initial_state']}")
    print(f"Stati totali:      {results['total_states']}")
    print(f"Transizioni totali:{results['total_transitions']}")
    print(f"Quality Score:     {results['quality_score']}/100")
    print(f"Valida:            {'✅ SÌ' if results['is_valid'] else '❌ NO'}")
    
    # Dead-end states
    if results["dead_end_states"]:
        print(f"\n⚠️  DEAD-END STATES ({len(results['dead_end_states'])}):")
        for issue in results["dead_end_states"]:
            print(f"  - {issue['state']}: {issue['description']}")
            print(f"    💡 {issue['suggestion']}")
    
    # Unreachable states
    if results["unreachable_states"]:
        print(f"\n⚠️  STATI NON RAGGIUNGIBILI ({len(results['unreachable_states'])}):")
        for issue in results["unreachable_states"]:
            print(f"  - {issue['state']}: {issue['description']}")
    
    # Invalid transitions
    if results["invalid_transitions"]:
        print(f"\n❌ TRANSIZIONI INVALIDE ({len(results['invalid_transitions'])}):")
        for issue in results["invalid_transitions"]:
            print(f"  - {issue['description']}")
    
    # Potential loops
    if results["potential_loops"]:
        print(f"\n⚠️  POTENZIALI CICLI INFINITI ({len(results['potential_loops'])}):")
        for issue in results["potential_loops"]:
            print(f"  - {issue['description']}")
    
    if not any([
        results["dead_end_states"],
        results["unreachable_states"],
        results["invalid_transitions"],
        results["potential_loops"]
    ]):
        print("\n✅ Nessuna issue trovata. La macchina a stati è ben strutturata.")
    
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Valida macchina a stati XState")
    parser.add_argument("--machine", type=str, default="output/spec/spec_machine.json",
                        help="XState machine JSON file")
    parser.add_argument("--output", type=str, default=None,
                        help="Output JSON report file (optional)")
    args = parser.parse_args()
    
    if not os.path.exists(args.machine):
        print(f"Error: Machine file not found: {args.machine}")
        sys.exit(1)
    
    results = validate_machine(args.machine)
    print_report(results)
    
    if args.output:
        os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"\n📄 Report salvato: {args.output}")
    
    # Exit code based on validity
    sys.exit(0 if results["is_valid"] else 1)


if __name__ == "__main__":
    main()