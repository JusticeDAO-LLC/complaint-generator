"""Assigned-lawyer case review workspace.

The list contains only cases where the caller holds an accepted membership
and a separate accepted case-action grant for ``case.read``. A lawyer role,
an operational-admin role, or a stale grant does not open case content.
Expired and removed memberships drop out of the list and deny an already
open session. Factual assertions and legal source rules are projected as
different graphs. This module does not decrypt the owner catalog and does
not call operational-admin actions.
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Mapping

from starlette.requests import Request

from applications.case_access import CaseAccessError, CaseActionAuthorizer
from applications.case_membership import CaseMembershipError, CaseMembershipStore
from applications.case_message_api import CaseMessageService
from applications.case_routes import CaseHandlerRegistry

TASK_ID = "CIMP-GUI-45"
LAWYER_WORKSPACE_PAGE = "/lawyer-workspace"
LAWYER_WORKSPACE_API = "/api/cases/lawyer-workspace"
_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "lawyer_workspace.html"
_EMPTY_REVIEW = {
    "live_revisions": {},
    "human_legal_reviews": [],
    "model_suggestions": [],
    "machine_proofs": [],
}
_LIMITATIONS = (
    "Only an accepted assigned-lawyer membership plus an explicit case.read grant is listed.",
    "Operational admin authority is not a case-content bypass.",
    "Expired and revoked memberships disappear from the list and are denied on a later read.",
    "Factual graph rows are user assertions. Legal graph rows are source passages. Facts do not rewrite rules.",
    "Unresolved proof and declared work stay unresolved. Private messages stay conversations.",
    "This workspace does not claim WebSocket or SSE support and is not governing law.",
)


class LawyerWorkspaceError(Exception):
    def __init__(self, code: str) -> None:
        self.code = str(code)
        super().__init__(self.code)


def lawyer_workspace_http_status(code: str) -> int:
    if code in {"unauthenticated", "missing_principal"}:
        return 401
    if code == "lawyer_workspace_unavailable":
        return 503
    return 403


def _clock_value(clock) -> int:
    value = clock() if callable(clock) else clock
    if type(value) is not int or isinstance(value, bool):
        raise LawyerWorkspaceError("lawyer_workspace_unavailable")
    return value


def _content_grant(authorizer: CaseActionAuthorizer, actor: str, case_id: str):
    """Process-memory action grant. Membership expiry is checked separately."""

    grants = getattr(authorizer, "_grants", None)
    if not isinstance(grants, dict):
        return None
    grant = grants.get((actor, case_id))
    if grant is None or grant.status != "accepted" or "case.read" not in grant.actions:
        return None
    return grant


def _membership_for(memberships: CaseMembershipStore, actor: str, case_id: str):
    matches = [
        grant for grant in memberships.recover()
        if grant.member_principal_id == actor and grant.case_id == case_id
    ]
    if not matches:
        return None
    matches.sort(key=lambda item: (item.version, item.grant_id))
    return matches[-1]


def _authorize_content(authorizer: CaseActionAuthorizer, actor: str, membership) -> Any:
    content = _content_grant(authorizer, actor, membership.case_id)
    if content is None:
        raise LawyerWorkspaceError("role_does_not_grant_case_access")
    if content.tenant_id != membership.tenant_id or content.resource_id != membership.resource_id:
        raise LawyerWorkspaceError("missing_case")
    try:
        decision = authorizer.authorize(
            boundary="http",
            actor_principal_id=actor,
            tenant_id=membership.tenant_id,
            case_id=membership.case_id,
            resource_id=membership.resource_id,
            action="case.read",
            expected_revision=content.case_revision,
            expected_membership_revision=content.revision,
            trust="authenticated",
        )
    except CaseAccessError as exc:
        if exc.code == "role_does_not_grant_case_access":
            raise LawyerWorkspaceError("role_does_not_grant_case_access") from exc
        raise LawyerWorkspaceError("missing_case") from exc
    if (decision.membership != "assigned-lawyer" or decision.permits_case_content is not True
            or decision.actor_is_encrypted_owner is True):
        raise LawyerWorkspaceError("role_does_not_grant_case_access")
    if decision.actor_principal_id == decision.canonical_owner_principal_id:
        raise LawyerWorkspaceError("role_does_not_grant_case_access")
    return decision


def _require_live_membership(membership, now: int) -> None:
    if membership is None:
        raise LawyerWorkspaceError("missing_case")
    if membership.status == "removed":
        raise LawyerWorkspaceError("membership_removed")
    if membership.status == "declined":
        raise LawyerWorkspaceError("membership_declined")
    if membership.status == "pending":
        raise LawyerWorkspaceError("membership_pending")
    if membership.status != "accepted":
        raise LawyerWorkspaceError("membership_required")
    if "case.read" not in membership.actions:
        raise LawyerWorkspaceError("action_not_permitted")
    if now >= membership.expires_at:
        raise LawyerWorkspaceError("grant_expired")


def list_assigned_cases(*, actor_principal_id: str, authorizer: CaseActionAuthorizer,
                        memberships: CaseMembershipStore, now: int) -> dict[str, Any]:
    """Public case ids only. Graph text and messages stay on the case read."""

    rows = []
    for grant in memberships.recover():
        if grant.member_principal_id != actor_principal_id or grant.status != "accepted":
            continue
        if now >= grant.expires_at or "case.read" not in grant.actions:
            continue
        try:
            decision = _authorize_content(authorizer, actor_principal_id, grant)
        except LawyerWorkspaceError:
            continue
        rows.append({
            "case_id": grant.case_id,
            "tenant_id": grant.tenant_id,
            "resource_id": grant.resource_id,
            "grant_id": grant.grant_id,
            "membership_version": grant.version,
            "membership": decision.membership,
            "state": "authorized",
            "expires_at": grant.expires_at,
            "actor_is_encrypted_owner": False,
            "canonical_owner_principal_id": decision.canonical_owner_principal_id,
            "admin_bypass": False,
            "plaintext_available": False,
        })
    rows.sort(key=lambda item: item["case_id"])
    return {
        "task_id": TASK_ID,
        "actor_principal_id": actor_principal_id,
        "membership": "assigned-lawyer",
        "cases": rows,
        "admin_bypass": False,
        "permits_operational_admin": False,
        "transport": {"http": True, "websocket": False, "sse": False},
        "limitations": list(_LIMITATIONS),
    }


def _rows(values, *, kind: str) -> list[dict[str, Any]]:
    rows = []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return rows
    for index, value in enumerate(values):
        if isinstance(value, str) and value.strip():
            rows.append({"graph_kind": kind, "item_id": f"{kind}-{index}", "text": value, "source_id": ""})
        elif isinstance(value, dict):
            text = str(value.get("text") or value.get("summary") or value.get("rule_text") or "")
            source_id = str(value.get("source_id") or value.get("source_identity") or value.get("event_id") or value.get("work_id") or "")
            if text or source_id:
                rows.append({
                    "graph_kind": kind,
                    "item_id": str(value.get("item_id") or value.get("work_id") or value.get("event_id") or f"{kind}-{index}"),
                    "text": text,
                    "source_id": source_id,
                    "status": str(value.get("status") or value.get("proof_status") or value.get("kind") or ""),
                    "at": str(value.get("at") or ""),
                })
    return rows


def project_case_review(case_file: Mapping[str, Any] | None, *, case_id: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Split factual assertions from legal source text without treating either as law."""

    material = case_file if isinstance(case_file, Mapping) else {}
    source = material.get("review_source_anchor") if isinstance(material.get("review_source_anchor"), Mapping) else {}
    legal_items = []
    if source:
        legal_items.append({
            "graph_kind": "legal",
            "item_id": str(source.get("source_identity") or "legal-source"),
            "text": str(source.get("source_text") or ""),
            "source_id": str(source.get("source_identity") or ""),
            "status": "source_passage",
        })
    factual = {
        "graph_kind": "factual",
        "distinction": "User assertions and evidence. These rows are not legal rules.",
        "items": _rows(material.get("review_fact_anchor"), kind="factual"),
        "rewrites_legal_rules": False,
    }
    legal = {
        "graph_kind": "legal",
        "distinction": "Source passages and admitted-rule candidates. Factual answers do not rewrite these rules.",
        "items": legal_items,
        "user_facts_are_not_law": True,
        "governing_legal_authority": False,
        "legal_sufficiency": False,
    }
    unresolved = _rows(material.get("unresolved_work"), kind="unresolved")
    obligations = []
    proof = material.get("proof_trace_display")
    if isinstance(proof, Mapping) and isinstance(proof.get("obligations"), list):
        obligations = proof["obligations"]
    for item in obligations:
        if not isinstance(item, dict):
            continue
        status = str(item.get("proof_status") or "not_executed")
        if status != "executed":
            unresolved.append({
                "graph_kind": "unresolved",
                "item_id": str(item.get("obligation_id") or "obligation"),
                "text": "Proof is not executed for " + str(item.get("source_identity") or item.get("obligation_id") or "obligation"),
                "source_id": str(item.get("source_identity") or ""),
                "status": status,
            })
    timeline = _rows(material.get("case_timeline"), kind="timeline")
    private = []
    for message in messages:
        if not isinstance(message, dict) or message.get("case_id") != case_id:
            continue
        private.append({
            "message_id": message.get("message_id"),
            "thread_id": message.get("thread_id"),
            "case_id": case_id,
            "sender_principal_id": message.get("sender_principal_id"),
            "text": message.get("text") or "",
            "disposition": message.get("disposition") or "conversation",
            "adopted_as_evidence": False,
            "governing_legal_authority": False,
        })
    return {
        "task_id": TASK_ID,
        "case_id": case_id,
        "factual_graph": factual,
        "legal_graph": legal,
        "unresolved_work": unresolved,
        "timeline": timeline,
        "private_messages": private,
        "graphs_are_distinct": True,
        "admin_bypass": False,
        "governing_legal_authority": False,
        "legal_sufficiency": False,
        "transport": {"http": True, "websocket": False, "sse": False},
        "limitations": list(_LIMITATIONS),
    }


