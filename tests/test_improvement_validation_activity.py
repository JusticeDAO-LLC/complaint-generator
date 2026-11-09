"""Synthetic ownership fixtures for host validation activity, never completion."""

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner


pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _write(path, value):
    path.write_text(json.dumps(value))
    path.chmod(0o600)


@dataclass(frozen=True)
class FakeBirth:
    pid: int
    start_time_ticks: int = 17
    boot_id: str = "explicit-synthetic-boot"

    def to_dict(self):
        return self.__dict__.copy()


@pytest.fixture
def ownership(tmp_path, monkeypatch):
    """All Native identities, claims and snapshots here are explicit fakes."""
    target = tmp_path / "source"
    target.mkdir()
    module_path = target / "integrations/ipfs_accelerate/improvement_runner.py"
    monkeypatch.setattr(runner, "__file__", str(module_path))
    campaign = tmp_path / "campaign"
    campaign.mkdir(mode=0o700)
    worktrees = tmp_path / "worktrees"
    worktrees.mkdir()
    workspace = worktrees / "fake-task"
    workspace.mkdir()
    logs = campaign / "implementation_logs"
    logs.mkdir()
    log = logs / ("cimp-fake-01-attempt-1-" + "a" * 32 + ".log")
    log.write_text("Synthetic initial log.\n")
    log.chmod(0o600)
    state_path = campaign / f"{runner.STATE_PREFIX}_task_state.json"
    now = time.time()
    stamp = lambda value: datetime.fromtimestamp(value, timezone.utc).isoformat()
    task = {"id": "CIMP-FAKE-01"}
    context = {"campaign_state_dir": str(campaign), "target_source_root": str(target),
               "task_id": task["id"], "task_cid": "explicit-fake-cid", "task_key": "explicit-fake-key"}
    body = {"active_task_id": task["id"], "last_implementation_task_id": task["id"],
        "active_task_cid": context["task_cid"], "active_task_key": context["task_key"], "active_attempt": 1,
        "active_phase": "validating", "implementation_in_progress": True,
        "active_worktree_path": str(workspace), "active_phase_started_at": stamp(now - 3),
        "last_implementation_started_at": stamp(now - 950), "last_implementation_finished_at": "",
        "active_log_path": str(log), "last_implementation_log_path": str(log)}
    birth = FakeBirth(os.getpid())
    expected = {"task_id": task["id"], "canonical_task_cid": context["task_cid"],
                "canonical_task_key": context["task_key"], "attempt": 1, "pid": os.getpid()}
    lease = {**expected, "kind": "implementation", "lease_id": "explicit-fake-lease",
             "repo_root": str(target), "state_dir": str(campaign)}
    claim = {**expected, "kind": "explicit-fake-claim-kind", "lease_role": "explicit-fake-dispatch",
        "lease_id": "explicit-fake-claim-lease", "state_dir": str(campaign), "state_path": str(state_path),
        "owner_process_birth": birth.to_dict(), "dispatch_authority_cid": "explicit-fake-dispatch-cid"}
    claim_path = campaign / "fake-task-claim.lock"
    _write(campaign / "implementation.lock", lease)
    _write(claim_path, claim)
    _write(campaign / "launcher.json", {"repo_root": str(target), "state_dir": str(campaign)})
    identity = SimpleNamespace(record_id="explicit-fake-owner-record", process_birth=birth,
        owner_scope={"repo_root": str(target), "state_dir": str(campaign), "state_prefix": runner.STATE_PREFIX,
            "todo_path": str(target / "docs/task_boards/complaint_intake_task_board.md"), "daemon_entrypoint": str(module_path)})

    class FakeDaemon:
        _validation_command_runner = staticmethod(lambda **_kwargs: {"explicit_fake": True})
        _implementation_task_claim_path = lambda _self, *_args, **_kwargs: claim_path
        _implementation_dispatch_authority_cid = staticmethod(lambda _claim: "explicit-fake-dispatch-cid")

    def private_identity(value):
        return (value.st_dev, value.st_ino, value.st_nlink, value.st_uid, value.st_mode,
                value.st_size, value.st_mtime_ns)

    daemon = SimpleNamespace(PortalImplementationDaemon=FakeDaemon,
        _open_no_follow_parent=lambda path: (os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW), path.name),
        _private_file_identity=private_identity)
    native = SimpleNamespace(parse_timestamp=lambda value: datetime.fromisoformat(value) if value else None,
        load_supervised_child_identity=lambda _path: identity, read_process_birth=lambda _pid: birth,
        ProcessBirthIdentity=SimpleNamespace(from_dict=lambda value: FakeBirth(**value)),
        IMPLEMENTATION_TASK_CLAIM_LOCK_KIND="explicit-fake-claim-kind",
        IMPLEMENTATION_DISPATCH_INTENT_LEASE_ROLE="explicit-fake-dispatch",
        checkout_lock_repository_matches=lambda *_args: True)
    plane = SimpleNamespace(read_portal_task_state_snapshot=lambda _path: {"body": deepcopy(body), "revision": 1})
    monkeypatch.setattr(runner, "_validation_activity_modules", lambda: (daemon, native, plane))
    monkeypatch.setattr(runner, "_validation_activity_snapshot", lambda _campaign: plane.read_portal_task_state_snapshot(state_path))
    monkeypatch.setattr(runner, "recorded_worktree_root", lambda *_args: (worktrees, None))
    return SimpleNamespace(target=target, campaign=campaign, workspace=workspace, log=log,
        task=task, context=context, body=body, birth=birth, lease=lease, claim=claim,
        claim_path=claim_path, identity=identity, daemon=daemon, native=native, plane=plane)


