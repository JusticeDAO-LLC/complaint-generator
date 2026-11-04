"""Scoped lawyer review of sourced interpretations, separate from model and proof records.

Assigned lawyers propose and review under ``case.review``. Each human approval
stores the exact case, source, fact, and proof revisions it saw. A later change
to law or facts leaves that approval in place and refuses promotion. Model
suggestions and machine proof stay in their own attributed lists. None of these
records is governing law, legal sufficiency, or an owner-key grant.

This module does not claim WebSocket, SSE, or streaming support.
"""
from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping

from starlette.requests import Request

TASK_ID = "CIMP-GUI-32"
REVIEW_TRANSITION_TASK_ID = "CIMP-GUI-47"
WORKFLOW_STAGE_TASK_ID = "CIMP-GUI-49"
WORKFLOW_STAGE_ROUTE = "/api/documents/{case_id}/workflow-stage"
DRAFT_VERSIONS_ROUTE = "/api/documents/{case_id}/draft-versions"
DRAFT_REVIEWS_ROUTE = "/api/documents/{case_id}/draft-reviews"
DRAFT_EXPORTS_ROUTE = "/api/documents/{case_id}/draft-exports"
LAWYER_REVIEW_ROUTE = "/api/legal-analysis/{case_id}/lawyer-reviews"
LAWYER_WORKSPACE_ROUTE = "/api/legal-analysis/{case_id}/lawyer-workspace"
REVIEW_ITEMS_ROUTE = "/api/legal-analysis/{case_id}/review-items"
REVIEW_TRANSITIONS_ROUTE = "/api/legal-analysis/{case_id}/review-transitions"
_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "lawyer_workspace.html"
_BODY_CAP = 65536
_HUMAN = "human_legal_review"
_MODEL = "model_suggestion"
_MACHINE = "machine_proof"
_KINDS = (_HUMAN, _MODEL, _MACHINE)
_DECISIONS = {"approved", "rejected", "withheld"}
_REVIEW_ITEM_TYPES = {"review_task", "review_comment", "review_proposal"}
_REVIEW_CREATE = {
    "create_task": "review_task",
    "create_comment": "review_comment",
    "create_proposal": "review_proposal",
}
_REVIEW_TARGETS = {"fact", "answer", "legal_admission", "draft_revision", "evidence_span", "qualified_evidence_span", "complaint_section"}
_SECTION_REVIEW_OPERATIONS = {"comment_review_target", "accept_review_target", "reject_review_target"}
_OWNER_KEY_FIELDS = {"owner_master_key", "master_key", "passphrase", "owner_key", "key_material", "private_key", "owner_key_session"}
_REVIEW_STATE_KEYS = ("facts", "answers", "legal_admissions", "draft_revisions")
_SOURCE_UNBOUND = "source-unbound"
_FACTS_UNBOUND = "facts-unbound"
_PROOF_UNBOUND = "proof-unbound"
_WORKFLOW_DOMAINS = ("factual", "legal", "evidence", "proof")
_CHECKBOX_KEYS = {"complete", "completed", "checked", "done", "ready", "ready_to_file"}
_PROOF_UNRESOLVED = {"not_executed", "timeout", "unavailable", "unknown", "cancelled", "disproved"}
_OWNER_ACTIONS_BY_STAGE = {
    "factual_unresolved": ("record_current_facts",),
    "legal_unresolved": ("admit_current_authority",),
    "evidence_unresolved": ("bind_current_evidence",),
    "proof_unresolved": ("record_current_proof",),
    "draft_review": ("version_draft", "review_draft"),
}
_LAWYER_ACTIONS_BY_STAGE = {
    "factual_unresolved": ("review_factual_gap",),
    "legal_unresolved": ("review_legal_gap",),
    "evidence_unresolved": ("review_evidence_gap",),
    "proof_unresolved": ("review_proof_gap",),
    "draft_review": ("review_draft",),
}
_WORKFLOW_LIMITATIONS = (
    "Stage and readiness follow current factual, legal, evidence, and proof bindings.",
    "Checkbox completion does not advance a stage or create readiness.",
    "Draft, review, and export are separate versioned operations.",
    "Export requires case.download and a review of the same draft revision.",
    "Export does not file with a court.",
    "No operation claims legal sufficiency or governing law.",
    "WebSocket and SSE transports are not supported.",
)


class CaseReviewError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def case_review_http_status(code: str) -> int:
    if code in {"unauthenticated", "lawyer_review_unavailable"}:
        return 401
    if code in {"lawyer_review_field", "lawyer_review_bounds"}:
        return 422
    if code in {"stale_revision", "stale_approval", "replay_mismatch", "stale_review_revision", "stale_target_revision"}:
        return 409
    if code in {"review_field", "review_bounds"}:
        return 422
    return 403


def _digest(kind: str, material: str) -> str:
    payload = f"{kind}\n{material}".encode("utf-8")
    return kind + "-" + hashlib.sha256(payload).hexdigest()[:32]


def _text(value: Any, *, limit: int, required: bool) -> str:
    if value is None or value == "":
        if required:
            raise CaseReviewError("lawyer_review_field")
        return ""
    if not isinstance(value, str):
        raise CaseReviewError("lawyer_review_field")
    stripped = value.strip()
    if required and not stripped:
        raise CaseReviewError("lawyer_review_field")
    if len(value) > limit:
        raise CaseReviewError("lawyer_review_bounds")
    return stripped


def _case_file(mediator: Any) -> MutableMapping[str, Any]:
    phase_manager = getattr(mediator, "phase_manager", None)
    if phase_manager is not None and hasattr(phase_manager, "get_phase_data"):
        from complaint_phases.phase_manager import ComplaintPhase

        stored = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file")
        if isinstance(stored, dict):
            return stored
    stored = getattr(mediator, "intake_case_file", None)
    if isinstance(stored, dict):
        return stored
    raise CaseReviewError("lawyer_review_unavailable")


def _source_material(case_file: Mapping[str, Any]) -> tuple[str, str]:
    anchor = case_file.get("review_source_anchor")
    if isinstance(anchor, dict):
        identity = str(anchor.get("source_identity") or "").strip()
        text = str(anchor.get("source_text") or "")
        if identity and text.strip():
            return identity[:256], text
    attachment = case_file.get("canonical_legal_ir_attachment")
    if isinstance(attachment, dict):
        identity = str(attachment.get("source_identity") or "").strip()
        text = str(attachment.get("source_text") or "")
        if not text.strip():
            obligations = attachment.get("typed_obligations")
            if isinstance(obligations, list):
                text = json.dumps(obligations, sort_keys=True, default=str)
        if identity and text.strip():
            return identity[:256], text
    return "", ""


def _fact_material(case_file: Mapping[str, Any]) -> str:
    facts = case_file.get("review_fact_anchor")
    if isinstance(facts, str) and facts.strip():
        return facts
    if isinstance(facts, list) and facts:
        return "\n".join(str(item) for item in facts)
    return ""


def _proof_material(case_file: Mapping[str, Any]) -> str:
    trace = case_file.get("proof_trace_display")
    if not isinstance(trace, dict):
        return ""
    rows = []
    obligations = trace.get("obligations")
    if isinstance(obligations, list):
        for item in obligations:
            if not isinstance(item, dict):
                continue
            rows.append("|".join((
                str(item.get("obligation_id") or ""),
                str(item.get("proof_status") or ""),
                str(item.get("source_identity") or ""),
                str(item.get("source_span") or ""),
                str(item.get("engine_name") or ""),
                str(item.get("engine_version") or ""),
            )))
    return str(trace.get("source_identity") or "") + "\n" + "\n".join(rows)


def live_revisions(case_file: Mapping[str, Any], *, case_revision: int) -> Dict[str, Any]:
    """Revision tuple a review must match. Absence is an explicit unbound token."""

    if type(case_revision) is not int or isinstance(case_revision, bool) or case_revision < 0:
        raise CaseReviewError("lawyer_review_field")
    identity, text = _source_material(case_file)
    facts = _fact_material(case_file)
    proof = _proof_material(case_file)
    return {
        "case_revision": case_revision,
        "source_identity": identity,
        "source_revision": _digest("source", identity + "\n" + text) if identity else _SOURCE_UNBOUND,
        "fact_revision": _digest("facts", facts) if facts else _FACTS_UNBOUND,
        "proof_revision": _digest("proof", proof) if proof else _PROOF_UNBOUND,
        "proof_bound": bool(proof),
        "governing_legal_authority": False,
        "legal_sufficiency": False,
        "admitted_law": False,
        "promotes_changed_law": False,
        "promotes_changed_facts": False,
    }


def _matches(record: Mapping[str, Any], live: Mapping[str, Any]) -> bool:
    return (
        record.get("case_revision") == live["case_revision"]
        and record.get("source_revision") == live["source_revision"]
        and record.get("fact_revision") == live["fact_revision"]
        and record.get("proof_revision") == live["proof_revision"]
    )


def _annotate(record: Mapping[str, Any], live: Mapping[str, Any]) -> Dict[str, Any]:
    current = _matches(record, live)
    human_approval = (
        record.get("record_kind") == _HUMAN
        and record.get("author_kind") == "human"
        and record.get("decision") == "approved"
    )
    promoted = record.get("operation") == "promote" and record.get("status") == "promoted_for_revision"
    projected = dict(record)
    projected["applies_to_current_revisions"] = current
    projected["stale"] = not current
    projected["accepted_for_bound_revision"] = bool(current and human_approval and record.get("operation") == "review" and live.get("source_bound", True))
    projected["promoted_for_current_revisions"] = bool(current and promoted and live.get("source_bound", True))
    projected["promotes_changed_law"] = False
    projected["promotes_changed_facts"] = False
    projected["governing_legal_authority"] = False
    projected["legal_sufficiency"] = False
    projected["admitted_law"] = False
    projected["admitted_facts"] = False
    return projected


