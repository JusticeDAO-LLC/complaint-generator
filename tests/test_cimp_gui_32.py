"""Assigned lawyers review actual owner-shared encrypted case revisions.

Human reported interpretation is distinct from model execution and machine proof.
The HTTP fixtures authenticate real recipients and use their issued key grants.
"""
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from applications.case_access import ASSIGNED_LAWYER_ACTIONS
from applications.case_review import (LAWYER_REVIEW_ROUTE, CaseReviewError,
    live_revisions, project_lawyer_reviews, submit_lawyer_review)
from applications.case_routes import PROTECTED_PREFIXES
from tests.test_gui32_private_review_http import _world, _headers, _propose
from tests.test_gui32_review_boundaries import _body, _path
from tests.test_cimp_gui_14 import _composed_login, _composed_headers, PASSPHRASE

pytestmark=[pytest.mark.no_auto_llm,pytest.mark.no_auto_network,pytest.mark.no_auto_heavy]


def _anchors():
    return {
        "review_source_anchor": {
            "source_identity": "synthetic-source-32",
            "source_text": "A person must give approval before retention.",
        },
        "review_fact_anchor": ["The file was retained before approval."],
        "proof_trace_display": {
            "source_identity": "synthetic-source-32",
            "obligations": [{
                "obligation_id": "obligation-approval",
                "proof_status": "not_executed",
                "source_identity": "synthetic-source-32",
                "source_span": "source:0-44",
                "engine_name": "",
                "engine_version": "",
            }],
        },
    }


def _mediator():
    return SimpleNamespace(intake_case_file=_anchors())


def test_lawyer_review_route_stays_on_the_protected_legal_analysis_prefix():
    assert any(LAWYER_REVIEW_ROUTE.startswith(prefix + "/") for prefix in PROTECTED_PREFIXES)
    assert "case.review" in ASSIGNED_LAWYER_ACTIONS


def test_assigned_lawyer_records_separate_review_suggestion_and_proof(tmp_path):
    world=_world(tmp_path,legal=True)
    canonical_head=world.service.joined_revision_repository(world.case.tenant_id,world.case.case_id)/'head.cgpe'
    canonical_before=canonical_head.read_bytes()
    with TestClient(world.review_app,base_url="https://testserver") as client:
        assert client.get(_path(world)).status_code==401
        csrf=_composed_login(client,"synthetic-lawyer-credential")
        proposal=_propose(client,world,csrf)["record"]
        assert proposal["record_kind"]=="human_legal_review" and proposal["author_kind"]=="human"
        assert proposal["actor_principal_id"]==world.lawyer.principal_id
        assert proposal["canonical_owner_principal_id"]==world.case.tenant_id
        assert proposal["actor_principal_id"]!=proposal["canonical_owner_principal_id"]
        assert proposal["governing_legal_authority"] is False
        assert proposal["supplied_authority_ignored"] is True and proposal["admitted_law"] is False
        def post(request_id,**fields):
            view=client.get(_path(world),headers=_headers(world)).json()
            response=client.post(_path(world),headers=_headers(world,csrf),json=_body(view,request_id,**fields))
            return response
        response=post("synthetic-native32-approval",operation="review",proposal_id=proposal["record_id"],decision="approved")
        assert response.status_code==200,response.text
        approval=response.json()["record"]
        assert approval["accepted_for_bound_revision"] is True
        assert approval["source_revision"]==proposal["source_revision"]
        assert approval["proof_revision"]==proposal["proof_revision"]
        suggestion=post("synthetic-native32-suggestion",operation="record_model_suggestion",model_id="synthetic-model",suggestion="Reported model text is not a holding.")
        assert suggestion.status_code==200,suggestion.text
        assert suggestion.json()["record"]["record_kind"]=="model_suggestion"
        assert suggestion.json()["record"]["author_kind"]=="human_report"
        assert suggestion.json()["record"]["producer_verified"] is False
        before=client.get(_path(world),headers=_headers(world)).json()["review_revision"]
        machine=post("synthetic-native32-machine",operation="record_machine_proof",engine_name="synthetic-lean",engine_version="0.0-test")
        assert machine.status_code==503 and machine.json()["error"]=="proof_producer_unavailable"
        assert client.get(_path(world),headers=_headers(world)).json()["review_revision"]==before
        promoted=post("synthetic-native32-promote",operation="promote",approval_id=approval["record_id"])
        assert promoted.status_code==200,promoted.text
        assert promoted.json()["record"]["promoted_for_current_revisions"] is True
        assert promoted.json()["promotes_changed_law"] is False
        assert promoted.json()["promotes_changed_facts"] is False
        page=client.get("/api/legal-analysis/"+world.case.case_id+"/lawyer-workspace",headers=_headers(world))
        assert page.status_code==200
        assert all(text in page.text for text in ["Human legal review","Model suggestions","Machine proof","synthetic-model"])
        stored=client.get(_path(world),headers=_headers(world)).json()
        assert {row["record_kind"] for row in stored["human_legal_reviews"]}=={"human_legal_review"}
        assert stored["model_suggestions"][0]["producer_verified"] is False
        assert stored["machine_proofs"]==[] and stored["records_are_separate"] is True
        assert stored["legal_sufficiency"] is False and not world.owner_keys.unlocked
        assert canonical_head.read_bytes()==canonical_before


