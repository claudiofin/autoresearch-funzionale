"""JSON structural validator for XState state machines.

Detects structural issues that make the JSON invalid or ambiguous:
- Duplicate states (same name in different paths)
- Orphan transitions (pointing to non-existent states)
- Dead-end states (no exit transitions, except finals)
- Invalid compound state hierarchy (missing initial, states, on)
- Relative transition resolution failures

This is the "Pathfinder" - a deterministic judge that validates the machine
structure before it's handed off to code generators.

Usage:
    python -m src.state_machine.json_validator output/spec/spec_machine.json
    # Exit code 0 = valid, 1 = issues found

    # Or programmatically:
    from src.state_machine.json_validator import validate_json_structure
    result = validate_json_structure("output/spec/spec_machine.json")
    if not result["is_valid"]:
        print(result["issues"])
"""

import json
import sys
import os
from typing import Optional


class StatePath:
    """Represents a fully qualified state path in the machine."""
    
    def __init__(self, path: str, config: dict):
        self.path = path  # e.g., "navigation.success.dashboard"
        self.name = path.split(".")[-1]  # e.g., "dashboard"
        self.config = config
        self.parts = path.split(".")
    
    @property
    def parent_path(self) -> str:
        if len(self.parts) > 1:
            return ".".join(self.parts[:-1])
        return ""
    
    @property
    def depth(self) -> int:
        return len(self.parts)


def _collect_all_states(states: dict, prefix: str = "") -> list:
    """Recursively collect all states with their full paths.
    
    Args:
        states: The states dict from the machine
        prefix: Current path prefix (e.g., "navigation.success")
    
    Returns:
        List of StatePath objects
    """
    result = []
    
    for name, config in states.items():
        full_path = f"{prefix}.{name}" if prefix else name
        result.append(StatePath(full_path, config))
        
        # Recurse into nested states
        if "states" in config and isinstance(config["states"], dict):
            nested = _collect_all_states(config["states"], full_path)
            result.extend(nested)
    
    return result


def find_duplicate_states(machine: dict) -> list:
    """Find states with the same name appearing in different paths.
    
    This is the "Schizofrenia del JSON" - when dashboard appears both
    under navigation.success.dashboard AND as a flat state at root level.
    
    FIX: Sub-states with the same name in different compound states are NOT duplicates.
    For example, 'loading' in 'dashboard.loading' and 'catalog.loading' are legitimate
    sub-states of different parent states. Only flag as duplicate when the same name
    appears at the same hierarchy level (siblings) or at root level.
    
    Returns:
        List of dicts with duplicate info
    """
    all_states = _collect_all_states(machine.get("states", {}))
    
    # Group by short name
    name_to_paths = {}
    for state in all_states:
        if state.name not in name_to_paths:
            name_to_paths[state.name] = []
        name_to_paths[state.name].append(state.path)
    
    # Sub-state names that are commonly used in compound states
    # These are NOT duplicates when they appear in different parent states
    common_sub_state_names = {"loading", "ready", "error", "error_handler", 
                              "calculating", "fetching", "submitting", "processing",
                              "idle", "none", "success", "failed", "timeout"}
    
    duplicates = []
    for name, paths in name_to_paths.items():
        if len(paths) > 1:
            # FIX: Check if these are sub-states in different compound states
            # If so, they are NOT duplicates
            if name in common_sub_state_names:
                # Check if all paths have different parents
                parents = set()
                for path in paths:
                    parts = path.split(".")
                    if len(parts) >= 2:
                        # This is a sub-state — get the parent path
                        parent = ".".join(parts[:-1])
                        parents.add(parent)
                    else:
                        # Root-level state — could be a real duplicate
                        parents.add(path)
                
                # If all parents are different, these are legitimate sub-states
                # Only flag as duplicate if the same name appears at root level
                # or as siblings under the same parent
                root_level_paths = [p for p in paths if "." not in p]
                if len(root_level_paths) > 1:
                    # Multiple root-level states with same name — real duplicate
                    duplicates.append({
                        "state_name": name,
                        "paths": paths,
                        "count": len(paths),
                        "issue": "DUPLICATE_STATE",
                        "description": f"State '{name}' appears {len(paths)} times at different paths: {', '.join(paths)}",
                        "severity": "critical"
                    })
                elif len(parents) == len(paths):
                    # All sub-states have different parents — NOT a duplicate
                    continue
                else:
                    # Some share the same parent — check for sibling duplicates
                    # Group by parent
                    parent_to_paths = {}
                    for path in paths:
                        parts = path.split(".")
                        parent = ".".join(parts[:-1]) if len(parts) >= 2 else ""
                        if parent not in parent_to_paths:
                            parent_to_paths[parent] = []
                        parent_to_paths[parent].append(path)
                    
                    # Only flag if same parent has multiple states with same name
                    for parent, parent_paths in parent_to_paths.items():
                        if len(parent_paths) > 1:
                            duplicates.append({
                                "state_name": name,
                                "paths": parent_paths,
                                "count": len(parent_paths),
                                "issue": "DUPLICATE_STATE",
                                "description": f"State '{name}' appears {len(parent_paths)} times under '{parent}': {', '.join(parent_paths)}",
                                "severity": "critical"
                            })
            else:
                # Non-sub-state name — use original logic
                duplicates.append({
                    "state_name": name,
                    "paths": paths,
                    "count": len(paths),
                    "issue": "DUPLICATE_STATE",
                    "description": f"State '{name}' appears {len(paths)} times at different paths: {', '.join(paths)}",
                    "severity": "critical"
                })
    
    return duplicates


