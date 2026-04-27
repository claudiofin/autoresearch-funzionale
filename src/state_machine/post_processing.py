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
    
    Also adds exit transitions to prevent dead-end states.
    
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
                # Create state with exit transitions to prevent dead-end
                current[part] = {
                    "entry": [], 
                    "exit": [], 
                    "on": {
                        "GO_BACK": "app_idle",
                        "CANCEL": "app_idle",
                        "COMPLETE": "app_idle"
                    }
                }
            
            if i < len(parts) - 1:
                if "states" not in current[part]:
                    current[part]["states"] = {}
                current = current[part]["states"]

    def walk_states(states_dict, depth=0):
        if depth > 10:
            return  # Safety limit to prevent infinite recursion
        # Collect all targets first, then create them (avoid modifying dict during iteration)
        targets_to_create = []
        
        for state_name, state_config in list(states_dict.items()):
            on_events = state_config.get("on", {})
            for event_name, target in on_events.items():
                if isinstance(target, str):
                    targets_to_create.append((target, state_name, event_name))
                elif isinstance(target, dict):
                    t = target.get("target", "")
                    if t:
                        targets_to_create.append((t, state_name, event_name))
                elif isinstance(target, list):
                    for t in target:
                        if isinstance(t, dict):
                            t_str = t.get("target", "")
                            if t_str:
                                targets_to_create.append((t_str, state_name, event_name))
                        elif isinstance(t, str):
                            targets_to_create.append((t, state_name, event_name))
            
            if "states" in state_config:
                walk_states(state_config["states"], depth + 1)
        
        # Now create all missing targets
        for target, source_state, event_name in targets_to_create:
            # Check if target exists (as top-level or nested)
            target_parts = target.lstrip('.').split('.')
            target_exists = False
            
            # Check as top-level state
            if target_parts[0] in states_root:
                if len(target_parts) == 1:
                    target_exists = True
                else:
                    # Check nested path
                    current = states_root[target_parts[0]]
                    for part in target_parts[1:]:
                        if "states" in current and part in current["states"]:
                            current = current["states"][part]
                            target_exists = True
                        else:
                            target_exists = False
                            break
            
            if not target_exists:
                ensure_path(target)

    walk_states(states_root)
    
    # Also check for common missing states that are often referenced
    common_missing_states = ["data_sync_state", "sync_complete", "sync_error"]
    for state_name in common_missing_states:
        if state_name not in states_root:
            print(f"  🔧 Created common missing state: '{state_name}'")
            states_root[state_name] = {
                "entry": [], 
                "exit": [], 
                "on": {
                    "GO_BACK": "app_idle",
                    "CANCEL": "app_idle",
                    "SYNC_COMPLETE": "app_idle",
                    "SYNC_FAILED": "app_idle"
                }
            }
    
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
    - 'authenticating' (bare name, should be 'auth_guard.validating' or similar)
    - 'ready'/'error'/'loading' (bare names that need context-aware resolution)
    
    This function uses a two-phase approach:
    1. Build a complete index of all state paths (including nested)
    2. Resolve bare targets by searching the tree contextually
    3. Fall back to event-based defaults if no match found
    
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
    
    # Phase 1: Collect ALL valid state paths and build a short-name → full-path index
    valid_states = set()
    short_to_full = {}  # short_name -> [full_path1, full_path2, ...]
    
    def collect_states(states_dict, prefix=""):
        for name in states_dict:
            full_path = f"{prefix}.{name}" if prefix else name
            valid_states.add(name)
            valid_states.add(full_path)
            # Index short name → full path(s)
            if name not in short_to_full:
                short_to_full[name] = []
            short_to_full[name].append(full_path)
            if "states" in states_dict[name]:
                collect_states(states_dict[name]["states"], full_path)
    
    collect_states(states_root)
    
    # Also add top-level machine states (outside navigation)
    top_level_states = set()
    if machine.get("type") == "parallel":
        for name in machine.get("states", {}):
            if name != "navigation":
                valid_states.add(name)
                top_level_states.add(name)
    
    # Phase 2: Context-aware resolution helpers
    def _find_substate_of(source_state, target_short):
        """Try to find target_short as a sub-state of source_state's parent chain."""
        parts = source_state.split(".")
        # Walk up the parent chain looking for the target as a sibling/sub
        for i in range(len(parts), 0, -1):
            parent_prefix = ".".join(parts[:i])
            candidate = f"{parent_prefix}.{target_short}" if parent_prefix else target_short
            if candidate in valid_states:
                return candidate
        return None
    
    def _find_in_sibling_branches(source_state, target_short):
        """Try to find target_short in sibling branches of the source state."""
        parts = source_state.split(".")
        if len(parts) >= 2:
            # Try as sibling of immediate parent
            parent_prefix = ".".join(parts[:-1])
            for candidate_path in short_to_full.get(target_short, []):
                if candidate_path.startswith(parent_prefix + "."):
                    return candidate_path
        return None
    
    def _smart_resolve(target_str, source_state, event_name):
        """Resolve a bare target name to a full path using context."""
        event_upper = event_name.upper() if event_name else ""
        
        # If target already exists as-is, no fix needed
        if target_str in valid_states:
            return target_str
        
        # Try to find as sub-state of source's parent chain
        resolved = _find_substate_of(source_state, target_str)
        if resolved:
            return resolved
        
        # Try to find in sibling branches
        resolved = _find_in_sibling_branches(source_state, target_str)
        if resolved:
            return resolved
        
        # Event-based fallback with context-aware targets
        if "CANCEL" in event_upper or "GO_BACK" in event_upper:
            # Try to go to parent state
            parts = source_state.split(".")
            if len(parts) > 1:
                parent = ".".join(parts[:-1])
                if parent in valid_states:
                    return parent
            return "app_idle" if "app_idle" in valid_states else None
        
        elif "RETRY" in event_upper or "REFRESH" in event_upper:
            # If source IS a loading state, RETRY → self
            if source_state == "loading" or source_state.endswith(".loading"):
                return source_state
            # Try loading sub-state of current state's parent
            parts = source_state.split(".")
            if len(parts) >= 2:
                parent = ".".join(parts[:-1])
                loading_candidate = f"{parent}.loading"
                if loading_candidate in valid_states:
                    return loading_candidate
            return "app_idle" if "app_idle" in valid_states else None
        
        elif "START_APP" in event_upper:
            # START_APP should go to auth flow
            for path in short_to_full.get("auth_guard", []):
                return path
            for path in short_to_full.get("login", []):
                return path
            # Fallback: authenticating (flat state)
            if "authenticating" in valid_states:
                return "authenticating"
            return "app_idle" if "app_idle" in valid_states else None
        
        elif "REAUTHENTICATE" in event_upper:
            # REAUTHENTICATE should go to auth validation
            for path in short_to_full.get("auth_guard", []):
                return path
            for path in short_to_full.get("login", []):
                return path
            return "app_idle" if "app_idle" in valid_states else None
        
        elif "TIMEOUT" in event_upper:
            # TIMEOUT → error sub-state of parent
            parts = source_state.split(".")
            if len(parts) >= 2:
                parent = ".".join(parts[:-1])
                error_candidate = f"{parent}.error"
                if error_candidate in valid_states:
                    return error_candidate
            return "app_error" if "app_error" in valid_states else None
        
        elif "ON_ERROR" in event_upper or "LOAD_FAILED" in event_upper:
            # Error → error sub-state of parent
            parts = source_state.split(".")
            if len(parts) >= 2:
                parent = ".".join(parts[:-1])
                error_candidate = f"{parent}.error"
                if error_candidate in valid_states:
                    return error_candidate
            return "app_error" if "app_error" in valid_states else None
        
        elif "DATA_LOADED" in event_upper or "ON_SUCCESS" in event_upper:
            # Success → ready sub-state of parent, or dashboard for auth flows
            parts = source_state.split(".")
            if len(parts) >= 2:
                parent = ".".join(parts[:-1])
                ready_candidate = f"{parent}.ready"
                if ready_candidate in valid_states:
                    return ready_candidate
            # Auth flow success → dashboard
            for path in short_to_full.get("dashboard", []):
                return path
            return "app_idle" if "app_idle" in valid_states else None
        
        elif "AUTH_SUCCESS" in event_upper:
            # Auth success → dashboard
            for path in short_to_full.get("dashboard", []):
                return path
            return "app_idle" if "app_idle" in valid_states else None
        
        elif "AUTH_FAILED" in event_upper or "LOGIN_FAILED" in event_upper:
            # Auth failure → login
            for path in short_to_full.get("login", []):
                return path
            return "app_error" if "app_error" in valid_states else None
        
        elif "COMPLETE" in event_upper or "COMPLETED" in event_upper:
            # Workflow complete → return to navigation root
            return "app_idle" if "app_idle" in valid_states else None
        
        # Last resort: use first match from index or None
        if target_str in short_to_full and short_to_full[target_str]:
            return short_to_full[target_str][0]
        
        return None  # Cannot resolve
    
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
        
        # Phase 2: Smart resolution
        resolved = _smart_resolve(target_str, source_state, event_name)
        
        if resolved:
            print(f"  🔧 Fixed broken transition: {source_state} --{event_name}-> '{original}' → '{resolved}'")
            return resolved, True
        
        # Absolute last resort: app_idle
        fallback = "app_idle" if "app_idle" in valid_states else (list(valid_states)[0] if valid_states else "app_idle")
        print(f"  🔧 Fixed broken transition (fallback): {source_state} --{event_name}-> '{original}' → '{fallback}'")
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
# Post-Processing: Fix Structural Issues (Empty states, dead-ends, navigation duplicates)
# ---------------------------------------------------------------------------

