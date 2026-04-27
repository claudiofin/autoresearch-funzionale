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
    8. Adds generic navigation transitions
    9. Removes unreachable states
    10. Fixes compound states with empty states dict
    
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
    
    # Phase 1.5: Rename duplicate state names within navigation
    # Find all state names that appear at different paths and rename them
    def find_and_rename_duplicates(states_dict, prefix="", name_counts=None, name_paths=None):
        if name_counts is None:
            name_counts = {}
        if name_paths is None:
            name_paths = {}
        
        for name, config in list(states_dict.items()):
            full_path = f"{prefix}.{name}" if prefix else name
            
            # Count occurrences
            if name not in name_counts:
                name_counts[name] = 0
                name_paths[name] = []
            name_counts[name] += 1
            name_paths[name].append(full_path)
            
            # Recurse into sub-states
            if "states" in config:
                find_and_rename_duplicates(config["states"], full_path, name_counts, name_paths)
        
        return name_counts, name_paths
    
    # First pass: count all names
    name_counts, name_paths = find_and_rename_duplicates(nav_states, "navigation")
    
    # Find duplicates (names that appear more than once)
    # BUT: Skip standard compound state sub-states that are intentionally duplicated
    STANDARD_SUBSTATES = {"loading", "ready", "error", "error_handler"}
    
    duplicates = {}
    for name, paths in name_paths.items():
        if len(paths) > 1:
            # Only consider it a duplicate if it's NOT a standard substate
            # OR if it's a workflow-level state (like 'saving' in finalize steps)
            if name not in STANDARD_SUBSTATES:
                duplicates[name] = paths
            elif name in ["saving", "creating", "processing", "validating", "fetching"]:
                # These are workflow action states that might be duplicated
                duplicates[name] = paths
    
    if duplicates:
        print(f"  🧹 [CLEANUP] Found {len(duplicates)} duplicate state names to rename")
        
        # Build rename mapping: old_name -> new_name for duplicates
        rename_map = {}  # full_path -> new_name
        
        for name, paths in duplicates.items():
            print(f"  🧹 [CLEANUP] Duplicate '{name}' found at: {paths}")
            # Keep the first occurrence, rename the rest
            for i, path in enumerate(paths[1:], 1):
                # Generate unique name based on parent path
                parent_parts = path.split(".")
                if len(parent_parts) >= 2:
                    # Use parent state name as prefix
                    parent_name = parent_parts[-2] if len(parent_parts) > 1 else parent_parts[0]
                    new_name = f"{parent_name}_{name}"
                    
                    # Ensure uniqueness
                    counter = 1
                    original_new_name = new_name
                    while new_name in name_counts and new_name != name:
                        new_name = f"{original_new_name}_{counter}"
                        counter += 1
                    
                    rename_map[path] = new_name
                    print(f"  🔧 [CLEANUP] Will rename: {path} -> {new_name}")
        
        # Second pass: apply renames
        def apply_renames(states_dict, prefix=""):
            renamed = 0
            for name in list(states_dict.keys()):
                full_path = f"{prefix}.{name}" if prefix else name
                config = states_dict[name]
                
                # Check if this state needs to be renamed
                if full_path in rename_map:
                    new_name = rename_map[full_path]
                    print(f"  🔧 [CLEANUP] Renaming state: {full_path} -> {new_name}")
                    states_dict[new_name] = states_dict.pop(name)
                    name = new_name
                    renamed += 1
                
                # Recurse into sub-states
                if "states" in config:
                    renamed += apply_renames(config["states"], f"{prefix}.{name}" if prefix else name)
            return renamed
        
        renamed_count = apply_renames(nav_states, "navigation")
        removed_count += renamed_count
        
        # Phase 1.6: Update all transition targets to use renamed states
        def update_transition_targets(states_dict, prefix=""):
            for name, config in states_dict.items():
                full_path = f"{prefix}.{name}" if prefix else name
                
                if "on" in config:
                    for event, target in list(config["on"].items()):
                        if isinstance(target, str):
                            # Check if target needs to be updated
                            target_clean = target.lstrip(".#")
                            # Find if this target matches any renamed path
                            for old_path, new_name in rename_map.items():
                                if target_clean == old_path or target_clean.endswith(f".{old_path.split('.')[-1]}"):
                                    # Build new target path
                                    old_parts = old_path.split(".")
                                    if len(old_parts) > 1:
                                        parent_path = ".".join(old_parts[:-1])
                                        new_target = f"{parent_path}.{new_name}"
                                        if target != new_target:
                                            print(f"  🔧 [CLEANUP] Updated transition target: {full_path} --{event}--> {new_target}")
                                            config["on"][event] = new_target
                                            break
                        
                        elif isinstance(target, dict):
                            tgt = target.get("target", "")
                            tgt_clean = tgt.lstrip(".#")
                            for old_path, new_name in rename_map.items():
                                if tgt_clean == old_path or tgt_clean.endswith(f".{old_path.split('.')[-1]}"):
                                    old_parts = old_path.split(".")
                                    if len(old_parts) > 1:
                                        parent_path = ".".join(old_parts[:-1])
                                        new_target = f"{parent_path}.{new_name}"
                                        if tgt != new_target:
                                            print(f"  🔧 [CLEANUP] Updated transition target: {full_path} --{event}--> {new_target}")
                                            target["target"] = new_target
                                            break
                        
                        elif isinstance(target, list):
                            for t in target:
                                if isinstance(t, dict):
                                    tgt = t.get("target", "")
                                    tgt_clean = tgt.lstrip(".#")
                                    for old_path, new_name in rename_map.items():
                                        if tgt_clean == old_path or tgt_clean.endswith(f".{old_path.split('.')[-1]}"):
                                            old_parts = old_path.split(".")
                                            if len(old_parts) > 1:
                                                parent_path = ".".join(old_parts[:-1])
                                                new_target = f"{parent_path}.{new_name}"
                                                if tgt != new_target:
                                                    print(f"  🔧 [CLEANUP] Updated transition target: {full_path} --{event}--> {new_target}")
                                                    t["target"] = new_target
                                                    break
                                elif isinstance(t, str):
                                    t_clean = t.lstrip(".#")
                                    for old_path, new_name in rename_map.items():
                                        if t_clean == old_path or t_clean.endswith(f".{old_path.split('.')[-1]}"):
                                            old_parts = old_path.split(".")
                                            if len(old_parts) > 1:
                                                parent_path = ".".join(old_parts[:-1])
                                                new_target = f"{parent_path}.{new_name}"
                                                if t != new_target:
                                                    print(f"  🔧 [CLEANUP] Updated transition target: {full_path} --{event}--> {new_target}")
                                                    # Update in list
                                                    idx = target.index(t)
                                                    target[idx] = new_target
                                                    break
                
                # Recurse into sub-states
                if "states" in config:
                    update_transition_targets(config["states"], full_path)
        
        update_transition_targets(nav_states, "navigation")
    
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
                        # fallback: try to find any state that could be the entry point
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
    
    # Phase 8: Add generic navigation transitions based on state patterns
    def add_generic_navigation_transitions(nav_states):
        """Add navigation transitions based on common patterns found in the machine.
        
        This is a generic approach that doesn't hardcode specific state names,
        but instead analyzes the structure and adds appropriate transitions.
        """
        added = 0
        
        # Find all compound states that have loading/ready/error pattern
        def find_pattern_states(states_dict, prefix="", results=None):
            if results is None:
                results = []
            
            for name, config in states_dict.items():
                full_path = f"{prefix}.{name}" if prefix else name
                
                if "states" in config:
                    sub_states = config["states"]
                    # Check if this compound state has loading/ready/error pattern
                    has_loading = "loading" in sub_states
                    has_ready = "ready" in sub_states
                    has_error = "error" in sub_states
                    
                    if has_loading or has_ready or has_error:
                        results.append({
                            "name": name,
                            "path": full_path,
                            "config": config,
                            "has_loading": has_loading,
                            "has_ready": has_ready,
                            "has_error": has_error,
                            "sub_states": list(sub_states.keys())
                        })
                    
                    # Recurse
                    find_pattern_states(sub_states, full_path, results)
            
            return results
        
        pattern_states = find_pattern_states(nav_states, "navigation")
        
        # Group states by their parent to understand navigation structure
        parent_groups = {}
        for state_info in pattern_states:
            parent = state_info["path"].rsplit(".", 1)[0] if "." in state_info["path"] else "root"
            if parent not in parent_groups:
                parent_groups[parent] = []
            parent_groups[parent].append(state_info)
        
        # For each group of sibling states, add navigation between them
        for parent, siblings in parent_groups.items():
            if len(siblings) < 2:
                continue
            
            # Add NAVIGATE_TO_* transitions between siblings
            for i, source in enumerate(siblings):
                source_config = source["config"]
                
                # Ensure 'on' section exists
                if "on" not in source_config:
                    source_config["on"] = {}
                
                # Add transitions to other siblings
                for target in siblings:
                    if target["name"] == source["name"]:
                        continue
                    
                    event_name = f"NAVIGATE_TO_{target['name'].upper()}"
                    target_path = f"#{target['path']}"
                    
                    if event_name not in source_config["on"]:
                        source_config["on"][event_name] = target_path
                        added += 1
        
        # Add transitions from ready sub-state to parent transitions
        for state_info in pattern_states:
            if state_info["has_ready"]:
                ready_config = state_info["config"]["states"]["ready"]
                parent_config = state_info["config"]
                
                # Ensure ready has 'on' section
                if "on" not in ready_config:
                    ready_config["on"] = {}
                
                # Copy parent's transitions to ready (if ready doesn't have them)
                if "on" in parent_config:
                    for event, target in parent_config["on"].items():
                        if event not in ready_config["on"]:
                            ready_config["on"][event] = target
                            added += 1
        
        # NEW: Add navigation between ALL top-level states under navigation
        # This ensures auth_guard can navigate to dashboard, catalog, etc.
        top_level_states = []
        for name, config in nav_states.items():
            if name == "app_idle":
                continue  # Skip app_idle as it's the entry point
            if "states" in config:
                top_level_states.append({
                    "name": name,
                    "path": f"navigation.{name}",
                    "config": config
                })
        
        # Add navigation transitions between all top-level states
        if len(top_level_states) >= 2:
            for source in top_level_states:
                source_config = source["config"]
                
                # Ensure 'on' section exists at parent level
                if "on" not in source_config:
                    source_config["on"] = {}
                
                # Add transitions to other top-level states
                for target in top_level_states:
                    if target["name"] == source["name"]:
                        continue
                    
                    event_name = f"NAVIGATE_TO_{target['name'].upper()}"
                    target_path = f"#{target['path']}"
                    
                    if event_name not in source_config["on"]:
                        source_config["on"][event_name] = target_path
                        added += 1
                
                # Also add transitions from ALL sub-states (not just ready/loading)
                # This ensures that no matter which sub-state is active, navigation is possible
                def add_transitions_to_all_substates(config, source_name):
                    """Recursively add navigation transitions to ALL sub-states."""
                    local_added = 0
                    if "states" in config:
                        for sub_name, sub_config in config["states"].items():
                            # Add transitions to this sub-state
                            if "on" not in sub_config:
                                sub_config["on"] = {}
                            
                            for target in top_level_states:
                                if target["name"] == source_name:
                                    continue
                                
                                event_name = f"NAVIGATE_TO_{target['name'].upper()}"
                                target_path = f"#{target['path']}"
                                
                                if event_name not in sub_config["on"]:
                                    sub_config["on"][event_name] = target_path
                                    local_added += 1
                            
                            # Recurse into nested states
                            if "states" in sub_config:
                                local_added += add_transitions_to_all_substates(sub_config, source_name)
                    return local_added
                
                added += add_transitions_to_all_substates(source_config, source["name"])
        
        return added
    
    added_nav = add_generic_navigation_transitions(nav_states)
    if added_nav > 0:
        print(f"  🔧 [CLEANUP] Added {added_nav} generic navigation transitions")
    
    added_bootstrap = ensure_bootstrap_transitions(machine)
    if added_bootstrap > 0:
        print(f"  🔧 [CLEANUP] Added/fixed {added_bootstrap} critical bootstrap transitions")
    
    # Phase 9: Remove unreachable states
    def remove_unreachable_states(machine):
        """Remove states that are not reachable from the initial state."""
        import sys
        sys.path.insert(0, 'src')
        from state_machine.validation import _bfs_parallel, _collect_all_states_recursive
        
        # Get all states and reachable states
        all_states = _collect_all_states_recursive(machine.get("states", {}))
        reachable = _bfs_parallel(machine)
        
        unreachable = set(all_states.keys()) - reachable
        
        if not unreachable:
            return 0
        
        print(f"  🧹 [CLEANUP] Found {len(unreachable)} unreachable states to remove")
        
        # Remove unreachable states from the machine
        def remove_states(states_dict, prefix=""):
            removed = 0
            for name in list(states_dict.keys()):
                full_path = f"{prefix}.{name}" if prefix else name
                
                if full_path in unreachable:
                    print(f"  🧹 [CLEANUP] Removed unreachable state: {full_path}")
                    del states_dict[name]
                    removed += 1
                elif "states" in states_dict[name]:
                    removed += remove_states(states_dict[name]["states"], full_path)
            
            return removed
        
        nav_states = machine.get("states", {}).get("navigation", {}).get("states", {})
        removed = remove_states(nav_states, "navigation")
        
        # Also remove from active_workflows if it exists
        aw_states = machine.get("states", {}).get("active_workflows", {}).get("states", {})
        if aw_states:
            removed += remove_states(aw_states, "active_workflows")
        
        return removed
    
    removed_unreachable = remove_unreachable_states(machine)
    if removed_unreachable > 0:
        print(f"  🧹 [CLEANUP] Removed {removed_unreachable} unreachable states")
    
    # Phase 10: Fix compound states with empty states dict
    def fix_empty_compound_states(states_dict, prefix=""):
        """Convert compound states with empty states dict to atomic states."""
        fixed = 0
        for name, config in list(states_dict.items()):
            full_path = f"{prefix}.{name}" if prefix else name
            
            # Check if this is a compound state with empty states
            if "states" in config:
                if not config["states"]:
                    # Empty states dict - convert to atomic state
                    print(f"  🔧 [CLEANUP] Converting empty compound to atomic: {full_path}")
                    del config["states"]
                    if "initial" in config:
                        del config["initial"]
                    fixed += 1
                else:
                    # Recurse into sub-states
                    fixed += fix_empty_compound_states(config["states"], full_path)
        
        return fixed
    
    fixed_empty = fix_empty_compound_states(nav_states, "navigation")
    if fixed_empty > 0:
        print(f"  🔧 [CLEANUP] Fixed {fixed_empty} empty compound states")
    
    if removed_count > 0 or removed_unreachable > 0 or fixed_empty > 0:
        print(f"  ✅ [CLEANUP] Complete: fixed {removed_count + removed_unreachable + fixed_empty} issues")
    else:
        print(f"  ✅ [CLEANUP] No critical issues found")
    
    return machine
