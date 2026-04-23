#!/usr/bin/env python3
"""
UI Generator Dinamico - Genera specifiche UI usando un LLM.

Legge spec_machine.json e project_context.md, usa un LLM per generare:
1. output/ui_specs/states/UI_<stato>.md — Specifiche per ogni stato macchina
2. output/ui_specs/screens/<screen>.md — Specifiche per ogni schermata reale
3. output/ui_specs/README.md — Indice con diagramma PlantUML

Il LLM analizza la macchina a stati e il contesto per generare UI specs
realistiche e coerenti con il prodotto reale.
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Configurazione LLM
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openai")  # openai, anthropic, ollama
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o")  # o "claude-3-5-sonnet-20241022", "llama3"
LLM_API_KEY = os.environ.get("OPENAI_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")  # Per Ollama o altri provider


def load_machine(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def load_context(path: str) -> str:
    with open(path, "r") as f:
        return f.read()


def load_spec(path: str) -> str:
    with open(path, "r") as f:
        return f.read()


def call_llm(prompt: str, system_prompt: str = "", max_tokens: int = 4096) -> str:
    """Chiama il LLM configurato e ritorna la risposta."""
    if LLM_PROVIDER == "openai":
        return _call_openai(prompt, system_prompt, max_tokens)
    elif LLM_PROVIDER == "anthropic":
        return _call_anthropic(prompt, system_prompt, max_tokens)
    elif LLM_PROVIDER == "ollama":
        return _call_ollama(prompt, system_prompt, max_tokens)
    else:
        raise ValueError(f"Provider LLM non supportato: {LLM_PROVIDER}")


def _call_openai(prompt: str, system_prompt: str, max_tokens: int) -> str:
    """Chiama OpenAI API."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL or None)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.7,
        )
        return response.choices[0].message.content
    except ImportError:
        print("❌ Installa openai: pip install openai")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Errore OpenAI: {e}")
        sys.exit(1)


def _call_anthropic(prompt: str, system_prompt: str, max_tokens: int) -> str:
    """Chiama Anthropic API."""
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=LLM_API_KEY)
        
        response = client.messages.create(
            model=LLM_MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except ImportError:
        print("❌ Installa anthropic: pip install anthropic")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Errore Anthropic: {e}")
        sys.exit(1)


def _call_ollama(prompt: str, system_prompt: str, max_tokens: int) -> str:
    """Chiama Ollama API (locale)."""
    try:
        import requests
        url = LLM_BASE_URL or "http://localhost:11434"
        payload = {
            "model": LLM_MODEL,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.7,
            }
        }
        response = requests.post(f"{url}/api/generate", json=payload, timeout=120)
        response.raise_for_status()
        return response.json().get("response", "")
    except ImportError:
        print("❌ Installa requests: pip install requests")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Errore Ollama: {e}")
        sys.exit(1)


def generate_state_spec_llm(state_name: str, state_def: dict, machine: dict, context: str, spec: str) -> str:
    """Genera UI spec per uno stato usando il LLM."""
    
    # Costruisci il contesto per il LLM
    states_info = json.dumps({state_name: state_def}, indent=2)
    
    # Trova stati correlati (incoming/outgoing)
    related = []
    for s_name, s_def in machine.get("states", {}).items():
        transitions = s_def.get("on", {})
        if state_name in transitions.values():
            event = [k for k, v in transitions.items() if v == state_name][0]
            related.append(f"- Da {s_name} tramite evento {event}")
        if state_name == s_name:
            for event, dest in transitions.items():
                related.append(f"- Verso {dest} tramite evento {event}")
    
    prompt = f"""Sei un Senior Product Manager e UI/UX Designer. Analizza lo stato della macchina a stati e genera una specifica UI completa.

## Contesto del Progetto
{context[:2000]}

## Specifica Funzionale
{spec[:2000]}

## Stato da Analizzare
```json
{states_info}
```

## Transizioni Correlate
{chr(10).join(related) if related else 'Nessuna transizione trovata'}

## Entry/Exit Actions
Entry: {state_def.get('entry', [])}
Exit: {state_def.get('exit', [])}

## Istruzioni
Genera un file Markdown completo per lo stato '{state_name}' che includa:

1. **Descrizione** — Cosa mostra questa schermata/stato all'utente
2. **Contesto** — Da dove si arriva e dove si può andare
3. **Dati Necessari** — Tabella con campi, tipi e descrizioni (basati sul contesto del progetto)
4. **Componenti UI** — Lista dei componenti visivi con tipo, elementi e interazioni
5. **Vincoli e Regole** — Regole di business e vincoli tecnici
6. **Note UI** — Layout, colori, animazioni, pattern
7. **Flusso Utente** — Diagramma testuale del flusso
8. **Riferimento Tecnico** — Entry/Exit actions

IMPORTANTE:
- Sii specifico e concreto, basati sul contesto del progetto reale
- Genera dati mock realistici (nomi, prezzi, ecc.)
- Descrivi componenti UI reali (card, badge, grafici, ecc.)
- Il file deve essere pronto per essere usato da un developer o da un AI UI generator
"""

    system_prompt = "Sei un esperto di specifiche UI/UX. Generi documentazione tecnica dettagliata e pronta per l'implementazione."
    
    return call_llm(prompt, system_prompt)


