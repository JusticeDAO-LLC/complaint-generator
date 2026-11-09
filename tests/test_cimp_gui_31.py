"""Show source-bound proof traces and unavailable states in the workspace.

Legacy caller claims remain explicitly unverified. Actual encrypted current
IR is rendered through Chromium without executing a prover.
Missing prover, timeout, and source drift stay visible. None of those become a
green checkmark or legal sufficiency.
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
from applications.case_access import CaseActionAuthorizer
from applications.case_directory import CaseDirectory
from applications.case_routes import PROTECTED_PREFIXES, CaseHandlerRegistry, compose_case_routes
from applications.legal_analysis_api import (
    PROOF_TRACE_ROUTE,
    LegalAnalysisError,
    project_proof_traces,
    record_case_proof_traces,
)
from applications.principal_store import PrincipalStore

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

SOURCE = "synthetic-source-identity-31"


def _row(**overrides):
    payload = {
        "obligation_id": "obligation-executed",
        "statement": "The synthetic source requires approval before retention.",
        "source_span": "source:0-48",
        "source_identity": SOURCE,
        "proof_status": "executed",
        "engine_name": "synthetic-lean",
        "engine_version": "0.0-test",
        "legal_sufficiency": True,
        "green_checkmark": True,
    }
    payload.update(overrides)
    return payload


def _body(obligations, **overrides):
    payload = {
        "request_id": "cimp-gui-31-synthetic",
        "source_identity": SOURCE,
        "expected_source_identity": SOURCE,
        "legal_sufficiency": True,
        "obligations": obligations,
    }
    payload.update(overrides)
    return payload


def _assert_not_sufficient(payload):
    assert payload["legal_sufficiency"] is False
    assert payload["proof"] is False
    assert payload["executed_proof"] is False
    assert payload["governing_legal_authority"] is False
    assert payload["admitted_law"] is False
    for row in payload["obligations"]:
        assert row["legal_sufficiency"] is False
        assert row["executed_proof"] is False
        assert row["source_bound"] is False


def test_recorded_trace_keeps_executed_degraded_and_not_executed_distinct():
    mediator = SimpleNamespace(intake_case_file={
        "canonical_legal_ir_attachment": {
            "source_identity": SOURCE,
            "typed_obligations": [{
                "obligation_id": "obligation-from-ir",
                "statement": "Canonical source obligation remains unbound to a prover.",
                "source_span": "source:80-120",
            }],
        },
    })
    payload = record_case_proof_traces(mediator, _body([
        _row(),
        _row(obligation_id="obligation-degraded", proof_status="degraded", engine_name="synthetic-z3", engine_version="4.13-test", counterexample="model: approval bit is false"),
        _row(obligation_id="obligation-open", proof_status="not_executed", engine_name="", engine_version=""),
    ]))
    assert payload["task_id"] == "CIMP-GUI-31"
    assert payload["status"] == "visible"
    assert payload["supplied_legal_sufficiency_ignored"] is True
    _assert_not_sufficient(payload)
    by_id = {row["obligation_id"]: row for row in payload["obligations"]}
    assert by_id["obligation-executed"]["proof_status"] == "not_executed"
    assert by_id["obligation-executed"]["reported_proof_status"] == "executed"
    assert by_id["obligation-executed"]["green_checkmark"] is False
    assert by_id["obligation-degraded"]["proof_status"] == "degraded"
    assert by_id["obligation-degraded"]["green_checkmark"] is False
    assert by_id["obligation-degraded"]["counterexample"] == "model: approval bit is false"
    assert by_id["obligation-open"]["proof_status"] == "not_executed"
    assert by_id["obligation-open"]["green_checkmark"] is False
    assert by_id["obligation-from-ir"]["proof_status"] == "not_executed"
    assert by_id["obligation-from-ir"]["green_checkmark"] is False
    assert payload["engine_versions"] == []
    assert by_id["obligation-executed"]["reported_engine_name"] == "synthetic-lean"
    assert payload["counterexamples"][0]["green_checkmark"] is False
    projected = project_proof_traces(mediator.intake_case_file)
    assert projected["obligations"][0]["proof_status"] == "not_executed"
    assert projected["legal_sufficiency"] is False
    empty = project_proof_traces({})
    assert empty["status"] == "empty"
    assert empty["legal_sufficiency"] is False
    assert "not a successful proof" in empty["limitations"][0]


def test_missing_prover_timeout_and_source_drift_stay_visible():
    mediator = SimpleNamespace(intake_case_file={})
    payload = record_case_proof_traces(mediator, _body([
        _row(obligation_id="obligation-missing", proof_status="executed", engine_name="", engine_version="", prover_missing=True),
        _row(obligation_id="obligation-timeout", proof_status="executed", timed_out=True),
        _row(obligation_id="obligation-drift", proof_status="executed", source_identity="other-source"),
        _row(obligation_id="obligation-counterexample", proof_status="executed", counterexample="trace: goal unsat under the bound"),
    ]))
    by_id = {row["obligation_id"]: row for row in payload["obligations"]}
    assert by_id["obligation-missing"]["proof_status"] == "missing_prover"
    assert by_id["obligation-timeout"]["proof_status"] == "timeout"
    assert by_id["obligation-drift"]["proof_status"] == "source_drift"
    assert by_id["obligation-counterexample"]["proof_status"] == "not_executed"
    assert by_id["obligation-counterexample"]["reported_proof_status"] == "executed"
    for row in by_id.values():
        if row["obligation_id"] != "obligation-counterexample":
            assert row["green_checkmark"] is False
    assert by_id["obligation-counterexample"]["green_checkmark"] is False
    assert payload["source_drift"] is True
    _assert_not_sufficient(payload)
    drifted = record_case_proof_traces(SimpleNamespace(intake_case_file={}), _body(
        [_row(obligation_id="obligation-envelope")],
        expected_source_identity="expected-other-source",
    ))
    assert drifted["obligations"][0]["proof_status"] == "source_drift"
    assert drifted["obligations"][0]["green_checkmark"] is False
    assert drifted["legal_sufficiency"] is False
    with pytest.raises(LegalAnalysisError) as missing:
        record_case_proof_traces(SimpleNamespace(), _body([_row()]))
    assert missing.value.code == "legal_analysis_unavailable"








def test_proof_trace_route_stays_on_the_protected_legal_analysis_prefix():
    assert any(PROOF_TRACE_ROUTE.startswith(prefix + "/") for prefix in PROTECTED_PREFIXES)


def test_http_projects_unavailable_states_without_authority(tmp_path):
    from tests.test_gui25_26_private_owner_http import _world as real_world, _login, _headers
    from tests.test_gui31_private_proof_trace import _compiled
    from tests.test_cimp_gui_14 import _composed_ciphertext_snapshot
    world = real_world(tmp_path)
    path = f"/api/legal-analysis/{world.case.case_id}/proof-traces"
    with TestClient(world.app, base_url="https://testserver") as client:
        assert client.get(path, headers=_headers(world)).status_code == 401
        csrf = _login(client)
        compiled = _compiled(client, world, csrf)
        before = _composed_ciphertext_snapshot(world.service)
        current = client.get(path, headers=_headers(world))
        assert current.status_code == 200
        view = current.json()
        assert view["case_id"] == world.case.case_id
        assert {row["obligation_id"] for row in view["obligations"]} == {row["obligation_id"] for row in compiled["typed_obligations"]}
        assert all(row["source_bound"] and row["proof_status"] == "not_executed" and not row["green_checkmark"] for row in view["obligations"])
        assert view["engine_versions"] == [] and view["legal_sufficiency"] is False
        refused = client.post(path, headers=_headers(world, csrf), json=_body([_row()]))
        assert refused.status_code == 503
        assert refused.json()["error"] == "proof_producer_unavailable"
        assert refused.json()["obligations"] == []
        assert _composed_ciphertext_snapshot(world.service) == before
        assert client.get(path + "?case_id=other-case", headers=_headers(world)).status_code == 403
        issued = client.post("/api/complaint-workspace/auth/login", json={"credential":"synthetic-stranger-credential"})
        assert issued.status_code == 200
        assert client.get(path, headers=_headers(world)).status_code == 403




def test_workspace_script_renders_traces_and_keeps_unavailable_states_visible(tmp_path, monkeypatch):
    from tests.test_gui3031_private_panels import _private_page, _refresh_proof
    with _private_page(tmp_path, monkeypatch) as (world, page, compiled):
        _refresh_proof(page, world.case.case_id)
        assert page.locator(".proof-trace-row").count() == len(compiled["typed_obligations"])
        assert page.locator(".proof-trace-row[data-source-bound='true']").count() == len(compiled["typed_obligations"])
        assert page.locator(".proof-trace-row[data-proof-status='not_executed']").count() == len(compiled["typed_obligations"])
        assert page.locator("[data-green-checkmark='true']").count() == 0
        summary = page.locator("#proof-trace-summary")
        assert summary.get_attribute("data-proof") == "false"
        assert "not executed proofs" in summary.inner_text()
        assert "No engine version recorded" in page.locator("#proof-trace-engines").inner_text()
        assert "Compilation is not proof" in page.locator("#proof-trace-notice").inner_text()
        page.click("#workspace-clear-private-state")
        page.wait_for_function("document.body.dataset.workspaceHydrated === 'cleared'")
        assert page.locator(".proof-trace-row").count() == 0
        assert page.locator("#proof-trace-engines").inner_text() == ""
