# Example Scripts Reference

Complete guide to all 22 example scripts in the repository, organized by category.

## Overview

The `examples/` directory contains 22 demonstration scripts covering all major features of the complaint generator system. Scripts are organized into four categories:

1. **Core System Examples** (7) - Basic workflows and core features
2. **Complaint Analysis Examples** (5) - Analysis and classification
3. **Adversarial Testing Examples** (7) - Testing and optimization
4. **Advanced Examples** (3) - Code generation and autopatch

## Core System Examples

### 1. three_phase_example.py

**Purpose:** Complete demonstration of the three-phase complaint processing workflow.

**Features Demonstrated:**
- Phase 1: Intake & denoising with knowledge/dependency graphs
- Phase 2: Evidence gathering and gap filling
- Phase 3: Formalization with neurosymbolic matching
- Automatic phase transitions
- Graph persistence and state management
- Convergence detection

**Usage:**
```bash
python examples/three_phase_example.py
```

**Key Code:**
```python
from mediator import Mediator
from backends import LLMRouterBackend

backend = LLMRouterBackend(id='llm', provider='copilot_cli', model='gpt-5-mini')
mediator = Mediator(backends=[backend])

result = mediator.run_three_phase_processing(
    initial_complaint="I was terminated after reporting safety violations...",
    max_iterations=5
)

print(f"Current Phase: {result['current_phase']}")
print(f"Formal Complaint: {result['formal_complaint']}")
```

---

### 2. legal_analysis_demo.py

**Purpose:** Demonstrate the 4-stage legal analysis pipeline.

**Features Demonstrated:**
- Legal classification (claim types, jurisdiction)
- Statute retrieval (applicable laws)
- Summary judgment (required elements)
- Question generation (evidence gathering)
- Hook-based architecture

**Usage:**
```bash
python examples/legal_analysis_demo.py
```

**Key Code:**
```python
# Placeholder implementation: the current demo script only prints a message.
print("Legal Analysis Hooks Demo - See docs/LEGAL_HOOKS.md for full documentation")
print("This demonstrates the 4-step legal analysis process:")
print("1. Classification - Identify claim types")
print("2. Statute Retrieval - Find applicable laws")
print("3. Requirements - Determine elements to prove") 
print("4. Questions - Generate targeted questions")
```

---

### 3. evidence_management_demo.py

**Purpose:** IPFS-based evidence storage and management.

**Features Demonstrated:**
- Evidence submission to IPFS
- Content-addressable storage (CID)
- DuckDB metadata management
- Evidence retrieval and querying
- Gap analysis and recommendations

**Usage:**
```bash
python examples/evidence_management_demo.py
```

**Key Code:**
```python
# Submit evidence
result = mediator.submit_evidence(
    data=b"Performance review document...",
    evidence_type='document',
    description='5 years of excellent reviews',
    claim_type='wrongful_termination'
)
print(f"Evidence CID: {result['cid']}")

# Analyze evidence gaps
analysis = mediator.analyze_evidence(claim_type='wrongful_termination')
print(f"Recommendations: {analysis['recommendation']}")
```

---

### 4. legal_authority_research_demo.py

**Purpose:** Multi-source legal research demonstration.

**Features Demonstrated:**
- US Code statute lookup
- Federal Register regulations
- RECAP case law archive
- Common Crawl web archives
- DuckDB citation storage
- Relevance scoring

**Usage:**
```bash
python examples/legal_authority_research_demo.py
```

**Key Code:**
```python
# Automatic research
results = mediator.research_case_automatically()
print(f"Researched claim types: {results['claim_types']}")
for claim_type, stored in results['authorities_stored'].items():
    coverage = results['claim_coverage_matrix'][claim_type]
    print(f"{claim_type}: {stored['total_records']} authorities processed")
    print(f"  partial={coverage['status_counts']['partially_supported']} missing={coverage['status_counts']['missing']}")

# Get authorities for specific claim
authorities = mediator.get_legal_authorities(claim_type='retaliation')
for auth in authorities:
    print(f"- {auth['citation']}: {auth['title']}")
```

