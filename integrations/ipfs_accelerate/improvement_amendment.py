"""Explicit, stopped-campaign migration of the pending narrative task's scope.

This is deliberately one amendment recipe, not a task-state repair API. Native
accounting, claims, callbacks and completion evidence are read but never edited.
The immutable recovery receipt keeps its original plan identity.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any, Mapping
import uuid

from . import improvement_plan as compiler
from . import improvement_recovery as recovery
from . import improvement_runner as runner


SCHEMA = "complaint-improvement-pending-amendment@1"
POINTER_SCHEMA = "complaint-improvement-active-epoch@2"
TASK = "CIMP-TUI-02"
BASELINE_TASK = "CIMP-TUI-01"
BASELINE_CID = "baguqeeraxq775q25gtjritvqbbfcnryzpodeib3cn6dayanky4hrvo6the7q"
BASELINE_TEST = "tests/test_tui_intake_baseline.py"
BASELINE_RECEIPT = "docs/task_boards/complaint_tui_baseline_receipt.json"
GUIDANCE = (
    "Migrate the live TUI baseline tests alongside narrative capture: retain the "
    "historical baseline receipt byte-for-byte and validate its recorded history, "
    "but replace live assertions requiring known defects to persist. Exercise the "
    "new narrative-first contract through the real terminal while retaining the "
    "bounded PTY, pause/resume and diagnostic-redaction checks. Do not skip, xfail, "
    "mock the application or conditionally accept the old narrative-as-name bug. "
    "Later graph, outcome, interruption and privacy tasks own their desired "
    "behavioral regressions; historical gap observations are not current product "
    "requirements. This note grants no additional output or completion authority."
)
_NO_AUTHORITY = ("attempt_refunded", "completion_authority", "callback_authority",
                 "hold_released", "evidence_reuse_authority", "provider_started")


def _encoded(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def _source_bytes(path: Path) -> bytes:
    # Reviewed tracked sources can retain the repository's historical 0664
    # umask; the stable owned fd and exact CAS hash are still required.
    return recovery._owned_bytes(path, legacy_group_write=True)


def _head(root: Path) -> str:
    result = subprocess.run(["git", "--no-replace-objects", "rev-parse", "HEAD"],
        cwd=root, capture_output=True, text=True, check=True, timeout=10)
    head = result.stdout.strip()
    if re.fullmatch(r"[0-9a-f]{40,64}", head) is None:
        raise ValueError("source revision is unavailable")
    return head


def amended_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Return only the reviewed TUI-02 baseline migration, without writing it."""
    result = deepcopy(dict(spec))
    matches = [task for task in result["tasks"] if task["id"] == TASK]
    if len(matches) != 1 or BASELINE_TEST in matches[0]["targets"]:
        raise ValueError("pending baseline amendment is absent or already applied")
    task = matches[0]
    if (len(task["validation_commands"]) != 1
            or not task["validation_commands"][0].endswith("tests/test_tui_narrative_capture.py")
            or task["depends_on"] != [BASELINE_TASK]):
        raise ValueError("narrative task contract differs from the reviewed amendment recipe")
    task["targets"].append(BASELINE_TEST)
    task["validation_commands"][0] += " " + BASELINE_TEST
    task["implementation_prompt"] += "\n\n" + GUIDANCE
    return compiler.validate_spec(result)


def _blocks(raw: bytes) -> dict[str, bytes]:
    text = raw.decode("utf-8")
    matches = list(re.finditer(r"^## (CIMP-[A-Za-z0-9_.:-]+)(?:\s|$)", text, re.MULTILINE))
    result = {m.group(1): text[m.start(): matches[i + 1].start() if i + 1 < len(matches) else len(text)].encode()
              for i, m in enumerate(matches)}
    if len(result) != len(matches):
        raise ValueError("duplicate board task headings")
    return result


