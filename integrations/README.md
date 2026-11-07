# Integrations

The `integrations` package holds complaint-generator facades for accelerate, datasets, and mike. The package directory is `integrations`, and its initializer is [`integrations/__init__.py`](__init__.py). The repository module map records this package at [`docs/architecture/repository_module_map.json`](../docs/architecture/repository_module_map.json).

Submodule checkouts are at `external/`. The committed declaration is [`.gitmodules`](../.gitmodules): `external/ipfs_accelerate_py`, `external/ipfs_datasets_py`, `external/ipfs_kit_py`, and `external/mike`. Those paths are the SDK trees. Documentation work does not edit `external/`, submodule gitlinks, or dependency pins. External/ pins are not advanced by documentation work.

The empty root `ipfs_datasets_py` and `mike` directories are compatibility paths, not the SDK trees. They are not populated checkouts and they are not the packages under `integrations/`. The module map records both as empty compatibility directories.

## Interface versions

Each public facade uses schema `complaint-generator/module-interface@1`. Importing an interface records owner modules and public symbol names. That import does not import the owners, start a server, start a supervisor, update a submodule, or read a private workspace path.

| Integration | Module | Interface version | Source |
| --- | --- | --- | --- |
| accelerate | `integrations.ipfs_accelerate.interface` | `1.0.0` | [`ipfs_accelerate/interface.py`](ipfs_accelerate/interface.py) |
| datasets | `integrations.ipfs_datasets.interface` | `1.0.0` | [`ipfs_datasets/interface.py`](ipfs_datasets/interface.py) |
| mike | `integrations.mike.interface` | `1.0.0` | [`mike/interface.py`](mike/interface.py) |

The accelerate interface version is `1.0.0`. The datasets interface version is `1.0.0`. The mike interface version is `1.0.0`. `INTERFACE_VERSION` is `1.0.0` on each of those three modules.

## Accelerate owners

Package initializer: [`ipfs_accelerate/__init__.py`](ipfs_accelerate/__init__.py).

The accelerate interface names these owner modules and no others:

| Owner module | Source | Public symbols |
| --- | --- | --- |
| `integrations.ipfs_accelerate.campaign` | [`ipfs_accelerate/campaign.py`](ipfs_accelerate/campaign.py) | `CampaignArtifacts`, `DEFAULT_ARTIFACTS`, `campaign_artifacts` |
| `integrations.ipfs_accelerate.improvement_plan` | [`ipfs_accelerate/improvement_plan.py`](ipfs_accelerate/improvement_plan.py) | `validate_spec`, `load_spec`, `build_improvement_work_plan`, `generate`, `EVIDENCE_SCHEMA`, `canonical_model_policy`, `bind_sources` |

## Datasets owners

Package initializer: [`ipfs_datasets/__init__.py`](ipfs_datasets/__init__.py). Checkout classification lives in [`ipfs_datasets/loader.py`](ipfs_datasets/loader.py) and reads `.gitmodules` only. It does not advance an `external/` pin.

The datasets interface names these owner modules and no others:

| Owner module | Source | Public symbols |
| --- | --- | --- |
| `integrations.ipfs_datasets.loader` | [`ipfs_datasets/loader.py`](ipfs_datasets/loader.py) | `RepoPaths`, `ImportFailure`, `get_repo_paths`, `declared_submodule_paths`, `classify_owner_checkout`, `import_module_optional`, `import_attr_optional` |
| `integrations.ipfs_datasets.documents` | [`ipfs_datasets/documents.py`](ipfs_datasets/documents.py) | `DOCUMENTS_AVAILABLE`, `PARSER_VERSION`, `detect_document_input_format`, `parse_document`, `ingest_local_document` |

## Mike owners

Package initializer: [`mike/__init__.py`](mike/__init__.py).

The mike interface names these owner modules and no others. It does not treat the empty root `mike` directory or `external.mike` as an owner.

| Owner module | Source | Public symbols |
| --- | --- | --- |
| `integrations.mike` | [`mike/__init__.py`](mike/__init__.py) | `apply_mike_llm_router_patch`, `MIKE_LLM_PATCH_VERSION`, `load_skill`, `list_skill_ids`, `SKILLS_DIR` |
| `integrations.mike.llm_patch` | [`mike/llm_patch.py`](mike/llm_patch.py) | `MIKE_LLM_PATCH_DESCRIPTOR`, `get_router_generate_fn` |
| `integrations.mike.skills` | [`mike/skills/__init__.py`](mike/skills/__init__.py) | `load_all_skills` |

`apply_mike_llm_router_patch`, `MIKE_LLM_PATCH_VERSION`, `load_skill`, `list_skill_ids`, and `SKILLS_DIR` are also defined by the package initializer because it re-exports them. `MIKE_LLM_PATCH_DESCRIPTOR` and `get_router_generate_fn` are defined in `integrations.mike.llm_patch`. `load_all_skills` is defined in `integrations.mike.skills`.
