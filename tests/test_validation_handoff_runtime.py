"""Synthetic controller regression; ownership mocks are explicitly fixtures.

The live incident separately supplies the genuine Native timeout→successful
executor→premature fencing evidence. These tests do not claim live ownership.
"""
from copy import deepcopy
from datetime import datetime, timezone
import time

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner
from tests.test_improvement_validation_activity import ownership
from tests.test_reconciliation_validation_activity import ordinary

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def test_returned_canonical_executor_has_only_a_short_current_owner_handoff(ordinary):
    c = ordinary
    c.body["active_task_started_at"] = datetime.fromtimestamp(time.time() - 950, timezone.utc).isoformat()
    c.body["implementation_attempts"] = {c.task["id"]: 1}
    before = deepcopy(c.body)
    calls = []
    result = {"explicit_fake_executor_result": True}

    def executor(**kwargs):
        calls.append(kwargs["timeout_seconds"])
        return result

    c.daemon.PortalImplementationDaemon._validation_command_runner = staticmethod(executor)
    assert runner._call_validation_with_activity(executor=executor, spec=None,
        workspace_path=c.workspace, timeout_seconds=60, environment={}, task=c.task, context=c.context) is result
    assert len(calls) == 1 and 0 < calls[0] <= 60
    current = runner.status(c.target, c.target / "spec.json", c.campaign)
    assert current["status"] == "active" and current["healthy"] is True
    assert current["validation_activity_evidence"]["type"] == "canonical_native_validation_finalizing"
    assert current["validation_activity_evidence"]["completion_authority"] is False
    assert current["provider_progress_verified"] is False
    assert c.body == before
    replacement = {**c.claim, "lease_id": "explicit-replacement-claim"}
    c.claim_path.write_text(__import__("json").dumps(replacement))
    refused = runner.status(c.target, c.target / "spec.json", c.campaign)
    assert refused["status"] == "stalled" and refused["healthy"] is False
    assert c.body == before and len(calls) == 1
