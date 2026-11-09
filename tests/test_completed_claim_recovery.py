"""Synthetic interrupted callback histories, genuine Native CP/claim/queue/Git.
No model, provider, actual campaign, or fabricated terminal lifecycle is used.
"""
from copy import deepcopy
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from integrations.ipfs_accelerate import completed_claim_recovery as repair
from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def _cli_config(root, state):
    from integrations.ipfs_accelerate import improvement_runner as runner
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as supervisor
    argv = runner.native_argv(root / "board.md", state, "main", worktree_root=root.parent / "worktrees",
        board_namespace="synthetic-supervisor-runtime", protected_paths=("board.md",))
    return supervisor.supervisor_config_from_args(supervisor.parse_args(argv), repo_root=root)


def daemon_for(root, state):
    from ipfs_accelerate_py.agent_supervisor.merge.merge_queue import MergeQueue
    config = _cli_config(root, state)
    return repair.completed_claim_daemon(config, merge_queue=MergeQueue(config.merge_queue_dir))


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import utc_now
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.worktrees import WorktreePool
    base = tmp_path_factory.mktemp("genuine_native_callback")
    root, state = base / "repo", base / "state"
    root.mkdir(); state.mkdir(mode=0o700)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Synthetic Native callback fixture")
    git(root, "config", "user.email", "synthetic@example.invalid")
    (root / "board.md").write_text("# Synthetic task\n\n## CIMP-SYN-40 Interrupted callback\n\n"
        "- Status: ready\n- Completion: validation\n- Priority: P1\n- Track: ops\n"
        "- Outputs: result.txt, tests/test_synthetic.py\n- Validation: python -m pytest -q tests/test_synthetic.py\n"
        "- Acceptance: A synthetic local result is recorded.\n")
    git(root, "add", "board.md"); git(root, "commit", "-qm", "Synthetic pending task")
    baseline = git(root, "rev-parse", "HEAD")
    daemon = daemon_for(root, state)
    task = daemon._load_tasks()[0]
    daemon._register_task_identities([task])  # Genuine synthetic-root registration, never live.
    identity = daemon._identity_for_task(task)
    branch = "implementation/syn-40-interrupted-attempt-1"
    pool = WorktreePool(repo_root=root, worktree_root=base / "worktrees")
    lease = pool.acquire(cache_key="synthetic-callback", base_ref="main", branch_name=branch)
    started_at = utc_now()
    # A real short-lived Native claim producer records its actual birth and exits.
    driver = base / "claim_producer.py"
    driver.write_text("import sys,json\nfrom pathlib import Path\nsys.path[:0]=" + repr(list(sys.path)) + "\n"
        "from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as n\n"
        "d=n.PortalImplementationDaemon(todo_path=Path(sys.argv[1]),state_path=Path(sys.argv[2]),"
        "strategy_path=Path(sys.argv[3]),events_path=Path(sys.argv[4]),repo_root=Path(sys.argv[5]),"
        "task_header_prefix='## CIMP-SYN-',implement=False,use_ephemeral_worktree=False,"
        "worktree_submodule_paths=[],merge_queue_dir=Path(sys.argv[6]),llm_merge_resolver_command='')\n"
        "t=d._load_tasks()[0]\nm=d._build_implementation_task_claim_metadata(t,1,sys.argv[7])\n"
        "p=d._implementation_task_claim_path(t.task_id,canonical_task_cid=d._identity_for_task(t).canonical_task_cid)\n"
        "ok,reason,prior=d._try_acquire_implementation_task_claim(p,m)\nassert ok,reason\n"
        "m=d._build_implementation_lock_metadata(t,1,sys.argv[7])\n"
        "fd,reason,prior=d._try_acquire_lock(d._implementation_lock_path(),lock_kind='implementation',"
        "owner_active=d._implementation_lock_owner_is_active)\nassert fd is not None,reason\n"
        "d._write_lock_metadata(fd,m)\n")
    subprocess.run([sys.executable, "-I", "-B", str(driver), str(daemon.todo_path),
        str(daemon.state_path), str(daemon.strategy_path), str(daemon.events_path),
        str(root), str(state / "merge-queue"), started_at], check=True, timeout=90)
    claim_path = daemon._implementation_task_claim_path(task.task_id,
        canonical_task_cid=identity.canonical_task_cid)
    claim = json.loads(claim_path.read_text())
    current = native.PortalTaskState.load(daemon.state_path)
    current.implementation_attempts[task.task_id] = 1
    current.implementation_attempts_by_cid[identity.canonical_task_cid] = 1
    current.task_statuses[task.task_id] = "ready"
    current.task_identities[task.task_id] = identity.to_dict()
    current.last_implementation_task_id = task.task_id
    current.last_implementation_task_cid = identity.canonical_task_cid
    current.last_implementation_started_at = started_at
    current.last_implementation_worktree_path = str(lease.path)
    current.last_implementation_branch = branch
    current.save(daemon.state_path)
    def emit(kind, values):
        daemon._record_event(kind, {"synthetic_history": True, **values})
    common = {"task_id": task.task_id, "attempt": 1}
    emit("implementation_started", {**common, "branch": branch, "worktree_path": str(lease.path),
                                  "baseline_ref": baseline})
    (lease.path / "result.txt").write_text("synthetic local result\n")
    (lease.path / "tests").mkdir()
    (lease.path / "tests/test_synthetic.py").write_text("from pathlib import Path\n"
        "def test_synthetic_artifact():\n assert Path('result.txt').read_text() == 'synthetic local result\\n'\n")
    # Actual Native proposal admission, Host scheduler and queue compaction;
    # the fixture's history is synthetic, but these producer shapes are real.
    proposal = daemon._validate_implementation_patch(lease.path, task,
        baseline_ref=baseline, allow_scope_adjudication=False)
    assert proposal.accepted, proposal.to_dict()
    from integrations.ipfs_accelerate import improvement_runner as runner
    from ipfs_accelerate_py.agent_supervisor.validation.validation_runtime import (
        build_validation_environment, validation_environment_for_runner)
    from ipfs_accelerate_py.agent_supervisor.validation.validation_scheduler import (
        ValidationScheduler, build_declared_validation_plan_graph)
    executor = native.PortalImplementationDaemon._validation_command_runner
    environment = build_validation_environment(dict(os.environ))
    roots = [lease.path, Path(runner.__file__).resolve().parents[2], Path(native.__file__).resolve().parents[3],
             Path(pytest.__file__).resolve().parents[1]]
    environment["PYTHONPATH"] = os.pathsep.join(map(str, roots))
    environment = validation_environment_for_runner(environment, executor)
    command = "python -m pytest -q tests/test_synthetic.py"
    contract = {"id": task.task_id, "targets": ["result.txt", "tests/test_synthetic.py"],
                "validation_commands": [command], "depends_on": []}
    scheduler = runner.EvidenceValidationScheduler(ValidationScheduler(max_workers=1),
        state_dir=state, spec={"tasks": [contract]}, defer_readiness=True)
    scheduler.bind_task(task, lease.path)
    commands, impact = build_declared_validation_plan_graph([command],
        repository_tree_id=baseline, changed_paths=proposal.proposal.changed_paths)
    validation = scheduler.run_validated(proposal, commands, workspace_path=lease.path,
        target_commit=baseline, impact_graph=impact, scope="pre_merge",
        runner=executor, environment=environment)
    validation["proposal_gate"] = daemon._compact_proposal_validation(proposal)
    (base / "synthetic-validation.json").write_text(json.dumps(validation, default=lambda x: x.to_dict()))
    assert validation["passed"], validation
    admission = validation["behavioral_evidence"][0]
    git(lease.path, "add", "result.txt", "tests/test_synthetic.py")
    git(lease.path, "commit", "-qm", "Synthetic implementation")
    candidate = git(lease.path, "rev-parse", "HEAD")
    emit("implementation_candidate_handoff_verified", {**common, "allowed": True,
        "implementation_commit": candidate})
    released = lease.release()
    assert released["released"] and released["reason"] == "clean_prepared_workspace"
    emit("worktree_pool_lease_released", released)
    request, queued = daemon._enqueue_merge_candidate(branch_name=branch,
        implementation_commit=candidate, baseline_ref=baseline, worktree_path=lease.path,
        task=task, attempt=1, validation_result=validation, worktree_pool_handoff=True)
    assert queued["queued"]
    metadata = request.metadata
    assert "behavioral_evidence" not in metadata["validation_proof"]
    git(root, "merge", "--no-ff", "--no-edit", branch)
    merged = git(root, "rev-parse", "HEAD")
    emit("merge_finished", {"branch": branch, "target_branch": "main", "merged": True,
        "attempted": True, "returncode": 0, "merge_commit": merged, "integration_base_commit": baseline})
    git(root, "branch", "-D", branch)
    emit("cleanup_finished", {"branch": branch, "cleaned": True, "deleted_branch": True})
    # Use the genuine Native callback, not a hand-written completed status/event.
    callback = daemon._mark_task_completed_in_todo(task.task_id,
        expected_task_cids={task.task_id: identity.canonical_task_cid})
    assert callback["updated"]
    processing = daemon.merge_queue.claim_pending_request(request, consumer_id="synthetic-native-completion")
    assert processing is not None
    daemon.merge_queue.complete(processing)
    # Deliberately do not save the old Portal snapshot after its actual callback.
    assert native.PortalTaskState.load(daemon.state_path).task_statuses[task.task_id] == "ready"
    assert not daemon.worktree_lifecycle.workspace_path_for(lease.path).exists()
    return dict(daemon=daemon, root=root, state=state, claim_path=claim_path,
        claim=claim, task=task, identity=identity, branch=branch, workspace=lease.path,
        head=git(root, "rev-parse", "HEAD"), callback=callback, request=request, admission=admission,
        candidate=candidate, merged=merged, validation=metadata["validation_proof"])