def _board_revision(raw: bytes, old_spec: Mapping[str, Any], new_spec: Mapping[str, Any],
                    old_id: str, new_id: str) -> bytes:
    text = raw.decode("utf-8")
    marker = f"<!-- plan_id: {old_id} -->"
    if text.count(marker) != 1:
        raise ValueError("board plan marker differs")
    blocks = _blocks(raw)
    old = next(task for task in old_spec["tasks"] if task["id"] == TASK)
    new = next(task for task in new_spec["tasks"] if task["id"] == TASK)
    block = blocks[TASK].decode()
    pairs = [
        ("Outputs", ", ".join(old["targets"]), ", ".join(new["targets"])),
        ("Validation", "; ".join(old["validation_commands"]), "; ".join(new["validation_commands"])),
    ]
    for field, before, after in pairs:
        line = f"- {field}: {before}"
        if block.splitlines().count(line) != 1:
            raise ValueError(f"pending board {field} differs from the reviewed specification")
        block = block.replace(line + "\n", f"- {field}: {after}\n", 1)
    # Existing operator runtime/retry guidance is retained, including unknown
    # fields. Add the bounded advisory to the single existing runtime field.
    guidance = re.findall(r"^- Runtime guidance: (.*)$", block, re.MULTILINE)
    if len(guidance) != 1:
        raise ValueError("pending task needs one existing runtime guidance field")
    if len((guidance[0] + " " + GUIDANCE).encode()) > 8 * 1024:
        raise ValueError("amended runtime guidance exceeds the native advisory budget")
    block = block.replace("- Runtime guidance: " + guidance[0] + "\n",
                          "- Runtime guidance: " + guidance[0] + " " + GUIDANCE + "\n", 1)
    result = text.replace(blocks[TASK].decode(), block, 1).replace(marker, f"<!-- plan_id: {new_id} -->", 1).encode()
    after_blocks = _blocks(result)
    if any(after_blocks[key] != value for key, value in blocks.items() if key != TASK):
        raise ValueError("amendment changed an unrelated task block")
    return result


def _compile(spec: Mapping[str, Any]) -> tuple[Any, bytes, dict[str, Any]]:
    plan = compiler.build_improvement_work_plan(spec)
    from ipfs_accelerate_py.agent_supervisor.planning.formal_planning_contracts import FormalWorkPlan
    from ipfs_accelerate_py.agent_supervisor.planning.formal_plan_validator import FormalPlanValidator
    document = {**plan.to_dict(), "plan_id": plan.plan_id}
    restored = FormalWorkPlan.from_dict(document)
    if restored.plan_id != plan.plan_id:
        raise ValueError("native plan round trip changed identity")
    validation = FormalPlanValidator().validate(restored).to_record()
    return plan, _encoded(document), validation


def _tasks(native: Any, root: Path, raw: bytes) -> dict[str, Any]:
    # Use the actual native snapshot parser with the exact production path:
    # namespaces/keys are path-bound even where semantic CIDs are reusable.
    tasks = native.parse_task_text(raw.decode("utf-8"), path=root / compiler.BOARD_RELATIVE,
                                   task_header_prefix=runner.TASK_PREFIX)
    result = {task.task_id: task for task in tasks}
    if len(result) != len(tasks):
        raise ValueError("native parser found duplicate task identities")
    return result


