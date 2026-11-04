"""Read-only chronological projection of case correspondence and activity.

The projection combines authorized AI-mediator turns, human messages, review
decisions, and case actions. It does not seal a new record, grant access, or
adopt conversation text as evidence or an intake answer. Each entry keeps the
source record type and the canonical encrypted owner.
"""

from __future__ import annotations

from typing import Any, Mapping

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from applications.browser_sessions import SESSION_COOKIE, BrowserSessionError, BrowserSessionService
from applications.case_messages import CaseMessageError, message_http_status

TASK_ID = "CIMP-UX-35"
RECORD_TYPES = ("ai_mediator_turn", "human_message", "review_decision", "case_action")
_RECORD_RANK = {name: index for index, name in enumerate(RECORD_TYPES)}
_NO_STORE = {"Cache-Control": "no-store, max-age=0, private", "Pragma": "no-cache", "Expires": "0"}
_PAGE_LIMIT = 20
_MAX_PAGES = 50
LIMITATIONS = (
    "projection_is_not_authority",
    "projection_does_not_adopt_evidence_or_answers",
    "original_record_types_preserved",
    "original_encrypted_owner_preserved",
    "actor_remains_distinct_from_canonical_encrypted_owner",
    "missing_source_is_unavailable",
    "display_does_not_adopt_or_relabel",
)
_WORKFLOW_TARGETS = {
    "evidence": "evidence",
    "evidence_artifact": "evidence",
    "artifact": "evidence",
    "draft": "draft",
    "draft_section": "draft",
    "complaint_section": "draft",
    "inquiry": "inquiry",
    "intake_question": "inquiry",
    "intake_inquiry": "inquiry",
    "question": "inquiry",
}
_ATTRIBUTION = {
    "human_message": "human",
    "ai_mediator_turn": "ai",
    "review_decision": "review",
    "case_action": "action",
}
_MINT_FIELDS = frozenset({
    "canonical_owner_principal_id",
    "actor_is_encrypted_owner",
    "record_type",
    "entries",
    "adopts_evidence",
    "adopts_answer",
    "adopts_intake_answer",
    "disposition",
    "authority",
    "projection_is_authority",
    "invocation_id",
    "trusted_local",
    "trust",
    "role",
    "roles",
    "staff_role",
    "is_admin",
    "is_staff",
    "is_lawyer",
    "evidence",
    "narrative",
    "credentials",
    "credential",
})


class CaseCorrespondenceError(Exception):
    """Fail-closed projection error. ``code`` is a stable machine reason."""

    def __init__(self, code: str) -> None:
        self.code = str(code)
        super().__init__(self.code)


def correspondence_http_status(code: str) -> int:
    if code in {"unauthenticated", "request_body"}:
        return 401
    if code in {"revision_conflict", "replay_mismatch", "membership_revision_conflict"}:
        return 409
    if code in {"correspondence_unavailable", "message_unavailable"}:
        return 503
    if code in {"missing_case", "missing_thread", "missing_grant", "missing_principal"}:
        return 404
    return 403


def _label(value: Any, code: str) -> str:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise CaseCorrespondenceError(code)
    if any(char in value for char in ("\x00", "\n", "\r")):
        raise CaseCorrespondenceError(code)
    return value


def _revision(value: Any) -> int | str:
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and value.strip() != "" and value == value.strip():
        return value
    raise CaseCorrespondenceError("activity_record")


def _occurred_at(value: Any) -> int:
    if type(value) is not int:
        raise CaseCorrespondenceError("activity_record")
    return value


