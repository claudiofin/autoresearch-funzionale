"""Tests for state_machine/validation.py"""

import pytest
import json
import tempfile
import os
from state_machine.validation import (
    _extract_targets,
    _suggest_exit_transitions,
    find_dead_end_states,
    find_unreachable_states,
    find_invalid_transitions,
    find_potential_infinite_loops,
    validate_machine,
)


class TestExtractTargets:
    def test_string_target(self):
        assert _extract_targets("success") == ["success"]

    def test_dict_target(self):
        assert _extract_targets({"target": "success", "cond": "hasData"}) == ["success"]

    def test_list_targets(self):
        result = _extract_targets([
            {"target": "success", "cond": "hasData"},
            {"target": "empty"},
        ])
        assert result == ["success", "empty"]

    def test_empty_dict(self):
        assert _extract_targets({}) == []

    def test_none(self):
        assert _extract_targets(None) == []


class TestSuggestExitTransitions:
    def test_error_state(self):
        result = _suggest_exit_transitions("error")
        assert "RETRY" in result
        assert "CANCEL" in result

    def test_loading_state(self):
        result = _suggest_exit_transitions("loading")
        assert "CANCEL" in result
        assert "TIMEOUT" in result

    def test_empty_state(self):
        result = _suggest_exit_transitions("empty")
        assert "REFRESH" in result

    def test_session_state(self):
        result = _suggest_exit_transitions("session_expired")
        assert "REAUTHENTICATE" in result

    def test_generic_state(self):
        result = _suggest_exit_transitions("unknown_state")
        assert "exit transition" in result.lower()


class TestFindDeadEndStates:
    def test_finds_dead_end(self):
        machine = {
            "states": {
                "idle": {"on": {"START": "loading"}},
                "loading": {"on": {}},  # dead end
            }
        }
        result = find_dead_end_states(machine)
        assert len(result) == 1
        assert result[0]["state"] == "loading"

    def test_ignores_success_state(self):
        machine = {
            "states": {
                "success": {"on": {}},
            }
        }
        result = find_dead_end_states(machine)
        assert len(result) == 0

    def test_ignores_ready_state(self):
        machine = {
            "states": {
                "ready": {"on": {}},
            }
        }
        result = find_dead_end_states(machine)
        assert len(result) == 0

    def test_no_dead_ends(self):
        machine = {
            "states": {
                "idle": {"on": {"START": "loading"}},
                "loading": {"on": {"SUCCESS": "success"}},
                "success": {"on": {}},
            }
        }
        result = find_dead_end_states(machine)
        assert len(result) == 0


class TestFindUnreachableStates:
    def test_finds_unreachable(self):
        machine = {
            "initial": "idle",
            "states": {
                "idle": {"on": {"START": "loading"}},
                "loading": {"on": {}},
                "orphan": {"on": {}},  # unreachable
            }
        }
        result = find_unreachable_states(machine)
        assert len(result) == 1
        assert result[0]["state"] == "orphan"

    def test_all_reachable(self):
        machine = {
            "initial": "idle",
            "states": {
                "idle": {"on": {"START": "loading"}},
                "loading": {"on": {"SUCCESS": "success"}},
                "success": {"on": {}},
            }
        }
        result = find_unreachable_states(machine)
        assert len(result) == 0

    def test_invalid_initial(self):
        machine = {
            "initial": "nonexistent",
            "states": {"idle": {"on": {}}},
        }
        result = find_unreachable_states(machine)
        assert any(r.get("issue") == "INVALID_INITIAL" for r in result)


class TestFindInvalidTransitions:
    def test_finds_invalid_target(self):
        machine = {
            "states": {
                "idle": {"on": {"START": "nonexistent"}},
            }
        }
        result = find_invalid_transitions(machine)
        assert len(result) == 1
        assert result[0]["target"] == "nonexistent"

    def test_all_valid(self):
        machine = {
            "states": {
                "idle": {"on": {"START": "loading"}},
                "loading": {"on": {"SUCCESS": "success"}},
                "success": {"on": {}},
            }
        }
        result = find_invalid_transitions(machine)
        assert len(result) == 0


class TestFindPotentialInfiniteLoops:
    def test_finds_bidirectional_loop(self):
        machine = {
            "states": {
                "A": {"on": {"NEXT": "B"}},
                "B": {"on": {"BACK": "A"}},
            }
        }
        result = find_potential_infinite_loops(machine)
        assert len(result) > 0

    def test_no_loop_with_exit(self):
        machine = {
            "states": {
                "A": {"on": {"NEXT": "B", "EXIT": "C"}},
                "B": {"on": {"BACK": "A", "EXIT": "C"}},
                "C": {"on": {}},
            }
        }
        result = find_potential_infinite_loops(machine)
        assert len(result) == 0


class TestValidateMachine:
    def test_valid_machine(self):
        machine = {
            "id": "test",
            "initial": "idle",
            "states": {
                "idle": {"on": {"START": "loading"}},
                "loading": {"on": {"SUCCESS": "success"}},
                "success": {"on": {}},
            },
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(machine, f)
            f.flush()
            result = validate_machine(f.name)
            os.unlink(f.name)

        assert result["is_valid"] is True
        assert result["quality_score"] == 100
        assert result["dead_end_count"] == 0
        assert result["unreachable_count"] == 0
        assert result["invalid_transition_count"] == 0

    def test_invalid_machine(self):
        machine = {
            "id": "test",
            "initial": "idle",
            "states": {
                "idle": {"on": {"START": "nonexistent"}},
                "orphan": {"on": {}},
            },
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(machine, f)
            f.flush()
            result = validate_machine(f.name)
            os.unlink(f.name)

        assert result["is_valid"] is False
        assert result["invalid_transition_count"] > 0
        assert result["unreachable_count"] > 0