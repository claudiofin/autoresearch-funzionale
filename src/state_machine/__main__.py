"""Entry point for running state_machine modules from the command line.

Usage:
    python -m state_machine.json_validator <machine_file.json>
"""

import sys

from state_machine.json_validator import main as json_validator_main


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m state_machine <module> [args...]")
        print("Available modules:")
        print("  json_validator <machine_file.json>  - Validate machine structure")
        sys.exit(1)
    
    module = sys.argv[1]
    args = sys.argv[2:]
    
    if module == "json_validator":
        # Temporarily replace sys.argv for the validator's main()
        original_argv = sys.argv
        sys.argv = ["json_validator"] + args
        try:
            json_validator_main()
        finally:
            sys.argv = original_argv
    else:
        print(f"Unknown module: {module}")
        print("Available modules: json_validator")
        sys.exit(1)


if __name__ == "__main__":
    main()