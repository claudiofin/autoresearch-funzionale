"""
Frontend analysis pipeline.

Coordinates the iterative analysis of UI/UX through:
1. analyst   - Analyze context and suggest UI patterns
2. spec      - Generate functional specification + state machine
3. validator - Validate state machine quality
4. fuzzer    - Fuzz test edge cases
5. critic    - Critique quality and UX decisions
"""

__all__ = ["analyst", "spec", "validator", "fuzzer", "critic"]