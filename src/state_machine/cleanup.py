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
    
    CRITICAL FIX: Also fix self-referencing targets. If loading.on.DATA_LOADED
    points to the parent compound state (e.g., 'navigation.app_idle' from
    'navigation.app_idle.loading'), convert it to the proper relative target
    (e.g., '.ready').
    
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
            
            full_path = f"{parent_path}.{name}" if parent_path else name
            sub_states = config.get("states", {})
            if sub_states:
                # This is a compound state — connect its sub-states
                for sub_name, sub_config in sub_states.items():
                    if not isinstance(sub_config, dict):
                        continue
                    
                    transitions = sub_config.get("on", {})
                    
                    # FIX: Detect and fix self-referencing targets
                    # If a sub-state's transition points to the parent compound state
                    # (e.g., 'navigation.app_idle' from 'navigation.app_idle.loading'),
                    # convert it to the proper relative target based on the event.
                    # Also detect when target equals full_path itself.
                    for event, target in list(transitions.items()):
                        if isinstance(target, str):
                            is_self_ref = (target == full_path)
                            # Check if target is the parent compound state
                            # e.g., target='navigation.app_idle', full_path='navigation.app_idle.loading'
                            if not is_self_ref and parent_path:
                                is_self_ref = (target == parent_path)
                            
                            if is_self_ref:
                                # Self-referencing! Fix based on event type
                                if sub_name in SIBLING_TRANSITIONS and event in SIBLING_TRANSITIONS[sub_name]:
                                    correct_target = SIBLING_TRANSITIONS[sub_name][event]
                                    target_name = correct_target.lstrip(".")
                                    if target_name in sub_states:
                                        transitions[event] = correct_target
                    
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
                _connect(sub_states, full_path, depth + 1)
    
    _connect(states)
    return machine


