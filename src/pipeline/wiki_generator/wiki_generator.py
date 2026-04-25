"""
LLM Wiki Generator - Creates the Memory Bank for AI Agents.

Generates 6 essential files inside output/llm_wiki/:
- @TECH_RULES.md       (Absolute technical rules, stack, prohibitions)
- @DOMAIN_GLOSSARY.md  (Business domain vocabulary)
- @SECURITY_RULES.md   (Security rules, threat model, compliance)
- @ARCHITECTURE_MAP.md (Architecture map, where to save files)
- project_index.md     (Navigable index of all files)
- active_context.md    (Development log, updated by the agent)

Hybrid approach: if files exist, they are skipped (preserving memory).
With --force, all files are regenerated from scratch.
"""

import os
import glob
from pathlib import Path


# ---------------------------------------------------------------------------
# LLM Prompts
# ---------------------------------------------------------------------------

PROMPT_TECH_RULES = """You are a Lead Software Architect. I have this project context.
I need to instruct a team of AI Agents (Junior/Mid Developers) to write code.

Create a file with strict rules containing:
1. **Tech Stack** (frameworks, libraries, tools)
2. **ABSOLUTE RULES** (what NOT to do - LLMs understand prohibitions well)
3. **Code Standards** (conventions, mandatory patterns)
4. **Folder Structure** (where to save files)

Be telegraphic. Use bullet points. Do not write discursive paragraphs.

## Project Context:
{context}
"""

PROMPT_DOMAIN_GLOSSARY = """You are a Technical Writer expert in Domain-Driven Design.
I need to create a glossary that maps business domain terms to variable/function names in the code.

Analyze the context and create a Markdown table with:
- **Business Term** (e.g., "Clinic", "Smart Group")
- **Code Name** (e.g., `ClinicProfile`, `PurchaseGroup`)
- **Description** (1 line)

Be consistent with the nomenclature already used in the project.

## Project Context:
{context}
"""

PROMPT_SECURITY_RULES = """You are a Senior Security Architect. I have this project context and related security specifications.
I need to instruct a team of AI Agents (Junior/Mid Developers) to write secure code.

Create a file with security rules containing:
1. **ABSOLUTE SECURITY RULES** (what NEVER to do - input validation, SQL injection, XSS, etc.)
2. **Authentication and Authorization** (how to handle sessions, tokens, permissions)
3. **Data Protection** (encryption, PII, data handling)
4. **API Security** (rate limiting, CORS, input sanitization)
5. **Compliance** (GDPR, HIPAA, or other frameworks relevant to the domain)
6. **Security Checklist** (what to verify before every deploy)

Be telegraphic. Use bullet points. Do not write discursive paragraphs.
Use emoji for categorization: 🔐 Auth, 🛡️ Data, 🚫 Prohibited, ✅ Mandatory, ⚠️ Warning.

## Project Context:
{context}
"""

PROMPT_ARCHITECTURE_MAP = """You are a Senior Software Architect. I need to create an architecture map that tells AI Agents exactly where to save the files they create.

Analyze the context and create a file with:
1. **Directory Structure Rules** (each folder and what goes inside)
2. **File Naming Conventions** (how to name files)
3. **Component Placement Rules** (where to put each type of component)
4. **Import/Export Patterns** (how to organize imports)

Be telegraphic. Use bullet points.

## Project Context:
{context}
"""

PROMPT_PROJECT_INDEX = """You are a Librarian. Create a Markdown index (Table of Contents)
of all documentation files generated for this project.

Organize the index by categories:
- 📋 Functional Specifications
- 🎨 Design System & UI
- 🏗️ Backend Architecture
- 🔄 State Machines (XState)
- 📊 Reports & Analysis

For each file, write:
- Link to the file
- 1-line description
- When it was generated (if visible)

## Project Context:
{context}
"""

SYSTEM_PROMPT = "You are an AI Technical Architect. Respond only with the requested Markdown content, without additional text."


# ---------------------------------------------------------------------------
# Core Functions
# ---------------------------------------------------------------------------

