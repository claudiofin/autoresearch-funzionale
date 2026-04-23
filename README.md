# Autoresearch - Automatic Functional Analysis

> **The concept**: give an AI a project (notes, screenshots, HTML) and let it autonomously generate the complete functional specification with diagrams, edge cases, and executable state machines.

The idea is inspired by Andrej Karpathy's [autoresearch](https://github.com/karpathy/autoresearch) project, but applied to Product Management instead of LLM model training.

## How It Works

1. **Input**: text files, notes, screenshots, HTML from UIs
2. **Ingest**: extracts context from raw material
3. **Analyst**: the LLM analyzes and generates states, transitions, edge cases
4. **Spec**: generates functional specification with PlantUML diagrams and XState state machine
5. **Validator**: validates that all critical flows are present
6. **Fuzzer**: tests the state machine with random paths
7. **Critic**: hostile reviewer (finds missing edge cases)
8. **Loop**: the system iterates automatically improving the specification

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure LLM (REQUIRED)
export LLM_API_KEY="your-key"
export LLM_PROVIDER="openai"  # or anthropic, google, dashscope

# 3. Put your inputs in inputs/
cp your_files.txt inputs/

# 4. Run the autonomous loop (with automatic ingest)
python run.py loop --input-dir inputs/ --max-iterations 10 --force
```

### Execution Modes

```bash
# Mode 1: Complete loop with automatic ingest
python run.py loop --input-dir inputs/ --max-iterations 10

# Mode 2: Loop without ingest (context already exists)
python run.py loop --context output/project_context.md --max-iterations 10

# Mode 3: Ingest only
python run.py ingest --input-dir inputs/

# Mode 4: Individual steps
python run.py analyst --context output/project_context.md
python run.py spec --context output/project_context.md
python run.py validator --machine output/spec/spec_machine.json
python run.py fuzzer --machine output/spec_machine.json
python run.py critic --fuzz-report output/fuzz_report.json
```

## Project Structure

```
autoresearch/
├── inputs/              # Your input files (text, notes, HTML)
├── output/              # Automatically generated files
│   ├── context/
│   │   └── project_context.md   # Extracted context
│   ├── analyst/
│   │   └── analyst_suggestions.json  # LLM analysis
│   ├── spec/
│   │   ├── spec.md              # Functional specification with PlantUML
│   │   └── spec_machine.json    # XState state machine
│   ├── fuzzer_report.json   # Fuzzer report
│   └── critic_feedback.json # Critic feedback
├── src/
│   ├── config.py          # Multi-provider LLM configuration
│   ├── rules.py           # Structural rules (WHAT must be there)
│   ├── ingest.py          # Extracts context from inputs
│   ├── analyst.py         # Analyzes and generates states/transitions
│   ├── spec.py            # Generates specification with PlantUML + XState
│   ├── validator.py       # Validates state machine
│   ├── fuzzer.py          # Tests state machine
│   ├── critic.py          # Hostile reviewer (edge cases)
│   ├── ui_generator.py    # Generates UI specs for AI generators
│   └── loop.py            # Autonomous loop
├── run.py                 # Main entry point
└── requirements.txt       # Python dependencies
```

## LLM Configuration

The system supports multiple LLM providers. Configure with environment variables:

| Variable | Description | Example |
|-----------|-------------|---------|
| `LLM_API_KEY` | API Key (REQUIRED) | `sk-...` |
| `LLM_PROVIDER` | Provider to use | `openai`, `anthropic`, `google`, `dashscope` |
| `LLM_BASE_URL` | Base URL (optional, override) | `https://api.openai.com/v1` |
| `LLM_MODEL` | Model to use (optional, override) | `gpt-4o`, `claude-3-5-sonnet-20241022` |

### Supported Providers

| Provider | `LLM_PROVIDER` | Default Model |
|----------|----------------|-----------------|
| OpenAI | `openai` | `gpt-4o` |
| Anthropic | `anthropic` | `claude-3-5-sonnet-20241022` |
| Google | `google` | `gemini-2.0-flash` |
| DashScope (Alibaba) | `dashscope` | `qwen-plus` |

### Examples

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

### UI Specifications (output/ui_specs/)

