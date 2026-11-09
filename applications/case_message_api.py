"""HTTP owner for authorized encrypted case conversations.

Routes sit on the case catalog boundary. The session actor is taken from the
verified browser principal. Request bodies cannot mint a role, a grant, or a
disposition. Message text remains conversation until ``adopt``.

This module does not deliver external messages and does not claim WebSocket
or SSE. Adoption does not call a model or write an evidence artifact.
"""

from __future__ import annotations

from typing import Any, Mapping

from starlette.requests import Request
from starlette.concurrency import run_in_threadpool
from applications.browser_sessions import BrowserSessionError, BrowserSessionService, SESSION_COOKIE

from applications.case_messages import (
    CaseMessageError,
    CaseMessageStore,
    message_http_status,
)

TASK_ID = "CIMP-GUI-42"
_NO_STORE = {"Cache-Control": "no-store, max-age=0, private", "Pragma": "no-cache", "Expires": "0"}
_WORKFLOW_KINDS = frozenset({"evidence", "draft", "inquiry"})
_MINT_FIELDS = frozenset({
    "attribution",
    "record_type",
    "adopts_evidence",
    "adopts_answer",
    "adopts_intake_answer",
    "disposition",
    "sender_principal_id",
    "actor_is_encrypted_owner",
    "canonical_owner_principal_id",
    "eligible",
    "adopted",
    "accepted_fact",
    "human_attribution",
})


def _workflow_label(value: Any, code: str) -> str:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise CaseMessageError(code)
    if any(char in value for char in ("\x00", "\n", "\r", "/", "\\")):
        raise CaseMessageError(code)
    if len(value) > 200:
        raise CaseMessageError(code)
    return value


def _workflow_revision(value: Any) -> int | str:
    if type(value) is int and not isinstance(value, bool) and value >= 0:
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise CaseMessageError("workflow_context_required")


def workflow_context_from_body(body: Mapping[str, Any]) -> dict[str, Any]:
    """Exact evidence, draft, or inquiry identity. The caller cannot mint eligibility."""

    if any(name in body for name in _MINT_FIELDS):
        raise CaseMessageError("request_cannot_mint_authority")
    if body.get("by_display") is True or body.get("displayed") is True:
        raise CaseMessageError("display_is_not_adoption")
    kind = body.get("context_kind")
    if kind not in _WORKFLOW_KINDS:
        raise CaseMessageError("workflow_context_required")
    context_id = _workflow_label(body.get("context_id"), "workflow_context_required")
    if kind == "draft":
        revision = body.get("context_revision")
        if isinstance(revision, str) and revision.strip() != "" and revision == revision.strip() and "\x00" not in revision and len(revision) <= 200:
            context_revision: int | str = revision
        else:
            context_revision = _workflow_revision(revision)
        section_id = _workflow_label(body.get("section_id"), "workflow_context_required")
        span = None
    elif kind == "evidence":
        context_revision = _workflow_revision(body.get("context_revision"))
        section_id = None
        span = _workflow_label(body.get("span"), "workflow_context_required")
    else:
        context_revision = _workflow_revision(body.get("context_revision"))
        section_id = None
        span = None
    return {
        "context_kind": kind,
        "context_id": context_id,
        "context_revision": context_revision,
        "section_id": section_id,
        "span": span,
        "eligible": True,
        "eligibility": "exact_workflow_context",
    }


