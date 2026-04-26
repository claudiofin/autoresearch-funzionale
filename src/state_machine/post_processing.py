"""State machine post-processing.

Handles:
- Removing top-level duplicate states (when they exist as sub-states of 'success')
- Completing missing transition branches (both guard paths)
- Ensuring session_expired has REAUTHENTICATE transition
- Cleaning unreachable states and XState keywords
- Validating critical rules (15, 16, 17)

Supports both flat and parallel state machine architectures.
"""


def _get_states_for_processing(machine: dict) -> dict:
    """Get the states dict to process, handling both flat and parallel architectures.
    
    For parallel architecture, returns the navigation branch states.
    For flat architecture, returns the root states.
    
    Args:
        machine: The state machine dict.
    
    Returns:
        The states dict to process.
    """
    if machine.get("type") == "parallel" and "navigation" in machine.get("states", {}):
        return machine["states"]["navigation"].get("states", {})
    return machine.get("states", {})


# ---------------------------------------------------------------------------
# Post-Processing: Remove Top-Level Duplicate States
# ---------------------------------------------------------------------------

def remove_toplevel_duplicates(machine: dict) -> dict:
    """Remove states at root level if they already exist as sub-states of 'success'.
    
    The LLM sometimes creates both 'dashboard' (top-level) and 'success.dashboard' (sub-state).
    This function removes the top-level duplicates to prevent state machine conflicts.
    
    Args:
        machine: The state machine dict to fix.
    
    Returns:
        Fixed machine dict.
    """
    states = _get_states_for_processing(machine)
    success_sub_states = states.get("success", {}).get("states", {})
    
    if not success_sub_states:
        return machine  # No sub-states in success, nothing to do
    
    root_keys_to_delete = []
    for root_state in states.keys():
        if root_state in success_sub_states and root_state != "success":
            root_keys_to_delete.append(root_state)
    
    for key in root_keys_to_delete:
        print(f"  🧹 Removed top-level duplicate state: '{key}'")
        del states[key]
    
    return machine


# ---------------------------------------------------------------------------
# Post-Processing: Complete Missing Transition Branches
# ---------------------------------------------------------------------------

def complete_missing_branches(machine: dict) -> dict:
    """Ensure every conditional event has BOTH positive and negative branches.
    
    The LLM often generates only the negative branch (e.g., "!hasData" → empty)
    but forgets the positive branch (e.g., "hasData" → success). This function
    detects missing branches and adds them automatically.
    
    Supports both flat and parallel architectures.
    
    Args:
        machine: The state machine dict to fix.
    
    Returns:
        Fixed machine dict.
    """
    # Define expected branch pairs for known conditional events
    BRANCH_RULES = {
        "ON_SUCCESS": {
            "positive_guard": "hasData",
            "positive_target": "success",
            "negative_guard": "!hasData",
            "negative_target": "empty",
        },
        "CANCEL": {
            "positive_guard": "hasPreviousState",
            "positive_target": "success",
            "negative_guard": "!hasPreviousState",
            "negative_target": "app_idle",
        },
        "RETRY_FETCH": {
            "positive_guard": "canRetry",
            "positive_target": "loading",
            "negative_guard": "!canRetry",
            "negative_target": "session_expired",
        },
    }
    
    all_states = _get_states_for_processing(machine)
    fixed_count = 0
    
    for state_name, state_config in all_states.items():
        on_events = state_config.get("on", {})
        
        for event_name, rule in BRANCH_RULES.items():
            if event_name not in on_events:
                continue
            
            # Get existing transition(s) for this event
            existing = on_events[event_name]
            
            # Normalize to list of transitions
            if isinstance(existing, str):
                # Simple transition without guard - skip (no conditional)
                continue
            elif isinstance(existing, dict):
                existing_list = [existing]
            elif isinstance(existing, list):
                existing_list = existing
            else:
                continue
            
            # Check which guards exist
            existing_guards = set()
            for t in existing_list:
                if isinstance(t, dict):
                    guard = t.get("cond", "") or t.get("guard", "")
                    if guard:
                        existing_guards.add(guard)
            
            # Check if positive branch is missing
            if rule["positive_guard"] not in existing_guards:
                # Add positive branch
                if isinstance(existing, dict):
                    # Convert single transition to list
                    on_events[event_name] = [existing]
                    existing_list = on_events[event_name]
                elif isinstance(existing, str):
                    on_events[event_name] = [
                        {"target": existing},
                        {"target": rule["positive_target"], "cond": rule["positive_guard"]}
                    ]
                    fixed_count += 1
                    continue
                
                on_events[event_name].append({
                    "target": rule["positive_target"],
                    "cond": rule["positive_guard"]
                })
                fixed_count += 1
                print(f"  🔧 Added missing positive branch: {state_name} --{event_name}[{rule['positive_guard']}]-> {rule['positive_target']}")
            
            # Check if negative branch is missing
            if rule["negative_guard"] not in existing_guards:
                if isinstance(on_events[event_name], dict):
                    on_events[event_name] = [on_events[event_name]]
                
                on_events[event_name].append({
                    "target": rule["negative_target"],
                    "cond": rule["negative_guard"]
                })
                fixed_count += 1
                print(f"  🔧 Added missing negative branch: {state_name} --{event_name}[{rule['negative_guard']}]-> {rule['negative_target']}")
    
    # FIX: Ensure session_expired is not a dead-end state
    if "session_expired" in all_states:
        se_config = all_states["session_expired"]
        if "on" not in se_config:
            se_config["on"] = {}
        if "REAUTHENTICATE" not in se_config["on"]:
            print("  🔧 Added REAUTHENTICATE → authenticating transition to 'session_expired'")
            se_config["on"]["REAUTHENTICATE"] = "authenticating"
    
    if fixed_count > 0:
        print(f"  ✅ Fixed {fixed_count} missing transition branches")
    
    return machine


