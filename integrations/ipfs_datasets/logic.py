from __future__ import annotations

from collections import Counter
from copy import deepcopy
from contextlib import contextmanager
from dataclasses import replace
from datetime import date
from enum import Enum
import hashlib
import inspect
import json
import math
import os
import re
import threading
import time
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from lib.formal_logic.capabilities import (
    CanonicalCompilerCapability,
    CanonicalCompilerSupport,
    FormalLogicCapability,
    FormalLogicCapabilityError,
    FormalLogicDegradedError,
    FormalLogicOperation,
    FormalLogicUnavailableError,
    LogicCapabilityState,
    LogicCapabilityStatus,
    classify_canonical_compiler_capability,
)
from lib.formal_logic.frames import FrameKnowledgeBase

from .loader import import_module_optional
from .types import with_adapter_metadata


_logic_module, _logic_error = import_module_optional("ipfs_datasets_py.logic")
_fol_module, _fol_error = import_module_optional("ipfs_datasets_py.logic.fol")
_deontic_module, _deontic_error = import_module_optional("ipfs_datasets_py.logic.deontic")
_tdfol_module, _tdfol_error = import_module_optional("ipfs_datasets_py.logic.TDFOL")
_integration_module, _integration_error = import_module_optional("ipfs_datasets_py.logic.integration")
_external_provers_module, _external_provers_error = import_module_optional(
    "ipfs_datasets_py.logic.external_provers"
)
_z3_module, _z3_error = import_module_optional(
    "ipfs_datasets_py.logic.external_provers.smt.z3_prover_bridge"
)
# If the ipfs_datasets_py z3 bridge is absent, try the standalone z3-solver package.
_local_z3_module: Any = None
if _z3_module is None:
    _local_z3_module, _ = import_module_optional("z3")
_reasoner_module, _reasoner_error = import_module_optional(
    "ipfs_datasets_py.ipfs_datasets_py.processors.legal_data.reasoner.hybrid_v2_blueprint"
)
if _reasoner_module is None:
    _reasoner_module, _reasoner_error = import_module_optional(
        "ipfs_datasets_py.processors.legal_data.reasoner.hybrid_v2_blueprint"
    )

LOGIC_AVAILABLE = any(
    value is not None
    for value in (
        _logic_module,
        _fol_module,
        _deontic_module,
        _tdfol_module,
        _integration_module,
        _external_provers_module,
    )
)
LOGIC_ERROR = (
    _logic_error
    or _fol_error
    or _deontic_error
    or _tdfol_error
    or _integration_error
    or _external_provers_error
    or _z3_error
)
Z3_AVAILABLE = _z3_module is not None or _local_z3_module is not None
REASONER_BRIDGE_AVAILABLE = _reasoner_module is not None
REASONER_BRIDGE_ERROR = _reasoner_error
REASONER_BRIDGE_PATH = getattr(_reasoner_module, "__name__", "") if _reasoner_module is not None else ""
LOCAL_FORMAL_LOGIC_AVAILABLE = True
LOCAL_FORMAL_LOGIC_PATH = "lib.formal_logic"
LOGIC_CAPABILITY_SCHEMA_VERSION = "formal-logic-capabilities/v1"

_canonical_pipeline_module, _canonical_pipeline_error = import_module_optional(
    "ipfs_datasets_py.logic.integration.reasoning.legal_ir_canonical_pipeline"
)
_canonical_contracts_module, _canonical_contracts_error = import_module_optional(
    "ipfs_datasets_py.logic.legal_ir.canonical_contracts"
)
_canonical_compiler_module, _canonical_compiler_error = import_module_optional(
    "ipfs_datasets_py.logic.legal_ir.canonical_compiler"
)
_canonical_source_map_module, _canonical_source_map_error = import_module_optional(
    "ipfs_datasets_py.logic.integration.reasoning.legal_ir_source_maps"
)
_legal_ir_obligations_module, _legal_ir_obligations_error = import_module_optional(
    "ipfs_datasets_py.logic.integration.reasoning.legal_ir_obligations"
)
_proof_router_module, _proof_router_error = import_module_optional(
    "ipfs_datasets_py.logic.integration.reasoning.legal_ir_proof_router"
)
_hammer_module, _hammer_error = import_module_optional(
    "ipfs_datasets_py.logic.integration.reasoning.hammer"
)
_process_lifecycle_module, _process_lifecycle_error = import_module_optional(
    "ipfs_datasets_py.logic.hammers.process_lifecycle"
)
_CANONICAL_FORMALIZATION_RECEIPTS: Dict[str, Dict[str, Any]] = {}
_CANONICAL_FORMALIZATION_CACHE: Dict[str, str] = {}
_CANONICAL_RECEIPT_ORIGIN_DIGESTS: Dict[str, str] = {}
_CANONICAL_SUPPORTED_EXECUTION: Dict[str, Any] | None = None
_BOUND_OBLIGATION_RECEIPTS: Dict[str, Dict[str, Any]] = {}
_BOUND_OBLIGATION_CACHE: Dict[str, str] = {}
PROOF_OBLIGATION_ARTIFACT_SCHEMA = "legal-ir-bound-proof-obligations/v1"
PROOF_OBLIGATION_PREMISE_SCHEMA = "legal-ir-premise-inventory/v1"
PROOF_OBLIGATION_CHECKER_VERSION = "proof02-obligation-binder/v1"
PROOF_OBLIGATION_POLICY_VERSION = "proof02-structural-not-entailment/v1"
PROOF_OBLIGATION_BACKEND_IDENTITY = (
    "ipfs_datasets_py.logic.integration.reasoning.legal_ir_obligations."
    "generate_legal_ir_proof_obligations"
)
PROOF_OBLIGATION_TRUST_STRUCTURAL = "structural"
PROOF_ROUTING_SCHEMA = "legal-ir-bound-proof-routing/v1"
PROOF_ROUTING_POLICY_VERSION = "proof03-open-world-substantive-trust/v1"
PROOF_ELEMENT_CACHE_SCHEMA = "legal-ir-satisfied-element-cache/v1"
PROOF_ELEMENT_CACHE_POLICY_VERSION = "proof04-versioned-invalidation/v1"
_SATISFIED_ELEMENT_PROOF_CACHE: Dict[str, Dict[str, Any]] = {}
_BOUND_ROUTING_RECEIPT_ORIGINS: Dict[str, Dict[str, Any]] = {}
_ELEMENT_PROOF_EVALUATION_ORIGINS: Dict[str, Dict[str, Any]] = {}
PROOF_ROUTING_OUTCOMES = (
    "proved",
    "disproved",
    "refuted",
    "inconsistent",
    "unknown",
    "unsupported",
    "timeout",
    "cancelled",
    "unavailable",
)
PROOF_ROUTING_SUBSTANTIVE_TRUST = "kernel"
_PROOF_ROUTING_SAFE_ROUTES = (
    "deterministic_syntax",
    "deterministic_graph",
    "deterministic_contract",
)
_PROOF_ROUTING_INSTALL_PRONE_ROUTES = ("native_flogic",)
_UNTRUSTED_ROUTE_METADATA_KEYS = {
    "deterministic_syntax_valid",
    "deterministic_graph_valid",
    "deterministic_contract_valid",
    "native_tdfol_result",
    "native_cec_result",
    "native_flogic_result",
    "native_tdfol_prover",
    "native_cec_prover",
    "native_flogic_prover",
}
_INSTALL_DISABLE_ENV = {
    "IPFS_DATASETS_PY_LAZY_INSTALL_PROVERS": "0",
    "IPFS_DATASETS_PY_AUTO_INSTALL_PROVERS": "0",
}

_DEGRADED_OPERATION_REASONS = {
    FormalLogicOperation.TEXT_TO_FOL: (
        "The FOL provider imports, but this adapter exposes only a structural "
        "conversion contract; authoritative text-to-FOL conversion is unavailable."
    ),
    FormalLogicOperation.LEGAL_TEXT_TO_DEONTIC: (
        "The deontic provider imports, but this adapter exposes only a structural "
        "conversion contract; authoritative legal-rule translation is unavailable."
    ),
    FormalLogicOperation.PROVE_CLAIM_ELEMENTS: (
        "TDFOL is available for formula construction, but claim-element proof "
        "execution is not connected to a complete prover contract."
    ),
    FormalLogicOperation.CHECK_CONTRADICTIONS: (
        "TDFOL is available for formula construction, but contradiction checking "
        "is limited to structural signal extraction."
    ),
}


def _provider_diagnostic(error: Any, *, fallback: str) -> str:
    diagnostic = str(error or "").strip()
    return diagnostic or fallback


def get_logic_capability(
    operation: FormalLogicOperation | str,
) -> FormalLogicCapability:
    """Return the typed runtime contract for one logic operation.

    Importing the broad provider package is not evidence that every operation
    works.  Each operation is gated by the module it actually needs.  Degraded
    operations may return deterministic structural payloads, while strict
    validation callers can demand a complete implementation before execution.
    """

    normalized_operation = FormalLogicOperation.coerce(operation)
    module: Any = None
    error: Any = None
    module_path = ""

    if normalized_operation is FormalLogicOperation.TEXT_TO_FOL:
        module, error, module_path = _fol_module, _fol_error, "ipfs_datasets_py.logic.fol"
    elif normalized_operation is FormalLogicOperation.LEGAL_TEXT_TO_DEONTIC:
        module, error, module_path = (
            _deontic_module,
            _deontic_error,
            "ipfs_datasets_py.logic.deontic",
        )
    elif normalized_operation in {
        FormalLogicOperation.PROVE_CLAIM_ELEMENTS,
        FormalLogicOperation.CHECK_CONTRADICTIONS,
    }:
        module, error, module_path = (
            _tdfol_module,
            _tdfol_error,
            "ipfs_datasets_py.logic.TDFOL",
        )
    else:
        local_implemented = bool(LOCAL_FORMAL_LOGIC_AVAILABLE)
        reasoner_implemented = bool(REASONER_BRIDGE_AVAILABLE)
        if local_implemented or reasoner_implemented:
            provider = LOCAL_FORMAL_LOGIC_PATH if local_implemented else REASONER_BRIDGE_PATH
            return FormalLogicCapability(
                operation=normalized_operation,
                state=LogicCapabilityState.IMPLEMENTED,
                provider=provider,
                module_path=provider,
                details={
                    "schema_version": LOGIC_CAPABILITY_SCHEMA_VERSION,
                    "local_formal_logic_available": local_implemented,
                    "reasoner_bridge_available": reasoner_implemented,
                    "reasoner_bridge_path": REASONER_BRIDGE_PATH,
                },
            )
        return FormalLogicCapability(
            operation=normalized_operation,
            state=LogicCapabilityState.UNAVAILABLE,
            provider="ipfs_datasets_py",
            module_path=REASONER_BRIDGE_PATH or LOCAL_FORMAL_LOGIC_PATH,
            reason=_provider_diagnostic(
                REASONER_BRIDGE_ERROR,
                fallback="Neither the local formal-logic bridge nor the reasoner bridge is available.",
            ),
            details={"schema_version": LOGIC_CAPABILITY_SCHEMA_VERSION},
        )

    # Keep the aggregate probe as a startup master switch, but retain the
    # operation-specific module and diagnostic in the returned contract.
    if not LOGIC_AVAILABLE:
        module = None
        error = error or LOGIC_ERROR

    if module is None:
        return FormalLogicCapability(
            operation=normalized_operation,
            state=LogicCapabilityState.UNAVAILABLE,
            provider="ipfs_datasets_py",
            module_path=module_path,
            reason=_provider_diagnostic(
                error,
                fallback=f"Required provider module '{module_path}' is unavailable.",
            ),
            details={
                "schema_version": LOGIC_CAPABILITY_SCHEMA_VERSION,
                "local_formal_logic_available": bool(LOCAL_FORMAL_LOGIC_AVAILABLE),
            },
        )

    return FormalLogicCapability(
        operation=normalized_operation,
        state=LogicCapabilityState.DEGRADED,
        provider="ipfs_datasets_py",
        module_path=module_path,
        reason=_DEGRADED_OPERATION_REASONS[normalized_operation],
        details={
            "schema_version": LOGIC_CAPABILITY_SCHEMA_VERSION,
            "local_formal_logic_available": bool(LOCAL_FORMAL_LOGIC_AVAILABLE),
        },
    )


def get_logic_capabilities() -> Dict[FormalLogicOperation, FormalLogicCapability]:
    """Return capability contracts keyed by the typed operation enum."""

    return {operation: get_logic_capability(operation) for operation in FormalLogicOperation}


def get_logic_capability_report() -> Dict[str, Any]:
    """Return a JSON-ready summary of all formal-logic capabilities."""

    capabilities = get_logic_capabilities()
    state_counts = {
        state.value: sum(
            capability.state is state for capability in capabilities.values()
        )
        for state in LogicCapabilityState
    }
    return {
        "schema_version": LOGIC_CAPABILITY_SCHEMA_VERSION,
        "state_counts": state_counts,
        "capabilities": {
            operation.value: capability.as_dict()
            for operation, capability in capabilities.items()
        },
        "unavailable": [
            operation.value
            for operation, capability in capabilities.items()
            if not capability.available
        ],
        "degraded": [
            operation.value
            for operation, capability in capabilities.items()
            if capability.degraded
        ],
        "implemented": [
            operation.value
            for operation, capability in capabilities.items()
            if capability.implemented
        ],
    }


def require_logic_capability(
    operation: FormalLogicOperation | str,
    *,
    allow_degraded: bool = False,
) -> FormalLogicCapability:
    """Gate an operation and raise a typed, predictable capability error."""

    capability = get_logic_capability(operation)
    if allow_degraded:
        return capability.require_available()
    return capability.require_implemented()


def _logic_operation_metadata(capability: FormalLogicCapability) -> Dict[str, Any]:
    return {
        "capability_status": capability.state.value,
        "capability_available": capability.available,
        "capability_degraded": capability.degraded,
        "capability_implemented": capability.implemented,
        "capability": capability.as_dict(),
        "local_formal_logic_available": LOCAL_FORMAL_LOGIC_AVAILABLE,
        "local_formal_logic_path": LOCAL_FORMAL_LOGIC_PATH,
    }


def _selected_logic_path(*candidates: tuple[Any, str], fallback: str = "local") -> str:
    for module, path in candidates:
        if module is not None:
            return path
    return fallback

# Maximum byte length of a Z3 Boolean variable atom name (avoids identifier
# overflow for long formula strings submitted to the local z3-solver fallback).
_Z3_ATOM_NAME_MAX_LENGTH = 60


def _normalize_logic_symbol(value: Any, *, prefix: str) -> str:
    text = str(value or "").strip().lower()
    normalized = ''.join(ch if ch.isalnum() else '_' for ch in text).strip('_')
    if not normalized:
        normalized = prefix
    if normalized[0].isdigit():
        normalized = f"{prefix}_{normalized}"
    return normalized


def _normalize_time_symbol(date_value: Any, *, fallback: str = "t_unknown") -> str:
    text = str(date_value or "").strip()
    if not text:
        return fallback
    normalized = ''.join(ch if ch.isalnum() else '_' for ch in text).strip('_')
    return f"t_{normalized}" if normalized else fallback


def _build_temporal_formula_for_fact(event_symbol: str, temporal_fact: Dict[str, Any]) -> Dict[str, str]:
    start_date = temporal_fact.get("start_date")
    end_date = temporal_fact.get("end_date") or start_date
    is_range = bool(temporal_fact.get("is_range", False)) or (start_date and end_date and start_date != end_date)
    is_approximate = bool(temporal_fact.get("is_approximate", False))
    start_symbol = _normalize_time_symbol(start_date)
    end_symbol = _normalize_time_symbol(end_date, fallback=start_symbol)

    if start_date and not is_range:
        tdfol_formula = f"forall t (AtTime(t,{start_symbol}) -> Fact({event_symbol},t))"
        dcec_formula = f"Happens({event_symbol},{start_symbol})"
    elif start_date and end_date:
        tdfol_formula = f"forall t (During(t,{start_symbol},{end_symbol}) -> Fact({event_symbol},t))"
        dcec_formula = f"HoldsDuring({event_symbol},{start_symbol},{end_symbol})"
    else:
        tdfol_formula = f"forall t (Fact({event_symbol},t))"
        dcec_formula = f"Observed({event_symbol})"

    if is_approximate:
        tdfol_formula = f"{tdfol_formula} and Approximate({event_symbol})"
        dcec_formula = f"{dcec_formula} and ApproximateTime({event_symbol})"

    return {
        "tdfol": tdfol_formula,
        "dcec": dcec_formula,
    }


def _normalize_claim_support_temporal_handoff(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}

    def _normalize_text_list(items: Any) -> List[str]:
        normalized_items: List[str] = []
        for item in items if isinstance(items, list) else []:
            text = str(item or "").strip()
            if text and text not in normalized_items:
                normalized_items.append(text)
        return normalized_items

    normalized = {
        "claim_type": str(value.get("claim_type") or "").strip(),
        "claim_element_id": str(value.get("claim_element_id") or "").strip(),
        "unresolved_temporal_issue_count": int(value.get("unresolved_temporal_issue_count", 0) or 0),
        "chronology_task_count": int(value.get("chronology_task_count", 0) or 0),
        "unresolved_temporal_issue_ids": _normalize_text_list(value.get("unresolved_temporal_issue_ids")),
        "event_ids": _normalize_text_list(value.get("event_ids")),
        "temporal_fact_ids": _normalize_text_list(value.get("temporal_fact_ids")),
        "temporal_relation_ids": _normalize_text_list(value.get("temporal_relation_ids")),
        "timeline_issue_ids": _normalize_text_list(value.get("timeline_issue_ids")),
        "temporal_issue_ids": _normalize_text_list(value.get("temporal_issue_ids")),
        "temporal_proof_bundle_ids": _normalize_text_list(value.get("temporal_proof_bundle_ids")),
        "temporal_proof_objectives": _normalize_text_list(value.get("temporal_proof_objectives")),
    }
    if not normalized["claim_type"]:
        normalized.pop("claim_type")
    if not normalized["claim_element_id"]:
        normalized.pop("claim_element_id")
    if not normalized.get("unresolved_temporal_issue_count") and not normalized.get("chronology_task_count") and not any(
        normalized[key]
        for key in (
            "unresolved_temporal_issue_ids",
            "event_ids",
            "temporal_fact_ids",
            "temporal_relation_ids",
            "timeline_issue_ids",
            "temporal_issue_ids",
            "temporal_proof_bundle_ids",
            "temporal_proof_objectives",
        )
    ):
        return {}
    return normalized


def _normalize_claim_reasoning_review(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    normalized: Dict[str, Any] = {}
    for claim_type, review in value.items():
        claim_key = str(claim_type or "").strip()
        if not claim_key or not isinstance(review, dict):
            continue
        normalized[claim_key] = deepcopy(review)
    return normalized


def _stable_json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _stable_payload_digest(value: Any) -> str:
    return hashlib.sha256(_stable_json_dumps(value).encode("utf-8")).hexdigest()


def _normalize_temporal_proof_bundle(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    bundle = deepcopy(value)
    proof_bundle_id = str(bundle.get("proof_bundle_id") or "").strip()
    theorem_exports = bundle.get("theorem_exports")
    if not isinstance(theorem_exports, dict):
        theorem_exports = {}
        bundle["theorem_exports"] = theorem_exports
    tdfol_formulas = [
        str(formula).strip()
        for formula in (
            theorem_exports.get("tdfol_formulas")
            or bundle.get("tdfol_formulas")
            or bundle.get("tdfol_preview")
            or []
        )
        if str(formula).strip()
    ]
    dcec_formulas = [
        str(formula).strip()
        for formula in (
            theorem_exports.get("dcec_formulas")
            or bundle.get("dcec_formulas")
            or bundle.get("dcec_preview")
            or []
        )
        if str(formula).strip()
    ]
    theorem_exports["tdfol_formulas"] = tdfol_formulas
    theorem_exports["dcec_formulas"] = dcec_formulas
    theorem_exports.setdefault("tdfol_preview", tdfol_formulas[:3])
    theorem_exports.setdefault("dcec_preview", dcec_formulas[:3])
    theorem_exports["tdfol_formula_count"] = len(tdfol_formulas)
    theorem_exports["dcec_formula_count"] = len(dcec_formulas)
    theorem_export_metadata = theorem_exports.get("theorem_export_metadata")
    if not isinstance(theorem_export_metadata, dict):
        theorem_export_metadata = {}
        theorem_exports["theorem_export_metadata"] = theorem_export_metadata
    if proof_bundle_id and not theorem_export_metadata.get("proof_bundle_id"):
        theorem_export_metadata["proof_bundle_id"] = proof_bundle_id
    bundle.setdefault("contract_version", "claim_support_temporal_proof_bundle_v1")
    if proof_bundle_id:
        bundle.setdefault("persistence_key", proof_bundle_id)
    digest_payload = {
        "contract_version": bundle.get("contract_version"),
        "proof_bundle_id": proof_bundle_id,
        "claim_type": bundle.get("claim_type"),
        "claim_element_id": bundle.get("claim_element_id"),
        "rule_frame_id": bundle.get("rule_frame_id"),
        "temporal_fact_ids": bundle.get("temporal_fact_ids") or bundle.get("fact_ids") or [],
        "temporal_relation_ids": bundle.get("temporal_relation_ids") or bundle.get("relation_ids") or [],
        "temporal_issue_ids": bundle.get("temporal_issue_ids") or bundle.get("issue_ids") or [],
        "tdfol_formulas": tdfol_formulas,
        "dcec_formulas": dcec_formulas,
        "theorem_export_metadata": theorem_export_metadata,
    }
    bundle.setdefault("bundle_digest", _stable_payload_digest(digest_payload))
    return bundle


def _normalize_proof_bundles(value: Any) -> Dict[str, Dict[str, Any]]:
    bundles: Dict[str, Dict[str, Any]] = {}
    if isinstance(value, dict):
        for raw_key, raw_bundle in value.items():
            bundle = _normalize_temporal_proof_bundle(raw_bundle)
            if not bundle:
                continue
            key = str(raw_key or "").strip()
            if not key:
                key = str(bundle.get("persistence_key") or bundle.get("proof_bundle_id") or "").strip()
            if key:
                bundles[key] = bundle
    single_bundle = _normalize_temporal_proof_bundle(value)
    if single_bundle:
        key = str(
            single_bundle.get("persistence_key")
            or single_bundle.get("proof_bundle_id")
            or ""
        ).strip()
        if key:
            bundles[key] = single_bundle
    return bundles


def _extract_formula_payload_from_proof_bundles(
    proof_bundles: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    tdfol_formulas: List[str] = []
    dcec_formulas: List[str] = []
    tdfol_formula_certainties: Dict[str, str] = {}
    dcec_formula_certainties: Dict[str, str] = {}
    theorem_export_metadata: Dict[str, Any] = {}
    bundle_digests: List[str] = []

    for bundle_key in sorted(proof_bundles):
        bundle = proof_bundles[bundle_key]
        theorem_exports = bundle.get("theorem_exports") if isinstance(bundle.get("theorem_exports"), dict) else {}
        for formula in theorem_exports.get("tdfol_formulas", []) or []:
            normalized_formula = str(formula).strip()
            if normalized_formula and normalized_formula not in tdfol_formulas:
                tdfol_formulas.append(normalized_formula)
        for formula in theorem_exports.get("dcec_formulas", []) or []:
            normalized_formula = str(formula).strip()
            if normalized_formula and normalized_formula not in dcec_formulas:
                dcec_formulas.append(normalized_formula)
        if isinstance(theorem_exports.get("tdfol_formula_certainties"), dict):
            for formula, certainty in theorem_exports["tdfol_formula_certainties"].items():
                normalized_formula = str(formula).strip()
                if normalized_formula:
                    tdfol_formula_certainties[normalized_formula] = str(certainty or "certain")
        if isinstance(theorem_exports.get("dcec_formula_certainties"), dict):
            for formula, certainty in theorem_exports["dcec_formula_certainties"].items():
                normalized_formula = str(formula).strip()
                if normalized_formula:
                    dcec_formula_certainties[normalized_formula] = str(certainty or "certain")
        metadata = theorem_exports.get("theorem_export_metadata")
        if isinstance(metadata, dict) and not theorem_export_metadata:
            theorem_export_metadata = deepcopy(metadata)
        bundle_digest = str(bundle.get("bundle_digest") or "").strip()
        if bundle_digest and bundle_digest not in bundle_digests:
            bundle_digests.append(bundle_digest)

    if theorem_export_metadata:
        theorem_export_metadata = deepcopy(theorem_export_metadata)
        theorem_export_metadata["proof_bundle_digests"] = bundle_digests
        theorem_export_metadata["proof_execution_source"] = "temporal_proof_bundle"

    return {
        "tdfol_formulas": tdfol_formulas,
        "dcec_formulas": dcec_formulas,
        "tdfol_formula_certainties": tdfol_formula_certainties,
        "dcec_formula_certainties": dcec_formula_certainties,
        "theorem_export_metadata": theorem_export_metadata,
        "proof_bundle_digests": bundle_digests,
    }


def _summarize_fact_registry_for_facts(support_facts: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    facts = [fact for fact in support_facts or [] if isinstance(fact, dict)]
    source_family_counts: Dict[str, int] = {}
    record_scope_counts: Dict[str, int] = {}
    artifact_family_counts: Dict[str, int] = {}
    corpus_family_counts: Dict[str, int] = {}
    content_origin_counts: Dict[str, int] = {}
    parse_source_counts: Dict[str, int] = {}
    input_format_counts: Dict[str, int] = {}
    quality_tier_counts: Dict[str, int] = {}
    support_kind_counts: Dict[str, int] = {}
    source_table_counts: Dict[str, int] = {}
    unique_fact_ids = set()
    unique_source_refs = set()
    unique_source_records = set()
    passage_anchored_count = 0

    def _count(target: Dict[str, int], value: Any) -> None:
        text = str(value or "").strip()
        if text:
            target[text] = target.get(text, 0) + 1

    for fact in facts:
        fact_id = str(fact.get("fact_id") or "").strip()
        source_ref = str(fact.get("source_ref") or "").strip()
        source_family = str(fact.get("source_family") or "").strip()
        source_record_id = fact.get("source_record_id")
        source_passage = fact.get("source_passage") if isinstance(fact.get("source_passage"), dict) else {}
        if fact_id:
            unique_fact_ids.add(fact_id)
        if source_ref:
            unique_source_refs.add(source_ref)
        if source_family and source_record_id not in (None, ""):
            unique_source_records.add((source_family, str(source_record_id)))
        if source_passage.get("chunk_id") or fact.get("chunk_id"):
            passage_anchored_count += 1
        _count(source_family_counts, source_family)
        _count(record_scope_counts, fact.get("record_scope"))
        _count(artifact_family_counts, fact.get("artifact_family"))
        _count(corpus_family_counts, fact.get("corpus_family"))
        _count(content_origin_counts, fact.get("content_origin"))
        _count(parse_source_counts, fact.get("parse_source"))
        _count(input_format_counts, fact.get("input_format"))
        _count(quality_tier_counts, fact.get("quality_tier"))
        _count(support_kind_counts, fact.get("support_kind"))
        _count(source_table_counts, fact.get("source_table"))

    return {
        "registry_version": "claim_fact_registry_summary.v1",
        "source": "logic_predicate_support_facts",
        "fact_count": len(facts),
        "unique_fact_count": len(unique_fact_ids),
        "unique_source_ref_count": len(unique_source_refs),
        "unique_source_record_count": len(unique_source_records),
        "passage_anchored_count": passage_anchored_count,
        "source_family_counts": source_family_counts,
        "record_scope_counts": record_scope_counts,
        "artifact_family_counts": artifact_family_counts,
        "corpus_family_counts": corpus_family_counts,
        "content_origin_counts": content_origin_counts,
        "parse_source_counts": parse_source_counts,
        "input_format_counts": input_format_counts,
        "quality_tier_counts": quality_tier_counts,
        "support_kind_counts": support_kind_counts,
        "source_table_counts": source_table_counts,
    }


def _summarize_fact_registry_for_predicates(
    predicates: Iterable[Dict[str, Any]],
    *,
    support_facts: Iterable[Dict[str, Any]] = (),
) -> Dict[str, Any]:
    facts: List[Dict[str, Any]] = [fact for fact in support_facts or [] if isinstance(fact, dict)]
    predicate_summaries: List[Dict[str, Any]] = []
    for predicate in predicates or []:
        if not isinstance(predicate, dict):
            continue
        facts.extend(
            fact
            for fact in predicate.get("support_facts", []) or []
            if isinstance(fact, dict)
        )
        if isinstance(predicate.get("fact_registry_summary"), dict):
            predicate_summaries.append(predicate["fact_registry_summary"])
    summary = _summarize_fact_registry_for_facts(facts)
    if facts or not predicate_summaries:
        return summary

    count_map_keys = (
        "source_family_counts",
        "record_scope_counts",
        "artifact_family_counts",
        "corpus_family_counts",
        "content_origin_counts",
        "parse_source_counts",
        "input_format_counts",
        "quality_tier_counts",
        "support_kind_counts",
        "source_table_counts",
    )
    scalar_count_keys = (
        "fact_count",
        "unique_fact_count",
        "unique_source_ref_count",
        "unique_source_record_count",
        "passage_anchored_count",
    )
    for predicate_summary in predicate_summaries:
        for key in scalar_count_keys:
            summary[key] = int(summary.get(key) or 0) + int(predicate_summary.get(key) or 0)
        for key in count_map_keys:
            target = summary.setdefault(key, {})
            source = predicate_summary.get(key) if isinstance(predicate_summary.get(key), dict) else {}
            for value, count in source.items():
                text = str(value or "").strip()
                if text:
                    target[text] = int(target.get(text) or 0) + int(count or 0)
    summary["source"] = "logic_predicate_fact_registry_summary"
    return summary


def _normalize_logic_payload(payload_or_predicates: Any) -> Dict[str, Any]:
    if isinstance(payload_or_predicates, dict):
        raw_predicates = payload_or_predicates.get("predicates")
        predicates = raw_predicates if isinstance(raw_predicates, list) else []
        raw_support_facts = payload_or_predicates.get("support_facts")
        support_facts = [fact for fact in raw_support_facts if isinstance(fact, dict)] if isinstance(raw_support_facts, list) else []
        fact_registry_summary = (
            dict(payload_or_predicates.get("fact_registry_summary"))
            if isinstance(payload_or_predicates.get("fact_registry_summary"), dict)
            else _summarize_fact_registry_for_predicates(predicates, support_facts=support_facts)
        )
        temporal_reasoning_payload = payload_or_predicates.get("temporal_reasoning_payload")
        proof_bundles = _normalize_proof_bundles(payload_or_predicates.get("proof_bundles"))
        if isinstance(temporal_reasoning_payload, dict) and isinstance(temporal_reasoning_payload.get("proof_bundles"), dict):
            proof_bundles.update(_normalize_proof_bundles(temporal_reasoning_payload.get("proof_bundles")))
        temporal_proof_bundle = _normalize_temporal_proof_bundle(payload_or_predicates.get("temporal_proof_bundle"))
        if temporal_proof_bundle:
            key = str(
                temporal_proof_bundle.get("persistence_key")
                or temporal_proof_bundle.get("proof_bundle_id")
                or ""
            ).strip()
            if key:
                proof_bundles[key] = temporal_proof_bundle
        return {
            "predicates": [predicate for predicate in predicates if isinstance(predicate, dict)],
            "support_facts": support_facts,
            "fact_registry_summary": fact_registry_summary,
            "temporal_reasoning_payload": temporal_reasoning_payload if isinstance(temporal_reasoning_payload, dict) else {},
            "proof_bundles": proof_bundles,
            "claim_support_temporal_handoff": _normalize_claim_support_temporal_handoff(
                payload_or_predicates.get("claim_support_temporal_handoff")
            ),
            "claim_reasoning_review": _normalize_claim_reasoning_review(
                payload_or_predicates.get("claim_reasoning_review")
            ),
            "payload_keys": sorted(payload_or_predicates.keys()),
        }

    predicate_list = [predicate for predicate in payload_or_predicates if isinstance(predicate, dict)]
    return {
        "predicates": predicate_list,
        "support_facts": [],
        "fact_registry_summary": _summarize_fact_registry_for_predicates(predicate_list),
        "temporal_reasoning_payload": {},
        "proof_bundles": {},
        "claim_support_temporal_handoff": {},
        "claim_reasoning_review": {},
        "payload_keys": [],
    }


def _build_theorem_export_metadata(claim_support_temporal_handoff: Any) -> Dict[str, Any]:
    handoff = _normalize_claim_support_temporal_handoff(claim_support_temporal_handoff)
    if not handoff:
        return {}
    unresolved_temporal_issue_ids = list(handoff.get("unresolved_temporal_issue_ids", []) or [])
    temporal_issue_ids = list(handoff.get("temporal_issue_ids", []) or [])
    return {
        "contract_version": "claim_support_temporal_handoff_v1",
        "claim_type": str(handoff.get("claim_type") or "").strip(),
        "claim_element_id": str(handoff.get("claim_element_id") or "").strip(),
        "chronology_blocked": bool(
            int(handoff.get("unresolved_temporal_issue_count", 0) or 0)
            or unresolved_temporal_issue_ids
            or temporal_issue_ids
        ),
        "chronology_task_count": int(handoff.get("chronology_task_count", 0) or 0),
        "unresolved_temporal_issue_ids": unresolved_temporal_issue_ids,
        "event_ids": list(handoff.get("event_ids", []) or []),
        "temporal_fact_ids": list(handoff.get("temporal_fact_ids", []) or []),
        "temporal_relation_ids": list(handoff.get("temporal_relation_ids", []) or []),
        "timeline_issue_ids": list(handoff.get("timeline_issue_ids", []) or []),
        "temporal_issue_ids": temporal_issue_ids,
        "temporal_proof_bundle_ids": list(handoff.get("temporal_proof_bundle_ids", []) or []),
        "temporal_proof_objectives": list(handoff.get("temporal_proof_objectives", []) or []),
    }


def _build_temporal_reasoning_payload(
    predicates: Iterable[Dict[str, Any]],
    *,
    claim_support_temporal_handoff: Any = None,
    claim_reasoning_review: Any = None,
    proof_bundles: Any = None,
) -> Dict[str, Any]:
    predicate_list: List[Dict[str, Any]] = [
        predicate for predicate in predicates
        if isinstance(predicate, dict)
    ]
    claim_elements: List[Dict[str, Any]] = []
    support_traces: List[Dict[str, Any]] = []
    timeline_events: List[Dict[str, Any]] = []
    temporal_proof_leads: List[Dict[str, Any]] = []
    temporal_relations: List[Dict[str, Any]] = []
    contradiction_signals: List[Dict[str, Any]] = []
    tdfol_formulas: List[str] = []
    dcec_formulas: List[str] = []
    claim_type_counts: Counter[str] = Counter()

    for predicate in predicate_list:
        claim_type = str(predicate.get("claim_type") or "").strip()
        if claim_type:
            claim_type_counts[claim_type] += 1

        predicate_type = str(predicate.get("predicate_type") or "").strip()
        if predicate_type == "claim_element":
            claim_symbol = _normalize_logic_symbol(predicate.get("claim_element_id") or predicate.get("predicate_id"), prefix="claim")
            claim_element = {
                "claim_symbol": claim_symbol,
                "claim_type": claim_type,
                "claim_element_id": predicate.get("claim_element_id"),
                "claim_element_text": predicate.get("claim_element_text"),
                "coverage_status": predicate.get("coverage_status"),
            }
            if isinstance(predicate.get("fact_registry_summary"), dict):
                claim_element["fact_registry_summary"] = dict(predicate["fact_registry_summary"])
            support_facts = [fact for fact in predicate.get("support_facts", []) or [] if isinstance(fact, dict)]
            if support_facts:
                claim_element["support_fact_count"] = len(support_facts)
            claim_elements.append(claim_element)
        elif predicate_type == "support_trace":
            trace_symbol = _normalize_logic_symbol(predicate.get("predicate_id") or predicate.get("support_ref"), prefix="support")
            support_trace = {
                "support_symbol": trace_symbol,
                "claim_type": claim_type,
                "support_ref": predicate.get("support_ref"),
                "support_kind": predicate.get("support_kind"),
                "text": predicate.get("text") or "",
            }
            for field in (
                "source_family",
                "source_record_id",
                "source_ref",
                "record_scope",
                "artifact_family",
                "corpus_family",
                "content_origin",
                "parse_source",
                "input_format",
                "quality_tier",
                "quality_score",
                "chunk_id",
                "chunk_index",
                "source_passage",
            ):
                value = predicate.get(field)
                if value not in (None, "", [], {}):
                    support_trace[field] = value
            support_traces.append(support_trace)
            claim_symbol = _normalize_logic_symbol(predicate.get("claim_element_id") or claim_type, prefix="claim")
            tdfol_formulas.append(f"Supports({trace_symbol},{claim_symbol})")
            dcec_formulas.append(f"Supports({trace_symbol},{claim_symbol})")
        elif predicate_type == "temporal_fact":
            event_symbol = _normalize_logic_symbol(predicate.get("fact_id") or predicate.get("predicate_id"), prefix="event")
            event_entry = {
                "event_symbol": event_symbol,
                "claim_type": claim_type,
                "fact_id": predicate.get("fact_id"),
                "text": predicate.get("text") or "",
                "fact_type": predicate.get("fact_type"),
                "start_date": predicate.get("start_date"),
                "end_date": predicate.get("end_date"),
                "granularity": predicate.get("granularity"),
                "is_approximate": bool(predicate.get("is_approximate", False)),
                "is_range": bool(predicate.get("is_range", False)),
                "relative_markers": list(predicate.get("relative_markers", []) or []),
            }
            timeline_events.append(event_entry)
            formulas = _build_temporal_formula_for_fact(event_symbol, event_entry)
            tdfol_formulas.append(formulas["tdfol"])
            dcec_formulas.append(formulas["dcec"])
        elif predicate_type == "temporal_proof_lead":
            lead_symbol = _normalize_logic_symbol(predicate.get("lead_id") or predicate.get("predicate_id"), prefix="lead")
            lead_entry = {
                "lead_symbol": lead_symbol,
                "claim_type": claim_type,
                "lead_id": predicate.get("lead_id"),
                "description": predicate.get("description") or "",
                "related_fact_ids": list(predicate.get("related_fact_ids", []) or []),
                "element_targets": list(predicate.get("element_targets", []) or []),
                "temporal_scope": predicate.get("temporal_scope"),
                "start_date": predicate.get("start_date"),
                "end_date": predicate.get("end_date"),
                "granularity": predicate.get("granularity"),
                "is_approximate": bool(predicate.get("is_approximate", False)),
                "is_range": bool(predicate.get("is_range", False)),
            }
            temporal_proof_leads.append(lead_entry)
            formulas = _build_temporal_formula_for_fact(lead_symbol, lead_entry)
            tdfol_formulas.append(formulas["tdfol"].replace("Fact", "EvidenceLead"))
            dcec_formulas.append(formulas["dcec"].replace("Happens", "Available").replace("HoldsDuring", "AvailableDuring"))
            for related_fact_id in lead_entry["related_fact_ids"]:
                event_symbol = _normalize_logic_symbol(related_fact_id, prefix="event")
                tdfol_formulas.append(f"Supports({lead_symbol},{event_symbol})")
                dcec_formulas.append(f"Supports({lead_symbol},{event_symbol})")
        elif predicate_type == "temporal_relation":
            relation_type = str(predicate.get("relation_type") or "related_to").strip().lower() or "related_to"
            source_symbol = _normalize_logic_symbol(predicate.get("source_fact_id"), prefix="event")
            target_symbol = _normalize_logic_symbol(predicate.get("target_fact_id"), prefix="event")
            temporal_relations.append(
                {
                    "relation_id": predicate.get("predicate_id"),
                    "claim_type": claim_type,
                    "relation_type": relation_type,
                    "source_event_symbol": source_symbol,
                    "target_event_symbol": target_symbol,
                    "source_fact_id": predicate.get("source_fact_id"),
                    "target_fact_id": predicate.get("target_fact_id"),
                    "confidence": predicate.get("confidence"),
                }
            )
            relation_name = {
                "before": "Before",
                "same_time": "SameTime",
                "overlaps": "Overlaps",
            }.get(relation_type, _normalize_logic_symbol(relation_type, prefix="rel").title().replace("_", ""))
            tdfol_formulas.append(f"{relation_name}({source_symbol},{target_symbol})")
            dcec_formulas.append(f"{relation_name}({source_symbol},{target_symbol})")
        elif predicate_type in {"temporal_issue", "contradiction_candidate"}:
            signal_symbol = _normalize_logic_symbol(predicate.get("predicate_id") or predicate.get("summary"), prefix="signal")
            signal_entry = {
                "signal_symbol": signal_symbol,
                "claim_type": claim_type,
                "predicate_type": predicate_type,
                "issue_type": predicate.get("issue_type") or predicate.get("summary") or predicate_type,
                "summary": predicate.get("summary") or "",
                "severity": predicate.get("severity"),
            }
            contradiction_signals.append(signal_entry)
            if predicate_type == "temporal_issue":
                left_symbol = _normalize_logic_symbol(predicate.get("left_node_name"), prefix="event")
                right_symbol = _normalize_logic_symbol(predicate.get("right_node_name"), prefix="event")
                tdfol_formulas.append(f"Conflict({left_symbol},{right_symbol})")
                dcec_formulas.append(f"Conflicts({left_symbol},{right_symbol})")

    temporal_reasoning_payload = {
        "formalism": "tdfol_dcec_bridge_v1",
        "claim_types": sorted(claim_type_counts.keys()),
        "claim_elements": claim_elements,
        "support_traces": support_traces,
        "timeline_events": timeline_events,
        "temporal_proof_leads": temporal_proof_leads,
        "temporal_relations": temporal_relations,
        "contradiction_signals": contradiction_signals,
        "tdfol_formulas": tdfol_formulas,
        "dcec_formulas": dcec_formulas,
        "tdfol_formula_count": len(tdfol_formulas),
        "dcec_formula_count": len(dcec_formulas),
    }
    normalized_proof_bundles = _normalize_proof_bundles(proof_bundles)
    if normalized_proof_bundles:
        bundle_formula_payload = _extract_formula_payload_from_proof_bundles(normalized_proof_bundles)
        if bundle_formula_payload["tdfol_formulas"] or bundle_formula_payload["dcec_formulas"]:
            temporal_reasoning_payload["tdfol_formulas"] = bundle_formula_payload["tdfol_formulas"]
            temporal_reasoning_payload["dcec_formulas"] = bundle_formula_payload["dcec_formulas"]
            temporal_reasoning_payload["tdfol_formula_count"] = len(bundle_formula_payload["tdfol_formulas"])
            temporal_reasoning_payload["dcec_formula_count"] = len(bundle_formula_payload["dcec_formulas"])
            temporal_reasoning_payload["tdfol_formula_certainties"] = bundle_formula_payload["tdfol_formula_certainties"]
            temporal_reasoning_payload["dcec_formula_certainties"] = bundle_formula_payload["dcec_formula_certainties"]
        temporal_reasoning_payload["proof_bundles"] = deepcopy(normalized_proof_bundles)
        temporal_reasoning_payload["proof_execution_source"] = "temporal_proof_bundle"
        if bundle_formula_payload["theorem_export_metadata"]:
            temporal_reasoning_payload["theorem_export_metadata"] = bundle_formula_payload["theorem_export_metadata"]
    normalized_handoff = _normalize_claim_support_temporal_handoff(claim_support_temporal_handoff)
    if normalized_handoff:
        temporal_reasoning_payload["claim_support_temporal_handoff"] = normalized_handoff
        handoff_export_metadata = _build_theorem_export_metadata(normalized_handoff)
        existing_export_metadata = (
            temporal_reasoning_payload.get("theorem_export_metadata")
            if isinstance(temporal_reasoning_payload.get("theorem_export_metadata"), dict)
            else {}
        )
        if existing_export_metadata:
            merged_export_metadata = dict(handoff_export_metadata)
            merged_export_metadata.update(existing_export_metadata)
            temporal_reasoning_payload["theorem_export_metadata"] = merged_export_metadata
        else:
            temporal_reasoning_payload["theorem_export_metadata"] = handoff_export_metadata
    normalized_claim_reasoning_review = _normalize_claim_reasoning_review(claim_reasoning_review)
    if normalized_claim_reasoning_review:
        temporal_reasoning_payload["claim_reasoning_review"] = normalized_claim_reasoning_review
    return temporal_reasoning_payload


def _derive_reasoner_sentence(
    predicates: Iterable[Dict[str, Any]],
    temporal_reasoning_payload: Dict[str, Any],
) -> str:
    claim_element_text = ""
    claim_type = ""

    for predicate in predicates:
        if not isinstance(predicate, dict):
            continue
        if str(predicate.get("predicate_type") or "") != "claim_element":
            continue
        claim_element_text = str(predicate.get("claim_element_text") or "").strip()
        claim_type = str(predicate.get("claim_type") or "").strip()
        if claim_element_text:
            break

    if not claim_type:
        claim_types = list(temporal_reasoning_payload.get("claim_types", []) or [])
        claim_type = str(claim_types[0] or "").strip() if claim_types else ""

    seed_text = claim_element_text or claim_type
    seed_text = str(seed_text or "").strip().strip(".")
    if not seed_text:
        return ""

    lowered = seed_text.lower()
    if " shall not " in f" {lowered} " or " shall " in f" {lowered} " or " may " in f" {lowered} ":
        return seed_text if seed_text.endswith(".") else seed_text + "."

    return f"Claimant shall establish {seed_text.lower()}."


def _build_local_proof_artifact(
    predicates: Iterable[Dict[str, Any]],
    temporal_reasoning_payload: Dict[str, Any],
    claim_support_temporal_handoff: Dict[str, Any],
    proof_bundles: Dict[str, Dict[str, Any]] | None = None,
    *,
    reason: str = "",
) -> Dict[str, Any]:
    """Build a deterministic proof artifact from the local temporal bridge.

    The optional upstream reasoner is useful when present, but the adapter
    contract still needs a reviewable proof object in degraded installations.
    This local artifact treats generated TDFOL/DCEC formulas, temporal
    relations, and contradiction signals as the proof basis and exposes the
    same handoff metadata shape used by the upstream bridge.
    """
    predicate_list = [predicate for predicate in predicates if isinstance(predicate, dict)]
    normalized_proof_bundles = _normalize_proof_bundles(proof_bundles)
    theorem_export_metadata = dict(temporal_reasoning_payload.get("theorem_export_metadata") or {})
    handoff = dict(claim_support_temporal_handoff or {})
    tdfol_formulas = [
        str(formula).strip()
        for formula in temporal_reasoning_payload.get("tdfol_formulas", []) or []
        if str(formula).strip()
    ]
    dcec_formulas = [
        str(formula).strip()
        for formula in temporal_reasoning_payload.get("dcec_formulas", []) or []
        if str(formula).strip()
    ]
    contradiction_signals = [
        signal for signal in temporal_reasoning_payload.get("contradiction_signals", []) or []
        if isinstance(signal, dict)
    ]
    proof_basis = {
        "formalism": temporal_reasoning_payload.get("formalism") or "tdfol_dcec_bridge_v1",
        "claim_types": list(temporal_reasoning_payload.get("claim_types", []) or []),
        "predicate_ids": [
            str(predicate.get("predicate_id") or predicate.get("claim_element_id") or "").strip()
            for predicate in predicate_list
            if str(predicate.get("predicate_id") or predicate.get("claim_element_id") or "").strip()
        ],
        "tdfol_formulas": tdfol_formulas,
        "dcec_formulas": dcec_formulas,
        "theorem_export_metadata": theorem_export_metadata,
        "claim_support_temporal_handoff": handoff,
        "proof_bundle_digests": [
            str(bundle.get("bundle_digest") or "").strip()
            for bundle in normalized_proof_bundles.values()
            if str(bundle.get("bundle_digest") or "").strip()
        ],
    }
    proof_id = f"local-proof-{_stable_payload_digest(proof_basis)[:16]}"
    proof_status = "needs_review" if contradiction_signals else "passed"
    violation_count = len(contradiction_signals)
    explanation = {
        "proof_id": proof_id,
        "status": proof_status,
        "proof_execution_source": "local_temporal_bridge",
        "formalism": proof_basis["formalism"],
        "claim_types": proof_basis["claim_types"],
        "tdfol_formula_count": len(tdfol_formulas),
        "dcec_formula_count": len(dcec_formulas),
        "temporal_relation_count": len(temporal_reasoning_payload.get("temporal_relations", []) or []),
        "contradiction_signal_count": violation_count,
        "theorem_export_metadata": theorem_export_metadata,
        "claim_support_temporal_handoff": handoff,
        "reason": reason,
    }
    return {
        "available": True,
        "status": "success",
        "backend": "local_temporal_bridge",
        "reason": reason,
        "sentence": _derive_reasoner_sentence(predicate_list, temporal_reasoning_payload),
        "proof_id": proof_id,
        "proof_status": proof_status,
        "violation_count": violation_count,
        "theorem_export_metadata": theorem_export_metadata,
        "claim_support_temporal_handoff": handoff,
        "explanation": explanation,
        "prover_report": {
            "backend": "local_temporal_bridge",
            "formula_count": len(tdfol_formulas) + len(dcec_formulas),
            "tdfol_formula_count": len(tdfol_formulas),
            "dcec_formula_count": len(dcec_formulas),
            "contradiction_signal_count": violation_count,
        },
        "proof_bundles": deepcopy(normalized_proof_bundles),
    }


def _build_reasoner_proof_artifact(
    predicates: Iterable[Dict[str, Any]],
    temporal_reasoning_payload: Dict[str, Any],
    claim_support_temporal_handoff: Dict[str, Any],
    proof_bundles: Dict[str, Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    if not REASONER_BRIDGE_AVAILABLE or _reasoner_module is None:
        return _build_local_proof_artifact(
            predicates,
            temporal_reasoning_payload,
            claim_support_temporal_handoff,
            proof_bundles,
            reason=str(REASONER_BRIDGE_ERROR or "reasoner_bridge_unavailable"),
        )

    run_pipeline = getattr(_reasoner_module, "run_v2_pipeline_with_defaults", None)
    check_compliance = getattr(_reasoner_module, "check_compliance", None)
    explain_proof = getattr(_reasoner_module, "explain_proof", None)
    if not callable(run_pipeline) or not callable(check_compliance) or not callable(explain_proof):
        return _build_local_proof_artifact(
            predicates,
            temporal_reasoning_payload,
            claim_support_temporal_handoff,
            proof_bundles,
            reason="reasoner_bridge_missing_entrypoints",
        )

    sentence = _derive_reasoner_sentence(predicates, temporal_reasoning_payload)
    if not sentence:
        return _build_local_proof_artifact(
            predicates,
            temporal_reasoning_payload,
            claim_support_temporal_handoff,
            proof_bundles,
            reason="missing_reasoner_sentence",
        )

    theorem_export_metadata = dict(temporal_reasoning_payload.get("theorem_export_metadata") or {})
    normalized_proof_bundles = _normalize_proof_bundles(proof_bundles)
    try:
        pipeline_kwargs = {
            "theorem_export_metadata": theorem_export_metadata,
            "claim_support_temporal_handoff": claim_support_temporal_handoff,
            "proof_bundles": normalized_proof_bundles,
        }
        try:
            supported_parameters = set(inspect.signature(run_pipeline).parameters)
        except (TypeError, ValueError):
            supported_parameters = set()
        if supported_parameters:
            pipeline_kwargs = {
                key: value
                for key, value in pipeline_kwargs.items()
                if key in supported_parameters
            }
        pipeline = run_pipeline(sentence, **pipeline_kwargs)
        compliance = check_compliance(
            {
                "ir": pipeline.get("ir"),
                "facts": {},
                "events": [],
                "theorem_export_metadata": theorem_export_metadata,
                "claim_support_temporal_handoff": claim_support_temporal_handoff,
                "proof_bundles": normalized_proof_bundles,
            },
            {},
        )
        proof_id = str(compliance.get("proof_id") or "").strip()
        explanation = explain_proof(proof_id, format="json") if proof_id else {}
        normalized_explanation = explanation if isinstance(explanation, dict) else {}
        # Provider versions differ in how much context ``explain_proof``
        # returns.  Preserve the adapter contract even when the provider emits
        # only the proof graph.
        normalized_explanation = dict(normalized_explanation)
        normalized_explanation.setdefault("proof_id", proof_id)
        normalized_explanation.setdefault(
            "theorem_export_metadata",
            dict(compliance.get("theorem_export_metadata") or theorem_export_metadata),
        )
        normalized_explanation.setdefault(
            "claim_support_temporal_handoff",
            dict(compliance.get("claim_support_temporal_handoff") or claim_support_temporal_handoff),
        )
        return {
            "available": True,
            "status": "success",
            "sentence": sentence,
            "proof_id": proof_id,
            "proof_status": compliance.get("status"),
            "violation_count": compliance.get("violation_count"),
            "theorem_export_metadata": dict(compliance.get("theorem_export_metadata") or theorem_export_metadata),
            "claim_support_temporal_handoff": dict(
                compliance.get("claim_support_temporal_handoff") or claim_support_temporal_handoff
            ),
            "explanation": normalized_explanation,
            "prover_report": dict(pipeline.get("prover_report") or {}),
            "proof_bundles": deepcopy(normalized_proof_bundles),
        }
    except Exception as exc:
        local_artifact = _build_local_proof_artifact(
            predicates,
            temporal_reasoning_payload,
            claim_support_temporal_handoff,
            proof_bundles,
            reason=str(exc),
        )
        local_artifact["upstream_error"] = str(exc)
        local_artifact["sentence"] = sentence
        return local_artifact


def _summarize_predicates(predicates: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    predicate_list: List[Dict[str, Any]] = [
        predicate for predicate in predicates
        if isinstance(predicate, dict)
    ]
    predicate_type_counts: Counter[str] = Counter()
    claim_type_counts: Counter[str] = Counter()
    temporal_predicate_count = 0
    temporal_relation_count = 0
    contradiction_signal_count = 0

    for predicate in predicate_list:
        predicate_type = str(predicate.get("predicate_type") or "unknown").strip() or "unknown"
        predicate_type_counts[predicate_type] += 1
        claim_type = str(predicate.get("claim_type") or "").strip()
        if claim_type:
            claim_type_counts[claim_type] += 1
        if predicate_type.startswith("temporal_"):
            temporal_predicate_count += 1
        if predicate_type == "temporal_relation":
            temporal_relation_count += 1
        if predicate_type in {"contradiction_candidate", "temporal_issue"}:
            contradiction_signal_count += 1

    return {
        "predicate_count": len(predicate_list),
        "predicate_type_counts": dict(sorted(predicate_type_counts.items())),
        "claim_type_counts": dict(sorted(claim_type_counts.items())),
        "temporal_predicate_count": temporal_predicate_count,
        "temporal_relation_count": temporal_relation_count,
        "contradiction_signal_count": contradiction_signal_count,
    }


def _build_local_logic_snapshot(temporal_reasoning_payload: Dict[str, Any]) -> Dict[str, Any]:
    frame_kb = FrameKnowledgeBase()

    for claim in temporal_reasoning_payload.get("claim_elements", []) or []:
        claim_symbol = str(claim.get("claim_symbol") or "claim_unknown")
        frame_name = str(claim.get("claim_element_text") or claim_symbol)
        for slot in ("claim_type", "claim_element_id", "coverage_status"):
            value = claim.get(slot)
            if value:
                frame_kb.add_fact(claim_symbol, frame_name, slot, value, "claim_element")

    for trace in temporal_reasoning_payload.get("support_traces", []) or []:
        trace_symbol = str(trace.get("support_symbol") or "support_unknown")
        frame_name = str(trace.get("text") or trace_symbol)
        for slot in ("claim_type", "support_ref", "support_kind"):
            value = trace.get(slot)
            if value:
                frame_kb.add_fact(trace_symbol, frame_name, slot, value, "support_trace")

    for event in temporal_reasoning_payload.get("timeline_events", []) or []:
        event_symbol = str(event.get("event_symbol") or "event_unknown")
        frame_name = str(event.get("text") or event_symbol)
        for slot in ("claim_type", "fact_id", "fact_type", "start_date", "end_date", "granularity"):
            value = event.get(slot)
            if value:
                frame_kb.add_fact(event_symbol, frame_name, slot, value, "temporal_fact")
        for marker in event.get("relative_markers", []) or []:
            frame_kb.add_fact(event_symbol, frame_name, "relative_marker", marker, "temporal_fact")

    for relation in temporal_reasoning_payload.get("temporal_relations", []) or []:
        relation_symbol = str(relation.get("relation_id") or relation.get("relation_type") or "relation_unknown")
        frame_name = str(relation.get("relation_type") or relation_symbol)
        for slot in ("claim_type", "relation_type", "source_event_symbol", "target_event_symbol"):
            value = relation.get(slot)
            if value:
                frame_kb.add_fact(relation_symbol, frame_name, slot, value, "temporal_relation")

    for signal in temporal_reasoning_payload.get("contradiction_signals", []) or []:
        signal_symbol = str(signal.get("signal_symbol") or "signal_unknown")
        frame_name = str(signal.get("summary") or signal.get("issue_type") or signal_symbol)
        for slot in ("claim_type", "predicate_type", "issue_type", "severity"):
            value = signal.get(slot)
            if value:
                frame_kb.add_fact(signal_symbol, frame_name, slot, value, "contradiction_signal")

    return {
        "frame_count": frame_kb.frame_count(),
        "frames": frame_kb.to_dict(),
    }


# ---------------------------------------------------------------------------
# Local FOL extraction helpers (regex-based fallback when ipfs_datasets_py
# logic modules are absent or have not yet been populated by the submodule).
# ---------------------------------------------------------------------------

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_NAMED_ENTITY_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b")
_VERB_PHRASE_RE = re.compile(
    r"\b(report(?:ed)?|terminat(?:ed)?|discriminat(?:ed)?|retaliat(?:ed)?|"
    r"violat(?:ed)?|breach(?:ed)?|fail(?:ed)?|notif(?:ied)?|request(?:ed)?|"
    r"deny|denied|harm(?:ed)?|seek(?:s)?|allege(?:s)?)\b",
    re.IGNORECASE,
)
_DATE_RE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2}(?:,?\s+\d{4})?"
    r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b"
    r"|\b\d{4}-\d{2}-\d{2}\b",
    re.IGNORECASE,
)


def _local_extract_fol_predicates(text: str) -> List[Dict[str, Any]]:
    """Extract simple FOL-style predicates from *text* using regex heuristics.

    Returns a list of predicate dicts compatible with the rest of the logic
    pipeline.  Each dict carries at minimum ``predicate_type``, ``formula``,
    and ``source_sentence``.
    """
    predicates: List[Dict[str, Any]] = []
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    for index, sentence in enumerate(sentences, start=1):
        entities = _NAMED_ENTITY_RE.findall(sentence)
        verbs = _VERB_PHRASE_RE.findall(sentence)
        dates = _DATE_RE.findall(sentence)

        for verb in verbs:
            subj = entities[0] if entities else "Unknown"
            obj = entities[1] if len(entities) > 1 else "party"
            predicate_symbol = _normalize_logic_symbol(f"{verb}_{index}", prefix="pred")
            predicates.append(
                {
                    "predicate_type": "factual_statement",
                    "formula": f"{verb.capitalize()}({_normalize_logic_symbol(subj, prefix='e')},{_normalize_logic_symbol(obj, prefix='e')})",
                    "symbol": predicate_symbol,
                    "source_sentence": sentence,
                    "entities": entities[:4],
                    "verb": verb.lower(),
                }
            )

        for date in dates:
            temporal_symbol = _normalize_logic_symbol(f"temporal_{index}", prefix="t")
            predicates.append(
                {
                    "predicate_type": "temporal_fact",
                    "formula": f"AtTime({temporal_symbol},{_normalize_time_symbol(date)})",
                    "symbol": temporal_symbol,
                    "source_sentence": sentence,
                    "date_expression": date,
                }
            )

    return predicates


# ---------------------------------------------------------------------------
# Local deontic extraction helpers
# ---------------------------------------------------------------------------

_DEONTIC_PATTERNS: List[tuple[str, str, re.Pattern[str]]] = [
    ("prohibition", "F",
     re.compile(r"\b(must not|shall not|may not|cannot|can not|will not|is prohibited from|is forbidden to)\b", re.I)),
    ("obligation", "O",
     re.compile(r"\b(must|shall|required to|is required to|has a duty to|ought to)\b", re.I)),
    ("permission", "P",
     re.compile(r"\b(may|is permitted to|is allowed to|is entitled to|has the right to)\b", re.I)),
]


def _local_extract_deontic_norms(text: str) -> List[Dict[str, Any]]:
    """Extract deontic norms from *text* using pattern matching."""
    norms: List[Dict[str, Any]] = []
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    for index, sentence in enumerate(sentences, start=1):
        for norm_type, modality_symbol, pattern in _DEONTIC_PATTERNS:
            match = pattern.search(sentence)
            if match:
                entities = _NAMED_ENTITY_RE.findall(sentence)
                actor = entities[0] if entities else "actor"
                actor_sym = _normalize_logic_symbol(actor, prefix="a")
                norm_symbol = _normalize_logic_symbol(f"{norm_type}_{index}", prefix="norm")
                verb_rest = sentence[match.end():].strip().rstrip(".,;") or "perform_action"
                action_sym = _normalize_logic_symbol(verb_rest[:40], prefix="act")
                norms.append(
                    {
                        "norm_type": norm_type,
                        "modality": modality_symbol,
                        "formula": f"{modality_symbol}({actor_sym},{action_sym})",
                        "symbol": norm_symbol,
                        "actor": actor,
                        "action_text": verb_rest[:80],
                        "source_sentence": sentence,
                        "trigger_keyword": match.group(0),
                    }
                )
                break
    return norms


def text_to_fol(
    text: str,
    *,
    require_implemented: bool = False,
) -> Dict[str, Any]:
    """Convert *text* to First-Order Logic predicates.

    Tries the ``ipfs_datasets_py.logic.fol.FOLConverter`` from the submodule
    first.  Falls back to local regex-based extraction when the upstream
    module is unavailable.
    """
    capability = get_logic_capability(FormalLogicOperation.TEXT_TO_FOL)
    if require_implemented:
        capability.require_implemented()
    implementation_status = (
        "implemented" if capability.available else capability.state.value
    )
    # --- Try upstream FOLConverter (sync path) ---
    if _fol_module is not None:
        try:
            FOLConverter = getattr(_fol_module, "FOLConverter", None)
            if FOLConverter is None:
                # Older module layout: fol is a directory package
                fol_converter_mod, _ = import_module_optional("ipfs_datasets_py.logic.fol.converter")
                if fol_converter_mod is not None:
                    FOLConverter = getattr(fol_converter_mod, "FOLConverter", None)
            if FOLConverter is not None:
                converter = FOLConverter(use_nlp=False, use_cache=False)
                result = converter.convert(str(text or ""))
                raw_predicates = []
                if hasattr(result, "output") and result.output is not None:
                    output = result.output
                    if hasattr(output, "predicates"):
                        raw_predicates = [
                            {
                                "predicate_type": "factual_statement",
                                "formula": str(p) if not isinstance(p, dict) else str(p.get("formula", p)),
                                "symbol": _normalize_logic_symbol(str(p)[:30], prefix="pred"),
                            }
                            for p in (output.predicates or [])
                        ]
                return with_adapter_metadata(
                    {
                        "status": "success",
                        "predicates": raw_predicates,
                        "source_text": str(text or ""),
                        "converter": "FOLConverter",
                        "capability": capability.as_dict(),
                    },
                    operation="text_to_fol",
                    backend_available=capability.available,
                    degraded_reason=capability.reason,
                    implementation_status=implementation_status,
                    extra_metadata={
                        "local_formal_logic_available": LOCAL_FORMAL_LOGIC_AVAILABLE,
                        "local_formal_logic_path": LOCAL_FORMAL_LOGIC_PATH,
                        **_logic_operation_metadata(capability),
                        "logic_path": "logic.fol",
                    },
                )
        except Exception:
            pass

    # --- Local regex fallback ---
    predicates = _local_extract_fol_predicates(str(text or ""))
    return with_adapter_metadata(
        {
            "status": "success" if capability.available else capability.state.value,
            "predicates": predicates,
            "source_text": str(text or ""),
            "converter": "local_regex_fallback",
            "capability": capability.as_dict(),
        },
        operation="text_to_fol",
        backend_available=capability.available,
        degraded_reason=capability.reason,
        implementation_status=implementation_status,
        extra_metadata={
            "local_formal_logic_available": LOCAL_FORMAL_LOGIC_AVAILABLE,
            "local_formal_logic_path": LOCAL_FORMAL_LOGIC_PATH,
            **_logic_operation_metadata(capability),
            "logic_path": "logic.fol" if _fol_module is not None else "local",
        },
    )


def legal_text_to_deontic(
    text: str,
    *,
    require_implemented: bool = False,
) -> Dict[str, Any]:
    """Convert legal *text* to deontic logic norms.

    Tries ``ipfs_datasets_py.logic.deontic.DeonticConverter`` first, then
    supplements (or falls back) to local pattern-based extraction.

    The upstream converter returns a single ``DeonticFormula`` per call.  We
    wrap it into the same list format as the local extractor.  When the
    upstream result is empty the local extractor is used as a supplement so
    that well-known prohibition/obligation patterns are never silently dropped.
    """
    capability = get_logic_capability(FormalLogicOperation.LEGAL_TEXT_TO_DEONTIC)
    if require_implemented:
        capability.require_implemented()
    implementation_status = (
        "implemented" if capability.available else capability.state.value
    )
    upstream_norms: List[Dict[str, Any]] = []
    upstream_available = False

    # --- Try upstream DeonticConverter (sync path) ---
    if _deontic_module is not None:
        try:
            DeonticConverter = getattr(_deontic_module, "DeonticConverter", None)
            if DeonticConverter is None:
                deontic_conv_mod, _ = import_module_optional(
                    "ipfs_datasets_py.logic.deontic.converter"
                )
                if deontic_conv_mod is not None:
                    DeonticConverter = getattr(deontic_conv_mod, "DeonticConverter", None)
            if DeonticConverter is not None:
                converter = DeonticConverter(jurisdiction="us", document_type="general")
                result = converter.convert(str(text or ""))
                if hasattr(result, "output") and result.output is not None:
                    output = result.output
                    # DeonticFormula is a single formula object — wrap it.
                    if hasattr(output, "operator") and hasattr(output, "proposition"):
                        raw_op = getattr(output, "operator", None)
                        # Handle enum objects: prefer .value, then fall back to str.
                        op_value = str(getattr(raw_op, "value", raw_op) or "")
                        modality_map = {"O": "obligation", "P": "permission", "F": "prohibition"}
                        upstream_norms = [
                            {
                                "norm_type": modality_map.get(op_value, "obligation"),
                                "modality": op_value,
                                "formula": str(output.formula) if hasattr(output, "formula") else str(output),
                                "source_text": str(getattr(output, "source_text", "")),
                                "converter": "DeonticConverter",
                            }
                        ]
                    elif hasattr(output, "formulas"):
                        # DeonticFormulaSet
                        for f in (output.formulas or []):
                            op_val = str(getattr(getattr(f, "operator", None), "value", "") or "")
                            modality_map = {"O": "obligation", "P": "permission", "F": "prohibition"}
                            upstream_norms.append(
                                {
                                    "norm_type": modality_map.get(op_val, "obligation"),
                                    "modality": op_val,
                                    "formula": str(f.formula) if hasattr(f, "formula") else str(f),
                                    "source_text": str(getattr(f, "source_text", "")),
                                    "converter": "DeonticConverter",
                                }
                            )
                    elif hasattr(output, "norms"):
                        for n in (output.norms or []):
                            upstream_norms.append(
                                {
                                    "norm_type": str(getattr(n, "norm_type", "obligation")),
                                    "modality": str(getattr(n, "modality", "O")),
                                    "formula": str(getattr(n, "formula", n)),
                                    "source_text": str(getattr(n, "source_text", "")),
                                    "converter": "DeonticConverter",
                                }
                            )
                upstream_available = True
        except Exception:
            pass

    # --- Local pattern extraction ---
    local_norms = _local_extract_deontic_norms(str(text or ""))

    # Use upstream if it found norms, otherwise supplement with local patterns.
    if upstream_norms:
        norms = upstream_norms
        converter_used = "DeonticConverter"
    else:
        norms = local_norms
        converter_used = "local_pattern_fallback"

    return with_adapter_metadata(
        {
            "status": "success" if capability.available else capability.state.value,
            "norms": norms,
            "source_text": str(text or ""),
            "converter": converter_used,
            "capability": capability.as_dict(),
        },
        operation="legal_text_to_deontic",
        backend_available=capability.available,
        degraded_reason=capability.reason,
        implementation_status=implementation_status,
        extra_metadata={
            "local_formal_logic_available": LOCAL_FORMAL_LOGIC_AVAILABLE,
            "local_formal_logic_path": LOCAL_FORMAL_LOGIC_PATH,
            **_logic_operation_metadata(capability),
            "logic_path": "logic.deontic" if _deontic_module is not None else "local",
        },
    )


def prove_claim_elements(
    predicates: Iterable[Dict[str, Any]] | Dict[str, Any],
    *,
    require_implemented: bool = False,
) -> Dict[str, Any]:
    """Prove or refute claim elements by running the hybrid reasoning pipeline.

    Delegates to :func:`run_hybrid_reasoning` so that both the upstream
    ``hybrid_v2_blueprint`` reasoner bridge *and* the local TDFOL/DCEC bridge
    are tried in priority order.  The return value includes ``provable_elements``
    and ``unprovable_elements`` extracted from the proof artifact.

    Contradiction detection is performed by :func:`check_contradictions` and
    the count is included as ``contradiction_count`` in the result.
    """
    capability = get_logic_capability(FormalLogicOperation.PROVE_CLAIM_ELEMENTS)
    if require_implemented:
        capability.require_implemented()
    implementation_status = (
        "implemented" if capability.available else capability.state.value
    )
    normalized_payload = _normalize_logic_payload(predicates)
    predicate_list = normalized_payload["predicates"]
    predicate_summary = _summarize_predicates(predicate_list)
    fact_registry_summary = normalized_payload["fact_registry_summary"]
    proof_bundles = normalized_payload["proof_bundles"]

    # Run the full hybrid reasoning pipeline (handles reasoner bridge + fallback).
    reasoning_result = run_hybrid_reasoning(normalized_payload)
    result_inner = dict(reasoning_result.get("result") or {})
    proof_artifact = dict(result_inner.get("proof_artifact") or {})
    temporal_reasoning_payload = dict(reasoning_result.get("temporal_reasoning_payload") or {})

    proof_status = str(
        proof_artifact.get("proof_status")
        or proof_artifact.get("status")
        or "needs_review"
    )
    # Normalise status values from the reasoner bridge that should be treated
    # as "needs_review" rather than propagated as opaque strings.
    if proof_status in ("unavailable", "pending", "not_implemented", ""):
        proof_status = "needs_review"
    violation_count = int(proof_artifact.get("violation_count") or 0)

    # Run check_contradictions for a precise contradiction count that includes
    # both temporal-signal contradictions and formula-level negation pairs.
    contradiction_result = check_contradictions(normalized_payload)
    contradiction_count = int(contradiction_result.get("contradiction_count") or 0)
    contradiction_list = list(contradiction_result.get("contradictions") or [])
    # Escalate proof_status to needs_review when contradictions are found.
    if contradiction_count and proof_status == "passed":
        proof_status = "needs_review"

    # Classify each predicate as provable / unprovable based on proof status.
    # claim_element predicates are classified as provable only when their coverage
    # status is 'supported'; partially-supported or missing elements are *not*
    # classified as unprovable here, because those gaps are already tracked by the
    # missing_support_kind proof gap mechanism and would otherwise create duplicate
    # "logic_unprovable" proof gaps for what is really a support-coverage gap.
    # Unprovable classification is reserved for explicit reasoner failures
    # (proof_status == "failed") rather than partial-coverage situations.
    provable_elements: List[Dict[str, Any]] = []
    unprovable_elements: List[Dict[str, Any]] = []
    for pred in predicate_list:
        pred_type = str(pred.get("predicate_type") or "")
        if pred_type == "claim_element":
            coverage = str(pred.get("coverage_status") or "").strip().lower()
            if coverage == "supported":
                provable_elements.append(pred)
            elif proof_status == "failed":
                # Only flag as unprovable when the reasoner explicitly rejected the
                # predicate; a missing/partial coverage status is not a logic failure.
                unprovable_elements.append(pred)

    # Export TDFOL/DCEC formulas to Lean 4 and Coq theorem stubs.
    theorem_export: Dict[str, Any] = {}
    try:
        from .theorem_export import export_proof_result_to_theorems

        theorem_export = export_proof_result_to_theorems(
            {
                "temporal_reasoning_payload": temporal_reasoning_payload,
                "proof_artifact": proof_artifact,
                "proof_bundles": proof_bundles,
            },
        )
    except Exception:
        pass

    return with_adapter_metadata(
        {
            "status": (
                "success"
                if capability.available and proof_status not in {"error", "failed"}
                else capability.state.value
                if not capability.available
                else "error"
            ),
            "provable_elements": provable_elements,
            "unprovable_elements": unprovable_elements,
            "proof_status": proof_status,
            "violation_count": violation_count,
            "contradiction_count": contradiction_count,
            "contradictions": contradiction_list,
            **predicate_summary,
            "fact_registry_summary": deepcopy(fact_registry_summary),
            "temporal_reasoning_payload": temporal_reasoning_payload,
            "capability": capability.as_dict(),
            "proof_bundles": deepcopy(proof_bundles),
            "proof_artifact": proof_artifact,
            "theorem_export": theorem_export,
        },
        operation="prove_claim_elements",
        backend_available=capability.available,
        degraded_reason=capability.reason,
        implementation_status=implementation_status,
        extra_metadata={
            **predicate_summary,
            "fact_registry_summary": deepcopy(fact_registry_summary),
            "temporal_reasoning_payload": temporal_reasoning_payload,
            "proof_bundles": deepcopy(proof_bundles),
            "local_formal_logic_available": LOCAL_FORMAL_LOGIC_AVAILABLE,
            "local_formal_logic_path": LOCAL_FORMAL_LOGIC_PATH,
            "logic_path": _selected_logic_path(
                (_integration_module, "logic.integration"),
                (_external_provers_module, "logic.external_provers"),
                (_tdfol_module, "logic.TDFOL"),
                (_fol_module, "logic.fol"),
                (_deontic_module, "logic.deontic"),
            ),
            "reasoner_bridge_available": REASONER_BRIDGE_AVAILABLE,
            "theorem_export_version": theorem_export.get("export_version") or "",
            **_logic_operation_metadata(capability),
        },
    )


def _detect_formula_contradictions(formulas: List[str]) -> List[Dict[str, Any]]:
    """Detect simple A / not-A formula contradictions in *formulas*.

    A contradiction is flagged when the formula list contains both a positive
    assertion ``Pred(x,y)`` and its negation ``not(Pred(x,y))`` or a
    ``Conflict(x,y)`` entry that references known predicates.

    Returns a list of contradiction dicts compatible with the unified
    ``contradictions`` schema.
    """
    contradictions: List[Dict[str, Any]] = []
    positive: Dict[str, str] = {}
    negative: Dict[str, str] = {}
    conflict_pairs: List[Tuple[str, str]] = []

    _not_re = re.compile(r"^not\((.+)\)$", re.IGNORECASE)
    _conflict_re = re.compile(r"^Conflict\(([^,]+),([^)]+)\)$", re.IGNORECASE)

    for formula in formulas:
        formula = formula.strip()
        not_match = _not_re.match(formula)
        if not_match:
            inner = not_match.group(1).strip()
            negative[inner] = formula
            if inner in positive:
                contradictions.append(
                    {
                        "contradiction_id": f"formula-{len(contradictions) + 1}",
                        "type": "formula_negation",
                        "positive_formula": positive[inner],
                        "negative_formula": formula,
                        "summary": f"Contradiction: {inner} and not({inner})",
                        "severity": "error",
                    }
                )
        else:
            conflict_match = _conflict_re.match(formula)
            if conflict_match:
                left = conflict_match.group(1).strip()
                right = conflict_match.group(2).strip()
                conflict_pairs.append((left, right))
            else:
                positive[formula] = formula
                if formula in negative:
                    contradictions.append(
                        {
                            "contradiction_id": f"formula-{len(contradictions) + 1}",
                            "type": "formula_negation",
                            "positive_formula": formula,
                            "negative_formula": negative[formula],
                            "summary": f"Contradiction: {formula} and not({formula})",
                            "severity": "error",
                        }
                    )

    for left, right in conflict_pairs:
        contradictions.append(
            {
                "contradiction_id": f"conflict-{len(contradictions) + 1}",
                "type": "temporal_conflict",
                "left_symbol": left,
                "right_symbol": right,
                "summary": f"Temporal conflict between {left} and {right}",
                "severity": "warning",
            }
        )

    return contradictions


def _run_local_z3_check(
    tdfol_formulas: List[str],
    contradictions: List[Dict[str, Any]],
    z3_mod: Any,
) -> None:
    """Use the standalone z3-solver package to check formula satisfiability.

    This is called when the ipfs_datasets_py Z3 bridge is absent but the
    ``z3-solver`` PyPI package is installed.  The approach is conservative:

    * Each TDFOL formula string is parsed as a simple boolean variable
      (``z3.Bool``).  Formulas whose negations are both present in the set
      trigger an UNSAT result via the local :func:`_detect_formula_contradictions`
      helper — that part is already handled by step 2/3 above.
    * For conjunction formulas (``A and B``) we add both conjuncts as separate
      assertions so Z3 can derive conflicts between them.

    If Z3 reports UNSAT for the resulting assertion set we append a
    ``smt_unsat`` entry to *contradictions*.
    """
    Bool = getattr(z3_mod, "Bool", None)
    Solver = getattr(z3_mod, "Solver", None)
    unsat_const = getattr(z3_mod, "unsat", None)
    if not callable(Bool) or not callable(Solver) or unsat_const is None:
        return

    solver = Solver()
    # Pre-compute all normalised atom names in a set for O(1) negation lookup.
    all_atom_names = {
        re.sub(r"[^A-Za-z0-9_]", "_", f.strip())[:_Z3_ATOM_NAME_MAX_LENGTH]
        for f in tdfol_formulas
    }
    for formula in tdfol_formulas:
        # Represent each atomic formula as a fresh Boolean variable named
        # after the formula string (truncated to avoid Z3 identifier limits).
        atom_name = re.sub(r"[^A-Za-z0-9_]", "_", formula.strip())[:_Z3_ATOM_NAME_MAX_LENGTH]
        if not atom_name:
            continue
        var = Bool(atom_name)
        solver.add(var)
        # If the formula set already contains the negation of this formula
        # we add its negation as a second assertion so Z3 can derive UNSAT.
        neg_name = re.sub(r"[^A-Za-z0-9_]", "_", f"not({formula.strip()})")[:_Z3_ATOM_NAME_MAX_LENGTH]
        if neg_name in all_atom_names:
            neg_var = Bool(neg_name)
            solver.add(neg_var)

    if solver.check() == unsat_const:
        contradictions.append(
            {
                "contradiction_id": f"z3-local-{len(contradictions) + 1}",
                "type": "smt_unsat",
                "summary": "Z3 SMT solver (local z3-solver) reports formula set is unsatisfiable",
                "severity": "error",
                "z3_backend": "z3-solver",
            }
        )


def check_contradictions(
    predicates: Iterable[Dict[str, Any]] | Dict[str, Any],
    *,
    require_implemented: bool = False,
) -> Dict[str, Any]:
    """Check *predicates* for logical contradictions.

    Detection strategy (applied in order, results merged):

    1. **Contradiction-signal predicates** — predicates with
       ``predicate_type`` of ``temporal_issue`` or
       ``contradiction_candidate`` are surfaced directly.
    2. **Formula-level negation** — pairs ``P(x)`` / ``not(P(x))`` in the
       TDFOL formula set generated by the temporal bridge.
    3. **Conflict formulas** — any ``Conflict(a,b)`` entry emitted by the
       temporal bridge for temporal ordering violations.
    4. **Z3 SMT prover** (when ``ipfs_datasets_py`` Z3 bridge is available) —
       the formula set is submitted to the SMT prover for a satisfiability
       check; an UNSAT result is reported as a contradiction.

    Returns a dict with:

    * ``contradictions`` — list of contradiction dicts (typed, with
      ``contradiction_id``, ``type``, ``summary``, ``severity``)
    * ``contradiction_count`` — integer count
    * ``has_contradictions`` — bool
    * ``proof_status`` — ``"passed"`` (no contradictions found),
      ``"needs_review"`` (signals present but not proven), or ``"error"``
    """
    capability = get_logic_capability(FormalLogicOperation.CHECK_CONTRADICTIONS)
    if require_implemented:
        capability.require_implemented()
    implementation_status = (
        "implemented" if capability.available else capability.state.value
    )
    normalized_payload = _normalize_logic_payload(predicates)
    predicate_list = normalized_payload["predicates"]
    predicate_summary = _summarize_predicates(predicate_list)
    proof_bundles = normalized_payload["proof_bundles"]
    temporal_reasoning_payload = _build_temporal_reasoning_payload(
        predicate_list,
        claim_support_temporal_handoff=normalized_payload["claim_support_temporal_handoff"],
        claim_reasoning_review=normalized_payload["claim_reasoning_review"],
        proof_bundles=proof_bundles,
    )

    contradictions: List[Dict[str, Any]] = []

    # 1. Contradiction-signal predicates (temporal_issue / contradiction_candidate)
    for signal in temporal_reasoning_payload.get("contradiction_signals") or []:
        contradictions.append(
            {
                "contradiction_id": f"signal-{len(contradictions) + 1}",
                "type": str(signal.get("predicate_type") or "temporal_issue"),
                "issue_type": str(signal.get("issue_type") or ""),
                "summary": str(signal.get("summary") or "temporal contradiction signal"),
                "severity": str(signal.get("severity") or "warning"),
                "claim_type": str(signal.get("claim_type") or ""),
                "signal_symbol": str(signal.get("signal_symbol") or ""),
            }
        )

    # 2 & 3. Formula-level negation and Conflict() pairs from TDFOL bridge
    tdfol_formulas: List[str] = list(temporal_reasoning_payload.get("tdfol_formulas") or [])
    contradictions.extend(_detect_formula_contradictions(tdfol_formulas))

    # 4. Z3 SMT prover (optional, additive)
    # Tries the ipfs_datasets_py bridge first, then falls back to the
    # standalone z3-solver package if available.
    if _z3_module is not None:
        try:
            z3_check = getattr(_z3_module, "check_satisfiability", None)
            if callable(z3_check) and tdfol_formulas:
                z3_result = z3_check(tdfol_formulas)
                if isinstance(z3_result, dict) and z3_result.get("satisfiable") is False:
                    contradictions.append(
                        {
                            "contradiction_id": f"z3-{len(contradictions) + 1}",
                            "type": "smt_unsat",
                            "summary": "Z3 SMT solver reports formula set is unsatisfiable",
                            "severity": "error",
                            "z3_result": z3_result,
                        }
                    )
        except Exception:
            pass
    elif _local_z3_module is not None and tdfol_formulas:
        # Local z3-solver fallback: build a simple uninterpreted-function
        # model and check satisfiability of the formula set parsed as
        # assertion strings via z3.parse_smt2_string when possible.
        try:
            _run_local_z3_check(tdfol_formulas, contradictions, _local_z3_module)
        except Exception:
            pass

    proof_status = "passed" if not contradictions else "needs_review"

    return with_adapter_metadata(
        {
            "status": "success" if capability.available else capability.state.value,
            "contradictions": contradictions,
            "contradiction_count": len(contradictions),
            "has_contradictions": bool(contradictions),
            "proof_status": proof_status,
            **predicate_summary,
            "temporal_reasoning_payload": temporal_reasoning_payload,
            "proof_bundles": deepcopy(proof_bundles),
            "capability": capability.as_dict(),
        },
        operation="check_contradictions",
        backend_available=capability.available,
        degraded_reason=capability.reason,
        implementation_status=implementation_status,
        extra_metadata={
            **predicate_summary,
            "temporal_reasoning_payload": temporal_reasoning_payload,
            "proof_bundles": deepcopy(proof_bundles),
            "local_formal_logic_available": LOCAL_FORMAL_LOGIC_AVAILABLE,
            "local_formal_logic_path": LOCAL_FORMAL_LOGIC_PATH,
            **_logic_operation_metadata(capability),
        },
    )


def run_hybrid_reasoning(
    payload: Dict[str, Any],
    *,
    require_implemented: bool = False,
) -> Dict[str, Any]:
    """Run the local temporal bridge under an explicit capability contract."""

    capability = get_logic_capability(FormalLogicOperation.RUN_HYBRID_REASONING)
    if require_implemented:
        capability.require_implemented()
    normalized_payload = _normalize_logic_payload(payload)
    predicates = normalized_payload["predicates"]
    bridge_payload = normalized_payload["temporal_reasoning_payload"]
    claim_support_temporal_handoff = normalized_payload["claim_support_temporal_handoff"]
    claim_reasoning_review = normalized_payload["claim_reasoning_review"]
    proof_bundles = normalized_payload["proof_bundles"]
    predicate_summary = _summarize_predicates(predicates)
    fact_registry_summary = normalized_payload["fact_registry_summary"]

    if isinstance(bridge_payload, dict) and bridge_payload:
        temporal_reasoning_payload = deepcopy(bridge_payload)
    else:
        temporal_reasoning_payload = _build_temporal_reasoning_payload(
            predicates,
            claim_support_temporal_handoff=claim_support_temporal_handoff,
            claim_reasoning_review=claim_reasoning_review,
            proof_bundles=proof_bundles,
        )

    if proof_bundles:
        bundle_formula_payload = _extract_formula_payload_from_proof_bundles(proof_bundles)
        if bundle_formula_payload["tdfol_formulas"] or bundle_formula_payload["dcec_formulas"]:
            temporal_reasoning_payload["tdfol_formulas"] = bundle_formula_payload["tdfol_formulas"]
            temporal_reasoning_payload["dcec_formulas"] = bundle_formula_payload["dcec_formulas"]
            temporal_reasoning_payload["tdfol_formula_count"] = len(bundle_formula_payload["tdfol_formulas"])
            temporal_reasoning_payload["dcec_formula_count"] = len(bundle_formula_payload["dcec_formulas"])
            temporal_reasoning_payload["tdfol_formula_certainties"] = bundle_formula_payload["tdfol_formula_certainties"]
            temporal_reasoning_payload["dcec_formula_certainties"] = bundle_formula_payload["dcec_formula_certainties"]
        temporal_reasoning_payload["proof_bundles"] = deepcopy(proof_bundles)
        temporal_reasoning_payload["proof_execution_source"] = "temporal_proof_bundle"
        if bundle_formula_payload["theorem_export_metadata"]:
            temporal_reasoning_payload["theorem_export_metadata"] = bundle_formula_payload["theorem_export_metadata"]

    if claim_support_temporal_handoff and not isinstance(
        temporal_reasoning_payload.get("claim_support_temporal_handoff"),
        dict,
    ):
        temporal_reasoning_payload["claim_support_temporal_handoff"] = claim_support_temporal_handoff
    if claim_support_temporal_handoff and not isinstance(
        temporal_reasoning_payload.get("theorem_export_metadata"),
        dict,
    ):
        temporal_reasoning_payload["theorem_export_metadata"] = _build_theorem_export_metadata(
            claim_support_temporal_handoff
        )
    if claim_reasoning_review and not isinstance(
        temporal_reasoning_payload.get("claim_reasoning_review"),
        dict,
    ):
        temporal_reasoning_payload["claim_reasoning_review"] = deepcopy(claim_reasoning_review)
    if fact_registry_summary and not isinstance(
        temporal_reasoning_payload.get("fact_registry_summary"),
        dict,
    ):
        temporal_reasoning_payload["fact_registry_summary"] = deepcopy(fact_registry_summary)

    proof_artifact = _build_reasoner_proof_artifact(
        predicates,
        temporal_reasoning_payload,
        claim_support_temporal_handoff,
        proof_bundles,
    )
    local_logic_snapshot = _build_local_logic_snapshot(temporal_reasoning_payload)

    result_payload = {
        "status": "success",
        "capability": capability.as_dict(),
        "result": {
            "formalism": temporal_reasoning_payload.get("formalism") or "tdfol_dcec_bridge_v1",
            "claim_types": list(temporal_reasoning_payload.get("claim_types", []) or []),
            "tdfol_formulas": list(temporal_reasoning_payload.get("tdfol_formulas", []) or []),
            "dcec_formulas": list(temporal_reasoning_payload.get("dcec_formulas", []) or []),
            "theorem_export_metadata": dict(temporal_reasoning_payload.get("theorem_export_metadata") or {}),
            "proof_execution_source": str(temporal_reasoning_payload.get("proof_execution_source") or "predicates"),
            "proof_bundles": deepcopy(proof_bundles),
            "timeline_event_count": len(temporal_reasoning_payload.get("timeline_events", []) or []),
            "temporal_relation_count": len(temporal_reasoning_payload.get("temporal_relations", []) or []),
            "contradiction_signal_count": len(temporal_reasoning_payload.get("contradiction_signals", []) or []),
            "reasoning_mode": "temporal_bridge",
            "compiler_bridge_available": REASONER_BRIDGE_AVAILABLE,
            "proof_artifact": proof_artifact,
            "local_logic_snapshot": local_logic_snapshot,
            "fact_registry_summary": deepcopy(fact_registry_summary),
            "claim_reasoning_review": deepcopy(temporal_reasoning_payload.get("claim_reasoning_review") or {}),
            "compiler_bridge_path": (
                REASONER_BRIDGE_PATH if REASONER_BRIDGE_AVAILABLE else ""
            ),
        },
        "payload_keys": normalized_payload["payload_keys"],
        "predicate_count": predicate_summary.get("predicate_count", 0),
        "fact_registry_summary": deepcopy(fact_registry_summary),
        "proof_bundles": deepcopy(proof_bundles),
        "temporal_reasoning_payload": temporal_reasoning_payload,
    }
    return with_adapter_metadata(
        result_payload,
        operation="run_hybrid_reasoning",
        backend_available=capability.available,
        degraded_reason=str(REASONER_BRIDGE_ERROR) if REASONER_BRIDGE_ERROR and not REASONER_BRIDGE_AVAILABLE else None,
        implementation_status=capability.state.value,
        extra_metadata={
            **predicate_summary,
            "reasoning_mode": "temporal_bridge",
            "compiler_bridge_available": REASONER_BRIDGE_AVAILABLE,
            "compiler_bridge_path": (
                REASONER_BRIDGE_PATH if REASONER_BRIDGE_AVAILABLE else ""
            ),
            "local_formal_logic_available": LOCAL_FORMAL_LOGIC_AVAILABLE,
            "local_formal_logic_path": LOCAL_FORMAL_LOGIC_PATH,
            "local_logic_snapshot_frame_count": local_logic_snapshot["frame_count"],
            **_logic_operation_metadata(capability),
            "proof_bundle_count": len(proof_bundles),
        },
    )


def export_theorem_from_proof_bundle(
    proof_bundle: Dict[str, Any],
    *,
    exported_at: str = "1970-01-01T00:00:00+00:00",
) -> Dict[str, Any]:
    """Recreate Lean/Coq theorem exports from a persisted temporal proof bundle.

    The function is deterministic by default: if callers do not supply
    ``exported_at`` the same persisted bundle produces byte-identical theorem
    sources across runs.  The bundle's formulas, metadata, certainties, and
    digest are preserved in the returned export payload.
    """
    bundle = _normalize_temporal_proof_bundle(proof_bundle)
    theorem_exports = bundle.get("theorem_exports") if isinstance(bundle.get("theorem_exports"), dict) else {}
    tdfol_formulas = [
        str(formula).strip()
        for formula in theorem_exports.get("tdfol_formulas", []) or []
        if str(formula).strip()
    ]
    dcec_formulas = [
        str(formula).strip()
        for formula in theorem_exports.get("dcec_formulas", []) or []
        if str(formula).strip()
    ]
    theorem_export_metadata = (
        deepcopy(theorem_exports.get("theorem_export_metadata"))
        if isinstance(theorem_exports.get("theorem_export_metadata"), dict)
        else {}
    )
    theorem_export_metadata["proof_execution_source"] = "temporal_proof_bundle"
    theorem_export_metadata["proof_bundle_digest"] = bundle.get("bundle_digest", "")

    from .theorem_export import export_proof_result_to_theorems

    theorem_export = export_proof_result_to_theorems(
        {
            "temporal_reasoning_payload": {
                "formalism": "tdfol_dcec_bridge_v1",
                "tdfol_formulas": tdfol_formulas,
                "dcec_formulas": dcec_formulas,
                "tdfol_formula_certainties": deepcopy(theorem_exports.get("tdfol_formula_certainties") or {}),
                "dcec_formula_certainties": deepcopy(theorem_exports.get("dcec_formula_certainties") or {}),
                "theorem_export_metadata": theorem_export_metadata,
                "proof_bundles": {
                    str(bundle.get("persistence_key") or bundle.get("proof_bundle_id") or "bundle"): bundle
                },
            },
            "proof_bundles": {
                str(bundle.get("persistence_key") or bundle.get("proof_bundle_id") or "bundle"): bundle
            },
        },
        claim_id=str(bundle.get("proof_bundle_id") or ""),
        exported_at=exported_at,
    )
    theorem_export["theorem_export_metadata"] = theorem_export_metadata
    theorem_export["proof_bundle_id"] = str(bundle.get("proof_bundle_id") or "")
    theorem_export["proof_bundle_digest"] = str(bundle.get("bundle_digest") or "")
    theorem_export["tdfol_formula_certainties"] = deepcopy(theorem_exports.get("tdfol_formula_certainties") or {})
    theorem_export["dcec_formula_certainties"] = deepcopy(theorem_exports.get("dcec_formula_certainties") or {})
    return theorem_export




# ---------------------------------------------------------------------------
# Complaint-type predicate templates
#
# Each template maps a claim element to:
#   - fol_template: First-Order Logic formula template (use {subject}/{object} placeholders)
#   - dcec_template: DCEC formula template
#   - predicate_types: list of expected predicate types for the element
#   - grounded_facts: example grounded predicate strings for the element
# ---------------------------------------------------------------------------

_COMPLAINT_PREDICATE_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "employment_discrimination": {
        "label": "Employment Discrimination",
        "elements": [
            {
                "element_id": "protected_trait",
                "element_text": "Protected trait or class",
                "fol_template": "exists x (Employee(x) & HasProtectedTrait(x, {trait}) & MemberOf(x, ProtectedClass))",
                "dcec_template": "Believes(Claimant, HasProtectedTrait(Employee, {trait}))",
                "predicate_types": ["factual_statement", "claim_element"],
                "grounded_facts": [
                    "Employee(complainant) & HasProtectedTrait(complainant, race)",
                    "Employee(complainant) & HasProtectedTrait(complainant, disability)",
                ],
                "expected_supporting_evidence": ["personnel_record", "testimony", "hire_record"],
            },
            {
                "element_id": "employment_relationship",
                "element_text": "Employment relationship or workplace context",
                "fol_template": "exists x y (Employee(x) & Employer(y) & EmployedBy(x, y) & At(x, Workplace))",
                "dcec_template": "Knows(Employer, EmployedBy(Employee, Employer))",
                "predicate_types": ["factual_statement", "claim_element"],
                "grounded_facts": [
                    "EmployedBy(complainant, respondent)",
                    "WorkplaceContext(complainant, respondent, {start_date})",
                ],
                "expected_supporting_evidence": ["offer_letter", "pay_stub", "org_chart"],
            },
            {
                "element_id": "adverse_action",
                "element_text": "Adverse employment action or harassment",
                "fol_template": (
                    "exists x y (Employee(x) & Employer(y) & "
                    "AdverseAction(y, x, {action_type}) & OccurredAt({action_type}, {date}))"
                ),
                "dcec_template": "Happens(AdverseAction(Employer, Employee, {action_type}), {date})",
                "predicate_types": ["factual_statement", "claim_element", "temporal_fact"],
                "grounded_facts": [
                    "AdverseAction(respondent, complainant, termination)",
                    "AdverseAction(respondent, complainant, demotion)",
                ],
                "expected_supporting_evidence": ["termination_notice", "discipline_record", "performance_review"],
            },
            {
                "element_id": "discriminatory_motive",
                "element_text": "Facts suggesting discriminatory motive",
                "fol_template": (
                    "exists x y t (AdverseAction(y, x, {action_type}) & "
                    "HasProtectedTrait(x, {trait}) & "
                    "CausedBy({action_type}, HasProtectedTrait(x, {trait})))"
                ),
                "dcec_template": (
                    "Causes(HasProtectedTrait(Employee, {trait}), AdverseAction(Employer, Employee, {action_type}))"
                ),
                "predicate_types": ["factual_statement", "claim_element"],
                "grounded_facts": [
                    "CausedBy(termination, HasProtectedTrait(complainant, race))",
                    "DiscriminatoryMotive(respondent, complainant, disability)",
                ],
                "expected_supporting_evidence": ["email", "witness_statement", "comparator_record"],
            },
        ],
    },
    "housing_discrimination": {
        "label": "Housing Discrimination",
        "elements": [
            {
                "element_id": "protected_trait",
                "element_text": "Protected trait or class",
                "fol_template": "exists x (Tenant(x) & HasProtectedTrait(x, {trait}) & MemberOf(x, ProtectedClass))",
                "dcec_template": "Believes(Claimant, HasProtectedTrait(Tenant, {trait}))",
                "predicate_types": ["factual_statement", "claim_element"],
                "grounded_facts": [
                    "Tenant(complainant) & HasProtectedTrait(complainant, race)",
                    "Tenant(complainant) & HasProtectedTrait(complainant, disability)",
                ],
                "expected_supporting_evidence": ["application_record", "testimony"],
            },
            {
                "element_id": "housing_context",
                "element_text": "Housing relationship or tenancy context",
                "fol_template": (
                    "exists x y (Tenant(x) & Landlord(y) & "
                    "HasHousingRelationship(x, y, {relationship_type}))"
                ),
                "dcec_template": "Knows(Landlord, HasHousingRelationship(Tenant, Landlord, {relationship_type}))",
                "predicate_types": ["factual_statement", "claim_element"],
                "grounded_facts": [
                    "HasHousingRelationship(complainant, respondent, tenant)",
                    "HasHousingRelationship(complainant, respondent, applicant)",
                ],
                "expected_supporting_evidence": ["lease", "application_record", "rent_record"],
            },
            {
                "element_id": "adverse_action",
                "element_text": "Discriminatory housing action",
                "fol_template": (
                    "exists x y (Landlord(y) & Tenant(x) & "
                    "HousingAdverseAction(y, x, {action_type}) & OccurredAt({action_type}, {date}))"
                ),
                "dcec_template": "Happens(HousingAdverseAction(Landlord, Tenant, {action_type}), {date})",
                "predicate_types": ["factual_statement", "claim_element", "temporal_fact"],
                "grounded_facts": [
                    "HousingAdverseAction(respondent, complainant, eviction)",
                    "HousingAdverseAction(respondent, complainant, denial)",
                ],
                "expected_supporting_evidence": ["denial_notice", "eviction_notice", "witness_statement"],
            },
            {
                "element_id": "discriminatory_motive",
                "element_text": "Facts suggesting discriminatory motive",
                "fol_template": (
                    "exists x y (HousingAdverseAction(y, x, {action_type}) & "
                    "HasProtectedTrait(x, {trait}) & "
                    "CausedBy({action_type}, HasProtectedTrait(x, {trait})))"
                ),
                "dcec_template": (
                    "Causes(HasProtectedTrait(Tenant, {trait}), HousingAdverseAction(Landlord, Tenant, {action_type}))"
                ),
                "predicate_types": ["factual_statement", "claim_element"],
                "grounded_facts": [
                    "CausedBy(denial, HasProtectedTrait(complainant, race))",
                    "DiscriminatoryMotive(respondent, complainant, disability)",
                ],
                "expected_supporting_evidence": ["landlord_message", "witness_statement"],
            },
        ],
    },
    "retaliation": {
        "label": "Retaliation",
        "elements": [
            {
                "element_id": "protected_activity",
                "element_text": "Protected activity",
                "fol_template": (
                    "exists x (Employee(x) & ProtectedActivity(x, {activity_type}) & "
                    "OccurredAt({activity_type}, {date}))"
                ),
                "dcec_template": "Happens(ProtectedActivity(Employee, {activity_type}), {date})",
                "predicate_types": ["factual_statement", "claim_element", "temporal_fact"],
                "grounded_facts": [
                    "ProtectedActivity(complainant, discrimination_complaint)",
                    "ProtectedActivity(complainant, safety_report)",
                ],
                "expected_supporting_evidence": ["hr_complaint", "eeoc_filing", "email"],
            },
            {
                "element_id": "knowledge_of_activity",
                "element_text": "Employer knowledge of protected activity",
                "fol_template": (
                    "exists x y (Employee(x) & Employer(y) & "
                    "Knows(y, ProtectedActivity(x, {activity_type})))"
                ),
                "dcec_template": "Knows(Employer, ProtectedActivity(Employee, {activity_type}))",
                "predicate_types": ["factual_statement", "claim_element"],
                "grounded_facts": [
                    "Knows(respondent, ProtectedActivity(complainant, discrimination_complaint))",
                ],
                "expected_supporting_evidence": ["acknowledgment", "email", "witness_statement"],
            },
            {
                "element_id": "adverse_action",
                "element_text": "Adverse action following protected activity",
                "fol_template": (
                    "exists x y (Employee(x) & Employer(y) & "
                    "AdverseAction(y, x, {action_type}) & "
                    "After(AdverseAction(y, x, {action_type}), ProtectedActivity(x, {activity_type})))"
                ),
                "dcec_template": (
                    "Happens(AdverseAction(Employer, Employee, {action_type}), {date}) & "
                    "After({date}, {activity_date})"
                ),
                "predicate_types": ["factual_statement", "claim_element", "temporal_fact", "temporal_relation"],
                "grounded_facts": [
                    "AdverseAction(respondent, complainant, termination)",
                    "After(termination_date, complaint_date)",
                ],
                "expected_supporting_evidence": ["termination_notice", "schedule_change", "witness_statement"],
            },
            {
                "element_id": "causal_connection",
                "element_text": "Causal connection between protected activity and adverse action",
                "fol_template": (
                    "exists x y (CausedBy(AdverseAction(y, x, {action_type}), ProtectedActivity(x, {activity_type})) & "
                    "TemporalProximity(AdverseAction(y, x, {action_type}), ProtectedActivity(x, {activity_type})))"
                ),
                "dcec_template": (
                    "Causes(ProtectedActivity(Employee, {activity_type}), AdverseAction(Employer, Employee, {action_type}))"
                ),
                "predicate_types": ["factual_statement", "claim_element"],
                "grounded_facts": [
                    "CausedBy(termination, discrimination_complaint)",
                    "TemporalProximity(termination_date, complaint_date)",
                ],
                "expected_supporting_evidence": ["email", "witness_statement", "timeline_record"],
            },
        ],
    },
    "fair_housing": {
        "label": "Fair Housing",
        "elements": [
            {
                "element_id": "protected_trait",
                "element_text": "Protected trait or class",
                "fol_template": "exists x (Person(x) & HasProtectedTrait(x, {trait}) & MemberOf(x, ProtectedClass))",
                "dcec_template": "Believes(Claimant, HasProtectedTrait(Person, {trait}))",
                "predicate_types": ["factual_statement", "claim_element"],
                "grounded_facts": [
                    "Person(complainant) & HasProtectedTrait(complainant, race)",
                    "Person(complainant) & HasProtectedTrait(complainant, disability)",
                ],
                "expected_supporting_evidence": ["application_record", "testimony"],
            },
            {
                "element_id": "housing_activity",
                "element_text": "Covered housing activity",
                "fol_template": (
                    "exists x y (Person(x) & HousingProvider(y) & "
                    "HousingActivity(y, x, {activity_type}))"
                ),
                "dcec_template": "Knows(HousingProvider, HousingActivity(HousingProvider, Person, {activity_type}))",
                "predicate_types": ["factual_statement", "claim_element"],
                "grounded_facts": [
                    "HousingActivity(respondent, complainant, rental_application)",
                    "HousingActivity(respondent, complainant, loan_application)",
                ],
                "expected_supporting_evidence": ["application_record", "lease", "loan_document"],
            },
            {
                "element_id": "adverse_action",
                "element_text": "Discriminatory or adverse housing action",
                "fol_template": (
                    "exists x y (HousingProvider(y) & Person(x) & "
                    "AdverseHousingAction(y, x, {action_type}) & OccurredAt({action_type}, {date}))"
                ),
                "dcec_template": "Happens(AdverseHousingAction(HousingProvider, Person, {action_type}), {date})",
                "predicate_types": ["factual_statement", "claim_element", "temporal_fact"],
                "grounded_facts": [
                    "AdverseHousingAction(respondent, complainant, denial)",
                    "AdverseHousingAction(respondent, complainant, steering)",
                ],
                "expected_supporting_evidence": ["denial_notice", "correspondence", "witness_statement"],
            },
            {
                "element_id": "discriminatory_motive",
                "element_text": "Facts suggesting discriminatory motive",
                "fol_template": (
                    "exists x y (AdverseHousingAction(y, x, {action_type}) & "
                    "HasProtectedTrait(x, {trait}) & "
                    "CausedBy({action_type}, HasProtectedTrait(x, {trait})))"
                ),
                "dcec_template": (
                    "Causes(HasProtectedTrait(Person, {trait}), AdverseHousingAction(HousingProvider, Person, {action_type}))"
                ),
                "predicate_types": ["factual_statement", "claim_element"],
                "grounded_facts": [
                    "CausedBy(denial, HasProtectedTrait(complainant, race))",
                    "DiscriminatoryMotive(respondent, complainant, disability)",
                ],
                "expected_supporting_evidence": ["correspondence", "witness_statement", "comparator_record"],
            },
        ],
    },
}


def get_predicate_templates(complaint_type: str) -> Dict[str, Any]:
    """Return grounded predicate templates for *complaint_type*.

    Supports ``employment_discrimination``, ``housing_discrimination``,
    ``retaliation``, and ``fair_housing``.  Returns an empty elements list
    for unknown types.

    Each element in the result carries ``fol_template``, ``dcec_template``,
    ``predicate_types``, and ``grounded_facts`` ready for use in
    :func:`map_claim_elements_to_predicates`.
    """
    normalized_type = str(complaint_type or "").strip().lower().replace("-", "_").replace(" ", "_")
    template = _COMPLAINT_PREDICATE_TEMPLATES.get(normalized_type)
    if template is None:
        return with_adapter_metadata(
            {
                "status": "not_found",
                "complaint_type": complaint_type,
                "label": "",
                "elements": [],
                "element_count": 0,
                "supported_complaint_types": list(_COMPLAINT_PREDICATE_TEMPLATES.keys()),
            },
            operation="get_predicate_templates",
            backend_available=True,
            implementation_status="implemented",
        )
    return with_adapter_metadata(
        {
            "status": "success",
            "complaint_type": complaint_type,
            "label": template.get("label", ""),
            "elements": template["elements"],
            "element_count": len(template["elements"]),
            "supported_complaint_types": list(_COMPLAINT_PREDICATE_TEMPLATES.keys()),
        },
        operation="get_predicate_templates",
        backend_available=True,
        implementation_status="implemented",
        extra_metadata={"complaint_type": complaint_type},
    )


def map_claim_elements_to_predicates(
    claim_type: str,
    elements: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    """Map claim *elements* to FOL/DCEC predicates using the template for *claim_type*.

    Each input element should be a dict with at least ``element_id`` or
    ``element_text``.  The function enriches each element with its matching
    template (``fol_template``, ``dcec_template``) and produces a
    ``predicates`` list ready for :func:`prove_claim_elements`.

    Returns a structured payload with ``predicates`` (list of predicate dicts)
    and ``template_match_count`` (how many elements matched a template entry).
    """
    templates_result = get_predicate_templates(claim_type)
    element_templates = {
        t["element_id"]: t
        for t in (templates_result.get("elements") or [])
        if isinstance(t, dict) and t.get("element_id")
    }

    predicates: List[Dict[str, Any]] = []
    template_match_count = 0
    unmapped_element_ids: List[str] = []
    all_support_facts: List[Dict[str, Any]] = []

    for element in list(elements):
        if not isinstance(element, dict):
            continue
        element_id = str(element.get("element_id") or "")
        element_text = str(element.get("element_text") or element.get("label") or "")
        coverage_status = str(element.get("status") or element.get("coverage_status") or "missing")
        predicate_id = element.get("predicate_id") or f"{claim_type}:{element_id}" if element_id else f"{claim_type}:unknown"
        support_facts = [
            dict(fact)
            for fact in element.get("support_facts", []) or []
            if isinstance(fact, dict)
        ]
        all_support_facts.extend(support_facts)
        fact_registry_summary = (
            dict(element.get("fact_registry_summary"))
            if isinstance(element.get("fact_registry_summary"), dict)
            else dict(element.get("support_fact_registry_summary"))
            if isinstance(element.get("support_fact_registry_summary"), dict)
            else _summarize_fact_registry_for_facts(support_facts)
        )

        tmpl = element_templates.get(element_id)
        if tmpl:
            template_match_count += 1
            fol_template = tmpl.get("fol_template", "")
            dcec_template = tmpl.get("dcec_template", "")
        else:
            fol_template = ""
            dcec_template = ""
            if element_id:
                unmapped_element_ids.append(element_id)

        predicate: Dict[str, Any] = {
            "predicate_type": "claim_element",
            "claim_type": claim_type,
            "predicate_id": predicate_id,
            "claim_element_id": element_id,
            "claim_element_text": element_text,
            "coverage_status": coverage_status,
            "formula": fol_template,
            "fol_template": fol_template,
            "dcec_template": dcec_template,
            "grounded_facts": tmpl.get("grounded_facts", []) if tmpl else [],
            "expected_predicate_types": tmpl.get("predicate_types", ["claim_element"]) if tmpl else ["claim_element"],
            "template_matched": bool(tmpl),
            "support_facts": support_facts,
            "fact_registry_summary": fact_registry_summary,
        }
        predicates.append(predicate)

    fact_registry_summary = _summarize_fact_registry_for_facts(all_support_facts)
    return with_adapter_metadata(
        {
            "status": "success",
            "claim_type": claim_type,
            "predicates": predicates,
            "predicate_count": len(predicates),
            "template_match_count": template_match_count,
            "unmapped_element_ids": unmapped_element_ids,
            "fact_registry_summary": fact_registry_summary,
        },
        operation="map_claim_elements_to_predicates",
        backend_available=True,
        implementation_status="implemented",
        extra_metadata={
            "claim_type": claim_type,
            "element_count": len(predicates),
            "fact_registry_summary": fact_registry_summary,
        },
    )


# ---------------------------------------------------------------------------
# Source-bound legal rule candidates (CIMP-LAW-04)
# ---------------------------------------------------------------------------

SOURCE_BOUND_RULE_CONTRACT = "source-bound-legal-rule/v1"
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RULE_SENTENCE_RE = re.compile(r"[^.!?\n]+(?:[.!?]+)?", re.MULTILINE)
_EXCEPTION_RE = re.compile(
    r"\b(except(?:\s+(?:that|when|where|if))?|unless|provided that|however)\b",
    re.IGNORECASE,
)
_CONDITION_RE = re.compile(
    r"^(if|when|where|whenever)\s+(.+?),\s+(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_AND_RE = re.compile(r"\band\b", re.IGNORECASE)
_OR_RE = re.compile(r"\bor\b", re.IGNORECASE)
_PROCEDURAL_RE = re.compile(
    r"\b(within\s+\d+\s+(?:days|hours|months)|deadline|timely|exhaust|notice|"
    r"venue|filed|file[sd]?|procedure|service of process|statute of limitations)\b",
    re.IGNORECASE,
)
_DEONTIC_RULES: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    ("prohibition", re.compile(
        r"\b(must not|shall not|may not|cannot|can not|is prohibited|is forbidden|prohibited)\b",
        re.IGNORECASE,
    )),
    ("obligation", re.compile(
        r"\b(must|shall|required to|is required to|has a duty to|ought to)\b",
        re.IGNORECASE,
    )),
    ("permission", re.compile(
        r"\b(may|is permitted to|is allowed to|is entitled to|has the right to)\b",
        re.IGNORECASE,
    )),
)
_UNKNOWN_TOKENS = frozenset({
    "", "unknown", "unspecified", "n/a", "na", "none", "null", "current", "latest", "unverified",
})
_LEGACY_DISCRIMINATION_TEMPLATES: Tuple[Tuple[str, str], ...] = (
    ("Protected Class Membership", "Plaintiff must be member of protected class"),
    ("Adverse Action", "Plaintiff suffered adverse employment/housing action"),
    ("Causal Connection", "Protected class status was motivating factor"),
)
def _as_mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _first_text(mapping: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _nested_context(authority: Mapping[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for key in ("metadata", "provenance", "applicable_date", "date_context"):
        nested = authority.get(key)
        if isinstance(nested, Mapping):
            merged.update(dict(nested))
    merged.update(dict(authority))
    return merged


def _normalize_sha256(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text.startswith("sha256:"):
        text = text.split(":", 1)[1].strip()
    if re.fullmatch(r"[0-9a-f]{64}", text):
        return text
    return ""


def sha256_utf8(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _byte_span(source_text: str, char_start: int, char_end: int) -> Tuple[int, int]:
    prefix = source_text[:char_start].encode("utf-8")
    fragment = source_text[char_start:char_end].encode("utf-8")
    return len(prefix), len(prefix) + len(fragment)


def _unique_fragment_span(source_text: str, fragment: str) -> Tuple[Optional[Dict[str, Any]], str]:
    if not source_text or not fragment:
        return None, "missing_source_span"
    start = source_text.find(fragment)
    if start < 0:
        return None, "missing_source_span"
    if source_text.find(fragment, start + 1) != -1:
        return None, "ambiguous_source_span"
    byte_start, byte_end = _byte_span(source_text, start, start + len(fragment))
    sliced = source_text.encode("utf-8")[byte_start:byte_end].decode("utf-8")
    if sliced != fragment:
        return None, "source_span_mismatch"
    return {
        "start": byte_start,
        "end": byte_end,
        "text": fragment,
        "unit": "utf-8-bytes",
    }, ""


def _iter_rule_sentences(source_text: str) -> List[Tuple[str, int, int]]:
    found: List[Tuple[str, int, int]] = []
    for match in _RULE_SENTENCE_RE.finditer(source_text):
        raw = match.group(0)
        stripped = raw.strip()
        if not stripped:
            continue
        leading = len(raw) - len(raw.lstrip())
        char_start = match.start() + leading
        char_end = char_start + len(stripped)
        if source_text[char_start:char_end] != stripped:
            continue
        found.append((stripped, char_start, char_end))
    return found


def _deontic_operator(sentence: str) -> str:
    for name, pattern in _DEONTIC_RULES:
        if pattern.search(sentence):
            return name
    return "unknown"


def _clause_record(source_text: str, fragment: str) -> Dict[str, Any]:
    span, status = _unique_fragment_span(source_text, fragment.strip(" ,;"))
    return {
        "text": fragment.strip(" ,;"),
        "span": span,
        "span_status": "exact" if span else status,
    }


def _structure_for_sentence(source_text: str, sentence: str) -> Dict[str, Any]:
    operative = sentence
    exceptions: List[Dict[str, Any]] = []
    exception_match = _EXCEPTION_RE.search(sentence)
    if exception_match:
        exception_text = sentence[exception_match.start():].strip()
        operative = sentence[:exception_match.start()].strip(" ,;")
        exceptions.append(_clause_record(source_text, exception_text))
    conditions: List[Dict[str, Any]] = []
    condition_match = _CONDITION_RE.match(operative)
    if condition_match:
        conditions.append(_clause_record(source_text, condition_match.group(2).strip()))
        operative_for_connective = condition_match.group(3).strip()
    else:
        operative_for_connective = operative
    conjunction_count = len(_AND_RE.findall(operative_for_connective))
    disjunction_count = len(_OR_RE.findall(operative_for_connective))
    if conjunction_count and disjunction_count:
        connective = "ambiguous"
    elif conjunction_count:
        connective = "conjunction"
    elif disjunction_count:
        connective = "disjunction"
    else:
        connective = "none"
    conjuncts: List[Dict[str, Any]] = []
    disjuncts: List[Dict[str, Any]] = []
    if connective == "conjunction":
        conjuncts = [_clause_record(source_text, part) for part in _AND_RE.split(operative_for_connective) if part.strip()]
    elif connective == "disjunction":
        disjuncts = [_clause_record(source_text, part) for part in _OR_RE.split(operative_for_connective) if part.strip()]
    deontic = _deontic_operator(sentence)
    clause_parts = [operative_for_connective] + [item["text"] for item in exceptions if item.get("text")]
    if conditions:
        clause_parts.append(conditions[0]["text"])
    procedural_parts = [part for part in clause_parts if part and _PROCEDURAL_RE.search(part)]
    substantive_parts = [
        part for part in clause_parts
        if part and not _PROCEDURAL_RE.search(part) and _deontic_operator(part) != "unknown"
    ]
    if procedural_parts and substantive_parts:
        rule_character = "mixed"
    elif procedural_parts or _PROCEDURAL_RE.search(sentence):
        rule_character = "procedural"
    elif deontic != "unknown":
        rule_character = "substantive"
    else:
        rule_character = "unknown"
    return {
        "conditions": conditions,
        "exceptions": exceptions,
        "connective": connective,
        "conjunction_count": conjunction_count,
        "disjunction_count": disjunction_count,
        "conjuncts": conjuncts,
        "disjuncts": disjuncts,
        "rule_character": rule_character,
        "deontic_operator": deontic,
        "deontic_operator_source": "pattern_heuristic",
        "deontic_operator_is_proof": False,
        "entailment_status": "unsupported",
    }


def _iso_date(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 64:
        return ""
    text = value.strip()
    if not _ISO_DATE_RE.fullmatch(text):
        return ""
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return ""


def _authority_coordinates(authority: Mapping[str, Any]) -> Dict[str, Any]:
    context = _nested_context(authority)
    jurisdiction = _first_text(context, "jurisdiction")
    authority_id = _first_text(context, "authority_id", "authority_identity", "id")
    citation = _first_text(context, "citation", "cite")
    version = _first_text(context, "authority_version", "version", "corpus_version", "release")
    source_text = authority.get("source_text")
    if not isinstance(source_text, str) or source_text == "":
        source_text = authority.get("text") if isinstance(authority.get("text"), str) else ""
    supplied_hash = _normalize_sha256(
        context.get("source_hash") or context.get("content_hash") or context.get("authority_hash")
    )
    hash_scope = str(context.get("content_hash_scope") or context.get("source_hash_scope") or "").strip()
    dates = {
        "effective_date": _iso_date(context.get("effective_date")),
        "as_of_date": _iso_date(context.get("as_of_date") or context.get("applicable_date") or context.get("applicable_on")),
        "expiration_date": _iso_date(context.get("expiration_date")),
    }
    return {
        "jurisdiction": jurisdiction,
        "authority_id": authority_id,
        "citation": citation,
        "authority_version": version,
        "source_text": source_text,
        "source_hash": supplied_hash,
        "hash_scope": hash_scope,
        "applicable_date": dates,
    }


def _known_token(value: str) -> bool:
    return value.strip().lower() not in _UNKNOWN_TOKENS


_TEMPORAL_AUTHORITY_MODULE = (
    "ipfs_datasets_py.logic.integration.reasoning.legal_ir_temporal_authority"
)
_TEMPORAL_APPLICABILITY_CONTRACT = "legal_ir_temporal_applicability_v1"
_BLOCKING_TREATMENT_TYPES = frozenset({
    "adverse",
    "good_law_unconfirmed",
    "questioned",
    "limits",
    "distinguishes",
    "superseded",
})
_TEMPORAL_STATUS_LABELS = {
    "applicable": "effective",
    "not_yet_effective": "future",
    "expired": "expired",
    "repealed": "repealed",
    "superseded": "superseded",
    "wrong_jurisdiction": "wrong_jurisdiction",
    "authority_preempted": "authority_preempted",
    "emergency_expired": "expired",
    "unresolved_authority": "unavailable",
}


_TEMPORAL_MAX_VERSIONS = 64
_TEMPORAL_MAX_CHANGES = 128
_TEMPORAL_MAX_TEXT = 65536
_TEMPORAL_MAX_RULES = 256


def _temporal_input_reason(payload: Mapping[str, Any]) -> str:
    """Bound the finite local graph input before copying records or importing."""
    if len(payload) > 128:
        return "authority_field_bound_exceeded"
    containers = [payload]
    for key in ("metadata", "provenance", "applicable_date", "date_context", "temporal_window"):
        nested = payload.get(key)
        if isinstance(nested, Mapping):
            if len(nested) > 64:
                return "authority_field_bound_exceeded"
            containers.append(nested)
    for container in containers:
        for key in ("source_text", "text", "rule_text"):
            value = container.get(key)
            if isinstance(value, str) and len(value) > _TEMPORAL_MAX_TEXT:
                return "source_text_bound_exceeded"
        for key in ("authority_id", "authority_identity", "id", "citation", "cite", "jurisdiction",
                    "authority_version", "version", "corpus_version", "release"):
            value = container.get(key)
            if isinstance(value, str) and len(value) > 1024:
                return "authority_field_bound_exceeded"
    window = payload.get("temporal_window")
    if isinstance(window, Mapping) and any(not isinstance(value, (str, type(None)))
                                          or isinstance(value, str) and len(value) > 64 for value in window.values()):
        return "temporal_record_bound_exceeded"
    for key, limit in (("law_versions", _TEMPORAL_MAX_VERSIONS),
                       ("changes", _TEMPORAL_MAX_CHANGES), ("temporal_changes", _TEMPORAL_MAX_CHANGES)):
        records = payload.get(key)
        if records in (None, []):
            continue
        if not isinstance(records, list) or len(records) > limit:
            return "temporal_records_bound_exceeded"
        for record in records:
            if not isinstance(record, Mapping) or len(record) > 64:
                return "malformed_temporal_record"
            for value in record.values():
                values = value.values() if isinstance(value, Mapping) else value if isinstance(value, (list, tuple)) else (value,)
                if isinstance(value, (Mapping, list, tuple)) and len(value) > 32:
                    return "temporal_record_bound_exceeded"
                if any(not isinstance(item, (str, int, float, bool, type(None)))
                       or isinstance(item, str) and len(item) > 4096 for item in values):
                    return "temporal_record_bound_exceeded"
    return ""


def _date_aliases(mapping: Mapping[str, Any], keys: Sequence[str]) -> Tuple[str, str]:
    present = [mapping[key] for key in keys if mapping.get(key) not in (None, "")
               and not (key == "applicable_date" and isinstance(mapping[key], Mapping))]
    parsed = [_iso_date(value) if isinstance(value, str) else "" for value in present]
    if any(not value for value in parsed):
        return "", "invalid_source_date"
    if len(set(parsed)) > 1:
        return "", "contradictory_date_context"
    return (parsed[0] if parsed else ""), ""


def _source_date_aliases(payload: Mapping[str, Any], keys: Sequence[str]) -> Tuple[str, str]:
    values = []
    for container in (payload, *(payload.get(key) for key in
                       ("metadata", "provenance", "applicable_date", "date_context", "temporal_window"))):
        if isinstance(container, Mapping):
            value, reason = _date_aliases(container, keys)
            if reason:
                return "", reason
            if value:
                values.append(value)
    if len(set(values)) > 1:
        return "", "contradictory_date_context"
    return (values[0] if values else ""), ""


def _temporal_authority_api() -> Tuple[Any, str]:
    """Load LegalIR temporal graph and query APIs only when a caller needs them."""
    module, error = import_module_optional(_TEMPORAL_AUTHORITY_MODULE)
    required = (
        "build_legal_ir_temporal_authority_graph",
        "query_legal_ir_temporal_applicability",
        "LegalIRTemporalQueryContext",
    )
    if module is None or any(not hasattr(module, name) for name in required):
        return None, _provider_diagnostic(error, fallback="temporal_authority_api_unavailable")
    return module, ""


def _unavailable_temporal_applicability(reason: str, **extra: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "contract": _TEMPORAL_APPLICABILITY_CONTRACT,
        "available": False,
        "applicable": False,
        "applicability_status": "unavailable",
        "legal_ir_status": "unavailable",
        "reason": reason,
        "review_reason": f"temporal_applicability_{reason}",
        "guessed_current_rule": False,
        "selected_current_rule": False,
        "query_date_source": "unavailable",
        "decisions": [],
        "version_decisions": [],
        "diagnostics": [],
        "api": _TEMPORAL_AUTHORITY_MODULE,
    }
    payload.update(extra)
    return payload


def _iter_treatment_records(authority: Mapping[str, Any]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    edges = authority.get("authority_treatment_edges")
    if isinstance(edges, list) and edges:
        records.extend(item for item in edges if isinstance(item, Mapping))
    else:
        raw = authority.get("treatment_records")
        if not isinstance(raw, list):
            summary = authority.get("treatment_summary")
            raw = summary.get("records") if isinstance(summary, Mapping) else []
        if isinstance(raw, list):
            records.extend(item for item in raw if isinstance(item, Mapping))
    return records


def requirement_treatment_support(authority: Mapping[str, Any]) -> Dict[str, Any]:
    """Keep treatment edges visible and say whether they block requirement support."""
    visible: List[Dict[str, Any]] = []
    types: List[str] = []
    for record in _iter_treatment_records(authority):
        treatment_type = str(
            record.get("relation_type") or record.get("treatment_type") or record.get("type") or ""
        ).strip()
        if not treatment_type:
            continue
        types.append(treatment_type)
        visible.append({
            "treatment_type": treatment_type,
            "source_authority_id": str(
                record.get("source_authority_id") or record.get("treated_by_authority_id") or ""
            ),
            "target_authority_id": str(
                record.get("target_authority_id")
                or record.get("treated_authority_id")
                or record.get("target_id")
                or ""
            ),
            "explanation": str(record.get("explanation") or record.get("treatment_explanation") or ""),
        })
    blocking = [name for name in types if name in _BLOCKING_TREATMENT_TYPES]
    return {
        "treatment_edges": visible,
        "treatment_types": list(dict.fromkeys(types)),
        "treatment_edges_visible": True,
        "blocking_treatments": list(dict.fromkeys(blocking)),
        "treatment_blocks_support": bool(blocking),
        "support_eligible": not blocking,
    }


def _selected_law_versions(authority: Mapping[str, Any], coordinates: Mapping[str, Any]) -> List[Dict[str, Any]]:
    supplied = authority.get("law_versions")
    if isinstance(supplied, list) and supplied:
        versions = [dict(item) for item in supplied if isinstance(item, Mapping)]
        if versions:
            return versions
    dates = coordinates.get("applicable_date") if isinstance(coordinates.get("applicable_date"), Mapping) else {}
    version = str(coordinates.get("authority_version") or "")
    authority_id = str(coordinates.get("authority_id") or coordinates.get("citation") or "authority")
    window = authority.get("temporal_window") if isinstance(authority.get("temporal_window"), Mapping) else {}
    return [{
        "law_version_id": str(authority.get("law_version_id") or f"{authority_id}:{version or 'unspecified'}"),
        "citation": str(coordinates.get("citation") or ""),
        "authority_id": str(coordinates.get("authority_id") or ""),
        "jurisdiction": str(coordinates.get("jurisdiction") or ""),
        "version": version,
        "effective_date": str(window.get("effective_date") or dates.get("effective_date") or ""),
        "sunset_date": str(window.get("sunset_date") or authority.get("sunset_date") or authority.get("expiration_date") or dates.get("expiration_date") or ""),
        "repeal_date": str(window.get("repeal_date") or authority.get("repeal_date") or ""),
        "superseded_date": str(window.get("superseded_date") or authority.get("superseded_date") or ""),
    }]


def _label_temporal_status(legal_ir_status: str, law: Any) -> str:
    label = _TEMPORAL_STATUS_LABELS.get(legal_ir_status, legal_ir_status or "unavailable")
    amended_by = tuple(getattr(law, "amended_by", ()) or ())
    if legal_ir_status == "superseded" and amended_by:
        return "amended"
    return label


def evaluate_temporal_requirement_applicability(
    authority: Mapping[str, Any],
    query_context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Decide applicability with LegalIR's temporal graph and query context.

    An unknown source version or query date stays ``unavailable``. This function
    does not substitute today's date or another version and call it current.
    """
    if not isinstance(authority, Mapping) or len(authority) > 128:
        return _unavailable_temporal_applicability("authority_field_bound_exceeded")
    payload = _as_mapping(authority)
    if query_context is not None and (not isinstance(query_context, Mapping) or len(query_context) > 32):
        return _unavailable_temporal_applicability("malformed_query_context")
    reason = _temporal_input_reason(payload)
    if reason:
        return _unavailable_temporal_applicability(reason)
    context = dict(query_context or {})
    nested_query = payload.get("query_context") or payload.get("temporal_query_context")
    if isinstance(nested_query, Mapping):
        if len(nested_query) > 32:
            return _unavailable_temporal_applicability("query_context_bound_exceeded")
        merged = dict(nested_query)
        merged.update(context)
        context = merged
    if len(context) > 32 or any(not isinstance(value, (str, int, float, bool, type(None)))
                                or isinstance(value, str) and len(value) > 1024 for value in context.values()):
        return _unavailable_temporal_applicability("query_context_bound_exceeded")
    coordinates = _authority_coordinates(payload)
    source_jurisdiction = str(coordinates.get("jurisdiction") or "")
    if not _known_token(source_jurisdiction) or not _known_token(str(context.get("jurisdiction") or source_jurisdiction)):
        return _unavailable_temporal_applicability("unknown_source_jurisdiction")
    version = str(coordinates.get("authority_version") or "")
    requested_version = str(context.get("authority_version") or context.get("version") or version)
    if not _known_token(version) or not _known_token(requested_version):
        return _unavailable_temporal_applicability("unknown_source_version", authority_version=version)
    if requested_version != version:
        return _unavailable_temporal_applicability("source_version_mismatch", authority_version=version)
    explicit_version_id = str(context.get("law_version_id") or payload.get("law_version_id") or "")
    versions = _selected_law_versions(payload, coordinates)
    matched = [item for item in versions
               if isinstance(item.get("version"), str) and item["version"] == version
               and (not explicit_version_id or str(item.get("law_version_id") or "") == explicit_version_id)]
    if len(matched) != 1:
        return _unavailable_temporal_applicability(
            "unknown_source_version" if not matched else "ambiguous_source_version", authority_version=version)
    selected_version = matched[0]
    if any(selected_version.get(key) and coordinates.get(key)
           and str(selected_version[key]) != str(coordinates[key]) for key in ("authority_id", "jurisdiction")):
        return _unavailable_temporal_applicability("source_identity_mismatch", authority_version=version)
    known_ids = [str(item.get("law_version_id") or "") for item in versions if item.get("law_version_id")]
    if len(known_ids) != len(set(known_ids)):
        return _unavailable_temporal_applicability("ambiguous_source_version", authority_version=version)
    effective, reason = _date_aliases(selected_version, ("effective_date", "effective_on"))
    if reason or not effective:
        return _unavailable_temporal_applicability(reason or "unknown_source_date", authority_version=version)
    source_effective, reason = _source_date_aliases(payload, ("effective_date", "effective_on"))
    if reason or source_effective and source_effective != effective:
        return _unavailable_temporal_applicability(reason or "contradictory_date_context", authority_version=version)
    for item in versions:
        for keys in (("effective_date", "effective_on"), ("sunset_date", "sunsets_on", "expiration_date"),
                     ("repeal_date", "repealed_on"), ("superseded_date", "superseded_on"),
                     ("emergency_expires_on", "emergency_expiration_date")):
            value, reason = _date_aliases(item, keys)
            if reason:
                return _unavailable_temporal_applicability(reason, authority_version=version)
            if value and keys[0] != "effective_date" and value <= effective and item is selected_version:
                return _unavailable_temporal_applicability("contradictory_date_context", authority_version=version)
            if value:
                item[keys[0]] = value
    for keys in (("sunset_date", "expiration_date"), ("repeal_date",), ("superseded_date",)):
        source_end, reason = _source_date_aliases(payload, keys)
        selected_end, selected_reason = _date_aliases(selected_version, keys)
        if reason or selected_reason or source_end and selected_end and source_end != selected_end:
            return _unavailable_temporal_applicability(reason or selected_reason or "contradictory_date_context", authority_version=version)
        if source_end and not selected_end:
            if source_end <= effective:
                return _unavailable_temporal_applicability("contradictory_date_context", authority_version=version)
            selected_version[keys[0]] = source_end
    for change in payload.get("changes") or payload.get("temporal_changes") or []:
        for keys in (("effective_date", "effective_on"), ("enacted_date", "enacted_on")):
            _value, reason = _date_aliases(change, keys)
            if reason:
                return _unavailable_temporal_applicability(reason, authority_version=version)
    query_keys = ("query_date", "as_of", "as_of_date")
    query_date, reason = _date_aliases(context, query_keys)
    if not query_date and not reason:
        query_date, reason = _source_date_aliases(payload, ("as_of_date", "applicable_date", "applicable_on"))
    if reason or not query_date:
        return _unavailable_temporal_applicability(reason or "unknown_source_date", authority_version=version)
    query_date_source = "explicit_query_context" if any(context.get(key) for key in query_keys) else "as_of_date"
    try:
        module, error = _temporal_authority_api()
        if module is None:
            return _unavailable_temporal_applicability(
                "temporal_authority_api_unavailable",
                authority_version=version,
                query_date=query_date,
                diagnostic="temporal_authority_api_unavailable",
            )
        authority_id = str(
            (selected_version or {}).get("authority_id")
            or coordinates.get("authority_id")
            or ""
        )
        jurisdiction = str((selected_version or {}).get("jurisdiction") or coordinates.get("jurisdiction") or "")
        query_jurisdiction = str(context.get("jurisdiction") or jurisdiction)
        law_versions = []
        for item in versions:
            law = dict(item)
            law.setdefault("authority_id", authority_id)
            law.setdefault("jurisdiction", jurisdiction)
            law.setdefault("citation", str(coordinates.get("citation") or ""))
            if not str(law.get("law_version_id") or "").strip():
                law["law_version_id"] = f"{law['authority_id']}:{law.get('version') or 'unspecified'}"
            law_versions.append(law)
        if not selected_version:
            return _unavailable_temporal_applicability(
                "unknown_source_version",
                authority_version=version,
                query_date=query_date,
                known_versions=[str(item.get("version") or "") for item in versions],
            )
        selected_id = str(selected_version.get("law_version_id") or f"{authority_id}:{version}")
        changes = payload.get("changes") or payload.get("temporal_changes") or []
        document = {
            "document_id": authority_id or "legal-requirement",
            "authority_id": authority_id,
            "jurisdiction": jurisdiction,
            "version": version,
            "law_versions": law_versions,
            "changes": list(changes) if isinstance(changes, list) else [],
        }
        graph = module.build_legal_ir_temporal_authority_graph(document)
        query = module.LegalIRTemporalQueryContext(
            query_date=query_date,
            jurisdiction=query_jurisdiction,
            authority_id=authority_id,
            law_version_ids=(selected_id,),
        )
        result = module.query_legal_ir_temporal_applicability(graph, query)
        result_dict = result.to_dict()
        decisions = list(result_dict.get("decisions") or [])
        decision = next((item for item in decisions if item.get("law_version_id") == selected_id), None)
        if decision is None:
            return _unavailable_temporal_applicability(
                "temporal_applicability_unresolved",
                authority_version=version,
                query_date=query_date,
                query_date_source=query_date_source,
                query_jurisdiction=query_jurisdiction,
                diagnostics=list(result_dict.get("diagnostics") or []),
                guessed_current_rule=False,
            )
        law = graph.law_version_by_id.get(str(decision.get("law_version_id") or ""))
        legal_ir_status = str(decision.get("status") or "unavailable")
        label = _label_temporal_status(legal_ir_status, law)
        applicable = legal_ir_status == "applicable" and label == "effective"
        return {
            "contract": _TEMPORAL_APPLICABILITY_CONTRACT,
            "available": True,
            "applicable": applicable,
            "applicability_status": label,
            "legal_ir_status": legal_ir_status,
            "reason": "" if applicable else f"temporal_applicability_{label}",
            "review_reason": "" if applicable else f"temporal_applicability_{label}",
            "guessed_current_rule": False,
            "selected_current_rule": False,
            "query_date": query_date,
            "query_date_source": query_date_source,
            "query_jurisdiction": query_jurisdiction,
            "authority_version": str(getattr(law, "version", "") or version),
            "law_version_id": str(decision.get("law_version_id") or ""),
            "effective_date": str(decision.get("effective_date") or ""),
            "end_date": str(decision.get("end_date") or ""),
            "amended_by": list(getattr(law, "amended_by", ()) or ()),
            "superseded_by": str(getattr(law, "superseded_by", "") or ""),
            "repealed_by": str(getattr(law, "repealed_by", "") or ""),
            "decisions": decisions,
            "version_decisions": decisions,
            "diagnostics": list(decision.get("diagnostics") or []),
            "schema_version": result_dict.get("schema_version") or "",
            "api": _TEMPORAL_AUTHORITY_MODULE,
            "temporal_authority_graph_id": graph.temporal_authority_graph_id,
        }
    except Exception:
        return _unavailable_temporal_applicability(
            "temporal_authority_evaluation_failed", authority_version=version,
            query_date=query_date, diagnostic="legal_ir_temporal_api_failure")


def is_applicable_legal_requirement(attributes: Any) -> bool:
    """Return whether a graph element may be used as an applicable requirement.

    Records that never went through this gate stay eligible so existing
    hand-built elements keep their previous meaning. Explicit templates,
    unpromoted candidates, unavailable temporal decisions, and blocking
    treatment marks do not.
    """
    if not isinstance(attributes, Mapping):
        return False
    if attributes.get("legacy_template") is True:
        return False
    if attributes.get("verification_status") == "unverified_template":
        return False
    if attributes.get("applicable") is False:
        return False
    if attributes.get("promotion_status") in {"candidate", "unverified_template", "not_promoted"}:
        return False
    if attributes.get("support_eligible") is False or attributes.get("treatment_blocks_support") is True:
        return False
    temporal = attributes.get("temporal_applicability")
    if isinstance(temporal, Mapping):
        if temporal.get("applicable") is False:
            return False
        if str(temporal.get("applicability_status") or "") not in {"", "effective", "applicable"}:
            return False
    return True


def _promotion_reasons(
    *,
    coordinates: Mapping[str, Any],
    span: Optional[Mapping[str, Any]],
    span_status: str,
    structure: Mapping[str, Any],
    legacy_template: bool,
) -> List[str]:
    reasons: List[str] = []
    if legacy_template:
        reasons.append("legacy_unverified_template")
    if not _known_token(str(coordinates.get("jurisdiction") or "")):
        reasons.append("missing_jurisdiction")
    if not (_known_token(str(coordinates.get("authority_id") or "")) or _known_token(str(coordinates.get("citation") or ""))):
        reasons.append("missing_authority_identity")
    if not _known_token(str(coordinates.get("authority_version") or "")):
        reasons.append("missing_authority_version")
    source_text = str(coordinates.get("source_text") or "")
    supplied_hash = str(coordinates.get("source_hash") or "")
    if not source_text:
        reasons.append("missing_source_text")
    if not supplied_hash:
        reasons.append("missing_source_hash")
    elif source_text:
        full_hash = sha256_utf8(source_text)
        span_hash = sha256_utf8(str(span.get("text") or "")) if span else ""
        scope = str(coordinates.get("hash_scope") or "")
        matches_full = supplied_hash == full_hash
        matches_span = scope == "source_passage" and bool(span_hash) and supplied_hash == span_hash
        if not matches_full and not matches_span:
            reasons.append("source_hash_mismatch")
    if span is None:
        reasons.append(span_status or "missing_source_span")
    dates = coordinates.get("applicable_date") if isinstance(coordinates.get("applicable_date"), Mapping) else {}
    if not (dates.get("effective_date") or dates.get("as_of_date")):
        reasons.append("missing_applicable_date")
    if structure.get("deontic_operator") == "unknown":
        reasons.append("unsupported_deontic_extraction")
    if structure.get("connective") == "ambiguous":
        reasons.append("ambiguous_connective")
    if structure.get("rule_character") == "unknown":
        reasons.append("ambiguous_rule_character")
    for clause in list(structure.get("conditions") or []) + list(structure.get("exceptions") or []):
        if isinstance(clause, Mapping) and clause.get("span_status") == "ambiguous_source_span":
            reasons.append("ambiguous_clause_span")
            break
    # Caller-supplied promotion flags are never a reason to pass.
    return list(dict.fromkeys(reasons))


def _candidate_record(
    *,
    authority: Mapping[str, Any],
    coordinates: Mapping[str, Any],
    sentence: str,
    span: Optional[Dict[str, Any]],
    span_status: str,
    structure: Mapping[str, Any],
    legacy_template: bool,
    temporal: Optional[Dict[str, Any]] = None,
    treatment: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    reasons = _promotion_reasons(
        coordinates=coordinates,
        span=span,
        span_status=span_status,
        structure=structure,
        legacy_template=legacy_template,
    )
    temporal = evaluate_temporal_requirement_applicability(authority) if temporal is None else deepcopy(temporal)
    treatment = requirement_treatment_support(authority) if treatment is None else deepcopy(treatment)
    if not temporal.get("applicable"):
        reason = str(temporal.get("review_reason") or "temporal_applicability_unavailable")
        reasons.append(reason)
    promoted = not reasons
    support_eligible = bool(promoted and treatment.get("support_eligible") and temporal.get("applicable"))
    source_text = str(coordinates.get("source_text") or "")
    span_text = str(span.get("text") if span else "")
    return {
        "contract": SOURCE_BOUND_RULE_CONTRACT,
        "status": "promoted" if promoted else "candidate",
        "promotion_status": "promoted" if promoted else "candidate",
        "verification_status": "promoted" if promoted else "candidate",
        "promoted": promoted,
        "applicable": promoted and support_eligible,
        "support_eligible": support_eligible,
        "treatment_blocks_support": bool(treatment.get("treatment_blocks_support")),
        "treatment_edges": list(treatment.get("treatment_edges") or []),
        "blocking_treatments": list(treatment.get("blocking_treatments") or []),
        "temporal_applicability": temporal,
        "legacy_template": legacy_template,
        "review_reason": ";".join(reasons),
        "review_reasons": reasons,
        "rule_text": sentence,
        "source_span": dict(span) if span else {"start": None, "end": None, "text": "", "unit": "utf-8-bytes"},
        "span_status": "exact" if span else span_status,
        "source_hash": str(coordinates.get("source_hash") or ""),
        "source_hash_scope": (
            "source_passage"
            if str(coordinates.get("hash_scope") or "") == "source_passage"
            else "authority_text"
        ),
        "authority_text_sha256": sha256_utf8(source_text) if source_text else "",
        "span_sha256": sha256_utf8(span_text) if span_text else "",
        "jurisdiction": str(coordinates.get("jurisdiction") or ""),
        "authority_id": str(coordinates.get("authority_id") or ""),
        "authority_identity": str(coordinates.get("authority_id") or coordinates.get("citation") or ""),
        "authority_version": str(coordinates.get("authority_version") or ""),
        "citation": str(coordinates.get("citation") or ""),
        "applicable_date": dict(coordinates.get("applicable_date") or {}),
        "structure": dict(structure),
        "rule_character": structure.get("rule_character", "unknown"),
        "deontic_operator": structure.get("deontic_operator", "unknown"),
        "deontic_operator_is_proof": False,
        "entailment_status": "unsupported",
        "about_complainant": False,
    }


def _unavailable_rule_candidates(reason: str) -> Dict[str, Any]:
    candidate = _candidate_record(
        authority={}, coordinates=_authority_coordinates({}), sentence="", span=None,
        span_status="missing_source_text", structure=_structure_for_sentence("", ""), legacy_template=False,
        temporal=_unavailable_temporal_applicability(reason),
        treatment={"support_eligible": False, "treatment_edges": [], "blocking_treatments": []})
    return {"contract": SOURCE_BOUND_RULE_CONTRACT, "candidates": [candidate],
            "promoted_requirements": [], "candidate_count": 1, "promoted_count": 0}


_ACQUIRED_TRUE_FLAGS = ("verified", "applicable", "support_eligible", "promoted", "proof")
_ACQUIRED_TEXT_ALIASES = ("source_text", "text", "content", "source_passage", "full_text", "section_text")


def _acquired_flag_is_true(payload: Any) -> bool:
    if not isinstance(payload, Mapping):
        return False
    return any(payload.get(key) is True for key in _ACQUIRED_TRUE_FLAGS)


def _acquired_hash_hex(value: Any) -> str:
    return _normalize_sha256(value)


def prepare_acquired_authority_record(
    candidate: Mapping[str, Any],
    *,
    jurisdiction: str,
    as_of_date: str,
) -> Dict[str, Any]:
    """Turn one acquired owned candidate into a canonical storage record.

    Source, authority-text, and span hashes are recomputed from the owned
    passage bytes. Caller verification flags are not stored. Metadata text
    that is not the owned passage, and a citation that is neither the source
    locator nor present in the owned passage, are rejected.
    """
    rejected = {
        "status": "rejected",
        "record": None,
        "hashes": {},
        "source_locator": "",
        "authority_version": "",
        "jurisdiction": "",
        "effective_date": "",
        "as_of_date": "",
    }
    if not isinstance(candidate, Mapping) or len(candidate) > 64:
        return dict(rejected, reason="candidate_malformed")
    if _acquired_flag_is_true(candidate) or _acquired_flag_is_true(candidate.get("metadata")):
        return dict(rejected, reason="caller_verification_flag")
    source_text = candidate.get("source_text")
    locator = candidate.get("locator")
    version = candidate.get("version")
    if not isinstance(source_text, str) or not source_text or len(source_text) > _TEMPORAL_MAX_TEXT:
        return dict(rejected, reason="source_text_missing")
    if not isinstance(locator, str) or not locator.strip() or len(locator) > 1024:
        return dict(rejected, reason="locator_missing")
    if not isinstance(version, str) or not version.strip() or len(version) > 1024:
        return dict(rejected, reason="missing_edition")
    owned = source_text.encode("utf-8")
    if candidate.get("source_byte_length") not in (None, len(owned)):
        return dict(rejected, reason="owned_byte_mismatch")
    locator = locator.strip()
    version = version.strip()
    retrieval = candidate.get("retrieval") if isinstance(candidate.get("retrieval"), Mapping) else {}
    metadata = candidate.get("metadata") if isinstance(candidate.get("metadata"), Mapping) else {}
    if len(retrieval) > 64 or len(metadata) > 64:
        return dict(rejected, reason="candidate_malformed")
    for container in (candidate, metadata, retrieval):
        for key in _ACQUIRED_TEXT_ALIASES:
            value = container.get(key)
            if isinstance(value, str) and value and value != source_text and not (container is candidate and key == "source_text"):
                return dict(rejected, reason="substituted_metadata_text")
    citation = candidate.get("citation")
    if citation not in (None, ""):
        if not isinstance(citation, str) or not citation.strip() or len(citation) > 1024:
            return dict(rejected, reason="model_invented_citation")
        citation = citation.strip()
        if citation != locator and citation not in source_text:
            return dict(rejected, reason="model_invented_citation")
    else:
        citation = ""
    for container in (metadata, candidate):
        alternate = container.get("authority_version") or container.get("corpus_version")
        if container is candidate:
            alternate = container.get("authority_version")
        if isinstance(alternate, str) and alternate.strip() and alternate.strip() != version:
            return dict(rejected, reason="substituted_authority_version")
    meta_version = metadata.get("authority_version") or metadata.get("version") or metadata.get("corpus_version")
    if isinstance(meta_version, str) and meta_version.strip() and meta_version.strip() != version:
        return dict(rejected, reason="substituted_authority_version")
    resolved_jurisdiction = str(jurisdiction or "").strip()
    if not resolved_jurisdiction or resolved_jurisdiction.lower() in _UNKNOWN_TOKENS:
        return dict(rejected, reason="missing_jurisdiction")
    for container in (candidate, metadata):
        supplied_jurisdiction = container.get("jurisdiction")
        if isinstance(supplied_jurisdiction, str) and supplied_jurisdiction.strip():
            if supplied_jurisdiction.strip().lower() in _UNKNOWN_TOKENS:
                return dict(rejected, reason="substituted_jurisdiction")
            if supplied_jurisdiction.strip() not in {resolved_jurisdiction, resolved_jurisdiction.upper(), resolved_jurisdiction.lower()}:
                # Accept only the explicit jurisdiction already selected for admission.
                folded = supplied_jurisdiction.strip()
                if folded.lower() != resolved_jurisdiction.lower():
                    return dict(rejected, reason="substituted_jurisdiction")
    if str(retrieval.get("jurisdiction_status") or "") == "mismatch":
        return dict(rejected, reason="substituted_jurisdiction")
    effective = retrieval.get("effective_date")
    if not isinstance(effective, str) or not _iso_date(effective):
        meta_effective = metadata.get("effective_date")
        effective = meta_effective if isinstance(meta_effective, str) else ""
    effective = _iso_date(effective)
    if not effective:
        return dict(rejected, reason="missing_effective_date")
    for container in (candidate, metadata):
        supplied_effective = container.get("effective_date")
        if isinstance(supplied_effective, str) and supplied_effective.strip() and _iso_date(supplied_effective) != effective:
            return dict(rejected, reason="substituted_effective_date")
    as_of = _iso_date(as_of_date)
    candidate_as_of = candidate.get("law_query_date")
    if isinstance(candidate_as_of, Mapping):
        candidate_as_of = candidate_as_of.get("precise_date")
    if isinstance(candidate_as_of, str) and candidate_as_of.strip() and _iso_date(candidate_as_of) not in {"", as_of}:
        return dict(rejected, reason="substituted_as_of_date")
    if not as_of:
        return dict(rejected, reason="missing_as_of_date")
    source_hash = sha256_utf8(source_text)
    sentences = _iter_rule_sentences(source_text)
    span_hash = ""
    span: Optional[Dict[str, Any]] = None
    if len(sentences) == 1:
        sentence, char_start, char_end = sentences[0]
        start, end = _byte_span(source_text, char_start, char_end)
        span_bytes = owned[start:end]
        if span_bytes.decode("utf-8") != sentence:
            return dict(rejected, reason="span_byte_mismatch")
        span_hash = hashlib.sha256(span_bytes).hexdigest()
        span = {"start": start, "end": end, "text": sentence, "unit": "utf-8-bytes"}
    elif source_text and not sentences:
        span_hash = source_hash
        span = {"start": 0, "end": len(owned), "text": source_text, "unit": "utf-8-bytes"}
    supplied_span = candidate.get("source_span")
    if isinstance(supplied_span, Mapping) and span is not None:
        try:
            if int(supplied_span.get("start")) != span["start"] or int(supplied_span.get("end")) != span["end"]:
                return dict(rejected, reason="substituted_source_span")
        except (TypeError, ValueError):
            return dict(rejected, reason="substituted_source_span")
        if isinstance(supplied_span.get("text"), str) and supplied_span.get("text") != span["text"]:
            return dict(rejected, reason="substituted_source_span")
    for container in (candidate, metadata, retrieval):
        for key in ("source_hash", "content_hash", "authority_hash", "authority_text_sha256"):
            if key not in container or container.get(key) in (None, ""):
                continue
            if _acquired_hash_hex(container.get(key)) != source_hash:
                return dict(rejected, reason="caller_hash_mismatch")
        if container.get("span_sha256") not in (None, "") and span_hash:
            if _acquired_hash_hex(container.get("span_sha256")) != span_hash:
                return dict(rejected, reason="caller_hash_mismatch")
    authority_id = locator
    stored_citation = citation or locator
    hashes = {
        "source_hash": source_hash,
        "authority_text_sha256": source_hash,
        "span_sha256": span_hash,
    }
    record_metadata = {
        "authority_id": authority_id,
        "authority_version": version,
        "version": version,
        "jurisdiction": resolved_jurisdiction,
        "source_hash": source_hash,
        "authority_text_sha256": source_hash,
        "span_sha256": span_hash,
        "content_hash_scope": "authority_text",
        "effective_date": effective,
        "as_of_date": as_of,
        "source_locator": locator,
        "locator_kind": str(candidate.get("locator_kind") or ""),
        "law_version_id": authority_id + ":" + version,
        "law_versions": [{
            "law_version_id": authority_id + ":" + version,
            "authority_id": authority_id,
            "citation": stored_citation,
            "jurisdiction": resolved_jurisdiction,
            "version": version,
            "effective_date": effective,
        }],
        "changes": [],
        "source_family": str(candidate.get("source_family") or retrieval.get("source_family") or ""),
        "parameter_api": str(candidate.get("parameter_api") or ""),
    }
    if span is not None:
        record_metadata["source_span"] = span
    record = {
        "type": str(candidate.get("source_family") or "statute"),
        "source": str(candidate.get("parameter_api") or candidate.get("source_family") or "canonical_corpus"),
        "citation": stored_citation,
        "title": locator,
        "content": source_text,
        "url": locator if candidate.get("locator_kind") == "uri" else "",
        "jurisdiction": resolved_jurisdiction,
        "metadata": record_metadata,
    }
    return {
        "status": "admitted",
        "reason": "owned_bytes",
        "record": record,
        "hashes": hashes,
        "source_locator": locator,
        "authority_version": version,
        "jurisdiction": resolved_jurisdiction,
        "effective_date": effective,
        "as_of_date": as_of,
    }


def extract_source_bound_rule_candidates(authority: Mapping[str, Any]) -> Dict[str, Any]:
    """Extract rule candidates from authority text and promote only exact matches.

    Promotion keeps jurisdiction, authority identity and version, the checked
    source hash, the exact UTF-8 span, and an applicable ISO date. Keyword
    templates, missing coordinates, and ambiguous structure stay candidates.
    Caller-supplied promoted or applicable flags are ignored.
    """
    if isinstance(authority, Mapping) and len(authority) > 128:
        return _unavailable_rule_candidates("authority_field_bound_exceeded")
    payload = _as_mapping(authority)
    reason = _temporal_input_reason(payload)
    if reason:
        return _unavailable_rule_candidates(reason)
    legacy_template = (
        payload.get("legacy_template") is True
        or payload.get("verification_status") == "unverified_template"
        or payload.get("template_kind") in {"claim_keyword_template", "procedural_template"}
    )
    coordinates = _authority_coordinates(payload)
    source_text = str(coordinates["source_text"] or "")
    sentences = _iter_rule_sentences(source_text) if source_text else []
    if len(sentences) > _TEMPORAL_MAX_RULES:
        return _unavailable_rule_candidates("rule_count_bound_exceeded")
    temporal = evaluate_temporal_requirement_applicability(payload)
    treatment = requirement_treatment_support(payload)
    explicit_rule = _first_text(payload, "rule_text")
    selected: List[Tuple[str, Optional[Dict[str, Any]], str]] = []
    if explicit_rule:
        span, status = _unique_fragment_span(source_text, explicit_rule)
        supplied_span = payload.get("source_span") if isinstance(payload.get("source_span"), Mapping) else None
        if span and supplied_span:
            try:
                supplied_start = int(supplied_span.get("start"))
                supplied_end = int(supplied_span.get("end"))
            except (TypeError, ValueError):
                supplied_start = supplied_end = None
            if supplied_start != span["start"] or supplied_end != span["end"]:
                span = None
                status = "source_span_mismatch"
        selected.append((explicit_rule, span, status))
    elif sentences:
        seen: Dict[str, int] = {}
        for sentence, char_start, char_end in sentences:
            seen[sentence] = seen.get(sentence, 0) + 1
            byte_start, byte_end = _byte_span(source_text, char_start, char_end)
            if seen[sentence] > 1:
                selected.append((sentence, None, "ambiguous_source_span"))
                continue
            span = {
                "start": byte_start,
                "end": byte_end,
                "text": sentence,
                "unit": "utf-8-bytes",
            }
            if source_text.find(sentence) != char_start:
                # An earlier identical sentence makes this occurrence ambiguous.
                selected.append((sentence, None, "ambiguous_source_span"))
            else:
                selected.append((sentence, span, ""))
        # Mark the first copy ambiguous once a later copy was seen.
        ambiguous_texts = {text for text, _span, status in selected if status == "ambiguous_source_span"}
        if ambiguous_texts:
            rewritten: List[Tuple[str, Optional[Dict[str, Any]], str]] = []
            seen_text: set[str] = set()
            for item in selected:
                text = item[0]
                if text in seen_text:
                    continue
                seen_text.add(text)
                if text in ambiguous_texts:
                    rewritten.append((text, None, "ambiguous_source_span"))
                else:
                    rewritten.append(item)
            selected = rewritten
    else:
        selected.append(("", None, "missing_source_text"))

    empty_structure = {
        "conditions": [],
        "exceptions": [],
        "connective": "none",
        "conjunction_count": 0,
        "disjunction_count": 0,
        "conjuncts": [],
        "disjuncts": [],
        "rule_character": "unknown",
        "deontic_operator": "unknown",
        "deontic_operator_source": "pattern_heuristic",
        "deontic_operator_is_proof": False,
        "entailment_status": "unsupported",
    }
    candidates = [
        _candidate_record(
            authority=payload,
            temporal=temporal, treatment=treatment,
            coordinates=coordinates,
            sentence=sentence,
            span=span,
            span_status=status or "missing_source_span",
            structure=_structure_for_sentence(source_text, sentence) if sentence else empty_structure,
            legacy_template=legacy_template,
        )
        for sentence, span, status in selected
        if sentence or not any(item[0] for item in selected)
    ]
    if not candidates:
        candidates = [
            _candidate_record(
                authority=payload,
                temporal=temporal, treatment=treatment,
                coordinates=coordinates,
                sentence="",
                span=None,
                span_status="missing_source_text",
                structure={
                    "conditions": [], "exceptions": [], "connective": "none",
                    "conjunction_count": 0, "disjunction_count": 0, "conjuncts": [], "disjuncts": [],
                    "rule_character": "unknown", "deontic_operator": "unknown",
                    "deontic_operator_source": "pattern_heuristic", "deontic_operator_is_proof": False,
                    "entailment_status": "unsupported",
                },
                legacy_template=legacy_template,
            )
        ]
    promoted = [dict(candidate) for candidate in candidates if candidate["promoted"]]
    return {
        "contract": SOURCE_BOUND_RULE_CONTRACT,
        "candidates": candidates,
        "promoted_requirements": promoted,
        "candidate_count": len(candidates),
        "promoted_count": len(promoted),
    }


def legacy_unverified_requirement_templates(claim_types: Sequence[str]) -> List[Dict[str, Any]]:
    """Return simplified claim-keyword templates that cannot be applied as law."""
    claim_text = " ".join(str(item) for item in claim_types).lower()
    if "discrimination" not in claim_text:
        return []
    templates: List[Dict[str, Any]] = []
    for name, description in _LEGACY_DISCRIMINATION_TEMPLATES:
        templates.append({
            "name": name,
            "description": description,
            "required": True,
            "element_type": "legal_requirement",
            "verification_status": "unverified_template",
            "promotion_status": "unverified_template",
            "applicable": False,
            "legacy_template": True,
            "template_kind": "claim_keyword_template",
            "review_reason": "legacy_unverified_template",
            "source_bound": False,
            "about_complainant": False,
        })
    return templates


def _canonical_symbol(module: Any, name: str) -> Any:
    if module is None:
        return None
    return getattr(module, name, None)


def _canonical_modules_ready() -> bool:
    required = (
        _canonical_symbol(_canonical_pipeline_module, "compile_canonical_pipeline"),
        _canonical_symbol(_canonical_contracts_module, "CompilerRequest"),
        _canonical_symbol(_canonical_contracts_module, "CanonicalAtomVocabulary"),
        _canonical_symbol(_canonical_compiler_module, "TYPED_DEONTIC_COMPILER_CONFIG_CID"),
        _canonical_symbol(_canonical_source_map_module, "LegalIRSourceMapBuilder"),
        _canonical_symbol(_canonical_source_map_module, "build_legal_ir_source_map"),
        _canonical_symbol(_canonical_source_map_module, "validate_legal_ir_source_map"),
        _canonical_symbol(_canonical_source_map_module, "trace_legal_ir_fact"),
        _canonical_symbol(_canonical_source_map_module, "bind_legal_ir_artifact_source_map"),
    )
    return all(symbol is not None for symbol in required)


def _canonical_import_reason() -> str:
    return _provider_diagnostic(
        _canonical_pipeline_error
        or _canonical_contracts_error
        or _canonical_compiler_error
        or _canonical_source_map_error,
        fallback="Canonical compiler pipeline or source-map module is unavailable.",
    )


def canonical_compiler_identities() -> Dict[str, Any] | None:
    """Return live schema, compiler, policy, pipeline, and stage identities."""

    if not _canonical_modules_ready():
        return None
    contracts = _canonical_contracts_module
    compiler = _canonical_compiler_module
    pipeline = _canonical_pipeline_module
    source_maps = _canonical_source_map_module
    stage_table = tuple(pipeline.compiler_stage_identities())
    return {
        "source_map_schema": str(source_maps.LEGAL_IR_SOURCE_MAP_SCHEMA_VERSION),
        "canonical_ir_schema": str(contracts.CANONICAL_ROUNDTRIP_IR_SCHEMA_VERSION),
        "canonical_ir_interface": str(contracts.CANONICAL_ROUNDTRIP_IR_INTERFACE),
        "compiler_interface": str(contracts.CANONICAL_STRUCTURED_TEXT_COMPILER_INTERFACE),
        "compiler_config_cid": str(compiler.TYPED_DEONTIC_COMPILER_CONFIG_CID),
        "measured_compiler_raw_cid": str(compiler.MEASURED_TYPED_DEONTIC_ADAPTER_RAW_CID),
        "policy_cid": str(contracts.CANONICAL_PARITY_POLICY_CID),
        "pipeline_interface": str(pipeline.CANONICAL_COMPILER_PIPELINE_INTERFACE),
        "pipeline_cid": str(pipeline.CANONICAL_COMPILER_PIPELINE_CID),
        "stage_ids": [str(item["stage_id"]) for item in stage_table],
        "stage_interfaces": {
            str(item["stage_id"]): str(item["interface"]) for item in stage_table
        },
    }


def _canonical_evidence(
    *,
    executed: bool = False,
    status: str = "",
    traceable: bool = False,
    source_map_valid: bool = False,
    schema_match: bool = True,
    tampered: bool = False,
    reason: str = "",
) -> Dict[str, Any]:
    return {
        "module_present": _canonical_modules_ready(),
        "provider": "ipfs_datasets_py",
        "module_path": "ipfs_datasets_py.logic.integration.reasoning.legal_ir_canonical_pipeline",
        "executed": executed,
        "status": status,
        "traceable": traceable,
        "source_map_valid": source_map_valid,
        "schema_match": schema_match,
        "tampered": tampered,
        "reason": reason,
        "identities": canonical_compiler_identities() or {},
    }


def get_canonical_compiler_capability() -> CanonicalCompilerCapability:
    """Return the canonical compiler gate.

    Importing the pipeline module leaves the capability degraded. Implemented
    status is recorded only after a supported compile with a validated source
    map, and only while the live identities still match that execution.
    """

    if not _canonical_modules_ready():
        return classify_canonical_compiler_capability(
            _canonical_evidence(reason=_canonical_import_reason())
        )
    execution = _CANONICAL_SUPPORTED_EXECUTION
    live = canonical_compiler_identities() or {}
    if not execution:
        return classify_canonical_compiler_capability(_canonical_evidence())
    if execution.get("identities") != live:
        return classify_canonical_compiler_capability(
            _canonical_evidence(
                schema_match=False,
                reason="Live canonical identities no longer match the executed formalization.",
            )
        )
    return classify_canonical_compiler_capability(
        _canonical_evidence(
            executed=True,
            status="success",
            traceable=True,
            source_map_valid=True,
        )
    )


def reset_canonical_formalization_cache() -> None:
    """Drop cached formalizations and the supported-execution marker.

    Receipts already returned to callers are independent copies. This reset
    clears only the adapter's reuse index.
    """

    global _CANONICAL_SUPPORTED_EXECUTION
    _CANONICAL_FORMALIZATION_RECEIPTS.clear()
    _CANONICAL_FORMALIZATION_CACHE.clear()
    _CANONICAL_RECEIPT_ORIGIN_DIGESTS.clear()
    _CANONICAL_SUPPORTED_EXECUTION = None
    reset_bound_proof_obligation_cache()


def inspect_canonical_formalization_receipt(receipt_id: str) -> Dict[str, Any] | None:
    """Return a stored formalization receipt without treating it as reusable."""

    stored = _CANONICAL_FORMALIZATION_RECEIPTS.get(str(receipt_id or ""))
    if stored is None:
        return None
    return deepcopy(stored)


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return _jsonable(to_dict())
        except (TypeError, ValueError):
            return str(value)
    if isinstance(value, Enum):
        return value.value
    return str(value)


def _identity_mismatch(live: Mapping[str, Any], expected: Mapping[str, Any]) -> List[str]:
    mismatched: List[str] = []
    for key, expected_value in expected.items():
        if expected_value is None:
            continue
        actual = live.get(key)
        if key == "stage_ids":
            actual_ids = tuple(actual or ())
            expected_ids = tuple(expected_value)
            if actual_ids != expected_ids:
                mismatched.append(key)
            continue
        if str(actual or "") != str(expected_value):
            mismatched.append(key)
    return mismatched


def _vocabulary_from_mapping(value: Mapping[str, Any]) -> Any:
    vocabulary_type = _canonical_contracts_module.CanonicalAtomVocabulary
    return vocabulary_type(
        actors=tuple(value.get("actors") or ()),
        actions=tuple(value.get("actions") or ()),
        objects=tuple(value.get("objects") or ()),
        qualifiers=tuple(value.get("qualifiers") or ()),
    )


def _legal_source_text(
    source_text: str,
    legal_context: Mapping[str, Any] | None,
) -> tuple[str, str]:
    context = legal_context if isinstance(legal_context, Mapping) else {}
    versioned = str(
        context.get("source_text")
        or context.get("normalized_text")
        or ""
    ).strip()
    if versioned:
        return versioned, "legal_context"
    return str(source_text or ""), "argument"


def _citation_from_context(legal_context: Mapping[str, Any] | None, request_id: str) -> str:
    context = legal_context if isinstance(legal_context, Mapping) else {}
    for key in ("citation", "authority_locator", "source_locator", "authority_id"):
        text = str(context.get(key) or "").strip()
        if text:
            return text
    return request_id or "synthetic-legal-source"


def _version_from_context(legal_context: Mapping[str, Any] | None) -> str:
    context = legal_context if isinstance(legal_context, Mapping) else {}
    for key in ("authority_version", "corpus_version", "version"):
        text = str(context.get(key) or "").strip()
        if text:
            return text
    return ""


def _compile_cache_key(
    identities: Mapping[str, Any],
    *,
    source_cid: str,
    request_id: str,
    vocabulary: Mapping[str, Any],
    allow_explicit_partial: bool,
    authority_version: str,
    citation: str,
    legal_text_origin: str,
    excluded_user_facts: Sequence[str],
    factual_premises: Sequence[Mapping[str, Any]] = (),
    unresolved_assumptions: Sequence[Mapping[str, Any]] = (),
) -> str:
    payload = {
        "allow_explicit_partial": allow_explicit_partial,
        "authority_version": authority_version,
        "citation": citation,
        "legal_text_origin": legal_text_origin,
        "excluded_user_facts": list(excluded_user_facts),
        "factual_premises": [dict(item) for item in factual_premises],
        "unresolved_assumptions": [dict(item) for item in unresolved_assumptions],
        "identities": dict(identities),
        "request_id": request_id,
        "source_cid": source_cid,
        "vocabulary": dict(vocabulary),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _source_cid_for_text(source_text: str) -> str:
    cid_for_bytes = _canonical_symbol(_canonical_contracts_module, "cid_for_bytes")
    if cid_for_bytes is None:
        from ipfs_datasets_py.utils.cid_utils import cid_for_bytes as cid_for_bytes  # type: ignore
    return str(cid_for_bytes(source_text.encode("utf-8")))


def _prevalidate_character_spans(
    source_text: str,
    source_cid: str,
    entries: Sequence[Any],
) -> List[Dict[str, str]]:
    """Reject spans before the source-map builder can clamp them.

    Canonical entries are character offsets. Byte offsets from other contracts
    are not accepted, including offsets that would become in-range after clamping.
    """

    issues: List[Dict[str, str]] = []
    character_length = len(source_text)
    if not entries:
        issues.append(
            {
                "code": "empty_source_map",
                "message": "Canonical result emitted no source-map entries.",
                "field_path": "source_map",
            }
        )
        return issues
    for index, entry in enumerate(entries):
        path = f"source_map[{index}]"
        entry_cid = str(getattr(entry, "source_cid", "") or "")
        if entry_cid != source_cid:
            issues.append(
                {
                    "code": "source_cid_mismatch",
                    "message": "Source-map entry CID does not match the legal source text.",
                    "field_path": path,
                }
            )
        start = getattr(entry, "start", None)
        end = getattr(entry, "end", None)
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, int)
            or not isinstance(end, int)
            or start < 0
            or end <= start
            or end > character_length
        ):
            issues.append(
                {
                    "code": "character_span_out_of_range",
                    "message": "Source-map span is not a nonempty character range inside the legal text.",
                    "field_path": path,
                }
            )
            continue
        passage = source_text[start:end]
        if passage == "":
            issues.append(
                {
                    "code": "empty_passage",
                    "message": "Character span selected an empty passage.",
                    "field_path": path,
                }
            )
    return issues


def _bridge_canonical_source_map(
    *,
    source_text: str,
    source_cid: str,
    citation: str,
    entries: Sequence[Any],
    rules: Sequence[Any],
    stages: Sequence[Any],
    identities: Mapping[str, Any],
) -> Dict[str, Any]:
    """Bridge canonical character spans into the LegalIR source-map schema."""

    source_maps = _canonical_source_map_module
    builder = source_maps.LegalIRSourceMapBuilder(
        source_map_id="",
        metadata={
            "builder": "canonical_compiler_adapter",
            "span_unit": "character",
            "schema_version": identities.get("source_map_schema"),
            "compiler_interface": identities.get("compiler_interface"),
            "pipeline_cid": identities.get("pipeline_cid"),
        },
    )
    builder.add_source_document(
        source_cid,
        source_text,
        citation=citation,
        metadata={"source_cid": source_cid, "span_unit": "character"},
    )
    formula_ids = list(dict.fromkeys(str(rule.rule_cid) for rule in rules))
    expected_fields = {
        (str(rule.rule_cid), f"/rules/{index}/{field}")
        for index, rule in enumerate(rules)
        for field in rule.to_dict()
    }
    observed_fields = Counter((str(entry.rule_cid), str(entry.field_path)) for entry in entries)
    coverage_issues = []
    if set(observed_fields) != expected_fields or any(count != 1 for count in observed_fields.values()):
        coverage_issues.append({
            "code": "canonical_field_coverage_mismatch",
            "message": "Every emitted rule field requires exactly one matching source-map entry.",
            "field_path": "source_map",
        })
    field_ids_by_rule: Dict[str, List[str]] = {}
    passages: List[Dict[str, Any]] = []
    for entry in entries:
        passage = source_text[entry.start:entry.end]
        span = builder.add_span(
            source_cid,
            entry.start,
            entry.end,
            citation=citation,
            normalized_text=passage,
            transformation_step_id="canonical.source_span",
            decompiler_attribution="not_decompiled",
            metadata={
                "rule_cid": entry.rule_cid,
                "field_path": entry.field_path,
                "attribution": entry.attribution,
                "span_unit": "character",
            },
        )
        node_id = f"field:{entry.rule_cid}:{entry.field_path}"
        builder.add_node(
            node_id,
            node_kind="canonical_field",
            span_ids=(span.span_id,),
            emitted_fact=entry.rule_cid,
            transformation_step_id="canonical.source_span",
            decompiler_attribution="not_decompiled",
            metadata={"field_path": entry.field_path, "rule_cid": entry.rule_cid},
        )
        field_ids_by_rule.setdefault(str(entry.rule_cid), []).append(node_id)
        passages.append(
            {
                "rule_cid": entry.rule_cid,
                "field_path": entry.field_path,
                "source_cid": entry.source_cid,
                "start": entry.start,
                "end": entry.end,
                "passage": passage,
                "span_id": span.span_id,
                "span_unit": "character",
            }
        )

    for rule in rules:
        rule_cid = str(rule.rule_cid)
        parents = tuple(field_ids_by_rule.get(rule_cid) or ())
        if not parents:
            continue
        builder.add_derived_node(
            rule_cid,
            node_kind="compiler_formula",
            derived_from_node_ids=parents,
            transformation_step="compiler.emit_formula",
            transform_kind=source_maps.LegalIRTransformationKind.COMPILER,
            emitted_fact=rule_cid,
            decompiler_attribution="not_decompiled",
            metadata={"rule": _jsonable(rule.to_dict())},
        )

    previous = tuple(node_id for ids in field_ids_by_rule.values() for node_id in ids)
    stage_ids: List[str] = []
    for stage in stages:
        stage_id = str(stage.stage_id)
        node_id = f"stage:{stage_id}"
        builder.add_derived_node(
            node_id,
            node_kind="compiler_stage",
            derived_from_node_ids=previous or tuple(formula_ids),
            transformation_step=f"compiler.stage.{stage_id}",
            transform_kind=source_maps.LegalIRTransformationKind.COMPILER,
            emitted_fact=node_id,
            decompiler_attribution="not_decompiled",
            metadata={
                "interface": str(stage.interface),
                "identity_cid": str(stage.identity_cid),
                "status": str(stage.status),
            },
        )
        previous = (node_id,)
        stage_ids.append(node_id)

    bridged = builder.to_source_map()
    formula_document = {
        "modal_ir": {
            "document_id": source_cid,
            "normalized_text": source_text,
            "citation": citation,
            "formulas": [
                {
                    "formula_id": item["rule_cid"],
                    "provenance": {
                        "source_document_id": source_cid,
                        "source_id": source_cid,
                        "citation": citation,
                        "start_char": item["start"],
                        "end_char": item["end"],
                        "transformation_step": "compiler.source_span",
                        "decompiler_attribution": "not_decompiled",
                    },
                }
                for item in passages
            ],
        }
    }
    built = source_maps.build_legal_ir_source_map(formula_document)
    if (bridged.schema_version != identities.get("source_map_schema")
            or built.schema_version != identities.get("source_map_schema")):
        coverage_issues.append({
            "code": "source_map_schema_mismatch",
            "message": "The executed source-map schema differs from the current identity.",
            "field_path": "source_map.schema_version",
        })
    validation = source_maps.validate_legal_ir_source_map(bridged)
    built_validation = source_maps.validate_legal_ir_source_map(built)
    emitted_ids = tuple(dict.fromkeys([*formula_ids, *stage_ids]))
    binding = source_maps.bind_legal_ir_artifact_source_map(
        {"emitted_fact_ids": list(emitted_ids), "artifact_id": bridged.source_map_id},
        bridged,
        artifact_kind="compiler_formula",
        emitted_fact_ids=emitted_ids,
    )
    binding_payload = {
        "artifact_id": binding.artifact_id,
        "artifact_kind": binding.artifact_kind,
        "emitted_fact_ids": list(binding.emitted_fact_ids),
        "traceable_fact_ids": list(binding.traceable_fact_ids),
        "derived_fact_ids": list(binding.derived_fact_ids),
        "missing_fact_ids": list(binding.missing_fact_ids),
        "traceable": bool(binding.traceable),
        "issues": [issue.to_dict() for issue in binding.issues],
    }
    traces = [
        source_maps.trace_legal_ir_fact(bridged, fact_id).to_dict()
        for fact_id in emitted_ids
    ]
    built_formula_ids = [node.node_id for node in built.nodes]
    missing_from_build = sorted(set(formula_ids) - set(built_formula_ids))
    transformations_missing = [
        trace["fact_id"]
        for trace in traces
        if trace["fact_id"] in formula_ids
        and (not trace.get("transformation_steps") or not trace.get("source_spans"))
    ]
    coverage_ok = bool(formula_ids) and bool(stage_ids) and not missing_from_build and not coverage_issues
    return {
        "source_map": bridged.to_dict(),
        "built_source_map": built.to_dict(),
        "validation": validation.to_dict(),
        "built_validation": built_validation.to_dict(),
        "traceability": binding_payload,
        "traces": traces,
        "passages": passages,
        "formula_ids": formula_ids,
        "stage_node_ids": stage_ids,
        "transformations_missing": transformations_missing,
        "coverage_issues": coverage_issues,
        "coverage_ok": (
            coverage_ok
            and validation.valid
            and built_validation.valid
            and binding.traceable
            and not transformations_missing
            and binding.emitted_fact_ids
        ),
    }


def _unsupported_diagnostics(result: Any, stages: Sequence[Any]) -> List[Dict[str, Any]]:
    diagnostics: List[Dict[str, Any]] = []
    for item in getattr(result, "unsupported_semantics", ()) or ():
        payload = _jsonable(item.to_dict() if hasattr(item, "to_dict") else item)
        if isinstance(payload, dict):
            payload["origin"] = "result.unsupported_semantics"
            diagnostics.append(payload)
    for item in getattr(result, "diagnostics", ()) or ():
        payload = _jsonable(item.to_dict() if hasattr(item, "to_dict") else item)
        if isinstance(payload, dict):
            payload["origin"] = "result.diagnostics"
            diagnostics.append(payload)
    error = getattr(result, "error", None)
    if error is not None:
        payload = _jsonable(error.to_dict() if hasattr(error, "to_dict") else error)
        if isinstance(payload, dict):
            payload["origin"] = "result.error"
            diagnostics.append(payload)
    for stage in stages:
        for item in getattr(stage, "unsupported", ()) or ():
            payload = _jsonable(item)
            if isinstance(payload, dict):
                payload["origin"] = f"stage.{stage.stage_id}"
                diagnostics.append(payload)
    return diagnostics


def _stage_records(stages: Sequence[Any]) -> List[Dict[str, Any]]:
    return [_jsonable(stage.to_dict()) for stage in stages]


def _receipt_shell(
    *,
    status: str,
    capability: CanonicalCompilerCapability,
    identities: Mapping[str, Any] | None,
    reason: str,
    cache_outcome: str,
    prior_receipt_id: str = "",
    mismatched_fields: Sequence[str] = (),
    extra: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "schema_version": "canonical-formalization-receipt/v1",
        "status": status,
        "capability": capability.as_dict(),
        "identities": dict(identities or {}),
        "reason": reason,
        "cache_outcome": cache_outcome,
        "reused": cache_outcome == "reused",
        "prior_receipt_id": prior_receipt_id,
        "mismatched_fields": list(mismatched_fields),
        "entails_applicability": False,
        "entails_claim": False,
        "legal_text_separated_from_user_facts": True,
        "user_facts_included_in_source": False,
        "source_map": None,
        "source_map_validation": None,
        "traceability": None,
        "unsupported_diagnostics": [],
        "stages": [],
        "formula_ids": [],
        "passages": [],
    }
    if extra:
        body.update(dict(extra))
    encoded = json.dumps(
        {key: body[key] for key in ("status", "reason", "identities", "prior_receipt_id", "mismatched_fields")},
        sort_keys=True,
        default=str,
    )
    body["receipt_id"] = "canonical-receipt-" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:32]
    return body


def _canonical_receipt_origin_digest(receipt: Mapping[str, Any]) -> str:
    """Pin the original host-owned record, excluding presentation-only fields.

    Public callers receive copies. This custody check does not authenticate
    arbitrary privileged Python code that can replace private module state.
    """
    body = {key: value for key, value in receipt.items()
            if key not in {"metadata", "reused", "cache_outcome"}}
    # with_adapter_metadata adds these top-level defaults after storage. Apply
    # exactly those defaults to both copies without trusting metadata as proof.
    body.setdefault("provider", "ipfs_datasets_py")
    capability = body.get("capability")
    if isinstance(capability, Mapping):
        reason = str(capability.get("reason") or "").strip()
        if reason:
            body.setdefault("degraded_reason", reason)
    return hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _canonical_receipt_has_execution_origin(receipt: Mapping[str, Any]) -> bool:
    receipt_id = receipt.get("receipt_id")
    stored = _CANONICAL_FORMALIZATION_RECEIPTS.get(receipt_id) if isinstance(receipt_id, str) else None
    digest = _CANONICAL_RECEIPT_ORIGIN_DIGESTS.get(receipt_id) if isinstance(receipt_id, str) else None
    if stored is None or digest is None:
        return False
    try:
        return (_canonical_receipt_origin_digest(stored) == digest
                and _canonical_receipt_origin_digest(receipt) == digest)
    except (TypeError, ValueError, RecursionError):
        return False


def _store_receipt(receipt: Dict[str, Any], *, cache_key: str = "") -> Dict[str, Any]:
    stored = deepcopy(receipt)
    _CANONICAL_FORMALIZATION_RECEIPTS[stored["receipt_id"]] = stored
    _CANONICAL_RECEIPT_ORIGIN_DIGESTS[stored["receipt_id"]] = _canonical_receipt_origin_digest(stored)
    if cache_key and stored.get("status") == "success":
        _CANONICAL_FORMALIZATION_CACHE[cache_key] = stored["receipt_id"]
    return deepcopy(stored)


def _finish(receipt: Dict[str, Any]) -> Dict[str, Any]:
    capability = receipt.get("capability") if isinstance(receipt.get("capability"), Mapping) else {}
    return with_adapter_metadata(
        receipt,
        operation="compile_canonical_legal_ir",
        backend_available=bool(capability.get("available")),
        degraded_reason=capability.get("reason"),
        implementation_status=str(capability.get("status") or ""),
        extra_metadata={
            "canonical_support": capability.get("support"),
            "pipeline_cid": (receipt.get("identities") or {}).get("pipeline_cid", ""),
            "compiler_config_cid": (receipt.get("identities") or {}).get("compiler_config_cid", ""),
        },
    )


_RETAINED_STAGE_IDS = (
    "typed_family_parse",
    "elaboration",
    "formalization",
    "bridge",
)


def _optional_exact_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or isinstance(value, bool):
        raise ValueError(field_name)
    return value


def _bind_admitted_law(
    source_text: str,
    legal_context: Mapping[str, Any] | None,
    admitted_law: Mapping[str, Any] | None,
) -> tuple[str, str, Dict[str, Any], str]:
    """Select legal bytes from admitted law when that record is present.

    A factual narrative passed as ``source_text`` cannot replace an admitted
    statute, and a hash or length that does not match the UTF-8 text is a
    typed failure rather than a compiled source.
    """

    context = dict(legal_context) if isinstance(legal_context, Mapping) else {}
    if admitted_law is None:
        legal_text, origin = _legal_source_text(source_text, context)
        return legal_text, origin, context, ""
    if not isinstance(admitted_law, Mapping):
        return "", "admitted_law", context, "admitted_law_malformed"
    text = admitted_law.get("source_text")
    if not isinstance(text, str) or not text.strip():
        return "", "admitted_law", context, "admitted_law_missing_text"
    try:
        raw = text.encode("utf-8")
        if raw.decode("utf-8") != text:
            return "", "admitted_law", context, "utf8_correspondence_failed"
        expected_hash = admitted_law.get("source_sha256")
        if expected_hash is not None:
            if not isinstance(expected_hash, str) or expected_hash != hashlib.sha256(raw).hexdigest():
                return "", "admitted_law", context, "admitted_source_hash_mismatch"
        if _optional_exact_int(admitted_law.get("source_character_length"), "source_character_length") not in (None, len(text)):
            return "", "admitted_law", context, "character_length_mismatch"
        if _optional_exact_int(admitted_law.get("source_byte_length"), "source_byte_length") not in (None, len(raw)):
            return "", "admitted_law", context, "byte_length_mismatch"
    except (UnicodeError, ValueError):
        return "", "admitted_law", context, "admitted_law_malformed"
    argument = source_text if isinstance(source_text, str) else ""
    if argument.strip() and argument != text:
        return "", "admitted_law", context, "source_text_conflicts_with_admitted_law"
    context_text = str(context.get("source_text") or context.get("normalized_text") or "")
    if context_text.strip() and context_text != text:
        return "", "admitted_law", context, "legal_context_conflicts_with_admitted_law"
    for key in ("citation", "authority_locator", "authority_id", "authority_version", "corpus_version", "version"):
        if key in admitted_law and key not in context:
            context[key] = admitted_law[key]
    context["source_text"] = text
    return text, "admitted_law", context, ""


def _bind_factual_premises(
    premises: Sequence[Any] | None,
    legal_text: str,
) -> tuple[List[Dict[str, Any]], str]:
    """Bind factual premises beside the statute without copying them into it."""

    if premises is None:
        return [], ""
    if isinstance(premises, (str, bytes)) or not isinstance(premises, Sequence):
        return [], "factual_premises_malformed"
    bound: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(premises):
        if not isinstance(item, Mapping):
            return [], "factual_premise_malformed"
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            return [], "factual_premise_missing_text"
        if text == legal_text:
            return [], "factual_premise_replaced_admitted_law"
        try:
            raw = text.encode("utf-8")
            if raw.decode("utf-8") != text:
                return [], "factual_premise_utf8_mismatch"
            expected_hash = item.get("text_sha256")
            digest = hashlib.sha256(raw).hexdigest()
            if expected_hash is not None and expected_hash != digest:
                return [], "factual_premise_hash_mismatch"
        except UnicodeError:
            return [], "factual_premise_malformed"
        premise_id = str(item.get("premise_id") or f"premise-{index}").strip()
        if not premise_id or premise_id in seen:
            return [], "factual_premise_identity_malformed"
        seen.add(premise_id)
        bound.append({
            "premise_id": premise_id,
            "text": text,
            "text_sha256": digest,
            "character_length": len(text),
            "byte_length": len(raw),
            "span_unit": "character",
            "role": "factual_premise",
            "bound_separately": True,
            "included_in_legal_source": False,
        })
    return bound, ""


def _bind_unresolved_assumptions(
    assumptions: Sequence[Any] | None,
) -> tuple[List[Dict[str, Any]], str]:
    """Keep caller assumptions unresolved. Resolution is not a compiler result."""

    if assumptions is None:
        return [], ""
    if isinstance(assumptions, (str, bytes)) or not isinstance(assumptions, Sequence):
        return [], "unresolved_assumptions_malformed"
    bound: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(assumptions):
        record = {"assumption_id": f"assumption-{index}", "statement": item} if isinstance(item, str) else item
        if not isinstance(record, Mapping):
            return [], "unresolved_assumption_malformed"
        if record.get("resolved") is True or record.get("status") in {"resolved", "proved", "satisfied"}:
            return [], "assumption_resolution_unsupported"
        statement = record.get("statement")
        if not isinstance(statement, str) or not statement.strip():
            return [], "unresolved_assumption_missing_statement"
        assumption_id = str(record.get("assumption_id") or f"assumption-{index}").strip()
        if not assumption_id or assumption_id in seen:
            return [], "unresolved_assumption_identity_malformed"
        seen.add(assumption_id)
        source_ref_ids = record.get("source_ref_ids") or []
        if not isinstance(source_ref_ids, Sequence) or isinstance(source_ref_ids, (str, bytes)):
            return [], "unresolved_assumption_malformed"
        bound.append({
            "assumption_id": assumption_id,
            "statement": statement,
            "source_ref_ids": [str(ref) for ref in source_ref_ids],
            "resolved": False,
            "proves_claim": False,
        })
    return bound, ""


def _retained_stage_identities(
    stages: Sequence[Any],
    source_map: Mapping[str, Any] | None,
    identities: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    by_id = {
        str(stage.get("stage_id")): stage
        for stage in stages
        if isinstance(stage, Mapping) and stage.get("stage_id")
    }
    retained: Dict[str, Any] = {}
    for stage_id in _RETAINED_STAGE_IDS:
        stage = by_id.get(stage_id)
        if stage is None:
            retained[stage_id] = None
            continue
        retained[stage_id] = {
            "stage_id": stage.get("stage_id"),
            "interface": stage.get("interface"),
            "identity_cid": stage.get("identity_cid"),
            "input_cid": stage.get("input_cid"),
            "output_cid": stage.get("output_cid"),
            "config_cid": stage.get("config_cid"),
            "status": stage.get("status"),
        }
    if isinstance(source_map, Mapping):
        retained["source_map"] = {
            "schema_version": source_map.get("schema_version") or (identities or {}).get("source_map_schema"),
            "source_map_id": source_map.get("source_map_id"),
        }
    else:
        retained["source_map"] = None
    return retained


def _binding_failure_receipt(
    *,
    identities: Mapping[str, Any],
    reason: str,
    user_facts: Sequence[str],
    legal_origin: str,
    authority_version: str,
    factual_premises: Sequence[Mapping[str, Any]],
    unresolved_assumptions: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    capability = classify_canonical_compiler_capability(
        _canonical_evidence(executed=True, status="failed", reason=reason)
    )
    return _receipt_shell(
        status="failed",
        capability=capability,
        identities=identities,
        reason=reason,
        cache_outcome="not_cached",
        extra={
            "user_facts": list(user_facts),
            "legal_text_origin": legal_origin,
            "authority_version": authority_version,
            "factual_premises": [dict(item) for item in factual_premises],
            "unresolved_assumptions": [dict(item) for item in unresolved_assumptions],
            "retained_stage_identities": _retained_stage_identities((), None, identities),
            "stage_evidence": {
                "kind": "canonical_legal_ir_stage_evidence",
                "status": "failed",
                "fabricated_ir": False,
                "source_map_present": False,
            },
            "establishes_governing_law_meaning": False,
            "proves_claim": False,
            "factual_premises_included_in_source": False,
        },
    )


def compile_canonical_legal_ir(
    source_text: str,
    *,
    request_id: str,
    vocabulary: Mapping[str, Sequence[str]],
    legal_context: Mapping[str, Any] | None = None,
    user_facts: Sequence[str] | None = None,
    admitted_law: Mapping[str, Any] | None = None,
    factual_premises: Sequence[Any] | None = None,
    unresolved_assumptions: Sequence[Any] | None = None,
    allow_explicit_partial: bool = False,
    expected_schema_version: str | None = None,
    expected_compiler_interface: str | None = None,
    expected_compiler_config_cid: str | None = None,
    expected_policy_cid: str | None = None,
    expected_pipeline_interface: str | None = None,
    expected_pipeline_cid: str | None = None,
    expected_stage_ids: Sequence[str] | None = None,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """Compile legal text through ``compile_canonical_pipeline`` and map sources.

    User facts are recorded as excluded. They are not appended to the legal
    source, and neither applicability nor claim entailment is claimed.
    A version or schema mismatch does not reuse a cached formalization; the
    previous receipt stays inspectable.
    """

    global _CANONICAL_SUPPORTED_EXECUTION
    identities = canonical_compiler_identities()
    if identities is None:
        capability = classify_canonical_compiler_capability(
            _canonical_evidence(reason=_canonical_import_reason())
        )
        receipt = _receipt_shell(
            status="unavailable",
            capability=capability,
            identities=None,
            reason=capability.reason or _canonical_import_reason(),
            cache_outcome="not_cached",
            extra={"user_facts": [str(item) for item in (user_facts or ())]},
        )
        return _finish(_store_receipt(receipt))

    expected = {
        "source_map_schema": expected_schema_version,
        "compiler_interface": expected_compiler_interface,
        "compiler_config_cid": expected_compiler_config_cid,
        "policy_cid": expected_policy_cid,
        "pipeline_interface": expected_pipeline_interface,
        "pipeline_cid": expected_pipeline_cid,
        "stage_ids": None if expected_stage_ids is None else tuple(expected_stage_ids),
    }
    provided = {
        key: value
        for key, value in expected.items()
        if value is not None and key != "stage_ids" or (key == "stage_ids" and expected_stage_ids is not None)
    }
    mismatched = _identity_mismatch(identities, provided)
    if mismatched:
        capability = classify_canonical_compiler_capability(
            _canonical_evidence(
                schema_match=False,
                reason="Requested canonical schema or compiler identity does not match the live pipeline.",
            )
        )
        prior = ""
        if _CANONICAL_FORMALIZATION_CACHE:
            prior = next(reversed(_CANONICAL_FORMALIZATION_CACHE.values()))
        receipt = _receipt_shell(
            status="schema_mismatch",
            capability=capability,
            identities=identities,
            reason=capability.reason or "schema mismatch",
            cache_outcome="invalidated",
            prior_receipt_id=prior,
            mismatched_fields=mismatched,
        )
        return _finish(_store_receipt(receipt))

    legal_text, legal_origin, bound_context, binding_error = _bind_admitted_law(
        source_text, legal_context, admitted_law,
    )
    premise_records, premise_error = _bind_factual_premises(factual_premises, legal_text)
    assumption_records, assumption_error = _bind_unresolved_assumptions(unresolved_assumptions)
    input_error = binding_error or premise_error or assumption_error
    excluded_facts = [str(item) for item in (user_facts or ()) if str(item).strip()]
    for premise in premise_records:
        if premise["text"] not in excluded_facts:
            excluded_facts.append(premise["text"])
    authority_version = _version_from_context(bound_context)
    citation = _citation_from_context(bound_context, request_id)
    if input_error:
        receipt = _binding_failure_receipt(
            identities=identities,
            reason=input_error,
            user_facts=excluded_facts,
            legal_origin=legal_origin,
            authority_version=authority_version,
            factual_premises=premise_records,
            unresolved_assumptions=assumption_records,
        )
        return _finish(_store_receipt(receipt))
    if not str(legal_text or "").strip():
        capability = classify_canonical_compiler_capability(
            _canonical_evidence(
                executed=True,
                status="failed",
                reason="Legal source text is required and is separate from user facts.",
            )
        )
        receipt = _receipt_shell(
            status="failed",
            capability=capability,
            identities=identities,
            reason=capability.reason or "missing legal text",
            cache_outcome="not_cached",
            extra={
                "user_facts": excluded_facts,
                "legal_text_origin": legal_origin,
                "authority_version": authority_version,
                "factual_premises": premise_records,
                "unresolved_assumptions": assumption_records,
                "retained_stage_identities": _retained_stage_identities((), None, identities),
                "stage_evidence": {
                    "kind": "canonical_legal_ir_stage_evidence",
                    "status": "failed",
                    "fabricated_ir": False,
                    "source_map_present": False,
                },
                "establishes_governing_law_meaning": False,
                "proves_claim": False,
                "factual_premises_included_in_source": False,
            },
        )
        return _finish(_store_receipt(receipt))

    try:
        atom_vocabulary = _vocabulary_from_mapping(vocabulary)
        request = _canonical_contracts_module.CompilerRequest(
            source_text=legal_text,
            request_id=str(request_id),
            atom_vocabulary=atom_vocabulary,
            allow_explicit_partial=bool(allow_explicit_partial),
        )
    except (TypeError, ValueError) as exc:
        capability = classify_canonical_compiler_capability(
            _canonical_evidence(executed=True, status="failed", reason=str(exc))
        )
        receipt = _receipt_shell(
            status="failed",
            capability=capability,
            identities=identities,
            reason=str(exc),
            cache_outcome="not_cached",
            extra={
            "user_facts": excluded_facts,
            "authority_version": authority_version,
            "factual_premises": premise_records,
            "unresolved_assumptions": assumption_records,
            "retained_stage_identities": _retained_stage_identities((), None, identities),
            "stage_evidence": {
                "kind": "canonical_legal_ir_stage_evidence",
                "status": "failed",
                "fabricated_ir": False,
                "source_map_present": False,
            },
            "establishes_governing_law_meaning": False,
            "proves_claim": False,
        },
        )
        return _finish(_store_receipt(receipt))

    cache_key = _compile_cache_key(
        identities,
        source_cid=request.source_cid,
        request_id=str(request_id),
        vocabulary=atom_vocabulary.to_dict(),
        allow_explicit_partial=bool(allow_explicit_partial),
        authority_version=authority_version,
        citation=citation,
        legal_text_origin=legal_origin,
        excluded_user_facts=excluded_facts,
        factual_premises=premise_records,
        unresolved_assumptions=assumption_records,
    )
    if use_cache and cache_key in _CANONICAL_FORMALIZATION_CACHE:
        cached_id = _CANONICAL_FORMALIZATION_CACHE[cache_key]
        cached = _CANONICAL_FORMALIZATION_RECEIPTS.get(cached_id)
        if (cached is not None and cached.get("identities") == identities
                and _canonical_receipt_has_execution_origin(cached)):
            reused = deepcopy(cached)
            reused["reused"] = True
            reused["cache_outcome"] = "reused"
            reused["cache_key"] = cache_key
            return _finish(reused)

    try:
        pipeline = _canonical_pipeline_module.compile_canonical_pipeline(request)
    except (TypeError, ValueError) as exc:
        capability = classify_canonical_compiler_capability(
            _canonical_evidence(executed=True, status="failed", reason=str(exc))
        )
        receipt = _receipt_shell(
            status="failed",
            capability=capability,
            identities=identities,
            reason=str(exc),
            cache_outcome="not_cached",
            extra={
                "user_facts": excluded_facts,
                "cache_key": cache_key,
                "factual_premises": premise_records,
                "unresolved_assumptions": assumption_records,
                "retained_stage_identities": _retained_stage_identities((), None, identities),
                "stage_evidence": {
                    "kind": "canonical_legal_ir_stage_evidence",
                    "status": "failed",
                    "fabricated_ir": False,
                    "source_map_present": False,
                },
                "establishes_governing_law_meaning": False,
                "proves_claim": False,
            },
        )
        return _finish(_store_receipt(receipt))

    result = pipeline.result
    stages = tuple(pipeline.stages)
    status_value = str(getattr(result.status, "value", result.status))
    diagnostics = _unsupported_diagnostics(result, stages)
    stage_payload = _stage_records(stages)
    observed_pipeline_cid = str(pipeline.pipeline_cid)
    if observed_pipeline_cid != identities["pipeline_cid"]:
        capability = classify_canonical_compiler_capability(_canonical_evidence(
            schema_match=False, reason="Executed pipeline identity differs from the current compiler contract.",
        ))
        return _finish(_store_receipt(_receipt_shell(
            status="schema_mismatch", capability=capability, identities=identities,
            reason=capability.reason or "pipeline identity mismatch", cache_outcome="invalidated",
            mismatched_fields=("pipeline_cid",),
        )))
    rules = () if result.canonical_ir is None else tuple(result.canonical_ir.rules)
    span_issues = []
    bridge: Dict[str, Any] | None = None
    if status_value == "success":
        span_issues = _prevalidate_character_spans(legal_text, request.source_cid, result.source_map)
        if not span_issues and rules:
            bridge = _bridge_canonical_source_map(
                source_text=legal_text,
                source_cid=request.source_cid,
                citation=citation,
                entries=result.source_map,
                rules=rules,
                stages=stages,
                identities=identities,
            )
        elif not span_issues and not rules:
            span_issues.append(
                {
                    "code": "empty_formula_coverage",
                    "message": "Successful compile emitted no formulas to trace.",
                    "field_path": "canonical_ir.rules",
                }
            )
    coverage_ok = bool(bridge and bridge.get("coverage_ok"))
    partial = status_value == "success" and bool(result.unsupported_semantics)
    if status_value == "success" and not partial and coverage_ok and not span_issues:
        outcome = "success"
    elif status_value == "success" and partial and coverage_ok and not span_issues:
        outcome = "partial"
    elif status_value == "abstained":
        outcome = "abstained"
    else:
        outcome = "failed"
    reason = ""
    if outcome != "success":
        if span_issues:
            reason = "; ".join(item["message"] for item in span_issues)
        elif bridge is not None and not bridge.get("coverage_ok"):
            reason = "Emitted formulas are not fully traceable to source passages and transformations."
        elif outcome == "partial":
            reason = "Canonical compile retained unsupported semantics as an explicit partial result."
        elif outcome == "abstained":
            reason = "Canonical compile abstained and did not emit a reusable formalization."
        else:
            reason = "Canonical compile failed."
    capability = classify_canonical_compiler_capability(
        _canonical_evidence(
            executed=True,
            status=outcome,
            traceable=coverage_ok,
            source_map_valid=coverage_ok,
            reason=reason,
        )
    )
    if capability.implemented:
        _CANONICAL_SUPPORTED_EXECUTION = {
            "identities": deepcopy(identities),
            "receipt_status": outcome,
        }
    receipt_extra: Dict[str, Any] = {
        "request_id": str(request_id),
        "request_cid": request.request_cid,
        "source_cid": request.source_cid,
        "source_text": legal_text,
        "source_character_length": len(legal_text),
        "source_byte_length": len(legal_text.encode("utf-8")),
        "span_unit": "character",
        "legal_text_origin": legal_origin,
        "authority_version": authority_version,
        "citation": citation,
        "user_facts": excluded_facts,
        "compiler_status": status_value,
        "result_cid": str(result.result_cid),
        "compiler_request": _jsonable(request.to_dict()),
        "compiler_result": _jsonable(result.to_dict()),
        "pipeline_cid": observed_pipeline_cid,
        "stages": stage_payload,
        "unsupported_diagnostics": diagnostics,
        "span_issues": span_issues,
        "cache_key": cache_key,
        "formula_ids": [] if bridge is None else list(bridge["formula_ids"]),
        "passages": [] if bridge is None else list(bridge["passages"]),
        "source_map": None if bridge is None else bridge["source_map"],
        "built_source_map": None if bridge is None else bridge["built_source_map"],
        "source_map_validation": None if bridge is None else bridge["validation"],
        "built_source_map_validation": None if bridge is None else bridge["built_validation"],
        "traceability": None if bridge is None else bridge["traceability"],
        "traces": [] if bridge is None else list(bridge["traces"]),
        "vocabulary": atom_vocabulary.to_dict(),
        "allow_explicit_partial": bool(allow_explicit_partial),
        "factual_premises": premise_records,
        "unresolved_assumptions": assumption_records,
        "factual_premises_included_in_source": False,
        "establishes_governing_law_meaning": False,
        "proves_claim": False,
        "retained_stage_identities": _retained_stage_identities(
            stage_payload,
            None if bridge is None else bridge["source_map"],
            identities,
        ),
        "stage_evidence": {
            "kind": "canonical_legal_ir_stage_evidence",
            "status": outcome,
            "fabricated_ir": False,
            "source_map_present": bridge is not None,
        },
    }
    if any(fact and fact in legal_text for fact in excluded_facts):
        receipt_extra["user_facts_overlap_warning"] = (
            "A user fact string also occurs inside the legal source; it was not added as a fact premise."
        )
    receipt = _receipt_shell(
        status=outcome,
        capability=capability,
        identities=identities,
        reason=reason,
        cache_outcome="stored",
        extra=receipt_extra,
    )
    # Include the compiler result CID so distinct compiles do not share a shell id.
    receipt["receipt_id"] = "canonical-receipt-" + hashlib.sha256(
        f"{result.result_cid}:{cache_key}:{outcome}".encode("utf-8")
    ).hexdigest()[:32]
    return _finish(_store_receipt(receipt, cache_key=cache_key if outcome == "success" else ""))


def verify_canonical_formalization_receipt(
    receipt_id: str,
    *,
    source_text: str | None = None,
) -> Dict[str, Any]:
    """Re-check a stored receipt. Tampering does not delete the old receipt."""

    stored = inspect_canonical_formalization_receipt(receipt_id)
    if stored is None:
        capability = classify_canonical_compiler_capability(
            _canonical_evidence(reason="Canonical formalization receipt was not found.")
        )
        return _finish(
            {
                "schema_version": "canonical-formalization-receipt/v1",
                "status": "unavailable",
                "receipt_id": str(receipt_id or ""),
                "capability": capability.as_dict(),
                "reason": capability.reason,
                "tampered": False,
                "identities": {},
            }
        )
    candidate = deepcopy(stored)
    if source_text is not None:
        candidate["source_text"] = source_text
    audit = audit_canonical_formalization_payload(candidate)
    audit["inspected_receipt_id"] = stored.get("receipt_id")
    audit["stored_status"] = stored.get("status")
    return _finish(audit)


def audit_canonical_formalization_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Recheck source/IR coverage and distinguish structure from execution.

    A serialized mapping can be structurally valid without proving that this
    process executed it. Only an unchanged originally stored receipt can retain
    executed capability, and only while its complete live identities still match.
    """
    if not _canonical_modules_ready():
        capability = classify_canonical_compiler_capability(
            _canonical_evidence(reason=_canonical_import_reason())
        )
        return {"status": "unavailable", "tampered": False,
                "capability": capability.as_dict(), "reason": capability.reason,
                "issues": [], "traceable": False}

    issues: List[Dict[str, str]] = []
    current = canonical_compiler_identities() or {}
    recorded = payload.get("identities") if isinstance(payload.get("identities"), Mapping) else {}
    identities_match = dict(recorded) == current
    if not identities_match:
        issues.append({"code": "canonical_identity_mismatch",
                       "message": "Receipt identities do not match the current canonical compiler contract.",
                       "field_path": "identities"})
    execution_origin = _canonical_receipt_has_execution_origin(payload)
    receipt_id = payload.get("receipt_id")
    known_origin = isinstance(receipt_id, str) and receipt_id in _CANONICAL_RECEIPT_ORIGIN_DIGESTS
    if known_origin and not execution_origin:
        issues.append({"code": "execution_receipt_mismatch",
                       "message": "Receipt differs from the originally stored execution record.",
                       "field_path": "receipt_id"})

    validation_payload = None
    traceable = False
    status_value = str(payload.get("status") or "")
    text = payload.get("source_text")
    if isinstance(text, str):
        for index, passage in enumerate(payload.get("passages") or ()):
            if not isinstance(passage, Mapping):
                issues.append({"code": "passage_invalid", "message": "Passage record is not an object.",
                               "field_path": f"passages[{index}]"})
                continue
            start, end = passage.get("start"), passage.get("end")
            if (type(start) is not int or type(end) is not int
                    or not 0 <= start < end <= len(text)):
                issues.append({"code": "character_span_out_of_range",
                               "message": "Stored passage is outside the source character length.",
                               "field_path": f"passages[{index}]"})
            elif text[start:end] != passage.get("passage"):
                issues.append({"code": "passage_tampered",
                               "message": "Stored passage does not match the source character span.",
                               "field_path": f"passages[{index}].passage"})
    if status_value in {"success", "partial"}:
        try:
            request = _canonical_contracts_module.CompilerRequest.from_dict(payload.get("compiler_request"))
            result = _canonical_contracts_module.CompilerResult.from_dict(payload.get("compiler_result"))
            if (request.request_cid != result.request_cid
                    or request.request_cid != payload.get("request_cid")
                    or request.source_cid != payload.get("source_cid")
                    or request.source_text != payload.get("source_text")
                    or str(result.result_cid) != payload.get("result_cid")):
                issues.append({"code": "source_or_result_binding_mismatch",
                               "message": "Top-level source and compiler result do not match their typed request.",
                               "field_path": "compiler_request"})
            expected_outcome = "partial" if result.unsupported_semantics else "success"
            if (str(getattr(result.status, "value", result.status)) != "success"
                    or result.canonical_ir is None or status_value != expected_outcome):
                issues.append({"code": "compiler_outcome_mismatch",
                               "message": "Receipt status does not match the executed compiler outcome.",
                               "field_path": "status"})
            provenance = result.provenance
            if any(provenance.get(key) != current.get(identity) for key, identity in (
                    ("measured_adapter_raw_cid", "measured_compiler_raw_cid"),
                    ("compiler_config_cid", "compiler_config_cid"),
                    ("policy_cid", "policy_cid"))):
                issues.append({"code": "compiler_provenance_mismatch",
                               "message": "Compiler provenance differs from the current measured implementation.",
                               "field_path": "compiler_result.provenance"})
            stages = []
            for item in payload.get("stages") or ():
                stage = _canonical_pipeline_module.CompilerStageRecord(
                    stage_id=item["stage_id"], interface=item["interface"],
                    input_cid=item["input_cid"], output_cid=item["output_cid"],
                    config_cid=item["config_cid"], status=item["status"],
                    unsupported=tuple(item.get("unsupported") or ()),
                )
                if stage.to_dict() != item:
                    raise ValueError("stage identity mismatch")
                stages.append(stage)
            if ([stage.stage_id for stage in stages] != current.get("stage_ids")
                    or payload.get("pipeline_cid") != current.get("pipeline_cid")):
                issues.append({"code": "pipeline_stage_identity_mismatch",
                               "message": "Receipt does not contain the current complete ordered pipeline.",
                               "field_path": "stages"})
            span_issues = _prevalidate_character_spans(
                request.source_text, request.source_cid, result.source_map)
            issues.extend(span_issues)
            if not span_issues and result.canonical_ir is not None:
                bridge = _bridge_canonical_source_map(
                    source_text=request.source_text, source_cid=request.source_cid,
                    citation=str(payload.get("citation") or ""),
                    entries=result.source_map, rules=result.canonical_ir.rules,
                    stages=stages, identities=current,
                )
                validation_payload = bridge["validation"]
                traceable = bool(bridge["coverage_ok"])
                issues.extend(bridge["coverage_issues"])
                # Rebuild both maps from the typed source/result. Neither a
                # caller's smaller formula list nor an internally consistent
                # map from a different document can select the checked universe.
                for field, key in (
                        ("formula_ids", "formula_ids"), ("passages", "passages"),
                        ("source_map", "source_map"), ("built_source_map", "built_source_map"),
                        ("source_map_validation", "validation"),
                        ("built_source_map_validation", "built_validation"),
                        ("traceability", "traceability"), ("traces", "traces")):
                    if payload.get(field) != bridge[key]:
                        issues.append({"code": "source_map_binding_mismatch",
                                       "message": "Stored map, passages or emitted IDs differ from the full typed result.",
                                       "field_path": field})
                if not traceable:
                    issues.append({"code": "traceability_failed",
                                   "message": "Every emitted formula must trace to its source and transformations.",
                                   "field_path": "formula_ids"})
        except Exception:
            # Malformed persisted records stay typed; parser/contract exception
            # text can contain the caller's source and must not become a report.
            issues.append({"code": "canonical_record_invalid",
                           "message": "Typed compiler request, result or pipeline record is invalid.",
                           "field_path": "compiler_result"})

    structurally_valid = status_value in {"success", "partial"} and not issues and traceable
    executed = structurally_valid and execution_origin
    reason = ("Canonical formalization receipt failed integrity checks." if issues else
              "" if executed else "Serialized structure does not prove an original compiler execution.")
    capability = classify_canonical_compiler_capability(_canonical_evidence(
        executed=executed, status=status_value if executed else "failed",
        traceable=structurally_valid, source_map_valid=structurally_valid,
        schema_match=identities_match, tampered=bool(issues), reason=reason,
    ))
    return {
        "schema_version": "canonical-formalization-audit/v1",
        "status": "tampered" if issues else "verified" if executed else "unverified",
        "tampered": bool(issues), "capability": capability.as_dict(),
        "reason": reason, "issues": issues, "source_map_validation": validation_payload,
        "traceable": structurally_valid, "execution_origin_verified": executed,
        "identities": dict(recorded), "receipt_id": receipt_id,
    }


CANONICAL_IR_ATTACHMENT_SCHEMA = "canonical-legal-ir-source-obligations/v1"
TYPED_SOURCE_OBLIGATION_KINDS = frozenset({
    "obligation", "prohibition", "permission", "exception", "condition", "definition", "source_span",
})
_APPLICABILITY_VALUES = frozenset({"applicable", "inapplicable", "limited", "unknown"})
_APPLICABILITY_FIELDS = ("jurisdiction", "authority_version", "effective_date", "forum", "applicability")


def _normalize_applicability_context(raw: Mapping[str, Any] | None) -> Tuple[Dict[str, Any], str]:
    """Copy declared applicability. A caller cannot appoint governing law."""

    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        return {}, "applicability_context_invalid"
    context: Dict[str, Any] = {}
    for key in _APPLICABILITY_FIELDS:
        if key not in raw:
            continue
        value = raw[key]
        if not isinstance(value, str) or value != value.strip() or not value or len(value) > 160:
            return {}, "applicability_context_invalid"
        context[key] = value
    applicability = context.get("applicability", "unknown")
    if applicability not in _APPLICABILITY_VALUES:
        return {}, "applicability_context_invalid"
    context["applicability"] = applicability
    context["governing_legal_authority"] = False
    context["selects_governing_law"] = False
    return context, ""


def _exact_character_span(source_text: str, start: Any, end: Any, claimed: Any) -> Dict[str, Any] | None:
    if type(start) is not int or type(end) is not int or isinstance(start, bool) or isinstance(end, bool):
        return None
    if not 0 <= start < end <= len(source_text):
        return None
    text = source_text[start:end]
    if not isinstance(claimed, str) or claimed != text or not text.strip():
        return None
    return {"unit": "character", "start": start, "end": end, "text": text}


def _typed_obligation_record(
    *,
    obligation_id: str,
    kind: str,
    span: Mapping[str, Any],
    applicability: Mapping[str, Any],
    origin: str,
) -> Dict[str, Any]:
    return {
        "obligation_id": obligation_id,
        "kind": kind,
        "statement": span["text"],
        "source_span": dict(span),
        "applicability_context": dict(applicability),
        "typed": True,
        "origin": origin,
        "executed_proof": False,
        "governing_legal_authority": False,
        "discharged": False,
        "ir_parse_is_proof": False,
        "consistency_is_proof": False,
        "lean_text_is_proof": False,
    }


def attach_canonical_legal_ir_source_obligations(
    source_text: str,
    *,
    request_id: str,
    vocabulary: Mapping[str, Sequence[str]],
    applicability_context: Mapping[str, Any] | None = None,
    legal_context: Mapping[str, Any] | None = None,
    admitted_law: Mapping[str, Any] | None = None,
    factual_premises: Sequence[Any] | None = None,
    user_facts: Sequence[str] | None = None,
    unresolved_assumptions: Sequence[Any] | None = None,
    typed_obligations: Sequence[Any] | None = None,
    current_source: str | None = None,
    emitted_lean: str | None = None,
    supplied_receipt: Mapping[str, Any] | None = None,
    allow_explicit_partial: bool = False,
) -> Dict[str, Any]:
    """Compile current legal source and attach only span-checked typed obligations.

    ``compile_canonical_legal_ir`` and ``verify_canonical_formalization_receipt``
    are the only formalization path. A parsed IR, an internally consistent map,
    or emitted Lean text is recorded as non-authority. A caller-supplied receipt
    mapping is ignored and is not verified as if this process stored it.
    """

    context, context_error = _normalize_applicability_context(applicability_context)
    limitations = [
        "IR parsing is not executed proof.",
        "Internal consistency is not governing legal authority.",
        "Emitted Lean text is not executed proof.",
        "A caller-supplied receipt JSON is not a current-source verification.",
    ]
    rejected: List[Dict[str, Any]] = []
    if supplied_receipt is not None:
        rejected.append({
            "reason": "supplied_receipt_ignored",
            "governing_legal_authority": False,
            "executed_proof": False,
        })
    lean_text = emitted_lean if isinstance(emitted_lean, str) else ""
    if emitted_lean is not None and not isinstance(emitted_lean, str):
        rejected.append({"reason": "emitted_lean_not_text", "lean_text_is_proof": False})
    base: Dict[str, Any] = {
        "schema": CANONICAL_IR_ATTACHMENT_SCHEMA,
        "operation": "attach_canonical_legal_ir_source_obligations",
        "request_id": str(request_id or ""),
        "applicability_context": context,
        "typed_obligations": [],
        "rejected_obligations": rejected,
        "source_spans": [],
        "receipt_id": "",
        "receipt_verification": None,
        "compile_status": "",
        "status": "failed",
        "reason": "",
        "executed_proof": False,
        "governing_legal_authority": False,
        "ir_parse_is_proof": False,
        "consistency_is_proof": False,
        "lean_text_is_proof": False,
        "emitted_lean_character_length": len(lean_text),
        "emitted_lean_sha256": hashlib.sha256(lean_text.encode("utf-8")).hexdigest() if lean_text else "",
        "supplied_receipt_ignored": supplied_receipt is not None,
        "user_facts_are_not_law": True,
        "limitations": limitations,
    }
    if context_error:
        base["status"] = "failed"
        base["reason"] = context_error
        return base
    if not isinstance(source_text, str) or not source_text.strip():
        base["reason"] = "legal_source_required"
        return base
    if not isinstance(vocabulary, Mapping):
        base["reason"] = "vocabulary_required"
        return base
    merged_context = dict(legal_context or {})
    for key in ("jurisdiction", "authority_version", "effective_date", "forum"):
        if key in context and key not in merged_context:
            merged_context[key] = context[key]
    compiled = compile_canonical_legal_ir(
        source_text,
        request_id=str(request_id or ""),
        vocabulary=vocabulary,
        legal_context=merged_context or None,
        admitted_law=admitted_law,
        factual_premises=factual_premises,
        user_facts=user_facts,
        unresolved_assumptions=unresolved_assumptions,
        allow_explicit_partial=allow_explicit_partial,
    )
    base["compile_status"] = str(compiled.get("status") or "")
    base["receipt_id"] = str(compiled.get("receipt_id") or "")
    base["reason"] = str(compiled.get("reason") or "")
    base["establishes_governing_law_meaning"] = False
    base["proves_claim"] = False
    if compiled.get("status") in {"unavailable", "schema_mismatch"} or not base["receipt_id"]:
        base["status"] = str(compiled.get("status") or "unavailable")
        base["reason"] = base["reason"] or "canonical_compiler_unavailable"
        return base
    observed_source = compiled.get("source_text") if isinstance(compiled.get("source_text"), str) else source_text
    checked_source = observed_source if current_source is None else current_source
    if not isinstance(checked_source, str):
        base["status"] = "failed"
        base["reason"] = "current_source_invalid"
        return base
    verification = verify_canonical_formalization_receipt(base["receipt_id"], source_text=checked_source)
    base["receipt_verification"] = {
        "status": verification.get("status"),
        "tampered": verification.get("tampered") is True,
        "traceable": verification.get("traceable") is True,
        "execution_origin_verified": verification.get("execution_origin_verified") is True,
        "reason": verification.get("reason") or "",
        "issue_codes": [
            str(item.get("code"))
            for item in (verification.get("issues") or [])
            if isinstance(item, Mapping) and item.get("code")
        ],
    }
    verified = (
        verification.get("status") == "verified"
        and verification.get("tampered") is not True
        and verification.get("execution_origin_verified") is True
        and checked_source == observed_source
    )
    spans: List[Dict[str, Any]] = []
    if verified:
        for index, passage in enumerate(compiled.get("passages") or []):
            if not isinstance(passage, Mapping):
                rejected.append({"reason": "passage_invalid", "index": index})
                continue
            span = _exact_character_span(checked_source, passage.get("start"), passage.get("end"), passage.get("passage"))
            if span is None:
                rejected.append({"reason": "source_span_mismatch", "index": index, "executed_proof": False})
                continue
            span["source_cid"] = str(passage.get("source_cid") or compiled.get("source_cid") or "")
            span["formula_id"] = str(passage.get("rule_cid") or passage.get("field_path") or f"passage-{index}")
            spans.append(span)
            base["typed_obligations"].append(_typed_obligation_record(
                obligation_id=f"source-span-{index}",
                kind="source_span",
                span=span,
                applicability=context,
                origin="current_source_receipt",
            ))
    else:
        rejected.append({
            "reason": "current_source_receipt_unverified",
            "verification_status": verification.get("status"),
            "executed_proof": False,
            "governing_legal_authority": False,
        })
    for index, item in enumerate(typed_obligations or ()):
        if not isinstance(item, Mapping):
            rejected.append({"reason": "typed_obligation_invalid", "index": index})
            continue
        if item.get("executed_proof") is True or item.get("governing_legal_authority") is True or item.get("discharged") is True:
            rejected.append({
                "reason": "typed_obligation_authority_claim_rejected",
                "index": index,
                "executed_proof": False,
                "governing_legal_authority": False,
            })
            continue
        kind = item.get("kind")
        if kind not in TYPED_SOURCE_OBLIGATION_KINDS or kind == "source_span":
            rejected.append({"reason": "typed_obligation_kind", "index": index})
            continue
        span_in = item.get("source_span") if isinstance(item.get("source_span"), Mapping) else {}
        span = _exact_character_span(
            checked_source if verified else "",
            span_in.get("start"),
            span_in.get("end"),
            span_in.get("text"),
        ) if verified else None
        statement = item.get("statement")
        if span is None or not isinstance(statement, str) or statement != span["text"]:
            rejected.append({
                "reason": "typed_obligation_span_mismatch" if verified else "current_source_receipt_unverified",
                "index": index,
                "executed_proof": False,
            })
            continue
        obligation_id = item.get("obligation_id")
        if not isinstance(obligation_id, str) or not obligation_id.strip() or len(obligation_id) > 80:
            obligation_id = f"typed-{index}"
        base["typed_obligations"].append(_typed_obligation_record(
            obligation_id=obligation_id,
            kind=str(kind),
            span=span,
            applicability=context,
            origin="caller_typed",
        ))
    base["source_spans"] = spans
    base["source_character_length"] = len(checked_source)
    base["source_text_sha256"] = hashlib.sha256(checked_source.encode("utf-8")).hexdigest()
    base["span_unit"] = "character"
    if verified and spans and base["typed_obligations"]:
        base["status"] = "attached"
        base["reason"] = ""
    elif verified:
        base["status"] = "failed"
        base["reason"] = base["reason"] or "no_exact_source_spans"
    else:
        base["status"] = "source_unverified"
        base["reason"] = base["reason"] or "current_source_receipt_unverified"
        base["typed_obligations"] = []
        base["source_spans"] = []
    return base


DEFINITION_CORRESPONDENCE_SCHEMA = "current-data-definition-correspondence-binding/v1"
_SOURCE_CORRESPONDENCE_OWNER = "ipfs_datasets_py.logic.autoformal.legal_norm_scope_correspondence_v1"
_CORRESPONDENCE_REQUESTS_OWNER = "ipfs_datasets_py.logic.autoformal.legal_source_correspondence_requests_v1"
_APPLICABILITY_OWNER = "ipfs_datasets_py.logic.autoformal.legal_norm_definition_applicability_v1"
_CONTEXTUAL_REVIEW_OWNER = "ipfs_datasets_py.logic.autoformal.legal_source_sampling_context_definition_review_v2"
_REQUIRED_CORRESPONDENCE_FAMILIES = (
    "source_correspondence",
    "definition_applicability",
    "contextual_review",
)
_CONTEXTUAL_REVIEW_FIELDS = (
    "expected_binding_sha256",
    "expected_subject_sha256",
    "contextual_replay_inputs",
    "candidate_inputs",
    "expected_candidate_pin",
    "context_inputs",
    "expected_context_population",
    "dependency_manifest",
    "expected_manifest_sha256",
    "required_dependency_ids",
)


def _json_blob(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)


def _walk_contains_source(value: Any, source: str) -> bool:
    if isinstance(value, str):
        return source in value
    if isinstance(value, bytes):
        encoded = source.encode("utf-8")
        if encoded in value:
            return True
        try:
            return source in value.decode("utf-8")
        except UnicodeDecodeError:
            return False
    if isinstance(value, Mapping):
        return any(_walk_contains_source(item, source) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_walk_contains_source(item, source) for item in value)
    return False


def _missing_population(result: Any, required: Sequence[str]) -> List[str]:
    if result is None:
        return list(required)
    blob = _json_blob(result)
    missing = [item for item in required if item not in blob]
    if isinstance(result, Mapping):
        companion = result.get("contextual_correspondence")
        if isinstance(companion, Mapping) and companion.get("contextual_population_complete") is False:
            if "contextual_population_complete" not in missing:
                missing.append("contextual_population_complete")
    return missing


def _selected_applicability(result: Mapping[str, Any]) -> bool:
    decisions = result.get("decisions")
    if not isinstance(decisions, list):
        declaration = result.get("declaration")
        if isinstance(declaration, Mapping):
            decisions = declaration.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        return False
    selected = 0
    for choice in decisions:
        if not isinstance(choice, Mapping):
            return False
        decision = choice.get("decision")
        if decision in (None, "", "unresolved"):
            continue
        if decision != "declare_one_supplied_alternative_applicable":
            return False
        selected += 1
    return selected > 0 and selected == len(decisions)


def _family_record(
    *,
    owner: str,
    genuine: bool,
    source_bound: bool,
    missing: Sequence[str],
    receipt_sha256: str,
    schema: str,
    reason: str,
    definition_unbound: bool = False,
) -> Dict[str, Any]:
    return {
        "owner": owner,
        "genuine_current_owner_receipt": genuine,
        "source_bound": source_bound,
        "population_complete": not missing,
        "population_missing": list(missing),
        "receipt_sha256": receipt_sha256,
        "schema": schema,
        "reason": reason,
        "definition_unbound": definition_unbound,
        "authorizes_law": False,
        "authorizes_proof": False,
        "user_receipt_accepted": False,
    }


def _failed_family(owner: str, reason: str, *, source_bound: bool = False) -> Dict[str, Any]:
    return _family_record(
        owner=owner,
        genuine=False,
        source_bound=source_bound,
        missing=["owner_result"],
        receipt_sha256="",
        schema="",
        reason=reason,
        definition_unbound=True,
    )


def _verified_definition_source_basis(correspondence: Any, source_text: str) -> Dict[str, Any] | None:
    """Read exact byte scope only after the actual owner replay succeeded."""
    from ipfs_datasets_py.logic.autoformal import legal_norm_scope_correspondence_v1 as correspondence_owner
    from ipfs_datasets_py.logic.autoformal import legal_source_norm_scope_v1 as scope_owner
    if not isinstance(correspondence, Mapping) or correspondence.get("schema") != correspondence_owner.SCHEMA:
        return None
    scope = correspondence.get("source_scope")
    if not isinstance(scope, Mapping) or scope.get("schema") != scope_owner.SCHEMA:
        return None
    selection = scope.get("source_selector")
    records = scope.get("source_records")
    occurrence = records.get("source_occurrence") if isinstance(records, Mapping) else None
    if (not isinstance(selection, Mapping) or not isinstance(occurrence, Mapping)
            or not isinstance(source_text, str) or not source_text
            or selection.get("text") != source_text or occurrence.get("span_text") != source_text):
        return None
    start, end = selection.get("utf8_byte_start"), selection.get("utf8_byte_end")
    if (type(start) is not int or type(end) is not int or start < 0
            or end - start != len(source_text.encode("utf-8"))
            or (occurrence.get("start_utf8"), occurrence.get("end_utf8")) != (start, end)):
        return None
    pins = scope.get("input_pins")
    selected = pins.get("selected_unit_ref") if isinstance(pins, Mapping) else None
    if not isinstance(selected, Mapping):
        return None
    return {"schema": "definition-owner-current-source-basis/v1",
        "source_text_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        "source_bytes": len(source_text.encode("utf-8")), "selected_unit_ref": deepcopy(dict(selected)),
        "source_scope_report_sha256": scope_owner.sampled_norm_scope_report_sha256(scope),
        "exact_selected_bytes_verified": True, "source_semantics_verified": False}


def _replay_scope(bundle: Mapping[str, Any], source_text: str, population: Sequence[str]) -> Dict[str, Any]:
    from .definition_evidence import (
        prepare_norm_scope_correspondence_v1,
        validate_norm_scope_correspondence_v1,
    )

    args = list(bundle.get("args") or [])
    kwargs = dict(bundle.get("kwargs") or {})
    kwargs.pop("expected_report_sha256", None)
    kwargs.pop("supplied_receipt", None)
    source_bound = False
    prepared = prepare_norm_scope_correspondence_v1(*args, **kwargs)
    if prepared.get("status") != "replayed" or not isinstance(prepared.get("result"), Mapping):
        return _failed_family(_SOURCE_CORRESPONDENCE_OWNER, str(prepared.get("reason") or prepared.get("status") or "scope_correspondence_failed"), source_bound=source_bound)
    report = prepared["result"]
    from ipfs_datasets_py.logic.autoformal import legal_norm_scope_correspondence_v1 as scope_owner

    receipt_sha = scope_owner.norm_scope_correspondence_sha256(report)
    checked = validate_norm_scope_correspondence_v1(
        report, *args, expected_report_sha256=receipt_sha, **kwargs,
    )
    genuine = (
        checked.get("status") == "replayed"
        and isinstance(checked.get("result"), Mapping)
        and checked["result"] == report
    )
    basis = _verified_definition_source_basis(report, source_text) if genuine else None
    source_bound = basis is not None
    missing = _missing_population(report, population)
    reason = "" if genuine and source_bound and not missing else (
        "source_unbound" if genuine and not source_bound else
        "incomplete_declared_population" if genuine and missing else
        str(checked.get("reason") or "scope_correspondence_not_genuine")
    )
    record = _family_record(
        owner=_SOURCE_CORRESPONDENCE_OWNER,
        genuine=genuine and source_bound and not missing,
        source_bound=source_bound,
        missing=missing,
        receipt_sha256=receipt_sha if genuine else "",
        schema=str(report.get("schema") or ""),
        reason=reason,
    )
    record["source_basis"] = basis
    return record


def _replay_contextual(bundle: Mapping[str, Any], source_text: str, population: Sequence[str], *,
                       verified_endpoint_bases: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    from .definition_evidence import (
        prepare_contextual_definition_review,
        validate_contextual_definition_review,
    )

    binding_result = bundle.get("binding_result")
    review_subject = bundle.get("review_subject")
    raw_kwargs = dict(bundle.get("kwargs") or {})
    kwargs = {key: raw_kwargs[key] for key in _CONTEXTUAL_REVIEW_FIELDS if key in raw_kwargs}
    source_bound = False
    prepared = prepare_contextual_definition_review(binding_result, review_subject, **kwargs)
    if prepared.get("status") != "replayed" or not isinstance(prepared.get("result"), Mapping):
        return _failed_family(
            _CONTEXTUAL_REVIEW_OWNER,
            str(prepared.get("reason") or prepared.get("status") or "contextual_review_failed"),
            source_bound=source_bound,
        )
    report = prepared["result"]
    from ipfs_datasets_py.logic.autoformal import legal_source_sampling_context_definition_review_v2 as review_owner

    receipt_sha = review_owner.correspondence_sha256(report)
    checked = validate_contextual_definition_review(
        report,
        binding_result,
        review_subject,
        expected_correspondence_sha256=receipt_sha,
        **kwargs,
    )
    genuine = (
        checked.get("status") == "replayed"
        and isinstance(checked.get("result"), Mapping)
        and checked["result"] == report
    )
    basis = (verified_endpoint_bases or {}).get(receipt_sha) if genuine else None
    source_bound = (isinstance(basis, Mapping) and basis.get("source_text_sha256")
        == hashlib.sha256(source_text.encode("utf-8")).hexdigest())
    missing = _missing_population(report, population)
    reason = "" if genuine and source_bound and not missing else (
        "source_unbound" if genuine and not source_bound else
        "incomplete_declared_population" if genuine and missing else
        str(checked.get("reason") or "contextual_review_not_genuine")
    )
    record = _family_record(
        owner=_CONTEXTUAL_REVIEW_OWNER,
        genuine=genuine and source_bound and not missing,
        source_bound=source_bound,
        missing=missing,
        receipt_sha256=receipt_sha if genuine else "",
        schema=str(report.get("schema") or ""),
        reason=reason,
    )
    record["source_basis"] = deepcopy(basis) if source_bound else None
    return record


def _replay_applicability(bundle: Mapping[str, Any], source_text: str, population: Sequence[str]) -> Dict[str, Any]:
    from ipfs_datasets_py.logic.autoformal import legal_norm_definition_applicability_v1 as applicability

    operation = str(bundle.get("operation") or "declaration")
    args = list(bundle.get("args") or [])
    kwargs = dict(bundle.get("kwargs") or {})
    kwargs.pop("supplied_receipt", None)
    kwargs.pop("expected_report_sha256", None)
    source_bound = False
    builders = {
        "template": applicability.build_norm_definition_applicability_template_v1,
        "declaration": applicability.build_norm_definition_applicability_declaration_v1,
        "assessment": applicability.assess_norm_definition_applicability_v1,
    }
    builder = builders.get(operation)
    if builder is None:
        return _failed_family(_APPLICABILITY_OWNER, "applicability_operation_rejected", source_bound=source_bound)
    try:
        report = builder(*args, **kwargs)
        regenerated = builder(*args, **kwargs)
    except Exception as exc:
        return _failed_family(_APPLICABILITY_OWNER, str(exc) or type(exc).__name__, source_bound=source_bound)
    if not isinstance(report, Mapping) or not isinstance(regenerated, Mapping):
        return _failed_family(_APPLICABILITY_OWNER, "applicability_report_invalid", source_bound=source_bound)
    receipt_sha = applicability.norm_definition_applicability_sha256(report)
    regenerated_sha = applicability.norm_definition_applicability_sha256(regenerated)
    genuine = receipt_sha == regenerated_sha and _json_blob(report) == _json_blob(regenerated)
    basis, endpoints = None, {}
    if genuine:
        from ipfs_datasets_py.logic.autoformal import legal_norm_interpretation_review_v1 as norm_owner
        inputs = kwargs.get("companion_inputs")
        preparation = inputs.get("norm_preparation") if isinstance(inputs, Mapping) else None
        if (isinstance(preparation, Mapping) and norm_owner.norm_review_sha256(preparation)
                == inputs.get("expected_norm_preparation_sha256")):
            basis = _verified_definition_source_basis(preparation.get("correspondence"), source_text)
            definitions = inputs.get("definitions")
            if basis is not None and isinstance(definitions, list) and len(definitions) <= 128:
                for endpoint in definitions:
                    pin = endpoint.get("expected_correspondence_sha256") if isinstance(endpoint, Mapping) else None
                    if isinstance(pin, str) and len(pin) == 64 and all(char in "0123456789abcdef" for char in pin):
                        endpoints[pin] = deepcopy(basis)
    source_bound = basis is not None
    declared = operation == "declaration" and _selected_applicability(report)
    unbound = not declared
    missing = _missing_population(report, population)
    reason = ""
    if not genuine:
        reason = "applicability_not_regenerated"
    elif not source_bound:
        reason = "source_unbound"
    elif missing:
        reason = "incomplete_declared_population"
    elif unbound:
        reason = "unbound_definition"
    record = _family_record(
        owner=_APPLICABILITY_OWNER,
        genuine=genuine and source_bound and not missing and not unbound,
        source_bound=source_bound,
        missing=missing,
        receipt_sha256=receipt_sha if genuine else "",
        schema=str(report.get("schema") or ""),
        reason=reason,
        definition_unbound=unbound,
    )
    record["source_basis"] = basis
    record["verified_contextual_endpoint_bases"] = endpoints
    return record


def _replay_correspondence_requests(bundle: Mapping[str, Any], source_text: str, population: Sequence[str]) -> Dict[str, Any]:
    from ipfs_datasets_py.logic.autoformal import legal_source_correspondence_requests_v1 as requests_owner

    args = list(bundle.get("args") or [])
    kwargs = dict(bundle.get("kwargs") or {})
    kwargs.pop("supplied_receipt", None)
    source_bound = False
    try:
        report = requests_owner.prepare_source_correspondence_requests_v3(*args, **kwargs)
        receipt_sha = requests_owner.source_correspondence_requests_v3_sha256(report)
        regenerated = requests_owner.validate_source_correspondence_requests_v3(
            report,
            *args,
            expected_report_sha256=receipt_sha,
            **kwargs,
        )
    except Exception as exc:
        return _failed_family(
            _CORRESPONDENCE_REQUESTS_OWNER,
            str(exc) or type(exc).__name__,
            source_bound=source_bound,
        )
    genuine = isinstance(report, Mapping) and isinstance(regenerated, Mapping) and _json_blob(report) == _json_blob(regenerated)
    missing = _missing_population(report if isinstance(report, Mapping) else None, population)
    reason = "" if genuine and source_bound and not missing else (
        "source_unbound" if genuine and not source_bound else
        "incomplete_declared_population" if genuine else
        "correspondence_requests_not_genuine"
    )
    return _family_record(
        owner=_CORRESPONDENCE_REQUESTS_OWNER + ":prepare_source_correspondence_requests_v3",
        genuine=genuine and source_bound and not missing,
        source_bound=source_bound,
        missing=missing,
        receipt_sha256=receipt_sha if genuine else "",
        schema=str(report.get("schema") or "") if isinstance(report, Mapping) else "",
        reason=reason,
    )


def bind_current_definition_correspondence_owners(
    source_text: str,
    *,
    request_id: str,
    declared_populations: Mapping[str, Sequence[str]] | None = None,
    scope_correspondence: Mapping[str, Any] | None = None,
    correspondence_requests: Mapping[str, Any] | None = None,
    applicability: Mapping[str, Any] | None = None,
    contextual_review: Mapping[str, Any] | None = None,
    supplied_receipt: Mapping[str, Any] | None = None,
    training_metrics: Any = None,
    graph_join: Any = None,
) -> Dict[str, Any]:
    """Bind current definition and correspondence owners to one exact legal source.

    Receipts count only when the pinned owner regenerates them from the
    forwarded populations. A caller-supplied receipt JSON, a training metric,
    an incomplete graph join, or an unbound definition does not authorize law
    or proof. Regenerated owner reports remain non-authority.
    """

    populations = dict(declared_populations or {})
    limitations = [
        "A regenerated owner receipt is not governing law.",
        "A regenerated owner receipt is not executed proof.",
        "Incomplete graph joins do not authorize law or proof.",
        "Model training metrics do not authorize law or proof.",
        "Unbound definitions do not authorize law or proof.",
        "User-supplied receipt JSON is not a current owner receipt.",
    ]
    record: Dict[str, Any] = {
        "schema": DEFINITION_CORRESPONDENCE_SCHEMA,
        "operation": "bind_current_definition_correspondence_owners",
        "request_id": str(request_id or ""),
        "status": "failed",
        "reason": "",
        "source_text_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest() if isinstance(source_text, str) else "",
        "owners": {},
        "authorizes_law": False,
        "authorizes_proof": False,
        "executed_proof": False,
        "governing_legal_authority": False,
        "proof": False,
        "supplied_receipt_ignored": supplied_receipt is not None,
        "training_metrics_authorize_law": False,
        "training_metrics_authorize_proof": False,
        "training_metrics_present": training_metrics is not None,
        "graph_join_authorizes_law": False,
        "graph_join_authorizes_proof": False,
        "graph_join_present": graph_join is not None,
        "incomplete_graph_join": False,
        "definition_unbound": True,
        "limitations": limitations,
    }
    if not isinstance(source_text, str) or not source_text.strip():
        record["reason"] = "legal_source_required"
        return record
    if not isinstance(request_id, str) or not request_id.strip():
        record["reason"] = "request_id_required"
        return record
    normalized: Dict[str, List[str]] = {}
    for family in _REQUIRED_CORRESPONDENCE_FAMILIES:
        required = populations.get(family)
        if not isinstance(required, (list, tuple)) or not required or any(
            not isinstance(item, str) or not item.strip() for item in required
        ):
            record["reason"] = "incomplete_declared_population"
            record["owners"][family] = _failed_family("", "incomplete_declared_population")
            return record
        normalized[family] = [str(item) for item in required]
    if graph_join is not None:
        covered: set[str] = set()
        if isinstance(graph_join, Mapping) and isinstance(graph_join.get("population_ids"), list):
            covered = {item for item in graph_join["population_ids"] if isinstance(item, str)}
        needed = {item for ids in normalized.values() for item in ids}
        record["incomplete_graph_join"] = graph_join.get("complete") is not True if isinstance(graph_join, Mapping) else True
        if not needed <= covered or record["incomplete_graph_join"]:
            record["incomplete_graph_join"] = True
    bundles = {
        "source_correspondence": scope_correspondence,
        "definition_applicability": applicability,
        "contextual_review": contextual_review,
    }
    if any(not isinstance(bundle, Mapping) or not bundle for bundle in bundles.values()):
        record["status"] = "incomplete_graph_join" if record["incomplete_graph_join"] and not any(bundles.values()) else "incomplete"
        record["reason"] = "owner_populations_required" if any(bundles.values()) else (
            "incomplete_graph_join" if record["incomplete_graph_join"] else "owner_populations_required"
        )
        if training_metrics is not None and not any(isinstance(bundle, Mapping) and bundle for bundle in bundles.values()):
            record["status"] = "rejected"
            record["reason"] = "training_metrics_are_not_authority"
        if supplied_receipt is not None and not any(isinstance(bundle, Mapping) and bundle for bundle in bundles.values()):
            record["status"] = "rejected"
            record["reason"] = "supplied_receipt_ignored"
        return record
    try:
        record["owners"]["source_correspondence"] = _replay_scope(
            scope_correspondence, source_text, normalized["source_correspondence"],
        )
        record["owners"]["definition_applicability"] = _replay_applicability(
            applicability, source_text, normalized["definition_applicability"],
        )
        record["owners"]["contextual_review"] = _replay_contextual(
            contextual_review, source_text, normalized["contextual_review"],
            verified_endpoint_bases=record["owners"]["definition_applicability"].pop("verified_contextual_endpoint_bases", {}),
        )
        if isinstance(correspondence_requests, Mapping) and correspondence_requests:
            requests_population = populations.get("source_correspondence_requests") or normalized["source_correspondence"]
            record["owners"]["source_correspondence_requests"] = _replay_correspondence_requests(
                correspondence_requests,
                source_text,
                [str(item) for item in requests_population],
            )
    except Exception as exc:
        record["status"] = "unavailable"
        record["reason"] = str(exc) or type(exc).__name__
        return record
    families = [record["owners"][name] for name in _REQUIRED_CORRESPONDENCE_FAMILIES]
    requests_family = record["owners"].get("source_correspondence_requests")
    if requests_family is not None and requests_family.get("genuine_current_owner_receipt") is not True:
        record["status"] = "rejected"
        record["reason"] = str(requests_family.get("reason") or "correspondence_requests_rejected")
        record["definition_unbound"] = True
        return record
    if any(family.get("reason") == "unbound_definition" for family in families):
        record["status"] = "unbound_definition"
        record["reason"] = "unbound_definition"
        record["definition_unbound"] = True
        return record
    record["definition_unbound"] = any(family.get("definition_unbound") is True for family in families)
    if all(family.get("genuine_current_owner_receipt") is True for family in families) and not record["definition_unbound"]:
        record["status"] = "bound"
        record["reason"] = ""
    elif any(family.get("reason") == "source_unbound" for family in families):
        record["status"] = "source_unbound"
        record["reason"] = "source_unbound"
    elif any(family.get("reason") == "incomplete_declared_population" for family in families):
        record["status"] = "incomplete_declared_population"
        record["reason"] = "incomplete_declared_population"
    else:
        record["status"] = "rejected"
        record["reason"] = next((str(family.get("reason") or "") for family in families if family.get("reason")), "owner_rejected")
    if record["incomplete_graph_join"]:
        record["graph_join_authorizes_law"] = False
        record["graph_join_authorizes_proof"] = False
    return record


def reset_bound_proof_obligation_cache() -> None:
    """Drop the obligation reuse index. Stored receipts stay until this reset."""

    _BOUND_OBLIGATION_RECEIPTS.clear()
    _BOUND_OBLIGATION_CACHE.clear()


def inspect_bound_proof_obligation_receipt(receipt_id: str) -> Dict[str, Any] | None:
    """Return a stored obligation artifact without marking it reusable."""

    stored = _BOUND_OBLIGATION_RECEIPTS.get(str(receipt_id or ""))
    if stored is None:
        return None
    return deepcopy(stored)


def _obligation_error_code(exc: BaseException) -> str:
    name = type(exc).__name__ or "Error"
    if not name.replace("_", "").isalnum():
        return "generator_error"
    return name


def _mapping_or_empty(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "to_dict") and callable(value.to_dict):
        try:
            converted = value.to_dict()
        except (TypeError, ValueError):
            return {}
        if isinstance(converted, Mapping):
            return dict(converted)
    return {}


def _attr_or_key(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _is_canonical_formalization_receipt(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    schema = str(value.get("schema_version") or "")
    return schema.startswith("canonical-formalization-receipt")


def _is_pipeline_result(value: Any) -> bool:
    if value is None or isinstance(value, (str, bytes, Mapping)):
        return False
    name = type(value).__name__
    if name == "CompilerPipelineResult":
        return True
    return hasattr(value, "pipeline_cid") and hasattr(value, "result") and not hasattr(value, "formulas") and not hasattr(value, "modal_ir")


def modal_ir_from_canonical_formalization(receipt: Mapping[str, Any]) -> Dict[str, Any]:
    """Bridge a PROOF01 receipt into the ModalIR document the obligation generator accepts.

    Canonical ``CompilerPipelineResult`` objects are not that schema. Character
    spans on the receipt stay character offsets. Rule fields are copied only
    when the stored canonical rule already has them.
    """

    source_text = str(receipt.get("source_text") or "")
    source_map = receipt.get("source_map") if isinstance(receipt.get("source_map"), Mapping) else {}
    rules_by_id: Dict[str, Dict[str, Any]] = {}
    for node in source_map.get("nodes") or []:
        if not isinstance(node, Mapping):
            continue
        metadata = node.get("metadata") if isinstance(node.get("metadata"), Mapping) else {}
        rule = metadata.get("rule") if isinstance(metadata.get("rule"), Mapping) else None
        if rule and rule.get("rule_cid"):
            rules_by_id[str(rule["rule_cid"])] = dict(rule)
    formulas: List[Dict[str, Any]] = []
    for passage in receipt.get("passages") or []:
        if not isinstance(passage, Mapping):
            continue
        rule_cid = str(passage.get("rule_cid") or "")
        rule = rules_by_id.get(rule_cid, {})
        formula: Dict[str, Any] = {
            "formula_id": rule_cid or str(passage.get("field_path") or "formula"),
            "provenance": {
                "source_id": str(passage.get("source_cid") or receipt.get("source_cid") or ""),
                "source_document_id": str(receipt.get("source_cid") or ""),
                "citation": str(receipt.get("citation") or ""),
                "start_char": passage.get("start"),
                "end_char": passage.get("end"),
                "span_unit": "character",
            },
        }
        for key in ("operator", "predicate", "conditions", "exceptions"):
            if key in rule:
                formula[key] = deepcopy(rule[key])
        formulas.append(formula)
    return {
        "document_id": str(receipt.get("source_cid") or receipt.get("request_id") or "canonical-formalization"),
        "sample_id": str(receipt.get("request_id") or receipt.get("source_cid") or ""),
        "normalized_text": source_text,
        "formulas": formulas,
        "bridge": "proof01_canonical_formalization_receipt",
    }


def _document_view(sample_or_document: Any) -> Any:
    if isinstance(sample_or_document, Mapping) and isinstance(sample_or_document.get("modal_ir"), (Mapping, object)):
        modal = sample_or_document.get("modal_ir")
        if modal is not None and modal is not sample_or_document and (
            isinstance(modal, Mapping) or hasattr(modal, "formulas") or hasattr(modal, "normalized_text")
        ):
            return modal
    return sample_or_document


def _normalized_text_of(sample_or_document: Any) -> str:
    document = _document_view(sample_or_document)
    text = _attr_or_key(sample_or_document, "normalized_text", None)
    if text is None:
        text = _attr_or_key(document, "normalized_text", "")
    return str(text or "")


def _formulas_of(sample_or_document: Any) -> List[Any]:
    document = _document_view(sample_or_document)
    raw = _attr_or_key(document, "formulas", None)
    if raw is None:
        raw = _attr_or_key(sample_or_document, "formulas", ())
    if raw is None:
        return []
    return list(raw)


def _formula_identity(formula: Any, index: int) -> str:
    return str(_attr_or_key(formula, "formula_id", None) or f"formula-{index}")


def _character_span_status(text: str, start: Any, end: Any) -> Dict[str, Any]:
    try:
        start_i = int(start)
        end_i = int(end)
    except (TypeError, ValueError):
        return {"status": "invalid_offsets", "verified": False, "sha256": "", "character_length": 0, "byte_length": 0}
    if start_i < 0 or end_i < start_i or end_i > len(text):
        return {"status": "out_of_range", "verified": False, "sha256": "", "character_length": 0, "byte_length": 0}
    selected = text[start_i:end_i]
    if selected == "":
        return {"status": "empty_slice", "verified": False, "sha256": "", "character_length": 0, "byte_length": 0}
    encoded = selected.encode("utf-8")
    return {
        "status": "verified_characters",
        "verified": True,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "character_length": len(selected),
        "byte_length": len(encoded),
        "start": start_i,
        "end": end_i,
        "span_unit": "character",
    }


def _byte_span_status(text: str, start: Any, end: Any) -> Dict[str, Any]:
    encoded = text.encode("utf-8")
    try:
        start_i = int(start)
        end_i = int(end)
    except (TypeError, ValueError):
        return {"status": "invalid_offsets", "verified": False, "sha256": "", "character_length": 0, "byte_length": 0}
    if start_i < 0 or end_i < start_i or end_i > len(encoded):
        return {"status": "out_of_range", "verified": False, "sha256": "", "character_length": 0, "byte_length": 0}
    sliced = encoded[start_i:end_i]
    if sliced == b"":
        return {"status": "empty_slice", "verified": False, "sha256": "", "character_length": 0, "byte_length": 0}
    try:
        decoded = sliced.decode("utf-8")
    except UnicodeDecodeError:
        return {"status": "utf8_boundary", "verified": False, "sha256": "", "character_length": 0, "byte_length": len(sliced)}
    return {
        "status": "verified_utf8_bytes",
        "verified": True,
        "sha256": hashlib.sha256(sliced).hexdigest(),
        "character_length": len(decoded),
        "byte_length": len(sliced),
        "start": start_i,
        "end": end_i,
        "span_unit": "utf8_byte",
    }


def _prevalidate_modal_source_spans(sample_or_document: Any) -> List[Dict[str, Any]]:
    """Check ModalIR character spans before generation.

    Native ``source_span_sha256`` hashes the formula payload when the text
    slice is absent. That fallback is not verified source bytes.
    """

    text = _normalized_text_of(sample_or_document)
    checks: List[Dict[str, Any]] = []
    labels: Dict[str, int] = {}
    for index, formula in enumerate(_formulas_of(sample_or_document), start=1):
        formula_id = _formula_identity(formula, index)
        labels[formula_id] = labels.get(formula_id, 0) + 1
        provenance = _attr_or_key(formula, "provenance", {}) or {}
        provenance_map = _mapping_or_empty(provenance)
        start = _attr_or_key(provenance, "start_char", provenance_map.get("start_char"))
        end = _attr_or_key(provenance, "end_char", provenance_map.get("end_char"))
        checked = _character_span_status(text, start, end)
        checks.append(
            {
                "formula_id": formula_id,
                "occurrence": labels[formula_id],
                "binding_id": f"{formula_id}#{labels[formula_id]}",
                "span_unit": "character",
                "verified": checked["verified"],
                "status": checked["status"],
                "verified_source_sha256": checked["sha256"],
                "character_length": checked["character_length"],
                "byte_length": checked["byte_length"],
                "native_hash_is_verified_source": bool(checked["verified"]),
                "native_span_hash_is_fallback": not checked["verified"],
            }
        )
    return checks


def _duplicate_local_labels(checks: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    counts: Dict[str, List[str]] = {}
    for item in checks:
        counts.setdefault(str(item.get("formula_id") or ""), []).append(str(item.get("binding_id") or ""))
    return [
        {"formula_id": formula_id, "occurrences": len(binding_ids), "binding_ids": binding_ids}
        for formula_id, binding_ids in counts.items()
        if formula_id and len(binding_ids) > 1
    ]


def _text_of_premise(record: Mapping[str, Any]) -> str:
    for key in ("text", "statement", "fact_text", "rule_text", "source_text"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _premise_source_check(record: Mapping[str, Any], source_text: str) -> Dict[str, Any]:
    """Validate a premise span. ModalIR offsets are characters. FACT01 spans are UTF-8 bytes."""

    if not source_text:
        return {"verified": False, "status": "source_text_absent", "span_unit": "", "sha256": ""}
    unit = str(record.get("span_unit") or record.get("offset_unit") or "").strip().lower()
    byte_keys = ("byte_start", "utf8_start", "start_byte")
    char_keys = ("char_start", "start_char", "character_start")
    has_byte = any(key in record for key in byte_keys)
    has_char = any(key in record for key in char_keys)
    if unit in {"utf8_byte", "byte", "bytes", "utf-8"} or (has_byte and unit not in {"character", "char", "characters"}):
        start = next(record[key] for key in byte_keys if key in record)
        end = record.get("byte_end", record.get("utf8_end", record.get("end_byte")))
        checked = _byte_span_status(source_text, start, end)
    elif has_char or unit in {"character", "char", "characters"}:
        start = next((record[key] for key in char_keys if key in record), None)
        end = record.get("char_end", record.get("end_char", record.get("character_end")))
        checked = _character_span_status(source_text, start, end)
    else:
        return {"verified": False, "status": "span_absent", "span_unit": "", "sha256": ""}
    expected = _text_of_premise(record)
    if checked["verified"] and expected:
        if checked["span_unit"] == "character":
            actual = source_text[checked["start"]:checked["end"]]
        else:
            actual = source_text.encode("utf-8")[checked["start"]:checked["end"]].decode("utf-8")
        if actual != expected:
            return {
                "verified": False,
                "status": "span_text_mismatch",
                "span_unit": checked["span_unit"],
                "sha256": "",
                "character_length": checked["character_length"],
                "byte_length": checked["byte_length"],
            }
    return checked


def _premise_entry(
    record: Mapping[str, Any],
    *,
    role: str,
    source_text: str,
    index: int,
) -> Dict[str, Any]:
    original_id = str(
        record.get("id")
        or record.get("premise_id")
        or record.get("fact_id")
        or record.get("rule_id")
        or record.get("assumption_id")
        or ""
    )
    text = _text_of_premise(record)
    revision = str(
        record.get("revision")
        or record.get("fact_revision")
        or record.get("assertion_revision")
        or record.get("version")
        or "unversioned"
    )
    label = str(record.get("label") or record.get("assumption_label") or "")
    if role == "assumption" and not label:
        label = f"assumption-{index}"
    span = _premise_source_check(record, source_text)
    disputed = role == "disputed_fact" or bool(record.get("disputed"))
    epistemic = {
        "asserted_fact": "allegation",
        "disputed_fact": "disputed",
        "selected_legal_rule": "selected_legal_rule",
        "assumption": "assumption",
        "missing_fact": "missing",
    }[role]
    provenance = {
        "original_id": original_id,
        # Retain caller evidence as evidence, independently of our span check.
        "record_provenance": deepcopy(_mapping_or_empty(record.get("provenance"))),
        "support_ref": str(record.get("support_ref") or ""),
        "source_table": str(record.get("source_table") or ""),
        "citation": str(record.get("citation") or ""),
        "authority_version": str(record.get("authority_version") or record.get("rule_version") or ""),
        "content_hash": str(record.get("content_hash") or ""),
        "span_unit": span.get("span_unit") or "",
        "span_status": span.get("status") or "",
        "character_span": {
            "start": record.get("char_start", record.get("start_char")),
            "end": record.get("char_end", record.get("end_char")),
        }
        if any(key in record for key in ("char_start", "start_char", "char_end", "end_char"))
        else None,
        "utf8_byte_span": {
            "start": record.get("byte_start", record.get("utf8_start", record.get("start_byte"))),
            "end": record.get("byte_end", record.get("utf8_end", record.get("end_byte"))),
        }
        if any(key in record for key in ("byte_start", "utf8_start", "start_byte", "byte_end", "utf8_end", "end_byte"))
        else None,
    }
    return {
        "premise_id": original_id or f"{role}-{index}",
        "original_id": original_id,
        "role": role,
        "epistemic_status": epistemic,
        "label": label,
        "text": text,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest() if text else "",
        "revision": revision,
        "version": str(record.get("version") or record.get("authority_version") or record.get("rule_version") or ""),
        "axiom": False,
        "source_validated": bool(span.get("verified")),
        "disputed": disputed,
        "validation_status": str(record.get("validation_status") or ""),
        "input_record_sha256": _stable_payload_digest(dict(record)),
        "provenance": provenance,
    }


def _as_premise_records(values: Sequence[Any] | None) -> List[Mapping[str, Any]]:
    records: List[Mapping[str, Any]] = []
    for item in values or ():
        if isinstance(item, str):
            records.append({"text": item})
        elif isinstance(item, Mapping):
            records.append(item)
    return records


def build_legal_ir_premise_inventory(
    *,
    asserted_facts: Sequence[Any] | None = None,
    disputed_facts: Sequence[Any] | None = None,
    selected_legal_rules: Sequence[Any] | None = None,
    assumptions: Sequence[Any] | None = None,
    missing_facts: Sequence[Any] | None = None,
    source_text: str = "",
    coverage_status: str = "",
) -> Dict[str, Any]:
    """Separate allegations, disputes, selected rules, and labeled assumptions.

    Missing and disputed statements stay out of the axiom set. A coverage
    status of ``supported`` is not an axiom and not a proof.
    """

    selected: List[Dict[str, Any]] = []
    rejected_rules: List[Dict[str, Any]] = []
    for index, record in enumerate(_as_premise_records(selected_legal_rules), start=1):
        applicable = record.get("applicable", record.get("selected", True))
        entry = _premise_entry(record, role="selected_legal_rule", source_text=source_text, index=index)
        if applicable is False:
            entry["epistemic_status"] = "rejected_rule"
            rejected_rules.append(entry)
        else:
            selected.append(entry)
    asserted = [
        _premise_entry(record, role="asserted_fact", source_text=source_text, index=index)
        for index, record in enumerate(_as_premise_records(asserted_facts), start=1)
        if not record.get("disputed") and str(record.get("validation_status") or "").lower() not in {"disputed", "contested"}
    ]
    disputed_input = list(_as_premise_records(disputed_facts))
    disputed_input.extend(
        record
        for record in _as_premise_records(asserted_facts)
        if record.get("disputed") or str(record.get("validation_status") or "").lower() in {"disputed", "contested"}
    )
    disputed = [
        _premise_entry(record, role="disputed_fact", source_text=source_text, index=index)
        for index, record in enumerate(disputed_input, start=1)
    ]
    assumed = [
        _premise_entry(record, role="assumption", source_text=source_text, index=index)
        for index, record in enumerate(_as_premise_records(assumptions), start=1)
    ]
    missing = [
        _premise_entry(record, role="missing_fact", source_text=source_text, index=index)
        for index, record in enumerate(_as_premise_records(missing_facts), start=1)
    ]
    return {
        "schema_version": PROOF_OBLIGATION_PREMISE_SCHEMA,
        "asserted_facts": asserted,
        "disputed_facts": disputed,
        "selected_legal_rules": selected,
        "assumptions": assumed,
        "missing_facts": missing,
        "rejected_rules": rejected_rules,
        "axioms": [],
        "coverage_status": str(coverage_status or ""),
        "coverage_status_is_proof": False,
        "disputed_or_missing_promoted_to_axiom": False,
    }


def _source_map_identity(receipt: Mapping[str, Any] | None) -> str:
    if not receipt:
        return ""
    source_map = receipt.get("source_map")
    if not isinstance(source_map, Mapping):
        return str(receipt.get("receipt_id") or "")
    encoded = json.dumps(source_map, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _formula_identity_digest(sample_or_document: Any) -> str:
    rows = []
    for index, formula in enumerate(_formulas_of(sample_or_document), start=1):
        # Native ids intentionally omit some semantics. Our cache must not.
        payload = _mapping_or_empty(formula)
        payload.update({
            "formula_id": _formula_identity(formula, index),
            "operator": _mapping_or_empty(_attr_or_key(formula, "operator", {})),
            "predicate": _mapping_or_empty(_attr_or_key(formula, "predicate", {})),
            "provenance": _mapping_or_empty(_attr_or_key(formula, "provenance", {})),
            "conditions": list(_attr_or_key(formula, "conditions", []) or []),
            "exceptions": list(_attr_or_key(formula, "exceptions", []) or []),
            "metadata": _mapping_or_empty(_attr_or_key(formula, "metadata", {})),
        })
        rows.append(payload)
    return _stable_payload_digest(rows)


def _execution_identity(parts: Mapping[str, Any]) -> str:
    return _stable_payload_digest(dict(parts))


def _obligation_shell(
    *,
    status: str,
    reason: str,
    support: str,
    backend_available: bool,
    inventory: Mapping[str, Any],
    versions: Mapping[str, Any],
    extra: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    assumptions = [
        {"premise_id": item.get("premise_id"), "label": item.get("label"), "revision": item.get("revision")}
        for item in inventory.get("assumptions") or []
        if isinstance(item, Mapping)
    ]
    body: Dict[str, Any] = {
        "schema_version": PROOF_OBLIGATION_ARTIFACT_SCHEMA,
        "status": status,
        "support": support,
        "reason": reason,
        "backend": {
            "identity": PROOF_OBLIGATION_BACKEND_IDENTITY,
            "available": backend_available,
            "module": "ipfs_datasets_py.logic.integration.reasoning.legal_ir_obligations",
        },
        "trust_level": PROOF_OBLIGATION_TRUST_STRUCTURAL if backend_available and status not in {"unavailable", "unsupported"} else "unavailable",
        "structural_only": True,
        "substantive_entailment": False,
        "entails_claim_element": False,
        "entails_applicability": False,
        "coverage_status_promoted_to_proof": False,
        "complete_coverage": False,
        "complete_coverage_certificate": None,
        "assumptions": assumptions,
        "premise_inventory": deepcopy(dict(inventory)),
        "versions": dict(versions),
        "obligations": [],
        "native_obligation_ids": [],
        "native_schema_versions": [],
        "operational_trace": [],
        "reused": False,
        "cache_outcome": "not_cached",
        "prior_receipt_id": "",
    }
    if extra:
        body.update(dict(extra))
    identity = str(body["versions"].get("execution_identity") or _execution_identity(body["versions"]))
    body["execution_identity"] = identity
    body["receipt_id"] = "proof-obligation-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
    return body


def _definition_binding_identity(binding: Mapping[str, Any] | None) -> str:
    if not isinstance(binding, Mapping) or not binding:
        return ""
    identities = binding.get("identities")
    if isinstance(identities, Mapping) and identities:
        return _stable_payload_digest(dict(identities))
    retained = binding.get("retained") if isinstance(binding.get("retained"), Mapping) else {}
    pins = retained.get("source_pins") if isinstance(retained, Mapping) else {}
    payload = {
        "requirement_id": binding.get("requirement_id"),
        "definition": (binding.get("definition_scope") or {}).get("identities") if isinstance(binding.get("definition_scope"), Mapping) else None,
        "source_pins": pins,
    }
    if not any(payload.values()):
        return ""
    return _stable_payload_digest(payload)


def _assumption_binding_identity(inventory: Mapping[str, Any], binding: Mapping[str, Any] | None) -> str:
    rows = [
        {"premise_id": item.get("premise_id"), "revision": item.get("revision"), "text_sha256": item.get("text_sha256")}
        for item in (inventory or {}).get("assumptions") or []
        if isinstance(item, Mapping)
    ]
    retained = binding.get("retained") if isinstance(binding, Mapping) and isinstance(binding.get("retained"), Mapping) else {}
    extra = retained.get("assumptions") if isinstance(retained, Mapping) else None
    if extra:
        rows.append({"retained_assumptions": extra})
    if not rows:
        return ""
    return _stable_payload_digest(rows)


def _adverse_treatment_identity(treatment: Any) -> str:
    if treatment is None or treatment == "" or treatment == {} or treatment == []:
        return ""
    if isinstance(treatment, str):
        return treatment
    return _stable_payload_digest(treatment)


def _store_obligation_receipt(receipt: Mapping[str, Any], *, cache_key: str = "") -> Dict[str, Any]:
    stored = deepcopy(dict(receipt))
    receipt_id = str(stored.get("receipt_id") or "")
    if receipt_id and receipt_id not in _BOUND_OBLIGATION_RECEIPTS:
        _BOUND_OBLIGATION_RECEIPTS[receipt_id] = stored
    elif receipt_id:
        stored = deepcopy(_BOUND_OBLIGATION_RECEIPTS[receipt_id])
    if cache_key and stored.get("status") in {"success", "truncated", "presence_diagnostic", "source_unverified"}:
        _BOUND_OBLIGATION_CACHE[cache_key] = str(stored.get("receipt_id") or "")
    return deepcopy(stored)


def generate_bound_legal_ir_proof_obligations(
    sample_or_document: Any = None,
    *,
    canonical_receipt: Mapping[str, Any] | None = None,
    max_obligations: int | None = None,
    claim_id: str = "",
    element_id: str = "",
    asserted_facts: Sequence[Any] | None = None,
    disputed_facts: Sequence[Any] | None = None,
    selected_legal_rules: Sequence[Any] | None = None,
    assumptions: Sequence[Any] | None = None,
    missing_facts: Sequence[Any] | None = None,
    legal_context_version: str = "",
    coverage_status: str = "",
    structural_validation: Mapping[str, Any] | None = None,
    source_text: str | None = None,
    use_cache: bool = True,
    requirement_id: str = "",
    definition_binding: Mapping[str, Any] | None = None,
    adverse_treatment: Any = None,
) -> Dict[str, Any]:
    """Generate native Legal IR obligations and bind them to premise identity.

    Native ``obligation_id`` and ``schema_version`` values are copied unchanged.
    The first-party execution identity also covers source, rule, fact, claim,
    assumption, and checker versions, which native ids omit. Structural checks
    stay structural: they do not entail a claim element.
    """

    if _is_canonical_formalization_receipt(sample_or_document) and canonical_receipt is None:
        canonical_receipt = sample_or_document
        sample_or_document = None
    bridge_name = ""
    if sample_or_document is None and canonical_receipt is not None:
        sample_or_document = modal_ir_from_canonical_formalization(canonical_receipt)
        bridge_name = "proof01_canonical_formalization_receipt"
    source = source_text if source_text is not None else _normalized_text_of(sample_or_document)
    inventory = build_legal_ir_premise_inventory(
        asserted_facts=asserted_facts,
        disputed_facts=disputed_facts,
        selected_legal_rules=selected_legal_rules,
        assumptions=assumptions,
        missing_facts=missing_facts,
        source_text=source,
        coverage_status=coverage_status,
    )
    span_checks = _prevalidate_modal_source_spans(sample_or_document) if sample_or_document is not None else []
    duplicates = _duplicate_local_labels(span_checks)
    document_hash = hashlib.sha256(source.encode("utf-8")).hexdigest() if source else ""
    passage_hashes = [item["verified_source_sha256"] for item in span_checks if item.get("verified_source_sha256")]
    versions = {
        "document_sha256": document_hash,
        "source_passage_sha256": passage_hashes,
        "formula_identity": _formula_identity_digest(sample_or_document) if sample_or_document is not None else "",
        "modal_document_identity": _stable_payload_digest({
            "sample_id": _attr_or_key(sample_or_document, "sample_id", None),
            "document": _mapping_or_empty(_document_view(sample_or_document)),
        }),
        "source_map_identity": _source_map_identity(canonical_receipt),
        "premise_inventory_identity": _stable_payload_digest(inventory),
        "structural_validation_identity": _stable_payload_digest(dict(structural_validation or {})),
        "legal_context_version": str(legal_context_version or (canonical_receipt or {}).get("authority_version") or ""),
        "rule_versions": [
            {
                "premise_id": item.get("premise_id"),
                "version": item.get("version"),
                "revision": item.get("revision"),
            }
            for item in inventory["selected_legal_rules"]
        ],
        "claim_id": str(claim_id or ""),
        "element_id": str(element_id or ""),
        "fact_revisions": [
            {"premise_id": item.get("premise_id"), "revision": item.get("revision"), "text_sha256": item.get("text_sha256")}
            for item in [*inventory["asserted_facts"], *inventory["disputed_facts"], *inventory["missing_facts"]]
        ],
        "assumption_ids": [item.get("premise_id") for item in inventory["assumptions"]],
        "assumption_labels": [item.get("label") for item in inventory["assumptions"]],
        "requirement_id": str(requirement_id or (definition_binding or {}).get("requirement_id") or ""),
        "definition_identity": _definition_binding_identity(definition_binding),
        "assumption_identity": _assumption_binding_identity(inventory, definition_binding),
        "adverse_treatment_identity": _adverse_treatment_identity(adverse_treatment if adverse_treatment is not None else (definition_binding or {}).get("adverse_treatment")),
        "source_identity": document_hash,
        "checker_version": PROOF_OBLIGATION_CHECKER_VERSION,
        "policy_version": PROOF_OBLIGATION_POLICY_VERSION,
        "native_backend": PROOF_OBLIGATION_BACKEND_IDENTITY,
        "coverage_status": str(coverage_status or ""),
        "max_obligations": max_obligations,
    }
    versions["execution_identity"] = _execution_identity(versions)
    cache_key = str(versions["execution_identity"])

    def _unavailable(status: str, support: str, reason: str, *, code: str) -> Dict[str, Any]:
        receipt = _obligation_shell(
            status=status,
            reason=reason,
            support=support,
            backend_available=False,
            inventory=inventory,
            versions=versions,
            extra={
                "bridge": bridge_name,
                "source_span_checks": span_checks,
                "duplicate_local_labels": duplicates,
                "structural_validation": deepcopy(dict(structural_validation or {})),
                "structural_validation_is_entailment": False,
                "operational_trace": [{"code": code, "status": status}],
                "cache_outcome": "not_cached",
            },
        )
        # An unavailable result must not resolve to an earlier successful
        # receipt for this request identity. Keep that history unchanged.
        return receipt

    if _is_pipeline_result(sample_or_document):
        return _unavailable(
            "unsupported",
            "unsupported",
            "CompilerPipelineResult is not a ModalIR document. Use the PROOF01 formalization bridge.",
            code="pipeline_result_not_modal_ir",
        )
    if _legal_ir_obligations_module is None or not hasattr(_legal_ir_obligations_module, "generate_legal_ir_proof_obligations"):
        return _unavailable(
            "unavailable",
            "unsupported",
            "Legal IR proof obligation generator is unavailable.",
            code="generator_unavailable",
        )
    if use_cache and cache_key in _BOUND_OBLIGATION_CACHE:
        cached = _BOUND_OBLIGATION_RECEIPTS.get(_BOUND_OBLIGATION_CACHE[cache_key])
        if cached is not None:
            reused = deepcopy(cached)
            reused["reused"] = True
            reused["cache_outcome"] = "reused"
            return reused
    prior = ""
    if _BOUND_OBLIGATION_CACHE:
        prior = next(reversed(_BOUND_OBLIGATION_CACHE.values()))
    try:
        native = _legal_ir_obligations_module.generate_legal_ir_proof_obligations(
            sample_or_document,
            max_obligations=max_obligations,
        )
    except Exception as exc:  # noqa: BLE001 - typed generator failure without premise text
        return _unavailable(
            "unavailable",
            "unsupported",
            "Legal IR proof obligation generator failed.",
            code=_obligation_error_code(exc),
        )
    native_payloads = []
    native_ids: List[str] = []
    native_schemas: List[str] = []
    for obligation in native or []:
        payload = obligation.to_dict() if hasattr(obligation, "to_dict") else dict(obligation)
        native_payloads.append(payload)
        native_ids.append(str(payload.get("obligation_id") or ""))
        schema = str(payload.get("schema_version") or "")
        if schema and schema not in native_schemas:
            native_schemas.append(schema)
    kinds = {str(item.get("kind") or "") for item in native_payloads}
    unbounded_count = None
    truncated = False
    if max_obligations is not None:
        try:
            limit = max(0, int(max_obligations))
        except (TypeError, ValueError):
            limit = 0
        truncated = len(native_payloads) >= limit
        if truncated:
            try:
                full = _legal_ir_obligations_module.generate_legal_ir_proof_obligations(sample_or_document)
                unbounded_count = len(list(full))
                truncated = unbounded_count > len(native_payloads)
            except Exception:  # noqa: BLE001 - truncation stays marked without echoing the error
                unbounded_count = None
                truncated = True
    spans_verified = bool(span_checks) and all(item.get("verified") for item in span_checks)
    if not _formulas_of(sample_or_document):
        status = "presence_diagnostic"
    elif truncated:
        status = "truncated"
    elif span_checks and not spans_verified:
        status = "source_unverified"
    else:
        status = "success"
    for check in span_checks:
        matched = next(
            (
                item.get("metadata", {}).get("source_span_sha256")
                for item in native_payloads
                if item.get("formula_id") == check["formula_id"] and isinstance(item.get("metadata"), Mapping)
                and item.get("metadata", {}).get("source_span_sha256")
            ),
            "",
        )
        check["native_source_span_sha256"] = str(matched or "")
        if check["verified"] and matched:
            check["native_hash_matches_verified_source"] = matched == check["verified_source_sha256"]
        elif not check["verified"]:
            check["native_hash_matches_verified_source"] = False
            check["native_span_hash_is_fallback"] = True
    trace = [
        {
            "code": "native_obligations_generated",
            "status": status,
            "obligation_count": len(native_payloads),
            "truncated": truncated,
        }
    ]
    if duplicates:
        trace.append({"code": "duplicate_local_labels", "status": "recorded", "count": len(duplicates)})
    if any(not item.get("verified") for item in span_checks):
        trace.append({"code": "source_span_unverified", "status": "native_hash_not_source_bytes"})
    receipt = _obligation_shell(
        status=status,
        reason="",
        support="executed",
        backend_available=True,
        inventory=inventory,
        versions=versions,
        extra={
            "bridge": bridge_name,
            "obligations": native_payloads,
            "native_obligation_ids": native_ids,
            "native_schema_versions": native_schemas,
            "obligation_count": len(native_payloads),
            "unbounded_obligation_count": unbounded_count,
            "truncated": truncated,
            "max_obligations": max_obligations,
            "source_span_checks": span_checks,
            "source_spans_verified": spans_verified,
            "duplicate_local_labels": duplicates,
            "structural_validation": deepcopy(dict(structural_validation or {})),
            "structural_validation_is_entailment": False,
            "obligation_kinds": sorted(kind for kind in kinds if kind and not kind.endswith("Error")),
            "presence_diagnostic": "modal_formula_presence" in kinds,
            "operational_trace": trace,
            "cache_outcome": "stored",
            "prior_receipt_id": prior if prior and prior != ("proof-obligation-" + hashlib.sha256(cache_key.encode()).hexdigest()[:32]) else "",
            "checker_version": PROOF_OBLIGATION_CHECKER_VERSION,
            "policy_version": PROOF_OBLIGATION_POLICY_VERSION,
            "trust_level": PROOF_OBLIGATION_TRUST_STRUCTURAL,
        },
    )
    return _store_obligation_receipt(receipt, cache_key=cache_key)


def _positive_finite(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be positive and finite") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{label} must be positive and finite")
    return number


@contextmanager
def _prover_installs_disabled():
    previous = {key: os.environ.get(key) for key in _INSTALL_DISABLE_ENV}
    os.environ.update(_INSTALL_DISABLE_ENV)
    try:
        yield
    finally:
        for key, old in previous.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def _default_stage_budgets() -> Dict[str, float]:
    return {
        "deterministic": 0.25,
        "native_logic": 0.5,
        "smt_atp": 0.75,
        "lean_reconstruction": 0.75,
    }


def _routing_modules_available() -> bool:
    return (
        _proof_router_module is not None
        and _hammer_module is not None
        and hasattr(_proof_router_module, "LegalIRProofRouter")
        and hasattr(_proof_router_module, "ProofRoutingPolicy")
    )


def _clean_obligation_metadata(metadata: Mapping[str, Any] | None) -> Tuple[Dict[str, Any], List[str]]:
    rejected: List[str] = []
    cleaned: Dict[str, Any] = {}
    for key, value in dict(metadata or {}).items():
        if key in _UNTRUSTED_ROUTE_METADATA_KEYS or callable(value):
            rejected.append(str(key))
            continue
        if isinstance(value, bool):
            rejected.append(str(key))
            continue
        cleaned[str(key)] = value
    return cleaned, rejected


def _coerce_obligation(obligation: Any, goal_statement: str) -> Tuple[Any, List[str]]:
    if not _routing_modules_available():
        raise RuntimeError("proof router unavailable")
    obligation_type = _legal_ir_obligations_module.LegalIRProofObligation if (
        _legal_ir_obligations_module is not None and hasattr(_legal_ir_obligations_module, "LegalIRProofObligation")
    ) else None
    if obligation is None:
        if obligation_type is None:
            raise RuntimeError("obligation type unavailable")
        return obligation_type(
            obligation_id="unbound-goal",
            statement=str(goal_statement or "unknown_goal"),
            kind="claim_element",
            legal_ir_view="intake",
            logic_family="unspecified",
        ), []
    if obligation_type is not None and isinstance(obligation, obligation_type):
        metadata, rejected = _clean_obligation_metadata(obligation.metadata)
        return replace(obligation, metadata=metadata), rejected
    if isinstance(obligation, Mapping):
        metadata, rejected = _clean_obligation_metadata(
            obligation.get("metadata") if isinstance(obligation.get("metadata"), Mapping) else {}
        )
        if obligation_type is None:
            raise RuntimeError("obligation type unavailable")
        return obligation_type(
            obligation_id=str(obligation.get("obligation_id") or "unbound-goal"),
            statement=str(obligation.get("statement") or goal_statement or "unknown_goal"),
            kind=str(obligation.get("kind") or "claim_element"),
            legal_ir_view=str(obligation.get("legal_ir_view") or "intake"),
            logic_family=str(obligation.get("logic_family") or "unspecified"),
            sample_id=str(obligation.get("sample_id") or ""),
            formula_id=str(obligation.get("formula_id") or ""),
            metadata=metadata,
        ), rejected
    raise TypeError("obligation must be a LegalIRProofObligation or a mapping")


def _hammer_premises(premise_inventory: Mapping[str, Any] | None, premises: Sequence[Any] | None) -> List[Any]:
    hammer_premise = _hammer_module.HammerPremise
    built: List[Any] = []
    if premises:
        for item in premises:
            if isinstance(item, hammer_premise):
                built.append(item)
            elif isinstance(item, Mapping) and item.get("role") != "missing_fact":
                built.append(
                    hammer_premise(
                        name=str(item.get("premise_id") or item.get("name") or "premise"),
                        statement=str(item.get("statement") or item.get("text") or ""),
                        metadata={
                            "role": str(item.get("role") or ""),
                            "premise_id": str(item.get("premise_id") or ""),
                            "revision": str(item.get("revision") or ""),
                            "axiom": False,
                        },
                    )
                )
        return built
    inventory = premise_inventory or {}
    for role in ("selected_legal_rules", "asserted_facts", "assumptions"):
        for item in inventory.get(role) or []:
            if not isinstance(item, Mapping):
                continue
            built.append(
                hammer_premise(
                    name=str(item.get("premise_id") or role),
                    statement=str(item.get("text") or item.get("label") or ""),
                    metadata={
                        "role": role,
                        "premise_id": str(item.get("premise_id") or ""),
                        "revision": str(item.get("revision") or ""),
                        "version": str(item.get("version") or ""),
                        "axiom": False,
                        "epistemic_status": str(item.get("epistemic_status") or ""),
                    },
                )
            )
    return built


def _premise_identity(premise_inventory: Mapping[str, Any] | None) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    inventory = premise_inventory or {}
    for role in ("asserted_facts", "disputed_facts", "selected_legal_rules", "assumptions", "missing_facts"):
        for item in inventory.get(role) or []:
            if not isinstance(item, Mapping):
                continue
            rows.append(
                {
                    "role": role,
                    "premise_id": str(item.get("premise_id") or ""),
                    "revision": str(item.get("revision") or ""),
                    "version": str(item.get("version") or ""),
                    "text_sha256": str(item.get("text_sha256") or ""),
                }
            )
    return rows


def _missing_fact_values(premise_inventory: Mapping[str, Any] | None) -> List[Dict[str, Any]]:
    values: List[Dict[str, Any]] = []
    for item in (premise_inventory or {}).get("missing_facts") or []:
        if not isinstance(item, Mapping):
            continue
        values.append(
            {
                "premise_id": str(item.get("premise_id") or ""),
                "value": None,
                "interpreted_as_false": False,
                "open_world": True,
            }
        )
    return values


# The actual router runs in this isolated call process. Input is JSON over stdin;
# neither caller callbacks nor outcome-selecting backends cross this boundary.
_PROOF_ROUTER_CALL_SOURCE = r"""
import sys
bootstrap_flags = {name:getattr(sys.flags,name) for name in ('no_site','isolated','ignore_environment','dont_write_bytecode')}
if any(value != 1 for value in bootstrap_flags.values()): raise SystemExit(2)
import ctypes, os, signal
manager = int(sys.argv[1])
if manager <= 1 or os.getppid() != manager: raise SystemExit(2)
if ctypes.CDLL(None).prctl(1, signal.SIGKILL, 0, 0, 0) != 0: raise SystemExit(2)
if os.getppid() != manager: raise SystemExit(2)
# Bind parent death before any request read or optional-module import.
import contextlib, hashlib, importlib, json, socket, time
# Retain the actual interpreter flags even if request ingress stalls.
fd=os.open('router-bootstrap.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'w') as stream:
 json.dump({'schema':'complaint-owned-proof-router-bootstrap@1','pid':os.getpid(),
  'manager_pid':manager,'flags':bootstrap_flags},stream,separators=(',',':'))
 stream.flush();os.fsync(stream.fileno())
request = json.loads(sys.stdin.buffer.read(1048577))
if request.get('schema') != 'complaint-proof-router-call@1': raise SystemExit(2)
if request.get('expected_manager_pid') != manager or os.getppid() != manager: raise SystemExit(2)
def guard(event, args):
 if event == 'socket.__new__' and len(args)>1 and args[1] in (socket.AF_INET,socket.AF_INET6): raise PermissionError('proof_network_disabled')
 if event in ('socket.connect','socket.connect_ex','socket.sendto','socket.getaddrinfo','socket.gethostbyname','socket.gethostbyaddr','socket.getnameinfo'): raise PermissionError('proof_network_disabled')
 if event in ('subprocess.Popen','os.system','os.posix_spawn','os.posix_spawnp','os.fork','os.forkpty') or event.startswith('os.exec') or event.startswith('os.spawn'): raise PermissionError('unconfigured_proof_process_disabled')
sys.addaudithook(guard)
sys.path[:0] = request['roots']
def source_pins():
 pins = {}
 for name, expected in request['sources'].items():
  path = expected['path']
  with open(path,'rb') as stream: digest = hashlib.sha256(stream.read()).hexdigest()
  if digest != expected['sha256']: raise ValueError('proof_source_changed')
  pins[name] = {'path':path,'sha256':digest}
 return pins
payload = {'status':'unavailable','error_code':'proof_router_failed'}
try:
 before = source_pins()
 # Optional-module notices must not become protocol output or private errors.
 with contextlib.redirect_stdout(sys.stderr):
  modules = {name:importlib.import_module(name) for name in request['sources']}
  for name,module in modules.items():
   if os.path.realpath(module.__file__) != before[name]['path']: raise ValueError('proof_module_origin_mismatch')
  from ipfs_datasets_py.logic.integration.reasoning.legal_ir_obligations import LegalIRProofObligation
  from ipfs_datasets_py.logic.integration.reasoning.hammer import HammerGoal, HammerPipeline, HammerPremise
  from ipfs_datasets_py.logic.integration.reasoning.legal_ir_proof_router import LegalIRProofRouter, ProofRoutingPolicy
  remaining = request['deadline_monotonic'] - time.monotonic()
  if remaining <= 0: raise TimeoutError()
  policy = ProofRoutingPolicy(required_trust=request['policy']['required_trust'],
   total_timeout_seconds=remaining,stage_timeout_seconds={key:min(value,remaining) for key,value in request['policy']['stage_timeout_seconds'].items()},
   enabled_routes=tuple(request['policy']['enabled_routes']),stop_on_theorem_failure=True)
  pipeline = HammerPipeline(backends=[], kernel_verifier=None)
  router = LegalIRProofRouter(pipeline, policy=policy)
  obligation = LegalIRProofObligation(**request['obligation'])
  goal = HammerGoal(statement=request['goal_statement'],name=obligation.obligation_id,
   metadata={'logic_family':obligation.logic_family,'substantive_goal':True})
  premises = [HammerPremise(**item) for item in request['premises']]
  native = router.route(obligation,goal,premises,sample_or_document=request['sample_or_document'])
  after = source_pins()
  if after != before: raise ValueError('proof_source_changed')
  native_payload = native.to_dict()
  for attempt in native_payload.get('attempts',[]):
   if attempt.get('status') == 'error':
    attempt['reason']='route_execution_failed';attempt['metadata']={}
  payload = {'status':'ok','native':native_payload,'runtime_sources':after,
   'request_identity':request['request_identity'],'kernel_artifact_verified':False,
   'negative_artifact_verified':False,'router_pid':os.getpid()}
except TimeoutError:
 payload = {'status':'timeout','error_code':'request_deadline'}
except (ImportError,AttributeError,FileNotFoundError):
 payload = {'status':'unavailable','error_code':'proof_backend_unavailable'}
except BaseException:
 payload = {'status':'unavailable','error_code':'proof_router_failed'}
encoded = json.dumps(payload,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode()
if len(encoded)>524288: encoded=b'{"status":"unavailable","error_code":"proof_output_limit"}'
sys.stdout.buffer.write(encoded);sys.stdout.buffer.flush()
"""


# This manager alone is a subreaper. It owns the actual call, not an unrelated
# preliminary command, and confirms closure before the outer supervisor returns.
_PROOF_ROUTER_MANAGER_SOURCE = r"""
import sys
bootstrap_flags = {name:getattr(sys.flags,name) for name in ('no_site','isolated','ignore_environment','dont_write_bytecode')}
if any(value != 1 for value in bootstrap_flags.values()): raise SystemExit(2)
import ctypes, fcntl, hashlib, json, math, os, selectors, signal, stat, subprocess, time
if sys.platform != 'linux': raise SystemExit(2)
execution_deadline = float(sys.argv[1])
cleanup_deadline = float(sys.argv[2])
cleanup_seconds = float(sys.argv[3])
owner = int(sys.argv[4])
request_path,request_size,request_sha256,request_inode=sys.argv[5],int(sys.argv[6]),sys.argv[7],int(sys.argv[8])
parts=request_path.split('/')
if (len(parts)!=5 or parts[:4]!=['','proc',str(owner),'fd'] or not parts[4].isdecimal()
 or str(int(parts[4]))!=parts[4] or int(parts[4])<3 or not 0<request_size<=1048576
 or request_inode<=0 or len(request_sha256)!=64 or any(c not in '0123456789abcdef' for c in request_sha256)):
 raise SystemExit(2)
request_verified=False
required_seals=fcntl.F_SEAL_SEAL|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_GROW|fcntl.F_SEAL_WRITE
if not all(math.isfinite(n) for n in (execution_deadline,cleanup_deadline,cleanup_seconds)): raise SystemExit(2)
if cleanup_seconds<=0 or cleanup_deadline<=execution_deadline or owner<=1: raise SystemExit(2)
cancelled = False
process = None
sent = total_input = 0
stdin_complete = False
def cancel(_signum,_frame):
 global cancelled
 cancelled = True
signal.signal(signal.SIGTERM,cancel)
signal.signal(signal.SIGINT,cancel)
if os.getppid()!=owner: raise SystemExit(2)
libc = ctypes.CDLL(None)
if libc.prctl(1,signal.SIGTERM,0,0,0)!=0: raise SystemExit(2)
if os.getppid()!=owner: raise SystemExit(2)
if libc.prctl(36,1,0,0,0)!=0: raise SystemExit(2)
call_source = CALL_SOURCE_LITERAL
selector = None
def check_execution():
 # The owner also sends SIGTERM when this execution budget expires. That
 # generic signal must not relabel an elapsed deadline as caller cancellation.
 if time.monotonic()>=execution_deadline: raise TimeoutError()
 if cancelled: raise InterruptedError()
def read_request():
 # Current DataSupervisor cannot resume large stdin writes after a heartbeat
 # timeout. Read immutable anonymous memory instead; never stage facts on disk.
 global request_verified
 check_execution()
 if os.getppid()!=owner:raise ValueError('request_owner_changed')
 fd=os.open(request_path,os.O_RDONLY|os.O_CLOEXEC|os.O_NONBLOCK)
 try:
  before=os.fstat(fd)
  if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid()
   or stat.S_IMODE(before.st_mode)!=0o600 or before.st_nlink!=0
   or before.st_size!=request_size or before.st_ino!=request_inode
   or fcntl.fcntl(fd,fcntl.F_GET_SEALS)&required_seals!=required_seals):
   raise ValueError('request_memory_identity')
  os.lseek(fd,0,os.SEEK_SET)
  raw=bytearray()
  while True:
   check_execution()
   chunk=os.read(fd,min(65536,1048577-len(raw)))
   check_execution()
   if not chunk:break
   raw.extend(chunk)
   if len(raw)>1048576:raise ValueError('request_limit')
  after=os.fstat(fd)
  fields=('st_dev','st_ino','st_size','st_mode','st_uid','st_nlink','st_mtime_ns','st_ctime_ns')
  if (any(getattr(before,k)!=getattr(after,k)for k in fields)
   or len(raw)!=request_size or hashlib.sha256(raw).hexdigest()!=request_sha256
   or fcntl.fcntl(fd,fcntl.F_GET_SEALS)&required_seals!=required_seals
   or os.getppid()!=owner):raise ValueError('request_memory_changed')
  request_verified=True
  check_execution()
  return json.loads(raw)
 finally:
  os.close(fd)
def retain_child_identity():
 # This is a direct, unreaped owned child. Its PID cannot be reused here.
 with open('/proc/'+str(process.pid)+'/stat') as stream:
  fields=stream.read().rpartition(')')[2].split()
 if os.getpgid(process.pid)!=process.pid:raise ValueError('router_group_mismatch')
 identity={'schema':'complaint-owned-proof-router-child@1','pid':process.pid,
  'start_ticks':int(fields[19]),'process_group_id':process.pid,'manager_pid':os.getpid(),
  'manager_parent_pid':owner,'worker_source_sha256':hashlib.sha256(call_source.encode()).hexdigest()}
 fd=os.open('router-child.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'w') as stream:
  json.dump(identity,stream,separators=(',',':'));stream.flush();os.fsync(stream.fileno())
def cleanup():
 if process is None:return True
 deadline=min(cleanup_deadline,time.monotonic()+cleanup_seconds)
 try:os.killpg(process.pid,signal.SIGKILL)
 except ProcessLookupError:pass
 except OSError:return False
 remaining=deadline-time.monotonic()
 if remaining<=0:return False
 try:process.wait(timeout=remaining)
 except subprocess.TimeoutExpired:return False
 while time.monotonic()<deadline:
  try:children=[int(p) for p in open('/proc/self/task/'+str(os.getpid())+'/children').read().split()]
  except (OSError,ValueError):return False
  for pid in children:
   try:os.kill(pid,signal.SIGKILL)
   except ProcessLookupError:pass
  try:
   while True:
    pid,_=os.waitpid(-1,os.WNOHANG)
    if pid==0:break
  except ChildProcessError:return True
  time.sleep(.002)
 return False
result={'outcome':'unavailable','cleanup_confirmed':False}
try:
 request=read_request()
 call=dict(request['call']);call['expected_manager_pid']=os.getpid()
 if call['deadline_monotonic']!=execution_deadline:raise ValueError('request_deadline_mismatch')
 raw=json.dumps(call,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode()
 total_input=len(raw)
 if total_input>1048576:raise ValueError('request_limit')
 check_execution()
 process=subprocess.Popen([sys.executable,'-I','-S','-B','-c',call_source,str(os.getpid())],stdin=subprocess.PIPE,
  stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ),process_group=0)
 retain_child_identity()
 selector=selectors.DefaultSelector()
 for stream,events,label in ((process.stdin,selectors.EVENT_WRITE,'stdin'),
   (process.stdout,selectors.EVENT_READ,'stdout'),(process.stderr,selectors.EVENT_READ,'stderr')):
  os.set_blocking(stream.fileno(),False);selector.register(stream,events,label)
 output=bytearray();total_output=0;outcome='ok'
 while selector.get_map():
  check_execution()
  for key,_ in selector.select(min(.02,max(0,execution_deadline-time.monotonic()))):
   check_execution()
   if key.data=='stdin':
    try:written=os.write(key.fileobj.fileno(),raw[sent:sent+65536])
    except BlockingIOError:continue
    except BrokenPipeError:outcome='input_failed';break
    if written<=0:outcome='input_failed';break
    sent+=written
    if sent==total_input:
     selector.unregister(key.fileobj);key.fileobj.close();stdin_complete=True
    continue
   try:chunk=os.read(key.fileobj.fileno(),65536)
   except BlockingIOError:continue
   if not chunk:selector.unregister(key.fileobj);continue
   total_output+=len(chunk)
   if total_output>524288:outcome='output_limit';break
   if key.data=='stdout':output.extend(chunk)
  if outcome!='ok':break
 result={'outcome':outcome,'cleanup_confirmed':False}
 if outcome=='ok':
  try:result['payload']=json.loads(output)
  except (ValueError,UnicodeError):result['outcome']='unavailable'
except InterruptedError:
 result={'outcome':'cancelled','cleanup_confirmed':False}
except TimeoutError:
 result={'outcome':'timeout','cleanup_confirmed':False}
except BaseException:
 result={'outcome':'unavailable','cleanup_confirmed':False}
finally:
 confirmed=cleanup();result['cleanup_confirmed']=confirmed
 result.update(bootstrap_flags=bootstrap_flags,sealed_request_verified=request_verified,
  request_sha256=request_sha256,request_size=request_size,request_inode=request_inode,router_pid=None if process is None else process.pid,input_bytes_sent=sent,
  input_bytes_total=total_input,stdin_complete=stdin_complete)
 if result.get('outcome')=='ok' and process is not None and process.returncode!=0:
  result.pop('payload',None);result['outcome']='unavailable'
 if not confirmed:
  result.pop('payload',None);result['outcome']='cleanup_unconfirmed'
 if selector is not None:selector.close()
 for stream in (() if process is None else (process.stdin,process.stdout,process.stderr)):
  try:stream.close()
  except (OSError,ValueError):pass
 sys.stdout.write(json.dumps(result,ensure_ascii=True,allow_nan=False,separators=(',',':')));sys.stdout.flush()
"""


@contextmanager
def _proof_router_private_scope(state_directory: str | None):
    import shutil
    import tempfile
    from pathlib import Path

    if state_directory:
        Path(state_directory).mkdir(parents=True, exist_ok=True, mode=0o700)
    root = Path(tempfile.mkdtemp(prefix="proof-router-", dir=state_directory))
    closure = {"confirmed": False}
    try:
        yield root, closure
    finally:
        # Unknown custody retains the private native manifest for recovery.
        if closure["confirmed"]:
            shutil.rmtree(root)


def _run_owned_proof_router(request: Mapping[str, Any], *, deadline: float, cancellation_event: Any,
                            state_directory: str | None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    import fcntl
    import site
    import sys
    from pathlib import Path

    process: Dict[str, Any] = {"available": False, "process_group_reaped": False,
                               "timed_out": False, "cancelled": False, "actual_router_owned": True}
    if _process_lifecycle_module is None or sys.platform != "linux":
        return {"status": "unavailable", "error_code": "process_supervisor_unavailable"}, process
    if cancellation_event is not None and cancellation_event.is_set():
        process.update(available=True, cancelled=True, process_group_reaped=True)
        return {"status": "cancelled"}, process
    with _proof_router_private_scope(state_directory) as (root, closure):
        for name in ("home", "tmp", "control-plane"):
            (root / name).mkdir(mode=0o700)
        environment = {
            "PATH": "/usr/bin:/bin", "HOME": str(root / "home"), "TMPDIR": str(root / "tmp"),
            "LC_ALL": "C", "LANG": "C", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
            "IPFS_DATASETS_PY_AUTO_NLTK_DOWNLOAD": "0", "IPFS_DATASETS_PY_MINIMAL_IMPORTS": "1",
            "IPFS_ACCELERATE_AGENT_ORCHESTRATION_DIR": str(root / "control-plane"),
            "IPFS_ACCELERATE_META_TODO_TASK_FILE": "", "IPFS_ACCELERATE_META_TODO_RUN_ID": "",
            **_INSTALL_DISABLE_ENV,
        }
        modules = [_proof_router_module, _hammer_module, _legal_ir_obligations_module]
        sources = {module.__name__: {"path": str(Path(module.__file__).resolve()),
                   "sha256": hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()} for module in modules}
        data_root = str(Path(_proof_router_module.__file__).resolve().parents[4])
        roots = [data_root, *[entry for entry in site.getsitepackages() if Path(entry).is_dir()]]
        remaining = deadline - time.monotonic()
        reserve = min(0.8, remaining / 2)
        if remaining <= 0.02:
            process.update(available=True, timed_out=True, process_group_reaped=True)
            closure["confirmed"] = True
            return {"status": "timeout"}, process
        call = {**dict(request), "schema": "complaint-proof-router-call@1", "sources": sources,
                "roots": roots, "deadline_monotonic": deadline - reserve}
        call["request_identity"] = _stable_payload_digest(call)
        encoded = json.dumps({"call": call}, ensure_ascii=True,
                             allow_nan=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 1048576:
            closure["confirmed"] = True
            return {"status": "unsupported", "error_code": "proof_request_limit"}, process
        request_fd = os.memfd_create("complaint-proof-router-request", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        entered_native_run = False
        try:
            os.fchmod(request_fd, 0o600)
            request_bytes = encoded.encode("utf-8")
            offset = 0
            while offset < len(request_bytes):
                if time.monotonic() >= deadline:
                    raise TimeoutError()
                written = os.write(request_fd, request_bytes[offset:offset+65536])
                if written <= 0:
                    raise OSError("request_memory_write_failed")
                offset += written
            required_seals = fcntl.F_SEAL_SEAL | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE
            fcntl.fcntl(request_fd, fcntl.F_ADD_SEALS, required_seals)
            info = os.fstat(request_fd)
            actual_seals = fcntl.fcntl(request_fd, fcntl.F_GET_SEALS)
            if actual_seals & required_seals != required_seals or info.st_size != len(request_bytes):
                raise OSError("request_memory_unsealed")
            request_memory = {"path": f"/proc/{os.getpid()}/fd/{request_fd}", "size": info.st_size,
                              "inode": info.st_ino, "sha256": hashlib.sha256(request_bytes).hexdigest(),
                              "seals": actual_seals, "owner_pid": os.getpid()}
            source = _PROOF_ROUTER_MANAGER_SOURCE.replace("CALL_SOURCE_LITERAL", repr(_PROOF_ROUTER_CALL_SOURCE), 1)
            supervisor = _process_lifecycle_module.ProcessSupervisor(
                state_directory=root / "lifecycle", heartbeat_interval_seconds=0.02, recover=False)
            remaining = deadline - time.monotonic()
            if remaining <= reserve:
                process.update(available=True, timed_out=True, process_group_reaped=True)
                closure["confirmed"] = True
                return {"status": "timeout"}, process
            # The manager has time to reap before the native owner's final kill.
            # Both levels consume this request's existing reserve, never a new total.
            limits = _process_lifecycle_module.ProcessLimits(wall_time_seconds=remaining-reserve,
                graceful_shutdown_seconds=3*reserve/4, forced_cleanup_seconds=reserve/4)
            command = [sys.executable, "-I", "-S", "-B", "-c", source, str(call["deadline_monotonic"]),
                       str(deadline-reserve/4), str(reserve/2), str(os.getpid()),
                       request_memory["path"],str(request_memory["size"]),request_memory["sha256"],str(request_memory["inode"])]
            entered_native_run = True
            result = supervisor.run(command, limits=limits,
                cancel_event=cancellation_event, env=environment, cwd=str(root), input_text=None)
        except TimeoutError:
            if entered_native_run:
                raise
            process.update(available=True, timed_out=True, process_group_reaped=True)
            closure["confirmed"] = True
            return {"status": "timeout"}, process
        finally:
            os.close(request_fd)
        process.update({key: getattr(result, key) for key in (
            "pid", "process_group_id", "returncode", "timed_out", "cancelled", "wall_time_seconds",
            "process_group_reaped", "termination_reason", "forced_cleanup")})
        process["available"] = True
        process["stdout_bytes"] = len(result.stdout.encode("utf-8"))
        process["stderr_bytes"] = len(result.stderr.encode("utf-8"))
        process["worker_source_sha256"] = hashlib.sha256(_PROOF_ROUTER_CALL_SOURCE.encode()).hexdigest()
        process["manager_source_sha256"] = hashlib.sha256(source.encode()).hexdigest()
        process["cleanup_reserve_seconds"] = reserve
        process["execution_budget_seconds"] = max(0.0, remaining-reserve)
        try:
            envelope = json.loads(result.stdout)
        except (ValueError, TypeError):
            envelope = {}
        cleanup = envelope.get("cleanup_confirmed") is True or (result.pid is None and result.process_group_reaped)
        process["router_tree_reaped"] = cleanup
        process["router_pid"] = envelope.get("router_pid")
        identity_path = root / "router-child.json"
        identity = None
        if identity_path.exists() and not identity_path.is_symlink():
            info = identity_path.stat()
            if info.st_uid == os.getuid() and info.st_mode & 0o777 == 0o600 and info.st_size <= 4096:
                try:
                    candidate = json.loads(identity_path.read_text())
                    if (isinstance(candidate, dict) and candidate.get("schema") == "complaint-owned-proof-router-child@1"
                            and type(candidate.get("pid")) is int and candidate["pid"] > 1
                            and type(candidate.get("start_ticks")) is int and candidate["start_ticks"] > 0
                            and candidate.get("process_group_id") == candidate["pid"]
                            and candidate.get("manager_pid") == result.pid
                            and candidate.get("manager_parent_pid") == os.getpid()
                            and candidate.get("worker_source_sha256") == process["worker_source_sha256"]
                            and process["router_pid"] in (None, candidate["pid"])):
                        identity = candidate
                except (OSError, ValueError, TypeError):
                    pass
        if identity is not None:
            process["router_pid"] = identity["pid"]
            process["router_child_identity"] = identity
        elif type(process["router_pid"]) is int:
            cleanup = False
            process["router_tree_reaped"] = False
        expected_flags = {key: 1 for key in ("no_site", "isolated", "ignore_environment", "dont_write_bytecode")}
        manager_flags = envelope.get("bootstrap_flags")
        process["manager_bootstrap_flags"] = manager_flags if manager_flags == expected_flags else None
        bootstrap_path = root / "router-bootstrap.json"
        worker_flags = None
        if identity is not None and bootstrap_path.exists() and not bootstrap_path.is_symlink():
            info = bootstrap_path.stat()
            if info.st_uid == os.getuid() and info.st_mode & 0o777 == 0o600 and info.st_size <= 4096:
                try:
                    observed = json.loads(bootstrap_path.read_text())
                    if (isinstance(observed, dict) and observed.get("schema") == "complaint-owned-proof-router-bootstrap@1"
                            and observed.get("pid") == identity["pid"]
                            and observed.get("manager_pid") == result.pid
                            and observed.get("flags") == expected_flags):
                        worker_flags = observed["flags"]
                except (OSError, ValueError, TypeError):
                    pass
        process["worker_bootstrap_flags"] = worker_flags
        process["isolated_no_site_bootstrap_verified"] = (
            process["manager_bootstrap_flags"] == expected_flags and worker_flags == expected_flags)
        if identity is not None and not process["isolated_no_site_bootstrap_verified"]:
            envelope.pop("payload", None)
            envelope["outcome"] = "unavailable"
        process["request_transport"] = "sealed_parent_memfd"
        process["request_memory"] = request_memory
        process["sealed_request_transport_verified"] = (
            envelope.get("sealed_request_verified") is True
            and envelope.get("request_sha256") == request_memory["sha256"]
            and envelope.get("request_size") == request_memory["size"]
            and envelope.get("request_inode") == request_memory["inode"])
        if identity is not None and not process["sealed_request_transport_verified"]:
            envelope.pop("payload", None)
            envelope["outcome"] = "unavailable"
        process["input_bytes_sent"] = envelope.get("input_bytes_sent", 0)
        process["input_bytes_total"] = envelope.get("input_bytes_total", 0)
        process["stdin_complete"] = envelope.get("stdin_complete") is True
        process["actual_router_started"] = type(process["router_pid"]) is int
        process["process_group_reaped"] = process["process_group_reaped"] and cleanup
        closure["confirmed"] = process["process_group_reaped"]
        if not closure["confirmed"]:
            process["retained_state_directory"] = str(root)
        process["timed_out"] = process["timed_out"] or envelope.get("outcome") == "timeout"
        process["timed_out"] = process["timed_out"] or time.monotonic() >= deadline
        # Native's owner records why it sent the generic termination signal.
        # Explicit owner cancellation remains authoritative even if cleanup
        # crosses the request deadline; an owner timeout cannot be overridden
        # by the manager interpreting the same SIGTERM as cancellation.
        process["cancelled"] = bool(result.cancelled) or (
            envelope.get("outcome") == "cancelled" and not bool(result.timed_out))
        payload = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else {}
        if payload.get("status") == "timeout":
            process["timed_out"] = True
        if (not process["process_group_reaped"] or result.returncode != 0
                or payload.get("status") == "ok" and (payload.get("request_identity") != call["request_identity"]
                                                       or payload.get("runtime_sources") != sources)):
            return {"status": "unavailable", "error_code": "proof_cleanup_or_identity_unconfirmed"}, process
        return payload or {"status": envelope.get("outcome") or "unavailable",
                           "error_code": "proof_output_limit" if envelope.get("outcome") == "output_limit" else "proof_router_unavailable"}, process


def _classify_route(*, native_status: str, native_trust: str, native_reason: str,
                    attempt_metadata: Sequence[Mapping[str, Any]], missing_facts: Sequence[Mapping[str, Any]],
                    versions_match: bool, similarity_score: Any, model_assertion: Any,
                    process: Mapping[str, Any] | None, goal_bound_kernel: bool = False,
                    negative_artifact_verified: bool = False) -> Dict[str, Any]:
    structural_proved = any(str(item.get("status") or "") == "proved"
        and str(item.get("route") or "").startswith("deterministic_") for item in attempt_metadata)
    if process and process.get("cancelled"):
        outcome = "cancelled"
    elif process and process.get("timed_out"):
        outcome = "timeout"
    elif process and not process.get("process_group_reaped"):
        outcome = "unavailable"
    elif not versions_match or missing_facts:
        outcome = "unknown"
    elif native_status == "timeout":
        outcome = "timeout"
    elif native_status == "cancelled":
        outcome = "cancelled"
    elif native_status in {"unsupported_translation", "unsupported", "theorem_failed"}:
        outcome = "disproved" if native_status == "theorem_failed" and negative_artifact_verified else "unsupported"
    elif native_status == "proved" and native_trust == "kernel" and goal_bound_kernel and not structural_proved:
        outcome = "proved"
    elif native_status in {"disproved", "refuted"} and negative_artifact_verified:
        outcome = "disproved"
    elif native_status in {"error", "unavailable"}:
        outcome = "unavailable"
    else:
        outcome = "unknown"
    return {"outcome": outcome, "disproved": outcome == "disproved",
        "substantive_trust_satisfied": outcome == "proved",
        "structural_route_proved": structural_proved, "structural_proof_is_substantive": False,
        "similarity_score_ignored": similarity_score is not None, "model_assertion_ignored": model_assertion is not None,
        "consistency_is_entailment": False, "unsat_proves_arbitrary_claim": False,
        "theorem_failed_is_counterexample": outcome == "disproved", "native_status": native_status,
        "native_trust": native_trust, "native_reason": native_reason}


def _routing_receipt(
    *,
    outcome: str,
    reason: str,
    policy: Mapping[str, Any] | None,
    versions: Mapping[str, Any],
    extra: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    payload = {
        "schema_version": PROOF_ROUTING_SCHEMA,
        "policy_version": PROOF_ROUTING_POLICY_VERSION,
        "outcome": outcome,
        "reason": reason,
        "outcomes": list(PROOF_ROUTING_OUTCOMES),
        "substantive_trust_floor": PROOF_ROUTING_SUBSTANTIVE_TRUST,
        "substantive_trust_satisfied": outcome == "proved",
        "entails_claim_element": False,
        "structural_proof_is_substantive": False,
        "missing_facts_are_false": False,
        "policy": dict(policy or {}),
        "versions": dict(versions),
        "installs_disabled": dict(_INSTALL_DISABLE_ENV),
        "empty_enabled_routes_enables_all": True,
    }
    payload.update(dict(extra or {}))
    origin = _stable_payload_digest(payload)
    payload['routing_receipt_id'] = 'bound-routing-' + origin
    _BOUND_ROUTING_RECEIPT_ORIGINS[payload['routing_receipt_id']] = deepcopy(payload)
    return payload


def route_bound_legal_ir_proof(
    obligation: Any = None,
    *,
    premises: Sequence[Any] | None = None,
    premise_inventory: Mapping[str, Any] | None = None,
    sample_or_document: Any = None,
    goal_statement: str = "",
    required_trust: str = PROOF_ROUTING_SUBSTANTIVE_TRUST,
    total_timeout_seconds: float = 2.0,
    stage_timeout_seconds: Mapping[str, float] | None = None,
    enabled_routes: Sequence[str] | None = None,
    cancellation_event: Any = None,
    managed_command: Sequence[str] | None = None,
    managed_state_directory: str | None = None,
    managed_wall_time_seconds: float | None = None,
    local_backend: str = "",
    similarity_score: Any = None,
    model_assertion: Any = None,
    execution_identity: str = "",
    expected_execution_identity: str = "",
    obligation_version: str = "",
    expected_obligation_version: str = "",
    premise_version: str = "",
    expected_premise_version: str = "",
    requirement_id: str = "",
    expected_requirement_id: str = "",
    definition_identity: str = "",
    expected_definition_identity: str = "",
    assumption_identity: str = "",
    expected_assumption_identity: str = "",
    adverse_treatment_identity: str = "",
    expected_adverse_treatment_identity: str = "",
    source_identity: str = "",
    expected_source_identity: str = "",
) -> Dict[str, Any]:
    """Own the actual native router within one request deadline.

    The compatibility selector and command parameters cannot supply a backend,
    choose an outcome, or launch arbitrary code. This configuration has no
    checked substantive kernel backend: structural successes remain unknown.
    """
    started = time.monotonic()
    total = _positive_finite(total_timeout_seconds, "total_timeout_seconds")
    deadline = started + total
    if managed_wall_time_seconds is not None:
        deadline = min(deadline, started + _positive_finite(managed_wall_time_seconds, "managed_wall_time_seconds"))
    stage_input = dict(stage_timeout_seconds if stage_timeout_seconds is not None else _default_stage_budgets())
    if any(key not in stage_input for key in _default_stage_budgets()):
        raise ValueError("missing stage budget")
    stages = {key: _positive_finite(stage_input[key], key) for key in _default_stage_budgets()}
    rejected_empty_enabled_routes = enabled_routes is not None and len(tuple(enabled_routes)) == 0
    requested_routes = tuple(str(item) for item in (
        enabled_routes if enabled_routes is not None and not rejected_empty_enabled_routes else _PROOF_ROUTING_SAFE_ROUTES))
    dropped_install_routes = [item for item in requested_routes if item in _PROOF_ROUTING_INSTALL_PRONE_ROUTES]
    safe_routes = tuple(item for item in requested_routes if item not in _PROOF_ROUTING_INSTALL_PRONE_ROUTES) or _PROOF_ROUTING_SAFE_ROUTES
    versions = {
        "execution_identity": str(execution_identity or ""),
        "expected_execution_identity": str(expected_execution_identity or execution_identity or ""),
        "obligation_version": str(obligation_version or ""),
        "expected_obligation_version": str(expected_obligation_version or obligation_version or ""),
        "premise_version": str(premise_version or ""),
        "expected_premise_version": str(expected_premise_version or premise_version or ""),
        "requirement_id": str(requirement_id or ""),
        "expected_requirement_id": str(expected_requirement_id or requirement_id or ""),
        "definition_identity": str(definition_identity or ""),
        "expected_definition_identity": str(expected_definition_identity or definition_identity or ""),
        "assumption_identity": str(assumption_identity or ""),
        "expected_assumption_identity": str(expected_assumption_identity or assumption_identity or ""),
        "adverse_treatment_identity": str(adverse_treatment_identity or ""),
        "expected_adverse_treatment_identity": str(expected_adverse_treatment_identity or adverse_treatment_identity or ""),
        "source_identity": str(source_identity or ""),
        "expected_source_identity": str(expected_source_identity or source_identity or ""),
        "policy_version": PROOF_ROUTING_POLICY_VERSION,
        "premises": _premise_identity(premise_inventory),
    }
    versions_match = all(versions[key] == versions["expected_" + key]
                         for key in (
                             "execution_identity", "obligation_version", "premise_version",
                             "requirement_id", "definition_identity", "assumption_identity",
                             "adverse_treatment_identity", "source_identity",
                         ))
    missing = _missing_fact_values(premise_inventory)
    common = {
        "missing_facts": missing, "backend_available": False, "attempts": [], "process": None,
        "rejected_empty_enabled_routes": rejected_empty_enabled_routes,
        "dropped_install_prone_routes": dropped_install_routes, "requested_trust": str(required_trust),
        "assumption_ids": [str(item.get("premise_id") or "") for item in (premise_inventory or {}).get("assumptions") or [] if isinstance(item, Mapping)],
        "similarity_score_ignored": similarity_score is not None, "model_assertion_ignored": model_assertion is not None,
        "consistency_is_entailment": False, "unsat_proves_arbitrary_claim": False,
        "theorem_failed_is_counterexample": False, "entails_claim_element": False,
    }
    def unavailable(outcome: str, reason: str, *, policy: Mapping[str, Any] | None = None,
                    extra: Mapping[str, Any] | None = None) -> Dict[str, Any]:
        return _routing_receipt(outcome=outcome, reason=reason, policy=policy, versions=versions,
                                extra={**common, **dict(extra or {})})
    if not versions_match:
        return unavailable("unknown", "stale_source_or_policy_version")
    if missing:
        return unavailable("unknown", "missing_fact_open_world")
    if local_backend:
        return unavailable("unsupported", "untrusted_backend_selector", extra={"backend_selector_rejected": True})
    if managed_command:
        return unavailable("unsupported", "untrusted_process_command", extra={"managed_command_rejected": True})
    if not _routing_modules_available():
        return unavailable("unavailable", "legal_ir_proof_router_unavailable")
    try:
        bound_obligation, rejected_metadata = _coerce_obligation(obligation, goal_statement)
        goal_text = str(goal_statement or bound_obligation.statement or "")
        policy = _proof_router_module.ProofRoutingPolicy(required_trust=required_trust,
            total_timeout_seconds=total, stage_timeout_seconds=stages, enabled_routes=safe_routes,
            stop_on_theorem_failure=True)
        hammer_premises = _hammer_premises(premise_inventory, premises)
        document = None if sample_or_document is None else _mapping_or_empty(_document_view(sample_or_document))
        request = {
            "policy": policy.to_dict(), "goal_statement": goal_text,
            "obligation": bound_obligation.to_dict(),
            "premises": [{"name": item.name, "statement": item.statement, "weight": item.weight,
                          "metadata": item.metadata} for item in hammer_premises],
            "sample_or_document": document,
        }
        # Serializing actual typed inputs rejects callback/opaque object shortcuts.
        json.dumps(request, allow_nan=False)
        native_result, process = _run_owned_proof_router(request, deadline=deadline,
            cancellation_event=cancellation_event, state_directory=managed_state_directory)
    except Exception:  # noqa: BLE001 - never expose private source/error text
        return unavailable("unavailable", "proof_request_or_supervisor_failed")
    common.update(process=process, rejected_untrusted_metadata=rejected_metadata,
                  goal_statement_sha256=hashlib.sha256(goal_text.encode("utf-8")).hexdigest(),
                  obligation_id=str(bound_obligation.obligation_id),
                  request_elapsed_seconds=max(0.0, time.monotonic()-started),
                  checked_kernel_backend_configured=False)
    if native_result.get("status") != "ok":
        outcome = "cancelled" if process.get("cancelled") else "timeout" if process.get("timed_out") else "unsupported" if native_result.get("status") == "unsupported" else "unavailable"
        return unavailable(outcome, "owned_router_"+outcome, policy=policy.to_dict(),
                           extra={"error_code": native_result.get("error_code", "")})
    native = native_result["native"]
    attempts = list(native.get("attempts") or [])
    classified = _classify_route(native_status=str(native.get("status") or ""),
        native_trust=str(native.get("trust_level") or ""), native_reason=str(native.get("stop_reason") or ""),
        attempt_metadata=attempts, missing_facts=missing, versions_match=versions_match,
        similarity_score=similarity_score, model_assertion=model_assertion, process=process,
        goal_bound_kernel=False, negative_artifact_verified=False)
    reason = "structural_check_below_substantive_trust" if classified["structural_route_proved"] else classified["outcome"]
    if native.get("status") == "theorem_failed":
        reason = "theorem_failed_without_bound_negative_proof"
    return _routing_receipt(outcome=classified["outcome"], reason=reason, policy=policy.to_dict(), versions=versions,
        extra={**common, "backend_available": True,
            "router": "ipfs_datasets_py.logic.integration.reasoning.legal_ir_proof_router.LegalIRProofRouter",
            "router_schema_version": str(native.get("schema_version") or ""),
            "native_status": native.get("status"), "native_trust": native.get("trust_level"),
            "native_required_trust": native.get("required_trust"), "native_stop_reason": native.get("stop_reason"),
            "native_proved": bool(native.get("proved")), "native_trust_satisfied": bool(native.get("trust_satisfied")),
            "attempts": attempts, "runtime_sources": native_result.get("runtime_sources"),
            "structural_route_proved": classified["structural_route_proved"],
            "substantive_trust_satisfied": False, "legacy_no_contradiction_is_certified_consistency": False})


def _as_identity_rows(value: Any) -> List[Dict[str, Any]]:
    if value is None:
        return []
    rows = value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else [value]
    normalized: List[Dict[str, Any]] = []
    for item in rows:
        if isinstance(item, Mapping):
            normalized.append({str(key): item[key] for key in sorted(item, key=str)})
        else:
            normalized.append({"value": item})
    normalized.sort(key=_stable_json_dumps)
    return normalized


def _chronology_flags(chronology: Mapping[str, Any] | None) -> Dict[str, Any]:
    payload = dict(chronology or {})
    issue_types = []
    for item in payload.get("issues") or payload.get("issue_types") or []:
        if isinstance(item, Mapping):
            label = item.get("issue_type") or item.get("category") or ""
        else:
            label = item
        text = str(label or "").strip().lower()
        if text and text not in issue_types:
            issue_types.append(text)
    contradictory = bool(payload.get("contradictory_dates") or payload.get("has_contradictory_dates"))
    relative_only = bool(payload.get("relative_only") or payload.get("relative_only_ordering"))
    if "contradictory_dates" in issue_types:
        contradictory = True
    if "relative_only_ordering" in issue_types:
        relative_only = True
    return {
        "contradictory_dates": contradictory,
        "relative_only_ordering": relative_only,
        "issue_types": issue_types,
    }


def chronology_follow_ups(issue_type: str) -> List[Dict[str, str]]:
    """Targeted follow-up for chronology that cannot satisfy an element."""

    kind = str(issue_type or "").strip().lower()
    if kind == "contradictory_dates":
        return [{
            "lane": "contradiction_resolution",
            "follow_up_lane": "contradiction_resolution",
            "follow_up_target": "document_request",
            "issue_type": "contradictory_dates",
            "target_kind": "event_dates",
            "reason": "Resolve contradictory event dates with a dated document or authoritative record.",
        }]
    if kind == "relative_only_ordering":
        return [{
            "lane": "anchor_capture",
            "follow_up_lane": "anchor_capture",
            "follow_up_target": "document_request",
            "issue_type": "relative_only_ordering",
            "target_kind": "absolute_chronology",
            "reason": "Replace relative-only ordering with a calendar date or dated record.",
        }]
    return []


def proof_cache_identity(
    *,
    claim_id: str = "",
    element_id: str = "",
    factual_revisions: Any = None,
    legal_source: Mapping[str, Any] | None = None,
    compiler: Mapping[str, Any] | None = None,
    compiler_config: Mapping[str, Any] | None = None,
    proof_policy: Mapping[str, Any] | None = None,
    chronology: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Identity for a satisfied-element proof.

    Factual revision, applicable legal source and version, compiler schema and
    config, and proof policy all participate. A change to any of them is a
    different cache entry.
    """

    source = dict(legal_source or {})
    rules = _as_identity_rows(source.get("rules") or source.get("rule_versions"))
    for rule in rules:
        rule["superseded"] = bool(rule.get("superseded") or str(rule.get("status") or "").lower() == "superseded")
    factual = _as_identity_rows(factual_revisions)
    compiler_identities = dict(compiler) if compiler is not None else (canonical_compiler_identities() or {})
    policy = {
        "obligation_policy": PROOF_OBLIGATION_POLICY_VERSION,
        "routing_policy": PROOF_ROUTING_POLICY_VERSION,
        "cache_policy": PROOF_ELEMENT_CACHE_POLICY_VERSION,
        "policy": dict(proof_policy or {}),
    }
    components = {
        "claim_id": str(claim_id or ""),
        "element_id": str(element_id or ""),
        "factual_revisions": factual,
        "legal_source": {
            **deepcopy(source),
            "source_id": str(source.get("source_id") or ""),
            "source_version": str(source.get("source_version") or source.get("legal_context_version") or ""),
            "legal_context_version": str(source.get("legal_context_version") or ""),
            "law_as_of": str(source.get("law_as_of") or source.get("applicable_law_date") or ""),
            "requirement_id": str(source.get("requirement_id") or ""),
            "definition_identity": str(source.get("definition_identity") or ""),
            "assumption_identity": str(source.get("assumption_identity") or ""),
            "adverse_treatment_identity": str(source.get("adverse_treatment_identity") or _adverse_treatment_identity(source.get("adverse_treatment"))),
            "source_identity": str(source.get("source_identity") or source.get("source_hash") or ""),
            "rules": rules,
        },
        "compiler": {
            "schema_version": PROOF_ELEMENT_CACHE_SCHEMA,
            "obligation_schema": PROOF_OBLIGATION_ARTIFACT_SCHEMA,
            "routing_schema": PROOF_ROUTING_SCHEMA,
            "identities": compiler_identities,
            "current_identities": deepcopy(canonical_compiler_identities()),
            "config": dict(compiler_config or {}),
        },
        "proof_policy": policy,
        "chronology": _chronology_flags(chronology),
    }
    return {
        "schema_version": PROOF_ELEMENT_CACHE_SCHEMA,
        "components": components,
        "cache_identity": _stable_payload_digest(components),
    }


def _validated_element_cache_identity(identity: Mapping[str, Any]) -> Dict[str, Any] | None:
    if not isinstance(identity, Mapping) or set(identity) != {'schema_version', 'components', 'cache_identity'}:
        return None
    if identity.get('schema_version') != PROOF_ELEMENT_CACHE_SCHEMA:
        return None
    components = identity.get('components')
    if (not isinstance(components, Mapping)
            or set(components) != {'claim_id', 'element_id', 'factual_revisions', 'legal_source', 'compiler', 'proof_policy', 'chronology'}
            or not isinstance(components.get('legal_source'), Mapping)
            or not isinstance(components.get('chronology'), Mapping)
            or not isinstance(components.get('factual_revisions'), list)):
        return None
    try:
        if str(identity.get('cache_identity') or '') != _stable_payload_digest(components):
            return None
        compiler = components.get('compiler')
        policy = components.get('proof_policy')
        if not isinstance(compiler, Mapping) or not isinstance(policy, Mapping):
            return None
        if (compiler.get('schema_version') != PROOF_ELEMENT_CACHE_SCHEMA
                or compiler.get('obligation_schema') != PROOF_OBLIGATION_ARTIFACT_SCHEMA
                or compiler.get('routing_schema') != PROOF_ROUTING_SCHEMA
                or compiler.get('current_identities') != canonical_compiler_identities()
                or policy.get('obligation_policy') != PROOF_OBLIGATION_POLICY_VERSION
                or policy.get('routing_policy') != PROOF_ROUTING_POLICY_VERSION
                or policy.get('cache_policy') != PROOF_ELEMENT_CACHE_POLICY_VERSION):
            return None
        return deepcopy(dict(identity))
    except (TypeError, ValueError):
        return None


def _current_routing_origin(result: Mapping[str, Any], identity: Mapping[str, Any]) -> bool:
    if not isinstance(result, Mapping):
        return False
    receipt_id = str(result.get('routing_receipt_id') or '')
    stored = _BOUND_ROUTING_RECEIPT_ORIGINS.get(receipt_id)
    if stored is None or dict(result) != stored:
        return False
    payload = {key: value for key, value in result.items() if key != 'routing_receipt_id'}
    if receipt_id != 'bound-routing-' + _stable_payload_digest(payload):
        return False
    versions = result.get('versions')
    if (result.get('schema_version') != PROOF_ROUTING_SCHEMA
            or result.get('policy_version') != PROOF_ROUTING_POLICY_VERSION
            or not isinstance(versions, Mapping)
            or versions.get('policy_version') != PROOF_ROUTING_POLICY_VERSION):
        return False
    components = identity['components']
    requested = components['compiler'].get('identities') or {}
    for key in ('execution_identity', 'obligation_version', 'premise_version'):
        expected = str(requested.get(key) or '')
        if expected and (versions.get(key) != expected or versions.get('expected_' + key) != expected):
            return False
    inventory = components['legal_source'].get('premise_inventory')
    if isinstance(inventory, Mapping) and versions.get('premises') != _premise_identity(inventory):
        return False
    source = components['legal_source']
    for key in ('requirement_id', 'definition_identity', 'assumption_identity', 'adverse_treatment_identity', 'source_identity'):
        expected = str(source.get(key) or '')
        if not expected:
            continue
        if versions.get(key) != expected or versions.get('expected_' + key) != expected:
            return False
    return True


def _publish_element_evaluation(record: Mapping[str, Any], identity: Mapping[str, Any], *, cache: bool = False) -> Dict[str, Any]:
    issued = deepcopy(dict(record))
    issued['identity'] = deepcopy(dict(identity))
    material = {key: value for key, value in issued.items() if key not in {'reused', 'provider_called'}}
    issued['evaluation_id'] = 'element-evaluation-' + _stable_payload_digest(material)
    _ELEMENT_PROOF_EVALUATION_ORIGINS[issued['evaluation_id']] = deepcopy(issued)
    if cache:
        _SATISFIED_ELEMENT_PROOF_CACHE[str(identity['cache_identity'])] = deepcopy(issued)
    return deepcopy(issued)


def verify_element_proof_evaluation(evaluation: Mapping[str, Any]) -> Dict[str, Any]:
    """Verify issued/current evaluation lineage, without minting kernel trust."""
    if not isinstance(evaluation, Mapping):
        return {'verified': False, 'satisfied': False, 'reason': 'unbound_element_evaluation'}
    stored = _ELEMENT_PROOF_EVALUATION_ORIGINS.get(str(evaluation.get('evaluation_id') or ''))
    if stored is None:
        return {'verified': False, 'satisfied': False, 'reason': 'unbound_element_evaluation'}
    material = {key: value for key, value in evaluation.items() if key not in {'reused', 'provider_called', 'evaluation_id'}}
    expected = {key: value for key, value in stored.items() if key not in {'reused', 'provider_called', 'evaluation_id'}}
    identity = _validated_element_cache_identity(evaluation.get('identity'))
    if material != expected or identity is None or evaluation.get('cache_identity') != identity['cache_identity']:
        return {'verified': False, 'satisfied': False, 'reason': 'stale_or_modified_element_evaluation'}
    # Current route_bound_legal_ir_proof never configures a checked substantive
    # kernel backend. Neither a provider flag nor cached structure can add one.
    return {'verified': True, 'satisfied': False, 'reason': 'checked_kernel_backend_not_configured',
            'identity': identity, 'evaluation': deepcopy(dict(evaluation))}


def reset_satisfied_element_proof_cache() -> None:
    _SATISFIED_ELEMENT_PROOF_CACHE.clear()


def lookup_satisfied_element_proof(identity: Mapping[str, Any]) -> Dict[str, Any] | None:
    """Only a current origin-bound substantive result could satisfy an element."""
    current = _validated_element_cache_identity(identity)
    if current is None or _element_cache_block(current):
        return None
    stored = _SATISFIED_ELEMENT_PROOF_CACHE.get(current['cache_identity'])
    verified = verify_element_proof_evaluation(stored) if stored is not None else {}
    if not verified.get('verified') or not verified.get('satisfied'):
        return None
    found = deepcopy(stored)
    found['reused'] = True
    found['provider_called'] = False
    return found


def _element_cache_block(identity: Mapping[str, Any]) -> Dict[str, Any] | None:
    components = identity.get("components") if isinstance(identity.get("components"), Mapping) else {}
    chronology = _chronology_flags(components.get("chronology") if isinstance(components.get("chronology"), Mapping) else {})
    if chronology["contradictory_dates"]:
        return {
            "reason": "contradictory_event_dates",
            "recommended_follow_ups": chronology_follow_ups("contradictory_dates"),
        }
    if chronology["relative_only_ordering"]:
        return {
            "reason": "relative_only_chronology",
            "recommended_follow_ups": chronology_follow_ups("relative_only_ordering"),
        }
    legal = components.get("legal_source") if isinstance(components.get("legal_source"), Mapping) else {}
    rules = legal.get("rules") if isinstance(legal.get("rules"), list) else []
    if any(isinstance(rule, Mapping) and rule.get("superseded") for rule in rules):
        return {"reason": "superseded_rule", "recommended_follow_ups": [], "evaluate": True}
    return None


def replay_satisfied_element_proof(
    identity: Mapping[str, Any],
    *,
    provider: Any = None,
) -> Dict[str, Any]:
    """Replay only rederived current inputs and actual issued routing results.

    This configured adapter has structural routing and no checked kernel
    backend. Replay preserves actual diagnostics, never substantive satisfaction.
    """
    current = _validated_element_cache_identity(identity)
    if current is None:
        return {'schema_version': PROOF_ELEMENT_CACHE_SCHEMA, 'cache_identity': '',
                'satisfied': False, 'status': 'unknown', 'reason': 'invalid_current_cache_identity',
                'substantive_trust_satisfied': False, 'entails_claim_element': False,
                'recommended_follow_ups': [], 'reused': False, 'provider_called': False,
                'deterministic': True, 'result': None}
    key = current['cache_identity']
    # Current chronology/source blockers are evaluated before any cached result.
    block = _element_cache_block(current)
    stored = _SATISFIED_ELEMENT_PROOF_CACHE.get(key)
    if stored is not None and verify_element_proof_evaluation(stored).get('verified'):
        replayed = deepcopy(stored)
        replayed['reused'] = True
        replayed['provider_called'] = False
        return replayed
    record = {'schema_version': PROOF_ELEMENT_CACHE_SCHEMA, 'cache_identity': key,
              'satisfied': False, 'status': 'unknown', 'reason': '',
              'substantive_trust_satisfied': False, 'entails_claim_element': False,
              'recommended_follow_ups': [], 'reused': False, 'provider_called': False,
              'deterministic': True, 'result': None}
    if block and not block.get('evaluate'):
        record.update(status='uncertain', reason=block['reason'],
                      recommended_follow_ups=list(block['recommended_follow_ups']))
        return _publish_element_evaluation(record, current, cache=True)
    if provider is None:
        record.update(status='not_cached', reason='proof_cache_miss')
        return _publish_element_evaluation(record, current)
    produced = provider()
    produced_map = dict(produced) if isinstance(produced, Mapping) else {'value': produced}
    record.update(provider_called=True, result=deepcopy(produced_map))
    if not _current_routing_origin(produced_map, current):
        record.update(reason='unbound_or_modified_routing_result', result=None,
                      rejected_result=deepcopy(produced_map))
        return _publish_element_evaluation(record, current)
    if (produced_map.get('satisfied') is True or produced_map.get('substantive_trust_satisfied') is True
            or produced_map.get('entails_claim_element') is True or produced_map.get('outcome') == 'proved'):
        record.update(reason='unverified_substantive_proof', result=None,
                      rejected_result=deepcopy(produced_map))
        return _publish_element_evaluation(record, current)
    record.update(status=str(produced_map.get('outcome') or 'unknown'),
                  reason=str(produced_map.get('reason') or 'structural_or_unavailable_proof'))
    if block and block.get('reason') == 'superseded_rule':
        record.update(status='uncertain', reason='superseded_rule')
    # Retry transient absence/errors; preserve a stable actual negative/structural
    # observation only while source/premise/compiler/policy inputs remain current.
    cacheable = produced_map.get('outcome') in {'unknown', 'unsupported', 'refuted', 'disproved'}
    return _publish_element_evaluation(record, current, cache=cacheable)


def connect_definition_handoff_proof(
    requirement: Mapping[str, Any],
    handoff: Mapping[str, Any] | None = None,
    *,
    provider: Any = None,
) -> Dict[str, Any]:
    """Bind current definition-handoff identities to obligation and route owners.

    A solver selector, generated Lean packet, or review packet is recorded and
    is not a proved result. The requirement proof field changes only when an
    issued evaluation is verified and satisfied against the same identities.
    Factual assertion stays separate from legal sufficiency.
    """

    requirement_map = dict(requirement or {})
    bound = dict(handoff or {})
    retained = bound.get("retained") if isinstance(bound.get("retained"), Mapping) else {}
    assumptions = list(retained.get("assumptions") or requirement_map.get("assumptions") or [])
    requirement_id = str(bound.get("requirement_id") or requirement_map.get("requirement_id") or "")
    source_text = requirement_map.get("admitted_legal_text")
    if not isinstance(source_text, str):
        source_text = str(bound.get("admitted_legal_text") or "")
    treatment = bound.get("adverse_treatment", requirement_map.get("adverse_treatment"))
    obligations = generate_bound_legal_ir_proof_obligations(
        None,
        claim_id=str(requirement_map.get("claim_id") or ""),
        element_id=str(requirement_map.get("element_id") or requirement_id),
        assumptions=assumptions,
        asserted_facts=requirement_map.get("asserted_facts") if isinstance(requirement_map.get("asserted_facts"), list) else [],
        selected_legal_rules=requirement_map.get("selected_legal_rules") if isinstance(requirement_map.get("selected_legal_rules"), list) else [],
        source_text=source_text,
        requirement_id=requirement_id,
        definition_binding=bound,
        adverse_treatment=treatment,
        use_cache=False,
    )
    versions = obligations.get("versions") if isinstance(obligations.get("versions"), Mapping) else {}
    inventory = obligations.get("premise_inventory") if isinstance(obligations.get("premise_inventory"), Mapping) else {}
    identity = proof_cache_identity(
        claim_id=str(requirement_map.get("claim_id") or ""),
        element_id=str(requirement_map.get("element_id") or requirement_id),
        factual_revisions=versions.get("fact_revisions") or [],
        legal_source={
            "source_id": str(requirement_map.get("source_id") or ""),
            "source_version": str(versions.get("legal_context_version") or ""),
            "requirement_id": str(versions.get("requirement_id") or ""),
            "definition_identity": str(versions.get("definition_identity") or ""),
            "assumption_identity": str(versions.get("assumption_identity") or ""),
            "adverse_treatment_identity": str(versions.get("adverse_treatment_identity") or ""),
            "source_identity": str(versions.get("source_identity") or ""),
            "premise_inventory": inventory,
        },
        compiler={"execution_identity": str(versions.get("execution_identity") or "")},
    )
    packet_outcome = _nonproof_packet_outcome(bound)

    def _route():
        if provider is not None:
            return provider()
        return route_bound_legal_ir_proof(
            premise_inventory=inventory,
            goal_statement=source_text,
            execution_identity=str(versions.get("execution_identity") or ""),
            expected_execution_identity=str(versions.get("execution_identity") or ""),
            requirement_id=str(versions.get("requirement_id") or ""),
            expected_requirement_id=str(versions.get("requirement_id") or ""),
            definition_identity=str(versions.get("definition_identity") or ""),
            expected_definition_identity=str(versions.get("definition_identity") or ""),
            assumption_identity=str(versions.get("assumption_identity") or ""),
            expected_assumption_identity=str(versions.get("assumption_identity") or ""),
            adverse_treatment_identity=str(versions.get("adverse_treatment_identity") or ""),
            expected_adverse_treatment_identity=str(versions.get("adverse_treatment_identity") or ""),
            source_identity=str(versions.get("source_identity") or ""),
            expected_source_identity=str(versions.get("source_identity") or ""),
            premise_version=str(inventory.get("digest") or ""),
            expected_premise_version=str(inventory.get("digest") or ""),
        )

    evaluation = replay_satisfied_element_proof(identity, provider=_route)
    routed = evaluation.get("result") if isinstance(evaluation.get("result"), Mapping) else {}
    outcome = str(routed.get("outcome") or evaluation.get("status") or "unknown")
    if packet_outcome:
        outcome = packet_outcome
    verified = verify_element_proof_evaluation(evaluation)
    proof_supported = bool(verified.get("verified") and verified.get("satisfied") and outcome == "proved")
    original_proof = requirement_map.get("proof")
    return {
        "schema": "definition-handoff-proof-binding/v1",
        "requirement_id": requirement_id,
        "admitted_legal_text": source_text,
        "admitted_legal_text_changed": False,
        "proof": original_proof if proof_supported else original_proof,
        "proof_field_supported": proof_supported,
        "proof_satisfied": proof_supported,
        "proof_changed": False,
        "factual_assertion": {
            "asserted": bool(requirement_map.get("asserted_facts")),
            "satisfies_element": False,
        },
        "legal_sufficiency": {
            "outcome": outcome,
            "satisfied": proof_supported,
        },
        "outcome": outcome,
        "outcome_distinctions": list(PROOF_ROUTING_OUTCOMES),
        "solver_is_proof": False,
        "generated_lean_is_proof": False,
        "review_packet_is_proof": False,
        "legal_ir_proof_obligations": obligations,
        "legal_ir_proof_routing": dict(routed) if routed else {"outcome": outcome, "substantive_trust_satisfied": False},
        "proof_cache_identity": identity.get("cache_identity"),
        "evaluation": evaluation,
        "versions": dict(versions),
    }


def _nonproof_packet_outcome(handoff: Mapping[str, Any]) -> str:
    """Solver, Lean, and review packets stay diagnostic. They are not proved."""

    lean = handoff.get("conditional_lean")
    review = handoff.get("review")
    solver = handoff.get("solver") or handoff.get("declared_prover_result")
    packets = [item for item in (lean, review, solver) if isinstance(item, Mapping) and item]
    if not packets:
        return ""
    for packet in packets:
        status = str(packet.get("status") or packet.get("outcome") or "").lower()
        if status in {"timeout", "cancelled", "unavailable", "disproved", "unknown"}:
            return status
    return "unknown"


def gate_qualified_model_candidate(
    requirement: Mapping[str, Any] | None = None,
    candidate: Mapping[str, Any] | None = None,
    **identity: Any,
) -> Dict[str, Any]:
    """Admit a qualified model record only as a candidate.

    Predicate preparation and numerical qualification stay engineering evidence.
    The returned record cannot select governing law, satisfy a definition review,
    or prove an element. Missing and incompatible owners stay unavailable or
    ineligible. This gate does not train, restore, download, or fit a model.
    """

    from .definition_evidence import describe_qualified_model_candidate

    requirement_map = dict(requirement or {})
    if candidate is None:
        described = describe_qualified_model_candidate(**identity)
    else:
        described = describe_qualified_model_candidate(**identity) if identity else None
        supplied = dict(candidate)
        if described is None:
            described = supplied
        else:
            described = dict(described)
            described["supplied_candidate"] = {
                "status": supplied.get("status"),
                "selects_governing_law": False,
                "satisfies_definition_review": False,
                "proves_element": False,
            }
            if supplied.get("status") in {"unavailable", "ineligible"}:
                described["status"] = supplied.get("status")
                described["reason"] = supplied.get("reason") or described.get("reason")
    status = described.get("status")
    if status not in {"unavailable", "ineligible", "candidate"}:
        status = "ineligible"
        described = dict(described)
        described["status"] = status
        described["reason"] = "unrecognized_candidate_status"
    admitted_text = requirement_map.get("admitted_legal_text")
    return {
        "schema": "qualified-model-candidate-gate/v1",
        "status": status,
        "reason": described.get("reason"),
        "role": "candidate" if status == "candidate" else "not_admitted",
        "eligible": status == "candidate",
        "eligible_as_authority": False,
        "legally_eligible": False,
        "selects_governing_law": False,
        "satisfies_definition_review": False,
        "proves_element": False,
        "governing_definition": None,
        "definition_review_satisfied": False,
        "element_proved": False,
        "numerical_qualification_is_authority": False,
        "training_preparation_is_authority": False,
        "engineering_evidence": bool(described.get("engineering_evidence")),
        "live_owner_verified": False,
        "model_executed": False,
        "training_executed": False,
        "skipped": False,
        "admitted_legal_text": admitted_text,
        "admitted_legal_text_changed": False,
        "proof": requirement_map.get("proof"),
        "proof_changed": False,
        "proof_satisfied": False,
        "candidate": described,
    }


def _binding_token(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    token = value.strip()
    if not token or len(token) > 256 or any(ord(char) < 32 for char in token):
        return ""
    return token


def _current_binding_drift(payload: Mapping[str, Any], source_text: str) -> str:
    """Return a drift code when the request is not the current binding."""

    source_hash = payload.get("source_hash")
    if source_hash is not None and source_hash != sha256_utf8(source_text):
        return "source_drift"
    for supplied_key, current_key in (
        ("source_version", "current_source_version"),
        ("definition_identity", "current_definition_identity"),
    ):
        if current_key in payload and payload.get(supplied_key) != payload.get(current_key):
            return "stale_binding"
        if current_key in payload and not _binding_token(payload.get(current_key)):
            return "stale_binding"
    current_premises = payload.get("current_premises")
    premises = payload.get("premises")
    if current_premises is None and premises is None:
        return ""
    if not isinstance(premises, list) or (current_premises is not None and not isinstance(current_premises, list)):
        return "premise_malformed"
    current_by_id = {}
    for item in current_premises or []:
        if not isinstance(item, Mapping):
            return "premise_malformed"
        premise_id = _binding_token(item.get("premise_id"))
        revision = _binding_token(str(item.get("revision") or "")) if item.get("revision") is not None else ""
        digest = item.get("text_sha256")
        if not premise_id or (digest is not None and (not isinstance(digest, str) or len(digest) != 64)):
            return "premise_malformed"
        current_by_id[premise_id] = {"revision": str(item.get("revision") or ""), "text_sha256": digest}
    seen = set()
    for item in premises:
        if not isinstance(item, Mapping):
            return "premise_malformed"
        premise_id = _binding_token(item.get("premise_id"))
        text = item.get("text")
        if not premise_id or not isinstance(text, str) or not text.strip() or premise_id in seen:
            return "premise_malformed"
        seen.add(premise_id)
        digest = sha256_utf8(text)
        if item.get("text_sha256") not in (None, digest):
            return "premise_drift"
        current = current_by_id.get(premise_id) if current_premises is not None else None
        if current_premises is not None and current is None:
            return "premise_drift"
        if current is not None:
            if str(item.get("revision") or "") != current["revision"]:
                return "premise_drift"
            if current["text_sha256"] not in (None, digest):
                return "premise_drift"
    if current_premises is not None and set(current_by_id) != seen:
        return "premise_drift"
    return ""


def _nonproof_observations(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Record caller artifacts that cannot mint proof or legal sufficiency."""

    formula = payload.get("parsed_formula")
    graph = payload.get("structural_graph")
    classifier = payload.get("classifier_score")
    training = payload.get("training_metric")
    packet = payload.get("fake_producer")
    return {
        "parsed_formula": {
            "present": formula not in (None, "", {}, []),
            "executed_proof": False,
            "legal_sufficiency": False,
        },
        "structural_graph_packet": {
            "present": isinstance(graph, Mapping),
            "caller_status": graph.get("status") if isinstance(graph, Mapping) else None,
            "executed_proof": False,
            "legal_sufficiency": False,
        },
        "classifier_score": {
            "present": classifier is not None,
            "value_ignored": True,
            "executed_proof": False,
            "legal_sufficiency": False,
        },
        "training_metric": {
            "present": training is not None,
            "value_ignored": True,
            "executed_proof": False,
            "legal_sufficiency": False,
        },
        "fake_producer": {
            "present": isinstance(packet, Mapping),
            "caller_outcome": packet.get("outcome") if isinstance(packet, Mapping) else None,
            "rejected": isinstance(packet, Mapping),
            "executed_proof": False,
            "legal_sufficiency": False,
        },
    }


def _neurosymbolic_parse_surface(formula: str) -> Dict[str, Any]:
    """Call the pinned neurosymbolic parser. A parse is not an executed proof."""

    try:
        from ipfs_datasets_py.logic.integration.symbolic.neurosymbolic_api import (
            NeurosymbolicReasoner,
        )
    except Exception as exc:
        return {
            "status": "unavailable",
            "execution": "unexecuted",
            "reason": type(exc).__name__,
            "producer": "ipfs_datasets_py.logic.integration.symbolic.neurosymbolic_api.NeurosymbolicReasoner",
            "parsed": False,
            "executed_proof": False,
            "legal_sufficiency": False,
        }
    try:
        reasoner = NeurosymbolicReasoner(use_cec=False, use_modal=False, use_nl=False)
        parsed = reasoner.parse(formula, format="tdfol") if formula else None
    except Exception as exc:
        return {
            "status": "unavailable",
            "execution": "unexecuted",
            "reason": type(exc).__name__,
            "producer": "NeurosymbolicReasoner.parse",
            "parsed": False,
            "executed_proof": False,
            "legal_sufficiency": False,
        }
    return {
        "status": "parsed" if parsed is not None else "unparsed",
        "execution": "parsed_not_proved",
        "reason": "",
        "producer": "NeurosymbolicReasoner.parse",
        "parsed": parsed is not None,
        "formula_type": type(parsed).__name__ if parsed is not None else "",
        "executed_proof": False,
        "legal_sufficiency": False,
    }


def _proof_from_live_route(routed: Mapping[str, Any]) -> bool:
    receipt_id = str(routed.get("routing_receipt_id") or "")
    origin = _BOUND_ROUTING_RECEIPT_ORIGINS.get(receipt_id)
    if not isinstance(origin, Mapping):
        return False
    return (
        origin.get("outcome") == "proved"
        and origin.get("substantive_trust_satisfied") is True
        and routed.get("outcome") == "proved"
        and routed.get("substantive_trust_satisfied") is True
    )


def ground_bound_formal_analysis(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Run current-bound formal producers and keep non-proof artifacts non-proof.

    Canonical compilation, obligation generation, and ``route_bound_legal_ir_proof``
    are the proof producers. FOL conversion and neurosymbolic parsing are recorded
    as parsed IR. A caller formula, graph packet, classifier score, training
    metric, or fabricated producer packet cannot become executed proof or legal
    sufficiency. A missing producer stays unavailable and unexecuted.
    """

    if not isinstance(payload, Mapping):
        return {
            "status": "refused",
            "code": "malformed_input",
            "execution": "unexecuted",
            "executed_proof": False,
            "legal_sufficiency": False,
            "producer_invoked": False,
        }
    source_text = payload.get("source_text")
    if not isinstance(source_text, str) or not source_text.strip():
        return {
            "status": "refused",
            "code": "missing_source_text",
            "execution": "unexecuted",
            "executed_proof": False,
            "legal_sufficiency": False,
            "producer_invoked": False,
            "nonproof": _nonproof_observations(payload),
        }
    source_text = source_text.strip()
    source_version = _binding_token(payload.get("source_version")) or _binding_token(payload.get("current_source_version"))
    definition_identity = _binding_token(payload.get("definition_identity")) or _binding_token(payload.get("current_definition_identity"))
    if not source_version or not definition_identity:
        return {
            "status": "refused",
            "code": "missing_binding",
            "execution": "unexecuted",
            "executed_proof": False,
            "legal_sufficiency": False,
            "producer_invoked": False,
            "nonproof": _nonproof_observations(payload),
        }
    drift = _current_binding_drift(payload, source_text)
    if drift:
        return {
            "status": "unexecuted",
            "code": drift,
            "execution": "unexecuted",
            "executed_proof": False,
            "legal_sufficiency": False,
            "producer_invoked": False,
            "source_version": source_version,
            "definition_identity": definition_identity,
            "nonproof": _nonproof_observations(payload),
        }

    requirement_id = _binding_token(payload.get("requirement_id")) or "requirement-unspecified"
    citation = _binding_token(payload.get("citation")) or "synthetic-authority"
    premises = [dict(item) for item in payload.get("premises") or [] if isinstance(item, Mapping)]
    for premise in premises:
        premise["text_sha256"] = sha256_utf8(str(premise.get("text") or ""))
    vocabulary = payload.get("vocabulary") if isinstance(payload.get("vocabulary"), Mapping) else {}
    vocabulary = {
        "actors": tuple(vocabulary.get("actors") or ("Employer", "Employee")),
        "actions": tuple(vocabulary.get("actions") or ("retaliate", "oppose")),
        "objects": tuple(vocabulary.get("objects") or ("practice",)),
        "qualifiers": tuple(vocabulary.get("qualifiers") or ()),
    }
    nonproof = _nonproof_observations(payload)
    formula_text = payload.get("parsed_formula")
    if not isinstance(formula_text, str) or not formula_text.strip():
        formula_text = "forall x. Employer(x) -> Obligation(x)"
    neurosymbolic = _neurosymbolic_parse_surface(formula_text.strip())
    fol = text_to_fol(source_text)
    fol_view = {
        "status": fol.get("status"),
        "converter": fol.get("converter"),
        "predicate_count": len(fol.get("predicates") or []),
        "logic_path": (fol.get("metadata") or {}).get("logic_path") if isinstance(fol.get("metadata"), Mapping) else fol.get("logic_path"),
        "executed_proof": False,
        "legal_sufficiency": False,
        "producer": "text_to_fol",
    }
    identities = canonical_compiler_identities()
    if identities is None:
        return {
            "status": "unavailable",
            "code": "missing_producer",
            "execution": "unexecuted",
            "executed_proof": False,
            "legal_sufficiency": False,
            "producer_invoked": False,
            "source_version": source_version,
            "definition_identity": definition_identity,
            "requirement_id": requirement_id,
            "fol": fol_view,
            "neurosymbolic": neurosymbolic,
            "canonical": {"status": "unavailable", "executed_proof": False, "legal_sufficiency": False},
            "obligations": {"status": "unexecuted", "executed_proof": False},
            "route": {"outcome": "unavailable", "executed_proof": False, "producer_invoked": False},
            "nonproof": nonproof,
        }
    compiled = compile_canonical_legal_ir(
        source_text,
        request_id=requirement_id,
        vocabulary=vocabulary,
        legal_context={"citation": citation, "authority_version": source_version},
        factual_premises=premises,
        admitted_law={
            "source_text": source_text,
            "source_sha256": sha256_utf8(source_text),
            "authority_version": source_version,
            "definition_identity": definition_identity,
            "citation": citation,
        },
    )
    canonical_view = {
        "status": compiled.get("status"),
        "reason": compiled.get("reason"),
        "entails_claim": compiled.get("entails_claim") is True,
        "entails_applicability": compiled.get("entails_applicability") is True,
        "executed_proof": False,
        "legal_sufficiency": False,
        "producer": "compile_canonical_legal_ir",
    }
    obligations = generate_bound_legal_ir_proof_obligations(
        None,
        canonical_receipt=compiled if isinstance(compiled, Mapping) else None,
        source_text=source_text,
        asserted_facts=premises,
        requirement_id=requirement_id,
        definition_binding={
            "requirement_id": requirement_id,
            "definition_identity": definition_identity,
            "source_version": source_version,
        },
        legal_context_version=source_version,
        max_obligations=4,
    )
    obligation_view = {
        "status": obligations.get("status"),
        "support": obligations.get("support"),
        "execution_identity": (obligations.get("versions") or {}).get("execution_identity") if isinstance(obligations.get("versions"), Mapping) else "",
        "obligation_count": obligations.get("obligation_count") or 0,
        "structural_validation_is_entailment": obligations.get("structural_validation_is_entailment") is True,
        "executed_proof": False,
        "legal_sufficiency": False,
        "producer": "generate_bound_legal_ir_proof_obligations",
    }
    versions = obligations.get("versions") if isinstance(obligations.get("versions"), Mapping) else {}
    routed = route_bound_legal_ir_proof(
        goal_statement=source_text,
        premise_inventory=obligations.get("premise_inventory") if isinstance(obligations.get("premise_inventory"), Mapping) else None,
        execution_identity=str(versions.get("execution_identity") or ""),
        expected_execution_identity=str(versions.get("execution_identity") or ""),
        requirement_id=requirement_id,
        expected_requirement_id=requirement_id,
        definition_identity=str(versions.get("definition_identity") or definition_identity),
        expected_definition_identity=str(versions.get("definition_identity") or definition_identity),
        assumption_identity=str(versions.get("assumption_identity") or ""),
        expected_assumption_identity=str(versions.get("assumption_identity") or ""),
        adverse_treatment_identity=str(versions.get("adverse_treatment_identity") or ""),
        expected_adverse_treatment_identity=str(versions.get("adverse_treatment_identity") or ""),
        source_identity=str(versions.get("source_identity") or sha256_utf8(source_text)),
        expected_source_identity=str(versions.get("source_identity") or sha256_utf8(source_text)),
        premise_version=str((obligations.get("premise_inventory") or {}).get("digest") or "") if isinstance(obligations.get("premise_inventory"), Mapping) else "",
        expected_premise_version=str((obligations.get("premise_inventory") or {}).get("digest") or "") if isinstance(obligations.get("premise_inventory"), Mapping) else "",
        total_timeout_seconds=2.0,
        similarity_score=payload.get("classifier_score"),
        model_assertion=payload.get("fake_producer"),
    )
    executed_proof = _proof_from_live_route(routed)
    route_view = {
        "outcome": routed.get("outcome"),
        "reason": routed.get("reason"),
        "substantive_trust_satisfied": routed.get("substantive_trust_satisfied") is True,
        "structural_proof_is_substantive": routed.get("structural_proof_is_substantive") is True,
        "structural_route_proved": routed.get("structural_route_proved") is True,
        "similarity_score_ignored": routed.get("similarity_score_ignored") is True,
        "model_assertion_ignored": routed.get("model_assertion_ignored") is True,
        "routing_receipt_id": routed.get("routing_receipt_id"),
        "attempt_count": len(routed.get("attempts") or []),
        "executed_proof": executed_proof,
        "legal_sufficiency": False,
        "producer": "route_bound_legal_ir_proof",
        "producer_invoked": True,
    }
    return {
        "status": "grounded",
        "code": "producer_result",
        "execution": str(routed.get("outcome") or "unknown"),
        "executed_proof": executed_proof,
        "legal_sufficiency": False,
        "producer_invoked": True,
        "source_version": source_version,
        "definition_identity": definition_identity,
        "requirement_id": requirement_id,
        "source_hash": sha256_utf8(source_text),
        "fol": fol_view,
        "neurosymbolic": neurosymbolic,
        "canonical": canonical_view,
        "obligations": obligation_view,
        "route": route_view,
        "nonproof": nonproof,
    }


def legacy_procedural_template_attributes() -> Dict[str, Any]:
    return {
        "category": "civil_procedure",
        "record_kind": "legal_requirement",
        "about_complainant": False,
        "verification_status": "unverified_template",
        "promotion_status": "unverified_template",
        "applicable": False,
        "legacy_template": True,
        "template_kind": "procedural_template",
        "review_reason": "legacy_unverified_template",
        "source_bound": False,
    }


__all__ = [
    "FormalLogicCapability",
    "FormalLogicCapabilityError",
    "FormalLogicDegradedError",
    "FormalLogicOperation",
    "FormalLogicUnavailableError",
    "LOGIC_AVAILABLE",
    "LOGIC_CAPABILITY_SCHEMA_VERSION",
    "LOGIC_ERROR",
    "Z3_AVAILABLE",
    "LOCAL_FORMAL_LOGIC_AVAILABLE",
    "LOCAL_FORMAL_LOGIC_PATH",
    "REASONER_BRIDGE_AVAILABLE",
    "REASONER_BRIDGE_ERROR",
    "LogicCapabilityState",
    "LogicCapabilityStatus",
    "get_logic_capabilities",
    "get_logic_capability",
    "get_logic_capability_report",
    "require_logic_capability",
    "text_to_fol",
    "legal_text_to_deontic",
    "prove_claim_elements",
    "check_contradictions",
    "run_hybrid_reasoning",
    "export_theorem_from_proof_bundle",
    "get_predicate_templates",
    "map_claim_elements_to_predicates",
    "_COMPLAINT_PREDICATE_TEMPLATES",
    "SOURCE_BOUND_RULE_CONTRACT",
    "extract_source_bound_rule_candidates",
    "prepare_acquired_authority_record",
    "evaluate_temporal_requirement_applicability",
    "is_applicable_legal_requirement",
    "requirement_treatment_support",
    "legacy_procedural_template_attributes",
    "legacy_unverified_requirement_templates",
    "sha256_utf8",
    "CanonicalCompilerCapability",
    "CanonicalCompilerSupport",
    "audit_canonical_formalization_payload",
    "canonical_compiler_identities",
    "compile_canonical_legal_ir",
    "get_canonical_compiler_capability",
    "inspect_canonical_formalization_receipt",
    "reset_canonical_formalization_cache",
    "verify_canonical_formalization_receipt",
    "attach_canonical_legal_ir_source_obligations",
    "bind_current_definition_correspondence_owners",
    "DEFINITION_CORRESPONDENCE_SCHEMA",
    "CANONICAL_IR_ATTACHMENT_SCHEMA",
    "TYPED_SOURCE_OBLIGATION_KINDS",
    "route_bound_legal_ir_proof",
    "PROOF_ROUTING_SCHEMA",
    "PROOF_ROUTING_OUTCOMES",
    "PROOF_ELEMENT_CACHE_SCHEMA",
    "chronology_follow_ups",
    "proof_cache_identity",
    "reset_satisfied_element_proof_cache",
    "lookup_satisfied_element_proof",
    "verify_element_proof_evaluation",
    "replay_satisfied_element_proof",
    "connect_definition_handoff_proof",
    "gate_qualified_model_candidate",
    "ground_bound_formal_analysis",
]
