# Complaint phases

The `complaint_phases` package holds the phase pipeline, plus legal-document and deontic modules that stay outside that pipeline. The package directory is `complaint_phases`, and its initializer is [`complaint_phases/__init__.py`](__init__.py). The repository module map records this package at [`docs/architecture/repository_module_map.json`](../docs/architecture/repository_module_map.json).

## Interface

Public entry for the phase pipeline is [`complaint_phases.interface`](interface.py).

| Field | Value |
| --- | --- |
| Schema | `complaint-generator/module-interface@1` |
| Interface version | `1.0.0` |
| Module | `complaint_phases.interface` |

The interface version is `1.0.0`. `INTERFACE_VERSION` is `1.0.0`. Importing `complaint_phases.interface` records the phase-pipeline owner modules and their public symbol names. That import does not import those owners, start a server, or read a private workspace path.

The phase pipeline is distinct from the separate legal and deontic owners. New code that needs the pipeline imports `complaint_phases.interface`. It does not treat [`legal_document.py`](legal_document.py), [`legal_document_facade.py`](legal_document_facade.py), or [`deontic_logic.py`](deontic_logic.py) as owners of this interface.

## Phase pipeline owners

The interface names these owner modules and no others:

| Owner module | Source | Public symbols |
| --- | --- | --- |
| `complaint_phases.phase_manager` | [`complaint_phases/phase_manager.py`](phase_manager.py) | `ComplaintPhase`, `PhaseManager` |
| `complaint_phases.knowledge_graph` | [`complaint_phases/knowledge_graph.py`](knowledge_graph.py) | `Entity`, `Relationship`, `KnowledgeGraph`, `KnowledgeGraphBuilder` |
| `complaint_phases.intake_case_file` | [`complaint_phases/intake_case_file.py`](intake_case_file.py) | `QUESTION_DISPOSITIONS`, `build_intake_case_file`, `build_canonical_facts` |

`ComplaintPhase` and `PhaseManager` are the public phase symbols on `complaint_phases.phase_manager`. Graph symbols are `Entity`, `Relationship`, `KnowledgeGraph`, and `KnowledgeGraphBuilder` on `complaint_phases.knowledge_graph`. Intake symbols are `QUESTION_DISPOSITIONS`, `build_intake_case_file`, and `build_canonical_facts` on `complaint_phases.intake_case_file`.

This document names only those public symbols for interface version `1.0.0`. It does not add a symbol the interface does not name.

## Separate legal and deontic owners

Legal and deontic modules are separate owners from the phase pipeline. They are not entries in `OWNER_MODULES` for `complaint_phases.interface`.

| Separate owner | Source | Relationship to the phase pipeline |
| --- | --- | --- |
| Legal document | [`legal_document.py`](legal_document.py) | `complaint_phases.legal_document` owns pleading and parsed-document helpers. It is not a phase-pipeline owner. |
| Legal document facade | [`legal_document_facade.py`](legal_document_facade.py) | `complaint_phases.legal_document_facade` is the versioned legal-document facade. It is not a phase-pipeline owner. |
| Deontic logic | [`deontic_logic.py`](deontic_logic.py) | `complaint_phases.deontic_logic` owns deontic graph types. It is not a phase-pipeline owner. |

`complaint_phases.legal_graph` in [`legal_graph.py`](legal_graph.py) is package code beside the pipeline. It is not an owner of `complaint_phases.interface`.
