from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from .loader import ImportFailure, build_import_failure_diagnostic, import_module_optional
from .types import CapabilityStatus


CAPABILITY_SCHEMA_VERSION = "ipfs-datasets-capabilities/v1"


@dataclass(frozen=True)
class CapabilityDefinition:
    """Static metadata for one public adapter capability group."""

    name: str
    module_path: str
    adapter_module: str
    contract_family: str
    install_extra: str
    owner: str = "ipfs_datasets_py"
    bridge: str = ""
    public_adapter: str = ""
    canonical_modules: str = ""
    deprecated_upstream: str = ""


# This is the canonical adapter-group contract.  It is deliberately independent
# of import results so full, partial, and degraded environments expose the same
# ordered keys.  Groups backed only by local normalization code are omitted;
# every entry here describes an optional upstream provider boundary.
CAPABILITY_DEFINITIONS = (
    CapabilityDefinition(
        "llm_router",
        "ipfs_accelerate_py.llm_router",
        "integrations.ipfs_accelerate.routers",
        "generation",
        "api",
        owner="ipfs_accelerate_py",
        bridge="ipfs_datasets_py.llm_router",
        public_adapter="integrations.ipfs_datasets.llm",
    ),
    CapabilityDefinition(
        "embeddings_router",
        "ipfs_accelerate_py.embeddings_router",
        "integrations.ipfs_accelerate.routers",
        "retrieval",
        "api",
        owner="ipfs_accelerate_py",
        bridge="ipfs_datasets_py.embeddings_router",
        public_adapter="integrations.ipfs_datasets.vector_store",
    ),
    CapabilityDefinition(
        "multimodal_router",
        "ipfs_accelerate_py.multimodal_router",
        "integrations.ipfs_accelerate.routers",
        "generation",
        "api",
        owner="ipfs_accelerate_py",
        bridge="ipfs_datasets_py.multimodal_router",
        public_adapter="integrations.ipfs_datasets.multimodal",
    ),
    CapabilityDefinition(
        "agent_supervisor",
        "ipfs_accelerate_py.agent_supervisor",
        "integrations.ipfs_accelerate.supervisor",
        "supervision",
        "",
        owner="ipfs_accelerate_py",
    ),
    CapabilityDefinition(
        "ipfs_storage",
        "ipfs_kit_py",
        "integrations.ipfs_datasets.storage",
        "storage",
        "ipld",
        owner="ipfs_kit_py",
        bridge="ipfs_datasets_py.ipfs_backend_router",
    ),
    CapabilityDefinition(
        "web_archiving",
        "ipfs_datasets_py.web_archiving",
        "integrations.ipfs_datasets.search",
        "acquisition",
        "scraping",
    ),
    CapabilityDefinition(
        "common_crawl",
        "ipfs_datasets_py.processors.web_archiving.common_crawl_integration",
        "integrations.ipfs_datasets.search",
        "acquisition",
        "scraping",
    ),
    CapabilityDefinition(
        "documents",
        "ipfs_datasets_py.processors",
        "integrations.ipfs_datasets.documents",
        "documents",
        "file_conversion",
    ),
    CapabilityDefinition(
        "legal_scrapers",
        "ipfs_datasets_py.processors.legal_scrapers",
        "integrations.ipfs_datasets.legal",
        "legal",
        "scraping,vectors",
    ),
    CapabilityDefinition(
        "knowledge_graphs",
        "ipfs_datasets_py.knowledge_graphs",
        "integrations.ipfs_datasets.graphs",
        "graphs",
        "knowledge_graphs",
    ),
    CapabilityDefinition(
        "legal_data",
        "ipfs_datasets_py.processors.legal_data",
        "integrations.ipfs_datasets.legal_data",
        "legal",
        "scraping",
    ),
    CapabilityDefinition(
        "multimedia",
        "ipfs_datasets_py.processors.multimedia",
        "integrations.ipfs_datasets.multimedia",
        "documents",
        "file_conversion",
    ),
    CapabilityDefinition(
        "graphrag",
        "ipfs_datasets_py.optimizers.graphrag",
        "integrations.ipfs_datasets.graphrag",
        "validation",
        "knowledge_graphs,logic",
    ),
    CapabilityDefinition(
        "logic_tools",
        "ipfs_datasets_py.logic",
        "integrations.ipfs_datasets.logic",
        "validation",
        "logic",
        canonical_modules="logic.fol,logic.deontic,logic.integration,logic.external_provers,logic.TDFOL",
        deprecated_upstream="logic.tools",
    ),
    CapabilityDefinition(
        "policy_rules",
        "ipfs_datasets_py.processors.file_converter.converter",
        "integrations.ipfs_datasets.policy_rules",
        "validation",
        "file_conversion,knowledge_graphs",
    ),
    CapabilityDefinition(
        "vector_store",
        "ipfs_datasets_py.vector_stores",
        "integrations.ipfs_datasets.vector_store",
        "retrieval",
        "vectors",
    ),
    CapabilityDefinition(
        "mcp_gateway",
        "ipfs_datasets_py.mcp_server",
        "integrations.ipfs_datasets.mcp_gateway",
        "mcp",
        "api",
    ),
)

