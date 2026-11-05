#!/usr/bin/env python3
"""Focused current-source UX acceptance.

Task CIMP-UX-68 runs one in-process controller group while that task is still
pending. The declared final-matrix selectors and the production Native
completion verifier stay outside this 900-second validation. They run only
after a genuine callback. Saved JSON and caller booleans are not authority.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import html.parser
import json
import os
import stat
import sys
import weakref
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from integrations.private_storage import (
    ENVELOPE_MAGIC,
    PrivateArtifactBinding,
    PrivateArtifactIntegrityError,
    open_private_artifact,
    seal_private_artifact,
)
from tests.gui_native_browser import (
    SAME_ORIGIN,
    BrowserHttpRequest,
    SameOriginAsgiBridge,
    probe_inherited_network_denial,
)


SCHEMA = "complaint-ux-current-source-groups@1"
TASK_ID = "CIMP-UX-68"
FOCUSED_GROUP = "controller_focus"
CONTRACT_RELATIVE = "docs/task_boards/complaint_gui_ux_overhaul_completion_contract.json"
EXPERIENCE_RELATIVE = "docs/ux/complaint_ux_overhaul/experience_contract.md"
MANIFEST_RELATIVE = "docs/ux/complaint_ux_overhaul/baseline/screenshot_manifest.json"
REVIEW_RELATIVE = "docs/ux/complaint_ux_overhaul/before_after_review.md"
STALE_HEADER = "No case selected"
NATIVE_VERIFIER = "integrations.ipfs_accelerate.campaign_completion.verify_campaign_completion"
_SOURCE_FILES = (
    EXPERIENCE_RELATIVE,
    MANIFEST_RELATIVE,
    REVIEW_RELATIVE,
    CONTRACT_RELATIVE,
)
_PLAINTEXT = b"synthetic-cimp-ux-68-note"
_KEY = bytes(range(32))
_KEY_ID = "synthetic-cimp-ux-68-key"


class CurrentAcceptanceError(ValueError):
    """The focused controller refused a result that is not current evidence."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _freeze_group(spec: Mapping[str, Any]) -> Mapping[str, Any]:
    selectors = tuple(spec["selectors"])
    if not selectors or len(selectors) != len(set(selectors)):
        raise CurrentAcceptanceError("empty_or_duplicate_selectors")
    if int(spec["minimum_cases"]) != len(selectors) or int(spec["timeout_seconds"]) <= 0:
        raise CurrentAcceptanceError("empty_or_duplicate_selectors")
    if int(spec["timeout_seconds"]) > 900:
        raise CurrentAcceptanceError("group_deadline_exceeded")
    return MappingProxyType({
        "selectors": selectors,
        "minimum_cases": len(selectors),
        "timeout_seconds": int(spec["timeout_seconds"]),
        "evidence": tuple(spec["evidence"]),
        "executes_during_task68": bool(spec["executes_during_task68"]),
    })


_DECLARED = MappingProxyType({
    FOCUSED_GROUP: _freeze_group({
        "selectors": (
            "kernel_policy",
            "ast_source_binding",
            "dom_same_origin_state",
            "private_state_binding",
            "source_story_binding",
        ),
        "minimum_cases": 5,
        "timeout_seconds": 120,
        "evidence": ("kernel", "ast", "dom", "state", "source"),
        "executes_during_task68": True,
    }),
    "screenshot_story": _freeze_group({
        "selectors": (
            "tests/test_gui_ux_overhaul_campaign.py::test_screenshot_inputs_are_real_complete_synthetic_viewport_bound_pngs",
        ),
        "minimum_cases": 1,
        "timeout_seconds": 180,
        "evidence": ("source",),
        "executes_during_task68": False,
    }),
    "journey_bindings": _freeze_group({
        "selectors": (
            "tests/test_cimp_ux_67.py::test_measured_png_bytes_match_the_manifest_and_the_review",
            "tests/test_cimp_ux_67.py::test_public_recovery_commands_match_the_runner_parser",
        ),
        "minimum_cases": 2,
        "timeout_seconds": 180,
        "evidence": ("source",),
        "executes_during_task68": False,
    }),
    "historical_separation": _freeze_group({
        "selectors": (
            "tests/test_cimp_ux_67.py::test_screenshot_only_and_historical_completion_do_not_close_the_program",
        ),
        "minimum_cases": 1,
        "timeout_seconds": 180,
        "evidence": ("source",),
        "executes_during_task68": False,
    }),
})


