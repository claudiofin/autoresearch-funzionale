"""State machine builder - creates XState machine from LLM data.

Handles:
- Base machine generation (parallel or flat)
- State config building (flat and hierarchical)
- Transition addition with guard/action support
- XState action formatting (assign actions for context updates)
- State deduplication (prevents "Schizofrenia del JSON")

Key fix: States are now written ONLY to their canonical path.
No more duplicate states appearing in both navigation.success.X AND as flat states.
"""

import json


def _format_xstate_actions(actions_list: list) -> list:
    """Format textual actions into valid XState v5 actions.
    
    Converts action strings like 'incrementRetryCount' into XState assign actions
    that actually update the machine context.
    
    Args:
        actions_list: List of action strings from LLM (e.g., ['incrementRetryCount', 'show_toast'])
    
    Returns:
        List of XState-compatible actions (strings and/or assign objects).
    """
    formatted = []
    for action in actions_list:
        if action == "incrementRetryCount":
            formatted.append({
                "type": "assign",
                "assignment": {
                    "retryCount": lambda ctx: ctx.get("retryCount", 0) + 1
                }
            })
        elif action == "setPreviousState":
            formatted.append({
                "type": "assign",
                "assignment": {
                    "previousState": lambda ctx, evt, meta: meta.state.value
                }
            })
        else:
            # Keep as string for side-effect actions (show_toast, log, etc.)
            formatted.append(action)
    return formatted


def generate_base_machine(use_parallel: bool = True) -> dict:
    """Generate an empty base state machine.
    
    Args:
        use_parallel: If True, creates parallel states architecture with
                      'navigation' and 'active_workflows' branches.
                      If False, creates flat architecture (legacy).
    """
    if use_parallel:
        return {
            "id": "appFlow",
            "type": "parallel",
            "context": {"user": None, "errors": [], "retryCount": 0, "previousState": None},
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "on": {},  # ← Added: compound state needs 'on'
                    "states": {}
                },
                "active_workflows": {
                    "initial": "none",
                    "on": {},  # ← Added: compound state needs 'on'
                    "states": {
                        "none": {}
                    }
                }
            }
        }
    else:
        return {
            "id": "appFlow",
            "initial": "app_idle",
            "context": {"user": None, "errors": [], "retryCount": 0, "previousState": None},
            "states": {}
        }


def build_state_config(state: dict) -> dict:
    """Build XState state config from LLM state dict.
    
    Supports hierarchical states: if 'sub_states' is present and non-empty,
    creates nested states with an 'initial' sub-state and navigation events.
    
    Args:
        state: LLM-generated state dict with name, entry_actions, exit_actions, sub_states.
    
    Returns:
        XState-compatible state config dict.
    """
    config = {
        "entry": state.get("entry_actions", []),
        "exit": state.get("exit_actions", []),
        "on": {}
    }
    
    sub_states = state.get("sub_states", [])
    if sub_states:
        initial_sub = state.get("initial_sub_state") or sub_states[0]
        if isinstance(initial_sub, dict):
            initial_sub = initial_sub.get("name", sub_states[0] if isinstance(sub_states[0], str) else "")
        
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
    
    return config


def _resolve_state_target(target: str, from_state_path: str, all_state_paths: set) -> str:
    """Resolve a transition target to its canonical full path.
    
    This prevents orphan transitions by resolving relative/sibling references
    to their actual canonical paths.
    
    Args:
        target: The target string from the transition (e.g., ".dashboard", "success", "#navigation.loading")
        from_state_path: The full path of the source state
        all_state_paths: Set of all valid state paths in the machine
    
    Returns:
        The resolved canonical path, or the original target if unresolvable.
    """
    if not target:
        return target
    
    # Cross-branch reference (# prefix) - already canonical
    if target.startswith("#"):
        return target[1:]
    
    # Relative reference (. prefix)
    if target.startswith("."):
        parts = from_state_path.split(".")
        if len(parts) > 1:
            parent = ".".join(parts[:-1])
            resolved = f"{parent}{target}"
            if resolved in all_state_paths:
                return resolved
        # Fallback: try as root-level
        root_target = target[1:]
        if root_target in all_state_paths:
            return root_target
        return target
    
    # Absolute reference (contains .)
    if "." in target:
        if target in all_state_paths:
            return target
        # Try to find the state by searching
        for path in all_state_paths:
            if path.endswith(f".{target}"):
                return path
        return target
    
    # Sibling or root-level reference
    # First try same parent
    parts = from_state_path.split(".")
    if len(parts) > 1:
        parent = ".".join(parts[:-1])
        candidate = f"{parent}.{target}"
        if candidate in all_state_paths:
            return candidate
    
    # Try as root-level
    if target in all_state_paths:
        return target
    
    # Last resort: search for any state ending with this name
    for path in all_state_paths:
        if path.split(".")[-1] == target:
            return path
    
    return target


