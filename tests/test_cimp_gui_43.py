"""Message attachments are admitted only for the current thread.

Reads, writes, and previews repeat the thread, membership, key grant, and
resource revision checks. A path, a CID, another thread, or another tenant
cannot select bytes. Plaintext responses are marked uncacheable, and notices
name only the admitted thread.
"""

from __future__ import annotations

import base64
import hashlib
import os
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.browser_sessions import (
    SESSION_COOKIE,
    BrowserSessionConfiguration,
    BrowserSessionService,
    PrincipalStoreCredentialAdapter,
)
from applications.case_access import CaseActionAuthorizer
from applications.case_api import CaseCatalog
from applications.case_assignment_api import CaseAssignmentService
from applications.case_attachment_api import CaseAttachmentService
from applications.case_directory import CaseDirectory
from applications.case_membership import CaseMembershipStore
from applications.case_message_api import CaseMessageService
from applications.case_messages import CaseMessageStore
from applications.case_routes import compose_case_routes
from applications.principal_store import PrincipalStore
from integrations.private_collaboration import (
    ATTACHMENT_KIND,
    CaseResourceKeyGrantStore,
    SharedAttachmentStore,
)
from integrations.private_storage import ENVELOPE_MAGIC, UserOwnedKeySession

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

OWNER_CREDENTIAL = "synthetic-password"
LAWYER_CREDENTIAL = "synthetic-auth-token"
STRANGER_CREDENTIAL = "synthetic-refresh-token"
REVISION = "7"
FILENAME = "notice-991.pdf"
SECRET = b"UNIQUE-BODY-TOKEN-991"


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


def _pdf() -> bytes:
    return b"%PDF-1.4\n" + SECRET + b"\n" + (b"synthetic page\n" * 4)


def _world(tmp_path):
    now = {"t": 1_700_000_000}

    def clock():
        return now["t"]

    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    case_key = os.urandom(32)
    cases = CaseDirectory(tmp_path / "cases", key=case_key, key_id="case-key")
    owner = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    stranger = principals.register_from_request({})
    memberships = CaseMembershipStore(
        tmp_path / "memberships", key=os.urandom(32), key_id="membership-key",
        principals=principals, cases=cases, clock=clock,
    )
    key_grants = CaseResourceKeyGrantStore(
        tmp_path / "key-grants", key=os.urandom(32), key_id="resource-grant-key",
        principals=principals, cases=cases, memberships=memberships,
    )
    messages = CaseMessageStore(
        tmp_path / "messages", key=os.urandom(32), key_id="message-key",
        principals=principals, cases=cases, memberships=memberships, clock=clock,
    )
    owner_session = UserOwnedKeySession(tmp_path / "owner-keys")
    owner_session.create(protection="passphrase", passphrase="owner-passphrase")
    lawyer_session = UserOwnedKeySession(tmp_path / "lawyer-keys")
    lawyer_session.create(protection="passphrase", passphrase="lawyer-passphrase")
    stranger_session = UserOwnedKeySession(tmp_path / "stranger-keys")
    stranger_session.create(protection="passphrase", passphrase="stranger-passphrase")
    kit = _Kit()
    attachments = CaseAttachmentService(
        SharedAttachmentStore(tmp_path / "attachments", key_grants, backend=kit),
        {
            owner.principal_id: owner_session,
            lawyer.principal_id: lawyer_session,
            stranger.principal_id: stranger_session,
        },
    )
    message_service = CaseMessageService(messages)
    assignments = CaseAssignmentService(
        principals=principals, cases=cases, memberships=memberships, key_grants=key_grants,
        sessions={
            owner.principal_id: owner_session,
            lawyer.principal_id: lawyer_session,
            stranger.principal_id: stranger_session,
        },
        clock=clock,
    )
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            OWNER_CREDENTIAL: owner.principal_id,
            LAWYER_CREDENTIAL: lawyer.principal_id,
            STRANGER_CREDENTIAL: stranger.principal_id,
        }),
        signing_key=os.urandom(32),
        ttl_seconds=120,
    ))
    authorizer = CaseActionAuthorizer(principals, cases)
    catalog = CaseCatalog(cases, authorizer, key=case_key, key_id="case-key")
    app = FastAPI()
    compose_case_routes(
        app, authorizer=authorizer, browser_sessions=sessions, case_catalog=catalog,
        case_assignments=assignments, case_messages=message_service, case_attachments=attachments,
        include_workspace=False, include_review=False, include_document=False,
    )
    return SimpleNamespace(
        app=app, owner=owner, lawyer=lawyer, stranger=stranger, now=now, memberships=memberships,
        grants=key_grants, owner_session=owner_session, lawyer_session=lawyer_session,
        stranger_session=stranger_session, kit=kit, attachments=attachments, messages=message_service,
    )


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _csrf(token):
    return {"x-csrf-token": token, "content-type": "application/json"}


