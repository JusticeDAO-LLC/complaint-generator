"""Typed capability contracts for optional formal-logic operations.

Python callers use these immutable contracts to gate execution without parsing
display strings.  JSON consumers receive the same state through ``as_dict`` at
the serialization boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Optional


class LogicCapabilityState(str, Enum):
    """Implementation state of a formal-logic operation."""

    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"
    IMPLEMENTED = "implemented"

    @property
    def available(self) -> bool:
        """Whether the operation can return a useful result."""

        return self is not LogicCapabilityState.UNAVAILABLE

    @property
    def degraded(self) -> bool:
        """Whether only a partial or fallback contract is available."""

        return self is LogicCapabilityState.DEGRADED

    @property
    def implemented(self) -> bool:
        """Whether the operation fulfils its complete formal contract."""

        return self is LogicCapabilityState.IMPLEMENTED


# Descriptive alias for consumers that call the enum a status.
LogicCapabilityStatus = LogicCapabilityState


class FormalLogicOperation(str, Enum):
    """Stable identifiers for public formal-logic operations."""

    TEXT_TO_FOL = "text_to_fol"
    LEGAL_TEXT_TO_DEONTIC = "legal_text_to_deontic"
    PROVE_CLAIM_ELEMENTS = "prove_claim_elements"
    CHECK_CONTRADICTIONS = "check_contradictions"
    RUN_HYBRID_REASONING = "run_hybrid_reasoning"

    @classmethod
    def coerce(cls, value: "FormalLogicOperation | str") -> "FormalLogicOperation":
        """Normalize an API-boundary value or raise a useful validation error."""

        if isinstance(value, cls):
            return value
        try:
            return cls(str(value))
        except ValueError as exc:
            supported = ", ".join(operation.value for operation in cls)
            raise ValueError(
                f"Unknown formal-logic operation {value!r}; expected one of: {supported}"
            ) from exc


class FormalLogicCapabilityError(RuntimeError):
    """Base error raised when a capability cannot satisfy a requested gate."""

    error_code = "formal_logic_capability_error"

    def __init__(self, capability: "FormalLogicCapability", *, required: str) -> None:
        self.capability = capability
        self.operation = capability.operation
        self.state = capability.state
        self.required = required
        reason = capability.reason or "no diagnostic was provided"
        super().__init__(
            f"Formal logic operation '{capability.operation.value}' requires {required}; "
            f"state is '{capability.state.value}': {reason}"
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a stable error payload for API and job-runner boundaries."""

        return {
            "error": self.error_code,
            "operation": self.operation.value,
            "required": self.required,
            "status": self.state.value,
            "reason": self.capability.reason,
            "capability": self.capability.as_dict(),
        }


class FormalLogicUnavailableError(FormalLogicCapabilityError):
    """Raised when an operation has no executable provider or fallback."""

    error_code = "formal_logic_unavailable"


class FormalLogicDegradedError(FormalLogicCapabilityError):
    """Raised when full formal validation is requested from a fallback."""

    error_code = "formal_logic_degraded"


@dataclass(frozen=True)
class FormalLogicCapability:
    """Immutable capability description used to gate one operation.

    ``available`` includes degraded operations because they can provide a
    useful structural result.  ``implemented`` remains false so authoritative
    validation can explicitly reject partial behavior.
    """

    operation: FormalLogicOperation
    state: LogicCapabilityState
    provider: str
    module_path: str
    reason: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation", FormalLogicOperation.coerce(self.operation))
        if not isinstance(self.state, LogicCapabilityState):
            object.__setattr__(self, "state", LogicCapabilityState(str(self.state)))
        object.__setattr__(self, "provider", str(self.provider or "").strip())
        object.__setattr__(self, "module_path", str(self.module_path or "").strip())
        normalized_reason = str(self.reason or "").strip() or None
        object.__setattr__(self, "reason", normalized_reason)
        object.__setattr__(self, "details", MappingProxyType(dict(self.details or {})))

        if self.state is not LogicCapabilityState.IMPLEMENTED and not normalized_reason:
            raise ValueError("Unavailable and degraded capabilities require a reason")

    @property
    def available(self) -> bool:
        return self.state.available

    @property
    def degraded(self) -> bool:
        return self.state is LogicCapabilityState.DEGRADED

    @property
    def implemented(self) -> bool:
        return self.state.implemented

    def require_available(self) -> "FormalLogicCapability":
        """Return self when usable; otherwise raise a deterministic error."""

        if not self.available:
            raise FormalLogicUnavailableError(self, required="an available capability")
        return self

    def require_implemented(self) -> "FormalLogicCapability":
        """Require authoritative implementation rather than fallback behavior."""

        if self.state is LogicCapabilityState.UNAVAILABLE:
            raise FormalLogicUnavailableError(self, required="an implemented capability")
        if self.state is LogicCapabilityState.DEGRADED:
            raise FormalLogicDegradedError(self, required="an implemented capability")
        return self

    def as_dict(self) -> dict[str, Any]:
        """Serialize the contract for JSON consumers."""

        return {
            "operation": self.operation.value,
            "status": self.state.value,
            "available": self.available,
            "degraded": self.degraded,
            "implemented": self.implemented,
            "provider": self.provider,
            "module_path": self.module_path,
            "reason": self.reason,
            "details": dict(self.details),
        }


