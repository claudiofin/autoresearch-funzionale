"""State machine builder — coordinator module.

This module orchestrates the compilation pipeline by importing functions
from specialized sub-modules. The actual logic lives in:
- constants.py: Default configuration
- traversal.py: BFS, path collection, target extraction
- normalization.py: Naming fixes, branch placement
- injection.py: Error handlers, global exit, auto-inject sub_states
- cleanup.py: Dead state removal, deduplication
- target_resolution.py: Relative/caret target resolution, placeholders
- context_awareness.py: Guards, emergency exits
- transitions.py: Adding transitions to machines
- workflows.py: Workflow compound state building

Usage:
    from state_machine.builder import generate_base_machine, build_and_compile
    
    base = generate_base_machine()
    machine = build_and_compile(base, transitions, workflows)
"""

import json

from state_machine.constants import (
    DEFAULT_STATE_NAMES, DEFAULT_BRANCH_NAMES, DEFAULT_ACTION_NAMES,
    DEFAULT_GUARD_NAMES, DEFAULT_EVENT_NAMES, DEFAULT_EMERGENCY_EVENTS,
    XSTATE_ACTION_MAP,
)
from state_machine.traversal import (
    extract_target_string, extract_target_names,
    collect_all_state_paths, bfs_reachable,
    resolve_canonical_target, resolve_simple_target,
)
from state_machine.normalization import (
    normalize_machine, apply_branch_placement, apply_universal_normalization,
    _resolve_state_name, _resolve_branch_name, _resolve_action_name,
    _normalize_state_name, _normalize_path,
)
from state_machine.injection import (
    apply_error_injection, apply_global_exit, auto_inject_sub_states,
    apply_id_injection, apply_initial_enforcer, apply_placeholder_flattening,
    _find_exit_target_for_state, _infer_sub_state_name,
    _find_emergency_exit_target,
)
from state_machine.cleanup import (
    apply_dead_state_cleanup, apply_specificity_dedup, apply_dead_end_pruning,
    apply_phantom_state_cleanup, apply_workflow_dedup,
    remove_empty_states_dict, fix_relative_transitions,
    fix_start_app_transitions, connect_unreachable_states,
    fix_initial_state, connect_sibling_substates,
)
from state_machine.target_resolution import (
    apply_target_resolution, apply_target_crosscheck,
    _resolve_relative_target, _resolve_caret_target,
    _fix_workflows_none_target, _fix_nonexistent_targets,
    _ensure_target_exists, _create_placeholder_state,
)
from state_machine.context_awareness import (
    apply_context_awareness,
    _is_in_workflow_branch, _find_session_expired_target, _find_error_target,
)
from state_machine.transitions import (
    add_transitions, add_transitions_to_branch,
    _format_xstate_actions,
)
from state_machine.workflows import (
    build_workflow_compound_state, add_workflows_to_machine,
)


# Re-export for backward compatibility
__all__ = [
    # Constants
    "DEFAULT_STATE_NAMES", "DEFAULT_BRANCH_NAMES", "DEFAULT_ACTION_NAMES",
    "DEFAULT_GUARD_NAMES", "DEFAULT_EVENT_NAMES", "DEFAULT_EMERGENCY_EVENTS",
    "XSTATE_ACTION_MAP",
    # Traversal
    "extract_target_string", "extract_target_names",
    "collect_all_state_paths", "bfs_reachable",
    "resolve_canonical_target", "resolve_simple_target",
    # Normalization
    "normalize_machine", "apply_branch_placement", "apply_universal_normalization",
    # Injection
    "apply_error_injection", "apply_global_exit", "auto_inject_sub_states",
    # Cleanup
    "apply_dead_state_cleanup", "apply_specificity_dedup",
    # Target resolution
    "apply_target_resolution",
    # Context awareness
    "apply_context_awareness",
    # Transitions
    "add_transitions", "add_transitions_to_branch",
    # Workflows
    "build_workflow_compound_state", "add_workflows_to_machine",
    # Main API
    "generate_base_machine", "build_state_config",
    "compile_machine", "build_and_compile", "deduplicate_machine",
    # ID Injection
    "apply_id_injection",
    # Initial Enforcer
    "apply_initial_enforcer",
    # Dead-end Pruning
    "apply_dead_end_pruning",
]


def get_machine_type(machine: dict) -> str:
    """Get the type of a state machine.
    
    Args:
        machine: State machine dict
    
    Returns:
        Machine type string ('parallel', 'hierarchical', 'flat', etc.)
    """
    return machine.get("type", "flat")


