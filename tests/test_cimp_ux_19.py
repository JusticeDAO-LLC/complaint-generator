"""Classification choices follow the current case, not a fixed claim menu.

User labels, AI suggestions, and reviewed acceptance stay distinct. A source
or artifact version change retires the affected choice and keeps who made it.
"""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from integrations.evidence_workspace import MemoryByteBackend, classification_choices_from_context
from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import _composed_headers, _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

GAP = "notice-date-missing"
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


def _admitted(source_version="ord-2024-1", graph_revision="facts-1"):
    return {
        "legal_context_status": "admitted",
        "context_owner": "request",
        "factual_graph_revision": graph_revision,
        "source_version": source_version,
        "jurisdiction": "Example County",
        "authority_version": "auth-v3",
        "factual_gaps": [{"gap_id": GAP, "label": "Date the written notice was received"}],
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
        "idempotency_key": "ux19-evidence",
    })


def test_choices_use_current_gaps_and_admitted_requirements_only():
    unknown = classification_choices_from_context({})
    assert unknown["legal_context_status"] == "unknown"
    assert unknown["admitted_requirement_ids"] == []
    assert unknown["hardcoded_elements_used"] is False
    assert unknown["fixed_assumptions_offered"] is False
    assert [item["choice_id"] for item in unknown["choices"]] == ["unknown_legal_context"]
    assert "protected_activity" not in unknown["factual_gap_ids"]

    poisoned = classification_choices_from_context({
        "legal_context_status": "admitted",
        "source_version": "ord-2024-1",
        "jurisdiction": "Example County",
        "authority_version": "auth-v3",
        "factual_gaps": [
            {"gap_id": "protected_activity", "label": "Protected activity"},
            {"gap_id": "employer_knowledge", "label": "Employer knowledge"},
            {"gap_id": GAP, "label": "Date the written notice was received"},
        ],
        "admitted_requirements": [
            {"requirement_id": "causation", "passage_id": "p-hr", "label": "HR causation",
             "source_version": "ord-2024-1", "jurisdiction": "Example County",
             "authority_version": "auth-v3", "admitted_law": True},
            {"requirement_id": REQUIREMENT, "passage_id": PASSAGE, "label": "Written notice within 21 days",
             "source_version": "ord-2024-1", "jurisdiction": "Example County",
             "authority_version": "auth-v3", "admitted_law": True},
            {"requirement_id": "unreviewed-rule", "passage_id": "p-2", "label": "Not admitted",
             "source_version": "ord-2024-1", "jurisdiction": "Example County",
             "authority_version": "auth-v3", "admitted_law": False},
        ],
    })
    assert poisoned["factual_gap_ids"] == [GAP]
    assert poisoned["admitted_requirement_ids"] == [REQUIREMENT]
    assert set(poisoned["refused_fixed_assumptions"]) >= {"protected_activity", "employer_knowledge", "causation"}
    assert poisoned["establishes_legal_support"] is False
    assert all(item["choice_id"] not in {"protected_activity", "employer_knowledge", "causation", "hr"} for item in poisoned["choices"])

    incomplete = classification_choices_from_context({
        "legal_context_status": "admitted",
        "factual_gaps": [{"gap_id": GAP, "label": "Date the written notice was received"}],
        "admitted_requirements": [{
            "requirement_id": REQUIREMENT, "passage_id": PASSAGE, "admitted_law": True,
            "source_version": "ord-2024-1", "jurisdiction": "Example County", "authority_version": "auth-v3",
        }],
    })
    assert incomplete["legal_context_status"] == "unknown"
    assert incomplete["admitted_requirement_ids"] == []
    assert REQUIREMENT not in [item["choice_id"] for item in incomplete["choices"]]


