"""Normalization and branch placement for state machines.

Fixes naming issues, moves orphan states to correct branches.
Implements the "Law of Orthography" — a universal corrector that works
with ANY domain (veterinary, finance, cooking, space).
"""

import re
from state_machine.constants import DEFAULT_STATE_NAMES, DEFAULT_BRANCH_NAMES, DEFAULT_ACTION_NAMES, BRANCH_NAMES


# Universal suffix patterns to strip from state names
_STATE_SUFFIXES = {"_state", "_screen", "_page", "_view", "_panel", "_section", "_tab", "_menu"}


def _normalize_state_name(name: str) -> str:
    """Normalize a state name using universal rules.
    
    THE LAW OF ORTHOGRAPHY:
    1. Convert to snake_case
    2. Remove duplicate consecutive parts (active_active → active)
    3. Strip common suffixes (_state, _screen, _page, etc.)
    4. Collapse multiple underscores (my__state → my_state)
    
    This works with ANY domain — veterinary, finance, cooking, space.
    
    Args:
        name: Raw state name from LLM
    
    Returns:
        Normalized state name
    """
    if not name:
        return name
    
    # Step 1: Convert to lowercase
    normalized = name.lower().strip()
    
    # Step 2: Replace hyphens and spaces with underscores
    normalized = re.sub(r'[-\s]+', '_', normalized)
    
    # Step 3: Remove non-alphanumeric chars (except underscore)
    normalized = re.sub(r'[^a-z0-9_]', '', normalized)
    
    # Step 4: Strip leading/trailing underscores (BEFORE collapsing)
    normalized = normalized.strip('_')
    
    # Step 5: Remove duplicate consecutive parts (single-level)
    # e.g., "active_active_workflows" → "active_workflows"
    parts = normalized.split('_')
    deduped = []
    for part in parts:
        if not deduped or deduped[-1] != part:
            deduped.append(part)
    normalized = '_'.join(deduped)
    
    # Step 6: Strip common suffixes
    for suffix in _STATE_SUFFIXES:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)]
            break
    
    # Step 7: Final cleanup — collapse any remaining double underscores
    normalized = re.sub(r'_+', '_', normalized).strip('_')
    
    return normalized if normalized else name


def _normalize_path(path: str) -> str:
    """Normalize a full state path (e.g., 'navigation.app_initial.app_initial').
    
    Removes recursive duplicates in the path chain using ANCESTRAL GUARD:
    - Consecutive duplicates: A-A → A
    - Alternating patterns: A-B-A-B → A-B
    - Semantic loops: A-B-C-A → A-B-C
    
    Only preserves valid branch names (navigation, workflows, active_workflows).
    If the first part is not a valid branch, deduplicates the entire path.
    
    Args:
        path: Full state path
    
    Returns:
        Normalized path
    """
    if not path:
        return path
    
    parts = path.split('.')
    
    if len(parts) <= 1:
        return path
    
    # Valid branch names — only these are preserved as the first element
    VALID_BRANCHES = {"navigation", "workflows", "active_workflows"}
    
    first_part = parts[0]
    
    if first_part in VALID_BRANCHES:
        # Preserve branch, deduplicate the rest
        branch = first_part
        state_parts = parts[1:]
    else:
        # First part is NOT a valid branch — deduplicate everything
        branch = ""
        state_parts = parts
    
    # ANCESTRAL GUARD: Remove any part that already appears earlier in the chain
    seen = set()
    deduped = []
    for part in state_parts:
        if part not in seen:
            seen.add(part)
            deduped.append(part)
        # Skip if already seen (recursive pattern)
    
    if branch:
        return f"{branch}.{'.'.join(deduped)}" if deduped else branch
    else:
        return '.'.join(deduped) if deduped else path


def _resolve_state_name(name: str, state_names: dict = None) -> str:
    """Resolve a state name using defaults + overrides.
    
    Args:
        name: Key to look up (e.g., "initial", "workflow_none")
        state_names: Optional override dict
    
    Returns:
        Resolved state name
    """
    overrides = state_names or {}
    return overrides.get(name, DEFAULT_STATE_NAMES.get(name, name))


def _resolve_branch_name(name: str, branch_names: dict = None) -> str:
    """Resolve a branch name using defaults + overrides.
    
    Args:
        name: Key to look up (e.g., "navigation", "workflows")
        branch_names: Optional override dict
    
    Returns:
        Resolved branch name
    """
    overrides = branch_names or {}
    return overrides.get(name, DEFAULT_BRANCH_NAMES.get(name, name))


def _resolve_action_name(name: str, action_names: dict = None) -> str:
    """Resolve an action name using defaults + overrides.
    
    Args:
        name: Key to look up (e.g., "hide_workflow", "show_loading")
        action_names: Optional override dict
    
    Returns:
        Resolved action name
    """
    overrides = action_names or {}
    return overrides.get(name, DEFAULT_ACTION_NAMES.get(name, name))


