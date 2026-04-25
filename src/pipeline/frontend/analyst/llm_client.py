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
    
    prompt = (
        "Analyze this project context and generate a functional specification.\n\n"
        "Context:\n"
        + context_text + "\n"
        + critic_section + "\n\n"
        "Respond ONLY with valid JSON (no markdown, no extra code):\n\n"
        "{\n"
        '  "patterns_detected": ["pattern1", "pattern2"],\n'
        '  "states": [\n'
        '    {"name": "state_name", "description": "desc", "entry": [], "exit": []}\n'
        "  ],\n"
        '  "transitions": [\n'
        '    {"from": "state1", "to": "state2", "event": "EVENT_NAME", "guard": null}\n'
        "  ],\n"
        '  "edge_cases": [\n'
        '    {"id": "EC001", "scenario": "desc", "trigger": "cause", "expected": "behavior", "priority": "high"}\n'
        "  ],\n"
        '  "events": [\n'
        '    {"name": "EVENT_NAME", "description": "desc", "payload": {}}\n'
        "  ],\n"
        '  "workflows": [\n'
        '    {\n'
        '      "id": "workflow_name",\n'
        '      "name": "Human readable name",\n'
        '      "description": "What this workflow accomplishes",\n'
        '      "trigger": "EVENT_THAT_STARTS_WORKFLOW",\n'
        '      "steps": ["step1", "step2", "step3"],\n'
        '      "cross_page_events": ["EVENT1", "EVENT2"],\n'
        '      "completion_events": ["COMPLETED", "CANCELLED"]\n'
        '    }\n'
        "  ],\n"
        '  "ux_questions": ["question1"],\n'
        '  "confidence": 0.8\n'
        "}\n\n"
        "CRITICAL Rules:\n"
        "1. 100% valid JSON - no text outside the JSON\n"
        "2. State names in lowercase_snake_case\n"
        "3. Events in UPPERCASE_WITH_UNDERSCORE\n"
        "4. Include at least: loading, error, success, empty states\n"
        "5. Include transitions for: forward/back navigation, error, cancellation\n"
        "6. Edge cases: timeout, network error, expired session, invalid input\n\n"
        "FUNDAMENTAL RULE - NO DEAD-END STATES:\n"
        "Every state MUST have at least one exit transition (except the final success state).\n"
        "- ERROR state: must have RETRY transition → loading state, and CANCEL → initial state\n"
        "- LOADING state: must have CANCEL transition → previous state, TIMEOUT → error state\n"
        "- EMPTY state: must have REFRESH transition → loading state, GO_BACK → initial state\n"
        "- SUCCESS state: may have no transitions (it's a final state)\n"
        "- SESSION_EXPIRED state: must have REAUTHENTICATE transition → loading state, CANCEL → initial state\n\n"
        'Verification: for each state you generate, ask yourself "how does the user exit this state?" and add the corresponding transition.\n\n'
        "RULE FOR INTERACTIVE SCREENS (COMPOUND STATES):\n"
        "For each main screen inside the app (e.g., dashboard, catalog, offers, profile, settings),\n"
        'DO NOT create empty/flat states. Each screen MUST be a "Compound State" with its own\n'
        "local micro-states for a professional UX:\n\n"
        "  - An initial \"loading\" sub-state (to show local skeleton/shimmer effects)\n"
        "  - A \"ready\" sub-state (data loaded successfully, render the actual content)\n"
        '  - An "error" sub-state (to handle API failures scoped to that component only)\n\n'
        "Global navigation events (NAVIGATE_*, MAPS_*) MUST stay at the PARENT level (outside\n"
        'the compound state\'s internal "on" block), so the user can switch pages even if a\n'
        "component is in local error state.\n\n"
        "Example structure for a catalog screen:\n"
        '  "catalog": {\n'
        '    "initial": "loading",\n'
        '    "states": {\n'
        '      "loading": {\n'
        '        "entry": ["showCatalogShimmer"],\n'
        '        "on": { "FETCH_SUCCESS": "ready", "FETCH_ERROR": "error" }\n'
        "      },\n"
        '      "ready": {\n'
        '        "entry": ["renderCatalogGrid"],\n'
        '        "on": { "APPLY_FILTER": "loading", "LOCAL_REFRESH": "loading" }\n'
        "      },\n"
        '      "error": {\n'
        '        "entry": ["showInlineErrorCard"],\n'
        '        "on": { "RETRY": "loading" }\n'
        "      }\n"
        "    },\n"
        '    "on": {\n'
        '      "NAVIGATE_DASHBOARD": "dashboard",\n'
        '      "NAVIGATE_OFFERS": "offers"\n'
        "    }\n"
        "  }\n\n"
        "This creates the state path: success.catalog.loading → success.catalog.ready\n\n"
        "============================================================================\n"
        "WORKFLOWS - CROSS-PAGE FEATURE ORCHESTRATION (NEW - CRITICAL)\n"
        "============================================================================\n\n"
        "IDENTIFY WORKFLOWS FROM THE INPUT CONTEXT.\n"
        "Look for VERBS OF ACTION (partecipare, confrontare, ricevere, unirsi, monitorare, vedere, scoprire)\n"
        "that describe multi-step processes spanning multiple screens.\n\n"
        "A WORKFLOW is NOT a page. A workflow is a JOURNEY that may:\n"
        "  - Start from one page (e.g., Catalog)\n"
        "  - Show an overlay/modal (e.g., Price Comparison)\n"
        "  - Require confirmation (e.g., Join Group modal)\n"
        "  - End with tracking/feedback (e.g., Group Progress)\n\n"
        "For each workflow, generate a COMPOUND STATE that:\n"
        "  1. Has its own internal micro-states (discovery, viewing, joining, tracking)\n"
        "  2. Can be 'activated' from any page via a trigger event\n"
        "  3. ALWAYS has a completion event (COMPLETED, CANCELLED, DISMISSED) that returns to 'none'\n"
        "  4. Uses cross-page events to navigate between workflow steps\n\n"
        "WORKFLOW LIFECYCLE:\n"
        "  none → [TRIGGER_EVENT] → discovery → viewing → joining → tracking → COMPLETED/CANCELLED → none\n\n"
        "PARALLEL STATES ARCHITECTURE:\n"
        "The root state machine uses type: 'parallel' with two branches:\n"
        "  - 'navigation': tracks which PAGE the user is physically on (dashboard, catalog, etc.)\n"
        "  - 'active_workflows': tracks which WORKFLOW is currently active (none, benchmark_workflow, etc.)\n\n"
        "This allows the user to:\n"
        "  - Be 'inside' a workflow (e.g., tracking a purchase group)\n"
        "  - While simultaneously navigating to different pages (e.g., check the dashboard)\n"
        "  - The workflow state persists because it lives in a parallel branch\n\n"
        "WORKFLOW EXAMPLE - Benchmarking Prezzi Farmaci:\n"
        '  "workflows": [\n'
        '    {\n'
        '      "id": "benchmark_workflow",\n'
        '      "name": "Benchmarking Prezzi Farmaci",\n'
        '      "description": "User compares their drug prices with network average and joins purchase groups",\n'
        '      "trigger": "VIEW_BENCHMARK",\n'
        '      "steps": ["discovery", "viewing", "joining", "tracking"],\n'
        '      "cross_page_events": ["VIEW_BENCHMARK", "JOIN_GROUP", "CONFIRM_JOIN", "GO_BACK"],\n'
        '      "completion_events": ["COMPLETED", "CANCELLED"]\n'
        '    }\n'
        "  ]\n\n"
        "WORKFLOW EXAMPLE - Purchase Group:\n"
        '  "workflows": [\n'
        '    {\n'
        '      "id": "purchase_group_workflow",\n'
        '      "name": "Gruppo d\'Acquisto",\n'
        '      "description": "User discovers, joins, and tracks a smart purchase group",\n'
        '      "trigger": "JOIN_GROUP",\n'
        '      "steps": ["browsing", "confirming", "tracking", "completed"],\n'
        '      "cross_page_events": ["JOIN_GROUP", "CONFIRM_JOIN", "TRACK_PROGRESS", "GO_BACK"],\n'
        '      "completion_events": ["GROUP_COMPLETE", "CANCELLED", "DISMISSED"]\n'
        '    }\n'
        "  ]\n\n"
        "RULES FOR WORKFLOWS:\n"
        "1. Every workflow MUST have a completion event that returns to 'none'\n"
        "2. Every workflow step MUST have a GO_BACK or CANCEL transition\n"
        "3. Workflows are IDENTIFIED from the input context, not invented\n"
        "4. If the input mentions 'voglio vedere se risparmio' → that's a benchmark workflow\n"
        "5. If the input mentions 'gruppi d\'acquisto' → that's a purchase group workflow\n"
        "6. If the input mentions 'alert prezzi' → that's a price alert workflow\n"
        "7. Cross-page events connect workflow steps to navigation events\n\n"
        "VERB-TO-WORKFLOW MAPPING:\n"
        '  "confrontare prezzi" → benchmark_workflow\n'
        '  "partecipare a gruppo" → purchase_group_workflow\n'
        '  "ricevere alert" → price_alert_workflow\n'
        '  "monitorare progresso" → tracking_workflow\n'
        '  "scoprire opportunità" → discovery_workflow\n'
    )
    
    streaming_tag = " [streaming]" if use_streaming else ""
    print(f"  🤖 Calling LLM ({model}){streaming_tag}, context: {len(context_text)} chars...")
    
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
