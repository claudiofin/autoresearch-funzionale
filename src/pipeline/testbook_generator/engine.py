"""
Testbook Engine - Deterministic path discovery and scenario generation for XState machines.

This engine analyzes the state machine JSON and generates:
1. State Coverage Audit - Detects unreachable states (orphans)
2. Global Invariants - Verifies logical properties (e.g., CANCEL always leads to none)
3. Test Scenarios - Happy paths, interruptions, and error paths for each workflow

The engine is 100% generic - it works with ANY XState machine JSON, regardless of domain.
No LLM is needed for the core functionality.
"""

import json
from collections import deque
from datetime import datetime
from typing import Any


class TestbookEngine:
    """Core engine for testbook generation from XState machine definitions."""

    # Events that represent "exit" or "error" paths (not happy path transitions)
    EXIT_EVENTS = {"CANCEL", "GO_BACK", "CANCELLED", "ON_ERROR", "RETRY_FETCH", "DISMISSED"}
    # Events that represent successful progression
    SUCCESS_EVENTS = {"COMPLETED", "CONFIRM_JOIN", "JOIN_GROUP", "VIEW_BENCHMARK", "SET_PRICE_ALERT",
                      "ACKNOWLEDGE_ALERT", "APPROFITTA", "TRACK_PROGRESS", "START_APP",
                      "ON_SUCCESS", "NAVIGATE_CATALOG", "NAVIGATE_OFFERS", "NAVIGATE_ALERTS",
                      "NAVIGATE_BENCHMARK", "NAVIGATE_DASHBOARD", "SEARCH", "LOAD_MORE",
                      "SUBMIT_DATA", "CLAIM_OFFER", "REFRESH_CLUSTER", "REFRESH_DATA",
                      "APPLY_FILTER", "PULL_TO_REFRESH", "MARK_AS_READ", "REAUTHENTICATE"}

    def __init__(self, machine_path: str):
        """Initialize the engine with a path to the XState machine JSON file.

        Args:
            machine_path: Path to the spec_machine.json file
        """
        with open(machine_path, "r", encoding="utf-8") as f:
            self.machine = json.load(f)

        self.machine_id = self.machine.get("id", "unknown")
        self.context = self.machine.get("context", {})

        # Extract workflows from parallel architecture
        self.workflows = self._extract_workflows()

    def _extract_workflows(self) -> dict:
        """Extract workflow definitions from the machine.

        Handles both parallel architecture (navigation + active_workflows)
        and flat architecture.

        Returns:
            Dict of workflow_id -> workflow_data
        """
        states = self.machine.get("states", {})

        # Parallel architecture: workflows are in active_workflows branch
        if self.machine.get("type") == "parallel" and "active_workflows" in states:
            all_workflows = states["active_workflows"].get("states", {})
            # Filter out "none" - it's the initial "no workflow active" state, not a real workflow
            return {k: v for k, v in all_workflows.items() if k != "none"}

        # Flat architecture: workflows are top-level states with nested states
        workflows = {}
        for state_name, state_data in states.items():
            if "states" in state_data and "initial" in state_data:
                # This is a compound state (potential workflow)
                workflows[state_name] = state_data

        return workflows

    # ---------------------------------------------------------------------------
    # PHASE 1: State Coverage Audit
    # ---------------------------------------------------------------------------

    def audit_state_coverage(self) -> dict:
        """Audit which states are reachable in each workflow.

        Returns:
            Dict with coverage data per workflow:
            {
                "workflow_id": {
                    "total_states": int,
                    "reachable_states": int,
                    "unreachable_states": list,
                    "status": "PASS" | "WARNING"
                }
            }
        """
        coverage = {}

        for workflow_id, workflow_data in self.workflows.items():
            states = workflow_data.get("states", {})
            initial = workflow_data.get("initial")

            if not initial or not states:
                coverage[workflow_id] = {
                    "total_states": 0,
                    "reachable_states": 0,
                    "unreachable_states": [],
                    "status": "WARNING",
                    "note": "No initial state or no sub-states defined"
                }
                continue

            reachable = self._bfs_reachable(states, initial)
            all_states = set(states.keys())
            unreachable = all_states - reachable

            coverage[workflow_id] = {
                "total_states": len(all_states),
                "reachable_states": len(reachable),
                "unreachable_states": sorted(list(unreachable)),
                "status": "PASS" if not unreachable else "WARNING"
            }

        return coverage

    def _bfs_reachable(self, states: dict, initial: str) -> set:
        """BFS to find all reachable states from initial state.

        Args:
            states: Dict of state_name -> state_config
            initial: Initial state name

        Returns:
            Set of reachable state names
        """
        reachable = set()
        queue = deque([initial])
        reachable.add(initial)

        while queue:
            current = queue.popleft()
            state_config = states.get(current, {})

            transitions = state_config.get("on", {})
            for event, target in transitions.items():
                targets = self._extract_targets(target)
                for t in targets:
                    t_clean = self._clean_state_name(t)
                    if t_clean and t_clean in states and t_clean not in reachable:
                        reachable.add(t_clean)
                        queue.append(t_clean)

        return reachable

    # ---------------------------------------------------------------------------
    # PHASE 2: Global Invariants Verification
    # ---------------------------------------------------------------------------

    def verify_invariants(self) -> list:
        """Verify global invariants across all workflows.

        Invariants checked:
        1. CANCEL always leads to 'none' (exit strategy)
        2. Every workflow has at least one terminal/completion state
        3. No transitions point to non-existent states
        4. Every state is reachable from initial (covered by audit)

        Returns:
            List of invariant results:
            [
                {
                    "invariant": str,
                    "status": "PASS" | "FAIL",
                    "details": str,
                    "violations": list
                }
            ]
        """
        invariants = []

        # Invariant 1: CANCEL → none
        invariants.append(self._check_cancel_invariant())

        # Invariant 2: Every workflow has a completion path
        invariants.append(self._check_completion_invariant())

        # Invariant 3: No dangling transitions
        invariants.append(self._check_dangling_transitions())

        return invariants

    def _check_cancel_invariant(self) -> dict:
        """Check that CANCEL event always leads to 'none' state."""
        violations = []
        total_checked = 0

        for workflow_id, workflow_data in self.workflows.items():
            states = workflow_data.get("states", {})
            for state_name, state_config in states.items():
                transitions = state_config.get("on", {})
                if "CANCEL" in transitions:
                    total_checked += 1
                    targets = self._extract_targets(transitions["CANCEL"])
                    for t in targets:
                        t_clean = self._clean_state_name(t)
                        if t_clean != "none":
                            violations.append({
                                "workflow": workflow_id,
                                "state": state_name,
                                "target": t_clean,
                                "expected": "none"
                            })

        return {
            "invariant": "CANCEL → none (exit strategy)",
            "status": "PASS" if not violations else "FAIL",
            "details": f"{total_checked}/{total_checked} states verified" if not violations
                       else f"{len(violations)} violation(s) found",
            "violations": violations
        }

    def _check_completion_invariant(self) -> dict:
        """Check that every workflow has at least one path to completion."""
        violations = []

        for workflow_id, workflow_data in self.workflows.items():
            states = workflow_data.get("states", {})
            initial = workflow_data.get("initial")

            if not initial or not states:
                violations.append({
                    "workflow": workflow_id,
                    "reason": "No initial state or no sub-states"
                })
                continue

            # Check if any state has a transition to "none" via COMPLETED or similar
            has_completion = False
            for state_name, state_config in states.items():
                transitions = state_config.get("on", {})
                for event in transitions:
                    if event in ("COMPLETED", "DISMISSED"):
                        has_completion = True
                        break
                if has_completion:
                    break

            if not has_completion:
                violations.append({
                    "workflow": workflow_id,
                    "reason": "No COMPLETED/DISMISSED transition found"
                })

        return {
            "invariant": "Every workflow has a completion path",
            "status": "PASS" if not violations else "FAIL",
            "details": f"{len(self.workflows)}/{len(self.workflows)} workflows verified" if not violations
                       else f"{len(violations)} workflow(s) without completion path",
            "violations": violations
        }

    def _check_dangling_transitions(self) -> dict:
        """Check that no transitions point to non-existent states."""
        violations = []

        for workflow_id, workflow_data in self.workflows.items():
            states = workflow_data.get("states", {})
            for state_name, state_config in states.items():
                transitions = state_config.get("on", {})
                for event, target in transitions.items():
                    targets = self._extract_targets(target)
                    for t in targets:
                        t_clean = self._clean_state_name(t)
                        # 'none' is a valid target (exit workflow)
                        if t_clean and t_clean != "none" and t_clean not in states:
                            violations.append({
                                "workflow": workflow_id,
                                "from_state": state_name,
                                "event": event,
                                "target": t_clean
                            })

        return {
            "invariant": "No dangling transitions",
            "status": "PASS" if not violations else "FAIL",
            "details": "All transitions point to valid states" if not violations
                       else f"{len(violations)} dangling transition(s) found",
            "violations": violations
        }

    # ---------------------------------------------------------------------------
    # PHASE 3: Path Discovery
    # ---------------------------------------------------------------------------

    def discover_all_paths(self) -> dict:
        """Discover all test paths for all workflows.

        Returns:
            Dict of workflow_id -> paths:
            {
                "workflow_id": {
                    "happy_path": list,           # State sequence for happy path
                    "interruptions": list,        # CANCEL from each state
                    "back_paths": list,           # GO_BACK from each state
                    "error_paths": list,          # ON_ERROR transitions
                    "completion_paths": list      # COMPLETED transitions
                }
            }
        """
        all_paths = {}

        for workflow_id in self.workflows:
            all_paths[workflow_id] = {
                "happy_path": self._find_happy_path(workflow_id),
                "interruptions": self._find_interruptions(workflow_id),
                "back_paths": self._find_back_paths(workflow_id),
                "error_paths": self._find_error_paths(workflow_id),
                "completion_paths": self._find_completion_paths(workflow_id)
            }

        return all_paths

    def _find_happy_path(self, workflow_id: str) -> list:
        """Find the happy path (optimal completion) for a workflow.

        Uses BFS to find the shortest path from initial to a terminal state.

        Args:
            workflow_id: The workflow to analyze

        Returns:
            List of state names representing the happy path
        """
        workflow_data = self.workflows.get(workflow_id, {})
        states = workflow_data.get("states", {})
        initial = workflow_data.get("initial")

        if not initial or not states:
            return []

        # BFS to find shortest path to any terminal state
        queue = deque([(initial, [initial])])
        visited = {initial}

        while queue:
            current, path = queue.popleft()
            state_config = states.get(current, {})
            transitions = state_config.get("on", {})

            # Check if current state has a completion transition
            for event in transitions:
                if event in ("COMPLETED", "DISMISSED"):
                    return path + ["COMPLETED"]

            # Follow non-exit transitions (happy path)
            for event, target in transitions.items():
                if event not in self.EXIT_EVENTS:
                    targets = self._extract_targets(target)
                    for t in targets:
                        t_clean = self._clean_state_name(t)
                        if t_clean and t_clean in states and t_clean not in visited:
                            visited.add(t_clean)
                            new_path = path + [t_clean]
                            queue.append((t_clean, new_path))

        # If no completion found, return the longest path found
        return [initial] if initial in states else []

    def _find_interruptions(self, workflow_id: str) -> list:
        """Find all CANCEL interruptions for a workflow.

        Args:
            workflow_id: The workflow to analyze

        Returns:
            List of interruption dicts:
            [
                {"from": state, "event": "CANCEL", "to": "none"},
                ...
            ]
        """
        workflow_data = self.workflows.get(workflow_id, {})
        states = workflow_data.get("states", {})
        interruptions = []

        for state_name, state_config in states.items():
            transitions = state_config.get("on", {})
            if "CANCEL" in transitions:
                targets = self._extract_targets(transitions["CANCEL"])
                for t in targets:
                    t_clean = self._clean_state_name(t)
                    interruptions.append({
                        "from": state_name,
                        "event": "CANCEL",
                        "to": t_clean if t_clean else "none"
                    })

        return interruptions

    def _find_back_paths(self, workflow_id: str) -> list:
        """Find all GO_BACK paths for a workflow.

        Args:
            workflow_id: The workflow to analyze

        Returns:
            List of back path dicts
        """
        workflow_data = self.workflows.get(workflow_id, {})
        states = workflow_data.get("states", {})
        back_paths = []

        for state_name, state_config in states.items():
            transitions = state_config.get("on", {})
            if "GO_BACK" in transitions:
                targets = self._extract_targets(transitions["GO_BACK"])
                for t in targets:
                    t_clean = self._clean_state_name(t)
                    back_paths.append({
                        "from": state_name,
                        "event": "GO_BACK",
                        "to": t_clean if t_clean else "unknown"
                    })

        return back_paths

    def _find_error_paths(self, workflow_id: str) -> list:
        """Find all error transitions for a workflow.

        Args:
            workflow_id: The workflow to analyze

        Returns:
            List of error path dicts
        """
        workflow_data = self.workflows.get(workflow_id, {})
        states = workflow_data.get("states", {})
        error_paths = []

        for state_name, state_config in states.items():
            transitions = state_config.get("on", {})
            for event in ("ON_ERROR", "ERROR"):
                if event in transitions:
                    targets = self._extract_targets(transitions[event])
                    for t in targets:
                        t_clean = self._clean_state_name(t)
                        error_paths.append({
                            "from": state_name,
                            "event": event,
                            "to": t_clean if t_clean else "error"
                        })

        return error_paths

    def _find_completion_paths(self, workflow_id: str) -> list:
        """Find all completion transitions for a workflow.

        Args:
            workflow_id: The workflow to analyze

        Returns:
            List of completion path dicts
        """
        workflow_data = self.workflows.get(workflow_id, {})
        states = workflow_data.get("states", {})
        completion_paths = []

        for state_name, state_config in states.items():
            transitions = state_config.get("on", {})
            for event in ("COMPLETED", "DISMISSED"):
                if event in transitions:
                    targets = self._extract_targets(transitions[event])
                    for t in targets:
                        t_clean = self._clean_state_name(t)
                        completion_paths.append({
                            "from": state_name,
                            "event": event,
                            "to": t_clean if t_clean else "none"
                        })

        return completion_paths

    # ---------------------------------------------------------------------------
    # PHASE 4: Scenario Generation
    # ---------------------------------------------------------------------------

    def generate_scenarios(self) -> list:
        """Generate test scenarios from discovered paths.

        Returns:
            List of scenario dicts:
            [
                {
                    "workflow_id": str,
                    "tc_id": str,
                    "scenario": str,
                    "trace": str,          # State sequence
                    "expected_result": str
                },
                ...
            ]
        """
        scenarios = []
        all_paths = self.discover_all_paths()

        tc_counters = {}  # Track TC numbers per workflow

        for workflow_id, paths in all_paths.items():
            tc_counters[workflow_id] = 1

            # 1. Happy Path
            if paths["happy_path"]:
                trace = " → ".join(paths["happy_path"])
                scenarios.append({
                    "workflow_id": workflow_id,
                    "tc_id": self._make_tc_id(workflow_id, tc_counters[workflow_id]),
                    "scenario": "Happy Path",
                    "trace": trace,
                    "expected_result": "Workflow completed successfully, returns to none"
                })
                tc_counters[workflow_id] += 1

            # 2. Interruptions (CANCEL from each state)
            for interruption in paths["interruptions"]:
                from_state = interruption["from"]
                trace = f"{from_state} → CANCEL → {interruption['to']}"
                scenarios.append({
                    "workflow_id": workflow_id,
                    "tc_id": self._make_tc_id(workflow_id, tc_counters[workflow_id]),
                    "scenario": f"Cancel from {from_state}",
                    "trace": trace,
                    "expected_result": f"Workflow exits to {interruption['to']}, UI overlay closes"
                })
                tc_counters[workflow_id] += 1

            # 3. Back Paths (GO_BACK from each state)
            for back_path in paths["back_paths"]:
                from_state = back_path["from"]
                trace = f"{from_state} → GO_BACK → {back_path['to']}"
                scenarios.append({
                    "workflow_id": workflow_id,
                    "tc_id": self._make_tc_id(workflow_id, tc_counters[workflow_id]),
                    "scenario": f"Back from {from_state}",
                    "trace": trace,
                    "expected_result": f"Returns to {back_path['to']}, preserves context"
                })
                tc_counters[workflow_id] += 1

            # 4. Error Paths
            for error_path in paths["error_paths"]:
                from_state = error_path["from"]
                trace = f"{from_state} → {error_path['event']} → {error_path['to']}"
                scenarios.append({
                    "workflow_id": workflow_id,
                    "tc_id": self._make_tc_id(workflow_id, tc_counters[workflow_id]),
                    "scenario": f"Error from {from_state}",
                    "trace": trace,
                    "expected_result": f"Transitions to {error_path['to']}, shows error state"
                })
                tc_counters[workflow_id] += 1

            # 5. Completion Paths
            for completion in paths["completion_paths"]:
                from_state = completion["from"]
                trace = f"{from_state} → {completion['event']} → {completion['to']}"
                scenarios.append({
                    "workflow_id": workflow_id,
                    "tc_id": self._make_tc_id(workflow_id, tc_counters[workflow_id]),
                    "scenario": f"Completion from {from_state}",
                    "trace": trace,
                    "expected_result": f"Workflow completes, returns to {completion['to']}"
                })
                tc_counters[workflow_id] += 1

        return scenarios

    def _make_tc_id(self, workflow_id: str, number: int) -> str:
        """Generate a test case ID from workflow ID and number.

        Args:
            workflow_id: e.g., "benchmark_workflow"
            number: e.g., 1

        Returns:
            e.g., "TC-BM-01"
        """
        # Create abbreviation from workflow name
        parts = workflow_id.replace("_workflow", "").split("_")
        if len(parts) >= 2:
            abbr = parts[0][0] + parts[1][:1]  # e.g., "benchmark_workflow" → "BM"
        elif len(parts) == 1:
            abbr = parts[0][:2].upper()  # e.g., "checkout" → "CH"
        else:
            abbr = workflow_id[:2].upper()

        return f"TC-{abbr}-{number:02d}"

    # ---------------------------------------------------------------------------
    # PHASE 5: Markdown Generation
    # ---------------------------------------------------------------------------

    def generate_testbook_md(self) -> str:
        """Generate the complete testbook as Markdown.

        Returns:
            Markdown string with all sections
        """
        coverage = self.audit_state_coverage()
        invariants = self.verify_invariants()
        scenarios = self.generate_scenarios()

        lines = []

        # Header
        lines.append("# 🧪 System Testbook")
        lines.append("")
        lines.append(f"> Automated test scenarios generated from XState machine definition.")
        lines.append(f"> Machine: `{self.machine_id}` | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Section 1: State Coverage Audit
        lines.extend(self._render_coverage_audit(coverage))
        lines.append("")
        lines.append("---")
        lines.append("")

        # Section 2: Global Invariants
        lines.extend(self._render_invariants(invariants))
        lines.append("")
        lines.append("---")
        lines.append("")

        # Section 3: Test Scenarios by Workflow
        lines.append("## 📋 Test Scenarios by Workflow")
        lines.append("")

        # Group scenarios by workflow
        workflows_scenarios = {}
        for scenario in scenarios:
            wf = scenario["workflow_id"]
            if wf not in workflows_scenarios:
                workflows_scenarios[wf] = []
            workflows_scenarios[wf].append(scenario)

        for workflow_id, wf_scenarios in workflows_scenarios.items():
            lines.extend(self._render_workflow_table(workflow_id, wf_scenarios))
            lines.append("")

        # Footer
        lines.append("---")
        lines.append("")
        lines.append("## 📊 Summary")
        lines.append("")
        total_scenarios = len(scenarios)
        total_workflows = len(workflows_scenarios)
        lines.append(f"- **Total Workflows:** {total_workflows}")
        lines.append(f"- **Total Test Scenarios:** {total_scenarios}")

        all_pass = all(c["status"] == "PASS" for c in coverage.values())
        all_invariants_pass = all(i["status"] == "PASS" for i in invariants)

        if all_pass and all_invariants_pass:
            lines.append("- **Overall Status:** ✅ ALL PASS - Machine is logically sound")
        else:
            lines.append("- **Overall Status:** ⚠️ WARNINGS DETECTED - Review coverage and invariants above")

        lines.append("")

        return "\n".join(lines)

    def _render_coverage_audit(self, coverage: dict) -> list:
        """Render the State Coverage Audit section."""
        lines = []
        lines.append("## 🔍 State Coverage Audit")
        lines.append("")
        lines.append("| Workflow | Total States | Reachable | Unreachable | Status |")
        lines.append("|----------|-------------|-----------|-------------|--------|")

        has_warnings = False
        for workflow_id, data in coverage.items():
            lines.append(
                f"| {workflow_id} | {data['total_states']} | {data['reachable_states']} "
                f"| {len(data['unreachable_states'])} | {'✅ PASS' if data['status'] == 'PASS' else '⚠️ WARNING'} |"
            )
            if data["status"] == "WARNING":
                has_warnings = True

        lines.append("")

        if has_warnings:
            lines.append("> ⚠️ **WARNING:** Some states are unreachable. These 'orphan' states may indicate")
            lines.append("> missing transitions or dead code in the machine definition.")
            lines.append("")
            for workflow_id, data in coverage.items():
                if data["unreachable_states"]:
                    lines.append(f"> - **{workflow_id}**: Unreachable states: {', '.join(data['unreachable_states'])}")
            lines.append("")
        else:
            lines.append("> ✅ **ALL PASS:** All states are reachable. The machine is logically complete.")
            lines.append("")

        return lines

    def _render_invariants(self, invariants: list) -> list:
        """Render the Global Invariants section."""
        lines = []
        lines.append("## 🔒 Global Invariants")
        lines.append("")
        lines.append("| Invariant | Status | Details |")
        lines.append("|-----------|--------|---------|")

        for inv in invariants:
            status_icon = "✅ PASS" if inv["status"] == "PASS" else "❌ FAIL"
            lines.append(f"| {inv['invariant']} | {status_icon} | {inv['details']} |")

        lines.append("")

        # Show violations if any
        violations = [inv for inv in invariants if inv["violations"]]
        if violations:
            lines.append("> **Violations:**")
            lines.append("")
            for inv in violations:
                lines.append(f"> ### {inv['invariant']}")
                lines.append("")
                for v in inv["violations"]:
                    if "from_state" in v:
                        lines.append(f"> - `{v.get('workflow', '')}`: `{v['from_state']}` → `{v['event']}` → `{v['target']}`")
                    elif "state" in v:
                        lines.append(f"> - `{v['workflow']}` in `{v['state']}`: CANCEL → `{v['target']}` (expected: `{v['expected']}`)")
                    else:
                        lines.append(f"> - `{v['workflow']}`: {v['reason']}")
                lines.append("")

        return lines

    def _render_workflow_table(self, workflow_id: str, scenarios: list) -> list:
        """Render a test scenario table for a single workflow."""
        lines = []
        lines.append(f"### 📊 Workflow: `{workflow_id}`")
        lines.append("")
        lines.append("| ID | Scenario | State Trace | Expected Result |")
        lines.append("|----|----------|-------------|-----------------|")

        for s in scenarios:
            lines.append(
                f"| {s['tc_id']} | {s['scenario']} | {s['trace']} | {s['expected_result']} |"
            )

        lines.append("")
        return lines

    # ---------------------------------------------------------------------------
    # Utility Methods
    # ---------------------------------------------------------------------------

    def _extract_targets(self, target: Any) -> list:
        """Extract target state names from a transition definition.

        Handles:
        - Simple string: "success" → ["success"]
        - Dict with guard: {"target": "success", "cond": "hasData"} → ["success"]
        - Array of conditions: [{"target": "success", "cond": "hasData"}, {"target": "empty"}] → ["success", "empty"]

        Args:
            target: The transition target (string, dict, or list)

        Returns:
            List of target state names
        """
        if isinstance(target, str):
            return [target]
        elif isinstance(target, dict):
            t = target.get("target", "")
            return [t] if t else []
        elif isinstance(target, list):
            targets = []
            for item in target:
                if isinstance(item, dict):
                    t = item.get("target", "")
                    if t:
                        targets.append(t)
                elif isinstance(item, str):
                    targets.append(item)
            return targets
        return []

    def _clean_state_name(self, name: str) -> str:
        """Clean a state name by removing relative path prefixes.

        Args:
            name: e.g., ".viewing" or "benchmark_workflow.viewing"

        Returns:
            e.g., "viewing"
        """
        if not name:
            return ""
        # Remove leading dot (relative path)
        if name.startswith("."):
            name = name[1:]
        # Take only the last part of dotted paths
        if "." in name:
            name = name.split(".")[-1]
        return name