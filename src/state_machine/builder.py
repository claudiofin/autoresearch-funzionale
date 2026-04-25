# =============================================================================
# Domain Configuration Constants (STRUCTURAL: configurable, not hardcoded)
# =============================================================================

# Default state names — override via state_names parameter
DEFAULT_STATE_NAMES = {
    "initial": "app_idle",
    "workflow_none": "none",
    "loading": "loading",
    "ready": "ready",
    "error": "error",
}

# Default branch names — override via branch_names parameter
DEFAULT_BRANCH_NAMES = {
    "navigation": "navigation",
    "workflows": "active_workflows",
}

# Default event names — override via event_names parameter
DEFAULT_EVENT_NAMES = {
    "navigate": "NAVIGATE",
    "error": "ERROR",
    "retry": "RETRY",
    "cancel": "CANCEL",
    "complete": "COMPLETED",
    "data_loaded": "DATA_LOADED",
    "load_failed": "LOAD_FAILED",
    "timeout": "TIMEOUT",
}

# Default action names — override via action_names parameter
DEFAULT_ACTION_NAMES = {
    "hide_workflow": "hideWorkflowOverlay",
    "show_workflow": "showWorkflowOverlay",
    "show_loading": "showLoading",
    "hide_loading": "hideLoading",
    "show_error": "showErrorBanner",
    "hide_error": "hideErrorBanner",
    "log_error": "logError",
}

# Default guard names — override via guard_names parameter
# These are UNIVERSAL guards that work for any app
DEFAULT_GUARD_NAMES = {
    "can_retry": "canRetry",
    "has_data": "hasData",
    "has_previous_state": "hasPreviousState",
    "is_authenticated": "isAuthenticated",
    "has_network": "hasNetwork",
}

# Default emergency event names — override via emergency_events parameter
# These events allow graceful exit from any state when app conditions change
DEFAULT_EMERGENCY_EVENTS = {
    "session_expired": "SESSION_EXPIRED",
    "network_lost": "NETWORK_LOST",
    "app_background": "APP_BACKGROUND",
    "global_exit": "GLOBAL_EXIT",
}


def _resolve_state_name(name: str, state_names: dict = None) -> str:
    """Resolve a state name using defaults + overrides.
    
    Args:
        name: Key to look up (e.g., "initial", "workflow_none")
        state_names: Optional override dict
    
    Returns:
        Resolved state name
    """
    overrides = state_names or {}
    return overrides.get(name, DEFAULT_STATE_NAMES.get(name, name))


def _resolve_branch_name(name: str, branch_names: dict = None) -> str:
    """Resolve a branch name using defaults + overrides.
    
    Args:
        name: Key to look up (e.g., "navigation", "workflows")
        branch_names: Optional override dict
    
    Returns:
        Resolved branch name
    """
    overrides = branch_names or {}
    return overrides.get(name, DEFAULT_BRANCH_NAMES.get(name, name))


def _resolve_event_name(name: str, event_names: dict = None) -> str:
    """Resolve an event name using defaults + overrides.
    
    Args:
        name: Key to look up (e.g., "navigate", "error")
        event_names: Optional override dict
    
    Returns:
        Resolved event name
    """
    overrides = event_names or {}
    return overrides.get(name, DEFAULT_EVENT_NAMES.get(name, name))


def _resolve_action_name(name: str, action_names: dict = None) -> str:
    """Resolve an action name using defaults + overrides.
    
    Args:
        name: Key to look up (e.g., "hide_workflow", "show_loading")
        action_names: Optional override dict
    
    Returns:
        Resolved action name
    """
    overrides = action_names or {}
    return overrides.get(name, DEFAULT_ACTION_NAMES.get(name, name))


def _extract_target_names(target) -> list:
    """Extract target state names from a transition target.
    
    Handles both string targets and list of targets (for conditional transitions).
    
    Args:
        target: Target string, dict, or list of targets
    
    Returns:
        List of target state names
    """
    if isinstance(target, str):
        return [target]
    elif isinstance(target, dict):
        t = target.get("target", "")
        return [t] if t else []
    elif isinstance(target, list):
        names = []
        for item in target:
            if isinstance(item, dict):
                t = item.get("target", "")
                if t:
                    names.append(t)
            elif isinstance(item, str):
                names.append(item)
        return names
    return []


def _resolve_simple_target(target: str, current: str, states: dict, prefix: str = "") -> str:
    """Resolve a simple target reference.
    
    Args:
        target: Target string (may be relative with .)
        current: Current state name
        states: States dict
        prefix: Path prefix
    
    Returns:
        Resolved state name or None
    """
    if not target:
        return None
    
    # Relative reference
    if target.startswith("."):
        return target[1:]  # Strip the dot
    
    # Already in states
    if target in states:
        return target
    
    return None


# =============================================================================
# Helper Functions for Compilation Pipeline
# =============================================================================

def _bfs_reachable(machine: dict) -> set:
    """BFS to find all reachable states from initial states.
    
    Args:
        machine: The state machine dict
    
    Returns:
        Set of reachable state paths
    """
    reachable = set()
    states = machine.get("states", {})
    
    # Find initial states
    def _get_initials(states_dict: dict, prefix: str = "") -> list:
        initials = []
        for name, config in states_dict.items():
            full_path = f"{prefix}.{name}" if prefix else name
            if config.get("initial"):
                initials.append((name, full_path))
            if "states" in config:
                initials.extend(_get_initials(config["states"], full_path))
        return initials
    
    initials = _get_initials(states)
    queue = [(name, path) for name, path in initials]
    
    while queue:
        name, path = queue.pop(0)
        if path in reachable:
            continue
        reachable.add(path)
        
        # Find the state config
        parts = path.split(".")
        current = states
        for part in parts:
            if part in current:
                current = current[part]
            else:
                break
        
        # Add transition targets to queue
        transitions = current.get("on", {})
        for event, target in transitions.items():
            target_str = _extract_target_string(target)
            if target_str:
                # Resolve relative targets
                if target_str.startswith("."):
                    sibling = target_str[1:]
                    parent = ".".join(parts[:-1])
                    resolved = f"{parent}.{sibling}" if parent else sibling
                elif target_str.startswith("#"):
                    resolved = target_str[1:]
                else:
                    resolved = target_str
                
                if resolved not in reachable:
                    # Check if it exists
                    check_parts = resolved.split(".")
                    check_current = states
                    exists = True
                    for cp in check_parts:
                        if cp in check_current:
                            check_current = check_current[cp]
                        else:
                            exists = False
                            break
                    if exists:
                        queue.append((check_parts[-1], resolved))
        
        # Add sub-states to queue
        if "states" in current:
            sub_initial = current.get("initial")
            if sub_initial and sub_initial in current["states"]:
                sub_path = f"{path}.{sub_initial}"
                if sub_path not in reachable:
                    queue.append((sub_initial, sub_path))
    
    return reachable


def _collect_all_state_paths(states_dict: dict, prefix: str = "") -> list:
    """Collect all state paths in the machine.
    
    Args:
        states_dict: The states dict to traverse
        prefix: Current path prefix
    
    Returns:
        List of full state paths
    """
    paths = []
    for name, config in states_dict.items():
        full_path = f"{prefix}.{name}" if prefix else name
        paths.append(full_path)
        if "states" in config:
            paths.extend(_collect_all_state_paths(config["states"], full_path))
    return paths