def _private_messages(service: CaseMessageService | None, actor: str, membership) -> list[dict[str, Any]]:
    if not isinstance(service, CaseMessageService):
        return []
    body = {
        "case_id": membership.case_id,
        "tenant_id": membership.tenant_id,
        "resource_id": membership.resource_id,
        "membership_grant_id": membership.grant_id,
        "expected_membership_version": membership.version,
    }
    listed = service.list_threads(actor, body)
    messages: list[dict[str, Any]] = []
    for thread in listed.get("threads") or []:
        if thread.get("case_id") != membership.case_id:
            continue
        page = service.page(actor, str(thread["thread_id"]), {**body, "limit": 20})
        if page.get("case_id") != membership.case_id:
            continue
        for message in page.get("messages") or []:
            if message.get("case_id") == membership.case_id:
                messages.append(message)
    return messages


def _case_file(mediator: Any) -> Mapping[str, Any]:
    material = getattr(mediator, "intake_case_file", None)
    return material if isinstance(material, Mapping) else {}


def read_assigned_case(*, actor_principal_id: str, case_id: str, authorizer: CaseActionAuthorizer,
                       memberships: CaseMembershipStore, handlers: CaseHandlerRegistry | None,
                       messages: CaseMessageService | None, now: int) -> dict[str, Any]:
    membership = _membership_for(memberships, actor_principal_id, case_id)
    _require_live_membership(membership, now)
    decision = _authorize_content(authorizer, actor_principal_id, membership)
    if handlers is None or not isinstance(handlers, CaseHandlerRegistry):
        raise LawyerWorkspaceError("lawyer_workspace_unavailable")
    try:
        mediator, _workspace, _root = handlers.resolve(decision)
    except CaseAccessError as exc:
        raise LawyerWorkspaceError("lawyer_workspace_unavailable") from exc
    try:
        private = _private_messages(messages, actor_principal_id, membership)
    except Exception as exc:
        code = getattr(exc, "code", "")
        if code in {"grant_expired", "membership_removed", "membership_pending", "membership_declined"}:
            raise LawyerWorkspaceError(code) from exc
        raise LawyerWorkspaceError("lawyer_workspace_unavailable") from exc
    projected = project_case_review(_case_file(mediator), case_id=case_id, messages=private)
    projected.update({
        "actor_principal_id": actor_principal_id,
        "membership": decision.membership,
        "grant_id": membership.grant_id,
        "membership_version": membership.version,
        "tenant_id": membership.tenant_id,
        "resource_id": membership.resource_id,
        "actor_is_encrypted_owner": False,
        "canonical_owner_principal_id": decision.canonical_owner_principal_id,
        "permits_operational_admin": False,
    })
    return projected


