# Legal Analysis Hooks for Complaint Generator

This document describes the legal analysis hooks that have been added to the mediator to classify issues, retrieve statutes, generate requirements, and create questions.

## Overview

The legal analysis system consists of four main hooks:

1. **LegalClassificationHook** - Classifies types of legal issues in complaints
2. **StatuteRetrievalHook** - Retrieves applicable statutes based on classification
3. **SummaryJudgmentHook** - Creates requirements for summary judgment
4. **QuestionGenerationHook** - Generates targeted questions based on requirements

## Architecture

```
Complaint Text
     ↓
[LegalClassificationHook]
     ↓ (claim types, jurisdiction, legal areas)
[StatuteRetrievalHook]
     ↓ (relevant statutes)
[SummaryJudgmentHook]
     ↓ (required elements to prove)
[QuestionGenerationHook]
     ↓ (specific questions for evidence)
Question Pool
```

## Usage

### Basic Usage

```python
from mediator import Mediator
from backends import LLMRouterBackend

# Initialize mediator with LLM backend
backend = LLMRouterBackend(
    id='llm-router',
    provider='codex',
    model='gpt-5.3-codex'
)
mediator = Mediator(backends=[backend])

# Set complaint text
mediator.state.complaint = """
The plaintiff alleges that the defendant breached a written contract
for services by failing to deliver the agreed-upon work by the deadline,
causing significant financial damages.
"""

# Run full legal analysis
result = mediator.analyze_complaint_legal_issues()

# Access results
print("Claim Types:", result['classification']['claim_types'])
print("Applicable Statutes:", result['statutes'])
print("Requirements:", result['requirements'])
print("Generated Questions:", result['questions'])
```

### Step-by-Step Usage

You can also use each hook individually:

```python
# Step 1: Classify the complaint
classification = mediator.legal_classifier.classify_complaint(
    mediator.state.complaint
)
# Returns: {
#     'claim_types': ['breach of contract', ...],
#     'jurisdiction': 'federal',
#     'legal_areas': ['contract law', ...],
#     'key_facts': [...]
# }

# Step 2: Retrieve statutes
statutes = mediator.statute_retriever.retrieve_statutes(classification)
# Returns: [
#     {
#         'citation': '42 U.S.C. § 1983',
#         'title': 'Civil Rights Act',
#         'relevance': 'Applies to civil rights violations'
#     },
#     ...
# ]

# Step 3: Generate requirements
requirements = mediator.summary_judgment.generate_requirements(
    classification,
    statutes
)
# Returns: {
#     'breach of contract': [
#         'Existence of a valid contract',
#         'Plaintiff\'s performance',
#         'Defendant\'s breach',
#         'Damages'
#     ],
#     ...
# }

# Step 4: Generate questions
questions = mediator.question_generator.generate_questions(
    requirements,
    classification
)
# Returns: [
#     {
#         'question': 'Do you have a written contract with the defendant?',
#         'claim_type': 'breach of contract',
#         'element': 'Existence of a valid contract',
#         'priority': 'High',
#         'answer': None
#     },
#     ...
# ]

# Optional enhanced retrieval bundle (when IPFS_DATASETS_ENHANCED_LEGAL/SEARCH enabled)
bundle = mediator.statute_retriever.retrieve_statutes_bundle(classification)
# {
#   'raw': [...],
#   'normalized': [...]  # only present when enhanced mode enabled
# }

# Capability registry (availability + flag state)
registry = mediator.statute_retriever.get_capability_registry()
```

## Hook Details

### LegalClassificationHook

**Purpose**: Analyzes complaint text using LLM to identify legal issues.

**Input**: Complaint summary text

**Output**: Dictionary with:
- `claim_types`: List of legal claim types (e.g., "breach of contract", "negligence")
- `jurisdiction`: Level of jurisdiction ("federal", "state", "municipal")
- `legal_areas`: Areas of law involved (e.g., "contract law", "tort law")
- `key_facts`: Legally significant facts extracted from complaint

**Example**:
```python
classification = mediator.legal_classifier.classify_complaint(complaint_text)
# {
#     'claim_types': ['breach of contract', 'fraud'],
#     'jurisdiction': 'federal',
#     'legal_areas': ['contract law', 'business law'],
#     'key_facts': ['written agreement', 'failure to perform', 'damages']
# }
```

### StatuteRetrievalHook

**Purpose**: Identifies relevant statutes based on classified legal issues.

**Input**: Classification dictionary

**Output**: List of statute dictionaries with:
- `citation`: Legal citation (e.g., "42 U.S.C. § 1983")
- `title`: Statute title
- `relevance`: Why this statute is relevant
- `provenance`: Source metadata (`source_type`, `source_name`, `query`, `confidence`, `retrieved_at`, `metadata`)

**Notes**: 
- Uses LLM to identify relevant statutes
- Can be extended to use ipfs_datasets_py legal scrapers for actual statute text retrieval

**Example**:
```python
statutes = mediator.statute_retriever.retrieve_statutes(classification)
# [
#     {
#         'citation': '42 U.S.C. § 1983',
#         'title': 'Civil Rights Act',
#         'relevance': 'Applies to civil rights violations under color of law'
#     },
#     ...
# ]
```

