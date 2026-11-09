"""Adverse hook and storage outcomes in the public workspace flow.

Synthetic private fixtures only. Each public operation keeps the last graph
token, pending inquiry, and snapshot head, returns a safe error, and does not
claim legal completion. Owned children are reaped. Provider processes and the
network are not started. A missing capability is an asserted outcome.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from applications.complaint_workspace import ComplaintWorkspaceService
from mediator.hook_runtime import PUBLIC_ADVERSE_OUTCOMES


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

PASSPHRASE = "synthetic-mgnd-40-passphrase"
USER_ID = "mgnd40-adverse"
NARRATIVE = "On March 4, 2024 supervisor Alex Rivera ended the assignment. SYNTHETIC-MGND40-NARRATIVE"
SAFE_CODES = {
    "malformed_model_proposal": {"model_cannot_satisfy_requirements", "model_cannot_invoke_tools", "malformed"},
    "late_model_proposal": {"stale_revision"},
    "consent_revocation": {"consent_revoked"},
    "wrong_key": {"authentication_failed"},
    "legal_source_outage": {"storage_unavailable", "acquisition_unavailable", "source_outage"},
    "interrupted_snapshot": {"durability_unproven"},
    "corrupt_replica": {"replica_unavailable"},
}


def _service(root: Path) -> ComplaintWorkspaceService:
    service = ComplaintWorkspaceService(root_dir=root)
    status = service.private_key_status()
    if status.get("protection") in {None, "", "missing"}:
        service.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
    if service.private_key_status().get("unlocked") is not True:
        service.unlock_private_keys(passphrase=PASSPHRASE)
    service.ensure_private_case_key(USER_ID, USER_ID)
    return service


def _seed(service: ComplaintWorkspaceService) -> None:
    service.set_privacy_policy(USER_ID, "local")
    service.run_intake_chat_turn(USER_ID, message=NARRATIVE)
    service.commit_complete_grounded_snapshot(USER_ID)


def _assert_common(result: dict, kind: str) -> None:
    assert result["kind"] == kind
    assert result["code"] in SAFE_CODES[kind]
    assert result["legal_completion"] is False
    assert result["proof"] is False
    assert result["legal_sufficiency"] is False
    assert result["requirements_satisfied"] is False
    assert result["backend_completed"] is False
    assert result["provider_process_started"] is False
    assert result["network_touched"] is False
    assert result["preserved"]["graph_revision"] is True
    assert result["preserved"]["pending_inquiry"] is True
    assert result["preserved"]["head_revision"] is True
    assert result["preserved"]["session_revision"] is True
    assert result["before"]["head_revision"]
    children = result["owned_children"]
    assert children["provider_process_started"] is False
    assert children["network_touched"] is False
    assert children["unrelated_processes_signaled"] is False
    assert children["within_deadline"] is True
    assert children["elapsed_seconds"] <= children["deadline_seconds"]
    if children["status"] == "reaped":
        assert children["pids"]
        assert children["reaped"] == children["pids"]
        for pid in children["pids"]:
            with pytest.raises(ProcessLookupError):
                os.kill(pid, 0)
    else:
        assert children["status"] == "unavailable"
        assert result["owned_child_capability"] == "unavailable"
    if result["resume_possible"] is True:
        assert result["next_action"]
    else:
        assert result["nonrecoverable_boundary"]


def test_public_adverse_cases_are_nonempty():
    assert len(PUBLIC_ADVERSE_OUTCOMES) >= 6
    assert set(SAFE_CODES) == set(PUBLIC_ADVERSE_OUTCOMES)


@pytest.mark.parametrize("kind", PUBLIC_ADVERSE_OUTCOMES)
def test_public_adverse_outcome_preserves_head(tmp_path: Path, kind: str):
    service = _service(tmp_path / "sessions")
    _seed(service)
    repository = tmp_path / "replicas"
    result = service.run_public_adverse_outcome(USER_ID, kind, deadline_seconds=30, repository=repository)
    _assert_common(result, kind)
    if kind == "malformed_model_proposal":
        assert result["provider_invoked"] is False
        assert result["resume_possible"] is True
        assert result["nonrecoverable_boundary"] is None
    elif kind == "late_model_proposal":
        assert result["accepted"] is False
        assert result["acceptor_called"] is False
        assert result["live_model_identity_verified"] is False
        assert result["synthetic_transport"] is True
    elif kind == "consent_revocation":
        assert result["acceptor_called"] is False
        assert result["policy_read"] is True
        policy = service.get_privacy_policy(USER_ID)
        assert policy["policy"]["processing_mode"] == "local_private"
        assert result["live_model_identity_verified"] is False
    elif kind == "wrong_key":
        assert result["nonrecoverable_boundary"] == "wrong_key_cannot_open_head"
        assert result["resume_possible"] is True
        opened = service.load_complete_interview_snapshot(USER_ID)
        assert opened["snapshot"]["revision"] == result["before"]["head_revision"]
    elif kind == "legal_source_outage":
        assert result["stored_as_answer"] is False
        assert result["resume_possible"] is True
    elif kind == "interrupted_snapshot":
        assert result["head_replaced"] is False
        opened = service.load_complete_interview_snapshot(USER_ID)
        assert opened["snapshot"]["revision"] == result["before"]["head_revision"]
        retried = service.commit_complete_grounded_snapshot(USER_ID, expected_revision=str(result["before"]["head_revision"]))
        assert retried["snapshot"]["revision"] != result["before"]["head_revision"]
    elif kind == "corrupt_replica":
        assert result["corrupt_replica_used"] is False
        assert result["primary_preserved"] is True
        assert result["network_durable"] is False
        assert result["nonrecoverable_boundary"] == "corrupt_replica_not_a_restore_source"
        assert result["resume_possible"] is True
        opened = service.load_complete_interview_snapshot(USER_ID)
        assert opened["snapshot"]["revision"] == result["before"]["head_revision"]