def review_tui_baseline_amendment(repo_root: Path, spec_path: Path, base_state_dir: Path,
                                  *, baseline_receipt_sha256: str) -> dict[str, Any]:
    """Produce exact CAS inputs for operator review, without changing artifacts."""
    root, spec_path, base = repo_root.resolve(), spec_path.resolve(), base_state_dir.resolve()
    if spec_path != root / compiler.SPEC_RELATIVE:
        raise ValueError("amendment requires the canonical specification path")
    _, native = runner._native_modules(root)
    paths = {"spec": spec_path, "plan": root / compiler.PLAN_RELATIVE,
             "board": root / compiler.BOARD_RELATIVE, "pointer": base / "active_epoch.json",
             "baseline_receipt": root / BASELINE_RECEIPT}
    raw = {key: _source_bytes(path) for key, path in paths.items()}
    spec = compiler.validate_spec(json.loads(raw["spec"]))
    old, old_plan, _ = _compile(spec)
    restored = json.loads(raw["plan"])
    if restored != json.loads(old_plan):
        raise ValueError("old formal plan differs from its specification")
    state = recovery.resolve_active_epoch(root, spec_path, base)
    pointer = json.loads(raw["pointer"])
    if pointer.get("schema") != recovery.POINTER_SCHEMA or state == base:
        raise ValueError("this bounded migration requires one unamended recovery epoch")
    new_spec = amended_spec(spec)
    new, new_plan, validation = _compile(new_spec)
    new_board = _board_revision(raw["board"], spec, new_spec, old.plan_id, new.plan_id)
    old_tasks, new_tasks = _tasks(native, root, raw["board"]), _tasks(native, root, new_board)
    expected_tasks = _tasks(native, root, compiler._render_board(spec, old.plan_id).encode())
    if set(old_tasks) != set(new_tasks) or set(old_tasks) != {task["id"] for task in spec["tasks"]}:
        raise ValueError("native board task set differs")
    for key, task in old_tasks.items():
        expected_task = expected_tasks[key]
        if (task.canonical_task_cid != expected_task.canonical_task_cid
                or task.validation != expected_task.validation or task.depends_on != expected_task.depends_on):
            raise ValueError("old native board contract differs from its specification")
    changed = [key for key in old_tasks if old_tasks[key].canonical_task_cid != new_tasks[key].canonical_task_cid]
    if changed != [TASK] or old_tasks[BASELINE_TASK].canonical_task_cid != BASELINE_CID:
        raise ValueError("amendment must change only TUI-02 and preserve the pinned first CID")
    if (old_tasks[BASELINE_TASK].status != "completed" or old_tasks[TASK].status != "todo"
            or runner._board_summary([old_tasks[TASK]])["manual_hold_task_ids"]
            or recovery._digest(raw["baseline_receipt"]) != baseline_receipt_sha256):
        raise ValueError("completed baseline identity, receipt or pending narrative task differs")
    if (new_tasks[TASK].validation != next(t for t in new_spec["tasks"] if t["id"] == TASK)["validation_commands"]
            or new_tasks[TASK].status != old_tasks[TASK].status):
        raise ValueError("native amended contract or status differs")
    # Return small identities, not mutable candidate source, as the approval/CAS
    # surface. Apply recomputes the one allowed recipe from these exact inputs.
    return {"schema": SCHEMA, "repo_root": str(root), "state_dir": str(state),
            "source_head": _head(root), "old_plan_id": old.plan_id, "new_plan_id": new.plan_id,
            "sha256": {key: recovery._digest(value) for key, value in raw.items()},
            "task_id": TASK, "old_task_cid": old_tasks[TASK].canonical_task_cid,
            "new_task_cid": new_tasks[TASK].canonical_task_cid,
            "baseline_task_cid": BASELINE_CID, "native_validation": validation,
            "unchanged_task_cids": {key: task.canonical_task_cid for key, task in old_tasks.items() if key != TASK}}


def _assert_containers_quiescent(state: Path) -> dict[str, Any]:
    from ipfs_accelerate_py.agent_supervisor.runtime import grok_cli_runner as runtime
    binary = runtime._docker_isolation_binary()
    if not binary:
        raise ValueError("trusted Docker observation is unavailable")
    command = [binary, "--host=unix:///var/run/docker.sock"]
    def observe(arguments: list[str]) -> str:
        result = subprocess.run(command + arguments, stdin=subprocess.DEVNULL, text=True,
            capture_output=True, timeout=10, check=True, env=runtime._docker_control_env())
        if len(result.stdout.encode()) > 2_000_000:
            raise ValueError("Docker amendment inventory exceeds bound")
        return result.stdout
    identifiers = observe(["ps", "-a", "--no-trunc", "--filter",
        "label=ipfs_accelerate.grok_isolation=true", "--format", "{{.ID}}"]).splitlines()
    if len(identifiers) > 256 or any(re.fullmatch(r"[0-9a-f]{64}", item) is None for item in identifiers):
        raise ValueError("Docker amendment inventory is invalid")
    matched = []
    projection = '{"Id":{{json .Id}},"Running":{{json .State.Running}},"Mounts":{{json .Mounts}}}'
    for identifier in identifiers:
        row = json.loads(observe(["inspect", "--format", projection, identifier]))
        if not isinstance(row, dict) or row.get("Id") != identifier or not isinstance(row.get("Mounts"), list):
            raise ValueError("Docker amendment container identity is unavailable")
        for mount in row["Mounts"]:
            if not isinstance(mount, dict):
                raise ValueError("Docker amendment mount is invalid")
            if mount.get("Type") != "bind":
                continue
            source = Path(str(mount.get("Source", "")))
            if not source.is_absolute():
                raise ValueError("Docker amendment bind source is invalid")
            if source == state or source.is_relative_to(state) or state.is_relative_to(source):
                if row.get("Running") is not False:
                    raise ValueError("campaign Docker worker is running or unknown")
                matched.append(identifier)
                break
    return {"running_matching_containers": 0, "stopped_container_ids": matched}


