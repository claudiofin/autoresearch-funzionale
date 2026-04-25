"""
Core logic for Kanban Task Generator.

Functions:
- gather_all_markdown_context: Scans output/ and collects all .md files
- generate_kanban_plan_llm: Calls LLM to create initial epic/sprint/task plan
- refine_plan_loop: Iteratively refines the plan (dependencies, parallelization)
- generate_task_markdown: Formats a single task as an agent-friendly Markdown file
- generate_master_plan: Creates the MASTER_PLAN.md roadmap
"""

import json
import os
import glob
import re
import time
from pathlib import Path

from pipeline.kanban_task.llm_client import call_llm, LLMConfig


# ---------------------------------------------------------------------------
# Context Gathering
# ---------------------------------------------------------------------------

def gather_all_markdown_context(base_dir: str) -> str:
    """
    Esplora base_dir ricorsivamente e unisce il contenuto di tutti i file .md trovati.
    Salta automaticamente la cartella kanban_tasks per evitare di leggere task vecchi.
    """
    combined_context = ""
    md_files = glob.glob(f"{base_dir}/**/*.md", recursive=True)
    
    # Ordina i file per priorità logica
    priority_order = [
        "project_context.md",
        "spec.md",
        "spec_machine.json",  # anche se non è .md, potrebbe essere utile
        "DESIGN.md",
        "backend_spec.md",
        "ci_cd_spec.md",
    ]
    
    # Filtra e ordina
    filtered_files = []
    for file_path in md_files:
        # Salta kanban_tasks per evitare di leggere task vecchi
        if "kanban_tasks" in file_path:
            continue
        # Salta file che non sono .md
        if not file_path.endswith(".md"):
            continue
        filtered_files.append(file_path)
    
    # Ordina per priorità
    def priority_key(filepath: str) -> int:
        filename = os.path.basename(filepath)
        for i, priority in enumerate(priority_order):
            if filename == priority:
                return i
        return len(priority_order)  # file non prioritari alla fine
    
    filtered_files.sort(key=priority_key)
    
    print(f"📚 Found {len(filtered_files)} Markdown context files. Assembling...")
    
    for file_path in filtered_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                combined_context += f"\n\n{'='*60}\n"
                combined_context += f"FILE: {file_path}\n"
                combined_context += f"{'='*60}\n\n"
                # Tronca i file giganteschi per non sforare il limite di token
                max_chars = 5000
                combined_context += content[:max_chars] + (
                    "\n...[TRUNCATED]..." if len(content) > max_chars else ""
                )
        except Exception as e:
            print(f"  ⚠️ Cannot read {file_path}: {e}")
    
    return combined_context


# ---------------------------------------------------------------------------
# LLM Plan Generation
# ---------------------------------------------------------------------------

