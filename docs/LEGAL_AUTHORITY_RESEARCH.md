# Legal Authority Research System

This document describes the legal authority research system that uses web archiving tools and legal scrapers from ipfs_datasets_py to automatically find and store relevant legal authorities for cases.

## Overview

The legal authority research system consists of three main hooks:

1. **LegalAuthoritySearchHook** - Searches for relevant legal authorities using multiple sources
2. **LegalAuthorityStorageHook** - Stores found authorities in DuckDB with metadata
3. **LegalAuthorityAnalysisHook** - Analyzes stored authorities and provides recommendations

## Architecture

```
Complaint Analysis → Classification
        ↓
[LegalAuthoritySearchHook]
  ↓ (Search US Code, Federal Register, Case Law, Web Archives)
Legal Authorities Found
        ↓
[LegalAuthorityStorageHook]
  ↓ (Store in DuckDB with CID references)
Authority Database
        ↓
[LegalAuthorityAnalysisHook]
  ↓ (Analyze & Generate Recommendations)
Research Insights
```

## Features

- **Multi-Source Search**: US Code, Federal Register, RECAP (case law), web archives
- **DuckDB Storage**: Fast, efficient storage with SQL queries
- **Web Archiving**: Uses Common Crawl Search Engine from ipfs_datasets_py
- **Legal Scrapers**: Integrated scrapers for federal and state law
- **Automatic Research**: Auto-research based on complaint classification
- **Citation Tracking**: Tracks legal citations for easy reference
- **Relevance Scoring**: Ranks authorities by relevance to claims

## Usage

### Basic Search

```python
from mediator import Mediator
from backends import LLMRouterBackend

# Initialize mediator
backend = LLMRouterBackend(id='llm-router', provider='copilot_cli', model='gpt-5-mini')
mediator = Mediator(backends=[backend])
mediator.state.username = 'user123'

# Search for legal authorities
results = mediator.search_legal_authorities(
    query='employment discrimination',
    claim_type='discrimination',
    search_all=True  # Search all sources
)

print(f"Found {len(results['statutes'])} statutes")
print(f"Found {len(results['regulations'])} regulations")
print(f"Found {len(results['case_law'])} cases")
```

### Store Authorities

```python
# Store found authorities in DuckDB
stored = mediator.store_legal_authorities(
    authorities=results,
    claim_type='employment discrimination',
    search_query='employment discrimination'
)

print(f"Stored {stored['statutes']} statutes")
print(f"Stored {stored['case_law']} cases")
print(f"New authority rows: {stored['total_new']}")
print(f"Reused authority rows: {stored['total_reused']}")
```

### Retrieve Stored Authorities

```python
# Get all authorities for a claim type
authorities = mediator.get_legal_authorities(claim_type='employment discrimination')

for auth in authorities:
    print(f"Type: {auth['type']}")
    print(f"Citation: {auth['citation']}")
    print(f"Title: {auth['title']}")
    print(f"Relevance: {auth['relevance_score']}")
    print()
```

### Analyze Authorities

```python
# Analyze stored authorities for a claim
analysis = mediator.analyze_legal_authorities(
    claim_type='employment discrimination'
)

print(f"Total authorities: {analysis['total_authorities']}")
print(f"By type: {analysis['by_type']}")
print(f"Recommendation: {analysis['recommendation']}")
```

### Automatic Research

```python
# Automatically research all claims in the case
mediator.state.complaint = "User alleges employment discrimination..."

# This will:
# 1. Analyze complaint and classify claims
# 2. Search for authorities for each claim
# 3. Store all found authorities
results = mediator.research_case_automatically()

print(f"Researched {len(results['claim_types'])} claim types")
for claim_type, authorities in results['authorities_stored'].items():
    coverage = results['claim_coverage_matrix'][claim_type]
    print(f"{claim_type}: {authorities['total_records']} authorities")
    print(f"  new={authorities['total_new']} reused={authorities['total_reused']}")
    print(f"  partial={coverage['status_counts']['partially_supported']} missing={coverage['status_counts']['missing']}")
```

## Storage Result Semantics

Authority storage is deduplication-aware. `store_legal_authorities(...)` returns both per-source counts and aggregate totals:

- `total_records`: Authorities processed for the call.
- `total_new`: New authority rows inserted.
- `total_reused`: Existing authority rows reused.
- `total_support_links_added`: New claim-support links created.
- `total_support_links_reused`: Existing claim-support links reused.