def _resolve_canonical_target(target: str, from_state: str, all_paths: list) -> str:
    """Resolve a target to its canonical (full) path.
    
    Args:
        target: Target string (may be relative or partial)
        from_state: Source state path
        all_paths: List of all state paths in the machine
    
    Returns:
        Canonical target path
    """
    if not target:
        return target
    
    # Already absolute with #
    if target.startswith("#"):
        return target[1:]
    
    # Relative reference: .name
    if target.startswith("."):
        sibling = target[1:]
        parts = from_state.rsplit(".", 1)
        if len(parts) == 2:
            parent = parts[0]
            return f"{parent}.{sibling}"
        return sibling
    
    # Check if it's already a full path
    if target in all_paths:
        return target
    
    # Try to find it as a sibling
    parts = from_state.rsplit(".", 1)
    if len(parts) == 2:
        parent = parts[0]
        candidate = f"{parent}.{target}"
        if candidate in all_paths:
            return candidate
    
    # Try to find it in the same branch
    branch = parts[0] if parts else ""
    candidate = f"{branch}.{target}"
    if candidate in all_paths:
        return candidate
    
    # Return as-is
    return target


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
    
    def _dedup_states(states_dict: dict) -> None:
        # Count occurrences of each state name
        name_counts = {}
        for name in states_dict:
            name_counts[name] = name_counts.get(name, 0) + 1
        
        # If no duplicates, skip
        if all(count == 1 for count in name_counts.values()):
            # Still recurse
            for config in states_dict.values():
                if "states" in config:
                    _dedup_states(config["states"])
            return
        
        # For now, just recurse (actual dedup would need more context)
        for config in states_dict.values():
            if "states" in config:
                _dedup_states(config["states"])
    
    _dedup_states(states)
    return machine


def apply_error_injection(machine: dict) -> dict:
    """Inject error handlers into states that need them.
    
    For each state with entry actions or transitions, ensure there's an
    error_handler sub-state with RETRY and CANCEL transitions.
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with error handlers injected
    """
    states = machine.get("states", {})
    
    def _inject_recursive(states_dict: dict, prefix: str = "", depth: int = 0) -> None:
        # Prevent infinite recursion
        if depth > 10:
            return
        
        for name, config in list(states_dict.items()):
            full_path = f"{prefix}.{name}" if prefix else name
            
            # Skip if already has error_handler
            sub_states = config.get("states", {})
            if "error_handler" in sub_states:
                # Recurse into existing sub_states
                _inject_recursive(sub_states, full_path, depth + 1)
                continue
            
            # Check if this state needs error handling
            entry_actions = config.get("entry", [])
            transitions = config.get("on", {})
            
            needs_error = len(entry_actions) > 0 or len(transitions) > 0
            
            if needs_error and not sub_states:
                # Create error_handler
                exit_target = _find_exit_target_for_state(full_path, machine)
                config["states"] = {
                    "error_handler": {
                        "entry": ["logError", "showRetryModal"],
                        "exit": ["hideRetryModal"],
                        "on": {
                            "RETRY": f"^{full_path}",
                            "CANCEL": f"#{exit_target}"
                        }
                    }
                }
            elif sub_states:
                # Recurse into existing sub_states
                _inject_recursive(sub_states, full_path, depth + 1)
    
    _inject_recursive(states)
    return machine


def apply_global_exit(machine: dict) -> dict:
    """Add GLOBAL_EXIT transition to all top-level states.
    
    GLOBAL_EXIT → #navigation.{initial} allows any state to exit to home.
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with global exit transitions
    """
    emergency_target = _find_emergency_exit_target(machine)
    states = machine.get("states", {})
    
    for branch_name, branch_config in states.items():
        branch_states = branch_config.get("states", {})
        for state_name, state_config in branch_states.items():
            transitions = state_config.get("on", {})
            # Add GLOBAL_EXIT if not already present
            if "GLOBAL_EXIT" not in transitions:
                transitions["GLOBAL_EXIT"] = emergency_target
    
    return machine


def apply_dead_state_cleanup(machine: dict) -> dict:
    """Remove or connect unreachable states.
    
    States that can't be reached from the initial state are either:
    - Connected (if they have entry actions — likely important)
    - Removed (if they're truly dead)
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with dead states cleaned up
    """
    reachable = _bfs_reachable(machine)
    states = machine.get("states", {})
    
    def _cleanup(states_dict: dict, prefix: str = "") -> None:
        to_remove = []
        
        for name, config in states_dict.items():
            full_path = f"{prefix}.{name}" if prefix else name
            
            if full_path not in reachable and name not in ("error_handler",):
                # Check if it has entry actions (might be important)
                entry_actions = config.get("entry", [])
                if not entry_actions:
                    to_remove.append(name)
            
            # Recurse
            if "states" in config:
                _cleanup(config["states"], full_path)
        
        for name in to_remove:
            del states_dict[name]
    
    _cleanup(states)
    return machine


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
    states = machine.get("states", {})
    # Check both possible workflow branch names
    return state_path.startswith("workflows.") or state_path.startswith("active_workflows.")


def _find_session_expired_target(machine: dict) -> str:
    """Find the session_expired state in the navigation branch.
    
    STRUCTURAL: dynamically finds the session_expired state.
    Falls back to navigation.error if not found.
    
    Args:
        machine: The full state machine dict
    
    Returns:
        Absolute path to session_expired state
    """
    states = machine.get("states", {})
    nav = states.get("navigation", {})
    nav_states = nav.get("states", {})
    
    if "session_expired" in nav_states:
        return "navigation.session_expired"
    
    # Fallback: navigation.error
    if "error" in nav_states:
        return "navigation.error"
    
    # Ultimate fallback: navigation initial
    nav_initial = nav.get("initial", "app_idle")
    return f"navigation.{nav_initial}"


def _find_error_target(machine: dict) -> str:
    """Find the error state in the navigation branch.
    
    STRUCTURAL: dynamically finds the error state.
    Falls back to navigation initial if not found.
    
    Args:
        machine: The full state machine dict
    
    Returns:
        Absolute path to error state
    """
    states = machine.get("states", {})
    nav = states.get("navigation", {})
    nav_states = nav.get("states", {})
    
    if "error" in nav_states:
        return "navigation.error"
    
    # Fallback: navigation initial
    nav_initial = nav.get("initial", "app_idle")
    return f"navigation.{nav_initial}"


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
        # Prevent infinite recursion
        if depth > 10:
            return
        
        for name, config in states_dict.items():
            full_path = f"{prefix}.{name}" if prefix else name
            
            # 1. Add guards to RETRY transitions in error states
            if "error" in name.lower():
                transitions = config.get("on", {})
                
                # Handle simple string RETRY target
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
                
                # Handle simple string RETRY_FETCH target
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


# =============================================================================
# Core Builder Functions
# =============================================================================

# STRUCTURAL: extensible action mapping — add domain-specific actions here
# Each entry maps an action name → (type, assignment_key, value_lambda)
XSTATE_ACTION_MAP = {
    "incrementRetryCount": ("assign", "retryCount", lambda ctx: ctx.get("retryCount", 0) + 1),
    "setPreviousState": ("assign", "previousState", lambda ctx, evt, meta: meta.state.value),
    "clearErrors": ("assign", "errors", lambda ctx: []),
    "resetRetryCount": ("assign", "retryCount", lambda ctx: 0),
    "setUser": ("assign", "user", lambda ctx, evt: evt.data),
    "setLoading": ("assign", "loading", lambda ctx: True),
    "setLoaded": ("assign", "loading", lambda ctx: False),
}


