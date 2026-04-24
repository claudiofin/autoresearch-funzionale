"""
Spec generator for automatic functional analysis.

Reads project_context.md and generates spec.md with PlantUML diagrams and XState state machine.

ITERATIVE APPROACH:
- Iteration 1: generate from scratch
- Subsequent iterations: modify existing machine based on:
  - Analyst suggestions (missing states/transitions)
  - Critic feedback (critical issues to fix)
  - Validator errors (dead-end states, unreachable states)

Usage:
    python run.py spec --context output/context/project_context.md
    
Environment Variables:
    LLM_API_KEY: Your API key (REQUIRED)
    LLM_PROVIDER: Provider (openai, anthropic, google, dashscope)
    LLM_BASE_URL: Base API URL (optional, override)
    LLM_MODEL: Model to use (optional, override)
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import LLM_CONFIG, DEFAULT_PROVIDER

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TIME_BUDGET = 300

# ---------------------------------------------------------------------------
# XState State Machine Generator
# ---------------------------------------------------------------------------

def generate_base_machine() -> dict:
    """Generate an empty base state machine."""
    return {
        "id": "appFlow",
        "initial": "app_idle",
        "context": {"user": None, "errors": [], "retryCount": 0},
        "states": {}
    }


# ---------------------------------------------------------------------------
# PlantUML Diagram Generators
# ---------------------------------------------------------------------------

def generate_plantuml_statechart(machine: dict) -> str:
    """Convert XState machine to PlantUML state diagram (hierarchical layout)."""
    lines = ["@startuml", ""]
    
    def _render_states(states: dict, indent: str = "    ") -> list:
        out = []
        for state_name, state_config in states.items():
            entry_actions = state_config.get("entry", [])
            exit_actions = state_config.get("exit", [])
            sub_states = state_config.get("states", {})
            
            note_lines = []
            if entry_actions:
                note_lines.append(f'{indent}    note: Entry: {", ".join(entry_actions)}')
            if exit_actions:
                note_lines.append(f'{indent}    note: Exit: {", ".join(exit_actions)}')
                
            if sub_states:
                out.append(f'{indent}state "{state_name}" {{')
                for note in note_lines:
                    out.append(note)
                initial_sub = state_config.get("initial", "")
                if initial_sub:
                    out.append(f'{indent}    [*] --> {initial_sub}')
                out.extend(_render_states(sub_states, indent + "    "))
                out.append(f'{indent}}}')
            else:
                if note_lines:
                    out.append(f'{indent}state "{state_name}" {{')
                    for note in note_lines:
                        out.append(note)
                    out.append(f'{indent}}}')
                else:
                    out.append(f'{indent}state "{state_name}"')
        return out

    def _render_transitions(states: dict, indent: str = "    ") -> list:
        out = []
        for state_name, state_config in states.items():
            transitions = state_config.get("on", {})
            for event, target in transitions.items():
                if isinstance(target, dict):
                    target_state = target.get("target", "unknown").lstrip('.')
                    guard = target.get("guard", "") or target.get("cond", "")
                    if guard:
                        out.append(f"{indent}{state_name} --> {target_state} : {event} [{guard}]")
                    else:
                        out.append(f"{indent}{state_name} --> {target_state} : {event}")
                elif isinstance(target, str):
                    target_state = target.lstrip('.')
                    out.append(f"{indent}{state_name} --> {target_state} : {event}")
                elif isinstance(target, list):
                    for t in target:
                        target_state = t.get("target", "unknown").lstrip('.') if isinstance(t, dict) else t.lstrip('.')
                        guard = t.get("cond", "") if isinstance(t, dict) else ""
                        if guard:
                            out.append(f"{indent}{state_name} --> {target_state} : {event} [{guard}]")
                        else:
                            out.append(f"{indent}{state_name} --> {target_state} : {event}")
            
            if "states" in state_config:
                out.extend(_render_transitions(state_config["states"], indent))
        return out

    if machine.get("initial"):
        lines.append(f'    [*] --> {machine["initial"]}')
    lines.append("")
    
    lines.extend(_render_states(machine.get("states", {})))
    lines.append("")
    lines.extend(_render_transitions(machine.get("states", {})))
    
    # Final states
    lines.extend(["", "    [*] <-- cancelled", "    [*] <-- success", "@enduml"])
    return "\n".join(lines)


def generate_plantuml_sequence(flows: list) -> str:
    """Generate PlantUML sequence diagrams from actual flows."""
    if not flows:
        lines = [
            "@startuml", "",
            "participant User", "participant Interface", "participant Backend", "participant Database", "",
            "User -> Interface: START",
            "Interface -> Interface: showLoadingIndicator()",
            "Interface -> Backend: Request", "",
            "alt Success",
            "    Backend --> Interface: 200 OK",
            "    Interface -> Interface: showSuccessMessage()",
            "    Interface --> User: Display Result",
            "else Error",
            "    Backend --> Interface: 4xx/5xx Error",
            "    Interface -> Interface: showErrorMessage()",
            "    Interface --> User: Display Error",
            "else Timeout",
            "    Interface -> Interface: showTimeoutMessage()",
            "    Interface --> User: Display Timeout",
            "end", "", "@enduml"
        ]
        return "\n".join(lines)
    
    all_diagrams = []
    for flow in flows:
        lines = ["@startuml", "", f"== {flow['name'].replace('_', ' ').title()} ==", ""]
        lines.extend([
            "participant User", "participant Interface", "participant Backend", "participant Database", ""
        ])
        
        steps = flow.get("steps", [])
        for i, step in enumerate(steps):
            trigger = step.get("trigger", "")
            action = step.get("action", "")
            outcome = step.get("expected_outcome", "")
            error = step.get("error_scenario", "")
            
            if i == 0:
                lines.append(f"User -> Interface: {trigger}")
            else:
                lines.append(f"User -> Interface: {trigger}")
            
            if "POST" in action or "GET" in action or "PUT" in action or "DELETE" in action:
                lines.append(f"Interface -> Backend: {action}")
                lines.append(f"Backend -> Database: query")
                lines.append(f"Database --> Backend: result")
            
            if error:
                lines.append(f"")
                lines.append(f"alt Success")
                lines.append(f"    Backend --> Interface: {outcome}")
                lines.append(f"    Interface --> User: Display Result")
                lines.append(f"else Error")
                lines.append(f"    Backend --> Interface: {error}")
                lines.append(f"    Interface --> User: Show Error")
                lines.append(f"end")
            else:
                lines.append(f"    Backend --> Interface: {outcome}")
                lines.append(f"    Interface --> User: Display Result")
            
            lines.append("")
        
        lines.append("@enduml")
        all_diagrams.append("\n".join(lines))
    
    return "\n\n".join(all_diagrams)


# ---------------------------------------------------------------------------
# LLM Client - ITERATIVE APPROACH
# ---------------------------------------------------------------------------

def call_llm_spec(context_text: str, analyst_suggestions: dict = None, 
                  existing_machine: dict = None, critic_feedback: dict = None,
                  max_retries: int = 3) -> dict:
    """Call the LLM to generate/modify the functional specification.
    
    ITERATIVE APPROACH:
    - If an existing machine exists, pass it to the LLM
    - The LLM must MODIFY the machine, not regenerate it
    - Analyst suggestions indicate what to add
    - Critic feedback indicates what to fix
    """
    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key:
        print("❌ ERROR: LLM_API_KEY is not set.")
        sys.exit(1)
    
    provider = os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER)
    
    if provider in LLM_CONFIG:
        base_url = os.getenv("LLM_BASE_URL", LLM_CONFIG[provider]["base_url"])
        model = os.getenv("LLM_MODEL", LLM_CONFIG[provider]["model"])
    else:
        base_url = os.getenv("LLM_BASE_URL")
        model = os.getenv("LLM_MODEL")
        if not base_url or not model:
            print(f"❌ ERROR: Provider '{provider}' not recognized.")
            sys.exit(1)
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
    except ImportError:
        print("❌ ERROR: openai not installed.")
        sys.exit(1)
    
    # Truncate context
    max_context = 4000
    if len(context_text) > max_context:
        lines = context_text.split("\n")
        important = [l for l in lines if l.startswith("##") or l.startswith("###") or l.startswith("-") or l.startswith("|")]
        context_text = "\n".join(important[:100])
        if len(context_text) > max_context:
            context_text = context_text[:max_context]
    
    # Build existing machine section (if any)
    existing_section = ""
    if existing_machine:
        existing_states = list(existing_machine.get("states", {}).keys())
        existing_transitions = []
        for state_name, state_config in existing_machine.get("states", {}).items():
            for event, target in state_config.get("on", {}).items():
                existing_transitions.append(f"    {state_name} --{event}--> {target}")
        
        existing_section = f"""

