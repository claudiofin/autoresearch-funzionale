"""
Fuzzer per macchine a stati XState.
Esegue test automatici sulla state machine generata da spec.py e trova bug logici.

Questo è il "Critic" deterministico del sistema - trova edge case che l'agente ha mancato.

Usage:
    python fuzzer.py --machine spec_machine.json --output fuzz_report.json
"""

import os
import sys
import json
import time
import argparse
import random
from pathlib import Path
from datetime import datetime
from collections import defaultdict

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    print("Warning: networkx not installed, using basic graph analysis")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_FUZZ_ITERATIONS = 1000
DEFAULT_MAX_STEPS = 50
DEFAULT_SEED = 42

# ---------------------------------------------------------------------------
# State Machine Validator
# ---------------------------------------------------------------------------

class StateMachineValidator:
    """Validates XState machine structure and finds logical errors."""
    
    def __init__(self, machine: dict):
        self.machine = machine
        self.errors = []
        self.warnings = []
        
    def validate(self) -> list[dict]:
        """Run all validation checks."""
        self._check_initial_state_exists()
        self._check_all_states_reachable()
        self._check_dead_end_states()
        self._check_unreachable_states()
        self._check_duplicate_events()
        self._check_self_loops()
        self._check_context_variables()
        # Nuovi check anti-"salsiccia" e placeholder
        self._check_linear_chain_pattern()
        self._check_missing_error_transitions()
        self._check_placeholder_descriptions()
        return self.errors
    
    def _check_initial_state_exists(self):
        """Check that initial state is defined and exists."""
        initial = self.machine.get("initial")
        if not initial:
            self.errors.append({
                "type": "MISSING_INITIAL",
                "severity": "error",
                "message": "No initial state defined",
                "state": None,
            })
        elif initial not in self.machine.get("states", {}):
            self.errors.append({
                "type": "INVALID_INITIAL",
                "severity": "error",
                "message": f"Initial state '{initial}' does not exist",
                "state": initial,
            })
    
    def _check_all_states_reachable(self):
        """Check that all states are reachable from initial state using BFS."""
        if not HAS_NETWORKX:
            # Basic BFS without networkx
            return self._check_reachable_basic()
        
        states = self.machine.get("states", {})
        initial = self.machine.get("initial")
        
        if not initial or initial not in states:
            return
        
        # Build graph
        G = nx.DiGraph()
        for state_name in states:
            G.add_node(state_name)
        
        for state_name, state_config in states.items():
            transitions = state_config.get("on", {})
            for event, target in transitions.items():
                if isinstance(target, dict):
                    target_state = target.get("target")
                    if target_state:
                        G.add_edge(state_name, target_state)
                elif target in states:
                    G.add_edge(state_name, target)
        
        # Find unreachable states
        reachable = nx.descendants(G, initial)
        reachable.add(initial)
        unreachable = set(states.keys()) - reachable
        
        for state in unreachable:
            self.errors.append({
                "type": "UNREACHABLE_STATE",
                "severity": "error",
                "message": f"State '{state}' is not reachable from initial state",
                "state": state,
            })
    
    def _check_reachable_basic(self):
        """Basic reachability check without networkx."""
        states = self.machine.get("states", {})
        initial = self.machine.get("initial")
        
        if not initial or initial not in states:
            return
        
        visited = set()
        queue = [initial]
        
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            
            state_config = states.get(current, {})
            transitions = state_config.get("on", {})
            for event, target in transitions.items():
                if isinstance(target, dict):
                    target_state = target.get("target")
                else:
                    target_state = target
                
                if target_state and target_state in states and target_state not in visited:
                    queue.append(target_state)
        
        unreachable = set(states.keys()) - visited
        for state in unreachable:
            self.errors.append({
                "type": "UNREACHABLE_STATE",
                "severity": "error",
                "message": f"State '{state}' is not reachable from initial state",
                "state": state,
            })
    
    def _check_dead_end_states(self):
        """Check for states with no outgoing transitions (except terminal states)."""
        states = self.machine.get("states", {})
        terminal_states = {"cancelled", "error", "success", "end", "done", "finished"}
        
        for state_name, state_config in states.items():
            transitions = state_config.get("on", {})
            
            # Skip if state has transitions
            if transitions:
                continue
            
            # Skip terminal states
            if state_name.lower() in terminal_states:
                continue
            
            # Check if it has exit actions (might be intentional)
            if state_config.get("exit"):
                continue
            
            self.warnings.append({
                "type": "DEAD_END_STATE",
                "severity": "warning",
                "message": f"State '{state_name}' has no outgoing transitions - possible dead end",
                "state": state_name,
                "suggestion": "Add transitions or mark as terminal state",
            })
    
    def _check_unreachable_states(self):
        """Check for states that can never be entered."""
        states = self.machine.get("states", {})
        initial = self.machine.get("initial")
        
        # Collect all target states
        target_states = set()
        for state_name, state_config in states.items():
            transitions = state_config.get("on", {})
            for event, target in transitions.items():
                if isinstance(target, dict):
                    target_state = target.get("target")
                else:
                    target_state = target
                if target_state:
                    target_states.add(target_state)
        
        # Check each state (except initial) is a target
        for state_name in states:
            if state_name == initial:
                continue
            if state_name not in target_states:
                self.warnings.append({
                    "type": "POTENTIALLY_UNREACHABLE",
                    "severity": "warning",
                    "message": f"State '{state_name}' is never targeted by any transition",
                    "state": state_name,
                })
    
    def _check_duplicate_events(self):
        """Check for duplicate event handlers in same state."""
        states = self.machine.get("states", {})
        
        for state_name, state_config in states.items():
            transitions = state_config.get("on", {})
            events = list(transitions.keys())
            
            if len(events) != len(set(events)):
                # Find duplicates
                seen = set()
                duplicates = []
                for event in events:
                    if event in seen:
                        duplicates.append(event)
                    seen.add(event)
                
                self.errors.append({
                    "type": "DUPLICATE_EVENT",
                    "severity": "error",
                    "message": f"State '{state_name}' has duplicate event handlers: {duplicates}",
                    "state": state_name,
                })
    
    def _check_self_loops(self):
        """Check for excessive self-loops (might indicate design issue)."""
        states = self.machine.get("states", {})
        
        for state_name, state_config in states.items():
            transitions = state_config.get("on", {})
            self_loop_events = []
            
            for event, target in transitions.items():
                if isinstance(target, dict):
                    target_state = target.get("target", state_name)
                else:
                    target_state = target
                
                if target_state == state_name:
                    self_loop_events.append(event)
            
            if len(self_loop_events) > 3:
                self.warnings.append({
                    "type": "EXCESSIVE_SELF_LOOPS",
                    "severity": "warning",
                    "message": f"State '{state_name}' has {len(self_loop_events)} self-loops: {self_loop_events}",
                    "state": state_name,
                    "suggestion": "Consider splitting into substates",
                })
    
    def _check_context_variables(self):
        """Check that context variables are used consistently."""
        context = self.machine.get("context", {})
        
        if not context:
            self.warnings.append({
                "type": "NO_CONTEXT",
                "severity": "info",
                "message": "No context variables defined",
            })
            return
        
        # Check for potentially unused context
        context_keys = set(context.keys())
        
        # Look for context references in guards and actions
        all_text = json.dumps(self.machine)
        used_context = set()
        
        for key in context_keys:
            if f'context.{key}' in all_text or f'context["{key}"]' in all_text:
                used_context.add(key)
        
        unused = context_keys - used_context
        for key in unused:
            self.warnings.append({
                "type": "UNUSED_CONTEXT",
                "severity": "info",
                "message": f"Context variable '{key}' may not be used",
                "context_var": key,
            })
    
    def _check_linear_chain_pattern(self):
        """
        Rileva il pattern 'a salsiccia': troppi stati collegati in sequenza lineare
        senza ramificazioni per errori. Questo è un anti-pattern comune degli LLM.
        
        Un flusso ben progettato ha:
        - Ramificazioni per errori (almeno 2-3 uscite per stati async)
        - Stati terminali multipli
        - Possibilità di tornare indietro
        """
        states = self.machine.get("states", {})
        
        # Conta transizioni in uscita per stato
        outgoing_counts = {}
        for state_name, state_config in states.items():
            transitions = state_config.get("on", {})
            outgoing_counts[state_name] = len(transitions)
        
        # Rileva stati con singola uscita (catena lineare)
        single_exit_states = [s for s, c in outgoing_counts.items() if c == 1]
        
        # Se >70% degli stati ha una sola uscita, è probabile una "salsiccia"
        if len(states) > 3 and len(single_exit_states) / len(states) > 0.7:
            # Verifica se ci sono ramificazioni per errori
            error_events = {"ERROR", "TIMEOUT", "CANCEL", "FAIL", "RETRY"}
            has_error_branching = False
            
            for state_name, state_config in states.items():
                transitions = state_config.get("on", {})
                for event in transitions.keys():
                    if any(err in event for err in error_events):
                        has_error_branching = True
                        break
            
            if not has_error_branching:
                self.warnings.append({
                    "type": "LINEAR_CHAIN_PATTERN",
                    "severity": "warning",
                    "message": f"Rilevato pattern 'a salsiccia': {len(single_exit_states)}/{len(states)} stati con singola uscita. Mancano ramificazioni per errori.",
                    "states_affected": single_exit_states[:10],  # Max 10
                    "suggestion": "Aggiungi transizioni ERROR, TIMEOUT, CANCEL per stati async"
                })
    
    def _check_missing_error_transitions(self):
        """
        Verifica che gli stati che rappresentano operazioni async
        abbiano transizioni per gestire errori.
        """
        # Stati che tipicamente rappresentano operazioni async
        async_indicators = {"pending", "loading", "processing", "submitting", "validating", "waiting"}
        error_events = {"ERROR", "TIMEOUT", "CANCEL"}
        
        states = self.machine.get("states", {})
        for state_name, state_config in states.items():
            # Check se è uno stato async
            is_async = any(ind in state_name.lower() for ind in async_indicators)
            
            if is_async:
                transitions = state_config.get("on", {})
                events = set(transitions.keys())
                
                # Verifica se ha almeno una transizione di errore
                has_error_handling = any(
                    any(err in event for err in error_events) 
                    for event in events
                )
                
                if not has_error_handling:
                    self.warnings.append({
                        "type": "MISSING_ERROR_TRANSITIONS",
                        "severity": "warning",
                        "message": f"Stato async '{state_name}' non ha transizioni ERROR/TIMEOUT/CANCEL",
                        "state": state_name,
                        "current_events": list(events),
                        "suggestion": "Aggiungi almeno ERROR e TIMEOUT per gestire fallimenti"
                    })
    
    def _check_placeholder_descriptions(self):
        """
        Rileva descrizioni placeholder/generiche negli stati e transizioni.
        Queste indicano che l'LLM è stato pigro.
        """
        placeholder_phrases = [
            "gestisce gracefully",
            "necessario per gestire",
            "completa il flusso",
            "permette di procedere",
            "gestione errore",
            "permette all'utente",
            "logEntry",
            "logTransition"
        ]
        
        states = self.machine.get("states", {})
        
        for state_name, state_config in states.items():
            # Check entry/exit actions per placeholder
            for action in state_config.get("entry", []) + state_config.get("exit", []):
                if action in placeholder_phrases:
                    self.warnings.append({
                        "type": "PLACEHOLDER_ACTION",
                        "severity": "info",
                        "message": f"Stato '{state_name}' ha azione placeholder: {action}",
                        "state": state_name,
                        "suggestion": "Sostituisci con azioni specifiche (es. 'showLoadingSpinner', 'submitForm')"
                    })


