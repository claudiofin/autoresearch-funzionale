"""
Loop autonomo per analisi funzionale automatica.

Coordina il flusso:
  Ingest → Analyst → Spec → Completeness → Fuzzer → Critic → Analyst → ...

Criteri di stop:
  - 0 errori critici
  - Max iterazioni raggiunte
  - Timeout raggiunto

Usage:
    python loop.py --context project_context.md --max-iterations 5 --time-budget 600
    python loop.py --input-dir inputs/ --max-iterations 5  # con ingest automatico
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
DEFAULT_TIME_BUDGET = 1200  # 20 minuti
OUTPUT_DIR = "./output"
CONTEXT_DIR = "./output/context"
ANALYST_DIR = "./output/analyst"
SPEC_DIR = "./output/spec"
DEFAULT_CHECKPOINT_DIR = "./output/loop_checkpoints"
FORCE_ALL_ITERATIONS = False  # Se True, forza tutte le iterazioni anche senza errori

# Directory degli script (src/ se eseguito dalla root, . se eseguito da src/)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Loop Coordinator
# ---------------------------------------------------------------------------

class AutonomousLoop:
    """Coordina il loop autonomo di analisi funzionale."""
    
    def __init__(
        self,
        context_file: str,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        time_budget: int = DEFAULT_TIME_BUDGET,
        checkpoint_dir: str = DEFAULT_CHECKPOINT_DIR,
        force_iterations: bool = FORCE_ALL_ITERATIONS,
        input_dir: str = None
    ):
        self.max_iterations = max_iterations
        self.time_budget = time_budget
        self.checkpoint_dir = checkpoint_dir
        self.force_iterations = force_iterations
        self.input_dir = input_dir  # Se fornito, esegue ingest all'inizio
        
        # Output files (organized in subfolders)
        if input_dir:
            # Con ingest automatico, il contesto va in output/context/
            self.context_file = os.path.join(CONTEXT_DIR, "project_context.md")
        else:
            # Contesto fornito dall'utente, usa il percorso dato
            self.context_file = context_file
        self.analyst_output = os.path.join(ANALYST_DIR, "analyst_suggestions.json")
        self.spec_output = os.path.join(SPEC_DIR, "spec.md")
        self.spec_machine = os.path.join(SPEC_DIR, "spec_machine.json")
        self.fuzz_report = os.path.join(OUTPUT_DIR, "fuzz_report.json")
        self.critic_feedback = os.path.join(OUTPUT_DIR, "critic_feedback.json")
        self.completeness_report = os.path.join(OUTPUT_DIR, "completeness_report.json")
        
        # State
        self.iteration = 0
        self.start_time = None
        self.history = []
        
        # Create output directories
        os.makedirs(checkpoint_dir, exist_ok=True)
        os.makedirs(CONTEXT_DIR, exist_ok=True)
        os.makedirs(ANALYST_DIR, exist_ok=True)
        os.makedirs(SPEC_DIR, exist_ok=True)
    
    def run(self) -> dict:
        """Esegue il loop autonomo completo."""
        
        self.start_time = time.time()
        
        print("=" * 60)
        print("LOOP AUTONOMO - Analisi Funzionale Automatica")
        print("=" * 60)
        print(f"Contesto: {self.context_file}")
        print(f"Max iterazioni: {self.max_iterations}")
        print(f"Time budget: {self.time_budget}s")
        if self.input_dir:
            print(f"Input dir: {self.input_dir} (ingest automatico)")
        print()
        
        # Step 0: Ingest (se input_dir fornito e contesto non esiste)
        if self.input_dir:
            self._run_ingest()
        
        while self._should_continue():
            self.iteration += 1
            print()
            print("=" * 60)
            print(f"ITERAZIONE {self.iteration}/{self.max_iterations}")
            print("=" * 60)
            
            # Esegui step del loop
            step_result = self._run_iteration()
            self.history.append(step_result)
            
            # Salva checkpoint
            self._save_checkpoint(step_result)
            
            # Check se completato
            if step_result.get("completed"):
                print()
                print("🎉 Loop completato con successo!")
                break
        
        # Report finale
        return self._generate_report()
    
    def _should_continue(self) -> bool:
        """Controlla se il loop dovrebbe continuare."""
        
        # Check iterations
        if self.iteration >= self.max_iterations:
            print(f"\n⏹️  Raggiunte max {self.max_iterations} iterazioni")
            return False
        
        # Check time budget
        elapsed = time.time() - self.start_time
        if elapsed > self.time_budget:
            print(f"\n⏹️  Raggiunto time budget ({elapsed:.0f}s > {self.time_budget}s)")
            return False
        
        return True
    
    def _run_iteration(self) -> dict:
        """Esegue una singola iterazione del loop."""
        
        iteration_start = time.time()
        result = {
            "iteration": self.iteration,
            "steps": {},
            "errors": [],
            "completed": False
        }
        
        # Step 1: Analyst (ad OGNI iterazione - non solo alla prima)
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
        
        # Step 3: Completeness check
        print("\n✅ Step 3: Completeness check...")
        completeness_result = self._run_completeness()
        result["steps"]["completeness"] = completeness_result
        if completeness_result.get("error"):
            result["errors"].append(f"Completeness: {completeness_result['error']}")
        
        # Step 4: Fuzzer
        print("\n🔍 Step 4: Fuzzer...")
        fuzz_result = self._run_fuzzer()
        result["steps"]["fuzzer"] = fuzz_result
        if fuzz_result.get("error"):
            result["errors"].append(f"Fuzzer: {fuzz_result['error']}")
        
        # Step 5: Critic
        print("\n🧐 Step 5: Critic...")
        critic_result = self._run_critic()
        result["steps"]["critic"] = critic_result
        if critic_result.get("error"):
            result["errors"].append(f"Critic: {critic_result['error']}")
        
        # Check completion criteria (skip if force_iterations is True)
        if not self.force_iterations:
            critical_errors = critic_result.get("critical_issues", 0)
            if critical_errors == 0 and not result["errors"]:
                result["completed"] = True
                print("\n✅ Nessun errore critico - Loop completato!")
        else:
            print(f"\n🔄 Iterazione {self.iteration}/{self.max_iterations} completata (force mode)")
        
        # Summary
        elapsed = time.time() - iteration_start
        result["elapsed_seconds"] = elapsed
        print(f"\n⏱️  Iterazione completata in {elapsed:.1f}s")
        
        return result
    
    def _run_ingest(self) -> dict:
        """Esegue l'Ingest per generare il contesto dagli input."""
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
            
            return {"error": "Ingest non ha prodotto output"}
            
        except subprocess.TimeoutExpired:
            return {"error": "Ingest timeout"}
        except Exception as e:
            return {"error": str(e)}
    
    def _run_analyst(self) -> dict:
        """Esegue l'Analyst."""
        try:
            env = os.environ.copy()
            script = os.path.join(SCRIPT_DIR, "analyst.py")
            result = subprocess.run(
                ["python3", script, "--context", self.context_file],
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
        """Esegue la generazione della spec."""
        try:
            env = os.environ.copy()
            script = os.path.join(SCRIPT_DIR, "spec.py")
            result = subprocess.run(
                ["python3", script, "--context", self.context_file],
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
    
    def _run_completeness(self) -> dict:
        """Esegue il completeness check e legge il report JSON."""
        try:
            env = os.environ.copy()
            script = os.path.join(SCRIPT_DIR, "completeness.py")
            result = subprocess.run(
                ["python3", script, "--spec", self.spec_output, "--machine", self.spec_machine, "--context", self.context_file, "--fix"],
                capture_output=True,
                text=True,
                timeout=300,
                env=env
            )
            
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        print(f"  {line}")
            
            # Leggi il report JSON con le metriche
            if os.path.exists(self.completeness_report):
                with open(self.completeness_report, "r") as f:
                    data = json.load(f)
                return {
                    "success": True,
                    "total_flows": data.get("total_flows", 0),
                    "complete_flows": data.get("complete_flows", 0),
                    "missing_flows": data.get("missing_flows", 0),
                    "fix_applied": data.get("fix_applied", False),
                    "fix_success": data.get("fix_success"),
                    "flows_fixed": data.get("flows_fixed", []),
                    "flows_still_missing": data.get("flows_still_missing", []),
                }
            
            return {"success": True}
            
        except subprocess.TimeoutExpired:
            return {"error": "Completeness timeout"}
        except Exception as e:
            return {"error": str(e)}
    
    def _run_fuzzer(self) -> dict:
        """Esegue il Fuzzer."""
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
            
            # Parse del report
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
    
    def _run_critic(self) -> dict:
        """Esegue il Critic."""
        try:
            env = os.environ.copy()
            script = os.path.join(SCRIPT_DIR, "critic.py")
            result = subprocess.run(
                ["python3", script, "--fuzz-report", self.fuzz_report],
                capture_output=True,
                text=True,
                timeout=60,
                env=env
            )
            
            # Parse del feedback
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
        """Salva un checkpoint dell'iterazione."""
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
        """Genera il report finale del loop."""
        
        elapsed = time.time() - self.start_time
        
        # Calcola statistiche
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
        
        # Salva report
        report_file = os.path.join(self.checkpoint_dir, "final_report.json")
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        
        return report


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Loop autonomo per analisi funzionale")
    parser.add_argument("--context", type=str, default="project_context.md",
                        help="File di contesto da analizzare")
    parser.add_argument("--input-dir", type=str, default=None,
                        help="Directory input (se fornito, esegue ingest automatico)")
    parser.add_argument("--max-iterations", type=int, default=DEFAULT_MAX_ITERATIONS,
                        help=f"Max iterazioni (default: {DEFAULT_MAX_ITERATIONS})")
    parser.add_argument("--time-budget", type=int, default=DEFAULT_TIME_BUDGET,
                        help=f"Time budget in secondi (default: {DEFAULT_TIME_BUDGET})")
    parser.add_argument("--checkpoint-dir", type=str, default=DEFAULT_CHECKPOINT_DIR,
                        help=f"Directory per checkpoint (default: {DEFAULT_CHECKPOINT_DIR})")
    parser.add_argument("--force", action="store_true",
                        help="Forza tutte le iterazioni anche senza errori critici")
    args = parser.parse_args()
    
    # Se input-dir è fornito, non serve che il contesto esista già
    if args.input_dir and not os.path.exists(args.input_dir):
        print(f"Errore: Directory input non trovata: {args.input_dir}")
        sys.exit(1)
    
    # Se non c'è input-dir, il contesto deve esistere
    if not args.input_dir and not os.path.exists(args.context):
        print(f"Errore: File di contesto non trovato: {args.context}")
        print("Esegui prima 'python ingest.py' per generare project_context.md")
        print("Oppure usa --input-dir per eseguire ingest automatico")
        sys.exit(1)
    
    # Run loop
    loop = AutonomousLoop(
        context_file=args.context,
        max_iterations=args.max_iterations,
        time_budget=args.time_budget,
        checkpoint_dir=args.checkpoint_dir,
        force_iterations=args.force,
        input_dir=args.input_dir
    )
    
    report = loop.run()
    
    # Stampa report finale
    print()
    print("=" * 60)
    print("REPORT FINALE")
    print("=" * 60)
    print(f"Completato:       {report['completed']}")
    print(f"Iterazioni:       {report['iterations_run']}/{report['max_iterations']}")
    print(f"Tempo totale:     {report['elapsed_seconds']:.1f}s")
    print(f"Errori finali:    {report['final_errors']}")
    print(f"Warning finali:   {report['final_warnings']}")
    print()
    print(f"Checkpoint: {args.checkpoint_dir}/")
    print(f"Report:     {args.checkpoint_dir}/final_report.json")


if __name__ == "__main__":
    main()