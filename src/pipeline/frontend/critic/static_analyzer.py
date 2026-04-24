"""
Static critic analysis - fallback when LLM is not available.
"""


def static_critic_analysis(fuzz_report: dict, machine: dict) -> dict:
    """Static critical analysis (without LLM)."""
    
    critical_issues = []
    ux_decisions = []
    edge_cases = []
    recommendations = []
    
    summary = fuzz_report.get("summary", {})
    bugs = fuzz_report.get("bugs", [])
    
    # Analyze dead-end states
    dead_end_bugs = [b for b in bugs if b.get("type") == "dead_end_state"]
    for bug in dead_end_bugs:
        critical_issues.append({
            "id": f"CRIT-{len(critical_issues)+1:03d}",
            "category": "logic",
            "description": bug["description"],
            "affected_states": [bug.get("state", "unknown")],
            "severity": "critical",
            "suggestion": f"Add a transition from '{bug.get('state', 'unknown')}' to handle the dead-end (e.g., retry, go back, or show error)"
        })
    
    # Analyze unreachable states
    unreachable = fuzz_report.get("unreachable_states", [])
    for state in unreachable:
        critical_issues.append({
            "id": f"CRIT-{len(critical_issues)+1:03d}",
            "category": "logic",
            "description": f"State '{state}' is unreachable from initial state",
            "affected_states": [state],
            "severity": "high",
            "suggestion": f"Either add a transition path to '{state}' or remove it if unused"
        })
    
    # Analyze unknown targets
    unknown_bugs = [b for b in bugs if b.get("type") == "unknown_target"]
    for bug in unknown_bugs:
        critical_issues.append({
            "id": f"CRIT-{len(critical_issues)+1:03d}",
            "category": "logic",
            "description": bug["description"],
            "affected_states": [bug.get("from_state", "unknown")],
            "severity": "critical",
            "suggestion": f"Fix the transition target to point to a valid state"
        })
    
    # UX decisions based on loading states
    states = machine.get("states", {})
    loading_states = [s for s in states.keys() if "loading" in s.lower()]
    if loading_states:
        ux_decisions.append({
            "id": f"UX-{len(ux_decisions)+1:03d}",
            "question": "What should the user see during loading states?",
            "context": f"There are {len(loading_states)} loading states ({', '.join(loading_states[:3])}...)",
            "options": ["Skeleton screens", "Loading spinner with progress", "Static placeholder", "Shimmer effect"]
        })
    
    # Edge cases based on error states
    error_states = [s for s in states.keys() if "error" in s.lower() or "timeout" in s.lower()]
    if error_states:
        edge_cases.append({
            "id": f"EC-NEW-{len(edge_cases)+1:03d}",
            "scenario": "User is in error state and tries to retry",
            "expected_behavior": "Should show retry button with exponential backoff",
            "priority": "high"
        })
        edge_cases.append({
            "id": f"EC-NEW-{len(edge_cases)+1:03d}",
            "scenario": "Multiple consecutive errors occur",
            "expected_behavior": "After 3 failures, show 'contact support' option",
            "priority": "high"
        })
    
    # Recommendations
    if summary.get("total_errors", 0) > 0:
        recommendations.append(f"Fix {summary['total_errors']} structural errors before proceeding")
    if summary.get("unreachable_states", 0) > 0:
        recommendations.append(f"Review {summary['unreachable_states']} unreachable states - they may indicate missing flows")
    if summary.get("structural_loops", 0) > 0:
        recommendations.append(f"Verify {summary['structural_loops']} structural loops are intentional (not infinite loops)")
    
    if not recommendations:
        recommendations.append("Specification looks solid. Consider adding more edge cases for production readiness.")
    
    return {
        "critical_issues": critical_issues,
        "ux_decisions_needed": ux_decisions,
        "edge_cases_to_add": edge_cases,
        "recommendations": recommendations
    }