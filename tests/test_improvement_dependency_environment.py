"""Campaign dependency bootstrap stays non-fetching in the real native boundaries."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import socket
import subprocess

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner
from ipfs_accelerate_py.agent_supervisor.runtime import grok_cli_runner as grok
from ipfs_accelerate_py.agent_supervisor.runtime.provider_command_environment import project_provider_command_environment
from ipfs_accelerate_py.agent_supervisor.validation.validation_runtime import build_validation_environment

ROOT = Path(__file__).resolve().parents[1]
FLAG = "COMMON_CRAWL_AUTO_CLONE_SOURCE"
pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


@pytest.mark.parametrize("ambient", [{}, {FLAG: "0"}, {FLAG: "1"}, {FLAG: "true"}])
def test_campaign_pins_nonfetch_dependency_policy_after_ambient_overrides(tmp_path, ambient):
    environment = runner.campaign_environment(ROOT, ambient, state_dir=tmp_path / "state")
    assert environment[FLAG] == "0"
    assert environment["TODO_DAEMON_LLM_PROVIDER"] == "grok_cli"
    assert environment["TODO_DAEMON_LLM_ALLOW_CROSS_PROVIDER_FALLBACK"] == "0"
    assert environment[runner.AUTOMATIC_RETRY_REARM_ENV] == "1"


def test_campaign_policy_reaches_real_native_provider_and_validation_environments(tmp_path):
    source = runner.campaign_environment(ROOT, {FLAG: "1", "COMMON_CRAWL_SEARCH_ENGINE_REPO": "not-approved"}, state_dir=tmp_path / "state")
    provider = project_provider_command_environment(source)
    validation = build_validation_environment(source)
    workspace = tmp_path / "workspace"; workspace.mkdir()
    home = tmp_path / "home"; home.mkdir()
    effective, approved = grok._grok_task_container_environment(
        base_env=source, child_env={}, workspace=workspace, grok_home=home)
    assert all(v[FLAG] == "0" for v in (source, provider, validation, effective, approved))
    assert all("COMMON_CRAWL_SEARCH_ENGINE_REPO" not in v for v in (provider, validation, effective, approved))
    assert effective[grok.PROVIDER_COMMAND_ENV_DIGEST_ENV] == grok.provider_command_environment_sha256(approved)


def test_pinned_upstream_missing_source_does_not_clone_and_remains_unavailable(tmp_path, monkeypatch):
    environment = runner.campaign_environment(ROOT, {FLAG: "1"}, state_dir=tmp_path / "state")
    # Load the complete unmodified upstream module in an isolated empty source
    # tree. No real checkout, package source or existing nested repository is edited.
    package = importlib.util.find_spec("ipfs_datasets_py")
    assert package is not None and package.origin
    upstream = Path(package.origin).parent / "processors/web_archiving/common_crawl_integration.py"
    assert upstream.is_file()
    isolated = tmp_path / "source/common_crawl_integration.py"
    isolated.parent.mkdir()
    isolated.write_bytes(upstream.read_bytes())
    calls = []
    def no_external(*args, **kwargs):
        calls.append(True)
        raise AssertionError("external bootstrap is forbidden")
    monkeypatch.setattr(subprocess, "run", no_external)
    monkeypatch.setattr(socket, "create_connection", no_external)
    monkeypatch.setattr(socket.socket, "connect", no_external)
    monkeypatch.setenv(FLAG, environment[FLAG])
    monkeypatch.setenv("COMMON_CRAWL_ENABLE_LEGACY_HF_STREAMING_FALLBACK", "0")
    for name in ("CCINDEX_STATE_DIR", "CCINDEX_EVENT_LOG_PATH", "CCINDEX_BRAVE_TRACE", "BRAVE_RESOLVE_STRATEGY", "BRAVE_RESOLVE_ROWGROUP_SLICE_MODE", "BRAVE_RESOLVE_SKIP_LEGACY_SCHEMA", "BRAVE_RESOLVE_ROWGROUP_WORKERS"):
        monkeypatch.delenv(name, raising=False)
    spec = importlib.util.spec_from_file_location("synthetic_common_crawl_nonfetch", isolated)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module._ensure_common_crawl_source_checkout() is None
    engine = module.CommonCrawlSearchEngine(mode="local", state_dir=tmp_path / "state")
    assert engine.is_available() is False and engine.api is None
    assert calls == []
    assert not (isolated.parent / "common_crawl_search_engine").exists()
    assert isolated.read_bytes() == upstream.read_bytes()
    assert module.assert_module_source_unchanged() == module.MODULE_IMPORT_SOURCE_SHA256