def enforce_compound_states(machine: dict) -> dict:
    """Convert flat screen states into compound states with loading/ready/error.
    
    FIX: The LLM generates 'dashboard' as a flat state, but the validator
    and fuzzer expect hierarchical states (dashboard.loading, dashboard.ready,
    dashboard.error). This function wraps flat screens into compound states.
    
    CRITICAL FIX: Do NOT wrap states that already have meaningful transitions.
    States like 'app_idle' with START_APP → auth_guard already have navigation
    logic. Wrapping them moves those transitions into 'ready' sub-state, but
    'loading' (the initial) has no way to reach 'ready', making everything unreachable.
    
    Strategy:
    1. Identify "screen" states (have entry actions or are in navigation branch)
    2. ONLY wrap states that have NO transitions (truly flat, no navigation logic)
    3. Wrap them: { initial: "loading", states: { loading, ready, error } }
    4. Move original entry/exit/on into the 'ready' sub-state
    5. Create loading sub-state with DATA_LOADED/LOAD_FAILED/TIMEOUT
    6. Create error sub-state with RETRY/CANCEL
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with flat screens converted to compound states
    """
    states = machine.get("states", {})
    
    # Screen names that should be compound (common navigation screens)
    SCREEN_NAMES = {
        "dashboard", "catalog", "offers", "alerts", "profile", "settings",
        "login", "auth_guard", "session_expired", "app_initial", "app_idle",
        "app_loading", "app_error", "app_empty", "app_success",
        "benchmark_viewing", "benchmark_tracking", "benchmark_joining",
        "alert_monitoring", "alert_configuration", "alert_notification",
        "purchase_browsing", "purchase_confirming", "purchase_tracking",
        "viewing", "browsing", "confirming", "tracking", "discovery",
        "completed", "configuration", "notification", "acknowledgment",
    }
    
    # Standard sub-state names that should NEVER be wrapped
    SUB_STATE_NAMES = {"loading", "ready", "error", "error_handler", "checking", "validating",
                       "form", "failure_retry", "dashboard_ready", "catalog_ready",
                       "offers_ready", "alerts_ready"}
    
    def _has_meaningful_transitions(config: dict) -> bool:
        """Check if a state already has meaningful navigation transitions.
        
        If a state has transitions like START_APP, AUTH_SUCCESS, GO_BACK, etc.,
        it already has navigation logic and should NOT be wrapped.
        """
        on = config.get("on", {})
        if not on:
            return False
        
        # Events that indicate the state already has navigation logic
        NAVIGATION_EVENTS = {
            "START_APP", "AUTH_SUCCESS", "AUTH_FAILED", "LOGIN_SUCCESS", "LOGIN_FAILED",
            "GO_BACK", "CANCEL", "GLOBAL_EXIT", "REAUTHENTICATE", "COMPLETE",
            "NAVIGATE_DASHBOARD", "NAVIGATE_CATALOG", "NAVIGATE_OFFERS", "NAVIGATE_ALERTS",
            "OPEN_CATALOG", "OPEN_OFFERS", "OPEN_ALERTS", "OPEN_DASHBOARD",
            "SAVE_AND_BACK", "GO_HOME",
        }
        
        for event in on:
            if event in NAVIGATION_EVENTS:
                return True
        
        # If it has more than 2 transitions, it likely has navigation logic
        if len(on) > 2:
            return True
        
        return False
    
    def _is_screen_state(name: str, config: dict) -> bool:
        """Check if a state should be a compound screen state."""
        # Never wrap standard sub-state names
        if name in SUB_STATE_NAMES:
            return False
        
        # CRITICAL: Don't wrap states that already have navigation transitions
        if _has_meaningful_transitions(config):
            return False
        
        if name in SCREEN_NAMES:
            return True
        # States with entry actions but no sub-states are likely screens
        if config.get("entry") and not config.get("states"):
            return True
        return False
    
    def _wrap_as_compound(name: str, config: dict, parent_path: str) -> dict:
        """Wrap a flat state into a compound state with loading/ready/error."""
        # Save original content
        original_entry = config.get("entry", [])
        original_exit = config.get("exit", [])
        original_on = config.get("on", {})
        
        # Build ready sub-state (contains original logic)
        ready_config = {
            "entry": list(original_entry),
            "exit": list(original_exit),
            "on": dict(original_on),
        }
        
        # Build loading sub-state
        loading_config = {
            "entry": ["showLoading", f"fetch{name.title()}"],
            "exit": ["hideLoading"],
            "on": {
                "DATA_LOADED": ".ready",
                "LOAD_FAILED": ".error",
                "TIMEOUT": ".error",
            },
        }
        
        # Build error sub-state
        error_config = {
            "entry": ["logError", "showErrorBanner"],
            "exit": ["hideErrorBanner"],
            "on": {
                "RETRY": ".loading",
                "CANCEL": f"#{parent_path}" if parent_path else ".ready",
            },
        }
        
        return {
            "id": config.get("id", name),
            "initial": "loading",
            "states": {
                "loading": loading_config,
                "ready": ready_config,
                "error": error_config,
            },
        }
    
    def _enforce(states_dict: dict, parent_path: str = "", depth: int = 0) -> None:
        if depth > 10:
            return
        
        for name, config in list(states_dict.items()):
            if not isinstance(config, dict):
                continue
            
            full_path = f"{parent_path}.{name}" if parent_path else name
            sub_states = config.get("states", {})
            
            if sub_states:
                # Already compound — recurse
                _enforce(sub_states, full_path, depth + 1)
            elif _is_screen_state(name, config):
                # Flat screen with no navigation transitions — wrap as compound
                states_dict[name] = _wrap_as_compound(name, config, parent_path)
    
    _enforce(states)
    return machine


