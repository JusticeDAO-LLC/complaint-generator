"""Actual cookie/case/key/consent regressions for legal research publication.

All cases and law bytes are authored fixtures. Acquisition is the production
Mediator and Data311 local adapter; no provider or external network is used.
The late-result barrier delegates the genuine adapter unchanged and pauses
only delivery to the mounted handler, without fabricating its result.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
import json
import os
import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.browser_sessions import BrowserSessionConfiguration, BrowserSessionService, PrincipalStoreCredentialAdapter
from applications.case_access import CaseActionAuthorizer
from applications.case_consent_api import CaseConsentService
from applications.case_directory import CaseDirectory
from applications.case_routes import CaseHandlerRegistry, compose_case_routes
from applications.complaint_workspace import ComplaintWorkspaceService
from applications.principal_store import PrincipalStore
from tests.test_gui25_26_canonical_contract import _real_source
from tests.test_cimp_mgnd_17 import _rows_for
from tests.mgnd_fixtures import meaningful_cases

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _world(tmp_path):
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principals")
    owner = principals.register_from_request({})
    stranger = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    cases = CaseDirectory(tmp_path / "cases", key=os.urandom(32), key_id="cases")
    case = cases.create_case(actor_principal_id=owner.principal_id)
    assert owner.principal_id != case.tenant_id
    authorizer = CaseActionAuthorizer(principals, cases)
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {"synthetic-owner-credential": owner.principal_id,
            "synthetic-stranger-credential": stranger.principal_id, "synthetic-lawyer-credential": lawyer.principal_id}),
        signing_key=os.urandom(32), ttl_seconds=300))
    service_root = tmp_path / "workspace"
    service = ComplaintWorkspaceService(root_dir=service_root)
    assert service.initialize_private_keys(protection="passphrase", passphrase="synthetic-password")["unlocked"] is True
    service.ensure_private_case_key(case.tenant_id, case.case_id)
    mediator, case_file, _authority, _acquisition, _candidate = _real_source(tmp_path / "mediator")
    consent = CaseConsentService(tmp_path / "consent", cases=cases, key=os.urandom(32),
        key_id="consent", clock=lambda: int(time.time()))
    def app_for(selected_mediator, selected_service):
        handlers = CaseHandlerRegistry()
        handlers.bind(case, mediator=selected_mediator, workspace_service=selected_service)
        app = FastAPI()
        compose_case_routes(app, authorizer=authorizer, browser_sessions=sessions, case_handlers=handlers,
            case_consent=consent, include_review=False, include_document=False)
        return app
    return SimpleNamespace(case=case, owner=owner, stranger=stranger, lawyer=lawyer, cases=cases, authorizer=authorizer, mediator=mediator, service=service, service_root=service_root,
        consent=consent, app_for=app_for, app=app_for(mediator, service), root=tmp_path)


def _login(client):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": "synthetic-owner-credential"})
    assert response.status_code == 200
    return response.json()["csrf_token"]


def _headers(world, csrf=None):
    case = world.case
    headers = {"x-tenant-id": case.tenant_id, "x-case-id": case.case_id,
        "x-resource-id": case.resource_id, "x-expected-revision": str(case.revision)}
    if csrf:
        headers["x-csrf-token"] = csrf
    return headers


def _start_case(client, world, csrf):
    authored = next(case for case in meaningful_cases() if case.label == "baseline")
    narrative = "My employer fired me on 2024-03-04 after I submitted a safety report. " + authored.narrative.text + " Under Oregon law. Applicable law date: 2024-03-15."
    response = client.post("/api/complaint-workspace/intake-chat", headers=_headers(world, csrf),
        json={"message": narrative, "question_id": "original_complaint", "interview_action": "start"})
    assert response.status_code == 200
    assert response.json()["session"]["user_id"] == world.case.tenant_id
    assert response.json()["interview"]["session_revision"] >= 1
    from integrations.private_storage import ENVELOPE_MAGIC
    files = [path for path in world.service._session_dir.rglob("*") if path.is_file()]
    sealed = [path for path in files if path.read_bytes().startswith(ENVELOPE_MAGIC)]
    assert sealed and all(narrative.encode() not in path.read_bytes() for path in sealed)
    current = client.get(f"/api/legal-context/{world.case.case_id}", headers=_headers(world))
    assert current.status_code == 200
    selected = client.post(f"/api/legal-context/{world.case.case_id}", headers=_headers(world, csrf),
        json={"expected_context_revision": current.json()["context_revision"], "jurisdiction": "Oregon",
            "forum": "synthetic-state-trial-forum", "applicability": "explicit",
            "applicable_law_date": "2024-03-15", "event_date": authored.narrative.event_date})
    assert selected.status_code == 200
    assert selected.json()["changed"] is True


def _choose(client, world, csrf):
    response = client.post(f"/api/cases/{world.case.case_id}/processing-consent",
        headers={"x-csrf-token": csrf}, json={"purpose": "citation_acquisition", "mode": "local_private", "expected_generation": 0})
    assert response.status_code == 200
    return response.json()["generation"]


def _body(generation):
    authored = next(case for case in meaningful_cases() if case.label == "baseline")
    return {"purpose": "citation_acquisition", "query": "termination statute", "max_results": 2,
        "deadline_seconds": 2.0, "max_bytes": 4096, "retrieval_mode": "cache",
        "expected_consent_generation": generation, "operation_id": "synthetic-private-source-query",
        "local_rows": _rows_for(authored)}


def _acquire(client, world, csrf, generation):
    response = client.post(f"/api/legal-research/{world.case.case_id}",
        headers=_headers(world, csrf), json=_body(generation))
    assert response.status_code == 200
    assert response.json()["candidate_count"] > 0, {key: response.json().get(key) for key in ("status", "error_code", "candidate_count", "research_gap_count", "context_required")}
    assert response.json()["admitted_law"] is False and response.json()["proof"] is False
    return response.json()


def test_warm_legal_source_cache_cannot_bypass_actual_private_key_lock(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _login(client)
        _start_case(client, world, csrf)
        generation = _choose(client, world, csrf)
        _acquire(client, world, csrf, generation)
        assert world.service.lock_private_keys()["unlocked"] is False
        assert world.service.private_key_status()["unlocked"] is False
        denied = client.get(f"/api/legal-research/{world.case.case_id}", headers=_headers(world))
        assert denied.status_code in {401, 403, 409, 503}, "locked_case_cached_source_returned"


@pytest.mark.parametrize("changed_owner", ["purpose", "context"])
def test_real_acquisition_cannot_publish_after_actual_http_purpose_revision_changes(tmp_path, monkeypatch, changed_owner):
    world = _world(tmp_path)
    reached, resume = threading.Event(), threading.Event()
    from mediator.legal_authority_hooks import LegalAuthoritySearchHook
    original = LegalAuthoritySearchHook.acquire_bounded_canonical_sources
    def paused(self, *args, **kwargs):
        actual = original(self, *args, **kwargs)
        assert actual["status"] == "candidates"
        reached.set()
        assert resume.wait(20), "test_delivery_barrier_expired"
        return actual
    with TestClient(world.app, base_url="https://testserver") as client, TestClient(world.app, base_url="https://testserver") as revoker:
        csrf = _login(client)
        revoker.cookies.update(client.cookies)
        other_csrf = csrf
        _start_case(client, world, csrf)
        generation = _choose(client, world, csrf)
        monkeypatch.setattr(LegalAuthoritySearchHook, "acquire_bounded_canonical_sources", paused)
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(client.post, f"/api/legal-research/{world.case.case_id}",
                headers=_headers(world, csrf), json=_body(generation))
            try:
                assert reached.wait(20), "actual_acquisition_did_not_reach_delivery"
                if changed_owner == "purpose":
                    changed = revoker.post(f"/api/cases/{world.case.case_id}/processing-consent/revoke",
                        headers={"x-csrf-token": other_csrf}, json={"purpose": "citation_acquisition", "expected_generation": generation})
                    assert changed.status_code == 200
                    assert changed.json()["generation"] > generation
                else:
                    context = revoker.get(f"/api/legal-context/{world.case.case_id}", headers=_headers(world)).json()
                    changed = revoker.post(f"/api/legal-context/{world.case.case_id}", headers=_headers(world, other_csrf),
                        json={"expected_context_revision": context["context_revision"], "forum": "changed-owned-source-forum"})
                    assert changed.status_code == 200
            finally:
                resume.set()
            response = result.result(timeout=20)
        assert response.status_code in {401, 403, 409, 503}, "obsolete_purpose_generation_published"


def test_legal_source_receipt_survives_fresh_workspace_key_session_and_mediator(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _login(client)
        _start_case(client, world, csrf)
        generation = _choose(client, world, csrf)
        before = _acquire(client, world, csrf, generation)
    world.service.lock_private_keys()
    fresh = ComplaintWorkspaceService(root_dir=world.service_root)
    assert fresh.unlock_private_keys(passphrase="synthetic-password")["unlocked"] is True
    mediator, _case, _authority, _acquisition, _candidate = _real_source(tmp_path / "cold-mediator")
    with TestClient(world.app_for(mediator, fresh), base_url="https://testserver") as client:
        _login(client)
        reopened = client.get(f"/api/legal-research/{world.case.case_id}", headers=_headers(world))
        assert reopened.status_code == 200
        assert reopened.json()["candidate_count"] == before["candidate_count"], "acknowledged_legal_sources_lost_on_reopen"
        assert reopened.json()["source_version_receipts"] == before["source_version_receipts"]


def test_exact_review_admits_real_source_without_inventing_applicability_and_cold_reads_it(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _login(client)
        _start_case(client, world, csrf)
        generation = _choose(client, world, csrf)
        acquired = _acquire(client, world, csrf, generation)
        source = next(row for row in acquired["source_version_receipts"] if row["kind"] == "candidate")
        body = {"decision": "admit", "source_passage": source["source_passage"],
            "authority_identity": source["authority_identity"], "jurisdiction": source["jurisdiction"],
            "effective_date": source["effective_date"], "version": source["version"],
            "content_hash": source["content_hash"], "applicability": source["stated_applicability"],
            "treatment_state": source["treatment_state"], "exceptions": source["exceptions"],
            "operation_id": "synthetic-exact-source-review"}
        response = client.post(f"/api/legal-research/{world.case.case_id}/admissions",
            headers=_headers(world, csrf), json=body)
        assert response.status_code == 200, response.json().get("error")
        record = response.json()
        assert record["source_status"] == "source_admitted", {key: record.get(key) for key in ("reason", "source_status", "attribution")}
        assert record["source_admission"]["status"] == "admitted"
        assert record["source_admission"]["stored_record_ids"]
        assert record["source_admission"]["record"]["content"] == source["source_passage"]
        assert record["admitted_law"] is False and record["proof"] is False and record["support_eligible"] is False
        assert record["applicability"] == "unknown" and record["treatment_state"] == "unknown"
        assert record["attribution"]["actor_principal_id"] == world.owner.principal_id
        assert record["attribution"]["canonical_owner_principal_id"] == world.case.tenant_id
        replay = client.post(f"/api/legal-research/{world.case.case_id}/admissions", headers=_headers(world, csrf), json=body)
        assert replay.status_code == 200 and replay.json()["replayed"] is True
        assert replay.json()["private_revision"] == record["private_revision"]
    world.service.lock_private_keys()
    fresh = ComplaintWorkspaceService(root_dir=world.service_root)
    assert fresh.unlock_private_keys(passphrase="synthetic-password")["unlocked"] is True
    mediator, _case, _authority, _acquisition, _candidate = _real_source(tmp_path / "review-cold-mediator")
    with TestClient(world.app_for(mediator, fresh), base_url="https://testserver") as client:
        _login(client)
        response = client.get(f"/api/legal-research/{world.case.case_id}/admissions", headers=_headers(world))
        assert response.status_code == 200
        assert response.json()["source_admitted_count"] == 1
        assert response.json()["admitted_count"] == 0
        assert response.json()["admissions"][0]["source_admission"] == record["source_admission"]


def test_legacy_research_command_replays_owned_canonical_sources_and_honors_stale_revision(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _login(client)
        _start_case(client, world, csrf)
        generation = _choose(client, world, csrf)
        acquired = _acquire(client, world, csrf, generation)
        session = client.get("/api/complaint-workspace/session", headers=_headers(world)).json()["session"]
        shared = session["shared_interview"]
        result = client.post("/api/complaint-workspace/intake-chat", headers=_headers(world, csrf), json={"message": "/research"})
        assert result.status_code == 200
        research = result.json()["legal_research"]
        assert research["candidate_count"] == acquired["candidate_count"]
        assert research["source_version_receipts"] == acquired["source_version_receipts"]
        assert research["replayed"] is True and research["admitted_law"] is False
        assert result.json()["stored_as_answer"] is False
        assert result.json()["session"]["shared_interview"]["answered_inquiries"] == shared["answered_inquiries"]
        head = (world.service.joined_revision_repository(world.case.tenant_id, world.case.case_id) / "head.cgpe").read_bytes()
        stale = client.post("/api/complaint-workspace/intake-chat", headers=_headers(world, csrf),
            json={"message": "/research", "expected_session_revision": 0})
        assert stale.status_code in {200, 409}
        assert stale.json()["legal_research"]["error_code"] == "stale_research"
        assert (world.service.joined_revision_repository(world.case.tenant_id, world.case.case_id) / "head.cgpe").read_bytes() == head
        for value in (True, "0", 0.0):
            invalid = client.post("/api/complaint-workspace/intake-chat", headers=_headers(world, csrf),
                json={"message": "/research", "expected_session_revision": value})
            assert invalid.status_code == 422
        revoked = client.post(f"/api/cases/{world.case.case_id}/processing-consent/revoke",
            headers={"x-csrf-token": csrf}, json={"purpose": "citation_acquisition", "expected_generation": generation})
        assert revoked.status_code == 200
        denied = client.post("/api/complaint-workspace/intake-chat", headers=_headers(world, csrf), json={"message": "/research"})
        assert denied.status_code == 200
        assert denied.json()["legal_research"].get("candidate_count", 0) == 0


@pytest.mark.parametrize("boundary", ["logout", "key_lock", "consent"])
def test_real_source_publication_rechecks_authority_after_head_temp_fsync(tmp_path, monkeypatch, boundary):
    from integrations import private_storage
    world = _world(tmp_path)
    reached, resume = threading.Event(), threading.Event()
    original = private_storage._fsync_file
    with TestClient(world.app, base_url="https://testserver") as client, TestClient(world.app, base_url="https://testserver") as other:
        csrf = _login(client)
        other.cookies.update(client.cookies)
        _start_case(client, world, csrf)
        generation = _choose(client, world, csrf)
        repository = world.service.joined_revision_repository(world.case.tenant_id, world.case.case_id)
        before = (repository / "head.cgpe").read_bytes()
        def pause_actual_head(fd, operation):
            original(fd, operation)
            staged = Path(os.readlink(f"/proc/self/fd/{fd}"))
            if (staged.parent == repository and staged.read_bytes().startswith(private_storage._HEAD_RECORD_MAGIC)
                    and not reached.is_set()):
                reached.set()
                assert resume.wait(20), "publication_barrier_expired"
        monkeypatch.setattr(private_storage, "_fsync_file", pause_actual_head)
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(client.post, f"/api/legal-research/{world.case.case_id}", headers=_headers(world, csrf), json=_body(generation))
            try:
                assert reached.wait(25), "actual_head_temp_not_produced"
                if boundary == "logout":
                    assert other.post("/api/complaint-workspace/auth/logout", headers={"x-csrf-token": csrf}).status_code == 200
                elif boundary == "key_lock":
                    world.service.lock_private_keys()
                elif boundary == "consent":
                    assert other.post(f"/api/cases/{world.case.case_id}/processing-consent/revoke", headers={"x-csrf-token": csrf},
                        json={"purpose": "citation_acquisition", "expected_generation": generation}).status_code == 200
                else:
                    context = other.get(f"/api/legal-context/{world.case.case_id}", headers=_headers(world)).json()
                    changed = other.post(f"/api/legal-context/{world.case.case_id}", headers=_headers(world, csrf),
                        json={"expected_context_revision": context["context_revision"], "forum": "changed-synthetic-forum"})
                    assert changed.status_code == 200
                    before = (repository / "head.cgpe").read_bytes()
            finally:
                resume.set()
            response = result.result(timeout=25)
        assert response.status_code in {401, 403, 409, 503}
        assert (repository / "head.cgpe").read_bytes() == before
        decisions = [json.loads(line) for line in (repository / "wal" / "transaction-decisions.jsonl").read_text().splitlines()]
        assert any(row["kind"] == "abort" for row in decisions)
        assert list(repository.glob(".*.tmp")) == []
        if boundary == "key_lock":
            world.service.unlock_private_keys(passphrase="synthetic-password")
        world.service.recover_joined_intake_revision(world.case.tenant_id, case_id=world.case.case_id)
        assert (repository / "head.cgpe").read_bytes() == before


def test_automatic_private_artifact_facade_uses_live_exact_owner_not_actor_as_aad(tmp_path):
    from applications.complaint_workspace import WorkspaceAccess, WorkspaceAuthorizationDenied, workspace_access_scope
    from applications.workspace_case_authority import issue_workspace_case_authority, workspace_case_authority_scope
    from integrations.private_storage import PrivateArtifactBinding, ENVELOPE_MAGIC
    from tests.test_cimp_gui_14 import _composed_case_world
    world = _composed_case_world(tmp_path)
    case, service = world.case, world.services[world.case.case_id]
    issued = world.sessions.login({"credential": "synthetic-owner-credential"})
    decision = world.authorizer.authorize(boundary="http", actor_principal_id=world.owner.principal_id,
        tenant_id=case.tenant_id, case_id=case.case_id, resource_id=case.resource_id, action="case.update", expected_revision=case.revision)
    authority = issue_workspace_case_authority(authorizer=world.authorizer, sessions=world.sessions,
        token=issued.token, decision=decision, registry=world.handlers)
    binding = PrivateArtifactBinding(tenant_id=case.tenant_id, case_id=case.case_id, principal_id=case.tenant_id,
        artifact_kind="annotation", revision="annotation-1")
    with workspace_case_authority_scope(authority), workspace_access_scope(WorkspaceAccess.authenticated(world.owner.principal_id, case.case_id)):
        assert world.owner.principal_id != case.tenant_id
        result = service.persist_private_case_materials(world.owner.principal_id, {"annotation": b"synthetic-private-source-association"}, case_id=case.case_id)
        assert result["written"] is True and result["plaintext_disk"] is False
        blob = service._private_local_backend().cat(result["artifacts"]["annotation"]["cid"])
        assert blob.startswith(ENVELOPE_MAGIC) and b"synthetic-private-source-association" not in blob
        provider = service.private_key_provider()
        assert len(provider.resolve(binding)[1]) == 32
        with workspace_access_scope(WorkspaceAccess.authenticated(world.owner.principal_id, world.second.case_id)):
            with pytest.raises(WorkspaceAuthorizationDenied):
                provider.resolve(binding)
        with workspace_access_scope(WorkspaceAccess.authenticated(world.stranger.principal_id, case.case_id)):
            with pytest.raises(WorkspaceAuthorizationDenied):
                service.persist_private_case_materials(world.stranger.principal_id, {"annotation": b"denied"}, case_id=case.case_id)
        with workspace_access_scope(WorkspaceAccess.authenticated(world.lawyer.principal_id, case.case_id)):
            with pytest.raises(WorkspaceAuthorizationDenied):
                provider.resolve(binding)
        with ThreadPoolExecutor(max_workers=1) as operator:
            operator.submit(service.lock_private_keys).result(timeout=10)
        with pytest.raises(Exception) as locked:
            provider.resolve(binding)
        assert getattr(locked.value, "code", "") == "unlock_needed"
        with ThreadPoolExecutor(max_workers=1) as operator:
            operator.submit(service.unlock_private_keys, passphrase="synthetic-gui-14-passphrase").result(timeout=10)
        world.sessions.logout(issued.token, csrf_token=issued.csrf_token)
        with pytest.raises(WorkspaceAuthorizationDenied):
            provider.resolve(binding)
    with pytest.raises(WorkspaceAuthorizationDenied):
        provider.resolve(binding)


def test_actual_owner_refuses_stale_caller_preconditions_and_unavailable_live_corpus(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _login(client)
        _start_case(client, world, csrf)
        generation = _choose(client, world, csrf)
        repository = world.service.joined_revision_repository(world.case.tenant_id, world.case.case_id)
        before = (repository / "head.cgpe").read_bytes()
        for changed in ({"expected_private_revision": "0"}, {"expected_session_revision": 0},
                        {"expected_source_scope_sha256": "0" * 64}):
            result = client.post(f"/api/legal-research/{world.case.case_id}", headers=_headers(world, csrf),
                json={**_body(generation), **changed})
            assert result.status_code == 409
            assert (repository / "head.cgpe").read_bytes() == before
        live = client.post(f"/api/legal-research/{world.case.case_id}", headers=_headers(world, csrf),
            json={**_body(generation), "retrieval_mode": "live"})
        assert live.status_code == 503 and live.json()["error"] == "legal_corpus_unavailable"
        assert (repository / "head.cgpe").read_bytes() == before
        assert client.get(f"/api/legal-research/{world.case.case_id}", headers=_headers(world)).json()["candidate_count"] == 0
