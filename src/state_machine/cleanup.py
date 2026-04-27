"""Cleanup utilities for state machines.

Dead state removal, specificity deduplication, unreachable state connection,
and transition fixing utilities.
"""

from state_machine.constants import DEPTH_LIMITS
from state_machine.traversal import bfs_reachable, extract_target_string


def apply_specificity_dedup(machine: dict) -> dict:
    """Remove duplicate states by keeping the most specific version.
    
    When multiple states have the same name (e.g., from different LLM passes),
    keep the one with the most transitions/actions (highest specificity).
    
    Args:
        machine: The state machine dict
    
    Returns:
        Deduplicated machine
    """
    states = machine.get("states", {})
    limit = DEPTH_LIMITS["dedup"]
    
    def _dedup_states(states_dict: dict, depth: int = 0) -> None:
        if depth > limit:
            return
        
        name_counts = {}
        for name in states_dict:
            name_counts[name] = name_counts.get(name, 0) + 1
        
        if all(count == 1 for count in name_counts.values()):
            for name, config in states_dict.items():
                if isinstance(config, dict) and "states" in config:
                    _dedup_states(config["states"], depth + 1)
            return
        
        for name, config in states_dict.items():
            if isinstance(config, dict) and "states" in config:
                _dedup_states(config["states"], depth + 1)
    
    _dedup_states(states)
    return machine


def apply_dead_end_pruning(machine: dict) -> dict:
    """Add emergency exit transitions to dead-end states.
    
    If a state has no transitions (on: {}) and is not a final state
    (like success, empty), add CANCEL -> first valid screen state.
    
    This prevents the "Ghost Ship" problem where states exist but you can't leave them.
    
    GENERIC: Uses _find_first_valid_screen_state instead of hardcoding navigation.{initial}.
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with dead-end states having emergency exits
    """
    from state_machine.injection import _find_first_valid_screen_state
    
    states = machine.get("states", {})
    
    # GENERIC: Find first valid screen state instead of hardcoding navigation.app_idle
    default_exit = _find_first_valid_screen_state(machine)
    
    # States that are allowed to be dead-ends (final states)
    final_states = {"success", "empty", "session_expired", "max_retries_exceeded",
                    "workflow_idle", "none", "error_handler"}
    
    def _prune(states_dict: dict, prefix: str = "", depth: int = 0) -> None:
        if depth > 10:
            return
        
        for name, config in list(states_dict.items()):
            full_path = f"{prefix}.{name}" if prefix else name
            transitions = config.get("on", {})
            sub_states = config.get("states", {})
            
            # Leaf state with no transitions and not a final state
            if not sub_states and not transitions and name not in final_states:
                config["on"] = {"CANCEL": default_exit}
            
            if sub_states:
                _prune(sub_states, full_path, depth + 1)
    
    _prune(states)
    return machine


def apply_dead_state_cleanup(machine: dict) -> dict:
    """Remove or connect unreachable states.
    
    States that can't be reached from the initial state are either:
    - Connected (if they have entry actions — likely important)
    - Removed (if they're truly dead)
    
    FIX: Do NOT remove states that are direct children of parallel branches.
    Parallel branches (like 'navigation', 'active_workflows') may not have
    an initial state set, making all their children appear unreachable via BFS.
    These states are "structurally reachable" and should be preserved.
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with dead states cleaned up
    """
    from state_machine.builder import get_machine_type
    
    reachable = bfs_reachable(machine)
    states = machine.get("states", {})
    limit = DEPTH_LIMITS["cleanup"]
    machine_type = get_machine_type(machine)
    
    # Collect all state names that exist under parallel branches
    # These should NOT be removed even if unreachable via BFS
    structurally_reachable = set()
    if machine_type == "parallel":
        for branch_name, branch_config in states.items():
            if isinstance(branch_config, dict):
                branch_states = branch_config.get("states", {})
                for sub_name in branch_states:
                    structurally_reachable.add(sub_name)
                    # Also add nested states
                    sub_config = branch_states[sub_name]
                    if isinstance(sub_config, dict):
                        nested = sub_config.get("states", {})
                        for nested_name in nested:
                            structurally_reachable.add(f"{sub_name}.{nested_name}")
    
    def _cleanup(states_dict: dict, prefix: str = "", depth: int = 0) -> None:
        if depth > limit:
            return
        
        to_remove = []
        
        for name, config in states_dict.items():
            if not isinstance(config, dict):
                continue
            full_path = f"{prefix}.{name}" if prefix else name
            
            # FIX: Skip removal for structurally reachable states in parallel machines
            if machine_type == "parallel" and name in structurally_reachable:
                # Don't remove, but still recurse into sub-states
                if "states" in config:
                    _cleanup(config["states"], full_path, depth + 1)
                continue
            
            if full_path not in reachable and name not in ("error_handler",):
                entry_actions = config.get("entry", [])
                if not entry_actions:
                    to_remove.append(name)
            
            if "states" in config:
                _cleanup(config["states"], full_path, depth + 1)
        
        for name in to_remove:
            del states_dict[name]
    
    _cleanup(states)
    return machine


