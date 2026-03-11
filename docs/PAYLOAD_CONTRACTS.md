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
  "parse_summary": {
    "processed": 2,
    "total_chunks": 4,
    "total_paragraphs": 3,
    "total_text_length": 1800,
    "status_counts": {"fallback": 2},
    "input_format_counts": {"text": 2},
    "parser_versions": ["documents-adapter:1"]
  },
  "parse_details": [
    {
      "cid": "Qm...",
      "status": "fallback",
      "chunk_count": 2,
      "text_length": 900,
      "parser_version": "documents-adapter:1",
      "input_format": "text",
      "paragraph_count": 1
    }
  ],
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
- `parse_summary`: Aggregate parse statistics for stored web evidence in the request.
- `parse_details`: Per-record parse metadata extracted from `document_parse_summary`.

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

Stored authority records returned by `Mediator.get_legal_authorities(...)` also include:

- `fact_count`: Number of persisted fact rows extracted from the authority text.

Per-source keys follow the pattern:

- `<source_group>`
- `<source_group>_new`
- `<source_group>_reused`
- `<source_group>_support_links_added`
- `<source_group>_support_links_reused`

## Automatic Legal Research

`Mediator.research_case_automatically(...)` returns the authority storage contract per claim type under `authorities_stored`.

It also returns a per-claim `claim_coverage_matrix` that groups support by claim element and by support kind.
For compact reporting, it also returns `claim_coverage_summary` with counts and missing-element labels.

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
  },
  "claim_coverage_matrix": {
    "civil rights": {
      "claim_type": "civil rights",
      "required_support_kinds": ["evidence", "authority"],
      "total_elements": 2,
      "status_counts": {
        "covered": 0,
        "partially_supported": 1,
        "missing": 1
      },
      "total_links": 1,
      "total_facts": 1,
      "support_by_kind": {
        "authority": 1
      },
      "elements": [
        {
          "element_id": "civil_rights:1",
          "element_text": "Protected activity",
          "status": "partially_supported",
          "missing_support_kinds": ["evidence"],
          "links_by_kind": {
            "authority": [
              {
                "support_ref": "42 U.S.C. § 1983",
                "record_summary": {
                  "citation": "42 U.S.C. § 1983",
                  "parse_status": "fallback",
                  "graph_status": "available-fallback"
                },
                "graph_summary": {
                  "entity_count": 2,
                  "relationship_count": 2
                }
              }
            ]
          }
        }
      ]
    }
  },
  "claim_coverage_summary": {
    "civil rights": {
      "claim_type": "civil rights",
      "total_elements": 2,
      "total_links": 1,
      "total_facts": 1,
      "support_by_kind": {
        "authority": 1
      },
      "status_counts": {
        "covered": 0,
        "partially_supported": 1,
        "missing": 1
      },
      "missing_elements": ["Adverse action"],
      "partially_supported_elements": ["Protected activity"]
    }
  }
}
```

Interpretation notes:

- `claim_coverage_matrix` is the review-oriented support payload for operator and UI workflows.
- `claim_coverage_summary` is the compact companion payload for dashboards, logs, and quick status rendering.
- `status_counts` separates fully covered, partially supported, and still-missing elements.
- `links_by_kind` groups evidence and authority support without requiring callers to regroup raw links.
- `record_summary` and `graph_summary` provide lightweight parse and graph context inline with the support record.

## Claim Support Summary

`Mediator.summarize_claim_support(...)` returns the persisted support-link view grouped by claim type and claim element.

Representative shape:

```json
{
  "claims": {
    "employment discrimination": {
      "claim_type": "employment discrimination",
      "total_links": 3,
      "covered_elements": 2,
      "missing_elements": 1,
      "total_facts": 4,
      "elements": [
        {
          "element_id": "employment_discrimination:1",
          "element_text": "Adverse action",
          "support_count": 2,
          "support_by_kind": {
            "evidence": 1,
            "authority": 1
          },
          "fact_count": 4,
          "links": [
            {
              "source_table": "legal_authorities",
              "support_ref": "42 U.S.C. § 1983",
              "authority_record_id": 12,
              "fact_count": 4,
              "facts": [
                {
                  "fact_type": "CaseFact",
                  "text": "Protected activity is covered"
                }
              ]
            }
          ]
        }
      ]
    }
  }
}
```

Field semantics:

- `total_facts`: Sum of fact rows attached to enriched evidence and authority support links for the claim.
- `fact_count`: Sum of fact rows attached to enriched evidence and authority support links for the claim element.
- `evidence_record_id`: DuckDB evidence row resolved from the support reference CID.
- `authority_record_id`: DuckDB legal-authority row resolved from the persisted support-link metadata.
- `facts`: Persisted fact rows returned by `Mediator.get_evidence_facts(...)` or `Mediator.get_authority_facts(...)`.

## Claim Element View

`Mediator.get_claim_element_view(...)` wraps the claim-support summary for a single element together with matching evidence and authority rows.

Representative shape:

```json
{
  "claim_type": "employment discrimination",
  "claim_element_id": "employment_discrimination:1",
  "claim_element": "Adverse action",
  "exists": true,
  "is_covered": true,
  "missing_support": false,
  "support_summary": {
    "element_id": "employment_discrimination:1",
    "element_text": "Adverse action",
    "total_links": 2,
    "support_by_kind": {
      "evidence": 1,
      "authority": 1
    },
    "fact_count": 4,
    "links": [
      {
        "source_table": "legal_authorities",
        "support_ref": "42 U.S.C. § 1983",
        "authority_record_id": 12,
        "fact_count": 4,
        "facts": [
          {
            "fact_type": "CaseFact",
            "text": "Protected activity is covered"
          }
        ]
      }
    ]
  },
  "support_facts": [
    {
      "fact_id": "fact:abc123",
      "text": "Protected activity is covered",
      "claim_type": "employment discrimination",
      "claim_element_id": "employment_discrimination:1",
      "claim_element_text": "Adverse action",
      "support_kind": "authority",
      "support_ref": "42 U.S.C. § 1983",
      "source_table": "legal_authorities",
      "authority_record_id": 12
    }
  ],
  "evidence": [
    {
      "id": 14,
      "cid": "Qm...",
      "fact_count": 2
    }
  ],
  "authorities": [
    {
      "id": 12,
      "citation": "42 U.S.C. § 1983",
      "fact_count": 4
    }
  ],
  "total_facts": 4,
  "total_evidence": 1,
  "total_authorities": 1
}
```

Interpretation notes:

- `support_summary` is the same enriched element summary used inside `summarize_claim_support(...)`.
- `support_facts` is the flattened fact list collected from the element's enriched evidence and authority support links.
- `evidence` and `authorities` are the matching stored rows for the resolved claim element.

## Support Fact Retrieval

`Mediator.get_claim_support_facts(...)` returns the flattened persisted fact rows attached to claim-support links, optionally filtered to one claim element.

Representative shape:

```json
[
  {
    "fact_id": "fact:abc123",
    "text": "Employee complained about discrimination.",
    "claim_type": "employment discrimination",
    "claim_element_id": "employment_discrimination:1",
    "claim_element_text": "Protected activity",
    "support_kind": "evidence",
    "support_ref": "Qm...",
    "support_label": "HR complaint email",
    "source_table": "evidence",
    "evidence_record_id": 12,
    "authority_record_id": null
  }
]
```

Use this when downstream workflows need a cross-source fact list without re-walking `support_summary.links`.

## Claim Graph Support Query

`Mediator.query_claim_graph_support(...)` ranks persisted support facts for a claim element and returns a fallback graph-support view.

Representative shape:

```json
{
  "status": "available-fallback",
  "claim_type": "employment discrimination",
  "claim_element_id": "employment_discrimination:1",
  "claim_element_text": "Protected activity",
  "graph_id": "intake-knowledge-graph",
  "results": [
    {
      "fact_id": "fact:abc123",
      "text": "Employee complained about discrimination.",
      "support_kind": "evidence",
      "source_table": "evidence",
      "score": 2.6,
      "matched_claim_element": true,
      "duplicate_count": 2,
      "cluster_size": 2,
      "cluster_texts": [
        "Employee complained about discrimination.",
        "Employee filed an HR discrimination complaint."
      ],
      "evidence_record_id": 12
    }
  ],
  "summary": {
    "result_count": 1,
    "total_fact_count": 3,
    "unique_fact_count": 2,
    "duplicate_fact_count": 1,
    "semantic_cluster_count": 1,
    "semantic_duplicate_count": 1,
    "support_by_kind": {
      "evidence": 2,
      "authority": 1
    },
    "support_by_source": {
      "evidence": 2,
      "legal_authorities": 1
    },
    "max_score": 2.6
  },
  "graph_context": {
    "knowledge_graph_available": true,
    "entity_count": 8,
    "relationship_count": 7
  }
}
```

Interpretation notes:

- `results` are ranked fallback matches derived from persisted evidence and authority facts.
- `duplicate_count` shows how many repeated fact rows were collapsed into the ranked result.
- `cluster_size` and `cluster_texts` capture semantically similar fact variants that were merged into the same ranked support item.
- `score` combines stored fact confidence with claim-element ID/text matching and token overlap.
- `unique_fact_count` and `duplicate_fact_count` let callers distinguish distinct support from repeated sentence-level copies.
- `semantic_cluster_count` and `semantic_duplicate_count` provide the same distinction after near-duplicate semantic clustering.
- `graph_context` summarizes the currently loaded intake knowledge graph; it does not imply that the results were generated by a remote graph database.

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

Case-level auto-discovery payloads from `Mediator.discover_evidence_automatically(...)` also include compact follow-up summaries:

```json
{
  "follow_up_plan_summary": {
    "employment discrimination": {
      "task_count": 2,
      "blocked_task_count": 1,
      "graph_supported_task_count": 1,
      "suppressed_task_count": 1,
      "semantic_cluster_count": 1,
      "semantic_duplicate_count": 2,
      "recommended_actions": {
        "review_existing_support": 1,
        "retrieve_more_support": 1
      }
    }
  },
  "follow_up_execution_summary": {
    "employment discrimination": {
      "executed_task_count": 1,
      "skipped_task_count": 1,
      "suppressed_task_count": 1,
      "cooldown_skipped_task_count": 0,
      "semantic_cluster_count": 3,
      "semantic_duplicate_count": 4
    }
  }
}
```

Interpretation notes:

- `follow_up_plan_summary` is a compact operator-facing view of the full `follow_up_plan` payload.
- `semantic_cluster_count` and `semantic_duplicate_count` summarize distinct versus near-duplicate graph-support clusters across planned tasks.
- `follow_up_execution_summary` separates suppressed tasks from cooldown skips so dashboards can explain why follow-up work did not run.
- `follow_up_execution_summary.semantic_cluster_count` and `follow_up_execution_summary.semantic_duplicate_count` aggregate graph-support clusters across executed and skipped tasks, preserving the support context that informed execution decisions.
- `claim_coverage_matrix[claim_type]` exposes the same grouped claim-element support view used by automatic legal research.
- `claim_coverage_summary[claim_type]` provides the smaller per-claim status snapshot with counts and missing-element labels.

Follow-up planning payloads from `Mediator.get_claim_follow_up_plan(...)` now include graph-support context on each task:

```json
{
  "claims": {
    "employment discrimination": {
      "tasks": [
        {
          "claim_element_id": "employment_discrimination:1",
          "claim_element": "Protected activity",
          "priority": "medium",
          "priority_score": 2,
          "missing_support_kinds": ["evidence"],
          "has_graph_support": true,
          "graph_support_strength": "strong",
          "recommended_action": "review_existing_support",
          "should_suppress_retrieval": true,
          "suppression_reason": "existing_support_high_duplication",
          "graph_support": {
            "summary": {
              "total_fact_count": 3,
              "unique_fact_count": 1,
              "duplicate_fact_count": 2,
              "support_by_kind": {
                "authority": 1,
                "evidence": 2
              }
            },
            "results": [
              {
                "fact_id": "fact:abc123",
                "score": 2.6,
                "matched_claim_element": true
              }
            ]
          }
        }
      ]
    }
  }
}
```

Interpretation notes:

- `graph_support` is the same fallback support ranking returned by `Mediator.query_claim_graph_support(...)`.
- `has_graph_support` is a quick boolean derived from whether any ranked fact results already exist for the task's claim element.
- `graph_support_strength` classifies the ranked support snapshot as `none`, `moderate`, or `strong`.
- `recommended_action` distinguishes between tasks that should review existing support first and tasks that still need broader retrieval.
- `priority_score` is the sortable numeric priority after graph-support adjustment; `priority` is the corresponding label.
- `should_suppress_retrieval` flags low-value follow-up tasks that are skipped automatically unless execution is forced.
- `suppression_reason` explains why retrieval was suppressed.

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

Executed and skipped follow-up tasks also carry the same `graph_support` snapshot so downstream review can compare the pre-search support context with the new retrieval result.

Suppressed task example:

```json
{
  "skipped": {
    "suppressed": {
      "reason": "existing_support_high_duplication"
    }
  },
  "should_suppress_retrieval": true,
  "suppression_reason": "existing_support_high_duplication"
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