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

## Runtime Entrypoint and Ownership Map

This section is the refactor baseline for deciding where new code belongs and
which modules should be split first. The current package exposes thin script
entrypoints in `pyproject.toml`; those entrypoints mostly delegate into
`applications/` modules or daemon modules. Refactor work should preserve these
public command names while moving implementation detail behind smaller internal
modules.

### Public Runtime Entrypoints

| Surface | Public entrypoint | Current owner | Responsibility | Refactor guidance |
|---|---|---|---|---|
| Main package command | `complaint-generator` -> `complaint_generator.entrypoints:main` | `complaint_generator/entrypoints.py`, `run.py` | Legacy top-level command dispatch. | Keep as compatibility wrapper; move behavior into named application or service modules. |
| Workspace CLI | `complaint-workspace`, `complaint-generator-workspace` -> `complaint_generator.cli:main` | `applications/complaint_cli.py`, `applications/complaint_workspace.py` | Typer CLI for sessions, intake, evidence, review, document generation, imports, and daemon commands. | Keep CLI parsing thin; route workflow behavior through `ComplaintWorkspaceService` or smaller service modules. |
| MCP server | `complaint-mcp-server`, `complaint-generator-mcp` -> `complaint_generator.mcp_server:main` | `applications/complaint_mcp_server.py`, `applications/complaint_mcp_protocol.py` | MCP protocol surface and tool exposure. | Treat protocol schemas as stable contracts; do not place business logic in protocol handlers. |
| UI/UX workflow | `complaint-ui-ux-workflow` -> `complaint_generator.ui_ux_workflow:main` | `complaint_generator/ui_ux_workflow.py`, `applications/ui_review.py` | Browser audit, review, and actor-critic UI workflow orchestration. | Keep automation orchestration separate from UI payload builders and workspace state helpers. |
| UI optimizer daemon | `complaint-ui-optimizer-daemon` -> `complaint_generator.ui_optimizer_daemon:main` | `complaint_generator/ui_optimizer_daemon.py` | Long-running UI optimization daemon with status, logs, screenshots, and review artifacts. | Align daemon status payloads with other daemons; keep task derivation separate from process lifecycle code. |
| Review API | `applications.review_api:create_review_api_app` | `applications/review_api.py`, `applications/document_api.py` | FastAPI claim-support and document review endpoints. | Keep route handlers as DTO adapters; move normalization and payload assembly behind explicit helpers. |
| Dashboard UI | `applications.dashboard_ui` | `applications/dashboard_ui.py`, templates/static assets | Browser dashboard, review hub, IPFS dashboard links, and fixture-backed display surfaces. | Split fixture/data assembly from route rendering before changing UI behavior. |
| Refactor supervisor | `scripts/refactor_agent_supervisor.py` | `data/refactor_supervisor/*`, `docs/REFACTOR_SUPERVISOR_TASKBOARD.md` | Codebase scan, goal/subgoal generation, DuckDB taskboard refill using `ipfs_accelerate_py.p2p_tasks.TaskQueue`. | Planning-only daemon; implementation agents should claim scoped tasks and run the task's validation command. |

### Package Ownership Boundaries

| Package or directory | Owner role | Inputs | Outputs | Refactor notes |
|---|---|---|---|---|
| `applications/` | User-facing transport layer for CLI, FastAPI, dashboard, review, and browser workflows. | HTTP requests, CLI options, uploaded files, user/session IDs. | DTO payloads, rendered HTML, files, and calls into workspace or mediator services. | Should not own deep legal workflow logic. Extract route groups and fixture builders before feature changes. |
| `complaint_generator/` | Public package compatibility layer plus workspace and daemon orchestration. | Console script calls, workspace requests, UI optimization cycles. | Stable package imports, CLI/MCP wrappers, workspace service responses, daemon status artifacts. | Keep top-level modules import-light and preserve existing public exports. |
| `mediator/` | Core workflow orchestration and stateful legal/evidence hooks. | Normalized case state, evidence, authorities, graph outputs, adapter capabilities. | Claim support payloads, review plans, follow-up execution, formal document inputs. | `mediator/mediator.py` and `mediator/claim_support_hooks.py` are highest-risk extraction targets; split by cohesive service while preserving public method names. |
| `complaint_phases/` | Workflow graph primitives and three-phase complaint processing. | Complaint narratives, claim requirements, entities, facts, authorities. | Knowledge graphs, dependency graphs, intake case files, denoiser questions, legal graph matches. | Keep domain graph algorithms here; optional graph persistence/query calls may use the integration port, but avoid importing application or transport modules. |
| `integrations/ipfs_datasets/` | Optional dependency adapter boundary for `ipfs_datasets_py` and related capabilities. | Adapter calls from mediator, workspace, document, search, graph, GraphRAG, logic, storage, and LLM code. | Degraded-mode safe results, capability reports, provenance, parsed documents, graph/query outputs. | Production code should route optional dependency behavior through this layer rather than direct imports or ad hoc `sys.path` mutation. |
| `backends/` | LLM/provider backend adapters. | Provider configuration, prompts, model choices, rate limits. | Text or multimodal model responses. | Keep provider-specific failure handling here and expose typed errors to callers. |
| `lib/` | Cross-consumer utility contracts for formal logic, document rendering, graph export, support maps, and payload helpers. | Pure data structures or local file inputs. | Reusable utilities without user-interface side effects. | Shared code should land here only when it has at least two real consumers. |
| `scripts/` | Operator and batch workflows. | Shell/CLI invocation, local paths, batch options. | Reports, imports, generated docs, local artifacts. | Run repository scripts from an installed environment or as modules from the repository root. Entrypoints must not mutate `sys.path` to discover project or sibling modules. |
| `tests/` | Regression and contract coverage. | Public APIs, fixtures, snapshots, browser flows. | Safety net for refactor slices. | Add focused lanes before large extractions: imports, adapter degraded mode, mediator, document pipeline, and UI smoke. |

