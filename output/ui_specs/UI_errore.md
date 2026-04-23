# Stato: `errore`

## Descrizione

Schermata di errore. Mostra banner e toast di errore quando si verifica un problema (rete, timeout, ecc.).

## Contesto

**Da dove si arriva:**
- `iniziale` → evento `INPUT_INVALIDO`
- `caricamento` → evento `ERRORE_RETE`

**Dove si può andare:**
- `RIPROVA` → `caricamento`
- `RIAUTENTICAZIONE` → `sessione_scaduta`

## Dati Necessari

- **`error_code`** (string): Codice errore (es. NET_001, TIMEOUT_001)
- **`error_message`** (string): Messaggio descrittivo per l'utente
- **`retry_available`** (boolean): Se è possibile riprovare

## Azioni/Interazioni

| Azione | Evento | Destinazione | Descrizione |
|--------|--------|--------------|-------------|
| Riprova | `RIPROVA` | `caricamento` | Riprovare l'operazione |
| Riautenticati | `RIAUTENTICAZIONE` | `sessione_scaduta` | Effettuare nuovamente il login |

## Vincoli e Regole

- Messaggio di errore chiaro e non tecnico
- Azione di retry sempre disponibile quando possibile
- Logging dell'errore per debugging
- Possibilità di contattare il supporto

## Note UI

- Icona di errore visibile (⚠️ o similar)
- Banner rosso in alto o messaggio centrato
- Toast di errore per dettagli tecnici
- Pulsante di retry prominente

## Riferimento Tecnico (Entry/Exit Actions)

**Entry:**
- `show_error_banner`
- `show_error_toast`

**Exit:**
- `log_error`

