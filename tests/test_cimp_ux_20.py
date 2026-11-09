"""Evidence spans link to current facts or sourced requirements.

ClaimSupportHook owns the fact and support rows. Explicit human acceptance
can record corroboration or contradiction. A checkbox or classifier does not
become verified legal support, and a missing target stays unavailable.
"""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from integrations.evidence_workspace import MemoryByteBackend, support_targets_from_context
from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import _composed_headers, _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

ASSERTION = "notice-received"
REQUIREMENT = "written-notice-21"
PASSAGE = "passage-notice-21"


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


def _context(graph_revision="facts-1", source_version="ord-2024-1"):
    return {
        "legal_context_status": "admitted",
        "context_owner": "request",
        "factual_graph_revision": graph_revision,
        "source_version": source_version,
        "jurisdiction": "Example County",
        "authority_version": "auth-v3",
        "factual_assertions": [{
            "assertion_id": ASSERTION,
            "text": "The notice was received on 3 March.",
            "status": "current",
            "graph_revision": graph_revision,
        }],
        "admitted_requirements": [{
            "requirement_id": REQUIREMENT,
            "passage_id": PASSAGE,
            "label": "Written notice within 21 days",
            "source_version": source_version,
            "jurisdiction": "Example County",
            "authority_version": "auth-v3",
            "admitted_law": True,
        }],
    }


def _identity(case, evidence_id, **extra):
    body = {
        "tenant_id": case.tenant_id,
        "case_id": case.case_id,
        "resource_id": case.resource_id,
        "evidence_id": evidence_id,
        "artifact_version": 1,
        "expected_case_revision": case.revision,
    }
    body.update(extra)
    return body


def _receive(workspace, case, actor):
    return workspace.receive(actor, {
        "tenant_id": case.tenant_id,
        "case_id": case.case_id,
        "resource_id": case.resource_id,
        "source_filename": "notice.txt",
        "original_filename": "notice.txt",
        "media_type": "text/plain",
        "content_base64": base64.b64encode(b"Notice text for a synthetic case.\n").decode("ascii"),
        "idempotency_key": "ux20-evidence",
    })


def _span(**extra):
    body = {"page": 2, "span_start": 10, "span_end": 28}
    body.update(extra)
    return body


def test_targets_keep_only_current_assertions_and_sourced_requirements():
    offered = support_targets_from_context(_context())
    assert [item["target_id"] for item in offered["factual_assertions"]] == [ASSERTION]
    assert [item["target_id"] for item in offered["sourced_requirements"]] == [REQUIREMENT]
    assert offered["establishes_legal_support"] is False
    assert offered["admission_verified_by_evidence_workspace"] is False

    stale = support_targets_from_context({
        **_context(),
        "factual_assertions": [
            {"assertion_id": ASSERTION, "text": "The notice was received on 3 March.", "status": "superseded", "graph_revision": "facts-1"},
            {"assertion_id": "protected_activity", "text": "Protected activity", "status": "current", "graph_revision": "facts-1"},
            {"assertion_id": "other-fact", "text": "A different graph.", "status": "current", "graph_revision": "facts-9"},
        ],
        "admitted_requirements": [{
            "requirement_id": "causation", "passage_id": "p-hr", "label": "HR causation",
            "source_version": "ord-2024-1", "jurisdiction": "Example County",
            "authority_version": "auth-v3", "admitted_law": True,
        }],
    })
    assert stale["factual_assertions"] == []
    assert stale["sourced_requirements"] == []


