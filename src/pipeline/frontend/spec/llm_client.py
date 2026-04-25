"""
LLM client for spec generation - calls LLM to generate/modify state machines.
"""

import os
import sys
import json

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import LLM_CONFIG, DEFAULT_PROVIDER


def _call_llm_streaming_no_thinking(client, model: str, system_message: str, prompt: str,
                                     temperature: float, max_tokens: int, timeout: int) -> str:
    """Call LLM with streaming but WITHOUT thinking enabled.
    
    For NVIDIA NIM: thinking/reasoning can contaminate JSON output.
    This function streams the response without enabling the thinking template.
    """
    print(f"  🔄 Streaming response (no thinking)...")
    
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
    
    print()  # newline after streaming
    return full_content


def call_llm_spec(
    context_text: str, 
    analyst_suggestions: dict = None, 
    existing_machine: dict = None, 
    critic_feedback: dict = None,
    max_retries: int = 3
) -> dict:
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
    
    use_streaming = (provider == "nvidia")
    
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
        workflows = analyst_suggestions.get("workflows", [])
        
        workflows_text = ""
        if workflows:
            workflows_text = f"""
- {len(workflows)} suggested workflows: {', '.join(w['id'] for w in workflows[:10])}
  Workflow details:
{chr(10).join(f'    * {w["id"]}: {w.get("name", "")} - {w.get("description", "")} (trigger: {w.get("trigger", "")}, steps: {", ".join(w.get("steps", []))})' for w in workflows[:10])}
"""
        
        suggestions_section = f"""

ANALYST SUGGESTIONS (YOU MUST INCLUDE THESE):
- {len(states)} suggested states: {', '.join(s['name'] for s in states[:15])}
- {len(transitions)} suggested transitions
- {len(edge_cases)} edge cases to handle
- {len(events)} events to support: {', '.join(e['name'] for e in events[:10])}
{workflows_text}
REQUIRED ACTIONS:
1. Add ALL suggested states that don't already exist
2. Add suggested transitions
3. Handle edge cases with appropriate error states
4. For EACH suggested workflow, create a compound state under "active_workflows" with internal micro-states
5. Each workflow MUST have a completion event that returns to "none"
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
14. HIERARCHICAL STATES: The "success" state MUST be hierarchical (nested). Analyze the project context and create a sub-state for each main area/screen of the app (e.g., for e-commerce: catalog, cart, profile; for some app: dashboard, catalog, offers, benchmark, groups). Each sub-state should have navigation events to other sub-states (e.g., NAVIGATE_CATALOG, NAVIGATE_OFFERS). This allows the UI generator to create separate screen files for each area.

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

18. CONTEXT MUST TRACK PREVIOUS STATE for CANCEL guard:
    The "context" object MUST include a "previousState" field:
      "context": {"user": null, "errors": [], "retryCount": 0, "previousState": null}
    
    When transitioning FROM success TO loading (e.g., via REFRESH_DATA),
    the loading state's "entry" MUST include an action to save the previous state:
      "entry": ["showSkeleton", "setPreviousState"]
    
    The guard "hasPreviousState" checks: context.previousState !== null
    This allows CANCEL to return to success (during refresh) or app_idle (first load).

19. RETRY_FETCH MUST increment retryCount:
    The transition from error to loading via RETRY_FETCH MUST include the action:
      "actions": ["incrementRetryCount"]
    
    The guard "canRetry" checks: context.retryCount < 3
    Without this action, retryCount stays at 0 and the user can retry infinitely.

20. EVENT NAMING: Use ENGLISH for all event names (standardize on English).
    - Use NAVIGATE_CATALOG (not NAVIGATE_CATALOGO)
    - Use NAVIGATE_OFFERS (not NAVIGATE_OFFERTE)
    - Use NAVIGATE_GROUPS (not NAVIGATE_GRUPPI)
    - Event names are code identifiers — keep them in English.
    - Comments and descriptions can be in Italian.

21. MICRO-OPERATIONS AND INTERNAL TRANSITIONS (BUSINESS LOGIC):
    Ensure that each sub-state does NOT ONLY contain navigation events (NAVIGATE_*).
    You MUST include data manipulation events (micro-operations) as internal transitions or transitions to child states.
    Examples for a generic app (e.g., e-commerce or social):
    - In a list/feed state: include "APPLY_FILTER", "LOAD_MORE", or "SEARCH" with appropriate "actions" like ["updateSearchFilters"].
    - In a detail state: include "LIKE_ITEM", "DELETE_ITEM", or "ADD_TO_CART" with actions like ["updateItemStatus"].
    - In a form/modal state: include "SUBMIT_DATA" or "CANCEL_EDIT" with actions and/or targets.
    Without these, the application has no business logic and only acts as an empty navigation shell!

22. PARALLEL STATES ARCHITECTURE (NEW - CRITICAL FOR WORKFLOWS):
    The root state machine MUST use type: "parallel" with TWO branches:
    
    Branch 1 - "navigation": tracks which PAGE the user is physically on
      - Contains: app_idle, authenticating, loading, success (with sub-states), empty, error, session_expired
      - This is the EXISTING navigation structure you already generate
    
    Branch 2 - "active_workflows": tracks which WORKFLOW is currently active
      - initial: "none"
      - Contains compound states for each workflow identified from the context
      - Each workflow compound state has its own internal micro-states
      - EVERY workflow MUST have a completion event that returns to "none"
    
    Example root structure:
    {
      "id": "appFlow",
      "type": "parallel",
      "states": {
        "navigation": {
          "initial": "app_idle",
          "states": { /* existing navigation states */ }
        },
        "active_workflows": {
          "initial": "none",
          "states": {
            "none": {},
            "benchmark_workflow": {
              "initial": "discovery",
              "states": {
                "discovery": {
                  "entry": ["showBenchmarkOverlay"],
                  "on": { "VIEW_DETAILS": "viewing", "GO_BACK": "none" }
                },
                "viewing": {
                  "entry": ["showPriceComparison"],
                  "on": { "JOIN_GROUP": "joining", "GO_BACK": "discovery" }
                },
                "joining": {
                  "entry": ["showJoinConfirmation"],
                  "on": { "CONFIRM_JOIN": "tracking", "CANCEL": "viewing" }
                },
                "tracking": {
                  "entry": ["showGroupProgress"],
                  "on": { "GROUP_COMPLETE": "none", "GO_BACK": "discovery" }
                }
              },
              "on": {
                "NAVIGATE_DASHBOARD": "#navigation.success.dashboard",
                "NAVIGATE_CATALOG": "#navigation.success.catalog"
              }
            },
            "purchase_group_workflow": {
              "initial": "browsing",
              "states": {
                "browsing": {
                  "entry": ["showGroupCatalog"],
                  "on": { "SELECT_GROUP": "confirming", "GO_BACK": "none" }
                },
                "confirming": {
                  "entry": ["showJoinModal"],
                  "on": { "CONFIRM_JOIN": "tracking", "CANCEL": "browsing" }
                },
                "tracking": {
                  "entry": ["showGroupTracking"],
                  "on": { "GROUP_COMPLETE": "none", "GO_BACK": "browsing" }
                }
              },
              "on": {
                "NAVIGATE_DASHBOARD": "#navigation.success.dashboard",
                "NAVIGATE_CATALOG": "#navigation.success.catalog"
              }
            }
          }
        }
      }
    }

23. WORKFLOW IDENTIFICATION RULES:
    Identify workflows from the INPUT CONTEXT by looking for:
    - VERBS OF ACTION: partecipare, confrontare, ricevere, unirsi, monitorare, vedere, scoprire
    - MULTI-STEP PROCESSES: anything that spans multiple screens
    - USER JOURNEYS: "voglio vedere se risparmio" = benchmark_workflow
    - "gruppi d'acquisto" = purchase_group_workflow
    - "alert prezzi" = price_alert_workflow
    
    For each workflow:
    - Give it a unique id (snake_case) ending with "_workflow"
    - Define 3-5 internal steps (micro-states)
    - Each step MUST have entry actions and transitions
    - EVERY step MUST have a GO_BACK or CANCEL transition
    - The LAST step MUST have a completion event (COMPLETED, CANCELLED, DISMISSED) → "none"

24. WORKFLOW-TO-PAGE CONNECTIONS:
    Workflows can be triggered FROM pages and can navigate BACK to pages:
    - Trigger events come FROM navigation states (e.g., VIEW_BENCHMARK from catalog)
    - Cross-page events in workflow "on" block use "#navigation." prefix
    - Example: "NAVIGATE_DASHBOARD": "#navigation.success.dashboard"
    - This connects the parallel branches without breaking encapsulation

25. WORKFLOW COMPLETION IS MANDATORY:
    Every workflow compound state MUST have at least one transition that returns to "none":
    - "COMPLETED" → "none" (success path)
    - "CANCELLED" → "none" (user cancelled)
    - "DISMISSED" → "none" (workflow dismissed)
    
    Without this, the workflow stays "active" forever and blocks the app.
    This is a HARD REQUIREMENT - no exceptions.

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
    
    print(f"  🤖 Calling LLM for spec ({model}){' [streaming]' if use_streaming else ''}, context: {len(context_text)} chars...")
    if existing_machine:
        print(f"  📦 Existing machine: {len(existing_machine.get('states', {}))} states")
    
    for attempt in range(max_retries):
        try:
            print(f"  Attempt {attempt + 1}/{max_retries}...")
            
            if use_streaming:
                # NVIDIA NIM: use streaming WITHOUT thinking to avoid JSON contamination
                content = _call_llm_streaming_no_thinking(
                    client, model,
                    "You are an expert Product Manager specializing in state machines. Respond ONLY with valid JSON. Start with { and end with }. No markdown, no extra text.",
                    prompt, 0.3, 8192, 180
                )
            else:
                response = client.chat.completions.create(
                    timeout=180,
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are an expert Product Manager specializing in state machines. Respond ONLY with valid JSON. Start with { and end with }. No markdown, no extra text."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=8192,
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