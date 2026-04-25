"""State machine post-processing.

Handles:
- Removing top-level duplicate states (when they exist as sub-states of 'success')
- Completing missing transition branches (both guard paths)
- Ensuring session_expired has REAUTHENTICATE transition
- Cleaning unreachable states and XState keywords
- Validating critical rules (15, 16, 17)
"""


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
    states = machine.get("states", {})
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
    
    all_states = machine.get("states", {})
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
    
    Args:
        machine: The state machine dict to clean.
    
    Returns:
        Cleaned machine dict.
    """
    initial_state = machine.get("initial", "app_idle")
    all_states = machine.get("states", {})
    
    # XState reserved keywords that should never be state names
    XSTATE_KEYWORDS = {"initial", "states", "on", "entry", "exit", "context", "id", "type", "invoke", "activities"}
    
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
    """
    def ensure_path(path: str):
        parts = path.lstrip('.').split('.')
        current = machine.setdefault("states", {})
        for i, part in enumerate(parts):
            if part not in current:
                print(f"  🔧 Created missing target state: {'.'.join(parts[:i+1])}")
                current[part] = {"entry": [], "exit": [], "on": {}}
            
            if i < len(parts) - 1:
                if "states" not in current[part]:
                    current[part]["states"] = {}
                current = current[part]["states"]

    def walk_states(states_dict):
        for state_config in states_dict.values():
            on_events = state_config.get("on", {})
            for target in on_events.values():
                if isinstance(target, str):
                    ensure_path(target)
                elif isinstance(target, dict):
                    t = target.get("target", "")
                    if t:
                        ensure_path(t)
                elif isinstance(target, list):
                    for t in target:
                        if isinstance(t, dict):
                            t_str = t.get("target", "")
                            if t_str:
                                ensure_path(t_str)
                        elif isinstance(t, str):
                            ensure_path(t)
            
            if "states" in state_config:
                walk_states(state_config["states"])

    walk_states(machine.get("states", {}))
    return machine



# ---------------------------------------------------------------------------
# Post-Processing: Validate No Critical Patterns (Rules 15, 16, 17)
# ---------------------------------------------------------------------------

def validate_no_critical_patterns(machine: dict) -> list:
    """Validate the machine against critical rules 15, 16, 17.
    
    Returns a list of violation messages. Empty list = no violations.
    Messages are designed to be "speaking" — they tell the LLM exactly what's wrong.
    
    Args:
        machine: The state machine dict to validate.
    
    Returns:
        List of violation message strings.
    """
    violations = []
    all_states = machine.get("states", {})
    
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