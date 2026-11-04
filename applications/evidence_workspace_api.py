"""HTTP handlers for the case-scoped evidence catalog and private uploads.

The browser session supplies the actor. A body cannot mint a role, a key, or
a legal conclusion. Missing keys and missing extraction capability stay
unavailable. A ciphertext receipt is not authenticity, relevance, admissibility,
or claim support.

Uploads are chunked control messages over the same catalog owner. Bytes are
held only until the private artifact owner seals them, then discarded. Progress
stays inside 0–99 until that seal, and a cancelled or stale attempt cannot
become a successful receipt.

Previews decrypt one requested artifact version for the current actor and
case, then drop those bytes. Text and PDF pages become plain strings. Raster
images are returned only when their bytes match a still image type. Other
formats get a safe alternative. Nothing in a preview is sent to a model, and
plaintext is not cached on the process.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import struct
import zlib
from pathlib import Path
from typing import Any, Mapping

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from applications.browser_sessions import SESSION_COOKIE, BrowserSessionError, BrowserSessionService
from applications.case_directory import CaseDirectoryError
from applications.evidence_annotation_store import ANNOTATION_TASK_ID, EvidenceAnnotationStore

from integrations.evidence_workspace import (
    CLASSIFICATION_TASK_ID,
    INGESTION_STATUSES,
    SUPPORT_LINK_TASK_ID,
    TASK_ID,
    EvidenceWorkspace,
    EvidenceWorkspaceError,
    legal_qualities,
)
from integrations.private_storage import BoundPrivateRecordError, PrivateStorageError, retrieve_private_artifact

UPLOAD_TASK_ID = "CIMP-UX-14"
PREVIEW_TASK_ID = "CIMP-UX-16"
_PREVIEW_TEXT = frozenset({"text/plain", "text/csv"})
_PREVIEW_IMAGES = frozenset({"image/png", "image/jpeg", "image/webp"})
_PREVIEW_REFUSED = frozenset({
    "invoke_model", "model", "prompt", "provider", "consent", "messages",
})
_MAX_UPLOAD_BYTES = 256 * 1024
_MAX_CHUNK_BYTES = 64 * 1024
_ALLOWED_MEDIA = frozenset({
    "text/plain",
    "text/csv",
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/tiff",
    "image/webp",
})
_REJECTED_FIELDS = frozenset({
    "cid", "url", "uri", "role", "roles", "trusted_local", "key", "passphrase",
    "admin_key", "is_admin", "is_staff", "staff_role",
})
_UPLOADS: dict[int, dict[str, dict[str, Any]]] = {}

_NO_STORE_HEADERS = {
    "Cache-Control": "no-store, max-age=0, private",
    "Pragma": "no-cache",
    "Expires": "0",
}


def evidence_http_status(code: str) -> int:
    if code in {"unauthenticated"}:
        return 401
    if code in {"not_owner", "tenant_mismatch", "selector_rejected", "legal_quality_rejected", "missing_evidence"}:
        return 403
    if code in {"revision_conflict", "replay_mismatch", "lifecycle_conflict", "operation_revoked", "upload_stale", "artifact_version_mismatch"}:
        return 409
    if code in {"request_body", "content_rejected", "action", "source_filename", "original_filename", "idempotency_key", "evidence_id", "failure_code", "complaint_link_id", "media_type", "actor", "media_rejected", "oversized", "upload_offset", "upload_id", "annotation_rejected", "artifact_version", "adoption_requires_explicit_action", "kind", "classifier_rejected", "support_link_rejected", "support_span_rejected"}:
        return 400
    if code == "missing_annotation":
        return 404
    if code == "upload_missing":
        return 404
    return 503


def mount_evidence_workspace(app: Any) -> None:
    """Mount catalog routes on the authenticated case boundary."""

    from fastapi.responses import JSONResponse

    def _service(request: Request) -> EvidenceWorkspace:
        service = getattr(request.app.state, "evidence_workspace", None)
        if not isinstance(service, EvidenceWorkspace):
            raise EvidenceWorkspaceError("evidence_unavailable")
        return service

    def _actor(request: Request) -> str:
        principal = getattr(request.state, "browser_principal", None)
        actor = getattr(principal, "principal_id", None)
        if not isinstance(actor, str) or actor == "":
            raise EvidenceWorkspaceError("unauthenticated")
        return actor

    def _verify(request: Request):
        sessions = getattr(request.app.state, "browser_sessions", None)
        bound = getattr(request.state, "browser_principal", None)
        token = request.cookies.get(SESSION_COOKIE)
        if not isinstance(sessions, BrowserSessionService) or bound is None:
            raise EvidenceWorkspaceError("unauthenticated")

        def verify() -> None:
            try:
                current = sessions.authenticate_token(token)
            except BrowserSessionError as exc:
                raise EvidenceWorkspaceError("unauthenticated") from exc
            if (current.principal_id != bound.principal_id or current.tenant_id != bound.tenant_id
                    or current.generation != bound.generation):
                raise EvidenceWorkspaceError("unauthenticated")

        return verify

    def _material(request: Request) -> Mapping[str, Any]:
        material = getattr(request.state, "case_catalog_material", None)
        return material if isinstance(material, Mapping) else {}

    def _fail(exc: EvidenceWorkspaceError) -> JSONResponse:
        code = exc.code
        body = {
            "task_id": TASK_ID,
            "error": code,
            "ingestion_status": "unavailable" if code in {"key_unavailable", "evidence_unavailable", "ciphertext_unavailable"} else "",
            "legal": legal_qualities(),
            "receipt_establishes_legal_quality": False,
            "operation_succeeded": False,
            "items": [],
            "allowed_ingestion_statuses": list(INGESTION_STATUSES),
        }
        return JSONResponse(body, status_code=evidence_http_status(code), headers=_NO_STORE_HEADERS)

    @app.post("/api/cases/evidence")
    async def receive_evidence(request: Request):
        try:
            verify = _verify(request)
            verify()
            service, actor, material = _service(request), _actor(request), _material(request)
            verify_key = await run_in_threadpool(service.key_scope_verifier, actor, material)
            verify()
            record = await run_in_threadpool(service.receive, actor, material, verify_request=verify_key)
            await run_in_threadpool(verify_key)
            verify()
        except EvidenceWorkspaceError as exc:
            return _fail(exc)
        return JSONResponse(record, status_code=201, headers=_NO_STORE_HEADERS)

    @app.post("/api/cases/evidence/lifecycle")
    async def transition_evidence(request: Request):
        try:
            verify = _verify(request)
            verify()
            service, actor, material = _service(request), _actor(request), _material(request)
            verify_key = await run_in_threadpool(service.key_scope_verifier, actor, material)
            verify()
            record = await run_in_threadpool(service.transition, actor, material, verify_request=verify_key)
            await run_in_threadpool(verify_key)
            verify()
        except EvidenceWorkspaceError as exc:
            return _fail(exc)
        status = 200 if record.get("operation_succeeded") else 409 if record.get("ingestion_status") == "failed" else 503
        return JSONResponse(record, status_code=status, headers=_NO_STORE_HEADERS)

    @app.get("/api/cases/evidence")
    async def list_evidence(request: Request):
        try:
            verify = _verify(request)
            verify()
            service, actor, material = _service(request), _actor(request), _material(request)
            verify_key = await run_in_threadpool(service.key_scope_verifier, actor, material)
            verify()
            catalog = await run_in_threadpool(service.list_catalog, actor, material, verify_request=verify_key)
            await run_in_threadpool(verify_key)
            verify()
        except EvidenceWorkspaceError as exc:
            return _fail(exc)
        status = 200 if catalog.get("error") in {None, ""} else 503
        return JSONResponse(catalog, status_code=status, headers=_NO_STORE_HEADERS)

    async def _call_upload(request: Request, operation):
        # Cached upload projections carry decrypted filenames too. Keep the
        # original key lifetime across thread dispatch and the HTTP response,
        # just as the catalog owner does for a fresh ciphertext operation.
        verify = _verify(request)
        verify()
        service, actor, material = _service(request), _actor(request), _material(request)
        verify_key = await run_in_threadpool(service.key_scope_verifier, actor, material)
        verify()
        payload = await run_in_threadpool(operation, request, actor, material, verify_request=verify_key)
        await run_in_threadpool(verify_key)
        verify()
        return payload

    @app.post("/api/cases/evidence/uploads")
    async def begin_evidence_upload(request: Request):
        try:
            payload = await _call_upload(request, _begin_upload)
        except EvidenceWorkspaceError as exc:
            return _fail(exc)
        code = 200 if payload.get("resumed") else 201
        return JSONResponse(payload, status_code=code, headers=_NO_STORE_HEADERS)

    @app.post("/api/cases/evidence/uploads/chunk")
    async def receive_evidence_chunk(request: Request):
        try:
            payload = await _call_upload(request, _accept_chunk)
        except EvidenceWorkspaceError as exc:
            return _fail(exc)
        return JSONResponse(payload, status_code=200, headers=_NO_STORE_HEADERS)

    @app.post("/api/cases/evidence/uploads/complete")
    async def complete_evidence_upload(request: Request):
        try:
            payload = await _call_upload(request, _complete_upload)
        except EvidenceWorkspaceError as exc:
            return _fail(exc)
        code = 200 if payload.get("idempotent_replay") else 201
        return JSONResponse(payload, status_code=code, headers=_NO_STORE_HEADERS)

    @app.post("/api/cases/evidence/uploads/cancel")
    async def cancel_evidence_upload(request: Request):
        try:
            payload = await _call_upload(request, _cancel_upload)
        except EvidenceWorkspaceError as exc:
            return _fail(exc)
        return JSONResponse(payload, status_code=200, headers=_NO_STORE_HEADERS)

    @app.post("/api/cases/evidence/uploads/retry")
    async def retry_evidence_upload(request: Request):
        try:
            payload = await _call_upload(request, _retry_upload)
        except EvidenceWorkspaceError as exc:
            return _fail(exc)
        code = 200 if payload.get("upload_state") == "sealed" else 201
        return JSONResponse(payload, status_code=code, headers=_NO_STORE_HEADERS)

    @app.get("/api/cases/evidence/uploads/status")
    async def evidence_upload_status(request: Request):
        try:
            payload = await _call_upload(request, _upload_status)
        except EvidenceWorkspaceError as exc:
            return _fail(exc)
        return JSONResponse(payload, status_code=200, headers=_NO_STORE_HEADERS)

    @app.post("/api/cases/evidence/annotations")
    async def create_evidence_annotation(request: Request):
        try:
            verify = _verify(request)
            verify()
            service, actor, material = _service(request), _actor(request), _material(request)
            verify_key = await run_in_threadpool(service.key_scope_verifier, actor, _annotation_scope_body(material))
            verify()
            payload = await run_in_threadpool(
                _create_annotation, request, service, actor, material, verify_request=verify_key,
            )
            await run_in_threadpool(verify_key)
            verify()
        except EvidenceWorkspaceError as exc:
            return _fail(exc)
        status = 200 if payload.get("idempotent_replay") else 201
        return JSONResponse(payload, status_code=status, headers=_NO_STORE_HEADERS)

    @app.post("/api/cases/evidence/annotations/adopt")
    async def adopt_evidence_annotation(request: Request):
        try:
            verify = _verify(request)
            verify()
            service, actor, material = _service(request), _actor(request), _material(request)
            verify_key = await run_in_threadpool(service.key_scope_verifier, actor, _annotation_scope_body(material))
            verify()
            payload = await run_in_threadpool(
                _adopt_annotation, request, service, actor, material, verify_request=verify_key,
            )
            await run_in_threadpool(verify_key)
            verify()
        except EvidenceWorkspaceError as exc:
            return _fail(exc)
        status = 200 if payload.get("idempotent_replay") else 201
        return JSONResponse(payload, status_code=status, headers=_NO_STORE_HEADERS)

    @app.get("/api/cases/evidence/annotations")
    async def list_evidence_annotations(request: Request):
        try:
            verify = _verify(request)
            verify()
            service, actor, material = _service(request), _actor(request), _material(request)
            verify_key = await run_in_threadpool(service.key_scope_verifier, actor, _annotation_scope_body(material))
            verify()
            payload = await run_in_threadpool(
                _list_annotations, request, service, actor, material, verify_request=verify_key,
            )
            await run_in_threadpool(verify_key)
            verify()
        except EvidenceWorkspaceError as exc:
            return _fail(exc)
        return JSONResponse(payload, status_code=200, headers=_NO_STORE_HEADERS)

    @app.post("/api/cases/evidence/classifications/offer")
    async def offer_evidence_classifiers(request: Request):
        try:
            verify = _verify(request)
            verify()
            service, actor, material = _service(request), _actor(request), _material(request)
            verify_key = await run_in_threadpool(service.key_scope_verifier, actor, _annotation_scope_body(material))
            verify()
            payload = await run_in_threadpool(
                _offer_classifiers, request, service, actor, material, verify_request=verify_key,
            )
            await run_in_threadpool(verify_key)
            verify()
        except EvidenceWorkspaceError as exc:
            return _fail(exc)
        return JSONResponse(payload, status_code=200, headers=_NO_STORE_HEADERS)

    @app.post("/api/cases/evidence/classifications")
    async def record_evidence_classifier(request: Request):
        try:
            verify = _verify(request)
            verify()
            service, actor, material = _service(request), _actor(request), _material(request)
            verify_key = await run_in_threadpool(service.key_scope_verifier, actor, _annotation_scope_body(material))
            verify()
            payload = await run_in_threadpool(
                _record_classifier, request, service, actor, material, verify_request=verify_key,
            )
            await run_in_threadpool(verify_key)
            verify()
        except EvidenceWorkspaceError as exc:
            return _fail(exc)
        status = 200 if payload.get("idempotent_replay") else 201
        return JSONResponse(payload, status_code=status, headers=_NO_STORE_HEADERS)

    @app.post("/api/cases/evidence/support-links/offer")
    async def offer_evidence_support_links(request: Request):
        try:
            verify = _verify(request)
            verify()
            service, actor, material = _service(request), _actor(request), _material(request)
            verify_key = await run_in_threadpool(service.key_scope_verifier, actor, _annotation_scope_body(material))
            verify()
            payload = await run_in_threadpool(
                _offer_support_links, request, service, actor, material, verify_request=verify_key,
            )
            await run_in_threadpool(verify_key)
            verify()
        except EvidenceWorkspaceError as exc:
            return _fail(exc)
        return JSONResponse(payload, status_code=200, headers=_NO_STORE_HEADERS)

    @app.post("/api/cases/evidence/support-links")
    async def record_evidence_support_link(request: Request):
        try:
            verify = _verify(request)
            verify()
            service, actor, material = _service(request), _actor(request), _material(request)
            verify_key = await run_in_threadpool(service.key_scope_verifier, actor, _annotation_scope_body(material))
            verify()
            payload = await run_in_threadpool(
                _record_support_link, request, service, actor, material, verify_request=verify_key,
            )
            await run_in_threadpool(verify_key)
            verify()
        except EvidenceWorkspaceError as exc:
            return _fail(exc)
        if payload.get("posture") == "unavailable" or payload.get("operation_succeeded") is False:
            status = 200
        else:
            status = 200 if payload.get("idempotent_replay") else 201
        return JSONResponse(payload, status_code=status, headers=_NO_STORE_HEADERS)

    @app.get("/api/cases/evidence/preview")
    async def preview_evidence(request: Request):
        try:
            verify = _verify(request)
            verify()
            service, actor, material = _service(request), _actor(request), _material(request)
            verify_key = await run_in_threadpool(service.key_scope_verifier, actor, material)
            verify()
            payload = await run_in_threadpool(
                _preview_evidence, service, actor, material, verify_request=verify_key,
            )
            await run_in_threadpool(verify_key)
            verify()
        except EvidenceWorkspaceError as exc:
            return _fail(exc)
        return JSONResponse(payload, status_code=200, headers=_NO_STORE_HEADERS)


def _bucket(service: EvidenceWorkspace) -> dict[str, dict[str, Any]]:
    return _UPLOADS.setdefault(id(service), {})


def _reject_ambient(body: Mapping[str, Any]) -> None:
    if not isinstance(body, Mapping):
        raise EvidenceWorkspaceError("request_body")
    if any(name in body for name in _REJECTED_FIELDS):
        raise EvidenceWorkspaceError("selector_rejected")


def _hex_digest(value: Any) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise EvidenceWorkspaceError("content_rejected")
    return value


def _declared_length(value: Any) -> int:
    if type(value) is not int or value < 1:
        raise EvidenceWorkspaceError("content_rejected")
    if value > _MAX_UPLOAD_BYTES:
        raise EvidenceWorkspaceError("oversized")
    return value


def _media_allowed(value: Any) -> str:
    if not isinstance(value, str) or value not in _ALLOWED_MEDIA:
        raise EvidenceWorkspaceError("media_rejected")
    return value


def _live_revision(request: Request, actor: str, body: Mapping[str, Any]) -> int:
    directory = getattr(request.app.state, "case_directory", None)
    expected = body.get("expected_revision")
    if type(expected) is not int:
        raise EvidenceWorkspaceError("revision_conflict")
    if directory is None:
        return expected
    try:
        case = directory.select_case(actor_principal_id=actor, case_id=str(body.get("case_id") or ""))
    except CaseDirectoryError as exc:
        raise EvidenceWorkspaceError("not_owner") from exc
    if case.tenant_id != body.get("tenant_id") or case.resource_id != body.get("resource_id"):
        raise EvidenceWorkspaceError("tenant_mismatch")
    if case.revision != expected:
        raise EvidenceWorkspaceError("revision_conflict")
    return case.revision


def _preflight(request: Request, actor: str, body: Mapping[str, Any]) -> int:
    _reject_ambient(body)
    revision = _live_revision(request, actor, body)
    service = getattr(request.app.state, "evidence_workspace", None)
    if not isinstance(service, EvidenceWorkspace):
        raise EvidenceWorkspaceError("evidence_unavailable")
    catalog = service.list_catalog(actor, body)
    if catalog.get("error"):
        raise EvidenceWorkspaceError(str(catalog["error"]))
    return revision


def _identity_key(actor: str, body: Mapping[str, Any]) -> str:
    idempotency = body.get("idempotency_key")
    if not isinstance(idempotency, str) or idempotency.strip() == "":
        raise EvidenceWorkspaceError("idempotency_key")
    return "\n".join((actor, str(body.get("tenant_id")), str(body.get("case_id")), idempotency))


def _wipe(session: dict[str, Any]) -> None:
    buffer = session.get("buffer")
    if isinstance(buffer, bytearray):
        for index in range(len(buffer)):
            buffer[index] = 0
        buffer.clear()
    session["buffer"] = bytearray()


def _view(session: dict[str, Any], *, record: Mapping[str, Any] | None = None, resumed: bool = False, replay: bool = False) -> dict[str, Any]:
    accepted = int(session.get("accepted") or 0)
    total = int(session.get("declared") or 0)
    state = str(session.get("state") or "")
    if state == "sealed":
        percent = 100
    elif total <= 0 or accepted <= 0:
        percent = 0
    else:
        percent = min(99, (accepted * 100) // total)
    sealed = record if record is not None else session.get("record")
    payload: dict[str, Any] = {
        "task_id": UPLOAD_TASK_ID,
        "upload_id": session.get("upload_id"),
        "upload_generation": session.get("generation"),
        "upload_state": state,
        "bytes_accepted": accepted if state != "sealed" else total,
        "byte_length": total,
        "progress_percent": percent,
        "progress_bounded": percent <= 100,
        "cancel_available": state == "accepting",
        "retry_available": state in {"sealed", "cancelled", "failed"},
        "ingestion_status": (sealed or {}).get("ingestion_status") or session.get("ingestion_status") or "",
        "operation_succeeded": state == "sealed",
        "legal": legal_qualities(),
        "receipt_establishes_legal_quality": False,
        "public_content_address": False,
        "resumed": resumed,
        "idempotent_replay": replay,
    }
    if isinstance(sealed, Mapping) and sealed.get("evidence_id"):
        payload["evidence_id"] = sealed["evidence_id"]
        payload["evidence"] = dict(sealed)
    return payload


def _session_for(request: Request, actor: str, body: Mapping[str, Any], *, upload_id: str) -> dict[str, Any]:
    service = getattr(request.app.state, "evidence_workspace", None)
    if not isinstance(service, EvidenceWorkspace):
        raise EvidenceWorkspaceError("evidence_unavailable")
    found = _bucket(service).get(upload_id)
    if found is None or found.get("actor") != actor:
        raise EvidenceWorkspaceError("upload_missing")
    if found.get("case_id") != body.get("case_id") or found.get("tenant_id") != body.get("tenant_id"):
        raise EvidenceWorkspaceError("tenant_mismatch")
    if found.get("resource_id") != body.get("resource_id"):
        raise EvidenceWorkspaceError("tenant_mismatch")
    generation = body.get("upload_generation")
    if type(generation) is not int or generation != found.get("generation"):
        raise EvidenceWorkspaceError("upload_stale")
    revision = _live_revision(request, actor, body)
    if revision != found.get("case_revision"):
        raise EvidenceWorkspaceError("upload_stale")
    return found


def _begin_upload(request: Request, actor: str, body: Mapping[str, Any], *, verify_request=None) -> dict[str, Any]:
    if verify_request is not None:
        verify_request()
    revision = _preflight(request, actor, body)
    service = request.app.state.evidence_workspace
    declared = _declared_length(body.get("byte_length"))
    digest = _hex_digest(body.get("content_sha256"))
    media = _media_allowed(body.get("media_type"))
    source = body.get("source_filename")
    original = body.get("original_filename")
    if not isinstance(source, str) or not isinstance(original, str):
        raise EvidenceWorkspaceError("source_filename")
    key = _identity_key(actor, body)
    bucket = _bucket(service)
    for existing in bucket.values():
        if existing.get("identity") == key and existing.get("state") == "sealed":
            if existing.get("content_sha256") != digest or existing.get("source_filename") != source:
                raise EvidenceWorkspaceError("replay_mismatch")
            return _view(existing, resumed=True, replay=True)
    upload_id = "up-" + os.urandom(16).hex()
    session = {
        "upload_id": upload_id,
        "generation": 1,
        "state": "accepting",
        "actor": actor,
        "tenant_id": body.get("tenant_id"),
        "case_id": body.get("case_id"),
        "resource_id": body.get("resource_id"),
        "case_revision": revision,
        "identity": key,
        "idempotency_key": body.get("idempotency_key"),
        "source_filename": source,
        "original_filename": original,
        "media_type": media,
        "declared": declared,
        "content_sha256": digest,
        "accepted": 0,
        "buffer": bytearray(),
        "ingestion_status": "",
        "record": None,
    }
    bucket[upload_id] = session
    return _view(session)


def _decode_chunk(encoded: Any) -> bytes:
    if not isinstance(encoded, str) or encoded == "":
        raise EvidenceWorkspaceError("content_rejected")
    try:
        payload = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError) as exc:
        raise EvidenceWorkspaceError("content_rejected") from exc
    if not payload or len(payload) > _MAX_CHUNK_BYTES:
        raise EvidenceWorkspaceError("oversized" if payload and len(payload) > _MAX_CHUNK_BYTES else "content_rejected")
    return payload


def _accept_chunk(request: Request, actor: str, body: Mapping[str, Any], *, verify_request=None) -> dict[str, Any]:
    if verify_request is not None:
        verify_request()
    _reject_ambient(body)
    upload_id = body.get("upload_id")
    if not isinstance(upload_id, str) or not upload_id.startswith("up-"):
        raise EvidenceWorkspaceError("upload_id")
    session = _session_for(request, actor, body, upload_id=upload_id)
    if session["state"] == "cancelled":
        raise EvidenceWorkspaceError("operation_revoked")
    if session["state"] != "accepting":
        raise EvidenceWorkspaceError("lifecycle_conflict")
    offset = body.get("offset")
    if type(offset) is not int or offset < 0:
        raise EvidenceWorkspaceError("upload_offset")
    chunk = _decode_chunk(body.get("content_base64"))
    accepted = int(session["accepted"])
    if offset == accepted - len(chunk) and bytes(session["buffer"][offset:offset + len(chunk)]) == chunk:
        return _view(session)
    if offset != accepted:
        raise EvidenceWorkspaceError("upload_offset")
    if accepted + len(chunk) > int(session["declared"]):
        _wipe(session)
        session["state"] = "failed"
        session["accepted"] = 0
        session["ingestion_status"] = "failed"
        raise EvidenceWorkspaceError("oversized")
    session["buffer"].extend(chunk)
    session["accepted"] = accepted + len(chunk)
    return _view(session)


def _complete_upload(request: Request, actor: str, body: Mapping[str, Any], *, verify_request=None) -> dict[str, Any]:
    if verify_request is not None:
        verify_request()
    _reject_ambient(body)
    upload_id = body.get("upload_id")
    if not isinstance(upload_id, str):
        raise EvidenceWorkspaceError("upload_id")
    session = _session_for(request, actor, body, upload_id=upload_id)
    if session["state"] == "sealed" and isinstance(session.get("record"), Mapping):
        return _view(session, replay=True)
    if session["state"] == "cancelled":
        raise EvidenceWorkspaceError("operation_revoked")
    if session["state"] != "accepting":
        raise EvidenceWorkspaceError("lifecycle_conflict")
    payload = bytes(session["buffer"])
    if len(payload) != int(session["declared"]) or hashlib.sha256(payload).hexdigest() != session["content_sha256"]:
        _wipe(session)
        session["state"] = "failed"
        session["accepted"] = 0
        session["ingestion_status"] = "failed"
        raise EvidenceWorkspaceError("content_rejected")
    service = request.app.state.evidence_workspace
    record = service.receive(actor, {
        "tenant_id": session["tenant_id"],
        "case_id": session["case_id"],
        "resource_id": session["resource_id"],
        "source_filename": session["source_filename"],
        "original_filename": session["original_filename"],
        "media_type": session["media_type"],
        "content_base64": base64.b64encode(payload).decode("ascii"),
        "idempotency_key": session["idempotency_key"],
    }, verify_request=verify_request)
    if verify_request is not None:
        verify_request()
    _wipe(session)
    session["state"] = "sealed"
    session["accepted"] = int(session["declared"])
    session["ingestion_status"] = record.get("ingestion_status") or "received"
    session["record"] = record
    return _view(session, record=record)


def _cancel_upload(request: Request, actor: str, body: Mapping[str, Any], *, verify_request=None) -> dict[str, Any]:
    if verify_request is not None:
        verify_request()
    _reject_ambient(body)
    upload_id = body.get("upload_id")
    if not isinstance(upload_id, str):
        raise EvidenceWorkspaceError("upload_id")
    session = _session_for(request, actor, body, upload_id=upload_id)
    if session["state"] == "sealed":
        raise EvidenceWorkspaceError("lifecycle_conflict")
    _wipe(session)
    session["state"] = "cancelled"
    session["accepted"] = 0
    session["ingestion_status"] = ""
    session["record"] = None
    view = _view(session)
    view["error"] = "operation_revoked"
    view["operation_succeeded"] = False
    return view


def _retry_upload(request: Request, actor: str, body: Mapping[str, Any], *, verify_request=None) -> dict[str, Any]:
    if verify_request is not None:
        verify_request()
    _reject_ambient(body)
    upload_id = body.get("upload_id")
    if not isinstance(upload_id, str):
        raise EvidenceWorkspaceError("upload_id")
    session = _session_for(request, actor, body, upload_id=upload_id)
    if session["state"] == "sealed":
        return _view(session, replay=True)
    if session["state"] not in {"cancelled", "failed"}:
        raise EvidenceWorkspaceError("lifecycle_conflict")
    revision = _live_revision(request, actor, body)
    _wipe(session)
    session["generation"] = int(session["generation"]) + 1
    session["state"] = "accepting"
    session["accepted"] = 0
    session["case_revision"] = revision
    session["ingestion_status"] = ""
    session["record"] = None
    return _view(session)


def _upload_status(request: Request, actor: str, body: Mapping[str, Any], *, verify_request=None) -> dict[str, Any]:
    if verify_request is not None:
        verify_request()
    _reject_ambient(body)
    upload_id = body.get("upload_id")
    if not isinstance(upload_id, str):
        raise EvidenceWorkspaceError("upload_id")
    # Query parameters arrive as text; mutation bodies retain their strict
    # integer contract. A converted selector still has to match the live
    # upload generation and canonical case revision below.
    material = dict(body)
    generation = material.get("upload_generation")
    if (isinstance(generation, str) and 0 < len(generation) <= 20
            and generation.isascii() and generation.isdecimal()):
        material["upload_generation"] = int(generation)
    return _view(_session_for(request, actor, material, upload_id=upload_id))


def _preview_evidence(service: EvidenceWorkspace, actor: str, body: Mapping[str, Any], *, verify_request=None) -> dict[str, Any]:
    """Decrypt one artifact version and describe a safe preview.

    The decrypted buffer lives only in this call. Callers receive plain text
    or a still-image encoding, never an HTML document and never a model request.
    """

    if verify_request is not None:
        verify_request()
    if any(name in body for name in _PREVIEW_REFUSED):
        raise EvidenceWorkspaceError("selector_rejected")
    evidence_id = body.get("evidence_id")
    if not isinstance(evidence_id, str) or evidence_id.strip() == "":
        raise EvidenceWorkspaceError("evidence_id")
    requested = _preview_version(body.get("version"))
    identity = service._identity(actor, body, content=False, idempotency=False)
    with service._lock:
        scope = service._open(identity, verify_request=verify_request)
        case, key_id, data_key = scope.case, scope.key_id, scope.data_key
        document = service._load(identity, case, key_id, data_key, scope)
        item = document["items"].get(evidence_id)
        if item is None or item.get("actor_principal_id") != identity["actor_principal_id"]:
            raise EvidenceWorkspaceError("missing_evidence")
        if item.get("case_id") != case.case_id or item.get("tenant_id") != case.tenant_id:
            raise EvidenceWorkspaceError("tenant_mismatch")
        version = _selected_version(item, requested)
        try:
            opened = retrieve_private_artifact(
                version["ciphertext_cid"],
                access=_artifact_access(service, case),
                tenant_id=case.tenant_id,
                case_id=case.case_id,
                artifact_kind="evidence-artifact",
                revision=f"{evidence_id}-v{version['version']}",
                principal_id=case.tenant_id,
                key=data_key,
                key_id=key_id,
                backend=service._backend,
                backend_name=service._backend_name,
            )
        except PrivateStorageError as exc:
            raise EvidenceWorkspaceError("ciphertext_unavailable") from exc
        service._verify_scope(scope)
    payload = opened.get("data")
    if not isinstance(payload, (bytes, bytearray)):
        raise EvidenceWorkspaceError("ciphertext_unavailable")
    content = bytes(payload)
    if hashlib.sha256(content).hexdigest() != version["integrity_sha256"]:
        raise EvidenceWorkspaceError("ciphertext_unavailable")
    preview = _safe_preview(content, str(item.get("media_type") or "application/octet-stream"))
    preview.update({
        "task_id": PREVIEW_TASK_ID,
        "evidence_id": evidence_id,
        "tenant_id": case.tenant_id,
        "case_id": case.case_id,
        "resource_id": item.get("resource_id") or identity["resource_id"],
        "actor_principal_id": identity["actor_principal_id"],
        "version": version["version"],
        "media_type": item.get("media_type") or "",
        "integrity_sha256": version["integrity_sha256"],
        "byte_length": len(content),
        "model_invoked": False,
        "model_input_sent": False,
        "active_content_executed": False,
        "external_fetch": False,
        "plaintext_cached": False,
        "cache_scope": "\n".join((
            case.tenant_id, case.case_id, identity["actor_principal_id"],
            evidence_id, str(version["version"]), version["integrity_sha256"],
        )),
        "legal": legal_qualities(),
        "receipt_establishes_legal_quality": False,
    })
    del content
    return preview


def _artifact_access(service: EvidenceWorkspace, case: Any):
    access_type = service._observe.__func__.__globals__["_Access"]
    return access_type(trust="authenticated", principal_id=case.tenant_id, case_id=case.case_id)


def _preview_version(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, str) and value.isascii() and value.isdecimal() and 0 < len(value) <= 9:
        value = int(value)
    if type(value) is not int or isinstance(value, bool) or value < 1:
        raise EvidenceWorkspaceError("evidence_id")
    return value


def _selected_version(item: Mapping[str, Any], requested: int | None) -> Mapping[str, Any]:
    versions = list(item.get("artifact_versions") or [])
    if requested is None:
        if not versions:
            raise EvidenceWorkspaceError("missing_evidence")
        return versions[-1]
    for version in versions:
        if version.get("version") == requested and isinstance(version.get("ciphertext_cid"), str):
            return version
    raise EvidenceWorkspaceError("missing_evidence")


def _safe_preview(content: bytes, media: str) -> dict[str, Any]:
    active = _declares_active_content(content)
    if media in _PREVIEW_TEXT:
        return _text_preview(content, active)
    if media == "application/pdf":
        pages = _pdf_pages(content)
        if pages is None:
            return _alternative(content, media, "content_not_renderable", active)
        return _page_preview(pages, "pdf", active)
    if media in _PREVIEW_IMAGES:
        image = _still_image(content, media)
        if image is None:
            return _alternative(content, media, "content_not_renderable", active)
        return {
            "supported": True,
            "preview_kind": "image",
            "active_content_present": active,
            "pages": [{
                "page": 1,
                "anchor": "page-1",
                "spans": [{
                    "span": 1,
                    "anchor": "page-1-span-1",
                    "text": image["accessible_text"],
                }],
            }],
            "accessible_text": image["accessible_text"],
            "image": image,
            "alternative": None,
        }
    return _alternative(content, media, "unsupported_format", active)


def _text_preview(content: bytes, active: bool) -> dict[str, Any]:
    text = content.decode("utf-8", errors="replace").replace("\x00", "")
    lines = text.splitlines() or [""]
    pages = []
    spans = []
    for index, line in enumerate(lines, start=1):
        page_number = ((index - 1) // 40) + 1
        span_number = index - ((page_number - 1) * 40)
        spans.append({
            "page": page_number,
            "span": span_number,
            "anchor": f"page-{page_number}-span-{span_number}",
            "text": line[:4000],
        })
    grouped: dict[int, list[dict[str, Any]]] = {}
    for span in spans:
        grouped.setdefault(span["page"], []).append({key: span[key] for key in ("span", "anchor", "text")})
    for page_number, page_spans in grouped.items():
        pages.append({"page": page_number, "anchor": f"page-{page_number}", "spans": page_spans})
    accessible = "\n".join(span["text"] for span in spans)
    return {
        "supported": True,
        "preview_kind": "text",
        "active_content_present": active,
        "pages": pages,
        "accessible_text": accessible[:20000],
        "image": None,
        "alternative": None,
    }


def _page_preview(pages: list[list[str]], kind: str, active: bool) -> dict[str, Any]:
    rendered = []
    pieces = []
    for page_number, lines in enumerate(pages, start=1):
        spans = []
        usable = lines or ["No extractable text on this page."]
        for span_number, line in enumerate(usable, start=1):
            text = line[:4000]
            spans.append({
                "span": span_number,
                "anchor": f"page-{page_number}-span-{span_number}",
                "text": text,
            })
            pieces.append(text)
        rendered.append({"page": page_number, "anchor": f"page-{page_number}", "spans": spans})
    return {
        "supported": True,
        "preview_kind": kind,
        "active_content_present": active,
        "pages": rendered,
        "accessible_text": "\n".join(pieces)[:20000],
        "image": None,
        "alternative": None,
    }


def _alternative(content: bytes, media: str, reason: str, active: bool) -> dict[str, Any]:
    excerpt = _safe_excerpt(content)
    message = (
        "This format cannot be previewed safely inside the workspace. "
        "The file stays encrypted in the case. No script, remote address, or model request was used."
    )
    return {
        "supported": False,
        "preview_kind": "unsupported",
        "active_content_present": active,
        "pages": [],
        "accessible_text": excerpt,
        "image": None,
        "alternative": {
            "reason": reason,
            "message": message,
            "media_type": media,
            "byte_length": len(content),
            "safe_text": excerpt,
        },
    }


def _safe_excerpt(content: bytes) -> str:
    text = content.decode("utf-8", errors="replace")
    cleaned = "".join(char if char.isprintable() or char in "\n\t" else " " for char in text).strip()
    if sum(char.isalnum() for char in cleaned) < 4:
        return ""
    return cleaned[:800]


def _declares_active_content(content: bytes) -> bool:
    sample = content[:8000].lower()
    markers = (b"<script", b"javascript:", b"/javascript", b"/js", b"/launch", b"/submitform", b"<iframe", b"<html")
    return any(marker in sample for marker in markers)


def _pdf_pages(content: bytes) -> list[list[str]] | None:
    if not content.startswith(b"%PDF-"):
        return None
    page_count = len(re.findall(br"/Type\s*/Page(?!s)", content))
    streams = _pdf_streams(content)
    text_pages = [lines for lines in (_pdf_text_lines(stream) for stream in streams) if lines]
    if page_count <= 0 and not text_pages:
        return None
    count = page_count or len(text_pages)
    pages: list[list[str]] = []
    for index in range(count):
        pages.append(text_pages[index] if index < len(text_pages) else [])
    if len(text_pages) > count:
        pages[-1].extend(line for extra in text_pages[count:] for line in extra)
    return pages


def _pdf_streams(content: bytes) -> list[bytes]:
    streams = []
    for match in re.finditer(br"<<(.*?)>>\s*stream\r?\n", content, re.S):
        header = match.group(1)
        start = match.end()
        end = content.find(b"endstream", start)
        if end < 0:
            continue
        raw = content[start:end]
        if raw.endswith(b"\r\n"):
            raw = raw[:-2]
        elif raw.endswith(b"\n"):
            raw = raw[:-1]
        if b"FlateDecode" in header:
            try:
                raw = zlib.decompress(raw)
            except zlib.error:
                continue
        streams.append(raw)
    return streams


def _pdf_text_lines(stream: bytes) -> list[str]:
    lines = []
    for match in re.finditer(br"\[(.*?)\]\s*TJ", stream, re.S):
        lines.extend(_pdf_strings(match.group(1)))
    for match in re.finditer(br"(\((?:\\.|[^\\)])*\))\s*(?:Tj|'|\")", stream, re.S):
        lines.extend(_pdf_strings(match.group(1)))
    return [line for line in lines if line.strip()]


def _pdf_strings(blob: bytes) -> list[str]:
    found = []
    for match in re.finditer(br"\(((?:\\.|[^\\)])*)\)", blob, re.S):
        found.append(_pdf_unescape(match.group(1)))
    return found


def _pdf_unescape(raw: bytes) -> str:
    out = bytearray()
    index = 0
    while index < len(raw):
        if raw[index] != 0x5C or index + 1 >= len(raw):
            out.append(raw[index])
            index += 1
            continue
        nxt = raw[index + 1]
        mapped = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12, ord("("): 40, ord(")"): 41, ord("\\"): 92}
        if nxt in mapped:
            out.append(mapped[nxt])
            index += 2
            continue
        if nxt in b"01234567":
            digits = bytes([nxt])
            index += 2
            while index < len(raw) and raw[index] in b"01234567" and len(digits) < 3:
                digits += bytes([raw[index]])
                index += 1
            out.append(int(digits, 8) & 0xFF)
            continue
        out.append(nxt)
        index += 2
    return out.decode("utf-8", errors="replace")


def _still_image(content: bytes, media: str) -> dict[str, Any] | None:
    size = _image_size(content, media)
    if size is None:
        return None
    width, height = size
    if width < 1 or height < 1 or width > 20000 or height > 20000:
        return None
    accessible = f"Image preview, {width} by {height} pixels. No text was extracted from this image."
    return {
        "media_type": media,
        "byte_length": len(content),
        "width": width,
        "height": height,
        "content_base64": base64.b64encode(content).decode("ascii"),
        "accessible_text": accessible,
    }


def _image_size(content: bytes, media: str) -> tuple[int, int] | None:
    if media == "image/png":
        if not content.startswith(b"\x89PNG\r\n\x1a\n") or content[12:16] != b"IHDR" or len(content) < 24:
            return None
        return struct.unpack(">II", content[16:24])
    if media == "image/jpeg":
        return _jpeg_size(content)
    if media == "image/webp":
        return _webp_size(content)
    return None


def _jpeg_size(content: bytes) -> tuple[int, int] | None:
    if not content.startswith(b"\xff\xd8"):
        return None
    index = 2
    while index + 8 < len(content):
        if content[index] != 0xFF:
            return None
        while index < len(content) and content[index] == 0xFF:
            index += 1
        if index >= len(content):
            return None
        marker = content[index]
        index += 1
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(content):
            return None
        if marker in {0xC0, 0xC1, 0xC2}:
            height, width = struct.unpack(">HH", content[index + 3:index + 7])
            return width, height
        length = struct.unpack(">H", content[index:index + 2])[0]
        if length < 2:
            return None
        index += length
    return None


def _webp_size(content: bytes) -> tuple[int, int] | None:
    if len(content) < 30 or content[:4] != b"RIFF" or content[8:12] != b"WEBP":
        return None
    kind = content[12:16]
    if kind == b"VP8X" and len(content) >= 30:
        width = 1 + int.from_bytes(content[24:27], "little")
        height = 1 + int.from_bytes(content[27:30], "little")
        return width, height
    if kind == b"VP8 " and content[23:26] == b"\x9d\x01\x2a":
        width = int.from_bytes(content[26:28], "little") & 0x3FFF
        height = int.from_bytes(content[28:30], "little") & 0x3FFF
        return width, height
    if kind == b"VP8L" and len(content) >= 25 and content[20] == 0x2F:
        bits = int.from_bytes(content[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    return None


_ANNOTATION_DOCUMENT_FIELDS = frozenset({
    "content_base64",
    "source_filename",
    "original_filename",
    "media_type",
    "extracted_content_base64",
})
_ANNOTATION_AUTHORITY_FIELDS = frozenset({
    "key",
    "passphrase",
    "role",
    "roles",
    "trusted_local",
    "cid",
    "admin_key",
})


def _annotation_scope_body(body: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(body, Mapping):
        raise EvidenceWorkspaceError("request_body")
    return {
        "tenant_id": body.get("tenant_id"),
        "case_id": body.get("case_id"),
        "resource_id": body.get("resource_id"),
    }


def _annotation_store(request: Request, service: EvidenceWorkspace) -> EvidenceAnnotationStore:
    root = getattr(service, "_root", None)
    if root is None:
        raise EvidenceWorkspaceError("evidence_unavailable")
    path = Path(root) / "annotations"
    current = getattr(request.app.state, "evidence_annotation_store", None)
    if isinstance(current, EvidenceAnnotationStore) and Path(getattr(current, "_root")) == path:
        return current
    store = EvidenceAnnotationStore(path)
    request.app.state.evidence_annotation_store = store
    return store


def _annotation_case(service: EvidenceWorkspace, actor: str, body: Mapping[str, Any]):
    identity = service._identity(actor, _annotation_scope_body(body), content=False, idempotency=False)
    return service._open(identity)


def _case_revision(body: Mapping[str, Any], case: Any) -> None:
    expected = body.get("expected_case_revision")
    if isinstance(expected, str) and expected.strip().lstrip("-").isdigit():
        expected = int(expected.strip())
    if type(expected) is not int or isinstance(expected, bool) or expected != case.revision:
        raise EvidenceWorkspaceError("revision_conflict")


def _artifact_version_value(body: Mapping[str, Any]) -> int:
    value = body.get("artifact_version")
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if type(value) is not int or isinstance(value, bool):
        raise EvidenceWorkspaceError("artifact_version")
    return value


def _bound_evidence(service: EvidenceWorkspace, actor: str, body: Mapping[str, Any], verify_request):
    if verify_request is not None:
        verify_request()
    if not isinstance(body, Mapping):
        raise EvidenceWorkspaceError("request_body")
    if any(name in body for name in _ANNOTATION_AUTHORITY_FIELDS):
        raise EvidenceWorkspaceError("selector_rejected")
    if any(name in body for name in _ANNOTATION_DOCUMENT_FIELDS):
        raise EvidenceWorkspaceError("content_rejected")
    claimed_actor = body.get("actor_principal_id")
    if claimed_actor is not None and claimed_actor != actor:
        raise EvidenceWorkspaceError("actor")
    scope = _annotation_case(service, actor, body)
    _case_revision(body, scope.case)
    claimed_owner = body.get("canonical_owner_principal_id")
    if claimed_owner is not None and claimed_owner != scope.case.tenant_id:
        raise EvidenceWorkspaceError("selector_rejected")
    evidence_id = body.get("evidence_id")
    if not isinstance(evidence_id, str) or evidence_id.strip() == "" or evidence_id != evidence_id.strip():
        raise EvidenceWorkspaceError("evidence_id")
    version = _artifact_version_value(body)
    catalog = service.list_catalog(actor, _annotation_scope_body(body), verify_request=verify_request)
    items = list(catalog.get("items") or [])
    item = next((entry for entry in items if entry.get("evidence_id") == evidence_id), None)
    if item is None:
        raise EvidenceWorkspaceError("missing_evidence")
    known = {entry.get("version") for entry in item.get("artifact_versions") or []}
    if version not in known:
        raise EvidenceWorkspaceError("artifact_version_mismatch")
    if verify_request is not None:
        verify_request()
    return scope, evidence_id, version, [entry.get("evidence_id") for entry in items]


def _store_call(operation):
    try:
        return operation()
    except BoundPrivateRecordError as exc:
        raise EvidenceWorkspaceError(exc.code) from exc


def _create_annotation(request: Request, service: EvidenceWorkspace, actor: str, body: Mapping[str, Any], *, verify_request=None) -> dict[str, Any]:
    if body.get("adopted") is True or body.get("adopt") is True:
        raise EvidenceWorkspaceError("adoption_requires_explicit_action")
    scope, evidence_id, version, evidence_ids = _bound_evidence(service, actor, body, verify_request)
    idempotency = body.get("idempotency_key")
    expected = body.get("expected_annotation_revision")
    if not isinstance(idempotency, str) or idempotency.strip() == "":
        raise EvidenceWorkspaceError("idempotency_key")
    if not isinstance(expected, str):
        raise EvidenceWorkspaceError("revision_conflict")
    kind = body.get("kind")
    if not isinstance(kind, str):
        raise EvidenceWorkspaceError("kind")
    store = _annotation_store(request, service)
    payload = _store_call(lambda: store.commit_attributed_annotation(
        evidence_id=evidence_id,
        artifact_version=version,
        kind=kind,
        actor_principal_id=actor,
        canonical_owner_principal_id=scope.case.tenant_id,
        tenant_id=scope.case.tenant_id,
        case_id=scope.case.case_id,
        idempotency_key=idempotency,
        expected_annotation_revision=expected,
        key=scope.data_key,
        key_id=scope.key_id,
        note=body.get("note") if isinstance(body.get("note"), str) else "",
        label=body.get("label") if isinstance(body.get("label"), str) else "",
        page=body.get("page") if kind == "page_span" else None,
        span_start=body.get("span_start") if kind == "page_span" else None,
        span_end=body.get("span_end") if kind == "page_span" else None,
        claim_element=body.get("claim_element") if "claim_element" in body else None,
        display_role=body.get("display_role") if isinstance(body.get("display_role"), str) else None,
    ))
    after = service.list_catalog(actor, _annotation_scope_body(body), verify_request=verify_request)
    after_ids = [entry.get("evidence_id") for entry in after.get("items") or []]
    payload["evidence_ids"] = after_ids
    payload["synthesized_evidence"] = after_ids != evidence_ids
    payload["task_id"] = ANNOTATION_TASK_ID
    payload["display_role_authoritative"] = False
    return payload


def _adopt_annotation(request: Request, service: EvidenceWorkspace, actor: str, body: Mapping[str, Any], *, verify_request=None) -> dict[str, Any]:
    scope, evidence_id, version, evidence_ids = _bound_evidence(service, actor, body, verify_request)
    annotation_id = body.get("annotation_id")
    idempotency = body.get("idempotency_key")
    expected = body.get("expected_annotation_revision")
    if not isinstance(annotation_id, str) or not isinstance(idempotency, str) or not isinstance(expected, str):
        raise EvidenceWorkspaceError("annotation_rejected")
    store = _annotation_store(request, service)
    payload = _store_call(lambda: store.adopt_annotation(
        evidence_id=evidence_id,
        artifact_version=version,
        annotation_id=annotation_id,
        actor_principal_id=actor,
        canonical_owner_principal_id=scope.case.tenant_id,
        tenant_id=scope.case.tenant_id,
        case_id=scope.case.case_id,
        idempotency_key=idempotency,
        expected_annotation_revision=expected,
        key=scope.data_key,
        key_id=scope.key_id,
        adopt=body.get("adopt") is True,
        display_role=body.get("display_role") if isinstance(body.get("display_role"), str) else None,
    ))
    after = service.list_catalog(actor, _annotation_scope_body(body), verify_request=verify_request)
    after_ids = [entry.get("evidence_id") for entry in after.get("items") or []]
    payload["evidence_ids"] = after_ids
    payload["synthesized_evidence"] = after_ids != evidence_ids
    payload["adopted_as_evidence"] = False
    payload["task_id"] = ANNOTATION_TASK_ID
    return payload


def _classification_body(body: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(body, Mapping):
        raise EvidenceWorkspaceError("request_body")
    material = dict(body)
    version = material.get("artifact_version")
    if isinstance(version, str) and version.strip().isdigit():
        material["artifact_version"] = int(version.strip())
    context = material.get("case_context")
    if context is None:
        material["case_context"] = {"legal_context_status": "unknown", "context_owner": "request"}
    elif isinstance(context, Mapping):
        copied = dict(context)
        copied.setdefault("context_owner", "request")
        material["case_context"] = copied
    else:
        raise EvidenceWorkspaceError("classifier_rejected")
    material["task_id"] = CLASSIFICATION_TASK_ID
    return material


def _offer_classifiers(request: Request, service: EvidenceWorkspace, actor: str, body: Mapping[str, Any], *, verify_request=None) -> dict[str, Any]:
    material = _classification_body(body)
    payload = service.offer_classifiers(actor, material, verify_request=verify_request)
    payload["annotation_user_labels"] = _annotation_user_labels(request, service, actor, material, verify_request)
    payload["fixed_assumptions_offered"] = False
    payload["establishes_legal_support"] = False
    return payload


def _support_body(body: Mapping[str, Any]) -> dict[str, Any]:
    material = _classification_body(body)
    for name in ("page", "span_start", "span_end"):
        value = material.get(name)
        if isinstance(value, str) and value.strip().isdigit():
            material[name] = int(value.strip())
    material["task_id"] = SUPPORT_LINK_TASK_ID
    if material.get("client_checkbox") is True or material.get("verified_legal_support") is True:
        material["client_checkbox"] = True
    return material


def _offer_support_links(request: Request, service: EvidenceWorkspace, actor: str, body: Mapping[str, Any], *, verify_request=None) -> dict[str, Any]:
    del request
    payload = service.offer_support_links(actor, _support_body(body), verify_request=verify_request)
    payload["client_checkbox_mints_support"] = False
    payload["classifier_mints_support"] = False
    payload["establishes_legal_support"] = False
    return payload


def _record_support_link(request: Request, service: EvidenceWorkspace, actor: str, body: Mapping[str, Any], *, verify_request=None) -> dict[str, Any]:
    del request
    payload = service.record_support_link(actor, _support_body(body), verify_request=verify_request)
    payload["client_checkbox_mints_support"] = False
    payload["classifier_mints_support"] = False
    payload["establishes_legal_support"] = False
    payload["verified_legal_support"] = False
    return payload


def _record_classifier(request: Request, service: EvidenceWorkspace, actor: str, body: Mapping[str, Any], *, verify_request=None) -> dict[str, Any]:
    material = _classification_body(body)
    payload = service.record_classifier(actor, material, verify_request=verify_request)
    payload["annotation_user_labels"] = _annotation_user_labels(request, service, actor, material, verify_request)
    payload["fixed_assumptions_offered"] = False
    payload["establishes_legal_support"] = False
    return payload


def _annotation_user_labels(request: Request, service: EvidenceWorkspace, actor: str, body: Mapping[str, Any], verify_request) -> list[dict[str, Any]]:
    """Surface saved annotation labels beside classifiers. A label is not acceptance."""

    try:
        listed = _list_annotations(request, service, actor, body, verify_request=verify_request)
    except EvidenceWorkspaceError:
        return []
    labels = []
    for item in listed.get("items") or []:
        if not isinstance(item, Mapping) or item.get("kind") != "label":
            continue
        labels.append({
            "origin": "user_label",
            "record_type": "annotation_label",
            "annotation_id": item.get("annotation_id") or "",
            "label": item.get("label") or "",
            "actor_principal_id": item.get("actor_principal_id") or "",
            "artifact_version": item.get("artifact_version"),
            "reviewed": False,
            "accepted": False,
            "establishes_legal_support": False,
            "legal_requirement": False,
        })
    return labels


def _list_annotations(request: Request, service: EvidenceWorkspace, actor: str, body: Mapping[str, Any], *, verify_request=None) -> dict[str, Any]:
    scope, evidence_id, version, evidence_ids = _bound_evidence(service, actor, body, verify_request)
    store = _annotation_store(request, service)
    payload = _store_call(lambda: store.list_attributed_annotations(
        evidence_id=evidence_id,
        artifact_version=version,
        canonical_owner_principal_id=scope.case.tenant_id,
        tenant_id=scope.case.tenant_id,
        case_id=scope.case.case_id,
        key=scope.data_key,
    ))
    payload["evidence_ids"] = evidence_ids
    payload["display_role_authoritative"] = False
    return payload
