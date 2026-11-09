"""Evidence revisions keep lineage, and conflicts keep encrypted history.

A repeated or revised upload asks for a deliberate duplicate decision.
It does not overwrite an artifact or copy support links. Concurrent notes
and links return conflict data. Revoked or rotated keys deny late
publication and preview.
"""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from applications.evidence_annotation_store import AnnotationRevisionConflict, EvidenceAnnotationStore
from integrations.evidence_workspace import EvidenceWorkspaceError
from integrations.private_storage import PrivateArtifactBinding
from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import _composed_headers, _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

KEY = bytes(range(32))
NOTE = "synthetic note on the first sealed copy"
ASSERTION = "notice-received"


def _ready(tmp_path):
    world = owner_lawyer_journey_world(tmp_path / "journey")
    from integrations.evidence_workspace import EvidenceWorkspace, MemoryByteBackend
    workspace = EvidenceWorkspace(
        world.cases,
        {world.owner.principal_id: world.owner_keys, world.lawyer.principal_id: world.recipient},
        MemoryByteBackend(),
        tmp_path / "evidence-root",
    )
    world.app.state.evidence_workspace = workspace
    return world


def _body(case, content: bytes, key: str, **extra):
    payload = {
        "tenant_id": case.tenant_id,
        "case_id": case.case_id,
        "resource_id": case.resource_id,
        "source_filename": "notice.txt",
        "original_filename": "notice.txt",
        "media_type": "text/plain",
        "content_base64": base64.b64encode(content).decode("ascii"),
        "idempotency_key": key,
    }
    payload.update(extra)
    return payload


def _context():
    return {
        "legal_context_status": "admitted",
        "context_owner": "request",
        "factual_graph_revision": "facts-21",
        "source_version": "ord-2024-21",
        "jurisdiction": "Example County",
        "authority_version": "auth-v21",
        "factual_assertions": [{
            "assertion_id": ASSERTION,
            "text": "The notice was received on 3 March.",
            "status": "current",
            "graph_revision": "facts-21",
        }],
        "admitted_requirements": [],
    }


def _annotation(store, **extra):
    common = dict(
        evidence_id="evidence-21",
        artifact_version=1,
        actor_principal_id="actor-owner",
        canonical_owner_principal_id="tenant-owner",
        tenant_id="tenant-owner",
        case_id="case-21",
        key=KEY,
        key_id="key-21",
    )
    common.update(extra)
    return common


def test_repeated_and_revised_uploads_keep_lineage_and_require_a_decision(tmp_path):
    world = _ready(tmp_path)
    workspace = world.app.state.evidence_workspace
    actor = world.owner.principal_id
    original = workspace.receive(actor, _body(world.case, b"Notice text for a synthetic case.\n", "ux21-original"))
    assert original["current_version"] == 1
    assert original["lineage_original_evidence_id"] == original["evidence_id"]
    assert original["support_links_copied"] is False

    repeated = workspace.receive(actor, _body(world.case, b"Notice text for a synthetic case.\n", "ux21-repeat"))
    assert repeated["duplicate_decision_required"] is True
    assert repeated["operation_succeeded"] is False
    assert repeated["overwrote_artifact"] is False
    assert repeated["support_links_copied"] is False
    assert repeated["lineage"]["original_evidence_id"] == original["evidence_id"]
    assert repeated["decisions"] == ["retain_original", "record_revision", "separate_artifact"]
    catalog = workspace.list_catalog(actor, _body(world.case, b"unused", "unused-list"))
    assert [item["evidence_id"] for item in catalog["items"]] == [original["evidence_id"]]

    kept = workspace.receive(actor, _body(
        world.case, b"Notice text for a synthetic case.\n", "ux21-keep", duplicate_decision="retain_original",
    ))
    assert kept["evidence_id"] == original["evidence_id"]
    assert kept["current_version"] == 1
    assert kept["duplicate_decision_applied"] == "retain_original"
    assert kept["version_appended"] is False

    revised = workspace.receive(actor, _body(
        world.case, b"Notice text revised after the first seal.\n", "ux21-revise", duplicate_decision="record_revision",
    ))
    assert revised["evidence_id"] == original["evidence_id"]
    assert revised["current_version"] == 2
    assert revised["lineage_original_evidence_id"] == original["evidence_id"]
    assert revised["artifact_versions"][0]["version"] == 1
    assert revised["artifact_versions"][1]["kind"] == "revision"
    assert revised["artifact_versions"][1]["parent_version"] == 1
    assert revised["overwrote_artifact"] is False
    assert revised["support_links_copied"] is False
    assert revised["artifact_versions"][0]["integrity_sha256"] != revised["artifact_versions"][1]["integrity_sha256"]

    separate = workspace.receive(actor, _body(
        world.case, b"Notice text revised after the first seal.\n", "ux21-separate", duplicate_decision="separate_artifact",
    ))
    assert separate["evidence_id"] != original["evidence_id"]
    assert separate["lineage_original_evidence_id"] == original["evidence_id"]
    assert separate["lineage_parent_evidence_id"] == original["evidence_id"]
    assert separate["support_links_copied"] is False
    assert separate["current_version"] == 1
    listed = workspace.list_catalog(actor, {"tenant_id": world.case.tenant_id, "case_id": world.case.case_id, "resource_id": world.case.resource_id})
    assert {item["evidence_id"] for item in listed["items"]} == {original["evidence_id"], separate["evidence_id"]}
    original_again = next(item for item in listed["items"] if item["evidence_id"] == original["evidence_id"])
    assert original_again["current_version"] == 2
    assert len(original_again["artifact_versions"]) == 2


