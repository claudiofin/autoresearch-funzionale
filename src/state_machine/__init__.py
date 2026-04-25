"""State machine operations - builder, post-processing, and validation."""

from .builder import generate_base_machine, build_state_config, add_transitions
from .post_processing import complete_missing_branches, clean_unreachable_states, validate_no_critical_patterns, create_missing_target_states
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