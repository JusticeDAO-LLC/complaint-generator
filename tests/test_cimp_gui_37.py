"""Encrypted shared attachments and derived artifacts.

Positive cases seal the file, its preview, and its derived index before a Kit
backend add or replicate, then deliver bytes only to the actor who still holds
the matching grant. Negative cases reject content policy violations, a swapped
resource, and a download after revocation. Public listings and Kit bytes omit
the filename, preview, and index terms.
"""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.browser_sessions import (
    SESSION_COOKIE,
    BrowserSessionConfiguration,
    BrowserSessionService,
    VerifiedPrincipal,
)
from applications.case_attachment_api import CaseAttachmentService
from applications.case_directory import CaseDirectory
from applications.case_membership import CaseMembershipStore
from applications.case_routes import compose_case_routes
from applications.principal_store import PrincipalStore
from integrations.private_collaboration import (
    ATTACHMENT_KIND,
    SharedAttachmentError,
    SharedAttachmentStore,
    CaseResourceKeyGrantStore,
)
from integrations.private_storage import ENVELOPE_MAGIC, UserOwnedKeySession

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

REVISION = "7"
FILENAME = "notice-991.pdf"
SECRET = b"UNIQUE-BODY-TOKEN-991"
PREVIEW_MARK = b"%PDF-1.4\nUNIQUE-BODY"


class _Kit:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.added: list[bytes] = []
        self.replicated: list[bytes] = []

    def add_bytes(self, data: bytes, pin: bool = True) -> dict[str, object]:
        blob = bytes(data)
        self.added.append(blob)
        cid = "cid" + hashlib.sha256(blob).hexdigest()[:24]
        self.objects[cid] = blob
        return {"cid": cid, "success": True, "pinned": True, "status": "available"}

    def cat(self, cid: str):
        if cid not in self.objects:
            return {"success": False, "error": "missing", "cid": cid}
        return self.objects[cid]

    def pin(self, cid: str) -> dict[str, object]:
        return {"cid": cid, "success": True, "pinned": True, "status": "available"}

    def replicate(self, data: bytes) -> None:
        self.replicated.append(bytes(data))


class _Adapter:
    def __init__(self, principals: dict[str, VerifiedPrincipal]) -> None:
        self.principals = principals

    def verify_credential(self, material: dict) -> VerifiedPrincipal:
        principal = self.principals.get(str(material.get("credential") or ""))
        if principal is None:
            raise RuntimeError("authentication_failed")
        return principal


def _pdf() -> bytes:
    return b"%PDF-1.4\n" + SECRET + b"\n" + (b"synthetic page\n" * 8)


def _world(tmp_path: Path):
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    cases = CaseDirectory(tmp_path / "cases", key=os.urandom(32), key_id="case-key")
    owner = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    case = cases.create_case(actor_principal_id=owner.principal_id)
    memberships = CaseMembershipStore(
        tmp_path / "memberships", key=os.urandom(32), key_id="membership-key",
        principals=principals, cases=cases, clock=lambda: 1_700_000_000,
    )
    grants = CaseResourceKeyGrantStore(
        tmp_path / "key-grants", key=os.urandom(32), key_id="resource-grant-key",
        principals=principals, cases=cases, memberships=memberships,
    )
    owner_session = UserOwnedKeySession(tmp_path / "owner-keys")
    owner_session.create(protection="passphrase", passphrase="owner-passphrase")
    lawyer_session = UserOwnedKeySession(tmp_path / "lawyer-keys")
    lawyer_session.create(protection="passphrase", passphrase="lawyer-passphrase")
    owner_session.ensure_data_key(case.tenant_id, case.case_id)
    kit = _Kit()
    store = SharedAttachmentStore(tmp_path / "attachments", grants, backend=kit)
    service = CaseAttachmentService(store, {owner.principal_id: owner_session, lawyer.principal_id: lawyer_session})
    return {
        "principals": principals, "cases": cases, "memberships": memberships, "grants": grants,
        "owner": owner, "lawyer": lawyer, "case": case, "owner_session": owner_session,
        "lawyer_session": lawyer_session, "kit": kit, "store": store, "service": service,
    }