Per-source counters remain available with keys such as `statutes_new`, `statutes_reused`, `statutes_support_links_added`, and `statutes_support_links_reused`.

Stored authority rows are also fact-aware:

- `get_legal_authorities(...)` returns `fact_count` for each authority row.
- `get_authority_facts(authority_id)` returns the persisted fact rows extracted from the authority text.

## Legal Sources

### US Code

Search federal statutes:
```python
results = mediator.legal_authority_search.search_us_code(
    query='civil rights',
    max_results=10
)
```

### Federal Register

Search regulations and notices:
```python
results = mediator.legal_authority_search.search_federal_register(
    query='equal employment opportunity',
    start_date='2020-01-01',
    max_results=10
)
```

### Case Law (RECAP Archive)

Search court decisions:
```python
results = mediator.legal_authority_search.search_case_law(
    query='Title VII discrimination',
    jurisdiction='9th Circuit',
    max_results=10
)
```

### Web Archives

Search legal information from archived websites:
```python
results = mediator.legal_authority_search.search_web_archives(
    domain='law.cornell.edu',
    max_results=20
)
```

## Database Schema

### legal_authorities Table

```sql
CREATE TABLE legal_authorities (
    id INTEGER PRIMARY KEY,
    user_id VARCHAR,
    complaint_id VARCHAR,
    claim_type VARCHAR,
    authority_type VARCHAR NOT NULL,  -- statute, regulation, case_law, web_archive
    source VARCHAR NOT NULL,          -- us_code, federal_register, recap, web
    citation VARCHAR,                 -- Legal citation (e.g., "42 U.S.C. § 1983")
    title TEXT,
    content TEXT,
    url VARCHAR,
    metadata JSON,
    relevance_score FLOAT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    search_query VARCHAR
)
```

### legal_authority_facts Table

```sql
CREATE TABLE legal_authority_facts (
    authority_id BIGINT,
    fact_id VARCHAR,
    fact_text TEXT,
    source_authority_id VARCHAR,
    confidence FLOAT,
    metadata JSON,
    provenance JSON
)
```

### Indexes

- `idx_authorities_user` - Fast user-specific queries
- `idx_authorities_claim` - Filter by claim type
- `idx_authorities_citation` - Lookup by citation

## Configuration

### DuckDB Location

Default: `statefiles/legal_authorities.duckdb`

Custom path:
```python
mediator = Mediator(
    backends=[backend],
    legal_authority_db_path='/custom/path/authorities.duckdb'
)
```

### Web Archiving

The system uses Common Crawl Search Engine from ipfs_datasets_py:

```python
# Configured automatically in LegalAuthoritySearchHook
# Uses local mode by default
```

Environment variables:
```bash
# Configure web archiving backend
export IPFS_DATASETS_PY_WEB_ARCHIVE_MODE=local
```

## Integration with Legal Analysis

The legal authority system integrates with existing legal analysis hooks:

```python
# 1. Analyze complaint
legal_analysis = mediator.analyze_complaint_legal_issues()

# 2. Automatically research authorities
research_results = mediator.research_case_automatically()

# 3. Analyze stored authorities
for claim_type in legal_analysis['classification']['claim_types']:
    authority_analysis = mediator.analyze_legal_authorities(claim_type)
    coverage = research_results['claim_coverage_matrix'][claim_type]
    print(f"Analysis for {claim_type}:")
    print(authority_analysis['recommendation'])
    print(f"Missing elements: {coverage['status_counts']['missing']}")
```

## API Reference

### Mediator Methods

#### `search_legal_authorities(query, claim_type=None, jurisdiction=None, search_all=False)`

Search for legal authorities.

**Args:**
- `query` (str): Search query
- `claim_type` (str, optional): Claim type to focus search
- `jurisdiction` (str, optional): Jurisdiction filter
- `search_all` (bool): If True, search all sources

**Returns:** Dictionary with results by source type

#### `store_legal_authorities(authorities, claim_type=None, search_query=None, user_id=None)`

Store found authorities in DuckDB.

**Args:**
- `authorities` (dict): Authorities by type (from search_legal_authorities)
- `claim_type` (str, optional): Claim type
- `search_query` (str, optional): Original query
- `user_id` (str, optional): User identifier

