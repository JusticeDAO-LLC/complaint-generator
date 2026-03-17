# Three-Phase Complaint Processing System

## Overview

The complaint-generator now implements a sophisticated three-phase complaint processing system that combines knowledge graphs, dependency graphs, and neurosymbolic AI to create formal legal complaints. This system is inspired by denoising diffusion techniques and uses an iterative refinement approach to progressively improve the quality and completeness of complaints.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    PHASE 1: INTAKE                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Initial Complaint Text                              │   │
│  └──────────────┬───────────────────────────────────────┘   │
│                 │                                            │
│                 ▼                                            │
│  ┌──────────────────────────┐  ┌────────────────────────┐   │
│  │   Knowledge Graph        │  │  Dependency Graph      │   │
│  │  (Entities & Relations)  │  │  (Claims & Reqs)       │   │
│  └──────────────────────────┘  └────────────────────────┘   │
│                 │                          │                 │
│                 └──────────┬───────────────┘                 │
│                            ▼                                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │   Denoising Questions                                │   │
│  │   (Fill gaps, reduce uncertainty)                    │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  PHASE 2: EVIDENCE                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Identify Evidence Gaps                              │   │
│  └──────────────┬───────────────────────────────────────┘   │
│                 │                                            │
│                 ▼                                            │
│  ┌──────────────────────────┐  ┌────────────────────────┐   │
│  │  User-Submitted Evidence │  │  Auto-Discovered       │   │
│  │  (Documents, Testimony)  │  │  Evidence (Web)        │   │
│  └──────────────────────────┘  └────────────────────────┘   │
│                 │                          │                 │
│                 └──────────┬───────────────┘                 │
│                            ▼                                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │   Enhanced Knowledge & Dependency Graphs             │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              PHASE 3: FORMALIZATION                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Legal Graph (Statutes, Requirements, Procedures)    │   │
│  └──────────────┬───────────────────────────────────────┘   │
│                 │                                            │
│                 ▼                                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │   Neurosymbolic Matching                             │   │
│  │   (Facts ↔ Legal Requirements)                       │   │
│  └──────────────┬───────────────────────────────────────┘   │
│                 │                                            │
│                 ▼                                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │   Formal Complaint Document                          │   │
│  │   (Title, Parties, Claims, Facts, Relief)            │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Knowledge Graph (`complaint_phases/knowledge_graph.py`)

**Purpose:** Represent the facts, entities, and relationships from the complaint.

**Key Classes:**
- `Entity`: Represents people, organizations, dates, facts, claims
- `Relationship`: Represents connections between entities (employed_by, caused_by, etc.)
- `KnowledgeGraph`: Container for entities and relationships with gap detection
- `KnowledgeGraphBuilder`: Constructs graphs from complaint text

**Features:**
- Entity extraction from text
- Relationship inference
- Gap detection (low confidence, isolated entities, unsupported claims)
- Merge capability for iterative enhancement
- JSON serialization for persistence

### 2. Dependency Graph (`complaint_phases/dependency_graph.py`)

**Purpose:** Track what each claim requires and whether requirements are satisfied.

**Key Classes:**
- `DependencyNode`: Represents claims, requirements, facts, evidence, legal elements
- `Dependency`: Represents dependencies (requires, supports, contradicts)
- `DependencyGraph`: Container tracking satisfaction of requirements
- `DependencyGraphBuilder`: Constructs dependency structures from claims

**Features:**
- Requirement satisfaction tracking
- Claim readiness assessment
- Evidence-to-claim linking
- Gap identification
- JSON serialization

### 3. Complaint Denoiser (`complaint_phases/denoiser.py`)

**Purpose:** Iteratively ask questions to fill gaps and reduce uncertainty.

**Key Class:** `ComplaintDenoiser`

**Features:**
- Question generation from knowledge/dependency gaps
- Answer processing to update graphs
- Noise level calculation (0.0 = perfect, 1.0 = maximum uncertainty)
- Question prioritization (high/medium/low)
- Exhaustion detection

**Metrics:**
- Knowledge graph confidence (entity confidence scores)
- Dependency satisfaction (ratio of satisfied requirements)
- Gap ratio (number of gaps / total entities)
- Combined noise metric for convergence detection

