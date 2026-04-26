"""State injection utilities for state machines.

Error handlers, global exit, auto-inject sub_states (loading/ready/error).
"""

from state_machine.constants import (
    AUTO_GENERATED_SUB_STATES, DEPTH_LIMITS, VERB_PATTERNS,
)
from state_machine.traversal import extract_target_string


def _find_first_valid_screen_state(machine: dict) -> str:
    """Find the first valid screen state in the machine.
    
    GENERIC FALLBACK: Instead of hardcoding 'app_initial' or 'navigation.app_initial',
    this dynamically finds the first state that looks like a screen/entry point.
    
    Search order:
    1. States in 'navigation' branch (if exists)
    2. States in first branch that has sub-states
    3. Root-level states that look like screens (dashboard, catalog, offers, alerts, etc.)
    4. Any root-level state with sub-states or entry actions
    5. First root-level state
    
    Args:
        machine: The state machine dict
    
    Returns:
        Absolute path to a valid screen state
    """
    states = machine.get("states", {})
    
    # 1. Try navigation branch first
    nav = states.get("navigation", {})
    nav_states = nav.get("states", {})
    if nav_states:
        nav_initial = nav.get("initial")
        if nav_initial and nav_initial in nav_states:
            return f"navigation.{nav_initial}"
        # Return first state in navigation
        first = next(iter(nav_states))
        return f"navigation.{first}"
    
    # 2. Try to find any branch with sub-states
    for branch_name, branch_config in states.items():
        if branch_name in ("workflows", "active_workflows"):
            continue  # Skip workflow branches
        if isinstance(branch_config, dict):
            branch_states = branch_config.get("states", {})
            if branch_states:
                branch_initial = branch_config.get("initial")
                if branch_initial and branch_initial in branch_states:
                    return f"{branch_name}.{branch_initial}"
                first = next(iter(branch_states))
                return f"{branch_name}.{first}"
    
    # 3. Try root-level screen candidates
    screen_candidates = ["dashboard", "catalog", "offers", "alerts", "home", "main",
                         "app_initial", "app_idle", "app_loading", "app_success"]
    for candidate in screen_candidates:
        if candidate in states:
            return candidate
    
    # 4. Try any root-level state with sub-states or entry actions
    for name, config in states.items():
        if isinstance(config, dict):
            if config.get("states") or config.get("entry"):
                return name
    
    # 5. Last resort: first root-level state
    if states:
        return next(iter(states))
    
    # Absolute last resort
    return "dashboard"


def _find_exit_target_for_state(state_name: str, machine: dict = None) -> str:
    """Find the appropriate exit target for a state using STRUCTURAL analysis.
    
    FIX: When returning 'active_workflows.none' or 'workflows.none', verify
    the branch actually exists. If not, fall back to a valid screen state.
    
    Args:
        state_name: Full path of the state (e.g., "workflows.benchmark", "navigation.success")
        machine: Optional state machine dict for structural lookup
    
    Returns:
        Canonical exit target path
    """
    if state_name.startswith("workflows.") or state_name.startswith("active_workflows."):
        # Check if workflows branch actually exists
        if machine:
            states = machine.get("states", {})
            if "active_workflows" in states:
                return "active_workflows.none"
            if "workflows" in states:
                return "workflows.none"
        # No workflows branch — fall through to screen state
        if machine:
            return _find_first_valid_screen_state(machine)
        return "dashboard"
    
    if state_name.startswith("navigation."):
        if machine:
            nav = machine.get("states", {}).get("navigation", {})
            nav_states = nav.get("states", {})
            if nav_states:
                nav_initial = nav.get("initial")
                if nav_initial and nav_initial in nav_states:
                    return f"navigation.{nav_initial}"
                first = next(iter(nav_states))
                return f"navigation.{first}"
        # Navigation branch doesn't exist — use generic fallback
        if machine:
            return _find_first_valid_screen_state(machine)
        return "dashboard"
    
    if any(kw in state_name.lower() for kw in ["workflow", "benchmark", "purchase", "alert", "group"]):
        if machine:
            states = machine.get("states", {})
            if "active_workflows" in states:
                return "active_workflows.none"
            if "workflows" in states:
                return "workflows.none"
        # No workflows branch — use screen state
        if machine:
            return _find_first_valid_screen_state(machine)
        return "dashboard"
    
    # GENERIC FALLBACK: Use _find_first_valid_screen_state instead of hardcoded app_initial
    if machine:
        return _find_first_valid_screen_state(machine)
    return "dashboard"


