"""
Step runners - executes individual pipeline steps as subprocesses.

Three independent runners:
- FrontendRunner: analyst → spec → validator → fuzzer → critic
- BackendRunner: architect → critic
- CICDRunner: planner
"""

import os
import sys
import json
import subprocess
from typing import Optional

# Script directory (src/loop/)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Project root directory (autoresearch-master/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
# Project src directory (src/)
SRC_DIR = os.path.dirname(SCRIPT_DIR)
OUTPUT_DIR = "./output"

# Required environment variables for LLM calls
REQUIRED_LLM_ENV_VARS = ["LLM_API_KEY"]

# Supported providers and their default models
SUPPORTED_PROVIDERS = {
    "openai": {"model": "gpt-4o", "base_url": "https://api.openai.com/v1"},
    "anthropic": {"model": "claude-3-5-sonnet-20241022", "base_url": "https://api.anthropic.com"},
    "google": {"model": "gemini-2.5-flash", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai"},
    "dashscope": {"model": "qwen-max", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
    "coding": {"model": "qwen3.5-plus", "base_url": "https://coding-intl.dashscope.aliyuncs.com/v1"},
    "nvidia": {"model": "deepseek-ai/deepseek-v4-pro", "base_url": "https://integrate.api.nvidia.com/v1"},
}


class FrontendRunner:
    """Executes frontend pipeline steps as subprocess calls."""
    
    def __init__(
        self,
        context_file: str,
        analyst_output: str,
        spec_output: str,
        spec_machine: str,
        fuzz_report: str,
        critic_feedback: str,
        force_design: bool = False
    ):
        self.context_file = context_file
        self.analyst_output = analyst_output
        self.spec_output = spec_output
        self.spec_machine = spec_machine
        self.fuzz_report = fuzz_report
        self.critic_feedback = critic_feedback
        self.force_design = force_design
    
    @staticmethod
    def validate_llm_env() -> tuple[bool, list[str]]:
        """Validate that required LLM environment variables are set.
        
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        # Check required vars
        for var in REQUIRED_LLM_ENV_VARS:
            if not os.getenv(var):
                errors.append(f"❌ {var} is not set")
        
        # Check provider configuration
        provider = os.getenv("LLM_PROVIDER", "")
        if provider and provider not in SUPPORTED_PROVIDERS:
            errors.append(f"⚠️  Unknown provider '{provider}'. Supported: {', '.join(SUPPORTED_PROVIDERS.keys())}")
        
        # If custom provider, check base_url and model
        if provider and provider not in SUPPORTED_PROVIDERS:
            if not os.getenv("LLM_BASE_URL"):
                errors.append(f"❌ LLM_BASE_URL is required for custom provider '{provider}'")
            if not os.getenv("LLM_MODEL"):
                errors.append(f"❌ LLM_MODEL is required for custom provider '{provider}'")
        
        return (len(errors) == 0, errors)
    
    @staticmethod
    def print_llm_config():
        """Print current LLM configuration."""
        provider = os.getenv("LLM_PROVIDER", "openai")
        model = os.getenv("LLM_MODEL", SUPPORTED_PROVIDERS.get(provider, {}).get("model", "unknown"))
        base_url = os.getenv("LLM_BASE_URL", SUPPORTED_PROVIDERS.get(provider, {}).get("base_url", "custom"))
        
        print(f"  🤖 LLM Configuration:")
        print(f"     Provider: {provider}")
        print(f"     Model:    {model}")
        print(f"     Base URL: {base_url}")
    
    def _run_module(self, module_name: str, args: list, timeout: int = 300) -> dict:
        """Generic module runner (uses python -m pipeline.frontend.xxx)."""
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = SRC_DIR
            env["PYTHONUNBUFFERED"] = "1"
            result = subprocess.run(
                ["python3", "-m", f"pipeline.frontend.{module_name}"] + args,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=PROJECT_ROOT
            )
            
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        print(f"  {line}")
                sys.stdout.flush()
            if result.stderr:
                for line in result.stderr.strip().split("\n"):
                    if line.strip():
                        print(f"  [stderr] {line}")
                sys.stdout.flush()
            
            return {"returncode": result.returncode, "stdout": result.stdout}
            
        except subprocess.TimeoutExpired:
            return {"error": f"pipeline.frontend.{module_name} timeout"}
        except Exception as e:
            return {"error": str(e)}
    
    def _print_output(self, result: dict):
        """Print stdout lines from result."""
        if result.get("stdout"):
            for line in result["stdout"].strip().split("\n"):
                if line.strip():
                    print(f"  {line}")
    
    # ---- Individual Steps ----
    
    def run_ingest(self, input_dir: str, output_file: str) -> dict:
        """Runs Ingest to generate context from inputs."""
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = SRC_DIR
            result = subprocess.run(
                ["python3", "-m", "pipeline.ingest", "--input-dir", input_dir, "--output-file", output_file],
                capture_output=True,
                text=True,
                timeout=300,
                env=env,
                cwd=PROJECT_ROOT
            )
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        print(f"  {line}")
            if os.path.exists(output_file):
                return {"success": True, "output": output_file}
            return {"error": "Ingest did not produce output"}
        except subprocess.TimeoutExpired:
            return {"error": "pipeline.ingest timeout"}
        except Exception as e:
            return {"error": str(e)}
    
    def run_analyst(self, critic_feedback: str) -> dict:
        """Runs the Analyst."""
        args = ["--context", self.context_file]
        if os.path.exists(critic_feedback):
            args.extend(["--critic-feedback", critic_feedback])
        
        result = self._run_module("analyst", args, timeout=300)
        if result.get("error"):
            return {"error": result["error"]}
        
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
    
    def run_spec(self, analyst_output: str, spec_machine: str, critic_feedback: str, validator_feedback: dict = None) -> dict:
        """Runs spec generation (iterative approach)."""
        args = ["--context", self.context_file]
        
        if os.path.exists(analyst_output):
            args.extend(["--suggestions", analyst_output])
        if os.path.exists(spec_machine):
            args.extend(["--machine", spec_machine])
        if os.path.exists(critic_feedback):
            args.extend(["--critic-feedback", critic_feedback])
        
        # Pass validator feedback as JSON string if available
        if validator_feedback:
            import json as json_mod
            validator_json = json_mod.dumps(validator_feedback)
            args.extend(["--validator-feedback", validator_json])
        
        result = self._run_module("spec", args, timeout=1800)
        if result.get("error"):
            return {"error": result["error"]}
        
        if os.path.exists(self.spec_output):
            return {
                "success": True,
                "output": self.spec_output,
                "machine": self.spec_machine
            }
        return {"success": True}
    
    def run_validator(self, spec_machine: str) -> dict:
        """Runs the state machine validator."""
        result = self._run_module("validator", ["--machine", spec_machine], timeout=60)
        if result.get("error"):
            return {"error": result["error"]}
        
        output_text = result.get("stdout", "")
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
            "exit_code": result.get("returncode", 0)
        }
    
    def run_json_validator(self, spec_machine: str) -> dict:
        """Runs the JSON structural validator (deterministic judge).
        
        This is the "Pathfinder" - it validates the machine structure
        before it's handed off to code generators.
        
        Returns:
            Dict with validation results including:
            - is_valid: True if no critical/high issues
            - quality_score: 0-100 score
            - duplicate_count: Number of duplicate states
            - orphan_count: Number of orphan transitions
            - dead_end_count: Number of dead-end states
            - total_issues: Total number of issues
        """
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = SRC_DIR
            result = subprocess.run(
                ["python3", "-m", "state_machine.json_validator", spec_machine],
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
                cwd=PROJECT_ROOT
            )
            
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        print(f"  {line}")
            if result.stderr:
                for line in result.stderr.strip().split("\n"):
                    if line.strip():
                        print(f"  [stderr] {line}")
            
            # Parse the validation report
            output_text = result.stdout or ""
            quality_score = None
            total_issues = 0
            critical_count = 0
            high_count = 0
            medium_count = 0
            is_valid = False
            
            for line in output_text.split("\n"):
                if "Quality Score:" in line:
                    try:
                        quality_score = int(line.split(":")[1].strip().split("/")[0])
                    except:
                        pass
                if "Issues Found:" in line:
                    try:
                        total_issues = int(line.split(":")[1].strip())
                    except:
                        pass
                if "Critical:" in line:
                    try:
                        critical_count = int(line.split(":")[1].strip())
                    except:
                        pass
                if "High:" in line:
                    try:
                        high_count = int(line.split(":")[1].strip())
                    except:
                        pass
                if "Medium:" in line:
                    try:
                        medium_count = int(line.split(":")[1].strip())
                    except:
                        pass
                if "✅ VALID" in line:
                    is_valid = True
                if "❌ INVALID" in line:
                    is_valid = False
            
            return {
                "success": True,
                "is_valid": is_valid,
                "quality_score": quality_score,
                "total_issues": total_issues,
                "critical_count": critical_count,
                "high_count": high_count,
                "medium_count": medium_count,
                "exit_code": result.returncode
            }
            
        except subprocess.TimeoutExpired:
            return {"error": "json_validator timeout", "is_valid": False}
        except Exception as e:
            return {"error": str(e), "is_valid": False}
    
    def run_fuzzer(self, spec_machine: str, fuzz_report: str) -> dict:
        """Runs the Fuzzer."""
        result = self._run_module("fuzzer", ["--machine", spec_machine], timeout=300)
        if result.get("error"):
            return {"error": result["error"]}
        
        if os.path.exists(fuzz_report):
            with open(fuzz_report, "r") as f:
                data = json.load(f)
            return {
                "success": True,
                "errors": data.get("summary", {}).get("total_errors", 0),
                "warnings": data.get("summary", {}).get("total_warnings", 0),
                "bugs_found": data.get("summary", {}).get("bugs_found", 0),
                "output": fuzz_report
            }
        return {"success": True}
    
    def run_critic(
        self, fuzz_report: str, spec_output: str, spec_machine: str, context_file: str
    ) -> dict:
        """Runs the Critic."""
        cmd = [
            "--fuzz-report", fuzz_report,
            "--spec", spec_output,
            "--machine", spec_machine,
            "--context", context_file
        ]
        result = self._run_module("critic", cmd, timeout=120)
        if result.get("error"):
            return {"error": result["error"]}
        
        if os.path.exists(self.critic_feedback):
            with open(self.critic_feedback, "r") as f:
                data = json.load(f)
            
            critical_count = len(data.get("critical_issues", []))
            ux_count = len(data.get("ux_decisions_needed", []))
            missing_count = len(data.get("missing_flows", []))
            total_issues = critical_count + ux_count + missing_count
            
            return {
                "success": True,
                "total_issues": total_issues,
                "critical_issues": critical_count,
                "ux_decisions": ux_count,
                "recommendations": len(data.get("recommendations", [])),
                "output": self.critic_feedback
            }
        return {"success": True}
    
    def run_ui_generator(self, spec_machine: str, context_file: str, force_design: bool) -> dict:
        """Runs the UI Generator to create UI specs from the state machine."""
        ui_output_dir = os.path.join(OUTPUT_DIR, "ui_specs")
        spec_output = os.path.join(OUTPUT_DIR, "spec", "spec.md")
        cmd = [
            "--machine", spec_machine,
            "--context", context_file,
            "--spec", spec_output,
            "--output-dir", ui_output_dir
        ]
        if force_design:
            cmd.append("--force-design")
        
        # Detect provider from environment
        provider = os.environ.get("LLM_PROVIDER", "")
        model = os.environ.get("LLM_MODEL", "")
        base_url = os.environ.get("LLM_BASE_URL", "")
        
        if provider:
            cmd.extend(["--provider", provider])
        if model:
            cmd.extend(["--model", model])
        if base_url:
            cmd.extend(["--base-url", base_url])
        
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = SRC_DIR
            result = subprocess.run(
                ["python3", "-m", "pipeline.ui_generator"] + cmd,
                capture_output=True,
                text=True,
                timeout=3600,
                env=env,
                cwd=PROJECT_ROOT
            )
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        print(f"  {line}")
            if result.stderr:
                for line in result.stderr.strip().split("\n"):
                    if line.strip():
                        print(f"  [stderr] {line}")
            
            if result.returncode == 0:
                print(f"\n  ✅ UI specs generated in {ui_output_dir}/")
                print(f"     Open {ui_output_dir}/README.md to navigate.")
                return {"success": True, "output_dir": ui_output_dir}
            else:
                print(f"\n  ⚠️  UI Generator returned error: {result.returncode}")
                return {"error": f"Exit code {result.returncode}"}
        except subprocess.TimeoutExpired:
            print("\n  ⚠️  UI Generator timed out after 3600s.")
            return {"error": "pipeline.ui_generator timeout"}
        except Exception as e:
            print(f"\n  ⚠️  UI Generator error: {e}")
            return {"error": str(e)}


class BackendRunner:
    """Executes backend pipeline steps as subprocess calls."""
    
    def __init__(
        self,
        context_file: str,
        spec_machine: str,
        spec_output: str,
        backend_spec: str,
        backend_critic_report: str
    ):
        self.context_file = context_file
        self.spec_machine = spec_machine
        self.spec_output = spec_output
        self.backend_spec = backend_spec
        self.backend_critic_report = backend_critic_report
    
    def _run_module(self, module_name: str, args: list, timeout: int = 300) -> dict:
        """Generic module runner (uses python -m pipeline.backend.xxx)."""
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = SRC_DIR
            env["PYTHONUNBUFFERED"] = "1"
            result = subprocess.run(
                ["python3", "-m", f"pipeline.backend.{module_name}"] + args,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=PROJECT_ROOT
            )
            
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        print(f"  {line}")
                sys.stdout.flush()
            if result.stderr:
                for line in result.stderr.strip().split("\n"):
                    if line.strip():
                        print(f"  [stderr] {line}")
                sys.stdout.flush()
            
            return {"returncode": result.returncode, "stdout": result.stdout}
            
        except subprocess.TimeoutExpired:
            return {"error": f"pipeline.backend.{module_name} timeout"}
        except Exception as e:
            return {"error": str(e)}
    
    def run_architect(self) -> dict:
        """Runs the Backend Architect to generate backend_spec.md."""
        cmd = [
            "--machine", self.spec_machine,
            "--context", self.context_file,
            "--output", self.backend_spec
        ]
        result = self._run_module("architect", cmd, timeout=300)
        if result.get("error"):
            return {"error": result["error"]}
        
        if os.path.exists(self.backend_spec):
            return {
                "success": True,
                "output": self.backend_spec
            }
        return {"success": True}
    
    def run_critic(self) -> dict:
        """Runs the Backend Critic."""
        cmd = [
            "--backend-spec", self.backend_spec,
            "--spec", self.spec_output,
            "--machine", self.spec_machine,
            "--output", self.backend_critic_report
        ]
        result = self._run_module("critic", cmd, timeout=120)
        if result.get("error"):
            return {"error": result["error"]}
        
        if os.path.exists(self.backend_critic_report):
            with open(self.backend_critic_report, "r") as f:
                data = json.load(f)
            return {
                "success": True,
                "total_issues": data.get("summary", {}).get("total_issues", 0),
                "critical_issues": len(data.get("summary", {}).get("critical_issues", [])),
                "output": self.backend_critic_report
            }
        return {"success": True}


class CICDRunner:
    """Executes CI/CD pipeline steps as subprocess calls."""
    
    def __init__(
        self,
        spec_output: str,
        backend_spec: str,
        ci_cd_spec: str
    ):
        self.spec_output = spec_output
        self.backend_spec = backend_spec
        self.ci_cd_spec = ci_cd_spec
    
    def _run_module(self, module_name: str, args: list, timeout: int = 300) -> dict:
        """Generic module runner (uses python -m pipeline.ci_cd.xxx)."""
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = SRC_DIR
            env["PYTHONUNBUFFERED"] = "1"
            result = subprocess.run(
                ["python3", "-m", f"pipeline.ci_cd.{module_name}"] + args,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=PROJECT_ROOT
            )
            
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        print(f"  {line}")
                sys.stdout.flush()
            if result.stderr:
                for line in result.stderr.strip().split("\n"):
                    if line.strip():
                        print(f"  [stderr] {line}")
                sys.stdout.flush()
            
            return {"returncode": result.returncode, "stdout": result.stdout}
            
        except subprocess.TimeoutExpired:
            return {"error": f"pipeline.ci_cd.{module_name} timeout"}
        except Exception as e:
            return {"error": str(e)}
    
    def run_planner(self) -> dict:
        """Runs the CI/CD Planner."""
        cmd = [
            "--spec", self.spec_output,
            "--backend-spec", self.backend_spec,
            "--output", self.ci_cd_spec
        ]
        result = self._run_module("planner", cmd, timeout=300)
        if result.get("error"):
            return {"error": result["error"]}
        
        if os.path.exists(self.ci_cd_spec):
            return {
                "success": True,
                "output": self.ci_cd_spec
            }
        return {"success": True}