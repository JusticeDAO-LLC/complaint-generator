# Adversarial Test Harness

An LLM-based adversarial testing framework for optimizing complaint generation through multi-agent interaction and evaluation.

## Overview

The adversarial test harness implements a sophisticated system for testing and optimizing the mediator's complaint processing capabilities using three LLM-based agents:

1. **Complainant Agent** - Simulates real complainants with various personalities
2. **Mediator** (System Under Test) - Processes complaints and asks questions
3. **Critic Agent** - Evaluates interaction quality across multiple dimensions

The system uses stochastic gradient descent (SGD) cycles with parallel batch processing to iteratively improve performance based on critic feedback.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Seed Complaint Library                    │
│         (Templates + Pre-defined Complaint Scenarios)       │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  Adversarial Harness                        │
│  ┌────────────────────────────────────────────────────┐     │
│  │  Parallel Session Executor (LLM Router)            │     │
│  │  - Runs multiple sessions concurrently             │     │
│  │  - Handles failures and retries                    │     │
│  │  - Aggregates results                              │     │
│  └────────────────────────────────────────────────────┘     │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
         ┌───────────────────────────────────┐
         │    Adversarial Session            │
         │  ┌─────────────────────────────┐  │
         │  │  1. Complainant (LLM)       │  │
         │  │     - Generates complaint   │  │
         │  │     - Answers questions     │  │
         │  └─────────────────────────────┘  │
         │            ↕                      │
         │  ┌─────────────────────────────┐  │
         │  │  2. Mediator (SUT)          │  │
         │  │     - Processes complaint   │  │
         │  │     - Asks questions        │  │
         │  └─────────────────────────────┘  │
         │            ↓                      │
         │  ┌─────────────────────────────┐  │
         │  │  3. Critic (LLM)            │  │
         │  │     - Evaluates interaction │  │
         │  │     - Scores quality        │  │
         │  └─────────────────────────────┘  │
         └───────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                       Optimizer                             │
│  - Analyzes critic scores across sessions                   │
│  - Identifies patterns and trends                           │
│  - Generates optimization recommendations                   │
│  - Tracks improvement over time                             │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Adversarial Harness (`harness.py`)

**Purpose:** Orchestrates parallel execution of multiple adversarial sessions.

**Key Classes:**
- `AdversarialHarness` - Main coordinator for batch testing

**Features:**
- Parallel session execution via LLM Router
- Failure handling and automatic retries
- Result aggregation and reporting
- Configurable batch sizes and parallelism

**Example:**
```python
from adversarial_harness import AdversarialHarness
from backends import LLMRouterBackend

backend = LLMRouterBackend(id='llm', provider='copilot_cli', model='gpt-5-mini')
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

### 2. Complainant Agent (`complainant.py`)

**Purpose:** LLM-based agent that simulates real complainants.

**Key Classes:**
- `ComplaintContext` - Context information for a complaint
- `Complainant` - Main complainant agent
- `ComplaintGenerator` - Generates complaint variations

**Personality Types:**
- `cooperative` - Provides clear, complete answers
- `defensive` - Reluctant to share information
- `vague` - Provides unclear or incomplete responses
- `emotional` - Focuses on feelings over facts
- `technical` - Provides detailed factual information

**Example:**
```python
from adversarial_harness import Complainant, ComplaintContext

complainant = Complainant(backend, personality="cooperative")

context = ComplaintContext(
    complaint_type="employment_discrimination",
    key_facts={
        'employer': 'Acme Corp',
        'action': 'terminated',
        'protected_class': 'age'
    }
)
complainant.set_context(context)

# Generate initial complaint
complaint = complainant.generate_initial_complaint(seed_data)

# Respond to questions
response = complainant.respond_to_question("When did this occur?")
```

### 3. Critic Agent (`critic.py`)

**Purpose:** Evaluates mediator-complainant interaction quality.

**Key Classes:**
- `CriticScore` - Structured score with breakdown by dimension
- `Critic` - Evaluation agent

**Evaluation Dimensions:**
1. **Question Quality** (25% weight) - Relevance, clarity, legal appropriateness
2. **Information Extraction** (25% weight) - Completeness, efficiency of information gathering
3. **Empathy** (15% weight) - Tone, sensitivity, rapport building
4. **Efficiency** (15% weight) - Question count, redundancy, focus
5. **Coverage** (20% weight) - Breadth of legal issues addressed

**Example:**
```python
from adversarial_harness import Critic