def _accept(world, key: str):
    case = world["case"]
    pending = world["memberships"].invite(
        owner_principal_id=world["owner"].principal_id, member_principal_id=world["lawyer"].principal_id,
        case_id=case.case_id, resource_id=case.resource_id, tenant_id=case.tenant_id,
        actions={"case.read", "case.download", "case.message.send"}, expires_at=1_700_003_600,
        expected_case_revision=case.revision, idempotency_key=key,
    )
    return world["memberships"].accept(
        member_principal_id=world["lawyer"].principal_id, grant_id=pending.grant_id,
        expected_version=pending.version, idempotency_key=key + "-accept",
    )


def _grant(world, membership, key: str):
    case = world["case"]
    return world["grants"].issue(
        actor_principal_id=world["owner"].principal_id, recipient_principal_id=world["lawyer"].principal_id,
        membership_grant_id=membership.grant_id, membership_version=membership.version,
        case_id=case.case_id, resource_id=case.resource_id, tenant_id=case.tenant_id,
        artifact_kind=ATTACHMENT_KIND, artifact_revision=REVISION, owner_session=world["owner_session"],
        recipient_session=world["lawyer_session"], idempotency_key=key,
    )


def _owner_body(world, content: bytes, *, key: str = "store-1", filename: str = FILENAME, media: str = "application/pdf"):
    case = world["case"]
    return {
        "tenant_id": case.tenant_id, "case_id": case.case_id, "resource_id": case.resource_id,
        "artifact_revision": REVISION, "filename": filename, "media_type": media,
        "content_base64": base64.b64encode(content).decode("ascii"), "idempotency_key": key,
    }


def _lawyer_body(world, membership, grant, **extra):
    body = _owner_body(world, _pdf(), **extra) if "content" not in extra else extra.pop("content")
    if not isinstance(body, dict):
        body = _owner_body(world, _pdf())
    body = dict(body)
    body.update(extra)
    body["membership_grant_id"] = membership.grant_id
    body["membership_version"] = membership.version
    body["key_grant_id"] = grant.key_grant_id
    return body


def _assert_private(world, *needles: bytes) -> None:
    blobs = list(world["kit"].added) + list(world["kit"].replicated) + list(world["kit"].objects.values())
    assert blobs
    for blob in blobs:
        assert blob.startswith(ENVELOPE_MAGIC)
        for needle in needles:
            assert needle not in blob
    root = world["store"]._root
    for path in root.rglob("*"):
        if path.is_file() and path.name != ".lock":
            raw = path.read_bytes()
            for needle in needles:
                assert needle not in raw


