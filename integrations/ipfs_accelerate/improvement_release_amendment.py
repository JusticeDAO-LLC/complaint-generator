"""Stopped-campaign amendment of REL03's prerequisite and admission phase.

This second bounded recipe preserves the v1 recovery and v2 narrative receipts.
It changes no native accounting, status, execution policy or completion evidence.
"""
from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping

from . import improvement_amendment as prior
from . import improvement_plan as compiler
from . import improvement_recovery as recovery
from . import improvement_runner as runner

SCHEMA = "complaint-improvement-release-dependency-amendment@1"
POINTER_SCHEMA = "complaint-improvement-active-epoch@3"
TASK = "CIMP-REL-03"
PREREQUISITE = "CIMP-TUI-12"
SCRIPT_COMMAND = "python scripts/validate_complaint_intake.py"
PRE_ADMISSION_COMMAND = SCRIPT_COMMAND + " --phase pre-admission"
POST_COMPLETION_COMMAND = SCRIPT_COMMAND + " --phase post-completion"
GUIDANCE = (
    "Implement explicit release-checker phases. The reviewed validation command "
    "uses --phase pre-admission: require genuine accepted evidence for all 57 "
    "other tasks including CIMP-TUI-12, run bounded mandatory offline suites on "
    "the candidate source with live-provider/network guards, and validate this "
    "checker's own behavior. Record release_qualified=false, "
    "self_completion_pending=true and CIMP-REL-03 as pending; never mark self "
    "complete or fabricate receipts. Default and --phase post-completion must "
    "strictly require all 58 actual native task completions and goal/subgoal "
    "evidence, with no unresolved required work. Only run that final audit after "
    "the genuine native merge/completion callback; only it may report release "
    "qualified. Preserve the committed pre-admission report and write any final "
    "report as a separate owned runtime artifact bound to real integration "
    "proof. Keep hash scopes explicit without a self-referential future commit "
    "hash, avoid recursive self-validation, and report optional live checks "
    "honestly. Missing, held, stale, skipped or unknown required evidence fails "
    "closed. This phase distinction waives no acceptance requirement and grants "
    "no completion, refund, callback or additional output authority."
)
_OLD_DEPENDENCIES = ["CIMP-REL-01", "CIMP-REL-02", "CIMP-OPS-06"]
_SNAPSHOTS = {"old_spec", "old_plan", "old_board", "old_pointer", "old_baseline_receipt",
              "prior_amendment_receipt", "origin_recovery", "new_spec", "new_plan", "new_board"}


