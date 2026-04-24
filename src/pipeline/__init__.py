"""Pipeline modules for the autoresearch system.

Three independent analysis pipelines:
1. frontend - UI/UX analysis (analyst → spec → validator → fuzzer → critic)
2. backend  - Backend functional analysis (architect → critic)
3. ci_cd    - CI/CD functional analysis (planner)

Shared modules:
- ingest       - Ingest project context
- ui_generator - Generate UI code from state machine
"""

__all__ = [
    "frontend",
    "backend",
    "ci_cd",
    "ingest",
    "ui_generator",
]