def discover_screens_llm(machine: dict, context: str, spec: str) -> list:
    """Usa il LLM per scoprire quali schermate generare basandosi sul contesto."""
    
    states_info = json.dumps(machine.get("states", {}), indent=2)
    
    prompt = f"""Sei un Senior Product Manager. Analizza il contesto del progetto e la macchina a stati per determinare quali schermate reali generare.

## Contesto del Progetto
{context[:3000]}

## Specifica Funzionale
{spec[:3000]}

## Stati della Macchina
```json
{states_info}
```

## Istruzioni
Identifica le schermate reali del prodotto basandoti sul contesto. Per ogni schermata, indica:
1. Nome screen (es. "01_login", "02_dashboard")
2. Quali stati della macchina sono correlati

Rispondi SOLO con un JSON array nel formato:
```json
[
  {{"name": "01_login", "states": ["app_idle", "authenticating", "sessione_scaduta"]}},
  {{"name": "02_dashboard", "states": ["successo", "caricamento", "vuoto", "errore"]}}
]
```

Non aggiungere altro testo, solo il JSON.
"""
    
    system_prompt = "Sei un analista funzionale. Identifichi le schermate di un'app basandoti sul contesto e sulla macchina a stati. Rispondi solo con JSON."
    
    try:
        response = call_llm(prompt, system_prompt, max_tokens=2048)
        # Estrai il JSON dalla risposta
        import re
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if json_match:
            screens = json.loads(json_match.group())
            print(f"  🧠 LLM ha identificato {len(screens)} schermate:")
            for s in screens:
                print(f"     - {s['name']}: {', '.join(s['states'])}")
            return screens
        else:
            print("  ⚠️  LLM non ha restituito JSON valido, uso default")
            return [
                {"name": "01_login", "states": ["app_idle", "authenticating", "sessione_scaduta", "iniziale", "errore"]},
                {"name": "02_dashboard", "states": ["successo", "caricamento", "vuoto", "errore"]},
                {"name": "03_catalogo", "states": ["successo", "caricamento", "vuoto", "errore"]},
                {"name": "04_offerte", "states": ["successo", "caricamento", "vuoto", "errore"]},
                {"name": "05_alert", "states": ["successo", "caricamento", "vuoto", "errore"]},
                {"name": "06_confronti", "states": ["successo", "caricamento", "vuoto", "errore"]},
            ]
    except Exception as e:
        print(f"  ⚠️  Errore discover_screens: {e}, uso default")
        return [
            {"name": "01_login", "states": ["app_idle", "authenticating", "sessione_scaduta", "iniziale", "errore"]},
            {"name": "02_dashboard", "states": ["successo", "caricamento", "vuoto", "errore"]},
            {"name": "03_catalogo", "states": ["successo", "caricamento", "vuoto", "errore"]},
            {"name": "04_offerte", "states": ["successo", "caricamento", "vuoto", "errore"]},
            {"name": "05_alert", "states": ["successo", "caricamento", "vuoto", "errore"]},
            {"name": "06_confronti", "states": ["successo", "caricamento", "vuoto", "errore"]},
        ]


