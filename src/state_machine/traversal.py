"""Traversal utilities for state machine analysis.

BFS reachability, path collection, target extraction.
Used by builder, cleanup, and validation modules.
"""

from state_machine.constants import DEPTH_LIMITS


def extract_target_string(target) -> str:
    """Extract a target string from a transition target, handling all formats.
    
    Handles:
    - String: "loading" → "loading"
    - Dict: {"target": "loading", "cond": "canRetry"} → "loading"
    - List: [{"target": "loading", "cond": "canRetry"}, ...] → "loading" (first)
    
    Args:
        target: Target in any format (str, dict, or list)
    
    Returns:
        Target string, or empty string if not found
    """
    if isinstance(target, str):
        return target
    elif isinstance(target, dict):
        return target.get("target", "")
    elif isinstance(target, list):
        for item in target:
            if isinstance(item, dict):
                t = item.get("target", "")
                if t:
                    return t
            elif isinstance(item, str):
                if item:
                    return item
        return ""
    return ""


def extract_target_names(target) -> list:
    """Extract target state names from a transition target.
    
    Handles both string targets and list of targets (for conditional transitions).
    
    Args:
        target: Target string, dict, or list of targets
    
    Returns:
        List of target state names
    """
    if isinstance(target, str):
        return [target]
    elif isinstance(target, dict):
        t = target.get("target", "")
        return [t] if t else []
    elif isinstance(target, list):
        names = []
        for item in target:
            if isinstance(item, dict):
                t = item.get("target", "")
                if t:
                    names.append(t)
            elif isinstance(item, str):
                names.append(item)
        return names
    return []


def collect_all_state_paths(states_dict: dict, prefix: str = "", depth: int = 0) -> list:
    """Collect all state paths in the machine.
    
    Args:
        states_dict: The states dict to traverse
        prefix: Current path prefix
        depth: Current recursion depth (safety limit)
    
    Returns:
        List of full state paths
    """
    limit = DEPTH_LIMITS["collect_paths"]
    if depth > limit:
        return []
    
    paths = []
    for name, config in states_dict.items():
        if not isinstance(config, dict):
            continue
        full_path = f"{prefix}.{name}" if prefix else name
        paths.append(full_path)
        if "states" in config:
            paths.extend(collect_all_state_paths(config["states"], full_path, depth + 1))
    return paths


def bfs_reachable(machine: dict) -> set:
    """BFS to find all reachable states from initial states.
    
    CRITICAL FIX: Limits path depth to prevent infinite loops when
    sub-states (like app_idle) are injected into multiple parent states.
    Without this limit, paths like "navigation.page_19.app_idle.app_idle.app_idle..."
    would grow infinitely.
    
    Args:
        machine: The state machine dict
    
    Returns:
        Set of reachable state paths
    """
    from state_machine.traversal import extract_target_string
    
    reachable = set()
    states = machine.get("states", {})
    max_depth = DEPTH_LIMITS["bfs_depth"]
    
    def _get_initials(states_dict: dict, prefix: str = "", depth: int = 0) -> list:
        limit = DEPTH_LIMITS["get_initials"]
        if depth > limit:
            return []
        initials = []
        for name, config in states_dict.items():
            if not isinstance(config, dict):
                continue
            full_path = f"{prefix}.{name}" if prefix else name
            if config.get("initial"):
                initials.append((name, full_path))
            if "states" in config:
                initials.extend(_get_initials(config["states"], full_path, depth + 1))
        return initials
    
    initials = _get_initials(states)
    
    # Track visited paths to prevent duplicates
    seen = set()
    queue = []
    for name, path in initials:
        if path not in seen:
            seen.add(path)
            queue.append((name, path))
    
    while queue:
        name, path = queue.pop(0)
        if path in reachable:
            continue
        reachable.add(path)
        
        # CRITICAL: Skip if path is too deep (prevents infinite loops)
        path_depth = path.count(".") + 1
        if path_depth > max_depth:
            continue
        
        # Find the state config
        parts = path.split(".")
        current = states
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                break
        
        # Add transition targets to queue
        if not isinstance(current, dict):
            continue
        transitions = current.get("on", {})
        for event, target in transitions.items():
            target_str = extract_target_string(target)
            if target_str:
                # Resolve relative targets
                if target_str.startswith("."):
                    sibling = target_str[1:]
                    parent = ".".join(parts[:-1])
                    resolved = f"{parent}.{sibling}" if parent else sibling
                elif target_str.startswith("#"):
                    resolved = target_str[1:]
                else:
                    resolved = target_str
                
                # Only add if not already seen
                if resolved not in seen and resolved not in reachable:
                    # Check if it exists
                    check_parts = resolved.split(".")
                    check_current = states
                    exists = True
                    for cp in check_parts:
                        if cp in check_current:
                            check_current = check_current[cp]
                        else:
                            exists = False
                            break
                    if exists:
                        seen.add(resolved)
                        queue.append((check_parts[-1], resolved))
        
        # Add sub-states to queue
        if "states" in current:
            sub_initial = current.get("initial")
            if sub_initial and sub_initial in current["states"]:
                sub_path = f"{path}.{sub_initial}"
                if sub_path not in seen and sub_path not in reachable:
                    seen.add(sub_path)
                    queue.append((sub_initial, sub_path))
    
    return reachable


def resolve_canonical_target(target: str, from_state: str, all_paths: list) -> str:
    """Resolve a target to its canonical (full) path.
    
    Args:
        target: Target string (may be relative or partial)
        from_state: Source state path
        all_paths: List of all state paths in the machine
    
    Returns:
        Canonical target path
    """
    if not target:
        return target
    
    # Already absolute with #
    if target.startswith("#"):
        return target[1:]
    
    # Relative reference: .name
    if target.startswith("."):
        sibling = target[1:]
        parts = from_state.rsplit(".", 1)
        if len(parts) == 2:
            parent = parts[0]
            return f"{parent}.{sibling}"
        return sibling
    
    # Check if it's already a full path
    if target in all_paths:
        return target
    
    # Try to find it as a sibling
    parts = from_state.rsplit(".", 1)
    if len(parts) == 2:
        parent = parts[0]
        candidate = f"{parent}.{target}"
        if candidate in all_paths:
            return candidate
    
    # Try to find it in the same branch
    branch = parts[0] if parts else ""
    candidate = f"{branch}.{target}"
    if candidate in all_paths:
        return candidate
    
    # Return as-is
    return target


def resolve_simple_target(target: str, current: str, states: dict, prefix: str = "") -> str:
    """Resolve a simple target reference.
    
    Args:
        target: Target string (may be relative with .)
        current: Current state name
        states: States dict
        prefix: Path prefix
    
    Returns:
        Resolved state name or None
    """
    if not target:
        return None
    
    # Relative reference
    if target.startswith("."):
        return target[1:]  # Strip the dot
    
    # Already in states
    if target in states:
        return target
    
    return None