### 4. Phase Manager (`complaint_phases/phase_manager.py`)

**Purpose:** Orchestrate transitions between phases and track progress.

**Key Classes:**
- `ComplaintPhase`: Enum (INTAKE, EVIDENCE, FORMALIZATION)
- `PhaseManager`: Manages phase transitions and completion criteria

**Features:**
- Phase completion checking
- Iteration tracking with loss/noise history
- Convergence detection
- Next action recommendations
- State serialization

**Completion Criteria:**
- **Phase 1 (INTAKE):** Knowledge/dependency graphs built, gaps addressed, convergence reached
- **Phase 2 (EVIDENCE):** Evidence gathered, graphs enhanced, gap ratio < 30%
- **Phase 3 (FORMALIZATION):** Legal graph built, matching complete, formal complaint generated

### Phase 2 Enhanced Graph Augmentation (IPFS Integrations)

When `IPFS_DATASETS_ENHANCED_GRAPH=true`, mediator can enrich Phase 2 graphs from cached normalized retrieval artifacts:

- `last_legal_authorities_normalized`
- `last_web_evidence_normalized`

The enrichment path converts these artifacts into evidence payloads and injects them into:

- Knowledge Graph as `evidence` entities and `supports` relationships
- Dependency Graph via existing evidence-to-claim links

This flow is integrated into `advance_to_evidence_phase()` and can also be invoked directly through `enrich_graphs_with_retrieval_artifacts()`.

### 5. Legal Graph (`complaint_phases/legal_graph.py`)

**Purpose:** Represent legal requirements, statutes, and procedural rules.

**Key Classes:**
- `LegalElement`: Statutes, regulations, requirements, procedural rules
- `LegalRelation`: Relationships between legal elements
- `LegalGraph`: Container for legal knowledge
- `LegalGraphBuilder`: Constructs legal graphs from statutes and rules

**Features:**
- Statute-to-requirement extraction
- Rules of civil procedure representation
- Jurisdiction-specific requirements
- Requirement-to-claim-type mapping

### 6. Neurosymbolic Matcher (`complaint_phases/neurosymbolic_matcher.py`)

**Purpose:** Match complaint facts against legal requirements using hybrid reasoning.

**Key Class:** `NeurosymbolicMatcher`

**Matching Approaches:**
- **Symbolic:** Graph pattern matching, logical inference from dependency graph
- **Semantic:** LLM-based similarity assessment (when available)
- **Hybrid:** Combination of both for robust matching

**Features:**
- Claim-to-law matching
- Requirement satisfaction checking
- Claim viability assessment
- Fact-finding recommendations
- Gap identification

## Usage

### Basic Three-Phase Workflow

```python
from mediator.mediator import Mediator

# Initialize with LLM backend
mediator = Mediator([your_llm_backend])

# PHASE 1: Start intake
result = mediator.start_three_phase_process(complaint_text)

# Answer denoising questions
for question in result['initial_questions']:
    answer = get_user_input(question['question'])
    update = mediator.process_denoising_answer(question, answer)
    
    if update.get('ready_for_evidence_phase'):
        break

# PHASE 2: Evidence gathering
evidence_status = mediator.advance_to_evidence_phase()

# Add evidence
mediator.add_evidence_to_graphs({
    'name': 'Employment Contract',
    'type': 'document',
    'supports_claims': ['claim_id'],
    'confidence': 0.9
})

# PHASE 3: Formalization
formal_status = mediator.advance_to_formalization_phase()

# Generate formal complaint
complaint = mediator.generate_formal_complaint()

# Save graphs
mediator.save_graphs_to_statefiles('my_complaint')
```

### Checking Status

```python
# Get current status
status = mediator.get_three_phase_status()
print(f"Phase: {status['current_phase']}")
print(f"Iterations: {status['iteration_count']}")
print(f"Phases complete: {status['phase_completion']}")
```

### Working with Graphs Directly