def test_explicit_acceptance_links_span_through_claim_support_hook(tmp_path):
    world = _ready(tmp_path)
    workspace = world.app.state.evidence_workspace
    actor = world.owner.principal_id
    evidence_id = _receive(workspace, world.case, actor)["evidence_id"]
    context = _context()

    allegation = workspace.record_support_link(actor, _identity(
        world.case, evidence_id, posture="allegation", origin="human_statement",
        target_kind="factual_assertion", target_id=ASSERTION, case_context=context,
        idempotency_key="ux20-allegation", **_span(),
    ))
    assert allegation["posture"] == "allegation"
    assert allegation["explicit_acceptance"] is False
    assert allegation["accepted"] is False
    assert allegation["span_ref"] == "page:2:10-28"
    assert allegation["artifact_version"] == 1
    assert allegation["page"] == 2
    assert allegation["verified_legal_support"] is False
    assert allegation["establishes_legal_support"] is False
    assert allegation["fact_id"]
    assert allegation["actor_principal_id"] == actor
    assert allegation["canonical_owner_principal_id"] == world.case.tenant_id

    hypothesis = workspace.record_support_link(actor, _identity(
        world.case, evidence_id, posture="hypothesis", origin="ai_suggested",
        target_kind="sourced_requirement", target_id=REQUIREMENT,
        model_id="synthetic-model", invocation_id="invoke-20",
        case_context=context, idempotency_key="ux20-hypothesis", **_span(span_start=30, span_end=40),
    ))
    assert hypothesis["posture"] == "hypothesis"
    assert hypothesis["accepted"] is False
    assert hypothesis["model_id"] == "synthetic-model"
    assert hypothesis["verified_legal_support"] is False

    refused = None
    try:
        workspace.record_support_link(actor, _identity(
            world.case, evidence_id, posture="corroboration", origin="human_acceptance",
            accept=True, client_checkbox=True, target_kind="factual_assertion", target_id=ASSERTION,
            case_context=context, idempotency_key="ux20-checkbox", **_span(),
        ))
    except Exception as exc:
        refused = getattr(exc, "code", "")
    assert refused == "support_link_rejected"

    refused_classifier = None
    try:
        workspace.record_support_link(actor, _identity(
            world.case, evidence_id, posture="corroboration", origin="human_acceptance",
            accept=True, classifier_id="cl-existing", target_kind="factual_assertion", target_id=ASSERTION,
            case_context=context, idempotency_key="ux20-classifier", **_span(),
        ))
    except Exception as exc:
        refused_classifier = getattr(exc, "code", "")
    assert refused_classifier == "support_link_rejected"

    corroborated = workspace.record_support_link(actor, _identity(
        world.case, evidence_id, posture="corroboration", origin="human_acceptance", accept=True,
        target_kind="factual_assertion", target_id=ASSERTION, case_context=context,
        idempotency_key="ux20-corroboration", **_span(span_start=40, span_end=55),
    ))
    assert corroborated["explicit_acceptance"] is True
    assert corroborated["posture"] == "corroboration"
    assert corroborated["verified_legal_support"] is False
    assert corroborated["governing_law"] is False
    assert "to_chunk" or corroborated["hook_link_ids"]

    contradicted = workspace.record_support_link(actor, _identity(
        world.case, evidence_id, posture="contradiction", origin="human_acceptance", accept=True,
        target_kind="sourced_requirement", target_id=REQUIREMENT, case_context=context,
        idempotency_key="ux20-contradiction", **_span(page=3, span_start=1, span_end=12),
    ))
    assert contradicted["posture"] == "contradiction"
    assert contradicted["passage_id"] == PASSAGE
    assert contradicted["explicit_acceptance"] is True
    assert contradicted["verified_legal_support"] is False

    replay = workspace.record_support_link(actor, _identity(
        world.case, evidence_id, posture="contradiction", origin="human_acceptance", accept=True,
        target_kind="sourced_requirement", target_id=REQUIREMENT, case_context=context,
        idempotency_key="ux20-contradiction", **_span(page=3, span_start=1, span_end=12),
    ))
    assert replay["idempotent_replay"] is True
    assert replay["support_link_id"] == contradicted["support_link_id"]

    facts = workspace.claim_support.get_fact_records(world.case.tenant_id, include_links=True)
    by_span = {row["span_ref"]: row for row in facts}
    assert by_span["page:2:10-28"]["source_artifact_id"] == evidence_id
    assert by_span["page:2:10-28"]["validation_state"] == "unvalidated"
    assert by_span["page:2:30-40"]["uncertainty_flag"] is True
    assert by_span["page:2:40-55"]["validation_state"] == "unvalidated"
    assert by_span["page:3:1-12"]["contradiction_flag"] is True
    assert by_span["page:3:1-12"]["chunk_ref"] == f"artifact:{evidence_id}:version:1:page:3:1-12"
    chunk_links = [link for link in by_span["page:2:40-55"]["links"] if link["link_kind"] == "to_chunk"]
    assert chunk_links
    assert chunk_links[0]["target_id"].endswith("page:2:40-55")
    assert chunk_links[0]["metadata"]["verified_legal_support"] is False
    assert chunk_links[0]["metadata"]["explicit_acceptance"] is True
    authority_links = [link for link in by_span["page:3:1-12"]["links"] if link["link_kind"] == "to_authority"]
    assert authority_links[0]["target_id"] == REQUIREMENT
    support_rows = workspace.claim_support.get_support_links(world.case.tenant_id, "evidence_span_support")
    assert {row["support_kind"] for row in support_rows} >= {"allegation", "hypothesis", "corroboration", "contradiction"}
    assert all(float(row["support_strength"] or 0) == 0.0 for row in support_rows)

    missing = workspace.record_support_link(actor, _identity(
        world.case, evidence_id, posture="allegation", origin="human_statement",
        target_kind="factual_assertion", target_id="not-current", case_context=context,
        idempotency_key="ux20-missing", **_span(span_start=60, span_end=70),
    ))
    assert missing["posture"] == "unavailable"
    assert missing["operation_succeeded"] is False
    assert missing["recorded"] is False
    assert missing["reason"] == "target_not_current"
    assert "page:2:60-70" not in {row["span_ref"] for row in workspace.claim_support.get_fact_records(world.case.tenant_id)}

    changed = _context(graph_revision="facts-2", source_version="ord-2025-2")
    offered = workspace.offer_support_links(actor, _identity(world.case, evidence_id, case_context=changed))
    assert {row["support_link_id"] for row in offered["retired"]} >= {
        allegation["support_link_id"], hypothesis["support_link_id"],
        corroborated["support_link_id"], contradicted["support_link_id"],
    }
    assert offered["corroborations"] == []
    assert offered["establishes_legal_support"] is False
    assert all(row["verified_legal_support"] is False for row in offered["retired"])


