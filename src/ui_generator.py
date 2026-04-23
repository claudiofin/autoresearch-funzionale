#!/usr/bin/env python3
"""
UI Generator - Genera specifiche UI tool-agnostic dalla macchina a stati.

Legge spec_machine.json e project_context.md, genera:
1. output/ui_specs/README.md — Indice delle UI con link
2. output/ui_specs/UI_<stato>.md — Prompt dettagliato per ogni stato UI

Output completamente indipendente da qualsiasi strumento di UI generation.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path


# Stati che sono "transitori" (loading, authenticating) e non meritano una UI spec
TRANSIENT_STATES = {"caricamento", "authenticating"}


def load_machine(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def load_context(path: str) -> str:
    with open(path, "r") as f:
        return f.read()


def get_state_description(state_name: str, state_def: dict, context: str) -> str:
    """Genera una descrizione testuale dello stato basata su entry/exit actions."""
    entry = state_def.get("entry", [])
    exit_actions = state_def.get("exit", [])
    
    descriptions = {
        "app_idle": "Schermata iniziale dell'applicazione. Punto di ingresso del flusso, dove l'utente avvia il processo o si trova prima dell'autenticazione.",
        "iniziale": "Schermata di validazione iniziale. L'utente inserisce i dati di accesso o le credenziali. Vengono validati i parametri prima di procedere.",
        "caricamento": "Stato transitorio di loading. Mostra skeleton UI mentre i dati vengono caricati dal server. Non è una schermata permanente.",
        "vuoto": "Schermata quando non ci sono dati da visualizzare. L'utente può ricaricare o tornare indietro.",
        "errore": "Schermata di errore. Mostra banner e toast di errore quando si verifica un problema (rete, timeout, ecc.).",
        "successo": "Schermata principale con dati caricati con successo. Dashboard o vista principale dell'applicazione.",
        "sessione_scaduta": "Schermata di riautenticazione. Appare quando la sessione è scaduta e l'utente deve effettuare nuovamente il login.",
        "authenticating": "Stato transitorio di verifica token. Non visibile all'utente, gestisce la validazione delle credenziali.",
    }
    
    return descriptions.get(state_name, f"Stato '{state_name}' nel flusso dell'applicazione.")


def get_state_context(state_name: str, state_def: dict, machine: dict) -> dict:
    """Determina da dove si arriva e dove si può andare."""
    states = machine.get("states", {})
    
    # Trova stati che portano a questo stato
    incoming = []
    for s_name, s_def in states.items():
        transitions = s_def.get("on", {})
        if state_name in transitions.values():
            event = [k for k, v in transitions.items() if v == state_name][0]
            incoming.append((s_name, event))
    
    # Trova stati di destinazione
    outgoing = []
    transitions = state_def.get("on", {})
    for event, dest in transitions.items():
        outgoing.append((dest, event))
    
    return {
        "incoming": incoming,
        "outgoing": outgoing,
    }


def get_mock_data(state_name: str, context: str) -> list:
    """Genera mock data realistici basati sul contesto del progetto."""
    mock_data = {
        "app_idle": [
            ("email", "string", "Email dell'utente (es. demo@vetunita.it)"),
            ("password", "string", "Password (min. 8 caratteri)"),
        ],
        "iniziale": [
            ("credentials", "object", "Credenziali di accesso validate"),
            ("config", "object", "Configurazione dell'app caricata"),
        ],
        "vuoto": [
            ("message", "string", "Nessun dato disponibile da visualizzare"),
            ("action_hint", "string", "Prova a ricaricare la pagina"),
        ],
        "errore": [
            ("error_code", "string", "Codice errore (es. NET_001, TIMEOUT_001)"),
            ("error_message", "string", "Messaggio descrittivo per l'utente"),
            ("retry_available", "boolean", "Se è possibile riprovare"),
        ],
        "successo": [
            ("risparmio_ytd", "number", "Risparmio totale anno in corso (es. $42,850)"),
            ("distributori", "array", "Lista distributori con percentuali"),
            ("acquisti_recenti", "array", "Ultimi acquisti effettuati"),
            ("cluster_info", "object", "Informazioni sul cluster di appartenenza"),
        ],
        "sessione_scaduta": [
            ("redirect_url", "string", "URL della pagina di login"),
            ("message", "string", "La sessione è scaduta, effettua nuovamente il login"),
        ],
    }
    
    return mock_data.get(state_name, [])


def get_interactions(state_name: str, state_def: dict) -> list:
    """Estrae le interazioni possibili dallo stato."""
    transitions = state_def.get("on", {})
    interactions = []
    
    interaction_names = {
        "AVVIA_CARICAMENTO": ("Avvia", "Pulsante principale per iniziare il flusso"),
        "START_FLOW": ("Inizia", "Pulsante per avviare il processo"),
        "VALIDATE_TOKEN": ("Accedi", "Pulsante di login/autenticazione"),
        "INPUT_INVALIDO": ("Correggi", "Azione per correggere input errato"),
        "VALIDATE_AND_LOAD": ("Conferma e Carica", "Convalida i dati e avvia il caricamento"),
        "DATI_CARICATI": ("Continua", "Procedi con i dati caricati"),
        "ERRORE_RETE": ("Riprova", "Riprovare l'operazione"),
        "TIMEOUT": ("Riprova", "Riprovare per timeout"),
        "FETCH_SUCCESS": ("Visualizza", "Visualizza i dati caricati"),
        "FETCH_EMPTY": ("Ricarica", "Ricarica la pagina"),
        "FETCH_ERROR": ("Riprova", "Riprovare il caricamento"),
        "RICARICA": ("Ricarica", "Ricarica i dati"),
        "ANNULLA": ("Annulla", "Torna indietro / Annulla"),
        "RIPROVA": ("Riprova", "Riprovare l'operazione"),
        "RIAUTENTICAZIONE": ("Riautenticati", "Effettuare nuovamente il login"),
        "TOKEN_VALIDO": ("Procedi", "Token valido, procedi"),
        "TORNA_INDIETRO": ("Torna Indietro", "Torna alla schermata precedente"),
        "AGGIORNA": ("Aggiorna", "Aggiorna i dati"),
    }
    
    for event, dest in transitions.items():
        label, desc = interaction_names.get(event, (event.replace("_", " ").title(), f"Evento: {event}"))
        interactions.append({
            "label": label,
            "event": event,
            "destination": dest,
            "description": desc,
        })
    
    return interactions


def get_constraints(state_name: str, state_def: dict) -> list:
    """Genera vincoli e regole per lo stato."""
    constraints = {
        "app_idle": [
            "I campi email e password devono essere validi prima di abilitare il pulsante di accesso",
            "Deve essere presente un link per 'Password dimenticata?'",
            "Supporto per accesso guest/demo",
        ],
        "iniziale": [
            "Validazione input prima del caricamento",
            "Configurazione caricata prima di procedere",
            "Gestione input invalido con messaggio chiaro",
        ],
        "vuoto": [
            "Mostrare un'illustrazione o icona per stato vuoto",
            "Testo descrittivo che spiega perché non ci sono dati",
            "Azione di ricarica sempre disponibile",
        ],
        "errore": [
            "Messaggio di errore chiaro e non tecnico",
            "Azione di retry sempre disponibile quando possibile",
            "Logging dell'errore per debugging",
            "Possibilità di contattare il supporto",
        ],
        "successo": [
            "Pull-to-refresh per aggiornare i dati",
            "Skeleton loading durante l'aggiornamento",
            "Cache dei dati per accesso offline",
            "Gestione sessione scaduta durante la visualizzazione",
        ],
        "sessione_scaduta": [
            "Salvataggio dello stato corrente prima del redirect",
            "Possibilità di tornare alla schermata precedente dopo il login",
            "Clear dei token scaduti",
        ],
    }
    
    return constraints.get(state_name, [])


def get_ui_notes(state_name: str, state_def: dict) -> list:
    """Note UI generiche per lo stato."""
    notes = {
        "app_idle": [
            "Layout centrato con card di login",
            "Logo dell'app in alto",
            "Campi input con icone (email, lock)",
            "Pulsante primario grande e visibile",
            "Link secondari in basso (password dimenticata, registrazione)",
        ],
        "iniziale": [
            "Form con validazione inline",
            "Feedback visivo per campi validi/invalidi",
            "Pulsante disabilitato fino a validazione completa",
        ],
        "vuoto": [
            "Illustrazione SVG/animata per stato vuoto",
            "Testo descrittivo centrato",
            "Pulsante di azione principale (ricarica)",
            "Design pulito e non frustrante",
        ],
        "errore": [
            "Icona di errore visibile (⚠️ o similar)",
            "Banner rosso in alto o messaggio centrato",
            "Toast di errore per dettagli tecnici",
            "Pulsante di retry prominente",
        ],
        "successo": [
            "Dashboard con griglia di card",
            "Grafici a barre per confronti",
            "Badge e indicatori di stato",
            "Pull-to-refresh gesture",
            "Skeleton shimmer durante loading",
        ],
        "sessione_scaduta": [
            "Modal o schermata intera con overlay",
            "Messaggio chiaro sulla scadenza sessione",
            "Pulsante di login prominente",
            "Opzione per salvare il lavoro corrente",
        ],
    }
    
    return notes.get(state_name, [])


def generate_ui_spec(state_name: str, state_def: dict, machine: dict, context: str) -> str:
    """Genera il contenuto Markdown per uno stato UI."""
    description = get_state_description(state_name, state_def, context)
    ctx = get_state_context(state_name, state_def, machine)
    mock_data = get_mock_data(state_name, context)
    interactions = get_interactions(state_name, state_def)
    constraints = get_constraints(state_name, state_def)
    ui_notes = get_ui_notes(state_name, state_def)
    
    # Header
    md = f"# Stato: `{state_name}`\n\n"
    md += f"## Descrizione\n\n{description}\n\n"
    
    # Contesto
    md += "## Contesto\n\n"
    if ctx["incoming"]:
        md += "**Da dove si arriva:**\n"
        for src, event in ctx["incoming"]:
            md += f"- `{src}` → evento `{event}`\n"
    else:
        md += "- Stato iniziale del flusso\n"
    md += "\n"
    
    if ctx["outgoing"]:
        md += "**Dove si può andare:**\n"
        for dest, event in ctx["outgoing"]:
            md += f"- `{event}` → `{dest}`\n"
    md += "\n"
    
    # Dati Necessari
    if mock_data:
        md += "## Dati Necessari\n\n"
        for name, type_, desc in mock_data:
            md += f"- **`{name}`** ({type_}): {desc}\n"
        md += "\n"
    
    # Azioni/Interazioni
    if interactions:
        md += "## Azioni/Interazioni\n\n"
        md += "| Azione | Evento | Destinazione | Descrizione |\n"
        md += "|--------|--------|--------------|-------------|\n"
        for inter in interactions:
            md += f"| {inter['label']} | `{inter['event']}` | `{inter['destination']}` | {inter['description']} |\n"
        md += "\n"
    
    # Vincoli e Regole
    if constraints:
        md += "## Vincoli e Regole\n\n"
        for c in constraints:
            md += f"- {c}\n"
        md += "\n"
    
    # Note UI
    if ui_notes:
        md += "## Note UI\n\n"
        for note in ui_notes:
            md += f"- {note}\n"
        md += "\n"
    
    # Entry/Exit Actions (riferimento tecnico)
    entry = state_def.get("entry", [])
    exit_actions = state_def.get("exit", [])
    if entry or exit_actions:
        md += "## Riferimento Tecnico (Entry/Exit Actions)\n\n"
        if entry:
            md += "**Entry:**\n"
            for a in entry:
                md += f"- `{a}`\n"
        if exit_actions:
            md += "\n**Exit:**\n"
            for a in exit_actions:
                md += f"- `{a}`\n"
        md += "\n"
    
    return md


def generate_index(states: dict, machine: dict, output_dir: str) -> str:
    """Genera il README.md con l'indice di tutte le UI specs."""
    md = "# UI Specifications — Indice\n\n"
    md += f"Generato il: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    md += "Questo file contiene l'indice di tutte le specifiche UI generate dalla macchina a stati.\n\n"
    md += "---\n\n"
    
    # Tabella indice
    md += "## 📋 Elenco Stati UI\n\n"
    md += "| # | Stato | File | Tipo | Descrizione |\n"
    md += "|---|-------|------|------|-------------|\n"
    
    idx = 1
    for state_name in states:
        is_transient = state_name in TRANSIENT_STATES
        state_type = "⏳ Transitorio" if is_transient else "🖥️ Schermata"
        filename = f"UI_{state_name}.md"
        filepath = f"[{filename}]({filename})"
        
        description = get_state_description(state_name, states[state_name], "")
        # Trunca descrizione per la tabella
        if len(description) > 60:
            description = description[:57] + "..."
        
        md += f"| {idx} | `{state_name}` | {filepath} | {state_type} | {description} |\n"
        idx += 1
    
    md += "\n---\n\n"
    
    # Diagramma di flusso (Mermaid)
    md += "## 🗺️ Diagramma di Flusso\n\n"
    md += "```mermaid\n"
    md += "stateDiagram-v2\n"
    
    initial = machine.get("initial", "")
    if initial:
        md += f"    [*] --> {initial}\n"
    
    for state_name, state_def in states.items():
        transitions = state_def.get("on", {})
        for event, dest in transitions.items():
            md += f"    {state_name} --> {dest} : {event}\n"
    
    md += "```\n\n"
    md += "---\n\n"
    
    # Come usare
    md += "## 🚀 Come Usare Questi File\n\n"
    md += "1. **Scegli lo stato** che ti interessa dalla tabella sopra\n"
    md += "2. **Apri il file** `.md` corrispondente\n"
    md += "3. **Copia il contenuto** del file\n"
    md += "4. **Incollalo** nel tuo strumento UI preferito:\n"
    md += "   - [v0.dev](https://v0.dev) → UI React/Tailwind\n"
    md += "   - [Claude Artifacts](https://claude.ai) → Componenti con logica\n"
    md += "   - [Bolt.new](https://bolt.new) → App complete\n"
    md += "   - [Lovable](https://lovable.dev) → UI moderne\n"
    md += "   - Figma AI → Design\n"
    md += "   - Oppure semplicemente consegnalo a uno sviluppatore\n"
    md += "5. **Itera** sulla UI usando le interazioni descritte nel file\n\n"
    md += "---\n\n"
    
    # Flussi principali
    md += "## 🔄 Flussi Principali\n\n"
    
    # Identifica il flusso principale (catena dagli stati non transitori)
    md += "### Flusso di Autenticazione\n\n"
    auth_flow = []
    for state_name in ["app_idle", "iniziale", "caricamento", "successo", "errore", "sessione_scaduta"]:
        if state_name in states:
            auth_flow.append(state_name)
    md += " → ".join([f"`{s}`" for s in auth_flow]) + "\n\n"
    
    md += "### Flusso di Caricamento Dati\n\n"
    load_flow = []
    for state_name in ["iniziale", "caricamento", "successo", "vuoto", "errore"]:
        if state_name in states:
            load_flow.append(state_name)
    md += " → ".join([f"`{s}`" for s in load_flow]) + "\n\n"
    
    return md


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Genera specifiche UI dalla macchina a stati")
    parser.add_argument("--machine", default="output/spec/spec_machine.json", help="Percorso spec_machine.json")
    parser.add_argument("--context", default="output/context/project_context.md", help="Percorso project_context.md")
    parser.add_argument("--output-dir", default="output/ui_specs", help="Directory di output")
    args = parser.parse_args()
    
    # Carica input
    print(f"📦 Caricamento macchina a stati: {args.machine}")
    machine = load_machine(args.machine)
    
    print(f"📖 Caricamento contesto: {args.context}")
    context = load_context(args.context)
    
    states = machine.get("states", {})
    print(f"🔍 Trovati {len(states)} stati nella macchina")
    
    # Crea directory output
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Genera UI spec per ogni stato
    generated = 0
    for state_name, state_def in states.items():
        is_transient = state_name in TRANSIENT_STATES
        prefix = "⏳" if is_transient else "🖥️"
        
        print(f"  {prefix} Generando UI spec per '{state_name}'...")
        
        md_content = generate_ui_spec(state_name, state_def, machine, context)
        output_path = os.path.join(args.output_dir, f"UI_{state_name}.md")
        
        with open(output_path, "w") as f:
            f.write(md_content)
        
        generated += 1
        print(f"    ✅ Scritto: {output_path}")
    
    # Genera indice
    print(f"\n📋 Generando indice...")
    index_content = generate_index(states, machine, args.output_dir)
    index_path = os.path.join(args.output_dir, "README.md")
    
    with open(index_path, "w") as f:
        f.write(index_content)
    
    print(f"  ✅ Scritto: {index_path}")
    
    print(f"\n🎉 Completato! {generated} UI specs generate in {args.output_dir}/")
    print(f"   Apri {index_path} per navigare tra tutte le specifiche.")


if __name__ == "__main__":
    main()