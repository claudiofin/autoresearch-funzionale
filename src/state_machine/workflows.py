"""Workflow compound state building for state machines.

Builds hierarchical workflow states with internal micro-states for each step.
"""

from state_machine.traversal import collect_all_state_paths


def build_workflow_compound_state(workflow: dict, machine: dict = None) -> dict:
    """Build a compound state for a workflow.
    
    STRUCTURAL: resolves 'none' and navigation targets dynamically.
    Creates hierarchical state with internal micro-states for each step.
    
    Args:
        workflow: Analyst workflow dict with id, name, steps, etc.
        machine: Optional state machine dict for structural resolution
    
    Returns:
        XState compound state config
    """
    workflow_id = workflow["id"]
    steps = workflow.get("steps", [])
    cross_page_events = workflow.get("cross_page_events", [])
    completion_events = workflow.get("completion_events", ["COMPLETED", "CANCELLED"])
    
    if not steps:
        return {}
    
    # STRUCTURAL: find the "none" state dynamically
    none_target = "none"
    if machine:
        wf_branch = machine.get("states", {}).get("workflows") or machine.get("states", {}).get("active_workflows", {})
        wf_states = wf_branch.get("states", {})
        for state_name, state_config in wf_states.items():
            entry = state_config.get("entry", [])
            if any("hideWorkflow" in a for a in entry) or state_name == "none":
                none_target = state_name
                break
    
    # STRUCTURAL: find the navigation success state dynamically
    nav_success_prefix = "#navigation.success"
    if machine:
        nav = machine.get("states", {}).get("navigation", {})
        nav_states = nav.get("states", {})
        for state_name in nav_states:
            if state_name in ("success", "main", "home", "dashboard"):
                nav_success_prefix = f"#navigation.{state_name}"
                break
    
    initial_step = steps[0]
    state_config = {
        "initial": initial_step,
        "states": {},
        "on": {}
    }
    
    for i, step in enumerate(steps):
        step_config = {
            "entry": [f"show{step.title()}"],
            "exit": [f"hide{step.title()}"],
            "on": {}
        }
        
        if i < len(steps) - 1:
            next_step = steps[i + 1]
            trigger_event = cross_page_events[i] if i < len(cross_page_events) else "NEXT_STEP"
            step_config["on"][trigger_event] = next_step
        
        if i > 0:
            step_config["on"]["GO_BACK"] = steps[i - 1]
        else:
            step_config["on"]["GO_BACK"] = none_target
        
        step_config["on"]["CANCEL"] = none_target
        
        if i == len(steps) - 1:
            for completion_event in completion_events:
                step_config["on"][completion_event] = none_target
        
        state_config["states"][step] = step_config
    
    for event in cross_page_events:
        if event.startswith("NAVIGATE_"):
            target_page = event.replace("NAVIGATE_", "").lower()
            state_config["on"][event] = f"{nav_success_prefix}.{target_page}"
    
    return state_config


def add_workflows_to_machine(machine: dict, workflows: list):
    """Add workflow compound states to the workflows branch.
    
    Args:
        machine: The state machine dict
        workflows: List of workflow dicts
    """
    workflows_branch = machine.get("states", {}).get("workflows") or machine.get("states", {}).get("active_workflows")
    if not workflows_branch:
        return
    
    for workflow in workflows:
        workflow_id = workflow["id"]
        compound_state = build_workflow_compound_state(workflow)
        if compound_state:
            workflows_branch["states"][workflow_id] = compound_state