def _load_context(context_path: str) -> str:
    """Load and merge context files."""
    parts = []
    
    # Load project_context.md
    if os.path.exists(context_path):
        with open(context_path, "r", encoding="utf-8") as f:
            parts.append(f.read())
    
    # Load spec.md if it exists
    spec_path = context_path.replace("/context/project_context.md", "/spec/spec.md")
    if os.path.exists(spec_path):
        with open(spec_path, "r", encoding="utf-8") as f:
            parts.append(f"\n\n{'='*60}\nSPECIFICATIONS:\n{'='*60}\n\n" + f.read())
    
    # Load DESIGN.md if it exists
    design_path = context_path.replace("/context/project_context.md", "/ui_specs/DESIGN.md")
    if os.path.exists(design_path):
        with open(design_path, "r", encoding="utf-8") as f:
            parts.append(f"\n\n{'='*60}\nDESIGN SYSTEM:\n{'='*60}\n\n" + f.read())
    
    return "\n\n".join(parts)


def _call_llm_for_wiki(prompt: str) -> str:
    """
    Call the LLM using the same client as other pipelines.
    Dynamic import to avoid circular dependencies.
    """
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    
    from pipeline.kanban_task.llm_client import call_llm, LLMConfig
    
    config = LLMConfig()
    return call_llm(prompt, SYSTEM_PROMPT, max_tokens=4096, config=config)


def generate_tech_rules(context: str, output_dir: str, force: bool = False) -> str:
    """Generate @TECH_RULES.md with the project's technical rules."""
    output_path = os.path.join(output_dir, "@TECH_RULES.md")
    
    if os.path.exists(output_path) and not force:
        print(f"  ⏭️  @TECH_RULES.md already exists, skipping (use --force to regenerate)")
        return output_path
    
    print("  🧠 Generating @TECH_RULES.md...")
    prompt = PROMPT_TECH_RULES.format(context=context[:6000])
    content = _call_llm_for_wiki(prompt)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# 🛠️ Tech Rules & Constraints\n\n"
                f"> Automatically generated by the LLM Wiki pipeline.\n"
                f"> This file contains the project's absolute technical rules.\n\n"
                f"{content}\n")
    
    print(f"  ✅ @TECH_RULES.md generated ({len(content)} chars)")
    return output_path


def generate_domain_glossary(context: str, output_dir: str, force: bool = False) -> str:
    """Generate @DOMAIN_GLOSSARY.md with the domain vocabulary."""
    output_path = os.path.join(output_dir, "@DOMAIN_GLOSSARY.md")
    
    if os.path.exists(output_path) and not force:
        print(f"  ⏭️  @DOMAIN_GLOSSARY.md already exists, skipping (use --force to regenerate)")
        return output_path
    
    print("  📖 Generating @DOMAIN_GLOSSARY.md...")
    prompt = PROMPT_DOMAIN_GLOSSARY.format(context=context[:6000])
    content = _call_llm_for_wiki(prompt)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# 📖 Domain Glossary\n\n"
                f"> Maps business domain terms to code names.\n"
                f"> Automatically generated by the LLM Wiki pipeline.\n\n"
                f"{content}\n")
    
    print(f"  ✅ @DOMAIN_GLOSSARY.md generated ({len(content)} chars)")
    return output_path


def generate_security_rules(context: str, output_dir: str, force: bool = False) -> str:
    """Generate @SECURITY_RULES.md with the project's security rules."""
    output_path = os.path.join(output_dir, "@SECURITY_RULES.md")
    
    if os.path.exists(output_path) and not force:
        print(f"  ⏭️  @SECURITY_RULES.md already exists, skipping (use --force to regenerate)")
        return output_path
    
    print("  🔐 Generating @SECURITY_RULES.md...")
    prompt = PROMPT_SECURITY_RULES.format(context=context[:6000])
    content = _call_llm_for_wiki(prompt)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# 🔐 Security Rules & Guidelines\n\n"
                f"> Automatically generated by the LLM Wiki pipeline.\n"
                f"> This file contains the project's absolute security rules.\n\n"
                f"{content}\n")
    
    print(f"  ✅ @SECURITY_RULES.md generated ({len(content)} chars)")
    return output_path


