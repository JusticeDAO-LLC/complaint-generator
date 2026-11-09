"""Operational account directory. Roles stay server-owned.

An operational admin may provision accounts, replace a single server role,
and disable or restore an account. Audit read is a separate right held in
this service, not a role a request body can mint. Directory and search
responses use a fixed field allowlist. They do not open case artifacts, and
they do not copy narratives, messages, evidence, keys, or summaries.

Disabling an account, or changing its role, drops that principal's current
browser session before the response returns. The next request on an
already-open client, and any forged replay of the old cookie, fails closed.
Operations inspection adds sealed-index and assignment counts, storage and
worker states, and bounded diagnostic codes. It does not open owner envelopes.
Incident handling records that code and does not impersonate a case owner or
grant case content. This module does not send external messages and does not
use WebSocket or SSE.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from starlette.requests import Request

from applications.browser_sessions import BrowserSessionService
from applications.principal_store import (
    KNOWN_ROLES,
    PrincipalRecord,
    PrincipalStore,
    PrincipalStoreError,
)

TASK_ID = "CIMP-GUI-50"
OPERATIONS_TASK_ID = "CIMP-GUI-51"
UX_WORKSPACE_TASK_ID = "CIMP-UX-42"
CONTENT_ACCESS_TASK_ID = "CIMP-UX-43"
ADMIN_PAGE_PATH = "/admin"
ADMIN_SCRIPT_PATH = "/static/complaint_admin.js"
ADMIN_API_PREFIX = "/api/admin"
WORKSPACE_PATH = ADMIN_API_PREFIX + "/workspace"
CONTENT_ACCESS_PATH = ADMIN_API_PREFIX + "/content-access"
OPERATIONS_PATH = ADMIN_API_PREFIX + "/operations"
INCIDENT_PATH = OPERATIONS_PATH + "/incidents"
ASSIGNMENT_STATUSES = ("pending", "accepted", "declined", "expired", "removed")
WORKER_STATES = ("idle", "running", "stalled", "unavailable")
SUPPORT_DIAGNOSTIC_CODES = frozenset({
    "storage_unresolved",
    "worker_stalled",
    "assignment_backlog",
    "support_unobserved",
    "readback_mismatch",
    "backend_unavailable",
})
INCIDENT_SCOPES = frozenset({"assignment", "storage", "worker", "support"})
WORKSPACE_QUERY_FIELDS = frozenset({
    "principal_id",
    "account_kind",
    "status",
    "assignment",
    "assignment_status",
    "min_assigned_cases",
    "audit_right",
    "case_id",
})
ASSIGNMENT_FILTERS = frozenset({"", "any", "assigned", "unassigned"})
AUDIT_RIGHT_FILTERS = frozenset({"", "any", "granted", "absent"})
IMPERSONATION_FIELDS = frozenset({
    "act_as",
    "act_as_owner",
    "as_owner",
    "impersonate",
    "impersonate_owner",
    "owner_principal_id",
    "decrypt",
    "open_case",
    "grant_case_content",
    "case_content_access",
})
ACCOUNT_KINDS = KNOWN_ROLES
ACCOUNT_STATUSES = frozenset({"active", "disabled"})
LEAST_PRIVILEGE_FIELDS = (
    "principal_id",
    "roles",
    "status",
    "revision",
    "role_authority",
    "audit_right",
)
CONTENT_REQUEST_FIELDS = frozenset({
    "narrative",
    "narratives",
    "message",
    "messages",
    "evidence",
    "key",
    "keys",
    "summary",
    "summaries",
    "case_plaintext",
    "plaintext",
    "credential",
    "credentials",
    "data_key",
    "browser_key",
    "wrapped_ciphertext",
    "envelope",
})
REJECTED_BODY_FIELDS = frozenset({
    "trusted_local",
    "trust",
    "role",
    "roles",
    "staff_role",
    "is_admin",
    "is_staff",
    "is_lawyer",
    "membership",
    "grant",
    "actions",
    *CONTENT_REQUEST_FIELDS,
})
ADMIN_LIMITATIONS = (
    "request_body_cannot_assign_staff_role",
    "audit_right_is_separate_from_operational_admin",
    "admin_search_does_not_decrypt_case_artifacts",
    "case_content_requires_independent_case_grant",
    "disable_and_role_change_drop_existing_sessions",
    "no_external_notification_delivery",
    "no_websocket_or_sse",
    "operations_counts_do_not_open_owner_envelopes",
    "incident_handling_does_not_impersonate_case_owner",
    "incident_handling_does_not_grant_case_content",
    "support_diagnostics_are_bounded_codes",
    "audit_export_requires_purpose_current_grant_and_explicit_fields",
    "private_audit_exports_stay_encrypted_until_explicit_user_decryption",
    "direct_audit_download_is_denied",
    "operational_admin_does_not_authorize_legal_content_review",
    "body_roles_approvals_and_cached_cases_cannot_authorize_content",
    "content_access_cannot_bypass_key_grant",
    "tenant_case_actor_crossings_are_denied",
)


class OperationalAdminError(Exception):
    """Fail-closed directory error. ``code`` is a stable machine reason."""

    def __init__(self, code: str) -> None:
        self.code = str(code)
        super().__init__(self.code)


def _label(value: Any, code: str) -> str:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise OperationalAdminError(code)
    if any(char in value for char in ("\x00", "\n", "\r", "/", "\\")):
        raise OperationalAdminError(code)
    return value


class OperationalAdminService:
    """Account lifecycle over the sealed principal roster and live sessions."""

    def __init__(
        self,
        *,
        principals: PrincipalStore,
        sessions: BrowserSessionService,
        clock: Callable[[], int],
        audit_principal_ids: Sequence[str] = (),
        memberships: Any = None,
        cases: Any = None,
        storage: Any = None,
        assignments: Any = None,
        workers: Callable[[], Sequence[Mapping[str, Any]]] | None = None,
        case_audit: Any = None,
    ) -> None:
        if not isinstance(principals, PrincipalStore) or not isinstance(sessions, BrowserSessionService):
            raise OperationalAdminError("authority_owners")
        if not callable(clock):
            raise OperationalAdminError("authority_owners")
        if not isinstance(audit_principal_ids, Sequence) or isinstance(audit_principal_ids, (str, bytes)):
            raise OperationalAdminError("authority_owners")
        if workers is not None and not callable(workers):
            raise OperationalAdminError("authority_owners")
        from applications.case_audit import CaseAuditStore
        if case_audit is not None and not isinstance(case_audit, CaseAuditStore):
            raise OperationalAdminError("authority_owners")
        self._principals = principals
        self._sessions = sessions
        self._clock = clock
        self._memberships = memberships
        self._cases = cases
        self._storage = storage
        self._assignments = assignments
        self._workers = workers
        self._audit_readers = {str(item) for item in audit_principal_ids}
        self._case_audit = case_audit
        self._events: list[dict[str, Any]] = []
        self._incidents: list[dict[str, Any]] = []
        self._content_access: list[dict[str, Any]] = []

    def list_accounts(self, actor_principal_id: str, session_roles: Sequence[str], query: Mapping[str, Any] | None = None) -> dict[str, Any]:
        actor = self._require_admin(actor_principal_id, session_roles)
        payload = self._query(query or {})
        self._reject_content_request(payload)
        needle = payload.get("principal_id", "")
        if needle != "" and not isinstance(needle, str):
            raise OperationalAdminError("principal_id")
        case_id = payload.get("case_id", "")
        if case_id != "":
            case_id = _label(case_id, "case_id")
            if not self._independent_grant(actor.principal_id, case_id):
                raise OperationalAdminError("independent_case_grant_required")
        accounts = []
        for record in self._principals.recover():
            if needle and needle not in record.principal_id:
                continue
            accounts.append(self._least(record))
        accounts.sort(key=lambda item: item["principal_id"])
        return {
            "actor_principal_id": actor.principal_id,
            "accounts": accounts,
            "fields": list(LEAST_PRIVILEGE_FIELDS),
            "case_content": None,
            "narratives": [],
            "messages": [],
            "evidence": [],
            "keys": [],
            "summaries": [],
            "case_id": case_id or None,
            "limitations": list(ADMIN_LIMITATIONS),
        }

    def provision(self, actor_principal_id: str, session_roles: Sequence[str], body: Mapping[str, Any]) -> dict[str, Any]:
        actor = self._require_admin(actor_principal_id, session_roles)
        payload = self._body(body)
        kind = _label(payload.get("account_kind"), "account_kind")
        if kind not in ACCOUNT_KINDS:
            raise OperationalAdminError("unknown_role")
        if kind == "complainant":
            created = self._principals.register_from_request({})
        else:
            created = self._principals.install_server_role(role=kind)
        self._event(actor.principal_id, "provision", created, detail=kind)
        return self._least(created)

    def change_role(
        self,
        actor_principal_id: str,
        session_roles: Sequence[str],
        subject_principal_id: str,
        body: Mapping[str, Any],
    ) -> dict[str, Any]:
        actor = self._require_admin(actor_principal_id, session_roles)
        payload = self._body(body)
        subject_id = _label(subject_principal_id, "principal_id")
        kind = _label(payload.get("account_kind"), "account_kind")
        expected = payload.get("expected_revision")
        if type(expected) is not int:
            raise OperationalAdminError("revision_conflict")
        before = self._load(subject_id)
        if before.status != "active":
            raise OperationalAdminError("account_disabled")
        if kind not in before.roles and self._active_admin_count() == 1 and "operational_admin" in before.roles:
            raise OperationalAdminError("last_operational_admin")
        try:
            updated = self._principals.assign_role(
                actor_principal_id=actor.principal_id,
                subject_principal_id=subject_id,
                role=kind,
                expected_revision=expected,
            )
        except PrincipalStoreError as exc:
            raise OperationalAdminError(_role_code(exc.code)) from exc
        self._revoke(subject_id)
        self._event(actor.principal_id, "role_change", updated, detail=kind)
        return self._least(updated)

    def set_status(
        self,
        actor_principal_id: str,
        session_roles: Sequence[str],
        subject_principal_id: str,
        body: Mapping[str, Any],
    ) -> dict[str, Any]:
        actor = self._require_admin(actor_principal_id, session_roles)
        payload = self._body(body)
        subject_id = _label(subject_principal_id, "principal_id")
        status = _label(payload.get("status"), "status")
        if status not in ACCOUNT_STATUSES:
            raise OperationalAdminError("status")
        expected = payload.get("expected_revision")
        if type(expected) is not int:
            raise OperationalAdminError("revision_conflict")
        subject = self._load(subject_id)
        if expected != subject.revision:
            raise OperationalAdminError("revision_conflict")
        if subject.principal_id == actor.principal_id and status != "active":
            raise OperationalAdminError("actor_cannot_disable_self")
        if status == "disabled" and "operational_admin" in subject.roles and self._active_admin_count() == 1:
            raise OperationalAdminError("last_operational_admin")
        updated = PrincipalRecord(
            principal_id=subject.principal_id,
            tenant_id=subject.tenant_id,
            roles=subject.roles,
            status=status,
            revision=subject.revision + 1,
            role_authority="server",
            excluded_fields=subject.excluded_fields,
        )
        self._principals._seal(updated)
        if status != "active":
            self._audit_readers.discard(subject_id)
        self._revoke(subject_id)
        self._event(actor.principal_id, "status", updated, detail=status)
        return self._least(updated)

    def set_audit_right(
        self,
        actor_principal_id: str,
        session_roles: Sequence[str],
        subject_principal_id: str,
        body: Mapping[str, Any],
    ) -> dict[str, Any]:
        actor = self._require_admin(actor_principal_id, session_roles)
        if actor.principal_id not in self._audit_readers:
            raise OperationalAdminError("audit_right_required")
        payload = self._body(body)
        subject_id = _label(subject_principal_id, "principal_id")
        enabled = payload.get("enabled")
        if type(enabled) is not bool:
            raise OperationalAdminError("audit_right")
        expected = payload.get("expected_revision")
        if type(expected) is not int:
            raise OperationalAdminError("revision_conflict")
        subject = self._load(subject_id)
        if expected != subject.revision:
            raise OperationalAdminError("revision_conflict")
        if "operational_admin" not in subject.roles or subject.status != "active":
            raise OperationalAdminError("audit_right")
        if enabled:
            self._audit_readers.add(subject_id)
        else:
            if subject_id == actor.principal_id and self._audit_readers == {actor.principal_id}:
                raise OperationalAdminError("last_audit_right")
            self._audit_readers.discard(subject_id)
        self._event(actor.principal_id, "audit_right", subject, detail="granted" if enabled else "revoked")
        return self._least(subject)

    def analyze_workspace(
        self,
        actor_principal_id: str,
        session_roles: Sequence[str],
        query: Mapping[str, Any] | None = None,
        *,
        sources: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Filter accounts, roles, assignments, and sealed case counts.

        Operational admin status is enough for this metadata. Narratives,
        evidence, private messages, exports, and keys stay out of the payload.
        Naming a case requires that actor's separate accepted membership, and
        even then this surface still withholds case content.
        """

        actor = self._require_admin(actor_principal_id, session_roles)
        payload = self._query(query or {})
        self._reject_content_request(payload)
        if any(name in payload for name in ("export", "exports", "private_message", "private_messages")):
            raise OperationalAdminError("admin_case_content_denied")
        filters = self._workspace_filters(payload)
        resolved = self._sources(sources)
        roster = self._assignment_roster(resolved.get("memberships"))
        if filters["case_id"]:
            if not self._independent_grant(actor.principal_id, filters["case_id"]):
                raise OperationalAdminError("independent_case_grant_required")
        needs_assignments = filters["assignment"] in {"assigned", "unassigned"} or bool(filters["assignment_status"])
        if needs_assignments and not roster["observed"]:
            accounts: list[dict[str, Any]] = []
            state = "assignment_unobserved"
        else:
            accounts = []
            for record in self._principals.recover():
                row = self._workspace_row(record, roster)
                if not self._row_matches(row, filters, roster):
                    continue
                accounts.append(row)
            accounts.sort(key=lambda item: item["principal_id"])
            state = "empty" if not accounts else "ready"
        view = self._operations_view(resolved)
        return {
            "task_id": UX_WORKSPACE_TASK_ID,
            "actor_principal_id": actor.principal_id,
            "state": state,
            "filters": filters,
            "accounts": accounts,
            "filtered_account_count": len(accounts),
            "role_counts": _tally(accounts, "roles"),
            "status_counts": _tally_status(accounts),
            "case_counts": view["case_counts"],
            "assignment_status": view["assignment_status"],
            "content_review": {
                "exposed": False,
                "requires_explicit_case_grant": True,
                "grant_present": bool(filters["case_id"]),
                "narratives": [],
                "evidence": [],
                "private_messages": [],
                "exports": [],
                "keys": [],
            },
            "case_content": None,
            "case_content_granted": False,
            "limitations": list(ADMIN_LIMITATIONS),
        }

    def inspect_operations(
        self,
        actor_principal_id: str,
        session_roles: Sequence[str],
        query: Mapping[str, Any] | None = None,
        *,
        sources: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Counts and operational states for an admin. Envelopes stay sealed."""

        actor = self._require_admin(actor_principal_id, session_roles)
        payload = self._query(query or {})
        self._reject_operations_request(payload)
        view = self._operations_view(self._sources(sources))
        view["actor_principal_id"] = actor.principal_id
        view["task_id"] = OPERATIONS_TASK_ID
        return view

    def record_incident(
        self,
        actor_principal_id: str,
        session_roles: Sequence[str],
        body: Mapping[str, Any],
        *,
        sources: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record an operational incident without becoming a case owner.

        The handler does not select, list, or open a case, and it does not
        write a membership or key grant. A request that asks for either is
        rejected before any operations snapshot is built.
        """

        actor = self._require_admin(actor_principal_id, session_roles)
        payload = self._body(body)
        self._reject_operations_request(payload)
        code = _label(payload.get("code"), "support_diagnostic_code")
        scope = _label(payload.get("scope"), "incident_scope")
        if code not in SUPPORT_DIAGNOSTIC_CODES:
            raise OperationalAdminError("support_diagnostic_code")
        if scope not in INCIDENT_SCOPES:
            raise OperationalAdminError("incident_scope")
        if set(payload) - {"code", "scope"}:
            raise OperationalAdminError("incident_fields")
        resolved = self._sources(sources)
        incident = {
            "at": self._now(),
            "actor_principal_id": actor.principal_id,
            "action": "operational_incident",
            "code": code,
            "scope": scope,
            "impersonated_case_owner": False,
            "case_content_granted": False,
        }
        self._incidents.append(dict(incident))
        self._events.append({
            "at": incident["at"],
            "actor_principal_id": actor.principal_id,
            "action": "operational_incident",
            "subject_principal_id": actor.principal_id,
            "detail": code,
            "revision": actor.revision,
        })
        view = self._operations_view(resolved)
        view.update({
            "actor_principal_id": actor.principal_id,
            "task_id": OPERATIONS_TASK_ID,
            "incident": {
                "at": incident["at"],
                "code": code,
                "scope": scope,
                "impersonated_case_owner": False,
                "case_content_granted": False,
            },
            "case_content": None,
            "opened_case_ids": [],
        })
        return view

    def decide_content_access(
        self,
        actor_principal_id: str,
        session_roles: Sequence[str],
        body: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Record one content-access or assignment decision.

        The live case and membership are read from server owners. Body roles,
        approval labels, cached case objects, and keys cannot authorize
        content. The returned record never includes case plaintext.
        """

        from applications.case_review import CaseReviewError, assess_content_access

        actor = self._require_admin(actor_principal_id, session_roles)
        if not isinstance(body, Mapping):
            raise OperationalAdminError("request_body")
        self._reject_content_request(body)
        purpose = body.get("purpose")
        if not isinstance(purpose, str):
            raise OperationalAdminError("purpose_rejected")
        try:
            case_id = _label(body.get("case_id"), "case_id")
            subject_id = _label(body.get("subject_principal_id"), "subject_principal_id")
        except OperationalAdminError as exc:
            raise OperationalAdminError(exc.code) from exc
        self._load(subject_id)
        live = self._sealed_case(case_id)
        membership = self._subject_membership(subject_id, case_id, live)
        key_grant_present = False
        if membership is not None:
            grant_id = membership.get("key_grant_id")
            key_grant_present = isinstance(grant_id, str) and grant_id != ""
        try:
            verdict = assess_content_access(
                actor_principal_id=actor.principal_id,
                session_roles=tuple(actor.roles),
                purpose=purpose,
                body=body,
                live_case=live,
                subject_membership=membership,
                key_grant_present=key_grant_present,
                at=self._now(),
            )
        except CaseReviewError as exc:
            raise OperationalAdminError(exc.code) from exc
        if verdict.get("key_bypassed") is not False or "narrative" in verdict or "key" in verdict:
            raise OperationalAdminError("admin_case_content_denied")
        self._content_access.append(dict(verdict))
        self._events.append({
            "at": verdict["at"],
            "actor_principal_id": actor.principal_id,
            "action": verdict["purpose"],
            "subject_principal_id": verdict["subject_principal_id"],
            "detail": verdict["reason"],
            "revision": actor.revision,
            "tenant_id": verdict["tenant_id"],
            "case_id": verdict["case_id"],
            "decision": verdict["decision"],
            "content_permitted": False if verdict["purpose"] != "legal_content_review" else verdict["content_permitted"],
            "key_bypassed": False,
        })
        if verdict["decision"] == "denied":
            raise OperationalAdminError(verdict["reason"])
        return {
            "task_id": CONTENT_ACCESS_TASK_ID,
            "decision": verdict,
            "case_content": None,
            "narratives": [],
            "evidence": [],
            "private_messages": [],
            "exports": [],
            "keys": [],
            "limitations": list(ADMIN_LIMITATIONS),
        }

    def content_access_log(self, actor_principal_id: str, session_roles: Sequence[str]) -> dict[str, Any]:
        actor = self._require_admin(actor_principal_id, session_roles)
        if actor.principal_id not in self._audit_readers:
            raise OperationalAdminError("audit_right_required")
        return {
            "task_id": CONTENT_ACCESS_TASK_ID,
            "actor_principal_id": actor.principal_id,
            "decisions": list(self._content_access),
            "case_content": None,
            "narratives": [],
            "evidence": [],
            "private_messages": [],
            "exports": [],
            "keys": [],
            "limitations": list(ADMIN_LIMITATIONS),
        }

    def _sealed_case(self, case_id: str) -> dict[str, Any] | None:
        finder = getattr(self._cases, "sealed_case", None)
        if not callable(finder):
            return None
        found = finder(case_id)
        if found is None:
            return None
        tenant_id = getattr(found, "tenant_id", None)
        resource_id = getattr(found, "resource_id", None)
        owner_id = getattr(found, "owner_principal_id", None)
        revision = getattr(found, "revision", None)
        if not all(isinstance(item, str) and item for item in (tenant_id, resource_id, owner_id)):
            return None
        if type(revision) is not int:
            return None
        if getattr(found, "case_id", None) != case_id:
            return None
        return {
            "tenant_id": tenant_id,
            "case_id": case_id,
            "resource_id": resource_id,
            "owner_principal_id": owner_id,
            "revision": revision,
        }

    def _subject_membership(self, subject_id: str, case_id: str, live: Mapping[str, Any] | None) -> dict[str, Any] | None:
        memberships = self._memberships
        if memberships is None or not hasattr(memberships, "recover") or live is None:
            return None
        try:
            grants = memberships.recover()
        except Exception as exc:
            raise OperationalAdminError("assignment_status_unavailable") from exc
        for grant in grants:
            if getattr(grant, "member_principal_id", None) != subject_id:
                continue
            if getattr(grant, "case_id", None) != case_id:
                continue
            return {
                "member_principal_id": subject_id,
                "case_id": case_id,
                "tenant_id": getattr(grant, "tenant_id", live["tenant_id"]),
                "status": getattr(grant, "status", None),
                "revision": getattr(grant, "revision", None),
                "key_grant_id": getattr(grant, "key_grant_id", None),
            }
        return None

    def audit_log(self, actor_principal_id: str, session_roles: Sequence[str]) -> dict[str, Any]:
        actor = self._require_admin(actor_principal_id, session_roles)
        if actor.principal_id not in self._audit_readers:
            raise OperationalAdminError("audit_right_required")
        return {
            "actor_principal_id": actor.principal_id,
            "events": list(self._events),
            "fields": ["at", "actor_principal_id", "action", "subject_principal_id", "detail", "revision"],
            "case_content": None,
            "limitations": list(ADMIN_LIMITATIONS),
        }

    def export_audit(
        self,
        actor_principal_id: str,
        session_roles: Sequence[str],
        body: Mapping[str, Any],
        *,
        verify_access: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        """Export operational audit rows through the sealed case-audit owner.

        A role claim in the body is forged. The current audit-right grant is
        the actor's roster revision. Case content is not opened.
        """

        from applications.case_audit import CaseAuditError, CaseAuditStore

        if not isinstance(body, Mapping):
            raise OperationalAdminError("request_body")
        self._reject_content_request(body)
        if any(name in body for name in ("role", "roles", "staff_role", "is_admin", "is_staff", "is_lawyer")):
            raise OperationalAdminError("forged_role")
        actor = self._require_admin(actor_principal_id, session_roles)
        if actor.principal_id not in self._audit_readers:
            raise OperationalAdminError("audit_right_required")
        store = self._case_audit
        if not isinstance(store, CaseAuditStore):
            raise OperationalAdminError("audit_export_unavailable")
        # Bind the authenticated caller even for in-process callers. A second
        # admin's public identifier is not authority to export that actor's rows.
        material = dict(body)
        if material.get("actor_principal_id") != actor.principal_id:
            raise OperationalAdminError("unauthenticated")
        def admit() -> None:
            if verify_access is not None:
                if verify_access() is False:
                    raise OperationalAdminError("unauthenticated")
            current = self._require_admin(actor_principal_id, session_roles)
            if current.revision != actor.revision or current.principal_id not in self._audit_readers:
                raise OperationalAdminError("audit_right_required")
        try:
            return store.export_operational_from_request(
                material,
                session_roles=tuple(actor.roles),
                events=tuple(self._events),
                audit_reader=True,
                verify_access=admit,
            )
        except CaseAuditError as exc:
            raise OperationalAdminError(exc.code) from exc

    def _least(self, record: PrincipalRecord) -> dict[str, Any]:
        view = {
            "principal_id": record.principal_id,
            "roles": list(record.roles),
            "status": record.status,
            "revision": record.revision,
            "role_authority": record.role_authority,
            "audit_right": record.principal_id in self._audit_readers,
        }
        if tuple(view) != LEAST_PRIVILEGE_FIELDS:
            raise OperationalAdminError("least_privilege_fields")
        return view

    def _require_admin(self, actor_principal_id: str, session_roles: Sequence[str]) -> PrincipalRecord:
        actor_id = _label(actor_principal_id, "unauthenticated")
        presented = tuple(session_roles) if isinstance(session_roles, Sequence) and not isinstance(session_roles, str) else ()
        try:
            record = self._principals.load(actor_id)
        except PrincipalStoreError as exc:
            self._revoke(actor_id)
            raise OperationalAdminError("unauthenticated") from exc
        if record.status != "active":
            self._revoke(actor_id)
            raise OperationalAdminError("account_disabled")
        if tuple(record.roles) != presented:
            self._revoke(actor_id)
            raise OperationalAdminError("authority_stale")
        if "operational_admin" not in record.roles:
            raise OperationalAdminError("action_not_permitted")
        return record

    def _load(self, principal_id: str) -> PrincipalRecord:
        try:
            return self._principals.load(principal_id)
        except PrincipalStoreError as exc:
            raise OperationalAdminError("missing_principal") from exc

    def _active_admin_count(self) -> int:
        return sum(
            1
            for record in self._principals.recover()
            if record.status == "active" and "operational_admin" in record.roles
        )

    def _independent_grant(self, actor_id: str, case_id: str) -> bool:
        memberships = self._memberships
        if memberships is None or not hasattr(memberships, "recover"):
            return False
        try:
            grants = memberships.recover()
        except Exception as exc:
            raise OperationalAdminError("independent_case_grant_required") from exc
        for grant in grants:
            if getattr(grant, "member_principal_id", None) != actor_id:
                continue
            if getattr(grant, "case_id", None) != case_id:
                continue
            if getattr(grant, "status", None) == "accepted":
                return True
        return False

    def _reject_content_request(self, payload: Mapping[str, Any]) -> None:
        if any(name in payload for name in CONTENT_REQUEST_FIELDS):
            raise OperationalAdminError("admin_case_content_denied")

    def _reject_operations_request(self, payload: Mapping[str, Any]) -> None:
        self._reject_content_request(payload)
        if any(name in payload for name in IMPERSONATION_FIELDS):
            raise OperationalAdminError("incident_cannot_impersonate_owner")
        if payload.get("case_id") not in (None, ""):
            raise OperationalAdminError("operations_case_scope_denied")

    def _sources(self, sources: Mapping[str, Any] | None) -> dict[str, Any]:
        provided = sources if isinstance(sources, Mapping) else {}
        cases = provided.get("cases", self._cases)
        storage = provided.get("storage", self._storage)
        assignments = provided.get("assignments", self._assignments)
        memberships = provided.get("memberships", self._memberships)
        if memberships is None and assignments is not None:
            memberships = getattr(assignments, "_memberships", None)
        workers = provided.get("workers", self._workers)
        return {
            "cases": cases,
            "storage": storage,
            "assignments": assignments,
            "memberships": memberships,
            "workers": workers,
        }

    def _operations_view(self, sources: Mapping[str, Any]) -> dict[str, Any]:
        assignments = self._assignment_counts(sources.get("memberships"))
        storage = self._storage_states(sources.get("storage"))
        workers = self._worker_states(sources.get("workers"))
        diagnostics = self._support_diagnostics(assignments, storage, workers)
        return {
            "case_counts": self._case_counts(sources.get("cases"), assignments),
            "assignment_status": assignments,
            "storage": storage,
            "workers": workers,
            "support_diagnostics": diagnostics,
            "incidents": [
                {
                    "at": item["at"],
                    "code": item["code"],
                    "scope": item["scope"],
                    "impersonated_case_owner": False,
                    "case_content_granted": False,
                }
                for item in self._incidents
            ],
            "case_content": None,
            "narratives": [],
            "messages": [],
            "evidence": [],
            "keys": [],
            "summaries": [],
            "opened_case_ids": [],
            "impersonated_case_owner": False,
            "case_content_granted": False,
            "limitations": list(ADMIN_LIMITATIONS),
        }

    def _case_counts(self, cases: Any, assignments: Mapping[str, Any]) -> dict[str, Any]:
        sealed = _sealed_owner_indexes(cases)
        return {
            "sealed_owner_indexes": sealed,
            "assigned_case_count": assignments["assigned_case_count"],
            "exact_case_count_available": False,
            "envelopes_opened": False,
            "owner_impersonated": False,
        }

    def _assignment_counts(self, memberships: Any) -> dict[str, Any]:
        counts = {status: 0 for status in ASSIGNMENT_STATUSES}
        case_ids: set[str] = set()
        if memberships is None or not hasattr(memberships, "recover"):
            return {
                "counts": counts,
                "assigned_case_count": 0,
                "observed": False,
            }
        try:
            grants = memberships.recover()
        except Exception as exc:
            raise OperationalAdminError("assignment_status_unavailable") from exc
        now = self._now()
        for grant in grants:
            status = getattr(grant, "status", None)
            expires_at = getattr(grant, "expires_at", None)
            if status == "pending" and type(expires_at) is int and now >= expires_at:
                status = "expired"
            if status not in counts:
                raise OperationalAdminError("assignment_status_unavailable")
            counts[status] += 1
            case_id = getattr(grant, "case_id", None)
            if isinstance(case_id, str) and case_id:
                case_ids.add(case_id)
        return {
            "counts": counts,
            "assigned_case_count": len(case_ids),
            "observed": True,
        }

    def _storage_states(self, storage: Any) -> dict[str, Any]:
        receipts = getattr(storage, "_receipts", None) if storage is not None else None
        if not isinstance(receipts, dict):
            return {
                "observed": False,
                "readiness": "unobserved",
                "receipt_count": 0,
                "durable_count": 0,
                "unresolved_count": 0,
                "pending_replica_count": 0,
                "readiness_counts": {"ready": 0, "unavailable": 0, "unresolved": 0, "unobserved": 1},
            }
        readiness_counts = {"ready": 0, "unavailable": 0, "unresolved": 0, "unobserved": 0}
        durable_count = 0
        unresolved_count = 0
        pending_count = 0
        failure_kinds: set[str] = set()
        for receipt in receipts.values():
            if not isinstance(receipt, Mapping):
                raise OperationalAdminError("storage_state_unavailable")
            readiness = receipt.get("storage_readiness")
            if readiness not in readiness_counts:
                raise OperationalAdminError("storage_state_unavailable")
            readiness_counts[readiness] += 1
            if receipt.get("durable") is True:
                durable_count += 1
            else:
                unresolved_count += 1
            if receipt.get("pending_replica") is True:
                pending_count += 1
            kind = receipt.get("failure_kind")
            if isinstance(kind, str) and kind in {"readback_mismatch", "backend", "backend_unavailable", "storage", "none", ""}:
                if kind in SUPPORT_DIAGNOSTIC_CODES:
                    failure_kinds.add(kind)
                elif kind == "backend":
                    failure_kinds.add("backend_unavailable")
        if durable_count and unresolved_count == 0:
            readiness = "ready"
        elif not receipts:
            readiness = "unobserved"
        elif readiness_counts["unavailable"] and durable_count == 0 and readiness_counts["unresolved"] == 0:
            readiness = "unavailable"
        else:
            readiness = "unresolved"
        return {
            "observed": True,
            "readiness": readiness,
            "receipt_count": len(receipts),
            "durable_count": durable_count,
            "unresolved_count": unresolved_count,
            "pending_replica_count": pending_count,
            "readiness_counts": readiness_counts,
            "failure_kinds": sorted(failure_kinds),
        }

    def _worker_states(self, workers: Any) -> dict[str, Any]:
        counts = {state: 0 for state in WORKER_STATES}
        if workers is None:
            return {"observed": False, "state": "unobserved", "counts": counts, "queue_depth": 0}
        if not callable(workers):
            raise OperationalAdminError("worker_state_unavailable")
        try:
            rows = workers()
        except OperationalAdminError:
            raise
        except Exception as exc:
            raise OperationalAdminError("worker_state_unavailable") from exc
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            raise OperationalAdminError("worker_state_unavailable")
        queue_depth = 0
        for row in rows:
            if not isinstance(row, Mapping) or set(row) - {"worker_id", "state", "queue_depth"}:
                raise OperationalAdminError("worker_payload")
            state = row.get("state")
            depth = row.get("queue_depth")
            if state not in counts or type(depth) is not int or depth < 0:
                raise OperationalAdminError("worker_state_unavailable")
            _label(row.get("worker_id"), "worker_id")
            counts[state] += 1
            queue_depth += depth
        if counts["stalled"]:
            summary = "stalled"
        elif counts["unavailable"] and sum(counts.values()) == counts["unavailable"]:
            summary = "unavailable"
        elif counts["running"]:
            summary = "running"
        else:
            summary = "idle"
        return {"observed": True, "state": summary, "counts": counts, "queue_depth": queue_depth}

    def _support_diagnostics(self, assignments: Mapping[str, Any], storage: Mapping[str, Any], workers: Mapping[str, Any]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        if storage.get("observed") and storage.get("unresolved_count", 0):
            items.append({"code": "storage_unresolved", "count": int(storage["unresolved_count"])})
        for kind in storage.get("failure_kinds") or []:
            if kind in SUPPORT_DIAGNOSTIC_CODES and kind != "storage_unresolved":
                items.append({"code": kind, "count": 1})
        stalled = int((workers.get("counts") or {}).get("stalled") or 0)
        if stalled:
            items.append({"code": "worker_stalled", "count": stalled})
        pending = int((assignments.get("counts") or {}).get("pending") or 0)
        if pending:
            items.append({"code": "assignment_backlog", "count": pending})
        if not items and not storage.get("observed") and not workers.get("observed") and not assignments.get("observed"):
            items.append({"code": "support_unobserved", "count": 0})
        if len(items) > 8:
            raise OperationalAdminError("support_diagnostics_bounded")
        for item in items:
            if set(item) != {"code", "count"} or item["code"] not in SUPPORT_DIAGNOSTIC_CODES:
                raise OperationalAdminError("support_diagnostics_bounded")
        return items

    def _body(self, body: Mapping[str, Any]) -> Mapping[str, Any]:
        if not isinstance(body, Mapping):
            raise OperationalAdminError("request_body")
        self._reject_content_request(body)
        if any(name in body for name in REJECTED_BODY_FIELDS):
            raise OperationalAdminError("request_cannot_mint_authority")
        return body

    def _query(self, query: Mapping[str, Any]) -> Mapping[str, Any]:
        if not isinstance(query, Mapping):
            raise OperationalAdminError("request_body")
        return query

    def _workspace_filters(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        unknown = set(payload) - WORKSPACE_QUERY_FIELDS
        if unknown:
            raise OperationalAdminError("filter_rejected")
        account_kind = payload.get("account_kind") or ""
        status = payload.get("status") or ""
        assignment = payload.get("assignment") or ""
        assignment_status = payload.get("assignment_status") or ""
        audit_right = payload.get("audit_right") or ""
        principal_id = payload.get("principal_id") or ""
        case_id = payload.get("case_id") or ""
        if account_kind != "" and account_kind not in ACCOUNT_KINDS:
            raise OperationalAdminError("filter_rejected")
        if status != "" and status not in ACCOUNT_STATUSES:
            raise OperationalAdminError("filter_rejected")
        if assignment not in ASSIGNMENT_FILTERS or audit_right not in AUDIT_RIGHT_FILTERS:
            raise OperationalAdminError("filter_rejected")
        if assignment_status != "" and assignment_status not in ASSIGNMENT_STATUSES:
            raise OperationalAdminError("filter_rejected")
        if principal_id != "":
            principal_id = _label(principal_id, "principal_id")
        if case_id != "":
            case_id = _label(case_id, "case_id")
        minimum = payload.get("min_assigned_cases", "")
        if minimum in ("", None):
            min_assigned = None
        elif isinstance(minimum, str) and minimum.isdigit():
            min_assigned = int(minimum)
        elif type(minimum) is int and minimum >= 0:
            min_assigned = minimum
        else:
            raise OperationalAdminError("filter_rejected")
        return {
            "principal_id": principal_id,
            "account_kind": account_kind,
            "status": status,
            "assignment": assignment or "any",
            "assignment_status": assignment_status,
            "min_assigned_cases": min_assigned,
            "audit_right": audit_right or "any",
            "case_id": case_id,
        }

    def _assignment_roster(self, memberships: Any) -> dict[str, Any]:
        by_member: dict[str, dict[str, Any]] = {}
        if memberships is None or not hasattr(memberships, "recover"):
            return {"observed": False, "by_member": by_member}
        try:
            grants = memberships.recover()
        except Exception as exc:
            raise OperationalAdminError("assignment_status_unavailable") from exc
        now = self._now()
        for grant in grants:
            member = getattr(grant, "member_principal_id", None)
            case_id = getattr(grant, "case_id", None)
            status = getattr(grant, "status", None)
            expires_at = getattr(grant, "expires_at", None)
            if not isinstance(member, str) or not member:
                raise OperationalAdminError("assignment_status_unavailable")
            if status == "pending" and type(expires_at) is int and now >= expires_at:
                status = "expired"
            if status not in ASSIGNMENT_STATUSES:
                raise OperationalAdminError("assignment_status_unavailable")
            bucket = by_member.setdefault(member, {"counts": {name: 0 for name in ASSIGNMENT_STATUSES}, "case_ids": set()})
            bucket["counts"][status] += 1
            if isinstance(case_id, str) and case_id:
                bucket["case_ids"].add(case_id)
        return {"observed": True, "by_member": by_member}

    def _workspace_row(self, record: PrincipalRecord, roster: Mapping[str, Any]) -> dict[str, Any]:
        row = self._least(record)
        bucket = (roster.get("by_member") or {}).get(record.principal_id)
        if not roster.get("observed"):
            row["assigned_case_count"] = None
            row["assignment_counts"] = {name: 0 for name in ASSIGNMENT_STATUSES}
            row["assignment_observed"] = False
            return row
        counts = dict(bucket["counts"]) if bucket else {name: 0 for name in ASSIGNMENT_STATUSES}
        case_ids = set(bucket["case_ids"]) if bucket else set()
        row["assigned_case_count"] = len(case_ids)
        row["assignment_counts"] = counts
        row["assignment_observed"] = True
        return row

    def _row_matches(self, row: Mapping[str, Any], filters: Mapping[str, Any], roster: Mapping[str, Any]) -> bool:
        if filters["principal_id"] and filters["principal_id"] not in row["principal_id"]:
            return False
        if filters["account_kind"] and filters["account_kind"] not in row["roles"]:
            return False
        if filters["status"] and row["status"] != filters["status"]:
            return False
        if filters["audit_right"] == "granted" and row["audit_right"] is not True:
            return False
        if filters["audit_right"] == "absent" and row["audit_right"] is not False:
            return False
        count = row.get("assigned_case_count")
        if filters["assignment"] == "assigned" and not count:
            return False
        if filters["assignment"] == "unassigned" and count:
            return False
        wanted = filters["assignment_status"]
        if wanted and int((row.get("assignment_counts") or {}).get(wanted) or 0) <= 0:
            return False
        minimum = filters["min_assigned_cases"]
        if minimum is not None and (count is None or count < minimum):
            return False
        case_id = filters["case_id"]
        if case_id:
            bucket = (roster.get("by_member") or {}).get(row["principal_id"]) or {}
            if case_id not in (bucket.get("case_ids") or ()):
                return False
        return True

    def _event(self, actor_id: str, action: str, subject: PrincipalRecord, *, detail: str) -> None:
        self._events.append({
            "at": self._now(),
            "actor_principal_id": actor_id,
            "action": action,
            "subject_principal_id": subject.principal_id,
            "detail": detail,
            "revision": subject.revision,
        })

    def _revoke(self, principal_id: str) -> None:
        sessions = self._sessions
        records = getattr(sessions, "_records", None)
        by_principal = getattr(sessions, "_by_principal", None)
        drop = getattr(sessions, "_drop", None)
        if not isinstance(records, dict) or not callable(drop):
            return
        doomed = [session_id for session_id, record in list(records.items()) if record.principal_id == principal_id]
        if isinstance(by_principal, dict):
            current = by_principal.get(principal_id)
            if isinstance(current, str) and current not in doomed:
                doomed.append(current)
        for session_id in doomed:
            drop(session_id)

    def _now(self) -> int:
        value = self._clock()
        if type(value) is not int:
            raise OperationalAdminError("clock")
        return value


def _sealed_owner_indexes(cases: Any) -> int | None:
    """Count sealed owner index files. Do not open or decrypt them."""

    if cases is None:
        return None
    root = getattr(cases, "_root", None)
    if root is None:
        return None
    directory = Path(root)
    if not directory.is_dir() or directory.is_symlink():
        return None
    count = 0
    for path in directory.iterdir():
        if path.is_symlink() or not path.is_file():
            continue
        if path.name.endswith(".envelope"):
            count += 1
    return count


def _tally(accounts: Sequence[Mapping[str, Any]], field: str) -> dict[str, int]:
    counts = {name: 0 for name in ACCOUNT_KINDS}
    for account in accounts:
        roles = account.get(field) or []
        for role in roles:
            if role in counts:
                counts[role] += 1
    return counts


def _tally_status(accounts: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = {name: 0 for name in sorted(ACCOUNT_STATUSES)}
    for account in accounts:
        status = account.get("status")
        if status in counts:
            counts[status] += 1
    return counts


def _role_code(code: str) -> str:
    if code in {"actor_lacks_role_authority", "actor_cannot_drop_own_staff_role", "unknown_role", "revision_conflict", "missing_principal"}:
        return code
    return "action_not_permitted"


def admin_http_status(code: str) -> int:
    if code in {"unauthenticated", "account_disabled", "authority_stale", "request_body"}:
        return 401
    if code == "revision_conflict":
        return 409
    if code in {"admin_unavailable", "audit_export_unavailable"}:
        return 503
    if code == "missing_principal":
        return 404
    if code in {"assignment_status_unavailable", "storage_state_unavailable", "worker_state_unavailable"}:
        return 503
    return 403


def mount_operational_admin(app: Any) -> None:
    """Mount the directory page and API. Session checks run in case route composition."""

    from fastapi.responses import HTMLResponse, JSONResponse
    from starlette.concurrency import run_in_threadpool
    from applications.case_audit import CaseAuditError, audit_export_session_verifier

    root = __import__("pathlib").Path(__file__).resolve().parent.parent
    root_page = root / "templates" / "admin.html"
    script_path = root / "static" / "complaint_admin.js"

    def _service(request: Any) -> OperationalAdminService:
        service = getattr(request.app.state, "operational_admin", None)
        if not isinstance(service, OperationalAdminService):
            raise OperationalAdminError("admin_unavailable")
        return service

    def _actor(request: Any) -> tuple[str, tuple[str, ...]]:
        principal = getattr(request.state, "browser_principal", None)
        actor = getattr(principal, "principal_id", None)
        roles = getattr(principal, "roles", None)
        if not isinstance(actor, str) or actor == "" or not isinstance(roles, tuple):
            raise OperationalAdminError("unauthenticated")
        return actor, roles

    def _material(request: Any) -> Mapping[str, Any]:
        material = getattr(request.state, "admin_material", None)
        return material if isinstance(material, dict) else {}

    def _operations_sources(request: Any, service: OperationalAdminService) -> dict[str, Any]:
        state = request.app.state
        return {
            "cases": getattr(state, "case_directory", None) if getattr(state, "case_directory", None) is not None else service._cases,
            "assignments": getattr(state, "case_assignments", None) if getattr(state, "case_assignments", None) is not None else service._assignments,
            "storage": getattr(state, "case_storage", None) if getattr(state, "case_storage", None) is not None else service._storage,
            "memberships": service._memberships,
            "workers": service._workers,
        }

    def _fail(exc: OperationalAdminError) -> JSONResponse:
        return JSONResponse({"error": exc.code}, status_code=admin_http_status(exc.code))

    @app.get(ADMIN_PAGE_PATH)
    async def admin_page():
        html = root_page.read_text(encoding="utf-8")
        return HTMLResponse(html, headers={"cache-control": "no-store"})

    @app.get(ADMIN_SCRIPT_PATH)
    async def admin_script():
        from fastapi.responses import Response
        script = script_path.read_bytes()
        return Response(script, media_type="text/javascript; charset=utf-8", headers={"cache-control": "no-store"})

    @app.get(ADMIN_API_PREFIX + "/accounts")
    async def admin_accounts(request: Request):
        try:
            actor, roles = _actor(request)
            return JSONResponse(_service(request).list_accounts(actor, roles, _material(request)))
        except OperationalAdminError as exc:
            return _fail(exc)

    @app.post(ADMIN_API_PREFIX + "/accounts")
    async def admin_provision(request: Request):
        try:
            actor, roles = _actor(request)
            created = _service(request).provision(actor, roles, _material(request))
        except OperationalAdminError as exc:
            return _fail(exc)
        return JSONResponse(created, status_code=201)

    @app.post(ADMIN_API_PREFIX + "/accounts/{principal_id}/role")
    async def admin_role(principal_id: str, request: Request):
        try:
            actor, roles = _actor(request)
            return JSONResponse(_service(request).change_role(actor, roles, principal_id, _material(request)))
        except OperationalAdminError as exc:
            return _fail(exc)

    @app.post(ADMIN_API_PREFIX + "/accounts/{principal_id}/status")
    async def admin_status(principal_id: str, request: Request):
        try:
            actor, roles = _actor(request)
            return JSONResponse(_service(request).set_status(actor, roles, principal_id, _material(request)))
        except OperationalAdminError as exc:
            return _fail(exc)

    @app.post(ADMIN_API_PREFIX + "/accounts/{principal_id}/audit")
    async def admin_audit_right(principal_id: str, request: Request):
        try:
            actor, roles = _actor(request)
            return JSONResponse(_service(request).set_audit_right(actor, roles, principal_id, _material(request)))
        except OperationalAdminError as exc:
            return _fail(exc)

    @app.get(WORKSPACE_PATH)
    async def admin_workspace(request: Request):
        try:
            actor, roles = _actor(request)
            service = _service(request)
            payload = service.analyze_workspace(actor, roles, _material(request), sources=_operations_sources(request, service))
            return JSONResponse(payload)
        except OperationalAdminError as exc:
            return _fail(exc)

    @app.get(OPERATIONS_PATH)
    async def admin_operations(request: Request):
        try:
            actor, roles = _actor(request)
            service = _service(request)
            payload = service.inspect_operations(actor, roles, _material(request), sources=_operations_sources(request, service))
            return JSONResponse(payload)
        except OperationalAdminError as exc:
            return _fail(exc)

    @app.post(INCIDENT_PATH)
    async def admin_incident(request: Request):
        try:
            actor, roles = _actor(request)
            service = _service(request)
            payload = service.record_incident(actor, roles, _material(request), sources=_operations_sources(request, service))
        except OperationalAdminError as exc:
            return _fail(exc)
        return JSONResponse(payload, status_code=201)

    @app.post(CONTENT_ACCESS_PATH)
    async def admin_content_access(request: Request):
        try:
            actor, roles = _actor(request)
            payload = _service(request).decide_content_access(actor, roles, _material(request))
        except OperationalAdminError as exc:
            return _fail(exc)
        return JSONResponse(payload, status_code=201)

    @app.get(CONTENT_ACCESS_PATH)
    async def admin_content_access_log(request: Request):
        try:
            actor, roles = _actor(request)
            return JSONResponse(_service(request).content_access_log(actor, roles))
        except OperationalAdminError as exc:
            return _fail(exc)

    @app.get(ADMIN_API_PREFIX + "/audit")
    async def admin_audit(request: Request):
        try:
            actor, roles = _actor(request)
            return JSONResponse(_service(request).audit_log(actor, roles))
        except OperationalAdminError as exc:
            return _fail(exc)

    @app.post(ADMIN_API_PREFIX + "/audit/export")
    async def admin_audit_export(request: Request):
        try:
            actor, roles = _actor(request)
            verify = audit_export_session_verifier(request)
            payload = await run_in_threadpool(_service(request).export_audit, actor, roles,
                                             _material(request), verify_access=verify)
            verify()
            return JSONResponse(payload)
        except CaseAuditError as exc:
            return _fail(OperationalAdminError(exc.code))
        except OperationalAdminError as exc:
            return _fail(exc)

    @app.get(ADMIN_API_PREFIX + "/audit/exports/{export_id}")
    async def admin_audit_export_download(export_id: str):
        del export_id
        return JSONResponse({"error": "direct_download_denied"}, status_code=403)