def test_owner_store_encrypts_before_kit_and_lawyer_download_rechecks_grant(tmp_path: Path) -> None:
    world = _world(tmp_path)
    stored = world["service"].store_attachment(world["owner"].principal_id, _owner_body(world, _pdf()))
    assert stored["encrypted_before_kit"] is True
    assert stored["actor_is_encrypted_owner"] is False
    assert stored["canonical_owner_principal_id"] == world["case"].tenant_id
    assert stored["actor_principal_id"] == world["owner"].principal_id
    assert stored["artifact_kind"] == ATTACHMENT_KIND
    assert "filename" not in stored and "content_base64" not in stored
    assert world["kit"].added and world["kit"].replicated
    assert len(world["kit"].added) == 3
    assert world["kit"].replicated == world["kit"].added
    _assert_private(world, FILENAME.encode(), SECRET, PREVIEW_MARK)
    listed = world["service"].list_attachments(world["owner"].principal_id, _owner_body(world, _pdf()))
    assert listed["attachments"][0]["attachment_id"] == stored["attachment_id"]
    assert "filename" not in listed["attachments"][0]
    membership = _accept(world, "member-1")
    grant = _grant(world, membership, "grant-1")
    downloaded = world["service"].download_attachment(
        world["lawyer"].principal_id, stored["attachment_id"],
        _lawyer_body(world, membership, grant),
    )
    assert base64.b64decode(downloaded["content_base64"]) == _pdf()
    assert downloaded["filename"] == FILENAME
    assert downloaded["delivered_after_grant_recheck"] is True
    assert downloaded["actor_is_encrypted_owner"] is False
    preview = world["service"].download_attachment(
        world["lawyer"].principal_id, stored["attachment_id"],
        {**_lawyer_body(world, membership, grant), "artifact_role": "preview"},
    )
    assert base64.b64decode(preview["content_base64"]) == _pdf()[:32]
    index = world["service"].download_attachment(
        world["lawyer"].principal_id, stored["attachment_id"],
        {**_lawyer_body(world, membership, grant), "artifact_role": "derived-index"},
    )
    assert FILENAME.encode() in base64.b64decode(index["content_base64"])
    world["grants"].revoke_and_rotate(
        actor_principal_id=world["owner"].principal_id, recipient_principal_id=world["lawyer"].principal_id,
        case_id=world["case"].case_id, tenant_id=world["case"].tenant_id, resource_id=world["case"].resource_id,
        cutoff=grant.generation, owner_session=world["owner_session"], idempotency_key="revoke-1",
    )
    with pytest.raises(SharedAttachmentError) as denied:
        world["service"].download_attachment(
            world["lawyer"].principal_id, stored["attachment_id"], _lawyer_body(world, membership, grant),
        )
    assert denied.value.code != "missing_attachment"
    owner_copy = world["service"].download_attachment(
        world["owner"].principal_id, stored["attachment_id"], _owner_body(world, _pdf()),
    )
    assert base64.b64decode(owner_copy["content_base64"]) == _pdf()


def test_policy_mismatch_and_swapped_index_fail_closed(tmp_path: Path) -> None:
    world = _world(tmp_path)
    before = len(world["kit"].added)
    with pytest.raises(SharedAttachmentError) as huge:
        world["service"].store_attachment(
            world["owner"].principal_id, _owner_body(world, b"%PDF-" + b"x" * (256 * 1024), key="big"),
        )
    assert huge.value.code == "attachment_too_large"
    with pytest.raises(SharedAttachmentError) as elf:
        world["service"].store_attachment(
            world["owner"].principal_id,
            _owner_body(world, b"\x7fELF" + b"synthetic", key="elf", filename="note.txt", media="text/plain"),
        )
    assert elf.value.code == "content_rejected"
    with pytest.raises(SharedAttachmentError) as named:
        world["service"].store_attachment(
            world["owner"].principal_id, _owner_body(world, _pdf(), key="path", filename="../notice.pdf"),
        )
    assert named.value.code == "filename_rejected"
    assert len(world["kit"].added) == before
    stored = world["service"].store_attachment(world["owner"].principal_id, _owner_body(world, _pdf(), key="ok"))
    membership = _accept(world, "member-2")
    grant = _grant(world, membership, "grant-2")
    body = _lawyer_body(world, membership, grant)
    body["resource_id"] = "other-resource"
    with pytest.raises(SharedAttachmentError) as mismatch:
        world["service"].download_attachment(world["lawyer"].principal_id, stored["attachment_id"], body)
    assert mismatch.value.code == "resource_mismatch"
    record_path = world["store"]._root / "records" / f"{stored['attachment_id']}.json"
    text = record_path.read_text(encoding="utf-8").replace(stored["content_cid"], stored["index_cid"])
    record_path.write_text(text, encoding="utf-8")
    with pytest.raises(SharedAttachmentError) as swapped:
        world["service"].download_attachment(world["lawyer"].principal_id, stored["attachment_id"], _lawyer_body(world, membership, grant))
    assert swapped.value.code == "attachment_role_mismatch"
    with pytest.raises(SharedAttachmentError) as browser:
        world["service"].store_attachment(world["owner"].principal_id, {**_owner_body(world, _pdf(), key="browser"), "browser_key": "nope"})
    assert browser.value.code == "browser_key_rejected"


