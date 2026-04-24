"""
Spec generator - generates UI specifications using LLM.
"""

import json
import re

from pipeline.ui_generator.llm_client import call_llm


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
        response = response.strip()
        if response.startswith("```markdown"):
            response = response[11:]
        if response.endswith("```"):
            response = response[:-3]
        return response.strip()
    except Exception as e:
        print(f"  ⚠️  Error generating Design System: {e}")
        return ""


def generate_state_spec_llm(
    state_name: str, 
    state_def: dict, 
    machine: dict, 
    context: str, 
    spec: str, 
    design_system: str = ""
) -> str:
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
        print(f"  ⚠️  discover_screens error: {e}, using dynamic fallback based on actual machine states")
        all_states = list(machine.get("states", {}).keys())
        auth_states = [s for s in all_states if any(k in s.lower() for k in ["idle", "auth", "session", "expired"])]
        loading_states = [s for s in all_states if "loading" in s.lower() or s == "initial"]
        error_states = [s for s in all_states if any(k in s.lower() for k in ["error", "empty"])]
        
        # Consider any state that is not auth, loading, or error as a content state
        content_states = [s for s in all_states if s not in auth_states and s not in loading_states and s not in error_states]
        
        fallback = []
        if auth_states:
            fallback.append({"name": "01_auth", "states": auth_states})
        if loading_states:
            fallback.append({"name": "02_loading", "states": loading_states})
        if content_states:
            fallback.append({"name": "03_content", "states": content_states})
        if error_states:
            fallback.append({"name": "04_errors", "states": error_states})
        
        if not fallback:
            fallback.append({"name": "01_main", "states": all_states})
        
        return fallback


def _flatten_states(states: dict) -> dict:
    """Flattens nested states into a single dict with dot-notation keys."""
    flat = {}
    for name, defn in states.items():
        flat[name] = defn
        if "states" in defn:
            for sub_name, sub_defn in defn["states"].items():
                flat[f"{name}.{sub_name}"] = sub_defn
    return flat


def generate_screen_spec_llm(
    screen_name: str, 
    related_states: list, 
    machine: dict, 
    context: str, 
    spec: str, 
    design_system: str = ""
) -> str:
    """Generates UI spec for a real screen using the LLM."""
    
    all_states = _flatten_states(machine.get("states", {}))
    states_info = {state_name: all_states[state_name] for state_name in related_states if state_name in all_states}
    
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