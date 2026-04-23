#!/usr/bin/env python3
"""
Dynamic UI Generator - Generates UI specifications using an LLM.

Reads spec_machine.json and project_context.md, uses an LLM to generate:
1. output/ui_specs/states/UI_<state>.md — Specifications for each machine state
2. output/ui_specs/screens/<screen>.md — Specifications for each real screen
3. output/ui_specs/README.md — Index with PlantUML diagram

The LLM analyzes the state machine and context to generate realistic UI specs
consistent with the actual product.
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# LLM Configuration
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openai")  # openai, anthropic, ollama
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o")  # or "claude-3-5-sonnet-20241022", "llama3"
LLM_API_KEY = os.environ.get("OPENAI_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")  # For Ollama or other providers


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


def generate_design_system_llm(context: str) -> str:
    """Generates a properly formatted DESIGN.md file from the project context."""
    
    prompt = f"""You are a Lead UI/UX Designer. You must create a Design System based on the product context.

## Project Context
{context[:4000]}

## Instructions
Generate a complete `DESIGN.md` file. The file must RIGOROUSLY follow this format:
1. A YAML block at the top enclosed between `---` with design tokens.
2. A Markdown section below the YAML block explaining the visual philosophy.

Choose colors, fonts, and spacing that fit PERFECTLY the sector and audience of the project (e.g., B2B, consumer, medical, playful, etc.).

Use this exact schema for YAML:
---
version: "alpha"
name: "System Name"
colors:
  primary: "#..."
  secondary: "#..."
  tertiary: "#..."
  neutral: "#..."
  surface: "#..."
  text-main: "#..."
typography:
  h1:
    fontFamily: "..."
    fontSize: "..."
    fontWeight: "..."
  body:
    fontFamily: "..."
    fontSize: "..."
    fontWeight: "..."
rounded:
  sm: "..."
  md: "..."
spacing:
  sm: "..."
  md: "..."
components:
  button-primary:
    backgroundColor: "{{{{colors.primary}}}}"
    textColor: "#ffffff"
    rounded: "{{{{rounded.md}}}}"
---

Respond ONLY with the file content (YAML + Markdown), without introducing with phrases like "Here is the file".
"""

    system_prompt = "You are a Design Systems Architect. You generate DESIGN.md files with precise tokens."
    
    try:
        response = call_llm(prompt, system_prompt, max_tokens=2048)
        # Clean up any markdown blocks if the LLM adds them
        response = response.strip()
        if response.startswith("```markdown"):
            response = response[11:]
        if response.endswith("```"):
            response = response[:-3]
        return response.strip()
    except Exception as e:
        print(f"  ⚠️  Error generating Design System: {e}")
        return ""


def call_llm(prompt: str, system_prompt: str = "", max_tokens: int = 4096) -> str:
    """Calls the configured LLM and returns the response."""
    if LLM_PROVIDER == "openai":
        return _call_openai(prompt, system_prompt, max_tokens)
    elif LLM_PROVIDER == "anthropic":
        return _call_anthropic(prompt, system_prompt, max_tokens)
    elif LLM_PROVIDER == "ollama":
        return _call_ollama(prompt, system_prompt, max_tokens)
    elif LLM_PROVIDER == "dashscope":
        return _call_dashscope(prompt, system_prompt, max_tokens)
    else:
        raise ValueError(f"Unsupported LLM provider: {LLM_PROVIDER}")


def _call_openai(prompt: str, system_prompt: str, max_tokens: int) -> str:
    """Calls OpenAI API."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL or None)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.7,
        )
        return response.choices[0].message.content
    except ImportError:
        print("❌ Install openai: pip install openai")
        sys.exit(1)
    except Exception as e:
        print(f"❌ OpenAI Error: {e}")
        sys.exit(1)


