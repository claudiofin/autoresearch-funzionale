# Autoresearch - Analisi Funzionale Automatica

> **Il concetto**: dare a un'IA un progetto (note, screenshot, HTML) e lasciare che generi autonomamente la specifica funzionale completa con diagrammi, edge case e macchine a stati eseguibili.

L'idea è ispirata al progetto [autoresearch](https://github.com/karpathy/autoresearch) di Andrej Karpathy, ma applicata al Product Management invece che al training di modelli LLM.

## Come Funziona

1. **Input**: file di testo, note, screenshot, HTML delle UI
2. **Ingest**: estrae il contesto dal materiale grezzo
3. **Analyst**: l'LLM analizza e genera stati, transizioni, edge case
4. **Spec**: genera specifica funzionale con diagrammi PlantUML e macchina a stati XState
5. **Completeness**: valida che tutti i flussi critici siano presenti
6. **Fuzzer**: testa la macchina a stati con percorsi casuali
7. **Loop**: il sistema itera automaticamente migliorando la specifica

## Quick Start

```bash
# 1. Installa dipendenze
pip install -r requirements.txt

# 2. Configura LLM (OBBLIGATORIO)
export LLM_API_KEY="la-tua-chiave"
export LLM_PROVIDER="openai"  # o anthropic, google, dashscope

# 3. Metti i tuoi input in inputs/
cp tuoi_file.txt inputs/

# 4. Esegui il loop autonomo (con ingest automatico)
python run.py loop --input-dir inputs/ --max-iterations 10 --force
```

### Modalità di Esecuzione

```bash
# Modalità 1: Loop completo con ingest automatico
python run.py loop --input-dir inputs/ --max-iterations 10

# Modalità 2: Loop senza ingest (contesto già esistente)
python run.py loop --context output/project_context.md --max-iterations 10

# Modalità 3: Solo ingest
python run.py ingest --input-dir inputs/

# Modalità 4: Step singoli
python run.py analyst --context output/project_context.md
python run.py spec --context output/project_context.md
python run.py completeness --spec output/spec.md --machine output/spec_machine.json
python run.py fuzzer --machine output/spec_machine.json
```

## Struttura del Progetto

```
autoresearch/
├── inputs/              # I tuoi file di input (testo, note, HTML)
├── output/              # File generati automaticamente
│   ├── project_context.md   # Contesto estratto
│   ├── analyst_suggestions.json  # Analisi dell'LLM
│   ├── spec.md              # Specifica funzionale con PlantUML
│   ├── spec_machine.json    # Macchina a stati XState
│   └── fuzzer_report.json   # Report del fuzzer
├── src/
│   ├── config.py          # Configurazione LLM multi-provider
│   ├── rules.py           # Regole strutturali (COSA deve esserci)
│   ├── ingest.py          # Estrae contesto dagli input
│   ├── analyst.py         # Analizza e genera stati/transizioni
│   ├── spec.py            # Genera specifica con PlantUML + XState
│   ├── completeness.py    # Valida completezza flussi
│   ├── fuzzer.py          # Testa macchina a stati
│   ├── critic.py          # Revisore ostile (edge case)
│   └── loop.py            # Loop autonomo
├── run.py                 # Entry point principale
└── requirements.txt       # Dipendenze Python
```

## Configurazione LLM

Il sistema supporta multiple LLM provider. Configura con variabili d'ambiente:

| Variabile | Descrizione | Esempio |
|-----------|-------------|---------|
| `LLM_API_KEY` | Chiave API (OBBLIGATORIA) | `sk-...` |
| `LLM_PROVIDER` | Provider da usare | `openai`, `anthropic`, `google`, `dashscope` |
| `LLM_BASE_URL` | URL base (opzionale, override) | `https://api.openai.com/v1` |
| `LLM_MODEL` | Modello da usare (opzionale, override) | `gpt-4o`, `claude-3-5-sonnet-20241022` |

### Provider Supportati

| Provider | `LLM_PROVIDER` | Modello Default |
|----------|----------------|-----------------|
| OpenAI | `openai` | `gpt-4o` |
| Anthropic | `anthropic` | `claude-3-5-sonnet-20241022` |
| Google | `google` | `gemini-2.0-flash` |
| DashScope (Alibaba) | `dashscope` | `qwen-plus` |

