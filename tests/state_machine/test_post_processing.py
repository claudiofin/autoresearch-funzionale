"""Tests for state_machine/post_processing.py"""

import pytest
from state_machine.post_processing import (
    _get_states_for_processing,
    remove_toplevel_duplicates,
    complete_missing_branches,
    clean_unreachable_states,
    create_missing_target_states,
    validate_no_critical_patterns,
    fix_broken_transitions,
    remove_duplicate_states,
)


class TestGetStatesForProcessing:
    def test_flat_architecture_returns_root_states(self):
        machine = {
            "initial": "app_idle",
            "states": {
                "app_idle": {},
                "loading": {},
            },
        }
        result = _get_states_for_processing(machine)
        assert result == machine["states"]

    def test_parallel_architecture_returns_navigation_states(self):
        machine = {
            "type": "parallel",
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {},
                        "loading": {},
                    },
                },
                "active_workflows": {
                    "initial": "none",
                    "states": {"none": {}},
                },
            },
        }
        result = _get_states_for_processing(machine)
        assert result == machine["states"]["navigation"]["states"]

    def test_parallel_without_navigation_returns_root_states(self):
        machine = {
            "type": "parallel",
            "states": {
                "app_idle": {},
            },
        }
        result = _get_states_for_processing(machine)
        assert result == machine["states"]


class TestRemoveToplevelDuplicates:
    def test_removes_duplicate_at_root(self):
        machine = {
            "initial": "app_idle",
            "states": {
                "app_idle": {},
                "dashboard": {},  # duplicate
                "success": {
                    "states": {
                        "dashboard": {},  # original
                    },
                },
            },
        }
        result = remove_toplevel_duplicates(machine)
        assert "dashboard" not in result["states"]
        assert "dashboard" in result["states"]["success"]["states"]

    def test_no_duplicates(self):
        machine = {
            "initial": "app_idle",
            "states": {
                "app_idle": {},
                "loading": {},
                "success": {
                    "states": {
                        "dashboard": {},
                    },
                },
            },
        }
        result = remove_toplevel_duplicates(machine)
        assert "loading" in result["states"]

    def test_parallel_architecture(self):
        machine = {
            "type": "parallel",
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {},
                        "dashboard": {},  # duplicate
                        "success": {
                            "states": {
                                "dashboard": {},  # original
                            },
                        },
                    },
                },
                "active_workflows": {"initial": "none", "states": {"none": {}}},
            },
        }
        result = remove_toplevel_duplicates(machine)
        nav = result["states"]["navigation"]["states"]
        assert "dashboard" not in nav
        assert "dashboard" in nav["success"]["states"]


class TestCompleteMissingBranches:
    def _make_flat_machine(self):
        return {
            "initial": "app_idle",
            "states": {
                "app_idle": {"on": {}},
                "loading": {
                    "on": {
                        "ON_SUCCESS": {"target": "empty", "cond": "!hasData"},
                    },
                },
                "empty": {"on": {}},
                "success": {"on": {}},
            },
        }

    def test_adds_missing_positive_branch(self):
        machine = self._make_flat_machine()
        result = complete_missing_branches(machine)
        transitions = result["states"]["loading"]["on"]["ON_SUCCESS"]
        # Should now be a list with both branches
        assert isinstance(transitions, list)
        guards = [t.get("cond") for t in transitions if isinstance(t, dict)]
        assert "hasData" in guards
        assert "!hasData" in guards

    def test_adds_reauthenticate_to_session_expired(self):
        machine = {
            "initial": "app_idle",
            "states": {
                "app_idle": {"on": {}},
                "session_expired": {"on": {}},
            },
        }
        result = complete_missing_branches(machine)
        assert "REAUTHENTICATE" in result["states"]["session_expired"]["on"]
        assert result["states"]["session_expired"]["on"]["REAUTHENTICATE"] == "authenticating"

    def test_parallel_architecture(self):
        machine = {
            "type": "parallel",
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {"on": {}},
                        "loading": {
                            "on": {
                                "ON_SUCCESS": {"target": "empty", "cond": "!hasData"},
                            },
                        },
                        "empty": {"on": {}},
                        "success": {"on": {}},
                    },
                },
                "active_workflows": {"initial": "none", "states": {"none": {}}},
            },
        }
        result = complete_missing_branches(machine)
        nav = result["states"]["navigation"]["states"]
        transitions = nav["loading"]["on"]["ON_SUCCESS"]
        assert isinstance(transitions, list)


