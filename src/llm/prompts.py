"""Centralized prompts for all pipeline stages.

All LLM prompts are defined here for easy maintenance and consistency.
"""

# ---------------------------------------------------------------------------
# Analyst Prompt
# ---------------------------------------------------------------------------

ANALYST_PROMPT = """Analyze this project context and generate a functional specification.

Context:
{context}
{critic_section}

Respond ONLY with valid JSON (no markdown, no extra code):

{{
  "patterns_detected": ["pattern1", "pattern2"],
  "states": [
    {{"name": "state_name", "description": "desc", "entry": [], "exit": []}}
  ],
  "transitions": [
    {{"from": "state1", "to": "state2", "event": "EVENT_NAME", "guard": null}}
  ],
  "edge_cases": [
    {{"id": "EC001", "scenario": "desc", "trigger": "cause", "expected": "behavior", "priority": "high"}}
  ],
  "events": [
    {{"name": "EVENT_NAME", "description": "desc", "payload": {{}}}}
  ],
  "ux_questions": ["question1"],
  "confidence": 0.8
}}

CRITICAL Rules:
1. 100% valid JSON - no text outside the JSON
2. State names in lowercase_snake_case
3. Events in UPPERCASE_WITH_UNDERSCORE
4. Include at least: loading, error, success, empty states
5. Include transitions for: forward/back navigation, error, cancellation
6. Edge cases: timeout, network error, expired session, invalid input

FUNDAMENTAL RULE - NO DEAD-END STATES:
Every state MUST have at least one exit transition (except the final success state).
- ERROR state: must have RETRY transition → loading state, and CANCEL → initial state
- LOADING state: must have CANCEL transition → previous state, TIMEOUT → error state
- EMPTY state: must have REFRESH transition → loading state, GO_BACK → initial state
- SUCCESS state: may have no transitions (it's a final state)
- SESSION_EXPIRED state: must have REAUTHENTICATE transition → loading state, CANCEL → initial state

Verification: for each state you generate, ask yourself "how does the user exit this state?" and add the corresponding transition.
"""

# ---------------------------------------------------------------------------
# Spec Generator Prompt
# ---------------------------------------------------------------------------