def _native_snapshot(root: Path, state: Path) -> dict[str, Any]:
    payload, authority = runner._read_native_state(root, state / f"{runner.STATE_PREFIX}_task_state.json", timeout_seconds=10)
    if payload.get("read_error") or authority.get("source") != "native_control_plane":
        raise ValueError("existing native control-plane state is required")
    return payload


def _completed_queue_bindings(root: Path, state: Path, branch: str) -> dict[str, set[str]]:
    """Use native versioned completion rules over an existing read-only store.

    The caller retains hold_merge_queue_settlement. Only the connection
    transport is adapted: constructing MergeQueue would initialize/migrate the
    store. The native method still validates schema, primary CID and target.
    """
    import duckdb
    from ipfs_accelerate_py.agent_supervisor.merge.checkout_lock import checkout_repository_id
    from ipfs_accelerate_py.agent_supervisor.merge.merge_queue import MergeQueue
    from ipfs_accelerate_py.agent_supervisor.task_sources.duckdb_state import (
        DuckDBCursor, connect_duckdb_with_policy,
    )

    class ReadOnlyConnection:
        def __enter__(self):
            self.connection = connect_duckdb_with_policy(duckdb, state / "merge-queue/merge_queue.duckdb", read_only=True)
            return self

        def execute(self, sql, parameters=()):
            return DuckDBCursor(self.connection.execute(sql, parameters))

        def __exit__(self, *_args):
            self.connection.close()

    queue = object.__new__(MergeQueue)
    queue.target_repository_id = checkout_repository_id(root)
    queue.target_branch = branch
    queue.require_target_binding = True
    queue._connect = ReadOnlyConnection
    return queue.completed_task_cid_bindings()


