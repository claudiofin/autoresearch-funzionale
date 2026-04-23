"""
Critic per analisi funzionale automatica.

Legge il report del fuzzer e traduce gli errori tecnici in decisioni UX
che l'Analyst può usare per migliorare la specifica.

Usage:
    python critic.py --fuzz-report fuzz_report.json --output critic_feedback.json
"""

import os
import sys
import json
import argparse
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# UX Decision Templates
# ---------------------------------------------------------------------------

UX_DECISION_TEMPLATES = {
    "UNREACHABLE_STATE": {
        "title": "Stato Irraggiungibile",
        "description": "Lo stato '{state}' non può essere raggiunto dal flusso principale.",
        "ux_question": "Come dovrebbe l'utente arrivare a '{state}'? Quale azione/evento dovrebbe triggerare questa transizione?",
        "suggestions": [
            "Aggiungi una transizione da uno stato raggiungibile",
            "Rimuovi lo stato se non è necessario",
            "Considera se questo stato dovrebbe essere parte di un sotto-flusso"
        ]
    },
    "DEAD_END": {
        "title": "Vicolo Cieco",
        "description": "Lo stato '{state}' non ha transizioni in uscita. L'utente rimane bloccato.",
        "ux_question": "Cosa dovrebbe succedere dopo che l'utente è in '{state}'? Quali opzioni dovrebbe avere?",
        "suggestions": [
            "Aggiungi transizione per continuare il flusso",
            "Aggiungi opzione per tornare indietro",
            "Aggiungi opzione per annullare/chiudere"
        ]
    },
    "INFINITE_LOOP_RISK": {
        "title": "Rischio Loop Infinito",
        "description": "Rilevato potenziale loop infinito tra stati: {path}",
        "ux_question": "Come preveniamo che l'utente rimanga intrappolato in questo ciclo?",
        "suggestions": [
            "Aggiungi un limite di tentativi (es. max 3 retry)",
            "Aggiungi una via di uscita (escape hatch)",
            "Implementa debounce/throttle sugli eventi"
        ]
    },
    "MISSING_ERROR_STATE": {
        "title": "Stato di Errore Mancante",
        "description": "Non è definito uno stato per gestire gli errori in '{state}'.",
        "ux_question": "Cosa vede l'utente quando si verifica un errore in '{state}'?",
        "suggestions": [
            "Aggiungi stato 'error' con messaggio appropriato",
            "Definisci opzioni di recovery (retry, cancel, contact support)",
            "Considera errori specifici per questo contesto"
        ]
    },
    "MISSING_LOADING_STATE": {
        "title": "Stato di Caricamento Mancante",
        "description": "Non è definito uno stato di loading per l'azione '{event}'.",
        "ux_question": "Come comunichiamo all'utente che l'azione '{event}' è in corso?",
        "suggestions": [
            "Aggiungi stato 'loading' con spinner/indicator",
            "Disabilita i pulsanti durante il loading",
            "Mostra feedback immediato del click"
        ]
    },
    "MISSING_TIMEOUT_STATE": {
        "title": "Stato di Timeout Mancante",
        "description": "Non è gestito il timeout per l'azione '{event}'.",
        "ux_question": "Cosa succede se l'azione '{event}' richiede troppo tempo?",
        "suggestions": [
            "Aggiungi stato 'timeout' con messaggio chiaro",
            "Definisci durata del timeout (es. 30s)",
            "Offri opzione di retry con backoff"
        ]
    },
    "EXCESSIVE_SELF_LOOPS": {
        "title": "Troppi Auto-Loop",
        "description": "Lo stato '{state}' ha troppi auto-loop: {events}. Questo indica possibile complessità eccessiva.",
        "ux_question": "Questo stato dovrebbe essere suddiviso in sotto-stati più specifici?",
        "suggestions": [
            "Suddividi in stati più specifici",
            "Usa stati annidati (nested states)",
            "Raggruppa eventi simili"
        ]
    },
    "UNUSED_CONTEXT": {
        "title": "Variabile Contesto Inutilizzata",
        "description": "Una variabile di contesto è definita ma non sembra usata.",
        "ux_question": "Questa variabile serve davvero? Se sì, dove dovrebbe essere usata?",
        "suggestions": [
            "Rimuovi se non necessaria",
            "Aggiungi logica che usa questa variabile",
            "Verifica se è usata in codice non analizzato"
        ]
    },
}


# ---------------------------------------------------------------------------
# Critic Analysis
# ---------------------------------------------------------------------------

