"""
LLM client for critic - performs in-depth critical analysis of specifications.
"""

import os
import sys
import json

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import LLM_CONFIG, DEFAULT_PROVIDER


def get_llm_client():
    """Create LLM client. Returns None if LLM_API_KEY is not set."""
    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key:
        return None, None
    
    try:
        from openai import OpenAI
    except ImportError:
        return None, None
    
    provider = os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER)
    
    if provider in LLM_CONFIG:
        base_url = os.getenv("LLM_BASE_URL", LLM_CONFIG[provider]["base_url"])
        model = os.getenv("LLM_MODEL", LLM_CONFIG[provider]["model"])
    else:
        base_url = os.getenv("LLM_BASE_URL")
        model = os.getenv("LLM_MODEL")
        if not base_url or not model:
            return None, None
    
    return OpenAI(api_key=api_key, base_url=base_url), model


def call_llm_critic(fuzz_report: dict, spec_text: str, machine: dict, context_text: str = "") -> dict:
    """Call the LLM for in-depth critical analysis.
    
    Args:
        fuzz_report: Fuzzer report
        spec_text: Specification text
        machine: State machine
        context_text: Project context (for detecting missing flows)
    """
    client, model = get_llm_client()
    if not client:
        return None
    
    # Prepare the prompt
    fuzz_summary = json.dumps(fuzz_report.get("summary", {}), indent=2)
    bugs = json.dumps(fuzz_report.get("bugs", []), indent=2)
    
    states = machine.get("states", {})
    state_names = list(states.keys())
    transitions_list = []
    for state_name, state_config in states.items():
        for event, target in state_config.get("on", {}).items():
            if isinstance(target, dict):
                target_state = target.get("target", "")
            else:
                target_state = target
            transitions_list.append(f"{state_name} --{event}--> {target_state}")
    
    # Build the prompt with optional context
    context_section = ""
    if context_text:
        context_section = f"""
## Project Context (Original Requirements)
{context_text[:4000]}
"""
    
    prompt = f"""You are a ruthless QA Engineer and UX Reviewer. Your job is to find flaws in this functional specification.

## Fuzz Test Results
{fuzz_summary}

## Bugs Found by Fuzzer
{bugs}

## Current Specification (excerpt)
{spec_text[:3000]}

## State Machine Summary
States ({len(state_names)}): {', '.join(state_names[:20])}{'...' if len(state_names) > 20 else ''}
Initial: {machine.get('initial', 'unknown')}
Transitions ({len(transitions_list)}):
{chr(10).join(f'- {t}' for t in transitions_list[:30])}
{'...' if len(transitions_list) > 30 else ''}
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
8. **COMPOUND STATES**: Verify that each main screen (dashboard, catalog, offers, profile, settings, etc.) is a compound state with loading/ready/error sub-states. If a screen is a flat/empty state without local micro-states, flag it as a critical UX issue. Each screen should support local loading (skeleton/shimmer), local error (inline error card with retry), and local refresh without affecting the entire app.
"""
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a QA Engineer. Respond only with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=8192
        )
        
        content = response.choices[0].message.content.strip()
        # Extract JSON from response
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        return json.loads(content)
    
    except Exception as e:
        print(f"⚠️  LLM critic failed: {e}")
        return None