class TestCleanUnreachableStates:
    def test_removes_unreachable_state(self):
        machine = {
            "initial": "app_idle",
            "states": {
                "app_idle": {"on": {"START": "loading"}},
                "loading": {"on": {}},
                "orphan": {"on": {}},  # unreachable
            },
        }
        result = clean_unreachable_states(machine)
        assert "orphan" not in result["states"]
        assert "app_idle" in result["states"]
        assert "loading" in result["states"]

    def test_removes_xstate_keyword_states(self):
        machine = {
            "initial": "app_idle",
            "states": {
                "app_idle": {"on": {}},
                "initial": {"on": {}},  # XState keyword
                "states": {"on": {}},  # XState keyword
            },
        }
        result = clean_unreachable_states(machine)
        assert "initial" not in result["states"]
        assert "states" not in result["states"]

    def test_parallel_architecture_keeps_all_states(self):
        """For parallel architecture, all navigation states are kept (they're valid screens).
        Only XState keywords are removed."""
        machine = {
            "type": "parallel",
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {"on": {"START": "loading"}},
                        "loading": {"on": {}},
                        "orphan": {"on": {}},  # would be unreachable in flat, but kept in parallel
                        "initial": {"on": {}},  # XState keyword - should be removed
                    },
                },
                "active_workflows": {"initial": "none", "states": {"none": {}}},
            },
        }
        result = clean_unreachable_states(machine)
        nav = result["states"]["navigation"]["states"]
        # In parallel mode, all states are kept (including orphan)
        assert "orphan" in nav
        assert "app_idle" in nav
        assert "loading" in nav
        # Only XState keywords are removed
        assert "initial" not in nav


class TestCreateMissingTargetStates:
    def test_creates_missing_target_in_navigation(self):
        """For parallel architecture, missing targets are created in navigation branch."""
        machine = {
            "type": "parallel",
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {"on": {"START": "nonexistent"}},
                    },
                },
                "active_workflows": {"initial": "none", "states": {"none": {}}},
            },
        }
        result = create_missing_target_states(machine)
        nav = result["states"]["navigation"]["states"]
        assert "nonexistent" in nav

    def test_creates_nested_target_in_navigation(self):
        """Dot notation targets are created in the correct parent state."""
        machine = {
            "type": "parallel",
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {"on": {"START": "success.dashboard"}},
                        "success": {
                            "states": {},
                        },
                    },
                },
                "active_workflows": {"initial": "none", "states": {"none": {}}},
            },
        }
        result = create_missing_target_states(machine)
        nav = result["states"]["navigation"]["states"]
        assert "dashboard" in nav["success"]["states"]

    def test_flat_architecture_creates_at_root(self):
        """For flat architecture (no parallel), missing targets are created at root level."""
        machine = {
            "initial": "app_idle",
            "states": {
                "app_idle": {"on": {"START": "nonexistent"}},
            },
        }
        result = create_missing_target_states(machine)
        assert "nonexistent" in result["states"]


