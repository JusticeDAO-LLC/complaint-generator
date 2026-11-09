"""Accepted answers and corrections update the canonical graphs once.

A reply carries the server question id and the revision the person was shown.
A stale or conflicting reply stays readable JSON, leaves the pending inquiry
and encrypted head alone, and cannot repaint another case or admitted law.
"""
from __future__ import annotations

import hashlib
import json
from contextlib import ExitStack
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from applications.browser_sessions import SESSION_COOKIE

from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import PASSPHRASE, _composed_headers, _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

NARRATIVE = ("My employer discriminated against me and denied my request for an accessible workplace on April 2, 2024. "
             "Under Oregon law. Applicable law date: 2024-06-01.")
LAW_TEXT = "An employer shall provide written notice to an employee before denying an accommodation."
LAW_CITATION = "Synthetic UX10 fixture notice rule"
LAW_VERSION = "synthetic-2024-edition"
ANSWER = "The denial was given in person by the office manager on April 2."
CORRECTION = "The denial was given in writing by the office manager on April 2."


def _legal_digest(graph):
    return json.dumps(graph or {}, sort_keys=True, default=str, separators=(",", ":"))


def _open(tmp_path, monkeypatch, *, world):
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux10-profile"
    profile.mkdir(mode=0o700)
    observed = set()

    def verify_startup_cleanup():
        observed.update(browser._with_descendants(browser._matching_pids((str(profile), node.argv[1]))))
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup["cleaned"] and cleanup["remaining_pids"] == [], "failed startup left owned browser processes"

    with ExitStack() as startup:
        startup.callback(verify_startup_cleanup)
        playwright = browser._load_sync_playwright()().start()
        startup.callback(playwright.stop)
        observed.update(browser._with_descendants(browser._matching_pids((node.argv[1],))))
        context = browser._launch_context(playwright, chromium.path, profile, bridge)
        startup.callback(context.close)
        observed.update(browser._with_descendants(browser._matching_pids((str(profile), node.argv[1]))))
        browser._assert_process_custody(node, chromium, profile)
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(20000)
        page.set_viewport_size({"width": 1440, "height": 1000})
        startup.pop_all()
    return page, playwright, context, node, profile, observed


def _close(playwright, context, node, profile, observed):
    context.close()
    playwright.stop()
    observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
    cleanup = browser._wait_for_cleanup(observed)
    assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
    assert cleanup["remaining_pids"] == []


def _provision_local_source(world, *, token):
    # Use the real issued owner, key session, source storage, source admission,
    # graph producer and encrypted head writer. Private derived-index tokens
    # are process-local, so complete admission before discarding this mediator;
    # the canonical encrypted projection owns the resulting source-bound graph.
    from applications.complaint_workspace import WorkspaceAccess, workspace_access_scope
    from applications.workspace_case_authority import issue_workspace_case_authority, workspace_case_authority_scope
    from complaint_phases.phase_manager import ComplaintPhase

    case = world.case
    decision = world.authorizer.authorize(boundary="http", actor_principal_id=world.owner.principal_id,
        tenant_id=case.tenant_id, case_id=case.case_id, resource_id=case.resource_id,
        action="case.update", expected_revision=case.revision)
    authority = issue_workspace_case_authority(authorizer=world.authorizer, sessions=world.sessions,
        token=token, decision=decision, registry=world.app.state.case_handlers)
    with workspace_case_authority_scope(authority), workspace_access_scope(
            WorkspaceAccess.authenticated(world.owner.principal_id, case_id=case.case_id)):
        state = world.service._load_state(case.tenant_id, case_id=case.case_id)
        mediator = world.service._mediator_for_shared_interview(case.tenant_id, case.case_id, cache=False)
        mediator.workflow_actions.restore_session_projection(state["shared_interview"])
        knowledge = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
        claims = [{"type": entity.attributes["claim_type"], "name": entity.name,
                   "description": entity.attributes.get("description", "")}
                  for entity in knowledge.get_entities_by_type("claim")]
        assert claims and all(row["type"] != "unknown" for row in claims)
        source = {
            "type": "statute", "source": "authored-local-test-corpus", "title": "Synthetic notice rule",
            "citation": LAW_CITATION, "content": LAW_TEXT, "jurisdiction": "OR",
            "metadata": {
                "source_text": LAW_TEXT, "source_hash": hashlib.sha256(LAW_TEXT.encode()).hexdigest(),
                "authority_id": "synthetic-ux10-notice", "authority_version": LAW_VERSION,
                "effective_date": "2024-01-01", "as_of_date": "2024-06-01",
                "provenance": {"source_id": "synthetic-ux10-notice"},
            },
        }
        for claim_type in {row["type"] for row in claims}:
            stored = mediator.legal_authority_storage.add_authority(source, case.tenant_id, claim_type=claim_type)
            assert stored > 0
        case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file")
        requirements = mediator._collect_verified_legal_requirements(claims, case_file)
        assert any(requirements.values()), {"claim_types": list(requirements),
            "source_status": mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "legal_source_status")}
        graph = mediator.dg_builder.build_from_claims(claims, legal_requirements=requirements,
            require_verified_legal_sources=True)
        _assert_source_bound_law(graph.to_dict())
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "dependency_graph", graph)
        state["shared_interview"] = mediator.workflow_actions.export_session_projection()
        world.service._commit_joined_snapshot(state)