def amended_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Repair prerequisite ordering and the explicit pre-completion checker call."""
    result = deepcopy(dict(spec))
    tasks = {task["id"]: task for task in result["tasks"]}
    if TASK not in tasks or PREREQUISITE not in tasks or tasks[TASK]["depends_on"] != _OLD_DEPENDENCIES:
        raise ValueError("pending release dependency recipe is absent or already applied")
    task = tasks[TASK]
    if (len(task["validation_commands"]) != 2
            or not task["validation_commands"][0].endswith("tests/test_intake_release_gate.py")
            or task["validation_commands"][1] != SCRIPT_COMMAND
            or GUIDANCE in task["implementation_prompt"]):
        raise ValueError("pending release validation differs from the reviewed phase recipe")
    task["depends_on"].append(PREREQUISITE)
    task["validation_commands"][1] = PRE_ADMISSION_COMMAND
    task["implementation_prompt"] += "\n\n" + GUIDANCE
    return compiler.validate_spec(result)


def _board_revision(raw: bytes, old_spec: Mapping[str, Any], new_spec: Mapping[str, Any],
                    old_id: str, new_id: str) -> bytes:
    text = raw.decode("utf-8")
    marker = f"<!-- plan_id: {old_id} -->"
    blocks = prior._blocks(raw)
    if text.count(marker) != 1 or TASK not in blocks:
        raise ValueError("release amendment board marker or task differs")
    old = next(task for task in old_spec["tasks"] if task["id"] == TASK)
    new = next(task for task in new_spec["tasks"] if task["id"] == TASK)
    original_block = blocks[TASK].decode()
    block = original_block
    for label, old_value, new_value in (
            ("Depends on", ", ".join(old["depends_on"]), ", ".join(new["depends_on"])),
            ("Validation", "; ".join(old["validation_commands"]), "; ".join(new["validation_commands"]))):
        before, after = f"- {label}: {old_value}", f"- {label}: {new_value}"
        if block.splitlines().count(before) != 1:
            raise ValueError("release board contract differs from the reviewed specification")
        block = block.replace(before + "\n", after + "\n", 1)
    guidance = re.findall(r"^- Runtime guidance: (.*)$", block, re.MULTILINE)
    if len(guidance) != 1 or len((guidance[0] + " " + GUIDANCE).encode()) > 8 * 1024:
        raise ValueError("release amendment needs one bounded runtime guidance field")
    changed = block.replace("- Runtime guidance: " + guidance[0] + "\n",
        "- Runtime guidance: " + guidance[0] + " " + GUIDANCE + "\n", 1)
    result = text.replace(original_block, changed, 1).replace(marker, f"<!-- plan_id: {new_id} -->", 1).encode()
    if any(prior._blocks(result)[key] != value for key, value in blocks.items() if key != TASK):
        raise ValueError("release amendment changed an unrelated task block")
    return result


def _historical_v2(root: Path, spec_path: Path, base: Path, pointer: Mapping[str, Any],
                    snapshots: Mapping[str, bytes]) -> Path:
    if pointer.get("schema") != prior.POINTER_SCHEMA:
        raise ValueError("release amendment requires exactly one validated v2 predecessor")
    relative = pointer.get("amendment")
    if not isinstance(relative, str) or re.fullmatch(r"amendments/[0-9a-f]{64}/receipt\.json", relative) is None:
        raise ValueError("invalid predecessor amendment receipt path")
    path = base / relative
    if path.resolve() != path:
        raise ValueError("predecessor amendment receipt cannot traverse symlinks")
    if prior._source_bytes(path) != snapshots["prior_amendment_receipt"]:
        raise ValueError("immutable v2 amendment receipt changed")
    return prior.resolve_amended_epoch(root, spec_path, base, pointer, pointer.get("plan_id", ""),
        historical_artifacts={"spec": snapshots["old_spec"], "plan": snapshots["old_plan"],
            "board": snapshots["old_board"], "baseline_receipt": snapshots["old_baseline_receipt"]})


def review_release_dependency_amendment(repo_root: Path, spec_path: Path, base_state_dir: Path,
                                        *, baseline_receipt_sha256: str) -> dict[str, Any]:
    """Review the exact second recipe/CAS inputs without writing artifacts."""
    root, spec_path, base = repo_root.resolve(), spec_path.resolve(), base_state_dir.resolve()
    if spec_path != root / compiler.SPEC_RELATIVE:
        raise ValueError("release amendment requires the canonical specification path")
    paths = {"spec": spec_path, "plan": root / compiler.PLAN_RELATIVE,
        "board": root / compiler.BOARD_RELATIVE, "pointer": base / "active_epoch.json",
        "baseline_receipt": root / prior.BASELINE_RECEIPT}
    raw = {key: prior._source_bytes(path) for key, path in paths.items()}
    pointer = json.loads(raw["pointer"])
    if pointer.get("schema") != prior.POINTER_SCHEMA:
        raise ValueError("release amendment requires the current v2 pointer")
    state = recovery.resolve_active_epoch(root, spec_path, base)
    previous_path = base / pointer["amendment"]
    raw["prior_amendment_receipt"] = recovery._owned_bytes(previous_path)
    raw["origin_recovery"] = recovery._owned_bytes(state / recovery.RECEIPT_NAME)
    spec = compiler.validate_spec(json.loads(raw["spec"]))
    old, old_plan, _ = prior._compile(spec)
    if json.loads(raw["plan"]) != json.loads(old_plan):
        raise ValueError("old formal plan differs from the current specification")
    new_spec = amended_spec(spec)
    new, _, validation = prior._compile(new_spec)
    new_board = _board_revision(raw["board"], spec, new_spec, old.plan_id, new.plan_id)
    _, native = runner._native_modules(root)
    old_tasks, new_tasks = prior._tasks(native, root, raw["board"]), prior._tasks(native, root, new_board)
    expected_tasks = prior._tasks(native, root, compiler._render_board(spec, old.plan_id).encode())
    if set(old_tasks) != set(new_tasks) or set(old_tasks) != set(expected_tasks):
        raise ValueError("release amendment native task set differs")
    for key, task in old_tasks.items():
        expected_task = expected_tasks[key]
        if (task.canonical_task_cid != expected_task.canonical_task_cid
                or task.validation != expected_task.validation or task.depends_on != expected_task.depends_on):
            raise ValueError("old native board contract differs from its specification")
    changed = [key for key in old_tasks if old_tasks[key].canonical_task_cid != new_tasks[key].canonical_task_cid]
    if set(changed) - {TASK} or old_tasks[prior.BASELINE_TASK].canonical_task_cid != prior.BASELINE_CID:
        raise ValueError("release amendment must change only REL03 and preserve the first CID")
    if (old_tasks[TASK].status != "todo" or runner._board_summary([old_tasks[TASK]])["manual_hold_task_ids"]
            or old_tasks[prior.BASELINE_TASK].status != "completed"
            or recovery._digest(raw["baseline_receipt"]) != baseline_receipt_sha256):
        raise ValueError("release task is not untouched pending or historical baseline differs")
    if (new_tasks[TASK].depends_on != _OLD_DEPENDENCIES + [PREREQUISITE]
            or new_tasks[TASK].validation != [old_tasks[TASK].validation[0], PRE_ADMISSION_COMMAND]
            or new_tasks[TASK].status != old_tasks[TASK].status):
        raise ValueError("native release amendment contract differs")
    return {"schema": SCHEMA, "repo_root": str(root), "state_dir": str(state),
        "source_head": prior._head(root), "old_plan_id": old.plan_id, "new_plan_id": new.plan_id,
        "sha256": {key: recovery._digest(value) for key, value in raw.items()}, "task_id": TASK,
        "old_task_cid": old_tasks[TASK].canonical_task_cid, "new_task_cid": new_tasks[TASK].canonical_task_cid,
        "baseline_task_cid": prior.BASELINE_CID, "native_validation": validation,
        "pre_admission_validation_command": PRE_ADMISSION_COMMAND,
        "post_completion_validation_command": POST_COMPLETION_COMMAND,
        "added_dependency": PREREQUISITE, "changed_task_cid_ids": changed,
        "unchanged_task_cids": {key: task.canonical_task_cid for key, task in old_tasks.items() if key != TASK}}


def _assert_quiescent(root: Path, state: Path, reviewed: Mapping[str, Any]) -> dict[str, Any]:
    result = prior._assert_quiescent(root, state, reviewed["old_plan_id"], reviewed["old_task_cid"],
        reviewed["new_task_cid"], task_id=TASK)
    strategy_path = state / f"{runner.STATE_PREFIX}_strategy.json"
    if os.path.lexists(strategy_path):
        strategy = recovery._object(strategy_path, legacy_group_write=True)
        if set(strategy.get("blocked_tasks", ())) & {TASK, reviewed["old_task_cid"], reviewed["new_task_cid"]}:
            raise ValueError("release task has a retained strategy hold")
    return result


def apply_release_dependency_amendment(repo_root: Path, spec_path: Path, base_state_dir: Path,
                                       *, expected: Mapping[str, Any]) -> dict[str, Any]:
    """CAS-publish only REL03's pending recipe; native state stays unchanged."""
    root, spec_path, base = repo_root.resolve(), spec_path.resolve(), base_state_dir.resolve()
    state = recovery.resolve_active_epoch(root, spec_path, base)
    for path in (base, state):
        metadata = path.stat()
        if metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
            raise ValueError("release amendment campaign directories must be owned and private")
    with ExitStack() as stack:
        for path, name in ((base, "launcher.lock"), (state, "launcher.lock"), (state, "runner.lock")):
            stack.enter_context(runner._lock(path, name, blocking=False))
        current = review_release_dependency_amendment(root, spec_path, base,
            baseline_receipt_sha256=expected.get("sha256", {}).get("baseline_receipt", ""))
        if current != dict(expected):
            raise ValueError("reviewed release source/spec/plan/board/pointer CAS inputs changed")
        stack.enter_context(prior._native_maintenance(root, operation="pending_release_dependency_amendment"))
        from ipfs_accelerate_py.agent_supervisor.merge.checkout_lock import checkout_repository_id
        from ipfs_accelerate_py.agent_supervisor.merge.merge_queue import hold_merge_queue_settlement
        launcher = recovery._object(state / "launcher.json")
        queue = stack.enter_context(hold_merge_queue_settlement(state / "merge-queue",
            target_repository_id=checkout_repository_id(root), target_branch=launcher.get("merge_target", ""),
            lock_timeout_seconds=1.0))
        if queue.get("settled") is not True:
            raise ValueError("native merge queue has pending or processing work")
        before = _assert_quiescent(root, state, current)
        raw = {"spec": prior._source_bytes(spec_path), "plan": prior._source_bytes(root / compiler.PLAN_RELATIVE),
            "board": prior._source_bytes(root / compiler.BOARD_RELATIVE),
            "pointer": recovery._owned_bytes(base / "active_epoch.json"),
            "baseline_receipt": prior._source_bytes(root / prior.BASELINE_RECEIPT)}
        origin = json.loads(raw["pointer"])
        previous_raw = recovery._owned_bytes(base / origin["amendment"])
        origin_raw = recovery._owned_bytes(state / recovery.RECEIPT_NAME)
        original = json.loads(origin_raw)
        if recovery._digest(recovery._owned_bytes(Path(original["quarantine_path"]))) != original["quarantine_sha256"]:
            raise ValueError("immutable original quarantine proof changed")
        old_spec = compiler.validate_spec(json.loads(raw["spec"]))
        new_spec = amended_spec(old_spec)
        plan, new_plan, _ = prior._compile(new_spec)
        new = {"spec": prior._encoded(new_spec), "plan": new_plan,
            "board": _board_revision(raw["board"], old_spec, new_spec, current["old_plan_id"], plan.plan_id)}
        after = _assert_quiescent(root, state, current)
        if after["native_state"] != before["native_state"] or review_release_dependency_amendment(root, spec_path, base,
                baseline_receipt_sha256=current["sha256"]["baseline_receipt"]) != current:
            raise ValueError("campaign or reviewed release source changed before publication")
        directory = base / "amendments" / recovery._digest(plan.plan_id.encode())
        if directory.parent.resolve() != directory.parent:
            raise ValueError("release amendment directory cannot traverse symlinks")
        directory.parent.mkdir(mode=0o700, exist_ok=True)
        metadata = directory.parent.stat()
        if metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
            raise ValueError("release amendment directory must be owned and private")
        directory.mkdir(mode=0o700)
        snapshots = {**{"old_" + key: value for key, value in raw.items()},
            **{"new_" + key: value for key, value in new.items()},
            "prior_amendment_receipt": previous_raw, "origin_recovery": origin_raw}
        if set(snapshots) != _SNAPSHOTS:
            raise ValueError("release amendment snapshot set differs")
        for name, value in snapshots.items():
            prior._write(directory / (name + ".snapshot"), value)
        receipt = {**current, "epoch": origin["epoch"], "origin_plan_id": origin["origin_plan_id"],
            "origin_recovery_receipt_sha256": recovery._digest(origin_raw),
            "prior_amendment_receipt_sha256": recovery._digest(previous_raw),
            "snapshot_sha256": {name: recovery._digest(value) for name, value in snapshots.items()},
            "native_state_sha256": before["state_sha256"], "merge_queue_settlement": queue,
            "baseline_completion": {"task_id": prior.BASELINE_TASK, "canonical_task_cid": prior.BASELINE_CID,
                "source": "native_completed_task_cid_bindings", "queue_receipt_cid": queue["receipt_cid"]},
            "preserved_attempts": {key: before["native_state"].get(key, {}) for key in
                ("implementation_attempts", "implementation_attempts_by_cid")},
            "preserved_completed_task_ids": before["native_state"].get("completed_task_ids", []),
            "unchanged_native_accounting": True, "same_epoch": True,
            "quarantine_sha256": original["quarantine_sha256"],
            **{key: False for key in prior._NO_AUTHORITY}}
        prior._write(directory / "receipt.json", prior._encoded(receipt))
        pointer = {"schema": POINTER_SCHEMA, "repo_root": str(root), "plan_id": plan.plan_id,
            "origin_plan_id": origin["origin_plan_id"], "prior_plan_id": current["old_plan_id"],
            "epoch": origin["epoch"], "recovery_receipt_sha256": origin["recovery_receipt_sha256"],
            "amendment": str((directory / "receipt.json").relative_to(base)),
            "amendment_receipt_sha256": recovery._digest(prior._encoded(receipt))}
        for key, path in (("spec", spec_path), ("plan", root / compiler.PLAN_RELATIVE), ("board", root / compiler.BOARD_RELATIVE)):
            prior._write(path, new[key], mode=stat.S_IMODE(path.stat().st_mode))
        prior._write(base / "active_epoch.json", prior._encoded(pointer))
        if prior._native_snapshot(root, state) != before["native_state"]:
            raise ValueError("native state changed during release publication; retain proof for inspection")
        return receipt