def _capability_payload(value: Mapping[str, Any]) -> Mapping[str, Any]:
    """Locate the most specific capability contract in an adapter payload."""

    nested = value.get("capability")
    if isinstance(nested, Mapping):
        return nested

    metadata = value.get("metadata")
    if isinstance(metadata, Mapping):
        nested = metadata.get("capability")
        if isinstance(nested, Mapping):
            return nested
        details = metadata.get("details")
        if isinstance(details, Mapping):
            nested = details.get("capability")
            if isinstance(nested, Mapping):
                return nested
        return metadata

    details = value.get("details")
    if isinstance(details, Mapping):
        nested = details.get("capability")
        if isinstance(nested, Mapping):
            return nested
    return value


def capability_state_from_payload(
    payload: Mapping[str, Any] | None,
) -> Optional[LogicCapabilityState]:
    """Read a serialized capability state without leaking wire strings.

    New producers embed the complete capability contract.  The compatibility
    paths below keep persisted pre-contract review payloads readable while all
    branching remains centralized here instead of being repeated by callers.
    ``None`` means the payload contains no recognizable capability signal.
    """

    root: Mapping[str, Any] = payload if isinstance(payload, Mapping) else {}
    value = _capability_payload(root)
    raw_state = value.get("status") or value.get("implementation_status")
    if not raw_state and value is not root:
        raw_state = root.get("implementation_status") or root.get("status")
    normalized = str(raw_state or "").strip().lower()

    signals: list[LogicCapabilityState] = []
    try:
        if normalized:
            signals.append(LogicCapabilityState(normalized))
    except ValueError:
        # Compatibility for stored payloads created before the v1 contract.
        if normalized == "not_implemented":
            signals.append(
                LogicCapabilityState.DEGRADED
                if value.get("backend_available", root.get("backend_available")) is not False
                else LogicCapabilityState.UNAVAILABLE
            )
        elif normalized == "error":
            signals.append(LogicCapabilityState.DEGRADED)
        elif normalized in {"available", "success"}:
            signals.append(LogicCapabilityState.IMPLEMENTED)

    if value.get("implemented") is True or value.get("capability_implemented") is True:
        signals.append(LogicCapabilityState.IMPLEMENTED)
    if value.get("degraded") is True or value.get("capability_degraded") is True:
        signals.append(LogicCapabilityState.DEGRADED)
    if value.get("available") is False or value.get("capability_available") is False:
        signals.append(LogicCapabilityState.UNAVAILABLE)
    if not normalized and value.get("backend_available") is False:
        signals.append(LogicCapabilityState.UNAVAILABLE)

    if not signals:
        return None

    # Persisted payloads can contain stale duplicate flags.  Select the least
    # capable recognized signal so authoritative validation never proceeds
    # because one optimistic field disagrees with the rest of the contract.
    precedence = {
        LogicCapabilityState.UNAVAILABLE: 0,
        LogicCapabilityState.DEGRADED: 1,
        LogicCapabilityState.IMPLEMENTED: 2,
    }
    return min(signals, key=precedence.__getitem__)


class CanonicalCompilerSupport(str, Enum):
    """Why a canonical-compiler capability is or is not implemented.

    This scope is intentionally separate from ``FormalLogicOperation``. The
    five-operation inventory stays stable, and importing the compiler module
    is not itself a supported execution.
    """

    MISSING_MODULE = "missing_module"
    NOT_EXECUTED = "not_executed"
    EXECUTED = "executed"
    UNSUPPORTED = "unsupported"
    PARTIAL = "partial"
    SCHEMA_MISMATCH = "schema_mismatch"
    FAILED = "failed"
    TAMPERED = "tampered"


