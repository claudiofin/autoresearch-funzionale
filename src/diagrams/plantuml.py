"""PlantUML diagram generators.

Converts XState state machines to PlantUML state charts and sequence diagrams.
"""


def generate_plantuml_statechart(machine: dict) -> str:
    """Convert XState machine to PlantUML state diagram (hierarchical layout).
    
    Args:
        machine: XState machine dict.
    
    Returns:
        PlantUML state chart string.
    """
    lines = ["@startuml", ""]
    
    def _render_states(states: dict, indent: str = "    ") -> list:
        out = []
        for state_name, state_config in states.items():
            entry_actions = state_config.get("entry", [])
            exit_actions = state_config.get("exit", [])
            sub_states = state_config.get("states", {})
            
            note_lines = []
            if entry_actions:
                note_lines.append(f'{indent}    note: Entry: {", ".join(entry_actions)}')
            if exit_actions:
                note_lines.append(f'{indent}    note: Exit: {", ".join(exit_actions)}')
                
            if sub_states:
                out.append(f'{indent}state "{state_name}" {{')
                for note in note_lines:
                    out.append(note)
                initial_sub = state_config.get("initial", "")
                if initial_sub:
                    out.append(f'{indent}    [*] --> {initial_sub}')
                out.extend(_render_states(sub_states, indent + "    "))
                out.append(f'{indent}}}')
            else:
                if note_lines:
                    out.append(f'{indent}state "{state_name}" {{')
                    for note in note_lines:
                        out.append(note)
                    out.append(f'{indent}}}')
                else:
                    out.append(f'{indent}state "{state_name}"')
        return out

    def _render_transitions(states: dict, indent: str = "    ") -> list:
        out = []
        for state_name, state_config in states.items():
            transitions = state_config.get("on", {})
            for event, target in transitions.items():
                if isinstance(target, dict):
                    target_state = target.get("target", "unknown").lstrip('.')
                    guard = target.get("guard", "") or target.get("cond", "")
                    if guard:
                        out.append(f"{indent}{state_name} --> {target_state} : {event} [{guard}]")
                    else:
                        out.append(f"{indent}{state_name} --> {target_state} : {event}")
                elif isinstance(target, str):
                    target_state = target.lstrip('.')
                    out.append(f"{indent}{state_name} --> {target_state} : {event}")
                elif isinstance(target, list):
                    for t in target:
                        target_state = t.get("target", "unknown").lstrip('.') if isinstance(t, dict) else t.lstrip('.')
                        guard = t.get("cond", "") if isinstance(t, dict) else ""
                        if guard:
                            out.append(f"{indent}{state_name} --> {target_state} : {event} [{guard}]")
                        else:
                            out.append(f"{indent}{state_name} --> {target_state} : {event}")
            
            if "states" in state_config:
                out.extend(_render_transitions(state_config["states"], indent))
        return out

    if machine.get("initial"):
        lines.append(f'    [*] --> {machine["initial"]}')
    lines.append("")
    
    lines.extend(_render_states(machine.get("states", {})))
    lines.append("")
    lines.extend(_render_transitions(machine.get("states", {})))
    
    # Final states
    lines.extend(["", "    [*] <-- cancelled", "    [*] <-- success", "@enduml"])
    return "\n".join(lines)


def generate_plantuml_sequence(flows: list) -> str:
    """Generate PlantUML sequence diagrams from actual flows.
    
    Args:
        flows: List of flow dicts from LLM.
    
    Returns:
        PlantUML sequence diagram string.
    """
    if not flows:
        lines = [
            "@startuml", "",
            "participant User", "participant Interface", "participant Backend", "participant Database", "",
            "User -> Interface: START",
            "Interface -> Interface: showLoadingIndicator()",
            "Interface -> Backend: Request", "",
            "alt Success",
            "    Backend --> Interface: 200 OK",
            "    Interface -> Interface: showSuccessMessage()",
            "    Interface --> User: Display Result",
            "else Error",
            "    Backend --> Interface: 4xx/5xx Error",
            "    Interface -> Interface: showErrorMessage()",
            "    Interface --> User: Display Error",
            "else Timeout",
            "    Interface -> Interface: showTimeoutMessage()",
            "    Interface --> User: Display Timeout",
            "end", "", "@enduml"
        ]
        return "\n".join(lines)
    
    all_diagrams = []
    for flow in flows:
        lines = ["@startuml", "", f"== {flow['name'].replace('_', ' ').title()} ==", ""]
        lines.extend([
            "participant User", "participant Interface", "participant Backend", "participant Database", ""
        ])
        
        steps = flow.get("steps", [])
        for i, step in enumerate(steps):
            trigger = step.get("trigger", "")
            action = step.get("action", "")
            outcome = step.get("expected_outcome", "")
            error = step.get("error_scenario", "")
            
            if i == 0:
                lines.append(f"User -> Interface: {trigger}")
            else:
                lines.append(f"User -> Interface: {trigger}")
            
            if "POST" in action or "GET" in action or "PUT" in action or "DELETE" in action:
                lines.append(f"Interface -> Backend: {action}")
                lines.append(f"Backend -> Database: query")
                lines.append(f"Database --> Backend: result")
            
            if error:
                lines.append(f"")
                lines.append(f"alt Success")
                lines.append(f"    Backend --> Interface: {outcome}")
                lines.append(f"    Interface --> User: Display Result")
                lines.append(f"else Error")
                lines.append(f"    Backend --> Interface: {error}")
                lines.append(f"    Interface --> User: Show Error")
                lines.append(f"end")
            else:
                lines.append(f"    Backend --> Interface: {outcome}")
                lines.append(f"    Interface --> User: Display Result")
            
            lines.append("")
        
        lines.append("@enduml")
        all_diagrams.append("\n".join(lines))
    
    return "\n\n".join(all_diagrams)