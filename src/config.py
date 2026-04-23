"""
Configurazione centrale per il sistema di analisi funzionale.

LLM Provider Configuration:
    - Default: OpenAI (gpt-4o)
    - Supportati: openai, anthropic, google, dashscope
    - Override: env vars LLM_BASE_URL, LLM_MODEL

Usage:
    from config import LLM_CONFIG, DEFAULT_PROVIDER
    
    provider = os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER)
    base_url = os.getenv("LLM_BASE_URL", LLM_CONFIG[provider]["base_url"])
    model = os.getenv("LLM_MODEL", LLM_CONFIG[provider]["model"])
"""

# ---------------------------------------------------------------------------
# LLM Provider Configuration
# ---------------------------------------------------------------------------

LLM_CONFIG = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o",
        "description": "OpenAI GPT-4o (default)",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "model": "claude-3-5-sonnet-20241022",
        "description": "Anthropic Claude 3.5 Sonnet",
    },
    "google": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.0-flash",
        "description": "Google Gemini 2.0 Flash",
    },
    "dashscope": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "description": "Alibaba DashScope (Qwen)",
    },
}

# Provider di default
DEFAULT_PROVIDER = "openai"

# ---------------------------------------------------------------------------
# Loop Configuration
# ---------------------------------------------------------------------------

DEFAULT_MAX_ITERATIONS = 10
DEFAULT_TIME_BUDGET = 1200  # 20 minuti
OUTPUT_DIR = "./output"
DEFAULT_CHECKPOINT_DIR = "./output/loop_checkpoints"
FORCE_ALL_ITERATIONS = False

# ---------------------------------------------------------------------------
# Fuzzer Configuration
# ---------------------------------------------------------------------------

DEFAULT_FUZZ_ROUNDS = 50
DEFAULT_TIMEOUT_SECONDS = 300

# ---------------------------------------------------------------------------
# File Paths
# ---------------------------------------------------------------------------

SPEC_FILE = "output/spec.md"
MACHINE_FILE = "output/spec_machine.json"
FUZZ_REPORT_FILE = "output/fuzz_report.json"
CRITIC_FEEDBACK_FILE = "output/critic_feedback.json"
ANALYST_OUTPUT_FILE = "output/analyst_suggestions.json"
PROJECT_CONTEXT_FILE = "output/project_context.md"