def _sanitize_double_prefix(machine: dict) -> dict:
    """Fix double-prefix branch names (e.g., 'active_active_workflows' → 'active_workflows').
    
    The LLM sometimes duplicates the 'active_' prefix, creating 'active_active_workflows'.
    This function renames the branch and updates all transition targets that reference it.
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with sanitized branch names
    """
    states = machine.get("states", {})
    
    # Fix double-prefix branch name
    if "active_active_workflows" in states:
        old_config = states.pop("active_active_workflows")
        states["active_workflows"] = old_config
        
        # Update all transition targets that reference the old name
        def _fix_targets(states_dict: dict, prefix: str = "") -> None:
            for name, config in states_dict.items():
                full_path = f"{prefix}.{name}" if prefix else name
                transitions = config.get("on", {})
                for event, target in list(transitions.items()):
                    if isinstance(target, str) and "active_active_workflows" in target:
                        transitions[event] = target.replace("active_active_workflows", "active_workflows")
                    elif isinstance(target, dict) and "target" in target:
                        if "active_active_workflows" in target["target"]:
                            target["target"] = target["target"].replace("active_active_workflows", "active_workflows")
                sub_states = config.get("states", {})
                if sub_states:
                    _fix_targets(sub_states, full_path)
        
        _fix_targets(states)
    
    return machine


def normalize_machine(machine: dict) -> dict:
    """Normalize machine: fix common issues.
    
    STRUCTURAL approach: uses the 'initial' value to determine the target state name,
    not hardcoded 'app_idle'. Works with ANY naming convention.
    
    Handles both parallel and flat architectures.
    
    Args:
        machine: The state machine dict
    
    Returns:
        Normalized machine dict
    """
    # Fix double-prefix branch names first
    machine = _sanitize_double_prefix(machine)
    
    if machine.get("type") == "parallel" and "navigation" in machine.get("states", {}):
        nav_branch = machine["states"]["navigation"]
        nav_initial = nav_branch.get("initial", "app_idle")
        
        # Fix idle → {initial} (use the actual initial state name)
        if "idle" in nav_branch.get("states", {}) and nav_initial:
            nav_branch["states"][nav_initial] = nav_branch["states"].pop("idle")
            for state_config in nav_branch["states"].values():
                for event, target in list(state_config.get("on", {}).items()):
                    if target == "idle":
                        state_config["on"][event] = nav_initial
        
        # Ensure initial state exists
        if nav_initial and nav_initial not in nav_branch.get("states", {}):
            nav_branch["states"][nav_initial] = {"entry": [], "exit": [], "on": {}}
    
    else:
        # Flat architecture
        seq_initial = machine.get("initial", "app_idle")
        
        if "idle" in machine["states"] and seq_initial:
            machine["states"][seq_initial] = machine["states"].pop("idle")
            for state_config in machine["states"].values():
                for event, target in list(state_config.get("on", {}).items()):
                    if target == "idle":
                        state_config["on"][event] = seq_initial
        
        if seq_initial and seq_initial not in machine["states"]:
            machine["states"][seq_initial] = {"entry": [], "exit": [], "on": {}}
    
    return machine


def _is_compound_state(state_config: dict) -> bool:
    """Check if a state is a compound state (has sub_states).
    
    A compound state is a state that contains other states.
    These are typically workflows or complex screens.
    
    Args:
        state_config: The state's configuration dict
    
    Returns:
        True if this state has sub_states
    """
    return bool(state_config.get("states", {}))


def _is_leaf_state(state_config: dict) -> bool:
    """Check if a state is a leaf state (no sub_states, just entry/exit/on).
    
    A leaf state is a simple state that doesn't contain other states.
    These are typically navigation pages/screens.
    
    Args:
        state_config: The state's configuration dict
    
    Returns:
        True if this state has no sub_states
    """
    return not state_config.get("states", {})


