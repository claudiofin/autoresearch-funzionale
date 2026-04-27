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


def _collect_all_states_recursive(states: dict, prefix: str = "", depth: int = 0) -> dict:
    """Collect all states with their full paths.
    
    Returns:
        Dict mapping full_path → state_config
    """
    if depth > 15:
        return {}  # Safety limit to prevent infinite recursion
    result = {}
    for name, config in states.items():
        full_path = f"{prefix}.{name}" if prefix else name
        result[full_path] = config
        if "states" in config and isinstance(config["states"], dict):
            result.update(_collect_all_states_recursive(config["states"], full_path, depth + 1))
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


def _find_flat_substate_initial(full_path: str, all_paths: set) -> str:
    """Find the initial sub-state of a flat-path state.
    
    Since sub-states may be defined as flat paths (e.g., 'navigation.auth_guard.verifying.validating')
    rather than nested, we need to find them by checking which paths start with full_path + '.'
    and match the 'initial' pattern.
    
    We use a heuristic: look for paths that are direct children of full_path
    (i.e., have exactly one more path component).
    """
    prefix = f"{full_path}."
    children = [p for p in all_paths if p.startswith(prefix) and p.count(".") == full_path.count(".") + 1]
    if children:
        # Return the first child (alphabetically, which often matches 'initial' naming)
        # Common initial sub-state names: loading, validating, error_handler, ready
        for name in ["loading", "validating", "error_handler", "ready", "initializing", "checking_auth",
                      "verifying", "authenticating", "creating", "syncing", "connected", "routing"]:
            candidate = f"{full_path}.{name}"
            if candidate in children:
                return candidate
        return children[0]
    return None


def _add_compound_initial_chain(state_name: str, state_config: dict, prefix: str, reachable: set, queue_list: list = None, all_paths: set = None) -> None:
    """Add a state and recursively follow its initial sub-state chain.
    
    When entering a compound state like 'app_idle' with initial='loading',
    we must also mark 'app_idle.loading' (and its initial sub-state, etc.)
    as reachable. This prevents 176 false-positive unreachable states.
    
    If queue_list is provided, also append each chain state to it for BFS processing.
    
    If all_paths is provided, also check for flat-path sub-states (states defined
    as 'navigation.auth_guard.verifying.validating' rather than nested).
    """
    full_path = f"{prefix}.{state_name}" if prefix else state_name
    if full_path in reachable:
        return
    reachable.add(full_path)
    if queue_list is not None:
        queue_list.append(full_path)
    
    sub_states = state_config.get("states", {})
    sub_initial = state_config.get("initial")
    
    if sub_initial:
        # First try nested sub-state
        if sub_initial in sub_states:
            _add_compound_initial_chain(sub_initial, sub_states[sub_initial], full_path, reachable, queue_list, all_paths)
        # Fallback: check if sub-state exists as a flat path
        elif all_paths is not None:
            candidate = f"{full_path}.{sub_initial}"
            if candidate in all_paths and candidate not in reachable:
                if queue_list is not None:
                    queue_list.append(candidate)
                # Recursively follow its initial chain using flat-path lookup
                _follow_flat_initial_chain(candidate, all_paths, reachable, queue_list)


def _follow_flat_initial_chain(full_path: str, all_paths: set, reachable: set, queue_list: list = None) -> None:
    """Follow the initial sub-state chain for flat-path states.
    
    For states defined as flat paths, we find sub-states by checking which
    paths in all_paths are direct children of the current path.
    """
    if full_path in reachable:
        return
    reachable.add(full_path)
    if queue_list is not None:
        queue_list.append(full_path)
    
    # Find direct children of this state
    prefix = f"{full_path}."
    depth = full_path.count(".")
    children = [p for p in all_paths if p.startswith(prefix) and p.count(".") == depth + 1]
    
    if children:
        # Try to find the initial sub-state by common naming patterns
        initial_name = None
        for name in ["loading", "validating", "error_handler", "ready", "initializing", "checking_auth",
                      "verifying", "authenticating", "creating", "syncing", "connected", "routing"]:
            candidate = f"{full_path}.{name}"
            if candidate in children:
                initial_name = name
                break
        
        if initial_name:
            child_path = f"{full_path}.{initial_name}"
            if child_path not in reachable:
                _follow_flat_initial_chain(child_path, all_paths, reachable, queue_list)


