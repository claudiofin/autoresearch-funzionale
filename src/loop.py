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
import sys
import json
import time
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

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
FORCE_ALL_ITERATIONS = False  # If True, forces all iterations even without errors

# Script directory (src/ if run from root, . if run from src/)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

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
        self.input_dir = input_dir  # If provided, runs ingest at start
        self.generate_ui = generate_ui  # If True, generates UI specs at end
        self.force_design = force_design  # If True, forces DESIGN.md regeneration
        
        # Output files (organized in subfolders)
        if input_dir:
            # With automatic ingest, context goes to output/context/
            self.context_file = os.path.join(CONTEXT_DIR, "project_context.md")
        else:
            # Context provided by user, uses given path
            self.context_file = context_file
        self.analyst_output = os.path.join(ANALYST_DIR, "analyst_suggestions.json")
        self.spec_output = os.path.join(SPEC_DIR, "spec.md")
        self.spec_machine = os.path.join(SPEC_DIR, "spec_machine.json")
        self.fuzz_report = os.path.join(OUTPUT_DIR, "fuzz_report.json")
        self.critic_feedback = os.path.join(OUTPUT_DIR, "critic_feedback.json")

        
        # State
        self.iteration = 0
        self.start_time = None
        self.history = []
        self.quality_history = []  # Track Quality Score for convergence
        
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
        
        # Step 0: Ingest (if input_dir provided and context doesn't exist)
        if self.input_dir:
            self._run_ingest()
        
        while self._should_continue():
            self.iteration += 1
            print()
            print("=" * 60)
            print(f"ITERATION {self.iteration}/{self.max_iterations}")
            print("=" * 60)
            
            # Run loop step
            step_result = self._run_iteration()
            self.history.append(step_result)
            
            # Save checkpoint
            self._save_checkpoint(step_result)
            
            # Check if completed
            if step_result.get("completed"):
                print()
                print("🎉 Loop completed successfully!")
                break
        
        # Final step: UI Generator (if requested)
        if self.generate_ui:
            print()
            print("=" * 60)
            print("🎨 UI SPECS GENERATION")
            print("=" * 60)
            self._run_ui_generator()
        
        # Final report
        return self._generate_report()
    
    def _should_continue(self) -> bool:
        """Checks if the loop should continue."""
        
        # Check iterations
        if self.iteration >= self.max_iterations:
            print(f"\n⏹️  Reached max {self.max_iterations} iterations")
            return False
        
        # Check time budget
        elapsed = time.time() - self.start_time
        if elapsed > self.time_budget:
            print(f"\n⏹️  Reached time budget ({elapsed:.0f}s > {self.time_budget}s)")
            return False
        
        # Check quality-based stop criteria (skip if force_iterations)
        if not self.force_iterations and len(self.quality_history) >= 1:
            latest_quality = self.quality_history[-1]
            
            # Criterion 1: Quality Score 100/100 → immediate STOP
            if latest_quality == 100:
                print(f"\n🎉 Quality Score 100/100 reached! Loop completed.")
                return False
            
            # Criterion 2: Convergence - same score for 2 consecutive iterations
            if len(self.quality_history) >= 2:
                prev_quality = self.quality_history[-2]
                if latest_quality == prev_quality and latest_quality >= 80:
                    print(f"\n🎯 Convergence reached: Quality Score {latest_quality}/100 stable for 2 iterations.")
                    return False
        
        return True
    
    def _check_quality_stop(self, validator_result: dict, critic_result: dict) -> bool:
        """Check if loop should stop based on Quality Score and critical issues.
        
        Returns True if loop should stop.
        """
        if self.force_iterations:
            return False
        
        quality_score = validator_result.get("quality_score")
        critical_issues = critic_result.get("critical_issues", 0)
        
        if quality_score is not None:
            # Criterion 1: Quality Score 100/100 → STOP
            if quality_score == 100:
                print(f"\n🎉 Quality Score 100/100! Perfect machine.")
                return True
            
            # Criterion 2: Quality ≥ 90 AND 0 critical issues → STOP
            if quality_score >= 90 and critical_issues == 0:
                print(f"\n✅ Quality Score {quality_score}/100 with 0 critical issues. Sufficient quality.")
                return True
        
        return False
    
    def _run_iteration(self) -> dict:
        """Runs a single iteration of the loop."""
        
        iteration_start = time.time()
        result = {
            "iteration": self.iteration,
            "steps": {},
            "errors": [],
            "completed": False
        }
        
        # Step 1: Analyst (at EVERY iteration - not just the first)
        print("\n📊 Step 1: Analyst...")
        analyst_result = self._run_analyst()
        result["steps"]["analyst"] = analyst_result
        if analyst_result.get("error"):
            result["errors"].append(f"Analyst: {analyst_result['error']}")
        
        # Step 2: Spec generation
        print("\n📝 Step 2: Spec generation...")
        spec_result = self._run_spec()
        result["steps"]["spec"] = spec_result
        if spec_result.get("error"):
            result["errors"].append(f"Spec: {spec_result['error']}")
        
        # Step 2.5: Validator (check machine state quality)
        print("\n🔎 Step 2.5: State machine validation...")
        validator_result = self._run_validator()
        result["steps"]["validator"] = validator_result
        if validator_result.get("error"):
            result["errors"].append(f"Validator: {validator_result['error']}")
        elif validator_result.get("quality_score") is not None:
            score = validator_result["quality_score"]
            dead_ends = validator_result.get("dead_end_count", 0)
            print(f"  Quality Score: {score}/100, Dead-end states: {dead_ends}")
            # Track Quality Score for convergence
            self.quality_history.append(score)
            if dead_ends > 0:
                result["warnings"] = result.get("warnings", []) + [f"{dead_ends} dead-end states found"]
        
        # Step 3: Fuzzer
        print("\n🔍 Step 3: Fuzzer...")
        fuzz_result = self._run_fuzzer()
        result["steps"]["fuzzer"] = fuzz_result
        if fuzz_result.get("error"):
            result["errors"].append(f"Fuzzer: {fuzz_result['error']}")
        
        # Step 4: Critic
        print("\n🧐 Step 4: Critic...")
        critic_result = self._run_critic()
        result["steps"]["critic"] = critic_result
        if critic_result.get("error"):
            result["errors"].append(f"Critic: {critic_result['error']}")
        
        # Check quality-based stop criteria (after validator + critic)
        if not self.force_iterations:
            # First check quality score and critical issues
            if self._check_quality_stop(validator_result, critic_result):
                result["completed"] = True
                print("\n✅ Sufficient quality - Loop completed!")
            else:
                # Check if there are structural issues from validator
                has_structural_issues = (
                    validator_result.get("dead_end_count", 0) > 0 or
                    validator_result.get("unreachable_count", 0) > 0 or
                    validator_result.get("cycle_count", 0) > 0
                )
                
                critical_errors = critic_result.get("critical_issues", 0)
                
                # Don't stop if there are structural issues OR critical errors
                if not has_structural_issues and critical_errors == 0 and not result["errors"]:
                    result["completed"] = True
                    print("\n✅ No critical errors - Loop completed!")
                elif has_structural_issues:
                    print(f"\n⚠️  Structural issues detected - continuing iteration...")
        else:
            print(f"\n🔄 Iteration {self.iteration}/{self.max_iterations} completed (force mode)")
        
        # Summary
        elapsed = time.time() - iteration_start
        result["elapsed_seconds"] = elapsed
        print(f"\n⏱️  Iteration completed in {elapsed:.1f}s")
        
        return result
    
    def _run_ingest(self) -> dict:
        """Runs Ingest to generate context from inputs."""
        try:
            env = os.environ.copy()
            script = os.path.join(SCRIPT_DIR, "ingest.py")
            result = subprocess.run(
                ["python3", script, "--input-dir", self.input_dir, "--output-file", self.context_file],
                capture_output=True,
                text=True,
                timeout=300,
                env=env
            )
            
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        print(f"  {line}")
            
            if os.path.exists(self.context_file):
                return {"success": True, "output": self.context_file}
            
            return {"error": "Ingest did not produce output"}
            
        except subprocess.TimeoutExpired:
            return {"error": "Ingest timeout"}
        except Exception as e:
            return {"error": str(e)}
    
    def _run_analyst(self) -> dict:
        """Runs the Analyst."""
        try:
            env = os.environ.copy()
            script = os.path.join(SCRIPT_DIR, "analyst.py")
            
            # Build arguments: also pass critic feedback if exists
            args = ["python3", script, "--context", self.context_file]
            
            # If critic feedback exists from previous iterations, pass it to the analyst
            if os.path.exists(self.critic_feedback):
                args.extend(["--critic-feedback", self.critic_feedback])
            
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=300,
                env=env
            )
            
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        print(f"  {line}")
            
            if os.path.exists(self.analyst_output):
                with open(self.analyst_output, "r") as f:
                    data = json.load(f)
                return {
                    "success": True,
                    "patterns_detected": len(data.get("patterns_detected", [])),
                    "states_suggested": len(data.get("suggested_states", [])),
                    "output": self.analyst_output
                }
            
            return {"success": True, "output": self.analyst_output}
            
        except subprocess.TimeoutExpired:
            return {"error": "Analyst timeout"}
        except Exception as e:
            return {"error": str(e)}
    
    def _run_spec(self) -> dict:
        """Runs spec generation (iterative approach)."""
        try:
            env = os.environ.copy()
            script = os.path.join(SCRIPT_DIR, "spec.py")
            
            # Build arguments: pass everything for iterative approach
            args = ["python3", script, "--context", self.context_file]
            
            # Analyst suggestions
            if os.path.exists(self.analyst_output):
                args.extend(["--suggestions", self.analyst_output])
            
            # Existing machine (for subsequent iterations)
            if os.path.exists(self.spec_machine):
                args.extend(["--machine", self.spec_machine])
            
            # Critic feedback (to fix issues)
            if os.path.exists(self.critic_feedback):
                args.extend(["--critic-feedback", self.critic_feedback])
            
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=300,
                env=env
            )
            
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        print(f"  {line}")
            if result.stderr:
                for line in result.stderr.strip().split("\n"):
                    if line.strip():
                        print(f"  [stderr] {line}")
            
            if os.path.exists(self.spec_output):
                return {
                    "success": True,
                    "output": self.spec_output,
                    "machine": self.spec_machine
                }
            
            return {"success": True}
            
        except subprocess.TimeoutExpired:
            return {"error": "Spec timeout"}
        except Exception as e:
            return {"error": str(e)}
    
    def _run_validator(self) -> dict:
        """Runs the state machine validator."""
        try:
            env = os.environ.copy()
            script = os.path.join(SCRIPT_DIR, "validator.py")
            result = subprocess.run(
                ["python3", script, "--machine", self.spec_machine],
                capture_output=True,
                text=True,
                timeout=60,
                env=env
            )
            
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        print(f"  {line}")
            
            # Parse output to extract metrics
            output_text = result.stdout or ""
            quality_score = None
            dead_end_count = 0
            unreachable_count = 0
            cycle_count = 0
            
            for line in output_text.split("\n"):
                if "Quality Score:" in line:
                    try:
                        quality_score = int(line.split(":")[1].strip().split("/")[0])
                    except:
                        pass
                if "DEAD-END STATES" in line:
                    try:
                        dead_end_count = int(line.split("(")[1].split(")")[0])
                    except:
                        pass
                if "UNREACHABLE STATES" in line:
                    try:
                        unreachable_count = int(line.split("(")[1].split(")")[0])
                    except:
                        pass
                if "INFINITE LOOPS" in line:
                    try:
                        cycle_count = int(line.split("(")[1].split(")")[0])
                    except:
                        pass
            
            return {
                "success": True,
                "quality_score": quality_score,
                "dead_end_count": dead_end_count,
                "unreachable_count": unreachable_count,
                "cycle_count": cycle_count,
                "exit_code": result.returncode
            }
            
        except subprocess.TimeoutExpired:
            return {"error": "Validator timeout"}
        except Exception as e:
            return {"error": str(e)}
    
    def _run_fuzzer(self) -> dict:
        """Runs the Fuzzer."""
        try:
            env = os.environ.copy()
            script = os.path.join(SCRIPT_DIR, "fuzzer.py")
            result = subprocess.run(
                ["python3", script, "--machine", self.spec_machine],
                capture_output=True,
                text=True,
                timeout=300,
                env=env
            )
            
            # Parse report
            if os.path.exists(self.fuzz_report):
                with open(self.fuzz_report, "r") as f:
                    data = json.load(f)
                return {
                    "success": True,
                    "errors": data.get("summary", {}).get("total_errors", 0),
                    "warnings": data.get("summary", {}).get("total_warnings", 0),
                    "bugs_found": data.get("summary", {}).get("bugs_found", 0),
                    "output": self.fuzz_report
                }
            
            return {"success": True}
            
        except subprocess.TimeoutExpired:
            return {"error": "Fuzzer timeout"}
        except Exception as e:
            return {"error": str(e)}
    
    def _run_ui_generator(self) -> dict:
        """Runs the UI Generator to create UI specs from the state machine."""
        try:
            env = os.environ.copy()
            script = os.path.join(SCRIPT_DIR, "ui_generator.py")
            ui_output_dir = os.path.join(OUTPUT_DIR, "ui_specs")
            
            cmd = [
                "python3", script, 
                "--machine", self.spec_machine,
                "--context", self.context_file,
                "--output-dir", ui_output_dir
            ]
            
            # Pass force_design flag if set
            if self.force_design:
                cmd.append("--force-design")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                env=env
            )
            
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        print(f"  {line}")
            
            if result.returncode == 0:
                print(f"\n  ✅ UI specs generated in {ui_output_dir}/")
                print(f"     Open {ui_output_dir}/README.md to navigate.")
                return {"success": True, "output_dir": ui_output_dir}
            else:
                print(f"\n  ⚠️  UI Generator returned error: {result.returncode}")
                return {"error": f"Exit code {result.returncode}"}
            
        except subprocess.TimeoutExpired:
            return {"error": "UI Generator timeout"}
        except Exception as e:
            return {"error": str(e)}
    
    def _run_critic(self) -> dict:
        """Runs the Critic."""
        try:
            env = os.environ.copy()
            script = os.path.join(SCRIPT_DIR, "critic.py")
            cmd = [
                "python3", script,
                "--fuzz-report", self.fuzz_report,
                "--spec", self.spec_output,
                "--machine", self.spec_machine,
                "--context", self.context_file
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,  # Increased for LLM with context
                env=env
            )
            
            # Parse feedback
            if os.path.exists(self.critic_feedback):
                with open(self.critic_feedback, "r") as f:
                    data = json.load(f)
                return {
                    "success": True,
                    "total_issues": data.get("summary", {}).get("total_issues", 0),
                    "critical_issues": len(data.get("summary", {}).get("critical_issues", [])),
                    "ux_decisions": len(data.get("summary", {}).get("ux_decisions_needed", [])),
                    "recommendations": len(data.get("recommendations", [])),
                    "output": self.critic_feedback
                }
            
            return {"success": True}
            
        except subprocess.TimeoutExpired:
            return {"error": "Critic timeout"}
        except Exception as e:
            return {"error": str(e)}
    
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
        
        # Calculate statistics
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
        
        # Save report
        report_file = os.path.join(self.checkpoint_dir, "final_report.json")
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        
        return report


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Autonomous loop for functional analysis")
    parser.add_argument("--context", type=str, default="output/context/project_context.md",
                        help="Context file to analyze")
    parser.add_argument("--input-dir", type=str, default=None,
                        help="Input directory (if provided, runs automatic ingest)")
    parser.add_argument("--max-iterations", type=int, default=DEFAULT_MAX_ITERATIONS,
                        help=f"Max iterations (default: {DEFAULT_MAX_ITERATIONS})")
    parser.add_argument("--time-budget", type=int, default=DEFAULT_TIME_BUDGET,
                        help=f"Time budget in seconds (default: {DEFAULT_TIME_BUDGET})")
    parser.add_argument("--checkpoint-dir", type=str, default=DEFAULT_CHECKPOINT_DIR,
                        help=f"Checkpoint directory (default: {DEFAULT_CHECKPOINT_DIR})")
    parser.add_argument("--force", action="store_true",
                        help="Force all iterations even without critical errors")
    parser.add_argument("--generate-ui", action="store_true",
                        help="Generate UI specs from state machine (at end of loop)")
    parser.add_argument("--force-design", action="store_true",
                        help="Force regeneration of DESIGN.md even if it exists")
    args = parser.parse_args()
    
    # If input-dir is provided, context doesn't need to exist yet
    if args.input_dir and not os.path.exists(args.input_dir):
        print(f"Error: Input directory not found: {args.input_dir}")
        sys.exit(1)
    
    # If no input-dir, context must exist
    if not args.input_dir and not os.path.exists(args.context):
        print(f"Error: Context file not found: {args.context}")
        print("Run 'python ingest.py' first to generate project_context.md")
        print("Or use --input-dir to run automatic ingest")
        sys.exit(1)
    
    # Run loop
    loop = AutonomousLoop(
        context_file=args.context,
        max_iterations=args.max_iterations,
        time_budget=args.time_budget,
        checkpoint_dir=args.checkpoint_dir,
        force_iterations=args.force,
        input_dir=args.input_dir,
        generate_ui=args.generate_ui,
        force_design=args.force_design
    )
    
    report = loop.run()
    
    # Print final report
    print()
    print("=" * 60)
    print("FINAL REPORT")
    print("=" * 60)
    print(f"Completed:       {report['completed']}")
    print(f"Iterations:      {report['iterations_run']}/{report['max_iterations']}")
    print(f"Total time:      {report['elapsed_seconds']:.1f}s")
    print(f"Final errors:    {report['final_errors']}")
    print(f"Final warnings:  {report['final_warnings']}")
    print()
    print(f"Checkpoint: {args.checkpoint_dir}/")
    print(f"Report:     {args.checkpoint_dir}/final_report.json")


if __name__ == "__main__":
    main()