class CriticAnalyzer:
    """Analizza errori del fuzzer e genera feedback UX."""
    
    def __init__(self, fuzz_report: dict, spec_file: str = None):
        self.report = fuzz_report
        self.spec_file = spec_file
        self.feedback = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_errors": 0,
                "total_warnings": 0,
                "critical_issues": [],
                "ux_decisions_needed": []
            },
            "issues": [],
            "recommendations": []
        }
    
    def analyze(self) -> dict:
        """Esegue l'analisi completa del report."""
        
        # Conta errori e warning
        self.feedback["summary"]["total_errors"] = len(
            self.report.get("validation_errors", [])
        )
        self.feedback["summary"]["total_warnings"] = len(
            self.report.get("validation_warnings", [])
        )
        
        # Analizza errori di validazione
        for error in self.report.get("validation_errors", []):
            self._process_error(error)
        
        # Analizza warning
        for warning in self.report.get("validation_warnings", []):
            self._process_warning(warning)
        
        # Analizza bug di fuzzing
        fuzz_bugs = self.report.get("fuzzing_bugs", [])
        if fuzz_bugs:
            self._analyze_fuzz_bugs(fuzz_bugs)
        
        # Genera raccomandazioni globali
        self._generate_recommendations()
        
        return self.feedback
    
    def _process_error(self, error: dict):
        """Processa un errore di validazione."""
        error_type = error.get("type", "UNKNOWN")
        template = UX_DECISION_TEMPLATES.get(error_type, {
            "title": "Errore Sconosciuto",
            "description": "Errore: {error}",
            "ux_question": "Come risolviamo questo errore?",
            "suggestions": ["Review della specifica"]
        })
        
        state = error.get("state", "unknown")
        message = error.get("message", "")
        
        # Crea issue strutturata
        issue = {
            "id": f"ISS-{len(self.feedback['issues'])+1:03d}",
            "type": error_type,
            "severity": "critical",
            "title": template["title"],
            "description": template["description"].format(state=state, error=message),
            "ux_question": template["ux_question"].format(state=state, event=error.get("event", "unknown")),
            "suggestions": template["suggestions"],
            "raw_error": error,
            "analyst_action_required": True
        }
        
        self.feedback["issues"].append(issue)
        self.feedback["summary"]["critical_issues"].append(issue["id"])
    
    def _process_warning(self, warning: dict):
        """Processa un warning di validazione."""
        warning_type = warning.get("type", "UNKNOWN")
        template = UX_DECISION_TEMPLATES.get(warning_type, {
            "title": "Warning",
            "description": "Warning: {warning}",
            "ux_question": "Come miglioriamo questo aspetto?",
            "suggestions": ["Review della specifica"]
        })
        
        state = warning.get("state", "unknown")
        message = warning.get("message", "")
        
        # Crea issue
        issue = {
            "id": f"ISS-{len(self.feedback['issues'])+1:03d}",
            "type": warning_type,
            "severity": "warning",
            "title": template["title"],
            "description": template["description"].format(state=state, warning=message),
            "ux_question": template["ux_question"].format(state=state, event=warning.get("event", "unknown")),
            "suggestions": template["suggestions"],
            "raw_error": warning,
            "analyst_action_required": warning_type in ["DEAD_END", "MISSING_ERROR_STATE"]
        }
        
        self.feedback["issues"].append(issue)
        if issue["analyst_action_required"]:
            self.feedback["summary"]["ux_decisions_needed"].append(issue["id"])
    
    def _analyze_fuzz_bugs(self, bugs: list):
        """Analizza i bug trovati dal fuzzer."""
        # Raggruppa bug per tipo
        bug_types = {}
        for bug in bugs:
            bug_type = bug.get("type", "UNKNOWN")
            if bug_type not in bug_types:
                bug_types[bug_type] = []
            bug_types[bug_type].append(bug)
        
        # Crea issue per ogni tipo di bug (con esempi)
        for bug_type, bug_list in bug_types.items():
            template = UX_DECISION_TEMPLATES.get(bug_type, {
                "title": bug_type,
                "description": "Trovati {count} bug di tipo {type}",
                "ux_question": "Come preveniamo questi bug?",
                "suggestions": ["Review della specifica"]
            })
            
            # Prendi un esempio rappresentativo
            example_bug = bug_list[0]
            details = example_bug.get("details", {})
            path = details.get("path", [])
            
            issue = {
                "id": f"ISS-{len(self.feedback['issues'])+1:03d}",
                "type": bug_type,
                "severity": "warning",
                "title": template["title"],
                "description": template["description"].format(
                    count=len(bug_list), 
                    type=bug_type,
                    path=" -> ".join(path[:5]) if path else "N/A"
                ),
                "ux_question": template["ux_question"].format(path=path),
                "occurrences": len(bug_list),
                "example_path": path[:10],  # Limita a 10 step
                "suggestions": template["suggestions"],
                "analyst_action_required": bug_type == "INFINITE_LOOP_RISK"
            }
            
            self.feedback["issues"].append(issue)
            if issue["analyst_action_required"]:
                self.feedback["summary"]["ux_decisions_needed"].append(issue["id"])
    
    def _generate_recommendations(self):
        """Genera raccomandazioni basate sugli errori trovati."""
        recommendations = []
        
        # Conta tipi di errori
        error_counts = {}
        for issue in self.feedback["issues"]:
            error_type = issue["type"]
            error_counts[error_type] = error_counts.get(error_type, 0) + 1
        
        # Genera raccomandazioni basate sui pattern di errori
        if error_counts.get("DEAD_END", 0) > 0:
            recommendations.append({
                "priority": "high",
                "category": "UX Flow",
                "recommendation": "Aggiungi transizioni di uscita da tutti gli stati terminali. "
                                  "Ogni stato dovrebbe avere almeno: (1) via per continuare, "
                                  "(2) via per annullare/tornare indietro."
            })
        
        if error_counts.get("UNREACHABLE_STATE", 0) > 0:
            recommendations.append({
                "priority": "high",
                "category": "State Design",
                "recommendation": "Review degli stati irraggiungibili. Per ogni stato, "
                                  "definisci chiaramente quale evento/azione porta a quello stato."
            })
        
        if error_counts.get("INFINITE_LOOP_RISK", 0) > 0:
            recommendations.append({
                "priority": "medium",
                "category": "Error Handling",
                "recommendation": "Implementa meccanismi di break per i loop: "
                                  "max retry count, timeout, o escape hatch."
            })
        
        if len(self.feedback["issues"]) > 10:
            recommendations.append({
                "priority": "medium",
                "category": "Complexity",
                "recommendation": "La specifica ha molti problemi. Considera di "
                                  "semplificare il flusso o suddividere in sotto-flussi."
            })
        
        self.feedback["recommendations"] = recommendations


