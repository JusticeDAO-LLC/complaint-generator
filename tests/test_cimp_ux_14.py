"""Private evidence upload with bounded progress, cancel, and idempotent retry.

Files are sealed by the case evidence owner. A local selection, a cancelled
attempt, or a rejected request is not an ingested artifact.
"""

from __future__ import annotations

import base64
import hashlib
import logging

import pytest
from fastapi.testclient import TestClient

from applications.browser_sessions import SESSION_COOKIE
from integrations.evidence_workspace import EvidenceWorkspace, MemoryByteBackend
from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import PASSPHRASE, _composed_headers, _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

PAYLOAD = b"synthetic housing notice ux14 private upload"
SOURCE = "notice.txt"
ORIGINAL = "Housing denial scan.tiff"


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _ready(tmp_path):
    world = owner_lawyer_journey_world(tmp_path / "journey")
    backend = MemoryByteBackend()
    workspace = EvidenceWorkspace(
        world.cases,
        {world.owner.principal_id: world.owner_keys, world.lawyer.principal_id: world.recipient},
        backend,
        tmp_path / "evidence-root",
    )
    world.app.state.evidence_workspace = workspace
    return world, backend


def _meta(case, payload=PAYLOAD, **extra):
    body = {
        "tenant_id": case.tenant_id,
        "case_id": case.case_id,
        "resource_id": case.resource_id,
        "expected_revision": case.revision,
        "source_filename": SOURCE,
        "original_filename": ORIGINAL,
        "media_type": "text/plain",
        "byte_length": len(payload),
        "content_sha256": _digest(payload),
        "idempotency_key": "upload-ux14-1",
    }
    body.update(extra)
    return body


def _post(client, path, case, csrf, body):
    return client.post(path, headers=_composed_headers(case, csrf), json=body)


def _upload(client, case, csrf, payload=PAYLOAD, chunk=16):
    opened = _post(client, "/api/cases/evidence/uploads", case, csrf, _meta(case, payload))
    assert opened.status_code == 201, opened.text
    ticket = opened.json()
    assert ticket["upload_state"] == "accepting"
    assert ticket["progress_percent"] == 0
    assert ticket["operation_succeeded"] is False
    assert "evidence_id" not in ticket
    seen = []
    for offset in range(0, len(payload), chunk):
        piece = payload[offset:offset + chunk]
        sent = _post(client, "/api/cases/evidence/uploads/chunk", case, csrf, {
            "tenant_id": case.tenant_id,
            "case_id": case.case_id,
            "resource_id": case.resource_id,
            "expected_revision": case.revision,
            "upload_id": ticket["upload_id"],
            "upload_generation": ticket["upload_generation"],
            "offset": offset,
            "content_base64": base64.b64encode(piece).decode("ascii"),
        })
        assert sent.status_code == 200, sent.text
        progress = sent.json()
        assert 0 < progress["progress_percent"] <= 99
        assert progress["progress_bounded"] is True
        assert progress["operation_succeeded"] is False
        seen.append(progress["progress_percent"])
        replay = _post(client, "/api/cases/evidence/uploads/chunk", case, csrf, {
            "tenant_id": case.tenant_id,
            "case_id": case.case_id,
            "resource_id": case.resource_id,
            "expected_revision": case.revision,
            "upload_id": ticket["upload_id"],
            "upload_generation": ticket["upload_generation"],
            "offset": offset,
            "content_base64": base64.b64encode(piece).decode("ascii"),
        })
        assert replay.status_code == 200
        assert replay.json()["bytes_accepted"] == progress["bytes_accepted"]
    done = _post(client, "/api/cases/evidence/uploads/complete", case, csrf, {
        "tenant_id": case.tenant_id,
        "case_id": case.case_id,
        "resource_id": case.resource_id,
        "expected_revision": case.revision,
        "upload_id": ticket["upload_id"],
        "upload_generation": ticket["upload_generation"],
    })
    assert done.status_code == 201, done.text
    return ticket, seen, done.json()