SPEC_PROMPT = """{task}

Project context:
{context}
{existing_section}
{suggestions_section}
{critic_section}

Respond ONLY with valid JSON:

{{
  "states": [{{"name": "snake_case", "description": "...", "entry_actions": [], "exit_actions": [], "sub_states": [], "initial_sub_state": null}}],
  "transitions": [{{"from_state": "...", "to_state": "...", "event": "UPPER_CASE", "guard": null}}],
  "edge_cases": [{{"id": "EC001", "scenario": "...", "trigger": "...", "expected_behavior": "...", "priority": "high"}}],
  "flows": [{{"name": "...", "steps": [{{"trigger": "...", "action": "...", "expected_outcome": "...", "error_scenario": "..."}}]}],
  "api_endpoints": [{{"method": "GET", "path": "...", "description": "..."}}],
  "error_handling": [{{"code": 404, "type": "Not Found", "message": "User friendly message", "action": "Return home"}}],
  "data_validation": [{{"field": "email", "type": "string", "required": true, "pattern": "RFC 5322", "max_length": 254}}]
}}

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
      "on": {{ "START_APP": "authenticating" }}
    The UI layer is responsible for firing START_APP when the app is ready.
    This prevents infinite loops: app_idle → checkAuth fails → login → cancel → app_idle → ...

17. CLUSTERING MUST BE A SUB-STATE with error exit:
    If the app has a "clustering" or "calculation" feature inside a page (e.g., Benchmark),
    it MUST be a sub-state of that page: success.benchmark.clustering_calculation.
    
    CRITICAL: Every nested sub-state MUST define an exit path to "error".
    Either inherit from parent or define explicitly:
      "on": {{ "ON_ERROR": ".." }}  (goes to parent's error handler)
    Deep nesting without error exit = broken state machine.

CRITICAL - DO NOT USE THESE REDUNDANT EVENTS (use the consolidated alternatives):
- DATA_LOADED, DATA_FETCHED -> use ON_SUCCESS (with guard "hasData")
- FETCH_ERROR, FETCH_FAILED, TIMEOUT, TIMEOUT_FETCH, ERROR -> use ON_ERROR
- CANCEL_FETCH -> use CANCEL (with guard "hasPreviousState")
- RETRY (without guard) -> use RETRY_FETCH with cond "canRetry"

EXAMPLE - loading state transitions (follow this pattern):
  In the "transitions" array, you MUST generate BOTH branches for every conditional event:
  - {{"from_state": "loading", "to_state": "success", "event": "ON_SUCCESS", "guard": "hasData"}}
  - {{"from_state": "loading", "to_state": "empty", "event": "ON_SUCCESS", "guard": "!hasData"}}
  - {{"from_state": "loading", "to_state": "error", "event": "ON_ERROR"}}
  - {{"from_state": "loading", "to_state": "success", "event": "CANCEL", "guard": "hasPreviousState"}}
  - {{"from_state": "loading", "to_state": "app_idle", "event": "CANCEL", "guard": "!hasPreviousState"}}

EXAMPLE - error state transitions (follow this pattern):
  - {{"from_state": "error", "to_state": "loading", "event": "RETRY_FETCH", "guard": "canRetry", "actions": ["incrementRetryCount"]}}
  - {{"from_state": "error", "to_state": "session_expired", "event": "RETRY_FETCH", "guard": "!canRetry"}}
  - {{"from_state": "error", "to_state": "app_idle", "event": "CANCEL"}}

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

# ---------------------------------------------------------------------------
# Critic Prompt
# ---------------------------------------------------------------------------

CRITIC_PROMPT = """You are a ruthless QA Engineer and UX Reviewer. Your job is to find flaws in this functional specification.

## Fuzz Test Results
{fuzz_summary}

## Bugs Found by Fuzzer
{bugs}

## Current Specification (excerpt)
{spec_text}

## State Machine Summary
States ({states_count}): {state_names}
Initial: {initial_state}
Transitions ({transitions_count}):
{transitions_list}
{context_section}
Your task: Analyze and provide critical feedback in JSON format:
{{
  "critical_issues": [
    {{
      "id": "CRIT-001",
      "category": "logic|ux|error_handling|security|performance|missing_flow",
      "description": "Clear description of the issue",
      "affected_states": ["state1", "state2"],
      "severity": "critical|high|medium",
      "suggestion": "How to fix it"
    }}
  ],
  "ux_decisions_needed": [
    {{
      "id": "UX-001",
      "question": "What should happen when...?",
      "context": "Current behavior is ambiguous because...",
      "options": ["Option A", "Option B", "Option C"]
    }}
  ],
  "edge_cases_to_add": [
    {{
      "id": "EC-NEW-001",
      "scenario": "Description of the edge case",
      "expected_behavior": "What should happen",
      "priority": "high|medium|low"
    }}
  ],
  "missing_flows": [
    {{
      "id": "FLOW-001",
      "flow_name": "Name of the missing flow",
      "description": "What this flow should do",
      "business_reason": "Why this is required based on project context",
      "suggested_states": ["state1", "state2"],
      "suggested_transitions": [
        {{"from": "state1", "to": "state2", "event": "EVENT_NAME"}}
      ]
    }}
  ],
  "recommendations": [
    "General recommendation 1",
    "General recommendation 2"
  ]
}}

Be thorough. Look for:
1. Missing error handling paths
2. Ambiguous user flows
3. Security concerns (data exposure, auth bypass)
4. Performance issues (unnecessary API calls, missing caching)
5. UX problems (confusing states, missing feedback)
6. Edge cases the fuzzer might have missed
7. **MISSING FLOWS**: Compare the project context with the current state machine. Are there any features or flows described in the context that are completely absent from the state machine? (e.g., if the app has login but no auth flow exists, if it has search but no search states)
"""