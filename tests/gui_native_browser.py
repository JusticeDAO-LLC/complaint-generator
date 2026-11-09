"""Native browser qualification for the complaint GUI.

The bridge forwards one browser HTTP request at a time into the ASGI app.
It does not keep a cookie jar, and it does not add actor or role headers.
WebSocket, server-sent events, and streaming responses stay unqualified.
"""

from __future__ import annotations

import asyncio
import errno
import hashlib
import html
import json
import math
import os
import secrets
import shlex
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit

from applications.server import SERVER


SAME_ORIGIN = "http://127.0.0.1:41731"
EXTERNAL_ORIGIN = "http://127.0.0.1:41732"
EXTERNAL_NAME = "https://example.invalid"
COOKIE_NAME = "cimp_gui_02_session"
MARKER_HEADER = "x-cimp-gui-marker"
_HOP_BY_HOP = frozenset({
    "connection",
    "keep-alive",
    "proxy-connection",
    "te",
    "trailer",
    "trailers",
    "transfer-encoding",
    "upgrade",
})
_FORBIDDEN_ARGV_TOKENS = ("--remote-debugging-port", "--remote-debugging-address")
_REQUIRED_CHROMIUM_ARG = "--remote-debugging-pipe"
_UNQUALIFIED_TRANSPORTS = ("websocket", "sse", "streaming")
_ASGI_REQUEST_SECONDS = 30
_ASGI_THREAD_JOIN_SECONDS = 35
OWNED_BROWSER_CLEANUP_SECONDS = 5


class BrowserCapabilityError(RuntimeError):
    """The browser capability is missing or the custody check failed."""


class _VanishedBrowserProcess(BrowserCapabilityError):
    """A known proc metadata read failed after this numeric PID disappeared."""

    def __init__(self, pid: int):
        super().__init__("Browser process identity vanished during verification")
        self.pid = pid


@dataclass(frozen=True)
class PinnedExecutable:
    role: str
    path: str
    sha256: str
    argv: tuple[str, ...]


@dataclass
class BrowserHttpRequest:
    method: str
    url: str
    headers: list[tuple[str, str]]
    body: bytes = b""
    resource_type: str = "other"


@dataclass
class BrowserHttpResult:
    action: str
    status: int = 0
    headers: list[tuple[str, str]] = field(default_factory=list)
    body: bytes = b""
    reason: str = ""


@dataclass
class QualificationReport:
    node: PinnedExecutable
    chromium: PinnedExecutable
    playwright_version: str
    private_profiles: tuple[str, ...]
    pipe_transport: bool
    network_denial: dict[str, Any]
    same_origin_paths: list[str]
    aborted_external: list[str]
    aborted_service_workers: list[str]
    aborted_unqualified: dict[str, list[str]]
    unsupported_transport_outcomes: dict[str, str]
    header_marker: str
    injected_actor_header: bool
    cookie_replayed_by_bridge: bool
    login_logout: dict[str, Any]
    cross_context_isolated: bool
    persisted_note: str
    download: dict[str, Any]
    download_transport: str
    direct_attachment_navigation_qualified: bool
    health_status: int
    child_cleanup: dict[str, Any]
    qualified_transports: dict[str, bool]
    limitations: tuple[str, ...]


def probe_inherited_network_denial() -> dict[str, Any]:
    """Read the inherited socket policy without installing a new filter."""

    def _attempt(family: int) -> dict[str, Any]:
        try:
            opened = socket.socket(family, socket.SOCK_STREAM)
        except OSError as exc:
            return {"opened": False, "errno": exc.errno}
        opened.close()
        return {"opened": True, "errno": 0}

    unix = _attempt(socket.AF_UNIX)
    inet = _attempt(socket.AF_INET)
    inet6 = _attempt(getattr(socket, "AF_INET6", -1)) if hasattr(socket, "AF_INET6") else {"opened": False, "errno": errno.EAFNOSUPPORT}
    denied = (not inet["opened"] and inet["errno"] in {errno.EPERM, errno.EACCES}
              and not inet6["opened"] and inet6["errno"] in {errno.EPERM, errno.EACCES, errno.EAFNOSUPPORT})
    seccomp = _seccomp_status(os.getpid())
    return {
        "af_unix": unix,
        "af_inet": inet,
        "af_inet6": inet6,
        "af_unix_only": bool(unix["opened"] and denied),
        "seccomp": seccomp,
    }


def _seccomp_status(pid: int) -> dict[str, str]:
    try:
        text = Path(f"/proc/{pid}/status").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    found: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith(("Seccomp:", "Seccomp_filters:")):
            key, value = line.split(":", 1)
            found[key] = value.strip()
    return found


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _executable_file(path: Path) -> bool:
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        return False
    return resolved.is_file() and os.access(resolved, os.X_OK)


def discover_playwright_driver() -> tuple[Path, Path]:
    """Return the installed Playwright Node binary and driver cli.js."""

    repo_root = Path(__file__).resolve().parents[1]
    saved_path = sys.path[:]
    shadowed = [name for name in list(sys.modules) if name == "playwright" or name.startswith("playwright.")]
    saved_modules = {name: sys.modules.get(name) for name in shadowed}
    try:
        sys.path = [entry for entry in sys.path if Path(entry or os.getcwd()).resolve() != repo_root]
        for name in shadowed:
            module = sys.modules.get(name)
            module_file = str(getattr(module, "__file__", "") or "")
            if module is None or module_file.startswith(str(repo_root / "playwright")) or not module_file:
                sys.modules.pop(name, None)
        try:
            import playwright  # type: ignore
        except ImportError as exc:
            raise BrowserCapabilityError("Playwright Node driver is not installed") from exc
        package = Path(getattr(playwright, "__file__", "") or "").resolve().parent
        if not ((package / "sync_api.py").is_file()
                or (package / "sync_api" / "__init__.py").is_file()):
            raise BrowserCapabilityError("Playwright Node driver is not installed")
        driver = package / "driver"
        cli = driver / "package" / "cli.js"
        if not cli.is_file():
            raise BrowserCapabilityError("Playwright driver cli.js is not installed")
        bundled = driver / "node"
        node = bundled if _executable_file(bundled) else Path("/usr/bin/node")
        if not _executable_file(node):
            raise BrowserCapabilityError("Playwright Node executable is not installed")
        return node.resolve(), cli.resolve()
    finally:
        sys.path[:] = saved_path
        for name, module in saved_modules.items():
            if module is not None and name not in sys.modules:
                sys.modules[name] = module