def test_revision_does_not_copy_support_and_stale_links_conflict(tmp_path):
    world = _ready(tmp_path)
    workspace = world.app.state.evidence_workspace
    actor = world.owner.principal_id
    evidence = workspace.receive(actor, _body(world.case, b"Notice text for a synthetic case.\n", "ux21-support-evidence"))
    evidence_id = evidence["evidence_id"]
    identity = {
        "tenant_id": world.case.tenant_id,
        "case_id": world.case.case_id,
        "resource_id": world.case.resource_id,
        "evidence_id": evidence_id,
        "artifact_version": 1,
        "page": 1,
        "span_start": 0,
        "span_end": 12,
        "posture": "allegation",
        "origin": "human_statement",
        "target_kind": "factual_assertion",
        "target_id": ASSERTION,
        "case_context": _context(),
        "idempotency_key": "ux21-link-1",
        "expected_support_revision": "",
    }
    linked = workspace.record_support_link(actor, identity)
    assert linked["operation_succeeded"] is True
    assert linked["support_links_copied"] is False
    assert linked["support_revision"]
    stale = workspace.record_support_link(actor, {**identity, "idempotency_key": "ux21-link-2", "expected_support_revision": ""})
    assert stale["conflict"] is True
    assert stale["error"] == "revision_conflict"
    assert stale["published"] is False
    assert stale["history_retained"] is True
    assert stale["support_links_copied"] is False
    assert linked["support_link_id"] in stale["preserved_support_link_ids"]
    assert stale["support_revision"] == linked["support_revision"]
    offered = workspace.offer_support_links(actor, {
        "tenant_id": world.case.tenant_id,
        "case_id": world.case.case_id,
        "resource_id": world.case.resource_id,
        "evidence_id": evidence_id,
        "artifact_version": 1,
        "case_context": _context(),
    })
    assert [row["support_link_id"] for row in offered["current"]] == [linked["support_link_id"]]
    assert offered["support_conflict_history"]
    assert offered["support_conflict_history"][-1]["encrypted"] is True

    revised = workspace.receive(actor, _body(
        world.case, b"A later scan of the same notice.\n", "ux21-support-revise", duplicate_decision="record_revision",
    ))
    assert revised["current_version"] == 2
    assert revised["support_links_copied"] is False
    offered_again = workspace.offer_support_links(actor, {
        "tenant_id": world.case.tenant_id,
        "case_id": world.case.case_id,
        "resource_id": world.case.resource_id,
        "evidence_id": evidence_id,
        "artifact_version": 2,
        "case_context": _context(),
    })
    assert offered_again["current"] == []
    assert [row["support_link_id"] for row in offered_again["retired"]] == [linked["support_link_id"]]
    assert offered_again["retired"][0]["artifact_version"] == 1