@pytest.fixture
def unchanged_world(world):
    d = world["daemon"]
    files = [world["claim_path"], d._implementation_lock_path(), d.todo_path, d.events_path]
    original = {p: p.read_bytes() for p in files}
    state = native.PortalTaskState.load(d.state_path)
    yield world
    for p, raw in original.items():
        p.write_bytes(raw)
    (wstate := world["state"] / native.IMPLEMENTATION_PROTECTED_ACTIVE_SNAPSHOT_FILENAME).unlink(missing_ok=True)
    state.save(d.state_path)
    git(world["root"], "update-ref", "refs/heads/main", world["head"])


def test_real_native_callback_proof_with_stale_cp_and_no_lifecycle(unchanged_world):
    w = unchanged_world
    value = repair.review_completed_claim(w["daemon"])
    assert value["source_status"] == "completed"
    assert value["portal_projection_status"] == "ready"
    assert value["claim"]["owner_process_birth"]["pid"] != os.getpid()


def test_exact_native_primitive_retires_only_claim_preserving_full_cp(unchanged_world):
    w = unchanged_world
    before = asdict(native.PortalTaskState.load(w["daemon"].state_path))
    closures = []
    result = repair.reconcile_completed_claim(w["daemon"], reprove_closure=lambda: closures.append(True))
    assert result["reconciled"] and len(closures) == 3
    assert not w["claim_path"].exists()
    assert not w["daemon"]._implementation_lock_path().exists()
    assert asdict(native.PortalTaskState.load(w["daemon"].state_path)) == before
    assert not result["completion_authority"] and not result["attempt_refunded"]
    assert json.loads(Path(result["receipt_path"]).read_text())["phase"] == "released"