def generate_base_machine(use_parallel: bool = True, state_names: dict = None, branch_names: dict = None) -> dict:
    """Generate an empty base state machine with proper parallel structure.
    
    STRUCTURAL: Uses configurable state and branch names instead of hardcoded values.
    This makes the builder universal — works for e-commerce, IoT, social, gaming, etc.
    
    ANTI-FRATTALE: The initial state (app_initial/app_idle) is created with a 
    default START_APP transition to prevent the "Frozen State" problem where
    the fuzzer enters the app but cannot navigate anywhere.
    
    Args:
        use_parallel: If True, creates parallel states architecture
        state_names: Optional dict overriding DEFAULT_STATE_NAMES (e.g., {"initial": "home"})
        branch_names: Optional dict overriding DEFAULT_BRANCH_NAMES (e.g., {"navigation": "ui"})
    
    Returns:
        Base machine dict
    """
    initial_name = _resolve_state_name("initial", state_names)
    workflow_none = _resolve_state_name("workflow_none", state_names)
    nav_branch = _resolve_branch_name("navigation", branch_names)
    wf_branch = _resolve_branch_name("workflows", branch_names)
    hide_workflow = _resolve_action_name("hide_workflow")
    
    if use_parallel:
        return {
            "id": "appFlow",
            "type": "parallel",
            "initial": nav_branch,  # FIX: Root-level initial for parallel machines (fuzzer compatibility)
            "context": {
                "user": None,
                "errors": [],
                "retryCount": 0,
                "previousState": None
            },
            "states": {
                nav_branch: {
                    "id": "nav_branch",
                    "initial": initial_name,
                    "on": {},
                    "states": {
                        # BOOTSTRAP: Initial state with default transition to prevent frozen state
                        initial_name: {
                            "id": f"{nav_branch}.{initial_name}",
                            "entry": ["initializeApp"],
                            "on": {
                                "START_APP": ".app_loading"  # Default bootstrap transition
                            }
                        }
                    }
                },
                wf_branch: {
                    "id": "wf_branch",
                    "initial": workflow_none,
                    "on": {},
                    "states": {
                        workflow_none: {
                            "entry": [hide_workflow],
                            "exit": [],
                            "on": {}
                        }
                    }
                }
            }
        }
    else:
        return {
            "id": "appFlow",
            "initial": initial_name,
            "context": {
                "user": None,
                "errors": [],
                "retryCount": 0,
                "previousState": None
            },
            "states": {
                initial_name: {
                    "id": initial_name,
                    "entry": ["initializeApp"],
                    "on": {
                        "START_APP": "app_loading"
                    }
                }
            }
        }


def build_state_config(state: dict) -> dict:
    """Build XState state config from LLM state dict.
    
    Supports hierarchical states with auto-generated navigation events.
    Auto-generates loading/ready/error sub_states for states that need them.
    
    Args:
        state: LLM-generated state dict
    
    Returns:
        XState-compatible state config
    """
    state_name = state.get("name", "unknown")
    
    config = {
        "entry": state.get("entry_actions", []),
        "exit": state.get("exit_actions", []),
        "on": {}
    }
    
    sub_states = state.get("sub_states", [])
    if sub_states:
        initial_sub = state.get("initial_sub_state") or sub_states[0]
        if isinstance(initial_sub, dict):
            initial_sub = initial_sub.get("name", "")
        
        config["initial"] = initial_sub
        config["states"] = {}
        
        for sub in sub_states:
            sub_name = sub if isinstance(sub, str) else sub.get("name", "")
            if "." in sub_name:
                sub_name = sub_name.split(".")[-1]
            
            sub_entry = [] if isinstance(sub, str) else sub.get("entry_actions", [])
            sub_exit = [] if isinstance(sub, str) else sub.get("exit_actions", [])
            config["states"][sub_name] = {
                "entry": sub_entry,
                "exit": sub_exit,
                "on": {}
            }
        
        # Auto-generate NAVIGATE events between sub-states
        for sub in sub_states:
            sub_name = sub if isinstance(sub, str) else sub.get("name", "")
            if "." in sub_name:
                sub_name = sub_name.split(".")[-1]
            nav_event = f"NAVIGATE_{sub_name.upper()}"
            for other_sub in sub_states:
                other_name = other_sub if isinstance(other_sub, str) else other_sub.get("name", "")
                if "." in other_name:
                    other_name = other_name.split(".")[-1]
                if other_name != sub_name:
                    config["states"][other_name]["on"][nav_event] = f".{sub_name}"
    else:
        # Auto-generate sub_states if this state needs them
        auto_sub = _auto_generate_sub_states(state_name, state)
        if auto_sub:
            config["initial"] = auto_sub["initial"]
            config["states"] = auto_sub["states"]
    
    return config


