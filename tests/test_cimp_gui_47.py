"""Review items stay typed until an authorized acceptance changes case state.

Tasks, comments, and proposals do not rewrite facts, answers, legal admissions,
or draft revisions. Acceptance compares the review revision and the target
revision, keeps dissent and prior text, and invalidates support bound to the
replaced revision.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.browser_sessions import (
    BrowserSessionConfiguration,
    BrowserSessionService,
    PrincipalStoreCredentialAdapter,
)
from applications.case_access import ASSIGNED_LAWYER_ACTIONS, CaseActionAuthorizer
from applications.case_directory import CaseDirectory
from applications.case_review import REVIEW_ITEMS_ROUTE, REVIEW_TRANSITIONS_ROUTE
from applications.case_routes import PROTECTED_PREFIXES, CaseHandlerRegistry, compose_case_routes
from applications.principal_store import PrincipalStore
from mediator.workflow_service import WorkflowActionService

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]


def _world(tmp_path):
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    owner = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    other = principals.install_server_role(role="lawyer")
    reader = principals.install_server_role(role="lawyer")
    cases = CaseDirectory(tmp_path / "cases", key=os.urandom(32), key_id="case-key")
    case = cases.create_case(actor_principal_id=owner.principal_id)
    authorizer = CaseActionAuthorizer(principals, cases)
    grant = authorizer.grant_assigned_lawyer(
        owner_principal_id=owner.principal_id,
        lawyer_principal_id=lawyer.principal_id,
        case_id=case.case_id,
        resource_id=case.resource_id,
        tenant_id=case.tenant_id,
        actions=frozenset({"case.read", "case.review"}),
        expected_case_revision=case.revision,
    )
    other_grant = authorizer.grant_assigned_lawyer(
        owner_principal_id=owner.principal_id,
        lawyer_principal_id=other.principal_id,
        case_id=case.case_id,
        resource_id=case.resource_id,
        tenant_id=case.tenant_id,
        actions=frozenset({"case.read", "case.review"}),
        expected_case_revision=case.revision,
    )
    read_grant = authorizer.grant_assigned_lawyer(
        owner_principal_id=owner.principal_id,
        lawyer_principal_id=reader.principal_id,
        case_id=case.case_id,
        resource_id=case.resource_id,
        tenant_id=case.tenant_id,
        actions=frozenset({"case.read"}),
        expected_case_revision=case.revision,
    )
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            "synthetic-lawyer-credential": lawyer.principal_id,
            "synthetic-other-credential": other.principal_id,
            "synthetic-reader-credential": reader.principal_id,
        }),
        signing_key=os.urandom(32),
        ttl_seconds=300,
    ))
    mediator = SimpleNamespace(intake_case_file={})
    handlers = CaseHandlerRegistry()
    handlers.bind(case, mediator=mediator, workspace_service=SimpleNamespace(case_id=case.case_id),
        authorize_delegated=lambda decision: decision.membership == "assigned-lawyer")
    app = FastAPI()
    compose_case_routes(app, authorizer=authorizer, browser_sessions=sessions, case_handlers=handlers,
        include_workspace=False, include_review=False, include_document=False)
    return SimpleNamespace(case=case, grant=grant, other_grant=other_grant, read_grant=read_grant,
        app=app, mediator=mediator, lawyer=lawyer, other=other)


def _headers(case, csrf, membership_revision):
    return {
        "x-tenant-id": case.tenant_id,
        "x-case-id": case.case_id,
        "x-resource-id": case.resource_id,
        "x-expected-revision": str(case.revision),
        "x-expected-membership-revision": str(membership_revision),
        "x-csrf-token": csrf,
    }


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _paths(case_id):
    return (
        f"/api/legal-analysis/{case_id}/review-items",
        f"/api/legal-analysis/{case_id}/review-transitions",
    )


def test_review_routes_require_case_review_on_the_legal_analysis_prefix():
    assert any(REVIEW_ITEMS_ROUTE.startswith(prefix + "/") for prefix in PROTECTED_PREFIXES)
    assert any(REVIEW_TRANSITIONS_ROUTE.startswith(prefix + "/") for prefix in PROTECTED_PREFIXES)
    assert "case.review" in ASSIGNED_LAWYER_ACTIONS
    assert "case.update" not in ASSIGNED_LAWYER_ACTIONS


def test_only_authorized_acceptance_updates_case_state_and_invalidates_support(tmp_path):
    """Mounted acceptance uses the encrypted proposal and real factual owner.

    The former namespace/cache fixture could report acceptance while the
    actual private KG stayed unchanged. Keep authority and invalidation checks
    on the canonical path, with unsupported domain owners explicitly refused.
    """
    from tests.test_gui47_private_acceptance import (
        test_public_review_acceptance_supersedes_private_fact_and_replays_without_another_commit,
        test_assigned_lawyer_cannot_adopt_with_unlocked_owner_keys,
        test_unimplemented_target_owners_refuse_instead_of_adopting_shadow_state,
    )
    test_public_review_acceptance_supersedes_private_fact_and_replays_without_another_commit(tmp_path / 'canonical')
    test_assigned_lawyer_cannot_adopt_with_unlocked_owner_keys(tmp_path / 'authority')
    for kind in ('legal_admission', 'draft_revision'):
        test_unimplemented_target_owners_refuse_instead_of_adopting_shadow_state(tmp_path / kind, kind)



def test_concurrent_acceptance_keeps_one_revision_and_dissent(tmp_path, monkeypatch):
    """One case CAS wins; an actual later dissent invalidates review CAS."""
    from tests.test_gui47_private_acceptance import (
        test_concurrent_acceptance_has_one_actual_factual_commit,
        test_real_review_cas_change_during_correction_prevents_canonical_publication,
    )
    with monkeypatch.context() as scoped:
        test_concurrent_acceptance_has_one_actual_factual_commit(tmp_path / 'concurrent', scoped)
    with monkeypatch.context() as scoped:
        test_real_review_cas_change_during_correction_prevents_canonical_publication(tmp_path / 'dissent', scoped)



def test_direct_transition_refuses_comments_and_replay_mismatch(tmp_path):
    mediator = SimpleNamespace(intake_case_file={})
    service = WorkflowActionService(mediator)
    common = dict(
        case_id="case-synthetic",
        actor_principal_id="lawyer-1",
        canonical_owner_principal_id="tenant-1",
        authorized=True,
        item_id="proposal-1",
        target_kind="draft_revision",
        target_id="draft-1",
        replacement="Paragraph one.",
        expected_review_revision=0,
        expected_target_revision=0,
        request_id="direct-1",
    )
    refused = service.apply_authorized_review_transition(**{**common, "item_type": "review_comment"})
    assert refused["status"] == "refused"
    assert refused["error"]["code"] == "not_an_accepted_transition"
    assert refused["applied"] is False
    assert mediator.intake_case_file.get("review_case_state") is None
    unauthorized = service.apply_authorized_review_transition(**{**common, "item_type": "review_proposal", "authorized": False})
    assert unauthorized["error"]["code"] == "actor_not_permitted"
    assert mediator.intake_case_file.get("review_case_state") is None
    applied = service.apply_authorized_review_transition(**{**common, "item_type": "review_proposal"})
    assert applied["status"] == "applied"
    assert applied["draft_revisions"]["draft-1"]["revision"] == 1
    mismatch = service.apply_authorized_review_transition(**{
        **common,
        "item_type": "review_proposal",
        "replacement": "Paragraph two.",
        "expected_review_revision": 1,
        "expected_target_revision": 1,
    })
    assert mismatch["error"]["code"] == "replay_mismatch"
    assert mediator.intake_case_file["review_case_state"]["draft_revisions"]["draft-1"]["text"] == "Paragraph one."
    replay = service.apply_authorized_review_transition(**{**common, "item_type": "review_proposal"})
    assert replay["replayed"] is True
    assert replay["draft_revisions"]["draft-1"]["revision"] == 1
