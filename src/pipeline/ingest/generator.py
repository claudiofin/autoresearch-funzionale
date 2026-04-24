"""
Context markdown generator - creates unified project context from extracted data.
"""

from datetime import datetime


def generate_context_markdown(
    texts: list, 
    html_structures: list, 
    screenshots: list, 
    pdf_texts: list = None, 
    docx_texts: list = None
) -> str:
    """Generate the unified project context Markdown file."""
    
    # Merge all text sources
    all_texts = list(texts)
    if pdf_texts:
        all_texts.extend(pdf_texts)
    if docx_texts:
        all_texts.extend(docx_texts)
    
    sections = []
    
    # Header
    sections.append(f"""# Project Context
Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

This file contains the extracted context from all input files (notes, PDF, DOCX, screenshots, HTML).
It serves as the "Bible" for the functional analysis agents.

---

""")
    
    # Section 1: Business Rules (from text files, PDF, DOCX)
    sections.append("""## 1. Business Rules (Extracted from Notes)

""")
    
    if all_texts:
        for text in all_texts:
            type_label = text["type"].upper()
            sections.append(f"### [{type_label}] {text['filename']}\n")
            sections.append(f"```\n{text['content']}\n```\n\n")
    else:
        sections.append("*No text files found.*\n\n")
    
    sections.append("---\n\n")
    
    # Section 2: UI Inventory (from HTML)
    sections.append("""## 2. UI Inventory (Extracted from HTML)

""")
    
    if html_structures:
        for html in html_structures:
            structure = html["structure"]
            sections.append(f"### File: {structure['filename']}\n")
            sections.append(f"**Title:** {structure['title']}\n\n")
            
            if structure["forms"]:
                sections.append("#### Forms\n")
                for form in structure["forms"]:
                    sections.append(f"- **Action:** `{form['action']}` ({form['method']})\n")
                    for field in form["fields"]:
                        required = " (required)" if field["required"] else ""
                        sections.append(f"  - `{field['name']}`: {field['type']}{required}\n")
                        if field["pattern"]:
                            sections.append(f"    - Pattern: `{field['pattern']}`\n")
                sections.append("\n")
            
            if structure["buttons"]:
                sections.append("#### Buttons / CTA\n")
                for btn in structure["buttons"]:
                    sections.append(f"- `{btn['text']}` (type: {btn['type']})\n")
                    if btn.get("formaction"):
                        sections.append(f"  - Form action: `{btn['formaction']}`\n")
                sections.append("\n")
            
            if structure["inputs"]:
                sections.append("#### Input Fields\n")
                for inp in structure["inputs"]:
                    required = " (required)" if inp["required"] else ""
                    sections.append(f"- `{inp['name']}`: {inp['type']}{required}\n")
                sections.append("\n")
            
            if structure["links"]:
                sections.append("#### Links\n")
                for link in structure["links"]:
                    sections.append(f"- `{link['text']}` → `{link['href']}`\n")
                sections.append("\n")
            
            if structure["headings"]:
                sections.append("#### Headings Structure\n")
                for h in structure["headings"]:
                    indent = "  " * (h["level"] - 1)
                    sections.append(f"{indent}- H{h['level']}: {h['text']}\n")
                sections.append("\n")
            
            sections.append("---\n\n")
    else:
        sections.append("*No HTML files found.*\n\n")
        sections.append("---\n\n")
    
    # Section 3: Screenshots (with Vision analysis)
    sections.append("""## 3. Screenshots UI (Analyzed with Vision)

""")
    
    if screenshots:
        for ss in screenshots:
            sections.append(f"### Screenshot: {ss['filename']}\n\n")
            if ss.get("analysis"):
                sections.append(f"{ss['analysis']}\n\n")
            else:
                sections.append("*Analysis unavailable*\n\n")
            sections.append("---\n\n")
    else:
        sections.append("*No screenshots found.*\n\n")
    
    sections.append("---\n\n")
    
    # Section 4: Data Model Inference
    sections.append("""## 4. Data Model (Inferred)

Based on analysis of HTML forms and inputs:

""")
    
    inferred_fields = {}
    for html in html_structures:
        for form in html["structure"]["forms"]:
            for field in form["fields"]:
                key = field["name"] or field["id"] or "unnamed"
                if key not in inferred_fields:
                    inferred_fields[key] = {
                        "types": set(),
                        "required": False,
                        "patterns": set(),
                    }
                inferred_fields[key]["types"].add(field["type"])
                if field["required"]:
                    inferred_fields[key]["required"] = True
                if field["pattern"]:
                    inferred_fields[key]["patterns"].add(field["pattern"])
    
    if inferred_fields:
        sections.append("| Field | Type | Required | Pattern |\n")
        sections.append("|-------|------|----------|--------|\n")
        for field_name, info in sorted(inferred_fields.items()):
            types = ", ".join(sorted(info["types"]))
            patterns = ", ".join(sorted(info["patterns"])) if info["patterns"] else "-"
            required = "✓" if info["required"] else "-"
            sections.append(f"| `{field_name}` | {types} | {required} | {patterns} |\n")
        sections.append("\n")
    else:
        sections.append("*No data fields inferred from HTML forms.*\n\n")
    
    sections.append("---\n\n")
    
    # Section 5: API Endpoints (inferred)
    sections.append("""## 5. API Endpoints (Inferred)

Based on analysis of form actions:

""")
    
    endpoints = set()
    for html in html_structures:
        for form in html["structure"]["forms"]:
            if form["action"]:
                endpoints.add((form["action"], form["method"]))
        for btn in html["structure"]["buttons"]:
            if btn.get("formaction"):
                endpoints.add((btn["formaction"], "POST"))
    
    if endpoints:
        sections.append("| Endpoint | Method |\n")
        sections.append("|----------|--------|\n")
        for endpoint, method in sorted(endpoints):
            sections.append(f"| `{endpoint}` | {method} |\n")
        sections.append("\n")
    else:
        sections.append("*No API endpoints inferred.*\n\n")
    
    sections.append("---\n\n")
    
    # Section 6: Notes for Agent
    sections.append("""## 6. Notes for the Analyst Agent

This context was automatically generated. Use it as a base for:

1. **Generate user flows** (User Journey)
2. **Define application states** (State Machine)
3. **Identify edge cases** (error handling, boundary states)
4. **Create Mermaid diagrams** (Flowchart, Sequence Diagram)
5. **Generate executable XState configuration**

### Analysis Checklist:
- [ ] Does every form have a defined loading state?
- [ ] Does every API call have 4xx and 5xx error handling?
- [ ] Is there a way to cancel every intermediate operation?
- [ ] What happens if the user loses connection?
- [ ] What happens if the user presses "back" in the browser?
- [ ] Do error states show clear messages to the user?
- [ ] Is there a way to recover from an error state?

""")
    
    return "".join(sections)