### SummaryJudgmentHook

**Purpose**: Generates legal elements that must be proven for each claim type.

**Input**: 
- Classification dictionary
- List of applicable statutes

**Output**: Dictionary mapping claim types to lists of required elements

**Example**:
```python
requirements = mediator.summary_judgment.generate_requirements(
    classification,
    statutes
)
# {
#     'breach of contract': [
#         'Existence of a valid contract between parties',
#         'Plaintiff performed obligations under the contract',
#         'Defendant breached the contract',
#         'Plaintiff suffered damages as a result of the breach'
#     ],
#     'fraud': [
#         'Defendant made a false representation',
#         'Defendant knew the representation was false',
#         'Plaintiff relied on the representation',
#         'Plaintiff suffered damages'
#     ]
# }
```

### QuestionGenerationHook

**Purpose**: Creates specific factual questions to gather evidence for each required element.

**Input**:
- Requirements dictionary (from SummaryJudgmentHook)
- Classification dictionary

**Output**: List of question dictionaries with:
- `question`: The question text
- `claim_type`: Related claim type
- `element`: Legal element being addressed
- `priority`: Priority level (High/Medium/Low)
- `answer`: Placeholder for answer (initially None)
- `provenance`: Generation metadata including claim/element context and integration flags

**Example**:
```python
questions = mediator.question_generator.generate_questions(
    requirements,
    classification
)
# [
#     {
#         'question': 'Do you have a written contract with the defendant?',
#         'claim_type': 'breach of contract',
#         'element': 'Existence of a valid contract',
#         'priority': 'High',
#         'answer': None
#     },
#     {
#         'question': 'What is the date the contract was signed?',
#         'claim_type': 'breach of contract',
#         'element': 'Existence of a valid contract',
#         'priority': 'High',
#         'answer': None
#     },
#     ...
# ]
```

## Integration with Inquiries System

The generated questions can be integrated with the existing inquiries system:

```python
# After generating legal questions
legal_questions = mediator.question_generator.generate_questions(
    requirements,
    classification
)

# Add to state for use in inquiries
for q in legal_questions:
    mediator.state.inquiries.append({
        'question': q['question'],
        'answer': q['answer'],
        'metadata': {
            'claim_type': q['claim_type'],
            'element': q['element'],
            'priority': q['priority']
        }
    })
```

## State Storage

Legal analysis results are stored in the mediator's state:

```python
# After running analyze_complaint_legal_issues()
mediator.state.legal_classification  # Classification results
mediator.state.applicable_statutes   # Relevant statutes
mediator.state.summary_judgment_requirements  # Required elements
mediator.state.legal_questions       # Generated questions

# Retrieve later
analysis = mediator.get_legal_analysis()
```

## Extension Points

### Custom Classification Logic

You can subclass `LegalClassificationHook` to add custom classification logic:

```python
from mediator.legal_hooks import LegalClassificationHook

class CustomClassificationHook(LegalClassificationHook):
    def classify_complaint(self, complaint_text):
        # Custom pre-processing
        preprocessed = self.preprocess(complaint_text)
        
        # Call parent method
        classification = super().classify_complaint(preprocessed)
        
        # Custom post-processing
        classification['custom_field'] = self.extract_custom_info(classification)
        
        return classification
```

### Using Legal Scrapers

The `StatuteRetrievalHook` can be extended to use complaint-generator's legal adapter layer rather than importing upstream scraper modules directly:

```python
from integrations.ipfs_datasets.legal import search_us_code

class EnhancedStatuteRetrieval(StatuteRetrievalHook):
    def retrieve_statutes(self, classification):
        # Get statute citations from LLM
        statutes = super().retrieve_statutes(classification)
        
        # Retrieve actual statute text through the normalized adapter seam
        for statute in statutes:
            if 'U.S.C.' in statute['citation']:
                matches = search_us_code(statute['citation'], max_results=1)
                statute['full_text'] = matches[0].get('content', '') if matches else ''
        
        return statutes
```

## Testing

Tests are provided in `tests/test_legal_hooks.py`:

```bash
# Run legal hooks tests
pytest tests/test_legal_hooks.py -v

# Run with coverage
pytest tests/test_legal_hooks.py --cov=mediator.legal_hooks
```

## Dependencies

- **Required**: LLM backend (via mediator.query_backend)
- **Optional**: ipfs_datasets_py legal scrapers for statute text retrieval

## Future Enhancements

1. **Statute Database Integration**: Connect to actual legal databases for full statute text
2. **Case Law Retrieval**: Add hooks to retrieve relevant case law
3. **Precedent Analysis**: Analyze how similar cases were decided
4. **Evidence Checklist**: Generate checklist of required evidence
5. **Document Generation**: Auto-generate discovery requests based on requirements
6. **Timeline Analysis**: Extract and analyze temporal elements
7. **Party Identification**: Automatically identify all parties and their roles

## See Also

- `mediator/legal_hooks.py` - Implementation
- `tests/test_legal_hooks.py` - Tests
- `docs/LLM_ROUTER.md` - LLM backend configuration
- ipfs_datasets_py legal scrapers - Statute retrieval tools
