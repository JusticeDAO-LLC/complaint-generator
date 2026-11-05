"""Adversarial evidence, role, transport, and late-result cases.

Owner, lawyer, admin, and stranger stay distinct. Hostile evidence stays
data. A wrong case cannot preview, message, or download another case's
bytes. Missing consent and a stale key, source, or result are refused.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests import gui_native_browser as browser
from tests.gui_ux_overhaul_security_fixtures import (
    ADMIN_CREDENTIAL,
    ATTACHMENT_TEXT,
    HOSTILE_HTML,
    LAWYER_CREDENTIAL,
    OWNER_CREDENTIAL,
    SEALED_TEXT,
    STRANGER_CREDENTIAL,
    UNSUPPORTED_TRANSPORTS,
    assert_fixture_source_has_no_authority_bypass,
    refuse_self_authorization,
    security_world,
)
from tests.test_cimp_gui_14 import PASSPHRASE, _composed_headers, _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

ROOT = Path(__file__).resolve().parents[1]


def _csrf(client, credential=OWNER_CREDENTIAL):
    return {"x-csrf-token": _composed_login(client, credential), "content-type": "application/json"}


def _receive(client, case, csrf, name, media, content, key):
    response = client.post(
        "/api/cases/evidence",
        headers=csrf,
        json={
            "tenant_id": case.tenant_id,
            "case_id": case.case_id,
            "resource_id": case.resource_id,
            "source_filename": name,
            "original_filename": name,
            "media_type": media,
            "content_base64": base64.b64encode(content).decode("ascii"),
            "idempotency_key": key,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _preview(client, case, evidence_id):
    return client.get(
        "/api/cases/evidence/preview",
        params={
            "tenant_id": case.tenant_id,
            "case_id": case.case_id,
            "resource_id": case.resource_id,
            "evidence_id": evidence_id,
        },
        headers=_composed_headers(case),
    )


def test_sources_keep_inherited_guards_and_refuse_self_authorization():
    before = browser.probe_inherited_network_denial()
    for relative in ("tests/gui_ux_overhaul_security_fixtures.py", "tests/test_cimp_ux_63.py"):
        assert_fixture_source_has_no_authority_bypass(ROOT / relative)
    refuse_self_authorization({"route": "/cases", "role": "stranger"})
    with pytest.raises(ValueError, match="self_authorization_refused"):
        refuse_self_authorization({"authorized": True, "custody_proof": "minted"})
    with pytest.raises(ValueError, match="fake_custody_refused"):
        refuse_self_authorization({"pinned": True})
    after = browser.probe_inherited_network_denial()
    assert before == after
    assert before["af_unix"]["opened"] is True
    process = sys.modules.get("subprocess")
    if process is not None:
        assert process.Popen.__name__ == "Popen"
    if before["af_unix_only"]:
        assert before["af_inet"]["opened"] is False
        assert before["seccomp"].get("Seccomp") not in {None, "", "0"}


def test_roles_are_isolated_and_hostile_evidence_stays_inert(tmp_path):
    world = security_world(tmp_path)
    case = world.case
    other = world.cases.create_case(actor_principal_id=world.owner.principal_id)
    with TestClient(world.app, base_url="https://testserver") as owner, TestClient(world.app, base_url="https://testserver") as lawyer, TestClient(world.app, base_url="https://testserver") as admin, TestClient(world.app, base_url="https://testserver") as stranger:
        owner_headers = _csrf(owner)
        text = _receive(owner, case, owner_headers, "sealed.txt", "text/plain", SEALED_TEXT, "ux63-text")
        hostile = _receive(owner, case, owner_headers, "hostile.html", "text/html", HOSTILE_HTML, "ux63-html")
        opened = _preview(owner, case, text["evidence_id"])
        assert opened.status_code == 200, opened.text
        assert SEALED_TEXT.decode() in opened.json()["accessible_text"]
        assert opened.json()["model_invoked"] is False
        rendered = _preview(owner, case, hostile["evidence_id"])
        assert rendered.status_code == 200, rendered.text
        body = rendered.json()
        assert body["supported"] is False
        assert body["active_content_executed"] is False
        assert body["external_fetch"] is False
        assert body["image"] is None and body["pages"] == []
        assert "<script" in body["alternative"]["safe_text"]
        assert "cannot be previewed safely" in body["alternative"]["message"]
        stolen_preview = _preview(owner, other, text["evidence_id"])
        assert stolen_preview.status_code == 403, stolen_preview.text
        assert SEALED_TEXT.decode() not in stolen_preview.text

        thread = owner.post("/api/cases/messages/threads", headers=owner_headers, json={
            "case_id": case.case_id, "idempotency_key": "ux63-thread",
        })
        assert thread.status_code == 201, thread.text
        thread_id = thread.json()["thread_id"]
        wrong_message = owner.post(
            f"/api/cases/messages/threads/{thread_id}/messages",
            headers=owner_headers,
            json={"case_id": other.case_id, "text": SEALED_TEXT.decode(), "idempotency_key": "ux63-wrong-message"},
        )
        assert wrong_message.status_code >= 400, wrong_message.text
        assert SEALED_TEXT.decode() not in wrong_message.text
        listed = owner.get("/api/cases/messages/threads", params={"case_id": other.case_id})
        assert listed.status_code == 200, listed.text
        assert listed.json()["threads"] == []

        stored = owner.post(
            f"/api/cases/messages/threads/{thread_id}/attachments",
            headers=owner_headers,
            json={
                "tenant_id": case.tenant_id,
                "case_id": case.case_id,
                "resource_id": case.resource_id,
                "expected_revision": case.revision,
                "artifact_revision": "ux63-1",
                "thread_id": thread_id,
                "filename": "note.txt",
                "media_type": "text/plain",
                "content_base64": base64.b64encode(ATTACHMENT_TEXT).decode("ascii"),
                "idempotency_key": "ux63-file",
            },
        )
        assert stored.status_code == 201, stored.text
        attachment_id = stored.json()["attachment_id"]
        assert world.ciphertext.objects
        assert all(ATTACHMENT_TEXT not in blob for blob in world.ciphertext.objects.values())
        wrong_download = owner.post(
            f"/api/cases/messages/threads/{thread_id}/attachments/{attachment_id}/download",
            headers=owner_headers,
            json={
                "tenant_id": other.tenant_id,
                "case_id": other.case_id,
                "resource_id": other.resource_id,
                "expected_revision": other.revision,
                "artifact_revision": "ux63-1",
                "thread_id": thread_id,
                "idempotency_key": "ux63-wrong-download",
            },
        )
        assert wrong_download.status_code >= 400, wrong_download.text
        assert ATTACHMENT_TEXT.decode() not in wrong_download.text
        assert "content_base64" not in wrong_download.text
        own_download = owner.post(
            f"/api/cases/messages/threads/{thread_id}/attachments/{attachment_id}/download",
            headers=owner_headers,
            json={
                "tenant_id": case.tenant_id,
                "case_id": case.case_id,
                "resource_id": case.resource_id,
                "expected_revision": case.revision,
                "artifact_revision": "ux63-1",
                "thread_id": thread_id,
                "idempotency_key": "ux63-own-download",
            },
        )
        assert own_download.status_code == 200, own_download.text
        assert base64.b64decode(own_download.json()["content_base64"]) == ATTACHMENT_TEXT

        for client, credential in (
            (lawyer, LAWYER_CREDENTIAL),
            (admin, ADMIN_CREDENTIAL),
            (stranger, STRANGER_CREDENTIAL),
        ):
            _csrf(client, credential)
            denied_case = client.get(f"/api/cases/{case.case_id}")
            assert denied_case.status_code == 404, denied_case.text
            assert SEALED_TEXT.decode() not in denied_case.text
            denied_preview = _preview(client, case, text["evidence_id"])
            assert denied_preview.status_code in {403, 404}, denied_preview.text
            assert SEALED_TEXT.decode() not in denied_preview.text
            denied_download = client.post(
                f"/api/cases/messages/threads/{thread_id}/attachments/{attachment_id}/download",
                headers=_csrf(client, credential),
                json={
                    "tenant_id": case.tenant_id,
                    "case_id": case.case_id,
                    "resource_id": case.resource_id,
                    "expected_revision": case.revision,
                    "artifact_revision": "ux63-1",
                    "thread_id": thread_id,
                    "idempotency_key": "ux63-denied-download",
                },
            )
            assert denied_download.status_code >= 400
            assert ATTACHMENT_TEXT.decode() not in denied_download.text
        accounts = admin.get("/api/admin/accounts")
        assert accounts.status_code == 200, accounts.text
        assert accounts.json()["case_content"] is None
        assert accounts.json()["evidence"] == []
        assert case.case_id not in accounts.text
        assert SEALED_TEXT.decode() not in accounts.text


def test_missing_consent_and_stale_key_source_and_result_are_denied(tmp_path):
    world = security_world(tmp_path)
    case = world.case
    with TestClient(world.app, base_url="https://testserver") as owner:
        headers = _csrf(owner)
        text = _receive(owner, case, headers, "sealed.txt", "text/plain", SEALED_TEXT, "ux63-stale-text")
        consent = owner.get(f"/api/cases/{case.case_id}/processing-consent")
        assert consent.status_code == 200, consent.text
        assert consent.json()["egress_authorized"] is False
        missing = owner.post(
            f"/api/cases/{case.case_id}/processing-consent/late-result",
            headers=headers,
            json={
                "purpose": "extract_facts",
                "consent_generation": 0,
                "result_id": "ux63-late",
                "expected_generation": 0,
            },
        )
        assert missing.status_code == 200, missing.text
        assert missing.json()["admitted"] is False
        assert missing.json()["display_allowed"] is False
        assert missing.json()["code"] == "local_private"
        assert SEALED_TEXT.decode() not in missing.text
        saved = owner.post(
            f"/api/cases/{case.case_id}/processing-consent",
            headers=headers,
            json={
                "purpose": "extract_facts",
                "mode": "grok_cloud",
                "explicit_case_purpose": True,
                "expected_generation": 0,
            },
        )
        assert saved.status_code == 200, saved.text
        stale_result = owner.post(
            f"/api/cases/{case.case_id}/processing-consent/late-result",
            headers=headers,
            json={
                "purpose": "extract_facts",
                "consent_generation": 0,
                "result_id": "ux63-late",
                "expected_generation": saved.json()["generation"],
            },
        )
        assert stale_result.status_code == 200, stale_result.text
        assert stale_result.json()["admitted"] is False
        assert stale_result.json()["display_allowed"] is False
        assert stale_result.json()["code"] == "consent_generation_mismatch"

        current = _preview(owner, case, text["evidence_id"])
        assert SEALED_TEXT.decode() in current.json()["accessible_text"]
        for cid in list(world.evidence_backend._blobs):
            world.evidence_backend._blobs[cid] = b"replaced-ciphertext"
        stale_source = _preview(owner, case, text["evidence_id"])
        assert stale_source.status_code >= 400, stale_source.text
        assert SEALED_TEXT.decode() not in stale_source.text

    actor = world.owner.principal_id
    opened = world.service.synchronize_key_coherence(
        action="unlock", tenant_id=case.tenant_id, case_id=case.case_id,
        actor_id=actor, passphrase=PASSPHRASE,
    )
    assert opened["admitted"] is True
    rotated = world.service.synchronize_key_coherence(
        action="rotate", tenant_id=case.tenant_id, case_id=case.case_id, actor_id=actor,
        expected_epoch=opened["epoch"], captured_key_id=opened["data_key_id"],
    )
    assert rotated["admitted"] is True
    with pytest.raises(Exception) as stale_key:
        world.service.update_draft(
            case.tenant_id, body=SEALED_TEXT.decode(), case_id=case.case_id, actor_id=actor,
            expected_key_epoch=opened["epoch"], captured_key_id=opened["data_key_id"],
        )
    assert stale_key.value.code == "stale_key_epoch"
    assert SEALED_TEXT.decode() not in str(stale_key.value)


def _launch(tmp_path, monkeypatch, world):
    denial = browser.probe_inherited_network_denial()
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux63-profile"
    profile.mkdir(mode=0o700)
    playwright = browser._load_sync_playwright()().start()
    context = browser._launch_context(playwright, chromium.path, profile, bridge)
    browser._assert_process_custody(node, chromium, profile)
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(20000)
    return page, playwright, context, node, profile, bridge


def _close(playwright, context, node, profile):
    context.close()
    playwright.stop()
    observed = browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
    cleanup = browser._wait_for_cleanup(observed)
    assert cleanup["cleaned"], cleanup
    assert cleanup["remaining_pids"] == []


def _probe_channel(page, script: str) -> str:
    """One unsupported transport. An abort is denial, not a served channel."""

    try:
        value = page.evaluate(script, browser.SAME_ORIGIN)
    except Exception as exc:
        text = f"{type(exc).__name__}: {exc}"
        if "AbortError" not in text and "Timeout" not in text:
            raise
        return "denied:" + type(exc).__name__
    if not isinstance(value, str) or not value:
        raise AssertionError(f"transport probe returned {value!r}")
    return value


def _unsupported_transport_probe(page) -> dict[str, str]:
    """SSE, WebSocket, and streaming stay closed. Each probe has its own deadline."""

    events = _probe_channel(
        page,
        """async (origin) => {
            const finish = new Promise((resolve) => {
                let settled = false;
                const done = (value) => { if (!settled) { settled = true; resolve(value); } };
                const source = new EventSource(origin + '/events');
                source.onerror = () => { source.close(); done('sse-error'); };
                source.onopen = () => { source.close(); done('sse-open'); };
                setTimeout(() => { source.close(); done('sse-denied'); }, 8000);
            });
            return finish;
        }""",
    )
    socket_result = _probe_channel(
        page,
        """async (origin) => {
            const finish = new Promise((resolve) => {
                let settled = false;
                const done = (value) => { if (!settled) { settled = true; resolve(value); } };
                let socket;
                try {
                    socket = new WebSocket(origin.replace('http://', 'ws://') + '/socket');
                } catch (error) {
                    done('websocket-error');
                    return;
                }
                socket.onopen = () => { socket.close(); done('websocket-open'); };
                socket.onerror = () => done('websocket-error');
                socket.onclose = () => done('websocket-closed');
                setTimeout(() => { try { socket.close(); } catch (error) {} done('websocket-denied'); }, 8000);
            });
            return finish;
        }""",
    )
    stream_result = _probe_channel(
        page,
        """async (origin) => {
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), 8000);
            try {
                await fetch(origin + '/stream', {signal: controller.signal});
                return 'stream-open';
            } catch (error) {
                return 'stream-error';
            } finally {
                clearTimeout(timer);
            }
        }""",
    )
    return {"events": events, "socketResult": socket_result, "streamResult": stream_result}


def test_browser_renders_hostile_evidence_as_data_and_rejects_unsupported_transports(tmp_path, monkeypatch):
    world = security_world(tmp_path / "browser")
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _csrf(client)
        hostile = _receive(client, world.case, csrf, "hostile.html", "text/html", HOSTILE_HTML, "ux63-ui-html")
        text = _receive(client, world.case, csrf, "sealed.txt", "text/plain", SEALED_TEXT, "ux63-ui-text")
    before_network = browser.probe_inherited_network_denial()
    page, playwright, context, node, profile, bridge = _launch(tmp_path, monkeypatch, world)
    remote = []
    page.on("request", lambda request: remote.append(request.url) if "evil.invalid" in request.url else None)
    try:
        opened = page.goto(browser.SAME_ORIGIN + "/workspace", wait_until="domcontentloaded")
        assert opened.status == 200
        page.wait_for_function(
            """() => {
                const node = document.getElementById('complaint-interface-requests');
                const pending = node && node.dataset.lifecycle === 'pending';
                return Boolean(window.complaintCaseShell && window.workspaceClient && !pending);
            }"""
        )
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
        # The shell retires in-flight /api fetches when hydration changes the
        # actor or key binding. Retry only that abort; a real denial still fails.
        issued = page.evaluate(
            """async () => {
                async function login() {
                    const response = await fetch('/api/complaint-workspace/auth/login', {
                        method: 'POST', credentials: 'same-origin',
                        headers: {'content-type': 'application/json'},
                        body: JSON.stringify({credential: 'synthetic-owner-credential'}),
                    });
                    if (!response.ok) throw new Error('login-http-' + response.status);
                    return response.json();
                }
                let body;
                let lastError;
                for (let attempt = 0; attempt < 4; attempt += 1) {
                    try {
                        body = await login();
                        lastError = null;
                        break;
                    } catch (error) {
                        lastError = error;
                        if (!error || error.name !== 'AbortError') throw error;
                        await new Promise((resolve) => setTimeout(resolve, 40));
                    }
                }
                if (!body) throw lastError || new Error('login-aborted');
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
        page.wait_for_selector("#evidence-library")
        page.click(f"#evidence-library-list [data-evidence-id='{text['evidence_id']}']")
        page.wait_for_function(
            """(needle) => {
                const stage = document.getElementById('evidence-preview-stage');
                return stage && stage.textContent.includes(needle);
            }""",
            arg=SEALED_TEXT.decode(),
        )
        page.click(f"#evidence-library-list [data-evidence-id='{hostile['evidence_id']}']")
        page.wait_for_function(
            """() => {
                const node = document.getElementById('evidence-preview-alternative');
                return node && !node.hidden && node.textContent.includes('cannot be previewed safely');
            }"""
        )
        assert page.evaluate("() => window.__previewRan") is None
        assert page.locator("#evidence-preview script, #evidence-preview iframe").count() == 0
        assert "synthetic-hostile-ux63" in page.locator("#evidence-preview-alternative").inner_text()
        assert not remote
        transports = _unsupported_transport_probe(page)
        assert transports["events"] in {"sse-error", "sse-denied"} or transports["events"].startswith("denied:")
        assert transports["socketResult"] in {"websocket-error", "websocket-closed", "websocket-denied"} or transports["socketResult"].startswith("denied:")
        assert transports["streamResult"] == "stream-error" or transports["streamResult"].startswith("denied:")
        assert set(UNSUPPORTED_TRANSPORTS) == {"websocket", "sse", "streaming"}
        assert bridge.aborted_unqualified["sse"]
        assert bridge.aborted_unqualified["streaming"] or transports["streamResult"].startswith("denied:")
        assert bridge.aborted_unqualified["websocket"] or transports["socketResult"] != "websocket-open"
        after_network = browser.probe_inherited_network_denial()
        assert before_network == after_network
        if before_network["af_unix_only"]:
            assert after_network["af_inet"]["opened"] is False
    finally:
        _close(playwright, context, node, profile)