```python
from complaint_phases import KnowledgeGraphBuilder, DependencyGraphBuilder

# Build knowledge graph
kg_builder = KnowledgeGraphBuilder()
kg = kg_builder.build_from_text(complaint_text)

# Analyze gaps
gaps = kg.find_gaps()
for gap in gaps:
    print(f"{gap['type']}: {gap['suggested_question']}")

# Build dependency graph
dg_builder = DependencyGraphBuilder()
claims = [{'name': 'Discrimination', 'type': 'employment_discrimination'}]
dg = dg_builder.build_from_claims(claims)

# Check claim readiness
readiness = dg.get_claim_readiness()
print(f"Ready claims: {readiness['ready_claims']}/{readiness['total_claims']}")
```

## Denoising Process

The denoising process is inspired by diffusion models but applied to text and knowledge:

1. **Initial State:** High noise - incomplete, uncertain information
2. **Iterative Refinement:** Ask targeted questions to fill gaps
3. **Convergence:** Noise decreases as information becomes complete and confident
4. **Completion:** When noise stabilizes or question pool exhausted

**Noise Calculation:**
```
noise = (1 - entity_confidence) * 0.4 +
        (1 - dependency_satisfaction) * 0.4 +
        gap_ratio * 0.2
```

**Convergence Detection:**
- Track noise over sliding window (e.g., last 5 iterations)
- Converged when max_change < threshold (e.g., 0.01)

## Neurosymbolic Matching

The neurosymbolic matcher combines two paradigms:

### Symbolic Reasoning
- Graph pattern matching
- Logical dependency checking
- Explicit requirement satisfaction rules

### Neural/Semantic Reasoning  
- LLM-based similarity assessment
- Contextual understanding
- Flexible interpretation

### Hybrid Approach
```python
def check_requirement(legal_req, facts):
    # 1. Symbolic check
    if dependency_graph_shows_satisfied(legal_req):
        return True, 1.0
    
    # 2. Semantic check
    if llm_assesses_satisfied(legal_req, facts):
        return True, 0.8
    
    return False, 0.0
```

## Graph Storage

All graphs are stored as JSON in the `statefiles/` directory:

```
statefiles/
├── complaint_123_knowledge_graph.json
├── complaint_123_dependency_graph.json
├── complaint_123_legal_graph.json
└── complaint_123_phase_state.json
```

Each graph includes:
- Metadata (created_at, last_updated, version)
- Full graph structure (entities/nodes, relationships/dependencies)
- Confidence scores
- Source attribution

## Testing

Run all tests:
```bash
pytest tests/test_complaint_phases.py -v
pytest tests/test_mediator_three_phase.py -v
```

## Examples

See `examples/three_phase_example.py` for a complete demonstration.

## Integration with Existing Features

The three-phase system integrates with existing mediator capabilities:

- **Legal Analysis Hooks:** Used to extract claims and legal requirements
- **Evidence Hooks:** Evidence automatically added to graphs
- **Web Evidence Discovery:** Auto-discovered evidence enhances graphs
- **Legal Authority Research:** Retrieved authorities populate legal graph

## Performance Considerations

- **Graph Size:** Typical complaints generate 10-50 entities, 20-100 relationships
- **Iteration Count:** Usually converges in 5-15 iterations
- **Memory:** Graphs are lightweight, stored as dictionaries
- **Persistence:** JSON serialization enables resumption across sessions

## Future Enhancements

Potential improvements for future versions:

1. **LLM Integration:** Full entity/relationship extraction via LLM
2. **Graph Embeddings:** Vector representations for semantic search
3. **Multi-modal Evidence:** Images, videos integrated into knowledge graph
4. **Interactive Visualization:** Web-based graph visualization UI
5. **Template Library:** Pre-built legal requirement graphs for common claim types
6. **Collaborative Graphs:** Multiple users contributing to shared graph
7. **Version Control:** Track graph changes over time

## References

- Denoising Diffusion Probabilistic Models (Ho et al., 2020)
- Knowledge Graph Construction and Reasoning
- Neurosymbolic AI (Combining Neural and Symbolic Approaches)
- Legal Ontologies and Reasoning Systems

## Support

For questions or issues with the three-phase system:
1. Check documentation and examples
2. Review test cases for usage patterns
3. File an issue on GitHub