### Esempi

```bash
# OpenAI (default)
export LLM_API_KEY="sk-proj-..."

# Anthropic
export LLM_API_KEY="sk-ant-..."
export LLM_PROVIDER="anthropic"

# Google
export LLM_API_KEY="AIza..."
export LLM_PROVIDER="google"

# DashScope (Qwen)
export LLM_API_KEY="sk-..."
export LLM_PROVIDER="dashscope"

# Custom provider (OpenAI-compatible)
export LLM_API_KEY="your-key"
export LLM_PROVIDER="custom"
export LLM_BASE_URL="https://your-api.com/v1"
export LLM_MODEL="your-model"
```

## Output

### Specifica Funzionale (spec.md)

La specifica generata include:

1. **User Flows**: descrizione testuale di tutti i flussi utente
2. **State Diagram (PlantUML)**: diagramma di stato eseguibile
3. **XState Configuration**: macchina a stati JSON compatibile con XState
4. **Sequence Diagram (PlantUML)**: diagramma di sequenza User → Interface → Backend
5. **Edge Cases**: tabella con tutti gli edge case identificati
6. **Error Handling**: gestione errori con codici HTTP e recovery
7. **Data Validation**: regole di validazione input
8. **API Contract**: contratti API generati dall'LLM

### Diagrammi PlantUML

I diagrammi sono in formato PlantUML, renderizzabili da:
- Editor Markdown con supporto PlantUML (VS Code, IntelliJ)
- [PlantUML Web Server](http://www.plantuml.com/plantuml/uml/)
- GitHub (con estensione PlantUML)

### Macchina a Stati XState

La macchina a stati è in formato JSON compatibile con [XState](https://xstate.js.org/):

```json
{
  "id": "appFlow",
  "initial": "idle",
  "context": {"user": null, "errors": [], "retryCount": 0},
  "states": {
    "idle": {
      "entry": ["initializeApp"],
      "on": {
        "START": "loading"
      }
    },
    "loading": {
      "entry": ["showLoadingIndicator"],
      "on": {
        "SUCCESS": "success",
        "ERROR": "error",
        "TIMEOUT": "timeout"
      }
    }
  }
}
```

## Design Choices

### LLM Obbligatorio

Il sistema **richiede** un LLM per funzionare. Non ci sono fallback simulati.

- **Perché**: la qualità dell'analisi dipende dalla capacità dell'LLM di comprendere il contesto
- **Cosa serve**: qualsiasi LLM con supporto API OpenAI-compatible
- **Consigliato**: modelli con finestra di contesto lunga (8K+ token)

### Regole vs Contenuti

Il sistema usa un approccio a due livelli:

1. **Regole** (`src/rules.py`): dicono COSA deve esserci (es. "deve esserci un flusso di autenticazione")
2. **LLM**: decide COME si chiama (es. "login_form → login_pending → login_success")

Questo permette al sistema di essere generico e adattarsi a qualsiasi progetto.

### PlantUML invece di Mermaid

I diagrammi sono in PlantUML perché:
- Supporta diagrammi di stato più complessi
- Sintassi più leggibile per macchine a stati
- Migliore supporto per entry/exit actions
- Renderizzazione più bella per diagrammi di sequenza

### Loop Autonomo

Il sistema itera automaticamente:

1. **Analyst** genera stati e transizioni
2. **Spec** genera la specifica con PlantUML
3. **Completeness** valida che tutti i flussi siano presenti
4. **Fuzzer** testa la macchina a stati
5. **Critic** trova edge case mancanti
6. **Loop** riparte dai punti deboli trovati

## Requisiti

- Python 3.10+
- Chiave API per un LLM provider
- 2GB RAM (per il processing dei file)

### Dipendenze Opzionali

Per installare le dipendenze opzionali (PDF, DOCX):

```bash
pip install -r requirements-optional.txt
```

| Dipendenza | Per cosa | Obbligatoria? |
|------------|----------|---------------|
| `pypdf` | Lettura PDF | No |
| `python-docx` | Lettura DOCX | No |
| `openai` | LLM + Vision API | **Sì** |
| `instructor` | Output strutturato | No |
| `beautifulsoup4` | Parsing HTML | **Sì** |

## License

MIT