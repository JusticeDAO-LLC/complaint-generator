# IPFS Datasets Py Direct Import Audit

Date: 2026-03-12
Status: Production audit complete

Companion docs:

- `docs/IPFS_DATASETS_PY_BATCH1_IMPLEMENTATION_PLAN.md`
- `docs/IPFS_DATASETS_PY_CAPABILITY_MATRIX.md`
- `docs/IPFS_DATASETS_PY_INTEGRATION.md`

## Purpose

Verify whether complaint-generator production code still imports `ipfs_datasets_py` directly outside the adapter boundary under `integrations/ipfs_datasets/`.

This audit narrows Batch 1 scope by separating real production cleanup from test, benchmark, vendored-submodule, and documentation noise.

## Audit scope

The audit excluded:

- the vendored `ipfs_datasets_py/` submodule itself
- `tests/`
- top-level `test_*.py`
- benchmark and profiling scripts such as `batch_*.py` and `profile_generate_10k.py`
- `examples/`
- `tmp/`

The goal was to inspect complaint-generator production code only.

## Audit method

Production-only import scan:

```bash
grep -RInE '(from ipfs_datasets_py|import ipfs_datasets_py)' . \
  --exclude-dir=ipfs_datasets_py \
  --exclude-dir=tests \
  --exclude-dir=examples \
  --exclude-dir=tmp \
  --exclude='test_*.py' \
  --exclude='batch_*.py' \
  --exclude='profile_generate_10k.py'
```

## Finding summary

## 1. Production code import boundary is currently clean

No remaining direct `ipfs_datasets_py` imports were found in complaint-generator production Python modules outside the adapter boundary.

This means:

- the Batch 1 direct-import cleanup risk is currently lower than previously assumed
- the adapter boundary under `integrations/ipfs_datasets/` is already the effective production import seam
- Batch 1 effort should focus more on contract normalization and capability reporting than on broad production import migration

## 2. The remaining drift is documentation drift

The audit did find multiple documentation references that use stale or unvalidated upstream import paths or classes.

Examples include references to:

- `BraveSearchClient`
- `CommonCrawlSearchEngine` as a root `web_archiving` import
- `PDFProcessor`
- `GraphRAGIntegrator`
- `VectorSearch`
- older `legal_scrapers` import examples that do not match the validated adapter guidance

These are documentation problems, not current production-code integration problems.

## 3. Tests and benchmark-style scripts still use direct imports

This is expected and acceptable where the intent is:

- validating upstream optimizer or GraphRAG APIs directly
- benchmarking submodule functionality directly
- smoke testing submodule behavior in isolation from complaint-generator adapters

Those uses should not be treated as production-boundary violations.

## Documentation files with likely stale import examples

The following files were flagged during the audit output and should be treated as likely follow-up candidates for documentation cleanup:

- `docs/COMPLAINT_ANALYSIS_EXAMPLES.md`
- `docs/SEARCH_HOOKS.md`
- `docs/IPFS_DATASETS_INTEGRATION.md`
- `docs/LEGAL_HOOKS.md`
- `docs/HACC_VS_IPFS_DATASETS_QUICK.md`
- `docs/IPFS_DATASETS_PY_INTEGRATION.md`
- `docs/HACC_IPFS_HYBRID_USAGE.md`

Not every reference is necessarily wrong in intent, but these files contain examples or references that should be reconciled with the validated module paths captured in `docs/IPFS_DATASETS_PY_CAPABILITY_MATRIX.md`.

## Batch 1 implication

Slice 6 from `docs/IPFS_DATASETS_PY_BATCH1_IMPLEMENTATION_PLAN.md` should now be interpreted as:

1. confirm there are no hidden direct production imports
2. keep this audit current when new production code lands
3. prioritize documentation import cleanup over broad production-code refactoring unless new direct imports appear

In other words, Batch 1 is now primarily a contract-stabilization pass, not a production import-migration pass.

## Recommended next actions

1. Keep Slice 6 in Batch 1, but downgrade it from likely code migration to ongoing audit guardrail.
2. A focused pytest guardrail now exists at `tests/test_ipfs_adapter_import_boundary.py` to catch new direct production imports outside `integrations/ipfs_datasets/`.
3. Create a documentation cleanup slice to replace stale `ipfs_datasets_py` examples with either:
   - adapter-based examples for complaint-generator docs, or
   - validated current upstream module paths where direct upstream examples are intentional.

## Exit statement

As of this audit, complaint-generator production code appears to respect the intended `integrations/ipfs_datasets/` import boundary. The remaining cleanup surface is primarily documentation correctness and keeping future production changes from bypassing the adapter seam.