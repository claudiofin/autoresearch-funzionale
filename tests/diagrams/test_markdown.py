"""Tests for diagrams/markdown.py"""

import pytest
from diagrams.markdown import generate_spec_markdown as generate_markdown_spec


def _make_llm_data():
    return {
        "edge_cases": [],
        "flows": [],
        "error_handling": [],
        "api_contracts": [],
    }


def _make_diagrams():
    return "@startuml\n@enduml", "@startuml\n@enduml"


class TestGenerateMarkdownSpec:
    def test_returns_string(self):
        machine = {
            "id": "test",
            "initial": "idle",
            "states": {
                "idle": {"entry": [], "exit": [], "on": {"START": "loading"}},
                "loading": {"entry": ["show_spinner"], "exit": [], "on": {"SUCCESS": "success", "ERROR": "error"}},
                "success": {"entry": [], "exit": [], "on": {}},
                "error": {"entry": ["show_error"], "exit": [], "on": {"RETRY": "loading"}},
            },
        }
        statechart, sequence = _make_diagrams()
        result = generate_markdown_spec(machine, _make_llm_data(), statechart, sequence)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_state_names(self):
        machine = {
            "id": "test",
            "initial": "idle",
            "states": {
                "idle": {"entry": [], "exit": [], "on": {}},
                "loading": {"entry": [], "exit": [], "on": {}},
                "success": {"entry": [], "exit": [], "on": {}},
            },
        }
        statechart, sequence = _make_diagrams()
        result = generate_markdown_spec(machine, _make_llm_data(), statechart, sequence)
        assert "idle" in result
        assert "loading" in result
        assert "success" in result

    def test_contains_transitions(self):
        machine = {
            "id": "test",
            "initial": "idle",
            "states": {
                "idle": {"entry": [], "exit": [], "on": {"START": "loading"}},
                "loading": {"entry": [], "exit": [], "on": {"SUCCESS": "success"}},
                "success": {"entry": [], "exit": [], "on": {}},
            },
        }
        statechart, sequence = _make_diagrams()
        result = generate_markdown_spec(machine, _make_llm_data(), statechart, sequence)
        assert "START" in result
        assert "SUCCESS" in result

    def test_contains_entry_actions(self):
        machine = {
            "id": "test",
            "initial": "loading",
            "states": {
                "loading": {"entry": ["show_spinner", "fetch_data"], "exit": [], "on": {}},
            },
        }
        statechart, sequence = _make_diagrams()
        result = generate_markdown_spec(machine, _make_llm_data(), statechart, sequence)
        assert "show_spinner" in result
        assert "fetch_data" in result

    def test_handles_compound_states(self):
        machine = {
            "id": "test",
            "initial": "success",
            "states": {
                "success": {
                    "entry": [],
                    "exit": [],
                    "on": {},
                    "states": {
                        "loading": {"entry": ["show_shimmer"], "exit": [], "on": {"FETCH_SUCCESS": "ready"}},
                        "ready": {"entry": ["render_grid"], "exit": [], "on": {}},
                    },
                },
            },
        }
        statechart, sequence = _make_diagrams()
        result = generate_markdown_spec(machine, _make_llm_data(), statechart, sequence)
        assert "loading" in result
        assert "ready" in result
        assert "show_shimmer" in result
        assert "render_grid" in result

    def test_empty_machine(self):
        machine = {"id": "empty", "initial": "idle", "states": {"idle": {"entry": [], "exit": [], "on": {}}}}
        statechart, sequence = _make_diagrams()
        result = generate_markdown_spec(machine, _make_llm_data(), statechart, sequence)
        assert isinstance(result, str)