CAPABILITY_NAMES = tuple(definition.name for definition in CAPABILITY_DEFINITIONS)
# Descriptive alias for report consumers and compatibility with early callers.
CAPABILITY_GROUP_KEYS = CAPABILITY_NAMES


def _probe_capability(definition: CapabilityDefinition) -> CapabilityStatus:
    module, error = import_module_optional(definition.module_path)
    available = module is not None
    if not available and definition.name == "ipfs_storage" and definition.bridge:
        bridge_module, bridge_error = import_module_optional(definition.bridge)
        available = bridge_module is not None
        if not available and error is None:
            error = bridge_error
    if not available and error is None:
        # Optional import helpers normally return a typed error.  Synthesize one
        # if an alternate implementation returns ``(None, None)`` so degraded
        # status can never collapse back to a generic "unavailable" string.
        error = ImportFailure(
            module_name=definition.module_path,
            error_type="ModuleNotFoundError",
            message=f"No module named '{definition.module_path}'",
            missing_module_name=definition.module_path,
        )
    diagnostic = build_import_failure_diagnostic(
        None if available else error,
        module_name=definition.module_path,
        capability=definition.name,
        install_extra=definition.install_extra,
        package_name=definition.owner,
    )
    return CapabilityStatus(
        status="available" if available else "degraded",
        available=available,
        module_path=definition.module_path,
        degraded_reason=diagnostic["degraded_reason"],
        provider=definition.owner,
        details={
            "capability": definition.name,
            "adapter_module": definition.adapter_module,
            "contract_family": definition.contract_family,
            "install_extra": definition.install_extra,
            "owner": definition.owner,
            "bridge": definition.bridge,
            "public_adapter": definition.public_adapter,
            "canonical_modules": definition.canonical_modules,
            "deprecated_upstream": definition.deprecated_upstream,
            **diagnostic,
        },
    )


@lru_cache(maxsize=1)
def get_ipfs_datasets_capabilities() -> dict[str, CapabilityStatus]:
    """Return capability status for every optional IPFS datasets adapter group.

    Probes are cached because importing the provider can be expensive.  Call
    ``get_ipfs_datasets_capabilities.cache_clear()`` after changing installed
    extras in a long-running process.
    """

    return {
        definition.name: _probe_capability(definition)
        for definition in CAPABILITY_DEFINITIONS
    }


def summarize_ipfs_datasets_capabilities() -> dict[str, str]:
    """Return a compact, human-readable summary with the canonical group keys."""

    return {
        name: (
            "available"
            if status.available
            else f"degraded: {status.degraded_reason or 'optional provider unavailable'}"
        )
        for name, status in get_ipfs_datasets_capabilities().items()
    }