def _entry(
    *,
    record_type: str,
    source_id: str,
    occurred_at: int | None,
    sequence: int | None,
    actor_principal_id: str,
    canonical_owner_principal_id: str,
    invocation_id: str | None,
    target_kind: str,
    target_id: str,
    revision: int | str,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if record_type not in _RECORD_RANK:
        raise CaseCorrespondenceError("activity_record")
    row = {
        "record_type": record_type,
        "source_id": source_id,
        "occurred_at": occurred_at,
        "sequence": sequence,
        "actor_principal_id": actor_principal_id,
        "canonical_owner_principal_id": canonical_owner_principal_id,
        "actor_is_encrypted_owner": actor_principal_id == canonical_owner_principal_id,
        "invocation_id": invocation_id,
        "target": {"kind": target_kind, "id": target_id},
        "revision": revision,
        "adopts_evidence": False,
        "adopts_answer": False,
        "projection_is_authority": False,
    }
    if extra:
        row.update(dict(extra))
    return row


def _workflow_view(case_id: str, context: Mapping[str, Any], *, attribution: str, eligible: bool, adopted: bool, reason: str) -> dict[str, Any]:
    navigation = {
        "surface": context.get("context_kind"),
        "case_id": case_id,
        "context_kind": context.get("context_kind"),
        "context_id": context.get("context_id"),
        "context_revision": context.get("context_revision"),
        "section_id": context.get("section_id"),
        "span": context.get("span"),
    }
    return {
        "exact": True,
        "eligible": eligible,
        "adopted": adopted,
        "explicit": False,
        "context_kind": context.get("context_kind"),
        "context_id": context.get("context_id"),
        "context_revision": context.get("context_revision"),
        "section_id": context.get("section_id"),
        "span": context.get("span"),
        "navigation": navigation,
        "attribution": attribution,
        "reason": reason,
        "accepted_by_display": False,
        "display_changes_attribution": False,
        "wrote_evidence_artifact": False,
        "wrote_intake_answer": False,
    }


def _sort_key(entry: Mapping[str, Any]) -> tuple:
    occurred = entry.get("occurred_at")
    timed = type(occurred) is int
    sequence = entry.get("sequence")
    sequence_value = sequence if type(sequence) is int else 0
    # Timed records order by clock, then record type, then source sequence.
    # Untimed case actions order by their own sequence.
    return (
        0 if timed else 1,
        occurred if timed else sequence_value,
        _RECORD_RANK[str(entry["record_type"])],
        sequence_value if timed else 0,
        str(entry["source_id"]),
    )


def _activity_row(record: Mapping[str, Any], *, expected_type: str, case_id: str, owner: str) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise CaseCorrespondenceError("activity_record")
    if record.get("record_type") != expected_type:
        raise CaseCorrespondenceError("activity_record")
    if record.get("case_id") != case_id or record.get("canonical_owner_principal_id") != owner:
        raise CaseCorrespondenceError("owner_mismatch")
    if record.get("adopts_evidence") is True or record.get("adopts_answer") is True:
        raise CaseCorrespondenceError("projection_cannot_adopt")
    source_id = _label(record.get("source_id"), "activity_record")
    actor = _label(record.get("actor_principal_id"), "activity_record")
    invocation = record.get("invocation_id")
    if expected_type == "case_action":
        if invocation is not None:
            raise CaseCorrespondenceError("activity_record")
        invocation_id = None
    else:
        invocation_id = _label(invocation, "activity_record")
    target_kind = _label(record.get("target_kind"), "activity_record")
    target_id = _label(record.get("target_id"), "activity_record")
    occurred = record.get("occurred_at")
    sequence = record.get("sequence")
    if sequence is not None and type(sequence) is not int:
        raise CaseCorrespondenceError("activity_record")
    extra = {}
    if isinstance(record.get("text"), str):
        extra["text"] = record["text"]
    return _entry(
        record_type=expected_type,
        source_id=source_id,
        occurred_at=None if occurred is None else _occurred_at(occurred),
        sequence=sequence,
        actor_principal_id=actor,
        canonical_owner_principal_id=owner,
        invocation_id=invocation_id,
        target_kind=target_kind,
        target_id=target_id,
        revision=_revision(record.get("revision")),
        extra=extra,
    )


class CaseCorrespondenceService:
    """Project authorized records. This object stores nothing."""

    def __init__(self, messages: Any, *, audit: Any = None, activity: Any = None) -> None:
        from applications.case_message_api import CaseMessageService

        if not isinstance(messages, CaseMessageService):
            raise CaseCorrespondenceError("correspondence_unavailable")
        self._messages = messages
        self._audit = audit
        self._activity = activity

    def project(self, actor_principal_id: str, body: Mapping[str, Any], *, verify_access=None) -> dict[str, Any]:
        if not isinstance(body, Mapping):
            raise CaseCorrespondenceError("request_body")
        if any(name in body for name in _MINT_FIELDS):
            raise CaseCorrespondenceError("request_cannot_mint_authority")
        case_id = _label(body.get("case_id"), "missing_case")
        listed = self._messages.list_threads(actor_principal_id, body, verify_access=verify_access)
        owner = str(listed["canonical_owner_principal_id"])
        if listed.get("case_id") != case_id:
            raise CaseCorrespondenceError("owner_mismatch")
        messages = self._messages_for(actor_principal_id, body, listed, verify_access=verify_access)
        turns, reviews, turn_status, review_status = self._activity_rows(
            actor_principal_id, case_id, owner, listed,
        )
        actions, action_status = self._actions(actor_principal_id, body, listed)
        entries = [*turns, *self._message_entries(messages, owner), *reviews, *actions]
        entries = [self._with_workflow(entry, case_id) for entry in entries]
        entries.sort(key=_sort_key)
        if any(_sort_key(entries[index]) > _sort_key(entries[index + 1]) for index in range(len(entries) - 1)):
            raise CaseCorrespondenceError("order_mismatch")
        message_status = "available" if messages else "empty"
        return {
            "task_id": TASK_ID,
            "operation": "project_correspondence",
            "projection_is_authority": False,
            "adopts_evidence": False,
            "adopts_answer": False,
            "case_id": case_id,
            "actor_principal_id": listed["actor_principal_id"],
            "canonical_owner_principal_id": owner,
            "actor_is_encrypted_owner": listed["actor_principal_id"] == owner,
            "entries": entries,
            "entry_count": len(entries),
            "ordered": True,
            "order": "occurred_at,record_type,sequence,source_id",
            "sources": {
                "ai_mediator_turns": turn_status,
                "human_messages": message_status,
                "review_decisions": review_status,
                "case_actions": action_status,
            },
            "record_types": list(RECORD_TYPES),
            "limitations": list(LIMITATIONS),
        }

    def _messages_for(self, actor: str, body: Mapping[str, Any], listed: Mapping[str, Any], *, verify_access) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for thread in listed.get("threads") or []:
            if not isinstance(thread, Mapping) or thread.get("case_id") != listed.get("case_id"):
                raise CaseCorrespondenceError("owner_mismatch")
            cursor = 0
            for _page in range(_MAX_PAGES):
                material = dict(body)
                material["limit"] = _PAGE_LIMIT
                material["cursor"] = cursor
                page = self._messages.page(actor, str(thread["thread_id"]), material, verify_access=verify_access)
                if page.get("case_id") != listed.get("case_id") or page.get("canonical_owner_principal_id") != listed.get("canonical_owner_principal_id"):
                    raise CaseCorrespondenceError("owner_mismatch")
                batch = page.get("messages") or []
                if not isinstance(batch, list):
                    raise CaseCorrespondenceError("activity_record")
                rows.extend(item for item in batch if isinstance(item, Mapping))
                nxt = page.get("next_cursor")
                if nxt is None:
                    break
                if type(nxt) is not int or nxt <= cursor:
                    raise CaseCorrespondenceError("order_mismatch")
                cursor = nxt
            else:
                raise CaseCorrespondenceError("order_mismatch")
        return rows

    def _message_entries(self, messages: list[Mapping[str, Any]], owner: str) -> list[dict[str, Any]]:
        entries = []
        for message in messages:
            if message.get("canonical_owner_principal_id") != owner:
                raise CaseCorrespondenceError("owner_mismatch")
            if message.get("disposition") not in {"conversation", "evidence", "answer", "model_input"}:
                raise CaseCorrespondenceError("activity_record")
            created = None
            versions = message.get("versions")
            if isinstance(versions, list) and versions:
                stamp = versions[-1].get("created_at") if isinstance(versions[-1], Mapping) else None
                if type(stamp) is int:
                    created = stamp
            adoption = message.get("adoption")
            entries.append(_entry(
                record_type="human_message",
                source_id=_label(message.get("message_id"), "activity_record"),
                occurred_at=created,
                sequence=message.get("sequence") if type(message.get("sequence")) is int else None,
                actor_principal_id=_label(message.get("sender_principal_id"), "activity_record"),
                canonical_owner_principal_id=owner,
                invocation_id=None,
                target_kind="case_message",
                target_id=_label(message.get("message_id"), "activity_record"),
                revision=_revision(message.get("current_version")),
                extra={
                    "thread_id": message.get("thread_id"),
                    "disposition": message.get("disposition"),
                    "text": message.get("text"),
                    "adoption_recorded_on_source": isinstance(adoption, Mapping),
                    "recorded_as_evidence_artifact": False,
                    "recorded_as_intake_answer": False,
                },
            ))
        return entries

    def _activity_rows(self, actor: str, case_id: str, owner: str, listed: Mapping[str, Any]) -> tuple[list, list, str, str]:
        reader = getattr(self._activity, "authorized_correspondence_activity", None)
        if not callable(reader):
            return [], [], "unavailable", "unavailable"
        threads = listed.get("threads") or []
        resource_id = ""
        if threads and isinstance(threads[0], Mapping):
            resource_id = str(threads[0].get("resource_id") or "")
        if resource_id == "":
            resource_id = self._resource_id(actor, case_id, owner)
        payload = reader(
            actor_principal_id=actor,
            case_id=case_id,
            tenant_id=owner,
            resource_id=resource_id,
        )
        if not isinstance(payload, Mapping):
            raise CaseCorrespondenceError("activity_record")
        turns, turn_status = self._bucket(payload.get("mediator_turns"), "ai_mediator_turn", case_id, owner)
        reviews, review_status = self._bucket(payload.get("review_decisions"), "review_decision", case_id, owner)
        return turns, reviews, turn_status, review_status

    def _bucket(self, raw: Any, record_type: str, case_id: str, owner: str) -> tuple[list[dict[str, Any]], str]:
        if raw == "unavailable" or raw is None:
            return [], "unavailable"
        if not isinstance(raw, list):
            raise CaseCorrespondenceError("activity_record")
        rows = [_activity_row(item, expected_type=record_type, case_id=case_id, owner=owner) for item in raw]
        return rows, "available" if rows else "empty"

    def _with_workflow(self, entry: Mapping[str, Any], case_id: str) -> dict[str, Any]:
        row = dict(entry)
        row["workflow"] = self._workflow_for(row, case_id)
        row["adopts_evidence"] = False
        row["adopts_answer"] = False
        if row.get("record_type") == "ai_mediator_turn":
            row["attribution"] = "ai"
        elif row.get("record_type") == "human_message":
            row["attribution"] = "human"
            row["disposition"] = row.get("disposition") or "conversation"
        return row

    def _workflow_for(self, entry: Mapping[str, Any], case_id: str) -> dict[str, Any]:
        record_type = str(entry.get("record_type") or "")
        attribution = _ATTRIBUTION.get(record_type, "unknown")
        base = {
            "exact": False,
            "eligible": False,
            "adopted": False,
            "explicit": False,
            "context_kind": None,
            "context_id": None,
            "context_revision": None,
            "section_id": None,
            "span": None,
            "navigation": None,
            "attribution": attribution,
            "reason": "human_message_stays_conversation" if record_type == "human_message" else "no_workflow_context",
            "accepted_by_display": False,
            "display_changes_attribution": False,
            "wrote_evidence_artifact": False,
            "wrote_intake_answer": False,
        }
        if record_type == "human_message":
            source_id = str(entry.get("source_id") or "")
            link = self._messages.workflow_link(source_id) if hasattr(self._messages, "workflow_link") else None
            adoption = self._messages.workflow_adoption(source_id) if hasattr(self._messages, "workflow_adoption") else None
            if not isinstance(link, Mapping) or link.get("case_id") != case_id:
                return base
            context = link.get("context") if isinstance(link.get("context"), Mapping) else {}
            if context.get("eligible") is not True:
                base["reason"] = "material_not_eligible"
                return base
            adopted = isinstance(adoption, Mapping) and adoption.get("explicit") is True and adoption.get("case_id") == case_id
            view = _workflow_view(case_id, context, attribution="human", eligible=True, adopted=adopted, reason="exact_workflow_context")
            view["message_version"] = link.get("message_version")
            if adopted:
                view["explicit"] = True
                view["authorized_action"] = adoption.get("authorized_action")
                view["accepted_by_display"] = False
                view["ai_text_became_human"] = False
                view["ai_text_became_fact"] = False
            return view
        target = entry.get("target") if isinstance(entry.get("target"), Mapping) else {}
        kind = _WORKFLOW_TARGETS.get(str(target.get("kind") or ""))
        if kind is None or not target.get("id"):
            if record_type == "ai_mediator_turn":
                base["reason"] = "ai_text_is_not_human_or_evidence"
                base["eligible"] = False
            return base
        reason = "ai_text_is_not_human_or_evidence" if record_type == "ai_mediator_turn" else "navigation_is_not_adoption"
        return _workflow_view(
            case_id,
            {
                "context_kind": kind,
                "context_id": target.get("id"),
                "context_revision": entry.get("revision"),
                "section_id": None,
                "span": None,
                "eligible": False,
            },
            attribution=attribution,
            eligible=False,
            adopted=False,
            reason=reason,
        )

    def _resource_id(self, actor: str, case_id: str, owner: str) -> str:
        cases = getattr(getattr(self._messages, "store", None), "_cases", None)
        select = getattr(cases, "select_case", None)
        if not callable(select):
            return ""
        try:
            case = select(actor_principal_id=actor, case_id=case_id)
        except Exception:
            return ""
        if getattr(case, "tenant_id", None) != owner:
            raise CaseCorrespondenceError("owner_mismatch")
        return str(getattr(case, "resource_id", "") or "")

    def _actions(self, actor: str, body: Mapping[str, Any], listed: Mapping[str, Any]) -> tuple[list[dict[str, Any]], str]:
        audit = self._audit
        history = getattr(audit, "history", None)
        if not callable(history):
            return [], "unavailable"
        owner = str(listed["canonical_owner_principal_id"])
        case_id = str(listed["case_id"])
        resource_id = self._resource_id(actor, case_id, owner)
        revision = None
        grant_id = body.get("membership_grant_id")
        if isinstance(grant_id, str) and grant_id != "":
            memberships = getattr(getattr(self._messages, "store", None), "_memberships", None)
            load = getattr(memberships, "load", None)
            if not callable(load):
                raise CaseCorrespondenceError("audit_unavailable")
            try:
                grant = load(grant_id)
            except Exception as exc:
                raise CaseCorrespondenceError("missing_grant") from exc
            if getattr(grant, "tenant_id", None) != owner or getattr(grant, "case_id", None) != case_id:
                raise CaseCorrespondenceError("owner_mismatch")
            resource_id = str(grant.resource_id)
            revision = grant.case_revision
            grant_kind = "membership"
            membership_version = body.get("expected_membership_version")
            if isinstance(membership_version, str) and membership_version.isdigit():
                membership_version = int(membership_version)
            if type(membership_version) is not int:
                raise CaseCorrespondenceError("membership_revision_conflict")
        else:
            cases = getattr(getattr(self._messages, "store", None), "_cases", None)
            try:
                case = cases.select_case(actor_principal_id=actor, case_id=case_id)
            except Exception as exc:
                raise CaseCorrespondenceError("audit_unavailable") from exc
            if case.tenant_id != owner:
                raise CaseCorrespondenceError("owner_mismatch")
            resource_id = case.resource_id
            revision = case.revision
            from applications.case_audit import owner_grant_reference
            grant_id = owner_grant_reference(case.tenant_id)
            grant_kind = "owner"
            membership_version = None
        try:
            events = history(
                actor_principal_id=actor,
                case_id=case_id,
                tenant_id=owner,
                resource_id=resource_id,
                grant_id=grant_id,
                grant_kind=grant_kind,
                expected_revision=revision,
                membership_version=membership_version,
            )
        except Exception as exc:
            code = getattr(exc, "code", None)
            raise CaseCorrespondenceError(str(code or "audit_unavailable")) from exc
        rows = []
        for event in events:
            view = event.public_view() if hasattr(event, "public_view") else None
            if not isinstance(view, Mapping):
                raise CaseCorrespondenceError("activity_record")
            if view.get("case_id") != case_id or view.get("canonical_owner_principal_id") != owner:
                raise CaseCorrespondenceError("owner_mismatch")
            rows.append(_entry(
                record_type="case_action",
                source_id=_label(view.get("event_id"), "activity_record"),
                occurred_at=None,
                sequence=view.get("sequence") if type(view.get("sequence")) is int else None,
                actor_principal_id=_label(view.get("actor_principal_id"), "activity_record"),
                canonical_owner_principal_id=owner,
                invocation_id=None,
                target_kind="case_resource",
                target_id=_label(view.get("resource_id"), "activity_record"),
                revision=_revision(view.get("revision")),
                extra={
                    "action": view.get("action"),
                    "purpose_ref": view.get("purpose_ref"),
                    "grant_kind": view.get("grant_kind"),
                },
            ))
        return rows, "available" if rows else "empty"


def mount_case_correspondence(app: Any) -> None:
    """Mount the projection on the case catalog boundary. It only reads."""

    from fastapi.responses import JSONResponse

    def _service(request: Any) -> CaseCorrespondenceService:
        messages = getattr(request.app.state, "case_messages", None)
        audit = getattr(request.app.state, "case_audit", None)
        activity = getattr(request.app.state, "case_handlers", None)
        try:
            return CaseCorrespondenceService(messages, audit=audit, activity=activity)
        except CaseCorrespondenceError:
            raise
        except Exception as exc:
            raise CaseCorrespondenceError("correspondence_unavailable") from exc

    def _actor(request: Any) -> str:
        principal = getattr(request.state, "browser_principal", None)
        actor = getattr(principal, "principal_id", None)
        if not isinstance(actor, str) or actor == "":
            raise CaseCorrespondenceError("unauthenticated")
        return actor

    def _material(request: Any) -> Mapping[str, Any]:
        material = getattr(request.state, "case_catalog_material", None)
        return material if isinstance(material, dict) else {}

    def _fail(exc: CaseCorrespondenceError) -> JSONResponse:
        return JSONResponse({"error": exc.code}, status_code=correspondence_http_status(exc.code), headers=_NO_STORE)

    @app.get("/api/cases/correspondence")
    async def project_correspondence(request: Request):
        try:
            service = _service(request)
            sessions = getattr(request.app.state, "browser_sessions", None)
            bound = getattr(request.state, "browser_principal", None)
            token = request.cookies.get(SESSION_COOKIE)
            if not isinstance(sessions, BrowserSessionService) or bound is None:
                raise CaseCorrespondenceError("unauthenticated")

            def verify():
                try:
                    current = sessions.authenticate_token(token)
                except BrowserSessionError:
                    raise CaseCorrespondenceError("unauthenticated") from None
                if (current.principal_id, current.tenant_id, current.generation) != (
                        bound.principal_id, bound.tenant_id, bound.generation):
                    raise CaseCorrespondenceError("unauthenticated")
                if getattr(request.app.state, "browser_sessions", None) is not sessions:
                    raise CaseCorrespondenceError("correspondence_unavailable")
                if getattr(request.app.state, "case_messages", None) is not service._messages:
                    raise CaseCorrespondenceError("correspondence_unavailable")

            verify()
            result = await run_in_threadpool(service.project, _actor(request), _material(request), verify_access=verify)
            verify()
            return JSONResponse(result, status_code=200, headers=_NO_STORE)
        except CaseMessageError as exc:
            return JSONResponse({"error": exc.code}, status_code=message_http_status(exc.code), headers=_NO_STORE)
        except CaseCorrespondenceError as exc:
            return _fail(exc)