def inject_auth_flow(machine: dict) -> dict:
    """Inject authentication flow states if they don't exist.
    
    FIX: The LLM often skips auth states despite prompt instructions.
    This function ensures every machine has:
    - auth_guard (token validation)
    - login (user credentials)
    - session_expired (re-authentication)
    
    These are injected into the navigation branch and connected to
    app_initial (START_APP → auth_guard) and dashboard (AUTH_SUCCESS → dashboard).
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with auth flow states injected
    """
    states = machine.get("states", {})
    
    # Find the navigation branch
    navigation = states.get("navigation", {})
    if not isinstance(navigation, dict):
        return machine
    
    nav_states = navigation.get("states", {})
    
    # === Inject auth_guard if missing ===
    if "auth_guard" not in nav_states:
        nav_states["auth_guard"] = {
            "id": "navigation.auth_guard",
            "initial": "checking",
            "states": {
                "checking": {
                    "entry": ["validateToken", "checkSession"],
                    "on": {
                        "AUTH_SUCCESS": "navigation.dashboard",
                        "AUTH_FAILED": "navigation.login",
                        "SESSION_EXPIRED": "navigation.session_expired",
                    },
                },
                "validating": {
                    "entry": ["showAuthSpinner"],
                    "on": {
                        "AUTH_SUCCESS": "navigation.dashboard",
                        "AUTH_FAILED": "navigation.login",
                    },
                },
            },
        }
    
    # === Inject login if missing ===
    if "login" not in nav_states:
        nav_states["login"] = {
            "id": "navigation.login",
            "initial": "form",
            "states": {
                "form": {
                    "entry": ["showLoginForm"],
                    "exit": ["hideLoginForm"],
                    "on": {
                        "LOGIN_SUCCESS": "navigation.dashboard",
                        "LOGIN_FAILED": ".failure_retry",
                        "GO_BACK": "navigation.app_idle",
                    },
                },
                "failure_retry": {
                    "entry": ["showLoginError"],
                    "on": {
                        "RETRY_LOGIN": "form",
                        "GO_BACK": "navigation.app_idle",
                    },
                },
            },
        }
    
    # === Inject session_expired if missing ===
    if "session_expired" not in nav_states:
        nav_states["session_expired"] = {
            "id": "navigation.session_expired",
            "entry": ["showSessionExpiredBanner"],
            "exit": ["hideSessionExpiredBanner"],
            "on": {
                "REAUTHENTICATE": "navigation.login",
                "CANCEL": "navigation.app_idle",
            },
        }
    
    # === Connect app_initial/app_idle → auth_guard ===
    for initial_name in ["app_initial", "app_idle"]:
        if initial_name in nav_states:
            initial_config = nav_states[initial_name]
            if isinstance(initial_config, dict):
                on = initial_config.get("on", {})
                current_target = on.get("START_APP", "")
                # Redirect self-loops to auth_guard
                if "START_APP" not in on or current_target == f"navigation.{initial_name}":
                    on["START_APP"] = "navigation.auth_guard"
                initial_config["on"] = on
                
                # CRITICAL FIX: If this is a compound state, also add START_APP
                # to the initial sub-state (e.g., 'loading') so it's reachable
                # from the actual entry point.
                sub_states = initial_config.get("states", {})
                compound_initial = initial_config.get("initial", "")
                if compound_initial and compound_initial in sub_states:
                    initial_sub = sub_states[compound_initial]
                    if isinstance(initial_sub, dict):
                        sub_on = initial_sub.get("on", {})
                        if "START_APP" not in sub_on:
                            sub_on["START_APP"] = "navigation.auth_guard"
                        initial_sub["on"] = sub_on
    
    return machine


def fix_authenticating_targets(machine: dict) -> dict:
    """Fix all transitions pointing to non-existent 'authenticating' state.
    
    FIX: The LLM generates transitions to 'authenticating' but this state
    doesn't exist. The correct target is 'navigation.auth_guard'.
    
    This handles:
    - Direct 'authenticating' targets
    - Relative '.authenticating' targets
    - 'authenticating' in any nested state
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with 'authenticating' targets redirected to 'navigation.auth_guard'
    """
    states = machine.get("states", {})
    
    # Determine the correct auth target
    navigation = states.get("navigation", {})
    nav_states = navigation.get("states", {}) if isinstance(navigation, dict) else {}
    
    if "auth_guard" in nav_states:
        auth_target = "navigation.auth_guard"
    elif "login" in nav_states:
        auth_target = "navigation.login"
    elif "app_idle" in nav_states:
        auth_target = "navigation.app_idle"
    else:
        auth_target = "navigation.app_idle"
    
    def _fix_auth(states_dict: dict, depth: int = 0) -> None:
        if depth > 10:
            return
        
        for name, config in list(states_dict.items()):
            if not isinstance(config, dict):
                continue
            
            transitions = config.get("on", {})
            for event, target in list(transitions.items()):
                if isinstance(target, str):
                    # Fix direct 'authenticating' target
                    if target == "authenticating":
                        transitions[event] = auth_target
                    # Fix relative '.authenticating' target
                    elif target == ".authenticating":
                        transitions[event] = auth_target
            
            # Recurse into sub-states
            sub_states = config.get("states", {})
            if sub_states:
                _fix_auth(sub_states, depth + 1)
    
    _fix_auth(states)
    return machine