@pytest.mark.parametrize("damage", ["pending", "changed_definition", "wrong_cid", "wrong_key",
    "attempt", "live_owner", "fence", "corrupt_journal", "nonancestor", "new_lane",
    "foreign_impl_lease", "wrong_impl_start", "merge_impl_lease", "bool_impl_attempt"])
def test_unknown_or_nonterminal_authority_cannot_release(unchanged_world, damage):
    w = unchanged_world; d = w["daemon"]
    if damage in {"pending", "changed_definition"}:
        text = d.todo_path.read_text()
        d.todo_path.write_text(text.replace("Status: completed", "Status: ready") if damage == "pending"
                              else text.replace("result.txt", "other.txt"))
    elif damage in {"wrong_cid", "wrong_key", "live_owner", "fence"}:
        value = json.loads(w["claim_path"].read_text())
        if damage == "wrong_cid": value["canonical_task_cid"] += "x"
        elif damage == "wrong_key": value["canonical_task_key"] += "x"
        elif damage == "live_owner":
            from ipfs_accelerate_py.agent_supervisor.merge.worktree_lifecycle import current_process_birth
            value["owner_process_birth"] = current_process_birth().to_dict()
            value["pid"] = os.getpid()
        else:
            (w["state"] / native.IMPLEMENTATION_PROTECTED_ACTIVE_SNAPSHOT_FILENAME).write_text("{}")
        w["claim_path"].write_text(json.dumps(value))
    elif damage in {"attempt", "new_lane"}:
        value = native.PortalTaskState.load(d.state_path)
        if damage == "attempt": value.implementation_attempts[w["task"].task_id] = 2
        else: value.implementation_in_progress = True
        value.save(d.state_path)
    elif damage in {"foreign_impl_lease", "wrong_impl_start", "merge_impl_lease", "bool_impl_attempt"}:
        value = json.loads(d._implementation_lock_path().read_text())
        key = {"foreign_impl_lease": "task_id", "wrong_impl_start": "started_at", "merge_impl_lease": "kind",
               "bool_impl_attempt": "attempt"}[damage]
        value[key] = True if damage == "bool_impl_attempt" else "different"
        d._implementation_lock_path().write_text(json.dumps(value))
    elif damage == "corrupt_journal":
        d.events_path.write_bytes(d.events_path.read_bytes().replace(b'"synthetic_history":true', b'"synthetic_history":false', 1))
    else:
        git(w["root"], "update-ref", "refs/heads/main",
            git(w["root"], "rev-list", "--max-parents=0", "HEAD"))
    raw = w["claim_path"].read_bytes()
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        repair.reconcile_completed_claim(d, reprove_closure=lambda: None)
    assert w["claim_path"].read_bytes() == raw