def _call_anthropic(prompt: str, system_prompt: str, max_tokens: int) -> str:
    """Calls Anthropic API."""
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=LLM_API_KEY)
        
        response = client.messages.create(
            model=LLM_MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except ImportError:
        print("❌ Install anthropic: pip install anthropic")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Anthropic Error: {e}")
        sys.exit(1)


def _call_ollama(prompt: str, system_prompt: str, max_tokens: int) -> str:
    """Calls Ollama API (local)."""
    try:
        import requests
        url = LLM_BASE_URL or "http://localhost:11434"
        payload = {
            "model": LLM_MODEL,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.7,
            }
        }
        response = requests.post(f"{url}/api/generate", json=payload, timeout=120)
        response.raise_for_status()
        return response.json().get("response", "")
    except ImportError:
        print("❌ Install requests: pip install requests")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Ollama Error: {e}")
        sys.exit(1)


def _call_dashscope(prompt: str, system_prompt: str, max_tokens: int) -> str:
    """Calls DashScope API (Alibaba Cloud)."""
    try:
        from openai import OpenAI
        base_url = LLM_BASE_URL or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        client = OpenAI(api_key=LLM_API_KEY, base_url=base_url)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        response = client.chat.completions.create(
            model=LLM_MODEL or "qwen-plus",
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.7,
        )
        return response.choices[0].message.content
    except ImportError:
        print("❌ Install openai: pip install openai")
        sys.exit(1)
    except Exception as e:
        print(f"❌ DashScope Error: {e}")
        sys.exit(1)


def generate_state_spec_llm(state_name: str, state_def: dict, machine: dict, context: str, spec: str, design_system: str = "") -> str:
    """Generates UI spec for a state using the LLM."""
    
    states_info = json.dumps({state_name: state_def}, indent=2)
    
    related = []
    for s_name, s_def in machine.get("states", {}).items():
        transitions = s_def.get("on", {})
        if state_name in transitions.values():
            event = [k for k, v in transitions.items() if v == state_name][0]
            related.append(f"- From {s_name} via event {event}")
        if state_name == s_name:
            for event, dest in transitions.items():
                related.append(f"- To {dest} via event {event}")
    
    # Design System instructions
    design_instructions = ""
    if design_system:
        design_instructions = f"""
## Design System (RIGID VISUAL RULES)
```markdown
{design_system}
```
CRITICAL INSTRUCTION: When listing "UI Components" and "UI Notes", you MUST use exclusively the design tokens (colors, spacing, typography, rounded, components) defined above.
Do NOT invent generic classes (e.g., do NOT say 'use a bg-blue-500', but use the color '{{{{colors.primary}}}}').
Reference component variants like `button-primary`, `button-success` etc. as defined in the components section.
"""
    
    prompt = f"""You are a Senior Product Manager and UI/UX Designer. Analyze the state machine state and generate a complete UI specification.

## Project Context
{context[:2000]}

## Functional Specification
{spec[:2000]}

{design_instructions}
## State to Analyze
```json
{states_info}
```

## Related Transitions
{chr(10).join(related) if related else 'No transitions found'}

## Entry/Exit Actions
Entry: {state_def.get('entry', [])}
Exit: {state_def.get('exit', [])}

## Instructions
Generate a complete Markdown file for state '{state_name}' that includes:

1. **Description** — What this screen/state shows to the user
2. **Context** — Where you come from and where you can go
3. **Required Data** — Table with fields, types, and descriptions (based on project context)
4. **UI Components** — List of visual components with type, elements, and interactions, clearly specifying the XSTATE MAPPING (e.g., "Continue" Button mapped to EVENT_X). Use design tokens from the Design System section.
5. **Constraints and Rules** — Business rules and technical constraints
6. **UI Notes** — Layout, colors, animations, patterns. Reference design tokens explicitly.
7. **User Flow** — Textual flow diagram

IMPORTANT:
- Be specific and concrete, based on the real project context
- Generate realistic mock data
- The file must be ready to be used by an AI UI generator (like v0 or Claude).
- When describing visual elements, ALWAYS reference the design tokens from the Design System section.
"""

    system_prompt = "You are a UI/UX specification expert. You generate detailed technical documentation ready for implementation."
    return call_llm(prompt, system_prompt)


