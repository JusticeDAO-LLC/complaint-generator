# Web Evidence Discovery System

This document describes the web evidence discovery system that automatically finds evidence using web archiving tools and search engines from ipfs_datasets_py.

## Overview

The web evidence discovery system uses multiple web sources to automatically locate relevant evidence:

1. **Brave Search** - Current web content search
2. **Common Crawl Search Engine** - Historical archived web pages
3. **Web Archive tools** - Additional archiving capabilities
4. **Multi-engine search orchestration** - Aggregated search across multiple engines
5. **Archived domain sweeps** - Domain-first archive retrieval for better coverage

This system discovers evidence automatically and stores it alongside user-submitted evidence.

## Architecture

```
Complaint/Claim Analysis
        ↓
Generate Search Keywords
        ↓
[WebEvidenceSearchHook]
  ↓ (Search Brave, Common Crawl, Web Archives)
Web Evidence Found
        ↓
[Validate Evidence]
  ↓ (Check relevance, quality)
Validated Evidence
        ↓
[Store in IPFS + DuckDB]
  ↓ (Automatic evidence records)
Evidence Database
```

## Features

- **Multi-Source Search**: Brave Search (current), Common Crawl (historical)
- **Extended Source Orchestration**: Multi-engine aggregation and archived domain sweeps
- **Automatic Discovery**: Generate keywords from claims
- **Relevance Validation**: AI-powered relevance scoring
- **IPFS Storage**: Store discovered evidence immutably
- **DuckDB Tracking**: Track source, relevance, auto-discovery
- **User Integration**: Works alongside manually submitted evidence
- **Agentic Scraper Loop**: Iterative scrape, review, critique, and tactic reweighting for coverage growth

## Usage

### Basic Web Evidence Search

```python
from mediator import Mediator
from backends import LLMRouterBackend

# Initialize mediator
backend = LLMRouterBackend(id='llm-router', provider='copilot_cli', model='gpt-5-mini')
mediator = Mediator(backends=[backend])
mediator.state.username = 'user123'

# Search for evidence (without storing)
results = mediator.search_web_for_evidence(
    keywords=['employment discrimination', 'wrongful termination'],
    domains=['eeoc.gov', 'dol.gov'],
    max_results=20
)

print(f"Found {results['total_found']} evidence items")
print(f"Brave Search: {len(results['brave_search'])}")
print(f"Common Crawl: {len(results['common_crawl'])}")
print(f"Multi-engine: {len(results['multi_engine_search'])}")
print(f"Archive sweeps: {len(results['archived_domain_scrape'])}")
```

### Agentic Scraper Loop

```python
daemon_result = mediator.run_agentic_scraper_cycle(
    keywords=['employment discrimination', 'retaliation'],
    domains=['eeoc.gov', 'dol.gov'],
    iterations=3,
    sleep_seconds=0.0,
    quality_domain='caselaw',
)

print(len(daemon_result['iterations']))
print(len(daemon_result['final_results']))
print(sorted(daemon_result['coverage_ledger'].keys())[:3])
```

Each iteration records tactic-level discovery counts, accepted and scraped counts, quality scores, coverage metrics, and critique recommendations that are used to reweight the next pass.

### Standalone CLI

The repository includes a standalone command for running and inspecting the scraper daemon outside the interactive complaint flow.

```bash
python scripts/agentic_scraper_cli.py enqueue \
    --keywords employment discrimination retaliation \
    --domains eeoc.gov dol.gov \
    --iterations 3

python scripts/agentic_scraper_cli.py worker --once
python scripts/agentic_scraper_cli.py queue --user-id cli-user

python scripts/agentic_scraper_cli.py run \
    --keywords employment discrimination retaliation \
    --domains eeoc.gov dol.gov \
    --iterations 3

python scripts/agentic_scraper_cli.py history --user-id cli-user
python scripts/agentic_scraper_cli.py detail 1 --json
python scripts/agentic_scraper_cli.py tactics --user-id cli-user
```

Use `enqueue` plus `worker` for daemon-style operation. The worker only executes claimed queue items, so an empty queue results in an idle poll or a clean exit with `--once` instead of launching a scrape cycle.

### Discover and Store Evidence