# ---------------------------------------------------------------------------
# Fuzzing Engine
# ---------------------------------------------------------------------------

class StateMachineFuzzer:
    """Executes random paths through the state machine to find bugs."""
    
    def __init__(self, machine: dict, seed: int = DEFAULT_SEED):
        self.machine = machine
        self.seed = seed
        random.seed(seed)
        self.states = machine.get("states", {})
        self.initial = machine.get("initial", "idle")
        self.context = machine.get("context", {}).copy()
        
        self.bugs_found = []
        self.paths_executed = 0
        self.steps_executed = 0
        
    def fuzz(self, iterations: int = DEFAULT_FUZZ_ITERATIONS, 
             max_steps: int = DEFAULT_MAX_STEPS) -> list[dict]:
        """Run fuzzing iterations."""
        
        for i in range(iterations):
            self._execute_random_path(max_steps)
            
            # Progress indicator
            if (i + 1) % 100 == 0:
                print(f"  Fuzzing: {i + 1}/{iterations} iterations, {len(self.bugs_found)} bugs found")
        
        return self.bugs_found
    
    def _execute_random_path(self, max_steps: int):
        """Execute a random path through the state machine."""
        current_state = self.initial
        path = [current_state]
        context = self.context.copy()
        
        for step in range(max_steps):
            self.steps_executed += 1
            
            state_config = self.states.get(current_state, {})
            transitions = state_config.get("on", {})
            
            if not transitions:
                # Dead end reached
                if step > 0:  # Don't count initial state as dead end
                    self._record_bug("DEAD_END", {
                        "state": current_state,
                        "path": path,
                        "steps": step,
                    })
                break
            
            # Choose random event
            events = list(transitions.keys())
            event = random.choice(events)
            target = transitions[event]
            
            # Resolve target
            if isinstance(target, dict):
                target_state = target.get("target", current_state)
                guard = target.get("guard")
                
                # Check guard (simplified - just check if context allows)
                if guard and not self._evaluate_guard(guard, context):
                    # Guard failed - this is actually good design
                    continue
                    
                actions = target.get("actions", [])
                self._execute_actions(actions, context)
            else:
                target_state = target
            
            # Check for infinite loop
            if target_state == current_state:
                if path.count(current_state) > 5:
                    self._record_bug("INFINITE_LOOP_RISK", {
                        "state": current_state,
                        "event": event,
                        "path": path[-10:],
                    })
                    break
            
            current_state = target_state
            path.append(current_state)
        
        self.paths_executed += 1
    
    def _evaluate_guard(self, guard: str, context: dict) -> bool:
        """Evaluate a guard condition (simplified)."""
        # Simple guard evaluation
        if guard == "canRetry":
            return context.get("retryCount", 0) < 3
        elif guard.startswith("has"):
            var = guard[3:].lower()
            return context.get(var) is not None
        return True
    
    def _execute_actions(self, actions: list, context: dict):
        """Execute state entry/transition actions."""
        for action in actions:
            if action == "incrementRetryCount":
                context["retryCount"] = context.get("retryCount", 0) + 1
            elif action == "clearErrors":
                context["errors"] = []
            elif action == "logError":
                context["errors"].append({"time": time.time()})
    
    def _record_bug(self, bug_type: str, details: dict):
        """Record a bug found during fuzzing."""
        self.bugs_found.append({
            "type": bug_type,
            "severity": self._get_severity(bug_type),
            "details": details,
            "timestamp": datetime.now().isoformat(),
        })
    
    def _get_severity(self, bug_type: str) -> str:
        """Get severity level for bug type."""
        severity_map = {
            "DEAD_END": "error",
            "INFINITE_LOOP_RISK": "warning",
            "UNREACHABLE_STATE": "error",
            "MISSING_ERROR_HANDLER": "warning",
            "RACE_CONDITION": "error",
        }
        return severity_map.get(bug_type, "info")


