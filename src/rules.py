"""
Rules per analisi funzionale automatica.

Contiene SOLO regole strutturali (COSA deve esserci), nessun contenuto hardcoded.
Tutti i nomi, descrizioni, comportamenti sono generati dall'LLM.

Le regole dicono: "deve esserci un flusso di autenticazione"
L'LLM decide: "login_form → login_pending → login_success"
"""

from typing import Dict, List, Set


# ---------------------------------------------------------------------------
# Regole Strutturali (COSA deve esserci, non COME si chiama)
# ---------------------------------------------------------------------------

RULES: Dict[str, dict] = {
    "authentication": {
        "description": "Ogni app con utenti deve avere un flusso di autenticazione",
        "must_have_states": [
            "uno_stato_per_l_input_delle_credenziali",
            "uno_stato_per_l_attesa_della_risposta",
            "uno_stato_per_il_successo",
            "uno_stato_per_il_fallimento",
        ],
        "must_have_transitions": [
            {"from": "stato_input", "to": "stato_attesa", "event": "SUBMIT_CREDENTIALS"},
            {"from": "stato_attesa", "to": "stato_successo", "event": "AUTH_SUCCESS"},
            {"from": "stato_attesa", "to": "stato_fallimento", "event": "AUTH_FAILED"},
        ],
        "edge_cases_to_check": [
            "password_dimenticata_deve_avere_un_flusso_di_recupero",
            "account_bloccato_dopo_troppi_tentativi",
            "sessione_scaduta_deve_permettere_il_relogin",
            "accesso_da_più_dispositivi_contemporaneamente",
        ],
        "questions_to_ask": [
            "Dopo quanti tentativi falliti si blocca l'account?",
            "Quanto dura il token di sessione?",
            "L'utente può essere loggato su più device?",
        ],
    },
    
    "form_handling": {
        "description": "Ogni form deve gestire input, validazione, submit, successo, errore",
        "must_have_states": [
            "uno_stato_per_la_modifica_del_form",
            "uno_stato_per_la_validazione",
            "uno_stato_per_l_attesa_del_submit",
            "uno_stato_per_il_successo",
            "uno_stato_per_l_errore",
        ],
        "must_have_transitions": [
            {"from": "stato_modifica", "to": "stato_validazione", "event": "VALIDATE"},
            {"from": "stato_validazione", "to": "stato_submit", "event": "SUBMIT"},
            {"from": "stato_submit", "to": "stato_successo", "event": "SUBMIT_SUCCESS"},
            {"from": "stato_submit", "to": "stato_errore", "event": "SUBMIT_ERROR"},
            {"from": "qualsiasi_stato_intermedio", "to": "stato_iniziale", "event": "CANCEL"},
        ],
        "edge_cases_to_check": [
            "doppio_click_sul_pulsante_submit",
            "validazione_inline_vs_on_submit",
            "chiusura_browser_durante_submit",
            "dati_persi_per_connessione_persa",
            "campi_obbligatori_mancanti",
        ],
        "questions_to_ask": [
            "La validazione è inline (on blur) o solo on submit?",
            "Cosa succede se l'utente chiude il browser durante il submit?",
            "Il form può essere salvato come bozza?",
        ],
    },
    
    "error_handling": {
        "description": "Ogni operazione async deve gestire errori, timeout, cancellazione",
        "must_have_states": [
            "uno_stato_per_l_errore_generico",
            "uno_stato_per_il_timeout",
            "uno_stato_per_l_annullamento",
        ],
        "must_have_transitions": [
            {"from": "qualsiasi_stato_async", "to": "stato_errore", "event": "ERROR"},
            {"from": "qualsiasi_stato_async", "to": "stato_timeout", "event": "TIMEOUT"},
            {"from": "qualsiasi_stato_async", "to": "stato_annullato", "event": "CANCEL"},
            {"from": "stato_errore", "to": "stato_riprova", "event": "RETRY"},
        ],
        "edge_cases_to_check": [
            "errore_di_rete_durante_operazione_critica",
            "timeout_del_server",
            "rate_limiting_raggiunto",
            "errore_500_del_server",
            "dati_corrotti_o_malformati",
        ],
        "questions_to_ask": [
            "L'utente può riprovare dopo un errore? Quante volte?",
            "Cosa succede se l'errore è irreversibile?",
            "Come comunichi l'errore all'utente (toast, modale, pagina)?",
        ],
    },
    
    "navigation": {
        "description": "Ogni app deve gestire navigazione tra schermate, back, deep link",
        "must_have_states": [
            "uno_stato_home_principale",
            "uno_stato_di_dettaglio",
            "uno_stato_di_caricamento",
        ],
        "must_have_transitions": [
            {"from": "stato_home", "to": "stato_dettaglio", "event": "NAVIGATE_TO_DETAIL"},
            {"from": "stato_dettaglio", "to": "stato_home", "event": "GO_BACK"},
            {"from": "stato_home", "to": "stato_caricamento", "event": "LOAD_DATA"},
        ],
        "edge_cases_to_check": [
            "pulsante_back_durante_caricamento",
            "deep_link_a_pagina_non_esistente",
            "navigazione_doppia_rapida",
            "stato_perso_cambio_orientamento",
        ],
        "questions_to_ask": [
            "Cosa succede se l'utente preme back durante un'operazione?",
            "Come gestisci i deep link se l'utente non è loggato?",
            "Lo stato della schermata viene preservato al ritorno?",
        ],
    },
    
    "empty_states": {
        "description": "Ogni lista o ricerca deve gestire stati vuoti",
        "must_have_states": [
            "uno_stato_per_risultati_vuoti",
            "uno_stato_per_primo_utilizzo",
        ],
        "must_have_transitions": [
            {"from": "stato_ricerca", "to": "stato_vuoto", "event": "NO_RESULTS"},
            {"from": "stato_vuoto", "to": "stato_azione_alternativa", "event": "TAKE_ACTION"},
        ],
        "edge_cases_to_check": [
            "ricerca_senza_risultati",
            "lista_vuota_al_primo_avvio",
            "dati_cancellati_tutti_in_una_volta",
        ],
        "questions_to_ask": [
            "Cosa mostra l'utente quando non ci sono risultati?",
            "Offri azioni alternative quando la lista è vuota?",
            "Come guidi l'utente al primo utilizzo?",
        ],
    },
    
    "notifications": {
        "description": "Ogni app deve gestire notifiche e alert",
        "must_have_states": [
            "uno_stato_per_centro_notifiche",
            "uno_stato_per_dettaglio_notifica",
        ],
        "must_have_transitions": [
            {"from": "qualsiasi_stato", "to": "stato_notifica", "event": "RECEIVE_NOTIFICATION"},
            {"from": "stato_notifica", "to": "stato_dettaglio", "event": "OPEN_NOTIFICATION"},
        ],
        "edge_cases_to_check": [
            "troppe_notifiche_contemporanee",
            "notifica_per_azione_gia_completata",
            "notifiche_disabilitate_dallutente",
        ],
        "questions_to_ask": [
            "Come raggruppi notifiche multiple?",
            "Cosa succede se tappi una notifica per un'azione già completata?",
            "L'utente può disabilitare le notifiche?",
        ],
    },
}


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def get_all_must_have_states() -> Set[str]:
    """Restituisce tutti gli stati che DEVONO esistere (descrittivi, non nomi specifici)."""
    states = set()
    for rule in RULES.values():
        states.update(rule.get("must_have_states", []))
    return states