def generate_kanban_plan_llm(context: str, config: LLMConfig) -> dict:
    """
    Usa il LLM per creare il piano iniziale delle Epiche, Sprint e Task in JSON.
    """
    prompt = f"""Sei un Technical Project Manager esperto in Agentic Software Engineering e Scrum.
Devi analizzare tutta la documentazione tecnica del progetto e pianificare lo sviluppo per un team di Agenti AI autonomi (come Cline o Claude).

## Regole d'oro per il Piano Kanban:
1. **Scomposizione in Sprint:** Dividi il lavoro in Sprint logici (Sprint 1: Fondamenta, Sprint 2: Core Features, Sprint 3: Advanced, ecc.)
2. **Dipendenze Bloccanti:** Identifica quali task DEVONO essere fatti prima di altri.
3. **Parallelizzazione (Multi-Agente):** Specifica quali task dentro lo stesso Sprint possono essere assegnati contemporaneamente a più agenti AI senza creare conflitti.
4. **Scope iper-limitato:** Un task non deve superare i 10-15 minuti di elaborazione AI. Se un task è troppo grande, scomponilo.
5. **Contesto esplicito:** Ogni task deve indicare quali file leggere prima di iniziare.

## Documentazione del Progetto:
{context}

## Istruzioni:
Scomponi il progetto in Sprint e Task. Rispondi ESCLUSIVAMENTE con un JSON formattato così:

```json
{{
  "project_name": "Nome del Progetto",
  "sprints": [
    {{
      "sprint_number": 1,
      "id": "Setup_Architettura",
      "sprint_goal": "Setup Iniziale e Architettura Base",
      "tasks": [
        {{
          "id": "TASK-01",
          "title": "Inizializzazione_Repo_e_Dipendenze",
          "description": "Crea il progetto React, installa Tailwind, Zustand e XState. Configura il linter e il formatter.",
          "files_to_read": ["output/context/project_context.md"],
          "acceptance_criteria": [
            "Progetto React creato e compila senza errori",
            "Tailwind CSS configurato",
            "Linter e formatter attivi"
          ],
          "dependencies": [],
          "can_be_parallelized": false,
          "parallel_group": null
        }},
        {{
          "id": "TASK-02",
          "title": "Implementazione_Design_System",
          "description": "Applica i token di DESIGN.md alla configurazione di Tailwind (colori, font, spacing, shadows).",
          "files_to_read": ["output/ui_specs/DESIGN.md"],
          "acceptance_criteria": [
            "Colori del design system disponibili come classi Tailwind",
            "Font e tipografia configurati",
            "Componenti base usano i token corretti"
          ],
          "dependencies": ["TASK-01"],
          "can_be_parallelized": false,
          "parallel_group": null
        }}
      ]
    }},
    {{
      "sprint_number": 2,
      "id": "Frontend_Core",
      "sprint_goal": "Sviluppo Schermate Core e Componenti UI",
      "tasks": [
        {{
          "id": "TASK-03",
          "title": "Componenti_Base_Bottoni_Card_Input",
          "description": "Crea i componenti UI base: Button, Card, Input, usando i token del Design System.",
          "files_to_read": ["output/ui_specs/DESIGN.md", "output/ui_specs/states/UI_*.md"],
          "acceptance_criteria": [
            "Componenti Button, Card, Input creati",
            "Usano i colori e font del Design System",
            "Responsive e accessibili"
          ],
          "dependencies": ["TASK-02"],
          "can_be_parallelized": true,
          "parallel_group": "A"
        }},
        {{
          "id": "TASK-04",
          "title": "Schermata_Login",
          "description": "Implementa la schermata di Login secondo le specifiche UI.",
          "files_to_read": ["output/ui_specs/screens/Login.md", "output/ui_specs/DESIGN.md"],
          "acceptance_criteria": [
            "Form di login funzionante",
            "Validazione campi",
            "Stile coerente con Design System"
          ],
          "dependencies": ["TASK-02"],
          "can_be_parallelized": true,
          "parallel_group": "A"
        }}
      ]
    }}
  ]
}}
```

**Importante:**
- Rispondi SOLO con il JSON, senza testo prima o dopo.
- I `dependencies` devono essere array di task ID (es. ["TASK-01", "TASK-02"]).
- `can_be_parallelized: true` significa che il task può essere eseguito da un agente mentre altri lavorano su altri task dello stesso sprint.
- `parallel_group` è un identificatore (es. "A", "B") per gruppi di task che possono essere paralleli.
- Se un task non ha dipendenze, usa `dependencies: []`.
"""
    
    system_prompt = "Sei un AI Technical Project Manager. Rispondi solo con JSON valido. Non aggiungere testo fuori dal JSON."
    
    response = call_llm(prompt, system_prompt, max_tokens=8192, config=config)
    
    # Estrazione pulita del JSON
    json_match = re.search(r'\{.*\}', response, re.DOTALL)
    if json_match:
        try:
            plan = json.loads(json_match.group())
            # Validazione base
            if "sprints" not in plan:
                raise ValueError("Il JSON non contiene il campo 'sprints'")
            return plan
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON non valido: {e}")
    raise ValueError("Il LLM non ha restituito un JSON valido per il piano Kanban.")


# ---------------------------------------------------------------------------
# Plan Refinement Loop
# ---------------------------------------------------------------------------

def refine_plan_loop(plan: dict, context: str, num_steps: int, config: LLMConfig) -> dict:
    """
    Iterativamente raffina il piano per migliorare:
    - Step 1 (decomposizione): già fatto in generate_kanban_plan_llm
    - Step 2 (dipendenze): analizza e corregge le dipendenze tra task
    - Step 3+ (ottimizzazione): ottimizza parallelizzazione e sprint allocation
    """
    current_plan = plan
    
    for step in range(1, num_steps):
        print(f"  🔄 Refinement step {step + 1}/{num_steps}...")
        
        if step == 1:
            # Analisi delle dipendenze
            current_plan = _refine_dependencies(current_plan, context, config)
        else:
            # Ottimizzazione sprint e parallelizzazione
            current_plan = _refine_optimization(current_plan, context, config)
        
        time.sleep(1)  # Rate limiting
    
    return current_plan


