"""Qualify real Chromium execution against the actual ASGI app.

A missing browser, a required skip, or an empty browser result fails the
module. Direct bridge cases cover cookie and header fidelity without treating
HTTP interception as WebSocket, SSE, or streaming coverage.
"""

from __future__ import annotations

from pathlib import Path
import json

import pytest

from tests.gui_native_browser import (
    BrowserCapabilityError,
    probe_inherited_network_denial,
    qualify_native_browser,
)
from tests.test_gui_native_browser_capability import (
    assert_harness_source_contract,
    assert_qualification_report,
    test_bridge_forwards_set_cookie_and_does_not_replay_it,
    test_header_forwarding_copies_browser_values_without_actor_authority,
    test_missing_chromium_fails_instead_of_skipping,
    test_driver_discovery_accepts_installed_sync_api_package,
    test_chromium_discovery_matches_driver_manifest,
    test_approved_cache_with_only_other_revision_fails_closed,
    test_bridge_preserves_actual_asgi_effects_inside_running_loop,
    test_bridge_propagates_actual_asgi_failure_inside_running_loop,
)


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]


def test_capability_contract_rejects_jars_skips_and_missing_browsers(tmp_path: Path) -> None:
    assert_harness_source_contract()
    test_missing_chromium_fails_instead_of_skipping(tmp_path)
    test_header_forwarding_copies_browser_values_without_actor_authority()
    test_bridge_forwards_set_cookie_and_does_not_replay_it(tmp_path)


def test_network_probe_is_stable_and_does_not_install_a_filter() -> None:
    first = probe_inherited_network_denial()
    second = probe_inherited_network_denial()
    assert first == second
    assert "af_unix" in first and "af_inet" in first and "seccomp" in first


def test_real_chromium_qualifies_dom_cookies_downloads_and_cleanup(tmp_path: Path) -> None:
    try:
        report = qualify_native_browser(tmp_path / "browser-profiles")
    except BrowserCapabilityError as exc:
        pytest.fail(f"native browser capability failed: {exc}")
    assert_qualification_report(report)
    metadata = {
        "schema": "complaint-gui02-browser-capability-observation@1",
        "scope": "synthetic browser capability; executor qualification is separate",
        "node_sha256": report.node.sha256,
        "chromium_sha256": report.chromium.sha256,
        "playwright_version": report.playwright_version,
        "download_transport": report.download_transport,
        "direct_attachment_navigation_qualified": report.direct_attachment_navigation_qualified,
        "download": {key: value for key, value in report.download.items() if key not in {"bytes", "path"}},
        "network_denial": report.network_denial,
        "pipe_transport": report.pipe_transport,
        "cross_context_isolated": report.cross_context_isolated,
        "cookie_replayed_by_bridge": report.cookie_replayed_by_bridge,
        "child_cleanup": report.child_cleanup,
        "qualified_transports": report.qualified_transports,
        "unsupported_transport_outcomes": report.unsupported_transport_outcomes,
        "limitations": report.limitations,
        "completion_authority": False,
    }
    receipt = tmp_path / "browser-capability-observation.json"
    receipt.write_text(json.dumps(metadata, sort_keys=True, indent=2) + "\n")
    receipt.chmod(0o600)