def _find_state_config(full_path: str, branch_name: str, branch_states: dict) -> dict:
    """Find a state config by its full path within a branch.
    
    E.g., 'navigation.auth_guard.verifying' with branch_name='navigation'
    → navigate branch_states → auth_guard → verifying
    
    The full_path may include the branch prefix or not — we strip it if present.
    """
    # Strip branch prefix if present
    if full_path.startswith(f"{branch_name}."):
        path_without_branch = full_path[len(branch_name) + 1:]
    else:
        path_without_branch = full_path
    
    parts = path_without_branch.split(".")
    config = branch_states
    for part in parts:
        if isinstance(config, dict) and part in config:
            config = config[part]
        else:
            return {}
    return config if isinstance(config, dict) else {}


def _get_all_transitions_for_state(full_path: str, branch_name: str, branch_states: dict) -> dict:
    """Get ALL transitions for a state, including parent compound state transitions.
    
    In XState, events bubble up from child to parent. So if you're in
    'app_idle.loading.error_handler', the START_APP transition on 'app_idle'
    is still valid. This prevents false-unreachable states.
    
    The full_path may include the branch prefix (e.g., 'navigation.app_idle.loading')
    but branch_states is already the branch's states dict, so we strip the prefix.
    
    Returns merged transitions dict (child overrides parent).
    """
    # Strip branch prefix if present
    if full_path.startswith(f"{branch_name}."):
        path_without_branch = full_path[len(branch_name) + 1:]
    else:
        path_without_branch = full_path
    
    parts = path_without_branch.split(".")
    merged = {}
    
    # Walk from root to leaf, merging transitions at each level
    current_config = branch_states
    for part in parts:
        if isinstance(current_config, dict) and part in current_config:
            state_cfg = current_config[part]
            if isinstance(state_cfg, dict):
                parent_on = state_cfg.get("on", {})
                for evt, tgt in parent_on.items():
                    if evt not in merged:  # Child overrides parent
                        merged[evt] = tgt
                current_config = state_cfg.get("states", {})
        else:
            break
    
    return merged


def _bfs_parallel(machine: dict) -> set:
    """BFS for parallel state machines.
    
    In parallel states, ALL top-level branches are active simultaneously.
    We traverse each branch from its initial state, FOLLOWING compound state
    initial chains (e.g., app_idle → app_idle.loading → app_idle.loading.error_handler).
    
    FIX 1: Previously only marked the top-level initial state, causing 176 false
    unreachable states. Now recursively enters compound states via their 'initial' property.
    
    FIX 2: Events bubble up from child to parent in XState. If you're in
    'app_idle.loading.error_handler', the START_APP transition on 'app_idle'
    is still valid. We now merge parent transitions when traversing.
    
    FIX 3: Queue now uses FULL paths (e.g., 'app_idle.loading.error_handler') instead
    of short names, so we can properly navigate the state tree.
    
    FIX 4: Handles flat-path sub-states (states defined as 'navigation.auth_guard.verifying.validating'
    rather than nested under their parent).
    """
    states = machine.get("states", {})
    all_paths = set(_collect_all_states_recursive(states).keys())
    reachable = set()
    
    for branch_name, branch_config in states.items():
        reachable.add(branch_name)
        
        branch_states = branch_config.get("states", {})
        initial = branch_config.get("initial")
        
        if initial and initial in branch_states:
            initial_config = branch_states[initial]
            # BFS within this branch — queue uses FULL paths
            queue = deque()
            # Follow the compound state initial chain AND add all chain states to queue
            _add_compound_initial_chain(initial, initial_config, branch_name, reachable, queue, all_paths)
            
            while queue:
                current_full = queue.popleft()
                # Get transitions including parent compound state transitions
                transitions = _get_all_transitions_for_state(current_full, branch_name, branch_states)
                
                for event, target in transitions.items():
                    for t in _extract_targets(target):
                        # Resolve relative targets
                        resolved = _resolve_target_in_branch(t, current_full, branch_name, branch_states, states)
                        if resolved and resolved not in reachable:
                            # If target is a compound state, follow its initial chain FIRST
                            # (before adding to reachable, so _add_compound_initial_chain doesn't early-return)
                            target_config = _find_state_config(resolved, branch_name, branch_states)
                            if target_config:
                                _add_compound_initial_chain(resolved.split(".")[-1], target_config, 
                                                           ".".join(resolved.split(".")[:-1]), reachable, queue, all_paths)
                            else:
                                # Not a compound state — just add it directly
                                reachable.add(resolved)
                                if resolved.startswith(f"{branch_name}."):
                                    queue.append(resolved)
                                elif resolved in branch_states:
                                    queue.append(f"{branch_name}.{resolved}")
    
    return reachable


