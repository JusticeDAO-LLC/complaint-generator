"""Synthetic adversarial recipes for the complaint UX security cases.

The world is the existing owner, lawyer, admin, and stranger journey. This
module does not mint membership, consent, key grants, or custody receipts.
Ciphertext stays in a process-local byte store that reports no remote pin.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from applications.case_attachment_api import CaseAttachmentService
from integrations.evidence_workspace import EvidenceWorkspace
from integrations.private_collaboration import SharedAttachmentStore
from tests.gui_ux_overhaul_fixtures import (
    ADMIN_CREDENTIAL,
    LAWYER_CREDENTIAL,
    OWNER_CREDENTIAL,
    synthetic_capture_world,
)

STRANGER_CREDENTIAL = "synthetic-stranger-credential"
HOSTILE_HTML = (
    b"<script>window.__previewRan=1</script>"
    b"<iframe src=\"https://evil.invalid/frame\"></iframe>"
    b"<img src=\"https://evil.invalid/pixel.png\">"
    b"synthetic-hostile-ux63"
)
SEALED_TEXT = b"Synthetic sealed sentence ux63 stays in the owner case."
ATTACHMENT_TEXT = b"Synthetic attachment sentence ux63 is not a proof."
UNSUPPORTED_TRANSPORTS = ("websocket", "sse", "streaming")
REFUSED_AUTHORITY_FIELDS = (
    "authorized",
    "self_authorized",
    "custody_proof",
    "custody_receipt",
    "governing_law",
    "verified_support",
)


class LocalCiphertextBytes:
    """Hold sealed envelopes in memory. A CID is a locator, not durability."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def add_bytes(self, data: bytes, pin: bool = True) -> dict[str, object]:
        blob = bytes(data)
        cid = "bafy" + hashlib.sha256(blob).hexdigest()[:55]
        self.objects[cid] = blob
        return {"cid": cid, "success": True, "pinned": False, "status": "available"}

    def cat(self, cid: str):
        found = self.objects.get(cid)
        if found is None:
            return {"success": False, "error": "missing", "cid": cid, "status": "missing"}
        return found

    def replicate(self, data: bytes) -> None:
        """Keep a local copy. Replication here is not a remote replica receipt."""

        blob = bytes(data)
        self.objects.setdefault("replica-" + hashlib.sha256(blob).hexdigest()[:16], blob)


def refuse_self_authorization(record: dict) -> None:
    """A fixture recipe cannot declare itself authorized or proven."""

    if not isinstance(record, dict):
        raise ValueError("security_record_required")
    present = [name for name in REFUSED_AUTHORITY_FIELDS if name in record]
    if present:
        raise ValueError("self_authorization_refused")
    if record.get("pinned") is True or record.get("remote_durable") is True:
        raise ValueError("fake_custody_refused")


def assert_fixture_source_has_no_authority_bypass(path: Path) -> None:
    """The declared test sources must not disable inherited guards."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = ""
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            if name in {"exec", "eval", "compile"}:
                raise ValueError("authority_bypass_call")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names]
            if any(name.split(".")[0] in {"socket", "subprocess", "ctypes"} for name in names):
                raise ValueError("inherited_guard_import")


def security_world(tmp_path: Path):
    """Journey app plus the real evidence and attachment owners.

    Admin remains an operational role. Stranger and lawyer receive no case
    grant from this constructor.
    """

    world = synthetic_capture_world(tmp_path / "journey")
    from integrations.evidence_workspace import MemoryByteBackend

    evidence_backend = MemoryByteBackend()
    evidence = EvidenceWorkspace(
        world.cases,
        {world.owner.principal_id: world.owner_keys, world.lawyer.principal_id: world.recipient},
        evidence_backend,
        tmp_path / "evidence-root",
    )
    world.app.state.evidence_workspace = evidence
    ciphertext = LocalCiphertextBytes()
    attachments = CaseAttachmentService(
        SharedAttachmentStore(tmp_path / "attachments", world.grants, backend=ciphertext),
        {world.owner.principal_id: world.owner_keys, world.lawyer.principal_id: world.recipient},
    )
    messages = world.app.state.case_messages
    attachments.bind_message_admission(messages.store)
    messages.bind_attachments(attachments)
    world.app.state.case_attachments = attachments
    world.evidence = evidence
    world.evidence_backend = evidence_backend
    world.ciphertext = ciphertext
    world.attachments = attachments
    if world.admin.principal_id in {world.owner.principal_id, world.lawyer.principal_id, world.stranger.principal_id}:
        raise RuntimeError("admin_collapsed_into_case_actor")
    if world.stranger.principal_id == world.owner.principal_id:
        raise RuntimeError("stranger_is_owner")
    return world


__all__ = [
    "ADMIN_CREDENTIAL",
    "ATTACHMENT_TEXT",
    "HOSTILE_HTML",
    "LAWYER_CREDENTIAL",
    "OWNER_CREDENTIAL",
    "SEALED_TEXT",
    "STRANGER_CREDENTIAL",
    "UNSUPPORTED_TRANSPORTS",
    "assert_fixture_source_has_no_authority_bypass",
    "refuse_self_authorization",
    "security_world",
]
