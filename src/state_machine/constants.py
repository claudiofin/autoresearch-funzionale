"""Domain configuration constants for state machine builder.

All defaults are overridable via parameters. This makes the builder
universal — works for e-commerce, IoT, social, gaming, etc.
"""

# Default state names — override via state_names parameter
DEFAULT_STATE_NAMES = {
    "initial": "app_idle",
    "workflow_none": "none",
    "loading": "loading",
    "ready": "ready",
    "error": "error",
}

# Default branch names — override via branch_names parameter
DEFAULT_BRANCH_NAMES = {
    "navigation": "navigation",
    "workflows": "active_workflows",
}

# Default event names — override via event_names parameter
DEFAULT_EVENT_NAMES = {
    "navigate": "NAVIGATE",
    "error": "ERROR",
    "retry": "RETRY",
    "cancel": "CANCEL",
    "complete": "COMPLETED",
    "data_loaded": "DATA_LOADED",
    "load_failed": "LOAD_FAILED",
    "timeout": "TIMEOUT",
}

# Default action names — override via action_names parameter
DEFAULT_ACTION_NAMES = {
    "hide_workflow": "hideWorkflowOverlay",
    "show_workflow": "showWorkflowOverlay",
    "show_loading": "showLoading",
    "hide_loading": "hideLoading",
    "show_error": "showErrorBanner",
    "hide_error": "hideErrorBanner",
    "log_error": "logError",
}

# Default guard names — override via guard_names parameter
# These are UNIVERSAL guards that work for any app
DEFAULT_GUARD_NAMES = {
    "can_retry": "canRetry",
    "has_data": "hasData",
    "has_previous_state": "hasPreviousState",
    "is_authenticated": "isAuthenticated",
    "has_network": "hasNetwork",
}

# Default emergency event names — override via emergency_events parameter
# These events allow graceful exit from any state when app conditions change
DEFAULT_EMERGENCY_EVENTS = {
    "session_expired": "SESSION_EXPIRED",
    "network_lost": "NETWORK_LOST",
    "app_background": "APP_BACKGROUND",
    "global_exit": "GLOBAL_EXIT",
}

# States that are part of the auto-generated loading/ready/error pattern
# and should NOT get their own sub_states injected.
AUTO_GENERATED_SUB_STATES = {
    "loading", "ready", "error", "calculating", "fetching", "submitting",
    "saving", "processing", "validating", "authenticating", "registering",
    "joining", "tracking", "monitoring", "deleting", "creating",
}

# XState reserved keywords that should never be state names
XSTATE_KEYWORDS = {
    "initial", "states", "on", "entry", "exit", "context", "id",
    "type", "invoke", "activities",
}

# Branch names that are structural (not orphans)
BRANCH_NAMES = {"navigation", "workflows", "active_workflows"}

# Verb prefix patterns → gerund form (universal linguistic mapping)
# Used to infer sub_state name from action name
VERB_PATTERNS = [
    ("calculate", "calculating"),
    ("compute", "calculating"),
    ("cluster", "calculating"),
    ("fetch", "fetching"),
    ("load", "loading"),
    ("get", "loading"),
    ("retrieve", "loading"),
    ("submit", "submitting"),
    ("send", "submitting"),
    ("post", "submitting"),
    ("save", "saving"),
    ("update", "saving"),
    ("store", "saving"),
    ("process", "processing"),
    ("handle", "processing"),
    ("execute", "processing"),
    ("validate", "validating"),
    ("verify", "validating"),
    ("check", "validating"),
    ("authenticate", "authenticating"),
    ("login", "authenticating"),
    ("register", "registering"),
    ("signup", "registering"),
    ("join", "joining"),
    ("track", "tracking"),
    ("monitor", "monitoring"),
    ("observe", "monitoring"),
    ("delete", "deleting"),
    ("remove", "deleting"),
    ("destroy", "deleting"),
    ("create", "creating"),
    ("add", "creating"),
    ("generate", "creating"),
]

# Default depth limits for recursive functions
DEPTH_LIMITS = {
    "walk_states": 10,
    "collect_paths": 15,
    "dedup": 15,
    "cleanup": 15,
    "process_states": 10,
    "inject_sub_states": 3,  # ANTI-FRATTALE: max 3 livelli di nidificazione (era 5)
    "get_initials": 15,
    "bfs_depth": 15,  # Max path depth for BFS reachability (prevents infinite loops)
}

# XState action mapping — extensible
# Each entry maps action_name → (type, assignment_key, value_lambda)
XSTATE_ACTION_MAP = {
    "incrementRetryCount": ("assign", "retryCount", lambda ctx: ctx.get("retryCount", 0) + 1),
    "setPreviousState": ("assign", "previousState", lambda ctx, evt, meta: meta.state.value),
    "clearErrors": ("assign", "errors", lambda ctx: []),
    "resetRetryCount": ("assign", "retryCount", lambda ctx: 0),
    "setUser": ("assign", "user", lambda ctx, evt: evt.data),
    "setLoading": ("assign", "loading", lambda ctx: True),
    "setLoaded": ("assign", "loading", lambda ctx: False),
}