---

### 5. web_evidence_discovery_demo.py

**Purpose:** Automated web evidence discovery.

**Features Demonstrated:**
- Brave Search API integration
- Common Crawl archive search
- Automatic keyword generation
- AI-powered relevance scoring
- Domain filtering
- Content classification

**Usage:**
```bash
export BRAVE_SEARCH_API_KEY="your_key"
python examples/web_evidence_discovery_demo.py
```

**Key Code:**
```python
# Automatic discovery
results = mediator.discover_evidence_automatically()
print(f"Claims analyzed: {results['claim_types']}")
for claim_type in results['claim_types']:
    coverage = results['claim_coverage_matrix'][claim_type]
    print(f"{claim_type}: discovered={results['evidence_discovered'][claim_type]} stored={results['evidence_stored'][claim_type]}")
    print(f"  partial={coverage['status_counts']['partially_supported']} missing={coverage['status_counts']['missing']}")

# Manual search with keywords
search_results = mediator.search_web_for_evidence(
    keywords=['OSHA retaliation', 'whistleblower'],
    domains=['osha.gov', 'dol.gov'],
    max_results=10
)
```

---

### 6. search_hooks_demo.py

**Purpose:** Legal corpus RAG and search integration.

**Features Demonstrated:**
- Legal corpus RAG (Retrieval-Augmented Generation)
- Semantic search across 14 complaint types
- Decision tree enhancement
- Seed enrichment with legal knowledge
- Question suggestion from legal corpus

**Usage:**
```bash
python examples/search_hooks_demo.py
```

**Key Code:**
```python
from mediator.legal_corpus_hooks import LegalCorpusRAGHook

hook = LegalCorpusRAGHook()

# Search legal corpus
results = hook.search_legal_corpus(
    query="employment discrimination requirements",
    complaint_type="employment",
    top_k=5
)

# Get legal requirements
requirements = hook.get_legal_requirements(
    complaint_type="employment"
)

# Suggest questions
questions = hook.suggest_questions(
    complaint_type="employment",
    answered_fields={'employer', 'action'}
)
```

---

### 7. claim_support_review_demo.py

**Purpose:** Review claim-element support coverage using the new matrix and summary payloads.

**Features Demonstrated:**
- `claim_coverage_matrix` review by claim element
- `claim_coverage_summary` for quick status dashboards
- grouped support links by evidence versus authority
- missing-support analysis and follow-up planning

**Usage:**
```bash
python examples/claim_support_review_demo.py
```

**Key Code:**
```python
claim_type = 'employment retaliation'

matrix = mediator.get_claim_coverage_matrix(claim_type=claim_type)
summary = mediator.research_case_automatically()['claim_coverage_summary'][claim_type]
follow_up = mediator.get_claim_follow_up_plan(claim_type=claim_type)

print(summary['status_counts'])
print(summary['missing_elements'])
for element in matrix['claims'][claim_type]['elements']:
    print(element['element_text'], element['status'])
```

---

## Complaint Analysis Examples

### 8. complaint_analysis_integration_demo.py

**Purpose:** End-to-end complaint analysis with all features.

**Features Demonstrated:**
- Seed generation from templates
- Decision tree navigation
- Prompt template usage
- Response parsing (entities, relationships, claims)
- State file ingestion
- Risk scoring

**Usage:**
```bash
python examples/complaint_analysis_integration_demo.py
```

**Key Code:**
```python
from complaint_analysis import (
    SeedGenerator,
    DecisionTreeGenerator,
    PromptLibrary,
    ResponseParserFactory
)

# Generate seed
generator = SeedGenerator()
seed = generator.generate_seed('housing_discrimination_1', {...})

# Use decision tree
tree_gen = DecisionTreeGenerator()
questions = tree_gen.get_next_questions('housing', answered_fields)

# Use prompt templates
prompts = PromptLibrary()
prompt = prompts.get_prompt('extract_entities', complaint_text)

# Parse LLM response
parser = ResponseParserFactory.get_parser('entities')
entities = parser.parse(llm_response)
```

