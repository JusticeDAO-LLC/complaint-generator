"""Durable private evidence, annotations, classification revisions, and links.

Records are sealed with the caller's case key and Kit authenticated encryption.
A content hash is not ciphertext. A queued or local write is not remote
durability. Missing keys and failed readback stay failures.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any, Mapping

from integrations.private_collaboration import commit_linkage_record
from integrations.private_storage import (
    BoundPrivateRecordError,
    PrivateArtifactBinding,
    commit_private_bound_record,
    open_private_bound_record,
    recover_private_bound_records,
    stage_interrupted_bound_record,
)


ANNOTATION_TASK_ID = "CIMP-UX-17"
ANNOTATION_KINDS = ("comment", "label", "page_span")
_MAX_NOTE = 4000
_MAX_LABEL = 80


class AnnotationRevisionConflict(BoundPrivateRecordError):
    """A concurrent note or link lost the compare-and-swap.

    The chain revision is unchanged. The rejected attempt is sealed in the
    encrypted history and returned on ``conflict`` for the caller to show.
    """

    def __init__(self, conflict: dict[str, Any]) -> None:
        super().__init__("revision_conflict")
        self.conflict = dict(conflict)


class EvidenceAnnotationStore:
    """Case-scoped store for the four private evidence record kinds.

    Versioned comments, labels, and page spans are sealed to the canonical
    case owner. The acting principal is recorded inside the ciphertext. A
    display role is not an owner, a note is not a document, and an omitted
    claim element is not causation.
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._lock = threading.Lock()

    def put_evidence(
        self,
        *,
        record_id: str,
        plaintext: bytes,
        binding: PrivateArtifactBinding,
        key: bytes,
        key_id: str,
        remote_backend: Any | None = None,
    ) -> dict[str, Any]:
        self._require_kind(binding, "evidence")
        return commit_private_bound_record(
            self._root,
            record_id=record_id,
            kind="evidence",
            plaintext=plaintext,
            binding=binding,
            key=key,
            key_id=key_id,
            remote_backend=remote_backend,
        )

    def put_annotation(
        self,
        *,
        record_id: str,
        evidence_id: str,
        note: str,
        binding: PrivateArtifactBinding,
        key: bytes,
        key_id: str,
        remote_backend: Any | None = None,
    ) -> dict[str, Any]:
        self._require_kind(binding, "annotation")
        self._label(evidence_id, "evidence_id_rejected")
        if not isinstance(note, str) or not note.strip() or len(note) > 4000:
            raise BoundPrivateRecordError("annotation_rejected")
        body = json.dumps(
            {"kind": "annotation", "evidence_id": evidence_id, "note": note},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return commit_private_bound_record(
            self._root,
            record_id=record_id,
            kind="annotation",
            plaintext=body,
            binding=binding,
            key=key,
            key_id=key_id,
            remote_backend=remote_backend,
        )

    def revise_classification(
        self,
        *,
        record_id: str,
        label: str,
        previous_revision: str,
        binding: PrivateArtifactBinding,
        key: bytes,
        key_id: str,
        remote_backend: Any | None = None,
    ) -> dict[str, Any]:
        self._require_kind(binding, "classification_revision")
        self._label(label, "classification_rejected")
        self._label(previous_revision, "classification_rejected")
        if previous_revision == binding.revision:
            raise BoundPrivateRecordError("classification_revision_unchanged")
        body = json.dumps(
            {
                "kind": "classification_revision",
                "label": label,
                "previous_revision": previous_revision,
                "revision": binding.revision,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return commit_private_bound_record(
            self._root,
            record_id=record_id,
            kind="classification_revision",
            plaintext=body,
            binding=binding,
            key=key,
            key_id=key_id,
            remote_backend=remote_backend,
        )

    def publish_annotation(self, **kwargs: Any) -> dict[str, Any]:
        """Publish one note, or return conflict or access denial.

        ``live_key_id`` is the key the caller just resolved. A staged
        ``expected_key_id`` that no longer matches, or a locked session,
        does not write. Concurrent revision loss returns the sealed
        conflict payload instead of replacing the chain.
        """

        expected_key_id = kwargs.pop("expected_key_id", None)
        live_key_id = kwargs.pop("live_key_id", None)
        access_locked = kwargs.pop("access_locked", False)
        if access_locked is True or not isinstance(live_key_id, str) or live_key_id == "":
            return self._access_denial("operation_revoked", kwargs)
        if not isinstance(expected_key_id, str) or expected_key_id != live_key_id:
            return self._access_denial("key_rotated", kwargs)
        try:
            published = self.commit_attributed_annotation(**kwargs)
        except AnnotationRevisionConflict as exc:
            return exc.conflict
        published["published"] = True
        published["preview_allowed"] = True
        published["history_retained"] = True
        return published

    def publish_link(
        self,
        *,
        evidence_id: str,
        artifact_version: int,
        annotation_id: str,
        actor_principal_id: str,
        canonical_owner_principal_id: str,
        tenant_id: str,
        case_id: str,
        idempotency_key: str,
        expected_annotation_revision: str,
        expected_key_id: str,
        live_key_id: str,
        key: bytes,
        key_id: str,
        access_locked: bool = False,
        remote_backend: Any | None = None,
    ) -> dict[str, Any]:
        """Link a note to an artifact version under the same conflict rules."""

        denial_args = {
            "evidence_id": evidence_id,
            "artifact_version": artifact_version,
            "tenant_id": tenant_id,
            "case_id": case_id,
            "canonical_owner_principal_id": canonical_owner_principal_id,
        }
        if access_locked is True or not isinstance(live_key_id, str) or live_key_id == "":
            return self._access_denial("operation_revoked", denial_args)
        if not isinstance(expected_key_id, str) or expected_key_id != live_key_id:
            return self._access_denial("key_rotated", denial_args)
        self._label(annotation_id, "annotation_rejected")
        self._token(idempotency_key, "annotation_rejected")
        if not isinstance(expected_annotation_revision, str):
            raise BoundPrivateRecordError("revision_conflict")
        fingerprint = _canonical({
            "operation": "link",
            "evidence_id": evidence_id,
            "artifact_version": artifact_version,
            "annotation_id": annotation_id,
            "actor_principal_id": actor_principal_id,
        })
        with self._lock:
            head = self._load_head(
                tenant_id=tenant_id,
                case_id=case_id,
                canonical_owner_principal_id=canonical_owner_principal_id,
                key=key,
            )
            chain_id = _chain_key(evidence_id, artifact_version)
            chain = head["chains"].get(chain_id)
            if chain is None:
                chain = {"revision": "", "items": {}, "idempotency": {}}
                head["chains"][chain_id] = chain
            chain.setdefault("items", {})
            chain.setdefault("idempotency", {})
            prior = chain["idempotency"].get(idempotency_key)
            if prior is not None and prior.get("operation") == "link":
                if prior.get("fingerprint") != fingerprint:
                    raise BoundPrivateRecordError("replay_mismatch")
                return {
                    "published": True,
                    "idempotent_replay": True,
                    "annotation_id": annotation_id,
                    "evidence_id": evidence_id,
                    "artifact_version": artifact_version,
                    "annotation_revision": chain["revision"],
                    "history_retained": True,
                    "preview_allowed": True,
                    "link_record_id": prior.get("record_id") or "",
                }
            if expected_annotation_revision != chain["revision"]:
                conflict = self._seal_conflict(
                    head,
                    chain,
                    {
                        "kind": "link",
                        "evidence_id": evidence_id,
                        "artifact_version": artifact_version,
                        "annotation_id": annotation_id,
                        "actor_principal_id": actor_principal_id,
                        "note": "",
                    },
                    expected_annotation_revision=expected_annotation_revision,
                    idempotency_key=idempotency_key,
                    key=key,
                    key_id=key_id,
                    remote_backend=remote_backend,
                )
                return conflict
            record_id = "lnk-" + hashlib.sha256(
                (fingerprint + "\n" + chain["revision"] + "\n" + idempotency_key).encode("utf-8")
            ).hexdigest()[:32]
            binding = PrivateArtifactBinding(
                tenant_id=tenant_id,
                case_id=case_id,
                artifact_kind="linkage",
                revision=record_id,
                principal_id=actor_principal_id,
            )
            linked = self.link(
                record_id=record_id,
                actor_principal_id=actor_principal_id,
                evidence_id=evidence_id,
                annotation_id=annotation_id,
                binding=binding,
                key=key,
                key_id=key_id,
                remote_backend=remote_backend,
            )
            if linked.get("local_durable") is not True:
                raise BoundPrivateRecordError("annotation_unavailable")
            revision = hashlib.sha256((chain["revision"] + "\n" + fingerprint).encode("utf-8")).hexdigest()
            chain["idempotency"][idempotency_key] = {
                "operation": "link",
                "fingerprint": fingerprint,
                "record_id": record_id,
                "annotation_id": annotation_id,
            }
            chain["revision"] = revision
            self._commit_head(head, key=key, key_id=key_id, remote_backend=remote_backend)
            return {
                "published": True,
                "idempotent_replay": False,
                "annotation_id": annotation_id,
                "evidence_id": evidence_id,
                "artifact_version": artifact_version,
                "annotation_revision": revision,
                "link_record_id": record_id,
                "history_retained": True,
                "preview_allowed": True,
                "local_durable": True,
                "support_duplicated": False,
            }

    def link(
        self,
        *,
        record_id: str,
        actor_principal_id: str,
        evidence_id: str,
        annotation_id: str,
        binding: PrivateArtifactBinding,
        key: bytes,
        key_id: str,
        remote_backend: Any | None = None,
    ) -> dict[str, Any]:
        return commit_linkage_record(
            self._root,
            actor_principal_id=actor_principal_id,
            evidence_id=evidence_id,
            annotation_id=annotation_id,
            binding=binding,
            key=key,
            key_id=key_id,
            record_id=record_id,
            remote_backend=remote_backend,
        )

    def commit_attributed_annotation(
        self,
        *,
        evidence_id: str,
        artifact_version: int,
        kind: str,
        actor_principal_id: str,
        canonical_owner_principal_id: str,
        tenant_id: str,
        case_id: str,
        idempotency_key: str,
        expected_annotation_revision: str,
        key: bytes,
        key_id: str,
        note: str = "",
        label: str = "",
        page: int | None = None,
        span_start: int | None = None,
        span_end: int | None = None,
        claim_element: str | None = None,
        display_role: str | None = None,
        remote_backend: Any | None = None,
    ) -> dict[str, Any]:
        """Seal one note on an exact artifact version.

        ``display_role`` is accepted and ignored. It never selects the actor
        or the canonical owner. ``claim_element`` is stored only when the
        caller supplied it; omission stays empty rather than causation.
        """

        del display_role
        self._token(idempotency_key, "annotation_rejected")
        if not isinstance(expected_annotation_revision, str) or len(expected_annotation_revision) > 64:
            raise BoundPrivateRecordError("revision_conflict")
        semantic = self._semantic(
            evidence_id=evidence_id,
            artifact_version=artifact_version,
            kind=kind,
            actor_principal_id=actor_principal_id,
            canonical_owner_principal_id=canonical_owner_principal_id,
            tenant_id=tenant_id,
            case_id=case_id,
            note=note,
            label=label,
            page=page,
            span_start=span_start,
            span_end=span_end,
            claim_element=claim_element,
        )
        fingerprint = _canonical(semantic)
        with self._lock:
            head = self._load_head(
                tenant_id=tenant_id,
                case_id=case_id,
                canonical_owner_principal_id=canonical_owner_principal_id,
                key=key,
            )
            chain_id = _chain_key(evidence_id, artifact_version)
            chain = head["chains"].get(chain_id)
            if chain is None:
                chain = {"revision": "", "items": {}, "idempotency": {}}
                head["chains"][chain_id] = chain
            chain.setdefault("items", {})
            chain.setdefault("idempotency", {})
            prior = chain["idempotency"].get(idempotency_key)
            if prior is not None:
                if prior.get("fingerprint") != fingerprint or prior.get("operation") != "create":
                    raise BoundPrivateRecordError("replay_mismatch")
                view = dict(chain["items"][prior["annotation_id"]])
                view["idempotent_replay"] = True
                view["annotation_revision"] = chain["revision"]
                view["synthesized_evidence"] = False
                return view
            if expected_annotation_revision != chain["revision"]:
                conflict = self._seal_conflict(
                    head,
                    chain,
                    semantic,
                    expected_annotation_revision=expected_annotation_revision,
                    idempotency_key=idempotency_key,
                    key=key,
                    key_id=key_id,
                    remote_backend=remote_backend,
                )
                raise AnnotationRevisionConflict(conflict)
            record_id = "ann-" + hashlib.sha256(
                (fingerprint + "\n" + chain["revision"] + "\n" + idempotency_key).encode("utf-8")
            ).hexdigest()[:32]
            if record_id in chain["items"]:
                raise BoundPrivateRecordError("revision_conflict")
            body = dict(semantic)
            body.update({
                "schema": "evidence-annotation@1",
                "annotation_id": record_id,
                "record_type": "note",
                "adopted": False,
                "adopted_as_evidence": False,
                "synthesized_evidence": False,
                "display_role_authoritative": False,
                "claim_element_defaulted": False,
                "establishes_claim_element": False,
                "establishes_causation": False,
            })
            plaintext = _canonical(body).encode("utf-8")
            binding = self._annotation_binding(
                tenant_id=tenant_id,
                case_id=case_id,
                canonical_owner_principal_id=canonical_owner_principal_id,
                revision=record_id,
            )
            receipt = commit_private_bound_record(
                self._root,
                record_id=record_id,
                kind="annotation",
                plaintext=plaintext,
                binding=binding,
                key=key,
                key_id=key_id,
                remote_backend=remote_backend,
            )
            if receipt.get("local_durable") is not True:
                raise BoundPrivateRecordError("annotation_unavailable")
            opened = json.loads(self.read(record_id=record_id, binding=binding, key=key))
            if opened.get("annotation_id") != record_id:
                raise BoundPrivateRecordError("readback_mismatch")
            revision = hashlib.sha256((chain["revision"] + "\n" + fingerprint).encode("utf-8")).hexdigest()
            stored = self._public_view(body, revision=revision, replay=False)
            chain["items"][record_id] = stored
            chain["idempotency"][idempotency_key] = {
                "operation": "create",
                "fingerprint": fingerprint,
                "annotation_id": record_id,
            }
            chain["revision"] = revision
            head["chains"][_chain_key(evidence_id, artifact_version)] = chain
            self._commit_head(head, key=key, key_id=key_id, remote_backend=remote_backend)
            return stored

    def adopt_annotation(
        self,
        *,
        evidence_id: str,
        artifact_version: int,
        annotation_id: str,
        actor_principal_id: str,
        canonical_owner_principal_id: str,
        tenant_id: str,
        case_id: str,
        idempotency_key: str,
        expected_annotation_revision: str,
        key: bytes,
        key_id: str,
        adopt: bool = False,
        display_role: str | None = None,
        remote_backend: Any | None = None,
    ) -> dict[str, Any]:
        """Mark an existing note adopted. Adoption does not mint evidence."""

        del display_role
        if adopt is not True:
            raise BoundPrivateRecordError("adoption_requires_explicit_action")
        self._label(annotation_id, "annotation_rejected")
        self._token(actor_principal_id, "annotation_rejected")
        self._token(idempotency_key, "annotation_rejected")
        self._token(canonical_owner_principal_id, "annotation_rejected")
        self._token(tenant_id, "annotation_rejected")
        self._token(case_id, "annotation_rejected")
        self._label(evidence_id, "evidence_id_rejected")
        if type(artifact_version) is not int or isinstance(artifact_version, bool) or artifact_version < 1:
            raise BoundPrivateRecordError("annotation_rejected")
        if not isinstance(expected_annotation_revision, str):
            raise BoundPrivateRecordError("revision_conflict")
        fingerprint = _canonical({
            "operation": "adopt",
            "annotation_id": annotation_id,
            "evidence_id": evidence_id,
            "artifact_version": artifact_version,
            "actor_principal_id": actor_principal_id,
        })
        with self._lock:
            head = self._load_head(
                tenant_id=tenant_id,
                case_id=case_id,
                canonical_owner_principal_id=canonical_owner_principal_id,
                key=key,
            )
            chain = head["chains"].get(_chain_key(evidence_id, artifact_version))
            if chain is None or annotation_id not in chain.get("items", {}):
                raise BoundPrivateRecordError("missing_annotation")
            prior = chain["idempotency"].get(idempotency_key)
            if prior is not None:
                if prior.get("fingerprint") != fingerprint or prior.get("operation") != "adopt":
                    raise BoundPrivateRecordError("replay_mismatch")
                view = dict(chain["items"][annotation_id])
                view["idempotent_replay"] = True
                view["annotation_revision"] = chain["revision"]
                view["synthesized_evidence"] = False
                return view
            if expected_annotation_revision != chain["revision"]:
                raise BoundPrivateRecordError("revision_conflict")
            current = dict(chain["items"][annotation_id])
            if current.get("adopted") is True:
                current["idempotent_replay"] = False
                current["annotation_revision"] = chain["revision"]
                current["synthesized_evidence"] = False
                current["adopted_as_evidence"] = False
                return current
            record_id = "adp-" + hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:32]
            adoption = {
                "schema": "evidence-annotation-adoption@1",
                "annotation_id": annotation_id,
                "evidence_id": evidence_id,
                "artifact_version": artifact_version,
                "actor_principal_id": actor_principal_id,
                "canonical_owner_principal_id": canonical_owner_principal_id,
                "record_type": "note",
                "adopted": True,
                "adopted_as_evidence": False,
                "synthesized_evidence": False,
                "display_role_authoritative": False,
                "claim_element": current.get("claim_element") or "",
                "establishes_causation": False,
            }
            binding = self._annotation_binding(
                tenant_id=tenant_id,
                case_id=case_id,
                canonical_owner_principal_id=canonical_owner_principal_id,
                revision=record_id,
            )
            receipt = commit_private_bound_record(
                self._root,
                record_id=record_id,
                kind="annotation",
                plaintext=_canonical(adoption).encode("utf-8"),
                binding=binding,
                key=key,
                key_id=key_id,
                remote_backend=remote_backend,
            )
            if receipt.get("local_durable") is not True:
                raise BoundPrivateRecordError("annotation_unavailable")
            revision = hashlib.sha256((chain["revision"] + "\n" + fingerprint).encode("utf-8")).hexdigest()
            current["adopted"] = True
            current["adopted_by_actor_principal_id"] = actor_principal_id
            current["record_type"] = "note"
            current["adopted_as_evidence"] = False
            current["synthesized_evidence"] = False
            current["establishes_causation"] = False
            current["establishes_claim_element"] = False
            current["annotation_revision"] = revision
            current["idempotent_replay"] = False
            current["display_role_authoritative"] = False
            chain["items"][annotation_id] = current
            chain["idempotency"][idempotency_key] = {
                "operation": "adopt",
                "fingerprint": fingerprint,
                "annotation_id": annotation_id,
            }
            chain["revision"] = revision
            head["chains"][_chain_key(evidence_id, artifact_version)] = chain
            self._commit_head(head, key=key, key_id=key_id, remote_backend=remote_backend)
            return current

    def list_attributed_annotations(
        self,
        *,
        evidence_id: str,
        artifact_version: int,
        canonical_owner_principal_id: str,
        tenant_id: str,
        case_id: str,
        key: bytes,
    ) -> dict[str, Any]:
        self._label(evidence_id, "evidence_id_rejected")
        if type(artifact_version) is not int or isinstance(artifact_version, bool) or artifact_version < 1:
            raise BoundPrivateRecordError("annotation_rejected")
        with self._lock:
            head = self._load_head(
                tenant_id=tenant_id,
                case_id=case_id,
                canonical_owner_principal_id=canonical_owner_principal_id,
                key=key,
            )
        chain = head["chains"].get(_chain_key(evidence_id, artifact_version)) or {
            "revision": "",
            "items": {},
        }
        items = [dict(item) for item in chain["items"].values()]
        items.sort(key=lambda item: str(item.get("annotation_id") or ""))
        history = [dict(entry) for entry in chain.get("conflict_history") or [] if isinstance(entry, dict)]
        return {
            "task_id": ANNOTATION_TASK_ID,
            "evidence_id": evidence_id,
            "artifact_version": artifact_version,
            "annotation_revision": chain.get("revision") or "",
            "items": items,
            "conflict_history": history,
            "history_retained": True,
            "synthesized_evidence": False,
            "display_role_authoritative": False,
        }

    def read(self, *, record_id: str, binding: PrivateArtifactBinding, key: bytes) -> bytes:
        return open_private_bound_record(self._root, record_id=record_id, binding=binding, key=key)

    def stage_evidence(
        self,
        *,
        record_id: str,
        plaintext: bytes,
        binding: PrivateArtifactBinding,
        key: bytes,
        key_id: str,
    ) -> dict[str, Any]:
        self._require_kind(binding, "evidence")
        return stage_interrupted_bound_record(
            self._root,
            record_id=record_id,
            kind="evidence",
            plaintext=plaintext,
            binding=binding,
            key=key,
            key_id=key_id,
        )

    def recover(
        self,
        *,
        key: bytes,
        bindings: Mapping[str, PrivateArtifactBinding],
        max_attempts: int = 3,
    ) -> dict[str, Any]:
        return recover_private_bound_records(
            self._root,
            key=key,
            bindings=bindings,
            max_attempts=max_attempts,
        )

    def _access_denial(self, code: str, raw: Mapping[str, Any]) -> dict[str, Any]:
        evidence_id = raw.get("evidence_id") if isinstance(raw.get("evidence_id"), str) else ""
        version = raw.get("artifact_version") if type(raw.get("artifact_version")) is int else 0
        preserved: list[str] = []
        revision = ""
        key = raw.get("key")
        if isinstance(key, bytes) and evidence_id and version >= 1:
            try:
                listed = self.list_attributed_annotations(
                    evidence_id=evidence_id,
                    artifact_version=version,
                    canonical_owner_principal_id=str(raw.get("canonical_owner_principal_id") or ""),
                    tenant_id=str(raw.get("tenant_id") or ""),
                    case_id=str(raw.get("case_id") or ""),
                    key=key,
                )
                preserved = [str(item.get("annotation_id") or "") for item in listed["items"]]
                revision = str(listed.get("annotation_revision") or "")
            except BoundPrivateRecordError:
                preserved = []
        return {
            "error": code,
            "published": False,
            "preview_allowed": False,
            "operation_succeeded": False,
            "history_retained": True,
            "overwrote_history": False,
            "evidence_id": evidence_id,
            "artifact_version": version,
            "annotation_revision": revision,
            "preserved_annotation_ids": preserved,
            "conflict": False,
        }

    def _seal_conflict(
        self,
        head: dict[str, Any],
        chain: dict[str, Any],
        semantic: Mapping[str, Any],
        *,
        expected_annotation_revision: str,
        idempotency_key: str,
        key: bytes,
        key_id: str,
        remote_backend: Any | None,
    ) -> dict[str, Any]:
        """Seal the rejected attempt and leave the chain revision in place."""

        chain.setdefault("items", {})
        chain.setdefault("conflict_history", [])
        preserved = sorted(str(item_id) for item_id in chain["items"])
        body = {
            "schema": "evidence-annotation-conflict@1",
            "expected_annotation_revision": expected_annotation_revision,
            "current_annotation_revision": chain.get("revision") or "",
            "idempotency_key": idempotency_key,
            "rejected": dict(semantic),
            "preserved_annotation_ids": preserved,
        }
        plaintext = _canonical(body).encode("utf-8")
        prefix = (str(chain.get("revision") or "") + "\n" + str(len(chain["conflict_history"])) + "\n").encode("utf-8")
        record_id = "cnf-" + hashlib.sha256(prefix + plaintext).hexdigest()[:32]
        binding = self._annotation_binding(
            tenant_id=head["tenant_id"],
            case_id=head["case_id"],
            canonical_owner_principal_id=head["canonical_owner_principal_id"],
            revision=record_id,
        )
        receipt = commit_private_bound_record(
            self._root,
            record_id=record_id,
            kind="annotation",
            plaintext=plaintext,
            binding=binding,
            key=key,
            key_id=key_id,
            remote_backend=remote_backend,
        )
        if receipt.get("local_durable") is not True:
            raise BoundPrivateRecordError("annotation_unavailable")
        opened = json.loads(self.read(record_id=record_id, binding=binding, key=key))
        if opened.get("schema") != "evidence-annotation-conflict@1":
            raise BoundPrivateRecordError("readback_mismatch")
        entry = {
            "record_id": record_id,
            "expected_annotation_revision": expected_annotation_revision,
            "current_annotation_revision": chain.get("revision") or "",
            "preserved_annotation_ids": preserved,
            "encrypted": True,
        }
        chain["conflict_history"].append(entry)
        self._commit_head(head, key=key, key_id=key_id, remote_backend=remote_backend)
        return {
            "error": "revision_conflict",
            "conflict": True,
            "published": False,
            "preview_allowed": True,
            "operation_succeeded": False,
            "history_retained": True,
            "overwrote_history": False,
            "encrypted_history_record_id": record_id,
            "expected_annotation_revision": expected_annotation_revision,
            "current_annotation_revision": chain.get("revision") or "",
            "annotation_revision": chain.get("revision") or "",
            "evidence_id": semantic.get("evidence_id") or "",
            "artifact_version": semantic.get("artifact_version"),
            "preserved_annotation_ids": preserved,
            "support_duplicated": False,
        }

    def _semantic(
        self,
        *,
        evidence_id: str,
        artifact_version: int,
        kind: str,
        actor_principal_id: str,
        canonical_owner_principal_id: str,
        tenant_id: str,
        case_id: str,
        note: str,
        label: str,
        page: int | None,
        span_start: int | None,
        span_end: int | None,
        claim_element: str | None,
    ) -> dict[str, Any]:
        self._label(evidence_id, "evidence_id_rejected")
        self._token(actor_principal_id, "annotation_rejected")
        self._token(canonical_owner_principal_id, "annotation_rejected")
        self._token(tenant_id, "annotation_rejected")
        self._token(case_id, "annotation_rejected")
        if kind not in ANNOTATION_KINDS:
            raise BoundPrivateRecordError("annotation_rejected")
        if type(artifact_version) is not int or isinstance(artifact_version, bool) or not 1 <= artifact_version <= 100000:
            raise BoundPrivateRecordError("annotation_rejected")
        if not isinstance(note, str) or len(note) > _MAX_NOTE:
            raise BoundPrivateRecordError("annotation_rejected")
        if not isinstance(label, str) or len(label) > _MAX_LABEL:
            raise BoundPrivateRecordError("annotation_rejected")
        if kind == "comment" and (not note.strip() or label or page is not None):
            raise BoundPrivateRecordError("annotation_rejected")
        if kind == "label" and (not label.strip() or label != label.strip() or note or page is not None):
            raise BoundPrivateRecordError("annotation_rejected")
        if kind == "page_span":
            if (type(page) is not int or isinstance(page, bool) or not 1 <= page <= 10000
                    or type(span_start) is not int or isinstance(span_start, bool) or span_start < 0
                    or type(span_end) is not int or isinstance(span_end, bool)
                    or span_end <= span_start or span_end > 1_000_000):
                raise BoundPrivateRecordError("annotation_rejected")
        elif page is not None or span_start is not None or span_end is not None:
            raise BoundPrivateRecordError("annotation_rejected")
        if claim_element is None:
            stored_claim = ""
        elif not isinstance(claim_element, str) or claim_element != claim_element.strip() or len(claim_element) > 80:
            raise BoundPrivateRecordError("annotation_rejected")
        else:
            stored_claim = claim_element
        return {
            "kind": kind,
            "evidence_id": evidence_id,
            "artifact_version": artifact_version,
            "actor_principal_id": actor_principal_id,
            "canonical_owner_principal_id": canonical_owner_principal_id,
            "actor_is_canonical_owner": actor_principal_id == canonical_owner_principal_id,
            "tenant_id": tenant_id,
            "case_id": case_id,
            "note": note,
            "label": label,
            "page": page,
            "span_start": span_start,
            "span_end": span_end,
            "anchor": f"page-{page}-span-{span_start}-{span_end}" if kind == "page_span" else "",
            "claim_element": stored_claim,
            "claim_element_is_causation": stored_claim == "causation",
        }

    def _annotation_binding(
        self,
        *,
        tenant_id: str,
        case_id: str,
        canonical_owner_principal_id: str,
        revision: str,
    ) -> PrivateArtifactBinding:
        return PrivateArtifactBinding(
            tenant_id=tenant_id,
            case_id=case_id,
            artifact_kind="annotation",
            revision=revision,
            principal_id=canonical_owner_principal_id,
        )

    def _head_dir(self, *, tenant_id: str, case_id: str, canonical_owner_principal_id: str) -> Path:
        digest = hashlib.sha256(
            "\n".join((tenant_id, case_id, canonical_owner_principal_id)).encode("utf-8")
        ).hexdigest()
        return self._root / "heads" / digest

    def _load_head(
        self,
        *,
        tenant_id: str,
        case_id: str,
        canonical_owner_principal_id: str,
        key: bytes,
    ) -> dict[str, Any]:
        pointer = self._head_dir(
            tenant_id=tenant_id,
            case_id=case_id,
            canonical_owner_principal_id=canonical_owner_principal_id,
        ) / "pointer.json"
        empty = {
            "tenant_id": tenant_id,
            "case_id": case_id,
            "canonical_owner_principal_id": canonical_owner_principal_id,
            "chains": {},
        }
        if not pointer.exists():
            return empty
        meta = json.loads(pointer.read_text(encoding="utf-8"))
        record_id = str(meta.get("record_id") or "")
        binding = self._annotation_binding(
            tenant_id=tenant_id,
            case_id=case_id,
            canonical_owner_principal_id=canonical_owner_principal_id,
            revision=record_id,
        )
        opened = json.loads(self.read(record_id=record_id, binding=binding, key=key))
        if opened.get("schema") != "evidence-annotation-head@1":
            raise BoundPrivateRecordError("annotation_unavailable")
        if not isinstance(opened.get("chains"), dict):
            raise BoundPrivateRecordError("annotation_unavailable")
        return opened

    def _commit_head(
        self,
        head: dict[str, Any],
        *,
        key: bytes,
        key_id: str,
        remote_backend: Any | None,
    ) -> None:
        payload = _canonical({
            "schema": "evidence-annotation-head@1",
            "tenant_id": head["tenant_id"],
            "case_id": head["case_id"],
            "canonical_owner_principal_id": head["canonical_owner_principal_id"],
            "chains": head["chains"],
        })
        record_id = "idx-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
        binding = self._annotation_binding(
            tenant_id=head["tenant_id"],
            case_id=head["case_id"],
            canonical_owner_principal_id=head["canonical_owner_principal_id"],
            revision=record_id,
        )
        receipt = commit_private_bound_record(
            self._root,
            record_id=record_id,
            kind="annotation",
            plaintext=payload.encode("utf-8"),
            binding=binding,
            key=key,
            key_id=key_id,
            remote_backend=remote_backend,
        )
        if receipt.get("local_durable") is not True:
            raise BoundPrivateRecordError("annotation_unavailable")
        directory = self._head_dir(
            tenant_id=head["tenant_id"],
            case_id=head["case_id"],
            canonical_owner_principal_id=head["canonical_owner_principal_id"],
        )
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / f".pointer-{record_id}.json"
        temporary.write_text(
            json.dumps({"record_id": record_id, "schema": "evidence-annotation-head-pointer@1"}),
            encoding="utf-8",
        )
        os.replace(temporary, directory / "pointer.json")

    @staticmethod
    def _public_view(body: Mapping[str, Any], *, revision: str, replay: bool) -> dict[str, Any]:
        return {
            "task_id": ANNOTATION_TASK_ID,
            "annotation_id": body["annotation_id"],
            "evidence_id": body["evidence_id"],
            "artifact_version": body["artifact_version"],
            "kind": body["kind"],
            "actor_principal_id": body["actor_principal_id"],
            "canonical_owner_principal_id": body["canonical_owner_principal_id"],
            "actor_is_canonical_owner": body["actor_is_canonical_owner"],
            "tenant_id": body["tenant_id"],
            "case_id": body["case_id"],
            "note": body["note"],
            "label": body["label"],
            "page": body["page"],
            "span_start": body["span_start"],
            "span_end": body["span_end"],
            "anchor": body["anchor"],
            "record_type": "note",
            "adopted": False,
            "adopted_as_evidence": False,
            "synthesized_evidence": False,
            "display_role_authoritative": False,
            "claim_element": body["claim_element"],
            "claim_element_is_causation": body["claim_element"] == "causation",
            "claim_element_defaulted": False,
            "establishes_claim_element": False,
            "establishes_causation": False,
            "annotation_revision": revision,
            "idempotent_replay": replay,
            "content_address_is_encryption": False,
        }

    @staticmethod
    def _require_kind(binding: PrivateArtifactBinding, kind: str) -> None:
        if not isinstance(binding, PrivateArtifactBinding) or binding.artifact_kind != kind:
            raise BoundPrivateRecordError("binding_kind_mismatch")

    @staticmethod
    def _label(value: str, code: str) -> None:
        if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > 80:
            raise BoundPrivateRecordError(code)

    @staticmethod
    def _token(value: str, code: str) -> None:
        if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > 180:
            raise BoundPrivateRecordError(code)
        if any(char in value for char in ("\x00", "\n", "\r")):
            raise BoundPrivateRecordError(code)


def _chain_key(evidence_id: str, artifact_version: int) -> str:
    return f"{evidence_id}\n{artifact_version}"


def _canonical(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