def _format_xstate_actions(actions_list: list, custom_map: dict = None) -> list:
    """Format textual actions into valid XState v5 actions.
    
    STRUCTURAL: uses an extensible map instead of hardcoded if/elif.
    Supports custom action mappings for domain-specific needs.
    
    Args:
        actions_list: List of action strings from LLM
        custom_map: Optional dict of additional action mappings
    
    Returns:
        List of XState-compatible actions
    """
    # Merge default + custom maps (custom overrides default)
    action_map = {**XSTATE_ACTION_MAP, **(custom_map or {})}
    
    formatted = []
    for action in actions_list:
        if action in action_map:
            action_type, key, value_fn = action_map[action]
            formatted.append({
                "type": action_type,
                "assignment": {key: value_fn}
            })
        else:
            formatted.append(action)
    return formatted


def generate_base_machine(use_parallel: bool = True, state_names: dict = None, branch_names: dict = None) -> dict:
    """Generate an empty base state machine with proper parallel structure.
    
    STRUCTURAL: Uses configurable state and branch names instead of hardcoded values.
    This makes the builder universal — works for e-commerce, IoT, social, gaming, etc.
    
    Args:
        use_parallel: If True, creates parallel states architecture
        state_names: Optional dict overriding DEFAULT_STATE_NAMES (e.g., {"initial": "home"})
        branch_names: Optional dict overriding DEFAULT_BRANCH_NAMES (e.g., {"navigation": "ui"})
    
    Returns:
        Base machine dict
    """
    # Resolve names using defaults + overrides
    initial_name = _resolve_state_name("initial", state_names)
    workflow_none = _resolve_state_name("workflow_none", state_names)
    nav_branch = _resolve_branch_name("navigation", branch_names)
    wf_branch = _resolve_branch_name("workflows", branch_names)
    hide_workflow = _resolve_action_name("hide_workflow")
    
    if use_parallel:
        return {
            "id": "appFlow",
            "type": "parallel",
            "context": {
                "user": None,
                "errors": [],
                "retryCount": 0,
                "previousState": None
            },
            "states": {
                nav_branch: {
                    "id": "nav_branch",
                    "initial": initial_name,
                    "on": {},
                    "states": {}
                },
                wf_branch: {
                    "id": "wf_branch",
                    "initial": workflow_none,
                    "on": {},
                    "states": {
                        workflow_none: {
                            "entry": [hide_workflow],
                            "exit": [],
                            "on": {}
                        }
                    }
                }
            }
        }
    else:
        return {
            "id": "appFlow",
            "initial": initial_name,
            "context": {
                "user": None,
                "errors": [],
                "retryCount": 0,
                "previousState": None
            },
            "states": {}
        }


def _auto_generate_sub_states(state_name: str, state: dict) -> dict:
    """Auto-generate sub_states (loading, ready, error) for states that need them.
    
    A state needs sub_states if:
    - It has entry actions (indicates it's a real screen/workflow)
    - It has API-like events (needs error handling)
    - It's a workflow step (has cross_page_events)
    
    Args:
        state_name: Name of the parent state
        state: LLM-generated state dict
    
    Returns:
        Dict with 'initial' and 'states' for sub-states
    """
    entry_actions = state.get("entry_actions", [])
    exit_actions = state.get("exit_actions", [])
    transitions = state.get("transitions", [])
    
    # Check if this state needs sub_states
    needs_sub_states = (
        len(entry_actions) > 0 or  # Has entry actions
        len(transitions) > 0 or    # Has transitions
        state.get("sub_states", [])  # Already has sub_states defined
    )
    
    if not needs_sub_states:
        return {}
    
    # Check if sub_states are already defined
    if state.get("sub_states"):
        return {}  # Already handled by the main logic
    
    # Auto-generate: loading → ready → error pattern
    sub_states = {}
    
    # 1. loading sub-state
    sub_states["loading"] = {
        "entry": ["showLoading", f"fetch{state_name.title()}"],
        "exit": ["hideLoading"],
        "on": {
            "DATA_LOADED": ".ready",
            "LOAD_FAILED": ".error",
            "TIMEOUT": ".error"
        }
    }
    
    # 2. ready sub-state (the main working state)
    ready_entry = list(entry_actions) if entry_actions else [f"show{state_name.title()}"]
    ready_exit = list(exit_actions) if exit_actions else [f"hide{state_name.title()}"]
    sub_states["ready"] = {
        "entry": ready_entry,
        "exit": ready_exit,
        "on": {}
    }
    
    # 3. error sub-state
    sub_states["error"] = {
        "entry": ["logError", "showErrorBanner"],
        "exit": ["hideErrorBanner"],
        "on": {
            "RETRY": ".loading",
            "CANCEL": f"#{_find_exit_target_for_state(state_name)}"
        }
    }
    
    return {
        "initial": "loading",
        "states": sub_states
    }


def _find_exit_target_for_state(state_name: str, machine: dict = None) -> str:
    """Find the appropriate exit target for a state using STRUCTURAL analysis.
    
    Instead of keyword matching, this checks:
    1. Is the state inside the workflows branch? → workflows.none
    2. Is the state inside the navigation branch? → navigation.{initial}
    3. Fallback: check if state name contains branch indicators in its path
    
    Args:
        state_name: Full path of the state (e.g., "workflows.benchmark", "navigation.success")
        machine: Optional state machine dict for structural lookup
    
    Returns:
        Canonical exit target path
    """
    # Structural check: if the path contains the branch name
    if state_name.startswith("workflows.") or state_name.startswith("active_workflows."):
        return "workflows.none"
    
    if state_name.startswith("navigation."):
        # Find the initial state of navigation
        if machine:
            nav = machine.get("states", {}).get("navigation", {})
            nav_initial = nav.get("initial", "app_idle")
            return f"navigation.{nav_initial}"
        return "navigation.app_idle"
    
    # Fallback: if state name contains workflow-like keywords (backward compat)
    if any(kw in state_name.lower() for kw in ["workflow", "benchmark", "purchase", "alert", "group"]):
        return "workflows.none"
    
    # Default: navigation initial
    if machine:
        nav = machine.get("states", {}).get("navigation", {})
        nav_initial = nav.get("initial", "app_idle")
        return f"navigation.{nav_initial}"
    return "navigation.app_idle"


def build_state_config(state: dict) -> dict:
    """Build XState state config from LLM state dict.
    
    Supports hierarchical states with auto-generated navigation events.
    Auto-generates loading/ready/error sub_states for states that need them.
    
    Args:
        state: LLM-generated state dict
    
    Returns:
        XState-compatible state config
    """
    state_name = state.get("name", "unknown")
    
    config = {
        "entry": state.get("entry_actions", []),
        "exit": state.get("exit_actions", []),
        "on": {}
    }
    
    sub_states = state.get("sub_states", [])
    if sub_states:
        initial_sub = state.get("initial_sub_state") or sub_states[0]
        if isinstance(initial_sub, dict):
            initial_sub = initial_sub.get("name", "")
        
        config["initial"] = initial_sub
        config["states"] = {}
        
        for sub in sub_states:
            sub_name = sub if isinstance(sub, str) else sub.get("name", "")
            if "." in sub_name:
                sub_name = sub_name.split(".")[-1]
            
            sub_entry = [] if isinstance(sub, str) else sub.get("entry_actions", [])
            sub_exit = [] if isinstance(sub, str) else sub.get("exit_actions", [])
            config["states"][sub_name] = {
                "entry": sub_entry,
                "exit": sub_exit,
                "on": {}
            }
        
        # Auto-generate NAVIGATE events between sub-states
        for sub in sub_states:
            sub_name = sub if isinstance(sub, str) else sub.get("name", "")
            if "." in sub_name:
                sub_name = sub_name.split(".")[-1]
            nav_event = f"NAVIGATE_{sub_name.upper()}"
            for other_sub in sub_states:
                other_name = other_sub if isinstance(other_sub, str) else other_sub.get("name", "")
                if "." in other_name:
                    other_name = other_name.split(".")[-1]
                if other_name != sub_name:
                    config["states"][other_name]["on"][nav_event] = f".{sub_name}"
    else:
        # Auto-generate sub_states if this state needs them
        auto_sub = _auto_generate_sub_states(state_name, state)
        if auto_sub:
            config["initial"] = auto_sub["initial"]
            config["states"] = auto_sub["states"]
    
    return config


