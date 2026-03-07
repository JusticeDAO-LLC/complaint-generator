# Search and Legal Corpus Hooks

## Overview

This document describes the search and legal corpus RAG (Retrieval-Augmented Generation) hooks that integrate Brave search and legal knowledge into both the adversarial testing framework and mediation process.

## Architecture

```
complaint_analysis (Legal Corpus)
        │
        ├─> LegalCorpusRAGHook ──────> Mediator
        │                              (Legal Research)
        │
        └─> DecisionTreeEnhancer ─────> Adversarial Testing
                                        (Tree Enhancement)

Brave Search API
        │
        ├─> WebEvidenceSearchHook ────> Mediator
        │                               (Evidence Discovery)
        │
        └─> SearchEnrichedSeedGenerator > Adversarial Testing
                                          (Seed Enrichment)
```

## Components

### 1. Legal Corpus RAG Hook

**File**: `mediator/legal_corpus_hooks.py`

Provides RAG over the legal corpus using complaint_analysis data (90+ legal patterns, 390+ keywords across 12 complaint types).

#### Key Methods

```python
from mediator import LegalCorpusRAGHook

hook = LegalCorpusRAGHook(mediator)

# Search legal corpus
results = hook.search_legal_corpus(
    query="discrimination",
    complaint_type="employment_discrimination",
    max_results=10
)

# Retrieve relevant laws for claims
laws = hook.retrieve_relevant_laws(
    claims=["age discrimination", "wrongful termination"]
)

# Enrich decision tree
enriched_tree = hook.enrich_decision_tree(
    complaint_type="employment_discrimination",
    tree_data=tree
)

# Get legal requirements
requirements = hook.get_legal_requirements("employment_discrimination")

# Suggest additional questions
suggestions = hook.suggest_questions(
    complaint_type="employment_discrimination",
    existing_questions=current_questions
)

# Inspect enhanced integration capability/flag status
registry = hook.get_capability_registry()

# Optional enhanced bundle (raw + normalized/reranked when flags enabled)
bundle = hook.search_legal_corpus_bundle(
    query="discrimination",
    complaint_type="employment_discrimination",
    max_results=10
)
```

#### Features

- **Legal Pattern Search**: Searches 90+ regex patterns for legal terms
- **Keyword Search**: Type-specific searches across 12 complaint types
- **Relevance Scoring**: Ranks results by relevance to query
- **Optional Vector Augmentation**: When `IPFS_DATASETS_ENHANCED_VECTOR=true`, normalized result bundles apply vector-ready score augmentation hints and metadata (`vector_augmented`, overlap ratio)
- **Optional Graph-Aware Reranking**: When `IPFS_DATASETS_ENHANCED_GRAPH=true` and `RETRIEVAL_RERANKER_MODE` is `graph`/`hybrid`/`auto`/`on`, normalized bundles apply graph-context overlap boosts and metadata (`graph_reranked`, overlap ratio)
- **Readiness Feedback Loop**: Graph-aware reranking also consumes dependency-graph readiness signals (incomplete claim names and unsatisfied dependency names) to prioritize retrieval records that reduce current evidence gaps (`graph_readiness_gap`, `graph_priority_overlap` metadata)
- **Optimizer-Assisted Tuning**: With `IPFS_DATASETS_ENHANCED_OPTIMIZER=true`, reranking adaptively expands boost budget for low-readiness/high-gap cases and emits tuning metadata (`graph_optimizer_tuned`, `graph_effective_max_boost`)
- **Latency Guard + Telemetry**: `RETRIEVAL_MAX_LATENCY_MS` constrains effective graph-boost ceilings for tighter budgets and emits per-run telemetry (`graph_latency_guard_applied`, `graph_run_elapsed_ms`, `graph_run_avg_boost`, `graph_run_boosted_count`)
- **Canary Rollout Control**: `RETRIEVAL_RERANKER_CANARY_PERCENT` (0-100) deterministically gates graph/optimizer reranking per request for safe staged rollout.
- **Decision Tree Enrichment**: Adds legal context to trees
- **Question Suggestion**: Identifies gaps and suggests questions
- **Requirement Extraction**: Extracts legal requirements per type

#### Use Cases