class TestValidateNoCriticalPatterns:
    def test_no_violations(self):
        machine = {
            "initial": "app_idle",
            "states": {
                "app_idle": {"entry": [], "on": {}},
                "success": {
                    "states": {
                        "dashboard": {"entry": [], "on": {}},
                    },
                },
            },
        }
        violations = validate_no_critical_patterns(machine)
        assert len(violations) == 0

    def test_rule_15_duplicate_states(self):
        machine = {
            "initial": "app_idle",
            "states": {
                "app_idle": {"entry": [], "on": {}},
                "success": {
                    "states": {
                        "dashboard": {"entry": [], "on": {}},
                        "success_dashboard": {"entry": [], "on": {}},  # duplicate
                    },
                },
            },
        }
        violations = validate_no_critical_patterns(machine)
        assert any("REGOLA 15" in v for v in violations)

    def test_rule_16_checkauth_in_app_idle(self):
        machine = {
            "initial": "app_idle",
            "states": {
                "app_idle": {"entry": ["checkAuth"], "on": {}},
            },
        }
        violations = validate_no_critical_patterns(machine)
        assert any("REGOLA 16" in v for v in violations)

    def test_rule_17_clustering_calculation_top_level(self):
        machine = {
            "initial": "app_idle",
            "states": {
                "app_idle": {"entry": [], "on": {}},
                "clustering_calculation": {"entry": [], "on": {}},  # should be sub-state
            },
        }
        violations = validate_no_critical_patterns(machine)
        assert any("REGOLA 17" in v for v in violations)

    def test_parallel_architecture(self):
        machine = {
            "type": "parallel",
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {"entry": ["checkAuth"], "on": {}},  # violation
                    },
                },
                "active_workflows": {"initial": "none", "states": {"none": {}}},
            },
        }
        violations = validate_no_critical_patterns(machine)
        assert any("REGOLA 16" in v for v in violations)


class TestFixBrokenTransitions:
    """Test fix_broken_transitions - redirects transitions to non-existent states."""

    def test_fixes_xstate_selector_syntax(self):
        """'#navigation.app_idle' should be fixed to 'app_idle'."""
        machine = {
            "type": "parallel",
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {"on": {}},
                        "loading": {"on": {"CANCEL": "#navigation.app_idle"}},
                    },
                },
                "active_workflows": {"initial": "none", "states": {"none": {}}},
            },
        }
        result = fix_broken_transitions(machine)
        nav = result["states"]["navigation"]["states"]
        # CANCEL should be redirected to app_idle
        assert nav["loading"]["on"]["CANCEL"] == "app_idle"

    def test_fixes_relative_path_to_nonexistent(self):
        """'.none.error' should be fixed based on event type."""
        machine = {
            "type": "parallel",
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {"on": {}},
                        "loading": {"on": {"RETRY": ".none.error"}},
                    },
                },
                "active_workflows": {"initial": "none", "states": {"none": {}}},
            },
        }
        result = fix_broken_transitions(machine)
        nav = result["states"]["navigation"]["states"]
        # RETRY should be redirected to loading
        assert nav["loading"]["on"]["RETRY"] == "loading"

    def test_fixes_bare_navigation_reference(self):
        """'navigation' (bare) should be fixed based on event type."""
        machine = {
            "type": "parallel",
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {"on": {}},
                        "authenticating": {"on": {}},  # must exist for fallback
                        "ready": {"on": {"START_APP": "navigation"}},
                    },
                },
                "active_workflows": {"initial": "none", "states": {"none": {}}},
            },
        }
        result = fix_broken_transitions(machine)
        nav = result["states"]["navigation"]["states"]
        # START_APP should be redirected to authenticating (since it exists)
        assert nav["ready"]["on"]["START_APP"] == "authenticating"

    def test_preserves_valid_transitions(self):
        """Valid transitions should not be modified."""
        machine = {
            "type": "parallel",
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {"on": {"START": "loading"}},
                        "loading": {"on": {"DATA_LOADED": "ready"}},
                        "ready": {"on": {}},
                    },
                },
                "active_workflows": {"initial": "none", "states": {"none": {}}},
            },
        }
        result = fix_broken_transitions(machine)
        nav = result["states"]["navigation"]["states"]
        assert nav["app_idle"]["on"]["START"] == "loading"
        assert nav["loading"]["on"]["DATA_LOADED"] == "ready"

    def test_handles_dict_target(self):
        """Dict-style targets should also be fixed."""
        machine = {
            "type": "parallel",
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {"on": {}},
                        "loading": {"on": {"CANCEL": {"target": "#navigation.app_idle"}}},
                    },
                },
                "active_workflows": {"initial": "none", "states": {"none": {}}},
            },
        }
        result = fix_broken_transitions(machine)
        nav = result["states"]["navigation"]["states"]
        assert nav["loading"]["on"]["CANCEL"]["target"] == "app_idle"

    def test_handles_list_targets(self):
        """List-style targets should also be fixed."""
        machine = {
            "type": "parallel",
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {"on": {}},
                        "loading": {"on": {"CANCEL": [{"target": "#navigation.app_idle"}]}},
                    },
                },
                "active_workflows": {"initial": "none", "states": {"none": {}}},
            },
        }
        result = fix_broken_transitions(machine)
        nav = result["states"]["navigation"]["states"]
        assert nav["loading"]["on"]["CANCEL"][0]["target"] == "app_idle"

    def test_flat_architecture(self):
        """Should work with flat (non-parallel) architecture too."""
        machine = {
            "initial": "app_idle",
            "states": {
                "app_idle": {"on": {}},
                "loading": {"on": {"CANCEL": "#navigation.app_idle"}},
            },
        }
        result = fix_broken_transitions(machine)
        assert result["states"]["loading"]["on"]["CANCEL"] == "app_idle"


