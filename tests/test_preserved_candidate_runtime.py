"""Real tiny Git worktrees/clones; synthetic SDK receipt protocol, no admission."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner
from integrations.ipfs_accelerate import preserved_candidate_runtime as runtime
from ipfs_accelerate_py.agent_supervisor.merge.worktree_lifecycle import WorktreeLifecycleStore
from ipfs_accelerate_py.agent_supervisor.todo_daemon import engine

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
TARGETS = ("mediator/hook_runtime.py", "applications/complaint_workspace.py", "tests/test_cimp_gui_34.py")
DEPS = ("external/ipfs_accelerate_py", "external/ipfs_datasets_py", "external/ipfs_kit_py")


def git(root, *args, binary=False):
    value = subprocess.check_output(["git", "-c", "core.hooksPath=/dev/null", *args], cwd=root)
    return value if binary else value.decode().strip()


def commit(root, message):
    git(root, "add", "-A")
    git(root, "-c", "user.name=Synthetic", "-c", "user.email=synthetic@example.invalid", "commit", "-qm", message)
    return git(root, "rev-parse", "HEAD")


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def publish(w):
    w.candidate["source_manifest_sha256"] = hashlib.sha256(encoded(w.receipt["request"]["candidate"])).hexdigest()
    w.receipt["preserved_candidate"] = deepcopy(w.candidate)
    w.receipt["operation_id"] = "sha256:" + hashlib.sha256(encoded(w.receipt["request"])).hexdigest()
    body = {k: v for k, v in w.receipt.items() if k != "receipt_id"}
    w.receipt["receipt_id"] = "sha256:" + hashlib.sha256(encoded(body)).hexdigest()
    w.proof.write_bytes(encoded(w.receipt) + b"\n"); w.proof.chmod(0o600)
    w.kwargs = {"root_base": w.base, "receipt_id": w.receipt["receipt_id"],
                "receipt_sha256": hashlib.sha256(w.proof.read_bytes()).hexdigest()}


@pytest.fixture
def world(tmp_path):
    from tests.test_improvement_recovery import _spec_text
    root, state = tmp_path / "root", tmp_path / "state"
    root.mkdir(); state.mkdir(mode=0o700); (state / "worktrees").mkdir(mode=0o700)
    git(root, "init", "-q")
    for index, relative in enumerate(TARGETS):
        path = root / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(f"BEFORE = {index}\n".encode())
    (root / "runtime.py").write_text("HOST_RUNTIME = 'original'\n")
    pins = {}
    for index, relative in enumerate(DEPS):
        path = root / relative; path.mkdir(parents=True)
        git(path, "init", "-q"); (path / "runtime.py").write_text(f"DEPENDENCY = {index}\n")
        (path / "package").mkdir(); (path / "package/module.py").write_text(f"NESTED_RUNTIME = {index}\n")
        (path / "docs").mkdir(); (path / "docs/archive.txt").write_text("Archived documentation is not runtime.\n")
        pins[relative] = commit(path, "dependency")
        git(path, "remote", "add", "origin", f"https://example.invalid/sdk-{index}.git")
        git(root, "update-index", "--add", "--cacheinfo", "160000," + pins[relative] + "," + relative)
    spec = root / "spec.json"; value = json.loads(_spec_text()); value["tasks"][0]["targets"] = list(TARGETS)
    spec.write_text(json.dumps(value)); baseline = commit(root, "baseline")
    original = state / "worktrees/original"
    git(root, "worktree", "add", "-b", "implementation/cimp-ops-03-attempt-1", str(original), baseline)
    for index, relative in enumerate(TARGETS):
        (original / relative).write_bytes(b"\x00BINARY\xff\n" if index == 1 else f"AFTER = {index}\n".encode())
    preserved = commit(original, "preserved source")
    rescue = "rescue/cimp-ops-03-preserved"; git(root, "branch", rescue, preserved)
    git(root, "worktree", "remove", str(original)); git(root, "branch", "-D", "implementation/cimp-ops-03-attempt-1")
    task = SimpleNamespace(task_id="CIMP-OPS-03", status="ready")
    identity = SimpleNamespace(canonical_task_cid="baguqeera-synthetic-task", canonical_task_key="synthetic-task-key", board_namespace="synthetic-board")
    daemon = SimpleNamespace(state_path=state / "task-state.json", worktree_submodule_paths=DEPS,
        worktree_lifecycle=WorktreeLifecycleStore(root), _load_tasks=lambda: [task],
        _identity_for_task=lambda _: identity, _worktree_lifecycle_attempt_for_identity=lambda **_: 1)
    daemon.state_path.write_text('{"implementation_attempts":{"CIMP-OPS-03":1}}\n')
    candidate = {"commit": preserved, "rescue_ref": rescue, "baseline_ref": baseline, "source_root": str(root),
        "original_workspace": str(original), "original_branch": "implementation/cimp-ops-03-attempt-1",
        "task_id": task.task_id, "task_cid": identity.canonical_task_cid, "task_key": identity.canonical_task_key,
        "attempt": 1, "source_manifest_sha256": "", "preservation_event_id": "sha256:" + "1" * 64}
    key = hashlib.sha256(encoded({"task_cid": candidate["task_cid"], "attempt": 1})).hexdigest()
    proof = state / "pending-task-claim-recoveries" / ("candidate-" + key + ".json")
    proof.parent.mkdir(mode=0o700); candidate["preservation_receipt_path"] = str(proof)
    files = {}
    for relative in TARGETS:
        raw = git(root, "show", preserved + ":" + relative, binary=True)
        files[relative] = {"blob": git(root, "rev-parse", preserved + ":" + relative), "mode": "100644",
                           "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    receipt = {"schema": "ordinary-preserved-pending-candidate-recovery@1", "phase": "released",
        "request": {"schema": "ordinary-preserved-pending-candidate-recovery@1",
            "base": {"repo_root": str(root), "state_path": str(daemon.state_path), "workspace": str(original),
                "baseline_ref": baseline, "repo_head": baseline, "task_id": task.task_id,
                "task_cid": identity.canonical_task_cid, "task_key": identity.canonical_task_key,
                "board_namespace": identity.board_namespace, "attempt": 1},
            "candidate": {"baseline_ref": baseline, "changed_paths": sorted(TARGETS), "files": files}},
        **{name: False for name in ("completion_authority", "attempt_refunded", "provider_callback_settled", "new_attempt_authority")}}
    w = SimpleNamespace(root=root, state=state, spec=spec, daemon=daemon, candidate=candidate,
        receipt=receipt, proof=proof, base=baseline, baseline=baseline, preserved=preserved, pins=pins, record={})
    publish(w)
    return w


def run(w):
    return runtime.materialize(w.root, w.spec, w.state, w.record, w.daemon, w.candidate, **w.kwargs)


def advance(w, *, overlap=False):
    path = w.root / (TARGETS[0] if overlap else "runtime.py")
    path.write_text("HOST_RUNTIME = 'reviewed-new-source'\n")
    w.base = commit(w.root, "reviewed host fix")
    w.receipt["request"]["base"]["repo_head"] = w.base
    publish(w)


def expected(w):
    branch = "rescue/worktree/cimp-ops-03-attempt-1-preserved-" + w.preserved[:12] + "-onto-" + w.base[:12]
    path = w.state / "worktrees" / ("preserved_cimp_ops_03_" + w.preserved[:12] + "_" + w.base[:12])
    return branch, path


@pytest.mark.parametrize("advanced", [False, True])
def test_real_git_materialization_preserves_binary_source_host_fixes_and_independent_runtime_clones(world, advanced):
    w = world
    if advanced: advance(w)
    state = w.daemon.state_path.read_bytes(); proof = w.proof.read_bytes()
    first = run(w); path = Path(first["worktree_path"])
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_supervisor import PortalImplementationSupervisor
    assert PortalImplementationSupervisor._worktree_branch_is_reconcilable(first["branch"])
    assert PortalImplementationSupervisor._worktree_branch_source_task_id(
        first["branch"], known_task_ids=[w.candidate["task_id"]]) == w.candidate["task_id"]
    assert run(w) == first
    assert git(path, "rev-list", "--parents", "-n", "1", "HEAD").split() == [first["commit"], w.base]
    for relative in TARGETS: assert (path / relative).read_bytes() == git(w.root, "show", w.preserved + ":" + relative, binary=True)
    assert (path / "runtime.py").read_bytes() == (w.root / "runtime.py").read_bytes()
    for relative, pin in w.pins.items():
        child = path / relative
        assert (child / ".git").is_dir() and git(child, "rev-parse", "HEAD") == pin
        assert Path(git(child, "rev-parse", "--absolute-git-dir")) == child / ".git"
        assert not git(child, "status", "--porcelain", "--untracked-files=all") and not (child / "docs").exists()
        assert (child / "package/module.py").read_text().startswith("NESTED_RUNTIME")
    assert w.daemon.state_path.read_bytes() == state and w.proof.read_bytes() == proof
    assert all(first[key] is False for key in ("native_admission_claimed", "completion_authority", "attempt_consumed", "provider_dispatched"))


@pytest.mark.parametrize("damage", ["receipt_id", "receipt_sha", "phase", "self_digest", "manifest", "cid", "mode", "foreign_receipt", "source_ref", "index", "overlap"])
def test_scope_receipt_or_retained_native_custody_refuses_before_worktree_creation(world, damage):
    w = world
    if damage == "receipt_id": w.kwargs["receipt_id"] = "sha256:" + "0" * 64
    elif damage == "receipt_sha": w.kwargs["receipt_sha256"] = "0" * 64
    elif damage == "phase": w.receipt["phase"] = "prepared"; publish(w)
    elif damage == "self_digest":
        v = deepcopy(w.receipt); v["operation_id"] = "changed"; w.proof.write_bytes(encoded(v)); w.kwargs["receipt_sha256"] = hashlib.sha256(w.proof.read_bytes()).hexdigest()
    elif damage == "manifest": w.receipt["request"]["candidate"]["files"][TARGETS[0]]["sha256"] = "0" * 64; publish(w)
    elif damage == "cid": w.receipt["request"]["base"]["task_cid"] = "foreign"; publish(w)
    elif damage == "mode": w.proof.chmod(0o644)
    elif damage == "foreign_receipt": w.candidate["preservation_receipt_path"] = str(w.state / "credentials.json")
    elif damage == "source_ref": git(w.root, "branch", "-f", w.candidate["rescue_ref"], w.baseline)
    elif damage == "index":
        index = w.daemon.worktree_lifecycle.task_index_path_for(canonical_task_cid=w.candidate["task_cid"], task_id=w.candidate["task_id"], attempt=1)
        index.parent.mkdir(parents=True, exist_ok=True); index.write_text("{}"); index.chmod(0o600)
    else: advance(w, overlap=True)
    _, path = expected(w)
    with pytest.raises(ValueError): run(w)
    assert not path.exists()


def test_foreign_independent_git_repository_with_identical_head_is_not_adopted(world):
    w = world; branch, path = expected(w)
    git(w.root, "clone", "--shared", str(w.root), str(path))
    git(path, "checkout", "-b", branch, w.preserved)
    before = (path / ".git/config").read_bytes()
    with pytest.raises(ValueError, match="unowned_existing_workspace"): run(w)
    assert (path / ".git/config").read_bytes() == before


@pytest.mark.parametrize("stage", ["worktree", "transplant", "commit", "clone", "sparse_init", "sparse_index"])
def test_real_partial_git_effects_resume_without_resetting_or_repeating_commit(world, monkeypatch, stage):
    w = world; advance(w)
    actual = engine.run_command; stopped = False
    def interrupted(command, **kwargs):
        nonlocal stopped
        result = actual(command, **kwargs)
        words = tuple(command)
        matches = ((stage == "worktree" and "worktree" in words and "add" in words)
            or (stage == "transplant" and "checkout" in words and w.preserved in words)
            or (stage == "commit" and "commit" in words)
            or (stage == "clone" and "clone" in words)
            or (stage in {"sparse_init", "sparse_index"} and "sparse-checkout" in words and "init" in words))
        if matches and not stopped:
            if stage == "sparse_index":
                # Some Git sparse initialization paths also publish an index;
                # construct that real Git intermediate explicitly.
                git(kwargs["cwd"], "read-tree", "-mu", "HEAD")
            stopped = True; raise OSError("synthetic crash after durable Git effect")
        return result
    monkeypatch.setattr(engine, "run_command", interrupted)
    with pytest.raises(OSError): run(w)
    _, path = expected(w); head = git(path, "rev-parse", "HEAD")
    monkeypatch.setattr(engine, "run_command", actual)
    resumed = run(w)
    if stage in {"commit", "clone", "sparse_init", "sparse_index"}: assert resumed["commit"] == head
    for relative in DEPS: assert (Path(resumed["worktree_path"]) / relative / "package/module.py").exists()
    assert run(w) == resumed


@pytest.mark.parametrize("damage", ["source", "index", "foreign_file"])
def test_partial_transplant_never_resets_foreign_working_or_staged_edits(world, monkeypatch, damage):
    w = world; advance(w)
    branch, path = expected(w); git(w.root, "worktree", "add", "-b", branch, str(path), w.base)
    target = path / ("foreign.txt" if damage == "foreign_file" else TARGETS[0])
    before = target.read_bytes() if target.exists() else None
    target.write_text("FOREIGN = 123\n")
    if damage == "index":
        git(path, "add", str(target)); target.write_bytes(before)
    with pytest.raises(ValueError, match="transplant"): run(w)
    if damage == "index": assert b"FOREIGN" in git(path, "show", ":" + TARGETS[0], binary=True)
    else: assert target.read_text() == "FOREIGN = 123\n"


def test_partial_sparse_clone_does_not_overwrite_a_present_skipped_foreign_runtime_file(world, monkeypatch):
    w = world; actual = engine.run_command; stopped = False
    def interrupted(command, **kwargs):
        nonlocal stopped
        result = actual(command, **kwargs)
        if "sparse-checkout" in command and "init" in command and not stopped:
            git(kwargs["cwd"], "read-tree", "-mu", "HEAD")
            stopped = True; raise OSError("synthetic sparse-init crash")
        return result
    monkeypatch.setattr(engine, "run_command", interrupted)
    with pytest.raises(OSError): run(w)
    _, path = expected(w); target = path / DEPS[0] / "package/module.py"
    target.parent.mkdir(exist_ok=True); target.write_text("FOREIGN_SKIPPED = 1\n")
    monkeypatch.setattr(engine, "run_command", actual)
    with pytest.raises(ValueError, match="dependency"): run(w)
    assert target.read_text() == "FOREIGN_SKIPPED = 1\n"



def test_real_resource_admission_blocks_before_materialization_with_its_stage(world, monkeypatch):
    monkeypatch.setattr(runner, "_resource_capacity", lambda *_args: {
        "ready": False, "reason": "synthetic_capacity_denial", "capacity_reserved": False})
    with pytest.raises(runner.CampaignResourceHold) as caught:
        run(world)
    assert caught.value.observation["stage"] == "preserved_candidate_materialization"
    branch, path = expected(world)
    assert not path.exists()
    assert git(world.root, "branch", "--list", branch) == ""
    assert world.daemon.state_path.read_text() == '{"implementation_attempts":{"CIMP-OPS-03":1}}\n'