def project_lawyer_reviews(case_file: Mapping[str, Any], *, case_revision: int, live_context=None) -> Dict[str, Any]:
    live = dict(live_context) if live_context is not None else live_revisions(case_file, case_revision=case_revision)
    stored = case_file.get("lawyer_review_ledger")
    rows = [_annotate(item, live) for item in stored if isinstance(item, dict)] if isinstance(stored, list) else []
    human = [item for item in rows if item.get("record_kind") == _HUMAN]
    model = [item for item in rows if item.get("record_kind") == _MODEL]
    machine = [item for item in rows if item.get("record_kind") == _MACHINE]
    current_promotion = next((item for item in reversed(human) if item.get("promoted_for_current_revisions")), None)
    return {
        "task_id": TASK_ID,
        "operation": "project_lawyer_reviews",
        "status": "visible" if rows else "empty",
        "live_revisions": live,
        "human_legal_reviews": human,
        "model_suggestions": model,
        "machine_proofs": machine,
        "records_are_separate": True,
        "current_promotion": current_promotion,
        "stale_approvals_promote": False,
        "promotes_changed_law": False,
        "promotes_changed_facts": False,
        "governing_legal_authority": False,
        "legal_sufficiency": False,
        "admitted_law": False,
        "admitted_facts": False,
        "limitations": [
            "Human legal review, model suggestions, and machine proof are separate attributed records.",
            "A stale approval does not promote changed law or changed facts.",
            "Lawyer review is not governing law, legal sufficiency, or an owner-key grant.",
            "Machine proof status is not a human approval.",
        ],
    }


def _require_live(body: Mapping[str, Any], live: Mapping[str, Any]) -> None:
    expected = {
        "case_revision": body.get("expected_case_revision"),
        "source_revision": body.get("expected_source_revision"),
        "fact_revision": body.get("expected_fact_revision"),
        "proof_revision": body.get("expected_proof_revision"),
    }
    for key, value in expected.items():
        if (key=='case_revision' and type(value) is not int) or (key!='case_revision' and not isinstance(value,str)):
            raise CaseReviewError('lawyer_review_field')
        if value != live[key]:
            raise CaseReviewError("stale_revision")


def _base_record(body: Mapping[str, Any], live: Mapping[str, Any], *, actor_principal_id: str,
                 canonical_owner_principal_id: str, membership: str, kind: str, author_kind: str,
                 operation: str) -> Dict[str, Any]:
    if actor_principal_id == canonical_owner_principal_id:
        raise CaseReviewError("actor_is_not_canonical_owner")
    return {
        "task_id": TASK_ID,
        "record_id": _digest("record", actor_principal_id + "\n" + operation + "\n" + _text(body.get("request_id"), limit=80, required=True) + "\n" + str(len(json.dumps(live)))),
        "request_id": _text(body.get("request_id"), limit=80, required=True),
        "record_kind": kind,
        "author_kind": author_kind,
        "operation": operation,
        "actor_principal_id": actor_principal_id,
        "canonical_owner_principal_id": canonical_owner_principal_id,
        "actor_is_canonical_owner": False,
        "membership": membership,
        "case_revision": live["case_revision"],
        "source_identity": live["source_identity"],
        "source_revision": live["source_revision"],
        "fact_revision": live["fact_revision"],
        "proof_revision": live["proof_revision"],
        "governing_legal_authority": False,
        "legal_sufficiency": False,
        "admitted_law": False,
        "admitted_facts": False,
        "promotes_changed_law": False,
        "promotes_changed_facts": False,
    }


def submit_review_record(case_file: MutableMapping[str, Any], body: Mapping[str, Any], *, actor_principal_id: str,
                         canonical_owner_principal_id: str, case_revision: int, membership: str, live_context=None) -> Dict[str, Any]:
    """Append one attributed review record. Stale revisions are not stored as current."""

    if membership != "assigned-lawyer":
        raise CaseReviewError("lawyer_assignment_required")
    if not isinstance(body, Mapping) or len(json.dumps(body, default=str)) > _BODY_CAP:
        raise CaseReviewError("lawyer_review_bounds")
    operation = _text(body.get("operation"), limit=40, required=True)
    if operation not in {"propose", "review", "promote", "record_model_suggestion", "record_machine_proof"}:
        raise CaseReviewError("lawyer_review_field")
    live = dict(live_context) if live_context is not None else live_revisions(case_file, case_revision=case_revision)
    _require_live(body, live)
    stored = case_file.get("lawyer_review_ledger")
    ledger = stored if isinstance(stored, list) else []
    request_id = _text(body.get("request_id"), limit=80, required=True)
    for existing in ledger:
        if isinstance(existing, dict) and existing.get("request_id") == request_id:
            if existing.get("operation") != operation:
                raise CaseReviewError("replay_mismatch")
            projected = project_lawyer_reviews(case_file, case_revision=case_revision, live_context=live)
            projected["record"] = _annotate(existing, live)
            projected["operation"] = operation
            return projected

    if operation in {"propose", "review", "promote"}:
        record = _base_record(body, live, actor_principal_id=actor_principal_id,
            canonical_owner_principal_id=canonical_owner_principal_id, membership=membership,
            kind=_HUMAN, author_kind="human", operation=operation)
        record["interpretation"] = _text(body.get("interpretation"), limit=2000, required=operation == "propose")
        if operation == "propose":
            record["decision"] = "proposed"
            record["status"] = "proposed"
            citation = _text(body.get("source_citation"), limit=512, required=True)
            record["source_citation"] = citation
        elif operation == "review":
            decision = _text(body.get("decision"), limit=32, required=True)
            if decision not in _DECISIONS:
                raise CaseReviewError("lawyer_review_field")
            proposal_id = _text(body.get("proposal_id"), limit=80, required=True)
            proposal = next((item for item in ledger if isinstance(item, dict) and item.get("record_id") == proposal_id), None)
            if proposal is None or proposal.get("record_kind") != _HUMAN or proposal.get("operation") != "propose":
                raise CaseReviewError("proposal_required")
            if not _matches(proposal, live):
                raise CaseReviewError("stale_approval")
            record["decision"] = decision
            record["status"] = decision
            record["proposal_id"] = proposal_id
            record["interpretation"] = str(proposal.get("interpretation") or "")
            record["source_citation"] = str(proposal.get("source_citation") or "")
        else:
            approval_id = _text(body.get("approval_id"), limit=80, required=True)
            approval = next((item for item in ledger if isinstance(item, dict) and item.get("record_id") == approval_id), None)
            if approval is None or approval.get("record_kind") != _HUMAN or approval.get("decision") != "approved":
                raise CaseReviewError("approval_required")
            if not _matches(approval, live):
                raise CaseReviewError("stale_approval")
            record["decision"] = "approved"
            record["status"] = "promoted_for_revision"
            record["approval_id"] = approval_id
            record["proposal_id"] = approval.get("proposal_id")
            record["interpretation"] = str(approval.get("interpretation") or "")
            record["source_citation"] = str(approval.get("source_citation") or "")
            record["accepted_for_bound_revision"] = True
    elif operation == "record_model_suggestion":
        if body.get("decision") in _DECISIONS or body.get("approved") is True:
            raise CaseReviewError("model_cannot_approve")
        record = _base_record(body, live, actor_principal_id=actor_principal_id,
            canonical_owner_principal_id=canonical_owner_principal_id, membership=membership,
            kind=_MODEL, author_kind="model", operation=operation)
        record["model_id"] = _text(body.get("model_id"), limit=80, required=True)
        record["suggestion"] = _text(body.get("suggestion"), limit=2000, required=True)
        record["decision"] = "suggestion"
        record["status"] = "not_a_human_review"
        record["submitted_by_actor_principal_id"] = actor_principal_id
    else:
        if body.get("decision") in _DECISIONS or body.get("approved") is True:
            raise CaseReviewError("machine_proof_cannot_approve")
        record = _base_record(body, live, actor_principal_id=actor_principal_id,
            canonical_owner_principal_id=canonical_owner_principal_id, membership=membership,
            kind=_MACHINE, author_kind="machine", operation=operation)
        record["engine_name"] = _text(body.get("engine_name"), limit=80, required=False)
        record["engine_version"] = _text(body.get("engine_version"), limit=80, required=False)
        record["proof_status"] = "referenced" if live["proof_bound"] else "not_executed"
        record["decision"] = "machine_proof"
        record["status"] = "not_a_human_review"
        record["executed_proof_is_legal_sufficiency"] = False
    if body.get("governing_legal_authority") is True or body.get("legal_sufficiency") is True or body.get("admitted_law") is True:
        record["supplied_authority_ignored"] = True
    if case_file.get("lawyer_review_ledger") is not ledger:
        case_file["lawyer_review_ledger"] = ledger
    ledger.append(record)
    projected = project_lawyer_reviews(case_file, case_revision=case_revision, live_context=live)
    projected["record"] = _annotate(record, live)
    projected["operation"] = operation
    return projected


def _review_items(case_file: MutableMapping[str, Any]) -> list:
    stored = case_file.get("collaborative_review_items")
    if not isinstance(stored, list):
        stored = []
        case_file["collaborative_review_items"] = stored
    return stored


def _review_service(mediator: Any):
    service = getattr(mediator, "workflow_service", None)
    if service is not None and hasattr(service, "apply_authorized_review_transition"):
        return service
    from mediator.workflow_service import WorkflowActionService

    service = WorkflowActionService(mediator)
    mediator.workflow_service = service
    return service


def _state_view(case_file: Mapping[str, Any]) -> Dict[str, Any]:
    state = case_file.get("review_case_state")
    if not isinstance(state, dict):
        state = {}
    return {key: state.get(key) if isinstance(state.get(key), dict) else {} for key in _REVIEW_STATE_KEYS}


