# Autoresearch - Automatic Functional Analysis

> **The concept**: give an AI a project (notes, screenshots, HTML) and let it autonomously generate the complete functional specification with diagrams, edge cases, and executable state machines.

The idea is inspired by Andrej Karpathy's [autoresearch](https://github.com/karpathy/autoresearch) project, but applied to Product Management instead of LLM model training.

## 🆕 Latest: Journey-Centric Architecture with Parallel States

The system now supports **Journey-Centric** state machine architecture with **Parallel States** (XState v5). Instead of just modeling pages, it now models **user journeys** (workflows) that span multiple screens while maintaining persistent state.

### What's New

- **Parallel States Architecture**: Root state machine uses `type: "parallel"` with two branches:
  - `navigation`: tracks which page the user is on
  - `active_workflows`: tracks which workflow is currently active
- **Workflow Compound States**: Multi-step processes (benchmark, purchase groups, price alerts) are now first-class citizens with internal micro-states
- **LLM Wiki Generator**: Creates a "Memory Bank" for AI coding agents (Tech Rules, Domain Glossary, Architecture Map)
- **Security Pipeline**: Automated security analysis (OWASP Top 10, data protection, auth security)
- **Enhanced Analyst**: Now identifies workflows from verbs of action (partecipare, confrontare, monitorare)

## 🛡️ Deterministic Validation Layer

> **The problem**: LLMs generate structurally invalid state machines — duplicate states, orphan transitions, dead ends. Asking an LLM to "be careful" doesn't work.

> **The solution**: A deterministic Python validator that checks the JSON structure and assigns a Quality Score. **No LLM needed.**

### JSON Structural Validator (`json_validator.py`)

A 315-line Python script that validates the state machine structure:

| Check | Description | Severity |
|-------|-------------|----------|
| **Duplicate States** | States appearing in multiple locations (e.g., `dashboard` under both `navigation.*` and at root) | Critical |
| **Orphan Transitions** | Transitions pointing to non-existent states | Critical |
| **Dead-End States** | States with no outgoing transitions (except terminal states) | High |
| **Unreachable States** | States not reachable from `app_idle` | High |
| **Missing Entry/Exit** | States without entry/exit action arrays | Medium |
| **Missing `on` Property** | States without transition map | Medium |

### Quality Score Formula

$$S = 100 - \sum (w_{critical} \cdot C + w_{high} \cdot H + w_{medium} \cdot M)$$

Where:
- $w_{critical} = 10$ (each critical issue costs 10 points)
- $w_{high} = 5$ (each high issue costs 5 points)
- $w_{medium} = 2$ (each medium issue costs 2 points)

**Stop criteria**: The loop continues until $S \geq 90$ OR $S = 100$.

### First Run Results

Against the existing `spec_machine.json` (before fixes):
- **47 total issues found**
- 12 Critical (6 duplicate states, 6 orphan transitions)
- 12 High (4 dead-end states, 8 unreachable states)
- 23 Medium (missing properties)
- **Quality Score: 0/100** → Loop forced to iterate

### Usage

```bash
# Standalone validation
python3 -m state_machine.json_validator output/spec/spec_machine.json

# Integrated in the loop (automatic)
python3 run.py loop-frontend --input-dir inputs/ --max-iterations 5
```

### Output Example

```
⚖️  JSON Structural Validation Report
═══════════════════════════════════════
File: output/spec/spec_machine.json

📊 Quality Score: 72/100

🔴 Critical Issues (3):
  1. DUPLICATE_STATE: 'dashboard' appears at root and under navigation.success
  2. DUPLICATE_STATE: 'catalog' appears at root and under navigation.success
  3. ORPHAN_TRANSITION: 'app_idle' → 'nonexistent_state' (event: NAVIGATE)

🟡 High Issues (2):
  1. DEAD_END: 'error' has no outgoing transitions
  2. UNREACHABLE: 'benchmark' not reachable from 'app_idle'

🟢 Medium Issues (5):
  1. MISSING_PROPERTY: 'loading' missing 'entry' array
  ...

✅ VALID (score ≥ 90) — proceed to task generation
```

## 🔧 Deterministic Build Layer

> **The problem**: The LLM generates states with inconsistent naming — `dashboard`, `success.dashboard`, `#navigation.success.dashboard` all referring to the same state.