def _create_case(client, token, label="owned"):
    created = client.post("/api/cases", headers=_csrf(token), json={"label": label})
    assert created.status_code == 201, created.text
    return created.json()


def _invite(owner_client, owner_token, lawyer_client, lawyer_token, world, case):
    scope = ["case.read", "case.message.send", "case.download", "case.review"]
    invited = owner_client.post("/api/cases/assignments", headers=_csrf(owner_token), json={
        "case_id": case["case_id"],
        "member_principal_id": world.lawyer.principal_id,
        "scope": scope,
        "expires_at": world.now["t"] + 500,
        "expected_case_revision": case["directory_revision"],
        "idempotency_key": "invite-attach",
    })
    assert invited.status_code == 201, invited.text
    grant_id = invited.json()["grant_id"]
    accepted = lawyer_client.post(f"/api/cases/assignments/{grant_id}/accept", headers=_csrf(lawyer_token), json={
        "scope": scope,
        "expected_version": 1,
        "idempotency_key": "invite-attach-accept",
    })
    assert accepted.status_code == 200, accepted.text
    return grant_id, accepted.json()["version"]


def _thread(client, token, case, key):
    response = client.post("/api/cases/messages/threads", headers=_csrf(token), json={
        "case_id": case["case_id"], "idempotency_key": key,
    })
    assert response.status_code == 201, response.text
    return response.json()["thread_id"]


def _body(case, thread_id, *, key="file-1", content=None, **extra):
    payload = {
        "tenant_id": case["tenant_id"],
        "case_id": case["case_id"],
        "resource_id": case["resource_id"],
        "expected_revision": case["directory_revision"],
        "artifact_revision": REVISION,
        "thread_id": thread_id,
        "filename": FILENAME,
        "media_type": "application/pdf",
        "content_base64": base64.b64encode(_pdf() if content is None else content).decode("ascii"),
        "idempotency_key": key,
    }
    payload.update(extra)
    return payload


def _grant(world, case, membership_id, version):
    world.owner_session.ensure_data_key(case["tenant_id"], case["case_id"])
    return world.grants.issue(
        actor_principal_id=world.owner.principal_id,
        recipient_principal_id=world.lawyer.principal_id,
        membership_grant_id=membership_id,
        membership_version=version,
        case_id=case["case_id"],
        resource_id=case["resource_id"],
        tenant_id=case["tenant_id"],
        artifact_kind=ATTACHMENT_KIND,
        artifact_revision=REVISION,
        owner_session=world.owner_session,
        recipient_session=world.lawyer_session,
        idempotency_key="key-grant-attach",
    )


def _assert_private(world) -> None:
    blobs = list(world.kit.added) + list(world.kit.replicated)
    assert blobs
    for blob in blobs:
        assert blob.startswith(ENVELOPE_MAGIC)
        assert FILENAME.encode() not in blob
        assert SECRET not in blob


