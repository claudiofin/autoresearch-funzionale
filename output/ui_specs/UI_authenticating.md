# Stato: `authenticating`

## Descrizione

Stato transitorio di verifica token. Non visibile all'utente, gestisce la validazione delle credenziali.

## Contesto

**Da dove si arriva:**
- `app_idle` → evento `VALIDATE_TOKEN`

**Dove si può andare:**
- `TOKEN_VALIDO` → `iniziale`

## Azioni/Interazioni

| Azione | Evento | Destinazione | Descrizione |
|--------|--------|--------------|-------------|
| Procedi | `TOKEN_VALIDO` | `iniziale` | Token valido, procedi |

## Riferimento Tecnico (Entry/Exit Actions)

**Entry:**
- `verify_token`

**Exit:**
- `set_auth_state`

