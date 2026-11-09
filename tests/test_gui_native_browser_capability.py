"""Capability contract for the native browser harness.

Missing browsers and required skips are failures. The checks below do not
turn an unavailable browser into a passing fallback.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from tests.gui_native_browser import (
    SAME_ORIGIN,
    BrowserCapabilityError,
    BrowserHttpRequest,
    QualificationReport,
    SameOriginAsgiBridge,
    build_qualification_app,
    discover_chromium,
    forward_browser_headers,
    pin_executables,
)


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests" / "gui_native_browser.py"
CAPABILITY = Path(__file__)
QUALIFICATION = ROOT / "tests" / "test_cimp_gui_02.py"
_FORBIDDEN_SNIPPETS = ("httpx", "Cookies(", "pytest.skip", "pytest.importorskip")


def _calls_skip(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
        if name in {"skip", "importorskip", "xfail"}:
            return True
    return False


def assert_harness_source_contract() -> None:
    source = HARNESS.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module or ""
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
    )
    if "httpx" in imported or "httpx" in source:
        raise AssertionError("the bridge must not use an HTTPX cookie jar")
    for snippet in _FORBIDDEN_SNIPPETS:
        if snippet in source:
            raise AssertionError(f"harness contains forbidden snippet: {snippet}")
    for path in (HARNESS, CAPABILITY, QUALIFICATION):
        if _calls_skip(path):
            raise AssertionError(f"required module requests a skip: {path.name}")


def assert_qualification_report(report: QualificationReport) -> None:
    if not report.network_denial["af_unix_only"] or not report.network_denial["unchanged"]:
        raise AssertionError("inherited AF_UNIX-only denial was not preserved")
    if not report.pipe_transport or "--remote-debugging-pipe" not in report.chromium.argv:
        raise AssertionError("Chromium CDP pipe custody is incomplete")
    if report.node.argv[-1] != "run-driver":
        raise AssertionError("Playwright Node argv is not pinned")
    if report.persisted_note != "synthetic-note-02":
        raise AssertionError("DOM note was not persisted by the app")
    if report.health_status != 200 or "/health" not in report.same_origin_paths:
        raise AssertionError("same-origin HTTP did not reach the actual app")
    if not report.aborted_external or not report.aborted_service_workers:
        raise AssertionError("external origin or service worker was not aborted")
    if report.cookie_replayed_by_bridge or report.injected_actor_header:
        raise AssertionError("bridge stored cookies or injected actor authority")
    login = report.login_logout
    if not login["login_authenticated"] or not login["whoami_authenticated"]:
        raise AssertionError("browser login cookie did not reach the app")
    if login["logout_authenticated"] or not login["http_only_hidden"]:
        raise AssertionError("browser logout or HttpOnly cookie fidelity failed")
    if login["marker"] != "from-browser" or login["actor_headers"]:
        raise AssertionError("browser header was not forwarded unchanged")
    if not report.cross_context_isolated:
        raise AssertionError("cookie leaked across browser contexts")
    if report.download["bytes"] != b"synthetic-download-02\n":
        raise AssertionError("download body was not qualified")
    import hashlib
    assert report.download_transport == "same_origin_fetch_blob"
    assert report.direct_attachment_navigation_qualified is False
    assert report.download["sha256"] == hashlib.sha256(report.download["bytes"]).hexdigest()
    assert report.download["filename"] == report.download["suggested_filename"] == "synthetic-note.txt"
    assert report.download["content_type"] == "text/plain; charset=utf-8"
    assert "attachment" in report.download["content_disposition"]
    assert report.download["status"] == 200
    assert report.download["cookie_scope_verified"] is True
    assert report.download["revoked_status"] == 401
    assert report.playwright_version
    assert report.unsupported_transport_outcomes["events"] == "sse-error"
    assert report.unsupported_transport_outcomes["socketResult"] in {"websocket-closed", "websocket-error"}
    assert report.unsupported_transport_outcomes["streamResult"] == "stream-error"
    if not report.child_cleanup["cleaned"] or report.child_cleanup["owned_count"] < 1:
        raise AssertionError("owned browser descendants were not measured or not cleaned")
    for name in ("websocket", "sse", "streaming"):
        if report.qualified_transports[name]:
            raise AssertionError(f"{name} was claimed from HTTP interception")
        if name not in report.limitations[0] and name not in " ".join(report.limitations).lower() and name != "streaming":
            raise AssertionError(f"{name} limitation was not recorded")
    if report.qualified_transports["streaming"]:
        raise AssertionError("streaming was claimed")
    joined = " ".join(report.limitations).lower()
    if "websocket" not in joined or "server-sent" not in joined or "streaming" not in joined:
        raise AssertionError("unqualified transports were not stated")


def test_harness_source_has_no_cookie_jar_or_required_skip() -> None:
    assert_harness_source_contract()


def test_missing_chromium_fails_instead_of_skipping(tmp_path: Path) -> None:
    missing = tmp_path / "missing-chromium"
    with pytest.raises(BrowserCapabilityError, match="Chromium executable is missing"):
        discover_chromium(missing)


def test_header_forwarding_copies_browser_values_without_actor_authority() -> None:
    forwarded = forward_browser_headers([
        ("Cookie", "cimp_gui_02_session=synthetic"),
        ("X-Cimp-Gui-Marker", "from-browser"),
        ("Connection", "close"),
        ("Upgrade", "websocket"),
    ])
    names = [name.decode("latin-1") for name, _value in forwarded]
    values = dict(forwarded)
    assert names == ["cookie", "x-cimp-gui-marker"]
    assert values[b"cookie"] == b"cimp_gui_02_session=synthetic"
    assert values[b"x-cimp-gui-marker"] == b"from-browser"
    assert b"x-actor-id" not in values
    assert b"authorization" not in values


def test_bridge_forwards_set_cookie_and_does_not_replay_it(tmp_path: Path) -> None:
    application, fixture = build_qualification_app(tmp_path / "state")
    bridge = SameOriginAsgiBridge(application)
    login = bridge.handle(BrowserHttpRequest(
        "POST",
        f"{SAME_ORIGIN}/__cimp_gui_02__/login",
        headers=[("x-cimp-gui-marker", "from-browser")],
    ))
    assert login.action == "fulfill"
    set_cookie = dict(login.headers)["set-cookie"]
    assert set_cookie.startswith("cimp_gui_02_session=")
    assert "HttpOnly" in set_cookie
    anonymous = bridge.handle(BrowserHttpRequest(
        "GET",
        f"{SAME_ORIGIN}/__cimp_gui_02__/whoami",
        headers=[("x-cimp-gui-marker", "from-browser")],
    ))
    assert json.loads(anonymous.body)["authenticated"] is False
    token = set_cookie.split(";", 1)[0].split("=", 1)[1]
    authed = bridge.handle(BrowserHttpRequest(
        "GET",
        f"{SAME_ORIGIN}/__cimp_gui_02__/whoami",
        headers=[("cookie", f"cimp_gui_02_session={token}"), ("x-cimp-gui-marker", "from-browser")],
    ))
    payload = json.loads(authed.body)
    assert payload["authenticated"] is True
    assert payload["marker"] == "from-browser"
    assert payload["actor_headers"] == []
    download = bridge.handle(BrowserHttpRequest(
        "GET", f"{SAME_ORIGIN}/__cimp_gui_02__/download",
        headers=[("cookie", f"cimp_gui_02_session={token}"), ("x-cimp-gui-marker", "from-browser")],
    ))
    assert download.body == b"synthetic-download-02\n"
    assert "attachment" in dict(download.headers)["content-disposition"]
    logout = bridge.handle(BrowserHttpRequest(
        "POST",
        f"{SAME_ORIGIN}/__cimp_gui_02__/logout",
        headers=[("cookie", f"cimp_gui_02_session={token}")],
    ))
    assert "Max-Age=0" in dict(logout.headers)["set-cookie"]
    assert token not in fixture.sessions
    external = bridge.handle(BrowserHttpRequest("GET", "https://example.invalid/secret", headers=[]))
    worker = bridge.handle(BrowserHttpRequest("GET", f"{SAME_ORIGIN}/sw.js", headers=[], resource_type="serviceworker"))
    events = bridge.handle(BrowserHttpRequest(
        "GET",
        f"{SAME_ORIGIN}/__cimp_gui_02__/events",
        headers=[("accept", "text/event-stream")],
    ))
    stream = bridge.handle(BrowserHttpRequest("GET", f"{SAME_ORIGIN}/__cimp_gui_02__/stream", headers=[]))
    socket = bridge.handle(BrowserHttpRequest("GET", "ws://127.0.0.1:41731/socket", headers=[]))
    assert external.action == worker.action == events.action == stream.action == socket.action == "abort"
    assert bridge.asgi_calls == 5
    saved = bridge.handle(BrowserHttpRequest(
        "POST",
        f"{SAME_ORIGIN}/__cimp_gui_02__/notes",
        headers=[("content-type", "application/json")],
        body=b'{"note":"synthetic-note-02"}',
    ))
    assert json.loads(saved.body)["stored"] is True
    assert fixture.notes() == ["synthetic-note-02"]
    download = bridge.handle(BrowserHttpRequest("GET", f"{SAME_ORIGIN}/__cimp_gui_02__/download", headers=[]))
    assert download.status == 401
    assert b"synthetic-download-02" not in download.body
    revoked_download = bridge.handle(BrowserHttpRequest(
        "GET", f"{SAME_ORIGIN}/__cimp_gui_02__/download",
        headers=[("cookie", f"cimp_gui_02_session={token}")],
    ))
    assert revoked_download.status == 401
    assert b"synthetic-download-02" not in revoked_download.body


def test_installed_pins_or_missing_stack_do_not_skip() -> None:
    try:
        node, chromium = pin_executables()
    except BrowserCapabilityError as exc:
        assert str(exc)
        assert "skip" not in str(exc).lower()
        return
    assert node.argv[0] == node.path
    assert chromium.argv[0] == chromium.path
    assert Path(node.path).is_file()
    assert Path(chromium.path).is_file()


def test_driver_discovery_accepts_installed_sync_api_package(tmp_path: Path, monkeypatch) -> None:
    """Filesystem discovery fixture only; the synthetic executable is never run."""
    import sys
    from types import ModuleType
    from tests import gui_native_browser as harness

    package = tmp_path / "installed-playwright"
    (package / "sync_api").mkdir(parents=True)
    (package / "sync_api" / "__init__.py").write_text("")
    module_file = package / "__init__.py"
    module_file.write_text("")
    driver = package / "driver"
    (driver / "package").mkdir(parents=True)
    cli = driver / "package" / "cli.js"
    cli.write_text("")
    node = driver / "node"
    node.write_text("discovery fixture, never executed")
    node.chmod(0o700)
    installed = ModuleType("playwright")
    installed.__file__ = str(module_file)
    monkeypatch.setitem(sys.modules, "playwright", installed)
    assert not (package / "sync_api.py").exists()
    assert harness.discover_playwright_driver() == (node.resolve(), cli.resolve())


@pytest.mark.parametrize("cache_name,layout", [
    ("chromium_headless_shell", "chrome-headless-shell-linux64/chrome-headless-shell"),
    ("chromium", "chrome-linux64/chrome"),
    ("chromium_headless_shell", "chrome-linux/headless_shell"),
    ("chromium", "chrome-linux/chrome"),
])
def test_chromium_discovery_matches_driver_manifest(tmp_path: Path, monkeypatch, cache_name: str, layout: str) -> None:
    """Cache fixtures qualify discovery, never browser execution or completion."""
    from tests import gui_native_browser as harness

    cli = tmp_path / "driver" / "package" / "cli.js"
    cli.parent.mkdir(parents=True)
    cli.write_text("")
    (cli.parent / "browsers.json").write_text(json.dumps({"browsers": [
        {"name": "chromium", "revision": "1200"},
        {"name": "chromium-headless-shell", "revision": "1200"},
    ]}))
    cache = tmp_path / "cache"
    for revision in ("9999", "1200"):
        executable = cache / f"{cache_name}-{revision}" / layout
        executable.parent.mkdir(parents=True)
        executable.write_text("discovery fixture, never executed")
        executable.chmod(0o700)
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(cache))
    monkeypatch.setattr(harness, "discover_playwright_driver", lambda: (tmp_path / "unused-node", cli))
    assert discover_chromium() == (cache / f"{cache_name}-1200" / layout).resolve()


def test_approved_cache_with_only_other_revision_fails_closed(tmp_path: Path, monkeypatch) -> None:
    from tests import gui_native_browser as harness

    cli = tmp_path / "driver" / "package" / "cli.js"
    cli.parent.mkdir(parents=True)
    cli.write_text("")
    (cli.parent / "browsers.json").write_text(json.dumps({"browsers": [
        {"name": "chromium", "revision": "1200"},
    ]}))
    executable = tmp_path / "cache" / "chromium-9999" / "chrome-linux64" / "chrome"
    executable.parent.mkdir(parents=True)
    executable.write_text("discovery fixture, never executed")
    executable.chmod(0o700)
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path / "cache"))
    monkeypatch.setattr(harness, "discover_playwright_driver", lambda: (tmp_path / "unused-node", cli))
    with pytest.raises(BrowserCapabilityError, match="Playwright manifest revision"):
        discover_chromium()


def test_bridge_preserves_actual_asgi_effects_inside_running_loop(tmp_path: Path) -> None:
    import asyncio

    application, fixture = build_qualification_app(tmp_path / "running-loop-state")
    bridge = SameOriginAsgiBridge(application)

    async def exercise() -> None:
        response = bridge.handle(BrowserHttpRequest(
            "POST", f"{SAME_ORIGIN}/__cimp_gui_02__/notes",
            headers=[("content-type", "application/json")],
            body=b'{"note":"running-loop-note"}',
        ))
        assert response.action == "fulfill"
        assert json.loads(response.body)["stored"] is True
        assert fixture.notes() == ["running-loop-note"]
        assert bridge.asgi_calls == 1

    asyncio.run(exercise())


def test_bridge_propagates_actual_asgi_failure_inside_running_loop() -> None:
    import asyncio

    async def unavailable_app(scope, receive, send):
        raise ValueError("synthetic ASGI operation unavailable")

    bridge = SameOriginAsgiBridge(unavailable_app)

    async def exercise() -> None:
        with pytest.raises(ValueError, match="synthetic ASGI operation unavailable"):
            bridge.handle(BrowserHttpRequest("GET", f"{SAME_ORIGIN}/health", headers=[]))

    asyncio.run(exercise())


def test_actual_failed_asgi_route_aborts_browser_fetch_and_preserves_error(tmp_path: Path, monkeypatch) -> None:
    """A real app error must settle fetch and remain an error for the validator."""
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse
    from tests import gui_native_browser as browser

    assert browser.probe_inherited_network_denial()["af_unix_only"]
    application = FastAPI()
    original_error = TypeError("synthetic ASGI route failure")

    @application.get("/")
    async def document():
        return HTMLResponse("<!doctype html><title>actual error delivery</title>")

    @application.get("/actual-error")
    async def actual_error():
        raise original_error

    bridge = browser.SameOriginAsgiBridge(application)
    node, chromium = browser.pin_executables()
    profile = tmp_path / "actual-error-browser-profile"
    profile.mkdir(mode=0o700)
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    playwright, context = None, None
    observed = set()
    try:
        playwright = browser._load_sync_playwright()().start()
        context = browser._launch_context(playwright, chromium.path, profile, bridge)
        browser._assert_process_custody(node, chromium, profile)
        observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(browser.SAME_ORIGIN + "/", wait_until="domcontentloaded")
        errors = []

        def record_error(failure):
            # Playwright preserves the type but prefixes the API call name.
            assert type(failure) is type(original_error)
            assert "synthetic ASGI route failure" in str(failure)
            errors.append(type(failure))

        def read_after_error(operation):
            try:
                return operation()
            except TypeError as failure:
                record_error(failure)
                return operation()

        try:
            page.evaluate("""() => {
                window.failedRouteState = 'pending';
                fetch('/actual-error').then(
                    () => { window.failedRouteState = 'fulfilled'; },
                    () => { window.failedRouteState = 'rejected'; });
            }""")
        except TypeError as failure:
            record_error(failure)
        read_after_error(lambda: page.wait_for_function(
            "window.failedRouteState !== 'pending'", timeout=5000))
        assert read_after_error(lambda: page.evaluate("window.failedRouteState")) == "rejected"
        assert errors == [TypeError]
        assert bridge.same_origin_paths == ["/"]
        assert bridge.asgi_calls == 2
    finally:
        try:
            if context is not None:
                try:
                    context.close()
                except TypeError as failure:
                    assert "synthetic ASGI route failure" in str(failure)
                    context.close()
        finally:
            if playwright is not None:
                playwright.stop()
            assert browser._wait_for_cleanup(observed)["cleaned"]
