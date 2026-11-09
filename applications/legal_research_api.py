"""Bounded legal-source candidate acquisition for one authorized case.

The route is mounted by ``compose_case_routes``. Session and case-action checks
run before these handlers. Acquisition goes through the bound mediator's
``build_legal_acquisition_request`` and ``legal_authority_search`` owners.
Search hits, snippets, missing archives, and model text stay candidates or
research gaps. A later explicit review by the case owner or an assigned
lawyer can admit one versioned passage only when every stored source field
matches. This module does not claim WebSocket or SSE support.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Dict, Mapping, MutableMapping

from starlette.requests import Request

TASK_ID = "CIMP-GUI-25"
LEGAL_RESEARCH_PREFIX = "/api/legal-research"
PURPOSES = ("citation_acquisition", "public_law_citation")
RETRIEVAL_MODES = ("cache", "offline", "live")
LOCAL_MODES = ("cache", "offline")
ADMISSION_TASK_ID = "CIMP-GUI-26"
AUTHORIZED_ADMISSION_MEMBERSHIPS = frozenset({"owner", "assigned-lawyer"})
APPLICABILITY_VALUES = frozenset({"applicable", "inapplicable", "limited"})
TREATMENT_STATES = frozenset({"good_law", "distinguished", "overruled", "questioned", "superseded"})
PASSAGE_MAX_CHARS = 8192
QUERY_MAX_CHARS = 256
RESULT_CAP = 5
TIMEOUT_CAP_SECONDS = 5.0
BYTE_CAP = 4096
_GAP_REASONS = {
    "snippet": "snippet_not_law",
    "snippet_only": "snippet_not_law",
    "model_text": "model_text_not_law",
    "missing_archive": "missing_archive",
    "archive_missing": "missing_archive",
}


class LegalResearchError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def legal_research_http_status(code: str) -> int:
    if code == "unauthenticated":
        return 401
    if code in {"consent_revision_conflict", "legal_research_revision_conflict"}:
        return 409
    if code in {"legal_research_bounds", "legal_research_field", "purpose_not_allowed"}:
        return 422
    if code in {"acquisition_unavailable", "research_hook_unavailable", "legal_corpus_unavailable", "legal_research_unavailable", "unlock_needed"}:
        return 503
    return 403


def _case_file_from_mediator(mediator: Any) -> MutableMapping[str, Any]:
    phase_manager = getattr(mediator, "phase_manager", None)
    if phase_manager is not None and hasattr(phase_manager, "get_phase_data"):
        from complaint_phases.phase_manager import ComplaintPhase

        stored = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file")
        if isinstance(stored, dict):
            return stored
    stored = getattr(mediator, "intake_case_file", None)
    if isinstance(stored, dict):
        return stored
    raise LegalResearchError("legal_research_unavailable")


def _purpose_decision(view: Mapping[str, Any], purpose: str) -> Dict[str, Any]:
    rows = view.get("decisions")
    if isinstance(rows, list):
        matches = [item for item in rows if isinstance(item, dict) and item.get("purpose") == purpose]
    elif isinstance(rows, dict) and isinstance(rows.get(purpose), dict):
        matches = [rows[purpose]]
    else:
        matches = []
    if len(matches) != 1:
        raise LegalResearchError("purpose_consent_required")
    return matches[0]


def _require_purpose_consent(authority: Any, workspace: Any, purpose: str, expected_generation: int, retrieval_mode: str) -> Dict[str, Any]:
    try:
        view = authority.processing_consent(
            purpose=purpose,
            actor_principal_id=authority.actor_principal_id,
            workspace=workspace,
        )
    except LegalResearchError:
        raise
    except Exception as exc:
        code = str(getattr(exc, "code", "") or "")
        if code in {"consent_revoked", "purpose_consent_required", "case_purpose_consent_required"}:
            raise LegalResearchError("purpose_consent_required") from exc
        raise LegalResearchError("purpose_consent_required") from exc
    if not isinstance(view, dict):
        raise LegalResearchError("purpose_consent_required")
    choice = _purpose_decision(view, purpose)
    generation = choice.get("generation")
    if type(generation) is not int or isinstance(generation, bool) or generation < 1:
        raise LegalResearchError("purpose_consent_required")
    if generation != expected_generation:
        raise LegalResearchError("consent_revision_conflict")
    if retrieval_mode == "live":
        if choice.get("egress_authorized") is not True or choice.get("revoked") is True or choice.get("explicit") is not True:
            raise LegalResearchError("purpose_consent_required")
    elif choice.get("revoked") is True and choice.get("mode") not in {None, "", "local_private"}:
        raise LegalResearchError("consent_revoked")
    return {
        "purpose": purpose,
        "generation": generation,
        "mode": choice.get("mode") or "local_private",
        "egress_authorized": choice.get("egress_authorized") is True,
        "data_class": choice.get("data_class") or "public_legal_source_graph",
        "revoked": choice.get("revoked") is True,
    }


def _bounds(body: Mapping[str, Any]) -> Dict[str, Any]:
    purpose = body.get("purpose")
    if purpose not in PURPOSES:
        raise LegalResearchError("purpose_not_allowed")
    query = body.get("query")
    if not isinstance(query, str) or not query.strip() or len(query) > QUERY_MAX_CHARS or query != query.strip():
        raise LegalResearchError("legal_research_bounds")
    max_results = body.get("max_results", RESULT_CAP)
    if type(max_results) is not int or isinstance(max_results, bool) or not 1 <= max_results <= RESULT_CAP:
        raise LegalResearchError("legal_research_bounds")
    deadline = body.get("deadline_seconds", TIMEOUT_CAP_SECONDS)
    if isinstance(deadline, bool) or not isinstance(deadline, (int, float)):
        raise LegalResearchError("legal_research_bounds")
    deadline_seconds = float(deadline)
    if not deadline_seconds > 0 or deadline_seconds > TIMEOUT_CAP_SECONDS:
        raise LegalResearchError("legal_research_bounds")
    max_bytes = body.get("max_bytes", BYTE_CAP)
    if type(max_bytes) is not int or isinstance(max_bytes, bool) or not 1 <= max_bytes <= BYTE_CAP:
        raise LegalResearchError("legal_research_bounds")
    retrieval_mode = body.get("retrieval_mode", "cache")
    if retrieval_mode not in RETRIEVAL_MODES:
        raise LegalResearchError("legal_research_bounds")
    expected = body.get("expected_consent_generation")
    if type(expected) is not int or isinstance(expected, bool) or expected < 0:
        raise LegalResearchError("legal_research_field")
    operation_id = body.get("operation_id", "")
    if not isinstance(operation_id, str) or len(operation_id) > 64:
        raise LegalResearchError("legal_research_field")
    if body.get("cancelled") not in {True, False, None}:
        raise LegalResearchError("legal_research_field")
    local_rows = body.get("local_rows")
    if local_rows is not None and not isinstance(local_rows, dict):
        raise LegalResearchError("legal_research_field")
    if isinstance(local_rows, dict) and len(json.dumps(local_rows, default=str)) > BYTE_CAP:
        raise LegalResearchError("legal_research_bounds")
    return {
        "purpose": purpose,
        "query": query,
        "max_results": max_results,
        "deadline_seconds": deadline_seconds,
        "max_bytes": max_bytes,
        "retrieval_mode": retrieval_mode,
        "expected_consent_generation": expected,
        "operation_id": operation_id,
        "cancelled": body.get("cancelled") is True,
        "local_rows": local_rows,
    }


def _gap(reason: str, *, source_id: str = "", version: str = "", locator: str = "") -> Dict[str, Any]:
    return {
        "kind": "research_gap",
        "reason": reason,
        "admitted_law": False,
        "proof": False,
        "support_eligible": False,
        "applicable": False,
        "source_id": source_id,
        "version": version,
        "locator": locator,
        "content_hash": "",
    }


def _candidate_receipt(item: Mapping[str, Any]) -> Dict[str, Any]:
    retrieval = item.get("retrieval") if isinstance(item.get("retrieval"), dict) else {}
    version = str(item.get("version") or item.get("authority_version") or retrieval.get("corpus_version") or "")
    locator = str(item.get("locator") or "")
    source_id = str(item.get("source_id") or retrieval.get("corpus_id") or locator or "")
    content_hash = str(retrieval.get("content_hash") or item.get("content_hash") or "")
    passage_status = str(item.get("passage_status") or "")
    archive_status = str(item.get("archive_status") or item.get("archive") or "")
    if item.get("model_text") or item.get("model_inference_used") is True or passage_status == "model_text":
        return _gap("model_text_not_law", source_id=source_id, version=version, locator=locator)
    if item.get("snippet") or passage_status in {"snippet", "snippet_only"}:
        return _gap("snippet_not_law", source_id=source_id, version=version, locator=locator)
    if archive_status in {"missing", "missing_archive", "archive_missing"} or item.get("archive_missing") is True:
        return _gap("missing_archive", source_id=source_id, version=version, locator=locator)
    source_text = item.get("source_text") if isinstance(item.get("source_text"), str) else ""
    if not source_text or not version.strip() or not locator:
        reason = "source_text_missing" if not source_text else "source_version_missing"
        return _gap(reason, source_id=source_id, version=version, locator=locator)
    if not content_hash:
        content_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    passage = _passage_index_record(item, source_text=source_text, version=version.strip(), content_hash=content_hash, source_id=source_id, locator=locator)
    return {
        "kind": "candidate",
        "reason": "",
        "admitted_law": False,
        "proof": False,
        "support_eligible": False,
        "applicable": False,
        "source_id": source_id,
        "version": version.strip(),
        "locator": locator,
        "locator_kind": str(item.get("locator_kind") or ""),
        "content_hash": content_hash,
        "source_family": str(item.get("source_family") or retrieval.get("source_family") or ""),
        "byte_length": len(source_text.encode("utf-8")),
        "source_passage": passage["source_passage"],
        "authority_identity": passage["authority_identity"],
        "jurisdiction": passage["jurisdiction"],
        "effective_date": passage["effective_date"],
        "stated_applicability": passage["applicability"],
        "exceptions": list(passage["exceptions"]) if isinstance(passage["exceptions"], list) else None,
        "treatment_state": passage["treatment_state"],
        "version_state": passage["version_state"],
    }


def _string_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if not isinstance(value, list) or len(value) > 32:
        return None
    rows = []
    for item in value:
        if not isinstance(item, str) or item != item.strip() or not item or len(item) > 256:
            return None
        rows.append(item)
    return rows


def _passage_index_record(item: Mapping[str, Any], *, source_text: str, version: str, content_hash: str, source_id: str, locator: str) -> Dict[str, Any]:
    current = str(item.get("current_version") or item.get("current_authority_version") or "")
    version_state = str(item.get("version_state") or "")
    stale = version_state == "stale" or item.get("stale") is True or bool(current and current != version)
    identity = str(item.get("authority_identity") or item.get("authority_id") or locator or "")
    exceptions = _string_list(item.get("exceptions"))
    applicability = item.get("applicability") if isinstance(item.get("applicability"), str) else ""
    treatment = item.get("treatment_state") if isinstance(item.get("treatment_state"), str) else "unknown"
    retrieval = item.get("retrieval") if isinstance(item.get("retrieval"), Mapping) else {}
    passage = source_text if len(source_text) <= PASSAGE_MAX_CHARS else ""
    return {
        "source_passage": passage,
        "authority_identity": identity,
        "jurisdiction": str(item.get("jurisdiction") or ""),
        "effective_date": str(item.get("effective_date") or retrieval.get("effective_date") or ""),
        "applicability": applicability,
        "exceptions": exceptions,
        "treatment_state": treatment,
        "version": version,
        "current_version": current,
        "version_state": "stale" if stale else "current",
        "content_hash": content_hash,
        "source_id": source_id,
        "locator": locator,
    }


def _index_acquired_passages(case_file: MutableMapping[str, Any], acquisition: Mapping[str, Any], *, acquisition_context=None) -> None:
    index = case_file.get("legal_source_passage_index")
    if not isinstance(index, dict):
        index = {}
        case_file["legal_source_passage_index"] = index
    raw_candidates = acquisition.get("candidates") if isinstance(acquisition.get("candidates"), list) else []
    for item in raw_candidates:
        if not isinstance(item, dict):
            continue
        receipt = _candidate_receipt(item)
        if receipt.get("kind") != "candidate":
            continue
        content_hash = str(receipt.get("content_hash") or "")
        if not content_hash or not receipt.get("source_passage"):
            continue
        if content_hash not in index and len(index) >= 256:
            raise LegalResearchError("legal_research_bounds")
        index[content_hash] = {
            **deepcopy(item),
            "source_passage": receipt["source_passage"],
            "authority_identity": receipt["authority_identity"],
            "jurisdiction": receipt["jurisdiction"],
            "effective_date": receipt["effective_date"],
            "applicability": receipt["stated_applicability"],
            "exceptions": list(receipt["exceptions"]) if isinstance(receipt["exceptions"], list) else None,
            "treatment_state": receipt["treatment_state"],
            "version": receipt["version"],
            "current_version": str(item.get("current_version") or item.get("current_authority_version") or ""),
            "version_state": receipt["version_state"],
            "content_hash": content_hash,
            "source_id": receipt["source_id"],
            "locator": receipt["locator"],
            # Presentation fields never replace the owned admission record.
            "canonical_source": deepcopy(item),
            "acquisition_context": deepcopy(acquisition_context),
        }


def _project_acquisition(acquisition: Mapping[str, Any], *, bounds: Mapping[str, Any], consent: Mapping[str, Any], replayed: bool) -> Dict[str, Any]:
    raw_candidates = acquisition.get("candidates") if isinstance(acquisition.get("candidates"), list) else []
    receipts = [_candidate_receipt(item) for item in raw_candidates if isinstance(item, dict)]
    for operation in acquisition.get("operations") or []:
        if not isinstance(operation, dict):
            continue
        status = str(operation.get("status") or "")
        error_code = str(operation.get("error_code") or "")
        if status in {"missing_edition", "incomplete", "empty", "unavailable", "timeout", "error"} or error_code in _GAP_REASONS:
            receipts.append(_gap(
                _GAP_REASONS.get(error_code, error_code or status or "research_gap"),
                source_id=str(operation.get("source_family") or ""),
                version=str(operation.get("version") or ""),
            ))
        for withheld in operation.get("withheld") or []:
            if isinstance(withheld, dict):
                reason = str(withheld.get("reason") or "research_gap")
                receipts.append(_gap(reason, source_id=str(operation.get("source_family") or "")))
    for receipt in receipts:
        receipt["admitted_law"] = False
        receipt["proof"] = False
    status = str(acquisition.get("status") or "unavailable")
    if bounds.get("cancelled"):
        status = "cancelled"
    return {
        "task_id": TASK_ID,
        "action": "legal_source_candidates",
        "admitted_law": False,
        "proof": False,
        "legal_sufficiency": False,
        "stored_as_answer": False,
        "status": status,
        "error_code": "cancelled" if bounds.get("cancelled") else str(acquisition.get("error_code") or ""),
        "replayed": replayed,
        "dispatched": not replayed,
        "cancelled": bool(bounds.get("cancelled")),
        "purpose": consent.get("purpose"),
        "consent_generation": consent.get("generation"),
        "retrieval_mode": bounds.get("retrieval_mode"),
        "bounds": {
            "max_results": bounds.get("max_results"),
            "deadline_seconds": bounds.get("deadline_seconds"),
            "max_bytes": bounds.get("max_bytes"),
            "query_chars": len(str(bounds.get("query") or "")),
        },
        "source_version_receipts": receipts,
        "candidate_count": sum(1 for item in receipts if item.get("kind") == "candidate"),
        "research_gap_count": sum(1 for item in receipts if item.get("kind") == "research_gap"),
        "model_inference_used": False,
        "limitations": [
            "Search results, snippets, missing archives, and model text are candidates or research gaps.",
            "Nothing returned by this route is admitted law.",
            "WebSocket and SSE transports are not supported.",
        ],
    }


def acquire_bounded_legal_sources(mediator: Any, workspace: Any, authority: Any, body: Mapping[str, Any], *, source_scope_sha256="") -> Dict[str, Any]:
    """Invoke the bound research hook once. Results are never admitted law."""
    if not isinstance(body, Mapping):
        raise LegalResearchError("legal_research_field")
    bounds = _bounds(body)
    consent = _require_purpose_consent(
        authority,
        workspace,
        bounds["purpose"],
        bounds["expected_consent_generation"],
        bounds["retrieval_mode"],
    )
    case_file = _case_file_from_mediator(mediator)
    seen = case_file.get("legal_source_operations")
    if not isinstance(seen, dict):
        if seen is not None:
            raise LegalResearchError("legal_research_revision_conflict")
        seen = {}
        case_file["legal_source_operations"] = seen
    operation_id = bounds["operation_id"]
    fingerprint = _operation_fingerprint({
        "request": bounds, "actor": authority.actor_principal_id,
        "case_id": authority.case_id, "legal_context": None if source_scope_sha256 else case_file.get("legal_context"),
        "source_scope_sha256": source_scope_sha256,
    })
    if operation_id and operation_id in seen:
        prior = seen[operation_id]
        if prior.get("fingerprint") != fingerprint:
            raise LegalResearchError("legal_research_revision_conflict")
        replay = deepcopy(prior["receipt"])
        replay["replayed"] = True
        replay["dispatched"] = False
        replay["admitted_law"] = False
        return replay
    if operation_id and len(seen) >= 256:
        raise LegalResearchError("legal_research_bounds")
    builder = getattr(mediator, "build_legal_acquisition_request", None)
    search = getattr(mediator, "legal_authority_search", None)
    acquire = getattr(search, "acquire_bounded_canonical_sources", None)
    if not callable(builder) or not callable(acquire):
        raise LegalResearchError("research_hook_unavailable")
    binding = builder(
        case_file,
        query_terms=[bounds["query"]],
        max_results=bounds["max_results"],
        timeout_seconds=bounds["deadline_seconds"],
        storage_available=True,
    )
    acquisition = acquire(
        binding,
        owner_id=str(getattr(authority, "actor_principal_id", "") or ""),
        case_id=str(getattr(authority, "case_id", "") or ""),
        purpose=bounds["purpose"],
        data_class=consent["data_class"],
        provider_kind="local" if bounds["retrieval_mode"] in LOCAL_MODES else "legal_corpus",
        retrieval_mode=bounds["retrieval_mode"],
        local_rows=bounds["local_rows"],
        deadline_seconds=bounds["deadline_seconds"],
        max_bytes=bounds["max_bytes"],
        max_results=bounds["max_results"],
        cancelled=bounds["cancelled"],
    )
    if not isinstance(acquisition, dict):
        raise LegalResearchError("acquisition_unavailable")
    receipt = _project_acquisition(acquisition, bounds=bounds, consent=consent, replayed=False)
    if isinstance(binding, Mapping) and binding.get("ready") is False:
        receipt["context_required"] = {
            "selection_status": str(binding.get("selection_status") or "unknown"),
            "reason_codes": [str(item) for item in binding.get("unresolved_reasons", [])][:16],
        }
    receipt["operation_id"] = operation_id
    if not bounds["cancelled"]:
        _index_acquired_passages(case_file, acquisition, acquisition_context={
            "purpose": consent["purpose"], "consent_generation": consent["generation"],
            "source_scope_sha256": source_scope_sha256})
    case_file["legal_source_candidate_receipt"] = receipt
    if operation_id:
        seen[operation_id] = {"fingerprint": fingerprint, "request": deepcopy(bounds),
            "source_scope_sha256": source_scope_sha256, "receipt": deepcopy(receipt)}
    return receipt


def _admission_ledger(case_file: MutableMapping[str, Any]) -> list:
    ledger = case_file.get("legal_authority_admissions")
    if not isinstance(ledger, list):
        ledger = []
        case_file["legal_authority_admissions"] = ledger
    return ledger


def _operation_fingerprint(value: Mapping[str, Any]) -> str:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError):
        raise LegalResearchError("legal_research_field") from None
    return hashlib.sha256(raw).hexdigest()


def _review_fields(body: Mapping[str, Any]) -> Dict[str, Any]:
    decision = body.get("decision")
    if decision not in {"admit", "reject"}:
        raise LegalResearchError("legal_research_field")
    passage = body.get("source_passage")
    if not isinstance(passage, str) or len(passage) > PASSAGE_MAX_CHARS:
        raise LegalResearchError("legal_research_field")
    content_hash = body.get("content_hash")
    version = body.get("version")
    identity = body.get("authority_identity")
    jurisdiction = body.get("jurisdiction")
    effective_date = body.get("effective_date")
    applicability = body.get("applicability")
    treatment = body.get("treatment_state")
    for value in (content_hash, version, identity, jurisdiction, effective_date, applicability, treatment):
        if not isinstance(value, str) or len(value) > 256:
            raise LegalResearchError("legal_research_field")
    exceptions = _string_list(body.get("exceptions"))
    if exceptions is None and body.get("exceptions") is not None:
        raise LegalResearchError("legal_research_field")
    operation_id = body.get("operation_id", "")
    if not isinstance(operation_id, str) or len(operation_id) > 64:
        raise LegalResearchError("legal_research_field")
    claimed = body.get("reviewer_principal_id", "")
    if not isinstance(claimed, str) or len(claimed) > 128:
        raise LegalResearchError("legal_research_field")
    return {
        "decision": decision,
        "source_passage": passage,
        "content_hash": content_hash,
        "version": version,
        "authority_identity": identity,
        "jurisdiction": jurisdiction,
        "effective_date": effective_date,
        "applicability": applicability,
        "exceptions": exceptions,
        "treatment_state": treatment,
        "operation_id": operation_id,
        "reviewer_principal_id": claimed,
    }


def _admission_record(fields: Mapping[str, Any], *, status: str, reason: str, admitted: bool, attribution: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "task_id": ADMISSION_TASK_ID,
        "action": "review_versioned_authority",
        "status": status,
        "reason": reason,
        "decision": fields["decision"],
        "admitted_law": admitted,
        "proof": False,
        "legal_sufficiency": False,
        "support_eligible": False,
        "source_passage": fields["source_passage"],
        "authority_identity": fields["authority_identity"],
        "jurisdiction": fields["jurisdiction"],
        "effective_date": fields["effective_date"],
        "applicability": fields["applicability"],
        "exceptions": list(fields["exceptions"]) if fields["exceptions"] is not None else None,
        "treatment_state": fields["treatment_state"],
        "version": fields["version"],
        "content_hash": fields["content_hash"],
        "attribution": dict(attribution),
        "operation_id": fields["operation_id"],
        "limitations": [
            "Only an exact match of the stored passage, identity, jurisdiction, effective date, applicability, exceptions, and treatment state is admitted.",
            "Source mismatch, a stale version, a missing passage, and an unauthorized reviewer stay unresolved.",
            "Search snippets, model text, and this review record are not a proof of legal sufficiency.",
            "WebSocket and SSE transports are not supported.",
        ],
    }


def _compare_passage(fields: Mapping[str, Any], stored: Mapping[str, Any] | None) -> str:
    passage = fields["source_passage"]
    if not passage.strip():
        return "missing_passage"
    if stored is None or not stored.get("source_passage"):
        return "missing_passage"
    if fields["version"] != stored.get("version") or stored.get("version_state") == "stale":
        return "stale_version"
    current = str(stored.get("current_version") or "")
    if current and current != stored.get("version"):
        return "stale_version"
    same = (
        passage == stored.get("source_passage")
        and fields["content_hash"] == stored.get("content_hash")
        and fields["authority_identity"] == stored.get("authority_identity")
        and fields["jurisdiction"] == stored.get("jurisdiction")
        and fields["effective_date"] == stored.get("effective_date")
        and fields["applicability"] == stored.get("applicability")
        and fields["exceptions"] == stored.get("exceptions")
        and fields["treatment_state"] == stored.get("treatment_state")
    )
    if not same:
        return "source_mismatch"
    if fields["applicability"] in {"", "unknown", "disputed"} or fields["treatment_state"] in {"", "unknown"} or fields["exceptions"] is None:
        return "source_metadata_unresolved"
    if fields["applicability"] not in APPLICABILITY_VALUES or fields["treatment_state"] not in TREATMENT_STATES:
        return "source_mismatch"
    return ""


def review_versioned_authority(
    mediator: Any,
    workspace: Any,
    authority: Any,
    body: Mapping[str, Any],
    *,
    membership: str,
    actor_is_encrypted_owner: bool = False,
    canonical_owner_principal_id: str = "",
    source_scope_sha256: str = "",
) -> Dict[str, Any]:
    """Admit one stored passage only for an owner or assigned lawyer.

    The actor on the authority object is recorded. A body-claimed reviewer is
    not the actor. Mismatches stay unresolved and keep that attribution.
    """
    if not isinstance(body, Mapping):
        raise LegalResearchError("legal_research_field")
    fields = _review_fields(body)
    actor_id = str(getattr(authority, "actor_principal_id", "") or "")
    attribution = {
        "actor_principal_id": actor_id,
        "membership": str(membership or ""),
        "canonical_owner_principal_id": str(canonical_owner_principal_id or ""),
        "actor_is_encrypted_owner": bool(actor_is_encrypted_owner),
        "decision": fields["decision"],
        "recorded": True,
    }
    if fields["reviewer_principal_id"] and fields["reviewer_principal_id"] != actor_id:
        attribution["claimed_reviewer_principal_id"] = fields["reviewer_principal_id"]
    case_file = _case_file_from_mediator(mediator)
    seen = case_file.get("legal_authority_review_operations")
    if not isinstance(seen, dict):
        if seen is not None:
            raise LegalResearchError("legal_research_revision_conflict")
        seen = {}
        case_file["legal_authority_review_operations"] = seen
    operation_id = fields["operation_id"]
    index = case_file.get("legal_source_passage_index") if isinstance(case_file.get("legal_source_passage_index"), dict) else {}
    stored = index.get(fields["content_hash"]) if isinstance(index.get(fields["content_hash"]), dict) else None
    fingerprint = _operation_fingerprint({
        "request": fields, "attribution": attribution,
        "case_id": getattr(authority, "case_id", ""),
        "legal_context": None if source_scope_sha256 else case_file.get("legal_context"),
        "source": {key: value for key, value in stored.items() if key not in {"reviewed_source_record", "source_admission"}} if isinstance(stored, dict) else None,
        "source_scope_sha256": source_scope_sha256,
    })
    if operation_id and operation_id in seen:
        prior = seen[operation_id]
        if prior.get("fingerprint") != fingerprint:
            raise LegalResearchError("legal_research_revision_conflict")
        replay = deepcopy(prior["receipt"])
        replay["replayed"] = True
        replay["admitted_law"] = replay.get("admitted_law") is True
        replay["proof"] = False
        return replay
    if operation_id and len(seen) >= 256:
        raise LegalResearchError("legal_research_bounds")
    reason = ""
    if membership not in AUTHORIZED_ADMISSION_MEMBERSHIPS or not actor_id:
        reason = "unauthorized_reviewer"
    elif attribution.get("claimed_reviewer_principal_id"):
        reason = "unauthorized_reviewer"
    if not reason and fields["decision"] == "reject":
        reason = "rejected"
    if not reason:
        reason = _compare_passage(fields, stored)
    admitted = reason == "" and fields["decision"] == "admit"
    source_review = fields["decision"] == "admit" and reason in {"", "source_metadata_unresolved"}
    source_admission = None
    if source_review:
        owner = getattr(mediator, "admit_acquired_authorities", None)
        if not callable(owner):
            reason = "admission_owner_unavailable"
            admitted = False
        else:
            try:
                source = stored.get("canonical_source") if isinstance(stored, dict) else None
                if not isinstance(source, dict):
                    raise LegalResearchError("canonical_source_missing")
                canonical_owner = str(canonical_owner_principal_id or getattr(authority, "canonical_owner_principal_id", "") or "")
                if not canonical_owner:
                    raise LegalResearchError("canonical_owner_unavailable")
                claims = case_file.get("candidate_claims")
                claims = [dict(item) for item in claims if isinstance(item, dict)] if isinstance(claims, list) else []
                outcome = owner(
                    {"status": "candidates", "candidates": [deepcopy(source)], "explicit_review": True, "proof": False},
                    claims,
                    case_file,
                    user_id=canonical_owner,
                )
            except Exception:
                outcome = {}
            admission = outcome.get("admission") if isinstance(outcome, dict) else None
            owner_status = admission.get("status") if isinstance(admission, dict) else ""
            stored_ids = admission.get("stored_record_ids") if isinstance(admission, dict) else None
            if (owner_status != "admitted" or admission.get("proof") is not False
                    or not isinstance(stored_ids, list) or not stored_ids
                    or any(type(item) is not int or item < 0 for item in stored_ids)):
                reason = "admission_owner_unresolved"
                admitted = False
                attribution["owner_status"] = str(owner_status or "unavailable")
            else:
                from integrations.ipfs_datasets.logic import prepare_acquired_authority_record
                decisions = admission.get("decisions") or []
                accepted_source = next((row for row in decisions if isinstance(row, dict)
                    and row.get("status") == "admitted"), None)
                prepared = prepare_acquired_authority_record(source,
                    jurisdiction=str((accepted_source or {}).get("jurisdiction") or ""),
                    as_of_date=str((accepted_source or {}).get("as_of_date") or ""))
                if (prepared.get("status") != "admitted" or not accepted_source
                        or prepared.get("hashes") != accepted_source.get("hashes")):
                    reason, admitted = "admission_source_unverified", False
                else:
                    source_record = deepcopy(prepared["record"])
                    claim_record_ids = {}
                    for claim in claims:
                        claim_type = str(claim.get("type") or claim.get("claim_type") or "").strip()
                        if not claim_type or claim_type in claim_record_ids:
                            continue
                        rows = mediator.get_legal_authorities(user_id=canonical_owner, claim_type=claim_type)
                        joined_ids = sorted({row["id"] for row in rows if isinstance(row, dict)
                            and type(row.get("id")) is int and row["id"] in stored_ids})
                        if joined_ids:
                            claim_record_ids[claim_type] = joined_ids
                    if not claim_record_ids:
                        reason, admitted = "admission_claim_binding_unverified", False
                    else:
                        source_admission = {"status": "admitted", "stored_record_ids": list(stored_ids),
                            "claim_record_ids": claim_record_ids,
                            "source_record_sha256": _operation_fingerprint(source_record),
                            "source_scope_sha256": source_scope_sha256, "hashes": deepcopy(prepared["hashes"]),
                            "record": source_record, "proof": False}
                        stored["reviewed_source_record"] = source_record
                        stored["source_admission"] = deepcopy(source_admission)
    record = _admission_record(
        fields,
        status="admitted" if admitted else "unresolved",
        reason="" if admitted else reason,
        admitted=admitted,
        attribution=attribution,
    )
    record["replayed"] = False
    record["case_id"] = str(getattr(authority, "case_id", "") or "")
    record["workspace_bound"] = workspace is not None
    record["source_status"] = "source_admitted" if source_admission is not None else "not_admitted"
    record["source_admission"] = source_admission
    record["governing_applicability"] = fields["applicability"]
    _admission_ledger(case_file).append(record)
    if operation_id:
        seen[operation_id] = {"fingerprint": fingerprint, "receipt": deepcopy(record)}
    return record


def verified_reviewed_source_records(
    case_file: Mapping[str, Any], *, source_scope_sha256: str,
) -> Dict[str, list[dict]]:
    """Copy current owned source records grouped by their actual storage join.

    This verifies custody, not governing applicability or a legal proof. The
    caller supplies the current server-derived case/source scope. Empty scope
    and absent reviewed sources yield no records; there is no database union.
    """
    from integrations.ipfs_datasets.logic import prepare_acquired_authority_record

    index = case_file.get("legal_source_passage_index")
    ledger = case_file.get("legal_authority_admissions", [])
    if not isinstance(source_scope_sha256, str) or len(source_scope_sha256) != 64:
        raise LegalResearchError("legal_research_revision_conflict")
    if index is None:
        return {}
    if not isinstance(index, dict) or len(index) > 256 or not isinstance(ledger, list):
        raise LegalResearchError("legal_research_revision_conflict")
    grouped: Dict[str, list[dict]] = {}
    for content_hash, entry in index.items():
        if not isinstance(entry, dict):
            raise LegalResearchError("legal_research_revision_conflict")
        admission = entry.get("source_admission")
        if admission is None:
            continue
        # A later rejection or changed case source invalidates the old join.
        latest = next((row for row in reversed(ledger) if isinstance(row, dict)
            and row.get("content_hash") == content_hash), None)
        if (not isinstance(admission, dict) or not latest
                or latest.get("source_status") != "source_admitted"
                or latest.get("source_admission") != admission
                or admission.get("source_scope_sha256") != source_scope_sha256
                or admission.get("proof") is not False):
            raise LegalResearchError("legal_research_revision_conflict")
        record = entry.get("reviewed_source_record")
        metadata = record.get("metadata") if isinstance(record, dict) else None
        if not isinstance(metadata, dict):
            raise LegalResearchError("legal_research_revision_conflict")
        prepared = prepare_acquired_authority_record(entry.get("canonical_source"),
            jurisdiction=str(metadata.get("jurisdiction") or ""),
            as_of_date=str(metadata.get("as_of_date") or ""))
        if (prepared.get("status") != "admitted" or prepared.get("record") != record
                or admission.get("record") != record
                or admission.get("source_record_sha256") != _operation_fingerprint(record)
                or admission.get("hashes") != prepared.get("hashes")
                or not isinstance(content_hash, str)
                or prepared.get("hashes", {}).get("source_hash") != content_hash.removeprefix("sha256:")):
            raise LegalResearchError("legal_research_revision_conflict")
        stored_ids, joins = admission.get("stored_record_ids"), admission.get("claim_record_ids")
        if (not isinstance(stored_ids, list) or not stored_ids
                or any(type(value) is not int or value < 0 for value in stored_ids)
                or not isinstance(joins, dict) or not joins or len(joins) > 64):
            raise LegalResearchError("legal_research_revision_conflict")
        for claim_type, ids in joins.items():
            if (not isinstance(claim_type, str) or not claim_type.strip() or len(claim_type) > 256
                    or not isinstance(ids, list) or not ids
                    or any(type(value) is not int or value not in stored_ids for value in ids)):
                raise LegalResearchError("legal_research_revision_conflict")
            records = grouped.setdefault(claim_type, [])
            if record not in records:
                records.append(deepcopy(record))
    return grouped


def project_authority_admissions(case_file: Mapping[str, Any]) -> Dict[str, Any]:
    rows = case_file.get("legal_authority_admissions") if isinstance(case_file, Mapping) else None
    admissions = [dict(item) for item in rows if isinstance(item, dict)] if isinstance(rows, list) else []
    for item in admissions:
        item["proof"] = False
        item["legal_sufficiency"] = False
        if item.get("status") != "admitted":
            item["admitted_law"] = False
    return {
        "task_id": ADMISSION_TASK_ID,
        "action": "review_versioned_authority",
        "admissions": admissions,
        "admitted_count": sum(1 for item in admissions if item.get("admitted_law") is True),
        "source_admitted_count": sum(1 for item in admissions if item.get("source_status") == "source_admitted"),
        "unresolved_count": sum(1 for item in admissions if item.get("status") != "admitted"),
        "proof": False,
        "legal_sufficiency": False,
        "limitations": [
            "Admission is limited to the explicit matching review record.",
            "Unresolved reviews keep their admission or rejection attribution.",
        ],
    }


def project_legal_research(case_file: Mapping[str, Any]) -> Dict[str, Any]:
    stored = case_file.get("legal_source_candidate_receipt") if isinstance(case_file, Mapping) else None
    if not isinstance(stored, dict):
        return {
            "task_id": TASK_ID,
            "action": "legal_source_candidates",
            "admitted_law": False,
            "status": "empty",
            "source_version_receipts": [],
            "candidate_count": 0,
            "research_gap_count": 0,
            "limitations": [
                "No legal-source acquisition has been recorded.",
                "Search results are not admitted law.",
            ],
            "authority_admissions": project_authority_admissions(case_file),
        }
    projected = dict(stored)
    projected["admitted_law"] = False
    projected["proof"] = False
    receipts = projected.get("source_version_receipts")
    if isinstance(receipts, list):
        for item in receipts:
            if isinstance(item, dict):
                item["admitted_law"] = False
                item["proof"] = False
    projected["authority_admissions"] = project_authority_admissions(case_file)
    return projected


def mount_legal_research_routes(app: Any) -> None:
    """Expose only the actual encrypted Workspace owner under issued authority."""
    from fastapi.responses import JSONResponse
    from starlette.concurrency import run_in_threadpool
    from applications.case_routes import _BOUND_HANDLERS
    from applications.complaint_workspace import (ComplaintWorkspaceService, WorkspaceAccess,
        WorkspaceAuthorizationDenied, WorkspacePersistenceError, workspace_access_scope)
    from applications.workspace_case_authority import (WorkspaceCaseAuthorityError,
        current_workspace_case_authority)

    def fail(code):
        return JSONResponse({"error": code, "status": "denied", "admitted_law": False,
            "proof": False}, status_code=legal_research_http_status(code))

    def authorized(request, case_id, action):
        decision = getattr(request.state, "case_authorization", None)
        actor = getattr(getattr(request.state, "browser_principal", None), "principal_id", None)
        authority = current_workspace_case_authority()
        if (decision is None or decision.permits_case_content is not True or decision.action != action
                or decision.case_id != case_id or not actor or authority is None):
            raise LegalResearchError("legal_research_ungranted")
        query_case = request.query_params.get("case_id")
        if query_case and query_case != case_id:
            raise LegalResearchError("cross_case_id")
        resolver = _BOUND_HANDLERS.get()
        if resolver is None:
            raise LegalResearchError("legal_research_unavailable")
        _mediator, workspace, _root = resolver()
        if not isinstance(workspace, ComplaintWorkspaceService):
            raise LegalResearchError("legal_research_unavailable")
        authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
        return workspace, authority, actor

    def operation(workspace, actor, case_id, kind, body):
        with workspace_access_scope(WorkspaceAccess.authenticated(actor, case_id)):
            if kind in {"read", "admissions"}:
                return workspace.read_case_legal_research(actor, case_id=case_id, admissions=kind == "admissions")
            if kind == "acquire":
                return workspace.acquire_case_legal_research(actor, case_id=case_id, request=body)
            return workspace.review_case_legal_authority(actor, case_id=case_id, request=body)

    async def dispatch(request, case_id, kind):
        action = "case.read" if kind in {"read", "admissions"} else ("case.update" if kind == "acquire" else "case.review")
        try:
            workspace, authority, actor = authorized(request, case_id, action)
            try:
                body = await request.json() if kind in {"acquire", "review"} else None
            except (ValueError, UnicodeError):
                raise LegalResearchError("legal_research_field") from None
            if body is not None and not isinstance(body, dict):
                raise LegalResearchError("legal_research_field")
            payload = await run_in_threadpool(operation, workspace, actor, case_id, kind, body)
            authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
            return JSONResponse(payload)
        except (WorkspaceAuthorizationDenied, WorkspaceCaseAuthorityError):
            return fail("legal_research_ungranted")
        except WorkspacePersistenceError as exc:
            return fail("legal_research_revision_conflict" if exc.code == "revision_conflict" else (
                "unlock_needed" if exc.code == "unlock_needed" else "legal_research_unavailable"))
        except LegalResearchError as exc:
            return fail(exc.code)

    @app.get(LEGAL_RESEARCH_PREFIX + "/{case_id}")
    async def read_legal_research(case_id: str, request: Request):
        return await dispatch(request, case_id, "read")

    @app.post(LEGAL_RESEARCH_PREFIX + "/{case_id}")
    async def acquire_legal_research(case_id: str, request: Request):
        return await dispatch(request, case_id, "acquire")

    @app.get(LEGAL_RESEARCH_PREFIX + "/{case_id}/admissions")
    async def read_authority_admissions(case_id: str, request: Request):
        return await dispatch(request, case_id, "admissions")

    @app.post(LEGAL_RESEARCH_PREFIX + "/{case_id}/admissions")
    async def review_authority_admission(case_id: str, request: Request):
        return await dispatch(request, case_id, "review")
