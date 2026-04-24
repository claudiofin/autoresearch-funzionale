import pytest
import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from pipeline.frontend.fuzzer import run_fuzz_test

def test_run_fuzz_test_basic():
    machine = {
        "id": "test",
        "initial": "a",
        "states": {
            "a": {"on": {"NEXT": "b"}},
            "b": {"on": {"BACK": "a"}}
        }
    }
    # Test that it can run without crashing and find paths
    report = run_fuzz_test(machine, num_paths=10, max_steps_per_path=5)
    assert report["summary"]["total_paths_simulated"] == 10
    assert "total_errors" in report["summary"]
    assert report["bugs"] == []

def test_run_fuzz_test_with_dead_end():
    machine = {
        "id": "test",
        "initial": "a",
        "states": {
            "a": {"on": {"NEXT": "b"}},
            "b": {"on": {}} # dead end
        }
    }
    # Fuzzer finds dead ends as errors (or reports them)
    report = run_fuzz_test(machine, num_paths=10)
    assert report["summary"]["total_paths_simulated"] == 10
    # Dead ends should be detected
    assert len(report["bugs"]) > 0
    assert any(b["type"] == "dead_end_state" for b in report["bugs"])