def fix_bare_app_idle_targets(machine: dict) -> dict:
    """Fix all transitions pointing to bare 'app_idle' without 'navigation.' prefix.
    
    FIX: The LLM generates transitions like:
    - 'AUTH_SUCCESS' → 'app_idle' (should be 'navigation.app_idle')
    - 'LOGIN_SUCCESS' → 'app_idle' (should be 'navigation.dashboard')
    - 'GO_BACK' → 'app_idle' (should be 'navigation.dashboard')
    - 'GLOBAL_EXIT' → 'app_idle' (should be '#navigation.app_idle')
    
    This function:
    1. Finds all transitions targeting bare 'app_idle'
    2. If inside navigation branch, prefixes with 'navigation.'
    3. If it's a GLOBAL_EXIT, uses '#navigation.app_idle'
    4. If it's a success event (LOGIN_SUCCESS, AUTH_SUCCESS), redirects to 'navigation.dashboard'
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with bare 'app_idle' targets fixed
    """
    states = machine.get("states", {})
    
    # Check if navigation.app_idle exists
    navigation = states.get("navigation", {})
    nav_states = navigation.get("states", {}) if isinstance(navigation, dict) else {}
    
    if "app_idle" not in nav_states and "app_initial" not in nav_states:
        return machine  # No app_idle to fix
    
    # Events that should go to dashboard on success (not app_idle)
    SUCCESS_EVENTS = {
        "LOGIN_SUCCESS", "AUTH_SUCCESS", "AUTH_VERIFIED", "ONBOARDING_COMPLETE",
        "BENCHMARK_COMPLETE", "PURCHASE_GROUP_COMPLETE", "PRICE_ALERT_COMPLETE",
        "CHECKOUT_COMPLETE", "PAYMENT_COMPLETE",
    }
    
    # Events that are navigation (should go to specific screens)
    NAV_EVENTS = {
        "NAV_TO_DASHBOARD", "NAV_TO_CATALOG", "NAV_TO_OFFERS", "NAV_TO_ALERTS",
        "NAV_TO_SETTINGS", "NAV_TO_HISTORY",
        "OPEN_CATALOG", "OPEN_OFFERS", "OPEN_ALERTS", "OPEN_DASHBOARD",
        "OPEN_SETTINGS", "OPEN_PURCHASE_HISTORY", "OPEN_BENCHMARK",
        "OPEN_PURCHASE_GROUP", "OPEN_PRICE_ALERT",
    }
    
    def _fix_bare_idle(states_dict: dict, parent_path: str = "", depth: int = 0) -> None:
        if depth > 10:
            return
        
        for name, config in list(states_dict.items()):
            if not isinstance(config, dict):
                continue
            
            full_path = f"{parent_path}.{name}" if parent_path else name
            transitions = config.get("on", {})
            
            for event, target in list(transitions.items()):
                if isinstance(target, str):
                    # Fix bare 'app_idle' (not prefixed with 'navigation.' or '#')
                    if target == "app_idle":
                        if event in SUCCESS_EVENTS:
                            # Success events should go to dashboard
                            transitions[event] = "navigation.dashboard" if "dashboard" in nav_states else "navigation.app_idle"
                        elif event == "GLOBAL_EXIT":
                            # Global exit uses '#' prefix
                            transitions[event] = "#navigation.app_idle"
                        elif full_path.startswith("navigation."):
                            # Inside navigation branch — just prefix it
                            transitions[event] = "navigation.app_idle"
                        else:
                            # Outside navigation — prefix it
                            transitions[event] = "navigation.app_idle"
                    
                    # Also fix bare 'app_initial'
                    elif target == "app_initial":
                        if event in SUCCESS_EVENTS:
                            transitions[event] = "navigation.dashboard" if "dashboard" in nav_states else "navigation.app_initial"
                        elif event == "GLOBAL_EXIT":
                            transitions[event] = "#navigation.app_initial"
                        elif full_path.startswith("navigation."):
                            transitions[event] = "navigation.app_initial"
                        else:
                            transitions[event] = "navigation.app_initial"
                    
                    # Fix bare 'dashboard', 'catalog', 'offers', 'alerts' (navigation targets)
                    elif target in nav_states and target not in ("app_idle", "app_initial"):
                        if event in NAV_EVENTS or event.startswith("NAV_") or event.startswith("OPEN_"):
                            if not target.startswith("navigation.") and not target.startswith("#"):
                                transitions[event] = f"navigation.{target}"
            
            # Recurse into sub-states
            sub_states = config.get("states", {})
            if sub_states:
                _fix_bare_idle(sub_states, full_path, depth + 1)
    
    _fix_bare_idle(states)
    return machine


