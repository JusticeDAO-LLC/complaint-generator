"""Authorized case creation, listing, reading, and selection.

The authenticated browser principal is the only actor. A request ``user_id``
is never a directory selector and never widens the result. Newly created cases
stay owner-only: this surface does not invite collaborators or mint key grants.
Explicit membership that already exists on ``CaseActionAuthorizer`` may name a
case, but missing key grants stay closed and ciphertext is not opened.

Each case keeps its own sealed revision and unresolved gaps. Selecting another
case clears that actor's transient UI draft and does not rewrite the other
case's envelope.
"""
from __future__ import annotations

import hashlib
import json
import base64
from contextlib import contextmanager
import fcntl
import os
import stat
import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from starlette.requests import Request

from applications.case_access import CaseAccessError, CaseActionAuthorizer
from applications.case_directory import (
    MEMBERSHIP_OWNER_ONLY,
    CaseDirectory,
    CaseDirectoryError,
    CaseNamespace,
)
from integrations.private_storage import (
    PrivateArtifactBinding,
    PrivateArtifactIntegrityError,
    PrivateStorageError,
    assert_access_matches_binding,
    open_private_artifact,
    seal_private_artifact,
)

TASK_ID = "CIMP-GUI-08"
CATALOG_LIMITATIONS = (
    "newly_created_cases_are_owner_only",
    "key_grants_are_not_issued_here",
    "explicit_membership_without_a_key_grant_does_not_open_ciphertext",
    "unknown_identifiers_do_not_enumerate_other_users",
)
COLLABORATION_FIELDS = frozenset({
    "collaborators",
    "members",
    "memberships",
    "grants",
    "grant",
    "invite",
    "invitees",
    "share_with",
    "lawyer_principal_id",
    "assigned_lawyer",
})
ARTIFACT_KIND = "case-ui-revision"
_MAX_GAPS = 32
_MAX_GAP_LENGTH = 200
_MAX_DRAFT = 4000
_QUEUE_PAGE_MAX = 10
_QUEUE_STATES = ("authorized", "pending", "locked", "revoked")
_QUEUE_SORTS = ("priority", "label", "state", "expires")
_SCOPE_LABELS = {
    "case.read": "Read",
    "case.review": "Review",
    "case.download": "Download",
    "case.message.send": "Message",
}
_STATE_LABELS = {
    "authorized": "Authorized",
    "pending": "Pending acceptance",
    "locked": "Locked",
    "revoked": "Revoked",
}


@dataclass(frozen=True)
class _CanonicalAccess:
    trust: str
    principal_id: str
    case_id: str


@dataclass
class _TransientUI:
    selected_case_id: str | None = None
    draft: str = ""


@dataclass
class _SealedRevision:
    content_revision: int
    envelope: bytes
    gaps: tuple[str, ...]
    label: str