CANONICAL_COMPILER_CAPABILITY_SCHEMA = "canonical-compiler-capability/v1"


@dataclass(frozen=True)
class CanonicalCompilerCapability:
    """Typed gate for the canonical compiler adapter.

    ``implemented`` is true only for a completed supported execution whose
    source map was validated and whose emitted formulas were traced. A module
    import, an abstention, a partial projection, a schema mismatch, or a
    tampered receipt cannot satisfy that gate.
    """

    state: LogicCapabilityState
    support: CanonicalCompilerSupport
    provider: str
    module_path: str
    reason: str | None = None
    schema_version: str = CANONICAL_COMPILER_CAPABILITY_SCHEMA
    compiler_interface: str = ""
    compiler_config_cid: str = ""
    policy_cid: str = ""
    pipeline_interface: str = ""
    pipeline_cid: str = ""
    stage_ids: tuple[str, ...] = ()
    executed: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.state, LogicCapabilityState):
            object.__setattr__(self, "state", LogicCapabilityState(str(self.state)))
        if not isinstance(self.support, CanonicalCompilerSupport):
            object.__setattr__(
                self, "support", CanonicalCompilerSupport(str(self.support))
            )
        object.__setattr__(self, "provider", str(self.provider or "").strip())
        object.__setattr__(self, "module_path", str(self.module_path or "").strip())
        normalized_reason = str(self.reason or "").strip() or None
        object.__setattr__(self, "reason", normalized_reason)
        object.__setattr__(self, "stage_ids", tuple(str(item) for item in self.stage_ids))
        object.__setattr__(self, "executed", bool(self.executed))
        object.__setattr__(self, "details", MappingProxyType(dict(self.details or {})))
        if self.state is LogicCapabilityState.IMPLEMENTED:
            if not self.executed or self.support is not CanonicalCompilerSupport.EXECUTED:
                raise ValueError(
                    "Implemented canonical compiler capability requires an executed "
                    "supported operation"
                )
            if normalized_reason:
                raise ValueError("Implemented canonical compiler capability cannot carry a reason")
        elif not normalized_reason:
            raise ValueError("Unavailable and degraded canonical capabilities require a reason")

    @property
    def available(self) -> bool:
        return self.state.available

    @property
    def degraded(self) -> bool:
        return self.state is LogicCapabilityState.DEGRADED

    @property
    def implemented(self) -> bool:
        return self.state.implemented

    def require_implemented(self) -> "CanonicalCompilerCapability":
        if self.state is LogicCapabilityState.UNAVAILABLE:
            raise FormalLogicUnavailableError(
                _canonical_gate_capability(self),
                required="an implemented canonical compiler execution",
            )
        if self.state is not LogicCapabilityState.IMPLEMENTED:
            raise FormalLogicDegradedError(
                _canonical_gate_capability(self),
                required="an implemented canonical compiler execution",
            )
        return self

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operation": "compile_canonical_legal_ir",
            "status": self.state.value,
            "support": self.support.value,
            "available": self.available,
            "degraded": self.degraded,
            "implemented": self.implemented,
            "executed": self.executed,
            "provider": self.provider,
            "module_path": self.module_path,
            "reason": self.reason,
            "compiler_interface": self.compiler_interface,
            "compiler_config_cid": self.compiler_config_cid,
            "policy_cid": self.policy_cid,
            "pipeline_interface": self.pipeline_interface,
            "pipeline_cid": self.pipeline_cid,
            "stage_ids": list(self.stage_ids),
            "details": dict(self.details),
        }


def _canonical_gate_capability(capability: CanonicalCompilerCapability) -> FormalLogicCapability:
    """Adapt the separate canonical gate onto the existing error contract.

    The operation value stays ``run_hybrid_reasoning`` only as the error
    object's required enum. Callers read ``capability.operation`` from the
    canonical payload (``compile_canonical_legal_ir``), not from this bridge.
    """

    return FormalLogicCapability(
        operation=FormalLogicOperation.RUN_HYBRID_REASONING,
        state=capability.state,
        provider=capability.provider,
        module_path=capability.module_path,
        reason=capability.reason,
        details={"canonical_support": capability.support.value},
    )


