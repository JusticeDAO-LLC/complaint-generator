"""HTTP owner for encrypted shared attachments and derived artifacts.

The browser session supplies the actor. Bodies cannot mint a role, a key, or
a grant. Filenames, previews, and derived indexes are returned only from a
download that has just rechecked the actor grant. Listing stays opaque.

Admission is JSON base64 inside the existing case body limit. This route does
not accept multipart uploads and does not claim a streaming transport.
"""

from __future__ import annotations

import base64
from typing import Any, Mapping

from starlette.requests import Request
from starlette.concurrency import run_in_threadpool
from applications.browser_sessions import BrowserSessionError, BrowserSessionService, SESSION_COOKIE
from applications.case_directory import CaseDirectoryError
from applications.case_membership import CaseMembershipError
from applications.case_messages import CaseMessageError, CaseMessageStore

from integrations.private_collaboration import (
    ATTACHMENT_KIND,
    WRITE_ACTION,
    CaseResourceKeyGrantError,
    BROWSER_KEY_FIELDS,
    SharedAttachmentError,
    SharedAttachmentStore,
    UserOwnedKeySession,
    attachment_http_status,
)

TASK_ID = "CIMP-GUI-37"
MESSAGE_ATTACHMENT_TASK = "CIMP-GUI-43"
MESSAGE_ATTACHMENT_LIMITATIONS = (
    "attachment_bound_to_thread_membership_grant_and_resource_revision",
    "revocation_rechecked_per_request",
    "no_path_or_cid_selection",
    "plaintext_responses_are_not_browser_cacheable",
    "notifications_stay_inside_the_admitted_tenant_and_thread",
    "no_websocket_or_sse",
)
_SELECTOR_FIELDS = frozenset({
    "path",
    "cid",
    "content_cid",
    "preview_cid",
    "index_cid",
    "local_path",
    "filesystem_path",
    "file_path",
    "uri",
    "url",
})
_NO_STORE_HEADERS = {
    "Cache-Control": "no-store, max-age=0, private",
    "Pragma": "no-cache",
    "Expires": "0",
}


def _label(value: Any, code: str) -> str:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise SharedAttachmentError(code)
    if any(char in value for char in ("\x00", "\n", "\r", "/", "\\")):
        raise SharedAttachmentError(code)
    if len(value) > 200:
        raise SharedAttachmentError(code)
    return value