def required_groups() -> dict[str, dict[str, Any]]:
    """Return copies. Callers cannot replace the declared selectors."""

    return {
        name: {
            "selectors": list(spec["selectors"]),
            "minimum_cases": spec["minimum_cases"],
            "timeout_seconds": spec["timeout_seconds"],
            "evidence": list(spec["evidence"]),
            "executes_during_task68": spec["executes_during_task68"],
        }
        for name, spec in _DECLARED.items()
    }


class _Output:
    """Hold a fresh private output directory until the report is durable."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.parent_fd: int | None = None
        self.child_fd: int | None = None
        if (not self.path.is_absolute() or self.path.parent.resolve(strict=True) != self.path.parent
                or self.path.name in ("", ".", "..")):
            raise CurrentAcceptanceError("private_output_path")
        root = _repo_root()
        if self.path == root or self.path.is_relative_to(root) or root.is_relative_to(self.path):
            raise CurrentAcceptanceError("private_output_overlaps_source")
        reserved = {".git", "campaign", "campaigns", "worker-worktrees", "claims", "watchdog", "control_plane", "control-plane"}
        for parent in (self.path.parent, *self.path.parent.parents):
            if parent.name in reserved or (parent / "launcher.json").exists() or (parent / ".git").exists():
                raise CurrentAcceptanceError("private_output_overlaps_control_state")
        try:
            self.parent_fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK)
            parent_stat = os.fstat(self.parent_fd)
            if parent_stat.st_uid != os.getuid() or parent_stat.st_mode & 0o077:
                raise CurrentAcceptanceError("private_output_parent")
            os.mkdir(self.path.name, 0o700, dir_fd=self.parent_fd)
            self.child_fd = os.open(
                self.path.name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=self.parent_fd,
            )
            self.reprove()
        except BaseException:
            self.close()
            raise

    def reprove(self) -> None:
        try:
            if self.path.parent.resolve(strict=True) != self.path.parent:
                raise CurrentAcceptanceError("private_output_custody")
            for held, named in (
                (os.fstat(self.parent_fd), os.stat(self.path.parent, follow_symlinks=False)),
                (os.fstat(self.child_fd), os.stat(self.path.name, dir_fd=self.parent_fd, follow_symlinks=False)),
            ):
                if (not stat.S_ISDIR(held.st_mode) or held.st_uid != os.getuid() or held.st_mode & 0o077
                        or (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino)):
                    raise CurrentAcceptanceError("private_output_custody")
        except OSError as exc:
            raise CurrentAcceptanceError("private_output_custody") from exc

    def close(self) -> None:
        for name in ("child_fd", "parent_fd"):
            fd = getattr(self, name)
            if fd is not None:
                setattr(self, name, None)
                os.close(fd)

    def __enter__(self) -> "_Output":
        self.reprove()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _write_report(directory: _Output, body: Mapping[str, Any]) -> Path:
    if type(directory) is not _Output:
        raise CurrentAcceptanceError("private_output_custody")
    directory.reprove()
    data = (_canonical(body) + "\n").encode()
    fd = os.open(
        "report.json",
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK,
        0o600,
        dir_fd=directory.child_fd,
    )
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    directory.reprove()
    os.fsync(directory.child_fd)
    return directory.path / "report.json"


def _case(selector: str, *, passed: bool, evidence_kind: str, detail: Mapping[str, Any]) -> dict[str, Any]:
    if not passed:
        raise CurrentAcceptanceError("required_case_not_passed:" + selector)
    return {
        "selector": selector,
        "case_id": selector,
        "executed": True,
        "skipped": False,
        "passed": True,
        "outcome": "passed",
        "evidence_kind": evidence_kind,
        "detail": dict(detail),
    }


def _kernel_case() -> dict[str, Any]:
    measured = probe_inherited_network_denial()
    again = probe_inherited_network_denial()
    unix_open = measured["af_unix"]["opened"] is True and measured["af_unix"]["errno"] == 0
    consistent = measured["af_unix_only"] == again["af_unix_only"]
    seccomp = measured.get("seccomp") or {}
    passed = bool(unix_open and consistent and seccomp.get("Seccomp"))
    return _case(
        "kernel_policy",
        passed=passed,
        evidence_kind="kernel",
        detail={
            "af_unix_only": bool(measured["af_unix_only"]),
            "af_unix_opened": bool(measured["af_unix"]["opened"]),
            "af_inet_opened": bool(measured["af_inet"]["opened"]),
            "af_inet_errno": int(measured["af_inet"]["errno"]),
            "seccomp": str(seccomp.get("Seccomp") or ""),
            "seccomp_filters": str(seccomp.get("Seccomp_filters") or ""),
            "caller_supplied": False,
        },
    )


def _ast_case() -> dict[str, Any]:
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    constants = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    functions = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }
    missing = [
        selector
        for spec in _DECLARED.values()
        for selector in spec["selectors"]
        if selector not in constants
    ]
    required_functions = {"run_focused_group", "aggregate_focused_groups", "main", "run_final_matrix", "invoke_native_verifier"}
    passed = not missing and required_functions <= functions and FOCUSED_GROUP in constants
    return _case(
        "ast_source_binding",
        passed=passed,
        evidence_kind="ast",
        detail={
            "module": Path(__file__).name,
            "declared_selector_count": sum(len(spec["selectors"]) for spec in _DECLARED.values()),
            "missing_selectors": missing,
            "functions_bound": sorted(required_functions),
        },
    )


class _DomCollector(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: dict[str, str] = {}
        self._current: str | None = None
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._flush()
        found = dict(attrs).get("id")
        self._current = str(found) if found else None
        self._chunks = []

    def handle_data(self, data: str) -> None:
        if self._current:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        self._flush()

    def _flush(self) -> None:
        if self._current is not None:
            self.ids[self._current] = "".join(self._chunks).strip()
        self._current = None
        self._chunks = []


def _story_app():
    """Same-origin synthetic page bound to the measured stale-header story."""

    root = _repo_root()
    contract = (root / EXPERIENCE_RELATIVE).read_text(encoding="utf-8")
    manifest = json.loads((root / MANIFEST_RELATIVE).read_text(encoding="utf-8"))
    workspace = next(row for row in manifest["screenshots"] if row["id"] == "02-workspace-desktop")
    if STALE_HEADER not in contract:
        raise CurrentAcceptanceError("source_story_missing")
    notes: list[str] = []

    async def application(scope, receive, send) -> None:
        if scope.get("type") != "http":
            await send({"type": "http.response.start", "status": 400, "headers": []})
            await send({"type": "http.response.body", "body": b""})
            return
        method = scope.get("method", "GET").upper()
        path = scope.get("path") or "/"
        message = await receive()
        body = message.get("body") or b""
        if method == "POST" and path == "/inquiry":
            payload = json.loads(body.decode("utf-8"))
            text = str(payload.get("text") or "")
            if text and text not in notes:
                notes.append(text)
            encoded = json.dumps({"stored": True, "count": len(notes)}).encode()
            await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": encoded})
            return
        inquiry = html.escape(notes[-1]) if notes else ""
        page = (
            "<!DOCTYPE html><html><body>"
            f"<p id=\"stale-access\">{html.escape(STALE_HEADER)}</p>"
            f"<main id=\"inquiry\" data-state=\"{html.escape(workspace['state'])}\">{inquiry}</main>"
            "<p id=\"mock-api\"></p>"
            "</body></html>"
        ).encode()
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/html; charset=utf-8")]})
        await send({"type": "http.response.body", "body": page})

    return application, notes, workspace["state"]


def _dom_case() -> dict[str, Any]:
    application, notes, state_name = _story_app()
    bridge = SameOriginAsgiBridge(application)
    external = bridge.handle(BrowserHttpRequest("GET", "https://example.invalid/workspace", []))
    socket_result = bridge.handle(BrowserHttpRequest(
        "GET",
        SAME_ORIGIN + "/workspace",
        [("upgrade", "websocket"), ("connection", "Upgrade")],
    ))
    before = bridge.handle(BrowserHttpRequest("GET", SAME_ORIGIN + "/", [("accept", "text/html")]))
    posted = bridge.handle(BrowserHttpRequest(
        "POST",
        SAME_ORIGIN + "/inquiry",
        [("content-type", "application/json"), ("accept", "application/json")],
        body=b'{"text":"synthetic pending inquiry"}',
    ))
    after = bridge.handle(BrowserHttpRequest("GET", SAME_ORIGIN + "/", [("accept", "text/html")]))
    parser = _DomCollector()
    parser.feed(after.body.decode("utf-8"))
    before_parser = _DomCollector()
    before_parser.feed(before.body.decode("utf-8"))
    stored = json.loads(posted.body.decode("utf-8"))
    passed = (
        external.action == "abort"
        and external.reason == "external-origin"
        and socket_result.action == "abort"
        and socket_result.reason == "websocket-unqualified"
        and before.status == 200
        and before_parser.ids.get("stale-access") == STALE_HEADER
        and before_parser.ids.get("inquiry") == ""
        and stored == {"stored": True, "count": 1}
        and notes == ["synthetic pending inquiry"]
        and parser.ids.get("stale-access") == STALE_HEADER
        and parser.ids.get("inquiry") == "synthetic pending inquiry"
        and state_name == "authenticated_backend_with_existing_stale_workspace_header"
        and "mockApi" not in after.body.decode("utf-8")
        and bridge.asgi_calls == 3
    )
    return _case(
        "dom_same_origin_state",
        passed=passed,
        evidence_kind="dom",
        detail={
            "stale_access": parser.ids.get("stale-access"),
            "inquiry": parser.ids.get("inquiry"),
            "workspace_state": state_name,
            "external_aborted": external.reason,
            "websocket_aborted": socket_result.reason,
            "asgi_calls": bridge.asgi_calls,
            "mock_api": False,
        },
    )


def _binding(principal: str) -> PrivateArtifactBinding:
    return PrivateArtifactBinding(
        tenant_id="synthetic-tenant-68",
        case_id="synthetic-case-68",
        artifact_kind="ux-acceptance-note",
        revision="1",
        principal_id=principal,
    )


def _state_case() -> dict[str, Any]:
    binding = _binding("synthetic-owner-68")
    envelope = seal_private_artifact(_PLAINTEXT, binding=binding, key=_KEY, key_id=_KEY_ID)
    opened = open_private_artifact(envelope, binding=binding, key=_KEY, expected_key_id=_KEY_ID)
    denied = False
    try:
        open_private_artifact(envelope, binding=_binding("synthetic-stranger-68"), key=_KEY, expected_key_id=_KEY_ID)
    except PrivateArtifactIntegrityError:
        denied = True
    hidden = _PLAINTEXT not in envelope and envelope.startswith(ENVELOPE_MAGIC)
    return _case(
        "private_state_binding",
        passed=opened == _PLAINTEXT and denied and hidden,
        evidence_kind="state",
        detail={"bytes": len(envelope), "stranger_denied": denied, "plaintext_hidden": hidden},
    )


def _source_case() -> dict[str, Any]:
    root = _repo_root()
    files = {relative: _sha256(root / relative) for relative in _SOURCE_FILES}
    manifest = json.loads((root / MANIFEST_RELATIVE).read_text(encoding="utf-8"))
    contract = json.loads((root / CONTRACT_RELATIVE).read_text(encoding="utf-8"))
    experience = (root / EXPERIENCE_RELATIVE).read_text(encoding="utf-8")
    review = (root / REVIEW_RELATIVE).read_text(encoding="utf-8")
    pngs = [row for row in manifest["screenshots"] if (root / "docs/ux/complaint_ux_overhaul/baseline" / row["path"]).is_file()]
    passed = (
        all(len(value) == 64 for value in files.values())
        and manifest["screenshot_count"] == len(manifest["screenshots"]) == len(pngs) == 13
        and manifest["synthetic_data_only"] is True
        and manifest["provider_invoked"] is False
        and manifest["mock_api_used"] is False
        and STALE_HEADER in experience
        and STALE_HEADER in review
        and contract.get("completion_authority") is False
        and contract.get("instructional_only") is True
        and TASK_ID in contract.get("task_ids", [])
        and contract.get("native_history_verifier") == NATIVE_VERIFIER
    )
    return _case(
        "source_story_binding",
        passed=passed,
        evidence_kind="source",
        detail={"files": files, "screenshot_count": manifest["screenshot_count"], "completion_authority": False},
    )


_EXECUTORS = MappingProxyType({
    "kernel_policy": _kernel_case,
    "ast_source_binding": _ast_case,
    "dom_same_origin_state": _dom_case,
    "private_state_binding": _state_case,
    "source_story_binding": _source_case,
})


def _execute_focused_cases() -> list[dict[str, Any]]:
    spec = _DECLARED[FOCUSED_GROUP]
    if tuple(_EXECUTORS) != spec["selectors"]:
        raise CurrentAcceptanceError("mandatory_selector_missing")
    cases = [_EXECUTORS[selector]() for selector in spec["selectors"]]
    nodeids = [case["selector"] for case in cases]
    if nodeids != list(spec["selectors"]) or len(nodeids) < spec["minimum_cases"]:
        raise CurrentAcceptanceError("empty_or_missing_required_cases")
    if any(case["skipped"] or case["outcome"] != "passed" or not case["executed"] for case in cases):
        raise CurrentAcceptanceError("required_case_not_passed")
    kinds = {case["evidence_kind"] for case in cases}
    if kinds != set(spec["evidence"]):
        raise CurrentAcceptanceError("mandatory_selector_missing")
    return cases


_RUNS: weakref.WeakSet = weakref.WeakSet()
_TOKEN = object()


class FocusedGroupRun:
    __slots__ = ("_json", "_source", "__weakref__")

    def __init__(self, token: object, body: Mapping[str, Any], source: Mapping[str, str]) -> None:
        if token is not _TOKEN:
            raise CurrentAcceptanceError("host_measurement_required")
        object.__setattr__(self, "_json", _canonical(body))
        object.__setattr__(self, "_source", _canonical(source))

    def __setattr__(self, name: str, value: Any) -> None:
        raise CurrentAcceptanceError("immutable_host_run")

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self._json)

    @property
    def source_digest(self) -> str:
        return self._source


def _source_digest() -> dict[str, str]:
    root = _repo_root()
    return {relative: _sha256(root / relative) for relative in _SOURCE_FILES}


def run_focused_group(output_directory: Path) -> FocusedGroupRun:
    """Execute the one controller group. Do not read task status or Native history."""

    spec = _DECLARED[FOCUSED_GROUP]
    if not spec["executes_during_task68"]:
        raise CurrentAcceptanceError("final_matrix_outside_task68_budget")
    with _Output(Path(output_directory)) as custody:
        before = _source_digest()
        cases = _execute_focused_cases()
        after = _source_digest()
        if before != after:
            raise CurrentAcceptanceError("stale_current_source")
        body = {
            "schema": SCHEMA,
            "task_id": TASK_ID,
            "scope": "one_bounded_current_controller_group",
            "group": FOCUSED_GROUP,
            "selectors": list(spec["selectors"]),
            "cases": cases,
            "executed": True,
            "skipped_required_cases": 0,
            "passed": True,
            "focused_controller_passed": True,
            "source_before": before,
            "source_after": after,
            "source_unchanged": True,
            "missing_groups": [name for name in _DECLARED if name != FOCUSED_GROUP],
            "current_acceptance_passed": False,
            "final_matrix_executed": False,
            "native_verifier_invoked": False,
            "native_verifier": NATIVE_VERIFIER,
            "preconditions_checked": [],
            "required_completed_tasks": [],
            "self_pending_circular_precondition": False,
            "completion_authority": False,
            "provider_invoked": False,
        }
        path = _write_report(custody, body)
        body["report_path"] = str(path)
        issued = FocusedGroupRun(_TOKEN, body, before)
        _RUNS.add(issued)
        return issued


def aggregate_focused_groups(runs: Sequence[Any]) -> dict[str, Any]:
    """Accept only live runs from this process. Saved JSON is not a result."""

    runs = tuple(runs)
    if any(type(item) is not FocusedGroupRun or item not in _RUNS for item in runs):
        raise CurrentAcceptanceError("host_measurement_required")
    current = _canonical(_source_digest())
    seen: dict[str, dict[str, Any]] = {}
    for item in runs:
        body = item.to_dict()
        if body["group"] in seen:
            raise CurrentAcceptanceError("duplicate_group")
        if item.source_digest != current or body["source_before"] != body["source_after"]:
            raise CurrentAcceptanceError("stale_current_source")
        spec = _DECLARED.get(body["group"])
        if spec is None or not spec["executes_during_task68"] or body["selectors"] != list(spec["selectors"]):
            raise CurrentAcceptanceError("group_contract_mismatch")
        if [case["selector"] for case in body["cases"]] != list(spec["selectors"]):
            raise CurrentAcceptanceError("group_case_identity_mismatch")
        if any(case.get("skipped") or case.get("outcome") != "passed" for case in body["cases"]):
            raise CurrentAcceptanceError("required_case_not_passed")
        if body.get("completion_authority") is not False or body.get("native_verifier_invoked") is not False:
            raise CurrentAcceptanceError("caller_or_saved_json_not_authority")
        seen[body["group"]] = body
    missing = [name for name in _DECLARED if name not in seen]
    return {
        "schema": SCHEMA,
        "scope": "current_local_synthetic_acceptance",
        "groups": list(seen.values()),
        "missing_groups": missing,
        "executed_groups": len(seen),
        "focused_controller_passed": FOCUSED_GROUP in seen and seen[FOCUSED_GROUP]["passed"] is True,
        "current_acceptance_passed": False,
        "final_matrix_executed": False,
        "native_verifier_invoked": False,
        "completion_authority": False,
    }


def run_final_matrix() -> dict[str, Any]:
    """The full selector matrix is outside this task's validation budget."""

    raise CurrentAcceptanceError("final_matrix_outside_task68_budget")


