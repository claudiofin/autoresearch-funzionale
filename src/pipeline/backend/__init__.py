"""
Backend analysis pipeline.

Generates functional backend specifications from the frontend state machine:
1. architect - State-to-endpoint mapping, data schema, contracts
2. critic    - API/Security/Resilience quality gate
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def main():
    """Run the Backend Architect."""
    parser = argparse.ArgumentParser(description="Generate backend functional specification")
    parser.add_argument("--machine", required=True, help="Path to spec_machine.json")
    parser.add_argument("--context", required=True, help="Path to project_context.md")
    parser.add_argument("--output", default="output/backend/backend_spec.md", help="Output file")
    args = parser.parse_args()
    
    from pipeline.backend.architect import generate_backend_spec
    generate_backend_spec(args.machine, args.context, args.output)


def main_critic():
    """Run the Backend Critic."""
    parser = argparse.ArgumentParser(description="Critique backend specification")
    parser.add_argument("--backend-spec", required=True, help="Path to backend_spec.md")
    parser.add_argument("--spec", required=True, help="Path to spec.md")
    parser.add_argument("--machine", required=True, help="Path to spec_machine.json")
    parser.add_argument("--output", default="output/backend/critic_report.json", help="Output file")
    args = parser.parse_args()
    
    from pipeline.backend.critic import critique_backend
    critique_backend(args.backend_spec, args.spec, args.machine, args.output)


if __name__ == "__main__":
    main()