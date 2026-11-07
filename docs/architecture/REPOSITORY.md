# Repository operator guide

This file is the current architecture guide for module boundaries in complaint-generator. The inventory it describes is [`repository_module_map.json`](repository_module_map.json). The root overview is [`README.md`](../../README.md).

## Package map

A top-level Python package is a directory directly under the repository root that contains `__init__.py`. Unreadable top-level directories are omitted. The package map records those packages, root scripts, compatibility directories, and duplicate owners. Source files were not moved or rewritten to produce the map.

| Package | Path |
| --- | --- |
| `adversarial_harness` | [`adversarial_harness`](../../adversarial_harness/__init__.py) |
| `applications` | [`applications`](../../applications/__init__.py) |
| `backends` | [`backends`](../../backends/__init__.py) |
| `complaint_analysis` | [`complaint_analysis`](../../complaint_analysis/__init__.py) |
| `complaint_generator` | [`complaint_generator`](../../complaint_generator/__init__.py) |
| `complaint_phases` | [`complaint_phases`](../../complaint_phases/__init__.py) |
| `integrations` | [`integrations`](../../integrations/__init__.py) |
| `lib` | [`lib`](../../lib/__init__.py) |
| `mediator` | [`mediator`](../../mediator/__init__.py) |
| `scripts` | [`scripts`](../../scripts/__init__.py) |
| `static` | [`static`](../../static/__init__.py) |
| `templates` | [`templates`](../../templates/__init__.py) |
| `tests` | [`tests`](../../tests/__init__.py) |

The root directories `ipfs_datasets_py` and `mike` are empty compatibility directories. They are not `external/` submodule checkouts, and they are not the packages under `integrations/`.

Public entry for new code is a versioned interface, not a giant implementation module:

| Interface module | Source |
| --- | --- |
| `applications.interface` | [`applications/interface.py`](../../applications/interface.py) |
| `mediator.interface` | [`mediator/interface.py`](../../mediator/interface.py) |
| `complaint_phases.interface` | [`complaint_phases/interface.py`](../../complaint_phases/interface.py) |
| `complaint_generator.interface` | [`complaint_generator/interface.py`](../../complaint_generator/interface.py) |
| `lib.interface` | [`lib/interface.py`](../../lib/interface.py) |
| `integrations.ipfs_accelerate.interface` | [`integrations/ipfs_accelerate/interface.py`](../../integrations/ipfs_accelerate/interface.py) |
| `integrations.ipfs_datasets.interface` | [`integrations/ipfs_datasets/interface.py`](../../integrations/ipfs_datasets/interface.py) |
| `integrations.mike.interface` | [`integrations/mike/interface.py`](../../integrations/mike/interface.py) |

## Interface version

Published interfaces use schema `complaint-generator/module-interface@1`. The interface version is `1.0.0`. `INTERFACE_SCHEMA` is `complaint-generator/module-interface@1`. `INTERFACE_VERSION` is `1.0.0`.

The contract is [`module_interface_schema.json`](module_interface_schema.json). Required fields are schema, module, version, owner_modules, and public_symbols. Version is a major.minor.patch string. An empty public surface is accepted only when `STATUS` is `facade-only`. Importing an interface records owner modules and symbol names. That import does not start a server or read a private workspace path. Owner modules are parsed, not executed, by the checker.

## Import ratchet

The import ratchet blocks new direct imports of unpublished owner modules. A bypass is an import of one of these modules from a file outside that module's owner package:

- `mediator.mediator` (owner package `mediator`)
- `applications.complaint_workspace` (owner package `applications`)
- `complaint_phases.denoiser` (owner package `complaint_phases`)
- `document_pipeline` (owner file `document_pipeline.py`)

[`import_boundary_baseline.json`](import_boundary_baseline.json) records each current bypass as a file path plus imported module (`complaint-generator/import-boundary-baseline@1`). Existing baseline entries stay allowed, including the large owner modules. A Python file that adds a bypass the baseline does not list fails the ratchet. Imports of a published package interface are not bypasses. The checker does not rewrite those imports.

## Submodule pin policy

Populated SDK checkouts are the `external/` paths declared in [`.gitmodules`](../../.gitmodules):

- `external/ipfs_accelerate_py`
- `external/ipfs_datasets_py`
- `external/ipfs_kit_py`
- `external/mike`

The submodule pin policy is: use those pinned checkouts. Do not edit `external/`, submodule gitlinks, or dependency pins. Do not run `git submodule update`, and do not initialize nested submodules. Do not float pins, recursively initialize submodules, or clone CommonCrawl. Documentation does not advance those pins. This reorganization does not change the committed gitlinks.

## Files new work must not edit

New work edits only the targets declared for that task. It must not edit these implementation bodies:

- [`applications/complaint_workspace.py`](../../applications/complaint_workspace.py)
- [`mediator/mediator.py`](../../mediator/mediator.py)
- [`mediator/claim_support_hooks.py`](../../mediator/claim_support_hooks.py)
- [`complaint_phases/denoiser.py`](../../complaint_phases/denoiser.py)
- [`document_pipeline.py`](../../document_pipeline.py)

New work must not edit `external/`, submodule gitlinks, or dependency pins. It must not edit these operator-protected repository files:

- [`docs/task_boards/complaint_repository_reorganization_spec.json`](../task_boards/complaint_repository_reorganization_spec.json)
- [`docs/task_boards/complaint_repository_reorganization_formal_work_plan.json`](../task_boards/complaint_repository_reorganization_formal_work_plan.json)
- [`docs/task_boards/complaint_repository_reorganization_task_board.md`](../task_boards/complaint_repository_reorganization_task_board.md)

Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns. Quarantine warning: both retained quarantines stay untouched. Do not release, rewrite, or delete a quarantine record from this reorganization.

The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them. `origin/main` and `origin/master` already contain the published UX work, and this reorganization does not reopen those boards.

## Parallel work rule

Parallel work rule: tasks may edit only their declared targets. Tasks with satisfied dependencies and disjoint targets may run together. A task does not rewrite another task's outputs, and it does not mark backlog metadata complete unless that task explicitly requires it.

## Operator checks

From the repository root, check one interface module:

```
python scripts/check_module_interface.py <module_name>
```

Example:

```
python scripts/check_module_interface.py mediator.interface
```

The checker is [`scripts/check_module_interface.py`](../../scripts/check_module_interface.py). It reads [`module_interface_schema.json`](module_interface_schema.json), parses the requested module, and exits nonzero with a specific reason when the contract fails. A server-starting import is rejected from the syntax tree before the interface module is executed.

From the repository root, run the import ratchet:

```
python scripts/check_import_boundaries.py
```

Optional root and baseline:

```
python scripts/check_import_boundaries.py --root ROOT --baseline PATH
```

The checker is [`scripts/check_import_boundaries.py`](../../scripts/check_import_boundaries.py). The default baseline is [`import_boundary_baseline.json`](import_boundary_baseline.json). It exits `0` and prints `import boundary check ok` when every bypass is already listed. It exits `1` when a Python file adds an unlisted bypass. It exits `2` when the baseline or the tree cannot be read.

These commands are read-only. They do not start a supervisor, server, or browser, and they do not write campaign state.
