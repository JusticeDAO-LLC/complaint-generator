# Objective Bundle: refactor/g10/g10-s2

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-203: REF-203 Add analyzer canaries, parser failure budgets, and fail-closed health classification

## REF-203 Add analyzer canaries, parser failure budgets, and fail-closed health classification

- Status: completed
- Completion: manual
- Priority: P0
- Track: G10
- Depends on: REF-201
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/analyzer_health.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/backlog_refinery.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_analyzer_health.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_backlog_refinery.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_analyzer_health.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_backlog_refinery.py -q
- Bundle: refactor/g10/g10-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G10.S2
- Missing evidence: A scanner that silently stops recognizing syntax can otherwise report the same zero findings as a complete repository.
- AST symbols: ANALYZER_HEALTH_SCHEMA, ANALYZER_CANARY_SCHEMA, ANALYSIS_ESCALATION_SCHEMA, _env_bool, AnalyzerHealthStatus, AnalysisEscalationStage, AnalysisEscalationStatus, AnalysisEscalationPolicy, AnalysisEscalationLimits, AnalysisEscalationRecord, AnalyzerHealthThresholds, AnalyzerCanaryFixture, _CODEBASE_V1_CANARIES, validate_canary_registry, AnalyzerCanaryResult, AnalyzerCanaryReport, CanaryAnalyzer, run_analyzer_canaries, AnalyzerHealthReport, _FUNNEL_KEYS, _integer, impossible_candidate_funnel, classify_analyzer_health, __all__, value, HEALTHY, PARTIAL, UNHEALTHY, INCREMENTAL_STATIC, EXHAUSTIVE_AST
- Merge key: refactor/g10/g10-s2
- Candidate kind: seed
- Todo vector key: ref-203-addanalyzercanariesparserfailurebudgetsandfail-c
- Acceptance: Deterministic fixtures exercise every supported finding kind and parser path on each analyzer version.; Missing canaries, excessive skips, parser failures, incomplete git-root discovery, and impossible candidate funnels classify the scan as unhealthy or partial.; Health thresholds are configurable, recorded in the receipt, and cannot silently downgrade a failed scan to exhausted.; The daemon continues safe implementation work while preventing unhealthy analysis from closing goals.

- [x] Task checkbox-204: REF-204 Implement fingerprint-independent audit scans and exhaustion quorum

## REF-204 Implement fingerprint-independent audit scans and exhaustion quorum

- Status: completed
- Completion: manual
- Priority: P0
- Track: G10
- Depends on: REF-201, REF-202
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/audit_scanner.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/scan_receipts.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/backlog_refinery.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/dataset_store.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_audit_scanner.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_audit_scanner.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_incremental_runtime.py -q
- Bundle: refactor/g10/g10-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G10.S2
- Missing evidence: A saturated or corrupt seen-fingerprint set can make normal refill scans appear exhausted without independently re-evaluating the codebase.
- AST symbols: AUDIT_SCANNER_VERSION, AST_COVERAGE_ANALYZER_VERSION, AuditFindingStatus, AuditFindingDisposition, AstCoverageReport, run_exhaustive_ast_coverage, _finding_mapping, _finding, audit_finding_key, audit_finding_content_revision, audit_snapshot_record, AuditFindingRecord, AuditFindingChange, classify_audit_findings, AuditScanResult, AuditScanReport, _audit_gate_reason, _audit_scope_id, _configuration, AnalysisEscalationResult, _analysis_candidate_dict, _stage_values, run_low_backlog_analysis, run_analysis_escalation, escalate_low_backlog_analysis, run_audit_scan, audit_codebase_findings, scan_codebase_audit, __all__, KNOWN
- Merge key: refactor/g10/g10-s2
- Candidate kind: seed
- Todo vector key: ref-204-implementfingerprint-independentauditscansandexh
- Acceptance: Audit mode scans without mutating or trusting the normal seen set and reports known, stale, changed, and novel findings separately.; Exhaustion requires a configurable quorum of healthy exhaustive receipts tied to repository tree, analyzer version, configuration, and objective revision.; Relevant code, configuration, analyzer, or objective changes invalidate prior quorum members deterministically.; Repeated scans of an unchanged tree are deduplicated and cannot manufacture quorum confidence.

- [x] Task checkbox-205: REF-205 Escalate low-backlog analysis through AST and llm_router planning before declaring exhaustion

## REF-205 Escalate low-backlog analysis through AST and llm_router planning before declaring exhaustion

- Status: completed
- Completion: manual
- Priority: P1
- Track: G10
- Depends on: REF-203, REF-204
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/analyzer_health.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/audit_scanner.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_proposal_router.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/plan_evaluator.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_analysis_escalation.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_analysis_escalation.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py -q
- Bundle: refactor/g10/g10-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G10.S2
- Missing evidence: Static pattern exhaustion should trigger bounded semantic and goal-directed analysis rather than leave the board below its configured floor without explanation.
- AST symbols: ANALYZER_HEALTH_SCHEMA, ANALYZER_CANARY_SCHEMA, ANALYSIS_ESCALATION_SCHEMA, _env_bool, AnalyzerHealthStatus, AnalysisEscalationStage, AnalysisEscalationStatus, AnalysisEscalationPolicy, AnalysisEscalationLimits, AnalysisEscalationRecord, AnalyzerHealthThresholds, AnalyzerCanaryFixture, _CODEBASE_V1_CANARIES, validate_canary_registry, AnalyzerCanaryResult, AnalyzerCanaryReport, CanaryAnalyzer, run_analyzer_canaries, AnalyzerHealthReport, _FUNNEL_KEYS, _integer, impossible_candidate_funnel, classify_analyzer_health, __all__, value, HEALTHY, PARTIAL, UNHEALTHY, INCREMENTAL_STATIC, EXHAUSTIVE_AST
- Merge key: refactor/g10/g10-s2
- Candidate kind: seed
- Todo vector key: ref-205-escalatelow-backloganalysisthroughastandllm-rout
- Acceptance: A policy escalates from incremental static scan to exhaustive AST coverage and then schema-constrained llm_router proposals when healthy backlog remains below target.; Each escalation records cost, scope, novelty, confidence, rejected candidates, and the objective terms it attempted to cover.; Router failure or low-confidence output produces an analysis-inconclusive result and deterministic fallback, never a false completion.; Rate, token, retry, and novelty limits prevent an unbounded task-generation loop.
