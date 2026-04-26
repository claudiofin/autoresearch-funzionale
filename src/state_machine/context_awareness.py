"""Context awareness for state machines.

Adds guards to retry transitions, emergency exits to workflow states.
"""

from state_machine.constants import DEFAULT_GUARD_NAMES


def _is_in_workflow_branch(state_path: str, machine: dict) -> bool:
    """Check if a state path is inside the workflow branch.
    
    STRUCTURAL: checks if the path starts with the workflow branch name.
    Works with both 'workflows' and 'active_workflows' branch names.
    
    Args:
        state_path: Full state path (e.g., "active_workflows.benchmark.discovery")
        machine: The full state machine dict
    
    Returns:
        True if the state is inside a workflow branch
    """
    return state_path.startswith("workflows.") or state_path.startswith("active_workflows.")


def _find_session_expired_target(machine: dict) -> str:
    """Find the session_expired state in the machine.
    
    STRUCTURAL: dynamically finds the session_expired state.
    Searches in navigation branch first, then at root level, then anywhere.
    GENERIC FALLBACK: Uses _find_session_expired_target's own search instead of
    hardcoding navigation.{initial}.
    
    Args:
        machine: The full state machine dict
    
    Returns:
        Absolute path to session_expired state, or fallback to error/dashboard
    """
    states = machine.get("states", {})
    
    # 1. Search in navigation branch
    nav = states.get("navigation", {})
    nav_states = nav.get("states", {})
    if "session_expired" in nav_states:
        return "navigation.session_expired"
    
    # 2. Check at root level
    if "session_expired" in states:
        return "session_expired"
    
    # 3. Search in ANY branch (generic fallback)
    for branch_name, branch_config in states.items():
        if branch_name in ("workflows", "active_workflows"):
            continue
        if isinstance(branch_config, dict):
            branch_states = branch_config.get("states", {})
            if "session_expired" in branch_states:
                return f"{branch_name}.session_expired"
    
    # 4. Fallback to error state (anywhere)
    if "error" in nav_states:
        return "navigation.error"
    if "error" in states:
        return "error"
    for branch_name, branch_config in states.items():
        if isinstance(branch_config, dict):
            branch_states = branch_config.get("states", {})
            if "error" in branch_states:
                return f"{branch_name}.error"
    
    # 5. GENERIC FALLBACK: Return first screen state (not hardcoded navigation.app_initial)
    from state_machine.injection import _find_first_valid_screen_state
    return _find_first_valid_screen_state(machine)


def _find_error_target(machine: dict) -> str:
    """Find the error state in the machine.
    
    STRUCTURAL: dynamically finds the error state.
    GENERIC FALLBACK: Uses _find_first_valid_screen_state instead of hardcoding.
    
    Args:
        machine: The full state machine dict
    
    Returns:
        Absolute path to error state, or fallback to first screen state
    """
    states = machine.get("states", {})
    
    # 1. Search in navigation branch
    nav = states.get("navigation", {})
    nav_states = nav.get("states", {})
    if "error" in nav_states:
        return "navigation.error"
    
    # 2. Check at root level
    if "error" in states:
        return "error"
    
    # 3. Search in ANY branch (generic fallback)
    for branch_name, branch_config in states.items():
        if branch_name in ("workflows", "active_workflows"):
            continue
        if isinstance(branch_config, dict):
            branch_states = branch_config.get("states", {})
            if "error" in branch_states:
                return f"{branch_name}.error"
    
    # 4. GENERIC FALLBACK: Return first screen state (not hardcoded navigation.app_initial)
    from state_machine.injection import _find_first_valid_screen_state
    return _find_first_valid_screen_state(machine)


def apply_context_awareness(machine: dict) -> dict:
    """Add context-aware guards and actions to error/retry transitions.
    
    STRUCTURAL: This function analyzes the machine and adds:
    1. Guards to RETRY transitions in error states (canRetry / !canRetry)
    2. Assign actions to increment retryCount on positive retry
    3. Emergency exits for workflow states (SESSION_EXPIRED, NETWORK_LOST)
    
    This is GENERIC — it works for any state machine, not just this one.
    It detects error states by name pattern ("error" in name) and workflow
    states by branch membership.
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with context-aware guards and emergency exits
    """
    states = machine.get("states", {})
    can_retry_guard = DEFAULT_GUARD_NAMES["can_retry"]
    session_expired_target = _find_session_expired_target(machine)
    error_target = _find_error_target(machine)
    
    def _process_states(states_dict: dict, prefix: str = "", depth: int = 0) -> None:
        if depth > 10:
            return
        
        for name, config in states_dict.items():
            full_path = f"{prefix}.{name}" if prefix else name
            
            # 1. Add guards to RETRY transitions in error states
            if "error" in name.lower():
                transitions = config.get("on", {})
                
                if "RETRY" in transitions and isinstance(transitions["RETRY"], str):
                    current_target = transitions["RETRY"]
                    transitions["RETRY"] = [
                        {
                            "target": current_target,
                            "cond": can_retry_guard,
                            "actions": ["incrementRetryCount"]
                        },
                        {
                            "target": session_expired_target,
                            "cond": f"!{can_retry_guard}"
                        }
                    ]
                
                if "RETRY_FETCH" in transitions and isinstance(transitions["RETRY_FETCH"], str):
                    current_target = transitions["RETRY_FETCH"]
                    transitions["RETRY_FETCH"] = [
                        {
                            "target": current_target,
                            "cond": can_retry_guard,
                            "actions": ["incrementRetryCount"]
                        },
                        {
                            "target": session_expired_target,
                            "cond": f"!{can_retry_guard}"
                        }
                    ]
            
            # 2. Add emergency exits to workflow states
            if _is_in_workflow_branch(full_path, machine):
                transitions = config.get("on", {})
                if "SESSION_EXPIRED" not in transitions:
                    transitions["SESSION_EXPIRED"] = session_expired_target
                if "NETWORK_LOST" not in transitions:
                    transitions["NETWORK_LOST"] = error_target
            
            # Recurse into sub-states
            if "states" in config:
                _process_states(config["states"], full_path, depth + 1)
    
    _process_states(states)
    return machine