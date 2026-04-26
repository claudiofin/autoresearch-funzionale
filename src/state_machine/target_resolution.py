"""Target resolution for state machine transitions.

Resolves relative targets (.name), caret syntax (^parent), branch name fixes,
and creates placeholder states for missing targets.
"""

from state_machine.constants import DEPTH_LIMITS
from state_machine.traversal import extract_target_string


def _resolve_relative_target(target: str, source_path: str, machine: dict) -> str:
    """Resolve a relative target (.name) to an absolute path.
    
    STRUCTURAL: resolves .app_idle from navigation.authenticating → navigation.app_idle
    
    FIX B2: When resolving relative targets (.ready, .error) within compound states,
    check if the resolved absolute path actually exists. If not, keep the relative form
    because the target is a sibling sub-state (e.g., loading → .ready within app_initial).
    
    FIX B8: Handle malformed relative targets like .benchmark_workflow.discovery.ready
    when source is workflows.benchmark_workflow.discovery.loading. The LLM sometimes
    includes the parent path in the relative target. We detect this and extract just
    the sibling name (.ready).
    
    The fuzzer handles relative targets by stripping the '.' prefix and looking for
    the state as a sibling sub-state. Resolving .ready → app_initial.ready breaks
    this because the fuzzer can't find 'app_initial.ready' as a flat key.
    
    Args:
        target: Target string (may start with .)
        source_path: Full path of the source state (e.g., "navigation.authenticating")
        machine: The full state machine dict
    
    Returns:
        Resolved absolute path (e.g., "navigation.app_idle") or original relative target
        if the resolved path doesn't exist (for sibling sub-state resolution)
    """
    if not target:
        return target
    
    if target.startswith("#"):
        return target[1:]
    
    if target.startswith("."):
        sibling_name = target[1:]
        parts = source_path.rsplit(".", 1)
        
        if len(parts) == 2:
            parent_path, current_state = parts
            
            # FIX E: Check if sibling_name is a root-level state BEFORE resolving as sibling
            # e.g., source = "dashboard.loading", target = ".app_initial"
            # app_initial is a root-level state, NOT a sibling of dashboard
            # So ".app_initial" should resolve to "app_initial" (root level), not "dashboard.app_initial"
            states = machine.get("states", {})
            if sibling_name in states:
                # sibling_name exists at root level — return it directly
                return sibling_name
            
            # FIX F: If sibling_name is a common state that doesn't exist at root level,
            # re-route to a valid default target
            # This handles cases like ".app_initial" when app_initial was removed by cleanup
            if sibling_name in ("app_initial", "app_idle", "app_loading", "app_success"):
                # Try to find a valid entry point
                entry_candidates = ["dashboard", "catalog", "offers", "alerts", "home", "main",
                                   "app_initial", "app_idle", "login", "session_expired"]
                for candidate in entry_candidates:
                    if candidate in states:
                        return candidate
                # If no candidate found, return first root-level state
                if states:
                    return next(iter(states))
            
            # FIX B8: Handle malformed relative targets
            # e.g., source = "workflows.benchmark_workflow.discovery.loading"
            #       target = ".benchmark_workflow.discovery.ready"
            # The sibling_name contains the parent path as prefix — strip it
            if sibling_name.startswith(parent_path.split(".")[-1] + "."):
                # sibling_name starts with the last component of parent_path
                # e.g., "benchmark_workflow.discovery.ready" starts with "benchmark_workflow."
                # Try to find the actual sibling by checking each level
                sibling_parts = sibling_name.split(".")
                for i, part in enumerate(sibling_parts):
                    # Check if remaining parts form a valid sibling path
                    remaining = ".".join(sibling_parts[i:])
                    candidate = f"{parent_path}.{remaining}"
                    if _path_exists(candidate, machine):
                        return candidate
                # If nothing found, try just the last component as sibling
                last_part = sibling_parts[-1]
                candidate = f"{parent_path}.{last_part}"
                if _path_exists(candidate, machine):
                    return candidate
                # Keep relative with just the last part
                return f".{last_part}"
            
            resolved = f"{parent_path}.{sibling_name}"
            # FIX: ALWAYS resolve relative targets to absolute paths.
            # The resolved path will exist after sub-state injection (Pattern Compiler).
            # Keeping relative targets breaks the validator which needs absolute paths.
            return resolved
        return sibling_name
    
    if "." in target:
        return target
    
    source_parts = source_path.split(".")
    if len(source_parts) >= 2:
        branch = source_parts[0]
        candidate = f"{branch}.{target}"
        states = machine.get("states", {})
        branch_config = states.get(branch, {})
        branch_states = branch_config.get("states", {})
        if target in branch_states:
            return candidate
    
    return target


