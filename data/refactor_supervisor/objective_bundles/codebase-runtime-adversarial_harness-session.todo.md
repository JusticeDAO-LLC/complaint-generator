# Codebase Bundle: codebase/runtime/adversarial_harness-session

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-080 Review swallowed exception path in adversarial_harness/session.py:4416

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/agent_supervisor/discovery, adversarial_harness/session.py
- Validation: python3 -m py_compile adversarial_harness/session.py
- Bundle: codebase/runtime/adversarial_harness-session
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-adversarial_harness-session.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/adversarial_harness-session
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: adversarial_harness/session.py
- AST symbols: __init__, _anchor_probe_map, _build_document_generation_fallback, _build_fallback_probe, _build_grounding_summary, _build_intake_question_structure_summary, _build_runtime_workflow_guidance, _candidate_matches_intake_objective, _claim_temporal_gap_prompts, _compact_document_generation_result, _coverage_gap_rank, _covered_anchor_sections_from_questions, _default_relief_for_seed, _emit_progress, _empathy_prefix_for_question, _extract_actor_critic_intake_context, _extract_actor_critic_score, _extract_anchor_sections, _extract_blocker_closure_match_count, _extract_claim_temporal_gap_summary, _extract_document_chronology_priority_hints, _extract_intake_prompt_candidates, _extract_latest_batch_priorities, _extract_latest_batch_priority_flags, _extract_phase1_section, _extract_question_objective, _extract_question_text, _extract_question_type, _extract_required_blocker_objectives, _extract_selector_score, _extract_selector_signals, _extract_workflow_phase, _has_empathy_prefix, _inject_intake_prompt_questions, _intake_objective_gap_label, _intake_objective_group, _intake_objective_weight, _is_actor_or_decisionmaker_question, _is_adverse_action_detail_question, _is_causation_sequence_question, _is_contradiction_resolution_question, _is_documentary_evidence_question, _is_exact_dates_question, _is_exhibit_ready_question, _is_harm_or_remedy_question, _is_hearing_request_timing_question, _is_protected_activity_causation_question, _is_redundant_candidate, _is_response_dates_question, _is_staff_names_titles_question, _is_timeline_question, _is_witness_question, _normalize_question, _normalized_actor_critic_score, _normalized_selector_score, _objective_sort_key, _persist_intake_priority_summary, _phase_focus_rank_for_candidate, _phase_focus_weight, _question_dedupe_key, _question_intent_key, _question_mentions_evidence_anchor, _question_objectives_from_prompt, _question_precision_score, _question_quality_score, _question_similarity, _question_specificity_score, _question_targets_anchor_section, _question_targets_missing_anchor_section, _question_tokens, _questions_substantially_overlap, _refresh_final_intake_case_file_snapshot, _reprioritize_candidates_for_intake_objectives, _router_backed_quality_signal, _run_document_generation, _seed_requires_causation_probe, _seed_supports_reasonable_accommodation, _seed_supports_selection_criteria, _select_next_question, _should_apply_empathy_prefix
- Goal id: codebase/runtime/adversarial_harness-session
- Missing evidence: Review swallowed exception path in adversarial_harness/session.py:4416
- Merge key: codebase/runtime/adversarial_harness-session
- Merge family: adversarial_harness/session.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Todo vector key: 8af245b6aa1f9912
- Acceptance: Codebase scan filed this finding from adversarial_harness/session.py:4416. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-080-codebase-scan-8af245b6aa1f.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-081 Review swallowed exception path in adversarial_harness/session.py:4423

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/agent_supervisor/discovery, adversarial_harness/session.py
- Validation: python3 -m py_compile adversarial_harness/session.py
- Bundle: codebase/runtime/adversarial_harness-session
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-adversarial_harness-session.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/adversarial_harness-session
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: adversarial_harness/session.py
- AST symbols: __init__, _anchor_probe_map, _build_document_generation_fallback, _build_fallback_probe, _build_grounding_summary, _build_intake_question_structure_summary, _build_runtime_workflow_guidance, _candidate_matches_intake_objective, _claim_temporal_gap_prompts, _compact_document_generation_result, _coverage_gap_rank, _covered_anchor_sections_from_questions, _default_relief_for_seed, _emit_progress, _empathy_prefix_for_question, _extract_actor_critic_intake_context, _extract_actor_critic_score, _extract_anchor_sections, _extract_blocker_closure_match_count, _extract_claim_temporal_gap_summary, _extract_document_chronology_priority_hints, _extract_intake_prompt_candidates, _extract_latest_batch_priorities, _extract_latest_batch_priority_flags, _extract_phase1_section, _extract_question_objective, _extract_question_text, _extract_question_type, _extract_required_blocker_objectives, _extract_selector_score, _extract_selector_signals, _extract_workflow_phase, _has_empathy_prefix, _inject_intake_prompt_questions, _intake_objective_gap_label, _intake_objective_group, _intake_objective_weight, _is_actor_or_decisionmaker_question, _is_adverse_action_detail_question, _is_causation_sequence_question, _is_contradiction_resolution_question, _is_documentary_evidence_question, _is_exact_dates_question, _is_exhibit_ready_question, _is_harm_or_remedy_question, _is_hearing_request_timing_question, _is_protected_activity_causation_question, _is_redundant_candidate, _is_response_dates_question, _is_staff_names_titles_question, _is_timeline_question, _is_witness_question, _normalize_question, _normalized_actor_critic_score, _normalized_selector_score, _objective_sort_key, _persist_intake_priority_summary, _phase_focus_rank_for_candidate, _phase_focus_weight, _question_dedupe_key, _question_intent_key, _question_mentions_evidence_anchor, _question_objectives_from_prompt, _question_precision_score, _question_quality_score, _question_similarity, _question_specificity_score, _question_targets_anchor_section, _question_targets_missing_anchor_section, _question_tokens, _questions_substantially_overlap, _refresh_final_intake_case_file_snapshot, _reprioritize_candidates_for_intake_objectives, _router_backed_quality_signal, _run_document_generation, _seed_requires_causation_probe, _seed_supports_reasonable_accommodation, _seed_supports_selection_criteria, _select_next_question, _should_apply_empathy_prefix
- Goal id: codebase/runtime/adversarial_harness-session
- Missing evidence: Review swallowed exception path in adversarial_harness/session.py:4423
- Merge key: codebase/runtime/adversarial_harness-session
- Merge family: adversarial_harness/session.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Todo vector key: 34e672b9ad65450c
- Acceptance: Codebase scan filed this finding from adversarial_harness/session.py:4423. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-081-codebase-scan-34e672b9ad65.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-082 Review swallowed exception path in adversarial_harness/session.py:4449

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/agent_supervisor/discovery, adversarial_harness/session.py
- Validation: python3 -m py_compile adversarial_harness/session.py
- Bundle: codebase/runtime/adversarial_harness-session
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-adversarial_harness-session.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/adversarial_harness-session
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: adversarial_harness/session.py
- AST symbols: __init__, _anchor_probe_map, _build_document_generation_fallback, _build_fallback_probe, _build_grounding_summary, _build_intake_question_structure_summary, _build_runtime_workflow_guidance, _candidate_matches_intake_objective, _claim_temporal_gap_prompts, _compact_document_generation_result, _coverage_gap_rank, _covered_anchor_sections_from_questions, _default_relief_for_seed, _emit_progress, _empathy_prefix_for_question, _extract_actor_critic_intake_context, _extract_actor_critic_score, _extract_anchor_sections, _extract_blocker_closure_match_count, _extract_claim_temporal_gap_summary, _extract_document_chronology_priority_hints, _extract_intake_prompt_candidates, _extract_latest_batch_priorities, _extract_latest_batch_priority_flags, _extract_phase1_section, _extract_question_objective, _extract_question_text, _extract_question_type, _extract_required_blocker_objectives, _extract_selector_score, _extract_selector_signals, _extract_workflow_phase, _has_empathy_prefix, _inject_intake_prompt_questions, _intake_objective_gap_label, _intake_objective_group, _intake_objective_weight, _is_actor_or_decisionmaker_question, _is_adverse_action_detail_question, _is_causation_sequence_question, _is_contradiction_resolution_question, _is_documentary_evidence_question, _is_exact_dates_question, _is_exhibit_ready_question, _is_harm_or_remedy_question, _is_hearing_request_timing_question, _is_protected_activity_causation_question, _is_redundant_candidate, _is_response_dates_question, _is_staff_names_titles_question, _is_timeline_question, _is_witness_question, _normalize_question, _normalized_actor_critic_score, _normalized_selector_score, _objective_sort_key, _persist_intake_priority_summary, _phase_focus_rank_for_candidate, _phase_focus_weight, _question_dedupe_key, _question_intent_key, _question_mentions_evidence_anchor, _question_objectives_from_prompt, _question_precision_score, _question_quality_score, _question_similarity, _question_specificity_score, _question_targets_anchor_section, _question_targets_missing_anchor_section, _question_tokens, _questions_substantially_overlap, _refresh_final_intake_case_file_snapshot, _reprioritize_candidates_for_intake_objectives, _router_backed_quality_signal, _run_document_generation, _seed_requires_causation_probe, _seed_supports_reasonable_accommodation, _seed_supports_selection_criteria, _select_next_question, _should_apply_empathy_prefix
- Goal id: codebase/runtime/adversarial_harness-session
- Missing evidence: Review swallowed exception path in adversarial_harness/session.py:4449
- Merge key: codebase/runtime/adversarial_harness-session
- Merge family: adversarial_harness/session.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Todo vector key: 7272a7e35b1fb333
- Acceptance: Codebase scan filed this finding from adversarial_harness/session.py:4449. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-082-codebase-scan-7272a7e35b1f.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-088 Review swallowed exception path in adversarial_harness/session.py:4284

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, adversarial_harness/session.py
- Validation: python3 -m py_compile adversarial_harness/session.py
- Bundle: codebase/runtime/adversarial_harness-session
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-adversarial_harness-session.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/adversarial_harness-session
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: adversarial_harness/session.py
- AST symbols: __init__, _anchor_probe_map, _build_document_generation_fallback, _build_fallback_probe, _build_grounding_summary, _build_intake_question_structure_summary, _build_runtime_workflow_guidance, _candidate_matches_intake_objective, _claim_temporal_gap_prompts, _compact_document_generation_result, _coverage_gap_rank, _covered_anchor_sections_from_questions, _default_relief_for_seed, _emit_progress, _empathy_prefix_for_question, _extract_actor_critic_intake_context, _extract_actor_critic_score, _extract_anchor_sections, _extract_blocker_closure_match_count, _extract_claim_temporal_gap_summary, _extract_document_chronology_priority_hints, _extract_intake_prompt_candidates, _extract_latest_batch_priorities, _extract_latest_batch_priority_flags, _extract_phase1_section, _extract_question_objective, _extract_question_text, _extract_question_type, _extract_required_blocker_objectives, _extract_selector_score, _extract_selector_signals, _extract_workflow_phase, _has_empathy_prefix, _inject_intake_prompt_questions, _intake_objective_gap_label, _intake_objective_group, _intake_objective_weight, _is_actor_or_decisionmaker_question, _is_adverse_action_detail_question, _is_causation_sequence_question, _is_contradiction_resolution_question, _is_documentary_evidence_question, _is_exact_dates_question, _is_exhibit_ready_question, _is_harm_or_remedy_question, _is_hearing_request_timing_question, _is_protected_activity_causation_question, _is_redundant_candidate, _is_response_dates_question, _is_staff_names_titles_question, _is_timeline_question, _is_witness_question, _normalize_question, _normalized_actor_critic_score, _normalized_selector_score, _objective_sort_key, _persist_intake_priority_summary, _phase_focus_rank_for_candidate, _phase_focus_weight, _question_dedupe_key, _question_intent_key, _question_mentions_evidence_anchor, _question_objectives_from_prompt, _question_precision_score, _question_quality_score, _question_similarity, _question_specificity_score, _question_targets_anchor_section, _question_targets_missing_anchor_section, _question_tokens, _questions_substantially_overlap, _refresh_final_intake_case_file_snapshot, _reprioritize_candidates_for_intake_objectives, _router_backed_quality_signal, _run_document_generation, _seed_requires_causation_probe, _seed_supports_reasonable_accommodation, _seed_supports_selection_criteria, _select_next_question, _should_apply_empathy_prefix
- Goal id: codebase/runtime/adversarial_harness-session
- Missing evidence: Review swallowed exception path in adversarial_harness/session.py:4284
- Merge key: codebase/runtime/adversarial_harness-session
- Merge family: adversarial_harness/session.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 350c07cde027ae4a
- Acceptance: Codebase scan filed this finding from adversarial_harness/session.py:4284. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-088-codebase-scan-350c07cde027.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-089 Review swallowed exception path in adversarial_harness/session.py:4409

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, adversarial_harness/session.py
- Validation: python3 -m py_compile adversarial_harness/session.py
- Bundle: codebase/runtime/adversarial_harness-session
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-adversarial_harness-session.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/adversarial_harness-session
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: adversarial_harness/session.py
- AST symbols: __init__, _anchor_probe_map, _build_document_generation_fallback, _build_fallback_probe, _build_grounding_summary, _build_intake_question_structure_summary, _build_runtime_workflow_guidance, _candidate_matches_intake_objective, _claim_temporal_gap_prompts, _compact_document_generation_result, _coverage_gap_rank, _covered_anchor_sections_from_questions, _default_relief_for_seed, _emit_progress, _empathy_prefix_for_question, _extract_actor_critic_intake_context, _extract_actor_critic_score, _extract_anchor_sections, _extract_blocker_closure_match_count, _extract_claim_temporal_gap_summary, _extract_document_chronology_priority_hints, _extract_intake_prompt_candidates, _extract_latest_batch_priorities, _extract_latest_batch_priority_flags, _extract_phase1_section, _extract_question_objective, _extract_question_text, _extract_question_type, _extract_required_blocker_objectives, _extract_selector_score, _extract_selector_signals, _extract_workflow_phase, _has_empathy_prefix, _inject_intake_prompt_questions, _intake_objective_gap_label, _intake_objective_group, _intake_objective_weight, _is_actor_or_decisionmaker_question, _is_adverse_action_detail_question, _is_causation_sequence_question, _is_contradiction_resolution_question, _is_documentary_evidence_question, _is_exact_dates_question, _is_exhibit_ready_question, _is_harm_or_remedy_question, _is_hearing_request_timing_question, _is_protected_activity_causation_question, _is_redundant_candidate, _is_response_dates_question, _is_staff_names_titles_question, _is_timeline_question, _is_witness_question, _normalize_question, _normalized_actor_critic_score, _normalized_selector_score, _objective_sort_key, _persist_intake_priority_summary, _phase_focus_rank_for_candidate, _phase_focus_weight, _question_dedupe_key, _question_intent_key, _question_mentions_evidence_anchor, _question_objectives_from_prompt, _question_precision_score, _question_quality_score, _question_similarity, _question_specificity_score, _question_targets_anchor_section, _question_targets_missing_anchor_section, _question_tokens, _questions_substantially_overlap, _refresh_final_intake_case_file_snapshot, _reprioritize_candidates_for_intake_objectives, _router_backed_quality_signal, _run_document_generation, _seed_requires_causation_probe, _seed_supports_reasonable_accommodation, _seed_supports_selection_criteria, _select_next_question, _should_apply_empathy_prefix
- Goal id: codebase/runtime/adversarial_harness-session
- Missing evidence: Review swallowed exception path in adversarial_harness/session.py:4409
- Merge key: codebase/runtime/adversarial_harness-session
- Merge family: adversarial_harness/session.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 8a0485e56dc33b2b
- Acceptance: Codebase scan filed this finding from adversarial_harness/session.py:4409. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-089-codebase-scan-8a0485e56dc3.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-090 Review swallowed exception path in adversarial_harness/session.py:4416

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, adversarial_harness/session.py
- Validation: python3 -m py_compile adversarial_harness/session.py
- Bundle: codebase/runtime/adversarial_harness-session
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-adversarial_harness-session.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/adversarial_harness-session
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: adversarial_harness/session.py
- AST symbols: __init__, _anchor_probe_map, _build_document_generation_fallback, _build_fallback_probe, _build_grounding_summary, _build_intake_question_structure_summary, _build_runtime_workflow_guidance, _candidate_matches_intake_objective, _claim_temporal_gap_prompts, _compact_document_generation_result, _coverage_gap_rank, _covered_anchor_sections_from_questions, _default_relief_for_seed, _emit_progress, _empathy_prefix_for_question, _extract_actor_critic_intake_context, _extract_actor_critic_score, _extract_anchor_sections, _extract_blocker_closure_match_count, _extract_claim_temporal_gap_summary, _extract_document_chronology_priority_hints, _extract_intake_prompt_candidates, _extract_latest_batch_priorities, _extract_latest_batch_priority_flags, _extract_phase1_section, _extract_question_objective, _extract_question_text, _extract_question_type, _extract_required_blocker_objectives, _extract_selector_score, _extract_selector_signals, _extract_workflow_phase, _has_empathy_prefix, _inject_intake_prompt_questions, _intake_objective_gap_label, _intake_objective_group, _intake_objective_weight, _is_actor_or_decisionmaker_question, _is_adverse_action_detail_question, _is_causation_sequence_question, _is_contradiction_resolution_question, _is_documentary_evidence_question, _is_exact_dates_question, _is_exhibit_ready_question, _is_harm_or_remedy_question, _is_hearing_request_timing_question, _is_protected_activity_causation_question, _is_redundant_candidate, _is_response_dates_question, _is_staff_names_titles_question, _is_timeline_question, _is_witness_question, _normalize_question, _normalized_actor_critic_score, _normalized_selector_score, _objective_sort_key, _persist_intake_priority_summary, _phase_focus_rank_for_candidate, _phase_focus_weight, _question_dedupe_key, _question_intent_key, _question_mentions_evidence_anchor, _question_objectives_from_prompt, _question_precision_score, _question_quality_score, _question_similarity, _question_specificity_score, _question_targets_anchor_section, _question_targets_missing_anchor_section, _question_tokens, _questions_substantially_overlap, _refresh_final_intake_case_file_snapshot, _reprioritize_candidates_for_intake_objectives, _router_backed_quality_signal, _run_document_generation, _seed_requires_causation_probe, _seed_supports_reasonable_accommodation, _seed_supports_selection_criteria, _select_next_question, _should_apply_empathy_prefix
- Goal id: codebase/runtime/adversarial_harness-session
- Missing evidence: Review swallowed exception path in adversarial_harness/session.py:4416
- Merge key: codebase/runtime/adversarial_harness-session
- Merge family: adversarial_harness/session.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 8af245b6aa1f9912
- Acceptance: Codebase scan filed this finding from adversarial_harness/session.py:4416. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-090-codebase-scan-8af245b6aa1f.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