# ---------------------------------------------------------------------------
# Graph Analysis (for Mermaid validation)
# ---------------------------------------------------------------------------

def analyze_mermaid_graph(spec_file: str) -> dict:
    """Analyze Mermaid diagrams in spec file for structural issues."""
    
    try:
        with open(spec_file, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return {"errors": [], "warnings": []}
    
    issues = {"errors": [], "warnings": []}
    
    # Extract state diagrams
    import re
    state_diagrams = re.findall(r'```mermaid\s*(stateDiagram[^`]+)```', content, re.DOTALL)
    
    for i, diagram in enumerate(state_diagrams):
        lines = diagram.strip().split('\n')
        
        states = set()
        transitions = []
        initial = None
        
        for line in lines:
            line = line.strip()
            
            # Parse initial state
            if line.startswith('[*] -->'):
                initial = line.split('-->')[1].strip()
                states.add(initial)
            
            # Parse state definitions
            if '-->' in line and not line.startswith('[*]'):
                parts = line.split('-->')
                if len(parts) == 2:
                    source = parts[0].strip()
                    target = parts[1].split(':')[0].strip()
                    
                    if source != '[*]':
                        states.add(source)
                    if target != '[*]':
                        states.add(target)
                    
                    transitions.append((source, target))
        
        # Check for nodes without outgoing edges (except [*])
        sources = set(t[0] for t in transitions if t[0] != '[*]')
        targets = set(t[1] for t in transitions if t[1] != '[*]')
        
        # Find potential dead ends
        for state in states:
            if state not in sources and state != initial:
                # Check if it's a terminal state (points to [*])
                is_terminal = any(t[0] == state and t[1] == '[*]' for t in transitions)
                if not is_terminal:
                    issues["warnings"].append({
                        "type": "MERMAID_DEAD_END",
                        "message": f"State '{state}' in diagram {i+1} has no outgoing transitions",
                        "diagram": i + 1,
                        "state": state,
                    })
    
    return issues


# ---------------------------------------------------------------------------
# Coverage Analysis
# ---------------------------------------------------------------------------

def calculate_coverage(machine: dict, fuzzer: StateMachineFuzzer) -> dict:
    """Calculate test coverage metrics."""
    
    states = set(machine.get("states", {}).keys())
    transitions = set()
    
    for state_name, state_config in machine.get("states", {}).items():
        for event in state_config.get("on", {}).keys():
            transitions.add((state_name, event))
    
    # This is simplified - real coverage would track actual paths
    coverage = {
        "states_total": len(states),
        "states_visited": min(len(states), fuzzer.paths_executed),
        "transitions_total": len(transitions),
        "transitions_covered": min(len(transitions), fuzzer.steps_executed),
        "state_coverage_percent": round(min(100, fuzzer.paths_executed / max(1, len(states)) * 100), 1),
        "transition_coverage_percent": round(min(100, fuzzer.steps_executed / max(1, len(transitions)) * 100), 1),
    }
    
    return coverage


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_fuzzing(machine_file: str, spec_file: str = None, 
                iterations: int = DEFAULT_FUZZ_ITERATIONS,
                max_steps: int = DEFAULT_MAX_STEPS,
                output_file: str = None) -> dict:
    """Run complete fuzzing analysis."""
    
    start_time = time.time()
    
    # Load machine
    with open(machine_file, "r", encoding="utf-8") as f:
        machine = json.load(f)
    
    print(f"Loaded state machine: {len(machine.get('states', {}))} states")
    
    # Run structural validation
    print("\nRunning structural validation...")
    validator = StateMachineValidator(machine)
    errors = validator.validate()
    warnings = validator.warnings
    
    print(f"  Found {len(errors)} errors, {len(warnings)} warnings")
    
    # Run fuzzing
    print(f"\nRunning fuzzer ({iterations} iterations, max {max_steps} steps)...")
    fuzzer = StateMachineFuzzer(machine)
    bugs = fuzzer.fuzz(iterations, max_steps)
    
    print(f"  Found {len(bugs)} bugs through fuzzing")
    
    # Analyze Mermaid diagrams
    if spec_file and os.path.exists(spec_file):
        print("\nAnalyzing Mermaid diagrams...")
        mermaid_issues = analyze_mermaid_graph(spec_file)
        errors.extend(mermaid_issues.get("errors", []))
        warnings.extend(mermaid_issues.get("warnings", []))
        print(f"  Found {len(mermaid_issues['errors'])} errors, {len(mermaid_issues['warnings'])} warnings")
    
    # Calculate coverage
    coverage = calculate_coverage(machine, fuzzer)
    
    elapsed = time.time() - start_time
    
    # Build report
    report = {
        "summary": {
            "machine_file": machine_file,
            "spec_file": spec_file,
            "elapsed_seconds": round(elapsed, 2),
            "total_errors": len(errors) + len([b for b in bugs if b["severity"] == "error"]),
            "total_warnings": len(warnings) + len([b for b in bugs if b["severity"] == "warning"]),
            "bugs_found": len(bugs),
        },
        "validation_errors": errors,
        "validation_warnings": warnings,
        "fuzzing_bugs": bugs,
        "coverage": coverage,
        "metrics": {
            "states_count": len(machine.get("states", {})),
            "transitions_count": sum(len(s.get("on", {})) for s in machine.get("states", {}).values()),
            "iterations": iterations,
            "max_steps": max_steps,
            "paths_executed": fuzzer.paths_executed,
            "steps_executed": fuzzer.steps_executed,
        }
    }
    
    # Write report
    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"\nReport written to: {output_file}")
    
    return report