def test_private_upload_seals_once_and_retries_without_a_second_artifact(tmp_path, caplog):
    world, backend = _ready(tmp_path)
    caplog.set_level(logging.DEBUG)
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        before = len(backend._blobs)
        _ticket, seen, sealed = _upload(client, world.case, csrf)
        assert seen
        assert sealed["upload_state"] == "sealed"
        assert sealed["progress_percent"] == 100
        assert sealed["operation_succeeded"] is True
        assert sealed["ingestion_status"] == "received"
        assert sealed["public_content_address"] is False
        assert sealed["evidence"]["integrity_sha256"] == _digest(PAYLOAD)
        assert sealed["evidence"]["source_filename"] == SOURCE
        assert sealed["evidence"]["authenticity"] == "not_established"
        assert "cid" not in sealed["evidence"]
        rendered = sealed.__repr__()
        assert PAYLOAD.decode() not in rendered
        assert "ipfs" not in rendered.lower()
        assert backend.contains(PAYLOAD) is False
        assert len(backend._blobs) > before

        again = _post(client, "/api/cases/evidence/uploads/complete", world.case, csrf, {
            "tenant_id": world.case.tenant_id,
            "case_id": world.case.case_id,
            "resource_id": world.case.resource_id,
            "expected_revision": world.case.revision,
            "upload_id": sealed["upload_id"],
            "upload_generation": sealed["upload_generation"],
        })
        assert again.status_code == 200
        assert again.json()["idempotent_replay"] is True
        assert again.json()["evidence_id"] == sealed["evidence_id"]

        resumed = _post(client, "/api/cases/evidence/uploads", world.case, csrf, _meta(world.case))
        assert resumed.status_code == 200
        assert resumed.json()["resumed"] is True
        assert resumed.json()["evidence_id"] == sealed["evidence_id"]
        blobs_after_retry = len(backend._blobs)

        retry = _post(client, "/api/cases/evidence/uploads/retry", world.case, csrf, {
            "tenant_id": world.case.tenant_id,
            "case_id": world.case.case_id,
            "resource_id": world.case.resource_id,
            "expected_revision": world.case.revision,
            "upload_id": sealed["upload_id"],
            "upload_generation": sealed["upload_generation"],
        })
        assert retry.status_code == 200
        assert retry.json()["evidence_id"] == sealed["evidence_id"]
        assert len(backend._blobs) == blobs_after_retry

        listed = client.get("/api/cases/evidence", headers=_composed_headers(world.case, csrf), params={
            "tenant_id": world.case.tenant_id,
            "case_id": world.case.case_id,
            "resource_id": world.case.resource_id,
        })
        assert listed.status_code == 200
        assert [item["evidence_id"] for item in listed.json()["items"]] == [sealed["evidence_id"]]
        assert listed.json()["items"][0]["ingestion_status"] == "received"
        assert PAYLOAD.decode() not in caplog.text
        assert "ambient-admin" not in caplog.text