def _assert_source_bound_law(graph):
    nodes = graph.get("nodes") or {}
    matching = [node for node in nodes.values()
        if node.get("node_type") == "legal_element"
        and (node.get("attributes") or {}).get("dependency_class") == "legally_sourced_requirement"
        and (node.get("attributes") or {}).get("citation") == LAW_CITATION]
    assert matching, {"message": "the actual source admission did not produce a legal requirement",
        "metadata": graph.get("metadata"),
        "node_classes": [(node.get("node_type"), (node.get("attributes") or {}).get("dependency_class"),
            (node.get("attributes") or {}).get("reason")) for node in nodes.values()]}
    for node in matching:
        attrs = node["attributes"]
        assert attrs["source_available"] is True
        assert attrs["support_eligible"] is True
        assert attrs["source_hash"] == hashlib.sha256(LAW_TEXT.encode()).hexdigest()
        assert attrs["authority_version"] == LAW_VERSION
        assert attrs["temporal_applicability"]["applicable"] is True
        assert attrs["law_derived"] is False
        span = attrs["source_span"]
        assert LAW_TEXT.encode()[span["start"]:span["end"]].decode() == attrs["rule_text"]


def _assert_factual_statement(graph, statement, *, status):
    states = ((graph.get("metadata") or {}).get("factual_ledger") or {}).get("assertion_states") or {}
    matching = [row for row in states.values()
        if (row.get("envelope") or {}).get("source_text") == statement and row.get("status") == status]
    assert matching, f"the persisted factual graph lacks the {status} statement"
    for row in matching:
        envelope = row["envelope"]
        assert envelope["is_asserted_user_fact"] is True
        entity = graph["entities"][row["entity_id"]]
        assert entity["provenance"]["user_assertion"]["source_text"] == statement
    return matching


def _rpc_arguments(request, action):
    if request.method != "POST" or not request.url.endswith("/api/complaint-workspace/mcp/rpc"):
        return None
    body = json.loads(request.post_data or "{}")
    params = body.get("params") or {}
    arguments = params.get("arguments") or {}
    if (body.get("method") == "tools/call" and params.get("name") == "complaint.run_intake_chat_turn"
            and arguments.get("interview_action") == action):
        return arguments
    return None


def _rpc_payload(response):
    body = response.json()
    result = body["result"]
    return result.get("structuredContent", result)