def _auto_generate_sub_states(state_name: str, state: dict) -> dict:
    """Auto-generate sub_states (loading, ready, error) for states that need them.
    
    A state needs sub_states if:
    - It has entry actions (indicates it's a real screen/workflow)
    - It has API-like events (needs error handling)
    - It's a workflow step (has cross_page_events)
    
    Args:
        state_name: Name of the parent state
        state: LLM-generated state dict
    
    Returns:
        Dict with 'initial' and 'states' for sub-states
    """
    entry_actions = state.get("entry_actions", [])
    exit_actions = state.get("exit_actions", [])
    transitions = state.get("transitions", [])
    
    needs_sub_states = (
        len(entry_actions) > 0 or
        len(transitions) > 0 or
        state.get("sub_states", [])
    )
    
    if not needs_sub_states:
        return {}
    
    if state.get("sub_states"):
        return {}
    
    sub_states = {}
    
    sub_states["loading"] = {
        "entry": ["showLoading", f"fetch{state_name.title()}"],
        "exit": ["hideLoading"],
        "on": {
            "DATA_LOADED": ".ready",
            "LOAD_FAILED": ".error",
            "TIMEOUT": ".error"
        }
    }
    
    ready_entry = list(entry_actions) if entry_actions else [f"show{state_name.title()}"]
    ready_exit = list(exit_actions) if exit_actions else [f"hide{state_name.title()}"]
    sub_states["ready"] = {
        "entry": ready_entry,
        "exit": ready_exit,
        "on": {}
    }
    
    sub_states["error"] = {
        "entry": ["logError", "showErrorBanner"],
        "exit": ["hideErrorBanner"],
        "on": {
            "RETRY": ".loading",
            "CANCEL": f"#{_find_exit_target_for_state(state_name)}"
        }
    }
    
    return {
        "initial": "loading",
        "states": sub_states
    }