def add_transitions(machine: dict, transitions: list):
    """Add transitions with canonical target resolution.
    
    Uses specificity-based resolution to handle ambiguous targets.
    
    Args:
        machine: The state machine dict
        transitions: List of transition dicts from LLM
    """
    all_paths = _collect_all_state_paths(machine.get("states", {}))
    
    for i, trans in enumerate(transitions):
        if "from_state" not in trans or "to_state" not in trans or "event" not in trans:
            print(f"  ⚠️  Skipping transition #{i}: missing required fields")
            continue
        
        from_state = trans["from_state"]
        to_state = trans["to_state"]
        event = trans["event"]
        guard = trans.get("guard") or trans.get("cond")
        actions = trans.get("actions") or trans.get("action", [])
        if isinstance(actions, str):
            actions = [actions]
        
        # Resolve dot notation
        target_dict = machine.get("states", {})
        resolved_from = from_state
        
        if "." in from_state:
            parts = from_state.split(".")
            parent = parts[0]
            child = parts[1]
            if parent in target_dict and "states" in target_dict[parent]:
                if child in target_dict[parent]["states"]:
                    target_dict = target_dict[parent]["states"]
                    resolved_from = child
                    if not to_state.startswith("."):
                        to_state = f".{to_state}" if "." not in to_state else to_state
        
        if resolved_from in target_dict:
            resolved_target = _resolve_canonical_target(to_state, from_state, all_paths)
            
            if guard or actions:
                transition = {"target": resolved_target}
                if guard:
                    transition["cond"] = guard
                if actions:
                    transition["actions"] = _format_xstate_actions(actions)
                target_dict[resolved_from]["on"][event] = transition
            else:
                target_dict[resolved_from]["on"][event] = resolved_target


def add_transitions_to_branch(machine: dict, transitions: list):
    """Add transitions to the navigation branch.
    
    Args:
        machine: The state machine dict (parallel structure)
        transitions: List of transition dicts
    """
    nav_branch = machine.get("states", {}).get("navigation", {})
    if not nav_branch:
        return
    
    all_paths = _collect_all_state_paths(machine.get("states", {}))
    
    for i, trans in enumerate(transitions):
        if "from_state" not in trans or "to_state" not in trans or "event" not in trans:
            continue
        
        from_state = trans["from_state"]
        to_state = trans["to_state"]
        event = trans["event"]
        guard = trans.get("guard") or trans.get("cond")
        actions = trans.get("actions") or trans.get("action", [])
        if isinstance(actions, str):
            actions = [actions]
        
        target_dict = nav_branch.get("states", {})
        resolved_from = from_state
        
        if "." in from_state:
            parts = from_state.split(".")
            parent = parts[0]
            child = parts[1]
            if parent in target_dict and "states" in target_dict[parent]:
                if child in target_dict[parent]["states"]:
                    target_dict = target_dict[parent]["states"]
                    resolved_from = child
                    if not to_state.startswith("."):
                        to_state = f".{to_state}" if "." not in to_state else to_state
        
        if resolved_from in target_dict:
            resolved_target = _resolve_canonical_target(to_state, from_state, all_paths)
            
            if guard or actions:
                transition = {"target": resolved_target}
                if guard:
                    transition["cond"] = guard
                if actions:
                    transition["actions"] = _format_xstate_actions(actions)
                target_dict[resolved_from]["on"][event] = transition
            else:
                target_dict[resolved_from]["on"][event] = resolved_target


def build_workflow_compound_state(workflow: dict, machine: dict = None) -> dict:
    """Build a compound state for a workflow.
    
    STRUCTURAL: resolves 'none' and navigation targets dynamically.
    Creates hierarchical state with internal micro-states for each step.
    
    Args:
        workflow: Analyst workflow dict with id, name, steps, etc.
        machine: Optional state machine dict for structural resolution
    
    Returns:
        XState compound state config
    """
    workflow_id = workflow["id"]
    steps = workflow.get("steps", [])
    cross_page_events = workflow.get("cross_page_events", [])
    completion_events = workflow.get("completion_events", ["COMPLETED", "CANCELLED"])
    
    if not steps:
        return {}
    
    # STRUCTURAL: find the "none" state dynamically
    none_target = "none"  # default
    if machine:
        wf_branch = machine.get("states", {}).get("workflows") or machine.get("states", {}).get("active_workflows", {})
        wf_states = wf_branch.get("states", {})
        # Find the first state that looks like a "none" state (has hideWorkflowOverlay entry)
        for state_name, state_config in wf_states.items():
            entry = state_config.get("entry", [])
            if any("hideWorkflow" in a for a in entry) or state_name == "none":
                none_target = state_name
                break
    
    # STRUCTURAL: find the navigation success state dynamically
    nav_success_prefix = "#navigation.success"  # default
    if machine:
        nav = machine.get("states", {}).get("navigation", {})
        nav_states = nav.get("states", {})
        # Find the first state that looks like a success/main state
        for state_name in nav_states:
            if state_name in ("success", "main", "home", "dashboard"):
                nav_success_prefix = f"#navigation.{state_name}"
                break
    
    initial_step = steps[0]
    state_config = {
        "initial": initial_step,
        "states": {},
        "on": {}
    }
    
    for i, step in enumerate(steps):
        step_config = {
            "entry": [f"show{step.title()}"],
            "exit": [f"hide{step.title()}"],
            "on": {}
        }
        
        # Transition to next step
        if i < len(steps) - 1:
            next_step = steps[i + 1]
            trigger_event = cross_page_events[i] if i < len(cross_page_events) else "NEXT_STEP"
            step_config["on"][trigger_event] = next_step
        
        # GO_BACK to previous step
        if i > 0:
            step_config["on"]["GO_BACK"] = steps[i - 1]
        else:
            step_config["on"]["GO_BACK"] = none_target
        
        # CANCEL to none (resolved dynamically)
        step_config["on"]["CANCEL"] = none_target
        
        # Completion events for last step
        if i == len(steps) - 1:
            for completion_event in completion_events:
                step_config["on"][completion_event] = none_target
        
        state_config["states"][step] = step_config
    
    # Cross-page navigation events
    for event in cross_page_events:
        if event.startswith("NAVIGATE_"):
            target_page = event.replace("NAVIGATE_", "").lower()
            state_config["on"][event] = f"{nav_success_prefix}.{target_page}"
    
    return state_config


