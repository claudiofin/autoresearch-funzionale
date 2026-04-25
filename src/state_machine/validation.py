"""State machine validation — enhanced for parallel states and pattern-compiled machines.

Detects:
- Dead-end states (states without exit transitions)
- Unreachable states from initial state (BFS-aware of parallel branches)
- Transitions to undefined states
- Potential infinite loops
- Cross-branch reference validity
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
    - Global ID: "#navigation.success" -> ["navigation.success"]
    """
    if isinstance(target, str):
        # Handle global IDs (#prefix)
        if target.startswith("#"):
            return [target[1:]]
        return [target]
    elif isinstance(target, dict):
        t = target.get("target", "")
        if t.startswith("#"):
            t = t[1:]
        return [t] if t else []
    elif isinstance(target, list):
        targets = []
        for item in target:
            if isinstance(item, dict):
                t = item.get("target", "")
                if t.startswith("#"):
                    t = t[1:]
                if t:
                    targets.append(t)
            elif isinstance(item, str):
                t = item
                if t.startswith("#"):
                    t = t[1:]
                targets.append(t)
        return targets
    return []


def _suggest_exit_transitions(state_name: str) -> str:
    """Suggest exit transitions based on state name pattern.
    
    Suggestions are DOMAIN-AGNOSTIC — they describe the PATTERN, not specific state names.
    """
    name = state_name.lower()
    
    if "error" in name or "fail" in name:
        return "Add: RETRY → a loading/retry state, CANCEL → initial/resting state"
    elif "loading" in name or "connect" in name or "fetch" in name:
        return "Add: CANCEL → previous state, TIMEOUT → error state"
    elif "empty" in name or "no_data" in name or "no_results" in name:
        return "Add: REFRESH → loading state, GO_BACK → initial state"
    elif "timeout" in name:
        return "Add: RETRY → loading state, CANCEL → initial state"
    elif "session" in name or "auth" in name or "login" in name:
        return "Add: REAUTHENTICATE → loading state, EXIT → initial state"
    elif "handler" in name or "processor" in name:
        return "Add: RETRY → parent state, CANCEL → workflow idle state"
    elif "idle" in name or "none" in name or "standby" in name:
        return "This appears to be an idle/none state — it should have a START event to begin a workflow"
    else:
        return "Add at least one appropriate exit transition (GO_BACK, CANCEL, or a domain-specific event)"


def _collect_all_states_recursive(states: dict, prefix: str = "") -> dict:
    """Collect all states with their full paths.
    
    Returns:
        Dict mapping full_path → state_config
    """
    result = {}
    for name, config in states.items():
        full_path = f"{prefix}.{name}" if prefix else name
        result[full_path] = config
        if "states" in config and isinstance(config["states"], dict):
            result.update(_collect_all_states_recursive(config["states"], full_path))
    return result


def _is_final_state(state_name: str, state_config: dict) -> bool:
    """A state is final if:
    1. STRUCTURAL: no transitions + has entry actions (it's a destination)
    2. KEYWORD: name matches known final state keywords (success, ready, done, etc.)
    
    This is a HYBRID check: structural first, keyword fallback.
    """
    has_transitions = bool(state_config.get("on", {}))
    has_entry = bool(state_config.get("entry", []))
    
    # Structural check: no transitions, but has entry actions (it's a destination)
    if not has_transitions and has_entry:
        return True
    
    # Keyword fallback: known final state names
    if not has_transitions:
        final_keywords = ["success", "ready", "complete", "done", "finished", "none"]
        if any(kw in state_name.lower() for kw in final_keywords):
            return True
    
    return False


def _is_error_state(state_name: str, state_config: dict) -> bool:
    """A state is an error state if name contains error/fail/exception OR has RETRY/CANCEL transitions."""
    lower = state_name.lower()
    if "error" in lower or "fail" in lower or "exception" in lower:
        return True
    on = state_config.get("on", {})
    has_retry = any("retry" in k.lower() for k in on.keys())
    has_cancel = any("cancel" in k.lower() for k in on.keys())
    return has_retry or has_cancel


def _find_dead_ends_in_states(states: dict, prefix: str = "") -> list:
    """Find dead-end states recursively."""
    dead_ends = []
    
    for state_name, state_config in states.items():
        full_path = f"{prefix}.{state_name}" if prefix else state_name
        transitions = state_config.get("on", {})
        
        if not transitions:
            # STRUCTURAL check: is this a legitimate final state?
            is_final = _is_final_state(state_name, state_config)
            is_error = _is_error_state(state_name, state_config)
            
            if not is_final and not is_error:
                dead_ends.append({
                    "state": full_path,
                    "issue": "NO_EXIT_TRANSITIONS",
                    "description": f"State '{full_path}' has no exit transitions. User gets stuck.",
                    "suggestion": _suggest_exit_transitions(state_name)
                })
        
        # Recurse into sub-states
        if "states" in state_config and isinstance(state_config["states"], dict):
            dead_ends.extend(_find_dead_ends_in_states(state_config["states"], full_path))
    
    return dead_ends