def _assert_quiescent(root: Path, state: Path, old_plan_id: str, old_cid: str, new_cid: str,
                      *, task_id: str = TASK) -> dict[str, Any]:
    _, native = runner._native_modules(root)
    launcher = recovery._object(state / "launcher.json")
    heartbeat = recovery._object(state / f"{runner.STATE_PREFIX}_supervisor_status.json", legacy_group_write=True)
    if launcher.get("repo_root") != str(root) or launcher.get("plan_id") != old_plan_id:
        raise ValueError("stopped launcher source binding differs")
    processes = recovery._assert_processes_absent(state, state, launcher, {}, heartbeat)
    containers = _assert_containers_quiescent(state)
    payload = _native_snapshot(root, state)
    if any(payload.get(key) for key in ("implementation_in_progress", "active_task_id", "active_task_cid",
            "active_attempt", "active_worktree_path", "active_branch", "active_provider_runner")):
        raise ValueError("native campaign still has an active implementation")
    if ((payload.get("task_identities") or {}).get(BASELINE_TASK, {}).get("canonical_task_cid") != BASELINE_CID):
        raise ValueError("native completed baseline source identity differs")
    if _completed_queue_bindings(root, state, launcher.get("merge_target", "")).get(BASELINE_TASK) != {BASELINE_CID}:
        raise ValueError("exact versioned native queue completion of the baseline is required")
    forbidden_lists = ("completed_task_ids", "assumed_completed_task_ids", "blocked_task_ids", "external_reserved_task_ids")
    refs = {task_id, old_cid, new_cid}
    if any(set(payload.get(key, [])) & refs for key in forbidden_lists):
        raise ValueError("changed task is completed, held, blocked or reserved")
    for key in ("implementation_attempts", "implementation_attempts_by_cid", "protected_implementation_attempts",
                "retry_budget_repair_receipts", "retry_budget_repair_rearm_receipts",
                "stale_proposal_replay_rearm_receipts", "validation_obsolescence_rearm_receipts"):
        if any(value for ref, value in (payload.get(key) or {}).items()
               if ref in refs or isinstance(value, Mapping) and any(
                   isinstance(value.get(field), str) and value[field] in refs
                   for field in ("task_id", "canonical_task_cid", "task_revision_cid"))):
            raise ValueError("changed task has consumed attempts, held state or retry history")
    status = (payload.get("task_statuses") or {}).get(task_id, "todo")
    if status not in {"todo", "needed", "pending", "waiting"}:
        raise ValueError("changed task native status is not pending")
    facade = object.__new__(native.PortalImplementationDaemon)
    facade.repo_root, facade.state_path = root, state / f"{runner.STATE_PREFIX}_task_state.json"
    for cid in (old_cid, new_cid):
        if os.path.lexists(facade._implementation_task_claim_path(task_id, canonical_task_cid=cid)):
            raise ValueError("changed task has an existing native claim")
    for name in ("implementation.lock", native.IMPLEMENTATION_PROTECTED_ACTIVE_SNAPSHOT_FILENAME,
                 native.IMPLEMENTATION_PROTECTED_INCIDENT_FILENAME):
        if os.path.lexists(state / name):
            raise ValueError("native implementation claim or protected fence remains")
    from ipfs_accelerate_py.agent_supervisor.merge.worktree_lifecycle import WorktreeLifecycleStore
    if any(record.task_id == task_id or record.canonical_task_cid in {old_cid, new_cid}
           for record in WorktreeLifecycleStore(repo_root=root).iter_records()):
        raise ValueError("changed task has native worktree history")
    events = state / f"{runner.STATE_PREFIX}_events.jsonl"
    if events.exists():
        for line in recovery._owned_bytes(events, runner.MAX_EVENT_HISTORY_BYTES, legacy_group_write=True).decode().splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except ValueError as exc:
                raise ValueError("native execution history is malformed") from exc
            if not isinstance(event, dict):
                raise ValueError("native execution history is malformed")
            if event.get("task_id") == task_id or event.get("canonical_task_cid") in refs:
                raise ValueError("changed task already has native execution history")
    return {"state_sha256": recovery._digest(_encoded(payload)), "processes": processes,
            "containers": containers, "native_state": payload}


@contextmanager
def _native_maintenance(root: Path, *, operation: str = "pending_tui_baseline_amendment"):
    from ipfs_accelerate_py.agent_supervisor.merge import checkout_lock as locks
    paths = [locks.board_scoped_protected_path_maintenance_lock_path(root, "complaint-intake-improvement"),
             locks.board_scoped_checkout_mutation_lock_path(root, "complaint-intake-improvement")]
    leases = []
    try:
        for path in paths:
            metadata = locks.checkout_lock_metadata(
                kind="implementation-protected-maintenance" if not leases else "merge",
                repo_root=root, owner_script="",
                extra={"lease_id": uuid.uuid4().hex, "operation": operation})
            lease, _, _, _ = locks.acquire_checkout_mutation_lease(path, metadata, owner_active=lambda _: True)
            if lease is None:
                raise ValueError("native maintenance or merge owner is present")
            leases.append(lease)
        yield
    finally:
        for lease in reversed(leases):
            if not locks.release_checkout_mutation_lease(lease, require_exact_metadata=True):
                raise ValueError("native amendment lease changed; retained for inspection")


def _write(path: Path, raw: bytes, *, mode: int = 0o600) -> None:
    import tempfile
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        Path(temporary).unlink(missing_ok=True)


