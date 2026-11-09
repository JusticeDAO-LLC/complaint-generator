"""Finite handoff serialization and filesystem fences, using synthetic scope."""
from copy import deepcopy
import os
import time

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner
from integrations.ipfs_accelerate import validation_handoff as handoff
from tests.test_improvement_validation_activity import ownership, _binding

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _publish(c):
    binding = _binding(c)
    now = time.time()
    assert handoff.publish(runner, binding, activity_id="d" * 32, started_at=now - 1,
                           settled_at=now, deadline_at=binding["phase_deadline"])
    value = handoff.read(runner, binding, now_ts=now)
    assert value is not None
    return binding, value


def test_handoff_expires_without_refreshing_any_deadline_or_native_state(ownership):
    c = ownership
    before = deepcopy(c.body)
    binding, value = _publish(c)
    assert value["deadline_at"] == min(binding["phase_deadline"], value["settled_at"] + 30)
    assert handoff.read(runner, binding, now_ts=value["deadline_at"]) is None
    path = handoff._path(runner, binding)
    raw = path.read_bytes()
    assert not handoff.publish(runner, binding, activity_id=value["activity_id"], started_at=value["started_at"],
                               settled_at=value["settled_at"] + 10, deadline_at=binding["phase_deadline"])
    assert path.read_bytes() == raw and c.body == before


@pytest.mark.parametrize("damage", ["owner", "claim", "attempt", "cid", "phase", "source", "hold"])
def test_current_scope_changes_cannot_borrow_a_returned_executor(ownership, damage):
    c = ownership
    binding, value = _publish(c)
    if damage == "owner":
        c.identity.process_birth = type(c.birth)(os.getpid(), start_time_ticks=99)
    elif damage == "claim":
        c.claim_path.write_text(__import__("json").dumps({**c.claim, "lease_id": "changed-claim"}))
    elif damage == "attempt": c.body["active_attempt"] = 2
    elif damage == "cid": c.body["active_task_cid"] = "other-task"
    elif damage == "phase": c.body["active_phase"] = "implementing"
    elif damage == "source": c.body["active_worktree_path"] = str(c.target)
    else: c.body["manual_hold"] = True
    supervisor = type("ExplicitSyntheticSupervisor", (), {})()
    supervisor.config = type("ExplicitSyntheticConfig", (), {"state_dir": c.campaign, "repo_root": c.target})()
    state = type("ExplicitSyntheticState", (), c.body)()
    assert not handoff.owned(runner, supervisor, state, now_ts=time.time(), owner_pid=os.getpid())


@pytest.mark.parametrize("damage", ["future", "expanded", "phase_deadline", "completion", "state", "binding", "boolean"])
def test_modified_receipts_never_extend_or_grant_authority(ownership, damage):
    binding, value = _publish(ownership)
    changed = deepcopy(value)
    if damage == "future": changed["settled_at"] = time.time() + 10
    elif damage == "expanded": changed["deadline_at"] = value["settled_at"] + 31
    elif damage == "phase_deadline": changed["deadline_at"] = binding["phase_deadline"] + 1
    elif damage == "completion": changed["completion_authority"] = True
    elif damage == "state": changed["state"] = "running"
    elif damage == "binding": changed["binding"]["claim_lease_id"] = "forged"
    else: changed["settled_at"] = True
    assert not handoff.valid(runner, changed, binding, now_ts=time.time())


@pytest.mark.parametrize("damage", ["symlink", "hardlink", "mode"])
def test_aliased_or_shared_handoff_is_unusable(ownership, damage):
    binding, value = _publish(ownership)
    path = handoff._path(runner, binding)
    other = path.with_name("alias.json")
    if damage == "symlink":
        path.rename(other)
        path.symlink_to(other)
    elif damage == "hardlink": os.link(path, other)
    else: path.chmod(0o644)
    assert handoff.read(runner, binding, now_ts=time.time()) is None


def test_a_different_process_cannot_publish_for_the_controller(ownership):
    binding = _binding(ownership)
    binding["owner_birth"]["pid"] += 1
    now = time.time()
    assert not handoff.publish(runner, binding, activity_id="e" * 32, started_at=now - 1,
                               settled_at=now, deadline_at=binding["phase_deadline"])
