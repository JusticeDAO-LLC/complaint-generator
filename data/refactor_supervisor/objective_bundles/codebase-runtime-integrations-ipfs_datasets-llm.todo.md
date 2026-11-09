# Codebase Bundle: codebase/runtime/integrations-ipfs_datasets-llm

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-124 Review swallowed exception path in integrations/ipfs_datasets/llm.py:78

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, integrations/ipfs_datasets/llm.py
- Validation: python3 -m py_compile integrations/ipfs_datasets/llm.py
- Bundle: codebase/runtime/integrations-ipfs_datasets-llm
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-integrations-ipfs_datasets-llm.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/integrations-ipfs_datasets-llm
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: integrations/ipfs_datasets/llm.py
- AST symbols: __future__, __future__.annotations, _build_arch_router_prompt, _build_huggingface_router_request, _coalesce_env, _coerce_bool, _env_value, _extract_arch_router_config, _is_huggingface_router_request, _normalize_arch_router_routes, _normalize_headers, _parse_arch_router_route, _pop_first_string, _prepare_generate_text_call, _provider_preflight_error, _resolve_hf_token, _resolve_openai_api_key, _select_huggingface_arch_route, _slugify_route_name, _strip_code_fences, _temporary_env, build arch router prompt, build huggingface router request, coalesce env, coerce bool, contextlib, contextlib contextmanager, contextlib.contextmanager, env value, extract arch router config, future, future annotations, generate text via router, generate text with metadata, generate_text_via_router, generate_text_with_metadata, importlib, ipfs datasets py mcp server secrets vault, ipfs datasets py mcp server secrets vault get secrets vault, ipfs_datasets_py.mcp_server.secrets_vault, ipfs_datasets_py.mcp_server.secrets_vault.get_secrets_vault, is huggingface router request, json, keyring, llm router status, llm_router_status, loader, loader import attr optional, loader.import_attr_optional, normalize arch router routes, normalize headers, os, parse arch router route, pop first string, prepare generate text call, provider preflight error, re, resolve hf token, resolve openai api key, select huggingface arch route, shutil, slugify route name, strip code fences, temporary env, threading, types, types with adapter metadata, types.with_adapter_metadata, typing, typing any, typing dict, typing mapping, typing optional, typing.any, typing.dict, typing.mapping, typing.optional
- AST symbol scope: file
- Goal id: codebase/runtime/integrations-ipfs_datasets-llm
- Missing evidence: Review swallowed exception path in integrations/ipfs_datasets/llm.py:78
- Merge key: codebase/runtime/integrations-ipfs_datasets-llm
- Merge family: integrations/ipfs_datasets/llm.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 2d77448bbfcc8106
- Acceptance: Codebase scan filed this finding from integrations/ipfs_datasets/llm.py:78. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-124-codebase-scan-2d77448bbfcc.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-125 Review swallowed exception path in integrations/ipfs_datasets/llm.py:96

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, integrations/ipfs_datasets/llm.py
- Validation: python3 -m py_compile integrations/ipfs_datasets/llm.py
- Bundle: codebase/runtime/integrations-ipfs_datasets-llm
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-integrations-ipfs_datasets-llm.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/integrations-ipfs_datasets-llm
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: integrations/ipfs_datasets/llm.py
- AST symbols: __future__, __future__.annotations, _build_arch_router_prompt, _build_huggingface_router_request, _coalesce_env, _coerce_bool, _env_value, _extract_arch_router_config, _is_huggingface_router_request, _normalize_arch_router_routes, _normalize_headers, _parse_arch_router_route, _pop_first_string, _prepare_generate_text_call, _provider_preflight_error, _resolve_hf_token, _resolve_openai_api_key, _select_huggingface_arch_route, _slugify_route_name, _strip_code_fences, _temporary_env, build arch router prompt, build huggingface router request, coalesce env, coerce bool, contextlib, contextlib contextmanager, contextlib.contextmanager, env value, extract arch router config, future, future annotations, generate text via router, generate text with metadata, generate_text_via_router, generate_text_with_metadata, importlib, ipfs datasets py mcp server secrets vault, ipfs datasets py mcp server secrets vault get secrets vault, ipfs_datasets_py.mcp_server.secrets_vault, ipfs_datasets_py.mcp_server.secrets_vault.get_secrets_vault, is huggingface router request, json, keyring, llm router status, llm_router_status, loader, loader import attr optional, loader.import_attr_optional, normalize arch router routes, normalize headers, os, parse arch router route, pop first string, prepare generate text call, provider preflight error, re, resolve hf token, resolve openai api key, select huggingface arch route, shutil, slugify route name, strip code fences, temporary env, threading, types, types with adapter metadata, types.with_adapter_metadata, typing, typing any, typing dict, typing mapping, typing optional, typing.any, typing.dict, typing.mapping, typing.optional
- AST symbol scope: file
- Goal id: codebase/runtime/integrations-ipfs_datasets-llm
- Missing evidence: Review swallowed exception path in integrations/ipfs_datasets/llm.py:96
- Merge key: codebase/runtime/integrations-ipfs_datasets-llm
- Merge family: integrations/ipfs_datasets/llm.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 9d6be93589b36c91
- Acceptance: Codebase scan filed this finding from integrations/ipfs_datasets/llm.py:96. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-125-codebase-scan-9d6be93589b3.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-126 Review swallowed exception path in integrations/ipfs_datasets/llm.py:127

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, integrations/ipfs_datasets/llm.py
- Validation: python3 -m py_compile integrations/ipfs_datasets/llm.py
- Bundle: codebase/runtime/integrations-ipfs_datasets-llm
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-integrations-ipfs_datasets-llm.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/integrations-ipfs_datasets-llm
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: integrations/ipfs_datasets/llm.py
- AST symbols: __future__, __future__.annotations, _build_arch_router_prompt, _build_huggingface_router_request, _coalesce_env, _coerce_bool, _env_value, _extract_arch_router_config, _is_huggingface_router_request, _normalize_arch_router_routes, _normalize_headers, _parse_arch_router_route, _pop_first_string, _prepare_generate_text_call, _provider_preflight_error, _resolve_hf_token, _resolve_openai_api_key, _select_huggingface_arch_route, _slugify_route_name, _strip_code_fences, _temporary_env, build arch router prompt, build huggingface router request, coalesce env, coerce bool, contextlib, contextlib contextmanager, contextlib.contextmanager, env value, extract arch router config, future, future annotations, generate text via router, generate text with metadata, generate_text_via_router, generate_text_with_metadata, importlib, ipfs datasets py mcp server secrets vault, ipfs datasets py mcp server secrets vault get secrets vault, ipfs_datasets_py.mcp_server.secrets_vault, ipfs_datasets_py.mcp_server.secrets_vault.get_secrets_vault, is huggingface router request, json, keyring, llm router status, llm_router_status, loader, loader import attr optional, loader.import_attr_optional, normalize arch router routes, normalize headers, os, parse arch router route, pop first string, prepare generate text call, provider preflight error, re, resolve hf token, resolve openai api key, select huggingface arch route, shutil, slugify route name, strip code fences, temporary env, threading, types, types with adapter metadata, types.with_adapter_metadata, typing, typing any, typing dict, typing mapping, typing optional, typing.any, typing.dict, typing.mapping, typing.optional
- AST symbol scope: file
- Goal id: codebase/runtime/integrations-ipfs_datasets-llm
- Missing evidence: Review swallowed exception path in integrations/ipfs_datasets/llm.py:127
- Merge key: codebase/runtime/integrations-ipfs_datasets-llm
- Merge family: integrations/ipfs_datasets/llm.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 5ad6e5b2a62e8746
- Acceptance: Codebase scan filed this finding from integrations/ipfs_datasets/llm.py:127. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-126-codebase-scan-5ad6e5b2a62e.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-127 Review swallowed exception path in integrations/ipfs_datasets/llm.py:137

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, integrations/ipfs_datasets/llm.py
- Validation: python3 -m py_compile integrations/ipfs_datasets/llm.py
- Bundle: codebase/runtime/integrations-ipfs_datasets-llm
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-integrations-ipfs_datasets-llm.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/integrations-ipfs_datasets-llm
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: integrations/ipfs_datasets/llm.py
- AST symbols: __future__, __future__.annotations, _build_arch_router_prompt, _build_huggingface_router_request, _coalesce_env, _coerce_bool, _env_value, _extract_arch_router_config, _is_huggingface_router_request, _normalize_arch_router_routes, _normalize_headers, _parse_arch_router_route, _pop_first_string, _prepare_generate_text_call, _provider_preflight_error, _resolve_hf_token, _resolve_openai_api_key, _select_huggingface_arch_route, _slugify_route_name, _strip_code_fences, _temporary_env, build arch router prompt, build huggingface router request, coalesce env, coerce bool, contextlib, contextlib contextmanager, contextlib.contextmanager, env value, extract arch router config, future, future annotations, generate text via router, generate text with metadata, generate_text_via_router, generate_text_with_metadata, importlib, ipfs datasets py mcp server secrets vault, ipfs datasets py mcp server secrets vault get secrets vault, ipfs_datasets_py.mcp_server.secrets_vault, ipfs_datasets_py.mcp_server.secrets_vault.get_secrets_vault, is huggingface router request, json, keyring, llm router status, llm_router_status, loader, loader import attr optional, loader.import_attr_optional, normalize arch router routes, normalize headers, os, parse arch router route, pop first string, prepare generate text call, provider preflight error, re, resolve hf token, resolve openai api key, select huggingface arch route, shutil, slugify route name, strip code fences, temporary env, threading, types, types with adapter metadata, types.with_adapter_metadata, typing, typing any, typing dict, typing mapping, typing optional, typing.any, typing.dict, typing.mapping, typing.optional
- AST symbol scope: file
- Goal id: codebase/runtime/integrations-ipfs_datasets-llm
- Missing evidence: Review swallowed exception path in integrations/ipfs_datasets/llm.py:137
- Merge key: codebase/runtime/integrations-ipfs_datasets-llm
- Merge family: integrations/ipfs_datasets/llm.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 16bcf37c319c0b0e
- Acceptance: Codebase scan filed this finding from integrations/ipfs_datasets/llm.py:137. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-127-codebase-scan-16bcf37c319c.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-128 Review swallowed exception path in integrations/ipfs_datasets/llm.py:331

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, integrations/ipfs_datasets/llm.py
- Validation: python3 -m py_compile integrations/ipfs_datasets/llm.py
- Bundle: codebase/runtime/integrations-ipfs_datasets-llm
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-integrations-ipfs_datasets-llm.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/integrations-ipfs_datasets-llm
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: integrations/ipfs_datasets/llm.py
- AST symbols: __future__, __future__.annotations, _build_arch_router_prompt, _build_huggingface_router_request, _coalesce_env, _coerce_bool, _env_value, _extract_arch_router_config, _is_huggingface_router_request, _normalize_arch_router_routes, _normalize_headers, _parse_arch_router_route, _pop_first_string, _prepare_generate_text_call, _provider_preflight_error, _resolve_hf_token, _resolve_openai_api_key, _select_huggingface_arch_route, _slugify_route_name, _strip_code_fences, _temporary_env, build arch router prompt, build huggingface router request, coalesce env, coerce bool, contextlib, contextlib contextmanager, contextlib.contextmanager, env value, extract arch router config, future, future annotations, generate text via router, generate text with metadata, generate_text_via_router, generate_text_with_metadata, importlib, ipfs datasets py mcp server secrets vault, ipfs datasets py mcp server secrets vault get secrets vault, ipfs_datasets_py.mcp_server.secrets_vault, ipfs_datasets_py.mcp_server.secrets_vault.get_secrets_vault, is huggingface router request, json, keyring, llm router status, llm_router_status, loader, loader import attr optional, loader.import_attr_optional, normalize arch router routes, normalize headers, os, parse arch router route, pop first string, prepare generate text call, provider preflight error, re, resolve hf token, resolve openai api key, select huggingface arch route, shutil, slugify route name, strip code fences, temporary env, threading, types, types with adapter metadata, types.with_adapter_metadata, typing, typing any, typing dict, typing mapping, typing optional, typing.any, typing.dict, typing.mapping, typing.optional
- AST symbol scope: file
- Goal id: codebase/runtime/integrations-ipfs_datasets-llm
- Missing evidence: Review swallowed exception path in integrations/ipfs_datasets/llm.py:331
- Merge key: codebase/runtime/integrations-ipfs_datasets-llm
- Merge family: integrations/ipfs_datasets/llm.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 878fee469cd69e98
- Acceptance: Codebase scan filed this finding from integrations/ipfs_datasets/llm.py:331. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-128-codebase-scan-878fee469cd6.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