def test_http_catalog_stores_and_denies_revoked_download(tmp_path: Path) -> None:
    world = _world(tmp_path)
    case = world["case"]
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=_Adapter({
            "synthetic-owner-credential": VerifiedPrincipal(world["owner"].principal_id, case.tenant_id, ("complainant",)),
            "synthetic-lawyer-credential": VerifiedPrincipal(world["lawyer"].principal_id, case.tenant_id, ("lawyer",)),
        }),
        signing_key=os.urandom(32), ttl_seconds=600,
    ))
    app = FastAPI()
    compose_case_routes(
        app, authorizer=None, browser_sessions=sessions, case_attachments=world["service"],
        include_workspace=False, include_review=False, include_document=False,
    )
    membership = _accept(world, "member-3")
    grant = _grant(world, membership, "grant-3")
    with TestClient(app, base_url="https://testserver") as client:
        login = client.post("/api/complaint-workspace/auth/login", json={"credential": "synthetic-owner-credential"})
        assert login.status_code == 200, login.text
        assert client.cookies.get(SESSION_COOKIE)
        csrf = login.json()["csrf_token"]
        created = client.post(
            "/api/cases/attachments", headers={"x-csrf-token": csrf},
            json=_owner_body(world, _pdf(), key="http-1"),
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["private_filename"] is True and "filename" not in body
        assert FILENAME not in created.text and SECRET.decode() not in created.text
        listed = client.get(
            "/api/cases/attachments",
            params={"tenant_id": case.tenant_id, "case_id": case.case_id, "resource_id": case.resource_id},
        )
        assert listed.status_code == 200, listed.text
        assert listed.json()["attachments"][0]["attachment_id"] == body["attachment_id"]
        assert FILENAME not in listed.text
        downloaded = client.post(
            f"/api/cases/attachments/{body['attachment_id']}/download",
            headers={"x-csrf-token": csrf}, json=_owner_body(world, b"", key="unused"),
        )
        assert downloaded.status_code == 200, downloaded.text
        assert base64.b64decode(downloaded.json()["content_base64"]) == _pdf()
        logout = client.post("/api/complaint-workspace/auth/logout", headers={"x-csrf-token": csrf})
        assert logout.status_code == 200, logout.text
        lawyer_login = client.post("/api/complaint-workspace/auth/login", json={"credential": "synthetic-lawyer-credential"})
        assert lawyer_login.status_code == 200, lawyer_login.text
        lawyer_csrf = lawyer_login.json()["csrf_token"]
        granted = client.post(
            f"/api/cases/attachments/{body['attachment_id']}/download",
            headers={"x-csrf-token": lawyer_csrf},
            json=_lawyer_body(world, membership, grant),
        )
        assert granted.status_code == 200, granted.text
        assert base64.b64decode(granted.json()["content_base64"]) == _pdf()
        world["grants"].revoke_and_rotate(
            actor_principal_id=world["owner"].principal_id, recipient_principal_id=world["lawyer"].principal_id,
            case_id=case.case_id, tenant_id=case.tenant_id, resource_id=case.resource_id,
            cutoff=grant.generation, owner_session=world["owner_session"], idempotency_key="revoke-http",
        )
        denied = client.post(
            f"/api/cases/attachments/{body['attachment_id']}/download",
            headers={"x-csrf-token": lawyer_csrf},
            json=_lawyer_body(world, membership, grant),
        )
        assert denied.status_code == 403, denied.text
        assert "content_base64" not in denied.json()
        assert SECRET.decode() not in denied.text