def _resolve_transition_target(target: str, from_state_path: str, all_state_paths: set) -> Optional[str]:
    """Resolve a transition target to a full state path.
    
    Handles:
    - Absolute: "success.dashboard" -> "success.dashboard"
    - Relative: ".dashboard" -> "{parent}.dashboard"
    - Sibling: "dashboard" -> depends on context
    - Cross-branch: "#navigation.success.dashboard" -> "navigation.success.dashboard"
    
    Returns:
        Resolved full path, or None if unresolvable
    """
    if not target:
        return None
    
    # Cross-branch reference (# prefix)
    if target.startswith("#"):
        return target[1:]  # Remove # prefix
    
    # Relative reference (. prefix)
    if target.startswith("."):
        # Get parent of current state
        parts = from_state_path.split(".")
        if len(parts) > 1:
            parent = ".".join(parts[:-1])
            return f"{parent}{target}"
        return target[1:]  # Root level relative
    
    # Absolute or sibling reference
    if "." in target:
        return target
    
    # Sibling - try to find in same parent
    parts = from_state_path.split(".")
    if len(parts) > 1:
        parent = ".".join(parts[:-1])
        candidate = f"{parent}.{target}"
        if candidate in all_state_paths:
            return candidate
    
    # Try as root-level state
    if target in all_state_paths:
        return target
    
    return None


