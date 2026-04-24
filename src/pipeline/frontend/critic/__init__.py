"""
Critic - Review agent for automatic functional analysis.

Analyzes fuzzer reports, specification, and project context to generate
structured feedback that the Analyst can use to improve the specification.

The Critic adopts a "Red Team" approach: actively looks for logic holes,
unhandled edge cases, ambiguous UX decisions, and MISSING FLOWS.

Usage:
    python run.py critic --fuzz-report output/fuzz_report.json --spec output/spec/spec.md --machine output/spec/spec_machine.json --context output/context/project_context.md
"""

import os
import sys
import json
import argparse
from datetime import datetime

from pipeline.frontend.critic.llm_client import call_llm_critic
from pipeline.frontend.critic.static_analyzer import static_critic_analysis


def print_critic_report(report: dict):
    """Print the critic report."""
    
    print("\n" + "=" * 60)
    print("CRITIC REVIEW REPORT")
    print("=" * 60)
    
    issues = report.get("critical_issues", [])
    ux = report.get("ux_decisions_needed", [])
    edges = report.get("edge_cases_to_add", [])
    missing = report.get("missing_flows", [])
    recs = report.get("recommendations", [])
    
    print(f"\n🔴 CRITICAL ISSUES ({len(issues)}):")
    for issue in issues:
        print(f"  [{issue['id']}] {issue['description']}")
        print(f"    Category: {issue['category']} | Severity: {issue['severity']}")
        print(f"    Suggestion: {issue['suggestion']}")
        print()
    
    print(f"\n🤔 UX DECISIONS NEEDED ({len(ux)}):")
    for decision in ux:
        print(f"  [{decision['id']}] {decision['question']}")
        print(f"    Context: {decision['context']}")
        print(f"    Options: {', '.join(decision['options'])}")
        print()
    
    print(f"\n📋 EDGE CASES TO ADD ({len(edges)}):")
    for ec in edges:
        print(f"  [{ec['id']}] {ec['scenario']}")
        print(f"    Expected: {ec['expected_behavior']} | Priority: {ec['priority']}")
        print()
    
    if missing:
        print(f"\n🚨 MISSING FLOWS ({len(missing)}):")
        for flow in missing:
            print(f"  [{flow['id']}] {flow['flow_name']}")
            print(f"    Description: {flow['description']}")
            print(f"    Business reason: {flow.get('business_reason', 'N/A')}")
            if flow.get('suggested_states'):
                print(f"    Suggested states: {', '.join(flow['suggested_states'])}")
            if flow.get('suggested_transitions'):
                for t in flow['suggested_transitions']:
                    print(f"    Suggested transition: {t.get('from', '?')} --{t.get('event', '?')}--> {t.get('to', '?')}")
        print()
    
    print(f"\n💡 RECOMMENDATIONS ({len(recs)}):")
    for rec in recs:
        print(f"  - {rec}")
    
    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Critic - Critical review of functional specification")
    parser.add_argument("--fuzz-report", type=str, default="output/spec/fuzz_report.json",
                        help="Fuzz report JSON file")
    parser.add_argument("--spec", type=str, default="output/spec/spec.md",
                        help="Spec file for context")
    parser.add_argument("--machine", type=str, default="output/spec/spec_machine.json",
                        help="State machine JSON file")
    parser.add_argument("--context", type=str, default=None,
                        help="Project context file (for missing flow detection)")
    parser.add_argument("--output", type=str, default="output/spec/critic_report.json",
                        help="Output JSON file (default: output/spec/critic_report.json)")
    parser.add_argument("--use-llm", action="store_true",
                        help="Force LLM usage even if static analysis is available")
    args = parser.parse_args()
    
    # Load fuzz report
    if not os.path.exists(args.fuzz_report):
        print(f"⚠️  Fuzz report not found: {args.fuzz_report}")
        print("   Creating empty report...")
        fuzz_report = {"summary": {}, "bugs": [], "unreachable_states": []}
    else:
        with open(args.fuzz_report, "r", encoding="utf-8") as f:
            fuzz_report = json.load(f)
    
    # Load spec
    spec_text = ""
    if os.path.exists(args.spec):
        with open(args.spec, "r", encoding="utf-8") as f:
            spec_text = f.read()
    
    # Load context (optional)
    context_text = ""
    if args.context and os.path.exists(args.context):
        with open(args.context, "r", encoding="utf-8") as f:
            context_text = f.read()
        print(f"📄 Context loaded: {len(context_text)} chars")
    
    # Load machine
    if not os.path.exists(args.machine):
        print(f"Error: Machine file not found: {args.machine}")
        sys.exit(1)
    with open(args.machine, "r", encoding="utf-8") as f:
        machine = json.load(f)
    
    print(f"🧐 Critic analyzing...")
    print(f"   Fuzz bugs: {len(fuzz_report.get('bugs', []))}")
    print(f"   Spec size: {len(spec_text)} chars")
    print(f"   States: {len(machine.get('states', {}))}")
    
    # Try LLM first if requested or if there are bugs
    llm_result = None
    if args.use_llm or fuzz_report.get("summary", {}).get("bugs_found", 0) > 0 or context_text:
        print(f"\n  🤖 Trying LLM critic...")
        llm_result = call_llm_critic(fuzz_report, spec_text, machine, context_text)
    
    # Fallback to static analysis
    if llm_result:
        print(f"  ✅ LLM critic succeeded")
        report = llm_result
    else:
        print(f"  📊 Using static critic analysis")
        report = static_critic_analysis(fuzz_report, machine)
    
    # Add metadata
    report["metadata"] = {
        "timestamp": datetime.now().isoformat(),
        "method": "llm" if llm_result else "static",
        "fuzz_report_used": os.path.exists(args.fuzz_report),
        "spec_used": os.path.exists(args.spec),
        "context_used": bool(context_text),
    }
    
    print_critic_report(report)
    
    # Save output
    output_file = args.output
    os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else ".", exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    
    print(f"\n📄 Critic feedback saved: {output_file}")
    
    # Count critical issues
    critical_count = len(report.get("critical_issues", []))
    sys.exit(0 if critical_count == 0 else 1)


if __name__ == "__main__":
    main()