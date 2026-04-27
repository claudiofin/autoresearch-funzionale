"""Tests for FIX 10-12: enforce_compound_states, inject_auth_flow, apply_error_routing_matrix."""

import pytest
from state_machine.cleanup import (
    enforce_compound_states, inject_auth_flow, apply_error_routing_matrix,
)


class TestEnforceCompoundStates:
    """Test that flat screen states are converted to compound states."""
    
    def test_flat_dashboard_with_transitions_not_wrapped(self):
        """A flat 'dashboard' state WITH navigation transitions should NOT be wrapped.
        
        FIX: States that already have navigation transitions (like OPEN_CATALOG)
        have meaningful navigation logic. Wrapping them moves those transitions
        into 'ready' sub-state, but 'loading' (the initial) has no way to reach
        'ready', making everything unreachable.
        """
        machine = {
            "id": "test",
            "initial": "navigation",
            "states": {
                "navigation": {
                    "initial": "dashboard",
                    "states": {
                        "dashboard": {
                            "id": "navigation.dashboard",
                            "entry": ["showDashboard"],
                            "on": {"OPEN_CATALOG": "navigation.catalog"},
                        }
                    }
                }
            }
        }
        
        result = enforce_compound_states(machine)
        dashboard = result["states"]["navigation"]["states"]["dashboard"]
        
        # Should NOT be wrapped — it already has navigation transitions
        assert "states" not in dashboard
        assert dashboard["on"]["OPEN_CATALOG"] == "navigation.catalog"
    
    def test_flat_dashboard_without_transitions_becomes_compound(self):
        """A flat 'dashboard' state WITHOUT navigation transitions should be wrapped."""
        machine = {
            "id": "test",
            "initial": "navigation",
            "states": {
                "navigation": {
                    "initial": "dashboard",
                    "states": {
                        "dashboard": {
                            "id": "navigation.dashboard",
                            "entry": ["showDashboard"],
                        }
                    }
                }
            }
        }
        
        result = enforce_compound_states(machine)
        dashboard = result["states"]["navigation"]["states"]["dashboard"]
        
        assert "states" in dashboard
        assert "loading" in dashboard["states"]
        assert "ready" in dashboard["states"]
        assert "error" in dashboard["states"]
        assert dashboard["initial"] == "loading"
    
    def test_ready_preserves_original_entry(self):
        """The 'ready' sub-state should contain the original entry actions.
        
        Only applies to states WITHOUT navigation transitions (they get wrapped).
        """
        machine = {
            "id": "test",
            "initial": "navigation",
            "states": {
                "navigation": {
                    "initial": "catalog",
                    "states": {
                        "catalog": {
                            "id": "navigation.catalog",
                            "entry": ["fetchCatalog", "showCatalog"],
                            "exit": ["hideCatalog"],
                            # No navigation transitions — will be wrapped
                        }
                    }
                }
            }
        }
        
        result = enforce_compound_states(machine)
        ready = result["states"]["navigation"]["states"]["catalog"]["states"]["ready"]
        
        assert "fetchCatalog" in ready["entry"]
        assert "showCatalog" in ready["entry"]
        assert "hideCatalog" in ready["exit"]
    
    def test_loading_has_data_loaded_transition(self):
        """The 'loading' sub-state should have DATA_LOADED → .ready."""
        machine = {
            "id": "test",
            "initial": "navigation",
            "states": {
                "navigation": {
                    "initial": "offers",
                    "states": {
                        "offers": {
                            "id": "navigation.offers",
                            "entry": ["showOffers"],
                        }
                    }
                }
            }
        }
        
        result = enforce_compound_states(machine)
        loading = result["states"]["navigation"]["states"]["offers"]["states"]["loading"]
        
        assert loading["on"]["DATA_LOADED"] == ".ready"
        assert loading["on"]["LOAD_FAILED"] == ".error"
        assert loading["on"]["TIMEOUT"] == ".error"
    
    def test_error_has_retry_and_cancel(self):
        """The 'error' sub-state should have RETRY → .loading and CANCEL."""
        machine = {
            "id": "test",
            "initial": "navigation",
            "states": {
                "navigation": {
                    "initial": "alerts",
                    "states": {
                        "alerts": {
                            "id": "navigation.alerts",
                            "entry": ["showAlerts"],
                        }
                    }
                }
            }
        }
        
        result = enforce_compound_states(machine)
        error = result["states"]["navigation"]["states"]["alerts"]["states"]["error"]
        
        assert error["on"]["RETRY"] == ".loading"
        assert "CANCEL" in error["on"]
    
    def test_already_compound_not_wrapped(self):
        """States that already have sub-states should not be double-wrapped."""
        machine = {
            "id": "test",
            "initial": "navigation",
            "states": {
                "navigation": {
                    "initial": "dashboard",
                    "states": {
                        "dashboard": {
                            "id": "navigation.dashboard",
                            "initial": "loading",
                            "states": {
                                "loading": {"on": {"DATA_LOADED": ".ready"}},
                                "ready": {"entry": ["showDashboard"]},
                                "error": {"on": {"RETRY": ".loading"}},
                            }
                        }
                    }
                }
            }
        }
        
        result = enforce_compound_states(machine)
        dashboard = result["states"]["navigation"]["states"]["dashboard"]
        
        # Should still have the same structure, not double-wrapped
        assert "loading" in dashboard["states"]
        assert "ready" in dashboard["states"]
        assert "error" in dashboard["states"]
        # The 'ready' should still have the original entry, not a wrapper
        assert dashboard["states"]["ready"]["entry"] == ["showDashboard"]
    
    def test_non_screen_flat_state_not_wrapped(self):
        """Flat states that are not screens (no entry actions) should not be wrapped.
        
        FIX: States with navigation transitions (START_APP, GO_BACK) should NOT be
        wrapped even if they're known screen names, because wrapping would make
        their transitions unreachable (loading → ready path doesn't exist).
        """
        machine = {
            "id": "test",
            "initial": "navigation",
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {
                            "id": "navigation.app_idle",
                            "on": {"START_APP": "navigation.auth_guard"},
                        },
                        "some_orphan": {
                            # No entry actions, not a known screen — should not be wrapped
                            "on": {"GO_BACK": "navigation.app_idle"},
                        }
                    }
                }
            }
        }
        
        result = enforce_compound_states(machine)
        nav_states = result["states"]["navigation"]["states"]
        
        # app_idle has START_APP transition — should NOT be wrapped
        assert "states" not in nav_states["app_idle"]
        assert nav_states["app_idle"]["on"]["START_APP"] == "navigation.auth_guard"
        
        # some_orphan is not a known screen and has no entry — should NOT be wrapped
        assert "states" not in nav_states.get("some_orphan", {})