def summarize_ipfs_datasets_capability_report() -> dict[str, object]:
    capabilities = get_ipfs_datasets_capabilities()
    available_capabilities = sorted(
        name for name, status in capabilities.items() if status.available
    )
    degraded_capabilities = {
        name: status.degraded_reason or "optional provider unavailable"
        for name, status in capabilities.items()
        if not status.available
    }
    family_counts: dict[str, int] = {}
    for status in capabilities.values():
        family = str(status.details.get("contract_family") or "")
        if family:
            family_counts[family] = family_counts.get(family, 0) + 1

    available = not degraded_capabilities
    degraded_reason = None
    if degraded_capabilities:
        degraded_reason = (
            f"{len(degraded_capabilities)} optional capability group(s) are degraded: "
            f"{', '.join(sorted(degraded_capabilities))}. "
            "See degraded_capabilities for remediation."
        )

    return {
        "schema_version": CAPABILITY_SCHEMA_VERSION,
        "status": "available" if available else "degraded",
        "available": available,
        "degraded_reason": degraded_reason,
        "available_count": len(available_capabilities),
        "degraded_count": len(degraded_capabilities),
        "capability_keys": list(CAPABILITY_NAMES),
        "available_capabilities": available_capabilities,
        "degraded_capabilities": degraded_capabilities,
        "family_counts": family_counts,
        "capabilities": {
            name: status.as_dict() for name, status in capabilities.items()
        },
    }


def summarize_ipfs_datasets_startup_payload() -> dict[str, object]:
    capability_report = summarize_ipfs_datasets_capability_report()
    return {
        "schema_version": CAPABILITY_SCHEMA_VERSION,
        "status": capability_report["status"],
        "available": capability_report["available"],
        "degraded_reason": capability_report["degraded_reason"],
        "capability_report": capability_report,
        "capabilities": capability_report["capabilities"],
    }


# Compact owner table for the APIs named by the mediator-grounding spec.
# Training and definition rows are conditional engineering records. They are
# not semantic authority and they are not proof.
OWNER_INVENTORY_SCHEMA_VERSION = "complaint-mediator-grounding-owner-inventory/v1"
DECLARED_OWNER_PINS = {
    "ipfs_accelerate_py": "947f873e407efd9b12c551a5e69a9b62819b9c4e",
    "ipfs_datasets_py": "b857f28462bfbb9cbf02232a79cdefcaa1ef1bc7",
    "ipfs_kit_py": "0007f735b90215fa611f39aa558eb512a493b8af",
}
_OWNER_CANONICAL_FILES = {
    "ipfs_accelerate_py": ("external/ipfs_accelerate_py", "ipfs_accelerate_py/__init__.py"),
    "ipfs_datasets_py": ("external/ipfs_datasets_py", "ipfs_datasets_py/__init__.py"),
    "ipfs_kit_py": ("external/ipfs_kit_py", "ipfs_kit_py/__init__.py"),
}
_ENABLED_KG_PATH = "KnowledgeGraphExtractor.extract_knowledge_graph"
_ENHANCED_KG_PATH = "KnowledgeGraphExtractor.extract_enhanced_knowledge_graph"
_KG_PROBE_TEXT = "Ada met Bob."
_PRIVATE_PROBE_PLAINTEXT = b"synthetic-mgnd-02-private"
_PRIVATE_PROBE_KEY = bytes(range(32))

