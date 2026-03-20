# Architecture Overview

High-level architecture of the complaint-generator system, showing how all components work together.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User Interface                               │
│                  (CLI, Web App, API Endpoints)                       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          Mediator                                    │
│           (Core Orchestration & Workflow Management)                 │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │  - Three-Phase Processing                                  │     │
│  │  - Hook Management                                         │     │
│  │  - State Persistence                                       │     │
│  └────────────────────────────────────────────────────────────┘     │
└────┬──────────────┬──────────────┬──────────────┬──────────────┬────┘
     │              │              │              │              │
     ▼              ▼              ▼              ▼              ▼
┌─────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│Complaint│  │Complaint │  │Adversarial│  │ Backend  │  │ Evidence │
│Analysis │  │ Phases   │  │  Harness  │  │  Router  │  │ Storage  │
└─────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘
```

## Component Layers

### Layer 1: User Interface
- **CLI Application** - Command-line interface for interactive complaints
- **Web Application** - Browser-based UI (future)
- **API Endpoints** - RESTful API for integrations (future)

### Layer 2: Mediator (Orchestration)
- **Core Mediator** - Central coordinator for all operations
- **State Management** - DuckDB-backed persistent state
- **Hook Manager** - Dynamic hook registration and execution
- **Phase Manager** - Three-phase workflow orchestration

### Layer 3: Feature Modules

#### Complaint Analysis
- **Purpose:** Classify and analyze complaints across 14 legal domains
- **Components:**
  - Keyword registries (390+ keywords)
  - Legal pattern extraction (90+ patterns)
  - Decision trees (76 questions)
  - Risk scoring algorithms
  - Seed generation
- **Integration:** Provides classification for mediator workflows

#### Complaint Phases
- **Purpose:** Three-phase complaint processing with graph-based reasoning
- **Components:**
  - Knowledge Graph Builder (entities, relationships)
  - Dependency Graph Builder (claims, requirements)
  - Legal Graph Builder (statutes, procedures)
  - Denoiser (gap reduction)
  - Neurosymbolic Matcher (fact-to-requirement matching)
- **Integration:** Core processing engine called by mediator

#### Adversarial Harness
- **Purpose:** Test and optimize complaint generation quality
- **Components:**
  - Complainant Agent (LLM-based complainant simulation)
  - Critic Agent (multi-dimensional quality evaluation)
  - Optimizer (SGD cycle optimization)
  - Session Manager (multi-round testing)
- **Integration:** Tests mediator performance, provides optimization feedback

#### Backend Router
- **Purpose:** Route LLM requests to multiple providers
- **Components:**
  - LLM Router (multi-provider with fallback)
  - Provider adapters (OpenAI, HuggingFace, Copilot, etc.)
  - Rate limiter
  - Batch processor
- **Integration:** Provides LLM services to all components

#### Evidence Storage
- **Purpose:** Immutable evidence storage with content addressing
- **Components:**
  - IPFS backend (content-addressable storage)
  - DuckDB state (metadata and queries)
  - Evidence hooks (submission, retrieval, analysis)
- **Integration:** Stores and manages all evidence artifacts

### Layer 4: External Services

#### IPFS Network
- Distributed storage network
- Content-addressable files
- CID-based retrieval

#### LLM Providers
- Codex (`gpt-5.3-codex`)
- OpenAI
- OpenRouter (multi-model access)
- HuggingFace (open-source models)
- Copilot CLI (GitHub Copilot)
- Local models (workstation backend)

#### Legal Data Sources
- US Code (federal statutes)
- Federal Register (regulations)
- RECAP Archive (case law)
- Common Crawl (web archives)
- Brave Search (current web)

## Data Flow

### Complaint Intake Flow

```
User Input
    │
    ▼
Mediator.state.complaint
    │
    ▼
Complaint Analysis
    ├─→ Classify (claim types)
    ├─→ Extract keywords
    └─→ Score risk
    │
    ▼