def generate_screen_spec_llm(screen_name: str, related_states: list, machine: dict, context: str, spec: str) -> str:
    """Genera UI spec per una schermata reale usando il LLM."""
    
    # Estrai informazioni sugli stati correlati
    states_info = {}
    for state_name in related_states:
        if state_name in machine.get("states", {}):
            states_info[state_name] = machine["states"][state_name]
    
    prompt = f"""Sei un Senior Product Manager e UI/UX Designer. Analizza gli stati della macchina a stati e genera una specifica UI completa per la schermata reale del prodotto.

## Contesto del Progetto
{context[:3000]}

## Specifica Funzionale
{spec[:3000]}

## Schermata da Generare
{screen_name}

## Stati della Macchina Correlati
```json
{json.dumps(states_info, indent=2)}
```

## Istruzioni
Genera un file Markdown completo per la schermata '{screen_name}' che includa:

1. **Descrizione** — Cosa fa questa schermata nel prodotto reale
2. **Contesto** — Da dove si arriva (navigazione) e dove si può andare
3. **Dati Necessari** — Tabella con tutti i campi dati necessari (mock data realistici)
4. **Componenti UI** — Lista dettagliata di tutti i componenti visivi:
   - Nome componente
   - Tipo (card, lista, grafico, badge, ecc.)
   - Elementi che contiene
   - Interazioni possibili
5. **Stati della Macchina Correlati** — Tabella che mappa ogni stato UI (loading, successo, errore, vuoto) con link ai file states/
6. **Vincoli e Regole** — Regole di business, validazioni, cache, ecc.
7. **Note UI** — Layout, colori, animazioni, pattern specifici
8. **Flusso Utente** — Diagramma testuale del flusso completo
9. **Riferimento Tecnico** — Entry/Exit actions

IMPORTANTE:
- Sii specifico e concreto, basati SUL CONTESTO REALE DEL PROGETTO
- Genera nomi realistici per farmaci, prezzi, distributori, ecc.
- Descrivi componenti UI che un developer può implementare
- Pensa a come apparirebbe l'app reale sullo schermo
- Il file deve essere pronto per essere usato da un developer o da un AI UI generator (v0, Claude Artifacts, ecc.)
"""

    system_prompt = "Sei un esperto di specifiche UI/UX per app mobile. Generi documentazione tecnica dettagliata con componenti UI concreti e realistici."
    
    return call_llm(prompt, system_prompt)


def generate_index_llm(states: dict, screens: list, machine: dict) -> str:
    """Genera il README.md con indice usando il LLM."""
    
    states_list = ", ".join([f"`{s}`" for s in states.keys()])
    screens_list = ", ".join([f"`{s}`" for s in screens])
    
    prompt = f"""Genera un README.md per l'indice delle UI specifications.

## Stati della Macchina ({len(states)}):
{states_list}

## Schermate Reali ({len(screens)}):
{screens_list}

## Istruzioni
Genera un README.md con:
1. Titolo e descrizione
2. Tabella schermate reali con link
3. Tabella stati macchina con link
4. Diagramma PlantUML del flusso completo
5. Mappatura schermate → stati
6. Sezione "Come usare" con istruzioni per AI UI generators
7. Flussi principali

Usa emoji, tabelle formattate bene, e un tono professionale.
"""

    system_prompt = "Sei un technical writer. Generi documentazione chiara e ben formattata."
    
    return call_llm(prompt, system_prompt)


