import pytest
import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from validator import validate_machine

def test_validate_dead_end():
    machine = {
        "id": "test",
        "initial": "a",
        "states": {
            "a": {"on": {"NEXT": "b"}},
            "b": {"on": {}} # Dead end
        }
    }
    results = validate_machine(machine)
    assert results["dead_end_count"] == 1
    assert results["dead_end_states"][0]["state"] == "b"

def test_validate_unreachable():
    machine = {
        "id": "test",
        "initial": "a",
        "states": {
            "a": {"on": {}},
            "b": {"on": {}} # Unreachable
        }
    }
    results = validate_machine(machine)
    assert results["unreachable_count"] == 1
    assert results["unreachable_states"][0] == "b"

def test_validate_quality_score_perfect():
    machine = {
        "id": "test",
        "initial": "a",
        "states": {
            "a": {"on": {"NEXT": "a"}} # Simple self-loop
        }
    }
    results = validate_machine(machine)
    assert results["quality_score"] == 100
    assert results["is_valid"] is True

def test_validate_invalid_transition():
    machine = {
        "id": "test",
        "initial": "a",
        "states": {
            "a": {"on": {"NEXT": "non_existent"}}
        }
    }
    results = validate_machine(machine)
    assert results["invalid_transition_count"] == 1
