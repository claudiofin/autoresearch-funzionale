"""
Fuzzer engine - simulates random paths on state machines to find bugs.
"""

import json
import random
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
            return {
                "status": "dead_end",
                "path": path,
                "dead_end_state": current,
                "steps": steps
            }
        
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
    
    structural_loops = detect_loops(machine)
    
    total_errors = (
        len(path_results["dead_ends"]) +
        len(path_results["invalid_transitions"]) +
        len(path_results["unknown_targets"]) +
        len(unreachable_states)
    )
    
    total_warnings = len(path_results["potential_loops"]) + len(structural_loops)
    
    bugs_found = []
    
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
    
    for state in unreachable_states:
        bugs_found.append({
            "type": "unreachable_state",
            "state": state,
            "description": f"State '{state}' is not reachable from initial state",
            "severity": "warning"
        })
    
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
            "dead_ends": path_results["dead_ends"][:10],
            "invalid_transitions": path_results["invalid_transitions"][:10],
            "unknown_targets": path_results["unknown_targets"][:10],
            "potential_loops": path_results["potential_loops"][:10],
        },
        "structural_loops": structural_loops[:20],
        "unreachable_states": list(unreachable_states),
    }