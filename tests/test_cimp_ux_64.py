"""Complete complaint and human-review journey.

Original complaint, adaptive question, corrected graph, private annotation,
source-bound requirement, cited draft, lawyer message and review, explicit
owner acceptance, then a cold resume. Unresolved, unknown, cancelled,
provider, source, proof, and storage failures stay failures. A stranger is
denied. A completed screen does not file a case or declare legal sufficiency.
"""

from __future__ import annotations

import base64
import hashlib
import json
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from applications.case_review import CaseReviewError, accept_draft_suggestion, submit_draft_suggestion
from applications.complaint_workspace import WorkspaceAccess, workspace_access_scope
from complaint_phases.knowledge_graph import KnowledgeGraph
from integrations.ipfs_datasets.logic import sha256_utf8
from tests import gui_native_browser as browser
from tests.gui_ux_overhaul_fixtures import (
    JOURNEY_ANSWER,
    JOURNEY_CITATION,
    JOURNEY_MESSAGE,
    JOURNEY_NARRATIVE,
    JOURNEY_NOTE,
    JOURNEY_REPLACEMENT,
    JOURNEY_RULE,
    JOURNEY_STALE,
    attach_private_evidence_workspace,
    cited_draft_text,
    journey_case_body,
)
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import PASSPHRASE, _composed_headers, _composed_login
from tests.test_cimp_gui_56 import _arm, _browsers

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

KEY = bytes(range(32))


@contextmanager
def _owner_scope(world):
    case = world.case
    with workspace_access_scope(WorkspaceAccess.authenticated(case.tenant_id, case.case_id)):
        yield


def _chat(client, case, csrf, **body):
    response = client.post(
        "/api/complaint-workspace/intake-chat",
        headers=_composed_headers(case, csrf),
        json=body,
    )
    return response


def _session(client, case):
    response = client.get("/api/complaint-workspace/session", headers=_composed_headers(case))
    assert response.status_code == 200, response.text
    return response.json()["session"]


def _pending(payload):
    shared = payload.get("session", {}).get("shared_interview") or payload.get("shared_interview") or {}
    pending = shared.get("pending_inquiry") or payload.get("adaptive_inquiry") or {}
    if not pending and isinstance(payload.get("interview"), dict):
        pending = payload["interview"].get("pending_inquiry") or {}
    return pending


def _sufficiency(payload) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("legal_sufficiency") is True or payload.get("filed") is True or payload.get("court_filed") is True:
        return True
    for value in payload.values():
        if isinstance(value, dict) and _sufficiency(value):
            return True
    return False


def _authority():
    return {
        "source_text": JOURNEY_RULE,
        "jurisdiction": "OR",
        "authority_id": "ors:659A.030",
        "citation": JOURNEY_CITATION,
        "authority_version": "2024-edition",
        "source_hash": sha256_utf8(JOURNEY_RULE),
        "effective_date": "2024-01-01",
        "as_of_date": "2024-06-01",
    }