def find_dead_end_states(machine: dict) -> list:
    """Find states without exit transitions (except final states).
    
    Enhanced to handle parallel states and recursive sub-states.
    """
    states = machine.get("states", {})
    
    if machine.get("type") == "parallel":
        # For parallel states, check each branch independently
        dead_ends = []
        for branch_name, branch_config in states.items():
            branch_states = branch_config.get("states", {})
            dead_ends.extend(_find_dead_ends_in_states(branch_states, branch_name))
        return dead_ends
    
    return _find_dead_ends_in_states(states)


def _bfs_parallel(machine: dict) -> set:
    """BFS for parallel state machines.
    
    In parallel states, ALL top-level branches are active simultaneously.
    We traverse each branch from its initial state.
    """
    states = machine.get("states", {})
    reachable = set()
    
    for branch_name, branch_config in states.items():
        reachable.add(branch_name)
        
        branch_states = branch_config.get("states", {})
        initial = branch_config.get("initial")
        
        if initial and initial in branch_states:
            # BFS within this branch
            queue = deque([initial])
            reachable.add(f"{branch_name}.{initial}")
            
            while queue:
                current = queue.popleft()
                current_config = branch_states.get(current, {})
                transitions = current_config.get("on", {})
                
                for event, target in transitions.items():
                    for t in _extract_targets(target):
                        # Resolve relative targets
                        resolved = _resolve_target_in_branch(t, current, branch_name, branch_states, states)
                        if resolved and resolved not in reachable:
                            reachable.add(resolved)
                            # Add to queue if it's a state in this branch
                            state_name = resolved.split(".")[-1]
                            if state_name in branch_states:
                                queue.append(state_name)
    
    return reachable


def _resolve_target_in_branch(target: str, current: str, branch: str, branch_states: dict, all_states: dict) -> str:
    """Resolve a transition target within a parallel branch context."""
    if not target:
        return None
    
    # Global ID (#prefix)
    if target.startswith("#"):
        return target[1:]
    
    # Relative reference (.prefix)
    if target.startswith("."):
        state_name = target[1:]
        if state_name in branch_states:
            return f"{branch}.{state_name}"
        return None
    
    # Contains . → absolute path
    if "." in target:
        return target
    
    # Simple name → check branch first, then root
    if target in branch_states:
        return f"{branch}.{target}"
    
    # Check if it's a root-level state
    if target in all_states:
        return target
    
    return None


def _bfs_sequential(machine: dict) -> set:
    """BFS for sequential (non-parallel) state machines."""
    states = machine.get("states", {})
    initial = machine.get("initial", "")
    
    if not initial or initial not in states:
        return set()
    
    reachable = {initial}
    queue = deque([initial])
    
    while queue:
        current = queue.popleft()
        if current not in states:
            continue
        
        transitions = states[current].get("on", {})
        for event, target in transitions.items():
            for t in _extract_targets(target):
                if t.startswith("."):
                    t = t[1:]
                
                if t and t not in reachable:
                    reachable.add(t)
                    if t in states:
                        queue.append(t)
    
    return reachable


def find_unreachable_states(machine: dict) -> list:
    """Find states unreachable from initial state.
    
    Enhanced for parallel states: checks each branch independently.
    Also detects invalid initial state.
    """
    states = machine.get("states", {})
    
    # Check for invalid initial state (sequential only)
    if machine.get("type") != "parallel":
        initial = machine.get("initial", "")
        if initial and initial not in states:
            return [{
                "state": initial,
                "issue": "INVALID_INITIAL",
                "description": f"Initial state '{initial}' does not exist in states"
            }]
    
    if machine.get("type") == "parallel":
        reachable = _bfs_parallel(machine)
    else:
        reachable = _bfs_sequential(machine)
    
    # Collect all states
    all_states = _collect_all_states_recursive(states)
    
    unreachable = []
    for full_path in all_states:
        if full_path not in reachable:
            unreachable.append({
                "state": full_path,
                "issue": "UNREACHABLE",
                "description": f"State '{full_path}' is not reachable from initial state"
            })
    
    return unreachable


