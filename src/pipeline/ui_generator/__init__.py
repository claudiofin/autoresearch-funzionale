"""
Dynamic UI Generator - Generates UI specifications using an LLM.

Reads spec_machine.json and project_context.md, uses an LLM to generate:
1. output/ui_specs/states/UI_<state>.md — Specifications for each machine state
2. output/ui_specs/screens/<screen>.md — Specifications for each real screen
3. output/ui_specs/README.md — Index with PlantUML diagram
"""

import json
import os
import sys
import time
import argparse
from pathlib import Path

from pipeline.ui_generator.llm_client import call_llm, LLMConfig
from pipeline.ui_generator.spec_generator import (
    generate_design_system_llm,
    generate_state_spec_llm,
    discover_screens_llm,
    generate_screen_spec_llm,
    generate_index_llm,
)
from pipeline.ui_generator.plantuml import generate_plantuml


def load_machine(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def load_context(path: str) -> str:
    with open(path, "r") as f:
        return f.read()


def load_spec(path: str) -> str:
    with open(path, "r") as f:
        return f.read()


def load_design(path: str) -> str:
    """Loads the Design System from DESIGN.md file, if it exists."""
    try:
        with open(path, "r") as f:
            return f.read()
    except FileNotFoundError:
        print(f"⚠️  File {path} not found. Proceeding without Design System.")
        return ""


def main():
    parser = argparse.ArgumentParser(description="Dynamically generate UI specifications with LLM")
    parser.add_argument("--machine", default="output/spec/spec_machine.json", help="Path to spec_machine.json")
    parser.add_argument("--context", default="output/context/project_context.md", help="Path to project_context.md")
    parser.add_argument("--spec", default="output/spec/spec.md", help="Path to spec.md")
    parser.add_argument("--output-dir", default="output/ui_specs", help="Output directory")
    parser.add_argument("--provider", choices=["openai", "anthropic", "google", "ollama", "dashscope"], default="", help="LLM Provider")
    parser.add_argument("--model", default="", help="LLM Model")
    parser.add_argument("--api-key", default="", help="LLM API Key")
    parser.add_argument("--base-url", default="", help="LLM Base URL")
    parser.add_argument("--states-only", action="store_true", help="Generate only states")
    parser.add_argument("--screens-only", action="store_true", help="Generate only screens")
    parser.add_argument("--design", default="output/ui_specs/DESIGN.md", help="Path to Design System file")
    parser.add_argument("--force-design", action="store_true", help="Force regeneration of DESIGN.md even if it exists")
    args = parser.parse_args()
    
    # Initialize LLM config
    llm_config = LLMConfig(
        provider=args.provider,
        model=args.model,
        api_key=args.api_key,
        base_url=args.base_url
    )
    
    if not llm_config.api_key and llm_config.provider != "ollama":
        print("❌ Set LLM_API_KEY or OPENAI_API_KEY")
        sys.exit(1)
    
    print(f"🤖 Configuration: Provider={llm_config.provider} | Model={llm_config.model}")
    
    # Load context first (needed for design system generation)
    context = load_context(args.context)
    
    # Ensure output directory exists
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Design System: load or generate
    print(f"🎨 Design System configuration...")
    if os.path.exists(args.design) and not args.force_design:
        print(f"  ✅ Found existing file: {args.design}. Using it to preserve your modifications.")
        design_system = load_design(args.design)
    else:
        reason = "File not found" if not os.path.exists(args.design) else "Forced regeneration requested (--force-design)"
        print(f"  ✨ {reason}. Dynamically generating a new Design System from context...")
        design_system = generate_design_system_llm(context)
        
        if design_system:
            with open(args.design, "w") as f:
                f.write(design_system)
            print(f"  💾 New Design System generated and saved to {args.design}!")
        else:
            print("  ⚠️  Generation failed, proceeding without Design System.")
    
    # CORRECT ARRAY INITIALIZATION
    generated_states = []
    generated_screens = []
    
    machine = load_machine(args.machine)
    spec = load_spec(args.spec)
    states = machine.get("states", {})
    
    states_dir = os.path.join(args.output_dir, "states")
    screens_dir = os.path.join(args.output_dir, "screens")
    os.makedirs(states_dir, exist_ok=True)
    os.makedirs(screens_dir, exist_ok=True)
    
    if not args.screens_only:
        print(f"\n🏗️  Generating machine states (Level 2)...")
        for state_name, state_def in states.items():
            print(f"  🔄 Generating UI spec for '{state_name}'...")
            try:
                md_content = generate_state_spec_llm(state_name, state_def, machine, context, spec, design_system)
                output_path = os.path.join(states_dir, f"UI_{state_name}.md")
                with open(output_path, "w") as f:
                    f.write(md_content)
                generated_states.append(state_name)
            except Exception as e:
                print(f"    ❌ Error generating '{state_name}': {e}")
            time.sleep(1)
            
    if not args.states_only:
        print(f"\n🔍 Discovering screens via LLM...")
        screen_definitions = discover_screens_llm(machine, context, spec)
        print(f"\n🖥️  Generating real screens (Level 1)...")
        for screen_def in screen_definitions:
            screen_name = screen_def["name"]
            related_states = screen_def["states"]
            print(f"  🔄 Generating screen '{screen_name}'...")
            try:
                md_content = generate_screen_spec_llm(screen_name, related_states, machine, context, spec, design_system)
                output_path = os.path.join(screens_dir, f"{screen_name}.md")
                with open(output_path, "w") as f:
                    f.write(md_content)
                generated_screens.append(screen_name)
            except Exception as e:
                print(f"    ❌ Error generating '{screen_name}': {e}")
            time.sleep(1)
            
    print(f"\n📋 Generating README.md...")
    try:
        readme_content = generate_index_llm(states, generated_screens, machine)
        plantuml = generate_plantuml(machine)
        readme_content += f"\n\n## Flow Diagram (PlantUML)\n\n```plantuml\n{plantuml}\n```\n"
        readme_path = os.path.join(args.output_dir, "README.md")
        with open(readme_path, "w") as f:
            f.write(readme_content)
    except Exception as e:
        print(f"  ❌ Error generating README: {e}")
        
    print(f"\n🎉 Completed! {len(generated_states)} states and {len(generated_screens)} screens generated in {args.output_dir}.")


if __name__ == "__main__":
    main()