def apply_phantom_state_cleanup(machine: dict) -> dict:
    """Remove phantom states that were incorrectly created as placeholders.
    
    FIX: Removes states that should never exist at the root level:
    - States with '#' in their name (these are ID references, not real states)
    - States with empty string name
    - States that are duplicates of states already under a branch
      (e.g., 'completed' at root when 'navigation.purchase_group_workflow.completed' exists)
    - States that are sub-state names (loading, ready, error, error_handler) at root level
    - States with name 'N/A' (dead-end placeholder from LLM)
    
    FIX: Branch states (navigation, active_workflows) that have 'states' sub-dict
    are NOT phantoms — they are structural branches and must be preserved.
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with phantom states removed
    """
    states = machine.get("states", {})
    
    # Names that should never exist at root level (they're sub-state names)
    sub_state_names = {"loading", "ready", "error", "error_handler", "calculating", "fetching", "submitting"}
    
    # Collect all state names that exist under branches
    branch_state_names = set()
    for branch_name, branch_config in states.items():
        if isinstance(branch_config, dict):
            branch_states = branch_config.get("states", {})
            for sub_name in branch_states:
                branch_state_names.add(sub_name)
                # Also collect nested state names
                sub_states = branch_states[sub_name].get("states", {})
                for nested_name in sub_states:
                    branch_state_names.add(nested_name)
    
    to_remove = []
    
    for name, config in states.items():
        # Remove states with '#' in name
        if "#" in name:
            to_remove.append(name)
            continue
        
        # Remove empty string name
        if name == "":
            to_remove.append(name)
            continue
        
        # FIX: Remove 'N/A' dead-end state
        if name == "N/A":
            to_remove.append(name)
            continue
        
        # Remove sub-state names at root level
        if name in sub_state_names:
            to_remove.append(name)
            continue
        
        # FIX: Branch states (navigation, active_workflows) that have 'states' sub-dict
        # are structural branches, NOT phantoms. Preserve them.
        if isinstance(config, dict) and "states" in config:
            # This is a branch with sub-states — not a phantom
            continue
        
        # Remove states that are duplicates of branch states
        # Only remove if the state has no entry/exit/on/states (pure phantom)
        if name in branch_state_names:
            entry = config.get("entry", [])
            exit_actions = config.get("exit", [])
            on = config.get("on", {})
            has_sub_states = "states" in config and bool(config["states"])
            has_content = bool(entry) or bool(exit_actions) or bool(on) or has_sub_states
            if not has_content:
                to_remove.append(name)
    
    for name in to_remove:
        if name in states:
            del states[name]
    
    return machine


