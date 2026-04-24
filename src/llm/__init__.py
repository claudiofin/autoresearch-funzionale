"""LLM layer - Shared client and prompts for all pipeline stages."""

from .client import get_llm_client, call_llm
from .prompts import (
    ANALYST_PROMPT,
    SPEC_PROMPT,
    CRITIC_PROMPT,
)

__all__ = [
    "get_llm_client",
    "call_llm",
    "ANALYST_PROMPT",
    "SPEC_PROMPT",
    "CRITIC_PROMPT",
]