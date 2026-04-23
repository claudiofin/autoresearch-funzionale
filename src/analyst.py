"""
Analyst LLM per analisi funzionale automatica.

Legge il contesto e genera suggerimenti strutturati per espandere la specifica
funzionale con stati, transizioni ed edge case.

LLM È OBBLIGATORIO - nessun fallback simulato.

Output: JSON validato.

Usage:
    python run.py analyst --context output/project_context.md --output output/analyst_suggestions.json
    
Environment Variables:
    LLM_API_KEY: La tua chiave API (OBBLIGATORIA)
    LLM_PROVIDER: Provider (openai, anthropic, google, dashscope)
    LLM_BASE_URL: URL base dell'API (opzionale, override)
    LLM_MODEL: Modello da usare (opzionale, override)
"""

import os
import sys
import json
import argparse
from datetime import datetime

import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import LLM_CONFIG, DEFAULT_PROVIDER


# ---------------------------------------------------------------------------
# LLM Client
# ---------------------------------------------------------------------------

def get_llm_client():
    """Configura il client LLM."""
    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key:
        print("❌ ERRORE: LLM_API_KEY non è settato.")
        sys.exit(1)
    
    provider = os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER)
    
    if provider in LLM_CONFIG:
        base_url = os.getenv("LLM_BASE_URL", LLM_CONFIG[provider]["base_url"])
        model = os.getenv("LLM_MODEL", LLM_CONFIG[provider]["model"])
    else:
        base_url = os.getenv("LLM_BASE_URL")
        model = os.getenv("LLM_MODEL")
        if not base_url or not model:
            print(f"❌ ERRORE: Provider '{provider}' non riconosciuto.")
            sys.exit(1)
    
    try:
        from openai import OpenAI
        return OpenAI(api_key=api_key, base_url=base_url), model
    except ImportError:
        print("❌ ERRORE: openai non installato.")
        sys.exit(1)


def call_llm(context_text: str, max_retries: int = 3) -> dict:
    """Chiama l'LLM per analizzare il contesto e generare suggerimenti."""
    client, model = get_llm_client()
    
    # Tronca contesto per evitare risposte troncate
    max_context = 8000  # caratteri
    if len(context_text) > max_context:
        # Mantieni le sezioni più importanti
        lines = context_text.split("\n")
        important_lines = []
        for line in lines:
            if line.startswith("##") or line.startswith("###") or line.startswith("-") or line.startswith("|"):
                important_lines.append(line)
        context_text = "\n".join(important_lines[:200])  # max 200 linee importanti
        if len(context_text) > max_context:
            context_text = context_text[:max_context]
    
    prompt = f"""Analizza questo contesto di progetto e genera una specifica funzionale.

Contesto:
{context_text}

Rispondi SOLO con JSON valido (nessun markdown, nessun codice extra):

{{
  "patterns_detected": ["pattern1", "pattern2"],
  "states": [
    {{"name": "state_name", "description": "desc", "entry": [], "exit": []}}
  ],
  "transitions": [
    {{"from": "state1", "to": "state2", "event": "EVENT_NAME", "guard": null}}
  ],
  "edge_cases": [
    {{"id": "EC001", "scenario": "desc", "trigger": "cause", "expected": "behavior", "priority": "high"}}
  ],
  "events": [
    {{"name": "EVENT_NAME", "description": "desc", "payload": {{}}}}
  ],
  "ux_questions": ["question1"],
  "confidence": 0.8
}}

Regole:
1. JSON valido al 100% - nessun testo fuori dal JSON
2. Nomi stati in snake_case minuscolo
3. Eventi in MAIUSCOLO_CON_UNDERSCORE
4. Includi almeno: stati di loading, errore, successo, vuoto
5. Includi transizioni per: navigazione avanti/indietro, errore, annullamento
6. Edge case: timeout, errore rete, sessione scaduta, input invalido
"""
    
    print(f"  🤖 Chiamata LLM ({model}), contesto: {len(context_text)} chars...")
    
    for attempt in range(max_retries):
        try:
            print(f"  Tentativo {attempt + 1}/{max_retries}...")
            response = client.chat.completions.create(
                timeout=180,
                model=model,
                messages=[
                    {"role": "system", "content": "Sei un Senior Product Manager. Rispondi SOLO con JSON valido. Inizia con { e termina con }. Nessun markdown, nessun testo extra."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=4096,
            )
            
            content = response.choices[0].message.content.strip()
            
            # Estrai JSON da eventuali markdown
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            # Trova primo { e ultima }
            start = content.find("{")
            end = content.rfind("}")
            if start >= 0 and end > start:
                content = content[start:end+1]
            
            data = json.loads(content)
            print(f"  ✅ LLM ha restituito {len(json.dumps(data))} chars di JSON valido")
            return data
            
        except json.JSONDecodeError as e:
            print(f"  Tentativo {attempt + 1} fallito (JSON invalido): {e}")
            # Prova a estrarre manualmente
            try:
                start = content.find("{")
                end = content.rfind("}")
                if start >= 0 and end > start:
                    partial = content[start:end+1]
                    data = json.loads(partial)
                    print(f"  ✅ JSON estratto manualmente: {len(partial)} chars")
                    return data
            except:
                pass
            continue
        except Exception as e:
            print(f"  Tentativo {attempt + 1} fallito: {e}")
            continue
    
    print("❌ ERRORE: Tutti i tentativi LLM falliti.")
    print("   Il sistema non può funzionare senza LLM.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Analyst LLM per analisi funzionale")
    parser.add_argument("--context", type=str, default="output/project_context.md",
                        help="Context file")
    parser.add_argument("--output", type=str, default="output/analyst/analyst_suggestions.json",
                        help="Output JSON file")
    args = parser.parse_args()
    
    print("=" * 50)
    print("ANALYST - Analisi Funzionale Automatica")
    print("=" * 50)
    print(f"Contesto: {args.context}")
    print(f"Output: {args.output}")
    print()
    
    # Read context
    with open(args.context, "r", encoding="utf-8") as f:
        context_text = f.read()
    
    print(f"Contesto caricato: {len(context_text)} caratteri")
    print("  🚀 Esecuzione con LLM...")
    
    # Call LLM
    result = call_llm(context_text)
    
    # Write output
    os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Output scritto: {args.output}")
    print(f"  Patterns: {len(result.get('patterns_detected', []))}")
    print(f"  States: {len(result.get('states', []))}")
    print(f"  Transitions: {len(result.get('transitions', []))}")
    print(f"  Edge cases: {len(result.get('edge_cases', []))}")
    print(f"  Events: {len(result.get('events', []))}")


if __name__ == "__main__":
    main()