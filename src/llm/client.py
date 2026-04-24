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
        tuple: (openai_client, model_name, provider_name)
    
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
        return OpenAI(api_key=api_key, base_url=base_url), model, provider
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


def clean_markdown_response(content: str) -> str:
    """Clean markdown code blocks from LLM response.
    
    Some LLMs wrap their output in ```markdown ... ``` or ``` ... ``` even when
    asked to return plain text. This function strips those wrappers.
    
    Args:
        content: Raw LLM response text.
    
    Returns:
        Cleaned text without markdown code block wrappers.
    """
    content = content.strip()
    
    # Remove ```markdown ... ``` wrapper
    if content.startswith("```markdown"):
        content = content[len("```markdown"):]
    # Remove ```json ... ``` wrapper
    elif content.startswith("```json"):
        content = content[len("```json"):]
    # Remove generic ``` ... ``` wrapper
    elif content.startswith("```"):
        content = content[3:]
    
    # Remove trailing ```
    if content.endswith("```"):
        content = content[:-3]
    
    return content.strip()


def call_llm(
    prompt: str,
    system_message: str = "You are an expert. Respond ONLY with valid JSON.",
    max_retries: int = 3,
    timeout: int = 180,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    exit_on_failure: bool = True,
) -> dict:
    """Call the LLM with retry logic and JSON extraction.
    
    Supports streaming for NVIDIA NIM provider (extracts reasoning_content + content).
    
    Args:
        prompt: User prompt text.
        system_message: System role message.
        max_retries: Number of retry attempts.
        timeout: Request timeout in seconds.
        temperature: LLM temperature.
        max_tokens: Maximum response tokens.
        exit_on_failure: If True, call sys.exit(1) on failure. If False, return None.
    
    Returns:
        Parsed JSON dict from LLM response, or None if exit_on_failure=False and all retries fail.
    
    Raises:
        SystemExit: If all retry attempts fail and exit_on_failure=True.
    """
    client, model, provider = get_llm_client()
    use_streaming = (provider == "nvidia")
    
    print(f"  🤖 Calling LLM ({model}){' [streaming]' if use_streaming else ''}...")
    
    for attempt in range(max_retries):
        try:
            print(f"  Attempt {attempt + 1}/{max_retries}...")
            
            if use_streaming:
                # NVIDIA NIM: use streaming WITHOUT thinking for JSON responses
                # (thinking can cause reasoning output to contaminate the JSON)
                content = _call_llm_streaming(client, model, system_message, prompt, temperature, max_tokens, timeout, enable_thinking=False)
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
    if exit_on_failure:
        print("   The system cannot work without an LLM.")
        sys.exit(1)
    else:
        print("   Returning None (exit_on_failure=False).")
        return None


def _call_llm_streaming(client, model: str, system_message: str, prompt: str, 
                         temperature: float, max_tokens: int, timeout: int,
                         enable_thinking: bool = False) -> str:
    """Call LLM with streaming (for NVIDIA NIM with reasoning_content).
    
    Accumulates both reasoning_content and regular content from streaming chunks.
    
    Args:
        enable_thinking: If True, enables reasoning_content (for text/markdown output).
            Set to False for JSON responses to avoid reasoning contaminating the output.
    
    Returns:
        Full accumulated content string (reasoning + final content).
    """
    print(f"  🔄 Streaming response...")
    
    extra_body = {}
    if enable_thinking:
        extra_body["chat_template_kwargs"] = {"thinking": True, "reasoning_effort": "high"}
    
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
        extra_body=extra_body if extra_body else None,
    )
    
    full_content = ""
    for chunk in response:
        if not getattr(chunk, "choices", None):
            continue
        # Extract reasoning_content (NVIDIA NIM specific) — only when thinking is enabled
        reasoning = getattr(chunk.choices[0].delta, "reasoning_content", None)
        if reasoning:
            print(reasoning, end="", flush=True)
        # Extract regular content
        if chunk.choices and chunk.choices[0].delta.content is not None:
            content_chunk = chunk.choices[0].delta.content
            print(content_chunk, end="", flush=True)
            full_content += content_chunk
    
    print()  # newline after streaming
    return full_content


def call_llm_text(
    prompt: str,
    system_message: str = "You are an expert. Respond with text only.",
    max_retries: int = 3,
    timeout: int = 180,
    temperature: float = 0.3,
    max_tokens: int = 8192,
) -> str:
    """Call the LLM and return cleaned text response (not JSON).
    
    Supports streaming for NVIDIA NIM provider (extracts reasoning_content + content).
    
    Use this for generating Markdown, documentation, or any non-JSON output.
    Automatically strips markdown code block wrappers (```markdown, ```, etc.).
    
    Args:
        prompt: User prompt text.
        system_message: System role message.
        max_retries: Number of retry attempts.
        timeout: Request timeout in seconds.
        temperature: LLM temperature.
        max_tokens: Maximum response tokens.
    
    Returns:
        Cleaned text string from LLM response.
    
    Raises:
        SystemExit: If all retry attempts fail.
    """
    client, model, provider = get_llm_client()
    use_streaming = (provider == "nvidia")
    
    print(f"  🤖 Calling LLM ({model}){' [streaming]' if use_streaming else ''}...")
    
    for attempt in range(max_retries):
        try:
            print(f"  Attempt {attempt + 1}/{max_retries}...")
            
            if use_streaming:
                # NVIDIA NIM: use streaming WITH thinking for text/markdown responses
                content = _call_llm_streaming(client, model, system_message, prompt, temperature, max_tokens, timeout, enable_thinking=True)
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
                content = response.choices[0].message.content.strip()
            
            cleaned = clean_markdown_response(content)
            print(f"  ✅ LLM returned {len(cleaned)} chars of text")
            return cleaned
            
        except Exception as e:
            print(f"  Attempt {attempt + 1} failed: {e}")
            continue
    
    print("❌ ERROR: All LLM attempts failed.")
    print("   The system cannot work without an LLM.")
    sys.exit(1)
