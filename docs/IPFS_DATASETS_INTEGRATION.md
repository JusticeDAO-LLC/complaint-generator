# ipfs_datasets_py Integration

## Overview

The complaint-generator system integrates with the `ipfs_datasets_py` package to leverage previous work on document processing, web archiving, and legal research capabilities.

## Adapter-First Guidance

Complaint-generator production examples should prefer `integrations/ipfs_datasets/*` imports over direct `ipfs_datasets_py.*` imports.

Use direct upstream imports in this repository's docs only when the goal is to describe upstream implementation details rather than complaint-generator integration patterns.

## Integration Points

### 1. Web Evidence Discovery (`mediator/web_evidence_hooks.py`)

**Components Used:**
- `ipfs_datasets_py.web_archiving.CommonCrawlSearchEngine` - Search archived web pages
- `integrations.ipfs_datasets.search.search_brave_web` - Current web search through the adapter seam

**Features:**
- Automatic evidence discovery from web sources
- Common Crawl archive search for historical evidence
- Brave Search API for current content
- Graceful fallback when ipfs_datasets_py is unavailable

**Usage:**
```python
from mediator import WebEvidenceSearchHook

hook = WebEvidenceSearchHook(mediator)

# Search with both engines
results = hook.search_for_evidence(
    keywords=["employment discrimination", "hostile work environment"],
    domains=["eeoc.gov", "dol.gov"],
    max_results=20
)

# Results include:
# - brave_search: Current web results
# - common_crawl: Historical archived content
```

### 2. Evidence Storage (`mediator/evidence_hooks.py`)

**Components Used:**
- `ipfs_datasets_py.ipfs_backend_router` - IPFS backend management
  - `add_bytes()` - Store evidence on IPFS
  - `cat()` - Retrieve evidence from IPFS
  - `pin()` - Pin important evidence
  - `get_ipfs_backend()` - Get backend configuration

**Features:**
- Store evidence documents on IPFS
- Content-addressable storage (CID-based)
- Automatic deduplication
- Persistent pinning for important evidence

**Usage:**
```python
from mediator import EvidenceHook

hook = EvidenceHook(mediator)

# Store evidence on IPFS
cid = hook.store_evidence(
    content=evidence_bytes,
    filename="complaint_evidence.pdf",
    user_id="user123"
)

# Retrieve evidence
evidence_data = hook.retrieve_evidence(cid)
```

### 3. Legal Authority Research (`mediator/legal_authority_hooks.py`)

**Components Used:**
- `ipfs_datasets_py.legal_scrapers` - Legal database scrapers
  - `CourtListenerAPI` - Federal and state case law
  - `JustiaAPI` - Legal resources
  - `OpinionScraperAPI` - Court opinions

**Features:**
- Search case law databases
- Fetch court opinions
- Find legal precedents
- Store legal authorities on IPFS

**Usage:**
```python
from mediator import LegalAuthorityHook

hook = LegalAuthorityHook(mediator)

# Search for relevant case law
cases = hook.search_case_law(
    query="employment discrimination",
    jurisdiction="federal",
    max_results=10
)

# Fetch specific opinion
opinion = hook.fetch_opinion(citation="42 U.S.C. § 2000e")
```

### 4. Document Processing (Future Integration)

**Available through complaint-generator adapters:**
- `integrations.ipfs_datasets.documents.parse_document_file` - normalized document parsing
- `integrations.ipfs_datasets.documents.parse_document_bytes` - in-memory parsing
- `integrations.ipfs_datasets.documents.summarize_document_parse` - stable parse summaries

**Planned Integration:**
```python
# Future: Process uploaded evidence documents through the adapter seam
from integrations.ipfs_datasets.documents import parse_document_file

document_parse = parse_document_file(pdf_path)
text = document_parse['text']
metadata = document_parse['metadata']
```

### 5. GraphRAG and PDF Knowledge Graphs

**Available through complaint-generator adapters:**
- `integrations.ipfs_datasets.graphrag.build_ontology`
- `integrations.ipfs_datasets.graphrag.validate_ontology`
- `integrations.ipfs_datasets.graphrag.run_refinement_cycle`
- `integrations.ipfs_datasets.graphrag.ingest_pdf_to_graphrag`
- `integrations.ipfs_datasets.graphrag.extract_pdf_entities`
- `integrations.ipfs_datasets.graphrag.analyze_pdf_relationships`
- `integrations.ipfs_datasets.graphrag.cross_analyze_pdf_documents`
- `integrations.ipfs_datasets.graphrag.batch_process_pdfs`
- `integrations.ipfs_datasets.graphrag.query_pdf_knowledge_graph`

```python
# Preferred: use the adapter seam rather than direct upstream imports
from integrations.ipfs_datasets.graphrag import (
    build_ontology,
    ingest_pdf_to_graphrag,
    query_pdf_knowledge_graph,
    validate_ontology,
)

ontology_result = build_ontology("\n\n".join(legal_documents))
validation_result = validate_ontology(ontology_result.get('ontology'))

pdf_result = ingest_pdf_to_graphrag(
    "/data/housing_policy.pdf",
    target_llm="gpt-5.3-codex",
)

graph_query = query_pdf_knowledge_graph(
    graph_id=pdf_result.get("document_id", ""),
    query="eligibility requirements for applicants",
    query_type="natural_language",
)
```

## Setup Instructions

### 1. Initialize Submodule

```bash
# Clone with submodules
git clone --recursive https://github.com/endomorphosis/complaint-generator.git

# Or initialize after cloning
cd complaint-generator
git submodule init
git submodule update
```