# ---------------------------------------------------------------------------
# Post-Processing: Clean Unreachable States
# ---------------------------------------------------------------------------

def clean_unreachable_states(machine: dict) -> dict:
    """Remove unreachable states and XState keywords used as state names.
    
    The LLM sometimes generates states like 'initial' (which is an XState keyword)
    or states that have no path from the initial state. This function cleans them up.
    
    Supports both flat and parallel architectures.
    
    For parallel architecture, ALL top-level navigation states are considered
    "potentially reachable" since they represent app screens that can be reached
    via events from other parts of the application. Only XState keywords are removed.
    
    Args:
        machine: The state machine dict to clean.
    
    Returns:
        Cleaned machine dict.
    """
    # XState reserved keywords that should never be state names
    XSTATE_KEYWORDS = {"initial", "states", "on", "entry", "exit", "context", "id", "type", "invoke", "activities"}
    
    # For parallel architecture, only clean XState keywords from navigation branch
    # Don't remove "unreachable" states since all navigation states are valid screens
    if machine.get("type") == "parallel" and "navigation" in machine.get("states", {}):
        nav_states = machine["states"]["navigation"].get("states", {})
        
        # Only remove XState keyword states
        for keyword in XSTATE_KEYWORDS:
            if keyword in nav_states:
                print(f"  🧹 Removing XState keyword state: '{keyword}'")
                del nav_states[keyword]
        
        return machine
    
    # For flat architecture, do full unreachable detection
    initial_state = machine.get("initial", "app_idle")
    all_states = machine.get("states", {})
    
    # Remove XState keyword states
    for keyword in XSTATE_KEYWORDS:
        if keyword in all_states and keyword != initial_state:
            print(f"  🧹 Removing XState keyword state: '{keyword}'")
            del all_states[keyword]
    
    # BFS to find all reachable states from initial state
    reachable = set()
    queue = [initial_state]
    reachable.add(initial_state)
    
    while queue:
        current = queue.pop(0)
        if current not in all_states:
            continue
        state_config = all_states[current]
        
        # Check transitions
        for event, target in state_config.get("on", {}).items():
            if isinstance(target, str):
                target_name = target.lstrip('.')
                if target_name in all_states and target_name not in reachable:
                    reachable.add(target_name)
                    queue.append(target_name)
            elif isinstance(target, dict):
                target_name = target.get("target", "").lstrip('.')
                if target_name in all_states and target_name not in reachable:
                    reachable.add(target_name)
                    queue.append(target_name)
            elif isinstance(target, list):
                for t in target:
                    if isinstance(t, dict):
                        target_name = t.get("target", "").lstrip('.')
                    else:
                        target_name = str(t).lstrip('.')
                    if target_name in all_states and target_name not in reachable:
                        reachable.add(target_name)
                        queue.append(target_name)
        
        # Check sub-states
        sub_states = state_config.get("states", {})
        for sub_name in sub_states:
            if sub_name not in reachable:
                reachable.add(sub_name)
                queue.append(sub_name)
    
    # Remove unreachable states
    unreachable = set(all_states.keys()) - reachable
    for state_name in unreachable:
        print(f"  🧹 Removing unreachable state: '{state_name}'")
        del all_states[state_name]
    
    return machine


