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

# 2. Run the autonomous loop (LLM credentials will be prompted if not set)
python3 run.py loop-frontend --input-dir inputs/ --max-iterations 5 --time-budget 600 --generate-ui
```

### Interactive LLM Configuration

When you run `run.py`, if `LLM_API_KEY` or `LLM_PROVIDER` are not set, you'll be prompted to configure them:

```
============================================================
🤖 LLM CONFIGURATION
============================================================

This system requires an LLM API key to function.
Supported providers: OpenAI, Anthropic, Google Gemini, DashScope (Alibaba)

  🔑 LLM API Key: sk-...

  Select LLM Provider:
    [1] Openai (default model: gpt-4o)
    [2] Anthropic (default model: claude-3-5-sonnet-20241022)
    [3] Google (default model: gemini-2.5-flash)
    [4] Dashscope (default model: qwen-max)
    [5] Coding (default model: qwen3.5-plus)
    [6] Custom provider

  Your choice [1-6]: 1

  ✅ Configuration saved for this session:
     Provider: openai
     Model:    gpt-4o
     Base URL: https://api.openai.com/v1
```

### Or Set Environment Variables Manually

```bash
export LLM_API_KEY="your-key"
export LLM_PROVIDER="openai"  # or anthropic, google, dashscope, coding
```

## Running All Pipelines

The system has **three independent pipelines**: Frontend, Backend, and CI/CD.

```bash
# Set LLM credentials (or let run.py prompt you)
export LLM_API_KEY="sk-..."
export LLM_PROVIDER="coding"
export LLM_MODEL="qwen3.5-plus"
export LLM_BASE_URL="https://coding-intl.dashscope.aliyuncs.com/v1"

# 1. Frontend pipeline (iterative loop)
python3 run.py loop-frontend --input-dir inputs/ --max-iterations 5 --time-budget 600 --generate-ui

# 2. Backend pipeline
python3 run.py backend
python3 run.py backend-critic

# 3. CI/CD pipeline
python3 run.py ci-cd
```

### One-Liner (All Pipelines)

```bash
LLM_API_KEY="sk-..." LLM_PROVIDER="coding" LLM_MODEL="qwen3.5-plus" LLM_BASE_URL="https://coding-intl.dashscope.aliyuncs.com/v1" \
python3 run.py loop-frontend --input-dir inputs/ --max-iterations 5 --time-budget 600 --generate-ui \
&& python3 run.py backend \
&& python3 run.py backend-critic \
&& python3 run.py ci-cd
```

### Execution Modes

```bash
# Mode 1: Complete frontend loop with automatic ingest
python3 run.py loop-frontend --input-dir inputs/ --max-iterations 5 --time-budget 600

# Mode 2: Loop without ingest (context already exists)
python3 run.py loop-frontend --context output/context/project_context.md --max-iterations 5

# Mode 3: Ingest only
python3 run.py ingest --input-dir inputs/

# Mode 4: Individual frontend steps
python3 run.py frontend-analyst --context output/context/project_context.md
python3 run.py frontend-spec --context output/context/project_context.md
python3 run.py frontend-validator --machine output/spec/spec_machine.json
python3 run.py frontend-fuzzer --machine output/spec/spec_machine.json
python3 run.py frontend-critic --fuzz-report output/spec/fuzz_report.json

# Mode 5: Backend pipeline
python3 run.py backend --machine output/spec/spec_machine.json --context output/context/project_context.md
python3 run.py backend-critic --backend-spec output/backend/backend_spec.md --spec output/spec/spec.md --machine output/spec/spec_machine.json

# Mode 6: CI/CD pipeline
python3 run.py ci-cd --spec output/spec/spec.md --backend-spec output/backend/backend_spec.md

