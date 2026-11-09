# Codebase Bundle: codebase/runtime/complaint_phases-knowledge_graph

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-087 Resolve code annotation in complaint_phases/knowledge_graph.py:2168

- Status: completed
- Completion: manual
- Priority: P3
- Track: runtime
- Depends on: 
- Outputs: data/agent_supervisor/discovery, complaint_phases/knowledge_graph.py
- Validation: python3 -m py_compile complaint_phases/knowledge_graph.py
- Bundle: codebase/runtime/complaint_phases-knowledge_graph
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-complaint_phases-knowledge_graph.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/complaint_phases-knowledge_graph
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: complaint_phases/knowledge_graph.py
- AST symbols: __init__, _apply_entity_actor_critic, _apply_relationship_actor_critic, _clamp, _entity_actor_score, _entity_critic_penalty, _entity_text, _env_bool, _env_float, _extract_entities, _extract_event_date_reference, _extract_relationships, _get_entity_id, _get_relationship_id, _has_date_signal, _has_exact_date_signal, _llm_extract_entities, _llm_extract_relationships, _merge_provenance, _relation_actor_score, _relation_critic_penalty, _support_facts, _update_metadata, _utc_now_isoformat, add entity, add relationship, add timeline event fact, add_entity, add_relationship, add_timeline_event_fact, apply entity actor critic, apply relationship actor critic, average confidence, average entities per graph, average relationships per entity, average relationships per graph, average_confidence, average_entities_per_graph, average_relationships_per_entity, average_relationships_per_graph, bind graph services, bind_graph_services, build from text, build_from_text, clamp, dataclasses, dataclasses asdict, dataclasses dataclass, dataclasses field, dataclasses.asdict, dataclasses.dataclass, dataclasses.field, datetime, datetime datetime, datetime utc, datetime.datetime, datetime.utc, entity, entity actor score, entity critic penalty, entity extraction rate, entity text, entity to dict, entity type distribution, entity.to_dict, entity_extraction_rate, entity_type_distribution, env bool, env float, extract entities, extract event date reference, extract relationships, find gaps, find_gaps, from dict, from json, from_dict, from_json, get entities by type, get entity
- Goal id: codebase/runtime/complaint_phases-knowledge_graph
- Missing evidence: Resolve code annotation in complaint_phases/knowledge_graph.py:2168
- Merge key: codebase/runtime/complaint_phases-knowledge_graph
- Merge family: complaint_phases/knowledge_graph.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Todo vector key: fef985c2cd7eb07d
- Acceptance: Codebase scan filed this finding from complaint_phases/knowledge_graph.py:2168. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-087-codebase-scan-fef985c2cd7e.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