# module, symbols, owner, authority_role, canonical file relative to that owner
# or to the repository when owner is "first_party".
_API_TABLE = (
    ("ipfs_datasets_py.knowledge_graphs.extraction.extractor", ("KnowledgeGraphExtractor", "KnowledgeGraphExtractor.extract_knowledge_graph"), "ipfs_datasets_py", "candidate_evidence", "ipfs_datasets_py/knowledge_graphs/extraction/extractor.py"),
    ("ipfs_datasets_py.knowledge_graphs", ("Client", "GraphTarget"), "ipfs_datasets_py", "candidate_evidence", "ipfs_datasets_py/knowledge_graphs/__init__.py"),
    ("ipfs_datasets_py.processors.legal_scrapers.legal_dataset_api", ("search_state_law_corpus_from_parameters", "search_us_code_corpus_from_parameters", "search_federal_register_corpus_from_parameters", "search_court_rules_corpus_from_parameters"), "ipfs_datasets_py", "candidate_acquisition", "ipfs_datasets_py/processors/legal_scrapers/legal_dataset_api.py"),
    ("integrations.ipfs_datasets.logic", ("compile_canonical_legal_ir", "generate_bound_legal_ir_proof_obligations", "route_bound_legal_ir_proof", "proof_cache_identity", "replay_satisfied_element_proof"), "first_party", "proof_adapter", "integrations/ipfs_datasets/logic.py"),
    ("ipfs_datasets_py.logic.autoformal.legal_source_sampling_review_context", ("prepare", "validate", "record_response", "validate_response", "summarize"), "ipfs_datasets_py", "conditional_engineering", "ipfs_datasets_py/logic/autoformal/legal_source_sampling_review_context.py"),
    ("ipfs_datasets_py.logic.autoformal.legal_source_sampling_context_definition_binding_v2", ("prepare", "validate"), "ipfs_datasets_py", "conditional_engineering", "ipfs_datasets_py/logic/autoformal/legal_source_sampling_context_definition_binding_v2.py"),
    ("ipfs_datasets_py.logic.autoformal.legal_source_sampling_context_definition_review_v2", ("prepare", "validate"), "ipfs_datasets_py", "conditional_engineering", "ipfs_datasets_py/logic/autoformal/legal_source_sampling_context_definition_review_v2.py"),
    ("ipfs_datasets_py.logic.autoformal.legal_norm_definition_evidence_v1", ("prepare_norm_definition_evidence_v1", "validate_norm_definition_evidence_v1"), "ipfs_datasets_py", "conditional_engineering", "ipfs_datasets_py/logic/autoformal/legal_norm_definition_evidence_v1.py"),
    ("ipfs_datasets_py.logic.autoformal.legal_norm_scope_correspondence_v1", ("prepare_norm_scope_correspondence_v1", "validate_norm_scope_correspondence_v1"), "ipfs_datasets_py", "conditional_engineering", "ipfs_datasets_py/logic/autoformal/legal_norm_scope_correspondence_v1.py"),
    ("ipfs_datasets_py.logic.autoformal.legal_norm_interpretation_review_v1", ("prepare_norm_review_evidence_v1", "build_norm_review_subject_v1", "assess_norm_reviews_v1", "validate_norm_review_assessment_v1"), "ipfs_datasets_py", "conditional_engineering", "ipfs_datasets_py/logic/autoformal/legal_norm_interpretation_review_v1.py"),
    ("ipfs_datasets_py.logic.autoformal.legal_bound_variable_definition_v1", ("prepare_bound_variable_definition_v1", "validate_bound_variable_definition_v1"), "ipfs_datasets_py", "conditional_engineering", "ipfs_datasets_py/logic/autoformal/legal_bound_variable_definition_v1.py"),
    ("ipfs_datasets_py.logic.formalization.autoencoder.legal_compact_content_persistent_v1", ("load_compact_content_persistent_v1", "score_compact_content_persistent_v1"), "ipfs_datasets_py", "conditional_engineering", "ipfs_datasets_py/logic/formalization/autoencoder/legal_compact_content_persistent_v1.py"),
    ("ipfs_datasets_py.logic.formalization.autoencoder.legal_compact_content_predicate_training_v1", ("inspect", "checkpoint_sha256"), "ipfs_datasets_py", "conditional_engineering", "ipfs_datasets_py/logic/formalization/autoencoder/legal_compact_content_predicate_training_v1.py"),
    ("integrations.ipfs_datasets.storage", ("store_automatic_private_artifact", "store_private_artifact", "retrieve_private_artifact", "publish_encrypted_replicas", "reconcile_encrypted_replicas", "restore_encrypted_replicas", "restore_encrypted_workspace"), "first_party", "private_storage", "integrations/ipfs_datasets/storage.py"),
)


def _flag_enabled(name: str) -> bool:
    import os

    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return path.as_posix()


def _typed_call_failure(exc: BaseException) -> dict[str, object]:
    return {
        "called": True,
        "status": "unavailable",
        "error_type": type(exc).__name__,
        "available": False,
    }


