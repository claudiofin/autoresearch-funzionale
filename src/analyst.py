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
    """Costruisce il prompt per l'Analyst LLM."""
    
    prompt = f"""# Functional Analysis Agent

Sei un Senior Product Manager e System Analyst esperto.
Il tuo compito è analizzare il contesto del progetto e generare una specifica funzionale completa.

## Contesto del Progetto

{context_text}

## Il Tuo Compito

Analizza il contesto e produci un'analisi strutturata che includa:

### 1. Pattern Rilevati
Identifica quali pattern comuni (checkout, login, form, upload, search, notification) sono presenti.

### 2. Stati Mancanti
Per ogni pattern rilevato, suggerisci stati che non sono esplicitamente menzionati ma sono necessari per un'esperienza utente completa.

### 3. Transizioni Necessarie
Definisci come gli utenti si muovono tra gli stati, includendo:
- Flussi principali (happy path)
- Flussi alternativi (errori, annullamenti)
- Flussi di recupero (retry, back navigation)

### 4. Edge Case
Identifica almeno 5-10 edge case per ogni pattern principale, considerando:
- Errori di rete e timeout
- Input utente invalidi
- Navigazione browser (back button, refresh)
- Stati concorrenti (doppio click, sessioni multiple)
- Limiti del sistema (rate limiting, quote)

## Regola CRITICA per Edge Case: Chain of Thought OBBLIGATORIO

Per OGNI edge case, DEVI prima analizzare il PERCHÉ si verifica quel problema specifico, POI definire il comportamento.

**Esempio CORRETTO:**
```json
{{
  "id": "EC004",
  "scenario": "Password Dimenticata",
  "trigger": "Utente clicca Password dimenticata senza aver compilato il form",
  "analisi_del_problema": "Lutente non ricorda la propria password attuale. Non e un errore tecnico ma un bisogno di recupero account. Serve un flusso di reset via email.",
  "expected_behavior": "Apre modale con titolo Recupera Password, campo email con placeholder Inserisci email associata allaccount, pulsante Invia Link di Reset. Link Annulla per chiudere.",
  "priority": "high",
  "related_states": ["login_form", "login_recovery"]
}}
```

**Esempio SBAGLIATO (VIETATO):**
- Usare "Connessione assente" per problemi che non sono di rete
- Usare "File troppo grande" per problemi di formato
- Copiare-incollare comportamenti da altri edge case
- Analisi del problema generica o assente

### 5. Domande UX
Elenca le domande di prodotto che richiedono risposta per completare la specifica.

## Formato di Risposta

DEVI rispondere ESCLUSIVAMENTE con un JSON valido che segue questo schema:

```json
{{
    "patterns_detected": ["pattern1", "pattern2"],
    "suggested_states": [
        {{
            "name": "state_name",
            "description": "Cosa rappresenta questo stato",
            "entry_actions": ["action1", "action2"],
            "exit_actions": [],
            "parent_pattern": "pattern_name",
            "business_reason": "Perché questo stato è necessario dal punto di vista del business"
        }}
    ],
    "suggested_transitions": [
        {{
            "from_state": "state1",
            "to_state": "state2",
            "event": "EVENT_NAME",
            "guard": "condition (optional)",
            "actions": ["action1"],
            "business_reason": "Perché questa transizione è necessaria"
        }}
    ],
    "suggested_edge_cases": [
        {{
            "id": "EC001",
            "scenario": "Descrizione scenario",
            "trigger": "Cosa causa questo",
            "expected_behavior": "Cosa dovrebbe fare il sistema",
            "priority": "high|medium|low",
            "related_states": ["state1", "state2"]
        }}
    ],
    "suggested_events": [
        {{
            "name": "EVENT_NAME",
            "description": "Descrizione",
            "payload": {{"field": "type"}}
        }}
    ],
    "ux_questions": [
        "Domanda 1?",
        "Domanda 2?"
    ],
    "confidence_score": 0.85
}}
```

    ## Regole Importanti

1. **Sii specifico**: Non dire "gestisci gli errori", dì "mostra messaggio di errore con opzione retry"
2. **Giustifica**: Per ogni stato/transizione, spiega il motivo di business
3. **Completo**: Copri sia l'happy path che gli error path
4. **Coerente**: Usa naming convention coerente (snake_case per stati, UPPER_CASE per eventi)
5. **Pragmatico**: Suggerisci solo stati/transizioni realmente necessari

## Regole OBBLIGATORIE (VIOLAZIONI = OUTPUT INVALIDO)

### 1. DIVIETO DI LINEARITÀ FORZATA (Anti-"Salsiccia")
- **NON** collegare pattern diversi in un'unica sequenza lineare a meno che non sia LOGICAMENTE NECESSARIO
- Flussi paralleli (login, checkout, upload) devono rimanere **SEPARATI** o **RAMIFICATI**, non concatenati
- Esempio di ERRORE: `payment_pending -> login_form -> form_editing -> upload_idle` (questo è un bug)
- Esempio CORRETTO: Ogni pattern ha i propri stati e transizioni interne, connessi solo tramite stati hub se necessario

### 2. NO PLACEHOLDER (VIETATO COPIA-INCOLLA)
- **VIETATO USARE**: "gestisce gracefully", "necessario per gestire", "completa il flusso", "permette di procedere"
- **OBBLIGATORIO**: Descrivere l'esatto comportamento osservabile dall'utente
  - ❌ SBAGLIATO: "Il sistema gestisce gracefully l'errore"
  - ✅ CORRETTO: "Mostra toast rosso 'Pagamento fallito: carta rifiutata'. Disabilita pulsante per 3 secondi. Mantiene dati carta compilati."

### 3. MAPPATURA OBBLIGATORIA: EDGE CASE → TRANSIZIONI
- Per **OGNI** edge_case che identifichi, DEVI creare la transizione corrispondente
- Esempio: se EC001 = "Pagamento Fallito", devi avere una transizione da payment_pending a checkout_payment con evento PAYMENT_FAILED
- Se un edge case non ha una transizione associata, l'output è INVALIDO

### 4. TRANSIZIONI DI ERRORE OBBLIGATORIE
- Ogni stato che chiama API o fa operazioni async DEVE avere transizioni per:
  - `ERROR` (gestione errore generico)
  - `TIMEOUT` (timeout operazione)
  - `CANCEL` (annullamento utente)
- Esempio: `payment_pending` deve avere almeno 3 uscite: SUCCESS, ERROR, TIMEOUT

Rispondi SOLO con il JSON, senza testo aggiuntivo.
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
    print(f"  ⏱️  Timeout: 120s, Max tokens: 4096")
    
    last_error = None
    for attempt in range(max_retries):
        try:
            print(f"  Tentativo {attempt + 1}/{max_retries}...")
            response = client.chat.completions.create(
                timeout=120,
                model=model,
                messages=[
                    {"role": "system", "content": "Sei un Senior Product Manager e System Analyst esperto. Rispondi SOLO con JSON valido, senza markdown o codice. Solo JSON puro."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=4096,
                frequency_penalty=0.5,
                presence_penalty=0.3
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