def apply_universal_normalization(machine: dict) -> dict:
    """Apply universal normalization to the entire machine.
    
    THE LAW OF ORTHOGRAPHY — Universal Corrector:
    1. Normalize all state names (snake_case, dedup, strip suffixes)
    2. Normalize all transition targets (resolve recursive paths)
    3. Update initial properties to point to normalized names
    
    This is DOMAIN-AGNOSTIC: works with veterinary, finance, cooking, space.
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with all names normalized
    """
    states = machine.get("states", {})
    limit = 15  # Max recursion depth
    
    def _normalize_states(states_dict: dict, prefix: str = "", depth: int = 0) -> None:
        if depth > limit:
            return
        
        # First pass: collect renames (can't modify dict while iterating)
        renames = {}
        for name, config in states_dict.items():
            normalized = _normalize_state_name(name)
            if normalized != name:
                renames[name] = normalized
        
        # Second pass: apply renames
        for old_name, new_name in renames.items():
            if new_name not in states_dict:
                states_dict[new_name] = states_dict.pop(old_name)
            else:
                # Target name already exists — merge configs
                old_config = states_dict.pop(old_name)
                # Merge entry/exit actions
                for key in ("entry", "exit"):
                    if key in old_config:
                        if key not in states_dict[new_name]:
                            states_dict[new_name][key] = []
                        states_dict[new_name][key].extend(old_config[key])
                # Merge transitions
                if "on" in old_config:
                    if "on" not in states_dict[new_name]:
                        states_dict[new_name]["on"] = {}
                    states_dict[new_name]["on"].update(old_config["on"])
        
        # Third pass: normalize transitions and recurse
        for name, config in states_dict.items():
            full_path = f"{prefix}.{name}" if prefix else name
            
            # Normalize transition targets
            transitions = config.get("on", {})
            for event, target in list(transitions.items()):
                if isinstance(target, str):
                    # Handle relative targets
                    if target.startswith("."):
                        normalized_target = _normalize_path(target[1:])
                        transitions[event] = f".{normalized_target}"
                    elif target.startswith("#"):
                        normalized_target = _normalize_path(target[1:])
                        transitions[event] = f"#{normalized_target}"
                    elif target.startswith("^"):
                        normalized_target = _normalize_path(target[1:])
                        transitions[event] = f"^{normalized_target}"
                    else:
                        normalized_target = _normalize_path(target)
                        transitions[event] = normalized_target
                elif isinstance(target, dict) and "target" in target:
                    old_target = target["target"]
                    if isinstance(old_target, str):
                        target["target"] = _normalize_path(old_target)
            
            # Normalize initial property
            initial = config.get("initial")
            if initial:
                normalized_initial = _normalize_state_name(initial)
                if normalized_initial != initial:
                    config["initial"] = normalized_initial
            
            # Recurse into sub-states
            sub_states = config.get("states", {})
            if sub_states:
                _normalize_states(sub_states, full_path, depth + 1)
    
    _normalize_states(states)
    return machine


def apply_branch_placement(machine: dict) -> dict:
    """Move orphan states to the correct branch based on their structure.
    
    RULE: States at root level that are NOT 'navigation' or 'workflows' branches
    should be moved into the appropriate branch:
    - Compound states (have sub_states) → workflows branch
    - Leaf states (no sub_states) → navigation branch
    - States whose name equals machine.id → REMOVE (LLM error)
    
    This is a STRUCTURAL rule, not a name-based rule.
    It works with ANY app because it looks at the JSON structure, not the names.
    
    Args:
        machine: The state machine dict
    
    Returns:
        Machine with orphan states moved to correct branches
    """
    states = machine.get("states", {})
    machine_id = machine.get("id", "")
    
    # Identify branches
    nav_branch = states.get("navigation", {})
    wf_branch = states.get("workflows") or states.get("active_workflows", {})
    
    # CRITICAL: Handle machine.id as state name BEFORE structural branch detection
    # This is an LLM error: the machine's own ID should not be a state name.
    # If it's a compound state (has sub_states), move it to workflows branch.
    # If it's a leaf state, move it to navigation branch.
    if machine_id and machine_id in states:
        orphan_config = states[machine_id]
        if _is_compound_state(orphan_config):
            if "states" not in wf_branch:
                wf_branch["states"] = {}
            wf_branch["states"][machine_id] = orphan_config
        else:
            if "states" not in nav_branch:
                nav_branch["states"] = {}
            nav_branch["states"][machine_id] = orphan_config
        del states[machine_id]
    
    # Also detect branches by structure (has 'initial' + 'states' = parallel/compound branch)
    for name, config in list(states.items()):
        if name in BRANCH_NAMES:
            continue
        if config.get("initial") and config.get("states"):
            BRANCH_NAMES.add(name)
    
    # Find orphan states (at root level, not branches)
    orphans = {}
    for name, config in list(states.items()):
        if name in BRANCH_NAMES:
            continue
        orphans[name] = config
    
    # Move orphans to appropriate branch
    for name, config in orphans.items():
        if _is_compound_state(config):
            # Compound state → workflows branch
            if "states" not in wf_branch:
                wf_branch["states"] = {}
            wf_branch["states"][name] = config
        else:
            # Leaf state → navigation branch
            if "states" not in nav_branch:
                nav_branch["states"] = {}
            nav_branch["states"][name] = config
        
        # Remove from root
        if name in states:
            del states[name]
    
    return machine