def record_sdk_owner_identities() -> list[dict[str, object]]:
    """Record A/Data/Kit pins, canonical package paths, and checkout kind."""

    from .loader import (
        classify_owner_checkout,
        declared_submodule_paths,
        get_repo_paths,
        observe_checked_out_commit,
    )

    paths = get_repo_paths()
    declared = declared_submodule_paths(paths.repo_root)
    records: list[dict[str, object]] = []
    for name, (relative_root, canonical_relative) in _OWNER_CANONICAL_FILES.items():
        owner_path = paths.repo_root / relative_root
        classification = classify_owner_checkout(
            owner_path,
            canonical_relative=canonical_relative,
            declared_submodule=relative_root in declared,
        )
        observed = observe_checked_out_commit(owner_path)
        records.append({
            "name": name,
            "declared_pin": DECLARED_OWNER_PINS[name],
            "relative_path": relative_root,
            "canonical_source_path": f"{relative_root}/{canonical_relative}",
            "checkout_kind": classification["checkout_kind"],
            "populated": classification["populated"],
            "declared_submodule": classification["declared_submodule"],
            "checked_out_commit": observed["commit"],
            "checked_out_commit_status": observed["status"],
            "checked_out_commit_error_type": observed["error_type"],
            "committed_gitlink_observed": False,
            "committed_gitlink": "",
            "pin_is_observed_head": observed["commit"] == DECLARED_OWNER_PINS[name] and observed["status"] == "available",
        })
    return records


def record_named_api_paths() -> list[dict[str, object]]:
    """Resolve canonical source paths for the specification API table.

    Missing optional files stay typed records. This does not walk source trees
    or install the missing module.
    """

    from .loader import get_repo_paths

    root = get_repo_paths().repo_root
    rows: list[dict[str, object]] = []
    for module, symbols, owner, authority_role, relative_file in _API_TABLE:
        if owner == "first_party":
            source = root / relative_file
            source_path = relative_file
        else:
            owner_root = root / _OWNER_CANONICAL_FILES[owner][0]
            source = owner_root / relative_file
            source_path = f"{_OWNER_CANONICAL_FILES[owner][0]}/{relative_file}"
        try:
            present = source.is_file()
        except OSError:
            present = False
        conditional = authority_role == "conditional_engineering"
        rows.append({
            "module": module,
            "symbols": list(symbols),
            "owner": owner,
            "authority_role": authority_role,
            "semantic_authority": False,
            "proof_authority": False,
            "conditional_engineering": conditional,
            "canonical_source_path": source_path,
            "source_present": present,
            "status": "present" if present else "unavailable",
            "error_type": "" if present else "FileNotFoundError",
        })
    return rows


def record_enhanced_feature_flags() -> dict[str, object]:
    """Record enhanced flags and the path this probe actually enables.

    Nothing in the process environment is changed. Wikipedia enrichment,
    model setup, and a global enable-all switch stay off.
    """

    kit_enabled = _flag_enabled("COMPLAINT_GENERATOR_ENABLE_IPFS_KIT")
    state_stream_enabled = _flag_enabled("COMPLAINT_ENABLE_IPFS_STATE_LAWS_STREAM")
    return {
        "global_enable_all": False,
        "environment_mutated": False,
        "wikipedia_enrichment_enabled": False,
        "model_setup_enabled": False,
        "scraping_enabled": False,
        "enhanced_path": _ENHANCED_KG_PATH,
        "enhanced_path_enabled": False,
        "actually_enabled_path": _ENABLED_KG_PATH,
        "extractor_options": {
            "use_spacy": False,
            "use_transformers": False,
            "use_tracer": False,
            "use_srl": False,
        },
        "COMPLAINT_GENERATOR_ENABLE_IPFS_KIT": kit_enabled,
        "COMPLAINT_ENABLE_IPFS_STATE_LAWS_STREAM": state_stream_enabled,
        "ipfs_kit_explicitly_enabled": kit_enabled,
    }


class _SyntheticPrivateBackend:
    """In-memory ciphertext backend for the private-storage seam probe."""

    measurement_label = "synthetic-mgnd-02"

    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}
        self.seen: list[bytes] = []

    def add_bytes(self, data: bytes, pin: bool = True) -> dict[str, object]:
        del pin
        blob = bytes(data)
        self.seen.append(blob)
        cid = "bafysyntheticmgnd02"
        self.blobs[cid] = blob
        return {"success": True, "cid": cid, "pinned": False}

    def cat(self, cid: str) -> bytes:
        if cid not in self.blobs:
            raise FileNotFoundError(cid)
        return self.blobs[cid]

    def pin(self, cid: str) -> dict[str, object]:
        return {"success": True, "cid": cid, "pinned": True}