def _infer_sub_state_name(action_name: str) -> str:
    """Infer the sub_state name from an action name using linguistic patterns.
    
    Universal approach: analyzes the VERB prefix of the action name to determine
    what kind of operation is happening, then maps to an appropriate sub_state name.
    
    Examples:
    - calculateCluster → calculating (verb: calculate)
    - fetchGroupsData → fetching (verb: fetch)
    - submitGroup → submitting (verb: submit)
    
    Args:
        action_name: A single action string (e.g., "calculateCluster", "fetchGroups")
    
    Returns:
        The inferred sub_state name (e.g., 'calculating', 'fetching', 'loading')
    """
    if not action_name:
        return "loading"
    
    lower = action_name.lower()
    best_match = "loading"
    best_length = 0
    
    for verb, gerund in VERB_PATTERNS:
        if lower.startswith(verb) or verb in lower:
            if len(verb) > best_length:
                best_length = len(verb)
                best_match = gerund
    
    return best_match


def _find_emergency_exit_target(machine: dict) -> str:
    """Find the appropriate emergency exit target for a state machine.
    
    Instead of hardcoding '#navigation.app_idle', this dynamically finds
    the initial state of the navigation branch (or first branch if no navigation).
    
    VALIDATION: Verifies the target state actually exists in the machine
    to prevent broken references (e.g., GLOBAL_EXIT pointing to non-existent state).
    
    GENERIC: Uses _find_first_valid_screen_state as ultimate fallback.
    
    Args:
        machine: The state machine dict
    
    Returns:
        The canonical path to use as emergency exit target (e.g., '#navigation.app_idle')
    """
    states = machine.get("states", {})
    
    nav = states.get("navigation", {})
    nav_initial = nav.get("initial")
    if nav_initial:
        # Validate: does the target state actually exist?
        nav_states = nav.get("states", {})
        if nav_initial in nav_states:
            return f"#navigation.{nav_initial}"
        # Fallback: try to find any valid initial in navigation states
        for state_name, state_config in nav_states.items():
            if state_config.get("entry") is not None or state_config.get("on") is not None:
                return f"#navigation.{state_name}"
    
    for branch_name, branch_config in states.items():
        if branch_name in ("navigation", "workflows", "active_workflows"):
            continue
        branch_initial = branch_config.get("initial")
        if branch_initial:
            branch_states = branch_config.get("states", {})
            if branch_initial in branch_states:
                return f"#{branch_name}.{branch_initial}"
    
    seq_initial = machine.get("initial")
    if seq_initial:
        return seq_initial
    
    # Last resort: find any state in the machine that could serve as entry point
    for branch_name, branch_config in states.items():
        branch_states = branch_config.get("states", {})
        if branch_states:
            # Try to find the initial state of this branch
            branch_initial = branch_config.get("initial")
            if branch_initial and branch_initial in branch_states:
                return f"#{branch_name}.{branch_initial}"
            # Otherwise return the first state in this branch
            first_state = next(iter(branch_states))
            return f"#{branch_name}.{first_state}"
    
    # Absolute last resort: return the machine-level initial
    seq_initial = machine.get("initial")
    if seq_initial:
        return seq_initial
    
    # GENERIC FALLBACK: Use _find_first_valid_screen_state instead of hardcoding 'app_initial'
    screen_state = _find_first_valid_screen_state(machine)
    # Add '#' prefix if it's a path (contains '.')
    if "." in screen_state:
        return f"#{screen_state}"
    return screen_state


