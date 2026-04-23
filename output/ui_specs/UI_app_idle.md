# Stato: `app_idle`

## Descrizione

Schermata iniziale dell'applicazione. Punto di ingresso del flusso, dove l'utente avvia il processo o si trova prima dell'autenticazione.

## Contesto

**Da dove si arriva:**
- `caricamento` → evento `TIMEOUT`
- `vuoto` → evento `ANNULLA`

**Dove si può andare:**
- `AVVIA_CARICAMENTO` → `iniziale`
- `START_FLOW` → `iniziale`
- `VALIDATE_TOKEN` → `authenticating`

## Dati Necessari

- **`email`** (string): Email dell'utente (es. demo@vetunita.it)
- **`password`** (string): Password (min. 8 caratteri)

## Azioni/Interazioni

| Azione | Evento | Destinazione | Descrizione |
|--------|--------|--------------|-------------|
| Avvia | `AVVIA_CARICAMENTO` | `iniziale` | Pulsante principale per iniziare il flusso |
| Inizia | `START_FLOW` | `iniziale` | Pulsante per avviare il processo |
| Accedi | `VALIDATE_TOKEN` | `authenticating` | Pulsante di login/autenticazione |

## Vincoli e Regole

- I campi email e password devono essere validi prima di abilitare il pulsante di accesso
- Deve essere presente un link per 'Password dimenticata?'
- Supporto per accesso guest/demo

## Note UI

- Layout centrato con card di login
- Logo dell'app in alto
- Campi input con icone (email, lock)
- Pulsante primario grande e visibile
- Link secondari in basso (password dimenticata, registrazione)

## Riferimento Tecnico (Entry/Exit Actions)

**Entry:**
- `reset_ui`

**Exit:**
- `init_flow`
- `track_start`

