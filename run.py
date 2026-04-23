#!/usr/bin/env python3
"""
Wrapper script per eseguire i comandi del sistema di analisi funzionale.

Usage:
    python run.py loop --max-iterations 10
    python run.py completeness --fix
    python run.py fuzzer
"""

import os
import sys
import argparse

# Add src/ to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

def main():
    parser = argparse.ArgumentParser(description="Autoresearch - Analisi Funzionale Automatica")
    subparsers = parser.add_subparsers(dest="command", help="Comando da eseguire")
    
    # loop command
    loop_parser = subparsers.add_parser("loop", help="Esegui loop autonomo")
    loop_parser.add_argument("--context", type=str, default="output/project_context.md")
    loop_parser.add_argument("--input-dir", type=str, default=None,
                             help="Directory input (se fornito, esegue ingest automatico)")
    loop_parser.add_argument("--max-iterations", type=int, default=10)
    loop_parser.add_argument("--time-budget", type=int, default=1200)
    loop_parser.add_argument("--force", action="store_true")
    
    # completeness command
    comp_parser = subparsers.add_parser("completeness", help="Verifica completezza")
    comp_parser.add_argument("--spec", type=str, default="output/spec.md")
    comp_parser.add_argument("--machine", type=str, default="output/spec_machine.json")
    comp_parser.add_argument("--context", type=str, default="output/project_context.md")
    comp_parser.add_argument("--fix", action="store_true")
    
    # fuzzer command
    fuzz_parser = subparsers.add_parser("fuzzer", help="Esegui fuzzing")
    fuzz_parser.add_argument("--machine", type=str, default="output/spec_machine.json")
    
    # critic command
    critic_parser = subparsers.add_parser("critic", help="Esegui review critica")
    critic_parser.add_argument("--fuzz-report", type=str, default="output/fuzz_report.json")
    
    # spec command
    spec_parser = subparsers.add_parser("spec", help="Genera specifica")
    spec_parser.add_argument("--context", type=str, default="output/project_context.md")
    
    # ingest command
    ingest_parser = subparsers.add_parser("ingest", help="Processa input e genera contesto")
    ingest_parser.add_argument("--input-dir", type=str, default="inputs/")
    ingest_parser.add_argument("--output-file", type=str, default="output/project_context.md")

    # analyst command
    analyst_parser = subparsers.add_parser("analyst", help="Analizza pattern UI")
    analyst_parser.add_argument("--context", type=str, default="output/project_context.md")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Create output dir if needed
    os.makedirs("output", exist_ok=True)
    
    if args.command == "loop":
        from loop import main as loop_main
        sys.argv = ["loop",
                     "--context", args.context,
                     "--max-iterations", str(args.max_iterations),
                     "--time-budget", str(args.time_budget)]
        if args.force:
            sys.argv.append("--force")
        if args.input_dir:
            sys.argv.extend(["--input-dir", args.input_dir])
        loop_main()
    
    elif args.command == "completeness":
        from completeness import main as comp_main
        sys.argv = ["completeness",
                     "--spec", args.spec,
                     "--machine", args.machine,
                     "--context", args.context]
        if args.fix:
            sys.argv.append("--fix")
        comp_main()
    
    elif args.command == "fuzzer":
        from fuzzer import main as fuzz_main
        sys.argv = ["fuzzer", "--machine", args.machine]
        fuzz_main()
    
    elif args.command == "critic":
        from critic import main as critic_main
        sys.argv = ["critic", "--fuzz-report", args.fuzz_report]
        critic_main()
    
    elif args.command == "spec":
        from spec import main as spec_main
        sys.argv = ["spec", "--context", args.context]
        spec_main()
    
    elif args.command == "ingest":
        from ingest import main as ingest_main
        sys.argv = ["ingest",
                     "--input-dir", args.input_dir,
                     "--output-file", args.output_file]
        ingest_main()
    
    elif args.command == "analyst":
        from analyst import main as analyst_main
        sys.argv = ["analyst", "--context", args.context]
        analyst_main()


if __name__ == "__main__":
    main()