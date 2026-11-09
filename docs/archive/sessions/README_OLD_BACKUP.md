# Complaint Generator
### by JusticeDAO

![Complaint Generator Overview](https://user-images.githubusercontent.com/13929820/159738867-25593733-fc54-4683-abc7-a0703ce7d4a7.svg)

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

A sophisticated workflow that mirrors how legal professionals work:

- **Phase 1: Intake & Denoising** - Build knowledge and dependency graphs through iterative questioning
- **Phase 2: Evidence Gathering** - Identify and fill evidence gaps with intelligent web discovery
- **Phase 3: Formalization** - Generate formal complaints using neurosymbolic legal matching

[Learn more →](docs/THREE_PHASE_SYSTEM.md)

### 📋 14 Legal Complaint Types

Comprehensive support for diverse legal matters:

- Civil Rights (Discrimination, Housing, Employment)
- Consumer Protection
- Healthcare Law
- Immigration
- Family Law
- Criminal Defense
- Tax Law
- Intellectual Property
- Environmental Law
- Probate & Estate

Each type includes domain-specific keywords, legal patterns, and decision trees.

[Learn more →](docs/COMPLAINT_ANALYSIS_INTEGRATION.md)

### 🤖 Multi-Provider LLM Support

Flexible AI backend integration:

- **OpenAI** (GPT-4, GPT-3.5)
- **Anthropic Claude** (via OpenRouter)
- **Google Gemini**
- **GitHub Copilot**
- **HuggingFace Models**
- Automatic fallback between providers

[Learn more →](docs/LLM_ROUTER.md)

### 🔍 Comprehensive Legal Research

Automated research from authoritative sources:

- **US Code** - Federal statutes
- **Federal Register** - Regulations and notices  
- **RECAP Archive** - Court decisions and case law
- **Brave Search** - Current web content
- **Common Crawl** - Historical web archives

[Learn more →](docs/LEGAL_AUTHORITY_RESEARCH.md)

### 📂 Evidence Management System

Robust evidence handling:

- **IPFS Storage** - Immutable, content-addressable evidence storage
- **DuckDB Metadata** - Fast SQL queries for evidence organization
- **Gap Analysis** - AI-powered identification of missing evidence
- **Web Discovery** - Automated evidence discovery from online sources

[Learn more →](docs/EVIDENCE_MANAGEMENT.md)

### 🎯 Adversarial Testing Framework

Quality assurance through adversarial AI:

- **Complainant Agents** - Simulate diverse user personas
- **Critic Agents** - Evaluate quality across 5 dimensions
- **SGD Optimization** - Continuous improvement cycles
- **18+ Comprehensive Tests**

[Learn more →](docs/ADVERSARIAL_HARNESS.md)

### 📊 DEI Policy Analysis

Specialized analysis for Diversity, Equity, and Inclusion policies:

- Risk scoring (0-3 scale)
- Provision extraction with binding vs. aspirational detection
- Executive summaries and technical reports
- 100+ keywords across 9 applicability domains

[Learn more →](docs/HACC_INTEGRATION.md)

---

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- Git
- (Optional) API keys for LLM providers

### Installation

```bash
# Clone the repository
git clone https://github.com/endomorphosis/complaint-generator.git
cd complaint-generator

# Initialize submodules
git submodule update --init --recursive

# Install dependencies
pip install -r requirements.txt

# (Optional) Set up environment variables
export OPENAI_API_KEY="your-key-here"
export BRAVE_SEARCH_API_KEY="your-key-here"
```

### Running the System

#### CLI Interface (Interactive)

```bash
python run.py --config config.llm_router.json
```

#### Web Server (API + UI)

Edit `config.llm_router.json` to enable server mode:

```json
{
  "APPLICATION": {
    "type": ["server"]
  }
}
```

Then run:

```bash
python run.py --config config.llm_router.json
```

Access at: http://localhost:8000

[Complete setup guide →](docs/DEPLOYMENT.md)

---

## 📖 Usage Examples

### Example 1: Basic Complaint Processing

```python
from mediator import Mediator
from backends import LLMRouterBackend

# Initialize
backend = LLMRouterBackend(
    id='llm-router',
    provider='copilot_cli',
    model='gpt-4'
)
mediator = Mediator(backends=[backend])

# Process complaint
mediator.state.complaint = """
I was fired after reporting safety violations to OSHA.
My employer claimed poor performance, but I had 5 years
of excellent reviews.
"""

# Analyze
result = mediator.analyze_complaint_legal_issues()
print("Claim Types:", result['classification']['claim_types'])
print("Applicable Laws:", result['statutes'])
```

### Example 2: Three-Phase Workflow

```python
from complaint_phases import PhaseManager

# Start three-phase processing
manager = PhaseManager(mediator=mediator)

# Phase 1: Intake
manager.start_three_phase_process(initial_text)
while manager.current_phase == 'denoising':
    question = manager.get_next_question()
    answer = input(question)
    manager.process_answer(question, answer)

# Phase 2: Evidence
manager.advance_to_evidence_phase()
manager.discover_web_evidence()

# Phase 3: Formalization
manager.advance_to_formalization_phase()
complaint = manager.generate_formal_complaint()
```

### Example 3: Evidence Management

```python
# Submit evidence
result = mediator.submit_evidence(
    data=document_bytes,
    evidence_type='document',
    description='Performance reviews',
    claim_type='wrongful_termination'
)

# Analyze evidence gaps
analysis = mediator.analyze_evidence(claim_type='wrongful_termination')
print("Missing Evidence:", analysis['gaps'])
```

[More examples →](docs/EXAMPLES.md)

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────┐
│                   User Interface                         │
│              (CLI, Web App, API)                         │
└─────────────────────┬────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────────────┐
│                    Mediator                              │
│         (Core Orchestration & State Management)          │
└────────┬─────────────────────────────────────┬───────────┘
         │                                     │
         ▼                                     ▼
┌────────────────────────┐      ┌─────────────────────────┐
│   LLM Router Backend   │      │  Complaint Phases       │
│  (Multi-provider AI)   │      │  (3-Phase Processing)   │
└────────┬───────────────┘      └─────────┬───────────────┘
         │                                │
         │                                ▼
         │                      ┌──────────────────────┐
         │                      │  Knowledge Graphs    │
         │                      │  Dependency Graphs   │
         │                      │  Legal Graphs        │
         │                      └──────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────┐
│                   Analysis & Research                    │
├───────────────────┬──────────────────┬───────────────────┤
│  Complaint        │   Legal          │   Evidence        │
│  Analysis         │   Research       │   Management      │
│  (14 types)       │   (Multi-source) │   (IPFS+DuckDB)   │
└───────────────────┴──────────────────┴───────────────────┘
         │                  │                  │
         └──────────────────┴──────────────────┘
                           │
                           ▼
                ┌──────────────────────┐
                │   Storage Layer      │
                │  - IPFS (Evidence)   │
                │  - DuckDB (Metadata) │
                └──────────────────────┘
```

[Detailed architecture →](docs/ARCHITECTURE.md)

---

## 📚 Documentation

### Getting Started
- **[README](README.md)** - This file
- **[Configuration Guide](docs/CONFIGURATION.md)** - System configuration
- **[Deployment Guide](docs/DEPLOYMENT.md)** - Production deployment
- **[Applications Guide](docs/APPLICATIONS.md)** - CLI and web server

### Core Systems
- **[Three-Phase System](docs/THREE_PHASE_SYSTEM.md)** - Intelligent processing workflow
- **[LLM Router](docs/LLM_ROUTER.md)** - Multi-provider LLM integration
- **[Architecture](docs/ARCHITECTURE.md)** - System design and data flows

### Features
- **[Complaint Analysis](docs/COMPLAINT_ANALYSIS_INTEGRATION.md)** - 14 complaint types
- **[Legal Research](docs/LEGAL_AUTHORITY_RESEARCH.md)** - Multi-source research
- **[Evidence Management](docs/EVIDENCE_MANAGEMENT.md)** - IPFS and DuckDB
- **[Web Evidence Discovery](docs/WEB_EVIDENCE_DISCOVERY.md)** - Automated web search
- **[Adversarial Testing](docs/ADVERSARIAL_HARNESS.md)** - Quality assurance
- **[DEI Analysis](docs/HACC_INTEGRATION.md)** - Policy analysis

### Development
- **[Testing Guide](TESTING.md)** - Test-driven development
- **[Contributing](CONTRIBUTING.md)** - How to contribute
- **[Security Guide](docs/SECURITY.md)** - Security best practices
- **[Examples](docs/EXAMPLES.md)** - 21 usage examples

[Complete documentation index →](DOCUMENTATION_INDEX.md)

---

## 🧪 Testing

The system includes comprehensive test coverage:

- **150+ Tests** across all components
- **60+ Test Classes** organized by feature
- **Unit & Integration Tests** with pytest
- **Adversarial Testing Framework** for quality assurance

```bash
# Run all tests
pytest

# Run specific test categories
pytest -m "not integration"  # Unit tests only
pytest tests/test_complaint_phases.py  # Specific module

# Run with coverage
pytest --cov=. --cov-report=html
```

[Testing guide →](TESTING.md)

---

## 🔒 Security

**⚠️ Important Security Notice**

The current implementation has several security considerations for production deployment:

- Hardcoded JWT secret key (must be moved to environment variables)
- No HTTPS by default (configure SSL certificates for production)
- Authentication mechanism needs hardening
- Input validation should be enhanced

See the [Security Guide](docs/SECURITY.md) for detailed hardening steps before production deployment.

---

## 📊 System Requirements

### Minimum
- Python 3.8+
- 4 GB RAM
- 10 GB storage

### Recommended
- Python 3.10+
- 8 GB RAM
- 50 GB SSD storage
- Multi-core processor

### For Local LLM Models
- 16+ GB RAM
- GPU with CUDA support (optional but recommended)
- 100+ GB storage for models

---

## 🛠️ Configuration

The system is configured via `config.llm_router.json`:

```json
{
  "BACKENDS": [
    {
      "id": "llm-router",
      "type": "llm_router",
      "provider": "copilot_cli",
      "model": "gpt-4",
      "max_tokens": 2048
    }
  ],
  "MEDIATOR": {
    "backends": ["llm-router"]
  },
  "APPLICATION": {
    "type": ["cli"]
  },
  "LOG": {
    "level": "INFO"
  }
}
```

**Key Configuration Sections:**
- **BACKENDS** - LLM providers and models
- **MEDIATOR** - Core orchestration settings
- **APPLICATION** - CLI/server settings  
- **LOG** - Logging configuration

[Complete configuration reference →](docs/CONFIGURATION.md)

---

## 🤝 Contributing

We welcome contributions! To get started:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Write tests for your changes
4. Implement your changes
5. Run the test suite (`pytest`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

[Contributing guidelines →](CONTRIBUTING.md)

---

## 📦 Project Structure

```
complaint-generator/
├── adversarial_harness/      # Adversarial testing framework
├── applications/              # CLI and web server
├── backends/                  # LLM provider integrations
├── complaint_analysis/        # 14 complaint type analyzers
├── complaint_phases/          # Three-phase processing
├── docs/                      # Documentation (30+ guides)
├── examples/                  # 21 usage examples
├── mediator/                  # Core orchestration
├── templates/                 # Web UI templates
├── tests/                     # Test suite (150+ tests)
├── config.llm_router.json     # Configuration file
├── requirements.txt           # Python dependencies
└── run.py                     # Application entry point
```

---

## 🔗 Dependencies

### Core Libraries
- **duckdb** - Fast embedded database for state management
- **pytest** - Testing framework
- **fastapi** - Web framework for API server
- **pydantic** - Data validation

### Submodule: ipfs_datasets_py
- LLM routing across multiple providers
- IPFS backend for evidence storage
- Legal scrapers for research
- Web archiving tools

[View all dependencies →](requirements.txt)

---

## 🐛 Troubleshooting

### Common Issues

**"Submodule not initialized"**
```bash
git submodule update --init --recursive
```

**"Import errors from ipfs_datasets_py"**
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)/ipfs_datasets_py"
```

**"Database locked"**
```bash
rm statefiles/*.duckdb-wal
```

**"Missing Brave Search results"**
```bash
export BRAVE_SEARCH_API_KEY="your_key"
# Get free key at: https://brave.com/search/api/
```

---

## 📈 Project Status

- ✅ Core three-phase system implemented
- ✅ 14 complaint types with taxonomies
- ✅ Multi-provider LLM support
- ✅ Evidence management with IPFS
- ✅ Legal research automation
- ✅ Adversarial testing framework
- ✅ 150+ tests with comprehensive coverage
- 🚧 Web UI polish (in progress)
- 🚧 Additional complaint types (ongoing)
- 📋 Mobile app (planned)

---

## 📝 License

[License information would go here]

---

## 🙏 Acknowledgments

- Built with [ipfs_datasets_py](https://github.com/endomorphosis/ipfs_datasets_py)
- Developed by JusticeDAO
- Powered by multiple LLM providers
- Inspired by legal professionals worldwide

---

## 📬 Support & Contact

- **Issues**: https://github.com/endomorphosis/complaint-generator/issues
- **Discussions**: https://github.com/endomorphosis/complaint-generator/discussions
- **Documentation**: https://github.com/endomorphosis/complaint-generator/tree/main/docs

---

## ⚖️ Legal Disclaimer

**This system is designed to assist legal professionals and should not be considered a replacement for professional legal advice. Always consult with a qualified attorney for legal matters.**

The Complaint Generator is a tool to help organize information and generate documents. It does not provide legal advice, representation, or counseling. Users are responsible for reviewing all generated content and ensuring accuracy and legal compliance.

---

**Version**: 1.0  
**Last Updated**: 2026-02-10
