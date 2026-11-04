"""Case-scoped encrypted evidence catalog and ingestion lifecycle.

Artifacts are sealed with the case data key before any byte store sees them.
The public identifier is an opaque evidence id plus an HMAC scope binding over
the canonical tenant, case, and acting principal. A storage receipt records
ciphertext readback only. It does not establish authenticity, relevance,
admissibility, or claim support.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from applications.case_directory import CaseDirectory, CaseDirectoryError, CaseNamespace

from integrations.private_storage import (
    PrivateStorageError,
    KitLocalCiphertextBackend,
    PrivateArtifactBinding,
    UserOwnedKeySession,
    retrieve_private_artifact,
    store_private_artifact,
)

TASK_ID = "CIMP-UX-13"
CLASSIFICATION_TASK_ID = "CIMP-UX-19"
SUPPORT_LINK_TASK_ID = "CIMP-UX-20"
INGESTION_STATUSES = (
    "received",
    "extracted",
    "needs-review",
    "linked",
    "failed",
    "unavailable",
)
LEGAL_QUALITIES = ("authenticity", "relevance", "admissibility", "claim_support")
# These names are ordinary retaliation/HR assumptions. They are never added
# as a menu. A case may offer them only when that exact id is a current gap
# or an admitted requirement in the supplied context, and the offer still
# does not establish support.
_FIXED_ASSUMPTION_IDS = frozenset({
    "protected_activity",
    "employer_knowledge",
    "causation",
    "hr",
    "human_resources",
})
_CLASSIFICATION_ORIGINS = frozenset({"user_label", "ai_suggested", "reviewed_acceptance"})
_SUPPORT_POSTURES = frozenset({"allegation", "hypothesis", "corroboration", "contradiction", "unavailable"})
_SUPPORT_ORIGINS = frozenset({"human_statement", "human_acceptance", "ai_suggested"})
_CHECKBOX_ORIGINS = frozenset({"client_checkbox", "classifier", "user_label", "reviewed_acceptance"})
_ID_TEXT = r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}"
_KIND_CATALOG = "evidence-catalog"
_KIND_ARTIFACT = "evidence-artifact"
_MAX_BYTES = 256 * 1024


class EvidenceWorkspaceError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def legal_qualities() -> dict[str, str]:
    """Receipt and ingestion never establish these legal qualities."""

    return {name: "not_established" for name in LEGAL_QUALITIES}


def _choice_id(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(_ID_TEXT, value):
        return ""
    return value


def _context_text(value: Any, limit: int = 180) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if text != value or any(char in text for char in ("\x00", "\n", "\r")) or len(text) > limit:
        return ""
    return text


def classification_choices_from_context(context: Mapping[str, Any] | None) -> dict[str, Any]:
    """Offer gap and admitted-requirement ids present in this context.

    Missing or incomplete legal lineage stays unknown. Nothing in this menu
    is verified support, governing law, or a hardcoded claim element.
    """

    source = context if isinstance(context, Mapping) else {}
    status = source.get("legal_context_status")
    if status not in {"unknown", "admitted", "unresolved"}:
        status = "unknown"
    graph_revision = _context_text(source.get("factual_graph_revision"), 120)
    source_version = _context_text(source.get("source_version"), 120)
    jurisdiction = _context_text(source.get("jurisdiction"), 120)
    authority_version = _context_text(source.get("authority_version"), 120)
    refused: list[str] = []
    gaps: list[dict[str, Any]] = []
    seen: set[str] = set()
    raw_gaps = source.get("factual_gaps")
    if isinstance(raw_gaps, list):
        for item in raw_gaps:
            if not isinstance(item, Mapping):
                continue
            gap_id = _choice_id(item.get("gap_id") if item.get("gap_id") is not None else item.get("id"))
            if gap_id == "":
                continue
            if gap_id.casefold() in _FIXED_ASSUMPTION_IDS:
                refused.append(gap_id)
                continue
            if gap_id in seen:
                continue
            seen.add(gap_id)
            label = _context_text(item.get("label")) or gap_id
            gaps.append({
                "choice_id": gap_id,
                "target_kind": "factual_gap",
                "label": label,
                "admitted_law": False,
                "legal_requirement": False,
                "establishes_legal_support": False,
            })
    lineage_complete = bool(source_version and jurisdiction and authority_version)
    requirements: list[dict[str, Any]] = []
    if status == "admitted" and lineage_complete:
        raw_requirements = source.get("admitted_requirements")
        if isinstance(raw_requirements, list):
            for item in raw_requirements:
                if not isinstance(item, Mapping) or item.get("admitted_law") is not True:
                    continue
                requirement_id = _choice_id(
                    item.get("requirement_id") if item.get("requirement_id") is not None else item.get("passage_id")
                )
                if requirement_id == "":
                    continue
                if requirement_id.casefold() in _FIXED_ASSUMPTION_IDS:
                    refused.append(requirement_id)
                    continue
                item_source = _context_text(item.get("source_version"), 120)
                item_jurisdiction = _context_text(item.get("jurisdiction"), 120)
                item_authority = _context_text(item.get("authority_version"), 120)
                passage_id = _choice_id(item.get("passage_id"))
                if (item_source != source_version or item_jurisdiction != jurisdiction
                        or item_authority != authority_version or passage_id == ""):
                    continue
                if requirement_id in seen:
                    continue
                seen.add(requirement_id)
                label = _context_text(item.get("label") or item.get("name")) or requirement_id
                requirements.append({
                    "choice_id": requirement_id,
                    "target_kind": "legal_requirement",
                    "label": label,
                    "passage_id": passage_id,
                    "source_version": item_source,
                    "authority_version": item_authority,
                    "jurisdiction": item_jurisdiction,
                    "admitted_law": True,
                    "legal_requirement": True,
                    "admission_verified_by_evidence_workspace": False,
                    "establishes_legal_support": False,
                })
    if status == "admitted" and lineage_complete and requirements:
        legal_status = "admitted"
    elif status == "unresolved":
        legal_status = "unresolved"
    else:
        legal_status = "unknown"
    choices = list(gaps)
    if legal_status == "admitted":
        choices.extend(requirements)
    else:
        choices.append({
            "choice_id": "unknown_legal_context",
            "target_kind": "unknown_legal_context",
            "label": "Legal context is unknown." if legal_status == "unknown" else "Admitted legal requirements are unresolved.",
            "admitted_law": False,
            "legal_requirement": False,
            "establishes_legal_support": False,
        })
    fingerprint_payload = {
        "legal_context_status": legal_status,
        "factual_graph_revision": graph_revision,
        "source_version": source_version if legal_status == "admitted" else "",
        "jurisdiction": jurisdiction if legal_status == "admitted" else "",
        "authority_version": authority_version if legal_status == "admitted" else "",
        "factual_gap_ids": [item["choice_id"] for item in gaps],
        "admitted_requirement_ids": [item["choice_id"] for item in requirements] if legal_status == "admitted" else [],
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "task_id": CLASSIFICATION_TASK_ID,
        "legal_context_status": legal_status,
        "choices": choices,
        "factual_gap_ids": fingerprint_payload["factual_gap_ids"],
        "admitted_requirement_ids": fingerprint_payload["admitted_requirement_ids"],
        "fixed_assumptions_offered": False,
        "refused_fixed_assumptions": refused,
        "hardcoded_elements_used": False,
        "context_fingerprint": fingerprint,
        "factual_graph_revision": graph_revision,
        "source_version": fingerprint_payload["source_version"],
        "jurisdiction": fingerprint_payload["jurisdiction"],
        "authority_version": fingerprint_payload["authority_version"],
        "context_owner": _context_text(source.get("context_owner"), 40) or "request",
        "admission_verified_by_evidence_workspace": False,
        "establishes_legal_support": False,
        "governing_law": False,
    }


def support_targets_from_context(context: Mapping[str, Any] | None) -> dict[str, Any]:
    """Current factual assertions and sourced requirements that a span may cite.

    The evidence workspace does not admit law. A requirement is offered only
    when the same lineage used for classification is present, and an assertion
    is offered only when this context says it is current at the graph revision.
    """

    classified = classification_choices_from_context(context)
    source = context if isinstance(context, Mapping) else {}
    graph_revision = classified["factual_graph_revision"]
    assertions: list[dict[str, Any]] = []
    seen: set[str] = set()
    raw_assertions = source.get("factual_assertions")
    if graph_revision and isinstance(raw_assertions, list):
        for item in raw_assertions:
            if not isinstance(item, Mapping):
                continue
            if item.get("status") != "current":
                continue
            assertion_id = _choice_id(item.get("assertion_id") if item.get("assertion_id") is not None else item.get("id"))
            if assertion_id == "" or assertion_id.casefold() in _FIXED_ASSUMPTION_IDS or assertion_id in seen:
                continue
            if _context_text(item.get("graph_revision"), 120) != graph_revision:
                continue
            text = _context_text(item.get("text") or item.get("label"), 400)
            if text == "":
                continue
            seen.add(assertion_id)
            assertions.append({
                "target_id": assertion_id,
                "target_kind": "factual_assertion",
                "label": text,
                "graph_revision": graph_revision,
                "status": "current",
                "establishes_legal_support": False,
            })
    requirements = []
    if classified["legal_context_status"] == "admitted":
        for item in classified["choices"]:
            if item.get("target_kind") != "legal_requirement":
                continue
            requirements.append({
                "target_id": item["choice_id"],
                "target_kind": "sourced_requirement",
                "label": item.get("label") or item["choice_id"],
                "passage_id": item.get("passage_id") or "",
                "source_version": item.get("source_version") or "",
                "authority_version": item.get("authority_version") or "",
                "jurisdiction": item.get("jurisdiction") or "",
                "admitted_law": True,
                "admission_verified_by_evidence_workspace": False,
                "establishes_legal_support": False,
            })
    return {
        "task_id": SUPPORT_LINK_TASK_ID,
        "legal_context_status": classified["legal_context_status"],
        "factual_graph_revision": graph_revision,
        "source_version": classified["source_version"],
        "context_fingerprint": classified["context_fingerprint"],
        "context_owner": classified["context_owner"],
        "factual_assertions": assertions,
        "sourced_requirements": requirements,
        "admission_verified_by_evidence_workspace": False,
        "establishes_legal_support": False,
        "governing_law": False,
    }


class _SupportMediator:
    """Log sink for the claim-support owner. It grants no workflow authority."""

    def log(self, _event: str, **_kwargs: Any) -> None:
        return None


def _label(value: Any, code: str) -> str:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise EvidenceWorkspaceError(code)
    if any(char in value for char in ("\x00", "\n", "\r", "/", "\\")):
        raise EvidenceWorkspaceError(code)
    if len(value) > 180:
        raise EvidenceWorkspaceError(code)
    return value


def _media(value: Any) -> str:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise EvidenceWorkspaceError("media_type")
    if any(char in value for char in ("\x00", "\n", "\r", "\\")):
        raise EvidenceWorkspaceError("media_type")
    if len(value) > 120 or value.count("/") != 1:
        raise EvidenceWorkspaceError("media_type")
    return value


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _scope_binding(*, key: bytes, tenant_id: str, case_id: str, actor: str, evidence_id: str) -> str:
    material = "\n".join((tenant_id, case_id, actor, evidence_id)).encode("utf-8")
    return hmac.new(key, material, hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class _Access:
    trust: str
    principal_id: str
    case_id: str


@dataclass(frozen=True)
class _KeyScope:
    identity: Mapping[str, str]
    case: CaseNamespace
    session: UserOwnedKeySession
    epoch: int
    key_id: str
    data_key: bytes = field(repr=False)
    verify_request: Callable[[], None] | None = field(default=None, repr=False, compare=False)


class MemoryByteBackend:
    """Process-local ciphertext store. Callers pass already sealed envelopes."""

    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}

    def add(self, data: bytes, pin: bool = True) -> dict[str, Any]:
        cid = "evcid-" + hashlib.sha256(bytes(data)).hexdigest()
        self._blobs[cid] = bytes(data)
        return {"cid": cid, "status": "available", "pinned": bool(pin)}

    def cat(self, cid: str) -> bytes:
        found = self._blobs.get(cid)
        if found is None:
            raise EvidenceWorkspaceError("ciphertext_unavailable")
        return found

    def contains(self, needle: bytes) -> bool:
        return any(needle in blob for blob in self._blobs.values())


class EvidenceWorkspace:
    """Authorized catalog of one actor's evidence inside one owned case."""

    def __init__(self, directory: CaseDirectory, sessions: Mapping[str, UserOwnedKeySession], backend: Any, root: Path) -> None:
        if not isinstance(directory, CaseDirectory) or backend is None:
            raise EvidenceWorkspaceError("evidence_unavailable")
        self._directory = directory
        self._sessions = dict(sessions)
        self._backend = backend
        self._backend_name = KitLocalCiphertextBackend.backend_name if type(backend) is KitLocalCiphertextBackend else "evidence-memory"
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        os.chmod(self._root, 0o700)
        self._lock = threading.RLock()
        self._claim_support = None

    def receive(self, actor: str, body: Mapping[str, Any], *, verify_request: Callable[[], None] | None = None) -> dict[str, Any]:
        identity = self._identity(actor, body)
        content = self._content(body.get("content_base64"), "content_rejected")
        source = _label(body.get("source_filename"), "source_filename")
        original = _label(body.get("original_filename"), "original_filename")
        media = _media(body.get("media_type") or "application/octet-stream")
        self._reject_legal_claims(body)
        with self._lock:
            scope = self._open(identity, verify_request=verify_request)
            case, key_id, data_key = scope.case, scope.key_id, scope.data_key
            document = self._load(identity, case, key_id, data_key, scope)
            prior = document["idempotency"].get(identity["idempotency_key"])
            if prior is not None:
                item = document["items"].get(prior)
                if item is None or item.get("integrity_sha256") != _digest(content) or item.get("source_filename") != source:
                    raise EvidenceWorkspaceError("replay_mismatch")
                self._verify_scope(scope)
                return self._project(item, verified=True)
            evidence_id = "ev-" + hashlib.sha256(os.urandom(32)).hexdigest()[:32]
            version = self._seal_version(
                identity, case, key_id, data_key, evidence_id, 1, "source", content, scope,
            )
            item = {
                "evidence_id": evidence_id,
                "tenant_id": case.tenant_id,
                "case_id": case.case_id,
                "resource_id": identity["resource_id"],
                "actor_principal_id": identity["actor_principal_id"],
                "canonical_owner_principal_id": case.tenant_id,
                "actor_is_canonical_owner": identity["actor_principal_id"] == case.tenant_id,
                "source_filename": source,
                "original_filename": original,
                "media_type": media,
                "ingestion_status": "received",
                "prior_ingestion_status": "",
                "artifact_versions": [version],
                "current_version": 1,
                "integrity_sha256": version["integrity_sha256"],
                "scope_binding": _scope_binding(
                    key=data_key, tenant_id=case.tenant_id, case_id=case.case_id,
                    actor=identity["actor_principal_id"], evidence_id=evidence_id,
                ),
                "complaint_link_id": "",
                "failure_code": "",
                "legal": legal_qualities(),
                "receipt": self._receipt(version),
            }
            document["items"][evidence_id] = item
            document["idempotency"][identity["idempotency_key"]] = evidence_id
            self._save(identity, case, key_id, data_key, document, scope)
            self._verify_scope(scope)
            return self._project(item, verified=True)

    def transition(self, actor: str, body: Mapping[str, Any], *, verify_request: Callable[[], None] | None = None) -> dict[str, Any]:
        identity = self._identity(actor, body, content=False)
        evidence_id = _label(body.get("evidence_id"), "evidence_id")
        action = _label(body.get("action"), "action")
        self._reject_legal_claims(body)
        with self._lock:
            scope = self._open(identity, verify_request=verify_request)
            case, key_id, data_key = scope.case, scope.key_id, scope.data_key
            document = self._load(identity, case, key_id, data_key, scope)
            item = document["items"].get(evidence_id)
            if item is None or item.get("actor_principal_id") != identity["actor_principal_id"]:
                raise EvidenceWorkspaceError("missing_evidence")
            expected = body.get("expected_artifact_version")
            if type(expected) is not int or expected != item["current_version"]:
                raise EvidenceWorkspaceError("revision_conflict")
            if action == "extract":
                self._extract(identity, case, key_id, data_key, item, body, scope)
            elif action == "needs-review":
                if item["ingestion_status"] not in {"received", "extracted"}:
                    raise EvidenceWorkspaceError("lifecycle_conflict")
                self._move(item, "needs-review")
            elif action == "link":
                if item["ingestion_status"] not in {"extracted", "needs-review"}:
                    raise EvidenceWorkspaceError("lifecycle_conflict")
                item["complaint_link_id"] = _label(body.get("complaint_link_id"), "complaint_link_id")
                self._move(item, "linked")
            elif action == "fail":
                item["failure_code"] = _label(body.get("failure_code"), "failure_code")
                self._move(item, "failed")
            else:
                raise EvidenceWorkspaceError("action")
            item["legal"] = legal_qualities()
            self._save(identity, case, key_id, data_key, document, scope)
            self._verify_scope(scope)
            return self._project(item, verified=item["ingestion_status"] != "unavailable")

    def offer_classifiers(self, actor: str, body: Mapping[str, Any], *, verify_request: Callable[[], None] | None = None) -> dict[str, Any]:
        """Return current choices and retire stored choices whose source changed."""

        identity = self._identity(actor, body, content=False, idempotency=False)
        evidence_id = _label(body.get("evidence_id"), "evidence_id")
        version = body.get("artifact_version")
        if type(version) is not int or isinstance(version, bool):
            raise EvidenceWorkspaceError("artifact_version")
        offered = classification_choices_from_context(body.get("case_context") if isinstance(body.get("case_context"), Mapping) else {})
        with self._lock:
            scope = self._open(identity, verify_request=verify_request)
            case, key_id, data_key = scope.case, scope.key_id, scope.data_key
            document = self._load(identity, case, key_id, data_key, scope)
            item = document["items"].get(evidence_id)
            if item is None or item.get("actor_principal_id") != identity["actor_principal_id"]:
                raise EvidenceWorkspaceError("missing_evidence")
            known = {entry.get("version") for entry in item.get("artifact_versions") or []}
            if version not in known:
                raise EvidenceWorkspaceError("artifact_version_mismatch")
            retired = self._retire_classifiers(document, evidence_id, item, offered)
            if retired:
                self._save(identity, case, key_id, data_key, document, scope)
            self._verify_scope(scope)
            return self._classification_view(document, evidence_id, item, offered, retired=retired)

    def record_classifier(self, actor: str, body: Mapping[str, Any], *, verify_request: Callable[[], None] | None = None) -> dict[str, Any]:
        """Store one attributed classifier without turning it into legal support."""

        identity = self._identity(actor, body, content=False)
        evidence_id = _label(body.get("evidence_id"), "evidence_id")
        version = body.get("artifact_version")
        if type(version) is not int or isinstance(version, bool):
            raise EvidenceWorkspaceError("artifact_version")
        origin = body.get("origin")
        if origin not in _CLASSIFICATION_ORIGINS:
            raise EvidenceWorkspaceError("classifier_rejected")
        if any(name in body for name in LEGAL_QUALITIES) or body.get("claim_element") not in {None, ""}:
            raise EvidenceWorkspaceError("legal_quality_rejected")
        if body.get("establishes_legal_support") not in {None, False} or body.get("accepted") not in {None, True, False}:
            raise EvidenceWorkspaceError("classifier_rejected")
        offered = classification_choices_from_context(body.get("case_context") if isinstance(body.get("case_context"), Mapping) else {})
        with self._lock:
            scope = self._open(identity, verify_request=verify_request)
            case, key_id, data_key = scope.case, scope.key_id, scope.data_key
            document = self._load(identity, case, key_id, data_key, scope)
            item = document["items"].get(evidence_id)
            if item is None or item.get("actor_principal_id") != identity["actor_principal_id"]:
                raise EvidenceWorkspaceError("missing_evidence")
            known = {entry.get("version") for entry in item.get("artifact_versions") or []}
            if version not in known:
                raise EvidenceWorkspaceError("artifact_version_mismatch")
            if version != item.get("current_version"):
                raise EvidenceWorkspaceError("artifact_version_mismatch")
            retired = self._retire_classifiers(document, evidence_id, item, offered)
            bucket = document.setdefault("classification_idempotency", {})
            prior_id = bucket.get(identity["idempotency_key"])
            records = document.setdefault("classifiers", [])
            if prior_id is not None:
                prior = next((row for row in records if row.get("classifier_id") == prior_id), None)
                if prior is None or not self._same_classifier_request(prior, body, offered):
                    raise EvidenceWorkspaceError("replay_mismatch")
                if retired:
                    self._save(identity, case, key_id, data_key, document, scope)
                self._verify_scope(scope)
                view = self._public_classifier(prior)
                view["idempotent_replay"] = True
                view["choices"] = offered["choices"]
                view["legal_context_status"] = offered["legal_context_status"]
                return view
            record = self._new_classifier(identity, evidence_id, version, origin, body, offered, records)
            records.append(record)
            bucket[identity["idempotency_key"]] = record["classifier_id"]
            self._save(identity, case, key_id, data_key, document, scope)
            self._verify_scope(scope)
            view = self._public_classifier(record)
            view["idempotent_replay"] = False
            view["choices"] = offered["choices"]
            view["legal_context_status"] = offered["legal_context_status"]
            view["context_fingerprint"] = offered["context_fingerprint"]
            return view

    @property
    def claim_support(self):
        """The case-local ClaimSupportHook that owns fact and support rows."""

        with self._lock:
            if self._claim_support is None:
                from mediator.claim_support_hooks import ClaimSupportHook

                self._claim_support = ClaimSupportHook(
                    _SupportMediator(),
                    db_path=str(self._root / "claim_support.duckdb"),
                )
            return self._claim_support

    def offer_support_links(self, actor: str, body: Mapping[str, Any], *, verify_request: Callable[[], None] | None = None) -> dict[str, Any]:
        """List current targets and retire links whose artifact or source moved."""

        identity = self._identity(actor, body, content=False, idempotency=False)
        evidence_id = _label(body.get("evidence_id"), "evidence_id")
        version = body.get("artifact_version")
        if type(version) is not int or isinstance(version, bool):
            raise EvidenceWorkspaceError("artifact_version")
        offered = support_targets_from_context(body.get("case_context") if isinstance(body.get("case_context"), Mapping) else {})
        with self._lock:
            scope = self._open(identity, verify_request=verify_request)
            case, key_id, data_key = scope.case, scope.key_id, scope.data_key
            document = self._load(identity, case, key_id, data_key, scope)
            item = document["items"].get(evidence_id)
            if item is None or item.get("actor_principal_id") != identity["actor_principal_id"]:
                raise EvidenceWorkspaceError("missing_evidence")
            known = {entry.get("version") for entry in item.get("artifact_versions") or []}
            if version not in known:
                raise EvidenceWorkspaceError("artifact_version_mismatch")
            retired = self._retire_support_links(document, evidence_id, item, offered)
            if retired:
                self._save(identity, case, key_id, data_key, document, scope)
            self._verify_scope(scope)
            return self._support_view(document, evidence_id, item, offered, retired=retired)

    def record_support_link(self, actor: str, body: Mapping[str, Any], *, verify_request: Callable[[], None] | None = None) -> dict[str, Any]:
        """Bind one exact span to a current assertion or sourced requirement.

        Corroboration and contradiction require an explicit human acceptance.
        A checkbox, classifier, or model suggestion cannot become verified
        legal support, and a missing hook stays unavailable.
        """

        identity = self._identity(actor, body, content=False)
        evidence_id = _label(body.get("evidence_id"), "evidence_id")
        version = body.get("artifact_version")
        if type(version) is not int or isinstance(version, bool):
            raise EvidenceWorkspaceError("artifact_version")
        posture = body.get("posture")
        origin = body.get("origin")
        if posture not in _SUPPORT_POSTURES or posture == "unavailable" or origin not in _SUPPORT_ORIGINS:
            raise EvidenceWorkspaceError("support_link_rejected")
        if body.get("client_checkbox") is True or body.get("origin") in _CHECKBOX_ORIGINS:
            raise EvidenceWorkspaceError("support_link_rejected")
        if any(name in body for name in LEGAL_QUALITIES):
            raise EvidenceWorkspaceError("legal_quality_rejected")
        if body.get("establishes_legal_support") not in {None, False} or body.get("verified_legal_support") not in {None, False}:
            raise EvidenceWorkspaceError("support_link_rejected")
        if body.get("classifier_id") not in {None, ""} or body.get("from_classifier") is True:
            raise EvidenceWorkspaceError("support_link_rejected")
        page, span_start, span_end = self._span(body)
        target_kind = body.get("target_kind")
        target_id = _choice_id(body.get("target_id"))
        if target_kind not in {"factual_assertion", "sourced_requirement"} or target_id == "":
            raise EvidenceWorkspaceError("support_link_rejected")
        explicit = body.get("accept") is True and origin == "human_acceptance"
        if posture in {"corroboration", "contradiction"} and not explicit:
            raise EvidenceWorkspaceError("support_link_rejected")
        if posture == "allegation" and origin != "human_statement":
            raise EvidenceWorkspaceError("support_link_rejected")
        if posture == "hypothesis" and origin != "ai_suggested":
            raise EvidenceWorkspaceError("support_link_rejected")
        if posture in {"corroboration", "contradiction"} and origin != "human_acceptance":
            raise EvidenceWorkspaceError("support_link_rejected")
        if origin == "ai_suggested":
            model_id = _label(body.get("model_id"), "support_link_rejected")
            invocation_id = _label(body.get("invocation_id"), "support_link_rejected")
            if explicit:
                raise EvidenceWorkspaceError("support_link_rejected")
        else:
            model_id = ""
            invocation_id = ""
        offered = support_targets_from_context(body.get("case_context") if isinstance(body.get("case_context"), Mapping) else {})
        targets = offered["factual_assertions"] if target_kind == "factual_assertion" else offered["sourced_requirements"]
        target = next((item for item in targets if item.get("target_id") == target_id), None)
        with self._lock:
            scope = self._open(identity, verify_request=verify_request)
            case, key_id, data_key = scope.case, scope.key_id, scope.data_key
            document = self._load(identity, case, key_id, data_key, scope)
            item = document["items"].get(evidence_id)
            if item is None or item.get("actor_principal_id") != identity["actor_principal_id"]:
                raise EvidenceWorkspaceError("missing_evidence")
            known = {entry.get("version") for entry in item.get("artifact_versions") or []}
            if version not in known or version != item.get("current_version"):
                raise EvidenceWorkspaceError("artifact_version_mismatch")
            retired = self._retire_support_links(document, evidence_id, item, offered)
            records = document.setdefault("support_links", [])
            bucket = document.setdefault("support_link_idempotency", {})
            prior_id = bucket.get(identity["idempotency_key"])
            if prior_id is not None:
                prior = next((row for row in records if row.get("support_link_id") == prior_id), None)
                if prior is None or prior.get("request_fingerprint") != self._support_fingerprint(body, offered):
                    raise EvidenceWorkspaceError("replay_mismatch")
                if retired:
                    self._save(identity, case, key_id, data_key, document, scope)
                self._verify_scope(scope)
                view = self._public_support_link(prior)
                view["idempotent_replay"] = True
                return view
            if target is None:
                if retired:
                    self._save(identity, case, key_id, data_key, document, scope)
                self._verify_scope(scope)
                return self._unavailable_support(
                    evidence_id, version, page, span_start, span_end, target_kind, target_id, "target_not_current",
                )
            hook_effect = self._commit_support_hook(
                case.tenant_id, identity["actor_principal_id"], evidence_id, version,
                page, span_start, span_end, posture, explicit, target,
            )
            if hook_effect.get("available") is not True or hook_effect.get("recorded") is not True:
                if retired:
                    self._save(identity, case, key_id, data_key, document, scope)
                self._verify_scope(scope)
                unavailable = self._unavailable_support(
                    evidence_id, version, page, span_start, span_end, target_kind, target_id,
                    str(hook_effect.get("error") or "claim_support_hook_unavailable"),
                )
                unavailable["hook"] = {
                    "available": False,
                    "recorded": False,
                    "error": hook_effect.get("error") or "claim_support_hook_unavailable",
                }
                return unavailable
            record = {
                "support_link_id": "sl-" + hashlib.sha256(os.urandom(32)).hexdigest()[:24],
                "evidence_id": evidence_id,
                "artifact_version": version,
                "page": page,
                "span_start": span_start,
                "span_end": span_end,
                "span_ref": hook_effect["span_ref"],
                "chunk_ref": hook_effect["chunk_ref"],
                "target_kind": target_kind,
                "target_id": target_id,
                "target_label": target.get("label") or "",
                "passage_id": target.get("passage_id") or "",
                "posture": posture,
                "origin": origin,
                "actor_principal_id": identity["actor_principal_id"],
                "canonical_owner_principal_id": case.tenant_id,
                "status": "current",
                "retired_reason": "",
                "explicit_acceptance": explicit,
                "accepted": explicit,
                "reviewed": explicit,
                "model_id": model_id,
                "invocation_id": invocation_id,
                "context_fingerprint": offered["context_fingerprint"],
                "source_version": offered["source_version"],
                "factual_graph_revision": offered["factual_graph_revision"],
                "fact_id": hook_effect["fact_id"],
                "hook_link_ids": hook_effect["hook_link_ids"],
                "support_record_id": hook_effect["support_record_id"],
                "request_fingerprint": self._support_fingerprint(body, offered),
                "establishes_legal_support": False,
                "verified_legal_support": False,
                "governing_law": False,
                "client_checkbox": False,
                "classifier_minted": False,
            }
            records.append(record)
            bucket[identity["idempotency_key"]] = record["support_link_id"]
            self._save(identity, case, key_id, data_key, document, scope)
            self._verify_scope(scope)
            view = self._public_support_link(record)
            view["idempotent_replay"] = False
            view["hook_created"] = hook_effect.get("created") is True
            return view

    def list_catalog(self, actor: str, body: Mapping[str, Any], *, verify_request: Callable[[], None] | None = None) -> dict[str, Any]:
        identity = self._identity(actor, body, content=False, idempotency=False)
        with self._lock:
            try:
                scope = self._open(identity, verify_request=verify_request)
                case, key_id, data_key = scope.case, scope.key_id, scope.data_key
                document = self._load(identity, case, key_id, data_key, scope)
            except EvidenceWorkspaceError as exc:
                if exc.code in {"key_unavailable", "ciphertext_unavailable", "evidence_unavailable"}:
                    return {
                        "task_id": TASK_ID,
                        "ingestion_status": "unavailable",
                        "items": [],
                        "legal": legal_qualities(),
                        "receipt_establishes_legal_quality": False,
                        "error": exc.code,
                    }
                raise
            items = []
            for item in document["items"].values():
                if item.get("actor_principal_id") != identity["actor_principal_id"]:
                    continue
                items.append(self._observe(identity, case, key_id, data_key, item, scope))
            self._verify_scope(scope)
            return {
                "task_id": TASK_ID,
                "case_id": case.case_id,
                "tenant_id": case.tenant_id,
                "actor_principal_id": identity["actor_principal_id"],
                "canonical_owner_principal_id": case.tenant_id,
                "ingestion_status": "" if not items else "catalog",
                "catalog_empty": not items,
                "items": items,
                "legal": legal_qualities(),
                "receipt_establishes_legal_quality": False,
            }

    def _span(self, body: Mapping[str, Any]) -> tuple[int, int, int]:
        page = body.get("page")
        start = body.get("span_start")
        end = body.get("span_end")
        if type(page) is not int or isinstance(page, bool) or page < 1 or page > 10000:
            raise EvidenceWorkspaceError("support_span_rejected")
        if type(start) is not int or isinstance(start, bool) or start < 0:
            raise EvidenceWorkspaceError("support_span_rejected")
        if type(end) is not int or isinstance(end, bool) or end <= start or end - start > 4000:
            raise EvidenceWorkspaceError("support_span_rejected")
        return page, start, end

    def _support_rows(self, document: Mapping[str, Any], evidence_id: str) -> list[dict[str, Any]]:
        rows = document.get("support_links")
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict) and row.get("evidence_id") == evidence_id]

    def _retire_support_links(self, document: dict[str, Any], evidence_id: str, item: Mapping[str, Any], offered: Mapping[str, Any]) -> bool:
        changed = False
        current_version = item.get("current_version")
        fingerprint = offered.get("context_fingerprint")
        for row in self._support_rows(document, evidence_id):
            if row.get("status") != "current":
                continue
            reason = ""
            if row.get("artifact_version") != current_version:
                reason = "artifact_version_changed"
            elif row.get("context_fingerprint") != fingerprint:
                reason = "source_or_context_changed"
            if reason == "":
                continue
            row["status"] = "retired"
            row["retired_reason"] = reason
            row["establishes_legal_support"] = False
            row["verified_legal_support"] = False
            changed = True
        return changed

    def _support_fingerprint(self, body: Mapping[str, Any], offered: Mapping[str, Any]) -> str:
        payload = {
            "posture": body.get("posture"),
            "origin": body.get("origin"),
            "target_kind": body.get("target_kind"),
            "target_id": body.get("target_id") or "",
            "page": body.get("page"),
            "span_start": body.get("span_start"),
            "span_end": body.get("span_end"),
            "accept": body.get("accept") is True,
            "model_id": body.get("model_id") or "",
            "invocation_id": body.get("invocation_id") or "",
            "context_fingerprint": offered.get("context_fingerprint") or "",
            "artifact_version": body.get("artifact_version"),
            "evidence_id": body.get("evidence_id"),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def _commit_support_hook(self, owner_id, actor, evidence_id, version, page, start, end, posture, explicit, target) -> dict[str, Any]:
        span_ref = f"page:{page}:{start}-{end}"
        chunk_ref = f"artifact:{evidence_id}:version:{version}:{span_ref}"
        proposition = str(target.get("label") or "")
        validation = "unvalidated"
        uncertainty = False
        contradiction = False
        if posture == "hypothesis":
            validation = "uncertain"
            uncertainty = True
        elif posture == "contradiction":
            validation = "contradicted"
            contradiction = True
        metadata = {
            "support_posture": posture,
            "explicit_acceptance": explicit,
            "verified_legal_support": False,
            "establishes_legal_support": False,
            "actor_principal_id": actor,
            "canonical_owner_principal_id": owner_id,
            "evidence_id": evidence_id,
            "artifact_version": version,
            "page": page,
            "span_start": start,
            "span_end": end,
            "target_kind": target.get("target_kind") or "",
            "target_id": target.get("target_id") or "",
            "passage_id": target.get("passage_id") or "",
            "source_version": target.get("source_version") or "",
            "client_checkbox": False,
            "classifier_minted": False,
        }
        hook = self.claim_support
        fact = hook.persist_fact_record(
            owner_id,
            "evidence_span_support",
            claim_element_id=str(target.get("target_id") or ""),
            claim_element_text=proposition,
            proposition_text=proposition,
            source_artifact_id=evidence_id,
            source_authority_id=str(target.get("passage_id") or ""),
            chunk_ref=chunk_ref,
            span_ref=span_ref,
            confidence=0.0,
            validation_state=validation,
            uncertainty_flag=uncertainty,
            contradiction_flag=contradiction,
            metadata=metadata,
        )
        if fact.get("available") is not True or not fact.get("fact_id"):
            return {"available": False, "recorded": False, "error": fact.get("error") or "claim_support_hook_unavailable"}
        fact_id = str(fact["fact_id"])
        span_target = f"{chunk_ref}:{span_ref}"
        chunk_link = hook.add_fact_link(
            fact_id, "to_chunk", span_target, target_type="evidence_span", metadata=metadata,
        )
        if chunk_link.get("available") is not True:
            return {"available": False, "recorded": False, "error": chunk_link.get("error") or "claim_support_hook_unavailable", "fact_id": fact_id}
        link_ids = [chunk_link.get("link_id")]
        if target.get("target_kind") == "sourced_requirement":
            authority_link = hook.add_fact_link(
                fact_id, "to_authority", str(target.get("target_id") or ""),
                target_type="sourced_requirement", metadata=metadata,
            )
            if authority_link.get("available") is not True:
                return {"available": False, "recorded": False, "error": authority_link.get("error") or "claim_support_hook_unavailable"}
            link_ids.append(authority_link.get("link_id"))
        else:
            element_link = hook.add_fact_link(
                fact_id, "to_element", str(target.get("target_id") or ""),
                target_type="factual_assertion", metadata=metadata,
            )
            if element_link.get("available") is not True:
                return {"available": False, "recorded": False, "error": element_link.get("error") or "claim_support_hook_unavailable"}
            link_ids.append(element_link.get("link_id"))
        try:
            stored = hook.upsert_support_link(
                user_id=owner_id,
                claim_type="evidence_span_support",
                claim_element_id=str(target.get("target_id") or ""),
                claim_element_text=proposition,
                support_kind=posture,
                support_ref=span_target,
                support_label=proposition,
                source_table="evidence_workspace",
                support_strength=0.0,
                metadata=metadata,
                complaint_id=owner_id,
            )
        except Exception as exc:
            return {"available": False, "recorded": False, "error": "claim_support_hook_unavailable", "detail": str(exc), "fact_id": fact_id}
        record_id = stored.get("record_id") if isinstance(stored, Mapping) else None
        if not isinstance(record_id, int):
            return {"available": False, "recorded": False, "error": "claim_support_hook_unavailable", "fact_id": fact_id}
        created = fact.get("created") is True or fact.get("reused") is True
        return {
            "available": True,
            "recorded": True,
            "created": fact.get("created") is True,
            "reused": fact.get("reused") is True,
            "fact_id": fact_id,
            "span_ref": span_ref,
            "chunk_ref": chunk_ref,
            "hook_link_ids": [item for item in link_ids if item],
            "support_record_id": record_id,
            "hook_effect": created,
        }

    def _unavailable_support(self, evidence_id, version, page, start, end, target_kind, target_id, reason) -> dict[str, Any]:
        return {
            "task_id": SUPPORT_LINK_TASK_ID,
            "support_link_id": "",
            "evidence_id": evidence_id,
            "artifact_version": version,
            "page": page,
            "span_start": start,
            "span_end": end,
            "span_ref": f"page:{page}:{start}-{end}",
            "target_kind": target_kind,
            "target_id": target_id,
            "posture": "unavailable",
            "requested_posture_recorded": False,
            "status": "unavailable",
            "reason": reason,
            "explicit_acceptance": False,
            "accepted": False,
            "recorded": False,
            "operation_succeeded": False,
            "establishes_legal_support": False,
            "verified_legal_support": False,
            "governing_law": False,
            "client_checkbox_mints_support": False,
            "classifier_mints_support": False,
            "idempotent_replay": False,
        }

    def _public_support_link(self, row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "task_id": SUPPORT_LINK_TASK_ID,
            "support_link_id": row.get("support_link_id") or "",
            "evidence_id": row.get("evidence_id") or "",
            "artifact_version": row.get("artifact_version"),
            "page": row.get("page"),
            "span_start": row.get("span_start"),
            "span_end": row.get("span_end"),
            "span_ref": row.get("span_ref") or "",
            "chunk_ref": row.get("chunk_ref") or "",
            "target_kind": row.get("target_kind") or "",
            "target_id": row.get("target_id") or "",
            "target_label": row.get("target_label") or "",
            "passage_id": row.get("passage_id") or "",
            "posture": row.get("posture") or "",
            "origin": row.get("origin") or "",
            "actor_principal_id": row.get("actor_principal_id") or "",
            "canonical_owner_principal_id": row.get("canonical_owner_principal_id") or "",
            "status": row.get("status") or "",
            "retired_reason": row.get("retired_reason") or "",
            "explicit_acceptance": row.get("explicit_acceptance") is True,
            "accepted": row.get("accepted") is True,
            "reviewed": row.get("reviewed") is True,
            "model_id": row.get("model_id") or "",
            "invocation_id": row.get("invocation_id") or "",
            "context_fingerprint": row.get("context_fingerprint") or "",
            "source_version": row.get("source_version") or "",
            "factual_graph_revision": row.get("factual_graph_revision") or "",
            "fact_id": row.get("fact_id") or "",
            "hook_link_ids": list(row.get("hook_link_ids") or []),
            "support_record_id": row.get("support_record_id"),
            "recorded": row.get("status") == "current",
            "operation_succeeded": row.get("status") == "current",
            "establishes_legal_support": False,
            "verified_legal_support": False,
            "governing_law": False,
            "client_checkbox_mints_support": False,
            "classifier_mints_support": False,
        }

    def _support_view(self, document, evidence_id, item, offered, *, retired: bool) -> dict[str, Any]:
        rows = [self._public_support_link(row) for row in self._support_rows(document, evidence_id)]
        current = [row for row in rows if row["status"] == "current"]
        stale = [row for row in rows if row["status"] == "retired"]
        return {
            "task_id": SUPPORT_LINK_TASK_ID,
            "evidence_id": evidence_id,
            "artifact_version": item.get("current_version"),
            "factual_assertions": offered["factual_assertions"],
            "sourced_requirements": offered["sourced_requirements"],
            "legal_context_status": offered["legal_context_status"],
            "factual_graph_revision": offered["factual_graph_revision"],
            "source_version": offered["source_version"],
            "context_fingerprint": offered["context_fingerprint"],
            "context_owner": offered["context_owner"],
            "admission_verified_by_evidence_workspace": False,
            "current": current,
            "retired": stale,
            "allegations": [row for row in current if row["posture"] == "allegation"],
            "hypotheses": [row for row in current if row["posture"] == "hypothesis"],
            "corroborations": [row for row in current if row["posture"] == "corroboration"],
            "contradictions": [row for row in current if row["posture"] == "contradiction"],
            "unavailable": [row for row in rows if row["posture"] == "unavailable"],
            "retirement_persisted": retired,
            "establishes_legal_support": False,
            "verified_legal_support": False,
            "governing_law": False,
            "client_checkbox_mints_support": False,
            "classifier_mints_support": False,
        }

    def _classifier_rows(self, document: Mapping[str, Any], evidence_id: str) -> list[dict[str, Any]]:
        rows = document.get("classifiers")
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict) and row.get("evidence_id") == evidence_id]

    def _retire_classifiers(self, document: dict[str, Any], evidence_id: str, item: Mapping[str, Any], offered: Mapping[str, Any]) -> bool:
        changed = False
        current_version = item.get("current_version")
        fingerprint = offered.get("context_fingerprint")
        source_version = offered.get("source_version") or ""
        graph_revision = offered.get("factual_graph_revision") or ""
        for row in self._classifier_rows(document, evidence_id):
            if row.get("status") != "current":
                continue
            reason = ""
            if row.get("origin") == "user_label":
                if row.get("artifact_version") != current_version:
                    reason = "artifact_version_changed"
            else:
                if row.get("context_fingerprint") != fingerprint:
                    reason = "source_or_context_changed"
                elif row.get("artifact_version") != current_version:
                    reason = "artifact_version_changed"
                elif (row.get("source_version") or "") != source_version or (row.get("factual_graph_revision") or "") != graph_revision:
                    reason = "source_version_changed"
            if reason == "":
                continue
            row["status"] = "retired"
            row["retired_reason"] = reason
            row["establishes_legal_support"] = False
            changed = True
        return changed

    def _choice_map(self, offered: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
        return {
            str(item.get("choice_id")): item
            for item in offered.get("choices") or []
            if isinstance(item, Mapping) and item.get("choice_id")
        }

    def _new_classifier(self, identity, evidence_id, version, origin, body, offered, records) -> dict[str, Any]:
        choices = self._choice_map(offered)
        label = ""
        target_kind = ""
        target_id = ""
        prior_id = ""
        model_id = ""
        invocation_id = ""
        if origin == "user_label":
            supplied_target = body.get("target_id")
            if supplied_target not in {None, ""}:
                target_id = _choice_id(supplied_target)
                choice = choices.get(target_id)
                if choice is None or target_id.casefold() in _FIXED_ASSUMPTION_IDS:
                    raise EvidenceWorkspaceError("classifier_rejected")
                target_kind = str(choice.get("target_kind") or "")
                label = _context_text(body.get("label")) or str(choice.get("label") or target_id)
                if label == "":
                    raise EvidenceWorkspaceError("classifier_rejected")
            else:
                label = _label(body.get("label"), "classifier_rejected")
                target_kind = "user_label"
        else:
            target_id = _choice_id(body.get("target_id"))
            choice = choices.get(target_id)
            if choice is None or target_id.casefold() in _FIXED_ASSUMPTION_IDS:
                raise EvidenceWorkspaceError("classifier_rejected")
            target_kind = str(choice.get("target_kind") or "")
            label = str(choice.get("label") or target_id)
            if origin == "ai_suggested":
                model_id = _label(body.get("model_id"), "classifier_rejected")
                invocation_id = _label(body.get("invocation_id"), "classifier_rejected")
                if target_kind == "user_label":
                    raise EvidenceWorkspaceError("classifier_rejected")
            else:
                prior_id = _choice_id(body.get("prior_classifier_id"))
                if body.get("accept") is not True:
                    raise EvidenceWorkspaceError("classifier_rejected")
                prior = next((row for row in records if row.get("classifier_id") == prior_id), None)
                if (prior is None or prior.get("evidence_id") != evidence_id or prior.get("status") != "current"
                        or prior.get("origin") != "ai_suggested" or prior.get("target_id") != target_id
                        or prior.get("context_fingerprint") != offered.get("context_fingerprint")):
                    raise EvidenceWorkspaceError("classifier_rejected")
        if target_kind == "legal_requirement" and offered.get("legal_context_status") != "admitted":
            raise EvidenceWorkspaceError("classifier_rejected")
        return {
            "classifier_id": "cl-" + hashlib.sha256(os.urandom(32)).hexdigest()[:24],
            "evidence_id": evidence_id,
            "artifact_version": version,
            "origin": origin,
            "target_kind": target_kind,
            "target_id": target_id,
            "label": label,
            "actor_principal_id": identity["actor_principal_id"],
            "status": "current",
            "retired_reason": "",
            "context_fingerprint": offered.get("context_fingerprint") or "",
            "source_version": offered.get("source_version") or "",
            "factual_graph_revision": offered.get("factual_graph_revision") or "",
            "legal_context_status": offered.get("legal_context_status") or "unknown",
            "model_id": model_id,
            "invocation_id": invocation_id,
            "prior_classifier_id": prior_id,
            "reviewed": origin == "reviewed_acceptance",
            "accepted": origin == "reviewed_acceptance",
            "request_fingerprint": self._request_fingerprint(body, offered),
            "establishes_legal_support": False,
            "establishes_claim_element": False,
            "governing_law": False,
        }

    def _request_fingerprint(self, body: Mapping[str, Any], offered: Mapping[str, Any]) -> str:
        payload = {
            "origin": body.get("origin"),
            "label": body.get("label") or "",
            "target_id": body.get("target_id") or "",
            "model_id": body.get("model_id") or "",
            "invocation_id": body.get("invocation_id") or "",
            "prior_classifier_id": body.get("prior_classifier_id") or "",
            "accept": body.get("accept") is True,
            "context_fingerprint": offered.get("context_fingerprint") or "",
            "artifact_version": body.get("artifact_version"),
            "evidence_id": body.get("evidence_id"),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def _same_classifier_request(self, prior: Mapping[str, Any], body: Mapping[str, Any], offered: Mapping[str, Any]) -> bool:
        return prior.get("request_fingerprint") == self._request_fingerprint(body, offered)

    def _public_classifier(self, row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "task_id": CLASSIFICATION_TASK_ID,
            "classifier_id": row.get("classifier_id") or "",
            "evidence_id": row.get("evidence_id") or "",
            "artifact_version": row.get("artifact_version"),
            "origin": row.get("origin") or "",
            "target_kind": row.get("target_kind") or "",
            "target_id": row.get("target_id") or "",
            "label": row.get("label") or "",
            "actor_principal_id": row.get("actor_principal_id") or "",
            "status": row.get("status") or "",
            "retired_reason": row.get("retired_reason") or "",
            "context_fingerprint": row.get("context_fingerprint") or "",
            "source_version": row.get("source_version") or "",
            "factual_graph_revision": row.get("factual_graph_revision") or "",
            "legal_context_status": row.get("legal_context_status") or "unknown",
            "model_id": row.get("model_id") or "",
            "invocation_id": row.get("invocation_id") or "",
            "prior_classifier_id": row.get("prior_classifier_id") or "",
            "reviewed": row.get("reviewed") is True,
            "accepted": row.get("accepted") is True,
            "suggestion_attribution": {
                "model_id": row.get("model_id") or "",
                "invocation_id": row.get("invocation_id") or "",
                "actor_principal_id": row.get("actor_principal_id") or "",
            },
            "establishes_legal_support": False,
            "establishes_claim_element": False,
            "governing_law": False,
            "hardcoded_elements_used": False,
        }

    def _classification_view(self, document, evidence_id, item, offered, *, retired: bool) -> dict[str, Any]:
        rows = [self._public_classifier(row) for row in self._classifier_rows(document, evidence_id)]
        current = [row for row in rows if row["status"] == "current"]
        stale = [row for row in rows if row["status"] == "retired"]
        return {
            "task_id": CLASSIFICATION_TASK_ID,
            "evidence_id": evidence_id,
            "artifact_version": item.get("current_version"),
            "legal_context_status": offered["legal_context_status"],
            "choices": offered["choices"],
            "factual_gap_ids": offered["factual_gap_ids"],
            "admitted_requirement_ids": offered["admitted_requirement_ids"],
            "fixed_assumptions_offered": False,
            "refused_fixed_assumptions": offered["refused_fixed_assumptions"],
            "hardcoded_elements_used": False,
            "context_fingerprint": offered["context_fingerprint"],
            "source_version": offered["source_version"],
            "factual_graph_revision": offered["factual_graph_revision"],
            "context_owner": offered["context_owner"],
            "admission_verified_by_evidence_workspace": False,
            "current": current,
            "retired": stale,
            "user_labels": [row for row in current if row["origin"] == "user_label"],
            "ai_suggestions": [row for row in current if row["origin"] == "ai_suggested"],
            "reviewed_acceptances": [row for row in current if row["origin"] == "reviewed_acceptance"],
            "retired_count": len(stale),
            "retirement_persisted": retired,
            "establishes_legal_support": False,
            "governing_law": False,
        }

    def _extract(self, identity, case, key_id, data_key, item, body, scope) -> None:
        encoded = body.get("extracted_content_base64")
        if not isinstance(encoded, str) or encoded == "":
            item["failure_code"] = "extraction_capability_unavailable"
            self._move(item, "unavailable")
            return
        try:
            content = self._content(encoded, "content_rejected")
        except EvidenceWorkspaceError:
            item["failure_code"] = "extraction_failed"
            self._move(item, "failed")
            return
        claimed = body.get("expected_integrity_sha256")
        actual = _digest(content)
        if isinstance(claimed, str) and claimed != actual:
            item["failure_code"] = "integrity_mismatch"
            self._move(item, "failed")
            return
        if item["ingestion_status"] not in {"received", "needs-review"}:
            raise EvidenceWorkspaceError("lifecycle_conflict")
        version_number = item["current_version"] + 1
        version = self._seal_version(
            identity, case, key_id, data_key, item["evidence_id"], version_number, "extraction", content, scope,
        )
        item["artifact_versions"].append(version)
        item["current_version"] = version_number
        item["integrity_sha256"] = actual
        item["failure_code"] = ""
        self._move(item, "extracted")
        item["receipt"] = self._receipt(version)

    def _move(self, item: dict[str, Any], status: str) -> None:
        if status not in INGESTION_STATUSES:
            raise EvidenceWorkspaceError("lifecycle_conflict")
        item["prior_ingestion_status"] = item["ingestion_status"]
        item["ingestion_status"] = status

    def _seal_version(self, identity, case, key_id, data_key, evidence_id, number, kind, content, scope) -> dict[str, Any]:
        access = _Access(trust="authenticated", principal_id=case.tenant_id, case_id=case.case_id)
        revision = f"{evidence_id}-v{number}"
        try:
            stored = store_private_artifact(
                content,
                access=access,
                tenant_id=case.tenant_id,
                case_id=case.case_id,
                artifact_kind=_KIND_ARTIFACT,
                revision=revision,
                principal_id=case.tenant_id,
                key=data_key,
                key_id=key_id,
                backend=self._backend,
                backend_name=self._backend_name,
                pin_content=False,
            )
        except PrivateStorageError as exc:
            raise EvidenceWorkspaceError("evidence_unavailable") from exc
        self._verify_scope(scope)
        return {
            "version": number,
            "kind": kind,
            "integrity_sha256": _digest(content),
            "byte_length": len(content),
            "ciphertext_cid": str(stored.get("cid") or ""),
            "key_id": key_id,
            "ciphertext_readback": stored.get("verified") is True,
        }

    def _observe(self, identity, case, key_id, data_key, item, scope) -> dict[str, Any]:
        current = item["artifact_versions"][-1]
        verified = False
        try:
            opened = retrieve_private_artifact(
                current["ciphertext_cid"],
                access=_Access(trust="authenticated", principal_id=case.tenant_id, case_id=case.case_id),
                tenant_id=case.tenant_id,
                case_id=case.case_id,
                artifact_kind=_KIND_ARTIFACT,
                revision=f"{item['evidence_id']}-v{current['version']}",
                principal_id=case.tenant_id,
                key=data_key,
                key_id=key_id,
                backend=self._backend,
                backend_name=self._backend_name,
            )
            payload = opened.get("data")
            verified = isinstance(payload, (bytes, bytearray)) and _digest(bytes(payload)) == current["integrity_sha256"]
        except (PrivateStorageError, EvidenceWorkspaceError):
            verified = False
        self._verify_scope(scope)
        expected_scope = _scope_binding(
            key=data_key, tenant_id=case.tenant_id, case_id=case.case_id,
            actor=item["actor_principal_id"], evidence_id=item["evidence_id"],
        )
        if expected_scope != item.get("scope_binding") or not verified:
            view = dict(item)
            view["prior_ingestion_status"] = item["ingestion_status"]
            view["ingestion_status"] = "failed" if item.get("scope_binding") != expected_scope else "unavailable"
            view["failure_code"] = "integrity_mismatch" if item.get("scope_binding") != expected_scope else "ciphertext_unavailable"
            view["legal"] = legal_qualities()
            return self._project(view, verified=False)
        return self._project(item, verified=True)

    def _project(self, item: Mapping[str, Any], *, verified: bool) -> dict[str, Any]:
        versions = []
        for version in item.get("artifact_versions") or []:
            versions.append({
                "version": version["version"],
                "kind": version["kind"],
                "integrity_sha256": version["integrity_sha256"],
                "byte_length": version["byte_length"],
                "ciphertext_readback": version.get("ciphertext_readback") is True,
            })
        legal = legal_qualities()
        return {
            "task_id": TASK_ID,
            "evidence_id": item["evidence_id"],
            "tenant_id": item["tenant_id"],
            "case_id": item["case_id"],
            "resource_id": item["resource_id"],
            "actor_principal_id": item["actor_principal_id"],
            "canonical_owner_principal_id": item["canonical_owner_principal_id"],
            "actor_is_canonical_owner": item["actor_is_canonical_owner"],
            "source_filename": item["source_filename"],
            "original_filename": item["original_filename"],
            "media_type": item["media_type"],
            "ingestion_status": item["ingestion_status"],
            "prior_ingestion_status": item.get("prior_ingestion_status") or "",
            "artifact_versions": versions,
            "current_version": item["current_version"],
            "integrity_sha256": item["integrity_sha256"],
            "integrity_verified": verified,
            "scope_binding": item["scope_binding"],
            "complaint_link_id": item.get("complaint_link_id") or "",
            "failure_code": item.get("failure_code") or "",
            "legal": legal,
            "authenticity": legal["authenticity"],
            "relevance": legal["relevance"],
            "admissibility": legal["admissibility"],
            "claim_support": legal["claim_support"],
            "receipt": {
                "ciphertext_readback": bool((item.get("receipt") or {}).get("ciphertext_readback")),
                "establishes_authenticity": False,
                "establishes_relevance": False,
                "establishes_admissibility": False,
                "establishes_claim_support": False,
            },
            "receipt_establishes_legal_quality": False,
            "operation_succeeded": item["ingestion_status"] not in {"failed", "unavailable"},
        }

    def _receipt(self, version: Mapping[str, Any]) -> dict[str, Any]:
        return {"ciphertext_readback": version.get("ciphertext_readback") is True}

    def _identity(self, actor: str, body: Mapping[str, Any], *, content: bool = True, idempotency: bool = True) -> dict[str, str]:
        if not isinstance(body, Mapping):
            raise EvidenceWorkspaceError("request_body")
        rejected = {"cid", "url", "uri", "role", "trusted_local", "key", "passphrase"}
        if any(name in body for name in rejected):
            raise EvidenceWorkspaceError("selector_rejected")
        identity = {
            "actor_principal_id": _label(actor, "actor"),
            "tenant_id": _label(body.get("tenant_id"), "tenant_id"),
            "case_id": _label(body.get("case_id"), "case_id"),
            "resource_id": _label(body.get("resource_id"), "resource_id"),
        }
        if idempotency:
            identity["idempotency_key"] = _label(body.get("idempotency_key"), "idempotency_key")
        if content and "content_base64" not in body:
            raise EvidenceWorkspaceError("content_rejected")
        return identity

    def _reject_legal_claims(self, body: Mapping[str, Any]) -> None:
        for name in LEGAL_QUALITIES:
            if body.get(name) not in {None, "not_established", False}:
                raise EvidenceWorkspaceError("legal_quality_rejected")

    def _content(self, encoded: Any, code: str) -> bytes:
        import base64
        if not isinstance(encoded, str) or encoded.strip() == "":
            raise EvidenceWorkspaceError(code)
        try:
            payload = base64.b64decode(encoded.encode("ascii"), validate=True)
        except (UnicodeEncodeError, ValueError) as exc:
            raise EvidenceWorkspaceError(code) from exc
        if not payload or len(payload) > _MAX_BYTES:
            raise EvidenceWorkspaceError(code)
        return payload

    def _open(self, identity: Mapping[str, str], *, verify_request: Callable[[], None] | None = None) -> _KeyScope:
        if verify_request is not None:
            verify_request()
        try:
            case = self._directory.select_case(actor_principal_id=identity["actor_principal_id"], case_id=identity["case_id"])
        except CaseDirectoryError as exc:
            raise EvidenceWorkspaceError("not_owner") from exc
        if case.tenant_id != identity["tenant_id"] or case.resource_id != identity["resource_id"]:
            raise EvidenceWorkspaceError("tenant_mismatch")
        session = self._sessions.get(identity["actor_principal_id"])
        if not isinstance(session, UserOwnedKeySession) or not session.unlocked:
            raise EvidenceWorkspaceError("key_unavailable")
        epoch = session.session_epoch
        try:
            key_id = session.ensure_data_key(case.tenant_id, case.case_id)
            data_key = session.lookup_data_key(case.tenant_id, case.case_id, key_id)
        except Exception as exc:
            raise EvidenceWorkspaceError("key_unavailable") from exc
        if not isinstance(data_key, bytes) or len(data_key) != 32:
            raise EvidenceWorkspaceError("key_unavailable")
        scope = _KeyScope(dict(identity), case, session, epoch, key_id, data_key, verify_request)
        self._verify_scope(scope)
        return scope

    def key_scope_verifier(self, actor: str, body: Mapping[str, Any]) -> Callable[[], None]:
        """Capture a live scope for the HTTP boundary's final response check.

        The closure carries no new authority: every call reopens the actual
        case directory and resolves the current active key from its owner.
        No lock remains held while a backend or an HTTP worker runs.
        """
        identity = self._identity(actor, body, content=False, idempotency=False)
        scope = self._open(identity)
        return lambda: self._verify_scope(scope)

    def _verify_scope(self, scope: _KeyScope) -> None:
        # A queued HTTP invocation keeps its original boundary lifetime even
        # if the worker starts after a later unlock. This is an additional
        # constraint; the actual directory and key owner are always rechecked.
        if scope.verify_request is not None:
            scope.verify_request()
        identity, session = scope.identity, scope.session
        if (self._sessions.get(identity["actor_principal_id"]) is not session
                or session.session_epoch != scope.epoch or not session.unlocked):
            raise EvidenceWorkspaceError("key_unavailable")
        try:
            case = self._directory.select_case(
                actor_principal_id=identity["actor_principal_id"], case_id=identity["case_id"])
        except CaseDirectoryError as exc:
            raise EvidenceWorkspaceError("not_owner") from exc
        if (case != scope.case or case.tenant_id != identity["tenant_id"]
                or case.resource_id != identity["resource_id"]):
            raise EvidenceWorkspaceError("tenant_mismatch")
        try:
            key_id, data_key = session.provider().resolve(PrivateArtifactBinding(
                tenant_id=case.tenant_id, case_id=case.case_id,
                artifact_kind=_KIND_CATALOG, revision="scope-check",
                principal_id=case.tenant_id))
        except PrivateStorageError as exc:
            raise EvidenceWorkspaceError("key_unavailable") from exc
        if (session.session_epoch != scope.epoch or not session.unlocked
                or key_id != scope.key_id or not isinstance(data_key, bytes)
                or not hmac.compare_digest(data_key, scope.data_key)):
            raise EvidenceWorkspaceError("key_unavailable")
        if scope.verify_request is not None:
            scope.verify_request()

    def _pointer(self, identity: Mapping[str, str]) -> Path:
        digest = hashlib.sha256(
            "\n".join((identity["tenant_id"], identity["case_id"], identity["actor_principal_id"])).encode()
        ).hexdigest()
        slot = self._root / digest
        slot.mkdir(mode=0o700, exist_ok=True)
        return slot / "pointer.json"

    def _load(self, identity, case, key_id, data_key, scope) -> dict[str, Any]:
        path = self._pointer(identity)
        if not path.exists():
            self._verify_scope(scope)
            return {"revision": 0, "items": {}, "idempotency": {}}
        pointer = json.loads(path.read_text(encoding="utf-8"))
        cid = pointer.get("cid")
        if not isinstance(cid, str) or cid == "":
            raise EvidenceWorkspaceError("ciphertext_unavailable")
        try:
            opened = retrieve_private_artifact(
                cid,
                access=_Access(trust="authenticated", principal_id=case.tenant_id, case_id=case.case_id),
                tenant_id=case.tenant_id,
                case_id=case.case_id,
                artifact_kind=_KIND_CATALOG,
                revision=f"catalog-{pointer.get('revision')}",
                principal_id=case.tenant_id,
                key=data_key,
                key_id=key_id,
                backend=self._backend,
                backend_name=self._backend_name,
            )
        except PrivateStorageError as exc:
            raise EvidenceWorkspaceError("ciphertext_unavailable") from exc
        self._verify_scope(scope)
        data = opened.get("data")
        if not isinstance(data, (bytes, bytearray)):
            raise EvidenceWorkspaceError("ciphertext_unavailable")
        document = json.loads(bytes(data).decode("utf-8"))
        document.setdefault("items", {})
        document.setdefault("idempotency", {})
        return document

    def _save(self, identity, case, key_id, data_key, document: dict[str, Any], scope) -> None:
        self._verify_scope(scope)
        document["revision"] = int(document.get("revision") or 0) + 1
        payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        stored = store_private_artifact(
            payload,
            access=_Access(trust="authenticated", principal_id=case.tenant_id, case_id=case.case_id),
            tenant_id=case.tenant_id,
            case_id=case.case_id,
            artifact_kind=_KIND_CATALOG,
            revision=f"catalog-{document['revision']}",
            principal_id=case.tenant_id,
            key=data_key,
            key_id=key_id,
            backend=self._backend,
            backend_name=self._backend_name,
            pin_content=False,
        )
        self._verify_scope(scope)
        path = self._pointer(identity)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps({"cid": stored["cid"], "revision": document["revision"]}), encoding="utf-8")
        os.chmod(temporary, 0o600)
        self._verify_scope(scope)
        os.replace(temporary, path)