def apply_tui_baseline_amendment(repo_root: Path, spec_path: Path, base_state_dir: Path,
                                 *, expected: Mapping[str, Any]) -> dict[str, Any]:
    """CAS-publish the reviewed recipe; never launch or mutate native task state.

    The pointer is the final publication record. An interruption during the
    multi-file replacement leaves old pointer/spec bindings inconsistent and
    therefore refuses startup; snapshots are retained for explicit recovery.
    """
    root, spec_path, base = repo_root.resolve(), spec_path.resolve(), base_state_dir.resolve()
    state = recovery.resolve_active_epoch(root, spec_path, base)
    for directory in (base, state):
        identity = directory.stat()
        if identity.st_uid != os.getuid() or identity.st_mode & 0o077:
            raise ValueError("amendment campaign directories must be owned and private")
    with ExitStack() as stack:
        stack.enter_context(runner._lock(base, blocking=False))
        stack.enter_context(runner._lock(state, blocking=False))
        stack.enter_context(runner._lock(state, "runner.lock", blocking=False))
        current = review_tui_baseline_amendment(root, spec_path, base,
            baseline_receipt_sha256=expected.get("sha256", {}).get("baseline_receipt", ""))
        if current != dict(expected):
            raise ValueError("reviewed source/spec/plan/board/pointer CAS inputs changed")
        stack.enter_context(_native_maintenance(root))
        from ipfs_accelerate_py.agent_supervisor.merge.checkout_lock import checkout_repository_id
        from ipfs_accelerate_py.agent_supervisor.merge.merge_queue import hold_merge_queue_settlement
        launcher = recovery._object(state / "launcher.json")
        queue = stack.enter_context(hold_merge_queue_settlement(state / "merge-queue",
            target_repository_id=checkout_repository_id(root), target_branch=launcher.get("merge_target", ""),
            lock_timeout_seconds=1.0))
        if queue.get("settled") is not True:
            raise ValueError("native merge queue has pending or processing work")
        before = _assert_quiescent(root, state, current["old_plan_id"], current["old_task_cid"], current["new_task_cid"])
        raw = {"spec": _source_bytes(spec_path), "plan": _source_bytes(root / compiler.PLAN_RELATIVE),
               "board": _source_bytes(root / compiler.BOARD_RELATIVE),
               "pointer": recovery._owned_bytes(base / "active_epoch.json"),
               "baseline_receipt": _source_bytes(root / BASELINE_RECEIPT)}
        old_spec = compiler.validate_spec(json.loads(raw["spec"]))
        new_spec = amended_spec(old_spec)
        plan, new_plan, _ = _compile(new_spec)
        new = {"spec": _encoded(new_spec), "plan": new_plan,
               "board": _board_revision(raw["board"], old_spec, new_spec, current["old_plan_id"], plan.plan_id)}
        origin = json.loads(raw["pointer"])
        origin_receipt = recovery._owned_bytes(state / recovery.RECEIPT_NAME)
        origin_body = json.loads(origin_receipt)
        quarantine = Path(origin_body["quarantine_path"])
        if recovery._digest(recovery._owned_bytes(quarantine)) != origin_body["quarantine_sha256"]:
            raise ValueError("immutable original quarantine proof changed")
        # All potentially slow native and Docker observations occur before the
        # final source CAS. No native state is saved, re-registered or copied.
        after = _assert_quiescent(root, state, current["old_plan_id"], current["old_task_cid"], current["new_task_cid"])
        if after["native_state"] != before["native_state"] or review_tui_baseline_amendment(root, spec_path, base,
                baseline_receipt_sha256=current["sha256"]["baseline_receipt"]) != current:
            raise ValueError("campaign or reviewed source changed before publication")
        directory = base / "amendments" / recovery._digest(plan.plan_id.encode())
        if directory.parent.resolve() != directory.parent:
            raise ValueError("amendment directory cannot traverse symlinks")
        directory.parent.mkdir(mode=0o700, exist_ok=True)
        parent_stat = directory.parent.stat()
        if parent_stat.st_uid != os.getuid() or parent_stat.st_mode & 0o077:
            raise ValueError("amendment directory must be owned and private")
        directory.mkdir(mode=0o700)
        snapshots = {**{"old_" + key: value for key, value in raw.items()},
                     **{"new_" + key: value for key, value in new.items()},
                     "origin_recovery": origin_receipt}
        for name, data in snapshots.items():
            _write(directory / (name + ".snapshot"), data)
        receipt = {**current, "schema": SCHEMA, "epoch": origin["epoch"],
            "origin_recovery_receipt_sha256": recovery._digest(origin_receipt),
            "snapshot_sha256": {key: recovery._digest(value) for key, value in snapshots.items()},
            "native_state_sha256": before["state_sha256"],
            "merge_queue_settlement": queue,
            "baseline_completion": {"task_id": BASELINE_TASK, "canonical_task_cid": BASELINE_CID,
                "source": "native_completed_task_cid_bindings", "queue_receipt_cid": queue["receipt_cid"]},
            "preserved_attempts": {key: before["native_state"].get(key, {}) for key in
                ("implementation_attempts", "implementation_attempts_by_cid")},
            "preserved_completed_task_ids": before["native_state"].get("completed_task_ids", []),
            "unchanged_native_accounting": True, "same_epoch": True,
            "quarantine_sha256": origin_body["quarantine_sha256"],
            **{key: False for key in _NO_AUTHORITY}}
        _write(directory / "receipt.json", _encoded(receipt))
        pointer = {"schema": POINTER_SCHEMA, "repo_root": str(root), "plan_id": plan.plan_id,
            "origin_plan_id": current["old_plan_id"], "epoch": origin["epoch"],
            "recovery_receipt_sha256": origin["recovery_receipt_sha256"],
            "amendment": str((directory / "receipt.json").relative_to(base)),
            "amendment_receipt_sha256": recovery._digest(_encoded(receipt))}
        for name, path in (("spec", spec_path), ("plan", root / compiler.PLAN_RELATIVE),
                           ("board", root / compiler.BOARD_RELATIVE)):
            _write(path, new[name], mode=stat.S_IMODE(path.stat().st_mode))
        _write(base / "active_epoch.json", _encoded(pointer))
        if _native_snapshot(root, state) != before["native_state"]:
            raise ValueError("native state changed during publication; retain amendment for inspection")
        return receipt