```python
# Discover and automatically store relevant evidence
result = mediator.discover_web_evidence(
    keywords=['employment discrimination', 'retaliation'],
    domains=['eeoc.gov'],
    claim_type='employment discrimination',
    min_relevance=0.6  # Only store evidence with 60%+ relevance
)

print(f"Discovered: {result['discovered']}")
print(f"Validated: {result['validated']}")
print(f"Stored: {result['stored']}")
print(f"New records: {result['total_new']}")
print(f"Reused records: {result['total_reused']}")
print(f"New support links: {result['total_support_links_added']}")
print(f"Skipped: {result['skipped']}")
print(f"CIDs: {result['evidence_cids']}")
```

### Automatic Evidence Discovery for Case

```python
# Set up the case
mediator.state.complaint = """
The plaintiff was terminated after reporting safety violations.
Claims include wrongful termination and retaliation.
"""

# Automatically discover evidence for all claims
results = mediator.discover_evidence_automatically()

print(f"Claims analyzed: {results['claim_types']}")
for claim_type, count in results['evidence_discovered'].items():
    stored = results['evidence_stored'][claim_type]
    storage_summary = results['evidence_storage_summary'][claim_type]
    print(f"{claim_type}: {count} discovered, {stored} stored")
    print(f"  new={storage_summary['total_new']} reused={storage_summary['total_reused']}")
```

## Result Semantics

The discovery payload distinguishes raw processing counts from deduplicated storage outcomes:

- `stored`: Number of evidence items that completed the storage workflow.
- `stored_new`: Number of brand-new evidence rows inserted into DuckDB.
- `reused`: Number of items that resolved to an existing evidence row.
- `total_records`: Aggregate count of processed evidence records for the request.
- `total_new`: Aggregate count of newly inserted evidence rows.
- `total_reused`: Aggregate count of reused evidence rows.
- `support_links_added`: Number of new claim-support links created.
- `support_links_reused`: Number of claim-support links that already existed.
- `total_support_links_added`: Aggregate new support-link count.
- `total_support_links_reused`: Aggregate reused support-link count.

When evidence is projected into the active knowledge graph, each entry in `graph_projection` also reports whether the graph changed or the artifact was already present.

Web discovery responses also include parse-level reporting derived from each stored artifact's `document_parse_summary`:

- `parse_summary.processed`: Number of stored records for which parse metadata was examined.
- `parse_summary.total_chunks`: Aggregate parsed chunk count across stored results.
- `parse_summary.total_paragraphs`: Aggregate paragraph count across stored results.
- `parse_summary.total_text_length`: Aggregate normalized text length across stored results.
- `parse_summary.status_counts`: Parse status frequencies such as `fallback` or `available-fallback`.
- `parse_summary.input_format_counts`: Aggregate counts by normalized input format such as `text` or `html`.
- `parse_summary.parser_versions`: Distinct parser versions encountered in the request.
- `parse_details`: Per-record parse summary entries keyed by CID.

### Retrieve Discovered Evidence

```python
# Get all evidence (user-submitted + auto-discovered)
all_evidence = mediator.get_user_evidence()

# Filter for auto-discovered evidence
auto_evidence = [
    e for e in all_evidence 
    if e.get('metadata', {}).get('auto_discovered')
]

for evidence in auto_evidence:
    print(f"Type: {evidence['type']}")
    print(f"Source: {evidence['metadata']['source_type']}")
    print(f"URL: {evidence['metadata']['source_url']}")
    print(f"Relevance: {evidence['metadata']['relevance_score']}")
    print(f"CID: {evidence['cid']}")
    print()
```

## Search Sources

### Brave Search

Searches current web content using Brave Search API.

**Requirements:**
- Set `BRAVE_SEARCH_API_KEY` environment variable
- Available through ipfs_datasets_py.web_archiving.brave_search_client

**Features:**
- Real-time web search
- Freshness filters (past day, week, month)
- High-quality results
- Rate limiting and caching

**Configuration:**
```bash
export BRAVE_SEARCH_API_KEY="your_api_key_here"
```

### Common Crawl Search Engine

Searches historical web pages from Common Crawl archives.

**Features:**
- Billions of archived pages
- Historical evidence retrieval
- Domain-specific search
- No API key required

