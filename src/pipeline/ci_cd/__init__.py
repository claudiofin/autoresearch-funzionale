"""
CI/CD analysis pipeline.

Generates functional CI/CD specification from frontend and backend specs:
1. planner - Test matrix, environments, observability, deployment strategy
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def main():
    """Run the CI/CD Planner."""
    parser = argparse.ArgumentParser(description="Generate CI/CD functional specification")
    parser.add_argument("--spec", required=True, help="Path to spec.md")
    parser.add_argument("--backend-spec", required=True, help="Path to backend_spec.md")
    parser.add_argument("--output", default="output/ci_cd/ci_cd_spec.md", help="Output file")
    args = parser.parse_args()
    
    from pipeline.ci_cd.planner import generate_ci_cd_spec
    generate_ci_cd_spec(args.spec, args.backend_spec, args.output)


if __name__ == "__main__":
    main()