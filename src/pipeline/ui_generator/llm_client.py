"""
LLM client for UI Generator - handles calls to various LLM providers.
"""

import os
import sys

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import LLM_CONFIG, DEFAULT_PROVIDER


class LLMConfig:
    """Configuration for LLM calls."""
    
    def __init__(self, provider: str = "", model: str = "", api_key: str = "", base_url: str = ""):
        self.provider = provider or os.environ.get("LLM_PROVIDER", DEFAULT_PROVIDER)
        self.model = model or os.environ.get("LLM_MODEL", "")
        self.api_key = api_key or os.environ.get("LLM_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
        self.base_url = base_url or os.environ.get("LLM_BASE_URL", "")


def call_llm(prompt: str, system_prompt: str = "", max_tokens: int = 4096, config: LLMConfig = None) -> str:
    """Calls the configured LLM and returns the response."""
    if config is None:
        config = LLMConfig()
    
    if config.provider in ("openai", "google", "dashscope"):
        return _call_openai_compatible(prompt, system_prompt, max_tokens, config)
    elif config.provider == "anthropic":
        return _call_anthropic(prompt, system_prompt, max_tokens, config)
    elif config.provider == "ollama":
        return _call_ollama(prompt, system_prompt, max_tokens, config)
    else:
        raise ValueError(f"Unsupported LLM provider: {config.provider}")


def _call_openai_compatible(prompt: str, system_prompt: str, max_tokens: int, config: LLMConfig) -> str:
    """Calls any OpenAI-compatible API (OpenAI, DashScope, Google Gemini)."""
    try:
        from openai import OpenAI
        
        base_url = config.base_url
        model = config.model
        if not base_url and config.provider in LLM_CONFIG:
            base_url = LLM_CONFIG[config.provider]["base_url"]
        if not model and config.provider in LLM_CONFIG:
            model = LLM_CONFIG[config.provider]["model"]
            
        client = OpenAI(api_key=config.api_key, base_url=base_url or None)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        response = client.chat.completions.create(
            model=model or "gpt-4o",
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.7,
        )
        return response.choices[0].message.content
    except ImportError:
        print("❌ Install openai: pip install openai")
        sys.exit(1)
    except Exception as e:
        print(f"❌ OpenAI-compatible API Error ({config.provider}): {e}")
        sys.exit(1)


def _call_anthropic(prompt: str, system_prompt: str, max_tokens: int, config: LLMConfig) -> str:
    """Calls Anthropic API."""
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=config.api_key)
        
        model = config.model
        if not model and "anthropic" in LLM_CONFIG:
            model = LLM_CONFIG["anthropic"]["model"]
        
        response = client.messages.create(
            model=model or "claude-3-5-sonnet-20241022",
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


def _call_ollama(prompt: str, system_prompt: str, max_tokens: int, config: LLMConfig) -> str:
    """Calls Ollama API (local)."""
    try:
        import requests
        url = config.base_url or "http://localhost:11434"
        payload = {
            "model": config.model or "llama3",
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