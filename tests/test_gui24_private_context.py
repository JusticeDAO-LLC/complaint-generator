"""Actual encrypted owner HTTP and Chromium legal-context behavior.

Synthetic cases only; the browser uses the qualified pipe-to-ASGI transport.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from applications.case_routes import CaseHandlerRegistry, compose_case_routes
from applications.complaint_workspace import ComplaintWorkspaceService
from tests.test_cimp_gui_14 import (NARRATIVE, ANSWER, PASSPHRASE, _composed_case_world,
    _composed_ciphertext_snapshot, _composed_headers, _composed_login)
from tests.test_cimp_gui_15 import _page
from tests.test_cimp_gui_33 import _consent_login


pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _start(client, case):
    csrf = _composed_login(client)
    started = client.post("/api/complaint-workspace/intake-chat", headers=_composed_headers(case, csrf),
        json={"message": NARRATIVE, "interview_action": "start"})
    assert started.status_code == 200, started.text
    return csrf


def test_real_encrypted_owner_can_read_explicit_unknown_legal_context_without_writes(tmp_path):
    world = _composed_case_world(tmp_path)
    assert world.case.tenant_id != world.owner.principal_id
    with TestClient(world.app, base_url="https://testserver") as client:
        _start(client, world.case)
        before = _composed_ciphertext_snapshot(world.services[world.case.case_id])
        response = client.get(f"/api/legal-context/{world.case.case_id}", headers=_composed_headers(world.case))
        assert response.status_code == 200, response.text
        assert response.json()["case_id"] == world.case.case_id
        assert response.json()["governing_law_defaulted"] is False
        assert response.json()["jurisdiction"] == "unknown"
        assert _composed_ciphertext_snapshot(world.services[world.case.case_id]) == before


def test_cached_case_file_cannot_bypass_actual_workspace_key_lock(tmp_path):
    world = _composed_case_world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        _start(client, world.case)
        saved = client.get("/api/complaint-workspace/session", headers=_composed_headers(world.case))
        case_file = deepcopy(saved.json()["session"]["shared_interview"]["intake_case_file"])
    registry = CaseHandlerRegistry()
    service = world.services[world.case.case_id]
    registry.bind(world.case, mediator=SimpleNamespace(intake_case_file=case_file), workspace_service=service)
    app = FastAPI()
    compose_case_routes(app, authorizer=world.authorizer, browser_sessions=world.sessions,
        case_handlers=registry, include_review=False, include_document=False)
    with TestClient(app, base_url="https://testserver") as client:
        _composed_login(client)
        path = f"/api/legal-context/{world.case.case_id}"
        assert client.get(path, headers=_composed_headers(world.case)).status_code == 200
        service.lock_private_keys()
        before = _composed_ciphertext_snapshot(service)
        response = client.get(path, headers=_composed_headers(world.case))
        assert response.status_code == 503, response.text
        assert response.json()["error"] == "unlock_needed"
        assert _composed_ciphertext_snapshot(service) == before


def test_context_update_is_encrypted_cas_and_preserves_actual_workflow_facts(tmp_path):
    world = _composed_case_world(tmp_path)
    service = world.services[world.case.case_id]
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _start(client, world.case)
        headers = _composed_headers(world.case)
        path = f"/api/legal-context/{world.case.case_id}"
        saved = client.get("/api/complaint-workspace/session", headers=headers).json()["session"]
        before = deepcopy(saved["shared_interview"])
        updated = client.post(path, headers=_composed_headers(world.case, csrf), json={
            "expected_context_revision": 0, "applicability": "explicit", "jurisdiction": "OR",
            "forum": "Synthetic private forum", "applicable_law_date": "2024-03-04"})
        assert updated.status_code == 200, updated.text
        assert updated.json()["jurisdiction"] == "OR"
        assert updated.json()["context_revision"] == 1
        assert updated.json()["prior_versions"][0]["context_revision"] == 0
        persisted = client.get("/api/complaint-workspace/session", headers=headers).json()["session"]
        shared = persisted["shared_interview"]
        assert shared["knowledge_graph"] == before["knowledge_graph"]
        assert shared["pending_inquiry"] == before["pending_inquiry"]
        assert shared["answered_inquiries"] == before["answered_inquiries"]
        assert shared["narrative_extraction_count"] == before["narrative_extraction_count"]
        assert shared["session_revision"] == before["session_revision"] + 1
        assert int(persisted["private_revision"]) == int(saved["private_revision"]) + 1
        ciphertext = _composed_ciphertext_snapshot(service)
        stale = client.post(path, headers=_composed_headers(world.case, csrf), json={
            "expected_context_revision": 0, "jurisdiction": "CA"})
        assert stale.status_code == 409
        assert _composed_ciphertext_snapshot(service) == ciphertext
        reread = client.get(path, headers=headers)
        assert reread.status_code == 200 and reread.json()["forum"] == "Synthetic private forum"
        assert _composed_ciphertext_snapshot(service) == ciphertext
        for file in (service._session_dir / "joined-revisions").rglob("*"):
            if file.is_file():
                assert b"Synthetic private forum" not in file.read_bytes()
        repeated = client.post(path, headers=_composed_headers(world.case, csrf), json={
            "expected_context_revision": 1, "applicability": "explicit", "jurisdiction": "OR",
            "forum": "Synthetic private forum", "applicable_law_date": "2024-03-04"})
        assert repeated.status_code == 200 and repeated.json()["changed"] is False
        assert repeated.json()["context_revision"] == 1
        assert _composed_ciphertext_snapshot(service) == ciphertext


def _app_for_workspace(world, workspace):
    registry = CaseHandlerRegistry()
    registry.bind(world.case, mediator=workspace, workspace_service=workspace)
    app = FastAPI()
    compose_case_routes(app, authorizer=world.authorizer, browser_sessions=world.sessions,
        case_handlers=registry, include_review=False, include_document=False)
    return app


def test_saved_context_cold_reopens_only_with_actual_owner_key_and_cookie(tmp_path):
    world = _composed_case_world(tmp_path)
    path = f"/api/legal-context/{world.case.case_id}"
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _start(client, world.case)
        result = client.post(path, headers=_composed_headers(world.case, csrf), json={
            "expected_context_revision": 0, "applicability": "disputed", "jurisdiction": "OR",
            "forum": "Synthetic private disputed forum"})
        assert result.status_code == 200, result.text
    reopened = ComplaintWorkspaceService(root_dir=tmp_path / "workspaces" / world.case.case_id)
    with TestClient(_app_for_workspace(world, reopened), base_url="https://testserver") as client:
        _composed_login(client)
        assert client.get(path, headers=_composed_headers(world.case)).status_code == 503
        reopened.unlock_private_keys(passphrase="synthetic-wrong-passphrase")
        assert client.get(path, headers=_composed_headers(world.case)).status_code == 503
        reopened.unlock_private_keys(passphrase=PASSPHRASE)
        before = _composed_ciphertext_snapshot(reopened)
        result = client.get(path, headers=_composed_headers(world.case))
        assert result.status_code == 200, result.text
        assert result.json()["applicability"] == "disputed"
        assert result.json()["jurisdiction"] == "unknown"
        assert result.json()["candidate_jurisdiction"] == "OR"
        assert result.json()["context_revision"] == 1 and result.json()["prior_versions"]
        assert _composed_ciphertext_snapshot(reopened) == before


@pytest.mark.parametrize("boundary,status", [("logout", 403), ("expire", 403), ("key_lock", 503)])
@pytest.mark.parametrize("stage", ["crypto", "head_temp_fsync"])
def test_real_crypto_late_refusal_terminally_aborts_and_recovery_never_publishes(
        tmp_path, monkeypatch, boundary, status, stage):
    from integrations import private_storage

    world = _composed_case_world(tmp_path)
    service = world.services[world.case.case_id]
    entered, release = Event(), Event()
    seal = private_storage._seal_role
    fsync = private_storage._fsync_file

    def pause():
        entered.set()
        if not release.wait(10):
            raise AssertionError("bounded actual publication interleaving did not release")

    def seal_then_wait(payload, **values):
        result = seal(payload, **values)
        if stage == "crypto" and values.get("kind") == "revision-manifest":
            pause()
        return result

    def head_fsync_then_wait(fd, operation):
        fsync(fd, operation)
        staged = Path(os.readlink(f"/proc/self/fd/{fd}"))
        if (stage == "head_temp_fsync" and staged.parent == repository
                and staged.read_bytes().startswith(private_storage._HEAD_RECORD_MAGIC)):
            pause()

    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _start(client, world.case)
        repository = service.joined_revision_repository(world.case.tenant_id, world.case.case_id)
        head = (repository / "head.cgpe").read_bytes()
        initial_cache = dict(service._interview_mediators)
        assert initial_cache == {}
        monkeypatch.setattr(private_storage, "_seal_role", seal_then_wait)
        monkeypatch.setattr(private_storage, "_fsync_file", head_fsync_then_wait)
        results, errors = [], []

        def update():
            try:
                results.append(client.post(f"/api/legal-context/{world.case.case_id}",
                    headers=_composed_headers(world.case, csrf), json={"expected_context_revision": 0,
                        "jurisdiction": "OR", "forum": "Synthetic refused private forum"}))
            except BaseException as error:
                errors.append(error)

        worker = Thread(target=update, daemon=True)
        worker.start()
        try:
            assert entered.wait(10), "actual encrypted manifest was not produced"
            assert (repository / "head.cgpe").read_bytes() == head
            if boundary == "logout":
                assert client.post("/api/complaint-workspace/auth/logout",
                    headers={"x-csrf-token": csrf}).status_code == 200
            elif boundary == "expire":
                world.clock["now"] += 301
            else:
                service.lock_private_keys()
        finally:
            release.set()
            worker.join(10)
        assert not worker.is_alive()
        if errors:
            raise errors[0]
        assert len(results) == 1 and results[0].status_code == status, results[0].text if results else "missing result"
        assert "Synthetic refused private forum" not in results[0].text
        assert (repository / "head.cgpe").read_bytes() == head
        assert list(repository.glob(".*.tmp")) == []
        assert service._interview_mediators == initial_cache
        decisions = [json.loads(line) for line in (repository / "wal" / "transaction-decisions.jsonl").read_text().splitlines()]
        intent = [item for item in decisions if item["kind"] == "intent"][-1]
        transaction = intent["transaction_id"]
        assert any(item["kind"] == "abort" and item["transaction_id"] == transaction for item in decisions)
        assert not any(item["kind"] == "commit" and item["transaction_id"] == transaction for item in decisions)
        if boundary == "key_lock":
            service.unlock_private_keys(passphrase=PASSPHRASE)
        # Actual operator-owned WAL recovery, not a fake replay receipt.
        service.recover_joined_intake_revision(world.case.tenant_id, case_id=world.case.case_id)
        service.recover_joined_intake_revision(world.case.tenant_id, case_id=world.case.case_id)
        assert (repository / "head.cgpe").read_bytes() == head
        _composed_login(client)
        observed = client.get(f"/api/legal-context/{world.case.case_id}", headers=_composed_headers(world.case))
        assert observed.status_code == 200, observed.text
        assert observed.json()["context_revision"] == 0 and observed.json()["forum"] == "unknown"
        assert service._interview_mediators == initial_cache


def test_actual_intake_write_wins_cas_without_publishing_stale_legal_context(tmp_path, monkeypatch):
    from integrations import private_storage

    world = _composed_case_world(tmp_path)
    service = world.services[world.case.case_id]
    entered, release = Event(), Event()
    commit = private_storage.commit_private_revision

    def wait_before_legal_cas(*args, **values):
        if values.get("before_publish") is not None:
            entered.set()
            if not release.wait(10):
                raise AssertionError("bounded CAS interleaving did not release")
        return commit(*args, **values)

    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _start(client, world.case)
        saved = client.get("/api/complaint-workspace/session", headers=_composed_headers(world.case)).json()["session"]
        inquiry = saved["shared_interview"]["pending_inquiry"]
        monkeypatch.setattr(private_storage, "commit_private_revision", wait_before_legal_cas)
        results, errors = [], []
        def update():
            try:
                results.append(client.post(f"/api/legal-context/{world.case.case_id}",
                    headers=_composed_headers(world.case, csrf),
                    json={"expected_context_revision": 0, "jurisdiction": "OR"}))
            except BaseException as error:
                errors.append(error)
        worker = Thread(target=update, daemon=True)
        worker.start()
        try:
            assert entered.wait(10)
            answer = client.post("/api/complaint-workspace/intake-chat", headers=_composed_headers(world.case, csrf),
                json={"message": ANSWER, "interview_action": "answer", "question_id": inquiry["inquiry_id"],
                    "expected_question_revision": inquiry["revision"]})
            assert answer.status_code == 200, answer.text
            assert answer.json()["interview"]["session_revision"] > saved["shared_interview"]["session_revision"]
            after_answer = _composed_ciphertext_snapshot(service)
        finally:
            release.set()
            worker.join(10)
        assert not worker.is_alive()
        if errors:
            raise errors[0]
        assert len(results) == 1 and results[0].status_code == 409
        assert _composed_ciphertext_snapshot(service) == after_answer
        current = client.get(f"/api/legal-context/{world.case.case_id}", headers=_composed_headers(world.case))
        assert current.status_code == 200 and current.json()["context_revision"] == 0


@pytest.mark.parametrize("boundary,status", [("logout", 403), ("key_lock", 503)])
def test_pending_context_get_rechecks_actual_session_and_key_before_response(tmp_path, monkeypatch, boundary, status):
    from applications import legal_context_api

    world = _composed_case_world(tmp_path)
    service = world.services[world.case.case_id]
    entered, release = Event(), Event()
    project = legal_context_api.project_legal_context
    def project_and_wait(case_file):
        result = project(case_file)
        entered.set()
        if not release.wait(10):
            raise AssertionError("bounded current context read did not release")
        return result

    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _start(client, world.case)
        before = _composed_ciphertext_snapshot(service)
        monkeypatch.setattr(legal_context_api, "project_legal_context", project_and_wait)
        results, errors = [], []
        def read():
            try:
                results.append(client.get(f"/api/legal-context/{world.case.case_id}", headers=_composed_headers(world.case)))
            except BaseException as error:
                errors.append(error)
        worker = Thread(target=read, daemon=True)
        worker.start()
        try:
            assert entered.wait(10)
            if boundary == "logout":
                assert client.post("/api/complaint-workspace/auth/logout", headers={"x-csrf-token": csrf}).status_code == 200
            else:
                service.lock_private_keys()
        finally:
            release.set()
            worker.join(10)
        assert not worker.is_alive()
        if errors:
            raise errors[0]
        assert len(results) == 1 and results[0].status_code == status
        assert "context_revision" not in results[0].json()
        assert _composed_ciphertext_snapshot(service) == before


def _browser_start(page, world):
    _consent_login(page, world)
    started = page.evaluate("""async data => {
        await window.workspaceClient.bootstrapWorkspace(data.canonical);
        return await window.workspaceClient.runIntakeChatTurn(data.canonical,
            data.narrative, 'original_complaint', {interview_action:'start'});
    }""", {"canonical": world.case.tenant_id, "narrative": NARRATIVE})
    assert started["interview"]["session_revision"] >= 1
    page.fill("#legal-context-case-id", world.case.case_id)
    path = f"/api/legal-context/{world.case.case_id}"
    with page.expect_response(lambda r: r.url.endswith(path) and r.request.method == "GET") as seen:
        page.click("#legal-context-refresh")
    assert seen.value.status == 200
    page.wait_for_function("document.getElementById('legal-context-display').dataset.contextRevision !== undefined")
    return path


def _browser_save(page, path, forum):
    page.select_option("#legal-context-applicability", "explicit")
    page.fill("#legal-context-jurisdiction", "OR")
    page.fill("#legal-context-forum", forum)
    page.fill("#legal-context-applicable-law-date", "2024-03-04")
    with page.expect_response(lambda r: r.url.endswith(path) and r.request.method == "POST") as changed:
        page.click("#legal-context-save")
    assert changed.value.status == 200, changed.value.text()
    page.wait_for_function("document.getElementById('legal-context-display').dataset.contextRevision === '1'")


def test_real_chromium_legal_context_form_uses_actual_cookie_case_and_encrypted_session(tmp_path, monkeypatch):
    with _page(tmp_path, monkeypatch, "typed_owner") as (world, page):
        path = _browser_start(page, world)
        assert page.locator("#legal-context-display").get_attribute("data-governing-law-defaulted") == "false"
        _browser_save(page, path, "Synthetic private browser forum")
        assert "Synthetic private browser forum" in page.locator("#legal-context-display").inner_text()
        assert "Synthetic private browser forum" not in page.evaluate("JSON.stringify({local:{...localStorage},session:{...sessionStorage}})")


@pytest.mark.parametrize("boundary", ["clear", "switch", "logout"])
def test_real_context_dom_participates_in_existing_private_boundaries(tmp_path, monkeypatch, boundary):
    with _page(tmp_path, monkeypatch, "typed_owner") as (world, page):
        path = _browser_start(page, world)
        _browser_save(page, path, "Synthetic private prior context")
        if boundary == "switch":
            page.fill("#workspace-switch-user-id", "synthetic-next-user")
            page.click("#workspace-switch-user")
        elif boundary == "logout":
            page.click("#workspace-logout")
        else:
            page.click("#workspace-clear-private-state")
        page.wait_for_function("document.getElementById('legal-context-case-id').value === ''")
        assert page.locator("#legal-context-forum").input_value() == ""
        assert page.locator("#legal-context-jurisdiction").input_value() == ""
        assert not page.locator("#legal-context-display").get_attribute("data-context-revision")
        text = " ".join(page.locator("#" + element).inner_text() for element in [
            "legal-context-display", "legal-context-proofs", "legal-context-versions", "legal-context-provenance"])
        assert "Synthetic private prior context" not in text
        if boundary == "logout":
            assert page.evaluate("async () => (await fetch('/api/complaint-workspace/auth/session', {credentials:'same-origin'})).status") == 401


def test_real_context_dom_drops_late_actual_response_after_case_input_switch(tmp_path, monkeypatch):
    """A deterministic client-delivery race; ASGI transport stays serialized."""
    with _page(tmp_path, monkeypatch, "typed_owner") as (world, page):
        path = _browser_start(page, world)
        _browser_save(page, path, "Synthetic first case private context")
        page.evaluate("""path => {
            const actual = window.workspaceClient.fetchImpl;
            const render = window.renderLegalContext;
            window.oldLegalResponseReady = false;
            window.oldLegalResponseDelivered = false;
            window.oldLegalRenderSettled = false;
            window.renderLegalContext = function(payload, capture) {
                try { return render(payload, capture); }
                finally {
                    if ('/api/legal-context/' + encodeURIComponent(payload.case_id) === path)
                        window.oldLegalRenderSettled = true;
                }
            };
            window.workspaceClient.fetchImpl = async (...args) => {
                const response = await actual(...args);
                if (new URL(String(args[0]), location.href).pathname === path
                        && (!args[1] || (args[1].method || 'GET') === 'GET')) {
                    window.oldLegalResponseReady = true;
                    await new Promise(resolve => { window.releaseOldLegalResponse = resolve; });
                    window.oldLegalResponseDelivered = true;
                }
                return response;
            };
        }""", path)
        page.click("#legal-context-refresh")
        page.wait_for_function("window.oldLegalResponseReady === true")
        second = world.actual.second
        page.fill("#legal-context-case-id", second.case_id)
        assert page.locator("#legal-context-forum").input_value() == ""
        assert "Synthetic first case private context" not in page.locator("#legal-context-display").inner_text()
        # Exercise this component's input-generation guard independently of
        # the SDK's later setCaseContext privacy-epoch cancellation.
        page.evaluate("() => window.releaseOldLegalResponse()")
        page.wait_for_function("window.oldLegalResponseDelivered === true")
        page.wait_for_function("window.oldLegalRenderSettled === true")
        assert page.locator("#legal-context-case-id").input_value() == second.case_id
        assert page.locator("#legal-context-forum").input_value() == ""
        assert not page.locator("#legal-context-display").get_attribute("data-context-revision")
        assert "Synthetic first case private context" not in page.locator("#legal-context-display").inner_text()
        page.evaluate("""async data => {
            window.workspaceClient.setCaseContext(data.case);
            await window.workspaceClient.bootstrapWorkspace(data.case.tenant_id);
            await window.workspaceClient.runIntakeChatTurn(data.case.tenant_id, data.narrative,
                'original_complaint', {interview_action:'start'});
        }""", {"case": {"tenant_id": second.tenant_id, "case_id": second.case_id,
            "resource_id": second.resource_id, "revision": second.revision}, "narrative": NARRATIVE})
        second_path = f"/api/legal-context/{second.case_id}"
        with page.expect_response(lambda r: r.url.endswith(second_path)) as current:
            page.click("#legal-context-refresh")
        assert current.value.status == 200
        page.wait_for_function("document.getElementById('legal-context-display').dataset.contextRevision === '0'")
        assert page.locator("#legal-context-case-id").input_value() == second.case_id
        assert page.locator("#legal-context-display").get_attribute("data-context-revision") == "0"
        assert page.locator("#legal-context-forum").input_value() == ""
        assert "Synthetic first case private context" not in page.locator("#legal-context-display").inner_text()
