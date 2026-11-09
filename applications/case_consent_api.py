"""Persist case-specific processing consent.

Each case starts local-private. Grok processing is allowed only after the case
owner explicitly authorizes one purpose. Revocation returns that purpose to
local-private and bumps the consent generation so a late result cannot reuse
the earlier choice.

Lawyer membership, an operational-admin role, development Grok authorization,
and receipt of a message do not create or imply egress consent. This module
does not call a model and does not claim WebSocket or SSE.
"""

from __future__ import annotations

import hashlib
import json
import os
import fcntl
import stat
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

from starlette.requests import Request

from applications.case_access import CaseActionAuthorizer, CaseAccessError
from applications.browser_sessions import BrowserSessionError, BrowserSessionService, SESSION_COOKIE
from applications.case_directory import CaseDirectory, CaseDirectoryError
from integrations.ipfs_datasets.llm import (
    OPERATION_CONSENT_CONTRACT,
    OPERATION_CONSENT_VERSION,
    PRIVACY_GROK_MODEL,
    PRIVACY_GROK_PROVIDER,
    PRIVACY_PROCESSING_GROK,
    PRIVACY_PROCESSING_LOCAL,
)
from integrations.private_storage import (
    PrivateArtifactBinding,
    PrivateArtifactIntegrityError,
    PrivateStorageError,
    open_private_artifact,
    seal_private_artifact,
)

TASK_ID = "CIMP-GUI-33"
CONSENT_KIND = "case_processing_consent"
CONSENT_REVISION = "current"
CONSENT_CONTRACT = "case_processing_consent"
CONSENT_VERSION = "1"
MAX_CONSENT_BYTES = 64 * 1024
MODES = (PRIVACY_PROCESSING_LOCAL, PRIVACY_PROCESSING_GROK)
PURPOSE_DATA_CLASS = {
    "extract_facts": "raw_intake",
    "propose_questions": "raw_intake",
    "explain_candidate": "raw_intake",
    "citation_acquisition": "public_legal_source_graph",
    "public_law_citation": "public_legal_source_graph",
}
IMPLICATIONS = (
    "lawyer_membership",
    "admin_role",
    "development_grok_authorization",
    "message_receipt",
)
DOES_NOT_CREATE_CONSENT = (
    "key_unlock",
    "staff_role",
    "development_provider_authorization",
    "omitted_flags",
)
MINIMIZED_EGRESS = {
    "extract_facts": {
        "provider": PRIVACY_GROK_PROVIDER,
        "model": PRIVACY_GROK_MODEL,
        "data_class": "raw_intake",
        "leaves_the_machine": (
            "bounded source_text fragment for this purpose",
            "target_ref for that fragment",
        ),
        "stays_on_the_machine": (
            "the rest of the complaint",
            "attachments and evidence bytes",
            "drafts, keys, logs, and other purposes",
        ),
    },
    "propose_questions": {
        "provider": PRIVACY_GROK_PROVIDER,
        "model": PRIVACY_GROK_MODEL,
        "data_class": "raw_intake",
        "leaves_the_machine": (
            "gap_code for the open question",
            "target_ref for that gap",
        ),
        "stays_on_the_machine": (
            "the complaint narrative",
            "attachments and evidence bytes",
            "drafts, keys, logs, and other purposes",
        ),
    },
    "explain_candidate": {
        "provider": PRIVACY_GROK_PROVIDER,
        "model": PRIVACY_GROK_MODEL,
        "data_class": "raw_intake",
        "leaves_the_machine": (
            "candidate_ref for the suggestion being explained",
            "gap_code for that candidate",
        ),
        "stays_on_the_machine": (
            "the complaint narrative",
            "attachments and evidence bytes",
            "drafts, keys, logs, and other purposes",
        ),
    },
    "citation_acquisition": {
        "provider": PRIVACY_GROK_PROVIDER,
        "model": PRIVACY_GROK_MODEL,
        "data_class": "public_legal_source_graph",
        "leaves_the_machine": (
            "public citation text only",
        ),
        "stays_on_the_machine": (
            "complaint text is not copied into the citation query",
            "attachments, evidence bytes, drafts, and keys",
        ),
    },
    "public_law_citation": {
        "provider": PRIVACY_GROK_PROVIDER,
        "model": PRIVACY_GROK_MODEL,
        "data_class": "public_legal_source_graph",
        "leaves_the_machine": (
            "public citation text only",
        ),
        "stays_on_the_machine": (
            "complaint text is not copied into the citation query",
            "attachments, evidence bytes, drafts, and keys",
        ),
    },
}
_IMPLIED_FIELDS = frozenset({
    "lawyer_membership",
    "admin_role",
    "development_grok_authorization",
    "development_grok_authorized",
    "message_receipt",
    "message_received",
    "is_admin",
    "is_lawyer",
    "is_member",
    "membership",
    "role",
    "roles",
    "staff_role",
    "staff",
    "staff_roles",
    "is_staff",
    "key_unlock",
    "key_unlocked",
    "unlocked",
    "unlock",
    "development_provider_authorization",
    "development_provider_authorized",
    "development_authorization",
    "provider_authorized",
    "grok_cli_authorized",
    "omitted_flag",
    "omitted_flags",
    "allow_remote",
    "cloud_processing",
    "trusted_local",
    "trust",
})
LIMITATIONS = (
    "default_is_local_private",
    "grok_requires_explicit_case_purpose",
    "lawyer_membership_does_not_imply_egress",
    "admin_role_does_not_imply_egress",
    "development_grok_authorization_does_not_imply_egress",
    "message_receipt_does_not_imply_egress",
    "revocation_bumps_generation",
    "cancellation_rechecked_before_late_result",
    "key_unlock_does_not_create_consent",
    "staff_role_does_not_create_consent",
    "development_provider_authorization_does_not_create_consent",
    "omitted_flags_do_not_create_consent",
    "no_model_dispatch",
    "no_websocket_or_sse",
)


