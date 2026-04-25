"""
Kanban Task Generator - Generates agent-friendly tickets for Cline/Claude.

Reads all Markdown (.md) files in the output/ directory (project_context, spec, 
ui_specs, DESIGN, backend, ci_cd) and uses an LLM to decompose the project into 
Epics, Sprints, and Tasks that can be executed by autonomous AI agents.

Usage:
    python run.py kanban-task
    python run.py kanban-task --input-dir output --output-dir output/kanban_tasks --refine-steps 2
    python run.py kanban-task --dry-run
"""

import json
import os
import sys
import glob
import time
import argparse
import re
from pathlib import Path

# Add src/ to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from pipeline.kanban_task.llm_client import call_llm, LLMConfig
from pipeline.kanban_task.task_generator import (
    gather_all_markdown_context,
    generate_kanban_plan_llm,
    refine_plan_loop,
    generate_task_markdown,
    generate_master_plan,
)


def main():
    parser = argparse.ArgumentParser(
        description="Generate agent-friendly Kanban tasks from project documentation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python run.py kanban-task
    python run.py kanban-task --refine-steps 3 --dry-run
    python run.py kanban-task --input-dir output --output-dir output/kanban_tasks
        """
    )
    parser.add_argument(
        "--input-dir", 
        default="output", 
        help="Root directory to scan for .md context files (default: output)"
    )
    parser.add_argument(
        "--output-dir", 
        default="output/kanban_tasks", 
        help="Output directory for generated tasks (default: output/kanban_tasks)"
    )
    parser.add_argument(
        "--refine-steps", 
        type=int, 
        default=2,
        help="Number of refinement iterations (default: 2 = decomposition + dependencies)"
    )
    parser.add_argument(
        "--dry-run", 
        action="store_true",
        help="Show the plan without writing files"
    )
    parser.add_argument(
        "--provider", 
        choices=["openai", "anthropic", "google", "ollama", "dashscope", "coding", "nvidia"], 
        default="", 
        help="LLM Provider"
    )
    parser.add_argument(
        "--model", 
        default="", 
        help="LLM Model"
    )
    parser.add_argument(
        "--api-key", 
        default="", 
        help="LLM API Key"
    )
    parser.add_argument(
        "--base-url", 
        default="", 
        help="LLM Base URL"
    )
    parser.add_argument(
        "--force", 
        action="store_true",
        help="Overwrite existing kanban_tasks directory"
    )
    args = parser.parse_args()

    # Initialize LLM config
    llm_config = LLMConfig(
        provider=args.provider,
        model=args.model,
        api_key=args.api_key,
        base_url=args.base_url
    )
    
    if not llm_config.api_key and llm_config.provider != "ollama":
        print("❌ Set LLM_API_KEY or OPENAI_API_KEY")
        sys.exit(1)
    
    print(f"🤖 Configuration: Provider={llm_config.provider} | Model={llm_config.model}")
    print(f"📂 Input: {args.input_dir} | Output: {args.output_dir}")
    print(f"🔄 Refine steps: {args.refine_steps}")
    print()

    # Check if output directory already exists
    if os.path.exists(args.output_dir) and not args.force:
        existing_tasks = glob.glob(f"{args.output_dir}/**/*.md", recursive=True)
        if existing_tasks:
            print(f"⚠️  Output directory '{args.output_dir}' already contains {len(existing_tasks)} task files.")
            response = input("  Do you want to overwrite them? (y/N): ").strip().lower()
            if response not in ("y", "yes"):
                print("  Aborted.")
                sys.exit(0)

    # ─── STEP 1: Gather all markdown context ───
    print("📚 Step 1/4: Gathering all Markdown context files...")
    global_context = gather_all_markdown_context(args.input_dir)
    if not global_context:
        print("❌ No Markdown files found in the input directory.")
        print("   Make sure to run the other pipelines first (frontend loop, backend, ci-cd).")
        sys.exit(1)
    print(f"   ✅ Context assembled ({len(global_context)} characters)")

    # ─── STEP 2: Generate initial kanban plan ───
    print(f"\n🧠 Step 2/4: Generating kanban plan (decomposition + {args.refine_steps - 1} refinement(s))...")
    try:
        plan = generate_kanban_plan_llm(global_context, llm_config)
    except Exception as e:
        print(f"❌ Error during plan generation: {e}")
        sys.exit(1)

    # ─── STEP 3: Refine plan (dependency analysis + optimization) ───
    if args.refine_steps > 1:
        print(f"\n🔍 Step 3/4: Refining plan ({args.refine_steps - 1} iteration(s))...")
        try:
            plan = refine_plan_loop(plan, global_context, args.refine_steps, llm_config)
        except Exception as e:
            print(f"❌ Error during plan refinement: {e}")
            sys.exit(1)

    # ─── STEP 4: Dry-run or write files ───
    if args.dry_run:
        print(f"\n📋 Step 4/4: DRY RUN — Plan preview (no files written):")
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        total_tasks = sum(
            len(epic.get("tasks", [])) 
            for sprint in plan.get("sprints", []) 
            for epic in [sprint]  # hack to iterate
            for _ in [1]
        )
        # Actually count from sprints
        total_tasks = 0
        for sprint in plan.get("sprints", []):
            total_tasks += len(sprint.get("tasks", []))
        print(f"\n📊 Summary: {total_tasks} tasks in {len(plan.get('sprints', []))} sprints")
        print("\n✅ Dry run complete. Run without --dry-run to generate files.")
    else:
        print(f"\n📂 Step 4/4: Writing task files to {args.output_dir}...")
        os.makedirs(args.output_dir, exist_ok=True)

        total_tasks = 0
        for sprint in plan.get("sprints", []):
            sprint_dir = os.path.join(
                args.output_dir, 
                f"{sprint['sprint_number']:02d}_{sprint['id'].replace(' ', '_')}"
            )
            os.makedirs(sprint_dir, exist_ok=True)
            print(f"  📁 Sprint {sprint['sprint_number']}: {sprint.get('sprint_goal', sprint['id'])}")
            
            for task in sprint.get("tasks", []):
                task_filename = f"{task['id']}-{task['title']}.md"
                task_path = os.path.join(sprint_dir, task_filename)
                
                md_content = generate_task_markdown(
                    task, 
                    sprint_number=sprint["sprint_number"],
                    sprint_goal=sprint.get("sprint_goal", "")
                )
                
                with open(task_path, "w", encoding="utf-8") as f:
                    f.write(md_content)
                
                print(f"    📝 {task_filename}")
                total_tasks += 1

        # Generate master plan
        generate_master_plan(plan, args.output_dir)

        print(f"\n🎉 Completed! Generated {total_tasks} tasks in {len(plan.get('sprints', []))} sprints.")
        print(f"👉 Open '{args.output_dir}' in your IDE and tell Cline: 'Start working from TASK-01'.")


if __name__ == "__main__":
    main()