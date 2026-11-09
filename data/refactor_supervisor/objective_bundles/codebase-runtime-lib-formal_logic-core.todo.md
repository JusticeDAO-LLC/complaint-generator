# Codebase Bundle: codebase/runtime/lib-formal_logic-core

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-133 Replace placeholder runtime path in lib/formal_logic/core.py:112

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, lib/formal_logic/core.py
- Validation: python3 -m py_compile lib/formal_logic/core.py
- Bundle: codebase/runtime/lib-formal_logic-core
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-lib-formal_logic-core.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/lib-formal_logic-core
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: lib/formal_logic/core.py
- AST symbols: __future__, __future__.annotations, __init__, __str__, abc, abc abc, abc abstractmethod, abc.abc, abc.abstractmethod, action, action str, action.__str__, add fact, add rule, add statement, add_fact, add_rule, add_statement, check compliance, check_compliance, conjunction, conjunction evaluate, conjunction str, conjunction.__str__, conjunction.evaluate, contains, dataclasses, dataclasses dataclass, dataclasses field, dataclasses.dataclass, dataclasses.field, datetime, datetime datetime, datetime timedelta, datetime.datetime, datetime.timedelta, deonticknowledgebase, deonticknowledgebase add fact, deonticknowledgebase add rule, deonticknowledgebase add statement, deonticknowledgebase check compliance, deonticknowledgebase get statements, deonticknowledgebase infer statements, deonticknowledgebase init, deonticknowledgebase to dict, deonticknowledgebase.__init__, deonticknowledgebase.add_fact, deonticknowledgebase.add_rule, deonticknowledgebase.add_statement, deonticknowledgebase.check_compliance, deonticknowledgebase.get_statements, deonticknowledgebase.infer_statements, deonticknowledgebase.to_dict, deonticmodality, deonticstatement, deonticstatement str, deonticstatement.__str__, disjunction, disjunction evaluate, disjunction str, disjunction.__str__, disjunction.evaluate, enum, enum enum, enum.enum, evaluate, future, future annotations, get statements, get_statements, implication, implication evaluate, implication str, implication.__str__, implication.evaluate, infer statements, infer_statements, init, logicaloperator, negation
- AST symbol scope: file
- Goal id: codebase/runtime/lib-formal_logic-core
- Missing evidence: Replace placeholder runtime path in lib/formal_logic/core.py:112
- Merge key: codebase/runtime/lib-formal_logic-core
- Merge family: lib/formal_logic/core.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 02fac9895cc5b40e
- Acceptance: Codebase scan filed this finding from lib/formal_logic/core.py:112. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-133-codebase-scan-02fac9895cc5.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-134 Replace placeholder runtime path in lib/formal_logic/core.py:116

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, lib/formal_logic/core.py
- Validation: python3 -m py_compile lib/formal_logic/core.py
- Bundle: codebase/runtime/lib-formal_logic-core
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-lib-formal_logic-core.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/lib-formal_logic-core
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: lib/formal_logic/core.py
- AST symbols: __future__, __future__.annotations, __init__, __str__, abc, abc abc, abc abstractmethod, abc.abc, abc.abstractmethod, action, action str, action.__str__, add fact, add rule, add statement, add_fact, add_rule, add_statement, check compliance, check_compliance, conjunction, conjunction evaluate, conjunction str, conjunction.__str__, conjunction.evaluate, contains, dataclasses, dataclasses dataclass, dataclasses field, dataclasses.dataclass, dataclasses.field, datetime, datetime datetime, datetime timedelta, datetime.datetime, datetime.timedelta, deonticknowledgebase, deonticknowledgebase add fact, deonticknowledgebase add rule, deonticknowledgebase add statement, deonticknowledgebase check compliance, deonticknowledgebase get statements, deonticknowledgebase infer statements, deonticknowledgebase init, deonticknowledgebase to dict, deonticknowledgebase.__init__, deonticknowledgebase.add_fact, deonticknowledgebase.add_rule, deonticknowledgebase.add_statement, deonticknowledgebase.check_compliance, deonticknowledgebase.get_statements, deonticknowledgebase.infer_statements, deonticknowledgebase.to_dict, deonticmodality, deonticstatement, deonticstatement str, deonticstatement.__str__, disjunction, disjunction evaluate, disjunction str, disjunction.__str__, disjunction.evaluate, enum, enum enum, enum.enum, evaluate, future, future annotations, get statements, get_statements, implication, implication evaluate, implication str, implication.__str__, implication.evaluate, infer statements, infer_statements, init, logicaloperator, negation
- AST symbol scope: file
- Goal id: codebase/runtime/lib-formal_logic-core
- Missing evidence: Replace placeholder runtime path in lib/formal_logic/core.py:116
- Merge key: codebase/runtime/lib-formal_logic-core
- Merge family: lib/formal_logic/core.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 1c182497d16a23bf
- Acceptance: Codebase scan filed this finding from lib/formal_logic/core.py:116. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-134-codebase-scan-1c182497d16a.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