critic = Critic(backend)

score = critic.evaluate_session(
    complaint=complaint_text,
    questions=mediator_questions,
    responses=complainant_responses,
    mediator_analysis=analysis_result
)

print(f"Overall Score: {score.overall}")
print(f"Question Quality: {score.question_quality}")
print(f"Information Extraction: {score.information_extraction}")
print(f"Strengths: {score.strengths}")
print(f"Weaknesses: {score.weaknesses}")
```

### 4. Adversarial Session (`session.py`)

**Purpose:** Manages a single adversarial session (one complaint through full interaction).

**Key Classes:**
- `SessionResult` - Results from a single session
- `AdversarialSession` - Session coordinator

**Features:**
- Multi-round interaction management
- Conversation history tracking
- Automatic session termination on convergence
- Detailed logging and debugging

**Example:**
```python
from adversarial_harness import AdversarialSession

session = AdversarialSession(
    mediator=mediator,
    complainant=complainant,
    critic=critic,
    max_rounds=10
)

result = session.run(seed_complaint)

print(f"Rounds: {result.num_rounds}")
print(f"Converged: {result.converged}")
print(f"Score: {result.critic_score.overall}")
```

### 5. Optimizer (`optimizer.py`)

**Purpose:** Analyzes results and generates optimization recommendations.

**Key Classes:**
- `OptimizationReport` - Structured optimization recommendations
- `Optimizer` - Analysis and recommendation engine

**Analysis Types:**
- Pattern identification across sessions
- Trend analysis over time
- Comparative analysis by complaint type
- Performance regression detection

**Example:**
```python
from adversarial_harness import Optimizer

optimizer = Optimizer()

# Analyze single batch
report = optimizer.analyze_batch(session_results)
print(f"Top Recommendations: {report.recommendations[:3]}")
print(f"Trend: {report.trend}")

# Analyze multiple batches over time
trend_report = optimizer.analyze_trends(historical_results)
print(f"Improvement Rate: {trend_report.improvement_rate}")
```

### 6. Seed Complaint Library (`seed_complaints.py`)

**Purpose:** Pre-built complaint templates for bootstrapping tests.

**Key Classes:**
- `SeedComplaintLibrary` - Template repository
- `ComplaintTemplate` - Individual template structure

**Built-in Templates:**
- Employment discrimination
- Housing discrimination
- Wrongful termination
- Consumer fraud
- Healthcare malpractice
- And more...

**Example:**
```python
from adversarial_harness import SeedComplaintLibrary

library = SeedComplaintLibrary()

# Get template
template = library.get_template('employment_discrimination')
print(f"Required Fields: {template.required_fields}")
print(f"Optional Fields: {template.optional_fields}")

# Generate complaint from template
complaint = library.generate_from_template(
    'employment_discrimination',
    employer='Acme Corp',
    action='termination',
    protected_class='age'
)
```

### HACC Evidence-Backed Seeds

When the local `HACC` repository includes `hacc_research`, `research_results`, and the
knowledge-graph artifacts, the harness can seed the complainant from that evidence
instead of generic templates.

```python
from adversarial_harness import (
    AdversarialHarness,
    DEFAULT_HACC_QUERY_SPECS,
    HACC_QUERY_PRESETS,
    SeedComplaintLibrary,
)

seed_library = SeedComplaintLibrary()