def compile_machine(machine: dict, max_iterations: int = 1) -> dict:
    """Apply all Pattern Compiler rules to a state machine.
    
    This is the main entry point. Feed it any LLM-generated state machine
    and it will apply structural laws to make it valid.
    
    Order of operations:
    1. Branch Placement (Rule 6: move orphans to correct branch)
    2. Normalize (fix naming issues)
    3. Auto-inject sub_states (loading/ready/error)
    4. Specificity Dedup (remove duplicates)
    5. Error Injection (add error handlers)
    6. Global Exit (add exit transitions)
    7. ID Injection (inject explicit 'id' = full path for '#' references)
    8. Dead-end Pruning (add CANCEL to states with no transitions)
    9. Dead State Cleanup (remove unreachable)
    10. Target Resolution (fix relative targets, caret syntax, create placeholders)
    11. Context Awareness (add guards to retry, emergency exits to workflows)
    12. Target Cross-Check (validate ALL targets exist, re-route ghosts)
    13. Placeholder Flattening (collapse wrapper states with no logic) ← LAMA AFFILATA!
    14. Initial Enforcer (ensure EVERY compound state has valid 'initial') ← FINAL!
    
    SAFETY: Runs in a loop with max_iterations to handle cases where later steps
    (like target resolution) create new states that need earlier processing.
    The loop terminates early if the machine stabilizes (no changes between iterations).
    
    Args:
        machine: Raw LLM-generated state machine
        max_iterations: Maximum number of full compilation passes (default: 3)
    
    Returns:
        Compiled, structurally valid state machine
    """
    # FIX: Single iteration to prevent fractal nesting of auto-generated states
    # Each iteration re-processes states created in previous iteration, causing exponential growth
    max_iterations = 1
    
    # DEBUG: Track state count through compilation
    def _count_states(m):
        return len(m.get("states", {}))
    
    for iteration in range(max_iterations):
        try:
            before = json.dumps(machine, sort_keys=True, default=str)
        except (TypeError, ValueError):
            before = str(id(machine))
        
        print(f"  🔍 [DEBUG] compile_machine: starting with {_count_states(machine)} states")
        
        machine = apply_branch_placement(machine)
        print(f"  🔍 [DEBUG] after apply_branch_placement: {_count_states(machine)} states")
        
        machine = normalize_machine(machine)
        print(f"  🔍 [DEBUG] after normalize_machine: {_count_states(machine)} states")
        
        machine = apply_universal_normalization(machine)  # LAW OF ORTHOGRAPHY: universal name corrector
        print(f"  🔍 [DEBUG] after apply_universal_normalization: {_count_states(machine)} states")
        
        machine = auto_inject_sub_states(machine)
        print(f"  🔍 [DEBUG] after auto_inject_sub_states: {_count_states(machine)} states")
        
        machine = remove_empty_states_dict(machine)  # FIX: Remove empty 'states: {}' → INVALID_COMPOUND
        print(f"  🔍 [DEBUG] after remove_empty_states_dict: {_count_states(machine)} states")
        
        machine = apply_specificity_dedup(machine)
        print(f"  🔍 [DEBUG] after apply_specificity_dedup: {_count_states(machine)} states")
        
        machine = apply_error_injection(machine)
        print(f"  🔍 [DEBUG] after apply_error_injection: {_count_states(machine)} states")
        
        machine = apply_global_exit(machine)
        print(f"  🔍 [DEBUG] after apply_global_exit: {_count_states(machine)} states")
        
        machine = apply_id_injection(machine)  # CRITICAL: '#' references need explicit IDs
        print(f"  🔍 [DEBUG] after apply_id_injection: {_count_states(machine)} states")
        
        machine = apply_dead_end_pruning(machine)  # Add CANCEL to dead-end states
        print(f"  🔍 [DEBUG] after apply_dead_end_pruning: {_count_states(machine)} states")
        
        machine = apply_dead_state_cleanup(machine)
        print(f"  🔍 [DEBUG] after apply_dead_state_cleanup: {_count_states(machine)} states")
        
        machine = connect_unreachable_states(machine)  # FIX: Connect unreachable states to nav graph
        print(f"  🔍 [DEBUG] after connect_unreachable_states: {_count_states(machine)} states")
        
        machine = apply_target_resolution(machine)
        print(f"  🔍 [DEBUG] after apply_target_resolution: {_count_states(machine)} states")
        
        machine = fix_relative_transitions(machine)  # FIX: Resolve relative targets like '.none.ready'
        print(f"  🔍 [DEBUG] after fix_relative_transitions: {_count_states(machine)} states")
        
        machine = fix_start_app_transitions(machine)  # FIX: authenticating → auth_guard
        print(f"  🔍 [DEBUG] after fix_start_app_transitions: {_count_states(machine)} states")
        
        machine = apply_context_awareness(machine)
        print(f"  🔍 [DEBUG] after apply_context_awareness: {_count_states(machine)} states")
        
        machine = apply_target_crosscheck(machine)  # SAFETY NET: re-route ghost arrows
        print(f"  🔍 [DEBUG] after apply_target_crosscheck: {_count_states(machine)} states")
        
        machine = apply_placeholder_flattening(machine)  # LAMA AFFILATA: collapse wrappers
        print(f"  🔍 [DEBUG] after apply_placeholder_flattening: {_count_states(machine)} states")
        
        machine = apply_initial_enforcer(machine)  # FINAL: every compound state has valid initial
        print(f"  🔍 [DEBUG] after apply_initial_enforcer: {_count_states(machine)} states")
        
        machine = apply_phantom_state_cleanup(machine)  # Remove phantom states (#, empty, duplicates) — MUST BE LAST
        print(f"  🔍 [DEBUG] after apply_phantom_state_cleanup: {_count_states(machine)} states")
        
        machine = apply_workflow_dedup(machine)  # Remove duplicate workflow states at root level
        print(f"  🔍 [DEBUG] after apply_workflow_dedup: {_count_states(machine)} states")
        
        machine = fix_initial_state(machine)  # FIX: root initial must point to real state, not branch
        print(f"  🔍 [DEBUG] after fix_initial_state: initial={machine.get('initial')}")
        
        machine = connect_sibling_substates(machine)  # FIX: connect loading↔ready↔error within compounds
        print(f"  🔍 [DEBUG] after connect_sibling_substates: {_count_states(machine)} states")
        
        try:
            after = json.dumps(machine, sort_keys=True, default=str)
            if before == after:
                if iteration > 0:
                    print(f"  ✅ Machine stabilized after {iteration + 1} iteration(s)")
                break
        except (TypeError, ValueError):
            pass
    
    return machine


def build_and_compile(base_machine: dict, transitions: list, workflows: list = None) -> dict:
    """Build a state machine and compile it with all rules.
    
    Args:
        base_machine: Base machine from generate_base_machine()
        transitions: List of transitions from LLM
        workflows: Optional list of workflows
    
    Returns:
        Compiled state machine
    """
    machine = base_machine
    
    if machine.get("type") == "parallel":
        add_transitions_to_branch(machine, transitions)
    add_transitions(machine, transitions)
    
    if workflows:
        add_workflows_to_machine(machine, workflows)
    
    machine = compile_machine(machine)
    
    return machine


def deduplicate_machine(machine: dict) -> dict:
    """Remove duplicate states using specificity-based deduplication.
    
    Args:
        machine: The state machine dict
    
    Returns:
        Deduplicated machine
    """
    return apply_specificity_dedup(machine)