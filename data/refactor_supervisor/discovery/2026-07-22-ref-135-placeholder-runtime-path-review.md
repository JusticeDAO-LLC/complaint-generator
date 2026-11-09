# REF-135 Placeholder Runtime Path Review

Date: 2026-07-22
Source finding: `lib/knowledge_graph_formats.py:82`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-135-codebase-scan-018923b8aa31.md`

## Decision

The standalone fallback exposes a registry so callers can add handlers for
formats that are not built in. A missing handler is therefore a supported
runtime validation case, not an unimplemented method. Raising
`NotImplementedError` incorrectly characterized bad or incomplete registry
configuration as placeholder code. It also assumed every registry key had a
`.value` attribute, allowing an invalid format value to mask the intended
diagnostic with `AttributeError`.

The fallback registry now raises `ValueError` for unsupported save and load
formats. The diagnostic names the requested operation and value, lists the
handlers available for that operation, and directs callers to
`register_format()`. Enum and non-enum values use the same error path. Existing
registered handlers and the optional upstream implementation are unchanged.

## Focused Validation

`tests/test_ref_135_knowledge_graph_formats_fallback.py` loads the module with
the optional `ipfs_datasets_py` import intentionally unavailable. It verifies
the save and load errors for an unregistered enum member and confirms that an
invalid non-enum value still produces the actionable validation error.

Required syntax validation:

```text
python3 -m py_compile lib/knowledge_graph_formats.py
```

Validation results:

- PASS — `python3 -m py_compile lib/knowledge_graph_formats.py`
- PASS — `python3 -m pytest tests/test_ref_135_knowledge_graph_formats_fallback.py -q`
  (3 passed)
- PASS — `python3 -m pytest tests/test_lib_cross_consumer_contracts.py -q`
  (45 passed)
