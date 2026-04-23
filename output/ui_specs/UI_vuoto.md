# Stato: `vuoto`

## Descrizione

Schermata quando non ci sono dati da visualizzare. L'utente può ricaricare o tornare indietro.

## Contesto

**Da dove si arriva:**
- `caricamento` → evento `FETCH_EMPTY`
- `successo` → evento `TORNA_INDIETRO`

**Dove si può andare:**
- `RICARICA` → `caricamento`
- `ANNULLA` → `app_idle`

## Dati Necessari

- **`message`** (string): Nessun dato disponibile da visualizzare
- **`action_hint`** (string): Prova a ricaricare la pagina

## Azioni/Interazioni

| Azione | Evento | Destinazione | Descrizione |
|--------|--------|--------------|-------------|
| Ricarica | `RICARICA` | `caricamento` | Ricarica i dati |
| Annulla | `ANNULLA` | `app_idle` | Torna indietro / Annulla |

## Vincoli e Regole

- Mostrare un'illustrazione o icona per stato vuoto
- Testo descrittivo che spiega perché non ci sono dati
- Azione di ricarica sempre disponibile

## Note UI

- Illustrazione SVG/animata per stato vuoto
- Testo descrittivo centrato
- Pulsante di azione principale (ricarica)
- Design pulito e non frustrante

## Riferimento Tecnico (Entry/Exit Actions)

**Entry:**
- `show_empty_state`

**Exit:**
- `clear_cache`
- `hide_empty_state`