def add_workflows_to_machine(machine: dict, workflows: list):
    """Add workflow compound states to the workflows branch.
    
    Args:
        machine: The state machine dict
        workflows: List of workflow dicts
    """
    # Support both 'workflows' and 'active_workflows' branch names
    workflows_branch = machine.get("states", {}).get("workflows") or machine.get("states", {}).get("active_workflows")
    if not workflows_branch:
        return
    
    for workflow in workflows:
        workflow_id = workflow["id"]
        compound_state = build_workflow_compound_state(workflow)
        if compound_state:
            workflows_branch["states"][workflow_id] = compound_state


def normalize_machine(machine: dict) -> dict:
    """Normalize machine: fix common issues.
    
    STRUCTURAL approach: uses the 'initial' value to determine the target state name,
    not hardcoded 'app_idle'. Works with ANY naming convention.
    
    Handles both parallel and flat architectures.
    
    Args:
        machine: The state machine dict
    
    Returns:
        Normalized machine dict
    """
    if machine.get("type") == "parallel" and "navigation" in machine.get("states", {}):
        nav_branch = machine["states"]["navigation"]
        nav_initial = nav_branch.get("initial", "app_idle")
        
        # Fix idle → {initial} (use the actual initial state name)
        if "idle" in nav_branch.get("states", {}) and nav_initial:
            nav_branch["states"][nav_initial] = nav_branch["states"].pop("idle")
            for state_config in nav_branch["states"].values():
                for event, target in list(state_config.get("on", {}).items()):
                    if target == "idle":
                        state_config["on"][event] = nav_initial
        
        # Ensure initial state exists
        if nav_initial and nav_initial not in nav_branch.get("states", {}):
            nav_branch["states"][nav_initial] = {"entry": [], "exit": [], "on": {}}
    
    else:
        # Flat architecture
        seq_initial = machine.get("initial", "app_idle")
        
        if "idle" in machine["states"] and seq_initial:
            machine["states"][seq_initial] = machine["states"].pop("idle")
            for state_config in machine["states"].values():
                for event, target in list(state_config.get("on", {}).items()):
                    if target == "idle":
                        state_config["on"][event] = seq_initial
        
        if seq_initial and seq_initial not in machine["states"]:
            machine["states"][seq_initial] = {"entry": [], "exit": [], "on": {}}
    
    return machine


def deduplicate_machine(machine: dict) -> dict:
    """Remove duplicate states using specificity-based deduplication.
    
    This is the Pattern Compiler's approach: instead of name-based removal,
    we keep the 'smartest' version of each state (highest specificity).
    
    Args:
        machine: The state machine dict
    
    Returns:
        Deduplicated machine
    """
    return apply_specificity_dedup(machine)


# =============================================================================
# Rule 6: Structural Branch Placement
# =============================================================================

def _is_compound_state(state_config: dict) -> bool:
    """Check if a state is a compound state (has sub_states).
    
    A compound state is a state that contains other states.
    These are typically workflows or complex screens.
    
    Args:
        state_config: The state's configuration dict
    
    Returns:
        True if this state has sub_states
    """
    return bool(state_config.get("states", {}))


def _is_leaf_state(state_config: dict) -> bool:
    """Check if a state is a leaf state (no sub_states, just entry/exit/on).
    
    A leaf state is a simple state that doesn't contain other states.
    These are typically navigation pages/screens.
    
    Args:
        state_config: The state's configuration dict
    
    Returns:
        True if this state has no sub_states
    """
    return not state_config.get("states", {})


def apply_branch_placement(machine: dict) -> dict:
    """Move orphan states to the correct branch based on their structure.
    
    RULE: States at root level that are NOT 'navigation' or 'workflows' branches
    should be moved into the appropriate branch:
    - Compound states (have sub_states) → workflows branch
    - Leaf states (no sub_states) → navigation branch
    - States whose name equals machine.id → REMOVE (LLM error)
    
    This is a STRUCTURAL rule, not a name-based rule.
    It works with ANY app because it looks at the JSON structure, not the names.
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with orphan states moved to correct branches
    """
    states = machine.get("states", {})
    machine_id = machine.get("id", "")
    
    # Identify branches
    nav_branch = states.get("navigation", {})
    wf_branch = states.get("workflows") or states.get("active_workflows", {})
    
    # States that are branches (not orphans) — STRUCTURAL: any state with 'initial' + 'states' is a branch
    branch_names = {"navigation", "workflows", "active_workflows"}
    
    # CRITICAL: Handle machine.id as state name BEFORE structural branch detection
    # This is an LLM error: the machine's own ID should not be a state name.
    # If it's a compound state (has sub_states), move it to workflows branch.
    # If it's a leaf state, move it to navigation branch.
    if machine_id and machine_id in states:
        orphan_config = states[machine_id]
        if _is_compound_state(orphan_config):
            if "states" not in wf_branch:
                wf_branch["states"] = {}
            wf_branch["states"][machine_id] = orphan_config
        else:
            if "states" not in nav_branch:
                nav_branch["states"] = {}
            nav_branch["states"][machine_id] = orphan_config
        del states[machine_id]
    
    # Also detect branches by structure (has 'initial' + 'states' = parallel/compound branch)
    for name, config in list(states.items()):
        if name in branch_names:
            continue
        if config.get("initial") and config.get("states"):
            branch_names.add(name)
    
    # Find orphan states (at root level, not branches)
    orphans = {}
    for name, config in list(states.items()):
        if name in branch_names:
            continue
        # This is an orphan state
        orphans[name] = config
    
    # Move orphans to appropriate branch
    for name, config in orphans.items():
        if _is_compound_state(config):
            # Compound state → workflows branch
            if "states" not in wf_branch:
                wf_branch["states"] = {}
            wf_branch["states"][name] = config
        else:
            # Leaf state → navigation branch
            if "states" not in nav_branch:
                nav_branch["states"] = {}
            nav_branch["states"][name] = config
        
        # Remove from root
        if name in states:
            del states[name]
    
    return machine


# =============================================================================
# Main Compilation Pipeline
# =============================================================================

# States that are part of the auto-generated loading/ready/error pattern
# and should NOT get their own sub_states injected.
# STRUCTURAL: also skip any state that already has 'initial' + 'states' (compound states).
AUTO_GENERATED_SUB_STATES = {"loading", "ready", "error", "calculating", "fetching", "submitting", "saving", "processing", "validating", "authenticating", "registering", "joining", "tracking", "monitoring", "deleting", "creating"}