1. **During Mediation**: Search for relevant legal patterns while processing complaint
2. **Decision Tree Generation**: Enrich trees with legal knowledge
3. **Question Generation**: Suggest questions based on legal requirements
4. **Evidence Analysis**: Find legal basis for claims

### 2. Enhanced Web Evidence Hooks

**File**: `mediator/web_evidence_hooks.py`

Extended with convenience methods for legal research using Brave Search.

#### New Methods

```python
from mediator import WebEvidenceSearchHook

hook = WebEvidenceSearchHook(mediator)

# Search for legal precedents
precedents = hook.search_legal_precedents(
    claim="age discrimination in hiring",
    max_results=10
)

# Search case law
case_law = hook.search_case_law(
    complaint_type="employment_discrimination",
    jurisdiction="federal",  # Optional
    max_results=10
)

# Look up legal definitions
definitions = hook.search_legal_definitions(
    term="disparate impact",
    max_results=5
)

# Find statute text
statute = hook.search_statute_text(
    statute_name="Fair Housing Act",
    max_results=5
)
```

#### Requirements

- Brave Search API key: Set `BRAVE_SEARCH_API_KEY` environment variable
- ipfs_datasets_py submodule with BraveSearchClient

#### Features

- **Precedent Search**: Finds relevant legal precedents
- **Case Law Lookup**: Searches by type and jurisdiction
- **Definition Lookup**: Gets legal term definitions
- **Statute Retrieval**: Finds full text of statutes
- **All existing evidence discovery features**: CommonCrawl, auto-discovery, etc.

### 3. Adversarial Harness Search Hooks

**File**: `adversarial_harness/search_hooks.py`

Three classes for integrating search into adversarial testing.

#### SearchEnrichedSeedGenerator

Enriches seed templates with search results and legal corpus knowledge.

```python
from adversarial_harness import SearchEnrichedSeedGenerator

generator = SearchEnrichedSeedGenerator()

seed_template = {
    'complaint_type': 'employment_discrimination',
    'description': 'Age discrimination in the workplace',
    'required_fields': ['employer', 'date', 'discrimination_type']
}

# Enrich with Brave search
enriched = generator.enrich_seed_with_search(seed_template)

# Enrich with legal corpus
enriched = generator.enrich_seed_with_legal_corpus(seed_template)

# Full enrichment (both)
fully_enriched = generator.enrich_seed_full(seed_template)
```

**Benefits**:
- Adds real-world examples from search
- Includes legal terminology and patterns
- Improves test coverage with diverse scenarios
- Context-aware enrichment

#### DecisionTreeEnhancer

Enhances decision trees with legal corpus knowledge.

```python
from adversarial_harness import DecisionTreeEnhancer

enhancer = DecisionTreeEnhancer()

tree_data = {
    'complaint_type': 'employment_discrimination',
    'questions': {...}
}

# Enhance tree
enhanced = enhancer.enhance_decision_tree(tree_data)

# Suggest additional questions
suggestions = enhancer.suggest_additional_questions(tree_data)

# Validate question relevance
validation = enhancer.validate_question_relevance(
    question="What type of discrimination occurred?",
    complaint_type="employment_discrimination"
)
```

**Benefits**:
- Adds legal context to trees
- Identifies missing questions
- Validates question relevance
- Improves question quality

#### MediatorSearchIntegration

Integrates search into mediator during adversarial testing.

```python
from adversarial_harness import MediatorSearchIntegration

integration = MediatorSearchIntegration(mediator)

# Enhance question generation
additional_questions = integration.enhance_question_generation(
    complaint_type="employment_discrimination",
    current_questions=existing_questions
)

# Search for precedents
precedents = integration.search_for_precedents(
    claim="age discrimination"
)

# Enrich knowledge graph
enriched_graph = integration.enrich_knowledge_graph(
    graph_data=knowledge_graph,
    complaint_type="employment_discrimination"
)
```

**Benefits**:
- On-demand legal research during testing
- Knowledge graph enrichment
- Precedent discovery
- Question enhancement

## Integration Patterns

### Pattern 1: Enrich Seeds for Adversarial Testing