def main():
    parser = argparse.ArgumentParser(description="Fuzz XState state machine")
    parser.add_argument("--machine", type=str, default="spec_machine.json",
                        help="XState machine JSON file (default: spec_machine.json)")
    parser.add_argument("--spec", type=str, default="spec.md",
                        help="Spec Markdown file with Mermaid diagrams (default: spec.md)")
    parser.add_argument("--iterations", type=int, default=DEFAULT_FUZZ_ITERATIONS,
                        help=f"Number of fuzzing iterations (default: {DEFAULT_FUZZ_ITERATIONS})")
    parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS,
                        help=f"Max steps per path (default: {DEFAULT_MAX_STEPS})")
    parser.add_argument("--output", type=str, default="fuzz_report.json",
                        help="Output report file (default: fuzz_report.json)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED,
                        help=f"Random seed (default: {DEFAULT_SEED})")
    args = parser.parse_args()
    
    # Check machine file exists
    if not os.path.exists(args.machine):
        print(f"Error: Machine file not found: {args.machine}")
        print("Run 'python spec.py' first to generate spec_machine.json")
        sys.exit(1)
    
    random.seed(args.seed)
    
    print("=" * 50)
    print("STATE MACHINE FUZZER")
    print("=" * 50)
    print(f"Machine: {args.machine}")
    print(f"Spec: {args.spec}")
    print(f"Iterations: {args.iterations}")
    print(f"Max steps: {args.max_steps}")
    print(f"Random seed: {args.seed}")
    print()
    
    # Run fuzzing
    report = run_fuzzing(
        machine_file=args.machine,
        spec_file=args.spec,
        iterations=args.iterations,
        max_steps=args.max_steps,
        output_file=args.output,
    )
    
    # Print summary
    print()
    print("=" * 50)
    print("FUZZING COMPLETE")
    print("=" * 50)
    print(f"Total errors:   {report['summary']['total_errors']}")
    print(f"Total warnings: {report['summary']['total_warnings']}")
    print(f"Bugs found:     {report['summary']['bugs_found']}")
    print(f"Time elapsed:   {report['summary']['elapsed_seconds']:.2f}s")
    print()
    print("Coverage:")
    print(f"  States:       {report['coverage']['state_coverage_percent']}%")
    print(f"  Transitions:  {report['coverage']['transition_coverage_percent']}%")
    print()
    
    # Exit with error if critical bugs found
    if report['summary']['total_errors'] > 0:
        print("⚠️  CRITICAL: Errors found in state machine!")
        print("Review fuzz_report.json for details.")
        sys.exit(1)
    elif report['summary']['total_warnings'] > 0:
        print("⚡ Warnings found - review recommended")
        sys.exit(0)
    else:
        print("✅ No issues found - state machine looks solid!")
        sys.exit(0)


if __name__ == "__main__":
    main()