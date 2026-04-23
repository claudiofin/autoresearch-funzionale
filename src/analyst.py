"""
Analyst LLM per analisi funzionale automatica.

Legge il contesto e genera suggerimenti strutturati per espandere la specifica
funzionale con stati, transizioni ed edge case.

LLM È OBBLIGATORIO - nessun fallback simulato.

Output: JSON validato con Pydantic, compatibile con XState.

Usage:
    python run.py analyst --context output/project_context.md
    
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
from typing import List, Dict, Optional
from datetime import datetime

from config import LLM_CONFIG, DEFAULT_PROVIDER

# Import Pydantic models
from pydantic import BaseModel, Field

# Import instructor per output strutturato
try:
    import instructor
    from openai import OpenAI
    HAS_INSTRUCTOR = True
except ImportError:
    HAS_INSTRUCTOR = False


# ---------------------------------------------------------------------------
# Pydantic Models for Structured Output
# ---------------------------------------------------------------------------

class SuggestedState(BaseModel):
    name: str = Field(..., description="Nome dello stato (es. 'payment_pending')")
    description: str = Field(..., description="Descrizione di cosa rappresenta questo stato")
    entry_actions: List[str] = Field(default_factory=list, description="Azioni eseguite all'ingresso")
    exit_actions: List[str] = Field(default_factory=list, description="Azioni eseguite all'uscita")
    parent_pattern: str = Field(..., description="Pattern di riferimento (es. 'checkout')")
    business_reason: str = Field(..., description="Motivo di business per cui questo stato è necessario")

class SuggestedTransition(BaseModel):
    from_state: str = Field(..., description="Stato di origine")
    to_state: str = Field(..., description="Stato di destinazione")
    event: str = Field(..., description="Evento che triggera la transizione")
    guard: Optional[str] = Field(None, description="Condizione opzionale per la transizione")
    actions: List[str] = Field(default_factory=list, description="Azioni eseguite durante la transizione")
    business_reason: str = Field(..., description="Motivo di business per questa transizione")

class SuggestedEdgeCase(BaseModel):
    id: str = Field(..., description="Identificativo univoco (es. 'EC001')")
    scenario: str = Field(..., description="Descrizione dello scenario")
    trigger: str = Field(..., description="Cosa causa questo edge case")
    analisi_del_problema: str = Field(..., description="Analisi del PERCHÉ questo problema si verifica")
    expected_behavior: str = Field(..., description="Comportamento atteso del sistema")
    priority: str = Field(..., description="Priorità: 'high', 'medium', 'low'")
    related_states: List[str] = Field(default_factory=list, description="Stati coinvolti")

class SuggestedEvent(BaseModel):
    name: str = Field(..., description="Nome dell'evento (es. 'PAYMENT_CONFIRMED')")
    description: str = Field(..., description="Descrizione dell'evento")
    payload: Dict[str, str] = Field(default_factory=dict, description="Dati trasportati dall'evento")

class AnalystOutput(BaseModel):
    patterns_detected: List[str] = Field(default_factory=list, description="Pattern identificati nel contesto")
    suggested_states: List[SuggestedState] = Field(default_factory=list, description="Nuovi stati suggeriti")
    suggested_transitions: List[SuggestedTransition] = Field(default_factory=list, description="Nuove transizioni suggerite")
    suggested_edge_cases: List[SuggestedEdgeCase] = Field(default_factory=list, description="Edge case identificati")
    suggested_events: List[SuggestedEvent] = Field(default_factory=list, description="Eventi suggeriti")
    ux_questions: List[str] = Field(default_factory=list, description="Domande UX da rispondere")
    confidence_score: float = Field(..., ge=0, le=1, description="Confidenza dell'analisi (0-1)")


# ---------------------------------------------------------------------------
# LLM Client
# ---------------------------------------------------------------------------

def get_llm_client():
    """Configura il client LLM con instructor per output strutturato."""
    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key:
        print("❌ ERRORE: LLM_API_KEY non è settato.")
        print("   Il sistema richiede un LLM per funzionare.")
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
            print(f"   Provider disponibili: {', '.join(LLM_CONFIG.keys())}")
            sys.exit(1)
    
    client = instructor.from_openai(
        OpenAI(api_key=api_key, base_url=base_url)
    )
    
    return client, model


# ---------------------------------------------------------------------------
# Prompt Builder
# ---------------------------------------------------------------------------

def build_analyst_prompt(context_text: str) -> str:
    """Costruisce il prompt per l'Analyst LLM - versione ottimizzata."""
    
    prompt = f"""Analizza il contesto e genera JSON con: states, transitions, edge_cases, flows, api_endpoints.

## Contesto
{context_text}

## Output JSON
{{
  "states": [{{"name": "snake_case", "description": "...", "entry_actions": [], "exit_actions": [], "parent_pattern": "...", "business_reason": "..."}}],
  "transitions": [{{"from_state": "...", "to_state": "...", "event": "UPPER_CASE", "guard": null, "actions": [], "business_reason": "..."}}],
  "edge_cases": [{{"id": "EC001", "scenario": "...", "trigger": "...", "analisi_del_problema": "...", "expected_behavior": "...", "priority": "high|medium|low", "related_states": []}}],
  "flows": [{{"name": "...", "steps": [{{"trigger": "...", "action": "...", "expected_outcome": "...", "error_scenario": "..."}}]}}],
  "api_endpoints": [{{"method": "GET|POST|PUT|DELETE", "path": "...", "description": "...", "request_schema": {{}}, "response_schema": {{}}, "error_codes": []}}]
}}

## Regole
1. snake_case per stati, UPPER_CASE per eventi
2. OGNI stato API deve avere transizioni ERROR, TIMEOUT, CANCEL
3. OGNI edge_case deve avere transizione corrispondente
4. NO placeholder generici - descrivi comportamento esatto
5. Pattern paralleli restano separati, non concatenati
6. Copri: auth, core flow, error handling, empty states, notifications

Rispondi SOLO con JSON valido, niente markdown.
"""
    
    return prompt


