"""Hermetic launcher ownership and actual native ingestion/config contracts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
import os
from pathlib import Path
import signal
import sys
import time
from types import SimpleNamespace

import pytest

import integrations.ipfs_accelerate.improvement_runner as runner


ROOT = Path(__file__).resolve().parents[1]
pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


@pytest.fixture(autouse=True)
def private_containerd_metadata(tmp_path, monkeypatch):
    # Real fixture directory/capacity, replacing only fixed-path discovery.
    metadata = tmp_path / "containerd_metadata"
    metadata.mkdir(mode=0o700)
    monkeypatch.setattr(runner, "_containerd_metadata_directory", lambda: metadata)


@pytest.fixture(autouse=True)
def restore_cwd(monkeypatch):
    monkeypatch.chdir(ROOT)


def _spec():
    return {
        "schema_version": "complaint-intake-improvement@1", "title": "Synthetic interview campaign",
        "provider": {"router": "ipfs_accelerate_py.llm_router", "provider": "grok_cli",
                     "model": "grok-4.7", "allow_fallback": False},
        "execution_policy": {"one_lane": True},
        "goals": [{"id": "goal.intake", "title": "Intake", "subgoals": [{"id": "sub.intake", "title": "Questions"}]}],
        "tasks": [
            {"id": "CIMP-TUI-01", "title": "Inspect terminal", "goal_id": "goal.intake", "subgoal_id": "sub.intake",
             "priority": "P0", "targets": ["tests/test_terminal_contract.py"], "depends_on": [],
             "acceptance": ["Synthetic terminal interview is characterized"],
             "validation_commands": ["python -m pytest -q tests/test_terminal_contract.py"],
             "implementation_prompt": "Create a bounded synthetic terminal behavior test."},
            {"id": "CIMP-TUI-02", "title": "Refine interview", "goal_id": "goal.intake", "subgoal_id": "sub.intake",
             "priority": "P1", "targets": ["tests/test_question_contract.py"], "depends_on": ["CIMP-TUI-01"],
             "acceptance": ["Questions update facts without inventing facts"],
             "validation_commands": ["python -m pytest -q tests/test_question_contract.py"],
             "implementation_prompt": "Verify questions against user-provided facts."},
        ],
    }


@pytest.fixture
def campaign(tmp_path):
    from integrations.ipfs_accelerate.improvement_plan import generate
    spec = tmp_path / runner.SPEC_RELATIVE
    spec.parent.mkdir(parents=True)
    spec.write_text(json.dumps(_spec()))
    # Import the native package under the real repository before isolating
    # artifact paths; no provider/daemon is instantiated by these operations.
    runner._native_modules(ROOT)
    generated = generate(spec, tmp_path)
    return tmp_path, spec, tmp_path / "state", generated


def _identity(pid=991119, argv=None):
    return {"pid": pid, "start_ticks": 123456, "boot_id": "test-boot", "ppid": 1,
            "session": pid, "process_group": pid, "argv": argv or []}


def _owner(state, identity=None):
    argv = [sys.executable, str(ROOT / "scripts/run_complaint_improvement_supervisor.py"),
            "_run", "--state-dir", str(state), "--owner-token", "test-owner"]
    identity = identity or _identity(argv=argv)
    return {"identity": identity, "argv": argv, "owner_token": "test-owner",
            "started_at": runner.time.time() - 10, "status": "starting"}


def test_explicit_environment_removes_ambient_routes_and_pins_model():
    environment = runner.campaign_environment(ROOT, {
        "PATH": "/bin", "HOME": "/preserved/user", "XAI_API_KEY": "fixture-secret",
        "IPFS_ACCELERATE_AGENT_IMPLEMENTATION_PROVIDER": "codex",
        "IPFS_ACCELERATE_AGENT_IMPLEMENTATION_FALLBACK_PROVIDER": "codex",
        "IPFS_ACCELERATE_AGENT_PROVIDER_FALLBACK_POLICY": "grok_quota_only",
        "IPFS_ACCELERATE_AGENT_IMPLEMENTATION_ROUTE_ID": "other-campaign",
        "IPFS_ACCELERATE_AGENT_PRODUCTION_PROVIDER_POLICY": "independent-review",
        "IMPLEMENTATION_DAEMON_COMMAND": "unexpected-provider", "GROK_MODEL": "old-model",
        "TODO_DAEMON_LLM_ALLOW_CROSS_PROVIDER_FALLBACK": "1",
        "IPFS_ACCELERATE_AGENT_GROK_REASONING_EFFORT": "high",
        "IPFS_ACCELERATE_AGENT_GROK_MAX_TURNS": "1000",
        runner.AUTOMATIC_RETRY_REARM_ENV: "1",
        "IPFS_ACCELERATE_AGENT_WORKTREE_SUBMODULE_PATHS": "external/ambient-unrelated",
        "IPFS_ACCELERATE_AGENT_WORKTREE_POOL_MAX_ENTRIES": "1000",
    })
    assert environment["IPFS_ACCELERATE_AGENT_IMPLEMENTATION_PROVIDER"] == "grok"
    assert environment["GROK_MODEL"] == environment["TODO_DAEMON_LLM_MODEL"] == "grok-4.7"
    assert environment["TODO_DAEMON_LLM_ALLOW_CROSS_PROVIDER_FALLBACK"] == "0"
    assert environment["TODO_DAEMON_LLM_ALLOW_LOCAL_FALLBACK"] == "0"
    assert environment["IPFS_ACCELERATE_AGENT_GROK_MAX_TURNS"] == "64"
    assert environment["IPFS_ACCELERATE_AGENT_GROK_REASONING_EFFORT"] == "low"
    assert environment[runner.AUTOMATIC_RETRY_REARM_ENV] == "1"
    assert environment["IPFS_ACCELERATE_AGENT_WORKTREE_SUBMODULE_PATHS"] == "external/ipfs_datasets_py,external/ipfs_kit_py"
    assert environment["IPFS_ACCELERATE_AGENT_WORKTREE_POOL_MAX_ENTRIES"] == "1"
    assert environment["HOME"] == "/preserved/user"
    assert environment["XAI_API_KEY"] == "fixture-secret"
    assert json.loads(environment[runner.PRIVATE_PATHS_ENV]) == list(runner._PRIVATE_PATHS)
    assert environment["PATH"].split(os.pathsep)[0] == str(Path(sys.executable).parent)
    for key in ("IMPLEMENTATION_DAEMON_COMMAND", "IPFS_ACCELERATE_AGENT_IMPLEMENTATION_ROUTE_ID",
                "IPFS_ACCELERATE_AGENT_IMPLEMENTATION_FALLBACK_PROVIDER",
                "IPFS_ACCELERATE_AGENT_PROVIDER_FALLBACK_POLICY",
                "IPFS_ACCELERATE_AGENT_PRODUCTION_PROVIDER_POLICY"):
        assert key not in environment


def test_private_exclusions_use_trusted_spec_and_coalesce_mandatory_directories():
    result = runner.campaign_environment(ROOT, {runner.PRIVATE_PATHS_ENV: '["untrusted"]'},
                                         context_exclude=["data/**", ".complaint_workspace/sessions/**", "private-audit/**"])
    paths = json.loads(result[runner.PRIVATE_PATHS_ENV])
    assert "data" in paths and ".complaint_workspace" in paths and "private-audit/**" in paths
    assert "data/**" not in paths and "untrusted" not in paths


def test_campaign_has_its_own_native_control_plane_root(tmp_path):
    result = runner.campaign_environment(ROOT, {
        runner.ORCHESTRATION_DIR_ENV: "/other/campaign",
        "IPFS_ACCELERATE_AGENT_CONTROL_DUCKDB": "/other/lane.duckdb",
        "IPFS_ACCELERATE_AGENT_QUACK_ENDPOINT": "quack://other-campaign",
    }, state_dir=tmp_path)
    assert result[runner.ORCHESTRATION_DIR_ENV] == str(tmp_path / "control-plane")
    assert "IPFS_ACCELERATE_AGENT_CONTROL_DUCKDB" not in result
    assert "IPFS_ACCELERATE_AGENT_QUACK_ENDPOINT" not in result


@pytest.mark.parametrize("value", [["/home/user/secrets"], ["../secrets"], ["**"], ["*"], "data/**"])
def test_private_exclusions_reject_unbounded_or_unconfined_values(value):
    with pytest.raises(ValueError, match="bounded"):
        runner.campaign_environment(ROOT, {}, context_exclude=value)


def test_private_policy_survives_actual_native_daemon_and_provider_environment(campaign, monkeypatch):
    supervisor, daemon = runner._native_modules(ROOT)
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import supervisor_runtime
    policy = runner.campaign_environment(ROOT, {"PATH": os.defpath})
    monkeypatch.setattr(runner.os, "environ", dict(policy))
    observations = []
    monkeypatch.setattr(supervisor_runtime.subprocess, "Popen", lambda command, **kwargs:
                        observations.append(kwargs["env"]) or SimpleNamespace(pid=991119))
    supervisor_runtime.launch_process_child(
        ["synthetic-native-daemon"], cwd=ROOT,
        env=supervisor._managed_daemon_child_environment(),
    )
    child_environment = observations[0]
    assert child_environment[runner.PRIVATE_PATHS_ENV] == policy[runner.PRIVATE_PATHS_ENV]
    assert child_environment["IPFS_ACCELERATE_AGENT_GROK_REASONING_EFFORT"] == "low"
    assert child_environment["IPFS_ACCELERATE_AGENT_GROK_MAX_TURNS"] == "64"
    assert child_environment["IPFS_ACCELERATE_AGENT_WORKTREE_POOL_MAX_ENTRIES"] == "1"
    monkeypatch.setattr(runner.os, "environ", child_environment)
    provider_environment = daemon.PortalImplementationDaemon._implementation_untrusted_process_environment()
    assert provider_environment[runner.PRIVATE_PATHS_ENV] == policy[runner.PRIVATE_PATHS_ENV]
    assert provider_environment["IPFS_ACCELERATE_AGENT_GROK_REASONING_EFFORT"] == "low"
    assert provider_environment["IPFS_ACCELERATE_AGENT_GROK_MAX_TURNS"] == "64"
    assert provider_environment["IPFS_ACCELERATE_AGENT_IMPLEMENTATION_PROVIDER"] == "grok"


def test_campaign_pool_limit_preserves_leased_worktrees_and_prunes_only_idle(tmp_path, monkeypatch):
    import subprocess

    _, native = runner._native_modules(ROOT)
    repo = tmp_path / "synthetic-repo"
    repo.mkdir()

    def git(*args):
        return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True)

    git("init", "-b", "main")
    (repo / "app.py").write_text("VALUE = 1\n")
    git("add", "app.py")
    git("-c", "user.name=Pool fixture", "-c", "user.email=pool@example.invalid",
        "commit", "-m", "Synthetic pool baseline")
    state_dir = repo / "state"
    policy = runner.campaign_environment(repo, {"PATH": os.defpath,
        "IPFS_ACCELERATE_AGENT_WORKTREE_POOL_MAX_ENTRIES": "1000"}, state_dir=state_dir)
    monkeypatch.setattr(runner.os, "environ", dict(policy))
    todo = repo / "todo.md"
    todo.write_text("# Synthetic pool fixture\n")
    daemon = native.PortalImplementationDaemon(
        todo_path=todo, state_path=state_dir / "task_state.json",
        strategy_path=state_dir / "strategy.json", events_path=state_dir / "events.jsonl",
        repo_root=repo, implement=False, use_ephemeral_worktree=True,
        worktree_root=repo / "worktrees", merge_queue_dir=state_dir / "merge-queue",
        llm_merge_resolver_command="",
    )
    pool = daemon.worktree_pool
    assert pool is not None and pool.max_entries == 1
    held = pool.acquire(cache_key="synthetic-held", base_ref="main")
    try:
        first = pool.acquire(cache_key="synthetic-first", base_ref="main")
        assert first.release()["pooled"] is True
        first_state = pool.state_root / f"{first.entry_id}.json"
        held_state = pool.state_root / f"{held.entry_id}.json"
        held_before = held_state.read_bytes()
        second = pool.acquire(cache_key="synthetic-second", base_ref="main")
        assert second.release()["pooled"] is True
        assert not first.path.exists() and not first_state.exists()
        assert second.path.is_dir()
        assert held.path.is_dir() and held_state.read_bytes() == held_before
        assert held_state.with_suffix(".lock").is_file()
        states = [json.loads(path.read_text()) for path in pool.state_root.glob("*.json")]
        assert [item["lease_token"] for item in states if item["state"] == "idle"] == [second.entry_id]
        assert [item["lease_token"] for item in states if item["state"] == "leased"] == [held.entry_id]
        state = native.PortalTaskState.load(daemon.state_path)
        assert not state.implementation_attempts and not state.implementation_attempts_by_cid
        assert not state.completed_task_ids
    finally:
        held.release(reusable=False)


def test_real_native_parser_and_config_accept_explicit_bounded_campaign(campaign):
    root, _, state, generated = campaign
    native, _ = runner._native_modules(ROOT)
    args = native.parse_args(runner.native_argv(Path(generated["board_path"]), state, "local-campaign"))
    config = native.supervisor_config_from_args(args, repo_root=root)
    assert args.implement is True
    assert args.task_prefix == "## CIMP-"
    assert args.task_source_kind == "legacy-markdown"
    assert args.authority_mode == "legacy_markdown" and args.explicit_legacy_task_source
    assert args.implementation_timeout == args.implementation_max_timeout == 900
    assert args.max_task_attempts == 3 and args.max_restarts == 5
    assert args.task_shard_count == 1 and args.task_shard_index == 0
    assert config.use_ephemeral_worktree
    assert config.merge_target_branch == "local-campaign"
    assert config.worktree_reconciliation_enabled
    assert config.worktree_reconciliation_preflight_enabled
    assert config.worktree_root == state / "worktrees"
    assert tuple(config.worktree_submodule_paths) == ("external/ipfs_datasets_py", "external/ipfs_kit_py")



def test_first_party_tasks_select_pinned_kit_wal_for_native_worktree_setup(campaign):
    _, _, state, generated = campaign
    native, daemon_module = runner._native_modules(ROOT)
    board = Path(generated["board_path"])
    args = native.parse_args(runner.native_argv(board, state, "local-campaign"))
    config = native.supervisor_config_from_args(args, repo_root=ROOT)
    environment = runner.campaign_environment(ROOT, {
        "IPFS_ACCELERATE_AGENT_WORKTREE_SUBMODULE_PATHS": "external/unrelated",
    }, state_dir=state)
    expected = ("external/ipfs_datasets_py", "external/ipfs_kit_py")
    assert tuple(args.worktree_submodule_path) == expected
    assert tuple(config.worktree_submodule_paths) == expected
    assert daemon_module.normalize_relative_path_list(
        environment["IPFS_ACCELERATE_AGENT_WORKTREE_SUBMODULE_PATHS"]
    ) == expected
    tasks = daemon_module.parse_task_file(board, task_header_prefix=runner.TASK_PREFIX)
    assert tasks and all(not task.metadata.get("submodules") for task in tasks)
    # Exercise the actual setup dependency selector without constructing or
    # starting a daemon. These first-party tasks declare no Kit output.
    daemon = object.__new__(daemon_module.PortalImplementationDaemon)
    daemon.repo_root = ROOT
    daemon.worktree_submodule_paths = config.worktree_submodule_paths
    for task in tasks:
        assert not any("external/" in output for output in task.outputs)
        assert daemon._effective_worktree_submodule_paths(task) == expected
    kit = ROOT / expected[1]
    assert (kit / ".git").exists()
    for name in ("contracts.py", "coordinator.py", "writer.py", "segments.py"):
        assert (kit / "ipfs_kit_py/core/wal" / name).is_file()


def test_native_task_parser_sees_entire_dag_and_grok_route(campaign):
    root, spec, _, generated = campaign
    from integrations.ipfs_accelerate.improvement_plan import load_spec
    result = runner._validate_board(root, Path(generated["board_path"]), load_spec(spec))
    assert result["count"] == 2 and result["completed"] == 0
    assert result["ready_task_ids"] == ["CIMP-TUI-01"]


def test_parse_task_file_keeps_hold_owner_and_receipt_without_ingestion_completion(campaign):
    root, spec_path, _, generated = campaign
    from integrations.ipfs_accelerate.improvement_plan import PLAN_RELATIVE, generate

    board = Path(generated["board_path"])
    plan = root / PLAN_RELATIVE
    text = board.read_text(encoding="utf-8")
    text = text.replace("- Status: todo\n", "- Status: in_progress\n- Manual hold: true\n- Owner: worker-7\n- Claim: claim-42\n", 1)
    text = text.replace("- Status: todo\n", "- Status: completed\n- Completion receipt: baguqeerareceiptreference\n", 1)
    board.write_text(text, encoding="utf-8")
    before_board, before_plan = board.read_bytes(), plan.read_bytes()
    result = generate(spec_path, root)
    assert board.read_bytes() == before_board
    assert plan.read_bytes() == before_plan
    assert result["receipt"]["tasks_completed_by_ingestion"] == 0
    assert result["receipt"]["execution_started"] is False
    _, daemon = runner._native_modules(ROOT)
    tasks = daemon.parse_task_file(board, task_header_prefix=runner.TASK_PREFIX)
    by_id = {task.task_id: task for task in tasks}
    assert by_id["CIMP-TUI-01"].status == "in_progress"
    assert by_id["CIMP-TUI-01"].metadata["manual hold"] == "true"
    assert by_id["CIMP-TUI-01"].metadata["owner"] == "worker-7"
    assert by_id["CIMP-TUI-01"].metadata["claim"] == "claim-42"
    assert by_id["CIMP-TUI-02"].status == "completed"
    assert by_id["CIMP-TUI-02"].metadata["completion receipt"] == "baguqeerareceiptreference"
    summary = runner._board_summary(tasks)
    assert summary["manual_hold_task_ids"] == ["CIMP-TUI-01"]
    assert summary["completed"] == 1


def test_board_validation_rejects_changed_dependency(campaign):
    root, spec, _, generated = campaign
    from integrations.ipfs_accelerate.improvement_plan import load_spec
    path = Path(generated["board_path"])
    path.write_text(path.read_text().replace("- Depends on: CIMP-TUI-01", "- Depends on: forged-task"))
    with pytest.raises(ValueError, match="references/validation differ"):
        runner._validate_board(root, path, load_spec(spec))


def test_doctor_checks_presence_without_running_auth_or_provider(campaign, monkeypatch):
    root, spec, state, _ = campaign
    monkeypatch.setenv("XAI_API_KEY", "fixture-secret")
    monkeypatch.setattr(runner.shutil, "which", lambda *a, **k: "/bin/grok")
    monkeypatch.setattr(runner, "_private_runtime_checks", lambda *a: {"ready": True})
    # The local Git size observation is tested with real synthetic repositories
    # below; this presence-only contract keeps all process dispatch forbidden.
    capacity_observations = []
    monkeypatch.setattr(runner, "_worktree_capacity", lambda *a: capacity_observations.append(a) or {"sufficient": None})
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: pytest.fail("doctor spawned a provider/process"))
    result = runner.doctor(root, spec, state, merge_target="local-campaign")
    assert result["status"] == "ready" and result["paid_calls"] == 0
    assert result["auth_validated"] is False
    assert result["native_config_validated"]
    assert capacity_observations == [(root, state / "worktrees")]
    assert not state.exists()


def test_doctor_rejects_auth_provider_command_without_forwardable_credentials(campaign, monkeypatch):
    root, spec, state, _ = campaign
    for key in ("XAI_API_KEY", "ipfs_accelerate_py_XAI_API_KEY", "IPFS_ACCELERATE_PY_XAI_API_KEY", "IPFS_DATASETS_PY_XAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GROK_HOME", str(root / "empty-auth-home"))
    monkeypatch.setenv("GROK_AUTH_PROVIDER_COMMAND", "do-not-execute-this")
    monkeypatch.setattr(runner.shutil, "which", lambda *a, **k: "/bin/grok")
    monkeypatch.setattr(runner, "_private_runtime_checks", lambda *a: {"ready": True})
    result = runner.doctor(root, spec, state, merge_target="local-campaign")
    assert result["status"] == "not_ready" and not result["auth_material_present"]
    assert result["auth_provider_command_supported"] is False


def test_privacy_preflight_rejects_native_without_enforcement(campaign, monkeypatch):
    from ipfs_accelerate_py.agent_supervisor.runtime import grok_cli_runner
    monkeypatch.setattr(grok_cli_runner, "GROK_PRIVATE_PATHS_VERSION", 0, raising=False)
    result = runner._private_runtime_checks(ROOT, runner.campaign_environment(ROOT))
    assert not result["ready"] and not result["native_enforcement_available"]


def test_preflight_rejects_ignored_reasoning_configuration(campaign, monkeypatch):
    from ipfs_accelerate_py.agent_supervisor.runtime import grok_cli_runner
    monkeypatch.delattr(grok_cli_runner, "GROK_REASONING_EFFORT_ENV", raising=False)
    result = runner._private_runtime_checks(ROOT, runner.campaign_environment(ROOT))
    assert not result["ready"]
    assert result["reason"] == "native_reasoning_effort_control_unavailable"



def test_preflight_rejects_native_that_ignores_automatic_budget_reset_policy(campaign, monkeypatch):
    _, native = runner._native_modules(ROOT)
    monkeypatch.delattr(native, "AUTOMATIC_RETRY_REARM_ENV", raising=False)
    result = runner._private_runtime_checks(ROOT, runner.campaign_environment(ROOT))
    assert not result["ready"]
    assert result["reason"] == "native_retry_budget_control_unavailable"

def test_privacy_preflight_validates_policy_and_bounded_docker_readiness(campaign, monkeypatch):
    from ipfs_accelerate_py.agent_supervisor.runtime import grok_cli_runner
    monkeypatch.setattr(grok_cli_runner, "GROK_PRIVATE_PATHS_VERSION", 1, raising=False)
    monkeypatch.setattr(grok_cli_runner, "validate_grok_private_path_patterns", lambda raw: tuple(json.loads(raw)), raising=False)
    resolved = []
    monkeypatch.setattr(grok_cli_runner, "_grok_private_workspace_paths",
                        lambda **kwargs: resolved.append(kwargs) or (), raising=False)
    monkeypatch.setattr(grok_cli_runner, "_docker_isolation_binary", lambda: "/usr/bin/docker")
    monkeypatch.setattr(grok_cli_runner, "_ordinary_task_toolchain_image_profile", lambda: ("sha256:qualified", "amd64", "label"), raising=False)
    monkeypatch.setattr(runner.platform, "machine", lambda: "x86_64")
    calls = []
    monkeypatch.setattr(grok_cli_runner, "_docker_isolation_image_id", lambda binary, **kwargs:
                        calls.append((binary, kwargs)) or "sha256:base")
    monkeypatch.setattr(grok_cli_runner, "_docker_ordinary_task_toolchain_image_id", lambda binary, **kwargs:
                        calls.append((binary, kwargs)) or "sha256:qualified")
    result = runner._private_runtime_checks(ROOT, runner.campaign_environment(ROOT))
    assert result["ready"] and result["docker_ready"]
    assert resolved[0]["workspace"] == ROOT
    assert result["ordinary_task_image_id"] == "sha256:qualified"
    assert len(calls) == 2 and calls[0][0] == "/usr/bin/docker"
    assert calls[0][1]["docker_config"] == calls[1][1]["docker_config"]


@pytest.mark.parametrize("ordinary,architecture,reason", [
    ("", "amd64", "qualified_ordinary_task_image_unavailable"),
    ("sha256:qualified", "arm64", "ordinary_task_image_architecture_mismatch"),
])
def test_privacy_preflight_rejects_missing_or_wrong_architecture_image(campaign, monkeypatch, ordinary, architecture, reason):
    from ipfs_accelerate_py.agent_supervisor.runtime import grok_cli_runner
    monkeypatch.setattr(grok_cli_runner, "GROK_PRIVATE_PATHS_VERSION", 1, raising=False)
    monkeypatch.setattr(grok_cli_runner, "validate_grok_private_path_patterns", lambda raw: tuple(json.loads(raw)), raising=False)
    monkeypatch.setattr(grok_cli_runner, "_grok_private_workspace_paths", lambda **kwargs: (), raising=False)
    monkeypatch.setattr(grok_cli_runner, "_docker_isolation_binary", lambda: "/usr/bin/docker")
    monkeypatch.setattr(grok_cli_runner, "_docker_isolation_image_id", lambda *a, **k: "sha256:base")
    monkeypatch.setattr(grok_cli_runner, "_docker_ordinary_task_toolchain_image_id", lambda *a, **k: ordinary)
    monkeypatch.setattr(grok_cli_runner, "_ordinary_task_toolchain_image_profile", lambda: ("sha256:qualified", architecture, "label"), raising=False)
    monkeypatch.setattr(runner.platform, "machine", lambda: "x86_64")
    result = runner._private_runtime_checks(ROOT, runner.campaign_environment(ROOT))
    assert not result["ready"] and result["reason"] == reason


@pytest.mark.parametrize("changed", ["start_ticks", "boot_id", "argv", "session"])
def test_ownership_rejects_reused_pid_or_changed_command(tmp_path, monkeypatch, changed):
    record = _owner(tmp_path)
    current = dict(record["identity"])
    current[changed] = ["unrelated-process"] if changed == "argv" else "different"
    monkeypatch.setattr(runner, "process_identity", lambda pid: current)
    assert runner.owns_process(record) is False


def test_real_proc_identity_reads_own_process():
    identity = runner.process_identity(os.getpid())
    assert identity and identity["pid"] == os.getpid()
    assert identity["start_ticks"] > 0 and identity["boot_id"] and identity["argv"]


def _full_owner(root, spec, state, plan_id):
    token = "test-owner"
    argv = [sys.executable, str(root / "scripts/run_complaint_improvement_supervisor.py"), "_run",
            "--repo-root", str(root), "--spec", str(spec), "--state-dir", str(state),
            "--owner-token", token, "--merge-target", "campaign"]
    return {"schema_version": "complaint-improvement-launcher@1", "identity": _identity(argv=argv),
            "argv": argv, "owner_token": token, "started_at": runner.time.time() - 30,
            "status": "starting", "repo_root": str(root), "spec_path": str(spec),
            "state_dir": str(state), "merge_target": "campaign",
            "board_path": str(root / "docs/task_boards/complaint_intake_task_board.md"),
            "plan_id": plan_id, "provider": "grok_cli", "model": "grok-4.7", "allow_fallback": False}


def _shutdown_receipt(record, **overrides):
    receipt = {"schema": "complaint-improvement-container-shutdown@1", "repo_root": record["repo_root"],
               "state_dir": record["state_dir"], "plan_id": record["plan_id"], "started_at": record["started_at"],
               "owner_token_sha256": runner.hashlib.sha256(record["owner_token"].encode()).hexdigest(),
               "quiesced": True, "status": "stopped", "completion_authority": False,
               "provider_callback_settled": False, "attempt_refunded": False}
    receipt.update(overrides)
    return receipt


def _refuse_effects(monkeypatch):
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: pytest.fail("launch"))
    monkeypatch.setattr(runner, "_signal_birth", lambda *a, **k: pytest.fail("signal"))
    monkeypatch.setattr(runner, "prepare", lambda *a, **k: pytest.fail("prepare"))


class _AdmissionDocker:
    """Execute real admission/old shutdown logic against inert Docker transport."""

    identifier = "a" * 64
    image = "sha256:" + "b" * 64

    def __init__(self, row=None, failure=None):
        self.rows = {} if row is None else {self.identifier: row}
        self.failure = failure
        self.calls = []
        self.effects = []

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        assert argv[0] == "/trusted/native/docker"
        assert "--host=unix:///var/run/docker.sock" in argv
        assert "--config" in argv
        assert kwargs["stdin"] is runner.subprocess.DEVNULL
        assert kwargs["env"] == {"PATH": "/usr/bin", "HOME": "/nonexistent"}
        assert kwargs["timeout"] > 0
        offset = argv.index("--config") + 2
        operation, args = argv[offset], argv[offset + 1:]
        if self.failure == "timeout":
            raise runner.subprocess.TimeoutExpired(argv, kwargs["timeout"])
        if operation == "ps":
            identifiers = list(self.rows)
            if self.failure == "inventory":
                return SimpleNamespace(returncode=1, stdout="", stderr="unavailable")
            if self.failure == "duplicate":
                identifiers += identifiers
            elif self.failure == "invalid_id":
                identifiers = ["short-untrusted-id"]
            elif self.failure == "oversized":
                identifiers = [f"{index:064x}" for index in range(129)]
            return SimpleNamespace(returncode=0, stdout="\n".join(identifiers), stderr="")
        if operation == "inspect":
            if self.failure == "inspection" or args[-1] not in self.rows:
                return SimpleNamespace(returncode=1, stdout="", stderr="unavailable")
            value = "not-json" if self.failure == "malformed" else json.dumps(self.rows[args[-1]])
            return SimpleNamespace(returncode=0, stdout=value, stderr="")
        self.effects.append((operation, args[-1]))
        if operation == "stop":
            self.rows[args[-1]]["State"].update(Running=False, Pid=0, Status="exited")
        elif operation == "rm":
            self.rows.pop(args[-1], None)
        else:
            pytest.fail("unexpected Docker effect")
        return SimpleNamespace(returncode=0, stdout="", stderr="")


def _admission_transport(monkeypatch, row=None, *, failure=None):
    from integrations.ipfs_accelerate import improvement_shutdown as shutdown
    fake = _AdmissionDocker(row, failure)
    runtime = SimpleNamespace(_docker_isolation_binary=lambda: "/trusted/native/docker",
                              _docker_ordinary_task_toolchain_image_id=lambda *a, **k: fake.image,
                              _docker_control_env=lambda: {"PATH": "/usr/bin", "HOME": "/nonexistent"})
    monkeypatch.setattr(shutdown, "_native_runtime", lambda: runtime)
    monkeypatch.setattr(runner, "_admission_docker_runtime", lambda: runtime)
    monkeypatch.setattr(runner.subprocess, "run", fake)
    return fake


def _admission_fixture(campaign, monkeypatch, *, row_kind="live", failure=None):
    from integrations.ipfs_accelerate import improvement_shutdown as shutdown
    root, spec, state, generated = campaign
    state.mkdir(mode=0o700)
    record = _full_owner(root, spec, state, generated["receipt"]["plan_id"])
    record.update(status="stopped", board_path=str(root / "docs/task_boards/complaint_intake_task_board.md"))
    runner._atomic_json(state / "launcher.json", record)
    runner._atomic_json(state / "container_shutdown.json", _shutdown_receipt(record))
    runner._atomic_json(state / "complaint_intake_supervisor_status.json", {
        "status": "stopped", "repo_root": str(root), "supervisor_pid": record["identity"]["pid"],
        "updated_at": datetime.now(timezone.utc).isoformat(), "managed_daemon_cleanup": {"quiesced": True},
    })
    workspace = state / "worktrees" / "workspace_admission_01"
    workspace.mkdir(parents=True, mode=0o700)
    created = datetime.fromtimestamp(record["started_at"] + 5, timezone.utc).isoformat()
    event = {"type": "implementation_started", "timestamp": created,
             "event_id": "sha256:" + "c" * 64, "canonical_task_cid": "b" + "a" * 50,
             "task_id": "CIMP-TUI-01", "attempt": 1, "worktree_path": str(workspace)}
    (state / "complaint_intake_events.jsonl").write_text(json.dumps(event) + "\n")
    row = {"Id": _AdmissionDocker.identifier, "Image": _AdmissionDocker.image, "Created": created,
           "Name": "/ipfs-accelerate-grok-123-" + "d" * 32, "WorkingDir": str(workspace),
           "Label": "true", "Mounts": [{"Type": "bind", "Source": str(workspace),
                                           "Destination": str(workspace), "RW": True}],
           "State": {"Running": True, "Pid": 991121, "Status": "running", "Restarting": False, "Paused": False}}
    if row_kind == "unknown":
        row["State"]["Running"] = "false"
    elif row_kind == "stopped":
        row["State"].update(Running=False, Pid=0, Status="exited")
    elif row_kind == "ancestor":
        row["WorkingDir"] = "/unrelated/workspace"
        row["Mounts"][0]["Source"] = str(state)
    elif row_kind == "unrelated":
        row["WorkingDir"] = str(root.parent / "unrelated-campaign" / "workspace_01")
        row["Mounts"][0]["Source"] = row["WorkingDir"]
    fake = _admission_transport(monkeypatch, None if row_kind == "empty" else row, failure=failure)
    monkeypatch.setattr(runner, "process_identity", lambda _pid: None)
    monkeypatch.setattr(runner, "_signal_birth", lambda *a, **k: pytest.fail("admission signalled owner"))
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: pytest.fail("admission launched provider"))
    prepared = []
    monkeypatch.setattr(runner, "prepare", lambda *a: prepared.append(True) or {"board_path": record["board_path"]})
    monkeypatch.setattr(runner, "doctor", lambda *a, **k: {"status": "not_ready"})
    return root, spec, state, record, fake, prepared


@pytest.mark.parametrize("kind,failure", [("live", None), ("unknown", None), ("stopped", None),
                         ("ancestor", None), ("live", "inspection"), ("live", "malformed"), ("live", "timeout"),
                         ("live", "inventory"), ("live", "duplicate"), ("live", "invalid_id"), ("live", "oversized")])
def test_start_observes_real_container_seam_without_stopping_or_rewriting(campaign, monkeypatch, kind, failure):
    root, spec, state, record, fake, prepared = _admission_fixture(campaign, monkeypatch, row_kind=kind, failure=failure)
    originals = {name: (state / name).read_bytes() for name in ("launcher.json", "container_shutdown.json", "complaint_intake_events.jsonl")}
    result = runner.start(root, spec, state)
    assert fake.effects == [], "start must not stop or remove a live/unknown/stopped orphan"
    assert result["status"] == "stop_incomplete" and result["signalled"] is False
    assert not prepared
    assert all((state / name).read_bytes() == raw for name, raw in originals.items())


def test_missing_owner_cannot_hide_a_live_container_from_start(campaign, monkeypatch):
    root, spec, state, record, fake, prepared = _admission_fixture(campaign, monkeypatch)
    (state / "launcher.json").unlink()
    result = runner.start(root, spec, state)
    assert result["status"] == "stop_incomplete"
    assert not prepared and not fake.effects and fake.calls
    assert not (state / "launcher.json").exists()


def test_dead_mismatched_spec_refuses_before_container_observation(campaign, monkeypatch):
    root, spec, state, record, fake, prepared = _admission_fixture(campaign, monkeypatch)
    other_spec = spec.with_name("different-campaign.json")
    other_spec.write_bytes(spec.read_bytes())
    originals = {name: (state / name).read_bytes() for name in ("launcher.json", "container_shutdown.json")}
    result = runner.start(root, other_spec, state)
    assert result["status"] == "stop_incomplete" and not fake.calls and not fake.effects and not prepared
    assert all((state / name).read_bytes() == raw for name, raw in originals.items())


@pytest.mark.parametrize("kind", ["empty", "unrelated"])
def test_real_empty_or_unrelated_inventory_preserves_shutdown_evidence(campaign, monkeypatch, kind):
    root, spec, state, record, fake, prepared = _admission_fixture(campaign, monkeypatch, row_kind=kind)
    original = (state / "container_shutdown.json").read_bytes()
    result = runner.start(root, spec, state)
    assert result["status"] == "not_ready" and prepared == [True]
    assert fake.calls and not fake.effects
    assert (state / "container_shutdown.json").read_bytes() == original


@pytest.mark.parametrize("changed", [None, "container_id", "created", "image_id", "workspace", "removed", "quiesced"])
def test_only_exact_previously_retained_stopped_container_can_admit(campaign, monkeypatch, changed):
    root, spec, state, record, fake, prepared = _admission_fixture(campaign, monkeypatch, row_kind="stopped")
    row = fake.rows[fake.identifier]
    item = {"container_id": row["Id"], "created": row["Created"], "image_id": row["Image"],
            "workspace": row["WorkingDir"], "quiesced": True, "removed": False}
    if changed:
        item[changed] = not item[changed] if isinstance(item[changed], bool) else "different"
    runner._atomic_json(state / "container_shutdown.json", _shutdown_receipt(record, containers=[item]))
    original = (state / "container_shutdown.json").read_bytes()
    result = runner.start(root, spec, state)
    assert result["status"] == ("not_ready" if changed is None else "stop_incomplete")
    assert prepared == ([True] if changed is None else [])
    assert not fake.effects and fake.calls
    assert (state / "container_shutdown.json").read_bytes() == original


def test_same_birth_changed_command_never_acquires_admission(campaign, monkeypatch):
    root, spec, state, record, fake, prepared = _admission_fixture(campaign, monkeypatch, row_kind="empty")
    changed = {**record["identity"], "argv": ["unrelated-command"]}
    monkeypatch.setattr(runner, "process_identity", lambda pid: changed if pid == changed["pid"] else None)
    result = runner.start(root, spec, state)
    assert result["status"] == "stop_incomplete" and not prepared and not fake.calls and not fake.effects


@pytest.mark.parametrize("artifact", ["launcher.json", "container_shutdown.json"])
def test_receipt_change_during_inventory_refuses_without_replacing_it(campaign, monkeypatch, artifact):
    root, spec, state, record, fake, prepared = _admission_fixture(campaign, monkeypatch, row_kind="empty")
    original_run = runner.subprocess.run
    changed = (state / artifact).read_bytes().replace(b"test-owner", b"new--owner")
    if changed == (state / artifact).read_bytes():
        changed = changed.replace(b'"quiesced": true', b'"quiesced": false')

    def observe(*args, **kwargs):
        result = original_run(*args, **kwargs)
        (state / artifact).write_bytes(changed)
        return result

    monkeypatch.setattr(runner.subprocess, "run", observe)
    result = runner.start(root, spec, state)
    assert result["status"] == "stop_incomplete" and not prepared and not fake.effects
    assert (state / artifact).read_bytes() == changed


def test_duplicate_start_returns_existing_owned_process(tmp_path, monkeypatch):
    record = _owner(tmp_path)
    runner._atomic_json(tmp_path / "launcher.json", record)
    child = {**_identity(pid=991120), "ppid": record["identity"]["pid"]}
    monkeypatch.setattr(runner, "process_identity", lambda pid: record["identity"] if pid == record["identity"]["pid"] else child if pid == 991120 else None)
    monkeypatch.setattr(runner, "prepare", lambda *a: pytest.fail("duplicate recompiled campaign"))
    assert runner.start(ROOT, ROOT / runner.SPEC_RELATIVE, tmp_path)["status"] == "already_running"


def test_start_spawns_detached_but_reports_starting_not_running(tmp_path, monkeypatch):
    _admission_transport(monkeypatch)
    observations = {}
    current = {}
    monkeypatch.setattr(runner, "process_identity", lambda pid: current.get(pid))
    monkeypatch.setattr(runner, "prepare", lambda *a: {"board_path": "/board.md"})
    monkeypatch.setattr(runner, "doctor", lambda *a: {"status": "ready", "merge_target": "campaign", "native_plan_id": "plan-1"})
    def spawn(argv, **kwargs):
        observations.update(kwargs)
        current[991119] = _identity(argv=argv)
        return SimpleNamespace(pid=991119, poll=lambda: None)
    monkeypatch.setattr(runner.subprocess, "Popen", spawn)
    result = runner.start(ROOT, ROOT / runner.SPEC_RELATIVE, tmp_path)
    assert result["status"] == "starting" and result["progress_verified"] is False
    assert observations["start_new_session"] is True
    assert observations["stdin"] == runner.subprocess.DEVNULL
    assert observations["cwd"] == ROOT and observations["close_fds"] is True
    assert runner.owns_process(runner._read_json(tmp_path / "launcher.json"))


@pytest.mark.parametrize("field", ["repo_root", "spec_path", "plan_id", "state_dir"])
def test_live_receipt_mismatch_cannot_reuse_or_signal(campaign, monkeypatch, field):
    root, spec, state, generated = campaign
    state.mkdir(mode=0o700)
    record = _full_owner(root, spec, state, generated["receipt"]["plan_id"])
    record[field] = "/unrelated/campaign" if field != "plan_id" else "another-plan"
    runner._atomic_json(state / "launcher.json", record)
    original = (state / "launcher.json").read_bytes()
    monkeypatch.setattr(runner, "process_identity", lambda pid: record["identity"] if pid == record["identity"]["pid"] else None)
    _refuse_effects(monkeypatch)
    result = runner.start(root, spec, state)
    assert result["status"] == "stop_incomplete" and result["signalled"] is False
    assert result["reason"] == "live_campaign_mismatch"
    assert (state / "launcher.json").read_bytes() == original


@pytest.mark.parametrize("proof", ["missing", "stale", "unknown", "live_container"])
def test_dead_full_receipt_without_closure_cannot_launch_or_overwrite(campaign, monkeypatch, proof):
    root, spec, state, record, fake, prepared = _admission_fixture(
        campaign, monkeypatch, row_kind="live" if proof == "live_container" else "empty",
        failure="inspection" if proof == "unknown" else None)
    # An inspection error requires a visible container, rather than an empty
    # successful inventory which legitimately needs no per-container query.
    if proof == "unknown":
        fake.rows[fake.identifier] = {"Id": fake.identifier}
    original = (state / "launcher.json").read_bytes()
    if proof == "missing":
        (state / "container_shutdown.json").unlink()
    elif proof == "stale":
        runner._atomic_json(state / "container_shutdown.json", _shutdown_receipt(record, started_at=record["started_at"] - 5))
    evidence = (state / "container_shutdown.json").read_bytes() if proof != "missing" else None
    _refuse_effects(monkeypatch)
    result = runner.start(root, spec, state)
    assert result["status"] == "stop_incomplete" and result["signalled"] is False
    assert not prepared and not fake.effects
    assert (state / "launcher.json").read_bytes() == original
    if proof in {"missing", "stale"}:
        assert result["reason"] == "shutdown_proof_unverified" and fake.calls == []
    else:
        assert result["reason"] == "container_closure_unverified" and fake.calls
    if evidence is not None:
        assert (state / "container_shutdown.json").read_bytes() == evidence


def test_exact_quiesced_receipt_permits_one_detached_launch(campaign, monkeypatch):
    root, spec, state, record, fake, prepared = _admission_fixture(campaign, monkeypatch, row_kind="empty")
    evidence = (state / "container_shutdown.json").read_bytes()
    current = {}
    monkeypatch.setattr(runner, "process_identity", lambda pid: current.get(pid))
    monkeypatch.setattr(runner, "doctor", lambda *a, **k: {"status": "ready", "merge_target": "campaign", "native_plan_id": record["plan_id"]})
    observations = {}

    def spawn(argv, **kwargs):
        observations.update(kwargs)
        current[991119] = _identity(argv=argv)
        return SimpleNamespace(pid=991119, poll=lambda: None)

    monkeypatch.setattr(runner.subprocess, "Popen", spawn)
    result = runner.start(root, spec, state)
    assert prepared == [True] and fake.calls and not fake.effects
    assert result["status"] == "starting" and result["progress_verified"] is False
    assert observations["stdin"] is runner.subprocess.DEVNULL and observations["cwd"] == root
    assert observations["start_new_session"] is True
    retained = runner._read_json(state / "launcher.json")
    assert retained["owner_token"] != record["owner_token"]
    assert retained["repo_root"] == str(root) and retained["plan_id"] == record["plan_id"]
    assert runner.owns_process(retained)
    assert (state / "container_shutdown.json").read_bytes() == evidence


def test_duplicate_start_and_pid_reuse_preserve_unrelated_campaign(campaign, monkeypatch):
    root, spec, state, generated = campaign
    state.mkdir(mode=0o700)
    record = _full_owner(root, spec, state, generated["receipt"]["plan_id"])
    runner._atomic_json(state / "launcher.json", record)
    unrelated = campaign[0] / "unrelated-campaign"
    unrelated.mkdir(mode=0o700)
    runner._atomic_json(unrelated / "launcher.json", _owner(unrelated))
    unrelated_bytes = (unrelated / "launcher.json").read_bytes()
    owned_bytes = (state / "launcher.json").read_bytes()
    monkeypatch.setattr(runner, "process_identity", lambda pid: record["identity"] if pid == record["identity"]["pid"] else None)
    _refuse_effects(monkeypatch)
    assert runner.start(root, spec, state)["status"] == "already_running"
    reused = {**record["identity"], "start_ticks": record["identity"]["start_ticks"] + 1, "argv": ["unrelated-process"]}
    monkeypatch.setattr(runner, "process_identity", lambda pid: reused if pid == record["identity"]["pid"] else None)
    result = runner.start(root, spec, state)
    assert result["status"] == "stop_incomplete" and result["signalled"] is False
    assert (state / "launcher.json").read_bytes() == owned_bytes
    assert (unrelated / "launcher.json").read_bytes() == unrelated_bytes


def test_unready_start_never_launches(tmp_path, monkeypatch):
    _admission_transport(monkeypatch)
    monkeypatch.setattr(runner, "prepare", lambda *a: {})
    monkeypatch.setattr(runner, "doctor", lambda *a: {"status": "not_ready"})
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: pytest.fail("unready launch"))
    assert runner.start(ROOT, ROOT / runner.SPEC_RELATIVE, tmp_path)["status"] == "not_ready"


def test_stop_does_not_signal_recycled_pid_or_modify_manual_board(tmp_path, monkeypatch):
    record = _owner(tmp_path)
    runner._atomic_json(tmp_path / "launcher.json", record)
    changed = {**record["identity"], "start_ticks": 123457}
    monkeypatch.setattr(runner, "process_identity", lambda pid: changed)
    monkeypatch.setattr(runner, "_signal_birth", lambda *a: pytest.fail("signalled unrelated PID"))
    original = (tmp_path / "launcher.json").read_bytes()
    result = runner.stop(tmp_path)
    assert result["status"] == "not_owned_or_stopped" and not result["signalled"]
    assert (tmp_path / "launcher.json").read_bytes() == original


def test_stop_signals_only_owned_root_and_captured_births(tmp_path, monkeypatch):
    record = _owner(tmp_path)
    runner._atomic_json(tmp_path / "launcher.json", record)
    child = _identity(pid=991120)
    current = {record["identity"]["pid"]: record["identity"], child["pid"]: child}
    monkeypatch.setattr(runner, "process_identity", lambda pid: current.get(pid))
    monkeypatch.setattr(runner, "_descendants", lambda root: [child])
    signals = []
    def send(identity, signum):
        signals.append((identity["pid"], signum))
        current.pop(identity["pid"], None)
        return True
    monkeypatch.setattr(runner, "_signal_birth", send)
    result = runner.stop(tmp_path, timeout=0)
    assert result["status"] == "stopped" and result["manual_holds_preserved"]
    assert signals[0] == (991119, signal.SIGTERM)
    assert all(pid in {991119, 991120} for pid, _ in signals)


def _status_fixture(campaign, monkeypatch, *, native_state=None, board=None, heartbeat=True):
    root, spec, state, _ = campaign
    state.mkdir()
    record = _owner(state)
    runner._atomic_json(state / "launcher.json", record)
    child = {**_identity(pid=991120), "ppid": record["identity"]["pid"]}
    monkeypatch.setattr(runner, "process_identity", lambda pid: record["identity"] if pid == record["identity"]["pid"] else child if pid == 991120 else None)
    if native_state is not None:
        runner._atomic_json(state / f"{runner.STATE_PREFIX}_task_state.json", native_state)
    if heartbeat:
        runner._atomic_json(state / f"{runner.STATE_PREFIX}_supervisor_status.json", {
            "status": "running", "supervisor_pid": record["identity"]["pid"],
            "daemon_pid": 991120, "daemon_pid_alive": True,
        })
    if board is not None:
        monkeypatch.setattr(runner, "_validate_board", lambda *a: board)
    return root, spec, state, record


def test_status_does_not_promote_popen_to_progress(campaign, monkeypatch):
    root, spec, state, _ = _status_fixture(campaign, monkeypatch, heartbeat=False)
    result = runner.status(root, spec, state)
    assert result["status"] == "starting" and not result["progress_verified"]


def test_status_observes_current_native_task_claim(campaign, monkeypatch):
    root, spec, state, _ = _status_fixture(campaign, monkeypatch, native_state={
        "active_task_id": "CIMP-TUI-01", "implementation_in_progress": True,
        "active_phase": "implementation", "active_attempt": 1,
    })
    result = runner.status(root, spec, state)
    assert result["status"] == "active" and result["claim_progress_verified"]
    assert result["provider_execution_verified"] is False and result["progress_verified"] is False
    assert result["native_state"]["active_task_id"] == "CIMP-TUI-01"
    assert result["completion_authority"] is False


@pytest.mark.parametrize("executing,expected", [(False, "selected"), (True, "active")])
def test_status_never_uses_previous_attempt_log_for_new_claim(campaign, monkeypatch, executing, expected):
    stamp = datetime.now(timezone.utc).isoformat()
    root, spec, state, _ = _status_fixture(campaign, monkeypatch, native_state={
        "active_task_id": "CIMP-TUI-01", "active_attempt": 0,
        "active_phase": "", "active_task_started_at": stamp,
        "implementation_in_progress": executing,
    })
    old_log = state / "attempt-1.log"
    old_log.write_text("previous timed-out attempt\n")
    old = runner.time.time() - runner.STALL_SECONDS - 120
    os.utime(old_log, (old, old))
    path = state / f"{runner.STATE_PREFIX}_task_state.json"
    payload = json.loads(path.read_text())
    payload["last_implementation_log_path"] = str(old_log)
    runner._atomic_json(path, payload)
    result = runner.status(root, spec, state)
    assert result["status"] == expected
    assert result["claim_progress_verified"] and not result["provider_execution_verified"]


def test_status_bounds_selected_claim_without_worker(campaign, monkeypatch):
    stamp = datetime.fromtimestamp(runner.time.time() - runner.STALL_SECONDS - 10, timezone.utc).isoformat()
    root, spec, state, _ = _status_fixture(campaign, monkeypatch, native_state={
        "active_task_id": "CIMP-TUI-01", "active_attempt": 0,
        "active_phase": "", "active_task_started_at": stamp,
        "implementation_in_progress": False,
    })
    assert runner.status(root, spec, state)["status"] == "no_progress"


def test_status_still_detects_stale_current_execution_log(campaign, monkeypatch):
    stamp = datetime.fromtimestamp(runner.time.time() - runner.STALL_SECONDS - 20, timezone.utc).isoformat()
    root, spec, state, _ = _status_fixture(campaign, monkeypatch, native_state={
        "active_task_id": "CIMP-TUI-01", "active_attempt": 2,
        "active_phase": "implementing", "active_task_started_at": stamp,
        "implementation_in_progress": True,
    })
    log = state / "attempt-2.log"
    log.write_text("current stalled attempt\n")
    old = runner.time.time() - runner.STALL_SECONDS - 10
    os.utime(log, (old, old))
    path = state / f"{runner.STATE_PREFIX}_task_state.json"
    payload = json.loads(path.read_text())
    payload["active_log_path"] = str(log)
    runner._atomic_json(path, payload)
    assert runner.status(root, spec, state)["status"] == "stalled"


def test_status_reads_real_native_duckdb_row_without_json_mirror(campaign, monkeypatch):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import portal_task_state_control_plane as plane
    root, spec, state, _ = _status_fixture(campaign, monkeypatch)
    path = state / f"{runner.STATE_PREFIX}_task_state.json"
    monkeypatch.setenv(runner.ORCHESTRATION_DIR_ENV, str(state / "control-plane"))
    stamp = datetime.now(timezone.utc).isoformat()
    plane.save_portal_task_state(path.stem, {
        "active_task_id": "CIMP-TUI-01", "heartbeat_at": stamp,
        "active_task_started_at": stamp, "implementation_in_progress": True,
    }, state_path=path)
    database = plane.task_state_authority_file(path)
    assert not path.exists()
    result = runner.status(root, spec, state)
    assert result["status"] == "active" and result["claim_progress_verified"]
    assert result["native_state_source"]["source"] == "native_control_plane"
    assert result["native_state_source"]["authority_path"] == str(database)
    assert not result["provider_execution_verified"]


def test_native_observer_creates_no_catalog_or_legacy_migration(campaign, monkeypatch):
    root, _, state, _ = campaign
    state.mkdir()
    account = root / "isolated-account"
    legacy = account / ".local/state/ipfs_accelerate_py/legacy.duckdb"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"synthetic-unmigrated-catalog")
    monkeypatch.setenv("HOME", str(account))
    payload, source = runner._read_native_state(root, state / f"{runner.STATE_PREFIX}_task_state.json")
    assert not payload and not list(state.iterdir())
    assert source["authority_path"] is None
    assert legacy.read_bytes() == b"synthetic-unmigrated-catalog"


def test_native_observer_deadline_is_bounded(campaign, monkeypatch):
    root, _, state, _ = campaign
    started = time.monotonic()
    payload, _ = runner._read_native_state(root, state / "state.json", timeout_seconds=0.0001)
    assert payload["read_error"] == "native_state_read_timeout"
    assert time.monotonic() - started < 2


@pytest.mark.parametrize("native_status,child_alive,expected", [
    ("failed", True, "daemon_failed"), ("running", False, "daemon_failed"),
    ("recycling", False, "recycling"),
])
def test_status_honors_actual_native_heartbeat_and_child_liveness(campaign, monkeypatch, native_status, child_alive, expected):
    root, spec, state, _ = _status_fixture(campaign, monkeypatch, native_state={"active_task_id": "CIMP-TUI-01"})
    heartbeat_path = state / f"{runner.STATE_PREFIX}_supervisor_status.json"
    heartbeat = json.loads(heartbeat_path.read_text())
    heartbeat.update(status=native_status, daemon_pid_alive=child_alive)
    runner._atomic_json(heartbeat_path, heartbeat)
    assert runner.status(root, spec, state)["status"] == expected


@pytest.mark.parametrize("native_status,age,expected", [
    ("agentic_maintenance_started", 10, "starting"),
    ("agentic_maintenance_completed", 10, "starting"),
    ("agentic_maintenance_failed", 10, "daemon_failed"),
    ("agentic_maintenance_started", 100, "daemon_failed"),
])
def test_status_bounds_native_startup_maintenance_without_child(campaign, monkeypatch, native_status, age, expected):
    root, spec, state, record = _status_fixture(campaign, monkeypatch)
    record["started_at"] = runner.time.time() - age
    runner._atomic_json(state / "launcher.json", record)
    heartbeat_path = state / f"{runner.STATE_PREFIX}_supervisor_status.json"
    heartbeat = json.loads(heartbeat_path.read_text())
    heartbeat.update(status=native_status, daemon_pid=None, daemon_pid_alive=False)
    runner._atomic_json(heartbeat_path, heartbeat)
    assert runner.status(root, spec, state)["status"] == expected


def test_only_native_provider_start_event_verifies_provider_execution(campaign, monkeypatch):
    root, spec, state, _ = _status_fixture(campaign, monkeypatch, native_state={"active_task_id": "CIMP-TUI-01"})
    events = state / f"{runner.STATE_PREFIX}_events.jsonl"
    event = {"type": "task_selected", "task_id": "CIMP-TUI-01", "timestamp": datetime.now(timezone.utc).isoformat()}
    events.write_text(json.dumps(event) + "\n")
    assert not runner.status(root, spec, state)["provider_execution_verified"]
    event["type"] = "implementation_provider_started"
    events.write_text(json.dumps(event) + "\n")
    result = runner.status(root, spec, state)
    assert result["provider_execution_verified"] and result["progress_verified"]


def test_status_preserves_intentional_user_wait(campaign, monkeypatch):
    root, spec, state, _ = _status_fixture(campaign, monkeypatch, native_state={
        "active_task_id": "CIMP-TUI-01", "active_phase": "waiting_for_user"})
    assert runner.status(root, spec, state)["status"] == "waiting_for_user"


def test_status_reports_blocked_not_idle_success(campaign, monkeypatch):
    root, spec, state, _ = _status_fixture(campaign, monkeypatch, board={
        "count": 2, "completed": 0, "ready_task_ids": [], "manual_hold_task_ids": []})
    assert runner.status(root, spec, state)["status"] == "blocked"


def test_status_reports_native_attempt_limit_block_despite_ready_dependencies(campaign, monkeypatch):
    root, spec, state, _ = _status_fixture(campaign, monkeypatch, native_state={
        "blocked_task_ids": ["CIMP-TUI-01"], "selectable_ready_task_ids": [],
    })
    assert runner.status(root, spec, state)["status"] == "blocked"



def _attempt_limited_native_state():
    # Native keeps ready-but-budget-limited tasks out of blocked_task_ids.
    return {
        "active_task_id": "", "active_task_cid": "", "active_attempt": 0,
        "active_phase": "", "implementation_in_progress": False,
        "ready_task_ids": ["CIMP-UX-09", "CIMP-UX-18"],
        "selectable_ready_task_ids": [], "blocked_task_ids": [],
        "selection_idle_reason": "all_selectable_ready_tasks_reached_max_task_attempts",
        "implementation_attempts": {"CIMP-UX-09": 3, "CIMP-UX-18": 3},
        "implementation_attempts_by_cid": {"fixture-cid-09": 3, "fixture-cid-18": 3},
        "task_identities": {task: {"canonical_task_cid": cid} for task, cid in (
            ("CIMP-UX-09", "fixture-cid-09"), ("CIMP-UX-18", "fixture-cid-18"))},
    }


def _attempt_limited_status_fixture(campaign, monkeypatch):
    body = _attempt_limited_native_state()
    root, spec, state, record = _status_fixture(campaign, monkeypatch, native_state=body,
        board={"count": 68, "completed": 15, "ready_task_ids": body["ready_task_ids"],
               "manual_hold_task_ids": []})
    record["started_at"] = runner.time.time() - 3600
    runner._atomic_json(state / "launcher.json", record)
    # A fresh poll repeats backpressure; it is activity, never useful progress.
    events = state / f"{runner.STATE_PREFIX}_events.jsonl"
    events.write_text(json.dumps({"type": "task_attempt_limit_backpressure",
        "timestamp": datetime.now(timezone.utc).isoformat(), "max_task_attempts": 3,
        "limited_task_ids": body["ready_task_ids"], "selection_idle_reason": body["selection_idle_reason"]}) + "\n")
    return root, spec, state, record, body


@pytest.mark.parametrize("heartbeat_status", ["running", "agentic_maintenance_started", "agentic_maintenance_completed"])
def test_status_reports_actual_native_attempt_limit_without_claiming_heartbeat_progress(campaign, monkeypatch, heartbeat_status):
    root, spec, state, _, body = _attempt_limited_status_fixture(campaign, monkeypatch)
    heartbeat_path = state / f"{runner.STATE_PREFIX}_supervisor_status.json"
    heartbeat = json.loads(heartbeat_path.read_text())
    heartbeat.update(status=heartbeat_status)
    runner._atomic_json(heartbeat_path, heartbeat)
    if heartbeat_status != "running":
        from ipfs_accelerate_py.agent_supervisor.todo_daemon import supervisor_activity
        monkeypatch.setattr(supervisor_activity, "observe_supervisor_activity", lambda *a, **k:
                            SimpleNamespace(phase_ready=True))
    paths = [state / "launcher.json", state / f"{runner.STATE_PREFIX}_task_state.json", heartbeat_path,
             state / f"{runner.STATE_PREFIX}_events.jsonl"]
    before = {p: p.read_bytes() for p in paths}
    result = runner.status(root, spec, state)
    assert result["status"] == "budget_exhausted" and not result["healthy"]
    assert not result["progress_verified"]
    assert result["attempt_budget"] == {
        "reason": body["selection_idle_reason"], "max_task_attempts": 3,
        "task_ids": ["CIMP-UX-09", "CIMP-UX-18"],
        "attempts": {"CIMP-UX-09": 3, "CIMP-UX-18": 3},
        "completion_authority": False,
    }
    assert before == {p: p.read_bytes() for p in paths}


@pytest.mark.parametrize("change", ["available_task", "different_idle_reason", "new_cid", "active", "intentional_wait"])
def test_attempt_limit_observation_preserves_other_native_states(campaign, monkeypatch, change):
    root, spec, state, _, body = _attempt_limited_status_fixture(campaign, monkeypatch)
    expected = "running"
    if change == "available_task":
        body["selectable_ready_task_ids"] = ["CIMP-UX-18"]
        body["implementation_attempts"]["CIMP-UX-18"] = 2
        body["implementation_attempts_by_cid"]["fixture-cid-18"] = 2
    elif change == "different_idle_reason":
        body["selection_idle_reason"] = "no_ready_tasks"
    elif change == "new_cid":
        body["task_identities"]["CIMP-UX-18"]["canonical_task_cid"] = "fixture-new-cid"
    elif change == "active":
        body.update(active_task_id="CIMP-UX-09", active_task_cid="fixture-cid-09",
                    active_attempt=3, implementation_in_progress=True,
                    active_phase="implementation", active_task_started_at=datetime.now(timezone.utc).isoformat())
        expected = "active"
    else:
        body.update(active_phase="waiting_for_user", active_task_id="CIMP-UX-09")
        expected = "waiting_for_user"
    runner._atomic_json(state / f"{runner.STATE_PREFIX}_task_state.json", body)
    result = runner.status(root, spec, state)
    assert result["status"] == expected
    assert result["attempt_budget"] is None



def test_attempt_limit_reads_real_native_authority_without_a_json_mirror(campaign, monkeypatch):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import portal_task_state_control_plane as plane
    root, spec, state, _, body = _attempt_limited_status_fixture(campaign, monkeypatch)
    path = state / f"{runner.STATE_PREFIX}_task_state.json"
    path.unlink()
    monkeypatch.setenv(runner.ORCHESTRATION_DIR_ENV, str(state / "control-plane"))
    body["heartbeat_at"] = body["last_progress_at"] = datetime.fromtimestamp(
        runner.time.time() - 1800, timezone.utc).isoformat()
    plane.save_portal_task_state(path.stem, body, state_path=path)
    assert not path.exists()
    result = runner.status(root, spec, state)
    assert result["status"] == "budget_exhausted" and not result["healthy"]
    assert result["native_state_source"]["source"] == "native_control_plane"
    assert result["attempt_budget"]["attempts"] == {"CIMP-UX-09": 3, "CIMP-UX-18": 3}
    after = plane.read_task_state_payload(path)
    assert after["implementation_attempts"] == body["implementation_attempts"]
    assert after["implementation_attempts_by_cid"] == body["implementation_attempts_by_cid"]
    assert not path.exists()


def test_attempt_limit_does_not_hide_real_canonical_validation(campaign, monkeypatch):
    root, spec, state, _, _ = _attempt_limited_status_fixture(campaign, monkeypatch)
    from integrations.ipfs_accelerate import reconciliation_activity
    monkeypatch.setattr(reconciliation_activity, "evidence", lambda *a, **k:
                        {"type": "canonical_native_executor_in_flight", "deadline_at": runner.time.time() + 30})
    result = runner.status(root, spec, state)
    assert result["status"] == "active" and result["healthy"]
    assert result["validation_activity_verified"] and result["progress_verified"]


def test_attempt_limit_keeps_initial_bounded_maintenance_grace(campaign, monkeypatch):
    root, spec, state, record, _ = _attempt_limited_status_fixture(campaign, monkeypatch)
    record["started_at"] = runner.time.time() - 10
    runner._atomic_json(state / "launcher.json", record)
    heartbeat_path = state / f"{runner.STATE_PREFIX}_supervisor_status.json"
    heartbeat = json.loads(heartbeat_path.read_text())
    heartbeat.update(status="agentic_maintenance_started")
    runner._atomic_json(heartbeat_path, heartbeat)
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import supervisor_activity
    monkeypatch.setattr(supervisor_activity, "observe_supervisor_activity", lambda *a, **k:
                        SimpleNamespace(phase_ready=True))
    result = runner.status(root, spec, state)
    assert result["status"] == "maintenance" and result["healthy"]


def test_status_detects_expired_attempt_without_log(campaign, monkeypatch):
    started = datetime.fromtimestamp(runner.time.time() - 1000, timezone.utc).isoformat()
    root, spec, state, _ = _status_fixture(campaign, monkeypatch, native_state={
        "active_task_id": "CIMP-TUI-01", "active_task_started_at": started,
        "implementation_in_progress": True,
    })
    assert runner.status(root, spec, state)["status"] == "stalled"


def test_status_rejects_prior_run_claim_as_progress(campaign, monkeypatch):
    root, spec, state, record = _status_fixture(campaign, monkeypatch,
        native_state={"active_task_id": "CIMP-TUI-01"})
    old = record["started_at"] - 100
    os.utime(state / f"{runner.STATE_PREFIX}_task_state.json", (old, old))
    assert not runner.status(root, spec, state)["progress_verified"]



@pytest.mark.parametrize("has_old_claim", [False, True])
def test_fresh_supervisor_events_cannot_hide_missing_current_task_progress(campaign, monkeypatch, has_old_claim):
    root, spec, state, record = _status_fixture(campaign, monkeypatch,
        native_state={"active_task_id": "CIMP-TUI-01"} if has_old_claim else None)
    record["started_at"] = runner.time.time() - runner.STARTUP_SECONDS - 10
    runner._atomic_json(state / "launcher.json", record)
    if has_old_claim:
        old = record["started_at"] - 100
        os.utime(state / f"{runner.STATE_PREFIX}_task_state.json", (old, old))
    (state / f"{runner.STATE_PREFIX}_supervisor_events.jsonl").write_text(
        json.dumps({"type": "watchdog_heartbeat"}) + "\n")
    result = runner.status(root, spec, state)
    assert result["status"] == "no_progress"
    assert not result["claim_progress_verified"]


def test_selected_claim_without_attempt_clock_has_bounded_wait(campaign, monkeypatch):
    root, spec, state, record = _status_fixture(campaign, monkeypatch,
        native_state={"active_task_id": "CIMP-TUI-01", "implementation_in_progress": False})
    record["started_at"] = runner.time.time() - runner.STALL_SECONDS - 10
    runner._atomic_json(state / "launcher.json", record)
    result = runner.status(root, spec, state)
    assert result["status"] == "no_progress"


@pytest.mark.parametrize("proof", ["missing", "wrong_owner", "wrong_plan", "unquiesced", "verified"])
def test_dead_full_launcher_requires_bound_container_shutdown_proof(campaign, monkeypatch, proof):
    root, spec, state, record = _status_fixture(campaign, monkeypatch)
    record.update(schema_version="complaint-improvement-launcher@1", repo_root=str(root),
                  state_dir=str(state), plan_id=campaign[3]["receipt"]["plan_id"])
    runner._atomic_json(state / "launcher.json", record)
    monkeypatch.setattr(runner, "process_identity", lambda _pid: None)
    if proof != "missing":
        receipt = {"schema": "complaint-improvement-container-shutdown@1", "repo_root": str(root),
                   "state_dir": str(state), "plan_id": record["plan_id"], "started_at": record["started_at"],
                   "owner_token_sha256": runner.hashlib.sha256(record["owner_token"].encode()).hexdigest(),
                   "quiesced": proof != "unquiesced", "status": "stopped", "completion_authority": False,
                   "provider_callback_settled": False, "attempt_refunded": False}
        if proof == "wrong_owner":
            receipt["owner_token_sha256"] = "0" * 64
        if proof == "wrong_plan":
            receipt["plan_id"] = "another-plan"
        runner._atomic_json(state / "container_shutdown.json", receipt)
    result = runner.status(root, spec, state)
    assert result["status"] == ("stopped" if proof == "verified" else "stop_incomplete")
    assert result["container_shutdown_verified"] is (proof == "verified")
    assert not result["owned_process_alive"]

def test_status_handles_malformed_owner_and_native_receipts(campaign):
    root, spec, state, _ = campaign
    state.mkdir()
    runner._atomic_json(state / "launcher.json", {"identity": "malformed", "started_at": None})
    (state / f"{runner.STATE_PREFIX}_task_state.json").write_text("not-json")
    result = runner.status(root, spec, state)
    assert result["status"] == "stopped" and result["pid"] is None
    assert result["native_read_errors"]["state"] == "JSONDecodeError"


def test_tail_is_bounded_and_preserves_latest_lines(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text("old\n" * 10000 + "last\n")
    result = runner._tail(path, lines=3, maximum=100)
    assert len(result) == 3 and result[-1] == "last"


def test_cli_has_no_implicit_provider_model_override(monkeypatch, capsys, tmp_path):
    seen = []
    monkeypatch.setattr(runner, "doctor", lambda *a: seen.append(a) or {"status": "ready"})
    assert runner.main(["doctor", "--repo-root", str(ROOT), "--state-dir", str(tmp_path)]) == 0
    assert seen[0][0] == ROOT
    assert json.loads(capsys.readouterr().out)["status"] == "ready"
    with pytest.raises(SystemExit):
        runner.main(["start", "--model", "old-model"])


def test_internal_entry_requires_exact_parent_ownership(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "owns_process", lambda record: False)
    with pytest.raises(RuntimeError, match="exact owned launch receipt"):
        runner.run_internal(ROOT, ROOT / runner.SPEC_RELATIVE, tmp_path, "wrong", "campaign")


@pytest.mark.parametrize("changed_spec", [False, True])
def test_internal_entry_calls_actual_native_runner_contract_without_once(campaign, monkeypatch, changed_spec):
    root, spec, state, generated = campaign
    monkeypatch.setenv("XAI_API_KEY", "synthetic-owner-admission-never-dispatched")
    state.mkdir()
    record = _owner(state)
    record["plan_id"] = generated["receipt"]["plan_id"]
    record["identity"]["pid"] = os.getpid()
    runner._atomic_json(state / "launcher.json", record)
    monkeypatch.setattr(runner, "owns_process", lambda item: True)
    monkeypatch.setattr(runner, "_validate_board", lambda *a: {})
    monkeypatch.setattr(runner, "_private_runtime_checks", lambda *a: {"ready": True})
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor_runner as native_runner
    calls = []
    monkeypatch.setattr(runner, "_run_native_supervisor",
                        lambda argv, **kwargs: calls.append((argv, kwargs)))
    # Scope the environment mutation to this test; the child normally owns it.
    monkeypatch.setattr(runner.os, "environ", dict(os.environ))
    if changed_spec:
        document = json.loads(spec.read_text())
        document["tasks"][0]["implementation_prompt"] += " Changed after launch."
        spec.write_text(json.dumps(document))
        with pytest.raises(RuntimeError, match="specification changed"):
            runner.run_internal(root, spec, state, "test-owner", "campaign")
        assert not calls
        return
    assert runner.run_internal(root, spec, state, "test-owner", "campaign") == 0
    assert len(calls) == 1 and "--once" not in calls[0][0]
    assert calls[0][1]["repo_root"] == root
    assert "--implement" in calls[0][0]


def _configured_owner(repo, state, workspace_root):
    binding = runner._validate_worktree_root(repo, state, workspace_root, claim=True)
    record = _owner(state)
    record.update(repo_root=str(repo), state_dir=str(state), worktree_root=str(workspace_root),
                  worktree_root_binding=binding)
    record['argv'].extend(['--worktree-root', str(workspace_root)])
    record['identity']['argv'] = record['argv'][:]
    return record


@pytest.mark.parametrize('mutation', ['symlink', 'public_mode', 'nonempty', 'foreign_marker', 'foreign_uid', 'inside_repo', 'inside_state'])
def test_configured_worktree_root_rejects_unowned_or_non_dedicated_directory(tmp_path, monkeypatch, mutation):
    repo, state = tmp_path / 'repo', tmp_path / 'state'
    repo.mkdir(); state.mkdir(mode=0o700)
    target = tmp_path / 'external-root'
    target.mkdir(mode=0o700)
    if mutation == 'symlink':
        alias = tmp_path / 'alias'; alias.symlink_to(target, target_is_directory=True); target = alias
    elif mutation == 'public_mode':
        target.chmod(0o755)
    elif mutation == 'nonempty':
        (target / 'unrelated.txt').write_text('preserve')
    elif mutation == 'foreign_marker':
        runner._validate_worktree_root(repo, tmp_path / 'foreign-epoch', target, claim=True)
    elif mutation == 'foreign_uid':
        uid = os.getuid(); monkeypatch.setattr(runner.os, 'getuid', lambda: uid + 1)
    elif mutation == 'inside_repo':
        target = repo / 'private'; target.mkdir(mode=0o700)
    elif mutation == 'inside_state':
        target = state / 'private'; target.mkdir(mode=0o700)
    with pytest.raises((ValueError, OSError)):
        runner._validate_worktree_root(repo, state, target, claim=True)


def test_bound_worktree_root_persists_identity_without_touching_epoch_or_task_history(tmp_path, monkeypatch):
    repo, state, target = tmp_path / 'repo', tmp_path / 'epoch', tmp_path / 'storage-root'
    repo.mkdir(); state.mkdir(mode=0o700); target.mkdir(mode=0o700)
    history = state / 'spent-counts-and-quarantine.json'
    history.write_text('{"spent":4,"quarantine":"retained"}')
    before = history.read_bytes()
    record = _configured_owner(repo, state, target)
    assert (target / runner.WORKTREE_MARKER).stat().st_mode & 0o777 == 0o600
    (target / 'workspace_native_01').mkdir()
    monkeypatch.setenv('IPFS_ACCELERATE_AGENT_WORKTREE_ROOT', '/untrusted/ambient')
    selected, binding = runner._select_worktree_root(repo, state, record, None)
    assert selected == target and binding == record['worktree_root_binding']
    assert binding['device'] == target.stat().st_dev and binding['inode'] == target.stat().st_ino
    assert history.read_bytes() == before
    assert not (state / 'worktrees').exists()


@pytest.mark.parametrize('mutation', ['directory_replaced', 'marker_replaced', 'flag_missing', 'flag_duplicate', 'record_path_changed'])
def test_recorded_root_rejects_identity_or_argv_changes_before_stop_effects(tmp_path, monkeypatch, mutation):
    repo, state, target = tmp_path / 'repo', tmp_path / 'epoch', tmp_path / 'storage-root'
    repo.mkdir(); state.mkdir(mode=0o700); target.mkdir(mode=0o700)
    record = _configured_owner(repo, state, target)
    if mutation == 'directory_replaced':
        target.rename(tmp_path / 'preserved-old-root'); target.mkdir(mode=0o700)
        (target / runner.WORKTREE_MARKER).write_bytes((tmp_path / 'preserved-old-root' / runner.WORKTREE_MARKER).read_bytes())
        (target / runner.WORKTREE_MARKER).chmod(0o600)
    elif mutation == 'marker_replaced':
        (target / runner.WORKTREE_MARKER).write_text('{}')
    elif mutation == 'flag_missing':
        record['argv'] = record['argv'][:-2]
    elif mutation == 'flag_duplicate':
        record['argv'] += ['--worktree-root', str(target)]
    else:
        record['worktree_root'] = str(tmp_path / 'other-root')
    runner._atomic_json(state / 'launcher.json', record)
    monkeypatch.setattr(runner, '_signal_birth', lambda *a: pytest.fail('invalid binding signalled process'))
    from integrations.ipfs_accelerate import improvement_shutdown
    monkeypatch.setattr(improvement_shutdown, 'close_campaign_containers', lambda *a, **k: pytest.fail('invalid binding inspected Docker'))
    assert runner.stop(state)['status'] == 'stop_incomplete'


def test_actual_native_parser_uses_external_root_without_moving_state_or_queue(campaign):
    root, spec, state, generated = campaign
    target = root / 'external-storage'
    target.mkdir(mode=0o700)
    # This config parser is pure; storage validation is separately exercised on
    # a directory outside the synthetic repository boundary.
    native, _ = runner._native_modules(ROOT)
    parsed = native.parse_args(runner.native_argv(Path(generated['board_path']), state, 'campaign', worktree_root=target))
    config = native.supervisor_config_from_args(parsed, repo_root=root)
    assert config.worktree_root == target
    assert config.state_path == state / 'complaint_intake_task_state.json'
    assert config.merge_queue_dir == state / 'merge-queue'


def test_cli_accepts_explicit_root_only_for_start_doctor_and_owned_internal(monkeypatch, capsys, tmp_path):
    observed = []
    target = tmp_path / 'private-root'
    monkeypatch.setattr(runner, 'doctor', lambda *a, **k: observed.append(k) or {'status': 'ready'})
    assert runner.main(['doctor', '--repo-root', str(ROOT), '--state-dir', str(tmp_path), '--worktree-root', str(target)]) == 0
    assert observed == [{'worktree_root': target}]
    capsys.readouterr()
    for command in ['status', 'stop']:
        with pytest.raises(SystemExit):
            runner.main([command, '--worktree-root', str(target)])


def test_capacity_preflight_uses_real_pinned_blob_sizes_without_fetch(tmp_path, monkeypatch):
    repo = tmp_path / 'source'
    datasets = repo / 'external/ipfs_datasets_py'
    datasets.mkdir(parents=True)
    def git(path, *args):
        return runner.subprocess.run(['git', '-c', 'user.name=Synthetic Fixture', '-c', 'user.email=fixture@example.invalid', *args],
            cwd=path, check=True, capture_output=True, text=True).stdout.strip()
    git(datasets, 'init', '-q')
    (datasets / 'payload').write_bytes(b'd' * 8192)
    git(datasets, 'add', 'payload'); git(datasets, 'commit', '-qm', 'synthetic datasets')
    pinned = git(datasets, 'rev-parse', 'HEAD')
    git(repo, 'init', '-q')
    (repo / 'payload').write_bytes(b'r' * 4096)
    git(repo, 'add', 'payload')
    git(repo, 'update-index', '--add', '--cacheinfo', '160000,' + pinned + ',external/ipfs_datasets_py')
    git(repo, 'commit', '-qm', 'synthetic source with pinned datasets')
    target = tmp_path / 'target'; target.mkdir(mode=0o700)
    monkeypatch.setattr(runner.shutil, 'disk_usage', lambda path: SimpleNamespace(free=12287))
    capacity = runner._worktree_capacity(repo, target)
    assert capacity['minimum_cold_checkout_bytes'] == 12288
    assert capacity['sufficient'] is False and capacity['free_bytes'] == 12287
    assert list(target.iterdir()) == []


def test_doctor_refuses_known_insufficient_checkout_space_without_provider(campaign, monkeypatch):
    root, spec, state, generated = campaign
    monkeypatch.setattr(runner, '_branch', lambda path: 'campaign')
    monkeypatch.setattr(runner.shutil, 'which', lambda *a, **k: '/synthetic/grok')
    monkeypatch.setenv('XAI_API_KEY', 'synthetic-not-used')
    monkeypatch.setattr(runner, '_private_runtime_checks', lambda *a: {'ready': True})
    monkeypatch.setattr(runner, '_worktree_capacity', lambda *a: {'sufficient': False, 'free_bytes': 1, 'minimum_cold_checkout_bytes': 2})
    result = runner.doctor(root, spec, state)
    assert result['status'] == 'not_ready' and result['paid_calls'] == 0
    assert result['worktree_capacity']['sufficient'] is False


def test_configured_start_and_owned_reentry_preserve_root_epoch_and_native_contract(campaign, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "synthetic-owner-admission-never-dispatched")
    _admission_transport(monkeypatch)
    root, spec, state, generated = campaign
    state.mkdir(mode=0o700)
    target = root.parent / (root.name + '-dedicated-storage')
    target.mkdir(mode=0o700)
    history = state / 'original-accounting-and-quarantine.json'
    history.write_text('{"spent":4,"quarantine":"preserved"}')
    original = history.read_bytes()
    current = {}
    monkeypatch.setattr(runner, 'process_identity', lambda pid: current.get(pid))
    monkeypatch.setattr(runner, 'prepare', lambda *a: generated)
    monkeypatch.setattr(runner, 'doctor', lambda *a, **k: {'status': 'ready', 'merge_target': 'campaign',
                                                       'native_plan_id': generated['receipt']['plan_id']})
    def spawn(argv, **kwargs):
        current[991119] = _identity(argv=argv)
        return SimpleNamespace(pid=991119, poll=lambda: None)
    monkeypatch.setattr(runner.subprocess, 'Popen', spawn)
    assert runner.start(root, spec, state, worktree_root=target)['status'] == 'starting'
    record = runner._read_json(state / 'launcher.json')
    assert record['argv'].count('--worktree-root') == 1
    assert record['argv'][-2:] == ['--worktree-root', str(target)]
    assert record['worktree_root_binding']['marker_sha256'] == runner.hashlib.sha256((target / runner.WORKTREE_MARKER).read_bytes()).hexdigest()
    assert runner._select_worktree_root(root, state, record, None)[0] == target
    record['identity']['pid'] = os.getpid()
    runner._atomic_json(state / 'launcher.json', record)
    monkeypatch.setattr(runner, 'owns_process', lambda item: True)
    monkeypatch.setattr(runner, '_validate_board', lambda *a: {})
    monkeypatch.setattr(runner, '_private_runtime_checks', lambda *a: {'ready': True})
    monkeypatch.setattr(runner.os, 'environ', dict(os.environ))
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor_runner as native_runner
    calls = []
    monkeypatch.setattr(runner, '_run_native_supervisor', lambda argv, **kwargs: calls.append(argv))
    assert runner.run_internal(root, spec, state, record['owner_token'], 'campaign', worktree_root=target) == 0
    assert len(calls) == 1 and calls[0].count('--worktree-root') == 1
    assert calls[0][calls[0].index('--worktree-root') + 1] == str(target)
    assert calls[0][calls[0].index('--state-dir') + 1] == str(state)
    assert calls[0][calls[0].index('--merge-queue-dir') + 1] == str(state / 'merge-queue')
    assert history.read_bytes() == original
    assert not (state / 'worktrees').exists()


def _resource_directories(tmp_path):
    values = {}
    for role in ('repository', 'state', 'worktrees', 'home', 'temporary'):
        values[role] = tmp_path / role
        values[role].mkdir()
    return values


def _capacity_metadata(*, free_bytes=None, free_inodes=None, read_only=False):
    return SimpleNamespace(f_bavail=runner.RESOURCE_MIN_FREE_BYTES if free_bytes is None else free_bytes,
        f_frsize=1, f_favail=runner.RESOURCE_MIN_FREE_INODES if free_inodes is None else free_inodes,
        f_files=1_000_000, f_flag=os.ST_RDONLY if read_only else 0)


@pytest.mark.parametrize('role', ['repository', 'state', 'worktrees', 'home', 'temporary'])
@pytest.mark.parametrize('failure', ['bytes', 'inodes', 'readonly', 'access', 'unavailable'])
def test_each_campaign_filesystem_role_can_hold_admission(tmp_path, monkeypatch, role, failure):
    paths = _resource_directories(tmp_path)
    def capacity(path):
        if Path(path) != paths[role]:
            return _capacity_metadata()
        if failure == 'unavailable':
            raise OSError('synthetic statvfs refusal')
        return _capacity_metadata(free_bytes=runner.RESOURCE_MIN_FREE_BYTES - 1 if failure == 'bytes' else None,
            free_inodes=runner.RESOURCE_MIN_FREE_INODES - 1 if failure == 'inodes' else None,
            read_only=failure == 'readonly')
    monkeypatch.setattr(runner.os, 'statvfs', capacity)
    monkeypatch.setattr(runner.os, 'access', lambda path, *a, **k: failure != 'access' or Path(path) != paths[role])
    observed = runner._resource_capacity(paths['repository'], paths['state'], paths['worktrees'],
        {'HOME': str(paths['home']), 'TMPDIR': str(paths['temporary'])})
    assert observed['ready'] is False and observed['roles'][role]['ready'] is False
    assert all(value['ready'] for name, value in observed['roles'].items() if name != role)
    assert observed['capacity_reserved'] is False and observed['paid_dispatch'] is False
    assert observed['accounting_changed'] is False and observed['attempt_refunded'] is False
    assert observed['live_wait_or_lease_claimed'] is False


def test_absent_resource_locations_use_owned_ancestor_without_creation(tmp_path, monkeypatch):
    root = tmp_path / 'repository'; root.mkdir()
    home = tmp_path / 'home'; home.mkdir()
    state, worktrees, temporary = (tmp_path / name / 'absent' for name in ('state', 'worktrees', 'temporary'))
    checked = []
    monkeypatch.setattr(runner.os, 'statvfs', lambda path: checked.append(Path(path)) or _capacity_metadata())
    monkeypatch.setattr(runner.os, 'access', lambda *a, **k: True)
    observed = runner._resource_capacity(root, state, worktrees, {'HOME': str(home), 'TMPDIR': str(temporary)})
    assert observed['ready'] is True and len(checked) == 6 + int(sys.platform.startswith('linux'))
    assert observed['roles']['state']['filesystem_path'] == str(tmp_path)
    assert not state.parent.exists() and not worktrees.parent.exists() and not temporary.parent.exists()
    assert observed['capacity_reserved'] is False


@pytest.mark.parametrize('operation', ['doctor', 'start', 'internal'])
def test_resource_hold_precedes_state_creation_and_native_admission(tmp_path, monkeypatch, operation):
    root = tmp_path / 'repository'; root.mkdir()
    state = tmp_path / 'absent-state'
    history = tmp_path / 'spent-accounting.json'; history.write_text('{"spent":1}')
    before = history.read_bytes()
    monkeypatch.setattr(runner, '_resource_capacity', lambda *a: {'ready': False, 'reason': 'local_capacity_hold',
        'paid_dispatch': False, 'attempt_refunded': False, 'accounting_changed': False})
    monkeypatch.setattr(runner, '_native_modules', lambda *a: pytest.fail('resource hold imported Native'))
    monkeypatch.setattr(runner, '_lock', lambda *a, **k: pytest.fail('resource hold created a lock'))
    monkeypatch.setattr(runner, 'prepare', lambda *a: pytest.fail('resource hold rewrote the task board'))
    monkeypatch.setattr(runner.subprocess, 'Popen', lambda *a, **k: pytest.fail('resource hold spawned an actor'))
    if operation == 'internal':
        with pytest.raises(runner.CampaignResourceHold) as refused:
            runner.run_internal(root, root / 'unread-spec.json', state, 'synthetic-owner', 'campaign')
        assert refused.value.code == 'campaign_resource_hold'
        assert refused.value.observation['stage'] == 'before_owned_startup_lock'
    else:
        call = runner.doctor if operation == 'doctor' else runner.start
        observed = call(root, root / 'unread-spec.json', state)
        assert observed['status'] == 'not_ready' and observed['reason'] == 'campaign_resource_hold'
        assert observed['paid_calls'] == 0 and observed['execution_started'] is False
    assert history.read_bytes() == before and not state.exists()


@pytest.mark.parametrize('failure', ['bytes', 'unavailable', 'native_timeout'])
def test_public_native_loop_resource_hold_cannot_reach_run_once(tmp_path, monkeypatch, failure):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon_runner as native_loop
    calls, closed = [], []
    class InertDaemon:
        def run_once(self):
            calls.append(True)
            pytest.fail('resource hold reached dispatch')
        def close_event_runtime(self):
            closed.append(True)
    def capacity(*args):
        if failure == 'native_timeout':
            time.sleep(.2)
            pytest.fail('Native hook deadline did not interrupt the capacity observation')
        return {'ready': False, 'reason': 'local_capacity_insufficient' if failure == 'bytes' else 'local_capacity_unavailable',
            'paid_dispatch': False, 'attempt_refunded': False, 'accounting_changed': False}
    monkeypatch.setattr(runner, '_resource_capacity', capacity)
    context = native_loop.ImplementationDaemonRunContext(
        parsed=SimpleNamespace(once=True, daemon_hook_timeout_seconds=.02, interval=1),
        state_path=tmp_path / 'native-state.json', strategy_path=tmp_path / 'strategy.json',
        events_path=tmp_path / 'events.jsonl')
    with pytest.raises(runner.CampaignResourceHold) as refused:
        native_loop.run_portal_implementation_daemon_loop(InertDaemon(), context,
            logger=runner._LOGGER, hooks=(runner._resource_admission_hook(tmp_path, tmp_path / 'state', tmp_path / 'worktrees', {}),))
    assert refused.value.observation['stage'] == 'before_native_pass'
    assert calls == [] and closed == [True]
    assert refused.value.observation['paid_dispatch'] is False
    assert not context.events_path.exists() and not context.state_path.exists()
    if failure == 'native_timeout':
        assert refused.value.observation['reason'] == 'resource_observation_timed_out'


def test_public_native_loop_capacity_observation_allows_one_ordinary_pass(tmp_path, monkeypatch):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon_runner as native_loop
    from tests.test_worktree_capacity_admission import _world as pinned_git_world
    repo = pinned_git_world(tmp_path)
    calls, closed, checks = [], [], []
    class InertDaemon:
        def run_once(self):
            calls.append(True)
            return {'unchanged': True, 'write_count': 0}
        def close_event_runtime(self):
            closed.append(True)
    monkeypatch.setattr(runner, '_resource_capacity', lambda *a: checks.append(a) or {'ready': True})
    context = native_loop.ImplementationDaemonRunContext(
        parsed=SimpleNamespace(once=True, daemon_hook_timeout_seconds=1, interval=1),
        state_path=tmp_path / 'native-state.json', strategy_path=tmp_path / 'strategy.json',
        events_path=tmp_path / 'events.jsonl')
    native_loop.run_portal_implementation_daemon_loop(InertDaemon(), context,
        logger=runner._LOGGER, hooks=(runner._resource_admission_hook(repo, tmp_path / 'state', tmp_path / 'worktrees', {}),))
    assert len(checks) == 1 and calls == [True] and closed == [True]
    assert not context.events_path.exists() and not context.state_path.exists()



def test_native_resource_alarm_stops_remaining_filesystem_observations(tmp_path, monkeypatch):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon_runner as native_loop
    paths = _resource_directories(tmp_path)
    calls = []
    def expired(path):
        calls.append(Path(path))
        raise native_loop.DaemonHookTimeoutError('synthetic native alarm')
    monkeypatch.setattr(runner.os, 'statvfs', expired)
    observed = runner._resource_capacity(paths['repository'], paths['state'], paths['worktrees'],
        {'HOME': str(paths['home']), 'TMPDIR': str(paths['temporary'])})
    assert calls == [paths['repository']]
    assert observed['ready'] is False and observed['reason'] == 'resource_observation_timed_out'
    assert len(observed['roles']) == 6 and all(row['ready'] is False for row in observed['roles'].values())
    assert all(observed['roles'][name]['reason'] == 'unobserved_after_timeout'
        for name in ('state', 'worktrees', 'home', 'temporary', 'containerd_metadata'))
    assert observed['paid_dispatch'] is False and observed['live_wait_or_lease_claimed'] is False



def _owned_growing_native_event_history(path, start_event, *, padding_records):
    """Create only synthetic owned fixture history through the actual Native writer."""
    import hashlib
    from ipfs_accelerate_py.agent_supervisor.runtime.event_log import append_jsonl_event
    path.write_bytes(b'')
    start = append_jsonl_event(path, 'implementation_started', {
        key: value for key, value in start_event.items() if key not in {'type', 'event_id'}
    })
    padding = 'synthetic-history:' + 'x' * (512 * 1024)
    for index in range(padding_records):
        append_jsonl_event(path, 'synthetic_shutdown_history', {
            'timestamp': start['timestamp'], 'index': index, 'detail': padding,
        })
    path.chmod(0o664)
    original = path.read_bytes()
    records = [json.loads(line) for line in original.splitlines()]
    assert len(records) == padding_records + 1 and records[0] == start
    previous = ''
    for sequence, record in enumerate(records, 1):
        material = {key: value for key, value in record.items() if key != 'event_id'}
        canonical = json.dumps(material, sort_keys=True, separators=(',', ':'),
                               ensure_ascii=False, allow_nan=False).encode('utf-8')
        assert record['sequence'] == sequence and record['previous_event_id'] == previous
        assert record['event_id'] == 'sha256:' + hashlib.sha256(canonical).hexdigest()
        previous = record['event_id']
    return start, original


def test_growing_owned_event_history_preserves_progress_and_recovery_bounds(campaign, monkeypatch):
    root, spec, state, generated = campaign
    state.mkdir(mode=0o700)
    monkeypatch.setenv('IPFS_ACCELERATE_AGENT_EVENT_LOG_MAX_BYTES', str(50 * 1024 * 1024))
    monkeypatch.setenv(runner.ORCHESTRATION_DIR_ENV, str(state / 'control-plane'))
    selected_at = time.time() - 30
    execution = datetime.fromtimestamp(selected_at + 10, timezone.utc).isoformat()
    selection = datetime.fromtimestamp(selected_at, timezone.utc).isoformat()
    workspace = state / 'worktrees/workspace_history'
    workspace.mkdir(parents=True)
    log = state / 'attempt-1.log'
    log.write_text('Task: CIMP-TUI-01 synthetic\nStarted: ' + execution + '\nWorkspace: ' + str(workspace)
                   + '\n' + json.dumps({'type': 'usage', 'usage': {'input_tokens': 1}}) + '\n'
                   + json.dumps({'type': 'tool_call', 'name': 'synthetic-read'}) + '\n')
    log.chmod(0o600)
    events = state / f'{runner.STATE_PREFIX}_events.jsonl'
    start, original = _owned_growing_native_event_history(events, {
        'timestamp': execution, 'task_id': 'CIMP-TUI-01', 'canonical_task_cid': 'b' + 'a' * 58,
        'attempt': 1, 'worktree_path': str(workspace), 'log_path': str(log), 'execution_mode': 'model-assisted',
    }, padding_records=65)
    assert 32 * 1024 * 1024 < len(original) < runner.MAX_EVENT_HISTORY_BYTES
    binding = {'task_id': start['task_id'], 'task_cid': start['canonical_task_cid'], 'attempt': 1,
               'attempt_started_at': selection, 'execution_started_at': execution,
               'worktree': str(workspace), 'log_prefix': str(log)}
    progress = runner._owned_attempt_log_evidence(events, state, binding,
        started_at=selected_at - 1, now=time.time())
    assert progress is not None and progress['source'] == 'owned_attempt_log'
    assert progress['progress_fresh'] is True and progress['provider_terminal_observed'] is False
    assert progress['frame_counts'] == {'usage': 1, 'tool_call': 1}
    assert progress['task_id'] == start['task_id'] and progress['task_cid'] == start['canonical_task_cid']
    assert progress['completion_authority'] is False
    record = _full_owner(root, spec, state, generated['receipt']['plan_id'])
    runner._atomic_json(state / 'launcher.json', record)
    runner._atomic_json(state / 'container_shutdown.json', _shutdown_receipt(record))
    runner._atomic_json(state / f'{runner.STATE_PREFIX}_supervisor_status.json', {'status': 'stopped'})
    strategy = state / f'{runner.STATE_PREFIX}_strategy.json'
    runner._atomic_json(strategy, {})
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import portal_task_state_control_plane as plane
    state_path = state / f'{runner.STATE_PREFIX}_task_state.json'
    payload = {'implementation_attempts': {'CIMP-TUI-01': 1}, 'completed_task_ids': []}
    plane.save_portal_task_state(state_path.stem, payload, state_path=state_path)
    image = runner._recovery_preimage(root, state, record)
    assert image[str(events)][3] == runner.hashlib.sha256(original).hexdigest()
    assert image['native_payload']['implementation_attempts'] == payload['implementation_attempts']
    assert image['native_source']['source'] == 'native_control_plane'
    assert events.read_bytes() == original
    # A board/spec record with the same basename is not this epoch's journal.
    alternate = root / 'different-metadata' / f'{runner.STATE_PREFIX}_events.jsonl'
    alternate.parent.mkdir(mode=0o700)
    with alternate.open('wb') as output:
        output.truncate(32 * 1024 * 1024 + 1)
    for field in ('board_path', 'spec_path'):
        with pytest.raises(ValueError, match='bounded owned regular file'):
            runner._recovery_preimage(root, state, {**record, field: str(alternate)})
    assert events.read_bytes() == original
    # The event-specific increase must not enlarge provider-log or state reads.
    with log.open('ab') as output:
        output.truncate(32 * 1024 * 1024 + 1)
    assert runner._owned_attempt_log_evidence(events, state, binding,
        started_at=selected_at - 1, now=time.time()) is None
    with strategy.open('wb') as output:
        output.truncate(32 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match='bounded owned regular file'):
        runner._recovery_preimage(root, state, record)
    assert events.read_bytes() == original
# Trusted acceptance companion controls. These validate host admission, never
# manufacture a successful storage or Kit execution receipt.
def _replica_companion_roots(tmp_path, monkeypatch):
    trusted = tmp_path / "trusted"
    candidate = tmp_path / "candidate"
    source = trusted / "integrations/ipfs_accelerate/improvement_runner.py"
    source.parent.mkdir(parents=True)
    source.write_text("# trusted host fixture\n")
    monkeypatch.setattr(runner, "__file__", str(source))
    for root in (trusted, candidate):
        path = root / runner._PRIVATE_REPLICA_ACCEPTANCE
        path.parent.mkdir(parents=True)
        path.write_text("def test_replica_api_capability_is_explicit():\n    pass\n")
    return trusted, candidate


def test_storage_impact_always_selects_trusted_replica_companion(tmp_path):
    for changed in ("integrations/private_storage.py", "integrations/ipfs_datasets/storage.py"):
        expected = runner._IMPACTED_BEHAVIORAL_CHECKS[changed]
        for relative in expected:
            path = tmp_path / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        assert runner._PRIVATE_REPLICA_ACCEPTANCE in runner._impacted_behavioral_checks(tmp_path, [changed])


def test_replica_companion_binding_uses_installed_bytes_even_without_impact_context(tmp_path, monkeypatch):
    trusted, candidate = _replica_companion_roots(tmp_path, monkeypatch)
    binding = runner._private_replica_acceptance_binding(candidate, {"id": "CIMP-DUR-005"}, [])
    assert binding["required_supported"] is True
    assert binding["trusted_path"] == str(trusted / runner._PRIVATE_REPLICA_ACCEPTANCE)
    assert binding["candidate_path"] == str(candidate / runner._PRIVATE_REPLICA_ACCEPTANCE)
    import hashlib
    assert binding["sha256"] == hashlib.sha256(Path(binding["trusted_path"]).read_bytes()).hexdigest()


@pytest.mark.parametrize("damage", ["changed", "missing", "alias"])
def test_provider_cannot_weaken_or_remove_trusted_replica_checks(tmp_path, monkeypatch, damage):
    trusted, candidate = _replica_companion_roots(tmp_path, monkeypatch)
    path = candidate / runner._PRIVATE_REPLICA_ACCEPTANCE
    path.unlink()
    if damage == "changed":
        path.write_text("def test_replaced():\n    pass\n")
    elif damage == "alias":
        path.symlink_to(trusted / runner._PRIVATE_REPLICA_ACCEPTANCE)
    with pytest.raises(ValueError, match="trusted_replica_acceptance_changed"):
        runner._private_replica_acceptance_binding(candidate, {"id": "CIMP-DUR-005"}, [])


def _replica_capability_xml(values, *, include_identity=True):
    from xml.etree import ElementTree as ET
    suite = ET.Element("testsuite")
    case = ET.SubElement(suite, "testcase")
    properties = ET.SubElement(case, "properties")
    if include_identity:
        ET.SubElement(properties, "property", name="complaint_nodeid",
                      value=runner._PRIVATE_REPLICA_CAPABILITY_NODE)
    for value in values:
        ET.SubElement(properties, "property", name="private_replica_capability", value=value)
    return suite


def test_unsupported_baseline_is_explicit_but_cannot_satisfy_dur005():
    xml = _replica_capability_xml(["unsupported"])
    assert runner._private_replica_acceptance_capability(xml, {"required_supported": False}) == "unsupported"
    with pytest.raises(ValueError, match="private_replica_capability_unavailable"):
        runner._private_replica_acceptance_capability(xml, {"required_supported": True})


@pytest.mark.parametrize("values,identity", [([], True), (["supported", "supported"], True),
                                            (["true"], True), (["supported"], False)])
def test_replica_capability_cannot_omit_or_duplicate_actual_case_property(values, identity):
    with pytest.raises(ValueError, match="private_replica_capability_unavailable"):
        runner._private_replica_acceptance_capability(
            _replica_capability_xml(values, include_identity=identity), {"required_supported": True})


def test_unrelated_task_needs_no_replica_compatibility_file(tmp_path):
    assert runner._private_replica_kit_qualification(tmp_path, tmp_path / "evidence-runs", {"id": "OTHER"}, {}) is None


def test_dur005_requires_actual_host_kit_compatibility_binding(tmp_path):
    with pytest.raises(ValueError, match="private_replica_compatibility_unavailable"):
        runner._private_replica_kit_qualification(
            tmp_path / "candidate", tmp_path / "evidence-runs", {"id": "CIMP-DUR-005"}, {},
            campaign_state_dir=tmp_path)


@pytest.mark.parametrize("damage", ["group_writable", "alias"])
def test_kit_host_binding_rejects_unsafe_metadata_before_reader_import(tmp_path, damage):
    directory = tmp_path / "host-acceptance"
    directory.mkdir(mode=0o700)
    path = directory / "private-replica-kit.json"
    actual = tmp_path / "not-an-executable-reader.json"
    actual.write_text("{}")
    actual.chmod(0o600)
    if damage == "alias":
        path.symlink_to(actual)
    else:
        path.write_text("{}")
        path.chmod(0o620)
    with pytest.raises(ValueError, match="private_replica_compatibility_unavailable"):
        runner._private_replica_kit_qualification(
            tmp_path / "candidate", tmp_path / "evidence-runs", {"id": "CIMP-DUR-005"}, {},
            campaign_state_dir=tmp_path)


@pytest.mark.parametrize("damage", ["remove_test", "weaken_assertion", "change_fixture", "missing_module", "alias_module"])
def test_existing_regression_definitions_cannot_be_silently_replaced(tmp_path, damage):
    trusted, candidate = tmp_path / "trusted", tmp_path / "candidate"
    for root in (trusted, candidate):
        (root / "tests").mkdir(parents=True)
    original = "def fixture():\n    return 3\n\nclass TestEarlier:\n    def test_preserved(self):\n        assert fixture() == 3\n"
    (trusted / "tests/test_earlier.py").write_text(original)
    path = candidate / "tests/test_earlier.py"
    altered = original
    if damage == "remove_test":
        altered = "def test_new_only():\n    assert True\n"
    elif damage == "weaken_assertion":
        altered = original.replace("assert fixture() == 3", "assert True")
    elif damage == "change_fixture":
        altered = original.replace("return 3", "return 4")
    if damage == "alias_module":
        path.symlink_to(trusted / "tests/test_earlier.py")
    elif damage != "missing_module":
        path.write_text(altered)
    with pytest.raises(ValueError, match="existing_behavioral_definition_changed"):
        runner._preserve_existing_behavioral_definitions(candidate, ["tests/test_earlier.py"], trusted_root=trusted)


def test_existing_test_class_can_gain_checks_without_losing_earlier_definitions(tmp_path):
    trusted, candidate = tmp_path / "trusted", tmp_path / "candidate"
    for root in (trusted, candidate):
        (root / "tests").mkdir(parents=True)
    original = "class TestEarlier:\n    def test_preserved(self):\n        assert 2 + 2 == 4\n"
    (trusted / "tests/test_earlier.py").write_text(original)
    (candidate / "tests/test_earlier.py").write_text(original + "\n    def test_added(self):\n        assert 3 + 3 == 6\n")
    rows = runner._preserve_existing_behavioral_definitions(candidate, ["tests/test_earlier.py"], trusted_root=trusted)
    assert len(rows) == 1 and rows[0]["preserved_definition_count"] == 2
    assert rows[0]["trusted_sha256"] != rows[0]["candidate_sha256"]


def test_new_behavioral_test_module_needs_no_invented_previous_suite(tmp_path):
    trusted, candidate = tmp_path / "trusted", tmp_path / "candidate"
    trusted.mkdir();(candidate / "tests").mkdir(parents=True)
    (candidate / "tests/test_new.py").write_text("def test_new():\n    assert True\n")
    assert runner._preserve_existing_behavioral_definitions(candidate, ["tests/test_new.py"], trusted_root=trusted) == []
# Validation is allowed its own existing command deadline after the provider
# returns. These cases exercise the real Native watchdog, including its early
# provider-log check, while controlling the owned-child witness at the boundary.
@pytest.fixture
def validation_watchdog_case(tmp_path, monkeypatch):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
    now = time.time()
    stamp = lambda age: datetime.fromtimestamp(now - age, timezone.utc).isoformat()
    workspace_root = tmp_path / "workspaces"
    workspace = workspace_root / "owned"
    workspace.mkdir(parents=True)
    log = tmp_path / "provider.log"
    log.write_text("provider returned before bounded validation\n")
    os.utime(log, (now - 1000, now - 1000))
    state = native.PortalTaskState()
    for key, value in dict(active_phase="validating", implementation_in_progress=True,
            active_task_id="CIMP-QUEST-04", active_task_key="quest04-key",
            active_task_cid="bag-current-task", active_attempt=1,
            last_implementation_task_id="CIMP-QUEST-04",
            active_phase_started_at=stamp(100), last_implementation_started_at=stamp(1200),
            last_implementation_finished_at="", active_worktree_path=str(workspace),
            heartbeat_at=stamp(1000), last_progress_at=stamp(1000),
            last_implementation_log_path=str(log)).items():
        setattr(state, key, value)
    cls = runner._validation_aware_supervisor_class(native.PortalImplementationSupervisor)
    supervisor = object.__new__(cls)
    supervisor._worktree_worker_phase = ""
    supervisor._last_worktree_worker_seen_monotonic = None
    supervisor.config = SimpleNamespace(repo_root=ROOT, state_dir=tmp_path,
        state_path=tmp_path / "task_state.json", worktree_root=workspace_root,
        stale_seconds=180, check_interval=30, implementation_log_stall_seconds=180, state_prefix="test")
    monkeypatch.setattr(supervisor, "_implementation_watchdog_timeout_seconds", lambda: 900.0)
    scope = {"repo_root": str(ROOT), "state_dir": str(tmp_path)}
    birth = native.read_process_birth(os.getpid())
    identity = SimpleNamespace(process_birth=birth, command=native.read_process_command_argv(os.getpid()), owner_scope=scope)
    lease = dict(kind="implementation", lease_id="owned-lease", pid=os.getpid(),
        task_id=state.active_task_id, canonical_task_key=state.active_task_key,
        canonical_task_cid=state.active_task_cid, attempt=1, repo_root=str(ROOT), state_dir=str(tmp_path))
    claim = dict(lease, kind=native.IMPLEMENTATION_TASK_CLAIM_LOCK_KIND,
        lease_role=native.IMPLEMENTATION_DISPATCH_INTENT_LEASE_ROLE,
        owner_process_birth=birth.to_dict(), state_path=str(supervisor.config.state_path))
    claim["dispatch_authority_cid"] = native.PortalImplementationDaemon._implementation_dispatch_authority_cid(claim)
    monkeypatch.setattr(supervisor, "_implementation_maintenance_lock_path", lambda: tmp_path / "lease")
    monkeypatch.setattr(supervisor, "_task_dispatch_claim_path", lambda s: tmp_path / "claim")
    monkeypatch.setattr(supervisor, "_managed_daemon_identity_path", lambda: tmp_path / "identity")
    monkeypatch.setattr(runner, "_read_validation_watchdog_authority", lambda p: lease if p.name == "lease" else claim)
    monkeypatch.setattr(supervisor, "_managed_daemon_owner_scope", lambda: scope)
    monkeypatch.setattr(supervisor, "_build_daemon_command", lambda: list(identity.command))
    monkeypatch.setattr(native, "load_supervised_child_identity", lambda p: identity)
    monkeypatch.setattr(native, "checkout_lock_repository_matches", lambda c, r: True)
    monkeypatch.setattr(supervisor, "_active_validation_subprocess_exists", lambda: True)
    return native, supervisor, state, lease, claim, identity, now


def test_validation_watchdog_keeps_current_owned_tests_after_provider_deadline(validation_watchdog_case):
    native, supervisor, state, lease, claim, identity, now = validation_watchdog_case
    assert native.PortalImplementationSupervisor._implementation_attempt_is_active(supervisor, state, now_ts=now) is False
    before = dict(vars(state))
    assert supervisor._implementation_log_stall_reason(state, now_ts=now) == ""
    assert supervisor.is_stuck(state, now_ts=now) == (False, "")
    assert vars(state) == before


@pytest.mark.parametrize("change", ["expired", "future", "other_phase", "wrong_task", "wrong_cid",
    "wrong_attempt", "finished", "outside_worktree", "no_worker", "wrong_owner", "missing_claim"])
def test_validation_watchdog_refuses_unowned_or_expired_window(validation_watchdog_case, monkeypatch, change, tmp_path):
    native, supervisor, state, lease, claim, identity, now = validation_watchdog_case
    if change == "expired": state.active_phase_started_at = datetime.fromtimestamp(now - 901, timezone.utc).isoformat()
    elif change == "future": state.active_phase_started_at = datetime.fromtimestamp(now + 1, timezone.utc).isoformat()
    elif change == "other_phase": state.active_phase = "implementing"
    elif change == "wrong_task": claim["task_id"] = "CIMP-OTHER-01"
    elif change == "wrong_cid": claim["canonical_task_cid"] = "bag-another-task"
    elif change == "wrong_attempt": claim["attempt"] = 2
    elif change == "finished": state.last_implementation_finished_at = datetime.fromtimestamp(now - 10, timezone.utc).isoformat()
    elif change == "outside_worktree": state.active_worktree_path = str(tmp_path)
    elif change == "no_worker": monkeypatch.setattr(supervisor, "_active_validation_subprocess_exists", lambda: False)
    elif change == "wrong_owner": identity.owner_scope = {"state_dir": "/unrelated"}
    elif change == "missing_claim": monkeypatch.setattr(runner, "_read_validation_watchdog_authority", lambda p: None)
    assert runner._owned_validation_window(supervisor, state, now_ts=now) is False
    assert supervisor.is_stuck(state, now_ts=now)[0] is True


def test_validation_watchdog_preserves_original_provider_window(validation_watchdog_case, monkeypatch):
    native, supervisor, state, lease, claim, identity, now = validation_watchdog_case
    state.last_implementation_started_at = datetime.fromtimestamp(now - 10, timezone.utc).isoformat()
    def unexpected_probe(*args, **kwargs):
        pytest.fail("a live provider attempt must use its original Native predicate")
    monkeypatch.setattr(runner, "_owned_validation_window", unexpected_probe)
    assert supervisor._implementation_attempt_is_active(state, now_ts=now) is True



def test_validation_adapter_uses_native_configuration_and_exactly_one_native_loop(tmp_path, monkeypatch):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor_runner as lifecycle
    construction = []
    loops = []
    instance = object()
    def adapter_class(original):
        assert original is native.PortalImplementationSupervisor
        def construct(config):
            construction.append(config)
            return instance
        return construct
    def loop(supervisor, context, *, logger):
        assert supervisor is instance
        loops.append(context)
        return "native-loop-result"
    monkeypatch.setattr(runner, "_validation_aware_supervisor_class", adapter_class)
    monkeypatch.setattr(lifecycle, "run_portal_implementation_supervisor", loop)
    argv = runner.native_argv(ROOT / "docs/task_boards/complaint_intake_improvement.md", tmp_path, "main", worktree_root=tmp_path / "workspaces")
    result = runner._run_native_supervisor(argv, repo_root=ROOT, logger=runner._LOGGER, daemon_script_path=Path(runner.__file__))
    assert result == "native-loop-result" and len(construction) == len(loops) == 1
    config, context = construction[0], loops[0]
    assert context.config is config and context.parsed.once is False
    assert config.repo_root == ROOT and config.state_dir == tmp_path
    assert config.implementation_timeout == config.implementation_max_timeout == 900
    assert config.max_task_attempts == 3 and config.max_restarts == 5
    assert tuple(config.worktree_submodule_paths) == ("external/ipfs_datasets_py", "external/ipfs_kit_py")
    assert context.state_path == config.state_path and context.events_path == config.events_path
    assert context.daemon_events_path.parent == tmp_path


@pytest.mark.parametrize("mode", [0o600, 0o640, 0o664, 0o775])
def test_validation_authority_reads_real_native_lease_modes_without_mutating_them(tmp_path, mode):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
    path = tmp_path / "native-lease.json"
    payload = {"kind": "implementation", "pid": os.getpid(), "attempt": 2}
    path.write_text(json.dumps(payload))
    path.chmod(mode)
    before = (path.read_bytes(), path.stat())
    assert runner._read_validation_watchdog_authority(path) == payload
    if mode & 0o020:
        assert native.PortalImplementationSupervisor._read_watchdog_authority(path) is None
    after = path.stat()
    assert path.read_bytes() == before[0]
    assert (after.st_ino, after.st_mode, after.st_mtime_ns, after.st_ctime_ns) == (before[1].st_ino, before[1].st_mode, before[1].st_mtime_ns, before[1].st_ctime_ns)


@pytest.mark.parametrize("damage", ["world_writable", "alias", "hardlink", "oversized", "nonobject", "invalid_json", "fifo", "missing"])
def test_validation_authority_refuses_unproven_native_lease_files(tmp_path, damage):
    path = tmp_path / "lease.json"
    path.write_text('{"kind":"implementation"}')
    path.chmod(0o600)
    if damage == "world_writable": path.chmod(0o777)
    elif damage == "alias":
        alias = tmp_path / "alias.json"
        alias.symlink_to(path)
        path = alias
    elif damage == "hardlink": os.link(path, tmp_path / "other.json")
    elif damage == "oversized": path.write_text(" " * 65537)
    elif damage == "nonobject": path.write_text("[]")
    elif damage == "invalid_json": path.write_text("{")
    elif damage == "fifo":
        path.unlink()
        os.mkfifo(path, 0o600)
    elif damage == "missing": path.unlink()
    assert runner._read_validation_watchdog_authority(path) is None


def test_campaign_validation_returns_without_full_campaign_readiness_scan(tmp_path, monkeypatch):
    def forbidden_scan(*args, **kwargs):
        pytest.fail("full-campaign readiness must stay outside current Native validation")
    monkeypatch.setattr(runner, "recompute_dependent_readiness", forbidden_scan)
    monkeypatch.setattr(runner, "_source_freeze", forbidden_scan)
    delegated = []
    class NativeScheduler:
        def run(self, commands, **kwargs):
            delegated.append(tuple(commands))
            return {"passed": False, "returncode": 41, "results": []}
    scheduler = runner.EvidenceValidationScheduler(NativeScheduler(), state_dir=tmp_path / "state", spec=_spec(), defer_readiness=True)
    scheduler.bind_task(SimpleNamespace(task_id="CIMP-TUI-01"), tmp_path)
    result = scheduler.run(["python -m pytest -q tests/test_terminal_contract.py"], workspace_path=tmp_path)
    assert len(delegated) == 1 and result["passed"] is False and result["returncode"] == 41
    assert result["dependent_readiness"] == {"available": False, "reason": "deferred_outside_validation", "native_scheduling_enforced": False, "completion_authority": False}
    assert not (tmp_path / "state/evidence/readiness.json").exists()


def test_standalone_validation_keeps_explicit_readiness_observation(tmp_path, monkeypatch):
    calls = []
    class NativeScheduler:
        def run(self, commands, **kwargs):
            return {"passed": False, "returncode": 41, "results": []}
    monkeypatch.setattr(runner, "_source_freeze", lambda *a: {"dependencies": {"external/ipfs_datasets_py": {"head": "synthetic-legal-revision"}}})
    def observe(*args, **kwargs):
        calls.append(kwargs["legal_data_version"])
        return {"available": True, "completion_authority": False}
    monkeypatch.setattr(runner, "recompute_dependent_readiness", observe)
    scheduler = runner.EvidenceValidationScheduler(NativeScheduler(), state_dir=tmp_path / "state", spec=_spec())
    scheduler.bind_task(SimpleNamespace(task_id="CIMP-TUI-01"), tmp_path)
    result = scheduler.run(["python -m pytest -q tests/test_terminal_contract.py"], workspace_path=tmp_path)
    assert calls == ["synthetic-legal-revision"] and result["passed"] is False
    assert result["dependent_readiness"] == {"available": True, "completion_authority": False}


def test_production_daemon_uses_deferred_readiness(tmp_path, monkeypatch):
    captured = []
    monkeypatch.setattr(runner, "_run_evidence_daemon_adapter", lambda argv, **kwargs: captured.append(kwargs) or 17)
    argv = ["--todo-path", str(ROOT / "docs/task_boards/complaint_intake_improvement.md"), "--state-dir", str(tmp_path), "--implementation-timeout", "900", "--validation-max-workers", "1"]
    assert runner.evidence_daemon_main(argv) == 17
    scheduler = captured[0]["validation_scheduler"]
    assert scheduler.defer_readiness is True and scheduler.state_dir == tmp_path
    assert captured[0]["proof_workflow"].__self__ is scheduler


def test_orphan_reconciliation_keeps_measured_validation_and_binds_native_task(tmp_path):
    native_scheduler = object()
    daemon = SimpleNamespace(validation_scheduler=native_scheduler, proof_workflow=None)
    construction = []
    class NativeSupervisor:
        def _build_worktree_reconciliation_daemon(self):
            construction.append(True)
            return daemon
    supervisor = runner._validation_aware_supervisor_class(NativeSupervisor)()
    supervisor.config = SimpleNamespace(repo_root=ROOT, state_dir=tmp_path)
    assert supervisor._build_worktree_reconciliation_daemon() is daemon
    scheduler = daemon.validation_scheduler
    assert construction == [True] and isinstance(scheduler, runner.EvidenceValidationScheduler)
    assert scheduler.native_scheduler is native_scheduler and scheduler.defer_readiness is True
    task = SimpleNamespace(task_id="CIMP-QUEST-04")
    assert daemon.proof_workflow(task, tmp_path) == {}
    assert scheduler.bound_task == (task, tmp_path.resolve())
    assert len(scheduler.spec["tasks"]) == 58


@pytest.fixture
def uncommitted_reconciliation_case(campaign, monkeypatch):
    from integrations.ipfs_accelerate.improvement_plan import BOARD_RELATIVE
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_supervisor import PortalImplementationSupervisor
    root, spec, state, generated = campaign
    state.mkdir()
    workroot = root / "owned-worktrees"
    workspace = workroot / "pending"
    workspace.mkdir(parents=True)
    launch = _owner(state)
    launch.update(repo_root=str(root), state_dir=str(state), worktree_root=str(workroot))
    launch["identity"]["pid"] = os.getpid()
    runner._atomic_json(state / "launcher.json", launch)
    monkeypatch.setattr(runner, "owns_process", lambda record: True)
    monkeypatch.setattr(runner, "recorded_worktree_root", lambda record, state_dir: (workroot, {"unit_binding": True}))
    calls = []
    records = [{"worktree": str(workspace), "branch": "refs/heads/implementation/cimp-tui-01-attempt-1", "HEAD": "baseline"}]
    behavior = {"owner": None, "commands": [], "dirty": [" M tests/test_terminal_contract.py"], "merged": True, "preserved": True, "integrated": True}
    class NativeSupervisor:
        _worktree_branch_is_reconcilable = staticmethod(PortalImplementationSupervisor._worktree_branch_is_reconcilable)
        _worktree_branch_source_task_id = staticmethod(PortalImplementationSupervisor._worktree_branch_source_task_id)
        def _git_worktree_records(self, repo): return records
        def _shared_active_worktree_owners(self, path): return {}
        def _list_process_commands(self): return behavior["commands"]
        def _git_ref_is_ancestor(self, *args): return behavior["merged"]
        def _git_status_short(self, path): return behavior["dirty"]
        def _active_worktree_skip_detail(self, path, owners): return behavior["owner"]
        def _rescue_dirty_worktree(self, path, **kwargs):
            calls.append(("rescue", path, kwargs))
            return {"preserved": behavior["preserved"], "path": str(path), "rescue_branch": "rescue/worktree/cimp-tui-01"}
        def reconcile_backlogged_worktrees(self, **kwargs):
            calls.append(("scan", kwargs))
            return {"attempted": True, "processed": [{"path": str(workspace), "merged": behavior["integrated"]}]}
    supervisor = runner._validation_aware_supervisor_class(NativeSupervisor)()
    supervisor.config = SimpleNamespace(repo_root=root, state_dir=state, worktree_root=workroot,
        todo_path=root / BOARD_RELATIVE, task_prefix=runner.TASK_PREFIX, merge_target_branch="main")
    lease = {"pid": os.getpid(), "lease_role": "supervisor_maintenance"}
    supervisor._held_implementation_maintenance_lease = lease
    return supervisor, lease, workspace, workroot, records, behavior, calls, launch


def test_uncommitted_proposal_on_integrated_baseline_is_preserved_before_native_scan(uncommitted_reconciliation_case):
    supervisor, lease, workspace, workroot, records, behavior, calls, launch = uncommitted_reconciliation_case
    result = supervisor.reconcile_backlogged_worktrees(preacquired_implementation_lock=lease)
    assert [call[0] for call in calls] == ["rescue", "scan"]
    assert calls[0][1] == workspace and calls[0][2]["head"] == "baseline"
    assert calls[0][2]["reason"] == "reconciliation_uncommitted_integrated_base"
    assert calls[1][1]["preacquired_implementation_lock"] is lease
    assert result["owned_uncommitted_candidates_preserved"] == [{"preserved": True, "path": str(workspace), "rescue_branch": "rescue/worktree/cimp-tui-01"}]


@pytest.mark.parametrize("condition", ["active_owner", "active_command", "foreign_path", "foreign_branch", "clean", "unowned_supervisor", "not_merged", "dependency_only"])
def test_uncommitted_reconciliation_prepass_respects_ownership_and_scope(uncommitted_reconciliation_case, condition):
    supervisor, lease, workspace, workroot, records, behavior, calls, launch = uncommitted_reconciliation_case
    if condition == "active_owner": behavior["owner"] = {"reason": "live_owner"}
    elif condition == "active_command": behavior["commands"] = ["python " + str(workspace)]
    elif condition == "foreign_path": records[0]["worktree"] = str(workroot.parent)
    elif condition == "foreign_branch": records[0]["branch"] = "refs/heads/user-work"
    elif condition == "clean": behavior["dirty"] = []
    elif condition == "dependency_only": behavior["dirty"] = [" M external/ipfs_accelerate_py"]
    elif condition == "unowned_supervisor": supervisor._held_implementation_maintenance_lease = None
    elif condition == "not_merged": behavior["merged"] = False
    result = supervisor.reconcile_backlogged_worktrees(preacquired_implementation_lock=lease)
    assert [call[0] for call in calls] == ["scan"]
    assert result["owned_uncommitted_candidates_preserved"] == []


def test_unpreservable_pending_proposal_blocks_dispatch_before_native_scan(uncommitted_reconciliation_case):
    supervisor, lease, workspace, workroot, records, behavior, calls, launch = uncommitted_reconciliation_case
    behavior["preserved"] = False
    with pytest.raises(RuntimeError, match="candidate preservation is required"):
        supervisor.reconcile_backlogged_worktrees(preacquired_implementation_lock=lease)
    assert [call[0] for call in calls] == ["rescue"]


def test_preserved_candidate_must_pass_native_recovery_before_another_provider_dispatch(uncommitted_reconciliation_case):
    supervisor, lease, workspace, workroot, records, behavior, calls, launch = uncommitted_reconciliation_case
    behavior["integrated"] = False
    with pytest.raises(RuntimeError, match="requires Native recovery before provider dispatch"):
        supervisor.reconcile_backlogged_worktrees(preacquired_implementation_lock=lease)
    assert [call[0] for call in calls] == ["rescue", "scan"]


def test_orphan_recovery_retains_the_configured_validation_worker_and_time_budgets(tmp_path):
    from ipfs_accelerate_py.agent_supervisor.validation.validation_scheduler import ValidationScheduler
    original = ValidationScheduler(max_workers=2, resource_budget=2, default_timeout_seconds=1800)
    daemon = SimpleNamespace(validation_scheduler=original, proof_workflow=None)
    class NativeSupervisor:
        def _build_worktree_reconciliation_daemon(self): return daemon
    supervisor = runner._validation_aware_supervisor_class(NativeSupervisor)()
    supervisor.config = SimpleNamespace(repo_root=ROOT, state_dir=tmp_path,
        validation_max_workers=1, validation_resource_budget=1, implementation_timeout=900)
    supervisor._build_worktree_reconciliation_daemon()
    scheduler = daemon.validation_scheduler.native_scheduler
    assert scheduler.max_workers == 1 and scheduler.resource_budget == 1
    assert scheduler.default_timeout_seconds == 900
    assert scheduler.cache is original.cache


@pytest.mark.parametrize("owner_alive", [False, True])
def test_real_native_maintenance_handoff_reads_legacy_mode_without_stealing_live_owner(tmp_path, monkeypatch, owner_alive):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
    cls = runner._validation_aware_supervisor_class(native.PortalImplementationSupervisor)
    supervisor = object.__new__(cls)
    supervisor.config = SimpleNamespace(repo_root=ROOT, state_dir=tmp_path, state_path=tmp_path / "state.json")
    old = {"kind": "implementation", "pid": 991119, "lease_id": "ordinary-owned-lease", "repo_root": str(ROOT), "state_dir": str(tmp_path), "attempt": 3}
    current = {"kind": "implementation", "pid": os.getpid(), "lease_id": "new-maintenance-lease", "repo_root": str(ROOT), "state_dir": str(tmp_path), "lease_role": "supervisor_maintenance"}
    path = tmp_path / "implementation.lock"
    path.write_text(json.dumps(old))
    path.chmod(0o775)
    before = path.read_bytes()
    monkeypatch.setattr(supervisor, "_implementation_maintenance_lease_metadata", lambda: current)
    def alive(pid):
        assert pid == old["pid"]
        return owner_alive
    monkeypatch.setattr(native, "process_is_running", alive)
    lease, guard = supervisor._acquire_implementation_maintenance_lease()
    if owner_alive:
        assert lease is None and guard["reason"] == "implementation_protected_path_attempt_active"
        assert path.read_bytes() == before and path.stat().st_mode & 0o777 == 0o775
    else:
        assert lease == current and guard["reason"] == "implementation_maintenance_lease_acquired"
        assert json.loads(path.read_text()) == current
        supervisor._release_implementation_maintenance_lease(lease)
        assert not path.exists()


@pytest.mark.parametrize("damage", ["world_writable", "wrong_scope"])
def test_real_native_maintenance_still_refuses_unproven_ordinary_lease(tmp_path, damage):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
    supervisor = object.__new__(runner._validation_aware_supervisor_class(native.PortalImplementationSupervisor))
    supervisor.config = SimpleNamespace(repo_root=ROOT, state_dir=tmp_path, state_path=tmp_path / "state.json")
    path = tmp_path / "implementation.lock"
    old = {"kind": "implementation", "pid": 991119, "lease_id": "legacy", "repo_root": str(ROOT if damage != "wrong_scope" else tmp_path), "state_dir": str(tmp_path)}
    path.write_text(json.dumps(old))
    path.chmod(0o777 if damage == "world_writable" else 0o775)
    current = {"kind": "implementation", "pid": os.getpid(), "lease_id": "next", "repo_root": str(ROOT), "state_dir": str(tmp_path), "lease_role": "supervisor_maintenance"}
    before = path.read_bytes()
    lease, guard = supervisor._acquire_implementation_maintenance_lease_serialized(path, current)
    assert lease is None and guard["reason"] == "implementation_maintenance_lease_owner_unproven"
    assert path.read_bytes() == before


@pytest.mark.parametrize("blocked", [True, False])
def test_startup_preflight_cannot_fall_through_to_worker_dispatch(blocked):
    trace = []
    class NativeSupervisor:
        def run_once(self, *, include_refill=True):
            assert include_refill is False
            return {"maintenance_blocked": blocked, "reason": "synthetic_lease_scope"}
        def _run_forever_loop(self):
            trace.append("preflight")
            self.run_once(include_refill=False)
            trace.append("dispatch")
            return "running"
    supervisor = runner._validation_aware_supervisor_class(NativeSupervisor)()
    if blocked:
        with pytest.raises(RuntimeError, match="Native startup preflight blocked"):
            supervisor._run_forever_loop()
        assert trace == ["preflight"]
    else:
        assert supervisor._run_forever_loop() == "running"
        assert trace == ["preflight", "dispatch"]


def test_live_worker_maintenance_deferral_after_preflight_is_not_a_startup_failure():
    outcomes = [{"maintenance_blocked": False}, {"maintenance_blocked": True, "reason": "implementation_protected_path_attempt_active"}]
    class NativeSupervisor:
        def run_once(self, **kwargs): return outcomes.pop(0)
        def _run_forever_loop(self): return self.run_once(include_refill=False)
    supervisor = runner._validation_aware_supervisor_class(NativeSupervisor)()
    assert supervisor._run_forever_loop() == {"maintenance_blocked": False}
    assert supervisor.run_once()["reason"] == "implementation_protected_path_attempt_active"


@pytest.mark.parametrize("damage", [None, "author", "committer", "parent", "subject", "branch", "reason", "event_commit", "event_branch", "event_rejected", "event_missing", "task"])
def test_rescue_receipt_provenance_requires_exact_native_attestation(damage):
    baseline, commit = "a" * 40, "b" * 40
    original = "implementation/cimp-quest-04-attempt-2-123"
    rescue = "rescue/worktree/" + original.replace("/", "-") + "-abcdef"
    raw = (f"tree {'c' * 40}\nparent {baseline}\nauthor Implementation Supervisor <implementation-supervisor@example.invalid> 1 +0000\n"
           "committer Implementation Supervisor <implementation-supervisor@example.invalid> 1 +0000\n\n"
           f"Rescue dirty worktree {original}\n\nOriginal branch: {original}\n\nOriginal HEAD: {baseline}\n\n"
           "Cleanup reason: reconciliation_uncommitted_integrated_base\n")
    event = {"type": "dirty_worktree_rescued", "preserved": True, "returncode": 0,
        "branch": original, "head": baseline, "rescue_branch": rescue, "rescue_commit": commit}
    if damage in {"author", "committer"}:
        raw = raw.replace(damage + " Implementation Supervisor <implementation-supervisor@example.invalid>", damage + " Other <other@example.invalid>")
    elif damage == "parent": raw = raw.replace("parent " + baseline, "parent " + "d" * 40)
    elif damage == "subject": raw = raw.replace("Rescue dirty worktree", "Untrusted snapshot")
    elif damage == "branch": raw = raw.replace("Original branch: " + original, "Original branch: implementation/foreign")
    elif damage == "reason": raw = raw.replace("reconciliation_uncommitted_integrated_base", "unknown_reason")
    elif damage == "event_commit": event["rescue_commit"] = "d" * 40
    elif damage == "event_branch": event["branch"] = "implementation/foreign"
    elif damage == "event_rejected": event["preserved"] = False
    events = [] if damage == "event_missing" else [event]
    answer = runner._rescue_original_branch_from_attestation(task_id="CIMP-PRIV-005" if damage == "task" else "CIMP-QUEST-04",
        branch=rescue, baseline=baseline, commit=commit, raw_commit=raw, events=events)
    assert answer == (original if damage is None else None)


@pytest.mark.parametrize("ordinary_segment,attested", [(True, True), (False, True), (False, False)])
def test_rescue_adapter_delegates_receipt_admission_to_native(monkeypatch, ordinary_segment, attested):
    calls = []
    original = "implementation/cimp-quest-04-attempt-2"
    rescue = "rescue/worktree/cimp-quest-04"
    original_receipts = ({"proposal_id": "native-content-addressed", "policy_id": "native-policy", "receipt_id": "native-receipt"},)
    class NativeDaemon:
        def _reconciliation_accepted_proposal_context(self, *, task, branch_name, baseline_ref):
            calls.append(branch_name)
            return {"segment_found": ordinary_segment or branch_name == original,
                "accepted_receipts": original_receipts if branch_name == original else ()}
    monkeypatch.setattr(runner, "_owned_rescue_original_branch", lambda *args: original if attested else None)
    daemon = runner._rescue_receipt_daemon_class(NativeDaemon, object())()
    answer = daemon._reconciliation_accepted_proposal_context(task=object(), branch_name=rescue, baseline_ref="a" * 40)
    expected = [rescue, original] if attested and not ordinary_segment else [rescue]
    assert calls == expected
    assert answer["accepted_receipts"] is original_receipts if len(expected) == 2 else answer["accepted_receipts"] == ()


@pytest.mark.parametrize("merged", [True, False])
def test_startup_cannot_dispatch_past_an_unresolved_recovery_candidate(merged):
    dispatched = []
    class NativeSupervisor:
        def run_once(self, **kwargs):
            return {"worktree_reconciliation": {"processed": [{"path": "/owned/candidate", "merged": merged}]}}
        def _run_forever_loop(self):
            self.run_once(include_refill=False)
            dispatched.append(True)
    supervisor = runner._validation_aware_supervisor_class(NativeSupervisor)()
    if merged:
        supervisor._run_forever_loop()
        assert dispatched == [True]
    else:
        with pytest.raises(RuntimeError, match="candidate recovery remains unresolved"):
            supervisor._run_forever_loop()
        assert dispatched == []


def test_real_native_recovery_instance_keeps_identity_and_native_receipt_checks(monkeypatch, tmp_path):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    daemon = object.__new__(native.PortalImplementationDaemon)
    daemon.todo_path = tmp_path / "board.md"
    daemon.implement = False
    task = native.PortalTask(task_id="CIMP-QUEST-04", title="Synthetic recovery", status="todo", completion="manual", priority="P1", track="ops",
        outputs=("tests/test_synthetic.py",), acceptance=("Synthetic case passes",))
    identity = daemon._identity_for_task(task)
    original = "implementation/cimp-quest-04-attempt-2"
    baseline = "a" * 40
    events = [
        {"type":"implementation_started","task_id":task.task_id,"branch":original,"baseline_ref":baseline,
            "canonical_task_key":identity.canonical_task_key,"canonical_task_cid":identity.canonical_task_cid,
            "board_namespace":identity.board_namespace},
        {"type":"implementation_proposal_validated","accepted":True,"task_id":task.task_id,
            "proposal_id":"proposal","policy_id":"policy","receipt_id":"receipt",
            "repository_tree_id":baseline,"changed_paths":["tests/test_synthetic.py"]},
    ]
    daemon._iter_events = lambda: iter(events)
    expected = daemon._reconciliation_accepted_proposal_context(task=task, branch_name=original, baseline_ref=baseline)
    assert expected["segment_found"] and not expected["segment_mismatches"]
    before = (id(daemon), dict(daemon.__dict__))
    monkeypatch.setattr(runner, "_owned_rescue_original_branch", lambda *args: original)
    daemon.__class__ = runner._rescue_receipt_daemon_class(type(daemon), object())
    observed = daemon._reconciliation_accepted_proposal_context(task=task,
        branch_name="rescue/worktree/synthetic", baseline_ref=baseline)
    assert observed == expected and (id(daemon), daemon.__dict__) == before
    mismatch = daemon._reconciliation_accepted_proposal_context(task=task,
        branch_name="rescue/worktree/synthetic", baseline_ref="f" * 40)
    assert mismatch["segment_mismatches"] == ("repository_tree_id",)


def test_invalid_monitor_window_cannot_start_an_unmonitored_runner(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "start", lambda *_a, **_k: pytest.fail("invalid monitor window started a runner"))
    result = runner.main(["start", "--watch", "--monitor-seconds", "nan", "--repo-root", str(ROOT), "--state-dir", str(tmp_path)])
    assert result == 2


@pytest.mark.parametrize("damage", [None, "reopened", "revision", "no_branch_event", "unknown_reason", "unfinished"])
def test_native_completed_candidate_is_retained_without_blocking_startup(tmp_path, monkeypatch, damage):
    import subprocess
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as daemon_native
    from ipfs_accelerate_py.agent_supervisor.task_sources.persistent_task_queue import PersistentTaskQueue

    root, worktrees, state = (tmp_path / name for name in ("repo", "worktrees", "state"))
    root.mkdir(); worktrees.mkdir(); state.mkdir()
    def git(*args, cwd=root):
        return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()
    git("init", "-q", "-b", "main")
    git("config", "user.name", "Synthetic startup fixture")
    git("config", "user.email", "synthetic@example.invalid")
    board = root / "board.md"
    board_text = ("# Synthetic tasks\n\n## CIMP-MGND-01 Retained candidate\n\n"
        "- Status: " + ("ready" if damage == "unfinished" else "completed") + "\n"
        "- Completion: manual\n- Priority: P1\n- Track: ops\n"
        "- Outputs: out/task.py\n- Acceptance: A synthetic check passes.\n")
    board.write_text(board_text)
    git("add", "board.md"); git("commit", "-qm", "Synthetic completed board")
    original = "rescue/worktree/implementation-cimp-mgnd-01-synthetic"
    leaf = worktrees / "retained"
    git("worktree", "add", "-q", "-b", original, str(leaf), "HEAD")
    (leaf / "retained.txt").write_text("Preserve the original candidate.\n")
    git("add", "retained.txt", cwd=leaf); git("commit", "-qm", "Synthetic retained candidate", cwd=leaf)
    candidate = git("rev-parse", "HEAD", cwd=leaf)
    daemon = object.__new__(daemon_native.PortalImplementationDaemon)
    daemon.task_source = None
    daemon.todo_path = board
    daemon.task_header_prefix = "CIMP-"
    daemon.task_queue = PersistentTaskQueue()
    event = {"type": "worktree_reconciliation_validation_started", "task_id": "CIMP-MGND-01", "branch": original}
    daemon._iter_events = lambda: iter([] if damage == "no_branch_event" else [event])
    daemon.reconcile_validated_worktree_candidate = lambda **kwargs: {
        "merge_result": {"attempted": False, "merged": False, "reason": "synthetic_validation_rejected"}}
    observed, dispatched = [], []

    class Startup(native.PortalImplementationSupervisor):
        def run_once(self, *, include_refill=True):
            result = self.reconcile_backlogged_worktrees()
            observed.append(result)
            if damage == "reopened":
                board.write_text(board_text.replace("Status: completed", "Status: ready"))
            elif damage == "revision":
                board.write_text(board_text.replace("out/task.py", "out/changed.py"))
            elif damage == "unknown_reason":
                result["processed"][0]["merge_result"]["reason"] = "unknown_terminal_claim"
            return {"worktree_reconciliation": result}

        def _run_forever_loop(self):
            self.run_once(include_refill=False)
            dispatched.append(True)

    supervisor = object.__new__(runner._validation_aware_supervisor_class(Startup))
    supervisor.config = SimpleNamespace(repo_root=root, state_dir=state, state_path=state / "task-state.json",
        state_prefix="synthetic", worktree_root=worktrees, todo_path=board, task_prefix="CIMP-",
        merge_target_branch="main", worktree_reconciliation_enabled=True,
        worktree_reconciliation_max_merges=1, worktree_reconciliation_dry_run=False,
        worktree_reconciliation_preflight_enabled=False, worktree_scan_cache_enabled=False,
        worktree_scan_cache_ttl_seconds=0)
    monkeypatch.setattr(supervisor, "_build_worktree_reconciliation_daemon", lambda: daemon)
    monkeypatch.setattr(supervisor, "_list_process_commands", lambda: [])
    monkeypatch.setattr(supervisor, "_shared_active_worktree_owners", lambda path: {})
    monkeypatch.setattr(supervisor, "_record_event", lambda *_args: None)
    if damage is None:
        supervisor._run_forever_loop()
        assert dispatched == [True]
        assert supervisor._complaint_startup_reconciliation_context is None
    else:
        with pytest.raises(RuntimeError, match="candidate recovery remains unresolved"):
            supervisor._run_forever_loop()
        assert dispatched == []
    row = observed[0]["processed"][0]
    assert row["merged"] is False and row["merge_result"]["attempted"] is False
    if damage not in {"unknown_reason", "unfinished"}:
        assert row["merge_result"]["reason"] == "reconciliation_candidate_task_already_completed"
    assert leaf.is_dir() and git("rev-parse", original) == candidate
    assert (leaf / "retained.txt").read_text() == "Preserve the original candidate.\n"