def _cell(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _table(caption: str, headers: list[str], rows: list[list[Any]], *, element_id: str) -> str:
    head = "".join(f"<th>{_cell(item)}</th>" for item in headers)
    body = []
    for row in rows:
        body.append("<tr>" + "".join(f"<td>{_cell(item)}</td>" for item in row) + "</tr>")
    return (
        f'<section id="{element_id}"><h2>{_cell(caption)}</h2>'
        f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></section>"
    )


def render_assigned_lawyer_workspace(projection: Mapping[str, Any]) -> str:
    """Fill the shared lawyer template. Review JSON stays valid for the older script."""

    template = _TEMPLATE.read_text(encoding="utf-8")
    factual = projection.get("factual_graph") if isinstance(projection.get("factual_graph"), Mapping) else {}
    legal = projection.get("legal_graph") if isinstance(projection.get("legal_graph"), Mapping) else {}
    cases = projection.get("cases") if isinstance(projection.get("cases"), list) else []
    parts = [
        _table("Assigned cases", ["Case", "Membership", "State"], [
            [item.get("case_id"), item.get("membership"), item.get("state")] for item in cases if isinstance(item, dict)
        ] or ([[projection.get("case_id"), projection.get("membership"), "authorized"]] if projection.get("case_id") else []),
            element_id="assigned-cases"),
        _table("Factual graph", ["Distinction", "Text"], [
            [factual.get("distinction"), item.get("text")] for item in factual.get("items") or []
        ], element_id="factual-graph"),
        _table("Legal graph", ["Distinction", "Source", "Text"], [
            [legal.get("distinction"), item.get("source_id"), item.get("text")] for item in legal.get("items") or []
        ], element_id="legal-graph"),
        _table("Unresolved work", ["Status", "Text"], [
            [item.get("status"), item.get("text")] for item in projection.get("unresolved_work") or []
        ], element_id="unresolved-work"),
        _table("Timeline", ["When", "Text"], [
            [item.get("at"), item.get("text")] for item in projection.get("timeline") or []
        ], element_id="timeline"),
        _table("Private messages", ["Sender", "Disposition", "Text"], [
            [item.get("sender_principal_id"), item.get("disposition"), item.get("text")]
            for item in projection.get("private_messages") or []
        ], element_id="private-messages"),
    ]
    rendered = "\n".join(parts)
    payload = json.dumps(projection, sort_keys=True)
    review_payload = json.dumps(_EMPTY_REVIEW, sort_keys=True)
    page = template.replace("__ASSIGNED_REVIEW_HTML__", rendered)
    page = page.replace("__LAWYER_CASE_REVIEW_JSON__", html.escape(payload, quote=True))
    page = page.replace("__LAWYER_REVIEW_JSON__", html.escape(review_payload, quote=True))
    if "__LAWYER_CASE_REVIEW_JSON__" in page or "__ASSIGNED_REVIEW_HTML__" in page:
        raise LawyerWorkspaceError("lawyer_workspace_unavailable")
    return page


def mount_lawyer_workspace(app: Any) -> None:
    """Mount list and case reads on the case catalog boundary."""

    from fastapi.responses import HTMLResponse, JSONResponse

    def _actor(request: Request) -> str:
        principal = getattr(request.state, "browser_principal", None)
        actor = getattr(principal, "principal_id", None)
        if not isinstance(actor, str) or actor == "":
            raise LawyerWorkspaceError("unauthenticated")
        return actor

    def _owners(request: Request):
        authorizer = getattr(request.app.state, "case_authorizer", None)
        assignments = getattr(request.app.state, "case_assignments", None)
        memberships = getattr(assignments, "_memberships", None)
        if not isinstance(authorizer, CaseActionAuthorizer) or not isinstance(memberships, CaseMembershipStore):
            raise LawyerWorkspaceError("lawyer_workspace_unavailable")
        clock = getattr(assignments, "_clock", None)
        now = _clock_value(clock)
        handlers = getattr(request.app.state, "case_handlers", None)
        messages = getattr(request.app.state, "case_messages", None)
        if messages is not None and not isinstance(messages, CaseMessageService):
            raise LawyerWorkspaceError("lawyer_workspace_unavailable")
        return authorizer, memberships, handlers, messages, now

    def _fail(exc: LawyerWorkspaceError) -> JSONResponse:
        return JSONResponse(
            {
                "error": exc.code,
                "task_id": TASK_ID,
                "admin_bypass": False,
                "case_content": False,
                "permits_operational_admin": False,
            },
            status_code=lawyer_workspace_http_status(exc.code),
        )

    @app.get(LAWYER_WORKSPACE_PAGE)
    async def lawyer_workspace_page():
        page = render_assigned_lawyer_workspace({
            "task_id": TASK_ID,
            "cases": [],
            "factual_graph": {"graph_kind": "factual", "distinction": "User assertions and evidence. These rows are not legal rules.", "items": []},
            "legal_graph": {"graph_kind": "legal", "distinction": "Source passages and admitted-rule candidates. Factual answers do not rewrite these rules.", "items": []},
            "unresolved_work": [],
            "timeline": [],
            "private_messages": [],
            "admin_bypass": False,
            "membership": "",
            "transport": {"http": True, "websocket": False, "sse": False},
            "limitations": list(_LIMITATIONS),
        })
        return HTMLResponse(page, headers={"cache-control": "no-store"})

    @app.get(LAWYER_WORKSPACE_API)
    async def lawyer_workspace_list(request: Request):
        try:
            authorizer, memberships, _handlers, _messages, now = _owners(request)
            payload = list_assigned_cases(
                actor_principal_id=_actor(request), authorizer=authorizer, memberships=memberships, now=now,
            )
        except LawyerWorkspaceError as exc:
            return _fail(exc)
        except CaseMembershipError as exc:
            return _fail(LawyerWorkspaceError("lawyer_workspace_unavailable" if exc.code not in {
                "grant_expired", "membership_removed"} else exc.code))
        return JSONResponse(payload, headers={"cache-control": "no-store"})

    @app.get(LAWYER_WORKSPACE_API + "/{case_id}")
    async def lawyer_workspace_case(case_id: str, request: Request):
        try:
            authorizer, memberships, handlers, messages, now = _owners(request)
            payload = read_assigned_case(
                actor_principal_id=_actor(request),
                case_id=case_id,
                authorizer=authorizer,
                memberships=memberships,
                handlers=handlers,
                messages=messages,
                now=now,
            )
            if request.query_params.get("case_id") not in {None, "", case_id}:
                raise LawyerWorkspaceError("missing_case")
        except LawyerWorkspaceError as exc:
            return _fail(exc)
        return JSONResponse(payload, headers={"cache-control": "no-store"})

    @app.get(LAWYER_WORKSPACE_API + "/{case_id}/page")
    async def lawyer_workspace_case_page(case_id: str, request: Request):
        try:
            authorizer, memberships, handlers, messages, now = _owners(request)
            payload = read_assigned_case(
                actor_principal_id=_actor(request),
                case_id=case_id,
                authorizer=authorizer,
                memberships=memberships,
                handlers=handlers,
                messages=messages,
                now=now,
            )
            page = render_assigned_lawyer_workspace(payload)
        except LawyerWorkspaceError as exc:
            return _fail(exc)
        return HTMLResponse(page, headers={"cache-control": "no-store"})