# ---------------------------------------------------------------------------
# Post-Processing: Create Missing Target States
# ---------------------------------------------------------------------------

def create_missing_target_states(machine: dict) -> dict:
    """Ensure all transition targets exist in the state machine.
    
    If a transition targets a sub-state using dot notation (e.g., 'success.benchmark.clustering_calculation')
    and it doesn't exist, this function creates an empty state for it to prevent crashes.
    
    Supports both flat and parallel architectures.
    """
    # For parallel architecture, work with navigation branch states
    if machine.get("type") == "parallel" and "navigation" in machine.get("states", {}):
        states_root = machine["states"]["navigation"].get("states", {})
    else:
        states_root = machine.get("states", {})
    
    def ensure_path(path: str):
        parts = path.lstrip('.').split('.')
        current = states_root
        for i, part in enumerate(parts):
            if part not in current:
                print(f"  🔧 Created missing target state: {'.'.join(parts[:i+1])}")
                current[part] = {"entry": [], "exit": [], "on": {}}
            
            if i < len(parts) - 1:
                if "states" not in current[part]:
                    current[part]["states"] = {}
                current = current[part]["states"]

    def walk_states(states_dict, depth=0):
        if depth > 10:
            return  # Safety limit to prevent infinite recursion
        # Collect all targets first, then create them (avoid modifying dict during iteration)
        targets_to_create = []
        
        for state_config in list(states_dict.values()):
            on_events = state_config.get("on", {})
            for target in on_events.values():
                if isinstance(target, str):
                    targets_to_create.append(target)
                elif isinstance(target, dict):
                    t = target.get("target", "")
                    if t:
                        targets_to_create.append(t)
                elif isinstance(target, list):
                    for t in target:
                        if isinstance(t, dict):
                            t_str = t.get("target", "")
                            if t_str:
                                targets_to_create.append(t_str)
                        elif isinstance(t, str):
                            targets_to_create.append(t)
            
            if "states" in state_config:
                walk_states(state_config["states"], depth + 1)
        
        # Now create all missing targets
        for target in targets_to_create:
            ensure_path(target)

    walk_states(states_root)
    return machine


# ---------------------------------------------------------------------------
# Post-Processing: Fix Broken Transitions (point to non-existent states)
# ---------------------------------------------------------------------------

