"""Tests for state_machine/builder.py"""

import pytest
import json
from state_machine.builder import (
    generate_base_machine,
    build_state_config,
    add_transitions,
    add_transitions_to_branch,
    normalize_machine,
    build_workflow_compound_state,
    add_workflows_to_machine,
    _format_xstate_actions,
    compile_machine,
    apply_branch_placement,
)


class TestGenerateBaseMachine:
    def test_returns_dict_with_required_keys(self):
        machine = generate_base_machine(use_parallel=False)
        assert "id" in machine
        assert "initial" in machine
        assert "context" in machine
        assert "states" in machine

    def test_initial_state_is_app_idle(self):
        machine = generate_base_machine(use_parallel=False)
        assert machine["initial"] == "app_idle"

    def test_context_has_default_values(self):
        machine = generate_base_machine()
        ctx = machine["context"]
        assert ctx["user"] is None
        assert ctx["errors"] == []
        assert ctx["retryCount"] == 0
        assert ctx["previousState"] is None

    def test_states_starts_empty_flat(self):
        machine = generate_base_machine(use_parallel=False)
        assert machine["states"] == {}

    def test_states_has_parallel_branches(self):
        machine = generate_base_machine(use_parallel=True)
        assert "navigation" in machine["states"]
        assert "active_workflows" in machine["states"]


class TestFormatXStateActions:
    def test_plain_action_kept_as_string(self):
        result = _format_xstate_actions(["show_toast", "log_event"])
        assert result == ["show_toast", "log_event"]

    def test_increment_retry_count_becomes_assign(self):
        result = _format_xstate_actions(["incrementRetryCount"])
        assert len(result) == 1
        action = result[0]
        assert action["type"] == "assign"
        assert "retryCount" in action["assignment"]

    def test_set_previous_state_becomes_assign(self):
        result = _format_xstate_actions(["setPreviousState"])
        assert len(result) == 1
        action = result[0]
        assert action["type"] == "assign"
        assert "previousState" in action["assignment"]

    def test_mixed_actions(self):
        result = _format_xstate_actions(["show_toast", "incrementRetryCount", "log_event"])
        assert result[0] == "show_toast"
        assert result[2] == "log_event"
        assert result[1]["type"] == "assign"

    def test_empty_list(self):
        result = _format_xstate_actions([])
        assert result == []


class TestBuildStateConfig:
    def test_flat_state_has_entry_exit_on(self):
        state = {
            "entry_actions": ["show_loading"],
            "exit_actions": ["hide_loading"],
        }
        config = build_state_config(state)
        assert config["entry"] == ["show_loading"]
        assert config["exit"] == ["hide_loading"]
        assert config["on"] == {}

    def test_flat_state_defaults_empty_lists(self):
        config = build_state_config({})
        assert config["entry"] == []
        assert config["exit"] == []
        assert config["on"] == {}

    def test_compound_state_with_sub_states(self):
        state = {
            "entry_actions": ["enter_catalog"],
            "sub_states": ["loading", "ready", "error"],
        }
        config = build_state_config(state)
        assert "initial" in config
        assert "states" in config
        assert "loading" in config["states"]
        assert "ready" in config["states"]
        assert "error" in config["states"]

    def test_compound_state_initial_is_first_sub(self):
        state = {
            "sub_states": ["loading", "ready", "error"],
        }
        config = build_state_config(state)
        assert config["initial"] == "loading"

    def test_compound_state_custom_initial(self):
        state = {
            "initial_sub_state": "ready",
            "sub_states": ["loading", "ready", "error"],
        }
        config = build_state_config(state)
        assert config["initial"] == "ready"

    def test_compound_state_sub_with_entry_actions(self):
        state = {
            "sub_states": [
                {"name": "loading", "entry_actions": ["show_shimmer"]},
                {"name": "ready", "entry_actions": ["render_grid"]},
            ],
        }
        config = build_state_config(state)
        assert config["states"]["loading"]["entry"] == ["show_shimmer"]
        assert config["states"]["ready"]["entry"] == ["render_grid"]

    def test_compound_state_generates_nav_events(self):
        state = {
            "sub_states": ["loading", "ready"],
        }
        config = build_state_config(state)
        # loading should have NAVIGATE_READY event
        assert "NAVIGATE_READY" in config["states"]["loading"]["on"]
        # ready should have NAVIGATE_LOADING event
        assert "NAVIGATE_LOADING" in config["states"]["ready"]["on"]

    def test_compound_state_nav_targets_use_dot_notation(self):
        state = {
            "sub_states": ["loading", "ready"],
        }
        config = build_state_config(state)
        nav_target = config["states"]["loading"]["on"]["NAVIGATE_READY"]
        assert nav_target.startswith(".")

    def test_sub_state_name_stripped_of_dot_prefix(self):
        state = {
            "sub_states": [
                {"name": "success.loading", "entry_actions": ["a"]},
                {"name": "success.ready", "entry_actions": ["b"]},
            ],
        }
        config = build_state_config(state)
        assert "loading" in config["states"]
        assert "ready" in config["states"]
        assert "success.loading" not in config["states"]


