# Evidence Management System

This document describes the evidence management system that allows users to submit, store, and analyze evidence for their legal cases using IPFS for storage and DuckDB for state management.

## Overview

The evidence management system consists of three main hooks:

1. **EvidenceStorageHook** - Stores evidence in IPFS and returns Content IDs (CIDs)
2. **EvidenceStateHook** - Manages evidence metadata and state in DuckDB
3. **EvidenceAnalysisHook** - Analyzes stored evidence and provides insights

## Architecture

```
User Evidence
     ↓
[EvidenceStorageHook]
     ↓ (Store in IPFS → CID)
[EvidenceStateHook]
     ↓ (Record in DuckDB with CID reference)
[EvidenceAnalysisHook]
     ↓ (Analyze evidence for claims)
Evidence Insights
```

## Features

- **IPFS Storage**: Evidence stored immutably in IPFS with content-addressable IDs
- **DuckDB State**: Fast, efficient state management with SQL queries
- **CID References**: Evidence tracked by CID for integrity and retrieval
- **User Association**: Evidence linked to user accounts
- **Claim Mapping**: Evidence can be associated with specific legal claims
- **Analysis**: AI-powered evidence analysis and recommendations

## Usage

### Basic Usage

```python
from mediator import Mediator
from backends import LLMRouterBackend

# Initialize mediator
backend = LLMRouterBackend(id='llm-router', provider='codex', model='gpt-5.3-codex')
mediator = Mediator(backends=[backend])

# Set user context
mediator.state.username = 'john_doe'

# Submit evidence
result = mediator.submit_evidence(
    data=b"Contract document content...",
    evidence_type='document',
    description='Original signed contract',
    claim_type='breach of contract',
    metadata={'filename': 'contract.pdf', 'signed_date': '2023-01-15'}
)

print(f"Evidence stored with CID: {result['cid']}")
print(f"Record ID: {result['record_id']}")
print(f"New DB row: {result['record_created']}")
print(f"Reused DB row: {result['record_reused']}")
```

### Submit Evidence from File

```python
# Submit evidence from file path
result = mediator.submit_evidence_file(
    file_path='/path/to/evidence.pdf',
    evidence_type='document',
    description='Email correspondence with defendant',
    claim_type='breach of contract'
)
```

### Retrieve User Evidence

```python
# Get all evidence for current user
evidence_list = mediator.get_user_evidence()

for evidence in evidence_list:
    print(f"CID: {evidence['cid']}")
    print(f"Type: {evidence['type']}")
    print(f"Description: {evidence['description']}")
    print(f"Timestamp: {evidence['timestamp']}")
    print(f"Claim: {evidence['claim_type']}")
    print(f"Fact count: {evidence['fact_count']}")
    print()
```

### Retrieve Persisted Facts for Evidence

```python
facts = mediator.get_evidence_facts(record_id)

for fact in facts:
    print(f"Fact ID: {fact['fact_id']}")
    print(f"Text: {fact['text']}")
    print(f"Confidence: {fact['confidence']}")
```

### Retrieve Evidence by CID

```python
# Get evidence data from IPFS by CID
cid = 'QmXxxxx...'
data = mediator.retrieve_evidence(cid)

# Save to file
with open('retrieved_evidence.pdf', 'wb') as f:
    f.write(data)
```

### Analyze Evidence

```python
# Analyze evidence for a specific claim
analysis = mediator.analyze_evidence(claim_type='breach of contract')

print(f"Total evidence: {analysis['total_evidence']}")
print(f"Evidence by type: {analysis['evidence_by_type']}")
print(f"Recommendation: {analysis['recommendation']}")
```

## Evidence Types

Supported evidence types:

- `document` - PDF, Word documents, contracts, agreements
- `image` - Photos, screenshots, diagrams
- `video` - Video recordings, depositions
- `audio` - Audio recordings, phone calls
- `email` - Email correspondence
- `text` - Text notes, transcripts
- `financial` - Financial records, receipts, invoices
- `medical` - Medical records, bills
- `other` - Any other evidence type

## Database Schema

### Evidence Table

