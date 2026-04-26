"""
LLM client for spec generation - multi-step approach.
Separates state generation, transition generation, and workflow generation
into distinct LLM calls for better quality and focus.
"""

import os
import sys
import json

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import LLM_CONFIG, DEFAULT_PROVIDER


def _call_llm(client, model: str, system_message: str, prompt: str,
              temperature: float, max_tokens: int, timeout: int, use_streaming: bool = False) -> str:
    """Call LLM and return content. Handles streaming or non-streaming."""
    if use_streaming:
        print(f"  🔄 Streaming response...")
        response = client.chat.completions.create(
            timeout=timeout,
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        full_content = ""
        for chunk in response:
            if not getattr(chunk, "choices", None):
                continue
            if chunk.choices and chunk.choices[0].delta.content is not None:
                content_chunk = chunk.choices[0].delta.content
                print(content_chunk, end="", flush=True)
                full_content += content_chunk
        print()
        return full_content
    else:
        response = client.chat.completions.create(
            timeout=timeout,
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()


def _extract_json(content: str) -> dict:
    """Extract JSON from LLM response, handling markdown fences and extra text."""
    # Strip markdown fences
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()
    
    # Find the first { or [ 
    start = -1
    for i, c in enumerate(content):
        if c in ('{', '['):
            start = i
            break
    
    if start < 0:
        raise json.JSONDecodeError("No JSON object or array found", content, 0)
    
    # Use balanced brace matching to find the complete JSON
    bracket_stack = []
    in_string = False
    escape_next = False
    
    for i in range(start, len(content)):
        c = content[i]
        
        if escape_next:
            escape_next = False
            continue
        
        if c == '\\':
            escape_next = True
            continue
        
        if c == '"' and not escape_next:
            in_string = not in_string
            continue
        
        if in_string:
            continue
        
        if c in ('{', '['):
            bracket_stack.append(c)
        elif c in ('}', ']'):
            if not bracket_stack:
                # Unmatched closing bracket - this is extra data after valid JSON
                break
            opening = bracket_stack.pop()
            expected = '}' if opening == '{' else ']'
            if c != expected:
                # Mismatched bracket - stop here
                break
            if not bracket_stack:
                # Balanced! Extract from start to here
                json_str = content[start:i+1]
                return json.loads(json_str)
    
    # If we get here, try to parse what we have (might be truncated)
    json_str = content[start:]
    return json.loads(json_str)


def _get_client():
    """Create OpenAI client from environment variables."""
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
        return OpenAI(api_key=api_key, base_url=base_url), model, (provider == "nvidia")
    except ImportError:
        print("❌ ERROR: openai not installed.")
        sys.exit(1)


# ============================================================================
# STEP 1: Generate States
# ============================================================================

def call_llm_states(
    context_text: str,
    critic_feedback: dict = None,
    existing_states: list = None,
    validator_feedback: dict = None,
    max_retries: int = 3
) -> list:
    """Generate ONLY states (no transitions).
    
    Returns list of state dicts: [{"name": "...", "description": "...", "sub_states": [...], ...}]
    """
    client, model, use_streaming = _get_client()
    
    # Truncate context
    if len(context_text) > 3000:
        lines = context_text.split("\n")
        important = [l for l in lines if l.startswith("##") or l.startswith("###") or l.startswith("-") or l.startswith("|")]
        context_text = "\n".join(important[:80])
        if len(context_text) > 3000:
            context_text = context_text[:3000]
    
    existing_text = ""
    if existing_states:
        existing_text = f"\n\nEXISTING STATES (keep these, add more if needed):\n{', '.join(existing_states)}"
    
    critic_text = ""
    if critic_feedback:
        critical = critic_feedback.get("summary", {}).get("critical_issues", [])
        if critical:
            critic_text = f"\n\nCRITICAL ISSUES TO ADDRESS:\n" + "\n".join(f"- {c}" for c in critical[:5])
    
    validator_text = ""
    if validator_feedback:
        unreachable = validator_feedback.get("unreachable_states", [])
        dead_ends = validator_feedback.get("dead_end_states", [])
        score = validator_feedback.get("quality_score", "N/A")
        if unreachable or dead_ends:
            validator_text = f"\n\nVALIDATOR FEEDBACK (from previous iteration):\n"
            validator_text += f"  Quality Score: {score}/100\n"
            if unreachable:
                validator_text += f"  UNREACHABLE STATES ({len(unreachable)}): {', '.join(unreachable[:15])}\n"
                validator_text += f"  → These states have no incoming transitions. Either remove them or add transitions TO them.\n"
            if dead_ends:
                validator_text += f"  DEAD-END STATES ({len(dead_ends)}): {', '.join(dead_ends[:15])}\n"
                validator_text += f"  → These states have no exit transitions. Add transitions FROM them.\n"
    
    prompt = f"""Analyze this project context and generate a list of states for a state machine.

{context_text}
{existing_text}
{critic_text}
{validator_text}

Return ONLY valid JSON array of states:
[
  {{
    "name": "snake_case_name",
    "description": "what this state represents",
    "entry_actions": ["action1", "action2"],
    "exit_actions": [],
    "sub_states": [
      {{"name": "loading", "entry_actions": ["showSkeleton"], "initial_sub_state": true}},
      {{"name": "ready", "entry_actions": ["renderContent"]}},
      {{"name": "error", "entry_actions": ["showErrorBanner"]}}
    ],
    "initial_sub_state": "loading"
  }}
]

RULES (STRICT - VIOLATIONS WILL CAUSE VALIDATION FAILURE):
1. EXACTLY ONE initial/resting state MUST be included (e.g., "app_initial"). This is the ENTRY POINT of the entire app.
2. The initial state MUST be named "app_initial" (not "app_idle", not "home", not "navigation")
3. Include auth states: "auth_guard", "login", "session_expired" - these MUST be reachable from app_initial
4. Include main screen states: "dashboard", "catalog", "offers", "alerts"
5. Each screen state MUST have sub_states: loading, ready, error
6. Include workflow states: "benchmark_workflow", "purchase_group_workflow", "price_alert_workflow"
7. Each workflow state MUST have sub_states for each step (3-5 steps)
8. Use snake_case for ALL state names
9. NO duplicate state names across different paths (e.g., don't use "loading" in two different compound states)
10. Return ONLY the JSON array, no text outside
11. LIMIT TO 20-30 TOP-LEVEL STATES. Quality over quantity.

Focus on COMPLETENESS and CORRECTNESS. Every state must be reachable from app_initial."""

    system = "You are an expert Product Manager. Return ONLY valid JSON. No markdown, no extra text."
    
    for attempt in range(max_retries):
        try:
            print(f"  📋 Step 1/3: Generating states (attempt {attempt+1}/{max_retries})...")
            content = _call_llm(client, model, system, prompt, 0.3, 4096, 300, use_streaming)
            data = _extract_json(content)
            if isinstance(data, list):
                print(f"  ✅ Generated {len(data)} states")
                return data
            elif isinstance(data, dict) and "states" in data:
                print(f"  ✅ Generated {len(data['states'])} states")
                return data["states"]
        except json.JSONDecodeError as e:
            print(f"  ⚠️  JSON parse error: {e}")
            continue
        except Exception as e:
            print(f"  ⚠️  Error: {e}")
            continue
    
    print("❌ ERROR: All state generation attempts failed.")
    sys.exit(1)


# ============================================================================
# STEP 2: Generate Transitions
# ============================================================================

def call_llm_transitions(
    context_text: str,
    states: list,
    existing_transitions: list = None,
    validator_feedback: dict = None,
    max_retries: int = 3
) -> list:
    """Generate ONLY transitions (given the states).
    
    Returns list of transition dicts: [{"from_state": "...", "to_state": "...", "event": "...", "guard": null}, ...]
    """
    client, model, use_streaming = _get_client()
    
    state_names = [s["name"] for s in states]
    state_details = ""
    for s in states:
        subs = s.get("sub_states", [])
        sub_names = [sub["name"] for sub in subs] if subs else []
        state_details += f"- {s['name']} (sub-states: {', '.join(sub_names) if sub_names else 'none'})\n"
    
    existing_text = ""
    if existing_transitions:
        existing_text = f"\n\nEXISTING TRANSITIONS (add more, don't remove):\n" + "\n".join(
            f"  {t.get('from_state', '?')} --{t.get('event', '?')}--> {t.get('to_state', '?')}" 
            for t in existing_transitions[:20]
        )
    
    validator_text = ""
    if validator_feedback:
        unreachable = validator_feedback.get("unreachable_states", [])
        dead_ends = validator_feedback.get("dead_end_states", [])
        score = validator_feedback.get("quality_score", "N/A")
        if unreachable or dead_ends:
            validator_text = f"\n\nVALIDATOR FEEDBACK (from previous iteration):\n"
            validator_text += f"  Quality Score: {score}/100\n"
            if unreachable:
                validator_text += f"  UNREACHABLE STATES ({len(unreachable)}): {', '.join(unreachable[:15])}\n"
                validator_text += f"  → Add transitions TO these states from reachable states.\n"
            if dead_ends:
                validator_text += f"  DEAD-END STATES ({len(dead_ends)}): {', '.join(dead_ends[:15])}\n"
                validator_text += f"  → Add transitions FROM these states to other states.\n"
    
    prompt = f"""Given these states, generate ALL transitions between them.

STATES:
{state_details}
{existing_text}
{validator_text}

Return ONLY valid JSON array of transitions:
[
  {{"from_state": "app_initial", "to_state": "auth_guard", "event": "START_APP", "guard": null}},
  {{"from_state": "auth_guard", "to_state": "login", "event": "AUTH_REQUIRED", "guard": null}},
  {{"from_state": "login", "to_state": "dashboard", "event": "LOGIN_SUCCESS", "guard": null}},
  {{"from_state": "dashboard", "to_state": "catalog", "event": "NAVIGATE_CATALOG", "guard": null}},
  {{"from_state": "dashboard", "to_state": "offers", "event": "NAVIGATE_OFFERS", "guard": null}},
  {{"from_state": "dashboard", "to_state": "alerts", "event": "NAVIGATE_ALERTS", "guard": null}},
  {{"from_state": "catalog", "to_state": "dashboard", "event": "NAVIGATE_DASHBOARD", "guard": null}},
  {{"from_state": "offers", "to_state": "dashboard", "event": "NAVIGATE_DASHBOARD", "guard": null}},
  {{"from_state": "alerts", "to_state": "dashboard", "event": "NAVIGATE_DASHBOARD", "guard": null}}
]

RULES:
1. Every state MUST have at least 2 exit transitions (no dead-ends)
2. Include navigation between all main screens (dashboard, catalog, offers, alerts)
3. Include auth flow: app_initial -> auth_guard -> login -> dashboard
4. Include session_expired -> login (REAUTHENTICATE event)
5. For workflow states, include GO_BACK and COMPLETE transitions
6. Use UPPER_CASE for event names
7. Use snake_case for state names
8. Include guard conditions where appropriate (e.g., "hasData", "canRetry")
9. Every loading sub-state needs: ON_SUCCESS->ready, ON_ERROR->error, CANCEL->previous
10. Every error sub-state needs: RETRY_FETCH->loading, CANCEL->previous

Focus on CONNECTIVITY. Every state must be reachable and have exit paths."""

    system = "You are an expert Product Manager. Return ONLY valid JSON. No markdown, no extra text."
    
    for attempt in range(max_retries):
        try:
            print(f"  🔗 Step 2/3: Generating transitions (attempt {attempt+1}/{max_retries})...")
            content = _call_llm(client, model, system, prompt, 0.3, 4096, 300, use_streaming)
            data = _extract_json(content)
            if isinstance(data, list):
                print(f"  ✅ Generated {len(data)} transitions")
                return data
            elif isinstance(data, dict) and "transitions" in data:
                print(f"  ✅ Generated {len(data['transitions'])} transitions")
                return data["transitions"]
        except json.JSONDecodeError as e:
            print(f"  ⚠️  JSON parse error: {e}")
            continue
        except Exception as e:
            print(f"  ⚠️  Error: {e}")
            continue
    
    print("❌ ERROR: All transition generation attempts failed.")
    sys.exit(1)


# ============================================================================
# STEP 3: Generate Workflows
# ============================================================================

def call_llm_workflows(
    context_text: str,
    states: list,
    transitions: list,
    analyst_suggestions: dict = None,
    validator_feedback: dict = None,
    max_retries: int = 3
) -> list:
    """Generate ONLY workflow compound states with internal micro-states.
    
    Returns list of workflow dicts for the active_workflows branch.
    """
    client, model, use_streaming = _get_client()
    
    state_names = [s["name"] for s in states]
    
    workflows_text = ""
    if analyst_suggestions and analyst_suggestions.get("workflows"):
        workflows_text = "\n\nSUGGESTED WORKFLOWS:\n"
        for w in analyst_suggestions["workflows"][:5]:
            workflows_text += f"- {w['id']}: {w.get('description', '')}\n  Steps: {', '.join(w.get('steps', []))}\n"
    
    validator_text = ""
    if validator_feedback:
        unreachable = validator_feedback.get("unreachable_states", [])
        dead_ends = validator_feedback.get("dead_end_states", [])
        score = validator_feedback.get("quality_score", "N/A")
        if unreachable or dead_ends:
            validator_text = f"\n\nVALIDATOR FEEDBACK (from previous iteration):\n"
            validator_text += f"  Quality Score: {score}/100\n"
            if unreachable:
                validator_text += f"  UNREACHABLE STATES ({len(unreachable)}): {', '.join(unreachable[:15])}\n"
                validator_text += f"  → Ensure workflows connect to these states.\n"
            if dead_ends:
                validator_text += f"  DEAD-END STATES ({len(dead_ends)}): {', '.join(dead_ends[:15])}\n"
                validator_text += f"  → Ensure workflow steps have GO_BACK/CANCEL transitions.\n"
    
    prompt = f"""Analyze the context and generate workflow compound states.

CONTEXT:
{context_text[:2000]}
{workflows_text}
{validator_text}

EXISTING STATES: {', '.join(state_names)}

Return ONLY valid JSON array of workflows:
[
  {{
    "id": "benchmark_workflow",
    "name": "Benchmark Comparison",
    "initial": "discovery",
    "states": [
      {{"name": "discovery", "entry": ["showDiscovery"], "on": {{"NEXT": "viewing", "CANCEL": "none"}}}},
      {{"name": "viewing", "entry": ["showViewing"], "on": {{"NEXT": "comparison", "GO_BACK": "discovery"}}}},
      {{"name": "comparison", "entry": ["showComparison"], "on": {{"COMPLETE": "none", "GO_BACK": "viewing"}}}}
    ]
  }}
]

RULES:
1. Each workflow MUST have 3-5 internal steps (micro-states)
2. Each step MUST have entry actions and transitions
3. EVERY step MUST have GO_BACK or CANCEL transition
4. The LAST step MUST have COMPLETE/CANCELLED -> "none"
5. Use "none" as the idle state name
6. Each workflow needs ON_ERROR -> error sub-state with RETRY_FETCH
7. Workflow IDs must end with "_workflow"

Focus on WORKFLOW COMPLETION. Every workflow must return to "none"."""

    system = "You are an expert Product Manager. Return ONLY valid JSON. No markdown, no extra text."
    
    for attempt in range(max_retries):
        try:
            print(f"  🔄 Step 3/3: Generating workflows (attempt {attempt+1}/{max_retries})...")
            content = _call_llm(client, model, system, prompt, 0.3, 4096, 300, use_streaming)
            data = _extract_json(content)
            if isinstance(data, list):
                print(f"  ✅ Generated {len(data)} workflows")
                return data
            elif isinstance(data, dict) and "workflows" in data:
                print(f"  ✅ Generated {len(data['workflows'])} workflows")
                return data["workflows"]
        except json.JSONDecodeError as e:
            print(f"  ⚠️  JSON parse error: {e}")
            continue
        except Exception as e:
            print(f"  ⚠️  Error: {e}")
            continue
    
    print("❌ ERROR: All workflow generation attempts failed.")
    sys.exit(1)


# ============================================================================
# LEGACY: Single-call interface (for backward compatibility)
# ============================================================================

def call_llm_spec(
    context_text: str, 
    analyst_suggestions: dict = None, 
    existing_machine: dict = None, 
    critic_feedback: dict = None,
    max_retries: int = 3
) -> dict:
    """Legacy single-call interface. Now uses multi-step internally."""
    # Step 1: Generate states
    existing_states = None
    if existing_machine:
        existing_states = list(existing_machine.get("states", {}).keys())
    
    states = call_llm_states(context_text, critic_feedback, existing_states, max_retries)
    
    # Step 2: Generate transitions
    existing_transitions = None
    if existing_machine:
        existing_transitions = []
        for sn, sc in existing_machine.get("states", {}).items():
            for ev, tgt in sc.get("on", {}).items():
                existing_transitions.append({"from_state": sn, "to_state": tgt, "event": ev})
    
    transitions = call_llm_transitions(context_text, states, existing_transitions, max_retries)
    
    # Step 3: Generate workflows
    workflows = call_llm_workflows(context_text, states, transitions, analyst_suggestions, max_retries)
    
    # Combine into legacy format
    return {
        "states": states,
        "transitions": transitions,
        "workflows": workflows,
        "edge_cases": [],
        "flows": [],
        "api_endpoints": [],
        "error_handling": [],
        "data_validation": []
    }