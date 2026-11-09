# Codebase Bundle: codebase/runtime/document_optimization

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-095 Review swallowed exception path in document_optimization.py:43

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/agent_supervisor/discovery, document_optimization.py
- Validation: python3 -m py_compile document_optimization.py
- Bundle: codebase/runtime/document_optimization
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-document_optimization.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/document_optimization
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: document_optimization.py
- AST symbols: __future__, __future__.annotations, __init__, _apply_actor_payload, _apply_config, _build_anchored_chronology_summary, _build_blocker_prompt, _build_claim_reasoning_review, _build_claim_reasoning_theorem_export_metadata, _build_claim_support_temporal_handoff, _build_claim_supporting_facts_delta, _build_claim_temporal_gap_hints, _build_claims_for_relief_delta, _build_document_evidence_targeting_summary, _build_document_execution_drift_summary, _build_document_grounding_improvement_summary, _build_document_grounding_lane_outcome_summary, _build_document_workflow_execution_summary, _build_fallback_actor_payload, _build_generic_delta, _build_iteration_change_manifest, _build_list_delta, _build_manifest_delta_details, _build_packet_projection, _build_support_context, _build_upstream_optimizer_metadata, _build_workflow_optimization_guidance, _build_workflow_phase_targeting, _build_workflow_targeting_summary, _call_mediator, _choose_focus_section, _choose_focus_section_from_workflow_targeting, _chronology_fact_label, _claim_key, _claim_label, _claim_temporal_gap_focus, _clamp, _classify_manifest_change, _collect_temporal_registry_identifiers, _collect_unresolved_temporal_issue_identifiers, _contains_actor_marker, _contains_anchor, _contains_causation_link, _contains_date_anchor, _cosine_similarity, _dedupe_text_values, _embed_text, _extract_element_texts, _extract_llm_metadata, _extract_manifest_value, _extract_support_texts, _focus_query_text, _format_service_recipient_detail, _format_timeline_date, _generate_llm_payload, _get_embeddings_router, _get_upstream_llm_router, _heuristic_review, _join_chronology_segments, _lexical_overlap_score, _merge_review_payload, _normalize_affidavit_facts, _normalize_blocker_records, _normalize_claims_for_relief, _normalize_exhibits, _normalize_intake_objective, _normalize_intake_objectives, _normalize_lines, _normalize_optimizer_provider, _normalize_service_recipient_details, _parse_json_payload, _rank_candidates, _refresh_dependent_sections, _reset_runtime_state, _resolve_stage_provider, _resolve_tracked_fields, _router_status, _router_usage_summary, _run_actor, _run_critic
- AST symbol scope: file
- Goal id: codebase/runtime/document_optimization
- Missing evidence: Review swallowed exception path in document_optimization.py:43
- Merge key: codebase/runtime/document_optimization
- Merge family: document_optimization.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: d5d93085783be4b8
- Acceptance: Codebase scan filed this finding from document_optimization.py:43. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-095-codebase-scan-d5d93085783b.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-096 Review swallowed exception path in document_optimization.py:4355

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/agent_supervisor/discovery, document_optimization.py
- Validation: python3 -m py_compile document_optimization.py
- Bundle: codebase/runtime/document_optimization
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-document_optimization.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/document_optimization
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: document_optimization.py
- AST symbols: __future__, __future__.annotations, __init__, _apply_actor_payload, _apply_config, _build_anchored_chronology_summary, _build_blocker_prompt, _build_claim_reasoning_review, _build_claim_reasoning_theorem_export_metadata, _build_claim_support_temporal_handoff, _build_claim_supporting_facts_delta, _build_claim_temporal_gap_hints, _build_claims_for_relief_delta, _build_document_evidence_targeting_summary, _build_document_execution_drift_summary, _build_document_grounding_improvement_summary, _build_document_grounding_lane_outcome_summary, _build_document_workflow_execution_summary, _build_fallback_actor_payload, _build_generic_delta, _build_iteration_change_manifest, _build_list_delta, _build_manifest_delta_details, _build_packet_projection, _build_support_context, _build_upstream_optimizer_metadata, _build_workflow_optimization_guidance, _build_workflow_phase_targeting, _build_workflow_targeting_summary, _call_mediator, _choose_focus_section, _choose_focus_section_from_workflow_targeting, _chronology_fact_label, _claim_key, _claim_label, _claim_temporal_gap_focus, _clamp, _classify_manifest_change, _collect_temporal_registry_identifiers, _collect_unresolved_temporal_issue_identifiers, _contains_actor_marker, _contains_anchor, _contains_causation_link, _contains_date_anchor, _cosine_similarity, _dedupe_text_values, _embed_text, _extract_element_texts, _extract_llm_metadata, _extract_manifest_value, _extract_support_texts, _focus_query_text, _format_service_recipient_detail, _format_timeline_date, _generate_llm_payload, _get_embeddings_router, _get_upstream_llm_router, _heuristic_review, _join_chronology_segments, _lexical_overlap_score, _merge_review_payload, _normalize_affidavit_facts, _normalize_blocker_records, _normalize_claims_for_relief, _normalize_exhibits, _normalize_intake_objective, _normalize_intake_objectives, _normalize_lines, _normalize_optimizer_provider, _normalize_service_recipient_details, _parse_json_payload, _rank_candidates, _refresh_dependent_sections, _reset_runtime_state, _resolve_stage_provider, _resolve_tracked_fields, _router_status, _router_usage_summary, _run_actor, _run_critic
- AST symbol scope: file
- Goal id: codebase/runtime/document_optimization
- Missing evidence: Review swallowed exception path in document_optimization.py:4355
- Merge key: codebase/runtime/document_optimization
- Merge family: document_optimization.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 6d722b95b86a59c0
- Acceptance: Codebase scan filed this finding from document_optimization.py:4355. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-096-codebase-scan-6d722b95b86a.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-097 Review swallowed exception path in document_optimization.py:4683

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/agent_supervisor/discovery, document_optimization.py
- Validation: python3 -m py_compile document_optimization.py
- Bundle: codebase/runtime/document_optimization
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-document_optimization.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/document_optimization
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: document_optimization.py
- AST symbols: __future__, __future__.annotations, __init__, _apply_actor_payload, _apply_config, _build_anchored_chronology_summary, _build_blocker_prompt, _build_claim_reasoning_review, _build_claim_reasoning_theorem_export_metadata, _build_claim_support_temporal_handoff, _build_claim_supporting_facts_delta, _build_claim_temporal_gap_hints, _build_claims_for_relief_delta, _build_document_evidence_targeting_summary, _build_document_execution_drift_summary, _build_document_grounding_improvement_summary, _build_document_grounding_lane_outcome_summary, _build_document_workflow_execution_summary, _build_fallback_actor_payload, _build_generic_delta, _build_iteration_change_manifest, _build_list_delta, _build_manifest_delta_details, _build_packet_projection, _build_support_context, _build_upstream_optimizer_metadata, _build_workflow_optimization_guidance, _build_workflow_phase_targeting, _build_workflow_targeting_summary, _call_mediator, _choose_focus_section, _choose_focus_section_from_workflow_targeting, _chronology_fact_label, _claim_key, _claim_label, _claim_temporal_gap_focus, _clamp, _classify_manifest_change, _collect_temporal_registry_identifiers, _collect_unresolved_temporal_issue_identifiers, _contains_actor_marker, _contains_anchor, _contains_causation_link, _contains_date_anchor, _cosine_similarity, _dedupe_text_values, _embed_text, _extract_element_texts, _extract_llm_metadata, _extract_manifest_value, _extract_support_texts, _focus_query_text, _format_service_recipient_detail, _format_timeline_date, _generate_llm_payload, _get_embeddings_router, _get_upstream_llm_router, _heuristic_review, _join_chronology_segments, _lexical_overlap_score, _merge_review_payload, _normalize_affidavit_facts, _normalize_blocker_records, _normalize_claims_for_relief, _normalize_exhibits, _normalize_intake_objective, _normalize_intake_objectives, _normalize_lines, _normalize_optimizer_provider, _normalize_service_recipient_details, _parse_json_payload, _rank_candidates, _refresh_dependent_sections, _reset_runtime_state, _resolve_stage_provider, _resolve_tracked_fields, _router_status, _router_usage_summary, _run_actor, _run_critic
- AST symbol scope: file
- Goal id: codebase/runtime/document_optimization
- Missing evidence: Review swallowed exception path in document_optimization.py:4683
- Merge key: codebase/runtime/document_optimization
- Merge family: document_optimization.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 1d23478780270cb6
- Acceptance: Codebase scan filed this finding from document_optimization.py:4683. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-097-codebase-scan-1d2347878027.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