def add_transitions(machine: dict, transitions: list):
    """Add transitions with support for guards and actions.
    
    Handles dot notation for hierarchical states (e.g., success.dashboard).
    Validates transition format and skips invalid entries.
    
    FIX: Now resolves targets to their canonical paths to prevent orphans.
    
    Args:
        machine: The state machine dict to modify.
        transitions: List of transition dicts from LLM.
    """
    # Collect all valid state paths for resolution
    all_paths = _collect_state_paths(machine.get("states", {}))
    
    for i, trans in enumerate(transitions):
        # Validate required fields — skip invalid transitions
        if "from_state" not in trans:
            print(f"  ⚠️  Skipping transition #{i}: missing 'from_state' — {trans}")
            continue
        if "to_state" not in trans:
            print(f"  ⚠️  Skipping transition #{i}: missing 'to_state' — {trans}")
            continue
        if "event" not in trans:
            print(f"  ⚠️  Skipping transition #{i}: missing 'event' — {trans}")
            continue
        
        from_state = trans["from_state"]
        to_state = trans["to_state"]
        event = trans["event"]
        guard = trans.get("guard") or trans.get("cond")
        actions = trans.get("actions") or trans.get("action", [])
        if isinstance(actions, str):
            actions = [actions]
        
        # Resolve dot notation (e.g., success.dashboard -> parent='success', child='dashboard')
        target_dict = machine["states"]
        resolved_from = from_state
        if "." in from_state:
            parts = from_state.split(".")
            parent = parts[0]
            child = parts[1]
            if parent in machine["states"] and "states" in machine["states"][parent] and child in machine["states"][parent]["states"]:
                target_dict = machine["states"][parent]["states"]
                resolved_from = child
                if not to_state.startswith("."):
                    to_state = f".{to_state}" if "." not in to_state else to_state
        
        if resolved_from in target_dict:
            # Resolve the target to its canonical path
            resolved_target = _resolve_state_target(to_state, from_state, all_paths)
            
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
    """Add transitions to the navigation branch of a parallel state machine.
    
    For parallel architecture, transitions need to be added to the navigation branch.
    Handles dot notation for hierarchical states within the navigation branch.
    
    FIX: Now resolves targets to their canonical paths to prevent orphans.
    
    Args:
        machine: The state machine dict (must have parallel structure).
        transitions: List of transition dicts from LLM.
    """
    nav_branch = machine.get("states", {}).get("navigation", {})
    if not nav_branch:
        return
    
    # Collect all valid state paths for resolution
    all_paths = _collect_state_paths(machine.get("states", {}))
    
    for i, trans in enumerate(transitions):
        # Validate required fields — skip invalid transitions
        if "from_state" not in trans:
            continue
        if "to_state" not in trans:
            continue
        if "event" not in trans:
            continue
        
        from_state = trans["from_state"]
        to_state = trans["to_state"]
        event = trans["event"]
        guard = trans.get("guard") or trans.get("cond")
        actions = trans.get("actions") or trans.get("action", [])
        if isinstance(actions, str):
            actions = [actions]
        
        # Resolve dot notation within navigation branch
        target_dict = nav_branch.get("states", {})
        resolved_from = from_state
        if "." in from_state:
            parts = from_state.split(".")
            parent = parts[0]
            child = parts[1]
            if parent in target_dict and "states" in target_dict[parent] and child in target_dict[parent]["states"]:
                target_dict = target_dict[parent]["states"]
                resolved_from = child
                if not to_state.startswith("."):
                    to_state = f".{to_state}" if "." not in to_state else to_state
        
        if resolved_from in target_dict:
            # Resolve the target to its canonical path
            resolved_target = _resolve_state_target(to_state, from_state, all_paths)
            
            if guard or actions:
                transition = {"target": resolved_target}
                if guard:
                    transition["cond"] = guard
                if actions:
                    transition["actions"] = _format_xstate_actions(actions)
                target_dict[resolved_from]["on"][event] = transition
            else:
                target_dict[resolved_from]["on"][event] = resolved_target


