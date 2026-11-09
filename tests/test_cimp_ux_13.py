"""Case-scoped encrypted evidence catalog and ingestion lifecycle.

Receipt of ciphertext is not authenticity, relevance, admissibility, or claim
support. The six ingestion states stay distinct, and a locked key or missing
extractor is unavailable rather than a successful fallback.
"""

from __future__ import annotations

import base64
import hashlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.case_message_api import CaseMessageService
from applications.case_routes import compose_case_routes
from integrations.evidence_workspace import EvidenceWorkspace, MemoryByteBackend
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import PASSPHRASE, _composed_headers, _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

SOURCE = "notice.txt"
ORIGINAL = "Housing denial scan.tiff"
PAYLOAD = b"synthetic housing denial notice dated March 1"


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _world(tmp_path):
    world = owner_lawyer_journey_world(tmp_path / "journey")
    backend = MemoryByteBackend()
    workspace = EvidenceWorkspace(
        world.cases,
        {world.owner.principal_id: world.owner_keys, world.lawyer.principal_id: world.recipient},
        backend,
        tmp_path / "evidence-root",
    )
    app = FastAPI()
    compose_case_routes(
        app,
        authorizer=world.authorizer,
        browser_sessions=world.sessions,
        case_assignments=world.assignments,
        case_messages=CaseMessageService(world.messages),
        case_reviews=world.reviews,
        case_consent=world.consent,
        evidence_workspace=workspace,
        include_review=False,
        include_document=False,
    )
    return world, app, backend, workspace


def _body(case, **extra):
    payload = {
        "tenant_id": case.tenant_id,
        "case_id": case.case_id,
        "resource_id": case.resource_id,
        "source_filename": SOURCE,
        "original_filename": ORIGINAL,
        "media_type": "text/plain",
        "content_base64": base64.b64encode(PAYLOAD).decode("ascii"),
        "idempotency_key": "recv-ux13-1",
    }
    payload.update(extra)
    return payload


def _receive(client, case, csrf, **extra):
    return client.post(
        "/api/cases/evidence",
        headers=_composed_headers(case, csrf),
        json=_body(case, **extra),
    )