def _same_context(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return all(left.get(name) == right.get(name) for name in (
        "context_kind", "context_id", "context_revision", "section_id", "span",
    ))


class CaseMessageService:
    """Route-facing facade over the encrypted thread store."""

    def __init__(self, store: CaseMessageStore) -> None:
        if not isinstance(store, CaseMessageStore):
            raise CaseMessageError("authority_owners")
        self._store = store
        self._attachments: Any = None
        self._workflow_links: dict[str, dict[str, Any]] = {}
        self._workflow_adoptions: dict[str, dict[str, Any]] = {}
        self._workflow_idem: dict[tuple[str, str, str], dict[str, Any]] = {}

    def bind_attachments(self, attachments: Any) -> None:
        """Share files through the attachment owner. This service does not seal bytes itself."""

        from applications.case_attachment_api import CaseAttachmentService

        if not isinstance(attachments, CaseAttachmentService):
            raise CaseMessageError("authority_owners")
        self._attachments = attachments

    def share_attachment(self, actor_principal_id: str, thread_id: str, body: Mapping[str, Any], *, verify_access=None) -> dict[str, Any]:
        return self._attachment_call("store_attachment", actor_principal_id, thread_id, body, verify_access=verify_access)

    def list_attachments(self, actor_principal_id: str, thread_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._attachment_call("list_attachments", actor_principal_id, thread_id, body)

    def read_attachment(self, actor_principal_id: str, thread_id: str, attachment_id: str, body: Mapping[str, Any], *, verify_access=None) -> dict[str, Any]:
        return self._attachment_call("download_attachment", actor_principal_id, thread_id, body, attachment_id=attachment_id, verify_access=verify_access)

    def preview_attachment(self, actor_principal_id: str, thread_id: str, attachment_id: str, body: Mapping[str, Any], *, verify_access=None) -> dict[str, Any]:
        return self._attachment_call("preview_attachment", actor_principal_id, thread_id, body, attachment_id=attachment_id, verify_access=verify_access)

    def attachment_notices(self, actor_principal_id: str, thread_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._attachment_call("list_notices", actor_principal_id, thread_id, body)

    def _attachment_call(self, method: str, actor_principal_id: str, thread_id: str, body: Mapping[str, Any], *, attachment_id: str | None = None, verify_access=None) -> dict[str, Any]:
        from applications.case_attachment_api import CaseAttachmentService, SharedAttachmentError

        service = self._attachments
        if not isinstance(service, CaseAttachmentService):
            raise CaseMessageError("attachment_unavailable")
        if not isinstance(body, Mapping):
            raise CaseMessageError("request_body")
        material = dict(body)
        supplied = material.get("thread_id", thread_id)
        if supplied != thread_id:
            raise CaseMessageError("thread_mismatch")
        material["thread_id"] = thread_id
        try:
            target = getattr(service, method)
            if attachment_id is None:
                if verify_access is None or method == "list_attachments" or method == "list_notices":
                    if method in {"list_attachments", "list_notices"}:
                        return target(actor_principal_id, material)
                    return target(actor_principal_id, material, verify_access=verify_access)
                return target(actor_principal_id, material, verify_access=verify_access)
            return target(actor_principal_id, attachment_id, material, verify_access=verify_access)
        except SharedAttachmentError as exc:
            raise CaseMessageError(exc.code) from exc

    @property
    def store(self) -> CaseMessageStore:
        return self._store

    def _current_call(self, method, actor, *args, verify_access=None):
        if verify_access is None:
            return getattr(self._store, method)(actor, *args)
        body = args[-1]
        key = (self._store._key_id, self._store._key)
        def verify():
            verify_access()
            self._store._active(actor)
            if (self._store._key_id, self._store._key) != key:
                raise CaseMessageError("message_unavailable")
            payload = self._store._body(body)
            if method in {"page", "list_threads"}:
                admission = self._store._admit_read(actor, str(payload.get("case_id") or ""), payload)
            else:
                admission = self._store._admit(actor, str(payload.get("case_id") or ""),
                    "case.review" if method == "adopt" else "case.message.send", payload)
            if method not in {"create_thread", "list_threads"}:
                self._store._require_thread(args[0], admission["case_id"])
        with self._store.publication_scope(verify):
            return getattr(self._store, method)(actor, *args)

    def create_thread(self, actor_principal_id: str, body: Mapping[str, Any], *, verify_access=None) -> dict[str, Any]:
        return self._current_call("create_thread", actor_principal_id, body, verify_access=verify_access)

    def list_threads(self, actor_principal_id: str, body: Mapping[str, Any], *, verify_access=None) -> dict[str, Any]:
        return self._current_call("list_threads", actor_principal_id, body, verify_access=verify_access)

    def send(self, actor_principal_id: str, thread_id: str, body: Mapping[str, Any], *, verify_access=None) -> dict[str, Any]:
        return self._current_call("send", actor_principal_id, thread_id, body, verify_access=verify_access)

    def revise(self, actor_principal_id: str, thread_id: str, message_id: str, body: Mapping[str, Any], *, verify_access=None) -> dict[str, Any]:
        return self._current_call("revise", actor_principal_id, thread_id, message_id, body, verify_access=verify_access)

    def page(self, actor_principal_id: str, thread_id: str, body: Mapping[str, Any], *, verify_access=None) -> dict[str, Any]:
        return self._current_call("page", actor_principal_id, thread_id, body, verify_access=verify_access)

    def adopt(self, actor_principal_id: str, thread_id: str, message_id: str, body: Mapping[str, Any], *, verify_access=None) -> dict[str, Any]:
        return self._current_call("adopt", actor_principal_id, thread_id, message_id, body, verify_access=verify_access)

    def workflow_link(self, message_id: str) -> dict[str, Any] | None:
        row = self._workflow_links.get(message_id)
        return None if row is None else dict(row)

    def workflow_adoption(self, message_id: str) -> dict[str, Any] | None:
        row = self._workflow_adoptions.get(message_id)
        return None if row is None else dict(row)

    def link_workflow_context(self, actor_principal_id: str, thread_id: str, message_id: str, body: Mapping[str, Any], *, verify_access=None) -> dict[str, Any]:
        """Attach an exact workflow target. Linking does not adopt or relabel the message."""

        admission, payload = self._authorized(actor_principal_id, body, "case.message.send", verify_access)
        context = workflow_context_from_body(payload)
        key = _workflow_label(payload.get("idempotency_key"), "idempotency_key")
        message = self._message_on_thread(actor_principal_id, thread_id, message_id, payload, verify_access)
        if message.get("disposition") != "conversation":
            raise CaseMessageError("disposition_locked")
        fingerprint = {
            "context": context,
            "message_id": message["message_id"],
            "thread_id": message["thread_id"],
            "version": message["current_version"],
        }
        existing = self._workflow_idem.get(("link", actor_principal_id, key))
        if existing is not None:
            if existing.get("fingerprint") != fingerprint:
                raise CaseMessageError("replay_mismatch")
            return self._link_view(self._workflow_links[message["message_id"]], admission)
        prior = self._workflow_links.get(message["message_id"])
        if prior is not None and message["message_id"] in self._workflow_adoptions:
            raise CaseMessageError("disposition_locked")
        stored = {
            "message_id": message["message_id"],
            "thread_id": message["thread_id"],
            "case_id": admission["case_id"],
            "canonical_owner_principal_id": admission["tenant_id"],
            "linked_by": actor_principal_id,
            "message_version": message["current_version"],
            "context": context,
            "adopted": False,
            "attribution": "human",
            "record_type": "human_message",
            "disposition": "conversation",
        }
        self._workflow_links[message["message_id"]] = stored
        self._workflow_idem[("link", actor_principal_id, key)] = {"fingerprint": fingerprint, "message_id": message["message_id"]}
        return self._link_view(stored, admission)

    def adopt_workflow_material(self, actor_principal_id: str, thread_id: str, message_id: str, body: Mapping[str, Any], *, verify_access=None) -> dict[str, Any]:
        """Adopt the linked context. Display, AI text, and human chat do not qualify by themselves."""

        admission, payload = self._authorized(actor_principal_id, body, "case.review", verify_access)
        if payload.get("record_type") == "ai_mediator_turn" or payload.get("attribution") in {"human", "ai"}:
            raise CaseMessageError("request_cannot_mint_authority")
        context = workflow_context_from_body(payload)
        key = _workflow_label(payload.get("idempotency_key"), "idempotency_key")
        expected = payload.get("expected_message_version")
        if type(expected) is not int:
            if isinstance(expected, str) and expected.isdigit():
                expected = int(expected)
            else:
                raise CaseMessageError("revision_conflict")
        message = self._message_on_thread(actor_principal_id, thread_id, message_id, payload, verify_access)
        if message.get("disposition") != "conversation":
            raise CaseMessageError("disposition_locked")
        if int(message["current_version"]) != expected:
            raise CaseMessageError("revision_conflict")
        link = self._workflow_links.get(message["message_id"])
        if link is None or link.get("case_id") != admission["case_id"] or link.get("thread_id") != message["thread_id"]:
            raise CaseMessageError("workflow_context_required")
        fingerprint = {
            "context": context,
            "message_id": message["message_id"],
            "thread_id": message["thread_id"],
            "version": expected,
        }
        existing = self._workflow_idem.get(("adopt", actor_principal_id, key))
        if existing is not None:
            if existing.get("fingerprint") != fingerprint:
                raise CaseMessageError("replay_mismatch")
            return self._adoption_view(self._workflow_adoptions[message["message_id"]], admission, message)
        if not _same_context(link["context"], context):
            raise CaseMessageError("workflow_context_mismatch")
        if link["context"].get("eligible") is not True:
            raise CaseMessageError("material_not_eligible")
        prior = self._workflow_adoptions.get(message["message_id"])
        if prior is not None:
            if not _same_context(prior["context"], context) or prior.get("message_version") != expected:
                raise CaseMessageError("replay_mismatch")
            return self._adoption_view(prior, admission, message)
        adopted = {
            "message_id": message["message_id"],
            "thread_id": message["thread_id"],
            "case_id": admission["case_id"],
            "canonical_owner_principal_id": admission["tenant_id"],
            "actor_principal_id": actor_principal_id,
            "message_version": expected,
            "context": dict(link["context"]),
            "explicit": True,
            "authorized_action": "case.review",
            "disposition": "conversation",
            "attribution": "human",
            "record_type": "human_message",
            "accepted_by_display": False,
            "wrote_evidence_artifact": False,
            "wrote_intake_answer": False,
            "ai_text_became_human": False,
            "ai_text_became_fact": False,
            "idempotency_key": key,
        }
        self._workflow_adoptions[message["message_id"]] = adopted
        link["adopted"] = True
        self._workflow_idem[("adopt", actor_principal_id, key)] = {"fingerprint": fingerprint, "message_id": message["message_id"]}
        fresh = self._message_on_thread(actor_principal_id, thread_id, message_id, payload, verify_access)
        if fresh.get("disposition") != "conversation":
            raise CaseMessageError("disposition_locked")
        return self._adoption_view(adopted, admission, fresh)

    def _authorized(self, actor: str, body: Mapping[str, Any], action: str, verify_access) -> tuple[dict[str, Any], dict[str, Any]]:
        if not isinstance(body, Mapping):
            raise CaseMessageError("request_body")

        def admit() -> tuple[dict[str, Any], dict[str, Any]]:
            if verify_access is not None:
                verify_access()
            self._store._active(actor)
            payload = dict(self._store._body(body))
            case_id = str(payload.get("case_id") or "")
            admission = self._store._admit(actor, case_id, action, payload)
            return admission, payload

        if verify_access is None:
            return admit()
        with self._store.publication_scope(verify_access):
            return admit()

    def _message_on_thread(self, actor: str, thread_id: str, message_id: str, payload: Mapping[str, Any], verify_access) -> dict[str, Any]:
        material = dict(payload)
        material["limit"] = 20
        cursor = 0
        for _page in range(50):
            material["cursor"] = cursor
            page = self.page(actor, thread_id, material, verify_access=verify_access)
            for item in page.get("messages") or []:
                if isinstance(item, Mapping) and item.get("message_id") == message_id:
                    if item.get("case_id") != page.get("case_id") or item.get("thread_id") != thread_id:
                        raise CaseMessageError("thread_mismatch")
                    return dict(item)
            nxt = page.get("next_cursor")
            if nxt is None:
                break
            if type(nxt) is not int or nxt <= cursor:
                raise CaseMessageError("order_mismatch")
            cursor = nxt
        raise CaseMessageError("missing_message")

    def _link_view(self, stored: Mapping[str, Any], admission: Mapping[str, Any]) -> dict[str, Any]:
        context = dict(stored["context"])
        return {
            "operation": "link_workflow_context",
            "linked": True,
            "adopted": False,
            "explicit_adoption": False,
            "message_id": stored["message_id"],
            "thread_id": stored["thread_id"],
            "case_id": stored["case_id"],
            "actor_principal_id": admission["actor_principal_id"],
            "canonical_owner_principal_id": stored["canonical_owner_principal_id"],
            "disposition": "conversation",
            "attribution": "human",
            "record_type": "human_message",
            "message_version": stored["message_version"],
            "context": context,
            "navigation": _navigation(stored["case_id"], context),
            "accepted_by_display": False,
            "wrote_evidence_artifact": False,
            "wrote_intake_answer": False,
        }

    def _adoption_view(self, stored: Mapping[str, Any], admission: Mapping[str, Any], message: Mapping[str, Any]) -> dict[str, Any]:
        context = dict(stored["context"])
        return {
            "operation": "adopt_workflow_material",
            "adopted": True,
            "explicit": True,
            "authorized_action": "case.review",
            "message_id": stored["message_id"],
            "thread_id": stored["thread_id"],
            "case_id": stored["case_id"],
            "actor_principal_id": admission["actor_principal_id"],
            "canonical_owner_principal_id": stored["canonical_owner_principal_id"],
            "disposition": message.get("disposition"),
            "attribution": "human",
            "record_type": "human_message",
            "message_version": stored["message_version"],
            "context": context,
            "navigation": _navigation(stored["case_id"], context),
            "accepted_by_display": False,
            "wrote_evidence_artifact": False,
            "wrote_intake_answer": False,
            "ai_text_became_human": False,
            "ai_text_became_fact": False,
            "sender_principal_id": message.get("sender_principal_id"),
        }


def _navigation(case_id: str, context: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "surface": context["context_kind"],
        "case_id": case_id,
        "context_kind": context["context_kind"],
        "context_id": context["context_id"],
        "context_revision": context["context_revision"],
        "section_id": context.get("section_id"),
        "span": context.get("span"),
    }


def mount_case_messages(app: Any) -> None:
    """Mount conversation routes. Catalog authentication runs before these handlers."""

    from fastapi.responses import JSONResponse

    def _service(request: Any) -> CaseMessageService:
        service = getattr(request.app.state, "case_messages", None)
        if not isinstance(service, CaseMessageService):
            raise CaseMessageError("message_unavailable")
        return service

    def _actor(request: Any) -> str:
        principal = getattr(request.state, "browser_principal", None)
        actor = getattr(principal, "principal_id", None)
        if not isinstance(actor, str) or actor == "":
            raise CaseMessageError("unauthenticated")
        return actor

    def _material(request: Any) -> Mapping[str, Any]:
        material = getattr(request.state, "case_catalog_material", None)
        return material if isinstance(material, dict) else {}

    def _fail(exc: CaseMessageError) -> JSONResponse:
        return JSONResponse({"error": exc.code}, status_code=message_http_status(exc.code), headers=_NO_STORE)

    async def _dispatch(request, method, *identities, status=200):
        try:
            service = _service(request)
            sessions = getattr(request.app.state, "browser_sessions", None)
            bound = getattr(request.state, "browser_principal", None)
            token = request.cookies.get(SESSION_COOKIE)
            if not isinstance(sessions, BrowserSessionService) or bound is None:
                raise CaseMessageError("unauthenticated")
            def verify():
                try:
                    current = sessions.authenticate_token(token)
                except BrowserSessionError:
                    raise CaseMessageError("unauthenticated") from None
                if (current.principal_id, current.tenant_id, current.generation) != (
                        bound.principal_id, bound.tenant_id, bound.generation):
                    raise CaseMessageError("unauthenticated")
                if (_service(request) is not service
                        or getattr(request.app.state, "browser_sessions", None) is not sessions):
                    raise CaseMessageError("message_unavailable")
            verify()
            result = await run_in_threadpool(getattr(service, method), _actor(request),
                *identities, _material(request), verify_access=verify)
            verify()
            return JSONResponse(result, status_code=status, headers=_NO_STORE)
        except CaseMessageError as exc:
            return _fail(exc)

    @app.post("/api/cases/messages/threads")
    async def message_thread_create(request: Request):
        return await _dispatch(request, "create_thread", status=201)

    @app.get("/api/cases/messages/threads")
    async def message_thread_list(request: Request):
        return await _dispatch(request, "list_threads")

    @app.post("/api/cases/messages/threads/{thread_id}/messages")
    async def message_send(thread_id: str, request: Request):
        return await _dispatch(request, "send", thread_id, status=201)

    @app.post("/api/cases/messages/threads/{thread_id}/messages/{message_id}/revise")
    async def message_revise(thread_id: str, message_id: str, request: Request):
        return await _dispatch(request, "revise", thread_id, message_id)

    @app.get("/api/cases/messages/threads/{thread_id}/messages")
    async def message_page(thread_id: str, request: Request):
        return await _dispatch(request, "page", thread_id)

    @app.post("/api/cases/messages/threads/{thread_id}/messages/{message_id}/adopt")
    async def message_adopt(thread_id: str, message_id: str, request: Request):
        return await _dispatch(request, "adopt", thread_id, message_id)

    @app.post("/api/cases/messages/threads/{thread_id}/messages/{message_id}/workflow-context")
    async def message_workflow_context(thread_id: str, message_id: str, request: Request):
        return await _dispatch(request, "link_workflow_context", thread_id, message_id, status=201)

    @app.post("/api/cases/messages/threads/{thread_id}/messages/{message_id}/workflow-adoption")
    async def message_workflow_adoption(thread_id: str, message_id: str, request: Request):
        return await _dispatch(request, "adopt_workflow_material", thread_id, message_id)
