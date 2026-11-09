"""Actual source-owner DB orphans cannot become private case graph authority."""
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from applications.complaint_workspace import ComplaintWorkspaceService
from tests.test_authority_dependency_pipeline import _source_record
from tests.test_gui25_26_private_owner_http import _world, _login, _headers, _start_case, _choose, _acquire

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def test_review_persists_exact_source_custody_without_promoting_orphan_database_graph_rows(tmp_path, monkeypatch):
    world = _world(tmp_path)
    orphan = _source_record("synthetic-source-after-failed-private-CAS", "notice")
    original = ComplaintWorkspaceService._mediator_for_shared_interview
    seen = []
    def with_existing_orphan(self, user_id, case_id, *, cache=True):
        actual = original(self, user_id, case_id, cache=cache)
        # Fixture setup only: an existing source-owner DB row represents an
        # earlier artifact write whose private case-head publication aborted.
        record_id = actual.legal_authority_storage.add_authority({
            "type": "statute", "source": "synthetic-owned-corpus", "title": orphan["citation"],
            "citation": orphan["citation"], "content": orphan["source_text"], "jurisdiction": "OR",
            "metadata": {key: value for key, value in orphan.items()
                if key not in {"id", "content", "claim_type"}},
        }, world.case.tenant_id, claim_type="termination")
        assert type(record_id) is int and record_id > 0
        assert any(row["id"] == record_id for row in actual.get_legal_authorities(
            user_id=world.case.tenant_id, claim_type="termination"))
        seen.append(record_id)
        return actual
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _login(client)
        _start_case(client, world, csrf)
        generation = _choose(client, world, csrf)
        acquired = _acquire(client, world, csrf, generation)
        before = client.get("/api/complaint-workspace/session", headers=_headers(world)).json()["session"]["shared_interview"]
        source = next(row for row in acquired["source_version_receipts"] if row["kind"] == "candidate")
        body = {"decision": "admit", "source_passage": source["source_passage"],
            "authority_identity": source["authority_identity"], "jurisdiction": source["jurisdiction"],
            "effective_date": source["effective_date"], "version": source["version"],
            "content_hash": source["content_hash"], "applicability": source["stated_applicability"],
            "treatment_state": source["treatment_state"], "exceptions": source["exceptions"],
            "operation_id": "synthetic-reviewed-source-no-orphan-promotion"}
        monkeypatch.setattr(ComplaintWorkspaceService, "_mediator_for_shared_interview", with_existing_orphan)
        reviewed = client.post(f"/api/legal-research/{world.case.case_id}/admissions", headers=_headers(world, csrf), json=body)
        assert reviewed.status_code == 200
        assert reviewed.json()["source_status"] == "source_admitted" and seen
        after = client.get("/api/complaint-workspace/session", headers=_headers(world)).json()["session"]["shared_interview"]
        assert after["dependency_graph"] == before["dependency_graph"], "research_source_custody_promoted_legacy_db_union"
        assert after["knowledge_graph"] == before["knowledge_graph"]
        assert after["pending_inquiry"] == before["pending_inquiry"]
        assert reviewed.json()["graph_mutated"] is False
        assert reviewed.json()["dependency_refresh_status"] == "not_requested"
        assert reviewed.json()["admitted_law"] is False and reviewed.json()["proof"] is False
        admission = after["intake_case_file"]["legal_source_passage_index"][source["content_hash"]]["source_admission"]
        assert not set(seen) & set(admission["stored_record_ids"])
