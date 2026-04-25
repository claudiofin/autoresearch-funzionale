"""Tests for pipeline/kanban_task/task_generator.py"""

import pytest
import os
import json
import tempfile
from unittest.mock import patch, MagicMock

from pipeline.kanban_task.task_generator import (
    gather_all_markdown_context,
    generate_task_markdown,
    generate_master_plan,
)


class TestGatherAllMarkdownContext:
    def test_returns_empty_string_for_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = gather_all_markdown_context(tmpdir)
            assert result == ""

    def test_collects_md_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            with open(os.path.join(tmpdir, "test.md"), "w") as f:
                f.write("# Test Content")
            result = gather_all_markdown_context(tmpdir)
            assert "test.md" in result
            assert "# Test Content" in result

    def test_skips_kanban_tasks_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a kanban_tasks subdirectory with a file
            kb_dir = os.path.join(tmpdir, "kanban_tasks")
            os.makedirs(kb_dir)
            with open(os.path.join(kb_dir, "TASK-01.md"), "w") as f:
                f.write("# Old Task")
            # Create a regular file
            with open(os.path.join(tmpdir, "spec.md"), "w") as f:
                f.write("# Spec")
            result = gather_all_markdown_context(tmpdir)
            assert "TASK-01.md" not in result
            assert "spec.md" in result

    def test_skips_non_md_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "test.json"), "w") as f:
                f.write('{"key": "value"}')
            with open(os.path.join(tmpdir, "test.md"), "w") as f:
                f.write("# Markdown")
            result = gather_all_markdown_context(tmpdir)
            assert "test.json" not in result
            assert "test.md" in result

    def test_truncates_large_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            large_content = "A" * 10000
            with open(os.path.join(tmpdir, "large.md"), "w") as f:
                f.write(large_content)
            result = gather_all_markdown_context(tmpdir)
            assert "[TRUNCATED]" in result
            assert len(result) < len(large_content) + 200  # header + truncation marker

    def test_priority_order(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create files with different priorities
            with open(os.path.join(tmpdir, "ci_cd_spec.md"), "w") as f:
                f.write("CI/CD")
            with open(os.path.join(tmpdir, "project_context.md"), "w") as f:
                f.write("Context")
            with open(os.path.join(tmpdir, "spec.md"), "w") as f:
                f.write("Spec")
            result = gather_all_markdown_context(tmpdir)
            # project_context should appear before spec, spec before ci_cd_spec
            ctx_pos = result.find("Context")
            spec_pos = result.find("Spec")
            cicd_pos = result.find("CI/CD")
            assert ctx_pos < spec_pos < cicd_pos

    def test_recursive_search(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sub_dir = os.path.join(tmpdir, "subdir")
            os.makedirs(sub_dir)
            with open(os.path.join(sub_dir, "nested.md"), "w") as f:
                f.write("# Nested")
            result = gather_all_markdown_context(tmpdir)
            assert "nested.md" in result
            assert "# Nested" in result


class TestGenerateTaskMarkdown:
    def test_basic_task(self):
        task = {
            "id": "TASK-01",
            "title": "Test_Task",
            "description": "This is a test task.",
        }
        result = generate_task_markdown(task, 1, "Setup")
        assert "# TASK-01: Test_Task" in result
        assert "**Sprint:** 1" in result
        assert "This is a test task." in result

    def test_task_with_dependencies(self):
        task = {
            "id": "TASK-02",
            "title": "Dependent_Task",
            "description": "Depends on TASK-01",
            "dependencies": ["TASK-01"],
        }
        result = generate_task_markdown(task, 1, "Setup")
        assert "BLOCKED BY" in result
        assert "TASK-01" in result

    def test_task_without_dependencies(self):
        task = {
            "id": "TASK-01",
            "title": "First_Task",
            "description": "No deps",
            "dependencies": [],
        }
        result = generate_task_markdown(task, 1, "Setup")
        assert "READY TO START" in result

    def test_task_with_parallelization(self):
        task = {
            "id": "TASK-03",
            "title": "Parallel_Task",
            "description": "Can run in parallel",
            "dependencies": [],
            "can_be_parallelized": True,
            "parallel_group": "A",
        }
        result = generate_task_markdown(task, 2, "Frontend")
        assert "PARALLELIZABLE" in result
        assert "[A]" in result

    def test_task_with_files_to_read(self):
        task = {
            "id": "TASK-01",
            "title": "Task",
            "description": "Desc",
            "files_to_read": ["output/context/project_context.md", "DESIGN.md"],
        }
        result = generate_task_markdown(task, 1, "Setup")
        assert "project_context.md" in result
        assert "DESIGN.md" in result

    def test_task_with_acceptance_criteria(self):
        task = {
            "id": "TASK-01",
            "title": "Task",
            "description": "Desc",
            "acceptance_criteria": [
                "Compiles without errors",
                "Linter configured",
            ],
        }
        result = generate_task_markdown(task, 1, "Setup")
        assert "Compiles without errors" in result
        assert "Linter configured" in result
        assert "- [ ]" in result  # checkbox format

    def test_task_priority_based_on_dependencies(self):
        task_with_deps = {
            "id": "TASK-02",
            "title": "Task",
            "description": "Desc",
            "dependencies": ["TASK-01"],
        }
        result = generate_task_markdown(task_with_deps, 1, "Setup")
        assert "High" in result  # high priority

        task_no_deps = {
            "id": "TASK-01",
            "title": "Task",
            "description": "Desc",
            "dependencies": [],
        }
        result = generate_task_markdown(task_no_deps, 1, "Setup")
        assert "Medium" in result  # medium priority


class TestGenerateMasterPlan:
    def test_master_plan_contains_sprint_info(self):
        plan = {
            "project_name": "Test Project",
            "sprints": [
                {
                    "sprint_number": 1,
                    "id": "Setup",
                    "sprint_goal": "Setup and Architecture",
                    "tasks": [
                        {
                            "id": "TASK-01",
                            "title": "Init Repo",
                            "dependencies": [],
                            "can_be_parallelized": False,
                        },
                    ],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate_master_plan(plan, tmpdir)
            assert os.path.exists(path)
            with open(path, "r") as f:
                content = f.read()
            assert "Test Project" in content
            assert "Sprint 1" in content
            assert "Setup and Architecture" in content
            assert "TASK-01" in content
            assert "Init Repo" in content

    def test_master_plan_shows_dependencies(self):
        plan = {
            "project_name": "Test",
            "sprints": [
                {
                    "sprint_number": 1,
                    "id": "Setup",
                    "sprint_goal": "Setup",
                    "tasks": [
                        {
                            "id": "TASK-02",
                            "title": "Dependent Task",
                            "dependencies": ["TASK-01"],
                            "can_be_parallelized": False,
                        },
                    ],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate_master_plan(plan, tmpdir)
            with open(path, "r") as f:
                content = f.read()
            assert "TASK-01" in content
            assert "Depends on" in content

    def test_master_plan_shows_parallelization(self):
        plan = {
            "project_name": "Test",
            "sprints": [
                {
                    "sprint_number": 2,
                    "id": "Frontend",
                    "sprint_goal": "Frontend",
                    "tasks": [
                        {
                            "id": "TASK-03",
                            "title": "Parallel Task",
                            "dependencies": [],
                            "can_be_parallelized": True,
                            "parallel_group": "A",
                        },
                    ],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate_master_plan(plan, tmpdir)
            with open(path, "r") as f:
                content = f.read()
            assert "Parallelizable" in content
            assert "group A" in content

    def test_master_plan_summary(self):
        plan = {
            "project_name": "Test",
            "sprints": [
                {
                    "sprint_number": 1,
                    "id": "S1",
                    "sprint_goal": "Goal 1",
                    "tasks": [
                        {"id": "TASK-01", "title": "T1", "dependencies": [], "can_be_parallelized": False},
                        {"id": "TASK-02", "title": "T2", "dependencies": [], "can_be_parallelized": False},
                    ],
                },
                {
                    "sprint_number": 2,
                    "id": "S2",
                    "sprint_goal": "Goal 2",
                    "tasks": [
                        {"id": "TASK-03", "title": "T3", "dependencies": [], "can_be_parallelized": False},
                    ],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate_master_plan(plan, tmpdir)
            with open(path, "r") as f:
                content = f.read()
            assert "**Total Sprints:** 2" in content
            assert "**Total Tasks:** 3" in content

    def test_master_plan_default_project_name(self):
        plan = {"sprints": []}
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate_master_plan(plan, tmpdir)
            with open(path, "r") as f:
                content = f.read()
            assert "Project" in content