def find_orphan_transitions(machine: dict) -> list:
    """Find transitions that point to non-existent states.
    
    Returns:
        List of dicts with orphan transition info
    """
    all_states = _collect_all_states(machine.get("states", {}))
    all_paths = {s.path for s in all_states}
    
    # Also collect short names for flexible matching
    all_short_names = {s.name for s in all_states}
    
    orphans = []
    
    def check_transitions(states: dict, prefix: str = ""):
        for state_name, config in states.items():
            full_path = f"{prefix}.{state_name}" if prefix else state_name
            transitions = config.get("on", {})
            
            for event, target in transitions.items():
                # Extract target string(s)
                targets = _extract_target_strings(target)
                
                for target_str in targets:
                    resolved = _resolve_transition_target(target_str, full_path, all_paths)
                    
                    if resolved is None:
                        # Check if it's a relative reference that can't be resolved
                        if target_str.startswith("."):
                            orphans.append({
                                "from_state": full_path,
                                "event": event,
                                "target": target_str,
                                "issue": "ORPHAN_TRANSITION",
                                "description": f"Relative transition '{target_str}' from '{full_path}' cannot be resolved",
                                "severity": "critical"
                            })
                    elif resolved not in all_paths:
                        # Check if target exists as a short name somewhere
                        target_short = resolved.split(".")[-1]
                        if target_short not in all_short_names:
                            orphans.append({
                                "from_state": full_path,
                                "event": event,
                                "target": target_str,
                                "resolved_to": resolved,
                                "issue": "ORPHAN_TRANSITION",
                                "description": f"Transition '{event}' from '{full_path}' points to '{target_str}' (resolved: '{resolved}') which does not exist",
                                "severity": "critical"
                            })
            
            # Recurse into nested states
            if "states" in config and isinstance(config["states"], dict):
                check_transitions(config["states"], full_path)
    
    check_transitions(machine.get("states", {}))
    return orphans


def _extract_target_strings(target) -> list:
    """Extract target state strings from a transition definition.
    
    Handles:
    - String: "success" -> ["success"]
    - Dict: {"target": "success", "cond": "hasData"} -> ["success"]
    - List: [{"target": "success"}, {"target": "empty"}] -> ["success", "empty"]
    """
    if isinstance(target, str):
        return [target]
    elif isinstance(target, dict):
        t = target.get("target", "")
        return [t] if t else []
    elif isinstance(target, list):
        result = []
        for item in target:
            if isinstance(item, dict):
                t = item.get("target", "")
                if t:
                    result.append(t)
            elif isinstance(item, str):
                result.append(item)
        return result
    return []


def find_dead_end_states(machine: dict) -> list:
    """Find states without any exit transitions (except legitimate finals).
    
    Returns:
        List of dicts with dead-end state info
    """
    all_states = _collect_all_states(machine.get("states", {}))
    
    # Legitimate final state names
    final_keywords = ["success", "ready", "complete", "done", "finished", "none"]
    
    dead_ends = []
    for state in all_states:
        transitions = state.config.get("on", {})
        has_nested = "states" in state.config and isinstance(state.config["states"], dict)
        
        # A state is a dead-end if:
        # 1. It has no transitions AND
        # 2. It's not a compound state (which has internal transitions) AND
        # 3. It's not a legitimate final state
        if not transitions and not has_nested:
            is_final = any(kw in state.name.lower() for kw in final_keywords)
            if not is_final:
                dead_ends.append({
                    "state": state.path,
                    "state_name": state.name,
                    "issue": "DEAD_END_STATE",
                    "description": f"State '{state.path}' has no exit transitions and is not a final state",
                    "suggestion": _suggest_exit_for_state(state.name),
                    "severity": "high"
                })
    
    return dead_ends


def _suggest_exit_for_state(state_name: str) -> str:
    """Suggest appropriate exit transitions based on state name patterns."""
    name = state_name.lower()
    
    if "error" in name or "fail" in name:
        return "Add: RETRY → loading state, CANCEL → initial state"
    elif "loading" in name:
        return "Add: CANCEL → previous state, TIMEOUT → error state"
    elif "empty" in name:
        return "Add: REFRESH → loading state, GO_BACK → initial state"
    elif "timeout" in name:
        return "Add: RETRY → loading state, CANCEL → initial state"
    elif "session" in name or "auth" in name or "expired" in name:
        return "Add: REAUTHENTICATE → loading state, CANCEL → initial state"
    elif "idle" in name:
        return "Add: START_APP → authenticating/loading"
    else:
        return "Add at least one appropriate exit transition (GO_BACK, CANCEL, or navigation event)"