EXISTING STATE MACHINE (DO NOT REMOVE STATES, ONLY ADD/FIX):
Current states ({len(existing_states)}): {', '.join(existing_states[:20])}
Current transitions ({len(existing_transitions)}):
{chr(10).join(existing_transitions[:30])}

INSTRUCTIONS:
- KEEP all existing states
- ADD new states from analyst suggestions
- FIX transitions to resolve dead-end states
- NEVER remove an existing state
"""
    
    # Build analyst suggestions section
    suggestions_section = ""
    if analyst_suggestions:
        states = analyst_suggestions.get("states", [])
        transitions = analyst_suggestions.get("transitions", [])
        edge_cases = analyst_suggestions.get("edge_cases", [])
        events = analyst_suggestions.get("events", [])
        suggestions_section = f"""

ANALYST SUGGESTIONS (YOU MUST INCLUDE THESE):
- {len(states)} suggested states: {', '.join(s['name'] for s in states[:15])}
- {len(transitions)} suggested transitions
- {len(edge_cases)} edge cases to handle
- {len(events)} events to support: {', '.join(e['name'] for e in events[:10])}

REQUIRED ACTIONS:
1. Add ALL suggested states that don't already exist
2. Add suggested transitions
3. Handle edge cases with appropriate error states
"""
    
    # Build critic feedback section
    critic_section = ""
    if critic_feedback:
        critical = critic_feedback.get("summary", {}).get("critical_issues", [])
        if critical:
            critic_section = f"""

CRITICAL ISSUES TO FIX (HIGH PRIORITY):
{chr(10).join(f'- {c}' for c in critical[:10])}

REQUIRED ACTIONS:
- Fix EVERY critical issue above
- Add exit transitions for dead-end states
- Connect unreachable states to the initial state
"""
    
    # Determine if iterative or from scratch
    is_iterative = existing_machine is not None and len(existing_machine.get("states", {})) > 0
    
    if is_iterative:
        task = "MODIFY the existing state machine. DO NOT regenerate from scratch."
    else:
        task = "Generate a new state machine from the context."
    
    # Build prompt using concatenation to avoid f-string nesting limit
    prompt = task + """

