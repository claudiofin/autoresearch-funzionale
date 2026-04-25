"""
LLM Wiki Generator - Crea la Memory Bank per gli Agenti AI.

Genera 4 file fondamentali dentro output/llm_wiki/:
- @TECH_RULES.md       (Regole tecniche assolute, stack, divieti)
- @DOMAIN_GLOSSARY.md  (Vocabolario del dominio aziendale)
- project_index.md     (Indice navigabile di tutti i file)
- active_context.md    (Log di sviluppo, aggiornato dall'agente)

Approccio ibrido: se i file esistono, vengono saltati (preservano la memoria).
Con --force, vengono rigenerati tutti da zero.
"""

import os
import glob
from pathlib import Path


# ---------------------------------------------------------------------------
# Prompts LLM
# ---------------------------------------------------------------------------

PROMPT_TECH_RULES = """Sei un Lead Software Architect. Ho questo contesto di progetto.
Devo istruire un team di Agenti AI (Junior/Mid Developers) a scrivere il codice.

Crea un file di regole rigide contenente:
1. **Tech Stack** (framework, librerie, strumenti)
2. **REGOLE ASSOLUTE** (cosa NON fare - gli LLM capiscono bene i divieti)
3. **Standard di Codice** (convenzioni, pattern obbligatori)
4. **Struttura Cartelle** (dove salvare i file)

Sii telegrafico. Usa elenchi puntati. Non scrivere paragrafi discorsivi.

## Contesto del Progetto:
{context}
"""

PROMPT_DOMAIN_GLOSSARY = """Sei un Technical Writer esperto in Domain-Driven Design.
Devo creare un glossario che mappi i termini del dominio aziendale ai nomi delle variabili/funzioni nel codice.

Analizza il contesto e crea una tabella Markdown con:
- **Termine Aziendale** (es. "Clinic", "Smart Group")
- **Nome nel Codice** (es. `ClinicProfile`, `PurchaseGroup`)
- **Descrizione** (1 riga)

Sii coerente con la nomenclatura già usata nel progetto.

## Contesto del Progetto:
{context}
"""

PROMPT_PROJECT_INDEX = """Sei un Librarian. Crea un indice Markdown (Table of Contents) 
di tutti i file di documentazione generati per questo progetto.

Organizza l'indice per categorie:
- 📋 Specifiche Funzionali
- 🎨 Design System & UI
- 🏗️ Architettura Backend
- 🔄 Macchine a Stati (XState)
- 📊 Report & Analisi

Per ogni file, scrivi:
- Link al file
- 1 riga di descrizione
- Quando è stato generato (se visibile)

## Contesto del Progetto:
{context}
"""

SYSTEM_PROMPT = "Sei un AI Technical Architect. Rispondi solo con il contenuto Markdown richiesto, senza testo aggiuntivo."


# ---------------------------------------------------------------------------
# Core Functions
# ---------------------------------------------------------------------------

def _load_context(context_path: str) -> str:
    """Carica e unisce i file di contesto."""
    parts = []
    
    # Carica project_context.md
    if os.path.exists(context_path):
        with open(context_path, "r", encoding="utf-8") as f:
            parts.append(f.read())
    
    # Carica spec.md se esiste
    spec_path = context_path.replace("/context/project_context.md", "/spec/spec.md")
    if os.path.exists(spec_path):
        with open(spec_path, "r", encoding="utf-8") as f:
            parts.append(f"\n\n{'='*60}\nSPECIFICHE:\n{'='*60}\n\n" + f.read())
    
    # Carica DESIGN.md se esiste
    design_path = context_path.replace("/context/project_context.md", "/ui_specs/DESIGN.md")
    if os.path.exists(design_path):
        with open(design_path, "r", encoding="utf-8") as f:
            parts.append(f"\n\n{'='*60}\nDESIGN SYSTEM:\n{'='*60}\n\n" + f.read())
    
    return "\n\n".join(parts)


def _call_llm_for_wiki(prompt: str) -> str:
    """
    Chiama l'LLM usando lo stesso client degli altri pipeline.
    Importa dinamicamente per evitare dipendenze circolari.
    """
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    
    from pipeline.kanban_task.llm_client import call_llm, LLMConfig
    
    config = LLMConfig()
    return call_llm(prompt, SYSTEM_PROMPT, max_tokens=4096, config=config)


def generate_tech_rules(context: str, output_dir: str, force: bool = False) -> str:
    """Genera @TECH_RULES.md con le regole tecniche del progetto."""
    output_path = os.path.join(output_dir, "@TECH_RULES.md")
    
    if os.path.exists(output_path) and not force:
        print(f"  ⏭️  @TECH_RULES.md già esiste, salto (usa --force per rigenerare)")
        return output_path
    
    print("  🧠 Generazione @TECH_RULES.md...")
    prompt = PROMPT_TECH_RULES.format(context=context[:6000])
    content = _call_llm_for_wiki(prompt)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# 🛠️ Tech Rules & Constraints\n\n"
                f"> Generato automaticamente dalla pipeline LLM Wiki.\n"
                f"> Questo file contiene le regole tecniche assolute del progetto.\n\n"
                f"{content}\n")
    
    print(f"  ✅ @TECH_RULES.md generato ({len(content)} chars)")
    return output_path