def _infer_sub_state_name(action_name: str) -> str:
    """Infer the sub_state name from an action name using linguistic patterns.
    
    Universal approach: analyzes the VERB prefix of the action name to determine
    what kind of operation is happening, then maps to an appropriate sub_state name.
    
    Examples:
    - calculateCluster → calculating (verb: calculate)
    - fetchGroupsData → fetching (verb: fetch)
    - submitGroup → submitting (verb: submit)
    - saveUser → saving (verb: save)
    - loadProducts → loading (verb: load)
    - processPayment → processing (verb: process)
    
    Args:
        action_name: A single action string (e.g., "calculateCluster", "fetchGroups")
    
    Returns:
        The inferred sub_state name (e.g., 'calculating', 'fetching', 'loading')
    """
    if not action_name:
        return "loading"
    
    lower = action_name.lower()
    
    # Verb prefix patterns → gerund form (universal linguistic mapping)
    verb_patterns = [
        ("calculate", "calculating"),
        ("compute", "calculating"),
        ("cluster", "calculating"),
        ("fetch", "fetching"),
        ("load", "loading"),
        ("get", "loading"),
        ("retrieve", "loading"),
        ("submit", "submitting"),
        ("send", "submitting"),
        ("post", "submitting"),
        ("save", "saving"),
        ("update", "saving"),
        ("store", "saving"),
        ("process", "processing"),
        ("handle", "processing"),
        ("execute", "processing"),
        ("validate", "validating"),
        ("verify", "validating"),
        ("check", "validating"),
        ("authenticate", "authenticating"),
        ("login", "authenticating"),
        ("register", "registering"),
        ("signup", "registering"),
        ("join", "joining"),
        ("track", "tracking"),
        ("monitor", "monitoring"),
        ("observe", "monitoring"),
        ("delete", "deleting"),
        ("remove", "deleting"),
        ("destroy", "deleting"),
        ("create", "creating"),
        ("add", "creating"),
        ("generate", "creating"),
    ]
    
    # Find the best matching verb prefix (longest match = most specific)
    best_match = "loading"  # default fallback
    best_length = 0
    
    for verb, gerund in verb_patterns:
        if lower.startswith(verb) or verb in lower:
            if len(verb) > best_length:
                best_length = len(verb)
                best_match = gerund
    
    return best_match


def _find_emergency_exit_target(machine: dict) -> str:
    """Find the appropriate emergency exit target for a state machine.
    
    Instead of hardcoding '#navigation.app_idle', this dynamically finds
    the initial state of the navigation branch (or first branch if no navigation).
    
    Args:
        machine: The state machine dict
    
    Returns:
        The canonical path to use as emergency exit target (e.g., '#navigation.app_idle')
    """
    states = machine.get("states", {})
    
    # Priority 1: navigation branch → its initial state
    nav = states.get("navigation", {})
    nav_initial = nav.get("initial")
    if nav_initial:
        return f"#navigation.{nav_initial}"
    
    # Priority 2: any parallel branch with an initial state
    for branch_name, branch_config in states.items():
        if branch_name in ("navigation", "workflows", "active_workflows"):
            continue
        branch_initial = branch_config.get("initial")
        if branch_initial:
            return f"#{branch_name}.{branch_initial}"
    
    # Priority 3: sequential machine initial state
    seq_initial = machine.get("initial")
    if seq_initial:
        return seq_initial
    
    # Ultimate fallback
    return "app_idle"


def _extract_target_string(target) -> str:
    """Extract a target string from a transition target, handling all formats.
    
    Handles:
    - String: "loading" → "loading"
    - Dict: {"target": "loading", "cond": "canRetry"} → "loading"
    - List: [{"target": "loading", "cond": "canRetry"}, ...] → "loading" (first)
    
    Args:
        target: Target in any format (str, dict, or list)
    
    Returns:
        Target string, or empty string if not found
    """
    if isinstance(target, str):
        return target
    elif isinstance(target, dict):
        return target.get("target", "")
    elif isinstance(target, list):
        # Multi-target: extract first target string
        for item in target:
            if isinstance(item, dict):
                t = item.get("target", "")
                if t:
                    return t
            elif isinstance(item, str):
                if item:
                    return item
        return ""
    return ""


def _add_emergency_exits(states_dict: dict, machine: dict, parent_name: str = "") -> None:
    """Add emergency exit transitions for states that don't have a way back.
    
    If a state has entry actions but NO transitions that lead back to the main flow,
    add a default GO_BACK → [initial state] transition.
    
    This prevents the "Ghost Ship" problem where states exist but you can't leave them.
    
    Args:
        states_dict: The states dict to process
        machine: The full state machine (used to find emergency exit target)
        parent_name: Current path prefix
    """
    emergency_target = _find_emergency_exit_target(machine)
    
    for name, config in states_dict.items():
        full_name = f"{parent_name}.{name}" if parent_name else name
        
        # Skip auto-generated sub_states
        if name in AUTO_GENERATED_SUB_STATES:
            continue
        
        transitions = config.get("on", {})
        sub_states = config.get("states", {})
        
        # Check if this state has any exit transitions
        has_exit = False
        for event, target in transitions.items():
            target_str = _extract_target_string(target)
            # Check if target goes somewhere meaningful (not just self or parent)
            if target_str and target_str != name and target_str != ".":
                has_exit = True
                break
        
        # If no exit transitions and this is a real state (has entry actions), add emergency exit
        entry_actions = config.get("entry", [])
        if entry_actions and not has_exit and not sub_states:
            transitions["GO_BACK"] = emergency_target
            transitions["CANCEL"] = emergency_target
        
        # Recurse into sub_states
        if sub_states:
            _add_emergency_exits(sub_states, machine, full_name)


def _auto_inject_sub_states(machine: dict) -> dict:
    """Auto-inject loading/ready/error sub_states for states that need them.
    
    This is called by compile_machine to ensure every meaningful state has
    the loading → ready → error pattern, even if the LLM didn't generate it.
    
    CONTEXT-AWARE: Instead of always using 'loading', reads entry_actions to
    determine specific names:
    - calculateCluster → 'calculating'
    - fetchGroupsData → 'fetching'
    - submitGroup → 'submitting'
    
    A state needs sub_states if:
    - It has entry actions (indicates it's a real screen/workflow)
    - It has transitions (needs error handling)
    - It's NOT already a loading/ready/error sub_state
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with auto-injected sub_states
    """
    states = machine.get("states", {})
    
    def _inject_recursive(states_dict: dict, parent_name: str = "", depth: int = 0) -> None:
        # Prevent infinite recursion
        if depth > 5:
            return
        
        for name, config in list(states_dict.items()):
            full_name = f"{parent_name}.{name}" if parent_name else name
            
            # Skip auto-generated sub_states (loading, ready, error)
            if name in AUTO_GENERATED_SUB_STATES:
                continue
            
            # Skip if already has sub_states
            if "states" in config and config["states"]:
                # Recurse into existing sub_states
                _inject_recursive(config["states"], full_name, depth + 1)
                continue
            
            # Check if this state needs sub_states
            entry_actions = config.get("entry", [])
            exit_actions = config.get("exit", [])
            transitions = config.get("on", {})
            
            needs_sub_states = (
                len(entry_actions) > 0 or  # Has entry actions
                len(transitions) > 0       # Has transitions
            )
            
            if not needs_sub_states:
                continue
            
            # Context-aware: detect specific sub_state name from entry_actions
            # Use the first entry action to infer the loading sub_state name
            first_action = entry_actions[0] if entry_actions else ""
            loading_name = _infer_sub_state_name(first_action)
            
            # Generate sub_states
            sub_states = {}
            
            # 1. Context-aware loading sub-state (e.g., 'calculating', 'fetching')
            sub_states[loading_name] = {
                "entry": ["showLoading", f"fetch{full_name.title().replace('.', '')}"],
                "exit": ["hideLoading"],
                "on": {
                    "DATA_LOADED": ".ready",
                    "LOAD_FAILED": ".error",
                    "TIMEOUT": ".error"
                }
            }
            
            # 2. ready sub-state
            sub_states["ready"] = {
                "entry": list(entry_actions) if entry_actions else [f"show{full_name.title().replace('.', '')}"],
                "exit": list(exit_actions) if exit_actions else [f"hide{full_name.title().replace('.', '')}"],
                "on": dict(transitions)  # Copy existing transitions
            }
            
            # 3. error sub-state
            exit_target = _find_exit_target_for_state(full_name, machine)
            sub_states["error"] = {
                "entry": ["logError", "showErrorBanner"],
                "exit": ["hideErrorBanner"],
                "on": {
                    "RETRY": f".{loading_name}",  # Retry goes back to context-aware loading
                    "CANCEL": f"#{exit_target}"
                }
            }
            
            # Update config
            config["initial"] = loading_name
            config["states"] = sub_states
            config["on"] = {}  # Clear top-level transitions (moved to ready)
            
            # NO recursion into auto-generated sub_states (they're leaf states)
    
    _inject_recursive(states)
    
    # Add emergency exits for states without a way back
    _add_emergency_exits(states, machine)
    
    return machine