def fix_structural_issues(machine: dict) -> dict:
    """Fix structural issues that cause validation failures.
    
    Handles:
    - INVALID_COMPOUND_STATE: Removes empty 'states' dicts from compound states
    - DEAD_END_STATE: Adds exit transitions to states with no exits
    - DUPLICATE_STATE: Fixes navigation duplicates (navigation.navigation)
    
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
    
    fixed_empty = 0
    fixed_dead_ends = 0
    fixed_duplicates = 0
    
    def walk_and_fix(states_dict, parent_path=""):
        nonlocal fixed_empty, fixed_dead_ends, fixed_duplicates
        
        for state_name in list(states_dict.keys()):
            state_config = states_dict[state_name]
            current_path = f"{parent_path}.{state_name}" if parent_path else state_name
            
            # Fix 1: Remove empty 'states' dict (INVALID_COMPOUND_STATE)
            if "states" in state_config:
                sub_states = state_config["states"]
                if not sub_states or len(sub_states) == 0:
                    del state_config["states"]
                    # Also remove 'initial' if present since it's no longer a compound state
                    if "initial" in state_config:
                        del state_config["initial"]
                    fixed_empty += 1
                    print(f"  🔧 Fixed empty compound state: '{current_path}' (converted to atomic)")
                else:
                    # Fix initial mismatch: initial must point to an existing sub-state
                    if "initial" in state_config:
                        initial_state = state_config["initial"]
                        if initial_state not in sub_states:
                            # Pick first available sub-state as initial
                            first_sub = list(sub_states.keys())[0]
                            state_config["initial"] = first_sub
                            print(f"  🔧 Fixed initial mismatch: '{current_path}' initial '{initial_state}' → '{first_sub}'")
                    # Recurse into sub-states
                    walk_and_fix(sub_states, current_path)
            
            # Fix 2: Add exit transitions to dead-end states (DEAD_END_STATE)
            on_events = state_config.get("on", {})
            if not on_events and state_name not in ["app_idle", "dashboard", "success"]:
                # This is a dead-end state - add exit transitions
                state_config["on"] = {
                    "GO_BACK": parent_path if parent_path else "app_idle",
                    "CANCEL": "app_idle"
                }
                fixed_dead_ends += 1
                print(f"  🔧 Fixed dead-end state: '{current_path}' (added GO_BACK, CANCEL transitions)")
        
        # Fix 3: Handle navigation duplicates (e.g., navigation.navigation)
        if "navigation" in states_dict and parent_path.endswith("navigation"):
            # This is navigation.navigation - merge or remove
            nav_state = states_dict["navigation"]
            parent_nav = states_root  # Get the parent navigation
            
            # Merge sub-states from navigation.navigation into parent navigation
            if "states" in nav_state and nav_state["states"]:
                for sub_name, sub_config in nav_state["states"].items():
                    if sub_name not in parent_nav:
                        parent_nav[sub_name] = sub_config
                        print(f"  🔧 Merged duplicate navigation state: '{sub_name}'")
            
            # Remove the duplicate navigation state
            del states_dict["navigation"]
            fixed_duplicates += 1
            print(f"  🔧 Removed duplicate navigation state: '{current_path}.navigation'")
    
    walk_and_fix(states_root)
    
    if fixed_empty > 0 or fixed_dead_ends > 0 or fixed_duplicates > 0:
        print(f"  ✅ Structural fixes: {fixed_empty} empty states, {fixed_dead_ends} dead-ends, {fixed_duplicates} duplicates")
    
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


# ---------------------------------------------------------------------------
# Post-Processing: Ensure Connectivity (Fix Unreachable States)
# ---------------------------------------------------------------------------

def ensure_connectivity(machine: dict) -> dict:
    """Ensure all states are reachable from the initial state.
    
    The validator reports UNREACHABLE_STATE when states exist but have no
    path from the initial state. This function adds transitions from the
    initial state (or other reachable states) to unreachable states.
    
    This function:
    1. Performs BFS from initial state to find all reachable states
    2. Identifies unreachable states
    3. Adds transitions from reachable states to unreachable states
    4. Prioritizes adding transitions from the initial state
    
    Args:
        machine: The state machine dict to fix.
    
    Returns:
        Fixed machine dict.
    """
    # For parallel architecture, work with navigation branch states
    if machine.get("type") == "parallel" and "navigation" in machine.get("states", {}):
        states_root = machine["states"]["navigation"].get("states", {})
        initial_state = machine["states"]["navigation"].get("initial", "app_idle")
    else:
        states_root = machine.get("states", {})
        initial_state = machine.get("initial", "app_idle")
    
    if not states_root:
        return machine
    
    # BFS to find all reachable states
    reachable = set()
    queue = [initial_state]
    
    while queue:
        current = queue.pop(0)
        if current in reachable:
            continue
        if current not in states_root:
            continue
        
        reachable.add(current)
        state_config = states_root[current]
        
        # Check transitions
        for event, target in state_config.get("on", {}).items():
            if isinstance(target, str):
                target_name = target.split(".")[-1]  # Get short name
                if target_name in states_root and target_name not in reachable:
                    queue.append(target_name)
            elif isinstance(target, dict):
                target_name = target.get("target", "").split(".")[-1]
                if target_name in states_root and target_name not in reachable:
                    queue.append(target_name)
            elif isinstance(target, list):
                for t in target:
                    if isinstance(t, dict):
                        target_name = t.get("target", "").split(".")[-1]
                    else:
                        target_name = str(t).split(".")[-1]
                    if target_name in states_root and target_name not in reachable:
                        queue.append(target_name)
        
        # Check sub-states (they are reachable if parent is reachable)
        for sub_name in state_config.get("states", {}):
            full_path = f"{current}.{sub_name}"
            # Sub-states are considered reachable but we track parent states
    
    # Find unreachable states (top-level only for parallel architecture)
    all_states = set(states_root.keys())
    unreachable = all_states - reachable - {initial_state}
    
    if not unreachable:
        return machine
    
    print(f"  🔧 Found {len(unreachable)} unreachable states: {sorted(unreachable)[:10]}{'...' if len(unreachable) > 10 else ''}")
    
    # Add transitions from initial state to unreachable states
    initial_config = states_root.get(initial_state, {})
    if "on" not in initial_config:
        initial_config["on"] = {}
    
    added_count = 0
    for unreachable_state in sorted(unreachable):
        # Create a navigation event for this state
        event_name = f"NAVIGATE_TO_{unreachable_state.upper()}"
        
        # Check if transition already exists
        if event_name not in initial_config["on"]:
            initial_config["on"][event_name] = unreachable_state
            added_count += 1
            print(f"  🔧 Added transition: {initial_state} --{event_name}--> {unreachable_state}")
    
    if added_count > 0:
        print(f"  ✅ Added {added_count} transitions to connect unreachable states")
    
    return machine


# ---------------------------------------------------------------------------
# Post-Processing: Fix Duplicate State Names at Different Paths
# ---------------------------------------------------------------------------

def fix_duplicate_state_names(machine: dict) -> dict:
    """Fix states that appear with the same name at different paths.
    
    The validator reports DUPLICATE_STATE when the same state name appears
    at different paths (e.g., 'navigation' at root and 'navigation.navigation').
    
    This function:
    1. Detects duplicate state names across the entire machine
    2. Keeps the first occurrence (usually the intended one)
    3. Renames subsequent duplicates with a suffix
    4. Updates all transitions to point to the renamed states
    
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
    state_paths = {}  # name -> list of full paths
    
    def collect_state_paths(states_dict, prefix=""):
        for name, config in states_dict.items():
            full_path = f"{prefix}.{name}" if prefix else name
            if name not in state_paths:
                state_paths[name] = []
            state_paths[name].append(full_path)
            
            # Recurse into sub-states
            if "states" in config:
                collect_state_paths(config["states"], full_path)
    
    collect_state_paths(states_root)
    
    # Find duplicates (same name, different paths)
    duplicates = {name: paths for name, paths in state_paths.items() if len(paths) > 1}
    
    if not duplicates:
        return machine
    
    print(f"  🔧 Found {len(duplicates)} duplicate state names: {list(duplicates.keys())}")
    
    # Rename strategy: keep first occurrence, rename others
    rename_map = {}  # old_path -> new_name
    
    for name, paths in duplicates.items():
        # Keep the first path as-is, rename the rest
        for i, path in enumerate(paths[1:], 1):
            new_name = f"{name}_{i}"
            rename_map[path] = new_name
            print(f"  🔧 Will rename '{path}' to '{new_name}'")
    
    # Apply renames
    renamed_count = 0
    
    def rename_in_states(states_dict, prefix=""):
        nonlocal renamed_count
        
        # Process current level
        for name in list(states_dict.keys()):
            full_path = f"{prefix}.{name}" if prefix else name
            
            if full_path in rename_map:
                new_name = rename_map[full_path]
                # Rename the state
                states_dict[new_name] = states_dict.pop(name)
                renamed_count += 1
                print(f"  ✅ Renamed '{full_path}' to '{new_name}'")
                name = new_name
            
            # Recurse into sub-states
            if "states" in states_dict[name]:
                rename_in_states(states_dict[name]["states"], full_path)
    
    rename_in_states(states_root)
    
    # Update all transitions to use new names
    def update_transitions(states_dict, prefix=""):
        for name, config in states_dict.items():
            full_path = f"{prefix}.{name}" if prefix else name
            
            # Update transitions in 'on' events
            if "on" in config:
                for event, target in list(config["on"].items()):
                    if isinstance(target, str):
                        # Check if target needs to be renamed
                        for old_path, new_name in rename_map.items():
                            if target == old_path.split(".")[-1]:
                                # Target matches a renamed state
                                config["on"][event] = new_name
                                print(f"  🔧 Updated transition: {full_path} --{event}--> {new_name}")
                                break
                    elif isinstance(target, dict):
                        tgt = target.get("target", "")
                        for old_path, new_name in rename_map.items():
                            if tgt == old_path.split(".")[-1]:
                                target["target"] = new_name
                                print(f"  🔧 Updated transition: {full_path} --{event}--> {new_name}")
                                break
                    elif isinstance(target, list):
                        for i, t in enumerate(target):
                            if isinstance(t, dict):
                                tgt = t.get("target", "")
                                for old_path, new_name in rename_map.items():
                                    if tgt == old_path.split(".")[-1]:
                                        t["target"] = new_name
                                        print(f"  🔧 Updated transition: {full_path} --{event}--> {new_name}")
                                        break
                            elif isinstance(t, str):
                                for old_path, new_name in rename_map.items():
                                    if t == old_path.split(".")[-1]:
                                        target[i] = new_name
                                        print(f"  🔧 Updated transition: {full_path} --{event}--> {new_name}")
                                        break
            
            # Recurse into sub-states
            if "states" in config:
                update_transitions(config["states"], full_path)
    
    update_transitions(states_root)
    
    if renamed_count > 0:
        print(f"  ✅ Fixed {renamed_count} duplicate state names")
    
    return machine


