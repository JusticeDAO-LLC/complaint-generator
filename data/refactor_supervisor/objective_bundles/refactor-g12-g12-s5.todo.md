# Objective Bundle: refactor/g12/g12-s5

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [!] Task checkbox-291: REF-291 Admit every prover family through one shared CPU and process budget

## REF-291 Admit every prover family through one shared CPU and process budget

- Status: blocked
- Completion: manual
- Priority: P0
- Track: G12
- Depends on: REF-258, REF-281, REF-283, REF-285, REF-286, REF-287
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/multi_prover_resources.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_multi_prover_resources.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_multi_prover_resources.py -q
- Bundle: refactor/g12/g12-s5
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G12.S5
- Missing evidence: JVM model checkers, SMT solvers, ATPs, kernels, protocol tools, tests, and models must not create nested pools that oversubscribe the host.
- AST symbols: 
- Merge key: refactor/g12/g12-s5
- Candidate kind: seed
- Todo vector key: ref-291-admiteveryproverfamilythroughonesharedcpuandproc
- Acceptance: Resource classes cover translation, SMT, ATP, ITP kernels, JVM model checking, protocol verification, hyperproperty checking, runtime monitors, LLM inference, and artifact IO.; One top-level lease accounts for child processes, threads, memory, disk, provider quota, and model concurrency across serial and bundle supervisors.; Bundle admission launches dependency-closed ready-member slices so a later blocked member cannot idle earlier work, and mixed-readiness lanes retain task dependency enforcement.; Timeout and cancellation terminate process groups, release capacity, and preserve bounded diagnostics and partial receipts.; Portfolio width adapts to host pressure and critical-path value while deterministic cache hits bypass execution safely.

- [!] Task checkbox-292: REF-292 Adversarially test formal plans and every prover-matrix trust boundary

## REF-292 Adversarially test formal plans and every prover-matrix trust boundary

- Status: blocked
- Completion: manual
- Priority: P0
- Track: G12
- Depends on: REF-271, REF-282, REF-290, REF-291
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_planning_adversarial.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_planning_adversarial.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_planning_adversarial.py -q
- Bundle: refactor/g12/g12-s5
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G12.S5
- Missing evidence: The expanded planner must resist forged plans, unsound translations, stale evidence, malicious tool output, and cross-lane leakage.
- AST symbols: 
- Merge key: refactor/g12/g12-s5
- Candidate kind: seed
- Todo vector key: ref-292-adversariallytestformalplansandeveryprover-matri
- Acceptance: Tests mutate actor authority, temporal bounds, task dependencies, formulas, models, premises, tool versions, cache keys, receipts, traces, and assurance labels.; Fixtures cover unavailable tools, fake executable versions, solver disagreement, incomplete exploration, protocol false positives, hypertrace leakage, and monitor gaps.; No path promotes model text, native heuristic proofs, bounded results without bounds, simulated ZKP, or stale cache entries beyond policy.; Parallel crash, cancellation, restart, and duplicate claims preserve single-flight and fail-closed behavior.

- [!] Task checkbox-293: REF-293 Exercise an end-to-end proof-carrying planning and implementation workflow

## REF-293 Exercise an end-to-end proof-carrying planning and implementation workflow

- Status: blocked
- Completion: manual
- Priority: P0
- Track: G12
- Depends on: REF-292
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_carrying_planner.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_carrying_planner_e2e.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_carrying_planner_e2e.py -q
- Bundle: refactor/g12/g12-s5
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G12.S5
- Missing evidence: Formal planning, bounded model context, implementation, verification, runtime monitoring, and replanning must work as one restartable workflow.
- AST symbols: 
- Merge key: refactor/g12/g12-s5
- Candidate kind: seed
- Todo vector key: ref-293-exerciseanend-to-endproof-carryingplanningandimp
- Acceptance: The workflow compiles and verifies a plan, dispatches independent Codex tasks, verifies changed scopes, merges accepted work, monitors execution, and repairs a seeded counterexample.; It exercises Hammer reconstruction, Lean or Coq checking, Leanstral shadow proposals, optional ZKP attestation, matrix-specific lanes, and test fallbacks without conflating assurance.; Independent plan and proof nodes execute concurrently while conflict, dependency, and shared-resource constraints remain authoritative.; All decisions are reproducible from paired JSON and DuckDB artifacts after restart.

- [!] Task checkbox-294: REF-294 Benchmark and gate formal-planning rollout by assurance and throughput

## REF-294 Benchmark and gate formal-planning rollout by assurance and throughput

- Status: blocked
- Completion: manual
- Priority: P1
- Track: G12
- Depends on: REF-273, REF-274, REF-293
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_planning_metrics.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_planning_rollout.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_planning_benchmarks.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_planning_benchmarks.py -q
- Bundle: refactor/g12/g12-s5
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G12.S5
- Missing evidence: The broader prover matrix should expand only when it reduces model work and improves defect detection without unacceptable CPU or scheduling regressions.
- AST symbols: 
- Merge key: refactor/g12/g12-s5
- Candidate kind: seed
- Todo vector key: ref-294-benchmarkandgateformal-planningrolloutbyassuranc
- Acceptance: Cold and warm benchmarks measure context tokens, plan defects found before LLM dispatch, proof support, counterexample quality, cache reuse, queue latency, CPU saturation, memory, and accepted-task throughput.; Metrics separate property class, translator profile, prover, kernel, finite bound, rollout mode, task risk, and authoritative assurance.; Shadow, canary, and enforcement thresholds are explicit; unavailable or low-value lanes remain advisory and operator overrides remain durable and scoped.; Operator projections expose the executable matrix, degraded reasons, active formal plans, unmet obligations, trace violations, and rollout decisions without raw context dumps.
