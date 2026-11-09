"""Case ciphertext durability through Kit manifest, queue, pin, and readback.

The browser session supplies the actor. A body cannot mint authority, choose a
public gateway, or declare durability from a CID. Plaintext is sealed before
the Kit owner sees it. The response lists local commit, queued replication,
pin, and verified replica as separate states and sets durable only after
ciphertext readback matches.

Failure recovery keeps every acknowledged state. A missing key, an offline or
unavailable backend, and corrupt or truncated ciphertext stay unresolved.
Storage readiness does not set interview or legal readiness. Public receipts
and logs omit keys, passphrases, and plaintext.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import Any, Mapping

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from applications.browser_sessions import BrowserSessionError, BrowserSessionService, SESSION_COOKIE
from applications.case_directory import CaseDirectory, CaseDirectoryError

from integrations.private_storage import (
    DURABILITY_STATE_LOCAL_COMMIT,
    DURABILITY_STATE_PIN,
    DURABILITY_STATE_QUEUED_REPLICATION,
    DURABILITY_STATE_VERIFIED_REPLICA,
    DURABILITY_STATES,
    ENVELOPE_MAGIC,
    CiphertextDurabilityError,
    PrivateArtifactBinding,
    UserOwnedKeySession,
    _kit_call,
    _kit_replica_contract,
    _opaque_ref,
    seal_private_artifact,
)

TASK_ID = "CIMP-GUI-38"
RECOVERY_TASK_ID = "CIMP-GUI-39"
_KIND = "case-ciphertext"
_LOG = logging.getLogger("applications.case_storage_api")
_SECRET_FIELDS = frozenset({
    "key",
    "data_key",
    "passphrase",
    "secret",
    "content_base64",
    "ciphertext",
    "browser_key",
    "wrapped_key",
    "master_key",
    "private_key",
    "encryption_key",
    "password",
})
_NO_STORE_HEADERS = {
    "Cache-Control": "no-store, max-age=0, private",
    "Pragma": "no-cache",
    "Expires": "0",
}
_REJECTED_FIELDS = frozenset({
    "cid",
    "content_cid",
    "url",
    "uri",
    "gateway",
    "public_gateway",
    "infer_from_cid",
    "durable",
    "role",
    "trusted_local",
    "browser_key",
    "key",
    "data_key",
    "passphrase",
    "secret",
    "private_key",
    "encryption_key",
    "master_key",
    "interview_ready",
    "interview_readiness",
    "legal_ready",
    "legal_readiness",
    "storage_ready",
    "storage_readiness",
})


class CaseStorageError(Exception):
    def __init__(self, code: str, receipt: Mapping[str, Any] | None = None) -> None:
        self.code = code
        self.receipt = dict(receipt) if isinstance(receipt, Mapping) else None
        super().__init__(code)


def _label(value: Any, code: str) -> str:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise CaseStorageError(code)
    if any(char in value for char in ("\x00", "\n", "\r", "/", "\\")):
        raise CaseStorageError(code)
    if len(value) > 200:
        raise CaseStorageError(code)
    return value


def case_storage_status(code: str) -> int:
    if code in {"unauthenticated"}:
        return 401
    if code in {"not_owner", "missing_case", "key_unavailable"}:
        return 403
    if code in {"readback_mismatch", "ciphertext_corrupt", "ciphertext_truncated", "public_gateway_rejected", "resource_mismatch", "tenant_mismatch", "replay_mismatch"}:
        return 409
    if code.startswith("kit_") or code in {"kit_contracts_unavailable", "storage_unavailable", "backend_unavailable"}:
        return 503
    return 400


def _strip_secrets(value: Any) -> Any:
    """Drop key material before a receipt is stored, returned, or logged."""

    if isinstance(value, Mapping):
        cleaned: dict[str, Any] = {}
        for name, item in value.items():
            if not isinstance(name, str) or name in _SECRET_FIELDS:
                continue
            cleaned[name] = _strip_secrets(item)
        return cleaned
    if isinstance(value, (bytes, bytearray)):
        return None
    if isinstance(value, tuple):
        return tuple(_strip_secrets(item) for item in value)
    if isinstance(value, list):
        return [_strip_secrets(item) for item in value]
    return value


def _log_receipt(receipt: Mapping[str, Any]) -> None:
    public = _strip_secrets(receipt)
    _LOG.info(
        "case_storage_recovery task=%s case_id=%s durable=%s unresolved=%s failure_kind=%s replica_status=%s states=%s",
        public.get("recovery_task_id"),
        public.get("case_id"),
        public.get("durable"),
        public.get("unresolved"),
        public.get("failure_kind"),
        public.get("replica_status"),
        public.get("state_names"),
    )


def _failure_kind(code: str) -> str:
    if code in {"", "none"}:
        return "none"
    if code in {"key_unavailable"}:
        return "key"
    if code.startswith("kit_") or code in {"kit_contracts_unavailable", "storage_unavailable", "backend_unavailable"}:
        return "backend"
    return "storage"


def _readiness(code: str, *, durable: bool) -> str:
    if durable:
        return "ready"
    if _failure_kind(code) == "backend" or code == "storage_unavailable":
        return "unavailable"
    return "unresolved"


def _condition(payload: bytes, loaded: Any) -> str:
    if isinstance(loaded, (bytes, bytearray)) and bytes(loaded) == payload:
        return "matched"
    if isinstance(loaded, (bytes, bytearray)):
        blob = bytes(loaded)
        if blob and len(blob) < len(payload) and payload.startswith(blob):
            return "truncated"
        if not blob.startswith(ENVELOPE_MAGIC):
            return "corrupt"
    elif loaded is not None:
        return "corrupt"
    return "mismatch"


def observe_ciphertext_durability(kit: Any, envelope: bytes) -> dict[str, Any]:
    """Observe Kit states and keep partial acknowledgements when a step fails.

    ``durable`` stays false until readback matches. Queued replication remains
    a pending replica. Corrupt, truncated, offline, and unavailable results
    stay unresolved instead of discarding earlier states.
    """

    if not isinstance(envelope, (bytes, bytearray)) or not bytes(envelope).startswith(ENVELOPE_MAGIC):
        raise CiphertextDurabilityError("ciphertext_required")
    payload = bytes(envelope)
    states: list[dict[str, Any]] = []
    ref = ""

    def record(state: str, *, kit_state: str) -> None:
        if state not in DURABILITY_STATES or any(item["state"] == state for item in states):
            raise CiphertextDurabilityError("durability_state_collision")
        states.append({
            "state": state,
            "ref": ref,
            "kit_replica_state": kit_state,
            "durable": False,
            "counts_as_verified_replica": False,
        })

    def unfinished(code: str, *, condition: str = "unavailable", loaded: Any = None) -> dict[str, Any]:
        names = [item["state"] for item in states]
        pending = DURABILITY_STATE_QUEUED_REPLICATION in names and DURABILITY_STATE_VERIFIED_REPLICA not in names
        observed_condition = condition
        if code == "readback_mismatch":
            observed_condition = _condition(payload, loaded)
        return {
            "states": states,
            "state_names": names,
            "durable": False,
            "readback_matched": False,
            "ciphertext_sha256": hashlib.sha256(payload).hexdigest(),
            "byte_length": len(payload),
            "ref": ref,
            "public_gateway_consulted": False,
            "cid_inference": False,
            "pin_is_durable": False,
            "queued_replication_is_durable": False,
            "local_commit_is_durable": False,
            "code": "readback_mismatch" if observed_condition in {"corrupt", "truncated", "mismatch"} else code,
            "ciphertext_condition": observed_condition,
            "unresolved": True,
            "pending_replica": pending,
            "replica_status": "pending" if pending else "unresolved",
            "acknowledged_work_retained": bool(names),
        }

    try:
        replica_state = _kit_replica_contract()
    except CiphertextDurabilityError as exc:
        return unfinished(exc.code)

    try:
        manifest = _kit_call(kit, "manifest", payload)
    except CiphertextDurabilityError as exc:
        if exc.code == "public_gateway_rejected":
            raise
        return unfinished(exc.code)
    if not isinstance(manifest, Mapping):
        return unfinished("kit_manifest_failed")
    try:
        ref = _opaque_ref(manifest)
    except CiphertextDurabilityError as exc:
        if exc.code == "public_gateway_rejected":
            raise
        return unfinished(exc.code)
    record(DURABILITY_STATE_LOCAL_COMMIT, kit_state="local_commit")

    try:
        queued = _kit_call(kit, "queue_replication", ref)
    except CiphertextDurabilityError as exc:
        return unfinished(exc.code)
    if not isinstance(queued, Mapping):
        return unfinished("kit_queue_replication_failed")
    record(DURABILITY_STATE_QUEUED_REPLICATION, kit_state=replica_state.QUEUED.value)

    try:
        pinned = _kit_call(kit, "pin", ref)
    except CiphertextDurabilityError as exc:
        return unfinished(exc.code)
    if not isinstance(pinned, Mapping) or pinned.get("pinned") is not True:
        return unfinished("kit_pin_failed")
    record(DURABILITY_STATE_PIN, kit_state="pin")

    try:
        loaded = _kit_call(kit, "readback", ref)
    except CiphertextDurabilityError as exc:
        return unfinished(exc.code)
    if isinstance(loaded, (bytes, bytearray)) and bytes(loaded) == payload:
        record(DURABILITY_STATE_VERIFIED_REPLICA, kit_state=replica_state.VERIFIED.value)
        states[-1]["counts_as_verified_replica"] = True
        states[-1]["durable"] = True
        names = [item["state"] for item in states]
        return {
            "states": states,
            "state_names": names,
            "durable": True,
            "readback_matched": True,
            "ciphertext_sha256": hashlib.sha256(payload).hexdigest(),
            "byte_length": len(payload),
            "ref": ref,
            "public_gateway_consulted": False,
            "cid_inference": False,
            "pin_is_durable": False,
            "queued_replication_is_durable": False,
            "local_commit_is_durable": False,
            "code": "",
            "ciphertext_condition": "matched",
            "unresolved": False,
            "pending_replica": False,
            "replica_status": "verified",
            "acknowledged_work_retained": True,
        }
    return unfinished("readback_mismatch", condition=_condition(payload, loaded), loaded=loaded)


class CaseStorageService:
    """Owner-only durability checks for one sealed case payload."""

    def __init__(self, directory: CaseDirectory, sessions: Mapping[str, UserOwnedKeySession], kit: Any) -> None:
        if not isinstance(directory, CaseDirectory) or kit is None:
            raise CaseStorageError("storage_unavailable")
        self._directory = directory
        self._sessions = dict(sessions)
        self._kit = kit
        self._receipts: dict[str, dict[str, Any]] = {}
        self._identities: dict[str, dict[str, str]] = {}

    def commit(self, actor_principal_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        identity = self._identity(actor_principal_id, body)
        key_name = identity["idempotency_key"]
        previous = self._receipts.get(key_name)
        if previous is not None:
            if self._identities.get(key_name) != identity:
                raise CaseStorageError("replay_mismatch")
            retained = dict(previous)
            if retained.get("durable") is True:
                _log_receipt(retained)
                return retained
            raise CaseStorageError(str(retained.get("error") or "readback_mismatch"), retained)
        case = self._case(identity)
        session = self._sessions.get(identity["actor_principal_id"])
        if not isinstance(session, UserOwnedKeySession):
            raise CaseStorageError("key_unavailable", self._failure_receipt(identity, "key_unavailable", case_tenant=case.tenant_id))
        try:
            key_id = session.ensure_data_key(case.tenant_id, case.case_id)
            data_key = session.lookup_data_key(case.tenant_id, case.case_id, key_id)
        except Exception as exc:
            raise CaseStorageError("key_unavailable") from exc
        if data_key is None:
            raise CaseStorageError("key_unavailable")
        binding = PrivateArtifactBinding(
            tenant_id=case.tenant_id,
            case_id=case.case_id,
            artifact_kind=_KIND,
            revision=identity["revision"],
            principal_id=case.tenant_id,
        )
        try:
            envelope = seal_private_artifact(self._content(body), binding=binding, key=data_key, key_id=key_id)
        except Exception as exc:
            raise CaseStorageError("key_unavailable") from exc
        try:
            checked = observe_ciphertext_durability(self._kit, envelope)
        except CiphertextDurabilityError as exc:
            raise CaseStorageError(exc.code) from exc
        receipt = self._public(checked, identity, case.tenant_id)
        if receipt["durable"] is not True:
            self._remember(key_name, identity, receipt)
            _log_receipt(receipt)
            raise CaseStorageError(str(receipt.get("error") or "readback_mismatch"), receipt)
        self._remember(key_name, identity, receipt)
        _log_receipt(receipt)
        return receipt

    def read(self, actor_principal_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        identity = self._identity(actor_principal_id, body, content=False)
        self._case(identity)
        found = self._receipts.get(identity["idempotency_key"])
        if found is None or self._identities.get(identity["idempotency_key"]) != identity:
            raise CaseStorageError("missing_receipt", self._failure_receipt(identity, "missing_receipt", case_tenant=None))
        retained = dict(found)
        _log_receipt(retained)
        return retained

    def _failure_receipt(self, identity: Mapping[str, str], code: str, *, case_tenant: str | None) -> dict[str, Any]:
        receipt = {
            "task_id": TASK_ID,
            "recovery_task_id": RECOVERY_TASK_ID,
            "tenant_id": identity.get("tenant_id", ""),
            "case_id": identity.get("case_id", ""),
            "resource_id": identity.get("resource_id", ""),
            "revision": identity.get("revision", ""),
            "actor_principal_id": identity.get("actor_principal_id", ""),
            "canonical_owner_principal_id": case_tenant or "",
            "actor_is_encrypted_owner": False,
            "idempotency_key": identity.get("idempotency_key", ""),
            "states": [],
            "state_names": [],
            "durable": False,
            "readback_matched": False,
            "error": code,
            "failure_kind": _failure_kind(code),
            "storage_readiness": _readiness(code, durable=False),
            "interview_readiness": "not_evaluated",
            "legal_readiness": "not_evaluated",
            "storage_sets_interview_readiness": False,
            "storage_sets_legal_readiness": False,
            "unresolved": True,
            "pending_replica": False,
            "replica_status": "unresolved",
            "ciphertext_condition": "unavailable" if _failure_kind(code) == "backend" else "unresolved",
            "acknowledged_work_retained": False,
            "public_gateway_consulted": False,
            "cid_inference": False,
            "loss_of_acknowledged_work": False,
        }
        _log_receipt(receipt)
        return receipt

    def _remember(self, key_name: str, identity: Mapping[str, str], receipt: Mapping[str, Any]) -> None:
        self._identities[key_name] = dict(identity)
        self._receipts[key_name] = dict(receipt)

    def _public(self, checked: Mapping[str, Any], identity: Mapping[str, str], canonical: str) -> dict[str, Any]:
        names = list(checked["state_names"])
        durable = checked.get("durable") is True and checked.get("readback_matched") is True
        if durable and names != list(DURABILITY_STATES):
            raise CaseStorageError(str(checked.get("code") or "readback_mismatch"))
        code = "" if durable else str(checked.get("code") or "readback_mismatch")
        pending = checked.get("pending_replica") is True and not durable
        receipt = {
            "task_id": TASK_ID,
            "recovery_task_id": RECOVERY_TASK_ID,
            "tenant_id": identity["tenant_id"],
            "case_id": identity["case_id"],
            "resource_id": identity["resource_id"],
            "revision": identity["revision"],
            "actor_principal_id": identity["actor_principal_id"],
            "canonical_owner_principal_id": canonical,
            "actor_is_encrypted_owner": False,
            "idempotency_key": identity["idempotency_key"],
            "states": list(checked["states"]),
            "state_names": names,
            "durable": durable,
            "readback_matched": durable,
            "ciphertext_sha256": checked["ciphertext_sha256"],
            "byte_length": checked["byte_length"],
            "ref": checked["ref"],
            "public_gateway_consulted": False,
            "cid_inference": False,
            "pin_is_durable": False,
            "queued_replication_is_durable": False,
            "local_commit_is_durable": False,
            "error": code,
            "failure_kind": "none" if durable else _failure_kind(code),
            "storage_readiness": "ready" if durable else _readiness(code, durable=False),
            "interview_readiness": "not_evaluated",
            "legal_readiness": "not_evaluated",
            "storage_sets_interview_readiness": False,
            "storage_sets_legal_readiness": False,
            "unresolved": not durable,
            "pending_replica": pending,
            "replica_status": "verified" if durable else ("pending" if pending else "unresolved"),
            "ciphertext_condition": checked.get("ciphertext_condition") or ("matched" if durable else "unresolved"),
            "acknowledged_work_retained": bool(names) or durable,
            "loss_of_acknowledged_work": False,
            "limitations": (
                "durable_only_after_ciphertext_readback",
                "pin_queue_and_local_commit_are_distinct",
                "no_public_gateway_or_cid_inference",
                "no_websocket_or_sse",
                "storage_readiness_independent_of_interview_and_legal",
                "keys_omitted_from_receipts_and_logs",
                "unresolved_ciphertext_keeps_acknowledged_states",
            ),
        }
        return _strip_secrets(receipt)

    def _case(self, identity: Mapping[str, str]):
        try:
            case = self._directory.select_case(actor_principal_id=identity["actor_principal_id"], case_id=identity["case_id"])
        except CaseDirectoryError as exc:
            raise CaseStorageError("not_owner") from exc
        if case.tenant_id != identity["tenant_id"]:
            raise CaseStorageError("tenant_mismatch")
        if case.resource_id != identity["resource_id"]:
            raise CaseStorageError("resource_mismatch")
        return case

    def _identity(self, actor: str, body: Mapping[str, Any], *, content: bool = True) -> dict[str, str]:
        if not isinstance(body, Mapping):
            raise CaseStorageError("request_body")
        if any(name in body for name in _REJECTED_FIELDS):
            raise CaseStorageError("selector_rejected")
        if content and "content_base64" not in body:
            raise CaseStorageError("content_rejected")
        required = ("tenant_id", "case_id", "resource_id", "revision", "idempotency_key")
        identity = {"actor_principal_id": _label(actor, "actor")}
        for name in required:
            identity[name] = _label(body.get(name), name)
        return identity

    def _content(self, body: Mapping[str, Any]) -> bytes:
        encoded = body.get("content_base64")
        if not isinstance(encoded, str) or encoded.strip() == "":
            raise CaseStorageError("content_rejected")
        try:
            payload = base64.b64decode(encoded.encode("ascii"), validate=True)
        except (UnicodeEncodeError, ValueError) as exc:
            raise CaseStorageError("content_rejected") from exc
        if not payload or len(payload) > 256 * 1024:
            raise CaseStorageError("content_rejected")
        return payload


def mount_case_storage(app: Any) -> None:
    """Mount durability routes on the authenticated case catalog boundary."""

    from fastapi.responses import JSONResponse

    def _service(request: Request) -> CaseStorageService:
        service = getattr(request.app.state, "case_storage", None)
        if not isinstance(service, CaseStorageService):
            raise CaseStorageError("storage_unavailable")
        return service

    def _actor(request: Request) -> str:
        principal = getattr(request.state, "browser_principal", None)
        actor = getattr(principal, "principal_id", None)
        if not isinstance(actor, str) or actor == "":
            raise CaseStorageError("unauthenticated")
        return actor

    def _verify(request: Request):
        sessions = getattr(request.app.state, "browser_sessions", None)
        bound = getattr(request.state, "browser_principal", None)
        token = request.cookies.get(SESSION_COOKIE)
        if not isinstance(sessions, BrowserSessionService) or bound is None:
            raise CaseStorageError("unauthenticated")

        def verify() -> None:
            try:
                current = sessions.authenticate_token(token)
            except BrowserSessionError as exc:
                raise CaseStorageError("unauthenticated") from exc
            if (current.principal_id != bound.principal_id or current.tenant_id != bound.tenant_id
                    or current.generation != bound.generation):
                raise CaseStorageError("unauthenticated")

        return verify

    def _material(request: Request) -> Mapping[str, Any]:
        material = getattr(request.state, "case_catalog_material", None)
        return material if isinstance(material, Mapping) else {}

    def _publish(request: Request, body: Mapping[str, Any]) -> None:
        """Record storage readiness only. Interview and legal readiness stay put."""

        readiness = body.get("storage_readiness")
        if readiness in {"ready", "unresolved", "unavailable"}:
            request.app.state.storage_readiness = readiness

    def _fail(request: Request, exc: BaseException) -> JSONResponse:
        code = str(getattr(exc, "code", "storage_unavailable"))
        body: dict[str, Any] = {
            "error": code,
            "durable": False,
            "recovery_task_id": RECOVERY_TASK_ID,
            "failure_kind": _failure_kind(code),
            "storage_readiness": _readiness(code, durable=False),
            "interview_readiness": "not_evaluated",
            "legal_readiness": "not_evaluated",
            "storage_sets_interview_readiness": False,
            "storage_sets_legal_readiness": False,
            "unresolved": True,
            "pending_replica": False,
            "replica_status": "unresolved",
            "acknowledged_work_retained": False,
            "loss_of_acknowledged_work": False,
            "public_gateway_consulted": False,
            "cid_inference": False,
            "actor_is_encrypted_owner": False,
        }
        receipt = getattr(exc, "receipt", None)
        if isinstance(receipt, Mapping):
            public = _strip_secrets(receipt)
            for name in (
                "state_names", "states", "readback_matched", "pending_replica", "replica_status",
                "storage_readiness", "interview_readiness", "legal_readiness",
                "storage_sets_interview_readiness", "storage_sets_legal_readiness",
                "unresolved", "failure_kind", "ciphertext_condition", "acknowledged_work_retained",
                "loss_of_acknowledged_work", "recovery_task_id", "idempotency_key", "revision",
                "actor_is_encrypted_owner",
            ):
                if name in public:
                    body[name] = public[name]
            body["readback_matched"] = public.get("readback_matched") is True
            body["public_gateway_consulted"] = False
            body["cid_inference"] = False
            body["durable"] = False
        body = _strip_secrets(body)
        _publish(request, body)
        _log_receipt(body)
        return JSONResponse(body, status_code=case_storage_status(code), headers=_NO_STORE_HEADERS)

    @app.post("/api/cases/storage/durability")
    async def storage_commit(request: Request):
        try:
            verify = _verify(request)
            verify()
            receipt = await run_in_threadpool(_service(request).commit, _actor(request), _material(request))
            verify()
        except CaseStorageError as exc:
            return _fail(request, exc)
        _publish(request, receipt)
        return JSONResponse(receipt, status_code=201, headers=_NO_STORE_HEADERS)

    @app.get("/api/cases/storage/durability")
    async def storage_read(request: Request):
        try:
            verify = _verify(request)
            verify()
            receipt = await run_in_threadpool(_service(request).read, _actor(request), _material(request))
            verify()
        except CaseStorageError as exc:
            return _fail(request, exc)
        _publish(request, receipt)
        return JSONResponse(receipt, headers=_NO_STORE_HEADERS)
