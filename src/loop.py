"""
Wrapper for backward compatibility.
Use 'from loop import AutonomousLoop' or 'from loop.cli import main'.
"""

from loop import AutonomousLoop, DEFAULT_MAX_ITERATIONS, DEFAULT_TIME_BUDGET, DEFAULT_CHECKPOINT_DIR
from loop.cli import main

__all__ = [
    "AutonomousLoop",
    "DEFAULT_MAX_ITERATIONS",
    "DEFAULT_TIME_BUDGET", 
    "DEFAULT_CHECKPOINT_DIR",
    "main"
]