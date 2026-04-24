"""
Spec generator for automatic functional analysis.

Reads project_context.md and generates spec.md with PlantUML diagrams and XState state machine.

ITERATIVE APPROACH:
- Iteration 1: generate from scratch
- Subsequent iterations: modify existing machine based on:
  - Analyst suggestions (missing states/transitions)
  - Critic feedback (critical issues to fix)
  - Validator errors (dead-end states, unreachable states)

Usage:
    python run.py spec --context output/context/project_context.md
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path

from pipeline.frontend.spec.llm_client import call_llm_spec
from pipeline.frontend.spec.orchestrator import run_analysis

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TIME_BUDGET = 300


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate functional specification from context")
    parser.add_argument("--context", type=str, default="output/context/project_context.md",
                        help="Input context file")
    parser.add_argument("--output", type=str, default="output/spec/spec.md",
                        help="Output spec file")
    parser.add_argument("--time-budget", type=int, default=TIME_BUDGET,
                        help="Time budget in seconds")
    parser.add_argument("--suggestions", type=str, default=None,
                        help="Analyst suggestions JSON file")
    parser.add_argument("--machine", type=str, default=None,
                        help="Existing machine JSON file (for iterative approach)")
    parser.add_argument("--critic-feedback", type=str, default=None,
                        help="Critic feedback JSON file")
    args = parser.parse_args()
    
    if not os.path.exists(args.context):
        print(f"Error: Context file not found: {args.context}")
        print("Run 'python ingest.py' first")
        sys.exit(1)
    
    # Load analyst suggestions if provided
    analyst_suggestions = None
    if args.suggestions and os.path.exists(args.suggestions):
        with open(args.suggestions, "r", encoding="utf-8") as f:
            analyst_suggestions = json.load(f)
        print(f"  📋 Analyst suggestions loaded: {args.suggestions}")
    
    # Load critic feedback if provided
    critic_feedback = None
    if args.critic_feedback and os.path.exists(args.critic_feedback):
        with open(args.critic_feedback, "r", encoding="utf-8") as f:
            critic_feedback = json.load(f)
        print(f"  🚨 Critic feedback loaded: {args.critic_feedback}")
    
    print(f"Running functional analysis...")
    print(f"  Context: {args.context}")
    print(f"  Output: {args.output}")
    print(f"  Time budget: {args.time_budget}s")
    print()
    
    metrics = run_analysis(
        args.context, 
        args.output, 
        args.time_budget, 
        analyst_suggestions=analyst_suggestions,
        existing_machine_file=args.machine,
        critic_feedback=critic_feedback
    )
    
    print()
    print("=" * 50)
    print("ANALYSIS COMPLETE")
    print("=" * 50)
    print(f"States defined:      {metrics['states_count']}")
    print(f"Transitions:         {metrics['transitions_count']}")
    print(f"Edge cases:          {metrics['edge_cases_count']}")
    print(f"Error types:         {metrics['error_types_count']}")
    print(f"Time:                {metrics['elapsed_seconds']:.1f}s")
    print()
    print(f"Output files:")
    print(f"  - {metrics['spec_file']}")
    print(f"  - {metrics['machine_file']}")


if __name__ == "__main__":
    main()