def _seed(world):
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        headers = _composed_headers(world.case, csrf)
        started = client.post(
            "/api/complaint-workspace/intake-chat",
            headers=headers,
            json={"message": NARRATIVE, "interview_action": "start", "question_id": "original_complaint"},
        )
        assert started.status_code == 200, started.text
        current = client.get(f"/api/legal-context/{world.case.case_id}", headers=headers)
        assert current.status_code == 200
        selected = client.post(f"/api/legal-context/{world.case.case_id}", headers=headers,
            json={"expected_context_revision": current.json()["context_revision"],
                  "jurisdiction": "Oregon", "forum": "synthetic-fixture-forum", "applicability": "explicit",
                  "applicable_law_date": "2024-06-01", "event_date": "2024-04-02"})
        assert selected.status_code == 200, selected.text
        _provision_local_source(world, token=client.cookies.get(SESSION_COOKIE))
        actual = client.get('/api/complaint-workspace/session', headers=headers)
        assert actual.status_code == 200
        body = actual.json()
        session = body["session"]
        pending = session["shared_interview"]["pending_inquiry"]
        _assert_source_bound_law(session["shared_interview"]["dependency_graph"])
        return {
            "inquiry_id": pending["inquiry_id"],
            "revision": pending["revision"],
            "question": pending["question"],
            "legal": _legal_digest(session["shared_interview"].get("dependency_graph")),
            "graph": _legal_digest(session["shared_interview"].get("knowledge_graph")),
            "head": body["encrypted_head"]["private_revision"],
            "case_id": session.get("case_id") or world.case.case_id,
        }


def _sign_in(page, *, case_label="owner-lawyer-journey"):
    page.goto(browser.SAME_ORIGIN + "/cases", wait_until="domcontentloaded")
    page.fill("#case-credential", "synthetic-owner-credential")
    with page.expect_response(lambda response: response.request.method == "POST"
            and response.url.endswith("/api/complaint-workspace/auth/login")):
        page.click("#case-login button[type=submit]")
    page.locator("#case-list").get_by_role("button", name=case_label, exact=True).click()
    page.wait_for_function("""() => document.getElementById('complaint-case-shell-actor').dataset.relationship === 'owner'""")


def _workspace(page, inquiry_id):
    page.goto(browser.SAME_ORIGIN + "/workspace", wait_until="domcontentloaded")
    page.wait_for_function("""(inquiryId) => {
        const card = document.getElementById('inquiry-card');
        return card && card.dataset.pending === 'true' && card.dataset.inquiryId === inquiryId
            && document.getElementById('adaptive-submit-answer');
    }""", arg=inquiry_id)
    page.locator('#complaint-case-shell-nav [data-case-task="mediator"]').click()
    page.locator('[data-case-panel="mediator"] #adaptive-answer').wait_for(state="visible")


def _server_graphs(page, *, case=None):
    binding = None if case is None else {"tenant_id": case.tenant_id, "case_id": case.case_id,
        "resource_id": case.resource_id, "directory_revision": case.revision}
    return page.evaluate("""async (explicitBinding) => {
        const binding = explicitBinding || window.complaintCaseShell.binding();
        const response = await fetch('/api/complaint-workspace/session?case_id=' + encodeURIComponent(binding.case_id), {
            credentials: 'same-origin',
            headers: {
                'x-case-id': binding.case_id,
                'x-tenant-id': binding.tenant_id,
                'x-resource-id': binding.resource_id,
                'x-expected-revision': String(binding.directory_revision),
            },
        });
        const body = await response.json();
        const session = body.session || {};
        const interview = session.shared_interview || {};
        const pending = interview.pending_inquiry || {};
        const projection = body.affected_support_projection || session.affected_support_projection || [];
        return {
            status: response.status,
            caseId: session.case_id || '',
            inquiryId: pending.inquiry_id || '',
            revision: pending.revision,
            question: pending.question || '',
            head: (body.encrypted_head || {}).private_revision || String(session.private_revision || ''),
            supportCount: projection.length,
            effects: projection.map((item) => item.effect_id),
            changesLaw: projection.some((item) => item.changes_law === true),
            legal: JSON.stringify(interview.dependency_graph || {}),
            factual: JSON.stringify(interview.knowledge_graph || {}),
            offer: ((body.adaptive_inquiry || {}).factual_correction) || {},
        };
    }""", binding)


