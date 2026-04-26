"""
Spec orchestrator - coordinates the multi-step spec generation pipeline.
Step 1: Generate states
Step 2: Generate transitions
Step 3: Generate workflows
Step 4: Merge, compile, and validate
"""

import os
import sys
import json
import time

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from pipeline.frontend.spec.llm_client import call_llm_states, call_llm_transitions, call_llm_workflows
from state_machine.builder import generate_base_machine, build_state_config, add_transitions, add_transitions_to_branch, normalize_machine, add_workflows_to_machine, compile_machine
from state_machine.post_processing import remove_toplevel_duplicates, complete_missing_branches, clean_unreachable_states, validate_no_critical_patterns, create_missing_target_states
from diagrams.plantuml import generate_plantuml_statechart, generate_plantuml_sequence
from diagrams.markdown import generate_spec_markdown, _make_serializable


def run_analysis(
    context_file: str, 
    output_file: str, 
    time_budget: int, 
    analyst_suggestions: dict = None, 
    existing_machine_file: str = None,
    critic_feedback: dict = None,
    validator_feedback: dict = None
) -> dict:
    """Run the multi-step functional analysis and generate spec.md.
    
    MULTI-STEP APPROACH:
    1. Generate states (focused on completeness)
    2. Generate transitions (focused on connectivity)
    3. Generate workflows (focused on completion)
    4. Merge, compile, validate
    
    VALIDATOR FEEDBACK LOOP:
    If validator_feedback is provided (from previous iteration), it contains:
    - unreachable_states: list of state names that are not reachable
    - dead_end_states: list of states with no exit transitions
    - quality_score: current quality score
    This feedback is passed to the LLM to fix issues.
    """
    
    start_time = time.time()
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Read context
    with open(context_file, "r", encoding="utf-8") as f:
        context_text = f.read()
    
    # Load existing machine (if any)
    existing_machine = None
    if existing_machine_file and os.path.exists(existing_machine_file):
        with open(existing_machine_file, "r", encoding="utf-8") as f:
            existing_machine = json.load(f)
        print(f"  📦 Existing machine loaded: {len(existing_machine.get('states', {}))} states")
    
    print(f"Context loaded: {len(context_text)} characters")
    if analyst_suggestions:
        print(f"  📋 Analyst suggestions: {len(analyst_suggestions.get('states', []))} states, {len(analyst_suggestions.get('transitions', []))} transitions")
    if critic_feedback:
        critical = critic_feedback.get("summary", {}).get("critical_issues", [])
        print(f"  🚨 Critic feedback: {len(critical)} critical issues")
    if validator_feedback:
        unreachable = validator_feedback.get("unreachable_states", [])
        dead_ends = validator_feedback.get("dead_end_states", [])
        score = validator_feedback.get("quality_score", "N/A")
        print(f"  📊 Validator feedback: score={score}, unreachable={len(unreachable)}, dead_ends={len(dead_ends)}")
    
    # ========================================================================
    # STEP 1: Generate States
    # ========================================================================
    existing_states = None
    if existing_machine:
        existing_states = list(existing_machine.get("states", {}).keys())
    
    states = call_llm_states(
        context_text, 
        critic_feedback=critic_feedback,
        existing_states=existing_states,
        validator_feedback=validator_feedback,
        max_retries=3
    )
    
    # ========================================================================
    # STEP 2: Generate Transitions
    # ========================================================================
    existing_transitions = None
    if existing_machine:
        existing_transitions = []
        for sn, sc in existing_machine.get("states", {}).items():
            for ev, tgt in sc.get("on", {}).items():
                existing_transitions.append({"from_state": sn, "to_state": tgt, "event": ev})
    
    transitions = call_llm_transitions(
        context_text,
        states=states,
        existing_transitions=existing_transitions,
        validator_feedback=validator_feedback,
        max_retries=3
    )
    
    # ========================================================================
    # STEP 3: Generate Workflows
    # ========================================================================
    workflows = call_llm_workflows(
        context_text,
        states=states,
        transitions=transitions,
        analyst_suggestions=analyst_suggestions,
        validator_feedback=validator_feedback,
        max_retries=3
    )
    
    print(f"\n  📊 LLM Results: {len(states)} states, {len(transitions)} transitions, {len(workflows)} workflows")
    
    # ========================================================================
    # STEP 4: Build Machine
    # ========================================================================
    
    # Determine if we should use parallel states architecture
    has_workflows = len(workflows) > 0 or (analyst_suggestions and len(analyst_suggestions.get("workflows", [])) > 0)
    is_existing_parallel = existing_machine and existing_machine.get("type") == "parallel"
    use_parallel = has_workflows or is_existing_parallel
    
    # Build machine using modular builder
    machine = None
    
    if existing_machine and not critic_feedback:
        # Iterative mode: start from existing machine, add new states
        machine = existing_machine.copy()
        machine["states"] = dict(existing_machine.get("states", {}))
        
        # Add new states from LLM suggestions
        for state in states:
            state_name = state["name"]
            
            # Ignore dot-notation clones generated by LLM (e.g. success.dashboard)
            if "." in state_name:
                continue
                
            if state_name not in machine["states"]:
                machine["states"][state_name] = build_state_config(state)
            else:
                # Update existing state
                existing_entry = machine["states"][state_name].get("entry", [])
                new_entry = state.get("entry_actions", [])
                machine["states"][state_name]["entry"] = list(set(existing_entry + new_entry))
                
                existing_exit = machine["states"][state_name].get("exit", [])
                new_exit = state.get("exit_actions", [])
                machine["states"][state_name]["exit"] = list(set(existing_exit + new_exit))
                
                # Preserve or add hierarchical sub-states
                sub_states = state.get("sub_states", [])
                if sub_states:
                    new_config = build_state_config(state)
                    machine["states"][state_name]["initial"] = new_config["initial"]
                    existing_subs = machine["states"][state_name].get("states", {})
                    existing_subs.update(new_config.get("states", {}))
                    machine["states"][state_name]["states"] = existing_subs
        
        # Add transitions
        add_transitions(machine, transitions)
    else:
        # Generate from scratch with parallel architecture if workflows exist
        machine = generate_base_machine(use_parallel=use_parallel)
        
        if use_parallel:
            # In parallel mode, states go into navigation branch
            nav_branch = machine["states"]["navigation"]
            for state in states:
                state_name = state["name"]
                nav_branch["states"][state_name] = build_state_config(state)
            
            # Add transitions to navigation branch
            add_transitions_to_branch(machine, transitions)
            
            # Add workflows to active_workflows branch
            if has_workflows:
                workflow_list = workflows if workflows else analyst_suggestions.get("workflows", [])
                add_workflows_to_machine(machine, workflow_list)
                print(f"  🔄 Added {len(workflow_list)} workflows to active_workflows branch")
        else:
            # Legacy flat mode
            for state in states:
                state_name = state["name"]
                machine["states"][state_name] = build_state_config(state)
            
            # Add transitions
            add_transitions(machine, transitions)
    
    # Apply Pattern Compiler (Normalization, Auto-injection, Dedup, Error Injection, Global Exit, Dead State Cleanup, Target Resolution, Context Awareness)
    machine = compile_machine(machine)
    
    # Post-processing: validate against critical rules
    violations = validate_no_critical_patterns(machine)
    if violations:
        print(f"\n  ⚠️  CRITICAL RULE VIOLATIONS DETECTED ({len(violations)}):")
        for v in violations:
            print(f"    ❌ {v}")
        print(f"\n  💡 These violations will be reported to the critic for the next iteration.")
    else:
        print(f"  ✅ No critical rule violations")
    
    print(f"Generated state machine: {len(machine['states'])} states")
    
    # Generate diagrams using modular components
    statechart = generate_plantuml_statechart(machine)
    flows = []  # Flows come from LLM data, but we don't have them in multi-step mode
    sequence = generate_plantuml_sequence(flows)
    
    # Generate markdown spec using modular component
    llm_data = {
        "states": states,
        "transitions": transitions,
        "workflows": workflows,
        "edge_cases": [],
        "flows": [],
        "api_endpoints": [],
        "error_handling": [],
        "data_validation": []
    }
    
    spec_content = generate_spec_markdown(
        machine=machine,
        llm_data=llm_data,
        statechart=statechart,
        sequence=sequence,
        violations=violations,
    )
    
    # Write spec
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(spec_content)
    
    # Write XState (make serializable to handle lambda/function objects)
    xstate_file = output_file.replace(".md", "_machine.json")
    with open(xstate_file, "w", encoding="utf-8") as f:
        json.dump(_make_serializable(machine), f, indent=2)
    
    elapsed = time.time() - start_time
    
    metrics = {
        "states_count": len(machine["states"]),
        "transitions_count": sum(len(s.get("on", {})) for s in machine["states"].values()),
        "edge_cases_count": 0,
        "error_types_count": 1,
        "elapsed_seconds": elapsed,
        "spec_file": output_file,
        "machine_file": xstate_file,
    }
    
    return metrics


def run_multi_step_spec(
    context_file: str,
    output_file: str,
    time_budget: int,
    analyst_suggestions: dict = None,
    existing_machine_file: str = None,
    critic_feedback: dict = None,
    validator_feedback: dict = None
) -> dict:
    """Alias for run_analysis - multi-step spec generation with validator feedback.
    
    This function provides a clear entry point for iterative improvement
    when validator feedback is available from a previous iteration.
    """
    return run_analysis(
        context_file,
        output_file,
        time_budget,
        analyst_suggestions=analyst_suggestions,
        existing_machine_file=existing_machine_file,
        critic_feedback=critic_feedback,
        validator_feedback=validator_feedback
    )