def _binding(context):
    return runner._validation_activity_binding(context.workspace, context.task, context.context, now_ts=time.time())


def test_synthetic_native_binding_requires_current_owner_and_exact_task(ownership):
    value = _binding(ownership)
    assert value["owner_birth"] == ownership.birth.to_dict()
    assert value["canonical_task_cid"] == ownership.context["task_cid"]
    assert value["log_identity"] == (ownership.log.stat().st_dev, ownership.log.stat().st_ino)
    assert value["phase_deadline"] <= time.time() + runner.TIMEOUT_SECONDS


@pytest.mark.parametrize("damage", ["cid", "key", "workspace", "attempt", "phase", "owner", "lease", "claim", "expiry"])
def test_synthetic_binding_refuses_mismatched_or_expired_authority(ownership, damage):
    context = ownership
    if damage == "cid": context.body["active_task_cid"] = "other-fake-cid"
    elif damage == "key": context.body["active_task_key"] = "other-fake-key"
    elif damage == "workspace": context.body["active_worktree_path"] = str(context.target)
    elif damage == "attempt": context.body["active_attempt"] = 2
    elif damage == "phase": context.body["active_phase"] = "implementing"
    elif damage == "owner": context.identity.process_birth = FakeBirth(os.getpid(), start_time_ticks=99)
    elif damage == "lease":
        _write(context.campaign / "implementation.lock", {**context.lease, "pid": os.getpid() + 1})
    elif damage == "claim":
        _write(context.claim_path, {**context.claim, "canonical_task_cid": "other-fake-cid"})
    else:
        context.body["active_phase_started_at"] = datetime.fromtimestamp(time.time() - 901, timezone.utc).isoformat()
    assert _binding(context) is None


@pytest.mark.parametrize("alias", ["symlink", "hardlink", "mode"])
def test_synthetic_activity_never_uses_aliased_or_shared_log(ownership, alias):
    context = ownership
    other = context.log.with_name("other.log")
    if alias == "symlink":
        other.write_text("Synthetic other log\n")
        context.log.unlink()
        context.log.symlink_to(other)
    elif alias == "hardlink": os.link(context.log, other)
    else: context.log.chmod(0o660)
    assert _binding(context) is None