def test_owner_receives_encrypted_catalog_entry_without_legal_conclusions(tmp_path):
    world, app, backend, _workspace = _world(tmp_path)
    with TestClient(app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        denied = client.post("/api/cases/evidence", json=_body(world.case))
        assert denied.status_code == 403
        assert denied.json()["error"] == "csrf_rejected"

        created = _receive(client, world.case, csrf)
        assert created.status_code == 201, created.text
        record = created.json()
        assert record["ingestion_status"] == "received"
        assert record["current_version"] == 1
        assert record["artifact_versions"][0]["kind"] == "source"
        assert record["artifact_versions"][0]["integrity_sha256"] == _digest(PAYLOAD)
        assert record["integrity_verified"] is True
        assert record["source_filename"] == SOURCE
        assert record["original_filename"] == ORIGINAL
        assert record["actor_principal_id"] == world.owner.principal_id
        assert record["case_id"] == world.case.case_id
        assert record["canonical_owner_principal_id"] == world.case.tenant_id
        assert record["actor_is_canonical_owner"] is False
        assert len(record["scope_binding"]) == 64
        for quality in ("authenticity", "relevance", "admissibility", "claim_support"):
            assert record[quality] == "not_established"
        assert record["receipt"]["ciphertext_readback"] is True
        assert record["receipt"]["establishes_authenticity"] is False
        assert record["receipt"]["establishes_claim_support"] is False
        assert record["receipt_establishes_legal_quality"] is False
        assert "cid" not in record
        assert backend.contains(PAYLOAD) is False
        assert backend.contains(ORIGINAL.encode()) is False
        assert backend.contains(SOURCE.encode()) is False

        replay = _receive(client, world.case, csrf)
        assert replay.status_code == 201
        assert replay.json()["evidence_id"] == record["evidence_id"]

        clash = _receive(client, world.case, csrf, content_base64=base64.b64encode(b"other notice").decode("ascii"))
        assert clash.status_code == 409
        assert clash.json()["error"] == "replay_mismatch"

        listed = client.get("/api/cases/evidence", headers=_composed_headers(world.case, csrf))
        assert listed.status_code == 200, listed.text
        items = listed.json()["items"]
        assert len(items) == 1
        assert items[0]["evidence_id"] == record["evidence_id"]
        assert items[0]["integrity_verified"] is True
        assert items[0]["scope_binding"] == record["scope_binding"]
        assert listed.json()["receipt_establishes_legal_quality"] is False


def test_lifecycle_separates_extracted_review_linked_failed_and_unavailable(tmp_path):
    world, app, _backend, _workspace = _world(tmp_path)
    with TestClient(app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        created = _receive(client, world.case, csrf, idempotency_key="recv-ux13-life").json()
        evidence_id = created["evidence_id"]
        walked = _receive(client, world.case, csrf, idempotency_key="recv-ux13-walk").json()
        walked_id = walked["evidence_id"]

        missing = client.post(
            "/api/cases/evidence/lifecycle",
            headers=_composed_headers(world.case, csrf),
            json={
                "tenant_id": world.case.tenant_id,
                "case_id": world.case.case_id,
                "resource_id": world.case.resource_id,
                "evidence_id": evidence_id,
                "action": "extract",
                "expected_artifact_version": 1,
                "idempotency_key": "life-extract-missing",
            },
        )
        assert missing.status_code == 503
        assert missing.json()["ingestion_status"] == "unavailable"
        assert missing.json()["prior_ingestion_status"] == "received"
        assert missing.json()["failure_code"] == "extraction_capability_unavailable"
        assert missing.json()["operation_succeeded"] is False
        assert missing.json()["claim_support"] == "not_established"

        stale = client.post(
            "/api/cases/evidence/lifecycle",
            headers=_composed_headers(world.case, csrf),
            json={
                "tenant_id": world.case.tenant_id,
                "case_id": world.case.case_id,
                "resource_id": world.case.resource_id,
                "evidence_id": evidence_id,
                "action": "needs-review",
                "expected_artifact_version": 9,
                "idempotency_key": "life-stale",
            },
        )
        assert stale.status_code == 409
        assert stale.json()["error"] == "revision_conflict"

        extracted_bytes = b"exact passage: request denied"
        extracted = client.post(
            "/api/cases/evidence/lifecycle",
            headers=_composed_headers(world.case, csrf),
            json={
                "tenant_id": world.case.tenant_id,
                "case_id": world.case.case_id,
                "resource_id": world.case.resource_id,
                "evidence_id": walked_id,
                "action": "extract",
                "expected_artifact_version": 1,
                "extracted_content_base64": base64.b64encode(extracted_bytes).decode("ascii"),
                "idempotency_key": "life-extract",
            },
        )
        assert extracted.status_code == 200, extracted.text
        assert extracted.json()["ingestion_status"] == "extracted"
        assert extracted.json()["current_version"] == 2
        assert extracted.json()["artifact_versions"][1]["kind"] == "extraction"
        assert extracted.json()["integrity_sha256"] == _digest(extracted_bytes)
        assert extracted.json()["admissibility"] == "not_established"

        review = client.post(
            "/api/cases/evidence/lifecycle",
            headers=_composed_headers(world.case, csrf),
            json={
                "tenant_id": world.case.tenant_id,
                "case_id": world.case.case_id,
                "resource_id": world.case.resource_id,
                "evidence_id": walked_id,
                "action": "needs-review",
                "expected_artifact_version": 2,
                "idempotency_key": "life-review",
            },
        )
        assert review.status_code == 200, review.text
        assert review.json()["ingestion_status"] == "needs-review"
        assert review.json()["relevance"] == "not_established"

        linked = client.post(
            "/api/cases/evidence/lifecycle",
            headers=_composed_headers(world.case, csrf),
            json={
                "tenant_id": world.case.tenant_id,
                "case_id": world.case.case_id,
                "resource_id": world.case.resource_id,
                "evidence_id": walked_id,
                "action": "link",
                "complaint_link_id": "paragraph-4",
                "expected_artifact_version": 2,
                "idempotency_key": "life-link",
                "claim_support": True,
            },
        )
        assert linked.status_code == 403
        assert linked.json()["error"] == "legal_quality_rejected"

        linked = client.post(
            "/api/cases/evidence/lifecycle",
            headers=_composed_headers(world.case, csrf),
            json={
                "tenant_id": world.case.tenant_id,
                "case_id": world.case.case_id,
                "resource_id": world.case.resource_id,
                "evidence_id": walked_id,
                "action": "link",
                "complaint_link_id": "paragraph-4",
                "expected_artifact_version": 2,
                "idempotency_key": "life-link",
            },
        )
        assert linked.status_code == 200, linked.text
        assert linked.json()["ingestion_status"] == "linked"
        assert linked.json()["complaint_link_id"] == "paragraph-4"
        assert linked.json()["claim_support"] == "not_established"
        assert linked.json()["receipt"]["establishes_claim_support"] is False

        failed = client.post(
            "/api/cases/evidence/lifecycle",
            headers=_composed_headers(world.case, csrf),
            json={
                "tenant_id": world.case.tenant_id,
                "case_id": world.case.case_id,
                "resource_id": world.case.resource_id,
                "evidence_id": walked_id,
                "action": "fail",
                "failure_code": "operator-rejected-parse",
                "expected_artifact_version": 2,
                "idempotency_key": "life-fail",
            },
        )
        assert failed.status_code == 409
        assert failed.json()["ingestion_status"] == "failed"
        assert failed.json()["prior_ingestion_status"] == "linked"
        assert failed.json()["failure_code"] == "operator-rejected-parse"
        assert failed.json()["authenticity"] == "not_established"


def test_locked_key_cross_case_and_other_actor_cannot_use_the_catalog(tmp_path):
    world, app, backend, workspace = _world(tmp_path)
    with TestClient(app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        created = _receive(client, world.case, csrf, idempotency_key="recv-ux13-scope")
        assert created.status_code == 201
        evidence_id = created.json()["evidence_id"]
        world.owner_keys.lock()
        locked = client.get("/api/cases/evidence", headers=_composed_headers(world.case, csrf))
        assert locked.status_code == 503
        assert locked.json()["ingestion_status"] == "unavailable"
        assert locked.json()["items"] == []
        world.owner_keys.unlock_passphrase(PASSPHRASE)

        foreign = _receive(
            client, world.case, csrf,
            case_id="case-does-not-belong",
            idempotency_key="recv-ux13-foreign",
        )
        assert foreign.status_code == 403
        assert foreign.json()["error"] == "not_owner"

        client.cookies.clear()
        lawyer = _composed_login(client, "synthetic-lawyer-credential")
        stolen = client.get("/api/cases/evidence", headers=_composed_headers(world.case, lawyer))
        assert stolen.status_code == 403
        assert stolen.json()["error"] == "not_owner"
        posted = _receive(client, world.case, lawyer, idempotency_key="recv-ux13-lawyer")
        assert posted.status_code == 403

    reopened = EvidenceWorkspace(
        world.cases,
        {world.owner.principal_id: world.owner_keys},
        backend,
        tmp_path / "evidence-root",
    )
    catalog = reopened.list_catalog(world.owner.principal_id, {
        "tenant_id": world.case.tenant_id,
        "case_id": world.case.case_id,
        "resource_id": world.case.resource_id,
    })
    assert catalog["items"][0]["evidence_id"] == evidence_id
    assert catalog["items"][0]["ingestion_status"] == "received"
    assert catalog["items"][0]["integrity_verified"] is True
    assert workspace is not reopened