def test_http_checkbox_and_classifier_do_not_verify_support(tmp_path):
    world = _ready(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        received = client.post(
            "/api/cases/evidence",
            headers=_composed_headers(world.case, csrf),
            json={
                "tenant_id": world.case.tenant_id,
                "case_id": world.case.case_id,
                "resource_id": world.case.resource_id,
                "source_filename": "notice.txt",
                "original_filename": "notice.txt",
                "media_type": "text/plain",
                "content_base64": base64.b64encode(b"Notice text for a synthetic case.\n").decode("ascii"),
                "idempotency_key": "ux20-http-evidence",
            },
        )
        assert received.status_code == 201, received.text
        evidence_id = received.json()["evidence_id"]
        headers = _composed_headers(world.case, csrf)
        context = _context()
        checkbox = client.post(
            "/api/cases/evidence/support-links",
            headers=headers,
            json=_identity(
                world.case, evidence_id, posture="corroboration", origin="human_acceptance",
                accept=True, client_checkbox=True, verified_legal_support=True,
                target_kind="factual_assertion", target_id=ASSERTION, case_context=context,
                idempotency_key="ux20-http-checkbox", **_span(),
            ),
        )
        assert checkbox.status_code == 400
        assert checkbox.json()["error"] == "support_link_rejected"
        assert checkbox.json()["operation_succeeded"] is False
        assert checkbox.json()["legal"]["claim_support"] == "not_established"

        labeled = client.post(
            "/api/cases/evidence/classifications",
            headers=headers,
            json=_identity(
                world.case, evidence_id, origin="user_label", label="desk-copy",
                idempotency_key="ux20-http-label", case_context={"legal_context_status": "unknown"},
            ),
        )
        assert labeled.status_code == 201, labeled.text
        offered = client.post(
            "/api/cases/evidence/support-links/offer",
            headers=headers,
            json=_identity(world.case, evidence_id, case_context=context),
        )
        assert offered.status_code == 200, offered.text
        body = offered.json()
        assert body["allegations"] == []
        assert body["corroborations"] == []
        assert body["classifier_mints_support"] is False
        assert [item["target_id"] for item in body["factual_assertions"]] == [ASSERTION]

        saved = client.post(
            "/api/cases/evidence/support-links",
            headers=headers,
            json=_identity(
                world.case, evidence_id, posture="corroboration", origin="human_acceptance", accept=True,
                target_kind="sourced_requirement", target_id=REQUIREMENT, case_context=context,
                idempotency_key="ux20-http-accept", **_span(page=4, span_start=2, span_end=9),
            ),
        )
        assert saved.status_code == 201, saved.text
        saved_body = saved.json()
        assert saved_body["explicit_acceptance"] is True
        assert saved_body["verified_legal_support"] is False
        assert saved_body["span_ref"] == "page:4:2-9"
        assert saved_body["canonical_owner_principal_id"] == world.case.tenant_id
        facts = world.app.state.evidence_workspace.claim_support.get_fact_records(world.case.tenant_id)
        assert any(row["span_ref"] == "page:4:2-9" and row["source_artifact_id"] == evidence_id for row in facts)


def _browser(world, tmp_path, monkeypatch):
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    bridge = browser.SameOriginAsgiBridge(world.app)
    world.browser_bridge = bridge
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux20-profile"
    profile.mkdir(mode=0o700)
    playwright = browser._load_sync_playwright()().start()
    context = browser._launch_context(playwright, chromium.path, profile, bridge)
    browser._assert_process_custody(node, chromium, profile)
    observed = set(browser._with_descendants(browser._matching_pids((str(profile), node.argv[1]))))
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(15000)
    page.set_viewport_size({"width": 1440, "height": 1000})
    return page, playwright, context, node, profile, observed


def _close(playwright, context, node, profile, observed):
    context.close()
    playwright.stop()
    observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
    cleanup = browser._wait_for_cleanup(observed)
    assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
    assert cleanup["remaining_pids"] == []


def test_support_panel_refuses_checkbox_when_no_current_target(tmp_path, monkeypatch):
    world = _ready(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        received = client.post(
            "/api/cases/evidence",
            headers=_composed_headers(world.case, csrf),
            json={
                "tenant_id": world.case.tenant_id,
                "case_id": world.case.case_id,
                "resource_id": world.case.resource_id,
                "source_filename": "notice.txt",
                "original_filename": "notice.txt",
                "media_type": "text/plain",
                "content_base64": base64.b64encode(b"Notice text for a synthetic case.\n").decode("ascii"),
                "idempotency_key": "ux20-browser-evidence",
            },
        )
        assert received.status_code == 201, received.text
        evidence_id = received.json()["evidence_id"]
    page, playwright, context, node, profile, observed = _browser(world, tmp_path, monkeypatch)
    try:
        opened = page.goto(browser.SAME_ORIGIN + "/workspace", wait_until="domcontentloaded")
        assert opened.status == 200
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
        issued = page.evaluate(
            """async () => {
                const response = await fetch('/api/complaint-workspace/auth/login', {
                    method: 'POST', credentials: 'same-origin',
                    headers: {'content-type': 'application/json'},
                    body: JSON.stringify({credential: 'synthetic-owner-credential'}),
                });
                const body = await response.json();
                window.workspaceClient.setBrowserSession(body);
                return body;
            }"""
        )
        assert issued["authenticated"] is True
        page.evaluate(
            """context => window.workspaceClient.setCaseContext(context)""",
            {
                "tenant_id": world.case.tenant_id,
                "case_id": world.case.case_id,
                "resource_id": world.case.resource_id,
                "revision": world.case.revision,
                "expected_revision": world.case.revision,
            },
        )
        page.click("[data-tab-target='evidence']")
        page.wait_for_function("() => document.getElementById('evidence-library').dataset.state === 'ready'")
        page.wait_for_function(
            """() => {
                const panel = document.getElementById('evidence-support-panel');
                return panel && (panel.dataset.state === 'ready' || panel.dataset.state === 'unavailable' || panel.dataset.state === 'error');
            }"""
        )
        status = page.locator("#evidence-support-status").inner_text().casefold()
        assert "unavailable" in status or "no current" in status
        assert page.locator("#evidence-support-target option").count() >= 1
        page.locator("#evidence-support-checkbox").check()
        page.click("#evidence-support-checkbox-submit")
        page.wait_for_function(
            """() => {
                const panel = document.getElementById('evidence-support-panel');
                const error = document.getElementById('evidence-support-error');
                return panel && panel.dataset.state === 'error' && error && error.textContent.toLowerCase().indexOf('checkbox') !== -1;
            }"""
        )
        assert "verified legal support" in page.locator("#evidence-support-error").inner_text().casefold()
        page.click("#evidence-support-allegation")
        page.wait_for_function(
            """() => {
                const panel = document.getElementById('evidence-support-panel');
                return panel && (panel.dataset.state === 'unavailable' || panel.dataset.state === 'error');
            }"""
        )
        unavailable = page.locator("#evidence-support-unavailable").inner_text().casefold()
        assert "unavailable" in unavailable or "no current" in page.locator("#evidence-support-status").inner_text().casefold()
    finally:
        _close(playwright, context, node, profile, observed)

    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        listed = client.post(
            "/api/cases/evidence/support-links/offer",
            headers=_composed_headers(world.case, csrf),
            json=_identity(world.case, evidence_id, case_context={"legal_context_status": "unknown"}),
        )
        assert listed.status_code == 200, listed.text
        body = listed.json()
        assert body["current"] == []
        assert body["corroborations"] == []
        assert body["verified_legal_support"] is False
        facts = world.app.state.evidence_workspace.claim_support.get_fact_records(world.case.tenant_id)
        assert facts == []