def _pulse(context, binding, *, stopped=None):
    return runner._validation_activity_pulse(binding, context.workspace, context.task, context.context,
        deadline=time.monotonic() + 10, stopped=stopped or threading.Event(), activity_lock=threading.Lock(),
        activity_id="b" * 32, started_at=time.time() - 1, deadline_at=time.time() + 9)


def test_synthetic_pulse_records_only_activity_and_preserves_native_state(ownership):
    context = ownership
    binding = _binding(context)
    before = deepcopy(context.body)
    assert _pulse(context, binding) is True
    path = runner._validation_activity_path(binding)
    record = runner._read_validation_activity(path)
    assert runner._validation_activity_record_valid(record, binding, now_ts=time.time())
    assert record["completion_authority"] is False
    assert context.body == before
    assert "canonical_native_executor_in_flight" in context.log.read_text()
    assert path.stat().st_mode & 0o777 == 0o600
    runner._clear_validation_activity(binding, "b" * 32)
    assert not path.exists()


def test_synthetic_replay_expiry_and_closed_record_cannot_extend_window(ownership):
    binding = _binding(ownership)
    assert _pulse(ownership, binding)
    value = runner._read_validation_activity(runner._validation_activity_path(binding))
    assert not runner._validation_activity_record_valid(value, {**binding, "owner_record_id": "other-fake-owner"}, now_ts=time.time())
    assert not runner._validation_activity_record_valid(value, {**binding, "attempt": 2}, now_ts=time.time())
    assert not runner._validation_activity_record_valid(value, binding, now_ts=value["deadline_at"] + 1)
    assert not runner._validation_activity_record_valid({**value, "deadline_at": binding["phase_deadline"] + 1}, binding, now_ts=time.time())
    assert not runner._validation_activity_record_valid({**value, "state": "closed"}, binding, now_ts=time.time())


def test_synthetic_supervisor_reader_requires_same_live_claim_and_record(ownership):
    context = ownership
    binding = _binding(context)
    assert _pulse(context, binding)
    supervisor = SimpleNamespace(config=SimpleNamespace(state_dir=context.campaign, repo_root=context.target))
    state = SimpleNamespace(**context.body)
    assert runner._owned_validation_activity(supervisor, state, now_ts=time.time(), owner_pid=os.getpid())
    _write(context.claim_path, {**context.claim, "lease_id": "replacement-fake-claim"})
    assert not runner._owned_validation_activity(supervisor, state, now_ts=time.time(), owner_pid=os.getpid())


def test_synthetic_alias_sidecar_and_changed_log_inode_fail_closed(ownership):
    context = ownership
    binding = _binding(context)
    path = runner._validation_activity_path(binding, create=True)
    other = path.with_name("other.json")
    _write(other, {"accepted": True})
    path.symlink_to(other)
    with pytest.raises(ValueError, match="aliased"):
        runner._read_validation_activity(path)
    path.unlink()
    context.log.rename(context.log.with_name("old-retained-inode.log"))
    context.log.write_text("Synthetic replacement inode\n")
    context.log.chmod(0o600)
    assert not _pulse(context, binding)
    assert not path.exists()


def test_stopped_or_expired_activity_does_not_touch_log(ownership):
    binding = _binding(ownership)
    before = ownership.log.read_bytes()
    stopped = threading.Event()
    stopped.set()
    assert not _pulse(ownership, binding, stopped=stopped)
    assert ownership.log.read_bytes() == before


