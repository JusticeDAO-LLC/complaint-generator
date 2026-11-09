"""Recipient-scoped in-app notifications for assignment, message, and review events.

Badges and operational logs name the event kind and identifiers only. They do
not copy complaint, evidence, or message text. Read, unread, and retry repeat
the same outcome. This campaign does not activate email, SMS, or external chat.
"""

from __future__ import annotations

import threading
import uuid
from typing import Any, Mapping

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from applications.browser_sessions import BrowserSessionError, BrowserSessionService, SESSION_COOKIE
from applications.case_membership import CaseMembershipStore

TASK_ID = "CIMP-GUI-48"
EVENT_KINDS = frozenset({"assignment", "message", "review"})
CHANNEL = "in_app"
BADGE_LABELS = {
    "assignment": "Assignment",
    "message": "Message",
    "review": "Review",
}
LIMITATIONS = (
    "recipient_scoped",
    "badges_omit_complaint_and_evidence_text",
    "operational_logs_omit_complaint_and_evidence_text",
    "read_unread_is_idempotent",
    "retry_is_idempotent",
    "no_external_email_sms_or_chat",
    "no_websocket_or_sse",
)
_REJECTED_BODY_FIELDS = frozenset({
    "text",
    "body",
    "evidence",
    "complaint",
    "narrative",
    "proposed_text",
    "message",
    "email",
    "sms",
    "phone",
    "chat",
    "subject",
    "plaintext",
    "case_plaintext",
    "credential",
    "credentials",
    "trusted_local",
    "trust",
    "role",
    "roles",
    "channel",
    "delivery",
})
_NO_STORE = {"Cache-Control": "no-store, max-age=0, private", "Pragma": "no-cache", "Expires": "0"}