def _path_exists(path: str, machine: dict) -> bool:
    """Check if a state path exists in the machine.
    
    FIX: Properly handles deeply nested paths like "auth_guard.loading.error_handler"
    by walking the full hierarchy.
    
    Args:
        path: State path to check
        machine: The full state machine dict
    
    Returns:
        True if the path exists
    """
    parts = path.split(".")
    states = machine.get("states", {})
    
    for i, part in enumerate(parts):
        if part in states:
            states = states[part].get("states", {})
        else:
            return False
    
    return True


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
    
    if "active_workflows" in states:
        if target == "#workflows.none":
            return "active_workflows.none"
        if target == "workflows.none":
            return "active_workflows.none"
        if target.startswith("#workflows.none."):
            return target.replace("#workflows.none.", "active_workflows.none.")
        if target.startswith("workflows.none."):
            return target.replace("workflows.none.", "active_workflows.none.")
    
    return target


def _fix_nonexistent_targets(target: str, machine: dict, source_branch: str = "", source_path: str = "") -> str:
    """Fix targets that reference non-existent branches/states.
    
    STRUCTURAL: maps common LLM errors to correct paths.
    Examples:
    - success.dashboard → navigation.success (success is a state, not a branch)
    - active_active_workflows.none → active_workflows.none (double prefix)
    - authenticating → navigation.authenticating (bare state name)
    - success.dashboard → .dashboard (if source is also under success — sibling)
    
    Args:
        target: Target string
        machine: The full state machine dict
        source_branch: The branch where the source state lives (for bare name resolution)
        source_path: Full path of the source state (for sibling detection)
    
    Returns:
        Fixed target
    """
    if not target:
        return target
    
    states = machine.get("states", {})
    
    if target.startswith("active_active_workflows."):
        return target.replace("active_active_workflows.", "active_workflows.")
    
    # SIBLING DETECTION: If source is under "success" and target is "success.X",
    # convert to relative ".X" (sibling transition)
    if source_path and "." in target:
        target_first_part = target.split(".")[0]
        source_parts = source_path.split(".")
        if len(source_parts) >= 2 and source_parts[0] == target_first_part:
            # Source and target share the same parent — use relative notation
            sibling_name = ".".join(target.split(".")[1:])
            return f".{sibling_name}"
    
    if target.startswith("success."):
        nav = states.get("navigation", {})
        nav_states = nav.get("states", {})
        if "success" in nav_states:
            return "navigation.success"
        nav_initial = nav.get("initial", "app_idle")
        return f"navigation.{nav_initial}"
    
    if target.startswith("empty."):
        nav = states.get("navigation", {})
        nav_states = nav.get("states", {})
        if "empty" in nav_states:
            return "navigation.empty"
    
    if target.startswith("loading."):
        nav = states.get("navigation", {})
        nav_states = nav.get("states", {})
        if "loading" in nav_states:
            return "navigation.loading"
    
    if target.startswith("error."):
        nav = states.get("navigation", {})
        nav_states = nav.get("states", {})
        if "error" in nav_states:
            return "navigation.error"
    
    # FIX: Handle navigation.* targets when navigation branch doesn't exist
    # This is the #1 cause of ORPHAN_TRANSITION errors
    if target.startswith("navigation."):
        nav = states.get("navigation", {})
        nav_states = nav.get("states", {})
        nav_initial = nav.get("initial", "app_initial")
        
        # If navigation branch exists, keep target as-is
        if nav_states:
            return target
        
        # Navigation doesn't exist - map to root-level equivalent
        nav_state_name = target.split(".", 1)[1] if "." in target else ""
        
        # Check if the target state exists at root level
        if nav_state_name in states:
            return nav_state_name
        
        # Check for common mappings: navigation.app_idle → app_idle (or dashboard, etc.)
        if nav_state_name in ("app_idle", "app_initial"):
            # Try to find an entry point at root level
            for candidate in ["app_initial", "app_idle", "dashboard", "home"]:
                if candidate in states:
                    return candidate
            # If no candidate found, return the first state that looks like an entry point
            for name, config in states.items():
                if isinstance(config, dict) and (config.get("states") or config.get("entry")):
                    return name
        
        # Fallback: return the navigation initial state name at root level
        if nav_initial in states:
            return nav_initial
        
        # Last resort: return first state at root level
        if states:
            return next(iter(states))
        
        return "app_initial"
    
    if "." not in target and not target.startswith("#") and not target.startswith("^"):
        if target in states:
            return target
        
        if source_branch and source_branch in states:
            branch_config = states[source_branch]
            branch_states = branch_config.get("states", {})
            if target in branch_states:
                return f"{source_branch}.{target}"
        
        nav = states.get("navigation", {})
        nav_states = nav.get("states", {})
        if target in nav_states:
            return f"navigation.{target}"
        
        wf = states.get("active_workflows", {})
        wf_states = wf.get("states", {})
        if target in wf_states:
            return f"active_workflows.{target}"
        
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
    
    resolved = target
    
    if resolved.startswith("#"):
        resolved = resolved[1:]
    
    if resolved.startswith("."):
        from state_machine.target_resolution import _resolve_relative_target
        resolved = _resolve_relative_target(resolved, source_path, machine)
    
    if resolved.startswith("^"):
        from state_machine.target_resolution import _resolve_caret_target
        resolved = _resolve_caret_target(resolved, source_path, machine)
        if resolved.startswith("#"):
            resolved = resolved[1:]
    
    resolved = _fix_workflows_none_target(resolved, machine)
    
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
    
    FIX: Skip creating placeholder states for:
    - Paths starting with '#' (these are ID references, not real paths)
    - Paths that are just a branch name (e.g., 'navigation' alone)
    - Paths where the target is a sub-state reference (e.g., 'app_idle.ready' when app_idle exists)
    
    Args:
        path: Full path (e.g., "navigation.app_idle")
        machine: The full state machine dict
    """
    # FIX: Don't create placeholder for '#' prefixed paths
    # These are ID references that should have been resolved earlier
    if path.startswith("#"):
        return
    
    parts = path.split(".")
    
    # FIX: Don't create placeholder for bare branch names
    if len(parts) == 1 and parts[0] in ("navigation", "workflows", "active_workflows"):
        return
    
    states = machine.get("states", {})
    
    # FIX: Check if this is a sub-state reference where parent exists
    # e.g., "app_idle.ready" when "navigation.app_idle" exists
    if len(parts) == 2 and parts[0] not in states:
        # Check if parent exists under any branch
        for branch_name, branch_config in states.items():
            if isinstance(branch_config, dict):
                branch_states = branch_config.get("states", {})
                if parts[0] in branch_states:
                    # Parent exists under a branch - this is a valid sub-state reference
                    # Don't create a placeholder at root level
                    return
    
    for i, part in enumerate(parts[:-1]):
        if part in states:
            if "states" not in states[part]:
                states[part]["states"] = {}
            states = states[part]["states"]
        else:
            states[part] = {
                "initial": parts[i + 1] if i + 1 < len(parts) - 1 else None,
                "states": {},
                "on": {}
            }
            states = states[part]["states"]
    
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
    limit = DEPTH_LIMITS["process_states"]
    
    def _process_states(states_dict: dict, prefix: str = "", depth: int = 0) -> None:
        if depth > limit:
            return
        
        for name, config in list(states_dict.items()):
            full_path = f"{prefix}.{name}" if prefix else name
            
            source_branch = ""
            if "." in full_path:
                source_branch = full_path.split(".")[0]
            
            transitions = config.get("on", {})
            for event, target in list(transitions.items()):
                target_str = extract_target_string(target)
                
                if not target_str:
                    continue
                
                if target_str.startswith("."):
                    resolved = _resolve_relative_target(target_str, full_path, machine)
                elif target_str.startswith("^"):
                    resolved = _resolve_caret_target(target_str, full_path, machine)
                    if resolved.startswith("#"):
                        resolved = resolved[1:]
                else:
                    resolved = target_str
                
                resolved = _fix_workflows_none_target(resolved, machine)
                resolved = _fix_nonexistent_targets(resolved, machine, source_branch, full_path)
                
                if isinstance(target, str):
                    transitions[event] = resolved
                elif isinstance(target, dict):
                    target["target"] = resolved
                elif isinstance(target, list):
                    for item in target:
                        if isinstance(item, dict):
                            item["target"] = resolved
                            break
                
                if not _ensure_target_exists(resolved, full_path, machine):
                    _create_placeholder_state(resolved, machine)
            
            if "states" in config:
                _process_states(config["states"], full_path, depth + 1)
    
    _process_states(states)
    
    def _ensure_initial(states_dict: dict, prefix: str = "", depth: int = 0) -> None:
        if depth > limit:
            return
        for name, config in states_dict.items():
            full_path = f"{prefix}.{name}" if prefix else name
            initial = config.get("initial")
            if initial and "states" in config:
                if initial not in config["states"]:
                    config["states"][initial] = {
                        "entry": [],
                        "exit": [],
                        "on": {}
                    }
                _ensure_initial(config["states"], full_path, depth + 1)
    
    _ensure_initial(states)
    
    return machine


def apply_target_crosscheck(machine: dict) -> dict:
    """Final cross-check: validate ALL transition targets exist in the machine.
    
    This is the SAFETY NET that runs AFTER all other resolution steps.
    Any transition pointing to a non-existent state is re-routed to a valid default.
    
    Prevents the "Ghost Arrow" problem: transitions that point to states that
    were never created or were removed by cleanup.
    
    Also validates '#' prefixed targets (ID references) by checking if the ID
    matches any state's explicit 'id' property.
    
    FIX: Uses _find_default_target() instead of hardcoded "navigation.app_idle"
    to handle machines without a navigation branch.
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with all invalid transitions re-routed
    """
    states = machine.get("states", {})
    limit = DEPTH_LIMITS["process_states"]
    
    def _collect_all_state_paths(states_dict: dict, prefix: str = "") -> set:
        """Collect all valid state paths in the machine."""
        paths = set()
        for name, config in states_dict.items():
            full_path = f"{prefix}.{name}" if prefix else name
            paths.add(full_path)
            # Also collect the explicit 'id' if present
            state_id = config.get("id")
            if state_id:
                paths.add(state_id)
            sub_states = config.get("states", {})
            if sub_states:
                paths.update(_collect_all_state_paths(sub_states, full_path))
        return paths
    
    def _find_default_target(states: dict) -> str:
        """Find a valid default target (first initial state in navigation branch).
        
        GENERIC: Uses the same logic as _find_first_valid_screen_state from injection.py
        to find a valid screen state, instead of hardcoding navigation.app_idle.
        
        FIX: Prioritizes finding ANY valid entry point, not just navigation branch.
        This handles machines that use flat structure (no navigation branch).
        """
        # 1. Try navigation branch first (if it exists)
        nav = states.get("navigation", {})
        nav_initial = nav.get("initial")
        if nav_initial:
            nav_states = nav.get("states", {})
            if nav_initial in nav_states:
                return f"navigation.{nav_initial}"
        # Fallback: find any state in navigation
        nav_states = nav.get("states", {})
        if nav_states:
            first_state = next(iter(nav_states))
            return f"navigation.{first_state}"
        
        # 2. Try root-level screen candidates FIRST (before branches)
        # This handles flat machines where dashboard, catalog, etc. are at root level
        entry_candidates = ["dashboard", "catalog", "offers", "alerts", "home", "main",
                           "app_initial", "app_idle", "app_loading", "app_success"]
        for candidate in entry_candidates:
            if candidate in states:
                return candidate
        
        # 3. Try any branch with sub-states (skip workflows)
        for branch_name, branch_config in states.items():
            if branch_name in ("workflows", "active_workflows"):
                continue
            if isinstance(branch_config, dict):
                branch_states = branch_config.get("states", {})
                if branch_states:
                    branch_initial = branch_config.get("initial")
                    if branch_initial and branch_initial in branch_states:
                        return f"{branch_name}.{branch_initial}"
                    first = next(iter(branch_states))
                    return f"{branch_name}.{first}"
        
        # 4. Last resort: return first state that has sub_states or entry actions
        for name, config in states.items():
            if isinstance(config, dict):
                if config.get("states") or config.get("entry"):
                    return name
        
        # Absolute last resort: return first state
        if states:
            return next(iter(states))
        
        return "dashboard"
    
    default_target = _find_default_target(states)
    
    def _crosscheck_states(states_dict: dict, prefix: str = "", depth: int = 0) -> None:
        if depth > limit:
            return
        
        for name, config in list(states_dict.items()):
            full_path = f"{prefix}.{name}" if prefix else name
            
            transitions = config.get("on", {})
            for event, target in list(transitions.items()):
                target_str = extract_target_string(target)
                if not target_str:
                    continue
                
                # Handle '#' prefixed targets (ID references)
                if target_str.startswith("#"):
                    id_ref = target_str[1:]  # Remove '#' prefix
                    # Check if this ID exists in our collected paths
                    if id_ref not in all_paths:
                        # The ID doesn't exist — strip '#' and use as path
                        # or re-route to default if path also doesn't exist
                        if id_ref in all_paths:
                            # It exists as a path, just remove '#'
                            if isinstance(target, str):
                                transitions[event] = id_ref
                            elif isinstance(target, dict):
                                target["target"] = id_ref
                            elif isinstance(target, list):
                                for item in target:
                                    if isinstance(item, dict):
                                        item["target"] = id_ref
                                        break
                        else:
                            # Neither ID nor path exists — re-route to default
                            if isinstance(target, str):
                                transitions[event] = default_target
                            elif isinstance(target, dict):
                                target["target"] = default_target
                            elif isinstance(target, list):
                                for item in target:
                                    if isinstance(item, dict):
                                        item["target"] = default_target
                                        break
                    continue
                
                # Skip relative targets (they'll be resolved by the runtime)
                if target_str.startswith("."):
                    continue
                
                # Check if target exists
                if target_str not in all_paths:
                    # Re-route to default
                    if isinstance(target, str):
                        transitions[event] = default_target
                    elif isinstance(target, dict):
                        target["target"] = default_target
                    elif isinstance(target, list):
                        for item in target:
                            if isinstance(item, dict):
                                item["target"] = default_target
                                break
            
            if "states" in config:
                _crosscheck_states(config["states"], full_path, depth + 1)
    
    # Collect all valid paths first (including explicit IDs)
    all_paths = _collect_all_state_paths(states)
    
    # Also add branch-level paths
    for branch_name, branch_config in states.items():
        all_paths.add(branch_name)
        branch_states = branch_config.get("states", {})
        for state_name in branch_states:
            all_paths.add(f"{branch_name}.{state_name}")
    
    _crosscheck_states(states)
    
    return machine
