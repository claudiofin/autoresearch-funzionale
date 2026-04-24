"""Shared LLM client wrapper.

Provides a unified interface for calling the LLM across all pipeline stages.
Uses the openai SDK with configurable provider/base_url/model via environment variables.
"""

import os
import sys
import json

# Import config from parent
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import LLM_CONFIG, DEFAULT_PROVIDER


def get_llm_client():
    """Configure and return the LLM client.
    
    Returns:
        tuple: (openai_client, model_name)
    
    Raises:
        SystemExit: If LLM_API_KEY is not set or openai is not installed.
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
        return OpenAI(api_key=api_key, base_url=base_url), model
    except ImportError:
        print("❌ ERROR: openai not installed.")
        sys.exit(1)


def extract_json_from_response(content: str) -> str:
    """Extract JSON from LLM response, handling markdown fences.
    
    Args:
        content: Raw LLM response text.
    
    Returns:
        Extracted JSON string.
    """
    # Remove markdown fences
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()
    
    # Find first { and last }
    start = content.find("{")
    end = content.rfind("}")
    if start >= 0 and end > start:
        content = content[start:end+1]
    
    return content.strip()


def call_llm(
    prompt: str,
    system_message: str = "You are an expert. Respond ONLY with valid JSON.",
    max_retries: int = 3,
    timeout: int = 180,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> dict:
    """Call the LLM with retry logic and JSON extraction.
    
    Args:
        prompt: User prompt text.
        system_message: System role message.
        max_retries: Number of retry attempts.
        timeout: Request timeout in seconds.
        temperature: LLM temperature.
        max_tokens: Maximum response tokens.
    
    Returns:
        Parsed JSON dict from LLM response.
    
    Raises:
        SystemExit: If all retry attempts fail.
    """
    client, model = get_llm_client()
    
    print(f"  🤖 Calling LLM ({model})...")
    
    for attempt in range(max_retries):
        try:
            print(f"  Attempt {attempt + 1}/{max_retries}...")
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
            
            content = response.choices[0].message.content.strip()
            json_str = extract_json_from_response(content)
            
            data = json.loads(json_str)
            print(f"  ✅ LLM returned {len(json.dumps(data))} chars of valid JSON")
            return data
            
        except json.JSONDecodeError as e:
            print(f"  Attempt {attempt + 1} failed (invalid JSON): {e}")
            # Try to extract manually
            try:
                start = content.find("{")
                end = content.rfind("}")
                if start >= 0 and end > start:
                    partial = content[start:end+1]
                    data = json.loads(partial)
                    print(f"  ✅ JSON extracted manually: {len(partial)} chars")
                    return data
            except:
                pass
            continue
        except Exception as e:
            print(f"  Attempt {attempt + 1} failed: {e}")
            continue
    
    print("❌ ERROR: All LLM attempts failed.")
    print("   The system cannot work without an LLM.")
    sys.exit(1)