def discover_chromium(explicit: Path | None = None) -> Path:
    if explicit is not None:
        candidate = Path(explicit)
        if not _executable_file(candidate):
            raise BrowserCapabilityError(f"Chromium executable is missing: {candidate}")
        return candidate.resolve()
    env_root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    candidates: list[Path] = []
    if env_root:
        root = Path(env_root)
        _node, cli = discover_playwright_driver()
        try:
            manifest = json.loads((cli.parent / "browsers.json").read_text(encoding="utf-8"))
            browsers = manifest["browsers"]
            if not isinstance(browsers, list):
                raise ValueError("browser entries must be a list")
            revisions = {
                item["name"]: str(item["revision"])
                for item in browsers
                if isinstance(item, dict) and item.get("name") in {"chromium", "chromium-headless-shell"}
            }
            if not revisions or any(not value.isdecimal() for value in revisions.values()):
                raise ValueError("Chromium revision is missing or invalid")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise BrowserCapabilityError("Installed Playwright browser manifest is unavailable") from exc
        headless = revisions.get("chromium-headless-shell")
        if headless:
            installed = root / f"chromium_headless_shell-{headless}"
            candidates.extend((
                installed / "chrome-headless-shell-linux64" / "chrome-headless-shell",
                installed / "chrome-linux" / "headless_shell",
            ))
        chromium = revisions.get("chromium")
        if chromium:
            installed = root / f"chromium-{chromium}"
            candidates.extend((
                installed / "chrome-linux64" / "chrome",
                installed / "chrome-linux" / "chrome",
            ))
        for candidate in candidates:
            if _executable_file(candidate):
                return candidate.resolve()
        # An explicitly approved cache must not silently select another
        # installed revision or an unrelated system browser.
        raise BrowserCapabilityError("Chromium executable is not installed for the Playwright manifest revision")
    candidates.extend((
        Path("/usr/lib/chromium/chromium"),
        Path("/usr/lib/chromium-browser/chromium-browser"),
        Path("/usr/bin/chromium"),
        Path("/usr/bin/chromium-browser"),
        Path("/opt/google/chrome/chrome"),
    ))
    for candidate in candidates:
        if _executable_file(candidate):
            return candidate.resolve()
    raise BrowserCapabilityError("Chromium executable is not installed")


def pin_executables(*, chromium_path: Path | None = None) -> tuple[PinnedExecutable, PinnedExecutable]:
    node, cli = discover_playwright_driver()
    chromium = discover_chromium(chromium_path)
    node_pin = PinnedExecutable(
        "playwright-node",
        str(node),
        _sha256_file(node),
        (str(node), str(cli), "run-driver"),
    )
    chromium_pin = PinnedExecutable(
        "chromium",
        str(chromium),
        _sha256_file(chromium),
        (str(chromium), _REQUIRED_CHROMIUM_ARG),
    )
    return node_pin, chromium_pin


def _process_table() -> dict[int, tuple[int, tuple[str, ...], str]]:
    table: dict[int, tuple[int, tuple[str, ...], str]] = {}
    proc = Path("/proc")
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        try:
            raw = (entry / "stat").read_bytes()
            fields = raw.rsplit(b")", 1)[1].split()
            ppid = int(fields[1])
            cmdline = tuple(
                part.decode("utf-8", "surrogateescape")
                for part in (entry / "cmdline").read_bytes().split(b"\0")
                if part
            )
            exe = os.readlink(entry / "exe")
        except (OSError, IndexError, ValueError):
            continue
        table[pid] = (ppid, cmdline, exe)
    return table


def _matching_pids(needles: Sequence[str]) -> set[int]:
    return _retry_vanished_process_census(_matching_pids_once, needles)


def _matching_pids_once(needles: Sequence[str]) -> set[int]:
    """Inventory matching descendants of this validator, never sibling drivers."""
    table = _process_table()
    owner_pid = os.getpid()
    owner_birth = _process_birth(owner_pid)
    found: set[int] = set()
    for pid, (_ppid, cmdline, exe) in table.items():
        text = "\n".join((*cmdline, exe))
        if pid == owner_pid or not any(needle and needle in text for needle in needles):
            continue
        # Shared Playwright argv is only a prefilter. Another validator may
        # run the same pinned executable and must stay outside our cleanup set.
        cursor, seen = pid, set()
        while cursor != owner_pid and cursor in table and cursor not in seen and len(seen) < 128:
            seen.add(cursor)
            cursor = table[cursor][0]
        if cursor != owner_pid:
            continue
        chain = {}
        cursor = pid
        while cursor != owner_pid:
            if cursor in chain or len(chain) >= 128:
                raise BrowserCapabilityError("Browser inventory ancestry is invalid")
            chain[cursor] = _process_birth(cursor)
            cursor = chain[cursor][0]
        if (any(_process_birth(member) != birth for member, birth in chain.items())
                or _process_birth(owner_pid) != owner_birth):
            raise BrowserCapabilityError("Browser inventory ancestry changed during verification")
        found.add(pid)
    if _process_birth(owner_pid) != owner_birth:
        raise BrowserCapabilityError("Browser inventory owner changed during verification")
    return found


def _with_descendants(roots: Iterable[int]) -> set[int]:
    table = _process_table()
    owned = {pid for pid in roots if pid in table}
    changed = True
    while changed:
        changed = False
        for pid, (ppid, _cmdline, _exe) in table.items():
            if ppid in owned and pid not in owned:
                owned.add(pid)
                changed = True
    return owned


def _cmdline_contains(pid: int, token: str) -> bool:
    row = _process_table().get(pid)
    if row is None:
        return False
    return any(token in part for part in row[1])


def forward_browser_headers(headers: Sequence[tuple[str, str]]) -> list[tuple[bytes, bytes]]:
    """Copy browser headers. Added names are a custody failure."""

    forwarded: list[tuple[bytes, bytes]] = []
    for name, value in headers:
        lowered = name.lower().strip()
        if not lowered or lowered in _HOP_BY_HOP:
            continue
        forwarded.append((lowered.encode("latin-1"), value.encode("latin-1")))
    return forwarded


def _header_map(headers: Sequence[tuple[str, str]]) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for name, value in headers:
        mapped[name.lower()] = value
    return mapped


class SyntheticFixture:
    """App-side login, notes, and download state. The bridge does not own this."""

    def __init__(self, directory: Path) -> None:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        self.directory = directory
        self.notes_path = directory / "notes.json"
        self.sessions: set[str] = set()
        self.last_marker = ""
        self.actor_headers: list[str] = []
        self.download_requests: list[dict[str, Any]] = []
        if not self.notes_path.exists():
            self.notes_path.write_text("[]\n", encoding="utf-8")

    def notes(self) -> list[str]:
        payload = json.loads(self.notes_path.read_text(encoding="utf-8"))
        return [str(item) for item in payload]

    def issue(self) -> str:
        token = secrets.token_urlsafe(18)
        self.sessions.add(token)
        return token

    def revoke(self, token: str) -> None:
        self.sessions.discard(token)

    def authenticated(self, cookie_header: str) -> bool:
        return self._token(cookie_header) in self.sessions

    def _token(self, cookie_header: str) -> str:
        for part in cookie_header.split(";"):
            name, separator, value = part.strip().partition("=")
            if separator and name == COOKIE_NAME:
                return value
        return ""