def project_collaborative_reviews(case_file: Mapping[str, Any]) -> Dict[str, Any]:
    """Project typed review items separately from case-state targets."""

    items = [dict(item) for item in case_file.get("collaborative_review_items") or [] if isinstance(item, dict)]
    state = case_file.get("review_case_state") if isinstance(case_file.get("review_case_state"), dict) else {}
    support = [dict(item) for item in state.get("downstream_support") or [] if isinstance(item, dict)]
    grouped = {kind: [item for item in items if item.get("item_type") == kind] for kind in sorted(_REVIEW_ITEM_TYPES)}
    return {
        "task_id": REVIEW_TRANSITION_TASK_ID,
        "operation": "project_collaborative_reviews",
        "status": "visible" if items or state else "empty",
        "item_types": sorted(_REVIEW_ITEM_TYPES),
        "items": items,
        "review_tasks": grouped["review_task"],
        "review_comments": grouped["review_comment"],
        "review_proposals": grouped["review_proposal"],
        "dissent": [item for item in items if item.get("operation") == "dissent"],
        "acceptance_history": list(state.get("acceptance_history") or []),
        "review_revision": int(state.get("review_revision") or 0) if type(state.get("review_revision")) is int else 0,
        "facts": _state_view(case_file)["facts"],
        "answers": _state_view(case_file)["answers"],
        "legal_admissions": _state_view(case_file)["legal_admissions"],
        "draft_revisions": _state_view(case_file)["draft_revisions"],
        "section_reviews": [dict(item) for item in _section_review_rows(case_file)],
        "bound_review_targets": bound_review_targets(case_file),
        "downstream_support": support,
        "comments_update_case_state": False,
        "tasks_update_case_state": False,
        "unaccepted_proposals_update_case_state": False,
        "governing_legal_authority": False,
        "legal_sufficiency": False,
        "limitations": [
            "Review tasks, comments, and proposals have explicit item types.",
            "Only an authorized accepted review_proposal updates facts, answers, legal admissions, or draft revisions.",
            "Concurrent acceptance uses the expected review revision and expected target revision.",
            "Dissent and prior target history are preserved.",
            "Downstream support for a replaced revision is invalidated and retained.",
            "Acceptance is not governing law or legal sufficiency.",
            "WebSocket and SSE transports are not supported.",
        ],
    }


def _snapshot_targets(case_file: Mapping[str, Any]) -> str:
    return json.dumps(_state_view(case_file), sort_keys=True, default=str)


def submit_collaborative_record(case_file: MutableMapping[str, Any], body: Mapping[str, Any], *, actor_principal_id: str,
                                canonical_owner_principal_id: str, case_id: str, membership: str,
                                authorized: bool, workflow_owner=None) -> Dict[str, Any]:
    """Record a typed review item. This path does not change case state."""

    if membership not in {"assigned-lawyer", "owner"}:
        raise CaseReviewError("lawyer_assignment_required")
    if not isinstance(body, Mapping) or len(json.dumps(body, default=str)) > _BODY_CAP:
        raise CaseReviewError("review_bounds")
    operation = _text(body.get("operation"), limit=40, required=True)
    if operation not in set(_REVIEW_CREATE) | {"dissent", "bind_support"}:
        raise CaseReviewError("review_field")
    before = _snapshot_targets(case_file)
    items = _review_items(case_file)
    request_id = _text(body.get("request_id"), limit=80, required=True)
    for existing in items:
        if isinstance(existing, dict) and existing.get("request_id") == request_id:
            if existing.get("operation") != operation:
                raise CaseReviewError("replay_mismatch")
            projected = project_collaborative_reviews(case_file)
            projected["record"] = dict(existing)
            projected["replayed"] = True
            return projected
    if actor_principal_id == canonical_owner_principal_id:
        raise CaseReviewError("actor_is_not_canonical_owner")
    record: Dict[str, Any] = {
        "task_id": REVIEW_TRANSITION_TASK_ID,
        "request_id": request_id,
        "operation": operation,
        "actor_principal_id": actor_principal_id,
        "canonical_owner_principal_id": canonical_owner_principal_id,
        "actor_is_canonical_owner": False,
        "membership": membership,
        "case_id": case_id,
        "updates_case_state": False,
    }
    if operation in _REVIEW_CREATE:
        item_type = _REVIEW_CREATE[operation]
        record["item_type"] = item_type
        record["item_id"] = _digest("review-item", request_id + "\n" + item_type + "\n" + actor_principal_id)
        record["body"] = _text(body.get("body"), limit=2000, required=True)
        if item_type == "review_proposal":
            target_kind = _text(body.get("target_kind"), limit=40, required=True)
            if target_kind not in _REVIEW_TARGETS:
                raise CaseReviewError("review_field")
            record["target_kind"] = target_kind
            record["target_id"] = _text(body.get("target_id"), limit=80, required=True)
            record["proposed_text"] = _text(body.get("proposed_text"), limit=2000, required=True)
            record["status"] = "proposed"
        elif item_type == "review_task":
            record["title"] = _text(body.get("title"), limit=200, required=True)
            record["status"] = "open"
        else:
            record["proposal_id"] = _text(body.get("proposal_id"), limit=80, required=False)
            record["status"] = "comment"
    elif operation == "dissent":
        proposal_id = _text(body.get("proposal_id"), limit=80, required=True)
        proposal = next((item for item in items if item.get("item_id") == proposal_id and item.get("item_type") == "review_proposal"), None)
        if proposal is None:
            raise CaseReviewError("proposal_required")
        record["item_type"] = "review_comment"
        record["item_id"] = _digest("review-dissent", request_id + "\n" + proposal_id)
        record["proposal_id"] = proposal_id
        record["body"] = _text(body.get("body"), limit=2000, required=True)
        record["dissent"] = True
        record["status"] = "dissent"
    else:
        if workflow_owner is None:
            raise CaseReviewError("review_transition_owner_unavailable")
        service = workflow_owner
        receipt = service.register_review_downstream_support(
            case_id=case_id,
            support_id=_text(body.get("support_id"), limit=80, required=True),
            depends_on_kind=_text(body.get("depends_on_kind"), limit=40, required=True),
            depends_on_id=_text(body.get("depends_on_id"), limit=80, required=True),
            depends_on_revision=body.get("depends_on_revision"),
            request_id=request_id,
        )
        if receipt.get("status") != "bound":
            code = (receipt.get("error") or {}).get("code") or "review_field"
            raise CaseReviewError(str(code))
        record["item_type"] = "downstream_support_binding"
        record["item_id"] = _digest("review-support", request_id)
        record["support_id"] = body.get("support_id")
        record["status"] = "support_bound"
        record["body"] = "Downstream support is bound to the current target revision."
    if _snapshot_targets(case_file) != before:
        raise CaseReviewError("review_state_mutated")
    items.append(record)
    projected = project_collaborative_reviews(case_file)
    projected["record"] = dict(record)
    projected["replayed"] = False
    return projected



def submit_collaborative_review(mediator: Any, body: Mapping[str, Any], **scope) -> Dict[str, Any]:
    return submit_collaborative_record(_case_file(mediator), body,
        workflow_owner=_review_service(mediator) if body.get('operation') == 'bind_support' else None, **scope)


def accept_review_transition(mediator: Any, body: Mapping[str, Any], *, actor_principal_id: str,
                             canonical_owner_principal_id: str, case_id: str, membership: str,
                             authorized: bool) -> Dict[str, Any]:
    """Accept one proposal into case state when the caller and revisions match."""

    if not authorized or membership not in {"assigned-lawyer", "owner"}:
        raise CaseReviewError("actor_not_permitted")
    if not isinstance(body, Mapping) or len(json.dumps(body, default=str)) > _BODY_CAP:
        raise CaseReviewError("review_bounds")
    if _text(body.get("operation"), limit=40, required=True) != "accept":
        raise CaseReviewError("not_an_accepted_transition")
    case_file = _case_file(mediator)
    items = _review_items(case_file)
    request_id = _text(body.get("request_id"), limit=80, required=True)
    proposal_id = _text(body.get("proposal_id"), limit=80, required=True)
    proposal = next((item for item in items if item.get("item_id") == proposal_id), None)
    if proposal is None:
        raise CaseReviewError("proposal_required")
    if proposal.get("item_type") != "review_proposal":
        raise CaseReviewError("not_an_accepted_transition")
    replacement = _text(body.get("replacement"), limit=2000, required=True)
    if replacement != str(proposal.get("proposed_text") or ""):
        raise CaseReviewError("proposal_mismatch")
    target_kind = _text(body.get("target_kind"), limit=40, required=True)
    target_id = _text(body.get("target_id"), limit=80, required=True)
    if target_kind != proposal.get("target_kind") or target_id != proposal.get("target_id"):
        raise CaseReviewError("proposal_mismatch")
    for existing in items:
        if existing.get("request_id") == request_id and existing.get("operation") == "accept":
            projected = project_collaborative_reviews(case_file)
            projected["record"] = dict(existing)
            projected["replayed"] = True
            projected["applied"] = False
            return projected
    dissent_ids = [item.get("item_id") for item in items if item.get("dissent") is True and item.get("proposal_id") == proposal_id]
    service = _review_service(mediator)
    receipt = service.apply_authorized_review_transition(
        case_id=case_id,
        actor_principal_id=actor_principal_id,
        canonical_owner_principal_id=canonical_owner_principal_id,
        authorized=True,
        item_type="review_proposal",
        item_id=proposal_id,
        target_kind=target_kind,
        target_id=target_id,
        replacement=replacement,
        expected_review_revision=body.get("expected_review_revision"),
        expected_target_revision=body.get("expected_target_revision"),
        request_id=request_id,
    )
    if receipt.get("status") != "applied":
        code = (receipt.get("error") or {}).get("code") or "review_field"
        raise CaseReviewError(str(code))
    record = {
        "task_id": REVIEW_TRANSITION_TASK_ID,
        "request_id": request_id,
        "operation": "accept",
        "item_type": "review_proposal",
        "item_id": _digest("review-accept", request_id + "\n" + proposal_id),
        "proposal_id": proposal_id,
        "actor_principal_id": actor_principal_id,
        "canonical_owner_principal_id": canonical_owner_principal_id,
        "actor_is_canonical_owner": False,
        "membership": membership,
        "case_id": case_id,
        "target_kind": target_kind,
        "target_id": target_id,
        "target_revision": receipt["acceptance"]["target_revision"],
        "review_revision": receipt["review_revision"],
        "preserved_dissent_ids": dissent_ids,
        "invalidated_support_ids": list(receipt.get("invalidated_support_ids") or []),
        "updates_case_state": True,
        "status": "accepted",
        "governing_legal_authority": False,
        "legal_sufficiency": False,
    }
    items.append(record)
    projected = project_collaborative_reviews(case_file)
    projected["record"] = record
    projected["applied"] = True
    projected["replayed"] = False
    for dissent_id in dissent_ids:
        if not any(item.get("item_id") == dissent_id for item in projected["dissent"]):
            raise CaseReviewError("dissent_lost")
    return projected

