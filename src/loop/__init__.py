"""
Autonomous loop for automatic functional analysis.

Coordinates the flow:
  Ingest → Analyst → Spec → Validator → Fuzzer → Critic → Analyst → ...

Stop criteria:
  - Quality Score 100/100 (perfect machine)
  - Quality Score ≥ 90 AND 0 critical issues (sufficient quality)
  - Convergence: Quality Score doesn't improve for 2 consecutive iterations
  - Max iterations reached
  - Timeout reached

Usage:
    python loop.py --context project_context.md --max-iterations 5 --time-budget 600
    python loop.py --input-dir inputs/ --max-iterations 5  # with automatic ingest
"""

import os
import time
import json
from datetime import datetime
from typing import Dict, List, Optional

from loop.runner import FrontendRunner
from loop.quality import QualityChecker

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_MAX_ITERATIONS = 10
DEFAULT_TIME_BUDGET = 1200  # 20 minutes
OUTPUT_DIR = "./output"
CONTEXT_DIR = "./output/context"
ANALYST_DIR = "./output/analyst"
SPEC_DIR = "./output/spec"
DEFAULT_CHECKPOINT_DIR = "./output/loop_checkpoints"
FORCE_ALL_ITERATIONS = False

# ---------------------------------------------------------------------------
# Loop Coordinator
# ---------------------------------------------------------------------------