**Use Cases:**
- Finding historical evidence
- Archived company policies
- Past website content
- Historical documentation

### Web Archive Tools

Additional archiving capabilities from ipfs_datasets_py.

**Features:**
- Multiple archive sources
- Content extraction
- Metadata tracking

## Evidence Validation

Each discovered piece of evidence is validated:

```python
validation = {
    'valid': True,          # Has required fields
    'relevance_score': 0.8, # AI-assessed relevance (0.0 to 1.0)
    'issues': [],           # Any validation issues
    'recommendations': []   # Suggestions from AI
}
```

### Relevance Scoring

Evidence relevance is scored using:
1. **Default Score**: 0.5-0.7 based on source type
2. **LLM Assessment**: AI evaluates title, URL, and content
3. **Context Matching**: Keywords and claim type alignment

### Minimum Relevance Threshold

Set `min_relevance` to control quality:
- `0.5` - Moderate threshold (more results)
- `0.6` - Balanced (recommended)
- `0.7` - High quality only (fewer results)
- `0.8` - Very selective

## Evidence Metadata

Auto-discovered evidence includes additional metadata:

```json
{
    "cid": "QmXxxx...",
    "type": "web_document",
    "metadata": {
        "source_type": "brave_search",
        "source_url": "https://example.com/evidence",
        "auto_discovered": true,
        "relevance_score": 0.85,
        "keywords": ["employment", "discrimination"],
        "discovered_at": "2024-01-15T10:30:00"
    }
}
```

## API Reference

### Mediator Methods

#### `search_web_for_evidence(keywords, domains=None, max_results=20)`

Search web sources without storing.

**Args:**
- `keywords` (List[str]): Search keywords
- `domains` (List[str], optional): Specific domains to search
- `max_results` (int): Maximum results per source

**Returns:** Dictionary with results by source type

Typical keys now include `brave_search`, `common_crawl`, `multi_engine_search`, `archived_domain_scrape`, and `total_found`.

#### `discover_web_evidence(keywords, domains=None, user_id=None, claim_type=None, min_relevance=0.5)`

Discover and store evidence.

**Args:**
- `keywords` (List[str]): Search keywords
- `domains` (List[str], optional): Specific domains
- `user_id` (str, optional): User identifier
- `claim_type` (str, optional): Associated claim
- `min_relevance` (float): Minimum relevance (0.0 to 1.0)

**Returns:** Dictionary with discovery statistics

Typical keys include:

```json
{
    "discovered": 3,
    "validated": 2,
    "stored": 2,
    "stored_new": 1,
    "reused": 1,
    "total_records": 2,
    "total_new": 1,
    "total_reused": 1,
    "support_links_added": 2,
    "support_links_reused": 0,
    "total_support_links_added": 2,
    "total_support_links_reused": 0,
    "graph_projection": [
        {
            "graph_changed": true,
            "artifact_entity_added": true,
            "artifact_entity_already_present": false,
            "storage_record_created": true,
            "storage_record_reused": false,
            "support_link_created": true,
            "support_link_reused": false
        }
    ]
}
```

#### `discover_evidence_automatically(user_id=None)`

Automatically discover evidence for all case claims.

**Args:**
- `user_id` (str, optional): User identifier

**Returns:** Dictionary with results per claim type

Per-claim results now include both the legacy count in `evidence_stored[claim_type]` and the full deduplicated breakdown in `evidence_storage_summary[claim_type]`.

#### `run_agentic_scraper_cycle(keywords, domains=None, iterations=1, sleep_seconds=0.0, quality_domain='caselaw')`

Run a bounded scrape-review-critique-optimize loop.

**Args:**
- `keywords` (List[str]): Seed search terms
- `domains` (List[str], optional): Domains to prioritize during archive sweeps
- `iterations` (int): Number of tactic-optimization passes
- `sleep_seconds` (float): Delay between iterations
- `quality_domain` (str): Validation domain used by the scraper-quality scorer

**Returns:** Dictionary with iteration reports, final deduplicated results, tactic history, and coverage ledger.

## Advanced Usage

### Custom Keyword Generation