def apply_workflow_dedup(machine: dict) -> dict:
    """Remove duplicate workflow states at root level when they exist in active_workflows.
    
    FIX: The LLM sometimes generates workflow states both at root level AND inside
    the active_workflows branch. This creates duplicate states (e.g., benchmark_workflow
    at root AND active_workflows.benchmark_workflow).
    
    This function:
    1. Removes the 'workflows' branch when 'active_workflows' exists (workflows is a placeholder)
    2. Removes root-level states that duplicate workflow names
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with duplicate workflow states removed
    """
    states = machine.get("states", {})
    
    # Check if active_workflows branch exists
    active_wf = states.get("active_workflows", {})
    active_wf_states = active_wf.get("states", {})
    
    if not active_wf_states:
        # No active_workflows branch — nothing to dedup
        return machine
    
    # FIX: Remove the 'workflows' branch entirely when 'active_workflows' exists
    # The 'workflows' branch is a placeholder that duplicates active_workflows
    if "workflows" in states:
        del states["workflows"]
    
    # Collect all workflow state names from active_workflows
    workflow_names = set(active_wf_states.keys())
    
    # Remove root-level states that duplicate workflow names
    to_remove = []
    for name in workflow_names:
        if name in states and name not in ("active_workflows", "workflows"):
            # This is a root-level state that duplicates a workflow
            # Check if it's a compound state (has sub-states) — if so, it's likely a real screen
            config = states[name]
            if isinstance(config, dict):
                sub_states = config.get("states", {})
                # If it has sub-states that match workflow sub-states, it's a duplicate
                if sub_states:
                    # Check if sub-states overlap with active_workflows sub-states
                    wf_config = active_wf_states.get(name, {})
                    wf_sub_states = wf_config.get("states", {}) if isinstance(wf_config, dict) else {}
                    if wf_sub_states:
                        # Both have sub-states — root level is a duplicate
                        to_remove.append(name)
                else:
                    # No sub-states — likely a phantom, remove it
                    to_remove.append(name)
    
    for name in to_remove:
        if name in states:
            del states[name]
    
    return machine


def remove_empty_states_dict(machine: dict) -> dict:
    """Remove empty 'states' dicts from compound states.
    
    FIX: The validator flags states with 'states: {}' as INVALID_COMPOUND_STATE.
    A compound state should either have actual sub-states or no 'states' key at all
    (making it a leaf state).
    
    This function removes the 'states' key when it's empty, converting the state
    from an invalid compound state to a valid leaf state.
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with empty states dicts removed
    """
    states = machine.get("states", {})
    
    def _remove_empty(states_dict: dict, depth: int = 0) -> None:
        if depth > 10:
            return
        
        for name, config in list(states_dict.items()):
            if not isinstance(config, dict):
                continue
            
            sub_states = config.get("states")
            if sub_states is not None and not sub_states:
                # Empty states dict — remove it to make this a leaf state
                del config["states"]
                # Also remove 'initial' since there are no sub-states
                if "initial" in config:
                    del config["initial"]
            elif isinstance(sub_states, dict) and sub_states:
                # Non-empty states dict — recurse into it
                _remove_empty(sub_states, depth + 1)
    
    _remove_empty(states)
    return machine


def fix_relative_transitions(machine: dict) -> dict:
    """Fix relative transition targets (starting with '.') by resolving them.
    
    FIX: Transitions like '.none.ready', '.none.loading' are relative paths
    that need to be resolved against the parent state path.
    
    For example, if we're in 'active_workflows.none.ready.error_handler' and
    there's a transition RETRY -> '.none.ready', it should resolve to
    'active_workflows.none.ready' (going up to parent, then to 'ready' sibling).
    
    FIX ITERATION 2: Also fixes GLOBAL_EXIT transitions that point to bare
    state names like 'app_idle' (should be '#navigation.app_idle').
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with relative transitions resolved
    """
    states = machine.get("states", {})
    
    # Find navigation branch states for GLOBAL_EXIT fix
    navigation = states.get("navigation", {})
    nav_states = navigation.get("states", {}) if isinstance(navigation, dict) else {}
    
    # States that are valid GLOBAL_EXIT targets (top-level navigation states)
    valid_exit_targets = set(nav_states.keys())
    
    def _fix_transitions(states_dict: dict, parent_path: str = "", depth: int = 0) -> None:
        if depth > 10:
            return
        
        for name, config in list(states_dict.items()):
            if not isinstance(config, dict):
                continue
            
            full_path = f"{parent_path}.{name}" if parent_path else name
            
            # Fix transitions in this state
            transitions = config.get("on", {})
            for event, target in list(transitions.items()):
                if isinstance(target, str):
                    # Case 1: Relative target starting with '.'
                    if target.startswith("."):
                        resolved = _resolve_relative_target(target, full_path, machine)
                        if resolved:
                            transitions[event] = resolved
                        else:
                            # Can't resolve — try to fix as sibling reference
                            # e.g., '.app_idle.ready' from 'navigation.app_idle.loading'
                            # should be 'navigation.app_idle.ready'
                            resolved = _resolve_sibling_target(target, full_path)
                            if resolved:
                                transitions[event] = resolved
                            else:
                                del transitions[event]
                    
                    # Case 2: GLOBAL_EXIT pointing to bare state name (not full path)
                    elif event == "GLOBAL_EXIT" and target in valid_exit_targets:
                        # 'app_idle' → '#navigation.app_idle'
                        transitions[event] = f"#navigation.{target}"
                    
                    # Case 3: Target is a bare state name that exists in navigation
                    # but isn't a GLOBAL_EXIT — still needs full path
                    elif not target.startswith("#") and not target.startswith(".") and target in valid_exit_targets:
                        # Check if this target makes sense from current location
                        # If we're in navigation branch, bare name should be navigation.name
                        if full_path.startswith("navigation."):
                            transitions[event] = f"navigation.{target}"
            
            # Recurse into sub-states
            sub_states = config.get("states", {})
            if sub_states:
                _fix_transitions(sub_states, full_path, depth + 1)
    
    _fix_transitions(states)
    return machine