class CaseConsentError(Exception):
    """Fail-closed consent error. ``code`` is a stable machine reason."""

    def __init__(self, code: str) -> None:
        self.code = str(code)
        super().__init__(self.code)


def consent_http_status(code: str) -> int:
    if code in {"missing_case", "missing_purpose"}:
        return 404
    if code in {"revision_conflict"}:
        return 409
    if code in {"unauthenticated", "request_body"}:
        return 401
    if code == "consent_unavailable":
        return 503
    return 403


def _label(value: Any, code: str) -> str:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise CaseConsentError(code)
    if any(char in value for char in ("\x00", "\n", "\r", "/", "\\")):
        raise CaseConsentError(code)
    return value


def _result_id(value: Any) -> str:
    label = _label(value, "missing_result")
    if len(label) > 64:
        raise CaseConsentError("missing_result")
    return label


def _minimized_egress(purpose: str) -> dict[str, Any]:
    spec = MINIMIZED_EGRESS[purpose]
    return {
        "provider": spec["provider"],
        "model": spec["model"],
        "data_class": spec["data_class"],
        "leaves_the_machine": list(spec["leaves_the_machine"]),
        "stays_on_the_machine": list(spec["stays_on_the_machine"]),
        "requires_persisted_case_purpose_consent": True,
    }


def _generation(value: Any) -> int:
    if type(value) is not int or isinstance(value, bool) or value < 0:
        raise CaseConsentError("revision_conflict")
    return value


def _blank_decision(purpose: str) -> dict[str, Any]:
    return {
        "purpose": purpose,
        "data_class": PURPOSE_DATA_CLASS[purpose],
        "mode": PRIVACY_PROCESSING_LOCAL,
        "explicit": False,
        "revoked": False,
        "provider": "",
        "model": "",
        "generation": 0,
    }