class TestAddTransitions:
    def _make_machine(self):
        return {
            "id": "test",
            "initial": "idle",
            "context": {},
            "states": {
                "idle": {"entry": [], "exit": [], "on": {}},
                "loading": {"entry": [], "exit": [], "on": {}},
                "success": {
                    "entry": [],
                    "exit": [],
                    "on": {},
                    "states": {
                        "dashboard": {"entry": [], "exit": [], "on": {}},
                    },
                },
            },
        }

    def test_simple_transition(self):
        machine = self._make_machine()
        add_transitions(machine, [{"from_state": "idle", "to_state": "loading", "event": "START"}])
        assert machine["states"]["idle"]["on"]["START"] == "loading"

    def test_transition_with_guard(self):
        machine = self._make_machine()
        add_transitions(machine, [{
            "from_state": "idle",
            "to_state": "loading",
            "event": "START",
            "guard": "hasToken",
        }])
        trans = machine["states"]["idle"]["on"]["START"]
        assert trans["target"] == "loading"
        assert trans["cond"] == "hasToken"

    def test_transition_with_actions(self):
        machine = self._make_machine()
        add_transitions(machine, [{
            "from_state": "idle",
            "to_state": "loading",
            "event": "START",
            "actions": ["show_toast"],
        }])
        trans = machine["states"]["idle"]["on"]["START"]
        assert "actions" in trans
        assert "show_toast" in trans["actions"]

    def test_skips_transition_missing_from_state(self, capsys):
        machine = self._make_machine()
        add_transitions(machine, [{"to_state": "loading", "event": "START"}])
        captured = capsys.readouterr()
        assert "missing required fields" in captured.out

    def test_skips_transition_missing_to_state(self, capsys):
        machine = self._make_machine()
        add_transitions(machine, [{"from_state": "idle", "event": "START"}])
        captured = capsys.readouterr()
        assert "missing required fields" in captured.out

    def test_skips_transition_missing_event(self, capsys):
        machine = self._make_machine()
        add_transitions(machine, [{"from_state": "idle", "to_state": "loading"}])
        captured = capsys.readouterr()
        assert "missing required fields" in captured.out

    def test_dot_notation_transition(self):
        machine = self._make_machine()
        add_transitions(machine, [{
            "from_state": "success.dashboard",
            "to_state": "ready",
            "event": "FETCH_SUCCESS",
        }])
        # Should add to the nested dashboard state
        assert "FETCH_SUCCESS" in machine["states"]["success"]["states"]["dashboard"]["on"]

    def test_action_string_converted_to_list(self):
        machine = self._make_machine()
        add_transitions(machine, [{
            "from_state": "idle",
            "to_state": "loading",
            "event": "START",
            "actions": "show_toast",  # string instead of list
        }])
        trans = machine["states"]["idle"]["on"]["START"]
        assert "actions" in trans


