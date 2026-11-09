"""Bounded watchdog for the complaint alignment execution board.

Each cycle repairs dead claims and dependency blocks, then runs one bounded
local check. Monitoring mode keeps polling while another owner is active or
checks need repair. An exclusive lock prevents duplicate execution.

This module does not construct a supervisor control-plane request and it is
not imported by the HTTP route.
"""

from __future__ import annotations

import json
import fcntl
import hashlib
import multiprocessing
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Mapping

from integrations.ipfs_accelerate.alignment_checks import CHECKERS


EXECUTION_SCHEMA = "complaint-generator.alignment_execution_board.v1"
_TERMINAL = {"completed", "failed", "cancelled"}
_KNOWN_STATUS = _TERMINAL | {"ready", "in_progress", "blocked"}
_REPAIRABLE_SUPERVISOR_REASONS = {"", "stall", "queue_stuck", "heartbeat_missing", "blocked", "dependency"}
_RECEIPT_LIMIT = 32
_LOCK_FD: int | None = None


def _source_fingerprint(root: Path) -> str:
    """Bind verification receipts to the first-party inputs they inspect."""
    digest = hashlib.sha256()
    for directory in ("applications", "integrations", "scripts"):
        for path in sorted((root / directory).rglob("*.py")):
            digest.update(str(path.relative_to(root)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


@contextmanager
def _state_lock(path: Path):
    global _LOCK_FD
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(path.suffix + ".lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
        else:
            _LOCK_FD = handle.fileno()
            try:
                yield True
            finally:
                _LOCK_FD = None
                fcntl.flock(handle, fcntl.LOCK_UN)


def _bounded_check(checker, root: Path, timeout_seconds: float) -> tuple[bool, str]:
    """Run checks in a disposable child so a stuck import cannot hang the monitor."""
    context = multiprocessing.get_context("fork")
    reader, writer = context.Pipe(duplex=False)

    def execute():
        # A surviving checker must not retain its dead parent's ownership lock.
        if _LOCK_FD is not None:
            os.close(_LOCK_FD)
        reader.close()
        try:
            ok, detail = checker(root)
            writer.send((bool(ok), str(detail)))
        except Exception as exc:
            writer.send((False, "checker raised " + type(exc).__name__ + ": " + str(exc)))
        finally:
            writer.close()

    child = context.Process(target=execute)
    child.start()
    writer.close()
    try:
        if not reader.poll(timeout_seconds):
            return False, f"checker timed out after {timeout_seconds:g}s"
        try:
            return reader.recv()
        except EOFError:
            return False, "checker exited without a result"
    finally:
        reader.close()
        child.join(timeout=0.1)
        if child.is_alive():
            child.terminate()
            child.join(timeout=1)
        if child.is_alive():
            child.kill()
            child.join()
        child.close()


def _as_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def _append_receipt(bucket: list[dict[str, Any]], receipt: dict[str, Any]) -> None:
    bucket.append(receipt)
    if len(bucket) > _RECEIPT_LIMIT:
        del bucket[:-_RECEIPT_LIMIT]


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _owner_dead(pid: int) -> bool:
    return pid not in (0, os.getpid()) and not _pid_alive(pid)


def load_formal_plan(path: Path) -> Any:
    """Load a formal work plan through the supervisor contract."""

    from integrations.ipfs_datasets.loader import ensure_import_paths

    ensure_import_paths("ipfs_accelerate_py.agent_supervisor")
    from ipfs_accelerate_py.agent_supervisor.planning.formal_planning_contracts import FormalWorkPlan

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("formal work plan JSON must be an object")
    return FormalWorkPlan.from_dict(payload)


def initial_execution_board(plan: Any) -> dict[str, Any]:
    """Build a ready board from a formal plan. Tasks with dependencies start blocked."""

    tasks: dict[str, Any] = {}
    for task in plan.tasks:
        depends_on = list(task.depends_on)
        blocked = bool(depends_on)
        tasks[task.task_id] = {
            "status": "blocked" if blocked else "ready",
            "attempts": 0,
            "heartbeat_unix": 0,
            "claim_pid": 0,
            "blocker": "dependency" if blocked else "",
            "depends_on": depends_on,
            "receipts": [],
        }
    return {
        "schema_version": EXECUTION_SCHEMA,
        "plan_id": plan.plan_id,
        "supervisor": {
            "status": "idle",
            "heartbeat_unix": 0,
            "blocked_reason": "",
            "pid": 0,
            "stall_receipts": [],
            "last_action": "",
        },
        "tasks": tasks,
    }


def _blank_task(depends_on: list[str]) -> dict[str, Any]:
    blocked = bool(depends_on)
    return {
        "status": "blocked" if blocked else "ready",
        "attempts": 0,
        "heartbeat_unix": 0,
        "claim_pid": 0,
        "blocker": "dependency" if blocked else "",
        "depends_on": depends_on,
        "receipts": [],
    }


def save_state(path: Path, state: Mapping[str, Any]) -> None:
    """Atomically replace the execution board."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=destination.name + ".", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(state, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_or_create_state(path: Path, plan: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Load the execution board, or rebuild it when the file is missing or malformed."""

    destination = Path(path)
    if not destination.exists():
        return initial_execution_board(plan), [{"kind": "state_created"}]
    try:
        payload = json.loads(destination.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        state = initial_execution_board(plan)
        _append_receipt(state["supervisor"]["stall_receipts"], {"kind": "state_rebuilt", "reason": "malformed_json"})
        return state, [{"kind": "state_rebuilt", "reason": "malformed_json"}]
    if not isinstance(payload, dict) or payload.get("schema_version") != EXECUTION_SCHEMA:
        state = initial_execution_board(plan)
        _append_receipt(state["supervisor"]["stall_receipts"], {"kind": "state_rebuilt", "reason": "schema"})
        return state, [{"kind": "state_rebuilt", "reason": "schema"}]
    if not isinstance(payload.get("tasks"), dict) or not isinstance(payload.get("supervisor"), dict):
        state = initial_execution_board(plan)
        _append_receipt(state["supervisor"]["stall_receipts"], {"kind": "state_rebuilt", "reason": "shape"})
        return state, [{"kind": "state_rebuilt", "reason": "shape"}]
    if payload.get("plan_id") != plan.plan_id:
        return initial_execution_board(plan), [{"kind": "state_rebuilt", "reason": "plan_changed"}]
    return payload, []


def repair_execution_board(
    state: dict[str, Any],
    plan: Any,
    *,
    now: int,
    stall_seconds: int,
    max_attempts: int,
) -> list[dict[str, Any]]:
    """Requeue stale claims, clear resolved dependency blocks, and repair the supervisor record."""

    if stall_seconds < 1:
        raise ValueError("stall_seconds must be positive")
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    receipts: list[dict[str, Any]] = []
    tasks_by_id = {task.task_id: task for task in plan.tasks}
    board_tasks = state["tasks"]
    if not isinstance(board_tasks, dict):
        raise ValueError("execution board tasks must be an object")

    if state.get("plan_id") != plan.plan_id:
        receipts.append({"kind": "plan_id_refreshed", "at_unix": now})
        state["plan_id"] = plan.plan_id

    for task in plan.tasks:
        if task.task_id not in board_tasks or not isinstance(board_tasks.get(task.task_id), dict):
            board_tasks[task.task_id] = _blank_task(list(task.depends_on))
            receipts.append({"kind": "added_missing_task", "task_id": task.task_id, "at_unix": now})

    for task_id, record in list(board_tasks.items()):
        if task_id not in tasks_by_id:
            if isinstance(record, dict) and record.get("status") not in _TERMINAL:
                record["status"] = "cancelled"
                record["blocker"] = "not_in_plan"
                record["claim_pid"] = 0
                receipts.append({"kind": "cancelled_unknown_task", "task_id": task_id, "at_unix": now})
            continue
        if not isinstance(record, dict):
            board_tasks[task_id] = _blank_task(list(tasks_by_id[task_id].depends_on))
            receipts.append({"kind": "rebuilt_task", "task_id": task_id, "at_unix": now})
            continue
        record["depends_on"] = list(tasks_by_id[task_id].depends_on)
        record["attempts"] = _as_int(record.get("attempts"))
        record["heartbeat_unix"] = _as_int(record.get("heartbeat_unix"))
        record["claim_pid"] = _as_int(record.get("claim_pid"))
        record["blocker"] = str(record.get("blocker") or "")
        if not isinstance(record.get("receipts"), list):
            record["receipts"] = []

    supervisor = state.setdefault("supervisor", {})
    if not isinstance(supervisor, dict):
        supervisor = {}
        state["supervisor"] = supervisor
    supervisor.setdefault("stall_receipts", [])
    if not isinstance(supervisor.get("stall_receipts"), list):
        supervisor["stall_receipts"] = []
    supervisor["heartbeat_unix"] = _as_int(supervisor.get("heartbeat_unix"))
    supervisor["pid"] = _as_int(supervisor.get("pid"))
    supervisor["blocked_reason"] = str(supervisor.get("blocked_reason") or "")
    supervisor["status"] = str(supervisor.get("status") or "idle")
    supervisor.setdefault("last_action", "")

    supervisor_stale = _owner_dead(supervisor["pid"]) or supervisor["heartbeat_unix"] <= 0 or (
        now - supervisor["heartbeat_unix"]
    ) >= stall_seconds
    status = supervisor["status"]
    reason = supervisor["blocked_reason"]
    should_repair_supervisor = (status == "blocked" and reason in _REPAIRABLE_SUPERVISOR_REASONS) or (
        status == "running" and supervisor_stale
    )
    if should_repair_supervisor:
        receipt = {
            "kind": "supervisor_repaired",
            "from_status": status,
            "blocked_reason": reason,
            "at_unix": now,
        }
        receipts.append(receipt)
        _append_receipt(supervisor["stall_receipts"], receipt)
        supervisor["status"] = "idle"
        supervisor["blocked_reason"] = ""
        supervisor["pid"] = 0
        supervisor["heartbeat_unix"] = now

    for task_id, record in board_tasks.items():
        if task_id not in tasks_by_id or record.get("status") != "in_progress":
            continue
        heartbeat = _as_int(record.get("heartbeat_unix"))
        claim_dead = _owner_dead(_as_int(record.get("claim_pid")))
        stale = claim_dead or heartbeat <= 0 or (now - heartbeat) >= stall_seconds
        if not stale:
            continue
        record["attempts"] = _as_int(record.get("attempts")) + 1
        record["claim_pid"] = 0
        record["heartbeat_unix"] = 0
        if record["attempts"] >= max_attempts:
            record["status"] = "blocked"
            record["blocker"] = "attempt_cap"
            receipt = {"kind": "attempt_cap", "task_id": task_id, "attempts": record["attempts"], "at_unix": now}
        else:
            record["status"] = "ready"
            record["blocker"] = ""
            receipt = {"kind": "stall_requeued", "task_id": task_id, "attempts": record["attempts"], "at_unix": now}
        receipts.append(receipt)
        _append_receipt(record["receipts"], receipt)

    for _ in range(len(board_tasks) + 1):
        changed = False
        for task_id, record in board_tasks.items():
            if task_id not in tasks_by_id:
                continue
            depends_on = list(record.get("depends_on") or [])
            deps_done = all(board_tasks.get(dep, {}).get("status") == "completed" for dep in depends_on)
            status = str(record.get("status") or "")
            blocker = str(record.get("blocker") or "")
            if status == "blocked" and blocker in {"stall", "supervisor_stall"}:
                record["status"] = "ready"
                record["blocker"] = ""
                changed = True
                receipt = {"kind": "stall_block_cleared", "task_id": task_id, "at_unix": now}
                receipts.append(receipt)
                _append_receipt(record["receipts"], receipt)
                status = "ready"
                blocker = ""
            if status not in _KNOWN_STATUS:
                record["status"] = "ready" if deps_done else "blocked"
                record["blocker"] = "" if deps_done else "dependency"
                changed = True
                receipts.append({"kind": "status_normalized", "task_id": task_id, "at_unix": now})
                continue
            if status == "ready" and not deps_done:
                record["status"] = "blocked"
                record["blocker"] = "dependency"
                changed = True
                receipts.append({"kind": "dependency_blocked", "task_id": task_id, "at_unix": now})
            elif status == "blocked" and blocker in {"", "dependency", "waiting_on_dependency"} and deps_done:
                record["status"] = "ready"
                record["blocker"] = ""
                changed = True
                receipt = {"kind": "dependency_cleared", "task_id": task_id, "at_unix": now}
                receipts.append(receipt)
                _append_receipt(record["receipts"], receipt)
        if not changed:
            break
    return receipts


def _next_ready(state: Mapping[str, Any]) -> str:
    ready = [
        task_id
        for task_id, record in state["tasks"].items()
        if isinstance(record, dict) and record.get("status") == "ready"
    ]
    return sorted(ready)[0] if ready else ""


def task_counts(state: Mapping[str, Any]) -> dict[str, int]:
    counts = {status: 0 for status in sorted(_KNOWN_STATUS)}
    for record in state["tasks"].values():
        if isinstance(record, dict):
            status = str(record.get("status") or "")
            if status in counts:
                counts[status] += 1
    return counts


def run_cycle(
    state: dict[str, Any],
    plan: Any,
    *,
    repo_root: Path,
    now: int,
    stall_seconds: int,
    max_attempts: int,
    checkers: Mapping[str, Callable[[Path], tuple[bool, str]]] | None = None,
    save: Callable[[], None] | None = None,
    checker_timeout_seconds: float = 30,
) -> dict[str, Any]:
    """Repair the board, then run at most one ready task."""

    repairs = repair_execution_board(
        state,
        plan,
        now=now,
        stall_seconds=stall_seconds,
        max_attempts=max_attempts,
    )
    supervisor = state["supervisor"]
    if supervisor.get("status") in {"running", "blocked", "paused", "stopped", "stopping"}:
        supervisor["last_action"] = "held"
        return {"action": "held", "task_id": "", "ok": False, "repairs": repairs}
    in_progress = sorted(
        task_id
        for task_id, record in state["tasks"].items()
        if isinstance(record, dict) and record.get("status") == "in_progress"
    )
    if in_progress:
        supervisor["last_action"] = "held"
        return {"action": "held", "task_id": in_progress[0], "ok": False, "repairs": repairs}

    task_id = _next_ready(state)
    if not task_id:
        supervisor["status"] = "idle"
        supervisor["pid"] = 0
        supervisor["last_action"] = "idle"
        supervisor["heartbeat_unix"] = now
        return {"action": "idle", "task_id": "", "ok": False, "repairs": repairs}

    record = state["tasks"][task_id]
    record["status"] = "in_progress"
    record["heartbeat_unix"] = now
    record["claim_pid"] = os.getpid()
    record["blocker"] = ""
    supervisor["status"] = "running"
    supervisor["pid"] = os.getpid()
    supervisor["heartbeat_unix"] = now
    supervisor["blocked_reason"] = ""
    supervisor["last_action"] = "running"
    if save is not None:
        save()

    checker = (checkers or {}).get(task_id) or CHECKERS.get(task_id)
    if checker is None:
        ok, detail = False, "missing checker"
    else:
        ok, detail = _bounded_check(checker, Path(repo_root), checker_timeout_seconds)
    if ok:
        record["status"] = "completed"
        record["blocker"] = ""
        receipt = {"kind": "completed", "detail": detail, "at_unix": now}
    else:
        record["status"] = "failed"
        record["blocker"] = "check_failed"
        record["attempts"] = _as_int(record.get("attempts")) + 1
        receipt = {"kind": "failed", "detail": detail, "at_unix": now}
    record["claim_pid"] = 0
    record["heartbeat_unix"] = now
    _append_receipt(record["receipts"], receipt)
    supervisor["status"] = "idle"
    supervisor["pid"] = 0
    supervisor["heartbeat_unix"] = now
    supervisor["last_action"] = "executed"
    return {"action": "executed", "task_id": task_id, "ok": ok, "detail": detail, "repairs": repairs}


def board_completed(state: Mapping[str, Any], plan: Any) -> bool:
    return all(state["tasks"].get(task.task_id, {}).get("status") == "completed" for task in plan.tasks)


def run_watchdog(
    *,
    plan_path: Path,
    state_path: Path,
    repo_root: Path,
    max_cycles: int = 64,
    stall_seconds: int = 120,
    max_attempts: int = 3,
    now: Callable[[], int] | None = None,
    checkers: Mapping[str, Callable[[Path], tuple[bool, str]]] | None = None,
    monitor: bool = False,
    poll_seconds: float = 5,
    checker_timeout_seconds: float = 30,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Run checks with exclusive ownership, bounded retries, and optional monitoring.

    In monitoring mode, zero max_cycles means poll until completion. An exhausted
    check remains failed until its source inputs change; it is never marked done
    simply to unblock dependent tasks.
    """

    if max_cycles < 0 or (max_cycles == 0 and not monitor):
        raise ValueError("max_cycles must be positive, or zero in monitoring mode")
    if poll_seconds <= 0 or checker_timeout_seconds <= 0:
        raise ValueError("poll and checker timeout must be positive")
    if stall_seconds < 1 or max_attempts < 1:
        raise ValueError("stall_seconds and max_attempts must be positive")
    plan = load_formal_plan(plan_path)
    clock = now or (lambda: int(time.time()))
    with _state_lock(Path(state_path)) as owned:
        state, repairs = load_or_create_state(state_path, plan)
        last_action = "held"
        cycles = 0

        def _save() -> None:
            save_state(state_path, state)

        if owned:
            while max_cycles == 0 or cycles < max_cycles:
                if cycles:
                    # Workers and operators may have completed or resumed a held
                    # record since the previous poll. Never retain a stale snapshot.
                    state, loaded_repairs = load_or_create_state(state_path, plan)
                    repairs.extend(loaded_repairs)
                fingerprint = _source_fingerprint(Path(repo_root))
                active = any(r.get("status") == "in_progress" for r in state["tasks"].values()
                             if isinstance(r, dict))
                if state.get("source_fingerprint") != fingerprint and not active:
                    # Receipts from a previous checkout cannot prove current behavior.
                    for task in plan.tasks:
                        record = state["tasks"].get(task.task_id, {})
                        status = record.get("status") if isinstance(record, dict) else None
                        blocker = record.get("blocker") if isinstance(record, dict) else None
                        if status == "cancelled" or (status == "blocked" and blocker not in {
                            "", "dependency", "waiting_on_dependency", "stall", "supervisor_stall", "attempt_cap",
                        }):
                            continue
                        state["tasks"][task.task_id] = _blank_task(list(task.depends_on))
                    state["source_fingerprint"] = fingerprint
                    repairs.append({"kind": "source_revalidation", "at_unix": int(clock())})
                for task_id, record in state["tasks"].items():
                    if (isinstance(record, dict) and record.get("status") == "failed"
                            and record.get("blocker") == "check_failed"
                            and _as_int(record.get("attempts")) < max_attempts):
                        record["status"] = "ready"
                        record["blocker"] = ""
                        receipt = {"kind": "check_retried", "task_id": task_id, "at_unix": int(clock())}
                        if not isinstance(record.get("receipts"), list):
                            record["receipts"] = []
                        _append_receipt(record["receipts"], receipt)
                        repairs.append(receipt)
                cycles += 1
                outcome = run_cycle(
                    state, plan, repo_root=repo_root, now=int(clock()),
                    stall_seconds=stall_seconds, max_attempts=max_attempts,
                    checkers=checkers, save=_save,
                    checker_timeout_seconds=checker_timeout_seconds,
                )
                repairs.extend(outcome["repairs"])
                last_action = outcome["action"]
                _save()
                if board_completed(state, plan) and state.get("source_fingerprint") == _source_fingerprint(Path(repo_root)):
                    break
                if last_action in {"idle", "held"}:
                    if not monitor:
                        break
                    if max_cycles == 0 or cycles < max_cycles:
                        sleep(poll_seconds)

        source_current = state.get("source_fingerprint") == _source_fingerprint(Path(repo_root))
        completed = board_completed(state, plan) and source_current
        return {
            "status": "completed" if completed else "incomplete",
            "completed": completed,
            "cycles": cycles,
            "plan_id": plan.plan_id,
            "last_action": last_action,
            "task_counts": task_counts(state),
            "supervisor_status": state["supervisor"]["status"],
            "repairs": repairs,
            "off_request_path": True,
            "evidence_kind": "local_source_checks",
            "source_current": source_current,
            "pending_tasks": {
                key: {"status": value.get("status"), "blocker": value.get("blocker"),
                      "last_receipt": (value.get("receipts") or [None])[-1]}
                for key, value in state["tasks"].items()
                if isinstance(value, dict) and value.get("status") != "completed"
            },
        }
