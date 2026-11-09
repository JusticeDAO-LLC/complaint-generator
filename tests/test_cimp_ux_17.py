"""Versioned comments, labels, and page spans on exact evidence versions.

A note stays a note until an explicit adopt. The session actor and case key
authorize the write. Display-role text does not. A comment does not become a
new document, and an omitted claim element does not become causation.
"""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from applications.evidence_annotation_store import EvidenceAnnotationStore
from integrations.evidence_workspace import MemoryByteBackend
from integrations.private_storage import BoundPrivateRecordError
from tests.test_cimp_gui_14 import _composed_headers, _composed_login
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

NOTE = "synthetic margin note about the denial letter"
LABEL = "housing-denial"
KEY = bytes(range(32))
OTHER_KEY = bytes(reversed(range(32)))


def _ready(tmp_path):
    world = owner_lawyer_journey_world(tmp_path / "journey")
    backend = MemoryByteBackend()
    from integrations.evidence_workspace import EvidenceWorkspace
    workspace = EvidenceWorkspace(
        world.cases,
        {world.owner.principal_id: world.owner_keys, world.lawyer.principal_id: world.recipient},
        backend,
        tmp_path / "evidence-root",
    )
    world.app.state.evidence_workspace = workspace
    world.backend = backend
    return world


def _receive(client, case, csrf):
    response = client.post(
        "/api/cases/evidence",
        headers=_composed_headers(case, csrf),
        json={
            "tenant_id": case.tenant_id,
            "case_id": case.case_id,
            "resource_id": case.resource_id,
            "source_filename": "denial-letter.txt",
            "original_filename": "denial-letter.txt",
            "media_type": "text/plain",
            "content_base64": base64.b64encode(b"Line alpha\nLine beta span target\n").decode("ascii"),
            "idempotency_key": "ux17-evidence",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _annotation_body(case, evidence_id, **extra):
    body = {
        "tenant_id": case.tenant_id,
        "case_id": case.case_id,
        "resource_id": case.resource_id,
        "evidence_id": evidence_id,
        "artifact_version": 1,
        "expected_case_revision": case.revision,
        "expected_annotation_revision": "",
        "idempotency_key": "ux17-note",
        "kind": "comment",
        "note": NOTE,
        "display_role": "operational_admin",
    }
    body.update(extra)
    return body


def _post(client, case, csrf, body):
    return client.post("/api/cases/evidence/annotations", headers=_composed_headers(case, csrf), json=body)


def _ids(client, case):
    listed = client.get(
        f"/api/cases/evidence?tenant_id={case.tenant_id}&case_id={case.case_id}&resource_id={case.resource_id}",
        headers=_composed_headers(case),
    )
    assert listed.status_code == 200, listed.text
    return [item["evidence_id"] for item in listed.json()["items"]]


def test_store_seals_versioned_notes_with_cas_and_ignores_display_role(tmp_path):
    store = EvidenceAnnotationStore(tmp_path)
    common = dict(
        evidence_id="evidence-1",
        artifact_version=1,
        actor_principal_id="actor-owner",
        canonical_owner_principal_id="tenant-owner",
        tenant_id="tenant-owner",
        case_id="case-17",
        key=KEY,
        key_id="key-17",
        display_role="lawyer",
    )
    comment = store.commit_attributed_annotation(
        kind="comment",
        note=NOTE,
        idempotency_key="comment-1",
        expected_annotation_revision="",
        **common,
    )
    replay = store.commit_attributed_annotation(
        kind="comment",
        note=NOTE,
        idempotency_key="comment-1",
        expected_annotation_revision="",
        **common,
    )
    assert replay["annotation_id"] == comment["annotation_id"]
    assert replay["idempotent_replay"] is True
    assert comment["adopted"] is False
    assert comment["record_type"] == "note"
    assert comment["claim_element"] == ""
    assert comment["claim_element_is_causation"] is False
    assert comment["actor_principal_id"] == "actor-owner"
    assert comment["display_role_authoritative"] is False
    assert comment["synthesized_evidence"] is False
    label = store.commit_attributed_annotation(
        kind="label",
        label=LABEL,
        idempotency_key="label-1",
        expected_annotation_revision=comment["annotation_revision"],
        **common,
    )
    span = store.commit_attributed_annotation(
        kind="page_span",
        note="span note",
        page=1,
        span_start=1,
        span_end=4,
        idempotency_key="span-1",
        expected_annotation_revision=label["annotation_revision"],
        **common,
    )
    assert span["anchor"] == "page-1-span-1-4"
    assert span["adopted"] is False
    with pytest.raises(BoundPrivateRecordError) as stale:
        store.commit_attributed_annotation(
            kind="comment",
            note="another note",
            idempotency_key="comment-2",
            expected_annotation_revision="",
            **common,
        )
    assert stale.value.code == "revision_conflict"
    with pytest.raises(BoundPrivateRecordError) as replay_conflict:
        store.commit_attributed_annotation(
            kind="comment",
            note="changed note",
            idempotency_key="comment-1",
            expected_annotation_revision=span["annotation_revision"],
            **common,
        )
    assert replay_conflict.value.code == "replay_mismatch"
    listed = store.list_attributed_annotations(
        evidence_id="evidence-1",
        artifact_version=1,
        canonical_owner_principal_id="tenant-owner",
        tenant_id="tenant-owner",
        case_id="case-17",
        key=KEY,
    )
    assert listed["annotation_revision"] == span["annotation_revision"]
    assert {item["kind"] for item in listed["items"]} == {"comment", "label", "page_span"}
    assert all(item["adopted"] is False and item["claim_element"] != "causation" for item in listed["items"])
    other_version = store.list_attributed_annotations(
        evidence_id="evidence-1",
        artifact_version=2,
        canonical_owner_principal_id="tenant-owner",
        tenant_id="tenant-owner",
        case_id="case-17",
        key=KEY,
    )
    assert other_version["items"] == []
    with pytest.raises(BoundPrivateRecordError) as wrong_key:
        store.list_attributed_annotations(
            evidence_id="evidence-1",
            artifact_version=1,
            canonical_owner_principal_id="tenant-owner",
            tenant_id="tenant-owner",
            case_id="case-17",
            key=OTHER_KEY,
        )
    assert wrong_key.value.code == "authentication_failed"
    for path in tmp_path.rglob("*"):
        if path.is_file():
            blob = path.read_bytes()
            assert NOTE.encode() not in blob
            assert b"causation" not in blob
    adopted = store.adopt_annotation(
        evidence_id="evidence-1",
        artifact_version=1,
        annotation_id=comment["annotation_id"],
        actor_principal_id="actor-owner",
        canonical_owner_principal_id="tenant-owner",
        tenant_id="tenant-owner",
        case_id="case-17",
        idempotency_key="adopt-1",
        expected_annotation_revision=span["annotation_revision"],
        key=KEY,
        key_id="key-17",
        adopt=True,
        display_role="admin",
    )
    assert adopted["adopted"] is True
    assert adopted["record_type"] == "note"
    assert adopted["adopted_as_evidence"] is False
    assert adopted["claim_element"] == ""
    assert adopted["establishes_causation"] is False
    with pytest.raises(BoundPrivateRecordError) as implied:
        store.adopt_annotation(
            evidence_id="evidence-1",
            artifact_version=1,
            annotation_id=comment["annotation_id"],
            actor_principal_id="actor-owner",
            canonical_owner_principal_id="tenant-owner",
            tenant_id="tenant-owner",
            case_id="case-17",
            idempotency_key="adopt-2",
            expected_annotation_revision=adopted["annotation_revision"],
            key=KEY,
            key_id="key-17",
            adopt=False,
        )
    assert implied.value.code == "adoption_requires_explicit_action"


def test_http_annotations_follow_actor_version_and_do_not_mint_evidence(tmp_path):
    world = _ready(tmp_path)
    case = world.case
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        evidence = _receive(client, case, csrf)
        before = _ids(client, case)
        created = _post(client, case, csrf, _annotation_body(case, evidence["evidence_id"]))
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["actor_principal_id"] == world.owner.principal_id
        assert body["canonical_owner_principal_id"] == case.tenant_id
        assert body["actor_is_canonical_owner"] is False
        assert body["display_role_authoritative"] is False
        assert body["adopted"] is False
        assert body["record_type"] == "note"
        assert body["claim_element"] == ""
        assert body["claim_element_is_causation"] is False
        assert body["synthesized_evidence"] is False
        assert body["evidence_ids"] == before
        assert _ids(client, case) == before
        assert world.backend.contains(NOTE.encode()) is False

        replay = _post(client, case, csrf, _annotation_body(case, evidence["evidence_id"]))
        assert replay.status_code == 200, replay.text
        assert replay.json()["annotation_id"] == body["annotation_id"]
        assert replay.json()["idempotent_replay"] is True

        stale = _post(client, case, csrf, _annotation_body(
            case, evidence["evidence_id"], idempotency_key="ux17-second", note="second note",
        ))
        assert stale.status_code == 409
        assert stale.json()["error"] == "revision_conflict"

        labeled = _post(client, case, csrf, _annotation_body(
            case, evidence["evidence_id"], kind="label", note="", label=LABEL,
            idempotency_key="ux17-label", expected_annotation_revision=body["annotation_revision"],
        ))
        assert labeled.status_code == 201, labeled.text
        span = _post(client, case, csrf, _annotation_body(
            case, evidence["evidence_id"], kind="page_span", note="span note", page=1,
            span_start=0, span_end=2, idempotency_key="ux17-span",
            expected_annotation_revision=labeled.json()["annotation_revision"],
        ))
        assert span.status_code == 201, span.text
        assert span.json()["anchor"] == "page-1-span-0-2"
        assert span.json()["artifact_version"] == 1

        listed = client.get(
            "/api/cases/evidence/annotations",
            headers=_composed_headers(case),
            params={
                "tenant_id": case.tenant_id,
                "case_id": case.case_id,
                "resource_id": case.resource_id,
                "evidence_id": evidence["evidence_id"],
                "artifact_version": "1",
                "expected_case_revision": str(case.revision),
            },
        )
        assert listed.status_code == 200, listed.text
        kinds = {item["kind"] for item in listed.json()["items"]}
        assert kinds == {"comment", "label", "page_span"}
        assert all(item["adopted"] is False for item in listed.json()["items"])

        smuggled = _post(client, case, csrf, _annotation_body(
            case, evidence["evidence_id"], content_base64=base64.b64encode(b"forged document").decode("ascii"),
            idempotency_key="ux17-forge", expected_annotation_revision=span.json()["annotation_revision"],
        ))
        assert smuggled.status_code == 400
        assert smuggled.json()["error"] == "content_rejected"
        assert _ids(client, case) == before

        implied = client.post(
            "/api/cases/evidence/annotations/adopt",
            headers=_composed_headers(case, csrf),
            json=_annotation_body(
                case, evidence["evidence_id"], annotation_id=body["annotation_id"],
                idempotency_key="ux17-adopt-implied", adopt=False,
                expected_annotation_revision=span.json()["annotation_revision"],
            ),
        )
        assert implied.status_code == 400
        adopted = client.post(
            "/api/cases/evidence/annotations/adopt",
            headers=_composed_headers(case, csrf),
            json=_annotation_body(
                case, evidence["evidence_id"], annotation_id=body["annotation_id"],
                idempotency_key="ux17-adopt", adopt=True,
                expected_annotation_revision=span.json()["annotation_revision"],
                display_role="lawyer",
            ),
        )
        assert adopted.status_code == 201, adopted.text
        assert adopted.json()["adopted"] is True
        assert adopted.json()["record_type"] == "note"
        assert adopted.json()["adopted_as_evidence"] is False
        assert adopted.json()["claim_element"] == ""
        assert adopted.json()["synthesized_evidence"] is False
        assert adopted.json()["actor_principal_id"] == world.owner.principal_id
        assert _ids(client, case) == before

        stale_case = _post(client, case, csrf, _annotation_body(
            case, evidence["evidence_id"], expected_case_revision=case.revision + 9,
            idempotency_key="ux17-stale-case", note="late note",
            expected_annotation_revision=adopted.json()["annotation_revision"],
        ))
        assert stale_case.status_code == 409

        other = world.cases.create_case(actor_principal_id=world.owner.principal_id)
        crossed = _post(client, case, csrf, _annotation_body(
            case, evidence["evidence_id"], case_id=other.case_id, tenant_id=other.tenant_id,
            resource_id=other.resource_id, expected_case_revision=other.revision,
            idempotency_key="ux17-cross",
        ))
        assert crossed.status_code == 403
        assert _ids(client, case) == before


def test_display_role_does_not_authorize_another_actor(tmp_path):
    world = _ready(tmp_path)
    case = world.case
    with TestClient(world.app, base_url="https://testserver") as client:
        owner_csrf = _composed_login(client)
        evidence = _receive(client, case, owner_csrf)
        client.post("/api/complaint-workspace/auth/logout", headers={"x-csrf-token": owner_csrf})
        lawyer_csrf = _composed_login(client, "synthetic-lawyer-credential")
        denied = _post(client, case, lawyer_csrf, _annotation_body(
            case, evidence["evidence_id"], display_role="owner",
        ))
        assert denied.status_code == 403
        assert denied.json()["error"] in {"not_owner", "selector_rejected", "key_unavailable"}
        listed = client.get(
            "/api/cases/evidence/annotations",
            headers=_composed_headers(case),
            params={
                "tenant_id": case.tenant_id,
                "case_id": case.case_id,
                "resource_id": case.resource_id,
                "evidence_id": evidence["evidence_id"],
                "artifact_version": "1",
                "expected_case_revision": str(case.revision),
                "display_role": "owner",
            },
        )
        assert listed.status_code == 403