def invoke_native_verifier() -> dict[str, Any]:
    """Production Native completion stays after the genuine callback."""

    raise CurrentAcceptanceError("native_verifier_after_genuine_callback")


def accept_caller_boolean(passed: bool) -> None:
    raise CurrentAcceptanceError("caller_or_saved_json_not_authority")


def accept_saved_report(payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, Mapping):
        raise CurrentAcceptanceError("host_measurement_required")
    raise CurrentAcceptanceError("caller_or_saved_json_not_authority")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Focused current-source UX acceptance. No Native completion authority.")
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--group", choices=(FOCUSED_GROUP,), default=FOCUSED_GROUP)
    parser.add_argument("--final-matrix", action="store_true")
    parser.add_argument("--native-verifier", action="store_true")
    options = parser.parse_args(list(argv) if argv is not None else None)
    if options.final_matrix:
        run_final_matrix()
    if options.native_verifier:
        invoke_native_verifier()
    run = run_focused_group(options.output_root)
    summary = aggregate_focused_groups([run])
    sys.stdout.write(_canonical({
        "report": run.to_dict()["report_path"],
        "focused_controller_passed": summary["focused_controller_passed"],
        "current_acceptance_passed": summary["current_acceptance_passed"],
        "missing_groups": summary["missing_groups"],
        "completion_authority": False,
    }) + "\n")
    return 0 if summary["focused_controller_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