def test_records_distinguish_origins_and_retire_on_source_change(tmp_path):
    world = _ready(tmp_path)
    workspace = world.app.state.evidence_workspace
    actor = world.owner.principal_id
    evidence = _receive(workspace, world.case, actor)
    evidence_id = evidence["evidence_id"]
    context = _admitted()

    label = workspace.record_classifier(actor, _identity(
        world.case, evidence_id, origin="user_label", label="desk-copy",
        case_context=context, idempotency_key="ux19-label",
    ))
    assert label["origin"] == "user_label"
    assert label["target_kind"] == "user_label"
    assert label["accepted"] is False
    assert label["establishes_legal_support"] is False

    suggestion = workspace.record_classifier(actor, _identity(
        world.case, evidence_id, origin="ai_suggested", target_id=REQUIREMENT,
        model_id="synthetic-model", invocation_id="invoke-19",
        case_context=context, idempotency_key="ux19-ai",
    ))
    assert suggestion["origin"] == "ai_suggested"
    assert suggestion["accepted"] is False
    assert suggestion["reviewed"] is False
    assert suggestion["model_id"] == "synthetic-model"
    assert suggestion["establishes_claim_element"] is False

    refused_fixed = None
    try:
        workspace.record_classifier(actor, _identity(
            world.case, evidence_id, origin="ai_suggested", target_id="protected_activity",
            model_id="synthetic-model", invocation_id="invoke-fixed",
            case_context=context, idempotency_key="ux19-fixed",
        ))
    except Exception as exc:
        refused_fixed = getattr(exc, "code", "")
    assert refused_fixed == "classifier_rejected"

    refused_review = None
    try:
        workspace.record_classifier(actor, _identity(
            world.case, evidence_id, origin="reviewed_acceptance", target_id=REQUIREMENT,
            prior_classifier_id=label["classifier_id"], accept=True,
            case_context=context, idempotency_key="ux19-bad-review",
        ))
    except Exception as exc:
        refused_review = getattr(exc, "code", "")
    assert refused_review == "classifier_rejected"

    accepted = workspace.record_classifier(actor, _identity(
        world.case, evidence_id, origin="reviewed_acceptance", target_id=REQUIREMENT,
        prior_classifier_id=suggestion["classifier_id"], accept=True,
        case_context=context, idempotency_key="ux19-review",
    ))
    assert accepted["origin"] == "reviewed_acceptance"
    assert accepted["accepted"] is True
    assert accepted["reviewed"] is True
    assert accepted["prior_classifier_id"] == suggestion["classifier_id"]
    assert accepted["actor_principal_id"] == actor
    assert accepted["establishes_legal_support"] is False
    assert accepted["governing_law"] is False

    replay = workspace.record_classifier(actor, _identity(
        world.case, evidence_id, origin="reviewed_acceptance", target_id=REQUIREMENT,
        prior_classifier_id=suggestion["classifier_id"], accept=True,
        case_context=context, idempotency_key="ux19-review",
    ))
    assert replay["idempotent_replay"] is True
    assert replay["classifier_id"] == accepted["classifier_id"]

    changed = _admitted(source_version="ord-2025-2", graph_revision="facts-2")
    offered = workspace.offer_classifiers(actor, _identity(world.case, evidence_id, case_context=changed))
    assert offered["legal_context_status"] == "admitted"
    assert offered["source_version"] == "ord-2025-2"
    assert offered["admitted_requirement_ids"] == [REQUIREMENT]
    retired = {row["classifier_id"]: row for row in offered["retired"]}
    assert suggestion["classifier_id"] in retired
    assert accepted["classifier_id"] in retired
    assert retired[suggestion["classifier_id"]]["retired_reason"] == "source_or_context_changed"
    assert retired[suggestion["classifier_id"]]["model_id"] == "synthetic-model"
    assert retired[suggestion["classifier_id"]]["invocation_id"] == "invoke-19"
    assert retired[suggestion["classifier_id"]]["actor_principal_id"] == actor
    assert retired[accepted["classifier_id"]]["accepted"] is True
    assert label["classifier_id"] in {row["classifier_id"] for row in offered["user_labels"]}
    assert offered["ai_suggestions"] == []
    assert offered["reviewed_acceptances"] == []
    assert offered["fixed_assumptions_offered"] is False

    workspace.transition(actor, {
        "tenant_id": world.case.tenant_id,
        "case_id": world.case.case_id,
        "resource_id": world.case.resource_id,
        "evidence_id": evidence_id,
        "action": "extract",
        "expected_artifact_version": 1,
        "idempotency_key": "ux19-extract",
        "extracted_content_base64": base64.b64encode(b"Extracted notice sentence.\n").decode("ascii"),
    })
    after_version = workspace.offer_classifiers(actor, _identity(
        world.case, evidence_id, artifact_version=2, case_context=changed,
    ))
    assert after_version["artifact_version"] == 2
    assert label["classifier_id"] in {row["classifier_id"] for row in after_version["retired"]}
    kept = next(row for row in after_version["retired"] if row["classifier_id"] == label["classifier_id"])
    assert kept["retired_reason"] == "artifact_version_changed"
    assert kept["label"] == "desk-copy"
    assert kept["actor_principal_id"] == actor