> **The solution**: A deterministic builder that resolves all targets to canonical paths.

### Path Resolution (`_resolve_state_target()`)

| Input Target | Resolved To | Reason |
|-------------|-------------|--------|
| `dashboard` | `navigation.success.dashboard` | Sibling resolution within navigation branch |
| `.dashboard` | `navigation.success.dashboard` | Relative resolution from parent |
| `#navigation.success.dashboard` | `navigation.success.dashboard` | Cross-branch reference (already canonical) |
| `success` | `navigation.success` | Root-level resolution |

### State Deduplication (`deduplicate_machine()`)

Removes duplicate states that appear in multiple locations:
- **Before**: `dashboard` exists at root, under `navigation.*`, AND under `navigation.success.*`
- **After**: `dashboard` exists ONLY under `navigation.success.*` (canonical location)

### Compound State Fix

Parallel branch compound states now include `"on": {}` in the base machine, preventing XState v5 validation errors.

## 🎨 Design System & Mock Data

> **The problem**: UI specs use "Mad Libs" placeholders (`{{colors.surface}}`) and hardcoded mock data that doesn't change per project.

> **The solution**: Deterministic JSON files that provide real values.

### Design System (`inputs/design_system.json`)

Complete design token system:

```json
{
  "colors": {
    "primary": "#2563EB",
    "surface": "#FFFFFF",
    "text_primary": "#111827"
  },
  "typography": {
    "font_family_primary": "Inter, -apple-system, sans-serif",
    "font_size_base": "1rem"
  },
  "spacing": { "xs": "0.25rem", "sm": "0.5rem", "md": "1rem" },
  "border_radius": { "sm": "0.25rem", "md": "0.375rem", "lg": "0.5rem" },
  "shadows": { "sm": "0 1px 2px rgba(0,0,0,0.05)", "md": "0 4px 6px rgba(0,0,0,0.1)" }
}
```

**Usage in UI specs:**
- Before: `backgroundColor: {{colors.surface}}` (Mad Libs — guess the value)
- After: `backgroundColor: #FFFFFF` (deterministic — exact value)

### Mock Data (`inputs/mock_data.json`)

Project-specific mock data:

```json
{
  "project_context": { "name": "Clinical Hub", "domain": "veterinary_pharma" },
  "users": {
    "sales_rep": { "name": "Marco Rossi", "role": "sales_rep" }
  },
  "products": [
    { "name": "Bravecto", "price_euro": 45.90, "stock_status": "available" }
  ],
  "dashboard_metrics": {
    "total_revenue_euro": 125430,
    "active_customers": 47
  }
}
```

**Benefits:**
- Data changes per project (not hardcoded in prompts)
- Realistic values for AI UI generators
- Consistent across all generated specs

## How It Works

1. **Input**: text files, notes, screenshots, HTML from UIs
2. **Ingest**: extracts context from raw material
3. **Analyst**: the LLM analyzes and generates states, transitions, edge cases, **and workflows**
4. **Spec**: generates functional specification with PlantUML diagrams and XState state machine (parallel architecture)
5. **Validator**: validates that all critical flows are present (logic checks)
6. **JSON Validator**: validates machine structure (deterministic, no LLM) ← **NEW**
7. **Fuzzer**: tests the state machine with random paths
8. **Critic**: hostile reviewer (finds missing edge cases)
9. **Loop**: the system iterates automatically improving the specification
10. **UI Generator**: creates Markdown blueprints for AI UI generators (uses design_system.json) ← **ENHANCED**
11. **LLM Wiki Generator**: creates Memory Bank for AI coding agents
12. **Security Pipeline**: analyzes security requirements
13. **Backend Pipeline**: generates backend specification
14. **CI/CD Pipeline**: generates CI/CD specification
15. **Testbook Generator**: generates test scenarios from XState machine (deterministic, no LLM needed)

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

The system has **four independent pipelines**: Frontend, Backend, CI/CD, and Security.

