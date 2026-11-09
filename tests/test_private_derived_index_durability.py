"""Encrypted derived references survive a genuinely fresh authorized owner."""
from contextlib import contextmanager
import base64
import hashlib
import os

import pytest
from fastapi.testclient import TestClient

from applications.browser_sessions import SESSION_COOKIE
from applications.complaint_workspace import WorkspaceAccess, workspace_access_scope
from applications.workspace_case_authority import issue_workspace_case_authority, workspace_case_authority_scope
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import _composed_login
from integrations.private_storage import InjectedCaseKeyProvider
from mediator.evidence_hooks import EvidenceStateHook, PrivateDerivedIndex
from tests.test_cimp_mgnd_32 import _context, _MemoryBackend, _Mediator, _OWNER, _provider


pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

TEXT = "Synthetic private authority requires an employer to provide written notice before denial."
TITLE = "Synthetic private owner authority"


@contextmanager
def _issued_owner(world):
    with TestClient(world.app, base_url="https://testserver") as client:
        _composed_login(client)
        case = world.case
        decision = world.authorizer.authorize(boundary="http", actor_principal_id=world.owner.principal_id,
            tenant_id=case.tenant_id, case_id=case.case_id, resource_id=case.resource_id,
            action="case.update", expected_revision=case.revision)
        authority = issue_workspace_case_authority(authorizer=world.authorizer, sessions=world.sessions,
            token=client.cookies.get(SESSION_COOKIE), decision=decision, registry=world.app.state.case_handlers)
        with workspace_case_authority_scope(authority), workspace_access_scope(
                WorkspaceAccess.authenticated(world.owner.principal_id, case_id=case.case_id)):
            yield


def test_stored_authority_reopens_with_fresh_service_keys_and_mediator(tmp_path):
    world = owner_lawyer_journey_world(tmp_path / "world")
    with _issued_owner(world):
        mediator = world.service._mediator_for_shared_interview(world.case.tenant_id, world.case.case_id, cache=False)
        source = {"type": "statute", "source": "authored-private-fixture", "title": TITLE,
            "citation": "Synthetic private notice rule", "content": TEXT, "jurisdiction": "OR",
            "metadata": {"source_text": TEXT, "source_hash": hashlib.sha256(TEXT.encode()).hexdigest(),
                "authority_id": "synthetic-private-durable-rule", "authority_version": "synthetic-2024",
                "effective_date": "2024-01-01", "as_of_date": "2024-06-01"}}
        assert mediator.legal_authority_storage.add_authority(source, world.case.tenant_id, claim_type="synthetic") > 0
        stored = mediator.legal_authority_storage.get_all_authorities(world.case.tenant_id)[0]
        assert stored["content"].startswith("cgidx:")
        assert mediator._reveal_stored_authority_record(stored)["content"] == TEXT

    # Reopen disk-backed domain stores and wrapped key session; copy no index,
    # mediator, decrypted source or rendered projection into the fresh service.
    reopened = owner_lawyer_journey_world(world.root, previous=world)
    assert reopened.service is not world.service and reopened.owner_keys is not world.owner_keys
    with _issued_owner(reopened):
        fresh = reopened.service._mediator_for_shared_interview(world.case.tenant_id, world.case.case_id, cache=False)
        assert fresh.legal_authority_storage._derived().entries == {}
        row = fresh.legal_authority_storage.get_all_authorities(world.case.tenant_id)[0]
        revealed = fresh._reveal_stored_authority_record(row)
        assert revealed.get("source_unreadable") is not True
        assert revealed["content"] == TEXT
        assert revealed["title"] == TITLE
        assert revealed["metadata"]["source_text"] == TEXT


def _fresh_index(context):
    index = PrivateDerivedIndex()
    index.bind(context)
    assert index.entries == {}
    return index


def test_sql_reference_reopens_without_cache_and_new_write_preserves_both_revisions(tmp_path):
    backend = _MemoryBackend()
    context = _context("durable-case", backend, _provider("durable-case", os.urandom(32), "durable-key"), mode="durable")
    path = tmp_path / "evidence.duckdb"
    hook = EvidenceStateHook(_Mediator(), db_path=str(path))
    hook.bind_private_derived_index(context)
    saved = hook.commit_private_derived(case_id="durable-case", kind="private-preview", text=TEXT)
    assert saved["status"] == "available" and saved["row_persisted"] is True
    assert saved["token"].startswith("cgidx:ref:v1:")
    original = dict(hook._derived().entries[saved["token"]])
    blob = path.read_bytes()
    for private in (TEXT, original["cid"], original["revision"]):
        assert private.encode() not in blob
    reference = base64.urlsafe_b64decode(saved["token"].split(":", 3)[3])
    for private in (TEXT, original["cid"], original["revision"], original["kind"], "durable-case", _OWNER):
        assert private.encode() not in reference

    import duckdb
    with duckdb.connect(str(path)) as db:
        persisted = db.execute("SELECT token FROM private_derived_index").fetchone()[0]
    fresh = EvidenceStateHook(_Mediator(), db_path=str(path))
    fresh.bind_private_derived_index(context)
    assert fresh._derived().entries == {}
    assert fresh.read_private_derived(persisted)["text"] == TEXT
    second = fresh.commit_private_derived(case_id="durable-case", kind="private-preview", text=TEXT + " Revised.")
    assert second["status"] == "available" and second["token"] != persisted
    latest = fresh._derived().entries[second["token"]]
    assert latest["revision"] != original["revision"]
    cold = _fresh_index(context)
    assert cold.reveal(persisted)["text"] == TEXT
    assert cold.reveal(second["token"])["text"] == TEXT + " Revised."
    assert all(entry["text"] is None for entry in cold.entries.values())


