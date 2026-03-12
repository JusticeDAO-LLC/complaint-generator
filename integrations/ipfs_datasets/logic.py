from __future__ import annotations

from typing import Any, Dict, Iterable

from .loader import import_module_optional
from .types import with_adapter_metadata


_logic_module, _logic_error = import_module_optional("ipfs_datasets_py.logic")
_fol_module, _fol_error = import_module_optional("ipfs_datasets_py.logic.fol")
_deontic_module, _deontic_error = import_module_optional("ipfs_datasets_py.logic.deontic")
_tdfol_module, _tdfol_error = import_module_optional("ipfs_datasets_py.logic.TDFOL")
_z3_module, _z3_error = import_module_optional(
    "ipfs_datasets_py.logic.external_provers.smt.z3_prover_bridge"
)

LOGIC_AVAILABLE = any(
    value is not None
    for value in (_logic_module, _fol_module, _deontic_module, _tdfol_module)
)
LOGIC_ERROR = _logic_error or _fol_error or _deontic_error or _tdfol_error or _z3_error


def text_to_fol(text: str) -> Dict[str, Any]:
    return with_adapter_metadata(
        {
            "status": "not_implemented" if LOGIC_AVAILABLE else "unavailable",
            "predicates": [],
            "source_text": text,
        },
        operation="text_to_fol",
        backend_available=LOGIC_AVAILABLE,
        degraded_reason=LOGIC_ERROR if not LOGIC_AVAILABLE else None,
        implementation_status="not_implemented" if LOGIC_AVAILABLE else "unavailable",
    )


def legal_text_to_deontic(text: str) -> Dict[str, Any]:
    return with_adapter_metadata(
        {
            "status": "not_implemented" if LOGIC_AVAILABLE else "unavailable",
            "norms": [],
            "source_text": text,
        },
        operation="legal_text_to_deontic",
        backend_available=LOGIC_AVAILABLE,
        degraded_reason=LOGIC_ERROR if not LOGIC_AVAILABLE else None,
        implementation_status="not_implemented" if LOGIC_AVAILABLE else "unavailable",
    )


def prove_claim_elements(predicates: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    predicate_list = list(predicates)
    return with_adapter_metadata(
        {
            "status": "not_implemented" if LOGIC_AVAILABLE else "unavailable",
            "provable_elements": [],
            "unprovable_elements": [],
            "predicate_count": len(predicate_list),
        },
        operation="prove_claim_elements",
        backend_available=LOGIC_AVAILABLE,
        degraded_reason=LOGIC_ERROR if not LOGIC_AVAILABLE else None,
        implementation_status="not_implemented" if LOGIC_AVAILABLE else "unavailable",
    )


def check_contradictions(predicates: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    predicate_list = list(predicates)
    return with_adapter_metadata(
        {
            "status": "not_implemented" if LOGIC_AVAILABLE else "unavailable",
            "contradictions": [],
            "predicate_count": len(predicate_list),
        },
        operation="check_contradictions",
        backend_available=LOGIC_AVAILABLE,
        degraded_reason=LOGIC_ERROR if not LOGIC_AVAILABLE else None,
        implementation_status="not_implemented" if LOGIC_AVAILABLE else "unavailable",
    )


def run_hybrid_reasoning(payload: Dict[str, Any]) -> Dict[str, Any]:
    return with_adapter_metadata(
        {
            "status": "not_implemented" if LOGIC_AVAILABLE else "unavailable",
            "result": None,
            "payload_keys": sorted(payload.keys()),
        },
        operation="run_hybrid_reasoning",
        backend_available=LOGIC_AVAILABLE,
        degraded_reason=LOGIC_ERROR if not LOGIC_AVAILABLE else None,
        implementation_status="not_implemented" if LOGIC_AVAILABLE else "unavailable",
    )


__all__ = [
    "LOGIC_AVAILABLE",
    "LOGIC_ERROR",
    "text_to_fol",
    "legal_text_to_deontic",
    "prove_claim_elements",
    "check_contradictions",
    "run_hybrid_reasoning",
]