```bash
# Set LLM credentials (or let run.py prompt you)
export LLM_API_KEY="sk-..."
export LLM_PROVIDER="coding"
export LLM_MODEL="qwen3.5-plus"
export LLM_BASE_URL="https://coding-intl.dashscope.aliyuncs.com/v1"

# 1. Frontend pipeline (iterative loop with deterministic validation)
python3 run.py loop-frontend --input-dir inputs/ --max-iterations 5 --time-budget 600 --generate-ui

# 2. Backend pipeline
python3 run.py backend
python3 run.py backend-critic

# 3. CI/CD pipeline
python3 run.py ci-cd

# 4. Security pipeline
python3 run.py security

# 5. LLM Wiki Generator (creates Memory Bank for AI agents)
python3 run.py wiki-generator

# 6. Testbook Generator (generates test scenarios from XState)
python3 run.py testbook-generator
```

### One-Liner (All Pipelines)

```bash
LLM_API_KEY="sk-..." LLM_PROVIDER="coding" LLM_MODEL="qwen3.5-plus" LLM_BASE_URL="https://coding-intl.dashscope.aliyuncs.com/v1" \
python3 run.py loop-frontend --input-dir inputs/ --max-iterations 5 --time-budget 600 --generate-ui \
&& python3 run.py backend \
&& python3 run.py backend-critic \
&& python3 run.py ci-cd \
&& python3 run.py security \
&& python3 run.py wiki-generator
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

# Mode 8: Security Pipeline
python3 run.py security --spec output/spec/spec.md --backend-spec output/backend/backend_spec.md

# Mode 9: LLM Wiki Generator
python3 run.py wiki-generator --context output/context/project_context.md

# Mode 10: Testbook Generator (deterministic, no LLM needed)
python3 run.py testbook-generator --machine output/spec/spec_machine.json

# Mode 11: JSON Structural Validator (standalone, deterministic)
python3 -m state_machine.json_validator output/spec/spec_machine.json
```

## Project Structure