```python
from adversarial_harness import SearchEnrichedSeedGenerator, AdversarialHarness

# Generate enriched seeds
generator = SearchEnrichedSeedGenerator()
seed_library = SeedComplaintLibrary()

enriched_seeds = []
for template in seed_library.get_all_templates():
    enriched = generator.enrich_seed_full(template)
    enriched_seeds.append(enriched)

# Use in adversarial harness
harness = AdversarialHarness(
    llm_backend_complainant=backend1,
    llm_backend_critic=backend2,
    mediator_factory=lambda: Mediator([backend3]),
    seed_templates=enriched_seeds  # Use enriched seeds
)
```

### Pattern 2: Enhance Decision Trees During Generation

```python
from complaint_analysis import DecisionTreeGenerator
from adversarial_harness import DecisionTreeEnhancer

# Generate base tree
generator = DecisionTreeGenerator()
tree = generator.generate_tree('employment_discrimination')

# Enhance with legal corpus
enhancer = DecisionTreeEnhancer()
enhanced_tree = enhancer.enhance_decision_tree(tree.to_dict())

# Get suggestions for improvements
suggestions = enhancer.suggest_additional_questions(enhanced_tree)

# Add suggested questions
for suggestion in suggestions[:5]:
    # Add to tree...
    pass
```

### Pattern 3: Legal Research During Mediation

```python
from mediator import Mediator, LegalCorpusRAGHook, WebEvidenceSearchHook

mediator = Mediator([backend])

# Initialize hooks
legal_hook = LegalCorpusRAGHook(mediator)
web_hook = WebEvidenceSearchHook(mediator)

# During denoising phase
complaint_type = mediator.classify_complaint(complaint_text)

# Search legal corpus for relevant patterns
legal_results = legal_hook.search_legal_corpus(
    complaint_text,
    complaint_type=complaint_type
)

# Search web for precedents
precedents = web_hook.search_legal_precedents(complaint_text)

# Enrich decision tree
tree = load_decision_tree(complaint_type)
enriched_tree = legal_hook.enrich_decision_tree(complaint_type, tree)

# Use enriched tree for question generation
questions = generate_questions_from_tree(enriched_tree)
```

### Pattern 4: Validate Questions Before Asking

```python
from adversarial_harness import DecisionTreeEnhancer

enhancer = DecisionTreeEnhancer()

# Before asking a question
question = "What was the nature of the harassment?"
complaint_type = "employment_discrimination"

validation = enhancer.validate_question_relevance(question, complaint_type)

if validation['valid'] and validation['relevance_score'] > 0.5:
    # Ask the question
    response = mediator.ask_question(question)
else:
    # Skip or rephrase
    print(f"Question not relevant: {validation['reason']}")
```

## Configuration

### Environment Variables

```bash
# Required for Brave search
export BRAVE_SEARCH_API_KEY="your_api_key_here"

# Optional: Configure search behavior
export BRAVE_SEARCH_MAX_RESULTS=20
export BRAVE_SEARCH_FRESHNESS="pw"  # past week
```

### Dependencies

```python
# Required for full functionality
- ipfs_datasets_py (with BraveSearchClient)
- complaint_analysis module
- mediator module
- adversarial_harness module

# Optional
- duckdb (for evidence storage)
- IPFS backend (for evidence storage)
```

## API Reference

### LegalCorpusRAGHook

```python
class LegalCorpusRAGHook:
    def __init__(self, mediator):
        """Initialize with mediator instance."""
    
    def search_legal_corpus(
        self, 
        query: str, 
        complaint_type: Optional[str] = None,
        max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """Search legal corpus. Returns list of results with type, content, score."""
    
    def retrieve_relevant_laws(
        self,
        claims: List[str],
        complaint_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve laws for claims. Returns list of legal references."""
    
    def enrich_decision_tree(
        self,
        complaint_type: str,
        tree_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Enrich tree with legal context. Returns enhanced tree."""
    
    def get_legal_requirements(
        self,
        complaint_type: str
    ) -> Dict[str, Any]:
        """Get legal requirements. Returns requirements dict."""
    
    def suggest_questions(
        self,
        complaint_type: str,
        existing_questions: List[str]
    ) -> List[Dict[str, str]]:
        """Suggest questions. Returns list of suggestions with justification."""
```

### WebEvidenceSearchHook

```python
class WebEvidenceSearchHook:
    # ... existing methods ...
    
    def search_legal_precedents(
        self,
        claim: str,
        max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """Search for legal precedents."""
    
    def search_case_law(
        self,
        complaint_type: str,
        jurisdiction: Optional[str] = None,
        max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """Search case law."""
    
    def search_legal_definitions(
        self,
        term: str,
        max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """Search legal definitions."""
    
    def search_statute_text(
        self,
        statute_name: str,
        max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """Search statute text."""
```

