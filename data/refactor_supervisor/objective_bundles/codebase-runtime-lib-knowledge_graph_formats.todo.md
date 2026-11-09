# Codebase Bundle: codebase/runtime/lib-knowledge_graph_formats

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-135 Replace placeholder runtime path in lib/knowledge_graph_formats.py:82

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, lib/knowledge_graph_formats.py
- Validation: python3 -m py_compile lib/knowledge_graph_formats.py
- Bundle: codebase/runtime/lib-knowledge_graph_formats
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-lib-knowledge_graph_formats.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/lib-knowledge_graph_formats
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: lib/knowledge_graph_formats.py
- AST symbols: __init__, _builtin_load_dag_json, _builtin_load_json_lines, _builtin_save_dag_json, _builtin_save_json_lines, _formatregistry, _formatregistry.__init__, _formatregistry.load, _formatregistry.register, _formatregistry.registered_formats, _formatregistry.save, builtin load dag json, builtin load json lines, builtin save dag json, builtin save json lines, dataclasses, dataclasses dataclass, dataclasses field, dataclasses.dataclass, dataclasses.field, enum, enum enum, enum.enum, formatregistry, formatregistry init, formatregistry load, formatregistry register, formatregistry registered formats, formatregistry save, from dict, from json, from_dict, from_json, graphdata, graphdata from dict, graphdata from json, graphdata iter nodes chunked, graphdata iter relationships chunked, graphdata load from file, graphdata save to file, graphdata to dict, graphdata to json, graphdata.from_dict, graphdata.from_json, graphdata.iter_nodes_chunked, graphdata.iter_relationships_chunked, graphdata.load_from_file, graphdata.save_to_file, graphdata.to_dict, graphdata.to_json, init, ipfs datasets py knowledge graphs migration formats, ipfs datasets py knowledge graphs migration formats graphdata, ipfs datasets py knowledge graphs migration formats migrationformat, ipfs datasets py knowledge graphs migration formats nodedata, ipfs datasets py knowledge graphs migration formats register format, ipfs datasets py knowledge graphs migration formats registered formats, ipfs datasets py knowledge graphs migration formats relationshipdata, ipfs datasets py knowledge graphs migration formats schemadata, ipfs_datasets_py.knowledge_graphs.migration.formats, ipfs_datasets_py.knowledge_graphs.migration.formats.graphdata, ipfs_datasets_py.knowledge_graphs.migration.formats.migrationformat, ipfs_datasets_py.knowledge_graphs.migration.formats.nodedata, ipfs_datasets_py.knowledge_graphs.migration.formats.register_format, ipfs_datasets_py.knowledge_graphs.migration.formats.registered_formats, ipfs_datasets_py.knowledge_graphs.migration.formats.relationshipdata, ipfs_datasets_py.knowledge_graphs.migration.formats.schemadata, iter nodes chunked, iter relationships chunked, iter_nodes_chunked, iter_relationships_chunked, json, load, load from file, load_from_file, migrationformat, nodedata, nodedata from dict, nodedata to dict, nodedata to json
- AST symbol scope: file
- Goal id: codebase/runtime/lib-knowledge_graph_formats
- Missing evidence: Replace placeholder runtime path in lib/knowledge_graph_formats.py:82
- Merge key: codebase/runtime/lib-knowledge_graph_formats
- Merge family: lib/knowledge_graph_formats.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 018923b8aa31e26f
- Acceptance: Codebase scan filed this finding from lib/knowledge_graph_formats.py:82. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-135-codebase-scan-018923b8aa31.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
