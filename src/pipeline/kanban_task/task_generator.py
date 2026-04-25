"""
Core logic for Kanban Task Generator.

Functions:
- gather_all_markdown_context: Scans output/ and collects all .md files
- generate_kanban_plan_llm: Calls LLM to create initial epic/sprint/task plan
- refine_plan_loop: Iteratively refines the plan (dependencies, parallelization)
- generate_task_markdown: Formats a single task as an agent-friendly Markdown file
- generate_master_plan: Creates the MASTER_PLAN.md roadmap
"""

import json
import os
import glob
import re
import time
from pathlib import Path

from pipeline.kanban_task.llm_client import call_llm, LLMConfig


# ---------------------------------------------------------------------------
# Context Gathering
# ---------------------------------------------------------------------------

def gather_all_markdown_context(base_dir: str) -> str:
    """
    Recursively scans base_dir and merges the content of all .md files found.
    Automatically skips the kanban_tasks folder to avoid reading old tasks.
    """
    combined_context = ""
    md_files = glob.glob(f"{base_dir}/**/*.md", recursive=True)
    
    # Sort files by logical priority
    priority_order = [
        "project_context.md",
        "spec.md",
        "spec_machine.json",  # even if not .md, could be useful
        "DESIGN.md",
        "backend_spec.md",
        "ci_cd_spec.md",
    ]
    
    # Filter and sort
    filtered_files = []
    for file_path in md_files:
        # Skip kanban_tasks to avoid reading old tasks
        if "kanban_tasks" in file_path:
            continue
        # Skip files that are not .md
        if not file_path.endswith(".md"):
            continue
        filtered_files.append(file_path)
    
    # Sort by priority
    def priority_key(filepath: str) -> int:
        filename = os.path.basename(filepath)
        for i, priority in enumerate(priority_order):
            if filename == priority:
                return i
        return len(priority_order)  # non-priority files at the end
    
    filtered_files.sort(key=priority_key)
    
    print(f"📚 Found {len(filtered_files)} Markdown context files. Assembling...")
    
    for file_path in filtered_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                combined_context += f"\n\n{'='*60}\n"
                combined_context += f"FILE: {file_path}\n"
                combined_context += f"{'='*60}\n\n"
                # Truncate huge files to avoid token limit
                max_chars = 5000
                combined_context += content[:max_chars] + (
                    "\n...[TRUNCATED]..." if len(content) > max_chars else ""
                )
        except Exception as e:
            print(f"  ⚠️ Cannot read {file_path}: {e}")
    
    return combined_context


# ---------------------------------------------------------------------------
# LLM Plan Generation
# ---------------------------------------------------------------------------

