"""State machine validation.

Detects:
- Dead-end states (states without exit transitions)
- Unreachable states from initial state
- Transitions to undefined states
- Potential infinite loops
"""

import json
import os
from collections import deque


def load_machine(machine_file: str) -> dict:
    """Load state machine from JSON file."""
    with open(machine_file, "r", encoding="utf-8") as f:
        return json.load(f)


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


def _suggest_exit_transitions(state_name: str) -> str:
    """Suggest exit transitions based on state name."""
    name = state_name.lower()
    
    if "error" in name or "fail" in name:
        return "Add: RETRY → loading state, CANCEL → initial state"
    elif "loading" in name:
        return "Add: CANCEL → previous state, TIMEOUT → error state"
    elif "empty" in name:
        return "Add: REFRESH → loading state, GO_BACK → initial state"
    elif "timeout" in name:
        return "Add: RETRY → loading state, CANCEL → initial state"
    elif "session" in name or "auth" in name:
        return "Add: REAUTHENTICATE → loading state, EXIT → initial state"
    else:
        return "Add at least one appropriate exit transition"


def find_dead_end_states(machine: dict) -> list:
    """Find states without exit transitions (except final states)."""
    dead_ends = []
    states = machine.get("states", {})
    
    # States that can be final (by convention)
    final_keywords = ["success", "ready", "complete", "done", "finished"]
    
    for state_name, state_config in states.items():
        transitions = state_config.get("on", {})
        
        if not transitions:
            # Check if it's a legitimate final state
            is_final = any(kw in state_name.lower() for kw in final_keywords)
            
            if not is_final:
                dead_ends.append({
                    "state": state_name,
                    "issue": "NO_EXIT_TRANSITIONS",
                    "description": f"State '{state_name}' has no exit transitions. User gets stuck.",
                    "suggestion": _suggest_exit_transitions(state_name)
                })
    
    return dead_ends


def find_unreachable_states(machine: dict) -> list:
    """Find states unreachable from initial state."""
    states = machine.get("states", {})
    initial = machine.get("initial", "")
    
    if not initial or initial not in states:
        return [{"issue": "INVALID_INITIAL", "description": f"Initial state '{initial}' not found"}]
    
    # BFS to find all reachable states
    reachable = set()
    queue = deque([initial])
    reachable.add(initial)
    
    while queue:
        current = queue.popleft()
        if current in states:
            transitions = states[current].get("on", {})
            for event, target in transitions.items():
                for t in _extract_targets(target):
                    if t not in reachable:
                        reachable.add(t)
                        queue.append(t)
    
    unreachable = []
    for state_name in states:
        if state_name not in reachable:
            unreachable.append({
                "state": state_name,
                "issue": "UNREACHABLE",
                "description": f"State '{state_name}' is not reachable from initial state '{initial}'"
            })
    
    return unreachable


def find_invalid_transitions(machine: dict) -> list:
    """Find transitions pointing to undefined states."""
    states = machine.get("states", {})
    invalid = []
    
    for state_name, state_config in states.items():
        transitions = state_config.get("on", {})
        for event, target in transitions.items():
            for t in _extract_targets(target):
                if t and t not in states:
                    invalid.append({
                        "from_state": state_name,
                        "event": event,
                        "target": t,
                        "issue": "INVALID_TARGET",
                        "description": f"Transition '{event}' from '{state_name}' points to '{t}' which does not exist"
                    })
    
    return invalid


def find_potential_infinite_loops(machine: dict) -> list:
    """Find potential infinite loops (A→B→A without exit)."""
    states = machine.get("states", {})
    loops = []
    
    for state_name, state_config in states.items():
        transitions = state_config.get("on", {})
        for event, target in transitions.items():
            for t in _extract_targets(target):
                if t and t in states:
                    # Check if there's a reverse transition
                    target_transitions = states[t].get("on", {})
                    for reverse_event, reverse_target in target_transitions.items():
                        for rt in _extract_targets(reverse_target):
                            if rt == state_name:
                                # Cycle found: state_name ↔ t
                                # Check if at least one of them has an exit
                                has_exit_from_source = len(transitions) > 1
                                has_exit_from_target = len(target_transitions) > 1
                                
                                if not has_exit_from_source or not has_exit_from_target:
                                    loops.append({
                                        "cycle": [state_name, t],
                                        "issue": "POTENTIAL_INFINITE_LOOP",
                                        "description": f"Bidirectional cycle: {state_name} ↔ {t}. One of the two states has no other exits."
                                    })
    
    return loops


def validate_machine(machine_file: str) -> dict:
    """Run all validations on the state machine."""
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
        # Counts for loop.py
        "dead_end_count": 0,
        "unreachable_count": 0,
        "invalid_transition_count": 0,
        "cycle_count": 0,
    }
    
    # Calculate counts
    results["dead_end_count"] = len(results["dead_end_states"])
    results["unreachable_count"] = len(results["unreachable_states"])
    results["invalid_transition_count"] = len(results["invalid_transitions"])
    results["cycle_count"] = len(results["potential_loops"])
    
    # Calculate quality score
    issues_count = (
        len(results["dead_end_states"]) +
        len(results["unreachable_states"]) +
        len(results["invalid_transitions"])
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