Phase 1: Intake
    ├─→ Knowledge Graph Builder
    │     └─→ Extract entities & relationships
    ├─→ Dependency Graph Builder
    │     └─→ Map claims to requirements
    └─→ Denoiser
          └─→ Generate questions to fill gaps
    │
    ▼
User Answers Questions
    │
    ▼
Phase 1 Iteration
    └─→ Update graphs, check convergence
    │
    ▼
Phase 2: Evidence
    ├─→ Identify evidence gaps
    ├─→ User submits evidence → IPFS
    ├─→ Auto-discover web evidence
    └─→ Update dependency graph
    │
    ▼
Phase 3: Formalization
    ├─→ Legal Graph Builder
    │     └─→ Fetch applicable laws
    ├─→ Neurosymbolic Matcher
    │     └─→ Match facts to requirements
    └─→ Generate formal complaint
    │
    ▼
Formal Complaint Document
```

### Evidence Storage Flow

```
Evidence Submission
    │
    ▼
Evidence Storage Hook
    ├─→ IPFS
    │     └─→ Store content, get CID
    └─→ DuckDB
          └─→ Store metadata + CID
    │
    ▼
Evidence Analysis
    └─→ Identify gaps, generate recommendations
```

### Legal Research Flow

```
Legal Analysis Request
    │
    ▼
Legal Authority Search Hook
    ├─→ US Code API
    ├─→ Federal Register API
    ├─→ RECAP Archive
    └─→ Common Crawl Search
    │
    ▼
Legal Authority Storage Hook
    └─→ DuckDB
          └─→ Store citations, relevance scores
    │
    ▼
Legal Authority Analysis Hook
    └─→ AI relevance scoring, recommendations
```

### Adversarial Testing Flow

```
Adversarial Harness
    │
    ▼
Seed Complaint Library
    └─→ Generate test complaints
    │
    ▼
Parallel Sessions
    ├─→ Session 1: Complainant ↔ Mediator
    ├─→ Session 2: Complainant ↔ Mediator
    ├─→ Session 3: Complainant ↔ Mediator
    └─→ Session N: Complainant ↔ Mediator
    │
    ▼
Critic Evaluation
    └─→ Score each session (5 dimensions)
    │
    ▼
Optimizer Analysis
    └─→ Aggregate scores, identify trends
    │
    ▼
Recommendations
    └─→ Apply to mediator configuration
