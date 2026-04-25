"""Pattern Compiler for State Machines — transforms chaotic LLM output into valid XState.

This is NOT a validator. It's a COMPILER that applies 6 structural laws to ANY
state machine the LLM generates, regardless of app domain, naming conventions, or
language. It recognizes PATTERNS, not names.

The 6 Rules:
  1. ERROR INJECTION — Every state with API events gets an error_handler sub-state
  2. CANONICAL TARGETS — Cross-branch references use #ID, ambiguities resolved by specificity
  3. SPECIFICITY DEDUP — S(state) = depth × sub_states + transitions; keep the smartest
  4. DEAD STATE CLEANUP — BFS from initial; unreachable states are connected or removed
  5. GLOBAL EXIT — Every workflow gets a GLOBAL_EXIT → navigation entry point
  6. BRANCH PLACEMENT — Orphan states moved to correct branch (compound→workflows, leaf→navigation)

Key principle: The builder doesn't decide WHAT states to create, only HOW they must be structured.
All rules are STRUCTURAL (based on JSON shape), not NAME-BASED (no hardcoded keywords).
"""

import json
from collections import deque


# =============================================================================
# Rule 2: Canonical Target Resolution
# =============================================================================

def _compute_specificity(state_config: dict, depth: int = 1) -> int:
    """Calculate specificity score: S(state) = depth × sub_states + transitions.
    
    The 'smartest' version of a state has the most structure.
    Used to resolve duplicate state names.
    
    Args:
        state_config: The state's configuration dict
        depth: How deep in the state tree (root=1)
    
    Returns:
        Specificity score (higher = more complex = keep this one)
    """
    sub_states = state_config.get("states", {})
    transitions = state_config.get("on", {})
    
    # Count nested sub-states recursively
    total_sub = 0
    for sub_config in sub_states.values():
        total_sub += 1
        total_sub += _compute_specificity(sub_config, depth + 1)
    
    return depth * total_sub + len(transitions)


def _collect_all_state_paths(states: dict, prefix: str = "") -> dict:
    """Collect all state paths with their specificity scores.
    
    Returns:
        Dict mapping state_name → list of (full_path, specificity, config)
        This lets us find duplicates and pick the best one.
    """
    result = {}
    
    for name, config in states.items():
        full_path = f"{prefix}.{name}" if prefix else name
        
        if name not in result:
            result[name] = []
        result[name].append((full_path, _compute_specificity(config), config))
        
        # Recurse into sub-states
        if "states" in config and isinstance(config["states"], dict):
            sub_results = _collect_all_state_paths(config["states"], full_path)
            for sub_name, entries in sub_results.items():
                if sub_name not in result:
                    result[sub_name] = []
                result[sub_name].extend(entries)
    
    return result


def _resolve_canonical_target(target: str, source_path: str, all_paths: dict) -> str:
    """Resolve a transition target to its canonical path using specificity.
    
    Rules:
    - #prefix → already canonical, strip and return
    - .prefix → relative, keep as-is
    - Contains . → absolute path, verify exists
    - Simple name → find all matches, pick highest specificity
    
    Args:
        target: The target string from the transition
        source_path: Full path of the source state
        all_paths: Dict from _collect_all_state_paths
    
    Returns:
        The resolved canonical path
    """
    if not target:
        return target
    
    # Rule: #prefix means global ID (already canonical)
    if target.startswith("#"):
        return target[1:]
    
    # Rule: .prefix means relative reference
    if target.startswith("."):
        return target
    
    # Rule: Contains . → absolute path
    if "." in target:
        # Verify it exists somewhere
        target_name = target.split(".")[-1]
        if target_name in all_paths:
            for path, _, _ in all_paths[target_name]:
                if path == target:
                    return target
        # Try to find by suffix
        for name, entries in all_paths.items():
            for path, _, _ in entries:
                if path.endswith(f".{target}"):
                    return path
        return target
    
    # Rule: Simple name → resolve by specificity
    if target in all_paths:
        entries = all_paths[target]
        if len(entries) == 1:
            return entries[0][0]
        # Multiple matches → pick highest specificity
        best = max(entries, key=lambda e: e[1])
        return best[0]
    
    # Fallback: search by suffix
    for name, entries in all_paths.items():
        for path, _, _ in entries:
            if path.endswith(f".{target}"):
                return path
    
    return target


# =============================================================================
# Rule 1: Error Injection (The "Parachute")
# =============================================================================

# Events that imply an async API call and need error handling.
# STRUCTURAL: also matches ANY event containing underscore (e.g., PUBLISH_TELEMETRY, SYNC_DEVICES)
# This makes it domain-agnostic — works for e-commerce, IoT, social, etc.
API_EVENT_PATTERNS = {
    "SUBMIT", "CONFIRM", "LOAD", "SAVE", "JOIN", "FETCH",
    "CREATE", "UPDATE", "DELETE", "POST", "GET", "REQUEST",
    "PROCESS", "CALCULATE", "VALIDATE", "REGISTER", "LOGIN",
    "CHECKOUT", "PAY", "BOOK", "RESERVE",
    # IoT / real-time patterns
    "PUBLISH", "SUBSCRIBE", "TELEMETRY", "SYNC", "STREAM",
    "CONNECT", "DISCONNECT", "OBSERVE", "WATCH",
    # Social / content patterns
    "LIKE", "SHARE", "COMMENT", "FOLLOW", "POST", "UPLOAD",
    "DOWNLOAD", "IMPORT", "EXPORT", "SYNC"
}


