"""
Fuzzer per macchina a stati XState.

Simula percorsi casuali sulla macchina a stati per trovare:
- Dead-end states (già coperti dal validator, ma qui li troviamo tramite esecuzione)
- Stati non raggiungibili
- Loop infiniti
- Transizioni non gestite

Usage:
    python src/fuzzer.py --machine output/spec/spec_machine.json
"""

import os
import sys
import json
import random
import argparse
from collections import deque
from datetime import datetime


def load_machine(machine_file: str) -> dict:
    """Carica la macchina a stati."""
    with open(machine_file, "r", encoding="utf-8") as f:
        return json.load(f)


def get_all_events(machine: dict) -> set:
    """Estrae tutti gli eventi possibili dalla macchina."""
    events = set()
    for state_config in machine.get("states", {}).values():
        for event in state_config.get("on", {}).keys():
            events.add(event)
    return events


def get_all_states(machine: dict) -> set:
    """Estrae tutti gli stati."""
    return set(machine.get("states", {}).keys())


def find_reachable_states(machine: dict) -> set:
    """Trova tutti gli stati raggiungibili dallo stato iniziale (BFS)."""
    states = machine.get("states", {})
    initial = machine.get("initial", "")
    
    if not initial or initial not in states:
        return set()
    
    reachable = set()
    queue = deque([initial])
    reachable.add(initial)
    
    while queue:
        current = queue.popleft()
        if current in states:
            for event, target in states[current].get("on", {}).items():
                if isinstance(target, dict):
                    target = target.get("target", "")
                if target and target not in reachable:
                    reachable.add(target)
                    queue.append(target)
    
    return reachable


def simulate_path(machine: dict, max_steps: int = 50) -> dict:
    """Simula un percorso casuale dalla macchina a stati."""
    states = machine.get("states", {})
    initial = machine.get("initial", "")
    
    if not initial or initial not in states:
        return {"error": "Stato iniziale non valido", "path": []}
    
    path = [initial]
    current = initial
    steps = 0
    
    while steps < max_steps:
        transitions = states.get(current, {}).get("on", {})
        
        if not transitions:
            # Dead-end: non ci sono transizioni in uscita
            return {
                "status": "dead_end",
                "path": path,
                "dead_end_state": current,
                "steps": steps
            }
        
        # Scegli evento casuale
        event = random.choice(list(transitions.keys()))
        target = transitions[event]
        
        if isinstance(target, dict):
            target = target.get("target", "")
        
        if not target:
            return {
                "status": "invalid_transition",
                "path": path,
                "event": event,
                "from_state": current,
                "steps": steps
            }
        
        if target not in states:
            return {
                "status": "unknown_target",
                "path": path,
                "event": event,
                "from_state": current,
                "target": target,
                "steps": steps
            }
        
        path.append(target)
        current = target
        steps += 1
    
    # Verifica se siamo in un loop
    if len(path) != len(set(path)):
        return {
            "status": "potential_loop",
            "path": path,
            "steps": steps
        }
    
    return {
        "status": "completed",
        "path": path,
        "steps": steps
    }


def detect_loops(machine: dict) -> list:
    """Trova tutti i loop nella macchina a stati (DFS)."""
    states = machine.get("states", {})
    loops = []
    
    def dfs(state, visited, path):
        if state in visited:
            # Trovato un loop
            loop_start = path.index(state)
            loop = path[loop_start:] + [state]
            loops.append(loop)
            return
        
        visited.add(state)
        path.append(state)
        
        for event, target in states.get(state, {}).get("on", {}).items():
            if isinstance(target, dict):
                target = target.get("target", "")
            if target and target in states:
                dfs(target, visited.copy(), path.copy())
    
    initial = machine.get("initial", "")
    if initial in states:
        dfs(initial, set(), [])
    
    return loops