def test_thread_attachment_admission_preview_and_notice_are_bound(tmp_path) -> None:
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as owner_client, TestClient(world.app, base_url="https://testserver") as lawyer_client, TestClient(world.app, base_url="https://testserver") as stranger_client:
        owner_token = _login(owner_client, OWNER_CREDENTIAL)
        lawyer_token = _login(lawyer_client, LAWYER_CREDENTIAL)
        stranger_token = _login(stranger_client, STRANGER_CREDENTIAL)
        case = _create_case(owner_client, owner_token)
        other = _create_case(owner_client, owner_token, label="other")
        foreign = _create_case(stranger_client, stranger_token, label="foreign")
        world.stranger_session.ensure_data_key(foreign["tenant_id"], foreign["case_id"])
        membership_id, membership_version = _invite(owner_client, owner_token, lawyer_client, lawyer_token, world, case)
        key_grant = _grant(world, case, membership_id, membership_version)
        thread_id = _thread(owner_client, owner_token, case, "thread-a")
        other_thread = _thread(owner_client, owner_token, case, "thread-b")
        foreign_thread = _thread(stranger_client, stranger_token, foreign, "thread-foreign")

        before = len(world.kit.added)
        rejected = owner_client.post(
            f"/api/cases/messages/threads/{thread_id}/attachments",
            headers=_csrf(owner_token),
            json={**_body(case, thread_id, key="path-1"), "path": "/tmp/notice-991.pdf", "cid": "cid-picked"},
        )
        assert rejected.status_code == 403, rejected.text
        assert rejected.json()["error"] == "selector_rejected"
        assert FILENAME not in rejected.text and SECRET.decode() not in rejected.text
        assert len(world.kit.added) == before

        created = owner_client.post(
            f"/api/cases/messages/threads/{thread_id}/attachments",
            headers=_csrf(owner_token),
            json=_body(case, thread_id),
        )
        assert created.status_code == 201, created.text
        assert "no-store" in created.headers["cache-control"]
        stored = created.json()
        assert stored["thread_id"] == thread_id
        assert stored["resource_revision"] == case["directory_revision"]
        assert stored["bound_to_thread"] is True
        assert stored["selector"] == "attachment_id"
        assert "content_cid" not in stored and "preview_cid" not in stored and "index_cid" not in stored
        assert "filename" not in stored and SECRET.decode() not in created.text
        _assert_private(world)
        replay = owner_client.post(
            f"/api/cases/messages/threads/{thread_id}/attachments",
            headers=_csrf(owner_token),
            json=_body(case, thread_id),
        )
        assert replay.status_code == 201, replay.text
        assert replay.json()["attachment_id"] == stored["attachment_id"]
        crossed = owner_client.post(
            f"/api/cases/messages/threads/{other_thread}/attachments",
            headers=_csrf(owner_token),
            json=_body(case, other_thread),
        )
        assert crossed.status_code == 409, crossed.text
        assert crossed.json()["error"] == "replay_mismatch"

        stale = owner_client.post(
            f"/api/cases/messages/threads/{thread_id}/attachments",
            headers=_csrf(owner_token),
            json=_body(case, thread_id, key="stale", expected_revision=case["directory_revision"] + 9),
        )
        assert stale.status_code == 409, stale.text
        assert stale.json()["error"] == "revision_conflict"

        listed = owner_client.get(
            f"/api/cases/messages/threads/{thread_id}/attachments",
            params=_body(case, thread_id),
        )
        assert listed.status_code == 200, listed.text
        assert listed.json()["attachments"][0]["attachment_id"] == stored["attachment_id"]
        assert "filename" not in listed.json()["attachments"][0]
        assert "content_cid" not in listed.text and FILENAME not in listed.text
        hidden = owner_client.get(
            f"/api/cases/messages/threads/{other_thread}/attachments",
            params=_body(case, other_thread),
        )
        assert hidden.status_code == 200, hidden.text
        assert stored["attachment_id"] not in hidden.text

        lawyer_body = _body(
            case, thread_id,
            membership_grant_id=membership_id,
            membership_version=membership_version,
            expected_membership_version=membership_version,
            key_grant_id=key_grant.key_grant_id,
        )
        preview = lawyer_client.post(
            f"/api/cases/messages/threads/{thread_id}/attachments/{stored['attachment_id']}/preview",
            headers=_csrf(lawyer_token),
            json=lawyer_body,
        )
        assert preview.status_code == 200, preview.text
        assert "no-store" in preview.headers["cache-control"]
        assert preview.json()["role"] == "preview"
        assert "content_cid" not in preview.json()
        assert base64.b64decode(preview.json()["content_base64"]) == _pdf()[:32]
        downloaded = lawyer_client.post(
            f"/api/cases/messages/threads/{thread_id}/attachments/{stored['attachment_id']}/download",
            headers=_csrf(lawyer_token),
            json=lawyer_body,
        )
        assert downloaded.status_code == 200, downloaded.text
        assert "no-store" in downloaded.headers["cache-control"]
        assert base64.b64decode(downloaded.json()["content_base64"]) == _pdf()
        assert downloaded.json()["delivered_after_grant_recheck"] is True

        notices = lawyer_client.get(
            f"/api/cases/messages/threads/{thread_id}/attachment-notices",
            params=lawyer_body,
        )
        assert notices.status_code == 200, notices.text
        assert notices.json()["notices"][0]["attachment_id"] == stored["attachment_id"]
        assert notices.json()["notices"][0]["tenant_id"] == case["tenant_id"]
        assert "filename" not in notices.text and SECRET.decode() not in notices.text
        other_notices = owner_client.get(
            f"/api/cases/messages/threads/{other_thread}/attachment-notices",
            params=_body(case, other_thread),
        )
        assert other_notices.status_code == 200, other_notices.text
        assert stored["attachment_id"] not in other_notices.text
        foreign_notices = stranger_client.get(
            f"/api/cases/messages/threads/{foreign_thread}/attachment-notices",
            params=_body(foreign, foreign_thread),
        )
        assert foreign_notices.status_code == 200, foreign_notices.text
        assert stored["attachment_id"] not in foreign_notices.text
        assert case["tenant_id"] not in foreign_notices.text
        assert FILENAME not in foreign_notices.text
        leaked = stranger_client.post(
            f"/api/cases/messages/threads/{thread_id}/attachments/{stored['attachment_id']}/download",
            headers=_csrf(stranger_token),
            json=_body(case, thread_id, key="stolen"),
        )
        assert leaked.status_code >= 400
        assert stored["attachment_id"] not in leaked.text
        assert FILENAME not in leaked.text and SECRET.decode() not in leaked.text
        guessed = stranger_client.post(
            f"/api/cases/attachments/{world.kit.added and 'cid' + '0'*24}/download",
            headers=_csrf(stranger_token),
            json={**_body(foreign, foreign_thread), "cid": next(iter(world.kit.objects))},
        )
        assert guessed.status_code == 403
        assert guessed.json()["error"] == "selector_rejected"

        world.memberships.remove(
            owner_principal_id=world.owner.principal_id,
            grant_id=membership_id,
            expected_version=membership_version,
        )
        revoked = lawyer_client.post(
            f"/api/cases/messages/threads/{thread_id}/attachments/{stored['attachment_id']}/preview",
            headers=_csrf(lawyer_token),
            json=lawyer_body,
        )
        assert revoked.status_code >= 400
        assert "content_base64" not in revoked.text
        assert FILENAME not in revoked.text

        owner_still = owner_client.post(
            f"/api/cases/messages/threads/{thread_id}/attachments/{stored['attachment_id']}/download",
            headers=_csrf(owner_token),
            json=_body(case, thread_id, key="owner-read"),
        )
        assert owner_still.status_code == 200, owner_still.text
        assert base64.b64decode(owner_still.json()["content_base64"]) == _pdf()
        assert other["case_id"] != case["case_id"]