# ---------------------------------------------------------------------------
# Main Function
# ---------------------------------------------------------------------------

def run_critic(fuzz_report_file: str, output_file: str) -> dict:
    """
    Esegue l'analisi del Critic.
    
    Args:
        fuzz_report_file: File del report del fuzzer
        output_file: File JSON di output per il feedback
        
    Returns:
        Metriche sull'analisi
    """
    
    import time
    start_time = time.time()
    
    # Leggi report
    with open(fuzz_report_file, "r", encoding="utf-8") as f:
        fuzz_report = json.load(f)
    
    print(f"Report caricato: {len(fuzz_report.get('validation_errors', []))} errori, "
          f"{len(fuzz_report.get('validation_warnings', []))} warning")
    
    # Analizza
    analyzer = CriticAnalyzer(fuzz_report)
    feedback = analyzer.analyze()
    
    # Scrivi output
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(feedback, f, indent=2, ensure_ascii=False)
    
    elapsed = time.time() - start_time
    
    # Metriche
    metrics = {
        "total_issues": len(feedback["issues"]),
        "critical_issues": len(feedback["summary"]["critical_issues"]),
        "ux_decisions_needed": len(feedback["summary"]["ux_decisions_needed"]),
        "recommendations": len(feedback["recommendations"]),
        "output_file": output_file,
        "elapsed_seconds": elapsed
    }
    
    return metrics


def main():
    parser = argparse.ArgumentParser(description="Critic per analisi funzionale")
    parser.add_argument("--fuzz-report", type=str, default="fuzz_report.json",
                        help="File del report del fuzzer")
    parser.add_argument("--output", type=str, default="critic_feedback.json",
                        help="File JSON di output per il feedback")
    args = parser.parse_args()
    
    # Check file
    if not os.path.exists(args.fuzz_report):
        print(f"Errore: File non trovato: {args.fuzz_report}")
        print("Esegui prima 'python fuzzer.py' per generare il report")
        sys.exit(1)
    
    print("=" * 50)
    print("CRITIC - Analisi Feedback UX")
    print("=" * 50)
    print(f"Report: {args.fuzz_report}")
    print(f"Output: {args.output}")
    print()
    
    # Esegui analisi
    metrics = run_critic(args.fuzz_report, args.output)
    
    # Stampa risultati
    print()
    print("=" * 50)
    print("ANALISI CRITIC COMPLETATA")
    print("=" * 50)
    print(f"Totale issue:       {metrics['total_issues']}")
    print(f"Issue critiche:     {metrics['critical_issues']}")
    print(f"Decisioni UX:       {metrics['ux_decisions_needed']}")
    print(f"Raccomandazioni:    {metrics['recommendations']}")
    print(f"Tempo:              {metrics['elapsed_seconds']:.1f}s")
    print()
    print(f"Output: {metrics['output_file']}")
    print()
    print("Prossimo step: Review del feedback o esecuzione loop.py")


if __name__ == "__main__":
    main()