def _navigate_to_state(config: dict, path_parts: list) -> dict:
    """Navigate the state tree, handling parallel branch structure.
    
    For parallel branches like 'navigation', the structure is:
    {"navigation": {"type": "parallel", "states": {"app_idle": {...}, ...}}}
    
    So after entering 'navigation', we need to go into config["states"].
    """
    for part in path_parts:
        if isinstance(config, dict) and part in config:
            config = config[part]
        elif isinstance(config, dict) and "states" in config and part in config["states"]:
            config = config["states"][part]
        else:
            return None
    return config


def _resolve_target_in_branch(target: str, current: str, branch: str, branch_states: dict, all_states: dict) -> str:
    """Resolve a transition target within a parallel branch context.
    
    Resolution order:
    1. Global ID (#prefix) → strip # and return
    2. Relative reference (.suffix) → resolve to sibling in parent compound state
    3. Absolute path with branch prefix (navigation.X) → check if exists in branch
    4. Absolute path without branch prefix → return as-is
    5. Simple name → check branch_states, then sibling in parent, then all_states
    """
    if not target:
        return None
    
    # Global ID (#prefix)
    if target.startswith("#"):
        return target[1:]
    
    # Relative reference (.suffix) — resolve to sibling in parent compound state
    if target.startswith("."):
        suffix = target[1:]
        if not suffix:
            return None
        
        # Parse current path to find parent levels
        parts = current.split(".")
        
        # Try each level of the path as a potential parent
        for i in range(len(parts) - 1, 0, -1):
            parent_path = ".".join(parts[:i])
            # Navigate to the parent using the parallel-aware navigator
            path_parts = parent_path.split(".")
            config = _navigate_to_state(all_states, path_parts)
            
            if config is None:
                continue
            
            # Check if suffix is a sibling in this parent's states
            parent_states = config.get("states", {})
            if suffix in parent_states:
                return f"{parent_path}.{suffix}"
        
        return None
    
    # Contains . → could be absolute path like 'navigation.auth_guard'
    if "." in target:
        parts = target.split(".")
        # Check if it's a self-reference to this branch (e.g., 'navigation.auth_guard' in navigation branch)
        if len(parts) >= 2 and parts[0] == branch:
            # Navigate to find if this state exists in the branch
            config = branch_states
            for part in parts[1:]:
                if isinstance(config, dict) and part in config:
                    config = config[part]
                else:
                    config = None
                    break
            if config is not None:
                return target  # It exists in this branch
        # Otherwise treat as absolute path (might be a flat state at root)
        return target
    
    # Simple name → check branch first
    if target in branch_states:
        return f"{branch}.{target}"
    
    # Check if it's a sibling in the parent compound state
    # E.g., from 'navigation.app_idle.loading', 'ready' → 'navigation.app_idle.ready'
    parts = current.split(".")
    for i in range(len(parts) - 1, 0, -1):
        parent_path = ".".join(parts[:i])
        candidate = f"{parent_path}.{target}"
        # Check if this candidate exists using the parallel-aware navigator
        check_parts = candidate.split(".")
        check_config = _navigate_to_state(all_states, check_parts)
        if check_config is not None:
            return candidate
    
    # Check if it's a root-level flat state
    if target in all_states:
        return target
    
    return None