def discover_screens_llm(machine: dict, context: str, spec: str) -> list:
    """Uses the LLM to discover which screens to generate based on context."""
    
    states_info = json.dumps(machine.get("states", {}), indent=2)
    
    prompt = f"""You are a Senior Product Manager. Analyze the project context and state machine to determine which real screens (views) to generate.

## Project Context
{context[:3000]}

## Functional Specification
{spec[:3000]}

## Machine States
```json
{states_info}
```

## Instructions
Identify the physical screens of the product (e.g., Login, Dashboard). For each screen, indicate:
1. Screen name (e.g., "01_login")
2. Which abstract states of the machine are enclosed or related to this screen

Respond ONLY with a valid JSON array. Example:
[
  {{"name": "01_login", "states": ["app_idle", "authenticating", "session_expired"]}},
  {{"name": "02_dashboard", "states": ["dashboard_ready", "loading_dashboard"]}}
]
Do not add markdown like ```json, just print the array.
"""
    
    system_prompt = "You are a functional analyst. Respond strictly with pure JSON."
    
    try:
        response = call_llm(prompt, system_prompt, max_tokens=2048)
        import re
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if json_match:
            screens = json.loads(json_match.group())
            print(f"  🧠 LLM identified {len(screens)} screens:")
            for s in screens:
                print(f"     - {s['name']}: {', '.join(s['states'])}")
            return screens
        else:
            raise ValueError("JSON not found")
    except Exception as e:
        print(f"  ⚠️  discover_screens error: {e}, using default fallback")
        return [
            {"name": "01_login", "states": ["app_idle", "loading_auth", "error_auth", "session_expired", "access_denied"]},
            {"name": "02_dashboard", "states": ["dashboard_ready", "loading_dashboard", "empty", "general_error", "loading"]},
            {"name": "03_catalog", "states": ["catalog_ready", "loading_catalog"]},
            {"name": "04_offers", "states": ["offers_ready", "loading_offers", "group_in_progress"]},
            {"name": "05_benchmark", "states": ["benchmark_ready", "loading_benchmark"]}
        ]


def generate_screen_spec_llm(screen_name: str, related_states: list, machine: dict, context: str, spec: str, design_system: str = "") -> str:
    """Generates UI spec for a real screen using the LLM."""
    
    states_info = {state_name: machine["states"][state_name] for state_name in related_states if state_name in machine.get("states", {})}
    
    # Design System instructions
    design_instructions = ""
    if design_system:
        design_instructions = f"""
## Design System (RIGID VISUAL RULES)
```markdown
{design_system}
```
CRITICAL INSTRUCTION: When listing "UI Components" and "Notes for AI Generators", you MUST use exclusively the design tokens (colors, spacing, typography, rounded, components) defined above.
Do NOT invent generic classes. Reference component variants like `button-primary`, `button-success` etc. as defined in the components section.
"""
    
    prompt = f"""You are a Senior Product Manager and UI/UX Designer. Analyze these states and generate a complete UI specification for the final screen.

## Project Context
{context[:3000]}

## Screen to Generate
{screen_name}

{design_instructions}
## Related Machine States
```json
{json.dumps(states_info, indent=2)}
```

## Instructions
Generate a complete Markdown file for screen '{screen_name}' that includes:
1. **Description and Context**
2. **Required Data** — Realistic mock data.
3. **UI Components** — Component list. RIGIDLY map each button/action to the corresponding XState event. Use design tokens from the Design System section.
4. **UI States** — How the screen appears during loading, error, or empty states, based on the related states provided.
5. **Notes for AI Generators (v0 / Claude)** — Specific style instructions. Reference design tokens explicitly (e.g., "Use {{{{colors.primary}}}} for primary actions").

The file must be ready for copy-paste into v0.dev.
"""

    system_prompt = "You are a UI/UX expert. Create Markdown Blueprints."
    return call_llm(prompt, system_prompt)