def _refine_dependencies(plan: dict, context: str, config: LLMConfig) -> dict:
    """
    Raffina le dipendenze tra task. Assicura che:
    - Nessun task dipenda da un task futuro
    - Le dipendenze transitiva siano risolte
    - Non ci siano cicli
    """
    plan_json = json.dumps(plan, indent=2, ensure_ascii=False)
    
    prompt = f"""Sei un AI Project Manager. Analizza il piano attuale e correggi le dipendenze tra i task.

## Piano Attuale:
```json
{plan_json}
```

## Regole di Validazione:
1. Un task può dipendere SOLO da task nello stesso sprint o in sprint precedenti
2. Non devono esserci dipendenze cicliche
3. Se un task dipende da TASK-01 e TASK-01 dipende da TASK-02, allora TASK-02 deve essere prima
4. Rimuovi dipendenze ridondanti (se A→B e B→C, non serve A→C)

## Istruzioni:
Rispondi con il JSON del piano aggiornato, con le dipendenze corrette.
Mantieni la stessa struttura JSON originale.

```json
{{
  "project_name": "...",
  "sprints": [...]
}}
```

Rispondi SOLO con il JSON, senza testo aggiuntivo.
"""
    
    system_prompt = "Sei un AI che valida dipendenze di task. Rispondi solo con JSON valido."
    
    try:
        response = call_llm(prompt, system_prompt, max_tokens=8192, config=config)
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except Exception as e:
        print(f"  ⚠️ Dependency refinement failed: {e}. Using current plan.")
    
    return plan


def _refine_optimization(plan: dict, context: str, config: LLMConfig) -> dict:
    """
    Ottimizza la suddivisione in sprint e la parallelizzazione.
    """
    plan_json = json.dumps(plan, indent=2, ensure_ascii=False)
    
    prompt = f"""Sei un AI Project Manager esperto in ottimizzazione di sprint.
Analizza il piano e ottimizza:
1. La suddivisione dei task negli sprint (bilancia il carico)
2. La parallelizzazione (massimizza i task paralleli per ridurre il tempo)
3. Il percorso critico (identifica i task bloccanti)

## Piano Attuale:
```json
{plan_json}
```

## Istruzioni:
Rispondi con il JSON del piano ottimizzato. Mantieni la stessa struttura.
Puoi:
- Spostare task tra sprint per bilanciare
- Cambiare can_be_parallelized e parallel_group
- Aggiungere o rimuovere task se necessario

Rispondi SOLO con il JSON, senza testo aggiuntivo.
```json
{{
  "project_name": "...",
  "sprints": [...]
}}
```
"""
    
    system_prompt = "Sei un AI che ottimizza piani di sprint. Rispondi solo con JSON valido."
    
    try:
        response = call_llm(prompt, system_prompt, max_tokens=8192, config=config)
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except Exception as e:
        print(f"  ⚠️ Optimization refinement failed: {e}. Using current plan.")
    
    return plan


# ---------------------------------------------------------------------------
# Task Markdown Generation
# ---------------------------------------------------------------------------