### 2. Install ipfs_datasets_py Dependencies

```bash
cd ipfs_datasets_py
pip install -r requirements.txt
cd ..
```

### 3. Configure API Keys

```bash
# Brave Search (for web evidence discovery)
export BRAVE_SEARCH_API_KEY="your_brave_search_api_key"

# Court Listener (for case law search)
export COURTLISTENER_API_TOKEN="your_courtlistener_token"

# IPFS Backend (for evidence storage)
export IPFS_BACKEND="local"  # or "pinata", "ipfs_kit", etc.
```

### 4. Verify Integration

```python
# Test web evidence discovery
from mediator import WebEvidenceSearchHook, Mediator

mediator = Mediator()
hook = WebEvidenceSearchHook(mediator)

# Should work if ipfs_datasets_py is available
results = hook.search_for_evidence(["test query"])
print(f"Brave available: {hook.brave_available}")
print(f"Common Crawl available: {hook.common_crawl_available}")
```

## Graceful Degradation

The system is designed to work with or without ipfs_datasets_py:

1. **Check Availability**: Each module checks if ipfs_datasets_py is available
2. **Feature Flags**: Set flags (e.g., `BRAVE_SEARCH_AVAILABLE`) based on availability
3. **Fallback Behavior**: Provide graceful fallback when features unavailable
4. **Error Messages**: Clear logging when features are disabled

**Example:**
```python
from integrations.ipfs_datasets.search import COMMON_CRAWL_AVAILABLE

# Later in code
if COMMON_CRAWL_AVAILABLE:
    results = self.common_crawl.search(query)
else:
    logger.warning("Common Crawl not available, skipping")
    results = []
```

## Integration Benefits

### Leveraging Previous Work

1. **Web Archiving**: Reuse battle-tested Brave Search and Common Crawl clients
2. **IPFS Storage**: Content-addressable evidence storage with deduplication
3. **Legal Scrapers**: Access to Court Listener, Justia, and other legal databases
4. **Document Processing**: OCR and text extraction from complex documents
5. **GraphRAG**: Advanced knowledge graph-based retrieval (when available)

### Avoiding Duplication

- No need to reimplement web search clients
- Reuse existing IPFS integration code
- Leverage existing legal database APIs
- Use proven document processing pipelines

### Consistent Architecture

- Same error handling patterns
- Consistent logging
- Shared configuration management
- Common authentication/API key handling

## Current Integration Status

| Component | Status | Notes |
|-----------|--------|-------|
| Brave Search | ✅ Integrated | Via `WebEvidenceSearchHook` |
| Common Crawl | ✅ Integrated | Via `WebEvidenceSearchHook` |
| IPFS Storage | ✅ Integrated | Via `EvidenceHook` |
| Legal Scrapers | ✅ Integrated | Via `LegalAuthorityHook` |
| PDF Processing | 🔄 Planned | Will integrate for document upload |
| GraphRAG | ✅ Integrated | Adapter facade delegates to upstream ontology and PDF GraphRAG tools |
| Document Indexing | 🔄 Planned | Full-text search over evidence |

**Legend:**
- ✅ Integrated and working
- 🔄 Planned for future release
- ⚠️ Partially integrated

## Testing with ipfs_datasets_py

### Unit Tests

Tests are designed to work without ipfs_datasets_py:

```python
# tests/test_web_evidence_hooks.py
import pytest

from integrations.ipfs_datasets.search import COMMON_CRAWL_AVAILABLE

@pytest.mark.skipif(not COMMON_CRAWL_AVAILABLE, 
                   reason="Requires ipfs_datasets_py")
def test_common_crawl_search():
    # Test only runs if ipfs_datasets_py available
    pass
```

### Integration Tests

```bash
# Run all tests
pytest tests/

# Run only tests that require ipfs_datasets_py
pytest tests/ -m ipfs_datasets

# Skip ipfs_datasets tests
pytest tests/ -m "not ipfs_datasets"
```

## Troubleshooting

### ipfs_datasets_py Not Found

**Problem**: `ImportError: No module named 'ipfs_datasets_py'`

**Solutions:**
1. Initialize submodule: `git submodule update --init`
2. Check path: Verify `ipfs_datasets_py/` directory exists
3. Install dependencies: `cd ipfs_datasets_py && pip install -r requirements.txt`

### API Keys Not Working

**Problem**: Web searches returning empty results

**Solutions:**
1. Set environment variable: `export BRAVE_SEARCH_API_KEY="..."`
2. Check key validity: Test with curl/httpie
3. Check rate limits: May be hitting API limits

### IPFS Backend Not Available

**Problem**: Cannot store evidence on IPFS

**Solutions:**
1. Install IPFS: Follow ipfs.io installation guide
2. Start daemon: `ipfs daemon`
3. Configure backend: `export IPFS_BACKEND="local"`

## Future Enhancements

1. **Enhanced Document Processing**: Integrate PDF processor for evidence uploads
2. **GraphRAG Integration**: Use graph-based retrieval for legal research
3. **Advanced Indexing**: Full-text search over all evidence
4. **Citation Extraction**: Automatic legal citation parsing
5. **Precedent Analysis**: Similarity matching between cases
6. **Multi-Source Federation**: Query multiple legal databases simultaneously

## References

- **ipfs_datasets_py**: https://github.com/endomorphosis/ipfs_datasets_py
- **Brave Search API**: https://brave.com/search/api/
- **Common Crawl**: https://commoncrawl.org/
- **Court Listener**: https://www.courtlistener.com/
- **IPFS**: https://ipfs.io/