def fix_broken_transitions(machine: dict) -> dict:
    """Fix transitions that point to non-existent states.
    
    The LLM frequently generates invalid transition targets:
    - 'navigation' (should be a sub-state like 'navigation.dashboard')
    - '#navigation.app_idle' (XState selector syntax, invalid in JSON)
    - 'navigation.session_expired' (when session_expired is a sibling, not child)
    - '.none.error' (relative path to non-existent state)
    
    This function redirects broken transitions to valid fallback states:
    - CANCEL → app_idle (or nearest valid parent)
    - RETRY → loading (or nearest valid parent)
    - START_APP → authenticating
    - Other events → app_idle
    
    Supports both flat and parallel architectures.
    
    Args:
        machine: The state machine dict to fix.
    
    Returns:
        Fixed machine dict.
    """
    # For parallel architecture, work with navigation branch states
    if machine.get("type") == "parallel" and "navigation" in machine.get("states", {}):
        states_root = machine["states"]["navigation"].get("states", {})
    else:
        states_root = machine.get("states", {})
    
    # Collect all valid state paths (flat list of all state names at all levels)
    valid_states = set()
    
    def collect_states(states_dict, prefix=""):
        for name in states_dict:
            full_path = f"{prefix}.{name}" if prefix else name
            valid_states.add(name)  # Short name is always valid
            valid_states.add(full_path)  # Full path is also valid
            if "states" in states_dict[name]:
                collect_states(states_dict[name]["states"], full_path)
    
    collect_states(states_root)
    
    # Also add known valid targets for parallel architecture
    if machine.get("type") == "parallel":
        # Top-level machine states (outside navigation)
        for name in machine.get("states", {}):
            if name != "navigation":
                valid_states.add(name)
    
    fixed_count = 0
    
    def fix_target(target, source_state, event_name):
        """Fix a single transition target. Returns (fixed_target, was_fixed)."""
        if not target:
            return target, False
        
        original = target
        target_str = str(target)
        
        # Remove XState selector prefix '#'
        if target_str.startswith("#"):
            target_str = target_str[1:]
        
        # Remove leading dot (relative path)
        if target_str.startswith("."):
            target_str = target_str[1:]
        
        # Check if target exists
        if target_str in valid_states:
            return target_str, False
        
        # Target doesn't exist - determine fallback based on event name
        event_upper = event_name.upper() if event_name else ""
        
        if "CANCEL" in event_upper or "GO_BACK" in event_upper:
            fallback = "app_idle"
        elif "RETRY" in event_upper or "REFRESH" in event_upper:
            fallback = "loading"
        elif "START_APP" in event_upper:
            fallback = "authenticating"
        elif "REAUTHENTICATE" in event_upper:
            fallback = "authenticating"
        elif "TIMEOUT" in event_upper:
            fallback = "error"
        elif "ON_ERROR" in event_upper or "LOAD_FAILED" in event_upper:
            fallback = "error"
        elif "DATA_LOADED" in event_upper or "ON_SUCCESS" in event_upper:
            fallback = "ready"
        else:
            # Generic fallback: try to find a valid state with similar name
            # or default to app_idle
            fallback = "app_idle"
        
        # Check if fallback exists in valid states
        if fallback not in valid_states:
            # If fallback doesn't exist, use the first valid state as last resort
            fallback = "app_idle" if "app_idle" in valid_states else (list(valid_states)[0] if valid_states else "app_idle")
        
        print(f"  🔧 Fixed broken transition: {source_state} --{event_name}-> '{original}' → '{fallback}'")
        return fallback, True
    
    def walk_and_fix(states_dict, depth=0):
        nonlocal fixed_count
        if depth > 10:
            return
        
        for state_name, state_config in list(states_dict.items()):
            on_events = state_config.get("on", {})
            
            for event_name, target in list(on_events.items()):
                if isinstance(target, str):
                    fixed, was_fixed = fix_target(target, state_name, event_name)
                    if was_fixed:
                        on_events[event_name] = fixed
                        fixed_count += 1
                elif isinstance(target, dict):
                    t_target = target.get("target", "")
                    if t_target:
                        fixed, was_fixed = fix_target(t_target, state_name, event_name)
                        if was_fixed:
                            target["target"] = fixed
                            fixed_count += 1
                elif isinstance(target, list):
                    for i, t in enumerate(target):
                        if isinstance(t, dict):
                            t_target = t.get("target", "")
                            if t_target:
                                fixed, was_fixed = fix_target(t_target, state_name, event_name)
                                if was_fixed:
                                    target[i]["target"] = fixed
                                    fixed_count += 1
                        elif isinstance(t, str):
                            fixed, was_fixed = fix_target(t, state_name, event_name)
                            if was_fixed:
                                target[i] = fixed
                                fixed_count += 1
            
            # Recurse into sub-states
            if "states" in state_config:
                walk_and_fix(state_config["states"], depth + 1)
    
    walk_and_fix(states_root)
    
    if fixed_count > 0:
        print(f"  ✅ Fixed {fixed_count} broken transitions")
    
    return machine


# ---------------------------------------------------------------------------
# Post-Processing: Remove Duplicate States (same name at different paths)
# ---------------------------------------------------------------------------