def test_http_offer_rejects_fixed_targets_and_keeps_unknown_context(tmp_path):
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
                "idempotency_key": "ux19-http-evidence",
            },
        )
        assert received.status_code == 201, received.text
        evidence_id = received.json()["evidence_id"]
        headers = _composed_headers(world.case, csrf)
        offered = client.post(
            "/api/cases/evidence/classifications/offer",
            headers=headers,
            json=_identity(world.case, evidence_id, case_context={
                "legal_context_status": "unknown",
                "factual_gaps": [{"gap_id": "protected_activity", "label": "Protected activity"}],
                "admitted_requirements": [],
            }),
        )
        assert offered.status_code == 200, offered.text
        body = offered.json()
        assert body["legal_context_status"] == "unknown"
        assert body["admitted_requirement_ids"] == []
        assert body["fixed_assumptions_offered"] is False
        assert "protected_activity" not in {item["choice_id"] for item in body["choices"]}
        assert body["choices"][0]["target_kind"] == "unknown_legal_context"
        assert body["establishes_legal_support"] is False

        refused = client.post(
            "/api/cases/evidence/classifications",
            headers=headers,
            json=_identity(
                world.case, evidence_id, origin="ai_suggested", target_id="causation",
                model_id="synthetic-model", invocation_id="invoke-http",
                idempotency_key="ux19-http-fixed",
                case_context={"legal_context_status": "unknown"},
            ),
        )
        assert refused.status_code == 400
        assert refused.json()["error"] == "classifier_rejected"
        assert refused.json()["operation_succeeded"] is False

        saved = client.post(
            "/api/cases/evidence/classifications",
            headers=headers,
            json=_identity(
                world.case, evidence_id, origin="user_label", label="caller-note",
                idempotency_key="ux19-http-label",
                case_context={"legal_context_status": "unknown"},
            ),
        )
        assert saved.status_code == 201, saved.text
        assert saved.json()["origin"] == "user_label"
        assert saved.json()["legal_context_status"] == "unknown"
        assert saved.json()["accepted"] is False


def _browser(world, tmp_path, monkeypatch):
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    bridge = browser.SameOriginAsgiBridge(world.app)
    world.browser_bridge = bridge
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux19-profile"
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


def test_classification_panel_records_user_choice_without_fixed_elements(tmp_path, monkeypatch):
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
                "idempotency_key": "ux19-browser-evidence",
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
                const panel = document.getElementById('evidence-classification-panel');
                return panel && panel.dataset.state === 'ready';
            }"""
        )
        choices = page.locator("#evidence-classification-choices")
        choice_text = choices.inner_text().casefold()
        assert "unknown legal context" in choice_text or "legal context is unknown" in choice_text
        assert "protected activity" not in choice_text
        assert "employer knowledge" not in choice_text
        assert page.locator("#evidence-classification-choices input[value='protected_activity']").count() == 0
        assert page.locator("#evidence-classification-choices input[value='causation']").count() == 0
        assert page.locator("#evidence-classification-choices input[value='employer_knowledge']").count() == 0
        page.locator("#evidence-classification-choices input[value='unknown_legal_context']").check()
        page.click("#evidence-classification-save-choice")
        page.wait_for_function(
            """() => {
                const node = document.getElementById('evidence-classification-user-labels');
                return node && node.textContent.indexOf('unknown_legal_context') !== -1;
            }"""
        )
        reviewed_text = page.locator("#evidence-classification-reviewed").inner_text().casefold()
        assert "reviewed acceptance" not in reviewed_text or "no reviewed acceptance" in reviewed_text
        assert "no ai suggestion" in page.locator("#evidence-classification-suggestions").inner_text().casefold()
        page.fill("#evidence-classification-label", "desk-copy")
        page.click("#evidence-classification-save-label")
        page.wait_for_function(
            """() => document.getElementById('evidence-classification-user-labels').textContent.indexOf('desk-copy') !== -1"""
        )
        labels = page.locator("#evidence-classification-user-labels").inner_text().casefold()
        assert world.owner.principal_id.casefold() in labels
        page.click("#evidence-classification-accept")
        page.wait_for_function(
            """() => document.getElementById('evidence-classification-panel').dataset.state === 'error'"""
        )
        assert "ai suggestion" in page.locator("#evidence-classification-error").inner_text().casefold()
    finally:
        _close(playwright, context, node, profile, observed)

    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        listed = client.post(
            "/api/cases/evidence/classifications/offer",
            headers=_composed_headers(world.case, csrf),
            json=_identity(world.case, evidence_id, case_context={"legal_context_status": "unknown"}),
        )
        assert listed.status_code == 200, listed.text
        body = listed.json()
        labels = {row["label"] for row in body["user_labels"]}
        assert "desk-copy" in labels
        assert "unknown_legal_context" in labels or any(row["target_id"] == "unknown_legal_context" for row in body["user_labels"])
        assert body["reviewed_acceptances"] == []
        assert body["ai_suggestions"] == []
        assert body["legal_context_status"] == "unknown"
        assert all(row["establishes_legal_support"] is False for row in body["current"])