def probe_selected_owner_seams() -> dict[str, object]:
    """Invoke the KG, legal, logic, and private-storage seams once.

    Legal search is called without a query vector so it returns a typed
    parameter error before corpus setup. No install, scrape, or network
    call is requested by these probes.
    """

    return {
        "knowledge_graph": _probe_knowledge_graph(),
        "legal": _probe_legal_search(),
        "logic": _probe_logic_identity(),
        "private_storage": _probe_private_storage(),
    }


def _probe_knowledge_graph() -> dict[str, object]:
    from .loader import import_attr_optional

    extractor_type, error = import_attr_optional(
        "ipfs_datasets_py.knowledge_graphs.extraction.extractor",
        "KnowledgeGraphExtractor",
    )
    if extractor_type is None:
        return {
            "called": False,
            "status": "unavailable",
            "available": False,
            "error_type": getattr(error, "error_type", "ModuleNotFoundError"),
            "method": _ENABLED_KG_PATH,
            "enhanced_called": False,
            "wikipedia_enrichment_enabled": False,
            "entity_count": 0,
        }
    try:
        extractor = extractor_type(
            use_spacy=False,
            use_transformers=False,
            use_tracer=False,
            use_srl=False,
        )
        graph = extractor.extract_knowledge_graph(_KG_PROBE_TEXT, 0.1, 0.1)
        entities = getattr(graph, "entities", {}) or {}
        enhanced_called = bool(getattr(extractor, "use_tracer", True))
        return {
            "called": True,
            "status": "available",
            "available": True,
            "error_type": "",
            "method": _ENABLED_KG_PATH,
            "enhanced_called": enhanced_called,
            "wikipedia_enrichment_enabled": extractor.tracer is not None,
            "entity_count": len(entities),
            "use_spacy": bool(extractor.use_spacy),
            "use_transformers": bool(extractor.use_transformers),
        }
    except Exception as exc:  # optional extractor dependency or rule failure
        payload = _typed_call_failure(exc)
        payload.update({
            "method": _ENABLED_KG_PATH,
            "enhanced_called": False,
            "wikipedia_enrichment_enabled": False,
            "entity_count": 0,
        })
        return payload


def _probe_legal_search() -> dict[str, object]:
    import asyncio

    from .loader import import_attr_optional

    search, error = import_attr_optional(
        "ipfs_datasets_py.processors.legal_scrapers.legal_dataset_api",
        "search_us_code_corpus_from_parameters",
    )
    if search is None:
        return {
            "called": False,
            "status": "unavailable",
            "available": False,
            "error_type": getattr(error, "error_type", "ModuleNotFoundError"),
            "symbol": "search_us_code_corpus_from_parameters",
            "network_requested": False,
            "scraping_requested": False,
        }
    try:
        result = asyncio.run(search({}))
    except Exception as exc:
        payload = _typed_call_failure(exc)
        payload.update({
            "symbol": "search_us_code_corpus_from_parameters",
            "network_requested": False,
            "scraping_requested": False,
        })
        return payload
    if not isinstance(result, dict):
        return {
            "called": True,
            "status": "unavailable",
            "available": False,
            "error_type": "UnexpectedResult",
            "symbol": "search_us_code_corpus_from_parameters",
            "network_requested": False,
            "scraping_requested": False,
        }
    error_text = str(result.get("error") or "")
    return {
        "called": True,
        "status": str(result.get("status") or "unavailable"),
        "available": result.get("status") == "available",
        "error_type": "ParameterError" if error_text else "",
        "error": error_text,
        "operation": str(result.get("operation") or ""),
        "symbol": "search_us_code_corpus_from_parameters",
        "network_requested": False,
        "scraping_requested": False,
        "early_parameter_refusal": error_text == "query_vector is required",
    }


def _probe_logic_identity() -> dict[str, object]:
    try:
        from .logic import proof_cache_identity

        identity = proof_cache_identity(
            claim_id="synthetic-claim",
            element_id="synthetic-element",
            factual_revisions=({"id": "rev-1"},),
            legal_source={"source_id": "synthetic-source", "source_version": "v0", "rules": ({"id": "rule-1", "version": "v1"},)},
        )
    except Exception as exc:
        payload = _typed_call_failure(exc)
        payload.update({"symbol": "proof_cache_identity", "proof_authority": False, "satisfied": False})
        return payload
    cache_identity = str(identity.get("cache_identity") or "")
    return {
        "called": True,
        "status": "available" if cache_identity else "unavailable",
        "available": bool(cache_identity),
        "error_type": "" if cache_identity else "MissingCacheIdentity",
        "symbol": "proof_cache_identity",
        "schema_version": str(identity.get("schema_version") or ""),
        "cache_identity_present": bool(cache_identity),
        "satisfied": False,
        "proof_authority": False,
    }