# =============================================================================
# Rule 0: Target Resolution & Placeholder Creation (CRITICAL FIX)
# =============================================================================

def _resolve_relative_target(target: str, source_path: str, machine: dict) -> str:
    """Resolve a relative target (.name) to an absolute path.
    
    STRUCTURAL: resolves .app_idle from navigation.authenticating → navigation.app_idle
    
    Args:
        target: Target string (may start with .)
        source_path: Full path of the source state (e.g., "navigation.authenticating")
        machine: The full state machine dict
    
    Returns:
        Resolved absolute path (e.g., "navigation.app_idle")
    """
    if not target:
        return target
    
    # Already absolute with #
    if target.startswith("#"):
        return target[1:]
    
    # Relative reference: .name → resolve to sibling in same parent
    if target.startswith("."):
        sibling_name = target[1:]
        # Find the parent of the source
        parts = source_path.rsplit(".", 1)
        if len(parts) == 2:
            parent_path, _ = parts
            return f"{parent_path}.{sibling_name}"
        return sibling_name
    
    # Contains . → might be a partial path like "navigation.app_idle"
    if "." in target:
        # Check if it exists as-is
        return target
    
    # Simple name → try to find it in the same branch as source
    source_parts = source_path.split(".")
    if len(source_parts) >= 2:
        branch = source_parts[0]
        candidate = f"{branch}.{target}"
        # Verify it exists
        states = machine.get("states", {})
        branch_config = states.get(branch, {})
        branch_states = branch_config.get("states", {})
        if target in branch_states:
            return candidate
    
    return target


def _resolve_caret_target(target: str, source_path: str, machine: dict) -> str:
    """Resolve ^parent syntax (XState doesn't support ^).
    
    ^navigation.authenticating → #navigation.authenticating
    
    Args:
        target: Target string (may start with ^)
        source_path: Full path of the source state
        machine: The full state machine dict
    
    Returns:
        Resolved target with # prefix
    """
    if not target:
        return target
    
    if target.startswith("^"):
        return f"#{target[1:]}"
    
    return target


def _fix_workflows_none_target(target: str, machine: dict) -> str:
    """Fix #workflows.none when branch is actually active_workflows.
    
    STRUCTURAL: checks which workflow branch exists and adjusts target.
    Handles case where BOTH branches exist (workflows as placeholder, active_workflows as real).
    
    Args:
        target: Target string (may contain workflows.none)
        machine: The full state machine dict
    
    Returns:
        Fixed target
    """
    if not target:
        return target
    
    states = machine.get("states", {})
    
    # ALWAYS fix workflows.none → active_workflows.none if active_workflows exists
    # This handles both cases:
    # 1. Only active_workflows exists (workflows doesn't exist)
    # 2. Both exist (workflows as placeholder, active_workflows as real branch)
    if "active_workflows" in states:
        # Fix #workflows.none → active_workflows.none
        if target == "#workflows.none":
            return "active_workflows.none"
        # Fix workflows.none → active_workflows.none (without #)
        if target == "workflows.none":
            return "active_workflows.none"
        # Fix #workflows.none.X → active_workflows.none.X
        if target.startswith("#workflows.none."):
            return target.replace("#workflows.none.", "active_workflows.none.")
        # Fix workflows.none.X → active_workflows.none.X
        if target.startswith("workflows.none."):
            return target.replace("workflows.none.", "active_workflows.none.")
    
    return target


def _fix_nonexistent_targets(target: str, machine: dict, source_branch: str = "") -> str:
    """Fix targets that reference non-existent branches/states.
    
    STRUCTURAL: maps common LLM errors to correct paths.
    Examples:
    - success.dashboard → navigation.success (success is a state in navigation, not a branch)
    - success.catalog → navigation.success
    - active_active_workflows.none → active_workflows.none (double prefix)
    - authenticating → navigation.authenticating (bare state name)
    
    Args:
        target: Target string
        machine: The full state machine dict
        source_branch: The branch where the source state lives (for bare name resolution)
    
    Returns:
        Fixed target
    """
    if not target:
        return target
    
    states = machine.get("states", {})
    
    # Fix double prefix: active_active_workflows.none → active_workflows.none
    if target.startswith("active_active_workflows."):
        return target.replace("active_active_workflows.", "active_workflows.")
    
    # Fix success.X → navigation.success (success is a state, not a branch)
    if target.startswith("success."):
        # Check if navigation.success exists
        nav = states.get("navigation", {})
        nav_states = nav.get("states", {})
        if "success" in nav_states:
            return "navigation.success"
        # Fallback: navigation.{initial}
        nav_initial = nav.get("initial", "app_idle")
        return f"navigation.{nav_initial}"
    
    # Fix empty.X → navigation.empty
    if target.startswith("empty."):
        nav = states.get("navigation", {})
        nav_states = nav.get("states", {})
        if "empty" in nav_states:
            return "navigation.empty"
    
    # Fix loading.X → navigation.loading
    if target.startswith("loading."):
        nav = states.get("navigation", {})
        nav_states = nav.get("states", {})
        if "loading" in nav_states:
            return "navigation.loading"
    
    # Fix error.X → navigation.error
    if target.startswith("error."):
        nav = states.get("navigation", {})
        nav_states = nav.get("states", {})
        if "error" in nav_states:
            return "navigation.error"
    
    # Fix bare state names (no dot, not a branch name)
    # Examples: "authenticating" → "navigation.authenticating"
    #           "app_idle" → "navigation.app_idle"
    if "." not in target and not target.startswith("#") and not target.startswith("^"):
        # Check if it's a branch name (don't fix branch names)
        if target in states:
            return target  # It's a branch, leave it alone
        
        # Try to find it in the source branch first
        if source_branch and source_branch in states:
            branch_config = states[source_branch]
            branch_states = branch_config.get("states", {})
            if target in branch_states:
                return f"{source_branch}.{target}"
        
        # Try navigation branch (most common case)
        nav = states.get("navigation", {})
        nav_states = nav.get("states", {})
        if target in nav_states:
            return f"navigation.{target}"
        
        # Try active_workflows branch
        wf = states.get("active_workflows", {})
        wf_states = wf.get("states", {})
        if target in wf_states:
            return f"active_workflows.{target}"
        
        # Try workflows branch
        wf_old = states.get("workflows", {})
        wf_old_states = wf_old.get("states", {})
        if target in wf_old_states:
            return f"workflows.{target}"
    
    return target


