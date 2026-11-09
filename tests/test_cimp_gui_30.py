"""Bind current definition and correspondence owners to an exact legal source.

Positive cases replay the pinned scope-correspondence, definition-applicability
declaration, and contextual-review owners, then accept only the receipt those
owners regenerate. Negative cases reject a drifted source, an incomplete
declared population, an incomplete graph join, training metrics, an unbound
definition, and caller-supplied receipt JSON. None of those authorize law or
proof.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.browser_sessions import (
    BrowserSessionConfiguration,
    BrowserSessionService,
    PrincipalStoreCredentialAdapter,
)
from applications.case_access import CaseActionAuthorizer
from applications.case_directory import CaseDirectory
from applications.case_routes import CaseHandlerRegistry, compose_case_routes
from applications.legal_analysis_api import (
    LegalAnalysisError,
    bind_case_definition_correspondence,
    project_definition_correspondence,
)
from applications.principal_store import PrincipalStore

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

LEGAL_SOURCE = "Clérk may retain café records only with approval."
_FIXTURE_DIR = (
    Path(__file__).resolve().parents[1]
    / "external"
    / "ipfs_datasets_py"
    / "tests"
    / "unit"
    / "logic"
    / "autoformal"
)


def _load_fixture(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, _FIXTURE_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _populations():
    return {
        "source_correspondence": ["/occurrences/0/anchor"],
        "definition_applicability": ["declare_one_supplied_alternative_applicable"],
        "contextual_review": ["unsigned_contextual_correspondence_only"],
    }


def _bundle():
    scope_module = _load_fixture("test_legal_norm_scope_correspondence_v1.py", "cimp_gui_30_scope")
    evidence_module = _load_fixture("test_legal_norm_definition_evidence_v1.py", "cimp_gui_30_evidence")
    applicability = _load_fixture("test_legal_norm_definition_applicability_v1.py", "cimp_gui_30_applicability")
    from ipfs_datasets_py.logic.autoformal import legal_graph_dependencies as dependencies
    from ipfs_datasets_py.logic.autoformal import legal_graph_review as graph_review
    from ipfs_datasets_py.logic.autoformal import legal_norm_definition_applicability_v1 as applicability_owner
    from ipfs_datasets_py.logic.autoformal import legal_norm_definition_evidence_v1 as evidence_owner
    from ipfs_datasets_py.logic.autoformal import legal_norm_interpretation_review_v1 as norm

    scope_value = scope_module.case(edition=2024)
    scope_args, scope_kwargs = scope_module.arguments(scope_value)
    definition_case = evidence_module.build_case()
    companion = evidence_module.prepare(definition_case)
    preparation = definition_case["norm_preparation"]
    manifest = dependencies.build_dependency_manifest(
        preparation["artifacts"],
        preparation["edges"],
        expected_artifact_ids=preparation["required_dependency_ids"],
    )
    subject = norm.build_norm_review_subject_v1(
        preparation,
        manifest,
        expected_preparation_sha256=norm.norm_review_sha256(preparation),
        expected_manifest_sha256=manifest["manifest_sha256"],
        required_dependency_ids=preparation["required_dependency_ids"],
        **definition_case["norm_inputs"],
    )
    prepared = {
        "inputs": definition_case,
        "companion": companion,
        "subject": subject,
        "manifest": manifest,
    }
    decisions = applicability.choices(applicability_owner, prepared)
    support = applicability.SUPPORT
    for choice in decisions:
        for ref in choice["evidence_refs"]:
            ref["sha256"] = hashlib.sha256(support).hexdigest()
    correspondence = definition_case["definitions"][0]["correspondence_inputs"]
    contextual = {
        "binding_result": correspondence["binding_result"],
        "review_subject": correspondence["review_subject"],
        "kwargs": {
            key: correspondence[key]
            for key in (
                "expected_binding_sha256",
                "expected_subject_sha256",
                "contextual_replay_inputs",
                "candidate_inputs",
                "expected_candidate_pin",
                "context_inputs",
                "expected_context_population",
                "dependency_manifest",
                "expected_manifest_sha256",
                "required_dependency_ids",
            )
            if key in correspondence
        },
    }
    return {
        "scope_correspondence": {"args": scope_args, "kwargs": scope_kwargs},
        "applicability": {
            "operation": "declaration",
            "args": [companion, subject, manifest, decisions],
            "kwargs": {
                "declared_at_utc": applicability.DECLARED,
                "expected_companion_sha256": evidence_owner.norm_definition_evidence_sha256(companion),
                "companion_inputs": definition_case,
                "expected_norm_subject_sha256": graph_review.digest(subject),
                "expected_norm_manifest_sha256": manifest["manifest_sha256"],
            },
        },
        "contextual_review": contextual,
    }


@pytest.fixture(scope="module")
def owner_bundle():
    return _bundle()


def _assert_not_authority(payload: dict) -> None:
    assert payload["authorizes_law"] is False
    assert payload["authorizes_proof"] is False
    assert payload["executed_proof"] is False
    assert payload["governing_legal_authority"] is False
    assert payload["proof"] is False
    assert payload["training_metrics_authorize_law"] is False
    assert payload["graph_join_authorizes_law"] is False
    for family in payload["owners"].values():
        assert family["authorizes_law"] is False
        assert family["authorizes_proof"] is False
        assert family["user_receipt_accepted"] is False


def test_genuine_owner_receipts_bind_exact_source_and_populations(owner_bundle):
    mediator = SimpleNamespace(intake_case_file={})
    payload = bind_case_definition_correspondence(mediator, {
        "request_id": "cimp-gui-30-synthetic",
        "source_text": LEGAL_SOURCE,
        "declared_populations": _populations(),
        "receipt": {"executed_proof": True, "governing_legal_authority": True, "status": "verified"},
        "training_metrics": {"accuracy": 1.0, "authorizes_law": True},
        "graph_join": {"complete": False, "population_ids": [], "authorizes_proof": True},
        **owner_bundle,
    })
    assert payload["task_id"] == "CIMP-GUI-30"
    assert payload["status"] == "bound", payload.get("reason")
    assert payload["supplied_receipt_ignored"] is True
    assert payload["incomplete_graph_join"] is True
    assert payload["definition_unbound"] is False
    assert payload["training_metrics_present"] is True
    owners = payload["owners"]
    assert set(_populations()) <= set(owners)
    for name in _populations():
        assert owners[name]["genuine_current_owner_receipt"] is True, owners[name]
        assert owners[name]["source_bound"] is True
        assert owners[name]["population_complete"] is True
        assert owners[name]["receipt_sha256"]
    _assert_not_authority(payload)
    stored = mediator.intake_case_file["definition_correspondence_binding"]
    assert stored["status"] == "bound"
    projected = project_definition_correspondence(mediator.intake_case_file)
    assert projected["status"] == "bound"
    assert projected["proof"] is False
    assert projected["authorizes_law"] is False


def test_drift_incomplete_population_unbound_definition_and_substitutes_do_not_authorize(owner_bundle):
    drifted = bind_case_definition_correspondence(SimpleNamespace(intake_case_file={}), {
        "request_id": "cimp-gui-30-drift",
        "source_text": "A different sentence that is not the pinned legal source.",
        "declared_populations": _populations(),
        **owner_bundle,
    })
    assert drifted["status"] == "source_unbound"
    assert drifted["authorizes_law"] is False
    assert drifted["authorizes_proof"] is False
    assert all(family["genuine_current_owner_receipt"] is False for family in drifted["owners"].values())

    incomplete = bind_case_definition_correspondence(SimpleNamespace(intake_case_file={}), {
        "request_id": "cimp-gui-30-population",
        "source_text": LEGAL_SOURCE,
        "declared_populations": {
            **_populations(),
            "source_correspondence": ["/occurrences/0/anchor", "population-not-in-owner-result"],
        },
        **owner_bundle,
    })
    assert incomplete["status"] == "incomplete_declared_population"
    assert incomplete["owners"]["source_correspondence"]["population_complete"] is False
    assert incomplete["proof"] is False

    unbound = bind_case_definition_correspondence(SimpleNamespace(intake_case_file={}), {
        "request_id": "cimp-gui-30-unbound",
        "source_text": LEGAL_SOURCE,
        "declared_populations": {
            **_populations(),
            "definition_applicability": ["blank_unsubmitted_exact_use_applicability_template"],
        },
        "scope_correspondence": owner_bundle["scope_correspondence"],
        "contextual_review": owner_bundle["contextual_review"],
        "applicability": {
            "operation": "template",
            "args": owner_bundle["applicability"]["args"][:3],
            "kwargs": {
                key: value
                for key, value in owner_bundle["applicability"]["kwargs"].items()
                if key != "declared_at_utc"
            },
        },
    })
    assert unbound["status"] == "unbound_definition"
    assert unbound["definition_unbound"] is True
    assert unbound["authorizes_law"] is False
    assert unbound["governing_legal_authority"] is False

    receipt_only = bind_case_definition_correspondence(SimpleNamespace(intake_case_file={}), {
        "request_id": "cimp-gui-30-receipt",
        "source_text": LEGAL_SOURCE,
        "declared_populations": _populations(),
        "receipt": {"status": "verified", "executed_proof": True, "governing_legal_authority": True},
    })
    assert receipt_only["status"] == "rejected"
    assert receipt_only["reason"] == "supplied_receipt_ignored"
    assert receipt_only["executed_proof"] is False
    assert receipt_only["owners"] == {}

    metrics_only = bind_case_definition_correspondence(SimpleNamespace(intake_case_file={}), {
        "request_id": "cimp-gui-30-metrics",
        "source_text": LEGAL_SOURCE,
        "declared_populations": _populations(),
        "training_metrics": {"loss": 0.0, "proof": True},
    })
    assert metrics_only["status"] == "rejected"
    assert metrics_only["reason"] == "training_metrics_are_not_authority"
    assert metrics_only["training_metrics_authorize_proof"] is False

    join_only = bind_case_definition_correspondence(SimpleNamespace(intake_case_file={}), {
        "request_id": "cimp-gui-30-join",
        "source_text": LEGAL_SOURCE,
        "declared_populations": _populations(),
        "graph_join": {"complete": False, "population_ids": ["/occurrences/0/anchor"], "authorizes_law": True},
    })
    assert join_only["status"] == "incomplete_graph_join"
    assert join_only["incomplete_graph_join"] is True
    assert join_only["graph_join_authorizes_law"] is False
    assert join_only["authorizes_proof"] is False

    with pytest.raises(LegalAnalysisError) as missing:
        bind_case_definition_correspondence(SimpleNamespace(), {
            "request_id": "cimp-gui-30-missing",
            "source_text": LEGAL_SOURCE,
            "declared_populations": _populations(),
        })
    assert missing.value.code == "legal_analysis_unavailable"
    empty = project_definition_correspondence({})
    assert empty["status"] == "empty"
    assert empty["authorizes_law"] is False


class _Mediator:
    def __init__(self) -> None:
        self.intake_case_file = {"legal_context": {"jurisdiction": "US"}}


def _world(tmp_path):
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    owner = principals.register_from_request({})
    stranger = principals.register_from_request({})
    cases = CaseDirectory(tmp_path / "cases", key=os.urandom(32), key_id="case-key")
    case = cases.create_case(actor_principal_id=owner.principal_id)
    second = cases.create_case(actor_principal_id=owner.principal_id)
    authorizer = CaseActionAuthorizer(principals, cases)
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            "synthetic-owner-credential": owner.principal_id,
            "synthetic-stranger-credential": stranger.principal_id,
        }),
        signing_key=os.urandom(32),
        ttl_seconds=300,
    ))
    mediator = _Mediator()
    handlers = CaseHandlerRegistry()
    handlers.bind(case, mediator=mediator, workspace_service=SimpleNamespace(case_id=case.case_id),
        authorize_delegated=lambda _decision: False)
    handlers.bind(second, mediator=_Mediator(), workspace_service=SimpleNamespace(case_id=second.case_id),
        authorize_delegated=lambda _decision: False)
    app = FastAPI()
    compose_case_routes(app, authorizer=authorizer, browser_sessions=sessions, case_handlers=handlers,
        include_workspace=False, include_review=False, include_document=False)
    return SimpleNamespace(owner=owner, stranger=stranger, case=case, second=second, app=app, mediator=mediator)


def _headers(case, csrf=None):
    headers = {
        "x-tenant-id": case.tenant_id,
        "x-case-id": case.case_id,
        "x-resource-id": case.resource_id,
        "x-expected-revision": str(case.revision),
    }
    if csrf is not None:
        headers["x-csrf-token"] = csrf
    return headers


def test_http_rejects_receipt_metrics_and_cross_case(tmp_path):
    from tests.test_gui25_26_private_owner_http import _world, _login, _headers
    from tests.test_gui30_private_owner import _source, _request
    world = _world(tmp_path)
    path = f"/api/legal-analysis/{world.case.case_id}/definition-correspondence"
    with TestClient(world.app, base_url="https://testserver") as client:
        assert client.get(path, headers=_headers(world)).status_code == 401
        csrf = _login(client)
        source = _source(client, world, csrf)
        empty = client.get(path, headers=_headers(world))
        assert empty.status_code == 200 and empty.json()["status"] == "empty"
        body = _request(client, world, source)
        assert client.post(path, headers=_headers(world), json=body).status_code == 403
        forged = client.post(path, headers=_headers(world, csrf), json={**body,
            "receipt": {"executed_proof": True, "governing_legal_authority": True}})
        assert forged.status_code == 422 and forged.json()["error"] == "client_case_authority"
        metrics = client.post(path, headers=_headers(world, csrf), json={
            key:value for key,value in {**body, "training_metrics":{"accuracy":1},
                "graph_join":{"complete":False,"population_ids":[]}}.items() if key != "owner_inputs"})
        assert metrics.status_code == 200
        assert metrics.json()["reason"] == "training_metrics_are_not_authority"
        assert metrics.json()["binding_persisted"] is False and metrics.json()["authorizes_proof"] is False
        assert client.get(path, headers=_headers(world)).json()["status"] == "empty"
        crossed = client.post(path, headers=_headers(world, csrf), params={"case_id":"synthetic-other-case"}, json=body)
        assert crossed.status_code == 403 and crossed.json()["error"] == "cross_case_id"
        assert crossed.json()["proof"] is False
        login = client.post("/api/complaint-workspace/auth/login", json={"credential":"synthetic-stranger-credential"})
        assert login.status_code == 200
        denied = client.get(path, headers=_headers(world))
        assert denied.status_code == 403