@pytest.mark.parametrize("raises", [False, True])
def test_synthetic_canonical_executor_activity_exists_only_during_call(ownership, monkeypatch, raises):
    context = ownership
    observed = threading.Event()
    original_pulse = runner._validation_activity_pulse
    started = threading.Event()

    def pulse(*args, **kwargs):
        assert started.is_set()
        value = original_pulse(*args, **kwargs)
        if value: observed.set()
        return value

    result = {"explicit_fake_executor_result": True}
    def executor(**kwargs):
        assert 0 < kwargs["timeout_seconds"] <= 30
        started.set()
        assert observed.wait(1)
        if raises: raise RuntimeError("explicit synthetic executor failure")
        return result

    context.daemon.PortalImplementationDaemon._validation_command_runner = staticmethod(executor)
    monkeypatch.setattr(runner, "_VALIDATION_ACTIVITY_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(runner, "_validation_activity_pulse", pulse)
    call = lambda: runner._call_validation_with_activity(executor=executor, spec=SimpleNamespace(),
        workspace_path=context.workspace, timeout_seconds=30, environment={}, task=context.task, context=context.context)
    if raises:
        with pytest.raises(RuntimeError, match="synthetic executor"): call()
    else: assert call() is result
    assert observed.is_set()
    assert not runner._validation_activity_path(_binding(context)).exists()
    before = context.log.read_bytes()
    threading.Event().wait(0.03)
    assert context.log.read_bytes() == before


def test_noncanonical_executor_cannot_mint_activity(ownership, monkeypatch):
    monkeypatch.setattr(runner, "_validation_activity_binding", lambda *_args, **_kwargs: pytest.fail("noncanonical runner requested activity"))
    result = {"explicit_fake": True}
    assert runner._call_validation_with_activity(executor=lambda **_kwargs: result, spec=None,
        workspace_path=ownership.workspace, timeout_seconds=1, environment={}, task=ownership.task, context=ownership.context) is result


@pytest.mark.parametrize("raises", [False, True])
def test_missing_context_preserves_executor_without_importing_native(monkeypatch, raises):
    monkeypatch.setattr(runner, "_validation_activity_modules", lambda: pytest.fail("unbound activity imported Native"))
    result = {"explicit_fake_without_campaign": True}
    def executor(**_kwargs):
        if raises: raise RuntimeError("explicit synthetic unbound failure")
        return result
    call = lambda: runner._call_validation_with_activity(executor=executor, spec=None, workspace_path=Path("/unbound"),
        timeout_seconds=1, environment={}, task={"id": "CIMP-FAKE"}, context=None)
    if raises:
        with pytest.raises(RuntimeError, match="synthetic unbound"): call()
    else: assert call() is result


def test_canonical_call_receives_remaining_fixed_phase_budget(ownership, monkeypatch):
    binding = _binding(ownership)
    binding["phase_deadline"] = time.time() + 0.2
    monkeypatch.setattr(runner, "_validation_activity_binding", lambda *_args, **_kwargs: binding)
    observed = []
    def executor(**kwargs):
        observed.append(kwargs["timeout_seconds"])
        return {"explicit_fake": True}
    ownership.daemon.PortalImplementationDaemon._validation_command_runner = staticmethod(executor)
    runner._call_validation_with_activity(executor=executor, spec=None, workspace_path=ownership.workspace,
        timeout_seconds=9999, environment={}, task=ownership.task, context=ownership.context)
    assert len(observed) == 1 and 0 < observed[0] <= 0.2


def test_byte_identical_legacy_duplicate_definitions_remain_preserved(tmp_path):
    installed = tmp_path / "installed"
    candidate = tmp_path / "candidate"
    relative = "tests/test_legacy_repeated.py"
    for root in (installed, candidate):
        path = root / relative
        path.parent.mkdir(parents=True)
        path.write_text("def test_repeated():\n    assert True\ndef test_repeated():\n    assert 1 == 1\n")
    records = runner._preserve_existing_behavioral_definitions(candidate, [relative], trusted_root=installed)
    assert len(records) == 1 and records[0]["preserved_definition_count"] == 2
    assert records[0]["trusted_sha256"] == records[0]["candidate_sha256"]
    # Any ambiguity after source changes remains inadmissible.
    (candidate / relative).write_text((candidate / relative).read_text() + "# changed unit source\n")
    with pytest.raises(ValueError, match="existing_behavioral_definition_changed"):
        runner._preserve_existing_behavioral_definitions(candidate, [relative], trusted_root=installed)


def _import_cache_native():
    from integrations.ipfs_datasets.loader import ensure_import_paths
    ensure_import_paths("ipfs_accelerate_py.testing")
    from ipfs_accelerate_py.testing import pytest_ast_seal
    from integrations.ipfs_accelerate.release_guard import _NativeImportEdgeCache, _native_collection_cache
    return pytest_ast_seal, _NativeImportEdgeCache, _native_collection_cache


@pytest.fixture
def import_graph(tmp_path):
    """Small real Python sources exercise canonical Native parsing and hashes."""
    # Native's real config discovers repository roots by walking ancestors.
    # Keep this explicit miniature graph separate from any enclosing checkout.
    (tmp_path / ".git").mkdir()
    sources = {
        "conftest.py": "import shared\n",
        "shared.py": "import cycle\nVALUE=True\n",
        "cycle.py": "import shared\n",
        "pkg/__init__.py": "from .helper import VALUE\n",
        "pkg/helper.py": "import shared\nVALUE=True\n",
        "pkg/tests/conftest.py": "from pkg.helper import VALUE\n",
        "pkg/tests/test_first.py": "from ..helper import VALUE\nimport optional_module\n",
        "pkg/tests/test_second.py": "from pkg.helper import VALUE\n",
    }
    for relative, source in sources.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    return tmp_path, tmp_path / "pkg/tests/test_first.py", tmp_path / "pkg/tests/test_second.py"


def test_cached_import_edges_match_canonical_native_closures_and_seals(import_graph):
    native, Cache, _ = _import_cache_native()
    root, first, second = import_graph
    expected = [native.ast_closure(root, path) for path in (first, second)]
    cache = Cache(native)
    actual = [cache.closure(root, path) for path in (first, second)]
    assert actual == expected
    assert cache.parse_count == len(set().union(*map(set, expected)))
    assert cache.hit_count > 0
    for wanted, observed in zip(expected, actual):
        a = native.seal_files(wanted, native.MemorySealOracle())
        b = native.seal_files(observed, native.MemorySealOracle())
        assert a == b and a.complete and a.digest == b.digest
    assert first in actual[0] and root / "conftest.py" in actual[0]
    assert root / "pkg/tests/conftest.py" in actual[0] and root / "cycle.py" in actual[0]


def test_import_cache_rechecks_exact_bytes_and_current_module_resolution(import_graph):
    native, Cache, _ = _import_cache_native()
    root, first, _ = import_graph
    cache = Cache(native)
    initial = cache.closure(root, first)
    (root / "optional_module.py").write_text("VALUE=True\n")
    appeared = cache.closure(root, first)
    assert appeared == native.ast_closure(root, first)
    assert root / "optional_module.py" in appeared and root / "optional_module.py" not in initial
    helper = root / "pkg/helper.py"
    metadata = helper.stat()
    raw = helper.read_bytes().replace(b"shared", b"otherx")
    assert len(raw) == metadata.st_size
    (root / "otherx.py").write_text("VALUE=True\n")
    helper.write_bytes(raw)
    os.utime(helper, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
    assert helper.stat().st_mtime_ns == metadata.st_mtime_ns
    changed = cache.closure(root, first)
    assert changed == native.ast_closure(root, first)
    assert root / "otherx.py" in changed
    assert native.seal_files(changed, native.MemorySealOracle()).digest != native.seal_files(initial, native.MemorySealOracle()).digest


def test_import_cache_preserves_native_failure_bounds_and_eviction(import_graph):
    native, Cache, _ = _import_cache_native()
    root, first, second = import_graph
    cache = Cache(native, max_entries=1, max_bytes=128, max_imports=2, max_file_bytes=64)
    for path in (first, second, first):
        assert cache.closure(root, path) == native.ast_closure(root, path)
        assert len(cache._entries) <= 1 and cache._bytes <= 128 and cache._imports <= 2
    assert cache.closure(root, first, max_files=1) is native.ast_closure(root, first, max_files=1) is None
    with pytest.raises(TypeError): cache.closure(root, first, max_files=None)
    with pytest.raises(TypeError): native.ast_closure(root, first, max_files=None)
    (root / "pkg/helper.py").write_text("this is ! invalid\n")
    assert cache.closure(root, first) is native.ast_closure(root, first) is None
    (root / "pkg/helper.py").write_bytes(b"\xff")
    assert cache.closure(root, first) is native.ast_closure(root, first) is None


def test_import_cache_never_reuses_mutable_ast_objects(import_graph):
    import ast
    native, Cache, _ = _import_cache_native()
    root, first, _ = import_graph
    original_parse = native.ast.parse
    trees = []
    def capture(source, **kwargs):
        tree = original_parse(source, **kwargs)
        trees.append(tree)
        return tree
    # A module-local test facade observes parsing; stdlib ast is never patched.
    facade = SimpleNamespace(ast=SimpleNamespace(parse=capture), ast_closure=native.ast_closure,
        _imported_modules=native._imported_modules, _module_file=native._module_file,
        _conftest_chain=native._conftest_chain)
    cache = Cache(facade)
    expected = native.ast_closure(root, first)
    assert cache.closure(root, first) == expected
    parsed = cache.parse_count
    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names: alias.name = "externally_mutated_import"
    assert cache.closure(root, first) == expected == native.ast_closure(root, first)
    assert cache.parse_count == parsed and cache.hit_count > 0
    assert all(isinstance(row[0], bytes) and isinstance(row[1], tuple)
               and all(isinstance(name, str) for name in row[1]) for row in cache._entries.values())
    assert native.ast.parse is original_parse


def test_cached_native_collection_restores_api_and_does_not_create_passing_seals(import_graph):
    native, Cache, scope = _import_cache_native()
    root, first, second = import_graph
    canonical = native.ast_closure
    seal_function = native.seal_files
    oracle = native.MemorySealOracle()
    config = SimpleNamespace(rootpath=root, _pytest_ast_seal_oracle=oracle, addinivalue_line=lambda *_args: None)
    native.pytest_configure(config)
    assert getattr(config, native._CONFIG_KEY)["repo"] == root.resolve()
    marked = []
    items = [SimpleNamespace(path=path, nodeid=path.name + "::test_case", config=config,
        get_closest_marker=lambda *_args: None, add_marker=lambda marker: marked.append(marker)) for path in (first, second)]
    cache = Cache(native)
    with scope(native, cache):
        assert native.ast_closure.__self__ is cache
        native.pytest_collection_modifyitems(config, items)
    assert native.ast_closure is canonical and native.seal_files is seal_function
    assert not marked and not oracle._seals
    seals = getattr(config, native._CONFIG_KEY)["seals"]
    assert len(seals) == 2
    for item in items:
        expected = native.seal_files(canonical(root, item.path), native.MemorySealOracle())
        assert seals[item.nodeid] == expected
    with pytest.raises(RuntimeError, match="synthetic collection failure"):
        with scope(native, Cache(native)):
            raise RuntimeError("synthetic collection failure")
    assert native.ast_closure is canonical


def _native_batch_types():
    native, _, _ = _import_cache_native()
    from integrations.ipfs_accelerate import release_guard
    return native, release_guard


def _catalog_rows(path):
    import duckdb
    connection = duckdb.connect(str(path), read_only=True)
    try:
        return {
            "files": connection.execute("SELECT path,mtime_ns,size_bytes,content_hash FROM pytest_ast_file_hash ORDER BY path").fetchall(),
            # recorded_at is the real per-call wall clock, not seal identity.
            "seals": connection.execute("SELECT nodeid,seal,file_count,completion_authority FROM pytest_ast_seal ORDER BY nodeid").fetchall(),
        }
    finally:
        connection.close()


def test_native_batched_catalog_matches_canonical_pass_fail_skip_semantics(import_graph, monkeypatch):
    native, guard = _native_batch_types()
    root, first, _ = import_graph
    canonical_path, batched_path = root / "canonical.duckdb", root / "batched.duckdb"
    canonical = native.DuckDbQuackSealOracle(canonical_path)
    delegate = native.DuckDbQuackSealOracle(batched_path)
    oracle = guard._BatchedNativeSealOracle(native, delegate, batch_size=2)
    calls = []
    for name in ("remember", "remember_file_hash", "reuse", "cached_file_hash"):
        original = getattr(delegate, name)
        def observe(*args, _name=name, _method=original, **kwargs):
            calls.append(_name)
            return _method(*args, **kwargs)
        monkeypatch.setattr(delegate, name, observe)
    paths = native.ast_closure(root, first)
    seals = [native.seal_files(paths, value) for value in (canonical, oracle)]
    assert seals[0] == seals[1]
    for value, seal in zip((canonical, oracle), seals):
        config = SimpleNamespace()
        setattr(config, native._CONFIG_KEY, {"enabled": True, "oracle": value,
            "seals": {name: seal for name in ("passed", "failed", "skipped")}, "wrote": False})
        for name in ("passed", "failed", "skipped"):
            assert value.reuse(name, seal.digest) is False
            item = SimpleNamespace(nodeid=name, config=config)
            native._remember_passing_report(item, SimpleNamespace(when="setup", passed=True))
            native._remember_passing_report(item, SimpleNamespace(when="call", passed=name == "passed",
                failed=name == "failed", skipped=name == "skipped"))
        value.close()
    a, b = _catalog_rows(canonical_path), _catalog_rows(batched_path)
    assert a == b
    assert [row[0] for row in b["seals"]] == ["passed"]
    assert all(row[3] is False for row in b["seals"])
    assert {"remember", "remember_file_hash", "reuse", "cached_file_hash"} <= set(calls)
    assert oracle.completion_authority is delegate.completion_authority is False


def test_native_batch_commits_at_most64_and_aborted_tail_cannot_be_complete(tmp_path):
    import duckdb
    native, guard = _native_batch_types()
    path = tmp_path / "partial.duckdb"
    delegate = native.DuckDbQuackSealOracle(path)
    oracle = guard._BatchedNativeSealOracle(native, delegate)
    peer = duckdb.connect(str(path), config={"threads": 1})
    seal = native.hash_of_hashes((("explicit-synthetic-source.py", "a" * 64),))
    try:
        for index in range(63):
            oracle.remember(f"synthetic::{index}", seal, file_count=1)
        assert peer.execute("SELECT count(*) FROM pytest_ast_seal").fetchone()[0] == 0
        oracle.remember("synthetic::63", seal, file_count=1)
        assert peer.execute("SELECT count(*) FROM pytest_ast_seal").fetchone()[0] == 64
        for index in range(64, 67):
            oracle.remember(f"synthetic::{index}", seal, file_count=1)
        assert oracle._pending == 3
        # Closing the actual Native connection without the adapter's flush
        # models the uncommitted tail lost on abrupt process termination.
        delegate.close()
        assert peer.execute("SELECT count(*) FROM pytest_ast_seal").fetchone()[0] == 64
        assert peer.execute("SELECT bool_or(completion_authority) FROM pytest_ast_seal").fetchone()[0] is False
        required = {f"synthetic::{index}" for index in range(67)}
        actual = {row[0] for row in peer.execute("SELECT nodeid FROM pytest_ast_seal").fetchall()}
        assert actual != required and required - actual == {f"synthetic::{index}" for index in range(64, 67)}
        with pytest.raises(native.PytestSealCatalogError): oracle.close()
    finally:
        peer.close()
        delegate.close()


def test_native_batch_commit_failure_remains_fatal_after_report_hook_swallows_it(tmp_path):
    native, guard = _native_batch_types()
    path = tmp_path / "failed.duckdb"
    delegate = native.DuckDbQuackSealOracle(path)
    real = delegate._connection
    class FailingCommit:
        def execute(self, sql, *args, **kwargs):
            if sql == "COMMIT": raise RuntimeError("explicit synthetic commit failure")
            return real.execute(sql, *args, **kwargs)
        def close(self): real.close()
    delegate._connection = FailingCommit()
    oracle = guard._BatchedNativeSealOracle(native, delegate, batch_size=1)
    seal = SimpleNamespace(digest="a" * 64, files=("synthetic-source",))
    config = SimpleNamespace()
    setattr(config, native._CONFIG_KEY, {"enabled": True, "oracle": oracle,
        "seals": {"synthetic::pass": seal}, "wrote": False})
    native._remember_passing_report(SimpleNamespace(nodeid="synthetic::pass", config=config),
        SimpleNamespace(when="call", passed=True))
    assert oracle._failed is True
    with pytest.raises(native.PytestSealCatalogError, match="batch_failed"): oracle.close()
    with pytest.raises(native.PytestSealCatalogError): oracle.reuse("synthetic::pass", seal.digest)
    assert not _catalog_rows(path)["seals"]


def test_native_batch_public_injection_keeps_fresh_collection_without_passing_rows(import_graph, monkeypatch):
    native, guard = _native_batch_types()
    root, first, _ = import_graph
    path = root / "fresh-collect.duckdb"
    monkeypatch.setenv(native.SEAL_DUCKDB_ENV, str(path))
    config = SimpleNamespace(rootpath=root, pluginmanager=SimpleNamespace(get_plugins=lambda: {native}),
                             addinivalue_line=lambda *_args: None)
    guard.pytest_configure(config)
    native.pytest_configure(config)
    oracle = getattr(config, native._CONFIG_KEY)["oracle"]
    assert type(oracle) is guard._BatchedNativeSealOracle
    guard.pytest_configure(config)
    assert getattr(config, native._CONFIG_KEY)["oracle"] is oracle
    skipped = []
    item = SimpleNamespace(path=first, nodeid="synthetic::collected", config=config,
        get_closest_marker=lambda *_args: None, add_marker=lambda marker: skipped.append(marker))
    native.pytest_collection_modifyitems(config, [item])
    assert not skipped and not oracle.delegate._seals
    # Native itself calls close before it returns from collect-only finish.
    native.pytest_sessionfinish(SimpleNamespace(config=config), 0)
    guard.pytest_unconfigure(config)
    rows = _catalog_rows(path)
    assert rows["files"] and not rows["seals"]


@pytest.mark.parametrize("batch_size", [0, 65, True, 1.5])
def test_native_batch_rejects_invalid_bounds(tmp_path, batch_size):
    native, guard = _native_batch_types()
    delegate = native.DuckDbQuackSealOracle(tmp_path / "invalid-bound.duckdb")
    try:
        with pytest.raises(ValueError, match="batch_bound"):
            guard._BatchedNativeSealOracle(native, delegate, batch_size=batch_size)
    finally:
        delegate.close()


def test_native_batch_refuses_preexisting_passes_and_custom_oracles(tmp_path):
    native, guard = _native_batch_types()
    with pytest.raises(native.PytestSealCatalogError, match="delegate_required"):
        guard._BatchedNativeSealOracle(native, native.MemorySealOracle())
    path = tmp_path / "preexisting.duckdb"
    previous = native.DuckDbQuackSealOracle(path)
    previous.remember("synthetic::prior", "a" * 64, file_count=1)
    previous.close()
    delegate = native.DuckDbQuackSealOracle(path)
    try:
        with pytest.raises(native.PytestSealCatalogError, match="fresh_native"):
            guard._BatchedNativeSealOracle(native, delegate)
    finally:
        delegate.close()
    # Native excludes authority=True rows from its in-process seal cache;
    # those existing rows still make a phase catalog non-fresh.
    delegate = native.DuckDbQuackSealOracle(path)
    delegate._connection.execute("UPDATE pytest_ast_seal SET completion_authority=TRUE")
    delegate.close()
    delegate = native.DuckDbQuackSealOracle(path)
    try:
        assert not delegate._seals
        with pytest.raises(native.PytestSealCatalogError, match="fresh_native"):
            guard._BatchedNativeSealOracle(native, delegate)
    finally:
        delegate.close()