Project context:
""" + context_text + existing_section + suggestions_section + critic_section + """

Respond ONLY with valid JSON:

{
  "states": [{"name": "snake_case", "description": "...", "entry_actions": [], "exit_actions": [], "sub_states": [], "initial_sub_state": null}],
  "transitions": [{"from_state": "...", "to_state": "...", "event": "UPPER_CASE", "guard": null}],
  "edge_cases": [{"id": "EC001", "scenario": "...", "trigger": "...", "expected_behavior": "...", "priority": "high"}],
  "flows": [{"name": "...", "steps": [{"trigger": "...", "action": "...", "expected_outcome": "...", "error_scenario": "..."}]}],
  "api_endpoints": [{"method": "GET", "path": "...", "description": "..."}],
  "error_handling": [{"code": 404, "type": "Not Found", "message": "User friendly message", "action": "Return home"}],
  "data_validation": [{"field": "email", "type": "string", "required": true, "pattern": "RFC 5322", "max_length": 254}]
}

Rules:
1. 100% valid JSON - no text outside
2. snake_case for states, UPPER_CASE for events
3. Use CONSOLIDATED events: ON_SUCCESS, ON_ERROR, CANCEL (not multiple variants like DATA_LOADED, DATA_FETCHED, FETCH_ERROR, etc.)
4. ON_SUCCESS transition: use guard "hasData" to go to "success" if data exists, otherwise to "empty"
5. ON_ERROR transition: single event for all error types (network, timeout, server error)
6. CANCEL transition: use guard "hasPreviousState" to return to previous state (e.g., success during refresh), otherwise to app_idle
7. RETRY_FETCH in error state: MUST have guard "canRetry" (context.retryCount < 3)
8. When retry fails, use assign action to increment retryCount
9. After 3 failed retries, transition to "session_expired" or "max_retries_exceeded" state
10. Cover: auth, core flow, error handling, empty states
11. Initial state: app_idle (MUST exist)
12. Every state must have at least one exit transition (no dead-end)
13. All states must be reachable from app_idle
14. HIERARCHICAL STATES: The "success" state MUST be hierarchical (nested). Analyze the project context and create a sub-state for each main area/screen of the app (e.g., for e-commerce: catalog, cart, profile; for some app: dashboard, catalog, offers, benchmark, groups). Each sub-state should have navigation events to other sub-states (e.g., NAVIGATE_CATALOGO, NAVIGATE_OFFERTE). This allows the UI generator to create separate screen files for each area.

15. NO DUPLICATE STATES: Never create two sets of states for the same screens.
    If you create "dashboard", "catalog", "offers" as sub-states of "success",
    DO NOT also create "success_dashboard", "success_catalog", "success_offerte".
    Use ONLY the short names. Each screen = exactly ONE state.

16. app_idle IS A RESTING STATE — use START_APP event:
    DO NOT put checkAuth, validateCredentials, or any automatic action in app_idle's "entry".
    Instead, app_idle MUST listen for a "START_APP" event that triggers initial setup:
      "on": { "START_APP": "authenticating" }
    The UI layer is responsible for firing START_APP when the app is ready.
    This prevents infinite loops: app_idle → checkAuth fails → login → cancel → app_idle → ...