class TestNormalizeMachine:
    def test_renames_idle_to_app_idle(self):
        machine = {
            "initial": "app_idle",
            "states": {
                "idle": {"entry": [], "exit": [], "on": {"START": "loading"}},
                "loading": {"entry": [], "exit": [], "on": {}},
            },
        }
        result = normalize_machine(machine)
        assert "app_idle" in result["states"]
        assert "idle" not in result["states"]

    def test_updates_transitions_to_idle(self):
        machine = {
            "initial": "app_idle",
            "states": {
                "idle": {"entry": [], "exit": [], "on": {}},
                "loading": {"entry": [], "exit": [], "on": {"CANCEL": "idle"}},
            },
        }
        result = normalize_machine(machine)
        assert result["states"]["loading"]["on"]["CANCEL"] == "app_idle"

    def test_creates_initial_state_if_missing(self):
        """STRUCTURAL: creates the state named in 'initial' if it doesn't exist."""
        # Case 1: initial is "app_idle" but doesn't exist → create it
        machine = {
            "initial": "app_idle",
            "states": {
                "loading": {"entry": [], "exit": [], "on": {}},
            },
        }
        result = normalize_machine(machine)
        assert "app_idle" in result["states"]
        
        # Case 2: initial is "loading" and already exists → no extra state needed
        machine2 = {
            "initial": "loading",
            "states": {
                "loading": {"entry": [], "exit": [], "on": {}},
            },
        }
        result2 = normalize_machine(machine2)
        assert "loading" in result2["states"]
        assert len(result2["states"]) == 1  # No extra state created

    def test_parallel_architecture_has_navigation_and_workflows(self):
        machine = generate_base_machine(use_parallel=True)
        assert machine["type"] == "parallel"
        assert "navigation" in machine["states"]
        assert "active_workflows" in machine["states"]

    def test_parallel_architecture_initial_in_navigation(self):
        machine = generate_base_machine(use_parallel=True)
        assert machine["states"]["navigation"]["initial"] == "app_idle"

    def test_parallel_architecture_workflows_starts_with_none(self):
        machine = generate_base_machine(use_parallel=True)
        assert "none" in machine["states"]["active_workflows"]["states"]

    def test_flat_architecture_no_parallel_type(self):
        machine = generate_base_machine(use_parallel=False)
        assert machine.get("type") != "parallel"
        assert "navigation" not in machine["states"]


class TestAddTransitionsToBranch:
    def _make_parallel_machine(self):
        return {
            "id": "appFlow",
            "type": "parallel",
            "context": {"user": None, "errors": [], "retryCount": 0, "previousState": None},
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {"entry": [], "exit": [], "on": {}},
                        "loading": {"entry": [], "exit": [], "on": {}},
                        "success": {
                            "entry": [],
                            "exit": [],
                            "on": {},
                            "states": {
                                "dashboard": {"entry": [], "exit": [], "on": {}},
                                "catalog": {"entry": [], "exit": [], "on": {}},
                            },
                        },
                    },
                },
                "active_workflows": {
                    "initial": "none",
                    "states": {"none": {}},
                },
            },
        }

    def test_simple_transition_in_navigation(self):
        machine = self._make_parallel_machine()
        add_transitions_to_branch(machine, [
            {"from_state": "app_idle", "to_state": "loading", "event": "START_APP"}
        ])
        nav = machine["states"]["navigation"]["states"]
        # Target is resolved as sibling within the navigation branch
        assert nav["app_idle"]["on"]["START_APP"] == "loading"

    def test_transition_with_guard_in_navigation(self):
        machine = self._make_parallel_machine()
        add_transitions_to_branch(machine, [
            {
                "from_state": "loading",
                "to_state": "success",
                "event": "ON_SUCCESS",
                "guard": "hasData",
            }
        ])
        nav = machine["states"]["navigation"]["states"]
        trans = nav["loading"]["on"]["ON_SUCCESS"]
        # Target is resolved as sibling within the navigation branch
        assert trans["target"] == "success"
        assert trans["cond"] == "hasData"

    def test_dot_notation_in_navigation_branch(self):
        machine = self._make_parallel_machine()
        add_transitions_to_branch(machine, [
            {
                "from_state": "success.dashboard",
                "to_state": "catalog",
                "event": "NAVIGATE_CATALOG",
            }
        ])
        nav = machine["states"]["navigation"]["states"]["success"]["states"]
        assert "NAVIGATE_CATALOG" in nav["dashboard"]["on"]

    def test_skips_invalid_transitions(self):
        machine = self._make_parallel_machine()
        # Invalid transitions are silently skipped (no print)
        add_transitions_to_branch(machine, [
            {"to_state": "loading", "event": "START"},  # missing from_state
            {"from_state": "app_idle", "event": "START"},  # missing to_state
            {"from_state": "app_idle", "to_state": "loading"},  # missing event
        ])
        # Verify no transitions were added to app_idle
        nav = machine["states"]["navigation"]["states"]
        assert nav["app_idle"]["on"] == {}