### SearchEnrichedSeedGenerator

```python
class SearchEnrichedSeedGenerator:
    def __init__(self, mock_mediator=None):
        """Initialize with optional mock mediator."""
    
    def enrich_seed_with_search(
        self,
        seed_template: Dict[str, Any],
        use_brave: bool = True
    ) -> Dict[str, Any]:
        """Enrich with search results."""
    
    def enrich_seed_with_legal_corpus(
        self,
        seed_template: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Enrich with legal corpus."""
    
    def enrich_seed_full(
        self,
        seed_template: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Full enrichment (search + legal corpus)."""
```

### DecisionTreeEnhancer

```python
class DecisionTreeEnhancer:
    def __init__(self, mock_mediator=None):
        """Initialize with optional mock mediator."""
    
    def enhance_decision_tree(
        self,
        tree_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Enhance tree with legal corpus."""
    
    def suggest_additional_questions(
        self,
        tree_data: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """Suggest additional questions."""
    
    def validate_question_relevance(
        self,
        question: str,
        complaint_type: str
    ) -> Dict[str, Any]:
        """Validate question relevance."""
```

### MediatorSearchIntegration

```python
class MediatorSearchIntegration:
    def __init__(self, mediator):
        """Initialize with mediator instance."""
    
    def enhance_question_generation(
        self,
        complaint_type: str,
        current_questions: List[str]
    ) -> List[str]:
        """Enhance question generation."""
    
    def search_for_precedents(
        self,
        claim: str
    ) -> List[Dict[str, Any]]:
        """Search for legal precedents."""
    
    def enrich_knowledge_graph(
        self,
        graph_data: Dict[str, Any],
        complaint_type: str
    ) -> Dict[str, Any]:
        """Enrich knowledge graph."""
```

## Examples

See `examples/search_hooks_demo.py` for a comprehensive demonstration of all features.

```bash
python3 examples/search_hooks_demo.py
```

## Testing

```bash
# Run tests (requires pytest)
pytest tests/test_search_hooks.py -v

# Run specific test class
pytest tests/test_search_hooks.py::TestLegalCorpusRAGHook -v
```

## Troubleshooting

### Brave Search Not Working

```python
# Check if API key is set
import os
print("API Key:", "SET" if os.getenv('BRAVE_SEARCH_API_KEY') else "NOT SET")

# Check if BraveSearchClient available
try:
    from ipfs_datasets_py.web_archiving.brave_search_client import BraveSearchClient
    print("BraveSearchClient: AVAILABLE")
except ImportError as e:
    print(f"BraveSearchClient: NOT AVAILABLE - {e}")
```

### Legal Corpus Not Loading

```python
# Check complaint_analysis availability
try:
    from complaint_analysis import get_registered_types
    types = get_registered_types()
    print(f"Complaint types: {len(types)}")
except ImportError as e:
    print(f"complaint_analysis: NOT AVAILABLE - {e}")
```

### No Results from Search

```python
# Check search availability
hook = WebEvidenceSearchHook(mediator)
if not hook.brave_search:
    print("Brave search not initialized")
    # Check logs
    for log in mediator.logs:
        if 'brave' in log['type'].lower():
            print(log)
```

## Future Enhancements

1. **GraphRAG Integration**: Add graph-based RAG when available
2. **Caching Layer**: Cache search results for efficiency
3. **Advanced Ranking**: ML-based relevance ranking
4. **Multi-Source RAG**: Combine multiple legal databases
5. **Semantic Search**: Vector-based legal pattern search
6. **Citation Extraction**: Extract legal citations from results
7. **Precedent Analysis**: Analyze precedent applicability
8. **Jurisdiction Filtering**: Filter by specific jurisdictions

## References

- [Brave Search API Documentation](https://brave.com/search/api/)
- [complaint_analysis Module](./COMPLAINT_ANALYSIS_INTEGRATION.md)
- [Adversarial Harness](./ADVERSARIAL_HARNESS.md)
- [Web Evidence Discovery](./WEB_EVIDENCE_DISCOVERY.md)