def generate_index_llm(states: dict, screens: list, machine: dict) -> str:
    """Generates the README.md index using the LLM."""
    states_list = ", ".join([f"`{s}`" for s in states.keys()])
    screens_list = ", ".join([f"`{s}`" for s in screens])
    
    prompt = f"""Generate an index README.md file for this UI Kit.
Machine States: {states_list}
Screens Created: {screens_list}

Include:
1. Title and intro
2. Screen Mapping
3. Instructions on how to use the Markdown files with v0.dev or Claude Artifacts to generate frontend code.
"""
    system_prompt = "You are a technical writer."
    return call_llm(prompt, system_prompt)


def _extract_plantuml_targets(target) -> list:
    """Extract target state names for PlantUML generation."""
    if isinstance(target, str):
        return [target]
    elif isinstance(target, dict):
        t = target.get("target", "")
        return [t] if t else []
    elif isinstance(target, list):
        targets = []
        for item in target:
            if isinstance(item, dict):
                t = item.get("target", "")
                if t:
                    targets.append(t)
            elif isinstance(item, str):
                targets.append(item)
        return targets
    return []


def generate_plantuml(machine: dict) -> str:
    """Generates PlantUML flat syntax code."""
    uml = "@startuml\n"
    uml += "skinparam state {\n"
    uml += "  BackgroundColor #E8F5E9\n"
    uml += "  BorderColor #2E7D32\n"
    uml += "  ArrowColor #1B5E20\n"
    uml += "}\n\n"
    
    initial = machine.get("initial", "")
    if initial:
        uml += f"[*] --> {initial}\n\n"
    
    # Flat Syntax: States first
    for state_name, state_def in machine.get("states", {}).items():
        uml += f"state {state_name}\n"
        
    uml += "\n' Transitions\n"
    
    # Flat Syntax: Then arrows
    for state_name, state_def in machine.get("states", {}).items():
        transitions = state_def.get("on", {})
        for event, target in transitions.items():
            for dest in _extract_plantuml_targets(target):
                uml += f"{state_name} --> {dest} : {event}\n"
    
    uml += "@enduml"
    return uml


def main():
    import argparse
    
    global LLM_PROVIDER, LLM_MODEL, LLM_API_KEY, LLM_BASE_URL
    
    parser = argparse.ArgumentParser(description="Dynamically generate UI specifications with LLM")
    parser.add_argument("--machine", default="output/spec/spec_machine.json", help="Path to spec_machine.json")
    parser.add_argument("--context", default="output/context/project_context.md", help="Path to project_context.md")
    parser.add_argument("--spec", default="output/spec/spec.md", help="Path to spec.md")
    parser.add_argument("--output-dir", default="output/ui_specs", help="Output directory")
    parser.add_argument("--provider", choices=["openai", "anthropic", "ollama", "dashscope"], default=LLM_PROVIDER, help="LLM Provider")
    parser.add_argument("--model", default=LLM_MODEL, help="LLM Model")
    parser.add_argument("--api-key", default=LLM_API_KEY, help="LLM API Key")
    parser.add_argument("--base-url", default=LLM_BASE_URL, help="LLM Base URL")
    parser.add_argument("--states-only", action="store_true", help="Generate only states")
    parser.add_argument("--screens-only", action="store_true", help="Generate only screens")
    parser.add_argument("--design", default="output/ui_specs/DESIGN.md", help="Path to Design System file")
    parser.add_argument("--force-design", action="store_true", help="Force regeneration of DESIGN.md even if it exists")
    args = parser.parse_args()
    
    LLM_PROVIDER = args.provider
    LLM_MODEL = args.model
    LLM_API_KEY = args.api_key or LLM_API_KEY
    LLM_BASE_URL = args.base_url or LLM_BASE_URL
    
    if not LLM_API_KEY and LLM_PROVIDER != "ollama":
        print("❌ Set LLM_API_KEY or OPENAI_API_KEY")
        sys.exit(1)
    
    print(f"🤖 Configuration: Provider={LLM_PROVIDER} | Model={LLM_MODEL}")
    
    # Load context first (needed for design system generation)
    context = load_context(args.context)
    
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