def remove_duplicate_states(machine: dict) -> dict:
    """Remove duplicate states that appear at different paths.
    
    The LLM sometimes creates the same state name at different paths:
    - 'authenticating' at navigation.auth_guard.auth_guard_invalid.authenticating
    - 'authenticating' at navigation.session_expired.session_expired_reauth.authenticating
    
    This function keeps only the first occurrence and removes duplicates.
    
    Args:
        machine: The state machine dict to fix.
    
    Returns:
        Fixed machine dict.
    """
    # For parallel architecture, work with navigation branch states
    if machine.get("type") == "parallel" and "navigation" in machine.get("states", {}):
        states_root = machine["states"]["navigation"].get("states", {})
    else:
        states_root = machine.get("states", {})
    
    # Track all state names and their paths
    seen_states = {}  # name -> first path
    duplicates_to_remove = []  # (path, name) pairs to remove
    
    def find_duplicates(states_dict, prefix=""):
        for name in states_dict:
            full_path = f"{prefix}.{name}" if prefix else name
            
            if name in seen_states:
                # This is a duplicate - mark for removal
                duplicates_to_remove.append((full_path, name))
                print(f"  🧹 Found duplicate state: '{name}' at {full_path} (first at {seen_states[name]})")
            else:
                seen_states[name] = full_path
            
            # Recurse into sub-states
            if "states" in states_dict[name]:
                find_duplicates(states_dict[name]["states"], full_path)
    
    find_duplicates(states_root)
    
    # Remove duplicates (need to navigate to parent and delete)
    for path, name in duplicates_to_remove:
        parts = path.split(".")
        if len(parts) == 1:
            # Top-level duplicate - remove directly
            if name in states_root:
                del states_root[name]
        else:
            # Nested duplicate - navigate to parent
            parent = states_root
            for part in parts[:-1]:
                if part in parent and "states" in parent[part]:
                    parent = parent[part]["states"]
                else:
                    break
            if name in parent:
                del parent[name]
    
    if duplicates_to_remove:
        print(f"  ✅ Removed {len(duplicates_to_remove)} duplicate states")
    
    return machine


# ---------------------------------------------------------------------------
# Post-Processing: Validate No Critical Patterns (Rules 15, 16, 17)
# ---------------------------------------------------------------------------

def validate_no_critical_patterns(machine: dict) -> list:
    """Validate the machine against critical rules 15, 16, 17.
    
    Returns a list of violation messages. Empty list = no violations.
    Messages are designed to be "speaking" — they tell the LLM exactly what's wrong.
    
    Supports both flat and parallel architectures.
    
    Args:
        machine: The state machine dict to validate.
    
    Returns:
        List of violation message strings.
    """
    violations = []
    all_states = _get_states_for_processing(machine)
    
    # --- Rule 15: No duplicate states (success_* vs *) ---
    success_state = all_states.get("success", {})
    success_sub_states = success_state.get("states", {})
    
    if success_sub_states:
        # Find all short names inside success
        short_names = set(success_sub_states.keys())
        # Check for success_* duplicates
        for sub_name in list(short_names):
            duplicate_name = f"success_{sub_name}"
            if duplicate_name in success_sub_states:
                violations.append(
                    f"VIOLAZIONE REGOLA 15: Hai creato stati duplicati '{duplicate_name}' e '{sub_name}' "
                    f"entrambi dentro 'success'. Usa SOLO il nome breve '{sub_name}'. "
                    f"Rimuovi '{duplicate_name}' e tutte le sue transizioni."
                )
    
    # Also check for success_* at top level (shouldn't exist)
    for state_name in all_states:
        if state_name.startswith("success_") and state_name != "success":
            short = state_name.replace("success_", "")
            violations.append(
                f"VIOLAZIONE REGOLA 15: Stato '{state_name}' trovato a livello top-level. "
                f"Se '{short}' è già un sotto-stato di 'success', usa SOLO quello. "
                f"Rimuovi '{state_name}'."
            )
    
    # --- Rule 16: No checkAuth in app_idle entry ---
    app_idle = all_states.get("app_idle", {})
    app_idle_entry = app_idle.get("entry", [])
    
    forbidden_idle_actions = {"checkAuth", "validateCredentials", "startAuthTimer", "showAuthLoader"}
    found_forbidden = forbidden_idle_actions.intersection(set(app_idle_entry))
    
    if found_forbidden:
        violations.append(
            f"VIOLAZIONE REGOLA 16: app_idle ha azioni automatiche nella 'entry': {', '.join(found_forbidden)}. "
            f"app_idle è uno stato di riposo — NON deve eseguire azioni automatiche. "
            f"Rimuovi {', '.join(found_forbidden)} dalla entry di app_idle. "
            f"Invece, aggiungi un evento START_APP: \"on\": {{ \"START_APP\": \"authenticating\" }}."
        )
    
    # --- Rule 17: clustering_calculation must be a sub-state, not top-level ---
    if "clustering_calculation" in all_states:
        violations.append(
            f"VIOLAZIONE REGOLA 17: 'clustering_calculation' è uno stato top-level. "
            f"Deve essere un sotto-stato della pagina dove avviene il calcolo (es. success.benchmark.clustering_calculation). "
            f"Spostalo dentro 'benchmark' come sotto-stato e assicurati che abbia un'uscita verso 'error' "
            f"(es. \"on\": {{ \"ON_ERROR\": \"..\" }})."
        )
    
    return violations
