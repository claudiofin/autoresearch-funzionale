"""
Testbook Generator Pipeline - Generates test scenarios from XState machine definitions.

Usage:
    python run.py testbook-generator --machine output/spec/spec_machine.json
    python run.py testbook-generator --machine output/spec/spec_machine.json --output output/testbook/system_tests.md
    python run.py testbook-generator --force

Individual step:
    python -m src.pipeline.testbook_generator --machine output/spec/spec_machine.json
"""

import argparse
import os
import sys


def main():
    """Main entry point for the testbook generator pipeline."""
    parser = argparse.ArgumentParser(
        description="Testbook Generator - Generate test scenarios from XState machine definitions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python run.py testbook-generator
    python run.py testbook-generator --machine output/spec/spec_machine.json
    python run.py testbook-generator --output output/testbook/system_tests.md
    python run.py testbook-generator --force
        """
    )

    parser.add_argument(
        "--machine",
        type=str,
        default="output/spec/spec_machine.json",
        help="Path to the XState machine JSON file (default: output/spec/spec_machine.json)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output/testbook/system_tests.md",
        help="Output path for the testbook markdown file (default: output/testbook/system_tests.md)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force regeneration even if output file exists"
    )

    args = parser.parse_args()

    # Import here to avoid circular dependencies
    from pipeline.testbook_generator.engine import TestbookEngine

    # Validate input
    if not os.path.exists(args.machine):
        print(f"❌ Error: Machine file not found: {args.machine}")
        print("   Run 'python run.py frontend-spec' first to generate the state machine.")
        sys.exit(1)

    # Check if output exists
    if os.path.exists(args.output) and not args.force:
        print(f"⏭️  Testbook already exists: {args.output}")
        print("   Use --force to regenerate.")
        return

    # Create output directory
    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Run the engine
    print("\n" + "=" * 60)
    print("🧪 TESTBOOK GENERATOR")
    print("=" * 60)
    print()
    print(f"📄 Loading machine from: {args.machine}")

    engine = TestbookEngine(args.machine)

    print(f"   Machine ID: {engine.machine_id}")
    print(f"   Workflows found: {len(engine.workflows)}")
    for wf_id in engine.workflows:
        print(f"     - {wf_id}")
    print()

    # Generate testbook
    print("🔍 Running State Coverage Audit...")
    coverage = engine.audit_state_coverage()
    for wf_id, data in coverage.items():
        status = "✅" if data["status"] == "PASS" else "⚠️"
        print(f"   {status} {wf_id}: {data['reachable_states']}/{data['total_states']} states reachable")
    print()

    print("🔒 Verifying Global Invariants...")
    invariants = engine.verify_invariants()
    for inv in invariants:
        status = "✅" if inv["status"] == "PASS" else "❌"
        print(f"   {status} {inv['invariant']}: {inv['details']}")
    print()

    print("🔎 Discovering paths and generating scenarios...")
    scenarios = engine.generate_scenarios()
    print(f"   Generated {len(scenarios)} test scenarios")
    print()

    print("📝 Generating testbook markdown...")
    markdown = engine.generate_testbook_md()

    # Write output
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(markdown)

    print()
    print("=" * 60)
    print("✅ Testbook generated successfully!")
    print(f"📁 Output: {args.output}")
    print("=" * 60)
    print()
    print(f"File size: {len(markdown)} characters")
    print(f"Workflows covered: {len(engine.workflows)}")
    print(f"Test scenarios: {len(scenarios)}")
    print()


if __name__ == "__main__":
    main()