def generate_kanban_plan_llm(context: str, config: LLMConfig) -> dict:
    """
    Uses the LLM to create the initial plan of Epics, Sprints and Tasks in JSON.
    """
    prompt = f"""You are a Technical Project Manager expert in Agentic Software Engineering and Scrum.
You must analyze all the project's technical documentation and plan the development for a team of autonomous AI Agents (like Cline or Claude).

## Golden Rules for the Kanban Plan:
1. **Sprint Decomposition:** Divide the work into logical Sprints (Sprint 1: Foundations, Sprint 2: Core Features, Sprint 3: Advanced, etc.)
2. **Blocking Dependencies:** Identify which tasks MUST be done before others.
3. **Parallelization (Multi-Agent):** Specify which tasks within the same Sprint can be assigned simultaneously to multiple AI Agents without creating conflicts.
4. **Hyper-limited Scope:** A task must not exceed 10-15 minutes of AI processing. If a task is too large, break it down.
5. **Explicit Context:** Each task must indicate which files to read before starting.
6. **Mandatory LLM Wiki:** Each task MUST have these files at the beginning of the "files_to_read" array:
   - "output/llm_wiki/@TECH_RULES.md"
   - "output/llm_wiki/project_index.md"
   This is MANDATORY. The AI Agent must read these rules before writing any code.

## Project Documentation:
{context}

## Instructions:
Break down the project into Sprints and Tasks. Respond EXCLUSIVELY with a JSON formatted like this:

```json
{{
  "project_name": "Project Name",
  "sprints": [
    {{
      "sprint_number": 1,
      "id": "Setup_Architecture",
      "sprint_goal": "Initial Setup and Base Architecture",
      "tasks": [
        {{
          "id": "TASK-01",
          "title": "Repo_Initialization_and_Dependencies",
          "description": "Create the React project, install Tailwind, Zustand and XState. Configure the linter and formatter.",
          "files_to_read": ["output/context/project_context.md"],
          "acceptance_criteria": [
            "React project created and compiles without errors",
            "Tailwind CSS configured",
            "Linter and formatter active"
          ],
          "dependencies": [],
          "can_be_parallelized": false,
          "parallel_group": null
        }},
        {{
          "id": "TASK-02",
          "title": "Design_System_Implementation",
          "description": "Apply DESIGN.md tokens to Tailwind configuration (colors, fonts, spacing, shadows).",
          "files_to_read": ["output/ui_specs/DESIGN.md"],
          "acceptance_criteria": [
            "Design system colors available as Tailwind classes",
            "Fonts and typography configured",
            "Base components use correct tokens"
          ],
          "dependencies": ["TASK-01"],
          "can_be_parallelized": false,
          "parallel_group": null
        }}
      ]
    }},
    {{
      "sprint_number": 2,
      "id": "Frontend_Core",
      "sprint_goal": "Core Screens and UI Components Development",
      "tasks": [
        {{
          "id": "TASK-03",
          "title": "Base_Components_Buttons_Cards_Input",
          "description": "Create base UI components: Button, Card, Input, using Design System tokens.",
          "files_to_read": ["output/ui_specs/DESIGN.md", "output/ui_specs/states/UI_*.md"],
          "acceptance_criteria": [
            "Button, Card, Input components created",
            "Use Design System colors and fonts",
            "Responsive and accessible"
          ],
          "dependencies": ["TASK-02"],
          "can_be_parallelized": true,
          "parallel_group": "A"
        }},
        {{
          "id": "TASK-04",
          "title": "Login_Screen",
          "description": "Implement the Login screen according to UI specifications.",
          "files_to_read": ["output/ui_specs/screens/Login.md", "output/ui_specs/DESIGN.md"],
          "acceptance_criteria": [
            "Working login form",
            "Field validation",
            "Style consistent with Design System"
          ],
          "dependencies": ["TASK-02"],
          "can_be_parallelized": true,
          "parallel_group": "A"
        }}
      ]
    }}
  ]
}}
```

**Important:**
- Respond ONLY with the JSON, no text before or after.
- `dependencies` must be arrays of task IDs (e.g., ["TASK-01", "TASK-02"]).
- `can_be_parallelized: true` means the task can be executed by one agent while others work on other tasks in the same sprint.
- `parallel_group` is an identifier (e.g., "A", "B") for groups of tasks that can be parallel.
- If a task has no dependencies, use `dependencies: []`.
"""
    
    system_prompt = "You are an AI Technical Project Manager. Respond only with valid JSON. Do not add text outside the JSON."
    
    response = call_llm(prompt, system_prompt, max_tokens=8192, config=config)
    
    # Clean JSON extraction
    json_match = re.search(r'\{.*\}', response, re.DOTALL)
    if json_match:
        try:
            plan = json.loads(json_match.group())
            # Basic validation
            if "sprints" not in plan:
                raise ValueError("JSON does not contain the 'sprints' field")
            return plan
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")
    raise ValueError("The LLM did not return a valid JSON for the Kanban plan.")


# ---------------------------------------------------------------------------
# Plan Refinement Loop
# ---------------------------------------------------------------------------

def refine_plan_loop(plan: dict, context: str, num_steps: int, config: LLMConfig) -> dict:
    """
    Iteratively refines the plan to improve:
    - Step 1 (decomposition): already done in generate_kanban_plan_llm
    - Step 2 (dependencies): analyzes and corrects dependencies between tasks
    - Step 3+ (optimization): optimizes parallelization and sprint allocation
    """
    current_plan = plan
    
    for step in range(1, num_steps):
        print(f"  🔄 Refinement step {step + 1}/{num_steps}...")
        
        if step == 1:
            # Dependency analysis
            current_plan = _refine_dependencies(current_plan, context, config)
        else:
            # Sprint optimization and parallelization
            current_plan = _refine_optimization(current_plan, context, config)
        
        time.sleep(1)  # Rate limiting
    
    return current_plan