```
autoresearch/
├── inputs/              # Your input files (text, notes, HTML)
│   ├── design_system.json   # Design tokens (colors, typography, spacing) ← NEW
│   └── mock_data.json       # Project-specific mock data ← NEW
├── output/              # Automatically generated files
│   ├── context/
│   │   └── project_context.md   # Extracted context
│   ├── analyst/
│   │   └── analyst_suggestions.json  # LLM analysis (includes workflows)
│   ├── spec/
│   │   ├── spec.md              # Functional specification with PlantUML
│   │   ├── spec_machine.json    # XState state machine (parallel architecture)
│   │   ├── fuzz_report.json     # Fuzzer report
│   │   └── critic_report.json   # Critic feedback
│   ├── backend/
│   │   ├── backend_spec.md      # Backend functional specification
│   │   └── critic_report.json   # Backend critic report
│   ├── ci_cd/
│   │   └── ci_cd_spec.md        # CI/CD functional specification
│   ├── security/
│   │   └── security_spec.md     # Security analysis (OWASP Top 10)
│   ├── ui_specs/                # UI specifications for AI generators
│   │   ├── DESIGN.md            # Design system
│   │   ├── README.md            # Index with PlantUML diagram
│   │   ├── screens/             # Real screens (ready for v0/Claude)
│   │   └── states/              # Machine states (reference)
│   ├── llm_wiki/                # Memory Bank for AI coding agents
│   │   ├── @TECH_RULES.md       # Tech stack, architecture, absolute rules
│   │   ├── @DOMAIN_GLOSSARY.md  # Domain terminology (Clinic, Smart Group, etc.)
│   │   ├── @ARCHITECTURE_MAP.md # Directory structure rules
│   │   ├── @SECURITY_RULES.md   # Security requirements
│   │   ├── project_index.md     # Project index (where to find everything)
│   │   └── active_context.md    # Development log (updated by AI agent)
│   ├── testbook/                # Test scenarios from XState machine
│   │   └── system_tests.md      # Testbook with scenarios per workflow
│   └── loop_checkpoints/        # Loop iteration checkpoints
│       ├── checkpoint_iter_001.json
│       └── final_report.json
├── src/
│   ├── config.py              # Multi-provider LLM configuration
│   ├── loop/                  # Autonomous loop
│   │   ├── __init__.py        # AutonomousLoop coordinator
│   │   ├── cli.py             # CLI entry point
│   │   ├── runner.py          # Pipeline step runners (includes JSON validator) ← ENHANCED
│   │   └── quality.py         # Quality checker
│   ├── pipeline/              # Pipeline stages
│   │   ├── ingest/            # Context extraction
│   │   ├── frontend/          # Frontend analysis pipeline
│   │   │   ├── analyst/       # State/transition/workflow analysis
│   │   │   ├── spec/          # Specification generation (parallel states)
│   │   │   ├── validator/     # State machine validation
│   │   │   ├── fuzzer/        # Fuzz testing
│   │   │   └── critic/        # Critical review
│   │   ├── backend/           # Backend specification
│   │   │   ├── architect.py   # Backend architect
│   │   │   └── critic.py      # Backend critic
│   │   ├── ci_cd/             # CI/CD specification
│   │   │   └── planner.py     # CI/CD planner
│   │   ├── ui_generator/      # UI spec generation
│   │   ├── security/          # Security analysis
│   │   │   ├── auditor.py     # Security auditor (OWASP Top 10)
│   │   │   └── __main__.py    # CLI entry point
│   │   └── wiki_generator/    # LLM Wiki / Memory Bank generator
│   │       ├── wiki_generator.py  # Generates Tech Rules, Glossary, Index
│   │       └── __main__.py    # CLI entry point
│   │   └── testbook_generator/  # Testbook generation (deterministic)
│   │       ├── engine.py        # Core engine (coverage, invariants, scenarios)
│   │       ├── __init__.py      # CLI entry point
│   │       └── __main__.py      # Module support
│   ├── state_machine/         # XState machine building ← ENHANCED
│   │   ├── builder.py         # Machine builder (parallel states, workflows, dedup) ← REFACTORED
│   │   ├── json_validator.py  # Deterministic structural validator ← NEW
│   │   ├── __main__.py        # Module entry point for json_validator ← NEW
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

## 🆕 Journey-Centric Architecture

### From Page-Centric to Journey-Centric

Traditional state machines model **pages** (login, dashboard, catalog). Our system now models **journeys** (benchmark comparison, purchase group participation, price alert setup) that span multiple pages while maintaining persistent state.

### Parallel States Architecture

The root state machine uses `type: "parallel"` with two independent branches:

```json
{
  "id": "appFlow",
  "type": "parallel",
  "states": {
    "navigation": {
      "initial": "app_idle",
      "states": {
        "app_idle": { "on": { "START_APP": "authenticating" } },
        "authenticating": { "on": { "ON_SUCCESS": "success", "ON_ERROR": "error" } },
        "loading": { "on": { "ON_SUCCESS": "success", "ON_ERROR": "error" } },
        "success": {
          "initial": "dashboard",
          "states": {
            "dashboard": { "on": { "NAVIGATE_CATALOG": "catalog", "VIEW_BENCHMARK": "#active_workflows.benchmark_workflow.discovery" } },
            "catalog": { "on": { "NAVIGATE_DASHBOARD": "dashboard", "VIEW_BENCHMARK": "#active_workflows.benchmark_workflow.discovery" } }
          }
        },
        "error": { "on": { "RETRY_FETCH": "loading", "CANCEL": "app_idle" } }
      }
    },
    "active_workflows": {
      "initial": "none",
      "states": {
        "none": {},
        "benchmark_workflow": {
          "initial": "discovery",
          "states": {
            "discovery": {
              "entry": ["showBenchmarkOverlay"],
              "on": { "VIEW_DETAILS": "viewing", "GO_BACK": "none" }
            },
            "viewing": {
              "entry": ["showPriceComparison"],
              "on": { "JOIN_GROUP": "joining", "GO_BACK": "discovery" }
            },
            "joining": {
              "entry": ["showJoinConfirmation"],
              "on": { "CONFIRM_JOIN": "tracking", "CANCEL": "viewing" }
            },
            "tracking": {
              "entry": ["showGroupProgress"],
              "on": { "GROUP_COMPLETE": "none", "GO_BACK": "discovery" }
            }
          },
          "on": {
            "NAVIGATE_DASHBOARD": "#navigation.success.dashboard",
            "NAVIGATE_CATALOG": "#navigation.success.catalog"
          }
        }
      }
    }
  }
}
```

### Key Benefits

1. **Persistent State**: Workflow remains active even if user navigates to different page
2. **Context-Aware UI**: AI agent (Cline/Claude) knows which workflow is active and shows appropriate UI
3. **Scalability**: New workflows added under `active_workflows` without breaking navigation
4. **Mandatory Completion**: Every workflow has a completion event (COMPLETED, CANCELLED, DISMISSED) → "none"
5. **Cross-Page Navigation**: Workflows can navigate to pages using `#navigation.` prefix