---

### 9. complaint_analysis_taxonomies_demo.py

**Purpose:** Demonstrate all 14 complaint type taxonomies.

**Features Demonstrated:**
- All 14 complaint types (DEI, housing, employment, etc.)
- Type-specific keywords (390+ total)
- Legal pattern extraction (90+ patterns)
- Risk scoring per type
- Category-specific analysis

**Usage:**
```bash
python examples/complaint_analysis_taxonomies_demo.py
```

**Key Code:**
```python
from complaint_analysis import (
    get_registered_types,
    get_keywords,
    ComplaintAnalyzer
)

# List all types
types = get_registered_types()
print(f"Complaint Types: {types}")

# Analyze each type
for complaint_type in types:
    analyzer = ComplaintAnalyzer(complaint_type=complaint_type)
    result = analyzer.analyze(sample_complaint)
    print(f"{complaint_type}: Risk={result['risk_level']}")
```

---

### 10. dei_taxonomy_example.py

**Purpose:** DEI-specific analysis demonstration.

**Features Demonstrated:**
- DEI risk scoring (0-3 algorithm)
- Binding vs aspirational language detection
- DEI provision extraction
- Context-aware analysis
- Multiple applicability domains

**Usage:**
```bash
python examples/dei_taxonomy_example.py
```

**Key Code:**
```python
from complaint_analysis import (
    DEIRiskScorer,
    DEIProvisionExtractor
)

scorer = DEIRiskScorer()
risk = scorer.calculate_risk(policy_text)
print(f"Risk: {risk['level']} ({risk['score']}/3)")

extractor = DEIProvisionExtractor()
provisions = extractor.extract_provisions(policy_text)
for prov in provisions:
    print(f"{prov['section']}: Binding={prov['is_binding']}")
```

---

### 11. hacc_integration_example.py

**Purpose:** Full DEI policy analysis pipeline (formerly HACC).

**Features Demonstrated:**
- Complete DEI analysis workflow
- Risk scoring + provision extraction
- Report generation (executive, technical, CSV, JSON)
- Multi-document analysis
- Batch processing

**Usage:**
```bash
python examples/hacc_integration_example.py
```

**Key Code:**
```python
from complaint_analysis import (
    DEIRiskScorer,
    DEIProvisionExtractor,
    DEIReportGenerator
)

scorer = DEIRiskScorer()
extractor = DEIProvisionExtractor()
generator = DEIReportGenerator(project_name="Policy Review")

# Analyze documents
for doc in documents:
    risk = scorer.calculate_risk(doc['text'])
    provisions = extractor.extract_provisions(doc['text'])
    generator.add_document_analysis(risk, provisions, doc['metadata'])

# Generate reports
reports = generator.save_reports('output/')
print(f"Reports: {list(reports.keys())}")
```

---

### 12. hacc_dei_analysis_example.py

**Purpose:** DEI analysis with synthetic policy documents.

**Features Demonstrated:**
- Synthetic policy generation
- Batch analysis
- Comparative analysis across policies
- Report aggregation

**Usage:**
```bash
python examples/hacc_dei_analysis_example.py
```

---

## Adversarial Testing Examples

### 13. adversarial_harness_example.py

**Purpose:** Basic adversarial harness usage.

**Features Demonstrated:**
- Harness setup and configuration
- Parallel session execution
- Complainant/critic/mediator interaction
- Result aggregation
- Success rate calculation

**Usage:**
```bash
python examples/adversarial_harness_example.py
```

**Key Code:**
```python
from adversarial_harness import AdversarialHarness

harness = AdversarialHarness(
    backend=backend,
    parallelism=4,
    max_retries=3
)

results = harness.run_sessions(
    complaint_types=['employment_discrimination', 'housing'],
    num_sessions_per_type=10
)

print(f"Average Score: {results['average_score']}")
print(f"Success Rate: {results['success_rate']}")
```

