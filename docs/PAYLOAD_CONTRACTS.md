# Payload Contracts

This document centralizes the response payloads returned by the complaint generator's evidence, web-discovery, legal-authority, and graph-projection flows.

Use this page when you need the current response contract without stitching it together from multiple feature guides.

## Adapter Operation Metadata

Adapter-facing payloads under `integrations/ipfs_datasets/` now share one metadata family even when the top-level `status` differs by operation.

Representative metadata shape:

```json
{
  "status": "not_implemented",
  "metadata": {
    "operation": "text_to_fol",
    "backend_available": true,
    "implementation_status": "not_implemented"
  }
}
```

When an adapter is degraded or unavailable, payloads may also include:

```json
{
  "status": "unavailable",
  "degraded_reason": "No module named 'ipfs_datasets_py.logic'",
  "metadata": {
    "operation": "text_to_fol",
    "backend_available": false,
    "implementation_status": "unavailable",
    "degraded_reason": "No module named 'ipfs_datasets_py.logic'"
  }
}
```

Metadata semantics:

- `operation`: Canonical adapter operation name.
- `backend_available`: Whether the underlying `ipfs_datasets_py` capability imported successfully.
- `implementation_status`: Normalized implementation state for the adapter surface, such as `implemented`, `fallback`, `not_implemented`, `pending`, `noop`, `empty`, `error`, or `unavailable`.
- `degraded_reason`: Import or availability reason when the adapter is running degraded.

## Shared Parse Contract

Uploaded evidence, stored web evidence, and legal authority text now share one normalized parse bundle.

Representative shape:

```json
{
  "document_parse_contract": {
    "status": "fallback",
    "source": "web_document",
    "chunk_count": 2,
    "text": "Title: Example\n\nContent: ...",
    "text_preview": "Title: Example\n\nContent: ...",
    "summary": {
      "status": "fallback",
      "chunk_count": 2,
      "text_length": 900,
      "parser_version": "documents-adapter:1",
      "input_format": "text",
      "paragraph_count": 1,
      "source": "web_document"
    },
    "storage_metadata": {
      "filename": "example.txt",
      "parser_version": "documents-adapter:1",
      "source": "web_document",
      "transform_lineage": {
        "source": "web_document",
        "parser_version": "documents-adapter:1",
        "input_format": "text"
      }
    },
    "lineage": {
      "source": "web_document",
      "parser_version": "documents-adapter:1",
      "input_format": "text"
    }
  }
}
```

Compatibility notes:

- `metadata.document_parse_summary` remains present for existing callers.
- Stored DuckDB parse columns still use `parse_status`, `chunk_count`, `parsed_text_preview`, and `parse_metadata`.
- `document_parse_contract` is the canonical bundle those compatibility fields are now derived from.

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
    "support_link_reused": false,
    "graph_snapshot": {
      "status": "noop",
      "graph_id": "graph:...",
      "persisted": false,
      "created": true,
      "reused": false,
      "node_count": 4,
      "edge_count": 3
    }
  }
}
```

Field semantics:

- `record_created`: A new DuckDB evidence row was inserted.
- `record_reused`: The evidence matched an existing row in the same scope.
- `support_link_created`: A new claim-support link was inserted.
- `support_link_reused`: The claim-support link already existed.
- `graph_snapshot`: Adapter-normalized graph snapshot semantics for the current projection. `created` means the current projection introduced new graph structure, while `reused` means the artifact or support structure was already present.

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

`Mediator.discover_evidence_automatically(...)` and `WebEvidenceIntegrationHook.discover_evidence_for_case(...)` keep the legacy per-claim count and add richer per-claim storage, support, gap, contradiction, and follow-up summaries.

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
  },
  "claim_coverage_summary": {
    "employment discrimination": {
      "status_counts": {
        "covered": 0,
        "partially_supported": 1,
        "missing": 1
      },
      "missing_elements": ["Adverse action"],
      "partially_supported_elements": ["Protected activity"],
      "unresolved_element_count": 2,
      "recommended_gap_actions": {
        "collect_missing_support_kind": 1,
        "collect_initial_support": 1
      },
      "contradiction_candidate_count": 1,
      "contradicted_elements": ["Protected activity"],
      "graph_trace_summary": {
        "traced_link_count": 0,
        "snapshot_created_count": 0,
        "snapshot_reused_count": 0,
        "source_table_counts": {},
        "graph_status_counts": {},
        "graph_id_count": 0
      }
    }
  },
  "claim_support_gaps": {
    "employment discrimination": {
      "unresolved_count": 2,
      "unresolved_elements": []
    }
  },
  "claim_contradiction_candidates": {
    "employment discrimination": {
      "candidate_count": 1,
      "candidates": []
    }
  },
  "claim_support_snapshots": {
    "employment discrimination": {
      "gaps": {
        "snapshot_id": 101,
        "required_support_kinds": ["evidence", "authority"],
        "is_stale": false,
        "retention_limit": 3,
        "pruned_snapshot_count": 0,
        "metadata": {
          "source": "discover_evidence_for_case",
          "support_state_token": "..."
        }
      },
      "contradictions": {
        "snapshot_id": 102,
        "required_support_kinds": ["evidence", "authority"],
        "is_stale": false,
        "retention_limit": 3,
        "pruned_snapshot_count": 0,
        "metadata": {
          "source": "discover_evidence_for_case",
          "support_state_token": "..."
        }
      }
    }
  },
  "claim_support_snapshot_summary": {
    "employment discrimination": {
      "total_snapshot_count": 2,
      "fresh_snapshot_count": 2,
      "stale_snapshot_count": 0,
      "snapshot_kinds": ["contradictions", "gaps"],
      "fresh_snapshot_kinds": ["contradictions", "gaps"],
      "stale_snapshot_kinds": [],
      "retention_limits": [3],
      "total_pruned_snapshot_count": 0
    }
  }
}
```