### Current Extraction Priorities

The codebase scan that seeded the refactor taskboard found 433 Python files,
260 test files, and 243,492 Python lines. The largest runtime modules and their
first extraction direction are:

| Module | Current size signal | First safe extraction |
|---|---:|---|
| `mediator/mediator.py` | 10,852 lines | Move one cohesive workflow service behind private helpers while keeping `Mediator` public methods stable. |
| `applications/complaint_workspace.py` | 7,881 lines | Extract route/service payload builders and workspace state helpers from request-level orchestration. |
| `scripts/synthesize_hacc_complaint.py` | 6,933 lines | Split batch orchestration, data loading, and report rendering into importable helpers before behavior changes. |
| `complaint_phases/denoiser.py` | 5,691 lines | Separate scoring, prompt/question generation, and graph gap analysis. |
| `applications/dashboard_ui.py` | 5,562 lines | Extract dashboard entry catalogs, fixture builders, and render helpers from route setup. |
| `mediator/claim_support_hooks.py` | 5,309 lines | Split persistence/query helpers from review payload assembly and follow-up planning. |

### Allowed Import Direction

The dependency rule for production packages is top-down: user-facing surfaces
call orchestration, orchestration calls domain workflow and adapter packages,
and stable cross-consumer helpers sit at the bottom in `lib/`. Lower layers must
not import higher layers. The same contract is recorded in `pyproject.toml`
under `[tool.complaint_generator.import_boundaries]` and is enforced by
`tests/test_package_imports.py`.

| Package | May import these project packages | Must not import |
|---|---|---|
| `applications/` | `applications/`, `mediator/`, `complaint_phases/`, `integrations/`, `lib/` | Keep reusable legal, evidence, graph, and document workflow logic out of route handlers, CLI commands, Typer setup, FastAPI setup, and browser fixtures. |
| `mediator/` | `mediator/`, `complaint_phases/`, `integrations/`, `lib/` | Do not import `applications/`, UI frameworks, CLI frameworks, browser fixtures, templates, static assets, or script-only modules. |
| `complaint_phases/` | `complaint_phases/`, `integrations/`, `lib/` | Do not import `applications/`, `mediator/`, provider backends, or concrete `ipfs_datasets_py` modules. Integration imports are limited to explicit persistence/query ports; phase algorithms should stay deterministic and domain-focused. |
| `integrations/` | `integrations/`, `lib/` | Do not import `applications/`, `mediator/`, or `complaint_phases/` from adapter code; integration modules translate optional dependencies into local contracts. |
| `lib/` | `lib/` | Do not import application, mediator, phase, integration, backend, script, template, or static-asset modules. |

`complaint_generator/` remains the public compatibility package for console
scripts and import aliases. Its wrappers may delegate to `applications/`, but
new workflow behavior should still be implemented in the layer that owns it and
then exposed through a thin compatibility wrapper only when a public import path
requires it.

### Shared Code Rule

Keep code in its owning layer until two or more production consumers need the
same side-effect-light helper or data contract. At that point, move the stable
shared piece to `lib/` and keep transport concerns, persistence setup, provider
calls, and optional dependency loading in their original owner packages. Shared
code in `lib/` should accept plain values or small local data objects, avoid
network or database side effects, and be useful without importing application or
mediator state.

### Refactor Dependency Rules

1. New production imports between `applications/`, `mediator/`,
   `complaint_phases/`, `integrations/`, and `lib/` must match the allowed
   import table above.
2. Production optional dependency access should flow through
   `integrations/ipfs_datasets/`; direct `ipfs_datasets_py` imports are allowed
   only in adapters, tests, benchmarks, or explicitly documented shims.
3. Long-running automation should expose `status`, `pid`, `updated_at`,
   artifact paths, queue counts where applicable, and a stop path.
4. Each refactor slice should name a validation lane before code movement.
5. Operator entrypoints must resolve normal project imports from the installed
   package (or module execution from the repository root), never by modifying
   `sys.path`. File-based loading is reserved for isolated tooling and tests.

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