class TestBuildWorkflowCompoundState:
    def test_workflow_has_initial_and_states(self):
        workflow = {
            "id": "benchmark_workflow",
            "name": "Benchmark Comparison",
            "steps": ["discovery", "viewing", "joining", "tracking"],
            "cross_page_events": ["VIEW_DETAILS", "JOIN_GROUP", "CONFIRM_JOIN"],
            "completion_events": ["COMPLETED", "CANCELLED"],
        }
        result = build_workflow_compound_state(workflow)
        assert result["initial"] == "discovery"
        assert "discovery" in result["states"]
        assert "viewing" in result["states"]
        assert "joining" in result["states"]
        assert "tracking" in result["states"]

    def test_workflow_steps_have_entry_actions(self):
        workflow = {
            "id": "benchmark_workflow",
            "name": "Benchmark Comparison",
            "steps": ["discovery", "viewing"],
            "cross_page_events": ["VIEW_DETAILS"],
            "completion_events": ["COMPLETED"],
        }
        result = build_workflow_compound_state(workflow)
        assert "showDiscovery" in result["states"]["discovery"]["entry"]
        assert "showViewing" in result["states"]["viewing"]["entry"]

    def test_workflow_steps_have_next_transition(self):
        workflow = {
            "id": "benchmark_workflow",
            "name": "Benchmark Comparison",
            "steps": ["discovery", "viewing", "joining"],
            "cross_page_events": ["VIEW_DETAILS", "JOIN_GROUP"],
            "completion_events": ["COMPLETED"],
        }
        result = build_workflow_compound_state(workflow)
        assert result["states"]["discovery"]["on"]["VIEW_DETAILS"] == "viewing"
        assert result["states"]["viewing"]["on"]["JOIN_GROUP"] == "joining"

    def test_workflow_steps_have_go_back_transition(self):
        workflow = {
            "id": "benchmark_workflow",
            "name": "Benchmark Comparison",
            "steps": ["discovery", "viewing"],
            "cross_page_events": ["VIEW_DETAILS"],
            "completion_events": ["COMPLETED"],
        }
        result = build_workflow_compound_state(workflow)
        assert result["states"]["viewing"]["on"]["GO_BACK"] == "discovery"
        assert result["states"]["discovery"]["on"]["GO_BACK"] == "none"

    def test_workflow_steps_have_cancel_transition(self):
        workflow = {
            "id": "benchmark_workflow",
            "name": "Benchmark Comparison",
            "steps": ["discovery", "viewing"],
            "cross_page_events": ["VIEW_DETAILS"],
            "completion_events": ["COMPLETED"],
        }
        result = build_workflow_compound_state(workflow)
        assert result["states"]["discovery"]["on"]["CANCEL"] == "none"
        assert result["states"]["viewing"]["on"]["CANCEL"] == "none"

    def test_last_step_has_completion_events(self):
        workflow = {
            "id": "benchmark_workflow",
            "name": "Benchmark Comparison",
            "steps": ["discovery", "tracking"],
            "cross_page_events": ["CONFIRM_JOIN"],
            "completion_events": ["COMPLETED", "CANCELLED"],
        }
        result = build_workflow_compound_state(workflow)
        last_step = result["states"]["tracking"]["on"]
        assert last_step["COMPLETED"] == "none"
        assert last_step["CANCELLED"] == "none"

    def test_empty_steps_returns_empty_dict(self):
        workflow = {
            "id": "empty_workflow",
            "name": "Empty",
            "steps": [],
            "cross_page_events": [],
            "completion_events": [],
        }
        result = build_workflow_compound_state(workflow)
        assert result == {}

    def test_cross_page_navigation_events(self):
        workflow = {
            "id": "benchmark_workflow",
            "name": "Benchmark Comparison",
            "steps": ["discovery"],
            "cross_page_events": ["NAVIGATE_DASHBOARD"],
            "completion_events": ["COMPLETED"],
        }
        result = build_workflow_compound_state(workflow)
        assert "NAVIGATE_DASHBOARD" in result["on"]
        assert result["on"]["NAVIGATE_DASHBOARD"] == "#navigation.success.dashboard"