### Workflow Identification

The Analyst now identifies workflows from the input context by looking for:

- **Verbs of Action**: partecipare, confrontare, ricevere, unirsi, monitorare, vedere, scoprire
- **Multi-Step Processes**: anything that spans multiple screens
- **User Journeys**: "voglio vedere se risparmio" → benchmark_workflow
- **Domain Concepts**: "gruppi d'acquisto" → purchase_group_workflow, "alert prezzi" → price_alert_workflow

## LLM Wiki (Memory Bank for AI Agents)

The LLM Wiki is a **persistent, structured knowledge base** that AI coding agents (Cline, Claude Code) read before writing code. It prevents context window pollution and ensures consistent architecture decisions.

### Generated Files

| File | Purpose |
|------|---------|
| `@TECH_RULES.md` | Tech stack, architecture rules, absolute prohibitions (❌ NO Redux, ❌ NO MUI) |
| `@DOMAIN_GLOSSARY.md` | Domain terminology mapping (Clinic → ClinicProfile, Smart Group → PurchaseGroup) |
| `@ARCHITECTURE_MAP.md` | Directory structure rules (where to save files) |
| `@SECURITY_RULES.md` | Security requirements (OWASP Top 10, data protection) |
| `project_index.md` | Project index (where to find every generated file) |
| `active_context.md` | Development log (updated by AI agent after each task) |

### How AI Agents Use It

When Cline opens a Kanban task, it reads:

```
📚 Context Links (Read before coding):
- output/llm_wiki/@TECH_RULES.md
- output/llm_wiki/@DOMAIN_GLOSSARY.md
- output/llm_wiki/project_index.md
- output/ui_specs/screens/01_login.md
```

This gives the agent **all the context it needs** without reading 50,000 tokens of analysis documents.

### Generation

```bash
# Generate LLM Wiki from project context
python3 run.py wiki-generator --context output/context/project_context.md
```

### Complete Pipeline Flow

The full pipeline from raw inputs to AI-ready development tasks:

```
inputs/ (PDF, notes, HTML)
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  STEP 1: Frontend Loop (with Deterministic Validation)  │
│  python3 run.py loop-frontend --input-dir inputs/       │
│                                                         │
│  ingest → analyst → spec → validator → json_validator   │
│    → fuzzer → critic (iterates until S ≥ 90)            │
│                                                         │
│  Output: output/spec/spec_machine.json (validated)      │
│          output/spec/spec.md                            │
│          output/context/project_context.md              │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  STEP 2: UI Generator (uses design_system.json)         │
│  python3 run.py ui-generator                            │
│                                                         │
│  Output: output/ui_specs/DESIGN.md                      │
│          output/ui_specs/screens/*.md                   │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  STEP 3: Backend + CI/CD + Security (parallel)          │
│  python3 run.py backend && python3 run.py ci-cd         │
│  python3 run.py security                                │
│                                                         │
│  Output: output/backend/backend_spec.md                 │
│          output/ci_cd/ci_cd_spec.md                     │
│          output/security/security_spec.md               │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  STEP 4: LLM Wiki Generator (The "Brain")               │
│  python3 run.py wiki-generator                          │
│                                                         │
│  Output: output/llm_wiki/@TECH_RULES.md                 │
│          output/llm_wiki/@DOMAIN_GLOSSARY.md            │
│          output/llm_wiki/@SECURITY_RULES.md             │
│          output/llm_wiki/project_index.md               │
│          output/llm_wiki/active_context.md              │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  STEP 5: Testbook Generator (The "QA Auditor")          │
│  python3 run.py testbook-generator                      │
│                                                         │
│  Deterministic analysis of XState machine:              │
│  - State Coverage Audit (reachable/unreachable states)  │
│  - Global Invariants (CANCEL→none, completion paths)    │
│  - Test Scenarios (happy path, cancel, back per state)  │
│                                                         │
│  Output: output/testbook/system_tests.md                │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  STEP 6: Kanban Task Generator                          │
│  python3 run.py kanban-task                             │
│                                                         │
│  Each task includes wiki file references:               │
│  - output/llm_wiki/@TECH_RULES.md                       │
│  - output/llm_wiki/project_index.md                     │
│                                                         │
│  Output: output/kanban_tasks/MASTER_PLAN.md             │
│          output/kanban_tasks/TASK-01-*.md               │
│          output/kanban_tasks/TASK-02-*.md               │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  STEP 7: AI Agent Execution (Cline / Claude Code)       │
│                                                         │
│  Prompt: "Read MASTER_PLAN.md, pick first task,        │
│  read wiki files, write code, update active_context.md" │
│                                                         │
│  The agent reads the LLM Wiki before every task,        │
│  ensuring consistent architecture decisions.            │
└─────────────────────────────────────────────────────────┘
```