def test_concurrent_annotations_and_links_keep_encrypted_history(tmp_path):
    store = EvidenceAnnotationStore(tmp_path / "notes")
    common = _annotation(store)
    first = store.commit_attributed_annotation(
        kind="comment", note=NOTE, idempotency_key="note-1", expected_annotation_revision="", **common,
    )
    with pytest.raises(AnnotationRevisionConflict) as stale:
        store.commit_attributed_annotation(
            kind="comment", note="a later note that must not replace the first", idempotency_key="note-2",
            expected_annotation_revision="", **common,
        )
    conflict = stale.value.conflict
    assert stale.value.code == "revision_conflict"
    assert conflict["published"] is False
    assert conflict["history_retained"] is True
    assert conflict["current_annotation_revision"] == first["annotation_revision"]
    assert first["annotation_id"] in conflict["preserved_annotation_ids"]
    opened = store.read(
        record_id=conflict["encrypted_history_record_id"],
        binding=PrivateArtifactBinding(
            tenant_id="tenant-owner", case_id="case-21", artifact_kind="annotation",
            revision=conflict["encrypted_history_record_id"], principal_id="tenant-owner",
        ),
        key=KEY,
    )
    assert b"a later note that must not replace the first" in opened
    listed = store.list_attributed_annotations(
        evidence_id="evidence-21", artifact_version=1, canonical_owner_principal_id="tenant-owner",
        tenant_id="tenant-owner", case_id="case-21", key=KEY,
    )
    assert [item["annotation_id"] for item in listed["items"]] == [first["annotation_id"]]
    assert listed["annotation_revision"] == first["annotation_revision"]
    assert listed["conflict_history"][0]["record_id"] == conflict["encrypted_history_record_id"]

    returned = store.publish_annotation(
        kind="comment", note="still stale", idempotency_key="note-3", expected_annotation_revision="",
        expected_key_id="key-21", live_key_id="key-21", **common,
    )
    assert returned["conflict"] is True
    assert returned["published"] is False
    assert returned["history_retained"] is True

    linked = store.publish_link(
        evidence_id="evidence-21", artifact_version=1, annotation_id=first["annotation_id"],
        actor_principal_id="actor-owner", canonical_owner_principal_id="tenant-owner",
        tenant_id="tenant-owner", case_id="case-21", idempotency_key="link-1",
        expected_annotation_revision=first["annotation_revision"], expected_key_id="key-21",
        live_key_id="key-21", key=KEY, key_id="key-21",
    )
    assert linked["published"] is True
    assert linked["link_record_id"]
    raced = store.publish_link(
        evidence_id="evidence-21", artifact_version=1, annotation_id=first["annotation_id"],
        actor_principal_id="actor-owner", canonical_owner_principal_id="tenant-owner",
        tenant_id="tenant-owner", case_id="case-21", idempotency_key="link-2",
        expected_annotation_revision=first["annotation_revision"], expected_key_id="key-21",
        live_key_id="key-21", key=KEY, key_id="key-21",
    )
    assert raced["conflict"] is True
    assert raced["published"] is False
    assert raced["current_annotation_revision"] == linked["annotation_revision"]
    assert raced["history_retained"] is True
    denied = store.publish_annotation(
        kind="comment", note="after rotation", idempotency_key="note-4",
        expected_annotation_revision=linked["annotation_revision"],
        expected_key_id="key-21", live_key_id="key-22", **common,
    )
    assert denied["error"] == "key_rotated"
    assert denied["published"] is False
    assert denied["preview_allowed"] is False
    assert denied["history_retained"] is True
    assert first["annotation_id"] in denied["preserved_annotation_ids"]
    locked = store.publish_link(
        evidence_id="evidence-21", artifact_version=1, annotation_id=first["annotation_id"],
        actor_principal_id="actor-owner", canonical_owner_principal_id="tenant-owner",
        tenant_id="tenant-owner", case_id="case-21", idempotency_key="link-3",
        expected_annotation_revision=linked["annotation_revision"], expected_key_id="key-21",
        live_key_id="", key=KEY, key_id="key-21", access_locked=True,
    )
    assert locked["error"] == "operation_revoked"
    assert locked["published"] is False
    assert locked["preview_allowed"] is False
    still = store.list_attributed_annotations(
        evidence_id="evidence-21", artifact_version=1, canonical_owner_principal_id="tenant-owner",
        tenant_id="tenant-owner", case_id="case-21", key=KEY,
    )
    assert [item["note"] for item in still["items"]] == [NOTE]