def resolve_release_amended_epoch(root: Path, spec_path: Path, base: Path,
                                   pointer: Mapping[str, Any], plan_id: str) -> Path:
    """Validate the bounded v1 recovery -> v2 narrative -> v3 dependency chain."""
    relative = pointer.get("amendment")
    if not isinstance(relative, str) or re.fullmatch(r"amendments/[0-9a-f]{64}/receipt\.json", relative) is None:
        raise ValueError("invalid release amendment receipt path")
    path = base / relative
    if path.resolve() != path:
        raise ValueError("release amendment receipt cannot traverse symlinks")
    raw = recovery._owned_bytes(path)
    receipt = json.loads(raw)
    if (not isinstance(receipt, dict) or receipt.get("schema") != SCHEMA
            or recovery._digest(raw) != pointer.get("amendment_receipt_sha256")
            or receipt.get("repo_root") != str(root.resolve()) or receipt.get("new_plan_id") != plan_id
            or receipt.get("old_plan_id") != pointer.get("prior_plan_id")
            or receipt.get("origin_plan_id") != pointer.get("origin_plan_id")
            or receipt.get("epoch") != pointer.get("epoch") or receipt.get("task_id") != TASK
            or receipt.get("added_dependency") != PREREQUISITE
            or receipt.get("pre_admission_validation_command") != PRE_ADMISSION_COMMAND
            or receipt.get("post_completion_validation_command") != POST_COMPLETION_COMMAND
            or receipt.get("baseline_task_cid") != prior.BASELINE_CID
            or receipt.get("same_epoch") is not True or receipt.get("unchanged_native_accounting") is not True
            or any(receipt.get(key) is not False for key in prior._NO_AUTHORITY)):
        raise ValueError("release amendment receipt identity or authority changed")
    hashes = receipt.get("snapshot_sha256")
    if not isinstance(hashes, dict) or set(hashes) != _SNAPSHOTS:
        raise ValueError("release amendment snapshot set differs")
    snapshots = {name: recovery._owned_bytes(path.parent / (name + ".snapshot")) for name in _SNAPSHOTS}
    if any(recovery._digest(value) != hashes[name] for name, value in snapshots.items()):
        raise ValueError("release amendment snapshot hash changed")
    old_spec = compiler.validate_spec(json.loads(snapshots["old_spec"]))
    new_spec = compiler.validate_spec(json.loads(snapshots["new_spec"]))
    old_plan, new_plan = compiler.build_improvement_work_plan(old_spec), compiler.build_improvement_work_plan(new_spec)
    if (new_spec != amended_spec(old_spec) or old_plan.plan_id != receipt["old_plan_id"] or new_plan.plan_id != plan_id
            or json.loads(snapshots["old_plan"]) != {**old_plan.to_dict(), "plan_id": old_plan.plan_id}
            or json.loads(snapshots["new_plan"]) != {**new_plan.to_dict(), "plan_id": new_plan.plan_id}
            or snapshots["new_board"] != _board_revision(snapshots["old_board"], old_spec, new_spec, old_plan.plan_id, plan_id)):
        raise ValueError("release amendment is not the bounded dependency recipe")
    old_pointer = json.loads(snapshots["old_pointer"])
    target = _historical_v2(root, spec_path, base, old_pointer, snapshots)
    if (old_pointer.get("plan_id") != receipt["old_plan_id"]
            or old_pointer.get("origin_plan_id") != pointer.get("origin_plan_id")
            or old_pointer.get("epoch") != pointer.get("epoch")
            or old_pointer.get("recovery_receipt_sha256") != pointer.get("recovery_receipt_sha256")
            or recovery._digest(snapshots["prior_amendment_receipt"]) != receipt.get("prior_amendment_receipt_sha256")
            or recovery._owned_bytes(target / recovery.RECEIPT_NAME) != snapshots["origin_recovery"]
            or recovery._digest(snapshots["origin_recovery"]) != receipt.get("origin_recovery_receipt_sha256")
            or receipt.get("state_dir") != str(target)):
        raise ValueError("release amendment predecessor chain changed")
    original = json.loads(snapshots["origin_recovery"])
    if (recovery._digest(recovery._owned_bytes(Path(original["quarantine_path"])))
            != original.get("quarantine_sha256")
            or receipt.get("quarantine_sha256") != original.get("quarantine_sha256")):
        raise ValueError("release amendment original quarantine proof changed")
    _, native = runner._native_modules(root)
    old_tasks, new_tasks = prior._tasks(native, root, snapshots["old_board"]), prior._tasks(native, root, snapshots["new_board"])
    if set(old_tasks) != set(new_tasks):
        raise ValueError("release amendment task set changed")
    changed = [key for key in old_tasks if old_tasks[key].canonical_task_cid != new_tasks[key].canonical_task_cid]
    if (set(changed) - {TASK}
            or receipt.get("changed_task_cid_ids") != changed
            or receipt.get("old_task_cid") != old_tasks[TASK].canonical_task_cid
            or receipt.get("new_task_cid") != new_tasks[TASK].canonical_task_cid
            or receipt.get("unchanged_task_cids") != {key: task.canonical_task_cid for key, task in old_tasks.items() if key != TASK}):
        raise ValueError("release amendment task identity proof changed")
    current = prior._tasks(native, root, prior._source_bytes(root / compiler.BOARD_RELATIVE))
    route_keys = ("implementation provider", "provider role", "model", "router", "provider fallback")
    if (set(current) != set(new_tasks)
            or json.loads(prior._source_bytes(root / compiler.PLAN_RELATIVE)) != json.loads(snapshots["new_plan"])
            or recovery._digest(prior._source_bytes(spec_path)) != hashes["new_spec"]
            or recovery._digest(prior._source_bytes(root / prior.BASELINE_RECEIPT)) != hashes["old_baseline_receipt"]
            or any(current[key].canonical_task_cid != task.canonical_task_cid
                or current[key].canonical_task_key != task.canonical_task_key
                or current[key].depends_on != task.depends_on or current[key].validation != task.validation
                or any(current[key].metadata.get(field) != task.metadata.get(field) for field in route_keys)
                for key, task in new_tasks.items())):
        raise ValueError("current release-amended source contract changed")
    return target