def _positive_revision(value: Any) -> int:
    return value if type(value) is int and value > 0 else 0


def _workflow_domains(case_file: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    stored = case_file.get("workflow_domains")
    if not isinstance(stored, dict):
        stored = {}
    return {name: dict(stored.get(name)) if isinstance(stored.get(name), dict) else {} for name in _WORKFLOW_DOMAINS}


def _ignored_checkboxes(case_file: Mapping[str, Any], domains: Mapping[str, Mapping[str, Any]]) -> list:
    found = []
    stored = case_file.get("workflow_checkboxes")
    if isinstance(stored, dict):
        found.extend(sorted(str(key) for key in stored))
    for name, domain in domains.items():
        for key in _CHECKBOX_KEYS:
            if key in domain:
                found.append(name + "." + key)
    return found


def _factual_view(domain: Mapping[str, Any]) -> Dict[str, Any]:
    revision = _positive_revision(domain.get("revision"))
    assertions = domain.get("assertions")
    bound = (
        domain.get("status") == "current"
        and revision > 0
        and isinstance(assertions, list)
        and len(assertions) > 0
        and all(
            isinstance(item, dict)
            and item.get("bound") is True
            and _positive_revision(item.get("revision")) == revision
            for item in assertions
        )
    )
    reason = "current" if bound else "factual_not_current"
    return {"settled": bound, "revision": revision, "reason": reason}


def _legal_view(domain: Mapping[str, Any], factual_revision: int) -> Dict[str, Any]:
    revision = _positive_revision(domain.get("revision"))
    authority = str(domain.get("authority_id") or "").strip()
    settled = (
        domain.get("status") == "admitted"
        and revision > 0
        and domain.get("factual_revision") == factual_revision
        and factual_revision > 0
        and authority != ""
    )
    if settled:
        reason = "admitted_for_current_facts"
    elif domain.get("status") != "admitted":
        reason = "legal_not_admitted"
    elif domain.get("factual_revision") != factual_revision:
        reason = "legal_factual_mismatch"
    else:
        reason = "authority_missing"
    return {
        "settled": settled,
        "revision": revision,
        "reason": reason,
        "governing_law": False,
        "governing_law_claim_ignored": domain.get("governing_law") is True,
    }


def _evidence_view(domain: Mapping[str, Any], factual_revision: int, legal_revision: int) -> Dict[str, Any]:
    revision = _positive_revision(domain.get("revision"))
    exhibits = domain.get("exhibits")
    settled = (
        domain.get("status") == "bound"
        and revision > 0
        and domain.get("factual_revision") == factual_revision
        and domain.get("legal_revision") == legal_revision
        and factual_revision > 0
        and legal_revision > 0
        and isinstance(exhibits, list)
        and len(exhibits) > 0
        and all(
            isinstance(item, dict) and item.get("supports_factual_revision") == factual_revision
            for item in exhibits
        )
    )
    reason = "bound" if settled else "evidence_not_bound" if domain.get("status") != "bound" else "evidence_binding_mismatch"
    return {"settled": settled, "revision": revision, "reason": reason}


def _proof_view(domain: Mapping[str, Any], factual_revision: int, evidence_revision: int) -> Dict[str, Any]:
    revision = _positive_revision(domain.get("revision"))
    status = str(domain.get("status") or "not_executed")
    settled = (
        status == "executed"
        and domain.get("result") == "verified"
        and revision > 0
        and domain.get("factual_revision") == factual_revision
        and domain.get("evidence_revision") == evidence_revision
        and factual_revision > 0
        and evidence_revision > 0
    )
    if settled:
        reason = "executed_for_current_bindings"
    elif status in _PROOF_UNRESOLVED:
        reason = status
    elif domain.get("factual_revision") != factual_revision or domain.get("evidence_revision") != evidence_revision:
        reason = "proof_binding_mismatch"
    else:
        reason = "proof_not_verified"
    return {"settled": settled, "revision": revision, "reason": reason, "legal_sufficiency": False}


def _draft_store(case_file: MutableMapping[str, Any]) -> Dict[str, Any]:
    stored = case_file.get("draft_workflow")
    if not isinstance(stored, dict):
        stored = {"versions": [], "reviews": [], "exports": []}
        case_file["draft_workflow"] = stored
    for key in ("versions", "reviews", "exports"):
        if not isinstance(stored.get(key), list):
            stored[key] = []
    return stored


def _domain_snapshot(views: Mapping[str, Mapping[str, Any]]) -> Dict[str, int]:
    return {name: int(views[name]["revision"]) for name in _WORKFLOW_DOMAINS}


def _snapshot_matches(snapshot: Mapping[str, Any], views: Mapping[str, Mapping[str, Any]]) -> bool:
    return all(snapshot.get(name) == views[name]["revision"] for name in _WORKFLOW_DOMAINS)


def _accepted_review(store: Mapping[str, Any], draft_id: str, revision: int, snapshot: Mapping[str, Any]) -> Dict[str, Any] | None:
    for item in reversed(store.get("reviews") or []):
        if not isinstance(item, dict):
            continue
        if item.get("draft_id") == draft_id and item.get("draft_revision") == revision and item.get("decision") == "accepted_for_export":
            if item.get("domain_snapshot") == dict(snapshot):
                return item
    return None


def project_workflow_stage(case_file: Mapping[str, Any]) -> Dict[str, Any]:
    """Project stage, actions, and readiness from live domain bindings.

    Checkbox maps are reported and ignored. A verified proof or a drafted
    paragraph is not legal sufficiency and does not file anything.
    """

    domains = _workflow_domains(case_file)
    factual = _factual_view(domains["factual"])
    legal = _legal_view(domains["legal"], factual["revision"])
    evidence = _evidence_view(domains["evidence"], factual["revision"], legal["revision"] if legal["settled"] else 0)
    proof = _proof_view(domains["proof"], factual["revision"], evidence["revision"] if evidence["settled"] else 0)
    views = {"factual": factual, "legal": legal, "evidence": evidence, "proof": proof}
    stage = "draft_review"
    for name, label in (
        ("factual", "factual_unresolved"),
        ("legal", "legal_unresolved"),
        ("evidence", "evidence_unresolved"),
        ("proof", "proof_unresolved"),
    ):
        if not views[name]["settled"]:
            stage = label
            break
    store = case_file.get("draft_workflow") if isinstance(case_file.get("draft_workflow"), dict) else {}
    versions = [item for item in store.get("versions") or [] if isinstance(item, dict)]
    reviews = [item for item in store.get("reviews") or [] if isinstance(item, dict)]
    snapshot = _domain_snapshot(views)
    exportable = []
    if stage == "draft_review":
        for version in versions:
            if version.get("domain_snapshot") == snapshot and _accepted_review(store, str(version.get("draft_id") or ""), int(version.get("revision") or 0), snapshot):
                exportable.append({"draft_id": version.get("draft_id"), "revision": version.get("revision")})
    ignored = _ignored_checkboxes(case_file, domains)
    return {
        "task_id": WORKFLOW_STAGE_TASK_ID,
        "operation": "project_workflow_stage",
        "stage": stage,
        "readiness": {
            "derived_from": list(_WORKFLOW_DOMAINS),
            "checkbox_completion_counts": False,
            "ignored_checkbox_keys": ignored,
            "ready_for_draft_review": stage == "draft_review",
            "ready_for_versioned_export": bool(exportable),
            "legal_sufficiency": False,
            "automatic_court_filing": False,
            "court_filed": False,
            "governing_law": False,
        },
        "domains": views,
        "owner_actions": list(_OWNER_ACTIONS_BY_STAGE[stage]),
        "lawyer_actions": list(_LAWYER_ACTIONS_BY_STAGE[stage]),
        "download_scoped_actions": ["export_reviewed_draft"] if exportable else [],
        "refused_actions": ["file_with_court", "declare_legal_sufficiency"],
        "exportable_drafts": exportable,
        "draft_version_count": len(versions),
        "draft_review_count": len(reviews),
        "draft_review_actions": project_draft_review_actions(case_file),
        "legal_sufficiency": False,
        "automatic_court_filing": False,
        "court_filed": False,
        "limitations": list(_WORKFLOW_LIMITATIONS),
    }


_SUGGESTION_KINDS = ("human_reviews", "model_suggestions", "machine_proofs", "messages", "acceptances")
_DRAFT_SUGGESTION_OPERATIONS = {
    "propose_bounded_change": "human_reviews",
    "record_draft_model_suggestion": "model_suggestions",
    "record_draft_machine_proof": "machine_proofs",
}


def _suggestion_bucket(case_file: MutableMapping[str, Any]) -> Dict[str, Any]:
    stored = case_file.get("draft_suggestion_records")
    if not isinstance(stored, dict):
        stored = {}
        case_file["draft_suggestion_records"] = stored
    for key in _SUGGESTION_KINDS:
        if not isinstance(stored.get(key), list):
            stored[key] = []
    return stored


def _draft_versions(case_file: Mapping[str, Any]) -> list:
    store = case_file.get("draft_workflow") if isinstance(case_file.get("draft_workflow"), dict) else {}
    return [item for item in store.get("versions") or [] if isinstance(item, dict)]


def _target_version(case_file: Mapping[str, Any], draft_id: str) -> Dict[str, Any]:
    matched = [item for item in _draft_versions(case_file) if item.get("draft_id") == draft_id]
    if not matched:
        return {"draft_id": draft_id, "revision": 0, "text_digest": "", "actor_principal_id": "", "text": ""}
    current = max(matched, key=lambda item: int(item.get("revision") or 0))
    return {
        "draft_id": draft_id,
        "revision": int(current.get("revision") or 0),
        "text_digest": str(current.get("text_digest") or ""),
        "actor_principal_id": str(current.get("actor_principal_id") or ""),
        "text": str(current.get("text") or ""),
    }


def _public_suggestion(record: Mapping[str, Any], target: Mapping[str, Any]) -> Dict[str, Any]:
    current = (
        record.get("target_revision") == target.get("revision")
        and record.get("target_text_digest") == target.get("text_digest")
        and record.get("draft_id") == target.get("draft_id")
    )
    projected = dict(record)
    projected["applies_to_current_revision"] = bool(current)
    projected["stale"] = not current
    projected["adopted_into_owner_draft"] = False
    projected["changes_owner_draft"] = False
    return projected


def project_draft_review_actions(case_file: Mapping[str, Any], *, draft_id: str = "") -> Dict[str, Any]:
    """Show human review, model suggestions, machine proof, and messages apart.

    A suggestion projection never rewrites the owner's draft versions.
    """

    stored = case_file.get("draft_suggestion_records") if isinstance(case_file.get("draft_suggestion_records"), dict) else {}
    versions = _draft_versions(case_file)
    selected = draft_id or str((versions[-1].get("draft_id") if versions else "") or "")
    target = _target_version(case_file, selected) if selected else {
        "draft_id": "", "revision": 0, "text_digest": "", "actor_principal_id": "", "text": "",
    }
    grouped = {}
    for key in _SUGGESTION_KINDS:
        rows = stored.get(key) if isinstance(stored.get(key), list) else []
        grouped[key] = [_public_suggestion(item, target) for item in rows if isinstance(item, dict)]
    external_messages = case_file.get("case_messages") if isinstance(case_file.get("case_messages"), list) else []
    messages = list(grouped["messages"])
    for item in external_messages:
        if isinstance(item, dict):
            message = dict(item)
            message["record_kind"] = "case_message"
            message["provenance"] = "human_message"
            message["changes_owner_draft"] = False
            messages.append(message)
    populated = any(grouped[key] for key in _SUGGESTION_KINDS) or bool(messages)
    return {
        "task_id": "CIMP-UX-32",
        "operation": "project_draft_review_actions",
        "status": "visible" if populated else "empty",
        "draft_id": target["draft_id"],
        "target_revision": target["revision"],
        "target_text_digest": target["text_digest"],
        "target_author": target["actor_principal_id"],
        "human_reviews": grouped["human_reviews"],
        "model_suggestions": grouped["model_suggestions"],
        "machine_proofs": grouped["machine_proofs"],
        "messages": messages,
        "acceptances": grouped["acceptances"],
        "records_are_separate": True,
        "suggestions_change_owner_draft": False,
        "owner_draft_revision_count": len(versions),
        "bound_review_targets": bound_review_targets(case_file),
        "section_reviews": [dict(item) for item in _section_review_rows(case_file)],
        "limitations": [
            "Human review, model suggestions, machine proof, and messages are separate records.",
            "A proposal records the exact target revision, author, and provenance.",
            "Only an explicit authorized owner acceptance may be followed by a draft save.",
            "Recording a suggestion does not change the owner's draft.",
        ],
    }


def submit_draft_suggestion(case_file: MutableMapping[str, Any], body: Mapping[str, Any], *, actor_principal_id: str,
                            canonical_owner_principal_id: str, membership: str, action: str) -> Dict[str, Any]:
    """Record one bounded suggestion. The owner's draft versions stay unchanged."""

    if membership not in {"assigned-lawyer", "owner"} or action != "case.review":
        raise CaseReviewError("actor_not_permitted")
    if not isinstance(body, Mapping) or len(json.dumps(body, default=str)) > _BODY_CAP:
        raise CaseReviewError("draft_bounds")
    operation = _text(body.get("operation"), limit=64, required=True)
    if operation not in _DRAFT_SUGGESTION_OPERATIONS:
        raise CaseReviewError("draft_field")
    if body.get("decision") in _DECISIONS or body.get("approved") is True or body.get("legal_sufficiency") is True:
        raise CaseReviewError("draft_field")
    before_versions = json.dumps(_draft_versions(case_file), sort_keys=True, default=str)
    request_id = _text(body.get("request_id"), limit=80, required=True)
    draft_id = _text(body.get("draft_id"), limit=80, required=True)
    bucket = _suggestion_bucket(case_file)
    for key in _SUGGESTION_KINDS:
        for existing in bucket[key]:
            if isinstance(existing, dict) and existing.get("request_id") == request_id:
                if existing.get("operation") != operation:
                    raise CaseReviewError("replay_mismatch")
                projected = project_draft_review_actions(case_file, draft_id=draft_id)
                projected["record"] = dict(existing)
                projected["replayed"] = True
                return projected
    expected_revision = body.get("expected_revision")
    if type(expected_revision) is not int or isinstance(expected_revision, bool) or expected_revision < 0:
        raise CaseReviewError("draft_field")
    target = _target_version(case_file, draft_id)
    if expected_revision != target["revision"]:
        raise CaseReviewError("stale_revision")
    digest = _text(body.get("expected_text_digest"), limit=80, required=False)
    if digest != target["text_digest"]:
        raise CaseReviewError("stale_revision")
    provenance = _text(body.get("provenance"), limit=32, required=True)
    kind = _DRAFT_SUGGESTION_OPERATIONS[operation]
    if operation == "propose_bounded_change":
        if provenance != "human":
            raise CaseReviewError("draft_field")
        proposed = _text(body.get("proposed_text"), limit=2000, required=True)
        author_kind = "human"
        author = actor_principal_id
    elif operation == "record_draft_model_suggestion":
        if provenance != "model":
            raise CaseReviewError("draft_field")
        proposed = _text(body.get("proposed_text"), limit=2000, required=True)
        author_kind = "model"
        author = _text(body.get("model_id"), limit=80, required=True)
    else:
        if provenance != "machine":
            raise CaseReviewError("draft_field")
        if _text(body.get("proposed_text"), limit=2000, required=False):
            raise CaseReviewError("draft_field")
        proposed = ""
        author_kind = "machine"
        author = _text(body.get("engine_name"), limit=80, required=False) or "machine"
    record = {
        "task_id": "CIMP-UX-32",
        "record_id": _digest("draft-suggestion", operation + "\n" + request_id + "\n" + actor_principal_id),
        "request_id": request_id,
        "operation": operation,
        "record_kind": {"human_reviews": _HUMAN, "model_suggestions": _MODEL, "machine_proofs": _MACHINE}[kind],
        "author_kind": author_kind,
        "provenance": provenance,
        "author": author,
        "actor_principal_id": actor_principal_id,
        "canonical_owner_principal_id": canonical_owner_principal_id,
        "membership": membership,
        "draft_id": draft_id,
        "target_revision": target["revision"],
        "target_text_digest": target["text_digest"],
        "target_author": target["actor_principal_id"],
        "proposed_text": proposed,
        "status": "proposed" if proposed else "referenced",
        "changes_owner_draft": False,
        "adopted_into_owner_draft": False,
        "proof_status": "not_executed" if kind == "machine_proofs" else "",
        "legal_sufficiency": False,
        "governing_legal_authority": False,
    }
    bucket[kind].append(record)
    if json.dumps(_draft_versions(case_file), sort_keys=True, default=str) != before_versions:
        raise CaseReviewError("review_state_mutated")
    projected = project_draft_review_actions(case_file, draft_id=draft_id)
    projected["record"] = dict(record)
    projected["replayed"] = False
    return projected


def accept_draft_suggestion(case_file: MutableMapping[str, Any], body: Mapping[str, Any], *, actor_principal_id: str,
                            canonical_owner_principal_id: str, membership: str, action: str) -> Dict[str, Any]:
    """Mark one suggestion accepted. This does not itself rewrite draft versions."""

    if membership != "owner" or action != "case.update":
        raise CaseReviewError("actor_not_permitted")
    if not isinstance(body, Mapping) or len(json.dumps(body, default=str)) > _BODY_CAP:
        raise CaseReviewError("draft_bounds")
    if _text(body.get("operation"), limit=64, required=True) != "accept_draft_suggestion":
        raise CaseReviewError("draft_field")
    before_versions = json.dumps(_draft_versions(case_file), sort_keys=True, default=str)
    request_id = _text(body.get("request_id"), limit=80, required=True)
    proposal_id = _text(body.get("proposal_id"), limit=80, required=True)
    draft_id = _text(body.get("draft_id"), limit=80, required=True)
    bucket = _suggestion_bucket(case_file)
    for existing in bucket["acceptances"]:
        if existing.get("request_id") == request_id:
            if existing.get("proposal_id") != proposal_id:
                raise CaseReviewError("replay_mismatch")
            projected = project_draft_review_actions(case_file, draft_id=draft_id)
            projected["record"] = dict(existing)
            projected["replayed"] = True
            projected["adopted_text"] = existing.get("adopted_text")
            return projected
    candidates = bucket["human_reviews"] + bucket["model_suggestions"]
    proposal = next((item for item in candidates if item.get("record_id") == proposal_id), None)
    if proposal is None:
        if any(item.get("record_id") == proposal_id for item in bucket["machine_proofs"] + bucket["messages"]):
            raise CaseReviewError("draft_field")
        raise CaseReviewError("proposal_required")
    if proposal.get("status") == "accepted_for_draft":
        raise CaseReviewError("draft_field")
    expected_revision = body.get("expected_revision")
    if type(expected_revision) is not int or expected_revision != proposal.get("target_revision"):
        raise CaseReviewError("stale_revision")
    target = _target_version(case_file, draft_id)
    if target["revision"] != proposal.get("target_revision") or target["text_digest"] != proposal.get("target_text_digest"):
        raise CaseReviewError("stale_revision")
    if _text(body.get("expected_text_digest"), limit=80, required=False) != proposal.get("target_text_digest"):
        raise CaseReviewError("stale_revision")
    adopted = _text(body.get("proposed_text"), limit=2000, required=True)
    if adopted != str(proposal.get("proposed_text") or ""):
        raise CaseReviewError("draft_field")
    proposal["status"] = "accepted_for_draft"
    proposal["accepted_by"] = actor_principal_id
    record = {
        "task_id": "CIMP-UX-32",
        "record_id": _digest("draft-accept", request_id + "\n" + proposal_id),
        "request_id": request_id,
        "operation": "accept_draft_suggestion",
        "record_kind": "owner_acceptance",
        "proposal_id": proposal_id,
        "provenance": proposal.get("provenance"),
        "author": proposal.get("author"),
        "actor_principal_id": actor_principal_id,
        "canonical_owner_principal_id": canonical_owner_principal_id,
        "membership": membership,
        "draft_id": draft_id,
        "target_revision": proposal.get("target_revision"),
        "target_text_digest": proposal.get("target_text_digest"),
        "target_author": proposal.get("target_author"),
        "adopted_text": adopted,
        "status": "accepted_for_draft",
        "changes_owner_draft": False,
        "requires_explicit_owner_save": True,
        "legal_sufficiency": False,
    }
    bucket["acceptances"].append(record)
    if json.dumps(_draft_versions(case_file), sort_keys=True, default=str) != before_versions:
        raise CaseReviewError("review_state_mutated")
    projected = project_draft_review_actions(case_file, draft_id=draft_id)
    projected["record"] = dict(record)
    projected["adopted_text"] = adopted
    projected["replayed"] = False
    return projected


def _require_draft_body(body: Mapping[str, Any], operation: str) -> None:
    if not isinstance(body, Mapping) or len(json.dumps(body, default=str)) > _BODY_CAP:
        raise CaseReviewError("draft_bounds")
    requested = body.get("operation", operation)
    if requested in {"file_with_court", "court_filing", "automatic_filing"}:
        raise CaseReviewError("automatic_filing_refused")
    if requested != operation:
        raise CaseReviewError("draft_field")
    if body.get("legal_sufficiency") is True or body.get("court_filed") is True or body.get("governing_law") is True:
        raise CaseReviewError("legal_sufficiency_refused")


def _require_stage_snapshot(projection: Mapping[str, Any], body: Mapping[str, Any]) -> Dict[str, int]:
    if projection["stage"] != "draft_review":
        raise CaseReviewError("stage_not_ready")
    snapshot = _domain_snapshot(projection["domains"])
    for name in _WORKFLOW_DOMAINS:
        key = "expected_" + name + "_revision"
        if key in body and body.get(key) != snapshot[name]:
            raise CaseReviewError("stale_domain")
    return snapshot


def version_draft(case_file: MutableMapping[str, Any], body: Mapping[str, Any], *, actor_principal_id: str,
                  membership: str, action: str) -> Dict[str, Any]:
    """Store one owner draft revision bound to the current domain snapshot."""

    if isinstance(body, Mapping) and body.get("operation") == "accept_draft_suggestion":
        return accept_draft_suggestion(
            case_file, body, actor_principal_id=actor_principal_id,
            canonical_owner_principal_id=str(case_file.get("canonical_owner_principal_id") or actor_principal_id),
            membership=membership, action=action,
        )
    _require_draft_body(body, "version_draft")
    if membership != "owner" or action != "case.update":
        raise CaseReviewError("actor_not_permitted")
    projection = project_workflow_stage(case_file)
    snapshot = _require_stage_snapshot(projection, body)
    text = _text(body.get("text"), limit=4000, required=True)
    draft_id = _text(body.get("draft_id"), limit=80, required=True)
    request_id = _text(body.get("request_id"), limit=80, required=True)
    store = _draft_store(case_file)
    for existing in store["versions"]:
        if existing.get("request_id") == request_id:
            if existing.get("draft_id") != draft_id or existing.get("text") != text:
                raise CaseReviewError("replay_mismatch")
            projected = project_workflow_stage(case_file)
            projected["record"] = {key: existing[key] for key in existing if key != "text"}
            projected["replayed"] = True
            projected["text_digest"] = existing["text_digest"]
            return projected
    revision = 1 + max((int(item.get("revision") or 0) for item in store["versions"] if item.get("draft_id") == draft_id), default=0)
    record = {
        "task_id": WORKFLOW_STAGE_TASK_ID,
        "operation": "version_draft",
        "request_id": request_id,
        "draft_id": draft_id,
        "revision": revision,
        "text": text,
        "text_digest": _digest("draft-version", draft_id + "\n" + str(revision) + "\n" + text),
        "domain_snapshot": snapshot,
        "actor_principal_id": actor_principal_id,
        "membership": membership,
        "legal_sufficiency": False,
        "court_filed": False,
        "automatic_court_filing": False,
    }
    store["versions"].append(record)
    projected = project_workflow_stage(case_file)
    projected["record"] = {key: record[key] for key in record if key != "text"}
    projected["text_digest"] = record["text_digest"]
    projected["replayed"] = False
    return projected


def _section_review_rows(case_file: Mapping[str, Any]) -> list:
    stored = case_file.get("section_review_records")
    return [item for item in stored if isinstance(item, dict)] if isinstance(stored, list) else []


def _section_review_bucket(case_file: MutableMapping[str, Any]) -> list:
    stored = case_file.get("section_review_records")
    if not isinstance(stored, list):
        stored = []
        case_file["section_review_records"] = stored
    return stored


def _refuse_owner_key_material(body: Mapping[str, Any]) -> None:
    for key, value in body.items():
        if key in _OWNER_KEY_FIELDS and value not in (None, "", False):
            raise CaseReviewError("actor_not_permitted")
        if isinstance(value, Mapping) and any(name in value and value.get(name) not in (None, "", False) for name in _OWNER_KEY_FIELDS):
            raise CaseReviewError("actor_not_permitted")


def _catalog_int(value: Any) -> int:
    return value if type(value) is int and not isinstance(value, bool) and value > 0 else 0


def _span_pair(value: Mapping[str, Any]) -> tuple:
    span = value.get("span") if isinstance(value.get("span"), Mapping) else value
    start = span.get("start", span.get("span_start"))
    end = span.get("end", span.get("span_end"))
    if type(start) is int and type(end) is int and not isinstance(start, bool) and not isinstance(end, bool) and 0 <= start < end <= 1_000_000:
        return start, end
    return None


def bound_review_targets(case_file: Mapping[str, Any]) -> list:
    """Exact review anchors currently stored on the case. Qualified targets are not invented here."""

    targets = []
    domains = _workflow_domains(case_file)
    for item in domains["factual"].get("assertions") or []:
        if isinstance(item, dict) and str(item.get("id") or "").strip() and _catalog_int(item.get("revision")):
            targets.append({
                "target_kind": "fact", "qualification": "exact", "target_id": str(item.get("id")).strip(),
                "target_revision": item.get("revision"),
            })
    legal = domains["legal"]
    if str(legal.get("authority_id") or "").strip() and _catalog_int(legal.get("revision")):
        targets.append({
            "target_kind": "legal_admission", "qualification": "exact",
            "target_id": str(legal.get("authority_id")).strip(), "target_revision": legal.get("revision"),
        })
    for item in domains["evidence"].get("exhibits") or []:
        if not isinstance(item, dict):
            continue
        artifact_id = str(item.get("artifact_id") or "").strip()
        version = _catalog_int(item.get("artifact_version", item.get("version")))
        span = _span_pair(item)
        if artifact_id and version and span is not None:
            targets.append({
                "target_kind": "evidence_span", "qualification": "exact", "artifact_id": artifact_id,
                "artifact_version": version, "span_start": span[0], "span_end": span[1], "target_revision": version,
                "target_id": artifact_id,
            })
    state = case_file.get("review_case_state") if isinstance(case_file.get("review_case_state"), dict) else {}
    for kind, target_kind in (("answers", "answer"), ("facts", "fact"), ("legal_admissions", "legal_admission"), ("draft_revisions", "draft_revision")):
        bucket = state.get(kind)
        rows = bucket.values() if isinstance(bucket, dict) else bucket if isinstance(bucket, list) else []
        for item in rows:
            if not isinstance(item, dict):
                continue
            target_id = str(item.get("id") or item.get("target_id") or "").strip()
            revision = _catalog_int(item.get("revision"))
            if target_id and revision:
                targets.append({"target_kind": target_kind, "qualification": "exact", "target_id": target_id, "target_revision": revision})
    versions = _draft_versions(case_file)
    requirements = []
    stored = case_file.get("derived_dependency_requirements")
    if isinstance(stored, dict):
        requirements = [item for item in stored.get("requirements") or [] if isinstance(item, dict)]
    for version in versions:
        draft_id = str(version.get("draft_id") or "").strip()
        revision = _catalog_int(version.get("revision"))
        if not draft_id or not revision:
            continue
        targets.append({
            "target_kind": "draft_revision", "qualification": "exact", "target_id": draft_id,
            "draft_id": draft_id, "target_revision": revision,
        })
        for item in requirements:
            section_id = str(item.get("requirement_id") or item.get("passage_id") or "").strip()
            if section_id:
                targets.append({
                    "target_kind": "complaint_section", "qualification": "exact", "section_id": section_id,
                    "target_id": section_id, "draft_id": draft_id, "target_revision": revision,
                })
    unique = []
    seen = set()
    for target in targets:
        key = json.dumps({name: target.get(name) for name in ("target_kind", "target_id", "artifact_id", "artifact_version", "span_start", "span_end", "section_id", "draft_id", "target_revision")}, sort_keys=True)
        if key not in seen:
            seen.add(key)
            unique.append(target)
    return unique


def _target_identity(target: Mapping[str, Any]) -> str:
    material = {name: target.get(name) for name in (
        "target_kind", "qualification", "target_id", "artifact_id", "artifact_version",
        "span_start", "span_end", "section_id", "draft_id", "target_revision", "qualification_reason",
    )}
    return _digest("review-target", json.dumps(material, sort_keys=True, default=str))


def _normalize_review_target(case_file: Mapping[str, Any], body: Mapping[str, Any]) -> Dict[str, Any]:
    kind = _text(body.get("target_kind"), limit=40, required=True)
    if kind not in _REVIEW_TARGETS:
        raise CaseReviewError("review_field")
    expected = body.get("expected_target_revision", body.get("target_revision"))
    if type(expected) is not int or isinstance(expected, bool) or expected < 1:
        raise CaseReviewError("review_field")
    catalog = bound_review_targets(case_file)
    if kind == "qualified_evidence_span":
        artifact_id = _text(body.get("artifact_id"), limit=120, required=True)
        version = body.get("artifact_version")
        if type(version) is not int or isinstance(version, bool) or version < 1 or version != expected:
            raise CaseReviewError("stale_revision")
        reason = _text(body.get("qualification_reason"), limit=200, required=True)
        if _text(body.get("qualification"), limit=40, required=False) not in {"", "qualified"}:
            raise CaseReviewError("review_field")
        start = body.get("span_start")
        end = body.get("span_end")
        if start is not None or end is not None:
            if type(start) is not int or type(end) is not int or isinstance(start, bool) or isinstance(end, bool) or not 0 <= start < end <= 1_000_000:
                raise CaseReviewError("review_field")
            exact = any(
                item.get("target_kind") == "evidence_span" and item.get("artifact_id") == artifact_id
                and item.get("artifact_version") == version and item.get("span_start") == start and item.get("span_end") == end
                for item in catalog
            )
            if exact:
                raise CaseReviewError("review_field")
        else:
            start = end = None
        return {
            "target_kind": kind, "qualification": "qualified", "qualification_reason": reason,
            "artifact_id": artifact_id, "artifact_version": version, "span_start": start, "span_end": end,
            "target_id": artifact_id, "target_revision": version, "exact_span": False,
        }
    if kind == "evidence_span":
        artifact_id = _text(body.get("artifact_id") or body.get("target_id"), limit=120, required=True)
        version = body.get("artifact_version", expected)
        start = body.get("span_start")
        end = body.get("span_end")
        if type(version) is not int or isinstance(version, bool) or version != expected:
            raise CaseReviewError("stale_revision")
        if type(start) is not int or type(end) is not int or isinstance(start, bool) or isinstance(end, bool) or not 0 <= start < end <= 1_000_000:
            raise CaseReviewError("review_field")
        matched = next((
            item for item in catalog
            if item.get("target_kind") == "evidence_span" and item.get("artifact_id") == artifact_id
            and item.get("artifact_version") == version and item.get("span_start") == start and item.get("span_end") == end
        ), None)
        if matched is None:
            raise CaseReviewError("stale_revision")
        return {
            "target_kind": kind, "qualification": "exact", "artifact_id": artifact_id, "artifact_version": version,
            "span_start": start, "span_end": end, "target_id": artifact_id, "target_revision": version, "exact_span": True,
        }
    if kind == "complaint_section":
        section_id = _text(body.get("section_id") or body.get("target_id"), limit=80, required=True)
        draft_id = _text(body.get("draft_id"), limit=80, required=True)
        matched = next((
            item for item in catalog
            if item.get("target_kind") == "complaint_section" and item.get("section_id") == section_id
            and item.get("draft_id") == draft_id and item.get("target_revision") == expected
        ), None)
        if matched is None:
            raise CaseReviewError("stale_revision")
        return {
            "target_kind": kind, "qualification": "exact", "section_id": section_id, "draft_id": draft_id,
            "target_id": section_id, "target_revision": expected, "exact_span": False,
        }
    target_id = _text(body.get("target_id"), limit=80, required=True)
    matched = next((
        item for item in catalog
        if item.get("target_kind") == kind and item.get("target_id") == target_id and item.get("target_revision") == expected
    ), None)
    if matched is None:
        raise CaseReviewError("stale_revision")
    normalized = {"target_kind": kind, "qualification": "exact", "target_id": target_id, "target_revision": expected, "exact_span": False}
    if kind == "draft_revision":
        normalized["draft_id"] = target_id
    return normalized


def record_section_review(case_file: MutableMapping[str, Any], body: Mapping[str, Any], *, actor_principal_id: str,
                          canonical_owner_principal_id: str, membership: str, action: str, case_id: str = "") -> Dict[str, Any]:
    """Comment, accept, or reject a bound review target without using the owner master key."""

    if not isinstance(body, Mapping) or len(json.dumps(body, default=str)) > _BODY_CAP:
        raise CaseReviewError("review_bounds")
    _refuse_owner_key_material(body)
    if body.get("actor_principal_id") not in (None, "", actor_principal_id):
        raise CaseReviewError("actor_not_permitted")
    if membership not in {"owner", "assigned-lawyer"} or action != "case.review":
        raise CaseReviewError("actor_not_permitted")
    operation = _text(body.get("operation"), limit=40, required=True)
    if operation not in _SECTION_REVIEW_OPERATIONS:
        raise CaseReviewError("review_field")
    decision = {"comment_review_target": "comment", "accept_review_target": "accept", "reject_review_target": "reject"}[operation]
    request_id = _text(body.get("request_id"), limit=80, required=True)
    rows = _section_review_bucket(case_file)
    submitted_body = _text(body.get("body"), limit=2000, required=False)
    if decision == "comment" and not submitted_body:
        raise CaseReviewError("review_field")
    for existing in rows:
        if existing.get("request_id") == request_id:
            if (existing.get("actor_principal_id") != actor_principal_id or existing.get("operation") != operation
                    or existing.get("body") != submitted_body):
                raise CaseReviewError("replay_mismatch")
            projected = project_draft_review_actions(case_file)
            projected["record"] = dict(existing)
            projected["replayed"] = True
            return projected
    target = _normalize_review_target(case_file, body)
    identity = _target_identity(target)
    comment_id = _text(body.get("comment_id"), limit=80, required=decision != "comment")
    parent = None
    if decision != "comment":
        parent = next((item for item in rows if item.get("record_id") == comment_id and item.get("decision") == "comment"), None)
        if parent is None or parent.get("target_identity") != identity:
            raise CaseReviewError("review_field")
        if parent.get("status") in {"accepted", "rejected"}:
            raise CaseReviewError("review_field")
    else:
        comment_id = ""
    before_targets = json.dumps(bound_review_targets(case_file), sort_keys=True)
    before_versions = json.dumps(_draft_versions(case_file), sort_keys=True, default=str)
    lineage = [item.get("record_id") for item in rows if item.get("target_identity") == identity]
    record = {
        "task_id": "CIMP-UX-33",
        "record_id": _digest("section-review", operation + "\n" + request_id + "\n" + actor_principal_id),
        "request_id": request_id,
        "operation": operation,
        "decision": decision,
        "item_type": "review_comment",
        "actor_principal_id": actor_principal_id,
        "canonical_owner_principal_id": canonical_owner_principal_id,
        "actor_is_canonical_owner": actor_principal_id == canonical_owner_principal_id,
        "membership": membership,
        "action_scope": action,
        "case_id": case_id,
        "body": submitted_body,
        "comment_id": comment_id or "",
        "target_identity": identity,
        "target": target,
        "target_kind": target["target_kind"],
        "target_id": target.get("target_id") or "",
        "target_revision": target["target_revision"],
        "qualification": target["qualification"],
        "seen_review_revision": body.get("expected_review_revision") if type(body.get("expected_review_revision")) is int else None,
        "lineage": lineage,
        "previous_record_id": lineage[-1] if lineage else "",
        "status": {"comment": "commented", "accept": "accepted", "reject": "rejected"}[decision],
        "uses_owner_master_key": False,
        "updates_case_state": False,
        "changes_owner_draft": False,
        "legal_sufficiency": False,
        "governing_legal_authority": False,
    }
    record.update({key: target.get(key) for key in ("artifact_id", "artifact_version", "span_start", "span_end", "section_id", "draft_id", "qualification_reason", "exact_span") if key in target})
    rows.append(record)
    if decision != "comment" and parent is not None:
        parent["status"] = record["status"]
        parent["resolved_by"] = actor_principal_id
        parent["resolved_record_id"] = record["record_id"]
    if json.dumps(bound_review_targets(case_file), sort_keys=True) != before_targets:
        raise CaseReviewError("review_state_mutated")
    if json.dumps(_draft_versions(case_file), sort_keys=True, default=str) != before_versions:
        raise CaseReviewError("review_state_mutated")
    projected = project_draft_review_actions(case_file)
    projected["record"] = dict(record)
    projected["replayed"] = False
    return projected


def review_draft_version(case_file: MutableMapping[str, Any], body: Mapping[str, Any], *, actor_principal_id: str,
                         membership: str, action: str) -> Dict[str, Any]:
    """Review one draft revision. Acceptance authorizes export only."""

    if isinstance(body, Mapping) and body.get("operation") in _SECTION_REVIEW_OPERATIONS:
        return record_section_review(
            case_file, body, actor_principal_id=actor_principal_id,
            canonical_owner_principal_id=str(case_file.get("canonical_owner_principal_id") or ""),
            membership=membership, action=action, case_id=str(case_file.get("case_id") or ""),
        )
    if isinstance(body, Mapping) and body.get("operation") in _DRAFT_SUGGESTION_OPERATIONS:
        return submit_draft_suggestion(
            case_file, body, actor_principal_id=actor_principal_id,
            canonical_owner_principal_id=str(case_file.get("canonical_owner_principal_id") or ""),
            membership=membership, action=action,
        )
    _require_draft_body(body, "review_draft")
    if membership not in {"owner", "assigned-lawyer"} or action != "case.review":
        raise CaseReviewError("actor_not_permitted")
    projection = project_workflow_stage(case_file)
    snapshot = _domain_snapshot(projection["domains"])
    draft_id = _text(body.get("draft_id"), limit=80, required=True)
    request_id = _text(body.get("request_id"), limit=80, required=True)
    decision = _text(body.get("decision"), limit=40, required=True)
    if decision not in {"withheld", "commented", "accepted_for_export"}:
        raise CaseReviewError("draft_field")
    expected_revision = body.get("expected_revision")
    if type(expected_revision) is not int:
        raise CaseReviewError("draft_field")
    store = _draft_store(case_file)
    for existing in store["reviews"]:
        if existing.get("request_id") == request_id:
            if existing.get("draft_id") != draft_id or existing.get("decision") != decision or existing.get("draft_revision") != expected_revision:
                raise CaseReviewError("replay_mismatch")
            projected = project_workflow_stage(case_file)
            projected["record"] = dict(existing)
            projected["replayed"] = True
            return projected
    version = next((item for item in store["versions"] if item.get("draft_id") == draft_id and item.get("revision") == expected_revision), None)
    if version is None:
        raise CaseReviewError("draft_revision_required")
    if projection["stage"] != "draft_review" or version.get("domain_snapshot") != snapshot:
        raise CaseReviewError("stale_domain")
    digest = _text(body.get("expected_text_digest"), limit=80, required=True)
    if digest != version.get("text_digest"):
        raise CaseReviewError("stale_revision")
    record = {
        "task_id": WORKFLOW_STAGE_TASK_ID,
        "operation": "review_draft",
        "request_id": request_id,
        "draft_id": draft_id,
        "draft_revision": expected_revision,
        "decision": decision,
        "expected_text_digest": digest,
        "domain_snapshot": dict(version["domain_snapshot"]),
        "actor_principal_id": actor_principal_id,
        "membership": membership,
        "authorizes_export": decision == "accepted_for_export",
        "legal_sufficiency": False,
        "court_filed": False,
        "automatic_court_filing": False,
        "governing_law": False,
    }
    store["reviews"].append(record)
    projected = project_workflow_stage(case_file)
    projected["record"] = dict(record)
    projected["replayed"] = False
    return projected


def export_draft_version(case_file: MutableMapping[str, Any], body: Mapping[str, Any], *, actor_principal_id: str,
                         membership: str, action: str) -> Dict[str, Any]:
    """Export one reviewed revision. The result is not a court filing."""

    _require_draft_body(body, "export_draft")
    if action != "case.download" or membership not in {"owner", "assigned-lawyer"}:
        raise CaseReviewError("export_authorization_required")
    projection = project_workflow_stage(case_file)
    snapshot = _domain_snapshot(projection["domains"])
    draft_id = _text(body.get("draft_id"), limit=80, required=True)
    request_id = _text(body.get("request_id"), limit=80, required=True)
    expected_revision = body.get("expected_revision")
    if type(expected_revision) is not int:
        raise CaseReviewError("draft_field")
    store = _draft_store(case_file)
    for existing in store["exports"]:
        if existing.get("request_id") == request_id:
            if existing.get("draft_id") != draft_id or existing.get("draft_revision") != expected_revision:
                raise CaseReviewError("replay_mismatch")
            projected = project_workflow_stage(case_file)
            projected["record"] = dict(existing)
            projected["replayed"] = True
            return projected
    version = next((item for item in store["versions"] if item.get("draft_id") == draft_id and item.get("revision") == expected_revision), None)
    if version is None:
        raise CaseReviewError("draft_revision_required")
    if projection["stage"] != "draft_review" or version.get("domain_snapshot") != snapshot:
        raise CaseReviewError("stale_domain")
    review = _accepted_review(store, draft_id, expected_revision, snapshot)
    if review is None:
        raise CaseReviewError("review_required")
    record = {
        "task_id": WORKFLOW_STAGE_TASK_ID,
        "operation": "export_draft",
        "request_id": request_id,
        "export_id": _digest("draft-export", request_id + "\n" + draft_id + "\n" + str(expected_revision)),
        "draft_id": draft_id,
        "draft_revision": expected_revision,
        "text_digest": version["text_digest"],
        "review_request_id": review["request_id"],
        "domain_snapshot": dict(snapshot),
        "actor_principal_id": actor_principal_id,
        "membership": membership,
        "authorization_scope": "case.download",
        "legal_sufficiency": False,
        "court_filed": False,
        "automatic_court_filing": False,
        "governing_law": False,
        "status": "exported",
    }
    store["exports"].append(record)
    projected = project_workflow_stage(case_file)
    projected["record"] = dict(record)
    projected["replayed"] = False
    return projected


def submit_lawyer_review(mediator: Any, body: Mapping[str, Any], **scope) -> Dict[str, Any]:
    """Legacy pure reported-record helper; mounted routes use the encrypted owner."""
    return submit_review_record(_case_file(mediator), body, **scope)


def render_lawyer_workspace(projection: Mapping[str, Any]) -> str:
    """Fill the lawyer workspace template. The page does not treat stale rows as current."""

    template = _TEMPLATE.read_text(encoding="utf-8")
    payload = json.dumps(projection, sort_keys=True)
    safe = payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    if "__LAWYER_REVIEW_JSON__" not in template:
        raise CaseReviewError("lawyer_review_unavailable")
    return template.replace("__LAWYER_REVIEW_JSON__", safe)


def mount_lawyer_review_routes(app: Any) -> None:
    """Only the explicitly configured encrypted review owner serves this prefix."""
    from fastapi.responses import HTMLResponse, JSONResponse
    from starlette.concurrency import run_in_threadpool
    from applications.case_review_store import CaseReviewService, CaseReviewStoreError
    from applications.workspace_case_authority import current_workspace_case_authority

    def context(request, case_id):
        service = getattr(request.app.state, 'case_reviews', None)
        decision = getattr(request.state, 'case_authorization', None)
        authority = current_workspace_case_authority()
        if type(service) is not CaseReviewService:
            raise CaseReviewStoreError('review_unavailable')
        if decision is None or decision.case_id != case_id or authority is None:
            raise CaseReviewStoreError('lawyer_review_ungranted')
        return service, decision, authority

    def failed(exc):
        code = str(getattr(exc, 'code', '') or 'review_unavailable')
        allowed = {'lawyer_assignment_required','lawyer_review_ungranted','cross_case_id','review_key_locked',
            'review_source_changed','review_source_unbound','review_unavailable','review_integrity','review_key_grant_required',
            'review_membership_required','lawyer_review_field','lawyer_review_bounds','stale_revision','stale_approval',
            'replay_mismatch','proof_producer_unavailable','owner_share_required','recipient_review_grant_required',
            'proposal_required','approval_required','model_cannot_approve','machine_proof_cannot_approve',
            'review_transition_owner_unavailable','review_field','review_bounds','revision_conflict',
            'review_target_capability_unavailable','proposal_already_accepted','unlock_needed'}
        if code not in allowed:
            code = 'lawyer_review_ungranted' if code in {'grant_revoked','key_grant_rejected','late_result_after_cutoff',
                'membership_removed','membership_expired','workspace_authorization_denied','actor_not_permitted'} else 'review_unavailable'
        status = 409 if code in {'stale_revision','stale_approval','replay_mismatch','review_source_changed','revision_conflict','proposal_already_accepted'} else 422 if code in {
            'lawyer_review_field','lawyer_review_bounds','review_field','review_bounds'} else 503 if code in {'review_unavailable','review_key_locked',
            'review_source_unbound','proof_producer_unavailable','recipient_review_grant_required','review_transition_owner_unavailable',
            'review_target_capability_unavailable','unlock_needed'} else 403
        return JSONResponse({'task_id':TASK_ID,'error':code,'status':'unavailable' if status==503 else 'refused',
            'human_legal_reviews':[],'model_suggestions':[],'machine_proofs':[],'proof':False,
            'governing_legal_authority':False,'legal_sufficiency':False,'admitted_law':False,
            'promotes_changed_law':False,'promotes_changed_facts':False,
            'message':'Complaint changed; owner must share latest version.' if code=='review_source_changed' else 'Review access could not be verified.'},status_code=status)

    async def projection(request,case_id):
        service,decision,authority=context(request,case_id)
        value=await run_in_threadpool(service.read,decision.actor_principal_id,case_id=case_id,authority=authority)
        value.update(actor_principal_id=decision.actor_principal_id,
            case_context={'tenant_id':decision.tenant_id,'case_id':case_id,'resource_id':decision.resource_id,
                'revision':decision.revision,'membership_revision':decision.membership_revision},
            session_generation=request.state.browser_principal.generation)
        return value

    @app.get(LAWYER_WORKSPACE_ROUTE)
    async def read_lawyer_workspace(case_id: str, request: Request):
        try:
            return HTMLResponse(render_lawyer_workspace(await projection(request,case_id)))
        except Exception as exc:
            return failed(exc)

    @app.get(LAWYER_REVIEW_ROUTE)
    async def read_lawyer_reviews(case_id: str, request: Request):
        try:
            return JSONResponse(await projection(request,case_id))
        except Exception as exc:
            return failed(exc)

    @app.post(LAWYER_REVIEW_ROUTE)
    async def write_lawyer_review(case_id: str, request: Request):
        try:
            service,decision,authority=context(request,case_id)
            value=await run_in_threadpool(service.write,decision.actor_principal_id,case_id=case_id,
                request=await request.json(),authority=authority)
            return JSONResponse(value)
        except Exception as exc:
            return failed(exc)

    @app.get(LAWYER_REVIEW_ROUTE+'/sharing')
    async def read_sharing(case_id: str, request: Request):
        try:
            service,decision,authority=context(request,case_id)
            return JSONResponse(await run_in_threadpool(service.sharing_status,decision.actor_principal_id,
                case_id=case_id,authority=authority))
        except Exception as exc:
            return failed(exc)

    @app.post(LAWYER_REVIEW_ROUTE+'/share')
    async def share_review_source(case_id: str, request: Request):
        try:
            service,decision,authority=context(request,case_id)
            return JSONResponse(await run_in_threadpool(service.share_source,decision.actor_principal_id,
                case_id=case_id,request=await request.json(),authority=authority))
        except Exception as exc:
            return failed(exc)

    @app.get(REVIEW_ITEMS_ROUTE)
    async def read_review_items(case_id: str, request: Request):
        try:
            service,decision,authority=context(request,case_id)
            value=await run_in_threadpool(service.read,decision.actor_principal_id,case_id=case_id,authority=authority)
            return JSONResponse({**value['collaborative_reviews'],'case_id':case_id,'review_revision':value['review_revision'],
                'private_revision':value['private_revision'],'live_revisions':value['live_revisions'],'read_only':True})
        except Exception as exc:return failed(exc)

    @app.post(REVIEW_ITEMS_ROUTE)
    async def write_review_items(case_id: str, request: Request):
        try:
            service,decision,authority=context(request,case_id)
            return JSONResponse(await run_in_threadpool(service.write_item,decision.actor_principal_id,case_id=case_id,
                request=await request.json(),authority=authority))
        except Exception as exc:return failed(exc)

    @app.post(REVIEW_TRANSITIONS_ROUTE)
    async def write_review_transition(case_id: str, request: Request):
        try:
            service,decision,authority=context(request,case_id)
            return JSONResponse(await run_in_threadpool(service.accept_owner_transition,decision.actor_principal_id,
                case_id=case_id,request=await request.json(),authority=authority))
        except Exception as exc:return failed(exc)