```

## State Management

### DuckDB Tables

**Evidence Table:**
```sql
CREATE TABLE evidence (
    id BIGINT PRIMARY KEY,
    user_id VARCHAR,
    evidence_cid VARCHAR NOT NULL,
    evidence_type VARCHAR NOT NULL,
    description TEXT,
    claim_type VARCHAR,
    metadata JSON,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

**Legal Authorities Table:**
```sql
CREATE TABLE legal_authorities (
    id BIGINT PRIMARY KEY,
    user_id VARCHAR,
    claim_type VARCHAR,
    authority_type VARCHAR NOT NULL,
    source VARCHAR NOT NULL,
    citation VARCHAR,
    title TEXT,
    content TEXT,
    relevance_score FLOAT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### JSON State Files

Graphs are persisted as JSON for resumability:

- `statefiles/knowledge_graph.json` - Entities and relationships
- `statefiles/dependency_graph.json` - Claims and requirements
- `statefiles/legal_graph.json` - Legal elements and relations
- `statefiles/summary.json` - Complaint summary

## Integration Points

### Mediator ↔ Complaint Analysis
- Mediator uses complaint_analysis for classification
- Decision trees guide mediator's questioning
- Seed generation provides test data

### Mediator ↔ Complaint Phases
- Mediator invokes three-phase processing
- Phase manager coordinates graph builders
- Denoiser generates questions for mediator to ask

### Mediator ↔ Adversarial Harness
- Harness tests mediator's performance
- Critic evaluates mediator's questions
- Optimizer provides improvement recommendations

### Mediator ↔ Backends
- Mediator routes all LLM requests through backend
- Backend handles provider selection and fallback
- Batch processing for parallel operations

### Complaint Phases ↔ Evidence Storage
- Phase 2 identifies evidence gaps
- Evidence hooks store submissions in IPFS
- Dependency graph tracks evidence-requirement links

### Complaint Phases ↔ Legal Research
- Phase 3 fetches applicable laws
- Legal graph integrates research findings
- Neurosymbolic matcher uses legal requirements

## Extensibility

### Adding New Complaint Types

1. Register keywords and legal patterns
2. Create decision tree JSON
3. Update complaint_types.py registration
4. Add test cases

### Adding New Hooks

1. Implement hook interface (execute, hook_name)
2. Register with mediator
3. Add to configuration
4. Add test coverage

### Adding New Backends

1. Implement backend interface
2. Add provider configuration
3. Register with LLM router
4. Test with example scripts

### Adding New Analysis Features

1. Create feature module
2. Integrate with complaint_analysis
3. Add to prompt templates
4. Add response parsers

## Performance Considerations

### Caching
- LLM responses cached when appropriate
- DuckDB provides fast state queries
- Graph serialization enables resumability

### Parallelism
- Adversarial harness supports parallel sessions
- Backend supports batch LLM requests
- Multi-threaded evidence processing

### Optimization
- Minimize LLM calls (batch, cache)
- Efficient graph algorithms
- Indexed database queries

## Security Considerations

### Authentication
- API keys stored in environment variables
- Credentials should not be stored in code or config files

### Data Privacy
- User data isolated by user_id
- IPFS CIDs don't reveal content
- Local backend option for sensitive data

### Input Validation
- All user inputs sanitized
- LLM responses validated before parsing
- File uploads virus-scanned (recommended)

## Deployment Architecture

### Development
```
Developer Workstation
    ├─→ Local IPFS node
    ├─→ Local DuckDB files
    └─→ Copilot CLI backend
```

### Production (Recommended)
```
Load Balancer
    │
    ▼
Application Servers (N instances)
    ├─→ Shared IPFS cluster
    ├─→ Centralized DuckDB (or PostgreSQL)
    └─→ LLM Router → Multiple providers
```

### Scaling Strategy
- **Horizontal:** Add more application server instances
- **Backend:** Use multiple LLM provider accounts
- **Storage:** Scale IPFS cluster, migrate to PostgreSQL
- **Caching:** Add Redis for LLM response caching

## Monitoring and Observability

### Metrics to Track
- LLM API latency and error rates
- Complaint processing time per phase
- Evidence storage/retrieval performance
- Adversarial test scores over time
- Database query performance

### Logging
- Structured logging with correlation IDs
- Error tracking with stack traces
- Audit logs for user actions
- Performance profiling for bottlenecks

## Technology Stack

### Core
- **Python 3.8+** - Primary language
- **DuckDB** - Embedded SQL database
- **IPFS** - Distributed storage

### LLM Integration
- **Codex** - `gpt-5.3-codex`
- **OpenAI API**
- **HuggingFace** - Open-source models
- **Copilot CLI** - GitHub Copilot
- **llama.cpp** - Local model inference

### Testing
- **pytest** - Test framework
- **pytest-cov** - Coverage reporting
- **pytest-asyncio** - Async test support

### Documentation
- **Markdown** - Documentation format
- **SVG** - Architecture diagrams

## Future Enhancements

### Planned Features
- Web UI for complaint intake
- RESTful API for integrations
- Real-time collaboration features
- Mobile application
- Multi-language support

### Research Areas
- Improved neurosymbolic matching
- Better convergence detection
- Enhanced legal corpus RAG
- Automated legal brief generation
- Case outcome prediction

## See Also

- [README.md](../README.md) - Project overview
- [docs/THREE_PHASE_SYSTEM.md](THREE_PHASE_SYSTEM.md) - Three-phase workflow details
- [docs/BACKENDS.md](BACKENDS.md) - Backend configuration
- [mediator/readme.md](../mediator/readme.md) - Mediator documentation
- [complaint_analysis/README.md](../complaint_analysis/README.md) - Analysis module
- [complaint_phases/README.md](../complaint_phases/README.md) - Phase processing
- [adversarial_harness/README.md](../adversarial_harness/README.md) - Testing framework