---

### 14. adversarial_harness_standalone.py

**Purpose:** Standalone adversarial session without harness.

**Features Demonstrated:**
- Single session orchestration
- Complainant personality configuration
- Critic evaluation
- Session result analysis

**Usage:**
```bash
python examples/adversarial_harness_standalone.py
```

**Key Code:**
```python
from adversarial_harness import (
    AdversarialSession,
    Complainant,
    Critic
)

complainant = Complainant(backend, personality='cooperative')
critic = Critic(backend)
session = AdversarialSession(mediator, complainant, critic, max_rounds=10)

result = session.run(seed_complaint)
print(f"Score: {result.critic_score.overall}")
```

---

### 15. adversarial_optimization_demo.py

**Purpose:** SGD cycle optimization demonstration.

**Features Demonstrated:**
- Stochastic gradient descent cycles
- Optimizer analysis
- Trend tracking
- Convergence detection
- Recommendation application

**Usage:**
```bash
python examples/adversarial_optimization_demo.py
```

**Key Code:**
```python
from adversarial_harness import Optimizer

optimizer = Optimizer()

for cycle in range(10):
    results = harness.run_sessions(...)
    report = optimizer.analyze_batch(results['sessions'])
    
    # Apply recommendations
    apply_recommendations(mediator, report.recommendations)
    
    if report.converged:
        print(f"Converged after {cycle + 1} cycles")
        break
```

---

### 16. batch_sgd_cycle.py

**Purpose:** Batch SGD testing with state persistence.

**Features Demonstrated:**
- Batch execution
- State persistence between cycles
- Progress tracking
- Checkpoint saving/loading

**Usage:**
```bash
python examples/batch_sgd_cycle.py
```

---

### 17. session_sgd_report.py

**Purpose:** Report generation from adversarial sessions.

**Features Demonstrated:**
- Session result analysis
- Report formatting
- Metrics aggregation
- Visualization preparation

**Usage:**
```bash
python examples/session_sgd_report.py
```

---

### 18. parallelism_backoff_sweep.py

**Purpose:** Parameter sweeping for parallelism and backoff.

**Features Demonstrated:**
- Grid search over parameters
- Performance measurement
- Optimal parameter identification
- Result comparison

**Usage:**
```bash
python examples/parallelism_backoff_sweep.py
```

**Key Code:**
```python
# Sweep parameters
parallelism_values = [1, 2, 4, 8]
backoff_values = [0.5, 1.0, 2.0]

for p in parallelism_values:
    for b in backoff_values:
        harness = AdversarialHarness(parallelism=p, backoff=b)
        results = harness.run_sessions(...)
        record_results(p, b, results)

# Find optimal
optimal = find_best_parameters(all_results)
print(f"Optimal: parallelism={optimal['p']}, backoff={optimal['b']}")
```

---

### 19. sweep_ranker.py

**Purpose:** Ranking parameter sweep results.

**Features Demonstrated:**
- Multi-objective optimization
- Pareto frontier identification
- Result visualization
- Trade-off analysis

**Usage:**
```bash
python examples/sweep_ranker.py
```

---

### 20. codex_autopatch_from_run.py

**Purpose:** Code autopatch from adversarial run results.

**Features Demonstrated:**
- Codex integration for code generation
- Automated bug fixing from critic feedback
- Code patch application
- Validation testing

**Usage:**
```bash
python examples/codex_autopatch_from_run.py
```

**Note:** Requires Codex API access.

---

### 21. codex_multi_run_autopatch.py

**Purpose:** Multi-run autopatch loop.

**Features Demonstrated:**
- Iterative code improvement
- Multiple autopatch rounds
- Regression testing
- Convergence tracking

