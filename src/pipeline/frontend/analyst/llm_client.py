"""
LLM client for analyst - generates functional suggestions from context.
"""

import os
import sys
import json

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import LLM_CONFIG, DEFAULT_PROVIDER


def get_llm_client():
    """Configure the LLM client."""
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


def call_llm(context_text: str, critic_feedback: str = None, max_retries: int = 3) -> dict:
    """Call the LLM to analyze the context and generate suggestions."""
    client, model = get_llm_client()
    
    provider = os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER)
    use_streaming = (provider == "nvidia")
    
    # Truncate context to avoid truncated responses
    max_context = 8000  # characters
    if len(context_text) > max_context:
        lines = context_text.split("\n")
        important_lines = []
        for line in lines:
            if line.startswith("##") or line.startswith("###") or line.startswith("-") or line.startswith("|"):
                important_lines.append(line)
        context_text = "\n".join(important_lines[:200])
        if len(context_text) > max_context:
            context_text = context_text[:max_context]
    
    # Build the prompt with optional critic feedback
    critic_section = ""
    if critic_feedback:
        critic_section = f"""

CRITIC FEEDBACK (FIX THESE ISSUES):
{critic_feedback}

INSTRUCTIONS:
- Carefully analyze the critical_issues listed by the critic
- For EACH critical issue, modify the state machine to resolve it
- Priority: 1) Dead-end states (add exit transitions), 2) Logic errors (fix transitions), 3) Missing flows (add missing states/transitions)
- Keep everything else unchanged if not mentioned in the feedback
"""
    
    prompt = f"""Analyze this project context and generate a functional specification.

Context:
{context_text}
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

RULE FOR INTERACTIVE SCREENS (COMPOUND STATES):
For each main screen inside the app (e.g., dashboard, catalog, offers, profile, settings),
DO NOT create empty/flat states. Each screen MUST be a "Compound State" with its own
local micro-states for a professional UX:

  - An initial "loading" sub-state (to show local skeleton/shimmer effects)
  - A "ready" sub-state (data loaded successfully, render the actual content)
  - An "error" sub-state (to handle API failures scoped to that component only)

Global navigation events (NAVIGATE_*, MAPS_*) MUST stay at the PARENT level (outside
the compound state's internal "on" block), so the user can switch pages even if a
component is in local error state.

Example structure for a catalog screen:
  "catalog": {
    "initial": "loading",
    "states": {
      "loading": {
        "entry": ["showCatalogShimmer"],
        "on": { "FETCH_SUCCESS": "ready", "FETCH_ERROR": "error" }
      },
      "ready": {
        "entry": ["renderCatalogGrid"],
        "on": { "APPLY_FILTER": "loading", "LOCAL_REFRESH": "loading" }
      },
      "error": {
        "entry": ["showInlineErrorCard"],
        "on": { "RETRY": "loading" }
      }
    },
    "on": {
      "NAVIGATE_DASHBOARD": "dashboard",
      "NAVIGATE_OFFERS": "offers"
    }
  }

This creates the state path: success.catalog.loading → success.catalog.ready
"""
    
    print(f"  🤖 Calling LLM ({model}){' [streaming]' if use_streaming else ''}, context: {len(context_text)} chars...")
    
    for attempt in range(max_retries):
        try:
            print(f"  Attempt {attempt + 1}/{max_retries}...")
            
            if use_streaming:
                # NVIDIA NIM: use streaming WITHOUT thinking to avoid JSON contamination
                content = _call_llm_streaming_no_thinking(
                    client, model,
                    "You are a Senior Product Manager. Respond ONLY with valid JSON. Start with { and end with }. No markdown, no extra text.",
                    prompt, 0.3, 4096, 180
                )
            else:
                response = client.chat.completions.create(
                    timeout=180,
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are a Senior Product Manager. Respond ONLY with valid JSON. Start with { and end with }. No markdown, no extra text."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=4096,
                )
                content = response.choices[0].message.content.strip()
            
            # Extract JSON from any markdown
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