def classify_canonical_compiler_capability(
    evidence: Mapping[str, Any] | None,
) -> CanonicalCompilerCapability:
    """Classify canonical compiler support from execution evidence.

    Missing evidence, or evidence that only records a module import, is never
    implemented. Supported execution requires a successful compile, a valid
    non-empty source map, traceability of every emitted id, and identity
    agreement across schema, compiler, policy, pipeline, and stages.
    """

    payload: Mapping[str, Any] = evidence if isinstance(evidence, Mapping) else {}
    module_present = bool(payload.get("module_present"))
    identities = payload.get("identities") if isinstance(payload.get("identities"), Mapping) else {}
    common = {
        "provider": str(payload.get("provider") or "ipfs_datasets_py"),
        "module_path": str(
            payload.get("module_path")
            or "ipfs_datasets_py.logic.integration.reasoning.legal_ir_canonical_pipeline"
        ),
        "compiler_interface": str(identities.get("compiler_interface") or ""),
        "compiler_config_cid": str(identities.get("compiler_config_cid") or ""),
        "policy_cid": str(identities.get("policy_cid") or ""),
        "pipeline_interface": str(identities.get("pipeline_interface") or ""),
        "pipeline_cid": str(identities.get("pipeline_cid") or ""),
        "stage_ids": tuple(identities.get("stage_ids") or ()),
        "details": {
            "source_map_schema": str(identities.get("source_map_schema") or ""),
            "executed_status": str(payload.get("status") or ""),
        },
    }
    if not module_present:
        return CanonicalCompilerCapability(
            state=LogicCapabilityState.UNAVAILABLE,
            support=CanonicalCompilerSupport.MISSING_MODULE,
            reason=str(payload.get("reason") or "Canonical compiler module is unavailable."),
            **common,
        )
    if payload.get("schema_match") is False:
        return CanonicalCompilerCapability(
            state=LogicCapabilityState.DEGRADED,
            support=CanonicalCompilerSupport.SCHEMA_MISMATCH,
            reason=str(payload.get("reason") or "Canonical schema or compiler identity mismatch."),
            executed=False,
            **common,
        )
    if payload.get("tampered") is True:
        return CanonicalCompilerCapability(
            state=LogicCapabilityState.DEGRADED,
            support=CanonicalCompilerSupport.TAMPERED,
            reason=str(payload.get("reason") or "Canonical formalization receipt failed integrity checks."),
            executed=False,
            **common,
        )
    executed = bool(payload.get("executed"))
    status = str(payload.get("status") or "").strip().lower()
    if not executed:
        return CanonicalCompilerCapability(
            state=LogicCapabilityState.DEGRADED,
            support=CanonicalCompilerSupport.NOT_EXECUTED,
            reason=str(
                payload.get("reason")
                or "Canonical compiler module import is not a supported execution."
            ),
            executed=False,
            **common,
        )
    traceable = bool(payload.get("traceable"))
    source_map_valid = bool(payload.get("source_map_valid"))
    if status == "success" and traceable and source_map_valid:
        return CanonicalCompilerCapability(
            state=LogicCapabilityState.IMPLEMENTED,
            support=CanonicalCompilerSupport.EXECUTED,
            reason=None,
            executed=True,
            **common,
        )
    if status == "partial":
        support = CanonicalCompilerSupport.PARTIAL
        reason = "Canonical compile was only partially supported."
    elif status in {"abstained", "unsupported"}:
        support = CanonicalCompilerSupport.UNSUPPORTED
        reason = "Canonical compile abstained on unsupported semantics."
    else:
        support = CanonicalCompilerSupport.FAILED
        reason = "Canonical compile did not complete a supported traced execution."
    return CanonicalCompilerCapability(
        state=LogicCapabilityState.DEGRADED,
        support=support,
        reason=str(payload.get("reason") or reason),
        executed=True,
        **common,
    )


__all__ = [
    "CANONICAL_COMPILER_CAPABILITY_SCHEMA",
    "CanonicalCompilerCapability",
    "CanonicalCompilerSupport",
    "FormalLogicCapability",
    "FormalLogicCapabilityError",
    "FormalLogicDegradedError",
    "FormalLogicOperation",
    "FormalLogicUnavailableError",
    "LogicCapabilityState",
    "LogicCapabilityStatus",
    "capability_state_from_payload",
    "classify_canonical_compiler_capability",
]
