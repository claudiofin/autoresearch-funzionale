# Stato: `sessione_scaduta`

## Descrizione

Schermata di riautenticazione. Appare quando la sessione è scaduta e l'utente deve effettuare nuovamente il login.

## Contesto

**Da dove si arriva:**
- `errore` → evento `RIAUTENTICAZIONE`

**Dove si può andare:**
- `RIAUTENTICAZIONE` → `iniziale`

## Dati Necessari

- **`redirect_url`** (string): URL della pagina di login
- **`message`** (string): La sessione è scaduta, effettua nuovamente il login

## Azioni/Interazioni

| Azione | Evento | Destinazione | Descrizione |
|--------|--------|--------------|-------------|
| Riautenticati | `RIAUTENTICAZIONE` | `iniziale` | Effettuare nuovamente il login |

## Vincoli e Regole

- Salvataggio dello stato corrente prima del redirect
- Possibilità di tornare alla schermata precedente dopo il login
- Clear dei token scaduti

## Note UI

- Modal o schermata intera con overlay
- Messaggio chiaro sulla scadenza sessione
- Pulsante di login prominente
- Opzione per salvare il lavoro corrente

## Riferimento Tecnico (Entry/Exit Actions)

**Entry:**
- `show_login_prompt`
- `clear_auth_store`

**Exit:**
- `redirect_login`
- `clear_tokens`

