"""Instructional examples plus real read-only completion-verifier boundaries.

Legacy classifiers below explain policy from caller-provided labels only.
They authenticate no actor, startup, receipt, callback, or campaign completion.
Actual negative observations use the production verifier against private
synthetic missing/mismatched evidence; no live campaign is read or modified.
"""

from __future__ import annotations

import json
from pathlib import Path
from functools import wraps

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_RELATIVE = "docs/task_boards/complaint_gui_collaboration_completion_contract.json"
GUIDE_RELATIVE = "docs/task_boards/complaint_gui_collaboration_operator_guide.md"


def _load_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def load_contract() -> dict:
    return _load_json(CONTRACT_RELATIVE)


def load_guide() -> str:
    return (ROOT / GUIDE_RELATIVE).read_text(encoding="utf-8")


def plan_task_index(plan: dict) -> dict[str, dict[str, str]]:
    """Index task id to the goal and subgoal declared on the GUI plan."""

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


def _instructional(function):
    @wraps(function)
    def explain(*args, **kwargs):
        return {**function(*args, **kwargs), 'instructional_only':True,
                'verified':False, 'authorization_authority':False, 'startup_authority':False}
    return explain


def _authority(contract: dict) -> dict[str, bool]:
    return {name:False for name in ('completion_authority','provider_authority',
                                    'state_authority','publication_authority')}


def _result(contract: dict, phase: str, task_id: str, status: str, **extra) -> dict:
    body = {
        "schema": contract["schema"],
        "phase": phase,
        "task_id": task_id,
        "status": status,
        "completed": False,
        "manufactured_completion": False,
        "live_campaign_closed": False,
        "program_completed": False,
        **_authority(contract),
    }
    body.update(extra)
    if body["completed"] or body["completion_authority"] or body["manufactured_completion"] or body["program_completed"]:
        raise RuntimeError("evaluator_manufactured_completion")
    return body


def _present(value) -> bool:
    return value is not None and value != "" and value != {} and value != []


def _historical_program(contract: dict, packet: dict) -> dict | None:
    named = packet.get("historical_program")
    for program in contract["historical_programs"]:
        if named == program["program_id"]:
            return program
        task_id = str(packet.get("task_id") or "")
        if task_id.startswith(program["task_id_prefix"]):
            return program
    if packet.get("claims_old_58_completion") is True:
        return contract["historical_programs"][0]
    if packet.get("claims_old_44_completion") is True:
        return contract["historical_programs"][1]
    return None


