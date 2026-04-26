"""State machine operations - builder, post-processing, and validation.

This package provides a modular state machine builder with:
- Builder: Generate and compile state machines from LLM output
- Post-processing: Clean up and validate machine structure
- Validation: Check for dead ends, unreachable states, infinite loops

Modules:
- builder.py: Main coordinator (generate_base_machine, compile_machine, build_and_compile)
- constants.py: Default configuration (state names, branch names, events, actions)
- traversal.py: BFS, path collection, target extraction
- normalization.py: Naming fixes, branch placement
- injection.py: Error handlers, global exit, auto-inject sub_states
- cleanup.py: Dead state removal, deduplication
- target_resolution.py: Relative/caret target resolution, placeholders
- context_awareness.py: Guards, emergency exits
- transitions.py: Adding transitions to machines
- workflows.py: Workflow compound state building
- post_processing.py: Additional post-compilation cleanup
- validation.py: Machine validation and analysis
"""

from .builder import (
    generate_base_machine,
    build_state_config,
    add_transitions,
    normalize_machine,
    compile_machine,
    build_and_compile,
    deduplicate_machine,
    # Domain configuration exports
    DEFAULT_STATE_NAMES,
    DEFAULT_BRANCH_NAMES,
    DEFAULT_EVENT_NAMES,
    DEFAULT_ACTION_NAMES,
    DEFAULT_GUARD_NAMES,
    DEFAULT_EMERGENCY_EVENTS,
    XSTATE_ACTION_MAP,
    _resolve_state_name,
    _resolve_branch_name,
    _resolve_action_name,
)
from .post_processing import (
    complete_missing_branches,
    clean_unreachable_states,
    validate_no_critical_patterns,
    create_missing_target_states,
)
from .validation import (
    load_machine,
    find_dead_end_states,
    find_unreachable_states,
    find_invalid_transitions,
    find_potential_infinite_loops,
    validate_machine,
)

__all__ = [
    # Builder main API
    "generate_base_machine",
    "build_state_config",
    "add_transitions",
    "normalize_machine",
    "compile_machine",
    "build_and_compile",
    "deduplicate_machine",
    # Configuration
    "DEFAULT_STATE_NAMES",
    "DEFAULT_BRANCH_NAMES",
    "DEFAULT_EVENT_NAMES",
    "DEFAULT_ACTION_NAMES",
    "DEFAULT_GUARD_NAMES",
    "DEFAULT_EMERGENCY_EVENTS",
    "XSTATE_ACTION_MAP",
    # Post-processing
    "complete_missing_branches",
    "clean_unreachable_states",
    "validate_no_critical_patterns",
    "create_missing_target_states",
    # Validation
    "load_machine",
    "find_dead_end_states",
    "find_unreachable_states",
    "find_invalid_transitions",
    "find_potential_infinite_loops",
    "validate_machine",
]