def build_qualification_app(state_dir: Path, mediator: Any | None = None) -> tuple[Any, SyntheticFixture]:
    fixture = SyntheticFixture(state_dir)
    workspace_dir = state_dir / "workspace"
    workspace_dir.mkdir(mode=0o700, exist_ok=True)
    from applications import complaint_workspace as workspace_module

    previous_session = workspace_module._SESSION_DIR
    workspace_module._SESSION_DIR = workspace_dir
    try:
        real_app = SERVER(mediator if mediator is not None else _LocalMediator()).app
    finally:
        workspace_module._SESSION_DIR = previous_session

    async def application(scope: Mapping[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await _reject_non_http(send, scope.get("type"))
            return
        path = str(scope.get("path") or "")
        if path.startswith("/__cimp_gui_02__/"):
            await _fixture_http(fixture, scope, receive, send)
            return
        await real_app(scope, receive, send)

    return application, fixture


async def _reject_non_http(send: Any, scope_type: Any) -> None:
    await send({"type": "http.response.start", "status": 501, "headers": [(b"content-type", b"application/json")]})
    body = json.dumps({"qualified": False, "scope": str(scope_type)}).encode("utf-8")
    await send({"type": "http.response.body", "body": body, "more_body": False})


async def _fixture_http(fixture: SyntheticFixture, scope: Mapping[str, Any], receive: Any, send: Any) -> None:
    method = str(scope.get("method") or "GET").upper()
    path = str(scope.get("path") or "")
    headers = [(name.decode("latin-1"), value.decode("latin-1")) for name, value in scope.get("headers") or []]
    mapped = _header_map(headers)
    fixture.last_marker = mapped.get(MARKER_HEADER, "")
    fixture.actor_headers = [name for name in mapped if name in {"x-actor-id", "x-user-id", "x-role", "x-synthetic-actor"}]
    body = b""
    more = True
    while more:
        message = await receive()
        if message["type"] != "http.request":
            continue
        body += message.get("body") or b""
        more = bool(message.get("more_body"))
    status, response_headers, payload = _fixture_response(fixture, method, path, mapped, body)
    await send({"type": "http.response.start", "status": status, "headers": response_headers})
    await send({"type": "http.response.body", "body": payload, "more_body": False})


def _fixture_response(
    fixture: SyntheticFixture,
    method: str,
    path: str,
    headers: Mapping[str, str],
    body: bytes,
) -> tuple[int, list[tuple[bytes, bytes]], bytes]:
    cookie = headers.get("cookie", "")
    if path == "/__cimp_gui_02__/page" and method == "GET":
        note = fixture.notes()[-1] if fixture.notes() else ""
        page = _page_html(note)
        return 200, [(b"content-type", b"text/html; charset=utf-8")], page.encode("utf-8")
    if path == "/__cimp_gui_02__/login" and method == "POST":
        token = fixture.issue()
        set_cookie = f"{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax"
        payload = json.dumps({"authenticated": True}).encode("utf-8")
        return 200, [(b"content-type", b"application/json"), (b"set-cookie", set_cookie.encode("latin-1"))], payload
    if path == "/__cimp_gui_02__/logout" and method == "POST":
        fixture.revoke(fixture._token(cookie))
        cleared = f"{COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"
        payload = json.dumps({"authenticated": False}).encode("utf-8")
        return 200, [(b"content-type", b"application/json"), (b"set-cookie", cleared.encode("latin-1"))], payload
    if path == "/__cimp_gui_02__/whoami" and method == "GET":
        payload = json.dumps({
            "authenticated": fixture.authenticated(cookie),
            "marker": fixture.last_marker,
            "actor_headers": list(fixture.actor_headers),
        }).encode("utf-8")
        return 200, [(b"content-type", b"application/json")], payload
    if path == "/__cimp_gui_02__/notes" and method == "POST":
        try:
            note = str(json.loads(body.decode("utf-8")).get("note") or "")
        except (UnicodeError, json.JSONDecodeError, AttributeError):
            note = ""
        if not note or len(note) > 200:
            return 400, [(b"content-type", b"application/json")], b'{"stored":false}'
        notes = fixture.notes()
        notes.append(note)
        fixture.notes_path.write_text(json.dumps(notes) + "\n", encoding="utf-8")
        return 200, [(b"content-type", b"application/json")], json.dumps({"stored": True, "note": note}).encode("utf-8")
    if path == "/__cimp_gui_02__/notes" and method == "GET":
        payload = json.dumps({"notes": fixture.notes()}).encode("utf-8")
        return 200, [(b"content-type", b"application/json")], payload
    if path == "/__cimp_gui_02__/download" and method == "GET":
        authorized = fixture.authenticated(cookie)
        fixture.download_requests.append({
            "authenticated": authorized,
            "marker": headers.get(MARKER_HEADER, ""),
            "actor_headers": [name for name in headers if name in {"x-actor-id", "x-user-id", "x-role"}],
        })
        if not authorized:
            return 401, [(b"content-type", b"application/json")], b'{"authorized":false}'
        payload = b"synthetic-download-02\n"
        disposition = b"attachment; filename=\"synthetic-note.txt\""
        return 200, [(b"content-type", b"text/plain; charset=utf-8"), (b"content-disposition", disposition)], payload
    if path == "/__cimp_gui_02__/events":
        return 406, [(b"content-type", b"application/json")], b'{"transport":"sse","qualified":false}'
    if path == "/__cimp_gui_02__/stream":
        return 406, [(b"content-type", b"application/json")], b'{"transport":"streaming","qualified":false}'
    return 404, [(b"content-type", b"application/json")], b'{"missing":true}'


def _page_html(note: str) -> str:
    escaped = html.escape(note)
    return f"""<!doctype html>
<meta charset="utf-8">
<title>cimp-gui-02</title>
<label for="note">Synthetic note</label>
<input id="note" value="">
<button id="save" type="button">Save</button>
<button id="login" type="button">Login</button>
<button id="logout" type="button">Logout</button>
<button id="whoami" type="button">Whoami</button>
<a id="download" href="/__cimp_gui_02__/download" download="synthetic-note.txt">Download</a>
<output id="saved">{escaped}</output>
<pre id="who"></pre>
<pre id="health"></pre>
<pre id="download-meta"></pre>
<script>
const marker = "{MARKER_HEADER}";
async function send(path, method) {{
  document.getElementById("who").textContent = "";
  const response = await fetch(path, {{method, credentials: "include", headers: {{[marker]: "from-browser"}}}});
  document.getElementById("who").textContent = await response.text();
}}
document.getElementById("save").onclick = async () => {{
  const note = document.getElementById("note").value;
  const response = await fetch("/__cimp_gui_02__/notes", {{
    method: "POST", credentials: "include",
    headers: {{"content-type": "application/json", [marker]: "from-browser"}},
    body: JSON.stringify({{note}})
  }});
  const payload = await response.json();
  document.getElementById("saved").textContent = payload.stored ? payload.note : "";
}};
document.getElementById("login").onclick = () => send("/__cimp_gui_02__/login", "POST");
document.getElementById("logout").onclick = () => send("/__cimp_gui_02__/logout", "POST");
document.getElementById("whoami").onclick = () => send("/__cimp_gui_02__/whoami", "GET");
document.getElementById("download").onclick = async (event) => {{
  event.preventDefault();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {{
    const response = await fetch("/__cimp_gui_02__/download", {{
      credentials: "include", headers: {{[marker]: "from-browser"}}, signal: controller.signal
    }});
    if (!response.ok) throw new Error("Download was not authorized");
    const disposition = response.headers.get("content-disposition") || "";
    const match = disposition.match(/filename="([^"]+)"/);
    if (!match) throw new Error("Download filename header is missing");
    const body = await response.blob();
    const url = URL.createObjectURL(body);
    window.__cimpDownloadUrl = url;
    document.getElementById("download-meta").textContent = JSON.stringify({{
      content_type: response.headers.get("content-type"), content_disposition: disposition,
      filename: match[1], status: response.status
    }});
    const link = document.createElement("a");
    link.href = url; link.download = match[1]; document.body.appendChild(link);
    link.click(); link.remove();
  }} finally {{ clearTimeout(timer); }}
}};
fetch("/health", {{credentials: "include", headers: {{[marker]: "from-browser"}}}})
  .then((response) => response.text().then((body) => {{
    document.getElementById("health").textContent = response.status + " " + body;
  }}));
</script>
"""


class SameOriginAsgiBridge:
    """Translate one intercepted browser request into one ASGI call."""

    def __init__(self, application: Any) -> None:
        self.application = application
        self.same_origin_paths: list[str] = []
        self.aborted_external: list[str] = []
        self.aborted_service_workers: list[str] = []
        self.aborted_unqualified: dict[str, list[str]] = {name: [] for name in _UNQUALIFIED_TRANSPORTS}
        self.cookie_headers_seen: list[str] = []
        self.asgi_calls = 0
        self.non_http_scopes: list[str] = []

    def handle(self, request: BrowserHttpRequest) -> BrowserHttpResult:
        parts = urlsplit(request.url)
        origin = f"{parts.scheme}://{parts.netloc}"
        mapped = _header_map(request.headers)
        if request.resource_type == "serviceworker" or parts.path.endswith("/sw.js"):
            self.aborted_service_workers.append(request.url)
            return BrowserHttpResult("abort", reason="service-worker")
        if mapped.get("upgrade", "").lower() == "websocket" or parts.scheme in {"ws", "wss"}:
            self.aborted_unqualified["websocket"].append(request.url)
            return BrowserHttpResult("abort", reason="websocket-unqualified")
        if "text/event-stream" in mapped.get("accept", ""):
            self.aborted_unqualified["sse"].append(request.url)
            return BrowserHttpResult("abort", reason="sse-unqualified")
        if parts.path.endswith("/stream"):
            self.aborted_unqualified["streaming"].append(request.url)
            return BrowserHttpResult("abort", reason="streaming-unqualified")
        if origin != SAME_ORIGIN:
            self.aborted_external.append(request.url)
            return BrowserHttpResult("abort", reason="external-origin")
        self.cookie_headers_seen.append(mapped.get("cookie", ""))
        status, headers, body = self._invoke(request, parts)
        self.same_origin_paths.append(parts.path)
        return BrowserHttpResult("fulfill", status=status, headers=headers, body=body)

    def _invoke(self, request: BrowserHttpRequest, parts: Any) -> tuple[int, list[tuple[str, str]], bytes]:
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": request.method.upper(),
            "scheme": parts.scheme,
            "path": parts.path or "/",
            "raw_path": (parts.path or "/").encode("ascii"),
            "query_string": parts.query.encode("ascii"),
            "headers": forward_browser_headers(request.headers),
            "client": ("browser", 0),
            "server": (parts.hostname or "127.0.0.1", parts.port or 80),
        }
        result: dict[str, Any] = {"status": 500, "headers": [], "body": b""}

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": request.body, "more_body": False}

        async def send(message: Mapping[str, Any]) -> None:
            if message["type"] == "http.response.start":
                result["status"] = int(message["status"])
                result["headers"] = [
                    (name.decode("latin-1"), value.decode("latin-1"))
                    for name, value in message.get("headers") or []
                ]
            elif message["type"] == "http.response.body":
                result["body"] += message.get("body") or b""
                if message.get("more_body"):
                    self.aborted_unqualified["streaming"].append(request.url)

        async def runner() -> None:
            self.asgi_calls += 1
            await self.application(scope, receive, send)

        active: dict[str, Any] = {}

        def invoke() -> None:
            async def bounded() -> None:
                active["loop"] = asyncio.get_running_loop()
                active["task"] = asyncio.current_task()
                await asyncio.wait_for(runner(), timeout=_ASGI_REQUEST_SECONDS)
            asyncio.run(bounded())

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            invoke()
        else:
            # Sync Playwright executes route callbacks on its own running
            # loop. Keep the actual ASGI application on an independent loop;
            # its request scope, headers and server state are unchanged.
            errors: list[BaseException] = []

            def run_owned_loop() -> None:
                try:
                    invoke()
                except BaseException as exc:
                    errors.append(exc)

            worker = threading.Thread(target=run_owned_loop, name="gui-asgi-request", daemon=True)
            worker.start()
            worker.join(timeout=_ASGI_THREAD_JOIN_SECONDS)
            if worker.is_alive():
                loop, task = active.get("loop"), active.get("task")
                if loop is not None and task is not None:
                    try:
                        loop.call_soon_threadsafe(task.cancel)
                    except RuntimeError:
                        pass  # The owned loop may have closed during the join.
                worker.join(timeout=1)
                raise BrowserCapabilityError("ASGI bridge request exceeded its bounded deadline")
            if errors:
                raise errors[0]
        return int(result["status"]), list(result["headers"]), bytes(result["body"])


class _LocalMediator:
    def io(self, _message: str) -> str:
        return ""


def _load_sync_playwright() -> Any:
    repo_root = Path(__file__).resolve().parents[1]
    saved_path = sys.path[:]
    try:
        sys.path = [entry for entry in sys.path if Path(entry or os.getcwd()).resolve() != repo_root]
        for name in list(sys.modules):
            if name == "playwright" or name.startswith("playwright."):
                module = sys.modules[name]
                module_file = str(getattr(module, "__file__", "") or "")
                if not module_file or module_file.startswith(str(repo_root)):
                    sys.modules.pop(name, None)
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError as exc:
        raise BrowserCapabilityError("Playwright Node driver is not installed") from exc
    finally:
        sys.path[:] = saved_path


def _numeric_pid_absent(pid: int) -> bool:
    """Unknown, inaccessible, live, reused and zombie PIDs are never absence."""
    if type(pid) is not int or pid <= 0:
        return False
    try:
        (Path('/proc') / str(pid)).lstat()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return False


def _vanished_proc_metadata(pid: int, path: Path, error: BaseException) -> bool:
    """Recognize only disappearance at an actual known proc read site."""
    if (type(pid) is not int or pid <= 0
            or not isinstance(error, (FileNotFoundError, ProcessLookupError))
            or error.errno not in {errno.ENOENT, errno.ESRCH}
            or path not in {Path('/proc') / str(pid) / leaf for leaf in ('stat', 'status', 'exe')}):
        return False
    # A descriptor read may lack filename; it is still bound to this known
    # proc operation. An unrelated named failure cannot borrow that binding.
    if error.filename is not None:
        try:
            if os.fsdecode(error.filename) != str(path):
                return False
        except TypeError:
            return False
    return _numeric_pid_absent(pid)


def _process_birth(pid: int) -> tuple[int, int, tuple[int, ...], str]:
    """Read the kernel identity used to join an observed browser to its driver."""
    metadata_path = Path('/proc')
    try:
        proc = Path("/proc") / str(pid)
        metadata_path = proc / 'stat'
        fields = metadata_path.read_bytes().rsplit(b")", 1)[1].split()
        ppid, birth = int(fields[1]), int(fields[19])
        metadata_path = proc / 'status'
        rows = metadata_path.read_text().splitlines()
        uid = tuple(map(int, next(row for row in rows if row.startswith("Uid:")).split()[1:]))
        metadata_path = proc / 'exe'
        exe = os.readlink(metadata_path)
        if birth <= 0 or uid != (os.getuid(),) * 4:
            raise ValueError("foreign or missing process identity")
        return ppid, birth, uid, exe
    except (OSError, ValueError, IndexError, StopIteration) as exc:
        if _vanished_proc_metadata(pid, metadata_path, exc):
            raise _VanishedBrowserProcess(pid) from exc
        raise BrowserCapabilityError("Browser process identity could not be verified") from exc


def _pinned_process(pid: int, pin: PinnedExecutable) -> tuple[int, int, tuple[int, ...], str]:
    before = _process_birth(pid)
    if before[3] != pin.path:
        raise BrowserCapabilityError("Browser executable does not match the pin")
    metadata_path = Path('/proc') / str(pid) / 'exe'
    try:
        digest = _sha256_file(metadata_path)
    except OSError as exc:
        if _vanished_proc_metadata(pid, metadata_path, exc):
            raise _VanishedBrowserProcess(pid) from exc
        raise BrowserCapabilityError("Browser executable identity could not be verified") from exc
    if digest != pin.sha256:
        raise BrowserCapabilityError("Browser executable does not match the pin")
    if _process_birth(pid) != before:
        raise BrowserCapabilityError("Browser process birth changed during verification")
    return before


def _chromium_title_argv(argv: tuple[str, ...], chromium: PinnedExecutable, profile: Path) -> tuple[str, ...]:
    """Tokenize Chromium's Linux title only after its kernel identity is proved."""
    if not argv or any("\0" in part for part in argv) or sum(len(part) for part in argv) > 65536:
        raise BrowserCapabilityError("Chromium process arguments are invalid")
    if len(argv) == 1 and argv[0] != chromium.path:
        try:
            argv = tuple(shlex.split(argv[0], posix=True))
        except ValueError as exc:
            raise BrowserCapabilityError("Chromium process title is malformed") from exc
    if not argv or argv[0] != chromium.path:
        raise BrowserCapabilityError("Chromium executable does not match the pin")
    if any(token in part for part in argv for token in _FORBIDDEN_ARGV_TOKENS):
        raise BrowserCapabilityError("Chromium opened a TCP debugging port")
    profile_arg = "--user-data-dir=" + str(profile)
    if argv.count(profile_arg) != 1 or sum(part.startswith("--user-data-dir") for part in argv) != 1:
        raise BrowserCapabilityError("Chromium profile does not match the owned profile")
    if argv.count(_REQUIRED_CHROMIUM_ARG) != 1 or any(
        part.startswith(_REQUIRED_CHROMIUM_ARG) and part != _REQUIRED_CHROMIUM_ARG for part in argv
    ):
        raise BrowserCapabilityError("Chromium is not using the CDP pipe")
    return argv


def _chromium_process_argv(argv: tuple[str, ...], chromium: PinnedExecutable) -> tuple[str, ...]:
    """Tokenize only after the caller has proved the actual executable."""
    if (not argv or any(type(part) is not str or "\0" in part for part in argv)
            or sum(len(part) for part in argv) > 65536):
        raise BrowserCapabilityError("Chromium process arguments are invalid")
    if len(argv) == 1 and argv[0] != chromium.path:
        try:
            argv = tuple(shlex.split(argv[0], posix=True))
        except ValueError as exc:
            raise BrowserCapabilityError("Chromium process title is malformed") from exc
    if not argv or argv[0] != chromium.path:
        raise BrowserCapabilityError("Chromium executable does not match the pin")
    return argv


def _chromium_role_argv(argv: tuple[str, ...], chromium: PinnedExecutable, profile: Path) -> tuple[str, tuple[str, ...]]:
    """Classify a kernel-pinned process; this never proves browser custody."""
    argv = _chromium_process_argv(argv, chromium)
    if any(token in part for part in argv for token in _FORBIDDEN_ARGV_TOKENS):
        raise BrowserCapabilityError("Chromium opened a TCP debugging port")
    profiles = [part for part in argv if part.startswith("--user-data-dir")]
    if profiles and profiles != ["--user-data-dir=" + str(profile)]:
        raise BrowserCapabilityError("Chromium profile does not match the owned profile")
    pipe_flags = [part for part in argv if part.startswith(_REQUIRED_CHROMIUM_ARG)]
    if pipe_flags not in ([], [_REQUIRED_CHROMIUM_ARG]):
        raise BrowserCapabilityError("Chromium CDP pipe arguments are invalid")
    roles = [part for part in argv if part.startswith("--type")]
    if not roles:
        return "browser", argv
    if len(roles) != 1 or roles[0] not in {
        "--type=zygote", "--type=renderer", "--type=gpu-process", "--type=utility",
    }:
        raise BrowserCapabilityError("Chromium child role is unqualified")
    return roles[0].split("=", 1)[1], argv


def _assert_process_custody(node: PinnedExecutable, chromium: PinnedExecutable, profile: Path) -> None:
    return _retry_vanished_process_census(_assert_process_custody_once, node, chromium, profile)


def _retry_vanished_process_census(proof, *arguments):
    """Rebuild the complete proof at most three times for proved PID exit races."""
    for attempt in range(3):
        try:
            return proof(*arguments)
        except _VanishedBrowserProcess as exc:
            # Recheck immediately before restarting: reappearance or unknown
            # numeric PID state never permits a retry or reuse of partial proof.
            if attempt == 2 or not _numeric_pid_absent(exc.pid):
                raise


def _assert_process_custody_once(node: PinnedExecutable, chromium: PinnedExecutable, profile: Path) -> None:
    table = _process_table()
    owner_pid = os.getpid()
    owner_birth = _process_birth(owner_pid)
    node_births = {}
    node_chains = {}
    for pid, (_ppid, argv, _exe) in table.items():
        if node.path not in argv or node.argv[1] not in argv or "run-driver" not in argv:
            continue
        # Other validators may use the same executable concurrently. They
        # are not ours to inspect or authorize, including after they exit.
        cursor, seen = pid, set()
        while cursor != owner_pid and cursor in table and cursor not in seen and len(seen) < 128:
            seen.add(cursor)
            cursor = table[cursor][0]
        if cursor != owner_pid:
            continue
        if tuple(argv) != node.argv:
            raise BrowserCapabilityError("Playwright driver arguments do not match the pin")
        birth = _pinned_process(pid, node)
        chain = {pid: birth}
        parent = birth[0]
        while parent != owner_pid and parent not in chain and len(chain) < 128:
            chain[parent] = _process_birth(parent)
            parent = chain[parent][0]
        if parent != owner_pid:
            raise BrowserCapabilityError("Pinned Node is not owned by this validator")
        node_births[pid], node_chains[pid] = birth, chain
    records = {}

    def joined(pid, argv):
        birth = _pinned_process(pid, chromium)
        # Only current kernel edges join a Chromium process to our actual
        # driver. A process title and a reused PID cannot supply that proof.
        chain = {pid: birth}
        parent = birth[0]
        while parent not in node_births and parent not in chain and len(chain) < 128:
            chain[parent] = _process_birth(parent)
            parent = chain[parent][0]
        if parent not in node_births:
            raise BrowserCapabilityError("Chromium is not owned by the pinned Node driver")
        role, normalized = _chromium_role_argv(argv, chromium, profile)
        return {"birth": birth, "chain": chain, "node": parent,
                "role": role, "argv": argv, "normalized": normalized}

    # Locate the selected profile's unique browser root. Other disjoint
    # contexts under this validator's Node are outside this profile's claim.
    for pid, (_ppid, argv, _exe) in table.items():
        if str(profile) not in "\n".join(argv):
            continue
        _pinned_process(pid, chromium)
        normalized = _chromium_process_argv(argv, chromium)
        profiles = [part for part in normalized if part.startswith("--user-data-dir")]
        if (len(profiles) == 1 and profiles[0].startswith("--user-data-dir=")
                and profiles[0] != "--user-data-dir=" + str(profile)):
            continue  # A distinct well-formed profile is not this root claim.
        if profiles:
            records[pid] = joined(pid, argv)
    roots = [pid for pid, row in records.items() if row["role"] == "browser"]
    if not node_births or len(roots) != 1:
        raise BrowserCapabilityError("Pinned Node or unique Chromium browser was not observed")
    root = roots[0]
    root_record = records[root]
    # Preserve the original root contract, including its unique profile,
    # exact CDP pipe and TCP refusal. Child classification cannot satisfy it.
    _chromium_title_argv(root_record["argv"], chromium, profile)

    # Inspect every pinned Chromium descendant of the proved root, including
    # children that omit the profile flag or supply a different one. The table
    # is only a negative prefilter; actual births rederive every admitted edge.
    for pid, (_ppid, argv, _exe) in table.items():
        if pid == root:
            continue
        cursor, seen = pid, set()
        while cursor in table and cursor not in seen and cursor != root and len(seen) < 128:
            seen.add(cursor)
            cursor = table[cursor][0]
        if cursor != root or _exe != chromium.path:
            continue
        birth = _process_birth(pid)
        if birth[3] != chromium.path:
            continue  # Non-browser helpers confer no Chromium custody.
        if pid not in records:
            records[pid] = joined(pid, argv)

    for pid, row in records.items():
        if pid != root:
            if (row["role"] == "browser" or root not in row["chain"]
                    or row["chain"][root] != root_record["birth"]
                    or row["node"] != root_record["node"]):
                raise BrowserCapabilityError("Chromium child is not owned through the pinned browser root")
        chain = {**row["chain"], **node_chains[row["node"]], owner_pid: owner_birth}
        if any(_process_birth(member) != identity for member, identity in chain.items()):
            raise BrowserCapabilityError("Browser ancestry changed during verification")


def await_owned_browser_cleanup(pids: set[int], *, deadline_seconds: float = OWNED_BROWSER_CLEANUP_SECONDS) -> dict[str, Any]:
    """Wait for already-closed owned browser descendants. Do not signal them.

    The deadline is the existing five-second cleanup ceiling. A non-positive,
    non-finite, or longer deadline is rejected. Processes that are still alive
    stay alive; this wait never becomes a kill or a second launch.
    """

    if (isinstance(deadline_seconds, bool) or type(deadline_seconds) not in (int, float)
            or not math.isfinite(deadline_seconds) or deadline_seconds <= 0
            or deadline_seconds > OWNED_BROWSER_CLEANUP_SECONDS):
        raise BrowserCapabilityError("browser_cleanup_deadline_unbounded")
    started = time.monotonic()
    if (type(pids) is not set or len(pids) > 4096
            or any(type(pid) is not int or pid <= 0 for pid in pids)):
        raise BrowserCapabilityError("browser_cleanup_pids_invalid")
    remaining = set(pids)
    while remaining and time.monotonic() - started < deadline_seconds:
        live = set(_process_table())
        remaining &= live
        if remaining:
            time.sleep(0.05)
    return {
        "owned_count": len(pids),
        "remaining_pids": sorted(remaining),
        "cleaned": not remaining,
        "elapsed_seconds": round(time.monotonic() - started, 4),
        "deadline_seconds": float(deadline_seconds),
        "signaled": False,
    }


def _wait_for_cleanup(pids: set[int]) -> dict[str, Any]:
    started = time.monotonic()
    remaining = set(pids)
    while remaining and time.monotonic() - started < 5:
        live = set(_process_table())
        remaining &= live
        if remaining:
            time.sleep(0.05)
    return {
        "owned_count": len(pids),
        "remaining_pids": sorted(remaining),
        "cleaned": not remaining,
        "elapsed_seconds": round(time.monotonic() - started, 4),
    }


def _browser_header_pairs(request: Any) -> list[tuple[str, str]]:
    array = getattr(request, "headers_array", None)
    if callable(array):
        return [(str(item["name"]), str(item["value"])) for item in array()]
    return [(str(name), str(value)) for name, value in request.headers.items()]


def _fulfill(route: Any, result: BrowserHttpResult) -> None:
    if result.action != "fulfill":
        route.abort("blockedbyclient")
        return
    headers = {name: value for name, value in result.headers}
    content_type = headers.pop("content-type", None)
    route.fulfill(status=result.status, headers=headers, body=result.body, content_type=content_type)


def qualify_native_browser(profile_root: Path, *, chromium_path: Path | None = None) -> QualificationReport:
    """Launch pinned Playwright Node and Chromium and exercise the ASGI bridge."""

    before_network = probe_inherited_network_denial()
    node, chromium = pin_executables(chromium_path=chromium_path)
    profile_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(profile_root, 0o700)
    profile_a = profile_root / "context-a"
    profile_b = profile_root / "context-b"
    for profile in (profile_a, profile_b):
        profile.mkdir(mode=0o700, exist_ok=True)
        os.chmod(profile, 0o700)
    application, fixture = build_qualification_app(profile_root / "app-state")
    bridge = SameOriginAsgiBridge(application)
    sync_playwright = _load_sync_playwright()
    previous_node = os.environ.get("PLAYWRIGHT_NODEJS_PATH")
    os.environ["PLAYWRIGHT_NODEJS_PATH"] = node.path
    playwright = None
    observed: set[int] = set()
    try:
        playwright = sync_playwright().start()
        context_a = _launch_context(playwright, chromium.path, profile_a, bridge)
        _assert_process_custody(node, chromium, profile_a)
        observed |= _with_descendants(_matching_pids((node.argv[1], str(profile_a), str(profile_b))))
        page = context_a.pages[0] if context_a.pages else context_a.new_page()
        page_result = _exercise_page(page, fixture, bridge)
        context_b = _launch_context(playwright, chromium.path, profile_b, bridge)
        observed |= _with_descendants(_matching_pids((str(profile_b),)))
        other = context_b.pages[0] if context_b.pages else context_b.new_page()
        isolated = _other_context_is_anonymous(other)
        during_network = probe_inherited_network_denial()
        child_seccomp = _child_seccomp(observed)
        context_a.close()
        context_b.close()
    finally:
        if playwright is not None:
            playwright.stop()
        if previous_node is None:
            os.environ.pop("PLAYWRIGHT_NODEJS_PATH", None)
        else:
            os.environ["PLAYWRIGHT_NODEJS_PATH"] = previous_node
    cleanup = _wait_for_cleanup(observed)
    after_network = probe_inherited_network_denial()
    unchanged = before_network == during_network == after_network and _seccomp_matches(before_network, child_seccomp)
    if not before_network["af_unix_only"] or not unchanged:
        raise BrowserCapabilityError("Inherited AF_UNIX-only network denial changed or is absent")
    if not cleanup["cleaned"]:
        raise BrowserCapabilityError("Owned browser descendants are still running")
    download_path = profile_root / "download" / "synthetic-note.txt"
    from playwright._repo_version import version as playwright_version
    report = QualificationReport(
        node=node,
        chromium=chromium,
        playwright_version=playwright_version,
        private_profiles=(str(profile_a), str(profile_b)),
        pipe_transport=True,
        network_denial={"before": before_network, "after": after_network, "unchanged": unchanged, "af_unix_only": True},
        same_origin_paths=list(bridge.same_origin_paths),
        aborted_external=list(bridge.aborted_external),
        aborted_service_workers=list(bridge.aborted_service_workers),
        aborted_unqualified={key: list(value) for key, value in bridge.aborted_unqualified.items()},
        unsupported_transport_outcomes=dict(page_result["unqualified_probe"]),
        header_marker=fixture.last_marker,
        injected_actor_header=bool(fixture.actor_headers),
        cookie_replayed_by_bridge=bool(page_result["cookie_replayed_by_bridge"]),
        login_logout=_login_report(page_result),
        cross_context_isolated=isolated,
        persisted_note=fixture.notes()[-1] if fixture.notes() else "",
        download={"path": str(download_path), "bytes": download_path.read_bytes() if download_path.is_file() else b"",
            "sha256": _sha256_file(download_path), **page_result["download_metadata"],
            "revoked_status": page_result["revoked_download_status"],
            "cookie_scope_verified": bool(any(item["authenticated"] and item["marker"] == "from-browser"
                and not item["actor_headers"] for item in fixture.download_requests)
                and len([item for item in fixture.download_requests if not item["authenticated"]]) >= 2)},
        download_transport="same_origin_fetch_blob",
        direct_attachment_navigation_qualified=False,
        health_status=page_result["health_status"],
        child_cleanup=cleanup,
        qualified_transports={
            "http": True,
            "cookies": True,
            "headers": True,
            "downloads": download_path.is_file(),
            "websocket": False,
            "sse": False,
            "streaming": False,
        },
        limitations=(
            "WebSocket transport is aborted and unqualified.",
            "Server-sent events (SSE) are aborted and unqualified.",
            "Response streaming is aborted and unqualified.",
            "Login uses the app-side synthetic fixture, not a product session.",
            "Only installed headless-shell Chromium is qualified by this run.",
            "Downloads use same-origin ASGI fetch followed by a native browser Blob URL download; direct attachment navigation is unqualified.",
        ),
    )
    _validate_report(report, fixture)
    return report


def _seccomp_matches(parent: Mapping[str, Any], children: Sequence[Mapping[str, str]]) -> bool:
    """Chromium may add sandbox filters. It must not drop the inherited ones."""

    if not children:
        return False
    parent_status = parent.get("seccomp") or {}
    try:
        parent_mode = int(parent_status.get("Seccomp") or 0)
        parent_filters = int(parent_status.get("Seccomp_filters") or 0)
    except ValueError:
        return False
    for child in children:
        try:
            mode = int(child.get("Seccomp") or 0)
            filters = int(child.get("Seccomp_filters") or 0)
        except ValueError:
            return False
        if mode < parent_mode or filters < parent_filters:
            return False
    return True


def _child_seccomp(pids: Iterable[int]) -> list[dict[str, str]]:
    found = []
    live = _process_table()
    for pid in pids:
        if pid in live:
            found.append(_seccomp_status(pid))
    return found


def bridge_replays_cookie(bridge: SameOriginAsgiBridge) -> bool:
    """A second request without a Cookie header must not become authenticated."""

    result = bridge.handle(BrowserHttpRequest(
        "GET",
        f"{SAME_ORIGIN}/__cimp_gui_02__/whoami",
        headers=[(MARKER_HEADER, "from-browser")],
    ))
    if result.action != "fulfill":
        return True
    payload = json.loads(result.body.decode("utf-8"))
    return bool(payload.get("authenticated"))


def _launch_context(playwright: Any, chromium: str, profile: Path, bridge: SameOriginAsgiBridge) -> Any:
    context = playwright.chromium.launch_persistent_context(
        str(profile),
        executable_path=chromium,
        headless=True,
        accept_downloads=True,
        service_workers="block",
        args=[
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-sync",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-component-update",
            "--no-sandbox",
            "--disable-breakpad",
            "--disable-crash-reporter",
        ],
    )

    def intercept(route: Any) -> None:
        request = route.request
        body = b""
        buffer = getattr(request, "post_data_buffer", None)
        if buffer:
            body = bytes(buffer)
        try:
            result = bridge.handle(BrowserHttpRequest(
                method=request.method,
                url=request.url,
                headers=_browser_header_pairs(request),
                body=body,
                resource_type=str(getattr(request, "resource_type", "") or ""),
            ))
            _fulfill(route, result)
        except BaseException:
            # A raised ASGI error must fail the validator and settle the real
            # intercepted request. Leaving it open can strand browser fetch.
            try:
                route.abort("failed")
            except Exception:
                pass  # Preserve the original error if the route already closed.
            raise

    context.route("**/*", intercept)
    websocket = getattr(context, "route_web_socket", None)
    if callable(websocket):
        async def block_socket(server: Any) -> None:
            bridge.aborted_unqualified["websocket"].append(str(getattr(server, "url", "")))
            # Installed Playwright awaits async WebSocket handlers, while
            # invoking its sync close wrapper here blocks its dispatcher.
            # Adapt the same real route handle to its public async API.
            from playwright.async_api import WebSocketRoute
            handle = getattr(server, "_impl_obj", None)
            if handle is None:
                raise BrowserCapabilityError("Installed WebSocket route cannot be adapted to async close")
            await asyncio.wait_for(
                WebSocketRoute(handle).close(code=1008, reason="WebSocket transport is unqualified"),
                timeout=5,
            )
        websocket("**/*", block_socket)
    return context


def _exercise_page(page: Any, fixture: SyntheticFixture, bridge: SameOriginAsgiBridge) -> dict[str, Any]:
    page.goto(f"{SAME_ORIGIN}/__cimp_gui_02__/page", wait_until="domcontentloaded")
    page.fill("#note", "synthetic-note-02")
    page.click("#save")
    page.wait_for_function("document.getElementById('saved').textContent === 'synthetic-note-02'")
    page.reload(wait_until="domcontentloaded")
    if page.text_content("#saved") != "synthetic-note-02":
        raise BrowserCapabilityError("Reloaded DOM did not show the persisted note")
    page.click("#login")
    page.wait_for_function("document.getElementById('who').textContent.includes('authenticated')")
    who_after_login = json.loads(page.text_content("#who") or "{}")
    page.click("#whoami")
    page.wait_for_function("() => { const node = document.getElementById('who'); return node.textContent.includes('marker'); }")
    whoami = json.loads(page.text_content("#who") or "{}")
    replayed = bridge_replays_cookie(bridge)
    visible_cookie = page.evaluate("document.cookie")
    streamed = page.evaluate(
        """async (origin) => {
            const bounded = async (operation, label) => {
              let timer;
              try {
                return await Promise.race([
                  operation,
                  new Promise((resolve, reject) => {
                    timer = setTimeout(() => reject(new Error(label + ' probe deadline exceeded')), 8000);
                  }),
                ]);
              } finally { clearTimeout(timer); }
            };
            const once = (executor) => new Promise((resolve) => {
              let settled = false;
              const finish = (value) => { if (!settled) { settled = true; resolve(value); } };
              executor(finish);
            });
            const events = await bounded(once((finish) => {
              const source = new EventSource(origin + '/__cimp_gui_02__/events');
              source.onerror = () => { source.close(); finish('sse-error'); };
              source.onopen = () => { source.close(); finish('sse-open'); };
            }), 'SSE');
            const socketResult = await bounded(once((finish) => {
              const socket = new WebSocket(origin.replace('http://', 'ws://') + '/__cimp_gui_02__/socket');
              socket.onopen = () => { socket.close(); finish('websocket-open'); };
              socket.onerror = () => { finish('websocket-error'); };
              socket.onclose = () => { finish('websocket-closed'); };
            }), 'WebSocket');
            const streamResult = await bounded(
              fetch(origin + '/__cimp_gui_02__/stream').then(() => 'stream-open', () => 'stream-error'),
              'streaming',
            );
            return {events, socketResult, streamResult};
        }""",
        SAME_ORIGIN,
    )
    page.click("#logout")
    page.wait_for_function("document.getElementById('who').textContent.includes('false')")
    page.click("#whoami")
    page.wait_for_function("() => { const payload = JSON.parse(document.getElementById('who').textContent || '{}'); return payload.authenticated === false; }")
    who_after_logout = json.loads(page.text_content("#who") or "{}")
    page.wait_for_function("() => document.getElementById('health').textContent.startsWith('200')")
    health_text = page.text_content("#health") or ""
    health_status = int(health_text.split(" ", 1)[0]) if health_text[:3].isdigit() else 0
    external = page.evaluate(
        """async (url) => {
            const controller = new AbortController();
            let expired = false;
            const timer = setTimeout(() => { expired = true; controller.abort(); }, 8000);
            try { await fetch(url, {signal: controller.signal}); return 'allowed'; }
            catch (error) {
              if (expired) throw new Error('External-origin probe deadline exceeded');
              return 'aborted';
            } finally { clearTimeout(timer); }
        }""",
        f"{EXTERNAL_NAME}/secret",
    )
    worker = page.evaluate(
        """async () => {
            const controller = new AbortController();
            let expired = false;
            const timer = setTimeout(() => { expired = true; controller.abort(); }, 8000);
            try { await fetch('/sw.js', {signal: controller.signal}); return 'fetched'; }
            catch (error) {
              if (expired) throw new Error('Service-worker probe deadline exceeded');
              return 'blocked';
            } finally { clearTimeout(timer); }
        }"""
    )
    download_dir = fixture.directory.parent / "download"
    download_dir.mkdir(mode=0o700, exist_ok=True)
    page.click("#login")
    page.wait_for_function("JSON.parse(document.getElementById('who').textContent || '{}').authenticated === true")
    with page.expect_download() as download_info:
        page.click("#download")
    download = download_info.value
    target = download_dir / "synthetic-note.txt"
    download.save_as(str(target))
    download_metadata = json.loads(page.text_content("#download-meta") or "{}")
    download_metadata["suggested_filename"] = download.suggested_filename
    page.evaluate("URL.revokeObjectURL(window.__cimpDownloadUrl); delete window.__cimpDownloadUrl")
    page.click("#logout")
    page.wait_for_function("JSON.parse(document.getElementById('who').textContent || '{}').authenticated === false")
    revoked = page.evaluate(
        """async () => {
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), 8000);
            try {
              const response = await fetch('/__cimp_gui_02__/download', {
                credentials: 'include', headers: {'x-cimp-gui-marker': 'from-browser'}, signal: controller.signal
              });
              return {status: response.status, body: await response.text()};
            } finally { clearTimeout(timer); }
        }"""
    )
    if revoked["status"] != 401 or "synthetic-download-02" in revoked["body"]:
        raise BrowserCapabilityError("Revoked browser session could still download")
    # Keep A authenticated while the independent B context is checked, so
    # cookie isolation cannot pass merely because every token was revoked.
    page.click("#login")
    page.wait_for_function("JSON.parse(document.getElementById('who').textContent || '{}').authenticated === true")
    result = {
        "who_after_login": who_after_login,
        "whoami": whoami,
        "visible_cookie": visible_cookie,
        "who_after_logout": who_after_logout,
        "health_status": health_status,
        "external": external,
        "worker": worker,
        "download_bytes": target.read_bytes(),
        "download_metadata": download_metadata,
        "revoked_download_status": revoked["status"],
        "cookie_replayed_by_bridge": replayed,
        "unqualified_probe": streamed,
    }
    if external != "aborted" or worker != "blocked":
        raise BrowserCapabilityError("External origin or service worker was not denied")
    probe = result["unqualified_probe"]
    if probe["events"] == "sse-open" or probe["socketResult"] == "websocket-open" or probe["streamResult"] == "stream-open":
        raise BrowserCapabilityError("An unqualified transport was served")
    if bridge.non_http_scopes:
        raise BrowserCapabilityError("Non-HTTP ASGI scopes were dispatched")
    return result


def _login_report(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "login_authenticated": bool(result.get("who_after_login", {}).get("authenticated")),
        "whoami_authenticated": bool(result.get("whoami", {}).get("authenticated")),
        "marker": result.get("whoami", {}).get("marker"),
        "http_only_hidden": COOKIE_NAME not in str(result.get("visible_cookie") or ""),
        "logout_authenticated": bool(result.get("who_after_logout", {}).get("authenticated")),
        "actor_headers": list(result.get("whoami", {}).get("actor_headers") or []),
    }


def _other_context_is_anonymous(page: Any) -> bool:
    page.goto(f"{SAME_ORIGIN}/__cimp_gui_02__/page", wait_until="domcontentloaded")
    page.click("#whoami")
    page.wait_for_function("document.getElementById('who').textContent.includes('authenticated')")
    payload = json.loads(page.text_content("#who") or "{}")
    download_status = page.evaluate(
        """async () => {
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), 8000);
            try { return (await fetch('/__cimp_gui_02__/download', {
              credentials: 'include', headers: {'x-cimp-gui-marker': 'from-browser'}, signal: controller.signal
            })).status; } finally { clearTimeout(timer); }
        }"""
    )
    return payload.get("authenticated") is False and download_status == 401


def _validate_report(report: QualificationReport, fixture: SyntheticFixture) -> None:
    if report.persisted_note != "synthetic-note-02":
        raise BrowserCapabilityError("Persisted note did not match the DOM submission")
    if report.header_marker != "from-browser" or report.injected_actor_header:
        raise BrowserCapabilityError("Browser marker was not forwarded without actor injection")
    login = report.login_logout
    if not login["login_authenticated"] or not login["whoami_authenticated"] or login["logout_authenticated"]:
        raise BrowserCapabilityError("Browser login or logout cookie was not honored by the app")
    if not login["http_only_hidden"] or login["marker"] != "from-browser" or login["actor_headers"]:
        raise BrowserCapabilityError("Cookie or header fidelity failed")
    if not report.cross_context_isolated:
        raise BrowserCapabilityError("Cookie jar leaked across browser contexts")
    if report.download["bytes"] != b"synthetic-download-02\n":
        raise BrowserCapabilityError("Download bytes were not forwarded")
    if report.health_status != 200 or "/health" not in report.same_origin_paths:
        raise BrowserCapabilityError("Same-origin navigation did not reach the actual ASGI app")
    if not report.aborted_external or not report.aborted_service_workers:
        raise BrowserCapabilityError("External origin or service worker was not aborted")
    if report.cookie_replayed_by_bridge:
        raise BrowserCapabilityError("The bridge replayed a cookie the browser did not send")
    if any(report.qualified_transports[name] for name in _UNQUALIFIED_TRANSPORTS):
        raise BrowserCapabilityError("HTTP interception claimed unsupported transport coverage")
    if fixture.actor_headers:
        raise BrowserCapabilityError("Synthetic actor authority was injected")