```python
# Generate targeted keywords for specific claim
keywords = mediator.web_evidence_integration._generate_search_keywords(
    'employment discrimination'
)
print(f"Generated keywords: {keywords}")

# Use custom keywords
custom_keywords = ['Title VII', 'EEOC complaint', 'discrimination lawsuit']
results = mediator.discover_web_evidence(keywords=custom_keywords)
```

### Domain-Specific Evidence

```python
# Search specific authoritative domains
legal_domains = [
    'eeoc.gov',
    'dol.gov',
    'law.cornell.edu',
    'justice.gov'
]

results = mediator.discover_web_evidence(
    keywords=['employment discrimination'],
    domains=legal_domains,
    min_relevance=0.7
)
```

### Batch Discovery for Multiple Claims

```python
claim_types = ['discrimination', 'retaliation', 'wrongful termination']

for claim_type in claim_types:
    keywords = [claim_type, f"{claim_type} evidence", f"{claim_type} case"]
    
    result = mediator.discover_web_evidence(
        keywords=keywords,
        claim_type=claim_type,
        min_relevance=0.6
    )
    
    print(f"{claim_type}: {result['stored']} evidence items stored")
```

### Evidence Quality Control

```python
# Discover with high quality threshold
result = mediator.discover_web_evidence(
    keywords=['employment discrimination'],
    min_relevance=0.8  # Only top-quality evidence
)

# Review discovered evidence
for cid in result['evidence_cids']:
    evidence_data = mediator.retrieve_evidence(cid)
    print(f"High-quality evidence: {cid}")
```

## Integration with Existing Systems

### Works with User Evidence

```python
# User submits manual evidence
manual_result = mediator.submit_evidence_file(
    file_path='/path/to/contract.pdf',
    evidence_type='document',
    description='Employment contract'
)

# System discovers additional evidence
auto_result = mediator.discover_evidence_automatically()

# Both types stored together
all_evidence = mediator.get_user_evidence()
print(f"Total evidence: {len(all_evidence)}")
```

### Works with Legal Analysis

```python
# Analyze complaint first
legal_analysis = mediator.analyze_complaint_legal_issues()

# Discover evidence based on analysis
evidence_results = mediator.discover_evidence_automatically()

# Combine for comprehensive case building
for claim_type in legal_analysis['classification']['claim_types']:
    authorities = mediator.get_legal_authorities(claim_type=claim_type)
    evidence = mediator.get_user_evidence()  # Includes auto-discovered
    
    print(f"\n{claim_type}:")
    print(f"  Legal authorities: {len(authorities)}")
    print(f"  Evidence items: {len(evidence)}")
```

## Configuration

### Environment Variables

```bash
# Brave Search API key (required for Brave Search)
export BRAVE_SEARCH_API_KEY="your_api_key_here"

# Cache directory for search results
export BRAVE_SEARCH_CACHE_PATH="/path/to/cache"

# Common Crawl state directory
export CCINDEX_STATE_DIR="/path/to/state"
```

### Mediator Configuration

```python
mediator = Mediator(
    backends=[backend],
    evidence_db_path='/custom/path/evidence.duckdb'
)
```

## Troubleshooting

### Brave Search Not Available

```
[web_evidence_warning] Brave Search API key not found
```

Solution: Set environment variable
```bash
export BRAVE_SEARCH_API_KEY="your_key"
```

Get API key from: https://brave.com/search/api/

### Common Crawl Not Available

```
[web_evidence_warning] Common Crawl not available
```

Solution: Ensure ipfs_datasets_py submodule is initialized:
```bash
git submodule update --init --recursive
```

### No Results Found

If searches return no results:
1. Broaden keywords
2. Remove domain restrictions
3. Lower `min_relevance` threshold
4. Check internet connectivity

## Dependencies

Required:
- `ipfs_datasets_py` - For web archiving tools

Optional:
- Brave Search API key - For Brave Search
- Common Crawl indices - For archive search

## See Also

- `mediator/web_evidence_hooks.py` - Implementation
- `tests/test_web_evidence_hooks.py` - Tests
- `docs/EVIDENCE_MANAGEMENT.md` - User evidence system
- `docs/LEGAL_AUTHORITY_RESEARCH.md` - Legal research system
- ipfs_datasets_py/web_archiving - Web archiving tools