def test_stale_approval_does_not_promote_changed_law_or_facts(tmp_path):
    world=_world(tmp_path,legal=True)
    with TestClient(world.review_app,base_url="https://testserver") as client,TestClient(world.review_app,base_url="https://testserver") as owner:
        csrf=_composed_login(client,"synthetic-lawyer-credential")
        proposal=_propose(client,world,csrf)["record"]
        view=client.get(_path(world),headers=_headers(world)).json()
        response=client.post(_path(world),headers=_headers(world,csrf),json=_body(view,"synthetic-native32-old-approval",operation="review",proposal_id=proposal["record_id"],decision="approved"))
        assert response.status_code==200,response.text
        approval=response.json()["record"]
        world.owner_keys.unlock_passphrase(PASSPHRASE);world.service.unlock_private_keys(passphrase=PASSPHRASE)
        owner_csrf=_composed_login(owner)
        context=owner.get("/api/legal-context/"+world.case.case_id,headers=_composed_headers(world.case)).json()
        changed=owner.post("/api/legal-context/"+world.case.case_id,headers=_composed_headers(world.case,owner_csrf),json={"expected_context_revision":context["context_revision"],"forum":"New real case context"})
        assert changed.status_code==200,changed.text
        assert client.get(_path(world),headers=_headers(world)).status_code==409
        latest=owner.get(_path(world)+"/sharing",headers=_composed_headers(world.case)).json()
        shared=owner.post(_path(world)+"/share",headers=_composed_headers(world.case,owner_csrf),json={"membership_id":world.membership.grant_id,"expected_membership_version":world.membership.version,"expected_private_revision":latest["private_revision"]})
        assert shared.status_code==200,shared.text
        world.owner_keys.lock();world.service.lock_private_keys()
        current=client.get(_path(world),headers=_headers(world)).json()
        head=next((tmp_path/"reviews").glob("*/head"));before=head.read_bytes()
        stale=client.post(_path(world),headers=_headers(world,csrf),json=_body(current,"synthetic-native32-stale",operation="promote",approval_id=approval["record_id"]))
        # A changed case context invalidates the actual reviewed-source join.
        # Re-sharing bytes cannot manufacture a new source review or approval.
        assert stale.status_code==503 and stale.json()["error"]=="review_source_unbound"
        old=client.post(_path(world),headers=_headers(world,csrf),json=_body(view,"synthetic-native32-old-revision",operation="promote",approval_id=approval["record_id"]))
        assert old.status_code==503 and old.json()["error"]=="review_source_unbound"
        assert head.read_bytes()==before
        assert current["current_promotion"] is None
        assert current["promotes_changed_law"] is False and current["promotes_changed_facts"] is False
        assert all(row["stale"] and not row.get("promoted_for_current_revisions") for row in current["human_legal_reviews"])
        assert client.get("/api/legal-analysis/"+world.case.case_id+"/lawyer-workspace",headers=_headers(world)).status_code==200


