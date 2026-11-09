# REF-070 Objective Validation Repair

Date: 2026-07-22
Goal id: G1.S2
Goal title: Remove ad hoc import path behavior from production surfaces
Gap source: data/refactor_supervisor/discovery/2026-07-22-ref-070-objective-gap-514368960e0e.md
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g1-g1-s2.todo.md
Todo vector key: 80d513659b600256
Canonical task key: task/v1/ad23811d9d14aedb7013be18cb8208f23af01bb88f24e7b8d47b41d7c18ec810
Canonical task CID: baguqeeravurychm5csxnw4atxymmxaqi6i5pag5yr4sopogupna5pqmozaia
Merge key: b74aae0dd2672d61
Merge family: objective/G1.S2

## Repair Summary

The objective scan filed REF-070 because G1.S2 had implementation paths but no
durable `objective validation repair` receipt. Revalidation also found that the
nine named operator entrypoints still changed `sys.path`, so this repair closes
the implementation gap rather than recording a documentation-only result.

All named entrypoints now use normal package imports. The two HACC orchestrators
load the repository synthesis module by its qualified module name; the grounded
pipeline loads an installed HACC provider and reports an actionable error when
that external package is absent. Email entrypoints use the repository-owned
IPFS adapter loader before importing provider modules. The loader recognizes
both the standard provider checkout and nested compatibility layout without
leaking provider changes to `sys.path`.

The `scripts` operator package is included in distribution metadata separately
from production packages, so qualified script-to-script imports work in an
installed environment without widening the production adapter scan. README and
HACC regression examples use `python -m scripts.<entrypoint>` and no longer
teach operators to set `PYTHONPATH` for these workflows.

`tests/test_package_imports.py` now statically covers every named entrypoint,
the synthesis entrypoint they share, and the earlier production surfaces. A
separate assertion proves that email entrypoints initialize the adapter before
direct provider imports. Adapter coverage also exercises nested provider-layout
discovery. `docs/ARCHITECTURE.md` and `pyproject.toml` record the resulting
operator-import and graph-port boundary contracts.

G1.S2 already has two appropriately bounded implementation tasks: REF-003 owns
path-stable entrypoints and REF-004 owns optional-dependency adapter access.
This repair advances both pieces together and does not need another child goal.
Task completion remains supervisor-owned; the canonical todo and bundle shard
only receive this evidence link.

## Evidence Covered

- Missing evidence term: objective validation repair
- Path-stable entrypoints: `scripts/graphrag_email_manifest.py`,
  `scripts/import_gmail_evidence.py`, `scripts/import_local_eml_directory.py`,
  `scripts/master_case_email.py`, `scripts/process_hacc_pdfs_to_kg.py`,
  `scripts/run_gmail_duckdb_pipeline.py`,
  `scripts/run_hacc_adversarial_report.py`,
  `scripts/run_hacc_grounded_pipeline.py`, and
  `scripts/run_hacc_preset_matrix.py`
- Shared synthesis import: `scripts/synthesize_hacc_complaint.py`
- Installed operator package contract: `scripts/__init__.py` and
  `pyproject.toml`
- Repository-owned optional-dependency loading:
  `integrations/ipfs_datasets/loader.py`
- Static path-mutation and adapter-order enforcement:
  `tests/test_package_imports.py`
- Adapter-layout and degraded-mode validation:
  `tests/test_ipfs_adapter_layer.py`
- Import contract documentation: `docs/ARCHITECTURE.md` and `pyproject.toml`
- Heap evidence: `data/refactor_supervisor/refactor_objective_heap.md`
- Canonical backlog evidence: REF-070 in
  `data/refactor_supervisor/refactor_todo.md`
- Bundle evidence: REF-070 in
  `data/refactor_supervisor/objective_bundles/refactor-g1-g1-s2.todo.md`

## Validation

- PASS — `python -m pytest tests/test_package_imports.py -q` (12 passed; exit
  code 0).
- PASS — `python -m pytest tests/test_ipfs_adapter_layer.py -q` (70 passed;
  exit code 0).
- PASS — `python -m pytest tests/test_import_gmail_evidence_cli.py -q` (8
  passed; exit code 0).
- PASS — focused email entrypoint regression run (12 passed, 2 optional
  pipeline tests skipped; exit code 0).
- PASS — focused HACC entrypoint regression run (40 passed, with 2 tests that
  require parent-workspace evidence fixtures deliberately deselected; exit
  code 0).

The validation runs emitted only the existing `pytest-asyncio` deprecation
warning for the unset `asyncio_default_fixture_loop_scope` option.
