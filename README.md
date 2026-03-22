# Complaint Generator
### by JusticeDAO

[![Focused Claim Support Regression](https://github.com/JusticeDAO-LLC/complaint-generator/actions/workflows/claim-support-regression.yml/badge.svg)](https://github.com/JusticeDAO-LLC/complaint-generator/actions/workflows/claim-support-regression.yml)
[![Standard Regression](https://github.com/JusticeDAO-LLC/complaint-generator/actions/workflows/standard-regression.yml/badge.svg)](https://github.com/JusticeDAO-LLC/complaint-generator/actions/workflows/standard-regression.yml)
[![HACC Unit Regression](https://github.com/JusticeDAO-LLC/complaint-generator/actions/workflows/hacc-unit-regression.yml/badge.svg)](https://github.com/JusticeDAO-LLC/complaint-generator/actions/workflows/hacc-unit-regression.yml)

Regression workflows: [Manual HACC Grounding Regression](https://github.com/JusticeDAO-LLC/complaint-generator/actions/workflows/hacc-grounding-regression.yml)

An AI-powered legal automation system that assists in preparing legal complaints through intelligent question-driven intake, evidence gathering, and formal complaint generation.

---

## 🎯 What It Does

The Complaint Generator helps users create comprehensive legal complaints by:

1. **Understanding Your Situation** - Intelligent question-driven dialogue to gather facts
2. **Analyzing Legal Issues** - Automated classification of claim types and applicable laws
3. **Organizing Evidence** - Systematic evidence management with gap analysis
4. **Researching Authorities** - Multi-source legal research (statutes, regulations, case law)
5. **Generating Complaints** - Formal complaint documents meeting legal requirements

---

## ✨ Key Features

### 🔄 Three-Phase Intelligent Processing

A sophisticated workflow inspired by denoising diffusion:

- **Phase 1: Intake & Denoising** - Build knowledge and dependency graphs through iterative questioning
- **Phase 2: Evidence Gathering** - Identify and fill evidence gaps with intelligent web discovery
- **Phase 3: Formalization** - Generate formal complaints using neurosymbolic legal matching

Includes convergence detection, graph persistence, and comprehensive tests.

[Learn more →](docs/THREE_PHASE_SYSTEM.md) | [Example →](examples/three_phase_example.py)

### 📋 14 Legal Complaint Types

Comprehensive support for:
- Civil Rights (Discrimination, Housing, Employment)
- Consumer Protection, Healthcare Law
- Immigration, Family Law
- Criminal Defense, Tax Law
- Intellectual Property, Environmental Law
- Probate & Estate
- **DEI Policy Analysis** (Special focus)

Each type includes 390+ domain keywords, 90+ legal patterns, and automated decision trees.

[Complaint Analysis →](docs/COMPLAINT_ANALYSIS_INTEGRATION.md) | [DEI Analysis →](docs/HACC_INTEGRATION.md) | [Probate Integration →](docs/PROBATE_INTEGRATION.md)

### 🤖 Multi-Provider LLM Support

Flexible AI backend integration with automatic fallback:

- Codex (`gpt-5.3-codex`)
- OpenAI
- Anthropic Claude (via OpenRouter)
- Google Gemini
- GitHub Copilot
- Hugging Face local models and Hugging Face router/inference endpoints
- Codex CLI

[LLM Router Guide →](docs/LLM_ROUTER.md) | [Backends →](docs/BACKENDS.md)

### 🔍 Comprehensive Legal Research

Automated research from authoritative sources:

- **US Code** - Federal statutes
- **Federal Register** - Regulations and notices
- **RECAP Archive** - Court decisions and case law
- **Brave Search** - Current web content
- **Common Crawl** - Historical web archives

[Legal Research →](docs/LEGAL_AUTHORITY_RESEARCH.md) | [Web Evidence Discovery →](docs/WEB_EVIDENCE_DISCOVERY.md)

### 📂 Evidence Management System

Robust evidence handling with IPFS and DuckDB:

- Immutable, content-addressable storage
- Fast SQL queries for organization
- AI-powered gap analysis
- Automated web discovery

[Evidence Management →](docs/EVIDENCE_MANAGEMENT.md)

### 🎯 Adversarial Testing Framework

Quality assurance through adversarial AI:

- Complainant agents simulate diverse user personas
- Critic agents evaluate across 5 dimensions
- SGD optimization with convergence detection
- 18+ comprehensive tests

[Adversarial Testing →](docs/ADVERSARIAL_HARNESS.md)

### 📊 Claim Support Review Dashboard

Operator workflow for testimony capture, document intake, and legal sufficiency review:

- Coverage summaries and follow-up execution controls
- Manual review resolution and recent history
- Claim coverage summary, support gaps, and contradiction candidates
- Claim reasoning review and proof-readiness scoring
- Accessible at `/claim-support-review`

[Dashboard Improvement Plan →](docs/CLAIM_SUPPORT_REVIEW_DASHBOARD_IMPROVEMENT_PLAN.md) | [Execution Backlog →](docs/CLAIM_SUPPORT_REVIEW_DASHBOARD_EXECUTION_BACKLOG.md)

### 🧠 GraphRAG Ontology Optimization

Knowledge-graph-powered document analysis and reasoning:

- `OntologyGenerator` for LLM-driven entity and relationship extraction
- `QueryUnifiedOptimizer` and `WikipediaOptimizer` for corpus enrichment
- `StreamingExtractor` for high-throughput pipelines
- Pre-compiled regex patterns and entity position indexing for performance
- Statistical methods: confidence bounds, percentiles, IQR, EWMA, kurtosis

[GraphRAG API →](docs/API_REFERENCE_GRAPHRAG.md) | [Common Optimizer API →](docs/API_REFERENCE_COMMON.md) | [Agentic Optimizer API →](docs/API_REFERENCE_AGENTIC.md) | [Performance Tuning →](docs/PERFORMANCE_TUNING.md)

---

## 🚀 Quick Start

### Installation

```bash
# Clone and setup
git clone https://github.com/endomorphosis/complaint-generator.git
cd complaint-generator
git submodule update --init --recursive
pip install -r requirements.txt

# (Optional) Configure API keys
export OPENAI_API_KEY="your-key"
export BRAVE_SEARCH_API_KEY="your-key"
```

### Running

**CLI Mode (Interactive):**
```bash
python run.py --config config.llm_router.json
```

**Web Server Mode:**
```bash
# Edit config.llm_router.json: "APPLICATION": {"type": ["server"]}
python run.py --config config.llm_router.json
# Access at http://localhost:8000
```

**Review Surface Mode:**
```bash
python run.py --config config.review_surface.json
# Access the operator dashboard at http://localhost:8000/claim-support-review
# Access the formal complaint builder at http://localhost:8000/document
```

### Regression Shortcuts

**Standard Regression:**

```bash
.venv/bin/python scripts/run_standard_regression.py
```

Also available via:

- VS Code tasks `Standard Regression (Lean)`, `Standard Regression (Review)`, and `Standard Regression (Full)`
- Run and Debug entries with the same three labels
- Make targets `regression`, `regression-lean`, `regression-review`, and `regression-full`
- GitHub Actions workflow `standard-regression.yml`

The helper now defaults to the browser-inclusive `full` slice so the review, template, document, and Playwright workflow contracts stay gated together.

**Claim Support Regression:**

```bash
.venv/bin/python scripts/run_claim_support_review_regression.py
```

Also available via:

- VS Code task `Claim Support Regression` with `No Browser` and `Require Browser` variants
- GitHub Actions workflow `claim-support-regression.yml` for the focused claim-support slice

If you need to proactively normalize older claim-support testimony rows after upgrading the review workflow, run:

```bash
.venv/bin/python scripts/backfill_claim_testimony_links.py \
    --db-path statefiles/claim_support.duckdb \
    --dry-run

.venv/bin/python scripts/backfill_claim_testimony_links.py \
    --db-path statefiles/claim_support.duckdb
```

The dry run reports legacy testimony rows that can be canonically linked to registered claim elements without updating the database. The non-dry-run invocation applies those repairs in place.

**HACC Regression:**

```bash
# Lightweight HACC unit slice
.venv/bin/python scripts/run_hacc_unit_regression.py

# Grounding-focused HACC regression without the live smoke run
.venv/bin/python scripts/run_hacc_grounding_regression.py --skip-smoke
```

The lightweight slice covers the HACC evidence loader, HACC complaint synthesis, and HACC adversarial-report runner. The grounding slice adds the HACC seed-generation checks and can optionally run the heavier live smoke path.
The lightweight slice also covers adversarial session intake-prompt regressions that shape HACC-specific questioning and recovery behavior.

To inspect an existing grounded HACC run without rerunning research, upload, or synthesis, use:

```bash
.venv/bin/python scripts/show_hacc_grounded_history.py

.venv/bin/python scripts/show_hacc_grounded_history.py --list-runs

.venv/bin/python scripts/show_hacc_grounded_history.py --json

.venv/bin/python scripts/show_hacc_grounded_history.py \
    --output-dir output/hacc_grounded/<run_id>

.venv/bin/python scripts/show_hacc_grounded_history.py --output-dir previous
.venv/bin/python scripts/show_hacc_grounded_history.py --output-dir last-successful
```

That helper can first list the available grounded runs, the current alias targets, the best candidate to resume, and a ready-to-run resume command, then summarize the current grounded workflow status, recent transitions, completed grounded worksheet state, refreshed grounding state, and grounded follow-up answer summary for the selected run directory. It accepts `latest`, `previous`, and `last-successful` aliases in addition to an explicit run directory.

Example output:

```text
Output directory: output/hacc_grounded/20260322_120000
Workflow stage: post_grounded_follow_up
Recorded transitions: 2
Next action: continue_drafting (document_generation)
Completed grounded worksheet items: 3
Refreshed grounding status: chronology_supported
Grounded follow-up answers: 3
```

Also available via:

- VS Code tasks `HACC Unit Regression`, `HACC Grounding Regression`, and `HACC Grounded History`
- Run and Debug entries `HACC Unit Regression`, `HACC Grounding Regression`, `HACC Grounding Regression (No Smoke)`, and `HACC Grounded History`
- Make targets `hacc-unit`, `hacc-grounding`, `hacc-grounding-no-smoke`, and `hacc-grounded-history`
- GitHub Actions workflow `hacc-unit-regression.yml`
- Manual workflow `hacc-grounding-regression.yml`

The helper defaults to the latest run under `output/hacc_grounded`. Set the grounded run directory explicitly when using `make`:

```bash
make hacc-grounded-history HACC_GROUNDED_RUN_DIR=output/hacc_grounded/<run_id>
```

**Hugging Face Router Quick Start:**
```bash
export HF_TOKEN="your-huggingface-token"

# Optional: override the routing model or the reasoning target used by the smoke tests
export HF_ARCH_ROUTER_MODEL="katanemo/Arch-Router-1.5B"
export HF_ROUTER_ARCH_REASONING_MODEL="meta-llama/Llama-3.3-70B-Instruct"

# General server mode with Hugging Face router as the active backend.
# The shipped config now uses Arch-Router to choose between legal-reasoning and drafting models.
python run.py --config config.huggingface_router.json

# Review surface and formal complaint builder with the same auto-routing profile
python run.py --config config.review_surface.huggingface_router.json

# Optional: real network smoke test for the HF router adapter path
HF_TOKEN="$HF_TOKEN" .venv/bin/python -m pytest \
    tests/test_ipfs_llm_huggingface_router.py \
    -k live_huggingface_router_smoke \
    --run-network --run-llm

# Optional: real network smoke test through the formal complaint API path
HF_TOKEN="$HF_TOKEN" .venv/bin/python -m pytest \
    tests/test_document_pipeline.py \
    -k live_huggingface_router_optimization_smoke \
    --run-network --run-llm

# Optional: real network smoke test through the review-surface app path
HF_TOKEN="$HF_TOKEN" .venv/bin/python -m pytest \
    tests/test_document_pipeline.py \
    -k review_surface_live_huggingface_router_optimization_smoke \
    --run-network --run-llm
```

**Adversarial Autopatch (Non-Interactive):**
```bash
# Demo mode (no live LLM required)
./.venv/bin/python run.py --config config.adversarial_autopatch_demo.json

# Live mode with Hugging Face router (requires HF_TOKEN)
export HF_TOKEN="your-huggingface-token"
./.venv/bin/python run.py --config config.adversarial_autopatch_live.json

# Batch mode: 4 sessions, 2 parallel
./.venv/bin/python run.py --config config.adversarial_autopatch_live_batch.json

# Multi-backend: hf-router → codex_cli → accelerate fallback
./.venv/bin/python run.py --config config.adversarial_autopatch_live_multibackend.json
```

The demo config sets `demo_backend=true`. The live config prefers the Hugging Face router first (requires `HF_TOKEN` or `HUGGINGFACE_HUB_TOKEN`). All configs emit a summary JSON payload to stdout and write patch artifacts under `tmp/` by default. The live runner records `runtime.selected_backend_id` and `runtime.probe_attempts` in the output payload.

The formal complaint builder and `/api/documents/formal-complaint` endpoint also support affidavit-specific exhibit controls. Use `affidavit_supporting_exhibits` to provide a curated affidavit exhibit list, or set `affidavit_include_complaint_exhibits=false` when the affidavit should not inherit the complaint's exhibit list by default.

The same formal complaint payload now carries claim-level support summaries and drafting-readiness source-context counts, so the builder can show whether each count is currently grounded in evidence, authority, archived captures, or fallback-only authority references without requiring a separate dashboard round-trip.

Agentic document optimization can also use Hugging Face Inference through the same OpenAI-compatible router endpoint documented for Chat UI `llm-router`. Set `optimization_provider` to `huggingface_router`, choose a Hugging Face model in `optimization_model_name`, and pass `optimization_llm_config.base_url=https://router.huggingface.co/v1` when you need to override the default router URL. The `/document` review surface now exposes these optimization controls directly, including iteration/target tuning, routed model selection, basic router overrides, an advanced JSON editor for `optimization_llm_config`, and optional IPFS trace persistence.

If you want automatic model selection for optimization requests, include `optimization_llm_config.arch_router` with a routing model such as `katanemo/Arch-Router-1.5B` and a route map like `legal_reasoning -> meta-llama/Llama-3.3-70B-Instruct` and `drafting -> Qwen/Qwen3-Coder-480B-A35B-Instruct`.

When `enable_agentic_optimization=true`, the formal complaint response adds a top-level `document_optimization` report summarizing the post-knowledge-graph actor/mediator/critic loop. The current report shape includes the optimization method/backend, initial and final scores, accepted iteration count, optimized section names, router/IPFS status, router usage diagnostics, upstream optimizer selection, stage-level provider selection, packet projection summaries, serialized initial/final critic reviews, a compact section history, and an optional trace CID when `optimization_persist_artifacts=true`. The `/document` preview surfaces those summaries directly after each generation run, including effective provider/model, provider-source, task-complexity, and selected-route details from the critic metadata when routed LLM calls are available.

**Agentic Scraper CLI:**
```bash
python scripts/agentic_scraper_cli.py enqueue \
    --keywords employment discrimination retaliation \
    --domains eeoc.gov dol.gov \
    --iterations 3

python scripts/agentic_scraper_cli.py worker --once
python scripts/agentic_scraper_cli.py queue --user-id cli-user

python scripts/agentic_scraper_cli.py run \
    --keywords employment discrimination retaliation \
    --domains eeoc.gov dol.gov \
    --iterations 3

python scripts/agentic_scraper_cli.py history --user-id cli-user
python scripts/agentic_scraper_cli.py tactics --user-id cli-user
```

[Complete setup guide →](docs/DEPLOYMENT.md) | [Configuration →](docs/CONFIGURATION.md) | [Applications →](docs/APPLICATIONS.md)

---

## 🧭 Canary Ops (Reranker Rollout)

Use the built-in workspace tasks in `.vscode/tasks.json` for rollout monitoring:

- `Canary: Run + Export + Summarize Reranker Metrics`
- `Canary: Summarize Latest Reranker Metrics Export`
- `Canary: Generate Sample + Summarize Reranker Metrics`
- `Canary: Validate Ops Wiring (CI-safe)`

You can also run CI-safe validation directly:

```bash
python scripts/validate_canary_ops.py
```

Or use the top-level Makefile aliases:

```bash
make canary-validate
make canary-smoke
make canary-sample
```

See [Canary configuration details →](docs/CONFIGURATION.md).

---

## 📖 Usage Examples

### Basic Complaint Processing

```python
from mediator import Mediator
from backends import LLMRouterBackend

# Initialize with the router-backed Codex route
backend = LLMRouterBackend(id='llm-router', provider='codex', model='gpt-5.3-codex')
mediator = Mediator(backends=[backend])

# Process complaint
mediator.state.complaint = "I was fired after reporting safety violations..."
result = mediator.analyze_complaint_legal_issues()

print("Claim Types:", result['classification']['claim_types'])
print("Applicable Laws:", result['statutes'])
```

### Three-Phase Workflow

```python
from complaint_phases import PhaseManager

manager = PhaseManager(mediator=mediator)

# Phase 1: Intake
manager.start_three_phase_process(initial_text)
while manager.current_phase == 'denoising':
    question = manager.get_next_question()
    answer = input(question)
    manager.process_answer(question, answer)

# Phase 2 & 3: Evidence gathering and formalization
manager.advance_to_evidence_phase()
manager.discover_web_evidence()
manager.advance_to_formalization_phase()
complaint = manager.generate_formal_complaint()
```

### Export a Filing Draft

```python
draft = mediator.generate_formal_complaint(
    district='New Mexico',
    case_number='1:26-cv-____'
)

docx_result = mediator.export_formal_complaint(
    'statefiles/formal_complaint.docx',
    district='New Mexico',
    case_number='1:26-cv-____'
)

pdf_result = mediator.export_formal_complaint(
    'statefiles/formal_complaint.pdf',
    district='New Mexico',
    case_number='1:26-cv-____'
)
```

The filing draft includes a traditional court header and caption, nature of the action,
jurisdiction and venue, factual allegations, claims for relief with legal standards,
requested relief, and linked exhibits sourced from stored evidence.

[More examples →](docs/EXAMPLES.md) - 23 complete examples

---

## 🏗️ Architecture

```
User Interface (CLI/Web) → Mediator → LLM Router Backend
                              ↓
                    Complaint Phases (3-Phase)
                     ├─ Knowledge Graphs
                     ├─ Dependency Graphs
                     └─ Legal Graphs
                              ↓
        Analysis & Research (14 types, Multi-source, IPFS+DuckDB)
                              ↓
              Storage Layer (IPFS Evidence + DuckDB Metadata)
```

[Detailed architecture →](docs/ARCHITECTURE.md)

---

## 📚 Documentation

### Getting Started
- [Configuration Guide](docs/CONFIGURATION.md) - System configuration
- [Deployment Guide](docs/DEPLOYMENT.md) - Production deployment
- [Applications Guide](docs/APPLICATIONS.md) - CLI and web server
- [Security Guide](docs/SECURITY.md) - Security best practices

### Core Systems
- [Three-Phase System](docs/THREE_PHASE_SYSTEM.md) - Processing workflow
- [LLM Router](docs/LLM_ROUTER.md) - Multi-provider integration
- [Architecture](docs/ARCHITECTURE.md) - System design
- [Backends](docs/BACKENDS.md) - LLM backend configuration

### GraphRAG & Optimization APIs
- [API Reference](docs/API_REFERENCE.md) - Top-level API reference index
- [GraphRAG Optimizer API](docs/API_REFERENCE_GRAPHRAG.md) - OntologyGenerator, QueryUnifiedOptimizer, WikipediaOptimizer, StreamingExtractor
- [Common Optimizer API](docs/API_REFERENCE_COMMON.md) - BaseOptimizer, OptimizerConfig, AsyncBatchProcessor
- [Agentic Optimizer API](docs/API_REFERENCE_AGENTIC.md) - AgenticOptimizer, AgenticCLI, FeedbackLoop
- [Refinement Strategy Guide](docs/REFINEMENT_STRATEGY_GUIDE.md) - OntologyMediator refinement strategy selection
- [Optimizer Examples](docs/EXAMPLES.md) - Complete example scripts reference
- [Performance Tuning](docs/PERFORMANCE_TUNING.md) - GraphRAG pipeline optimization guide

### Claim Support & Review
- [Payload Contracts](docs/PAYLOAD_CONTRACTS.md) - Central reference for all response payloads
- [Claim Support Review Dashboard](docs/CLAIM_SUPPORT_REVIEW_DASHBOARD_IMPROVEMENT_PLAN.md) - Dashboard roadmap
- [Dashboard Execution Backlog](docs/CLAIM_SUPPORT_REVIEW_DASHBOARD_EXECUTION_BACKLOG.md) - Implementation milestones
- [Intake Evidence Plan](docs/INTAKE_EVIDENCE_IMPROVEMENT_PLAN.md) - Phase 1/2 improvement roadmap

### IPFS Datasets Py Roadmap
- [Improvement Plan](docs/IPFS_DATASETS_PY_IMPROVEMENT_PLAN.md) - Comprehensive integration plan
- [Integration Guide](docs/IPFS_DATASETS_PY_INTEGRATION.md) - Current production integration model
- [Execution Backlog](docs/IPFS_DATASETS_PY_EXECUTION_BACKLOG.md) - Workstream-by-workstream backlog
- [Batch 1 Implementation Plan](docs/IPFS_DATASETS_PY_BATCH1_IMPLEMENTATION_PLAN.md) - Issue-sized execution plan
- [Dependency Map](docs/IPFS_DATASETS_PY_DEPENDENCY_MAP.md) - Runtime dependency map
- [Capability Matrix](docs/IPFS_DATASETS_PY_CAPABILITY_MATRIX.md) - Validated module map

### Features
- [Complaint Analysis](docs/COMPLAINT_ANALYSIS_INTEGRATION.md) - 14 complaint types
- [Legal Research](docs/LEGAL_AUTHORITY_RESEARCH.md) - Multi-source research
- [Legal Analysis Hooks](docs/LEGAL_HOOKS.md) - 4-stage legal analysis pipeline (classify → statutes → requirements → questions)
- [Search & RAG Hooks](docs/SEARCH_HOOKS.md) - Legal corpus RAG and Brave search integration
- [Evidence Management](docs/EVIDENCE_MANAGEMENT.md) - IPFS and DuckDB
- [Web Evidence](docs/WEB_EVIDENCE_DISCOVERY.md) - Automated discovery
- [Adversarial Testing](docs/ADVERSARIAL_HARNESS.md) - Quality assurance
- [DEI Analysis](docs/HACC_INTEGRATION.md) - Policy analysis
- [Probate Integration](docs/PROBATE_INTEGRATION.md) - Probate & estate law

[Complete documentation index →](DOCUMENTATION_INDEX.md) - 60+ guides, 250+ pages

---

## 🧪 Testing

- **100+ Test Files** across all components
- **340+ Test Classes** organized by feature
- **Unit & Integration Tests** with pytest

```bash
pytest                          # Run all tests
pytest -m "not integration"     # Unit tests only
pytest --cov=. --cov-report=html  # With coverage
```

[Testing guide →](TESTING.md)

---

## 🔒 Security Notice

⚠️ **Before production deployment:**
- Move hardcoded JWT secret to environment variables
- Configure HTTPS with SSL certificates
- Harden authentication mechanisms
- Enhance input validation

[Security Guide →](docs/SECURITY.md) - Complete hardening checklist

---

## 📊 System Requirements

**Minimum:** Python 3.8+, 4 GB RAM, 10 GB storage
**Recommended:** Python 3.10+, 8 GB RAM, 50 GB SSD
**For Local LLMs:** 16+ GB RAM, GPU with CUDA, 100+ GB storage

---

## 🤝 Contributing

We welcome contributions! [Contributing Guidelines →](CONTRIBUTING.md)

1. Fork the repository
2. Create a feature branch
3. Write tests for changes
4. Run test suite (`pytest`)
5. Submit Pull Request

---

## 📦 Project Structure

```
complaint-generator/
├── adversarial_harness/    # Adversarial testing (complainant, critic, optimizer agents)
├── applications/           # CLI, web server, document & review API/UI
├── backends/               # LLM integrations (llm_router, huggingface, openai, workstation)
├── complaint_analysis/     # 14 complaint types with keywords, patterns, decision trees
├── complaint_phases/       # 3-phase processing (denoiser, knowledge/dependency/legal graphs)
├── docs/                   # 62 documentation files
├── examples/               # 23 usage example scripts
├── integrations/           # IPFS datasets adapter layer
├── lib/                    # Logging and shared utilities
├── mediator/               # Core orchestration, hooks, state, formal documents
├── patches/                # Adversarial autopatch output artifacts
├── scripts/                # 13 CLI and utility scripts
├── statefiles/             # DuckDB state and evidence databases
├── templates/              # Web UI (HTML/Jinja2)
├── tests/                  # 100+ test files, 340+ test classes
├── claim_support_review.py         # Claim support review data models
├── document_optimization.py        # Agentic document optimizer
├── document_pipeline.py            # Formal complaint document pipeline
├── intake_status.py                # Intake status and contradiction helpers
├── config.llm_router.json          # Main LLM router configuration
├── config.huggingface_router.json  # HF router configuration
├── config.review_surface.json      # Review surface configuration
└── run.py                          # Application entry point
```

---

## 🐛 Troubleshooting

**Submodule not initialized:**
```bash
git submodule update --init --recursive
```

**Import errors:**
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)/ipfs_datasets_py"
```

**Database locked:**
```bash
rm statefiles/*.duckdb-wal
```

---

## 📈 Project Status

✅ Core systems implemented
✅ 100+ test files, 340+ test classes passing
✅ GraphRAG ontology optimization APIs
✅ Claim Support Review Dashboard
✅ Agentic document optimization with HF router
✅ Adversarial autopatch (demo and live modes)
🚧 Web UI polish (in progress)
🚧 IPFS Datasets Py full integration (in progress)
📋 Mobile app (planned)

---

## 📬 Support

- **Issues:** https://github.com/endomorphosis/complaint-generator/issues
- **Discussions:** https://github.com/endomorphosis/complaint-generator/discussions

---

## ⚖️ Legal Disclaimer

**This system assists legal professionals but does not replace professional legal advice. Always consult with a qualified attorney for legal matters.**

The Complaint Generator helps organize information and generate documents. It does not provide legal advice, representation, or counseling. Users are responsible for reviewing all generated content for accuracy and legal compliance.

---

**Developed by JusticeDAO** | Built with [ipfs_datasets_py](https://github.com/endomorphosis/ipfs_datasets_py)
**Version 1.0** | Last Updated: 2026-03-16