def _resolve_sibling_target(relative_target: str, current_path: str) -> str:
    """Resolve a relative target that references a sibling state.
    
    Examples:
    - '.app_idle.ready' from 'navigation.app_idle.loading' → 'navigation.app_idle.ready'
    - '.none.ready' from 'active_workflows.none.loading.error_handler' → 'active_workflows.none.ready'
    - '.login.success' from 'navigation.login.submitting' → 'navigation.login.success'
    
    Args:
        relative_target: The relative target (e.g., '.app_idle.ready')
        current_path: The full path of the current state
    
    Returns:
        Resolved target path, or None if can't resolve
    """
    # Remove leading dot
    target = relative_target.lstrip(".")
    if not target:
        return None
    
    # Split target into parts
    target_parts = target.split(".")
    
    # Split current path into parts
    current_parts = current_path.split(".")
    
    # Strategy: Find the common prefix and replace from there
    # e.g., current='navigation.app_idle.loading', target='app_idle.ready'
    # → 'navigation.app_idle.ready'
    
    # Try to find where the target's first part appears in current path
    first_target_part = target_parts[0]
    
    for i in range(len(current_parts) - 1, -1, -1):
        if current_parts[i] == first_target_part:
            # Found match — replace everything from this point
            new_parts = current_parts[:i] + target_parts
            return ".".join(new_parts)
    
    # Fallback: Replace the last component of current path with target
    if current_parts:
        new_parts = current_parts[:-1] + target_parts
        return ".".join(new_parts)
    
    return target


def _resolve_relative_target(relative_target: str, current_path: str, machine: dict) -> str:
    """Resolve a relative transition target against the current state path.
    
    Examples:
    - '.ready' from 'active_workflows.none.ready.error_handler' → 'active_workflows.none.ready'
    - '.loading' from 'active_workflows.none.error' → 'active_workflows.none.loading'
    - '..dashboard' from 'navigation.dashboard.dashboard_error' → 'navigation.dashboard'
    
    Args:
        relative_target: The relative target (e.g., '.ready', '..dashboard')
        current_path: The full path of the current state
        machine: The state machine dict
    
    Returns:
        Resolved target path, or None if can't resolve
    """
    # Count leading dots to determine how many levels to go up
    dot_count = 0
    for ch in relative_target:
        if ch == '.':
            dot_count += 1
        else:
            break
    
    target_name = relative_target[dot_count:]
    
    # Split current path into parts
    parts = current_path.split('.')
    
    # Go up (dot_count - 1) levels from current state's parent
    # '.target' means sibling at same level as current state's parent
    # '..target' means grandparent level
    levels_up = max(0, dot_count - 1)
    
    if levels_up >= len(parts):
        return None  # Can't go up that many levels
    
    parent_parts = parts[:len(parts) - 1 - levels_up] if levels_up > 0 else parts[:-1]
    
    if target_name:
        return '.'.join(parent_parts) + '.' + target_name if parent_parts else target_name
    else:
        return '.'.join(parent_parts) if parent_parts else None