class TestAddWorkflowsToMachine:
    def _make_parallel_machine(self):
        return {
            "id": "appFlow",
            "type": "parallel",
            "context": {"user": None, "errors": [], "retryCount": 0, "previousState": None},
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {"entry": [], "exit": [], "on": {}},
                    },
                },
                "active_workflows": {
                    "initial": "none",
                    "states": {"none": {}},
                },
            },
        }

    def test_adds_workflow_to_active_workflows(self):
        machine = self._make_parallel_machine()
        workflows = [
            {
                "id": "benchmark_workflow",
                "name": "Benchmark Comparison",
                "steps": ["discovery", "viewing"],
                "cross_page_events": ["VIEW_DETAILS"],
                "completion_events": ["COMPLETED"],
            }
        ]
        add_workflows_to_machine(machine, workflows)
        assert "benchmark_workflow" in machine["states"]["active_workflows"]["states"]

    def test_workflow_has_compound_state_structure(self):
        machine = self._make_parallel_machine()
        workflows = [
            {
                "id": "benchmark_workflow",
                "name": "Benchmark Comparison",
                "steps": ["discovery", "viewing"],
                "cross_page_events": ["VIEW_DETAILS"],
                "completion_events": ["COMPLETED"],
            }
        ]
        add_workflows_to_machine(machine, workflows)
        wf = machine["states"]["active_workflows"]["states"]["benchmark_workflow"]
        assert wf["initial"] == "discovery"
        assert "discovery" in wf["states"]
        assert "viewing" in wf["states"]

    def test_multiple_workflows(self):
        machine = self._make_parallel_machine()
        workflows = [
            {
                "id": "benchmark_workflow",
                "name": "Benchmark",
                "steps": ["discovery"],
                "cross_page_events": [],
                "completion_events": ["COMPLETED"],
            },
            {
                "id": "purchase_group_workflow",
                "name": "Purchase Group",
                "steps": ["browsing", "joining"],
                "cross_page_events": ["JOIN_GROUP"],
                "completion_events": ["COMPLETED"],
            },
        ]
        add_workflows_to_machine(machine, workflows)
        aw = machine["states"]["active_workflows"]["states"]
        assert "benchmark_workflow" in aw
        assert "purchase_group_workflow" in aw

    def test_removes_machine_id_as_state_name(self):
        """Fix A: apply_branch_placement removes states whose name equals machine.id."""
        machine = {
            "id": "appFlow",
            "type": "parallel",
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {},
                },
                "active_workflows": {
                    "initial": "none",
                    "states": {},
                },
                # This is the LLM error: machine.id used as a state name
                "appFlow": {
                    "entry": ["initContext"],
                    "exit": [],
                    "on": {},
                    "initial": "navigation",
                    "states": {
                        "loading": {"entry": ["showLoading"], "exit": [], "on": {}},
                        "ready": {"entry": ["initContext"], "exit": [], "on": {}},
                        "error": {"entry": ["logError"], "exit": [], "on": {}},
                    },
                },
            },
        }
        result = apply_branch_placement(machine)
        # appFlow should be removed from root-level states
        assert "appFlow" not in result["states"]
        # The compound state should be moved to workflows branch
        wf = result["states"].get("active_workflows", {}).get("states", {})
        assert "appFlow" in wf

    def test_compile_machine_removes_machine_id_state(self):
        """Fix A: full compile_machine pipeline removes machine.id as state."""
        machine = {
            "id": "myApp",
            "type": "parallel",
            "context": {"user": None, "errors": [], "retryCount": 0, "previousState": None},
            "states": {
                "navigation": {
                    "initial": "home",
                    "states": {},
                },
                "workflows": {
                    "initial": "none",
                    "states": {"none": {"entry": ["hideOverlay"], "exit": [], "on": {}}},
                },
                # LLM error: machine.id as state
                "myApp": {
                    "entry": ["initApp"],
                    "exit": [],
                    "on": {},
                    "states": {
                        "splash": {"entry": ["showSplash"], "exit": [], "on": {}},
                    },
                },
            },
        }
        result = compile_machine(machine)
        # myApp should NOT be at root level
        assert "myApp" not in result["states"]

    def test_no_active_workflows_branch(self):
        machine = {
            "id": "appFlow",
            "initial": "app_idle",
            "states": {"app_idle": {"entry": [], "exit": [], "on": {}}},
        }
        workflows = [
            {
                "id": "benchmark_workflow",
                "name": "Benchmark",
                "steps": ["discovery"],
                "cross_page_events": [],
                "completion_events": ["COMPLETED"],
            }
        ]
        # Should not raise, just does nothing
        add_workflows_to_machine(machine, workflows)
        assert "benchmark_workflow" not in machine["states"]