@_instructional
def evaluate_completion_contract(contract: dict, packet: dict | None, plan_index: dict | None = None) -> dict:
    """Explain legacy caller labels; never authenticate their claimed evidence.

    Field completeness is an instructional example only. The production
    read-only verifier, invoked separately after Native callbacks, reads the
    actual sources. This helper cannot establish readiness or completion.
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

    evidence_kind = packet.get("evidence_kind")
    if packet.get("packet_shape_only") is True or evidence_kind == "packet_shape":
        return _result(contract, phase, task_id, "rejected_packet_shape", reason="packet_shape_does_not_complete")
    if packet.get("ingestion_only") is True or evidence_kind == "ingestion":
        return _result(contract, phase, task_id, "rejected_ingestion", reason="ingestion_does_not_complete")

    historical = _historical_program(contract, packet)
    if historical is not None or packet.get("remap_historical_receipt") is True:
        program_id = (historical or {}).get("program_id", "historical")
        return _result(
            contract,
            phase,
            task_id,
            "rejected_historical_program",
            historical_program=program_id,
            reason="old_program_completion_does_not_complete_gui",
        )

    rules = contract["audit_phases"]["post_native_callback"]
    missing = [key for key in rules["requires"] if not _present(packet.get(key))]
    if missing:
        return _result(contract, phase, task_id, rules["missing_evidence_status"], missing=missing)

    declared = plan_index.get(task_id)
    if declared is None or not task_id.startswith(contract["new_plan"]["task_id_prefix"]):
        return _result(contract, phase, task_id, "unavailable", missing=["current_canonical_task"])
    if packet.get("goal_id") != declared["goal_id"] or packet.get("subgoal_id") != declared["subgoal_id"]:
        return _result(contract, phase, task_id, "rejected_goal_remap")

    identity = packet.get("current_canonical_identity") or {}
    if identity.get("namespace") != contract["new_plan"]["namespace"]:
        return _result(contract, phase, task_id, "rejected_identity", reason="namespace")
    if identity.get("source_revision") != contract["baseline_commit"]:
        return _result(contract, phase, task_id, "rejected_identity", reason="source_revision")
    if identity.get("task_id") != task_id:
        return _result(contract, phase, task_id, "rejected_identity", reason="task_id")

    cid = packet.get("canonical_task_cid")
    if not isinstance(cid, str) or len(cid) < 8 or cid.startswith("historical-"):
        return _result(contract, phase, task_id, "unavailable", missing=["canonical_task_cid"])
    if identity.get("canonical_task_cid") != cid:
        return _result(contract, phase, task_id, "rejected_identity", reason="canonical_task_cid")

    member = packet.get("native_member_receipt") or {}
    member_rules = contract["member_receipt"]
    if member.get("accepted") is not member_rules["accepted_must_equal"] or member.get("owner") != member_rules["owner"]:
        return _result(contract, phase, task_id, "rejected_member_receipt")
    if member.get("task_id") != task_id or member.get("canonical_task_cid") != cid:
        return _result(contract, phase, task_id, "rejected_member_receipt")

    queue = packet.get("settled_merge_queue") or {}
    queue_rules = contract["merge_queue"]
    if queue.get("pending_count") != queue_rules["pending_count_must_equal"]:
        return _result(contract, phase, task_id, "blocked", reasons=["merge_queue_unsettled"])
    if queue.get("settled") is not True or queue.get("task_id") != task_id:
        return _result(contract, phase, task_id, "blocked", reasons=["merge_queue_unsettled"])

    callback = packet.get("native_callback") or {}
    if callback.get("issued_by_this_task") is True or callback.get("synthetic") is True:
        status = "self_pending" if task_id == own else "rejected_synthetic_callback"
        return _result(contract, phase, task_id, status, reason="callback_not_from_native")
    if callback.get("issued_outside_task") is not True or callback.get("owner") != rules["native_callback_owner"]:
        return _result(contract, phase, task_id, "unavailable", missing=["native_callback"])
    if callback.get("task_id") != task_id or callback.get("canonical_task_cid") != cid:
        return _result(contract, phase, task_id, "rejected_callback_identity")

    return _result(
        contract,
        phase,
        task_id,
        "unverified_instructional_packet",
        audit_inputs_complete=False,
        packet_fields_present=True,
        reason="caller_fields_do_not_establish_native_evidence",
    )


@_instructional
def classify_authorization(contract: dict, request: dict) -> dict:
    """Apply actor, role, and encrypted-owner separation."""

    rules = contract["authorization"]
    actor = request.get("actor")
    actors = rules["actors"]
    if actor not in actors:
        return {"status": "denied", "reason": "unknown_actor", "case_content": False, "completed": False}
    if request.get("actor_id") and request.get("actor_id") == request.get("encrypted_owner_binding") and request.get("impersonates_owner") is True:
        return {"status": "denied", "reason": "actor_is_not_encrypted_owner", "case_content": False, "completed": False}
    if actor == "assigned_lawyer":
        grant_ok = request.get("membership_accepted") is True and request.get("key_grant_accepted") is True
        if request.get("role_alone") is True or not grant_ok:
            return {"status": "denied", "reason": "lawyer_role_alone", "case_content": False, "completed": False}
    if actor == "operational_admin" and request.get("requests_case_content") is True:
        return {"status": "denied", "reason": "admin_ambient_plaintext", "case_content": False, "completed": False}
    if actor == "unassigned":
        return {"status": "denied", "reason": "unassigned", "case_content": False, "completed": False}
    allowed = actor == "case_owner" or actor == "assigned_lawyer" or (
        actor == "operational_admin" and request.get("requests_case_content") is not True
    )
    return {
        "status": "instructional_allow" if allowed else "denied",
        "actor": actor,
        "case_content": False,
        "example_case_content": actor in {"case_owner", "assigned_lawyer"},
        "completed": False,
    }


@_instructional
def classify_grant_recovery(contract: dict, claim: dict) -> dict:
    """Missing keys do not mint replacements. Revocation is not erasure."""

    rules = contract["key_grant_recovery"]
    if claim.get("missing_key") is True and claim.get("mint_replacement") is True:
        return {"status": "rejected_key_mint", "access": "denied", "completed": False}
    if claim.get("missing_key") is True:
        return {"status": "unavailable", "reason": "missing_key", "access": "denied", "completed": False}
    if claim.get("expired") is True or claim.get("revoked") is True:
        if claim.get("erases_downloaded_content") is True:
            return {"status": "rejected_erasure_claim", "access": "denied", "completed": False}
        if claim.get("future_access") is not False:
            return {"status": "rejected_revocation", "access": "denied", "completed": False}
        return {"status": "revoked", "access": "denied", "downloaded_content_erased": False, "completed": False}
    required = rules["grant_fields"]
    missing = [field for field in required if not _present(claim.get(field))]
    if missing:
        return {"status": "unavailable", "missing": missing, "access": "denied", "completed": False}
    return {"status": "recoverable", "access": "grant_bound", "completed": False}


@_instructional
def classify_consent(contract: dict, choice: dict) -> dict:
    """Development authorization and encryption unlock are not egress consent."""

    rules = contract["consent"]
    if choice.get("development_authorization") is True and choice.get("treats_as_egress") is True:
        return {"status": "rejected_development_authorization", "egress": False, "completed": False}
    if choice.get("encryption_unlock") is True and choice.get("treats_as_consent") is True:
        return {"status": "rejected_unlock_as_consent", "egress": False, "completed": False}
    if choice.get("flag_omitted") is True and choice.get("creates_consent") is True:
        return {"status": "rejected_omitted_flag", "egress": False, "completed": False}
    mode = choice.get("mode")
    if mode not in rules["modes"]:
        return {"status": "unavailable", "egress": False, "completed": False}
    late = choice.get("late_result") is True
    if late and choice.get("rechecked") is not True:
        return {"status": "rejected_late_result", "egress": False, "completed": False}
    return {
        "status": "recorded",
        "mode": mode,
        "egress": mode == "grok",
        "completed": False,
    }


@_instructional
def classify_message(contract: dict, message: dict) -> dict:
    """A conversation stays a conversation until an explicit accepted action."""

    rules = contract["private_messaging"]
    transport = message.get("transport")
    if transport in rules["unqualified_transports"] or message.get("claims_streaming") is True:
        return {"status": "rejected_unqualified_transport", "state": "denied", "completed": False}
    if message.get("channel") in rules["outside_campaign"]:
        return {"status": "outside_campaign", "state": "not_sent", "completed": False}
    action = message.get("accepted_action")
    if action is None:
        return {"status": "conversation", "state": rules["default_state"], "evidence": False, "completed": False}
    if action not in rules["accepted_actions"]:
        return {"status": "rejected_adoption", "state": "conversation", "evidence": False, "completed": False}
    if message.get("authorized") is not True or message.get("actor_id") in (None, ""):
        return {"status": "denied", "state": "conversation", "evidence": False, "completed": False}
    return {"status": "adopted", "state": action, "evidence": action == "evidence", "completed": False}


@_instructional
def classify_graph_claim(contract: dict, claim: dict) -> dict:
    """Snippets, model text, and unexecuted proofs are not governing law."""

    rules = contract["graph_provenance"]
    kind = claim.get("kind")
    if kind in rules["not_governing_law"] or claim.get("governing_law") is True:
        return {"status": "rejected_not_governing_law", "legal_sufficiency": False, "completed": False}
    if claim.get("factual_answer_rewrites_rule") is True:
        return {"status": "rejected_rule_rewrite", "legal_sufficiency": False, "completed": False}
    if claim.get("legal_sufficiency") is True:
        return {"status": "rejected_legal_sufficiency", "legal_sufficiency": False, "completed": False}
    if kind == "admitted_authority":
        required = ("source_span", "jurisdiction", "effective_date", "version")
        missing = [field for field in required if not _present(claim.get(field))]
        if missing:
            return {"status": "unavailable", "missing": missing, "legal_sufficiency": False, "completed": False}
        return {"status": "admitted_candidate", "governing_law": False, "legal_sufficiency": False, "completed": False}
    if kind == "factual_assertion":
        if not _present(claim.get("source_id")):
            return {"status": "unavailable", "missing": ["source_id"], "legal_sufficiency": False, "completed": False}
        return {"status": "recorded_assertion", "governing_law": False, "legal_sufficiency": False, "completed": False}
    return {"status": "unavailable", "legal_sufficiency": False, "completed": False}


@_instructional
def classify_stop(contract: dict, event: dict) -> dict:
    """Finite stops and user waits are not legal sufficiency or stalled workers."""

    rules = contract["finite_stopping"]
    if event.get("awaiting_user") is True:
        stalled = event.get("classify_as_stalled_worker") is True
        return {
            "status": "rejected_stalled_classification" if stalled else "awaiting_user",
            "stalled_worker": False,
            "legal_sufficiency": False,
            "completed": False,
        }
    reason = event.get("reason")
    if reason not in rules["stop_reasons"] and reason != "saturation":
        return {"status": "unavailable", "legal_sufficiency": False, "completed": False}
    if event.get("legal_sufficiency") is True or (reason == "saturation" and event.get("claims_legal_sufficiency") is True):
        return {"status": "rejected_legal_sufficiency", "legal_sufficiency": False, "completed": False}
    attempts = event.get("attempts")
    if isinstance(attempts, int) and attempts > rules["max_task_attempts"]:
        return {"status": "rejected_attempt_cap", "legal_sufficiency": False, "completed": False}
    return {
        "status": "stopped",
        "reason": reason,
        "legal_sufficiency": False,
        "stalled_worker": False,
        "completed": False,
    }


@_instructional
def classify_watchdog(contract: dict, observation: dict) -> dict:
    """A doctor report or PID alone is not authenticated startup."""

    rules = contract["watchdog"]
    if observation.get("doctor_only") is True or observation.get("pid_only") is True:
        return {"status": "rejected_unauthenticated_watchdog", "startup": False, "completed": False}
    if observation.get("user_input_wait") is True and observation.get("classify_as_stalled_worker") is True:
        return {"status": "rejected_user_wait", "startup": False, "stalled_worker": False, "completed": False}
    if observation.get("provider") != rules["provider"] or observation.get("model") != rules["model"]:
        return {"status": "unavailable", "startup": False, "completed": False}
    if observation.get("allow_fallback") is not rules["allow_fallback"]:
        return {"status": "rejected_fallback", "startup": False, "completed": False}
    missing = [name for name in rules["required_observations"] if observation.get(name) is not True]
    if missing:
        return {"status": "unavailable", "missing": missing, "startup": False, "completed": False}
    if observation.get("preserves_holds") is not True:
        return {"status": "rejected_hold", "startup": False, "completed": False}
    if observation.get("authenticated") is not True:
        return {"status": "rejected_unauthenticated_watchdog", "startup": False, "completed": False}
    return {"status": "unverified_instructional_observation", "startup": False, "completed": False, "program_completed": False}


def _identity(contract: dict, task_id: str, cid: str) -> dict:
    return {
        "namespace": contract["new_plan"]["namespace"],
        "source_revision": contract["baseline_commit"],
        "task_id": task_id,
        "canonical_task_cid": cid,
    }


def _root_packet(contract: dict, plan_index: dict, task_id: str = "CIMP-GUI-59") -> dict:
    """Legacy instructional packet; these labels are not Native evidence."""
    declared = plan_index[task_id]
    cid = "bafysyntheticgui60cid"
    return {
        "phase": "post_native_callback",
        "task_id": task_id,
        "canonical_task_cid": cid,
        "goal_id": declared["goal_id"],
        "subgoal_id": declared["subgoal_id"],
        "current_canonical_identity": _identity(contract, task_id, cid),
        "native_member_receipt": {
            "accepted": True,
            "owner": contract["member_receipt"]["owner"],
            "task_id": task_id,
            "canonical_task_cid": cid,
        },
        "native_callback": {
            "issued_outside_task": True,
            "owner": contract["audit_phases"]["post_native_callback"]["native_callback_owner"],
            "synthetic": False,
            "issued_by_this_task": False,
            "task_id": task_id,
            "canonical_task_cid": cid,
        },
        "settled_merge_queue": {"settled": True, "pending_count": 0, "task_id": task_id},
    }


def test_operator_guide_documents_operations() -> None:
    contract = load_contract()
    guide = load_guide()
    phrases = contract["guide_required_phrases"]
    assert phrases
    missing = [phrase for phrase in phrases if phrase not in guide]
    assert missing == []
    assert "not completion authority" in guide
    assert "does not complete `CIMP-GUI-60`" in guide
    assert contract["baseline_commit"] in guide
    for mode in contract["consent"]["modes"]:
        assert mode in guide
    for reason in ("pause", "cancellation", "unavailable capability"):
        assert reason in guide


def test_contract_denies_authority_and_names_current_and_historical_programs() -> None:
    contract = load_contract()
    assert contract["schema"] == "complaint-gui-collaboration-completion-contract@1"
    assert contract["task_id"] == "CIMP-GUI-60"
    assert contract["goal_id"] == "goal.gui.operations"
    assert contract["subgoal_id"] == "subgoal.gui.operations.closure"
    assert contract["completion_authority"] is False
    assert contract["provider_authority"] is False
    assert contract["state_authority"] is False
    assert contract["publication_authority"] is False
    assert contract["manufactures_own_completion"] is False
    assert contract["recursive_campaign_read"] is False
    assert contract["self_task"]["status"] == "self_pending"
    assert contract["self_task"]["validation_closes_task"] is False
    assert contract["new_plan"]["namespace"] == "complaint-gui-collaboration"
    assert contract["new_plan"]["task_count"] == 60
    assert contract["historical_policy"]["old58_completion_completes_gui"] is False
    assert contract["historical_policy"]["old44_completion_completes_gui"] is False
    assert contract["historical_policy"]["remap_to_new_task_ids"] is False
    assert {item["task_count"] for item in contract["historical_programs"]} == {58, 44}
    assert contract["authorization"]["lawyer_role_alone_grants_case_access"] is False
    assert contract["key_grant_recovery"]["missing_key_mints_replacement"] is False
    assert contract["watchdog"]["doctor_or_pid_alone_establishes_startup"] is False


def test_pre_completion_stays_self_pending_when_validation_passes() -> None:
    contract = load_contract()
    cases = [
        {},
        {"phase": "pre_completion", "validation_passed": True, "task_id": "CIMP-GUI-60"},
        {"phase": "pre_completion", "native_callback": {"accepted": True, "owner": "root"}},
        {"phase": "pre_completion", "settled_merge_queue": {"settled": True, "pending_count": 0}},
    ]
    assert cases
    for packet in cases:
        outcome = evaluate_completion_contract(contract, packet, {})
        assert outcome["status"] == "self_pending"
        assert outcome["task_id"] == "CIMP-GUI-60"
        assert outcome["completed"] is False
        assert outcome["program_completed"] is False
        assert outcome["completion_authority"] is False
        assert outcome["live_campaign_closed"] is False


def test_native_receipts_identity_and_settled_queue_are_necessary_and_not_sufficient() -> None:
    contract = load_contract()
    plan = _load_json(contract["new_plan"]["plan_relative"])
    index = plan_task_index(plan)
    assert len(index) == contract["new_plan"]["task_count"]
    assert index["CIMP-GUI-60"]["goal_id"] == contract["goal_id"]
    assert index["CIMP-GUI-60"]["subgoal_id"] == contract["subgoal_id"]
    assert all(task_id.startswith("CIMP-GUI-") for task_id in index)

    ready = evaluate_completion_contract(contract, _root_packet(contract, index), index)
    assert ready["status"] == "unverified_instructional_packet"
    assert ready["audit_inputs_complete"] is False
    assert ready["instructional_only"] is True and ready["verified"] is False
    assert ready["completed"] is False
    assert ready["program_completed"] is False
    assert ready["completion_authority"] is False
    assert ready["state_authority"] is False

    own = _root_packet(contract, index, "CIMP-GUI-60")
    own["native_callback"] = {
        "issued_by_this_task": True,
        "synthetic": True,
        "owner": "root",
        "task_id": "CIMP-GUI-60",
        "canonical_task_cid": own["canonical_task_cid"],
    }
    manufactured = evaluate_completion_contract(contract, own, index)
    assert manufactured["status"] == "self_pending"
    assert manufactured["completed"] is False

    remapped = _root_packet(contract, index)
    remapped["goal_id"] = "goal.gui.baseline"
    assert evaluate_completion_contract(contract, remapped, index)["status"] == "rejected_goal_remap"

    unknown = _root_packet(contract, index)
    unknown["task_id"] = "CIMP-REL-03"
    unknown["current_canonical_identity"]["task_id"] = "CIMP-REL-03"
    assert evaluate_completion_contract(contract, unknown, index)["status"] == "unavailable"


def test_packet_shape_ingestion_and_old_programs_do_not_complete() -> None:
    contract = load_contract()
    index = plan_task_index(_load_json(contract["new_plan"]["plan_relative"]))
    shaped = _root_packet(contract, index)
    shaped["packet_shape_only"] = True
    assert evaluate_completion_contract(contract, shaped, index)["status"] == "rejected_packet_shape"

    ingested = _root_packet(contract, index)
    ingested["evidence_kind"] = "ingestion"
    assert evaluate_completion_contract(contract, ingested, index)["status"] == "rejected_ingestion"

    old58 = _root_packet(contract, index)
    old58["historical_program"] = "complaint-intake-58"
    old58["claims_old_58_completion"] = True
    outcome58 = evaluate_completion_contract(contract, old58, index)
    assert outcome58["status"] == "rejected_historical_program"
    assert outcome58["completed"] is False

    old44 = _root_packet(contract, index, "CIMP-GUI-01")
    old44["task_id"] = "CIMP-MGND-44"
    old44["claims_old_44_completion"] = True
    outcome44 = evaluate_completion_contract(contract, old44, index)
    assert outcome44["status"] == "rejected_historical_program"
    assert outcome44["program_completed"] is False

    intake_id = dict(_root_packet(contract, index))
    intake_id["task_id"] = "CIMP-INTAKE-58"
    assert evaluate_completion_contract(contract, intake_id, index)["status"] == "rejected_historical_program"


def test_missing_receipts_and_unsettled_queue_stay_explicit() -> None:
    contract = load_contract()
    index = plan_task_index(_load_json(contract["new_plan"]["plan_relative"]))
    missing_member = _root_packet(contract, index)
    missing_member["native_member_receipt"] = {}
    missing = evaluate_completion_contract(contract, missing_member, index)
    assert missing["status"] == "unavailable"
    assert "native_member_receipt" in missing["missing"]
    assert missing["completed"] is False

    mismatched = _root_packet(contract, index)
    mismatched["native_member_receipt"] = {
        "accepted": True,
        "owner": "root",
        "task_id": "CIMP-GUI-01",
        "canonical_task_cid": mismatched["canonical_task_cid"],
    }
    assert evaluate_completion_contract(contract, mismatched, index)["status"] == "rejected_member_receipt"

    unsettled = _root_packet(contract, index)
    unsettled["settled_merge_queue"] = {"settled": False, "pending_count": 2, "task_id": "CIMP-GUI-59"}
    blocked = evaluate_completion_contract(contract, unsettled, index)
    assert blocked["status"] == "blocked"
    assert blocked["reasons"] == ["merge_queue_unsettled"]
    assert blocked["completed"] is False

    stale_identity = _root_packet(contract, index)
    stale_identity["current_canonical_identity"]["source_revision"] = "historical-58-revision"
    assert evaluate_completion_contract(contract, stale_identity, index)["status"] == "rejected_identity"

    held = evaluate_completion_contract(
        contract,
        {"phase": "post_native_callback", "task_id": "CIMP-GUI-59", "blocked": True, "reasons": ["manual_hold"]},
        index,
    )
    assert held["status"] == "blocked"
    assert held["reasons"] == ["manual_hold"]


def test_authorization_grant_consent_and_messaging_have_negative_paths() -> None:
    contract = load_contract()
    owner = classify_authorization(contract, {"actor": "case_owner", "actor_id": "user-1", "encrypted_owner_binding": "owner-binding"})
    assert owner["status"] == "instructional_allow"
    assert owner["case_content"] is False
    assert owner["example_case_content"] is True and owner["authorization_authority"] is False
    assert owner["completed"] is False

    lawyer = classify_authorization(
        contract,
        {"actor": "assigned_lawyer", "role_alone": True, "membership_accepted": False, "key_grant_accepted": False},
    )
    assert lawyer["status"] == "denied"
    assert lawyer["reason"] == "lawyer_role_alone"

    granted = classify_authorization(
        contract,
        {"actor": "assigned_lawyer", "membership_accepted": True, "key_grant_accepted": True, "role_alone": False},
    )
    assert granted["status"] == "instructional_allow"

    admin = classify_authorization(contract, {"actor": "operational_admin", "requests_case_content": True})
    assert admin["status"] == "denied"
    assert admin["reason"] == "admin_ambient_plaintext"
    metadata = classify_authorization(contract, {"actor": "operational_admin", "requests_case_content": False})
    assert metadata["status"] == "instructional_allow"
    assert metadata["case_content"] is False

    stranger = classify_authorization(contract, {"actor": "unassigned"})
    assert stranger["status"] == "denied"
    impersonation = classify_authorization(
        contract,
        {
            "actor": "case_owner",
            "actor_id": "same-binding",
            "encrypted_owner_binding": "same-binding",
            "impersonates_owner": True,
        },
    )
    assert impersonation["status"] == "denied"

    minted = classify_grant_recovery(contract, {"missing_key": True, "mint_replacement": True})
    assert minted["status"] == "rejected_key_mint"
    revoked = classify_grant_recovery(
        contract,
        {"revoked": True, "future_access": False, "erases_downloaded_content": False},
    )
    assert revoked["status"] == "revoked"
    assert revoked["downloaded_content_erased"] is False
    erasure = classify_grant_recovery(contract, {"revoked": True, "future_access": False, "erases_downloaded_content": True})
    assert erasure["status"] == "rejected_erasure_claim"
    recoverable = classify_grant_recovery(
        contract,
        {"recipient": "lawyer-1", "scope": "read", "expiry": "2099-01-01", "revocation": "none", "rotation": "gen-1"},
    )
    assert recoverable["status"] == "recoverable"

    local = classify_consent(contract, {"mode": "local"})
    assert local["status"] == "recorded"
    assert local["egress"] is False
    remote = classify_consent(contract, {"mode": "grok", "late_result": True, "rechecked": True})
    assert remote["egress"] is True
    dev = classify_consent(contract, {"development_authorization": True, "treats_as_egress": True, "mode": "grok"})
    assert dev["status"] == "rejected_development_authorization"
    omitted = classify_consent(contract, {"flag_omitted": True, "creates_consent": True})
    assert omitted["status"] == "rejected_omitted_flag"
    late = classify_consent(contract, {"mode": "grok", "late_result": True, "rechecked": False})
    assert late["status"] == "rejected_late_result"

    conversation = classify_message(contract, {"transport": "http_polling", "authorized": True, "actor_id": "user-1"})
    assert conversation["status"] == "conversation"
    assert conversation["evidence"] is False
    adopted = classify_message(
        contract,
        {"transport": "http_polling", "authorized": True, "actor_id": "user-1", "accepted_action": "evidence"},
    )
    assert adopted["status"] == "adopted"
    assert adopted["evidence"] is True
    streaming = classify_message(contract, {"transport": "websocket", "claims_streaming": True})
    assert streaming["status"] == "rejected_unqualified_transport"
    external = classify_message(contract, {"channel": "court_filing", "transport": "http_polling"})
    assert external["status"] == "outside_campaign"


def test_graph_stop_and_watchdog_reject_overclaim() -> None:
    contract = load_contract()
    assertion = classify_graph_claim(contract, {"kind": "factual_assertion", "source_id": "span-1"})
    assert assertion["status"] == "recorded_assertion"
    assert assertion["legal_sufficiency"] is False
    snippet = classify_graph_claim(contract, {"kind": "snippet", "governing_law": True})
    assert snippet["status"] == "rejected_not_governing_law"
    rewrite = classify_graph_claim(contract, {"kind": "factual_assertion", "source_id": "span-1", "factual_answer_rewrites_rule": True})
    assert rewrite["status"] == "rejected_rule_rewrite"
    sufficiency = classify_graph_claim(contract, {"kind": "admitted_authority", "legal_sufficiency": True, "source_span": "s", "jurisdiction": "j", "effective_date": "d", "version": "v"})
    assert sufficiency["status"] == "rejected_legal_sufficiency"
    admitted = classify_graph_claim(
        contract,
        {"kind": "admitted_authority", "source_span": "s", "jurisdiction": "j", "effective_date": "d", "version": "v"},
    )
    assert admitted["status"] == "admitted_candidate"
    assert admitted["governing_law"] is False

    waiting = classify_stop(contract, {"awaiting_user": True})
    assert waiting["status"] == "awaiting_user"
    assert waiting["stalled_worker"] is False
    misread = classify_stop(contract, {"awaiting_user": True, "classify_as_stalled_worker": True})
    assert misread["status"] == "rejected_stalled_classification"
    paused = classify_stop(contract, {"reason": "pause", "attempts": 2})
    assert paused["status"] == "stopped"
    assert paused["legal_sufficiency"] is False
    saturated = classify_stop(contract, {"reason": "saturation", "claims_legal_sufficiency": True})
    assert saturated["status"] == "rejected_legal_sufficiency"
    overrun = classify_stop(contract, {"reason": "declared_limit", "attempts": 4})
    assert overrun["status"] == "rejected_attempt_cap"

    doctor = classify_watchdog(contract, {"doctor_only": True, "pid_only": False})
    assert doctor["status"] == "rejected_unauthenticated_watchdog"
    assert doctor["startup"] is False
    pid = classify_watchdog(contract, {"pid_only": True})
    assert pid["startup"] is False
    authenticated = classify_watchdog(
        contract,
        {
            "authenticated": True,
            "provider": "grok_cli",
            "model": "grok-4.7",
            "allow_fallback": False,
            "preserves_holds": True,
            "grok_route": True,
            "canonical_active_task": True,
            "fresh_owned_activity": True,
            "measured_validation": True,
            "merge": True,
            "completion_callback": True,
        },
    )
    assert authenticated["status"] == "unverified_instructional_observation"
    assert authenticated["startup"] is False
    assert authenticated["verified"] is False and authenticated["instructional_only"] is True
    assert authenticated["completed"] is False
    assert authenticated["program_completed"] is False
    partial = classify_watchdog(
        contract,
        {
            "authenticated": True,
            "provider": "grok_cli",
            "model": "grok-4.7",
            "allow_fallback": False,
            "preserves_holds": True,
            "grok_route": True,
        },
    )
    assert partial["status"] == "unavailable"
    assert "canonical_active_task" in partial["missing"]
    fallback = classify_watchdog(contract, {"provider": "grok_cli", "model": "grok-4.7", "allow_fallback": True})
    assert fallback["status"] == "rejected_fallback"


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
        {"CIMP-GUI-60": {"goal_id": contract["goal_id"], "subgoal_id": contract["subgoal_id"]}},
    )
    assert outcome["status"] == "self_pending"
    assert outcome["completed"] is False
    assert outcome["state_authority"] is False
    denied = classify_authorization(contract, {"actor": "unassigned"})
    assert denied["status"] == "denied"
    assert denied["completed"] is False


def test_real_plan_compiler_and_native_parser_derive_current_task_identity():
    from integrations.ipfs_accelerate import improvement_plan as compiler
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    contract=load_contract()
    spec=compiler.load_spec(ROOT/contract['new_plan']['spec_relative'])
    plan=compiler.build_improvement_work_plan(spec)
    stored=_load_json(contract['new_plan']['plan_relative'])
    assert stored=={**plan.to_dict(),'plan_id':plan.plan_id}
    assert plan.plan_id and len(stored['tasks'])==60
    formal={row['task_id']:row for row in stored['tasks']}
    parsed=native.parse_task_text((ROOT/contract['new_plan']['board_relative']).read_text(),
        path=ROOT/contract['new_plan']['board_relative'],task_header_prefix='## CIMP-')
    tasks={row.task_id:row for row in parsed}
    assert len(parsed)==len(tasks)==60 and set(tasks)==set(formal)
    actual=tasks['CIMP-GUI-60']
    assert actual.canonical_task_cid and actual.canonical_task_key
    assert formal[actual.task_id]['goal_id']==contract['goal_id']
    assert formal[actual.task_id]['subgoal_id']==contract['subgoal_id']
    assert contract['production_verifier']['read_only'] is True
    assert contract['current_source_acceptance']['required_groups']==12
    # This is actual pure identity derivation, with no completion observation.
    assert contract['completion_authority'] is False and contract['instructional_only'] is True


def test_actual_read_only_verifier_refuses_missing_and_mismatched_private_evidence(tmp_path):
    from integrations.ipfs_accelerate.campaign_completion import verify_campaign_completion
    from integrations.ipfs_accelerate import improvement_plan as compiler
    contract=load_contract();spec_path=ROOT/contract['new_plan']['spec_relative']
    spec=compiler.load_spec(spec_path);plan=compiler.build_improvement_work_plan(spec)
    state=tmp_path/'synthetic-existing-state';state.mkdir(mode=0o700)
    forged=state/'caller-success.json'
    forged.write_text(json.dumps({'verified':True,'completed':60,'authenticated':True}))
    forged.chmod(0o600)
    before={p.name:p.read_bytes() for p in state.iterdir()}
    missing=verify_campaign_completion(ROOT,spec_path,state)
    assert missing['verified'] is False and missing['completion_authority'] is False
    assert missing['task_count']==60 and missing['reason']=='completion_evidence_unavailable'
    assert missing.get('error_type')=='FileNotFoundError'
    assert {p.name:p.read_bytes() for p in state.iterdir()}==before
    # All metadata is authored synthetic input; a mismatch must be observed by
    # the real production API, not the legacy instructional evaluator above.
    launcher={'schema_version':'complaint-improvement-launcher@1','repo_root':str(ROOT),
        'state_dir':str(state),'spec_path':str(spec_path),'board_path':str(ROOT/contract['new_plan']['board_relative']),
        'plan_id':'mismatched-'+plan.plan_id,'merge_target':'synthetic-unused-branch',
        'provider':'grok_cli','model':'grok-4.7','allow_fallback':False}
    path=state/'launcher.json';path.write_text(json.dumps(launcher));path.chmod(0o600)
    before={p.name:p.read_bytes() for p in state.iterdir()}
    mismatch=verify_campaign_completion(ROOT,spec_path,state)
    assert mismatch['verified'] is False and mismatch['reason']=='campaign_launcher_binding_mismatch'
    assert mismatch['historical_execution_only'] is True
    assert mismatch['current_source_qualification'] is False and mismatch['tasks']=={}
    assert {p.name:p.read_bytes() for p in state.iterdir()}==before
    assert not (state/'control-plane').exists() and not (state/'merge-queue').exists()
