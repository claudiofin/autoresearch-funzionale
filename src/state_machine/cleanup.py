"""Cleanup utilities for state machines.

Dead state removal, specificity deduplication.
"""

from state_machine.constants import DEPTH_LIMITS
from state_machine.traversal import bfs_reachable, extract_target_string


def apply_specificity_dedup(machine: dict) -> dict:
    """Remove duplicate states by keeping the most specific version.
    
    When multiple states have the same name (e.g., from different LLM passes),
    keep the one with the most transitions/actions (highest specificity).
    
    Args:
        machine: The state machine dict
    
    Returns:
        Deduplicated machine
    """
    states = machine.get("states", {})
    limit = DEPTH_LIMITS["dedup"]
    
    def _dedup_states(states_dict: dict, depth: int = 0) -> None:
        if depth > limit:
            return
        
        name_counts = {}
        for name in states_dict:
            name_counts[name] = name_counts.get(name, 0) + 1
        
        if all(count == 1 for count in name_counts.values()):
            for name, config in states_dict.items():
                if isinstance(config, dict) and "states" in config:
                    _dedup_states(config["states"], depth + 1)
            return
        
        for name, config in states_dict.items():
            if isinstance(config, dict) and "states" in config:
                _dedup_states(config["states"], depth + 1)
    
    _dedup_states(states)
    return machine


def apply_dead_end_pruning(machine: dict) -> dict:
    """Add emergency exit transitions to dead-end states.
    
    If a state has no transitions (on: {}) and is not a final state
    (like success, empty), add CANCEL -> first valid screen state.
    
    This prevents the "Ghost Ship" problem where states exist but you can't leave them.
    
    GENERIC: Uses _find_first_valid_screen_state instead of hardcoding navigation.{initial}.
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with dead-end states having emergency exits
    """
    from state_machine.injection import _find_first_valid_screen_state
    
    states = machine.get("states", {})
    
    # GENERIC: Find first valid screen state instead of hardcoding navigation.app_idle
    default_exit = _find_first_valid_screen_state(machine)
    
    # States that are allowed to be dead-ends (final states)
    final_states = {"success", "empty", "session_expired", "max_retries_exceeded",
                    "workflow_idle", "none", "error_handler"}
    
    def _prune(states_dict: dict, prefix: str = "", depth: int = 0) -> None:
        if depth > 10:
            return
        
        for name, config in list(states_dict.items()):
            full_path = f"{prefix}.{name}" if prefix else name
            transitions = config.get("on", {})
            sub_states = config.get("states", {})
            
            # Leaf state with no transitions and not a final state
            if not sub_states and not transitions and name not in final_states:
                config["on"] = {"CANCEL": default_exit}
            
            if sub_states:
                _prune(sub_states, full_path, depth + 1)
    
    _prune(states)
    return machine


def apply_dead_state_cleanup(machine: dict) -> dict:
    """Remove or connect unreachable states.
    
    States that can't be reached from the initial state are either:
    - Connected (if they have entry actions — likely important)
    - Removed (if they're truly dead)
    
    FIX: Do NOT remove states that are direct children of parallel branches.
    Parallel branches (like 'navigation', 'active_workflows') may not have
    an initial state set, making all their children appear unreachable via BFS.
    These states are "structurally reachable" and should be preserved.
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with dead states cleaned up
    """
    from state_machine.builder import get_machine_type
    
    reachable = bfs_reachable(machine)
    states = machine.get("states", {})
    limit = DEPTH_LIMITS["cleanup"]
    machine_type = get_machine_type(machine)
    
    # Collect all state names that exist under parallel branches
    # These should NOT be removed even if unreachable via BFS
    structurally_reachable = set()
    if machine_type == "parallel":
        for branch_name, branch_config in states.items():
            if isinstance(branch_config, dict):
                branch_states = branch_config.get("states", {})
                for sub_name in branch_states:
                    structurally_reachable.add(sub_name)
                    # Also add nested states
                    sub_config = branch_states[sub_name]
                    if isinstance(sub_config, dict):
                        nested = sub_config.get("states", {})
                        for nested_name in nested:
                            structurally_reachable.add(f"{sub_name}.{nested_name}")
    
    def _cleanup(states_dict: dict, prefix: str = "", depth: int = 0) -> None:
        if depth > limit:
            return
        
        to_remove = []
        
        for name, config in states_dict.items():
            if not isinstance(config, dict):
                continue
            full_path = f"{prefix}.{name}" if prefix else name
            
            # FIX: Skip removal for structurally reachable states in parallel machines
            if machine_type == "parallel" and name in structurally_reachable:
                # Don't remove, but still recurse into sub-states
                if "states" in config:
                    _cleanup(config["states"], full_path, depth + 1)
                continue
            
            if full_path not in reachable and name not in ("error_handler",):
                entry_actions = config.get("entry", [])
                if not entry_actions:
                    to_remove.append(name)
            
            if "states" in config:
                _cleanup(config["states"], full_path, depth + 1)
        
        for name in to_remove:
            del states_dict[name]
    
    _cleanup(states)
    return machine


