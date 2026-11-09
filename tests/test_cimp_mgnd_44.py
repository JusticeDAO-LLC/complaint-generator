"""Pure completion-contract checks for grounded operations.

The evaluator reads only the contract, the operator guide, and the public
formal plan when a test asks it to. It does not read campaign state, start a
provider, publish artifacts, or mark CIMP-MGND-44 complete.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_RELATIVE = "docs/task_boards/complaint_mediator_grounding_completion_contract.json"
GUIDE_RELATIVE = "docs/task_boards/complaint_mediator_grounding_operator_guide.md"


def _load_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def load_contract() -> dict:
    return _load_json(CONTRACT_RELATIVE)


def load_guide() -> str:
    return (ROOT / GUIDE_RELATIVE).read_text(encoding="utf-8")


def plan_task_index(plan: dict) -> dict[str, dict[str, str]]:
    """Index task id to the goal and subgoal declared on the new plan."""

    index = {}
    for task in plan.get("tasks") or []:
        task_id = task.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            continue
        index[task_id] = {
            "goal_id": task.get("goal_id") or "",
            "subgoal_id": task.get("subgoal_id") or "",
        }
    return index


def _authority(contract: dict) -> dict[str, bool]:
    return {
        "completion_authority": False,
        "provider_authority": bool(contract.get("provider_authority")),
        "state_authority": bool(contract.get("state_authority")),
        "publication_authority": bool(contract.get("publication_authority")),
    }


def _result(contract: dict, phase: str, task_id: str, status: str, **extra) -> dict:
    body = {
        "schema": contract["schema"],
        "phase": phase,
        "task_id": task_id,
        "status": status,
        "completed": False,
        "manufactured_completion": False,
        "live_campaign_closed": False,
        **_authority(contract),
    }
    body.update(extra)
    if body["completed"] or body["completion_authority"] or body["manufactured_completion"]:
        raise RuntimeError("evaluator_manufactured_completion")
    return body


def _present(value) -> bool:
    return value is not None and value != "" and value != {} and value != []


def evaluate_completion_contract(contract: dict, packet: dict | None, plan_index: dict | None = None) -> dict:
    """Classify audit evidence without closing a task.

    Pre-completion always leaves this task self-pending. A post-callback packet
    can show that Root would have the required inputs, and it still leaves
    completed false. Missing evidence is unavailable. Work that cannot proceed
    is blocked. Historical 58-task receipts are not remapped.
    """

    packet = dict(packet or {})
    phase = str(packet.get("phase") or "pre_completion")
    own = contract["task_id"]
    task_id = str(packet.get("task_id") or own)
    plan_index = plan_index or {}

    if phase == "pre_completion":
        return _result(contract, phase, own, "self_pending", reason="validation_remains_self_pending")

    if phase != "post_native_callback":
        return _result(contract, phase, task_id, "unavailable", missing=["phase"])

    if packet.get("blocked") is True or packet.get("status") == "blocked":
        reasons = list(packet.get("reasons") or ["blocked"])
        return _result(contract, phase, task_id, "blocked", reasons=reasons)

    historical = contract["historical_intake"]
    if packet.get("historical_program") == historical["program_id"] or packet.get("remap_historical_receipt") is True:
        return _result(
            contract,
            phase,
            task_id,
            "rejected_historical_remap",
            reasons=["old_58_task_receipt_is_historical_scoped_evidence"],
        )

    if packet.get("fresh_old_release_qualification") is True or packet.get("claims_old_release_qualification") is True:
        return _result(contract, phase, task_id, "rejected_old_release_qualification")

    rules = contract["audit_phases"]["post_native_callback"]
    missing = [key for key in rules["requires"] if not _present(packet.get(key))]
    if missing:
        return _result(contract, phase, task_id, rules["missing_evidence_status"], missing=missing)

    declared = plan_index.get(task_id)
    if declared is None:
        return _result(contract, phase, task_id, "unavailable", missing=["new_plan_task"])
    if packet.get("goal_id") != declared["goal_id"] or packet.get("subgoal_id") != declared["subgoal_id"]:
        return _result(contract, phase, task_id, "rejected_goal_remap")

    cid = packet.get("canonical_task_cid")
    if not isinstance(cid, str) or len(cid) < 8 or cid.startswith("historical-58"):
        return _result(contract, phase, task_id, "unavailable", missing=["canonical_task_cid"])

    acceptance = packet["current_source_public_acceptance"]
    public_rules = contract["current_source_public_acceptance"]
    public_missing = [field for field in public_rules["required_fields"] if field not in acceptance]
    if public_missing:
        return _result(contract, phase, task_id, "unavailable", missing=public_missing)
    if acceptance.get("required_skips") != public_rules["required_skips_must_equal"]:
        return _result(contract, phase, task_id, "unavailable", missing=["required_skips"])
    if not isinstance(acceptance.get("case_count"), int) or acceptance["case_count"] < public_rules["case_count_min"]:
        return _result(contract, phase, task_id, "unavailable", missing=["case_count"])
    overclaims = [
        field
        for field in ("legal_sufficiency", "live_provider_qualified", "remote_durability_qualified")
        if acceptance.get(field) is not False
    ]
    if overclaims:
        return _result(contract, phase, task_id, "rejected_overclaim", overclaims=overclaims)

    callback = packet.get("native_callback") or {}
    if callback.get("issued_by_this_task") is True or callback.get("synthetic") is True:
        status = "self_pending" if task_id == own else "rejected_synthetic_callback"
        return _result(contract, phase, task_id, status, reason="callback_not_from_root")
    if callback.get("issued_outside_task") is not True or callback.get("owner") != rules["root_callback_owner"]:
        return _result(contract, phase, task_id, "unavailable", missing=["root_native_callback"])

    return _result(
        contract,
        phase,
        task_id,
        "ready_for_root_audit",
        audit_inputs_complete=True,
        reason="root_audits_outside_this_task",
    )


def classify_storage_claim(contract: dict, claim: dict) -> dict:
    """Keep encrypted local storage distinct from remote durability states."""

    kind = claim.get("kind")
    states = set(contract["durability_states"])
    if kind not in states:
        return {"status": "unavailable", "kind": kind, "durable_remote": False, "completed": False}
    implied = set(claim.get("implies") or [])
    allowed = set(contract["durability_implications"].get(kind) or [])
    extra = sorted(implied - allowed)
    if extra:
        return {
            "status": "rejected_durability_conflation",
            "kind": kind,
            "rejected_implications": extra,
            "durable_remote": False,
            "completed": False,
        }
    return {
        "status": "distinguished",
        "kind": kind,
        "durable_remote": kind == "verified_replica",
        "completed": False,
    }


def _public_acceptance(**overrides) -> dict:
    acceptance = {
        "source_revision": "synthetic-source-revision",
        "public_module": "tests/test_cimp_mgnd_43.py",
        "case_count": 2,
        "required_skips": 0,
        "legal_sufficiency": False,
        "live_provider_qualified": False,
        "remote_durability_qualified": False,
    }
    acceptance.update(overrides)
    return acceptance


def _root_packet(contract: dict, plan_index: dict, task_id: str = "CIMP-MGND-43") -> dict:
    declared = plan_index[task_id]
    return {
        "phase": "post_native_callback",
        "task_id": task_id,
        "canonical_task_cid": "bafysyntheticcid44",
        "goal_id": declared["goal_id"],
        "subgoal_id": declared["subgoal_id"],
        "current_source_public_acceptance": _public_acceptance(),
        "native_callback": {"issued_outside_task": True, "owner": "root", "synthetic": False, "issued_by_this_task": False},
    }


def test_operator_guide_documents_the_public_surface() -> None:
    contract = load_contract()
    guide = load_guide()
    phrases = contract["guide_required_phrases"]
    assert phrases
    missing = [phrase for phrase in phrases if phrase not in guide]
    assert missing == []
    surface = contract["operator_surface"]
    assert surface["canonical_command"] in guide
    for flag in surface["consent_flags"]:
        assert flag in guide
    for control in surface["session_controls"]:
        assert control in guide
    for state in contract["durability_states"]:
        assert state in guide
    assert "not completion authority" in guide
    assert "does not complete `CIMP-MGND-44`" in guide


def test_contract_has_no_authority_and_names_both_audits() -> None:
    contract = load_contract()
    assert contract["schema"] == "complaint-mediator-grounding-completion-contract@1"
    assert contract["task_id"] == "CIMP-MGND-44"
    assert contract["goal_id"] == "goal.mgnd.operations"
    assert contract["subgoal_id"] == "subgoal.mgnd.operations.acceptance"
    assert contract["completion_authority"] is False
    assert contract["provider_authority"] is False
    assert contract["state_authority"] is False
    assert contract["publication_authority"] is False
    assert contract["manufactures_own_completion"] is False
    assert contract["recursive_campaign_read"] is False
    assert contract["self_task"]["status"] == "self_pending"
    assert contract["self_task"]["validation_closes_task"] is False
    assert contract["audit_phases"]["pre_completion"]["own_task_remains"] == "self_pending"
    assert contract["audit_phases"]["post_native_callback"]["does_not_infer_from_pre_completion"] is True
    historical = contract["historical_intake"]
    assert historical["task_count"] == 58
    assert historical["remap_to_new_task_ids"] is False
    assert historical["fresh_old_release_qualification"] is False
    assert historical["old_release_module_closure_count"] == 83
    assert contract["new_plan"]["task_id_prefix"] == "CIMP-MGND-"


def test_pre_completion_stays_self_pending_when_validation_passes() -> None:
    contract = load_contract()
    cases = [
        {},
        {"phase": "pre_completion", "validation_passed": True, "task_id": "CIMP-MGND-44"},
        {"phase": "pre_completion", "native_callback": {"accepted": True, "owner": "root"}},
    ]
    assert cases
    for packet in cases:
        outcome = evaluate_completion_contract(contract, packet, {})
        assert outcome["status"] == "self_pending"
        assert outcome["task_id"] == "CIMP-MGND-44"
        assert outcome["completed"] is False
        assert outcome["completion_authority"] is False
        assert outcome["live_campaign_closed"] is False


def test_post_callback_shape_is_necessary_and_not_sufficient_to_complete() -> None:
    contract = load_contract()
    plan = _load_json(contract["new_plan"]["plan_relative"])
    index = plan_task_index(plan)
    assert "CIMP-MGND-44" in index
    assert index["CIMP-MGND-44"]["goal_id"] == contract["goal_id"]
    assert index["CIMP-MGND-44"]["subgoal_id"] == contract["subgoal_id"]
    assert len(index) != contract["historical_intake"]["task_count"]
    assert all(task_id.startswith("CIMP-MGND-") for task_id in index)

    ready = evaluate_completion_contract(contract, _root_packet(contract, index), index)
    assert ready["status"] == "ready_for_root_audit"
    assert ready["audit_inputs_complete"] is True
    assert ready["completed"] is False
    assert ready["completion_authority"] is False
    assert ready["provider_authority"] is False
    assert ready["state_authority"] is False
    assert ready["publication_authority"] is False

    own = _root_packet(contract, index, "CIMP-MGND-44")
    own["native_callback"] = {"issued_by_this_task": True, "synthetic": True, "owner": "root"}
    manufactured = evaluate_completion_contract(contract, own, index)
    assert manufactured["status"] == "self_pending"
    assert manufactured["completed"] is False

    remapped = _root_packet(contract, index)
    remapped["goal_id"] = "goal.mgnd.baseline"
    assert evaluate_completion_contract(contract, remapped, index)["status"] == "rejected_goal_remap"

    unknown = _root_packet(contract, index)
    unknown["task_id"] = "CIMP-REL-03"
    assert evaluate_completion_contract(contract, unknown, index)["status"] == "unavailable"


def test_unavailable_and_blocked_work_stay_explicit() -> None:
    contract = load_contract()
    index = {"CIMP-MGND-43": {"goal_id": "goal.mgnd.operations", "subgoal_id": "subgoal.mgnd.operations.acceptance"}}
    missing_cid = _root_packet(contract, index)
    missing_cid["canonical_task_cid"] = ""
    missing = evaluate_completion_contract(contract, missing_cid, index)
    assert missing["status"] == "unavailable"
    assert "canonical_task_cid" in missing["missing"]
    assert missing["completed"] is False

    blocked = evaluate_completion_contract(
        contract,
        {"phase": "post_native_callback", "task_id": "CIMP-MGND-43", "blocked": True, "reasons": ["source_unavailable"]},
        index,
    )
    assert blocked["status"] == "blocked"
    assert blocked["reasons"] == ["source_unavailable"]
    assert blocked["completed"] is False

    overclaim = _root_packet(contract, index)
    overclaim["current_source_public_acceptance"] = _public_acceptance(legal_sufficiency=True)
    assert evaluate_completion_contract(contract, overclaim, index)["status"] == "rejected_overclaim"

    skips = _root_packet(contract, index)
    skips["current_source_public_acceptance"] = _public_acceptance(required_skips=1)
    assert evaluate_completion_contract(contract, skips, index)["status"] == "unavailable"


def test_historical_58_receipts_are_not_remapped_or_requalified() -> None:
    contract = load_contract()
    index = plan_task_index(_load_json(contract["new_plan"]["plan_relative"]))
    historical = _root_packet(contract, index, "CIMP-MGND-01")
    historical["historical_program"] = "complaint-intake-58"
    historical["canonical_task_cid"] = "historical-58-receipt"
    outcome = evaluate_completion_contract(contract, historical, index)
    assert outcome["status"] == "rejected_historical_remap"
    assert outcome["completed"] is False

    requalified = _root_packet(contract, index)
    requalified["fresh_old_release_qualification"] = True
    requalified["old_module_count"] = 83
    assert evaluate_completion_contract(contract, requalified, index)["status"] == "rejected_old_release_qualification"

    assert contract["historical_intake"]["task_count"] == 58
    assert "CIMP-INTAKE" not in index
    assert set(index) != set()


def test_storage_claims_do_not_promote_local_ciphertext_to_a_replica() -> None:
    contract = load_contract()
    cases = [
        {"kind": "local_encrypted_commit", "implies": []},
        {"kind": "ciphertext_readback", "implies": ["local_encrypted_commit"]},
        {"kind": "queued_replication", "implies": []},
        {"kind": "pinning", "implies": []},
        {"kind": "verified_replica", "implies": []},
    ]
    assert cases
    for claim in cases:
        outcome = classify_storage_claim(contract, claim)
        assert outcome["status"] == "distinguished"
        assert outcome["completed"] is False
        assert outcome["durable_remote"] is (claim["kind"] == "verified_replica")

    conflated = classify_storage_claim(
        contract,
        {"kind": "local_encrypted_commit", "implies": ["verified_replica"]},
    )
    assert conflated["status"] == "rejected_durability_conflation"
    assert conflated["durable_remote"] is False
    assert classify_storage_claim(contract, {"kind": "unknown_store"})["status"] == "unavailable"


def test_evaluator_does_not_read_private_campaign_state(monkeypatch) -> None:
    contract = load_contract()

    def refuse_read(*args, **kwargs):
        raise AssertionError("private_or_source_read_inside_evaluator")

    monkeypatch.setattr("builtins.open", refuse_read)
    monkeypatch.setattr(Path, "open", refuse_read)
    monkeypatch.setattr(Path, "read_text", refuse_read)
    monkeypatch.setattr(Path, "read_bytes", refuse_read)
    outcome = evaluate_completion_contract(
        contract,
        {"phase": "pre_completion", "validation_passed": True},
        {"CIMP-MGND-44": {"goal_id": contract["goal_id"], "subgoal_id": contract["subgoal_id"]}},
    )
    assert outcome["status"] == "self_pending"
    assert outcome["completed"] is False
    assert outcome["state_authority"] is False
