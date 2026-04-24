"""
Analyst LLM for automatic functional analysis.

Reads the context and generates structured suggestions to expand the functional
specification with states, transitions, and edge cases.

LLM is REQUIRED - no simulated fallback.

Output: Validated JSON.

Usage:
    python run.py analyst --context output/context/project_context.md --output output/analyst/analyst_suggestions.json
"""

import os
import sys
import json
import argparse

from pipeline.frontend.analyst.llm_client import call_llm


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