def _bfs_sequential(machine: dict) -> set:
    """BFS for sequential (non-parallel) state machines.
    
    FIX: When entering a compound state, also mark its initial sub-state
    (and recursively) as reachable. This prevents false positives for
    sub-states like 'auth_guard.loading', 'dashboard.ready', etc.
    """
    states = machine.get("states", {})
    initial = machine.get("initial", "")
    
    if not initial or initial not in states:
        return set()
    
    reachable = set()
    queue = deque()
    
    def _add_state_and_descendants(state_name: str, parent_config: dict, prefix: str = ""):
        """Add a state and its initial sub-state chain to reachable."""
        full_path = f"{prefix}.{state_name}" if prefix else state_name
        if full_path in reachable:
            return
        reachable.add(full_path)
        
        config = parent_config.get(state_name, {})
        sub_states = config.get("states", {})
        if sub_states:
            # Mark the initial sub-state as reachable
            sub_initial = config.get("initial")
            if sub_initial and sub_initial in sub_states:
                _add_state_and_descendants(sub_initial, sub_states, full_path)
    
    _add_state_and_descendants(initial, states)
    queue.append(initial)
    
    while queue:
        current = queue.popleft()
        if current not in states:
            continue
        
        config = states[current]
        transitions = config.get("on", {})
        for event, target in transitions.items():
            for t in _extract_targets(target):
                if t.startswith("."):
                    t = t[1:]
                
                if t and t not in reachable:
                    reachable.add(t)
                    # If target is a compound state, also add its initial sub-state
                    if t in states:
                        target_config = states[t]
                        sub_states = target_config.get("states", {})
                        if sub_states:
                            sub_initial = target_config.get("initial")
                            if sub_initial and sub_initial in sub_states:
                                _add_state_and_descendants(sub_initial, sub_states, t)
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


def _resolve_relative_target(target: str, current_full_path: str, states: dict, all_state_paths: set) -> bool:
    """Resolve an XState relative target (.suffix) to check if it's valid.
    
    In XState, '.ready' means 'the sibling state named ready in the same parent compound state'.
    E.g., from 'navigation.app_idle.loading', '.ready' resolves to 'navigation.app_idle.ready'.
    
    We use all_state_paths to check if the candidate path exists — no tree navigation needed.
    """
    if not target.startswith("."):
        return False
    
    suffix = target[1:]
    if not suffix:
        return False
    
    # Parse the current path to find parent levels
    parts = current_full_path.split(".")
    
    # Try each ancestor as a potential parent
    # E.g., from 'navigation.app_idle.loading.error_handler', try:
    #   - navigation.app_idle.loading.ready
    #   - navigation.app_idle.ready
    #   - navigation.ready
    for i in range(len(parts) - 1, 0, -1):
        parent_path = ".".join(parts[:i])
        candidate = f"{parent_path}.{suffix}"
        if candidate in all_state_paths:
            return True
    
    return False


def _resolve_bare_target(target: str, current_full_path: str, states: dict, all_state_paths: set) -> bool:
    """Resolve a bare target (no prefix) to check if it's a valid sibling.
    
    E.g., from 'navigation.app_idle.loading', target 'ready' should resolve
    to 'navigation.app_idle.ready' (sibling in same parent).
    """
    parts = current_full_path.split(".")
    
    # Try each ancestor as a potential parent
    for i in range(len(parts) - 1, 0, -1):
        parent_path = ".".join(parts[:i])
        candidate = f"{parent_path}.{target}"
        if candidate in all_state_paths:
            return True
    
    return False


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
                
                # Check if target exists directly
                if t in all_state_paths:
                    continue
                
                # Try to resolve relative target (.suffix → sibling in parent)
                if t.startswith("."):
                    if _resolve_relative_target(t, full_path, states, all_state_paths):
                        continue
                
                # Try to resolve bare target (loading, ready, error → sibling in parent)
                elif "." not in t and not t.startswith("#"):
                    if _resolve_bare_target(t, full_path, states, all_state_paths):
                        continue
                
                # Target doesn't exist
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
    # Use weighted formula: dead ends and invalid transitions are critical,
    # unreachable states are less severe (may be intentional fallback states)
    dead_end_weight = 15
    invalid_weight = 15
    unreachable_weight = 2  # Much lower weight for unreachable states
    
    issues_count = (len(dead_ends) * dead_end_weight + 
                   len(invalid) * invalid_weight + 
                   len(unreachable) * unreachable_weight)
    total_states = results["total_states"]
    
    if total_states > 0:
        # Scale: max penalty is 100, but unreachable states contribute much less
        results["quality_score"] = max(0, 100 - issues_count)
    else:
        results["quality_score"] = 0
    
    results["is_valid"] = (
        len(invalid) == 0 and
        len(unreachable) == 0
    )
    
    return results