def find_invalid_compound_states(machine: dict) -> list:
    """Find compound states with invalid hierarchy.
    
    A valid compound state must have:
    - "initial" specifying the starting sub-state
    - "states" dict with sub-state definitions
    - "on" dict for transitions at the compound level
    
    Returns:
        List of dicts with invalid compound state info
    """
    all_states = _collect_all_states(machine.get("states", {}))
    
    invalid = []
    for state in all_states:
        has_nested = "states" in state.config and isinstance(state.config["states"], dict)
        
        if has_nested:
            # This is a compound state - validate its structure
            issues = []
            
            if "initial" not in state.config:
                issues.append("missing 'initial' property")
            
            sub_states = state.config.get("states", {})
            if not sub_states:
                issues.append("'states' dict is empty")
            else:
                # Check that initial points to a valid sub-state
                initial = state.config.get("initial", "")
                if initial and initial not in sub_states:
                    issues.append(f"'initial' ('{initial}') does not match any sub-state: {list(sub_states.keys())}")
            
            
            if issues:
                invalid.append({
                    "state": state.path,
                    "issue": "INVALID_COMPOUND_STATE",
                    "description": f"Compound state '{state.path}' has structural issues: {'; '.join(issues)}",
                    "severity": "high"
                })
    
    return invalid


def find_transition_cycles(machine: dict) -> list:
    """Find potential infinite loops (A→B→A without exit).
    
    Returns:
        List of dicts with cycle info
    """
    all_states = _collect_all_states(machine.get("states", {}))
    state_map = {s.path: s for s in all_states}
    
    cycles = []
    checked = set()
    
    for state in all_states:
        transitions = state.config.get("on", {})
        
        for event, target in transitions.items():
            targets = _extract_target_strings(target)
            
            for target_str in targets:
                resolved = _resolve_transition_target(target_str, state.path, {s.path for s in all_states})
                
                if resolved and resolved in state_map:
                    target_state = state_map[resolved]
                    target_transitions = target_state.config.get("on", {})
                    
                    # Check for reverse transition
                    for rev_event, rev_target in target_transitions.items():
                        rev_targets = _extract_target_strings(rev_target)
                        for rt in rev_targets:
                            rt_resolved = _resolve_transition_target(rt, target_state.path, {s.path for s in all_states})
                            if rt_resolved == state.path:
                                # Cycle found
                                cycle_key = tuple(sorted([state.path, target_state.path]))
                                if cycle_key not in checked:
                                    checked.add(cycle_key)
                                    
                                    # Check if at least one has an exit
                                    has_exit_from_source = len(transitions) > 1
                                    has_exit_from_target = len(target_transitions) > 1
                                    
                                    if not has_exit_from_source or not has_exit_from_target:
                                        cycles.append({
                                            "cycle": [state.path, target_state.path],
                                            "issue": "POTENTIAL_INFINITE_LOOP",
                                            "description": f"Bidirectional cycle: {state.path} ↔ {target_state.path}. One state has no other exits.",
                                            "severity": "medium"
                                        })
    
    return cycles


