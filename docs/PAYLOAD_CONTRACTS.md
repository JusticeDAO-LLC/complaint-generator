# Payload Contracts

This document centralizes the response payloads returned by the complaint generator's evidence, web-discovery, legal-authority, and graph-projection flows.

Use this page when you need the current response contract without stitching it together from multiple feature guides.

## Evidence Submission

`Mediator.submit_evidence(...)` and `Mediator.submit_evidence_file(...)` return the stored artifact payload plus deduplication and graph-projection metadata.

Representative fields:

```json
{
  "cid": "Qm...",
  "type": "document",
  "record_id": 12,
  "record_created": true,
  "record_reused": false,
  "support_link_id": 34,
  "support_link_created": true,
  "support_link_reused": false,
  "claim_type": "breach of contract",
  "claim_element_id": "breach_of_contract:1",
  "claim_element": "Valid contract",
  "graph_projection": {
    "projected": true,
    "graph_changed": true,
    "entity_count": 4,
    "relationship_count": 3,
    "claim_links": 1,
    "artifact_entity_added": true,
    "artifact_entity_already_present": false,
    "storage_record_created": true,
    "storage_record_reused": false,
    "support_link_created": true,
    "support_link_reused": false
  }
}
```

Field semantics:

- `record_created`: A new DuckDB evidence row was inserted.
- `record_reused`: The evidence matched an existing row in the same scope.
- `support_link_created`: A new claim-support link was inserted.
- `support_link_reused`: The claim-support link already existed.

## Web Evidence Discovery

`Mediator.discover_web_evidence(...)` and `WebEvidenceIntegrationHook.discover_and_store_evidence(...)` return request-level discovery counts plus deduplicated storage counts.

Representative fields:

```json
{
  "discovered": 3,
  "validated": 2,
  "stored": 2,
  "stored_new": 1,
  "reused": 1,
  "skipped": 1,
  "total_records": 2,
  "total_new": 1,
  "total_reused": 1,
  "support_links_added": 2,
  "support_links_reused": 0,
  "total_support_links_added": 2,
  "total_support_links_reused": 0,
  "evidence_cids": ["Qm...", "Qm..."],
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

Count semantics:

- `stored`: Items that completed the storage workflow.
- `stored_new`: Items that created a new evidence row.
- `reused`: Items that reused an existing evidence row.
- `total_records`: Aggregate processed evidence records for the request.
- `total_new`: Aggregate new evidence rows.
- `total_reused`: Aggregate reused evidence rows.
- `support_links_added`: New support links created during the request.
- `support_links_reused`: Support links that already existed.

## Automatic Evidence Discovery

`Mediator.discover_evidence_automatically(...)` and `WebEvidenceIntegrationHook.discover_evidence_for_case(...)` keep the legacy per-claim count and add a richer per-claim storage summary.

Representative shape:

```json
{
  "claim_types": ["employment discrimination"],
  "evidence_discovered": {
    "employment discrimination": 3
  },
  "evidence_stored": {
    "employment discrimination": 2
  },
  "evidence_storage_summary": {
    "employment discrimination": {
      "total_records": 2,
      "total_new": 1,
      "total_reused": 1,
      "total_support_links_added": 2,
      "total_support_links_reused": 0
    }
  }
}
```

Compatibility note:

- `evidence_stored[claim_type]` remains an integer count.
- `evidence_storage_summary[claim_type]` is the authoritative deduplication-aware breakdown.

## Legal Authority Storage

`Mediator.store_legal_authorities(...)` returns both per-source counts and aggregate totals.

Representative shape:

```json
{
  "statutes": 2,
  "statutes_new": 1,
  "statutes_reused": 1,
  "statutes_support_links_added": 1,
  "statutes_support_links_reused": 1,
  "case_law": 0,
  "total_records": 2,
  "total_new": 1,
  "total_reused": 1,
  "total_support_links_added": 1,
  "total_support_links_reused": 1
}
```

Aggregate semantics:

- `total_records`: Authorities processed for the call.
- `total_new`: New authority rows inserted.
- `total_reused`: Existing authority rows reused.
- `total_support_links_added`: New claim-support links created.
- `total_support_links_reused`: Existing claim-support links reused.

Per-source keys follow the pattern:

- `<source_group>`
- `<source_group>_new`
- `<source_group>_reused`
- `<source_group>_support_links_added`
- `<source_group>_support_links_reused`

## Automatic Legal Research

`Mediator.research_case_automatically(...)` returns the authority storage contract per claim type under `authorities_stored`.

Representative shape:

```json
{
  "authorities_stored": {
    "civil rights": {
      "total_records": 1,
      "total_new": 0,
      "total_reused": 1,
      "total_support_links_added": 0,
      "total_support_links_reused": 1
    }
  }
}
```

## Graph Projection

`graph_projection` is returned by `Mediator.add_evidence_to_graphs(...)` and also propagated through evidence submission and web-evidence discovery.

Important fields:

- `graph_changed`: The active knowledge graph was mutated.
- `artifact_entity_added`: A new evidence/artifact node was added.
- `artifact_entity_already_present`: The artifact node was already present in the graph.
- `storage_record_created`: The underlying evidence row was newly inserted.
- `storage_record_reused`: The underlying evidence row was reused.
- `support_link_created`: The supporting claim-link row was newly inserted.
- `support_link_reused`: The supporting claim-link row already existed.

Interpretation examples:

- `storage_record_reused=true` and `graph_changed=false`: The evidence was fully known to storage and graph layers.
- `storage_record_reused=true` and `graph_changed=true`: Storage reused an existing row, but the active graph still needed projection work.
- `storage_record_created=true` and `graph_changed=true`: New evidence was inserted and projected into the graph.

## Follow-Up Execution

Evidence and authority follow-up execution payloads embed the same storage breakdowns inside each executed task result.

Evidence task result:

```json
{
  "executed": {
    "evidence": {
      "query": "\"breach of contract\" \"Valid contract\" evidence",
      "keywords": ["breach of contract", "Valid contract", "evidence"],
      "result": {
        "total_records": 1,
        "total_new": 0,
        "total_reused": 1
      }
    }
  }
}
```

Authority task result:

```json
{
  "executed": {
    "authority": {
      "query": "\"civil rights\" \"Protected activity\" statute",
      "stored_counts": {
        "total_records": 1,
        "total_new": 0,
        "total_reused": 1
      }
    }
  }
}
```