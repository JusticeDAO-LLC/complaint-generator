"""Native configuration and Host startup ordering, without running validation."""

from copy import deepcopy
from pathlib import Path

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner


ROOT = Path(__file__).resolve().parents[1]
pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def test_actual_native_config_allows_two_reconciliations_without_more_paid_attempts(tmp_path):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native

    argv = runner.native_argv(tmp_path / "board.md", tmp_path / "campaign", "main",
        worktree_root=tmp_path / "worktrees")
    assert argv.count("--worktree-reconciliation-max-merges") == 1
    parsed = native.parse_args(argv)
    config = native.supervisor_config_from_args(parsed, repo_root=ROOT)
    assert config.worktree_reconciliation_max_merges == 2
    assert config.max_task_attempts == 3
    assert config.max_restarts == 5
    assert config.implementation_timeout == runner.TIMEOUT_SECONDS
    assert config.implementation_max_timeout == runner.TIMEOUT_SECONDS


def _startup_with_result(result):
    """Exercise the Host guard at its preflight-to-child handoff seam."""
    trace = []

    class NativeSupervisor:
        def run_once(self, *, include_refill=True):
            trace.append(("maintenance", include_refill))
            return result

        def _run_forever_loop(self):
            self.run_once(include_refill=False)
            trace.append(("child_dispatch",))
            return "running"

    return runner._validation_aware_supervisor_class(NativeSupervisor)(), trace


@pytest.mark.parametrize("processed", [[], [{"branch": "implementation/cimp-ux-08", "merged": True}]])
def test_limit_deferred_candidate_blocks_child_after_startup_maintenance(processed):
    result = {"maintenance_blocked": False, "worktree_reconciliation": {
        "processed": processed,
        "skipped": [{"branch": "implementation/cimp-ux-15", "reason": "reconciliation_limit_reached"}],
    }}
    before = deepcopy(result)
    supervisor, trace = _startup_with_result(result)

    with pytest.raises(RuntimeError, match="candidate recovery remains unresolved"):
        supervisor._run_forever_loop()

    assert trace == [("maintenance", False)]
    assert supervisor._complaint_startup_preflight_pending is True
    assert result == before


def test_failed_first_validation_blocks_child_after_both_results_are_observed():
    result = {"maintenance_blocked": False, "worktree_reconciliation": {
        "processed": [
            {"branch": "implementation/cimp-ux-08", "merged": False,
             "merge_result": {"attempted": False, "merged": False, "reason": "validation_failed"}},
            {"branch": "implementation/cimp-ux-15", "merged": True},
        ],
        "skipped": [],
    }}
    before = deepcopy(result)
    supervisor, trace = _startup_with_result(result)

    with pytest.raises(RuntimeError, match="candidate recovery remains unresolved"):
        supervisor._run_forever_loop()

    assert trace == [("maintenance", False)]
    assert supervisor._complaint_startup_preflight_pending is True
    assert result == before


def test_scope_reason_without_retained_proof_still_blocks_child_dispatch():
    result = {"maintenance_blocked": False, "worktree_reconciliation": {
        "processed": [{
            "branch": "implementation/cimp-ux-24-retained",
            "head": "c0eab9002438d072a2e6bb0a04101f101abb8ca2",
            "merged": False,
            "merge_result": {
                "attempted": False, "merged": False, "provider_dispatched": False,
                "attempt_consumed": False, "reason": "integrated_candidate_delta_outside_task_scope",
            },
        }],
        "skipped": [],
    }}
    before = deepcopy(result)
    supervisor, trace = _startup_with_result(result)

    with pytest.raises(RuntimeError, match="candidate recovery remains unresolved"):
        supervisor._run_forever_loop()

    assert trace == [("maintenance", False)]
    assert supervisor._complaint_startup_preflight_pending is True
    assert result == before


def test_two_successful_candidate_results_allow_child_dispatch():
    result = {"maintenance_blocked": False, "worktree_reconciliation": {
        "processed": [{"merged": True}, {"merged": True}],
        "skipped": [{"reason": "non_implementation_branch"}],
    }}
    supervisor, trace = _startup_with_result(result)

    assert supervisor._run_forever_loop() == "running"
    assert trace == [("maintenance", False), ("child_dispatch",)]
    assert supervisor._complaint_startup_preflight_pending is False


def test_maintenance_failure_still_prevents_child_dispatch():
    supervisor, trace = _startup_with_result({"maintenance_blocked": True, "reason": "owned_lease_unavailable"})

    with pytest.raises(RuntimeError, match="Native startup preflight blocked: owned_lease_unavailable"):
        supervisor._run_forever_loop()

    assert trace == [("maintenance", False)]


def test_limit_deferral_during_later_maintenance_preserves_running_child():
    result = {"maintenance_blocked": False, "worktree_reconciliation": {"processed": [], "skipped": []}}
    supervisor, trace = _startup_with_result(result)
    assert supervisor._run_forever_loop() == "running"
    result["worktree_reconciliation"]["skipped"] = [{"reason": "reconciliation_limit_reached"}]

    assert supervisor.run_once() is result
    assert trace == [("maintenance", False), ("child_dispatch",), ("maintenance", True)]
    assert supervisor._complaint_startup_preflight_pending is False