def _display(decision: Mapping[str, Any]) -> str:
    if decision.get("revoked") is True or (
        decision.get("mode") == PRIVACY_PROCESSING_LOCAL and int(decision.get("generation") or 0) > 0 and decision.get("explicit") is not True
    ):
        if decision.get("revoked") is True:
            return (
                "Revoked: Grok processing for this purpose is not authorized. "
                "Processing is local private."
            )
    if decision.get("mode") == PRIVACY_PROCESSING_GROK and decision.get("explicit") is True and decision.get("revoked") is not True:
        return (
            "Explicitly authorized Grok processing: grok_cli / grok-4.7 for this case and purpose."
        )
    return "Local private: this purpose never calls a remote provider."


def _egress(decision: Mapping[str, Any]) -> bool:
    return (
        decision.get("mode") == PRIVACY_PROCESSING_GROK
        and decision.get("explicit") is True
        and decision.get("revoked") is not True
        and decision.get("provider") == PRIVACY_GROK_PROVIDER
        and decision.get("model") == PRIVACY_GROK_MODEL
    )


class CaseConsentService:
    """Owner-only persisted processing choices, one record per case."""

    def __init__(self, root: str | Path, *, cases: CaseDirectory, key: bytes, key_id: str, clock: Callable[[], int]) -> None:
        if not isinstance(cases, CaseDirectory):
            raise CaseConsentError("authority_owners")
        if not isinstance(key, (bytes, bytearray)) or isinstance(key, memoryview) or len(bytes(key)) != 32:
            raise CaseConsentError("key_material")
        if not callable(clock):
            raise CaseConsentError("authority_owners")
        self._cases = cases
        self._key = bytes(key)
        self._key_id = _label(key_id, "key_id")
        self._clock = clock
        self._root = Path(root).absolute()
        if self._root.resolve() != self._root:
            raise CaseConsentError("consent_unavailable")
        self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._check_root()

    def read(self, actor_principal_id: str, case_id: str, *,
             authorizer: CaseActionAuthorizer | None = None, verify_session: Callable[[], None] | None = None) -> dict[str, Any]:
        with self._lock():
            if verify_session is not None:
                verify_session()
            record = self._owned(actor_principal_id, case_id)
            self._authorize(authorizer, actor_principal_id, record, "case.read", {}, verify_session)
            stored = self._load(record)
            self._authorize(authorizer, actor_principal_id, record, "case.read", {}, verify_session)
        return self._view(record, stored)

    def choose(self, actor_principal_id: str, case_id: str, body: Mapping[str, Any], *,
               authorizer: CaseActionAuthorizer | None = None, verify_session: Callable[[], None] | None = None) -> dict[str, Any]:
        material = self._body(body)
        self._reject_implications(material)
        purpose = _label(material.get("purpose"), "missing_purpose")
        if purpose not in PURPOSE_DATA_CLASS:
            raise CaseConsentError("missing_purpose")
        mode = _label(material.get("mode"), "mode_required")
        if mode not in MODES:
            raise CaseConsentError("mode_required")
        expected = _generation(material.get("expected_generation"))
        explicit = material.get("explicit_case_purpose") is True
        if mode == PRIVACY_PROCESSING_GROK and not explicit:
            raise CaseConsentError("explicit_case_purpose_required")
        if mode == PRIVACY_PROCESSING_LOCAL and explicit:
            raise CaseConsentError("explicit_case_purpose_required")
        with self._lock():
            if verify_session is not None:
                verify_session()
            record = self._owned(actor_principal_id, case_id)
            admit = lambda: self._authorize(authorizer, actor_principal_id, record, "case.processing.choose", material, verify_session)
            admit()
            stored = self._load(record)
            current = int(stored["generation"])
            if expected != current:
                raise CaseConsentError("revision_conflict")
            generation = current + 1
            cancelled = list(stored.get("cancelled_results") or [])
            decisions = {key: dict(value) for key, value in stored["decisions"].items()}
            decision = dict(decisions[purpose])
            decision["generation"] = generation
            decision["data_class"] = PURPOSE_DATA_CLASS[purpose]
            if mode == PRIVACY_PROCESSING_GROK:
                decision.update({
                    "mode": PRIVACY_PROCESSING_GROK,
                    "explicit": True,
                    "revoked": False,
                    "provider": PRIVACY_GROK_PROVIDER,
                    "model": PRIVACY_GROK_MODEL,
                })
            else:
                decision.update({
                    "mode": PRIVACY_PROCESSING_LOCAL,
                    "explicit": False,
                    "revoked": decisions[purpose].get("mode") == PRIVACY_PROCESSING_GROK or decisions[purpose].get("revoked") is True,
                    "provider": "",
                    "model": "",
                })
            decisions[purpose] = decision
            stored = {
                "contract": CONSENT_CONTRACT,
                "version": CONSENT_VERSION,
                "tenant_id": record.tenant_id,
                "case_id": record.case_id,
                "owner_principal_id": record.owner_principal_id,
                "generation": generation,
                "decided_at": self._now(),
                "decisions": decisions,
                "cancelled_results": cancelled,
            }
            self._write(record, stored, admit=admit)
        return self._view(record, stored)

    def revoke(self, actor_principal_id: str, case_id: str, body: Mapping[str, Any], *,
               authorizer: CaseActionAuthorizer | None = None, verify_session: Callable[[], None] | None = None) -> dict[str, Any]:
        material = self._body(body)
        self._reject_implications(material)
        purpose = _label(material.get("purpose"), "missing_purpose")
        if purpose not in PURPOSE_DATA_CLASS:
            raise CaseConsentError("missing_purpose")
        material = dict(material)
        material["mode"] = PRIVACY_PROCESSING_LOCAL
        material.pop("explicit_case_purpose", None)
        return self.choose(actor_principal_id, case_id, material, authorizer=authorizer, verify_session=verify_session)

    def admit_late_result(self, actor_principal_id: str, case_id: str, body: Mapping[str, Any], *,
                          authorizer: CaseActionAuthorizer | None = None, verify_session: Callable[[], None] | None = None) -> dict[str, Any]:
        """Recheck persisted consent before a late Grok result may be shown."""

        material = self._body(body)
        self._reject_implications(material)
        purpose = _label(material.get("purpose"), "missing_purpose")
        if purpose not in PURPOSE_DATA_CLASS:
            raise CaseConsentError("missing_purpose")
        if "consent_generation" not in material or "expected_generation" not in material or "result_id" not in material:
            raise CaseConsentError("consent_not_implied")
        result_id = _result_id(material.get("result_id"))
        consent_generation = _generation(material.get("consent_generation"))
        expected = _generation(material.get("expected_generation"))
        with self._lock():
            if verify_session is not None:
                verify_session()
            record = self._owned(actor_principal_id, case_id)
            self._authorize(authorizer, actor_principal_id, record, "case.read", material, verify_session)
            stored = self._load(record)
            self._authorize(authorizer, actor_principal_id, record, "case.read", material, verify_session)
            if expected != int(stored["generation"]):
                raise CaseConsentError("revision_conflict")
        return self._admission(record, stored, purpose, result_id, consent_generation)

    def cancel_late_result(self, actor_principal_id: str, case_id: str, body: Mapping[str, Any], *,
                           authorizer: CaseActionAuthorizer | None = None, verify_session: Callable[[], None] | None = None) -> dict[str, Any]:
        """Remember a cancelled result so a late copy cannot be admitted later."""

        material = self._body(body)
        self._reject_implications(material)
        purpose = _label(material.get("purpose"), "missing_purpose")
        if purpose not in PURPOSE_DATA_CLASS:
            raise CaseConsentError("missing_purpose")
        if "result_id" not in material or "expected_generation" not in material:
            raise CaseConsentError("consent_not_implied")
        result_id = _result_id(material.get("result_id"))
        expected = _generation(material.get("expected_generation"))
        with self._lock():
            if verify_session is not None:
                verify_session()
            record = self._owned(actor_principal_id, case_id)
            admit = lambda: self._authorize(authorizer, actor_principal_id, record, "case.read", material, verify_session)
            admit()
            stored = self._load(record)
            if expected != int(stored["generation"]):
                raise CaseConsentError("revision_conflict")
            cancelled = list(stored.get("cancelled_results") or [])
            if result_id not in cancelled:
                cancelled.append(result_id)
            stored["cancelled_results"] = cancelled[-32:]
            self._write(record, stored, admit=admit)
            stored = self._load(record)
        return self._admission(record, stored, purpose, result_id, _generation(stored["decisions"][purpose].get("generation")))

    @staticmethod
    def _authorize(authorizer, actor, record, action, material, verify_session=None) -> None:
        # Direct service calls retain the original owner-directory API. HTTP
        # always supplies the configured canonical authorizer below; requests
        # cannot provide or replace this server-owned object.
        if verify_session is not None:
            verify_session()
        if authorizer is None:
            return
        if not isinstance(authorizer, CaseActionAuthorizer):
            raise CaseConsentError("consent_unavailable")
        claims = {"actor_principal_id": actor, "user_id": actor,
                  "tenant_id": record.tenant_id, "case_id": record.case_id,
                  "resource_id": record.resource_id, "owner_principal_id": record.owner_principal_id}
        if any(name in material and material[name] != value for name, value in claims.items()):
            raise CaseConsentError("case_scope_mismatch")
        if "expected_revision" in material and (
                type(material["expected_revision"]) is not int or material["expected_revision"] != record.revision):
            raise CaseConsentError("revision_conflict")
        if "action" in material and material["action"] != action:
            raise CaseConsentError("action_not_permitted")
        try:
            decision = authorizer.authorize(boundary="http", actor_principal_id=actor,
                tenant_id=record.tenant_id, case_id=record.case_id, resource_id=record.resource_id,
                expected_revision=record.revision, action=action)
        except CaseAccessError as exc:
            raise CaseConsentError(exc.code) from exc
        if decision.membership != "owner" or decision.actor_principal_id != actor:
            raise CaseConsentError("missing_case")
        if verify_session is not None:
            verify_session()

    def _owned(self, actor_principal_id: str, case_id: str):
        actor = _label(actor_principal_id, "unauthenticated")
        try:
            record = self._cases.select_case(actor_principal_id=actor, case_id=case_id)
        except CaseDirectoryError as exc:
            code = "missing_case" if exc.code in {"missing_case", "case_id", "user_id_not_a_selector"} else exc.code
            raise CaseConsentError(code) from exc
        if record.owner_principal_id != actor:
            raise CaseConsentError("missing_case")
        return record

    def _body(self, body: Mapping[str, Any]) -> Mapping[str, Any]:
        if not isinstance(body, Mapping):
            raise CaseConsentError("request_body")
        return body

    def _reject_implications(self, body: Mapping[str, Any]) -> None:
        if any(name in body for name in _IMPLIED_FIELDS):
            raise CaseConsentError("consent_not_implied")

    def _now(self) -> int:
        value = self._clock()
        if type(value) is not int or isinstance(value, bool):
            raise CaseConsentError("clock")
        return value

    def _path(self, record) -> Path:
        identity = json.dumps([record.tenant_id, record.case_id, record.resource_id], separators=(",", ":"))
        return self._root / hashlib.sha256(identity.encode()).hexdigest()

    def _binding(self, record) -> PrivateArtifactBinding:
        return PrivateArtifactBinding(
            tenant_id=record.tenant_id,
            case_id=record.case_id,
            artifact_kind=CONSENT_KIND,
            revision=CONSENT_REVISION,
            principal_id=record.owner_principal_id,
        )

    def _empty(self, record) -> dict[str, Any]:
        return {
            "contract": CONSENT_CONTRACT,
            "version": CONSENT_VERSION,
            "tenant_id": record.tenant_id,
            "case_id": record.case_id,
            "owner_principal_id": record.owner_principal_id,
            "generation": 0,
            "decided_at": 0,
            "decisions": {purpose: _blank_decision(purpose) for purpose in PURPOSE_DATA_CLASS},
            "cancelled_results": [],
        }

    def _load(self, record) -> dict[str, Any]:
        path = self._path(record)
        try:
            self._check_root()
            try:
                descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            except FileNotFoundError:
                return self._empty(record)
            try:
                info = os.fstat(descriptor)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1
                        or stat.S_IMODE(info.st_mode) != 0o600 or not 0 < info.st_size <= MAX_CONSENT_BYTES):
                    raise CaseConsentError("consent_unavailable")
                with os.fdopen(os.dup(descriptor), "rb") as stream:
                    envelope = stream.read(MAX_CONSENT_BYTES + 1)
                after = os.fstat(descriptor)
                if len(envelope) != info.st_size or any(getattr(info, key) != getattr(after, key)
                        for key in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")):
                    raise CaseConsentError("consent_unavailable")
            finally:
                os.close(descriptor)
            plaintext = open_private_artifact(
                envelope,
                binding=self._binding(record),
                key=self._key,
                expected_key_id=self._key_id,
            )
            document = json.loads(plaintext.decode("utf-8"))
        except (PrivateArtifactIntegrityError, PrivateStorageError, OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CaseConsentError("consent_unavailable") from exc
        if (not isinstance(document, dict) or document.get("case_id") != record.case_id
                or document.get("contract") != CONSENT_CONTRACT or document.get("version") != CONSENT_VERSION):
            raise CaseConsentError("consent_unavailable")
        if document.get("tenant_id") != record.tenant_id or document.get("owner_principal_id") != record.owner_principal_id:
            raise CaseConsentError("consent_unavailable")
        decisions = document.get("decisions")
        if not isinstance(decisions, dict) or set(decisions) != set(PURPOSE_DATA_CLASS):
            raise CaseConsentError("consent_unavailable")
        try:
            document["generation"] = _generation(document.get("generation"))
            for purpose, decision in decisions.items():
                if (not isinstance(decision, dict) or decision.get("purpose") != purpose
                        or decision.get("data_class") != PURPOSE_DATA_CLASS[purpose]
                        or decision.get("mode") not in MODES
                        or type(decision.get("explicit")) is not bool or type(decision.get("revoked")) is not bool
                        or _generation(decision.get("generation")) > document["generation"]):
                    raise CaseConsentError("consent_unavailable")
        except CaseConsentError as exc:
            raise CaseConsentError("consent_unavailable") from exc
        cancelled = document.get("cancelled_results", [])
        if not isinstance(cancelled, list) or len(cancelled) > 32:
            raise CaseConsentError("consent_unavailable")
        try:
            document["cancelled_results"] = [_result_id(item) for item in cancelled]
        except CaseConsentError as exc:
            raise CaseConsentError("consent_unavailable") from exc
        return document

    def _write(self, record, document: dict[str, Any], *, admit: Callable[[], None]) -> None:
        payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        temporary = None
        try:
            self._check_root()
            envelope = seal_private_artifact(payload, binding=self._binding(record), key=self._key, key_id=self._key_id)
            descriptor, name = tempfile.mkstemp(prefix=".consent-", dir=self._root)
            temporary = Path(name)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(envelope)
                stream.flush()
                os.fsync(stream.fileno())
            self._check_root()
            admit()
            os.replace(temporary, self._path(record))
            directory = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except (PrivateStorageError, OSError) as exc:
            raise CaseConsentError("consent_unavailable") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _check_root(self) -> None:
        try:
            info = self._root.lstat()
            if (self._root.resolve() != self._root or not stat.S_ISDIR(info.st_mode)
                    or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700):
                raise CaseConsentError("consent_unavailable")
        except OSError as exc:
            raise CaseConsentError("consent_unavailable") from exc

    def _lock(self):
        self._check_root()
        class _Guard:
            def __init__(self, root: Path) -> None:
                try:
                    self._fd = os.open(root / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
                    info = os.fstat(self._fd)
                    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                            or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
                        os.close(self._fd)
                        raise CaseConsentError("consent_unavailable")
                except OSError as exc:
                    raise CaseConsentError("consent_unavailable") from exc

            def __enter__(self):
                fcntl.flock(self._fd, fcntl.LOCK_EX)
                return self

            def __exit__(self, *_args):
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)

        return _Guard(self._root)

    def _view(self, record, stored: Mapping[str, Any]) -> dict[str, Any]:
        decisions = []
        grants = []
        for purpose in PURPOSE_DATA_CLASS:
            raw = dict(stored["decisions"][purpose])
            item = {
                "purpose": purpose,
                "data_class": PURPOSE_DATA_CLASS[purpose],
                "mode": raw.get("mode") if raw.get("mode") in MODES else PRIVACY_PROCESSING_LOCAL,
                "explicit": raw.get("explicit") is True and raw.get("mode") == PRIVACY_PROCESSING_GROK and raw.get("revoked") is not True,
                "revoked": raw.get("revoked") is True,
                "provider": PRIVACY_GROK_PROVIDER if _egress(raw) else "",
                "model": PRIVACY_GROK_MODEL if _egress(raw) else "",
                "generation": int(raw.get("generation") or 0),
                "egress_authorized": _egress(raw),
                "display": _display(raw),
                "minimized_egress": _minimized_egress(purpose),
            }
            decisions.append(item)
            if item["egress_authorized"]:
                grants.append({
                    "purpose": purpose,
                    "provider_kind": "grok_inference",
                    "provider": PRIVACY_GROK_PROVIDER,
                    "model": PRIVACY_GROK_MODEL,
                    "data_class": item["data_class"],
                    "explicit": True,
                    "tools": False,
                })
        return {
            "task_id": TASK_ID,
            "case_id": record.case_id,
            "tenant_id": record.tenant_id,
            "owner_principal_id": record.owner_principal_id,
            "generation": int(stored["generation"]),
            "processing_choices": list(MODES),
            "decisions": decisions,
            "default_processing": PRIVACY_PROCESSING_LOCAL,
            "egress_authorized": any(item["egress_authorized"] for item in decisions),
            "minimized_egress": {purpose: _minimized_egress(purpose) for purpose in PURPOSE_DATA_CLASS},
            "implications": {name: False for name in IMPLICATIONS},
            "does_not_create_consent": {name: False for name in DOES_NOT_CREATE_CONSENT},
            "operation_consent": {
                "contract": OPERATION_CONSENT_CONTRACT,
                "version": OPERATION_CONSENT_VERSION,
                "user_id": record.owner_principal_id,
                "case_id": record.case_id,
                "generation": int(stored["generation"]),
                "revoked": not grants,
                "grants": grants,
            },
            "limitations": list(LIMITATIONS),
        }

    def _admission(self, record, stored: Mapping[str, Any], purpose: str, result_id: str, consent_generation: int) -> dict[str, Any]:
        raw = dict(stored["decisions"][purpose])
        cancelled = result_id in list(stored.get("cancelled_results") or [])
        if cancelled:
            code = "consent_cancelled"
        elif raw.get("revoked") is True or not _egress(raw):
            code = "consent_revoked" if raw.get("revoked") is True else "local_private"
        elif int(raw.get("generation") or 0) != consent_generation:
            code = "consent_generation_mismatch"
        else:
            code = "current_consent"
        admitted = code == "current_consent"
        return {
            "task_id": "CIMP-UX-12",
            "case_id": record.case_id,
            "purpose": purpose,
            "result_id": result_id,
            "admitted": admitted,
            "display_allowed": admitted,
            "code": code,
            "generation": int(stored["generation"]),
            "consent_generation": int(raw.get("generation") or 0),
            "default_processing": PRIVACY_PROCESSING_LOCAL,
            "minimized_egress": _minimized_egress(purpose),
            "does_not_create_consent": {name: False for name in DOES_NOT_CREATE_CONSENT},
        }


def mount_case_consent(app: Any) -> None:
    """Mount consent routes. Catalog authentication runs before these handlers."""

    from fastapi.responses import JSONResponse

    def _service(request: Any) -> CaseConsentService:
        service = getattr(request.app.state, "case_consent", None)
        if not isinstance(service, CaseConsentService):
            raise CaseConsentError("consent_unavailable")
        return service

    def _authorizer(request: Any) -> CaseActionAuthorizer:
        authority = getattr(request.app.state, "case_authorizer", None)
        if not isinstance(authority, CaseActionAuthorizer):
            raise CaseConsentError("consent_unavailable")
        return authority

    def _actor(request: Any) -> str:
        principal = getattr(request.state, "browser_principal", None)
        actor = getattr(principal, "principal_id", None)
        if not isinstance(actor, str) or actor == "":
            raise CaseConsentError("unauthenticated")
        return actor

    def _session_verifier(request: Any) -> Callable[[], None]:
        sessions = getattr(request.app.state, "browser_sessions", None)
        bound = getattr(request.state, "browser_principal", None)
        if not isinstance(sessions, BrowserSessionService) or bound is None:
            raise CaseConsentError("consent_unavailable")
        token = request.cookies.get(SESSION_COOKIE)
        def verify() -> None:
            try:
                current = sessions.authenticate_token(token)
            except BrowserSessionError as exc:
                raise CaseConsentError("unauthenticated") from exc
            if (current.principal_id != bound.principal_id or current.tenant_id != bound.tenant_id
                    or current.generation != bound.generation):
                raise CaseConsentError("unauthenticated")
        return verify

    def _material(request: Any) -> Mapping[str, Any]:
        material = getattr(request.state, "case_catalog_material", None)
        return material if isinstance(material, dict) else {}

    def _fail(exc: CaseConsentError) -> JSONResponse:
        return JSONResponse({"error": exc.code}, status_code=consent_http_status(exc.code))

    @app.get("/api/cases/{case_id}/processing-consent")
    async def consent_read(case_id: str, request: Request):
        try:
            return JSONResponse(_service(request).read(_actor(request), case_id, authorizer=_authorizer(request),
                verify_session=_session_verifier(request)))
        except CaseConsentError as exc:
            return _fail(exc)

    @app.post("/api/cases/{case_id}/processing-consent")
    async def consent_choose(case_id: str, request: Request):
        try:
            return JSONResponse(_service(request).choose(_actor(request), case_id, _material(request), authorizer=_authorizer(request),
                verify_session=_session_verifier(request)))
        except CaseConsentError as exc:
            return _fail(exc)

    @app.post("/api/cases/{case_id}/processing-consent/revoke")
    async def consent_revoke(case_id: str, request: Request):
        try:
            return JSONResponse(_service(request).revoke(_actor(request), case_id, _material(request), authorizer=_authorizer(request),
                verify_session=_session_verifier(request)))
        except CaseConsentError as exc:
            return _fail(exc)

    @app.post("/api/cases/{case_id}/processing-consent/late-result")
    async def consent_late_result(case_id: str, request: Request):
        try:
            return JSONResponse(_service(request).admit_late_result(_actor(request), case_id, _material(request), authorizer=_authorizer(request),
                verify_session=_session_verifier(request)))
        except CaseConsentError as exc:
            return _fail(exc)

    @app.post("/api/cases/{case_id}/processing-consent/late-result/cancel")
    async def consent_cancel_late_result(case_id: str, request: Request):
        try:
            return JSONResponse(_service(request).cancel_late_result(_actor(request), case_id, _material(request), authorizer=_authorizer(request),
                verify_session=_session_verifier(request)))
        except CaseConsentError as exc:
            return _fail(exc)