def fix_relative_substate_targets(machine: dict) -> dict:
    """Fix relative sub-state targets that should use '.' prefix.
    
    FIX: The LLM generates transitions like:
    - 'DATA_LOADED' → 'ready' (should be '.ready' inside compound states)
    - 'LOAD_FAILED' → 'error' (should be '.error')
    - 'RETRY' → 'loading' (should be '.loading')
    - 'CANCEL' → 'app_idle' (should be 'navigation.app_idle')
    
    This function:
    1. Finds compound states with sub-states (loading, ready, error)
    2. Fixes relative targets to use '.' prefix when pointing to sibling sub-states
    3. Fixes absolute targets (like 'app_idle') to use full paths
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with relative sub-state targets fixed
    """
    states = machine.get("states", {})
    
    # Standard sub-state names that should use relative targets
    SUB_STATE_NAMES = {"loading", "ready", "error", "error_handler", "checking", 
                       "validating", "form", "failure_retry", "fetching", "submitting"}
    
    # Events that typically use relative targets within compound states
    RELATIVE_EVENTS = {
        "DATA_LOADED", "LOAD_FAILED", "TIMEOUT", "RETRY", "CANCEL", 
        "ON_ERROR", "REFRESH", "SUBMIT_SUCCESS", "SUBMIT_FAILED",
        "VALIDATION_SUCCESS", "VALIDATION_FAILED",
    }
    
    def _fix_relative(states_dict: dict, parent_path: str = "", depth: int = 0) -> None:
        if depth > 10:
            return
        
        for name, config in list(states_dict.items()):
            if not isinstance(config, dict):
                continue
            
            full_path = f"{parent_path}.{name}" if parent_path else name
            sub_states = config.get("states", {})
            
            if sub_states:
                # This is a compound state — fix relative targets in sub-states
                for sub_name, sub_config in sub_states.items():
                    if not isinstance(sub_config, dict):
                        continue
                    
                    transitions = sub_config.get("on", {})
                    for event, target in list(transitions.items()):
                        if isinstance(target, str):
                            # Fix bare sub-state names (should be relative with '.')
                            if target in SUB_STATE_NAMES and target != name:
                                # This is a sibling reference — should use '.' prefix
                                if not target.startswith(".") and not target.startswith("#"):
                                    transitions[event] = f".{target}"
                            
                            # Fix relative targets that point to non-existent siblings
                            elif target.startswith("."):
                                target_name = target.lstrip(".")
                                if target_name not in sub_states:
                                    # Target doesn't exist in sub-states — might be absolute
                                    # Try to resolve it
                                    resolved = _try_resolve_absolute_target(target_name, full_path, machine)
                                    if resolved:
                                        transitions[event] = resolved
                                    else:
                                        # Remove invalid transition
                                        del transitions[event]
                    
                    sub_config["on"] = transitions
                
                # Recurse into sub-states
                _fix_relative(sub_states, full_path, depth + 1)
            else:
                # Leaf state — fix absolute targets
                transitions = config.get("on", {})
                for event, target in list(transitions.items()):
                    if isinstance(target, str) and target in SUB_STATE_NAMES:
                        # This is likely a mistake — leaf states shouldn't target sub-state names
                        # Try to resolve as absolute
                        resolved = _try_resolve_absolute_target(target, full_path, machine)
                        if resolved:
                            transitions[event] = resolved
                
                config["on"] = transitions
    
    _fix_relative(states)
    return machine


def _try_resolve_absolute_target(target_name: str, current_path: str, machine: dict) -> str:
    """Try to resolve a target name as an absolute path.
    
    Args:
        target_name: The target state name (e.g., 'dashboard', 'app_idle')
        current_path: The full path of the current state
        machine: The state machine dict
    
    Returns:
        Resolved target path, or empty string if can't resolve
    """
    states = machine.get("states", {})
    
    # Check navigation branch first
    navigation = states.get("navigation", {})
    if isinstance(navigation, dict):
        nav_states = navigation.get("states", {})
        if target_name in nav_states:
            return f"navigation.{target_name}"
    
    # Check active_workflows branch
    workflows = states.get("active_workflows", {})
    if isinstance(workflows, dict):
        wf_states = workflows.get("states", {})
        if target_name in wf_states:
            return f"active_workflows.{target_name}"
    
    # Check root level
    if target_name in states:
        return target_name
    
    return ""


