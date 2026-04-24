"""
Backend Critic - critiques backend specification quality.

Checks:
- API completeness (all states mapped to endpoints?)
- Security (ACL, auth on every endpoint?)
- Resilience (timeout handling, partial success?)
- Scalability (pagination, bulk fetch issues?)
"""

import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from llm.client import call_llm


def critique_backend(backend_spec_file: str, spec_file: str, machine_file: str, output_file: str) -> dict:
    """Critique the backend specification against the state machine and spec."""
    
    # Load files
    with open(backend_spec_file, "r") as f:
        backend_spec = f.read()
    
    with open(spec_file, "r") as f:
        spec = f.read()
    
    with open(machine_file, "r") as f:
        machine = json.load(f)
    
    # Extract states and transitions for analysis
    states = machine.get("states", {})
    state_names = list(states.keys())
    
    # Build the prompt
    prompt = f"""You are a Senior Backend Critic. Analyze the backend specification and find gaps, security issues, and design flaws.

## State Machine States
{json.dumps(state_names, indent=2)}

## Backend Specification
{backend_spec}

## Frontend Specification (for context)
{spec[:3000]}

## Critique Checklist

### 1. API Completeness
- Does every `loading` state have a corresponding GET endpoint?
- Are all command events (JOIN_GROUP, CALCULATE_CLUSTER) mapped to POST/PATCH/DELETE?
- Is there a missing endpoint for any state transition?

### 2. Security
- Are all data-fetching endpoints protected with auth?
- Is there an ACL (Access Control List) for role-based access?
- Are refresh tokens properly secured (httpOnly cookie)?
- Is there rate limiting on auth endpoints?

### 3. Resilience
- Is there a strategy for partial success (some data loaded, some failed)?
- Are timeouts defined for async operations?
- Is there a fallback/cached data strategy?
- Are retry policies defined (exponential backoff)?

### 4. Scalability
- Are list endpoints paginated?
- Is there a risk of bulk data download (N+1 query problem)?
- Are cache strategies defined with appropriate TTLs?

### 5. Idempotency
- Are POST operations that should be idempotent properly handled?
- Is the idempotency key strategy clearly defined?
- Are there safeguards against double-tap/double-submit?

## Output Format

Respond ONLY with valid JSON (no markdown, no extra text):

{{
  "summary": {{
    "total_issues": 5,
    "critical_issues": [
      {{
        "id": "BEC001",
        "category": "security",
        "severity": "critical",
        "issue": "Missing auth on GET /api/catalog endpoint",
        "recommendation": "Add Authorization header validation to all GET endpoints"
      }}
    ],
    "warnings": [
      {{
        "id": "BEW001",
        "category": "scalability",
        "severity": "warning",
        "issue": "No pagination defined for catalog listing",
        "recommendation": "Add page/limit parameters to GET /api/catalog"
      }}
    ]
  }},
  "checks": {{
    "api_completeness": {{
      "passed": true,
      "details": "All loading states have corresponding endpoints"
    }},
    "security": {{
      "passed": false,
      "details": "Missing ACL for role-based access"
    }},
    "resilience": {{
      "passed": true,
      "details": "Timeout and fallback strategies defined"
    }},
    "scalability": {{
      "passed": false,
      "details": "No pagination on list endpoints"
    }},
    "idempotency": {{
      "passed": true,
      "details": "Idempotency keys defined for POST operations"
    }}
  }},
  "recommendations": [
    "Add ACL middleware for role-based access control",
    "Implement pagination on all list endpoints",
    "Add health check endpoint for monitoring"
  ]
}}
"""
    
    print(f"  🤖 Calling LLM for backend critique...")
    print(f"     States: {len(state_names)}")
    print(f"     Backend spec: {len(backend_spec)} chars")
    
    # Use exit_on_failure=False to gracefully handle LLM failures
    response = call_llm(
        prompt,
        system_message="You are a Senior Backend Critic. Respond ONLY with valid JSON. Start with { and end with }. No markdown, no extra text.",
        exit_on_failure=False
    )
    
    # Parse and write output
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    if response is None:
        # LLM failed — create a fallback critique with 0 issues
        print(f"  ⚠️  LLM failed, generating fallback critique with 0 issues")
        data = {
            "summary": {
                "total_issues": 0,
                "critical_issues": [],
                "warnings": []
            },
            "checks": {},
            "recommendations": ["LLM critique failed — manual review recommended"],
            "llm_failed": True
        }
    else:
        # response is already a parsed dict from call_llm()
        data = response
    
    with open(output_file, "w") as f:
        json.dump(data, f, indent=2)
    
    critical = data.get("summary", {}).get("critical_issues", [])
    warnings = data.get("summary", {}).get("warnings", [])
    
    print(f"  ✅ Backend critique written to {output_file}")
    print(f"     Critical issues: {len(critical)}")
    print(f"     Warnings: {len(warnings)}")
    
    return {
        "success": True,
        "output": output_file,
        "critical_count": len(critical),
        "warning_count": len(warnings)
    }