def _collect_state_paths(states: dict, prefix: str = "") -> set:
    """Collect all state paths in the machine for resolution.
    
    Args:
        states: The states dict to traverse
        prefix: Current path prefix
    
    Returns:
        Set of all state paths (e.g., {"navigation.app_idle", "navigation.success.dashboard"})
    """
    paths = set()
    for name, config in states.items():
        full_path = f"{prefix}.{name}" if prefix else name
        paths.add(full_path)
        if "states" in config and isinstance(config["states"], dict):
            paths.update(_collect_state_paths(config["states"], full_path))
    return paths


def build_workflow_compound_state(workflow: dict) -> dict:
    """Build a compound state for a workflow from analyst suggestion.
    
    Creates a hierarchical state with internal micro-states for each workflow step.
    Each step has entry actions and transitions to next/previous/none states.
    
    Args:
        workflow: Analyst workflow dict with id, name, steps, cross_page_events, completion_events.
    
    Returns:
        XState compound state config dict.
    """
    workflow_id = workflow["id"]
    steps = workflow.get("steps", [])
    cross_page_events = workflow.get("cross_page_events", [])
    completion_events = workflow.get("completion_events", ["COMPLETED", "CANCELLED"])
    
    if not steps:
        return {}
    
    initial_step = steps[0]
    state_config = {
        "initial": initial_step,
        "states": {},
        "on": {}
    }
    
    # Build internal micro-states for each step
    for i, step in enumerate(steps):
        step_config = {
            "entry": [f"show{step.title()}"],
            "exit": [f"hide{step.title()}"],
            "on": {}
        }
        
        # Add transition to next step
        if i < len(steps) - 1:
            next_step = steps[i + 1]
            # Determine the event that triggers this transition
            if i < len(cross_page_events):
                trigger_event = cross_page_events[i]
            else:
                trigger_event = f"NEXT_STEP"
            step_config["on"][trigger_event] = next_step
        
        # Add GO_BACK transition to previous step or none
        if i > 0:
            prev_step = steps[i - 1]
            step_config["on"]["GO_BACK"] = prev_step
        else:
            step_config["on"]["GO_BACK"] = "none"
        
        # Add CANCEL transition to none for all steps
        step_config["on"]["CANCEL"] = "none"
        
        # Add completion events for the last step
        if i == len(steps) - 1:
            for completion_event in completion_events:
                step_config["on"][completion_event] = "none"
        
        state_config["states"][step] = step_config
    
    # Add cross-page navigation events at workflow level
    for event in cross_page_events:
        if event.startswith("NAVIGATE_"):
            # Extract target page from event name
            target_page = event.replace("NAVIGATE_", "").lower()
            state_config["on"][event] = f"#navigation.success.{target_page}"
    
    return state_config


def add_workflows_to_machine(machine: dict, workflows: list):
    """Add workflow compound states to the active_workflows branch.
    
    Args:
        machine: The state machine dict (must have parallel structure).
        workflows: List of workflow dicts from analyst suggestions.
    """
    if "active_workflows" not in machine.get("states", {}):
        return
    
    workflows_branch = machine["states"]["active_workflows"]
    
    for workflow in workflows:
        workflow_id = workflow["id"]
        compound_state = build_workflow_compound_state(workflow)
        if compound_state:
            workflows_branch["states"][workflow_id] = compound_state