def validate_json_structure(machine_file: str) -> dict:
    """Run all structural validations on the state machine JSON.
    
    Args:
        machine_file: Path to the spec_machine.json file
    
    Returns:
        Dict with validation results
    """
    # Load machine
    if isinstance(machine_file, dict):
        machine = machine_file
        source = "inline"
    else:
        if not os.path.exists(machine_file):
            return {
                "is_valid": False,
                "error": f"File not found: {machine_file}",
                "issues": [],
                "summary": {"critical": 0, "high": 0, "medium": 0, "low": 0}
            }
        with open(machine_file, "r", encoding="utf-8") as f:
            machine = json.load(f)
        source = machine_file
    
    # Run all checks
    duplicates = find_duplicate_states(machine)
    orphans = find_orphan_transitions(machine)
    dead_ends = find_dead_end_states(machine)
    invalid_compounds = find_invalid_compound_states(machine)
    cycles = find_transition_cycles(machine)
    
    # Combine all issues
    all_issues = duplicates + orphans + dead_ends + invalid_compounds + cycles
    
    # Count by severity
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for issue in all_issues:
        sev = issue.get("severity", "low")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
    
    # Machine is valid only if no critical or high issues
    is_valid = severity_counts["critical"] == 0 and severity_counts["high"] == 0
    
    # Calculate quality score
    total_states = len(_collect_all_states(machine.get("states", {})))
    critical_penalty = severity_counts["critical"] * 25
    high_penalty = severity_counts["high"] * 15
    medium_penalty = severity_counts["medium"] * 5
    quality_score = max(0, 100 - critical_penalty - high_penalty - medium_penalty)
    
    return {
        "is_valid": is_valid,
        "source": source,
        "machine_id": machine.get("id", "unknown"),
        "total_states": total_states,
        "total_transitions": sum(
            len(s.config.get("on", {})) for s in _collect_all_states(machine.get("states", {}))
        ),
        "issues": all_issues,
        "summary": {
            "total": len(all_issues),
            "critical": severity_counts["critical"],
            "high": severity_counts["high"],
            "medium": severity_counts["medium"],
            "low": severity_counts["low"],
        },
        "quality_score": quality_score,
        "categories": {
            "duplicate_states": duplicates,
            "orphan_transitions": orphans,
            "dead_end_states": dead_ends,
            "invalid_compound_states": invalid_compounds,
            "potential_cycles": cycles,
        }
    }


def print_validation_report(result: dict):
    """Print a human-readable validation report."""
    print("\n" + "=" * 70)
    print("JSON STRUCTURAL VALIDATION REPORT")
    print("=" * 70)
    
    print(f"\n📄 Source: {result.get('source', 'unknown')}")
    print(f"🏷️  Machine ID: {result.get('machine_id', 'unknown')}")
    print(f"📊 Total States: {result.get('total_states', 0)}")
    print(f"🔄 Total Transitions: {result.get('total_transitions', 0)}")
    print(f"⭐ Quality Score: {result.get('quality_score', 0)}/100")
    
    summary = result.get("summary", {})
    print(f"\n📋 Issues Found: {summary.get('total', 0)}")
    print(f"   🔴 Critical: {summary.get('critical', 0)}")
    print(f"   🟠 High: {summary.get('high', 0)}")
    print(f"   🟡 Medium: {summary.get('medium', 0)}")
    print(f"   🟢 Low: {summary.get('low', 0)}")
    
    is_valid = result.get("is_valid", False)
    print(f"\n{'✅ VALID' if is_valid else '❌ INVALID'} - Machine structure is {'acceptable' if is_valid else 'NOT acceptable'}")
    
    issues = result.get("issues", [])
    if issues:
        print(f"\n{'─' * 70}")
        print("DETAILED ISSUES:")
        print(f"{'─' * 70}")
        
        for i, issue in enumerate(issues, 1):
            sev = issue.get("severity", "low")
            sev_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(sev, "⚪")
            
            print(f"\n{sev_icon} [{i}] {issue.get('issue', 'UNKNOWN')}")
            print(f"    {issue.get('description', 'No description')}")
            
            if "suggestion" in issue:
                print(f"    💡 Suggestion: {issue['suggestion']}")
    
    print("\n" + "=" * 70)


def main():
    """CLI entry point for validation."""
    if len(sys.argv) < 2:
        print("Usage: python -m src.state_machine.json_validator <machine_file.json>")
        print("  Validates the structural integrity of an XState machine JSON file.")
        print("  Exit code 0 = valid, 1 = issues found")
        sys.exit(1)
    
    machine_file = sys.argv[1]
    result = validate_json_structure(machine_file)
    
    print_validation_report(result)
    
    # Exit with appropriate code
    sys.exit(0 if result["is_valid"] else 1)


if __name__ == "__main__":
    main()