def test_answer_and_correction_update_graphs_once_and_stale_replies_do_not(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "world")
    seeded = _seed(world)
    page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch, world=world)
    posted = []

    def remember(request):
        arguments = _rpc_arguments(request, "answer")
        if arguments is not None:
            posted.append(arguments)

    try:
        _sign_in(page)
        _workspace(page, seeded["inquiry_id"])
        page.on("request", remember)
        page.fill("#adaptive-answer", ANSWER)
        with page.expect_response(lambda response: _rpc_arguments(response.request, "answer") is not None) as answer_response:
            page.click("#adaptive-submit-answer")
        actual_answer = answer_response.value
        assert actual_answer.status == 200
        answer_payload = _rpc_payload(actual_answer)
        assert answer_payload["support_projection_updated"] is True, json.dumps({
            "interview": answer_payload.get("interview"), "conflict": answer_payload.get("conflict"),
            "updated": answer_payload.get("support_projection_updated"),
        }, sort_keys=True)
        try:
            page.wait_for_function("""() => {
                const node = document.getElementById('inquiry-graph-change');
                return node && node.dataset.applied === 'true' && node.dataset.changesLaw === 'false';
            }""")
        except Exception as exc:
            state = page.evaluate("""() => ({
                change: (document.getElementById('inquiry-graph-change') || {}).outerHTML || null,
                card: document.getElementById('inquiry-card').outerHTML,
                shell: window.complaintCaseShell.snapshot(),
                privacyActive: window.workspaceClient._privacyActive,
                privacyEpoch: window.workspaceClient._privacyEpoch,
                context: window.workspaceClient.caseContext,
            })""")
            raise AssertionError("The actual accepted answer did not render: " + json.dumps(state, sort_keys=True)) from exc
        shown = page.evaluate("""() => {
            const card = document.getElementById('inquiry-card');
            const change = document.getElementById('inquiry-graph-change');
            return {
                inquiryId: card.dataset.inquiryId,
                revision: card.dataset.revision,
                changeText: document.getElementById('inquiry-graph-change-text').textContent,
                count: change.dataset.count,
                caseId: change.dataset.caseId,
            };
        }""")
        assert posted, "the answer was not submitted"
        assert len(posted) == 1, "one answer click must issue one answer RPC"
        arguments = posted[0]
        assert arguments["question_id"] == seeded["inquiry_id"]
        assert arguments["expected_question_revision"] == seeded["revision"]
        assert arguments["interview_action"] == "answer"
        assert arguments["message"] == ANSWER
        after = _server_graphs(page)
        assert after["status"] == 200
        assert after["supportCount"] == 1
        assert after["effects"] == [f"answer:{seeded['inquiry_id']}:{seeded['revision']}"]
        assert after["changesLaw"] is False
        _assert_source_bound_law(json.loads(after["legal"]))
        assert json.loads(after["legal"]) == json.loads(seeded["legal"])
        assert json.loads(after["factual"]) != json.loads(seeded["graph"])
        _assert_factual_statement(json.loads(after["factual"]), ANSWER, status="active")
        assert after["offer"]["schema"] == "gui-factual-correction-v1"
        assert after["offer"]["requires_expected_revision"] is True
        assert after["offer"]["prior_answer"] == ANSWER
        assert after["offer"]["target_stable_id"]
        assert after["inquiryId"] == shown["inquiryId"]
        assert after["inquiryId"] != seeded["inquiry_id"] or after["revision"] != seeded["revision"]
        assert "factual graph was updated once" in shown["changeText"]
        head_after_answer = after["head"]
        pending_after_answer = after["inquiryId"]
        stale = page.evaluate("""async (prior) => {
            const client = window.workspaceClient;
            const userId = (client.caseContext && client.caseContext.tenant_id) || '';
            const result = await client.submitCanonicalGraphAnswer(userId, prior.answer + ' stale', {
                question_id: prior.inquiryId,
                expected_question_revision: prior.revision,
            });
            const card = document.getElementById('inquiry-card');
            return {
                accepted: result.accepted,
                conflict: result.conflict,
                readable: result.payload && typeof result.payload === 'object',
                payloadConflict: result.payload && result.payload.conflict,
                cardInquiry: card.dataset.inquiryId,
                cardRevision: card.dataset.revision,
                keptHead: (result.payload && result.payload.encrypted_head && result.payload.encrypted_head.private_revision) || '',
                keptInquiry: ((result.payload && result.payload.session && result.payload.session.shared_interview && result.payload.session.shared_interview.pending_inquiry) || {}).inquiry_id || '',
            };
        }""", {"answer": ANSWER, "inquiryId": seeded["inquiry_id"], "revision": seeded["revision"]})
        assert stale["accepted"] is False
        assert stale["readable"] is True
        assert stale["conflict"] == "stale_question"
        assert stale["payloadConflict"] == "stale_question"
        assert stale["cardInquiry"] == pending_after_answer
        assert stale["keptInquiry"] == pending_after_answer
        assert stale["keptHead"] == head_after_answer
        still = _server_graphs(page)
        assert still["supportCount"] == 1
        assert still["head"] == head_after_answer
        assert still["inquiryId"] == pending_after_answer
        assert still["legal"] == after["legal"]
        assert still["factual"] == after["factual"]
        _assert_source_bound_law(json.loads(still["legal"]))
        foreign = page.evaluate("""() => {
            const card = document.getElementById('inquiry-card');
            const before = card.dataset.inquiryId;
            window.complaintConversation.project({
                conflict: null,
                session: {
                    case_id: 'case-newer-than-the-open-case',
                    shared_interview: {pending_inquiry: {inquiry_id: 'inq-foreign', revision: 9, question: 'A different case question'}},
                },
                encrypted_head: {case_id: 'case-newer-than-the-open-case', private_revision: '0'},
            });
            return {before: before, after: card.dataset.inquiryId, question: document.getElementById('inquiry-card-question').textContent};
        }""")
        assert foreign["after"] == foreign["before"]
        assert "different case" not in foreign["question"]
        unchanged = _server_graphs(page)
        assert unchanged["head"] == head_after_answer
        assert unchanged["factual"] == after["factual"]
        assert unchanged["legal"] == after["legal"]
        assert page.input_value("#factual-correction-graph-revision") == after["offer"]["expected_graph_revision"]
        assert page.input_value("#factual-correction-session-revision") == str(after["offer"]["expected_session_revision"])
        assert page.input_value("#factual-correction-target") == after["offer"]["target_stable_id"]
        assert page.input_value("#factual-correction-actor") == after["offer"]["actor_principal_id"]
        page.fill("#factual-correction-replacement", CORRECTION)
        with page.expect_response(lambda response: _rpc_arguments(response.request, "correct") is not None) as actual:
            page.click("#factual-correction-submit")
        response = actual.value
        assert response.status == 200
        payload = _rpc_payload(response)
        receipt = payload["factual_correction"]
        assert receipt["status"] == "applied", json.dumps({
            "status": receipt["status"], "error": receipt.get("error"), "message": receipt.get("message"),
            "submitted": json.loads(_rpc_arguments(response.request, "correct")["message"]),
            "offered": after["offer"],
        }, sort_keys=True)
        assert receipt["correction"]["lineage"]["previous_envelope_retained"] is True
        assert receipt["correction"]["lineage"]["previous_status"] == "superseded"
        assert payload["support_projection_updated"] is True
        assert payload["support_projection_duplicate"] is False
        assert len(payload["affected_support_projection"]) == 2
        page.wait_for_function("""() => {
            const node = document.getElementById('inquiry-graph-change');
            return node && node.dataset.applied === 'true' && node.dataset.count === '2'
                && !node.dataset.conflict && node.dataset.effectId.startsWith('correction:');
        }""")
        corrected = _server_graphs(page)
        assert corrected["status"] == 200
        assert corrected["changesLaw"] is False
        _assert_source_bound_law(json.loads(corrected["legal"]))
        assert json.loads(corrected["legal"]) == json.loads(after["legal"])
        assert corrected["supportCount"] == 2
        assert corrected["effects"][0] == after["effects"][0]
        assert corrected["effects"][1].startswith("correction:")
        assert len(set(corrected["effects"])) == 2
        assert corrected["head"] != head_after_answer
        assert corrected["factual"] != after["factual"]
        corrected_graph = json.loads(corrected["factual"])
        _assert_factual_statement(corrected_graph, ANSWER, status="superseded")
        _assert_factual_statement(corrected_graph, CORRECTION, status="active")
        replay = page.evaluate("""async (fields) => {
            const client = window.workspaceClient;
            const userId = (client.caseContext && client.caseContext.tenant_id) || '';
            const result = await client.submitCanonicalGraphCorrection(userId, fields.replacement, fields);
            return {accepted: result.accepted, conflict: result.conflict, readable: typeof result.payload === 'object'};
        }""", {
            "replacement": CORRECTION,
            "expected_graph_revision": after["offer"]["expected_graph_revision"],
            "expected_session_revision": after["offer"]["expected_session_revision"],
            "target_stable_id": after["offer"]["target_stable_id"],
            "actor_principal_id": after["offer"]["actor_principal_id"],
            "question_id": after["offer"]["target_stable_id"],
        })
        assert replay["accepted"] is False
        assert replay["conflict"] == "stale_target"
        assert replay["readable"] is True
        replayed = _server_graphs(page)
        assert replayed["status"] == 200
        assert replayed["supportCount"] == 2
        assert replayed["effects"] == corrected["effects"]
        assert replayed["legal"] == corrected["legal"]
        assert replayed["head"] == corrected["head"]
        assert replayed["factual"] == corrected["factual"]
    finally:
        _close(playwright, context, node, profile, observed)