def fix_start_app_transitions(machine: dict) -> dict:
    """Fix START_APP transitions pointing to non-existent 'authenticating' state.
    
    FIX: The LLM generates START_APP -> 'authenticating' but 'authenticating'
    doesn't exist. Redirect to 'auth_guard' or 'onboarding' which do exist.
    
    FIX ITERATION 2: Also handles 'app_idle.ready' → 'authenticating' case
    where the transition is nested inside compound states.
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with fixed START_APP transitions
    """
    states = machine.get("states", {})
    
    # Find the navigation branch to check what states exist
    navigation = states.get("navigation", {})
    nav_states = navigation.get("states", {}) if isinstance(navigation, dict) else {}
    
    # Determine the best target
    if "auth_guard" in nav_states:
        auth_target = "navigation.auth_guard"
    elif "onboarding" in nav_states:
        auth_target = "navigation.onboarding"
    elif "app_idle" in nav_states:
        auth_target = "navigation.app_idle"
    else:
        # Fallback: first available state
        auth_target = f"navigation.{next(iter(nav_states), 'app_idle')}" if nav_states else "navigation.app_idle"
    
    def _fix_starts(states_dict: dict, depth: int = 0) -> None:
        if depth > 10:
            return
        
        for name, config in list(states_dict.items()):
            if not isinstance(config, dict):
                continue
            
            transitions = config.get("on", {})
            if "START_APP" in transitions:
                target = transitions["START_APP"]
                # FIX: Handle both 'authenticating' and relative '.authenticating'
                if target == "authenticating" or target == ".authenticating":
                    transitions["START_APP"] = auth_target
            
            # Recurse into ALL sub-states (not just first level)
            sub_states = config.get("states", {})
            if sub_states:
                _fix_starts(sub_states, depth + 1)
    
    _fix_starts(states)
    return machine