def run_fuzz_test(machine: dict, num_paths: int = 100, max_steps_per_path: int = 50) -> dict:
    """Esegue il fuzz test completo."""
    
    all_states = get_all_states(machine)
    reachable_states = find_reachable_states(machine)
    unreachable_states = all_states - reachable_states
    
    # Simula percorsi casuali
    path_results = {
        "dead_ends": [],
        "invalid_transitions": [],
        "unknown_targets": [],
        "potential_loops": [],
        "completed_paths": 0,
        "total_paths": num_paths,
    }
    
    for i in range(num_paths):
        result = simulate_path(machine, max_steps_per_path)
        
        if result["status"] == "dead_end":
            path_results["dead_ends"].append(result)
        elif result["status"] == "invalid_transition":
            path_results["invalid_transitions"].append(result)
        elif result["status"] == "unknown_target":
            path_results["unknown_targets"].append(result)
        elif result["status"] == "potential_loop":
            path_results["potential_loops"].append(result)
        else:
            path_results["completed_paths"] += 1
    
    # Trova loop strutturali
    structural_loops = detect_loops(machine)
    
    # Calcola statistiche
    total_errors = (
        len(path_results["dead_ends"]) +
        len(path_results["invalid_transitions"]) +
        len(path_results["unknown_targets"]) +
        len(unreachable_states)
    )
    
    total_warnings = len(path_results["potential_loops"]) + len(structural_loops)
    
    # Bugs trovati (errori che indicano problemi reali)
    bugs_found = []
    
    # Dead-end states unici
    dead_end_states = set()
    for de in path_results["dead_ends"]:
        dead_end_states.add(de["dead_end_state"])
    
    for state in dead_end_states:
        bugs_found.append({
            "type": "dead_end_state",
            "state": state,
            "description": f"Stato '{state}' è un vicolo cieco - l'utente può restare bloccato",
            "severity": "critical"
        })
    
    # Stati non raggiungibili
    for state in unreachable_states:
        bugs_found.append({
            "type": "unreachable_state",
            "state": state,
            "description": f"Stato '{state}' non è raggiungibile dallo stato iniziale",
            "severity": "warning"
        })
    
    # Transizioni a stati sconosciuti
    for ut in path_results["unknown_targets"]:
        bugs_found.append({
            "type": "unknown_target",
            "from_state": ut["from_state"],
            "event": ut["event"],
            "target": ut["target"],
            "description": f"Transizione '{ut['event']}' da '{ut['from_state']}' punta a '{ut['target']}' che non esiste",
            "severity": "critical"
        })
    
    summary = {
        "total_states": len(all_states),
        "reachable_states": len(reachable_states),
        "unreachable_states": len(unreachable_states),
        "total_paths_simulated": num_paths,
        "completed_paths": path_results["completed_paths"],
        "dead_end_paths": len(path_results["dead_ends"]),
        "invalid_transition_paths": len(path_results["invalid_transitions"]),
        "unknown_target_paths": len(path_results["unknown_targets"]),
        "potential_loop_paths": len(path_results["potential_loops"]),
        "structural_loops": len(structural_loops),
        "total_errors": total_errors,
        "total_warnings": total_warnings,
        "bugs_found": len(bugs_found),
        "coverage": f"{len(reachable_states)}/{len(all_states)} states reachable",
    }
    
    return {
        "timestamp": datetime.now().isoformat(),
        "machine_id": machine.get("id", "unknown"),
        "initial_state": machine.get("initial", "unknown"),
        "summary": summary,
        "bugs": bugs_found,
        "path_details": {
            "dead_ends": path_results["dead_ends"][:10],  # Limita output
            "invalid_transitions": path_results["invalid_transitions"][:10],
            "unknown_targets": path_results["unknown_targets"][:10],
            "potential_loops": path_results["potential_loops"][:10],
        },
        "structural_loops": structural_loops[:20],
        "unreachable_states": list(unreachable_states),
    }


def print_report(report: dict):
    """Stampa un report leggibile."""
    summary = report["summary"]
    
    print("\n" + "=" * 60)
    print("FUZZ TEST REPORT")
    print("=" * 60)
    print(f"Machine ID:        {report['machine_id']}")
    print(f"Stato iniziale:    {report['initial_state']}")
    print(f"Stati totali:      {summary['total_states']}")
    print(f"Stati raggiungibili: {summary['reachable_states']}")
    print(f"Stati non raggiungibili: {summary['unreachable_states']}")
    print()
    print(f"Percorsi simulati: {summary['total_paths_simulated']}")
    print(f"Percorsi completi: {summary['completed_paths']}")
    print(f"Percorsi dead-end: {summary['dead_end_paths']}")
    print(f"Percorsi loop:     {summary['potential_loop_paths']}")
    print()
    print(f"Errori totali:     {summary['total_errors']}")
    print(f"Warning totali:    {summary['total_warnings']}")
    print(f"Bugs trovati:      {summary['bugs_found']}")
    print(f"Copertura:         {summary['coverage']}")
    
    if report["bugs"]:
        print(f"\n🐛 BUGS TROVATI ({len(report['bugs'])}):")
        for bug in report["bugs"]:
            severity_icon = "🔴" if bug["severity"] == "critical" else "🟡"
            print(f"  {severity_icon} [{bug['severity'].upper()}] {bug['description']}")
    
    if report["unreachable_states"]:
        print(f"\n⚠️  STATI NON RAGGIUNGIBILI:")
        for state in report["unreachable_states"]:
            print(f"  - {state}")
    
    if report["structural_loops"]:
        print(f"\n🔄 LOOP STRUTTURALI ({len(report['structural_loops'])}):")
        for loop in report["structural_loops"][:5]:
            print(f"  - {' -> '.join(loop)}")
    
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Fuzz test per macchina a stati XState")
    parser.add_argument("--machine", type=str, default="output/spec/spec_machine.json",
                        help="XState machine JSON file")
    parser.add_argument("--output", type=str, default="output/fuzz_report.json",
                        help="Output JSON report file (default: output/fuzz_report.json)")
    parser.add_argument("--num-paths", type=int, default=100,
                        help="Numero di percorsi casuali da simulare (default: 100)")
    parser.add_argument("--max-steps", type=int, default=50,
                        help="Max steps per percorso (default: 50)")
    args = parser.parse_args()
    
    if not os.path.exists(args.machine):
        print(f"Error: Machine file not found: {args.machine}")
        sys.exit(1)
    
    machine = load_machine(args.machine)
    
    print(f"🔍 Fuzz test su macchina '{machine.get('id', 'unknown')}'")
    print(f"   Stati: {len(machine.get('states', {}))}")
    print(f"   Percorsi: {args.num_paths}")
    print(f"   Max steps: {args.max_steps}")
    
    report = run_fuzz_test(machine, args.num_paths, args.max_steps)
    print_report(report)
    
    # Salva report
    output_file = args.output
    os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else ".", exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    
    print(f"\n📄 Report salvato: {output_file}")
    
    # Exit code
    sys.exit(0 if report["summary"]["bugs_found"] == 0 else 1)


if __name__ == "__main__":
    main()