def test_revoked_or_rotated_access_denies_late_publication_and_preview(tmp_path):
    world = _ready(tmp_path)
    workspace = world.app.state.evidence_workspace
    actor = world.owner.principal_id
    content = b"Notice text for a synthetic case.\n"
    evidence = workspace.receive(actor, _body(world.case, content, "ux21-preview"))
    preview = workspace.preview_artifact(actor, {
        "tenant_id": world.case.tenant_id,
        "case_id": world.case.case_id,
        "resource_id": world.case.resource_id,
        "evidence_id": evidence["evidence_id"],
        "version": 1,
    })
    assert preview["preview_allowed"] is True
    assert preview["preview_text"].encode("utf-8") == content
    assert preview["model_invoked"] is False

    staged = workspace.stage_publication(actor, _body(world.case, b"late revision bytes\n", "ux21-late"))
    key_id = world.owner_keys.ensure_data_key(world.case.tenant_id, world.case.case_id)
    rotated = world.owner_keys.rotate_case_grant_data_key(
        world.case.tenant_id, world.case.case_id, resource_id=world.case.resource_id,
        expected_data_key_id=key_id, operation_id="ux21-rotate-preview",
    )
    assert rotated["rotated"] is True
    with pytest.raises(EvidenceWorkspaceError) as preview_denied:
        workspace.preview_artifact(actor, {
            "tenant_id": world.case.tenant_id,
            "case_id": world.case.case_id,
            "resource_id": world.case.resource_id,
            "evidence_id": evidence["evidence_id"],
            "version": 1,
        })
    assert preview_denied.value.code == "key_rotated"
    with pytest.raises(EvidenceWorkspaceError) as publish_denied:
        workspace.commit_publication(actor, {
            "tenant_id": world.case.tenant_id,
            "case_id": world.case.case_id,
            "resource_id": world.case.resource_id,
            "publication_id": staged["publication_id"],
            "idempotency_key": "ux21-late-commit",
        })
    assert publish_denied.value.code == "key_rotated"
    catalog = workspace.list_catalog(actor, {
        "tenant_id": world.case.tenant_id, "case_id": world.case.case_id, "resource_id": world.case.resource_id,
    })
    assert catalog.get("error") == "ciphertext_unavailable"
    assert catalog.get("items") == []
    assert "late revision" not in str(catalog)

    world.owner_keys.lock()
    with pytest.raises(EvidenceWorkspaceError) as locked_preview:
        workspace.preview_artifact(actor, {
            "tenant_id": world.case.tenant_id,
            "case_id": world.case.case_id,
            "resource_id": world.case.resource_id,
            "evidence_id": evidence["evidence_id"],
        })
    assert locked_preview.value.code == "operation_revoked"


def test_duplicate_decision_panel_keeps_the_original_artifact(tmp_path, monkeypatch):
    world = _ready(tmp_path)
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    sample = tmp_path / "notice.txt"
    sample.write_bytes(b"Notice text for a synthetic case.\n")
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        first = client.post(
            "/api/cases/evidence",
            headers=_composed_headers(world.case, csrf),
            json=_body(world.case, sample.read_bytes(), "ux21-browser-original"),
        )
        assert first.status_code == 201, first.text
        evidence_id = first.json()["evidence_id"]
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux21-profile"
    profile.mkdir(mode=0o700)
    playwright = browser._load_sync_playwright()().start()
    context = browser._launch_context(playwright, chromium.path, profile, bridge)
    browser._assert_process_custody(node, chromium, profile)
    observed = set(browser._with_descendants(browser._matching_pids((str(profile), node.argv[1]))))
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(15000)
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
        page.set_input_files("#evidence-attachment", str(sample))
        page.click("#evidence-upload-start")
        page.wait_for_selector("#evidence-duplicate-decision")
        assert "deliberate duplicate decision" in page.locator("#evidence-duplicate-lineage").inner_text().casefold()
        page.click("#evidence-duplicate-keep")
        page.wait_for_function(
            """() => {
                const root = document.getElementById('evidence-private-upload');
                const status = document.getElementById('evidence-upload-status');
                return root && root.dataset.state === 'sealed' && status
                    && status.textContent.toLowerCase().indexOf('duplicate decision') !== -1;
            }"""
        )
        status = page.locator("#evidence-upload-status").inner_text().casefold()
        assert "keep" in status or "retain_original" in status or "original" in status
        lineage = page.locator("#evidence-duplicate-lineage").inner_text().casefold()
        assert "overwrote artifact: no" in lineage
        assert "support copied: no" in lineage
        assert evidence_id in page.locator("#evidence-duplicate-lineage").inner_text()
    finally:
        context.close()
        playwright.stop()
        observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
        assert cleanup["remaining_pids"] == []

    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        listed = client.get("/api/cases/evidence", headers=_composed_headers(world.case, csrf))
        assert listed.status_code == 200, listed.text
        items = listed.json()["items"]
        assert [item["evidence_id"] for item in items] == [evidence_id]
        assert items[0]["current_version"] == 1
        assert items[0]["support_links_copied"] is False