class TestRemoveDuplicateStates:
    """Test remove_duplicate_states - removes states with same name at different paths."""

    def test_removes_nested_duplicate(self):
        """Duplicate 'authenticating' at different paths should be removed."""
        machine = {
            "type": "parallel",
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {"on": {}},
                        "auth_guard": {
                            "states": {
                                "auth_guard_invalid": {
                                    "states": {
                                        "authenticating": {"on": {}},  # first occurrence
                                    },
                                },
                            },
                        },
                        "session_expired": {
                            "states": {
                                "session_expired_reauth": {
                                    "states": {
                                        "authenticating": {"on": {}},  # duplicate
                                    },
                                },
                            },
                        },
                    },
                },
                "active_workflows": {"initial": "none", "states": {"none": {}}},
            },
        }
        result = remove_duplicate_states(machine)
        nav = result["states"]["navigation"]["states"]
        # First occurrence should be kept
        assert "authenticating" in nav["auth_guard"]["states"]["auth_guard_invalid"]["states"]
        # Duplicate should be removed
        assert "authenticating" not in nav["session_expired"]["states"]["session_expired_reauth"]["states"]

    def test_removes_top_level_duplicate(self):
        """Duplicate at top level should be removed."""
        machine = {
            "type": "parallel",
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {"on": {}},
                        "creating": {"on": {}},  # first occurrence
                        "login": {
                            "states": {
                                "login_success": {
                                    "states": {
                                        "creating": {"on": {}},  # duplicate
                                    },
                                },
                            },
                        },
                    },
                },
                "active_workflows": {"initial": "none", "states": {"none": {}}},
            },
        }
        result = remove_duplicate_states(machine)
        nav = result["states"]["navigation"]["states"]
        # First occurrence (top-level) should be kept
        assert "creating" in nav
        # Duplicate should be removed
        assert "creating" not in nav["login"]["states"]["login_success"]["states"]

    def test_no_duplicates(self):
        """Machine without duplicates should be unchanged."""
        machine = {
            "type": "parallel",
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {"on": {}},
                        "loading": {"on": {}},
                        "ready": {"on": {}},
                    },
                },
                "active_workflows": {"initial": "none", "states": {"none": {}}},
            },
        }
        result = remove_duplicate_states(machine)
        nav = result["states"]["navigation"]["states"]
        assert "app_idle" in nav
        assert "loading" in nav
        assert "ready" in nav

    def test_flat_architecture(self):
        """Should work with flat (non-parallel) architecture too."""
        machine = {
            "initial": "app_idle",
            "states": {
                "app_idle": {"on": {}},
                "loading": {"on": {}},
                "success": {
                    "states": {
                        "loading": {"on": {}},  # duplicate
                    },
                },
            },
        }
        result = remove_duplicate_states(machine)
        # First occurrence (top-level) should be kept
        assert "loading" in result["states"]
        # Duplicate should be removed
        assert "loading" not in result["states"]["success"]["states"]