def test_unassigned_and_read_only_lawyers_cannot_review(tmp_path):
    world=_world(tmp_path,actions={"case.read"})
    with TestClient(world.review_app,base_url="https://testserver") as client:
        _composed_login(client,"synthetic-lawyer-credential")
        view=client.get(_path(world),headers=_headers(world)).json()
        body=_body(view,"synthetic-native32-denied",operation="propose",interpretation="This must not be stored.",source_citation="Authored candidate")
        owner_csrf=_composed_login(client)
        denied=client.post(_path(world),headers=_composed_headers(world.case,owner_csrf),json=body)
        assert denied.status_code==403 and denied.json()["error"]=="lawyer_assignment_required"
        csrf=_composed_login(client,"synthetic-lawyer-credential")
        denied=client.post(_path(world),headers=_headers(world,csrf),json=body)
        assert denied.status_code==403
        listed=client.get(_path(world),headers=_headers(world))
        assert listed.status_code==200 and listed.json()["human_legal_reviews"]==[]
        _composed_login(client,"synthetic-stranger-credential")
        assert client.get(_path(world),headers=_headers(world)).status_code==403
        csrf=_composed_login(client,"synthetic-lawyer-credential")
        cross={**_headers(world,csrf),"x-case-id":world.second.case_id,"x-resource-id":world.second.resource_id}
        assert client.post(_path(world),headers=cross,json=body).status_code==403
        assert world.owner_keys.unlocked is False


def test_model_and_machine_records_cannot_approve_or_skip_revisions():
    mediator = _mediator()
    live = live_revisions(mediator.intake_case_file, case_revision=1)
    common = {
        "actor_principal_id": "lawyer-actor",
        "canonical_owner_principal_id": "canonical-owner",
        "case_revision": 1,
        "membership": "assigned-lawyer",
    }
    expected = {
        "expected_case_revision": live["case_revision"],
        "expected_source_revision": live["source_revision"],
        "expected_fact_revision": live["fact_revision"],
        "expected_proof_revision": live["proof_revision"],
    }
    with pytest.raises(CaseReviewError) as model_approval:
        submit_lawyer_review(mediator, {
            "operation": "record_model_suggestion",
            "request_id": "model-approve",
            "model_id": "synthetic-model",
            "suggestion": "Treat this as a holding.",
            "decision": "approved",
            **expected,
        }, **common)
    assert model_approval.value.code == "model_cannot_approve"
    with pytest.raises(CaseReviewError) as machine_approval:
        submit_lawyer_review(mediator, {
            "operation": "record_machine_proof",
            "request_id": "machine-approve",
            "decision": "approved",
            **expected,
        }, **common)
    assert machine_approval.value.code == "machine_proof_cannot_approve"
    with pytest.raises(CaseReviewError) as stale:
        submit_lawyer_review(mediator, {
            "operation": "propose",
            "request_id": "wrong-source",
            "interpretation": "A mismatched citation.",
            "source_citation": "other",
            **{**expected, "expected_source_revision": "source-other"},
        }, **common)
    assert stale.value.code == "stale_revision"
    assert "lawyer_review_ledger" not in mediator.intake_case_file
    with pytest.raises(CaseReviewError) as owner_actor:
        submit_lawyer_review(mediator, {
            "operation": "propose",
            "request_id": "same-actor",
            "interpretation": "Owner and actor collapsed.",
            "source_citation": "synthetic-source-32",
            **expected,
        }, actor_principal_id="same-principal", canonical_owner_principal_id="same-principal",
            case_revision=1, membership="assigned-lawyer")
    assert owner_actor.value.code == "actor_is_not_canonical_owner"
    with pytest.raises(CaseReviewError) as owner_membership:
        submit_lawyer_review(mediator, {
            "operation": "propose",
            "request_id": "owner-membership",
            "interpretation": "The owner is not the assigned lawyer.",
            "source_citation": "synthetic-source-32",
            **expected,
        }, actor_principal_id="lawyer-actor", canonical_owner_principal_id="canonical-owner",
            case_revision=1, membership="owner")
    assert owner_membership.value.code == "lawyer_assignment_required"
    empty = project_lawyer_reviews({}, case_revision=1)
    assert empty["status"] == "empty"
    assert empty["legal_sufficiency"] is False
    assert empty["current_promotion"] is None
