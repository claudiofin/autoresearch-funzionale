"""State machine builder - creates XState machine from LLM data.

Handles:
- Base machine generation
- State config building (flat and hierarchical)
- Transition addition with guard/action support
- XState action formatting (assign actions for context updates)
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


def generate_base_machine() -> dict:
    """Generate an empty base state machine."""
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
            nav_event = f"NAVIGATE_{sub_name.upper()}"
            for other_sub in sub_states:
                other_name = other_sub if isinstance(other_sub, str) else other_sub.get("name", "")
                if other_name != sub_name:
                    config["states"][other_name]["on"][nav_event] = f".{sub_name}"
    
    return config


def add_transitions(machine: dict, transitions: list):
    """Add transitions with support for guards and actions.
    
    Handles dot notation for hierarchical states (e.g., success.dashboard).
    Validates transition format and skips invalid entries.
    
    Args:
        machine: The state machine dict to modify.
        transitions: List of transition dicts from LLM.
    """
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
        actions = trans.get("actions", [])
        
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
            if guard or actions:
                transition = {"target": to_state}
                if guard:
                    transition["cond"] = guard
                if actions:
                    transition["actions"] = _format_xstate_actions(actions)
                target_dict[resolved_from]["on"][event] = transition
            else:
                target_dict[resolved_from]["on"][event] = to_state


def normalize_machine(machine: dict) -> dict:
    """Normalize machine: fix idle→app_idle, ensure app_idle exists.
    
    Args:
        machine: The state machine dict to normalize.
    
    Returns:
        Normalized machine dict.
    """
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