def generate_task_markdown(task: dict, sprint_number: int, sprint_goal: str) -> str:
    """
    Formatta un singolo ticket in un file Markdown perfetto per l'agente AI.
    """
    files_to_read = task.get("files_to_read", [])
    acceptance_criteria = task.get("acceptance_criteria", [])
    dependencies = task.get("dependencies", [])
    can_parallelize = task.get("can_be_parallelized", False)
    parallel_group = task.get("parallel_group")
    
    # Files to read
    files_str = "\n".join([f"- `{f}`" for f in files_to_read]) if files_to_read else "- Nessuno specifico"
    
    # Acceptance criteria
    ac_str = "\n".join([f"- [ ] {ac}" for ac in acceptance_criteria]) if acceptance_criteria else "- [ ] Verificare che il task sia completato"
    
    # Dependencies
    if dependencies:
        deps_str = "⚠️ **BLOCCATO DA:** Devi verificare che questi task siano completati prima di iniziare:\n"
        deps_str += "\n".join([f"- `{d}`" for d in dependencies])
    else:
        deps_str = "🟢 **PRONTO PER INIZIARE:** Nessuna dipendenza bloccante."
    
    # Parallelization
    parallel_str = ""
    if can_parallelize and parallel_group:
        parallel_str = f"🚀 **PARALLELIZZABILE:** Questo task fa parte del gruppo **[{parallel_group}]**. Può essere assegnato a un agente mentre altri lavorano su altri task dello stesso gruppo."
    elif can_parallelize:
        parallel_str = "🚀 **PARALLELIZZABILE:** Questo task può essere eseguito in parallelo con altri task dello stesso sprint."
    else:
        parallel_str = "🧱 **SEQUENZIALE:** Questo task deve essere eseguito in sequenza (dipendenze bloccanti)."
    
    return f"""# {task['id']}: {task['title']}

**Sprint:** {sprint_number} — {sprint_goal}
**Status:** ⏳ To Do
**Priority:** {"🔴 Alta" if dependencies else "🟡 Media"}

---

## 🚦 Controlli Pre-Volo (Per l'Agente AI)

{deps_str}

{parallel_str}

---

## 🎯 Obiettivo del Task

{task.get('description', 'Nessuna descrizione disponibile.')}

---

## 📚 Contesto Necessario

Prima di scrivere codice o fare modifiche, assicurati di aver letto e compreso questi file:

{files_str}

---

## ✅ Criteri di Accettazione (Definition of Done)

Prima di chiudere questo task e considerarlo completato, verifica di aver soddisfatto tutti questi punti:

{ac_str}

---

## 📝 Note per l'Agente

- Lavora a piccoli step. Fai commit frequenti con messaggi chiari (es. `feat({task['id']}): ...`).
- Fermati e chiedi conferma all'utente se incontri ambiguità nei requisiti.
- Se un file di contesto non esiste, procedi con le migliori pratiche e segnala il problema.
- Dopo aver completato tutti i criteri di accettazione, aggiorna lo Status in `✅ Done`.
"""


# ---------------------------------------------------------------------------
# Master Plan Generation
# ---------------------------------------------------------------------------

def generate_master_plan(plan: dict, output_dir: str) -> str:
    """
    Crea un file MASTER_PLAN.md con la roadmap completa e le dipendenze degli sprint.
    """
    project_name = plan.get("project_name", "Progetto")
    
    md = f"""# 🗺️ Master Plan: {project_name}

> Generato automaticamente dalla pipeline Kanban Task Generator.
> Questo file è la fonte di verità per il piano di sviluppo.

---

"""
    
    total_tasks = 0
    for sprint in plan.get("sprints", []):
        sprint_num = sprint.get("sprint_number", "?")
        sprint_id = sprint.get("id", f"Sprint {sprint_num}")
        sprint_goal = sprint.get("sprint_goal", "")
        tasks = sprint.get("tasks", [])
        
        md += f"## Sprint {sprint_num}: {sprint_goal}\n\n"
        md += f"**Obiettivo:** {sprint_goal}\n"
        md += f"**Task count:** {len(tasks)}\n\n"
        
        for task in tasks:
            task_id = task.get("id", "?")
            task_title = task.get("title", "Senza titolo")
            dependencies = task.get("dependencies", [])
            can_parallelize = task.get("can_be_parallelized", False)
            parallel_group = task.get("parallel_group", "")
            
            # Dependency info
            if dependencies:
                deps_str = f"*(Dipende da: {', '.join(dependencies)})*"
            else:
                deps_str = "*(Inizio Libero)*"
            
            # Parallelization info
            if can_parallelize and parallel_group:
                parallel_str = f"⚡ Parallelizzabile [gruppo {parallel_group}]"
            elif can_parallelize:
                parallel_str = "⚡ Parallelizzabile"
            else:
                parallel_str = "🧱 Sequenziale"
            
            md += f"- [ ] **{task_id}**: {task_title} {parallel_str} {deps_str}\n"
            total_tasks += 1
        
        md += "\n---\n\n"
    
    # Summary
    md += f"## 📊 Riepilogo\n\n"
    md += f"- **Sprint totali:** {len(plan.get('sprints', []))}\n"
    md += f"- **Task totali:** {total_tasks}\n"
    md += f"\n> 💡 **Come usare questo piano:**\n"
    md += f"> 1. Apri la cartella `kanban_tasks/` nel tuo IDE\n"
    md += f"> 2. Inizia dal TASK-01 (o dai task senza dipendenze)\n"
    md += f"> 3. Per i task parallelizzabili, apri più istanze di Cline/Claude\n"
    md += f"> 4. Ogni task è un file Markdown autonomo con tutto il contesto necessario\n"
    
    master_plan_path = os.path.join(output_dir, "MASTER_PLAN.md")
    with open(master_plan_path, "w", encoding="utf-8") as f:
        f.write(md)
    
    print(f"  🗺️ Master Plan generato: {master_plan_path}")
    return master_plan_path