Compatibility note:

- `evidence_stored[claim_type]` remains an integer count.
- `evidence_storage_summary[claim_type]` is the authoritative deduplication-aware breakdown.
- `claim_coverage_summary[claim_type]` is the compact support-health snapshot for dashboards and automation.
- `claim_support_gaps[claim_type]` and `claim_contradiction_candidates[claim_type]` expose the richer unresolved-support and conflict diagnostics behind that compact summary.
- `claim_support_snapshots[claim_type]` exposes the persisted snapshot ids, support-kind scope, freshness metadata, and bounded-retention pruning metadata for the stored diagnostics that automatic workflows just wrote.
- `claim_support_snapshot_summary[claim_type]` compresses that lifecycle state into fresh versus stale counts, snapshot kinds, retention limits, and total pruning for dashboard-style consumers.

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
      "support_trace_summary": {
        "trace_count": 1,
        "fact_trace_count": 1,
        "link_only_trace_count": 0,
        "unique_fact_count": 1,
        "unique_graph_id_count": 1,
        "unique_record_count": 1,
        "support_by_kind": {
          "authority": 1
        },
        "support_by_source": {
          "legal_authorities": 1
        },
        "parse_source_counts": {
          "legal_authority": 1
        },
        "graph_status_counts": {
          "available": 1
        }
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
          "support_trace_summary": {
            "trace_count": 1,
            "fact_trace_count": 1,
            "link_only_trace_count": 0,
            "unique_fact_count": 1,
            "unique_graph_id_count": 1,
            "unique_record_count": 1,
            "support_by_kind": {
              "authority": 1
            },
            "support_by_source": {
              "legal_authorities": 1
            },
            "parse_source_counts": {
              "legal_authority": 1
            },
            "graph_status_counts": {
              "available": 1
            }
          },
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
                },
                "graph_trace": {
                  "source_table": "legal_authorities",
                  "record_id": 7,
                  "summary": {
                    "status": "available",
                    "entity_count": 2,
                    "relationship_count": 2
                  },
                  "snapshot": {
                    "graph_id": "graph:...",
                    "created": true,
                    "reused": false
                  }
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
      "validation_status": "contradicted",
      "validation_status_counts": {
        "supported": 0,
        "incomplete": 0,
        "missing": 1,
        "contradicted": 1
      },
      "proof_gap_count": 3,
      "elements_requiring_follow_up": ["Protected activity", "Adverse action"],
      "reasoning_adapter_status_counts": {
        "logic_proof": {"not_implemented": 1},
        "logic_contradictions": {"not_implemented": 1},
        "ontology_build": {"implemented": 1},
        "ontology_validation": {"implemented": 1}
      },
      "reasoning_backend_available_count": 4,
      "reasoning_predicate_count": 4,
      "reasoning_ontology_entity_count": 3,
      "reasoning_ontology_relationship_count": 2,
      "reasoning_fallback_ontology_count": 0,
      "decision_source_counts": {
        "heuristic_contradictions": 1,
        "missing_support": 1
      },
      "adapter_contradicted_element_count": 0,
      "decision_fallback_ontology_element_count": 0,
      "proof_supported_element_count": 0,
      "logic_unprovable_element_count": 0,
      "ontology_invalid_element_count": 0,
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
      "unresolved_element_count": 2,
      "unresolved_elements": ["Protected activity", "Adverse action"],
      "recommended_gap_actions": {
        "collect_missing_support_kind": 1,
        "collect_initial_support": 1
      },
      "contradiction_candidate_count": 1,
      "contradicted_elements": ["Protected activity"],
      "graph_trace_summary": {
        "traced_link_count": 1,
        "snapshot_created_count": 1,
        "snapshot_reused_count": 0,
        "source_table_counts": {
          "legal_authorities": 1
        },
        "graph_status_counts": {
          "available": 1
        },
        "graph_id_count": 1
      },
      "missing_elements": ["Adverse action"],
      "partially_supported_elements": ["Protected activity"]
    }
  },
  "claim_support_gaps": {
    "civil rights": {
      "unresolved_count": 2,
      "unresolved_elements": [
        {
          "element_text": "Protected activity",
          "status": "partially_supported",
          "recommended_action": "collect_missing_support_kind"
        },
        {
          "element_text": "Adverse action",
          "status": "missing",
          "recommended_action": "collect_initial_support"
        }
      ]
    }
  },
  "claim_contradiction_candidates": {
    "civil rights": {
      "candidate_count": 1,
      "candidates": [
        {
          "claim_element_text": "Protected activity",
          "polarity": ["affirmative", "negative"],
          "overlap_terms": ["complaint", "discrimination"]
        }
      ]
    }
  },
  "claim_support_validation": {
    "civil rights": {
      "validation_status": "contradicted",
      "validation_status_counts": {
        "supported": 0,
        "incomplete": 0,
        "missing": 1,
        "contradicted": 1
      },
      "proof_gap_count": 3,
      "proof_gaps": [
        {
          "element_text": "Protected activity",
          "gap_type": "contradiction_candidates",
          "candidate_count": 1,
          "recommended_action": "resolve_contradiction"
        },
        {
          "element_text": "Adverse action",
          "gap_type": "missing_support_kind",
          "support_kind": "evidence",
          "recommended_action": "collect_initial_support"
        }
      ],
      "proof_diagnostics": {
        "reasoning": {
          "adapter_status_counts": {
            "logic_proof": {"not_implemented": 1},
            "logic_contradictions": {"not_implemented": 1},
            "ontology_build": {"implemented": 1},
            "ontology_validation": {"implemented": 1}
          },
          "backend_available_count": 4,
          "predicate_count": 4,
          "ontology_entity_count": 3,
          "ontology_relationship_count": 2,
          "fallback_ontology_count": 0
        },
        "decision": {
          "decision_source_counts": {
            "heuristic_contradictions": 1,
            "missing_support": 1
          },
          "adapter_contradicted_element_count": 0,
          "fallback_ontology_element_count": 0,
          "proof_supported_element_count": 0,
          "logic_unprovable_element_count": 0,
          "ontology_invalid_element_count": 0
        }
      },
      "elements": [
        {
          "element_text": "Protected activity",
          "coverage_status": "partially_supported",
          "validation_status": "contradicted",
          "contradiction_candidate_count": 1,
          "proof_gap_count": 2,
          "recommended_action": "resolve_contradiction",
          "reasoning_diagnostics": {
            "predicate_count": 3,
            "adapter_statuses": {
              "logic_proof": {"operation": "prove_claim_elements"},
              "logic_contradictions": {"operation": "check_contradictions"},
              "ontology_build": {"operation": "build_ontology"},
              "ontology_validation": {"operation": "validate_ontology"}
            }
          },
          "proof_decision_trace": {
            "decision_source": "heuristic_contradictions",
            "heuristic_contradiction_count": 1,
            "logic_contradiction_count": 0,
            "logic_provable_count": 0,
            "logic_unprovable_count": 0,
            "ontology_validation_signal": "unknown",
            "used_fallback_ontology": false
          }
        }
      ]
    }
  },
  "claim_support_snapshots": {
    "civil rights": {
      "gaps": {
        "snapshot_id": 21,
        "required_support_kinds": ["evidence", "authority"],
        "is_stale": false,
        "retention_limit": 3,
        "pruned_snapshot_count": 0,
        "metadata": {
          "source": "research_case_automatically",
          "support_state_token": "..."
        }
      },
      "contradictions": {
        "snapshot_id": 22,
        "required_support_kinds": ["evidence", "authority"],
        "is_stale": false,
        "retention_limit": 3,
        "pruned_snapshot_count": 0,
        "metadata": {
          "source": "research_case_automatically",
          "support_state_token": "..."
        }
      }
    }
  },
  "claim_support_snapshot_summary": {
    "civil rights": {
      "total_snapshot_count": 2,
      "fresh_snapshot_count": 2,
      "stale_snapshot_count": 0,
      "snapshot_kinds": ["contradictions", "gaps"],
      "fresh_snapshot_kinds": ["contradictions", "gaps"],
      "stale_snapshot_kinds": [],
      "retention_limits": [3],
      "total_pruned_snapshot_count": 0
    }
  },
  "claim_reasoning_review": {
    "civil rights": {
      "claim_type": "civil rights",
      "total_element_count": 2,
      "flagged_element_count": 1,
      "fallback_ontology_element_count": 0,
      "unavailable_backend_element_count": 0,
      "degraded_adapter_element_count": 1,
      "flagged_elements": [
        {
          "element_id": "civil_rights:1",
          "element_text": "Protected activity",
          "validation_status": "contradicted",
          "predicate_count": 3,
          "used_fallback_ontology": false,
          "backend_available_count": 4,
          "unavailable_adapters": [],
          "degraded_adapters": ["logic_contradictions", "logic_proof"]
        }
      ]
    }
  },
  "follow_up_history": {
    "civil rights": []
  },
  "follow_up_history_summary": {
    "civil rights": {
      "total_entry_count": 0,
      "status_counts": {},
      "support_kind_counts": {},
      "execution_mode_counts": {},
      "query_strategy_counts": {},
      "follow_up_focus_counts": {},
      "resolution_status_counts": {},
      "manual_review_entry_count": 0,
      "resolved_entry_count": 0,
      "contradiction_related_entry_count": 0,
      "latest_attempted_at": null
    }
  }
}
```

Support-link semantics:

- `graph_summary`: Compact counts from the currently available stored graph rows.
- `graph_trace`: Provenance-oriented graph packet combining source table, record id, adapter snapshot semantics, and stored lineage metadata for review or downstream tracing.
- `support_traces`: Persisted fact-oriented trace rows derived from the stored support links, fact tables, and graph lineage. These are the strongest review-oriented explanation layer for why an element is currently covered or still weak.
- `support_trace_summary`: Compact counts over `support_traces`, including fact-trace volume, parse-source mix, graph-status mix, and distinct record or graph counts.

Interpretation notes:

- `claim_coverage_matrix` is the review-oriented support payload for operator and UI workflows.
- `claim_coverage_summary` is the compact companion payload for dashboards, logs, and quick status rendering.
- `validation_status`, `validation_status_counts`, and `proof_gap_count` lift proof-health into the compact summary without requiring callers to inspect per-element diagnostics.
- `reasoning_adapter_status_counts`, `reasoning_backend_available_count`, `reasoning_predicate_count`, `reasoning_ontology_entity_count`, `reasoning_ontology_relationship_count`, and `reasoning_fallback_ontology_count` summarize what the `ipfs_datasets` logic and GraphRAG adapters contributed to the current validation pass.
- `decision_source_counts`, `adapter_contradicted_element_count`, and `decision_fallback_ontology_element_count` summarize how proof decisions were reached across the claim, including whether adapter contradiction output changed any element status.
- `proof_supported_element_count`, `logic_unprovable_element_count`, and `ontology_invalid_element_count` summarize how often proof and ontology adapters positively supported an element, downgraded an element as unprovable, or reported an invalid reasoning graph.
- `graph_trace_summary` is the compact lineage companion for dashboards and audit surfaces; it counts traced links, snapshot creation versus reuse, source-table mix, and distinct graph ids without requiring callers to inspect raw support links.
- `unresolved_element_count`, `unresolved_elements`, and `recommended_gap_actions` compress the richer gap payload into one per-claim summary for dashboards.
- `contradiction_candidate_count` and `contradicted_elements` surface likely support conflicts without requiring callers to scan every candidate pair.
- `claim_support_gaps` exposes unresolved-element diagnostics with recommended actions and per-element support context.
- `claim_contradiction_candidates` exposes heuristic contradiction candidates for operator review.
- `claim_support_validation` is the normalized proof-oriented companion payload. It classifies each element as `supported`, `incomplete`, `missing`, or `contradicted`, emits `proof_gaps`, and provides one recommended action per element.
- `proof_diagnostics.reasoning` aggregates backend-oriented diagnostics from the logic and GraphRAG adapters, while `reasoning_diagnostics` preserves the per-element adapter packets used to produce those aggregates.
- `proof_diagnostics.decision` aggregates how validation decisions were reached across the claim, while `proof_decision_trace` preserves the per-element decision source, any adapter contradiction contribution, and proof-oriented counts such as `logic_provable_count`, `logic_unprovable_count`, and `ontology_validation_signal`.
- `claim_support_snapshots` exposes the persisted snapshot ids, metadata, `is_stale` freshness flag, and snapshot-retention pruning metadata for the gap and contradiction diagnostics written by automatic legal research.
- `claim_support_snapshot_summary` is the compact lifecycle companion for those persisted diagnostics. It reports how many snapshots are fresh versus stale, which kinds are present, the active retention limits, and how much pruning happened during persistence.
- `claim_reasoning_review` is the compact operator-facing reasoning review surface. It highlights claim elements that were contradicted, required fallback ontology, or encountered unavailable or degraded adapter states during validation.
- `follow_up_history` and `follow_up_history_summary` expose the persisted follow-up execution ledger for automatic legal research, so legal-research consumers get the same audit trail already available in the review and web-evidence payloads.
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
  "gap_summary": {
    "element_id": "employment_discrimination:1",
    "element_text": "Adverse action",
    "status": "partially_supported",
    "missing_support_kinds": ["authority"],
    "total_links": 1,
    "fact_count": 2,
    "graph_trace_summary": {
      "traced_link_count": 1,
      "snapshot_created_count": 1,
      "snapshot_reused_count": 0,
      "source_table_counts": {"evidence": 1},
      "graph_status_counts": {"ready": 1},
      "graph_id_count": 1
    },
    "recommended_action": "collect_missing_support_kind",
    "graph_support": {
      "status": "ready",
      "summary": {
        "total_match_count": 1,
        "total_fact_count": 2
      }
    }
  },
  "contradiction_candidates": [
    {
      "claim_element_id": "employment_discrimination:1",
      "claim_element_text": "Adverse action",
      "fact_ids": ["fact:abc123", "fact:def456"],
      "texts": [
        "Employee submitted a discrimination complaint to management.",
        "Employee did not submit a discrimination complaint to management."
      ],
      "support_refs": ["Qm...", "42 U.S.C. § 1983"],
      "support_kinds": ["evidence", "authority"],
      "source_tables": ["evidence", "legal_authorities"],
      "polarity": ["affirmative", "negative"],
      "overlap_terms": ["complaint", "discrimination", "management", "submit"],
      "graph_trace_summary": {
        "traced_link_count": 2,
        "snapshot_created_count": 1,
        "snapshot_reused_count": 1,
        "source_table_counts": {"evidence": 1, "legal_authorities": 1},
        "graph_status_counts": {"ready": 2},
        "graph_id_count": 2
      }
    }
  ],
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
- `gap_summary` surfaces unresolved or partially satisfied support requirements for the same element, plus graph-backed trace counts and graph-support lookup output.
- `contradiction_candidates` contains heuristic fact-pair conflicts for the element when support facts disagree with opposite polarity over materially overlapping terms.
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
      "manual_review_task_count": 1,
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
      "manual_review_task_count": 1,
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

## Claim Support Review API

`POST /api/claim-support/review` wraps the claim-coverage, support-summary, and follow-up contracts into one operator-facing payload.

Representative request shape:

```json
{
  "claim_type": "retaliation",
  "required_support_kinds": ["evidence", "authority"],
  "follow_up_cooldown_seconds": 3600,
  "include_support_summary": true,
  "include_overview": true,
  "include_follow_up_plan": true,
  "execute_follow_up": true,
  "follow_up_support_kind": "authority",
  "follow_up_max_tasks_per_claim": 2
}
```

Representative response shape:

```json
{
  "user_id": "state-user",
  "claim_type": "retaliation",
  "required_support_kinds": ["evidence", "authority"],
  "claim_coverage_summary": {
    "retaliation": {
      "validation_status": "contradicted",
      "validation_status_counts": {
        "supported": 0,
        "incomplete": 1,
        "missing": 1,
        "contradicted": 1
      },
      "proof_gap_count": 3,
      "reasoning_backend_available_count": 4,
      "status_counts": {
        "covered": 1,
        "partially_supported": 1,
        "missing": 1
      },
      "missing_elements": ["Causal connection"],
      "partially_supported_elements": ["Adverse action"],
      "unresolved_element_count": 2,
      "recommended_gap_actions": {
        "collect_initial_support": 1,
        "collect_missing_support_kind": 1
      },
      "contradiction_candidate_count": 1,
      "contradicted_elements": ["Adverse action"]
    }
  },
  "claim_support_gaps": {
    "retaliation": {
      "unresolved_count": 2,
      "unresolved_elements": []
    }
  },
  "claim_contradiction_candidates": {
    "retaliation": {
      "candidate_count": 1,
      "candidates": []
    }
  },
  "claim_support_validation": {
    "retaliation": {
      "validation_status": "contradicted",
      "proof_gap_count": 3,
      "elements": []
    }
  },
  "claim_support_snapshots": {
    "retaliation": {
      "gaps": {
        "snapshot_id": 11,
        "is_stale": false
      },
      "contradictions": {
        "snapshot_id": 12,
        "is_stale": false
      }
    }
  },
  "claim_support_snapshot_summary": {
    "retaliation": {
      "total_snapshot_count": 2,
      "fresh_snapshot_count": 2,
      "stale_snapshot_count": 0,
      "snapshot_kinds": ["contradictions", "gaps"],
      "fresh_snapshot_kinds": ["contradictions", "gaps"],
      "stale_snapshot_kinds": [],
      "retention_limits": [],
      "total_pruned_snapshot_count": 0
    }
  },
  "claim_reasoning_review": {
    "retaliation": {
      "claim_type": "retaliation",
      "total_element_count": 1,
      "flagged_element_count": 1,
      "fallback_ontology_element_count": 1,
      "unavailable_backend_element_count": 1,
      "degraded_adapter_element_count": 1,
      "flagged_elements": [
        {
          "element_id": "retaliation:2",
          "element_text": "Adverse action",
          "validation_status": "contradicted",
          "predicate_count": 4,
          "used_fallback_ontology": true,
          "backend_available_count": 3,
          "unavailable_adapters": ["logic_contradictions"],
          "degraded_adapters": ["logic_contradictions", "logic_proof"]
        }
      ]
    }
  },
  "follow_up_history_summary": {
    "retaliation": {
      "total_entry_count": 2,
      "status_counts": {
        "skipped_manual_review": 1,
        "executed": 1
      },
      "support_kind_counts": {
        "manual_review": 1,
        "authority": 1
      },
      "execution_mode_counts": {
        "manual_review": 1,
        "retrieve_support": 1
      },
      "query_strategy_counts": {
        "standard_gap_targeted": 2
      },
      "follow_up_focus_counts": {
        "contradiction_resolution": 1,
        "support_gap_closure": 1
      },
      "resolution_status_counts": {},
      "manual_review_entry_count": 1,
      "resolved_entry_count": 0,
      "contradiction_related_entry_count": 1,
      "latest_attempted_at": "2026-03-12T10:15:00"
    }
  },
  "follow_up_plan_summary": {
    "retaliation": {
      "task_count": 2,
      "blocked_task_count": 1,
      "suppressed_task_count": 1,
      "semantic_cluster_count": 2,
      "semantic_duplicate_count": 3,
      "recommended_actions": {
        "retrieve_more_support": 1,
        "target_missing_support_kind": 1
      }
    }
  },
  "follow_up_execution_summary": {
    "retaliation": {
      "executed_task_count": 1,
      "skipped_task_count": 2,
      "suppressed_task_count": 1,
      "cooldown_skipped_task_count": 1,
      "semantic_cluster_count": 3,
      "semantic_duplicate_count": 4
    }
  }
}
```

Interpretation notes:

- `execute_follow_up=false` keeps the endpoint read-only and omits `follow_up_execution` plus `follow_up_execution_summary`.
- `follow_up_support_kind` narrows execution to one retrieval lane such as `evidence` or `authority` without changing the review-only sections.
- `follow_up_max_tasks_per_claim` limits side-effecting execution only; it does not truncate `follow_up_plan`.
- `claim_support_gaps` and `claim_contradiction_candidates` are the richer operator-facing review sections for unresolved support and possible support conflicts.
- `claim_support_validation` is the first-class proof-status surface for the review API. Follow-up planning uses the same normalized validation statuses, so contradiction-heavy elements can be prioritized and are not auto-suppressed.
- `claim_support_snapshots` exposes any persisted diagnostic snapshot ids reused by the review payload; when a stored snapshot no longer matches current support state it is marked with `is_stale=true` and the payload falls back to recomputation for that claim.
- `claim_support_snapshot_summary` is the compact review-facing lifecycle view for those persisted diagnostics, so dashboard consumers can see freshness and pruning at a glance without iterating the raw snapshot entries.
- `claim_reasoning_review` is the compact review-facing reasoning surface for flagged claim elements, capturing fallback ontology use plus unavailable or degraded adapter states without forcing clients to inspect every `reasoning_diagnostics` packet.
- `follow_up_history` exposes recent rows from the persisted `claim_follow_up_execution` ledger, including contradiction-targeted retrieval attempts and manual-review audit events.
- `follow_up_history_summary` compresses that ledger into counts by status, support kind, execution mode, query strategy, contradiction focus, and any recorded manual-review resolutions.
- `claim_coverage_summary`, `follow_up_plan_summary`, and `follow_up_execution_summary` are the compact operator-facing surfaces intended for dashboards and review tools.
- When `execute_follow_up=true`, the response adds `compatibility_notice` and emits `Deprecation`, `Sunset`, `Link`, and `Warning` headers so clients can migrate off the compatibility path.
- New clients should prefer `POST /api/claim-support/execute-follow-up` for side effects and treat `execute_follow_up` on the review endpoint as a compatibility path.

## Claim Support Follow-Up Execution API

`POST /api/claim-support/execute-follow-up` provides an explicit side-effecting surface for follow-up retrieval work.

Representative request shape:

```json
{
  "claim_type": "retaliation",
  "required_support_kinds": ["evidence", "authority"],
  "follow_up_cooldown_seconds": 3600,
  "follow_up_support_kind": "evidence",
  "follow_up_max_tasks_per_claim": 1,
  "follow_up_force": false,
  "include_post_execution_review": true,
  "include_support_summary": true,
  "include_overview": true,
  "include_follow_up_plan": true
}
```

Representative response shape:

```json
{
  "user_id": "testuser",
  "claim_type": "retaliation",
  "required_support_kinds": ["evidence", "authority"],
  "follow_up_support_kind": "evidence",
  "follow_up_force": false,
  "follow_up_execution": {
    "retaliation": {
      "task_count": 1,
      "tasks": [
        {
          "claim_element": "Protected activity",
          "execution_mode": "review_and_retrieve",
          "follow_up_focus": "contradiction_resolution",
          "query_strategy": "contradiction_targeted",
          "proof_gap_types": ["contradiction_candidates"],
          "executed": {
            "evidence": {
              "query": "\"retaliation\" \"Protected activity\" contradictory evidence rebuttal",
              "keywords": ["retaliation", "Protected activity", "contradictory", "evidence", "rebuttal"]
            }
          }
        }
      ],
      "skipped_tasks": [
        {
          "claim_element": "Adverse action",
          "execution_mode": "manual_review",
          "follow_up_focus": "contradiction_resolution",
          "skipped": {
            "manual_review": {
              "reason": "contradiction_requires_resolution",
              "audit_query": "manual_review::retaliation::retaliation:2::resolve_contradiction"
            }
          }
        }
      ]
    }
  },
  "follow_up_execution_summary": {
    "retaliation": {
      "executed_task_count": 1,
      "skipped_task_count": 1,
      "suppressed_task_count": 0,
      "cooldown_skipped_task_count": 0,
      "manual_review_task_count": 1,
      "semantic_cluster_count": 1,
      "semantic_duplicate_count": 0
    }
  },
  "post_execution_review": {
    "follow_up_history_summary": {
      "retaliation": {
        "total_entry_count": 2,
        "manual_review_entry_count": 1,
        "resolved_entry_count": 1,
        "resolution_status_counts": {
          "resolved_supported": 1
        },
        "contradiction_related_entry_count": 2,
        "latest_attempted_at": "2026-03-12T11:05:00"
      }
    },
    "claim_coverage_summary": {
      "retaliation": {
        "status_counts": {
          "covered": 2,
          "partially_supported": 0,
          "missing": 1
        }
      }
    }
  }
}
```

Interpretation notes:

- `execution_mode` distinguishes normal retrieval work from contradiction-driven `manual_review` or mixed `review_and_retrieve` tasks.
- `follow_up_focus` captures whether the task is closing an ordinary support gap or resolving a contradiction-heavy element.
- `query_strategy` records whether generated search text used the standard support-gap templates or contradiction-targeted retrieval prompts.
- `manual_review` skips are also written into the `claim_follow_up_execution` DuckDB ledger with `support_kind="manual_review"`, so contradiction-resolution work has an audit trail even when no retrieval runs.
- Operator resolutions can be appended to that same ledger as `status="resolved_manual_review"` events, carrying fields such as `resolution_status`, `resolution_notes`, and `related_execution_id`.
- Once a contradiction has a newer `resolved_manual_review` event, pure `manual_review` tasks stop appearing in `Mediator.get_claim_follow_up_plan(...)`; mixed `review_and_retrieve` tasks downgrade back to ordinary `retrieve_support` planning so only the unresolved support gap remains active.
- `manual_review_task_count` in both follow-up summaries tracks contradiction-review work that intentionally does not trigger evidence or authority retrieval.
- `post_execution_review.follow_up_history_summary` reflects the refreshed ledger after execution, so clients can confirm that retrieval and manual-review events were recorded.

- `follow_up_force=true` bypasses duplicate-within-cooldown suppression inside `Mediator.execute_claim_follow_up_plan(...)`.
- `include_post_execution_review=false` returns only execution results and skips the extra post-run coverage refresh.
- `post_execution_review` reuses the same review contract as `POST /api/claim-support/review`.

## Claim Support Manual Review Resolution API

`POST /api/claim-support/resolve-manual-review` records an operator resolution for a previously queued or audited `manual_review` task.

Representative request shape:

```json
{
  "claim_type": "retaliation",
  "claim_element_id": "retaliation:2",
  "claim_element": "Adverse action",
  "resolution_status": "resolved_supported",
  "resolution_notes": "Operator confirmed the contradictory evidence was reconciled.",
  "related_execution_id": 21,
  "resolution_metadata": {
    "reviewer": "case-analyst"
  },
  "include_post_resolution_review": true,
  "include_support_summary": true,
  "include_overview": true,
  "include_follow_up_plan": true
}
```

Representative response shape:

```json
{
  "user_id": "state-user",
  "claim_type": "retaliation",
  "claim_element_id": "retaliation:2",
  "claim_element": "Adverse action",
  "resolution_status": "resolved_supported",
  "resolution_notes": "Operator confirmed the contradictory evidence was reconciled.",
  "related_execution_id": 21,
  "resolution_result": {
    "recorded": true,
    "execution_id": 91,
    "claim_type": "retaliation",
    "claim_element_id": "retaliation:2",
    "claim_element_text": "Adverse action",
    "support_kind": "manual_review",
    "status": "resolved_manual_review",
    "query_text": "manual_review_resolution::retaliation::retaliation:2::resolved_supported",
    "metadata": {
      "resolution_status": "resolved_supported",
      "resolution_notes": "Operator confirmed the contradictory evidence was reconciled.",
      "related_execution_id": 21,
      "reviewer": "case-analyst"
    }
  },
  "post_resolution_review": {
    "follow_up_history_summary": {
      "retaliation": {
        "resolved_entry_count": 1,
        "resolution_status_counts": {
          "resolved_supported": 1
        }
      }
    }
  }
}
```

Interpretation notes:

- Resolution events are append-only ledger rows under `claim_follow_up_execution`; they do not overwrite the original `skipped_manual_review` event.
- `related_execution_id` should point at the original manual-review audit row when available, so the resolution can be traced back to the triggering contradiction workflow.
- `resolution_metadata` is merged into the stored ledger metadata and is intended for reviewer identity, rationale, or downstream workflow tags.
- `post_resolution_review` reuses the same review contract as `POST /api/claim-support/review`, making the updated history and summary immediately available after resolution.

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