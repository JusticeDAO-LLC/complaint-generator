"""Append-only encrypted case audit history.

Each event records an action, the authenticated actor, the case resource,
the case revision, a grant reference, and a purpose reference. The canonical
encrypted owner remains the case tenant. The actor principal is stored
separately and is never written into artifact associated data as the owner.

Envelopes are sealed with the injected case-audit key. Replay of the same
idempotency key returns the original event and does not append. Operational
logs, in-app notifications, and error payloads carry only those references.
Complaint text and key material are rejected and are not copied into those
surfaces.

Scoped export is a separate operation from append. It releases only an
explicit field and artifact allowlist for one case, one actor, one purpose,
and the current grant. The stored bundle stays sealed. Plaintext is returned
only when the caller sets user decryption explicitly. Path reads, forged
roles, mixed-tenant batches, stale grants, and direct downloads are denied.
History is not rewritten after revocation, and plaintext a caller already
holds is not erased.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
import re
import tempfile
import uuid
from urllib.parse import unquote
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from applications.case_access import OWNER_ACTIONS
from applications.case_directory import CaseDirectory, CaseDirectoryError, CaseNamespace
from applications.case_membership import CaseMembershipError, CaseMembershipStore
from applications.principal_store import PrincipalStore, PrincipalStoreError
from integrations.private_collaboration import CaseResourceKeyGrantError, CaseResourceKeyGrantStore
from integrations.private_storage import (
    PrivateArtifactBinding,
    PrivateArtifactBindingError,
    PrivateArtifactIntegrityError,
    assert_access_matches_binding,
    open_private_artifact,
    seal_private_artifact,
)

TASK_ID = "CIMP-GUI-13"
SCHEMA_VERSION = 1
ARTIFACT_KIND = "case-audit-event"
GRANT_KINDS = frozenset({"owner", "membership", "key"})
PURPOSE_RE = re.compile(r"purpose:[a-z0-9][a-z0-9._-]{0,63}\Z")
LIMITATIONS = (
    "history_is_append_only",
    "revocation_does_not_rewrite_recorded_events",
    "operational_surfaces_omit_complaint_text_and_key_material",
    "actor_is_distinct_from_canonical_encrypted_owner",
    "exports_require_current_grant_purpose_and_explicit_fields",
)
EXPORT_TASK_ID = "CIMP-GUI-52"
EXPORT_ARTIFACT_KIND = "case-audit-export"
OPERATIONAL_EXPORT_CASE_ID = "operational-audit"
OPERATIONAL_EXPORT_TENANT_ID = "operational"
USER_DECRYPT_CONFIRMATION = "user-decrypted"
AUTHORIZED_EXPORT_FIELDS = frozenset({
    "event_id",
    "sequence",
    "action",
    "actor_principal_id",
    "resource_id",
    "revision",
    "grant_id",
    "grant_kind",
    "grant_version",
    "purpose_ref",
    "tenant_id",
    "case_id",
})
OPERATIONAL_EXPORT_FIELDS = frozenset({
    "at",
    "actor_principal_id",
    "action",
    "subject_principal_id",
    "detail",
    "revision",
})
ROLE_CLAIM_FIELDS = frozenset({
    "role",
    "roles",
    "staff_role",
    "is_admin",
    "is_staff",
    "is_lawyer",
})
EXPORT_LIMITATIONS = (
    "private_export_stays_encrypted_until_explicit_user_decryption",
    "only_named_fields_and_artifacts_are_released",
    "export_requires_case_actor_purpose_and_current_grant",
    "direct_download_is_denied",
    "actor_is_distinct_from_canonical_encrypted_owner",
)
SENSITIVE_FIELDS = frozenset({
    "complaint",
    "complaint_text",
    "narrative",
    "evidence",
    "message",
    "messages",
    "plaintext",
    "body",
    "note",
    "notes",
    "summary",
    "key",
    "data_key",
    "wrap_key",
    "master_key",
    "private_key",
    "browser_key",
    "raw_key",
    "ciphertext",
    "wrapped_ciphertext",
    "nonce",
    "wrapped",
    "wrapped_data_key",
    "credentials",
    "credential",
    "password",
    "passphrase",
    "secret",
    "token",
    "trusted_local",
})
REQUEST_FIELDS = frozenset({
    "actor_principal_id",
    "case_id",
    "tenant_id",
    "resource_id",
    "action",
    "expected_revision",
    "grant_id",
    "grant_kind",
    "purpose_ref",
    "idempotency_key",
    "membership_version",
})


class CaseAuditError(Exception):
    """Fail-closed audit error. ``code`` is the only public message."""

    def __init__(self, code: str) -> None:
        self.code = str(code)
        super().__init__(self.code)


def audit_export_session_verifier(request: Any) -> Callable[[], None]:
    """Reprove the actual received browser cookie; never accept body authority."""
    from applications.browser_sessions import (
        BoundBrowserSession, BrowserSessionError, BrowserSessionService, SESSION_COOKIE,
    )
    sessions = getattr(request.app.state, "browser_sessions", None)
    bound = getattr(request.state, "browser_principal", None)
    if not isinstance(sessions, BrowserSessionService) or not isinstance(bound, BoundBrowserSession):
        raise CaseAuditError("unauthenticated")
    token = request.cookies.get(SESSION_COOKIE)
    def verify() -> None:
        try:
            current = sessions.authenticate_token(token)
        except BrowserSessionError as exc:
            raise CaseAuditError("unauthenticated") from exc
        if current != bound:
            raise CaseAuditError("unauthenticated")
    return verify


@dataclass(frozen=True)
class _CanonicalAccess:
    trust: str
    principal_id: str
    case_id: str


@dataclass(frozen=True)
class CaseAuditEvent:
    """One sealed history entry. Fields are references, not case content."""

    event_id: str
    sequence: int
    action: str
    actor_principal_id: str
    resource_id: str
    revision: int
    resource_revision: str
    grant_id: str
    grant_kind: str
    grant_version: int
    membership_version: int
    membership_grant_id: str
    purpose_ref: str
    tenant_id: str
    case_id: str
    canonical_owner_principal_id: str
    actor_is_encrypted_owner: bool
    previous_digest: str
    idempotency_key: str

    def public_view(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "sequence": self.sequence,
            "action": self.action,
            "actor_principal_id": self.actor_principal_id,
            "resource_id": self.resource_id,
            "revision": self.revision,
            "resource_revision": self.resource_revision,
            "grant_id": self.grant_id,
            "grant_kind": self.grant_kind,
            "grant_version": self.grant_version,
            "membership_version": self.membership_version,
            "membership_grant_id": self.membership_grant_id,
            "purpose_ref": self.purpose_ref,
            "tenant_id": self.tenant_id,
            "case_id": self.case_id,
            "canonical_owner_principal_id": self.canonical_owner_principal_id,
            "actor_is_encrypted_owner": self.actor_is_encrypted_owner,
            "schema_version": SCHEMA_VERSION,
            "limitations": list(LIMITATIONS),
        }


def owner_grant_reference(tenant_id: str) -> str:
    """Stable grant reference for the canonical owner binding, not the actor."""

    return "owner-binding:" + _label(tenant_id, "tenant_id")


def operational_log(event: CaseAuditEvent) -> dict[str, Any]:
    """Log record without complaint text or key material."""

    if not isinstance(event, CaseAuditEvent):
        raise CaseAuditError("audit_event")
    return {
        "record": "case_audit",
        "event_id": event.event_id,
        "sequence": event.sequence,
        "action": event.action,
        "actor_principal_id": event.actor_principal_id,
        "resource_id": event.resource_id,
        "revision": event.revision,
        "grant_id": event.grant_id,
        "grant_kind": event.grant_kind,
        "purpose_ref": event.purpose_ref,
    }


def notification_payload(event: CaseAuditEvent) -> dict[str, Any]:
    """In-app notification that names the audit references only."""

    if not isinstance(event, CaseAuditEvent):
        raise CaseAuditError("audit_event")
    return {
        "channel": "in_app",
        "template": "case_audit_recorded",
        "event_id": event.event_id,
        "action": event.action,
        "actor_principal_id": event.actor_principal_id,
        "resource_id": event.resource_id,
        "revision": event.revision,
        "grant_id": event.grant_id,
        "purpose_ref": event.purpose_ref,
    }


def refuse_direct_audit_download(path: str = "") -> None:
    """Every direct-download entry point fails closed. The path is not opened."""

    del path
    raise CaseAuditError("direct_download_denied")


def path_targets_audit_download(path: str, query: str = "") -> bool:
    """True when a URL or query asks to read an audit export as a file."""

    normalized = str(path or "").replace("\\", "/").rstrip("/")
    if normalized.startswith("/api/cases/audit-exports/") or normalized.startswith("/api/admin/audit/exports"):
        return True
    if normalized != "/api/documents/download":
        return False
    raw = unquote(str(query or "")).replace("\\", "/")
    return ".." in raw or "audit-export" in raw or "/exports/" in raw


def error_payload(error: BaseException) -> dict[str, str]:
    """Machine reason only. Exception text is not copied."""

    if isinstance(error, CaseAuditError) and error.code.isidentifier():
        return {"code": error.code}
    return {"code": "audit_failed"}


def _opaque_id() -> str:
    return uuid.uuid4().hex


def _label(value: str, code: str) -> str:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise CaseAuditError(code)
    if any(char in value for char in ("\x00", "\n", "\r", "/", "\\")):
        raise CaseAuditError(code)
    if len(value) > 200:
        raise CaseAuditError(code)
    return value


def _same_request(
    event: CaseAuditEvent,
    *,
    actor_principal_id: str,
    case_id: str,
    tenant_id: str,
    resource_id: str,
    action: str,
    expected_revision: int,
    grant_id: str,
    grant_kind: str,
    purpose_ref: str,
    idempotency_key: str,
    membership_version: int | None,
) -> bool:
    if membership_version is None:
        version_ok = event.grant_kind == "owner" and event.membership_version == 0
    else:
        version_ok = event.membership_version == membership_version
    return (
        version_ok
        and event.actor_principal_id == actor_principal_id
        and event.case_id == case_id
        and event.tenant_id == tenant_id
        and event.resource_id == resource_id
        and event.action == action
        and event.revision == expected_revision
        and event.grant_id == grant_id
        and event.grant_kind == grant_kind
        and event.purpose_ref == purpose_ref
        and event.idempotency_key == idempotency_key
    )


def _fingerprint(event: CaseAuditEvent) -> str:
    payload = {
        "action": event.action,
        "actor_principal_id": event.actor_principal_id,
        "resource_id": event.resource_id,
        "revision": event.revision,
        "resource_revision": event.resource_revision,
        "grant_id": event.grant_id,
        "grant_kind": event.grant_kind,
        "grant_version": event.grant_version,
        "membership_version": event.membership_version,
        "membership_grant_id": event.membership_grant_id,
        "purpose_ref": event.purpose_ref,
        "tenant_id": event.tenant_id,
        "case_id": event.case_id,
        "idempotency_key": event.idempotency_key,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _document_digest(document: Mapping[str, Any]) -> str:
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class CaseAuditStore:
    """File-backed append-only audit log for one injected data key."""

    def __init__(
        self,
        root: str | Path,
        *,
        key: bytes,
        key_id: str,
        principals: PrincipalStore,
        cases: CaseDirectory,
        memberships: CaseMembershipStore,
        key_grants: CaseResourceKeyGrantStore,
    ) -> None:
        if not isinstance(key, (bytes, bytearray)) or isinstance(key, memoryview) or len(bytes(key)) != 32:
            raise CaseAuditError("key_material")
        if not isinstance(principals, PrincipalStore) or not isinstance(cases, CaseDirectory):
            raise CaseAuditError("authority_owners")
        if not isinstance(memberships, CaseMembershipStore):
            raise CaseAuditError("membership_owner")
        if not isinstance(key_grants, CaseResourceKeyGrantStore):
            raise CaseAuditError("key_grant_owner")
        self._key = bytes(key)
        self._key_id = _label(key_id, "key_id")
        self._principals = principals
        self._cases = cases
        self._memberships = memberships
        self._key_grants = key_grants
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        os.chmod(self._root, 0o700)
        self._lock_path = self._root / ".lock"
        self._lock_path.touch(mode=0o600)
        (self._root / "events").mkdir(mode=0o700, exist_ok=True)
        (self._root / "idem").mkdir(mode=0o700, exist_ok=True)
        (self._root / "exports").mkdir(mode=0o700, exist_ok=True)
        self._logs: list[dict[str, Any]] = []
        self._notifications: list[dict[str, Any]] = []
        self._errors: list[dict[str, str]] = []

    def record(
        self,
        *,
        actor_principal_id: str,
        case_id: str,
        tenant_id: str,
        resource_id: str,
        action: str,
        expected_revision: int,
        grant_id: str,
        grant_kind: str,
        purpose_ref: str,
        idempotency_key: str,
        membership_version: int | None = None,
    ) -> CaseAuditEvent:
        """Append one event, or return the original event when the key replays."""

        try:
            event = self._record(
                actor_principal_id=actor_principal_id,
                case_id=case_id,
                tenant_id=tenant_id,
                resource_id=resource_id,
                action=action,
                expected_revision=expected_revision,
                grant_id=grant_id,
                grant_kind=grant_kind,
                purpose_ref=purpose_ref,
                idempotency_key=idempotency_key,
                membership_version=membership_version,
            )
        except CaseAuditError as exc:
            self._errors.append(error_payload(exc))
            raise
        return event

    def record_from_request(self, body: Mapping[str, Any]) -> CaseAuditEvent:
        """Record from a mapping. Sensitive fields and unknown keys are refused."""

        try:
            if not isinstance(body, Mapping):
                raise CaseAuditError("request_body")
            self._reject_sensitive(body)
            unexpected = set(body) - REQUEST_FIELDS
            if unexpected:
                raise CaseAuditError("unknown_field")
            version = body.get("membership_version")
            if version is not None and type(version) is not int:
                raise CaseAuditError("grant_version")
            revision = body.get("expected_revision")
            if type(revision) is not int:
                raise CaseAuditError("revision_conflict")
        except CaseAuditError as exc:
            self._errors.append(error_payload(exc))
            raise
        return self.record(
            actor_principal_id=str(body.get("actor_principal_id") or ""),
            case_id=str(body.get("case_id") or ""),
            tenant_id=str(body.get("tenant_id") or ""),
            resource_id=str(body.get("resource_id") or ""),
            action=str(body.get("action") or ""),
            expected_revision=revision,
            grant_id=str(body.get("grant_id") or ""),
            grant_kind=str(body.get("grant_kind") or ""),
            purpose_ref=str(body.get("purpose_ref") or ""),
            idempotency_key=str(body.get("idempotency_key") or ""),
            membership_version=version,
        )

    def history(
        self,
        *,
        actor_principal_id: str,
        case_id: str,
        tenant_id: str,
        resource_id: str,
        grant_id: str,
        grant_kind: str,
        expected_revision: int,
        membership_version: int | None = None,
    ) -> tuple[CaseAuditEvent, ...]:
        """Read the chain. Authorization is checked before any event is returned."""

        try:
            actor = self._active(actor_principal_id)
            case_label = _label(case_id, "case_id")
            self._authorize_read(
                actor_id=actor.principal_id,
                case_id=case_label,
                tenant_id=_label(tenant_id, "tenant_id"),
                resource_id=_label(resource_id, "resource_id"),
                grant_id=_label(grant_id, "grant_id"),
                grant_kind=self._grant_kind(grant_kind),
                expected_revision=expected_revision,
                membership_version=membership_version,
            )
            with self._locked():
                return self._chain(case_label)
        except CaseAuditError as exc:
            self._errors.append(error_payload(exc))
            raise

    def operational_logs(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._logs)

    def notifications(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._notifications)

    def error_payloads(self) -> tuple[dict[str, str], ...]:
        return tuple(self._errors)

    def direct_download(self, path: str = "") -> None:
        """No filesystem path, query path, or export id is a download."""

        raise CaseAuditError("direct_download_denied")

    def export_from_request(
        self,
        body: Mapping[str, Any],
        *,
        session_roles: Sequence[str] | None = None,
        verify_access: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        """Export one case's audit references, or reopen that sealed bundle.

        ``session_roles`` is the server session, not a role the body may mint.
        """

        try:
            return self._export_case(body, session_roles=session_roles, verify_access=verify_access)
        except CaseAuditError as exc:
            self._errors.append(error_payload(exc))
            raise

    def export_operational_from_request(
        self,
        body: Mapping[str, Any],
        *,
        session_roles: Sequence[str],
        events: Sequence[Mapping[str, Any]],
        audit_reader: bool,
        verify_access: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        """Export operational audit rows. Case envelopes are not opened."""

        try:
            if audit_reader is not True:
                raise CaseAuditError("audit_right_required")
            return self._export_operational(body, session_roles=session_roles, events=events, verify_access=verify_access)
        except CaseAuditError as exc:
            self._errors.append(error_payload(exc))
            raise

    def _export_case(self, body: Mapping[str, Any], *, session_roles: Sequence[str] | None,
                     verify_access: Callable[[], None] | None = None) -> dict[str, Any]:
        parsed = _parse_export_body(body)
        actor = self._active(parsed["actor_principal_id"])
        _reject_forged_role(actor, parsed["role_claims"], session_roles)
        kind = self._grant_kind(parsed["grant_kind"])
        try:
            bound = self._resolve_grant(
                actor_id=actor.principal_id,
                case_id=parsed["case_id"],
                tenant_id=parsed["tenant_id"],
                resource_id=parsed["resource_id"],
                action="case.read",
                expected_revision=parsed["expected_revision"],
                grant_id=parsed["grant_id"],
                grant_kind=kind,
                membership_version=parsed["membership_version"],
                require_action=True,
            )
        except CaseAuditError as exc:
            if exc.code == "revision_conflict" and kind != "owner":
                raise CaseAuditError("stale_grant") from exc
            raise
        if parsed["grant_version"] != bound["grant_version"]:
            raise CaseAuditError("stale_grant")
        def admit() -> None:
            if verify_access is not None:
                if verify_access() is False:
                    raise CaseAuditError("unauthenticated")
            current = self._active(actor.principal_id)
            _reject_forged_role(current, parsed["role_claims"], session_roles)
            fresh = self._resolve_grant(
                actor_id=current.principal_id, case_id=parsed["case_id"],
                tenant_id=parsed["tenant_id"], resource_id=parsed["resource_id"], action="case.read",
                expected_revision=parsed["expected_revision"], grant_id=parsed["grant_id"],
                grant_kind=kind, membership_version=parsed["membership_version"], require_action=True)
            if fresh != bound:
                raise CaseAuditError("stale_grant")
        _reject_mixed_tenant(parsed["cases"], bound["tenant_id"], bound["case_id"])
        if parsed["export_id"] is not None:
            return self._reopen_export(
                parsed,
                actor_id=actor.principal_id,
                tenant_id=bound["tenant_id"],
                case_id=bound["case_id"],
                verify_access=admit,
            )
        with self._locked():
            chain = self._chain(bound["case_id"])
        selected = _select_case_artifacts(
            chain,
            tenant_id=bound["tenant_id"],
            case_id=bound["case_id"],
            purpose_ref=parsed["purpose_ref"],
            artifact_ids=parsed["artifact_ids"],
        )
        records = [{name: record[name] for name in parsed["fields"]} for record in selected]
        return self._seal_export(
            parsed,
            kind="case",
            actor_id=actor.principal_id,
            tenant_id=bound["tenant_id"],
            case_id=bound["case_id"],
            resource_id=bound["resource_id"],
            grant_kind=kind,
            grant_version=bound["grant_version"],
            records=records,
            artifact_ids=tuple(record["event_id"] for record in selected),
            verify_access=admit,
        )

    def _export_operational(
        self,
        body: Mapping[str, Any],
        *,
        session_roles: Sequence[str],
        events: Sequence[Mapping[str, Any]],
        verify_access: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        parsed = _parse_export_body(body, operational=True)
        actor = self._active(parsed["actor_principal_id"])
        _reject_forged_role(actor, parsed["role_claims"], session_roles)
        if "operational_admin" not in actor.roles:
            raise CaseAuditError("forged_role")
        expected_grant = "audit-right:" + actor.principal_id
        if parsed["grant_id"] != expected_grant or parsed["grant_kind"] != "audit_right":
            raise CaseAuditError("grant_mismatch")
        if parsed["grant_version"] != actor.revision:
            raise CaseAuditError("stale_grant")
        def admit() -> None:
            if verify_access is not None:
                if verify_access() is False:
                    raise CaseAuditError("unauthenticated")
            current = self._active(actor.principal_id)
            _reject_forged_role(current, parsed["role_claims"], session_roles)
            if current.revision != actor.revision or "operational_admin" not in current.roles:
                raise CaseAuditError("stale_grant")
        if parsed["tenant_id"] != OPERATIONAL_EXPORT_TENANT_ID:
            raise CaseAuditError("mixed_tenant_batch")
        _reject_mixed_tenant(parsed["cases"], OPERATIONAL_EXPORT_TENANT_ID, OPERATIONAL_EXPORT_CASE_ID)
        if parsed["export_id"] is not None:
            return self._reopen_export(
                parsed,
                actor_id=actor.principal_id,
                tenant_id=OPERATIONAL_EXPORT_TENANT_ID,
                case_id=OPERATIONAL_EXPORT_CASE_ID,
                verify_access=admit,
            )
        rows = []
        for event in events:
            if not isinstance(event, Mapping):
                raise CaseAuditError("audit_event")
            if any(name in event for name in SENSITIVE_FIELDS):
                raise CaseAuditError("sensitive_field")
            rows.append({name: event[name] for name in parsed["fields"] if name in event})
        return self._seal_export(
            parsed,
            kind="operational",
            actor_id=actor.principal_id,
            tenant_id=OPERATIONAL_EXPORT_TENANT_ID,
            case_id=OPERATIONAL_EXPORT_CASE_ID,
            resource_id="operational-audit",
            grant_kind="audit_right",
            grant_version=actor.revision,
            records=rows,
            artifact_ids=tuple(parsed["artifact_ids"]),
            verify_access=admit,
        )

    def _seal_export(
        self,
        parsed: Mapping[str, Any],
        *,
        kind: str,
        actor_id: str,
        tenant_id: str,
        case_id: str,
        resource_id: str,
        grant_kind: str,
        grant_version: int,
        records: list[dict[str, Any]],
        artifact_ids: tuple[str, ...],
        verify_access: Callable[[], None],
    ) -> dict[str, Any]:
        export_id = _opaque_id()
        document = {
            "schema_version": SCHEMA_VERSION,
            "task_id": EXPORT_TASK_ID,
            "kind": kind,
            "export_id": export_id,
            "purpose_ref": parsed["purpose_ref"],
            "fields": list(parsed["fields"]),
            "artifact_ids": list(artifact_ids),
            "records": records,
            "grant_id": parsed["grant_id"],
            "grant_kind": grant_kind,
            "grant_version": grant_version,
            "actor_principal_id": actor_id,
            "tenant_id": tenant_id,
            "case_id": case_id,
            "resource_id": resource_id,
            "expected_revision": parsed["expected_revision"],
            "membership_version": parsed["membership_version"],
            "actor_is_encrypted_owner": False,
        }
        if actor_id == tenant_id:
            raise CaseAuditError("owner_impersonation")
        payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        binding = _export_binding(tenant_id, case_id, export_id)
        access = _CanonicalAccess("authenticated", tenant_id, case_id)
        assert_access_matches_binding(access, binding)
        envelope = seal_private_artifact(payload, binding=binding, key=self._key, key_id=self._key_id)
        path = self._export_path(export_id)
        if path.exists() or path.is_symlink():
            raise CaseAuditError("audit_append_conflict")
        descriptor, temporary_name = tempfile.mkstemp(prefix=".export-", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            view = envelope
            while view:
                wrote = os.write(descriptor, view)
                if wrote <= 0:
                    raise CaseAuditError("audit_write")
                view = view[wrote:]
            os.fsync(descriptor)
            # No ciphertext bundle becomes visible after a completed cutoff
            # during encryption or staging. Linking also refuses replacement.
            verify_access()
            os.link(temporary, path, follow_symlinks=False)
        finally:
            os.close(descriptor)
            temporary.unlink(missing_ok=True)
        payload = _export_view(document, envelope, user_decrypted=parsed["user_decrypt"])
        verify_access()
        return payload

    def _reopen_export(
        self,
        parsed: Mapping[str, Any],
        *,
        actor_id: str,
        tenant_id: str,
        case_id: str,
        verify_access: Callable[[], None],
    ) -> dict[str, Any]:
        export_id = parsed["export_id"]
        path = self._export_path(export_id)
        if not path.is_file() or path.is_symlink():
            raise CaseAuditError("missing_export")
        binding = _export_binding(tenant_id, case_id, export_id)
        access = _CanonicalAccess("authenticated", tenant_id, case_id)
        try:
            assert_access_matches_binding(access, binding)
            envelope = path.read_bytes()
            plaintext = open_private_artifact(
                envelope,
                binding=binding,
                key=self._key,
                expected_key_id=self._key_id,
            )
        except (PrivateArtifactIntegrityError, PrivateArtifactBindingError) as exc:
            raise CaseAuditError("integrity") from exc
        document = json.loads(plaintext.decode("utf-8"))
        if document.get("actor_principal_id") != actor_id or document.get("tenant_id") != tenant_id:
            raise CaseAuditError("binding_mismatch")
        if document.get("case_id") != case_id or document.get("actor_is_encrypted_owner") is not False:
            raise CaseAuditError("binding_mismatch")
        if document.get("purpose_ref") != parsed["purpose_ref"] or document.get("grant_id") != parsed["grant_id"]:
            raise CaseAuditError("grant_mismatch")
        payload = _export_view(document, envelope, user_decrypted=parsed["user_decrypt"])
        verify_access()
        return payload

    def _export_path(self, export_id: str) -> Path:
        label = _label(export_id, "traversal")
        if label != export_id or ".." in label or "/" in label or "\\" in label:
            raise CaseAuditError("traversal")
        path = self._root / "exports" / (label + ".envelope")
        if path.is_symlink():
            raise CaseAuditError("traversal")
        return path

    def _record(
        self,
        *,
        actor_principal_id: str,
        case_id: str,
        tenant_id: str,
        resource_id: str,
        action: str,
        expected_revision: int,
        grant_id: str,
        grant_kind: str,
        purpose_ref: str,
        idempotency_key: str,
        membership_version: int | None,
    ) -> CaseAuditEvent:
        actor = self._active(actor_principal_id)
        kind = self._grant_kind(grant_kind)
        requested = _label(action, "action_not_permitted")
        purpose = self._purpose(purpose_ref)
        key_name = _label(idempotency_key, "idempotency_key")
        case_label = _label(case_id, "case_id")
        tenant_label = _label(tenant_id, "tenant_id")
        resource_label = _label(resource_id, "resource_id")
        grant_label = _label(grant_id, "grant_id")
        if type(expected_revision) is not int or expected_revision < 1:
            raise CaseAuditError("revision_conflict")
        with self._locked():
            prior = self._idem_pointer(key_name)
            if prior is not None:
                existing = self._load(prior["case_id"], prior["sequence"], prior["event_id"])
                if not _same_request(
                    existing,
                    actor_principal_id=actor.principal_id,
                    case_id=case_label,
                    tenant_id=tenant_label,
                    resource_id=resource_label,
                    action=requested,
                    expected_revision=expected_revision,
                    grant_id=grant_label,
                    grant_kind=kind,
                    purpose_ref=purpose,
                    idempotency_key=key_name,
                    membership_version=membership_version,
                ):
                    raise CaseAuditError("replay_mismatch")
                return existing
        bound = self._resolve_grant(
            actor_id=actor.principal_id,
            case_id=case_label,
            tenant_id=tenant_label,
            resource_id=resource_label,
            action=requested,
            expected_revision=expected_revision,
            grant_id=grant_label,
            grant_kind=kind,
            membership_version=membership_version,
            require_action=True,
        )
        draft = CaseAuditEvent(
            event_id="",
            sequence=0,
            action=requested,
            actor_principal_id=actor.principal_id,
            resource_id=bound["resource_id"],
            revision=bound["revision"],
            resource_revision=bound["resource_revision"],
            grant_id=bound["grant_id"],
            grant_kind=kind,
            grant_version=bound["grant_version"],
            membership_version=bound["membership_version"],
            membership_grant_id=bound["membership_grant_id"],
            purpose_ref=purpose,
            tenant_id=bound["tenant_id"],
            case_id=bound["case_id"],
            canonical_owner_principal_id=bound["canonical_owner_principal_id"],
            actor_is_encrypted_owner=False,
            previous_digest="",
            idempotency_key=key_name,
        )
        with self._locked():
            prior = self._idem_pointer(key_name)
            if prior is not None:
                existing = self._load(prior["case_id"], prior["sequence"], prior["event_id"])
                if not _same_request(
                    existing,
                    actor_principal_id=actor.principal_id,
                    case_id=case_label,
                    tenant_id=tenant_label,
                    resource_id=resource_label,
                    action=requested,
                    expected_revision=expected_revision,
                    grant_id=grant_label,
                    grant_kind=kind,
                    purpose_ref=purpose,
                    idempotency_key=key_name,
                    membership_version=membership_version,
                ):
                    raise CaseAuditError("replay_mismatch")
                return existing
            chain = self._chain(bound["case_id"])
            sequence = len(chain) + 1
            previous = "0" * 64 if not chain else _document_digest(_event_document(chain[-1]))
            event = CaseAuditEvent(
                event_id=_opaque_id(),
                sequence=sequence,
                action=draft.action,
                actor_principal_id=draft.actor_principal_id,
                resource_id=draft.resource_id,
                revision=draft.revision,
                resource_revision=draft.resource_revision,
                grant_id=draft.grant_id,
                grant_kind=draft.grant_kind,
                grant_version=draft.grant_version,
                membership_version=draft.membership_version,
                membership_grant_id=draft.membership_grant_id,
                purpose_ref=draft.purpose_ref,
                tenant_id=draft.tenant_id,
                case_id=draft.case_id,
                canonical_owner_principal_id=draft.canonical_owner_principal_id,
                actor_is_encrypted_owner=False,
                previous_digest=previous,
                idempotency_key=key_name,
            )
            if event.actor_principal_id == event.canonical_owner_principal_id:
                raise CaseAuditError("owner_impersonation")
            self._seal(event)
            self._write_idem(key_name, event)
        self._logs.append(operational_log(event))
        self._notifications.append(notification_payload(event))
        return event

    def _resolve_grant(
        self,
        *,
        actor_id: str,
        case_id: str,
        tenant_id: str,
        resource_id: str,
        action: str,
        expected_revision: int,
        grant_id: str,
        grant_kind: str,
        membership_version: int | None,
        require_action: bool,
    ) -> dict[str, Any]:
        if grant_kind == "owner":
            case = self._select_owner_case(actor_id, case_id)
            self._expect_case(case, tenant_id=tenant_id, resource_id=resource_id, expected_revision=expected_revision)
            if actor_id == case.tenant_id:
                raise CaseAuditError("owner_impersonation")
            if grant_id != owner_grant_reference(case.tenant_id):
                raise CaseAuditError("grant_mismatch")
            if require_action and action not in OWNER_ACTIONS:
                raise CaseAuditError("action_not_permitted")
            if membership_version is not None:
                raise CaseAuditError("grant_mismatch")
            return {
                "case_id": case.case_id,
                "tenant_id": case.tenant_id,
                "resource_id": case.resource_id,
                "revision": case.revision,
                "resource_revision": str(case.revision),
                "grant_id": grant_id,
                "grant_version": 0,
                "membership_version": 0,
                "membership_grant_id": "",
                "canonical_owner_principal_id": case.tenant_id,
            }
        if grant_kind == "membership":
            if type(membership_version) is not int:
                raise CaseAuditError("grant_version")
            decision = self._authorize_membership(
                actor_id=actor_id,
                grant_id=grant_id,
                tenant_id=tenant_id,
                case_id=case_id,
                resource_id=resource_id,
                action=action,
                expected_version=membership_version,
            )
            if decision.version != membership_version or decision.revision_case != expected_revision:
                raise CaseAuditError("revision_conflict")
            return {
                "case_id": decision.case_id,
                "tenant_id": decision.tenant_id,
                "resource_id": decision.resource_id,
                "revision": expected_revision,
                "resource_revision": str(expected_revision),
                "grant_id": decision.grant_id,
                "grant_version": decision.version,
                "membership_version": decision.version,
                "membership_grant_id": decision.grant_id,
                "canonical_owner_principal_id": decision.canonical_owner_principal_id,
            }
        loaded = self._load_key_grant(grant_id)
        if loaded.status != "active":
            raise CaseAuditError("grant_revoked")
        if loaded.recipient_principal_id != actor_id:
            raise CaseAuditError("actor_not_recipient")
        if loaded.case_id != case_id or loaded.tenant_id != tenant_id or loaded.resource_id != resource_id:
            raise CaseAuditError("grant_mismatch")
        if type(membership_version) is not int or membership_version != loaded.membership_version:
            raise CaseAuditError("grant_version")
        if loaded.version < 1:
            raise CaseAuditError("grant_mismatch")
        decision = self._authorize_membership(
            actor_id=actor_id,
            grant_id=loaded.membership_grant_id,
            tenant_id=tenant_id,
            case_id=case_id,
            resource_id=resource_id,
            action=action,
            expected_version=membership_version,
        )
        if expected_revision != decision.revision_case:
            raise CaseAuditError("revision_conflict")
        return {
            "case_id": loaded.case_id,
            "tenant_id": loaded.tenant_id,
            "resource_id": loaded.resource_id,
            "revision": expected_revision,
            "resource_revision": loaded.artifact_revision,
            "grant_id": loaded.key_grant_id,
            "grant_version": loaded.version,
            "membership_version": membership_version,
            "membership_grant_id": loaded.membership_grant_id,
            "canonical_owner_principal_id": loaded.canonical_owner_principal_id,
        }

    def _authorize_read(
        self,
        *,
        actor_id: str,
        case_id: str,
        tenant_id: str,
        resource_id: str,
        grant_id: str,
        grant_kind: str,
        expected_revision: int,
        membership_version: int | None,
    ) -> None:
        self._resolve_grant(
            actor_id=actor_id,
            case_id=case_id,
            tenant_id=tenant_id,
            resource_id=resource_id,
            action="case.read",
            expected_revision=expected_revision,
            grant_id=grant_id,
            grant_kind=grant_kind,
            membership_version=membership_version,
            require_action=True,
        )

    def _authorize_membership(
        self,
        *,
        actor_id: str,
        grant_id: str,
        tenant_id: str,
        case_id: str,
        resource_id: str,
        action: str,
        expected_version: int,
    ) -> Any:
        try:
            decision = self._memberships.authorize(
                actor_principal_id=actor_id,
                grant_id=grant_id,
                tenant_id=tenant_id,
                case_id=case_id,
                resource_id=resource_id,
                action=action,
                expected_version=expected_version,
            )
        except CaseMembershipError as exc:
            raise CaseAuditError(exc.code if exc.code.isidentifier() else "membership_required") from exc
        grant = self._load_membership(grant_id)
        if type(grant.case_revision) is not int or grant.case_revision < 1:
            raise CaseAuditError("revision_conflict")
        return _MembershipView(
            grant_id=decision.grant_id,
            version=decision.version,
            case_id=decision.case_id,
            tenant_id=decision.tenant_id,
            resource_id=decision.resource_id,
            canonical_owner_principal_id=decision.canonical_owner_principal_id,
            revision_case=grant.case_revision,
        )

    def _load_membership(self, grant_id: str) -> Any:
        try:
            return self._memberships.load(grant_id)
        except CaseMembershipError as exc:
            raise CaseAuditError(exc.code if exc.code.isidentifier() else "missing_grant") from exc

    def _load_key_grant(self, grant_id: str) -> Any:
        try:
            return self._key_grants.load(grant_id)
        except CaseResourceKeyGrantError as exc:
            raise CaseAuditError(exc.code if exc.code.isidentifier() else "missing_grant") from exc

    def _select_owner_case(self, actor_id: str, case_id: str) -> CaseNamespace:
        try:
            case = self._cases.select_case(actor_principal_id=actor_id, case_id=case_id)
        except CaseDirectoryError as exc:
            raise CaseAuditError(exc.code if exc.code.isidentifier() else "missing_case") from exc
        if case.owner_principal_id != actor_id:
            raise CaseAuditError("actor_not_owner")
        return case

    def _expect_case(
        self,
        case: CaseNamespace,
        *,
        tenant_id: str,
        resource_id: str,
        expected_revision: int,
    ) -> None:
        if tenant_id != case.tenant_id:
            raise CaseAuditError("tenant_mismatch")
        if resource_id != case.resource_id:
            raise CaseAuditError("resource_mismatch")
        if expected_revision != case.revision:
            raise CaseAuditError("revision_conflict")

    def _active(self, principal_id: str) -> Any:
        try:
            record = self._principals.load(_label(principal_id, "actor"))
        except (PrincipalStoreError, CaseAuditError) as exc:
            code = getattr(exc, "code", "missing_principal")
            raise CaseAuditError(code if isinstance(code, str) and code.isidentifier() else "missing_principal") from exc
        if record.status != "active":
            raise CaseAuditError("inactive_principal")
        if record.principal_id == "":
            raise CaseAuditError("missing_principal")
        return record

    def _grant_kind(self, value: str) -> str:
        kind = _label(value, "grant_kind")
        if kind not in GRANT_KINDS:
            raise CaseAuditError("grant_kind")
        return kind

    def _purpose(self, value: str) -> str:
        purpose = _label(value, "purpose_ref")
        if PURPOSE_RE.fullmatch(purpose) is None:
            raise CaseAuditError("purpose_ref")
        return purpose

    def _reject_sensitive(self, body: Mapping[str, Any]) -> None:
        for name, value in body.items():
            if not isinstance(name, str) or name.lower() in SENSITIVE_FIELDS:
                raise CaseAuditError("sensitive_field")
            if isinstance(value, Mapping) or isinstance(value, (list, tuple)):
                raise CaseAuditError("sensitive_field")
            if isinstance(value, (bytes, bytearray)):
                raise CaseAuditError("sensitive_field")
            if isinstance(value, str) and (len(value) > 200 or "\n" in value or "\x00" in value):
                raise CaseAuditError("sensitive_field")

    def _chain(self, case_id: str) -> tuple[CaseAuditEvent, ...]:
        directory = self._event_dir(case_id)
        if not directory.is_dir():
            return ()
        sequences: list[int] = []
        for path in directory.iterdir():
            if path.is_symlink():
                raise CaseAuditError("unexpected_path")
            if not path.is_file() or not path.name.endswith(".envelope"):
                if path.name.endswith(".event") or path.name.endswith(".tenant"):
                    continue
                raise CaseAuditError("unexpected_path")
            stem = path.name[: -len(".envelope")]
            if not stem.isdigit() or stem.startswith("0"):
                raise CaseAuditError("audit_chain_broken")
            sequences.append(int(stem))
        if not sequences:
            return ()
        ordered = sorted(sequences)
        if ordered != list(range(1, ordered[-1] + 1)):
            raise CaseAuditError("audit_chain_broken")
        events: list[CaseAuditEvent] = []
        previous_digest = "0" * 64
        previous_document: dict[str, Any] | None = None
        for sequence in ordered:
            pointer = directory / f"{sequence}.event"
            tenant_path = directory / f"{sequence}.tenant"
            if not pointer.is_file() or pointer.is_symlink() or not tenant_path.is_file():
                raise CaseAuditError("audit_chain_broken")
            event_id = pointer.read_text(encoding="utf-8").strip()
            event = self._load(case_id, sequence, event_id)
            if event.sequence != sequence or event.previous_digest != previous_digest:
                raise CaseAuditError("audit_chain_broken")
            if previous_document is not None and event.previous_digest != _document_digest(previous_document):
                raise CaseAuditError("audit_chain_broken")
            document = _event_document(event)
            previous_document = document
            previous_digest = _document_digest(document)
            events.append(event)
        return tuple(events)

    def _load(self, case_id: str, sequence: int, event_id: str) -> CaseAuditEvent:
        directory = self._event_dir(case_id)
        path = directory / f"{sequence}.envelope"
        tenant_path = directory / f"{sequence}.tenant"
        if not path.is_file() or path.is_symlink() or not tenant_path.is_file() or tenant_path.is_symlink():
            raise CaseAuditError("audit_chain_broken")
        tenant_id = tenant_path.read_text(encoding="utf-8").strip()
        binding = PrivateArtifactBinding(
            tenant_id=tenant_id,
            case_id=case_id,
            artifact_kind=ARTIFACT_KIND,
            revision=str(sequence),
            principal_id=tenant_id,
        )
        access = _CanonicalAccess("authenticated", tenant_id, case_id)
        try:
            assert_access_matches_binding(access, binding)
            plaintext = open_private_artifact(
                path.read_bytes(),
                binding=binding,
                key=self._key,
                expected_key_id=self._key_id,
            )
        except (PrivateArtifactIntegrityError, PrivateArtifactBindingError) as exc:
            raise CaseAuditError("integrity") from exc
        event = _event_from_document(json.loads(plaintext.decode("utf-8")))
        if event.event_id != event_id or event.sequence != sequence:
            raise CaseAuditError("binding_mismatch")
        if event.case_id != case_id or event.tenant_id != tenant_id:
            raise CaseAuditError("binding_mismatch")
        if event.actor_principal_id == event.canonical_owner_principal_id:
            raise CaseAuditError("owner_impersonation")
        if event.actor_is_encrypted_owner:
            raise CaseAuditError("owner_impersonation")
        return event

    def _seal(self, event: CaseAuditEvent) -> None:
        binding = PrivateArtifactBinding(
            tenant_id=event.tenant_id,
            case_id=event.case_id,
            artifact_kind=ARTIFACT_KIND,
            revision=str(event.sequence),
            principal_id=event.tenant_id,
        )
        access = _CanonicalAccess("authenticated", event.tenant_id, event.case_id)
        assert_access_matches_binding(access, binding)
        payload = json.dumps(_event_document(event), sort_keys=True, separators=(",", ":")).encode("utf-8")
        envelope = seal_private_artifact(payload, binding=binding, key=self._key, key_id=self._key_id)
        directory = self._event_dir(event.case_id)
        directory.mkdir(mode=0o700, exist_ok=True)
        path = directory / f"{event.sequence}.envelope"
        if path.exists():
            raise CaseAuditError("audit_append_conflict")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
        descriptor = os.open(path, flags, 0o600)
        try:
            view = envelope
            while view:
                wrote = os.write(descriptor, view)
                view = view[wrote:]
        finally:
            os.close(descriptor)
        self._write_text(directory / f"{event.sequence}.event", event.event_id)
        self._write_text(directory / f"{event.sequence}.tenant", event.tenant_id)

    def _idem_pointer(self, key: str) -> dict[str, Any] | None:
        path = self._idem_path(key)
        if not path.is_file() or path.is_symlink():
            return None
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) != 4:
            raise CaseAuditError("replay_mismatch")
        case_id, sequence_text, event_id, actor_id = lines
        if not sequence_text.isdigit():
            raise CaseAuditError("replay_mismatch")
        return {
            "case_id": case_id,
            "sequence": int(sequence_text),
            "event_id": event_id,
            "actor_principal_id": actor_id,
        }

    def _write_idem(self, key: str, event: CaseAuditEvent) -> None:
        body = "\n".join((
            event.case_id,
            str(event.sequence),
            event.event_id,
            event.actor_principal_id,
        ))
        self._write_text(self._idem_path(key), body)

    def _idem_path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._root / "idem" / digest

    def _event_dir(self, case_id: str) -> Path:
        return self._root / "events" / case_id

    def _write_text(self, path: Path, text: str) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)

    def _locked(self):
        return _FileLock(self._lock_path)


@dataclass(frozen=True)
class _MembershipView:
    grant_id: str
    version: int
    case_id: str
    tenant_id: str
    resource_id: str
    canonical_owner_principal_id: str
    revision_case: int


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


def _reject_forged_role(actor: Any, role_claims: Mapping[str, Any], session_roles: Sequence[str] | None) -> None:
    if role_claims:
        raise CaseAuditError("forged_role")
    if session_roles is None:
        return
    if isinstance(session_roles, (str, bytes)) or not isinstance(session_roles, Sequence):
        raise CaseAuditError("forged_role")
    if tuple(session_roles) != tuple(actor.roles):
        raise CaseAuditError("forged_role")


def _reject_mixed_tenant(cases: list[dict[str, str]] | None, tenant_id: str, case_id: str) -> None:
    if cases is None:
        return
    tenants = {item["tenant_id"] for item in cases}
    if tenants != {tenant_id}:
        raise CaseAuditError("mixed_tenant_batch")
    if any(item["case_id"] != case_id for item in cases) and tenant_id != OPERATIONAL_EXPORT_TENANT_ID:
        if len({item["case_id"] for item in cases}) > 1 and any(item["case_id"] != case_id for item in cases):
            raise CaseAuditError("mixed_tenant_batch")


def _select_case_artifacts(
    chain: Sequence[CaseAuditEvent],
    *,
    tenant_id: str,
    case_id: str,
    purpose_ref: str,
    artifact_ids: tuple[str, ...],
) -> list[dict[str, Any]]:
    by_id = {event.event_id: event for event in chain}
    chosen = chain
    if artifact_ids:
        missing = [item for item in artifact_ids if item not in by_id]
        if missing:
            raise CaseAuditError("artifact_not_authorized")
        chosen = tuple(by_id[item] for item in artifact_ids)
    selected: list[dict[str, Any]] = []
    for event in chosen:
        if event.tenant_id != tenant_id or event.case_id != case_id:
            raise CaseAuditError("mixed_tenant_batch")
        if event.purpose_ref != purpose_ref:
            raise CaseAuditError("purpose_mismatch")
        view = event.public_view()
        selected.append({name: view[name] for name in AUTHORIZED_EXPORT_FIELDS if name in view})
    return selected


def _parse_export_body(body: Mapping[str, Any], *, operational: bool = False) -> dict[str, Any]:
    if not isinstance(body, Mapping):
        raise CaseAuditError("request_body")
    if "path" in body or any(isinstance(key, str) and (".." in key or "/" in key or "\\" in key) for key in body):
        raise CaseAuditError("traversal")
    role_claims = {name: body[name] for name in ROLE_CLAIM_FIELDS if name in body}
    for name, value in body.items():
        if not isinstance(name, str) or name.lower() in SENSITIVE_FIELDS:
            raise CaseAuditError("sensitive_field")
        if isinstance(value, (bytes, bytearray)):
            raise CaseAuditError("sensitive_field")
        if isinstance(value, str) and (len(value) > 200 or "\n" in value or "\x00" in value or ".." in value):
            raise CaseAuditError("traversal" if ".." in value or "/" in value or "\\" in value else "sensitive_field")
    fields = body.get("fields")
    allowed = OPERATIONAL_EXPORT_FIELDS if operational else AUTHORIZED_EXPORT_FIELDS
    if not isinstance(fields, list) or not fields or any(not isinstance(item, str) or item not in allowed for item in fields):
        raise CaseAuditError("unauthorized_field")
    if len(set(fields)) != len(fields):
        raise CaseAuditError("unauthorized_field")
    artifact_ids = body.get("artifact_ids", [])
    if not isinstance(artifact_ids, list) or any(not isinstance(item, str) for item in artifact_ids):
        raise CaseAuditError("artifact_not_authorized")
    for item in artifact_ids:
        _label(item, "traversal")
        if ".." in item:
            raise CaseAuditError("traversal")
    cases = body.get("cases")
    parsed_cases: list[dict[str, str]] | None = None
    if cases is not None:
        if not isinstance(cases, list) or not cases:
            raise CaseAuditError("mixed_tenant_batch")
        parsed_cases = []
        for item in cases:
            if not isinstance(item, Mapping) or set(item) - {"case_id", "tenant_id"}:
                raise CaseAuditError("mixed_tenant_batch")
            parsed_cases.append({
                "case_id": _label(str(item.get("case_id") or ""), "traversal"),
                "tenant_id": _label(str(item.get("tenant_id") or ""), "traversal"),
            })
    grant_version = body.get("grant_version")
    if type(grant_version) is not int:
        raise CaseAuditError("stale_grant")
    membership_version = body.get("membership_version")
    if membership_version is not None and type(membership_version) is not int:
        raise CaseAuditError("stale_grant")
    expected_revision = body.get("expected_revision", 1 if operational else None)
    if operational:
        expected_revision = 1
    elif type(expected_revision) is not int:
        raise CaseAuditError("revision_conflict")
    user_decrypt = body.get("user_decrypt") is True and body.get("decryption") == USER_DECRYPT_CONFIRMATION
    if body.get("user_decrypt") not in (None, False, True):
        raise CaseAuditError("user_decrypt")
    export_id = body.get("export_id")
    if export_id is not None:
        export_id = _label(str(export_id), "traversal")
        if ".." in export_id:
            raise CaseAuditError("traversal")
    purpose = _label(str(body.get("purpose_ref") or ""), "purpose_ref")
    if PURPOSE_RE.fullmatch(purpose) is None:
        raise CaseAuditError("purpose_ref")
    tenant_id = _label(str(body.get("tenant_id") or ""), "tenant_id")
    case_id = OPERATIONAL_EXPORT_CASE_ID if operational else _label(str(body.get("case_id") or ""), "case_id")
    resource_id = "operational-audit" if operational else _label(str(body.get("resource_id") or ""), "resource_id")
    return {
        "actor_principal_id": _label(str(body.get("actor_principal_id") or ""), "actor"),
        "case_id": case_id,
        "tenant_id": tenant_id,
        "resource_id": resource_id,
        "grant_id": _label(str(body.get("grant_id") or ""), "grant_id"),
        "grant_kind": _label(str(body.get("grant_kind") or ""), "grant_kind"),
        "grant_version": grant_version,
        "purpose_ref": purpose,
        "expected_revision": expected_revision,
        "membership_version": membership_version,
        "fields": tuple(fields),
        "artifact_ids": tuple(artifact_ids),
        "cases": parsed_cases,
        "user_decrypt": user_decrypt,
        "export_id": export_id,
        "role_claims": role_claims,
    }


def _export_binding(tenant_id: str, case_id: str, export_id: str) -> PrivateArtifactBinding:
    return PrivateArtifactBinding(
        tenant_id=tenant_id,
        case_id=case_id,
        artifact_kind=EXPORT_ARTIFACT_KIND,
        revision=export_id,
        principal_id=tenant_id,
    )


def _export_view(document: Mapping[str, Any], envelope: bytes, *, user_decrypted: bool) -> dict[str, Any]:
    released = user_decrypted is True
    records = document.get("records") if released else None
    if released and not isinstance(records, list):
        raise CaseAuditError("integrity")
    return {
        "task_id": EXPORT_TASK_ID,
        "export_id": document["export_id"],
        "kind": document["kind"],
        "encrypted": released is False,
        "user_decrypted": released,
        "purpose_ref": document["purpose_ref"],
        "grant_id": document["grant_id"],
        "grant_kind": document["grant_kind"],
        "grant_version": document["grant_version"],
        "actor_principal_id": document["actor_principal_id"],
        "tenant_id": document["tenant_id"],
        "case_id": document["case_id"],
        "fields": list(document["fields"]),
        "artifact_ids": list(document["artifact_ids"]),
        "envelope": None if released else base64.b64encode(envelope).decode("ascii"),
        "records": records,
        "actor_is_encrypted_owner": False,
        "limitations": list(EXPORT_LIMITATIONS),
    }


def _event_document(event: CaseAuditEvent) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": event.event_id,
        "sequence": event.sequence,
        "action": event.action,
        "actor_principal_id": event.actor_principal_id,
        "resource_id": event.resource_id,
        "revision": event.revision,
        "resource_revision": event.resource_revision,
        "grant_id": event.grant_id,
        "grant_kind": event.grant_kind,
        "grant_version": event.grant_version,
        "membership_version": event.membership_version,
        "membership_grant_id": event.membership_grant_id,
        "purpose_ref": event.purpose_ref,
        "tenant_id": event.tenant_id,
        "case_id": event.case_id,
        "canonical_owner_principal_id": event.canonical_owner_principal_id,
        "actor_is_encrypted_owner": event.actor_is_encrypted_owner,
        "previous_digest": event.previous_digest,
        "idempotency_key": event.idempotency_key,
        "fingerprint": _fingerprint(event),
    }


def _event_from_document(document: Mapping[str, Any]) -> CaseAuditEvent:
    if int(document.get("schema_version") or 0) != SCHEMA_VERSION:
        raise CaseAuditError("schema")
    sequence = document.get("sequence")
    revision = document.get("revision")
    grant_version = document.get("grant_version")
    membership_version = document.get("membership_version")
    if type(sequence) is not int or sequence < 1:
        raise CaseAuditError("schema")
    if type(revision) is not int or revision < 1 or type(grant_version) is not int or grant_version < 0:
        raise CaseAuditError("schema")
    if type(membership_version) is not int or membership_version < 0:
        raise CaseAuditError("schema")
    kind = str(document.get("grant_kind") or "")
    if kind not in GRANT_KINDS:
        raise CaseAuditError("schema")
    if document.get("actor_is_encrypted_owner") is not False:
        raise CaseAuditError("owner_impersonation")
    event = CaseAuditEvent(
        event_id=_label(str(document.get("event_id") or ""), "schema"),
        sequence=sequence,
        action=_label(str(document.get("action") or ""), "schema"),
        actor_principal_id=_label(str(document.get("actor_principal_id") or ""), "schema"),
        resource_id=_label(str(document.get("resource_id") or ""), "schema"),
        revision=revision,
        resource_revision=_label(str(document.get("resource_revision") or ""), "schema"),
        grant_id=_label(str(document.get("grant_id") or ""), "schema"),
        grant_kind=kind,
        grant_version=grant_version,
        membership_version=membership_version,
        membership_grant_id=str(document.get("membership_grant_id") or ""),
        purpose_ref=_label(str(document.get("purpose_ref") or ""), "schema"),
        tenant_id=_label(str(document.get("tenant_id") or ""), "schema"),
        case_id=_label(str(document.get("case_id") or ""), "schema"),
        canonical_owner_principal_id=_label(str(document.get("canonical_owner_principal_id") or ""), "schema"),
        actor_is_encrypted_owner=False,
        previous_digest=_label(str(document.get("previous_digest") or ""), "schema"),
        idempotency_key=_label(str(document.get("idempotency_key") or ""), "schema"),
    )
    if kind == "owner" and event.membership_grant_id != "":
        raise CaseAuditError("schema")
    if kind == "membership" and event.membership_grant_id != event.grant_id:
        raise CaseAuditError("schema")
    if kind == "key":
        _label(event.membership_grant_id, "schema")
    if PURPOSE_RE.fullmatch(event.purpose_ref) is None:
        raise CaseAuditError("schema")
    if len(event.previous_digest) != 64:
        raise CaseAuditError("schema")
    stored = str(document.get("fingerprint") or "")
    if stored != _fingerprint(event):
        raise CaseAuditError("integrity")
    return event