def test_replacement_at_closure_cannot_be_released(unchanged_world):
    w = unchanged_world
    count = 0
    def closure():
        nonlocal count
        count += 1
        if count == 2:
            value = json.loads(w["claim_path"].read_text())
            value["lease_id"] += "replacement"
            w["claim_path"].write_text(json.dumps(value))
    with pytest.raises(ValueError, match="proof_changed"):
        repair.reconcile_completed_claim(w["daemon"], reprove_closure=closure)
    assert w["claim_path"].exists()


def test_real_retained_checkout_guard_is_distinct_and_preserved(unchanged_world):
    from integrations.ipfs_accelerate import improvement_runner as runner
    from ipfs_accelerate_py.agent_supervisor.merge.checkout_lock import board_scoped_checkout_mutation_lock_path
    w = unchanged_world
    namespace = "synthetic-completed-claim"
    guard = board_scoped_checkout_mutation_lock_path(w["root"], namespace)
    assert guard != w["daemon"]._implementation_lock_path()
    with runner._recovery_checkout_lease(w["root"], board_namespace=namespace):
        original = guard.read_bytes()
        result = repair.reconcile_completed_claim(w["daemon"], reprove_closure=lambda: None)
        assert result["reconciled"]
        assert guard.read_bytes() == original
        assert not w["claim_path"].exists() and not w["daemon"]._implementation_lock_path().exists()


def _readonly_view(w):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_supervisor import PortalSupervisorConfig
    d = w["daemon"]
    config = PortalSupervisorConfig(todo_path=d.todo_path, state_path=d.state_path,
        strategy_path=d.strategy_path, events_path=w["state"] / "supervisor_events.jsonl",
        state_dir=w["state"], repo_root=w["root"], task_prefix="## CIMP-SYN-",
        state_prefix="complaint_intake", merge_target_branch="main", merge_queue_dir=d.merge_queue_dir,
        implementation_protected_paths=("board.md",))
    return repair.read_only_completion_view(config)


