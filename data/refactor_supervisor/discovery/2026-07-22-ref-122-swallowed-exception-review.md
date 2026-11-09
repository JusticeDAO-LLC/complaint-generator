# REF-122 Swallowed Exception Review

Date: 2026-07-22
Source finding: `integrations/ipfs_datasets/legal.py:112`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-122-codebase-scan-a99172acf7bb.md`

## Decision

The flagged handler is the final query-embedding attempt before state-law and
administrative-rule searches fall back to Hugging Face parquet text search and,
when enabled, live scraping. Embedding providers cross optional local, CLI, and
remote-service boundaries and do not expose a stable shared exception hierarchy,
so an ordinary provider failure must not prevent those independent legal-search
backends from returning results.

The fallback remains intentionally broad over ordinary `Exception` failures at
that adapter boundary, but it is no longer silent. It logs a warning with full
exception context and records a serialization-safe `embedding` diagnostic with
the failed stage, provider, model, exception type, and message. Both state legal
search entry points pass their existing search diagnostic into the embedding
helper, allowing callers to inspect the reason semantic corpus search was
skipped through `get_last_legal_search_diagnostic`. Exceptions outside the
ordinary runtime hierarchy, including `KeyboardInterrupt` and `SystemExit`, are
not intercepted.

## Focused Validation

`test_search_state_laws_reports_router_embedding_failure` injects a router
provider failure through the public state-law search and verifies that text-search
fallback remains available, the failure is logged with its original exception,
and `get_last_legal_search_diagnostic` retains the provider failure details.

Required syntax validation:

```text
python3 -m py_compile integrations/ipfs_datasets/legal.py
```