def apply_phantom_state_cleanup(machine: dict) -> dict:
    """Remove phantom states that were incorrectly created as placeholders.
    
    FIX: Removes states that should never exist at the root level:
    - States with '#' in their name (these are ID references, not real states)
    - States with empty string name
    - States that are duplicates of states already under a branch
      (e.g., 'completed' at root when 'navigation.purchase_group_workflow.completed' exists)
    - States that are sub-state names (loading, ready, error, error_handler) at root level
    
    FIX: Branch states (navigation, active_workflows) that have 'states' sub-dict
    are NOT phantoms — they are structural branches and must be preserved.
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with phantom states removed
    """
    states = machine.get("states", {})
    
    # Names that should never exist at root level (they're sub-state names)
    sub_state_names = {"loading", "ready", "error", "error_handler", "calculating", "fetching", "submitting"}
    
    # Collect all state names that exist under branches
    branch_state_names = set()
    for branch_name, branch_config in states.items():
        if isinstance(branch_config, dict):
            branch_states = branch_config.get("states", {})
            for sub_name in branch_states:
                branch_state_names.add(sub_name)
                # Also collect nested state names
                sub_states = branch_states[sub_name].get("states", {})
                for nested_name in sub_states:
                    branch_state_names.add(nested_name)
    
    to_remove = []
    
    for name, config in states.items():
        # Remove states with '#' in name
        if "#" in name:
            to_remove.append(name)
            continue
        
        # Remove empty string name
        if name == "":
            to_remove.append(name)
            continue
        
        # Remove sub-state names at root level
        if name in sub_state_names:
            to_remove.append(name)
            continue
        
        # FIX: Branch states (navigation, active_workflows) that have 'states' sub-dict
        # are structural branches, NOT phantoms. Preserve them.
        if isinstance(config, dict) and "states" in config:
            # This is a branch with sub-states — not a phantom
            continue
        
        # Remove states that are duplicates of branch states
        # Only remove if the state has no entry/exit/on/states (pure phantom)
        if name in branch_state_names:
            entry = config.get("entry", [])
            exit_actions = config.get("exit", [])
            on = config.get("on", {})
            has_sub_states = "states" in config and bool(config["states"])
            has_content = bool(entry) or bool(exit_actions) or bool(on) or has_sub_states
            if not has_content:
                to_remove.append(name)
    
    for name in to_remove:
        if name in states:
            del states[name]
    
    return machine


def apply_workflow_dedup(machine: dict) -> dict:
    """Remove duplicate workflow states at root level when they exist in active_workflows.
    
    FIX: The LLM sometimes generates workflow states both at root level AND inside
    the active_workflows branch. This creates duplicate states (e.g., benchmark_workflow
    at root AND active_workflows.benchmark_workflow).
    
    This function:
    1. Removes the 'workflows' branch when 'active_workflows' exists (workflows is a placeholder)
    2. Removes root-level states that duplicate workflow names
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with duplicate workflow states removed
    """
    states = machine.get("states", {})
    
    # Check if active_workflows branch exists
    active_wf = states.get("active_workflows", {})
    active_wf_states = active_wf.get("states", {})
    
    if not active_wf_states:
        # No active_workflows branch — nothing to dedup
        return machine
    
    # FIX: Remove the 'workflows' branch entirely when 'active_workflows' exists
    # The 'workflows' branch is a placeholder that duplicates active_workflows
    if "workflows" in states:
        del states["workflows"]
    
    # Collect all workflow state names from active_workflows
    workflow_names = set(active_wf_states.keys())
    
    # Remove root-level states that duplicate workflow names
    to_remove = []
    for name in workflow_names:
        if name in states and name not in ("active_workflows", "workflows"):
            # This is a root-level state that duplicates a workflow
            # Check if it's a compound state (has sub-states) — if so, it's likely a real screen
            config = states[name]
            if isinstance(config, dict):
                sub_states = config.get("states", {})
                # If it has sub-states that match workflow sub-states, it's a duplicate
                if sub_states:
                    # Check if sub-states overlap with active_workflows sub-states
                    wf_config = active_wf_states.get(name, {})
                    wf_sub_states = wf_config.get("states", {}) if isinstance(wf_config, dict) else {}
                    if wf_sub_states:
                        # Both have sub-states — root level is a duplicate
                        to_remove.append(name)
                else:
                    # No sub-states — likely a phantom, remove it
                    to_remove.append(name)
    
    for name in to_remove:
        if name in states:
            del states[name]
    
    return machine
