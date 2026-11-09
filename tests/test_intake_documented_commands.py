"""Execute the documented intake commands against a fresh temporary home.

The examples come from the CLI catalog. The operator guide and README must
carry the same primary command and the same example lines. No example may
point at a user home, a Codex profile, or an absolute interpreter path.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GUIDE = REPO_ROOT / "docs" / "COMPLAINT_INTAKE_OPERATOR_GUIDE.md"
README = REPO_ROOT / "README.md"
SPEC = REPO_ROOT / "docs" / "task_boards" / "complaint_intake_improvement_spec.json"
PRIMARY = "python -m complaint_generator.cli chat --user-id USER_ID"
FORBIDDEN_FRAGMENTS = (
    "/home/",
    "Codex",
    ".codex",
    "python3.11",
    "/usr/local/bin/python",
    "~/",
)


def _catalog() -> dict:
    from applications.complaint_cli import intake_operator_catalog

    return intake_operator_catalog()


def _python_argv(command: str, replacements: dict[str, str]) -> list[str]:
    rendered = command
    for key, value in replacements.items():
        rendered = rendered.replace(key, value)
    assert rendered.startswith("python ")
    body = rendered.split(" ", 1)[1]
    return [sys.executable, *body.split()]


def _run(argv: list[str], *, cwd: Path, env: dict, stdin: str = "", timeout: float = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        input=stdin,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _operator_env(home: Path, extra: dict | None = None) -> dict[str, str]:
    env = {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/bin",
        "HOME": str(home),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
        "XDG_STATE_HOME": str(home / ".local" / "state"),
        "PYTHONPATH": os.pathsep.join(dict.fromkeys([str(REPO_ROOT), *filter(None, os.environ.get("PYTHONPATH", "").split(os.pathsep))])),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "IPFS_DATASETS_PY_AUTO_NLTK_DOWNLOAD": "0",
        "IPFS_DATASETS_PY_MINIMAL_IMPORTS": "1",
        "COMMON_CRAWL_AUTO_CLONE_SOURCE": "0",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "COMPLAINT_CLI_NO_COLOR": "1",
        "TERM": "dumb",
    }
    for key in (
        "XAI_API_KEY",
        "ipfs_accelerate_py_XAI_API_KEY",
        "IPFS_ACCELERATE_PY_XAI_API_KEY",
        "IPFS_DATASETS_PY_XAI_API_KEY",
        "GROK_HOME",
    ):
        env.pop(key, None)
    if extra:
        env.update(extra)
    return env


def test_catalog_matches_guide_and_readme() -> None:
    catalog = _catalog()
    guide = GUIDE.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    assert catalog["primary_tui_command"] == PRIMARY
    assert guide.count(PRIMARY) >= 1
    assert PRIMARY in readme
    assert catalog["interpreter"] == "python"
    assert "COMPLAINT_WORKSPACE_SESSION_DIR" in guide
    assert ".complaint_workspace/sessions" in guide
    for example in catalog["examples"]:
        assert example["command"] in guide, example["id"]
        for fragment in FORBIDDEN_FRAGMENTS:
            assert fragment not in example["command"]
    for phrase in (
        "factual assertion",
        "applicable legal requirement",
        "Saturation",
        "legal sufficiency",
        "Remote model processing",
        "encryption at rest",
        "Local deletion",
        "remote erasure",
        "grok-4.7",
        "pinned",
        "cryptography>=41.0.0",
        "typer>=0.12.0",
    ):
        assert phrase in guide
    for fragment in ("/home/", "Codex", ".codex"):
        assert fragment not in guide
        section = readme[readme.find("primary intake terminal command"): readme.find("primary intake terminal command") + 1600]
        assert fragment not in section


def test_pinned_submodule_paths_exist() -> None:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    pins = spec["upstream_pins"]
    for name in ("ipfs_accelerate_py", "ipfs_datasets_py", "ipfs_kit_py"):
        path = REPO_ROOT / "external" / name
        assert path.is_dir(), name
        assert pins[name]


def _pty_run(argv: list[str], *, cwd: Path, env: dict, steps: list[tuple[str, str]], timeout: float = 90) -> tuple[int, str]:
    import pty
    import select
    import time

    master, slave = pty.openpty()
    process = subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        start_new_session=True,
    )
    os.close(slave)
    view = ""
    recent = ""
    pending = list(steps)
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline and process.poll() is None and pending:
            readable, _, _ = select.select([master], [], [], 0.2)
            if readable:
                try:
                    chunk = os.read(master, 4096).decode(errors="replace")
                except OSError:
                    break
                view += chunk
                recent = (recent + chunk)[-4000:]
            if pending and pending[0][0] in recent:
                os.write(master, pending[0][1].encode())
                recent = ""
                pending.pop(0)
        while time.monotonic() < deadline and process.poll() is None:
            readable, _, _ = select.select([master], [], [], 0.2)
            if not readable:
                continue
            try:
                chunk = os.read(master, 4096)
            except OSError:
                break
            if not chunk:
                break
            view += chunk.decode(errors="replace")
        if process.poll() is None:
            process.kill()
    finally:
        os.close(master)
    code = process.wait(timeout=10)
    return code, view


def test_primary_tui_controls_save_and_resume(tmp_path: Path) -> None:
    home = tmp_path / "home"
    sessions = tmp_path / "sessions"
    home.mkdir()
    sessions.mkdir(mode=0o700)
    env = _operator_env(home, {"COMPLAINT_WORKSPACE_SESSION_DIR": str(sessions)})
    init_code, init_out = _pty_run(
        _python_argv(
            "python -m complaint_generator.cli keys-init --store-dir STORE_DIR --protection passphrase",
            {"STORE_DIR": str(sessions / "private-keys")},
        ),
        cwd=REPO_ROOT,
        env=env,
        steps=[("passphrase", "synthetic-passphrase\n")],
    )
    assert init_code == 0, init_out[-2000:]
    transcript = "\n".join((
        "/help",
        "/status",
        "/why",
        "/skip",
        "/edit synthetic replacement",
        "/pause",
        "/resume",
        "/quit",
        "",
    ))
    code, output = _pty_run(
        _python_argv(PRIMARY, {"USER_ID": "synthetic-user"}),
        cwd=REPO_ROOT,
        env=env,
        steps=[("passphrase", "synthetic-passphrase\n"), (">", transcript)],
    )
    assert code == 0, output[-2500:]
    assert "Terminal controls" in output
    assert "does not satisfy a legal requirement" in output or "Skipped" in output
    assert "paused" in output.lower()
    second_code, second = _pty_run(
        _python_argv(PRIMARY, {"USER_ID": "synthetic-user"}),
        cwd=REPO_ROOT,
        env=env,
        steps=[("passphrase", "synthetic-passphrase\n"), (">", "/status\n/quit\n")],
    )
    assert second_code == 0, second[-2500:]
    assert "Restored pending question" in second or "stop_reason" in second


def test_grok47_canary_is_not_requested_without_confirm(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    command = next(item["command"] for item in _catalog()["examples"] if item["id"] == "router-live-canary-not-requested")
    completed = _run(_python_argv(command, {}), cwd=REPO_ROOT, env=_operator_env(home), timeout=60)
    assert completed.returncode == 0, completed.stderr[-2000:]
    payload = json.loads(completed.stdout)
    assert payload.get("status") == "not_requested" or payload.get("route_observation") == "not_dispatched"
    assert payload.get("complaint_data_included") is False


def test_key_status_unlock_and_rejected_passphrase_flag(tmp_path: Path) -> None:
    home = tmp_path / "home"
    store = tmp_path / "keys"
    home.mkdir()
    store.mkdir(mode=0o700)
    os.chmod(store, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    env = _operator_env(home)
    status = _run(
        _python_argv(
            "python -m complaint_generator.cli keys-status --store-dir STORE_DIR",
            {"STORE_DIR": str(store)},
        ),
        cwd=REPO_ROOT,
        env=env,
    )
    assert status.returncode == 0, status.stderr
    body = json.loads(status.stdout)
    assert body.get("raw_key_persisted") is False
    assert "passphrase" not in status.stdout.lower() or "protection" in body

    unlock = _run(
        _python_argv(
            "python -m complaint_generator.cli keys-unlock --store-dir STORE_DIR",
            {"STORE_DIR": str(store)},
        ),
        cwd=REPO_ROOT,
        env=env,
    )
    assert unlock.returncode != 0
    assert "passphrase" not in unlock.stdout or "Choose passphrase" in unlock.stdout or "unlock" in unlock.stdout

    rejected = _run(
        [sys.executable, "-m", "complaint_generator.cli", "keys-init", "--store-dir", str(store), "--passphrase", "secret"],
        cwd=REPO_ROOT,
        env=env,
    )
    assert rejected.returncode != 0
    assert "process arguments" in rejected.stderr or "process arguments" in rejected.stdout


def test_supervisor_start_status_stop_do_not_launch_without_auth(tmp_path: Path) -> None:
    home = tmp_path / "ipfs-accelerate-validation-home-intake"
    state = tmp_path / "supervisor-state"
    home.mkdir()
    state.mkdir(mode=0o700)
    env = _operator_env(home)
    replacements = {
        "REPO_ROOT": str(REPO_ROOT),
        "SPEC_PATH": str(SPEC),
        "STATE_DIR": str(state),
    }
    catalog = {item["id"]: item["command"] for item in _catalog()["examples"]}
    started = _run(_python_argv(catalog["supervisor-start"], replacements), cwd=REPO_ROOT, env=env, timeout=180)
    started_text = (started.stdout or started.stderr).strip()
    assert started_text, (started.returncode, started.stdout, started.stderr)
    decoder = json.JSONDecoder()
    try:
        payload, _end = decoder.raw_decode(started_text[started_text.find("{"):])
    except json.JSONDecodeError as exc:
        raise AssertionError(started_text[:2000]) from exc
    assert payload.get("status") in {"not_ready", "stop_incomplete", "error", "board_error", "state_error"}
    assert not (state / "launcher.json").exists() or json.loads((state / "launcher.json").read_text()).get("status") != "starting"

    status = _run(_python_argv(catalog["supervisor-status"], replacements), cwd=REPO_ROOT, env=env, timeout=180)
    status_text = (status.stdout or status.stderr).strip()
    assert "{" in status_text, (status.returncode, status.stdout, status.stderr)
    stopped = _run(_python_argv(catalog["supervisor-stop"], replacements), cwd=REPO_ROOT, env=env, timeout=60)
    stopped_text = (stopped.stdout or stopped.stderr).strip()
    stopped_payload, _end = json.JSONDecoder().raw_decode(stopped_text[stopped_text.find("{"):])
    assert stopped_payload.get("signalled") is False
    assert stopped_payload.get("status") in {"not_owned_or_stopped", "stop_incomplete", "not_ready"}


@pytest.mark.parametrize("example_id", ["keys-recover-export", "workspace-export", "supervisor-status"])
def test_documented_examples_have_no_interpreter_absolute_path(example_id: str) -> None:
    command = next(item["command"] for item in _catalog()["examples"] if item["id"] == example_id)
    assert command.startswith("python ")
    assert not command.split()[0].startswith("/")


def test_session_directory_alias_is_rejected_before_any_profile_effect(tmp_path,monkeypatch):
    from applications.complaint_cli import _LazyTerminalService
    target=tmp_path/'target';target.mkdir(mode=0o700)
    alias=tmp_path/'alias';alias.symlink_to(target,target_is_directory=True)
    monkeypatch.setenv('COMPLAINT_WORKSPACE_SESSION_DIR',str(alias))
    from applications.complaint_workspace import WorkspaceAuthorizationDenied
    before=target.stat().st_mode
    with pytest.raises(WorkspaceAuthorizationDenied):_LazyTerminalService().private_key_status()
    assert list(target.iterdir())==[]and target.stat().st_mode==before


@pytest.mark.parametrize("mode", ["grok", "local"])
@pytest.mark.parametrize("choice", ["flag", "slash"])
def test_fresh_terminal_processing_choice_is_explicit_and_case_bound(tmp_path: Path, mode: str, choice: str) -> None:
    from applications.complaint_workspace import ComplaintWorkspaceService
    home = tmp_path / "home"
    home.mkdir()
    sessions = tmp_path / "sessions"
    service = ComplaintWorkspaceService(root_dir=sessions)
    service.initialize_private_keys(protection="passphrase", passphrase="synthetic-policy-passphrase")
    service.ensure_private_case_key("synthetic-policy", "synthetic-policy")
    if mode == "local":
        service.set_privacy_policy("synthetic-policy", "grok")
    service.lock_private_keys()
    env = _operator_env(home, {"COMPLAINT_WORKSPACE_SESSION_DIR": str(sessions)})
    argv = _python_argv(PRIMARY, {"USER_ID": "synthetic-policy"})
    if choice == "flag":
        argv += ["--privacy-mode", mode]
    terminal_input = "/quit\n" if choice == "flag" else "/privacy " + mode + "\n/quit\n"
    code, output = _pty_run(argv, cwd=REPO_ROOT, env=env,
        steps=[("passphrase", "synthetic-policy-passphrase\n"), (">", terminal_input)])
    assert code == 0, output[-2000:]
    assert "synthetic-policy-passphrase" not in output
    restarted = ComplaintWorkspaceService(root_dir=sessions)
    restarted.unlock_private_keys(passphrase="synthetic-policy-passphrase")
    policy = restarted.get_privacy_policy("synthetic-policy")
    assert policy["user_id"] == policy["case_id"] == "synthetic-policy"
    assert policy["policy"]["cloud_processing_enabled"] is (mode == "grok")
    assert restarted.get_session("synthetic-policy")["session"]["intake_history"] == []
    assert not restarted.get_session("synthetic-policy")["session"].get("router_trace", {}).get("receipts")


def test_invalid_terminal_processing_choice_has_no_store_side_effects(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    sessions = tmp_path / "sessions"
    env = _operator_env(home, {"COMPLAINT_WORKSPACE_SESSION_DIR": str(sessions)})
    result = _run(_python_argv(PRIMARY, {"USER_ID": "synthetic-policy"}) + ["--privacy-mode", "invalid"], cwd=REPO_ROOT, env=env)
    assert result.returncode == 2
    assert "invalid_privacy_mode" in result.stdout
    assert not sessions.exists()


def test_documented_recovery_commands_round_trip_real_case_key(tmp_path: Path) -> None:
    from tests.test_private_workspace_portability import _stage, PASSPHRASE, RECOVERY, TENANT, CASE, PRINCIPAL, COMPLAINT, GRAPH, PROOF
    from integrations.private_storage import UserOwnedKeySession, read_private_workspace_generation
    _session, store, repository, _staged = _stage(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    env = _operator_env(home)
    catalog = {item["id"]: item["command"] for item in _catalog()["examples"]}
    recovery = tmp_path / "deliberate-recovery.cgpe"
    values = {"STORE_DIR": str(store), "TENANT_ID": TENANT, "CASE_ID": CASE, "RECOVERY_FILE": str(recovery)}
    code, output = _pty_run(_python_argv(catalog["keys-recover-export"], values), cwd=REPO_ROOT, env=env,
        steps=[("Private key passphrase", PASSPHRASE + "\n"), ("Recovery export passphrase", RECOVERY + "\n")])
    assert code == 0 and recovery.is_file(), output[-2000:]
    assert PASSPHRASE not in output and RECOVERY not in output
    assert stat.S_IMODE(recovery.stat().st_mode) == 0o600
    new_store = tmp_path / "recovered-keys"
    values["STORE_DIR"] = str(new_store)
    code, output = _pty_run(_python_argv(catalog["keys-recover-import"], values), cwd=REPO_ROOT, env=env,
        steps=[("Recovery import passphrase", RECOVERY + "\n"), ("New store passphrase", "synthetic-new-store-passphrase\n")])
    assert code == 0, output[-2000:]
    assert RECOVERY not in output and "synthetic-new-store-passphrase" not in output
    restored = UserOwnedKeySession(new_store)
    restored.unlock_passphrase("synthetic-new-store-passphrase")
    opened = read_private_workspace_generation(repository, restored, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL)
    assert (opened["complaint"], opened["fact_graph"], opened["proof"]) == (COMPLAINT, GRAPH, PROOF)


def test_documented_workspace_export_authenticates_in_a_fresh_store(tmp_path: Path) -> None:
    from tests.test_private_workspace_portability import _stage, PASSPHRASE, RECOVERY, TENANT, CASE, PRINCIPAL, COMPLAINT, GRAPH, PROOF
    from integrations.private_storage import UserOwnedKeySession, import_encrypted_workspace, read_private_workspace_generation
    _session, store, repository, _staged = _stage(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    export_dir, recovery = tmp_path / "ciphertext-export", tmp_path / "separate-recovery.cgpe"
    values = {"STORE_DIR": str(store), "TENANT_ID": TENANT, "CASE_ID": CASE, "PRINCIPAL_ID": PRINCIPAL,
        "REPOSITORY_DIR": str(repository), "EXPORT_DIR": str(export_dir), "RECOVERY_FILE": str(recovery)}
    command = next(item["command"] for item in _catalog()["examples"] if item["id"] == "workspace-export")
    code, output = _pty_run(_python_argv(command, values), cwd=REPO_ROOT, env=_operator_env(home),
        steps=[("Private key passphrase", PASSPHRASE + "\n"), ("Recovery export passphrase", RECOVERY + "\n")])
    assert code == 0 and recovery.is_file() and export_dir.is_dir(), output[-2000:]
    assert PASSPHRASE not in output and RECOVERY not in output
    assert recovery.parent != export_dir and stat.S_IMODE(recovery.stat().st_mode) == 0o600
    assert all(COMPLAINT not in path.read_bytes() for path in export_dir.rglob("*") if path.is_file())
    new_store, restored_repository = tmp_path / "fresh-keys", tmp_path / "fresh-repository"
    import_encrypted_workspace(restored_repository, export_dir, recovery, new_store,
        tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL,
        recovery_passphrase=RECOVERY, store_passphrase="synthetic-export-restore-passphrase")
    restored = UserOwnedKeySession(new_store)
    restored.unlock_passphrase("synthetic-export-restore-passphrase")
    opened = read_private_workspace_generation(restored_repository, restored, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL)
    assert (opened["complaint"], opened["fact_graph"], opened["proof"]) == (COMPLAINT, GRAPH, PROOF)