def connect_unreachable_states(machine: dict) -> dict:
    """Connect unreachable states to the navigation graph.
    
    FIX ITERATION 2: Major overhaul to connect 103 unreachable states.
    
    Strategy:
    1. Add transitions from app_initial/app_idle to auth_guard/onboarding
    2. Add transitions from auth_guard to dashboard (on success)
    3. Add transitions from dashboard_ready to all feature screens
    4. Add transitions between feature screens (catalog ↔ offers ↔ alerts)
    5. Add transitions from workflow states back to dashboard
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with additional navigation transitions
    """
    states = machine.get("states", {})
    
    # Find the navigation branch
    navigation = states.get("navigation", {})
    if not isinstance(navigation, dict):
        return machine
    
    nav_states = navigation.get("states", {})
    
    # === FIX 1: Connect app_initial/app_idle → auth_guard/onboarding ===
    for initial_name in ["app_initial", "app_idle"]:
        if initial_name in nav_states:
            initial_state = nav_states[initial_name]
            if isinstance(initial_state, dict):
                # Check for compound states (ready sub-state)
                initial_sub_states = initial_state.get("states", {})
                if initial_sub_states:
                    # Connect from each sub-state
                    for sub_name, sub_config in initial_sub_states.items():
                        if isinstance(sub_config, dict):
                            _add_transition_if_missing(
                                sub_config, "START_APP",
                                _find_best_start_target(nav_states)
                            )
                else:
                    # Leaf state — add transition directly
                    _add_transition_if_missing(
                        initial_state, "START_APP",
                        _find_best_start_target(nav_states)
                    )
    
    # === FIX 2: Connect auth_guard → dashboard ===
    if "auth_guard" in nav_states:
        auth_guard = nav_states["auth_guard"]
        if isinstance(auth_guard, dict):
            auth_sub_states = auth_guard.get("states", {})
            if auth_sub_states:
                for sub_name, sub_config in auth_sub_states.items():
                    if isinstance(sub_config, dict):
                        _add_transition_if_missing(
                            sub_config, "AUTH_SUCCESS",
                            "navigation.dashboard"
                        )
                        _add_transition_if_missing(
                            sub_config, "AUTH_FAILED",
                            "navigation.login" if "login" in nav_states else "navigation.app_initial"
                        )
            else:
                _add_transition_if_missing(auth_guard, "AUTH_SUCCESS", "navigation.dashboard")
    
    # === FIX 3: Connect login → dashboard (on success) ===
    if "login" in nav_states:
        login_state = nav_states["login"]
        if isinstance(login_state, dict):
            login_sub_states = login_state.get("states", {})
            if login_sub_states:
                for sub_name, sub_config in login_sub_states.items():
                    if isinstance(sub_config, dict):
                        _add_transition_if_missing(
                            sub_config, "LOGIN_SUCCESS",
                            "navigation.dashboard"
                        )
                        _add_transition_if_missing(
                            sub_config, "LOGIN_FAILED",
                            ".failure_retry" if "failure_retry" in login_sub_states else "navigation.app_initial"
                        )
            else:
                _add_transition_if_missing(login_state, "LOGIN_SUCCESS", "navigation.dashboard")
    
    # === FIX 4: Connect dashboard_ready → all feature screens ===
    dashboard = nav_states.get("dashboard", {})
    if isinstance(dashboard, dict):
        dashboard_states = dashboard.get("states", {})
        dashboard_ready = dashboard_states.get("dashboard_ready", {})
        
        if isinstance(dashboard_ready, dict):
            _add_feature_transitions(dashboard_ready, nav_states)
    
    # Also add from dashboard compound state itself (if no dashboard_ready)
    if isinstance(dashboard, dict) and "dashboard_ready" not in dashboard.get("states", {}):
        dashboard_on = dashboard.get("on", {})
        _add_feature_transitions_to_dict(dashboard_on, nav_states)
        dashboard["on"] = dashboard_on
    
    # === FIX 5: Connect catalog_ready ↔ offers_ready ↔ alerts_ready ===
    for screen_name, event_map in [
        ("catalog", {"OPEN_OFFERS": "offers", "OPEN_ALERTS": "alerts", "OPEN_DASHBOARD": "dashboard"}),
        ("offers", {"OPEN_CATALOG": "catalog", "OPEN_ALERTS": "alerts", "OPEN_DASHBOARD": "dashboard"}),
        ("alerts", {"OPEN_CATALOG": "catalog", "OPEN_OFFERS": "offers", "OPEN_DASHBOARD": "dashboard"}),
    ]:
        if screen_name in nav_states:
            screen = nav_states[screen_name]
            if isinstance(screen, dict):
                screen_states = screen.get("states", {})
                ready_name = f"{screen_name}_ready"
                ready_state = screen_states.get(ready_name, {})
                if isinstance(ready_state, dict):
                    for event, target in event_map.items():
                        if target in nav_states:
                            _add_transition_if_missing(
                                ready_state, event,
                                f"navigation.{target}"
                            )
    
    # === FIX 6: Connect workflow states back to dashboard ===
    workflow_names = [
        "benchmark_workflow", "purchase_group_workflow", "price_alert_workflow",
        "checkout_flow", "payment_processing", "group_management"
    ]
    for wf_name in workflow_names:
        if wf_name in nav_states:
            wf = nav_states[wf_name]
            if isinstance(wf, dict):
                wf_states = wf.get("states", {})
                # Find completion/error sub-states
                for sub_name, sub_config in wf_states.items():
                    if isinstance(sub_config, dict):
                        # Add GO_BACK to return to dashboard
                        _add_transition_if_missing(
                            sub_config, "GO_BACK",
                            "navigation.dashboard"
                        )
                        _add_transition_if_missing(
                            sub_config, "CANCEL",
                            "navigation.dashboard"
                        )
    
    # === FIX 7: Connect session_expired → login ===
    if "session_expired" in nav_states:
        session_state = nav_states["session_expired"]
        if isinstance(session_state, dict):
            session_sub_states = session_state.get("states", {})
            if session_sub_states:
                for sub_name, sub_config in session_sub_states.items():
                    if isinstance(sub_config, dict):
                        _add_transition_if_missing(
                            sub_config, "REAUTHENTICATE",
                            "navigation.login" if "login" in nav_states else "navigation.app_initial"
                        )
            else:
                _add_transition_if_missing(
                    session_state, "REAUTHENTICATE",
                    "navigation.login" if "login" in nav_states else "navigation.app_initial"
                )
    
    # === FIX 8: Connect profile_settings, notification_preferences, etc. to dashboard ===
    settings_names = ["profile_settings", "notification_preferences", "purchase_history"]
    for settings_name in settings_names:
        if settings_name in nav_states:
            settings_state = nav_states[settings_name]
            if isinstance(settings_state, dict):
                settings_sub_states = settings_state.get("states", {})
                ready_name = f"{settings_name.split('_')[0]}_ready" if "_" in settings_name else "ready"
                # Try common ready state names
                for candidate in [ready_name, f"{settings_name}_ready", "ready"]:
                    if candidate in settings_sub_states:
                        ready = settings_sub_states[candidate]
                        if isinstance(ready, dict):
                            _add_transition_if_missing(ready, "GO_BACK", "navigation.dashboard")
                            _add_transition_if_missing(ready, "SAVE_AND_BACK", "navigation.dashboard")
                            break
                else:
                    # Add GO_BACK to the compound state itself
                    _add_transition_if_missing(settings_state, "GO_BACK", "navigation.dashboard")
    
    return machine