def apply_initial_enforcer(machine: dict) -> dict:
    """Ensure EVERY compound state has an 'initial' property.
    
    This is the FINAL enforcer that runs after all injections.
    If a state has sub-states but no 'initial', it sets 'initial' to:
    - 'loading' if present
    - 'error_handler' if present (and no loading)
    - Otherwise, the first sub-state alphabetically
    
    EMERGENCY INITIAL HOOK: This function now also validates that the 'initial'
    property points to an ACTUAL child state. If the target doesn't exist,
    it falls back to the first available child.
    
    This prevents the "Frozen State" problem: XState cannot enter a compound
    state without knowing which sub-state to activate first.
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with all compound states having valid 'initial'
    """
    states = machine.get("states", {})
    
    def _enforce(states_dict: dict, depth: int = 0) -> None:
        if depth > 15:
            return
        
        for name, config in states_dict.items():
            sub_states = config.get("states", {})
            if sub_states:
                # EMERGENCY INITIAL HOOK: Ensure 'initial' exists AND is valid
                current_initial = config.get("initial")
                
                if not current_initial or current_initial not in sub_states:
                    # Prefer 'loading' if it exists, then 'error_handler', then first
                    if "loading" in sub_states:
                        config["initial"] = "loading"
                    elif "error_handler" in sub_states:
                        config["initial"] = "error_handler"
                    else:
                        config["initial"] = next(iter(sub_states))
                
                # Recurse into nested states
                _enforce(sub_states, depth + 1)
    
    _enforce(states)
    return machine


def apply_placeholder_flattening(machine: dict) -> dict:
    """Force-flatten placeholder states that add no value.
    
    LAMA AFFILATA FIX #2: If a state is just a wrapper (has children but no
    entry/exit actions and no direct transitions), collapse it by moving
    its children up one level.
    
    Examples of states to flatten:
    - 'none' with only sub_states and no entry/on
    - 'app_initial' that just wraps 'loading'
    - 'app_success' that just wraps 'ready'
    
    IMPORTANT: Branch states (first-level children of machine['states']) are
    NEVER flattened, even if they look like placeholders.
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with placeholder states flattened
    """
    states = machine.get("states", {})
    
    def _flatten(states_dict: dict, prefix: str = "", depth: int = 0, is_branch_level: bool = False) -> None:
        if depth > 10:
            return
        
        for name, config in list(states_dict.items()):
            full_path = f"{prefix}.{name}" if prefix else name
            sub_states = config.get("states", {})
            
            if not sub_states:
                continue
            
            # BRANCH PROTECTION: Never flatten first-level branch states
            if is_branch_level:
                _flatten(sub_states, full_path, depth + 1, is_branch_level=False)
                continue
            
            # Check if this is a "placeholder" state:
            # - Has sub_states
            # - No entry actions (or only generic ones)
            # - No direct transitions (on is empty or only has GLOBAL_EXIT)
            entry = config.get("entry", [])
            on = config.get("on", {})
            
            is_placeholder = (
                len(entry) == 0 and
                len(on) == 0 and
                len(sub_states) > 0
            )
            
            if is_placeholder:
                # FLATTEN: Move children up, preserve the initial
                child_initial = config.get("initial")
                
                # Merge children into parent
                for child_name, child_config in sub_states.items():
                    if child_name not in states_dict:
                        states_dict[child_name] = child_config
                
                # Update initial to point to child's initial if it had one
                if child_initial and child_initial in sub_states:
                    child_config = sub_states[child_initial]
                    if "states" in child_config:
                        child_child_initial = child_config.get("initial")
                        if child_child_initial:
                            config["initial"] = child_child_initial
                        else:
                            config["initial"] = child_initial
                
                # Remove the placeholder's own states (children are now at parent level)
                del config["states"]
                if "initial" in config:
                    del config["initial"]
            
            # Recurse into remaining sub_states
            if "states" in config:
                _flatten(config["states"], full_path, depth + 1, is_branch_level=False)
    
    # First level is always branch level - protect it
    _flatten(states, is_branch_level=True)
    return machine


