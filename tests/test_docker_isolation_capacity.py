"""A Docker image inspect miss must not freeze every ready task."""
import os
from types import SimpleNamespace

import pytest

from integrations.ipfs_accelerate.docker_isolation_capacity import (
    capacity_isolating_daemon,
    record_is_docker_isolation_miss,
)

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

MESSAGE = "Default Grok quota route requires the pinned local Docker isolation image"


def _record(log_path, **overrides):
    body = {
        "reason": "provider_capacity_settlement_required",
        "returncode": 2,
        "attempt_consumed": True,
        "provider_dispatched": "unknown",
        "providers": ["grok"],
        "retry_authorized": False,
        "settlement_authority": False,
        "completion_authority": False,
        "cleanup_allowed": False,
        "task_id": "CIMP-UX-20",
        "execution_observation": {
            "task_execution_observed": False,
            "tool_event_count": 0,
            "model_calls": 0,
            "turns": 0,
        },
        "log_path": str(log_path),
    }
    body.update(overrides)
    return body


def _log(path, body):
    path.write_text(body)
    os.chmod(path, 0o600)
    return path


def test_exact_image_miss_is_not_a_board_wide_hold(tmp_path):
    log = _log(tmp_path / "attempt.log", f"Task: CIMP-UX-20\nCommand: runner\n\n{MESSAGE}\n")
    record = _record(log)
    assert record_is_docker_isolation_miss(record)

    class Native:
        _runtime_wake_coordinator = None

        def _retained_provider_capacity_deferral(self):
            return record

        def _run_once(self):
            return {"selected": "CIMP-UX-36"}

        def run_once(self):
            retained = self._retained_provider_capacity_deferral()
            if retained is not None:
                return {"implementation_result": retained}
            return self._run_once()

        def _run_implementation(self, task, state):
            assert self._retained_provider_capacity_deferral() is None
            return {"task_id": task.task_id, "attempted": True}

        def _provider_capacity_failure_from_log(self, log_path, *, command=(), returncode=None):
            return {"exhausted": True, "providers": ["grok"], "reason": "provider_capacity_exhausted"}

    daemon = capacity_isolating_daemon(Native)()
    assert daemon.run_once() == {"selected": "CIMP-UX-36"}
    assert daemon._retained_provider_capacity_deferral() is record
    assert daemon._run_implementation(SimpleNamespace(task_id="CIMP-UX-20"), None)["attempted"] is True
    assert daemon._retained_provider_capacity_deferral() is record
    assert daemon._run_implementation(SimpleNamespace(task_id="CIMP-UX-36"), None)["attempted"] is True
    assert daemon._retained_provider_capacity_deferral() is record
    assert daemon._provider_capacity_failure_from_log(log)["exhausted"] is False
    assert daemon._provider_capacity_failure_from_log(log)["retained_callback_required"] is False


def test_real_capacity_record_still_stops_the_board(tmp_path):
    log = _log(tmp_path / "quota.log", "Task: CIMP-UX-20\n\nGrok usage balance exhausted\n")
    record = _record(log)
    assert record_is_docker_isolation_miss(record) is False

    class Native:
        def _retained_provider_capacity_deferral(self):
            return record

        def run_once(self):
            retained = self._retained_provider_capacity_deferral()
            if retained is not None:
                return {"implementation_result": retained}
            raise AssertionError("real capacity reached implementation")

        def _run_once(self):
            raise AssertionError("real capacity reached the scheduler")

        def _run_implementation(self, task, state):
            retained = self._retained_provider_capacity_deferral()
            if retained is not None:
                return retained
            raise AssertionError("real capacity reached implementation")

    daemon = capacity_isolating_daemon(Native)()
    assert daemon.run_once()["implementation_result"] is record
    assert daemon._run_implementation(SimpleNamespace(task_id="CIMP-UX-36"), None) is record


@pytest.mark.parametrize("overrides", [
    {"returncode": 78},
    {"attempt_consumed": False},
    {"provider_dispatched": False},
    {"retry_authorized": True},
    {"providers": ["grok", "codex"]},
    {"execution_observation": {"task_execution_observed": True, "tool_event_count": 1, "model_calls": 0, "turns": 0}},
    {"reason": "provider_capacity_backoff"},
])
def test_nearby_capacity_shapes_stay_retained(tmp_path, overrides):
    log = _log(tmp_path / "attempt.log", f"Task: CIMP-UX-20\n\n{MESSAGE}\n")
    assert record_is_docker_isolation_miss(_record(log, **overrides)) is False
