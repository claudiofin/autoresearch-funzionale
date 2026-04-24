"""
CLI entry point for the autonomous loop.
"""

import os
import sys
import argparse

from loop import AutonomousLoop, DEFAULT_MAX_ITERATIONS, DEFAULT_TIME_BUDGET, DEFAULT_CHECKPOINT_DIR


def main():
    parser = argparse.ArgumentParser(description="Autonomous loop for functional analysis")
    parser.add_argument("--context", type=str, default="output/context/project_context.md",
                        help="Context file to analyze")
    parser.add_argument("--input-dir", type=str, default=None,
                        help="Input directory (if provided, runs automatic ingest)")
    parser.add_argument("--max-iterations", type=int, default=DEFAULT_MAX_ITERATIONS,
                        help=f"Max iterations (default: {DEFAULT_MAX_ITERATIONS})")
    parser.add_argument("--time-budget", type=int, default=DEFAULT_TIME_BUDGET,
                        help=f"Time budget in seconds (default: {DEFAULT_TIME_BUDGET})")
    parser.add_argument("--checkpoint-dir", type=str, default=DEFAULT_CHECKPOINT_DIR,
                        help=f"Checkpoint directory (default: {DEFAULT_CHECKPOINT_DIR})")
    parser.add_argument("--force", action="store_true",
                        help="Force all iterations even without critical errors")
    parser.add_argument("--generate-ui", action="store_true",
                        help="Generate UI specs from state machine (at end of loop)")
    parser.add_argument("--force-design", action="store_true",
                        help="Force regeneration of DESIGN.md even if it exists")
    args = parser.parse_args()
    
    # If input-dir is provided, context doesn't need to exist yet
    if args.input_dir and not os.path.exists(args.input_dir):
        print(f"Error: Input directory not found: {args.input_dir}")
        sys.exit(1)
    
    # If no input-dir, context must exist
    if not args.input_dir and not os.path.exists(args.context):
        print(f"Error: Context file not found: {args.context}")
        print("Run 'python ingest.py' first to generate project_context.md")
        print("Or use --input-dir to run automatic ingest")
        sys.exit(1)
    
    # Run loop
    loop = AutonomousLoop(
        context_file=args.context,
        max_iterations=args.max_iterations,
        time_budget=args.time_budget,
        checkpoint_dir=args.checkpoint_dir,
        force_iterations=args.force,
        input_dir=args.input_dir,
        generate_ui=args.generate_ui,
        force_design=args.force_design
    )
    
    report = loop.run()
    
    # Print final report
    print()
    print("=" * 60)
    print("FINAL REPORT")
    print("=" * 60)
    print(f"Completed:       {report['completed']}")
    print(f"Iterations:      {report['iterations_run']}/{report['max_iterations']}")
    print(f"Total time:      {report['elapsed_seconds']:.1f}s")
    print(f"Final errors:    {report['final_errors']}")
    print(f"Final warnings:  {report['final_warnings']}")
    print()
    print(f"Checkpoint: {args.checkpoint_dir}/")
    print(f"Report:     {args.checkpoint_dir}/final_report.json")


if __name__ == "__main__":
    main()