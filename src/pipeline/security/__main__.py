"""
Security Pipeline CLI entry point.

Usage:
    python -m pipeline.security
    python -m pipeline.security --frontend output/spec.md --backend output/backend/backend_spec.md --ci-cd output/ci_cd/ci_cd_spec.md --context output/context/project_context.md
    python -m pipeline.security --output output/security/security_spec.md
"""

import argparse
import os
import sys

from pipeline.security.auditor import generate_security_spec


def main():
    parser = argparse.ArgumentParser(
        description="Generate security audit and threat model from project specifications.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m pipeline.security
    python -m pipeline.security --output output/security/security_spec.md
        """,
    )

    parser.add_argument(
        "--frontend",
        type=str,
        default="output/spec.md",
        help="Path to frontend specification file",
    )
    parser.add_argument(
        "--backend",
        type=str,
        default="output/backend/backend_spec.md",
        help="Path to backend specification file",
    )
    parser.add_argument(
        "--ci-cd",
        type=str,
        default="output/ci_cd/ci_cd_spec.md",
        help="Path to CI/CD specification file",
    )
    parser.add_argument(
        "--context",
        type=str,
        default="output/context/project_context.md",
        help="Path to project context file",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output/security/security_spec.md",
        help="Output file path for security specification",
    )

    args = parser.parse_args()

    # Read input files
    def read_file_safe(path: str) -> str:
        if not os.path.exists(path):
            print(f"  ⚠️ File not found: {path}")
            print(f"     Continuing with empty content for this input.")
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    frontend_spec = read_file_safe(args.frontend)
    backend_spec = read_file_safe(args.backend)
    ci_cd_spec = read_file_safe(args.ci_cd)
    context = read_file_safe(args.context)

    if not frontend_spec and not backend_spec and not ci_cd_spec:
        print("❌ No specification files found. Run the pipeline first:")
        print("   python run.py loop-frontend")
        print("   python run.py backend")
        print("   python run.py ci-cd")
        sys.exit(1)

    # Generate security spec
    result = generate_security_spec(
        frontend_spec=frontend_spec,
        backend_spec=backend_spec,
        ci_cd_spec=ci_cd_spec,
        context=context,
        output_file=args.output,
    )

    if result["success"]:
        print(f"\n✅ Security audit completed successfully!")
        print(f"   Output: {result['output']}")
        print(f"   Size: {result['size_chars']} characters")
    else:
        print(f"\n❌ Security audit failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()