def _refine_dependencies(plan: dict, context: str, config: LLMConfig) -> dict:
    """
    Refines dependencies between tasks. Ensures that:
    - No task depends on a future task
    - Transitive dependencies are resolved
    - No cycles exist
    """
    plan_json = json.dumps(plan, indent=2, ensure_ascii=False)
    
    prompt = f"""You are an AI Project Manager. Analyze the current plan and correct the dependencies between tasks.

## Current Plan:
```json
{plan_json}
```

## Validation Rules:
1. A task can depend ONLY on tasks in the same sprint or previous sprints
2. There must be no cyclic dependencies
3. If a task depends on TASK-01 and TASK-01 depends on TASK-02, then TASK-02 must come first
4. Remove redundant dependencies (if A→B and B→C, A→C is not needed)

## Instructions:
Respond with the updated plan JSON, with corrected dependencies.
Maintain the same original JSON structure.

```json
{{
  "project_name": "...",
  "sprints": [...]
}}
```

Respond ONLY with the JSON, no additional text.
"""
    
    system_prompt = "You are an AI that validates task dependencies. Respond only with valid JSON."
    
    try:
        response = call_llm(prompt, system_prompt, max_tokens=8192, config=config)
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except Exception as e:
        print(f"  ⚠️ Dependency refinement failed: {e}. Using current plan.")
    
    return plan


def _refine_optimization(plan: dict, context: str, config: LLMConfig) -> dict:
    """
    Optimizes sprint breakdown and parallelization.
    """
    plan_json = json.dumps(plan, indent=2, ensure_ascii=False)
    
    prompt = f"""You are an AI Project Manager expert in sprint optimization.
Analyze the plan and optimize:
1. Task distribution across sprints (balance the load)
2. Parallelization (maximize parallel tasks to reduce time)
3. Critical path (identify blocking tasks)

## Current Plan:
```json
{plan_json}
```

## Instructions:
Respond with the optimized plan JSON. Maintain the same structure.
You can:
- Move tasks between sprints to balance
- Change can_be_parallelized and parallel_group
- Add or remove tasks if necessary

Respond ONLY with the JSON, no additional text.
```json
{{
  "project_name": "...",
  "sprints": [...]
}}
```
"""
    
    system_prompt = "You are an AI that optimizes sprint plans. Respond only with valid JSON."
    
    try:
        response = call_llm(prompt, system_prompt, max_tokens=8192, config=config)
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except Exception as e:
        print(f"  ⚠️ Optimization refinement failed: {e}. Using current plan.")
    
    return plan


# ---------------------------------------------------------------------------
# Task Markdown Generation
# ---------------------------------------------------------------------------

def generate_task_markdown(task: dict, sprint_number: int, sprint_goal: str) -> str:
    """
    Formats a single ticket as a perfect Markdown file for the AI Agent.
    """
    files_to_read = task.get("files_to_read", [])
    acceptance_criteria = task.get("acceptance_criteria", [])
    dependencies = task.get("dependencies", [])
    can_parallelize = task.get("can_be_parallelized", False)
    parallel_group = task.get("parallel_group")
    
    # Files to read - add LLM Wiki header if present
    wiki_files = [f for f in files_to_read if "llm_wiki" in f]
    if wiki_files:
        wiki_header = "🧠 **LLM Wiki (Memory Bank):** These files contain the project's absolute technical rules. READ THEM BEFORE CODING.\n\n"
        files_str = wiki_header + "\n".join([f"- `{f}`" for f in files_to_read])
    else:
        files_str = "\n".join([f"- `{f}`" for f in files_to_read]) if files_to_read else "- None specific"
    
    # Acceptance criteria
    ac_str = "\n".join([f"- [ ] {ac}" for ac in acceptance_criteria]) if acceptance_criteria else "- [ ] Verify that the task is completed"
    
    # Dependencies
    if dependencies:
        deps_str = "⚠️ **BLOCKED BY:** You must verify that these tasks are completed before starting:\n"
        deps_str += "\n".join([f"- `{d}`" for d in dependencies])
    else:
        deps_str = "🟢 **READY TO START:** No blocking dependencies."
    
    # Parallelization
    parallel_str = ""
    if can_parallelize and parallel_group:
        parallel_str = f"🚀 **PARALLELIZABLE:** This task is part of group **[{parallel_group}]**. It can be assigned to an agent while others work on other tasks in the same group."
    elif can_parallelize:
        parallel_str = "🚀 **PARALLELIZABLE:** This task can be executed in parallel with other tasks in the same sprint."
    else:
        parallel_str = "🧱 **SEQUENTIAL:** This task must be executed sequentially (blocking dependencies)."
    
    return f"""# {task['id']}: {task['title']}

**Sprint:** {sprint_number} — {sprint_goal}
**Status:** ⏳ To Do
**Priority:** {"🔴 High" if dependencies else "🟡 Medium"}

---

## 🚦 Pre-Flight Checks (For the AI Agent)

{deps_str}

{parallel_str}

---

## 🎯 Task Objective

{task.get('description', 'No description available.')}

---

## 📚 Required Context

Before writing code or making changes, make sure you have read and understood these files:

{files_str}

---

## ✅ Acceptance Criteria (Definition of Done)

Before closing this task and considering it complete, verify that you have met all these points:

{ac_str}

---

## 📝 Notes for the Agent

- Work in small steps. Make frequent commits with clear messages (e.g., `feat({task['id']}): ...`).
- Stop and ask the user for confirmation if you encounter ambiguity in the requirements.
- If a context file does not exist, proceed with best practices and report the issue.
- After completing all acceptance criteria, update the Status to `✅ Done`.
"""


