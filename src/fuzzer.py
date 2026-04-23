"""
Fuzzer for XState state machine.

Simulates random paths on the state machine to find:
- Dead-end states (already covered by validator, but here we find them through execution)
- Unreachable states
- Infinite loops
- Unhandled transitions

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
    """Load state machine from JSON file."""
    with open(machine_file, "r", encoding="utf-8") as f:
        return json.load(f)


def get_all_events(machine: dict) -> set:
    """Extract all possible events from the machine."""
    events = set()
    for state_config in machine.get("states", {}).values():
        for event in state_config.get("on", {}).keys():
            events.add(event)
    return events


def get_all_states(machine: dict) -> set:
    """Extract all states."""
    return set(machine.get("states", {}).keys())


def _extract_targets(target) -> list:
    """Extract target state names from transition.
    
    Handles:
    - Simple string: "success" -> ["success"]
    - Dict with guard: {"target": "success", "cond": "hasData"} -> ["success"]
    - Array of conditions: [{"target": "success", "cond": "hasData"}, {"target": "empty"}] -> ["success", "empty"]
    """
    if isinstance(target, str):
        return [target]
    elif isinstance(target, dict):
        t = target.get("target", "")
        return [t] if t else []
    elif isinstance(target, list):
        targets = []
        for item in target:
            if isinstance(item, dict):
                t = item.get("target", "")
                if t:
                    targets.append(t)
            elif isinstance(item, str):
                targets.append(item)
        return targets
    return []


def find_reachable_states(machine: dict) -> set:
    """Find all states reachable from initial state (BFS)."""
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
                for t in _extract_targets(target):
                    if t and t not in reachable:
                        reachable.add(t)
                        queue.append(t)
    
    return reachable


def _pick_random_target(target) -> str:
    """Pick a random target from a transition (handles arrays with guards)."""
    targets = _extract_targets(target)
    if not targets:
        return ""
    return random.choice(targets)


def simulate_path(machine: dict, max_steps: int = 50) -> dict:
    """Simulate a random path through the state machine."""
    states = machine.get("states", {})
    initial = machine.get("initial", "")
    
    if not initial or initial not in states:
        return {"error": "Invalid initial state", "path": []}
    
    path = [initial]
    current = initial
    steps = 0
    
    while steps < max_steps:
        transitions = states.get(current, {}).get("on", {})
        
        if not transitions:
            # Dead-end: no exit transitions
            return {
                "status": "dead_end",
                "path": path,
                "dead_end_state": current,
                "steps": steps
            }
        
        # Choose random event
        event = random.choice(list(transitions.keys()))
        target = _pick_random_target(transitions[event])
        
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
    
    # Check if we're in a loop
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
    """Find all loops in the state machine (DFS)."""
    states = machine.get("states", {})
    loops = []
    
    def dfs(state, visited, path):
        if state in visited:
            # Loop found
            loop_start = path.index(state)
            loop = path[loop_start:] + [state]
            loops.append(loop)
            return
        
        visited.add(state)
        path.append(state)
        
        for event, target in states.get(state, {}).get("on", {}).items():
            for t in _extract_targets(target):
                if t and t in states:
                    dfs(t, visited.copy(), path.copy())
    
    initial = machine.get("initial", "")
    if initial in states:
        dfs(initial, set(), [])
    
    return loops


def run_fuzz_test(machine: dict, num_paths: int = 100, max_steps_per_path: int = 50) -> dict:
    """Run complete fuzz test."""
    
    all_states = get_all_states(machine)
    reachable_states = find_reachable_states(machine)
    unreachable_states = all_states - reachable_states
    
    # Simulate random paths
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
    
    # Find structural loops
    structural_loops = detect_loops(machine)
    
    # Calculate statistics
    total_errors = (
        len(path_results["dead_ends"]) +
        len(path_results["invalid_transitions"]) +
        len(path_results["unknown_targets"]) +
        len(unreachable_states)
    )
    
    total_warnings = len(path_results["potential_loops"]) + len(structural_loops)
    
    # Bugs found (errors indicating real problems)
    bugs_found = []
    
    # Unique dead-end states
    dead_end_states = set()
    for de in path_results["dead_ends"]:
        dead_end_states.add(de["dead_end_state"])
    
    for state in dead_end_states:
        bugs_found.append({
            "type": "dead_end_state",
            "state": state,
            "description": f"State '{state}' is a dead-end - user can get stuck",
            "severity": "critical"
        })
    
    # Unreachable states
    for state in unreachable_states:
        bugs_found.append({
            "type": "unreachable_state",
            "state": state,
            "description": f"State '{state}' is not reachable from initial state",
            "severity": "warning"
        })
    
    # Transitions to unknown states
    for ut in path_results["unknown_targets"]:
        bugs_found.append({
            "type": "unknown_target",
            "from_state": ut["from_state"],
            "event": ut["event"],
            "target": ut["target"],
            "description": f"Transition '{ut['event']}' from '{ut['from_state']}' points to '{ut['target']}' which does not exist",
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
            "dead_ends": path_results["dead_ends"][:10],  # Limit output
            "invalid_transitions": path_results["invalid_transitions"][:10],
            "unknown_targets": path_results["unknown_targets"][:10],
            "potential_loops": path_results["potential_loops"][:10],
        },
        "structural_loops": structural_loops[:20],
        "unreachable_states": list(unreachable_states),
    }


def print_report(report: dict):
    """Print a readable report."""
    summary = report["summary"]
    
    print("\n" + "=" * 60)
    print("FUZZ TEST REPORT")
    print("=" * 60)
    print(f"Machine ID:        {report['machine_id']}")
    print(f"Initial state:     {report['initial_state']}")
    print(f"Total states:      {summary['total_states']}")
    print(f"Reachable states:  {summary['reachable_states']}")
    print(f"Unreachable states:{summary['unreachable_states']}")
    print()
    print(f"Paths simulated:   {summary['total_paths_simulated']}")
    print(f"Completed paths:   {summary['completed_paths']}")
    print(f"Dead-end paths:    {summary['dead_end_paths']}")
    print(f"Loop paths:        {summary['potential_loop_paths']}")
    print()
    print(f"Total errors:      {summary['total_errors']}")
    print(f"Total warnings:    {summary['total_warnings']}")
    print(f"Bugs found:        {summary['bugs_found']}")
    print(f"Coverage:          {summary['coverage']}")
    
    if report["bugs"]:
        print(f"\n🐛 BUGS FOUND ({len(report['bugs'])}):")
        for bug in report["bugs"]:
            severity_icon = "🔴" if bug["severity"] == "critical" else "🟡"
            print(f"  {severity_icon} [{bug['severity'].upper()}] {bug['description']}")
    
    if report["unreachable_states"]:
        print(f"\n⚠️  UNREACHABLE STATES:")
        for state in report["unreachable_states"]:
            print(f"  - {state}")
    
    if report["structural_loops"]:
        print(f"\n🔄 STRUCTURAL LOOPS ({len(report['structural_loops'])}):")
        for loop in report["structural_loops"][:5]:
            print(f"  - {' -> '.join(loop)}")
    
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Fuzz test for XState state machine")
    parser.add_argument("--machine", type=str, default="output/spec/spec_machine.json",
                        help="XState machine JSON file")
    parser.add_argument("--output", type=str, default="output/spec/fuzz_report.json",
                        help="Output JSON report file (default: output/spec/fuzz_report.json)")
    parser.add_argument("--num-paths", type=int, default=100,
                        help="Number of random paths to simulate (default: 100)")
    parser.add_argument("--max-steps", type=int, default=50,
                        help="Max steps per path (default: 50)")
    args = parser.parse_args()
    
    if not os.path.exists(args.machine):
        print(f"Error: Machine file not found: {args.machine}")
        sys.exit(1)
    
    machine = load_machine(args.machine)
    
    print(f"🔍 Fuzz test on machine '{machine.get('id', 'unknown')}'")
    print(f"   States: {len(machine.get('states', {}))}")
    print(f"   Paths: {args.num_paths}")
    print(f"   Max steps: {args.max_steps}")
    
    report = run_fuzz_test(machine, args.num_paths, args.max_steps)
    print_report(report)
    
    # Save report
    output_file = args.output
    os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else ".", exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    
    print(f"\n📄 Report saved: {output_file}")
    
    # Exit code
    sys.exit(0 if report["summary"]["bugs_found"] == 0 else 1)


if __name__ == "__main__":
    main()