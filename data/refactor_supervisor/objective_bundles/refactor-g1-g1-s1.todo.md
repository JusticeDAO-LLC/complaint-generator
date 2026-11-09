# Objective Bundle: refactor/g1/g1-s1

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-1: REF-001 Create an entrypoint and ownership map for the largest runtime modules

## REF-001 Create an entrypoint and ownership map for the largest runtime modules

- Status: completed
- Completion: manual
- Priority: P0
- Track: G1
- Depends on: 
- Outputs: mediator/mediator.py, applications/complaint_workspace.py, tests/test_claim_support_review_playwright_smoke.py, scripts/synthesize_hacc_complaint.py, tests/test_review_api.py, complaint_phases/denoiser.py
- Validation: python -m pytest tests/test_package_imports.py -q
- Bundle: refactor/g1/g1-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G1.S1
- Missing evidence: Large modules dominate change risk and need explicit boundaries before extraction.
- AST symbols: ALIGNMENT_TASK_UPDATE_HISTORY_LIMIT, FOLLOW_UP_REVIEWABLE_ESCALATION_STATUSES, Mediator, __init__, reset, resume, get_state, set_state, response, select_intake_question_candidates, _phase_focus_rank, _phase_focus_bonus, _is_document_question_candidate, _build_exhibit_ready_document_question, _apply_exhibit_ready_intake_questioning, _is_exact_dates_closure_match, _is_staff_names_titles_closure_match, _is_hearing_request_timing_closure_match, _is_response_dates_closure_match, _is_causation_sequence_match, _build_intake_claim_pressure_map, _build_intake_selector_legal_graph, _build_intake_matching_pressure_map, _build_intake_workflow_action_queue, _summarize_intake_workflow_action_queue, _build_evidence_workflow_action_queue, _get_document_provenance_summary, _get_document_grounding_lane_outcome_summary, _get_document_grounding_recovery_action, _get_document_grounding_improvement_next_action
- Merge key: refactor/g1/g1-s1
- Candidate kind: seed
- Todo vector key: ref-001-createanentrypointandownershipmapforthelargestru
- Acceptance: A short module ownership map exists.; Entrypoints are grouped by CLI, web, mediator, and workflow role.

- [x] Task checkbox-2: REF-002 Document allowed dependency direction between applications, mediator, phases, integrations, and lib

## REF-002 Document allowed dependency direction between applications, mediator, phases, integrations, and lib

- Status: completed
- Completion: manual
- Priority: P0
- Track: G1
- Depends on: 
- Outputs: docs/ARCHITECTURE.md, pyproject.toml
- Validation: python -m pytest tests/test_package_imports.py -q
- Bundle: refactor/g1/g1-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G1.S1
- Missing evidence: Refactors need a clear import direction to avoid moving complexity around.
- AST symbols: 
- Merge key: refactor/g1/g1-s1
- Candidate kind: seed
- Todo vector key: ref-002-documentalloweddependencydirectionbetweenapplica
- Acceptance: Architecture docs identify allowed imports.; New work has a simple rule for where shared code belongs.