class TestInjectAuthFlow:
    """Test that auth flow states are injected when missing."""
    
    def test_injects_auth_guard(self):
        """auth_guard should be injected into navigation if missing."""
        machine = {
            "id": "test",
            "initial": "navigation",
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {"on": {"START_APP": "navigation.dashboard"}},
                        "dashboard": {"entry": ["showDashboard"]},
                    }
                }
            }
        }
        
        result = inject_auth_flow(machine)
        auth_guard = result["states"]["navigation"]["states"]["auth_guard"]
        
        assert auth_guard is not None
        assert "states" in auth_guard
        assert "checking" in auth_guard["states"]
    
    def test_auth_guard_has_success_and_failed(self):
        """auth_guard.checking should have AUTH_SUCCESS and AUTH_FAILED transitions."""
        machine = {
            "id": "test",
            "initial": "navigation",
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {"on": {"START_APP": "navigation.dashboard"}},
                        "dashboard": {"entry": ["showDashboard"]},
                    }
                }
            }
        }
        
        result = inject_auth_flow(machine)
        checking = result["states"]["navigation"]["states"]["auth_guard"]["states"]["checking"]
        
        assert checking["on"]["AUTH_SUCCESS"] == "navigation.dashboard"
        assert checking["on"]["AUTH_FAILED"] == "navigation.login"
    
    def test_injects_login(self):
        """login should be injected into navigation if missing."""
        machine = {
            "id": "test",
            "initial": "navigation",
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {"on": {"START_APP": "navigation.dashboard"}},
                        "dashboard": {"entry": ["showDashboard"]},
                    }
                }
            }
        }
        
        result = inject_auth_flow(machine)
        login = result["states"]["navigation"]["states"]["login"]
        
        assert login is not None
        assert "states" in login
        assert "form" in login["states"]
    
    def test_login_has_success_and_failed(self):
        """login.form should have LOGIN_SUCCESS and LOGIN_FAILED transitions."""
        machine = {
            "id": "test",
            "initial": "navigation",
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {"on": {"START_APP": "navigation.dashboard"}},
                        "dashboard": {"entry": ["showDashboard"]},
                    }
                }
            }
        }
        
        result = inject_auth_flow(machine)
        form = result["states"]["navigation"]["states"]["login"]["states"]["form"]
        
        assert form["on"]["LOGIN_SUCCESS"] == "navigation.dashboard"
        assert form["on"]["LOGIN_FAILED"] == ".failure_retry"
    
    def test_injects_session_expired(self):
        """session_expired should be injected into navigation if missing."""
        machine = {
            "id": "test",
            "initial": "navigation",
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {"on": {"START_APP": "navigation.dashboard"}},
                        "dashboard": {"entry": ["showDashboard"]},
                    }
                }
            }
        }
        
        result = inject_auth_flow(machine)
        session_expired = result["states"]["navigation"]["states"]["session_expired"]
        
        assert session_expired is not None
        assert session_expired["on"]["REAUTHENTICATE"] == "navigation.login"
        assert session_expired["on"]["CANCEL"] == "navigation.app_idle"
    
    def test_does_not_overwrite_existing_auth_guard(self):
        """If auth_guard already exists, it should not be overwritten."""
        machine = {
            "id": "test",
            "initial": "navigation",
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {"on": {"START_APP": "navigation.dashboard"}},
                        "dashboard": {"entry": ["showDashboard"]},
                        "auth_guard": {
                            "id": "navigation.auth_guard",
                            "initial": "custom_checking",
                            "states": {
                                "custom_checking": {
                                    "on": {"AUTH_SUCCESS": "navigation.dashboard"},
                                }
                            }
                        }
                    }
                }
            }
        }
        
        result = inject_auth_flow(machine)
        auth_guard = result["states"]["navigation"]["states"]["auth_guard"]
        
        # Should preserve the original structure
        assert "custom_checking" in auth_guard["states"]
        assert "checking" not in auth_guard["states"]
    
    def test_connects_app_idle_to_auth_guard(self):
        """app_idle should have START_APP → auth_guard after injection (only if missing)."""
        machine = {
            "id": "test",
            "initial": "navigation",
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {"on": {}},  # No START_APP — should be added
                        "dashboard": {"entry": ["showDashboard"]},
                    }
                }
            }
        }
        
        result = inject_auth_flow(machine)
        app_idle = result["states"]["navigation"]["states"]["app_idle"]
        
        # START_APP should be added pointing to auth_guard
        assert app_idle["on"]["START_APP"] == "navigation.auth_guard"
    
    def test_preserves_existing_start_app(self):
        """If app_idle already has START_APP to a non-self target, it should not be overwritten."""
        machine = {
            "id": "test",
            "initial": "navigation",
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {"on": {"START_APP": "navigation.dashboard"}},
                        "dashboard": {"entry": ["showDashboard"]},
                    }
                }
            }
        }
        
        result = inject_auth_flow(machine)
        app_idle = result["states"]["navigation"]["states"]["app_idle"]
        
        # START_APP should be preserved (not a self-loop)
        assert app_idle["on"]["START_APP"] == "navigation.dashboard"
    
    def test_redirects_self_loop_to_auth_guard(self):
        """If app_idle has START_APP pointing to itself, redirect to auth_guard."""
        machine = {
            "id": "test",
            "initial": "navigation",
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {"on": {"START_APP": "navigation.app_idle"}},
                        "dashboard": {"entry": ["showDashboard"]},
                    }
                }
            }
        }
        
        result = inject_auth_flow(machine)
        app_idle = result["states"]["navigation"]["states"]["app_idle"]
        
        # Self-loop should be redirected to auth_guard
        assert app_idle["on"]["START_APP"] == "navigation.auth_guard"


