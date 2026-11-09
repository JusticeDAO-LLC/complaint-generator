"""Real accepted membership, recipient AEAD keys, and authenticated HTTP.

All principals/content/transport bytes are private synthetic fixtures. The Kit
byte transport is deliberately in memory; grant/session/crypto owners are real.
"""
from threading import Event, Thread
import base64

import pytest
from fastapi.testclient import TestClient

from applications.case_attachment_api import CaseAttachmentService
from applications.case_message_api import CaseMessageService
from applications.case_messages import CaseMessageStore
from integrations.private_collaboration import SharedAttachmentStore, ATTACHMENT_KIND
from integrations.private_storage import UserOwnedKeySession
from tests.test_cimp_gui_43 import (
    _world, _login, _csrf, _create_case, _invite, _thread, _body, _pdf,
    OWNER_CREDENTIAL, LAWYER_CREDENTIAL, REVISION,
)

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
TEXT = "Synthetic private recipient conversation 43-44."


def _prepared(owner, lawyer, world):
    owner_csrf, lawyer_csrf = _login(owner, OWNER_CREDENTIAL), _login(lawyer, LAWYER_CREDENTIAL)
    case = _create_case(owner, owner_csrf)
    membership, version = _invite(owner, owner_csrf, lawyer, lawyer_csrf, world, case)
    # Provision with the actual owner key session, then issue the recipient
    # grant through the authenticated public assignment API.
    world.owner_session.ensure_data_key(case["tenant_id"], case["case_id"])
    grant = owner.post(f"/api/cases/assignments/{membership}/key-grant", headers=_csrf(owner_csrf),
        json={"artifact_kind": ATTACHMENT_KIND, "artifact_revision": REVISION,
            "idempotency_key": "journey-recipient-key"})
    assert grant.status_code == 201, grant.text
    thread = _thread(owner, owner_csrf, case, "journey-thread")
    sent = owner.post(f"/api/cases/messages/threads/{thread}/messages", headers=_csrf(owner_csrf),
        json={"case_id": case["case_id"], "text": TEXT, "idempotency_key": "journey-message"})
    assert sent.status_code == 201, sent.text
    uploaded = owner.post(f"/api/cases/messages/threads/{thread}/attachments", headers=_csrf(owner_csrf),
        json=_body(case, thread, key="journey-attachment"))
    assert uploaded.status_code == 201, uploaded.text
    material = _body(case, thread, membership_grant_id=membership, membership_version=version,
        expected_membership_version=version, key_grant_id=grant.json()["key_grant_id"])
    return {"case": case, "thread": thread, "attachment": uploaded.json()["attachment_id"],
        "material": material, "lawyer_csrf": lawyer_csrf, "owner_csrf": owner_csrf}


def _download(lawyer, prepared):
    return lawyer.post(f"/api/cases/messages/threads/{prepared['thread']}/attachments/{prepared['attachment']}/download",
        headers=_csrf(prepared["lawyer_csrf"]), json=prepared["material"])