@pytest.mark.parametrize("changed", ["tenant", "case", "principal"])
def test_reference_cannot_be_rebound_even_with_same_key_material(changed):
    key = os.urandom(32)
    backend = _MemoryBackend()
    context = _context("right-case", backend, _provider("right-case", key, "binding-key"), mode="durable")
    token = _fresh_index(context).contain(TEXT, kind="private-authority")
    wrong = dict(context)
    if changed == "tenant":
        wrong["tenant_id"] = "other-tenant"
    elif changed == "case":
        wrong["case_id"] = "other-case"
    else:
        wrong["principal_id"] = "other-principal"
    wrong["access"] = WorkspaceAccess.trusted_local(wrong["principal_id"], wrong["case_id"])
    wrong["key_provider"] = InjectedCaseKeyProvider({(wrong["tenant_id"], wrong["case_id"]): ("binding-key", key)})
    denied = _fresh_index(wrong).reveal(token)
    assert denied["status"] == "unavailable" and denied["code"] == "authentication_failed"
    assert denied["plaintext_fallback"] is False and "text" not in denied


@pytest.mark.parametrize("corruption", ["descriptor", "content", "revision", "malformed", "oversized", "backend_down"])
def test_authenticated_reference_and_content_fail_closed(corruption):
    backend = _MemoryBackend()
    context = _context("bound-case", backend, _provider("bound-case", os.urandom(32), "integrity-key"), mode="durable")
    writer = _fresh_index(context)
    token = writer.contain(TEXT, kind="private-authority")
    entry = writer.entries[token]
    if corruption == "descriptor":
        raw = bytearray(base64.urlsafe_b64decode(token.split(":", 3)[3]))
        raw[-1] ^= 1
        token = "cgidx:ref:v1:" + base64.urlsafe_b64encode(raw).decode("ascii")
    elif corruption == "content":
        blob = bytearray(backend.blobs[entry["cid"]]); blob[-1] ^= 1
        backend.blobs[entry["cid"]] = bytes(blob)
    elif corruption == "revision":
        # A trusted-writer fault must not permit an old/wrong content revision.
        token = writer._seal_durable_reference({**entry, "revision": "stale-index-revision"})
    elif corruption == "malformed":
        token = "cgidx:ref:v1:!not-a-reference!"
    elif corruption == "oversized":
        token = "cgidx:ref:v1:" + "A" * 16385
    else:
        backend.fail = True
    denied = _fresh_index(context).reveal(token)
    assert denied["status"] == "unavailable"
    assert denied["plaintext_fallback"] is False and "text" not in denied


def test_retained_reference_provider_observes_real_key_lock_and_unlock(tmp_path):
    from applications.complaint_workspace import ComplaintWorkspaceService
    from tests.test_cimp_gui_14 import PASSPHRASE
    service = ComplaintWorkspaceService(tmp_path / "workspace")
    service.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
    service.ensure_private_case_key(_OWNER, "lock-case")
    context = service._private_artifact_context(_OWNER, "lock-case")
    context.update(index_mode="durable", backend=service._private_local_backend(), backend_name="local_cache")
    token = _fresh_index(context).contain(TEXT, kind="private-authority")
    fresh = _fresh_index(context)
    assert fresh.reveal(token)["text"] == TEXT
    service.lock_private_keys()
    denied = fresh.reveal(token)
    assert denied["status"] == "unavailable" and "text" not in denied
    assert denied["plaintext_fallback"] is False
    assert service.unlock_private_keys(passphrase=PASSPHRASE)["unlocked"] is True
    assert fresh.reveal(token)["text"] == TEXT


def test_historical_counter_and_ephemeral_tokens_never_guess_a_cold_mapping():
    backend = _MemoryBackend()
    context = _context("legacy-case", backend, _provider("legacy-case", os.urandom(32), "legacy-key"), mode="durable")
    writer = _fresh_index(context)
    token = writer.contain(TEXT, kind="private-authority")
    writer.entries["cgidx:cid:1"] = writer.entries[token]
    assert writer.reveal("cgidx:cid:1")["text"] == TEXT
    assert _fresh_index(context).reveal("cgidx:cid:1")["status"] == "unavailable"
    ephemeral = {**context, "index_mode": "ephemeral"}
    token = _fresh_index(ephemeral).contain(TEXT, kind="private-authority")
    assert _fresh_index(ephemeral).reveal(token)["status"] == "unavailable"