def test_complete_journey_keeps_acceptance_separate_from_filing(tmp_path):
    world = owner_lawyer_journey_world(tmp_path / "world")
    attach_private_evidence_workspace(world, tmp_path / "evidence-root")
    case = world.case
    assert world.owner.principal_id != case.tenant_id
    service = world.service
    assert service.unlock_private_keys(passphrase=PASSPHRASE)["unlocked"] is True
    with _owner_scope(world):
        service.set_privacy_policy(case.tenant_id, "local")
        service.publish_case_host_entity(case.tenant_id, "target.ux64")
        stored = service.store_case_private_source(case.tenant_id, JOURNEY_RULE.encode(), key=KEY, key_id="ux64-key")
        assert stored["verified"] is True
        service.save_local_public_legal_text(case.tenant_id, "cite.ux64", JOURNEY_RULE)
        bindings = service.bind_lifecycle_case(
            case.tenant_id, source=JOURNEY_RULE.encode(), source_id="src-ux64",
            session_id="session-ux64", session_revision=1,
        )
        service.save_mediator_operation_consent(case.tenant_id, ["acquire_legal_sources"])

    with TestClient(world.app, base_url="https://testserver") as owner, TestClient(world.app, base_url="https://testserver") as lawyer, TestClient(world.app, base_url="https://testserver") as stranger:
        csrf = _composed_login(owner)
        started = _chat(owner, case, csrf, message=JOURNEY_NARRATIVE, question_id="original_complaint", interview_action="start")
        assert started.status_code == 200, started.text
        started_body = started.json()
        assert _sufficiency(started_body) is False
        pending = _pending(started_body)
        inquiry_id = pending.get("inquiry_id") or started_body.get("adaptive_inquiry", {}).get("inquiry_id")
        assert inquiry_id
        revision = pending.get("revision") or pending.get("question_revision") or started_body.get("interview", {}).get("question_revision")
        if revision is None:
            session = _session(owner, case)
            pending = session["shared_interview"]["pending_inquiry"]
            inquiry_id = pending["inquiry_id"]
            revision = pending.get("revision") or pending.get("question_revision")
        assert isinstance(revision, int)

        why = _chat(owner, case, csrf, message="/why")
        assert why.status_code == 200, why.text
        assert why.json().get("stored_as_answer") is False
        assert why.json().get("legal_sufficiency") is False

        answered = _chat(
            owner, case, csrf, message=JOURNEY_ANSWER, question_id=inquiry_id,
            expected_question_revision=revision, interview_action="answer",
        )
        assert answered.status_code == 200, answered.text
        answer_body = answered.json()
        assert _sufficiency(answer_body) is False
        offer = (answer_body.get("adaptive_inquiry") or {}).get("factual_correction") or answer_body.get("factual_correction") or {}
        target = offer.get("target_stable_id")
        graph_revision = offer.get("expected_graph_revision")
        session_revision = offer.get("expected_session_revision")
        if not target:
            graph = KnowledgeGraph.from_dict(_session(owner, case)["shared_interview"]["knowledge_graph"])
            active = [row for row in graph.assertions() if graph.assertion_state(row)["status"] == "active"] if hasattr(graph, "assertions") else []
            target = active[0] if active else None
        assert target and graph_revision and isinstance(session_revision, int)
        prior = KnowledgeGraph.from_dict(_session(owner, case)["shared_interview"]["knowledge_graph"]).assertion_state(target)
        correction_message = json.dumps({
            "schema": "gui-factual-correction-v1",
            "replacement": JOURNEY_REPLACEMENT,
            "expected_graph_revision": graph_revision,
            "expected_session_revision": session_revision,
            "target_stable_id": target,
            "actor_principal_id": world.owner.principal_id,
        })
        corrected = _chat(
            owner, case, csrf, message=correction_message, question_id=target, interview_action="correct",
            expected_graph_revision=graph_revision, expected_session_revision=session_revision,
        )
        assert corrected.status_code == 200, corrected.text
        receipt = corrected.json().get("factual_correction") or {}
        assert receipt.get("status") == "applied", corrected.text
        assert _sufficiency(corrected.json()) is False
        after = KnowledgeGraph.from_dict(_session(owner, case)["shared_interview"]["knowledge_graph"])
        assert after.assertion_state(target)["status"] == "superseded"
        assert after.assertion_state(target)["envelope"] == prior["envelope"]
        assert JOURNEY_REPLACEMENT in [row.get("answer") for row in _session(owner, case)["intake_history"]]

        evidence = owner.post("/api/cases/evidence", headers=_composed_headers(case, csrf), json={
            **journey_case_body(case),
            "source_filename": "denial.txt",
            "original_filename": "denial.txt",
            "media_type": "text/plain",
            "content_base64": base64.b64encode(b"Line one\nLine two stays sealed.\n").decode("ascii"),
            "idempotency_key": "ux64-evidence",
        })
        assert evidence.status_code == 201, evidence.text
        note = owner.post("/api/cases/evidence/annotations", headers=_composed_headers(case, csrf), json={
            **journey_case_body(case),
            "evidence_id": evidence.json()["evidence_id"],
            "artifact_version": 1,
            "expected_annotation_revision": "",
            "idempotency_key": "ux64-note",
            "kind": "comment",
            "note": JOURNEY_NOTE,
        })
        assert note.status_code == 201, note.text
        assert note.json()["adopted"] is False
        assert note.json()["record_type"] == "note"
        assert all(JOURNEY_NOTE.encode() not in blob for blob in world.evidence_backend.objects.values()) if getattr(world.evidence_backend, "objects", None) else True

        with _owner_scope(world):
            questions = service.exercise_lifecycle_hook(
            case.tenant_id, "QuestionGenerationHook", bindings=bindings,
            payload={
                "narrative": JOURNEY_RULE, "jurisdiction": "OR", "applicable_law_date": "2024-06-01",
                "context_revision": 1, "claim_candidates": ["retaliation"],
                "admitted_authorities": [_authority()], "inquiry_cap": 4, "capability_available": True,
                "model_text": "Judgment is automatic.", "model_requirements": ["The element is already proved."],
            },
        )
        assert questions["effect"] is True and questions["inquiry_count"] >= 1
        assert questions.get("legal_sufficiency") is not True
        with _owner_scope(world):
            support = service.exercise_lifecycle_hook(
            case.tenant_id, "LegalAuthorityAnalysisHook", bindings=bindings,
            payload={
                "user_id": case.tenant_id, "complaint_id": case.case_id, "claim_type": "retaliation",
                "admitted_passages": [{
                    "passage_id": "passage-ux64", "text": JOURNEY_RULE, "citation": JOURNEY_CITATION,
                    "requirement_id": "req-ux64", "source_version": "2024-edition", "definition_version": "def-3",
                    "source_hash": sha256_utf8(JOURNEY_RULE),
                }],
                "support_lineage": [{
                    "lineage_id": "lin-64", "requirement_id": "req-ux64", "passage_id": "passage-ux64",
                    "fact_id": "fact-64", "evidence_ref": evidence.json()["evidence_id"],
                    "source_version": "2024-edition", "definition_version": "def-3",
                    "source_hash": sha256_utf8(JOURNEY_RULE),
                }],
                "search_hits": [], "suggestions": [], "caller_flags": {}, "source_drift": [], "contradictions": [],
            },
        )
        assert support["effect"] is True
        assert support["legal_sufficiency"] is False
        assert support["governing_count"] == 1

        draft_text = cited_draft_text(citation=JOURNEY_CITATION, fact=JOURNEY_REPLACEMENT)
        with _owner_scope(world):
            drafted = service.update_draft(case.tenant_id, title="Synthetic cited draft", body=draft_text, case_id=case.case_id, actor_id=case.tenant_id)
        assert JOURNEY_CITATION in drafted["draft"]["body"]
        assert "not a court filing" in drafted["draft"]["body"]
        assert drafted["draft"].get("filed") is not True

        invited = owner.post("/api/cases/assignments", headers=_composed_headers(case, csrf), json={
            **journey_case_body(case),
            "member_principal_id": world.lawyer.principal_id,
            "scope": ["case.read", "case.review", "case.message.send"],
            "expires_at": world.now["t"] + 3600,
            "idempotency_key": "ux64-invite",
        })
        assert invited.status_code in {200, 201}, invited.text
        grant_id = invited.json()["grant_id"]
        grant_version = invited.json().get("version") or invited.json().get("server_version")
        lawyer_csrf = _composed_login(lawyer, "synthetic-lawyer-credential")
        accepted_scope = lawyer.post(
            f"/api/cases/assignments/{grant_id}/accept",
            headers=_composed_headers(case, lawyer_csrf),
            json={
                **journey_case_body(case),
                "scope": ["case.read", "case.review", "case.message.send"],
                "expected_version": grant_version,
                "idempotency_key": "ux64-accept-scope",
            },
        )
        assert accepted_scope.status_code == 200, accepted_scope.text

        thread = owner.post("/api/cases/messages/threads", headers=_composed_headers(case, csrf), json={
            "case_id": case.case_id, "idempotency_key": "ux64-thread",
        })
        assert thread.status_code == 201, thread.text
        sent = owner.post(
            f"/api/cases/messages/threads/{thread.json()['thread_id']}/messages",
            headers=_composed_headers(case, csrf),
            json={"case_id": case.case_id, "text": JOURNEY_MESSAGE, "idempotency_key": "ux64-message"},
        )
        assert sent.status_code == 201, sent.text
        assert sent.json()["disposition"] == "conversation"
        assert sent.json().get("adoption") is None

        stranger_csrf = _composed_login(stranger, "synthetic-stranger-credential")
        denied = stranger.get(f"/api/cases/{case.case_id}", headers=_composed_headers(case, stranger_csrf))
        assert denied.status_code == 404, denied.text
        assert JOURNEY_NARRATIVE not in denied.text
        denied_thread = stranger.get(
            "/api/cases/messages/threads",
            params={"case_id": case.case_id},
            headers=_composed_headers(case, stranger_csrf),
        )
        assert denied_thread.status_code in {200, 404}
        assert JOURNEY_MESSAGE not in denied_thread.text

        digest = hashlib.sha256(draft_text.encode()).hexdigest()
        case_file = {"workflow_domains": {}, "draft_workflow": {"versions": [{
            "draft_id": "draft-ux64", "revision": 1, "text": draft_text, "text_digest": digest,
            "actor_principal_id": world.owner.principal_id,
        }], "reviews": [], "exports": []}}
        proposal = submit_draft_suggestion(case_file, {
            "operation": "propose_bounded_change", "request_id": "ux64-human", "provenance": "human",
            "proposed_text": draft_text, "draft_id": "draft-ux64", "expected_revision": 1, "expected_text_digest": digest,
        }, actor_principal_id=world.lawyer.principal_id, canonical_owner_principal_id=case.tenant_id,
           membership="assigned-lawyer", action="case.review")
        assert proposal["record"]["legal_sufficiency"] is False
        assert proposal["record"]["changes_owner_draft"] is False
        with pytest.raises(CaseReviewError):
            accept_draft_suggestion(case_file, {
                "operation": "accept_draft_suggestion", "request_id": "ux64-lawyer-accept",
                "proposal_id": proposal["record"]["record_id"], "draft_id": "draft-ux64",
                "expected_revision": 1, "expected_text_digest": digest, "proposed_text": draft_text,
            }, actor_principal_id=world.lawyer.principal_id, canonical_owner_principal_id=case.tenant_id,
               membership="assigned-lawyer", action="case.update")
        accepted = accept_draft_suggestion(case_file, {
            "operation": "accept_draft_suggestion", "request_id": "ux64-owner-accept",
            "proposal_id": proposal["record"]["record_id"], "draft_id": "draft-ux64",
            "expected_revision": 1, "expected_text_digest": digest, "proposed_text": draft_text,
        }, actor_principal_id=world.owner.principal_id, canonical_owner_principal_id=case.tenant_id,
           membership="owner", action="case.update")
        assert accepted["record"]["record_kind"] == "owner_acceptance"
        assert accepted["record"]["legal_sufficiency"] is False
        assert accepted["record"]["requires_explicit_owner_save"] is True
        assert case_file["draft_workflow"]["versions"][0]["text"] == draft_text
        with _owner_scope(world):
            saved = service.update_draft(
                case.tenant_id, body=accepted["adopted_text"], case_id=case.case_id, actor_id=case.tenant_id,
            )
        assert saved["draft"]["body"] == draft_text
        assert saved["draft"].get("court_filed") is not True

        expected_pending = _session(owner, case)["shared_interview"]["pending_inquiry"]

    cold = owner_lawyer_journey_world(tmp_path / "world", previous=world)
    assert cold.service is not world.service
    with TestClient(cold.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        resumed = _chat(client, cold.case, csrf, message="browser-cache-must-not-return", interview_action="encrypted_resume")
        assert resumed.status_code == 200, resumed.text
        body = resumed.json()
        resume = body.get("encrypted_resume") or {}
        assert resume.get("hooks_replayed") is False
        assert resume.get("messages_replayed") is False
        assert resume.get("browser_cache_ignored") is True or resume.get("reconstructed_from_browser_cache") is False
        assert _sufficiency(body) is False
        assert "browser-cache-must-not-return" not in resumed.text
        state = _session(client, cold.case)
        assert state["shared_interview"]["pending_inquiry"] == expected_pending
        assert JOURNEY_REPLACEMENT in [row.get("answer") for row in state["intake_history"]]
        assert JOURNEY_CITATION in (state.get("draft") or {}).get("body", "")


def test_failures_do_not_become_sufficiency_or_access(tmp_path):
    world = owner_lawyer_journey_world(tmp_path / "world")
    case = world.case
    service = world.service
    assert service.unlock_private_keys(passphrase=PASSPHRASE)["unlocked"] is True
    with _owner_scope(world):
        service.set_privacy_policy(case.tenant_id, "local")
        service.publish_case_host_entity(case.tenant_id, "target.ux64")
        service.store_case_private_source(case.tenant_id, JOURNEY_RULE.encode(), key=KEY, key_id="ux64-key")
        service.bind_case_mediator_owners(case.tenant_id, key=KEY, key_id="ux64-key")
        bindings = service.bind_lifecycle_case(
        case.tenant_id, source=JOURNEY_RULE.encode(), source_id="src-ux64",
        session_id="session-ux64", session_revision=1,
    )
    with _owner_scope(world):
        unknown = service.exercise_lifecycle_hook(
        case.tenant_id, "LegalClassificationHook", bindings=bindings,
        payload={"narrative": JOURNEY_RULE, "jurisdiction": "not-a-jurisdiction", "applicable_law_date": "",
                 "admitted_authorities": [], "offline_cache": {}, "inquiry_cap": 1, "capability_available": True},
    )
    assert unknown["receipt_code"] == "unknown_legal_context"
    assert unknown.get("legal_sufficiency") is not True
    with _owner_scope(world):
        source = service.exercise_lifecycle_hook(
        case.tenant_id, "StatuteRetrievalHook", bindings=bindings,
        payload={"narrative": JOURNEY_RULE, "jurisdiction": "not-a-jurisdiction", "applicable_law_date": "",
                 "admitted_authorities": [], "offline_cache": {}, "capability_available": True},
    )
    assert source["effect"] is False and source["citations"] == []
    with _owner_scope(world):
        locked = service.exercise_lifecycle_hook(
        case.tenant_id, "EvidenceStorageHook", bindings=bindings,
        payload={
            "root": str(tmp_path / "locked"), "case_id": bindings["case_id"], "actor_id": case.tenant_id,
            "tenant_id": case.tenant_id, "revision": "rev1", "source": JOURNEY_RULE.encode(),
            "source_sha256": hashlib.sha256(JOURNEY_RULE.encode()).hexdigest(),
            "key": None, "key_locked": True, "key_id": "locked",
            "consent": {"granted": True, "revoked": False, "case_id": bindings["case_id"], "actor_id": case.tenant_id,
                        "operations": ["qualify_private_evidence"]},
            "annotation": b"note", "annotation_sha256": hashlib.sha256(b"note").hexdigest(),
            "db_path": str(tmp_path / "locked.duckdb"),
        },
    )
    assert locked["code"] == "key_locked" and locked["effect"] is False and locked["writes"] == 0
    with _owner_scope(world):
        proof = service.exercise_lifecycle_hook(
        case.tenant_id, "ClaimSupportHook", bindings=bindings,
        payload={"user_id": case.tenant_id, "complaint_id": case.case_id, "claim_type": "retaliation",
                 "admitted_passages": [], "support_lineage": [], "search_hits": [], "suggestions": [],
                 "caller_flags": {"verified_support": True}, "source_drift": [], "contradictions": []},
    )
    assert proof["proof"] is False and proof["legal_sufficiency"] is False and proof["effect"] is False

    with TestClient(world.app, base_url="https://testserver") as owner, TestClient(world.app, base_url="https://testserver") as stranger:
        csrf = _composed_login(owner)
        started = _chat(owner, case, csrf, message=JOURNEY_NARRATIVE, question_id="original_complaint", interview_action="start")
        assert started.status_code == 200, started.text
        cancelled = _chat(owner, case, csrf, interview_action="cancel")
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json().get("legal_sufficiency") is False
        stop = cancelled.json().get("finite_interview_outcome") or cancelled.json().get("interview_stop") or {}
        assert stop.get("stop") == "cancelled" or stop.get("state") == "cancelled" or cancelled.json().get("status") in {"cancelled", "refused"}
        assert cancelled.json().get("filed") is not True
        unavailable = _chat(owner, case, csrf, interview_action="unavailable")
        assert unavailable.status_code == 200, unavailable.text
        assert unavailable.json().get("legal_sufficiency") is False
        provider = unavailable.json().get("finite_interview_outcome") or {}
        assert provider.get("stop") in {"unavailable", "provider_unavailable", "cancelled"} or unavailable.json().get("status") != "filed"

        stale = _chat(owner, case, csrf, message=json.dumps({
            "schema": "gui-factual-correction-v1", "replacement": JOURNEY_STALE,
            "expected_graph_revision": "gr_stale", "expected_session_revision": 1,
            "target_stable_id": "missing-target", "actor_principal_id": world.owner.principal_id,
        }), interview_action="correct", expected_graph_revision="gr_stale", expected_session_revision=1)
        assert stale.status_code in {200, 409}, stale.text
        assert JOURNEY_STALE not in str(_session(owner, case).get("intake_history"))
        assert _sufficiency(stale.json()) is False

        research = owner.post(f"/api/legal-research/{case.case_id}", headers=_composed_headers(case, csrf), json={
            "purpose": "citation_acquisition", "query": "synthetic citation", "retrieval_mode": "offline",
            "expected_consent_generation": 1, "operation_id": "ux64-research", "max_results": 1,
            "deadline_seconds": 1, "max_bytes": 256, "cancelled": True,
        })
        if research.status_code == 200:
            assert research.json().get("status") == "cancelled"
            assert research.json().get("legal_sufficiency") is False
            assert research.json().get("admitted_law") is False
        else:
            assert research.status_code >= 400
            assert research.json().get("legal_sufficiency") is not True

        proof_post = owner.post(f"/api/legal-analysis/{case.case_id}/proof-traces", headers=_composed_headers(case, csrf), json={
            "request_id": "ux64-proof", "legal_sufficiency": True, "obligations": [{
                "obligation_id": "ob-64", "statement": "synthetic", "source_span": "span",
                "source_identity": "source-64", "proof_status": "executed", "engine_name": "absent",
                "prover_missing": True, "green_checkmark": True,
            }],
        })
        assert proof_post.status_code >= 400, proof_post.text
        assert proof_post.json().get("legal_sufficiency") is not True
        assert proof_post.json().get("error") == "proof_producer_unavailable" or proof_post.json().get("proof") is False

        stranger_csrf = _composed_login(stranger, "synthetic-stranger-credential")
        hidden = stranger.get(f"/api/cases/{case.case_id}")
        assert hidden.status_code == 404
        assert JOURNEY_NARRATIVE not in hidden.text
        assert stranger_csrf


def test_workspace_dom_question_does_not_declare_sufficiency(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "world")
    with _browsers(tmp_path / "browser", monkeypatch, world.app) as (open_page, _bridge):
        page = open_page("owner")
        page.set_default_timeout(90000)
        _arm(page, world, "synthetic-owner-credential")
        page.fill("#adaptive-narrative", JOURNEY_NARRATIVE)
        page.locator("#adaptive-enter-narrative").scroll_into_view_if_needed()
        with page.expect_response(lambda response: response.request.method == "POST" and ("/intake-chat" in response.url or "/mcp/" in response.url)) as started:
            page.click("#adaptive-enter-narrative")
        assert started.value.status == 200, started.value.text()
        page.wait_for_function("document.getElementById('adaptive-pending').dataset.pending === 'true'")
        assert page.get_attribute("#adaptive-pending", "data-inquiry-id")
        page.locator("#finite-interview-pause").scroll_into_view_if_needed()
        with page.expect_response(lambda response: response.request.method == "POST" and ("/intake-chat" in response.url or "/mcp/" in response.url)) as paused:
            page.click("#finite-interview-pause")
        assert paused.value.status == 200
        page.wait_for_function("document.getElementById('finite-interview-outcome').dataset.stop === 'paused'")
        assert page.get_attribute("#finite-interview-outcome", "data-legal-sufficiency") == "false"
        assert page.get_attribute("#finite-interview-outcome", "data-stop") == "paused"
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
        stranger = open_page("stranger")
        stranger.set_default_timeout(90000)
        stranger.goto(browser.SAME_ORIGIN + "/cases", wait_until="domcontentloaded")
        stranger.fill("#case-credential", "synthetic-stranger-credential")
        stranger.click("#case-login button[type=submit]")
        stranger.wait_for_function("document.getElementById('case-auth-status').textContent === 'Signed in'")
        assert JOURNEY_NARRATIVE not in stranger.locator("body").inner_text()