# ---------------------------------------------------------------------------
# Master Plan Generation
# ---------------------------------------------------------------------------

def generate_master_plan(plan: dict, output_dir: str) -> str:
    """
    Creates a MASTER_PLAN.md file with the complete roadmap and sprint dependencies.
    """
    project_name = plan.get("project_name", "Project")
    
    md = f"""# 🗺️ Master Plan: {project_name}

> Automatically generated by the Kanban Task Generator pipeline.
> This file is the source of truth for the development plan.

---

"""
    
    total_tasks = 0
    for sprint in plan.get("sprints", []):
        sprint_num = sprint.get("sprint_number", "?")
        sprint_id = sprint.get("id", f"Sprint {sprint_num}")
        sprint_goal = sprint.get("sprint_goal", "")
        tasks = sprint.get("tasks", [])
        
        md += f"## Sprint {sprint_num}: {sprint_goal}\n\n"
        md += f"**Goal:** {sprint_goal}\n"
        md += f"**Task count:** {len(tasks)}\n\n"
        
        for task in tasks:
            task_id = task.get("id", "?")
            task_title = task.get("title", "Untitled")
            dependencies = task.get("dependencies", [])
            can_parallelize = task.get("can_be_parallelized", False)
            parallel_group = task.get("parallel_group", "")
            
            # Dependency info
            if dependencies:
                deps_str = f"*(Depends on: {', '.join(dependencies)})*"
            else:
                deps_str = "*(Free Start)*"
            
            # Parallelization info
            if can_parallelize and parallel_group:
                parallel_str = f"⚡ Parallelizable [group {parallel_group}]"
            elif can_parallelize:
                parallel_str = "⚡ Parallelizable"
            else:
                parallel_str = "🧱 Sequential"
            
            md += f"- [ ] **{task_id}**: {task_title} {parallel_str} {deps_str}\n"
            total_tasks += 1
        
        md += "\n---\n\n"
    
    # Summary
    md += f"## 📊 Summary\n\n"
    md += f"- **Total Sprints:** {len(plan.get('sprints', []))}\n"
    md += f"- **Total Tasks:** {total_tasks}\n"
    md += f"\n> 💡 **How to use this plan:**\n"
    md += f"> 1. Open the `kanban_tasks/` folder in your IDE\n"
    md += f"> 2. Start from TASK-01 (or tasks without dependencies)\n"
    md += f"> 3. For parallelizable tasks, open multiple Cline/Claude instances\n"
    md += f"> 4. Each task is a self-contained Markdown file with all the necessary context\n"
    
    master_plan_path = os.path.join(output_dir, "MASTER_PLAN.md")
    with open(master_plan_path, "w", encoding="utf-8") as f:
        f.write(md)
    
    print(f"  🗺️ Master Plan generated: {master_plan_path}")
    return master_plan_path