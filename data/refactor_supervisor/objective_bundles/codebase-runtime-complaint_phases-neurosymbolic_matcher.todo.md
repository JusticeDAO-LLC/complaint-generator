# Codebase Bundle: codebase/runtime/complaint_phases-neurosymbolic_matcher

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-094 Resolve code annotation in complaint_phases/neurosymbolic_matcher.py:269

- Status: completed
- Completion: manual
- Priority: P3
- Track: runtime
- Depends on: 
- Outputs: data/agent_supervisor/discovery, complaint_phases/neurosymbolic_matcher.py
- Validation: python3 -m py_compile complaint_phases/neurosymbolic_matcher.py
- Bundle: codebase/runtime/complaint_phases-neurosymbolic_matcher
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-complaint_phases-neurosymbolic_matcher.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/complaint_phases-neurosymbolic_matcher
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: complaint_phases/neurosymbolic_matcher.py
- AST symbols: __init__, _check_requirement_satisfied, _llm_semantic_match, _match_single_claim, _requirement_matches, _semantic_requirement_check, assess claim viability, assess_claim_viability, average gaps per result, average satisfaction score, average_gaps_per_result, average_satisfaction_score, check requirement satisfied, dependency graph, dependency graph dependencygraph, dependency graph dependencynode, dependency graph nodetype, dependency_graph, dependency_graph.dependencygraph, dependency_graph.dependencynode, dependency_graph.nodetype, gap frequency distribution, gap_frequency_distribution, generate fact finding recommendations, generate_fact_finding_recommendations, high viability percentage, high_viability_percentage, init, knowledge graph, knowledge graph entity, knowledge graph knowledgegraph, knowledge_graph, knowledge_graph.entity, knowledge_graph.knowledgegraph, legal graph, legal graph legalelement, legal graph legalgraph, legal_graph, legal_graph.legalelement, legal_graph.legalgraph, llm semantic match, logging, match claims to law, match single claim, match_claims_to_law, matching history size, matching_history_size, most common gap, most_common_gap, neurosymbolicmatcher, neurosymbolicmatcher assess claim viability, neurosymbolicmatcher average gaps per result, neurosymbolicmatcher average satisfaction score, neurosymbolicmatcher check requirement satisfied, neurosymbolicmatcher gap frequency distribution, neurosymbolicmatcher generate fact finding recommendations, neurosymbolicmatcher high viability percentage, neurosymbolicmatcher init, neurosymbolicmatcher llm semantic match, neurosymbolicmatcher match claims to law, neurosymbolicmatcher match single claim, neurosymbolicmatcher matching history size, neurosymbolicmatcher most common gap, neurosymbolicmatcher requirement matches, neurosymbolicmatcher satisfaction improvement trend, neurosymbolicmatcher satisfaction variance, neurosymbolicmatcher semantic requirement check, neurosymbolicmatcher total claims processed, neurosymbolicmatcher total satisfied claims, neurosymbolicmatcher.__init__, neurosymbolicmatcher._check_requirement_satisfied, neurosymbolicmatcher._llm_semantic_match, neurosymbolicmatcher._match_single_claim, neurosymbolicmatcher._requirement_matches, neurosymbolicmatcher._semantic_requirement_check, neurosymbolicmatcher.assess_claim_viability, neurosymbolicmatcher.average_gaps_per_result, neurosymbolicmatcher.average_satisfaction_score, neurosymbolicmatcher.gap_frequency_distribution, neurosymbolicmatcher.generate_fact_finding_recommendations
- AST symbol scope: file
- Goal id: codebase/runtime/complaint_phases-neurosymbolic_matcher
- Missing evidence: Resolve code annotation in complaint_phases/neurosymbolic_matcher.py:269
- Merge key: codebase/runtime/complaint_phases-neurosymbolic_matcher
- Merge family: complaint_phases/neurosymbolic_matcher.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 7bc1d7368daf69b1
- Acceptance: Codebase scan filed this finding from complaint_phases/neurosymbolic_matcher.py:269. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-094-codebase-scan-7bc1d7368daf.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