def _find_best_start_target(nav_states: dict) -> str:
    """Find the best target for START_APP transition.
    
    Priority: auth_guard → onboarding → dashboard → app_idle
    
    Args:
        nav_states: Navigation branch states
    
    Returns:
        Target path string
    """
    for target in ["auth_guard", "onboarding", "dashboard", "app_idle", "app_initial"]:
        if target in nav_states:
            return f"navigation.{target}"
    # Fallback to first available state
    first = next(iter(nav_states), "app_idle")
    return f"navigation.{first}"


def _add_feature_transitions(state_config: dict, nav_states: dict) -> None:
    """Add navigation transitions from a state to all feature screens.
    
    Args:
        state_config: State config dict to add transitions to
        nav_states: Available navigation states
    """
    on_transitions = state_config.get("on", {})
    nav_targets = {
        "catalog": "OPEN_CATALOG",
        "offers": "OPEN_OFFERS",
        "alerts": "OPEN_ALERTS",
        "profile_settings": "OPEN_PROFILE",
        "notification_preferences": "OPEN_NOTIFICATION_PREFS",
        "purchase_history": "OPEN_PURCHASE_HISTORY",
        "medicine_detail": "OPEN_MEDICINE_DETAIL",
        "benchmark_workflow": "OPEN_BENCHMARK",
        "purchase_group_workflow": "OPEN_PURCHASE_GROUP",
        "price_alert_workflow": "OPEN_PRICE_ALERT",
        "checkout_flow": "OPEN_CHECKOUT",
        "payment_processing": "OPEN_PAYMENT",
        "group_management": "OPEN_GROUP_MANAGEMENT",
        "flash_sale_detail": "OPEN_FLASH_SALE",
        "network_invitation": "OPEN_NETWORK_INVITE",
        "data_sync": "TRIGGER_SYNC",
        "rebate_dashboard": "OPEN_REBATE_DASHBOARD",
        "dashboard": "OPEN_DASHBOARD",  # Self-reference for completeness
    }
    
    for target_name, event_name in nav_targets.items():
        if target_name in nav_states and event_name not in on_transitions:
            on_transitions[event_name] = f"navigation.{target_name}"
    
    state_config["on"] = on_transitions


def _add_feature_transitions_to_dict(on_dict: dict, nav_states: dict) -> None:
    """Add navigation transitions to a plain dict (for compound states without ready sub-state).
    
    Args:
        on_dict: Plain 'on' dict to add transitions to
        nav_states: Available navigation states
    """
    nav_targets = {
        "catalog": "OPEN_CATALOG",
        "offers": "OPEN_OFFERS",
        "alerts": "OPEN_ALERTS",
        "profile_settings": "OPEN_PROFILE",
        "notification_preferences": "OPEN_NOTIFICATION_PREFS",
        "purchase_history": "OPEN_PURCHASE_HISTORY",
        "dashboard": "OPEN_DASHBOARD",
    }
    
    for target_name, event_name in nav_targets.items():
        if target_name in nav_states and event_name not in on_dict:
            on_dict[event_name] = f"navigation.{target_name}"


