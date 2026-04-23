# Stato: `iniziale`

## Descrizione

Schermata di validazione iniziale. L'utente inserisce i dati di accesso o le credenziali. Vengono validati i parametri prima di procedere.

## Contesto

**Da dove si arriva:**
- `app_idle` → evento `AVVIA_CARICAMENTO`
- `sessione_scaduta` → evento `RIAUTENTICAZIONE`
- `authenticating` → evento `TOKEN_VALIDO`

**Dove si può andare:**
- `AVVIA_CARICAMENTO` → `caricamento`
- `INPUT_INVALIDO` → `errore`
- `VALIDATE_AND_LOAD` → `caricamento`

## Dati Necessari

- **`credentials`** (object): Credenziali di accesso validate
- **`config`** (object): Configurazione dell'app caricata

## Azioni/Interazioni

| Azione | Evento | Destinazione | Descrizione |
|--------|--------|--------------|-------------|
| Avvia | `AVVIA_CARICAMENTO` | `caricamento` | Pulsante principale per iniziare il flusso |
| Correggi | `INPUT_INVALIDO` | `errore` | Azione per correggere input errato |
| Conferma e Carica | `VALIDATE_AND_LOAD` | `caricamento` | Convalida i dati e avvia il caricamento |

## Vincoli e Regole

- Validazione input prima del caricamento
- Configurazione caricata prima di procedere
- Gestione input invalido con messaggio chiaro

## Note UI

- Form con validazione inline
- Feedback visivo per campi validi/invalidi
- Pulsante disabilitato fino a validazione completa

## Riferimento Tecnico (Entry/Exit Actions)

**Entry:**
- `validate_input`
- `load_config`

**Exit:**
- `validate_params`
- `clear_validation`