def apply_id_injection(machine: dict) -> dict:
    """Inject explicit 'id' property into every state using its full path.
    
    CRITICAL FIX for XState '#id' references:
    In XState, the '#' prefix in transitions (e.g., '#navigation.app_idle') 
    looks for an EXPLICIT 'id' property, NOT a path. Without this injection,
    GLOBAL_EXIT and other '#' references point to nothing.
    
    Example transformation:
        states["navigation"]["states"]["app_idle"] = {
            "entry": [...],
            "on": {...}
        }
    Becomes:
        states["navigation"]["states"]["app_idle"] = {
            "id": "navigation.app_idle",  ← INJECTED
            "entry": [...],
            "on": {...}
        }
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with explicit IDs on every state
    """
    states = machine.get("states", {})
    limit = DEPTH_LIMITS["process_states"]
    
    def _inject_ids(states_dict: dict, prefix: str = "", depth: int = 0) -> None:
        if depth > limit:
            return
        
        for name, config in states_dict.items():
            full_path = f"{prefix}.{name}" if prefix else name
            
            # Inject explicit ID = full path (this is what '#' references look for)
            config["id"] = full_path
            
            # Recurse into nested states
            sub_states = config.get("states", {})
            if sub_states:
                _inject_ids(sub_states, full_path, depth + 1)
    
    _inject_ids(states)
    
    # Also set ID on the machine root if not present
    if "id" not in machine:
        machine["id"] = "appFlow"
    
    return machine


def _has_error_handler_in_descendants(states_dict: dict) -> bool:
    """Check if any descendant state already has an error_handler.
    
    Prevents the 'Inception' problem: injecting error_handler inside
    another error_handler creates infinite nesting (e.g., navigation.catalog.error.error_handler.error_handler).
    
    Args:
        states_dict: The states dict to check
    
    Returns:
        True if any descendant has an error_handler sub-state
    """
    for name, config in states_dict.items():
        if name == "error_handler":
            return True
        sub_states = config.get("states", {})
        if sub_states and _has_error_handler_in_descendants(sub_states):
            return True
    return False


def apply_error_injection(machine: dict) -> dict:
    """Inject error handlers into states that need them.
    
    For each state with entry actions or transitions, ensure there's an
    error_handler sub-state with RETRY and CANCEL transitions.
    
    ANTI-INCEPTION: Skips states that already have error_handler descendants
    to prevent infinite nesting (e.g., error.error_handler.error_handler).
    
    DEPTH LIMIT: Uses DEPTH_LIMITS["inject_sub_states"] to prevent fractal
    nesting where error_handler creates states that trigger another round of
    error injection, creating paths like:
    group_confirming.error.error.group_confirming.error... (15+ levels)
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with error handlers injected
    """
    states = machine.get("states", {})
    # FIX A: Use inject_sub_states limit (3) instead of process_states (15)
    # to prevent fractal nesting in error injection
    limit = DEPTH_LIMITS["inject_sub_states"]
    
    def _inject_recursive(states_dict: dict, prefix: str = "", depth: int = 0) -> None:
        if depth > limit:
            return
        
        for name, config in list(states_dict.items()):
            full_path = f"{prefix}.{name}" if prefix else name
            
            sub_states = config.get("states", {})
            
            # ANTI-INCEPTION: If this state already has error_handler descendants,
            # skip it entirely — don't inject another error_handler on top
            if sub_states and _has_error_handler_in_descendants(sub_states):
                continue
            
            entry_actions = config.get("entry", [])
            transitions = config.get("on", {})
            needs_error = len(entry_actions) > 0 or len(transitions) > 0
            
            if needs_error and not sub_states:
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
                if "on" not in config:
                    config["on"] = {}
                # CRITICAL: Compound states MUST define initial (XState Rule)
                # Without this, the state machine freezes — no sub-state is entered
                config["initial"] = "error_handler"
            elif sub_states:
                _inject_recursive(sub_states, full_path, depth + 1)
    
    _inject_recursive(states)
    return machine