17. CLUSTERING MUST BE A SUB-STATE with error exit:
    If the app has a "clustering" or "calculation" feature inside a page (e.g., Benchmark),
    it MUST be a sub-state of that page: success.benchmark.clustering_calculation.
    
    CRITICAL: Every nested sub-state MUST define an exit path to "error".
    Either inherit from parent or define explicitly:
      "on": { "ON_ERROR": ".." }  (goes to parent's error handler)
    Deep nesting without error exit = broken state machine.

CRITICAL - DO NOT USE THESE REDUNDANT EVENTS (use the consolidated alternatives):
- DATA_LOADED, DATA_FETCHED -> use ON_SUCCESS (with guard "hasData")
- FETCH_ERROR, FETCH_FAILED, TIMEOUT, TIMEOUT_FETCH, ERROR -> use ON_ERROR
- CANCEL_FETCH -> use CANCEL (with guard "hasPreviousState")
- RETRY (without guard) -> use RETRY_FETCH with cond "canRetry"

EXAMPLE - loading state transitions (follow this pattern):
  In the "transitions" array, you MUST generate BOTH branches for every conditional event:
  - {"from_state": "loading", "to_state": "success", "event": "ON_SUCCESS", "guard": "hasData"}
  - {"from_state": "loading", "to_state": "empty", "event": "ON_SUCCESS", "guard": "!hasData"}
  - {"from_state": "loading", "to_state": "error", "event": "ON_ERROR"}
  - {"from_state": "loading", "to_state": "success", "event": "CANCEL", "guard": "hasPreviousState"}
  - {"from_state": "loading", "to_state": "app_idle", "event": "CANCEL", "guard": "!hasPreviousState"}

EXAMPLE - error state transitions (follow this pattern):
  - {"from_state": "error", "to_state": "loading", "event": "RETRY_FETCH", "guard": "canRetry", "actions": ["incrementRetryCount"]}
  - {"from_state": "error", "to_state": "session_expired", "event": "RETRY_FETCH", "guard": "!canRetry"}
  - {"from_state": "error", "to_state": "app_idle", "event": "CANCEL"}

CRITICAL RULE - BOTH BRANCHES ARE MANDATORY:
For EVERY event with a guard condition, you MUST generate TWO transitions in the "transitions" array:
1. The positive branch (guard: "hasData", "canRetry", "hasPreviousState")
2. The negative branch (guard: "!hasData", "!canRetry", "!hasPreviousState")
Missing either branch = INVALID state machine. You will be penalized for incomplete transitions.

PRE-GENERATION CHECKLIST (verify before outputting JSON):
- [ ] ON_SUCCESS has TWO entries: one with guard "hasData" → success, one with guard "!hasData" → empty
- [ ] CANCEL has TWO entries: one with guard "hasPreviousState" → success, one with guard "!hasPreviousState" → app_idle
- [ ] RETRY_FETCH has TWO entries: one with guard "canRetry" → loading, one with guard "!canRetry" → session_expired
- [ ] Every conditional event appears EXACTLY TWICE in the transitions array (once positive, once negative)

IF YOU MISS ANY BRANCH, THE STATE MACHINE IS BROKEN AND THE USER WILL LOSE DATA.
This is not a suggestion - it is a REQUIREMENT. Generate BOTH branches for every conditional event.

TRANSITION FORMAT:
- Simple: EVENT -> target_state
- With guard: EVENT with cond guardName -> target_state
- With actions: EVENT with actions [actionName] -> target_state
- With guard and actions: EVENT with cond guardName and actions [actionName] -> target_state
"""
    
    print(f"  🤖 Calling LLM for spec ({model}), context: {len(context_text)} chars...")
    if existing_machine:
        print(f"  📦 Existing machine: {len(existing_machine.get('states', {}))} states")
    
    for attempt in range(max_retries):
        try:
            print(f"  Attempt {attempt + 1}/{max_retries}...")
            response = client.chat.completions.create(
                timeout=180,
                model=model,
                messages=[
                    {"role": "system", "content": "You are an expert Product Manager specializing in state machines. Respond ONLY with valid JSON. Start with { and end with }. No markdown, no extra text."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=8192,  # Increased to handle larger machines
            )
            
            content = response.choices[0].message.content.strip()
            
            # Extract JSON
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            start = content.find("{")
            end = content.rfind("}")
            if start >= 0 and end > start:
                content = content[start:end+1]
            
            data = json.loads(content)
            print(f"  ✅ LLM returned {len(json.dumps(data))} chars of valid JSON")
            return data
            
        except json.JSONDecodeError as e:
            print(f"  Attempt {attempt + 1} failed (invalid JSON): {e}")
            try:
                start = content.find("{")
                end = content.rfind("}")
                if start >= 0 and end > start:
                    partial = content[start:end+1]
                    data = json.loads(partial)
                    print(f"  ✅ JSON extracted: {len(partial)} chars")
                    return data
            except:
                pass
            continue
        except Exception as e:
            print(f"  Attempt {attempt + 1} failed: {e}")
            continue
    
    print("❌ ERROR: All LLM attempts failed.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Post-Processing: Complete Missing Transition Branches
# ---------------------------------------------------------------------------

def _complete_missing_branches(machine: dict) -> dict:
    """Ensure every conditional event has BOTH positive and negative branches.
    
    The LLM often generates only the negative branch (e.g., "!hasData" → empty)
    but forgets the positive branch (e.g., "hasData" → success). This function
    detects missing branches and adds them automatically.
    """
    # Define expected branch pairs for known conditional events
    BRANCH_RULES = {
        "ON_SUCCESS": {
            "positive_guard": "hasData",
            "positive_target": "success",
            "negative_guard": "!hasData",
            "negative_target": "empty",
        },
        "CANCEL": {
            "positive_guard": "hasPreviousState",
            "positive_target": "success",
            "negative_guard": "!hasPreviousState",
            "negative_target": "app_idle",
        },
        "RETRY_FETCH": {
            "positive_guard": "canRetry",
            "positive_target": "loading",
            "negative_guard": "!canRetry",
            "negative_target": "session_expired",
        },
    }
    
    all_states = machine.get("states", {})
    fixed_count = 0
    
    for state_name, state_config in all_states.items():
        on_events = state_config.get("on", {})
        
        for event_name, rule in BRANCH_RULES.items():
            if event_name not in on_events:
                continue
            
            # Get existing transition(s) for this event
            existing = on_events[event_name]
            
            # Normalize to list of transitions
            if isinstance(existing, str):
                # Simple transition without guard - skip (no conditional)
                continue
            elif isinstance(existing, dict):
                existing_list = [existing]
            elif isinstance(existing, list):
                existing_list = existing
            else:
                continue
            
            # Check which guards exist
            existing_guards = set()
            for t in existing_list:
                if isinstance(t, dict):
                    guard = t.get("cond", "") or t.get("guard", "")
                    if guard:
                        existing_guards.add(guard)
            
            # Check if positive branch is missing
            if rule["positive_guard"] not in existing_guards:
                # Add positive branch
                if isinstance(existing, dict):
                    # Convert single transition to list
                    on_events[event_name] = [existing]
                    existing_list = on_events[event_name]
                elif isinstance(existing, str):
                    on_events[event_name] = [
                        {"target": existing},
                        {"target": rule["positive_target"], "cond": rule["positive_guard"]}
                    ]
                    fixed_count += 1
                    continue
                
                on_events[event_name].append({
                    "target": rule["positive_target"],
                    "cond": rule["positive_guard"]
                })
                fixed_count += 1
                print(f"  🔧 Added missing positive branch: {state_name} --{event_name}[{rule['positive_guard']}]-> {rule['positive_target']}")
            
            # Check if negative branch is missing
            if rule["negative_guard"] not in existing_guards:
                if isinstance(on_events[event_name], dict):
                    on_events[event_name] = [on_events[event_name]]
                
                on_events[event_name].append({
                    "target": rule["negative_target"],
                    "cond": rule["negative_guard"]
                })
                fixed_count += 1
                print(f"  🔧 Added missing negative branch: {state_name} --{event_name}[{rule['negative_guard']}]-> {rule['negative_target']}")
    
    if fixed_count > 0:
        print(f"  ✅ Fixed {fixed_count} missing transition branches")
    
    return machine


# ---------------------------------------------------------------------------
# Post-Processing: Clean Unreachable States
# ---------------------------------------------------------------------------

def _clean_unreachable_states(machine: dict) -> dict:
    """Remove unreachable states and XState keywords used as state names.
    
    The LLM sometimes generates states like 'initial' (which is an XState keyword)
    or states that have no path from the initial state. This function cleans them up.
    """
    initial_state = machine.get("initial", "app_idle")
    all_states = machine.get("states", {})
    
    # XState reserved keywords that should never be state names
    XSTATE_KEYWORDS = {"initial", "states", "on", "entry", "exit", "context", "id", "type", "invoke", "activities"}
    
    # Remove XState keyword states
    for keyword in XSTATE_KEYWORDS:
        if keyword in all_states and keyword != initial_state:
            print(f"  🧹 Removing XState keyword state: '{keyword}'")
            del all_states[keyword]
    
    # BFS to find all reachable states from initial state
    reachable = set()
    queue = [initial_state]
    reachable.add(initial_state)
    
    while queue:
        current = queue.pop(0)
        if current not in all_states:
            continue
        state_config = all_states[current]
        
        # Check transitions
        for event, target in state_config.get("on", {}).items():
            if isinstance(target, str):
                target_name = target.lstrip('.')
                if target_name in all_states and target_name not in reachable:
                    reachable.add(target_name)
                    queue.append(target_name)
            elif isinstance(target, dict):
                target_name = target.get("target", "").lstrip('.')
                if target_name in all_states and target_name not in reachable:
                    reachable.add(target_name)
                    queue.append(target_name)
            elif isinstance(target, list):
                for t in target:
                    if isinstance(t, dict):
                        target_name = t.get("target", "").lstrip('.')
                    else:
                        target_name = str(t).lstrip('.')
                    if target_name in all_states and target_name not in reachable:
                        reachable.add(target_name)
                        queue.append(target_name)
        
        # Check sub-states
        sub_states = state_config.get("states", {})
        for sub_name in sub_states:
            if sub_name not in reachable:
                reachable.add(sub_name)
                queue.append(sub_name)
    
    # Remove unreachable states
    unreachable = set(all_states.keys()) - reachable
    for state_name in unreachable:
        print(f"  🧹 Removing unreachable state: '{state_name}'")
        del all_states[state_name]
    
    return machine


# ---------------------------------------------------------------------------
# Post-Processing: Validate No Critical Patterns (Rules 15, 16, 17)
# ---------------------------------------------------------------------------

def _validate_no_critical_patterns(machine: dict) -> list:
    """Validate the machine against critical rules 15, 16, 17.
    
    Returns a list of violation messages. Empty list = no violations.
    Messages are designed to be "speaking" — they tell the LLM exactly what's wrong.
    """
    violations = []
    all_states = machine.get("states", {})
    
    # --- Rule 15: No duplicate states (success_* vs *) ---
    success_state = all_states.get("success", {})
    success_sub_states = success_state.get("states", {})
    
    if success_sub_states:
        # Find all short names inside success
        short_names = set(success_sub_states.keys())
        # Check for success_* duplicates
        for sub_name in list(short_names):
            duplicate_name = f"success_{sub_name}"
            if duplicate_name in success_sub_states:
                violations.append(
                    f"VIOLAZIONE REGOLA 15: Hai creato stati duplicati '{duplicate_name}' e '{sub_name}' "
                    f"entrambi dentro 'success'. Usa SOLO il nome breve '{sub_name}'. "
                    f"Rimuovi '{duplicate_name}' e tutte le sue transizioni."
                )
    
    # Also check for success_* at top level (shouldn't exist)
    for state_name in all_states:
        if state_name.startswith("success_") and state_name != "success":
            short = state_name.replace("success_", "")
            violations.append(
                f"VIOLAZIONE REGOLA 15: Stato '{state_name}' trovato a livello top-level. "
                f"Se '{short}' è già un sotto-stato di 'success', usa SOLO quello. "
                f"Rimuovi '{state_name}'."
            )
    
    # --- Rule 16: No checkAuth in app_idle entry ---
    app_idle = all_states.get("app_idle", {})
    app_idle_entry = app_idle.get("entry", [])
    
    forbidden_idle_actions = {"checkAuth", "validateCredentials", "startAuthTimer", "showAuthLoader"}
    found_forbidden = forbidden_idle_actions.intersection(set(app_idle_entry))
    
    if found_forbidden:
        violations.append(
            f"VIOLAZIONE REGOLA 16: app_idle ha azioni automatiche nella 'entry': {', '.join(found_forbidden)}. "
            f"app_idle è uno stato di riposo — NON deve eseguire azioni automatiche. "
            f"Rimuovi {', '.join(found_forbidden)} dalla entry di app_idle. "
            f"Invece, aggiungi un evento START_APP: \"on\": {{ \"START_APP\": \"authenticating\" }}."
        )
    
    # --- Rule 17: clustering_calculation must be a sub-state, not top-level ---
    if "clustering_calculation" in all_states:
        violations.append(
            f"VIOLAZIONE REGOLA 17: 'clustering_calculation' è uno stato top-level. "
            f"Deve essere un sotto-stato della pagina dove avviene il calcolo (es. success.benchmark.clustering_calculation). "
            f"Spostalo dentro 'benchmark' come sotto-stato e assicurati che abbia un'uscita verso 'error' "
            f"(es. \"on\": {{ \"ON_ERROR\": \"..\" }})."
        )
    
    return violations


# ---------------------------------------------------------------------------
# Main Analysis Function - ITERATIVE APPROACH
# ---------------------------------------------------------------------------

def run_analysis(context_file: str, output_file: str, time_budget: int, 
                 analyst_suggestions: dict = None, 
                 existing_machine_file: str = None,
                 critic_feedback: dict = None) -> dict:
    """Run the functional analysis and generate spec.md.
    
    ITERATIVE APPROACH:
    1. Load existing machine (if exists)
    2. Pass it to the LLM with suggestions and critic feedback
    3. The LLM modifies the machine instead of regenerating it
    """
    
    start_time = time.time()
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Read context
    with open(context_file, "r", encoding="utf-8") as f:
        context_text = f.read()
    
    # Load existing machine (if any)
    existing_machine = None
    if existing_machine_file and os.path.exists(existing_machine_file):
        with open(existing_machine_file, "r", encoding="utf-8") as f:
            existing_machine = json.load(f)
        print(f"  📦 Existing machine loaded: {len(existing_machine.get('states', {}))} states")
    
    print(f"Context loaded: {len(context_text)} characters")
    if analyst_suggestions:
        print(f"  📋 Analyst suggestions: {len(analyst_suggestions.get('states', []))} states, {len(analyst_suggestions.get('transitions', []))} transitions")
    if critic_feedback:
        critical = critic_feedback.get("summary", {}).get("critical_issues", [])
        print(f"  🚨 Critic feedback: {len(critical)} critical issues")
    print("  🚀 Generating with LLM...")
    
    # Call LLM (iterative approach)
    try:
        llm_data = call_llm_spec(
            context_text, 
            analyst_suggestions=analyst_suggestions,
            existing_machine=existing_machine,
            critic_feedback=critic_feedback
        )
        print(f"  ✅ LLM: {len(llm_data.get('states', []))} states, {len(llm_data.get('transitions', []))} transitions")
    except Exception as e:
        print(f"❌ ERROR: LLM failed: {e}")
        print("   The system cannot work without an LLM.")
        sys.exit(1)
    
# ----- Helper: build a state config (flat or hierarchical) -----
def _build_state_config(state: dict) -> dict:
    """Build XState state config from LLM state dict.
    
    Supports hierarchical states: if 'sub_states' is present and non-empty,
    creates nested states with an 'initial' sub-state and navigation events.
    """
    config = {
        "entry": state.get("entry_actions", []),
        "exit": state.get("exit_actions", []),
        "on": {}
    }
    
    sub_states = state.get("sub_states", [])
    if sub_states:
        initial_sub = state.get("initial_sub_state") or sub_states[0]
        config["initial"] = initial_sub
        config["states"] = {}
        for sub in sub_states:
            sub_name = sub if isinstance(sub, str) else sub.get("name", "")
            sub_entry = [] if isinstance(sub, str) else sub.get("entry_actions", [])
            sub_exit = [] if isinstance(sub, str) else sub.get("exit_actions", [])
            config["states"][sub_name] = {
                "entry": sub_entry,
                "exit": sub_exit,
                "on": {}
            }
        # Auto-generate NAVIGATE events between sub-states
        for sub in sub_states:
            sub_name = sub if isinstance(sub, str) else sub.get("name", "")
            nav_event = f"NAVIGATE_{sub_name.upper()}"
            for other_sub in sub_states:
                other_name = other_sub if isinstance(other_sub, str) else other_sub.get("name", "")
                if other_name != sub_name:
                    config["states"][other_name]["on"][nav_event] = f".{sub_name}"
    
    return config

# ----- Helper: add transitions to machine -----
def _add_transitions(machine: dict, transitions: list):
    """Add transitions with support for guards and actions."""
    for trans in transitions:
        from_state = trans["from_state"]
        to_state = trans["to_state"]
        event = trans["event"]
        guard = trans.get("guard") or trans.get("cond")
        actions = trans.get("actions", [])
        
        # Resolve dot notation (e.g., success.dashboard -> parent='success', child='dashboard')
        target_dict = machine["states"]
        resolved_from = from_state
        if "." in from_state:
            parts = from_state.split(".")
            parent = parts[0]
            child = parts[1]
            if parent in machine["states"] and "states" in machine["states"][parent] and child in machine["states"][parent]["states"]:
                target_dict = machine["states"][parent]["states"]
                resolved_from = child
                if not to_state.startswith("."): # Make destination relative if not already
                     to_state = f".{to_state}" if not "." in to_state else to_state
        
        if resolved_from in target_dict:
            if guard or actions:
                transition = {"target": to_state}
                if guard:
                    transition["cond"] = guard
                if actions:
                    transition["actions"] = actions
                target_dict[resolved_from]["on"][event] = transition
            else:
                target_dict[resolved_from]["on"][event] = to_state
    
    # Merge with existing machine (if any)
    if existing_machine:
        # Start from existing machine
        machine = existing_machine.copy()
        machine["states"] = dict(existing_machine.get("states", {}))
        
        # Add new states from LLM suggestions
        for state in llm_data.get("states", []):
            state_name = state["name"]
            
            # Ignore dot-notation clones generated by LLM (e.g. success.dashboard) because they belong inside 'success'
            if "." in state_name:
                continue
                
            if state_name not in machine["states"]:
                machine["states"][state_name] = _build_state_config(state)
            else:
                # Update existing state
                existing_entry = machine["states"][state_name].get("entry", [])
                new_entry = state.get("entry_actions", [])
                machine["states"][state_name]["entry"] = list(set(existing_entry + new_entry))
                
                existing_exit = machine["states"][state_name].get("exit", [])
                new_exit = state.get("exit_actions", [])
                machine["states"][state_name]["exit"] = list(set(existing_exit + new_exit))
                
                # Preserve or add hierarchical sub-states
                sub_states = state.get("sub_states", [])
                if sub_states:
                    new_config = _build_state_config(state)
                    machine["states"][state_name]["initial"] = new_config["initial"]
                    # Merge sub-states: keep existing, add new
                    existing_subs = machine["states"][state_name].get("states", {})
                    existing_subs.update(new_config.get("states", {}))
                    machine["states"][state_name]["states"] = existing_subs
        
        # Add transitions
        _add_transitions(machine, llm_data.get("transitions", []))
    else:
        # Generate from scratch
        machine = generate_base_machine()
        
        for state in llm_data.get("states", []):
            state_name = state["name"]
            machine["states"][state_name] = _build_state_config(state)
        
        # Add transitions
        _add_transitions(machine, llm_data.get("transitions", []))
    
    # Fix: if LLM used 'idle' instead of 'app_idle', normalize
    if "idle" in machine["states"] and machine["initial"] == "app_idle":
        machine["states"]["app_idle"] = machine["states"].pop("idle")
        for state_config in machine["states"].values():
            for event, target in list(state_config.get("on", {}).items()):
                if target == "idle":
                    state_config["on"][event] = "app_idle"
    
    # Fix: ensure app_idle exists
    if "app_idle" not in machine["states"]:
        machine["states"]["app_idle"] = {"entry": [], "exit": [], "on": {}}
    
    # Post-processing: complete missing transition branches
    machine = _complete_missing_branches(machine)
    
    # Post-processing: remove unreachable states and XState keywords used as state names
    machine = _clean_unreachable_states(machine)
    
    # Post-processing: validate against critical rules 15, 16, 17
    violations = _validate_no_critical_patterns(machine)
    if violations:
        print(f"\n  ⚠️  CRITICAL RULE VIOLATIONS DETECTED ({len(violations)}):")
        for v in violations:
            print(f"    ❌ {v}")
        print(f"\n  💡 These violations will be reported to the critic for the next iteration.")
        print(f"     The LLM should fix them when it sees the critic feedback.\n")
    else:
        print(f"  ✅ No critical rule violations (rules 15, 16, 17 passed)")
    
    print(f"Generated state machine: {len(machine['states'])} states")
    
    # Build sections
    edge_cases = llm_data.get("edge_cases", [])
    edge_cases_md = "| ID | Scenario | Expected | Priority |\n|----|----------|----------|----------|\n"
    for ec in edge_cases:
        edge_cases_md += f"| {ec['id']} | {ec['scenario']} | {ec['expected_behavior']} | {ec['priority']} |\n"
    
    flows = llm_data.get("flows", [])
    
    # Generate diagrams
    statechart = generate_plantuml_statechart(machine)
    sequence = generate_plantuml_sequence(flows)
    flows_md = ""
    for flow in flows:
        flows_md += f"\n### {flow['name']}\n"
        for step in flow.get("steps", []):
            flows_md += f"1. **Trigger**: {step.get('trigger', '')}\n"
            flows_md += f"   **Action**: {step.get('action', '')}\n"
            flows_md += f"   **Outcome**: {step.get('expected_outcome', '')}\n"
            if step.get('error_scenario'):
                flows_md += f"   **Error**: {step['error_scenario']}\n"
    
    endpoints = llm_data.get("api_endpoints", [])
    endpoints_md = ""
    for ep in endpoints:
        endpoints_md += f"\n#### {ep['method']} {ep['path']}\n"
        endpoints_md += f"- **Description**: {ep.get('description', '')}\n"
    
    # Error Handling Table
    error_handling = llm_data.get("error_handling", [])
    if error_handling:
        error_handling_md = "| Code | Type | User Message | Action |\n|--------|------|------------------|--------|\n"
        for err in error_handling:
            error_handling_md += f"| {err.get('code', '')} | {err.get('type', '')} | \"{err.get('message', '')}\" | {err.get('action', '')} |\n"
    else:
        # Fallback se array vuoto
        error_handling_md = "| Code | Type | User Message | Action |\n|--------|------|------------------|--------|\n"
        error_handling_md += "| 500 | Generic Error | \"Si è verificato un errore.\" | Riprova |\n"

    # Data Validation Table
    data_validation = llm_data.get("data_validation", [])
    if data_validation:
        data_validation_md = "| Field | Type | Required | Pattern | Max Length |\n|-------|------|--------------|---------|------------|\n"
        for val in data_validation:
            req = "Yes" if val.get('required') else "No"
            data_validation_md += f"| {val.get('field', '')} | {val.get('type', '')} | {req} | {val.get('pattern', '')} | {val.get('max_length', '')} |\n"
    else:
        data_validation_md = "*No data validation fields specified.*"
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    states_count = len(machine['states'])
    transitions_count = sum(len(s.get('on', {})) for s in machine['states'].values())
    edge_cases_count = len(edge_cases)
    error_types_count = len(error_handling) if error_handling else 1
    
    # Build spec
    spec_content = f"""# Functional Specification

Generated: {timestamp}

> Specification automatically generated from project context.

---

## 1. Overview

### 1.1 Scope
- User flows
- State machine (executable XState)
- Edge case analysis
- Error handling
- API contracts

---

## 2. User Flows
{flows_md if flows_md else "*No flows generated*"}

---

## 3. State Machine

### 3.1 State Diagram (PlantUML)

```plantuml
{statechart}
```

### 3.2 XState Configuration

```json
{json.dumps(machine, indent=2)}
```

---

## 4. Sequence Diagram (PlantUML)

```plantuml
{sequence}
```

---

## 5. Edge Cases

{edge_cases_md if edge_cases else "*No edge cases generated*"}

---

## 6. Error Handling

### 6.1 Error Types

{error_handling_md}

### 6.2 Error States

The state machine handles errors through dedicated states that:
- Log the error for debugging
- Show appropriate messages to the user
- Offer recovery options (retry, cancel, contact support)

---

## 7. Data Validation

### 7.1 Validation Rules

{data_validation_md}

### 7.2 Validation Feedback

- Inline validation on blur
- Summary validation on submit
- Clear messages with instructions

---

## 8. API Contract
{endpoints_md if endpoints_md else "*No endpoints generated*"}

---

## 9. Metrics

### 9.1 Analysis Coverage

- States defined: {states_count}
- Transitions defined: {transitions_count}
- Edge cases identified: {edge_cases_count}
- Error types handled: {error_types_count}

---

## Appendix A: Original Context

The original project context is in `project_context.md`.
"""
    
    # Write spec
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(spec_content)
    
    # Write XState
    xstate_file = output_file.replace(".md", "_machine.json")
    with open(xstate_file, "w", encoding="utf-8") as f:
        json.dump(machine, f, indent=2)
    
    elapsed = time.time() - start_time
    
    metrics = {
        "states_count": len(machine["states"]),
        "transitions_count": sum(len(s.get("on", {})) for s in machine["states"].values()),
        "edge_cases_count": edge_cases_count,
        "error_types_count": error_types_count,
        "elapsed_seconds": elapsed,
        "spec_file": output_file,
        "machine_file": xstate_file,
    }
    
    return metrics


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate functional specification from context")
    parser.add_argument("--context", type=str, default="output/context/project_context.md",
                        help="Input context file")
    parser.add_argument("--output", type=str, default="output/spec/spec.md",
                        help="Output spec file")
    parser.add_argument("--time-budget", type=int, default=TIME_BUDGET,
                        help="Time budget in seconds")
    parser.add_argument("--suggestions", type=str, default=None,
                        help="Analyst suggestions JSON file")
    parser.add_argument("--machine", type=str, default=None,
                        help="Existing machine JSON file (for iterative approach)")
    parser.add_argument("--critic-feedback", type=str, default=None,
                        help="Critic feedback JSON file")
    args = parser.parse_args()
    
    if not os.path.exists(args.context):
        print(f"Error: Context file not found: {args.context}")
        print("Run 'python ingest.py' first")
        sys.exit(1)
    
    # Load analyst suggestions if provided
    analyst_suggestions = None
    if args.suggestions and os.path.exists(args.suggestions):
        with open(args.suggestions, "r", encoding="utf-8") as f:
            analyst_suggestions = json.load(f)
        print(f"  📋 Analyst suggestions loaded: {args.suggestions}")
    
    # Load critic feedback if provided
    critic_feedback = None
    if args.critic_feedback and os.path.exists(args.critic_feedback):
        with open(args.critic_feedback, "r", encoding="utf-8") as f:
            critic_feedback = json.load(f)
        print(f"  🚨 Critic feedback loaded: {args.critic_feedback}")
    
    print(f"Running functional analysis...")
    print(f"  Context: {args.context}")
    print(f"  Output: {args.output}")
    print(f"  Time budget: {args.time_budget}s")
    print()
    
    metrics = run_analysis(
        args.context, 
        args.output, 
        args.time_budget, 
        analyst_suggestions=analyst_suggestions,
        existing_machine_file=args.machine,
        critic_feedback=critic_feedback
    )
    
    print()
    print("=" * 50)
    print("ANALYSIS COMPLETE")
    print("=" * 50)
    print(f"States defined:      {metrics['states_count']}")
    print(f"Transitions:         {metrics['transitions_count']}")
    print(f"Edge cases:          {metrics['edge_cases_count']}")
    print(f"Error types:         {metrics['error_types_count']}")
    print(f"Time:                {metrics['elapsed_seconds']:.1f}s")
    print()
    print(f"Output files:")
    print(f"  - {metrics['spec_file']}")
    print(f"  - {metrics['machine_file']}")


if __name__ == "__main__":
    main()