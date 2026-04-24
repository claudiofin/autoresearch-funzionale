"""
PlantUML diagram generator for state machines.
"""


def _extract_plantuml_targets(target) -> list:
    """Extract target state names for PlantUML generation."""
    if isinstance(target, str):
        return [target]
    elif isinstance(target, dict):
        t = target.get("target", "")
        return [t] if t else []
    elif isinstance(target, list):
        targets = []
        for item in target:
            if isinstance(item, dict):
                t = item.get("target", "")
                if t:
                    targets.append(t)
            elif isinstance(item, str):
                targets.append(item)
        return targets
    return []


def generate_plantuml(machine: dict) -> str:
    """Generates PlantUML code with hierarchical layout."""
    uml = ["@startuml"]
    uml.append("skinparam state {")
    uml.append("  BackgroundColor #E8F5E9")
    uml.append("  BorderColor #2E7D32")
    uml.append("  ArrowColor #1B5E20")
    uml.append("}\n")
    
    initial = machine.get("initial", "")
    if initial:
        uml.append(f"[*] --> {initial}\n")
    
    def _render_states(states: dict, indent=""):
        res = []
        for state_name, state_config in states.items():
            sub_states = state_config.get("states", {})
            if sub_states:
                res.append(f"{indent}state {state_name} {{")
                sub_initial = state_config.get("initial", "")
                if sub_initial:
                    res.append(f"{indent}  [*] --> {sub_initial}")
                res.extend(_render_states(sub_states, indent + "  "))
                res.append(f"{indent}}}")
            else:
                res.append(f"{indent}state {state_name}")
        return res
        
    def _render_transitions(states: dict, indent=""):
        res = []
        for state_name, state_config in states.items():
            transitions = state_config.get("on", {})
            for event, target in transitions.items():
                for dest in _extract_plantuml_targets(target):
                    dest = dest.lstrip('.')
                    res.append(f"{indent}{state_name} --> {dest} : {event}")
            if "states" in state_config:
                res.extend(_render_transitions(state_config["states"], indent))
        return res

    uml.extend(_render_states(machine.get("states", {})))
    uml.append("\n' Transitions\n")
    uml.extend(_render_transitions(machine.get("states", {})))
    
    uml.append("@enduml")
    return "\n".join(uml)