def resolve_amended_epoch(root: Path, spec_path: Path, base: Path, pointer: Mapping[str, Any], plan_id: str,
                          *, historical_artifacts: Mapping[str, bytes] | None = None) -> Path:
    """Validate one v2 chain against current files or hash-bound successor snapshots.

    Only a successor resolver supplies historical_artifacts after validating
    its immutable snapshots. Active v2 resolution always checks current files.
    This avoids rewriting earlier receipts when a later pending task changes.
    """
    if historical_artifacts is not None and (
            set(historical_artifacts) != {"spec", "plan", "board", "baseline_receipt"}
            or any(not isinstance(value, bytes) for value in historical_artifacts.values())):
        raise ValueError("historical amendment artifact set differs")

    def artifact(name: str, path: Path) -> bytes:
        return historical_artifacts[name] if historical_artifacts is not None else _source_bytes(path)
    relative = pointer.get("amendment")
    if not isinstance(relative, str) or re.fullmatch(r"amendments/[0-9a-f]{64}/receipt\.json", relative) is None:
        raise ValueError("invalid amendment receipt path")
    path = base / relative
    if path.resolve() != path:
        raise ValueError("amendment receipt cannot traverse symlinks")
    raw = recovery._owned_bytes(path)
    receipt = json.loads(raw)
    if (not isinstance(receipt, dict) or receipt.get("schema") != SCHEMA
            or recovery._digest(raw) != pointer.get("amendment_receipt_sha256")
            or receipt.get("repo_root") != str(root.resolve())
            or receipt.get("new_plan_id") != plan_id
            or receipt.get("old_plan_id") != pointer.get("origin_plan_id")
            or receipt.get("epoch") != pointer.get("epoch")
            or receipt.get("same_epoch") is not True or receipt.get("unchanged_native_accounting") is not True
            or receipt.get("task_id") != TASK or receipt.get("baseline_task_cid") != BASELINE_CID
            or any(receipt.get(key) is not False for key in _NO_AUTHORITY)):
        raise ValueError("amendment receipt identity or authority changed")
    hashes = receipt.get("snapshot_sha256")
    required = {"old_spec", "old_plan", "old_board", "old_pointer", "old_baseline_receipt",
                "new_spec", "new_plan", "new_board", "origin_recovery"}
    if not isinstance(hashes, dict) or set(hashes) != required:
        raise ValueError("amendment snapshot set differs")
    snapshots = {name: recovery._owned_bytes(path.parent / (name + ".snapshot")) for name in required}
    if any(recovery._digest(value) != hashes[name] for name, value in snapshots.items()):
        raise ValueError("amendment snapshot hash changed")
    old_spec = compiler.validate_spec(json.loads(snapshots["old_spec"]))
    new_spec = compiler.validate_spec(json.loads(snapshots["new_spec"]))
    old_plan = compiler.build_improvement_work_plan(old_spec)
    new_plan = compiler.build_improvement_work_plan(new_spec)
    if (new_spec != amended_spec(old_spec) or old_plan.plan_id != receipt["old_plan_id"]
            or new_plan.plan_id != plan_id
            or json.loads(snapshots["old_plan"]) != {**old_plan.to_dict(), "plan_id": old_plan.plan_id}
            or json.loads(snapshots["new_plan"]) != {**new_plan.to_dict(), "plan_id": new_plan.plan_id}
            or snapshots["new_board"] != _board_revision(snapshots["old_board"], old_spec, new_spec,
                old_plan.plan_id, new_plan.plan_id)
            or recovery._digest(artifact("baseline_receipt", root / BASELINE_RECEIPT)) != hashes["old_baseline_receipt"]):
        raise ValueError("amendment is not the bounded baseline recipe or historical receipt changed")
    _, native = runner._native_modules(root)
    old_tasks = _tasks(native, root, snapshots["old_board"])
    new_tasks = _tasks(native, root, snapshots["new_board"])
    if (set(old_tasks) != set(new_tasks)
            or [key for key in old_tasks if old_tasks[key].canonical_task_cid != new_tasks[key].canonical_task_cid] != [TASK]
            or old_tasks[BASELINE_TASK].canonical_task_cid != BASELINE_CID
            or receipt.get("old_task_cid") != old_tasks[TASK].canonical_task_cid
            or receipt.get("new_task_cid") != new_tasks[TASK].canonical_task_cid
            or receipt.get("unchanged_task_cids") != {
                key: task.canonical_task_cid for key, task in old_tasks.items() if key != TASK}):
        raise ValueError("amendment task identity proof changed")
    current_tasks = _tasks(native, root, artifact("board", root / compiler.BOARD_RELATIVE))
    current_plan = json.loads(artifact("plan", root / compiler.PLAN_RELATIVE))
    route_keys = ("implementation provider", "provider role", "model", "router", "provider fallback")
    if (set(current_tasks) != set(new_tasks) or current_plan != json.loads(snapshots["new_plan"])
            or any(current_tasks[key].canonical_task_cid != task.canonical_task_cid
                or current_tasks[key].canonical_task_key != task.canonical_task_key
                or current_tasks[key].depends_on != task.depends_on
                or current_tasks[key].validation != task.validation
                or any(current_tasks[key].metadata.get(field) != task.metadata.get(field) for field in route_keys)
                for key, task in new_tasks.items())):
        raise ValueError("current amended board or formal-plan contract changed")
    old_pointer = json.loads(snapshots["old_pointer"])
    if (not isinstance(old_pointer, dict) or old_pointer.get("schema") != recovery.POINTER_SCHEMA
            or old_pointer.get("repo_root") != str(root.resolve())
            or old_pointer.get("plan_id") != pointer.get("origin_plan_id")
            or old_pointer.get("epoch") != pointer.get("epoch")
            or old_pointer.get("recovery_receipt_sha256") != pointer.get("recovery_receipt_sha256")
            or recovery._digest(artifact("spec", spec_path)) != hashes["new_spec"]):
        raise ValueError("amendment origin pointer or current specification changed")
    target = recovery._epoch_path(base, pointer.get("epoch"))
    origin_raw = recovery._owned_bytes(target / recovery.RECEIPT_NAME)
    origin = json.loads(origin_raw)
    if (not isinstance(origin, dict) or origin_raw != snapshots["origin_recovery"]
            or recovery._digest(origin_raw) != pointer.get("recovery_receipt_sha256")
            or recovery._digest(origin_raw) != receipt.get("origin_recovery_receipt_sha256")
            or origin.get("schema") != recovery.SCHEMA or origin.get("repo_root") != str(root.resolve())
            or origin.get("plan_id") != pointer.get("origin_plan_id")
            or origin.get("new_state_dir") != str(target) or receipt.get("state_dir") != str(target)
            or any(origin.get(key) is not False for key in ("old_quarantine_released", "completion_authority",
                "attempt_refunded", "candidate_adoption_authority", "evidence_reuse_authority"))):
        raise ValueError("original recovery receipt changed")
    return target
