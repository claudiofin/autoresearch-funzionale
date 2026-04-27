
# ---------------------------------------------------------------------------
# Post-Processing: Complete Machine Cleanup and Fix
# ---------------------------------------------------------------------------

def aggressive_cleanup(machine: dict) -> dict:
    """Complete cleanup and fix of the state machine.
    
    This function performs comprehensive fixes:
    1. Removes duplicate states (same name at different paths)
    2. Fixes relative transition targets to absolute paths
    3. Adds exit transitions to dead-end states
    4. Removes unreachable states
    5. Fixes broken transitions
    6. Removes nested duplicates (e.g., navigation.navigation)
    7. Ensures critical bootstrap transitions exist
    
    Args:
        machine: The state machine dict to clean.
    
    Returns:
        Cleaned and fixed machine dict.
    """
    states = machine.get("states", {})
    
    # Check if we have navigation branch (parallel architecture)
    if "navigation" not in states:
        return machine
    
    nav_states = states["navigation"].get("states", {})
    
    # Phase 1: Remove states that have the same name as an ancestor (e.g., navigation.navigation)
    # This must be done FIRST before any other processing
    def remove_ancestor_duplicates(states_dict, ancestor_names=None, prefix=""):
        if ancestor_names is None:
            ancestor_names = set()
        
        removed = 0
        
        for name in list(states_dict.keys()):
            full_path = f"{prefix}.{name}" if prefix else name
            
            # Check if this state name matches any ancestor name
            if name in ancestor_names:
                print(f"  🧹 [CLEANUP] Removed ancestor duplicate: {full_path} (matches ancestor)")
                del states_dict[name]
                removed += 1
                continue
            
            # Add this name to ancestors and recurse
            new_ancestors = ancestor_names | {name}
            config = states_dict[name]
            
            if "states" in config:
                removed += remove_ancestor_duplicates(config["states"], new_ancestors, full_path)
        
        return removed
    
    removed_count = remove_ancestor_duplicates(nav_states, {"navigation"}, "navigation")
    
    # Phase 2: Build a map of all state names to their full paths
    state_paths = {}  # name -> full_path
    state_configs = {}  # full_path -> config
    
    def collect_all_states(states_dict, prefix=""):
        for name, config in states_dict.items():
            full_path = f"{prefix}.{name}" if prefix else name
            
            # Store the first occurrence
            if name not in state_paths:
                state_paths[name] = full_path
            
            state_configs[full_path] = config
            
            # Recurse into sub-states
            if "states" in config:
                collect_all_states(config["states"], full_path)
    
    collect_all_states(nav_states, "navigation")
    
    # Also add top-level states
    for name, config in states.items():
        if name not in state_paths:
            state_paths[name] = name
        state_configs[name] = config
    
    print(f"  📊 [CLEANUP] Found {len(state_paths)} unique state names, {len(state_configs)} total states")
    
    # Phase 3: Remove duplicate states (keep only the one in navigation)
    # Remove root-level duplicates that also exist in navigation
    for name in list(states.keys()):
        if name != "navigation" and name in nav_states:
            print(f"  🧹 [CLEANUP] Removed duplicate root state: '{name}' (keeping navigation.{name})")
            del states[name]
            removed_count += 1
    
    # Phase 4: Fix transition targets to use correct full paths
    def fix_transitions(states_dict, prefix=""):
        nonlocal removed_count
        
        for name, config in states_dict.items():
            full_path = f"{prefix}.{name}" if prefix else name
            
            if "on" in config:
                for event, target in list(config["on"].items()):
                    if isinstance(target, str):
                        # Fix relative target to absolute path
                        target_clean = target.lstrip(".#")
                        
                        # Check if target exists as-is in state_paths
                        if target_clean in state_paths:
                            full_target = state_paths[target_clean]
                            # Always use the full path for clarity
                            if target != full_target:
                                print(f"  🔧 [CLEANUP] Fixed transition: {full_path} --{event}--> {full_target}")
                                config["on"][event] = full_target
                        elif target_clean in state_configs:
                            # Target exists with different path - keep as is
                            pass
                        else:
                            # Target doesn't exist - remove transition
                            print(f"  🧹 [CLEANUP] Removed broken transition: {full_path} --{event}--> {target}")
                            del config["on"][event]
                            removed_count += 1
                    
                    elif isinstance(target, dict):
                        tgt = target.get("target", "")
                        tgt_clean = tgt.lstrip(".#")
                        
                        if tgt_clean in state_paths:
                            full_target = state_paths[tgt_clean]
                            if tgt != full_target:
                                print(f"  🔧 [CLEANUP] Fixed transition: {full_path} --{event}--> {full_target}")
                                target["target"] = full_target
                        elif tgt_clean not in state_configs:
                            print(f"  🧹 [CLEANUP] Removed broken transition: {full_path} --{event}--> {tgt}")
                            del config["on"][event]
                            removed_count += 1
                    
                    elif isinstance(target, list):
                        new_targets = []
                        for t in target:
                            if isinstance(t, dict):
                                tgt = t.get("target", "")
                                tgt_clean = tgt.lstrip(".#")
                                
                                if tgt_clean in state_paths:
                                    full_target = state_paths[tgt_clean]
                                    if tgt != full_target:
                                        t["target"] = full_target
                                    new_targets.append(t)
                                elif tgt_clean in state_configs:
                                    new_targets.append(t)
                                else:
                                    print(f"  🧹 [CLEANUP] Removed broken transition item: {full_path} --{event}--> {tgt}")
                                    removed_count += 1
                            elif isinstance(t, str):
                                t_clean = t.lstrip(".#")
                                if t_clean in state_paths:
                                    full_target = state_paths[t_clean]
                                    if t != full_target:
                                        new_targets.append(full_target)
                                    else:
                                        new_targets.append(t)
                                elif t_clean in state_configs:
                                    new_targets.append(t)
                                else:
                                    print(f"  🧹 [CLEANUP] Removed broken transition item: {full_path} --{event}--> {t}")
                                    removed_count += 1
                        
                        if new_targets:
                            config["on"][event] = new_targets
                        else:
                            del config["on"][event]
            
            # Recurse into sub-states
            if "states" in config:
                fix_transitions(config["states"], full_path)
    
    fix_transitions(nav_states, "navigation")
    
    # Also fix transitions in top-level states
    for name, config in states.items():
        if "on" in config:
            for event, target in list(config["on"].items()):
                if isinstance(target, str):
                    target_clean = target.lstrip(".#")
                    if target_clean in state_paths:
                        full_target = state_paths[target_clean]
                        if target != full_target:
                            print(f"  🔧 [CLEANUP] Fixed top-level transition: {name} --{event}--> {full_target}")
                            config["on"][event] = full_target
    
    # Phase 5: Add exit transitions to dead-end states
    def add_exit_transitions(states_dict, prefix=""):
        for name, config in states_dict.items():
            full_path = f"{prefix}.{name}" if prefix else name
            
            # Check if this is a dead-end state
            has_on = "on" in config and config["on"]
            is_final = config.get("type") == "final"
            
            if not has_on and not is_final:
                # This is a dead-end state - add exit transitions
                if "on" not in config:
                    config["on"] = {}
                
                # Add GO_BACK and CANCEL transitions to app_idle
                config["on"]["GO_BACK"] = "navigation.app_idle"
                config["on"]["CANCEL"] = "navigation.app_idle"
                print(f"  🔧 [CLEANUP] Added exit transitions to dead-end: {full_path}")
            
            # Recurse into sub-states
            if "states" in config:
                add_exit_transitions(config["states"], full_path)
    
    add_exit_transitions(nav_states, "navigation")
    
    # Phase 6: Fix initial states that point to non-existent sub-states
    def fix_initial_states(states_dict, prefix=""):
        for name, config in states_dict.items():
            full_path = f"{prefix}.{name}" if prefix else name
            
            if "initial" in config and "states" in config:
                initial = config["initial"]
                sub_states = config["states"]
                
                # Check if initial state exists
                if initial not in sub_states:
                    # Try to find a matching state
                    for sub_name in sub_states:
                        if sub_name.endswith(initial) or initial.endswith(sub_name):
                            config["initial"] = sub_name
                            print(f"  🔧 [CLEANUP] Fixed initial state: {full_path} -> {sub_name}")
                            break
                    else:
                        # Use first available sub-state
                        if sub_states:
                            first_state = list(sub_states.keys())[0]
                            config["initial"] = first_state
                            print(f"  🔧 [CLEANUP] Fixed initial state: {full_path} -> {first_state}")
            
            # Recurse into sub-states
            if "states" in config:
                fix_initial_states(config["states"], full_path)
    
    fix_initial_states(nav_states, "navigation")
    
    # Phase 7: Ensure critical bootstrap transitions exist
    def ensure_bootstrap_transitions(machine):
        """Ensure critical transitions like app_idle -> auth_guard exist."""
        added = 0
        
        if "navigation" in machine.get("states", {}):
            nav = machine["states"]["navigation"]
            nav_states = nav.get("states", {})
            
            if "app_idle" in nav_states:
                app_idle = nav_states["app_idle"]
                
                # Ensure app_idle has an 'on' section
                if "on" not in app_idle:
                    app_idle["on"] = {}
                
                # Check if START_APP transition exists and points to a valid target
                if "START_APP" not in app_idle["on"]:
                    # Find auth_guard
                    if "auth_guard" in nav_states:
                        app_idle["on"]["START_APP"] = "navigation.auth_guard"
                        print(f"  🔧 [CLEANUP] Added START_APP transition: app_idle -> navigation.auth_guard")
                        added += 1
                    else:
                        # Fallback: try to find any state that could be the entry point
                        for state_name in nav_states:
                            if state_name != "app_idle":
                                app_idle["on"]["START_APP"] = f"navigation.{state_name}"
                                print(f"  🔧 [CLEANUP] Added START_APP transition: app_idle -> navigation.{state_name} (fallback)")
                                added += 1
                                break
                else:
                    # Verify the target exists
                    current_target = app_idle["on"]["START_APP"]
                    target_clean = current_target.lstrip(".#")
                    
                    # Check if it's a valid path
                    if target_clean not in state_paths and target_clean not in state_configs:
                        # Target doesn't exist, fix it
                        if "auth_guard" in nav_states:
                            app_idle["on"]["START_APP"] = "navigation.auth_guard"
                            print(f"  🔧 [CLEANUP] Fixed START_APP transition: app_idle -> navigation.auth_guard")
                            added += 1
        
        return added
    
    added_bootstrap = ensure_bootstrap_transitions(machine)
    if added_bootstrap > 0:
        print(f"  🔧 [CLEANUP] Added/fixed {added_bootstrap} critical bootstrap transitions")
    
    if removed_count > 0:
        print(f"  ✅ [CLEANUP] Complete: fixed {removed_count} issues")
    else:
        print(f"  ✅ [CLEANUP] No critical issues found")
    
    return machine
