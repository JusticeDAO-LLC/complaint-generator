"""Actual current-owner graph refresh, source custody and late refusal.

The recorded legal source is authored synthetic input through the real pinned
Data acquisition/admission owner. This does not qualify a live legal corpus.
Delivery barriers pause the unchanged actual Core result, never fabricate it.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event

from fastapi.testclient import TestClient
import pytest

from tests.test_cimp_gui_28 import _world
from tests.test_cimp_gui_14 import _composed_headers, _composed_ciphertext_snapshot
from tests.test_gui24_private_context import _start

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _request(world, **changes):
    value = {"operation_id": "current-private-refresh", "case_id": world.case.case_id,
        "correction_kind": "context", "expected_case_revision": world.case.revision,
        "expected_consent_generation": 1, "expected_grant_revision": 0,
        "expected_dependency_generation": 0, "legal_source_hashes": []}
    value.update(changes)
    return value


def _choose(world, purpose="citation_acquisition"):
    return world.consent.choose(world.owner.principal_id, world.case.case_id,
        {"purpose": purpose, "mode": "local_private", "expected_generation": 0})


def test_private_revision_is_actual_decimal_string_and_wrong_case_or_body_authority_refused(tmp_path):
    world = _world(tmp_path)
    path = f"/api/graphs/{world.case.case_id}/legal-dependency/refresh"
    service = world.services[world.case.case_id]
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _start(client, world.case)
        _choose(world)
        headers = _composed_headers(world.case, csrf)
        state = client.get("/api/complaint-workspace/session", headers=headers).json()["session"]
        assert isinstance(state["private_revision"], str)
        before = _composed_ciphertext_snapshot(service)
        for changes, error in [({"case_id": world.second.case_id}, "cross_case_id"),
                ({"source_records": []}, "client_case_authority"),
                ({"expected_dependency_generation": True}, "refresh_field"),
                ({"expected_private_revision": int(state["private_revision"])}, "refresh_field")]:
            response = client.post(path, headers=headers, json=_request(world, **changes))
            assert response.status_code in {400, 403}
            # The canonical case middleware may refuse a foreign body tuple
            # before the graph owner sees it; both preserve the same boundary.
            assert response.json()["error"] in ({"cross_case_id", "resource_mismatch"}
                if error == "cross_case_id" else {error})
            assert _composed_ciphertext_snapshot(service) == before
        allowed = client.post(path, headers=headers, json=_request(world,
            expected_private_revision=state["private_revision"],
            expected_session_revision=state["shared_interview"]["session_revision"]))
        assert allowed.status_code == 200, allowed.text
        assert allowed.json()["applied"] is True
        saved = _composed_ciphertext_snapshot(service)
        stale = client.post(path, headers=headers, json=_request(world,
            operation_id="different-stale-snapshot", expected_private_revision=state["private_revision"]))
        assert stale.status_code == 409 and _composed_ciphertext_snapshot(service) == saved


def test_another_purpose_cannot_substitute_for_current_refresh_decision(tmp_path):
    world = _world(tmp_path)
    service = world.services[world.case.case_id]
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _start(client, world.case)
        _choose(world, "public_law_citation")
        before = _composed_ciphertext_snapshot(service)
        response = client.post(f"/api/graphs/{world.case.case_id}/legal-dependency/refresh",
            headers=_composed_headers(world.case, csrf), json=_request(world))
        assert response.status_code == 403 and response.json()["error"] == "purpose_consent_required"
        assert _composed_ciphertext_snapshot(service) == before


@pytest.mark.parametrize("change", ["logout", "expiry", "keylock", "consent", "context"])
def test_actual_core_result_cannot_publish_after_current_owner_or_source_changes(tmp_path, monkeypatch, change):
    from mediator.workflow_service import WorkflowActionService
    world = _world(tmp_path)
    service = world.services[world.case.case_id]
    reached, release = Event(), Event()
    actual = WorkflowActionService.refresh_legal_dependency_graph
    def pause_result(self, **kwargs):
        result = actual(self, **kwargs)
        assert result["applied"] is True
        reached.set()
        assert release.wait(20), "test_actual_result_delivery_barrier_expired"
        return result
    monkeypatch.setattr(WorkflowActionService, "refresh_legal_dependency_graph", pause_result)
    with TestClient(world.app, base_url="https://testserver") as client, TestClient(world.app, base_url="https://testserver") as other:
        csrf = _start(client, world.case)
        _choose(world)
        other.cookies.update(client.cookies)
        headers = _composed_headers(world.case, csrf)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(client.post, f"/api/graphs/{world.case.case_id}/legal-dependency/refresh",
                                  headers=headers, json=_request(world))
            try:
                assert reached.wait(20), "actual_core_refresh_not_reached"
                if change == "logout":
                    assert other.post("/api/complaint-workspace/auth/logout", headers={"x-csrf-token": csrf}).status_code == 200
                elif change == "expiry":
                    world.clock["now"] += 301
                elif change == "keylock":
                    assert service.lock_private_keys()["unlocked"] is False
                elif change == "consent":
                    world.consent.revoke(world.owner.principal_id, world.case.case_id,
                        {"purpose": "citation_acquisition", "expected_generation": 1})
                else:
                    current = other.get(f"/api/legal-context/{world.case.case_id}", headers=headers)
                    assert current.status_code == 200
                    changed = other.post(f"/api/legal-context/{world.case.case_id}", headers=headers, json={
                        "expected_context_revision": current.json()["context_revision"],
                        "jurisdiction": "OR", "applicability": "explicit", "applicable_law_date": "2024-06-01"})
                    assert changed.status_code == 200, changed.text
                after_other_effect = _composed_ciphertext_snapshot(service)
            finally:
                release.set()
            response = pending.result(timeout=20)
        assert response.status_code in {401, 403, 409, 503}, response.text
        assert response.json().get("applied") is not True
        assert _composed_ciphertext_snapshot(service) == after_other_effect


def test_actual_reviewed_source_refreshes_real_private_graph_and_cold_replays_current_scope(tmp_path):
    from applications.complaint_workspace import ComplaintWorkspaceService
    from tests.test_gui25_26_private_owner_http import _world as source_world, _login, _headers, _start_case, _choose as source_choose, _acquire
    from tests.test_gui25_26_canonical_contract import _real_source
    world = source_world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _login(client)
        _start_case(client, world, csrf)
        generation = source_choose(client, world, csrf)
        acquired = _acquire(client, world, csrf, generation)
        candidate = next(row for row in acquired["source_version_receipts"] if row["kind"] == "candidate")
        review = {"decision": "admit", **{key: candidate[key] for key in
            ("source_passage", "authority_identity", "jurisdiction", "effective_date", "version", "content_hash", "treatment_state", "exceptions")},
            "applicability": candidate["stated_applicability"], "operation_id": "review-exact-synthetic-source"}
        stored = client.post(f"/api/legal-research/{world.case.case_id}/admissions", headers=_headers(world, csrf), json=review)
        assert stored.status_code == 200 and stored.json()["source_status"] == "source_admitted", stored.text
        hashes = [stored.json()["source_admission"]["hashes"]["source_hash"]]
        before = client.get("/api/complaint-workspace/session", headers=_headers(world)).json()["session"]
        request = {"operation_id": "refresh-current-record", "case_id": world.case.case_id,
            "correction_kind": "source", "expected_case_revision": world.case.revision,
            "expected_consent_generation": generation, "expected_grant_revision": 0,
            "expected_dependency_generation": 0, "legal_source_hashes": hashes}
        response = client.post(f"/api/graphs/{world.case.case_id}/legal-dependency/refresh",
            headers=_headers(world, csrf), json=request)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["applied"] is True and result["dependency_refresh"]["source_admission_reread"] is True
        assert result["legal_source_hashes"] == hashes and set(result["admitted_source_hashes"]).issubset(hashes)
        assert result["proof"] is False and result["legal_sufficiency"] is False
        after = client.get("/api/complaint-workspace/session", headers=_headers(world)).json()["session"]
        assert after["shared_interview"]["knowledge_graph"] == before["shared_interview"]["knowledge_graph"]
        assert after["shared_interview"]["intake_case_file"]["legal_context"] == before["shared_interview"]["intake_case_file"]["legal_context"]
        assert int(after["private_revision"]) == int(before["private_revision"]) + 1
    fresh = ComplaintWorkspaceService(root_dir=world.service_root)
    assert fresh.unlock_private_keys(passphrase="synthetic-password")["unlocked"] is True
    mediator, *_ = _real_source(tmp_path / "cold-source-owner")
    with TestClient(world.app_for(mediator, fresh), base_url="https://testserver") as client:
        csrf = _login(client)
        before_replay = _composed_ciphertext_snapshot(fresh)
        replay = client.post(f"/api/graphs/{world.case.case_id}/legal-dependency/refresh",
            headers=_headers(world, csrf), json=request)
        assert replay.status_code == 200 and replay.json()["replayed"] is True, replay.text
        assert _composed_ciphertext_snapshot(fresh) == before_replay
