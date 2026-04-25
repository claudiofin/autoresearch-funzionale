"""State machine operations - builder, post-processing, and validation."""

from .builder import (
    generate_base_machine,
    build_state_config,
    add_transitions,
    normalize_machine,
    compile_machine,
    build_and_compile,
    # Domain configuration exports
    DEFAULT_STATE_NAMES,
    DEFAULT_BRANCH_NAMES,
    DEFAULT_EVENT_NAMES,
    DEFAULT_ACTION_NAMES,
    _resolve_state_name,
    _resolve_branch_name,
    _resolve_event_name,
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
    "generate_base_machine",
    "build_state_config",
    "add_transitions",
    "normalize_machine",
    "compile_machine",
    "build_and_compile",
    "DEFAULT_STATE_NAMES",
    "DEFAULT_BRANCH_NAMES",
    "DEFAULT_EVENT_NAMES",
    "DEFAULT_ACTION_NAMES",
    "complete_missing_branches",
    "clean_unreachable_states",
    "validate_no_critical_patterns",
    "create_missing_target_states",
    "load_machine",
    "find_dead_end_states",
    "find_unreachable_states",
    "find_invalid_transitions",
    "find_potential_infinite_loops",
    "validate_machine",
]