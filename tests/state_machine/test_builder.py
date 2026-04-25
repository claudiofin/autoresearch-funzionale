"""Tests for state_machine/builder.py"""

import pytest
import json
from state_machine.builder import (
    generate_base_machine,
    build_state_config,
    add_transitions,
    normalize_machine,
    _format_xstate_actions,
)


class TestGenerateBaseMachine:
    def test_returns_dict_with_required_keys(self):
        machine = generate_base_machine()
        assert "id" in machine
        assert "initial" in machine
        assert "context" in machine
        assert "states" in machine

    def test_initial_state_is_app_idle(self):
        machine = generate_base_machine()
        assert machine["initial"] == "app_idle"

    def test_context_has_default_values(self):
        machine = generate_base_machine()
        ctx = machine["context"]
        assert ctx["user"] is None
        assert ctx["errors"] == []
        assert ctx["retryCount"] == 0
        assert ctx["previousState"] is None

    def test_states_starts_empty(self):
        machine = generate_base_machine()
        assert machine["states"] == {}


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
        assert "missing 'from_state'" in captured.out

    def test_skips_transition_missing_to_state(self, capsys):
        machine = self._make_machine()
        add_transitions(machine, [{"from_state": "idle", "event": "START"}])
        captured = capsys.readouterr()
        assert "missing 'to_state'" in captured.out

    def test_skips_transition_missing_event(self, capsys):
        machine = self._make_machine()
        add_transitions(machine, [{"from_state": "idle", "to_state": "loading"}])
        captured = capsys.readouterr()
        assert "missing 'event'" in captured.out

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

    def test_creates_app_idle_if_missing(self):
        machine = {
            "initial": "loading",
            "states": {
                "loading": {"entry": [], "exit": [], "on": {}},
            },
        }
        result = normalize_machine(machine)
        assert "app_idle" in result["states"]