"""Gate supervisor terminal completion on executed synthetic evidence.

A source file that merely contains an acceptance phrase is not a completion
receipt. Interview ``awaiting_user`` is a product wait. It is not a stalled
development worker, and it is never cleared by inventing an answer or by
forcing a legal outcome.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


SCHEMA = "complaint-generator/supervisor-terminal-acceptance@1"
REQUIRED_LANES = ("pty", "graph", "privacy")
MAX_PTY_TURNS = 8
MAX_EXTERNAL_RETRIES = 3
DEFAULT_STALL_SECONDS = 120

# These are executed by the existing Native measured pytest command. The
# installed behavioral-definition guard preserves their reviewed implementations.
REQUIRED_TERMINAL_JOURNEYS = (
    "tests/test_tui_supervisor_acceptance.py::test_actual_native_terminal_pty_journey",
    "tests/test_tui_supervisor_acceptance.py::test_actual_native_shared_graph_journey",
    "tests/test_tui_supervisor_acceptance.py::test_actual_native_private_unlock_journey",
)

LaneRunner = Callable[[Mapping[str, Any]], Mapping[str, Any]]


def terminal_measurement_reason(observation, task: Mapping[str, Any]) -> str:
    """Require owned sealed measurements of all three real public journeys.

    This is admission evidence. Native's callback remains the sole task
    completion authority. Caller-supplied receipt dictionaries cannot qualify.
    """
    from .improvement_plan import _host_evidence_reason
    reason = _host_evidence_reason(observation, task)
    if reason:
        return reason
    required = observation.get("required_nodeids", [])
    measured = {row["nodeid"]: row["outcome"] for row in observation.get("cases", [])}
    if any(node not in required or measured.get(node) != "passed" for node in REQUIRED_TERMINAL_JOURNEYS):
        return "terminal_public_journeys_not_measured"
    return ""



class TerminalAcceptanceError(ValueError):
    """The supervisor refused an unsafe completion or recovery action."""


def _digest(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def source_identity(paths: Sequence[str | Path]) -> dict[str, Any]:
    """Hash declared source files. Missing files stay visible and unbound."""

    files: list[dict[str, Any]] = []
    missing: list[str] = []
    for raw in paths:
        path = Path(raw)
        record: dict[str, Any] = {"path": str(path)}
        if not path.is_file():
            record.update({"present": False, "sha256": "", "size": 0})
            missing.append(str(path))
        else:
            data = path.read_bytes()
            record.update({"present": True, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)})
        files.append(record)
    bound = [row for row in files if row["present"]]
    return {
        "files": files,
        "missing": missing,
        "digest": _digest([{"path": row["path"], "sha256": row["sha256"]} for row in bound]) if bound and not missing else "",
    }


def _lane_receipt(lane: str, body: Mapping[str, Any]) -> dict[str, Any]:
    status = str(body.get("status") or "")
    if status not in {"passed", "failed", "skipped"}:
        raise TerminalAcceptanceError(f"{lane} acceptance returned an unknown status")
    if body.get("executed") is not True and status != "skipped":
        raise TerminalAcceptanceError(f"{lane} acceptance reported {status} without execution")
    receipt = {
        "lane": lane,
        "status": status,
        "executed": bool(body.get("executed")),
        "reason": str(body.get("reason") or ""),
        "detail": body.get("detail") if isinstance(body.get("detail"), dict) else {},
    }
    receipt["digest"] = _digest(receipt)
    return receipt


def default_pty_acceptance(fixture: Mapping[str, Any]) -> dict[str, Any]:
    """Walk a bounded synthetic transcript. Missing user lines stay unanswered."""

    if fixture.get("fabricate_missing_answer") is True:
        raise TerminalAcceptanceError("synthetic PTY acceptance cannot fabricate a user answer")
    script = fixture.get("script")
    if not isinstance(script, list) or not script:
        return {"status": "skipped", "executed": False, "reason": "pty_fixture_absent", "detail": {}}
    if len(script) > int(fixture.get("max_turns") or MAX_PTY_TURNS):
        return {
            "status": "failed",
            "executed": True,
            "reason": "pty_turn_bound_exceeded",
            "detail": {"turns": len(script), "max_turns": int(fixture.get("max_turns") or MAX_PTY_TURNS)},
        }
    turns = []
    for index, turn in enumerate(script):
        if not isinstance(turn, Mapping) or turn.get("role") not in {"user", "assistant"} or not isinstance(turn.get("text"), str):
            return {"status": "failed", "executed": True, "reason": "pty_turn_malformed", "detail": {"index": index}}
        if turn["role"] == "user" and not turn["text"].strip():
            return {"status": "failed", "executed": True, "reason": "empty_user_turn", "detail": {"index": index}}
        turns.append({"role": turn["role"], "text": turn["text"]})
    awaiting = bool(fixture.get("awaiting_user"))
    return {
        "status": "passed",
        "executed": True,
        "reason": "bounded_synthetic_pty",
        "detail": {"turns": len(turns), "awaiting_user": awaiting, "transcript_digest": _digest(turns)},
    }


def default_graph_acceptance(fixture: Mapping[str, Any]) -> dict[str, Any]:
    """Require explicit synthetic nodes and provenance. Do not invent either."""

    nodes = fixture.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return {"status": "skipped", "executed": False, "reason": "graph_fixture_absent", "detail": {}}
    seen: set[str] = set()
    for index, node in enumerate(nodes):
        if not isinstance(node, Mapping):
            return {"status": "failed", "executed": True, "reason": "graph_node_malformed", "detail": {"index": index}}
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id or node_id in seen:
            return {"status": "failed", "executed": True, "reason": "graph_node_identity", "detail": {"index": index}}
        seen.add(node_id)
        provenance = node.get("provenance")
        if not isinstance(provenance, Mapping) or not provenance.get("source_id") or not provenance.get("source_kind"):
            return {"status": "failed", "executed": True, "reason": "graph_provenance_missing", "detail": {"id": node_id}}
    return {
        "status": "passed",
        "executed": True,
        "reason": "bounded_synthetic_graph",
        "detail": {"node_ids": sorted(seen), "graph_digest": _digest(list(nodes))},
    }


def default_privacy_acceptance(fixture: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed when a synthetic read touches a denied path. Do not open it."""

    denied = fixture.get("denied_paths")
    attempted = fixture.get("attempted_reads")
    if not isinstance(denied, list):
        return {"status": "skipped", "executed": False, "reason": "privacy_fixture_absent", "detail": {}}
    denied_set = {str(item) for item in denied}
    if not isinstance(attempted, list):
        attempted = []
    leaked = sorted(str(item) for item in attempted if str(item) in denied_set)
    if leaked:
        return {
            "status": "failed",
            "executed": True,
            "reason": "denied_path_read",
            "detail": {"leaked": leaked},
        }
    return {
        "status": "passed",
        "executed": True,
        "reason": "bounded_synthetic_privacy",
        "detail": {"denied_count": len(denied_set), "attempted_count": len(attempted)},
    }