# Mode 7: UI Generator
python3 run.py ui-generator --machine output/spec/spec_machine.json --context output/context/project_context.md
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
│   │   ├── spec_machine.json    # XState state machine
│   │   ├── fuzz_report.json     # Fuzzer report
│   │   └── critic_report.json   # Critic feedback
│   ├── backend/
│   │   ├── backend_spec.md      # Backend functional specification
│   │   └── critic_report.json   # Backend critic report
│   ├── ci_cd/
│   │   └── ci_cd_spec.md        # CI/CD functional specification
│   ├── ui_specs/                # UI specifications for AI generators
│   │   ├── DESIGN.md            # Design system
│   │   ├── README.md            # Index with PlantUML diagram
│   │   ├── screens/             # Real screens (ready for v0/Claude)
│   │   └── states/              # Machine states (reference)
│   └── loop_checkpoints/        # Loop iteration checkpoints
│       ├── checkpoint_iter_001.json
│       └── final_report.json
├── src/
│   ├── config.py              # Multi-provider LLM configuration
│   ├── loop/                  # Autonomous loop
│   │   ├── __init__.py        # AutonomousLoop coordinator
│   │   ├── cli.py             # CLI entry point
│   │   ├── runner.py          # Pipeline step runners
│   │   └── quality.py         # Quality checker
│   ├── pipeline/              # Pipeline stages
│   │   ├── ingest/            # Context extraction
│   │   ├── frontend/          # Frontend analysis pipeline
│   │   │   ├── analyst/       # State/transition analysis
│   │   │   ├── spec/          # Specification generation
│   │   │   ├── validator/     # State machine validation
│   │   │   ├── fuzzer/        # Fuzz testing
│   │   │   └── critic/        # Critical review
│   │   ├── backend/           # Backend specification
│   │   │   ├── architect.py   # Backend architect
│   │   │   └── critic.py      # Backend critic
│   │   ├── ci_cd/             # CI/CD specification
│   │   │   └── planner.py     # CI/CD planner
│   │   └── ui_generator/      # UI spec generation
│   ├── state_machine/         # XState machine building
│   │   ├── builder.py         # Machine builder with action formatting
│   │   ├── post_processing.py # Post-processing (dedup, cleanup)
│   │   └── validation.py      # State machine validation
│   ├── diagrams/              # Diagram generation
│   │   ├── plantuml.py        # PlantUML statechart & sequence
│   │   └── markdown.py        # Markdown spec generation
│   └── llm/                   # LLM client
│       ├── client.py          # Shared LLM client wrapper
│       └── prompts.py         # LLM prompt templates
├── run.py                     # Main entry point (with interactive LLM config)
└── requirements.txt           # Python dependencies
```

## LLM Configuration

The system supports multiple LLM providers. Configure with environment variables:

| Variable | Description | Example |
|-----------|-------------|---------|
| `LLM_API_KEY` | API Key (REQUIRED) | `sk-...` |
| `LLM_PROVIDER` | Provider to use | `openai`, `anthropic`, `google`, `dashscope`, `coding` |
| `LLM_BASE_URL` | Base URL (optional, override) | `https://api.openai.com/v1` |
| `LLM_MODEL` | Model to use (optional, override) | `gpt-4o`, `claude-3-5-sonnet-20241022` |

### Supported Providers

| Provider | `LLM_PROVIDER` | Default Model |
|----------|----------------|-----------------|
| OpenAI | `openai` | `gpt-4o` |
| Anthropic | `anthropic` | `claude-3-5-sonnet-20241022` |
| Google | `google` | `gemini-2.5-flash` |
| DashScope (Alibaba) | `dashscope` | `qwen-max` |
| Coding (DashScope Plan) | `coding` | `qwen3.5-plus` |

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

# Coding (DashScope Plan - Qwen + third-party models)
export LLM_API_KEY="sk-sp-..."
export LLM_PROVIDER="coding"
export LLM_MODEL="qwen3.5-plus"
export LLM_BASE_URL="https://coding-intl.dashscope.aliyuncs.com/v1"

# Custom provider (OpenAI-compatible)
export LLM_API_KEY="your-key"
export LLM_PROVIDER="custom"
export LLM_BASE_URL="https://your-api.com/v1"
export LLM_MODEL="your-model"
```

## Output

### Design System (DESIGN.md)

The system supports the [DESIGN.md](https://github.com/google-labs-code/design.md) format from Google Labs for defining visual design tokens. This ensures consistent UI generation across all screens.

**How it works:**
- **First run**: If `DESIGN.md` doesn't exist, the LLM generates it from the project context (colors, fonts, spacing, components)
- **Subsequent runs**: The existing `DESIGN.md` is used (preserves your manual modifications)
- **Force regeneration**: Use `--force-design` to regenerate when you change the project context

```bash
# Generate DESIGN.md from context (first time)
python3 run.py loop-frontend --input-dir inputs/ --generate-ui

# Use existing DESIGN.md (preserves your changes)
python3 run.py loop-frontend --context output/context/project_context.md --generate-ui

# Force regeneration (when context changed significantly)
python3 run.py loop-frontend --context output/context/project_context.md --generate-ui --force-design
```

**DESIGN.md structure:**
```markdown
---
version: "alpha"
name: "My Design System"
colors:
  primary: "#0ea5e9"
  secondary: "#64748b"
  tertiary: "#10b981"
  neutral: "#f8fafc"
typography:
  h1:
    fontFamily: "Inter"
    fontSize: "2.25rem"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "#ffffff"
---

## Overview
Design philosophy and visual guidelines...
```

### UI Specifications (output/ui_specs/)

After generating the state machine, you can use `ui-generator` to create **Markdown Blueprints** ready to be used with AI UI generators:

```bash
# Generate all UI specs (states + screens + README)
python3 run.py ui-generator --machine output/spec/spec_machine.json --context output/context/project_context.md

# Force DESIGN.md regeneration
python3 run.py ui-generator --machine output/spec/spec_machine.json --context output/context/project_context.md --force-design
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
  "initial": "app_idle",
  "context": {"user": null, "errors": [], "retryCount": 0, "previousState": null},
  "states": {
    "app_idle": {
      "entry": ["initializeApp"],
      "on": {
        "START": "loading"
      }
    },
    "loading": {
      "entry": ["showLoadingIndicator", "start_timeout_timer"],
      "exit": ["stop_timeout_timer"],
      "on": {
        "ON_SUCCESS": {
          "target": "success",
          "cond": "hasData",
          "actions": [{"type": "assign", "assignment": {"retryCount": 0}}]
        },
        "ON_SUCCESS": "empty",
        "ON_ERROR": "error"
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

**Stop criteria:**
- Quality Score 100/100 (perfect machine)
- Quality Score ≥ 90 AND 0 critical issues (sufficient quality)
- Convergence: Quality Score doesn't improve for 2 consecutive iterations
- Max iterations reached
- Timeout reached

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