def _second_case(world, tmp_path):
    from applications.complaint_workspace import ComplaintWorkspaceService

    created = world.app.state.case_catalog.create(world.owner.principal_id,
        {"label": "late-answer-second-case"})
    case = world.cases.select_case(actor_principal_id=world.owner.principal_id, case_id=created["case_id"])
    service = ComplaintWorkspaceService(root_dir=tmp_path / "second-workspace")
    service.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
    service.ensure_private_case_key(case.tenant_id, case.case_id)
    world.reviews.bind_case(case, service)
    world.app.state.case_handlers.bind(case, mediator=service, workspace_service=service,
        authorize_delegated=world.reviews.authorize_bound)
    return SimpleNamespace(**{**vars(world), "case": case, "service": service})


def _inquiry_dom(page):
    return page.evaluate("""() => ({
        caseId: document.getElementById('complaint-case-shell-case').dataset.caseId,
        inquiry: document.getElementById('inquiry-card').outerHTML,
        conversation: document.getElementById('mediator-conversation-log').innerHTML,
        change: (document.getElementById('inquiry-graph-change') || {}).outerHTML || null,
    })""")


def test_delayed_answer_cannot_repaint_a_new_selected_case(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "world")
    first = _seed(world)
    second_world = _second_case(world, tmp_path)
    second = _seed(second_world)
    page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch, world=world)
    try:
        _sign_in(page)
        _workspace(page, first["inquiry_id"])
        # Delegate to the real SDK transport and hold only delivery of the
        # actual accepted ASGI response. No response or authority is invented.
        page.evaluate("""() => {
            const client = window.workspaceClient;
            const transport = client.fetchImpl;
            const submit = client.submitCanonicalGraphAnswer;
            let hold = true;
            window.__ux10Restore = () => {
                client.fetchImpl = transport;
                client.submitCanonicalGraphAnswer = submit;
            };
            client.fetchImpl = async function(input, options) {
                const response = await transport.call(this, input, options);
                const path = new URL(typeof input === 'string' ? input : input.url, location.origin).pathname;
                const body = options && options.body ? JSON.parse(options.body) : {};
                const params = body.params || {};
                if (hold && path === '/api/complaint-workspace/mcp/rpc'
                        && body.method === 'tools/call' && params.name === 'complaint.run_intake_chat_turn'
                        && (params.arguments || {}).interview_action === 'answer') {
                    hold = false;
                    const body = await response.clone().json();
                    const result = body.result || {};
                    const actual = result.structuredContent || result;
                    window.__ux10Held = {status: response.status,
                        caseId: (actual.session || {}).case_id,
                        conflict: actual.conflict || null};
                    await new Promise(resolve => { window.__ux10Release = resolve; });
                }
                return response;
            };
            client.submitCanonicalGraphAnswer = function(...args) {
                const pending = submit.apply(this, args);
                window.__ux10AnswerSettled = pending.then(
                    result => ({accepted: result.accepted, conflict: result.conflict}),
                    error => ({error: error.code || error.message}));
                return pending;
            };
        }""")
        page.fill("#adaptive-answer", ANSWER)
        page.click("#adaptive-submit-answer")
        page.wait_for_function("() => Boolean(window.__ux10Held)")
        held = page.evaluate("() => window.__ux10Held")
        assert held == {"status": 200, "caseId": world.case.case_id, "conflict": None}
        with page.expect_response(lambda response: response.request.method == "POST"
                and response.url.endswith(f"/api/cases/{second_world.case.case_id}/select")) as selected:
            page.select_option("#complaint-case-shell-catalog", second_world.case.case_id)
        assert selected.value.status == 200
        page.wait_for_function("""expected => {
            const binding = window.complaintCaseShell.binding();
            const card = document.getElementById('inquiry-card');
            return binding && binding.case_id === expected.caseId
                && document.getElementById('complaint-case-shell-case').dataset.caseId === expected.caseId
                && card.dataset.inquiryId === expected.inquiryId;
        }""", arg={"caseId": second_world.case.case_id, "inquiryId": second["inquiry_id"]})
        before_dom = _inquiry_dom(page)
        before = _server_graphs(page)
        assert before["status"] == 200 and before["caseId"] == second_world.case.case_id
        assert before["supportCount"] == 0
        _assert_source_bound_law(json.loads(before["legal"]))
        settled = page.evaluate("""async () => {
            window.__ux10Release();
            const settled = await window.__ux10AnswerSettled;
            await new Promise(resolve => setTimeout(resolve, 0));
            window.__ux10Restore();
            return settled;
        }""")
        assert settled.get("error") == "workspace_state_changed", settled
        assert _inquiry_dom(page) == before_dom, "the retired answer repainted the newly selected case"
        after = _server_graphs(page)
        assert after == before
        assert ANSWER not in page.locator("#mediator-conversation-log").inner_text()
        # The answer was genuinely stored in the old case once, despite its
        # delivery being retired. The new case did not receive its fact/effect.
        old = _server_graphs(page, case=world.case)
        assert old["status"] == 200 and old["supportCount"] == 1
        assert old["effects"] == [f"answer:{first['inquiry_id']}:{first['revision']}"]
        _assert_factual_statement(json.loads(old["factual"]), ANSWER, status="active")
        _assert_source_bound_law(json.loads(old["legal"]))
        assert json.loads(old["legal"]) == json.loads(first["legal"])
    finally:
        if not page.is_closed():
            page.evaluate("""() => {
                if (window.__ux10Release) window.__ux10Release();
                if (window.__ux10Restore) window.__ux10Restore();
            }""")
        _close(playwright, context, node, profile, observed)
