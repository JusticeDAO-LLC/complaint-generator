# Complaint Generator

Remote: [endomorphosis/complaint-generator](https://github.com/endomorphosis/complaint-generator)

This repository prepares legal complaints through question-driven intake, evidence gathering, and formal complaint generation. `complaint_phases` implements that preparation as three phases named in its package initializer: initial intake and denoising (knowledge and dependency graphs, and questions), evidence gathering, and neurosymbolic representation that matches against law graphs and generates a formal complaint. The primary intake command is `python -m complaint_generator.cli chat --user-id USER_ID`.

Workflow status for this repository is not the JusticeDAO-LLC Actions badges. Those badge URLs are not this checkout's status.

The module inventory is [`docs/architecture/repository_module_map.json`](docs/architecture/repository_module_map.json). Package notes live next to each package. This file does not link to root session or batch reports.

## Current packages

A current package is a top-level directory that contains `__init__.py`, as recorded by the module map:

| Package | Role in this checkout |
| --- | --- |
| `adversarial_harness` | Adversarial complainant, critic, and optimizer harness |
| `applications` | HTTP, case-route, and process-launch surface |
| `backends` | Model backend adapters |
| `complaint_analysis` | Complaint-type analysis, keywords, and decision trees |
| `complaint_generator` | Versioned facade for workspace services, the package CLI, and the MCP tool surface |
| `complaint_phases` | Phase pipeline, intake case file, and separate legal-document and deontic modules |
| `integrations` | Facades for accelerate, datasets, and mike |
| `lib` | Shared logging, formal logic, and document helpers |
| `mediator` | Orchestration between the application surface and complaint workflows |
| `scripts` | Operator and validation scripts |
| `static` | Static assets package |
| `templates` | HTML templates package |
| `tests` | Pytest package |

## Layout

### Intake

Intake commands enter through `complaint_generator`. Public entry for new code is `complaint_generator.interface`. The workspace Typer application is re-exported by `complaint_generator.cli` from `applications.complaint_cli`. Session controls and privacy mode are arguments of that CLI (`chat`, `--privacy-mode`), not a separate product surface.

Phase intake records live in `complaint_phases.intake_case_file` and `complaint_phases.intake_claim_registry`. Those modules are named by `complaint_phases`. New code that needs the phase pipeline imports `complaint_phases.interface`.

### Mediator

`mediator` coordinates complaint processing workflows. Public entry for new code is `mediator.interface`. Owner modules recorded by that interface are `mediator.workflow_service`, `mediator.hook_runtime`, and `mediator.state`. Package notes are in [`mediator/readme.md`](mediator/readme.md).

### Phases

`complaint_phases` holds the phase pipeline. Public entry for new code is `complaint_phases.interface`. Owner modules recorded by that interface are `complaint_phases.phase_manager`, `complaint_phases.knowledge_graph`, and `complaint_phases.intake_case_file`. `complaint_phases.legal_document`, `complaint_phases.legal_document_facade`, and `complaint_phases.deontic_logic` are separate from that pipeline. Package notes are in [`complaint_phases/README.md`](complaint_phases/README.md).

### Applications

`applications` is the HTTP, case-route, and process-launch surface. Public entry for new code is `applications.interface`. Owner modules recorded by that interface are `applications.server`, `applications.case_routes`, and `applications.launcher`. Package notes are in [`applications/README.md`](applications/README.md).

### Integrations

`integrations` holds the accelerate, datasets, and mike facades. Public entries are `integrations.ipfs_accelerate.interface`, `integrations.ipfs_datasets.interface`, and `integrations.mike.interface`. Package notes are in [`integrations/README.md`](integrations/README.md).

Other current packages:

- `adversarial_harness` — see [`adversarial_harness/README.md`](adversarial_harness/README.md)
- `backends` — backend adapters under `backends/`
- `complaint_analysis` — see [`complaint_analysis/README.md`](complaint_analysis/README.md)
- `lib` — public entry `lib.interface` (`lib.log`, `lib.formal_logic`, `lib.knowledge_graph_export`)
- `scripts`, `static`, `templates`, and `tests` — the script, asset, template, and test packages recorded by the module map

## External submodule checkouts

Populated SDK checkouts are the `external/` paths declared in [`.gitmodules`](.gitmodules):

- `external/ipfs_accelerate_py`
- `external/ipfs_datasets_py`
- `external/ipfs_kit_py`
- `external/mike`

The root directories `ipfs_datasets_py` and `mike` are empty compatibility directories. They are not those external submodule checkouts, and they are not the packages under `integrations/`.

Clone this repository from `https://github.com/endomorphosis/complaint-generator.git` (`endomorphosis/complaint-generator`). Initializing the pinned external checkouts is `git submodule update --init external/ipfs_accelerate_py external/ipfs_datasets_py external/ipfs_kit_py external/mike`. Documentation does not advance those pins.

## Versioned package interfaces

Each public facade defines `INTERFACE_SCHEMA = "complaint-generator/module-interface@1"` and `INTERFACE_VERSION = "1.0.0"`. Importing an interface records owner modules and public symbol names. That import does not import the owner implementations, start a server, or read a private workspace path.

| Interface module | Package |
| --- | --- |
| `applications.interface` | `applications` |
| `mediator.interface` | `mediator` |
| `complaint_phases.interface` | `complaint_phases` |
| `complaint_generator.interface` | `complaint_generator` |
| `lib.interface` | `lib` |
| `integrations.ipfs_accelerate.interface` | `integrations` |
| `integrations.ipfs_datasets.interface` | `integrations` |
| `integrations.mike.interface` | `integrations` |

New code imports these versioned interfaces. It does not import giant implementation modules. The module map's largest Python modules include `applications/complaint_workspace.py`, `mediator/mediator.py`, `document_pipeline.py`, `mediator/claim_support_hooks.py`, and `complaint_phases/denoiser.py`. Those files remain implementation bodies. Do not import `applications.complaint_workspace`, `mediator.mediator`, `document_pipeline`, `mediator.claim_support_hooks`, or `complaint_phases.denoiser` from new code.

## Related package documents

- [`complaint_generator/README.md`](complaint_generator/README.md)
- [`applications/README.md`](applications/README.md)
- [`mediator/readme.md`](mediator/readme.md)
- [`complaint_phases/README.md`](complaint_phases/README.md)
- [`integrations/README.md`](integrations/README.md)
- [`complaint_analysis/README.md`](complaint_analysis/README.md)
- [`adversarial_harness/README.md`](adversarial_harness/README.md)
- [`docs/architecture/repository_module_map.json`](docs/architecture/repository_module_map.json)