def test_upload_rejects_oversized_disallowed_cross_case_locked_stale_and_revoked(tmp_path, monkeypatch, caplog):
    world, backend = _ready(tmp_path)
    monkeypatch.setenv("ADMIN_KEY", "ambient-admin-secret")
    caplog.set_level(logging.DEBUG)
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        oversized = _post(client, "/api/cases/evidence/uploads", world.case, csrf, _meta(
            world.case, byte_length=256 * 1024 + 1, idempotency_key="upload-ux14-big",
        ))
        assert oversized.status_code == 400
        assert oversized.json()["error"] == "oversized"
        assert oversized.json()["operation_succeeded"] is False
        assert "evidence_id" not in oversized.json()

        disallowed = _post(client, "/api/cases/evidence/uploads", world.case, csrf, _meta(
            world.case, media_type="text/html", idempotency_key="upload-ux14-html",
        ))
        assert disallowed.status_code == 400
        assert disallowed.json()["error"] == "media_rejected"
        assert disallowed.json()["operation_succeeded"] is False

        foreign = _post(client, "/api/cases/evidence/uploads", world.case, csrf, _meta(
            world.case, case_id="case-not-owned", idempotency_key="upload-ux14-foreign",
        ))
        assert foreign.status_code == 403
        assert foreign.json()["error"] == "not_owner"

        admin = _post(client, "/api/cases/evidence/uploads", world.case, csrf, _meta(
            world.case, key="ambient-admin-secret", idempotency_key="upload-ux14-admin",
        ))
        assert admin.status_code == 403
        assert admin.json()["error"] == "selector_rejected"
        assert admin.json()["operation_succeeded"] is False
        assert "ambient-admin-secret" not in admin.text

        stale = _post(client, "/api/cases/evidence/uploads", world.case, csrf, _meta(
            world.case, expected_revision=world.case.revision + 9, idempotency_key="upload-ux14-stale",
        ))
        assert stale.status_code == 409
        assert stale.json()["error"] == "revision_conflict"

        opened = _post(client, "/api/cases/evidence/uploads", world.case, csrf, _meta(
            world.case, idempotency_key="upload-ux14-cancel",
        ))
        assert opened.status_code == 201
        ticket = opened.json()
        piece = _post(client, "/api/cases/evidence/uploads/chunk", world.case, csrf, {
            "tenant_id": world.case.tenant_id,
            "case_id": world.case.case_id,
            "resource_id": world.case.resource_id,
            "expected_revision": world.case.revision,
            "upload_id": ticket["upload_id"],
            "upload_generation": ticket["upload_generation"],
            "offset": 0,
            "content_base64": base64.b64encode(PAYLOAD[:8]).decode("ascii"),
        })
        assert piece.status_code == 200
        assert piece.json()["progress_percent"] <= 99
        cancelled = _post(client, "/api/cases/evidence/uploads/cancel", world.case, csrf, {
            "tenant_id": world.case.tenant_id,
            "case_id": world.case.case_id,
            "resource_id": world.case.resource_id,
            "expected_revision": world.case.revision,
            "upload_id": ticket["upload_id"],
            "upload_generation": ticket["upload_generation"],
        })
        assert cancelled.status_code == 200
        assert cancelled.json()["error"] == "operation_revoked"
        assert cancelled.json()["operation_succeeded"] is False
        assert "evidence_id" not in cancelled.json()
        late = _post(client, "/api/cases/evidence/uploads/complete", world.case, csrf, {
            "tenant_id": world.case.tenant_id,
            "case_id": world.case.case_id,
            "resource_id": world.case.resource_id,
            "expected_revision": world.case.revision,
            "upload_id": ticket["upload_id"],
            "upload_generation": ticket["upload_generation"],
        })
        assert late.status_code == 409
        assert late.json()["error"] == "operation_revoked"
        assert late.json()["operation_succeeded"] is False

        retried = _post(client, "/api/cases/evidence/uploads/retry", world.case, csrf, {
            "tenant_id": world.case.tenant_id,
            "case_id": world.case.case_id,
            "resource_id": world.case.resource_id,
            "expected_revision": world.case.revision,
            "upload_id": ticket["upload_id"],
            "upload_generation": ticket["upload_generation"],
        })
        assert retried.status_code == 201
        assert retried.json()["upload_generation"] == ticket["upload_generation"] + 1
        stale_generation = _post(client, "/api/cases/evidence/uploads/chunk", world.case, csrf, {
            "tenant_id": world.case.tenant_id,
            "case_id": world.case.case_id,
            "resource_id": world.case.resource_id,
            "expected_revision": world.case.revision,
            "upload_id": ticket["upload_id"],
            "upload_generation": ticket["upload_generation"],
            "offset": 0,
            "content_base64": base64.b64encode(PAYLOAD[:8]).decode("ascii"),
        })
        assert stale_generation.status_code == 409
        assert stale_generation.json()["error"] == "upload_stale"

        world.owner_keys.lock()
        locked = _post(client, "/api/cases/evidence/uploads", world.case, csrf, _meta(
            world.case, idempotency_key="upload-ux14-locked",
        ))
        assert locked.status_code == 503
        assert locked.json()["error"] == "key_unavailable"
        assert locked.json()["ingestion_status"] == "unavailable"
        assert locked.json()["operation_succeeded"] is False
        world.owner_keys.unlock_passphrase(PASSPHRASE)

        token = client.cookies.get(SESSION_COOKIE)
        world.sessions.logout(token, csrf_token=csrf)
        revoked = _post(client, "/api/cases/evidence/uploads/chunk", world.case, csrf, {
            "tenant_id": world.case.tenant_id,
            "case_id": world.case.case_id,
            "resource_id": world.case.resource_id,
            "expected_revision": world.case.revision,
            "upload_id": retried.json()["upload_id"],
            "upload_generation": retried.json()["upload_generation"],
            "offset": 0,
            "content_base64": base64.b64encode(PAYLOAD[:8]).decode("ascii"),
        })
        assert revoked.status_code == 401
        assert revoked.json()["error"] == "authentication_failed"
        assert "evidence_id" not in revoked.json()

        listed = client.get("/api/cases/evidence", headers=_composed_headers(world.case, csrf))
        assert listed.status_code == 401
        assert backend.contains(PAYLOAD) is False
        assert PAYLOAD.decode() not in caplog.text
        assert "ambient-admin-secret" not in caplog.text
        assert "cid" not in oversized.text
        assert "ipfs" not in disallowed.text.lower()


