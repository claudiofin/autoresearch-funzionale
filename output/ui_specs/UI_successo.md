# Stato: `successo`

## Descrizione

Schermata principale con dati caricati con successo. Dashboard o vista principale dell'applicazione.

## Contesto

**Da dove si arriva:**
- `caricamento` → evento `DATI_CARICATI`

**Dove si può andare:**
- `TORNA_INDIETRO` → `vuoto`
- `AGGIORNA` → `caricamento`

## Dati Necessari

- **`risparmio_ytd`** (number): Risparmio totale anno in corso (es. $42,850)
- **`distributori`** (array): Lista distributori con percentuali
- **`acquisti_recenti`** (array): Ultimi acquisti effettuati
- **`cluster_info`** (object): Informazioni sul cluster di appartenenza

## Azioni/Interazioni

| Azione | Evento | Destinazione | Descrizione |
|--------|--------|--------------|-------------|
| Torna Indietro | `TORNA_INDIETRO` | `vuoto` | Torna alla schermata precedente |
| Aggiorna | `AGGIORNA` | `caricamento` | Aggiorna i dati |

## Vincoli e Regole

- Pull-to-refresh per aggiornare i dati
- Skeleton loading durante l'aggiornamento
- Cache dei dati per accesso offline
- Gestione sessione scaduta durante la visualizzazione

## Note UI

- Dashboard con griglia di card
- Grafici a barre per confronti
- Badge e indicatori di stato
- Pull-to-refresh gesture
- Skeleton shimmer durante loading

## Riferimento Tecnico (Entry/Exit Actions)

**Entry:**
- `render_data`
- `render_dashboard`

**Exit:**
- `cache_data`