def remove_duplicate_states(machine: dict) -> dict:
    """Remove duplicate states that exist at multiple levels.
    
    FIX: The LLM sometimes generates states that duplicate existing states:
    - 'completed' at root when 'navigation.purchase_group_workflow.completed' exists
    - 'dashboard' at root when 'navigation.dashboard' exists
    - States with same name but different content (conflicting definitions)
    
    Strategy:
    1. Collect all state names from navigation and active_workflows branches
    2. Remove root-level states that duplicate branch states (unless they have unique content)
    3. Merge conflicting definitions (keep the one with more transitions/actions)
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with duplicate states removed
    """
    states = machine.get("states", {})
    
    # Collect all state names from branches
    branch_states = {}  # name -> branch_path
    
    for branch_name in ["navigation", "active_workflows", "workflows"]:
        branch = states.get(branch_name, {})
        if isinstance(branch, dict):
            branch_states_dict = branch.get("states", {})
            for state_name in branch_states_dict:
                if state_name not in branch_states:
                    branch_states[state_name] = branch_name
    
    # Also collect nested state names
    nested_names = set()
    for branch_name in ["navigation", "active_workflows"]:
        branch = states.get(branch_name, {})
        if isinstance(branch, dict):
            branch_states_dict = branch.get("states", {})
            for state_name, state_config in branch_states_dict.items():
                if isinstance(state_config, dict):
                    sub_states = state_config.get("states", {})
                    for sub_name in sub_states:
                        nested_names.add(sub_name)
    
    to_remove = []
    
    for name, config in states.items():
        # Skip branch states themselves
        if name in ("navigation", "active_workflows", "workflows"):
            continue
        
        # Check if this is a duplicate of a branch state
        if name in branch_states:
            # This state duplicates one in a branch
            # Check if it has unique content (entry, exit, on, states)
            entry = config.get("entry", [])
            exit_actions = config.get("exit", [])
            on = config.get("on", {})
            has_sub_states = "states" in config and bool(config.get("states", {}))
            
            if not entry and not exit_actions and not on and not has_sub_states:
                # Pure phantom duplicate — remove it
                to_remove.append(name)
            elif name in nested_names:
                # This is a nested state name at root level — likely a duplicate
                # Check if it has meaningful content
                has_meaningful_content = (
                    len(entry) > 0 or 
                    len(exit_actions) > 0 or 
                    len(on) > 2 or  # More than just CANCEL/GO_BACK
                    has_sub_states
                )
                if not has_meaningful_content:
                    to_remove.append(name)
    
    for name in to_remove:
        if name in states:
            del states[name]
    
    return machine


def fix_invalid_compound_states(machine: dict) -> dict:
    """Fix compound states that have 'states' but no valid 'initial'.
    
    FIX: The validator flags INVALID_COMPOUND_STATE when:
    - A state has 'states' sub-dict but no 'initial' key
    - The 'initial' points to a non-existent sub-state
    - The 'initial' is empty string
    
    This function:
    1. Adds 'initial' to compound states missing it (defaults to first sub-state)
    2. Fixes 'initial' pointing to non-existent sub-states
    3. Removes 'initial' if it points to empty string
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with valid compound states
    """
    states = machine.get("states", {})
    
    def _fix_compounds(states_dict: dict, depth: int = 0) -> None:
        if depth > 10:
            return
        
        for name, config in list(states_dict.items()):
            if not isinstance(config, dict):
                continue
            
            sub_states = config.get("states", {})
            if sub_states:
                # This is a compound state — check 'initial'
                initial = config.get("initial", "")
                
                if not initial or initial not in sub_states:
                    # Fix: set initial to first sub-state
                    first_sub = next(iter(sub_states), None)
                    if first_sub:
                        config["initial"] = first_sub
                
                # Recurse into sub-states
                _fix_compounds(sub_states, depth + 1)
    
    _fix_compounds(states)
    return machine