def _browser(tmp_path, monkeypatch):
    world, _backend = _ready(tmp_path)
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux14-profile"
    profile.mkdir(mode=0o700)
    playwright = browser._load_sync_playwright()().start()
    context = browser._launch_context(playwright, chromium.path, profile, bridge)
    browser._assert_process_custody(node, chromium, profile)
    observed = set(browser._with_descendants(browser._matching_pids((str(profile), node.argv[1]))))
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(20000)
    page.set_viewport_size({"width": 1440, "height": 1000})
    return world, page, playwright, context, node, profile, observed


def _close(playwright, context, node, profile, observed):
    context.close()
    playwright.stop()
    observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
    cleanup = browser._wait_for_cleanup(observed)
    assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
    assert cleanup["remaining_pids"] == []


def _prepare_page(page, world):
    opened = page.goto(browser.SAME_ORIGIN + "/workspace", wait_until="domcontentloaded")
    assert opened.status == 200
    assert page.evaluate("() => typeof window.mockApi") == "undefined"
    assert page.locator("#evidence-private-upload").count() == 1
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
        },
    )
    page.click("[data-tab-target='evidence']")
    page.wait_for_selector("#evidence-attachment")


def test_workspace_upload_shows_progress_cancel_and_idempotent_retry(tmp_path, monkeypatch):
    world, page, playwright, context, node, profile, observed = _browser(tmp_path, monkeypatch)
    try:
        _prepare_page(page, world)
        notice = tmp_path / SOURCE
        notice.write_bytes(PAYLOAD)
        page.set_input_files("#evidence-attachment", str(notice))
        page.click("#evidence-upload-start")
        page.wait_for_function(
            """() => document.getElementById('evidence-private-upload').dataset.state === 'sealed'"""
        )
        view = page.evaluate(
            """() => {
                const root = document.getElementById('evidence-private-upload');
                return {
                    progress: root.dataset.progress,
                    pending: root.dataset.maxPending,
                    ingestion: document.getElementById('evidence-upload-ingestion').dataset.ingestion,
                    evidenceId: root.dataset.evidenceId,
                    text: document.getElementById('evidence-upload-status').textContent,
                };
            }"""
        )
        assert view["pending"] is not None
        assert 1 <= int(view["pending"]) <= 99
        assert view["progress"] == "100"
        assert view["ingestion"] == "received"
        assert view["evidenceId"].startswith("ev-")
        assert PAYLOAD.decode() not in view["text"]

        page.click("#evidence-upload-retry")
        page.wait_for_function(
            """() => document.getElementById('evidence-upload-status').textContent.includes('Idempotent retry')"""
        )
        retried = page.evaluate("() => document.getElementById('evidence-private-upload').dataset.evidenceId")
        assert retried == view["evidenceId"]
        catalog = page.evaluate(
            """async () => {
                const context = window.workspaceClient.caseContext;
                const response = await fetch('/api/cases/evidence?tenant_id=' + encodeURIComponent(context.tenant_id)
                    + '&case_id=' + encodeURIComponent(context.case_id)
                    + '&resource_id=' + encodeURIComponent(context.resource_id), {credentials: 'same-origin'});
                const body = await response.json();
                return {status: response.status, ids: body.items.map(item => item.evidence_id), ingestion: body.items.map(item => item.ingestion_status)};
            }"""
        )
        assert catalog["status"] == 200
        assert catalog["ids"] == [view["evidenceId"]]
        assert catalog["ingestion"] == ["received"]

        page.evaluate(
            """() => {
                const real = window.fetch.bind(window);
                window.__ux14Fetch = real;
                window.fetch = (url, options) => {
                    if (String(url).includes('/uploads/chunk')) return new Promise(() => {});
                    return real(url, options);
                };
            }"""
        )
        other = tmp_path / "follow-up.txt"
        other.write_bytes(b"second synthetic notice ux14")
        page.set_input_files("#evidence-attachment", str(other))
        page.click("#evidence-upload-start")
        page.wait_for_function(
            """() => document.getElementById('evidence-private-upload').dataset.uploadState === 'accepting'
                && document.getElementById('evidence-private-upload').dataset.state === 'pending'"""
        )
        page.click("#evidence-upload-cancel")
        page.wait_for_function(
            """() => document.getElementById('evidence-private-upload').dataset.state === 'revoked'"""
        )
        cancelled = page.evaluate(
            """() => ({
                ingestion: document.getElementById('evidence-upload-ingestion').dataset.ingestion,
                evidenceId: document.getElementById('evidence-private-upload').dataset.evidenceId,
                status: document.getElementById('evidence-upload-status').textContent,
            })"""
        )
        assert cancelled["ingestion"] == ""
        assert cancelled["evidenceId"] == ""
        assert "cancelled" in cancelled["status"].lower()
        page.evaluate("() => { window.fetch = window.__ux14Fetch; }")
        blocked = tmp_path / "page.html"
        blocked.write_text("<p>not evidence</p>", encoding="utf-8")
        page.set_input_files("#evidence-attachment", str(blocked))
        page.click("#evidence-upload-start")
        page.wait_for_function(
            """() => document.getElementById('evidence-private-upload').dataset.state === 'denied'"""
        )
        denied = page.evaluate("() => document.getElementById('evidence-private-upload').dataset.error")
        assert denied == "media_rejected"
        remaining = page.evaluate(
            """async () => {
                const context = window.workspaceClient.caseContext;
                const response = await fetch('/api/cases/evidence?tenant_id=' + encodeURIComponent(context.tenant_id)
                    + '&case_id=' + encodeURIComponent(context.case_id)
                    + '&resource_id=' + encodeURIComponent(context.resource_id), {credentials: 'same-origin'});
                const body = await response.json();
                return body.items.map(item => item.evidence_id);
            }"""
        )
        assert remaining == [view["evidenceId"]]
    finally:
        _close(playwright, context, node, profile, observed)
