"""Transition management for state machines.

Adding transitions to machines, with canonical target resolution.
"""

from state_machine.constants import XSTATE_ACTION_MAP
from state_machine.traversal import collect_all_state_paths, resolve_canonical_target


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


def add_transitions(machine: dict, transitions: list):
    """Add transitions with canonical target resolution.
    
    Uses specificity-based resolution to handle ambiguous targets.
    
    Args:
        machine: The state machine dict
        transitions: List of transition dicts from LLM
    """
    all_paths = collect_all_state_paths(machine.get("states", {}))
    
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
            resolved_target = resolve_canonical_target(to_state, from_state, all_paths)
            
            # SIBLING OPTIMIZATION: If target is under the same parent as source,
            # use relative notation (.sibling) instead of absolute (parent.sibling)
            # This is what XState expects for sibling transitions
            if "." in from_state and not resolved_target.startswith("#"):
                source_parent = from_state.rsplit(".", 1)[0]
                if resolved_target.startswith(source_parent + "."):
                    sibling_name = resolved_target[len(source_parent) + 1:]
                    resolved_target = f".{sibling_name}"
            
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
    
    all_paths = collect_all_state_paths(machine.get("states", {}))
    
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
            resolved_target = resolve_canonical_target(to_state, from_state, all_paths)
            
            # SIBLING OPTIMIZATION: If target is under the same parent as source,
            # use relative notation (.sibling) instead of absolute (parent.sibling)
            if "." in from_state and not resolved_target.startswith("#"):
                source_parent = from_state.rsplit(".", 1)[0]
                if resolved_target.startswith(source_parent + "."):
                    sibling_name = resolved_target[len(source_parent) + 1:]
                    resolved_target = f".{sibling_name}"
            
            if guard or actions:
                transition = {"target": resolved_target}
                if guard:
                    transition["cond"] = guard
                if actions:
                    transition["actions"] = _format_xstate_actions(actions)
                target_dict[resolved_from]["on"][event] = transition
            else:
                target_dict[resolved_from]["on"][event] = resolved_target