def _find_invalid_in_states(states: dict, all_state_paths: set, prefix: str = "") -> list:
    """Find invalid transitions recursively."""
    invalid = []
    
    for state_name, state_config in states.items():
        full_path = f"{prefix}.{state_name}" if prefix else state_name
        transitions = state_config.get("on", {})
        
        for event, target in transitions.items():
            for t in _extract_targets(target):
                if not t:
                    continue
                
                # Check if target exists
                if t not in all_state_paths:
                    # Try to resolve relative
                    resolved = False
                    if t.startswith("."):
                        simple = t[1:]
                        sub_states = state_config.get("states", {})
                        if simple in sub_states:
                            resolved = True
                    
                    if not resolved:
                        invalid.append({
                            "from_state": full_path,
                            "event": event,
                            "target": t,
                            "issue": "INVALID_TARGET",
                            "description": f"Transition '{event}' from '{full_path}' points to '{t}' which does not exist"
                        })
        
        # Recurse
        if "states" in state_config and isinstance(state_config["states"], dict):
            invalid.extend(_find_invalid_in_states(state_config["states"], all_state_paths, full_path))
    
    return invalid


def find_invalid_transitions(machine: dict) -> list:
    """Find transitions pointing to undefined states.
    
    Enhanced for parallel states and recursive sub-states.
    """
    states = machine.get("states", {})
    all_paths = set(_collect_all_states_recursive(states).keys())
    
    return _find_invalid_in_states(states, all_paths)


def _find_loops_in_states(states: dict, prefix: str = "") -> list:
    """Find potential infinite loops recursively."""
    loops = []
    
    for state_name, state_config in states.items():
        transitions = state_config.get("on", {})
        
        for event, target in transitions.items():
            for t in _extract_targets(target):
                # Resolve relative
                if t.startswith("."):
                    t = t[1:]
                
                if t and t in states:
                    target_transitions = states[t].get("on", {})
                    for reverse_event, reverse_target in target_transitions.items():
                        for rt in _extract_targets(reverse_target):
                            if rt.startswith("."):
                                rt = rt[1:]
                            
                            if rt == state_name:
                                has_exit_from_source = len(transitions) > 1
                                has_exit_from_target = len(target_transitions) > 1
                                
                                if not has_exit_from_source or not has_exit_from_target:
                                    full_source = f"{prefix}.{state_name}" if prefix else state_name
                                    full_target = f"{prefix}.{t}" if prefix else t
                                    loops.append({
                                        "cycle": [full_source, full_target],
                                        "issue": "POTENTIAL_INFINITE_LOOP",
                                        "description": f"Bidirectional cycle: {full_source} ↔ {full_target}. One of the two states has no other exits."
                                    })
        
        # Recurse
        if "states" in state_config and isinstance(state_config["states"], dict):
            full_path = f"{prefix}.{state_name}" if prefix else state_name
            loops.extend(_find_loops_in_states(state_config["states"], full_path))
    
    return loops


def find_potential_infinite_loops(machine: dict) -> list:
    """Find potential infinite loops (A→B→A without exit).
    
    Enhanced for parallel states.
    """
    states = machine.get("states", {})
    
    if machine.get("type") == "parallel":
        loops = []
        for branch_name, branch_config in states.items():
            branch_states = branch_config.get("states", {})
            loops.extend(_find_loops_in_states(branch_states, branch_name))
        return loops
    
    return _find_loops_in_states(states)


def validate_machine(machine_file) -> dict:
    """Run all validations on the state machine.
    
    Accepts either a file path (str) or a machine dict directly.
    """
    if isinstance(machine_file, dict):
        machine = machine_file
    else:
        machine = load_machine(machine_file)
    
    dead_ends = find_dead_end_states(machine)
    unreachable = find_unreachable_states(machine)
    invalid = find_invalid_transitions(machine)
    loops = find_potential_infinite_loops(machine)
    
    # Count all transitions (recursive)
    all_states = _collect_all_states_recursive(machine.get("states", {}))
    total_transitions = sum(
        len(s.get("on", {})) for s in all_states.values()
    )
    
    results = {
        "machine_id": machine.get("id", "unknown"),
        "initial_state": machine.get("initial", "unknown"),
        "total_states": len(all_states),
        "total_transitions": total_transitions,
        "dead_end_states": dead_ends,
        "unreachable_states": unreachable,
        "invalid_transitions": invalid,
        "potential_loops": loops,
        "dead_end_count": len(dead_ends),
        "unreachable_count": len(unreachable),
        "invalid_transition_count": len(invalid),
        "cycle_count": len(loops),
    }
    
    # Calculate quality score
    issues_count = len(dead_ends) + len(unreachable) + len(invalid)
    total_states = results["total_states"]
    
    if total_states > 0:
        results["quality_score"] = max(0, 100 - (issues_count * 10))
    else:
        results["quality_score"] = 0
    
    results["is_valid"] = (
        len(invalid) == 0 and
        len(unreachable) == 0
    )
    
    return results