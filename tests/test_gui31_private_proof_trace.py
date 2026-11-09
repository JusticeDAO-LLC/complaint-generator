"""Actual encrypted IR is a source-bound candidate, not an executed proof."""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from applications.legal_analysis_api import record_case_proof_traces
from tests.test_gui25_26_private_owner_http import _world, _login, _headers
from tests.test_gui29_private_legal_analysis import _reviewed_source, _analysis_request
from tests.test_cimp_gui_14 import _composed_ciphertext_snapshot

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _compiled(client, world, csrf):
    source = _reviewed_source(client, world, csrf)
    request = _analysis_request(client, world, source)
    response = client.post(f"/api/legal-analysis/{world.case.case_id}", headers=_headers(world, csrf), json=request)
    assert response.status_code == 200, response.text
    assert response.json()["typed_obligations"]
    assert response.json()["executed_proof"] is False
    return response.json()


def test_real_current_encrypted_ir_projects_as_unexecuted_without_write_or_new_compilation(tmp_path, monkeypatch):
    world = _world(tmp_path)
    assert world.owner.principal_id != world.case.tenant_id
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _login(client)
        compiled = _compiled(client, world, csrf)
        before = _composed_ciphertext_snapshot(world.service)
        import integrations.ipfs_datasets.logic as logic
        def no_new_execution(*args, **kwargs):
            pytest.fail("read_only_trace_executed_compiler_model_or_prover")
        monkeypatch.setattr(logic, "compile_canonical_legal_ir", no_new_execution)
        monkeypatch.setattr(logic, "route_bound_legal_ir_proof", no_new_execution)
        response = client.get(f"/api/legal-analysis/{world.case.case_id}/proof-traces", headers=_headers(world))
        assert response.status_code == 200, response.text
        view = response.json()
        assert view["obligations"], "current_encrypted_canonical_obligations_discarded_for_phase_cache"
        assert {row["obligation_id"] for row in view["obligations"]} == {row["obligation_id"] for row in compiled["typed_obligations"]}
        assert view["executed_proof"] is False and view["proof"] is False
        assert all(row["executed_proof"] is False and row["green_checkmark"] is False for row in view["obligations"])
        assert _composed_ciphertext_snapshot(world.service) == before


