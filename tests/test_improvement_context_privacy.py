"""Consumed native privacy controls, with synthetic-only source and byte markers.

Builder assertions are construction evidence, not live container/read-denial proof.
No model, real credential, Docker daemon, or campaign state is used here.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner
from ipfs_accelerate_py.agent_supervisor.runtime import grok_cli_runner as native
from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon
from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor

ROOT = Path(__file__).resolve().parents[1]
pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
PRIVATE_ROOTS = (".complaint_workspace", "data", "output", "statefiles", "exports", "secrets",
                 "evidence", "uploads", "attachments")
DEPENDENCIES = ("external/ipfs_accelerate_py", "external/ipfs_datasets_py", "external/ipfs_kit_py")
MARKER = "SYNTHETIC-PRIVATE-BYTES-OPS05-0b912"


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch, tmp_path):
    monkeypatch.chdir(ROOT)
    for key in ("XAI_API_KEY", "ipfs_accelerate_py_XAI_API_KEY", "IPFS_ACCELERATE_PY_XAI_API_KEY",
                "IPFS_DATASETS_PY_XAI_API_KEY", "GROK_AUTH_PROVIDER_COMMAND"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GROK_HOME", str(tmp_path / "empty-auth"))


def workspace(tmp_path):
    root = tmp_path / "synthetic-source"
    root.mkdir()
    for prefix in ("", *DEPENDENCIES):
        base = root / prefix
        (base / "src").mkdir(parents=True)
        (base / "src/app.py").write_text("# safe synthetic source\nVALUE = 1\n")
        for name in PRIVATE_ROOTS:
            (base / name).mkdir()
            (base / name / "synthetic.txt").write_text(MARKER)
        (base / ".env.synthetic").write_text(MARKER)
        (base / "synthetic.key").write_text(MARKER)
        (base / "synthetic.pem").write_text(MARKER)
        # A nested Git directory is an alternate private-byte reconstruction
        # channel even when source files themselves are safe.
        (base / ".git/objects").mkdir(parents=True)
        (base / ".git/objects/synthetic-object").write_text(MARKER)
    return root


def policy(root, **kwargs):
    return runner.campaign_environment(root, {"HOME": str(root.parent / "operator"), "PATH": os.defpath}, **kwargs)


@pytest.mark.parametrize("prefix", ("", *DEPENDENCIES))
def test_actual_native_policy_denies_private_roots_but_keeps_dependency_source(tmp_path, prefix):
    root = workspace(tmp_path)
    env = policy(root)
    denied = set(native._grok_private_workspace_paths(base_env=env, workspace=root))
    for name in (*PRIVATE_ROOTS, ".env.synthetic", "synthetic.key", "synthetic.pem"):
        assert root / prefix / name in denied
    if prefix:
        assert root / prefix / ".git" in denied
    assert root / prefix / "src" not in denied
    assert root / prefix / "src/app.py" not in denied
    assert len(native.validate_grok_private_path_patterns(env[runner.PRIVATE_PATHS_ENV])) <= 64
    assert MARKER not in json.dumps(env)


def test_native_environment_projection_preserves_exact_closed_policy(tmp_path, monkeypatch):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon
    root = workspace(tmp_path)
    env = policy(root)
    monkeypatch.setattr(runner.os, "environ", dict(env))
    child = implementation_daemon.PortalImplementationDaemon._implementation_untrusted_process_environment()
    assert child[runner.PRIVATE_PATHS_ENV] == env[runner.PRIVATE_PATHS_ENV]
    # The terminal wrapper is intentionally a non-secret closed environment;
    # the parent native builder consumes private paths before that projection.
    assert set(native._grok_private_workspace_paths(base_env=child, workspace=root)) == set(
        native._grok_private_workspace_paths(base_env=env, workspace=root))


def test_actual_ordinary_builder_masks_private_bytes_and_git_not_source(tmp_path):
    root = workspace(tmp_path)
    env = policy(root)
    temporary, child, _policy, denied = native._isolated_grok_home(
        base_env=env, child_env={}, codex_fallback_command=(), workspace=root)
    try:
        prompt = tmp_path / "prompt.txt"
        prompt.write_text("Implement synthetic source task; no user data.")
        binary = tmp_path / "inert-grok"
        binary.write_text("#!/bin/sh\nexit 97\n")
        binary.chmod(0o700)
        command = native._docker_ordinary_grok_command(
            grok_command=[str(binary), "--tools", native._SEALED_GROK_TOOLS,
                          "--disallowed-tools", native._SEALED_GROK_DISALLOWED_TOOLS,
                          "--no-subagents", "--disable-web-search"],
            grok_bin=binary, workspace=root, prompt_path=prompt,
            grok_home=Path(temporary.name), base_env=env, child_env=child,
            denied_paths=denied, mask_root=tmp_path / "masks", docker_config=tmp_path / "config",
            container_name="ipfs-accelerate-grok-123-" + "a" * 32, cidfile=tmp_path / "cid",
            docker_bin="/fixture/never-executed-docker", isolation_image=native._ordinary_task_toolchain_image_pin(),
            task_execution=True)
        mounts = [command[i + 1] for i, token in enumerate(command) if token == "--mount"]
        for private in (*denied, root / ".git"):
            if not private.is_relative_to(root):
                continue
            matching = [m for m in mounts if f"dst={private}," in m]
            assert len(matching) == 1
            fields = dict(p.split("=", 1) for p in matching[0].split(",") if "=" in p)
            mask = Path(fields["src"])
            assert mask.is_relative_to(tmp_path / "masks") and mask != private
            assert stat.S_IMODE(mask.stat().st_mode) == 0 and "readonly" in matching[0]
        assert any(f"src={root}" in m.split(",") and f"dst={root}" in m.split(",") and "readonly" not in m for m in mounts)
        assert not any(f"dst={root / prefix / 'src'}," in m for prefix in ("", *DEPENDENCIES) for m in mounts)
        assert "--pull=never" in command and "--read-only" in command
        assert "--cap-drop=ALL" in command and "--security-opt=no-new-privileges" in command
        assert MARKER not in " ".join(command)
        assert MARKER not in (tmp_path / "task-launchers/task-bootstrap.py").read_text()
    finally:
        temporary.cleanup()


@pytest.mark.parametrize("prefix", ("", *DEPENDENCIES))
def test_actual_native_alias_check_refuses_private_symlink(tmp_path, prefix):
    root = workspace(tmp_path)
    alias = root / prefix / "src/alias"
    alias.symlink_to(root / prefix / "secrets/synthetic.txt")
    denied = native._grok_private_workspace_paths(base_env=policy(root), workspace=root)
    assert alias in native._workspace_symlinks_reach_denied_paths(workspace=root, denied_paths=denied)
    assert alias.readlink() == root / prefix / "secrets/synthetic.txt"
    assert (root / prefix / "secrets/synthetic.txt").read_text() == MARKER


@pytest.mark.parametrize("kind", ("private", "external"))
def test_actual_native_hardlink_check_refuses_private_and_external_aliases(tmp_path, kind):
    root = workspace(tmp_path)
    source = root / "data/synthetic.txt"
    if kind == "external":
        source = tmp_path / "outside"
        source.write_text(MARKER)
    alias = root / "src/alias"
    os.link(source, alias)
    before = source.stat()
    denied = native._grok_private_workspace_paths(base_env=policy(root), workspace=root)
    assert alias in native._workspace_regular_file_hardlinks(root, private_paths=denied)
    assert source.stat().st_ino == before.st_ino and source.stat().st_nlink == 2
    assert source.read_text() == MARKER


@pytest.mark.parametrize("raw", ('["../outside"]', '["/outside"]', '["**/*.key"]', '[".git"]'))
def test_invalid_policy_refuses_before_docker_probe_without_path_echo(tmp_path, monkeypatch, raw):
    root = workspace(tmp_path)
    env = policy(root)
    env[runner.PRIVATE_PATHS_ENV] = raw
    monkeypatch.setattr(native, "_docker_isolation_binary", lambda: pytest.fail("invalid policy reached Docker"))
    result = runner._private_runtime_checks(root, env)
    assert result == {"ready": False, "native_enforcement_available": True,
                      "reason": "native_private_path_policy_invalid"}
    assert raw not in json.dumps(result) and MARKER not in json.dumps(result)


def test_native_private_prefix_escape_refuses_before_docker_probe(tmp_path, monkeypatch):
    root = tmp_path / "source"
    root.mkdir()
    outside = tmp_path / "private-outside"
    outside.mkdir()
    (outside / "synthetic.key").write_text(MARKER)
    (root / "external").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(native, "_docker_isolation_binary", lambda: pytest.fail("escaping policy reached Docker"))
    result = runner._private_runtime_checks(root, policy(root))
    assert not result["ready"] and result["reason"] == "native_private_path_policy_invalid"
    assert (outside / "synthetic.key").read_text() == MARKER


@pytest.mark.parametrize("unavailable", ("docker", "base-image", "task-image"))
def test_missing_native_container_refuses_without_dispatch(tmp_path, monkeypatch, unavailable):
    root = workspace(tmp_path)
    monkeypatch.setattr(native, "_docker_isolation_binary", lambda: "" if unavailable == "docker" else "/fixture/docker")
    monkeypatch.setattr(native, "_docker_isolation_image_id", lambda *a, **k: "" if unavailable == "base-image" else "sha256:base")
    monkeypatch.setattr(native, "_docker_ordinary_task_toolchain_image_id", lambda *a, **k: "" if unavailable == "task-image" else "sha256:task")
    monkeypatch.setattr(native.subprocess, "Popen", lambda *a, **k: pytest.fail("unavailable container dispatched process"))
    result = runner._private_runtime_checks(root, policy(root))
    assert not result["ready"] and not result["docker_ready"]
    assert MARKER not in json.dumps(result)


@pytest.mark.parametrize("case", ("missing", "empty", "symlink", "hardlink", "writable", "oversize", "safe"))
def test_auth_presence_does_not_read_or_validate_credentials(tmp_path, monkeypatch, case):
    home = tmp_path / "operator"
    home.mkdir()
    auth = home / "auth.json"
    if case != "missing":
        auth.write_text("" if case == "empty" else MARKER)
        auth.chmod(0o600)
    if case == "symlink":
        target = home / "target"
        auth.rename(target)
        auth.symlink_to(target)
    elif case == "hardlink":
        os.link(auth, home / "alias")
    elif case == "writable":
        auth.chmod(0o666)
    elif case == "oversize":
        with auth.open("wb") as handle:
            handle.truncate(1_048_577)
    monkeypatch.setattr(Path, "read_bytes", lambda *a, **k: pytest.fail("credential bytes read"))
    monkeypatch.setattr(Path, "read_text", lambda *a, **k: pytest.fail("credential text read"))
    assert runner._auth_material_present({"GROK_HOME": str(home)}) is (case == "safe")
    assert runner._auth_material_present({"GROK_HOME": str(home), "XAI_API_KEY": "synthetic-not-real"}) is True


def test_internal_admission_rechecks_auth_before_native_effect(tmp_path, monkeypatch):
    from integrations.ipfs_accelerate.improvement_plan import build_improvement_work_plan, load_spec
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor_runner
    spec = ROOT / runner.SPEC_RELATIVE
    plan_id = build_improvement_work_plan(load_spec(spec)).plan_id
    state = tmp_path / "state"
    state.mkdir()
    record = {"owner_token": "synthetic-owner", "identity": {"pid": os.getpid()}, "plan_id": plan_id}
    runner._atomic_json(state / "launcher.json", record)
    monkeypatch.setattr(runner, "owns_process", lambda r: True)
    monkeypatch.setattr(runner, "_validate_board", lambda *a: {})
    monkeypatch.setattr(runner, "_private_runtime_checks", lambda *a: pytest.fail("missing auth reached later admission"))
    monkeypatch.setattr(implementation_supervisor_runner, "run_configured_portal_implementation_supervisor",
                        lambda *a, **k: pytest.fail("missing auth launched native supervisor"))
    with pytest.raises(RuntimeError, match="^auth_material_unavailable$"):
        runner.run_internal(ROOT, spec, state, "synthetic-owner", "synthetic-main")
    assert not (state / "task_state.json").exists()
    assert json.loads((state / "launcher.json").read_text()) == record


def test_actual_native_arguments_and_environment_keep_bounded_source_campaign(tmp_path):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor
    env = policy(tmp_path)
    args = implementation_supervisor.parse_args(runner.native_argv(tmp_path / "todo.md", tmp_path / "state", "synthetic-main"))
    assert args.implementation_timeout == args.implementation_max_timeout == 900
    assert args.implementation_log_stall_seconds == 180
    assert args.max_task_attempts == 3 and args.max_restarts == 5
    assert env["IPFS_ACCELERATE_AGENT_GROK_MAX_TURNS"] == "64"
    assert env["IPFS_ACCELERATE_AGENT_GROK_MODEL"] == "grok-4.7"
    assert env["TODO_DAEMON_LLM_ALLOW_CROSS_PROVIDER_FALLBACK"] == "0"
    assert args.task_source_kind == "legacy-markdown" and args.explicit_legacy_task_source


def test_native_context_capsule_never_enumerates_private_source_bodies(tmp_path, monkeypatch):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon
    from ipfs_accelerate_py.agent_supervisor.context.context_compiler import render_context_capsule
    repo = workspace(tmp_path)
    # Real Git and native nonimplementing configuration live only in this
    # disposable synthetic source tree; neither can select or launch a task.
    def git(*args):
        subprocess.run(["git", *args], cwd=repo, check=True, text=True, capture_output=True)
    shutil.rmtree(repo / ".git")
    git("init", "-b", "main")
    todo = repo / "synthetic.todo.md"
    todo.write_text("# Synthetic task board\n")
    git("add", "src/app.py", "synthetic.todo.md")
    git("-c", "user.name=Synthetic fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "-m", "Synthetic source only")
    daemon = implementation_daemon.TodoImplementationDaemon(
        todo_path=todo, state_path=tmp_path / "native-state/task_state.json",
        strategy_path=tmp_path / "native-state/strategy.json",
        events_path=tmp_path / "native-state/events.jsonl", repo_root=repo,
        implement=False, task_header_prefix="## CIMP-")
    task = implementation_daemon.PortalTask(
        task_id="CIMP-SYNTHETIC-01", title="Synthetic source-only context", status="ready",
        completion="manual", priority="P0", track="synthetic", outputs=["src/app.py"],
        validation=["python -m pytest -q tests/test_synthetic.py"],
        acceptance="SYNTHETIC-TASK-CONTEXT-ALLOWED",
        metadata={"Provider role": "deterministic-only"})
    # Refuse any attempt by actual compilation to read private file bodies.
    real_read_bytes, real_read_text = Path.read_bytes, Path.read_text
    denied = native._grok_private_workspace_paths(base_env=policy(repo), workspace=repo)
    def check(path):
        assert not any(path == private or path.is_relative_to(private) for private in denied), "private content read into host context"
    def read_bytes(path, *args, **kwargs):
        check(path)
        return real_read_bytes(path, *args, **kwargs)
    def read_text(path, *args, **kwargs):
        check(path)
        return real_read_text(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    monkeypatch.setattr(Path, "read_text", read_text)
    result = daemon._compile_implementation_context(task, attempt=1)
    prompt = render_context_capsule(result.capsule)
    assert "SYNTHETIC-TASK-CONTEXT-ALLOWED" in prompt and "src/app.py" in prompt
    assert MARKER not in prompt and MARKER not in json.dumps(result.receipt.to_dict())
    assert daemon.implement is False