def generate_domain_glossary(context: str, output_dir: str, force: bool = False) -> str:
    """Genera @DOMAIN_GLOSSARY.md con il vocabolario del dominio."""
    output_path = os.path.join(output_dir, "@DOMAIN_GLOSSARY.md")
    
    if os.path.exists(output_path) and not force:
        print(f"  ⏭️  @DOMAIN_GLOSSARY.md già esiste, salto (usa --force per rigenerare)")
        return output_path
    
    print("  📖 Generazione @DOMAIN_GLOSSARY.md...")
    prompt = PROMPT_DOMAIN_GLOSSARY.format(context=context[:6000])
    content = _call_llm_for_wiki(prompt)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# 📖 Domain Glossary\n\n"
                f"> Mappa i termini del dominio aziendale ai nomi nel codice.\n"
                f"> Generato automaticamente dalla pipeline LLM Wiki.\n\n"
                f"{content}\n")
    
    print(f"  ✅ @DOMAIN_GLOSSARY.md generato ({len(content)} chars)")
    return output_path


def generate_project_index(context: str, output_dir: str, base_output_dir: str = "output") -> str:
    """Genera project_index.md con l'indice di tutti i file."""
    output_path = os.path.join(output_dir, "project_index.md")
    
    print("  🗺️  Generazione project_index.md...")
    
    # Scansiona tutti i file .md in output/
    md_files = glob.glob(f"{base_output_dir}/**/*.md", recursive=True)
    md_files = [f for f in md_files if "llm_wiki" not in f and "kanban_tasks" not in f]
    md_files.sort()
    
    # Crea la lista file
    file_list = "\n".join([f"- `{f}`" for f in md_files])
    
    # Prompt con lista effettiva dei file
    prompt = PROMPT_PROJECT_INDEX.format(context=context[:4000])
    prompt += f"\n\n## File Disponibili:\n{file_list}"
    
    content = _call_llm_for_wiki(prompt)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# 📂 Project Index\n\n"
                f"> Indice completo di tutti i file di documentazione.\n"
                f"> Generato automaticamente dalla pipeline LLM Wiki.\n\n"
                f"{content}\n")
    
    print(f"  ✅ project_index.md generato ({len(content)} chars, {len(md_files)} file)")
    return output_path


def generate_active_context(output_dir: str, force: bool = False) -> str:
    """Genera active_context.md con template precompilato."""
    output_path = os.path.join(output_dir, "active_context.md")
    
    if os.path.exists(output_path) and not force:
        print(f"  ⏭️  active_context.md già esiste, salto (usa --force per rigenerare)")
        return output_path
    
    print("  🔄 Creazione active_context.md (template)...")
    
    template = """# 🔄 Active Context (Log di Sviluppo)

> Questo file viene aggiornato dall'Agente AI (Cline/Claude) alla fine di ogni task.
> Tiene traccia dello stato attuale, dei problemi aperti e dei prossimi passi.

---

## 📌 Fase Attuale

**Sprint corrente:** Da definire
**Task in corso:** Nessuno
**Stato:** 🟡 In attesa di inizio sviluppo

---

## ✅ Task Completati (Ultime 24h)

_Nessun task completato ancora._

---

## 🚧 Bloccanti / Problemi Aperti

_Nessun bloccante al momento._

---

## ➡️ Prossimi Passi

1. Iniziare lo Sprint 1 (Fondamenta)
2. Completare TASK-01 (Inizializzazione Repo)
3. Completare TASK-02 (Configurazione Design Tokens)

---

## 📝 Note

_Spazio per note aggiuntive dell'agente o dell'utente._
"""
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(template)
    
    print(f"  ✅ active_context.md creato (template)")
    return output_path


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def generate_wiki(context_path: str = "output/context/project_context.md",
                  output_dir: str = "output/llm_wiki",
                  base_output_dir: str = "output",
                  force: bool = False) -> dict:
    """
    Genera tutti i file della LLM Wiki.
    
    Returns:
        dict con i path dei file generati
    """
    os.makedirs(output_dir, exist_ok=True)
    
    print("\n" + "=" * 60)
    print("🧠 LLM WIKI GENERATOR")
    print("=" * 60)
    print()
    
    # Carica il contesto
    print(f"📄 Caricamento contesto da {context_path}...")
    context = _load_context(context_path)
    print(f"  ✅ Contesto caricato ({len(context)} chars)")
    
    # Genera i 4 file
    results = {}
    results["tech_rules"] = generate_tech_rules(context, output_dir, force)
    results["domain_glossary"] = generate_domain_glossary(context, output_dir, force)
    results["project_index"] = generate_project_index(context, output_dir, base_output_dir)
    results["active_context"] = generate_active_context(output_dir, force)
    
    print()
    print("=" * 60)
    print("✅ LLM Wiki generata con successo!")
    print(f"📁 Cartella: {output_dir}/")
    print("=" * 60)
    print()
    print("File generati:")
    for key, path in results.items():
        print(f"  • {os.path.basename(path)}: {path}")
    
    return results