results = harness.run_batch(
    num_sessions=6,
    max_turns_per_session=6,
    include_hacc_evidence=True,
    hacc_count=4,
    hacc_preset="retaliation_focus",
    use_hacc_vector_search=False,
)
```

Available presets include:
- `full_audit`
- `housing_focus`
- `proxy_focus`
- `retaliation_focus`
- `contracting_focus`
- `administrative_plan_retaliation`
- `acop_due_process`
- `accommodation_focus`
- `core_hacc_policies`

You can still bypass presets and pass `hacc_query_specs=DEFAULT_HACC_QUERY_SPECS`
or your own custom list of query specs when you want tighter case-specific control.

The source-anchored presets are especially useful when you want the complainant to
draw from HACC's core policy artifacts directly:
- `administrative_plan_retaliation` emphasizes the `ADMINISTRATIVE PLAN`
- `acop_due_process` emphasizes the `ADMISSIONS AND CONTINUED OCCUPANCY POLICY`
- `accommodation_focus` emphasizes disability-accommodation passages in the core policies
- `core_hacc_policies` blends both documents into a single seed strategy

When anchor terms are present, the generated seed also stores `key_facts["anchor_passages"]`
so the complainant can cite concrete grievance, hearing, or accommodation snippets rather
than speaking only at the document-title level.

The seed also stores `key_facts["anchor_sections"]` and per-passage `section_labels`
such as `grievance_hearing`, `appeal_rights`, and `reasonable_accommodation`. That
gives the adversarial loop a more structured bridge into decision-tree design.

When you pass those HACC-backed sessions through `Optimizer.analyze(...)`, the report
now also includes:
- `recommended_hacc_preset`
- `hacc_preset_performance`
- `anchor_section_performance`

That makes it easier to see which local evidence strategy is producing the strongest
critic scores and which anchored sections still need better mediator branches.

Each HACC-backed seed includes:
- `key_facts["evidence_summary"]` for a short narrative grounding
- `hacc_evidence` with top supporting snippets and source paths
- complaint metadata that the complainant can use while answering mediator questions

This is useful when you want the critic and optimizer to evaluate question quality
against real local evidence rather than synthetic fact patterns.

You can also export aggregate anchor-section coverage after a batch:

```python
harness.save_anchor_section_report("anchor_section_coverage.csv", format="csv")
harness.save_anchor_section_report("anchor_section_coverage.md", format="markdown")
```

For a one-command run that emits the batch JSON, optimizer report, and anchor coverage
reports together:

```bash
python scripts/run_hacc_adversarial_report.py \
  --config config.llm_router.json \
  --preset core_hacc_policies \
  --num-sessions 4 \
  --hacc-count 4
```

To compare several presets side by side:

```bash
python scripts/run_hacc_preset_matrix.py \
  --config config.llm_router.json \
  --presets core_hacc_policies,accommodation_focus,administrative_plan_retaliation \
  --num-sessions 3
```

To synthesize a draft complaint package from the winning matrix run:

```bash
python scripts/synthesize_hacc_complaint.py \
  --matrix-summary output/hacc_preset_matrix/<timestamp>/preset_matrix_summary.json
```

When the matrix summary includes a `champion_challenger` block, the synthesis step
now prefers that rerun's `best_overall` preset automatically before falling back to
the initial matrix recommendation.

### 7. Search Integration (`search_hooks.py`)

**Purpose:** Enrich adversarial testing with legal research and web evidence.

**Key Classes:**
- `SearchEnrichedSeedGenerator` - Generate seeds enriched with search results
- `DecisionTreeEnhancer` - Enhance decision trees with legal knowledge
- `MediatorSearchIntegration` - Add search to mediation during testing

**Example:**
```python
from adversarial_harness import SearchEnrichedSeedGenerator

generator = SearchEnrichedSeedGenerator(
    legal_corpus_hook=legal_corpus_hook,
    web_search_hook=web_search_hook
)

enriched_seed = generator.generate_enriched_seed(
    complaint_type='employment_discrimination',
    include_legal_corpus=True,
    include_web_evidence=True
)

print(f"Legal Patterns: {enriched_seed['legal_patterns']}")
print(f"Web Evidence: {enriched_seed['web_evidence']}")
```

## Usage Patterns

### Basic Adversarial Session

```python
from adversarial_harness import (
    AdversarialSession,
    Complainant,
    Critic,
    SeedComplaintLibrary
)
from mediator import Mediator
from backends import LLMRouterBackend

# Setup
backend = LLMRouterBackend(id='llm', provider='copilot_cli', model='gpt-5-mini')
mediator = Mediator(backends=[backend])
complainant = Complainant(backend, personality='cooperative')
critic = Critic(backend)

# Get seed complaint
library = SeedComplaintLibrary()
seed = library.get_template('employment_discrimination').generate()

# Run session
session = AdversarialSession(mediator, complainant, critic, max_rounds=10)
result = session.run(seed)

print(f"Score: {result.critic_score.overall}")
print(f"Recommendations: {result.critic_score.recommendations}")
```

### Batch Testing with Harness

```python
from adversarial_harness import AdversarialHarness