def test_cached_actual_mediator_cannot_serve_trace_after_current_case_key_lock(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _login(client)
        _compiled(client, world, csrf)
        source = client.get("/api/complaint-workspace/session", headers=_headers(world)).json()["session"]["shared_interview"]
        restored = world.mediator.workflow_actions.restore_session_projection(deepcopy(source))
        assert not restored.get("error")
        # A caller-reported trace is not a proof, but it is still private case
        # content: locking the actual encrypted owner must also block its cache.
        supplied = {"request_id": "synthetic-cached-trace", "source_identity": "synthetic-claimed-source",
            "obligations": [{"obligation_id": "synthetic-private-trace", "statement": "synthetic-private-proof-marker",
                "source_span": "source:0-1", "source_identity": "synthetic-claimed-source",
                "proof_status": "not_executed", "engine_name": "", "engine_version": ""}]}
        recorded = client.post(f"/api/legal-analysis/{world.case.case_id}/proof-traces", headers=_headers(world, csrf), json=supplied)
        assert recorded.status_code in {200, 400, 403, 503}
        assert world.service.lock_private_keys()["unlocked"] is False
        before = _composed_ciphertext_snapshot(world.service)
        response = client.get(f"/api/legal-analysis/{world.case.case_id}/proof-traces", headers=_headers(world))
        assert response.status_code == 503, response.text
        assert "synthetic-private-proof-marker" not in response.text
        assert _composed_ciphertext_snapshot(world.service) == before


def test_client_engine_and_executed_claim_do_not_mint_a_green_proof(tmp_path):
    world = _world(tmp_path)
    result = record_case_proof_traces(world.mediator, {"request_id": "synthetic-unissued-claim",
        "source_identity": "synthetic-claimed-source", "obligations": [{
            "obligation_id": "unissued-proof", "statement": "A caller asserts a theorem was proved.",
            "source_span": "source:0-1", "source_identity": "synthetic-claimed-source",
            "proof_status": "executed", "engine_name": "claimed-engine", "engine_version": "claimed-version",
            "green_checkmark": True, "legal_sufficiency": True}]})
    assert result["executed_proof"] is False and result["proof"] is False
    assert result["obligations"][0]["green_checkmark"] is False



def test_empty_current_private_case_read_is_nonproof_and_does_not_write(tmp_path):
    from tests.test_cimp_gui_14 import _composed_case_world
    from tests.test_gui29_private_legal_analysis import _start
    world = _composed_case_world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        _start(client, world)
        before = _composed_ciphertext_snapshot(world.services[world.case.case_id])
        response = client.get(f"/api/legal-analysis/{world.case.case_id}/proof-traces",
            headers=_headers(world))
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["status"] == "empty" and data["obligations"] == [] and data["engine_versions"] == []
        assert data["executed_proof"] is False and data["read_only"] is True
        assert data["capabilities"]["executes_engine"] is False
        assert _composed_ciphertext_snapshot(world.services[world.case.case_id]) == before


def test_cold_compiler_registry_loss_does_not_remove_source_obligations_or_create_proof(tmp_path):
    from integrations.ipfs_datasets.logic import reset_canonical_formalization_cache
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _login(client)
        compiled = _compiled(client, world, csrf)
        reset_canonical_formalization_cache()
        before = _composed_ciphertext_snapshot(world.service)
        response = client.get(f"/api/legal-analysis/{world.case.case_id}/proof-traces", headers=_headers(world))
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["source_current"] is True and data["compiler_execution_verified"] is False
        assert {x["obligation_id"] for x in data["obligations"]} == {x["obligation_id"] for x in compiled["typed_obligations"]}
        assert data["engine_versions"] == [] and data["executed_proof"] is False
        assert all(x["proof_verification"]["checked_kernel_verified"] is False and not x["green_checkmark"] for x in data["obligations"])
        assert _composed_ciphertext_snapshot(world.service) == before


def test_case_policy_only_lawyer_and_stranger_cannot_read_owner_proof_material(tmp_path):
    from applications.case_access import ASSIGNED_LAWYER_ACTIONS
    from tests.test_cimp_gui_14 import _composed_login
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _login(client)
        _compiled(client, world, csrf)
        path = f"/api/legal-analysis/{world.case.case_id}/proof-traces"
        assert client.get(path + "?case_id=other-case", headers=_headers(world)).status_code == 403
        grant = world.authorizer.grant_assigned_lawyer(owner_principal_id=world.owner.principal_id,
            lawyer_principal_id=world.lawyer.principal_id, case_id=world.case.case_id,
            resource_id=world.case.resource_id, tenant_id=world.case.tenant_id,
            actions=set(ASSIGNED_LAWYER_ACTIONS), expected_case_revision=world.case.revision)
        _composed_login(client, "synthetic-lawyer-credential")
        headers = {**_headers(world), "x-expected-membership-revision": str(grant.revision)}
        denied = client.get(path, headers=headers)
        assert denied.status_code == 403 and not denied.json().get("obligations")
        _composed_login(client, "synthetic-stranger-credential")
        denied = client.get(path, headers=_headers(world))
        assert denied.status_code == 403 and not denied.json().get("obligations")


@pytest.mark.parametrize("change", ["logout", "rotate", "keylock", "source"])
def test_current_proof_read_refuses_late_session_key_or_source_change(tmp_path, monkeypatch, change):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    import applications.legal_analysis_api as api
    world = _world(tmp_path)
    reached, release = Event(), Event()
    actual = api.project_current_case_proof_traces
    def paused(*args, **kwargs):
        result = actual(*args, **kwargs)
        assert result["obligations"]
        reached.set()
        assert release.wait(20), "test_read_projection_barrier_expired"
        return result
    monkeypatch.setattr(api, "project_current_case_proof_traces", paused)
    with TestClient(world.app, base_url="https://testserver") as client, TestClient(world.app, base_url="https://testserver") as other:
        csrf = _login(client)
        _compiled(client, world, csrf)
        other.cookies.update(client.cookies)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(client.get, f"/api/legal-analysis/{world.case.case_id}/proof-traces", headers=_headers(world))
            try:
                assert reached.wait(20), "actual_current_proof_projection_not_reached"
                if change == "logout":
                    assert other.post("/api/complaint-workspace/auth/logout", headers={"x-csrf-token": csrf}).status_code == 200
                elif change == "rotate":
                    assert other.post("/api/complaint-workspace/auth/rotate", headers={"x-csrf-token": csrf}).status_code == 200
                elif change == "keylock":
                    assert world.service.lock_private_keys()["unlocked"] is False
                else:
                    context = other.get(f"/api/legal-context/{world.case.case_id}", headers=_headers(world))
                    changed = other.post(f"/api/legal-context/{world.case.case_id}", headers=_headers(world, csrf), json={
                        "expected_context_revision": context.json()["context_revision"], "forum": "new synthetic proof-source forum"})
                    assert changed.status_code == 200, changed.text
                after_other_effect = _composed_ciphertext_snapshot(world.service)
            finally:
                release.set()
            response = pending.result(timeout=20)
        assert response.status_code in {401, 403, 409, 503}, response.text
        assert not response.json().get("obligations") and response.json().get("executed_proof") is False
        assert _composed_ciphertext_snapshot(world.service) == after_other_effect


def test_legacy_projection_copies_claims_and_never_recreates_green_or_engine_authority():
    from applications.legal_analysis_api import project_proof_traces
    stored = {"proof_trace_display": {"status": "visible", "engine_versions": [{"name": "claim", "version": "claim"}],
        "obligations": [{"proof_status": "executed", "green_checkmark": True, "executed_proof": True,
            "source_bound": True, "engine_name": "claim", "engine_version": "claim"}]}}
    before = deepcopy(stored)
    view = project_proof_traces(stored)
    assert stored == before
    assert view["engine_versions"] == [] and view["executed_proof"] is False
    assert view["obligations"][0]["green_checkmark"] is False and view["obligations"][0]["source_bound"] is False


def test_modified_obligation_span_cannot_borrow_current_source_binding(tmp_path):
    from applications.legal_analysis_api import project_current_case_proof_traces
    from tests.test_cimp_gui_29 import LEGAL_TEXT
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _login(client)
        _compiled(client, world, csrf)
        analysis = client.get(f"/api/legal-analysis/{world.case.case_id}", headers=_headers(world)).json()
    assert analysis["source_current"] is True
    modified = deepcopy(analysis)
    altered_id = modified["typed_obligations"][0]["obligation_id"]
    modified["typed_obligations"][0]["statement"] = "A caller rewrites the theorem."
    projected = project_current_case_proof_traces(modified, source_text=LEGAL_TEXT)
    expected_ids = {row["obligation_id"] for row in analysis["typed_obligations"]} - {altered_id}
    assert {row["obligation_id"] for row in projected["obligations"]} == expected_ids
    assert all(row["statement"] != "A caller rewrites the theorem." for row in projected["obligations"])
    assert projected["status"] == "unavailable"
    assert projected["reason"] == "canonical_obligation_source_unbound" and projected["executed_proof"] is False


def test_client_proof_post_requires_unavailable_issued_producer_and_never_writes(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _login(client)
        _compiled(client, world, csrf)
        before = _composed_ciphertext_snapshot(world.service)
        response = client.post(f"/api/legal-analysis/{world.case.case_id}/proof-traces",
            headers=_headers(world, csrf), json={"request_id": "synthetic-unissued-provider",
                "source_identity": "synthetic-claimed-source", "obligations": [{
                    "obligation_id": "claimed-proof", "statement": "Caller claims success.",
                    "source_span": "source:0-1", "proof_status": "executed",
                    "engine_name": "claimed-engine", "engine_version": "claimed-version"}]})
        assert response.status_code == 503, response.text
        data = response.json()
        assert data["error"] == "proof_producer_unavailable" and data["executed_proof"] is False
        assert data["obligations"] == [] and data["engine_versions"] == []
        assert _composed_ciphertext_snapshot(world.service) == before