```sql
CREATE TABLE evidence (
    id INTEGER PRIMARY KEY,
    user_id VARCHAR,
    username VARCHAR,
    evidence_cid VARCHAR NOT NULL,      -- IPFS Content ID
    evidence_type VARCHAR NOT NULL,     -- Type of evidence
    evidence_size INTEGER,              -- Size in bytes
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSON,                      -- Additional metadata
    complaint_id VARCHAR,               -- Associated complaint
    claim_type VARCHAR,                 -- Legal claim type
    description TEXT                    -- Evidence description
)
```

### Indexes

- `idx_evidence_cid` - Fast lookup by CID
- `idx_evidence_user` - Fast user-specific queries

## Configuration

### DuckDB Location

By default, the evidence database is stored in `statefiles/evidence.duckdb`. You can customize this:

```python
# Custom database path
mediator = Mediator(
    backends=[backend],
    evidence_db_path='/custom/path/evidence.duckdb'
)
```

### IPFS Backend

The system uses `ipfs_datasets_py`'s IPFS backend router which supports:

- **Local Kubo**: Direct IPFS CLI (`ipfs` command)
- **ipfs_kit_py**: Advanced IPFS operations
- **ipfs_accelerate_py**: Distributed IPFS operations
- **Fallback**: Simulated CIDs using content hashing (when IPFS unavailable)

Configure via environment variables:

```bash
# Force specific IPFS backend
export IPFS_DATASETS_PY_IPFS_BACKEND=kubo

# Enable ipfs_kit_py backend
export IPFS_DATASETS_PY_ENABLE_IPFS_KIT=1

# Custom IPFS command
export IPFS_DATASETS_PY_KUBO_CMD=/usr/local/bin/ipfs
```

## API Reference

## Result Metadata

`submit_evidence(...)` and `submit_evidence_file(...)` now return explicit deduplication and graph-projection metadata in addition to the stored artifact details.

Important fields:

- `record_created`: `True` when a new evidence row was inserted into DuckDB.
- `record_reused`: `True` when the evidence matched an existing row in the same claim scope.
- `support_link_created`: `True` when a new claim-support link was inserted.
- `support_link_reused`: `True` when the claim-support link already existed.
- `graph_projection`: Knowledge-graph projection summary.

The `graph_projection` payload distinguishes storage reuse from graph mutation:

```json
{
    "graph_changed": false,
    "artifact_entity_added": false,
    "artifact_entity_already_present": true,
    "storage_record_created": false,
    "storage_record_reused": true,
    "support_link_created": false,
    "support_link_reused": true
}
```

Evidence records retrieved later through `get_user_evidence(...)` and `get_evidence_by_cid(...)` also expose:

- `fact_count`: Number of persisted fact rows extracted from the evidence graph.
- `chunk_count`: Number of persisted parsed chunks.
- `graph_entity_count`: Number of persisted graph entities.
- `graph_relationship_count`: Number of persisted graph relationships.

### Mediator Methods

#### `submit_evidence(data, evidence_type, user_id=None, description=None, claim_type=None, metadata=None)`

Submit evidence data.

**Args:**
- `data` (bytes): Evidence data
- `evidence_type` (str): Type of evidence
- `user_id` (str, optional): User identifier
- `description` (str, optional): Evidence description
- `claim_type` (str, optional): Associated claim type
- `metadata` (dict, optional): Additional metadata

**Returns:** Dict with CID, record_id, deduplication status, and graph projection details

#### `submit_evidence_file(file_path, evidence_type, ...)`

Submit evidence from file.

**Args:** Same as `submit_evidence` plus:
- `file_path` (str): Path to evidence file

**Returns:** Dict with CID, record_id, deduplication status, and graph projection details

#### `get_user_evidence(user_id=None)`

Get all evidence for a user.

**Args:**
- `user_id` (str, optional): User identifier (defaults to state username)

**Returns:** List of evidence records

#### `retrieve_evidence(cid)`

Retrieve evidence data from IPFS.

**Args:**
- `cid` (str): Content ID

**Returns:** Evidence data (bytes)

#### `get_evidence_facts(evidence_id)`