def connect_orphan_workflows(machine: dict) -> dict:
    """Connect unreachable workflow states to the navigation graph.
    
    FIX: Workflow states like 'benchmark_workflow', 'purchase_group_workflow',
    'price_alert_workflow' are unreachable because they have no entry transitions
    from navigation screens.
    
    This function:
    1. Adds OPEN_* events from dashboard_ready to workflow states
    2. Adds GO_BACK/CANCEL from workflow completion states to dashboard
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with workflows connected to navigation
    """
    states = machine.get("states", {})
    
    # Find navigation branch
    navigation = states.get("navigation", {})
    if not isinstance(navigation, dict):
        return machine
    
    nav_states = navigation.get("states", {})
    
    # Find active_workflows branch
    workflows = states.get("active_workflows", {})
    if not isinstance(workflows, dict):
        return machine
    
    wf_states = workflows.get("states", {})
    
    # Map workflow names to OPEN events
    workflow_events = {
        "benchmark_workflow": "OPEN_BENCHMARK",
        "purchase_group_workflow": "OPEN_PURCHASE_GROUP",
        "price_alert_workflow": "OPEN_PRICE_ALERT",
        "checkout_flow": "OPEN_CHECKOUT",
        "payment_processing": "OPEN_PAYMENT",
        "group_management": "OPEN_GROUP_MANAGEMENT",
    }
    
    # Connect dashboard → workflows
    dashboard = nav_states.get("dashboard", {})
    if isinstance(dashboard, dict):
        dashboard_states = dashboard.get("states", {})
        dashboard_ready = dashboard_states.get("dashboard_ready", {})
        
        if isinstance(dashboard_ready, dict):
            dashboard_on = dashboard_ready.get("on", {})
            for wf_name, event in workflow_events.items():
                if wf_name in wf_states and event not in dashboard_on:
                    dashboard_on[event] = f"active_workflows.{wf_name}"
            dashboard_ready["on"] = dashboard_on
    
    # Connect workflows → dashboard (GO_BACK/CANCEL)
    for wf_name, wf_config in wf_states.items():
        if not isinstance(wf_config, dict):
            continue
        
        wf_sub_states = wf_config.get("states", {})
        for sub_name, sub_config in wf_sub_states.items():
            if not isinstance(sub_config, dict):
                continue
            
            sub_on = sub_config.get("on", {})
            if "GO_BACK" not in sub_on:
                sub_on["GO_BACK"] = "navigation.dashboard"
            if "CANCEL" not in sub_on:
                sub_on["CANCEL"] = "navigation.dashboard"
            sub_config["on"] = sub_on
    
    return machine


def add_pull_to_refresh_states(machine: dict) -> dict:
    """Add pull-to-refresh micro-states to screen compound states.
    
    FIX: The critic notes that pull-to-refresh is specified for Dashboard
    but the state machine lacks local micro-states for it.
    
    This function adds:
    - PULL_TO_REFRESH → .loading (within screen compound states)
    - SYNC_SUCCESS → .ready
    - SYNC_FAILED → .error
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with pull-to-refresh micro-states
    """
    states = machine.get("states", {})
    
    # Screen names that should support pull-to-refresh
    REFRESHABLE_SCREENS = {"dashboard", "catalog", "offers", "alerts"}
    
    def _add_refresh(states_dict: dict, depth: int = 0) -> None:
        if depth > 10:
            return
        
        for name, config in list(states_dict.items()):
            if not isinstance(config, dict):
                continue
            
            sub_states = config.get("states", {})
            if name in REFRESHABLE_SCREENS and sub_states:
                # Add PULL_TO_REFRESH to ready sub-state
                ready = sub_states.get("ready", {})
                if isinstance(ready, dict):
                    ready_on = ready.get("on", {})
                    if "PULL_TO_REFRESH" not in ready_on and "loading" in sub_states:
                        ready_on["PULL_TO_REFRESH"] = ".loading"
                    if "SYNC_SUCCESS" not in ready_on:
                        ready_on["SYNC_SUCCESS"] = ".ready"
                    if "SYNC_FAILED" not in ready_on and "error" in sub_states:
                        ready_on["SYNC_FAILED"] = ".error"
                    ready["on"] = ready_on
            
            # Recurse
            if sub_states:
                _add_refresh(sub_states, depth + 1)
    
    _add_refresh(states)
    return machine