class AutonomousLoop:
    """Coordinates the autonomous functional analysis loop."""
    
    def __init__(
        self,
        context_file: str,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        time_budget: int = DEFAULT_TIME_BUDGET,
        checkpoint_dir: str = DEFAULT_CHECKPOINT_DIR,
        force_iterations: bool = FORCE_ALL_ITERATIONS,
        input_dir: str = None,
        generate_ui: bool = False,
        force_design: bool = False
    ):
        self.max_iterations = max_iterations
        self.time_budget = time_budget
        self.checkpoint_dir = checkpoint_dir
        self.force_iterations = force_iterations
        self.input_dir = input_dir
        self.generate_ui = generate_ui
        self.force_design = force_design
        
        # Output files
        if input_dir:
            self.context_file = os.path.join(CONTEXT_DIR, "project_context.md")
        else:
            self.context_file = context_file
        self.analyst_output = os.path.join(ANALYST_DIR, "analyst_suggestions.json")
        self.spec_output = os.path.join(SPEC_DIR, "spec.md")
        self.spec_machine = os.path.join(SPEC_DIR, "spec_machine.json")
        self.fuzz_report = os.path.join(SPEC_DIR, "fuzz_report.json")
        self.critic_feedback = os.path.join(SPEC_DIR, "critic_report.json")
        
        # State
        self.iteration = 0
        self.start_time = None
        self.history = []
        self.quality_history = []
        self.last_critical_issues = 0  # Track critical issues from last critic run
        
        # Sub-modules
        self.runner = FrontendRunner(
            context_file=self.context_file,
            analyst_output=self.analyst_output,
            spec_output=self.spec_output,
            spec_machine=self.spec_machine,
            fuzz_report=self.fuzz_report,
            critic_feedback=self.critic_feedback,
            force_design=force_design
        )
        self.quality_checker = QualityChecker(force_iterations=force_iterations)
        
        # Create output directories
        os.makedirs(checkpoint_dir, exist_ok=True)
        os.makedirs(CONTEXT_DIR, exist_ok=True)
        os.makedirs(ANALYST_DIR, exist_ok=True)
        os.makedirs(SPEC_DIR, exist_ok=True)
    
    def run(self) -> dict:
        """Runs the complete autonomous loop."""
        self.start_time = time.time()
        
        print("=" * 60)
        print("AUTONOMOUS LOOP - Automatic Functional Analysis")
        print("=" * 60)
        print(f"Context: {self.context_file}")
        print(f"Max iterations: {self.max_iterations}")
        print(f"Time budget: {self.time_budget}s")
        if self.input_dir:
            print(f"Input dir: {self.input_dir} (automatic ingest)")
        print()
        
        # Pre-flight: Validate LLM environment
        print("🔍 Pre-flight checks...")
        llm_valid, llm_errors = FrontendRunner.validate_llm_env()
        if not llm_valid:
            print("  ❌ LLM environment validation failed:")
            for err in llm_errors:
                print(f"     {err}")
            print()
            print("💡 Set the required environment variables before running:")
            print("   export LLM_API_KEY=sk-...")
            print("   export LLM_PROVIDER=openai  # or anthropic, google, dashscope")
            print("   export LLM_MODEL=gpt-4o     # optional, uses provider default")
            print()
            return {
                "completed": False,
                "iterations_run": 0,
                "max_iterations": self.max_iterations,
                "time_budget": self.time_budget,
                "elapsed_seconds": 0,
                "final_errors": len(llm_errors),
                "final_warnings": 0,
                "history": [],
                "error": "LLM environment validation failed",
                "llm_errors": llm_errors
            }
        
        FrontendRunner.print_llm_config()
        print("  ✅ LLM environment OK\n")
        
        # Step 0: Ingest (if input_dir provided)
        if self.input_dir:
            self._run_ingest()
        
        while self._should_continue():
            self.iteration += 1
            print()
            print("=" * 60)
            print(f"ITERATION {self.iteration}/{self.max_iterations}")
            print("=" * 60)
            
            step_result = self._run_iteration()
            self.history.append(step_result)
            self._save_checkpoint(step_result)
            
            if step_result.get("completed"):
                print()
                print("🎉 Loop completed successfully!")
                break
        
        # Final step: UI Generator
        if self.generate_ui:
            print()
            print("=" * 60)
            print("🎨 UI SPECS GENERATION")
            print("=" * 60)
            self._run_ui_generator()
        
        return self._generate_report()
    
    def _should_continue(self) -> bool:
        """Checks if the loop should continue."""
        if self.iteration >= self.max_iterations:
            print(f"\n⏹️  Reached max {self.max_iterations} iterations")
            return False
        
        elapsed = time.time() - self.start_time
        if elapsed > self.time_budget:
            print(f"\n⏹️  Reached time budget ({elapsed:.0f}s > {self.time_budget}s)")
            return False
        
        return self.quality_checker.should_continue(
            iteration=self.iteration,
            quality_history=self.quality_history,
            critical_issues=self.last_critical_issues
        )
    
    def _run_iteration(self) -> dict:
        """Runs a single iteration of the loop."""
        iteration_start = time.time()
        result = {
            "iteration": self.iteration,
            "steps": {},
            "errors": [],
            "completed": False
        }
        
        # Step 1: Analyst
        print("\n📊 Step 1: Analyst...")
        analyst_result = self.runner.run_analyst(self.critic_feedback)
        result["steps"]["analyst"] = analyst_result
        if analyst_result.get("error"):
            result["errors"].append(f"Analyst: {analyst_result['error']}")
        
        # Step 2: Spec generation
        print("\n📝 Step 2: Spec generation...")
        spec_result = self.runner.run_spec(
            self.analyst_output, self.spec_machine, self.critic_feedback
        )
        result["steps"]["spec"] = spec_result
        if spec_result.get("error"):
            result["errors"].append(f"Spec: {spec_result['error']}")
        
        # Step 2.5: Validator
        print("\n🔎 Step 2.5: State machine validation...")
        validator_result = self.runner.run_validator(self.spec_machine)
        result["steps"]["validator"] = validator_result
        if validator_result.get("error"):
            result["errors"].append(f"Validator: {validator_result['error']}")
        elif validator_result.get("quality_score") is not None:
            score = validator_result["quality_score"]
            dead_ends = validator_result.get("dead_end_count", 0)
            print(f"  Quality Score: {score}/100, Dead-end states: {dead_ends}")
            self.quality_history.append(score)
            if dead_ends > 0:
                result["warnings"] = result.get("warnings", []) + [f"{dead_ends} dead-end states found"]
        
        # Step 3: Fuzzer
        print("\n🔍 Step 3: Fuzzer...")
        fuzz_result = self.runner.run_fuzzer(self.spec_machine, self.fuzz_report)
        result["steps"]["fuzzer"] = fuzz_result
        if fuzz_result.get("error"):
            result["errors"].append(f"Fuzzer: {fuzz_result['error']}")
        
        # Step 4: Critic
        print("\n🧐 Step 4: Critic...")
        critic_result = self.runner.run_critic(
            self.fuzz_report, self.spec_output, self.spec_machine, self.context_file
        )
        result["steps"]["critic"] = critic_result
        if critic_result.get("error"):
            result["errors"].append(f"Critic: {critic_result['error']}")
        
        # Track critical issues for convergence check
        self.last_critical_issues = critic_result.get("critical_issues", 0)
        
        # Check stop criteria
        if not self.force_iterations:
            if self.quality_checker.check_quality_stop(validator_result, critic_result, self.iteration):
                result["completed"] = True
                print("\n✅ Sufficient quality - Loop completed!")
            else:
                has_structural_issues = (
                    validator_result.get("dead_end_count", 0) > 0 or
                    validator_result.get("unreachable_count", 0) > 0
                )
                critical_errors = critic_result.get("critical_issues", 0)
                fuzz_errors = fuzz_result.get("errors", 0)
                
                if not has_structural_issues and critical_errors == 0 and fuzz_errors == 0 and not result["errors"]:
                    result["completed"] = True
                    print("\n✅ No critical errors - Loop completed!")
                elif fuzz_errors > 0:
                    print(f"\n⚠️  Fuzzer found {fuzz_errors} errors - continuing iteration...")
                elif has_structural_issues:
                    print(f"\n⚠️  Structural issues detected - continuing iteration...")
        else:
            print(f"\n🔄 Iteration {self.iteration}/{self.max_iterations} completed (force mode)")
        
        elapsed = time.time() - iteration_start
        result["elapsed_seconds"] = elapsed
        print(f"\n⏱️  Iteration completed in {elapsed:.1f}s")
        
        return result
    
    def _run_ingest(self) -> dict:
        """Runs Ingest to generate context from inputs."""
        return self.runner.run_ingest(self.input_dir, self.context_file)
    
    def _run_ui_generator(self) -> dict:
        """Runs the UI Generator."""
        return self.runner.run_ui_generator(
            self.spec_machine, self.context_file, self.force_design
        )
    
    def _save_checkpoint(self, result: dict):
        """Saves an iteration checkpoint."""
        checkpoint_file = os.path.join(
            self.checkpoint_dir, 
            f"checkpoint_iter_{self.iteration:03d}.json"
        )
        checkpoint_data = {
            "timestamp": datetime.now().isoformat(),
            "iteration": self.iteration,
            "result": result,
            "history": self.history
        }
        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(checkpoint_data, f, indent=2)
    
    def _generate_report(self) -> dict:
        """Generates the final loop report."""
        elapsed = time.time() - self.start_time
        total_errors = sum(
            r.get("steps", {}).get("fuzzer", {}).get("errors", 0)
            for r in self.history
        )
        total_warnings = sum(
            r.get("steps", {}).get("fuzzer", {}).get("warnings", 0)
            for r in self.history
        )
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "context_file": self.context_file,
            "completed": self.history[-1].get("completed", False) if self.history else False,
            "iterations_run": len(self.history),
            "max_iterations": self.max_iterations,
            "time_budget": self.time_budget,
            "elapsed_seconds": elapsed,
            "final_errors": total_errors,
            "final_warnings": total_warnings,
            "history": self.history,
            "output_files": {
                "analyst": self.analyst_output,
                "spec": self.spec_output,
                "machine": self.spec_machine,
                "fuzz_report": self.fuzz_report,
                "critic_feedback": self.critic_feedback
            }
        }
        
        report_file = os.path.join(self.checkpoint_dir, "final_report.json")
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        
        return report