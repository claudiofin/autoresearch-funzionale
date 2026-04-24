#!/usr/bin/env python3
"""
Wrapper script to execute commands for the automatic functional analysis system.

Three independent pipelines:
  FRONTEND:  ingest → analyst → spec → validator → fuzzer → critic → ui_generator
  BACKEND:   architect → critic
  CI/CD:     planner

Usage:
    # Frontend loop (iterative)
    python run.py loop-frontend --input-dir inputs/ --max-iterations 10 --generate-ui

    # Backend pipeline
    python run.py backend --machine output/spec/spec_machine.json --context output/context/project_context.md
    python run.py backend-critic --backend-spec output/backend/backend_spec.md --spec output/spec/spec.md --machine output/spec/spec_machine.json

    # CI/CD pipeline
    python run.py ci-cd --spec output/spec/spec.md --backend-spec output/backend/backend_spec.md

    # Individual frontend steps
    python run.py ingest --input-dir inputs/
    python run.py frontend-analyst --context output/context/project_context.md
    python run.py frontend-spec --context output/context/project_context.md
    python run.py frontend-validator --machine output/spec/spec_machine.json
    python run.py frontend-fuzzer --machine output/spec/spec_machine.json
    python run.py frontend-critic --fuzz-report output/spec/fuzz_report.json
"""

import os
import sys
import argparse

# Add src/ to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))