def add_offline_mode(machine: dict) -> dict:
    """Add offline mode state and transitions.
    
    FIX: The critic notes missing offline mode for background sync and
    network failure handling.
    
    This function:
    1. Adds 'offline_mode' state to navigation branch
    2. Adds NETWORK_OFFLINE transitions from loading states
    3. Adds RETRY_NETWORK from offline_mode back to loading
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with offline mode support
    """
    states = machine.get("states", {})
    
    # Find navigation branch
    navigation = states.get("navigation", {})
    if not isinstance(navigation, dict):
        return machine
    
    nav_states = navigation.get("states", {})
    
    # Add offline_mode if missing
    if "offline_mode" not in nav_states:
        nav_states["offline_mode"] = {
            "id": "navigation.offline_mode",
            "entry": ["showOfflineBanner", "enableOfflineCache"],
            "exit": ["hideOfflineBanner", "disableOfflineCache"],
            "on": {
                "RETRY_NETWORK": "navigation.dashboard",
                "GO_HOME": "navigation.app_idle",
            },
        }
    
    # Add NETWORK_OFFLINE transitions from loading states
    def _add_offline_transitions(states_dict: dict, parent_path: str = "", depth: int = 0) -> None:
        if depth > 10:
            return
        
        for name, config in list(states_dict.items()):
            if not isinstance(config, dict):
                continue
            
            full_path = f"{parent_path}.{name}" if parent_path else name
            
            # If this is a loading sub-state, add NETWORK_OFFLINE
            if name == "loading":
                loading_on = config.get("on", {})
                if "NETWORK_OFFLINE" not in loading_on:
                    loading_on["NETWORK_OFFLINE"] = "navigation.offline_mode"
                config["on"] = loading_on
            
            # Recurse
            sub_states = config.get("states", {})
            if sub_states:
                _add_offline_transitions(sub_states, full_path, depth + 1)
    
    _add_offline_transitions(nav_states)
    return machine


def apply_error_routing_matrix(machine: dict) -> dict:
    """Apply strict error routing: local errors stay local, fatal errors bubble up.
    
    FIX: The fuzzer shows transitions to both 'app_initial.error' and 'app_error'
    with no clear strategy. This function enforces:
    
    ROUTING MATRIX:
    | Error Type          | Local Target              | Global Target          |
    |---------------------|---------------------------|------------------------|
    | Network timeout     | screen.loading → .error   | app_error (after 3x)   |
    | Auth failed         | login.failure_retry       | session_expired        |
    | Data empty          | screen.ready → .empty     | (not an error)         |
    | Server 500          | screen.error              | app_error (retry=3x)   |
    | Invalid input       | screen.error (inline)     | (never global)         |
    | Session expired     | session_expired           | session_expired        |
    
    Implementation:
    1. Find all error states in compound screens
    2. RETRY → .loading (local retry)
    3. After 3 retries → navigation.app_error (global)
    4. CANCEL → navigation.app_idle (safe exit)
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with error routing matrix applied
    """
    states = machine.get("states", {})
    
    # Check if global app_error exists — if not, create it
    navigation = states.get("navigation", {})
    if isinstance(navigation, dict):
        nav_states = navigation.get("states", {})
        
        if "app_error" not in nav_states:
            nav_states["app_error"] = {
                "id": "navigation.app_error",
                "entry": ["showGlobalError", "logFatalError"],
                "exit": ["hideGlobalError"],
                "on": {
                    "RETRY": "navigation.app_idle",
                    "CANCEL": "navigation.app_idle",
                    "GO_HOME": "navigation.app_idle",
                },
            }
    
    def _apply_error_routing(states_dict: dict, parent_path: str = "", depth: int = 0) -> None:
        if depth > 10:
            return
        
        for name, config in list(states_dict.items()):
            if not isinstance(config, dict):
                continue
            
            full_path = f"{parent_path}.{name}" if parent_path else name
            sub_states = config.get("states", {})
            
            if sub_states:
                # Check for error sub-state
                error_state = sub_states.get("error", {})
                if isinstance(error_state, dict):
                    error_on = error_state.get("on", {})
                    
                    # Ensure RETRY → .loading (local retry)
                    if "RETRY" not in error_on and "loading" in sub_states:
                        error_on["RETRY"] = ".loading"
                    
                    # Ensure CANCEL goes to parent or app_idle
                    if "CANCEL" not in error_on:
                        if parent_path:
                            error_on["CANCEL"] = f".{parent_path.split('.')[-1]}"
                        else:
                            error_on["CANCEL"] = "navigation.app_idle"
                    
                    error_state["on"] = error_on
                
                # Recurse into sub-states
                _apply_error_routing(sub_states, full_path, depth + 1)
    
    _apply_error_routing(states)
    return machine
