"""
Analyst LLM for automatic functional analysis.

Reads the context and generates structured suggestions to expand the functional
specification with states, transitions, and edge cases.

LLM is REQUIRED - no simulated fallback.

Output: Validated JSON.

Usage:
    python run.py analyst --context output/context/project_context.md --output output/analyst/analyst_suggestions.json
    
Environment Variables:
    LLM_API_KEY: Your API key (REQUIRED)
    LLM_PROVIDER: Provider (openai, anthropic, google, dashscope)
    LLM_BASE_URL: Base API URL (optional, override)
    LLM_MODEL: Model to use (optional, override)
"""

import os
import sys
import json
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import LLM_CONFIG, DEFAULT_PROVIDER


# ---------------------------------------------------------------------------
# LLM Client
# ---------------------------------------------------------------------------

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


def call_llm(context_text: str, critic_feedback: str = None, max_retries: int = 3) -> dict:
    """Call the LLM to analyze the context and generate suggestions."""
    client, model = get_llm_client()
    
    # Truncate context to avoid truncated responses
    max_context = 8000  # characters
    if len(context_text) > max_context:
        # Keep the most important sections
        lines = context_text.split("\n")
        important_lines = []
        for line in lines:
            if line.startswith("##") or line.startswith("###") or line.startswith("-") or line.startswith("|"):
                important_lines.append(line)
        context_text = "\n".join(important_lines[:200])  # max 200 important lines
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
"""
    
    print(f"  🤖 Calling LLM ({model}), context: {len(context_text)} chars...")
    
    for attempt in range(max_retries):
        try:
            print(f"  Attempt {attempt + 1}/{max_retries}...")
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Analyst LLM for functional analysis")
    parser.add_argument("--context", type=str, default="output/context/project_context.md",
                        help="Context file")
    parser.add_argument("--output", type=str, default="output/analyst/analyst_suggestions.json",
                        help="Output JSON file")
    parser.add_argument("--critic-feedback", type=str, default=None,
                        help="Critic feedback JSON file (for iterative correction)")
    args = parser.parse_args()
    
    print("=" * 50)
    print("ANALYST - Automatic Functional Analysis")
    print("=" * 50)
    print(f"Context: {args.context}")
    print(f"Output: {args.output}")
    if args.critic_feedback:
        print(f"Critic feedback: {args.critic_feedback}")
    print()
    
    # Read context
    with open(args.context, "r", encoding="utf-8") as f:
        context_text = f.read()
    
    # Read critic feedback if provided
    critic_text = None
    if args.critic_feedback and os.path.exists(args.critic_feedback):
        with open(args.critic_feedback, "r", encoding="utf-8") as f:
            critic_data = json.load(f)
        # Extract only critical issues for the prompt
        critical_issues = critic_data.get("critical_issues", [])
        if critical_issues:
            critic_text = json.dumps(critical_issues, indent=2, ensure_ascii=False)
            print(f"  📋 Critic feedback loaded: {len(critical_issues)} critical issues")
    
    print(f"Context loaded: {len(context_text)} characters")
    print("  🚀 Running with LLM...")
    
    # Call LLM
    result = call_llm(context_text, critic_feedback=critic_text)
    
    # Write output
    os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Output written: {args.output}")
    print(f"  Patterns: {len(result.get('patterns_detected', []))}")
    print(f"  States: {len(result.get('states', []))}")
    print(f"  Transitions: {len(result.get('transitions', []))}")
    print(f"  Edge cases: {len(result.get('edge_cases', []))}")
    print(f"  Events: {len(result.get('events', []))}")


if __name__ == "__main__":
    main()