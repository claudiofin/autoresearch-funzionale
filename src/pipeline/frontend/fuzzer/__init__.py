"""
Fuzzer for XState state machine.

Simulates random paths on the state machine to find:
- Dead-end states
- Unreachable states
- Infinite loops
- Unhandled transitions

Usage:
    python run.py fuzzer --machine output/spec/spec_machine.json
"""

import os
import sys
import json
import argparse

from pipeline.frontend.fuzzer.engine import load_machine, run_fuzz_test, simulate_path, detect_loops, find_reachable_states

__all__ = ["load_machine", "run_fuzz_test", "simulate_path", "detect_loops", "find_reachable_states", "main"]


def print_report(report: dict):
    """Print a readable report."""
    summary = report["summary"]
    
    print("\n" + "=" * 60)
    print("FUZZ TEST REPORT")
    print("=" * 60)
    print(f"Machine ID:        {report['machine_id']}")
    print(f"Initial state:     {report['initial_state']}")
    print(f"Total states:      {summary['total_states']}")
    print(f"Reachable states:  {summary['reachable_states']}")
    print(f"Unreachable states:{summary['unreachable_states']}")
    print()
    print(f"Paths simulated:   {summary['total_paths_simulated']}")
    print(f"Completed paths:   {summary['completed_paths']}")
    print(f"Dead-end paths:    {summary['dead_end_paths']}")
    print(f"Loop paths:        {summary['potential_loop_paths']}")
    print()
    print(f"Total errors:      {summary['total_errors']}")
    print(f"Total warnings:    {summary['total_warnings']}")
    print(f"Bugs found:        {summary['bugs_found']}")
    print(f"Coverage:          {summary['coverage']}")
    
    if report["bugs"]:
        print(f"\n🐛 BUGS FOUND ({len(report['bugs'])}):")
        for bug in report["bugs"]:
            severity_icon = "🔴" if bug["severity"] == "critical" else "🟡"
            print(f"  {severity_icon} [{bug['severity'].upper()}] {bug['description']}")
    
    if report["unreachable_states"]:
        print(f"\n⚠️  UNREACHABLE STATES:")
        for state in report["unreachable_states"]:
            print(f"  - {state}")
    
    if report["structural_loops"]:
        print(f"\n🔄 STRUCTURAL LOOPS ({len(report['structural_loops'])}):")
        for loop in report["structural_loops"][:5]:
            print(f"  - {' -> '.join(loop)}")
    
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Fuzz test for XState state machine")
    parser.add_argument("--machine", type=str, default="output/spec/spec_machine.json",
                        help="XState machine JSON file")
    parser.add_argument("--output", type=str, default="output/spec/fuzz_report.json",
                        help="Output JSON report file (default: output/spec/fuzz_report.json)")
    parser.add_argument("--num-paths", type=int, default=100,
                        help="Number of random paths to simulate (default: 100)")
    parser.add_argument("--max-steps", type=int, default=50,
                        help="Max steps per path (default: 50)")
    args = parser.parse_args()
    
    if not os.path.exists(args.machine):
        print(f"Error: Machine file not found: {args.machine}")
        sys.exit(1)
    
    machine = load_machine(args.machine)
    
    print(f"🔍 Fuzz test on machine '{machine.get('id', 'unknown')}'")
    print(f"   States: {len(machine.get('states', {}))}")
    print(f"   Paths: {args.num_paths}")
    print(f"   Max steps: {args.max_steps}")
    
    report = run_fuzz_test(machine, args.num_paths, args.max_steps)
    print_report(report)
    
    output_file = args.output
    os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else ".", exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    
    print(f"\n📄 Report saved: {output_file}")
    
    sys.exit(0 if report["summary"]["bugs_found"] == 0 else 1)


if __name__ == "__main__":
    main()