def test_automatic_recovery_factory_keeps_real_native_filename_identity(unchanged_world):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_supervisor import PortalSupervisorConfig
    w = unchanged_world; d = w["daemon"]
    config = PortalSupervisorConfig(todo_path=d.todo_path, state_path=d.state_path,
        strategy_path=d.strategy_path, events_path=w["state"] / "supervisor_events.jsonl",
        state_dir=w["state"], repo_root=w["root"], task_prefix="## CIMP-SYN-",
        state_prefix="complaint_intake", merge_target_branch="main", merge_queue_dir=d.merge_queue_dir,
        max_task_attempts=3, board_namespace="synthetic-supervisor-runtime",
        implementation_protected_paths=("board.md",))
    before = asdict(native.PortalTaskState.load(d.state_path))
    actual = repair.completed_claim_daemon(config, merge_queue=d.merge_queue)
    assert type(actual) is native.PortalImplementationDaemon and actual.implement is False
    assert actual._identity_for_task(actual._load_tasks()[0]).board_namespace == w["claim"]["board_namespace"]
    refused = actual.reconcile_quiesced_implementation_task_claim()
    assert refused["blocked"] and refused["reason"] == "task_claim_worktree_lifecycle_missing"
    result = repair.reconcile_completed_claim(actual, reprove_closure=lambda: None)
    assert result["reconciled"]
    assert not actual.reconcile_quiesced_active_attempt()["blocked"]
    assert not actual.reconcile_quiesced_implementation_task_claim()["blocked"]
    assert asdict(native.PortalTaskState.load(d.state_path)) == before


def _observe(w):
    from integrations.ipfs_accelerate import campaign_completion as completion
    from integrations.ipfs_accelerate import release_evidence as evidence
    from ipfs_accelerate_py.agent_supervisor.runtime import event_log
    view = _readonly_view(w)
    rows, pin = evidence._journal(w["state"], event_log)
    task = view._load_tasks()[0]
    latest = completion._latest_terminals(w["state"], pin, {task.task_id: task})
    return completion._task_completion_observation(w["root"], w["state"], task, native,
        rows, pin, latest, interrupted_view=view)


def test_final_verifier_observes_real_source_seal_after_claim_retirement(unchanged_world):
    w = unchanged_world
    repair.reconcile_completed_claim(w["daemon"], reprove_closure=lambda: None)
    before = {p: p.read_bytes() for p in w["state"].rglob("*") if p.is_file()}
    result = _observe(w)
    after = {p: p.read_bytes() for p in w["state"].rglob("*") if p.is_file()}
    assert before == after
    assert result["event_kind"] == "todo_status_updated"
    assert result["native_finish_event_synthesized"] is False
    assert result["observation_provenance"] == "interrupted_finish_completed_queue_and_durable_callback"
    assert result["member_receipt_digest"] and result["historical_evidence_digest"]


@pytest.mark.parametrize("damage", ["new_start", "failed_finish", "conflicting_identity", "seal_tampered"])
def test_interrupted_verifier_cannot_hide_new_execution_failure_or_bad_source_seal(unchanged_world, damage):
    w = unchanged_world; d = w["daemon"]
    saved = None
    if damage == "seal_tampered":
        path = Path(w["admission"]["measurement_record"]["path"])
        saved = (path, path.read_bytes())
        path.write_text("{}")
    else:
        payload = {"task_id": w["task"].task_id, "attempt": 1, "synthetic_history": True}
        if damage == "new_start":
            kind = "implementation_started"
            payload.update(branch="different", worktree_path=str(w["workspace"]))
        elif damage == "failed_finish":
            kind = "implementation_finished"; payload["returncode"] = 1
        else:
            kind = "synthetic_conflicting_identity"
            payload["canonical_task_cid"] = "different"
        d._record_event(kind, payload)
    try:
        with pytest.raises(ValueError): _observe(w)
    finally:
        if saved is not None: saved[0].write_bytes(saved[1])


def test_readonly_native_view_cannot_be_used_for_mutation(unchanged_world):
    w = unchanged_world
    with pytest.raises(ValueError, match="read_only_view"):
        repair.reconcile_completed_claim(_readonly_view(w), reprove_closure=lambda: pytest.fail("no closure effect"))
    assert w["claim_path"].exists()


