"""Markdown spec generator.

Generates the spec.md file with flows, edge cases, error handling, and API contracts.
"""

import json
from datetime import datetime


def generate_spec_markdown(
    machine: dict,
    llm_data: dict,
    statechart: str,
    sequence: str,
    violations: list = None,
) -> str:
    """Generate the full spec.md content.
    
    Args:
        machine: The XState machine dict.
        llm_data: LLM-generated data (flows, edge_cases, etc.).
        statechart: PlantUML state chart string.
        sequence: PlantUML sequence diagram string.
        violations: List of critical rule violation messages.
    
    Returns:
        Complete spec.md content string.
    """
    edge_cases = llm_data.get("edge_cases", [])
    flows = llm_data.get("flows", [])
    endpoints = llm_data.get("api_endpoints", [])
    error_handling = llm_data.get("error_handling", [])
    data_validation = llm_data.get("data_validation", [])
    
    # Edge cases markdown
    edge_cases_md = "| ID | Scenario | Expected | Priority |\n|----|----------|----------|----------|\n"
    for ec in edge_cases:
        edge_cases_md += f"| {ec['id']} | {ec['scenario']} | {ec['expected_behavior']} | {ec['priority']} |\n"
    
    # Flows markdown
    flows_md = ""
    for flow in flows:
        flows_md += f"\n### {flow['name']}\n"
        for step in flow.get("steps", []):
            flows_md += f"1. **Trigger**: {step.get('trigger', '')}\n"
            flows_md += f"   **Action**: {step.get('action', '')}\n"
            flows_md += f"   **Outcome**: {step.get('expected_outcome', '')}\n"
            if step.get('error_scenario'):
                flows_md += f"   **Error**: {step['error_scenario']}\n"
    
    # Endpoints markdown
    endpoints_md = ""
    for ep in endpoints:
        endpoints_md += f"\n#### {ep['method']} {ep['path']}\n"
        endpoints_md += f"- **Description**: {ep.get('description', '')}\n"
    
    # Error handling table
    if error_handling:
        error_handling_md = "| Code | Type | User Message | Action |\n|--------|------|------------------|--------|\n"
        for err in error_handling:
            error_handling_md += f"| {err.get('code', '')} | {err.get('type', '')} | \"{err.get('message', '')}\" | {err.get('action', '')} |\n"
    else:
        error_handling_md = "| Code | Type | User Message | Action |\n|--------|------|------------------|--------|\n"
        error_handling_md += "| 500 | Generic Error | \"Si è verificato un errore.\" | Riprova |\n"
    
    # Data validation table
    if data_validation:
        data_validation_md = "| Field | Type | Required | Pattern | Max Length |\n|-------|------|--------------|---------|------------|\n"
        for val in data_validation:
            req = "Yes" if val.get('required') else "No"
            data_validation_md += f"| {val.get('field', '')} | {val.get('type', '')} | {req} | {val.get('pattern', '')} | {val.get('max_length', '')} |\n"
    else:
        data_validation_md = "*No data validation fields specified.*"
    
    # Violations section
    violations_md = ""
    if violations:
        violations_md = "\n---\n\n## ⚠️ Critical Rule Violations\n\nThe following critical rules were violated. The LLM should fix these in the next iteration.\n\n"
        for v in violations:
            violations_md += f"- ❌ {v}\n"
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    states_count = len(machine['states'])
    transitions_count = sum(len(s.get('on', {})) for s in machine['states'].values())
    edge_cases_count = len(edge_cases)
    error_types_count = len(error_handling) if error_handling else 1
    
    spec_content = f"""# Functional Specification

Generated: {timestamp}

> Specification automatically generated from project context.

---

## 1. Overview

### 1.1 Scope
- User flows
- State machine (executable XState)
- Edge case analysis
- Error handling
- API contracts

---

## 2. User Flows
{flows_md if flows_md else "*No flows generated*"}

---

## 3. State Machine

### 3.1 State Diagram (PlantUML)

```plantuml
{statechart}
```

### 3.2 XState Configuration

```json
{json.dumps(machine, indent=2)}
```

---

## 4. Sequence Diagram (PlantUML)

```plantuml
{sequence}
```

---

## 5. Edge Cases

{edge_cases_md if edge_cases else "*No edge cases generated*"}

---

## 6. Error Handling

### 6.1 Error Types

{error_handling_md}

### 6.2 Error States

The state machine handles errors through dedicated states that:
- Log the error for debugging
- Show appropriate messages to the user
- Offer recovery options (retry, cancel, contact support)

---

## 7. Data Validation

### 7.1 Validation Rules

{data_validation_md}

### 7.2 Validation Feedback

- Inline validation on blur
- Summary validation on submit
- Clear messages with instructions

---

## 8. API Contract
{endpoints_md if endpoints_md else "*No endpoints generated*"}

---

## 9. Metrics

### 9.1 Analysis Coverage

- States defined: {states_count}
- Transitions defined: {transitions_count}
- Edge cases identified: {edge_cases_count}
- Error types handled: {error_types_count}

---

## Appendix A: Original Context

The original project context is in `project_context.md`.
{violations_md}
"""
    return spec_content