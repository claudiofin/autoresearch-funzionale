# Stato: `caricamento`

## Descrizione

Stato transitorio di loading. Mostra skeleton UI mentre i dati vengono caricati dal server. Non è una schermata permanente.

## Contesto

**Da dove si arriva:**
- `iniziale` → evento `AVVIA_CARICAMENTO`
- `vuoto` → evento `RICARICA`
- `errore` → evento `RIPROVA`
- `successo` → evento `AGGIORNA`

**Dove si può andare:**
- `DATI_CARICATI` → `successo`
- `ERRORE_RETE` → `errore`
- `TIMEOUT` → `app_idle`
- `FETCH_SUCCESS` → `successo`
- `FETCH_EMPTY` → `vuoto`
- `FETCH_ERROR` → `errore`

## Azioni/Interazioni

| Azione | Evento | Destinazione | Descrizione |
|--------|--------|--------------|-------------|
| Continua | `DATI_CARICATI` | `successo` | Procedi con i dati caricati |
| Riprova | `ERRORE_RETE` | `errore` | Riprovare l'operazione |
| Riprova | `TIMEOUT` | `app_idle` | Riprovare per timeout |
| Visualizza | `FETCH_SUCCESS` | `successo` | Visualizza i dati caricati |
| Ricarica | `FETCH_EMPTY` | `vuoto` | Ricarica la pagina |
| Riprova | `FETCH_ERROR` | `errore` | Riprovare il caricamento |

## Riferimento Tecnico (Entry/Exit Actions)

**Entry:**
- `show_skeleton`

**Exit:**
- `hide_skeleton`