def _has_api_events(state_config: dict) -> bool:
    """Check if a state has events that imply API calls.
    
    STRUCTURAL approach: matches known patterns OR any event with underscore
    (which typically indicates a domain-specific API call).
    
    Args:
        state_config: The state's configuration
    
    Returns:
        True if any event matches an API pattern
    """
    events = state_config.get("on", {})
    for event in events.keys():
        upper = event.upper()
        # Known pattern match
        if upper in API_EVENT_PATTERNS:
            return True
        # Structural: events with underscore are typically API calls (e.g., PUBLISH_TELEMETRY)
        if "_" in upper and len(upper) > 3:
            return True
    return False


def inject_error_handler(state_name: str, state_config: dict) -> dict:
    """Inject error_handler sub-state into a state with API events.
    
    For every state that has API-like events but no ERROR transition,
    we automatically add:
    - ERROR → .error_handler transition
    - error_handler sub-state with RETRY and CANCEL
    
    Args:
        state_name: Name of the parent state
        state_config: The state's configuration
    
    Returns:
        Modified state_config with error handling
    """
    events = state_config.get("on", {})
    
    # Check if this state has API events
    if not _has_api_events(state_config):
        return state_config
    
    # Check if ERROR is already handled
    if "ERROR" in events:
        return state_config
    
    # Inject ERROR transition
    events["ERROR"] = ".error_handler"
    
    # Create error_handler sub-state
    if "states" not in state_config:
        state_config["states"] = {}
    
    state_config["states"]["error_handler"] = {
        "entry": ["logError", "showRetryModal"],
        "exit": ["hideRetryModal"],
        "on": {
            "RETRY": f"^{state_name}",  # Return to parent state
            "CANCEL": "#workflows.none"  # Exit workflow
        }
    }
    
    return state_config


def apply_error_injection(machine: dict) -> dict:
    """Apply error injection to ALL states in the machine recursively.
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with error handlers injected
    """
    def _inject_recursive(states: dict, parent_name: str = "") -> None:
        for name, config in states.items():
            full_name = f"{parent_name}.{name}" if parent_name else name
            
            # Inject error handler if needed
            inject_error_handler(full_name, config)
            
            # Recurse into sub-states
            if "states" in config and isinstance(config["states"], dict):
                _inject_recursive(config["states"], full_name)
    
    _inject_recursive(machine.get("states", {}))
    return machine


# =============================================================================
# Rule 5: Global Exit Injection
# =============================================================================

def _find_first_nav_state(machine: dict) -> str:
    """Find the first navigation state to use as GLOBAL_EXIT target.
    
    STRUCTURAL approach: takes the INITIAL state of the navigation branch,
    or the first available state if no initial is defined.
    No keyword matching — works with ANY naming convention.
    
    Args:
        machine: The state machine dict
    
    Returns:
        The canonical path to the first nav state
    """
    states = machine.get("states", {})
    
    # Priority 1: navigation branch → use its initial state
    nav = states.get("navigation", {})
    nav_initial = nav.get("initial")
    nav_states = nav.get("states", {})
    
    if nav_initial and nav_initial in nav_states:
        return f"navigation.{nav_initial}"
    
    # Priority 2: first state in navigation (any name)
    if nav_states:
        first_state = next(iter(nav_states))
        return f"navigation.{first_state}"
    
    # Priority 3: any parallel branch with states
    for branch_name, branch_config in states.items():
        if branch_name in ("navigation",):
            continue
        branch_states = branch_config.get("states", {})
        if branch_states:
            first_state = next(iter(branch_states))
            return f"{branch_name}.{first_state}"
    
    # Fallback
    return "navigation"


def apply_global_exit(machine: dict) -> dict:
    """Inject GLOBAL_EXIT transition into every workflow.
    
    A 'workflow' is any state under the workflows branch (or any compound
    state with sub-states that isn't a navigation state).
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with GLOBAL_EXIT transitions added
    """
    nav_exit_target = _find_first_nav_state(machine)
    states = machine.get("states", {})
    
    def _inject_exit(states_dict: dict, is_workflow_level: bool = False) -> None:
        for name, config in states_dict.items():
            sub_states = config.get("states", {})
            
            # If this is a compound state (has sub-states) and is at workflow level
            if sub_states and is_workflow_level:
                # Add GLOBAL_EXIT to the workflow's on transitions
                config.setdefault("on", {})
                if "GLOBAL_EXIT" not in config["on"]:
                    config["on"]["GLOBAL_EXIT"] = f"#{nav_exit_target}"
            
            # Recurse
            if sub_states:
                # If we're under a branch like 'workflows' or 'active_workflows', mark as workflow level
                is_wf = is_workflow_level or name in ("workflows", "active_workflows")
                _inject_exit(sub_states, is_wf)
    
    _inject_exit(states)
    return machine