class CaseNotificationError(Exception):
    """Fail-closed notification error. ``code`` is a stable machine reason."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def notification_http_status(code: str) -> int:
    if code in {"missing_notification", "missing_case", "missing_principal"}:
        return 404
    if code in {"replay_mismatch"}:
        return 409
    if code in {"unauthenticated", "request_body"}:
        return 401
    if code == "notification_unavailable":
        return 503
    return 403


def _label(value: Any, code: str) -> str:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise CaseNotificationError(code)
    if any(char in value for char in ("\x00", "\n", "\r", "/", "\\")):
        raise CaseNotificationError(code)
    if len(value) > 200:
        raise CaseNotificationError(code)
    return value


class CaseNotificationService:
    """In-app inbox. Each row is visible only to its recipient principal."""

    def __init__(self, *, memberships: CaseMembershipStore, clock=None) -> None:
        if not isinstance(memberships, CaseMembershipStore):
            raise CaseNotificationError("notification_unavailable")
        self._memberships = memberships
        self._clock = clock if clock is not None else (lambda: 0)
        self._lock = threading.Lock()
        self._rows: dict[str, dict[str, Any]] = {}
        self._idem: dict[tuple[str, str, str, str], str] = {}
        self._retries: dict[tuple[str, str], int] = {}
        self._log: list[dict[str, Any]] = []
        self._observed = False

    def observe(self, assignments: Any, messages: Any) -> None:
        """Record counterparty notices from assignment and message owners.

        Wrapping is idempotent. Review items stay explicit because their owner
        is the case-file mediator, which this inbox does not open.
        """

        if self._observed:
            return
        self._observed = True
        if assignments is not None:
            self._wrap(assignments, "invite", self._from_assignment)
            self._wrap(assignments, "accept", self._from_assignment)
            self._wrap(assignments, "decline", self._from_assignment)
            self._wrap(assignments, "remove", self._from_assignment)
        if messages is not None:
            self._wrap(messages, "send", self._from_message)

    def _wrap(self, owner: Any, name: str, projector) -> None:
        original = getattr(owner, name)

        def wrapped(*args, **kwargs):
            result = original(*args, **kwargs)
            try:
                projector(result)
            except CaseNotificationError:
                return result
            return result

        setattr(owner, name, wrapped)

    def _from_assignment(self, view: Mapping[str, Any]) -> None:
        if not isinstance(view, Mapping):
            return
        state = str(view.get("state") or "")
        owner = view.get("owner_principal_id")
        member = view.get("member_principal_id")
        if state == "pending":
            recipient, actor = member, owner
        elif state in {"accepted", "declined"}:
            recipient, actor = owner, member
        elif state == "removed":
            recipient, actor = member, owner
        else:
            return
        self._put(
            event_kind="assignment",
            actor_principal_id=str(actor or ""),
            recipient_principal_id=str(recipient or ""),
            case_id=str(view.get("case_id") or ""),
            source_id=str(view.get("grant_id") or ""),
            idempotency_key="assignment:" + str(view.get("grant_id") or "") + ":" + state,
            enforce_parties=False,
        )

    def _from_message(self, view: Mapping[str, Any]) -> None:
        if not isinstance(view, Mapping):
            return
        case_id = str(view.get("case_id") or "")
        sender = str(view.get("sender_principal_id") or "")
        message_id = str(view.get("message_id") or "")
        for recipient in self._counterparties(case_id, sender):
            self._put(
                event_kind="message",
                actor_principal_id=sender,
                recipient_principal_id=recipient,
                case_id=case_id,
                source_id=message_id,
                idempotency_key="message:" + message_id + ":" + recipient,
                enforce_parties=False,
            )

    def _counterparties(self, case_id: str, actor: str) -> list[str]:
        found = []
        for grant in self._memberships.recover():
            if grant.case_id != case_id or grant.status != "accepted":
                continue
            for principal in (grant.owner_principal_id, grant.member_principal_id):
                if principal != actor and principal not in found:
                    found.append(principal)
        return found

    def _parties(self, case_id: str) -> set[tuple[str, str]]:
        pairs = set()
        for grant in self._memberships.recover():
            if grant.case_id != case_id:
                continue
            pairs.add((grant.owner_principal_id, grant.member_principal_id))
        return pairs

    def record(self, actor_principal_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        payload = self._body(body)
        kind = _label(payload.get("event_kind"), "event_kind")
        if kind not in EVENT_KINDS:
            raise CaseNotificationError("event_kind")
        return self._put(
            event_kind=kind,
            actor_principal_id=_label(actor_principal_id, "unauthenticated"),
            recipient_principal_id=_label(payload.get("recipient_principal_id"), "recipient_principal_id"),
            case_id=_label(payload.get("case_id"), "case_id"),
            source_id=_label(payload.get("source_id"), "source_id"),
            idempotency_key=_label(payload.get("idempotency_key"), "idempotency_key"),
            enforce_parties=True,
        )

    def _put(self, *, event_kind: str, actor_principal_id: str, recipient_principal_id: str,
             case_id: str, source_id: str, idempotency_key: str, enforce_parties: bool) -> dict[str, Any]:
        actor = _label(actor_principal_id, "unauthenticated")
        recipient = _label(recipient_principal_id, "recipient_principal_id")
        case = _label(case_id, "case_id")
        source = _label(source_id, "source_id")
        key = _label(idempotency_key, "idempotency_key")
        if recipient == actor:
            raise CaseNotificationError("recipient_required")
        if enforce_parties:
            pair = (actor, recipient) if (actor, recipient) in self._parties(case) else (recipient, actor)
            if pair not in self._parties(case):
                raise CaseNotificationError("notification_denied")
        fingerprint = (event_kind, recipient, case, source)
        with self._lock:
            existing_id = self._idem.get((event_kind, recipient, source, key))
            if existing_id is not None:
                row = self._rows[existing_id]
                if (row["event_kind"], row["recipient_principal_id"], row["case_id"], row["source_id"]) != fingerprint:
                    raise CaseNotificationError("replay_mismatch")
                view = self._view(row)
                view["replayed"] = True
                return view
            now = self._clock()
            if type(now) is not int:
                now = 0
            row = {
                "notification_id": uuid.uuid4().hex,
                "event_kind": event_kind,
                "actor_principal_id": actor,
                "recipient_principal_id": recipient,
                "case_id": case,
                "source_id": source,
                "read": False,
                "attempt_count": 1,
                "created_at": now,
            }
            self._rows[row["notification_id"]] = row
            self._idem[(event_kind, recipient, source, key)] = row["notification_id"]
            self._append_log("notification_recorded", row)
            view = self._view(row)
            view["replayed"] = False
            return view

    def list_for(self, actor_principal_id: str) -> dict[str, Any]:
        actor = _label(actor_principal_id, "unauthenticated")
        with self._lock:
            rows = [self._view(row) for row in self._rows.values() if row["recipient_principal_id"] == actor]
        rows.sort(key=lambda item: item["notification_id"])
        return {
            "actor_principal_id": actor,
            "notifications": rows,
            "badge": self.badge(actor),
            "external_delivery": False,
            "channels": [CHANNEL],
            "limitations": list(LIMITATIONS),
        }

    def badge(self, actor_principal_id: str) -> dict[str, Any]:
        actor = _label(actor_principal_id, "unauthenticated")
        with self._lock:
            unread = sum(1 for row in self._rows.values()
                         if row["recipient_principal_id"] == actor and row["read"] is False)
        return {
            "unread_count": unread,
            "badge_label": str(unread),
            "channel": CHANNEL,
            "external_delivery": False,
            "channels": [CHANNEL],
        }

    def operational_log(self, actor_principal_id: str) -> dict[str, Any]:
        actor = _label(actor_principal_id, "unauthenticated")
        with self._lock:
            rows = [dict(item) for item in self._log
                    if actor in {item["recipient_principal_id"], item["actor_principal_id"]}]
        return {"entries": rows, "external_delivery": False, "channels": [CHANNEL]}

    def set_read(self, actor_principal_id: str, notification_id: str, *, read: bool) -> dict[str, Any]:
        actor = _label(actor_principal_id, "unauthenticated")
        key = _label(notification_id, "notification_id")
        with self._lock:
            row = self._rows.get(key)
            if row is None or row["recipient_principal_id"] != actor:
                raise CaseNotificationError("missing_notification")
            replayed = row["read"] is read
            row["read"] = read
            if not replayed:
                self._append_log("notification_read" if read else "notification_unread", row)
            view = self._view(row)
            view["replayed"] = replayed
            view["badge"] = {
                "unread_count": sum(1 for item in self._rows.values()
                                    if item["recipient_principal_id"] == actor and item["read"] is False),
                "badge_label": None,
                "channel": CHANNEL,
                "external_delivery": False,
            }
            view["badge"]["badge_label"] = str(view["badge"]["unread_count"])
            return view

    def retry(self, actor_principal_id: str, notification_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        payload = self._body(body)
        actor = _label(actor_principal_id, "unauthenticated")
        key = _label(notification_id, "notification_id")
        retry_key = _label(payload.get("idempotency_key"), "idempotency_key")
        with self._lock:
            row = self._rows.get(key)
            if row is None or row["recipient_principal_id"] != actor:
                raise CaseNotificationError("missing_notification")
            slot = (key, retry_key)
            if slot in self._retries:
                view = self._view(row)
                view["replayed"] = True
                view["external_delivery"] = False
                view["channels"] = [CHANNEL]
                return view
            row["attempt_count"] = int(row["attempt_count"]) + 1
            self._retries[slot] = row["attempt_count"]
            self._append_log("notification_retry", row)
            view = self._view(row)
            view["replayed"] = False
            view["external_delivery"] = False
            view["channels"] = [CHANNEL]
            return view

    def _append_log(self, action: str, row: Mapping[str, Any]) -> None:
        self._log.append({
            "action": action,
            "notification_id": row["notification_id"],
            "event_kind": row["event_kind"],
            "recipient_principal_id": row["recipient_principal_id"],
            "actor_principal_id": row["actor_principal_id"],
            "case_id": row["case_id"],
            "source_id": row["source_id"],
            "channel": CHANNEL,
            "external_delivery": False,
        })

    def _view(self, row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "notification_id": row["notification_id"],
            "event_kind": row["event_kind"],
            "badge_label": BADGE_LABELS[row["event_kind"]],
            "actor_principal_id": row["actor_principal_id"],
            "recipient_principal_id": row["recipient_principal_id"],
            "case_id": row["case_id"],
            "source_id": row["source_id"],
            "read": row["read"],
            "attempt_count": row["attempt_count"],
            "channel": CHANNEL,
            "external_delivery": False,
            "task_id": TASK_ID,
        }

    def _body(self, body: Mapping[str, Any] | None) -> Mapping[str, Any]:
        if not isinstance(body, Mapping):
            raise CaseNotificationError("request_body")
        if any(name in body for name in _REJECTED_BODY_FIELDS):
            raise CaseNotificationError("complaint_text_rejected")
        return body


def mount_case_notifications(app: Any) -> None:
    """Mount inbox routes on the case catalog boundary. No external delivery."""

    from fastapi.responses import JSONResponse

    def _service(request: Any) -> CaseNotificationService:
        service = getattr(request.app.state, "case_notifications", None)
        if not isinstance(service, CaseNotificationService):
            raise CaseNotificationError("notification_unavailable")
        return service

    def _actor(request: Any) -> str:
        principal = getattr(request.state, "browser_principal", None)
        actor = getattr(principal, "principal_id", None)
        if not isinstance(actor, str) or actor == "":
            raise CaseNotificationError("unauthenticated")
        return actor

    def _fail(exc: CaseNotificationError) -> JSONResponse:
        return JSONResponse({"error": exc.code, "external_delivery": False}, status_code=notification_http_status(exc.code), headers=_NO_STORE)

    async def _call(request, method: str, *args, status: int = 200, **kwargs):
        try:
            service = _service(request)
            sessions = getattr(request.app.state, "browser_sessions", None)
            bound = getattr(request.state, "browser_principal", None)
            token = request.cookies.get(SESSION_COOKIE)
            if not isinstance(sessions, BrowserSessionService) or bound is None:
                raise CaseNotificationError("unauthenticated")

            def verify():
                try:
                    current = sessions.authenticate_token(token)
                except BrowserSessionError:
                    raise CaseNotificationError("unauthenticated") from None
                if (current.principal_id, current.tenant_id, current.generation) != (
                        bound.principal_id, bound.tenant_id, bound.generation):
                    raise CaseNotificationError("unauthenticated")

            verify()
            result = await run_in_threadpool(getattr(service, method), _actor(request), *args, **kwargs)
            verify()
            return JSONResponse(result, status_code=status, headers=_NO_STORE)
        except CaseNotificationError as exc:
            return _fail(exc)

    @app.get("/api/cases/notifications")
    async def notification_list(request: Request):
        return await _call(request, "list_for")

    @app.get("/api/cases/notifications/badge")
    async def notification_badge(request: Request):
        return await _call(request, "badge")

    @app.get("/api/cases/notifications/log")
    async def notification_log(request: Request):
        return await _call(request, "operational_log")

    @app.post("/api/cases/notifications")
    async def notification_record(request: Request):
        material = getattr(request.state, "case_catalog_material", None)
        body = material if isinstance(material, dict) else {}
        return await _call(request, "record", body, status=201)

    @app.post("/api/cases/notifications/{notification_id}/read")
    async def notification_read(notification_id: str, request: Request):
        return await _call(request, "set_read", notification_id, read=True)

    @app.post("/api/cases/notifications/{notification_id}/unread")
    async def notification_unread(notification_id: str, request: Request):
        return await _call(request, "set_read", notification_id, read=False)

    @app.post("/api/cases/notifications/{notification_id}/retry")
    async def notification_retry(notification_id: str, request: Request):
        material = getattr(request.state, "case_catalog_material", None)
        body = material if isinstance(material, dict) else {}
        return await _call(request, "retry", notification_id, body)