def test_real_cli_explicit_legacy_config_reads_genuine_callback_without_initializing_state(unchanged_world):
    w = unchanged_world
    config = _cli_config(w["root"], w["state"])
    assert config.database_program is not None
    assert config.database_program.explicit_legacy is True
    before = {p: p.read_bytes() for p in w["state"].rglob("*") if p.is_file()}
    view = repair.read_only_completion_view(config)
    proof = repair.completed_callback_proof(view, task_id=w["task"].task_id,
        canonical_task_cid=w["identity"].canonical_task_cid, attempt=1,
        workspace=str(w["workspace"]), branch=w["branch"])
    assert proof["source_status"] == "completed"
    assert before == {p: p.read_bytes() for p in w["state"].rglob("*") if p.is_file()}


@pytest.mark.parametrize("mode", ["quack", "embedded", "embedded_exclusive"])
def test_database_authority_configs_remain_refused(unchanged_world, mode):
    from dataclasses import replace
    from ipfs_accelerate_py.agent_supervisor.runtime.multi_supervisor_runner import DatabaseProgramConfig
    w = unchanged_world
    quack = ({"endpoint_secret_handle": "handle:synthetic-test-only",
        "quack_endpoint": "quack://127.0.0.1:19091", "store_id": "synthetic-store",
        "store_generation": "synthetic-generation", "schema_revision": "synthetic-schema"}
        if mode == "quack" else {})
    config = replace(_cli_config(w["root"], w["state"]),
        database_program=DatabaseProgramConfig(authority_mode=mode, task_source_kind="duckdb", **quack))
    with pytest.raises(ValueError, match="legacy_config_required"):
        repair.read_only_completion_view(config)
    with pytest.raises(ValueError, match="config_required"):
        repair.completed_claim_daemon(config, merge_queue=w["daemon"].merge_queue)


def test_real_successful_finish_allows_cleanup_without_missing_finish_fallback(unchanged_world):
    w = unchanged_world
    w["daemon"]._record_event("implementation_finished", {
        "task_id": w["task"].task_id, "attempt": 1, "returncode": 0, "synthetic_history": True,
        "implementation_commit": w["candidate"], "validation_result": w["validation"],
        "merge_result": {"merged": True, "returncode": 0, "merge_commit": w["merged"],
                         "todo_update_result": w["callback"]}})
    value = repair.review_completed_claim(w["daemon"])
    assert len(value["finish_event_ids"]) == 1
    result = repair.reconcile_completed_claim(w["daemon"], reprove_closure=lambda: None)
    assert result["reconciled"]
    assert not w["claim_path"].exists()