def generate_plantuml(machine: dict) -> str:
    """Genera il codice PlantUML dalla macchina a stati."""
    uml = "@startuml\n"
    uml += "skinparam state {\n"
    uml += "  BackgroundColor #E8F5E9\n"
    uml += "  BorderColor #2E7D32\n"
    uml += "  ArrowColor #1B5E20\n"
    uml += "}\n\n"
    
    initial = machine.get("initial", "")
    if initial:
        uml += f"  [*] --> {initial}\n"
    
    for state_name, state_def in machine.get("states", {}).items():
        transitions = state_def.get("on", {})
        for event, dest in transitions.items():
            uml += f"  {state_name} --> {dest} : {event}\n"
    
    uml += "@enduml"
    return uml


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Genera specifiche UI dinamicamente con LLM")
    parser.add_argument("--machine", default="output/spec/spec_machine.json", help="Percorso spec_machine.json")
    parser.add_argument("--context", default="output/context/project_context.md", help="Percorso project_context.md")
    parser.add_argument("--spec", default="output/spec/spec.md", help="Percorso spec.md")
    parser.add_argument("--output-dir", default="output/ui_specs", help="Directory di output")
    parser.add_argument("--provider", choices=["openai", "anthropic", "ollama"], default=LLM_PROVIDER, help="Provider LLM")
    parser.add_argument("--model", default=LLM_MODEL, help="Modello LLM")
    parser.add_argument("--api-key", default=LLM_API_KEY, help="API Key LLM")
    parser.add_argument("--base-url", default=LLM_BASE_URL, help="Base URL LLM (per Ollama)")
    parser.add_argument("--states-only", action="store_true", help="Genera solo gli stati")
    parser.add_argument("--screens-only", action="store_true", help="Genera solo le schermate")
    args = parser.parse_args()
    
    # Aggiorna configurazione globale
    global LLM_PROVIDER, LLM_MODEL, LLM_API_KEY, LLM_BASE_URL
    LLM_PROVIDER = args.provider
    LLM_MODEL = args.model
    LLM_API_KEY = args.api_key or LLM_API_KEY
    LLM_BASE_URL = args.base_url or LLM_BASE_URL
    
    if not LLM_API_KEY and LLM_PROVIDER != "ollama":
        print("❌ Imposta LLM_API_KEY o OPENAI_API_KEY")
        sys.exit(1)
    
    print(f"🤖 LLM Provider: {LLM_PROVIDER}")
    print(f"🧠 LLM Model: {LLM_MODEL}")
    
    # Carica input
    print(f"\n📦 Caricamento macchina a stati: {args.machine}")
    machine = load_machine(args.machine)
    
    print(f"📖 Caricamento contesto: {args.context}")
    context = load_context(args.context)
    
    print(f"📄 Caricamento specifica: {args.spec}")
    spec = load_spec(args.spec)
    
    states = machine.get("states", {})
    print(f"🔍 Trovati {len(states)} stati nella macchina")
    
    # Crea directory output
    states_dir = os.path.join(args.output_dir, "states")
    screens_dir = os.path.join(args.output_dir, "screens")
    os.makedirs(states_dir, exist_ok=True)
    os.makedirs(screens_dir, exist_ok=True)
    
    generated_states = []
    generated_screens = []
    
    # Genera stati (Livello 2)
    if not args.screens_only:
        print(f"\n🏗️  Generazione stati macchina (Livello 2)...")
        for state_name, state_def in states.items():
            print(f"  🔄 Generando UI spec per '{state_name}'...")
            
            try:
                md_content = generate_state_spec_llm(state_name, state_def, machine, context, spec)
                output_path = os.path.join(states_dir, f"UI_{state_name}.md")
                
                with open(output_path, "w") as f:
                    f.write(md_content)
                
                generated_states.append(state_name)
                print(f"    ✅ Scritto: {output_path}")
            except Exception as e:
                print(f"    ❌ Errore generando '{state_name}': {e}")
            
            # Rate limiting
            time.sleep(1)
    
    # Genera schermate (Livello 1) - SCOPerte dinamicamente dal LLM
    if not args.states_only:
        print(f"\n🔍 Scoperta schermate tramite LLM...")
        screen_definitions = discover_screens_llm(machine, context, spec)
        
        print(f"\n🖥️  Generazione schermate reali (Livello 1)...")
        for screen_def in screen_definitions:
            screen_name = screen_def["name"]
            related_states = screen_def["states"]
            print(f"  🔄 Generando schermata '{screen_name}'...")
            
            try:
                md_content = generate_screen_spec_llm(screen_name, related_states, machine, context, spec)
                output_path = os.path.join(screens_dir, f"{screen_name}.md")
                
                with open(output_path, "w") as f:
                    f.write(md_content)
                
                generated_screens.append(screen_name)
                print(f"    ✅ Scritto: {output_path}")
            except Exception as e:
                print(f"    ❌ Errore generando '{screen_name}': {e}")
            
            # Rate limiting
            time.sleep(1)
    
    # Genera README
    print(f"\n📋 Generando README.md...")
    try:
        readme_content = generate_index_llm(states, generated_screens, machine)
        # Aggiungi il diagramma PlantUML
        plantuml = generate_plantuml(machine)
        readme_content += f"\n\n## Diagramma di Flusso (PlantUML)\n\n```plantuml\n{plantuml}\n```\n"
        
        readme_path = os.path.join(args.output_dir, "README.md")
        with open(readme_path, "w") as f:
            f.write(readme_content)
        
        print(f"  ✅ Scritto: {readme_path}")
    except Exception as e:
        print(f"  ❌ Errore generando README: {e}")
    
    print(f"\n🎉 Completato!")
    print(f"   {len(generated_states)} stati generati in {states_dir}/")
    print(f"   {len(generated_screens)} schermate generate in {screens_dir}/")
    print(f"   README in {args.output_dir}/README.md")


if __name__ == "__main__":
    main()