After generating the state machine, you can use `ui_generator.py` to create **Markdown Blueprints** ready to be used with AI UI generators:

```bash
# Generate all UI specs (states + screens + README)
python3 src/ui_generator.py

# With specific provider
python3 src/ui_generator.py --provider ollama --model llama3

# States only or screens only
python3 src/ui_generator.py --states-only
python3 src/ui_generator.py --screens-only
```

#### What it generates

```
output/ui_specs/
├── README.md              ← Index with PlantUML diagram
├── screens/               ← Real screens (ready for v0/Claude)
│   ├── 01_login.md
│   ├── 02_dashboard.md
│   ├── 03_catalog.md
│   └── ...
└── states/                ← Machine states (reference)
    ├── UI_app_idle.md
    ├── UI_success.md
    └── ...
```

#### How to use them with AI UI Generators

1. **Open** a screen file (e.g., `output/ui_specs/screens/02_dashboard.md`)
2. **Copy** all the content
3. **Paste** into your favorite AI UI generator:

| Tool | URL | What it does |
|------|-----|--------------|
| **v0.dev** | https://v0.dev | Generates React/Tailwind UI |
| **Claude Artifacts** | https://claude.ai | Generates components with logic |
| **Bolt.new** | https://bolt.new | Generates complete apps |
| **Lovable** | https://lovable.dev | Generates modern UIs |
| **Google Stitch** | https://stitch.google | Generates UIs from prompts |
| **Figma AI** | https://figma.com | Generates designs |

Each Markdown file contains:
- Screen description
- Required data with mock data
- Detailed UI components
- XState mapping (each button → event)
- UI states (loading, error, empty)
- Notes for AI generators (Tailwind, Shadcn)

### Functional Specification (spec.md)

The generated specification includes:

1. **User Flows**: textual description of all user flows
2. **State Diagram (PlantUML)**: executable state diagram
3. **XState Configuration**: JSON state machine compatible with XState
4. **Sequence Diagram (PlantUML)**: User → Interface → Backend sequence diagram
5. **Edge Cases**: table with all identified edge cases
6. **Error Handling**: error handling with HTTP codes and recovery
7. **Data Validation**: input validation rules
8. **API Contract**: API contracts generated by the LLM

### PlantUML Diagrams

The diagrams are in PlantUML format, renderable by:
- Markdown editors with PlantUML support (VS Code, IntelliJ)
- [PlantUML Web Server](http://www.plantuml.com/plantuml/uml/)
- GitHub (with PlantUML extension)

### XState State Machine

The state machine is in JSON format compatible with [XState](https://xstate.js.org/):

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

### Required LLM

The system **requires** an LLM to work. There are no simulated fallbacks.

- **Why**: the quality of the analysis depends on the LLM's ability to understand the context
- **What you need**: any LLM with OpenAI-compatible API support
- **Recommended**: models with long context window (8K+ tokens)

### Rules vs Contents

The system uses a two-level approach:

1. **Rules** (`src/rules.py`): say WHAT must be there (e.g., "there must be an authentication flow")
2. **LLM**: decides HOW it's named (e.g., "login_form → login_pending → login_success")

This allows the system to be generic and adapt to any project.

### PlantUML instead of Mermaid

The diagrams are in PlantUML because:
- Supports more complex state diagrams
- More readable syntax for state machines
- Better support for entry/exit actions
- Better rendering for sequence diagrams

### Autonomous Loop

The system iterates automatically:

1. **Analyst** generates states and transitions
2. **Spec** generates the specification with PlantUML
3. **Validator** validates that all flows are present
4. **Fuzzer** tests the state machine
5. **Critic** finds missing edge cases
6. **Loop** restarts from the weak points found

## Requirements

- Python 3.10+
- API key for an LLM provider
- 2GB RAM (for file processing)

### Optional Dependencies

To install optional dependencies (PDF, DOCX):

```bash
pip install -r requirements-optional.txt
```

| Dependency | What for | Required? |
|------------|----------|---------------|
| `pypdf` | PDF reading | No |
| `python-docx` | DOCX reading | No |
| `openai` | LLM + Vision API | **Yes** |
| `instructor` | Structured output | No |
| `beautifulsoup4` | HTML parsing | **Yes** |

## License

MIT