def apply_global_exit(machine: dict) -> dict:
    """Add GLOBAL_EXIT transition to all top-level states.
    
    GLOBAL_EXIT → #navigation.{initial} allows any state to exit to home.
    
    ANTI-SELF-REFERENCE: If a state's ID matches the emergency target,
    skip adding GLOBAL_EXIT to prevent infinite loops.
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with global exit transitions
    """
    emergency_target = _find_emergency_exit_target(machine)
    states = machine.get("states", {})
    
    # Extract the actual target path (without # prefix) for comparison
    target_path = emergency_target.lstrip("#")
    
    for branch_name, branch_config in states.items():
        branch_states = branch_config.get("states", {})
        for state_name, state_config in branch_states.items():
            # ANTI-SELF-REFERENCE: Don't add GLOBAL_EXIT if this state IS the target
            state_id = state_config.get("id", f"{branch_name}.{state_name}")
            if state_id == target_path:
                continue  # Skip — this state IS the emergency target
            
            transitions = state_config.get("on", {})
            if "GLOBAL_EXIT" not in transitions:
                transitions["GLOBAL_EXIT"] = emergency_target
    
    return machine


def _add_emergency_exits(states_dict: dict, machine: dict, parent_name: str = "", depth: int = 0) -> None:
    """Add emergency exit transitions for states that don't have a way back.
    
    If a state has entry actions but NO transitions that lead back to the main flow,
    add a default GO_BACK → [initial state] transition.
    
    This prevents the "Ghost Ship" problem where states exist but you can't leave them.
    
    Args:
        states_dict: The states dict to process
        machine: The full state machine (used to find emergency exit target)
        parent_name: Current path prefix
        depth: Current recursion depth (safety limit)
    """
    limit = DEPTH_LIMITS["process_states"]
    if depth > limit:
        return

    emergency_target = _find_emergency_exit_target(machine)

    for name, config in states_dict.items():
        full_name = f"{parent_name}.{name}" if parent_name else name

        if name in AUTO_GENERATED_SUB_STATES:
            continue

        transitions = config.get("on", {})
        sub_states = config.get("states", {})

        has_exit = False
        for event, target in transitions.items():
            target_str = extract_target_string(target)
            if target_str and target_str != name and target_str != ".":
                has_exit = True
                break

        entry_actions = config.get("entry", [])
        if entry_actions and not has_exit and not sub_states:
            transitions["GO_BACK"] = emergency_target
            transitions["CANCEL"] = emergency_target

        if sub_states:
            _add_emergency_exits(sub_states, machine, full_name, depth + 1)


def _is_recursive_path(path: str) -> bool:
    """Check if a state path shows recursive/fractal patterns.
    
    ANTI-FRATTALE (Strict Path Unique Guard): Detects patterns like:
    - 'navigation.app_initial.app_initial.ready' (immediate repetition)
    - 'workflows.idle.price_alert_workflow.idle.price_alert_workflow' (alternating loops)
    - 'none.error.error_handler.none.error.error_handler' (semantic recursion)
    
    KEY INSIGHT: If a state name appears ANYWHERE in the ancestor chain,
    it's a recursive pattern — even if not consecutive.
    
    Args:
        path: Full state path (e.g., 'navigation.app_initial.app_initial.ready')
    
    Returns:
        True if the path contains recursive patterns
    """
    parts = path.split(".")
    if len(parts) < 2:
        return False
    
    # Skip the first part (branch name like 'navigation' or 'workflows')
    state_parts = parts[1:] if len(parts) > 1 else parts
    
    # Check for ANY duplicate in the state chain (not just consecutive)
    seen = set()
    for part in state_parts:
        if part in seen:
            return True  # Found a duplicate anywhere in the chain
        seen.add(part)
    
    # Check for alternating pattern (A-B-A-B) in last 4 segments
    if len(state_parts) >= 4:
        last_4 = state_parts[-4:]
        if last_4[0] == last_4[2] and last_4[1] == last_4[3]:
            return True
    
    # Check for 3-segment repetition (A-B-C-A) indicating a loop
    if len(state_parts) >= 4:
        last_4 = state_parts[-4:]
        if last_4[0] == last_4[3]:
            return True
    
    return False