def main():
    parser = argparse.ArgumentParser(
        description="Autoresearch - Automatic Functional Analysis System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Three independent pipelines:
  FRONTEND:  ingest → analyst → spec → validator → fuzzer → critic → ui_generator
  BACKEND:   architect → critic
  CI/CD:     planner

Examples:
  python run.py loop-frontend --input-dir inputs/ --max-iterations 10
  python run.py backend --machine output/spec/spec_machine.json --context output/context/project_context.md
  python run.py ci-cd --spec output/spec/spec.md --backend-spec output/backend/backend_spec.md
        """
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # ─── FRONTEND LOOP ───
    loop_parser = subparsers.add_parser("loop-frontend", help="Run autonomous frontend loop")
    loop_parser.add_argument("--context", type=str, default="output/context/project_context.md")
    loop_parser.add_argument("--input-dir", type=str, default=None,
                             help="Input directory (if provided, runs automatic ingest)")
    loop_parser.add_argument("--max-iterations", type=int, default=10)
    loop_parser.add_argument("--time-budget", type=int, default=1200)
    loop_parser.add_argument("--force", action="store_true")
    loop_parser.add_argument("--force-design", action="store_true",
                             help="Force regeneration of DESIGN.md even if it exists")
    loop_parser.add_argument("--generate-ui", action="store_true",
                             help="Generate UI specs from state machine (at end of loop)")

    # ─── BACKEND ───
    backend_parser = subparsers.add_parser("backend", help="Generate backend functional specification")
    backend_parser.add_argument("--machine", type=str, default="output/spec/spec_machine.json")
    backend_parser.add_argument("--context", type=str, default="output/context/project_context.md")
    backend_parser.add_argument("--output", type=str, default="output/backend/backend_spec.md")

    backend_critic_parser = subparsers.add_parser("backend-critic", help="Critique backend specification")
    backend_critic_parser.add_argument("--backend-spec", type=str, default="output/backend/backend_spec.md")
    backend_critic_parser.add_argument("--spec", type=str, default="output/spec/spec.md")
    backend_critic_parser.add_argument("--machine", type=str, default="output/spec/spec_machine.json")
    backend_critic_parser.add_argument("--output", type=str, default="output/backend/critic_report.json")

    # ─── CI/CD ───
    cicd_parser = subparsers.add_parser("ci-cd", help="Generate CI/CD functional specification")
    cicd_parser.add_argument("--spec", type=str, default="output/spec/spec.md")
    cicd_parser.add_argument("--backend-spec", type=str, default="output/backend/backend_spec.md")
    cicd_parser.add_argument("--output", type=str, default="output/ci_cd/ci_cd_spec.md")

    # ─── FRONTEND INDIVIDUAL STEPS ───
    ingest_parser = subparsers.add_parser("ingest", help="Process inputs and generate context")
    ingest_parser.add_argument("--input-dir", type=str, default="inputs/")
    ingest_parser.add_argument("--output-file", type=str, default="output/context/project_context.md")

    analyst_parser = subparsers.add_parser("frontend-analyst", help="Analyze UI patterns")
    analyst_parser.add_argument("--context", type=str, default="output/context/project_context.md")
    analyst_parser.add_argument("--critic-feedback", type=str, default=None,
                                help="Path to critic feedback JSON")

    spec_parser = subparsers.add_parser("frontend-spec", help="Generate specification")
    spec_parser.add_argument("--context", type=str, default="output/context/project_context.md")
    spec_parser.add_argument("--suggestions", type=str, default=None,
                             help="Path to analyst suggestions JSON")
    spec_parser.add_argument("--machine", type=str, default=None,
                             help="Path to existing spec_machine.json (iterative)")
    spec_parser.add_argument("--critic-feedback", type=str, default=None,
                             help="Path to critic feedback JSON")

    validator_parser = subparsers.add_parser("frontend-validator", help="Validate XState state machine")
    validator_parser.add_argument("--machine", type=str, default="output/spec/spec_machine.json")
    validator_parser.add_argument("--output", type=str, default=None,
                                  help="Output JSON report file")

    fuzzer_parser = subparsers.add_parser("frontend-fuzzer", help="Run fuzzing")
    fuzzer_parser.add_argument("--machine", type=str, default="output/spec/spec_machine.json")

    critic_parser = subparsers.add_parser("frontend-critic", help="Run critical review")
    critic_parser.add_argument("--fuzz-report", type=str, default="output/spec/fuzz_report.json")
    critic_parser.add_argument("--spec", type=str, default="output/spec/spec.md")
    critic_parser.add_argument("--machine", type=str, default="output/spec/spec_machine.json")
    critic_parser.add_argument("--context", type=str, default="output/context/project_context.md")

    ui_parser = subparsers.add_parser("ui-generator", help="Generate UI specs from state machine")
    ui_parser.add_argument("--machine", type=str, default="output/spec/spec_machine.json")
    ui_parser.add_argument("--context", type=str, default="output/context/project_context.md")
    ui_parser.add_argument("--output-dir", type=str, default="output/ui_specs")
    ui_parser.add_argument("--force-design", action="store_true")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Create output dir if needed
    os.makedirs("output", exist_ok=True)

    # ─── FRONTEND LOOP ───
    if args.command == "loop-frontend":
        from loop.cli import main as loop_main  # type: ignore
        sys.argv = ["loop",
                     "--context", args.context,
                     "--max-iterations", str(args.max_iterations),
                     "--time-budget", str(args.time_budget)]
        if args.force:
            sys.argv.append("--force")
        if args.input_dir:
            sys.argv.extend(["--input-dir", args.input_dir])
        if args.force_design:
            sys.argv.append("--force-design")
        if args.generate_ui:
            sys.argv.append("--generate-ui")
        loop_main()

    # ─── BACKEND ───
    elif args.command == "backend":
        from pipeline.backend import main as backend_main  # type: ignore
        sys.argv = ["backend",
                    "--machine", args.machine,
                    "--context", args.context,
                    "--output", args.output]
        backend_main()

    elif args.command == "backend-critic":
        from pipeline.backend import main_critic as backend_critic_main  # type: ignore
        sys.argv = ["backend-critic",
                    "--backend-spec", args.backend_spec,
                    "--spec", args.spec,
                    "--machine", args.machine,
                    "--output", args.output]
        backend_critic_main()

    # ─── CI/CD ───
    elif args.command == "ci-cd":
        from pipeline.ci_cd import main as cicd_main  # type: ignore
        sys.argv = ["ci-cd",
                    "--spec", args.spec,
                    "--backend-spec", args.backend_spec,
                    "--output", args.output]
        cicd_main()

    # ─── FRONTEND INDIVIDUAL STEPS ───
    elif args.command == "ingest":
        from pipeline.ingest import main as ingest_main  # type: ignore
        sys.argv = ["ingest",
                    "--input-dir", args.input_dir,
                    "--output-file", args.output_file]
        ingest_main()

    elif args.command == "frontend-analyst":
        from pipeline.frontend.analyst import main as analyst_main  # type: ignore
        sys.argv = ["analyst", "--context", args.context]
        if args.critic_feedback:
            sys.argv.extend(["--critic-feedback", args.critic_feedback])
        analyst_main()

    elif args.command == "frontend-spec":
        from pipeline.frontend.spec import main as spec_main  # type: ignore
        sys.argv = ["spec", "--context", args.context]
        if args.suggestions:
            sys.argv.extend(["--suggestions", args.suggestions])
        if args.machine:
            sys.argv.extend(["--machine", args.machine])
        if args.critic_feedback:
            sys.argv.extend(["--critic-feedback", args.critic_feedback])
        spec_main()

    elif args.command == "frontend-validator":
        from pipeline.frontend.validator import main as validator_main  # type: ignore
        sys.argv = ["validator", "--machine", args.machine]
        if args.output:
            sys.argv.extend(["--output", args.output])
        validator_main()

    elif args.command == "frontend-fuzzer":
        from pipeline.frontend.fuzzer import main as fuzz_main  # type: ignore
        sys.argv = ["fuzzer", "--machine", args.machine]
        fuzz_main()

    elif args.command == "frontend-critic":
        from pipeline.frontend.critic import main as critic_main  # type: ignore
        sys.argv = ["critic",
                    "--fuzz-report", args.fuzz_report,
                    "--spec", args.spec,
                    "--machine", args.machine,
                    "--context", args.context]
        critic_main()

    elif args.command == "ui-generator":
        from pipeline.ui_generator import main as ui_main  # type: ignore
        sys.argv = ["ui-generator",
                    "--machine", args.machine,
                    "--context", args.context,
                    "--output-dir", args.output_dir]
        if args.force_design:
            sys.argv.append("--force-design")
        ui_main()


if __name__ == "__main__":
    main()