@pytest.mark.parametrize("damage", ["missing", "task_cid", "task_key", "proposal", "baseline", "command", "targets", "contract_digest", "candidate_bytes", "candidate_replace"])
def test_compact_queue_requires_exact_owned_host_contract_and_candidate(unchanged_world, damage):
    from integrations.ipfs_accelerate import release_evidence as evidence
    from integrations.ipfs_accelerate import improvement_plan as compiler
    import hashlib
    w = unchanged_world
    path = w["state"] / "evidence" / w["task"].task_id / "completion.json"
    raw = path.read_bytes()
    measurement = Path(w["admission"]["measurement_record"]["path"])
    measured_raw = measurement.read_bytes()
    receipt = json.loads(raw)
    replaced = False
    try:
        if damage == "missing":
            path.unlink()
        elif damage in {"candidate_bytes", "candidate_replace"}:
            # Even an internally consistent replacement seal cannot describe
            # bytes different from the immutable queued Git candidate.
            item = "result.txt"
            replacement = hashlib.sha256(b"different synthetic candidate").hexdigest()
            if damage == "candidate_replace":
                # A real Git replacement reference must not change which
                # immutable candidate bytes the historical verifier hashes.
                root = w["root"]
                blob = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=root,
                    input=b"different synthetic candidate", capture_output=True, check=True).stdout.decode().strip()
                original_tree = git(root, "ls-tree", w["candidate"])
                lines = [line.split("\t")[0].rsplit(" ", 1)[0] + " " + blob + "\tresult.txt"
                         if line.endswith("\tresult.txt") else line for line in original_tree.splitlines()]
                tree = subprocess.run(["git", "mktree"], cwd=root, input="\n".join(lines)+"\n",
                    text=True, capture_output=True, check=True).stdout.strip()
                replacement_commit = subprocess.run(["git", "commit-tree", tree, "-p", git(root, "rev-parse", w["candidate"]+"^")],
                    cwd=root, input="Synthetic replacement-ref adversary\n", text=True, capture_output=True, check=True).stdout.strip()
                git(root, "replace", w["candidate"], replacement_commit)
                replaced = True
            receipt["source_binding"]["files"][item]["sha256"] = replacement
            measured = json.loads(measured_raw)
            for frame in (measured["source_before"], measured["source_after"]):
                frame["files"][item]["sha256"] = replacement
            measured["observation_binding"]["source_binding"] = deepcopy(receipt["source_binding"])
            measurement.write_text(json.dumps(measured))
            receipt["host_measurement"] = measured
            receipt["measurement_record"]["sha256"] = hashlib.sha256(measurement.read_bytes()).hexdigest()
            path.write_text(json.dumps(receipt))
        else:
            context = receipt["host_task_contract"]["context"]
            if damage in {"task_cid", "task_key"}: context[damage] += "wrong"
            elif damage == "proposal": context["proposal_id"] = "f" * 64
            elif damage == "baseline": context["repository_tree_id"] = "f" * 40
            elif damage == "command": receipt["host_task_contract"]["declared_command"] = "python -m pytest -q tests/other.py"
            elif damage == "targets": receipt["host_task_contract"]["task"]["targets"] = ["other.txt"]
            elif damage == "contract_digest": receipt["task_contract_digest"] = "f" * 64
            if damage != "contract_digest":
                receipt["task_contract_digest"] = compiler._digest(receipt["host_task_contract"])
            path.write_text(json.dumps(receipt))
        with pytest.raises((ValueError, OSError)):
            _observe(w)
    finally:
        if replaced:
            git(w["root"], "replace", "-d", w["candidate"])
        path.write_bytes(raw)
        measurement.write_bytes(measured_raw)


@pytest.mark.parametrize("damage", ["proposal", "tree", "result_command", "timeout", "cache", "ordinal", "population"])
def test_native_compact_summary_cannot_substitute_proposal_or_result(unchanged_world, damage):
    from integrations.ipfs_accelerate import release_evidence as evidence
    w = unchanged_world; d = w["daemon"]
    binding = repair.completed_callback_proof(d, task_id=w["task"].task_id,
        canonical_task_cid=w["identity"].canonical_task_cid, attempt=1,
        workspace=str(w["workspace"]), branch=w["branch"])
    value = deepcopy(binding["validation_proof"])
    if damage == "proposal": value["proposal_gate"]["proposal_id"] = "f" * 64
    elif damage == "tree": value["target_tree"] = "f" * 40
    elif damage == "result_command": value["results"][0]["command"] = "python -m pytest -q tests/other.py"
    elif damage == "timeout": value["results"][0]["timed_out"] = True
    elif damage == "cache": value["results"][0]["cache_hit"] = True
    elif damage == "ordinal": value["results"][0]["ordinal"] = True
    else: value["results"] = []
    with pytest.raises(ValueError):
        evidence._compact_queue_host_measurements(w["state"], value, w["task"], binding)


def test_full_modern_queue_seal_path_remains_compatible(unchanged_world):
    from integrations.ipfs_accelerate import release_evidence as evidence
    from ipfs_accelerate_py.agent_supervisor.runtime import event_log
    w = unchanged_world
    _, journal = evidence._journal(w["state"], event_log)
    value = evidence.historical_queue_validation(w["state"], {"behavioral_evidence": [w["admission"]]},
        w["task"], journal, callback_sequence=journal["last_sequence"], callback_event_id="synthetic-only")
    assert value["status"] == "HISTORICAL" and value["native_finish_event_synthesized"] is False
