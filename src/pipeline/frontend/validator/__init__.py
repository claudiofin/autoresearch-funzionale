"""
Automatic XState state machine validator.

Detects:
- Dead-end states (states without exit transitions)
- Unreachable states from initial state
- Transitions to undefined states
- Potential infinite loops

Usage:
    python run.py validator --machine output/spec/spec_machine.json
"""

import os
import sys
import json
import argparse

from state_machine.validation import validate_machine


def print_report(results: dict):
    """Print a readable report of the results."""
    print("\n" + "=" * 60)
    print("STATE MACHINE VALIDATION")
    print("=" * 60)
    print(f"Machine ID:        {results['machine_id']}")
    print(f"Initial state:     {results['initial_state']}")
    print(f"Total states:      {results['total_states']}")
    print(f"Total transitions: {results['total_transitions']}")
    print(f"Quality Score:     {results['quality_score']}/100")
    print(f"Valid:             {'✅ YES' if results['is_valid'] else '❌ NO'}")
    
    if results["dead_end_states"]:
        print(f"\n⚠️  DEAD-END STATES ({len(results['dead_end_states'])}):")
        for issue in results["dead_end_states"]:
            print(f"  - {issue['state']}: {issue['description']}")
            print(f"    💡 {issue['suggestion']}")
    
    if results["unreachable_states"]:
        print(f"\n⚠️  UNREACHABLE STATES ({len(results['unreachable_states'])}):")
        for issue in results["unreachable_states"]:
            state_name = issue.get('state', issue.get('issue', 'unknown'))
            print(f"  - {state_name}: {issue['description']}")
    
    if results["invalid_transitions"]:
        print(f"\n❌ INVALID TRANSITIONS ({len(results['invalid_transitions'])}):")
        for issue in results["invalid_transitions"]:
            print(f"  - {issue['description']}")
    
    if results["potential_loops"]:
        print(f"\n⚠️  POTENTIAL INFINITE LOOPS ({len(results['potential_loops'])}):")
        for issue in results["potential_loops"]:
            print(f"  - {issue['description']}")
    
    if not any([
        results["dead_end_states"],
        results["unreachable_states"],
        results["invalid_transitions"],
        results["potential_loops"]
    ]):
        print("\n✅ No issues found. The state machine is well structured.")
    
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Validate XState state machine")
    parser.add_argument("--machine", type=str, default="output/spec/spec_machine.json",
                        help="XState machine JSON file")
    parser.add_argument("--output", type=str, default=None,
                        help="Output JSON report file (optional)")
    args = parser.parse_args()
    
    if not os.path.exists(args.machine):
        print(f"Error: Machine file not found: {args.machine}")
        sys.exit(1)
    
    results = validate_machine(args.machine)
    print_report(results)
    
    if args.output:
        os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"\n📄 Report saved: {args.output}")
    
    sys.exit(0 if results["is_valid"] else 1)


if __name__ == "__main__":
    main()