### One-Liner (Complete Pipeline)

```bash
# Full pipeline from inputs to Kanban tasks
python3 run.py loop-frontend --input-dir inputs/ --max-iterations 5 --generate-ui \
&& python3 run.py backend \
&& python3 run.py ci-cd \
&& python3 run.py security \
&& python3 run.py wiki-generator \
&& python3 run.py testbook-generator \
&& python3 run.py kanban-task
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
2. **State Diagram (PlantUML)**: executable state diagram (parallel architecture)
3. **XState Configuration**: JSON state machine compatible with XState v5
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
  "type": "parallel",
  "context": {"user": null, "errors": [], "retryCount": 0, "previousState": null},
  "states": {
    "navigation": {
      "initial": "app_idle",
      "states": {
        "app_idle": {
          "on": { "START_APP": "authenticating" }
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
    },
    "active_workflows": {
      "initial": "none",
      "states": {
        "none": {},
        "benchmark_workflow": {
          "initial": "discovery",
          "states": {
            "discovery": {
              "entry": ["showBenchmarkOverlay"],
              "on": { "VIEW_DETAILS": "viewing", "GO_BACK": "none" }
            }
          }
        }
      }
    }
  }
}
```

## Security Pipeline

The security pipeline analyzes the functional specification and generates a comprehensive security report based on OWASP Top 10 and domain-specific requirements.

```bash
# Run security analysis
python3 run.py security --spec output/spec/spec.md --backend-spec output/backend/backend_spec.md
```

### Security Categories

| Category | Description |
|----------|-------------|
| **Authentication & Authorization** | JWT, session management, role-based access |
| **Data Protection** | GDPR compliance, data encryption, retention policies |
| **API Security** | Rate limiting, input validation, CORS |
| **Infrastructure** | HTTPS, security headers, dependency scanning |
| **Business Logic** | Benchmark manipulation, group fraud, price tampering |

### Output

```
output/security/
└── security_spec.md     # Security analysis with risk levels
```

## Design Choices

### Required LLM

The system **requires** an LLM to work. There are no simulated fallbacks.

- **Why**: the quality of the analysis depends on the LLM's ability to understand the context
- **What you need**: any LLM with OpenAI-compatible API support
- **Recommended**: models with long context window (8K+ tokens)

### Rules vs Contents

The system uses a two-level approach:

1. **Rules** (embedded in prompts): say WHAT must be there (e.g., "there must be an authentication flow")
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

1. **Analyst** generates states, transitions, and workflows
2. **Spec** generates the specification with PlantUML (parallel architecture)
3. **Validator** validates that all flows are present (logic checks)
4. **JSON Validator** validates machine structure (deterministic) ← **NEW**
5. **Fuzzer** tests the state machine
6. **Critic** finds missing edge cases
7. **Loop** restarts from the weak points found

**Stop criteria:**
- Quality Score 100/100 (perfect machine)
- Quality Score ≥ 90 AND 0 critical issues (sufficient quality)
- Convergence: Quality Score doesn't improve for 2 consecutive iterations
- Max iterations reached
- Timeout reached

### Journey-Centric vs Page-Centric

| Aspect | Page-Centric (Old) | Journey-Centric (New) |
|--------|-------------------|----------------------|
| Root structure | Flat states | Parallel states (navigation + workflows) |
| Multi-step flows | Scattered across pages | Encapsulated in compound states |
| State persistence | Lost on navigation | Maintained across page changes |
| AI agent context | Must read all specs | Reads LLM Wiki (condensed) |
| Scalability | Linear growth | Modular workflow addition |
| Structural validation | LLM-based (unreliable) | Deterministic Python (guaranteed) |

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