def _probe_private_storage() -> dict[str, object]:
    try:
        from applications.complaint_workspace import WorkspaceAccess

        from .storage import store_private_artifact

        backend = _SyntheticPrivateBackend()
        receipt = store_private_artifact(
            _PRIVATE_PROBE_PLAINTEXT,
            access=WorkspaceAccess.authenticated("tenant-mgnd02", case_id="case-mgnd02"),
            tenant_id="tenant-mgnd02",
            case_id="case-mgnd02",
            artifact_kind="intake-note",
            revision="rev-mgnd02",
            key=_PRIVATE_PROBE_KEY,
            key_id="case-key-mgnd02",
            backend=backend,
            pin_content=True,
        )
    except Exception as exc:
        payload = _typed_call_failure(exc)
        payload.update({
            "symbol": "store_private_artifact",
            "plaintext_observed": False,
            "kit_enabled_by_probe": False,
        })
        return payload
    plaintext_observed = any(_PRIVATE_PROBE_PLAINTEXT in blob for blob in backend.seen)
    return {
        "called": True,
        "status": str(receipt.get("status") or ("available" if receipt.get("verified") else "unavailable")),
        "available": bool(receipt.get("verified")),
        "error_type": "",
        "symbol": "store_private_artifact",
        "verified": bool(receipt.get("verified")),
        "stored_local": bool(receipt.get("stored_local")),
        "plaintext_observed": plaintext_observed,
        "kit_enabled_by_probe": False,
        "network_durable": False,
    }


def probe_training_definition_authority() -> dict[str, object]:
    """Call the training checkpoint hash only. Do not train, restore, or score law.

    Authority flags on the training owner stay false. A digest is engineering
    identity, not semantic review and not proof.
    """

    from .loader import import_module_optional

    module_name = "ipfs_datasets_py.logic.formalization.autoencoder.legal_compact_content_predicate_training_v1"
    module, error = import_module_optional(module_name)
    base = {
        "module": module_name,
        "authority_role": "conditional_engineering",
        "semantic_authority": False,
        "proof_authority": False,
        "governing_law": False,
        "training_executed": False,
        "inspect_called": False,
        "model_setup": False,
    }
    if module is None:
        base.update({
            "called": False,
            "status": "unavailable",
            "available": False,
            "error_type": getattr(error, "error_type", "ModuleNotFoundError"),
        })
        return base
    authority = dict(getattr(module, "AUTHORITY", {}) or {})
    try:
        digest = module.checkpoint_sha256({"probe": "synthetic-mgnd-02"})
    except Exception as exc:
        base.update(_typed_call_failure(exc))
        base["authority_all_false"] = bool(authority) and all(value is False for value in authority.values())
        base["symbol"] = "checkpoint_sha256"
        return base
    base.update({
        "called": True,
        "status": "available" if isinstance(digest, str) and len(digest) == 64 else "unavailable",
        "available": isinstance(digest, str) and len(digest) == 64,
        "error_type": "",
        "symbol": "checkpoint_sha256",
        "checkpoint_sha256_present": isinstance(digest, str) and len(digest) == 64,
        "authority_all_false": bool(authority) and all(value is False for value in authority.values()),
        "authority_flag_count": len(authority),
    })
    return base


def build_owner_inventory() -> dict[str, object]:
    """Build the owner inventory from the current checkout and bounded probes."""

    apis = record_named_api_paths()
    seams = probe_selected_owner_seams()
    training = probe_training_definition_authority()
    return {
        "schema_version": OWNER_INVENTORY_SCHEMA_VERSION,
        "task_id": "CIMP-MGND-02",
        "owners": record_sdk_owner_identities(),
        "apis": apis,
        "feature_flags": record_enhanced_feature_flags(),
        "seams": seams,
        "training_and_definition": training,
        "api_count": len(apis),
        "conditional_engineering_count": sum(1 for row in apis if row["conditional_engineering"]),
    }
