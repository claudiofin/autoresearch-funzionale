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
7. **AUTH FLOW IS MANDATORY**: Every app MUST have an authentication flow.
   - Include states: authenticating, auth_success, auth_error, session_expired
   - The initial state MUST transition to authenticating on START_APP
   - Without auth, the app is insecure and the specification is INVALID
8. **HIERARCHICAL STATES FOR EVERY PAGE**: Every main screen/page MUST have
   loading → ready → error sub-states. Flat states without loading are UX failures.
   - Example: dashboard.loading → dashboard.ready → dashboard.error
   - The "initial" property MUST point to "loading"
9. **NO SELF-REFERENCING TRANSITIONS**: Never create a transition where from_state == to_state.
   - WRONG: {"from": "app_initial", "to": "app_initial", "event": "GLOBAL_EXIT"}
   - GLOBAL_EXIT must point to a DIFFERENT state (e.g., navigation.app_idle)

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
4. ON_SUCCESS transition: use guard "hasData" to go to the main content state if data exists, otherwise to an empty state
5. ON_ERROR transition: single event for all error types (network, timeout, server error)
6. CANCEL transition: use guard "hasPreviousState" to return to previous state, otherwise to the initial state
7. RETRY_FETCH in error state: MUST have guard "canRetry" (context.retryCount < 3)
8. When retry fails, use assign action to increment retryCount
9. After 3 failed retries, transition to a session_expired or max_retries_exceeded state
10. Cover: auth, core flow, error handling, empty states

=== RULE 11: MANDATORY ENTRY POINT (NON-NEGOTIABLE) ===
The initial state (app_initial, home, dashboard, etc.) MUST have a START_APP transition to the authenticating state.
This is the "door" into your app. Without it, the fuzzer enters and freezes.

