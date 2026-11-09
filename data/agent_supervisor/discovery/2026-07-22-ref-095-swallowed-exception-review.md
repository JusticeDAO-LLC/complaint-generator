# REF-095 Swallowed Exception Review

Date: 2026-07-22
Source finding: `document_optimization.py:43`
Evidence: `data/refactor_supervisor/discovery/2026-07-22-ref-095-codebase-scan-d5d93085783b.md`

## Decision

The flagged boundary guarded the repository-owned
`integrations.ipfs_datasets.loader.import_attr_optional` helper. That helper is
required infrastructure, not an optional provider: it already converts failures
from the optional `ipfs_datasets_py` optimizer package into structured
`ImportFailure` values. Silently replacing the helper with a function that always
returned `(None, None)` erased those diagnostics and made a broken local adapter
indistinguishable from an intentionally absent upstream optimizer.

The fallback has been removed and the loader is imported before the optional
adapter modules. Missing or broken upstream optimizer packages continue to use
the loader's normal degraded-mode contract, while a defect in the local loader
now fails import immediately with its original exception.

## Focused Validation

`tests/test_ref_095_document_optimization_imports.py` asserts that the loader is
a single top-level required import and is not wrapped in a `try` statement. This
protects the error-propagation boundary without depending on which optional
providers happen to be installed in the test environment.

Required syntax validation:

```text
python3 -m py_compile document_optimization.py
```
