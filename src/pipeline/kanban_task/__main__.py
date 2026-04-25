"""CLI wrapper for kanban-task pipeline."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from pipeline.kanban_task import main

if __name__ == "__main__":
    main()