"""Durable case-scoped conversation threads with encrypted message versions.

Threads belong to one case. Sends are ordered and idempotent. Each message
version is a sealed envelope whose associated data is the case tenant, not the
authenticated actor. Plaintext stays classified as conversation until an
authorized adoption records evidence, an answer, or a model input.

Adoption records that classification only. It does not copy text into an
evidence store, an intake answer, or a model request.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from applications.case_directory import CaseDirectory, CaseDirectoryError
from applications.case_membership import CaseMembershipError, CaseMembershipStore
from applications.principal_store import PrincipalStore, PrincipalStoreError
from integrations.private_storage import (
    PrivateArtifactBinding,
    PrivateArtifactIntegrityError,
    assert_access_matches_binding,
    open_private_artifact,
    seal_private_artifact,
)

TASK_ID = "CIMP-GUI-42"
SCHEMA_VERSION = 1
THREAD_KIND = "case-message-thread"
MESSAGE_KIND = "case-message-version"
ATTACHMENT_BINDING_KIND = "case-message-attachment-binding"
MAX_TEXT_CHARS = 4000
DEFAULT_PAGE_LIMIT = 10
MAX_PAGE_LIMIT = 20
DISPOSITIONS = frozenset({"conversation", "evidence", "answer", "model_input"})
ADOPTION_TARGETS = frozenset({"evidence", "answer", "model_input"})
MESSAGE_LIMITATIONS = (
    "message_text_is_conversation_until_explicit_adoption",
    "adoption_does_not_execute_model_input",
    "adoption_does_not_write_evidence_or_intake_answers",
    "actor_is_not_the_canonical_encrypted_owner",
    "pagination_is_bounded",
    "send_is_idempotent",
    "no_external_delivery",
    "no_websocket_or_sse",
)
_REJECTED_BODY_FIELDS = frozenset({
    "trusted_local",
    "trust",
    "role",
    "roles",
    "staff_role",
    "is_admin",
    "is_staff",
    "is_lawyer",
    "is_member",
    "membership",
    "grant",
    "actions",
    "status",
    "accepted",
    "case_plaintext",
    "plaintext",
    "credentials",
    "credential",
    "narrative",
    "evidence",
    "browser_key",
    "data_key",
    "passphrase",
    "wrapped_ciphertext",
    "wrapped_nonce",
    "envelope",
    "key_material",
    "canonical_owner_principal_id",
    "actor_is_encrypted_owner",
})


class CaseMessageError(Exception):
    """Fail-closed conversation error. ``code`` is a stable machine reason."""

    def __init__(self, code: str) -> None:
        self.code = str(code)
        super().__init__(self.code)


@dataclass(frozen=True)
class _CanonicalAccess:
    trust: str
    principal_id: str
    case_id: str


@dataclass(eq=False)
class _PublicationScope:
    store: Any
    verify: Callable[[], Any]
    active: bool = True


_PUBLICATION_SCOPE: ContextVar[Any] = ContextVar("case_message_publication_scope", default=None)


def _opaque_id() -> str:
    return uuid.uuid4().hex


def _label(value: Any, code: str) -> str:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise CaseMessageError(code)
    if any(char in value for char in ("\x00", "\n", "\r", "/", "\\")):
        raise CaseMessageError(code)
    if len(value) > 200:
        raise CaseMessageError(code)
    return value


def _fingerprint(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _as_int(value: Any, code: str) -> int:
    if isinstance(value, bool):
        raise CaseMessageError(code)
    if type(value) is int:
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise CaseMessageError(code)


class _FileLock:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._handle: Any = None

    def __enter__(self) -> _FileLock:
        self._handle = self._path.open("a+")
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None


class CaseMessageStore:
    """File-backed encrypted threads for one injected storage key."""

    def __init__(
        self,
        root: str | Path,
        *,
        key: bytes,
        key_id: str,
        principals: PrincipalStore,
        cases: CaseDirectory,
        memberships: CaseMembershipStore,
        clock: Callable[[], int],
    ) -> None:
        if not isinstance(key, (bytes, bytearray)) or isinstance(key, memoryview) or len(bytes(key)) != 32:
            raise CaseMessageError("key_material")
        if not isinstance(principals, PrincipalStore) or not isinstance(cases, CaseDirectory):
            raise CaseMessageError("authority_owners")
        if not isinstance(memberships, CaseMembershipStore) or not callable(clock):
            raise CaseMessageError("authority_owners")
        self._key = bytes(key)
        self._key_id = _label(key_id, "key_id")
        self._principals = principals
        self._cases = cases
        self._memberships = memberships
        self._clock = clock
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        os.chmod(self._root, 0o700)
        self._lock_path = self._root / ".lock"
        self._lock_path.touch(mode=0o600)
        for name in ("threads", "messages", "order", "case-threads", "idem", "attachments"):
            path = self._root / name
            path.mkdir(mode=0o700, exist_ok=True)
        for name in ("thread", "send", "revise", "adopt"):
            (self._root / "idem" / name).mkdir(mode=0o700, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    @contextmanager
    def publication_scope(self, verify: Callable[[], Any]):
        """Use only a trusted current-request verifier, never a body flag.

        Its lifetime ends even in a copied context. Each existing atomic
        publication rechecks after preparation and immediately before replace.
        """
        if not callable(verify):
            raise CaseMessageError("message_unavailable")
        scope = _PublicationScope(self, verify)
        token = _PUBLICATION_SCOPE.set(scope)
        try:
            self._verify_publication()
            yield
            self._verify_publication()
        finally:
            scope.active = False
            _PUBLICATION_SCOPE.reset(token)

    def _verify_publication(self) -> None:
        scope = _PUBLICATION_SCOPE.get()
        if scope is not None:
            if type(scope) is not _PublicationScope or not scope.active or scope.store is not self:
                raise CaseMessageError("message_unavailable")
            scope.verify()

    def _attachment_directory(self, tenant_id: str, case_id: str) -> Path:
        identity = _fingerprint({"tenant_id": tenant_id, "case_id": case_id})
        return self._root / "attachments" / identity

    def record_thread_attachment(self, actor_principal_id: str, body: Mapping[str, Any],
                                 record: Mapping[str, Any], *, verify_access=None) -> dict[str, Any]:
        """Persist immutable thread metadata after the attachment owner admitted bytes.

        This encrypted record contains no path, CID, filename, key or payload.
        It cannot authorize attachment decryption: that remains the real grant
        and recipient-key owner on every read.
        """
        actor = self._active(actor_principal_id)
        payload = self._body(body)
        keys = {"attachment_id", "thread_id", "tenant_id", "case_id", "resource_id",
            "resource_revision", "artifact_revision", "actor_principal_id"}
        if not isinstance(record, Mapping) or set(record) != keys or record.get("actor_principal_id") != actor:
            raise CaseMessageError("binding_mismatch")
        document = dict(record)
        for field in keys - {"resource_revision"}:
            _label(document[field], "binding_mismatch")
        if type(document["resource_revision"]) is not int:
            raise CaseMessageError("revision_conflict")

        def verify():
            if verify_access is not None:
                verify_access()
            admission = self._admit(actor, document["case_id"], "case.message.send", payload)
            if any(document[key] != admission[key] for key in ("case_id", "tenant_id", "resource_id", "resource_revision")):
                raise CaseMessageError("revision_conflict")
            self._require_thread(document["thread_id"], admission["case_id"])

        with self.publication_scope(verify), self._locked():
            directory = self._attachment_directory(document["tenant_id"], document["case_id"])
            directory.mkdir(mode=0o700, exist_ok=True)
            path = directory / (document["attachment_id"] + ".envelope")
            if path.exists():
                prior = self._open_document(path, kind=ATTACHMENT_BINDING_KIND, revision=1,
                    tenant_id=document["tenant_id"], case_id=document["case_id"])
                if prior != document:
                    raise CaseMessageError("replay_mismatch")
                return dict(prior)
            self._seal(document=document, kind=ATTACHMENT_BINDING_KIND, directory=directory,
                stem=document["attachment_id"], revision=1, tenant_id=document["tenant_id"], case_id=document["case_id"])
            return dict(document)

    def thread_attachment_bindings(self, actor_principal_id: str, body: Mapping[str, Any],
                                   *, attachment_id: str | None = None) -> list[dict[str, Any]]:
        actor, payload = self._active(actor_principal_id), self._body(body)
        case_id = _label(payload.get("case_id"), "case_id")
        thread = _label(payload.get("thread_id"), "thread_id")
        admission = self._admit_read(actor, case_id, payload)
        with self._locked():
            self._require_thread(thread, case_id)
            directory = self._attachment_directory(admission["tenant_id"], case_id)
            paths = ([directory / (_label(attachment_id, "attachment_id") + ".envelope")]
                if attachment_id is not None else sorted(directory.glob("*.envelope")))
            if len(paths) > 4096:
                raise CaseMessageError("page_limit")
            rows = []
            for path in paths:
                if not path.exists():
                    continue
                record = self._open_document(path, kind=ATTACHMENT_BINDING_KIND, revision=1,
                    tenant_id=admission["tenant_id"], case_id=case_id)
                if (record.get("attachment_id") != path.stem or record.get("case_id") != case_id
                        or record.get("tenant_id") != admission["tenant_id"]
                        or record.get("resource_id") != admission["resource_id"]):
                    raise CaseMessageError("binding_mismatch")
                if record.get("thread_id") == thread:
                    rows.append(record)
            self._readmit_read(actor, case_id, payload)
            return rows

    def create_thread(self, actor_principal_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        actor = self._active(actor_principal_id)
        payload = self._body(body)
        if "text" in payload or "disposition" in payload:
            raise CaseMessageError("thread_has_no_message_text")
        case_id = _label(payload.get("case_id"), "case_id")
        key = _label(payload.get("idempotency_key"), "idempotency_key")
        admission = self._admit(actor, case_id, "case.message.send", payload)
        fingerprint = _fingerprint({
            "actor_principal_id": actor,
            "case_id": admission["case_id"],
            "tenant_id": admission["tenant_id"],
            "resource_id": admission["resource_id"],
        })
        with self._locked():
            self._readmit(actor, case_id, "case.message.send", payload)
            existing = self._read_idem("thread", key)
            if existing is not None:
                if existing.get("fingerprint") != fingerprint:
                    raise CaseMessageError("replay_mismatch")
                thread = self._load_thread(str(existing["thread_id"]))
                if thread["case_id"] != admission["case_id"]:
                    raise CaseMessageError("replay_mismatch")
                return self._thread_view(thread, admission)
            now = self._now()
            thread = {
                "schema_version": SCHEMA_VERSION,
                "thread_id": _opaque_id(),
                "case_id": admission["case_id"],
                "tenant_id": admission["tenant_id"],
                "resource_id": admission["resource_id"],
                "created_by": actor,
                "created_at": now,
                "version": 1,
            }
            self._seal_thread(thread)
            self._write_json(self._root / "order" / f"{thread['thread_id']}.json", [])
            threads = self._case_threads(thread["case_id"])
            threads.append(thread["thread_id"])
            self._write_json(self._root / "case-threads" / f"{thread['case_id']}.json", threads)
            self._write_idem("thread", key, {"thread_id": thread["thread_id"], "fingerprint": fingerprint})
            return self._thread_view(thread, admission)

    def list_threads(self, actor_principal_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        actor = self._active(actor_principal_id)
        payload = self._body(body)
        case_id = _label(payload.get("case_id"), "case_id")
        admission = self._admit_read(actor, case_id, payload)
        with self._locked():
            self._readmit_read(actor, case_id, payload)
            rows = []
            for thread_id in self._case_threads(admission["case_id"]):
                thread = self._load_thread(thread_id)
                if thread["case_id"] != admission["case_id"]:
                    raise CaseMessageError("case_mismatch")
                rows.append(self._thread_view(thread, admission))
            rows.sort(key=lambda item: item["thread_id"])
            return {
                "actor_principal_id": actor,
                "case_id": admission["case_id"],
                "threads": rows,
                "canonical_owner_principal_id": admission["tenant_id"],
                "actor_is_encrypted_owner": actor == admission["tenant_id"],
                "limitations": list(MESSAGE_LIMITATIONS),
            }

    def send(self, actor_principal_id: str, thread_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        actor = self._active(actor_principal_id)
        payload = self._body(body)
        if "disposition" in payload or "adopt" in payload:
            raise CaseMessageError("disposition_requires_transition")
        thread_key = _label(thread_id, "thread_id")
        supplied = payload.get("thread_id", thread_key)
        if supplied != thread_key:
            raise CaseMessageError("thread_mismatch")
        text = self._text(payload.get("text"))
        key = _label(payload.get("idempotency_key"), "idempotency_key")
        case_id = _label(payload.get("case_id"), "case_id")
        admission = self._admit(actor, case_id, "case.message.send", payload)
        fingerprint = _fingerprint({
            "actor_principal_id": actor,
            "thread_id": thread_key,
            "case_id": admission["case_id"],
            "text": text,
        })
        with self._locked():
            self._readmit(actor, case_id, "case.message.send", payload)
            thread = self._require_thread(thread_key, admission["case_id"])
            existing = self._read_idem("send", self._scoped_key(actor, thread_key, key))
            if existing is not None:
                if existing.get("fingerprint") != fingerprint:
                    raise CaseMessageError("replay_mismatch")
                message = self._load_message(str(existing["message_id"]))
                return self._message_view(message, admission, text_version=int(existing["version"]))
            sequence = self._next_sequence(thread_key)
            now = self._now()
            message = {
                "schema_version": SCHEMA_VERSION,
                "message_id": _opaque_id(),
                "thread_id": thread["thread_id"],
                "case_id": thread["case_id"],
                "tenant_id": thread["tenant_id"],
                "resource_id": thread["resource_id"],
                "sequence": sequence,
                "sender_principal_id": actor,
                "disposition": "conversation",
                "adoption": None,
                "versions": [{
                    "version": 1,
                    "text": text,
                    "created_at": now,
                    "actor_principal_id": actor,
                    "idempotency_key": key,
                }],
            }
            self._seal_message(message)
            order = self._order(thread_key)
            order.append({"message_id": message["message_id"], "sequence": sequence})
            self._write_json(self._root / "order" / f"{thread_key}.json", order)
            self._write_idem("send", self._scoped_key(actor, thread_key, key), {
                "message_id": message["message_id"],
                "version": 1,
                "fingerprint": fingerprint,
            })
            return self._message_view(message, admission, text_version=1)

    def revise(self, actor_principal_id: str, thread_id: str, message_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        actor = self._active(actor_principal_id)
        payload = self._body(body)
        if "disposition" in payload:
            raise CaseMessageError("disposition_requires_transition")
        thread_key = _label(thread_id, "thread_id")
        message_key = _label(message_id, "message_id")
        text = self._text(payload.get("text"))
        key = _label(payload.get("idempotency_key"), "idempotency_key")
        expected = _as_int(payload.get("expected_version"), "revision_conflict")
        case_id = _label(payload.get("case_id"), "case_id")
        admission = self._admit(actor, case_id, "case.message.send", payload)
        fingerprint = _fingerprint({
            "actor_principal_id": actor,
            "thread_id": thread_key,
            "message_id": message_key,
            "text": text,
            "expected_version": expected,
        })
        with self._locked():
            self._readmit(actor, case_id, "case.message.send", payload)
            self._require_thread(thread_key, admission["case_id"])
            existing = self._read_idem("revise", self._scoped_key(actor, message_key, key))
            if existing is not None:
                if existing.get("fingerprint") != fingerprint:
                    raise CaseMessageError("replay_mismatch")
                message = self._load_message(message_key)
                return self._message_view(message, admission, text_version=int(existing["version"]))
            message = self._load_message(message_key)
            self._bound_message(message, thread_key, admission["case_id"])
            if message["disposition"] != "conversation":
                raise CaseMessageError("disposition_locked")
            current = int(message["versions"][-1]["version"])
            if expected != current:
                raise CaseMessageError("revision_conflict")
            version = current + 1
            updated = dict(message)
            updated["versions"] = list(message["versions"]) + [{
                "version": version,
                "text": text,
                "created_at": self._now(),
                "actor_principal_id": actor,
                "idempotency_key": key,
            }]
            self._seal_message(updated)
            self._write_idem("revise", self._scoped_key(actor, message_key, key), {
                "message_id": message_key,
                "version": version,
                "fingerprint": fingerprint,
            })
            return self._message_view(updated, admission, text_version=version)

    def page(self, actor_principal_id: str, thread_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        actor = self._active(actor_principal_id)
        payload = self._body(body)
        thread_key = _label(thread_id, "thread_id")
        case_id = _label(payload.get("case_id"), "case_id")
        limit = DEFAULT_PAGE_LIMIT if payload.get("limit") is None else _as_int(payload.get("limit"), "page_limit")
        if not 1 <= limit <= MAX_PAGE_LIMIT:
            raise CaseMessageError("page_limit")
        cursor = 0 if payload.get("cursor") in (None, "") else _as_int(payload.get("cursor"), "page_cursor")
        if cursor < 0:
            raise CaseMessageError("page_cursor")
        admission = self._admit_read(actor, case_id, payload)
        with self._locked():
            self._readmit_read(actor, case_id, payload)
            thread = self._require_thread(thread_key, admission["case_id"])
            ordered = [item for item in self._order(thread_key) if int(item["sequence"]) > cursor]
            window = ordered[:limit]
            messages = []
            last = cursor
            for item in window:
                message = self._load_message(str(item["message_id"]))
                self._bound_message(message, thread["thread_id"], admission["case_id"])
                if int(message["sequence"]) != int(item["sequence"]):
                    raise CaseMessageError("order_mismatch")
                messages.append(self._message_view(message, admission))
                last = int(message["sequence"])
            if messages and any(messages[index]["sequence"] >= messages[index + 1]["sequence"] for index in range(len(messages) - 1)):
                raise CaseMessageError("order_mismatch")
            remaining = len(ordered) > len(window)
            return {
                "actor_principal_id": actor,
                "thread_id": thread["thread_id"],
                "case_id": thread["case_id"],
                "messages": messages,
                "ordered": True,
                "limit": limit,
                "cursor": cursor,
                "next_cursor": last if remaining else None,
                "canonical_owner_principal_id": admission["tenant_id"],
                "actor_is_encrypted_owner": actor == admission["tenant_id"],
                "limitations": list(MESSAGE_LIMITATIONS),
            }

    def adopt(self, actor_principal_id: str, thread_id: str, message_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        actor = self._active(actor_principal_id)
        payload = self._body(body)
        if "text" in payload:
            raise CaseMessageError("adoption_has_no_text")
        thread_key = _label(thread_id, "thread_id")
        message_key = _label(message_id, "message_id")
        target = payload.get("disposition")
        if target not in ADOPTION_TARGETS:
            raise CaseMessageError("disposition_required")
        key = _label(payload.get("idempotency_key"), "idempotency_key")
        expected = _as_int(payload.get("expected_version"), "revision_conflict")
        case_id = _label(payload.get("case_id"), "case_id")
        admission = self._admit(actor, case_id, "case.review", payload)
        fingerprint = _fingerprint({
            "actor_principal_id": actor,
            "thread_id": thread_key,
            "message_id": message_key,
            "disposition": target,
            "expected_version": expected,
        })
        with self._locked():
            self._readmit(actor, case_id, "case.review", payload)
            self._require_thread(thread_key, admission["case_id"])
            existing = self._read_idem("adopt", self._scoped_key(actor, message_key, key))
            if existing is not None:
                if existing.get("fingerprint") != fingerprint:
                    raise CaseMessageError("replay_mismatch")
                message = self._load_message(message_key)
                return self._message_view(message, admission)
            message = self._load_message(message_key)
            self._bound_message(message, thread_key, admission["case_id"])
            current = int(message["versions"][-1]["version"])
            if expected != current:
                raise CaseMessageError("revision_conflict")
            if message["disposition"] == target and message.get("adoption", {}).get("idempotency_key") == key:
                return self._message_view(message, admission)
            if message["disposition"] != "conversation":
                raise CaseMessageError("disposition_locked")
            updated = dict(message)
            updated["disposition"] = target
            updated["adoption"] = {
                "disposition": target,
                "actor_principal_id": actor,
                "at": self._now(),
                "version": current,
                "idempotency_key": key,
                "executed_as_model_input": False,
                "recorded_as_evidence_artifact": False,
                "recorded_as_intake_answer": False,
            }
            self._seal_message(updated)
            self._write_idem("adopt", self._scoped_key(actor, message_key, key), {
                "message_id": message_key,
                "fingerprint": fingerprint,
            })
            return self._message_view(updated, admission)

    def _admit_read(self, actor: str, case_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        failure: CaseMessageError | None = None
        for action in ("case.read", "case.message.send"):
            try:
                return self._admit(actor, case_id, action, payload)
            except CaseMessageError as exc:
                if exc.code != "action_not_permitted":
                    raise
                failure = exc
        if failure is None:
            raise CaseMessageError("action_not_permitted")
        raise failure

    def _readmit_read(self, actor: str, case_id: str, payload: Mapping[str, Any]) -> None:
        self._admit_read(actor, case_id, payload)

    def _admit(self, actor: str, case_id: str, action: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        owned = self._owner_case(actor, case_id)
        if owned is not None:
            self._matching_case_selectors(payload, owned.tenant_id, owned.resource_id)
            return {
                "actor_principal_id": actor,
                "tenant_id": owned.tenant_id,
                "case_id": owned.case_id,
                "resource_id": owned.resource_id,
                "resource_revision": owned.revision,
                "action": action,
            }
        if payload.get("membership_grant_id") in (None, ""):
            raise CaseMessageError("missing_case")
        grant_id = _label(payload.get("membership_grant_id"), "membership_grant_id")
        expected = _as_int(payload.get("expected_membership_version"), "membership_revision_conflict")
        try:
            grant = self._memberships.load(grant_id)
        except CaseMembershipError as exc:
            raise CaseMessageError("missing_grant" if exc.code == "missing_grant" else _membership_code(exc.code)) from exc
        if actor not in {grant.owner_principal_id, grant.member_principal_id}:
            raise CaseMessageError("missing_grant")
        self._matching_case_selectors(payload, grant.tenant_id, grant.resource_id)
        try:
            decision = self._memberships.authorize(
                actor_principal_id=actor,
                grant_id=grant.grant_id,
                tenant_id=grant.tenant_id,
                case_id=case_id,
                resource_id=grant.resource_id,
                action=action,
                expected_version=expected,
            )
        except CaseMembershipError as exc:
            code = "membership_revision_conflict" if exc.code == "revision_conflict" else _membership_code(exc.code)
            raise CaseMessageError(code) from exc
        return {
            "actor_principal_id": actor,
            "tenant_id": decision.tenant_id,
            "case_id": decision.case_id,
            "resource_id": decision.resource_id,
            "resource_revision": grant.case_revision,
            "action": action,
        }

    def _readmit(self, actor: str, case_id: str, action: str, payload: Mapping[str, Any]) -> None:
        self._admit(actor, case_id, action, payload)

    def _owner_case(self, actor: str, case_id: str):
        try:
            case = self._cases.select_case(actor_principal_id=actor, case_id=case_id)
        except CaseDirectoryError as exc:
            if exc.code == "missing_case":
                return None
            raise CaseMessageError("missing_case") from exc
        if case.owner_principal_id != actor:
            return None
        return case

    def _matching_case_selectors(self, payload: Mapping[str, Any], tenant_id: str, resource_id: str) -> None:
        if "tenant_id" in payload and payload.get("tenant_id") != tenant_id:
            raise CaseMessageError("missing_case")
        if "resource_id" in payload and payload.get("resource_id") != resource_id:
            raise CaseMessageError("missing_case")

    def _require_thread(self, thread_id: str, case_id: str) -> dict[str, Any]:
        try:
            thread = self._load_thread(thread_id)
        except CaseMessageError as exc:
            if exc.code == "missing_thread":
                raise
            raise
        if thread["case_id"] != case_id or thread["tenant_id"] == "":
            raise CaseMessageError("missing_thread")
        return thread

    def _bound_message(self, message: Mapping[str, Any], thread_id: str, case_id: str) -> None:
        if message["thread_id"] != thread_id or message["case_id"] != case_id:
            raise CaseMessageError("missing_message")

    def _thread_view(self, thread: Mapping[str, Any], admission: Mapping[str, Any]) -> dict[str, Any]:
        order = self._order(str(thread["thread_id"]))
        return {
            "thread_id": thread["thread_id"],
            "case_id": thread["case_id"],
            "tenant_id": thread["tenant_id"],
            "resource_id": thread["resource_id"],
            "created_by": thread["created_by"],
            "created_at": thread["created_at"],
            "message_count": len(order),
            "canonical_owner_principal_id": thread["tenant_id"],
            "actor_principal_id": admission["actor_principal_id"],
            "actor_is_encrypted_owner": admission["actor_principal_id"] == thread["tenant_id"],
            "limitations": list(MESSAGE_LIMITATIONS),
        }

    def _message_view(self, message: Mapping[str, Any], admission: Mapping[str, Any], *, text_version: int | None = None) -> dict[str, Any]:
        versions = []
        for item in message["versions"]:
            versions.append({
                "version": item["version"],
                "text": item["text"],
                "created_at": item["created_at"],
                "actor_principal_id": item["actor_principal_id"],
            })
        selected = versions[-1] if text_version is None else next(item for item in versions if item["version"] == text_version)
        adoption = message.get("adoption")
        return {
            "message_id": message["message_id"],
            "thread_id": message["thread_id"],
            "case_id": message["case_id"],
            "tenant_id": message["tenant_id"],
            "sequence": message["sequence"],
            "sender_principal_id": message["sender_principal_id"],
            "version": selected["version"],
            "current_version": versions[-1]["version"],
            "text": selected["text"],
            "disposition": message["disposition"],
            "versions": versions,
            "adoption": None if adoption is None else {
                "disposition": adoption["disposition"],
                "actor_principal_id": adoption["actor_principal_id"],
                "version": adoption["version"],
                "executed_as_model_input": False,
                "recorded_as_evidence_artifact": False,
                "recorded_as_intake_answer": False,
            },
            "canonical_owner_principal_id": message["tenant_id"],
            "actor_principal_id": admission["actor_principal_id"],
            "actor_is_encrypted_owner": admission["actor_principal_id"] == message["tenant_id"],
            "limitations": list(MESSAGE_LIMITATIONS),
        }

    def _seal_thread(self, thread: Mapping[str, Any]) -> None:
        self._seal(
            document=thread,
            kind=THREAD_KIND,
            directory=self._root / "threads",
            stem=str(thread["thread_id"]),
            revision=int(thread["version"]),
            tenant_id=str(thread["tenant_id"]),
            case_id=str(thread["case_id"]),
        )
        pointer = self._root / "threads" / str(thread["thread_id"])
        self._write_text(pointer.with_suffix(".tenant"), str(thread["tenant_id"]))
        self._write_text(pointer.with_suffix(".case"), str(thread["case_id"]))

    def _seal_message(self, message: Mapping[str, Any]) -> None:
        version = int(message["versions"][-1]["version"])
        self._seal(
            document=message,
            kind=MESSAGE_KIND,
            directory=self._root / "messages",
            stem=f"{message['message_id']}.v{version}",
            revision=version,
            tenant_id=str(message["tenant_id"]),
            case_id=str(message["case_id"]),
        )
        pointer = self._root / "messages" / message["message_id"]
        self._write_text(pointer.with_suffix(".version"), str(version))
        self._write_text(pointer.with_suffix(".tenant"), str(message["tenant_id"]))
        self._write_text(pointer.with_suffix(".case"), str(message["case_id"]))
        self._write_text(pointer.with_suffix(".thread"), str(message["thread_id"]))

    def _seal(self, *, document: Mapping[str, Any], kind: str, directory: Path, stem: str,
              revision: int, tenant_id: str, case_id: str) -> None:
        binding = PrivateArtifactBinding(
            tenant_id=tenant_id,
            case_id=case_id,
            artifact_kind=kind,
            revision=str(revision),
            principal_id=tenant_id,
        )
        access = _CanonicalAccess("authenticated", tenant_id, case_id)
        assert_access_matches_binding(access, binding)
        payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        envelope = seal_private_artifact(payload, binding=binding, key=self._key, key_id=self._key_id)
        path = directory / f"{stem}.envelope"
        temporary = directory / f"{stem}.envelope.tmp"
        temporary.write_bytes(envelope)
        os.chmod(temporary, 0o600)
        try:
            self._verify_publication()
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _load_thread(self, thread_id: str) -> dict[str, Any]:
        path = self._root / "threads" / f"{thread_id}.envelope"
        if not path.is_file() or path.is_symlink():
            raise CaseMessageError("missing_thread")
        # Thread identity is inside the envelope. The case index is a hint.
        case_id = self._thread_case(thread_id)
        tenant_id = self._thread_tenant(thread_id)
        return self._open_document(path, kind=THREAD_KIND, revision=1, tenant_id=tenant_id, case_id=case_id)

    def _thread_case(self, thread_id: str) -> str:
        for path in sorted((self._root / "case-threads").glob("*.json")):
            rows = json.loads(path.read_text(encoding="utf-8"))
            if thread_id in rows:
                return path.name[: -len(".json")]
        raise CaseMessageError("missing_thread")

    def _thread_tenant(self, thread_id: str) -> str:
        case_id = self._thread_case(thread_id)
        # Tenant is recovered by trying each sealed thread only after the case
        # index matches. The envelope binding uses the tenant stored beside it.
        pointer = self._root / "threads" / f"{thread_id}.tenant"
        if not pointer.is_file() or pointer.is_symlink():
            raise CaseMessageError("missing_thread")
        tenant_id = pointer.read_text(encoding="utf-8").strip()
        case_pointer = self._root / "threads" / f"{thread_id}.case"
        if not case_pointer.is_file() or case_pointer.read_text(encoding="utf-8").strip() != case_id:
            raise CaseMessageError("missing_thread")
        return tenant_id

    def _load_message(self, message_id: str) -> dict[str, Any]:
        pointer = self._root / "messages" / message_id
        version_path = pointer.with_suffix(".version")
        tenant_path = pointer.with_suffix(".tenant")
        case_path = pointer.with_suffix(".case")
        if not version_path.is_file() or not tenant_path.is_file() or not case_path.is_file():
            raise CaseMessageError("missing_message")
        if version_path.is_symlink() or tenant_path.is_symlink() or case_path.is_symlink():
            raise CaseMessageError("missing_message")
        version_text = version_path.read_text(encoding="utf-8").strip()
        if not version_text.isdigit():
            raise CaseMessageError("revision_pointer")
        version = int(version_text)
        tenant_id = tenant_path.read_text(encoding="utf-8").strip()
        case_id = case_path.read_text(encoding="utf-8").strip()
        path = self._root / "messages" / f"{message_id}.v{version}.envelope"
        document = self._open_document(path, kind=MESSAGE_KIND, revision=version, tenant_id=tenant_id, case_id=case_id)
        if document["message_id"] != message_id or int(document["versions"][-1]["version"]) != version:
            raise CaseMessageError("revision_mismatch")
        if document["case_id"] != case_id or document["tenant_id"] != tenant_id:
            raise CaseMessageError("binding_mismatch")
        return document

    def _open_document(self, path: Path, *, kind: str, revision: int, tenant_id: str, case_id: str) -> dict[str, Any]:
        if not path.is_file() or path.is_symlink():
            raise CaseMessageError("missing_message" if kind == MESSAGE_KIND else "missing_thread")
        binding = PrivateArtifactBinding(
            tenant_id=tenant_id,
            case_id=case_id,
            artifact_kind=kind,
            revision=str(revision),
            principal_id=tenant_id,
        )
        access = _CanonicalAccess("authenticated", tenant_id, case_id)
        assert_access_matches_binding(access, binding)
        try:
            plaintext = open_private_artifact(path.read_bytes(), binding=binding, key=self._key, expected_key_id=self._key_id)
        except PrivateArtifactIntegrityError as exc:
            raise CaseMessageError("integrity") from exc
        document = json.loads(plaintext.decode("utf-8"))
        if not isinstance(document, dict):
            raise CaseMessageError("integrity")
        return document

    def _next_sequence(self, thread_id: str) -> int:
        order = self._order(thread_id)
        if not order:
            return 1
        return max(int(item["sequence"]) for item in order) + 1

    def _order(self, thread_id: str) -> list[dict[str, Any]]:
        path = self._root / "order" / f"{thread_id}.json"
        if not path.is_file():
            raise CaseMessageError("missing_thread")
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise CaseMessageError("order_mismatch")
        return rows

    def _case_threads(self, case_id: str) -> list[str]:
        path = self._root / "case-threads" / f"{case_id}.json"
        if not path.exists():
            return []
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or any(not isinstance(item, str) for item in rows):
            raise CaseMessageError("integrity")
        return rows

    def _scoped_key(self, actor: str, scope: str, key: str) -> str:
        return _fingerprint({"actor": actor, "scope": scope, "key": key})

    def _read_idem(self, kind: str, key: str) -> dict[str, Any] | None:
        path = self._root / "idem" / kind / hashlib.sha256(key.encode("utf-8")).hexdigest()
        if not path.is_file():
            return None
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise CaseMessageError("integrity")
        return document

    def _write_idem(self, kind: str, key: str, document: Mapping[str, Any]) -> None:
        path = self._root / "idem" / kind / hashlib.sha256(key.encode("utf-8")).hexdigest()
        self._write_json(path, dict(document))

    def _write_json(self, path: Path, document: Any) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        os.chmod(temporary, 0o600)
        try:
            self._verify_publication()
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _write_text(self, path: Path, text: str) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        os.chmod(temporary, 0o600)
        try:
            self._verify_publication()
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _text(self, value: Any) -> str:
        if not isinstance(value, str) or value == "" or "\x00" in value:
            raise CaseMessageError("text_required")
        if len(value) > MAX_TEXT_CHARS:
            raise CaseMessageError("text_too_long")
        return value

    def _body(self, body: Mapping[str, Any] | None) -> Mapping[str, Any]:
        if not isinstance(body, Mapping):
            raise CaseMessageError("request_body")
        if any(name in body for name in _REJECTED_BODY_FIELDS):
            raise CaseMessageError("request_cannot_mint_authority")
        if body.get("trusted_local") is True or body.get("trust") == "trusted_local":
            raise CaseMessageError("request_cannot_mint_authority")
        return body

    def _active(self, principal_id: str) -> str:
        identity = _label(principal_id, "unauthenticated")
        try:
            record = self._principals.load(identity)
        except PrincipalStoreError as exc:
            raise CaseMessageError("missing_principal") from exc
        if record.status != "active":
            raise CaseMessageError("inactive_principal")
        return record.principal_id

    def _now(self) -> int:
        value = self._clock()
        if type(value) is not int:
            raise CaseMessageError("clock")
        return value

    @contextmanager
    def _locked(self) -> Iterator[None]:
        with _FileLock(self._lock_path):
            yield


def _membership_code(code: str) -> str:
    if code in {"missing_case", "actor_not_owner", "tenant_mismatch", "resource_mismatch", "missing_principal", "case_mismatch", "actor_not_member"}:
        return "missing_case"
    return code


def message_http_status(code: str) -> int:
    if code in {"missing_case", "missing_thread", "missing_message", "missing_grant", "missing_principal"}:
        return 404
    if code in {"revision_conflict", "replay_mismatch", "membership_revision_conflict"}:
        return 409
    if code in {"unauthenticated", "request_body"}:
        return 401
    if code == "message_unavailable":
        return 503
    return 403