def generate_project_index(context: str, output_dir: str, base_output_dir: str = "output") -> str:
    """Generate project_index.md with the index of all files."""
    output_path = os.path.join(output_dir, "project_index.md")
    
    print("  🗺️  Generating project_index.md...")
    
    # Scan all .md files in output/
    md_files = glob.glob(f"{base_output_dir}/**/*.md", recursive=True)
    md_files = [f for f in md_files if "llm_wiki" not in f and "kanban_tasks" not in f]
    md_files.sort()
    
    # Create the file list
    file_list = "\n".join([f"- `{f}`" for f in md_files])
    
    # Prompt with actual file list
    prompt = PROMPT_PROJECT_INDEX.format(context=context[:4000])
    prompt += f"\n\n## Available Files:\n{file_list}"
    
    content = _call_llm_for_wiki(prompt)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# 📂 Project Index\n\n"
                f"> Complete index of all documentation files.\n"
                f"> Automatically generated by the LLM Wiki pipeline.\n\n"
                f"{content}\n")
    
    print(f"  ✅ project_index.md generated ({len(content)} chars, {len(md_files)} files)")
    return output_path


def generate_architecture_map(context: str, output_dir: str, force: bool = False) -> str:
    """Generate @ARCHITECTURE_MAP.md with the project's architecture map."""
    output_path = os.path.join(output_dir, "@ARCHITECTURE_MAP.md")
    
    if os.path.exists(output_path) and not force:
        print(f"  ⏭️  @ARCHITECTURE_MAP.md already exists, skipping (use --force to regenerate)")
        return output_path
    
    print("  🗺️  Generating @ARCHITECTURE_MAP.md...")
    prompt = PROMPT_ARCHITECTURE_MAP.format(context=context[:6000])
    content = _call_llm_for_wiki(prompt)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# 🗺️ Architecture Map\n\n"
                f"> Automatically generated by the LLM Wiki pipeline.\n"
                f"> This file tells AI Agents where to save files.\n\n"
                f"{content}\n")
    
    print(f"  ✅ @ARCHITECTURE_MAP.md generated ({len(content)} chars)")
    return output_path


def generate_active_context(output_dir: str, force: bool = False) -> str:
    """Generate active_context.md with a pre-filled template."""
    output_path = os.path.join(output_dir, "active_context.md")
    
    if os.path.exists(output_path) and not force:
        print(f"  ⏭️  active_context.md already exists, skipping (use --force to regenerate)")
        return output_path
    
    print("  🔄 Creating active_context.md (template)...")
    
    template = """# 🔄 Active Context (Development Log)

> This file is updated by the AI Agent (Cline/Claude) at the end of each task.
> It tracks the current state, open issues, and next steps.

---

## 📌 Current Phase

**Current Sprint:** To be defined
**Current Task:** None
**Status:** 🟡 Waiting for development to start

---

## ✅ Completed Tasks (Last 24h)

_No tasks completed yet._

---

## 🚧 Blockers / Open Issues

_No blockers at the moment._

---

## ➡️ Next Steps

1. Start Sprint 1 (Foundations)
2. Complete TASK-01 (Repo Initialization)
3. Complete TASK-02 (Design Tokens Configuration)

---

## 📝 Notes

_Space for additional notes from the agent or user._
"""
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(template)
    
    print(f"  ✅ active_context.md created (template)")
    return output_path


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def generate_wiki(context_path: str = "output/context/project_context.md",
                  output_dir: str = "output/llm_wiki",
                  base_output_dir: str = "output",
                  force: bool = False) -> dict:
    """
    Generate all LLM Wiki files.
    
    Returns:
        dict with paths of generated files
    """
    os.makedirs(output_dir, exist_ok=True)
    
    print("\n" + "=" * 60)
    print("🧠 LLM WIKI GENERATOR")
    print("=" * 60)
    print()
    
    # Load context
    print(f"📄 Loading context from {context_path}...")
    context = _load_context(context_path)
    print(f"  ✅ Context loaded ({len(context)} chars)")
    
    # Generate the 6 files
    results = {}
    results["tech_rules"] = generate_tech_rules(context, output_dir, force)
    results["domain_glossary"] = generate_domain_glossary(context, output_dir, force)
    results["security_rules"] = generate_security_rules(context, output_dir, force)
    results["architecture_map"] = generate_architecture_map(context, output_dir, force)
    results["project_index"] = generate_project_index(context, output_dir, base_output_dir)
    results["active_context"] = generate_active_context(output_dir, force)
    
    print()
    print("=" * 60)
    print("✅ LLM Wiki generated successfully!")
    print(f"📁 Directory: {output_dir}/")
    print("=" * 60)
    print()
    print("Generated files:")
    for key, path in results.items():
        print(f"  • {os.path.basename(path)}: {path}")
    
    return results