def _contains_error_handler(path: str) -> bool:
    """Check if path already contains error_handler (prevent inception nesting).
    
    Args:
        path: Full state path
    
    Returns:
        True if 'error_handler' is in the path
    """
    return "error_handler" in path.split(".")


def auto_inject_sub_states(machine: dict) -> dict:
    """Auto-inject loading/ready/error sub_states for states that need them.
    
    This is called by compile_machine to ensure every meaningful state has
    the loading → ready → error pattern, even if the LLM didn't generate it.
    
    CONTEXT-AWARE: Instead of always using 'loading', reads entry_actions to
    determine specific names:
    - calculateCluster → 'calculating'
    - fetchGroupsData → 'fetching'
    - submitGroup → 'submitting'
    
    ANTI-FRATTALE GUARDS:
    1. Depth limit: max 3 levels of nesting (configurable via DEPTH_LIMITS)
    2. Recursive path detection: skips states with patterns like 'app_initial.app_initial'
    3. Error handler check: skips states already containing 'error_handler' in path
    4. Mandatory initial: every compound state gets 'initial' property
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with auto-injected sub_states
    """
    states = machine.get("states", {})
    limit = DEPTH_LIMITS["inject_sub_states"]
    
    def _inject_recursive(states_dict: dict, parent_name: str = "", depth: int = 0) -> None:
        if depth > limit:
            return
        
        for name, config in list(states_dict.items()):
            full_name = f"{parent_name}.{name}" if parent_name else name
            
            # ANTI-FRATTALE: Skip if path shows recursive patterns
            if _is_recursive_path(full_name):
                continue
            
            # ANTI-INCEPTION: Skip if already inside an error_handler
            if _contains_error_handler(full_name):
                continue
            
            if name in AUTO_GENERATED_SUB_STATES:
                continue
            
            # If this state already has sub_states, recurse into them
            if "states" in config and config["states"]:
                # MANDATORY INITIAL: Ensure compound states have 'initial'
                if "initial" not in config:
                    first_child = next(iter(config["states"]))
                    config["initial"] = first_child
                _inject_recursive(config["states"], full_name, depth + 1)
                continue
            
            entry_actions = config.get("entry", [])
            exit_actions = config.get("exit", [])
            transitions = config.get("on", {})
            
            needs_sub_states = (
                len(entry_actions) > 0 or
                len(transitions) > 0
            )
            
            if not needs_sub_states:
                continue
            
            first_action = entry_actions[0] if entry_actions else ""
            loading_name = _infer_sub_state_name(first_action)
            
            sub_states = {}
            
            sub_states[loading_name] = {
                "entry": ["showLoading", f"fetch{full_name.title().replace('.', '')}"],
                "exit": ["hideLoading"],
                "on": {
                    "DATA_LOADED": ".ready",
                    "LOAD_FAILED": ".error",
                    "TIMEOUT": ".error"
                }
            }
            
            # FIX: Copy transitions but update targets to be relative to ready sub-state
            # Original targets like "offers" are siblings at parent level, need to become ".offers"
            updated_transitions = {}
            for event, target in transitions.items():
                if isinstance(target, str) and not target.startswith(".") and not target.startswith("#"):
                    # Target is a sibling at parent level - make it relative
                    updated_transitions[event] = f".{target}"
                else:
                    updated_transitions[event] = target
            
            sub_states["ready"] = {
                "entry": list(entry_actions) if entry_actions else [f"show{full_name.title().replace('.', '')}"],
                "exit": list(exit_actions) if exit_actions else [f"hide{full_name.title().replace('.', '')}"],
                "on": updated_transitions
            }
            
            exit_target = _find_exit_target_for_state(full_name, machine)
            sub_states["error"] = {
                "entry": ["logError", "showErrorBanner"],
                "exit": ["hideErrorBanner"],
                "on": {
                    "RETRY": f".{loading_name}",
                    "CANCEL": f"#{exit_target}"
                }
            }
            
            # MANDATORY INITIAL: Set initial to the loading sub_state
            config["initial"] = loading_name
            config["states"] = sub_states
            config["on"] = {}
    
    _inject_recursive(states)
    _add_emergency_exits(states, machine)
    
    return machine
