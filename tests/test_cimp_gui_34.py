"""Actual cookie/CSRF case-purpose inference with an observed synthetic transport.

No live Grok identity is claimed. Unlike the retained unit-only candidate,
these cases derive authority from actual CaseDirectory/browser/workflow state.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from applications.case_consent_api import CaseConsentService
from applications.server import SERVER
from tests.test_cimp_gui_14 import _composed_case_world, _composed_headers, _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
NARRATIVE = "On March 4, 2024 supervisor Alex Rivera fired me after I reported safety concerns. I worked at Northwind Tools. My written report was dated March 1, 2024."
FRAGMENT = "supervisor Alex Rivera fired me after I reported safety concerns"


@pytest.fixture
def world(tmp_path):
    w = _composed_case_world(tmp_path)
    w.seen = []
    w.transport_action = None
    def transport(call):
        w.seen.append(call)
        if w.transport_action:
            w.transport_action()
        purpose = call["purpose_id"] if "purpose_id" in call else call.get("purpose")
        if purpose == "propose_questions":
            output = {"questions": [{"question": "Which date applies?", "target_ref": call["inputs"]["target_ref"]}]}
        elif purpose == "explain_candidate":
            output = {"candidate_ref": call["inputs"]["candidate_ref"], "explanation": "A candidate requires review."}
        else:
            output = {"facts": [{"field": "act", "value": "fired", "target_ref": call["inputs"]["target_ref"]}]}
        return {"status": "available", "output": output, "live_model_identity_verified": True,
                "observed_provider": "grok_cli", "observed_model": "grok-4.7"}
    w.consent = CaseConsentService(tmp_path / "consent", cases=w.cases, key=os.urandom(32),
        key_id="consent-key", clock=lambda: 1700000100)
    w.app = SERVER(None, authorizer=w.authorizer, browser_sessions=w.sessions,
        case_handlers=w.handlers, case_consent=w.consent, gui_inference_transport=transport).app
    with TestClient(w.app, base_url="https://testserver") as client:
        w.client = client
        w.csrf = _composed_login(client)
        w.headers = _composed_headers(w.case, w.csrf)
        started = client.post("/api/complaint-workspace/intake-chat", headers=w.headers,
            json={"message": NARRATIVE, "interview_action": "start"})
        assert started.status_code == 200, started.text
        w.started = started.json()
        w.target = w.started["graph_targets"]["target_id"]
        assert w.target
        yield w


def choose(w, purpose="extract_facts", *, grok=True):
    endpoint = f"/api/cases/{w.case.case_id}/processing-consent"
    current = w.client.get(endpoint)
    assert current.status_code == 200
    body = {"purpose": purpose, "mode": "grok_cloud" if grok else "local_private",
            "expected_generation": current.json()["generation"]}
    if grok:
        body["explicit_case_purpose"] = True
    result = w.client.post(endpoint, headers={"x-csrf-token": w.csrf}, json=body)
    assert result.status_code == 200, result.text
    return result.json()


def dispatch(w, **overrides):
    body = {"purpose": "extract_facts", "inputs": {"source_text": FRAGMENT, "target_ref": w.target}}
    body.update(overrides)
    return w.client.post("/api/complaint-workspace/inference/dispatch", headers=w.headers, json=body)


def admit(w, invocation):
    return w.client.post("/api/complaint-workspace/inference/admit", headers=w.headers,
        json={"invocation_id": invocation})


def test_real_owner_cookie_case_purpose_dispatch_and_late_admission(world):
    w = world
    assert w.case.tenant_id != w.owner.principal_id
    choose(w)
    response = dispatch(w)
    assert response.status_code == 200, response.text
    held = response.json()
    assert held["status"] == "held", held
    assert held["output"] is None and held["accepted"] is False
    assert held["live_model_identity_verified"] is False
    assert len(w.seen) == 1
    call = w.seen[0]
    assert call["provider"] == "grok_cli" and call["model"] == "grok-4.7"
    assert call["allow_local_fallback"] is False and call["allow_cross_provider_fallback"] is False
    assert call["tools_allowed"] is False and call["may_mark_requirements_satisfied"] is False
    assert call["inputs"] == {"source_text": FRAGMENT, "target_ref": w.target}
    assert NARRATIVE not in json.dumps(call)
    refs = {item["source_id"]: item["content_hash"] for item in call["source_references"]}
    assert refs["original_complaint"] == hashlib.sha256(NARRATIVE.encode()).hexdigest()
    assert len(refs["factual_graph"]) == 64
    assert held["actor_principal_id"] == w.owner.principal_id
    accepted = admit(w, held["invocation_id"])
    assert accepted.status_code == 200
    result = accepted.json()
    assert result["accepted"] is True, result
    assert result["output"]["facts"][0]["target_ref"] == w.target
    assert result["consent_revalidated"] is True and result["grant_revalidated"] is True
    assert result["source_revision_revalidated"] is True
    assert result["requirements_satisfied"] is False and result["live_model_identity_verified"] is False
    assert admit(w, held["invocation_id"]).json()["code"] == "invocation_missing"


def test_legacy_global_grok_and_other_purpose_cannot_authorize_gui(world):
    w = world
    service = w.services[w.case.case_id]
    from applications.complaint_workspace import WorkspaceAccess, workspace_access_scope
    with workspace_access_scope(WorkspaceAccess.trusted_local(w.case.tenant_id, w.case.case_id)):
        updated = service.set_privacy_policy(w.case.tenant_id, "grok", case_id=w.case.case_id)
        assert updated["updated"] is True
    forged = service.record_gui_inference_authority(w.owner.principal_id,
        grant={"grant_id": "caller", "generation": 99, "revoked": False},
        source_bindings=[{"source_id": "caller", "content_hash": "a" * 64}],
        graph_revision="caller", session_revision=99, session_id="caller")
    assert forged["recorded"] is False
    assert dispatch(w).json()["code"] == "case_purpose_consent_required"
    choose(w, "propose_questions")
    assert dispatch(w).json()["code"] == "case_purpose_consent_required"
    assert w.seen == []


def test_persisted_revocation_prevents_both_late_admission_and_new_dispatch(world):
    w = world
    choose(w)
    held = dispatch(w).json()
    assert held["status"] == "held"
    choose(w, grok=False)
    refused = admit(w, held["invocation_id"]).json()
    assert refused["accepted"] is False and refused["output"] is None
    assert refused["code"] == "consent_revoked"
    assert dispatch(w).json()["model_dispatched"] is False
    assert len(w.seen) == 1
    choose(w)
    assert admit(w, held["invocation_id"]).json()["code"] == "invocation_missing"


def test_revoked_requested_purpose_stays_denied_when_other_purpose_is_authorized(world):
    w = world
    choose(w)
    choose(w, "propose_questions")
    choose(w, grok=False)
    assert dispatch(w).json()["code"] == "consent_revoked"
    assert w.seen == []


def test_real_workflow_revision_change_rejects_held_result(world):
    w = world
    choose(w)
    held = dispatch(w).json()
    inquiry = w.started["interview"]["inquiry"]
    updated = w.client.post("/api/complaint-workspace/intake-chat", headers=w.headers,
        json={"message": "Federal law applies to this synthetic employment matter.",
              "question_id": inquiry["inquiry_id"], "expected_question_revision": inquiry["revision"],
              "interview_action": "answer"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["interview"]["session_revision"] > w.started["interview"]["session_revision"]
    result = admit(w, held["invocation_id"]).json()
    assert result["accepted"] is False and result["output"] is None
    assert result["code"].startswith("stale_"), result


@pytest.mark.parametrize("extra", ["grant", "source_bindings", "graph_revision", "model_transport", "complaint_text"])
def test_request_cannot_supply_authority_or_transport(world, extra):
    w = world
    choose(w)
    response = dispatch(w, **{extra: "caller-supplied"})
    assert response.status_code == (403 if extra == "grant" else 422)
    assert w.seen == []


@pytest.mark.parametrize("source,target", [(NARRATIVE, None), ("foreign case fragment", None), (FRAGMENT, "foreign-target")])
def test_inputs_must_be_minimized_and_bound_to_actual_case_source(world, source, target):
    w = world
    choose(w)
    result = dispatch(w, inputs={"source_text": source, "target_ref": target or w.target}).json()
    assert result["model_dispatched"] is False
    assert result["code"] in {"query_not_minimized", "source_binding_mismatch"}
    assert w.seen == []


def test_exact_pretransport_recheck_observes_real_consent_revocation(world, monkeypatch):
    w = world
    choose(w)
    service = w.services[w.case.case_id]
    original = service._gui_inference_snapshot
    calls = 0
    def snapshot(*args, **kwargs):
        nonlocal calls
        value = original(*args, **kwargs)
        calls += 1
        if calls == 1:
            current = w.consent.read(w.owner.principal_id, w.case.case_id, authorizer=w.authorizer)
            w.consent.revoke(w.owner.principal_id, w.case.case_id,
                {"purpose": "extract_facts", "expected_generation": current["generation"]}, authorizer=w.authorizer)
        return value
    monkeypatch.setattr(service, "_gui_inference_snapshot", snapshot)
    result = dispatch(w).json()
    assert result["model_dispatched"] is False and result["code"] == "consent_revoked"
    assert w.seen == []


def test_cookie_csrf_logout_and_new_session_do_not_reuse_old_invocation(world):
    w = world
    choose(w)
    held = dispatch(w).json()
    logged_out = w.client.post("/api/complaint-workspace/auth/logout", headers={"x-csrf-token": w.csrf})
    assert logged_out.status_code == 200
    assert admit(w, held["invocation_id"]).status_code == 401
    w.csrf = _composed_login(w.client)
    w.headers = _composed_headers(w.case, w.csrf)
    result = admit(w, held["invocation_id"]).json()
    assert result["accepted"] is False and result["output"] is None
    assert result["code"] == "grant_missing"
    assert len(w.seen) == 1


def test_actual_mcp_frontdoor_uses_same_case_purpose_and_source_owner(world):
    w = world
    choose(w)
    called = w.client.post("/api/complaint-workspace/mcp/call", headers=w.headers,
        json={"tool_name": "complaint.dispatch_bounded_gui_inference", "arguments": {
            "purpose": "extract_facts", "inputs": {"source_text": FRAGMENT, "target_ref": w.target}}})
    assert called.status_code == 200
    held = called.json()
    assert held["status"] == "held", held
    admitted = w.client.post("/api/complaint-workspace/mcp/call", headers=w.headers,
        json={"tool_name": "complaint.admit_bounded_gui_inference", "arguments": {"invocation_id": held["invocation_id"]}})
    assert admitted.json()["accepted"] is True, admitted.text
    assert len(w.seen) == 1


def test_direct_service_global_policy_is_not_gui_authority(tmp_path):
    from applications.complaint_workspace import ComplaintWorkspaceService
    service = ComplaintWorkspaceService(tmp_path / "workspace")
    result = service.dispatch_bounded_gui_inference("synthetic-owner", purpose="extract_facts",
        inputs={"source_text": FRAGMENT, "target_ref": "caller"})
    assert result["model_dispatched"] is False and result["code"] == "server_case_authority_required"


def test_real_authentication_and_csrf_precede_dispatch(world):
    w = world
    choose(w)
    body = {"purpose": "extract_facts", "inputs": {"source_text": FRAGMENT, "target_ref": w.target}}
    no_csrf = w.client.post("/api/complaint-workspace/inference/dispatch",
        headers=_composed_headers(w.case), json=body)
    assert no_csrf.status_code == 403
    with TestClient(w.app, base_url="https://testserver") as anonymous:
        denied = anonymous.post("/api/complaint-workspace/inference/dispatch", headers=w.headers, json=body)
        assert denied.status_code == 401
    assert w.seen == []


def test_foreign_case_and_actor_cannot_admit_owned_invocation(world):
    w = world
    choose(w)
    held = dispatch(w).json()
    wrong_case = w.client.post("/api/complaint-workspace/inference/admit",
        headers=_composed_headers(w.second, w.csrf), json={"invocation_id": held["invocation_id"]})
    assert wrong_case.status_code == 200
    assert wrong_case.json()["code"] == "invocation_missing"
    assert wrong_case.json()["output"] is None
    with TestClient(w.app, base_url="https://testserver") as stranger:
        csrf = _composed_login(stranger, "synthetic-stranger-credential")
        denied = stranger.post("/api/complaint-workspace/inference/admit",
            headers=_composed_headers(w.case, csrf), json={"invocation_id": held["invocation_id"]})
        assert denied.status_code == 403
    assert admit(w, held["invocation_id"]).json()["accepted"] is True


@pytest.mark.parametrize("target", [[], {"actor": "caller"}, None])
def test_nonreference_inputs_are_typed_refusals(world, target):
    w = world
    choose(w)
    result = dispatch(w, inputs={"source_text": FRAGMENT, "target_ref": target})
    assert result.status_code == 200
    assert result.json()["code"] == "source_binding_mismatch"
    assert result.json()["model_dispatched"] is False and w.seen == []


def test_timeout_result_is_not_retained_or_admitted(world):
    w = world
    choose(w)
    w.transport_action = lambda: time.sleep(0.55)
    result = dispatch(w, timeout_seconds=0.5).json()
    assert result["status"] == "timeout" and result["code"] == "deadline_expired"
    assert result["output"] is None and result["accepted"] is False
    assert len(w.seen) == 1
    assert 0 < w.seen[0]["timeout_seconds"] <= 0.5
    assert "+00:00" in w.seen[0]["deadline"]
    assert not getattr(w.services[w.case.case_id], "_gui_server_holds", {})


def test_expired_pretransport_budget_cannot_call_transport(world, monkeypatch):
    w = world
    choose(w)
    service = w.services[w.case.case_id]
    original = service._gui_inference_snapshot
    calls = 0
    def snapshot(*args, **kwargs):
        nonlocal calls
        value = original(*args, **kwargs)
        calls += 1
        if calls == 2:
            time.sleep(0.04)
        return value
    monkeypatch.setattr(service, "_gui_inference_snapshot", snapshot)
    result = dispatch(w, timeout_seconds=0.01).json()
    assert result["status"] == "timeout" and result["code"] == "deadline_expired"
    assert result["model_dispatched"] is False and result["output"] is None
    assert w.seen == []


class _GuiObservedStandIn:
    """Explicit API stand-in; these tests cannot qualify a live Grok identity."""
    def __init__(self, **fields):
        self.__dict__.update(fields)


class _GuiGenerationStandIn:
    def __init__(self, text, observation):
        self.text, self.observation = text, observation


def _install_gui_observed_boundary(world, monkeypatch, *, action=None, damaged=None):
    import uuid
    from integrations.ipfs_datasets import llm
    from mediator.hook_runtime import native_gui_inference_transport
    seen = []
    def generate(**options):
        seen.append(options)
        if action:
            action()
        if damaged == "timeout":
            raise TimeoutError("synthetic deadline")
        payload = json.loads(options["prompt"])
        target = payload["inputs"]["target_ref"]
        text = json.dumps({"facts": [{"field": "act", "value": "fired", "target_ref": target}]})
        if damaged == "oversized":
            text = "x" * 8193
        observation = _GuiObservedStandIn(invocation_id=uuid.uuid4().hex,
            request_id=options["observation_request_id"], native_dispatch_count=1,
            selected_provider_name="grok_cli", selected_model_name="grok-4.7",
            provider_reported_model="grok-4.7", wire_model_observed=True,
            process_returncode=0, stream_complete=True, evidence_class="native_final_end_model_usage",
            schema="native-grok-invocation-observation@1", invocation_scope="current_call",
            observation_only=True, raw_provider_data_exported=False)
        if damaged == "mapping":
            return {"text": text, "observation": observation, "live_model_identity_verified": True}
        return _GuiGenerationStandIn(text, observation)
    monkeypatch.setattr(llm, "load_observed_llm_symbols", lambda: (generate, _GuiGenerationStandIn, _GuiObservedStandIn))
    monkeypatch.setattr(llm, "generate_text", lambda *a, **k: pytest.fail("plain text/provider fallback"))
    world.app.state.gui_inference_transport = native_gui_inference_transport
    return seen


def test_native_gui_route_uses_real_observed_boundary_and_keeps_standins_unverified(world, monkeypatch):
    w = world
    seen = _install_gui_observed_boundary(w, monkeypatch)
    choose(w)
    held = dispatch(w, timeout_seconds=2.0).json()
    assert held["status"] == "held" and held["output"] is None, held
    assert not w.seen and len(seen) == 1
    options = seen[0]
    assert options["provider"] == "grok_cli" and options["model_name"] == "grok-4.7"
    assert options["allow_local_fallback"] is False and options["allow_cross_provider_fallback"] is False
    assert 0 < options["timeout"] <= 2.0 and len(options["observation_request_id"]) == 32
    assert options["grok_max_turns"] == 1 and options["grok_permission_mode"] == "dontAsk"
    assert set(options["grok_disallowed_tools"].split(",")) >= {"read_file", "search_tool", "use_tool"}
    prompt = json.loads(options["prompt"])
    assert prompt["purpose_id"] == "extract_facts" and NARRATIVE not in options["prompt"]
    assert prompt["inputs"]["source_text"] == FRAGMENT
    assert set(prompt["inputs"]) == {"source_text", "target_ref", "source_references"}
    assert all(set(row) == {"source_id", "content_hash"} for row in prompt["inputs"]["source_references"])
    assert held["provider_invoked"] is True and held["synthetic_transport_invoked"] is False
    assert held["live_model_identity_verified"] is False
    accepted = admit(w, held["invocation_id"]).json()
    assert accepted["accepted"] is True and accepted["output"]["facts"][0]["target_ref"] == w.target
    assert accepted["transport_kind"] == "native_observation" and accepted["native_observation_bound"] is False
    assert accepted["live_model_identity_verified"] is False and accepted["unverified_legal_support"] is True
    assert accepted["requirements_satisfied"] is False


def test_native_gui_route_missing_capability_is_unavailable_without_callback_or_fallback(world, monkeypatch):
    from integrations.ipfs_datasets import llm
    from mediator.hook_runtime import native_gui_inference_transport
    w = world; choose(w); w.app.state.gui_inference_transport = native_gui_inference_transport
    monkeypatch.setattr(llm, "load_observed_llm_symbols", lambda: (None, None, None))
    result = dispatch(w).json()
    assert result["status"] == "unavailable" and result["code"] == "route_unverified", result
    assert result["model_dispatched"] is False and result["output"] is None and not w.seen


@pytest.mark.parametrize("damage", ["mapping", "oversized", "timeout"])
def test_native_gui_route_refuses_unbound_or_bad_observed_results(world, monkeypatch, damage):
    w = world; seen = _install_gui_observed_boundary(w, monkeypatch, damaged=damage); choose(w)
    result = dispatch(w).json()
    assert len(seen) == 1 and not w.seen
    assert result["status"] != "held" and result["output"] is None and result["accepted"] is False, result
    assert result["live_model_identity_verified"] is False


def test_native_gui_route_fresh_persisted_revoke_during_generation_drops_result(world, monkeypatch):
    w = world; choose(w)
    def revoke():
        current = w.consent.read(w.owner.principal_id, w.case.case_id)
        w.consent.revoke(w.owner.principal_id, w.case.case_id,
            {"purpose": "extract_facts", "expected_generation": current["generation"]})
    seen = _install_gui_observed_boundary(w, monkeypatch, action=revoke)
    result = dispatch(w).json()
    assert len(seen) == 1 and not w.seen
    assert result["status"] == "refused" and result["output"] is None and result["accepted"] is False, result
    assert result["model_dispatched"] is True and result["provider_invoked"] is True
    assert result["synthetic_transport_invoked"] is False and result["live_model_identity_verified"] is False
    assert result["code"] == "late_revalidation_unavailable"
    assert not w.services[w.case.case_id]._gui_server_holds


def test_native_gui_route_preauthorization_time_consumes_same_deadline(world, monkeypatch):
    w = world; seen = _install_gui_observed_boundary(w, monkeypatch); choose(w)
    service = w.services[w.case.case_id]; actual = service._gui_inference_snapshot
    def delayed(*args, **kwargs):
        result = actual(*args, **kwargs)
        time.sleep(0.03)
        return result
    monkeypatch.setattr(service, "_gui_inference_snapshot", delayed)
    result = dispatch(w, timeout_seconds=0.01).json()
    assert result["status"] == "timeout" and result["code"] == "deadline_expired", result
    assert result["model_dispatched"] is False and not seen and not w.seen


def test_native_gui_route_logout_after_dispatch_preserves_backend_attempt_accounting(world, monkeypatch):
    from applications.browser_sessions import SESSION_COOKIE
    w = world; choose(w)
    service = w.services[w.case.case_id]; actual = service.dispatch_bounded_gui_inference; outcomes = []
    def captured(*args, **kwargs):
        result = actual(*args, **kwargs)
        outcomes.append(result)
        return result
    monkeypatch.setattr(service, "dispatch_bounded_gui_inference", captured)
    token = w.client.cookies.get(SESSION_COOKIE)
    seen = _install_gui_observed_boundary(w, monkeypatch,
        action=lambda: w.sessions.logout(token, csrf_token=w.csrf))
    response = dispatch(w)
    assert response.status_code in (200, 401, 403)
    assert len(seen) == 1 and len(outcomes) == 1 and not w.seen
    result = outcomes[0]
    assert result["status"] == "refused" and result["output"] is None and result["accepted"] is False
    assert result["model_dispatched"] is True and result["provider_invoked"] is True
    assert result["synthetic_transport_invoked"] is False and result["live_model_identity_verified"] is False
    assert result["code"] == "late_revalidation_unavailable"
    assert not service._gui_server_holds
