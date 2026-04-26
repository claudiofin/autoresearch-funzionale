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


def _get_navigation_states(machine: dict) -> dict:
    """Get states dict, handling both flat and parallel architectures."""
    if machine.get("type") == "parallel" and "navigation" in machine.get("states", {}):
        return machine["states"]["navigation"].get("states", {})
    return machine.get("states", {})


def get_all_events(machine: dict) -> set:
    """Extract all possible events from the machine."""
    events = set()
    states = _get_navigation_states(machine)
    for state_config in states.values():
        for event in state_config.get("on", {}).keys():
            events.add(event)
        # Also check sub-states
        for sub_config in state_config.get("states", {}).values():
            for event in sub_config.get("on", {}).keys():
                events.add(event)
    return events


def get_all_states(machine: dict) -> set:
    """Extract all states."""
    states = _get_navigation_states(machine)
    all_states = set(states.keys())
    # Also include sub-states
    for state_config in states.values():
        all_states.update(state_config.get("states", {}).keys())
    return all_states


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


def _get_parallel_initial_states(machine: dict) -> list:
    """Get initial states for a parallel machine.
    
    In parallel mode, each branch has its own 'initial' property that points
    to the actual starting state within that branch. We need to resolve these
    to find the real initial states.
    
    Example:
        machine = {
            "type": "parallel",
            "states": {
                "navigation": {"initial": "app_initial", "states": {"app_initial": {...}}},
                "workflows": {"initial": "none", "states": {"none": {...}}}
            }
        }
        → Returns ["app_initial", "none"]
    """
    initial_states = []
    branches = machine.get("states", {})
    
    for branch_name, branch_config in branches.items():
        if not isinstance(branch_config, dict):
            continue
        branch_initial = branch_config.get("initial")
        if branch_initial:
            initial_states.append(branch_initial)
        else:
            # Fallback: use first state in the branch
            branch_states = branch_config.get("states", {})
            if branch_states:
                initial_states.append(next(iter(branch_states)))
    
    return initial_states


def _get_initial_sub_states(states: dict, state_name: str) -> list:
    """Get the initial sub-states of a compound state.
    
    If a state has sub-states with an 'initial' property, return the initial
    sub-state path(s). This allows the fuzzer to enter compound states and
    find more reachable states.
    
    Example:
        states = {
            "app_idle": {
                "initial": "loading",
                "states": {"loading": {...}, "ready": {...}, "error": {...}}
            }
        }
        _get_initial_sub_states(states, "app_idle") → ["app_idle.loading"]
    
    Returns list because some states may have multiple initial sub-states
    (e.g., in parallel compound states).
    """
    if state_name not in states:
        return []
    
    state_config = states[state_name]
    sub_states = state_config.get("states", {})
    
    if not sub_states:
        return []
    
    initial = state_config.get("initial")
    if initial and initial in sub_states:
        return [f"{state_name}.{initial}"]
    
    # Fallback: return first sub-state
    first_sub = next(iter(sub_states), None)
    if first_sub:
        return [f"{state_name}.{first_sub}"]
    
    return []


def _resolve_state_path(states: dict, state_name: str) -> dict:
    """Resolve a state name (possibly with dot notation) to its config.
    
    Handles:
    - Simple: "app_idle" → states["app_idle"]
    - Dotted: "app_idle.loading" → states["app_idle"]["states"]["loading"]
    - Deep: "app_initial.checking_auth.validating" → nested states
    """
    if "." not in state_name:
        return _resolve_state(states, state_name)
    
    parts = state_name.split(".")
    current = states
    for part in parts:
        if part not in current:
            return {}
        current = current[part]
        # Navigate into sub-states if not the last part
        if "states" in current and part != parts[-1]:
            current = current["states"]
    
    return current if isinstance(current, dict) else {}


def find_reachable_states(machine: dict) -> set:
    """Find all states reachable from initial state (BFS).
    
    For parallel machines, enters compound states via their initial sub-states
    to find more reachable states. For example, if app_idle has sub-states
    {loading, ready, error} with initial=loading, the BFS starts from
    app_idle.loading and follows its transitions.
    """
    states = _get_navigation_states(machine)
    
    # Handle parallel architecture
    if machine.get("type") == "parallel":
        # Get actual initial states from each branch's 'initial' property
        initial_states = _get_parallel_initial_states(machine)
    else:
        initial = machine.get("initial", "")
        initial_states = [initial] if initial else []
    
    if not initial_states:
        return set()
    
    reachable = set()
    queue = deque()
    
    for s in initial_states:
        if s in states or _find_in_sub_states(states, s):
            reachable.add(s)
            queue.append(s)
            # FIX: Also enter compound states via their initial sub-states
            sub_initials = _get_initial_sub_states(states, s)
            for sub_path in sub_initials:
                if sub_path not in reachable:
                    reachable.add(sub_path)
                    queue.append(sub_path)
    
    while queue:
        current = queue.popleft()
        
        # Resolve state config (handles dotted paths like "app_idle.loading")
        state_config = _resolve_state_path(states, current)
        if not state_config:
            continue
        
        # Follow transitions
        for event, target in state_config.get("on", {}).items():
            for t in _extract_targets(target):
                t_clean = t.lstrip('.')
                if t_clean and t_clean not in reachable:
                    # Check if target exists
                    if _resolve_state_path(states, t_clean):
                        reachable.add(t_clean)
                        queue.append(t_clean)
                        # Also enter compound targets via their initial sub-states
                        sub_initials = _get_initial_sub_states(states, t_clean)
                        for sub_path in sub_initials:
                            if sub_path not in reachable:
                                reachable.add(sub_path)
                                queue.append(sub_path)
        
        # Also check direct sub-states
        direct_sub_states = state_config.get("states", {})
        for sub_name in direct_sub_states:
            sub_path = f"{current}.{sub_name}" if "." in current else sub_name
            if sub_path not in reachable:
                reachable.add(sub_path)
                queue.append(sub_path)
    
    return reachable