def test_real_recipient_key_opens_thread_attachment_without_unlocked_owner(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as owner, TestClient(world.app, base_url="https://testserver") as lawyer:
        prepared = _prepared(owner, lawyer, world)
        assert world.owner.principal_id != prepared["case"]["tenant_id"]
        world.owner_session.lock()
        opened = _download(lawyer, prepared)
        assert opened.status_code == 200, opened.text
        assert base64.b64decode(opened.json()["content_base64"]) == _pdf()
        world.lawyer_session.lock()
        refused = _download(lawyer, prepared)
        assert refused.status_code >= 400 and "content_base64" not in refused.text


def test_cold_recipient_and_services_preserve_durable_thread_attachment_binding(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as owner, TestClient(world.app, base_url="https://testserver") as lawyer:
        prepared = _prepared(owner, lawyer, world)
        world.owner_session.lock()
        cold_recipient = UserOwnedKeySession(tmp_path / "lawyer-keys")
        cold_recipient.unlock_passphrase("lawyer-passphrase")
        old_messages = world.messages.store
        messages = CaseMessageStore(old_messages.root, key=old_messages._key, key_id=old_messages._key_id,
            principals=old_messages._principals, cases=old_messages._cases,
            memberships=old_messages._memberships, clock=old_messages._clock)
        attachments = CaseAttachmentService(SharedAttachmentStore(tmp_path / "attachments", world.grants, backend=world.kit),
            {world.owner.principal_id: world.owner_session, world.lawyer.principal_id: cold_recipient})
        attachments.bind_message_admission(messages)
        service = CaseMessageService(messages)
        service.bind_attachments(attachments)
        world.app.state.case_messages, world.app.state.case_attachments = service, attachments
        page = lawyer.get(f"/api/cases/messages/threads/{prepared['thread']}/messages", params={
            "case_id": prepared["case"]["case_id"], "membership_grant_id": prepared["material"]["membership_grant_id"],
            "expected_membership_version": prepared["material"]["membership_version"]})
        assert page.status_code == 200 and page.json()["messages"][0]["text"] == TEXT, page.text
        opened = _download(lawyer, prepared)
        assert opened.status_code == 200, opened.text
        assert base64.b64decode(opened.json()["content_base64"]) == _pdf()
        notices = lawyer.get(f"/api/cases/messages/threads/{prepared['thread']}/attachment-notices", params={
            "case_id": prepared["case"]["case_id"], "membership_grant_id": prepared["material"]["membership_grant_id"],
            "expected_membership_version": prepared["material"]["membership_version"],
            "tenant_id": prepared["case"]["tenant_id"], "resource_id": prepared["case"]["resource_id"],
            "expected_revision": prepared["case"]["directory_revision"],
            "artifact_revision": prepared["material"]["artifact_revision"],
            "key_grant_id": prepared["material"]["key_grant_id"]})
        assert notices.status_code == 200, notices.text
        assert [item["attachment_id"] for item in notices.json()["notices"]] == [prepared["attachment"]]
        other_thread = _thread(owner, prepared["owner_csrf"], prepared["case"], "cold-other-thread")
        mismatch = lawyer.post(f"/api/cases/messages/threads/{other_thread}/attachments/{prepared['attachment']}/download",
            headers=_csrf(prepared["lawyer_csrf"]), json=dict(prepared["material"], thread_id=other_thread))
        assert mismatch.status_code >= 400 and "content_base64" not in mismatch.text


@pytest.mark.parametrize("invalidate", ["logout", "rotate", "membership"])
def test_actual_logout_while_message_plaintext_is_opening_cannot_publish_it(tmp_path, monkeypatch, invalidate):
    world = _world(tmp_path)
    entered, release = Event(), Event()
    with TestClient(world.app, base_url="https://testserver") as owner, TestClient(world.app, base_url="https://testserver") as lawyer:
        prepared = _prepared(owner, lawyer, world)
        world.owner_session.lock()
        actual = world.messages.store._load_message
        def opened_then_wait(*args, **kwargs):
            message = actual(*args, **kwargs)
            entered.set()
            assert release.wait(20), "Real message opening did not release."
            return message
        monkeypatch.setattr(world.messages.store, "_load_message", opened_then_wait)
        responses, errors = [], []
        def read():
            try:
                responses.append(lawyer.get(f"/api/cases/messages/threads/{prepared['thread']}/messages", params={
                    "case_id": prepared["case"]["case_id"], "membership_grant_id": prepared["material"]["membership_grant_id"],
                    "expected_membership_version": prepared["material"]["membership_version"]}))
            except BaseException as exc:
                errors.append(exc)
        worker = Thread(target=read, daemon=True)
        worker.start()
        try:
            assert entered.wait(20)
            if invalidate == "membership":
                removed = owner.post(f"/api/cases/assignments/{prepared['material']['membership_grant_id']}/remove",
                    headers=_csrf(prepared["owner_csrf"]), json={"expected_version": prepared["material"]["membership_version"]})
            else:
                removed = lawyer.post(f"/api/complaint-workspace/auth/{invalidate}", headers=_csrf(prepared["lawyer_csrf"]))
            assert removed.status_code == 200 and worker.is_alive()
        finally:
            release.set(); worker.join(20)
        assert not worker.is_alive() and not errors and len(responses) == 1
        assert responses[0].status_code >= 400 and TEXT not in responses[0].text


@pytest.mark.parametrize("operation", ["message", "attachment-binding"])
def test_revocation_after_real_encryption_prevents_new_publication(tmp_path, monkeypatch, operation):
    import applications.case_messages as owner_module
    world = _world(tmp_path)
    entered, release = Event(), Event()
    with TestClient(world.app, base_url="https://testserver") as owner, TestClient(world.app, base_url="https://testserver") as lawyer:
        prepared = _prepared(owner, lawyer, world)
        actual = owner_module.seal_private_artifact
        kind = owner_module.MESSAGE_KIND if operation == "message" else owner_module.ATTACHMENT_BINDING_KIND
        def encrypted_then_wait(*args, **kwargs):
            ciphertext = actual(*args, **kwargs)
            if kwargs["binding"].artifact_kind == kind:
                entered.set()
                assert release.wait(20), "Actual encryption was not released."
            return ciphertext
        monkeypatch.setattr(owner_module, "seal_private_artifact", encrypted_then_wait)
        before = {str(p.relative_to(world.messages.store.root)): p.read_bytes()
            for p in world.messages.store.root.rglob("*") if p.is_file()}
        responses, errors = [], []
        def write():
            try:
                if operation == "message":
                    responses.append(lawyer.post(f"/api/cases/messages/threads/{prepared['thread']}/messages",
                        headers=_csrf(prepared["lawyer_csrf"]), json={"case_id": prepared["case"]["case_id"],
                            "membership_grant_id": prepared["material"]["membership_grant_id"],
                            "expected_membership_version": prepared["material"]["membership_version"],
                            "text": "must-not-publish", "idempotency_key": "late-message"}))
                else:
                    responses.append(lawyer.post(f"/api/cases/messages/threads/{prepared['thread']}/attachments",
                        headers=_csrf(prepared["lawyer_csrf"]), json=dict(prepared["material"],
                            content_base64=base64.b64encode(_pdf()+b"\nnew").decode(), idempotency_key="late-binding")))
            except BaseException as exc:
                errors.append(exc)
        worker = Thread(target=write, daemon=True); worker.start()
        try:
            assert entered.wait(20)
            if operation == "message":
                invalidated = lawyer.post("/api/complaint-workspace/auth/logout", headers=_csrf(prepared["lawyer_csrf"]))
                assert invalidated.status_code == 200
            else:
                world.lawyer_session.lock()
            assert worker.is_alive(), "Revocation must precede publication reproof."
        finally:
            release.set(); worker.join(20)
        assert not worker.is_alive() and not errors and len(responses) == 1
        assert responses[0].status_code >= 400, responses[0].text
        after = {str(p.relative_to(world.messages.store.root)): p.read_bytes()
            for p in world.messages.store.root.rglob("*") if p.is_file()}
        # Recipient ciphertext may already be an unreachable artifact in the
        # separate attachment owner; no new message/thread binding is admitted.
        assert after == before


def test_publication_scope_cannot_be_reused_from_a_copied_expired_context(tmp_path):
    from contextvars import copy_context
    from applications.case_messages import CaseMessageError
    world = _world(tmp_path)
    with world.messages.store.publication_scope(lambda: None):
        captured = copy_context()
    with pytest.raises(CaseMessageError, match="message_unavailable"):
        captured.run(world.messages.store._verify_publication)