# ---------------------------------------------------------------------------
# LLM Call (REALE - nessun fallback)
# ---------------------------------------------------------------------------

def call_llm_analyst(prompt: str, max_retries: int = 3) -> dict:
    """
    Chiama l'LLM per l'analisi. LLM È OBBLIGATORIO - nessun fallback.
    
    Args:
        prompt: Prompt completo per l'LLM
        max_retries: Numero massimo di tentativi
        
    Returns:
        Dizionario con l'analisi strutturata
        
    Raises:
        RuntimeError: Se l'LLM non è disponibile o tutti i tentativi falliscono
    """
    if not HAS_INSTRUCTOR:
        raise RuntimeError("instructor o openai non installati. Il sistema richiede un LLM per funzionare.")
    
    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key:
        print("❌ ERRORE: LLM_API_KEY non è settato.")
        print("   Il sistema richiede un LLM per funzionare.")
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
            print(f"   Provider disponibili: {', '.join(LLM_CONFIG.keys())}")
            sys.exit(1)
    
    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=base_url)
    
    print(f"  🤖 Chiamata LLM in corso ({model})...")
    print(f"  ⏱️  Timeout: 180s, Max tokens: 2048")
    
    last_error = None
    for attempt in range(max_retries):
        try:
            print(f"  Tentativo {attempt + 1}/{max_retries}...")
            response = client.chat.completions.create(
                timeout=180,
                model=model,
                messages=[
                    {"role": "system", "content": "Rispondi SOLO con JSON valido. Niente markdown, niente codice. Solo JSON puro."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=2048,
                frequency_penalty=0.3,
                presence_penalty=0.2
            )
            
            content = response.choices[0].message.content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            data = json.loads(content)
            output = AnalystOutput(**data)
            
            # Converte da Pydantic a dict
            return {
                "patterns_detected": output.patterns_detected,
                "suggested_states": [
                    {
                        "name": s.name,
                        "description": s.description,
                        "entry_actions": s.entry_actions,
                        "exit_actions": s.exit_actions,
                        "parent_pattern": s.parent_pattern,
                        "business_reason": s.business_reason
                    }
                    for s in output.suggested_states
                ],
                "suggested_transitions": [
                    {
                        "from_state": t.from_state,
                        "to_state": t.to_state,
                        "event": t.event,
                        "guard": t.guard,
                        "actions": t.actions,
                        "business_reason": t.business_reason
                    }
                    for t in output.suggested_transitions
                ],
                "suggested_edge_cases": [
                    {
                        "id": e.id,
                        "scenario": e.scenario,
                        "trigger": e.trigger,
                        "analisi_del_problema": e.analisi_del_problema,
                        "expected_behavior": e.expected_behavior,
                        "priority": e.priority,
                        "related_states": e.related_states
                    }
                    for e in output.suggested_edge_cases
                ],
                "suggested_events": [
                    {
                        "name": e.name,
                        "description": e.description,
                        "payload": e.payload
                    }
                    for e in output.suggested_events
                ],
                "ux_questions": output.ux_questions,
                "confidence_score": output.confidence_score
            }
            
        except Exception as e:
            last_error = e
            print(f"  Tentativo {attempt + 1} fallito: {e}")
            continue
    
    raise last_error


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_output(output: dict) -> tuple[bool, str]:
    """Valida l'output dell'Analyst."""
    
    required_fields = [
        "patterns_detected",
        "suggested_states", 
        "suggested_transitions",
        "suggested_edge_cases",
        "suggested_events",
        "ux_questions",
        "confidence_score"
    ]
    
    for field in required_fields:
        if field not in output:
            return False, f"Campo mancante: {field}"
    
    if not isinstance(output["patterns_detected"], list):
        return False, "patterns_detected deve essere una lista"
    
    if not isinstance(output["suggested_states"], list):
        return False, "suggested_states deve essere una lista"
    
    if not isinstance(output["confidence_score"], (int, float)):
        return False, "confidence_score deve essere un numero"
    
    if not (0 <= output["confidence_score"] <= 1):
        return False, "confidence_score deve essere tra 0 e 1"
    
    for state in output["suggested_states"]:
        if "name" not in state:
            return False, "Ogni stato deve avere un 'name'"
        if "description" not in state:
            return False, "Ogni stato deve avere una 'description'"
        if "business_reason" not in state:
            return False, "Ogni stato deve avere un 'business_reason'"
    
    for trans in output["suggested_transitions"]:
        if "from_state" not in trans:
            return False, "Ogni transizione deve avere 'from_state'"
        if "to_state" not in trans:
            return False, "Ogni transizione deve avere 'to_state'"
        if "event" not in trans:
            return False, "Ogni transizione deve avere 'event'"
    
    for edge in output["suggested_edge_cases"]:
        if "id" not in edge:
            return False, "Ogni edge case deve avere un 'id'"
        if "scenario" not in edge:
            return False, "Ogni edge case deve avere uno 'scenario'"
        if "expected_behavior" not in edge:
            return False, "Ogni edge case deve avere 'expected_behavior'"
        if edge.get("priority") not in ["high", "medium", "low"]:
            return False, "Priority deve essere 'high', 'medium' o 'low'"
    
    return True, ""


# ---------------------------------------------------------------------------
# Main Analysis Function
# ---------------------------------------------------------------------------

def run_analyst(context_file: str, output_file: str) -> dict:
    """
    Esegue l'analisi del contesto e genera suggerimenti.
    LLM È OBBLIGATORIO.
    
    Args:
        context_file: File di contesto da analizzare
        output_file: File JSON di output per i suggerimenti
        
    Returns:
        Metriche sull'analisi
    """
    
    import time
    start_time = time.time()
    
    # Verifica LLM disponibile
    llm_api_key = os.getenv("LLM_API_KEY", "")
    if not llm_api_key or not HAS_INSTRUCTOR:
        print("❌ ERRORE: LLM non disponibile.")
        print("   Il sistema richiede un LLM per funzionare.")
        print("   Configura LLM_API_KEY e installa: pip install openai instructor")
        sys.exit(1)
    
    # Leggi contesto
    with open(context_file, "r", encoding="utf-8") as f:
        context_text = f.read()
    
    print(f"Contesto caricato: {len(context_text)} caratteri")
    print("  🚀 Esecuzione con LLM REALE...")
    
    # Costruisci prompt
    prompt = build_analyst_prompt(context_text)
    
    # Chiama LLM (nessun fallback)
    try:
        analysis = call_llm_analyst(prompt)
    except Exception as e:
        print(f"❌ ERRORE: LLM fallito: {e}")
        print("   Il sistema non può funzionare senza LLM.")
        sys.exit(1)
    
    # Valida output
    is_valid, error_msg = validate_output(analysis)
    if not is_valid:
        print(f"ERRORE: Output non valido: {error_msg}")
        return {
            "error": error_msg,
            "elapsed_seconds": time.time() - start_time
        }
    
    # Scrivi output
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)
    
    elapsed = time.time() - start_time
    
    # Metriche
    metrics = {
        "patterns_detected": len(analysis["patterns_detected"]),
        "states_suggested": len(analysis["suggested_states"]),
        "transitions_suggested": len(analysis["suggested_transitions"]),
        "edge_cases_suggested": len(analysis["suggested_edge_cases"]),
        "events_suggested": len(analysis["suggested_events"]),
        "ux_questions": len(analysis["ux_questions"]),
        "confidence_score": analysis["confidence_score"],
        "output_file": output_file,
        "elapsed_seconds": elapsed,
        "valid": is_valid
    }
    
    return metrics


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Analyst LLM per analisi funzionale")
    parser.add_argument("--context", type=str, default="project_context.md",
                        help="File di contesto da analizzare")
    parser.add_argument("--output", type=str, default="analyst_suggestions.json",
                        help="File JSON di output")
    args = parser.parse_args()
    
    # Check context file
    if not os.path.exists(args.context):
        print(f"Errore: File di contesto non trovato: {args.context}")
        print("Esegui prima 'python ingest.py' per generare project_context.md")
        sys.exit(1)
    
    print("=" * 50)
    print("ANALYST - Analisi Funzionale Automatica")
    print("=" * 50)
    print(f"Contesto: {args.context}")
    print(f"Output: {args.output}")
    print()
    
    # Esegui analisi
    metrics = run_analyst(args.context, args.output)
    
    # Stampa risultati
    print()
    print("=" * 50)
    print("ANALISI COMPLETATA")
    print("=" * 50)
    
    if "error" in metrics:
        print(f"ERRORE: {metrics['error']}")
    else:
        print(f"Pattern rilevati:     {metrics['patterns_detected']}")
        print(f"Stati suggeriti:      {metrics['states_suggested']}")
        print(f"Transizioni:          {metrics['transitions_suggested']}")
        print(f"Edge case:            {metrics['edge_cases_suggested']}")
        print(f"Eventi:               {metrics['events_suggested']}")
        print(f"Domande UX:           {metrics['ux_questions']}")
        print(f"Confidence:           {metrics['confidence_score']:.0%}")
        print(f"Tempo:                {metrics['elapsed_seconds']:.1f}s")
        print()
        print(f"Output: {metrics['output_file']}")
    
    print()
    print("Prossimo step: Review dei suggerimenti o esecuzione fuzzer")


if __name__ == "__main__":
    main()