class CaseCatalog:
    """Owner-scoped catalog over ``CaseDirectory`` plus per-case sealed UI state."""

    def __init__(self, cases: CaseDirectory, authorizer: CaseActionAuthorizer, *, key: bytes, key_id: str) -> None:
        if not isinstance(cases, CaseDirectory) or not isinstance(authorizer, CaseActionAuthorizer):
            raise CaseAccessError("authority_owners")
        if not isinstance(key, (bytes, bytearray)) or isinstance(key, memoryview) or len(bytes(key)) != 32:
            raise CaseAccessError("key_material")
        if not isinstance(key_id, str) or key_id.strip() == "" or key_id != key_id.strip():
            raise CaseAccessError("key_id")
        self._cases = cases
        self._authorizer = authorizer
        self._key = bytes(key)
        self._key_id = key_id
        self._ui: dict[str, _TransientUI] = {}
        self._queue_work: dict[str, dict[str, Any]] = {}

    def create(self, actor_principal_id: str, body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        payload = self._body(body)
        if any(name in payload for name in COLLABORATION_FIELDS):
            raise CaseAccessError("collaboration_not_available")
        actor = self._actor(actor_principal_id)
        supplied = payload.get("user_id")
        if supplied is not None and supplied != actor:
            raise CaseAccessError("user_id_not_a_selector")
        label = payload.get("label", "")
        if not isinstance(label, str) or len(label) > _MAX_GAP_LENGTH:
            raise CaseAccessError("label")
        try:
            record = self._cases.create_case(
                actor_principal_id=actor,
                supplied_user_id=actor if isinstance(supplied, str) else None,
            )
        except CaseDirectoryError as exc:
            raise CaseAccessError(exc.code) from exc
        if record.membership != MEMBERSHIP_OWNER_ONLY or record.owner_principal_id != actor:
            raise CaseAccessError("owner_only")
        self._write_sealed(record, content_revision=1, gaps=(), label=label)
        decision = self._authorize_owned(actor, record, action="case.read")
        return self._owner_view(decision, record, switched=False)

    def list_cases(self, actor_principal_id: str) -> dict[str, Any]:
        actor = self._actor(actor_principal_id)
        try:
            records = self._cases.list_cases(actor_principal_id=actor)
        except CaseDirectoryError as exc:
            raise CaseAccessError(exc.code) from exc
        cases = []
        for record in records:
            if record.owner_principal_id != actor or record.membership != MEMBERSHIP_OWNER_ONLY:
                continue
            decision = self._authorize_owned(actor, record, action="case.read")
            cases.append(self._owner_view(decision, record, switched=False))
        return {
            "actor_principal_id": actor,
            "cases": cases,
            "membership": MEMBERSHIP_OWNER_ONLY,
            "limitations": list(CATALOG_LIMITATIONS),
        }

    def read(self, actor_principal_id: str, case_id: str, body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self._open(actor_principal_id, case_id, body, action="case.read", switching=False)

    def select(self, actor_principal_id: str, case_id: str, body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self._open(actor_principal_id, case_id, body, action="case.select", switching=True)

    def set_transient(self, actor_principal_id: str, case_id: str, body: Mapping[str, Any] | None) -> dict[str, Any]:
        actor = self._actor(actor_principal_id)
        payload = self._body(body)
        draft = payload.get("draft", "")
        if not isinstance(draft, str) or len(draft) > _MAX_DRAFT:
            raise CaseAccessError("transient_draft")
        ui = self._ui.setdefault(actor, _TransientUI())
        if ui.selected_case_id != case_id:
            raise CaseAccessError("case_not_selected")
        # Confirm the selected id is still this actor's case before keeping text.
        self.read(actor, case_id, {})
        ui.draft = draft
        return {"actor_principal_id": actor, "selected_case_id": case_id, "transient": {"draft": draft}}

    def set_gaps(self, actor_principal_id: str, case_id: str, body: Mapping[str, Any] | None) -> dict[str, Any]:
        actor = self._actor(actor_principal_id)
        payload = self._body(body)
        record = self._owned(actor, case_id)
        if record is None:
            raise CaseAccessError("missing_case")
        decision = self._authorize_owned(actor, record, action="case.update")
        if decision.membership != "owner":
            raise CaseAccessError("key_grant_required")
        expected = payload.get("expected_content_revision")
        if type(expected) is not int:
            raise CaseAccessError("encrypted_revision_conflict")
        gaps = self._gaps(payload.get("unresolved_gaps"))
        # The same private lock is used by every catalog instance. Read and
        # compare inside the lock so a stale writer cannot overwrite a newer
        # revision merely because its own in-memory view is older.
        with self._revision_lock(record) as directory:
            sealed = self._load_sealed(record, directory)
            if sealed is None or sealed.content_revision != expected:
                raise CaseAccessError("encrypted_revision_conflict")
            self._write_sealed(record, content_revision=sealed.content_revision + 1,
                               gaps=gaps, label=sealed.label, directory=directory)
        return self._owner_view(decision, record, switched=False)

    def record_queue_work(self, actor_principal_id: str, case_id: str, body: Mapping[str, Any] | None) -> dict[str, Any]:
        """Owner-published queue labels. Ciphertext and grant ids stay out of this record."""

        actor = self._actor(actor_principal_id)
        payload = self._body(body)
        record = self._owned(actor, case_id)
        if record is None:
            raise CaseAccessError("missing_case")
        decision = self._authorize_owned(actor, record, action="case.update")
        if decision.membership != "owner":
            raise CaseAccessError("key_grant_required")
        tasks = self._queue_labels(payload.get("review_tasks"), "review_tasks")
        actions = self._queue_labels(payload.get("owner_actions"), "owner_actions")
        label = payload.get("label", "")
        if not isinstance(label, str) or len(label) > _MAX_GAP_LENGTH or label != label.strip():
            raise CaseAccessError("label")
        self._queue_work[record.case_id] = {
            "label": label,
            "review_tasks": tasks,
            "owner_actions": actions,
        }
        return {
            "actor_principal_id": actor,
            "case_id": record.case_id,
            "label": label,
            "review_task_count": len(tasks),
            "owner_action_count": len(actions),
            "published_to_unassigned_lawyers": False,
        }

    def lawyer_review_queue(self, actor_principal_id: str, query: Mapping[str, Any] | None, *, assignments: Any) -> dict[str, Any]:
        """Assigned-lawyer queue. A lawyer role does not list every complaint."""

        actor = self._actor(actor_principal_id)
        if assignments is None or not hasattr(assignments, "list_assignments"):
            raise CaseAccessError("lawyer_queue_unavailable")
        filters = _queue_query(query)
        try:
            listed = assignments.list_assignments(actor)
        except Exception as exc:
            code = getattr(exc, "code", "")
            if code in {"unauthenticated", "missing_principal", "inactive_principal"}:
                raise CaseAccessError("unauthenticated") from exc
            raise CaseAccessError("lawyer_queue_unavailable") from exc
        sessions = getattr(assignments, "_sessions", {})
        session = sessions.get(actor) if isinstance(sessions, Mapping) else None
        unlocked = getattr(session, "unlocked", False) is True
        rows = []
        for view in listed.get("assignments") or []:
            if not isinstance(view, dict) or view.get("party") != "recipient":
                continue
            if view.get("member_principal_id") not in (None, actor) and view.get("member_principal_id") != actor:
                continue
            item = self._queue_item(actor, view, unlocked=unlocked)
            if filters["state"] not in ("", "all") and item["state"] != filters["state"]:
                continue
            if filters["q"] and filters["q"] not in item["display_label"].casefold():
                continue
            rows.append(item)
        reverse = filters["direction"] == "desc"
        rows.sort(key=lambda item: (_queue_sort_value(item, filters["sort"]), item["case_id"]), reverse=reverse)
        total = len(rows)
        page_count = max(1, (total + filters["page_size"] - 1) // filters["page_size"]) if total else 1
        if filters["page"] > page_count:
            raise CaseAccessError("queue_page")
        start = (filters["page"] - 1) * filters["page_size"]
        page_rows = rows[start:start + filters["page_size"]]
        return {
            "actor_principal_id": actor,
            "role_alone_grants_cases": False,
            "unassigned_complaints_included": False,
            "filters": {"state": filters["state"] or "all", "q": filters["q"]},
            "sort": {
                "field": filters["sort"],
                "direction": filters["direction"],
                "labels": {
                    "priority": "Priority",
                    "label": "Label",
                    "state": "Status",
                    "expires": "Expiry",
                },
            },
            "page": {
                "number": filters["page"],
                "page_size": filters["page_size"],
                "total": total,
                "page_count": page_count if total else 0,
            },
            "items": page_rows,
            "empty": total == 0,
            "empty_label": "No assigned cases match this queue.",
            "states": [{"value": name, "label": _STATE_LABELS[name]} for name in _QUEUE_STATES],
        }

    def _queue_item(self, actor: str, view: Mapping[str, Any], *, unlocked: bool) -> dict[str, Any]:
        shown = str(view.get("state") or "")
        scope = [name for name in view.get("scope") or [] if isinstance(name, str)]
        scope_label = ", ".join(_SCOPE_LABELS[name] for name in scope if name in _SCOPE_LABELS) or "Assigned review"
        case_id = str(view.get("case_id") or "")
        if shown in {"removed", "declined", "expired"} or view.get("revoked") is True:
            state = "revoked"
            state_label = {"removed": "Revoked", "declined": "Declined", "expired": "Expired"}.get(shown, "Revoked")
        elif shown == "pending":
            state = "pending"
            state_label = "Pending acceptance"
        elif shown == "accepted" and view.get("change_pending") is True:
            state = "locked"
            state_label = "Locked while an owner change is pending"
        elif shown == "accepted" and view.get("key_grant") == "admitted" and unlocked and view.get("effective", True) is not False:
            state = "authorized"
            state_label = "Authorized"
        elif shown == "accepted":
            state = "locked"
            state_label = "Locked until a key grant is admitted" if view.get("key_grant") != "admitted" else "Locked while the recipient key is unavailable"
        else:
            state = "locked"
            state_label = "Locked"
        work = self._queue_work.get(case_id) if state == "authorized" else None
        review_tasks = [{"label": label, "status_label": "Open"} for label in (work or {}).get("review_tasks") or []]
        owner_actions = [{"label": label, "status_label": "Waiting on owner"} for label in (work or {}).get("owner_actions") or []]
        private_label = (work or {}).get("label") or ""
        if state == "authorized" and private_label:
            display_label = private_label + " — " + scope_label
        else:
            display_label = state_label + " — " + scope_label
        if review_tasks or owner_actions:
            priority = 300 + len(owner_actions) + len(review_tasks)
            priority_label = "High"
        elif state == "pending":
            priority = 150
            priority_label = "Normal"
        elif state == "locked":
            priority = 50
            priority_label = "Low"
        else:
            priority = 10
            priority_label = "Low"
        expires_at = view.get("expires_at") if type(view.get("expires_at")) is int else 0
        return {
            "display_label": display_label,
            "state": state,
            "state_label": state_label,
            "scope_label": scope_label,
            "priority": priority,
            "priority_label": priority_label,
            "review_tasks": review_tasks,
            "pending_owner_actions": owner_actions,
            "case_id": case_id,
            "expires_at": expires_at,
            "control": {"label": display_label, "action": "open-queue-item"},
            "actor_principal_id": actor,
        }

    def session(self, actor_principal_id: str) -> dict[str, Any]:
        actor = self._actor(actor_principal_id)
        ui = self._ui.get(actor) or _TransientUI()
        listed = self.list_cases(actor)
        return {
            "actor_principal_id": actor,
            "selected_case_id": ui.selected_case_id,
            "transient": {"draft": ui.draft},
            "cases": listed["cases"],
            "membership": MEMBERSHIP_OWNER_ONLY,
            "limitations": list(CATALOG_LIMITATIONS),
        }

    def sealed_envelope(self, actor_principal_id: str, case_id: str) -> bytes:
        """Return the actor's own sealed revision bytes. Foreign ids raise ``missing_case``."""

        actor = self._actor(actor_principal_id)
        record = self._owned(actor, case_id)
        if record is None:
            raise CaseAccessError("missing_case")
        self._authorize_owned(actor, record, action="case.read")
        with self._revision_lock(record) as directory:
            sealed = self._load_sealed(record, directory)
        if sealed is None:
            raise CaseAccessError("missing_case")
        return sealed.envelope

    def _open(self, actor_principal_id: str, case_id: str, body: Mapping[str, Any] | None, *, action: str, switching: bool) -> dict[str, Any]:
        actor = self._actor(actor_principal_id)
        payload = self._body(body)
        if any(name in payload for name in COLLABORATION_FIELDS):
            raise CaseAccessError("collaboration_not_available")
        if payload.get("user_id") not in {None, actor}:
            raise CaseAccessError("user_id_not_a_selector")
        record = self._owned(actor, case_id)
        if record is not None:
            used = "case.select" if switching else action
            decision = self._authorize_owned(actor, record, action=used, body=payload)
            view = self._owner_view(decision, record, switched=False)
            if switching:
                view.update(self._switch(actor, record.case_id))
            return view
        decision = self._authorize_explicit(actor, case_id, payload, action="case.read" if switching else action)
        if decision.membership == "owner":
            raise CaseAccessError("missing_case")
        # Policy membership is not a key grant. Do not open or copy ciphertext.
        if switching:
            switched = self._switch(actor, decision.case_id)
        else:
            switched = {"transient_cleared": False, "transient": {"draft": (self._ui.get(actor) or _TransientUI()).draft}}
        return {
            "actor_principal_id": actor,
            "tenant_id": decision.tenant_id,
            "case_id": decision.case_id,
            "resource_id": decision.resource_id,
            "directory_revision": decision.revision,
            "membership": decision.membership,
            "actor_is_encrypted_owner": decision.actor_is_encrypted_owner,
            "canonical_owner_principal_id": decision.canonical_owner_principal_id,
            "plaintext_available": False,
            "key_grant": "required",
            "limitations": list(CATALOG_LIMITATIONS),
            **switched,
        }

    def _switch(self, actor: str, case_id: str) -> dict[str, Any]:
        ui = self._ui.setdefault(actor, _TransientUI())
        switched = ui.selected_case_id != case_id
        if switched:
            ui.draft = ""
        ui.selected_case_id = case_id
        return {"transient_cleared": switched, "selected_case_id": case_id, "transient": {"draft": ui.draft}}

    def _authorize_owned(self, actor: str, record: CaseNamespace, *, action: str, body: Mapping[str, Any] | None = None) -> Any:
        payload = body or {}
        tenant_id = payload.get("tenant_id", record.tenant_id)
        resource_id = payload.get("resource_id", record.resource_id)
        revision = payload.get("expected_revision", record.revision)
        if not isinstance(tenant_id, str) or not isinstance(resource_id, str) or type(revision) is not int:
            raise CaseAccessError("revision_conflict")
        return self._authorizer.authorize(
            boundary="http",
            actor_principal_id=actor,
            tenant_id=tenant_id,
            case_id=record.case_id,
            resource_id=resource_id,
            action=action,
            expected_revision=revision,
            trust="authenticated",
        )

    def _authorize_explicit(self, actor: str, case_id: str, payload: Mapping[str, Any], *, action: str) -> Any:
        tenant_id = payload.get("tenant_id")
        resource_id = payload.get("resource_id")
        revision = payload.get("expected_revision")
        membership_revision = payload.get("expected_membership_revision")
        if not isinstance(tenant_id, str) or tenant_id == "" or not isinstance(resource_id, str) or resource_id == "":
            raise CaseAccessError("missing_case")
        if type(revision) is not int:
            raise CaseAccessError("missing_case")
        if membership_revision is not None and type(membership_revision) is not int:
            raise CaseAccessError("missing_case")
        try:
            return self._authorizer.authorize(
                boundary="http",
                actor_principal_id=actor,
                tenant_id=tenant_id,
                case_id=case_id,
                resource_id=resource_id,
                action=action,
                expected_revision=revision,
                expected_membership_revision=membership_revision if type(membership_revision) is int else None,
                trust="authenticated",
            )
        except CaseAccessError as exc:
            if exc.code in {"tenant_mismatch", "resource_mismatch", "revision_conflict", "membership_required", "action_not_permitted"}:
                raise CaseAccessError("missing_case") from exc
            raise

    def _owned(self, actor: str, case_id: str) -> CaseNamespace | None:
        try:
            return self._cases.select_case(actor_principal_id=actor, case_id=case_id)
        except CaseDirectoryError as exc:
            if exc.code == "missing_case":
                return None
            raise CaseAccessError(exc.code) from exc

    def _owner_view(self, decision: Any, record: CaseNamespace, *, switched: bool) -> dict[str, Any]:
        with self._revision_lock(record) as directory:
            sealed = self._load_sealed(record, directory)
        if sealed is None:
            raise CaseAccessError("case_revision_unavailable")
        opened = self._open_sealed(record, sealed)
        return {
            "actor_principal_id": decision.actor_principal_id,
            "tenant_id": record.tenant_id,
            "case_id": record.case_id,
            "resource_id": record.resource_id,
            "directory_revision": record.revision,
            "encrypted_content_revision": opened["content_revision"],
            "envelope_sha256": hashlib.sha256(sealed.envelope).hexdigest(),
            "unresolved_gaps": list(opened["unresolved_gaps"]),
            "label": opened["label"],
            "membership": MEMBERSHIP_OWNER_ONLY,
            "actor_is_encrypted_owner": decision.actor_is_encrypted_owner,
            "canonical_owner_principal_id": decision.canonical_owner_principal_id,
            "plaintext_available": True,
            "key_grant": "owner",
            "transient_cleared": switched,
            "limitations": list(CATALOG_LIMITATIONS),
        }

    def _write_sealed(self, record: CaseNamespace, *, content_revision: int, gaps: tuple[str, ...],
                      label: str, directory: int | None = None) -> None:
        if directory is None:
            with self._revision_lock(record) as owned:
                if self._load_sealed(record, owned) is not None:
                    raise CaseAccessError("encrypted_revision_conflict")
                return self._write_sealed(record, content_revision=content_revision,
                                          gaps=gaps, label=label, directory=owned)
        document = {
            "content_revision": content_revision,
            "unresolved_gaps": list(gaps),
            "label": label,
            "membership": MEMBERSHIP_OWNER_ONLY,
        }
        binding = self._binding(record, content_revision)
        access = _CanonicalAccess("authenticated", record.tenant_id, record.case_id)
        assert_access_matches_binding(access, binding)
        envelope = seal_private_artifact(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            binding=binding,
            key=self._key,
            key_id=self._key_id,
        )
        raw = json.dumps({"schema": "complaint-case-ui-revision@1", "revision": content_revision,
                          "envelope": base64.b64encode(envelope).decode("ascii")},
                         sort_keys=True, separators=(",", ":")).encode()
        temporary = ".revision-" + uuid.uuid4().hex + ".tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                             0o600, dir_fd=directory)
        try:
            remaining = memoryview(raw)
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    raise CaseAccessError("case_revision_unavailable")
                remaining = remaining[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            os.replace(temporary, "revision.json", src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass

    @contextmanager
    def _revision_lock(self, record: CaseNamespace):
        try:
            path = self._cases.owned_revision_directory(actor_principal_id=record.owner_principal_id,
                                                       case_id=record.case_id)
            directory = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            lock = None
            try:
                info = os.fstat(directory)
                if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                    raise CaseAccessError("case_revision_unavailable")
                lock = os.open(".revision.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
                               0o600, dir_fd=directory)
                self._private_file(os.fstat(lock))
                fcntl.flock(lock, fcntl.LOCK_EX)
                yield directory
            finally:
                if lock is not None:
                    os.close(lock)
                os.close(directory)
        except CaseDirectoryError as exc:
            raise CaseAccessError(exc.code) from exc
        except OSError as exc:
            raise CaseAccessError("case_revision_unavailable") from exc

    @staticmethod
    def _private_file(info):
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
            raise CaseAccessError("case_revision_unavailable")

    def _load_sealed(self, record: CaseNamespace, directory: int) -> _SealedRevision | None:
        try:
            descriptor = os.open("revision.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
        except FileNotFoundError:
            return None
        try:
            before = os.fstat(descriptor)
            self._private_file(before)
            if not 0 < before.st_size <= 65536:
                raise CaseAccessError("case_revision_unavailable")
            raw = os.read(descriptor, before.st_size + 1)
            after = os.fstat(descriptor)
            identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if len(raw) != before.st_size or identity(before) != identity(after):
                raise CaseAccessError("case_revision_unavailable")
        finally:
            os.close(descriptor)
        try:
            value = json.loads(raw)
            if (not isinstance(value, dict) or set(value) != {"schema", "revision", "envelope"}
                    or value["schema"] != "complaint-case-ui-revision@1"
                    or type(value["revision"]) is not int or value["revision"] < 1
                    or not isinstance(value["envelope"], str)):
                raise ValueError("revision")
            sealed = _SealedRevision(value["revision"], base64.b64decode(value["envelope"], validate=True), (), "")
            document = self._open_sealed(record, sealed)
            sealed.gaps = self._gaps(document["unresolved_gaps"])
            sealed.label = document["label"]
            return sealed
        except (ValueError, TypeError, KeyError) as exc:
            raise CaseAccessError("case_revision_unavailable") from exc

    def _open_sealed(self, record: CaseNamespace, sealed: _SealedRevision) -> dict[str, Any]:
        binding = self._binding(record, sealed.content_revision)
        access = _CanonicalAccess("authenticated", record.tenant_id, record.case_id)
        assert_access_matches_binding(access, binding)
        try:
            plaintext = open_private_artifact(sealed.envelope, binding=binding, key=self._key, expected_key_id=self._key_id)
            document = json.loads(plaintext.decode("utf-8"))
        except (PrivateArtifactIntegrityError, PrivateStorageError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CaseAccessError("missing_key") from exc
        if (not isinstance(document, dict) or set(document) != {"content_revision", "unresolved_gaps", "label", "membership"}
                or type(document.get("content_revision")) is not int
                or document["content_revision"] != sealed.content_revision
                or document["membership"] != MEMBERSHIP_OWNER_ONLY
                or not isinstance(document["label"], str) or len(document["label"]) > _MAX_GAP_LENGTH):
            raise CaseAccessError("encrypted_revision_conflict")
        return document

    def _binding(self, record: CaseNamespace, content_revision: int) -> PrivateArtifactBinding:
        return PrivateArtifactBinding(
            tenant_id=record.tenant_id,
            case_id=record.case_id,
            artifact_kind=ARTIFACT_KIND,
            revision=str(content_revision),
            principal_id=record.tenant_id,
        )

    def _key_for(self, record: CaseNamespace) -> tuple[str, str, str]:
        return (record.tenant_id, record.case_id, record.resource_id)

    def _actor(self, actor_principal_id: str) -> str:
        if not isinstance(actor_principal_id, str) or actor_principal_id.strip() == "":
            raise CaseAccessError("unauthenticated")
        return actor_principal_id

    def _body(self, body: Mapping[str, Any] | None) -> Mapping[str, Any]:
        if body is None:
            return {}
        if not isinstance(body, Mapping):
            raise CaseAccessError("request_body")
        return body

    def _gaps(self, value: Any) -> tuple[str, ...]:
        if not isinstance(value, list) or len(value) > _MAX_GAPS:
            raise CaseAccessError("unresolved_gaps")
        gaps = []
        for item in value:
            if not isinstance(item, str) or item.strip() == "" or item != item.strip() or len(item) > _MAX_GAP_LENGTH:
                raise CaseAccessError("unresolved_gaps")
            gaps.append(item)
        return tuple(gaps)

    def _queue_labels(self, value: Any, code: str) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, list) or len(value) > 8:
            raise CaseAccessError(code)
        labels = []
        for item in value:
            if not isinstance(item, str) or item.strip() == "" or item != item.strip() or len(item) > _MAX_GAP_LENGTH:
                raise CaseAccessError(code)
            if item in labels:
                raise CaseAccessError(code)
            labels.append(item)
        return tuple(labels)


def _queue_query(query: Mapping[str, Any] | None) -> dict[str, Any]:
    source = query if isinstance(query, Mapping) else {}
    state = source.get("state", "")
    if state is None:
        state = ""
    if not isinstance(state, str) or state not in {"", "all", *_QUEUE_STATES}:
        raise CaseAccessError("queue_filter")
    sort = source.get("sort", "priority")
    if not isinstance(sort, str) or sort not in _QUEUE_SORTS:
        raise CaseAccessError("queue_filter")
    direction = source.get("direction", "desc" if sort == "priority" else "asc")
    if not isinstance(direction, str) or direction not in {"asc", "desc"}:
        raise CaseAccessError("queue_filter")
    page = _queue_int(source.get("page", "1"), minimum=1, maximum=1000)
    page_size = _queue_int(source.get("page_size", "2"), minimum=1, maximum=_QUEUE_PAGE_MAX)
    text = source.get("q", "")
    if text is None:
        text = ""
    if not isinstance(text, str) or len(text) > _MAX_GAP_LENGTH:
        raise CaseAccessError("queue_filter")
    return {
        "state": "" if state == "all" else state,
        "sort": sort,
        "direction": direction,
        "page": page,
        "page_size": page_size,
        "q": text.casefold().strip(),
    }


def _queue_int(value: Any, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise CaseAccessError("queue_filter")
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    if type(value) is not int or value < minimum or value > maximum:
        raise CaseAccessError("queue_filter")
    return value


def _queue_sort_value(item: Mapping[str, Any], field: str) -> Any:
    if field == "priority":
        return int(item["priority"])
    if field == "expires":
        return int(item["expires_at"])
    if field == "state":
        return _QUEUE_STATES.index(item["state"]) if item["state"] in _QUEUE_STATES else 99
    return str(item["display_label"]).casefold()


def cases_template_text() -> str:
    from pathlib import Path

    return (Path(__file__).resolve().parent.parent / "templates" / "cases.html").read_text(encoding="utf-8")


def mount_case_catalog(app: Any) -> None:
    """Mount catalog routes. The middleware authenticates before these run."""

    from fastapi.responses import HTMLResponse, JSONResponse

    def _fail(exc: CaseAccessError) -> JSONResponse:
        status = {
            "missing_case": 404,
            "encrypted_revision_conflict": 409,
            "revision_conflict": 409,
            "case_catalog_unavailable": 503,
            "case_revision_unavailable": 503,
            "lawyer_queue_unavailable": 503,
            "unauthenticated": 401,
            "authorizer_required": 401,
            "queue_filter": 422,
            "queue_page": 422,
            "review_tasks": 422,
            "owner_actions": 422,
        }.get(exc.code, 403)
        return JSONResponse({"error": exc.code}, status_code=status)

    def _actor(request: Any) -> str:
        principal = getattr(request.state, "browser_principal", None)
        actor = getattr(principal, "principal_id", None)
        if not isinstance(actor, str) or actor == "":
            raise CaseAccessError("unauthenticated")
        return actor

    def _catalog(request: Any) -> CaseCatalog:
        catalog = getattr(request.app.state, "case_catalog", None)
        if not isinstance(catalog, CaseCatalog):
            raise CaseAccessError("case_catalog_unavailable")
        return catalog

    def _material(request: Any) -> dict[str, Any]:
        material = getattr(request.state, "case_catalog_material", None)
        if isinstance(material, dict):
            return material
        return {}

    @app.get("/cases")
    async def cases_page():
        return HTMLResponse(cases_template_text())

    @app.get("/api/cases/session")
    async def case_session(request: Request):
        try:
            return JSONResponse(_catalog(request).session(_actor(request)))
        except CaseAccessError as exc:
            return _fail(exc)

    @app.get("/api/cases/lawyer-queue")
    async def lawyer_review_queue(request: Request):
        try:
            assignments = getattr(request.app.state, "case_assignments", None)
            return JSONResponse(_catalog(request).lawyer_review_queue(
                _actor(request), request.query_params, assignments=assignments))
        except CaseAccessError as exc:
            return _fail(exc)

    @app.get("/api/cases")
    async def case_list(request: Request):
        try:
            return JSONResponse(_catalog(request).list_cases(_actor(request)))
        except CaseAccessError as exc:
            return _fail(exc)

    @app.post("/api/cases")
    async def case_create(request: Request):
        try:
            created = _catalog(request).create(_actor(request), _material(request))
        except CaseAccessError as exc:
            return _fail(exc)
        return JSONResponse(created, status_code=201)

    @app.get("/api/cases/{case_id}")
    async def case_read(case_id: str, request: Request):
        try:
            return JSONResponse(_catalog(request).read(_actor(request), case_id, _material(request)))
        except CaseAccessError as exc:
            return _fail(exc)

    @app.post("/api/cases/{case_id}/select")
    async def case_select(case_id: str, request: Request):
        try:
            return JSONResponse(_catalog(request).select(_actor(request), case_id, _material(request)))
        except CaseAccessError as exc:
            return _fail(exc)

    @app.post("/api/cases/{case_id}/transient")
    async def case_transient(case_id: str, request: Request):
        try:
            return JSONResponse(_catalog(request).set_transient(_actor(request), case_id, _material(request)))
        except CaseAccessError as exc:
            return _fail(exc)

    @app.post("/api/cases/{case_id}/queue-work")
    async def case_queue_work(case_id: str, request: Request):
        try:
            recorded = _catalog(request).record_queue_work(_actor(request), case_id, _material(request))
        except CaseAccessError as exc:
            return _fail(exc)
        return JSONResponse(recorded)

    @app.post("/api/cases/{case_id}/gaps")
    async def case_gaps(case_id: str, request: Request):
        try:
            return JSONResponse(_catalog(request).set_gaps(_actor(request), case_id, _material(request)))
        except CaseAccessError as exc:
            return _fail(exc)
