"""Safe previews of encrypted evidence bytes.

Supported text, PDF, and still images open from the sealed artifact with
page and span anchors. HTML and other active formats stay data. A preview
does not call a model, fetch a remote address, or reuse another case's bytes.
"""

from __future__ import annotations

import base64
import struct
import zlib

import pytest
from fastapi.testclient import TestClient

from integrations.evidence_workspace import MemoryByteBackend
from integrations.ipfs_datasets.llm import _REMOTE_INVOCATIONS, clear_remote_invocation_bindings
from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import PASSPHRASE, _composed_headers, _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

TEXT_NAME = "denial-letter.txt"
PDF_NAME = "denial-letter.pdf"
PNG_NAME = "doorway.png"
JPEG_NAME = "stair.jpeg"
HTML_NAME = "hostile.html"
TEXT_LINES = (
    "Line alpha housing denial https://evil.invalid/note",
    "Line beta span target",
)
PDF_PAGES = ("page one notice", "synthetic denial on page two")
WEBP_B64 = "UklGRiQAAABXRUJQVlA4IBgAAAAwAQCdASoBAAEAAUAmJaQAA3AA/v0gUAA="
HOSTILE_HTML = b"<script>window.__previewRan=1</script><iframe src=\"https://evil.invalid/frame\"></iframe><img src=\"https://evil.invalid/x.png\">"


def _png(width: int, height: int) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + bytes((20, 40, 60)) * width for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def _jpeg(width: int, height: int) -> bytes:
    """A still JPEG header with a start-of-frame segment and no external data."""

    frame = bytes([8]) + struct.pack(">HHB", height, width, 1) + bytes((1, 0x11, 0))
    return b"\xff\xd8\xff\xc0" + struct.pack(">H", len(frame) + 2) + frame + b"\xff\xd9"