def _find_in_sub_states(states: dict, state_name: str) -> bool:
    """Check if a state exists as a sub-state anywhere."""
    for state_config in states.values():
        if state_name in state_config.get("states", {}):
            return True
    return False


def _pick_random_target(target) -> str:
    """Pick a random target from a transition (handles arrays with guards)."""
    targets = _extract_targets(target)
    if not targets:
        return ""
    return random.choice(targets)


def _resolve_state(states: dict, state_name: str) -> dict:
    """Resolve a state name to its config, checking both top-level and sub-states."""
    if state_name in states:
        return states[state_name]
    # Check sub-states
    for state_config in states.values():
        if state_name in state_config.get("states", {}):
            return state_config["states"][state_name]
    return {}


def simulate_path(machine: dict, max_steps: int = 50) -> dict:
    """Simulate a random path through the state machine.
    
    For parallel machines, enters compound states via their initial sub-states
    to simulate more realistic paths through the state machine.
    """
    states = _get_navigation_states(machine)
    
    # Handle parallel architecture
    if machine.get("type") == "parallel":
        # For simulation, pick a random branch's initial or the branch itself
        branches = list(machine.get("states", {}).keys())
        initial_candidates = []
        for b in branches:
            b_config = machine["states"][b]
            b_initial = b_config.get("initial")
            if b_initial:
                initial_candidates.append(b_initial)
            else:
                initial_candidates.append(b)
        initial = random.choice(initial_candidates) if initial_candidates else ""
    else:
        initial = machine.get("initial", "")
    
    if not initial or not _resolve_state_path(states, initial):
        return {"error": "Invalid initial state", "path": []}
    
    path = [initial]
    current = initial
    steps = 0
    
    while steps < max_steps:
        current_config = _resolve_state_path(states, current)
        if not current_config:
            return {
                "status": "dead_end",
                "path": path,
                "dead_end_state": current,
                "steps": steps
            }
        
        transitions = current_config.get("on", {})
        
        if not transitions:
            # FIX: Try entering compound state via initial sub-state
            sub_initials = _get_initial_sub_states(states, current)
            if sub_initials:
                sub_target = random.choice(sub_initials)
                path.append(sub_target)
                current = sub_target
                steps += 1
                continue
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
        
        target_clean = target.lstrip('.')
        if not _resolve_state_path(states, target_clean):
            return {
                "status": "unknown_target",
                "path": path,
                "event": event,
                "from_state": current,
                "target": target_clean,
                "steps": steps
            }
        
        path.append(target_clean)
        current = target_clean
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
    """Find all loops in the state machine (DFS).
    
    For parallel machines, enters compound states via their initial sub-states
    to detect loops at all levels of the state hierarchy.
    """
    states = _get_navigation_states(machine)
    loops = []
    
    # Handle parallel architecture
    initial_states = []
    if machine.get("type") == "parallel":
        for branch_config in machine.get("states", {}).values():
            b_initial = branch_config.get("initial")
            if b_initial:
                initial_states.append(b_initial)
    else:
        initial = machine.get("initial", "")
        if initial:
            initial_states.append(initial)
    
    def dfs(state, visited, path):
        if state in visited:
            loop_start = path.index(state)
            loop = path[loop_start:] + [state]
            loops.append(loop)
            return
        
        visited.add(state)
        path.append(state)
        
        state_config = _resolve_state_path(states, state)
        if not state_config:
            return
        
        for event, target in state_config.get("on", {}).items():
            for t in _extract_targets(target):
                t_clean = t.lstrip('.')
                if t_clean and _resolve_state_path(states, t_clean):
                    dfs(t_clean, visited.copy(), path.copy())
        
        # Also check initial sub-states for compound states
        sub_initials = _get_initial_sub_states(states, state)
        for sub_path in sub_initials:
            if sub_path not in visited:
                dfs(sub_path, visited.copy(), path.copy())
    
    for initial in initial_states:
        if _resolve_state_path(states, initial):
            dfs(initial, set(), [])
            # Also start DFS from initial sub-states
            sub_initials = _get_initial_sub_states(states, initial)
            for sub_path in sub_initials:
                if _resolve_state_path(states, sub_path):
                    dfs(sub_path, set(), [])
    
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
        
        # Handle error case (invalid initial state, etc.)
        if "error" in result:
            path_results["dead_ends"].append({
                "dead_end_state": "N/A",
                "path": result.get("path", []),
                "steps": 0,
                "error": result["error"]
            })
            continue
        
        status = result.get("status", "")
        if status == "dead_end":
            path_results["dead_ends"].append(result)
        elif status == "invalid_transition":
            path_results["invalid_transitions"].append(result)
        elif status == "unknown_target":
            path_results["unknown_targets"].append(result)
        elif status == "potential_loop":
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
    
    # For parallel machines, report the navigation branch's initial as the main initial state
    if machine.get("type") == "parallel":
        nav_branch = machine.get("states", {}).get("navigation", {})
        reported_initial = nav_branch.get("initial", "unknown")
    else:
        reported_initial = machine.get("initial", "unknown")
    
    return {
        "timestamp": datetime.now().isoformat(),
        "machine_id": machine.get("id", "unknown"),
        "initial_state": reported_initial,
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