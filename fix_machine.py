#!/usr/bin/env python3
"""Fix existing spec_machine.json by re-running the compiler pipeline.

This applies all the generic fallback fixes to an already-generated machine
without needing to re-run the LLM pipeline.
"""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from state_machine import compile_machine


def main():
    machine_path = "output/spec/spec_machine.json"
    backup_path = "output/spec/spec_machine.json.bak"
    
    if not os.path.exists(machine_path):
        print(f"❌ Machine file not found: {machine_path}")
        sys.exit(1)
    
    # Load existing machine
    with open(machine_path, "r") as f:
        machine = json.load(f)
    
    print(f"📄 Loaded machine with {len(machine.get('states', {}))} top-level states")
    
    # Backup original
    with open(backup_path, "w") as f:
        json.dump(machine, f, indent=2)
    print(f"💾 Backup saved to {backup_path}")
    
    # Re-compile with fixed pipeline
    print("🔧 Re-compiling machine with fixed pipeline...")
    fixed_machine = compile_machine(machine)
    
    # Save fixed machine
    with open(machine_path, "w") as f:
        json.dump(fixed_machine, f, indent=2)
    
    print(f"✅ Fixed machine saved to {machine_path}")
    print(f"📊 Top-level states: {len(fixed_machine.get('states', {}))}")
    
    # Count total states
    def count_states(states_dict, prefix=""):
        count = 0
        for name, config in states_dict.items():
            count += 1
            if isinstance(config, dict) and "states" in config:
                count += count_states(config["states"], f"{prefix}.{name}")
        return count
    
    total = count_states(fixed_machine.get("states", {}))
    print(f"📊 Total states: {total}")


if __name__ == "__main__":
    main()