harness = AdversarialHarness(
    backend=backend,
    parallelism=4,
    max_retries=3
)

results = harness.run_sessions(
    complaint_types=['employment_discrimination', 'housing', 'consumer'],
    num_sessions_per_type=20,
    personalities=['cooperative', 'defensive', 'vague']
)

print(f"Total Sessions: {results['total_sessions']}")
print(f"Success Rate: {results['success_rate']}")
print(f"Average Score: {results['average_score']}")
print(f"Best Performing Type: {results['best_type']}")
```

### SGD Cycle Optimization

```python
from adversarial_harness import Optimizer

optimizer = Optimizer()

# Run multiple optimization cycles
for cycle in range(10):
    # Run batch
    results = harness.run_sessions(
        complaint_types=['employment_discrimination'],
        num_sessions_per_type=10
    )
    
    # Analyze and optimize
    report = optimizer.analyze_batch(results['sessions'])
    
    # Apply recommendations
    if report.recommendations:
        apply_recommendations(mediator, report.recommendations)
    
    # Check convergence
    if report.converged:
        print(f"Converged after {cycle + 1} cycles")
        break
    
    print(f"Cycle {cycle + 1}: Score={report.average_score}, Trend={report.trend}")
```

## Testing

Comprehensive test coverage in `tests/test_adversarial_harness.py`:

- `TestComplainant` - Complainant agent functionality (6 tests)
- `TestCritic` - Critic evaluation logic (4 tests)
- `TestSeedComplaintLibrary` - Template management (3 tests)
- `TestAdversarialSession` - Session orchestration (2 tests)
- `TestAdversarialHarness` - Batch execution (2 tests)
- `TestOptimizer` - Optimization logic (1 test)

Run tests:
```bash
pytest tests/test_adversarial_harness.py -v
```

## Examples

See the `examples/` directory for complete demonstrations:

- `adversarial_harness_example.py` - Basic harness usage
- `adversarial_harness_standalone.py` - Standalone session
- `adversarial_optimization_demo.py` - SGD cycle optimization
- `batch_sgd_cycle.py` - Batch SGD testing with persistence
- `session_sgd_report.py` - Report generation from sessions
- `parallelism_backoff_sweep.py` - Parameter sweeping
- `sweep_ranker.py` - Ranking parameter combinations

## Integration with Other Modules

### Complaint Analysis Integration
- Uses seed generators for complaint templates
- Leverages decision trees for guided testing
- Integrates legal patterns for enrichment

### Search Integration
- Enriches seeds with legal corpus knowledge
- Adds web evidence to test scenarios
- Enhances decision trees with legal research

### Mediator Integration
- Tests all mediator hooks and workflows
- Validates three-phase processing
- Evaluates evidence management capabilities

## Configuration

Key configuration parameters:

- `parallelism` - Number of concurrent sessions (default: 4)
- `max_retries` - Retry count for failed sessions (default: 3)
- `max_rounds` - Maximum interaction rounds per session (default: 10)
- `personality` - Complainant behavior type (default: 'cooperative')
- `convergence_threshold` - Score threshold for early termination (default: 0.8)

## Best Practices

1. **Start Small** - Begin with single sessions before batch testing
2. **Use Appropriate Personalities** - Match personalities to test goals
3. **Monitor Convergence** - Track improvement over SGD cycles
4. **Analyze Failures** - Review failed sessions for systemic issues
5. **Iterate on Feedback** - Apply critic recommendations incrementally
6. **Test Edge Cases** - Include difficult scenarios (vague, defensive)
7. **Track Metrics** - Log scores and trends for regression detection

## See Also

- [docs/ADVERSARIAL_HARNESS.md](../docs/ADVERSARIAL_HARNESS.md) - Detailed system documentation
- [examples/adversarial_harness_example.py](../examples/adversarial_harness_example.py) - Usage examples
- [tests/test_adversarial_harness.py](../tests/test_adversarial_harness.py) - Test suite
- [docs/THREE_PHASE_SYSTEM.md](../docs/THREE_PHASE_SYSTEM.md) - Three-phase workflow integration
- [docs/SEARCH_HOOKS.md](../docs/SEARCH_HOOKS.md) - Search integration
