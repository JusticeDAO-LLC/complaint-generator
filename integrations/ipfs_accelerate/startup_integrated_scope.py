"""Observe one already-integrated scope refusal without granting task authority.

Native has already refused to merge, retry, or complete this candidate. The
refusal stands only when the recorded commit is already contained by the merge
target, the worktree is unchanged, and the same binding check still rejects
the delta as outside the pending task. This lets the normal scheduler start.
It never consumes an attempt or retires the worktree.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Mapping

from . import release_evidence as evidence

_PENDING = {"todo", "ready", "needed", "pending"}
_REASON = "integrated_candidate_delta_outside_task_scope"


def retained_integrated_scope_refusal(supervisor, item, *, maintenance_result) -> bool:
    """Reprove the negative outcome. Any missing proof keeps startup blocked."""
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import (
        PortalImplementationDaemon,
        PortalTaskState,
        normalize_status,
    )

    try:
        if (not isinstance(maintenance_result, Mapping)
                or maintenance_result.get("maintenance_blocked") is True
                or maintenance_result.get("stuck") is True
                or getattr(supervisor, "_complaint_startup_preflight_pending", False) is not True):
            return False
        if not isinstance(item, Mapping) or item.get("merged") is not False:
            return False
        if item.get("recovery_result") or item.get("preflight_result"):
            return False
        merge = item.get("merge_result")
        if (not isinstance(merge, Mapping) or merge.get("attempted") is not False
                or merge.get("merged") is not False or merge.get("provider_dispatched") is not False
                or merge.get("attempt_consumed") is not False or merge.get("queued") is True
                or merge.get("reason") != _REASON):
            return False
        context = getattr(supervisor, "_complaint_startup_reconciliation_context", None)
        if not isinstance(context, Mapping):
            return False
        daemon = context.get("daemon")
        tasks = context.get("tasks_by_id")
        provenance_by_branch = context.get("provenance_by_branch")
        if (not isinstance(daemon, PortalImplementationDaemon) or not isinstance(tasks, Mapping)
                or not isinstance(provenance_by_branch, Mapping)):
            return False
        config = supervisor.config
        branch = str(item.get("branch") or "")
        head = str(item.get("head") or "")
        path = Path(str(item.get("path") or ""))
        root = Path(config.repo_root)
        trees = Path(config.worktree_root)
        if (not branch.startswith("implementation/") or re.fullmatch(r"[0-9a-f]{40}", head) is None
                or not path.is_absolute() or path.parent != trees
                or path.resolve(strict=True) != path or trees.resolve(strict=True) != trees
                or root.resolve(strict=True) != root):
            return False
        if not supervisor._git_ref_is_ancestor(root, head, config.merge_target_branch):
            return False
        if (supervisor._git_current_branch(path) != branch
                or supervisor._git_ref_commit(path, "HEAD") != head
                or supervisor._git_ref_commit(root, branch) != head
                or evidence._git(path, "status", "--porcelain", "--untracked-files=all",
                                  "--ignore-submodules=none")):
            return False
        matches = supervisor._integrated_candidate_task_matches(branch, tasks)
        if len(matches) != 1:
            return False
        task = matches[0]
        mapped = (context.get("task_ids_by_branch") or {}).get(branch)
        if (normalize_status(task.status) not in _PENDING
                or (mapped and mapped != task.task_id)):
            return False
        binding = supervisor._pending_integrated_candidate_binding(
            daemon=daemon, path=path, branch=branch, head=head, task=task,
            provenance=provenance_by_branch.get(branch))
        if binding.get("ready") is not False or binding.get("reason") != _REASON:
            return False
        state = PortalTaskState.load(Path(daemon.state_path))
        if (state.implementation_in_progress is not False or state.active_attempt
                or state.active_task_id or state.active_phase or state.active_worktree_path
                or state.active_provider_runner or state.active_log_path or state.active_branch
                or state.protected_implementation_attempts):
            return False
        if any(os.path.lexists(Path(config.state_dir) / "watchdog" / name)
               for name in ("HOLD", "OPERATOR_STOP")):
            return False
        return (getattr(supervisor, "_complaint_startup_reconciliation_context", None) is context
                and getattr(supervisor, "_complaint_startup_preflight_pending", False) is True)
    except Exception:
        return False