def get_all_must_have_transitions() -> List[dict]:
    """Restituisce tutte le transizioni che DEVONO esistere."""
    transitions = []
    for rule in RULES.values():
        transitions.extend(rule.get("must_have_transitions", []))
    return transitions


def get_all_edge_cases_to_check() -> Set[str]:
    """Restituisce tutti gli edge case che DEVONO essere verificati."""
    edge_cases = set()
    for rule in RULES.values():
        edge_cases.update(rule.get("edge_cases_to_check", []))
    return edge_cases


def get_all_questions() -> Set[str]:
    """Restituisce tutte le domande che DEVONO essere poste."""
    questions = set()
    for rule in RULES.values():
        questions.update(rule.get("questions_to_ask", []))
    return questions


def validate_against_rules(machine: dict) -> dict:
    """
    Valida una macchina a stati contro le regole.
    Restituisce un report di cosa manca.
    
    Args:
        machine: Macchina a stati XState
        
    Returns:
        Report di validazione con stati e transizioni mancanti
    """
    states = set(machine.get("states", {}).keys())
    transitions = []
    for state_name, state_config in machine.get("states", {}).items():
        for event, target in state_config.get("on", {}).items():
            if isinstance(target, dict):
                target_state = target.get("target", "")
            else:
                target_state = target
            transitions.append((state_name, target_state, event))
    
    missing_states = []
    missing_transitions = []
    
    for rule_name, rule in RULES.items():
        # Check states (descrittivi - l'LLM decide i nomi specifici)
        for required_state_desc in rule.get("must_have_states", []):
            # Non controlliamo nomi esatti, ma cerchiamo stati che contengono parole chiave
            keywords = required_state_desc.lower().replace("uno_stato_per_", "").replace("_", " ").split()
            found = False
            for state in states:
                state_lower = state.lower()
                if any(kw in state_lower for kw in keywords if len(kw) > 3):
                    found = True
                    break
            if not found:
                missing_states.append(f"[{rule_name}] {required_state_desc}")
        
        # Check transitions
        for required_trans in rule.get("must_have_transitions", []):
            event = required_trans.get("event", "")
            found = any(e == event for _, _, e in transitions)
            if not found:
                missing_transitions.append(f"[{rule_name}] {event}")
    
    return {
        "missing_states": missing_states,
        "missing_transitions": missing_transitions,
        "is_valid": len(missing_states) == 0 and len(missing_transitions) == 0,
    }


# ---------------------------------------------------------------------------
# Main (per testing)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Rules ===\n")
    for rule_name, rule in RULES.items():
        print(f"## {rule_name}: {rule['description']}")
        print(f"   Stati richiesti: {len(rule['must_have_states'])}")
        print(f"   Transizioni richieste: {len(rule['must_have_transitions'])}")
        print(f"   Edge case: {len(rule['edge_cases_to_check'])}")
        print()
    
    print(f"Totale stati richiesti: {len(get_all_must_have_states())}")
    print(f"Totale transizioni richieste: {len(get_all_must_have_transitions())}")
    print(f"Totale edge case: {len(get_all_edge_cases_to_check())}")
    print(f"Totale domande: {len(get_all_questions())}")