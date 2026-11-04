"""Host-owned execution context for legal and evidence hook operations.

The context is a value and a validation seam. It records the operation,
owner, case, session, graph revision, legal-context identity, consent,
purpose, and deadline. It does not search for law, publish evidence, or
call a provider. Legacy intake and hook callers stay on their existing
paths unless they opt into this context.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional, Sequence


HOOK_CONTEXT_SCHEMA = "hook_execution_context_receipt_v1"

LEGAL_EVIDENCE_OPERATIONS = (
    "acquire_legal_sources",
    "ingest_private_evidence",
    "refresh_grounding",
)

_REMOTE_BLOCKS_THAT_STILL_ALLOW_CONTEXT = frozenset({
    "privacy_denied:cloud_processing_disabled",
    "privacy_denied:grok_scope_mismatch",
})

_SECRET_FIELD_NAMES = frozenset({
    "key",
    "keys",
    "api_key",
    "passphrase",
    "secret",
    "private_key",
    "token",
    "password",
})


class HookContextError(ValueError):
    """Structural refusal raised before a context exists."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class HookExecutionContext:
    """Private host record. Public callers use :meth:`public_receipt`."""

    operation_id: str
    operation: str
    owner_id: str
    case_id: str
    session_id: str
    session_revision: int
    graph_revision: str
    legal_context_id: str
    consent_status: str
    purpose: str
    deadline: datetime
    source_binding_hash: str
    context_binding_hash: str
    source_count: int
    provider_call_allowed: bool

    def public_receipt(self) -> dict[str, Any]:
        return {
            "schema": HOOK_CONTEXT_SCHEMA,
            "operation_id": self.operation_id,
            "operation": self.operation,
            "owner_id": self.owner_id,
            "case_id": self.case_id,
            "session_id": self.session_id,
            "session_revision": self.session_revision,
            "graph_revision": self.graph_revision,
            "legal_context_id": self.legal_context_id,
            "consent_status": self.consent_status,
            "purpose_hash": _sha256_text(self.purpose),
            "deadline": self.deadline.isoformat(),
            "source_binding_hash": self.source_binding_hash,
            "context_binding_hash": self.context_binding_hash,
            "source_count": self.source_count,
        }


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_hash(payload: Any, *, prefix: str) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return prefix + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _require_token(value: Any, *, code: str, max_length: int = 128) -> str:
    if type(value) is not str:
        raise HookContextError(code)
    token = value.strip()
    if not token or len(token) > max_length:
        raise HookContextError(code)
    if any(ord(char) < 32 for char in token):
        raise HookContextError(code)
    return token


def _context_revision(value: Any) -> int:
    if type(value) is bool or value in (None, ""):
        return 0
    if type(value) is not int:
        raise HookContextError("legal_context_missing")
    if value < 0:
        raise HookContextError("legal_context_missing")
    return value


def _date_token(value: Any) -> str:
    if isinstance(value, Mapping):
        return "|".join((
            str(value.get("role") or ""),
            str(value.get("raw_text") or ""),
            str(value.get("start_date") or ""),
            str(value.get("end_date") or ""),
            str(bool(value.get("is_uncertain"))),
        ))
    return str(value or "")


def legal_context_identity(legal_context: Mapping[str, Any] | None) -> str:
    """Opaque identity of the explicit legal context, without question text."""

    if not isinstance(legal_context, Mapping):
        raise HookContextError("legal_context_missing")
    payload = {
        "status": str(legal_context.get("status") or ""),
        "jurisdiction": str(legal_context.get("jurisdiction") or ""),
        "jurisdiction_explicit": bool(legal_context.get("jurisdiction_explicit")),
        "context_revision": _context_revision(legal_context.get("context_revision")),
        "applicable_law_date": _date_token(legal_context.get("applicable_law_date")),
        "event_date": _date_token(legal_context.get("event_date")),
        "filing_reference_date": _date_token(legal_context.get("filing_reference_date")),
        "corpus_retrieval_date": _date_token(legal_context.get("corpus_retrieval_date")),
    }
    return _canonical_hash(payload, prefix="lc_")


def graph_revision_token(graph: Any) -> str:
    """Revision token from ledger indexes and event ids, not statement text."""

    ledger = graph.factual_ledger() if hasattr(graph, "factual_ledger") else {}
    revisions = ledger.get("revisions") if isinstance(ledger, Mapping) else ()
    material = []
    for record in revisions or ():
        if not isinstance(record, Mapping):
            continue
        material.append({
            "revision_index": int(record.get("revision_index") or 0),
            "event_id": str(record.get("event_id") or ""),
        })
    return _canonical_hash({"count": len(material), "revisions": material}, prefix="gr_")


def _reject_secret_fields(record: Mapping[str, Any]) -> None:
    for key in record:
        if str(key).strip().lower() in _SECRET_FIELD_NAMES:
            raise HookContextError("secret_material")


def normalize_source_bindings(source_bindings: Sequence[Mapping[str, Any]] | None) -> tuple[dict[str, str], ...]:
    """Keep source id and content hash. Drop raw passages and refuse keys."""

    if source_bindings is None:
        raise HookContextError("source_binding_missing")
    if isinstance(source_bindings, (str, bytes)) or not isinstance(source_bindings, Sequence):
        raise HookContextError("source_binding_missing")
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in source_bindings:
        if not isinstance(item, Mapping):
            raise HookContextError("source_binding_missing")
        _reject_secret_fields(item)
        source_id = _require_token(item.get("source_id"), code="source_binding_missing")
        content_hash = item.get("content_hash")
        if type(content_hash) is not str or len(content_hash) != 64:
            raise HookContextError("source_binding_missing")
        try:
            int(content_hash, 16)
        except ValueError as exc:
            raise HookContextError("source_binding_missing") from exc
        # A supplied passage is not retained. It cannot replace the hash.
        if "source_text" in item or "prompt" in item or "source_bytes" in item:
            passage = item.get("source_text")
            if type(passage) is str and passage and _sha256_text(passage) != content_hash:
                raise HookContextError("source_binding_mismatch")
        row = {"source_id": source_id, "content_hash": content_hash}
        identity = (row["source_id"], row["content_hash"])
        if identity in seen:
            raise HookContextError("source_binding_missing")
        seen.add(identity)
        rows.append(row)
    rows.sort(key=lambda row: (row["source_id"], row["content_hash"]))
    return tuple(rows)


def source_binding_hash(source_bindings: Sequence[Mapping[str, Any]] | None) -> str:
    rows = normalize_source_bindings(source_bindings)
    return _canonical_hash([dict(row) for row in rows], prefix="sb_")


def context_binding_hash(*, legal_context_id: str, owner_id: str, case_id: str, session_id: str) -> str:
    return _canonical_hash(
        {
            "legal_context_id": legal_context_id,
            "owner_id": owner_id,
            "case_id": case_id,
            "session_id": session_id,
        },
        prefix="cb_",
    )