**Returns:** Dictionary with count of stored authorities

#### `get_legal_authorities(user_id=None, claim_type=None)`

Retrieve stored authorities.

**Args:**
- `user_id` (str, optional): User identifier
- `claim_type` (str, optional): Filter by claim type

**Returns:** List of authority records

#### `analyze_legal_authorities(claim_type, user_id=None)`

Analyze authorities for a claim.

**Args:**
- `claim_type` (str): Claim type to analyze
- `user_id` (str, optional): User identifier

**Returns:** Analysis with recommendations

#### `research_case_automatically(user_id=None)`

Automatically research all claims in the case.

**Args:**
- `user_id` (str, optional): User identifier

**Returns:** Dictionary with research results

Per-claim results include:

- `authorities_stored[claim_type]`: storage and deduplication counts for the authority batch.
- `support_summary[claim_type]`: raw persisted support-link summary.
- `claim_overview[claim_type]`: covered, partially supported, and missing element buckets.
- `claim_coverage_matrix[claim_type]`: grouped claim-element support with `links_by_kind`, `missing_support_kinds`, inline record or graph summaries, and per-element support-packet lineage rollups.
- `claim_coverage_summary[claim_type]`: compact coverage counts plus missing, unresolved, contradiction, and support-packet lineage labels.
- `claim_support_gaps[claim_type]`: unresolved-element diagnostics with recommended actions.
- `claim_contradiction_candidates[claim_type]`: heuristic contradiction candidates for operator review.
- `claim_support_snapshots[claim_type]`: persisted snapshot ids and metadata for the stored gap and contradiction diagnostics.
- `follow_up_plan[claim_type]`: next-step authority or evidence retrieval tasks derived from the current support gaps.

## Advanced Usage

### Custom Relevance Scoring

```python
# Add authorities with custom relevance scores
authority = {
    'type': 'statute',
    'source': 'us_code',
    'citation': '42 U.S.C. § 1983',
    'title': 'Civil Rights Act',
    'content': '...',
    'relevance_score': 0.95  # High relevance
}

mediator.legal_authority_storage.add_authority(
    authority,
    user_id='user123',
    claim_type='civil rights violation'
)
```

### Batch Research Multiple Claims

```python
claim_types = ['breach of contract', 'fraud', 'negligence']

for claim_type in claim_types:
    # Search
    results = mediator.search_legal_authorities(
        query=claim_type,
        search_all=True
    )
    
    # Store
    mediator.store_legal_authorities(
        results,
        claim_type=claim_type
    )
    
    # Analyze
    analysis = mediator.analyze_legal_authorities(claim_type)
    print(f"{claim_type}: {analysis['total_authorities']} authorities")
```

### Export Authorities

```python
# Get all authorities
authorities = mediator.get_legal_authorities()

# Export to JSON for review
import json
with open('legal_authorities.json', 'w') as f:
    json.dump(authorities, f, indent=2)
```

## Dependencies

Required:
- `duckdb>=0.9.0` - For storage

Optional (from ipfs_datasets_py):
- `requests` - For web scraping
- `beautifulsoup4` - For HTML parsing
- Common Crawl Search Engine - For web archiving

Install:
```bash
pip install duckdb>=0.9.0
```

## Troubleshooting

### Legal Scrapers Not Available

If legal scrapers are not available:
```
[legal_authority_warning] Legal scrapers not fully available
```

The system will still work but with limited functionality. Initialize the ipfs_datasets_py submodule:
```bash
git submodule update --init --recursive
```

### Web Archiving Not Available

If web archiving is disabled:
```
[legal_authority_warning] Web archiving not available
```

Web archive search will be disabled but other sources will still work.

### No Results Found

If searches return no results:
1. Check internet connectivity
2. Verify ipfs_datasets_py submodule is initialized
3. Try more specific search queries
4. Check if legal databases are accessible

## See Also

- `mediator/legal_authority_hooks.py` - Implementation
- `tests/test_legal_authority_hooks.py` - Tests
- `docs/LEGAL_HOOKS.md` - Legal analysis system
- `docs/EVIDENCE_MANAGEMENT.md` - Evidence storage system
- ipfs_datasets_py/legal_scrapers - Legal scraper implementations
- ipfs_datasets_py/web_archiving - Web archiving tools
