"""Offline and unavailable GUI outcomes stay explicit.

Absent models, law, provers, and storage, plus rate limits, network denial,
missing keys, corrupt snapshots, and revoked grants are required cases.
Pending research and factual gaps stay visible. Durability and proof stay
unverified unless the owning check actually succeeded. An unavailable
capability is not a successful end-to-end route.

The original five tests are bounded unit/transport checks, including an
explicit in-process Kit stand-in. The additional actual-owner cases exercise
issued cookies, real encrypted workspaces, persisted purpose decisions,
recipient grants and Chromium against the composed production ASGI routes.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from applications.case_storage_api import CaseStorageError
from integrations.private_storage import (
    PrivateArtifactBinding,
    seal_private_artifact,
    verify_ciphertext_durability,
)
from applications.legal_analysis_api import project_proof_traces, record_case_proof_traces
from applications.legal_research_api import LegalResearchError, acquire_bounded_legal_sources
from applications.case_review import project_workflow_stage
from mediator.hook_runtime import admit_gui_bounded_inference, dispatch_gui_bounded_inference
from tests.gui_collaboration_fixtures import (
    CASE,
    GRAPH,
    OWNER,
    authenticated_storage_app,
    inference_bundle,
    proof_body,
    proof_mediator,
    research_authority,
    research_body,
    research_mediator,
    reset_inference_bindings,
    storage_body,
    storage_world,
    workflow_case,
)
from tests.gui_native_browser import probe_inherited_network_denial

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _dispatch(bundle, *, transport=None, session_id: str):
    return dispatch_gui_bounded_inference(
        policy_record=bundle["policy_record"],
        grant=bundle["grant"],
        purpose_id="extract_facts",
        inputs=bundle["inputs"],
        source_bindings=bundle["bindings"],
        legal_context=bundle["legal_context"],
        owner_id=OWNER,
        case_id=CASE,
        session_id=session_id,
        session_revision=1,
        graph_revision=GRAPH,
        deadline=bundle["deadline"],
        now=bundle["now"],
        privacy_context=bundle["privacy_context"],
        model_transport=transport,
        allow_local_fallback=False,
        allow_cross_provider_fallback=False,
        operation="refresh_grounding",
    )


def _assert_not_route(result: dict) -> None:
    assert result["accepted"] is False
    assert result["requirements_satisfied"] is False
    assert result["requirements_satisfied_by_model"] is False
    assert result["live_model_identity_verified"] is False
    assert result.get("status") != "available"


def test_absent_model_rate_limit_network_denial_and_revoked_grant_are_not_routes():
    reset_inference_bindings()
    absent = _dispatch(inference_bundle(session_id="session-absent"), transport=None, session_id="session-absent")
    _assert_not_route(absent)
    assert absent["status"] == "unavailable"
    assert absent["code"] == "unavailable"
    assert absent["router_calls"]

    limited = _dispatch(
        inference_bundle(session_id="session-rate"),
        transport=lambda _call: {"status": "rate_limited"},
        session_id="session-rate",
    )
    _assert_not_route(limited)
    assert limited["code"] == "rate_limited"
    assert limited["status"] == "unavailable"

    denied = _dispatch(
        inference_bundle(session_id="session-net"),
        transport=lambda _call: {"status": "network_denied"},
        session_id="session-net",
    )
    _assert_not_route(denied)
    assert denied["code"] == "network_denied"
    fence = probe_inherited_network_denial()
    assert isinstance(fence, dict)
    assert fence.get("af_unix_only") is True

    revoked_bundle = inference_bundle(revoked=True, session_id="session-revoked")
    revoked = _dispatch(revoked_bundle, transport=lambda _call: {"status": "available", "output": {"facts": []}}, session_id="session-revoked")
    _assert_not_route(revoked)
    assert revoked["code"] == "grant_revoked"
    assert revoked["router_calls"] == []


def test_held_model_text_is_not_an_end_to_end_success_and_revocation_drops_it():
    reset_inference_bindings()
    bundle = inference_bundle(session_id="session-hold")

    def transport(_call):
        return {"status": "available", "output": {"facts": [{"field": "act", "value": "synthetic act", "target_ref": "entity-57"}]}}

    held = _dispatch(bundle, transport=transport, session_id="session-hold")
    assert held["status"] == "held"
    assert held["code"] == "awaiting_late_admission"
    assert held["accepted"] is False
    assert held["output"] is None
    assert held["requirements_satisfied"] is False
    assert "provider_output_is_not_verified_legal_support" in held["limitations"]

    admitted = admit_gui_bounded_inference(
        invocation_id=held["invocation_id"],
        policy_record=bundle["policy_record"],
        grant=bundle["grant"],
        source_bindings=bundle["bindings"],
        owner_id=OWNER,
        case_id=CASE,
        graph_revision=GRAPH,
        session_revision=1,
    )
    assert admitted["accepted"] is True
    assert admitted["requirements_satisfied"] is False
    assert admitted["unverified_legal_support"] is True
    assert admitted["live_model_identity_verified"] is False
    assert admitted["output"]["facts"][0]["field"] == "act"

    again = inference_bundle(session_id="session-hold-revoke")
    second = _dispatch(again, transport=transport, session_id="session-hold-revoke")
    assert second["status"] == "held"
    revoked_grant = dict(again["grant"])
    revoked_grant["revoked"] = True
    dropped = admit_gui_bounded_inference(
        invocation_id=second["invocation_id"],
        policy_record=again["policy_record"],
        grant=revoked_grant,
        source_bindings=again["bindings"],
        owner_id=OWNER,
        case_id=CASE,
        graph_revision=GRAPH,
        session_revision=1,
    )
    assert dropped["accepted"] is False
    assert dropped["code"] == "grant_revoked"
    assert dropped["output"] is None
    assert dropped["requirements_satisfied"] is False


def test_absent_law_keeps_research_gaps_and_absent_hook_is_unavailable():
    missing = acquire_bounded_legal_sources(
        research_mediator(absent_law=True),
        object(),
        research_authority(),
        research_body(),
    )
    assert missing["admitted_law"] is False
    assert missing["proof"] is False
    assert missing["legal_sufficiency"] is False
    assert missing["status"] == "unavailable"
    assert missing["research_gap_count"] >= 1
    assert missing["context_required"]["selection_status"] == "pending"
    assert "law_corpus_absent" in missing["context_required"]["reason_codes"]
    reasons = {item["reason"] for item in missing["source_version_receipts"] if item["kind"] == "research_gap"}
    assert "missing_archive" in reasons
    assert "model_text_not_law" in reasons or "model_text" in reasons
    assert all(item["admitted_law"] is False and item["proof"] is False for item in missing["source_version_receipts"])

    with pytest.raises(LegalResearchError) as absent:
        acquire_bounded_legal_sources(research_mediator(absent_hook=True), object(), research_authority(), research_body())
    assert absent.value.code == "research_hook_unavailable"

    with pytest.raises(LegalResearchError) as revoked:
        acquire_bounded_legal_sources(
            research_mediator(absent_law=True),
            object(),
            research_authority(revoked=True),
            {**research_body(), "retrieval_mode": "live", "operation_id": "op-57-live"},
        )
    assert revoked.value.code == "purpose_consent_required"


def test_absent_prover_and_corrupt_snapshot_keep_factual_and_proof_gaps():
    mediator = proof_mediator()
    recorded = record_case_proof_traces(mediator, proof_body(status="missing_prover"))
    assert recorded["executed_proof"] is False
    assert recorded["proof"] is False
    assert recorded["legal_sufficiency"] is False
    assert recorded["admitted_law"] is False
    assert recorded["governing_legal_authority"] is False
    assert recorded["proof_status_counts"]["missing_prover"] == 1
    assert recorded["obligations"][0]["green_checkmark"] is False
    assert recorded["obligations"][0]["engine_name"] == ""
    assert recorded["supplied_legal_sufficiency_ignored"] is True
    projected = project_proof_traces(mediator.intake_case_file)
    assert projected["executed_proof"] is False

    claimed = record_case_proof_traces(proof_mediator(), proof_body(status="executed"))
    assert claimed["obligations"][0]["proof_status"] == "not_executed"
    assert claimed["obligations"][0]["reported_proof_status"] == "executed"
    assert claimed["executed_proof"] is False
    assert claimed["engine_versions"] == []

    pending = project_workflow_stage(workflow_case())
    assert pending["stage"] == "legal_unresolved"
    assert pending["domains"]["factual"]["settled"] is True
    assert pending["domains"]["legal"]["reason"] == "legal_not_admitted"
    assert pending["domains"]["proof"]["reason"] == "not_executed"
    assert pending["legal_sufficiency"] is False
    assert pending["readiness"]["ready_for_versioned_export"] is False

    corrupt = project_workflow_stage(workflow_case(corrupt_snapshot=True))
    assert corrupt["stage"] == "factual_unresolved"
    assert corrupt["domains"]["factual"]["reason"] == "factual_not_current"
    assert corrupt["domains"]["legal"]["governing_law"] is False
    assert corrupt["domains"]["legal"]["governing_law_claim_ignored"] is True
    assert corrupt["domains"]["proof"]["settled"] is False
    assert corrupt["exportable_drafts"] == []
    assert "ready" in corrupt["readiness"]["ignored_checkbox_keys"]


def test_missing_keys_corrupt_storage_and_absent_backend_stay_undurable(tmp_path):
    from tests.gui_collaboration_fixtures import Kit

    missing = storage_world(tmp_path / "missing-key", with_key=False)
    with pytest.raises(CaseStorageError) as missing_error:
        missing["service"].commit(missing["owner"].principal_id, storage_body(missing, idempotency_key="missing-key"))
    assert missing_error.value.code == "key_unavailable"
    assert missing_error.value.receipt["durable"] is False
    assert missing_error.value.receipt["storage_readiness"] == "unresolved"
    assert missing_error.value.receipt["actor_is_encrypted_owner"] is False

    offline = storage_world(tmp_path / "offline", Kit(offline=True))
    with pytest.raises(CaseStorageError) as offline_error:
        offline["service"].commit(offline["owner"].principal_id, storage_body(offline, idempotency_key="offline"))
    assert offline_error.value.code == "kit_manifest_failed"
    assert offline_error.value.receipt["storage_readiness"] == "unavailable"
    assert offline_error.value.receipt["durable"] is False
    assert offline_error.value.receipt["unresolved"] is True
    assert offline_error.value.receipt["replica_status"] == "unresolved"

    sealed = storage_world(tmp_path / "sealed", Kit())
    case = sealed["case"]
    session = sealed["service"]._sessions[sealed["owner"].principal_id]
    key_id = session.ensure_data_key(case.tenant_id, case.case_id)
    envelope = seal_private_artifact(
        b"synthetic-ciphertext-57",
        binding=PrivateArtifactBinding(
            tenant_id=case.tenant_id,
            case_id=case.case_id,
            artifact_kind="case-ciphertext",
            revision="r57",
            principal_id=case.tenant_id,
        ),
        key=session.lookup_data_key(case.tenant_id, case.case_id, key_id),
        key_id=key_id,
    )
    corrupt = verify_ciphertext_durability(Kit(corrupt=True), envelope)
    assert corrupt["durable"] is False
    assert corrupt["readback_matched"] is False
    assert corrupt["code"] == "readback_mismatch"
    assert corrupt["pin_is_durable"] is False
    assert "verified_replica" not in corrupt["state_names"]
    matched = verify_ciphertext_durability(Kit(), envelope)
    assert matched["durable"] is True
    assert matched["readback_matched"] is True
    assert matched["local_commit_is_durable"] is False
    assert matched["queued_replication_is_durable"] is False

    healthy = storage_world(tmp_path / "healthy", Kit())
    app = authenticated_storage_app(healthy, mount_storage=False)
    with TestClient(app, base_url="https://testserver") as client:
        login = client.post("/api/complaint-workspace/auth/login", json={"credential": "synthetic-owner-57"})
        assert login.status_code == 200, login.text
        failed = client.post(
            "/api/cases/storage/durability",
            headers={"x-csrf-token": login.json()["csrf_token"]},
            json=storage_body(healthy, idempotency_key="absent-backend"),
        )
    assert failed.status_code >= 400
    body = failed.json()
    assert body["error"] == "storage_unavailable"
    assert body["durable"] is False
    assert body["storage_readiness"] == "unavailable"
    assert body["unresolved"] is True
    assert b"synthetic-ciphertext-57".decode() not in failed.text
    assert "synthetic-passphrase-57" not in failed.text


def test_actual_cookie_owner_missing_model_law_and_storage_never_become_success(tmp_path):
    from tests.gui_collaboration_fixtures import actual_unavailable_world, choose_actual_purpose
    from tests.test_cimp_gui_14 import _composed_headers, _composed_ciphertext_snapshot, _composed_login
    from tests.test_cimp_gui_34 import FRAGMENT, NARRATIVE
    world = actual_unavailable_world(tmp_path)
    assert world.owner.principal_id != world.case.tenant_id
    with TestClient(world.app, base_url='https://testserver') as client:
        csrf_token = _composed_login(client)
        headers = _composed_headers(world.case, csrf_token)
        started = client.post('/api/complaint-workspace/intake-chat', headers=headers,
            json={'message':NARRATIVE,'interview_action':'start'})
        assert started.status_code == 200, started.text
        selected = choose_actual_purpose(client, world, csrf_token, 'extract_facts', cloud=True)
        assert any(row['purpose'] == 'extract_facts' and row['egress_authorized'] for row in selected['decisions'])
        current = client.get('/api/complaint-workspace/session', headers=headers)
        assert current.status_code == 200, current.text
        target = started.json()['graph_targets']['target_id']
        assert target
        before = _composed_ciphertext_snapshot(world.service)
        unavailable = client.post('/api/complaint-workspace/inference/dispatch', headers=headers,
            json={'purpose':'extract_facts','inputs':{'source_text':FRAGMENT,'target_ref':target}})
        assert unavailable.status_code == 200, unavailable.text
        result = unavailable.json()
        assert result['code'] == 'model_transport_unavailable'
        assert result['model_dispatched'] is False and result['accepted'] is False and result['output'] is None
        assert result['requirements_satisfied'] is False
        revoked = choose_actual_purpose(client, world, csrf_token, 'extract_facts')
        assert any(row['purpose'] == 'extract_facts' and not row['egress_authorized'] for row in revoked['decisions'])
        denied = client.post('/api/complaint-workspace/inference/dispatch', headers=headers,
            json={'purpose':'extract_facts','inputs':{'source_text':FRAGMENT,'target_ref':target}})
        assert denied.status_code == 200 and denied.json()['model_dispatched'] is False, denied.text
        assert denied.json()['code'] in {'case_purpose_consent_required','consent_revoked'}
        local = choose_actual_purpose(client, world, csrf_token, 'citation_acquisition')
        research = client.post('/api/legal-research/'+world.case.case_id, headers=headers,
            json={'purpose':'citation_acquisition','query':'Authored absent source 57',
                'retrieval_mode':'cache','expected_consent_generation':local['generation'],
                'operation_id':'synthetic-57-no-corpus','max_results':1,'deadline_seconds':1,'max_bytes':256})
        assert research.status_code == 200, research.text
        view = research.json()
        assert view['admitted_law'] is False and view['proof'] is False and view['legal_sufficiency'] is False
        assert view['candidate_count'] == 0
        assert view['context_required']['selection_status'] != 'selected'
        assert view['context_required']['reason_codes']
        context_path = '/api/legal-context/'+world.case.case_id
        context = client.get(context_path, headers=headers)
        assert context.status_code == 200, context.text
        selected_context = client.post(context_path, headers=headers, json={
            'expected_context_revision':context.json()['context_revision'], 'jurisdiction':'Oregon',
            'forum':'synthetic-state-trial-forum','applicability':'explicit',
            'applicable_law_date':'2024-03-15','event_date':'2024-03-04'})
        assert selected_context.status_code == 200, selected_context.text
        missing_corpus = client.post('/api/legal-research/'+world.case.case_id, headers=headers,
            json={'purpose':'citation_acquisition','query':'Authored absent source 57',
                'retrieval_mode':'cache','expected_consent_generation':local['generation'],
                'operation_id':'synthetic-57-selected-no-corpus','max_results':1,'deadline_seconds':1,'max_bytes':256})
        assert missing_corpus.status_code == 200, missing_corpus.text
        missing = missing_corpus.json()
        assert missing['candidate_count'] == 0
        assert missing['status'] in {'pending','unavailable','empty'}, {
            key:missing.get(key) for key in ('status','error_code','context_required','research_gap_count')}
        # The production adapter can refuse before any corpus operation. A
        # typed capability error is distinct from a per-operation research gap.
        if missing['research_gap_count'] == 0:
            assert missing.get('context_required',{}).get('reason_codes') or missing['error_code'], {
                key:missing.get(key) for key in ('status','error_code','context_required','research_gap_count')}
        (tmp_path/'actual-unavailable-research-metadata.json').write_text(__import__('json').dumps({
            key:missing.get(key) for key in ('status','error_code','context_required','candidate_count','research_gap_count')}))
        assert missing['admitted_law'] is False and missing['proof'] is False
        absent_storage = client.post('/api/cases/storage/durability', headers=headers,
            json={'tenant_id':world.case.tenant_id,'case_id':world.case.case_id,
                'resource_id':world.case.resource_id,'revision':'synthetic-57',
                'idempotency_key':'synthetic-57-missing-store','content_base64':'c3ludGhldGlj'})
        assert absent_storage.status_code == 503 and absent_storage.json()['error'] == 'storage_unavailable'
        assert absent_storage.json()['durable'] is False
        # Research may record a truthful pending result; no inference output is
        # promoted and current encrypted factual gaps remain unresolved.
        session = client.get('/api/complaint-workspace/session', headers=headers)
        assert session.status_code == 200 and session.json()['session']['case_id'] == world.case.case_id
        assert before


def test_actual_encrypted_ir_without_checked_prover_remains_nonproof_and_read_only(tmp_path, monkeypatch):
    from tests.test_gui25_26_private_owner_http import _world, _login, _headers
    from tests.test_gui31_private_proof_trace import _compiled
    from tests.test_cimp_gui_14 import _composed_ciphertext_snapshot
    import integrations.ipfs_datasets.logic as logic
    world = _world(tmp_path)
    with TestClient(world.app, base_url='https://testserver') as client:
        csrf_token = _login(client)
        compiled = _compiled(client, world, csrf_token)
        before = _composed_ciphertext_snapshot(world.service)
        def unexpected_execution(*args, **kwargs):
            pytest.fail('read-only unavailable proof route executed an engine')
        monkeypatch.setattr(logic, 'compile_canonical_legal_ir', unexpected_execution)
        monkeypatch.setattr(logic, 'route_bound_legal_ir_proof', unexpected_execution)
        path = '/api/legal-analysis/'+world.case.case_id+'/proof-traces'
        response = client.get(path, headers=_headers(world))
        assert response.status_code == 200, response.text
        view = response.json()
        assert {row['obligation_id'] for row in view['obligations']} == {row['obligation_id'] for row in compiled['typed_obligations']}
        assert view['capabilities']['checked_kernel_backend_configured'] is False
        assert view['read_only'] is True and view['executed_proof'] is False
        assert view['engine_versions'] == [] and view['counterexamples'] == []
        assert all(not row['green_checkmark'] and not row['executed_proof'] for row in view['obligations'])
        forged = client.post(path, headers=_headers(world, csrf_token), json=proof_body(status='executed'))
        assert forged.status_code == 503 and forged.json()['error'] == 'proof_producer_unavailable'
        assert forged.json()['executed_proof'] is False
        assert _composed_ciphertext_snapshot(world.service) == before


@pytest.mark.parametrize('boundary', ['key_lock', 'corrupt_ciphertext'])
def test_actual_current_owner_missing_key_or_corrupt_snapshot_returns_no_cached_plaintext(tmp_path, boundary):
    from tests.gui_collaboration_fixtures import actual_unavailable_world
    from tests.test_cimp_gui_14 import _composed_headers, _composed_ciphertext_snapshot, NARRATIVE
    from tests.test_gui29_private_legal_analysis import _start
    world = actual_unavailable_world(tmp_path)
    with TestClient(world.app, base_url='https://testserver') as client:
        _start(client, world)
        path = '/api/graphs/'+world.case.case_id+'/factual'
        positive = client.get(path, headers=_composed_headers(world.case))
        assert positive.status_code == 200 and NARRATIVE in positive.text, positive.text
        if boundary == 'key_lock':
            assert world.service.lock_private_keys()['unlocked'] is False
        else:
            head = world.service.joined_revision_repository(world.case.tenant_id, world.case.case_id)/'head.cgpe'
            ciphertext = head.read_bytes()
            assert ciphertext.startswith(b'CGJH') and b'CGPE' in ciphertext and NARRATIVE.encode() not in ciphertext
            head.write_bytes(ciphertext[:-1]+bytes([ciphertext[-1] ^ 1]))
        before = _composed_ciphertext_snapshot(world.service)
        response = client.get(path, headers=_composed_headers(world.case))
        assert response.status_code == 503, response.text
        assert NARRATIVE not in response.text
        assert _composed_ciphertext_snapshot(world.service) == before


def test_actual_revoked_recipient_review_cannot_fall_back_to_locked_owner_wallet(tmp_path):
    from tests.test_gui46_private_owner_controls import _world, _change
    from tests.test_gui32_private_review_http import _headers, _propose, MARKER
    from tests.test_cimp_gui_14 import _composed_login, PASSPHRASE
    world = _world(tmp_path)
    assert not world.owner_keys.unlocked and not world.service._private_key_session().unlocked
    path = '/api/legal-analysis/'+world.case.case_id+'/lawyer-reviews'
    with TestClient(world.review_app, base_url='https://testserver') as lawyer, TestClient(world.review_app, base_url='https://testserver') as owner:
        lawyer_csrf = _composed_login(lawyer, 'synthetic-lawyer-credential')
        _propose(lawyer, world, lawyer_csrf)
        positive = lawyer.get(path, headers=_headers(world))
        assert positive.status_code == 200 and MARKER in positive.text, positive.text
        owner_csrf = _composed_login(owner)
        world.owner_keys.unlock_passphrase(PASSPHRASE)
        revoked, _body = _change(world, owner, owner_csrf, revoke=True, key='synthetic-57-public-revocation')
        assert revoked.status_code == 200 and revoked.json()['revoked'] is True, revoked.text
        world.owner_keys.lock()
        assert not world.service._private_key_session().unlocked
        denied = lawyer.get(path, headers=_headers(world))
        assert denied.status_code == 403 and MARKER not in denied.text, denied.text
        denied_write = lawyer.post(path, headers=_headers(world, lawyer_csrf),
            json={'interpretation':MARKER, 'request_id':'synthetic-57-revoked-write'})
        assert denied_write.status_code == 403 and MARKER not in denied_write.text


def test_actual_chromium_unavailable_model_proof_and_locked_graph_never_show_success(tmp_path, monkeypatch):
    import os
    from applications.case_consent_api import CaseConsentService
    from tests.test_cimp_gui_15 import _page
    from tests.test_gui16_current_privacy import _bind_actual_owner, _enter
    from tests.test_cimp_gui_16 import NARRATIVE
    with _page(tmp_path, monkeypatch, 'typed_owner') as (world, page):
        world.actual.app.state.case_consent = CaseConsentService(tmp_path/'actual-browser-consent',
            cases=world.actual.cases,key=os.urandom(32),key_id='synthetic-57-browser-consent',clock=lambda:1_700_000_100)
        _bind_actual_owner(page, world)
        _enter(page)
        choice = page.evaluate('''async caseId => {
            const path='/api/cases/'+encodeURIComponent(caseId)+'/processing-consent';
            const current=await (await fetch(path,{credentials:'same-origin'})).json();
            const response=await fetch(path,{method:'POST',credentials:'same-origin',
                headers:{'content-type':'application/json','x-csrf-token':workspaceClient.csrfToken},
                body:JSON.stringify({purpose:'extract_facts',mode:'grok_cloud',explicit_case_purpose:true,
                    expected_generation:current.generation})});
            return {status:response.status,body:await response.json()};
        }''', world.case.case_id)
        assert choice['status'] == 200
        assert any(row['purpose']=='extract_facts' and row['egress_authorized'] for row in choice['body']['decisions'])
        page.fill('#adaptive-model-fragment', 'supervisor Alex Rivera fired me')
        page.click('#adaptive-model-extract')
        page.wait_for_function("document.getElementById('adaptive-model-status').dataset.code === 'model_transport_unavailable'")
        assert page.get_attribute('#adaptive-model-status','data-model-dispatched') == 'false'
        assert 'Model not called' in page.locator('#adaptive-model-status').inner_text()
        page.fill('#proof-trace-case-id', world.case.case_id)
        page.click('#proof-trace-refresh')
        page.wait_for_function("document.getElementById('proof-trace-summary').dataset.verification === 'unavailable'")
        assert page.get_attribute('#proof-trace-summary','data-proof') == 'false'
        assert page.locator('#proof-trace-engines').inner_text() == 'No engine version recorded.'
        assert page.locator('[data-green-checkmark="true"]').count() == 0
        page.evaluate('async()=>{await refreshFactualGraphInspector();}')
        assert NARRATIVE in page.locator('#factual-graph-mount').inner_text()
        world.service.lock_private_keys()
        page.evaluate('async()=>{await refreshFactualGraphInspector();}')
        assert NARRATIVE not in page.locator('#factual-graph-mount').inner_text()
        assert page.get_attribute('#factual-graph-inspector','data-authorized') == 'false'
        page.click('#workspace-clear-private-state')
        page.wait_for_function("document.body.dataset.workspaceHydrated === 'cleared'")
        assert page.locator('#adaptive-model-fragment').input_value() == ''
        assert page.locator('#proof-trace-list').inner_text() == ''