def _parse_deadline(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif type(value) is str and value.strip():
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise HookContextError("invalid_deadline") from exc
    else:
        raise HookContextError("invalid_deadline")
    if parsed.tzinfo is None:
        raise HookContextError("invalid_deadline")
    return parsed.astimezone(timezone.utc)


def _consent_status(policy: Mapping[str, Any]) -> str:
    consent = policy.get("consent")
    if not isinstance(consent, Mapping):
        return ""
    return str(consent.get("status") or "")


def intake_consent_rejection(
    privacy_context: Mapping[str, Any] | None,
    *,
    owner_id: str,
    case_id: str,
) -> tuple[Optional[str], str, bool]:
    """Reuse the intake privacy-policy and remote-consent checks.

    A local consent that blocks cloud processing still authorizes this
    context seam, and records that a provider call is not allowed. A
    missing or malformed consent is rejected. The returned status is the
    consent code, never a prompt or key.
    """

    from integrations.ipfs_datasets.llm import _privacy_context_block_reason, inspect_privacy_policy

    if not isinstance(privacy_context, Mapping):
        return "consent_missing", "", False
    if str(privacy_context.get("user_id") or "") != owner_id or str(privacy_context.get("case_id") or "") != case_id:
        return "wrong_case", "", False
    inspection = inspect_privacy_policy(privacy_context.get("policy"), user_id=owner_id, case_id=case_id)
    if not inspection.get("admitted"):
        reason = str(inspection.get("reason") or "consent_missing")
        if reason == "legacy_missing":
            reason = "consent_missing"
        return reason, "", False
    policy = inspection.get("policy") if isinstance(inspection.get("policy"), Mapping) else {}
    status = _consent_status(policy)
    if not status:
        return "consent_missing", "", False
    block = _privacy_context_block_reason(privacy_context, provider="grok_cli", model_name="grok-4.7")
    if block in _REMOTE_BLOCKS_THAT_STILL_ALLOW_CONTEXT:
        return None, status, False
    if block:
        return str(block), status, False
    return None, status, True


def intake_session_revision_rejection(host: Any, expected: int) -> Optional[str]:
    """Same session-revision comparison the intake router uses before dispatch."""

    workflow = getattr(host, "workflow_actions", None)
    meta = getattr(workflow, "_interview_meta", None) if workflow is not None else None
    if not isinstance(meta, dict) or "session_revision" not in meta:
        return None
    if int(meta.get("session_revision") or 0) != int(expected):
        return "stale_request"
    return None


def intake_action_rejection(
    host: Any,
    *,
    owner_id: str,
    case_id: str,
    session_id: str,
    session_revision: int,
) -> Optional[str]:
    """When an intake action is already bound, the hook must name that case."""

    action = getattr(host, "_intake_action", None)
    if action is None:
        return None
    try:
        bound_owner, bound_case, bound_session, bound_revision = action[1], action[2], action[3], int(action[4])
    except (TypeError, ValueError, IndexError):
        return "wrong_case"
    if bound_owner != owner_id or bound_case != case_id or bound_session != session_id:
        return "wrong_case"
    if bound_revision != int(session_revision):
        return "stale_request"
    return None


def bind_hook_execution_context(
    *,
    operation: str,
    owner_id: str,
    case_id: str,
    session_id: str,
    session_revision: int,
    graph_revision: str,
    legal_context: Mapping[str, Any],
    purpose: str,
    deadline: Any,
    source_bindings: Sequence[Mapping[str, Any]],
    privacy_context: Mapping[str, Any] | None,
    host: Any = None,
) -> HookExecutionContext:
    """Mint a host operation id and freeze the current case bindings."""

    if type(operation) is not str or operation not in LEGAL_EVIDENCE_OPERATIONS:
        raise HookContextError("unsupported_operation")
    owner = _require_token(owner_id, code="wrong_case")
    case = _require_token(case_id, code="wrong_case")
    session = _require_token(session_id, code="wrong_case")
    if type(session_revision) is not int or session_revision < 0:
        raise HookContextError("stale_request")
    revision = _require_token(graph_revision, code="stale_revision", max_length=80)
    if type(purpose) is not str or not purpose.strip():
        raise HookContextError("missing_purpose")
    purpose_text = purpose.strip()
    if len(purpose_text) > 200:
        raise HookContextError("missing_purpose")
    legal_id = legal_context_identity(legal_context)
    rows = normalize_source_bindings(source_bindings)
    consent_code, consent_status, provider_allowed = intake_consent_rejection(
        privacy_context, owner_id=owner, case_id=case,
    )
    if consent_code:
        raise HookContextError(consent_code)
    if host is not None:
        revision_code = intake_session_revision_rejection(host, session_revision)
        if revision_code:
            raise HookContextError(revision_code)
        action_code = intake_action_rejection(
            host, owner_id=owner, case_id=case, session_id=session, session_revision=session_revision,
        )
        if action_code:
            raise HookContextError(action_code)
    return HookExecutionContext(
        operation_id=uuid.uuid4().hex,
        operation=operation,
        owner_id=owner,
        case_id=case,
        session_id=session,
        session_revision=session_revision,
        graph_revision=revision,
        legal_context_id=legal_id,
        consent_status=consent_status,
        purpose=purpose_text,
        deadline=_parse_deadline(deadline),
        source_binding_hash=source_binding_hash(rows),
        context_binding_hash=context_binding_hash(
            legal_context_id=legal_id, owner_id=owner, case_id=case, session_id=session,
        ),
        source_count=len(rows),
        provider_call_allowed=provider_allowed,
    )


def _decision(
    *,
    authorized: bool,
    code: str,
    context: HookExecutionContext | None,
    effect_invoked: bool = False,
) -> dict[str, Any]:
    receipt = context.public_receipt() if context is not None and authorized else (
        context.public_receipt() if context is not None and code not in {"binding_missing"} else None
    )
    # Refusals still expose the opaque receipt when the host context exists,
    # so a caller can correlate the denial without receiving private fields.
    if context is not None and receipt is None and code != "binding_missing":
        receipt = context.public_receipt()
    return {
        "authorized": authorized,
        "code": code,
        "effect_invoked": effect_invoked,
        "effect_dispatched": False,
        "provider_invoked": False,
        "provider_call_allowed": bool(context and context.provider_call_allowed and authorized),
        "receipt": receipt,
    }


def authorize_hook_execution(
    context: HookExecutionContext | None,
    *,
    owner_id: str,
    case_id: str,
    session_id: str,
    session_revision: int,
    graph_revision: str,
    legal_context: Mapping[str, Any] | None,
    purpose: Any,
    source_bindings: Sequence[Mapping[str, Any]] | None,
    privacy_context: Mapping[str, Any] | None,
    now: datetime,
    host: Any = None,
    storage_available: bool = True,
    request_state: str = "active",
    effect: Optional[Callable[[Mapping[str, Any]], Any]] = None,
) -> dict[str, Any]:
    """Reject a drifted case before invoking an effect.

    A passed effect runs only after every check succeeds. This module does
    not supply a legal-search, publication, or provider effect.
    """

    if not isinstance(context, HookExecutionContext):
        return _decision(authorized=False, code="binding_missing", context=None)
    if type(purpose) is not str or not purpose.strip():
        return _decision(authorized=False, code="missing_purpose", context=context)
    if purpose.strip() != context.purpose:
        return _decision(authorized=False, code="purpose_mismatch", context=context)
    if (
        type(owner_id) is not str or owner_id.strip() != context.owner_id
        or type(case_id) is not str or case_id.strip() != context.case_id
        or type(session_id) is not str or session_id.strip() != context.session_id
    ):
        return _decision(authorized=False, code="wrong_case", context=context)
    if type(session_revision) is not int or session_revision != context.session_revision:
        return _decision(authorized=False, code="stale_request", context=context)
    if host is not None:
        revision_code = intake_session_revision_rejection(host, context.session_revision)
        if revision_code:
            return _decision(authorized=False, code=revision_code, context=context)
        action_code = intake_action_rejection(
            host,
            owner_id=context.owner_id,
            case_id=context.case_id,
            session_id=context.session_id,
            session_revision=context.session_revision,
        )
        if action_code:
            return _decision(authorized=False, code=action_code, context=context)
    if type(graph_revision) is not str or graph_revision.strip() != context.graph_revision:
        return _decision(authorized=False, code="stale_revision", context=context)
    try:
        current_sources = source_binding_hash(source_bindings)
        current_legal_id = legal_context_identity(legal_context)
    except HookContextError as exc:
        return _decision(authorized=False, code=exc.code, context=context)
    if current_sources != context.source_binding_hash:
        return _decision(authorized=False, code="source_binding_changed", context=context)
    current_context_binding = context_binding_hash(
        legal_context_id=current_legal_id,
        owner_id=context.owner_id,
        case_id=context.case_id,
        session_id=context.session_id,
    )
    if current_legal_id != context.legal_context_id or current_context_binding != context.context_binding_hash:
        return _decision(authorized=False, code="context_binding_changed", context=context)
    consent_code, _status, _provider_allowed = intake_consent_rejection(
        privacy_context, owner_id=context.owner_id, case_id=context.case_id,
    )
    if consent_code:
        return _decision(authorized=False, code=consent_code, context=context)
    if str(request_state or "") == "cancelled":
        return _decision(authorized=False, code="cancelled", context=context)
    if storage_available is False:
        return _decision(authorized=False, code="storage_unavailable", context=context)
    if not isinstance(now, datetime) or now.tzinfo is None:
        return _decision(authorized=False, code="invalid_deadline", context=context)
    if now.astimezone(timezone.utc) > context.deadline:
        return _decision(authorized=False, code="deadline_elapsed", context=context)
    receipt = context.public_receipt()
    effect_invoked = False
    if effect is not None:
        effect(receipt)
        effect_invoked = True
    decision = _decision(authorized=True, code="context_authorized", context=context, effect_invoked=effect_invoked)
    decision["effect_dispatched"] = False
    decision["provider_invoked"] = False
    return decision


# Declared hook purposes. Model purposes are proposals only: they cannot call
# tools or mark a legal requirement satisfied. Local purposes never dispatch.
MODEL_PURPOSE_IDS = frozenset({"extract_facts", "propose_questions", "explain_candidate"})
LOCAL_ONLY_PURPOSE_IDS = frozenset({"local_extraction", "citation_acquisition", "source_graph_check"})
_PURPOSE_INPUT_LIMIT = 8192
_EXPLANATION_LIMIT = 500
_TOOL_KEYS = frozenset({"tools", "tool_calls", "grok_tools", "invoke_tool", "tool"})
_SATISFACTION_KEYS = frozenset({"requirements_satisfied", "requirement_satisfied", "satisfied_requirements"})


def is_local_only_purpose(purpose_id: Any) -> bool:
    return type(purpose_id) is str and purpose_id in LOCAL_ONLY_PURPOSE_IDS


def is_model_purpose(purpose_id: Any) -> bool:
    return type(purpose_id) is str and purpose_id in MODEL_PURPOSE_IDS


def _purpose_ref_pattern():
    import re
    return re.compile(r"^[A-Za-z0-9_.:-]{1,128}\Z")


def _pinned_route() -> dict[str, Any]:
    from integrations.ipfs_datasets.llm import pinned_hook_inference_route

    return pinned_hook_inference_route()


def inference_purpose_catalog() -> tuple[dict[str, Any], ...]:
    """Bounded purpose declarations. The route pin is the same for every model purpose."""

    route = _pinned_route()
    shared = {
        "inference_owner": route["inference_owner"],
        "provider": route["provider"],
        "model": route["model"],
        "allow_local_fallback": False,
        "allow_cross_provider_fallback": False,
        "tools_allowed": False,
        "may_mark_requirements_satisfied": False,
        "max_input_bytes": _PURPOSE_INPUT_LIMIT,
    }
    return (
        {**shared, "purpose_id": "extract_facts", "dispatch": "model", "allowed_inputs": ("source_text", "target_ref"), "allowed_outputs": ("facts",), "max_output_items": 16},
        {**shared, "purpose_id": "propose_questions", "dispatch": "model", "allowed_inputs": ("gap_code", "target_ref"), "allowed_outputs": ("questions",), "max_output_items": 8},
        {**shared, "purpose_id": "explain_candidate", "dispatch": "model", "allowed_inputs": ("candidate_ref", "gap_code"), "allowed_outputs": ("candidate_ref", "explanation"), "max_output_items": 1},
        {"purpose_id": "local_extraction", "dispatch": "local", "model_dispatch": False, "allowed_inputs": ("source_text", "excerpt"), "allowed_outputs": ("source_start", "source_end", "excerpt"), "tools_allowed": False, "may_mark_requirements_satisfied": False, "max_input_bytes": _PURPOSE_INPUT_LIMIT},
        {"purpose_id": "citation_acquisition", "dispatch": "local", "model_dispatch": False, "allowed_inputs": ("citation", "authority_id"), "allowed_outputs": ("authority_id", "citation", "acquired_locally"), "tools_allowed": False, "may_mark_requirements_satisfied": False, "max_input_bytes": _PURPOSE_INPUT_LIMIT},
        {"purpose_id": "source_graph_check", "dispatch": "local", "model_dispatch": False, "allowed_inputs": ("graph_revision", "source_id", "expected_revision"), "allowed_outputs": ("consistent", "graph_revision", "source_id"), "tools_allowed": False, "may_mark_requirements_satisfied": False, "max_input_bytes": _PURPOSE_INPUT_LIMIT},
    )


def _scan_forbidden(value: Any, *, depth: int = 0) -> Optional[str]:
    if depth > 8:
        return "malformed"
    if isinstance(value, Mapping):
        for key, item in value.items():
            name = str(key)
            if name in _TOOL_KEYS:
                return "model_cannot_invoke_tools"
            if name in _SATISFACTION_KEYS:
                return "model_cannot_satisfy_requirements"
            found = _scan_forbidden(item, depth=depth + 1)
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        if len(value) > 64:
            return "malformed"
        for item in value:
            found = _scan_forbidden(item, depth=depth + 1)
            if found:
                return found
    return None


def _bounded_text(value: Any, *, limit: int) -> Optional[str]:
    if type(value) is not str:
        return None
    text = value.strip()
    if not text or len(text.encode("utf-8")) > limit:
        return None
    if any(ord(char) < 32 for char in text):
        return None
    return text


def _as_ref(value: Any) -> Optional[str]:
    text = _bounded_text(value, limit=128)
    if text is None or _purpose_ref_pattern().fullmatch(text) is None:
        return None
    return text


def _validate_purpose_inputs(purpose_id: str, inputs: Any) -> tuple[Optional[str], dict[str, Any]]:
    if not isinstance(inputs, Mapping):
        return "malformed", {}
    code = _scan_forbidden(inputs)
    if code:
        return code, {}
    try:
        encoded = json.dumps(inputs, sort_keys=True, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError):
        return "malformed", {}
    if len(encoded) > _PURPOSE_INPUT_LIMIT:
        return "input_bounds", {}
    if purpose_id == "extract_facts":
        if set(inputs) != {"source_text", "target_ref"}:
            return "input_bounds", {}
        source_text = _bounded_text(inputs.get("source_text"), limit=4096)
        target = _as_ref(inputs.get("target_ref"))
        if source_text is None or target is None:
            return "input_bounds", {}
        return None, {"source_text": source_text, "target_ref": target}
    if purpose_id == "propose_questions":
        if set(inputs) != {"gap_code", "target_ref"}:
            return "input_bounds", {}
        gap = _bounded_text(inputs.get("gap_code"), limit=128)
        target = _as_ref(inputs.get("target_ref"))
        if gap is None or target is None:
            return "input_bounds", {}
        return None, {"gap_code": gap, "target_ref": target}
    if purpose_id == "explain_candidate":
        if set(inputs) != {"candidate_ref", "gap_code"}:
            return "input_bounds", {}
        candidate = _as_ref(inputs.get("candidate_ref"))
        gap = _bounded_text(inputs.get("gap_code"), limit=128)
        if candidate is None or gap is None:
            return "input_bounds", {}
        return None, {"candidate_ref": candidate, "gap_code": gap}
    if purpose_id == "local_extraction":
        if set(inputs) != {"source_text", "excerpt"}:
            return "input_bounds", {}
        source_text = _bounded_text(inputs.get("source_text"), limit=4096)
        excerpt = _bounded_text(inputs.get("excerpt"), limit=500)
        if source_text is None or excerpt is None:
            return "input_bounds", {}
        return None, {"source_text": source_text, "excerpt": excerpt}
    if purpose_id == "citation_acquisition":
        if set(inputs) != {"citation", "authority_id"}:
            return "input_bounds", {}
        citation = _bounded_text(inputs.get("citation"), limit=160)
        authority = _as_ref(inputs.get("authority_id"))
        if citation is None or authority is None:
            return "input_bounds", {}
        return None, {"citation": citation, "authority_id": authority}
    if purpose_id == "source_graph_check":
        if set(inputs) != {"graph_revision", "source_id", "expected_revision"}:
            return "input_bounds", {}
        revision = _bounded_text(inputs.get("graph_revision"), limit=80)
        expected = _bounded_text(inputs.get("expected_revision"), limit=80)
        source_id = _as_ref(inputs.get("source_id"))
        if revision is None or expected is None or source_id is None:
            return "input_bounds", {}
        return None, {"graph_revision": revision, "source_id": source_id, "expected_revision": expected}
    return "undeclared_purpose", {}


def _validate_model_output(purpose_id: str, output: Any, inputs: Mapping[str, Any]) -> tuple[Optional[str], dict[str, Any]]:
    if not isinstance(output, Mapping):
        return "malformed", {}
    code = _scan_forbidden(output)
    if code:
        return code, {}
    from integrations.ipfs_datasets.llm import INTAKE_FACT_FIELDS

    if purpose_id == "extract_facts":
        if set(output) != {"facts"} or type(output.get("facts")) is not list:
            return "malformed", {}
        facts = output["facts"]
        if len(facts) > 16:
            return "malformed", {}
        clean = []
        for item in facts:
            if type(item) is not dict or set(item) != {"field", "value", "target_ref"}:
                return "malformed", {}
            field = item.get("field")
            value = _bounded_text(item.get("value"), limit=500)
            target = _as_ref(item.get("target_ref"))
            if type(field) is not str or field not in INTAKE_FACT_FIELDS or value is None or target is None:
                return "malformed", {}
            if target != inputs["target_ref"]:
                return "malformed", {}
            clean.append({"field": field, "value": value, "target_ref": target})
        return None, {"facts": clean}
    if purpose_id == "propose_questions":
        if set(output) != {"questions"} or type(output.get("questions")) is not list:
            return "malformed", {}
        questions = output["questions"]
        if len(questions) > 8:
            return "malformed", {}
        clean = []
        seen: set[str] = set()
        for item in questions:
            if type(item) is not dict or set(item) != {"question_id", "prompt", "target_ref"}:
                return "malformed", {}
            question_id = _as_ref(item.get("question_id"))
            prompt = _bounded_text(item.get("prompt"), limit=500)
            target = _as_ref(item.get("target_ref"))
            if question_id is None or prompt is None or target is None or target != inputs["target_ref"]:
                return "malformed", {}
            if question_id in seen:
                return "malformed", {}
            seen.add(question_id)
            clean.append({"question_id": question_id, "prompt": prompt, "target_ref": target})
        return None, {"questions": clean}
    if purpose_id == "explain_candidate":
        if set(output) != {"candidate_ref", "explanation"}:
            return "malformed", {}
        candidate = _as_ref(output.get("candidate_ref"))
        explanation = _bounded_text(output.get("explanation"), limit=_EXPLANATION_LIMIT)
        if candidate is None or explanation is None or candidate != inputs["candidate_ref"]:
            return "malformed", {}
        return None, {"candidate_ref": candidate, "explanation": explanation}
    return "undeclared_purpose", {}


def _run_local_purpose(purpose_id: str, inputs: Mapping[str, Any]) -> dict[str, Any]:
    if purpose_id == "local_extraction":
        source = inputs["source_text"].encode("utf-8")
        excerpt = inputs["excerpt"]
        start = inputs["source_text"].find(excerpt)
        if start < 0:
            return {"status": "not_found", "output": None}
        start_byte = len(inputs["source_text"][:start].encode("utf-8"))
        end_byte = start_byte + len(excerpt.encode("utf-8"))
        if source[start_byte:end_byte].decode("utf-8") != excerpt:
            return {"status": "not_found", "output": None}
        return {"status": "local_only", "output": {"source_start": start_byte, "source_end": end_byte, "excerpt": excerpt}}
    if purpose_id == "citation_acquisition":
        return {"status": "local_only", "output": {"authority_id": inputs["authority_id"], "citation": inputs["citation"], "acquired_locally": True}}
    consistent = inputs["graph_revision"] == inputs["expected_revision"]
    return {
        "status": "local_only",
        "output": {"consistent": consistent, "graph_revision": inputs["graph_revision"], "source_id": inputs["source_id"]},
    }


def _purpose_result(
    *,
    purpose_id: str,
    status: str,
    code: str,
    model_dispatched: bool,
    output: Any,
    identity: Optional[dict[str, Any]],
    route: Optional[dict[str, Any]],
    synthetic_transport_invoked: bool = False,
) -> dict[str, Any]:
    return {
        "purpose_id": purpose_id,
        "dispatch": "local" if status == "local_only" else ("model" if model_dispatched and status == "available" else "refused"),
        "status": status,
        "code": code,
        "model_dispatched": model_dispatched,
        "model_dispatch_count": 1 if model_dispatched else 0,
        "provider_invoked": False,
        "synthetic_transport_invoked": synthetic_transport_invoked,
        "requirements_satisfied": False,
        "requirements_satisfied_by_model": False,
        "tools_invoked": False,
        "tools_allowed": False,
        "output": output,
        "route": route or {},
        "identity": identity,
    }


def dispatch_declared_hook_purpose(
    context: HookExecutionContext | None,
    purpose_id: str,
    inputs: Mapping[str, Any] | None,
    *,
    owner_id: str,
    case_id: str,
    session_id: str,
    session_revision: int,
    graph_revision: str,
    legal_context: Mapping[str, Any] | None,
    source_bindings: Sequence[Mapping[str, Any]] | None,
    privacy_context: Mapping[str, Any] | None,
    now: datetime,
    host: Any = None,
    storage_available: bool = True,
    request_state: str = "active",
    model_transport: Optional[Callable[..., Any]] = None,
    requested_provider: Optional[str] = None,
    requested_model: Optional[str] = None,
    allow_local_fallback: bool = False,
    allow_cross_provider_fallback: bool = False,
) -> dict[str, Any]:
    """Run one declared purpose. Local work never calls the model transport.

    Injected transports are synthetic. This function does not verify a live
    Grok model or build identity.
    """

    from integrations.ipfs_datasets.llm import route_identity_diagnostics

    route = _pinned_route()
    if purpose_id not in MODEL_PURPOSE_IDS and purpose_id not in LOCAL_ONLY_PURPOSE_IDS:
        return _purpose_result(purpose_id=str(purpose_id), status="unavailable", code="undeclared_purpose", model_dispatched=False, output=None, identity=None, route=None)
    code, clean_inputs = _validate_purpose_inputs(purpose_id, inputs)
    if code:
        return _purpose_result(purpose_id=purpose_id, status="refused", code=code, model_dispatched=False, output=None, identity=None, route=route if is_model_purpose(purpose_id) else None)
    if not isinstance(context, HookExecutionContext) or context.purpose != purpose_id:
        return _purpose_result(purpose_id=purpose_id, status="refused", code="purpose_mismatch" if isinstance(context, HookExecutionContext) else "binding_missing", model_dispatched=False, output=None, identity=None, route=None)
    decision = authorize_hook_execution(
        context,
        owner_id=owner_id,
        case_id=case_id,
        session_id=session_id,
        session_revision=session_revision,
        graph_revision=graph_revision,
        legal_context=legal_context,
        purpose=purpose_id,
        source_bindings=source_bindings,
        privacy_context=privacy_context,
        now=now,
        host=host,
        storage_available=storage_available,
        request_state=request_state,
        effect=None,
    )
    if not decision["authorized"]:
        return _purpose_result(purpose_id=purpose_id, status="refused", code=str(decision["code"]), model_dispatched=False, output=None, identity=None, route=None)
    if is_local_only_purpose(purpose_id):
        if model_transport is not None:
            # Present but unused. Calling it would be an unnecessary model dispatch.
            pass
        local = _run_local_purpose(purpose_id, clean_inputs)
        return _purpose_result(
            purpose_id=purpose_id,
            status=str(local["status"]),
            code=str(local["status"]),
            model_dispatched=False,
            output=local["output"],
            identity=None,
            route=None,
        )
    requested = {
        "router": route["router"],
        "provider": requested_provider if requested_provider is not None else route["provider"],
        "model": requested_model if requested_model is not None else route["model"],
        "build": "",
    }
    if (
        requested["provider"] != route["provider"]
        or requested["model"] != route["model"]
        or requested["router"] != route["router"]
        or allow_local_fallback is not False
        or allow_cross_provider_fallback is not False
        or route["allow_local_fallback"] is not False
        or route["allow_cross_provider_fallback"] is not False
    ):
        identity = route_identity_diagnostics(
            requested=requested,
            selected={"router": "", "provider": "", "model": "", "build": ""},
            observed={"router": "", "provider": "", "model": "", "build": ""},
            transport_kind="synthetic",
        )
        return _purpose_result(purpose_id=purpose_id, status="refused", code="unpinned_route", model_dispatched=False, output=None, identity=identity, route=route)
    if decision.get("provider_call_allowed") is not True:
        return _purpose_result(purpose_id=purpose_id, status="refused", code="provider_not_allowed", model_dispatched=False, output=None, identity=None, route=route)
    selected = {"router": route["router"], "provider": route["provider"], "model": route["model"], "build": ""}
    if model_transport is None:
        identity = route_identity_diagnostics(requested=requested, selected=selected, observed={"router": "", "provider": "", "model": "", "build": ""}, transport_kind="synthetic")
        return _purpose_result(purpose_id=purpose_id, status="unavailable", code="model_transport_unavailable", model_dispatched=False, output=None, identity=identity, route=route)
    call = {
        "purpose_id": purpose_id,
        "inputs": clean_inputs,
        "router": route["router"],
        "provider": route["provider"],
        "model": route["model"],
        "allow_local_fallback": False,
        "allow_cross_provider_fallback": False,
        "tools_allowed": False,
        "grok_tools": "",
        "may_mark_requirements_satisfied": False,
    }
    request_id = uuid.uuid4().hex

    def finish_synthetic(result: dict[str, Any], identity: Mapping[str, Any] | None) -> dict[str, Any]:
        marked = dict(identity or {})
        marked["transport_kind"] = "synthetic"
        marked["native_observation_bound"] = False
        marked["synthetic_transport_invoked"] = True
        marked["live_model_identity_verified"] = False
        result["request_id"] = request_id
        result["provider_replayed"] = False
        result["live_model_identity_verified"] = False
        return _stamp_invocation_association(
            result,
            purpose=purpose_id,
            case_id=case_id,
            session_id=session_id,
            graph_revision=graph_revision,
            request_id=request_id,
            receipt=marked,
        )

    guard_key, guard_open = _dispatch_guard("declared", case_id, session_id, purpose_id, graph_revision)
    if not guard_open:
        replay = _purpose_result(purpose_id=purpose_id, status="refused", code="duplicate_dispatch", model_dispatched=False, output=None, identity=None, route=route)
        replay["provider_replayed"] = False
        replay["request_id"] = request_id
        return replay
    try:
        raw = model_transport(call)
    except Exception:
        identity = route_identity_diagnostics(requested=requested, selected=selected, observed={"router": "", "provider": "", "model": "", "build": ""}, transport_kind="synthetic")
        result = _purpose_result(purpose_id=purpose_id, status="unavailable", code="provider_exception", model_dispatched=True, output=None, identity=identity, route=route, synthetic_transport_invoked=True)
        result["dispatch"] = "refused"
        return finish_synthetic(result, identity)
    finally:
        _INFLIGHT_DISPATCHES.discard(guard_key)
    if not isinstance(raw, Mapping):
        identity = route_identity_diagnostics(requested=requested, selected=selected, observed={"router": "", "provider": "", "model": "", "build": ""}, transport_kind="synthetic")
        result = _purpose_result(purpose_id=purpose_id, status="unavailable", code="malformed", model_dispatched=True, output=None, identity=identity, route=route, synthetic_transport_invoked=True)
        result["dispatch"] = "refused"
        return finish_synthetic(result, identity)
    observed = {
        "router": raw.get("observed_router", ""),
        "provider": raw.get("observed_provider", ""),
        "model": raw.get("observed_model", ""),
        "build": raw.get("observed_build", ""),
    }
    identity = route_identity_diagnostics(
        requested=requested,
        selected=selected,
        observed=observed,
        transport_kind="synthetic",
        native_observation_bound=False,
        evidence_class=str(raw.get("evidence_class") or ""),
    )
    identity["native_observation_bound"] = False
    identity["evidence_class"] = "synthetic"
    transport_status = raw.get("status")
    if transport_status != "available":
        code_text = transport_status if type(transport_status) is str and transport_status else "unavailable"
        result = _purpose_result(purpose_id=purpose_id, status="unavailable", code=code_text, model_dispatched=True, output=None, identity=identity, route=route, synthetic_transport_invoked=True)
        result["dispatch"] = "refused"
        return finish_synthetic(result, identity)
    out_code, clean_output = _validate_model_output(purpose_id, raw.get("output"), clean_inputs)
    if out_code:
        result = _purpose_result(purpose_id=purpose_id, status="refused", code=out_code, model_dispatched=True, output=None, identity=identity, route=route, synthetic_transport_invoked=True)
        result["dispatch"] = "refused"
        return finish_synthetic(result, identity)
    result = _purpose_result(purpose_id=purpose_id, status="available", code="proposal_accepted", model_dispatched=True, output=clean_output, identity=identity, route=route, synthetic_transport_invoked=True)
    result["dispatch"] = "model"
    return finish_synthetic(result, identity)


def _pending_revision_token(pending_case: Any, graph_revision: str) -> str:
    if isinstance(pending_case, Mapping) and type(pending_case.get("revision")) is str:
        return pending_case["revision"]
    return graph_revision if type(graph_revision) is str else ""


INVOCATION_ASSOCIATION_SCHEMA = "invocation_association_v1"
_ASSOCIATION_PURPOSES = MODEL_PURPOSE_IDS | LOCAL_ONLY_PURPOSE_IDS
_ROUTER_RECEIPT_PUBLIC_KEYS = (
    "kind", "purpose_id", "status", "code", "request_id", "pending_revision",
    "accepted", "session_retained", "session_id", "router", "requested_router",
    "selected_router", "requested_provider", "selected_provider", "requested_model",
    "selected_model", "route_observation", "provider_supported_identity",
    "error_code", "prompt_logged", "intake_complete", "live_canary",
    "live_model_identity_verified", "live_build_identity_verified", "transport_kind",
    "observed_provider", "observed_model", "observed_build", "native_invocation_id",
    "native_observation_bound", "evidence_class", "invocation_label", "tools_allowed",
    "tools_invoked", "allow_local_fallback", "allow_cross_provider_fallback",
)
_INFLIGHT_DISPATCHES: set[tuple[str, str, str, str, str]] = set()


def _bounded_association_token(value: Any, limit: int) -> str:
    if type(value) is not str:
        return ""
    text = value.strip()
    if not text or len(text) > limit or any(ord(char) < 32 for char in text):
        return ""
    return text


def invocation_label_for_receipt(receipt: Mapping[str, Any] | None) -> str:
    """Label a receipt real only when the native observation seam bound it.

    Synthetic transports, unbound fake observation types, and receipts with no
    invocation stay fake. The label is not a live Grok identity claim.
    """

    if not isinstance(receipt, Mapping):
        return "fake"
    transport = receipt.get("transport_kind")
    observation = receipt.get("route_observation")
    evidence = receipt.get("evidence_class")
    if transport == "synthetic" or observation == "synthetic" or receipt.get("synthetic_transport_invoked") is True:
        return "fake"
    if type(evidence) is str and evidence.startswith("synthetic"):
        return "fake"
    if receipt.get("native_observation_bound") is False:
        return "fake"
    if receipt.get("native_observation_bound") is True and transport == "native_observation":
        return "real"
    if observation in {"not_dispatched", "", None} and not receipt.get("native_invocation_id"):
        return "fake"
    return "fake"


def invocation_association(
    *,
    invocation_label: str,
    purpose: Any,
    request_id: Any,
    case_id: Any,
    session_id: Any,
    accepted_graph_revision: Any,
    live_model_identity_verified: bool = False,
) -> dict[str, Any]:
    """Public association. Prompts, passages, keys, environments, and tool arguments are omitted."""

    label = invocation_label if invocation_label in {"real", "fake"} else "fake"
    purpose_text = _bounded_association_token(purpose, 64)
    if purpose_text not in _ASSOCIATION_PURPOSES:
        purpose_text = ""
    request = _bounded_association_token(request_id, 32)
    if re.fullmatch(r"[0-9a-f]{32}", request) is None:
        request = ""
    live = live_model_identity_verified is True and label == "real"
    return {
        "schema": INVOCATION_ASSOCIATION_SCHEMA,
        "invocation_label": label,
        "purpose": purpose_text,
        "request_id": request,
        "case_id": _bounded_association_token(case_id, 80),
        "session_id": _bounded_association_token(session_id, 80),
        "accepted_graph_revision": _bounded_association_token(accepted_graph_revision, 80),
        "live_model_identity_verified": live,
        "prompt_logged": False,
        "provider_replayed": False,
    }


def sanitized_router_receipt(receipt: Mapping[str, Any] | None) -> dict[str, Any]:
    """Copy the public receipt fields and drop payloads."""

    if not isinstance(receipt, Mapping):
        return {"prompt_logged": False}
    safe: dict[str, Any] = {}
    for key in _ROUTER_RECEIPT_PUBLIC_KEYS:
        if key not in receipt:
            continue
        value = receipt[key]
        if type(value) is bool or (type(value) is int and not isinstance(value, bool) and abs(value) <= 10000):
            safe[key] = value
        elif type(value) is str:
            token = _bounded_association_token(value, 160)
            if token:
                safe[key] = token
    safe["prompt_logged"] = False
    return safe


def public_router_trace_entry(
    receipt: Mapping[str, Any] | None,
    *,
    purpose: Any,
    case_id: Any,
    session_id: Any,
    accepted_graph_revision: Any,
    interview_session_id: Any = "",
    interview_revision: Any = None,
) -> dict[str, Any] | None:
    """One bounded trace entry. A receipt without a request id is not an invocation."""

    public = sanitized_router_receipt(receipt)
    association = invocation_association(
        invocation_label=invocation_label_for_receipt(receipt),
        purpose=purpose if purpose else public.get("purpose_id"),
        request_id=public.get("request_id"),
        case_id=case_id,
        session_id=session_id,
        accepted_graph_revision=accepted_graph_revision,
        live_model_identity_verified=bool(public.get("live_model_identity_verified")) and invocation_label_for_receipt(receipt) == "real",
    )
    if not association["request_id"]:
        return None
    entry = {
        "router_receipt": public,
        "interview_session_id": _bounded_association_token(interview_session_id, 80),
        "interview_revision": interview_revision if type(interview_revision) is int and not isinstance(interview_revision, bool) and 0 <= interview_revision <= 100000 else 0,
        **association,
    }
    return entry


def merge_router_trace(
    previous: Mapping[str, Any] | None,
    entries: Sequence[Mapping[str, Any]] | None,
    *,
    diagnostics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Append associations once. This never calls a provider or invents a request."""

    prior = previous if isinstance(previous, Mapping) else {}
    stored: list[dict[str, Any]] = []
    known: set[str] = set()
    for item in prior.get("receipts") or []:
        if not isinstance(item, Mapping):
            continue
        request_id = item.get("request_id") or (item.get("router_receipt") or {}).get("request_id")
        if type(request_id) is not str or request_id in known:
            continue
        stored.append(dict(item))
        known.add(request_id)
    added = False
    for item in entries or []:
        if not isinstance(item, Mapping):
            continue
        request_id = item.get("request_id")
        if type(request_id) is not str or not request_id or request_id in known:
            continue
        stored.append({key: item[key] for key in item})
        known.add(request_id)
        added = True
    if diagnostics is not None and (added or not prior):
        public_diagnostics = sanitized_router_receipt(diagnostics)
        public_diagnostics["prompt_logged"] = False
    else:
        public_diagnostics = dict(prior.get("diagnostics") or {}) if isinstance(prior.get("diagnostics"), Mapping) else {}
        if not public_diagnostics and diagnostics is not None:
            public_diagnostics = sanitized_router_receipt(diagnostics)
            public_diagnostics["prompt_logged"] = False
    return {"diagnostics": public_diagnostics, "receipts": stored[-32:]}


def _stamp_invocation_association(
    result: dict[str, Any],
    *,
    purpose: str,
    case_id: str,
    session_id: str,
    graph_revision: str,
    request_id: str,
    receipt: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not (result.get("model_dispatched") or result.get("provider_invoked") or result.get("synthetic_transport_invoked")):
        return result
    label_source = dict(receipt or {})
    label_source.setdefault("transport_kind", (result.get("identity") or {}).get("transport_kind") if isinstance(result.get("identity"), Mapping) else "")
    label_source.setdefault("synthetic_transport_invoked", result.get("synthetic_transport_invoked"))
    association = invocation_association(
        invocation_label=invocation_label_for_receipt(label_source),
        purpose=purpose,
        request_id=request_id,
        case_id=case_id,
        session_id=session_id,
        accepted_graph_revision=graph_revision,
        live_model_identity_verified=bool(label_source.get("live_model_identity_verified")),
    )
    result["invocation_association"] = association
    if isinstance(result.get("receipt"), dict):
        result["receipt"]["invocation_label"] = association["invocation_label"]
        result["receipt"]["purpose_id"] = association["purpose"]
        result["receipt"]["native_observation_bound"] = label_source.get("native_observation_bound") is True
        result["receipt"]["evidence_class"] = _bounded_association_token(label_source.get("evidence_class"), 80)
    return result


def _dispatch_guard(kind: str, case_id: str, session_id: str, purpose_id: str, graph_revision: str) -> tuple[tuple[str, str, str, str, str], bool]:
    key = (kind, case_id, session_id, purpose_id, graph_revision)
    if key in _INFLIGHT_DISPATCHES:
        return key, False
    _INFLIGHT_DISPATCHES.add(key)
    return key, True


def _hook_observation_receipt(
    *,
    purpose_id: str,
    status: str,
    code: str,
    request_id: str,
    pending_revision: str,
    identity: Optional[dict[str, Any]],
    accepted: bool,
) -> dict[str, Any]:
    """Public failure/success receipt. It omits prompts, source text, and tool arguments."""

    observed = {}
    if isinstance(identity, Mapping) and isinstance(identity.get("observed"), Mapping):
        observed = identity["observed"]
    request_ok = type(request_id) is str and len(request_id) == 32
    return {
        "kind": "hook_observation_receipt",
        "purpose_id": purpose_id if purpose_id in MODEL_PURPOSE_IDS or purpose_id in LOCAL_ONLY_PURPOSE_IDS else "",
        "status": status,
        "code": code,
        "request_id": request_id if request_ok else "",
        "pending_revision": pending_revision[:80],
        "pending_revision_recoverable": True,
        "case_revision_mutated": False,
        "accepted": accepted,
        "session_retained": True,
        "tools_allowed": False,
        "tools_invoked": False,
        "allow_local_fallback": False,
        "allow_cross_provider_fallback": False,
        "prompt_logged": False,
        "live_canary": False,
        "live_model_identity_verified": bool(identity and identity.get("live_model_identity_verified") is True and accepted),
        "live_build_identity_verified": bool(identity and identity.get("live_build_identity_verified") is True and accepted),
        "transport_kind": str(identity.get("transport_kind") or "") if isinstance(identity, Mapping) else "",
        "observed_provider": str(observed.get("provider") or "")[:128],
        "observed_model": str(observed.get("model") or "")[:128],
        "observed_build": str(observed.get("build") or "")[:128],
        "native_observation_bound": bool(isinstance(identity, Mapping) and identity.get("native_observation_bound") is True),
        "evidence_class": _bounded_association_token(identity.get("evidence_class") if isinstance(identity, Mapping) else "", 80),
        "invocation_label": invocation_label_for_receipt(identity if isinstance(identity, Mapping) else None),
    }


def dispatch_observed_hook_purpose(
    context: HookExecutionContext | None,
    purpose_id: str,
    inputs: Mapping[str, Any] | None,
    *,
    owner_id: str,
    case_id: str,
    session_id: str,
    session_revision: int,
    graph_revision: str,
    legal_context: Mapping[str, Any] | None,
    source_bindings: Sequence[Mapping[str, Any]] | None,
    privacy_context: Mapping[str, Any] | None,
    now: datetime,
    host: Any = None,
    storage_available: bool = True,
    request_state: str = "active",
    consent_record: Mapping[str, Any] | None = None,
    pending_case: Any = None,
    revision_reader: Optional[Callable[[], Mapping[str, Any]]] = None,
    cancel_event: Any = None,
    timeout: float = 30.0,
    data_class: str = "raw_intake",
    provider_kind: str = "grok_inference",
    provider_source_references: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Dispatch a declared hook purpose through the Native observation seam.

    Injected synthetic transports stay on ``dispatch_declared_hook_purpose``.
    This path does not substitute another model, does not enable tools, and
    does not write the pending case. Timeout, cancellation, quota, and
    malformed output return a bounded receipt and leave that revision in place.
    """

    import json as _json
    import uuid as _uuid

    from integrations.ipfs_datasets.llm import (
        accept_late_remote_result,
        bind_remote_invocation,
        evaluate_remote_operation_consent,
        generate_observed_hook_purpose,
        route_identity_diagnostics,
    )

    route = _pinned_route()
    pending_revision = _pending_revision_token(pending_case, graph_revision)
    pending_before = _json.dumps(pending_case, sort_keys=True, default=str) if pending_case is not None else None

    def seal(result: dict[str, Any]) -> dict[str, Any]:
        if pending_before is not None:
            after = _json.dumps(pending_case, sort_keys=True, default=str)
            result["pending_revision_recoverable"] = after == pending_before
            result["case_revision_mutated"] = after != pending_before
        else:
            result["pending_revision_recoverable"] = True
            result["case_revision_mutated"] = False
        result["pending_revision"] = pending_revision
        result["requirements_satisfied"] = False
        result["requirements_satisfied_by_model"] = False
        result["tools_invoked"] = False
        result["tools_allowed"] = False
        result["live_canary"] = False
        if result.get("identity") is None or result["identity"].get("live_model_identity_verified") is not True:
            result["live_model_identity_verified"] = False
        else:
            result["live_model_identity_verified"] = True
        observed_receipt = result.get("receipt") if isinstance(result.get("receipt"), dict) else {}
        _stamp_invocation_association(
            result,
            purpose=purpose_id,
            case_id=case_id,
            session_id=session_id,
            graph_revision=graph_revision,
            request_id=str(result.get("request_id") or observed_receipt.get("request_id") or ""),
            receipt={
                **observed_receipt,
                "transport_kind": (result.get("identity") or {}).get("transport_kind") if isinstance(result.get("identity"), Mapping) else observed_receipt.get("transport_kind"),
                "native_observation_bound": (result.get("identity") or {}).get("native_observation_bound") if isinstance(result.get("identity"), Mapping) else False,
                "evidence_class": (result.get("identity") or {}).get("evidence_class") if isinstance(result.get("identity"), Mapping) else "",
                "live_model_identity_verified": result.get("live_model_identity_verified") is True,
                "synthetic_transport_invoked": result.get("synthetic_transport_invoked") is True,
            },
        )
        return result

    if purpose_id not in MODEL_PURPOSE_IDS and purpose_id not in LOCAL_ONLY_PURPOSE_IDS:
        refused = _purpose_result(purpose_id=str(purpose_id), status="unavailable", code="undeclared_purpose", model_dispatched=False, output=None, identity=None, route=None)
        refused["receipt"] = _hook_observation_receipt(purpose_id=str(purpose_id), status="unavailable", code="undeclared_purpose", request_id="", pending_revision=pending_revision, identity=None, accepted=False)
        return seal(refused)
    code, clean_inputs = _validate_purpose_inputs(purpose_id, inputs)
    if code:
        refused = _purpose_result(purpose_id=purpose_id, status="refused", code=code, model_dispatched=False, output=None, identity=None, route=route if is_model_purpose(purpose_id) else None)
        refused["receipt"] = _hook_observation_receipt(purpose_id=purpose_id, status="refused", code=code, request_id="", pending_revision=pending_revision, identity=None, accepted=False)
        return seal(refused)
    if not isinstance(context, HookExecutionContext) or context.purpose != purpose_id:
        mismatch = "purpose_mismatch" if isinstance(context, HookExecutionContext) else "binding_missing"
        refused = _purpose_result(purpose_id=purpose_id, status="refused", code=mismatch, model_dispatched=False, output=None, identity=None, route=None)
        refused["receipt"] = _hook_observation_receipt(purpose_id=purpose_id, status="refused", code=mismatch, request_id="", pending_revision=pending_revision, identity=None, accepted=False)
        return seal(refused)
    decision = authorize_hook_execution(
        context,
        owner_id=owner_id,
        case_id=case_id,
        session_id=session_id,
        session_revision=session_revision,
        graph_revision=graph_revision,
        legal_context=legal_context,
        purpose=purpose_id,
        source_bindings=source_bindings,
        privacy_context=privacy_context,
        now=now,
        host=host,
        storage_available=storage_available,
        request_state=request_state,
        effect=None,
    )
    if not decision["authorized"]:
        refused = _purpose_result(purpose_id=purpose_id, status="refused", code=str(decision["code"]), model_dispatched=False, output=None, identity=None, route=None)
        refused["receipt"] = _hook_observation_receipt(purpose_id=purpose_id, status="refused", code=str(decision["code"]), request_id="", pending_revision=pending_revision, identity=None, accepted=False)
        return seal(refused)
    if is_local_only_purpose(purpose_id):
        local = _run_local_purpose(purpose_id, clean_inputs)
        result = _purpose_result(purpose_id=purpose_id, status=str(local["status"]), code=str(local["status"]), model_dispatched=False, output=local["output"], identity=None, route=None)
        result["receipt"] = _hook_observation_receipt(purpose_id=purpose_id, status=str(local["status"]), code=str(local["status"]), request_id="", pending_revision=pending_revision, identity=None, accepted=False)
        return seal(result)
    if decision.get("provider_call_allowed") is not True:
        refused = _purpose_result(purpose_id=purpose_id, status="refused", code="provider_not_allowed", model_dispatched=False, output=None, identity=None, route=route)
        refused["receipt"] = _hook_observation_receipt(purpose_id=purpose_id, status="refused", code="provider_not_allowed", request_id="", pending_revision=pending_revision, identity=None, accepted=False)
        return seal(refused)
    consent = evaluate_remote_operation_consent(
        consent_record,
        user_id=owner_id,
        case_id=case_id,
        purpose=purpose_id,
        provider_kind=provider_kind,
        data_class=data_class,
        tools=False,
    )
    if consent["effectful_allowed"] is not True:
        refused = _purpose_result(purpose_id=purpose_id, status="refused", code=str(consent["code"]), model_dispatched=False, output=None, identity=None, route=route)
        refused["receipt"] = _hook_observation_receipt(purpose_id=purpose_id, status="refused", code=str(consent["code"]), request_id="", pending_revision=pending_revision, identity=None, accepted=False)
        return seal(refused)
    requested = {"router": route["router"], "provider": route["provider"], "model": route["model"], "build": ""}
    selected = dict(requested)
    request_id = _uuid.uuid4().hex
    guard_key, guard_open = _dispatch_guard("observed", case_id, session_id, purpose_id, graph_revision)
    if not guard_open:
        replay = _purpose_result(purpose_id=purpose_id, status="refused", code="duplicate_dispatch", model_dispatched=False, output=None, identity=None, route=route)
        replay["provider_replayed"] = False
        replay["request_id"] = request_id
        replay["receipt"] = _hook_observation_receipt(purpose_id=purpose_id, status="refused", code="duplicate_dispatch", request_id=request_id, pending_revision=pending_revision, identity=None, accepted=False)
        return seal(replay)
    invocation_id = bind_remote_invocation(
        user_id=owner_id,
        case_id=case_id,
        purpose=purpose_id,
        provider_kind=provider_kind,
        data_class=data_class,
        generation=int(consent["generation"]),
    )
    generation_inputs = dict(clean_inputs)
    if provider_source_references is not None:
        try:
            references = minimal_source_references(source_bindings)
            if tuple(dict(row) for row in provider_source_references) != references:
                raise HookContextError("source_binding_mismatch")
        except (HookContextError, TypeError, ValueError):
            _INFLIGHT_DISPATCHES.discard(guard_key)
            return seal(_purpose_result(purpose_id=purpose_id, status="refused", code="source_binding_mismatch",
                model_dispatched=False, output=None, identity=None, route=route))
        generation_inputs["source_references"] = [dict(row) for row in references]
    try:
        observed_call = generate_observed_hook_purpose(
            purpose_id=purpose_id,
            inputs=generation_inputs,
            request_id=request_id,
            timeout=timeout,
            cancel_event=cancel_event,
        )
    finally:
        _INFLIGHT_DISPATCHES.discard(guard_key)
    identity = route_identity_diagnostics(
        requested=requested,
        selected=selected,
        observed={
            "router": observed_call.get("observed_router") or "",
            "provider": observed_call.get("observed_provider") or "",
            "model": observed_call.get("observed_model") or "",
            "build": observed_call.get("observed_build") or "",
        },
        transport_kind="native_observation",
        native_observation_bound=observed_call.get("native_observation_bound") is True,
        evidence_class=str(observed_call.get("evidence_class") or ""),
    )
    # The diagnostics helper can mark a qualified Native class as live. A
    # loaded test double must not inherit that claim.
    if observed_call.get("live_model_identity_verified") is not True:
        identity["live_model_identity_verified"] = False
        identity["live_build_identity_verified"] = False
    identity["native_observation_bound"] = observed_call.get("native_observation_bound") is True
    identity["evidence_class"] = _bounded_association_token(observed_call.get("evidence_class"), 80)
    if identity["native_observation_bound"] is not True:
        identity["live_model_identity_verified"] = False
        identity["live_build_identity_verified"] = False
    failure = str(observed_call.get("code") or "unavailable")
    if failure != "available":
        status = "unavailable" if failure not in {"cancelled", "timeout", "quota", "malformed"} else failure
        if failure in {"substitution_refused", "route_unverified"}:
            status = "unavailable"
        result = _purpose_result(
            purpose_id=purpose_id,
            status=status if status != "malformed" else "refused",
            code=failure,
            model_dispatched=bool(observed_call.get("model_dispatched")),
            output=None,
            identity=identity,
            route=route,
        )
        result["dispatch"] = "refused"
        result["provider_invoked"] = bool(observed_call.get("model_dispatched"))
        result["synthetic_transport_invoked"] = False
        result["invocation_id"] = invocation_id
        result["request_id"] = request_id
        result["accepted"] = False
        result["receipt"] = _hook_observation_receipt(
            purpose_id=purpose_id, status=result["status"], code=failure, request_id=request_id,
            pending_revision=pending_revision, identity=identity, accepted=False,
        )
        return seal(result)

    def current_late() -> dict[str, Any]:
        if revision_reader is None:
            return {
                "graph_revision": graph_revision,
                "session_revision": session_revision,
                "record": consent_record,
            }
        state = revision_reader()
        if not isinstance(state, Mapping):
            return {"graph_revision": "", "session_revision": None, "record": None}
        return {
            "graph_revision": state.get("graph_revision"),
            "session_revision": state.get("session_revision"),
            "record": state.get("record", consent_record),
        }

    try:
        late_state = current_late()
    except Exception:
        # Authorization/session/key/source reproof failed after the observed
        # provider call. Refuse output without erasing the dispatch fact.
        result = _purpose_result(purpose_id=purpose_id, status="refused", code="late_revalidation_unavailable",
            model_dispatched=True, output=None, identity=identity, route=route)
        result.update(dispatch="refused", provider_invoked=True, synthetic_transport_invoked=False,
            invocation_id=invocation_id, request_id=request_id, accepted=False)
        result["receipt"] = _hook_observation_receipt(purpose_id=purpose_id, status="refused",
            code="late_revalidation_unavailable", request_id=request_id, pending_revision=pending_revision,
            identity=identity, accepted=False)
        return seal(result)
    late = accept_late_remote_result(
        late_state.get("record"),
        invocation_id=invocation_id,
        user_id=owner_id,
        case_id=case_id,
        bound_graph_revision=graph_revision,
        current_graph_revision=late_state.get("graph_revision") if type(late_state.get("graph_revision")) is str else "",
        bound_session_revision=session_revision,
        current_session_revision=late_state.get("session_revision") if type(late_state.get("session_revision")) is int else -1,
    )
    if late["accepted"] is not True:
        result = _purpose_result(
            purpose_id=purpose_id, status="refused", code=str(late["code"]),
            model_dispatched=True, output=None, identity=identity, route=route,
        )
        result["dispatch"] = "refused"
        result["provider_invoked"] = True
        result["synthetic_transport_invoked"] = False
        result["invocation_id"] = invocation_id
        result["request_id"] = request_id
        result["accepted"] = False
        result["receipt"] = _hook_observation_receipt(
            purpose_id=purpose_id, status="refused", code=str(late["code"]), request_id=request_id,
            pending_revision=pending_revision, identity=identity, accepted=False,
        )
        return seal(result)
    try:
        parsed = _json.loads(observed_call.get("output_text") or "")
    except (TypeError, ValueError):
        parsed = None
    out_code, clean_output = _validate_model_output(purpose_id, parsed, clean_inputs)
    if out_code:
        result = _purpose_result(
            purpose_id=purpose_id, status="refused", code="malformed" if out_code == "malformed" else out_code,
            model_dispatched=True, output=None, identity=identity, route=route,
        )
        result["dispatch"] = "refused"
        result["provider_invoked"] = True
        result["synthetic_transport_invoked"] = False
        result["accepted"] = False
        result["request_id"] = request_id
        result["invocation_id"] = invocation_id
        result["receipt"] = _hook_observation_receipt(
            purpose_id=purpose_id, status="refused", code=result["code"], request_id=request_id,
            pending_revision=pending_revision, identity=identity, accepted=False,
        )
        return seal(result)
    result = _purpose_result(
        purpose_id=purpose_id, status="available", code="proposal_accepted",
        model_dispatched=True, output=clean_output, identity=identity, route=route,
    )
    result["dispatch"] = "model"
    result["provider_invoked"] = True
    result["synthetic_transport_invoked"] = False
    result["accepted"] = True
    result["request_id"] = request_id
    result["invocation_id"] = invocation_id
    result["receipt"] = _hook_observation_receipt(
        purpose_id=purpose_id, status="available", code="proposal_accepted", request_id=request_id,
        pending_revision=pending_revision, identity=identity, accepted=True,
    )
    return seal(result)


# Operation contracts. Registration records owners and disabled handlers.
# It does not search, ingest, refresh, persist, or call a provider.
HOOK_OPERATION_REGISTRY_SCHEMA = "hook_operation_registry_v1"
HOOK_OPERATION_REQUEST_SCHEMA = "hook_operation_request_v1"
HOOK_OPERATION_RESULT_SCHEMA = "hook_operation_result_v1"

_EXTRACTION_QUESTION_ROLES = ("extract_facts", "propose_questions", "explain_candidate")
_SOURCE_REF_LIMIT = 8
_HANDLER_CALLS = {"count": 0}

_EFFECT_FIELD_CODES = {
    "tools": "model_cannot_invoke_tools",
    "tool": "model_cannot_invoke_tools",
    "tool_calls": "model_cannot_invoke_tools",
    "grok_tools": "model_cannot_invoke_tools",
    "invoke_tool": "model_cannot_invoke_tools",
    "destination": "model_cannot_supply_destination",
    "destinations": "model_cannot_supply_destination",
    "endpoint": "model_cannot_supply_destination",
    "url": "model_cannot_supply_destination",
    "file_path": "model_cannot_supply_path",
    "path": "model_cannot_supply_path",
    "paths": "model_cannot_supply_path",
    "output_path": "model_cannot_supply_path",
    "provider_command": "model_cannot_supply_provider_command",
    "command": "model_cannot_supply_provider_command",
    "shell": "model_cannot_supply_provider_command",
    "argv": "model_cannot_supply_provider_command",
    "requirements_satisfied": "model_cannot_satisfy_requirements",
    "requirement_satisfied": "model_cannot_satisfy_requirements",
    "satisfied_requirements": "model_cannot_satisfy_requirements",
    "satisfied_nodes": "model_cannot_satisfy_requirements",
    "node_edits": "model_cannot_satisfy_requirements",
    "satisfied_node_edits": "model_cannot_satisfy_requirements",
    "chain": "unbounded_chain",
    "next_operation": "unbounded_chain",
    "next_operations": "unbounded_chain",
}

_OPERATION_FIELDS = {
    "acquire_legal_sources": frozenset({"operation", "role", "target_ref", "source_refs", "citation_ref"}),
    "ingest_private_evidence": frozenset({"operation", "role", "target_ref", "source_refs", "evidence_ref"}),
    "refresh_grounding": frozenset({"operation", "role", "target_ref", "source_refs", "graph_revision"}),
}

_OPERATION_OWNERS = {
    "acquire_legal_sources": "mediator.legal_authority_hooks.LegalAuthoritySearchHook",
    "ingest_private_evidence": "mediator.evidence_hooks.EvidenceStorageHook",
    "refresh_grounding": "mediator.mediator.Mediator.refresh_verified_legal_dependencies",
}

_INDEX_OWNERS = {
    "acquire_legal_sources": "mediator.legal_authority_hooks.LegalAuthoritySearchHook",
    "ingest_private_evidence": "mediator.evidence_hooks.EvidenceStorageHook",
    "refresh_grounding": "mediator.legal_authority_hooks.LegalAuthorityStorageHook",
}


def _disabled_handler(operation: str) -> Callable[[Mapping[str, Any]], Any]:
    def handler(_request: Mapping[str, Any]) -> Any:
        _HANDLER_CALLS["count"] += 1
        raise HookContextError("handler_disabled")

    handler.operation = operation  # type: ignore[attr-defined]
    handler.enabled = False  # type: ignore[attr-defined]
    return handler


_DISABLED_HANDLERS = {name: _disabled_handler(name) for name in LEGAL_EVIDENCE_OPERATIONS}


def operation_handler_call_count() -> int:
    return int(_HANDLER_CALLS["count"])


def _prerequisite_rows(operation: str) -> tuple[dict[str, Any], ...]:
    return (
        {
            "id": "persisted_operation_consent",
            "owner": "integrations.ipfs_datasets.llm",
            "implemented": False,
            "verified": False,
        },
        {
            "id": "encrypted_private_artifact_store",
            "owner": "integrations.ipfs_datasets.storage",
            "implemented": False,
            "verified": False,
        },
        {
            "id": "derived_index_boundary",
            "owner": _INDEX_OWNERS[operation],
            "implemented": False,
            "verified": False,
        },
    )


def legal_evidence_operation_registry() -> tuple[dict[str, Any], ...]:
    """Canonical owners and prerequisites. No operation names a successor."""

    rows = []
    for operation in LEGAL_EVIDENCE_OPERATIONS:
        rows.append({
            "operation": operation,
            "owner": _OPERATION_OWNERS[operation],
            "handler_bound": True,
            "handler_enabled": False,
            "effect_enabled": False,
            "writes_enabled": False,
            "prerequisites": [dict(item) for item in _prerequisite_rows(operation)],
            "next_operations": [],
            "adjacent_roles": list(_EXTRACTION_QUESTION_ROLES),
            "request_schema": HOOK_OPERATION_REQUEST_SCHEMA,
            "result_schema": HOOK_OPERATION_RESULT_SCHEMA,
            "request_fields": sorted(_OPERATION_FIELDS[operation]),
        })
    return tuple(rows)


def register_legal_evidence_operations(*, probes: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Bind disabled handlers. Probes and owners are not called."""

    if probes is not None and not isinstance(probes, Mapping):
        raise HookContextError("malformed")
    return {
        "schema": HOOK_OPERATION_REGISTRY_SCHEMA,
        "registered": True,
        "dispatch_enabled": False,
        "writes_enabled": False,
        "handler_enabled": False,
        "provider_invoked": False,
        "backend_invoked": False,
        "storage_invoked": False,
        "handler_call_count": operation_handler_call_count(),
        "operations": [dict(row) for row in legal_evidence_operation_registry()],
    }


def _effect_code(value: Any, *, depth: int = 0) -> Optional[str]:
    if depth > 6:
        return "malformed"
    if isinstance(value, Mapping):
        for key, item in value.items():
            name = str(key)
            if name in _EFFECT_FIELD_CODES:
                return _EFFECT_FIELD_CODES[name]
            if name in _SECRET_FIELD_NAMES:
                return "secret_material"
            found = _effect_code(item, depth=depth + 1)
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        if len(value) > 32:
            return "malformed"
        for item in value:
            found = _effect_code(item, depth=depth + 1)
            if found:
                return found
    elif isinstance(value, str) and ("/" in value or "\\" in value or ".." in value):
        return "model_cannot_supply_path"
    return None


def _clean_source_refs(value: Any) -> tuple[Optional[str], tuple[dict[str, str], ...]]:
    if type(value) is not list or len(value) > _SOURCE_REF_LIMIT:
        return "malformed", ()
    rows = []
    seen: set[tuple[str, str]] = set()
    for item in value:
        if type(item) is not dict or set(item) != {"source_id", "content_hash"}:
            return "malformed", ()
        source_id = _as_ref(item.get("source_id"))
        content_hash = item.get("content_hash")
        if source_id is None or type(content_hash) is not str or len(content_hash) != 64:
            return "malformed", ()
        try:
            int(content_hash, 16)
        except ValueError:
            return "malformed", ()
        identity = (source_id, content_hash)
        if identity in seen:
            return "malformed", ()
        seen.add(identity)
        rows.append({"source_id": source_id, "content_hash": content_hash})
    return None, tuple(rows)


HOOK_DISPATCH_TRACE_SCHEMA = "hook_dispatch_trace_v1"
HOOK_STAGE_RECEIPT_SCHEMA = "hook_stage_receipt_v1"
_TRACE_KINDS = ("operation", "request", "revision", "outcome")
_TRACE_TERMINALS = frozenset({
    "successful",
    "empty",
    "denied",
    "malformed",
    "timeout",
    "cancelled",
    "unavailable",
})
_SOURCE_SEARCH_STATES = frozenset({"empty", "failed", "found", "not_run"})
_ADMISSION_STATES = frozenset({"rejected", "admitted", "not_run"})
_STAGE_STATUSES = frozenset({
    "recorded",
    "not_reached",
    "malformed",
    "denied",
    "cancelled",
    "timeout",
    "unavailable",
})
_PUBLIC_CODES = frozenset({
    "successful",
    "empty",
    "denied",
    "malformed",
    "timeout",
    "cancelled",
    "unavailable",
    "prerequisite_unavailable",
    "key_unavailable",
    "private_store_unavailable",
    "derived_index_unready",
    "storage_unavailable",
    "binding_missing",
    "consent_missing",
    "consent_revoked",
    "wrong_case",
    "purpose_mismatch",
    "missing_purpose",
    "stale_request",
    "stale_revision",
    "source_binding_changed",
    "context_binding_changed",
    "target_not_host_owned",
    "secret_material",
    "undeclared_role",
    "unknown_field",
    "unsupported_operation",
    "model_cannot_invoke_tools",
    "model_cannot_supply_destination",
    "model_cannot_supply_path",
    "model_cannot_supply_provider_command",
    "model_cannot_satisfy_requirements",
    "model_cannot_select_target",
    "unbounded_chain",
    "deadline_elapsed",
    "invalid_deadline",
    "empty_source_search",
    "source_failure",
    "rejected_admission",
    "stage_not_observed",
    "privacy_denied",
    "operation_unregistered",
    "unclassified",
})
_COUNT_LIMIT = 64
_EARLY_MALFORMED = frozenset({"malformed", "unsupported_operation"})
_EARLY_DENIED = frozenset({
    "unknown_field",
    "undeclared_role",
    "secret_material",
    "target_not_host_owned",
    "unbounded_chain",
})
_UNAVAILABLE_CODES = frozenset({
    "prerequisite_unavailable",
    "key_unavailable",
    "private_store_unavailable",
    "derived_index_unready",
    "storage_unavailable",
    "binding_missing",
})


def _safe_code(value: Any, default: str) -> str:
    if type(value) is not str:
        return default
    if value.startswith("privacy_denied"):
        return "privacy_denied"
    if value in _PUBLIC_CODES:
        return value
    return default


def _safe_error_type(value: Any) -> str:
    if type(value) is not str:
        return ""
    if len(value) > 64 or not value.isidentifier():
        return ""
    return value


def _bounded_count(value: Any) -> int:
    if type(value) is not int or isinstance(value, bool) or value < 0:
        return 0
    if value > _COUNT_LIMIT:
        return _COUNT_LIMIT
    return value


def _safe_revision_token(value: Any) -> str:
    if type(value) is not str or not value or len(value) > 80:
        return ""
    for character in value:
        if character not in "abcdefghijklmnopqrstuvwxyz0123456789_.:-":
            return ""
    return value


def _safe_request_id(value: Any) -> str:
    if type(value) is str and len(value) == 32 and all(character in "0123456789abcdef" for character in value):
        return value
    return uuid.uuid4().hex


def _bounded_session_revision(value: Any) -> int:
    if type(value) is not int or isinstance(value, bool) or value < 0 or value > 1_000_000:
        return 0
    return value


def _dispatch_terminal(status: str, code: str) -> str:
    if code == "cancelled" or status == "cancelled":
        return "cancelled"
    if code in {"timeout", "deadline_elapsed"} or status == "timeout":
        return "timeout"
    if status == "unavailable" or code in _UNAVAILABLE_CODES:
        return "unavailable"
    if code in _EARLY_MALFORMED or status == "malformed":
        return "malformed"
    return "denied"


def _dispatch_stage_statuses(code: str, operation: str) -> tuple[str, str, str]:
    if code in _EARLY_MALFORMED or operation not in LEGAL_EVIDENCE_OPERATIONS:
        return "malformed", "malformed", "not_reached"
    if code in _EARLY_DENIED or code.startswith("model_cannot"):
        return "recorded", "denied", "not_reached"
    if code in {"stale_revision", "stale_request"}:
        return "recorded", "recorded", "denied"
    if code == "binding_missing":
        return "not_reached", "not_reached", "not_reached"
    return "recorded", "recorded", "recorded"


def _stage_status(value: Any, default: str) -> str:
    if type(value) is str and value in _STAGE_STATUSES and value != "successful":
        return value
    return default


def _reconcile_terminal(
    terminal: str,
    source_search: str,
    admission: str,
    code: str,
) -> tuple[str, str, str, str]:
    """Keep empty search, source failure, and rejected admission distinct.

    A caller-supplied success never overwrites a failed or unobserved stage.
    """

    search = source_search if source_search in _SOURCE_SEARCH_STATES else "not_run"
    admit = admission if admission in _ADMISSION_STATES else "not_run"
    term = terminal if terminal in _TRACE_TERMINALS else "unavailable"
    if term == "malformed":
        return "malformed", search, admit, _safe_code(code, "malformed")
    if term == "cancelled":
        return "cancelled", search, admit, "cancelled"
    if term == "timeout":
        kept = _safe_code(code, "timeout")
        return "timeout", search, admit, kept if kept != "unclassified" else "timeout"
    if search == "failed":
        return "unavailable", "failed", admit, "source_failure"
    if admit == "rejected":
        return "denied", search, "rejected", "rejected_admission"
    if term == "denied":
        return "denied", search, admit, _safe_code(code, "denied")
    if term == "unavailable":
        return "unavailable", search, admit, _safe_code(code, "unavailable")
    if term == "empty" or search == "empty":
        if search == "found" or admit == "admitted":
            return "unavailable", search, admit, "stage_not_observed"
        return "empty", "empty", "not_run", "empty_source_search"
    if term == "successful" and search == "found" and admit == "admitted":
        return "successful", "found", "admitted", "successful"
    return "unavailable", search, admit, "stage_not_observed"


def record_bounded_hook_outcome(observation: Mapping[str, Any] | None) -> dict[str, Any]:
    """Record ordered operation, request, revision, and outcome receipts.

    Diagnostics do not call a provider, retry, or copy error text, tool
    payloads, prompts, or source bytes. Stage failure stays visible.
    """

    raw = observation if isinstance(observation, Mapping) and not isinstance(observation, (str, bytes)) else {}
    operation = raw.get("operation") if raw.get("operation") in LEGAL_EVIDENCE_OPERATIONS else ""
    counts = raw.get("counts") if isinstance(raw.get("counts"), Mapping) else {}
    seen = _bounded_count(counts.get("seen", raw.get("seen")))
    admitted = _bounded_count(counts.get("admitted", raw.get("admitted")))
    if admitted > seen:
        admitted = seen
    errors = _bounded_count(counts.get("errors", raw.get("errors")))
    terminal, search, admission, code = _reconcile_terminal(
        str(raw.get("terminal") or ""),
        str(raw.get("source_search") or ""),
        str(raw.get("admission") or ""),
        str(raw.get("code") or ""),
    )
    if terminal != "successful" and errors == 0 and terminal not in {"empty"}:
        errors = 1
    if terminal == "successful":
        errors = 0
    operation_status = _stage_status(raw.get("operation_status"), "recorded" if operation else "malformed")
    request_status = _stage_status(raw.get("request_status"), "recorded" if operation else "malformed")
    revision_status = _stage_status(raw.get("revision_status"), "recorded" if operation else "not_reached")
    if terminal == "malformed" and operation_status == "recorded" and not operation:
        operation_status = "malformed"
        request_status = "malformed"
        revision_status = "not_reached"
    if terminal in {"cancelled", "timeout"} and revision_status == "recorded":
        pass
    outcome_status = terminal
    # No earlier receipt may claim success when the outcome is not success.
    if outcome_status != "successful":
        for label, status in (
            ("operation", operation_status),
            ("request", request_status),
            ("revision", revision_status),
        ):
            if status == "successful":
                if label == "operation":
                    operation_status = "recorded"
                elif label == "request":
                    request_status = "recorded"
                else:
                    revision_status = "recorded"
    request_id = _safe_request_id(raw.get("request_id"))
    session_revision = _bounded_session_revision(raw.get("session_revision"))
    graph_revision = _safe_revision_token(raw.get("graph_revision"))
    error_type = _safe_error_type(raw.get("error_type"))
    receipts = [
        {
            "schema": HOOK_STAGE_RECEIPT_SCHEMA,
            "ordinal": 1,
            "kind": "operation",
            "operation": operation,
            "status": operation_status,
            "code": code if operation_status in {"malformed", "denied", "cancelled", "timeout", "unavailable"} else "recorded",
        },
        {
            "schema": HOOK_STAGE_RECEIPT_SCHEMA,
            "ordinal": 2,
            "kind": "request",
            "request_id": request_id,
            "status": request_status,
            "code": code if request_status in {"malformed", "denied", "cancelled", "timeout", "unavailable"} else "recorded",
        },
        {
            "schema": HOOK_STAGE_RECEIPT_SCHEMA,
            "ordinal": 3,
            "kind": "revision",
            "session_revision": session_revision,
            "graph_revision": graph_revision,
            "status": revision_status,
            "code": code if revision_status in {"malformed", "denied", "cancelled", "timeout", "unavailable"} else "recorded",
        },
        {
            "schema": HOOK_STAGE_RECEIPT_SCHEMA,
            "ordinal": 4,
            "kind": "outcome",
            "status": outcome_status,
            "code": code,
            "source_search": search,
            "admission": admission,
            "error_type": error_type,
            "counts": {"seen": seen, "admitted": admitted, "errors": errors},
            "provider_invoked": False,
            "fallback_used": False,
            "retry_count": 0,
            "effect_dispatched": False,
            "backend_completed": False,
            "requirements_satisfied": False,
            "tool_payload_logged": False,
        },
    ]
    return {
        "schema": HOOK_DISPATCH_TRACE_SCHEMA,
        "ordered": True,
        "request_id": request_id,
        "terminal": terminal,
        "code": code,
        "source_search": search,
        "admission": admission,
        "receipts": receipts,
        "provider_invoked": False,
        "fallback_used": False,
        "retry_count": 0,
        "hides_failure": False,
    }


def public_hook_outcome_log(trace: Mapping[str, Any]) -> dict[str, Any]:
    """Sanitized mediator/router log fields. No payloads or error text."""

    operation = ""
    request_id = ""
    session_revision = 0
    graph_revision = ""
    outcome: Mapping[str, Any] = {}
    receipts = trace.get("receipts") if isinstance(trace, Mapping) else None
    if isinstance(receipts, list):
        for item in receipts:
            if not isinstance(item, Mapping):
                continue
            kind = item.get("kind")
            if kind == "operation" and type(item.get("operation")) is str:
                operation = item["operation"]
            elif kind == "request" and type(item.get("request_id")) is str:
                request_id = item["request_id"]
            elif kind == "revision":
                if type(item.get("session_revision")) is int and not isinstance(item.get("session_revision"), bool):
                    session_revision = item["session_revision"]
                if type(item.get("graph_revision")) is str:
                    graph_revision = item["graph_revision"]
            elif kind == "outcome":
                outcome = item
    counts = outcome.get("counts") if isinstance(outcome.get("counts"), Mapping) else {}
    terminal = trace.get("terminal") if isinstance(trace, Mapping) else ""
    return {
        "operation": operation,
        "request_id": request_id,
        "session_revision": session_revision,
        "graph_revision": graph_revision,
        "terminal": terminal if terminal in _TRACE_TERMINALS else "unavailable",
        "code": _safe_code(trace.get("code") if isinstance(trace, Mapping) else "", "unclassified"),
        "error_type": _safe_error_type(outcome.get("error_type")),
        "source_search": outcome.get("source_search") if outcome.get("source_search") in _SOURCE_SEARCH_STATES else "not_run",
        "admission": outcome.get("admission") if outcome.get("admission") in _ADMISSION_STATES else "not_run",
        "seen": _bounded_count(counts.get("seen")),
        "admitted": _bounded_count(counts.get("admitted")),
        "errors": _bounded_count(counts.get("errors")),
        "prompt_logged": False,
        "response_logged": False,
        "tool_payload_logged": False,
        "provider_invoked": False,
        "fallback_used": False,
        "retry_count": 0,
    }


def _operation_result(
    *,
    operation: str,
    status: str,
    code: str,
    source_refs: Sequence[Mapping[str, str]] = (),
    owner: str = "",
    prerequisites: Sequence[Mapping[str, Any]] = (),
    role: Optional[str] = None,
    session_revision: int = 0,
    graph_revision: str = "",
    request_id: str = "",
    error_type: str = "",
    source_search: str = "not_run",
    admission: str = "not_run",
    handler_invoked: bool = False,
    effect_dispatched: bool = False,
    writes: int = 0,
    storage_invoked: bool = False,
    dispatch_enabled: bool = False,
    handler_enabled: bool = False,
    candidate_status: str = "",
    source_status: str = "",
    late: bool = False,
    host: Any = None,
    owner_id: str = "",
    case_id: str = "",
) -> dict[str, Any]:
    refused = status in {"refused", "timeout", "cancelled", "malformed"}
    public_code = _safe_code(code, "unclassified")
    operation_status, request_status, revision_status = _dispatch_stage_statuses(public_code, operation if operation in LEGAL_EVIDENCE_OPERATIONS else "")
    if status == "successful":
        terminal = "successful"
    elif status == "empty":
        terminal = "empty"
    else:
        terminal = _dispatch_terminal(status, public_code)
    trace = record_bounded_hook_outcome({
        "operation": operation if operation in LEGAL_EVIDENCE_OPERATIONS else "",
        "terminal": terminal,
        "code": public_code,
        "source_search": source_search,
        "admission": admission,
        "operation_status": operation_status,
        "request_status": request_status,
        "revision_status": revision_status,
        "session_revision": session_revision,
        "graph_revision": graph_revision,
        "request_id": request_id,
        "error_type": error_type,
        "counts": {"seen": len(source_refs), "admitted": 0, "errors": 0 if status == "successful" else 1},
    })
    if status == "empty":
        resolved_candidate = "not_candidate"
        resolved_source = "not_admitted"
    elif candidate_status:
        resolved_candidate = candidate_status
        resolved_source = source_status or ("refused" if refused else "not_admitted")
    else:
        resolved_candidate = "refused" if refused else "not_candidate"
        resolved_source = "refused" if refused else "not_admitted"
    result = {
        "schema": HOOK_OPERATION_RESULT_SCHEMA,
        "operation": operation,
        "status": status,
        "code": code,
        "role": role,
        "role_dispatched": False,
        "candidate_status": resolved_candidate,
        "source_status": resolved_source,
        "support_status": "refused" if refused else "unsupported",
        "proof_status": "not_proof",
        "source_refs": [dict(item) for item in source_refs],
        "source_refs_admitted": False,
        "owner": owner,
        "prerequisites": [dict(item) for item in prerequisites],
        "handler_enabled": handler_enabled is True,
        "handler_invoked": handler_invoked is True,
        "effect_dispatched": effect_dispatched is True,
        "provider_invoked": False,
        "backend_invoked": False,
        "storage_invoked": storage_invoked is True,
        "writes": writes if type(writes) is int and writes > 0 else 0,
        "dispatch_enabled": dispatch_enabled is True,
        "late": late is True,
        "trace": trace,
    }
    if _host_qualifies_operations(host):
        _journal_qualified_result(host, result, owner_id=owner_id, case_id=case_id)
    return result


def _marked_prerequisites(operation: str, *, key_available: bool, private_store_available: bool, derived_index_ready: bool) -> list[dict[str, Any]]:
    rows = []
    for item in _prerequisite_rows(operation):
        row = dict(item)
        row["verified"] = False
        if item["id"] == "encrypted_private_artifact_store" and (not key_available or not private_store_available):
            row["status"] = "key_unavailable" if not key_available else "private_store_unavailable"
        elif item["id"] == "derived_index_boundary" and not derived_index_ready:
            row["status"] = "derived_index_unready"
        else:
            row["status"] = "unavailable"
        rows.append(row)
    return rows


def _host_qualifies_operations(host: Any) -> bool:
    """A qualified host exposes saved case facts. Flags and receipts do not."""

    required = (
        "load_saved_case_record",
        "case_knowledge_graph",
        "case_private_artifact_binding",
        "case_derived_index_owner",
        "case_operation_owner",
        "local_public_legal_text",
        "consume_pending_late_mutation",
        "append_mediator_operation_journal",
    )
    return all(callable(getattr(host, name, None)) for name in required)


def _journal_qualified_result(host: Any, result: Mapping[str, Any], *, owner_id: str, case_id: str) -> None:
    entry = {
        "schema": "mediator_operation_journal_v1",
        "operation": result.get("operation") if result.get("operation") in LEGAL_EVIDENCE_OPERATIONS else "",
        "status": str(result.get("status") or ""),
        "code": str(result.get("code") or ""),
        "owner_id": owner_id if type(owner_id) is str else "",
        "case_id": case_id if type(case_id) is str else "",
        "late": result.get("late") is True,
        "writes": result.get("writes") if type(result.get("writes")) is int else 0,
        "effect_dispatched": result.get("effect_dispatched") is True,
        "handler_invoked": result.get("handler_invoked") is True,
        "storage_invoked": result.get("storage_invoked") is True,
        "provider_invoked": False,
        "proof": False,
    }
    host.append_mediator_operation_journal(entry)


def _qualification_prerequisites(operation: str, *, consent: bool, artifact: bool, index: bool) -> list[dict[str, Any]]:
    flags = {
        "persisted_operation_consent": consent,
        "encrypted_private_artifact_store": artifact,
        "derived_index_boundary": index,
    }
    rows = []
    for item in _prerequisite_rows(operation):
        row = dict(item)
        verified = flags[item["id"]] is True
        row["implemented"] = verified
        row["verified"] = verified
        row["status"] = "verified" if verified else "unavailable"
        rows.append(row)
    return rows


def _qualify_saved_host(
    host: Any,
    *,
    operation: str,
    owner_id: str,
    case_id: str,
    target: str,
    graph_revision: str,
    citation_ref: str,
) -> dict[str, Any]:
    """Re-read saved consent, the live graph, ciphertext, and the derived index."""

    from complaint_phases.knowledge_graph import KnowledgeGraph
    from integrations.private_storage import (
        PrivateArtifactBindingError,
        PrivateArtifactIntegrityError,
        PrivateKeyMaterialError,
        retrieve_private_artifact,
    )
    from mediator.evidence_hooks import EvidenceStorageHook
    from mediator.legal_authority_hooks import LegalAuthoritySearchHook, LegalAuthorityStorageHook
    from mediator.mediator import Mediator

    def failed(code: str, status: str, *, consent: bool = False, artifact: bool = False, index: bool = False) -> dict[str, Any]:
        return {
            "ok": False,
            "code": code,
            "status": status,
            "fingerprint": "",
            "prerequisites": _qualification_prerequisites(operation, consent=consent, artifact=artifact, index=index),
            "opened_hash": "",
            "citation_ref": citation_ref,
        }

    try:
        record = host.load_saved_case_record(owner_id)
    except Exception:
        return failed("consent_missing", "refused")
    if not isinstance(record, Mapping):
        return failed("consent_missing", "refused")
    if str(record.get("user_id") or "") != owner_id or str(record.get("case_id") or "") != case_id:
        return failed("wrong_case", "refused")
    consent = record.get("mediator_operation_consent")
    if not isinstance(consent, Mapping):
        return failed("consent_missing", "refused")
    if consent.get("revoked") is True:
        return failed("consent_revoked", "refused")
    if str(consent.get("user_id") or "") != owner_id or str(consent.get("case_id") or "") != case_id:
        return failed("wrong_case", "refused")
    operations = consent.get("operations")
    generation = consent.get("generation")
    if not isinstance(operations, list) or operation not in operations:
        return failed("consent_missing", "refused")
    if type(generation) is not int or isinstance(generation, bool) or generation < 1:
        return failed("consent_missing", "refused")
    try:
        graph = host.case_knowledge_graph(owner_id, case_id)
    except Exception:
        graph = None
    if not isinstance(graph, KnowledgeGraph):
        return failed("target_not_host_owned", "refused", consent=True)
    token = graph_revision_token(graph)
    if token != graph_revision:
        return failed("stale_revision", "refused", consent=True)
    entities = getattr(graph, "entities", None)
    if not isinstance(entities, Mapping) or target not in entities:
        return failed("target_not_host_owned", "refused", consent=True)
    expected = {
        "acquire_legal_sources": LegalAuthoritySearchHook,
        "ingest_private_evidence": EvidenceStorageHook,
        "refresh_grounding": Mediator,
    }[operation]
    try:
        owner = host.case_operation_owner(operation, owner_id, case_id)
    except Exception:
        owner = None
    if not isinstance(owner, expected):
        return failed("binding_missing", "refused", consent=True)
    try:
        binding = host.case_private_artifact_binding(owner_id, case_id)
    except Exception:
        binding = {"code": "private_store_unavailable"}
    if not isinstance(binding, Mapping):
        return failed("private_store_unavailable", "unavailable", consent=True)
    binding_code = str(binding.get("code") or "")
    if binding_code == "key_unavailable":
        return failed("key_unavailable", "unavailable", consent=True)
    if binding_code != "bound":
        return failed("private_store_unavailable", "unavailable", consent=True)
    try:
        opened = retrieve_private_artifact(
            str(binding.get("cid") or ""),
            access=binding.get("access"),
            tenant_id=str(binding.get("tenant_id") or ""),
            case_id=case_id,
            artifact_kind=str(binding.get("artifact_kind") or ""),
            revision=str(binding.get("revision") or ""),
            principal_id=str(binding.get("principal_id") or binding.get("tenant_id") or ""),
            key=binding.get("key"),
            key_id=str(binding.get("key_id") or ""),
            backend=binding.get("backend"),
        )
    except PrivateKeyMaterialError:
        return failed("key_unavailable", "unavailable", consent=True)
    except (PrivateArtifactBindingError, PrivateArtifactIntegrityError):
        return failed("private_store_unavailable", "unavailable", consent=True)
    except Exception:
        return failed("private_store_unavailable", "unavailable", consent=True)
    payload = opened.get("data") if isinstance(opened, Mapping) else None
    if not isinstance(payload, (bytes, bytearray)) or not payload:
        return failed("private_store_unavailable", "unavailable", consent=True)
    opened_hash = hashlib.sha256(bytes(payload)).hexdigest()
    try:
        index = host.case_derived_index_owner(operation, owner_id, case_id)
    except Exception:
        index = None
    if not isinstance(index, LegalAuthorityStorageHook):
        return failed("derived_index_unready", "unavailable", consent=True, artifact=True)
    try:
        index_status = index.private_derived_index_status()
    except Exception:
        return failed("derived_index_unready", "unavailable", consent=True, artifact=True)
    ready = (
        isinstance(index_status, Mapping)
        and index_status.get("status") == "available"
        and index_status.get("case_id") == case_id
        and index_status.get("closed") is not True
        and index_status.get("owned") is True
    )
    if not ready:
        return failed("derived_index_unready", "unavailable", consent=True, artifact=True)
    fingerprint = json.dumps({
        "generation": generation,
        "graph": token,
        "cid": str(binding.get("cid") or ""),
        "hash": opened_hash,
        "index": str(index_status.get("index_mode") or ""),
        "owner": expected.__name__,
    }, sort_keys=True)
    return {
        "ok": True,
        "code": "verified",
        "status": "successful",
        "fingerprint": fingerprint,
        "prerequisites": _qualification_prerequisites(operation, consent=True, artifact=True, index=True),
        "opened_hash": opened_hash,
        "citation_ref": citation_ref,
        "generation": generation,
    }


def _apply_qualified_effect(host: Any, operation: str, snapshot: Mapping[str, Any], *, owner_id: str, case_id: str) -> dict[str, Any]:
    index = host.case_derived_index_owner(operation, owner_id, case_id)
    if operation == "ingest_private_evidence":
        label = "sha256:" + str(snapshot.get("opened_hash") or "")
        committed = index.commit_private_derived(case_id=case_id, kind="evidence", text=label)
        ok = isinstance(committed, Mapping) and committed.get("status") == "available" and bool(committed.get("token") or committed.get("row_id"))
        return {
            "ok": ok,
            "status": "successful" if ok else "unavailable",
            "code": "successful" if ok else str(committed.get("code") or "derived_index_unready"),
            "writes": 1 if ok else 0,
            "storage_invoked": True,
            "source_search": "found" if ok else "failed",
            "admission": "admitted" if ok else "rejected",
        }
    if operation == "acquire_legal_sources":
        citation = str(snapshot.get("citation_ref") or "")
        text = host.local_public_legal_text(owner_id, case_id, citation)
        if type(text) is not str or not text.strip():
            return {
                "ok": False,
                "status": "empty",
                "code": "empty_source_search",
                "writes": 0,
                "storage_invoked": False,
                "source_search": "empty",
                "admission": "not_run",
            }
        cached = index.cache_public_law_source(citation=citation, text=text)
        ok = isinstance(cached, Mapping) and cached.get("status") == "available" and bool(cached.get("cache_id"))
        owner = host.case_operation_owner(operation, owner_id, case_id)
        mediator = getattr(owner, "mediator", None)
        if mediator is not None and hasattr(mediator, "log"):
            mediator.log("qualified_legal_source_cache", citation=citation, cached=ok)
        return {
            "ok": ok,
            "status": "successful" if ok else "unavailable",
            "code": "successful" if ok else "storage_unavailable",
            "writes": 1 if ok else 0,
            "storage_invoked": False,
            "source_search": "found" if ok else "failed",
            "admission": "admitted" if ok else "rejected",
        }
    graph = host.case_knowledge_graph(owner_id, case_id)
    before = graph_revision_token(graph)
    graph.append_revision({
        "event_id": "grounding-" + str(snapshot.get("opened_hash") or "")[:16],
        "kind": "grounding_refresh",
    })
    after = graph_revision_token(graph)
    mediator = host.case_operation_owner(operation, owner_id, case_id)
    if hasattr(mediator, "log"):
        mediator.log("qualified_grounding_refresh", graph_changed=after != before)
    ok = after != before
    return {
        "ok": ok,
        "status": "successful" if ok else "unavailable",
        "code": "successful" if ok else "stale_revision",
        "writes": 1 if ok else 0,
        "storage_invoked": False,
        "source_search": "found" if ok else "not_run",
        "admission": "admitted" if ok else "not_run",
    }


def dispatch_registered_hook_operation(
    request: Mapping[str, Any] | None,
    *,
    context: HookExecutionContext | None,
    host_targets: Sequence[str],
    owner_id: str,
    case_id: str,
    session_id: str,
    session_revision: int,
    graph_revision: str,
    legal_context: Mapping[str, Any] | None,
    purpose: Any,
    source_bindings: Sequence[Mapping[str, Any]] | None,
    privacy_context: Mapping[str, Any] | None,
    now: datetime,
    host: Any = None,
    storage_available: bool = True,
    request_state: str = "active",
    key_available: bool = True,
    private_store_available: bool = True,
    derived_index_ready: bool = True,
    persisted_consent_verified: bool = False,
    probes: Mapping[str, Any] | None = None,
    effect: Optional[Callable[[Mapping[str, Any]], Any]] = None,
    handler: Optional[Callable[[Mapping[str, Any]], Any]] = None,
) -> dict[str, Any]:
    """Validate one registered operation.

    Caller booleans, probes, injected effects, and invented receipts cannot
    enable a handler. A host dispatch runs only after saved consent, a live
    graph target, private ciphertext, and the derived index are re-read.
    """

    del persisted_consent_verified, effect, handler, probes
    qualified_host = _host_qualifies_operations(host)
    if not isinstance(request, Mapping) or isinstance(request, (str, bytes)):
        return _operation_result(operation="", status="refused", code="malformed")
    proposal = request.get("model_proposal") if "model_proposal" in request else None
    if proposal is not None:
        proposal_code = _effect_code(proposal) or "model_cannot_select_target"
        if proposal_code == "malformed":
            proposal_code = "model_cannot_select_target"
        return _operation_result(operation=str(request.get("operation") or ""), status="refused", code=proposal_code)
    effect_code = _effect_code(request)
    if effect_code:
        return _operation_result(operation=str(request.get("operation") or ""), status="refused", code=effect_code)
    operation = request.get("operation")
    if type(operation) is not str or operation not in _OPERATION_FIELDS:
        return _operation_result(operation=str(operation or ""), status="refused", code="unsupported_operation")
    if set(request) - _OPERATION_FIELDS[operation]:
        return _operation_result(operation=operation, status="refused", code="unknown_field", owner=_OPERATION_OWNERS[operation])
    role = request.get("role")
    if role is not None and role not in _EXTRACTION_QUESTION_ROLES:
        return _operation_result(operation=operation, status="refused", code="undeclared_role", owner=_OPERATION_OWNERS[operation])
    ref_code, source_refs = _clean_source_refs(request.get("source_refs"))
    if ref_code:
        return _operation_result(operation=operation, status="refused", code=ref_code, owner=_OPERATION_OWNERS[operation])
    target = _as_ref(request.get("target_ref"))
    owned = tuple(item for item in host_targets if type(item) is str)
    if target is None or (not qualified_host and target not in owned):
        return _operation_result(
            operation=operation, status="refused", code="target_not_host_owned", owner=_OPERATION_OWNERS[operation],
            host=host, owner_id=owner_id if type(owner_id) is str else "", case_id=case_id if type(case_id) is str else "",
        )
    if operation == "acquire_legal_sources" and request.get("citation_ref") is not None and _as_ref(request.get("citation_ref")) is None:
        return _operation_result(operation=operation, status="refused", code="malformed", owner=_OPERATION_OWNERS[operation])
    if operation == "ingest_private_evidence" and request.get("evidence_ref") is not None and _as_ref(request.get("evidence_ref")) is None:
        return _operation_result(operation=operation, status="refused", code="malformed", owner=_OPERATION_OWNERS[operation])
    if operation == "refresh_grounding":
        revision = request.get("graph_revision")
        if _bounded_text(revision, limit=80) is None:
            return _operation_result(operation=operation, status="refused", code="malformed", owner=_OPERATION_OWNERS[operation])
        if revision != graph_revision:
            return _operation_result(
                operation=operation,
                status="refused",
                code="stale_revision",
                owner=_OPERATION_OWNERS[operation],
                session_revision=session_revision if type(session_revision) is int else 0,
                graph_revision=graph_revision if type(graph_revision) is str else "",
                host=host,
                owner_id=owner_id if type(owner_id) is str else "",
                case_id=case_id if type(case_id) is str else "",
            )
    decision = authorize_hook_execution(
        context,
        owner_id=owner_id,
        case_id=case_id,
        session_id=session_id,
        session_revision=session_revision,
        graph_revision=graph_revision,
        legal_context=legal_context,
        purpose=purpose,
        source_bindings=source_bindings,
        privacy_context=privacy_context,
        now=now,
        host=host,
        storage_available=storage_available,
        request_state=request_state,
        effect=None,
    )
    prerequisites = _marked_prerequisites(
        operation,
        key_available=key_available is True,
        private_store_available=private_store_available is True,
        derived_index_ready=derived_index_ready is True,
    )
    trace_revision = session_revision if type(session_revision) is int else 0
    trace_graph = graph_revision if type(graph_revision) is str else ""
    if not decision["authorized"]:
        auth_code = str(decision["code"])
        auth_status = "cancelled" if auth_code == "cancelled" else "refused"
        return _operation_result(
            operation=operation,
            status=auth_status,
            code=auth_code,
            source_refs=source_refs,
            owner=_OPERATION_OWNERS[operation],
            prerequisites=prerequisites,
            role=role if type(role) is str else None,
            session_revision=trace_revision,
            graph_revision=trace_graph,
            host=host,
            owner_id=owner_id if type(owner_id) is str else "",
            case_id=case_id if type(case_id) is str else "",
        )
    if request_state == "timeout":
        return _operation_result(
            operation=operation,
            status="timeout",
            code="timeout",
            source_refs=source_refs,
            owner=_OPERATION_OWNERS[operation],
            prerequisites=prerequisites,
            role=role if type(role) is str else None,
            session_revision=trace_revision,
            graph_revision=trace_graph,
            error_type="TimeoutError",
        )
    if key_available is not True:
        code = "key_unavailable"
    elif private_store_available is not True:
        code = "private_store_unavailable"
    elif derived_index_ready is not True:
        code = "derived_index_unready"
    else:
        code = "prerequisite_unavailable"
    if not qualified_host:
        return _operation_result(
            operation=operation,
            status="unavailable",
            code=code,
            source_refs=source_refs,
            owner=_OPERATION_OWNERS[operation],
            prerequisites=prerequisites,
            role=role if type(role) is str else None,
            session_revision=trace_revision,
            graph_revision=trace_graph,
        )
    citation_ref = ""
    if operation == "acquire_legal_sources":
        citation_ref = _as_ref(request.get("citation_ref")) or ""
    identity = owner_id if type(owner_id) is str else ""
    case_token = case_id if type(case_id) is str else ""
    common = dict(
        operation=operation,
        source_refs=source_refs,
        owner=_OPERATION_OWNERS[operation],
        role=role if type(role) is str else None,
        session_revision=trace_revision,
        graph_revision=trace_graph,
        host=host,
        owner_id=identity,
        case_id=case_token,
    )
    first = _qualify_saved_host(
        host, operation=operation, owner_id=identity, case_id=case_token, target=target,
        graph_revision=trace_graph, citation_ref=citation_ref,
    )
    if not first["ok"]:
        return _operation_result(
            status=str(first["status"]), code=str(first["code"]), prerequisites=first["prerequisites"], **common,
        )
    late_kind = None
    try:
        late_kind = host.consume_pending_late_mutation(identity, case_token)
    except Exception:
        late_kind = "late_failed"
    second = _qualify_saved_host(
        host, operation=operation, owner_id=identity, case_id=case_token, target=target,
        graph_revision=trace_graph, citation_ref=citation_ref,
    )
    if late_kind or not second["ok"] or second.get("fingerprint") != first.get("fingerprint"):
        status = str(second["status"]) if not second["ok"] else "refused"
        code = str(second["code"]) if not second["ok"] else "stale_request"
        return _operation_result(
            status=status, code=code, prerequisites=second["prerequisites"], late=True, **common,
        )
    _HANDLER_CALLS["count"] += 1
    applied = _apply_qualified_effect(host, operation, second, owner_id=identity, case_id=case_token)
    succeeded = applied["ok"] is True
    return _operation_result(
        status=str(applied["status"]),
        code=str(applied["code"]),
        prerequisites=second["prerequisites"],
        source_search=str(applied["source_search"]),
        admission=str(applied["admission"]),
        handler_invoked=True,
        effect_dispatched=succeeded,
        writes=int(applied["writes"]),
        storage_invoked=applied["storage_invoked"] is True,
        dispatch_enabled=succeeded,
        handler_enabled=succeeded,
        candidate_status="candidate" if succeeded else "",
        source_status="referenced" if succeeded else "",
        **common,
    )


def prepare_remote_hook_query(
    *,
    policy_reader: Callable[[], Any],
    provider_loader: Optional[Callable[[], Any]] = None,
    query_submitter: Optional[Callable[[Mapping[str, Any]], Any]] = None,
    owner_id: str,
    case_id: str,
    purpose: str,
    provider_kind: str,
    data_class: str,
    tools: bool = False,
    citation: Any = None,
    complaint_text: Any = None,
    private_fields: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Read persisted owner/case policy before any provider load or query submit.

    Unknown, missing, local, and revoked consent refuse effectful remote
    dispatch. A synthetic loader result is not a live Grok identity.
    """

    from integrations.ipfs_datasets.llm import (
        bind_remote_invocation,
        evaluate_remote_operation_consent,
        minimize_purpose_query,
    )

    base = {
        "purpose": purpose if type(purpose) is str else "",
        "policy_read": False,
        "provider_loader_called": False,
        "query_submitted": False,
        "effectful": False,
        "status": "refused",
        "code": "consent_missing",
        "query": None,
        "invocation_id": None,
        "tools_authorized": False,
        "complaint_included": False,
        "live_model_identity_verified": False,
        "provider_status": "",
    }
    try:
        record = policy_reader()
    except Exception:
        base["status"] = "unavailable"
        base["code"] = "policy_unavailable"
        return base
    base["policy_read"] = True
    decision = evaluate_remote_operation_consent(
        record,
        user_id=owner_id,
        case_id=case_id,
        purpose=purpose,
        provider_kind=provider_kind,
        data_class=data_class,
        tools=tools,
    )
    query = minimize_purpose_query(
        purpose,
        private_fields=private_fields,
        citation=citation,
        complaint_text=complaint_text,
    )
    complaint = complaint_text if type(complaint_text) is str else ""
    encoded = json.dumps(query, sort_keys=True, ensure_ascii=False)
    base["query"] = query
    base["complaint_included"] = bool(complaint) and complaint in encoded
    base["tools_authorized"] = False
    if base["complaint_included"]:
        base["code"] = "query_not_minimized"
        base["query"] = None
        return base
    if decision["local_query_allowed"] and not decision["effectful_allowed"]:
        if query_submitter is not None:
            query_submitter(query)
            base["query_submitted"] = True
        base["status"] = "local_only"
        base["code"] = "local_only"
        return base
    if not decision["effectful_allowed"]:
        base["code"] = str(decision["code"])
        base["query"] = None
        return base
    if provider_loader is None:
        base["status"] = "unavailable"
        base["code"] = "provider_unavailable"
        return base
    base["provider_loader_called"] = True
    try:
        loaded = provider_loader()
    except Exception:
        base["status"] = "unavailable"
        base["code"] = "provider_unavailable"
        return base
    provider_status = ""
    if isinstance(loaded, Mapping):
        provider_status = str(loaded.get("status") or "")
    elif loaded is None:
        provider_status = "unavailable"
    else:
        provider_status = "available"
    base["provider_status"] = provider_status
    if provider_status != "available":
        base["status"] = "unavailable"
        base["code"] = "provider_unavailable"
        return base
    invocation_id = bind_remote_invocation(
        user_id=owner_id,
        case_id=case_id,
        purpose=purpose,
        provider_kind=provider_kind,
        data_class=data_class,
        generation=int(decision["generation"]),
    )
    base["invocation_id"] = invocation_id
    if query_submitter is not None:
        try:
            query_submitter(query)
        except Exception:
            base["status"] = "unavailable"
            base["code"] = "query_unavailable"
            return base
        base["query_submitted"] = True
    base["effectful"] = True
    base["status"] = "available"
    base["code"] = "authorized"
    return base


def accept_late_hook_result(
    *,
    policy_reader: Callable[[], Any],
    invocation_id: str,
    owner_id: str,
    case_id: str,
    result_acceptor: Optional[Callable[[], Any]] = None,
    bound_graph_revision: Optional[str] = None,
    current_graph_revision: Optional[str] = None,
    bound_session_revision: Optional[int] = None,
    current_session_revision: Optional[int] = None,
) -> dict[str, Any]:
    """Recheck the persisted policy before accepting a late remote result.

    A changed graph or session revision is stale even when consent still matches.
    """

    from integrations.ipfs_datasets.llm import accept_late_remote_result

    try:
        record = policy_reader()
    except Exception:
        return {
            "accepted": False,
            "code": "policy_unavailable",
            "policy_read": False,
            "acceptor_called": False,
            "live_model_identity_verified": False,
        }
    decision = accept_late_remote_result(
        record,
        invocation_id=invocation_id,
        user_id=owner_id,
        case_id=case_id,
        bound_graph_revision=bound_graph_revision,
        current_graph_revision=current_graph_revision,
        bound_session_revision=bound_session_revision,
        current_session_revision=current_session_revision,
    )
    accepted = decision["accepted"] is True
    acceptor_called = False
    if accepted and result_acceptor is not None:
        result_acceptor()
        acceptor_called = True
    return {
        "accepted": accepted,
        "code": str(decision["code"]),
        "policy_read": True,
        "acceptor_called": acceptor_called,
        "live_model_identity_verified": False,
    }


_GUI_INFERENCE_HOLDS: dict[str, dict[str, Any]] = {}


def clear_gui_inference_holds() -> None:
    """Drop held GUI proposals. This does not call a provider."""

    _GUI_INFERENCE_HOLDS.clear()


def discard_gui_inference_hold(invocation_id: str) -> None:
    """Discard one held proposal without admitting it."""
    _GUI_INFERENCE_HOLDS.pop(invocation_id, None)


def minimal_source_references(source_bindings: Sequence[Mapping[str, Any]] | None) -> tuple[dict[str, str], ...]:
    """Source id and content hash only. Passages and secrets are not copied."""

    rows = normalize_source_bindings(source_bindings)
    return tuple({"source_id": row["source_id"], "content_hash": row["content_hash"]} for row in rows)


def _gui_grant_code(grant: Any, *, case_id: str, source_revision: str) -> Optional[str]:
    if not isinstance(grant, Mapping):
        return "grant_missing"
    if grant.get("revoked") is True:
        return "grant_revoked"
    if type(grant.get("grant_id")) is not str or not grant["grant_id"].strip():
        return "grant_missing"
    if str(grant.get("case_id") or "") != case_id:
        return "grant_wrong_case"
    generation = grant.get("generation")
    if type(generation) is not int or isinstance(generation, bool) or generation < 1:
        return "grant_missing"
    if type(grant.get("source_revision")) is not str or grant.get("source_revision") != source_revision:
        return "stale_source_revision"
    return None


def _gui_refusal(
    *,
    purpose_id: str,
    code: str,
    route: Optional[dict[str, Any]] = None,
    model_dispatched: bool = False,
) -> dict[str, Any]:
    result = _purpose_result(
        purpose_id=purpose_id,
        status="refused",
        code=code,
        model_dispatched=model_dispatched,
        output=None,
        identity=None,
        route=route,
    )
    result["accepted"] = False
    result["live_model_identity_verified"] = False
    result["router_calls"] = []
    result["source_references"] = []
    result["requirements_satisfied"] = False
    result["limitations"] = (
        "synthetic_transport_does_not_qualify_live_model",
        "development_authorization_is_not_case_consent",
    )
    return result


def native_gui_inference_transport(call: Mapping[str, Any]) -> dict[str, Any]:
    """First-party operator-selected route; the workspace owns its authority.

    This adapter accepts the server's bound hook arguments, not a browser
    policy document. The existing observed route owns the real router call,
    bounded Native observation, tools denial and output validation.
    """
    return dispatch_observed_hook_purpose(**dict(call))


def dispatch_gui_bounded_inference(
    *,
    policy_record: Mapping[str, Any] | None,
    grant: Mapping[str, Any] | None,
    purpose_id: str,
    inputs: Mapping[str, Any] | None,
    source_bindings: Sequence[Mapping[str, Any]] | None,
    legal_context: Mapping[str, Any] | None,
    owner_id: str,
    case_id: str,
    session_id: str,
    session_revision: int,
    graph_revision: str,
    deadline: Any,
    now: datetime,
    privacy_context: Mapping[str, Any] | None,
    model_transport: Optional[Callable[..., Any]] = None,
    complaint_text: Any = None,
    allow_local_fallback: bool = False,
    allow_cross_provider_fallback: bool = False,
    requested_provider: Optional[str] = None,
    requested_model: Optional[str] = None,
    operation: str = "refresh_grounding",
    timeout: float = 30.0,
    cancel_event: Any = None,
    revision_reader: Optional[Callable[[], Mapping[str, Any]]] = None,
) -> dict[str, Any]:
    """Dispatch one GUI purpose through the existing consented hook boundary.

    The injected transport is synthetic. A payload that claims a live Grok
    identity is not treated as qualification. Fallback stays disabled. The
    call carries allowed purpose inputs and source id/hash references only.
    Model output is held until :func:`admit_gui_bounded_inference`.
    """

    from integrations.ipfs_datasets.llm import bind_remote_invocation, evaluate_remote_operation_consent

    route = _pinned_route()
    purpose = purpose_id if type(purpose_id) is str else ""
    if purpose not in MODEL_PURPOSE_IDS:
        return _gui_refusal(purpose_id=purpose or str(purpose_id), code="undeclared_purpose", route=None)
    native_route = model_transport is native_gui_inference_transport
    if (allow_local_fallback is not False or allow_cross_provider_fallback is not False
            or requested_provider not in (None, route["provider"])
            or requested_model not in (None, route["model"])):
        return _gui_refusal(purpose_id=purpose, code="unpinned_route", route=route)
    try:
        references = minimal_source_references(source_bindings)
        source_revision = source_binding_hash(source_bindings)
    except HookContextError as exc:
        return _gui_refusal(purpose_id=purpose, code=exc.code, route=route)
    complaint = complaint_text if type(complaint_text) is str else ""
    try:
        encoded_inputs = json.dumps(inputs, sort_keys=True, ensure_ascii=False) if inputs is not None else ""
    except (TypeError, ValueError):
        encoded_inputs = ""
    if complaint and complaint in encoded_inputs:
        return _gui_refusal(purpose_id=purpose, code="query_not_minimized", route=route)
    grant_code = _gui_grant_code(grant, case_id=case_id, source_revision=source_revision)
    if grant_code:
        return _gui_refusal(purpose_id=purpose, code=grant_code, route=route)
    consent = evaluate_remote_operation_consent(
        policy_record,
        user_id=owner_id,
        case_id=case_id,
        purpose=purpose,
        provider_kind="grok_inference",
        data_class="raw_intake",
        tools=False,
    )
    if consent["effectful_allowed"] is not True:
        return _gui_refusal(purpose_id=purpose, code=str(consent["code"]), route=route)
    try:
        context = bind_hook_execution_context(
            operation=operation,
            owner_id=owner_id,
            case_id=case_id,
            session_id=session_id,
            session_revision=session_revision,
            graph_revision=graph_revision,
            legal_context=legal_context if isinstance(legal_context, Mapping) else {},
            purpose=purpose,
            deadline=deadline,
            source_bindings=source_bindings,
            privacy_context=privacy_context,
        )
    except HookContextError as exc:
        return _gui_refusal(purpose_id=purpose, code=exc.code, route=route)
    observed: list[dict[str, Any]] = []

    def observing(call: Mapping[str, Any]) -> Any:
        forwarded = dict(call)
        forwarded["source_references"] = [dict(row) for row in references]
        forwarded["allow_local_fallback"] = False
        forwarded["allow_cross_provider_fallback"] = False
        observed.append(forwarded)
        if model_transport is None:
            return {"status": "unavailable"}
        return model_transport(forwarded)

    invocation_id = bind_remote_invocation(
        user_id=owner_id,
        case_id=case_id,
        purpose=purpose,
        provider_kind="grok_inference",
        data_class="raw_intake",
        generation=int(consent["generation"]),
    )
    if native_route:
        import math
        if (type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 60
                or not callable(revision_reader)):
            return _gui_refusal(purpose_id=purpose, code="live_revalidation_required", route=route)
        fresh = revision_reader()
        if (not isinstance(fresh, Mapping) or fresh.get("record") != policy_record
                or fresh.get("grant") != grant or fresh.get("graph_revision") != graph_revision
                or fresh.get("session_revision") != session_revision):
            return _gui_refusal(purpose_id=purpose, code="stale_request", route=route)
        current = datetime.now(timezone.utc)
        remaining = min(float(timeout), (context.deadline - current).total_seconds())
        if remaining <= 0 or (cancel_event is not None and cancel_event.is_set()):
            return _gui_refusal(purpose_id=purpose, code="deadline_expired" if remaining <= 0 else "cancelled", route=route)
        result = native_gui_inference_transport({
            "context": context, "purpose_id": purpose, "inputs": inputs,
            "owner_id": owner_id, "case_id": case_id, "session_id": session_id,
            "session_revision": session_revision, "graph_revision": graph_revision,
            "legal_context": legal_context, "source_bindings": source_bindings,
            "privacy_context": privacy_context, "now": current, "consent_record": policy_record,
            "revision_reader": revision_reader, "cancel_event": cancel_event, "timeout": remaining,
            "provider_source_references": references,
        })
    else:
        result = dispatch_declared_hook_purpose(
        context,
        purpose,
        inputs,
        owner_id=owner_id,
        case_id=case_id,
        session_id=session_id,
        session_revision=session_revision,
        graph_revision=graph_revision,
        legal_context=legal_context,
        source_bindings=source_bindings,
        privacy_context=privacy_context,
        now=now,
        model_transport=observing,
        requested_provider=requested_provider,
        requested_model=requested_model,
        allow_local_fallback=False,
        allow_cross_provider_fallback=False,
    )
    result["router_calls"] = observed
    result["source_references"] = [dict(row) for row in references]
    result["invocation_id"] = invocation_id
    result["accepted"] = False
    result["live_model_identity_verified"] = native_route and result.get("live_model_identity_verified") is True
    result["requirements_satisfied"] = False
    result["requirements_satisfied_by_model"] = False
    result["bound_source_revision"] = source_revision
    result["bound_grant_generation"] = int(grant["generation"]) if isinstance(grant, Mapping) else 0
    result["bound_graph_revision"] = graph_revision
    result["bound_session_revision"] = session_revision
    result["consent_generation"] = int(consent["generation"])
    result["limitations"] = (
        "current_call_native_observation_only" if native_route else "synthetic_transport_does_not_qualify_live_model",
        "development_authorization_is_not_case_consent",
        "provider_output_is_not_verified_legal_support",
        "output_waits_for_late_admission",
    )
    if result.get("status") == "available" and result.get("output") is not None:
        _GUI_INFERENCE_HOLDS[invocation_id] = {
            "output": result["output"],
            "owner_id": owner_id,
            "case_id": case_id,
            "purpose": purpose,
            "source_revision": source_revision,
            "grant_id": str(grant.get("grant_id")) if isinstance(grant, Mapping) else "",
            "grant_generation": int(grant["generation"]) if isinstance(grant, Mapping) else 0,
            "graph_revision": graph_revision,
            "session_revision": session_revision,
            "invocation_id": invocation_id,
            "observation": {"transport_kind": "native_observation" if native_route else "synthetic",
                "provider_invoked": result.get("provider_invoked") is True,
                "live_model_identity_verified": result.get("live_model_identity_verified") is True,
                "native_observation_bound": bool((result.get("identity") or {}).get("native_observation_bound")),
                "request_id": str(result.get("request_id") or "")},
        }
        result["output"] = None
        result["status"] = "held"
        result["code"] = "awaiting_late_admission"
    return result


def admit_gui_bounded_inference(
    *,
    invocation_id: str,
    policy_record: Mapping[str, Any] | None,
    grant: Mapping[str, Any] | None,
    source_bindings: Sequence[Mapping[str, Any]] | None,
    owner_id: str,
    case_id: str,
    graph_revision: str,
    session_revision: int,
) -> dict[str, Any]:
    """Re-read consent, the resource grant, and source revisions before release.

    A synthetic hold is not a live model qualification. Revocation, a new
    grant generation, or a changed source hash drops the held proposal.
    """

    from integrations.ipfs_datasets.llm import accept_late_remote_result

    base = {
        "accepted": False,
        "code": "invocation_missing",
        "output": None,
        "live_model_identity_verified": False,
        "requirements_satisfied": False,
        "requirements_satisfied_by_model": False,
        "consent_revalidated": False,
        "grant_revalidated": False,
        "source_revision_revalidated": False,
        "policy_read": isinstance(policy_record, Mapping),
    }
    if type(invocation_id) is not str:
        return base
    held = _GUI_INFERENCE_HOLDS.get(invocation_id)
    if held is None:
        return base
    if held["owner_id"] != owner_id or held["case_id"] != case_id:
        base["code"] = "invocation_not_reusable"
        _GUI_INFERENCE_HOLDS.pop(invocation_id, None)
        return base
    late = accept_late_remote_result(
        policy_record,
        invocation_id=invocation_id,
        user_id=owner_id,
        case_id=case_id,
        bound_graph_revision=str(held["graph_revision"]),
        current_graph_revision=graph_revision if type(graph_revision) is str else "",
        bound_session_revision=int(held["session_revision"]),
        current_session_revision=session_revision if type(session_revision) is int else -1,
    )
    base["consent_revalidated"] = True
    if late["accepted"] is not True:
        base["code"] = str(late["code"])
        _GUI_INFERENCE_HOLDS.pop(invocation_id, None)
        return base
    try:
        current_revision = source_binding_hash(source_bindings)
    except HookContextError as exc:
        base["code"] = exc.code
        base["source_revision_revalidated"] = True
        _GUI_INFERENCE_HOLDS.pop(invocation_id, None)
        return base
    base["source_revision_revalidated"] = True
    if current_revision != held["source_revision"]:
        base["code"] = "stale_source_revision"
        _GUI_INFERENCE_HOLDS.pop(invocation_id, None)
        return base
    grant_code = _gui_grant_code(grant, case_id=case_id, source_revision=current_revision)
    base["grant_revalidated"] = True
    if grant_code:
        base["code"] = grant_code
        _GUI_INFERENCE_HOLDS.pop(invocation_id, None)
        return base
    if not isinstance(grant, Mapping) or str(grant.get("grant_id") or "") != held["grant_id"]:
        base["code"] = "grant_missing"
        _GUI_INFERENCE_HOLDS.pop(invocation_id, None)
        return base
    if int(grant["generation"]) != int(held["grant_generation"]):
        base["code"] = "stale_grant"
        _GUI_INFERENCE_HOLDS.pop(invocation_id, None)
        return base
    output = held["output"]
    _GUI_INFERENCE_HOLDS.pop(invocation_id, None)
    base["accepted"] = True
    base["code"] = "accepted"
    base["output"] = output
    observation = held.get("observation") or {}
    base.update(observation)
    base["live_model_identity_verified"] = (observation.get("transport_kind") == "native_observation"
        and observation.get("native_observation_bound") is True
        and observation.get("live_model_identity_verified") is True)
    base["unverified_legal_support"] = True
    return base


EFFECT_ACCEPTANCE_SCHEMA = "hook_effect_acceptance_v1"
EFFECT_RECEIPT_SCHEMA = "hook_effect_receipt_v1"
CANDIDATE_ACQUISITION_SCHEMA = "hook_candidate_acquisition_v1"
_EFFECT_RECORD_KINDS = frozenset({"source", "evidence", "support"})


def saved_case_hash(saved_case: Mapping[str, Any] | None) -> str:
    """Identity of the saved case document. Not a durability or proof claim."""

    if saved_case is None:
        return _canonical_hash(None, prefix="case_")
    if not isinstance(saved_case, Mapping):
        raise HookContextError("malformed")
    return _canonical_hash(dict(saved_case), prefix="case_")


def receipt_establishes_durability(receipt: Mapping[str, Any] | None) -> bool:
    """A receipt record is not evidence that the effect was durably stored."""

    del receipt
    return False


def receipt_establishes_proof(receipt: Mapping[str, Any] | None) -> bool:
    """A receipt record does not prove a legal requirement or admitted support."""

    del receipt
    return False


def _inquiry_token(inquiry: Any) -> Optional[str]:
    if inquiry is None:
        return None
    if not isinstance(inquiry, Mapping):
        raise HookContextError("malformed")
    inquiry_id = inquiry.get("inquiry_id")
    revision = inquiry.get("revision")
    if inquiry_id is None and revision is None:
        return None
    if type(inquiry_id) is not str or type(revision) is not int:
        raise HookContextError("malformed")
    return f"{inquiry_id}|{revision}"


def _normalize_effect_records(records: Sequence[Mapping[str, Any]] | None) -> tuple[dict[str, str], ...]:
    if records is None:
        return ()
    if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
        raise HookContextError("malformed")
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in records:
        if not isinstance(item, Mapping):
            raise HookContextError("malformed")
        _reject_secret_fields(item)
        kind = item.get("kind")
        if type(kind) is not str or kind not in _EFFECT_RECORD_KINDS:
            raise HookContextError("malformed")
        source_id = _require_token(item.get("source_id"), code="malformed")
        content_hash = item.get("content_hash")
        if type(content_hash) is not str or len(content_hash) != 64:
            raise HookContextError("malformed")
        try:
            int(content_hash, 16)
        except ValueError as exc:
            raise HookContextError("malformed") from exc
        record_id = item.get("record_id")
        if record_id is None:
            record_id = _canonical_hash(
                {"kind": kind, "source_id": source_id, "content_hash": content_hash},
                prefix=kind[:3] + "_",
            )
        else:
            record_id = _require_token(str(record_id) if type(record_id) is str else record_id, code="malformed")
        identity = (kind, record_id)
        if identity in seen:
            continue
        seen.add(identity)
        normalized.append({
            "kind": kind,
            "record_id": record_id,
            "source_id": source_id,
            "content_hash": content_hash,
        })
    normalized.sort(key=lambda row: (row["kind"], row["record_id"]))
    return tuple(normalized)


def _graph_effect_fingerprint(graph: Any) -> str:
    metadata = getattr(graph, "metadata", None)
    ledger = metadata.get("factual_ledger") if isinstance(metadata, Mapping) else None
    if not isinstance(ledger, Mapping):
        ledger = {}
    payload = {
        "revisions": list(ledger.get("revisions") or []),
        "hook_effect_records": dict(ledger.get("hook_effect_records") or {}),
        "answer_events": sorted((ledger.get("answer_events") or {}).keys()) if isinstance(ledger.get("answer_events"), Mapping) else [],
        "entities": sorted((getattr(graph, "entities", {}) or {}).keys()),
        "relationships": sorted((getattr(graph, "relationships", {}) or {}).keys()),
    }
    return _canonical_hash(payload, prefix="gf_")


def _candidate_acquisition(
    *,
    operation: str,
    request_id: str,
    source_preimage: str,
    context_preimage: str,
    records: Sequence[Mapping[str, str]],
    status: str,
) -> dict[str, Any]:
    acquisition_id = _canonical_hash(
        {
            "operation": operation,
            "request_id": request_id,
            "source_preimage": source_preimage,
            "context_preimage": context_preimage,
            "records": [dict(row) for row in records],
            "status": status,
        },
        prefix="acq_",
    )
    return {
        "schema": CANDIDATE_ACQUISITION_SCHEMA,
        "acquisition_id": acquisition_id,
        "operation": operation,
        "request_id": request_id,
        "source_preimage": source_preimage,
        "context_preimage": context_preimage,
        "candidate_status": status,
        "source_count": sum(1 for row in records if row["kind"] == "source"),
        "evidence_count": sum(1 for row in records if row["kind"] == "evidence"),
        "support_count": sum(1 for row in records if row["kind"] == "support"),
        "admitted": False,
        "durable": False,
        "proof": False,
        "proof_status": "not_proof",
    }


def _remember_candidate(log: list | None, candidate: Mapping[str, Any]) -> None:
    if log is None:
        return
    acquisition_id = candidate.get("acquisition_id")
    for item in log:
        if isinstance(item, Mapping) and item.get("acquisition_id") == acquisition_id:
            return
    log.append(dict(candidate))


def _refusal(
    *,
    code: str,
    candidate: Mapping[str, Any],
    operation: str,
    request_id: str,
    source_preimage: str,
    context_preimage: str,
    graph_revision: str,
    graph_fingerprint: str,
    pending_fingerprint: str,
    case_fingerprint: str,
    graph: Any,
    pending_inquiry: Any,
    saved_case: Any,
) -> dict[str, Any]:
    receipt = {
        "schema": EFFECT_RECEIPT_SCHEMA,
        "accepted": False,
        "code": code,
        "operation": operation,
        "request_id": request_id,
        "source_preimage": source_preimage,
        "context_preimage": context_preimage,
        "accepted_graph_revision": graph_revision,
        "revision_index": None,
        "source_ids": [],
        "evidence_ids": [],
        "support_ids": [],
        "durable": False,
        "proof": False,
        "proof_status": "not_proof",
    }
    return {
        "schema": EFFECT_ACCEPTANCE_SCHEMA,
        "accepted": False,
        "code": code,
        "idempotent_replay": False,
        "candidate_acquisition": dict(candidate),
        "effect_receipt": receipt,
        "mutated_graph": _graph_effect_fingerprint(graph) != graph_fingerprint,
        "mutated_pending_inquiry": _canonical_hash(pending_inquiry, prefix="inq_") != pending_fingerprint,
        "mutated_saved_case": _canonical_hash(saved_case, prefix="casebody_") != case_fingerprint,
    }


def _payload_mismatch_code(existing_payload: Mapping[str, Any], source_preimage: str, context_preimage: str, graph_revision: str) -> str:
    context = existing_payload.get("source_context") if isinstance(existing_payload.get("source_context"), Mapping) else {}
    if context.get("source_preimage") != source_preimage:
        return "source_preimage_changed"
    if context.get("context_preimage") != context_preimage:
        return "context_preimage_changed"
    if context.get("graph_revision") != graph_revision:
        return "stale_revision"
    return "effect_conflict"


def accept_bound_hook_effect(
    *,
    context: HookExecutionContext | None,
    graph: Any,
    source_bindings: Sequence[Mapping[str, Any]] | None,
    legal_context: Mapping[str, Any] | None,
    request_id: Any,
    records: Sequence[Mapping[str, Any]] | None = None,
    pending_inquiry: Any = None,
    saved_case: Mapping[str, Any] | None = None,
    bound_pending_inquiry: Any = None,
    bound_saved_case_hash: str | None = None,
    result_state: str = "active",
    storage_available: bool = True,
    acquisition_log: list | None = None,
) -> dict[str, Any]:
    """Admit one hook effect once, bound to the current preimages and graph revision.

    Candidate acquisition is recorded on ``acquisition_log`` only. It is not an
    admitted source, evidence, or support record. An effect receipt does not
    establish durability or proof. Replay of the same request, preimages, and
    accepted graph revision returns the stored admission. A changed preimage,
    stale revision, cancelled result, or stale result does not mutate the graph,
    the pending inquiry, or the saved case.
    """

    from complaint_phases.knowledge_graph import answer_event_fingerprint, answer_event_payload

    operation = context.operation if isinstance(context, HookExecutionContext) else ""
    request_token = request_id if type(request_id) is str else ""
    source_preimage = ""
    context_preimage = ""
    graph_revision = context.graph_revision if isinstance(context, HookExecutionContext) else ""
    if graph is None or not hasattr(graph, "factual_ledger") or not hasattr(graph, "append_revision"):
        candidate = _candidate_acquisition(
            operation=operation,
            request_id=request_token,
            source_preimage="",
            context_preimage="",
            records=(),
            status="unavailable",
        )
        _remember_candidate(acquisition_log, candidate)
        receipt = _refusal(
            code="graph_unavailable",
            candidate=candidate,
            operation=operation,
            request_id=request_token,
            source_preimage="",
            context_preimage="",
            graph_revision=graph_revision,
            graph_fingerprint=_graph_effect_fingerprint(graph),
            pending_fingerprint=_canonical_hash(pending_inquiry, prefix="inq_"),
            case_fingerprint=_canonical_hash(saved_case, prefix="casebody_"),
            graph=graph,
            pending_inquiry=pending_inquiry,
            saved_case=saved_case,
        )
        receipt["mutated_graph"] = False
        receipt["mutated_pending_inquiry"] = False
        receipt["mutated_saved_case"] = False
        return receipt

    graph_fingerprint = _graph_effect_fingerprint(graph)
    pending_fingerprint = _canonical_hash(pending_inquiry, prefix="inq_")
    case_fingerprint = _canonical_hash(saved_case, prefix="casebody_")

    def refuse(code: str, candidate: Mapping[str, Any]) -> dict[str, Any]:
        _remember_candidate(acquisition_log, candidate)
        return _refusal(
            code=code,
            candidate=candidate,
            operation=operation,
            request_id=request_token,
            source_preimage=source_preimage,
            context_preimage=context_preimage,
            graph_revision=graph_revision,
            graph_fingerprint=graph_fingerprint,
            pending_fingerprint=pending_fingerprint,
            case_fingerprint=case_fingerprint,
            graph=graph,
            pending_inquiry=pending_inquiry,
            saved_case=saved_case,
        )

    if not isinstance(context, HookExecutionContext):
        candidate = _candidate_acquisition(
            operation="", request_id=request_token, source_preimage="", context_preimage="", records=(), status="failed",
        )
        return refuse("binding_missing", candidate)
    try:
        request_token = _require_token(request_id, code="malformed")
        rows = normalize_source_bindings(source_bindings)
        source_preimage = source_binding_hash(rows)
        legal_id = legal_context_identity(legal_context)
        context_preimage = context_binding_hash(
            legal_context_id=legal_id,
            owner_id=context.owner_id,
            case_id=context.case_id,
            session_id=context.session_id,
        )
        effect_records = _normalize_effect_records(records)
        if bound_saved_case_hash is not None and not isinstance(saved_case, Mapping) and saved_case is not None:
            raise HookContextError("malformed")
        current_inquiry = _inquiry_token(pending_inquiry)
        bound_inquiry = None if bound_pending_inquiry is None else _inquiry_token(bound_pending_inquiry)
    except HookContextError as exc:
        candidate = _candidate_acquisition(
            operation=operation,
            request_id=request_id if type(request_id) is str else "",
            source_preimage=source_preimage,
            context_preimage=context_preimage,
            records=(),
            status="failed",
        )
        return refuse(exc.code, candidate)

    candidate_status = "acquired" if effect_records else "empty"
    candidate = _candidate_acquisition(
        operation=operation,
        request_id=request_token,
        source_preimage=source_preimage,
        context_preimage=context_preimage,
        records=effect_records,
        status=candidate_status,
    )
    if source_preimage != context.source_binding_hash:
        return refuse("source_preimage_changed", candidate)
    if context_preimage != context.context_binding_hash or legal_id != context.legal_context_id:
        return refuse("context_preimage_changed", candidate)
    if storage_available is not True:
        failed = dict(candidate)
        failed["candidate_status"] = "unavailable"
        return refuse("storage_unavailable", failed)
    state = result_state if type(result_state) is str else "malformed"
    if state == "cancelled":
        return refuse("cancelled", candidate)
    if state == "stale":
        return refuse("stale_result", candidate)
    if state == "timeout":
        failed = dict(candidate)
        failed["candidate_status"] = "failed"
        return refuse("timeout", failed)
    if state != "active":
        return refuse("malformed", candidate)
    if bound_pending_inquiry is not None and current_inquiry != bound_inquiry:
        return refuse("stale_inquiry", candidate)
    if bound_saved_case_hash is not None:
        try:
            current_case_hash = saved_case_hash(saved_case if isinstance(saved_case, Mapping) else None)
        except HookContextError as exc:
            return refuse(exc.code, candidate)
        if current_case_hash != bound_saved_case_hash:
            return refuse("stale_case", candidate)

    record_ids = {
        "source": [row["record_id"] for row in effect_records if row["kind"] == "source"],
        "evidence": [row["record_id"] for row in effect_records if row["kind"] == "evidence"],
        "support": [row["record_id"] for row in effect_records if row["kind"] == "support"],
    }
    payload = answer_event_payload(
        question=operation,
        answer=request_token,
        source_context={
            "source_preimage": source_preimage,
            "context_preimage": context_preimage,
            "graph_revision": context.graph_revision,
            "records": [dict(row) for row in effect_records],
        },
    )
    event_id = f"hook-effect:{operation}:{request_token}"
    ledger = graph.factual_ledger()
    events = ledger.get("answer_events") or {}
    existing = events.get(event_id) if isinstance(events, Mapping) else None
    if isinstance(existing, Mapping):
        if existing.get("fingerprint") == answer_event_fingerprint(payload):
            stored = existing.get("stored_acceptance")
            if isinstance(stored, Mapping) and isinstance(stored.get("effect_receipt"), Mapping):
                _remember_candidate(acquisition_log, stored.get("candidate_acquisition") or candidate)
                return {
                    "schema": EFFECT_ACCEPTANCE_SCHEMA,
                    "accepted": True,
                    "code": "accepted",
                    "idempotent_replay": True,
                    "candidate_acquisition": dict(stored.get("candidate_acquisition") or candidate),
                    "effect_receipt": dict(stored["effect_receipt"]),
                    "mutated_graph": _graph_effect_fingerprint(graph) != graph_fingerprint,
                    "mutated_pending_inquiry": _canonical_hash(pending_inquiry, prefix="inq_") != pending_fingerprint,
                    "mutated_saved_case": _canonical_hash(saved_case, prefix="casebody_") != case_fingerprint,
                }
        else:
            existing_payload = existing.get("payload") if isinstance(existing.get("payload"), Mapping) else {}
            return refuse(
                _payload_mismatch_code(existing_payload, source_preimage, context_preimage, context.graph_revision),
                candidate,
            )

    current_revision = graph_revision_token(graph)
    if current_revision != context.graph_revision:
        return refuse("stale_revision", candidate)

    receipt = {
        "schema": EFFECT_RECEIPT_SCHEMA,
        "accepted": True,
        "code": "accepted",
        "effect_id": event_id,
        "operation": operation,
        "request_id": request_token,
        "source_preimage": source_preimage,
        "context_preimage": context_preimage,
        "accepted_graph_revision": context.graph_revision,
        "revision_index": None,
        "source_ids": list(record_ids["source"]),
        "evidence_ids": list(record_ids["evidence"]),
        "support_ids": list(record_ids["support"]),
        "durable": False,
        "proof": False,
        "proof_status": "not_proof",
    }
    revision = graph.append_revision({
        "action": "hook_effect",
        "event_id": event_id,
        "source_preimage": source_preimage,
        "context_preimage": context_preimage,
        "accepted_graph_revision": context.graph_revision,
        "source_ids": list(record_ids["source"]),
        "evidence_ids": list(record_ids["evidence"]),
        "support_ids": list(record_ids["support"]),
    })
    receipt["revision_index"] = revision.get("revision_index")
    admitted = graph.factual_ledger().setdefault("hook_effect_records", {})
    admitted[event_id] = [dict(row) for row in effect_records]
    stored_acceptance = {
        "candidate_acquisition": dict(candidate),
        "effect_receipt": dict(receipt),
    }
    graph.finish_answer_event(event_id, payload, stored_acceptance=stored_acceptance)
    _remember_candidate(acquisition_log, candidate)
    return {
        "schema": EFFECT_ACCEPTANCE_SCHEMA,
        "accepted": True,
        "code": "accepted",
        "idempotent_replay": False,
        "candidate_acquisition": dict(candidate),
        "effect_receipt": dict(receipt),
        "mutated_graph": True,
        "mutated_pending_inquiry": _canonical_hash(pending_inquiry, prefix="inq_") != pending_fingerprint,
        "mutated_saved_case": _canonical_hash(saved_case, prefix="casebody_") != case_fingerprint,
    }


PUBLIC_ADVERSE_OUTCOMES = (
    "malformed_model_proposal",
    "late_model_proposal",
    "consent_revocation",
    "wrong_key",
    "legal_source_outage",
    "interrupted_snapshot",
    "corrupt_replica",
)

_ADVERSE_DEADLINE_CAP_SECONDS = 60.0


def bounded_deadline_seconds(value: Any, *, default: float = 5.0) -> float:
    """Clamp a caller deadline. Non-finite or non-positive values use the default."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if number != number or number in {float("inf"), float("-inf")} or number <= 0:
        number = default
    if number > _ADVERSE_DEADLINE_CAP_SECONDS:
        number = _ADVERSE_DEADLINE_CAP_SECONDS
    return number


class OwnedProcessGuard:
    """Track child processes this operation started and reap only those.

    Cleanup signals the process group of each child this guard spawned.
    It does not scan or signal any other process, and it does not open a socket.
    """

    def __init__(self, deadline_seconds: float) -> None:
        import time

        self.deadline_seconds = bounded_deadline_seconds(deadline_seconds)
        self._deadline = time.monotonic() + self.deadline_seconds
        self._started = time.monotonic()
        self._processes: list[Any] = []
        self.pids: list[int] = []
        self.reaped: list[int] = []
        self.status = "not_started"
        self.network_touched = False
        self.provider_process_started = False

    def expired(self) -> bool:
        import time

        return time.monotonic() >= self._deadline

    def elapsed_seconds(self) -> float:
        import time

        return max(0.0, time.monotonic() - self._started)

    def spawn_owned_idle_child(self) -> Optional[int]:
        """Start one local idle interpreter. Failure is an asserted capability gap."""

        import subprocess
        import sys

        if self.expired():
            self.status = "deadline_elapsed"
            return None
        try:
            process = subprocess.Popen(
                [sys.executable, "-I", "-c", "import time; time.sleep(30)"],
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            self.status = "unavailable"
            return None
        self._processes.append(process)
        self.pids.append(int(process.pid))
        self.status = "running"
        return int(process.pid)

    def cleanup(self) -> dict[str, Any]:
        """Reap owned children. A missing spawn stays an explicit unavailable status."""

        import subprocess

        for process in self._processes:
            pid = int(process.pid)
            if process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1.0)
            if pid not in self.reaped:
                self.reaped.append(pid)
        if self.status == "running":
            self.status = "reaped" if self.reaped == self.pids and self.pids else "unavailable"
        elif self.status == "not_started":
            self.status = "unavailable"
        return self.public_view()

    def public_view(self) -> dict[str, Any]:
        return {
            "deadline_seconds": self.deadline_seconds,
            "elapsed_seconds": self.elapsed_seconds(),
            "within_deadline": self.elapsed_seconds() <= self.deadline_seconds,
            "pids": list(self.pids),
            "reaped": list(self.reaped),
            "status": self.status,
            "spawned": len(self.pids),
            "provider_process_started": False,
            "network_touched": False,
            "unrelated_processes_signaled": False,
        }


def reject_public_model_proposal(proposal: Any) -> dict[str, Any]:
    """Refuse a model proposal before any effect, graph write, or provider call.

    Malformed proposals and proposals that claim legal completion stay refused.
    The caller keeps the last graph revision and pending inquiry.
    """

    request = {
        "operation": "acquire_legal_sources",
        "model_proposal": proposal,
    }
    decision = dispatch_registered_hook_operation(
        request,
        context=None,
        host_targets=(),
        owner_id="",
        case_id="",
        session_id="",
        session_revision=0,
        graph_revision="",
        legal_context=None,
        purpose=None,
        source_bindings=None,
        privacy_context=None,
        now=datetime.now(timezone.utc),
        host=None,
    )
    code = str(decision.get("code") or "malformed")
    return {
        "accepted": False,
        "code": code,
        "status": "refused",
        "legal_completion": False,
        "proof": False,
        "legal_sufficiency": False,
        "requirements_satisfied": False,
        "backend_completed": False,
        "provider_invoked": False,
        "effect_dispatched": False,
        "resume_possible": True,
        "nonrecoverable_boundary": None,
        "next_action": "continue_pending_inquiry",
        "operation": decision.get("operation") or "acquire_legal_sources",
    }


def qualify_private_evidence_hooks(**kwargs: Any) -> dict[str, Any]:
    """Public workflow entry for scoped evidence storage, state, and analysis.

    The effect is the Kit commit plus the dataset chunk metadata owner.
    A caller flag cannot turn a missing Kit or a refused consent into success.
    """

    from mediator.evidence_hooks import qualify_scoped_private_evidence

    receipt = qualify_scoped_private_evidence(**kwargs)
    receipt["workflow"] = "qualify_private_evidence_hooks"
    receipt["handler_enabled_by_caller"] = False
    return receipt