class TestApplyErrorRoutingMatrix:
    """Test that error routing matrix is applied correctly."""
    
    def test_creates_global_app_error(self):
        """navigation.app_error should be created if missing."""
        machine = {
            "id": "test",
            "initial": "navigation",
            "states": {
                "navigation": {
                    "initial": "app_idle",
                    "states": {
                        "app_idle": {"on": {"START_APP": "navigation.dashboard"}},
                        "dashboard": {
                            "initial": "loading",
                            "states": {
                                "loading": {"on": {"LOAD_FAILED": ".error"}},
                                "error": {"on": {"RETRY": ".loading"}},
                            }
                        },
                    }
                }
            }
        }
        
        result = apply_error_routing_matrix(machine)
        app_error = result["states"]["navigation"]["states"]["app_error"]
        
        assert app_error is not None
        assert "showGlobalError" in app_error["entry"]
        assert app_error["on"]["RETRY"] == "navigation.app_idle"
    
    def test_error_state_has_retry_to_loading(self):
        """Error sub-states should have RETRY → .loading."""
        machine = {
            "id": "test",
            "initial": "navigation",
            "states": {
                "navigation": {
                    "initial": "dashboard",
                    "states": {
                        "dashboard": {
                            "initial": "loading",
                            "states": {
                                "loading": {"on": {"LOAD_FAILED": ".error"}},
                                "error": {"on": {}},  # No RETRY — should be added
                            }
                        },
                    }
                }
            }
        }
        
        result = apply_error_routing_matrix(machine)
        error = result["states"]["navigation"]["states"]["dashboard"]["states"]["error"]
        
        assert error["on"]["RETRY"] == ".loading"
    
    def test_error_state_has_cancel_to_app_idle(self):
        """Error sub-states should have CANCEL → navigation.app_idle."""
        machine = {
            "id": "test",
            "initial": "navigation",
            "states": {
                "navigation": {
                    "initial": "dashboard",
                    "states": {
                        "dashboard": {
                            "initial": "loading",
                            "states": {
                                "loading": {"on": {"LOAD_FAILED": ".error"}},
                                "error": {"on": {"RETRY": ".loading"}},  # No CANCEL
                            }
                        },
                    }
                }
            }
        }
        
        result = apply_error_routing_matrix(machine)
        error = result["states"]["navigation"]["states"]["dashboard"]["states"]["error"]
        
        assert "CANCEL" in error["on"]
    
    def test_preserves_existing_error_transitions(self):
        """Existing error transitions should not be overwritten."""
        machine = {
            "id": "test",
            "initial": "navigation",
            "states": {
                "navigation": {
                    "initial": "dashboard",
                    "states": {
                        "dashboard": {
                            "initial": "loading",
                            "states": {
                                "loading": {"on": {"LOAD_FAILED": ".error"}},
                                "error": {
                                    "on": {
                                        "RETRY": ".loading",
                                        "CANCEL": "navigation.app_idle",
                                        "GO_HOME": "navigation.app_idle",
                                    }
                                },
                            }
                        },
                    }
                }
            }
        }
        
        result = apply_error_routing_matrix(machine)
        error = result["states"]["navigation"]["states"]["dashboard"]["states"]["error"]
        
        # Should preserve all original transitions
        assert error["on"]["RETRY"] == ".loading"
        assert error["on"]["CANCEL"] == "navigation.app_idle"
        assert error["on"]["GO_HOME"] == "navigation.app_idle"
    
    def test_nested_error_states_get_routing(self):
        """Error states in nested compound states should also get routing."""
        machine = {
            "id": "test",
            "initial": "navigation",
            "states": {
                "navigation": {
                    "initial": "catalog",
                    "states": {
                        "catalog": {
                            "initial": "loading",
                            "states": {
                                "loading": {"on": {"LOAD_FAILED": ".error"}},
                                "error": {"on": {}},  # No RETRY
                                "ready": {"entry": ["showCatalog"]},
                            }
                        },
                        "offers": {
                            "initial": "loading",
                            "states": {
                                "loading": {"on": {"LOAD_FAILED": ".error"}},
                                "error": {"on": {}},  # No RETRY
                                "ready": {"entry": ["showOffers"]},
                            }
                        },
                    }
                }
            }
        }
        
        result = apply_error_routing_matrix(machine)
        
        catalog_error = result["states"]["navigation"]["states"]["catalog"]["states"]["error"]
        offers_error = result["states"]["navigation"]["states"]["offers"]["states"]["error"]
        
        assert catalog_error["on"]["RETRY"] == ".loading"
        assert offers_error["on"]["RETRY"] == ".loading"