_DEFAULT_RUNNERS: dict[str, LaneRunner] = {
    "pty": default_pty_acceptance,
    "graph": default_graph_acceptance,
    "privacy": default_privacy_acceptance,
}


def _default_fixtures() -> dict[str, dict[str, Any]]:
    return {
        "pty": {
            "max_turns": MAX_PTY_TURNS,
            "awaiting_user": True,
            "script": [
                {"role": "assistant", "text": "What happened?"},
                {"role": "user", "text": "A synthetic event on 2024-01-02."},
            ],
        },
        "graph": {
            "nodes": [
                {
                    "id": "synthetic-event-1",
                    "provenance": {"source_kind": "user_statement", "source_id": "msg-synthetic-1"},
                }
            ]
        },
        "privacy": {"denied_paths": ["sessions/real", "exports/real"], "attempted_reads": ["fixtures/synthetic.txt"]},
    }


def execute_bounded_acceptance(
    *,
    task_id: str,
    source_paths: Sequence[str | Path],
    fixtures: Mapping[str, Mapping[str, Any]] | None = None,
    runners: Mapping[str, LaneRunner] | None = None,
    live_canary: Mapping[str, Any] | None = None,
    product_session: Mapping[str, Any] | None = None,
    substring_check: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate fixture structure and attach diagnostic source identity.

    Fixture processing is a unit lane and never authorizes completion.
    ``substring_check`` is recorded and never authorizes completion.
    """

    if not isinstance(task_id, str) or not task_id:
        raise TerminalAcceptanceError("terminal acceptance requires a task id")
    selected = dict(_DEFAULT_RUNNERS)
    if runners:
        unknown = set(runners) - set(REQUIRED_LANES)
        if unknown:
            raise TerminalAcceptanceError(f"unknown acceptance lane: {sorted(unknown)}")
        selected.update(runners)
    provided = dict(_default_fixtures())
    if fixtures:
        for lane, fixture in fixtures.items():
            if lane not in REQUIRED_LANES:
                raise TerminalAcceptanceError(f"unknown acceptance fixture: {lane}")
            if not isinstance(fixture, Mapping):
                raise TerminalAcceptanceError(f"{lane} fixture must be a mapping")
            provided[lane] = dict(fixture)
    receipts = []
    for lane in REQUIRED_LANES:
        body = selected[lane](provided[lane])
        if not isinstance(body, Mapping):
            raise TerminalAcceptanceError(f"{lane} acceptance returned no receipt")
        receipts.append(_lane_receipt(lane, body))
    identity = source_identity(source_paths)
    passed = [row["lane"] for row in receipts if row["status"] == "passed"]
    skipped = [row["lane"] for row in receipts if row["status"] == "skipped"]
    failed = [row["lane"] for row in receipts if row["status"] == "failed"]
    canary = _live_canary_status(live_canary)
    issues = _session_issues(product_session)
    substring = _substring_observation(substring_check)
    fixture_valid = bool(
        not failed
        and not skipped
        and passed == list(REQUIRED_LANES)
        and identity["digest"]
        and substring["authoritative"] is False
    )
    reason = "fixture_validation_only" if fixture_valid else _rejection_reason(failed, skipped, identity)
    return {
        "schema": SCHEMA,
        "task_id": task_id,
        "source_identity": identity,
        "output_receipts": receipts,
        "passed": passed,
        "skipped": skipped,
        "failed": failed,
        "live_canary": canary,
        "completion": False,
        "completion_authority": "none",
        "evidence_class": "unit_fixture",
        "fixture_valid": fixture_valid,
        "reason": reason,
        "substring_check": substring,
        "unresolved_legal_user_issues": issues,
        "product_session_legal_status": _legal_status(product_session),
    }


def _rejection_reason(failed: Sequence[str], skipped: Sequence[str], identity: Mapping[str, Any]) -> str:
    if not identity.get("digest"):
        return "missing_source_identity"
    if failed:
        return "acceptance_failed:" + ",".join(failed)
    if skipped:
        return "skipped_required_lane:" + ",".join(skipped)
    return "acceptance_incomplete"


def _substring_observation(check: Mapping[str, Any] | None) -> dict[str, Any]:
    if not check:
        return {"used": False, "matched": False, "authoritative": False}
    source_text = check.get("source_text")
    needle = check.get("needle")
    matched = isinstance(source_text, str) and isinstance(needle, str) and needle != "" and needle in source_text
    return {"used": True, "matched": matched, "authoritative": False}


def _live_canary_status(live_canary: Mapping[str, Any] | None) -> dict[str, Any]:
    if not live_canary or live_canary.get("requested") is not True:
        return {"requested": False, "executed": False, "status": "not_requested"}
    executed = live_canary.get("executed") is True
    raw_status = live_canary.get("status")
    if not executed:
        status = "not_executed"
    elif raw_status in {"passed", "failed"}:
        status = raw_status
    else:
        status = "not_executed"
        executed = False
    return {"requested": True, "executed": executed, "status": status}


def _session_issues(session: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if session is None:
        return []
    raw = session.get("unresolved_issues")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise TerminalAcceptanceError("product session unresolved issues must be a list")
    issues = []
    for item in raw:
        if not isinstance(item, Mapping) or not isinstance(item.get("id"), str) or not item.get("kind"):
            raise TerminalAcceptanceError("each unresolved issue needs an id and kind")
        if item["kind"] not in {"legal", "user"}:
            raise TerminalAcceptanceError("unresolved issue kind must be legal or user")
        issues.append({"id": item["id"], "kind": item["kind"], "summary": str(item.get("summary") or "")})
    return issues


def _legal_status(session: Mapping[str, Any] | None) -> str:
    if session is None:
        return "absent"
    status = session.get("legal_status", "unresolved")
    if status not in {"unresolved", "complete"}:
        raise TerminalAcceptanceError("product session legal_status is not recognized")
    return str(status)


def mark_terminal_complete(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Serialized receipts remain observations, including self-asserted success."""

    method = evidence.get("method")
    if method == "source_substring":
        return {
            "schema": SCHEMA,
            "completion": False,
            "completion_authority": "none",
            "reason": "source_substring_not_authoritative",
            "passed": [],
            "skipped": [],
            "live_canary": {"requested": False, "executed": False, "status": "not_requested"},
            "substring_check": {"used": True, "matched": bool(evidence.get("matched", True)), "authoritative": False},
        }
    receipt = evidence.get("receipt")
    if not isinstance(receipt, Mapping) or receipt.get("schema") != SCHEMA:
        raise TerminalAcceptanceError("terminal completion requires an acceptance receipt")
    if evidence.get("source_identity_digest") != receipt.get("source_identity", {}).get("digest"):
        rejected = dict(receipt)
        rejected["completion"] = False
        rejected["completion_authority"] = "none"
        rejected["reason"] = "stale_source_identity"
        return rejected
    if receipt.get("substring_check", {}).get("authoritative") is True:
        raise TerminalAcceptanceError("a substring check cannot be marked authoritative")
    rejected = dict(receipt)
    rejected.update(completion=False, completion_authority="none", reason="host_measurement_required", evidence_class="serialized_observation")
    return rejected


def distinguish_wait(observation: Mapping[str, Any]) -> dict[str, Any]:
    """Separate an end-user interview wait from a stalled development worker."""

    role = observation.get("role")
    phase = observation.get("phase")
    if role == "end_user_interview":
        legitimate = phase == "awaiting_user"
        return {
            "classification": "legitimate_awaiting_user" if legitimate else "interview_not_waiting",
            "stalled_development_worker": False,
            "recovery_action": "wait" if legitimate else "continue_interview",
            "fabricated_user_answer": None,
            "legal_completion_forced": False,
        }
    if role != "development_worker":
        raise TerminalAcceptanceError("wait observation role must be end_user_interview or development_worker")
    stall_after = observation.get("stall_after_seconds", DEFAULT_STALL_SECONDS)
    if isinstance(stall_after, bool) or not isinstance(stall_after, int) or stall_after <= 0:
        raise TerminalAcceptanceError("stall_after_seconds must be a positive integer")
    age = observation.get("heartbeat_age_seconds")
    if age is not None and (isinstance(age, bool) or not isinstance(age, (int, float)) or age < 0):
        raise TerminalAcceptanceError("heartbeat_age_seconds must be a non-negative number or null")
    stalled = age is None or age > stall_after
    return {
        "classification": "stalled_development_worker" if stalled else "development_worker_active",
        "stalled_development_worker": stalled,
        "recovery_action": "bounded_retry" if stalled else "continue",
        "fabricated_user_answer": None,
        "legal_completion_forced": False,
    }


def refuse_unstick_action(action: str) -> dict[str, Any]:
    """Development recovery must not invent user text or close legal issues."""

    if action == "fabricate_user_answer":
        raise TerminalAcceptanceError("refusing to fabricate a user answer to unstick development")
    if action == "force_legal_completion":
        raise TerminalAcceptanceError("refusing to force legal completion to unstick development")
    raise TerminalAcceptanceError(f"unknown unstick action: {action}")


def continue_development(
    task: Mapping[str, Any],
    *,
    synthetic_fixture: Mapping[str, Any] | None = None,
    external_dependency: Mapping[str, Any] | None = None,
    state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Continue on a synthetic fixture, or stop with a resumable external diagnostic."""

    task_id = task.get("id")
    if not isinstance(task_id, str) or not task_id:
        raise TerminalAcceptanceError("development task requires an id")
    if task.get("fabricate_user_answer") is True or task.get("force_legal_completion") is True:
        refuse_unstick_action(
            "fabricate_user_answer" if task.get("fabricate_user_answer") is True else "force_legal_completion"
        )
    prior = dict(state or {})
    attempt = prior.get("attempt", 0)
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 0:
        raise TerminalAcceptanceError("resumable attempt must be a non-negative integer")
    checkpoint = prior.get("checkpoint")
    if checkpoint is None:
        checkpoint = {"task_id": task_id, "cursor": task.get("cursor") or "start"}
    if not isinstance(checkpoint, Mapping):
        raise TerminalAcceptanceError("resumable checkpoint must be a mapping")
    checkpoint = dict(checkpoint)

    if synthetic_fixture is not None:
        if not isinstance(synthetic_fixture, Mapping) or not synthetic_fixture.get("fixture_id"):
            raise TerminalAcceptanceError("synthetic fixture requires a fixture_id")
        return {
            "task_id": task_id,
            "status": "continued",
            "used_synthetic_fixture": True,
            "fixture_id": str(synthetic_fixture["fixture_id"]),
            "attempt": attempt,
            "retry_cap": MAX_EXTERNAL_RETRIES,
            "checkpoint": checkpoint,
            "diagnostic": None,
            "fabricated_user_answer": None,
            "legal_completion_forced": False,
        }

    if external_dependency is None:
        raise TerminalAcceptanceError("development continuation needs a synthetic fixture or an external dependency")
    if external_dependency.get("irreducible") is not True:
        raise TerminalAcceptanceError("a reducible dependency must be replaced with a synthetic fixture")
    name = external_dependency.get("name")
    code = external_dependency.get("code")
    detail = external_dependency.get("detail")
    if not all(isinstance(item, str) and item for item in (name, code, detail)):
        raise TerminalAcceptanceError("external dependency diagnostic requires name, code, and detail")
    if external_dependency.get("available") is True:
        raise TerminalAcceptanceError("an available dependency is not an irreducible stop")
    next_attempt = attempt + 1
    blocked = next_attempt > MAX_EXTERNAL_RETRIES
    return {
        "task_id": task_id,
        "status": "blocked_external_dependency" if blocked else "retry_scheduled",
        "used_synthetic_fixture": False,
        "fixture_id": None,
        "attempt": next_attempt if not blocked else attempt,
        "retry_cap": MAX_EXTERNAL_RETRIES,
        "retries_remaining": 0 if blocked else MAX_EXTERNAL_RETRIES - next_attempt,
        "checkpoint": checkpoint,
        "diagnostic": {
            "name": name,
            "code": code,
            "detail": detail,
            "bounded": True,
        },
        "fabricated_user_answer": None,
        "legal_completion_forced": False,
    }


def apply_receipt_to_product_session(session: Mapping[str, Any], receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Copy unresolved legal and user issues onto the receipt without closing them."""

    if not isinstance(session, Mapping):
        raise TerminalAcceptanceError("product session must be a mapping")
    updated = {
        "session_id": session.get("session_id"),
        "legal_status": _legal_status(session),
        "unresolved_issues": _session_issues(session),
        "supervisor_receipt_task_id": receipt.get("task_id"),
        "supervisor_completion": bool(receipt.get("completion")),
    }
    if updated["unresolved_issues"] and updated["legal_status"] == "complete":
        raise TerminalAcceptanceError("a product session cannot be legally complete while issues remain")
    return updated