def _pdf(pages: list[str]) -> bytes:
    objects: list[bytes] = [b""]
    content_ids = []
    next_id = 3
    for _page in pages:
        content_ids.append(next_id + 1)
        next_id += 2
    kids = " ".join(f"{3 + (index * 2)} 0 R" for index in range(len(pages)))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Count {len(pages)} /Kids [{kids}] >>".encode())
    for index, text in enumerate(pages):
        safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf ({safe}) Tj ET".encode()
        objects.append(f"<< /Type /Page /Parent 2 0 R /Contents {content_ids[index]} 0 R >>".encode())
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    objects.append(b"<< /S /JavaScript /JS (app.alert('nope')) /URI (https://evil.invalid/pdf) >>")
    parts = [b"%PDF-1.4\n"]
    offsets = [0]
    for number, body in enumerate(objects[1:], start=1):
        offsets.append(sum(len(part) for part in parts))
        parts.append(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref_at = sum(len(part) for part in parts)
    xref = [f"xref\n0 {len(objects)}\n".encode(), b"0000000000 65535 f \n"]
    xref.extend(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    trailer = (
        f"trailer << /Size {len(objects)} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode()
    )
    return b"".join(parts + xref + [trailer])


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
    return world


def _receive(client, case, csrf, source, original, media, content, key):
    response = client.post(
        "/api/cases/evidence",
        headers=_composed_headers(case, csrf),
        json={
            "tenant_id": case.tenant_id,
            "case_id": case.case_id,
            "resource_id": case.resource_id,
            "source_filename": source,
            "original_filename": original,
            "media_type": media,
            "content_base64": base64.b64encode(content).decode("ascii"),
            "idempotency_key": key,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _preview(client, case, evidence_id, *, version=None, extra=""):
    query = (
        f"/api/cases/evidence/preview?tenant_id={case.tenant_id}&case_id={case.case_id}"
        f"&resource_id={case.resource_id}&evidence_id={evidence_id}"
    )
    if version is not None:
        query += f"&version={version}"
    query += extra
    return client.get(query, headers=_composed_headers(case))


def test_preview_reads_sealed_text_pdf_image_and_exact_version(tmp_path):
    world = _ready(tmp_path)
    png = _png(2, 2)
    jpeg = _jpeg(2, 3)
    webp = base64.b64decode(WEBP_B64)
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        text = _receive(client, world.case, csrf, TEXT_NAME, TEXT_NAME, "text/plain", "\n".join(TEXT_LINES).encode(), "ux16-text")
        pdf = _receive(client, world.case, csrf, PDF_NAME, PDF_NAME, "application/pdf", _pdf(list(PDF_PAGES)), "ux16-pdf")
        image = _receive(client, world.case, csrf, PNG_NAME, PNG_NAME, "image/png", png, "ux16-png")
        photo = _receive(client, world.case, csrf, JPEG_NAME, JPEG_NAME, "image/jpeg", jpeg, "ux16-jpeg")
        still = _receive(client, world.case, csrf, "still.webp", "still.webp", "image/webp", webp, "ux16-webp")
        opened = _preview(client, world.case, text["evidence_id"])
        assert opened.status_code == 200, opened.text
        assert opened.headers["cache-control"] == "no-store, max-age=0, private"
        body = opened.json()
        assert body["supported"] is True and body["preview_kind"] == "text"
        assert body["pages"][0]["anchor"] == "page-1"
        assert [span["text"] for span in body["pages"][0]["spans"]] == list(TEXT_LINES)
        assert body["pages"][0]["spans"][1]["anchor"] == "page-1-span-2"
        assert body["model_invoked"] is False and body["external_fetch"] is False
        assert body["image"] is None

        document = _preview(client, world.case, pdf["evidence_id"]).json()
        assert document["preview_kind"] == "pdf"
        assert [page["spans"][0]["text"] for page in document["pages"]] == list(PDF_PAGES)
        assert document["pages"][1]["anchor"] == "page-2"
        assert "app.alert" not in document["accessible_text"]
        assert "evil.invalid" not in document["accessible_text"]
        assert document["active_content_executed"] is False
        assert "content_base64" not in opened.text

        rendered = _preview(client, world.case, image["evidence_id"]).json()
        assert rendered["preview_kind"] == "image"
        assert rendered["image"]["width"] == 2 and rendered["image"]["height"] == 2
        assert base64.b64decode(rendered["image"]["content_base64"]) == png
        assert "2 by 2 pixels" in rendered["accessible_text"]
        photo_body = _preview(client, world.case, photo["evidence_id"]).json()
        assert photo_body["image"]["width"] == 2 and photo_body["image"]["height"] == 3
        webp_body = _preview(client, world.case, still["evidence_id"]).json()
        assert webp_body["image"]["width"] == 1 and webp_body["image"]["height"] == 1

        extracted = client.post(
            "/api/cases/evidence/lifecycle",
            headers=_composed_headers(world.case, csrf),
            json={
                "tenant_id": world.case.tenant_id,
                "case_id": world.case.case_id,
                "resource_id": world.case.resource_id,
                "evidence_id": text["evidence_id"],
                "action": "extract",
                "expected_artifact_version": 1,
                "extracted_content_base64": base64.b64encode(b"extracted sentence only").decode("ascii"),
                "idempotency_key": "ux16-extract",
            },
        )
        assert extracted.status_code == 200, extracted.text
        current = _preview(client, world.case, text["evidence_id"]).json()
        original = _preview(client, world.case, text["evidence_id"], version=1).json()
        assert current["version"] == 2 and current["accessible_text"] == "extracted sentence only"
        assert original["version"] == 1 and "Line beta span target" in original["accessible_text"]
        assert "extracted sentence only" not in original["accessible_text"]


def test_preview_blocks_active_content_other_cases_locked_keys_and_models(tmp_path):
    world = _ready(tmp_path)
    other = world.cases.create_case(actor_principal_id=world.owner.principal_id)
    clear_remote_invocation_bindings()
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        text = _receive(
            client, world.case, csrf, TEXT_NAME, TEXT_NAME, "text/plain",
            b"sealed sentence stays in this case", "ux16-seal",
        )
        hostile = _receive(client, world.case, csrf, HTML_NAME, HTML_NAME, "text/html", HOSTILE_HTML, "ux16-html")
        tiff = _receive(client, world.case, csrf, "scan.tiff", "scan.tiff", "image/tiff", b"II*\x00not-a-real-tiff", "ux16-tiff")
        posed = _receive(client, world.case, csrf, PNG_NAME, PNG_NAME, "image/png", b"<script>alert(1)</script>", "ux16-fake-png")

        alternative = _preview(client, world.case, hostile["evidence_id"])
        assert alternative.status_code == 200, alternative.text
        refused = alternative.json()
        assert refused["supported"] is False
        assert refused["alternative"]["reason"] == "unsupported_format"
        assert "cannot be previewed safely" in refused["alternative"]["message"]
        assert refused["image"] is None and refused["pages"] == []
        assert refused["model_invoked"] is False and refused["active_content_executed"] is False
        assert "<script" in refused["alternative"]["safe_text"]

        tiff_body = _preview(client, world.case, tiff["evidence_id"]).json()
        assert tiff_body["supported"] is False
        assert tiff_body["alternative"]["reason"] == "unsupported_format"
        fake = _preview(client, world.case, posed["evidence_id"]).json()
        assert fake["supported"] is False and fake["image"] is None
        assert fake["alternative"]["reason"] == "content_not_renderable"

        stolen = _preview(client, other, text["evidence_id"])
        assert stolen.status_code == 403, stolen.text
        assert "sealed sentence" not in stolen.text
        model = _preview(client, world.case, text["evidence_id"], extra="&invoke_model=true&prompt=read")
        assert model.status_code == 403, model.text
        assert "sealed sentence" not in model.text
        assert _REMOTE_INVOCATIONS == {}

        stranger = client.post("/api/complaint-workspace/auth/login", json={"credential": "synthetic-stranger-credential"})
        assert stranger.status_code == 200
        denied = _preview(client, world.case, text["evidence_id"])
        assert denied.status_code == 403
        assert "sealed sentence" not in denied.text

    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        opened = _preview(client, world.case, text["evidence_id"])
        assert "sealed sentence stays in this case" in opened.json()["accessible_text"]
        backend = world.app.state.evidence_workspace._backend
        for cid in list(backend._blobs):
            backend._blobs[cid] = b"replaced-ciphertext"
        stale = _preview(client, world.case, text["evidence_id"])
        assert stale.status_code == 503
        assert "sealed sentence" not in stale.text
        assert _REMOTE_INVOCATIONS == {}

    world.owner_keys.lock()
    with TestClient(world.app, base_url="https://testserver") as client:
        _composed_login(client)
        locked = _preview(client, world.case, text["evidence_id"])
        assert locked.status_code == 503
        assert "sealed sentence" not in locked.text
    world.owner_keys.unlock_passphrase(PASSPHRASE)


def _browser(tmp_path, monkeypatch):
    world = _ready(tmp_path)
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    bridge = browser.SameOriginAsgiBridge(world.app)
    world.browser_bridge = bridge
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux16-profile"
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


def _open(page, world):
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
        },
    )
    page.click("[data-tab-target='evidence']")
    page.wait_for_selector("#evidence-library")


def test_workspace_preview_zooms_anchors_and_drops_other_case_blobs(tmp_path, monkeypatch):
    world, page, playwright, context, node, profile, observed = _browser(tmp_path, monkeypatch)
    other = world.cases.create_case(actor_principal_id=world.owner.principal_id)
    remote = []
    page.on("request", lambda request: remote.append(request.url) if "evil.invalid" in request.url else None)
    try:
        with TestClient(world.app, base_url="https://testserver") as client:
            csrf = _composed_login(client)
            text = _receive(client, world.case, csrf, TEXT_NAME, TEXT_NAME, "text/plain", "\n".join(TEXT_LINES).encode(), "ux16-ui-text")
            pdf = _receive(client, world.case, csrf, PDF_NAME, PDF_NAME, "application/pdf", _pdf(list(PDF_PAGES)), "ux16-ui-pdf")
            image = _receive(client, world.case, csrf, PNG_NAME, PNG_NAME, "image/png", _png(8, 6), "ux16-ui-png")
            hostile = _receive(client, world.case, csrf, HTML_NAME, HTML_NAME, "text/html", HOSTILE_HTML, "ux16-ui-html")
        _open(page, world)
        page.wait_for_function(
            """() => {
                const stage = document.getElementById('evidence-preview-stage');
                return stage && stage.textContent.includes('Line beta span target');
            }"""
        )
        page.click("#evidence-preview-anchors a:text('Span 2')")
        assert page.evaluate("() => document.activeElement.id") == "evidence-preview-page-1-span-2"
        before = page.locator("#evidence-preview-stage").bounding_box()["height"]
        page.click("#evidence-preview-zoom-in")
        assert page.locator("#evidence-preview").get_attribute("data-zoom") == "125"
        assert page.locator("#evidence-preview-zoom-value").inner_text() == "125%"
        after = page.locator("#evidence-preview-stage").bounding_box()["height"]
        assert after > before

        page.set_viewport_size({"width": 390, "height": 800})
        page.click("#evidence-library-show-detail")
        assert page.locator("#evidence-preview-zoom-out").is_visible()
        page.click("#evidence-preview-zoom-out")
        assert page.locator("#evidence-preview").get_attribute("data-zoom") == "100"
        page.set_viewport_size({"width": 1440, "height": 1000})

        page.click(f"#evidence-library-list [data-evidence-id='{pdf['evidence_id']}']")
        page.wait_for_function(
            """() => document.getElementById('evidence-preview-stage').textContent.includes('synthetic denial on page two')"""
        )
        page.click("#evidence-preview-anchors a:text('Page 2')")
        assert page.evaluate("() => document.activeElement.id") == "evidence-preview-page-2"
        assert page.locator("#evidence-preview script").count() == 0

        page.evaluate(
            """() => {
                window.__revoked = [];
                const orig = URL.revokeObjectURL.bind(URL);
                URL.revokeObjectURL = (url) => { window.__revoked.push(String(url)); return orig(url); };
            }"""
        )
        page.click(f"#evidence-library-list [data-evidence-id='{image['evidence_id']}']")
        page.wait_for_selector("#evidence-preview-image")
        shown = page.evaluate(
            """() => {
                const image = document.getElementById('evidence-preview-image');
                return {src: image.src, width: image.naturalWidth, height: image.naturalHeight};
            }"""
        )
        assert shown["src"].startswith("blob:")
        assert shown["width"] == 8 and shown["height"] == 6
        page.click("#evidence-preview-zoom-in")
        assert page.locator("#evidence-preview").get_attribute("data-zoom") == "125"

        page.click(f"#evidence-library-list [data-evidence-id='{hostile['evidence_id']}']")
        page.wait_for_function(
            """() => {
                const node = document.getElementById('evidence-preview-alternative');
                return node && !node.hidden && node.textContent.includes('cannot be previewed safely');
            }"""
        )
        assert page.evaluate("() => window.__previewRan") is None
        assert page.locator("#evidence-preview script, #evidence-preview iframe, #evidence-preview img").count() == 0
        assert not any("evil.invalid" in url for url in remote)
        revoked = page.evaluate("() => window.__revoked")
        assert shown["src"] in revoked

        page.evaluate(
            """context => window.workspaceClient.setCaseContext(context)""",
            {
                "tenant_id": other.tenant_id,
                "case_id": other.case_id,
                "resource_id": other.resource_id,
                "revision": other.revision,
            },
        )
        page.click("#evidence-library-refresh")
        page.wait_for_function(
            """() => {
                const host = document.getElementById('evidence-library');
                return host.dataset.state === 'empty' || host.dataset.state === 'locked';
            }"""
        )
        library = page.locator("#evidence-library").inner_text()
        assert "Line beta span target" not in library
        assert "synthetic denial on page two" not in library
        assert page.locator("#evidence-preview-image").count() == 0
        assert text["evidence_id"] not in library
    finally:
        _close(playwright, context, node, profile, observed)
