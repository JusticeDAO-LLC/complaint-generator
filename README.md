# Complaint Generator
### by JusticeDAO

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

Includes convergence detection, graph persistence, and 33 comprehensive tests.

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

[Complaint Analysis →](docs/COMPLAINT_ANALYSIS_INTEGRATION.md) | [DEI Analysis →](docs/HACC_INTEGRATION.md)

### 🤖 Multi-Provider LLM Support

Flexible AI backend integration with automatic fallback:

- OpenAI (GPT-4, GPT-3.5)
- Anthropic Claude (via OpenRouter)
- Google Gemini
- GitHub Copilot
- Hugging Face local models and Hugging Face router/inference endpoints

[LLM Router Guide →](docs/LLM_ROUTER.md)

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

The formal complaint builder and `/api/documents/formal-complaint` endpoint also support affidavit-specific exhibit controls. Use `affidavit_supporting_exhibits` to provide a curated affidavit exhibit list, or set `affidavit_include_complaint_exhibits=false` when the affidavit should not inherit the complaint's exhibit list by default.

The same formal complaint payload now carries claim-level support summaries and drafting-readiness source-context counts, so the builder can show whether each count is currently grounded in evidence, authority, archived captures, or fallback-only authority references without requiring a separate dashboard round-trip.

Agentic document optimization can also use Hugging Face Inference through the same OpenAI-compatible router endpoint documented for Chat UI `llm-router`. Set `optimization_provider` to `huggingface_router`, choose a Hugging Face model in `optimization_model_name`, and pass `optimization_llm_config.base_url=https://router.huggingface.co/v1` when you need to override the default router URL. The `/document` review surface now exposes these optimization controls directly, including iteration/target tuning, routed model selection, basic router overrides, an advanced JSON editor for `optimization_llm_config`, and optional IPFS trace persistence.

If you want automatic model selection for optimization requests, include `optimization_llm_config.arch_router` with a routing model such as `katanemo/Arch-Router-1.5B` and a route map like `legal_reasoning -> meta-llama/Llama-3.3-70B-Instruct` and `drafting -> Qwen/Qwen3-Coder-480B-A35B-Instruct`.

When `enable_agentic_optimization=true`, the formal complaint response adds a top-level `document_optimization` report summarizing the post-knowledge-graph actor/mediator/critic loop. The current report shape includes the optimization method/backend, initial and final scores, accepted iteration count, optimized section names, router/IPFS status, a compact section history, and an optional trace CID when `optimization_persist_artifacts=true`.

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

## 📖 Usage Examples

### Basic Complaint Processing

```python
from mediator import Mediator
from backends import LLMRouterBackend

# Initialize
backend = LLMRouterBackend(id='llm-router', provider='copilot_cli', model='gpt-4')
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

[More examples →](docs/EXAMPLES.md) - 21 complete examples

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

### IPFS Datasets Py Roadmap
- [Improvement Plan](docs/IPFS_DATASETS_PY_IMPROVEMENT_PLAN.md) - Comprehensive integration plan for legal scrapers, legal dataset search, graph databases, theorem provers, web archiving, search engines, and information organization
- [Integration Guide](docs/IPFS_DATASETS_PY_INTEGRATION.md) - Current production integration model and adapter boundary
- [Execution Backlog](docs/IPFS_DATASETS_PY_EXECUTION_BACKLOG.md) - Workstream-by-workstream implementation backlog and sequencing
- [Batch 1 Implementation Plan](docs/IPFS_DATASETS_PY_BATCH1_IMPLEMENTATION_PLAN.md) - Issue-sized execution plan for adapter contract stabilization, capability reporting, and import-boundary cleanup

### Features
- [Complaint Analysis](docs/COMPLAINT_ANALYSIS_INTEGRATION.md) - 14 complaint types
- [Legal Research](docs/LEGAL_AUTHORITY_RESEARCH.md) - Multi-source research
- [Evidence Management](docs/EVIDENCE_MANAGEMENT.md) - IPFS and DuckDB
- [Web Evidence](docs/WEB_EVIDENCE_DISCOVERY.md) - Automated discovery
- [Adversarial Testing](docs/ADVERSARIAL_HARNESS.md) - Quality assurance
- [DEI Analysis](docs/HACC_INTEGRATION.md) - Policy analysis

[Complete documentation index →](DOCUMENTATION_INDEX.md) - 42+ guides, 250+ pages

---

## 🧪 Testing

- **150+ Tests** across all components
- **60+ Test Classes** organized by feature
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
├── adversarial_harness/    # Adversarial testing
├── applications/            # CLI and web server
├── backends/                # LLM integrations
├── complaint_analysis/      # 14 complaint types
├── complaint_phases/        # 3-phase processing
├── docs/                    # 32 documentation files
├── examples/                # 21 usage examples
├── mediator/                # Core orchestration
├── templates/               # Web UI
├── tests/                   # 150+ tests
└── config.llm_router.json   # Configuration
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
✅ 150+ tests passing  
🚧 Web UI polish (in progress)  
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
**Version 1.0** | Last Updated: 2026-02-10