def normalize_machine(machine: dict) -> dict:
    """Normalize machine: fix idle→app_idle, ensure app_idle exists.
    
    Handles both parallel and flat architectures.
    
    FIX: Now also removes duplicate states that appear in multiple locations.
    The canonical location for navigation states is under navigation.*
    The canonical location for workflow states is under active_workflows.*
    
    Args:
        machine: The state machine dict to normalize.
    
    Returns:
        Normalized machine dict.
    """
    # Handle parallel architecture
    if machine.get("type") == "parallel" and "navigation" in machine.get("states", {}):
        nav_branch = machine["states"]["navigation"]
        
        # Fix: if LLM used 'idle' instead of 'app_idle', normalize
        if "idle" in nav_branch.get("states", {}) and nav_branch.get("initial") == "app_idle":
            nav_branch["states"]["app_idle"] = nav_branch["states"].pop("idle")
            for state_config in nav_branch["states"].values():
                for event, target in list(state_config.get("on", {}).items()):
                    if target == "idle":
                        state_config["on"][event] = "app_idle"
        
        # Fix: ensure app_idle exists
        if "app_idle" not in nav_branch.get("states", {}):
            nav_branch["states"]["app_idle"] = {"entry": [], "exit": [], "on": {}}
        
        # FIX: Remove duplicate states that appear at root level
        # If a state exists both under navigation.* and at root, keep only the navigation.* version
        root_states = machine.get("states", {})
        nav_states = nav_branch.get("states", {})
        
        # States that should ONLY exist under navigation (not at root)
        navigation_only_states = {
            "app_idle", "authenticating", "loading", "success", "empty",
            "error", "session_expired", "dashboard", "catalog", "offers",
            "alerts", "benchmark", "active_workflows"
        }
        
        for state_name in navigation_only_states:
            if state_name in root_states and state_name != "navigation" and state_name != "active_workflows":
                # This state exists at root level but should only be under navigation
                # Check if it also exists under navigation
                if state_name in nav_states:
                    # Remove the root-level duplicate
                    del root_states[state_name]
        
        # Also clean up states under navigation.success that duplicate navigation.*
        success_states = nav_states.get("success", {}).get("states", {})
        if success_states:
            for state_name in list(success_states.keys()):
                if state_name in nav_states and state_name in navigation_only_states:
                    # Remove the duplicate under success
                    del success_states[state_name]
    
    else:
        # Handle flat architecture (legacy)
        # Fix: if LLM used 'idle' instead of 'app_idle', normalize
        if "idle" in machine["states"] and machine["initial"] == "app_idle":
            machine["states"]["app_idle"] = machine["states"].pop("idle")
            for state_config in machine["states"].values():
                for event, target in list(state_config.get("on", {}).items()):
                    if target == "idle":
                        state_config["on"][event] = "app_idle"
        
        # Fix: ensure app_idle exists
        if "app_idle" not in machine["states"]:
            machine["states"]["app_idle"] = {"entry": [], "exit": [], "on": {}}
    
    return machine


def deduplicate_machine(machine: dict) -> dict:
    """Remove duplicate states from the machine.
    
    This is the "Schizofrenia del JSON" fix. When the LLM generates states
    that appear in multiple locations (e.g., dashboard under both
    navigation.success.dashboard AND as a flat state), this function
    keeps only the canonical location.
    
    Canonical locations:
    - Navigation states: navigation.* (not at root, not under navigation.success)
    - Workflow states: active_workflows.* (not at root, not under navigation.active_workflows)
    
    Args:
        machine: The state machine dict to deduplicate.
    
    Returns:
        Deduplicated machine dict.
    """
    if machine.get("type") != "parallel":
        return machine
    
    root_states = machine.get("states", {})
    nav_branch = root_states.get("navigation", {})
    nav_states = nav_branch.get("states", {})
    workflows_branch = root_states.get("active_workflows", {})
    workflow_states = workflows_branch.get("states", {})
    
    # Track which states we've seen and their canonical paths
    seen_states = {}
    
    # First pass: record canonical locations
    # Navigation states are canonical under navigation.*
    for name in nav_states:
        if name not in ("success", "active_workflows"):  # Skip compound containers
            seen_states[name] = f"navigation.{name}"
    
    # Workflow states are canonical under active_workflows.*
    for name in workflow_states:
        seen_states[name] = f"active_workflows.{name}"
    
    # Second pass: remove duplicates at root level
    states_to_remove = []
    for name in root_states:
        if name in ("navigation", "active_workflows"):
            continue  # Skip compound containers
        if name in seen_states:
            states_to_remove.append(name)
    
    for name in states_to_remove:
        del root_states[name]
    
    # Third pass: remove duplicates under navigation.success
    success_states = nav_states.get("success", {}).get("states", {})
    if success_states:
        states_to_remove = []
        for name in success_states:
            if name in seen_states:
                states_to_remove.append(name)
        for name in states_to_remove:
            del success_states[name]
    
    # Fourth pass: remove duplicates under navigation.active_workflows
    nav_workflow_states = nav_states.get("active_workflows", {}).get("states", {})
    if nav_workflow_states:
        states_to_remove = []
        for name in nav_workflow_states:
            if name in seen_states:
                states_to_remove.append(name)
        for name in states_to_remove:
            del nav_workflow_states[name]
    
    return machine