# ---------------------------------------------------------------------------
# Post-Processing: Fix Infinite Loops
# ---------------------------------------------------------------------------

def fix_infinite_loops(machine: dict) -> dict:
    """Fix potential infinite loops in the state machine.
    
    The validator reports POTENTIAL_INFINITE_LOOP when there's a bidirectional
    cycle between two states (e.g., app_idle <-> auth_guard) where one state
    has no other exits.
    
    This function:
    1. Detects bidirectional cycles between states
    2. Adds alternative exit transitions to break the loop
    3. Ensures every state in a cycle has at least one exit to outside the cycle
    
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
    
    # Build transition graph
    transitions = {}  # state_name -> list of (target, event)
    
    def collect_transitions(states_dict, prefix=""):
        for name, config in states_dict.items():
            full_path = f"{prefix}.{name}" if prefix else name
            short_name = name  # Use short name for cycle detection
            
            if short_name not in transitions:
                transitions[short_name] = []
            
            if "on" in config:
                for event, target in config["on"].items():
                    if isinstance(target, str):
                        target_short = target.split(".")[-1]
                        transitions[short_name].append((target_short, event))
                    elif isinstance(target, dict):
                        tgt = target.get("target", "")
                        if tgt:
                            target_short = tgt.split(".")[-1]
                            transitions[short_name].append((target_short, event))
                    elif isinstance(target, list):
                        for t in target:
                            if isinstance(t, dict):
                                tgt = t.get("target", "")
                                if tgt:
                                    target_short = tgt.split(".")[-1]
                                    transitions[short_name].append((target_short, event))
                            elif isinstance(t, str):
                                target_short = t.split(".")[-1]
                                transitions[short_name].append((target_short, event))
            
            # Recurse into sub-states
            if "states" in config:
                collect_transitions(config["states"], full_path)
    
    collect_transitions(states_root)
    
    # Find bidirectional cycles
    cycles = []
    checked_pairs = set()
    
    for state_a, targets_a in transitions.items():
        for target_b, _ in targets_a:
            if target_b in transitions:
                # Check if target_b transitions back to state_a
                for target_a, _ in transitions.get(target_b, []):
                    if target_a == state_a:
                        pair = tuple(sorted([state_a, target_b]))
                        if pair not in checked_pairs:
                            checked_pairs.add(pair)
                            cycles.append((state_a, target_b))
    
    if not cycles:
        return machine
    
    print(f"  🔧 Found {len(cycles)} bidirectional cycles: {cycles}")
    
    # Fix each cycle by adding alternative exits
    fixed_cycles = 0
    
    for state_a, state_b in cycles:
        # Find which state has fewer exits
        exits_a = [t for t, _ in transitions.get(state_a, []) if t != state_b]
        exits_b = [t for t, _ in transitions.get(state_b, []) if t != state_a]
        
        # Add exit to the state with fewer alternatives
        if len(exits_a) == 0:
            # State A only goes to B - add an exit to dashboard or app_idle
            target_exit = "dashboard" if "dashboard" in states_root else "app_idle"
            if target_exit in states_root and state_a in states_root:
                state_config = states_root[state_a]
                if "on" not in state_config:
                    state_config["on"] = {}
                if "NAVIGATE_TO_DASHBOARD" not in state_config["on"]:
                    state_config["on"]["NAVIGATE_TO_DASHBOARD"] = target_exit
                    print(f"  🔧 Added exit from '{state_a}' to '{target_exit}' to break cycle")
                    fixed_cycles += 1
        
        if len(exits_b) == 0:
            # State B only goes to A - add an exit
            target_exit = "dashboard" if "dashboard" in states_root else "app_idle"
            if target_exit in states_root and state_b in states_root:
                state_config = states_root[state_b]
                if "on" not in state_config:
                    state_config["on"] = {}
                if "NAVIGATE_TO_DASHBOARD" not in state_config["on"]:
                    state_config["on"]["NAVIGATE_TO_DASHBOARD"] = target_exit
                    print(f"  🔧 Added exit from '{state_b}' to '{target_exit}' to break cycle")
                    fixed_cycles += 1
    
    if fixed_cycles > 0:
        print(f"  ✅ Fixed {fixed_cycles} infinite loops")
    
    return machine


# ---------------------------------------------------------------------------
# Post-Processing: Fix Root vs Navigation Duplicates
# ---------------------------------------------------------------------------

def fix_root_navigation_duplicates(machine: dict) -> dict:
    """Fix duplicate states that exist both at root level and inside navigation.
    
    The validator reports DUPLICATE_STATE when states like 'navigation' or 
    'data_sync_state' exist both as root states and as sub-states of 'navigation'.
    
    This function:
    1. Detects duplicates between root states and navigation sub-states
    2. Removes the root-level duplicates (keeping navigation sub-states)
    3. Updates all transitions to point to the correct paths
    
    Args:
        machine: The state machine dict to fix.
    
    Returns:
        Fixed machine dict.
    """
    states = machine.get("states", {})
    
    # Check if we have navigation branch
    if "navigation" not in states:
        return machine
    
    nav_states = states["navigation"].get("states", {})
    
    # Find duplicates: states that exist both at root and in navigation
    root_state_names = set(states.keys())
    nav_state_names = set(nav_states.keys())
    duplicates = root_state_names & nav_state_names
    
    if not duplicates:
        return machine
    
    # Filter out the 'navigation' branch itself - we should never remove the navigation branch
    duplicates = {d for d in duplicates if d != 'navigation'}
    
    if not duplicates:
        return machine
    
    print(f"  🔧 Found {len(duplicates)} root/navigation duplicates: {duplicates}")
    
    # Remove root-level duplicates (keep navigation sub-states)
    for dup_name in duplicates:
        if dup_name in states:
            del states[dup_name]
            print(f"  🔧 Removed root-level duplicate: '{dup_name}' (keeping navigation.{dup_name})")
    
    # Also remove invalid state names (starting with #)
    invalid_names = [name for name in nav_state_names if name.startswith("#")]
    for invalid_name in invalid_names:
        if invalid_name in nav_states:
            del nav_states[invalid_name]
            print(f"  🔧 Removed invalid state name: 'navigation.{invalid_name}'")
    
    # Update transitions that pointed to root duplicates
    def update_transitions(states_dict, prefix=""):
        for name, config in states_dict.items():
            full_path = f"{prefix}.{name}" if prefix else name
            
            if "on" in config:
                for event, target in list(config["on"].items()):
                    if isinstance(target, str):
                        # Check if target was a removed root duplicate
                        if target in duplicates:
                            # Update to point to navigation sub-state
                            new_target = f"navigation.{target}"
                            config["on"][event] = new_target
                            print(f"  🔧 Updated transition: {full_path} --{event}--> {new_target}")
                        elif target.startswith("#"):
                            # Remove transitions to invalid states
                            del config["on"][event]
                            print(f"  🔧 Removed transition to invalid state: {full_path} --{event}--> {target}")
                    elif isinstance(target, dict):
                        tgt = target.get("target", "")
                        if tgt in duplicates:
                            new_target = f"navigation.{tgt}"
                            target["target"] = new_target
                            print(f"  🔧 Updated transition: {full_path} --{event}--> {new_target}")
                        elif tgt.startswith("#"):
                            del config["on"][event]
                            print(f"  🔧 Removed transition to invalid state: {full_path} --{event}--> {tgt}")
                    elif isinstance(target, list):
                        new_targets = []
                        for t in target:
                            if isinstance(t, dict):
                                tgt = t.get("target", "")
                                if tgt in duplicates:
                                    t["target"] = f"navigation.{tgt}"
                                    print(f"  🔧 Updated transition: {full_path} --{event}--> navigation.{tgt}")
                                elif not tgt.startswith("#"):
                                    new_targets.append(t)
                                else:
                                    print(f"  🔧 Removed transition to invalid state: {full_path} --{event}--> {tgt}")
                            elif isinstance(t, str):
                                if t in duplicates:
                                    new_targets.append(f"navigation.{t}")
                                    print(f"  🔧 Updated transition: {full_path} --{event}--> navigation.{t}")
                                elif not t.startswith("#"):
                                    new_targets.append(t)
                                else:
                                    print(f"  🔧 Removed transition to invalid state: {full_path} --{event}--> {t}")
                        if new_targets:
                            config["on"][event] = new_targets
                        else:
                            del config["on"][event]
            
            # Recurse into sub-states
            if "states" in config:
                update_transitions(config["states"], full_path)
    
    # Update transitions in navigation branch
    update_transitions(nav_states, "navigation")
    
    # Update transitions in remaining root states
    for root_name, root_config in states.items():
        if isinstance(root_config, dict) and "on" in root_config:
            for event, target in list(root_config["on"].items()):
                if isinstance(target, str):
                    if target in duplicates:
                        root_config["on"][event] = f"navigation.{target}"
                        print(f"  🔧 Updated root transition: {root_name} --{event}--> navigation.{target}")
                    elif target.startswith("#"):
                        del root_config["on"][event]
                        print(f"  🔧 Removed root transition to invalid state: {root_name} --{event}--> {target}")
    
    # Update initial state if it pointed to a removed duplicate
    initial = machine.get("initial", "")
    if initial in duplicates:
        machine["initial"] = f"navigation.{initial}"
        print(f"  🔧 Updated initial state: {initial} -> navigation.{initial}")
    
    print(f"  ✅ Fixed {len(duplicates)} root/navigation duplicates")
    
    return machine