Get persisted fact rows for a stored evidence record.

**Args:**
- `evidence_id` (int): Evidence record ID

**Returns:** List of fact records with text, confidence, metadata, and provenance

#### `analyze_evidence(user_id=None, claim_type=None)`

Analyze evidence.

**Args:**
- `user_id` (str, optional): User identifier
- `claim_type` (str, optional): Specific claim to analyze

**Returns:** Analysis results with recommendations

## Advanced Usage

### Batch Evidence Submission

```python
evidence_files = [
    ('contract.pdf', 'document', 'Original contract'),
    ('email1.pdf', 'email', 'Email thread 1'),
    ('email2.pdf', 'email', 'Email thread 2'),
]

cids = []
for file_path, ev_type, description in evidence_files:
    result = mediator.submit_evidence_file(
        file_path=file_path,
        evidence_type=ev_type,
        description=description,
        claim_type='breach of contract'
    )
    cids.append(result['cid'])
    print(f"Submitted: {description} → {result['cid']}")
```

### Evidence Statistics

```python
# Get comprehensive statistics
stats = mediator.evidence_state.get_evidence_statistics()

print(f"Total evidence items: {stats['total_count']}")
print(f"Total storage used: {stats['total_size']} bytes")
print(f"Evidence types: {stats['type_count']}")
print(f"Total users: {stats['user_count']}")
```

### Query Evidence by CID

```python
# Get evidence record from DuckDB
evidence = mediator.evidence_state.get_evidence_by_cid('QmXxxxx...')

if evidence:
    print(f"Owner: {evidence['username']}")
    print(f"Type: {evidence['type']}")
    print(f"Uploaded: {evidence['timestamp']}")
    print(f"Claim: {evidence['claim_type']}")
```

### Integration with Legal Analysis

```python
# Run full legal analysis
legal_analysis = mediator.analyze_complaint_legal_issues()

# Submit evidence for each claim type
for claim_type in legal_analysis['classification']['claim_types']:
    print(f"\nEvidence needed for: {claim_type}")
    
    # Analyze existing evidence
    evidence_analysis = mediator.analyze_evidence(claim_type=claim_type)
    
    if evidence_analysis['total_evidence'] == 0:
        print("  No evidence submitted yet")
    else:
        print(f"  {evidence_analysis['total_evidence']} items submitted")
        print(f"  Recommendation: {evidence_analysis['recommendation']}")
```

## Security Considerations

1. **Content Integrity**: IPFS CIDs are content-addressable, ensuring evidence integrity
2. **Immutability**: Evidence stored in IPFS cannot be modified
3. **Privacy**: Consider encrypting sensitive evidence before submission
4. **Access Control**: Implement user authentication to restrict evidence access
5. **Backup**: DuckDB file should be backed up regularly

## Troubleshooting

### IPFS Not Available

If IPFS is not installed or accessible, the system falls back to simulated CIDs:

```
[evidence_warning] IPFS not available - evidence storage will be simulated
```

Evidence will still be tracked, but actual IPFS storage won't occur. Install IPFS to enable full functionality:

```bash
# Install IPFS Kubo
wget https://dist.ipfs.io/kubo/v0.18.0/kubo_v0.18.0_linux-amd64.tar.gz
tar -xvzf kubo_v0.18.0_linux-amd64.tar.gz
cd kubo
sudo bash install.sh
ipfs init
```

### DuckDB Not Available

If DuckDB is not installed:

```bash
pip install duckdb>=0.9.0
```

### Database Locked

If you get a "database is locked" error, ensure only one process accesses the database at a time.

## Dependencies

Required:
- `duckdb>=0.9.0` - For state management

Optional:
- `ipfs` CLI (Kubo) - For IPFS storage
- `ipfs_datasets_py` - For advanced IPFS operations

Install:
```bash
pip install duckdb>=0.9.0
```

## See Also

- `mediator/evidence_hooks.py` - Implementation
- `tests/test_evidence_hooks.py` - Tests
- `docs/LEGAL_HOOKS.md` - Legal analysis integration
- ipfs_datasets_py documentation - IPFS backend details