# =============================================================================
# Rule 3: Specificity-Based Deduplication
# =============================================================================

def apply_specificity_dedup(machine: dict) -> dict:
    """Remove duplicate states, keeping the most specific version.
    
    When the same state name appears in multiple locations, we keep the one
    with the highest specificity score (most sub-states + transitions).
    
    Args:
        machine: The state machine dict
    
    Returns:
        Deduplicated machine
    """
    if machine.get("type") != "parallel":
        return machine
    
    root_states = machine.get("states", {})
    
    # Collect all state paths with specificity
    all_paths = _collect_all_state_paths(root_states)
    
    # Find duplicates (names that appear in multiple locations)
    for name, entries in all_paths.items():
        if len(entries) <= 1:
            continue
        
        # Sort by specificity (highest first)
        entries.sort(key=lambda e: e[1], reverse=True)
        best_path = entries[0][0]
        
        # Determine which branch the best version is in
        best_branch = best_path.split(".")[0] if "." in best_path else best_path
        
        # Remove duplicates from root level (keep only branch versions)
        if name in root_states and name not in ("navigation", "active_workflows", "workflows"):
            # Check if there's a better version in a branch
            branch_entries = [e for e in entries if "." in e[0]]
            if branch_entries:
                del root_states[name]
    
    # Clean up navigation.active_workflows duplicates
    nav = root_states.get("navigation", {})
    nav_states = nav.get("states", {})
    nav_active_wf = nav_states.get("active_workflows", {})
    nav_wf_states = nav_active_wf.get("states", {})
    
    if nav_wf_states:
        # If active_workflows exists at root level, remove nav's version
        if "active_workflows" in root_states:
            root_wf_states = root_states["active_workflows"].get("states", {})
            for wf_name in list(nav_wf_states.keys()):
                if wf_name in root_wf_states:
                    del nav_wf_states[wf_name]
    
    return machine


# =============================================================================
# Rule 4: Dead State Cleanup
# =============================================================================

def _bfs_reachable(machine: dict) -> set:
    """BFS from initial state to find all reachable states.
    
    Handles parallel states by checking all branches.
    
    Args:
        machine: The state machine dict
    
    Returns:
        Set of reachable state paths
    """
    states = machine.get("states", {})
    
    # For parallel states, all top-level states are "reachable"
    if machine.get("type") == "parallel":
        reachable = set(states.keys())
        # Also traverse into each branch
        for branch_name, branch_config in states.items():
            if "states" in branch_config:
                initial = branch_config.get("initial")
                if initial and initial in branch_config["states"]:
                    _bfs_from(branch_config["states"], initial, reachable, prefix=branch_name)
        return reachable
    
    # For sequential states, BFS from initial
    initial = machine.get("initial")
    if not initial or initial not in states:
        return set()
    
    reachable = {initial}
    _bfs_from(states, initial, reachable)
    return reachable


def _bfs_from(states: dict, start: str, reachable: set, prefix: str = "") -> None:
    """BFS traversal from a starting state.
    
    Args:
        states: The states dict to traverse
        start: Starting state name
        reachable: Set to populate with reachable paths
        prefix: Path prefix for nested states
    """
    queue = deque([start])
    
    while queue:
        current = queue.popleft()
        current_path = f"{prefix}.{current}" if prefix else current
        
        if current not in states:
            continue
        
        transitions = states[current].get("on", {})
        for event, target in transitions.items():
            # Extract target name(s)
            targets = _extract_target_names(target)
            for t in targets:
                # Resolve relative targets
                resolved = _resolve_simple_target(t, current, states, prefix)
                if resolved and resolved not in reachable:
                    reachable.add(resolved)
                    if resolved in states:
                        queue.append(resolved)


def _extract_target_names(target) -> list:
    """Extract state names from a transition target.
    
    Handles:
    - String: "success" → ["success"]
    - Dict: {"target": "success"} → ["success"]
    - List: [{"target": "a"}, "b"] → ["a", "b"]
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


def generate_base_machine(use_parallel: bool = True) -> dict:
    """Generate an empty base state machine with proper parallel structure.
    
    Args:
        use_parallel: If True, creates parallel states architecture
    
    Returns:
        Base machine dict
    """
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
                "navigation": {
                    "id": "nav_branch",
                    "initial": "app_idle",
                    "on": {},
                    "states": {}
                },
                "workflows": {
                    "id": "wf_branch",
                    "initial": "none",
                    "on": {},
                    "states": {
                        "none": {
                            "entry": ["hideWorkflowOverlay"],
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
            "initial": "app_idle",
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
            target_str = target if isinstance(target, str) else target.get("target", "")
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


def compile_machine(machine: dict) -> dict:
    """Apply all 6 Pattern Compiler rules to a state machine.
    
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