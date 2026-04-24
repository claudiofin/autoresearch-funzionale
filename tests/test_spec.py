import pytest
import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from spec import (
    _build_state_config, 
    _add_transitions, 
    _complete_missing_branches, 
    _clean_unreachable_states,
    _validate_no_critical_patterns
)

def test_build_state_config_flat():
    state = {
        "name": "idle",
        "entry_actions": ["log"],
        "exit_actions": ["cleanup"]
    }
    config = _build_state_config(state)
    assert config["entry"] == ["log"]
    assert config["exit"] == ["cleanup"]
    assert "states" not in config

def test_build_state_config_hierarchical():
    state = {
        "name": "success",
        "sub_states": ["dashboard", "catalog"],
        "initial_sub_state": "dashboard"
    }
    config = _build_state_config(state)
    assert config["initial"] == "dashboard"
    assert "dashboard" in config["states"]
    assert "catalog" in config["states"]
    # Check auto-generated navigation
    assert config["states"]["dashboard"]["on"]["NAVIGATE_CATALOG"] == ".catalog"
    assert config["states"]["catalog"]["on"]["NAVIGATE_DASHBOARD"] == ".dashboard"

def test_add_transitions_dot_notation():
    machine = {
        "states": {
            "success": {
                "states": {
                    "dashboard": {"on": {}}
                }
            }
        }
    }
    transitions = [
        {"from_state": "success.dashboard", "to_state": "catalog", "event": "GO_TO_CATALOG"}
    ]
    _add_transitions(machine, transitions)
    # Should resolve to the nested state and make target relative
    assert machine["states"]["success"]["states"]["dashboard"]["on"]["GO_TO_CATALOG"] == ".catalog"

def test_complete_missing_branches():
    machine = {
        "states": {
            "loading": {
                "on": {
                    "ON_SUCCESS": {"target": "empty", "cond": "!hasData"}
                }
            }
        }
    }
    fixed = _complete_missing_branches(machine)
    transitions = fixed["states"]["loading"]["on"]["ON_SUCCESS"]
    assert len(transitions) == 2
    guards = [t.get("cond") for t in transitions]
    assert "hasData" in guards
    assert "!hasData" in guards

def test_clean_unreachable_states():
    machine = {
        "initial": "app_idle",
        "states": {
            "app_idle": {"on": {"START": "loading"}},
            "loading": {"on": {"OK": "success"}},
            "success": {"on": {}},
            "ghost_state": {"on": {}} # Unreachable
        }
    }
    cleaned = _clean_unreachable_states(machine)
    assert "ghost_state" not in cleaned["states"]
    assert "app_idle" in cleaned["states"]
    assert "success" in cleaned["states"]

def test_validate_no_critical_patterns_violations():
    machine = {
        "states": {
            # Violation 16: checkAuth in entry
            "app_idle": {"entry": ["checkAuth"]},
            # Violation 17: top-level clustering
            "clustering_calculation": {"on": {}},
            "success": {
                "states": {
                    # Violation 15: success_ prefix
                    "dashboard": {},
                    "success_dashboard": {}
                }
            }
        }
    }
    violations = _validate_no_critical_patterns(machine)
    assert len(violations) == 3
    assert any("REGOLA 15" in v for v in violations)
    assert any("REGOLA 16" in v for v in violations)
    assert any("REGOLA 17" in v for v in violations)