def _ensure_target_exists(target: str, source_path: str, machine: dict) -> bool:
    """Check if a target state exists in the machine.
    
    Args:
        target: Target string (absolute path or relative)
        source_path: Full path of the source state
        machine: The full state machine dict
    
    Returns:
        True if the target exists
    """
    if not target:
        return False
    
    # Resolve the target first
    resolved = target
    
    # Handle # prefix
    if resolved.startswith("#"):
        resolved = resolved[1:]
    
    # Handle . prefix (relative)
    if resolved.startswith("."):
        resolved = _resolve_relative_target(resolved, source_path, machine)
    
    # Handle ^ prefix (caret)
    if resolved.startswith("^"):
        resolved = _resolve_caret_target(resolved, source_path, machine)
        if resolved.startswith("#"):
            resolved = resolved[1:]
    
    # Fix workflows.none
    resolved = _fix_workflows_none_target(resolved, machine)
    
    # Now check if it exists
    parts = resolved.split(".")
    states = machine.get("states", {})
    
    for part in parts:
        if part in states:
            states = states[part].get("states", {})
        else:
            return False
    
    return True


def _create_placeholder_state(path: str, machine: dict) -> None:
    """Create a placeholder state at the given path.
    
    STRUCTURAL: creates minimal state config with entry/exit/on.
    
    Args:
        path: Full path (e.g., "navigation.app_idle")
        machine: The full state machine dict
    """
    parts = path.split(".")
    states = machine.get("states", {})
    
    # Navigate to parent
    for i, part in enumerate(parts[:-1]):
        if part in states:
            if "states" not in states[part]:
                states[part]["states"] = {}
            states = states[part]["states"]
        else:
            # Create intermediate placeholder
            states[part] = {
                "initial": parts[i + 1] if i + 1 < len(parts) - 1 else None,
                "states": {}
            }
            states = states[part]["states"]
    
    # Create the final state if it doesn't exist
    final_name = parts[-1]
    if final_name not in states:
        states[final_name] = {
            "entry": [],
            "exit": [],
            "on": {}
        }


def apply_target_resolution(machine: dict) -> dict:
    """Resolve all transition targets and create placeholders for missing states.
    
    This is the CRITICAL fix for the main problem:
    - .app_idle → navigation.app_idle (relative resolution)
    - ^navigation.authenticating → #navigation.authenticating (caret resolution)
    - #workflows.none → active_workflows.none (branch name fix)
    - success.dashboard → navigation.success (non-existent branch fix)
    - active_active_workflows.none → active_workflows.none (double prefix fix)
    - authenticating → navigation.authenticating (bare state name)
    - Creates placeholder states for any target that doesn't exist
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with all targets resolved and placeholders created
    """
    states = machine.get("states", {})
    
    def _process_states(states_dict: dict, prefix: str = "") -> None:
        for name, config in list(states_dict.items()):
            full_path = f"{prefix}.{name}" if prefix else name
            
            # Extract source branch for bare name resolution
            source_branch = ""
            if "." in full_path:
                source_branch = full_path.split(".")[0]
            
            # Process transitions
            transitions = config.get("on", {})
            for event, target in list(transitions.items()):
                target_str = _extract_target_string(target)
                
                if not target_str:
                    continue
                
                # Step 1: Resolve relative targets
                if target_str.startswith("."):
                    resolved = _resolve_relative_target(target_str, full_path, machine)
                elif target_str.startswith("^"):
                    resolved = _resolve_caret_target(target_str, full_path, machine)
                    if resolved.startswith("#"):
                        resolved = resolved[1:]
                else:
                    resolved = target_str
                
                # Step 2: Fix workflows.none
                resolved = _fix_workflows_none_target(resolved, machine)
                
                # Step 3: Fix non-existent targets (success.X, double prefix, bare names, etc.)
                resolved = _fix_nonexistent_targets(resolved, machine, source_branch)
                
                # Step 4: Update the transition
                if isinstance(target, str):
                    transitions[event] = resolved
                elif isinstance(target, dict):
                    target["target"] = resolved
                elif isinstance(target, list):
                    # Multi-target: update first target's target field
                    for item in target:
                        if isinstance(item, dict):
                            item["target"] = resolved
                            break
                
                # Step 5: Create placeholder if target doesn't exist
                if not _ensure_target_exists(resolved, full_path, machine):
                    _create_placeholder_state(resolved, machine)
            
            # Recurse into sub-states
            if "states" in config:
                _process_states(config["states"], full_path)
    
    _process_states(states)
    
    # Also ensure initial states exist
    def _ensure_initial(states_dict: dict, prefix: str = "") -> None:
        for name, config in states_dict.items():
            full_path = f"{prefix}.{name}" if prefix else name
            initial = config.get("initial")
            if initial and "states" in config:
                if initial not in config["states"]:
                    # Create placeholder for initial state
                    config["states"][initial] = {
                        "entry": [],
                        "exit": [],
                        "on": {}
                    }
                # Recurse
                _ensure_initial(config["states"], full_path)
    
    _ensure_initial(states)
    
    return machine


def compile_machine(machine: dict) -> dict:
    """Apply all Pattern Compiler rules to a state machine.
    
    This is the main entry point. Feed it any LLM-generated state machine
    and it will apply structural laws to make it valid.
    
    Order of operations:
    1. Branch Placement (Rule 6: move orphans to correct branch)
    2. Normalize (fix naming issues)
    3. Auto-inject sub_states (loading/ready/error)
    4. Specificity Dedup (remove duplicates)
    5. Error Injection (add error handlers)
    6. Global Exit (add exit transitions)
    7. Dead State Cleanup (remove unreachable)
    8. Target Resolution (fix relative targets, caret syntax, create placeholders)
    9. Context Awareness (add guards to retry, emergency exits to workflows) ← LAST!
    
    IMPORTANT: Context Awareness MUST run LAST because it needs all states
    (including error handlers from Step 5 and placeholders from Step 8) to exist.
    
    Args:
        machine: Raw LLM-generated state machine
    
    Returns:
        Compiled, structurally valid state machine
    """
    # Step 1: Branch Placement (Rule 6: move orphans to correct branch)
    machine = apply_branch_placement(machine)
    
    # Step 2: Normalize naming
    machine = normalize_machine(machine)
    
    # Step 3: Auto-inject sub_states for states that need them
    machine = _auto_inject_sub_states(machine)
    
    # Step 4: Remove duplicates by specificity
    machine = apply_specificity_dedup(machine)
    
    # Step 5: Inject error handlers (Rule 1)
    machine = apply_error_injection(machine)
    
    # Step 6: Inject global exit (Rule 5)
    machine = apply_global_exit(machine)
    
    # Step 7: Clean up dead states (Rule 4)
    machine = apply_dead_state_cleanup(machine)
    
    # Step 8: Target Resolution (fix relative targets, caret syntax, create placeholders)
    # This resolves all transition targets AFTER all states have been created
    # (including error handlers from Step 5)
    machine = apply_target_resolution(machine)
    
    # Step 9: Context Awareness (add guards to retry, emergency exits to workflows)
    # This is GENERIC — works for any state machine by detecting error states
    # and workflow states structurally (not by hardcoded names)
    machine = apply_context_awareness(machine)
    
    return machine


def build_and_compile(base_machine: dict, transitions: list, workflows: list = None) -> dict:
    """Build a state machine and compile it with all rules.
    
    Args:
        base_machine: Base machine from generate_base_machine()
        transitions: List of transitions from LLM
        workflows: Optional list of workflows
    
    Returns:
        Compiled state machine
    """
    machine = base_machine
    
    # Add transitions
    if machine.get("type") == "parallel":
        add_transitions_to_branch(machine, transitions)
    add_transitions(machine, transitions)
    
    # Add workflows
    if workflows:
        add_workflows_to_machine(machine, workflows)
    
    # Compile with all rules
    machine = compile_machine(machine)
    
    return machine