MANDATORY PATTERN:
  State: "app_initial" (or your chosen initial name)
    - entry: [] (NO automatic actions — it's a resting state)
    - on: { "START_APP": "navigation.authenticating" }
  
  State: "authenticating" (or "login", "token_validation")
    - entry: ["validateToken", "checkSession"]
    - on: { "AUTH_SUCCESS": "navigation.dashboard", "AUTH_FAILED": "navigation.auth_error" }
  
  State: "auth_error"
    - on: { "RETRY_AUTH": "navigation.authenticating", "CANCEL": "app_initial" }
  
  State: "session_expired"
    - on: { "REAUTHENTICATE": "navigation.authenticating", "CANCEL": "app_initial" }

WITHOUT THIS AUTH FLOW, THE SPECIFICATION IS INVALID.

=== RULE 12: DEPTH LIMIT — MAX 3 LEVELS (ANTI-FRATTALE) ===
NEVER nest states deeper than 3 levels from the branch root.
- Level 1: navigation.dashboard (OK)
- Level 2: navigation.dashboard.loading (OK)
- Level 3: navigation.dashboard.loading.calculating (OK — MAX)
- Level 4: navigation.dashboard.loading.calculating.progress (WRONG — TOO DEEP)

If you need more depth, use WORKFLOWS branch instead:
  active_workflows.benchmark.calculating (OK — workflow branch allows deeper nesting)

ANTI-INCEPTION CHECK:
- NEVER create: dashboard.loading.loading (duplicate consecutive)
- NEVER create: error.error_handler.error_handler (infinite nesting)
- NEVER create: app_initial.app_initial.app_initial (recursive loop)
- If you see a pattern repeating, STOP and go back to parent level.

=== RULE 13: SPECIFIC DOMAIN EVENTS (NOT GENERIC) ===
Use domain-specific event names, not generic NEXT/CANCEL:
- WRONG: {{"from": "benchmark", "to": "results", "event": "NEXT"}}
- CORRECT: {{"from": "benchmark.discovery", "to": "benchmark.results", "event": "VIEW_BENCHMARK_RESULTS"}}

- WRONG: {{"from": "purchase_group", "to": "confirmation", "event": "CONFIRM"}}
- CORRECT: {{"from": "purchase_group.review", "to": "purchase_group.confirmation", "event": "CONFIRM_GROUP_PURCHASE"}}

- WRONG: {{"from": "catalog", "to": "product_detail", "event": "SELECT"}}
- CORRECT: {{"from": "catalog.list", "to": "catalog.product_detail", "event": "VIEW_PRODUCT"}}

Domain events make the state machine self-documenting and prevent confusion between workflows.

14. HIERARCHICAL STATES: The main CONTENT state (name it based on context: "success", "dashboard", "feed", "connected", etc.)
    MUST be hierarchical (nested). Analyze the project context and create a sub-state for each main area/screen of the app.
    - Identify all main screens/areas from the project description.
    - Create a sub-state for each one (e.g., catalog, cart, profile, devices, rooms, feed, messages, etc.).
    - Each sub-state should have navigation events to other sub-states.
    This allows the UI generator to create separate screen files for each area.

15. NO DUPLICATE STATES: Never create two sets of states for the same screens.
    If you create states as sub-states of the main content state,
    DO NOT also create prefixed versions (e.g., "success_dashboard", "feed_profile").
    Use ONLY the short names. Each screen = exactly ONE state.

16. INITIAL STATE IS A RESTING STATE — use a START event:
    DO NOT put automatic actions (checkAuth, validateCredentials, connectDevice, etc.) in the initial state's "entry".
    Instead, the initial state MUST listen for a START event that triggers initial setup:
      "on": {{ "START_APP": "authenticating" }}  (or INIT, START_GAME, CONNECT, etc. — choose appropriate name)
    The UI layer is responsible for firing the START event when the app is ready.
    This prevents infinite loops: initial → auto-action fails → error → cancel → initial → ...

17. COMPLEX OPERATIONS MUST BE SUB-STATES with error exit:
    If a page has complex background processing or data calculation,
    it MUST be a sub-state of that page (e.g., dashboard.benchmark.calculating).
    
    CRITICAL: Every nested sub-state MUST define an exit path to "error".
    Either inherit from parent or define explicitly:
      "on": {{ "ON_ERROR": ".." }}  (goes to parent's error handler)
    Deep nesting without error exit = broken state machine.

18. TRANSITION TARGETS MUST BE ABSOLUTE PATHS — NEVER use relative references:
    - WRONG: "to_state": ".app_idle"  (relative — will break)
    - WRONG: "to_state": "^navigation.authenticating"  (caret syntax — not supported)
    - WRONG: "to_state": "#workflows.none"  (if branch is named active_workflows)
    - CORRECT: "to_state": "navigation.app_idle"  (absolute path from root)
    - CORRECT: "to_state": "active_workflows.none"  (absolute path from root)
    
    RULE: Always use the FULL PATH from the root of the state machine.
    Format: "branch_name.state_name" or "branch_name.parent_state.child_state"
    
    Examples:
    - navigation.app_idle (NOT .app_idle, NOT #navigation.app_idle)
    - active_workflows.none (NOT #workflows.none, NOT workflows.none if branch is active_workflows)
    - navigation.authenticating (NOT ^navigation.authenticating)

19. VERIFY ALL TARGETS EXIST before generating transitions:
    - For every "to_state" you generate, verify that the state exists in your "states" array.
    - If you reference "navigation.app_idle", make sure you have a state at that path.
    - If you're unsure about the branch name, use "navigation" for UI states and "active_workflows" for workflow states.
    - Missing targets = broken state machine = user data loss.

20. NEVER mix branch names:
    - If the navigation branch is "navigation", always use "navigation.X"
    - If the workflow branch is "active_workflows", always use "active_workflows.X"
    - DO NOT use "workflows.X" if the branch is "active_workflows"
    - DO NOT use "nav.X" if the branch is "navigation"

21. EVERY ERROR STATE MUST HAVE CONDITIONAL RETRY WITH GUARDS:
    - For EVERY error state (or error_handler sub-state), you MUST generate TWO RETRY transitions:
      a) RETRY_FETCH with guard "canRetry" → goes back to the loading state of the same parent
      b) RETRY_FETCH with guard "!canRetry" → goes to session_expired or max_retries_exceeded state
    - The guard "canRetry" means: context.retryCount < 3 (user can retry up to 3 times)
    - When the positive retry branch is taken, use action "incrementRetryCount" to update context
    - This is UNIVERSAL — every error state in every app needs this pattern
    
    EXAMPLE (follow this exact pattern for every error state):
    - {{"from_state": "error", "to_state": "loading", "event": "RETRY_FETCH", "guard": "canRetry", "actions": ["incrementRetryCount"]}}
    - {{"from_state": "error", "to_state": "session_expired", "event": "RETRY_FETCH", "guard": "!canRetry"}}
    - {{"from_state": "error", "to_state": "app_idle", "event": "CANCEL"}}

22. USE CONTEXT-AWARE ACTIONS FOR STATE MUTATIONS:
    - These actions are UNIVERSAL and work for any app:
      * "incrementRetryCount" → assign {{ retryCount: ctx.retryCount + 1 }}
      * "setPreviousState" → assign {{ previousState: meta.state.value }}
      * "clearErrors" → assign {{ errors: [] }}
      * "resetRetryCount" → assign {{ retryCount: 0 }}
    - Use "incrementRetryCount" on retry transitions (paired with guard "canRetry")
    - Use "setPreviousState" on navigation transitions that go deeper into the app
    - Use "clearErrors" when entering a fresh loading state
    - Use "resetRetryCount" when the user successfully completes an operation

23. EVERY WORKFLOW STEP MUST HAVE EMERGENCY EXITS:
    - For states inside the active_workflows branch (benchmark, purchase_group, price_alert, etc.),
      add these emergency transitions:
      a) SESSION_EXPIRED → navigation.session_expired (user's auth token expired mid-workflow)
      b) NETWORK_LOST → navigation.error (network disconnected mid-workflow)
    - These events allow the state machine to gracefully exit a workflow if the app state changes
    - This is UNIVERSAL — every workflow in every app can be interrupted by session expiry or network loss
    
    EXAMPLE (add these to every workflow step's "on" transitions):
    - {{"from_state": "benchmark.discovery", "to_state": "navigation.session_expired", "event": "SESSION_EXPIRED"}}
    - {{"from_state": "benchmark.discovery", "to_state": "navigation.error", "event": "NETWORK_LOST"}}

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
- [ ] app_initial has START_APP → authenticating transition
- [ ] authenticating has AUTH_SUCCESS → dashboard and AUTH_FAILED → auth_error transitions
- [ ] No state path exceeds 3 levels deep (branch.parent.child = OK, branch.parent.child.grandchild = WRONG)
- [ ] No recursive patterns (app_initial.app_initial, loading.loading, error.error_handler.error_handler)
- [ ] Events are domain-specific (VIEW_BENCHMARK_RESULTS, not NEXT; CONFIRM_GROUP_PURCHASE, not CONFIRM)

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
8. **STRUCTURAL VALIDITY — COMPOUND STATES MUST HAVE `initial`**:
   - Every state that has sub-states (nested "states" object) MUST define an "initial" property specifying which sub-state to enter first.
   - Without "initial", the state machine freezes — it cannot enter any sub-state.
   - Check: if a state has "states": { ... } but NO "initial": "...", flag it as CRITICAL.
   - Common pattern: loading → ready → error sub-states must have "initial": "loading".
   - Error handler sub-states must have "initial": "error_handler".
9. **ANTI-INCEPTION CHECK**:
   - Never allow error_handler to be nested inside another error_handler.
   - If you see states like "error.error_handler.error_handler", the machine has infinite nesting.
   - Each state should have AT MOST ONE level of error_handler sub-state.
10. **REACHABILITY**:
    - Every state must be reachable from the initial state via some transition path.
    - If a state exists but no transition leads to it, it's a "ghost state" — remove it or add the missing transition.
    - The fuzzer reports "Reachable: X/Y" — if X is much smaller than Y, there are unreachable states.
11. **AUTH FLOW ENFORCEMENT**:
    - Every app MUST have an authentication flow. Check for these states:
      * authenticating (or similar — the state that handles login)
      * auth_success (or similar — after successful authentication)
      * auth_error (or similar — when authentication fails)
      * session_expired (or similar — when the user's session expires)
    - The initial state should transition to the authenticating state on START_APP.
    - If NO auth-related states exist, flag as CRITICAL-004: "Missing Authentication Flow".
    - This is NON-NEGOTIABLE: an app without auth is a security vulnerability.
12. **HIERARCHY ENFORCEMENT — NO FLAT STATES**:
    - Every main screen/page MUST have loading → ready → error sub-states.
    - Flat states (states with entry actions but NO sub-states) are UX failures.
    - Check: if a state like "dashboard" or "catalog" has entry actions but no "states" object,
      flag it as CRITICAL-003: "Missing Loading State — user sees blank screen".
    - The "initial" property of such states MUST be "loading".
13. **SELF-REFERENCING TRANSITION DETECTION**:
    - A transition where from_state == to_state is a logic error (infinite loop).
    - Check ALL transitions: if "from_state" equals "to_state", flag as CRITICAL.
    - Common case: GLOBAL_EXIT pointing to the same state it's defined in.
    - GLOBAL_EXIT must always point to a DIFFERENT state (e.g., navigation.app_idle).
    - Also check for transitions like {"from": "app_initial", "to": "#navigation.app_initial"}
      where the target resolves back to the source state.
"""
