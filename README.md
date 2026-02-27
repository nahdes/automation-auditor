# 🏛 Automaton Auditor

> A hierarchical LangGraph swarm that forensically audits AI engineering repositories.
> Three detective agents collect evidence, three judge personas deliberate in parallel,
> and a deterministic Chief Justice synthesises the final verdict.

---

## Architecture

```
START → ContextBuilder
          ├── RepoInvestigator  ─┐
          ├── DocAnalyst        ─┤→ EvidenceAggregator
          └── VisionInspector   ─┘
                                    ├── Prosecutor  ─┐
                                    ├── Defense     ─┤→ ChiefJustice → ReportSaver → END
                                    └── TechLead    ─┘
```

- **Detective layer** — parallel fan-out; AST-based repo forensics, PDF analysis, diagram inspection
- **Judicial layer** — parallel fan-out; three distinct personas with `.with_structured_output()` enforcement
- **Synthesis layer** — deterministic Python rules (security override, fact supremacy, variance re-evaluation)
- **Conditional edges** — node failures are caught and logged; the graph never crashes silently

---

## Prerequisites

| Tool         | Version | Notes                                          |
| ------------ | ------- | ---------------------------------------------- |
| Python       | 3.11+   | Required by LangGraph                          |
| uv           | latest  | Fast package manager                           |
| Git          | any     | Used by RepoInvestigator for sandboxed cloning |
| Groq API key | —       | Free tier at console.groq.com                  |

---

## Setup

### 1 — Clone the repository

```bash
git clone https://github.com/nahdes/automation-auditor.git
cd automation-auditor
```

### 2 — Install uv and sync dependencies

```bash
pip install uv
uv sync
```

This reads `uv.lock` and installs all dependencies into `.venv` reproducibly.

### 3 — Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in at minimum:

```
GROQ_API_KEY=gsk_...          # from console.groq.com/keys
LANGCHAIN_API_KEY=ls-...      # from smith.langchain.com (for trace submission)
```

Full variable reference is in `.env.example`. **Never commit `.env`** — it is gitignored.

---

## Running an Audit

```bash
python -m src.graph <repo_url> <pdf_path> <audit_type>
```

| Argument     | Values                         | Description                                 |
| ------------ | ------------------------------ | ------------------------------------------- |
| `repo_url`   | any GitHub URL                 | Repository to audit                         |
| `pdf_path`   | file path                      | Accompanying PDF report (pass `""` to skip) |
| `audit_type` | `self` \| `peer` \| `received` | Controls which output folder is used        |

### Audit types

| Type       | Writes to                        | When to use                             |
| ---------- | -------------------------------- | --------------------------------------- |
| `self`     | `audit/report_onself_generated/` | Run your agent against your own repo    |
| `peer`     | `audit/report_onpeer_generated/` | Run your agent against your peer's repo |
| `received` | `audit/report_bypeer_received/`  | Save a report received from a peer      |

### Examples

```bash
# Self-audit (required submission deliverable)
python -m src.graph \
  https://github.com/nahdes/automation-auditor.git \
  reports/final_report.pdf \
  self

# Peer audit
python -m src.graph \
  https://github.com/peer/their-auditor.git \
  "" \
  peer
```

The generated Markdown report is written to the appropriate `audit/` subfolder and
also printed to stdout.

---

## Docker

```bash
# Build
docker build -t automaton-auditor .

# Self-audit, mounting the output directory so the report persists
docker run --env-file .env \
  -v $(pwd)/audit:/app/audit \
  automaton-auditor \
  https://github.com/nahdes/automation-auditor.git \
  /app/reports/final_report.pdf \
  self
```

---

## Project Structure

```
.
├── src/
│   ├── state.py              # Pydantic models + TypedDict AgentState with reducers
│   ├── graph.py              # StateGraph wiring — conditional edges, fan-out/fan-in
│   ├── config.py             # LLM provider selection (Groq / Ollama / OpenAI / Anthropic)
│   ├── nodes/
│   │   ├── detectives.py     # RepoInvestigator, DocAnalyst, VisionInspector, EvidenceAggregator
│   │   ├── judges.py         # Prosecutor, Defense, TechLead — .with_structured_output()
│   │   └── justice.py        # ChiefJustice — deterministic conflict resolution, no LLM
│   └── tools/
│       ├── repo_tools.py     # Sandboxed git clone (tempfile), AST forensics, git log
│       ├── doc_tools.py      # PDF ingestion (docling/pypdf/pdfminer), hallucination cross-ref
│       └── vision_tools.py   # Image extraction from PDF, multimodal diagram analysis
├── rubric/
│   └── week2_rubric.json     # Machine-readable constitution loaded at runtime
├── audit/
│   ├── report_onself_generated/   # Self-audit reports
│   ├── report_onpeer_generated/   # Peer audit reports
│   └── report_bypeer_received/    # Reports received from peers
├── reports/
│   └── final_report.pdf      # PDF report committed for peer agents to audit
├── pyproject.toml            # Dependencies managed by uv
├── uv.lock                   # Locked dependency tree
├── .env.example              # Environment variable template
└── Dockerfile                # Multi-stage container build
```

---

## LangSmith Tracing

With `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY` set, every audit run is
automatically traced. To retrieve your trace link:

1. Run any audit command
2. Go to [smith.langchain.com](https://smith.langchain.com)
3. Open project **automaton-auditor-week2**
4. Click the latest run → **Share** → copy the public URL

---

## Rubric

The agent evaluates 10 dimensions from `rubric/week2_rubric.json`:

| Dimension                       | Target artifact | What is checked                                                 |
| ------------------------------- | --------------- | --------------------------------------------------------------- |
| `git_forensic_analysis`         | repo            | Commit progression, timestamps, bulk-upload detection           |
| `state_management_rigor`        | repo            | Pydantic BaseModel, TypedDict, operator reducers                |
| `graph_orchestration`           | repo            | Dual fan-out/fan-in, conditional edges, EvidenceAggregator      |
| `safe_tool_engineering`         | repo            | tempfile sandboxing, no os.system(), error handling             |
| `structured_output_enforcement` | repo            | .with_structured_output(), retry on parse failure               |
| `judicial_nuance`               | repo            | Distinct persona prompts, dialectical disagreement              |
| `chief_justice_synthesis`       | repo            | Deterministic rules, dissent summaries, Markdown output         |
| `theoretical_depth`             | pdf             | Dialectical Synthesis, Fan-In/Fan-Out, Metacognition in context |
| `report_accuracy`               | pdf             | File paths cross-referenced; hallucination detection            |
| `swarm_visual`                  | pdf images      | Rendered diagram of parallel StateGraph topology                |