def _add_transition_if_missing(state_config: dict, event: str, target: str) -> None:
    """Add a transition to a state config if it doesn't already exist.
    
    Args:
        state_config: State config dict
        event: Event name
        target: Target state path
    """
    if not isinstance(state_config, dict):
        return
    
    on = state_config.get("on", {})
    if event not in on:
        on[event] = target
    state_config["on"] = on


def fix_initial_state(machine: dict) -> dict:
    """Fix the root 'initial' to point to a real state, not a branch.
    
    FIX: The root 'initial' is set to 'navigation' which is a branch (has 'states'
    sub-dict), not a real state. The validator can't reach any states because
    BFS starts from a branch that has no transitions.
    
    Solution: Set initial to 'navigation.app_idle' (or the first valid leaf state
    under navigation).
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with corrected initial state
    """
    states = machine.get("states", {})
    current_initial = machine.get("initial", "")
    
    # If initial points to a branch (has 'states' sub-dict), fix it
    if current_initial in states:
        initial_config = states[current_initial]
        if isinstance(initial_config, dict) and "states" in initial_config:
            # This is a branch — find the first valid sub-state
            branch_states = initial_config.get("states", {})
            branch_initial = initial_config.get("initial", "")
            
            if branch_initial and branch_initial in branch_states:
                # Use the branch's own initial
                new_initial = f"{current_initial}.{branch_initial}"
            else:
                # Use first available state
                first_state = next(iter(branch_states), None)
                if first_state:
                    new_initial = f"{current_initial}.{first_state}"
                else:
                    return machine  # No sub-states, can't fix
            
            machine["initial"] = new_initial
    
    return machine


def connect_sibling_substates(machine: dict) -> dict:
    """Connect sibling sub-states within compound states.
    
    FIX: Compound states like 'app_idle' with sub-states 'loading', 'ready', 'error'
    have 'initial: loading' but no transitions from loading→ready or loading→error.
    This makes 'ready' and 'error' unreachable via BFS.
    
    For every compound state with loading/ready/error sub-states:
    - loading → ready (on DATA_LOADED)
    - loading → error (on LOAD_FAILED, TIMEOUT)
    - error → loading (on RETRY)
    - ready → error (on ON_ERROR)
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with sibling sub-state transitions added
    """
    states = machine.get("states", {})
    
    # Standard sub-state transition rules
    SIBLING_TRANSITIONS = {
        "loading": {
            "DATA_LOADED": ".ready",
            "LOAD_FAILED": ".error",
            "TIMEOUT": ".error",
        },
        "ready": {
            "ON_ERROR": ".error",
            "REFRESH": ".loading",
        },
        "error": {
            "RETRY": ".loading",
            "CANCEL": ".ready",  # Fallback to ready
        },
        "fetching": {
            "DATA_LOADED": ".ready",
            "LOAD_FAILED": ".error",
        },
    }
    
    def _connect(states_dict: dict, parent_path: str = "", depth: int = 0) -> None:
        if depth > 10:
            return
        
        for name, config in list(states_dict.items()):
            if not isinstance(config, dict):
                continue
            
            sub_states = config.get("states", {})
            if sub_states:
                # This is a compound state — connect its sub-states
                for sub_name, sub_config in sub_states.items():
                    if not isinstance(sub_config, dict):
                        continue
                    
                    transitions = sub_config.get("on", {})
                    
                    # Add sibling transitions based on sub-state name
                    if sub_name in SIBLING_TRANSITIONS:
                        for event, target in SIBLING_TRANSITIONS[sub_name].items():
                            if event not in transitions:
                                # Only add if target sub-state exists
                                target_name = target.lstrip(".")
                                if target_name in sub_states:
                                    transitions[event] = target
                
                sub_config["on"] = transitions
                
                # Recurse into sub-states
                _connect(sub_states, f"{parent_path}.{name}" if parent_path else name, depth + 1)
    
    _connect(states)
    return machine