def _revision(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        raise SharedAttachmentError("revision_conflict")
    if type(value) is int:
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise SharedAttachmentError("revision_conflict")


def message_attachment_status(code: str) -> int:
    """Status for message-attachment denials. Selector mistakes stay forbidden."""

    if code == "missing_thread":
        return 404
    if code in {"membership_revision_conflict", "selector_rejected"}:
        return 409 if code == "membership_revision_conflict" else 403
    return attachment_http_status(code)


class CaseAttachmentService:
    """Route-facing facade. Key sessions are injected by the operator."""

    def __init__(self, store: SharedAttachmentStore, sessions: Mapping[str, UserOwnedKeySession]) -> None:
        if not isinstance(store, SharedAttachmentStore) or not isinstance(sessions, Mapping):
            raise SharedAttachmentError("authority_owners")
        self._store = store
        self._sessions = dict(sessions)
        for principal_id, session in self._sessions.items():
            if not isinstance(principal_id, str) or not isinstance(session, UserOwnedKeySession):
                raise SharedAttachmentError("key_owner_required")
        self._messages: CaseMessageStore | None = None
        self._bindings: dict[str, dict[str, Any]] = {}
        self._notices: list[dict[str, Any]] = []

    def bind_message_admission(self, messages: CaseMessageStore) -> None:
        """Use the conversation store's case and membership owners for admission."""

        if not isinstance(messages, CaseMessageStore):
            raise SharedAttachmentError("authority_owners")
        if not isinstance(getattr(messages, "_cases", None), object) or not hasattr(messages, "_memberships"):
            raise SharedAttachmentError("authority_owners")
        self._messages = messages

    @property
    def store(self) -> SharedAttachmentStore:
        return self._store

    def store_attachment(self, actor_principal_id: str, body: Mapping[str, Any], *, verify_access=None) -> dict[str, Any]:
        material = self._body(body)
        content = self._content(material)
        session = self._session(actor_principal_id)
        admission = self._admit(actor_principal_id, material) if self._messages is not None else None
        binding_verify = (self._binding_verifier(actor_principal_id, material, session, verify_access)
            if admission is not None else None)

        def _verify() -> None:
            if verify_access is not None:
                verify_access()
            if admission is not None:
                self._admit(actor_principal_id, material)

        if admission is not None:
            _verify()
        delegated = isinstance(material.get("key_grant_id"), str)
        if not delegated:
            created = self._store.store(
                actor_principal_id=actor_principal_id,
                tenant_id=str(material.get("tenant_id") or ""),
                case_id=str(material.get("case_id") or ""),
                resource_id=str(material.get("resource_id") or ""),
                artifact_revision=str(material.get("artifact_revision") or ""),
                filename=str(material.get("filename") or ""),
                media_type=str(material.get("media_type") or ""),
                content=content,
                idempotency_key=str(material.get("idempotency_key") or ""),
                owner_session=session, verify_access=_verify if admission is not None or verify_access is not None else None,
            )
        else:
            version = material.get("membership_version")
            created = self._store.store(
            actor_principal_id=actor_principal_id,
            tenant_id=str(material.get("tenant_id") or ""),
            case_id=str(material.get("case_id") or ""),
            resource_id=str(material.get("resource_id") or ""),
            artifact_revision=str(material.get("artifact_revision") or ""),
            filename=str(material.get("filename") or ""),
            media_type=str(material.get("media_type") or ""),
            content=content,
            idempotency_key=str(material.get("idempotency_key") or ""),
            recipient_session=session,
            membership_grant_id=material.get("membership_grant_id") if isinstance(material.get("membership_grant_id"), str) else None,
            membership_version=version if type(version) is int else None,
            key_grant_id=material.get("key_grant_id") if isinstance(material.get("key_grant_id"), str) else None,
            verify_access=_verify if admission is not None or verify_access is not None else None,
            )
        if admission is not None:
            _verify()
            self._bind(created, admission, material, verify_access=binding_verify)
            _verify()
            return self._present(created, admission)
        return created

    def list_attachments(self, actor_principal_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        material = self._body(body)
        admission = self._admit(actor_principal_id, material) if self._messages is not None else None
        version = material.get("membership_version")
        if isinstance(version, str) and version.isdigit():
            version = int(version)
        listed = self._store.list_public(
            actor_principal_id=actor_principal_id,
            tenant_id=str(material.get("tenant_id") or ""),
            case_id=str(material.get("case_id") or ""),
            resource_id=str(material.get("resource_id") or ""),
            membership_grant_id=material.get("membership_grant_id") if isinstance(material.get("membership_grant_id"), str) else None,
            membership_version=version if type(version) is int else None,
        )
        if admission is None:
            return listed
        self._admit(actor_principal_id, material)
        rows = []
        for item in listed.get("attachments", []):
            attachment_id = item.get("attachment_id")
            if not isinstance(attachment_id, str):
                continue
            try:
                self._matches(attachment_id, admission, material)
            except SharedAttachmentError:
                continue
            rows.append(self._present(item, admission))
        return {
            "attachments": rows,
            "private_filename": True,
            "private_preview": True,
            "private_derived_index": True,
            "thread_id": admission["thread_id"],
            "browser_cache": "no-store",
            "limitations": list(MESSAGE_ATTACHMENT_LIMITATIONS),
        }

    def preview_attachment(self, actor_principal_id: str, attachment_id: str, body: Mapping[str, Any], *, verify_access=None) -> dict[str, Any]:
        material = self._body(body)
        if material.get("artifact_role") not in (None, "preview"):
            raise SharedAttachmentError("attachment_role_mismatch")
        preview_body = dict(material)
        preview_body["artifact_role"] = "preview"
        return self.download_attachment(actor_principal_id, attachment_id, preview_body, verify_access=verify_access)

    def download_attachment(self, actor_principal_id: str, attachment_id: str, body: Mapping[str, Any], *, verify_access=None) -> dict[str, Any]:
        material = self._body(body)
        session = self._session(actor_principal_id)
        version = material.get("membership_version")
        if isinstance(version, str) and version.isdigit():
            version = int(version)
        role = material.get("artifact_role") if isinstance(material.get("artifact_role"), str) else "content"
        admission = self._admit(actor_principal_id, material) if self._messages is not None else None
        if admission is not None:
            self._matches(_label(attachment_id, "attachment_id"), admission, material)

        def _verify() -> None:
            if verify_access is not None:
                verify_access()
            if admission is not None:
                current = self._admit(actor_principal_id, material)
                self._matches(_label(attachment_id, "attachment_id"), current, material)

        if admission is not None:
            _verify()
        if not isinstance(material.get("key_grant_id"), str):
            opened = self._store.download(
                actor_principal_id=actor_principal_id,
                tenant_id=str(material.get("tenant_id") or ""),
                case_id=str(material.get("case_id") or ""),
                resource_id=str(material.get("resource_id") or ""),
                attachment_id=attachment_id,
                owner_session=session,
                role=role, verify_access=_verify if admission is not None or verify_access is not None else None,
            )
        else:
            opened = self._store.download(
            actor_principal_id=actor_principal_id,
            tenant_id=str(material.get("tenant_id") or ""),
            case_id=str(material.get("case_id") or ""),
            resource_id=str(material.get("resource_id") or ""),
            attachment_id=attachment_id,
            recipient_session=session,
            membership_grant_id=material.get("membership_grant_id") if isinstance(material.get("membership_grant_id"), str) else None,
            membership_version=version if type(version) is int else None,
            key_grant_id=material.get("key_grant_id") if isinstance(material.get("key_grant_id"), str) else None,
            role=role, verify_access=_verify if admission is not None or verify_access is not None else None,
            )
        if admission is not None:
            _verify()
            return self._present(opened, admission)
        return opened

    def _session(self, actor_principal_id: str) -> UserOwnedKeySession:
        session = self._sessions.get(actor_principal_id)
        if not isinstance(session, UserOwnedKeySession):
            raise SharedAttachmentError("key_owner_required")
        return session

    def _binding_verifier(self, actor, material, session, verify_access):
        """Keep the actual attachment owner's key/grant live through metadata publication.

        Reuse the existing key owner, including its real recipient unwrap and
        cutoff checks; a membership flag or stored grant ID is not key proof.
        No message-store lock is acquired by this callback.
        """
        from integrations.private_storage import PrivateArtifactBinding, PrivateKeyMaterialError
        from integrations.private_collaboration import _zero
        def key():
            try:
                owned = self._store._owner_case(actor, str(material.get("case_id") or ""))
                if owned is not None:
                    binding = PrivateArtifactBinding(tenant_id=owned.tenant_id, case_id=owned.case_id,
                        artifact_kind=ATTACHMENT_KIND, revision=str(material.get("artifact_revision") or ""),
                        principal_id=owned.tenant_id)
                    key_id, data = session.provider().resolve(binding)
                    return key_id, bytes(data), (owned.revision, owned.resource_id)
                grant, decision, data = self._store._grants._authorize_delegated(
                    actor_principal_id=actor, membership_grant_id=material.get("membership_grant_id"),
                    membership_version=material.get("membership_version"), key_grant_id=material.get("key_grant_id"),
                    case_id=str(material.get("case_id") or ""), tenant_id=str(material.get("tenant_id") or ""),
                    resource_id=str(material.get("resource_id") or ""), artifact_kind=ATTACHMENT_KIND,
                    artifact_revision=str(material.get("artifact_revision") or ""), recipient_session=session, action=WRITE_ACTION)
                try:
                    return grant.data_key_id, bytes(data), (grant.generation, decision.version)
                finally:
                    _zero(data)
            except (CaseResourceKeyGrantError, PrivateKeyMaterialError) as exc:
                raise SharedAttachmentError(getattr(exc, "code", "key_unavailable")) from None
        admitted = key()
        def verify():
            if verify_access is not None:
                verify_access()
            if key() != admitted:
                raise SharedAttachmentError("key_changed")
            if verify_access is not None:
                verify_access()
        return verify

    def recheck_message_admission(self, actor_principal_id: str, body: Mapping[str, Any]) -> dict[str, Any] | None:
        """Repeat thread, membership, and resource-revision admission for this request."""

        if self._messages is None:
            return None
        return self._admit(actor_principal_id, body)

    def list_notices(self, actor_principal_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        admission = self._require_admission(actor_principal_id, body)
        self._require_admission(actor_principal_id, body)
        records = self._messages.thread_attachment_bindings(actor_principal_id, body)
        notices = [
            {key: item[key] for key in ("tenant_id", "case_id", "thread_id", "resource_id", "resource_revision", "attachment_id", "actor_principal_id")}
            for item in records
            if item["tenant_id"] == admission["tenant_id"]
            and item["case_id"] == admission["case_id"]
            and item["thread_id"] == admission["thread_id"]
            and item["resource_id"] == admission["resource_id"]
            and item["resource_revision"] == admission["resource_revision"]
        ]
        return {
            "notices": notices,
            "cross_tenant": False,
            "plaintext": False,
            "limitations": list(MESSAGE_ATTACHMENT_LIMITATIONS),
        }

    def _require_admission(self, actor_principal_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        if self._messages is None:
            raise SharedAttachmentError("message_admission_required")
        return self._admit(actor_principal_id, body)

    def _admit(self, actor_principal_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        messages = self._messages
        if not isinstance(messages, CaseMessageStore):
            raise SharedAttachmentError("message_admission_required")
        material = self._body(body)
        thread_id = _label(material.get("thread_id"), "thread_id")
        case_id = _label(material.get("case_id"), "case_id")
        resource_revision = _revision(material.get("expected_revision"))
        artifact_revision = _label(material.get("artifact_revision"), "artifact_revision")
        message_body: dict[str, Any] = {"case_id": case_id}
        if "tenant_id" in material:
            message_body["tenant_id"] = material.get("tenant_id")
        if "resource_id" in material:
            message_body["resource_id"] = material.get("resource_id")
        grant_id = material.get("membership_grant_id")
        if isinstance(grant_id, str):
            message_body["membership_grant_id"] = grant_id
            version = material.get("expected_membership_version", material.get("membership_version"))
            if isinstance(version, str) and version.isdigit():
                version = int(version)
            if type(version) is not int:
                raise SharedAttachmentError("membership_revision_conflict")
            message_body["expected_membership_version"] = version
        try:
            listing = messages.list_threads(actor_principal_id, message_body)
        except CaseMessageError as exc:
            raise SharedAttachmentError(exc.code) from exc
        thread = next((item for item in listing.get("threads", []) if item.get("thread_id") == thread_id), None)
        if not isinstance(thread, dict):
            raise SharedAttachmentError("missing_thread")
        if thread.get("case_id") != case_id:
            raise SharedAttachmentError("missing_thread")
        cases = messages._cases
        memberships = messages._memberships
        try:
            owned = cases.select_case(actor_principal_id=actor_principal_id, case_id=case_id)
        except CaseDirectoryError:
            owned = None
        if owned is not None and owned.owner_principal_id == actor_principal_id:
            if owned.revision != resource_revision:
                raise SharedAttachmentError("revision_conflict")
            if owned.resource_id != thread.get("resource_id") or owned.tenant_id != thread.get("tenant_id"):
                raise SharedAttachmentError("resource_mismatch")
            if material.get("resource_id") not in (None, owned.resource_id) or material.get("tenant_id") not in (None, owned.tenant_id):
                raise SharedAttachmentError("resource_mismatch")
            tenant_id = owned.tenant_id
            resource_id = owned.resource_id
        else:
            if not isinstance(grant_id, str):
                raise SharedAttachmentError("missing_grant")
            try:
                grant = memberships.load(grant_id)
            except CaseMembershipError as exc:
                raise SharedAttachmentError("missing_grant") from exc
            if grant.status != "accepted" or actor_principal_id not in {grant.owner_principal_id, grant.member_principal_id}:
                raise SharedAttachmentError("missing_grant")
            if grant.case_id != case_id or grant.tenant_id != thread.get("tenant_id"):
                raise SharedAttachmentError("tenant_mismatch")
            if grant.resource_id != thread.get("resource_id"):
                raise SharedAttachmentError("resource_mismatch")
            if grant.case_revision != resource_revision:
                raise SharedAttachmentError("revision_conflict")
            tenant_id = grant.tenant_id
            resource_id = grant.resource_id
        if not isinstance(material.get("key_grant_id"), str) and owned is None:
            raise SharedAttachmentError("missing_grant")
        return {
            "thread_id": thread_id,
            "tenant_id": tenant_id,
            "case_id": case_id,
            "resource_id": resource_id,
            "resource_revision": resource_revision,
            "artifact_revision": artifact_revision,
            "actor_principal_id": actor_principal_id,
        }

    def _bind(self, view: Mapping[str, Any], admission: Mapping[str, Any], material, *, verify_access=None) -> None:
        attachment_id = _label(view.get("attachment_id"), "attachment_id")
        if view.get("tenant_id") != admission["tenant_id"] or view.get("case_id") != admission["case_id"]:
            raise SharedAttachmentError("tenant_mismatch")
        if view.get("resource_id") != admission["resource_id"] or view.get("revision") != admission["artifact_revision"]:
            raise SharedAttachmentError("revision_conflict")
        record = {
            "attachment_id": attachment_id,
            "thread_id": admission["thread_id"],
            "tenant_id": admission["tenant_id"],
            "case_id": admission["case_id"],
            "resource_id": admission["resource_id"],
            "resource_revision": admission["resource_revision"],
            "artifact_revision": admission["artifact_revision"],
            "actor_principal_id": admission["actor_principal_id"],
        }
        try:
            self._messages.record_thread_attachment(admission["actor_principal_id"], material, record,
                verify_access=verify_access)
        except CaseMessageError as exc:
            raise SharedAttachmentError(exc.code) from exc

    def _matches(self, attachment_id: str, admission: Mapping[str, Any], material) -> None:
        try:
            rows = self._messages.thread_attachment_bindings(admission["actor_principal_id"], material,
                attachment_id=attachment_id)
        except CaseMessageError as exc:
            raise SharedAttachmentError(exc.code) from exc
        record = rows[0] if len(rows) == 1 else None
        if record is None or record["thread_id"] != admission["thread_id"] or record["case_id"] != admission["case_id"]:
            raise SharedAttachmentError("missing_attachment")
        if record["tenant_id"] != admission["tenant_id"]:
            raise SharedAttachmentError("tenant_mismatch")
        if record["resource_id"] != admission["resource_id"]:
            raise SharedAttachmentError("resource_mismatch")
        if record["resource_revision"] != admission["resource_revision"] or record["artifact_revision"] != admission["artifact_revision"]:
            raise SharedAttachmentError("revision_conflict")

    def _present(self, view: Mapping[str, Any], admission: Mapping[str, Any] | None) -> dict[str, Any]:
        presented = dict(view)
        if admission is None:
            return presented
        for name in ("content_cid", "preview_cid", "index_cid"):
            presented.pop(name, None)
        presented["thread_id"] = admission["thread_id"]
        presented["resource_revision"] = admission["resource_revision"]
        presented["bound_to_thread"] = True
        presented["browser_cache"] = "no-store"
        presented["selector"] = "attachment_id"
        presented["task_id"] = MESSAGE_ATTACHMENT_TASK
        presented["limitations"] = list(MESSAGE_ATTACHMENT_LIMITATIONS)
        return presented

    def _guard(self, actor_principal_id: str, body: Mapping[str, Any], verify_access: Any) -> dict[str, Any] | None:
        if self._messages is None:
            return None
        admission = self._admit(actor_principal_id, body)

        def _recheck() -> None:
            if verify_access is not None:
                verify_access()
            self._admit(actor_principal_id, body)

        self._recheck = _recheck
        _recheck()
        return admission

    def _body(self, body: Mapping[str, Any]) -> Mapping[str, Any]:
        if not isinstance(body, Mapping):
            raise SharedAttachmentError("request_body")
        if any(name in body for name in BROWSER_KEY_FIELDS):
            raise SharedAttachmentError("browser_key_rejected")
        if any(name in body for name in _SELECTOR_FIELDS):
            raise SharedAttachmentError("selector_rejected")
        return body

    def _content(self, body: Mapping[str, Any]) -> bytes:
        encoded = body.get("content_base64")
        if not isinstance(encoded, str) or encoded.strip() == "":
            raise SharedAttachmentError("content_rejected")
        try:
            return base64.b64decode(encoded.encode("ascii"), validate=True)
        except (UnicodeEncodeError, ValueError) as exc:
            raise SharedAttachmentError("content_rejected") from exc


def mount_case_attachments(app: Any) -> None:
    """Mount attachment routes on the authenticated case catalog boundary."""

    from fastapi.responses import JSONResponse

    def _service(request: Any) -> CaseAttachmentService:
        service = getattr(request.app.state, "case_attachments", None)
        if not isinstance(service, CaseAttachmentService):
            raise SharedAttachmentError("attachment_unavailable")
        return service

    def _actor(request: Any) -> str:
        principal = getattr(request.state, "browser_principal", None)
        actor = getattr(principal, "principal_id", None)
        if not isinstance(actor, str) or actor == "":
            raise SharedAttachmentError("unauthenticated")
        return actor

    def _session_verifier(request):
        sessions = getattr(request.app.state, "browser_sessions", None)
        bound = getattr(request.state, "browser_principal", None)
        token = request.cookies.get(SESSION_COOKIE)
        if not isinstance(sessions, BrowserSessionService) or bound is None:
            raise SharedAttachmentError("unauthenticated")
        def verify():
            try:
                current = sessions.authenticate_token(token)
            except BrowserSessionError as exc:
                raise SharedAttachmentError("unauthenticated") from exc
            if (current.principal_id != bound.principal_id or current.tenant_id != bound.tenant_id
                    or current.generation != bound.generation):
                raise SharedAttachmentError("unauthenticated")
        return verify

    def _material(request: Any) -> Mapping[str, Any]:
        material = getattr(request.state, "case_catalog_material", None)
        return material if isinstance(material, dict) else {}

    def _fail(exc: BaseException) -> JSONResponse:
        code = getattr(exc, "code", "attachment_unavailable")
        return JSONResponse({"error": code}, status_code=message_attachment_status(str(code)), headers=_NO_STORE_HEADERS)

    def _messages(request: Any):
        from applications.case_message_api import CaseMessageService

        service = getattr(request.app.state, "case_messages", None)
        return service if isinstance(service, CaseMessageService) and service._attachments is not None else None

    def _thread_material(request: Any, thread_id: str | None = None) -> Mapping[str, Any]:
        material = dict(_material(request))
        if thread_id is not None:
            supplied = material.get("thread_id", thread_id)
            if supplied != thread_id:
                raise SharedAttachmentError("thread_mismatch")
            material["thread_id"] = thread_id
        return material

    @app.post("/api/cases/attachments")
    async def attachment_store(request: Request):
        try:
            verify = _session_verifier(request)
            verify()
            messages = _messages(request)
            actor, material = _actor(request), _material(request)
            if messages is not None:
                created = await run_in_threadpool(messages.share_attachment, actor, str(material.get("thread_id") or ""),
                    material, verify_access=verify)
                await run_in_threadpool(_service(request).recheck_message_admission, actor, material)
            else:
                created = await run_in_threadpool(_service(request).store_attachment, actor, material, verify_access=verify)
            verify()
        except (SharedAttachmentError, CaseMessageError) as exc:
            return _fail(exc)
        return JSONResponse(created, status_code=201, headers=_NO_STORE_HEADERS)

    @app.get("/api/cases/attachments")
    async def attachment_list(request: Request):
        try:
            verify = _session_verifier(request)
            verify()
            messages = _messages(request)
            actor, material = _actor(request), _material(request)
            if messages is not None:
                payload = await run_in_threadpool(messages.list_attachments, actor, str(material.get("thread_id") or ""), material)
                await run_in_threadpool(_service(request).recheck_message_admission, actor, material)
            else:
                payload = await run_in_threadpool(_service(request).list_attachments, actor, material)
            verify()
            return JSONResponse(payload, headers=_NO_STORE_HEADERS)
        except (SharedAttachmentError, CaseMessageError) as exc:
            return _fail(exc)

    @app.post("/api/cases/attachments/{attachment_id}/download")
    async def attachment_download(attachment_id: str, request: Request):
        try:
            verify = _session_verifier(request)
            verify()
            messages = _messages(request)
            actor, material = _actor(request), _material(request)
            if messages is not None:
                payload = await run_in_threadpool(messages.read_attachment, actor, str(material.get("thread_id") or ""),
                    attachment_id, material, verify_access=verify)
                await run_in_threadpool(_service(request).recheck_message_admission, actor, material)
            else:
                payload = await run_in_threadpool(_service(request).download_attachment, actor,
                    attachment_id, material, verify_access=verify)
            verify()
            return JSONResponse(payload, headers=_NO_STORE_HEADERS)
        except (SharedAttachmentError, CaseMessageError) as exc:
            return _fail(exc)

    @app.post("/api/cases/messages/threads/{thread_id}/attachments")
    async def thread_attachment_store(thread_id: str, request: Request):
        try:
            verify = _session_verifier(request)
            verify()
            messages = _messages(request)
            if messages is None:
                raise SharedAttachmentError("message_admission_required")
            material = _thread_material(request, thread_id)
            created = await run_in_threadpool(messages.share_attachment, _actor(request), thread_id, material, verify_access=verify)
            await run_in_threadpool(_service(request).recheck_message_admission, _actor(request), material)
            verify()
        except (SharedAttachmentError, CaseMessageError) as exc:
            return _fail(exc)
        return JSONResponse(created, status_code=201, headers=_NO_STORE_HEADERS)

    @app.get("/api/cases/messages/threads/{thread_id}/attachments")
    async def thread_attachment_list(thread_id: str, request: Request):
        try:
            verify = _session_verifier(request)
            verify()
            messages = _messages(request)
            if messages is None:
                raise SharedAttachmentError("message_admission_required")
            material = _thread_material(request, thread_id)
            payload = await run_in_threadpool(messages.list_attachments, _actor(request), thread_id, material)
            await run_in_threadpool(_service(request).recheck_message_admission, _actor(request), material)
            verify()
            return JSONResponse(payload, headers=_NO_STORE_HEADERS)
        except (SharedAttachmentError, CaseMessageError) as exc:
            return _fail(exc)

    @app.post("/api/cases/messages/threads/{thread_id}/attachments/{attachment_id}/download")
    async def thread_attachment_download(thread_id: str, attachment_id: str, request: Request):
        try:
            verify = _session_verifier(request)
            verify()
            messages = _messages(request)
            if messages is None:
                raise SharedAttachmentError("message_admission_required")
            material = _thread_material(request, thread_id)
            payload = await run_in_threadpool(messages.read_attachment, _actor(request), thread_id, attachment_id, material, verify_access=verify)
            await run_in_threadpool(_service(request).recheck_message_admission, _actor(request), material)
            verify()
            return JSONResponse(payload, headers=_NO_STORE_HEADERS)
        except (SharedAttachmentError, CaseMessageError) as exc:
            return _fail(exc)

    @app.post("/api/cases/messages/threads/{thread_id}/attachments/{attachment_id}/preview")
    async def thread_attachment_preview(thread_id: str, attachment_id: str, request: Request):
        try:
            verify = _session_verifier(request)
            verify()
            messages = _messages(request)
            if messages is None:
                raise SharedAttachmentError("message_admission_required")
            material = _thread_material(request, thread_id)
            payload = await run_in_threadpool(messages.preview_attachment, _actor(request), thread_id, attachment_id, material, verify_access=verify)
            await run_in_threadpool(_service(request).recheck_message_admission, _actor(request), material)
            verify()
            return JSONResponse(payload, headers=_NO_STORE_HEADERS)
        except (SharedAttachmentError, CaseMessageError) as exc:
            return _fail(exc)

    @app.get("/api/cases/messages/threads/{thread_id}/attachment-notices")
    async def thread_attachment_notices(thread_id: str, request: Request):
        try:
            verify = _session_verifier(request)
            verify()
            messages = _messages(request)
            if messages is None:
                raise SharedAttachmentError("message_admission_required")
            material = _thread_material(request, thread_id)
            payload = await run_in_threadpool(messages.attachment_notices, _actor(request), thread_id, material)
            await run_in_threadpool(_service(request).recheck_message_admission, _actor(request), material)
            verify()
            return JSONResponse(payload, headers=_NO_STORE_HEADERS)
        except (SharedAttachmentError, CaseMessageError) as exc:
            return _fail(exc)