**Usage:**
```bash
python examples/codex_multi_run_autopatch.py

# If Codex is rate-limited, wait indefinitely and optionally tune the fallback backoff:
python examples/codex_multi_run_autopatch.py \
    --codex-wait-forever-on-429 \
    --codex-wait-on-429-fallback-s 60 \
    --codex-wait-on-429-fallback-max-s 900
```

---

### 22. codex_multi_run_autopatch_loop.py

**Purpose:** Extended autopatch loop with convergence.

**Features Demonstrated:**
- Extended iteration with early stopping
- Comprehensive validation
- Performance metrics tracking
- Final report generation

**Usage:**
```bash
python examples/codex_multi_run_autopatch_loop.py

# Loop wrapper always enables --codex-wait-forever-on-429 when calling the orchestrator.
# You can tune fallback backoff for 429s without a reset timestamp:
python examples/codex_multi_run_autopatch_loop.py \
    --codex-wait-on-429-fallback-s 60 \
    --codex-wait-on-429-fallback-max-s 900
```

---

## Running Examples

### Prerequisites

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Initialize submodules:
```bash
git submodule update --init --recursive
```

3. (Optional) Set API keys:
```bash
export BRAVE_SEARCH_API_KEY="your_brave_key"
export OPENAI_API_KEY="your_openai_key"
```

### Run Individual Examples

```bash
# Run specific example
python examples/three_phase_example.py

# Run with custom config
python examples/adversarial_harness_example.py --config config.llm_router.json
```

### Run All Examples

```bash
# Run all examples sequentially
for script in examples/*.py; do
    echo "Running $script..."
    python "$script"
done
```

## Example Categories Quick Reference

| Category | Script Count | Key Features |
|----------|--------------|--------------|
| **Core System** | 6 | Three-phase workflow, legal analysis, evidence, research |
| **Complaint Analysis** | 5 | All 14 types, DEI analysis, seed generation, decision trees |
| **Adversarial Testing** | 8 | Harness, optimization, SGD cycles, parameter sweeping |
| **Advanced** | 2 | Code generation, automated patching |

## Common Patterns

### Basic Setup Pattern

Most examples follow this pattern:

```python
# 1. Import modules
from mediator import Mediator
from backends import LLMRouterBackend

# 2. Initialize backend
backend = LLMRouterBackend(
    id='llm',
    provider='copilot_cli',
    model='gpt-5-mini'
)

# 3. Initialize mediator
mediator = Mediator(backends=[backend])

# 4. Use features
result = mediator.some_feature(...)

# 5. Display results
print(result)
```

### Error Handling Pattern

Examples include error handling:

```python
try:
    result = mediator.analyze_complaint_legal_issues()
except Exception as e:
    print(f"Error: {e}")
    # Fallback behavior
```

## Customization

### Modify Backend

Change the backend in any example:

```python
# Use OpenAI instead of Copilot
backend = LLMRouterBackend(
    id='llm',
    provider='openai',
    model='gpt-4'
)
```

### Adjust Parameters

Modify parameters for different behavior:

```python
# Increase max tokens for longer responses
backend = LLMRouterBackend(
    id='llm',
    provider='copilot_cli',
    model='gpt-5-mini',
    max_tokens=1000  # Increased from default 128
)
```

### Add Custom Logic

Examples are templates - add your own logic:

```python
# Add custom processing
result = mediator.analyze_complaint_legal_issues()

# Custom analysis
if result['risk_score'] > 0.8:
    perform_additional_research()
```

## See Also

- [README.md](../README.md) - Main documentation
- [docs/THREE_PHASE_SYSTEM.md](THREE_PHASE_SYSTEM.md) - Three-phase workflow
- [docs/ADVERSARIAL_HARNESS.md](ADVERSARIAL_HARNESS.md) - Adversarial testing
- [docs/LEGAL_HOOKS.md](LEGAL_HOOKS.md) - Legal analysis
- [docs/BACKENDS.md](BACKENDS.md) - Backend configuration
