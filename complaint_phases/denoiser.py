"""
Complaint Denoiser

Iteratively asks questions to fill gaps in the knowledge graph and reduce
noise/ambiguity in the complaint information.
"""

import copy
import hashlib
import json
import logging
import re
from typing import Dict, List, Any, Optional, Tuple, Set
import os
import random
from lib.runtime_ownership import require_module_ownership
from .knowledge_graph import KnowledgeGraph, Entity, Relationship
from .dependency_graph import DependencyGraph
from .intake_claim_registry import (
    build_claim_element_question_intent,
    build_claim_element_question_text,
    build_proof_lead_question_intent,
    build_proof_lead_question_text,
    normalize_claim_type,
    render_question_text_from_intent,
)

logger = logging.getLogger(__name__)

_SUPPORT_STATE_NAMES = ("user_assertion", "corroboration", "candidate", "applicability", "proof")
_SUPPORT_STATE_TOKENS = frozenset({
    "unknown", "asserted", "unasserted", "corroborated", "uncorroborated",
    "candidate", "not_candidate", "applicable", "inapplicable", "unproved",
    "proved", "missing", "unavailable", "contradicted", "needs_review",
    "admitted", "rejected", "recorded",
})
_PRIVATE_DIAGNOSTIC_KEYS = frozenset({
    "narrative", "prompt", "answer", "question", "why_it_matters", "text", "wording",
    "span_text", "quote", "secret", "passphrase", "content", "candidate",
    "expected_information", "display", "password", "token", "recovery",
})
_CONDITION_COPY = {
    "unknown_authority": (
        "Admitted authority for this question is unknown.",
        "identify_or_research_admitted_authority",
    ),
    "source_outage": (
        "A legal source is unavailable. This outage is not legal sufficiency.",
        "retry_when_source_available",
    ),
    "contradiction": (
        "Accounts conflict. Neither account is treated as proved.",
        "clarify_the_conflicting_accounts",
    ),
    "missing_definition": (
        "The element definition is missing and still needs review.",
        "review_the_element_definition",
    ),
    "missing_review": (
        "A required review is missing.",
        "complete_manual_review",
    ),
}
_WHY_DISPLAY_CHAR_BUDGET = 3500
_FIELD_CHAR_BUDGET = 160


def _clip_public(value: Any, limit: int = _FIELD_CHAR_BUDGET) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _state_token(value: Any) -> str:
    token = str(value or "").strip().lower().replace(" ", "_")
    if token in _SUPPORT_STATE_TOKENS:
        return token
    return "recorded" if token else "unknown"


def _mapping(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _factual_target_view(inquiry: Dict[str, Any]) -> Dict[str, str]:
    raw = _mapping(inquiry.get("factual_target"))
    unresolved = _mapping(inquiry.get("unresolved_target"))
    kind = str(raw.get("kind") or unresolved.get("target_kind") or inquiry.get("target_kind") or inquiry.get("gap_family") or "")
    target_id = str(raw.get("target_id") or "").strip()
    label = str(raw.get("label") or raw.get("name") or "").strip()
    factual_kinds = {"factual", "factual_uncertainty", "timeline", "clarification"}
    if not target_id and kind.strip().lower() in factual_kinds:
        target_id = str(unresolved.get("target_id") or inquiry.get("target_id") or "").strip()
    if not label and kind.strip().lower() in factual_kinds:
        label = str(unresolved.get("label") or unresolved.get("name") or "").strip()
    return {
        "target_id": _clip_public(target_id) or "unknown",
        "label": _clip_public(label) or "unknown",
        "kind": "factual",
    }


def _law_requirement_view(inquiry: Dict[str, Any], factual: Dict[str, str]) -> Dict[str, str]:
    raw = _mapping(inquiry.get("law_derived_requirement") or inquiry.get("legal_requirement"))
    requirement_id = str(raw.get("requirement_id") or raw.get("element_id") or "").strip()
    label = str(raw.get("label") or raw.get("name") or raw.get("element") or "").strip()
    law_derived = raw.get("law_derived")
    if law_derived is None:
        law_derived = bool(requirement_id or label) or str(inquiry.get("gap_family") or "") == "legal_element_support"
    if not requirement_id and str(inquiry.get("gap_family") or "") == "legal_element_support":
        requirement_id = str(inquiry.get("requirement_id") or "").strip()
    # A factual target id is not a law-derived requirement, even when it is the only id present.
    if requirement_id and requirement_id == factual.get("target_id") and factual.get("target_id") != "unknown":
        if not raw:
            requirement_id = ""
    if label and label == factual.get("label") and factual.get("label") != "unknown" and not raw:
        label = ""
    return {
        "requirement_id": _clip_public(requirement_id) or "unknown",
        "label": _clip_public(label) or "unknown",
        "law_derived": "true" if law_derived and (requirement_id or label) else "false",
    }


def _admitted_authorities(inquiry: Dict[str, Any]) -> List[Dict[str, str]]:
    raw = inquiry.get("admitted_authorities")
    if not isinstance(raw, list):
        raw = inquiry.get("authority_references")
    if not isinstance(raw, list):
        single = _mapping(inquiry.get("admitted_authority"))
        raw = [single] if single else []
    admitted: List[Dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or item.get("admission") or "").strip().lower()
        if item.get("admitted") is False or status in {"rejected", "unknown", "candidate", "unavailable"}:
            continue
        if item.get("admitted") is not True and status not in {"admitted", "admitted_authority"}:
            continue
        citation = _clip_public(item.get("citation") or item.get("cite") or "")
        version = _clip_public(item.get("version") or item.get("edition") or "")
        span = _clip_public(item.get("span") or item.get("span_id") or item.get("span_ref") or "")
        if not (citation or version or span):
            continue
        admitted.append({
            "citation": citation or "unknown",
            "version": version or "unknown",
            "span": span or "unknown",
        })
        if len(admitted) >= 4:
            break
    return admitted


def _support_states(inquiry: Dict[str, Any]) -> Dict[str, str]:
    raw = _mapping(inquiry.get("support_states"))
    states = {name: _state_token(raw.get(name, inquiry.get(name))) for name in _SUPPORT_STATE_NAMES}
    score = inquiry.get("retrieval_score", inquiry.get("relevance_score"))
    raw_proof = raw.get("proof", inquiry.get("proof"))
    raw_proof_text = str(raw_proof).strip() if raw_proof is not None else ""
    score_text = str(score).strip() if score is not None else ""
    # A retrieval score never fills proof, including when a caller copies the score into proof.
    if not raw_proof_text or (score_text and raw_proof_text == score_text):
        states["proof"] = "unknown"
    return states


def _support_conditions(inquiry: Dict[str, Any], authorities: List[Dict[str, str]]) -> List[Dict[str, str]]:
    authority_status = str(inquiry.get("authority_status") or "").strip().lower()
    source_status = str(inquiry.get("source_status") or inquiry.get("legal_source_status") or "").strip().lower()
    definition_status = str(inquiry.get("definition_status") or "").strip().lower()
    review_status = str(inquiry.get("review_status") or "").strip().lower()
    reasons = {str(item).strip().lower() for item in (inquiry.get("unknown_reasons") or [])}
    family = str(inquiry.get("gap_family") or "").strip().lower()
    flags = {
        "unknown_authority": (not authorities) or authority_status in {"unknown", "missing"},
        "source_outage": source_status in {"outage", "unavailable", "source_outage"} or "source_outage" in reasons,
        "contradiction": family == "contradiction" or bool(inquiry.get("contradiction")) or "contradiction" in reasons,
        "missing_definition": definition_status in {"missing", "unknown"} or bool(inquiry.get("missing_definition")) or "missing_definition" in reasons,
        "missing_review": review_status in {"missing", "needs_review"} or bool(inquiry.get("missing_review")) or "missing_review" in reasons,
    }
    # Unknown authority is the standing case. Other conditions appear only when the inquiry says so.
    if authority_status in {"admitted", "known"} and authorities:
        flags["unknown_authority"] = False
    conditions: List[Dict[str, str]] = []
    for kind, enabled in flags.items():
        if not enabled:
            continue
        message, action = _CONDITION_COPY[kind]
        conditions.append({"kind": kind, "message": message, "next_action": action})
    return conditions


def question_support_view(inquiry: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Separate factual, law-derived, authority, and support facts for /why.

    Retrieval rank stays a retrieval fact. It is not proof, applicability, or admission.
    """
    record = inquiry if isinstance(inquiry, dict) else {}
    factual = _factual_target_view(record)
    requirement = _law_requirement_view(record, factual)
    authorities = _admitted_authorities(record)
    states = _support_states(record)
    conditions = _support_conditions(record, authorities)
    score = record.get("retrieval_score", record.get("relevance_score"))
    score_text = "none"
    if score is not None and str(score).strip():
        score_text = _clip_public(score, 32)
    return {
        "factual_target": factual,
        "law_derived_requirement": requirement,
        "admitted_authorities": authorities,
        "authority_status": "admitted" if authorities else "unknown",
        "support_states": states,
        "retrieval_score": score_text,
        "retrieval_score_is_proof": False,
        "conditions": conditions,
        "legal_sufficiency": False,
        "proof_established": states.get("proof") == "proved",
    }


def _support_display_lines(support: Dict[str, Any]) -> List[str]:
    factual = support["factual_target"]
    requirement = support["law_derived_requirement"]
    lines = [
        f"Factual target: {factual['label']} [{factual['target_id']}]",
        (
            "Law-derived requirement: "
            f"{requirement['label']} [{requirement['requirement_id']}] "
            f"law_derived={requirement['law_derived']}"
        ),
    ]
    authorities = support["admitted_authorities"]
    if authorities:
        for item in authorities:
            lines.append(
                "Admitted authority: "
                f"citation={item['citation']}; version={item['version']}; span={item['span']}"
            )
    else:
        lines.append("Admitted authority: unknown")
    state_text = "; ".join(f"{name}={support['support_states'][name]}" for name in _SUPPORT_STATE_NAMES)
    lines.append(f"Support states: {state_text}")
    lines.append(
        f"Retrieval score: {support['retrieval_score']}. A retrieval score is not proof, corroboration, applicability, or admission."
    )
    for condition in support["conditions"]:
        lines.append(f"Condition {condition['kind']}: {condition['message']}")
        lines.append(f"Next action: {condition['next_action']}")
    rendered: List[str] = []
    budget = _WHY_DISPLAY_CHAR_BUDGET
    for line in lines:
        safe = line.encode("ascii", "replace").decode("ascii")
        if budget <= 0:
            rendered.append("Further support lines omitted to keep this explanation bounded.")
            break
        if len(safe) > budget:
            safe = safe[: max(0, budget - 3)] + "..."
        rendered.append(safe)
        budget -= len(safe) + 1
    return rendered


def public_why_diagnostic_receipt(why: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Codes and references only. Question text and narrative stay out of the receipt."""
    payload = why if isinstance(why, dict) else {}
    support = payload.get("question_support") if isinstance(payload.get("question_support"), dict) else {}
    factual = _mapping(support.get("factual_target"))
    requirement = _mapping(support.get("law_derived_requirement"))
    states = _mapping(support.get("support_states"))
    conditions = [item for item in (support.get("conditions") or []) if isinstance(item, dict)]
    authorities = [item for item in (support.get("admitted_authorities") or []) if isinstance(item, dict)]
    return {
        "schema": "why-diagnostic-receipt-v1",
        "command": "/why",
        "objective_id": _clip_public(payload.get("objective_id") or "unknown", 80) or "unknown",
        "target_id": _clip_public(payload.get("target_id") or "unknown", 80) or "unknown",
        "factual_target_id": _clip_public(factual.get("target_id") or "unknown", 80),
        "law_requirement_id": _clip_public(requirement.get("requirement_id") or "unknown", 80),
        "authority_status": "admitted" if authorities else "unknown",
        "authority_count": len(authorities),
        "authority_citations": [_clip_public(item.get("citation") or "unknown", 80) for item in authorities],
        "support_states": {name: _state_token(states.get(name)) for name in _SUPPORT_STATE_NAMES},
        "retrieval_score_is_proof": False,
        "condition_kinds": [str(item.get("kind") or "") for item in conditions],
        "next_actions": [str(item.get("next_action") or "") for item in conditions],
        "legal_sufficiency": False,
        "contains_private_content": False,
        "awaiting_user": True,
        "worker_stalled": False,
    }


def redact_diagnostic_value(value: Any) -> Any:
    """Drop private complaint text from a diagnostic receipt before it is shown."""
    if isinstance(value, dict):
        redacted: Dict[str, Any] = {}
        for key, item in value.items():
            if str(key).strip().lower() in _PRIVATE_DIAGNOSTIC_KEYS:
                continue
            redacted[str(key)] = redact_diagnostic_value(item)
        redacted.setdefault("contains_private_content", False)
        return redacted
    if isinstance(value, list):
        return [redact_diagnostic_value(item) for item in value[:20]]
    if isinstance(value, str):
        if len(value) > 180:
            return "[redacted]"
        return value
    return value


def format_terminal_why(inquiry: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Render a /why explanation a person can read without seeing ranking internals."""
    if not isinstance(inquiry, dict) or not (
        str(inquiry.get("question") or "").strip() or str(inquiry.get("why_it_matters") or "").strip()
    ):
        support = question_support_view({})
        display = (
            "There is no current question to explain. "
            "The interview is waiting for a selected gap, and this is not a stalled worker.\n"
            + "\n".join(_support_display_lines(support))
        )
        payload = {
            "command": "/why",
            "display": display,
            "stored_as_answer": False,
            "awaiting_user": True,
            "worker_stalled": False,
            "inquiry": None,
            "legal_sufficiency": False,
            "question_support": support,
        }
        payload["diagnostic_receipt"] = public_why_diagnostic_receipt(payload)
        return payload
    why = str(inquiry.get("why_it_matters") or inquiry.get("question_reason") or "").strip()
    if not why:
        why = "This question asks for information that is still missing from the complaint record."
    question = str(inquiry.get("question") or "").strip()
    objective_id = str(inquiry.get("objective_id") or "")
    target_id = str(inquiry.get("target_id") or inquiry.get("inquiry_id") or "")
    answer_contract = inquiry.get("expected_answer_contract") if isinstance(inquiry.get("expected_answer_contract"), dict) else {}
    update_contract = inquiry.get("expected_update_contract") if isinstance(inquiry.get("expected_update_contract"), dict) else {}
    expected = str(
        answer_contract.get("expected_information")
        or inquiry.get("expected_information")
        or "facts, dates, people, or documents you observed"
    ).strip()
    update_kind = str(update_contract.get("update_kind") or "record the answer against this target").replace("_", " ")
    support = question_support_view(inquiry)
    support_lines = "\n".join(_support_display_lines(support))
    display = (
        f"Why this question: {why}\n"
        f"Question: {question}\n"
        f"Objective id: {objective_id}\n"
        f"Target id: {target_id}\n"
        f"Expected answer: {expected}.\n"
        f"Expected update: {update_kind} for this target. "
        "An unknown, refused, or skipped answer is recorded as that response and does not satisfy the underlying legal requirement.\n"
        f"{support_lines}"
    )
    if len(display) > _WHY_DISPLAY_CHAR_BUDGET:
        display = display[: _WHY_DISPLAY_CHAR_BUDGET - 3] + "..."
    payload = {
        "command": "/why",
        "display": display,
        "stored_as_answer": False,
        "awaiting_user": True,
        "worker_stalled": False,
        "objective_id": objective_id,
        "target_id": target_id,
        "why_it_matters": why,
        "expected_answer_contract": answer_contract,
        "expected_update_contract": update_contract,
        "question_support": support,
        "legal_sufficiency": False,
    }
    payload["diagnostic_receipt"] = public_why_diagnostic_receipt(payload)
    return payload


MODULE_OWNERSHIP = require_module_ownership("complaint_phases.denoiser")
RUNTIME_ENTRYPOINT_ROLE = MODULE_OWNERSHIP.role

# Question types that are inherently non-specific and should bypass objective-key deduplication.
# These are open-ended or clarification asks that don't target a discrete legal element.
_BYPASS_DEDUPLICATION_QUESTION_TYPES: frozenset = frozenset({
    'clarification',
    'general',
    'open_ended',
    'open-ended',
    'general_intake_clarification',
})


def project_stopping_policy(
    stop: Optional[Dict[str, Any]] = None,
    *,
    paused: bool = False,
    needs_review: bool = False,
) -> Dict[str, Any]:
    """Public stopping outcome. Saturation never claims legal sufficiency or complete proof."""
    payload = stop if isinstance(stop, dict) else {}
    summary = payload.get("unresolved_issue_summary") if isinstance(payload.get("unresolved_issue_summary"), dict) else {}
    items = [item for item in (summary.get("items") or []) if isinstance(item, dict)]
    shortcuts = [str(item) for item in (summary.get("rejected_shortcuts") or [])]
    state = str(payload.get("state") or "").strip()
    try:
        open_count = int(summary.get("open_answerable_count") or 0)
    except (TypeError, ValueError):
        open_count = 0
    bound_hit = bool(
        {"repeat_attempt_bound", "no_information_bound", "model_retry_bound"} & set(shortcuts)
    )
    if paused or state == "paused":
        outcome = "paused"
    elif state in {"provider_unavailable", "blocked_provider"}:
        outcome = "blocked_provider"
    elif state in {"limit_reached", "no_progress", "cancelled"} or bound_hit:
        outcome = "no_progress"
    elif state == "needs_answer" and open_count == 0 and shortcuts:
        outcome = "no_progress"
    elif state == "needs_review" or (needs_review and open_count == 0):
        outcome = "needs_review"
    elif state in {"deferred_unknown", "deferred_needs_evidence"}:
        outcome = "deferred_needs_evidence"
    elif state == "saturated" and needs_review:
        outcome = "needs_review"
    elif state == "saturated" and payload.get("intake_complete") and not items:
        outcome = "complete"
    elif state == "saturated":
        outcome = "saturated"
    elif state == "needs_answer" or open_count:
        outcome = "awaiting_user"
    else:
        stored = str(payload.get("outcome") or "").strip()
        outcome = stored if stored in {
            "saturated", "complete", "paused", "awaiting_user",
            "deferred_needs_evidence", "blocked_provider", "no_progress", "needs_review",
        } else "awaiting_user"
    if paused:
        outcome = "paused"
    stalled = bool(payload.get("worker_stalled"))
    if stalled and outcome in {"awaiting_user", "paused"}:
        outcome = "no_progress"
    lane = str(payload.get("dependency_lane") or "").strip()
    standing = {
        "reason": "interview_stop_is_not_legal_sufficiency",
        "legal_sufficiency": False,
        "core_facts_complete": False,
        "proof_requirements_satisfied": False,
    }
    remaining = [standing, *items]
    next_actions = {
        "paused": "resume_when_user_returns",
        "awaiting_user": "answer_pending_question",
        "deferred_needs_evidence": "collect_evidence_then_resume",
        "blocked_provider": "retry_when_provider_available",
        "no_progress": "review_unresolved_issues_then_resume",
        "needs_review": "manual_review_then_resume",
        "saturated": "review_unresolved_issues_then_resume",
        "complete": "review_evidence_gaps_before_filing",
    }
    distinction = {
        "awaiting_user": "awaiting_user",
        "paused": "awaiting_user",
        "deferred_needs_evidence": "evidence_request",
        "blocked_provider": "unavailable_provider",
        "no_progress": "no_progress",
        "needs_review": "review",
        "saturated": "saturated",
        "complete": "complete",
    }.get(outcome, outcome or "awaiting_user")
    action = next_actions.get(outcome, "review_unresolved_issues_then_resume")
    concrete = {
        "source_research": "acquire_legal_sources",
        "evidence_request": "ingest_private_evidence",
        "review": "refresh_grounding",
    }
    if lane in concrete and outcome not in {"no_progress", "blocked_provider", "paused", "awaiting_user"}:
        distinction = lane
        action = concrete[lane]
    elif outcome == "saturated" and lane == "source_research":
        distinction = "source_research"
        action = concrete["source_research"]
    return {
        "outcome": outcome,
        "state": state or None,
        "dependency_lane": lane or None,
        "stopping_distinction": distinction,
        "operation_terminated": outcome == "no_progress",
        "busy_loop": False,
        "reads_developer_stdin": False,
        "remaining_issues": remaining,
        "unresolved_issue_summary": summary,
        "resumable_next_action": {
            "action": action,
            "resumable": outcome != "no_progress" or not stalled,
            "reason": outcome,
            "worker_stalled": stalled,
            "supervisory_restart": False,
            "reads_developer_stdin": False,
            "busy_loop": False,
        },
        "legal_sufficiency": False,
        "core_facts_complete": False,
        "proof_requirements_satisfied": False,
        "filing_ready": False,
        "intake_complete": bool(payload.get("intake_complete")) and outcome == "complete",
        "rejected_shortcuts": shortcuts,
    }


_DEPENDENCY_LANE_ALIASES = {
    "source_research": "source_research",
    "source": "source_research",
    "legal_source": "source_research",
    "authority": "source_research",
    "evidence_request": "evidence_request",
    "evidence": "evidence_request",
    "proof": "evidence_request",
    "review": "review",
    "contradiction": "review",
    "grounding": "review",
}
_DEPENDENCY_LANE_ACTIONS = {
    "source_research": "acquire_legal_sources",
    "evidence_request": "ingest_private_evidence",
    "review": "refresh_grounding",
}
MAX_DEPENDENCY_ACTION_ATTEMPTS = 3


def dependency_lane_for(item: Any) -> Optional[str]:
    """Map one open dependency to a source, evidence, or review lane."""
    if not isinstance(item, dict):
        return None
    for key in ("lane", "dependency_lane", "kind", "target_kind", "dependency_kind"):
        token = str(item.get(key) or "").strip().lower()
        if token in _DEPENDENCY_LANE_ALIASES:
            return _DEPENDENCY_LANE_ALIASES[token]
    disposition = str(item.get("disposition") or "").strip().lower()
    if disposition == "contradictory":
        return "review"
    if item.get("needs_legal_source") or item.get("legal_source_open"):
        return "source_research"
    if item.get("needs_evidence") or item.get("evidence_open"):
        return "evidence_request"
    if item.get("needs_review"):
        return "review"
    return None


def publish_authorized_dependency_action(
    stop: Optional[Dict[str, Any]],
    *,
    attempt: int = 0,
    context: Optional[Dict[str, Any]] = None,
    hook_completed: bool = False,
) -> Dict[str, Any]:
    """Publish one authorized next action, or terminate when the bound is spent.

    A completed hook, an empty question pool, and a stalled worker do not
    establish factual, legal, proof, or filing sufficiency. This function
    decides once. It does not loop and it does not read developer stdin.
    """
    payload = stop if isinstance(stop, dict) else {}
    if payload.get("stopping_distinction"):
        policy = payload
    else:
        policy = project_stopping_policy(payload)
    distinction = str(policy.get("stopping_distinction") or "")
    resumed = context if isinstance(context, dict) else {}
    try:
        used = int(attempt)
    except (TypeError, ValueError):
        used = 0
    if used < 0:
        used = 0
    resumable_context = {
        "case_id": resumed.get("case_id"),
        "target_id": resumed.get("target_id"),
        "target_revision": resumed.get("target_revision"),
        "graph_revision": resumed.get("graph_revision"),
        "session_revision": resumed.get("session_revision"),
        "attempt": used,
        "max_attempts": MAX_DEPENDENCY_ACTION_ATTEMPTS,
    }
    packet = {
        "legal_sufficiency": False,
        "core_facts_complete": False,
        "proof_requirements_satisfied": False,
        "filing_ready": False,
        "hook_completed": bool(hook_completed),
        "hook_completed_is_sufficiency": False,
        "busy_loop": False,
        "reads_developer_stdin": False,
        "worker_stalled": bool((policy.get("resumable_next_action") or {}).get("worker_stalled")),
        "awaiting_user": policy.get("outcome") in {"awaiting_user", "paused"} and not policy.get("operation_terminated"),
        "attempt": used,
        "max_attempts": MAX_DEPENDENCY_ACTION_ATTEMPTS,
        "resumable_context": resumable_context,
        "stopping_distinction": distinction or None,
        "operation": _DEPENDENCY_LANE_ACTIONS.get(distinction),
    }
    if policy.get("operation_terminated") or distinction in {"no_progress", "unavailable_provider"}:
        packet.update({
            "status": "terminated" if distinction == "no_progress" or policy.get("operation_terminated") else "unavailable",
            "published": False,
            "authorized": False,
            "awaiting_user": False,
            "operation_terminated": distinction == "no_progress" or bool(policy.get("operation_terminated")),
            "reason": distinction or "terminated",
        })
        return packet
    if distinction not in _DEPENDENCY_LANE_ACTIONS:
        packet.update({
            "status": "withheld",
            "published": False,
            "authorized": False,
            "operation": None,
            "reason": distinction or "awaiting_user",
        })
        return packet
    if used >= MAX_DEPENDENCY_ACTION_ATTEMPTS:
        packet.update({
            "status": "terminated",
            "published": False,
            "authorized": False,
            "awaiting_user": False,
            "operation_terminated": True,
            "reason": "attempt_bound",
        })
        return packet
    packet.update({
        "status": "published",
        "published": True,
        "authorized": True,
        "bounded": True,
        "action": _DEPENDENCY_LANE_ACTIONS[distinction],
        "operation": _DEPENDENCY_LANE_ACTIONS[distinction],
        "reason": distinction,
        "operation_terminated": False,
    })
    packet["resumable_context"]["attempt"] = used + 1
    packet["attempt"] = used + 1
    return packet


from . import denoiser_questions

class ComplaintDenoiser:
    """
    Denoises complaint information through iterative questioning.
    
    Uses knowledge graph gaps and dependency graph requirements to generate
    targeted questions that help clarify and complete the complaint.
    """
    
    def __init__(self, mediator=None):
        self.mediator = mediator
        self.questions_asked = []
        self.questions_pool = []
        self.source_operator_diagnostics: List[Dict[str, Any]] = []
        self.target_dispositions: Dict[str, str] = {}
        self.question_disposition_records: List[Dict[str, Any]] = []
        self._question_scope_revision = "standard-intake"
        self.objective_repeat_counts: Dict[str, int] = {}
        self.semantic_repeat_counts: Dict[str, int] = {}
        self.no_information_attempts = 0
        self.model_retry_count = 0
        self.presented_question_records: List[Dict[str, Any]] = []
        self._presented_inquiry_ids: Set[str] = set()
        self.explained_inquiry_pool: List[Dict[str, Any]] = []
        self.current_explained_inquiry: Optional[Dict[str, Any]] = None
        self.suppressed_semantic_duplicates: List[Dict[str, Any]] = []
        self.retired_explained_targets: Set[str] = set()

        # Optional “policy” knobs for SGD-style exploration.
        # Default is deterministic/no-randomness.
        self.exploration_epsilon = self._env_float("CG_DENOISER_EXPLORATION_EPSILON", 0.0)
        self.momentum_beta = self._env_float("CG_DENOISER_MOMENTUM_BETA", 0.85)
        self.momentum_enabled = self._env_bool("CG_DENOISER_MOMENTUM_ENABLED", False)
        self.exploration_enabled = self._env_bool("CG_DENOISER_EXPLORATION_ENABLED", False)
        self.exploration_top_k = int(self._env_float("CG_DENOISER_EXPLORATION_TOP_K", 3) or 3)
        self.stagnation_window = int(self._env_float("CG_DENOISER_STAGNATION_WINDOW", 4) or 4)
        self.stagnation_gain_threshold = float(self._env_float("CG_DENOISER_STAGNATION_GAIN_THRESHOLD", 0.5) or 0.5)
        self.actor_critic_enabled = self._env_bool("CG_DENOISER_ACTOR_CRITIC_ENABLED", True)
        self.actor_weight = self._env_float("CG_DENOISER_ACTOR_WEIGHT", 1.0)
        self.critic_weight = self._env_float("CG_DENOISER_CRITIC_WEIGHT", 1.0)
        self.question_quality_weight = self._env_float("CG_DENOISER_QUESTION_QUALITY_WEIGHT", 1.0)
        self.empathy_weight = self._env_float("CG_DENOISER_EMPATHY_WEIGHT", 1.0)
        self.selector_quality_guard_enabled = self._env_bool("CG_DENOISER_SELECTOR_QUALITY_GUARD_ENABLED", True)
        self.phase_focus_order = self._env_csv(
            "CG_DENOISER_PHASE_FOCUS_ORDER",
            ["graph_analysis", "document_generation", "intake_questioning"],
        )

        seed = os.getenv("CG_DENOISER_SEED")
        self._rng = random.Random(int(seed)) if seed and seed.isdigit() else random.Random()

        # Momentum state: EMA of “gain” by question type.
        self._type_gain_ema: Dict[str, float] = {}
        self._recent_gains: List[float] = []


    def _env_bool(self, key: str, default: bool) -> bool:
        raw = os.getenv(key)
        if raw is None:
            return default
        val = raw.strip().lower()
        if val in {"1", "true", "yes", "y", "on"}:
            return True
        if val in {"0", "false", "no", "n", "off"}:
            return False
        return default


    def _env_float(self, key: str, default: float) -> float:
        raw = os.getenv(key)
        if raw is None:
            return default
        try:
            return float(raw.strip())
        except Exception:
            return default


    def _env_csv(self, key: str, default: List[str]) -> List[str]:
        raw = os.getenv(key)
        if raw is None:
            return list(default)
        values = [str(item).strip().lower() for item in raw.split(",")]
        cleaned = [item for item in values if item]
        return cleaned or list(default)


    def _workflow_phase_for_question(
        self,
        question_type: str,
        context: Optional[Dict[str, Any]] = None,
        source: str = "",
    ) -> str:
        qtype = (question_type or "").strip().lower()
        source_name = (source or "").strip().lower()
        context = context if isinstance(context, dict) else {}
        gap_type = str(context.get("gap_type") or "").strip().lower()
        follow_up_focus = {
            "missing_exact_action_dates",
            "missing_hearing_request_date",
            "missing_response_dates",
            "missing_hearing_timing",
            "retaliation_missing_causation",
            "retaliation_missing_causation_link",
            "retaliation_missing_sequencing_dates",
            "retaliation_missing_sequence",
        }
        if (
            qtype in {"timeline", "contradiction", "responsible_party"}
            or gap_type in follow_up_focus
            or source_name in {"dependency_graph_contradiction", "dependency_graph_requirement"}
        ):
            return "graph_analysis"
        if qtype in {"evidence", "remedy"} or gap_type in {"missing_written_notice"}:
            return "document_generation"
        return "intake_questioning"


    def _phase_focus_rank(self, workflow_phase: str) -> int:
        phase = (workflow_phase or "").strip().lower()
        if phase in self.phase_focus_order:
            return self.phase_focus_order.index(phase)
        return len(self.phase_focus_order)


    def _derive_extraction_targets(
        self,
        question_type: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        qtype = (question_type or "").strip().lower()
        context = context if isinstance(context, dict) else {}
        targets: List[str] = []
        if qtype in {"timeline", "contradiction"}:
            targets.extend(["exact_dates", "event_order"])
        if qtype in {"responsible_party", "relationship", "requirement"}:
            targets.extend(["actor_name", "actor_role"])
        if qtype in {"evidence", "requirement"}:
            targets.extend(["document_type", "document_date", "document_owner"])
        if qtype in {"timeline", "responsible_party", "contradiction"}:
            targets.extend(["decision_maker", "adverse_action"])
        if qtype in {"impact", "remedy"}:
            targets.extend(["harm_type", "requested_outcome"])
        gap_type = str(context.get("gap_type") or "").strip().lower()
        if gap_type in {"missing_written_notice", "missing_response_dates"}:
            targets.extend(["notice_chain", "notice_date", "response_timing"])
        if gap_type in {"retaliation_missing_causation", "retaliation_missing_sequence", "retaliation_missing_sequencing_dates"}:
            targets.extend(["protected_activity", "adverse_action", "causation_link"])
        if gap_type in {"missing_decision_timeline", "missing_exact_action_dates", "missing_hearing_timing"}:
            targets.extend(["exact_dates", "event_order", "response_timing"])
        if gap_type in {"missing_staff_identity", "missing_staff_title"}:
            targets.extend(["actor_name", "actor_role", "decision_maker"])
        deduped: List[str] = []
        for target in targets:
            if target and target not in deduped:
                deduped.append(target)
        return deduped


    def _derive_patchability_markers(
        self,
        question_type: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        qtype = (question_type or "").strip().lower()
        context = context if isinstance(context, dict) else {}
        markers: List[str] = []
        if qtype in {"timeline", "contradiction"}:
            markers.append("chronology_patch_anchor")
        if qtype in {"responsible_party", "relationship"}:
            markers.append("actor_link_patch_anchor")
        if qtype in {"evidence", "requirement"}:
            markers.append("support_patch_anchor")
            markers.append("documentary_artifact_patch_anchor")
        if qtype in {"impact", "remedy"}:
            markers.append("relief_patch_anchor")
        if str(context.get("gap_type") or "").strip().lower() in {"missing_written_notice", "missing_response_dates"}:
            markers.append("notice_chain_patch_anchor")
            markers.append("chronology_response_patch_anchor")
        if qtype in {"responsible_party", "timeline"}:
            markers.append("decision_actor_patch_anchor")
        if qtype in {"timeline", "contradiction"}:
            markers.append("adverse_action_patch_anchor")
        return markers


    def _short_description(self, text_value: str, limit: int = 160) -> str:
        snippet = " ".join((text_value or "").strip().split())
        if len(snippet) > limit:
            return snippet[: limit - 3] + "..."
        return snippet


    def _extract_date_strings(self, text: str) -> List[str]:
        if not text:
            return []
        date_patterns = [
            r'\b(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|August|Sep|Sept|September|Oct|October|Nov|November|Dec|December)\s+\d{1,2},\s+\d{4}\b',
            r'\b(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|August|Sep|Sept|September|Oct|October|Nov|November|Dec|December)\s+\d{4}\b',
            r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',
            r'\b\d{4}-\d{2}-\d{2}\b',
            r'\b(?:in|on|since|during|around|by|from)\s+((?:19|20)\d{2})\b',
        ]
        found: List[str] = []
        for pattern in date_patterns:
            for match in re.findall(pattern, text):
                if isinstance(match, tuple):
                    match = match[0]
                value = (match or "").strip()
                if value and value not in found:
                    found.append(value)
        return found


    def _extract_org_candidates(self, text: str) -> List[str]:
        if not text:
            return []
        candidates: Set[str] = set()
        org_suffixes = (
            r"(?:Inc\.?|LLC|Ltd\.?|Co\.?|Corp\.?|Corporation|Company|University|"
            r"Hospital|School|Department|Dept\.?|Agency|Clinic|Bank|Foundation|"
            r"Association|Partners|Group|Systems|Services)"
        )
        for match in re.findall(
            rf"\b([A-Z][\w&.-]*(?:\s+[A-Z][\w&.-]*){{0,4}}\s+{org_suffixes})\b",
            text,
        ):
            candidates.add(match.strip())
        for match in re.findall(
            r"\b(?:at|for|with|from)\s+([A-Z][\w&.-]*(?:\s+[A-Z][\w&.-]*){0,4})\b",
            text or "",
        ):
            candidates.add(match.strip())

        lower_text = text.lower()
        if any(
            k in lower_text
            for k in [
                "property management",
                "property manager",
                "management company",
                "leasing office",
                "housing authority",
                "housing office",
            ]
        ):
            candidates.add("Property Management")
        if "employer" in lower_text:
            candidates.add("Employer")
        if any(
            k in lower_text
            for k in [
                "company",
                "organization",
                "business",
                "agency",
                "department",
                "school",
                "university",
                "hospital",
                "clinic",
            ]
        ):
            candidates.add("Organization")

        months = {
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
            "jan",
            "feb",
            "mar",
            "apr",
            "jun",
            "jul",
            "aug",
            "sep",
            "sept",
            "oct",
            "nov",
            "dec",
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        }
        banned = {"i", "we", "they", "he", "she", "it", "my", "our", "their", "the", "a", "an"}

        results: List[str] = []
        for candidate in sorted(candidates):
            cleaned = re.sub(r"[^\w&.\-\s]", "", candidate).strip()
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered in banned or lowered in months:
                continue
            tokens = cleaned.split()
            if len(tokens) == 1 and len(cleaned) < 4:
                continue
            results.append(cleaned)
        return results


    def _extract_named_role_people(self, text: str) -> List[Tuple[str, str]]:
        if not text:
            return []
        role_keywords = (
            r"manager|supervisor|boss|coworker|co-worker|hr|human resources|director|"
            r"owner|principal|teacher|professor|doctor|nurse|attorney|lawyer|agent|"
            r"officer|landlord|neighbor|representative"
        )
        results: List[Tuple[str, str]] = []
        for match in re.finditer(
            rf"\b(?:my|the|a|an)\s+(?P<role>{role_keywords})\s+(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){{0,2}})\b",
            text or "",
            re.IGNORECASE,
        ):
            role = (match.group("role") or "").strip().lower()
            name = (match.group("name") or "").strip()
            if name and role:
                results.append((name, role))
        return results


    def _extract_generic_roles(self, text: str) -> List[str]:
        if not text:
            return []
        lower_text = text.lower()
        roles = [
            "manager",
            "supervisor",
            "boss",
            "owner",
            "landlord",
            "hr",
            "human resources",
            "director",
            "agent",
            "representative",
            "officer",
            "employer",
            "company",
            "organization",
            "agency",
            "department",
            "school",
            "university",
            "hospital",
            "clinic",
        ]
        found: List[str] = []
        for role in roles:
            if role in lower_text and role not in found:
                found.append(role)
        return found


    def _contains_remedy_cue(self, text: str) -> bool:
        if not text:
            return False
        lowered = text.lower()
        cues = [
            "seeking",
            "seek",
            "would like",
            "looking for",
            "request",
            "asking for",
            "refund",
            "reimbursement",
            "compensation",
            "back pay",
            "repair",
            "fix",
            "replacement",
            "apology",
            "policy change",
        ]
        return any(cue in lowered for cue in cues)


    def _contains_confirmation_placeholder(self, text: str) -> bool:
        if not text:
            return False
        lowered = text.lower()
        placeholder_cues = [
            "needs confirmation",
            "need confirmation",
            "to be confirmed",
            "tbd",
            "unknown",
            "not sure",
            "unsure",
            "can't remember",
            "cannot remember",
            "i think",
            "maybe",
            "possibly",
        ]
        return any(cue in lowered for cue in placeholder_cues)


    def _contains_causation_signal(self, text: str) -> bool:
        if not text:
            return False
        lowered = text.lower()
        sequencing_terms = [
            "because",
            "after",
            "soon after",
            "due to",
            "in retaliation",
            "as a result",
            "right after",
        ]
        return any(term in lowered for term in sequencing_terms)

    def _contains_sequence_signal(self, text: str) -> bool:
        if not text:
            return False
        lowered = text.lower()
        sequence_terms = [
            "before",
            "after",
            "then",
            "next",
            "later",
            "earlier",
            "same day",
            "the next day",
            "following day",
            "in sequence",
            "timeline",
        ]
        return any(term in lowered for term in sequence_terms)

    def _extract_response_timing_phrases(self, text: str) -> List[str]:
        if not text:
            return []
        patterns = [
            r"\b(?:within|after|in)\s+\d+\s+(?:minute|minutes|hour|hours|day|days|week|weeks|month|months)\b",
            r"\b\d+\s+(?:minute|minutes|hour|hours|day|days|week|weeks|month|months)\s+(?:later|after|before)\b",
            r"\b(?:same day|next day|following day|immediately|right away|no response|never responded)\b",
        ]
        found: List[str] = []
        for pattern in patterns:
            for match in re.findall(pattern, text.lower()):
                normalized = str(match or "").strip()
                if normalized and normalized not in found:
                    found.append(normalized)
        return found

    def _contains_adverse_action_signal(self, text: str) -> bool:
        if not text:
            return False
        lowered = text.lower()
        signals = [
            "terminated",
            "termination",
            "fired",
            "demoted",
            "disciplined",
            "suspended",
            "evicted",
            "denied",
            "denial",
            "rejected",
            "threatened",
            "adverse steps",
            "status change",
            "status-change",
            "written up",
            "write-up",
            "adverse action",
        ]
        return any(token in lowered for token in signals)

    def _strip_markdown_formatting(self, text: str) -> str:
        cleaned = str(text or "")
        cleaned = re.sub(r"[*_`]+", "", cleaned)
        cleaned = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", cleaned)
        return " ".join(cleaned.strip().split())

    def _normalize_structured_timeline_field(self, value: str) -> str:
        cleaned = self._strip_markdown_formatting(value)
        cleaned = re.sub(r"^\s*[-*]+\s*", "", cleaned)
        return " ".join(cleaned.strip(" -:").split())

    def _normalize_structured_timeline_date(self, value: str) -> str:
        cleaned = self._normalize_structured_timeline_field(value)
        cleaned = re.sub(r"^(?:exact/estimated\s+)?date(?:\s+range)?\s*:\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^days since prior event\s*:\s*", "", cleaned, flags=re.IGNORECASE)
        lowered = cleaned.lower()
        placeholder_tokens = {"", "needs exact confirmation", "unknown", "n/a", "na", "tbd"}
        extracted_dates = self._extract_date_strings(cleaned)
        if extracted_dates:
            return extracted_dates[0]
        if lowered in placeholder_tokens:
            return ""
        normalized_without_parenthetical = re.sub(r"\([^()]*\)", "", cleaned).strip(" .")
        normalized_without_parenthetical = re.sub(
            r"\b(?:exact date|date|request date|response date)\s+(?:still )?(?:not |un)?confirmed\b",
            "",
            normalized_without_parenthetical,
            flags=re.IGNORECASE,
        ).strip(" .")
        lowered_without_parenthetical = normalized_without_parenthetical.lower()
        if normalized_without_parenthetical and lowered_without_parenthetical not in placeholder_tokens:
            if any(
                token in lowered_without_parenthetical
                for token in ("after ", "before ", "shortly after", "ongoing", "same day", "next day")
            ):
                return normalized_without_parenthetical
        if any(token in lowered for token in ("exact date still unconfirmed", "request date still", "response date unconfirmed")):
            return ""
        parenthetical = re.findall(r"\(([^()]+)\)", cleaned)
        for item in parenthetical:
            normalized_item = self._normalize_structured_timeline_field(item)
            normalized_item = re.sub(r"^best estimate\s*:\s*", "", normalized_item, flags=re.IGNORECASE)
            lowered_item = normalized_item.lower()
            if (
                normalized_item
                and lowered_item not in placeholder_tokens
                and "unconfirmed" not in lowered_item
                and "email copy" not in lowered_item
                and "portal" not in lowered_item
            ):
                return normalized_item
        if "ongoing" in lowered:
            return "ongoing"
        if "before " in lowered or "after " in lowered:
            return cleaned
        return ""

    def _infer_structured_timeline_predicate_family(
        self,
        actor_text: str,
        action_text: str,
        artifact_text: str,
    ) -> str:
        combined = " ".join(
            item for item in [actor_text, action_text, artifact_text] if str(item or "").strip()
        ).lower()
        if any(token in combined for token in ("responded", "response", "appeal-right", "appeal right", "no response")):
            return "response_timeline"
        if any(token in combined for token in ("hearing", "appeal", "review")) and any(
            token in combined for token in ("requested", "request", "asked", "submitted", "sought")
        ):
            return "hearing_process"
        if self._contains_adverse_action_signal(combined) or any(
            token in combined for token in ("status-change", "status change", "housing status", "adverse notice", "voucher status")
        ):
            return "adverse_action"
        if any(
            token in combined for token in ("raised concerns", "grievance process", "grievance", "complained", "reported", "protected activity")
        ):
            return "protected_activity"
        if self._contains_causation_signal(combined):
            return "causation"
        return "timeline"

    def _structured_timeline_event_label(self, predicate_family: str) -> str:
        labels = {
            "protected_activity": "Protected activity",
            "adverse_action": "Adverse action",
            "hearing_process": "Hearing request event",
            "response_timeline": "Response event",
            "notice_chain": "Notice communication",
            "causation": "Causation sequence",
        }
        return labels.get(predicate_family, "Timeline event")

    def _extract_structured_timeline_events(self, text: str) -> List[Dict[str, Any]]:
        if not text or "|" not in text:
            return []
        group_hash = hashlib.md5(self._strip_markdown_formatting(text).encode("utf-8")).hexdigest()[:10]
        events: List[Dict[str, Any]] = []
        candidate_lines: List[str] = []
        for raw_line in str(text).splitlines():
            line = str(raw_line or "").strip()
            if "|" in line and re.match(r"^\s*[-*]", line):
                candidate_lines.append(line)
        if not candidate_lines:
            flattened = str(text).replace("\n", " ")
            for match in re.finditer(r"(?:^|\s)([-*]\s*[^|]+?\|\s*.*?)(?=(?:\s[-*]\s*[^|]+?\|)|$)", flattened):
                candidate = str(match.group(1) or "").strip()
                if "|" in candidate:
                    candidate_lines.append(candidate)
        for line in candidate_lines:
            cleaned_line = self._normalize_structured_timeline_field(line)
            parts = []
            for part in cleaned_line.split("|"):
                normalized = self._normalize_structured_timeline_field(part)
                if normalized:
                    parts.append(normalized)
            if len(parts) < 2:
                continue
            actor_text = re.sub(r"^(?:who|actor)\s*:\s*", "", parts[0], flags=re.IGNORECASE).strip()
            action_text = re.sub(r"^action\s*:\s*", "", parts[1], flags=re.IGNORECASE).strip()
            trailing_parts = parts[2:]
            date_text = ""
            artifact_text = ""
            for part in trailing_parts:
                lowered = part.lower()
                if not date_text and ("date" in lowered or "ongoing" in lowered or "before " in lowered or "after " in lowered):
                    date_text = part
                    continue
                if not artifact_text and lowered.startswith("artifact"):
                    artifact_text = re.sub(r"^artifact\s*:\s*", "", part, flags=re.IGNORECASE).strip()
            normalized_date = self._normalize_structured_timeline_date(date_text)
            predicate_family = self._infer_structured_timeline_predicate_family(actor_text, action_text, artifact_text)
            event_label = self._structured_timeline_event_label(predicate_family)
            description = f"{actor_text} {action_text}".strip()
            if normalized_date:
                description = f"{description} ({normalized_date})"
            if artifact_text:
                description = f"{description}. Artifact: {artifact_text}"
            events.append(
                {
                    "event_id": f"structured_event_{group_hash}_{len(events) + 1:02d}",
                    "structured_timeline_group": f"structured_timeline_{group_hash}",
                    "sequence_index": len(events) + 1,
                    "actor_text": actor_text,
                    "action_text": action_text,
                    "artifact_text": artifact_text,
                    "event_date_or_range": normalized_date,
                    "predicate_family": predicate_family,
                    "event_label": event_label,
                    "description": description,
                    "source_line": cleaned_line,
                }
            )
        return events

    def _contains_document_precision_signal(self, text: str) -> bool:
        if not text:
            return False
        lowered = text.lower()
        has_doc = any(token in lowered for token in ("notice", "letter", "email", "message", "record", "memo"))
        has_sender = any(token in lowered for token in ("from ", "sent by", "signed by", "authored by", "issued by"))
        has_date = bool(self._extract_date_strings(text))
        return bool(has_doc and has_sender and has_date)


    def _contains_retaliation_context(self, text: str) -> bool:
        if not text:
            return False
        lowered = text.lower()
        retaliation_terms = [
            "retaliation",
            "protected activity",
            "complained",
            "reported",
            "adverse action",
            "discipline",
            "fired",
            "terminated",
            "demoted",
        ]
        return any(term in lowered for term in retaliation_terms)


    def _extract_document_mentions(self, text: str) -> List[str]:
        if not text:
            return []
        lowered = text.lower()
        documents = []
        doc_tokens = [
            ("termination letter", "Termination letter"),
            ("notice", "Notice"),
            ("letter", "Letter"),
            ("email", "Email"),
            ("text message", "Text message"),
            ("message", "Message"),
            ("voicemail", "Voicemail"),
            ("record", "Record"),
            ("policy", "Policy"),
            ("handbook", "Handbook"),
            ("write-up", "Write-up"),
            ("write up", "Write-up"),
            ("memo", "Memo"),
        ]
        for token, label in doc_tokens:
            if token in lowered and label not in documents:
                documents.append(label)
        return documents


    def _needs_exhibit_ready_document_questions(self) -> bool:
        mediator = self.mediator
        if mediator is None:
            return False
        build_gap_context = getattr(mediator, "build_inquiry_gap_context", None)
        if not callable(build_gap_context):
            return False
        try:
            gap_context = build_gap_context()
        except Exception:
            return False
        return bool(gap_context.get("needs_exhibit_grounding"))


    def _build_exhibit_ready_document_prompt(
        self,
        *,
        claim_label: str = "",
        include_policy_document: bool = False,
        include_file_evidence: bool = False,
        base_question: str = "",
    ) -> str:
        lowered = str(base_question or "").strip().lower()
        examples: List[str] = []
        if include_file_evidence:
            for token, label in (
                ("denial", "denial notice"),
                ("notice", "notice"),
                ("appeal", "appeal request"),
                ("hearing", "hearing request"),
                ("review", "review request"),
                ("email", "email"),
                ("message", "message"),
                ("attachment", "attachment"),
                ("lease", "lease or tenancy record"),
            ):
                if token in lowered and label not in examples:
                    examples.append(label)
            for fallback in ("denial notice", "email", "hearing or review request"):
                if fallback not in examples:
                    examples.append(fallback)
        if include_policy_document:
            for fallback in ("policy excerpt", "handbook section"):
                if fallback not in examples:
                    examples.append(fallback)
        if not examples:
            examples = ["denial notice", "email", "policy excerpt"]
        claim_phrase = f" for {claim_label.strip()}" if str(claim_label or "").strip() else ""
        return (
            f"Which uploaded or uploadable documents, such as {', '.join(examples[:4])}, should be treated as exhibits{claim_phrase}, "
            "and for each one what are the date, sender or source, label or subject line, and the fact the document proves?"
        )


    def _build_exhibit_ready_temporal_prompt(
        self,
        issue_type: str,
        *,
        claim_label: str = "",
        base_question: str = "",
    ) -> str:
        normalized_issue_type = str(issue_type or "").strip().lower()
        claim_phrase = f" for {claim_label.strip()}" if str(claim_label or "").strip() else ""
        if normalized_issue_type in {"missing_hearing_request_date", "missing_hearing_timing"}:
            return (
                f"What exhibit-ready documents, such as a hearing request, review request, confirmation email, or portal message, "
                f"fix the request date{claim_phrase}, and for each one what are the date, sender or source, label or subject line, "
                "and the fact the document proves?"
            )
        if normalized_issue_type in {"missing_response_dates", "missing_decision_timeline"}:
            return (
                f"What exhibit-ready documents, such as a denial notice, decision letter, response email, or review decision, "
                f"fix the response timeline{claim_phrase}, and for each one what are the date, sender or source, label or subject line, "
                "and the fact the document proves?"
            )
        if normalized_issue_type == "missing_written_notice":
            return (
                f"Which uploaded or uploadable notice documents should be treated as exhibits{claim_phrase}, "
                "and for each one what are the date, sender or source, label or subject line, and the fact the document proves?"
            )
        return self._build_exhibit_ready_document_prompt(
            claim_label=claim_label,
            include_policy_document="policy" in str(base_question or "").lower(),
            include_file_evidence=True,
            base_question=base_question,
        )


    def _append_unique_text_item(self, values: Any, text_value: str) -> List[str]:
        normalized_value = str(text_value or "").strip()
        if not normalized_value:
            return list(values) if isinstance(values, list) else []
        normalized_lower = normalized_value.lower()
        existing = [str(item).strip() for item in values] if isinstance(values, list) else []
        if normalized_lower not in {item.lower() for item in existing if item}:
            existing.append(normalized_value)
        return existing


    def _extract_named_people_with_titles(self, text: str) -> List[Tuple[str, str]]:
        if not text:
            return []
        results: List[Tuple[str, str]] = []
        patterns = [
            r"\b(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s*,\s*(?P<title>[A-Za-z][A-Za-z\s/&-]{2,60})\b",
            r"\b(?P<title>manager|supervisor|director|hr manager|hr specialist|hearing officer|appeals officer|landlord|owner)\s+(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text or "", flags=re.IGNORECASE):
                name = (match.group("name") or "").strip()
                title = (match.group("title") or "").strip().lower()
                if name and title:
                    results.append((name, title))
        deduped: List[Tuple[str, str]] = []
        seen = set()
        for name, title in results:
            key = (name.lower(), title.lower())
            if key in seen:
                continue
            seen.add(key)
            deduped.append((name, title))
        return deduped


    def _update_responsible_parties_from_answer(self,
                                               answer: str,
                                               knowledge_graph: KnowledgeGraph,
                                               updates: Dict[str, Any]) -> Dict[str, Any]:
        if not answer:
            return updates
        claims = knowledge_graph.get_entities_by_type("claim")
        claim_id = claims[0].id if len(claims) == 1 else None
        added_any = False

        for name, role in self._extract_named_role_people(answer):
            person, created = self._add_entity_if_missing(
                knowledge_graph,
                "person",
                name,
                {"role": role},
                0.7,
            )
            if created:
                updates["entities_updated"] += 1
            if claim_id and person:
                _, rel_created = self._add_relationship_if_missing(
                    knowledge_graph,
                    claim_id,
                    person.id,
                    "involves",
                    0.6,
                )
                if rel_created:
                    updates["relationships_added"] += 1
            added_any = True

        for name, title in self._extract_named_people_with_titles(answer):
            person, created = self._add_entity_if_missing(
                knowledge_graph,
                "person",
                name,
                {"role": title},
                0.72,
            )
            if created:
                updates["entities_updated"] += 1
            elif person and not str((person.attributes or {}).get("role") or "").strip():
                person.attributes["role"] = title
                updates["entities_updated"] += 1
            if claim_id and person:
                _, rel_created = self._add_relationship_if_missing(
                    knowledge_graph,
                    claim_id,
                    person.id,
                    "involves",
                    0.62,
                )
                if rel_created:
                    updates["relationships_added"] += 1
            added_any = True

        for org_name in self._extract_org_candidates(answer):
            org, created = self._add_entity_if_missing(
                knowledge_graph,
                "organization",
                org_name,
                {"role": "respondent"},
                0.6,
            )
            if created:
                updates["entities_updated"] += 1
            if claim_id and org:
                _, rel_created = self._add_relationship_if_missing(
                    knowledge_graph,
                    claim_id,
                    org.id,
                    "involves",
                    0.6,
                )
                if rel_created:
                    updates["relationships_added"] += 1
            added_any = True

        if not added_any:
            for role in self._extract_generic_roles(answer):
                role_norm = role.strip().lower()
                if role_norm in {"employer", "company", "organization", "agency", "department", "school", "university", "hospital", "clinic"}:
                    etype = "organization"
                    name = "Employer" if role_norm == "employer" else role_norm.title()
                    attrs = {"role": "respondent"}
                    confidence = 0.55
                else:
                    etype = "person"
                    name = "HR" if role_norm == "hr" else role_norm.title()
                    attrs = {"role": role_norm if role_norm != "human resources" else "hr"}
                    confidence = 0.55
                entity, created = self._add_entity_if_missing(
                    knowledge_graph,
                    etype,
                    name,
                    attrs,
                    confidence,
                )
                if created:
                    updates["entities_updated"] += 1
                if claim_id and entity:
                    _, rel_created = self._add_relationship_if_missing(
                        knowledge_graph,
                        claim_id,
                        entity.id,
                        "involves",
                        0.55,
                    )
                    if rel_created:
                        updates["relationships_added"] += 1
        return updates


    def _find_entity(self, knowledge_graph: KnowledgeGraph, etype: str, name: str) -> Optional[Entity]:
        etype_norm = (etype or "").strip().lower()
        name_norm = (name or "").strip().lower()
        if not etype_norm or not name_norm:
            return None
        for entity in knowledge_graph.entities.values():
            if entity.type.lower() == etype_norm and entity.name.strip().lower() == name_norm:
                return entity
        return None


    def _next_entity_id(self, knowledge_graph: KnowledgeGraph) -> str:
        max_id = 0
        for entity_id in knowledge_graph.entities.keys():
            match = re.match(r"entity_(\d+)$", str(entity_id))
            if match:
                max_id = max(max_id, int(match.group(1)))
        return f"entity_{max_id + 1}"


    def _next_relationship_id(self, knowledge_graph: KnowledgeGraph) -> str:
        max_id = 0
        for rel_id in knowledge_graph.relationships.keys():
            match = re.match(r"rel_(\d+)$", str(rel_id))
            if match:
                max_id = max(max_id, int(match.group(1)))
        return f"rel_{max_id + 1}"


    def _add_entity_if_missing(self,
                               knowledge_graph: KnowledgeGraph,
                               etype: str,
                               name: str,
                               attributes: Dict[str, Any],
                               confidence: float) -> Tuple[Optional[Entity], bool]:
        existing = self._find_entity(knowledge_graph, etype, name)
        if existing:
            return existing, False
        entity = Entity(
            id=self._next_entity_id(knowledge_graph),
            type=etype,
            name=name,
            attributes=attributes,
            confidence=confidence,
            source='complaint'
        )
        knowledge_graph.add_entity(entity)
        return entity, True


    def _add_relationship_if_missing(self,
                                    knowledge_graph: KnowledgeGraph,
                                    source_id: str,
                                    target_id: str,
                                    relation_type: str,
                                    confidence: float) -> Tuple[Optional[Relationship], bool]:
        if not (source_id and target_id and relation_type):
            return None, False
        for rel in knowledge_graph.relationships.values():
            if rel.source_id == source_id and rel.target_id == target_id and rel.relation_type == relation_type:
                return rel, False
        relationship = Relationship(
            id=self._next_relationship_id(knowledge_graph),
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            attributes={},
            confidence=confidence,
            source='complaint'
        )
        knowledge_graph.add_relationship(relationship)
        return relationship, True


    def get_policy_state(self) -> Dict[str, Any]:
        return {
            "exploration_enabled": bool(self.exploration_enabled),
            "exploration_epsilon": float(self.exploration_epsilon),
            "exploration_top_k": int(self.exploration_top_k),
            "momentum_enabled": bool(self.momentum_enabled),
            "momentum_beta": float(self.momentum_beta),
            "stagnation_window": int(self.stagnation_window),
            "stagnation_gain_threshold": float(self.stagnation_gain_threshold),
            "type_gain_ema": dict(self._type_gain_ema),
            "recent_gains": list(self._recent_gains[-10:]),
            "actor_critic_enabled": bool(self.actor_critic_enabled),
            "actor_weight": float(self.actor_weight),
            "critic_weight": float(self.critic_weight),
            "question_quality_weight": float(self.question_quality_weight),
            "empathy_weight": float(self.empathy_weight),
            "selector_quality_guard_enabled": bool(self.selector_quality_guard_enabled),
            "phase_focus_order": list(self.phase_focus_order),
        }


    def _compute_gain(self, updates: Dict[str, Any]) -> float:
        # A small heuristic: “did this question produce useful structured updates?”
        return float(
            (updates.get('entities_updated') or 0)
            + (updates.get('relationships_added') or 0)
            + (updates.get('requirements_satisfied') or 0)
        )


    def _update_momentum(self, question_type: str, gain: float) -> None:
        qtype = (question_type or "unknown").strip() or "unknown"
        prev = float(self._type_gain_ema.get(qtype, gain))
        beta = float(self.momentum_beta)
        beta = min(max(beta, 0.0), 0.999)
        self._type_gain_ema[qtype] = beta * prev + (1.0 - beta) * float(gain)


    def _maybe_increase_exploration_when_stuck(self) -> float:
        # If recent gains are consistently low, boost epsilon slightly.
        if self.stagnation_window <= 0:
            return float(self.exploration_epsilon)
        window = self._recent_gains[-self.stagnation_window :]
        if len(window) < self.stagnation_window:
            return float(self.exploration_epsilon)
        avg_gain = sum(window) / max(len(window), 1)
        if avg_gain <= self.stagnation_gain_threshold:
            return min(0.5, float(self.exploration_epsilon) + 0.1)
        return float(self.exploration_epsilon)


    def is_stagnating(self) -> bool:
        if self.stagnation_window <= 0:
            return False
        window = self._recent_gains[-self.stagnation_window :]
        if len(window) < self.stagnation_window:
            return False
        avg_gain = sum(window) / max(len(window), 1)
        return avg_gain <= self.stagnation_gain_threshold


    def _apply_exploration_and_momentum(self, questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not questions:
            return questions

        # Keep deterministic behavior unless explicitly enabled.
        if not (self.momentum_enabled or self.exploration_enabled):
            return questions

        # Momentum: reorder within the same priority bucket by EMA gain.
        priority_order = {'high': 0, 'medium': 1, 'low': 2}

        def score(q: Dict[str, Any]) -> float:
            qtype = (q.get('type') or 'unknown')
            return float(self._type_gain_ema.get(qtype, 0.0))

        # Group by priority to preserve the high/medium/low structure.
        grouped: Dict[int, List[Dict[str, Any]]] = {0: [], 1: [], 2: [], 3: []}
        for q in questions:
            grouped[priority_order.get(q.get('priority', 'low'), 3)].append(q)

        if self.momentum_enabled:
            for k in list(grouped.keys()):
                grouped[k].sort(key=score, reverse=True)

        merged: List[Dict[str, Any]] = []
        for k in sorted(grouped.keys()):
            merged.extend(grouped[k])

        # Exploration: with probability epsilon, swap the top question with another
        # from the top-K to encourage exploration.
        if self.exploration_enabled and self.exploration_top_k > 1:
            epsilon = self._maybe_increase_exploration_when_stuck()
            if self._rng.random() < max(0.0, min(1.0, epsilon)):
                k = min(int(self.exploration_top_k), len(merged))
                if k > 1:
                    j = self._rng.randrange(0, k)
                    merged[0], merged[j] = merged[j], merged[0]

        return merged

    def _normalize_question_text(self, text: str) -> str:
        return (text or "").strip().lower()

    def _normalize_question_objective_token(self, value: Any) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
        return cleaned

    def _question_similarity_tokens(self, text: str) -> Set[str]:
        stop_words = {
            "a", "an", "and", "are", "as", "at", "be", "by", "can", "did", "do", "does", "for",
            "from", "have", "how", "i", "in", "is", "it", "of", "on", "or", "please", "that",
            "the", "this", "to", "was", "were", "what", "when", "where", "which", "who", "why",
            "with", "you", "your",
        }
        return {
            token
            for token in re.findall(r"[a-z0-9]+", str(text or "").lower())
            if len(token) > 2 and token not in stop_words
        }

    def _question_text_similarity(self, left: str, right: str) -> float:
        left_tokens = self._question_similarity_tokens(left)
        right_tokens = self._question_similarity_tokens(right)
        if not left_tokens or not right_tokens:
            return 0.0
        overlap = len(left_tokens.intersection(right_tokens))
        union = len(left_tokens.union(right_tokens))
        return float(overlap) / float(max(union, 1))

    def _question_context(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        context = candidate.get("context") if isinstance(candidate, dict) else {}
        return context if isinstance(context, dict) else {}

    def _question_ranking_explanation(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        explanation = candidate.get("ranking_explanation") if isinstance(candidate, dict) else {}
        return explanation if isinstance(explanation, dict) else {}

    def _question_target_claim_type(self, candidate: Dict[str, Any]) -> str:
        context = self._question_context(candidate)
        explanation = self._question_ranking_explanation(candidate)
        return self._normalize_question_objective_token(
            candidate.get("target_claim_type")
            or context.get("claim_type")
            or context.get("claim_name")
            or explanation.get("target_claim_type")
        )

    def _question_target_element_id(self, candidate: Dict[str, Any]) -> str:
        context = self._question_context(candidate)
        explanation = self._question_ranking_explanation(candidate)
        return self._normalize_question_objective_token(
            candidate.get("target_element_id")
            or context.get("target_element_id")
            or context.get("claim_element_id")
            or context.get("requirement_id")
            or explanation.get("target_element_id")
        )

    def _question_gap_id(self, candidate: Dict[str, Any]) -> str:
        context = self._question_context(candidate)
        return self._normalize_question_objective_token(
            context.get("deterministic_update_key")
            or context.get("gap_id")
            or context.get("temporal_issue_id")
            or context.get("issue_id")
            or context.get("node_id")
        )

    def _question_expected_update_kind(self, candidate: Dict[str, Any]) -> str:
        context = self._question_context(candidate)
        explanation = self._question_ranking_explanation(candidate)
        return self._normalize_question_objective_token(
            candidate.get("expected_update_kind")
            or context.get("expected_update_kind")
            or explanation.get("expected_update_kind")
        )

    def _question_objective_value(self, candidate: Dict[str, Any]) -> str:
        context = self._question_context(candidate)
        explanation = self._question_ranking_explanation(candidate)
        return self._normalize_question_objective_token(
            candidate.get("question_objective")
            or context.get("question_objective")
            or explanation.get("question_objective")
            or candidate.get("type")
        )

    def _question_extraction_target_signature(self, candidate: Dict[str, Any]) -> str:
        context = self._question_context(candidate)
        targets = [
            self._normalize_question_objective_token(target)
            for target in (
                candidate.get("extraction_targets")
                or context.get("extraction_targets")
                or []
            )
            if str(target or "").strip()
        ]
        return "+".join(sorted(dict.fromkeys(targets))[:6])

    def _question_coverage_key(self, candidate: Dict[str, Any]) -> str:
        qtype = self._normalize_question_objective_token(candidate.get("type") if isinstance(candidate, dict) else "")
        claim_type = self._question_target_claim_type(candidate)
        element_id = self._question_target_element_id(candidate)
        gap_id = self._question_gap_id(candidate)
        update_kind = self._question_expected_update_kind(candidate)
        objective = self._question_objective_value(candidate)
        target_signature = self._question_extraction_target_signature(candidate)
        if element_id:
            return f"claim_element:{claim_type}:{element_id}"
        if gap_id:
            return f"gap:{claim_type}:{gap_id}"
        if target_signature:
            return f"targets:{claim_type}:{qtype}:{target_signature}"
        return f"objective:{claim_type}:{qtype}:{objective}:{update_kind}"

    def _question_objective_key(self, candidate: Dict[str, Any]) -> str:
        qtype = self._normalize_question_objective_token(candidate.get("type") if isinstance(candidate, dict) else "")
        objective = self._question_objective_value(candidate)
        claim_type = self._question_target_claim_type(candidate)
        element_id = self._question_target_element_id(candidate)
        gap_id = self._question_gap_id(candidate)
        update_kind = self._question_expected_update_kind(candidate)
        target_signature = self._question_extraction_target_signature(candidate)
        target_key = element_id or gap_id or target_signature or self._normalize_question_text(str(candidate.get("question", "")))[:80]
        return "|".join(
            value
            for value in (qtype, objective, claim_type, target_key, update_kind)
            if value
        )

    def _question_proof_objective_text(self, candidate: Dict[str, Any]) -> str:
        objective = str(candidate.get("question_objective") or "").strip() or "clarify the intake record"
        update_kind = str(candidate.get("expected_update_kind") or "").strip()
        claim_type = str(candidate.get("target_claim_type") or self._question_context(candidate).get("claim_type") or "").strip()
        element_id = str(candidate.get("target_element_id") or self._question_context(candidate).get("target_element_id") or "").strip()
        target_bits = []
        if claim_type:
            target_bits.append(claim_type.replace("_", " "))
        if element_id:
            target_bits.append(element_id.replace("_", " "))
        target_text = " / ".join(target_bits) if target_bits else "the current complaint record"
        update_text = f" and should {update_kind.replace('_', ' ')}" if update_kind else ""
        return f"{objective.replace('_', ' ')} for {target_text}{update_text}."

    def _expected_proof_gain_score(self, value: Any) -> float:
        if isinstance(value, (int, float)):
            return max(0.0, min(1.0, float(value)))
        normalized = str(value or "").strip().lower()
        if normalized in {"critical", "very_high", "very high"}:
            return 0.95
        if normalized == "high":
            return 0.82
        if normalized == "medium":
            return 0.56
        if normalized == "low":
            return 0.28
        try:
            return max(0.0, min(1.0, float(normalized)))
        except Exception:
            return 0.5

    def _iter_asked_question_payloads(self) -> List[Dict[str, Any]]:
        payloads: List[Dict[str, Any]] = []
        for item in self.questions_asked:
            if not isinstance(item, dict):
                continue
            question = item.get("question")
            if isinstance(question, dict):
                payloads.append(question)
            elif "type" in item or "question" in item:
                payloads.append(item)
        return payloads

    def _recent_question_objective_keys(self) -> Set[str]:
        return {
            self._question_objective_key(question)
            for question in self._iter_asked_question_payloads()
            if isinstance(question, dict)
        }

    def _candidate_novelty_metadata(
        self,
        candidate: Dict[str, Any],
        *,
        selected: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        selected = selected if isinstance(selected, list) else []
        candidate_text = str(candidate.get("question") or "")
        objective_key = self._question_objective_key(candidate)
        coverage_key = self._question_coverage_key(candidate)
        best_similarity = 0.0
        best_source = ""
        duplicate_objective = False

        for source_name, questions in (
            ("asked", self._iter_asked_question_payloads()),
            ("selected", selected),
        ):
            for existing in questions:
                if not isinstance(existing, dict):
                    continue
                if self._question_objective_key(existing) == objective_key:
                    duplicate_objective = True
                    best_source = source_name
                    best_similarity = max(best_similarity, 1.0)
                    continue
                similarity = self._question_text_similarity(candidate_text, str(existing.get("question") or ""))
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_source = source_name

        novelty_score = max(0.0, min(1.0, 1.0 - best_similarity))
        if duplicate_objective:
            novelty_score = min(novelty_score, 0.12)
        return {
            "novelty_score": round(float(novelty_score), 4),
            "max_similarity": round(float(best_similarity), 4),
            "duplicate_objective": bool(duplicate_objective),
            "nearest_source": best_source,
            "objective_key": objective_key,
            "coverage_key": coverage_key,
        }

    def _annotate_proof_directed_candidate(
        self,
        candidate: Dict[str, Any],
        *,
        selected: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        if not isinstance(candidate, dict):
            return candidate
        enriched = dict(candidate)
        explanation = dict(enriched.get("ranking_explanation", {}) if isinstance(enriched.get("ranking_explanation"), dict) else {})
        question_reason = str(enriched.get("question_reason") or explanation.get("question_reason") or "").strip()
        if not question_reason:
            question_reason = "This question targets a remaining proof objective in the intake record."
            enriched["question_reason"] = question_reason
        enriched.setdefault("priority_reason", question_reason)
        proof_objective_key = self._question_objective_key(enriched)
        coverage_key = self._question_coverage_key(enriched)
        proof_objective_text = str(enriched.get("proof_objective") or "").strip() or self._question_proof_objective_text(enriched)
        novelty = self._candidate_novelty_metadata(enriched, selected=selected)
        gain_score = self._expected_proof_gain_score(enriched.get("expected_proof_gain"))

        enriched["proof_objective"] = proof_objective_text
        enriched["proof_objective_id"] = proof_objective_key
        enriched["question_objective_key"] = proof_objective_key
        enriched["coverage_key"] = coverage_key
        enriched["novelty_score"] = float(novelty["novelty_score"])
        enriched["expected_proof_gain_score"] = gain_score
        enriched["proof_gain_metadata"] = {
            "expected_update_kind": str(enriched.get("expected_update_kind") or ""),
            "expected_proof_gain": str(enriched.get("expected_proof_gain") or ""),
            "expected_proof_gain_score": gain_score,
            "claim_criticality": str(enriched.get("claim_criticality") or explanation.get("claim_criticality") or ""),
            "contradiction_risk": "high" if str(enriched.get("type") or "").strip().lower() == "contradiction" else "normal",
            "novelty_score": float(novelty["novelty_score"]),
        }
        enriched["novelty_metadata"] = novelty

        explanation.setdefault("question_objective", str(enriched.get("question_objective") or ""))
        explanation["proof_objective"] = proof_objective_text
        explanation["proof_objective_id"] = proof_objective_key
        explanation["question_objective_key"] = proof_objective_key
        explanation["coverage_key"] = coverage_key
        explanation["question_reason"] = question_reason
        explanation["priority_reason"] = str(enriched.get("priority_reason") or "")
        explanation["expected_proof_gain"] = str(enriched.get("expected_proof_gain") or "")
        explanation["expected_proof_gain_score"] = gain_score
        explanation["novelty_score"] = float(novelty["novelty_score"])
        explanation["novelty_metadata"] = novelty
        enriched["ranking_explanation"] = explanation

        signals = dict(enriched.get("selector_signals", {}) if isinstance(enriched.get("selector_signals"), dict) else {})
        signals.setdefault("question_objective", str(enriched.get("question_objective") or ""))
        signals["proof_objective"] = proof_objective_text
        signals["proof_objective_id"] = proof_objective_key
        signals["question_objective_key"] = proof_objective_key
        signals["coverage_key"] = coverage_key
        signals["novelty_score"] = float(novelty["novelty_score"])
        signals["expected_proof_gain_score"] = gain_score
        enriched["selector_signals"] = signals
        return enriched

    def _select_proof_directed_candidates(
        self,
        candidates: List[Dict[str, Any]],
        *,
        max_questions: int,
        preserve_order: bool = True,
    ) -> List[Dict[str, Any]]:
        if max_questions <= 0:
            return []
        ordered = [candidate for candidate in (candidates or []) if isinstance(candidate, dict)]
        if not preserve_order:
            ordered.sort(key=self._default_candidate_sort_key)

        selected: List[Dict[str, Any]] = []
        seen_text_keys: Set[Tuple[str, str]] = set()
        seen_objective_keys: Set[str] = set(self._recent_question_objective_keys())
        selected_objective_keys: Set[str] = set()
        seen_coverage_keys: Set[str] = {
            self._question_coverage_key(question)
            for question in self._iter_asked_question_payloads()
            if isinstance(question, dict)
        }
        suppressed_duplicates: List[Dict[str, Any]] = []

        for raw_candidate in ordered:
            candidate = self._annotate_proof_directed_candidate(raw_candidate, selected=selected)
            qtype = self._normalize_question_objective_token(candidate.get("type"))
            text_key = (self._normalize_question_text(str(candidate.get("question", ""))), qtype)
            objective_key = str(candidate.get("question_objective_key") or self._question_objective_key(candidate))
            coverage_key = str(candidate.get("coverage_key") or self._question_coverage_key(candidate))
            bypass = qtype in _BYPASS_DEDUPLICATION_QUESTION_TYPES
            exact_duplicate = text_key in seen_text_keys
            repeated_objective = objective_key in seen_objective_keys or objective_key in selected_objective_keys
            semantic_duplicate = any(
                self._question_text_similarity(str(candidate.get("question") or ""), str(existing.get("question") or "")) >= 0.84
                for existing in selected
            )
            preserves_new_coverage = bool(coverage_key and coverage_key not in seen_coverage_keys)

            if exact_duplicate and not preserves_new_coverage:
                suppressed_duplicates.append(candidate)
                continue
            if not bypass and (repeated_objective or semantic_duplicate) and not preserves_new_coverage:
                suppressed_duplicates.append(candidate)
                continue

            seen_text_keys.add(text_key)
            selected_objective_keys.add(objective_key)
            if coverage_key:
                seen_coverage_keys.add(coverage_key)
            selected.append(candidate)
            if len(selected) >= max_questions:
                break

        for candidate in selected:
            signals = dict(candidate.get("selector_signals", {}) if isinstance(candidate.get("selector_signals"), dict) else {})
            signals["suppressed_duplicate_candidate_count"] = len(suppressed_duplicates)
            candidate["selector_signals"] = signals
            explanation = dict(candidate.get("ranking_explanation", {}) if isinstance(candidate.get("ranking_explanation"), dict) else {})
            explanation["suppressed_duplicate_candidate_count"] = len(suppressed_duplicates)
            candidate["ranking_explanation"] = explanation
        return selected[:max_questions]

    def _already_asked(self, question_text: str) -> bool:
        norm = self._normalize_question_text(question_text)
        for item in self.questions_asked:
            q = item.get('question') or {}
            if isinstance(q, dict):
                asked_text = q.get('question', '')
            else:
                asked_text = str(q)
            if self._normalize_question_text(asked_text) == norm:
                return True
        return False

    def _with_empathy(self, question_text: str, question_type: str) -> str:
        # Keep this lightweight so we improve tone without bloating prompts.
        text = (question_text or "").strip()
        if not text:
            return text
        normalized = text.lower()
        empathy_openers = (
            "to make sure i understand, ",
            "i know this may be stressful, and this helps keep your record accurate: ",
            "so we can support your claim clearly, ",
            "thanks for sharing this. ",
            "i hear you. ",
        )
        if normalized.startswith(empathy_openers):
            return text

        prefix = ""
        qtype = (question_type or "").strip().lower()
        if qtype in {'clarification', 'relationship', 'requirement'}:
            prefix = "To make sure I understand, "
        elif qtype in {'timeline', 'contradiction', 'responsible_party'}:
            prefix = "I know this may be stressful, and this helps keep your record accurate: "
        elif qtype in {'evidence'}:
            prefix = "So we can support your claim clearly, "
        elif qtype in {'impact', 'remedy'}:
            prefix = "Thanks for sharing this. "

        if prefix:
            if prefix.endswith(": "):
                return prefix + text[0].lower() + text[1:] if len(text) > 1 else prefix + text.lower()
            return prefix + text
        return text

    def _question_quality_bonus_candidate(self, candidate: Dict[str, Any]) -> float:
        if not isinstance(candidate, dict):
            return 0.0
        question_text = str(candidate.get('question') or '').strip().lower()
        follow_up_tags = [str(tag).strip().lower() for tag in (candidate.get('follow_up_tags') or []) if str(tag).strip()]
        extraction_targets = [str(target).strip().lower() for target in (candidate.get('extraction_targets') or []) if str(target).strip()]
        workflow_phase = str(candidate.get('workflow_phase') or '').strip().lower()
        score = 0.0
        if not question_text:
            return score
        if question_text.endswith("?"):
            score += 0.35
        if question_text.count("?") <= 1:
            score += 0.35
        if any(question_text.startswith(prefix) for prefix in ("what ", "when ", "who ", "which ", "where ", "how ")):
            score += 0.4
        if 45 <= len(question_text) <= 240:
            score += 0.35
        if 'exact_dates' in follow_up_tags and any(token in question_text for token in ('exact date', 'what date', 'when')):
            score += 0.5
        if 'staff_identity' in follow_up_tags and any(token in question_text for token in ('full name', 'title', 'role', 'who')):
            score += 0.5
        if 'notice_chain' in follow_up_tags and any(token in question_text for token in ('notice', 'letter', 'email', 'message', 'document')):
            score += 0.4
        if 'retaliation_sequence' in follow_up_tags and any(token in question_text for token in ('protected activity', 'adverse', 'because', 'after')):
            score += 0.5
        if 'chronology_gap' in follow_up_tags and any(token in question_text for token in ('exact date', 'in order', 'before', 'after', 'sequence', 'how long')):
            score += 0.55
        if 'decision_precision' in follow_up_tags and any(token in question_text for token in ('who exactly', 'full name', 'title', 'organization', 'adverse action')):
            score += 0.55
        if 'documentary_precision' in follow_up_tags and any(token in question_text for token in ('document type', 'date', 'sender', 'recipient', 'delivered')):
            score += 0.55
        if 'response_timing' in follow_up_tags and any(token in question_text for token in ('how long', 'within', 'response', 'responded')):
            score += 0.55
        if extraction_targets:
            covered = 0
            keyword_map = {
                'exact_dates': ('date', 'when'),
                'event_order': ('before', 'after', 'timeline', 'sequence'),
                'actor_name': ('who', 'name'),
                'actor_role': ('title', 'role'),
                'document_type': ('document', 'notice', 'letter', 'email', 'message', 'record'),
                'document_date': ('date', 'dated', 'when'),
                'document_owner': ('who sent', 'who wrote', 'who owns', 'from'),
                'protected_activity': ('protected activity', 'complained', 'reported'),
                'adverse_action': ('adverse action', 'adverse', 'discipline', 'fired', 'terminated', 'denied'),
                'causation_link': ('because', 'as a result', 'why'),
                'harm_type': ('harm', 'impact'),
                'requested_outcome': ('remedy', 'seeking', 'outcome'),
                'notice_chain': ('notice', 'letter', 'email', 'message'),
                'response_timing': ('how long', 'within', 'response', 'responded'),
                'decision_maker': ('who made', 'who approved', 'decision-maker', 'decision maker'),
            }
            for target in extraction_targets:
                target_tokens = keyword_map.get(target, ())
                if target_tokens and any(token in question_text for token in target_tokens):
                    covered += 1
            if covered:
                score += min(1.0, 0.25 * float(covered))
        score += max(0.0, 0.7 - 0.25 * float(self._phase_focus_rank(workflow_phase)))
        return score

    def _empathy_bonus_candidate(self, candidate: Dict[str, Any]) -> float:
        if not isinstance(candidate, dict):
            return 0.0
        qtype = str(candidate.get('type') or '').strip().lower()
        question_text = str(candidate.get('question') or '').strip().lower()
        empathy_openers = (
            "to make sure i understand, ",
            "i know this may be stressful, and this helps keep your record accurate: ",
            "so we can support your claim clearly, ",
            "thanks for sharing this. ",
            "i hear you. ",
        )
        has_empathy_frame = question_text.startswith(empathy_openers)
        if has_empathy_frame:
            if qtype in {'timeline', 'contradiction', 'responsible_party', 'impact', 'remedy', 'evidence'}:
                return 0.8
            return 0.5
        if qtype in {'timeline', 'contradiction', 'responsible_party', 'impact', 'remedy'}:
            return -0.25
        return 0.0

    def _phase1_proof_priority(self, question_type: str) -> int:
        objective_order = {
            'contradiction': 0,
            'timeline': 0,
            'responsible_party': 2,
            'impact': 3,
            'requirement': 4,
            'evidence': 5,
            'clarification': 6,
            'relationship': 7,
        }
        return objective_order.get((question_type or '').strip().lower(), 7)

    def _phase1_question_metadata(
        self,
        question_type: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = context or {}
        qtype = (question_type or '').strip().lower()

        if qtype == 'timeline':
            return {
                'question_objective': 'establish_chronology',
                'question_reason': 'Chronology is necessary to determine sequence, notice, and causation.',
                'expected_proof_gain': 'high',
                'proof_priority': self._phase1_proof_priority(qtype),
            }
        if qtype == 'contradiction':
            contradiction_label = str(context.get('contradiction_label') or 'the conflicting facts')
            return {
                'question_objective': 'resolve_factual_contradiction',
                'question_reason': f"The intake record contains conflicting information about {contradiction_label} that should be reconciled before relying on it.",
                'expected_proof_gain': 'high',
                'proof_priority': self._phase1_proof_priority(qtype),
            }
        if qtype == 'responsible_party':
            return {
                'question_objective': 'identify_responsible_party',
                'question_reason': 'The complaint needs a concrete actor or organization tied to the alleged conduct.',
                'expected_proof_gain': 'high',
                'proof_priority': self._phase1_proof_priority(qtype),
            }
        if qtype == 'impact':
            return {
                'question_objective': 'capture_harm_and_requested_remedy',
                'question_reason': 'The intake record should state both the harm suffered and the outcome being sought.',
                'expected_proof_gain': 'high',
                'proof_priority': self._phase1_proof_priority(qtype),
            }
        if qtype == 'requirement':
            requirement_name = str(context.get('requirement_name') or 'this claim element')
            claim_name = str(context.get('claim_name') or 'the claim')
            return {
                'question_objective': 'satisfy_claim_requirement',
                'question_reason': f"{requirement_name} is still missing for {claim_name}.",
                'expected_proof_gain': 'high',
                'proof_priority': self._phase1_proof_priority(qtype),
            }
        if qtype == 'evidence':
            claim_name = str(context.get('claim_name') or 'the claim')
            return {
                'question_objective': 'identify_supporting_evidence',
                'question_reason': f"{claim_name} still needs supporting proof leads or corroborating evidence.",
                'expected_proof_gain': 'high',
                'proof_priority': self._phase1_proof_priority(qtype),
            }
        if qtype == 'clarification':
            entity_name = str(context.get('entity_name') or 'this fact')
            return {
                'question_objective': 'clarify_low_confidence_fact',
                'question_reason': f"The current record about {entity_name} is too uncertain to rely on safely.",
                'expected_proof_gain': 'medium',
                'proof_priority': self._phase1_proof_priority(qtype),
            }
        if qtype == 'relationship':
            entity_name = str(context.get('entity_name') or 'this entity')
            return {
                'question_objective': 'connect_parties_and_facts',
                'question_reason': f"{entity_name} needs clearer linkage to the complaint narrative.",
                'expected_proof_gain': 'medium',
                'proof_priority': self._phase1_proof_priority(qtype),
            }

        return {
            'question_objective': 'general_intake_clarification',
            'question_reason': 'This question helps fill a remaining intake gap.',
            'expected_proof_gain': 'medium',
            'proof_priority': self._phase1_proof_priority(qtype),
        }

    def _phase1_question_targeting(
        self,
        question_type: str,
        context: Optional[Dict[str, Any]] = None,
        source: str = '',
    ) -> Dict[str, Any]:
        """Attach section-aware routing metadata to phase-1 intake questions."""
        context = context or {}
        qtype = (question_type or '').strip().lower()

        defaults = {
            'phase1_section': 'general',
            'target_claim_type': str(context.get('claim_type') or ''),
            'target_element_id': str(context.get('requirement_id') or context.get('target_element_id') or ''),
            'target_fact_type': '',
            'blocking_level': 'important',
            'expected_update_kind': 'clarify_record',
        }

        if qtype == 'contradiction':
            defaults.update({
                'phase1_section': 'contradictions',
                'target_fact_type': 'contradicted_fact',
                'blocking_level': 'blocking',
                'expected_update_kind': 'resolve_contradiction',
            })
        elif qtype == 'timeline':
            defaults.update({
                'phase1_section': 'chronology',
                'target_fact_type': 'timeline',
                'blocking_level': 'blocking',
                'expected_update_kind': 'add_timeline_fact',
            })
        elif qtype == 'responsible_party':
            defaults.update({
                'phase1_section': 'actors',
                'target_fact_type': 'responsible_party',
                'blocking_level': 'blocking',
                'expected_update_kind': 'identify_actor',
            })
        elif qtype == 'impact':
            defaults.update({
                'phase1_section': 'harm_remedy',
                'target_fact_type': 'impact_or_remedy',
                'blocking_level': 'important',
                'expected_update_kind': 'capture_harm_or_remedy',
            })
        elif qtype == 'requirement':
            defaults.update({
                'phase1_section': 'claim_elements',
                'target_fact_type': 'claim_element',
                'blocking_level': 'blocking',
                'expected_update_kind': 'satisfy_claim_element',
            })
        elif qtype == 'evidence':
            defaults.update({
                'phase1_section': 'proof_leads',
                'target_fact_type': 'proof_lead',
                'blocking_level': 'important',
                'expected_update_kind': 'capture_proof_lead',
            })
        elif qtype == 'relationship':
            defaults.update({
                'phase1_section': 'actors',
                'target_fact_type': 'relationship',
                'blocking_level': 'important',
                'expected_update_kind': 'link_parties',
            })
        elif qtype == 'clarification':
            defaults.update({
                'phase1_section': 'general',
                'target_fact_type': 'uncertain_fact',
                'blocking_level': 'informational',
                'expected_update_kind': 'clarify_fact',
            })

        if not defaults['target_claim_type']:
            defaults['target_claim_type'] = str(context.get('claim_name') or '')
        workflow_phase = str(context.get('workflow_phase') or '').strip().lower() or self._workflow_phase_for_question(qtype, context=context, source=source)
        defaults['workflow_phase'] = workflow_phase
        defaults['workflow_phase_rank'] = int(context.get('workflow_phase_rank', self._phase_focus_rank(workflow_phase)) or self._phase_focus_rank(workflow_phase))
        context_targets = [str(target).strip() for target in (context.get('extraction_targets') or []) if str(target).strip()]
        context_markers = [str(marker).strip() for marker in (context.get('patchability_markers') or []) if str(marker).strip()]
        defaults['extraction_targets'] = context_targets or self._derive_extraction_targets(qtype, context=context)
        defaults['patchability_markers'] = context_markers or self._derive_patchability_markers(qtype, context=context)
        if context.get('recommended_resolution_lane'):
            defaults['recommended_resolution_lane'] = str(context.get('recommended_resolution_lane') or '')

        return defaults

    def _build_phase1_question(
        self,
        *,
        question_type: str,
        question_text: str,
        context: Optional[Dict[str, Any]] = None,
        priority: str = 'medium',
        question_intent: Optional[Dict[str, Any]] = None,
        source: str = '',
    ) -> Dict[str, Any]:
        normalized_intent = question_intent if isinstance(question_intent, dict) else None
        payload = {
            'type': question_type,
            'question': render_question_text_from_intent(normalized_intent) if normalized_intent else question_text,
            'context': context or {},
            'priority': priority,
        }
        if normalized_intent:
            payload['question_intent'] = normalized_intent
            payload['question_goal'] = str(normalized_intent.get('question_goal') or '')
            payload['question_strategy'] = str(normalized_intent.get('question_strategy') or '')
        payload.update(self._phase1_question_metadata(question_type, payload['context']))
        payload.update(self._phase1_question_targeting(question_type, payload['context'], source=source))
        return payload

    def _question_candidate(
        self,
        *,
        source: str,
        question_type: str,
        question_text: str,
        context: Optional[Dict[str, Any]] = None,
        priority: str = 'medium',
        question_intent: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        question_payload = self._build_phase1_question(
            question_type=question_type,
            question_text=question_text,
            context=context,
            priority=priority,
            question_intent=question_intent,
            source=source,
        )
        if str(question_text or '').strip():
            question_payload['question'] = str(question_text).strip()
        question_payload['candidate_source'] = source
        follow_up_tags = self._question_follow_up_tags(
            question_type=question_type,
            question_text=str(question_payload.get('question') or question_text or ''),
            context=question_payload.get('context'),
        )
        question_payload['follow_up_tags'] = follow_up_tags
        question_payload['ranking_explanation'] = {
            'candidate_source': source,
            'priority': str(question_payload.get('priority') or priority or 'medium'),
            'proof_priority': int(question_payload.get('proof_priority', self._phase1_proof_priority(question_type))),
            'blocking_level': str(question_payload.get('blocking_level') or ''),
            'phase1_section': str(question_payload.get('phase1_section') or ''),
            'question_objective': str(question_payload.get('question_objective') or ''),
            'question_reason': str(question_payload.get('question_reason') or ''),
            'question_goal': str(question_payload.get('question_goal') or question_payload.get('question_objective') or ''),
            'question_strategy': str(question_payload.get('question_strategy') or 'default_generation'),
            'target_claim_type': str(question_payload.get('target_claim_type') or ''),
            'target_element_id': str(question_payload.get('target_element_id') or ''),
            'target_fact_type': str(question_payload.get('target_fact_type') or ''),
            'expected_update_kind': str(question_payload.get('expected_update_kind') or ''),
            'expected_proof_gain': str(question_payload.get('expected_proof_gain') or ''),
            'recommended_resolution_lane': str(question_payload.get('recommended_resolution_lane') or ''),
            'workflow_phase': str(question_payload.get('workflow_phase') or ''),
            'workflow_phase_rank': int(question_payload.get('workflow_phase_rank')) if question_payload.get('workflow_phase_rank') is not None else 99,
            'extraction_targets': list(question_payload.get('extraction_targets') or []),
            'patchability_markers': list(question_payload.get('patchability_markers') or []),
            'follow_up_tags': list(follow_up_tags),
        }
        return self._bind_unresolved_target(self._annotate_proof_directed_candidate(question_payload))

    def _question_follow_up_tags(
        self,
        *,
        question_type: str,
        question_text: str,
        context: Optional[Dict[str, Any]],
    ) -> List[str]:
        tags: List[str] = []
        normalized_text = (question_text or "").lower()
        context = context if isinstance(context, dict) else {}
        gap_type = str(context.get('gap_type') or '').strip().lower()

        if gap_type in {'missing_exact_action_dates', 'missing_hearing_request_date', 'missing_response_dates', 'missing_hearing_timing'}:
            tags.append('exact_dates')
        if gap_type in {'missing_staff_identity', 'missing_staff_title'}:
            tags.append('staff_identity')
        if gap_type in {'missing_written_notice'}:
            tags.append('notice_chain')
        if gap_type in {'retaliation_missing_causation', 'retaliation_missing_causation_link', 'retaliation_missing_sequencing_dates', 'retaliation_missing_sequence'}:
            tags.append('retaliation_sequence')
        if gap_type in {'missing_exact_action_dates', 'missing_decision_timeline', 'missing_hearing_timing', 'missing_response_dates'}:
            tags.append('chronology_gap')
        if gap_type in {'missing_staff_identity', 'missing_staff_title'}:
            tags.append('decision_precision')
        if gap_type in {'missing_written_notice', 'missing_response_dates'}:
            tags.append('documentary_precision')

        if any(token in normalized_text for token in ('exact date', 'on what date', 'when did')):
            tags.append('exact_dates')
        if any(token in normalized_text for token in ('full name', 'title', 'role', 'who specifically')):
            tags.append('staff_identity')
        if any(token in normalized_text for token in ('notice', 'letter', 'email', 'message')):
            tags.append('notice_chain')
        if any(token in normalized_text for token in ('protected activity', 'adverse action', 'because of', 'soon after')):
            tags.append('retaliation_sequence')
        if any(token in normalized_text for token in ('sequence', 'before', 'after', 'timeline', 'order')):
            tags.append('chronology_gap')
        if any(token in normalized_text for token in ('decision-maker', 'decision maker', 'approved', 'communicated it')):
            tags.append('decision_precision')
        if any(token in normalized_text for token in ('document', 'message', 'email', 'who sent', 'dated')):
            tags.append('documentary_precision')
        if any(token in normalized_text for token in ('how long', 'within how many', 'response time', 'responded')):
            tags.append('response_timing')

        if question_type in {'timeline'} and 'exact_dates' not in tags:
            tags.append('timeline')
        deduped: List[str] = []
        for tag in tags:
            if tag and tag not in deduped:
                deduped.append(tag)
        return deduped

    def _build_contradiction_questions(
        self,
        dependency_graph: DependencyGraph,
        max_questions: int,
    ) -> List[Dict[str, Any]]:
        questions: List[Dict[str, Any]] = []
        seen_pairs: Set[str] = set()

        for dependency in dependency_graph.dependencies.values():
            dependency_type = getattr(dependency, 'dependency_type', None)
            dependency_type_value = getattr(dependency_type, 'value', str(dependency_type or '')).lower()
            if dependency_type_value != 'contradicts':
                continue

            left_node = dependency_graph.get_node(dependency.source_id)
            right_node = dependency_graph.get_node(dependency.target_id)
            left_name = left_node.name if left_node else dependency.source_id
            right_name = right_node.name if right_node else dependency.target_id
            pair_key = '|'.join(sorted([str(left_name), str(right_name)]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            contradiction_label = f"{left_name} and {right_name}"
            questions.append(self._question_candidate(
                source='dependency_graph_contradiction',
                question_type='contradiction',
                question_text=(
                    f"I have conflicting information about {left_name} and {right_name}. "
                    "What do you recall about each account, and what dates, documents, or records can you provide?"
                ),
                context={
                    'left_node_id': dependency.source_id,
                    'right_node_id': dependency.target_id,
                    'left_node_name': left_name,
                    'right_node_name': right_name,
                    'contradiction_label': contradiction_label,
                },
                priority='high',
            ))
            if len(questions) >= max_questions:
                break

        return questions

    def _build_claim_element_questions(
        self,
        intake_case_file: Optional[Dict[str, Any]],
        max_questions: int,
    ) -> List[Dict[str, Any]]:
        """Build questions from missing registry-backed claim elements in the intake case file."""
        if not isinstance(intake_case_file, dict):
            return []

        questions: List[Dict[str, Any]] = []
        seen_keys: Set[str] = set()
        exhibit_ready_documents = self._needs_exhibit_ready_document_questions()
        candidate_claims = intake_case_file.get('candidate_claims', [])
        if not isinstance(candidate_claims, list):
            return []

        def _expected_modalities(evidence_classes: List[str]) -> List[str]:
            values = [str(item or '').strip().lower() for item in evidence_classes if str(item or '').strip()]
            modalities: List[str] = []
            if any(token in values for token in ('policy', 'handbook')):
                modalities.append('policy_document')
            if any(
                token in values
                for token in (
                    'lease', 'denial_notice', 'termination_notice', 'eviction_notice', 'application_record',
                    'inspection_record', 'maintenance_record', 'rent_record', 'personnel_record',
                )
            ):
                modalities.append('file_evidence')
            if any(token in values for token in ('email', 'text_message', 'landlord_message', 'denial_message')):
                if 'file_evidence' not in modalities:
                    modalities.append('file_evidence')
            return modalities

        def _targets_for_element(element_id: str, modalities: List[str]) -> List[str]:
            normalized_element = str(element_id or '').strip().lower()
            targets: List[str] = ['actor_name', 'actor_role']
            element_target_map = {
                'protected_trait': ['harm_type'],
                'housing_context': ['actor_name', 'actor_role', 'decision_maker'],
                'employment_relationship': ['actor_name', 'actor_role', 'decision_maker'],
                'adverse_action': ['adverse_action', 'exact_dates', 'event_order'],
                'discriminatory_motive': ['causation_link', 'event_order'],
                'causation': ['protected_activity', 'adverse_action', 'causation_link', 'exact_dates', 'event_order'],
            }
            targets.extend(element_target_map.get(normalized_element, []))
            if 'policy_document' in modalities:
                targets.extend(['document_type', 'document_owner'])
            if 'file_evidence' in modalities:
                targets.extend(['document_type', 'document_date', 'document_owner'])
            deduped: List[str] = []
            for item in targets:
                if item and item not in deduped:
                    deduped.append(item)
            return deduped

        def _patchability_for_element(element_id: str, modalities: List[str]) -> List[str]:
            normalized_element = str(element_id or '').strip().lower()
            markers = ['claim_element_patch_anchor', 'support_patch_anchor']
            if normalized_element in {'housing_context', 'employment_relationship'}:
                markers.append('actor_link_patch_anchor')
            if normalized_element in {'adverse_action', 'causation'}:
                markers.append('chronology_patch_anchor')
            if 'policy_document' in modalities:
                markers.append('policy_document_patch_anchor')
            if 'file_evidence' in modalities:
                markers.append('documentary_artifact_patch_anchor')
            deduped: List[str] = []
            for item in markers:
                if item and item not in deduped:
                    deduped.append(item)
            return deduped

        for claim in candidate_claims:
            if not isinstance(claim, dict):
                continue
            claim_type = normalize_claim_type(str(claim.get('claim_type') or '').strip())
            claim_label = str(claim.get('label') or claim_type or 'this claim').strip()
            weak_claim_focus = claim_type in {'housing_discrimination', 'hacc_research_engine'}
            for element in claim.get('required_elements', []) or []:
                if not isinstance(element, dict):
                    continue
                element_status = str(element.get('status') or '').strip().lower()
                if element_status in {'present', 'satisfied', 'complete'}:
                    continue
                element_id = str(element.get('element_id') or '').strip()
                element_label = str(element.get('label') or element_id or 'this missing element').strip()
                question_key = f"{claim_type}:{element_id}:{element_label}".lower()
                if question_key in seen_keys:
                    continue
                seen_keys.add(question_key)
                evidence_classes = list(element.get('evidence_classes', []) or [])
                actor_roles = list(element.get('actor_roles', []) or [])
                expected_modalities = _expected_modalities(evidence_classes)
                extraction_targets = _targets_for_element(element_id, expected_modalities)
                patchability_markers = _patchability_for_element(element_id, expected_modalities)
                gap_id = f"{claim_type}:{element_id}".lower()
                question_intent = build_claim_element_question_intent(
                    claim_type,
                    claim_label,
                    {
                        'element_id': element_id,
                        'label': element_label,
                        'blocking': bool(element.get('blocking', False)),
                        'actor_roles': actor_roles,
                        'evidence_classes': evidence_classes,
                    },
                )
                question_text = build_claim_element_question_text(
                    claim_type,
                    claim_label,
                    element_id,
                    element_label,
                )
                if exhibit_ready_documents and (
                    'policy_document' in expected_modalities or 'file_evidence' in expected_modalities
                ):
                    question_text = self._build_exhibit_ready_document_prompt(
                        claim_label=claim_label,
                        include_policy_document='policy_document' in expected_modalities,
                        include_file_evidence='file_evidence' in expected_modalities,
                        base_question=question_text,
                    )
                elif 'policy_document' in expected_modalities and 'file_evidence' in expected_modalities:
                    question_text = (
                        f"{question_text} If available, identify one policy document and one file record "
                        "(notice, lease, email, or upload) with date and sender."
                    )
                elif 'policy_document' in expected_modalities:
                    question_text = (
                        f"{question_text} If available, identify the policy document (name/section) and who issued it."
                    )
                elif 'file_evidence' in expected_modalities:
                    question_text = (
                        f"{question_text} If available, identify one file record (notice, lease, email, or upload) with date and sender."
                    )
                if not self._already_asked(question_text):
                    questions.append(self._question_candidate(
                        source='intake_claim_element_gap',
                        question_type='requirement',
                        question_text=question_text,
                        context={
                            'claim_type': claim_type,
                            'claim_name': claim_label,
                            'requirement_id': element_id,
                            'requirement_name': element_label,
                            'target_element_id': element_id,
                            'gap_id': gap_id,
                            'gap_type': 'missing_claim_element',
                            'requirement_key': element_id,
                            'actor_roles': actor_roles,
                            'evidence_classes': evidence_classes,
                            'expected_evidence_modalities': expected_modalities,
                            'deterministic_update_key': gap_id,
                            'workflow_phase': 'graph_analysis' if (bool(element.get('blocking', False)) or weak_claim_focus) else 'intake_questioning',
                            'recommended_resolution_lane': 'structured_requirement_capture',
                            'extraction_targets': extraction_targets,
                            'patchability_markers': patchability_markers,
                        },
                        priority='high' if (bool(element.get('blocking', False)) or weak_claim_focus) else 'medium',
                        question_intent=question_intent,
                    ))
                if len(questions) >= max_questions:
                    return questions[:max_questions]

        return questions

    def _build_proof_lead_questions(
        self,
        intake_case_file: Optional[Dict[str, Any]],
        max_questions: int,
    ) -> List[Dict[str, Any]]:
        """Build claim-aware proof-lead questions when the intake still lacks support sources."""
        if not isinstance(intake_case_file, dict) or max_questions <= 0:
            return []

        proof_leads = intake_case_file.get('proof_leads', [])
        existing_policy_doc = False
        existing_file_evidence = False
        if isinstance(proof_leads, list):
            for lead in proof_leads:
                if not isinstance(lead, dict):
                    continue
                lead_text = " ".join(
                    str(lead.get(field) or '').strip().lower()
                    for field in ('lead_type', 'description', 'expected_format', 'recommended_support_kind', 'source_quality_target')
                )
                if any(token in lead_text for token in ('policy', 'handbook', 'rule', 'criteria')):
                    existing_policy_doc = True
                if any(token in lead_text for token in ('file', 'pdf', 'upload', 'notice', 'lease', 'record', 'email', 'message', 'document')):
                    existing_file_evidence = True
            if proof_leads and existing_policy_doc and existing_file_evidence:
                return []

        questions: List[Dict[str, Any]] = []
        seen_keys: Set[str] = set()
        candidate_claims = intake_case_file.get('candidate_claims', [])
        exhibit_ready_documents = self._needs_exhibit_ready_document_questions()
        if not isinstance(candidate_claims, list):
            return []

        for claim in candidate_claims:
            if not isinstance(claim, dict):
                continue
            claim_type = normalize_claim_type(str(claim.get('claim_type') or '').strip())
            claim_label = str(claim.get('label') or claim_type or 'this claim').strip()
            weak_claim_focus = claim_type in {'housing_discrimination', 'hacc_research_engine'}
            missing_modalities: List[str] = []
            if not existing_policy_doc:
                missing_modalities.append('policy_document')
            if not existing_file_evidence:
                missing_modalities.append('file_evidence')
            if not missing_modalities:
                continue
            question_key = f"{claim_type}:{claim_label}:proof_leads".lower()
            if question_key in seen_keys:
                continue
            seen_keys.add(question_key)
            question_intent = build_proof_lead_question_intent(claim_type, claim_label)
            question_text = build_proof_lead_question_text(claim_type, claim_label)
            if exhibit_ready_documents and (
                'policy_document' in missing_modalities or 'file_evidence' in missing_modalities
            ):
                question_text = self._build_exhibit_ready_document_prompt(
                    claim_label=claim_label,
                    include_policy_document='policy_document' in missing_modalities,
                    include_file_evidence='file_evidence' in missing_modalities,
                    base_question=question_text,
                )
            elif missing_modalities == ['policy_document', 'file_evidence'] or missing_modalities == ['file_evidence', 'policy_document']:
                question_text = (
                    f"{question_text} Please name at least one policy document and one file record "
                    "(notice, lease, email, or attachment) with date, sender, and where it can be obtained."
                )
            elif missing_modalities == ['policy_document']:
                question_text = (
                    f"{question_text} Please identify any policy document (name/section) relevant to this claim and who issued it."
                )
            elif missing_modalities == ['file_evidence']:
                question_text = (
                    f"{question_text} Please identify one file record (notice, lease, email, message, or attachment) with date, sender, and where it can be obtained."
                )
            if not self._already_asked(question_text):
                questions.append(self._question_candidate(
                    source='intake_proof_gap',
                    question_type='evidence',
                    question_text=question_text,
                    context={
                        'claim_type': claim_type,
                        'claim_name': claim_label,
                        'gap_id': f"{claim_type}:proof_leads",
                        'gap_type': 'missing_proof_leads',
                        'expected_evidence_modalities': list(missing_modalities),
                        'deterministic_update_key': f"{claim_type}:proof_leads:{'-'.join(missing_modalities)}",
                        'workflow_phase': 'graph_analysis' if weak_claim_focus else 'document_generation',
                        'recommended_resolution_lane': 'structured_proof_capture',
                        'extraction_targets': ['document_type', 'document_date', 'document_owner', 'actor_name'],
                        'patchability_markers': ['support_patch_anchor', 'documentary_artifact_patch_anchor', 'notice_chain_patch_anchor'],
                    },
                    priority='high',
                    question_intent=question_intent,
                ))
            if len(questions) >= max_questions:
                return questions[:max_questions]

        return questions

    def _temporal_issue_question_type(self, issue_type: str) -> str:
        normalized_issue_type = str(issue_type or '').strip().lower()
        if normalized_issue_type in {'missing_staff_identity', 'missing_staff_title'}:
            return 'responsible_party'
        if normalized_issue_type in {'missing_written_notice'}:
            return 'evidence'
        return 'timeline'

    def _temporal_issue_extraction_targets(
        self,
        issue_type: str,
        *,
        element_tags: List[str],
        question_type: str,
    ) -> List[str]:
        normalized_issue_type = str(issue_type or '').strip().lower()
        normalized_element_tags = [str(tag or '').strip().lower() for tag in (element_tags or []) if str(tag or '').strip()]
        targets = self._derive_extraction_targets(question_type, context={'gap_type': normalized_issue_type})
        if normalized_issue_type == 'relative_only_ordering' or normalized_issue_type.startswith('temporal_reverse_'):
            targets.extend(['exact_dates', 'event_order'])
        if normalized_issue_type in {
            'retaliation_missing_causation',
            'retaliation_missing_causation_link',
            'retaliation_missing_sequence',
            'retaliation_missing_sequencing_dates',
        } or 'causation' in normalized_element_tags:
            targets.extend(['protected_activity', 'adverse_action', 'causation_link', 'exact_dates', 'event_order'])
        if normalized_issue_type in {'missing_hearing_request_date', 'missing_hearing_timing'}:
            targets.extend(['exact_dates', 'response_timing', 'notice_chain', 'actor_name', 'actor_role'])
        if normalized_issue_type in {'missing_response_dates', 'missing_decision_timeline'}:
            targets.extend(['exact_dates', 'response_timing', 'notice_chain', 'document_date', 'document_owner'])
        if normalized_issue_type == 'missing_written_notice':
            targets.extend(['document_type', 'document_date', 'document_owner', 'notice_chain'])
        if normalized_issue_type in {'missing_staff_identity', 'missing_staff_title'}:
            targets.extend(['actor_name', 'actor_role', 'decision_maker', 'adverse_action'])
        deduped: List[str] = []
        for target in targets:
            if target and target not in deduped:
                deduped.append(target)
        return deduped

    def _temporal_issue_patchability_markers(
        self,
        issue_type: str,
        *,
        element_tags: List[str],
        question_type: str,
    ) -> List[str]:
        normalized_issue_type = str(issue_type or '').strip().lower()
        normalized_element_tags = [str(tag or '').strip().lower() for tag in (element_tags or []) if str(tag or '').strip()]
        markers = self._derive_patchability_markers(question_type, context={'gap_type': normalized_issue_type})
        if normalized_issue_type == 'relative_only_ordering' or normalized_issue_type.startswith('temporal_reverse_'):
            markers.extend(['chronology_patch_anchor', 'adverse_action_patch_anchor'])
        if normalized_issue_type in {
            'retaliation_missing_causation',
            'retaliation_missing_causation_link',
            'retaliation_missing_sequence',
            'retaliation_missing_sequencing_dates',
        } or 'causation' in normalized_element_tags:
            markers.extend(['chronology_patch_anchor', 'adverse_action_patch_anchor'])
        if normalized_issue_type in {'missing_hearing_request_date', 'missing_hearing_timing', 'missing_response_dates', 'missing_decision_timeline'}:
            markers.extend(['chronology_response_patch_anchor', 'notice_chain_patch_anchor'])
        if normalized_issue_type in {'missing_staff_identity', 'missing_staff_title'}:
            markers.extend(['actor_link_patch_anchor', 'decision_actor_patch_anchor'])
        if normalized_issue_type == 'missing_written_notice':
            markers.extend(['support_patch_anchor', 'documentary_artifact_patch_anchor', 'notice_chain_patch_anchor'])
        deduped: List[str] = []
        for marker in markers:
            if marker and marker not in deduped:
                deduped.append(marker)
        return deduped

    def _build_claim_temporal_gap_question_text(
        self,
        issue_type: str,
        *,
        claim_label: str,
        summary: str,
        left_node_name: str,
        right_node_name: str,
        relative_markers: List[str],
    ) -> str:
        normalized_issue_type = str(issue_type or '').strip().lower()
        claim_reference = str(claim_label or '').strip() or 'this claim'
        if claim_reference.lower() == 'this claim':
            claim_reference = 'claim'
        if normalized_issue_type == 'relative_only_ordering':
            relative_phrase = ''
            if relative_markers:
                relative_phrase = f" using the reported {', '.join(relative_markers)} sequence"
            anchor_subject = left_node_name or 'the event you described'
            relative_context = " ".join(
                part
                for part in (
                    claim_reference,
                    summary,
                    left_node_name,
                    right_node_name,
                    " ".join(relative_markers or []),
                )
                if isinstance(part, str) and part.strip()
            ).lower()
            if any(
                token in relative_context
                for token in (
                    'retaliat',
                    'adverse',
                    'complaint',
                    'grievance',
                    'hearing',
                    'appeal',
                    'housing status',
                )
            ):
                return (
                    f"For your {claim_reference}, what protected activity happened first, what exact adverse action "
                    "followed, on what date or timeframe did it happen, who communicated it, and what notice, "
                    "message, or decision record proves that action?"
                )
            return (
                f"For your {claim_reference} claim, what is the most specific date or timeframe for {anchor_subject}, "
                f"and what happened immediately before and after it{relative_phrase}?"
            )
        if normalized_issue_type.startswith('temporal_reverse_'):
            left_label = left_node_name or 'the first event'
            right_label = right_node_name or 'the second event'
            return (
                f"For your {claim_reference} claim, which happened first: {left_label} or {right_label}, "
                "and what is the most specific date or timeframe for each event?"
            )
        if normalized_issue_type in {
            'retaliation_missing_causation',
            'retaliation_missing_causation_link',
            'retaliation_missing_sequence',
            'retaliation_missing_sequencing_dates',
        }:
            return (
                f"For your {claim_reference} claim, what protected activity happened first, what adverse action followed, "
                "who was involved in each step, and on what exact dates or timeframes did those events occur?"
            )
        if normalized_issue_type in {'missing_hearing_request_date', 'missing_hearing_timing'}:
            return (
                f"For your {claim_reference} claim, on what date did you request the hearing, grievance, or review, "
                "who received it, and do you have any notice, email, or letter confirming that request?"
            )
        if normalized_issue_type in {'missing_response_dates', 'missing_decision_timeline'}:
            return (
                f"For your {claim_reference} claim, when did you receive each response or decision, who sent it, "
                "and do you have any notice, email, or letter showing that timeline?"
            )
        if normalized_issue_type == 'missing_written_notice':
            return (
                f"For your {claim_reference} claim, do you have any written notice, email, text, letter, or upload "
                "showing the decision, including the date and sender?"
            )
        if normalized_issue_type in {'missing_staff_identity', 'missing_staff_title'}:
            return (
                f"For your {claim_reference} claim, who specifically made or communicated the decision, "
                "and what were that person's full name, title, and role?"
            )
        summary_clause = f" This appears unresolved because {summary}" if summary else ''
        return (
            f"For your {claim_reference} claim, what exact dates, sequence details, and decision-maker information "
            f"would anchor this timeline gap clearly?{summary_clause}"
        )

    def _build_claim_temporal_gap_questions(
        self,
        intake_case_file: Optional[Dict[str, Any]],
        max_questions: int,
    ) -> List[Dict[str, Any]]:
        if not isinstance(intake_case_file, dict) or max_questions <= 0:
            return []

        temporal_issue_registry = intake_case_file.get('temporal_issue_registry', [])
        if not isinstance(temporal_issue_registry, list) or not temporal_issue_registry:
            return []

        claim_label_map: Dict[str, str] = {}
        for claim in intake_case_file.get('candidate_claims', []) or []:
            if not isinstance(claim, dict):
                continue
            claim_type = normalize_claim_type(str(claim.get('claim_type') or '').strip())
            if not claim_type:
                continue
            claim_label_map[claim_type] = str(claim.get('label') or claim_type).strip()

        questions: List[Dict[str, Any]] = []
        seen_keys: Set[str] = set()
        exhibit_ready_documents = self._needs_exhibit_ready_document_questions()
        for issue in temporal_issue_registry:
            if len(questions) >= max_questions:
                break
            if not isinstance(issue, dict):
                continue
            status = str(issue.get('status') or '').strip().lower()
            if status in {'resolved', 'closed', 'fixed'}:
                continue
            claim_types = [
                normalize_claim_type(str(value or '').strip())
                for value in (issue.get('claim_types') or issue.get('affected_claim_types') or [])
                if str(value or '').strip()
            ]
            claim_types = [claim_type for claim_type in claim_types if claim_type]
            claim_type = claim_types[0] if claim_types else ''
            claim_label = claim_label_map.get(claim_type) or (claim_type.replace('_', ' ') if claim_type else 'this claim')
            issue_id = str(issue.get('issue_id') or issue.get('source_ref') or issue.get('issue_type') or '').strip()
            issue_type = str(issue.get('issue_type') or issue.get('category') or '').strip().lower()
            element_tags = [str(tag or '').strip() for tag in (issue.get('element_tags') or issue.get('affected_element_ids') or []) if str(tag or '').strip()]
            target_element_id = str(element_tags[0] or '').strip().lower() if element_tags else ''
            question_key = '|'.join(filter(None, [issue_id.lower(), claim_type, issue_type, target_element_id]))
            if question_key in seen_keys:
                continue
            seen_keys.add(question_key)
            question_type = self._temporal_issue_question_type(issue_type)
            relative_markers = [str(marker or '').strip().lower() for marker in (issue.get('relative_markers') or []) if str(marker or '').strip()]
            question_text = self._build_claim_temporal_gap_question_text(
                issue_type,
                claim_label=claim_label,
                summary=self._short_description(str(issue.get('summary') or '').strip(), limit=120),
                left_node_name=str(issue.get('left_node_name') or '').strip(),
                right_node_name=str(issue.get('right_node_name') or '').strip(),
                relative_markers=relative_markers,
            )
            if exhibit_ready_documents and issue_type in {
                'missing_hearing_request_date',
                'missing_hearing_timing',
                'missing_response_dates',
                'missing_decision_timeline',
                'missing_written_notice',
            }:
                question_text = self._build_exhibit_ready_temporal_prompt(
                    issue_type,
                    claim_label=claim_label,
                    base_question=question_text,
                )
            if self._already_asked(question_text):
                continue
            extraction_targets = self._temporal_issue_extraction_targets(
                issue_type,
                element_tags=element_tags,
                question_type=question_type,
            )
            patchability_markers = self._temporal_issue_patchability_markers(
                issue_type,
                element_tags=element_tags,
                question_type=question_type,
            )
            question = self._question_candidate(
                source='intake_claim_temporal_gap',
                question_type=question_type,
                question_text=question_text,
                context={
                    'claim_type': claim_type,
                    'claim_name': claim_label,
                    'gap_id': issue_id or f'{claim_type}:{issue_type}',
                    'gap_type': issue_type,
                    'requirement_id': target_element_id,
                    'target_element_id': target_element_id,
                    'temporal_issue_id': issue_id,
                    'temporal_issue_category': str(issue.get('category') or issue_type),
                    'temporal_issue_summary': str(issue.get('summary') or ''),
                    'temporal_issue_status': status or 'open',
                    'left_node_name': str(issue.get('left_node_name') or ''),
                    'right_node_name': str(issue.get('right_node_name') or ''),
                    'fact_ids': list(issue.get('fact_ids') or []),
                    'relative_markers': list(relative_markers),
                    'deterministic_update_key': issue_id or f'{claim_type}:{issue_type}:{target_element_id}',
                    'workflow_phase': 'document_generation' if question_type == 'evidence' else 'graph_analysis',
                    'recommended_resolution_lane': str(issue.get('recommended_resolution_lane') or 'clarify_with_complainant'),
                    'extraction_targets': extraction_targets,
                    'patchability_markers': patchability_markers,
                },
                priority='high' if bool(issue.get('blocking')) or str(issue.get('severity') or '').strip().lower() == 'blocking' else 'medium',
            )
            question_objective = 'identify_supporting_proof' if question_type == 'evidence' else 'establish_chronology'
            question_goal = 'identify_supporting_proof' if question_type == 'evidence' else 'establish_element'
            if issue_type in {
                'retaliation_missing_causation',
                'retaliation_missing_causation_link',
                'retaliation_missing_sequence',
                'retaliation_missing_sequencing_dates',
            }:
                question_objective = 'establish_causation'
            elif question_type == 'responsible_party':
                question_objective = 'identify_responsible_actor'
            question['question_objective'] = question_objective
            question['question_goal'] = question_goal
            ranking_explanation = question.get('ranking_explanation') if isinstance(question.get('ranking_explanation'), dict) else {}
            ranking_explanation['question_objective'] = question_objective
            ranking_explanation['question_goal'] = question_goal
            question['ranking_explanation'] = ranking_explanation
            questions.append(question)

        return questions[:max_questions]

    def _build_history_follow_up_questions(
        self,
        max_questions: int,
    ) -> List[Dict[str, Any]]:
        return denoiser_questions._build_history_follow_up_questions(
            self,
            max_questions,
        )

    _LEGAL_CONTEXT_QUESTION_FIELDS = {
        'legal_context.jurisdiction': 'jurisdiction',
        'legal_context.event_dates': 'event_date',
        'legal_context.applicable_law_date': 'applicable_law_date',
        'legal_context.filing_reference_date': 'filing_reference_date',
        'legal_context.claim_candidates': 'claim_candidates',
    }

    def _current_legal_context_question_targets(
        self, knowledge_graph: KnowledgeGraph, intake_case_file: Optional[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """Rederive current open context fields without changing case or proof truth."""
        if not isinstance(intake_case_file, dict):
            return {}
        import json
        from complaint_phases.intake_case_file import refresh_explicit_legal_context
        from integrations.ipfs_datasets.legal import intake_legal_selection

        case = copy.deepcopy(intake_case_file)
        context = refresh_explicit_legal_context(case)
        claims = list(case.get('candidate_claims') or [])
        if not claims:
            claims = [
                {'name': entity.name,
                 'type': entity.attributes.get('claim_type', 'unknown'),
                 'description': entity.attributes.get('description', '')}
                for entity in (knowledge_graph.get_entities_by_type('claim') if knowledge_graph is not None else [])
            ]
        selection = intake_legal_selection(context, claims)
        revision = context.get('context_revision')
        if type(revision) is not int or revision < 0:
            return {}
        material = {
            'context_revision': revision,
            'jurisdiction': context.get('jurisdiction'),
            'date_roles': {role: context.get(role) for role in (
                'event_date', 'event_dates', 'applicable_law_date', 'filing_reference_date',
            )},
            'claim_candidates': selection.get('claim_candidates') or [],
        }
        try:
            raw = json.dumps(material, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False, allow_nan=False).encode('utf-8')
        except (TypeError, ValueError):
            return {}
        target_revision = f"legal-context:{revision}:" + hashlib.sha256(raw).hexdigest()
        targets: Dict[str, Dict[str, Any]] = {}
        for question in selection.get('questions') or []:
            if not isinstance(question, dict):
                continue
            question_id = str(question.get('question_id') or '')
            field = self._LEGAL_CONTEXT_QUESTION_FIELDS.get(question_id)
            if field is None or question.get('field') != field:
                continue
            prompt = str(question.get('prompt') or '').strip()
            reason = str(question.get('reason') or '').strip()
            if not prompt or not reason:
                continue
            targets[question_id] = {
                'question_id': question_id, 'field': field, 'prompt': prompt,
                'target_id': f"legal_context:{question_id}",
                'target_revision': target_revision, 'target_kind': 'factual',
                'provenance': {'candidate_source': 'canonical_legal_context',
                               'question_id': question_id, 'field': field,
                               'context_revision': revision},
                'why_answer_helps': f"Clarifies the current unresolved intake context: {reason}.",
                'expected_information': prompt, 'user_answerability': 'user_observable',
                'dependency_impact': 3, 'uncertainty': 2,
            }
        return targets

    def _bind_legal_context_question(
        self, candidate: Dict[str, Any], targets: Optional[Dict[str, Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """Accept only a currently open canonical field and refuse stale targets."""
        enriched = dict(candidate)
        question_id = str(enriched.get('question_id') or '')
        current = (targets or {}).get(question_id)
        prior = enriched.get('unresolved_target') if isinstance(enriched.get('unresolved_target'), dict) else {}
        if (not current or enriched.get('field') != current['field']
                or any(str(value) != current['target_revision'] for value in (
                    enriched.get('target_revision'), prior.get('target_revision'),
                ) if value not in (None, ''))
                or (prior.get('target_id') not in (None, '', current['target_id']))):
            enriched['unresolved_target'] = None
            return enriched
        target = {key: copy.deepcopy(value) for key, value in current.items()
                  if key not in {'question_id', 'field', 'prompt'}}
        # The current canonical prompt wins over caller text or assertion flags.
        enriched.update({
            'question': current['prompt'],
            'candidate_source': 'canonical_legal_context',
            'context': {'legal_context_field': current['field'],
                        'question_id': question_id,
                        'gap_id': current['target_id'] + '@' + current['target_revision'],
                        'target_revision': current['target_revision']},
            'unresolved_target': target,
            **{key: target[key] for key in (
                'target_id', 'target_revision', 'target_kind', 'why_answer_helps',
                'expected_information', 'user_answerability', 'dependency_impact', 'uncertainty',
            )},
        })
        explanation = dict(enriched.get('ranking_explanation') or {}) if isinstance(enriched.get('ranking_explanation'), dict) else {}
        explanation['unresolved_target'] = copy.deepcopy(target)
        enriched['ranking_explanation'] = explanation
        return enriched

    def _legal_context_case_file(self, source_context=None):
        # Actual workflow state takes precedence over a caller's serialized case.
        getter = getattr(getattr(self.mediator, 'phase_manager', None), 'get_phase_data', None)
        if callable(getter):
            from complaint_phases.phase_manager import ComplaintPhase
            case = getter(ComplaintPhase.INTAKE, 'intake_case_file')
            return case if isinstance(case, dict) else None
        case = source_context.get('intake_case_file') if isinstance(source_context, dict) else None
        return case if isinstance(case, dict) else None

    def _process_legal_context_answer(self, question, answer, knowledge_graph,
                                      source_context, disposition, factual_action=None):
        """Update an explicitly requested current context field, never a fact or law."""
        case = self._legal_context_case_file(source_context)
        current = self._current_legal_context_question_targets(knowledge_graph, case)
        bound = self._bind_legal_context_question(question, current)
        supplied = question.get('unresolved_target') if isinstance(question.get('unresolved_target'), dict) else {}
        target = bound.get('unresolved_target') or {}
        # An answer needs the exact target emitted by this current case. Raw
        # coordinate labels alone do not authorize changing intake context.
        if (not target or factual_action or supplied.get('target_id') != target.get('target_id')
                or supplied.get('target_revision') != target.get('target_revision')
                or self.is_question_target_closed(target.get('target_id'), target.get('target_revision'))):
            updates = self._non_fact_answer_updates('invalidated', {})
            updates['context_answer_status'] = 'stale_or_unbound_context_target'
            return updates
        record = self.record_question_disposition(
            bound, answer, disposition=disposition, intake_case_file=case,
            creates_fact=False, satisfies_requirement=False,
        )
        updates = self._non_fact_answer_updates(disposition, record)
        updates['context_fields_updated'] = []
        if disposition in self._NON_FACT_DISPOSITIONS:
            return updates
        field = bound['field']
        value = str(answer or '').strip()
        if field == 'claim_candidates':
            # Preserve the user's explicit candidate label; it is not a
            # promoted claim, source admission, or satisfied legal requirement.
            case['candidate_claims'] = [{'claim_type': value, 'type': value,
                                         'name': value, 'source': 'user_context_answer'}]
        else:
            apply_context = getattr(self.mediator, 'apply_explicit_legal_context', None)
            if callable(apply_context):
                apply_context(case, **{field: value})
            else:
                from complaint_phases.intake_case_file import apply_explicit_legal_context
                apply_explicit_legal_context(case, **{field: value})
        resolver = getattr(self.mediator, 'resolve_intake_legal_selection', None)
        manager = getattr(self.mediator, 'phase_manager', None)
        if callable(resolver) and manager is not None:
            from complaint_phases.phase_manager import ComplaintPhase
            claims = [
                {'name': entity.name, 'type': entity.attributes.get('claim_type', 'unknown'),
                 'description': entity.attributes.get('description', '')}
                for entity in (knowledge_graph.get_entities_by_type('claim') if knowledge_graph is not None else [])
            ]
            selection = resolver(claims, case)
            manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_case_file', case)
            manager.update_phase_data(ComplaintPhase.INTAKE, 'legal_selection', selection)
        updates['context_fields_updated'] = [field]
        unresolved = self._current_legal_context_question_targets(knowledge_graph, case).get(bound['question_id'])
        if unresolved is not None:
            # A partial or unrecognized value is new user input, not closure.
            # Retain its disposition history and explicitly reopen this field.
            reopened = self.reopen_disposed_question(
                bound['target_id'], 'The explicit context answer leaves this field unresolved.',
                target_revision=unresolved['target_revision'], intake_case_file=case,
                evidence_change='explicit-context-answer:' + hashlib.sha256(value.encode('utf-8')).hexdigest(),
            )
            updates['context_answer_status'] = 'needs_context_clarification'
            updates['question_reopened'] = reopened
        else:
            updates['context_answer_status'] = 'recorded_explicit_context'
        return updates

    _CLOSED_TARGET_DISPOSITIONS = {
        'answered', 'unknown', 'declined', 'refused', 'skipped', 'deferred',
        'invalidated', 'contradictory',
    }
    _NON_FACT_DISPOSITIONS = {'unknown', 'refused', 'skipped', 'deferred', 'invalidated', 'declined'}
    _DISPOSITION_ALIASES = {
        'answered': 'answered',
        'answer': 'answered',
        'unknown': 'unknown',
        'do_not_know': 'unknown',
        'dont_know': 'unknown',
        'declined': 'refused',
        'decline': 'refused',
        'refused': 'refused',
        'refuse': 'refused',
        'refusal': 'refused',
        'skipped': 'skipped',
        'skip': 'skipped',
        'deferred': 'deferred',
        'defer': 'deferred',
        'invalidated': 'invalidated',
        'invalidate': 'invalidated',
        'contradictory': 'contradictory',
    }
    _UNKNOWN_ANSWERS = {
        'unknown', 'i do not know', "i don't know", 'i dont know', 'idk', 'not sure',
        'unsure', 'no idea', 'do not know', "don't know", 'n/a', 'na', 'none',
    }
    _REFUSED_ANSWERS = {
        'i refuse', 'i refuse to answer', 'refused', 'refuse', 'i decline',
        'i decline to answer', 'declined', 'decline', 'prefer not to say',
    }
    _SKIPPED_ANSWERS = {'skip', 'skipped', 'skip this', 'skip this question'}
    _DEFERRED_ANSWERS = {'defer', 'deferred', 'later', 'not now', 'ask me later'}
    _INVALIDATED_ANSWERS = {'invalidated', 'invalidate', 'no longer applies'}
    _OPERATOR_GAP_TOKENS = (
        'prover', 'solver', 'huggingface', 'citation database', 'currentness',
        'backend', 'model download', 'repair the', 'source outage', 'unavailable source',
    )
    _LEGAL_CONCLUSION_REWRITES = (
        ('which version is correct', 'what do you recall about each account, and what dates, documents, or records can you provide'),
        ('is this illegal', 'what events, dates, and documents did you observe'),
        ('did they violate', 'what events, dates, and documents did you observe'),
        ('do you have a legal claim', 'what events, dates, and documents can you describe'),
        ('facts needed to win', 'events, dates, or documents you can share'),
    )

    def _target_rank_tuple(self, candidate: Dict[str, Any]) -> Tuple[int, int, int, str]:
        if not isinstance(candidate, dict):
            return (0, 0, 9, '')
        target = candidate.get('unresolved_target') if isinstance(candidate.get('unresolved_target'), dict) else {}
        answerability = str(target.get('user_answerability') or candidate.get('user_answerability') or 'user_observable')
        answer_rank = {'user_observable': 0, 'partial': 1, 'not_answerable': 2, 'operator_only': 3}.get(answerability, 2)
        try:
            impact = int(target.get('dependency_impact') or candidate.get('dependency_impact') or 0)
        except (TypeError, ValueError):
            impact = 0
        try:
            uncertainty = int(target.get('uncertainty') or candidate.get('uncertainty') or 0)
        except (TypeError, ValueError):
            uncertainty = 0
        return (-impact, -uncertainty, answer_rank, str(target.get('target_id') or ''))

    def _normalize_disposition_token(self, value: Any) -> str:
        token = " ".join(str(value or "").strip().lower().replace("_", " ").replace("-", " ").split())
        key = token.replace(" ", "_")
        if key in self._DISPOSITION_ALIASES:
            return self._DISPOSITION_ALIASES[key]
        compact = re.sub(r"[^a-z0-9' ]+", "", token).strip()
        return compact

    def classify_answer_disposition(self, answer: Any, explicit: Any = None) -> str:
        """Classify an answer without turning a non-answer into a fact."""
        if explicit not in (None, ""):
            mapped = self._DISPOSITION_ALIASES.get(self._normalize_disposition_token(explicit).replace(" ", "_"))
            if mapped:
                return mapped
            token = self._normalize_disposition_token(explicit)
            if token in self._CLOSED_TARGET_DISPOSITIONS or token in self._NON_FACT_DISPOSITIONS:
                return token
        compact = self._normalize_disposition_token(answer)
        if compact in self._UNKNOWN_ANSWERS:
            return "unknown"
        if compact in self._REFUSED_ANSWERS:
            return "refused"
        if compact in self._SKIPPED_ANSWERS:
            return "skipped"
        if compact in self._DEFERRED_ANSWERS:
            return "deferred"
        if compact in self._INVALIDATED_ANSWERS:
            return "invalidated"
        return "answered" if compact else "skipped"

    def _standard_intake_slot(self, candidate: Dict[str, Any]) -> str:
        if not isinstance(candidate, dict):
            return ""
        context = candidate.get("context") if isinstance(candidate.get("context"), dict) else {}
        source = str(candidate.get("candidate_source") or context.get("candidate_source") or "").strip()
        explicit = str(context.get("standard_intake_slot") or candidate.get("standard_intake_slot") or "").strip().lower()
        if explicit in {"timeline", "impact", "notice"}:
            return explicit
        if source != "standard_intake_backstop":
            return ""
        text = str(candidate.get("question") or "").lower()
        if any(token in text for token in ("harm", "remedy", "emotional", "financial", "damages")):
            return "impact"
        if any(token in text for token in ("notice", "letter", "email", "message", "who sent")):
            return "notice"
        if any(token in text for token in ("timeline", "key events", "who made", "what date")):
            return "timeline"
        return ""

    def _target_identity(self, question: Dict[str, Any]) -> Tuple[str, str, str]:
        target = question.get("unresolved_target") if isinstance(question, dict) and isinstance(question.get("unresolved_target"), dict) else {}
        context = question.get("context") if isinstance(question, dict) and isinstance(question.get("context"), dict) else {}
        target_id = str(target.get("target_id") or (question or {}).get("target_id") or "").strip()
        revision = str(
            target.get("target_revision")
            or (question or {}).get("target_revision")
            or context.get("target_revision")
            or self._question_scope_revision
            or "unresolved"
        ).strip() or "unresolved"
        kind = str(target.get("target_kind") or (question or {}).get("target_kind") or "").strip()
        return target_id, revision, kind

    def load_question_dispositions(self, intake_case_file: Optional[Dict[str, Any]]) -> None:
        if isinstance(intake_case_file, dict):
            scope = intake_case_file.get("question_scope_revision") or intake_case_file.get("scope_revision")
            legal = intake_case_file.get("legal_context") if isinstance(intake_case_file.get("legal_context"), dict) else {}
            scope = scope or legal.get("scope_revision")
            if str(scope or "").strip():
                self._question_scope_revision = str(scope).strip()
        from complaint_phases.intake_case_file import question_disposition_records
        incoming = question_disposition_records(intake_case_file)
        seen = {
            (
                str(item.get("target_id") or ""),
                str(item.get("target_revision") or ""),
                str(item.get("disposition") or ""),
                bool(item.get("reopened")),
                str(item.get("reopen_reason") or ""),
            )
            for item in self.question_disposition_records
            if isinstance(item, dict)
        }
        for record in incoming:
            key = (
                record["target_id"],
                record["target_revision"],
                record["disposition"],
                bool(record["reopened"]),
                str(record.get("reopen_reason") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            self.question_disposition_records.append(dict(record))

    def is_question_target_closed(self, target_id: Any, target_revision: Any = None) -> bool:
        wanted = str(target_id or "").strip()
        if not wanted:
            return False
        revision = str(target_revision or "").strip()
        blanket = str((self.target_dispositions or {}).get(wanted) or "").strip().lower()
        if blanket in self._CLOSED_TARGET_DISPOSITIONS:
            reopened = False
            for record in self.question_disposition_records:
                if not isinstance(record, dict) or str(record.get("target_id") or "") != wanted:
                    continue
                if record.get("reopened"):
                    reopen_revision = str(record.get("target_revision") or "")
                    if not revision or not reopen_revision or reopen_revision == revision:
                        reopened = True
            if not reopened:
                return True
        closed = False
        for record in self.question_disposition_records:
            if not isinstance(record, dict) or str(record.get("target_id") or "") != wanted:
                continue
            if record.get("reopened"):
                reopen_revision = str(record.get("target_revision") or "")
                if not revision or not reopen_revision or reopen_revision == revision:
                    closed = False
                continue
            disposition = str(record.get("disposition") or "").strip().lower()
            if disposition in self._CLOSED_TARGET_DISPOSITIONS or disposition in self._NON_FACT_DISPOSITIONS:
                closed = True
        return closed

    def record_question_disposition(
        self,
        question: Dict[str, Any],
        answer: Any = "",
        *,
        disposition: Any = None,
        reason: Any = None,
        intake_case_file: Optional[Dict[str, Any]] = None,
        creates_fact: bool = False,
        satisfies_requirement: bool = False,
        contradictory_conclusion: bool = False,
    ) -> Dict[str, Any]:
        from complaint_phases.intake_case_file import record_question_disposition as persist_disposition
        legal_targets = None
        if isinstance(question, dict) and str(question.get('type') or '').lower() == 'legal_context':
            case = intake_case_file if isinstance(intake_case_file, dict) else self._legal_context_case_file()
            graph = None
            manager = getattr(self.mediator, 'phase_manager', None)
            if manager is not None:
                from complaint_phases.phase_manager import ComplaintPhase
                graph = manager.get_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph')
            legal_targets = self._current_legal_context_question_targets(graph, case)
        bound = self._bind_unresolved_target(question if isinstance(question, dict) else {},
                                             legal_context_targets=legal_targets)
        target_id, revision, kind = self._target_identity(bound if isinstance(bound, dict) else {})
        if not target_id and isinstance(question, dict):
            slot = self._standard_intake_slot(question)
            if slot:
                kind = "proof" if slot == "notice" else "factual"
                target_id = f"{kind}:standard-intake:{slot}"
                revision = revision or self._question_scope_revision
        classified = self.classify_answer_disposition(answer, explicit=disposition)
        non_fact = classified in self._NON_FACT_DISPOSITIONS
        record = {
            "target_id": target_id,
            "target_revision": revision or self._question_scope_revision or "unresolved",
            "target_kind": kind or None,
            "disposition": classified,
            "question": str((bound or question or {}).get("question") or "") or None,
            "answer": None if non_fact else answer,
            "reason": str(reason or "").strip() or None,
            "creates_fact": False if non_fact else bool(creates_fact),
            "satisfies_requirement": False if non_fact else bool(satisfies_requirement),
            "contradictory_conclusion": False if non_fact else bool(contradictory_conclusion),
            "reopened": False,
            "status": "disposed",
        }
        if target_id:
            self.objective_repeat_counts[target_id] = int(self.objective_repeat_counts.get(target_id) or 0) + 1
        if classified in {"unknown", "skipped", "deferred"} or not str(answer or "").strip():
            self.no_information_attempts = int(getattr(self, "no_information_attempts", 0) or 0) + 1
        if target_id:
            self.question_disposition_records = [
                item for item in self.question_disposition_records
                if not (
                    isinstance(item, dict)
                    and str(item.get("target_id") or "") == target_id
                    and str(item.get("target_revision") or "") == record["target_revision"]
                    and not item.get("reopened")
                )
            ]
            self.question_disposition_records.append(dict(record))
        case_file = intake_case_file if isinstance(intake_case_file, dict) else None
        if case_file is None and self.mediator is not None:
            phase_manager = getattr(self.mediator, "phase_manager", None)
            getter = getattr(phase_manager, "get_phase_data", None)
            if callable(getter):
                try:
                    from complaint_phases.phase_manager import ComplaintPhase
                    loaded = getter(ComplaintPhase.INTAKE, "intake_case_file")
                except Exception:
                    loaded = None
                if isinstance(loaded, dict):
                    case_file = loaded
        if isinstance(case_file, dict) and target_id:
            persist_disposition(
                case_file,
                target_id=target_id,
                target_revision=record["target_revision"],
                disposition=classified,
                target_kind=kind,
                question=record["question"],
                answer=record["answer"],
                reason=record["reason"],
                creates_fact=record["creates_fact"],
                satisfies_requirement=record["satisfies_requirement"],
                contradictory_conclusion=record["contradictory_conclusion"],
            )
        return record

    def reopen_disposed_question(
        self,
        target_id: Any,
        reason: Any,
        *,
        target_revision: Any = None,
        intake_case_file: Optional[Dict[str, Any]] = None,
        evidence_change: Any = None,
        scope_change: Any = None,
    ) -> Dict[str, Any]:
        from complaint_phases.intake_case_file import reopen_question_disposition
        why = str(reason or "").strip()
        evidence = str(evidence_change or "").strip() or None
        scope = str(scope_change or "").strip() or None
        if not why:
            raise ValueError("reopening a disposed question requires a reason")
        if not evidence and not scope:
            raise ValueError("reopening a disposed question requires new evidence or changed scope")
        wanted = str(target_id or "").strip()
        case_file = intake_case_file if isinstance(intake_case_file, dict) else None
        if case_file is None and self.mediator is not None:
            phase_manager = getattr(self.mediator, "phase_manager", None)
            getter = getattr(phase_manager, "get_phase_data", None)
            if callable(getter):
                try:
                    from complaint_phases.phase_manager import ComplaintPhase
                    loaded = getter(ComplaintPhase.INTAKE, "intake_case_file")
                except Exception:
                    loaded = None
                if isinstance(loaded, dict):
                    case_file = loaded
        if isinstance(case_file, dict):
            reopened = reopen_question_disposition(
                case_file,
                wanted,
                reason=why,
                target_revision=target_revision,
                evidence_change=evidence,
                scope_change=scope,
            )
        else:
            if not any(
                isinstance(item, dict) and str(item.get("target_id") or "") == wanted and not item.get("reopened")
                for item in self.question_disposition_records
            ) and wanted not in (self.target_dispositions or {}):
                raise ValueError("no disposed question matches that target")
            reopened = {
                "target_id": wanted,
                "target_revision": str(target_revision or self._question_scope_revision or "unresolved"),
                "disposition": str((self.target_dispositions or {}).get(wanted) or "unknown"),
                "reopened": True,
                "reopen_reason": why,
                "evidence_change": evidence,
                "scope_change": scope,
                "status": "reopened",
                "creates_fact": False,
                "satisfies_requirement": False,
                "contradictory_conclusion": False,
            }
        self.question_disposition_records.append(dict(reopened))
        if wanted in self.target_dispositions:
            self.target_dispositions.pop(wanted, None)
        if scope:
            self._question_scope_revision = scope
        return reopened

    def _non_fact_answer_updates(self, disposition: str, record: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "entities_updated": 0,
            "relationships_added": 0,
            "requirements_satisfied": 0,
            "disposition": disposition,
            "creates_fact": False,
            "satisfies_requirement": False,
            "contradictory_conclusion": False,
            "question_disposition": record,
        }

    def _target_was_reopened(self, target_id: str) -> bool:
        wanted = str(target_id or "").strip()
        reopened = False
        for record in self.question_disposition_records:
            if not isinstance(record, dict) or str(record.get("target_id") or "") != wanted:
                continue
            if record.get("reopened"):
                reopened = True
            elif str(record.get("disposition") or "").strip().lower() in self._CLOSED_TARGET_DISPOSITIONS:
                reopened = False
        return reopened

    def _closed_target_ids(self) -> Set[str]:
        closed: Set[str] = set()
        for target_id, disposition in (self.target_dispositions or {}).items():
            if str(disposition or '').strip().lower() in self._CLOSED_TARGET_DISPOSITIONS and str(target_id or '').strip():
                if not self._target_was_reopened(str(target_id)):
                    closed.add(str(target_id))
        for record in self.question_disposition_records:
            if not isinstance(record, dict):
                continue
            target_id = str(record.get("target_id") or "").strip()
            disposition = str(record.get("disposition") or "").strip().lower()
            if target_id and not record.get("reopened") and disposition in self._CLOSED_TARGET_DISPOSITIONS:
                if not self._target_was_reopened(target_id):
                    closed.add(target_id)
        for item in self.questions_asked:
            if not isinstance(item, dict):
                continue
            question = item.get('question') if isinstance(item.get('question'), dict) else {}
            target = question.get('unresolved_target') if isinstance(question.get('unresolved_target'), dict) else {}
            target_id = str(target.get('target_id') or question.get('target_id') or '').strip()
            disposition = str(item.get('disposition') or item.get('answer_disposition') or question.get('disposition') or '').strip().lower()
            answer = str(item.get('answer') or '').strip().lower()
            if disposition in self._CLOSED_TARGET_DISPOSITIONS or any(
                phrase in answer for phrase in ("don't know", 'do not know', 'i decline', 'declined', 'i refuse', 'refused')
            ):
                if target_id and not self._target_was_reopened(target_id):
                    closed.add(target_id)
        return closed

    def _neutralize_question_text(self, question_text: str) -> str:
        text = str(question_text or '').strip()
        lowered = text.lower()
        for phrase, replacement in self._LEGAL_CONCLUSION_REWRITES:
            if phrase in lowered:
                text = re.sub(re.escape(phrase), replacement, text, flags=re.IGNORECASE)
                lowered = text.lower()
        if text and not text.endswith('?'):
            text = text.rstrip('.') + '?'
        return text

    def _is_operator_source_gap(self, candidate: Dict[str, Any]) -> bool:
        context = candidate.get('context') if isinstance(candidate.get('context'), dict) else {}
        status = str(
            context.get('source_status')
            or context.get('prover_status')
            or context.get('capability_status')
            or candidate.get('source_status')
            or ''
        ).strip().lower()
        if status in {'unavailable', 'degraded', 'outage', 'missing'}:
            return True
        kind = str(candidate.get('target_kind') or context.get('target_kind') or '').strip().lower()
        if kind == 'source_diagnostic':
            return True
        blob = ' '.join(
            str(candidate.get(key) or '')
            for key in ('question', 'question_reason', 'candidate_source')
        ).lower()
        return any(token in blob for token in self._OPERATOR_GAP_TOKENS) and any(
            token in blob for token in ('unavailable', 'outage', 'failed', 'down', 'repair', 'missing')
        )

    def _record_source_capability_diagnostic(self, intake_case_file: Optional[Dict[str, Any]]) -> None:
        if not isinstance(intake_case_file, dict):
            return
        status = intake_case_file.get('source_capability')
        if status is None:
            status = intake_case_file.get('prover_status')
        detail = status if isinstance(status, dict) else {'status': status}
        state = str(
            (detail.get('status') if isinstance(detail, dict) else status) or ''
        ).strip().lower()
        if state not in {'unavailable', 'degraded', 'outage', 'missing'}:
            return
        diagnostic = {
            'kind': 'source_operator_diagnostic',
            'target_kind': 'source_diagnostic',
            'status': state,
            'audience': 'operator',
            'user_question': None,
            'detail': detail if isinstance(detail, dict) else {'status': state},
            'message': (
                'Legal citation, currentness, prover, or solver capability is unavailable. '
                'Follow up with the source operator; do not ask the user to repair backend infrastructure.'
            ),
        }
        if diagnostic not in self.source_operator_diagnostics:
            self.source_operator_diagnostics.append(diagnostic)

    def _record_operator_candidates(self, candidates: List[Dict[str, Any]]) -> None:
        for candidate in candidates or []:
            if not isinstance(candidate, dict) or not self._is_operator_source_gap(candidate):
                continue
            diagnostic = {
                'kind': 'source_operator_diagnostic',
                'target_kind': 'source_diagnostic',
                'audience': 'operator',
                'user_question': None,
                'question': None,
                'message': (
                    'A legal citation, currentness, prover, or solver gap needs source or operator follow-up. '
                    'No user question was emitted.'
                ),
                'detail': {
                    'candidate_source': candidate.get('candidate_source'),
                    'source_status': (candidate.get('context') or {}).get('source_status') if isinstance(candidate.get('context'), dict) else None,
                },
            }
            if diagnostic not in self.source_operator_diagnostics:
                self.source_operator_diagnostics.append(diagnostic)

    def _bind_unresolved_target(self, candidate: Dict[str, Any], *,
                                legal_context_targets: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
        if not isinstance(candidate, dict):
            return candidate
        enriched = dict(candidate)
        if str(enriched.get('type') or enriched.get('question_type') or '').strip().lower() == 'legal_context':
            return self._bind_legal_context_question(enriched, legal_context_targets)
        context = dict(enriched.get('context') or {}) if isinstance(enriched.get('context'), dict) else {}
        enriched['question'] = self._neutralize_question_text(str(enriched.get('question') or ''))
        if self._is_operator_source_gap(enriched):
            enriched['user_answerability'] = 'operator_only'
            enriched['target_kind'] = 'source_diagnostic'
            enriched['unresolved_target'] = None
            return enriched

        question_type = str(enriched.get('type') or enriched.get('question_type') or '').strip().lower()
        source = str(enriched.get('candidate_source') or context.get('candidate_source') or '').strip()
        standard_slot = self._standard_intake_slot(enriched)
        left_id = str(context.get('left_node_id') or '').strip()
        right_id = str(context.get('right_node_id') or '').strip()
        raw_id = str(
            context.get('requirement_id')
            or enriched.get('target_element_id')
            or context.get('target_element_id')
            or context.get('claim_element_id')
            or context.get('entity_id')
            or context.get('issue_id')
            or context.get('gap_id')
            or context.get('deterministic_update_key')
            or context.get('node_id')
            or context.get('claim_id')
            or ''
        ).strip()
        if not raw_id and source == 'knowledge_graph_gap':
            raw_id = 'kg:' + str(context.get('gap_type') or question_type or 'gap')
        if standard_slot:
            target_kind = 'proof' if standard_slot == 'notice' else 'factual'
            target_id = f"{target_kind}:standard-intake:{standard_slot}"
        elif question_type == 'contradiction' or (left_id and right_id and 'contradict' in source):
            target_kind = 'contradiction'
            pair = tuple(sorted([left_id or raw_id or 'left', right_id or 'right']))
            target_id = f"contradiction:{pair[0]}:{pair[1]}"
        elif question_type == 'requirement' or source in {'dependency_graph_requirement', 'intake_claim_element_gap'}:
            target_kind = 'requirement'
            target_id = f"requirement:{raw_id}" if raw_id else ''
        elif question_type == 'evidence' or source in {'intake_proof_gap', 'history_follow_up'}:
            target_kind = 'proof' if source == 'intake_proof_gap' or question_type == 'evidence' else 'factual'
            if source == 'history_follow_up' and question_type != 'evidence':
                target_kind = 'factual'
            target_id = f"{target_kind}:{raw_id}" if raw_id else ''
        elif raw_id:
            target_kind = 'factual'
            target_id = f"factual:{raw_id}"
        else:
            existing = enriched.get('unresolved_target') if isinstance(enriched.get('unresolved_target'), dict) else None
            if not existing or not str(existing.get('target_id') or '').strip():
                enriched['unresolved_target'] = None
                return enriched
            target_kind = str(existing.get('target_kind') or 'factual')
            target_id = str(existing.get('target_id'))

        if not target_id:
            enriched['unresolved_target'] = None
            return enriched

        revision = str(
            context.get('target_revision')
            or context.get('revision')
            or enriched.get('target_revision')
            or 'unresolved'
        ).strip() or 'unresolved'
        priority = str(enriched.get('priority') or 'medium').strip().lower()
        blocking = str(enriched.get('blocking_level') or context.get('blocking_level') or '').strip().lower()
        dependency_impact = 3 if blocking == 'blocking' or priority == 'critical' else 2 if priority == 'high' else 1 if priority == 'medium' else 0
        if target_kind == 'contradiction':
            dependency_impact = max(dependency_impact, 3)
        uncertainty = 3 if target_kind == 'contradiction' else 2 if priority in {'high', 'critical'} else 1
        explicit_impact = context.get('dependency_impact', enriched.get('dependency_impact'))
        explicit_uncertainty = context.get('uncertainty', enriched.get('uncertainty'))
        if explicit_impact is not None:
            try:
                dependency_impact = int(explicit_impact)
            except (TypeError, ValueError):
                pass
        if explicit_uncertainty is not None:
            try:
                uncertainty = int(explicit_uncertainty)
            except (TypeError, ValueError):
                pass
        expected_information = str(
            enriched.get('expected_information')
            or context.get('expected_information')
            or enriched.get('expected_proof_gain')
            or 'Observed events, dates, people, or documents the user can recall or provide.'
        ).strip()
        why_answer_helps = str(
            enriched.get('why_answer_helps')
            or enriched.get('question_reason')
            or context.get('why_answer_helps')
            or 'The answer addresses an unresolved factual, requirement, or contradiction target without treating it as already proved.'
        ).strip()
        provenance = {
            'candidate_source': source,
            'requirement_id': str(context.get('requirement_id') or '') or None,
            'proof_objective_id': str(enriched.get('proof_objective_id') or '') or None,
            'entity_id': str(context.get('entity_id') or '') or None,
            'claim_id': str(context.get('claim_id') or '') or None,
            'left_node_id': left_id or None,
            'right_node_id': right_id or None,
            'node_id': str(context.get('node_id') or '') or None,
        }
        user_answerability = 'user_observable'
        lowered = str(enriched.get('question') or '').lower()
        if any(token in lowered for token in ('statute', 'case law', 'legal conclusion', 'liable', 'violation of law')):
            user_answerability = 'not_answerable'
        target = {
            'target_id': target_id,
            'target_revision': revision,
            'target_kind': target_kind,
            'provenance': provenance,
            'why_answer_helps': why_answer_helps,
            'expected_information': expected_information,
            'user_answerability': user_answerability,
            'dependency_impact': dependency_impact,
            'uncertainty': uncertainty,
        }
        enriched['unresolved_target'] = target
        enriched['target_id'] = target_id
        enriched['target_revision'] = revision
        enriched['target_kind'] = target_kind
        enriched['why_answer_helps'] = why_answer_helps
        enriched['expected_information'] = expected_information
        enriched['user_answerability'] = user_answerability
        enriched['dependency_impact'] = dependency_impact
        enriched['uncertainty'] = uncertainty
        explanation = dict(enriched.get('ranking_explanation') or {}) if isinstance(enriched.get('ranking_explanation'), dict) else {}
        explanation['unresolved_target'] = target
        explanation['dependency_impact'] = dependency_impact
        explanation['uncertainty'] = uncertainty
        explanation['user_answerability'] = user_answerability
        enriched['ranking_explanation'] = explanation
        return enriched

    def _finalize_neutral_targeted_questions(self, questions: List[Dict[str, Any]], *,
                                             legal_context_targets: Optional[Dict[str, Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """Keep only neutral user questions bound to an open unresolved target.

        An empty result is not saturation. Source and prover gaps become operator
        diagnostics and are not re-asked of the user.
        """
        closed = self._closed_target_ids()
        kept: List[Dict[str, Any]] = []
        seen_target_ids: Set[str] = set()
        for raw in questions or []:
            if not isinstance(raw, dict):
                continue
            candidate = self._bind_unresolved_target(raw, legal_context_targets=legal_context_targets)
            if self._is_operator_source_gap(candidate) or candidate.get('user_answerability') == 'operator_only':
                diagnostic = {
                    'kind': 'source_operator_diagnostic',
                    'target_kind': 'source_diagnostic',
                    'audience': 'operator',
                    'user_question': None,
                    'question': None,
                    'message': (
                        'A legal citation, currentness, prover, or solver gap needs source or operator follow-up. '
                        'No user question was emitted.'
                    ),
                    'detail': {
                        'candidate_source': candidate.get('candidate_source'),
                        'source_status': (candidate.get('context') or {}).get('source_status') if isinstance(candidate.get('context'), dict) else None,
                    },
                }
                if diagnostic not in self.source_operator_diagnostics:
                    self.source_operator_diagnostics.append(diagnostic)
                continue
            target = candidate.get('unresolved_target') if isinstance(candidate.get('unresolved_target'), dict) else None
            if not target or not str(target.get('target_id') or '').strip():
                continue
            if str(target.get('target_kind') or '') not in {'factual', 'requirement', 'contradiction', 'proof'}:
                continue
            if target.get('user_answerability') != 'user_observable':
                continue
            if str(target.get('target_id')) in closed or self.is_question_target_closed(
                target.get('target_id'),
                target.get('target_revision'),
            ):
                continue
            if str(target.get('target_id')) in seen_target_ids:
                continue
            seen_target_ids.add(str(target.get('target_id')))
            required = (
                'target_id', 'target_revision', 'target_kind', 'provenance',
                'why_answer_helps', 'expected_information', 'user_answerability',
            )
            if any(not target.get(field) for field in required):
                continue
            kept.append(candidate)
        return kept

    def collect_question_candidates(
        self,
        knowledge_graph: KnowledgeGraph,
        dependency_graph: DependencyGraph,
        max_questions: int = 10,
        intake_case_file: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        return denoiser_questions.collect_question_candidates(
            self,
            knowledge_graph,
            dependency_graph,
            max_questions,
            intake_case_file,
        )

    def _default_candidate_sort_key(self, candidate: Dict[str, Any]) -> Tuple[int, int, int]:
        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        if not isinstance(candidate, dict):
            return (99, 99, 99)
        return (
            int(candidate.get('proof_priority', self._phase1_proof_priority(candidate.get('type', '')))),
            priority_order.get(candidate.get('priority', 'low'), 3),
            int(candidate.get('workflow_phase_rank', 99) or 99),
        ) + self._target_rank_tuple(candidate)

    def _actor_score_candidate(self, candidate: Dict[str, Any]) -> float:
        if not isinstance(candidate, dict):
            return 0.0
        priority_map = {'high': 3.0, 'medium': 2.0, 'low': 1.0}
        blocking_map = {'blocking': 3.0, 'important': 2.0, 'informational': 1.0}
        qtype = str(candidate.get('type') or '').strip().lower()
        question_text = str(candidate.get('question') or '').strip().lower()
        follow_up_tags = [str(tag).strip().lower() for tag in (candidate.get('follow_up_tags') or []) if str(tag).strip()]
        extraction_targets = [str(target).strip().lower() for target in (candidate.get('extraction_targets') or []) if str(target).strip()]
        workflow_phase = str(candidate.get('workflow_phase') or '').strip().lower()
        patchability_markers = [str(marker).strip().lower() for marker in (candidate.get('patchability_markers') or []) if str(marker).strip()]
        proof_priority = int(candidate.get('proof_priority', self._phase1_proof_priority(qtype)) or 0)
        blocking_level = str(candidate.get('blocking_level') or '').strip().lower()
        score = 0.0
        score += max(0.0, 8.0 - float(proof_priority))
        score += priority_map.get(str(candidate.get('priority') or 'low').strip().lower(), 1.0)
        score += blocking_map.get(blocking_level, 0.0)
        if qtype in {'timeline', 'contradiction', 'responsible_party', 'requirement'}:
            score += 1.5
        if qtype == 'contradiction':
            # Preserve contradiction-first behavior for clearly conflicting records.
            score += 6.5
        if any(token in question_text for token in ('when', 'date', 'timeline', 'chronology', 'anchor')):
            score += 1.25
        if any(token in question_text for token in ('who', 'actor', 'manager', 'supervisor', 'organization')):
            score += 1.25
        if any(token in question_text for token in ('protected activity', 'adverse', 'retaliation', 'because', 'after')):
            score += 1.25
        if 'exact_dates' in follow_up_tags:
            score += 1.5
        if 'staff_identity' in follow_up_tags:
            score += 1.5
        if 'notice_chain' in follow_up_tags:
            score += 1.0
        if 'retaliation_sequence' in follow_up_tags:
            score += 2.0
        if 'chronology_gap' in follow_up_tags:
            score += 1.8
        if 'decision_precision' in follow_up_tags:
            score += 1.8
        if 'documentary_precision' in follow_up_tags:
            score += 1.4
        if 'response_timing' in follow_up_tags:
            score += 1.4
        if extraction_targets:
            score += min(2.0, 0.4 * float(len(extraction_targets)))
        if patchability_markers:
            score += min(1.5, 0.5 * float(len(patchability_markers)))
        score += max(0.0, 2.0 - float(self._phase_focus_rank(workflow_phase)) * 0.5)

        score += float(self.question_quality_weight) * float(self._question_quality_bonus_candidate(candidate))
        score += float(self.empathy_weight) * float(self._empathy_bonus_candidate(candidate))

        asked_count_for_type = sum(
            1
            for asked in self.questions_asked
            if isinstance(asked, dict)
            and isinstance(asked.get('question'), dict)
            and str(asked.get('question', {}).get('type') or '').strip().lower() == qtype
        )
        if asked_count_for_type == 0:
            score += 0.75
        elif asked_count_for_type >= 3:
            score -= 0.5
        return score

    def _critic_penalty_candidate(self, candidate: Dict[str, Any]) -> float:
        if not isinstance(candidate, dict):
            return 0.0
        qtype = str(candidate.get('type') or '').strip().lower()
        question_text = str(candidate.get('question') or '').strip().lower()
        context = candidate.get('context') if isinstance(candidate.get('context'), dict) else {}
        follow_up_tags = [str(tag).strip().lower() for tag in (candidate.get('follow_up_tags') or []) if str(tag).strip()]
        extraction_targets = [str(target).strip().lower() for target in (candidate.get('extraction_targets') or []) if str(target).strip()]
        workflow_phase = str(candidate.get('workflow_phase') or '').strip().lower()
        penalty = 0.0
        if not question_text:
            return 5.0
        generic_phrases = (
            "can you provide more details",
            "additional information",
            "this claim",
            "this evidence",
        )
        if any(phrase in question_text for phrase in generic_phrases):
            penalty += 1.25
        if len(question_text) < 35:
            penalty += 0.5
        if len(question_text) > 280:
            penalty += 0.5
        if question_text and not question_text.endswith('?'):
            penalty += 0.4
        if not context:
            penalty += 0.5
        if (
            ('retaliation' in question_text or 'protected activity' in question_text)
            and not any(token in question_text for token in ('when', 'date', 'who'))
        ):
            penalty += 1.0
        if 'exact_dates' in follow_up_tags and not any(token in question_text for token in ('exact date', 'on what date', 'what date', 'when')):
            penalty += 1.0
        if 'staff_identity' in follow_up_tags and not any(token in question_text for token in ('full name', 'title', 'role', 'who')):
            penalty += 1.0
        if 'retaliation_sequence' in follow_up_tags and not any(token in question_text for token in ('protected activity', 'adverse', 'because', 'after')):
            penalty += 1.0
        if 'chronology_gap' in follow_up_tags and not any(token in question_text for token in ('exact date', 'before', 'after', 'sequence', 'how long', 'response')):
            penalty += 1.1
        if 'decision_precision' in follow_up_tags and not any(token in question_text for token in ('who exactly', 'full name', 'title', 'organization', 'adverse action')):
            penalty += 1.1
        if 'documentary_precision' in follow_up_tags and not any(token in question_text for token in ('document type', 'date', 'sender', 'recipient', 'delivered')):
            penalty += 1.1
        if 'response_timing' in follow_up_tags and not any(token in question_text for token in ('how long', 'within', 'response', 'responded')):
            penalty += 1.1
        if question_text.count('?') > 1:
            penalty += 0.4
        if workflow_phase == 'graph_analysis' and not any(token in question_text for token in ('when', 'date', 'who', 'what happened')):
            penalty += 0.6
        if workflow_phase == 'document_generation' and not any(token in question_text for token in ('document', 'notice', 'letter', 'email', 'record', 'message')):
            penalty += 0.6
        if qtype in {'timeline', 'contradiction', 'responsible_party', 'impact', 'remedy'}:
            empathy_openers = (
                "to make sure i understand, ",
                "i know this may be stressful, and this helps keep your record accurate: ",
                "so we can support your claim clearly, ",
                "thanks for sharing this. ",
                "i hear you. ",
            )
            if not question_text.startswith(empathy_openers):
                penalty += 0.45
        if extraction_targets and not any(token in question_text for token in ('who', 'when', 'date', 'name', 'title', 'document', 'notice', 'record', 'because', 'after')):
            penalty += 0.5
        return penalty

    def _coverage_adjustment(
        self,
        candidate: Dict[str, Any],
        *,
        type_counts: Dict[str, int],
        phase_counts: Dict[str, int],
    ) -> float:
        if not isinstance(candidate, dict):
            return 0.0
        qtype = str(candidate.get('type') or '').strip().lower()
        workflow_phase = str(candidate.get('workflow_phase') or '').strip().lower()
        type_count = int(type_counts.get(qtype, 0))
        phase_count = int(phase_counts.get(workflow_phase, 0))
        bonus = 0.0
        if type_count <= 1:
            bonus += 0.5
        elif type_count >= 4:
            bonus -= 0.5
        if phase_count <= 1:
            bonus += 0.35
        elif phase_count >= 4:
            bonus -= 0.35
        phase_rank = self._phase_focus_rank(workflow_phase)
        if phase_rank == 0:
            bonus += 0.5
        elif phase_rank == 1:
            bonus += 0.25
        elif phase_rank == 2:
            bonus += 0.1
        return bonus

    def _annotate_actor_critic_scores(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        type_counts: Dict[str, int] = {}
        phase_counts: Dict[str, int] = {}
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            qtype = str(candidate.get('type') or '').strip().lower()
            phase = str(candidate.get('workflow_phase') or '').strip().lower()
            if qtype:
                type_counts[qtype] = type_counts.get(qtype, 0) + 1
            if phase:
                phase_counts[phase] = phase_counts.get(phase, 0) + 1

        annotated: List[Dict[str, Any]] = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            enriched = dict(candidate)
            actor_score = self._actor_score_candidate(enriched)
            critic_penalty = self._critic_penalty_candidate(enriched)
            coverage_adjustment = self._coverage_adjustment(
                enriched,
                type_counts=type_counts,
                phase_counts=phase_counts,
            )
            actor_critic_score = (
                float(self.actor_weight) * actor_score
                - float(self.critic_weight) * critic_penalty
                + float(coverage_adjustment)
            )
            enriched['actor_score'] = float(actor_score)
            enriched['critic_penalty'] = float(critic_penalty)
            enriched['coverage_adjustment'] = float(coverage_adjustment)
            enriched['actor_critic_score'] = float(actor_critic_score)
            explanation = (
                dict(enriched.get('ranking_explanation', {}))
                if isinstance(enriched.get('ranking_explanation'), dict)
                else {}
            )
            explanation['actor_score'] = float(actor_score)
            explanation['critic_penalty'] = float(critic_penalty)
            explanation['coverage_adjustment'] = float(coverage_adjustment)
            explanation['actor_critic_score'] = float(actor_critic_score)
            enriched['ranking_explanation'] = explanation
            annotated.append(enriched)
        return annotated

    def _is_low_quality_selected_candidate(
        self,
        candidate: Dict[str, Any],
        *,
        pool_score_floor: float,
    ) -> bool:
        if not isinstance(candidate, dict):
            return True
        score = float(candidate.get('actor_critic_score', 0.0) or 0.0)
        critic_penalty = float(candidate.get('critic_penalty', 0.0) or 0.0)
        text = str(candidate.get('question') or '').strip()
        extraction_targets = list(candidate.get('extraction_targets') or [])
        patchability_markers = list(candidate.get('patchability_markers') or [])
        if not text:
            return True
        if score < pool_score_floor and critic_penalty > 2.25:
            return True
        if len(text) < 24:
            return True
        if not extraction_targets and not patchability_markers and critic_penalty > 2.0:
            return True
        return False

    def select_question_candidates(
        self,
        candidates: List[Dict[str, Any]],
        *,
        max_questions: int = 10,
        selector: Any = None,
        legal_context_targets: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Select final question candidates, allowing a router/prover override."""
        normalized_candidates = [
            self._bind_unresolved_target(candidate, legal_context_targets=legal_context_targets)
            for candidate in (candidates or [])
            if isinstance(candidate, dict)
        ]
        if not normalized_candidates or max_questions <= 0:
            return []
        normalized_candidates = self._annotate_actor_critic_scores(normalized_candidates)

        def _finalize(items: Any, *, dedupe: bool) -> List[Dict[str, Any]]:
            normalized_items = [candidate for candidate in (items or []) if isinstance(candidate, dict)]
            if not dedupe:
                return [
                    self._annotate_proof_directed_candidate(candidate)
                    for candidate in normalized_items[:max_questions]
                ]
            return self._select_proof_directed_candidates(
                normalized_items,
                max_questions=max_questions,
                preserve_order=True,
            )

        selected: Any = None
        if callable(selector):
            try:
                selected = selector(normalized_candidates, max_questions=max_questions)
            except TypeError:
                selected = selector(normalized_candidates)
            except Exception:
                selected = None

        if isinstance(selected, list):
            normalized_selected = _finalize(selected, dedupe=True)
            if normalized_selected:
                if self.selector_quality_guard_enabled:
                    normalized_selected = self._annotate_actor_critic_scores(normalized_selected)
                if len(normalized_selected) >= max_questions:
                    if not self.selector_quality_guard_enabled:
                        return normalized_selected[:max_questions]
                    pool_scores = [
                        float(candidate.get('actor_critic_score', 0.0) or 0.0)
                        for candidate in normalized_candidates
                    ]
                    if pool_scores:
                        sorted_pool_scores = sorted(pool_scores, reverse=True)
                        anchor_index = min(len(sorted_pool_scores) - 1, max(0, max_questions - 1))
                        pool_score_floor = float(sorted_pool_scores[anchor_index]) - 0.75
                    else:
                        pool_score_floor = -999.0
                    selected_keys = {
                        (
                            self._normalize_question_text(str(candidate.get('question', ''))),
                            str(candidate.get('type', '')).strip().lower(),
                        )
                        for candidate in normalized_selected
                    }
                    fallback_candidates = [
                        candidate for candidate in normalized_candidates
                        if (
                            self._normalize_question_text(str(candidate.get('question', ''))),
                            str(candidate.get('type', '')).strip().lower(),
                        ) not in selected_keys
                    ]
                    fallback_candidates.sort(
                        key=lambda candidate: (
                            -float(candidate.get('actor_critic_score', 0.0) or 0.0),
                            -float(candidate.get('novelty_score', 1.0) or 0.0),
                            self._default_candidate_sort_key(candidate),
                        )
                    )
                    replacement_queue = list(fallback_candidates)
                    upgraded_selected: List[Dict[str, Any]] = []
                    for candidate in normalized_selected[:max_questions]:
                        if self._is_low_quality_selected_candidate(candidate, pool_score_floor=pool_score_floor) and replacement_queue:
                            upgraded_selected.append(replacement_queue.pop(0))
                        else:
                            upgraded_selected.append(candidate)
                    return _finalize(upgraded_selected, dedupe=True)
                selected_keys = {
                    (
                        self._normalize_question_text(str(candidate.get('question', ''))),
                        str(candidate.get('type', '')).strip().lower(),
                    )
                    for candidate in normalized_selected
                }
                fallback_candidates = [
                    candidate for candidate in normalized_candidates
                    if (
                        self._normalize_question_text(str(candidate.get('question', ''))),
                        str(candidate.get('type', '')).strip().lower(),
                    ) not in selected_keys
                ]
                fallback_candidates.sort(
                    key=lambda candidate: (
                        -float(candidate.get('actor_critic_score', 0.0) or 0.0),
                        -float(candidate.get('novelty_score', 1.0) or 0.0),
                        self._default_candidate_sort_key(candidate),
                    )
                )
                return _finalize(normalized_selected + fallback_candidates, dedupe=True)

        if self.actor_critic_enabled:
            normalized_candidates.sort(
                key=lambda candidate: (
                    -float(candidate.get('actor_critic_score', 0.0) or 0.0),
                    -float(candidate.get('novelty_score', 1.0) or 0.0),
                    self._default_candidate_sort_key(candidate),
                )
            )
        else:
            normalized_candidates.sort(key=self._default_candidate_sort_key)
        return _finalize(normalized_candidates, dedupe=True)

    SEMANTIC_DUPLICATE_REPEAT_LIMIT = 2
    _EXPLAINED_GAP_FAMILIES = frozenset({
        "factual_uncertainty",
        "legal_element_support",
        "contradiction",
        "evidence",
    })
    _SEMANTIC_DUPLICATE_SIMILARITY = 0.84

    def _explained_gap_family(self, candidate: Dict[str, Any]) -> str:
        source = str(candidate.get("candidate_source") or "").strip().lower()
        question_type = str(candidate.get("type") or candidate.get("question_type") or "").strip().lower()
        kind = str(candidate.get("target_kind") or "").strip().lower()
        if kind == "contradiction" or question_type == "contradiction" or "contradict" in source:
            return "contradiction"
        if source == "intake_claim_element_gap" or question_type == "requirement" or kind == "requirement" or source == "dependency_graph_requirement":
            return "legal_element_support"
        if question_type == "evidence" or kind == "proof" or source == "intake_proof_gap":
            return "evidence"
        if kind == "factual" or source == "knowledge_graph_gap" or question_type in {
            "clarification", "timeline", "relationship", "responsible_party", "impact", "remedy",
        }:
            return "factual_uncertainty"
        return ""

    def _stable_explained_id(self, prefix: str, *parts: Any) -> str:
        material = "|".join(str(part or "").strip() for part in parts)
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]
        return f"{prefix}-{digest}"

    def _explained_inquiry_from_candidate(self, candidate: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(candidate, dict):
            return None
        family = self._explained_gap_family(candidate)
        if family not in self._EXPLAINED_GAP_FAMILIES:
            return None
        if self._is_operator_source_gap(candidate) or candidate.get("user_answerability") == "operator_only":
            return None
        target = candidate.get("unresolved_target") if isinstance(candidate.get("unresolved_target"), dict) else {}
        target_id = str(target.get("target_id") or candidate.get("target_id") or "").strip()
        if not target_id:
            return None
        if target_id in self.retired_explained_targets or self.is_question_target_closed(
            target_id, target.get("target_revision") or candidate.get("target_revision"),
        ):
            return None
        if str(target.get("user_answerability") or candidate.get("user_answerability") or "user_observable") != "user_observable":
            return None
        question = str(candidate.get("question") or "").strip()
        if not question:
            return None
        objective_key = str(candidate.get("proof_objective_id") or candidate.get("question_objective_key") or self._question_objective_key(candidate))
        objective_id = self._stable_explained_id("obj", objective_key)
        semantic_key = str(candidate.get("coverage_key") or self._question_coverage_key(candidate) or objective_id)
        why = str(
            candidate.get("why_answer_helps")
            or candidate.get("question_reason")
            or (target.get("why_answer_helps") if isinstance(target, dict) else "")
            or ""
        ).strip()
        if not why:
            why = "This question asks for an unresolved fact, conflict, legal-element detail, or evidence lead."
        expected_information = str(
            candidate.get("expected_information")
            or (target.get("expected_information") if isinstance(target, dict) else "")
            or "Observed events, dates, people, or documents you can recall."
        ).strip()
        update_kind = str(candidate.get("expected_update_kind") or self._question_expected_update_kind(candidate) or "clarify_record")
        inquiry_id = self._stable_explained_id("inq", objective_id, target_id)
        family_reason = {
            "factual_uncertainty": "A factual detail is still uncertain, so later review cannot treat it as established.",
            "legal_element_support": "A legal element still lacks support. The element definition itself is not changed by the answer.",
            "contradiction": "Two accounts conflict, and neither account is treated as proved until you clarify it.",
            "evidence": "A proof lead is still missing, so the element cannot be treated as documented.",
        }[family]
        why_it_matters = f"{why} {family_reason}".strip()
        answer_contract = {
            "objective_id": objective_id,
            "target_id": target_id,
            "expected_information": expected_information,
            "accepts": ["observed_fact", "date", "person", "document_reference"],
            "non_answers": ["unknown", "refused", "skipped"],
            "non_answer_effect": "record_disposition_without_satisfying_legal_requirement",
        }
        update_contract = {
            "objective_id": objective_id,
            "target_id": target_id,
            "target_revision": str(target.get("target_revision") or candidate.get("target_revision") or "unresolved"),
            "update_kind": update_kind,
            "on_answer": "update_or_remove_candidate",
            "on_non_answer": "record_disposition_and_select_next_candidate",
            "satisfies_legal_requirement_on_non_answer": False,
        }
        return {
            "inquiry_id": inquiry_id,
            "objective_id": objective_id,
            "semantic_key": semantic_key,
            "target_id": target_id,
            "target_revision": update_contract["target_revision"],
            "target_kind": str(target.get("target_kind") or candidate.get("target_kind") or ""),
            "gap_family": family,
            "question": question,
            "why_it_matters": why_it_matters,
            "expected_information": expected_information,
            "expected_answer_contract": answer_contract,
            "expected_update_contract": update_contract,
            "candidate": candidate,
        }

    def _semantic_repeat_count(self, inquiry: Dict[str, Any], running: Dict[str, int], kept: List[Dict[str, Any]]) -> int:
        keys = [str(inquiry.get("objective_id") or ""), str(inquiry.get("semantic_key") or "")]
        count = max(int(running.get(key, 0) or 0) for key in keys)
        question = str(inquiry.get("question") or "")
        compared = list(self.presented_question_records) + list(kept)
        for prior in compared:
            if not isinstance(prior, dict):
                continue
            prior_question = str(prior.get("question") or "")
            if not prior_question:
                continue
            same_objective = str(prior.get("objective_id") or "") == str(inquiry.get("objective_id") or "")
            same_semantic = str(prior.get("semantic_key") or "") == str(inquiry.get("semantic_key") or "")
            similar = self._question_text_similarity(question, prior_question) >= self._SEMANTIC_DUPLICATE_SIMILARITY
            if not (same_objective or same_semantic or similar):
                continue
            prior_count = int(prior.get("repeat_count") or running.get(str(prior.get("semantic_key") or ""), 0) or 0)
            if prior in kept:
                prior_count = max(prior_count, 1)
            count = max(count, prior_count if (same_objective or same_semantic or similar) else 0)
            if similar or same_objective or same_semantic:
                count = max(count, int(running.get(str(prior.get("objective_id") or ""), 0) or 0))
                count = max(count, int(running.get(str(prior.get("semantic_key") or ""), 0) or 0))
        return count

    def apply_semantic_duplicate_repeat_policy(
        self,
        inquiries: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Allow a bounded number of semantically duplicate objectives, then stop repeating them."""
        running = dict(self.semantic_repeat_counts)
        for objective_id, count in self.objective_repeat_counts.items():
            running[str(objective_id)] = max(int(running.get(str(objective_id), 0) or 0), int(count or 0))
        kept: List[Dict[str, Any]] = []
        suppressed: List[Dict[str, Any]] = []
        for inquiry in inquiries or []:
            if not isinstance(inquiry, dict):
                continue
            count = self._semantic_repeat_count(inquiry, running, kept)
            if count >= self.SEMANTIC_DUPLICATE_REPEAT_LIMIT:
                suppressed.append({
                    "inquiry_id": inquiry.get("inquiry_id"),
                    "objective_id": inquiry.get("objective_id"),
                    "semantic_key": inquiry.get("semantic_key"),
                    "target_id": inquiry.get("target_id"),
                    "question": inquiry.get("question"),
                    "repeat_count": count,
                    "repeat_limit": self.SEMANTIC_DUPLICATE_REPEAT_LIMIT,
                    "suppressed_reason": "semantic_duplicate_repeat_limit",
                })
                continue
            kept.append(inquiry)
            for key in (inquiry.get("objective_id"), inquiry.get("semantic_key")):
                if key:
                    running[str(key)] = max(int(running.get(str(key), 0) or 0), count) + 1
        return kept, suppressed

    def _mark_explained_inquiry_presented(self, inquiry: Optional[Dict[str, Any]]) -> None:
        if not isinstance(inquiry, dict):
            return
        inquiry_id = str(inquiry.get("inquiry_id") or "")
        if not inquiry_id or inquiry_id in self._presented_inquiry_ids:
            return
        self._presented_inquiry_ids.add(inquiry_id)
        for key_name, store in (
            ("objective_id", self.objective_repeat_counts),
            ("semantic_key", self.semantic_repeat_counts),
        ):
            key = str(inquiry.get(key_name) or "")
            if key:
                store[key] = int(store.get(key, 0) or 0) + 1
        self.presented_question_records.append({
            "inquiry_id": inquiry_id,
            "objective_id": inquiry.get("objective_id"),
            "semantic_key": inquiry.get("semantic_key"),
            "question": inquiry.get("question"),
            "repeat_count": int(self.objective_repeat_counts.get(str(inquiry.get("objective_id") or ""), 1) or 1),
        })

    def select_explained_gap_inquiries(
        self,
        knowledge_graph: KnowledgeGraph,
        dependency_graph: DependencyGraph,
        *,
        intake_case_file: Optional[Dict[str, Any]] = None,
        max_questions: int = 8,
    ) -> List[Dict[str, Any]]:
        """Select explained questions from actionable graph gaps.

        Candidate text comes from ``collect_question_candidates`` and
        ``select_question_candidates``. This method adds stable objective and
        target ids, why the question matters, and the answer/update contract.
        """
        self.load_question_dispositions(intake_case_file)
        budget = max(int(max_questions or 0), 0)
        if budget <= 0:
            self.explained_inquiry_pool = []
            self.current_explained_inquiry = None
            self.suppressed_semantic_duplicates = []
            return []
        raw_candidates = self.collect_question_candidates(
            knowledge_graph,
            dependency_graph,
            max_questions=budget,
            intake_case_file=intake_case_file,
        )
        selected = self.select_question_candidates(
            raw_candidates,
            max_questions=max(budget * 4, budget),
        )
        shaped = []
        for candidate in selected:
            inquiry = self._explained_inquiry_from_candidate(candidate)
            if inquiry is not None:
                shaped.append(inquiry)
        admitted, suppressed = self.apply_semantic_duplicate_repeat_policy(shaped)
        self.suppressed_semantic_duplicates = suppressed
        self.explained_inquiry_pool = admitted[:budget]
        self.current_explained_inquiry = self.explained_inquiry_pool[0] if self.explained_inquiry_pool else None
        self._mark_explained_inquiry_presented(self.current_explained_inquiry)
        return list(self.explained_inquiry_pool)

    def apply_explained_inquiry_answer(
        self,
        answer: Any,
        knowledge_graph: KnowledgeGraph,
        dependency_graph: DependencyGraph,
        *,
        intake_case_file: Optional[Dict[str, Any]] = None,
        inquiry: Optional[Dict[str, Any]] = None,
        disposition: Any = None,
        max_questions: int = 8,
    ) -> Dict[str, Any]:
        """Record one answer, retire that candidate, and select the next gap."""
        current = inquiry if isinstance(inquiry, dict) else self.current_explained_inquiry
        if not isinstance(current, dict):
            raise ValueError("no current explained inquiry")
        question = current.get("candidate") if isinstance(current.get("candidate"), dict) else {}
        classified = self.classify_answer_disposition(answer, explicit=disposition)
        updates = self.process_answer(
            question,
            "" if answer is None else str(answer),
            knowledge_graph,
            dependency_graph,
            source_context={
                "intake_case_file": intake_case_file,
                "disposition": classified,
            },
        )
        if not isinstance(updates, dict):
            updates = {}
        non_fact = classified in self._NON_FACT_DISPOSITIONS
        if non_fact or not updates.get("question_disposition"):
            self.record_question_disposition(
                question,
                answer,
                disposition=classified,
                intake_case_file=intake_case_file,
                creates_fact=False if non_fact else bool(updates.get("creates_fact")),
                satisfies_requirement=False if non_fact else bool(updates.get("satisfies_requirement")),
            )
        satisfies_requirement = False if non_fact else bool(updates.get("satisfies_requirement"))
        target_id = str(current.get("target_id") or "")
        if target_id:
            self.retired_explained_targets.add(target_id)
        self._mark_explained_inquiry_presented(current)
        self.explained_inquiry_pool = [
            item for item in self.explained_inquiry_pool
            if str(item.get("target_id") or "") != target_id
        ]
        refreshed = self.select_explained_gap_inquiries(
            knowledge_graph,
            dependency_graph,
            intake_case_file=intake_case_file,
            max_questions=max_questions,
        )
        next_inquiry = self.current_explained_inquiry
        if isinstance(next_inquiry, dict) and str(next_inquiry.get("target_id") or "") == target_id:
            alternatives = [item for item in refreshed if str(item.get("target_id") or "") != target_id]
            if alternatives:
                next_inquiry = alternatives[0]
                self.current_explained_inquiry = next_inquiry
                self.explained_inquiry_pool = alternatives
            else:
                revised = dict(next_inquiry)
                revised["target_revision"] = str(int(str(revised.get("target_revision") or "0") or 0) + 1) if str(revised.get("target_revision") or "").isdigit() else str(revised.get("target_revision") or "unresolved") + ":updated"
                revised["why_it_matters"] = str(revised.get("why_it_matters") or "") + " The previous answer changed this candidate, and it remains open."
                next_inquiry = revised
                self.current_explained_inquiry = revised
        return {
            "disposition": classified,
            "recorded_as": classified if non_fact else "answered",
            "satisfies_requirement": satisfies_requirement,
            "removed_target_id": target_id,
            "objective_id": current.get("objective_id"),
            "inquiry_id": current.get("inquiry_id"),
            "next_inquiry": next_inquiry,
            "inquiries": list(self.explained_inquiry_pool),
            "updates": {
                "disposition": updates.get("disposition", classified),
                "creates_fact": False if non_fact else bool(updates.get("creates_fact")),
                "satisfies_requirement": satisfies_requirement,
                "requirements_satisfied": 0 if non_fact else int(updates.get("requirements_satisfied") or 0),
            },
        }

    def _ensure_standard_intake_questions(self, questions: List[Dict[str, Any]], max_questions: int) -> List[Dict[str, Any]]:
        if len(questions) >= max_questions:
            return questions

        existing_text = " ".join([q.get('question', '') for q in questions]).lower()
        added: List[Dict[str, Any]] = []
        revision = self._question_scope_revision or "standard-intake"

        def _slot_open(slot: str, kind: str) -> bool:
            target_id = f"{kind}:standard-intake:{slot}"
            if any(
                str((q.get("unresolved_target") or {}).get("target_id") or q.get("target_id") or "") == target_id
                for q in questions + added
                if isinstance(q, dict)
            ):
                return False
            return not self.is_question_target_closed(target_id, revision)

        timeline_text = (
            'What is the timeline of key events, including dates, who made each decision, what notice or communication you received, and when you requested help or accommodation?'
        )
        if len(questions) + len(added) < max_questions:
            if not any(q.get('type') == 'timeline' for q in questions) and not any(k in existing_text for k in ['timeline', 'when did', 'what date', 'dates', 'notice', 'who made']):
                if not self._already_asked(timeline_text) and _slot_open("timeline", "factual"):
                    added.append(self._question_candidate(
                        source='standard_intake_backstop',
                        question_type='timeline',
                        question_text=timeline_text,
                        context={
                            "standard_intake_slot": "timeline",
                            "target_revision": revision,
                        },
                        priority='high',
                    ))

        impact_text = (
            'What harm did you experience (financial, emotional, professional), what outcome or remedy are you seeking, and what notices, letters, or messages document that harm?'
        )
        if len(questions) + len(added) < max_questions:
            if not any(q.get('type') in {'impact', 'remedy'} for q in questions) and not any(k in existing_text for k in ['harm', 'damages', 'remedy', 'seeking', 'notice', 'letter', 'message']):
                if not self._already_asked(impact_text) and _slot_open("impact", "factual"):
                    added.append(self._question_candidate(
                        source='standard_intake_backstop',
                        question_type='impact',
                        question_text=impact_text,
                        context={
                            "standard_intake_slot": "impact",
                            "target_revision": revision,
                        },
                        priority='high',
                    ))

            notice_text = (
                "What exact notice, letter, email, or message did you receive, on what date, and who sent it?"
            )
            if len(questions) + len(added) < max_questions:
                if not any(q.get('type') == 'evidence' for q in questions) and not any(k in existing_text for k in ['notice', 'letter', 'email', 'message', 'sent it']):
                    if not self._already_asked(notice_text) and _slot_open("notice", "proof"):
                        added.append(self._question_candidate(
                            source='standard_intake_backstop',
                            question_type='evidence',
                            question_text=notice_text,
                            context={
                                "standard_intake_slot": "notice",
                                "target_revision": revision,
                            },
                            priority='high',
                        ))

        if not added:
            return questions

        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        combined = questions + added
        combined.sort(
            key=lambda q: (
                int(q.get('proof_priority', self._phase1_proof_priority(q.get('type', '')))),
                priority_order.get(q.get('priority', 'low'), 3),
            )
        )
        return combined[:max_questions]

    def _make_question_recommendation_id(
        self,
        claim_type: str,
        lane: str,
        target_claim_element_id: str,
        question_text: str,
    ) -> str:
        normalized_claim = re.sub(r'[^a-z0-9]+', '_', (claim_type or 'claim').lower()).strip('_') or 'claim'
        digest = hashlib.sha1(
            f"{normalized_claim}|{lane}|{target_claim_element_id}|{question_text}".encode('utf-8')
        ).hexdigest()[:12]
        return f"question:{normalized_claim}:{digest}"

    def _build_review_question_recommendation(
        self,
        *,
        claim_type: str,
        lane: str,
        target_claim_element_id: str,
        target_claim_element_text: str,
        question_text: str,
        question_reason: str,
        expected_proof_gain: str,
        supporting_evidence_summary: str,
        current_status: str,
        missing_support_kinds: Optional[List[str]] = None,
        contradiction_fact_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        normalized_text = self._with_empathy(question_text, lane)
        return {
            'question_id': self._make_question_recommendation_id(
                claim_type,
                lane,
                target_claim_element_id,
                normalized_text,
            ),
            'question_text': normalized_text,
            'target_claim_type': claim_type,
            'target_claim_element_id': target_claim_element_id,
            'target_claim_element_text': target_claim_element_text,
            'question_lane': lane,
            'question_reason': question_reason,
            'expected_proof_gain': expected_proof_gain,
            'supporting_evidence_summary': supporting_evidence_summary,
            'current_status': current_status,
            'missing_support_kinds': list(missing_support_kinds or []),
            'contradiction_fact_ids': list(contradiction_fact_ids or []),
            'suppression_key': self._normalize_question_text(normalized_text),
        }

    @staticmethod
    def _primary_quality_signal_for_summary(quality_summary: Dict[str, Any]) -> Dict[str, Any]:
        signal_counts = (
            quality_summary.get('quality_signal_counts', {})
            if isinstance(quality_summary.get('quality_signal_counts'), dict)
            else {}
        )
        prioritized = [
            ('structurally_missing_support', 'missing_element', 'collect_initial_support'),
            ('weak_graph_connectivity', 'graph_quality_gap', 'persist_or_query_graph_support'),
            ('weak_source_quality', 'source_quality_gap', 'improve_source_parse_quality'),
            ('duplicate_support', 'duplicate_support', 'collect_independent_support'),
            ('weak_support_path', 'support_quality_gap', 'strengthen_support_path'),
        ]
        for signal, lane, action in prioritized:
            count = int(signal_counts.get(signal, 0) or 0)
            if signal == 'structurally_missing_support':
                count = max(count, int(quality_summary.get('structurally_missing_path_count', 0) or 0))
            if signal == 'weak_support_path':
                count = max(count, int(quality_summary.get('weak_support_path_count', 0) or 0))
            if count > 0:
                return {
                    'signal_type': signal,
                    'question_lane': lane,
                    'follow_up_action': action,
                    'count': count,
                }
        recommended_action = str(quality_summary.get('recommended_quality_action') or '')
        if recommended_action:
            return {
                'signal_type': 'recommended_quality_action',
                'question_lane': 'support_quality_gap',
                'follow_up_action': recommended_action,
                'count': 1,
            }
        return {}

    def generate_review_question_recommendations(
        self,
        claim_type: str,
        gap_claim: Optional[Dict[str, Any]] = None,
        contradiction_claim: Optional[Dict[str, Any]] = None,
        max_questions: int = 6,
    ) -> List[Dict[str, Any]]:
        recommendations: List[Dict[str, Any]] = []
        seen_keys: Set[str] = set()
        normalized_claim_type = (claim_type or 'claim').strip() or 'claim'

        contradiction_candidates = []
        if isinstance(contradiction_claim, dict):
            contradiction_candidates = contradiction_claim.get('candidates', []) or []
        for candidate in contradiction_candidates:
            if not isinstance(candidate, dict):
                continue
            element_id = str(candidate.get('claim_element_id') or '')
            element_text = str(candidate.get('claim_element_text') or element_id or 'this element')
            overlap_terms = list(candidate.get('overlap_terms', []) or [])
            overlap_snippet = ', '.join(overlap_terms[:3]) if overlap_terms else 'the current support record'
            recommendation = self._build_review_question_recommendation(
                claim_type=normalized_claim_type,
                lane='contradiction_resolution',
                target_claim_element_id=element_id,
                target_claim_element_text=element_text,
                question_text=(
                    f"The current support for {element_text} conflicts. "
                    "What do you recall about each account, and what dates, documents, or records can you provide?"
                ),
                question_reason=(
                    f"Resolve a contradiction before collecting more support for {element_text}. "
                    f"The conflicting records overlap on {overlap_snippet}."
                ),
                expected_proof_gain='high',
                supporting_evidence_summary=(
                    f"Conflicting facts: {len(candidate.get('fact_ids', []) or [])}"
                ),
                current_status='contradicted',
                contradiction_fact_ids=candidate.get('fact_ids', []),
            )
            if recommendation['suppression_key'] in seen_keys:
                continue
            seen_keys.add(recommendation['suppression_key'])
            recommendations.append(recommendation)
            if len(recommendations) >= max_questions:
                return recommendations[:max_questions]

        unresolved_elements = []
        if isinstance(gap_claim, dict):
            unresolved_elements = gap_claim.get('unresolved_elements', []) or []
        for element in unresolved_elements:
            if not isinstance(element, dict):
                continue
            element_id = str(element.get('element_id') or '')
            element_text = str(element.get('element_text') or element_id or 'this element')
            status = str(element.get('status') or 'missing')
            missing_support_kinds = [
                str(kind) for kind in (element.get('missing_support_kinds', []) or []) if kind
            ]
            total_links = int(element.get('total_links', 0) or 0)
            fact_count = int(element.get('fact_count', 0) or 0)
            recommended_action = str(element.get('recommended_action') or '')
            support_quality_summary = (
                element.get('support_quality_summary', {})
                if isinstance(element.get('support_quality_summary'), dict)
                else {}
            )
            quality_signal_counts = (
                support_quality_summary.get('quality_signal_counts', {})
                if isinstance(support_quality_summary.get('quality_signal_counts'), dict)
                else {}
            )

            lane = 'testimony'
            if recommended_action == 'improve_parse_quality':
                lane = 'document_request'
            elif int(quality_signal_counts.get('weak_source_quality', 0) or 0) > 0:
                lane = 'document_request'
            elif int(quality_signal_counts.get('duplicate_support', 0) or 0) > 0:
                lane = 'document_request'
            elif (
                recommended_action in {'strengthen_support_path', 'review_support_quality'}
                or int(quality_signal_counts.get('weak_graph_connectivity', 0) or 0) > 0
            ):
                lane = 'testimony'
            elif missing_support_kinds == ['authority']:
                lane = 'authority_clarification'
            elif 'evidence' in missing_support_kinds or total_links == 0 or fact_count == 0:
                lane = 'testimony'
            elif 'authority' in missing_support_kinds:
                lane = 'authority_clarification'

            if lane == 'document_request':
                if int(quality_signal_counts.get('duplicate_support', 0) or 0) > 0:
                    question_text = f"Do you have an independent document, message, witness, or record that separately supports {element_text}?"
                    question_reason = (
                        f"{element_text} appears to rely on duplicate or non-independent support, so a distinct source would strengthen the proof path."
                    )
                else:
                    question_text = f"Do you have a clearer document, message, timeline, or record that supports {element_text}?"
                    question_reason = (
                        f"{element_text} has some support, but the current records indicate a parse, source-quality, or document-quality gap."
                    )
            elif lane == 'authority_clarification':
                question_text = f"Is there a rule, policy, statute, or case that clearly supports {element_text}?"
                question_reason = (
                    f"{element_text} is still missing authority support needed for legal review."
                )
            elif (
                recommended_action in {'strengthen_support_path', 'review_support_quality'}
                or int(quality_signal_counts.get('weak_graph_connectivity', 0) or 0) > 0
            ):
                question_text = (
                    f"What additional facts, source details, or relationships connect the current support "
                    f"more directly to {element_text}?"
                )
                question_reason = (
                    f"{element_text} has support, but GraphRAG support-path scoring found a structural quality gap "
                    "such as weak graph connectivity or an indirect support path."
                )
            else:
                question_text = f"What specific facts can you provide to support {element_text}?"
                question_reason = (
                    f"{element_text} is unresolved and needs clearer testimony or factual detail."
                )

            recommendation = self._build_review_question_recommendation(
                claim_type=normalized_claim_type,
                lane=lane,
                target_claim_element_id=element_id,
                target_claim_element_text=element_text,
                question_text=question_text,
                question_reason=question_reason,
                expected_proof_gain='high' if status == 'missing' else 'medium',
                supporting_evidence_summary=(
                    f"Current support: {total_links} links, {fact_count} facts"
                    + (f"; missing {', '.join(missing_support_kinds)}" if missing_support_kinds else '')
                ),
                current_status=status,
                missing_support_kinds=missing_support_kinds,
            )
            recommendation['support_quality_summary'] = support_quality_summary
            recommendation['quality_signal_counts'] = dict(quality_signal_counts)
            primary_quality_signal = self._primary_quality_signal_for_summary(support_quality_summary)
            recommendation['primary_quality_signal'] = primary_quality_signal
            recommendation['quality_follow_up_action'] = primary_quality_signal.get('follow_up_action', '')
            if recommendation['suppression_key'] in seen_keys:
                continue
            seen_keys.add(recommendation['suppression_key'])
            recommendations.append(recommendation)
            if len(recommendations) >= max_questions:
                break

        return recommendations[:max_questions]
    
    def generate_questions(self, 
                          knowledge_graph: KnowledgeGraph,
                          dependency_graph: DependencyGraph,
                          max_questions: int = 10,
                          intake_case_file: Optional[Dict[str, Any]] = None,
                          additional_candidates: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """
        Generate questions to denoise the complaint.
        
        Args:
            knowledge_graph: Current knowledge graph
            dependency_graph: Current dependency graph
            max_questions: Maximum number of questions to generate
            
        Returns:
            List of question dictionaries with type, question text, and context
        """
        self.load_question_dispositions(intake_case_file)
        legal_context_targets = self._current_legal_context_question_targets(knowledge_graph, intake_case_file)
        # Subsequent public answer turns do not pass additional_candidates.
        # Rederive their open context prompts instead of losing them after turn one.
        if additional_candidates is None:
            additional_candidates = [
                {'type': 'legal_context', 'question_id': item['question_id'],
                 'field': item['field'], 'question': item['prompt'], 'priority': 'critical'}
                for item in legal_context_targets.values()
            ]
        questions = self.collect_question_candidates(
            knowledge_graph,
            dependency_graph,
            max_questions=max_questions,
            intake_case_file=intake_case_file,
        )
        # Context questions join the same selection pass as graph questions.
        questions = [candidate for candidate in (additional_candidates or [])
                     if isinstance(candidate, dict)] + questions
        prepared = []
        for candidate in questions:
            if str(candidate.get('type') or candidate.get('question_type') or '').strip().lower() == 'legal_context':
                candidate = self._bind_unresolved_target(candidate, legal_context_targets=legal_context_targets)
                if not candidate.get('unresolved_target'):
                    continue
            prepared.append(candidate)
        questions = prepared
        selector = getattr(self.mediator, 'select_intake_question_candidates', None) if self.mediator else None
        questions = self.select_question_candidates(
            questions,
            max_questions=max_questions,
            selector=selector,
            legal_context_targets=legal_context_targets,
        )

        # Ensure we cover basic intake dimensions beyond evidence-only prompts.
        questions = self._ensure_standard_intake_questions(questions, max_questions)

        # Optional exploration/momentum policy (reorders questions only).
        questions = self._apply_exploration_and_momentum(questions)

        # Light empathy / framing tweaks (text-only; doesn't change structure).
        for q in questions:
            qtype = q.get('type', '')
            qtext = q.get('question', '')
            q['question'] = self._with_empathy(qtext, qtype)

        self._record_source_capability_diagnostic(intake_case_file)
        self._record_operator_candidates(list(additional_candidates or []) + list(questions))
        questions = self._finalize_neutral_targeted_questions(questions, legal_context_targets=legal_context_targets)

        # Track questions in pool
        self.questions_pool.extend(questions[:max_questions])

        return questions[:max_questions]
    
    def process_answer(self, question: Dict[str, Any], answer: str,
                      knowledge_graph: KnowledgeGraph,
                      dependency_graph: Optional[DependencyGraph] = None,
                      *,
                      answer_event_id: Optional[str] = None,
                      source_context: Optional[Dict[str, Any]] = None,
                      factual_action: Optional[str] = None,
                      supersedes_stable_id: Optional[str] = None,
                      retracts_stable_id: Optional[str] = None,
                      contradicts_stable_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Process an answer to a denoising question.

        Args:
            question: The question that was asked
            answer: The user's answer
            knowledge_graph: Knowledge graph to update
            dependency_graph: Optional dependency graph to update

        Returns:
            Information about what was updated
        """
        from complaint_phases.knowledge_graph import answer_event_payload

        event_payload = answer_event_payload(
            question=question,
            answer=answer,
            source_context=source_context,
            factual_action=factual_action,
            supersedes_stable_id=supersedes_stable_id,
            retracts_stable_id=retracts_stable_id,
            contradicts_stable_id=contradicts_stable_id,
        )
        if answer_event_id and knowledge_graph is not None:
            prior = knowledge_graph.begin_answer_event(answer_event_id, event_payload)
            if prior is not None and prior.get("denoiser_updates") is not None:
                return dict(prior["denoiser_updates"])
        explicit_disposition = None
        if isinstance(question, dict):
            explicit_disposition = question.get("disposition") or question.get("answer_disposition")
        if explicit_disposition in (None, "") and isinstance(source_context, dict):
            explicit_disposition = source_context.get("disposition") or source_context.get("answer_disposition")
        # A stored question label cannot turn "I don't know" or a refusal into a fact.
        answer_disposition = self.classify_answer_disposition(answer)
        if answer_disposition in self._NON_FACT_DISPOSITIONS:
            classified_disposition = answer_disposition
        else:
            classified_disposition = self.classify_answer_disposition(answer, explicit=explicit_disposition)
        if isinstance(question, dict) and str(question.get('type') or '').strip().lower() == 'legal_context':
            updates = self._process_legal_context_answer(
                question, answer, knowledge_graph, source_context,
                classified_disposition, factual_action=factual_action,
            )
            self.questions_asked.append({'question': question, 'answer': answer,
                                         'answer_event_id': answer_event_id,
                                         'disposition': updates['disposition'],
                                         'creates_fact': False, 'satisfies_requirement': False})
            if answer_event_id and knowledge_graph is not None:
                knowledge_graph.finish_answer_event(answer_event_id, event_payload,
                                                    denoiser_updates=dict(updates))
            return updates
        if classified_disposition in self._NON_FACT_DISPOSITIONS:
            record = self.record_question_disposition(
                question if isinstance(question, dict) else {},
                answer,
                disposition=classified_disposition,
                intake_case_file=(source_context or {}).get("intake_case_file") if isinstance(source_context, dict) else None,
            )
            updates = self._non_fact_answer_updates(classified_disposition, record)
            self.questions_asked.append({
                'question': question,
                'answer': answer,
                'answer_event_id': answer_event_id,
                'disposition': classified_disposition,
                'creates_fact': False,
                'satisfies_requirement': False,
                'contradictory_conclusion': False,
            })
            if answer_event_id and knowledge_graph is not None:
                knowledge_graph.finish_answer_event(
                    answer_event_id,
                    event_payload,
                    denoiser_updates=dict(updates),
                )
            return updates
        if factual_action:
            updates = self._process_factual_revision(
                question,
                answer,
                knowledge_graph,
                dependency_graph=dependency_graph,
                factual_action=factual_action,
                source_context=source_context,
                supersedes_stable_id=supersedes_stable_id,
                retracts_stable_id=retracts_stable_id,
                contradicts_stable_id=contradicts_stable_id,
                answer_event_id=answer_event_id,
            )
            self.questions_asked.append({
                'question': question,
                'answer': answer,
                'answer_event_id': answer_event_id,
                'factual_action': factual_action,
            })
            if answer_event_id and knowledge_graph is not None:
                knowledge_graph.finish_answer_event(
                    answer_event_id,
                    event_payload,
                    denoiser_updates=dict(updates),
                )
            return updates

        self.questions_asked.append({
            'question': question,
            'answer': answer
        })

        updates = {
            'entities_updated': 0,
            'relationships_added': 0,
            'requirements_satisfied': 0
        }

        question_type = str(question.get('type') or '').strip().lower()
        context = question.get('context', {})
        context = context if isinstance(context, dict) else {}
        answer_text = str(answer or '').strip()
        workflow_phase = str(
            context.get('workflow_phase')
            or question.get('workflow_phase')
            or self._workflow_phase_for_question(question_type, context, str(question.get('candidate_source') or ''))
        ).strip().lower()
        question_objective = str(
            question.get('question_objective')
            or context.get('question_objective')
            or ''
        ).strip().lower()
        expected_update_kind = str(
            question.get('expected_update_kind')
            or context.get('expected_update_kind')
            or ''
        ).strip().lower()
        target_element_id = str(
            question.get('target_element_id')
            or context.get('target_element_id')
            or context.get('requirement_id')
            or ''
        ).strip().lower()
        extraction_targets = {
            str(item).strip().lower()
            for item in (
                context.get('extraction_targets')
                or question.get('extraction_targets')
                or []
            )
            if str(item).strip()
        }
        patchability_markers = {
            str(item).strip().lower()
            for item in (
                context.get('patchability_markers')
                or question.get('patchability_markers')
                or []
            )
            if str(item).strip()
        }
        timeline_enrichment_types = {'clarification', 'evidence', 'impact', 'relationship', 'remedy', 'requirement', 'responsible_party', 'timeline'}
        responsible_party_enrichment_types = {'clarification', 'evidence', 'relationship', 'requirement', 'responsible_party', 'timeline'}
        fallback_timeline_fact_types = {'clarification', 'evidence', 'relationship', 'requirement', 'responsible_party', 'timeline'}
        low_information_tokens = {
            '', 'n/a', 'na', 'none', 'unknown', 'not sure', 'unsure', 'no idea', 'i do not know', "i don't know",
        }
        gap_type = str(context.get('gap_type') or '').strip().lower()
        answer_contract = context.get('answer_contract') if isinstance(context.get('answer_contract'), dict) else {}
        contract_required_fields = [
            str(field).strip().lower()
            for field in (
                answer_contract.get('required_fields')
                or context.get('required_fields')
                or []
            )
            if str(field).strip()
        ]
        contract_required_fields = list(dict.fromkeys(contract_required_fields))
        contract_missing_required_fields = {
            str(field).strip().lower()
            for field in (
                answer_contract.get('missing_required_fields')
                or context.get('missing_required_fields')
                or []
            )
            if str(field).strip()
        }
        contract_requirement_updates = {
            str(field).strip().lower()
            for field in (
                answer_contract.get('requirement_updates')
                or context.get('requirement_updates')
                or []
            )
            if str(field).strip()
        }
        contract_entity_updates = {
            str(field).strip().lower()
            for field in (
                answer_contract.get('entity_updates')
                or context.get('entity_updates')
                or []
            )
            if str(field).strip()
        }
        contract_relationship_updates = {
            str(field).strip().lower()
            for field in (
                answer_contract.get('relationship_updates')
                or context.get('relationship_updates')
                or []
            )
            if str(field).strip()
        }
        contract_single_turn_closable = bool(
            answer_contract.get('single_turn_closable')
            or context.get('single_turn_closable')
        )
        contract_single_field_closable = bool(
            answer_contract.get('single_field_closable')
            or context.get('single_field_closable')
        )
        contract_deterministically_closable = bool(
            answer_contract.get('deterministically_closable')
            or context.get('deterministically_closable')
        )
        deterministic_requirement_tokens_updated: Set[str] = set()
        deterministic_relationship_tokens_updated: Set[str] = set()
        deterministic_entity_tokens_updated: Set[str] = set()
        deterministic_plan_fields_captured: Set[str] = set()
        expected_modalities = {
            str(item).strip().lower()
            for item in (context.get('expected_evidence_modalities') or [])
            if str(item).strip()
        }
        weak_modalities = {
            str(item).strip().lower()
            for item in (context.get('weak_evidence_modalities') or [])
            if str(item).strip()
        }
        answer_lower = answer_text.lower()
        extracted_dates = self._extract_date_strings(answer_text)
        response_timing_phrases = self._extract_response_timing_phrases(answer_text)
        document_mentions = self._extract_document_mentions(answer_text)
        named_role_people = self._extract_named_role_people(answer_text)
        named_title_people = self._extract_named_people_with_titles(answer_text)
        org_candidates = self._extract_org_candidates(answer_text)
        generic_roles = self._extract_generic_roles(answer_text)
        has_sequence_signal = self._contains_sequence_signal(answer_text)
        has_causation_signal = self._contains_causation_signal(answer_text)
        has_adverse_action_signal = self._contains_adverse_action_signal(answer_text)
        has_document_precision_signal = self._contains_document_precision_signal(answer_text)
        deterministic_fields_updated: Set[str] = set()

        def _extract_contextual_dates(text_value: str) -> Dict[str, List[str]]:
            buckets: Dict[str, List[str]] = {
                'hearing_request_dates': [],
                'response_dates': [],
                'adverse_action_dates': [],
                'protected_activity_dates': [],
                'decision_dates': [],
                'document_dates': [],
            }
            if not text_value:
                return buckets
            segments = re.split(r'(?<=[.!?;])\s+|\n+', text_value)
            for segment in segments:
                snippet = str(segment or '').strip()
                if not snippet:
                    continue
                dates_in_segment = self._extract_date_strings(snippet)
                if not dates_in_segment:
                    continue
                lower_segment = snippet.lower()
                for date_value in dates_in_segment:
                    if any(token in lower_segment for token in ('hearing', 'appeal', 'requested hearing', 'request hearing', 'grievance hearing')):
                        buckets['hearing_request_dates'] = self._append_unique_text_item(
                            buckets.get('hearing_request_dates'),
                            date_value,
                        )
                    if any(token in lower_segment for token in ('responded', 'response', 'replied', 'reply', 'ignored', 'no response', 'never responded')):
                        buckets['response_dates'] = self._append_unique_text_item(
                            buckets.get('response_dates'),
                            date_value,
                        )
                    if any(token in lower_segment for token in ('denied', 'evicted', 'terminated', 'fired', 'adverse action', 'decision', 'notice', 'rejected')):
                        buckets['adverse_action_dates'] = self._append_unique_text_item(
                            buckets.get('adverse_action_dates'),
                            date_value,
                        )
                    if any(token in lower_segment for token in ('complained', 'reported', 'protected activity', 'grievance', 'accommodation', 'discrimination complaint')):
                        buckets['protected_activity_dates'] = self._append_unique_text_item(
                            buckets.get('protected_activity_dates'),
                            date_value,
                        )
                    if any(token in lower_segment for token in ('decision', 'determination', 'final decision', 'ruling')):
                        buckets['decision_dates'] = self._append_unique_text_item(
                            buckets.get('decision_dates'),
                            date_value,
                        )
                    if any(token in lower_segment for token in ('notice', 'letter', 'email', 'message', 'memo', 'policy', 'document')):
                        buckets['document_dates'] = self._append_unique_text_item(
                            buckets.get('document_dates'),
                            date_value,
                        )
            return buckets

        contextual_dates = _extract_contextual_dates(answer_text)

        def _single_claim_id() -> Optional[str]:
            claims = knowledge_graph.get_entities_by_type('claim')
            return claims[0].id if len(claims) == 1 else None

        def _single_claim_entity() -> Optional[Entity]:
            claim_id = _single_claim_id()
            return knowledge_graph.get_entity(claim_id) if claim_id else None

        def _answer_is_substantive(text_value: str) -> bool:
            normalized = " ".join(str(text_value or '').strip().lower().split())
            if not normalized:
                return False
            if normalized in low_information_tokens:
                return False
            if len(normalized) < 8:
                return False
            if self._contains_confirmation_placeholder(normalized):
                return False
            return True

        def _extract_file_references(text_value: str) -> List[str]:
            if not text_value:
                return []
            refs: List[str] = []
            for pattern in (
                r"\b[\w\-./]+\.(?:pdf|docx?|xlsx?|csv|txt|jpg|jpeg|png|gif|msg|eml)\b",
                r"\"([^\"]+\.(?:pdf|docx?|xlsx?|csv|txt|jpg|jpeg|png|gif|msg|eml))\"",
                r"'([^']+\.(?:pdf|docx?|xlsx?|csv|txt|jpg|jpeg|png|gif|msg|eml))'",
            ):
                for match in re.findall(pattern, text_value, flags=re.IGNORECASE):
                    candidate = str(match or "").strip()
                    if candidate and candidate not in refs:
                        refs.append(candidate)
            return refs[:6]

        def _extract_policy_references(text_value: str) -> List[str]:
            if not text_value:
                return []
            refs: List[str] = []
            for match in re.findall(
                r"\b([A-Z][A-Za-z0-9/&\-\s]{2,80}(?:Policy|Handbook|Manual|Rule|Procedure|Guideline|Code))\b",
                text_value,
            ):
                candidate = str(match or "").strip()
                if candidate and candidate not in refs:
                    refs.append(candidate)
            for match in re.findall(r"\b(section\s+\d+(?:\.\d+)*)\b", text_value, flags=re.IGNORECASE):
                candidate = str(match or "").strip()
                if candidate and candidate not in refs:
                    refs.append(candidate)
            return refs[:6]

        extracted_file_refs = _extract_file_references(answer_text)
        extracted_policy_refs = _extract_policy_references(answer_text)
        contract_missing_field_plan = [
            plan
            for plan in (answer_contract.get('missing_field_update_plan') or context.get('missing_field_update_plan') or [])
            if isinstance(plan, dict)
        ]
        policy_signal = any(token in answer_lower for token in ('policy', 'handbook', 'rule', 'criteria', 'section', 'guideline')) or bool(extracted_policy_refs)
        file_signal = bool(extracted_file_refs) or bool(document_mentions) or any(token in answer_lower for token in ('file', 'upload', 'attachment', 'exhibit', 'pdf', 'screenshot', 'scan'))
        staff_signal = bool(named_role_people or named_title_people or generic_roles)

        def _has_structured_signal() -> bool:
            return bool(
                extracted_dates
                or response_timing_phrases
                or staff_signal
                or has_sequence_signal
                or has_causation_signal
                or has_adverse_action_signal
                or policy_signal
                or file_signal
            )

        def _find_claim_entity_from_context() -> Optional[Entity]:
            for key in ('claim_entity_id', 'claim_id'):
                candidate_id = str(context.get(key) or '').strip()
                if not candidate_id:
                    continue
                entity = knowledge_graph.get_entity(candidate_id)
                if entity and entity.type == 'claim':
                    return entity
            claim_name = str(context.get('claim_name') or '').strip().lower()
            if claim_name:
                for entity in knowledge_graph.get_entities_by_type('claim'):
                    entity_name = str(entity.name or '').strip().lower()
                    if entity_name == claim_name or claim_name in entity_name or entity_name in claim_name:
                        return entity
            return _single_claim_entity()

        def _append_attr_list(entity: Optional[Entity], key: str, value: str) -> bool:
            if not entity:
                return False
            updated = self._append_unique_text_item((entity.attributes or {}).get(key), value)
            previous = (entity.attributes or {}).get(key)
            if previous != updated:
                entity.attributes[key] = updated
                return True
            return False

        def _mark_resolved_gap(claim_entity: Optional[Entity]) -> None:
            nonlocal updates
            if not claim_entity:
                return
            deterministic_key = str(context.get('deterministic_update_key') or '').strip().lower()
            gap_id = str(context.get('gap_id') or '').strip().lower()
            requirement_id = str(context.get('requirement_id') or context.get('target_element_id') or '').strip().lower()
            resolution_key = deterministic_key or gap_id or requirement_id
            if not resolution_key:
                return
            changed = _append_attr_list(claim_entity, 'resolved_gaps', resolution_key)
            if changed:
                updates['entities_updated'] += 1

        def _append_claim_signal(claim_entity: Optional[Entity], key: str, value: str) -> None:
            nonlocal updates
            if not value:
                return
            if _append_attr_list(claim_entity, key, value):
                updates['entities_updated'] += 1

        def _required_fields_for_gap(current_gap_type: str) -> List[str]:
            mapping = {
                'missing_exact_action_dates': ['event_date', 'adverse_action'],
                'missing_hearing_request_date': ['hearing_request_date', 'hearing_request_actor'],
                'missing_response_dates': ['response_date', 'response_actor'],
                'missing_hearing_timing': ['adverse_action_date', 'hearing_request_date'],
                'missing_staff_identity': ['staff_name', 'staff_role'],
                'missing_staff_title': ['staff_name', 'staff_title'],
                'retaliation_missing_causation': ['protected_activity', 'adverse_action', 'causation_link'],
                'retaliation_missing_causation_link': ['protected_activity', 'adverse_action', 'causation_link'],
                'retaliation_missing_sequence': ['protected_activity_date', 'adverse_action_date'],
                'retaliation_missing_sequencing_dates': ['protected_activity_date', 'adverse_action_date'],
                'missing_written_notice': ['document_name', 'document_date', 'issuing_actor'],
                'missing_decision_timeline': ['decision_date', 'decision_actor'],
                'missing_claim_element': ['supporting_fact'],
                'missing_proof_leads': ['supporting_fact'],
            }
            fields: List[str] = list(mapping.get(str(current_gap_type or '').strip().lower(), []))
            for contract_field in contract_required_fields:
                if contract_field not in fields:
                    fields.append(contract_field)
            return fields

        def _store_required_field_value(claim_entity: Optional[Entity], field_name: str, value: str) -> None:
            nonlocal updates
            if not claim_entity:
                return
            normalized_field = str(field_name or '').strip().lower()
            normalized_value = str(value or '').strip()
            if not normalized_field or not normalized_value:
                return
            attrs = claim_entity.attributes if isinstance(claim_entity.attributes, dict) else {}
            field_values = attrs.get('required_field_values')
            field_values = dict(field_values) if isinstance(field_values, dict) else {}
            existing_values = field_values.get(normalized_field)
            updated_values = self._append_unique_text_item(existing_values, normalized_value)
            if existing_values != updated_values:
                field_values[normalized_field] = updated_values
                attrs['required_field_values'] = field_values
                claim_entity.attributes = attrs
                updates['entities_updated'] += 1
                deterministic_fields_updated.add(normalized_field)
                _append_claim_signal(claim_entity, 'satisfied_requirements', normalized_field)

        def _link_claim_to_entity(claim_entity: Optional[Entity], target_entity: Optional[Entity], relation_type: str, confidence: float = 0.62) -> None:
            nonlocal updates
            if not claim_entity or not target_entity or not relation_type:
                return
            _, rel_created = self._add_relationship_if_missing(
                knowledge_graph,
                claim_entity.id,
                target_entity.id,
                relation_type,
                confidence,
            )
            if rel_created:
                updates['relationships_added'] += 1

        def _required_field_has_value(claim_entity: Optional[Entity], field_name: str) -> bool:
            if not claim_entity or not field_name:
                return False
            attrs = claim_entity.attributes if isinstance(claim_entity.attributes, dict) else {}
            field_values = attrs.get('required_field_values')
            field_values = field_values if isinstance(field_values, dict) else {}
            value = field_values.get(str(field_name or '').strip().lower())
            if isinstance(value, list):
                return any(str(item).strip() for item in value)
            return bool(str(value or '').strip())

        def _candidate_value_for_required_field(field_name: str) -> str:
            normalized = str(field_name or '').strip().lower()
            if not normalized:
                return ''
            if normalized in {'event_date', 'hearing_request_date', 'response_date', 'adverse_action_date', 'decision_date', 'protected_activity_date', 'document_date'}:
                if normalized == 'hearing_request_date' and contextual_dates.get('hearing_request_dates'):
                    return str((contextual_dates.get('hearing_request_dates') or [''])[0]).strip()
                if normalized == 'response_date' and contextual_dates.get('response_dates'):
                    return str((contextual_dates.get('response_dates') or [''])[0]).strip()
                if normalized == 'adverse_action_date' and contextual_dates.get('adverse_action_dates'):
                    return str((contextual_dates.get('adverse_action_dates') or [''])[0]).strip()
                if normalized == 'decision_date' and contextual_dates.get('decision_dates'):
                    return str((contextual_dates.get('decision_dates') or [''])[0]).strip()
                if normalized == 'protected_activity_date' and contextual_dates.get('protected_activity_dates'):
                    return str((contextual_dates.get('protected_activity_dates') or [''])[0]).strip()
                if normalized == 'document_date' and contextual_dates.get('document_dates'):
                    return str((contextual_dates.get('document_dates') or [''])[0]).strip()
                return str((extracted_dates or [''])[0]).strip()
            if normalized in {'staff_name', 'decision_actor', 'response_actor', 'hearing_request_actor', 'issuing_actor'}:
                if named_role_people:
                    name, role = named_role_people[0]
                    if normalized == 'staff_name':
                        return str(name or '').strip()
                    return f"{name} ({role})".strip()
                if named_title_people:
                    name, role = named_title_people[0]
                    if normalized == 'staff_name':
                        return str(name or '').strip()
                    return f"{name} ({role})".strip()
                return str((org_candidates or [''])[0]).strip()
            if normalized in {'staff_role', 'staff_title'}:
                if named_role_people:
                    return str(named_role_people[0][1] or '').strip()
                if named_title_people:
                    return str(named_title_people[0][1] or '').strip()
                return str((generic_roles or [''])[0]).strip()
            if normalized == 'document_name':
                if document_mentions:
                    return str(document_mentions[0]).strip()
                if extracted_file_refs:
                    return str(extracted_file_refs[0]).strip()
                if extracted_policy_refs:
                    return str(extracted_policy_refs[0]).strip()
                return ''
            if normalized == 'protected_activity' and has_causation_signal:
                return self._short_description(answer_text, 160)
            if normalized == 'adverse_action' and (has_adverse_action_signal or has_causation_signal):
                return self._short_description(answer_text, 160)
            if normalized == 'causation_link' and has_causation_signal:
                return self._short_description(answer_text, 160)
            if normalized == 'supporting_fact' and _has_structured_signal():
                return self._short_description(answer_text, 180)
            return ''

        def _apply_contract_gap_updates(claim_entity: Optional[Entity]) -> None:
            if not claim_entity or not _answer_is_substantive(answer_text):
                return

            # Force deterministic closure attempts for contract-identified missing fields.
            for field_name in contract_required_fields:
                if field_name in deterministic_fields_updated:
                    continue
                if field_name in contract_missing_required_fields or not _required_field_has_value(claim_entity, field_name):
                    candidate_value = _candidate_value_for_required_field(field_name)
                    if candidate_value:
                        _store_required_field_value(claim_entity, field_name, candidate_value)

            for plan in contract_missing_field_plan:
                field_name = str(plan.get('field_name') or '').strip().lower()
                if not field_name:
                    continue
                # Only execute deterministic field-level updates when this turn captured the field.
                if field_name not in deterministic_fields_updated:
                    continue
                deterministic_plan_fields_captured.add(field_name)
                for req_key in plan.get('requirement_updates') or []:
                    normalized_req = str(req_key or '').strip().lower()
                    if not normalized_req:
                        continue
                    deterministic_requirement_tokens_updated.add(normalized_req)
                    _append_claim_signal(claim_entity, 'satisfied_requirements', normalized_req)
                for rel_key in plan.get('relationship_updates') or []:
                    normalized_rel = str(rel_key or '').strip().lower()
                    if normalized_rel:
                        deterministic_relationship_tokens_updated.add(normalized_rel)
                for entity_key in plan.get('entity_updates') or []:
                    normalized_entity = str(entity_key or '').strip().lower()
                    if normalized_entity:
                        deterministic_entity_tokens_updated.add(normalized_entity)

            captured_contract_fields = deterministic_fields_updated.intersection(contract_missing_required_fields)
            if captured_contract_fields or (not contract_missing_required_fields and deterministic_fields_updated):
                deterministic_requirement_tokens_updated.update(contract_requirement_updates)
                deterministic_relationship_tokens_updated.update(contract_relationship_updates)
                deterministic_entity_tokens_updated.update(contract_entity_updates)

        def _deterministic_gap_field_updates(claim_entity: Optional[Entity]) -> None:
            if not claim_entity or not _answer_is_substantive(answer_text):
                return

            required_fields = _required_fields_for_gap(gap_type)
            if not required_fields:
                # Fall back to extraction targets to keep updates deterministic for registry-driven gaps.
                target_map = {
                    'exact_dates': 'event_date',
                    'event_order': 'supporting_fact',
                    'actor_name': 'staff_name',
                    'actor_role': 'staff_role',
                    'decision_maker': 'decision_actor',
                    'document_type': 'document_name',
                    'document_date': 'document_date',
                    'document_owner': 'issuing_actor',
                    'protected_activity': 'protected_activity',
                    'adverse_action': 'adverse_action',
                    'causation_link': 'causation_link',
                    'response_timing': 'response_date',
                }
                required_fields = [
                    target_map[target]
                    for target in extraction_targets
                    if target in target_map
                ]
                deduped_fields: List[str] = []
                for field_name in required_fields:
                    if field_name not in deduped_fields:
                        deduped_fields.append(field_name)
                required_fields = deduped_fields

            if extracted_dates:
                primary_date = extracted_dates[0]
                hearing_date = (contextual_dates.get('hearing_request_dates') or [primary_date])[0]
                response_date = (contextual_dates.get('response_dates') or [primary_date])[0]
                adverse_date = (contextual_dates.get('adverse_action_dates') or [primary_date])[0]
                decision_date = (contextual_dates.get('decision_dates') or [adverse_date])[0]
                protected_activity_date = (
                    (contextual_dates.get('protected_activity_dates') or [primary_date])[0]
                )
                if 'event_date' in required_fields:
                    _store_required_field_value(claim_entity, 'event_date', primary_date)
                if 'hearing_request_date' in required_fields:
                    _store_required_field_value(claim_entity, 'hearing_request_date', hearing_date)
                if 'response_date' in required_fields:
                    _store_required_field_value(claim_entity, 'response_date', response_date)
                if 'adverse_action_date' in required_fields:
                    _store_required_field_value(claim_entity, 'adverse_action_date', adverse_date)
                if 'decision_date' in required_fields:
                    _store_required_field_value(claim_entity, 'decision_date', decision_date)
                if 'protected_activity_date' in required_fields:
                    _store_required_field_value(claim_entity, 'protected_activity_date', protected_activity_date)

            staff_pairs: List[Tuple[str, str]] = []
            staff_pairs.extend(named_role_people)
            staff_pairs.extend(named_title_people)
            if staff_pairs:
                if 'staff_name' in required_fields:
                    _store_required_field_value(claim_entity, 'staff_name', staff_pairs[0][0])
                if 'staff_role' in required_fields:
                    _store_required_field_value(claim_entity, 'staff_role', staff_pairs[0][1])
                if 'staff_title' in required_fields:
                    _store_required_field_value(claim_entity, 'staff_title', staff_pairs[0][1])
                if 'decision_actor' in required_fields:
                    _store_required_field_value(claim_entity, 'decision_actor', f"{staff_pairs[0][0]} ({staff_pairs[0][1]})")
                if 'issuing_actor' in required_fields:
                    _store_required_field_value(claim_entity, 'issuing_actor', f"{staff_pairs[0][0]} ({staff_pairs[0][1]})")
                for person_name, person_role in staff_pairs[:4]:
                    person_entity, created = self._add_entity_if_missing(
                        knowledge_graph,
                        'person',
                        person_name,
                        {
                            'role': person_role,
                            'title': person_role,
                            'source': 'deterministic_gap_update',
                            'gap_type': gap_type,
                        },
                        0.78,
                    )
                    if created:
                        updates['entities_updated'] += 1
                    _link_claim_to_entity(claim_entity, person_entity, 'involves', 0.67)
                    if any(token in person_role for token in ('manager', 'director', 'officer', 'landlord', 'owner', 'supervisor', 'agent')):
                        _link_claim_to_entity(claim_entity, person_entity, 'has_decision_maker', 0.66)
            elif org_candidates and ('decision_actor' in required_fields or 'issuing_actor' in required_fields):
                if 'decision_actor' in required_fields:
                    _store_required_field_value(claim_entity, 'decision_actor', org_candidates[0])
                if 'issuing_actor' in required_fields:
                    _store_required_field_value(claim_entity, 'issuing_actor', org_candidates[0])
                org_entity, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'organization',
                    org_candidates[0],
                    {
                        'role': 'respondent',
                        'source': 'deterministic_gap_update',
                        'gap_type': gap_type,
                    },
                    0.72,
                )
                if created:
                    updates['entities_updated'] += 1
                _link_claim_to_entity(claim_entity, org_entity, 'involves', 0.65)

            if ('document_name' in required_fields or 'supporting_fact' in required_fields) and (document_mentions or extracted_file_refs or extracted_policy_refs):
                document_value = (
                    document_mentions[0]
                    if document_mentions
                    else extracted_file_refs[0]
                    if extracted_file_refs
                    else extracted_policy_refs[0]
                )
                if 'document_name' in required_fields:
                    _store_required_field_value(claim_entity, 'document_name', document_value)
                if 'supporting_fact' in required_fields:
                    _store_required_field_value(claim_entity, 'supporting_fact', self._short_description(answer_text, 160))

            if 'document_date' in required_fields and extracted_dates:
                document_date = (
                    (contextual_dates.get('document_dates') or extracted_dates)[0]
                )
                _store_required_field_value(claim_entity, 'document_date', document_date)

            if 'response_actor' in required_fields and (staff_pairs or org_candidates):
                if staff_pairs:
                    _store_required_field_value(claim_entity, 'response_actor', f"{staff_pairs[0][0]} ({staff_pairs[0][1]})")
                elif org_candidates:
                    _store_required_field_value(claim_entity, 'response_actor', org_candidates[0])

            if 'hearing_request_actor' in required_fields and (staff_pairs or org_candidates):
                if staff_pairs:
                    _store_required_field_value(claim_entity, 'hearing_request_actor', f"{staff_pairs[0][0]} ({staff_pairs[0][1]})")
                elif org_candidates:
                    _store_required_field_value(claim_entity, 'hearing_request_actor', org_candidates[0])

            if 'protected_activity' in required_fields and has_causation_signal:
                _store_required_field_value(claim_entity, 'protected_activity', self._short_description(answer_text, 160))
            if 'adverse_action' in required_fields and (has_adverse_action_signal or has_causation_signal):
                _store_required_field_value(claim_entity, 'adverse_action', self._short_description(answer_text, 160))
            if 'causation_link' in required_fields and has_causation_signal:
                _store_required_field_value(claim_entity, 'causation_link', self._short_description(answer_text, 160))

            if 'supporting_fact' in required_fields and _has_structured_signal():
                _store_required_field_value(claim_entity, 'supporting_fact', self._short_description(answer_text, 180))

            # Promote concrete hearing/response/causation sequencing fields even when not explicitly required.
            if gap_type in {'missing_hearing_request_date', 'missing_hearing_timing'} and extracted_dates:
                hearing_candidate = (
                    (contextual_dates.get('hearing_request_dates') or extracted_dates)[0]
                )
                _store_required_field_value(claim_entity, 'hearing_request_date', hearing_candidate)
            if gap_type in {'missing_response_dates', 'missing_decision_timeline'} and (extracted_dates or response_timing_phrases):
                if extracted_dates:
                    response_candidate = (
                        (contextual_dates.get('response_dates') or extracted_dates)[0]
                    )
                    _store_required_field_value(claim_entity, 'response_date', response_candidate)
                elif response_timing_phrases:
                    _store_required_field_value(claim_entity, 'response_date', response_timing_phrases[0])
            if gap_type in {'retaliation_missing_causation', 'retaliation_missing_causation_link', 'retaliation_missing_sequence', 'retaliation_missing_sequencing_dates'}:
                if has_causation_signal:
                    _store_required_field_value(claim_entity, 'causation_link', self._short_description(answer_text, 160))
                if extracted_dates:
                    protected_candidate = (
                        (contextual_dates.get('protected_activity_dates') or extracted_dates)[0]
                    )
                    adverse_candidates = contextual_dates.get('adverse_action_dates') or extracted_dates
                    _store_required_field_value(claim_entity, 'protected_activity_date', protected_candidate)
                    if len(adverse_candidates) > 1 and adverse_candidates[0] == protected_candidate:
                        _store_required_field_value(claim_entity, 'adverse_action_date', adverse_candidates[1])
                    else:
                        _store_required_field_value(claim_entity, 'adverse_action_date', adverse_candidates[0])

        def _deterministic_requirement_fact(claim_entity: Optional[Entity]) -> None:
            nonlocal updates
            if not claim_entity or not _answer_is_substantive(answer_text):
                return
            requirement_id = str(context.get('requirement_id') or context.get('target_element_id') or '').strip()
            requirement_name = str(context.get('requirement_name') or requirement_id or 'claim element').strip()
            claim_type = normalize_claim_type(str(context.get('claim_type') or claim_entity.attributes.get('claim_type') or '').strip())
            snippet = self._short_description(answer_text, 140)
            fact_name = f"Requirement {requirement_name}: {self._short_description(answer_text, 72)}"
            fact_entity, created = self._add_entity_if_missing(
                knowledge_graph,
                'fact',
                fact_name,
                {
                    'fact_type': 'requirement_support',
                    'description': snippet,
                    'requirement_id': requirement_id,
                    'requirement_name': requirement_name,
                    'claim_type': claim_type,
                    'source_question_type': question_type,
                    'gap_id': str(context.get('gap_id') or ''),
                },
                0.68,
            )
            if created:
                updates['entities_updated'] += 1
            _link_claim_to_entity(claim_entity, fact_entity, 'has_requirement_fact', 0.64)

            if requirement_id:
                changed = _append_attr_list(claim_entity, 'satisfied_requirements', requirement_id.lower())
                if changed:
                    updates['entities_updated'] += 1
            if str(context.get('requirement_name') or '').strip():
                changed = _append_attr_list(claim_entity, 'satisfied_requirement_labels', requirement_name)
                if changed:
                    updates['entities_updated'] += 1

        def _upsert_structured_evidence(claim_entity: Optional[Entity],
                                        claim_id: Optional[str],
                                        evidence_type: str,
                                        confidence: float,
                                        extra_attrs: Optional[Dict[str, Any]] = None) -> None:
            nonlocal updates
            if not claim_id or not _answer_is_substantive(answer_text):
                return
            snippet = self._short_description(answer_text, 140)
            prefix = "Policy document" if evidence_type == 'policy_document' else "File evidence"
            evidence_name = f"{prefix}: {self._short_description(answer_text, 80)}"
            attrs = {
                'description': snippet,
                'evidence_type': evidence_type,
                'gap_type': gap_type,
                'gap_id': str(context.get('gap_id') or ''),
            }
            if extra_attrs:
                attrs.update(extra_attrs)
            evidence_entity, created = self._add_entity_if_missing(
                knowledge_graph,
                'evidence',
                evidence_name,
                attrs,
                confidence,
            )
            if created:
                updates['entities_updated'] += 1
            if evidence_entity:
                _, rel_created = self._add_relationship_if_missing(
                    knowledge_graph,
                    claim_id,
                    evidence_entity.id,
                    'supported_by',
                    max(0.6, confidence - 0.01),
                )
                if rel_created:
                    updates['relationships_added'] += 1
            _append_claim_signal(claim_entity, 'satisfied_evidence_modalities', evidence_type)
            if evidence_type == 'policy_document':
                for ref in extracted_policy_refs[:3]:
                    _append_claim_signal(claim_entity, 'policy_document_refs', ref)
            if evidence_type == 'file_evidence':
                for ref in extracted_file_refs[:3]:
                    _append_claim_signal(claim_entity, 'file_evidence_refs', ref)

        def _mark_dependency_requirement_satisfied() -> None:
            nonlocal updates
            if not dependency_graph or not _answer_is_substantive(answer_text):
                return
            required_fields = _required_fields_for_gap(gap_type)
            captured_missing_required = deterministic_fields_updated.intersection(contract_missing_required_fields)
            if (
                required_fields
                and not deterministic_fields_updated.intersection(set(required_fields))
                and not deterministic_requirement_tokens_updated
            ):
                return
            if (
                workflow_phase == 'graph_analysis'
                and contract_missing_required_fields
                and not captured_missing_required
                and not deterministic_plan_fields_captured
            ):
                return
            candidate_ids = {
                str(context.get('requirement_id') or '').strip(),
                str(context.get('node_id') or '').strip(),
                str(context.get('target_element_id') or '').strip(),
            }
            requirement_name = str(context.get('requirement_name') or context.get('node_name') or '').strip().lower()
            requirement_key = str(context.get('requirement_key') or context.get('target_element_id') or '').strip().lower()
            requirement_aliases = {
                token
                for token in (
                    [requirement_key]
                    + list(deterministic_requirement_tokens_updated)
                    + list(contract_requirement_updates)
                )
                if str(token or '').strip()
            }

            matched_nodes = []
            for node_id in [item for item in candidate_ids if item]:
                node = dependency_graph.get_node(node_id)
                if node:
                    matched_nodes.append(node)
            if not matched_nodes:
                for node in dependency_graph.nodes.values():
                    node_name = str(node.name or '').strip().lower()
                    attrs = node.attributes if isinstance(node.attributes, dict) else {}
                    node_requirement_key = str(attrs.get('requirement_key') or '').strip().lower()
                    if requirement_name and node_name == requirement_name:
                        matched_nodes.append(node)
                    elif requirement_aliases and node_requirement_key and node_requirement_key in requirement_aliases:
                        matched_nodes.append(node)

            seen_node_ids: Set[str] = set()
            for node in matched_nodes:
                if not node or node.id in seen_node_ids:
                    continue
                seen_node_ids.add(node.id)
                if not node.satisfied:
                    node.satisfied = True
                    updates['requirements_satisfied'] += 1
                node.confidence = max(float(node.confidence or 0.0), 0.78)
                attrs = node.attributes if isinstance(node.attributes, dict) else {}
                attrs['satisfied_via_denoiser'] = True
                attrs['satisfied_answer_text'] = self._short_description(answer_text, 180)
                if str(context.get('gap_id') or '').strip():
                    attrs['satisfied_gap_id'] = str(context.get('gap_id'))
                if requirement_key:
                    attrs['requirement_key'] = requirement_key
                node.attributes = attrs

        def _mark_dependency_gap_satisfied() -> None:
            nonlocal updates
            if not dependency_graph or not _answer_is_substantive(answer_text):
                return
            required_fields = _required_fields_for_gap(gap_type)
            relevant_required = set(contract_missing_required_fields or required_fields)
            captured_required = deterministic_fields_updated.intersection(relevant_required)
            if (
                workflow_phase == 'graph_analysis'
                and relevant_required
                and not captured_required
                and not deterministic_requirement_tokens_updated
                and not deterministic_plan_fields_captured
            ):
                return
            gap_id = str(context.get('gap_id') or '').strip().lower()
            deterministic_key = str(context.get('deterministic_update_key') or '').strip().lower()
            target_keys = {
                item
                for item in [
                    gap_id,
                    deterministic_key,
                    str(context.get('target_element_id') or '').strip().lower(),
                    str(context.get('requirement_key') or '').strip().lower(),
                ]
                if item
            }
            if not target_keys and not gap_type:
                return
            for node in dependency_graph.nodes.values():
                attrs = node.attributes if isinstance(node.attributes, dict) else {}
                node_keys = {
                    str(node.id or '').strip().lower(),
                    str(node.name or '').strip().lower(),
                    str(attrs.get('gap_id') or '').strip().lower(),
                    str(attrs.get('gap_key') or '').strip().lower(),
                    str(attrs.get('requirement_key') or '').strip().lower(),
                    str(attrs.get('target_element_id') or '').strip().lower(),
                }
                node_gap_type = str(attrs.get('gap_type') or '').strip().lower()
                matched = bool(target_keys.intersection({item for item in node_keys if item}))
                if not matched and gap_type and node_gap_type == gap_type:
                    matched = True
                if not matched:
                    continue
                if not node.satisfied:
                    node.satisfied = True
                    updates['requirements_satisfied'] += 1
                node.confidence = max(float(node.confidence or 0.0), 0.8)
                attrs['satisfied_via_denoiser'] = True
                attrs['satisfied_answer_text'] = self._short_description(answer_text, 180)
                if gap_id:
                    attrs['satisfied_gap_id'] = gap_id
                if gap_type:
                    attrs['gap_type'] = gap_type
                node.attributes = attrs

        def _add_structured_graph_analysis_updates(claim_entity: Optional[Entity]) -> None:
            nonlocal updates
            if not claim_entity or not _answer_is_substantive(answer_text):
                return
            claim_id = claim_entity.id
            structured_timeline_events = self._extract_structured_timeline_events(answer_text)

            for event in structured_timeline_events[:10]:
                fact_entity, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'fact',
                    f"{event['event_label']}: {self._short_description(event['description'], 72)}",
                    {
                        'fact_type': 'timeline',
                        'predicate_family': event['predicate_family'],
                        'event_label': event['event_label'],
                        'event_id': event['event_id'],
                        'sequence_index': event['sequence_index'],
                        'structured_timeline_group': event['structured_timeline_group'],
                        'description': event['description'],
                        'event_date_or_range': event['event_date_or_range'],
                        'fact_participants': {'actor_label': event['actor_text']},
                        'event_support_refs': [event['artifact_text']] if event['artifact_text'] else [],
                        'source_artifact_ids': [event['artifact_text']] if event['artifact_text'] else [],
                        'source_span_refs': [{'kind': 'structured_answer_line', 'text': event['source_line']}],
                        'source': 'structured_timeline_answer',
                    },
                    0.77,
                )
                if created:
                    updates['entities_updated'] += 1
                _link_claim_to_entity(claim_entity, fact_entity, 'has_timeline_detail', 0.68)
                if event['artifact_text']:
                    _append_claim_signal(claim_entity, 'documentary_artifact_refs', event['artifact_text'])
                if event['predicate_family'] == 'protected_activity':
                    _append_claim_signal(claim_entity, 'protected_activity', event['description'])
                    if event['event_date_or_range']:
                        _append_claim_signal(claim_entity, 'protected_activity_dates', event['event_date_or_range'])
                elif event['predicate_family'] == 'adverse_action':
                    _append_claim_signal(claim_entity, 'adverse_action', event['description'])
                    if event['event_date_or_range']:
                        _append_claim_signal(claim_entity, 'adverse_action_dates', event['event_date_or_range'])
                elif event['predicate_family'] == 'hearing_process':
                    _append_claim_signal(claim_entity, 'hearing_request_timing', event['description'])
                elif event['predicate_family'] == 'response_timeline':
                    _append_claim_signal(claim_entity, 'response_dates', event['description'])
                elif event['predicate_family'] == 'causation':
                    _append_claim_signal(claim_entity, 'causation_sequences', event['description'])

            if extracted_dates:
                for date_str in extracted_dates[:5]:
                    date_entity, created = self._add_entity_if_missing(
                        knowledge_graph,
                        'date',
                        date_str,
                        {
                            'date_context_gap_type': gap_type,
                            'source_question_type': question_type,
                        },
                        0.74,
                    )
                    if created:
                        updates['entities_updated'] += 1
                    if date_entity:
                        _, rel_created = self._add_relationship_if_missing(
                            knowledge_graph,
                            claim_id,
                            date_entity.id,
                            'occurred_on',
                            0.66,
                        )
                        if rel_created:
                            updates['relationships_added'] += 1
                _append_claim_signal(claim_entity, 'exact_dates', ", ".join(extracted_dates[:5]))

            if response_timing_phrases:
                timing_fact, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'fact',
                    f"Response timing: {self._short_description(answer_text, 72)}",
                    {
                        'fact_type': 'response_timing',
                        'timing_phrases': list(response_timing_phrases[:4]),
                        'gap_type': gap_type,
                        'target_element_id': target_element_id,
                        'description': self._short_description(answer_text, 160),
                    },
                    0.72,
                )
                if created:
                    updates['entities_updated'] += 1
                _link_claim_to_entity(claim_entity, timing_fact, 'has_timeline_detail', 0.64)
                for phrase in response_timing_phrases[:4]:
                    _append_claim_signal(claim_entity, 'response_timing_phrases', phrase)

            people_with_roles: List[Tuple[str, str]] = []
            seen_people_roles: Set[Tuple[str, str]] = set()
            for pair in named_title_people + named_role_people:
                key = (str(pair[0] or '').strip().lower(), str(pair[1] or '').strip().lower())
                if not key[0] or not key[1]:
                    continue
                if key not in seen_people_roles:
                    seen_people_roles.add(key)
                    people_with_roles.append((pair[0], pair[1]))

            for name, title in people_with_roles[:8]:
                person, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'person',
                    name,
                    {'role': title, 'title': title, 'source': 'denoiser_answer'},
                    0.74,
                )
                if created:
                    updates['entities_updated'] += 1
                elif person:
                    previous_title = str((person.attributes or {}).get('title') or '').strip().lower()
                    if not previous_title and title:
                        person.attributes['title'] = title
                        updates['entities_updated'] += 1
                _link_claim_to_entity(claim_entity, person, 'involves', 0.64)
                if person and any(token in title for token in ('manager', 'director', 'officer', 'landlord', 'owner', 'supervisor', 'agent')):
                    _link_claim_to_entity(claim_entity, person, 'has_decision_maker', 0.62)
                    _append_claim_signal(claim_entity, 'decision_makers', f"{name} ({title})")

            for key, claim_attr in (
                ('hearing_request_dates', 'hearing_request_dates'),
                ('response_dates', 'response_dates'),
                ('adverse_action_dates', 'adverse_action_dates'),
                ('protected_activity_dates', 'protected_activity_dates'),
                ('decision_dates', 'decision_dates'),
            ):
                for date_token in (contextual_dates.get(key) or [])[:4]:
                    _append_claim_signal(claim_entity, claim_attr, date_token)

            if has_causation_signal or has_sequence_signal:
                causation_fact, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'fact',
                    f"Causation sequence: {self._short_description(answer_text, 72)}",
                    {
                        'fact_type': 'causation_sequence',
                        'has_causation_signal': bool(has_causation_signal),
                        'has_sequence_signal': bool(has_sequence_signal),
                        'has_adverse_action_signal': bool(has_adverse_action_signal),
                        'captured_dates': list(extracted_dates[:4]),
                        'target_element_id': target_element_id,
                        'description': self._short_description(answer_text, 160),
                    },
                    0.7,
                )
                if created:
                    updates['entities_updated'] += 1
                _link_claim_to_entity(claim_entity, causation_fact, 'has_causation_detail', 0.63)
                if has_causation_signal:
                    _append_claim_signal(claim_entity, 'causation_sequences', self._short_description(answer_text, 180))

            should_force_policy = (
                'documentary_artifact_patch_anchor' in patchability_markers
                or 'document_type' in extraction_targets
                or gap_type in {'missing_claim_element', 'missing_proof_leads', 'missing_written_notice'}
                or expected_update_kind in {'proof_lead', 'documentary_support'}
                or 'policy_document' in expected_modalities
                or 'policy_document' in weak_modalities
            )
            should_force_file = (
                should_force_policy
                or 'document_owner' in extraction_targets
                or 'file_evidence' in expected_modalities
                or 'file_evidence' in weak_modalities
            )
            if policy_signal and should_force_policy:
                _upsert_structured_evidence(
                    claim_entity,
                    claim_id,
                    'policy_document',
                    0.72,
                    {
                        'policy_refs': list(extracted_policy_refs[:4]),
                        'document_mentions': list(document_mentions[:4]),
                        'question_objective': question_objective,
                        'expected_update_kind': expected_update_kind,
                    },
                )
            if file_signal and should_force_file:
                _upsert_structured_evidence(
                    claim_entity,
                    claim_id,
                    'file_evidence',
                    0.72,
                    {
                        'file_refs': list(extracted_file_refs[:4]),
                        'document_mentions': list(document_mentions[:4]),
                        'question_objective': question_objective,
                        'expected_update_kind': expected_update_kind,
                    },
                )

            if gap_type in {'missing_hearing_request_date', 'missing_hearing_timing'} and (extracted_dates or response_timing_phrases):
                _append_claim_signal(claim_entity, 'hearing_request_timing', self._short_description(answer_text, 180))
                _append_claim_signal(claim_entity, 'satisfied_requirements', 'hearing_request_timing')
                hearing_fact, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'fact',
                    f"Hearing request timing: {self._short_description(answer_text, 70)}",
                    {
                        'fact_type': 'hearing_request_timing',
                        'captured_dates': list(extracted_dates[:3]),
                        'response_timing': list(response_timing_phrases[:3]),
                        'description': self._short_description(answer_text, 180),
                    },
                    0.73,
                )
                if created:
                    updates['entities_updated'] += 1
                _link_claim_to_entity(claim_entity, hearing_fact, 'has_timeline_detail', 0.66)
            if gap_type in {'missing_response_dates', 'missing_decision_timeline'} and (extracted_dates or response_timing_phrases):
                _append_claim_signal(claim_entity, 'response_dates', ", ".join(extracted_dates[:5]) or "; ".join(response_timing_phrases[:4]))
                _append_claim_signal(claim_entity, 'satisfied_requirements', 'response_dates')
                response_fact, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'fact',
                    f"Response dates: {self._short_description(answer_text, 70)}",
                    {
                        'fact_type': 'response_dates',
                        'captured_dates': list(extracted_dates[:4]),
                        'response_timing': list(response_timing_phrases[:4]),
                        'description': self._short_description(answer_text, 180),
                    },
                    0.74,
                )
                if created:
                    updates['entities_updated'] += 1
                _link_claim_to_entity(claim_entity, response_fact, 'has_timeline_detail', 0.66)
            if gap_type in {'missing_staff_identity', 'missing_staff_title'} and staff_signal:
                _append_claim_signal(claim_entity, 'staff_names_titles', self._short_description(answer_text, 180))
                _append_claim_signal(claim_entity, 'satisfied_requirements', 'staff_identity')
                for name, role in (named_title_people or named_role_people)[:4]:
                    person, created = self._add_entity_if_missing(
                        knowledge_graph,
                        'person',
                        name,
                        {'role': role, 'title': role, 'source': 'denoiser_answer'},
                        0.76,
                    )
                    if created:
                        updates['entities_updated'] += 1
                    _link_claim_to_entity(claim_entity, person, 'has_decision_maker', 0.68)
            if gap_type in {'retaliation_missing_causation', 'retaliation_missing_causation_link', 'retaliation_missing_sequence', 'retaliation_missing_sequencing_dates'} and (has_causation_signal or has_sequence_signal):
                _append_claim_signal(claim_entity, 'causation_timeline', self._short_description(answer_text, 180))
                _append_claim_signal(claim_entity, 'satisfied_requirements', 'causation_sequence')
                sequence_fact, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'fact',
                    f"Causation sequencing: {self._short_description(answer_text, 70)}",
                    {
                        'fact_type': 'causation_sequence',
                        'captured_dates': list(extracted_dates[:4]),
                        'has_causation_signal': bool(has_causation_signal),
                        'has_sequence_signal': bool(has_sequence_signal),
                        'description': self._short_description(answer_text, 180),
                    },
                    0.74,
                )
                if created:
                    updates['entities_updated'] += 1
                _link_claim_to_entity(claim_entity, sequence_fact, 'has_causation_detail', 0.67)

        def _apply_contract_entity_relationship_updates(claim_entity: Optional[Entity]) -> None:
            nonlocal updates
            if not claim_entity or not _answer_is_substantive(answer_text):
                return
            claim_id = claim_entity.id

            if (
                'staff_actor' in deterministic_entity_tokens_updated
                or 'link_staff_to_action' in deterministic_relationship_tokens_updated
            ) and (named_title_people or named_role_people or org_candidates):
                people = list(named_title_people) + list(named_role_people)
                if not people and org_candidates:
                    org_entity, created = self._add_entity_if_missing(
                        knowledge_graph,
                        'organization',
                        org_candidates[0],
                        {'role': 'respondent', 'source': 'answer_contract'},
                        0.76,
                    )
                    if created:
                        updates['entities_updated'] += 1
                    _link_claim_to_entity(claim_entity, org_entity, 'involves', 0.67)
                for name, title in people[:4]:
                    person, created = self._add_entity_if_missing(
                        knowledge_graph,
                        'person',
                        name,
                        {'role': title, 'title': title, 'source': 'answer_contract'},
                        0.78,
                    )
                    if created:
                        updates['entities_updated'] += 1
                    _link_claim_to_entity(claim_entity, person, 'involves', 0.67)
                    _link_claim_to_entity(claim_entity, person, 'has_decision_maker', 0.66)

            if (
                'document_evidence' in deterministic_entity_tokens_updated
                or 'link_document_to_claim' in deterministic_relationship_tokens_updated
            ):
                if policy_signal or extracted_policy_refs:
                    _upsert_structured_evidence(
                        claim_entity,
                        claim_id,
                        'policy_document',
                        0.72,
                        {
                            'policy_refs': list(extracted_policy_refs[:4]),
                            'document_mentions': list(document_mentions[:4]),
                            'source': 'answer_contract',
                        },
                    )
                if file_signal or extracted_file_refs:
                    _upsert_structured_evidence(
                        claim_entity,
                        claim_id,
                        'file_evidence',
                        0.72,
                        {
                            'file_refs': list(extracted_file_refs[:4]),
                            'document_mentions': list(document_mentions[:4]),
                            'source': 'answer_contract',
                        },
                    )

            if (
                'timeline_fact' in deterministic_entity_tokens_updated
                or 'link_event_sequence' in deterministic_relationship_tokens_updated
                or 'validate_temporal_order' in deterministic_relationship_tokens_updated
                or 'link_response_to_hearing_or_action' in deterministic_relationship_tokens_updated
            ) and (extracted_dates or response_timing_phrases or has_sequence_signal):
                timeline_fact, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'fact',
                    f"Timeline contract detail: {self._short_description(answer_text, 72)}",
                    {
                        'fact_type': 'timeline_contract_detail',
                        'captured_dates': list(extracted_dates[:4]),
                        'response_timing': list(response_timing_phrases[:4]),
                        'has_sequence_signal': bool(has_sequence_signal),
                        'gap_type': gap_type,
                    },
                    0.73,
                )
                if created:
                    updates['entities_updated'] += 1
                _link_claim_to_entity(claim_entity, timeline_fact, 'has_timeline_detail', 0.66)

            if (
                'claim_fact' in deterministic_entity_tokens_updated
                or 'link_causation_chain' in deterministic_relationship_tokens_updated
            ) and _has_structured_signal():
                fact_entity, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'fact',
                    f"Structured gap fact: {self._short_description(answer_text, 72)}",
                    {
                        'fact_type': 'structured_gap_fact',
                        'gap_type': gap_type,
                        'description': self._short_description(answer_text, 180),
                        'source': 'answer_contract',
                    },
                    0.72,
                )
                if created:
                    updates['entities_updated'] += 1
                _link_claim_to_entity(claim_entity, fact_entity, 'has_requirement_fact', 0.65)

        def _actor_critic_gap_confidence() -> float:
            if not _answer_is_substantive(answer_text):
                return 0.0
            claim_type_hint = normalize_claim_type(
                str(context.get('claim_type') or context.get('claim_name') or '').strip()
            )
            weak_claim_focus = claim_type_hint in {'housing_discrimination', 'hacc_research_engine'}
            weak_modality_focus = bool({'policy_document', 'file_evidence'}.intersection(weak_modalities))
            target_checks = {
                'exact_dates': bool(extracted_dates),
                'event_order': bool(has_sequence_signal),
                'response_timing': bool(response_timing_phrases),
                'decision_maker': bool(staff_signal),
                'actor_name': bool(staff_signal),
                'actor_role': bool(staff_signal),
                'adverse_action': bool(has_adverse_action_signal),
                'causation_link': bool(has_causation_signal),
                'document_type': bool(document_mentions),
                'document_date': bool(extracted_dates),
                'document_owner': bool(named_title_people or named_role_people or org_candidates),
                'hearing_request_timing': bool(contextual_dates.get('hearing_request_dates')),
                'response_dates': bool(contextual_dates.get('response_dates') or response_timing_phrases),
                'staff_names_titles': bool(staff_signal),
            }
            requested_targets = set(extraction_targets)
            if not requested_targets and target_element_id:
                if 'timing' in target_element_id or 'date' in target_element_id:
                    requested_targets.update({'exact_dates', 'event_order'})
                if any(token in target_element_id for token in ('actor', 'staff', 'identity', 'title', 'party')):
                    requested_targets.update({'actor_name', 'actor_role'})
                if any(token in target_element_id for token in ('causation', 'retaliation', 'sequence')):
                    requested_targets.update({'causation_link', 'event_order'})
            if requested_targets:
                hits = sum(1 for target in requested_targets if target_checks.get(target, False))
                actor_score = hits / max(len(requested_targets), 1)
            elif contract_required_fields:
                contract_hits = sum(
                    1
                    for field_name in contract_required_fields
                    if field_name in deterministic_fields_updated
                )
                actor_score = contract_hits / max(len(contract_required_fields), 1)
            else:
                actor_score = 1.0 if _has_structured_signal() else 0.35
            contract_capture_ratio = (
                len(deterministic_fields_updated.intersection(contract_missing_required_fields))
                / max(len(contract_missing_required_fields), 1)
                if contract_missing_required_fields
                else 1.0
            )
            critic_components = [
                1.0 if _has_structured_signal() else 0.0,
                1.0 if (policy_signal or file_signal) else 0.0,
                1.0 if (has_sequence_signal or has_causation_signal) else 0.0,
                1.0 if (extracted_dates or response_timing_phrases) else 0.0,
                1.0 if deterministic_fields_updated else 0.0,
                1.0 if deterministic_requirement_tokens_updated else 0.0,
                1.0 if (contextual_dates.get('response_dates') or contextual_dates.get('hearing_request_dates')) else 0.0,
                contract_capture_ratio,
            ]
            critic_score = sum(critic_components) / float(len(critic_components))
            weighted = (
                float(self.actor_weight or 1.0) * float(actor_score)
                + float(self.critic_weight or 1.0) * float(critic_score)
            ) / max(float(self.actor_weight or 1.0) + float(self.critic_weight or 1.0), 1e-6)
            if weak_claim_focus and bool(deterministic_fields_updated):
                weighted = min(1.0, weighted + 0.07)
            if weak_modality_focus and bool(policy_signal or file_signal):
                weighted = min(1.0, weighted + 0.05)
            return max(0.0, min(1.0, weighted))

        def _context_gap_is_closed() -> bool:
            if not _answer_is_substantive(answer_text):
                return False
            closure_confidence = _actor_critic_gap_confidence()
            if bool(self.actor_critic_enabled) and workflow_phase == 'graph_analysis' and closure_confidence < 0.5:
                return False

            claim_entity = _find_claim_entity_from_context()
            claim_attrs = claim_entity.attributes if (claim_entity and isinstance(claim_entity.attributes, dict)) else {}
            field_values = claim_attrs.get('required_field_values')
            field_values = field_values if isinstance(field_values, dict) else {}

            def _field_has_value(field_name: str) -> bool:
                value = field_values.get(field_name)
                if isinstance(value, list):
                    return any(str(item).strip() for item in value)
                return bool(str(value or '').strip())

            required_fields = _required_fields_for_gap(gap_type)
            if required_fields:
                matched_fields = 0
                for field_name in required_fields:
                    if field_name in deterministic_fields_updated or _field_has_value(field_name):
                        matched_fields += 1
                coverage = matched_fields / max(len(required_fields), 1)
                newly_captured_required = bool(deterministic_fields_updated.intersection(set(required_fields)))
                strict_gaps = {
                    'missing_staff_identity',
                    'missing_staff_title',
                    'missing_written_notice',
                    'missing_response_dates',
                    'missing_hearing_request_date',
                    'missing_decision_timeline',
                    'retaliation_missing_causation_link',
                    'retaliation_missing_sequencing_dates',
                }
                if gap_type in strict_gaps:
                    return coverage >= 1.0 and newly_captured_required
                if workflow_phase == 'graph_analysis' and contract_missing_required_fields:
                    captured_missing = deterministic_fields_updated.intersection(contract_missing_required_fields)
                    captured_ratio = len(captured_missing) / max(len(contract_missing_required_fields), 1)
                    if contract_single_field_closable:
                        return bool(captured_missing)
                    if contract_single_turn_closable:
                        return bool(captured_missing) and coverage >= 1.0 and captured_ratio >= 1.0
                    if contract_deterministically_closable:
                        return bool(captured_missing) and captured_ratio >= 0.5 and coverage >= 0.67
                # Require a concrete field capture in this turn before considering the gap closed.
                return newly_captured_required and coverage >= 0.5

            if not gap_type:
                return bool(_has_structured_signal() or question_type in {'requirement', 'evidence', 'timeline', 'responsible_party', 'relationship'})
            missing_claim_element_closed = bool(_has_structured_signal() or target_element_id)
            if target_element_id:
                if any(token in target_element_id for token in ('date', 'timeline', 'timing')):
                    missing_claim_element_closed = missing_claim_element_closed and bool(extracted_dates or response_timing_phrases)
                if any(token in target_element_id for token in ('staff', 'actor', 'party', 'title', 'identity')):
                    missing_claim_element_closed = missing_claim_element_closed and bool(staff_signal)
                if any(token in target_element_id for token in ('causation', 'retaliation', 'sequence')):
                    missing_claim_element_closed = missing_claim_element_closed and bool(has_causation_signal or has_sequence_signal)
            checks = {
                'missing_exact_action_dates': bool(extracted_dates),
                'missing_hearing_request_date': bool(extracted_dates),
                'missing_response_dates': bool(extracted_dates or response_timing_phrases),
                'missing_hearing_timing': bool(extracted_dates or response_timing_phrases),
                'missing_decision_timeline': bool(extracted_dates) and bool(has_sequence_signal or response_timing_phrases or has_adverse_action_signal),
                'missing_staff_identity': bool(named_role_people or named_title_people or org_candidates),
                'missing_staff_title': bool(named_role_people or named_title_people or generic_roles),
                'missing_written_notice': bool(file_signal or has_document_precision_signal),
                'retaliation_missing_causation': bool(has_causation_signal) and bool(has_adverse_action_signal or has_sequence_signal or extracted_dates),
                'retaliation_missing_causation_link': bool(has_causation_signal) and bool(has_adverse_action_signal or has_sequence_signal or extracted_dates),
                'retaliation_missing_sequence': bool(has_sequence_signal) and bool(extracted_dates or response_timing_phrases),
                'retaliation_missing_sequencing_dates': bool(has_sequence_signal) and bool(extracted_dates or response_timing_phrases),
                'missing_claim_element': missing_claim_element_closed,
                'missing_proof_leads': bool(policy_signal or file_signal or extracted_file_refs or extracted_policy_refs),
            }
            return bool(checks.get(gap_type, True))

        def _record_gap_resolution(claim_entity: Optional[Entity]) -> None:
            nonlocal updates
            if not claim_entity or not _answer_is_substantive(answer_text):
                return
            if not gap_type:
                return
            fact_name = f"Gap resolved ({gap_type}): {self._short_description(answer_text, 68)}"
            attrs: Dict[str, Any] = {
                'fact_type': 'gap_resolution',
                'gap_type': gap_type,
                'gap_id': str(context.get('gap_id') or ''),
                'description': self._short_description(answer_text, 140),
                'source_question_type': question_type,
            }
            if extracted_dates:
                attrs['captured_dates'] = list(extracted_dates[:4])
            if response_timing_phrases:
                attrs['captured_response_timing'] = list(response_timing_phrases[:3])
            if extracted_policy_refs:
                attrs['captured_policy_refs'] = list(extracted_policy_refs[:3])
            if extracted_file_refs:
                attrs['captured_file_refs'] = list(extracted_file_refs[:3])
            fact_entity, created = self._add_entity_if_missing(
                knowledge_graph,
                'fact',
                fact_name,
                attrs,
                0.68,
            )
            if created:
                updates['entities_updated'] += 1
            _link_claim_to_entity(claim_entity, fact_entity, 'has_gap_resolution', 0.64)

        def _apply_timeline_enrichment() -> None:
            nonlocal updates
            if question_type not in timeline_enrichment_types or not answer_text:
                return
            claim_entity = _find_claim_entity_from_context()
            claim_id = claim_entity.id if claim_entity else _single_claim_id()
            structured_timeline_events = self._extract_structured_timeline_events(answer_text)
            if claim_entity and structured_timeline_events:
                for event in structured_timeline_events[:10]:
                    fact_entity, created = self._add_entity_if_missing(
                        knowledge_graph,
                        'fact',
                        f"{event['event_label']}: {self._short_description(event['description'], 72)}",
                        {
                            'fact_type': 'timeline',
                            'predicate_family': event['predicate_family'],
                            'event_label': event['event_label'],
                            'event_id': event['event_id'],
                            'sequence_index': event['sequence_index'],
                            'structured_timeline_group': event['structured_timeline_group'],
                            'description': event['description'],
                            'event_date_or_range': event['event_date_or_range'],
                            'fact_participants': {'actor_label': event['actor_text']},
                            'event_support_refs': [event['artifact_text']] if event['artifact_text'] else [],
                            'source_artifact_ids': [event['artifact_text']] if event['artifact_text'] else [],
                            'source_span_refs': [{'kind': 'structured_answer_line', 'text': event['source_line']}],
                            'source': 'structured_timeline_answer',
                        },
                        0.77,
                    )
                    if created:
                        updates['entities_updated'] += 1
                    if claim_id and fact_entity:
                        _, rel_created = self._add_relationship_if_missing(
                            knowledge_graph,
                            claim_id,
                            fact_entity.id,
                            'has_timeline_detail',
                            0.68,
                        )
                        if rel_created:
                            updates['relationships_added'] += 1
            dates = self._extract_date_strings(answer_text)
            if dates:
                for date_str in dates:
                    date_entity, created = self._add_entity_if_missing(
                        knowledge_graph,
                        'date',
                        date_str,
                        {},
                        0.7
                    )
                    if created:
                        updates['entities_updated'] += 1
                    if claim_id and date_entity:
                        _, rel_created = self._add_relationship_if_missing(
                            knowledge_graph,
                            claim_id,
                            date_entity.id,
                            'occurred_on',
                            0.6
                        )
                        if rel_created:
                            updates['relationships_added'] += 1

            response_timing_phrases = self._extract_response_timing_phrases(answer_text)
            has_sequence = self._contains_sequence_signal(answer_text)
            should_add_timeline_fact = (
                question_type in fallback_timeline_fact_types
                and (not dates or has_sequence or bool(response_timing_phrases))
            )
            if should_add_timeline_fact:
                snippet = self._short_description(answer_text, 120)
                fact_name = f"Timeline detail: {self._short_description(answer_text, 60)}"
                fact_attrs: Dict[str, Any] = {'fact_type': 'timeline', 'description': snippet}
                if response_timing_phrases:
                    fact_attrs['response_timing'] = list(response_timing_phrases[:3])
                if has_sequence:
                    fact_attrs['event_order'] = 'captured'
                fact_entity, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'fact',
                    fact_name,
                    fact_attrs,
                    0.6
                )
                if created:
                    updates['entities_updated'] += 1
                if claim_id and fact_entity:
                    _, rel_created = self._add_relationship_if_missing(
                        knowledge_graph,
                        claim_id,
                        fact_entity.id,
                        'has_timeline_detail',
                        0.6
                    )
                    if rel_created:
                        updates['relationships_added'] += 1

            if question_type in {'evidence', 'timeline', 'responsible_party', 'requirement'}:
                document_mentions = self._extract_document_mentions(answer_text)
                for document_label in document_mentions[:3]:
                    artifact_name = f"{document_label}: {self._short_description(answer_text, 64)}"
                    artifact_entity, artifact_created = self._add_entity_if_missing(
                        knowledge_graph,
                        'fact',
                        artifact_name,
                        {
                            'fact_type': 'documentary_artifact',
                            'document_type': document_label,
                            'description': self._short_description(answer_text, 120),
                        },
                        0.58
                    )
                    if artifact_created:
                        updates['entities_updated'] += 1
                    if claim_id and artifact_entity:
                        _, rel_created = self._add_relationship_if_missing(
                            knowledge_graph,
                            claim_id,
                            artifact_entity.id,
                            'has_documentary_artifact',
                            0.58
                        )
                        if rel_created:
                            updates['relationships_added'] += 1

        if question_type == 'clarification':
            entity_id = context.get('entity_id')
            entity = knowledge_graph.get_entity(entity_id)
            if entity:
                entity.confidence = min(1.0, entity.confidence + 0.2)
                entity.attributes['clarification'] = answer
                updates['entities_updated'] += 1

        elif question_type == 'relationship':
            entity_id = context.get('entity_id')
            if entity_id and _answer_is_substantive(answer_text):
                entity = knowledge_graph.get_entity(entity_id)
                if entity:
                    entity.attributes['relationship_described'] = True
                    entity.attributes['relationship_description'] = self._short_description(answer_text, 180)
                    updates['entities_updated'] += 1
                    _link_claim_to_entity(_find_claim_entity_from_context(), entity, 'involves', 0.63)

        elif question_type == 'responsible_party':
            pass

        elif question_type == 'evidence':
            claim_entity = _find_claim_entity_from_context()
            if claim_entity:
                claim_entity.attributes['evidence_descriptions'] = self._append_unique_text_item(
                    claim_entity.attributes.get('evidence_descriptions'),
                    answer,
                )
                updates['entities_updated'] += 1
            claim_id = claim_entity.id if claim_entity else _single_claim_id()
            if claim_id and _answer_is_substantive(answer_text):
                snippet = self._short_description(answer_text, 120)
                evidence_name = f"Evidence: {self._short_description(answer_text, 80)}"
                evidence_entity, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'evidence',
                    evidence_name,
                    {'description': snippet},
                    0.6
                )
                if created:
                    updates['entities_updated'] += 1
                if evidence_entity:
                    _, rel_created = self._add_relationship_if_missing(
                        knowledge_graph,
                        claim_id,
                        evidence_entity.id,
                        'supported_by',
                        0.6
                    )
                    if rel_created:
                        updates['relationships_added'] += 1

            modality_targets = expected_modalities.union(weak_modalities)
            should_capture_policy = bool(policy_signal) and (
                'policy_document' in modality_targets
                or gap_type in {'missing_claim_element', 'missing_proof_leads', 'missing_written_notice'}
            )
            should_capture_file = bool(file_signal) and (
                'file_evidence' in modality_targets
                or gap_type in {'missing_claim_element', 'missing_proof_leads', 'missing_written_notice'}
            )
            if claim_id and _answer_is_substantive(answer_text):
                if should_capture_policy:
                    _upsert_structured_evidence(
                        claim_entity,
                        claim_id,
                        'policy_document',
                        0.7,
                        {
                            'policy_refs': list(extracted_policy_refs[:4]),
                            'document_mentions': list(document_mentions[:3]),
                            'document_date_candidates': list(extracted_dates[:3]),
                        },
                    )
                if should_capture_file:
                    _upsert_structured_evidence(
                        claim_entity,
                        claim_id,
                        'file_evidence',
                        0.7,
                        {
                            'file_refs': list(extracted_file_refs[:4]),
                            'document_mentions': list(document_mentions[:3]),
                            'document_date_candidates': list(extracted_dates[:3]),
                        },
                    )

        elif question_type == 'timeline':
            pass

        elif question_type in {'impact', 'remedy'}:
            if answer_text:
                claim_entity = _find_claim_entity_from_context()
                claim_id = claim_entity.id if claim_entity else _single_claim_id()
                snippet = self._short_description(answer_text, 120)
                if question_type == 'remedy':
                    fact_type = 'remedy'
                    fact_name = f"Requested remedy: {self._short_description(answer_text, 60)}"
                    rel_type = 'seeks_remedy'
                else:
                    fact_type = 'impact'
                    fact_name = f"Impact: {self._short_description(answer_text, 60)}"
                    rel_type = 'has_impact'
                fact_entity, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'fact',
                    fact_name,
                    {'fact_type': fact_type, 'description': snippet},
                    0.6
                )
                if created:
                    updates['entities_updated'] += 1
                if claim_id and fact_entity:
                    _, rel_created = self._add_relationship_if_missing(
                        knowledge_graph,
                        claim_id,
                        fact_entity.id,
                        rel_type,
                        0.6
                    )
                    if rel_created:
                        updates['relationships_added'] += 1
                if question_type == 'impact' and self._contains_remedy_cue(answer_text):
                    remedy_name = f"Requested remedy: {self._short_description(answer_text, 60)}"
                    remedy_entity, remedy_created = self._add_entity_if_missing(
                        knowledge_graph,
                        'fact',
                        remedy_name,
                        {'fact_type': 'remedy', 'description': snippet},
                        0.55
                    )
                    if remedy_created:
                        updates['entities_updated'] += 1
                    if claim_id and remedy_entity:
                        _, rel_created = self._add_relationship_if_missing(
                            knowledge_graph,
                            claim_id,
                            remedy_entity.id,
                            'seeks_remedy',
                            0.55
                        )
                        if rel_created:
                            updates['relationships_added'] += 1

        elif question_type == 'requirement':
            claim_entity = _find_claim_entity_from_context()
            _deterministic_requirement_fact(claim_entity)
            _mark_dependency_requirement_satisfied()
            _append_claim_signal(claim_entity, 'answered_requirement_questions', str(context.get('requirement_id') or context.get('target_element_id') or '').strip().lower())

        if question_type in responsible_party_enrichment_types and answer_text:
            updates = self._update_responsible_parties_from_answer(answer_text, knowledge_graph, updates)

        if question_type in timeline_enrichment_types and answer_text:
            _apply_timeline_enrichment()

        claim_entity_for_gap = _find_claim_entity_from_context()
        _deterministic_gap_field_updates(claim_entity_for_gap)
        _apply_contract_gap_updates(claim_entity_for_gap)
        _add_structured_graph_analysis_updates(claim_entity_for_gap)
        _apply_contract_entity_relationship_updates(claim_entity_for_gap)
        _mark_dependency_requirement_satisfied()

        if _context_gap_is_closed():
            _record_gap_resolution(claim_entity_for_gap)
            _mark_resolved_gap(claim_entity_for_gap)
            _mark_dependency_gap_satisfied()

        logger.info(f"Processed answer: {updates}")
        answered_record = self.record_question_disposition(
            question if isinstance(question, dict) else {},
            answer,
            disposition="answered",
            intake_case_file=(source_context or {}).get("intake_case_file") if isinstance(source_context, dict) else None,
            creates_fact=bool(updates.get("entities_updated") or updates.get("relationships_added")),
            satisfies_requirement=bool(updates.get("requirements_satisfied")),
            contradictory_conclusion=False,
        )
        updates["disposition"] = "answered"
        updates["creates_fact"] = answered_record["creates_fact"]
        updates["satisfies_requirement"] = bool(updates.get("requirements_satisfied"))
        updates["contradictory_conclusion"] = False
        updates["question_disposition"] = answered_record
        self.questions_asked[-1]["disposition"] = "answered"

        try:
            gain = self._compute_gain(updates)
            self._recent_gains.append(gain)
            if len(self._recent_gains) > 50:
                self._recent_gains = self._recent_gains[-50:]
            qtype = question.get('type') if isinstance(question, dict) else 'unknown'
            self._update_momentum(str(qtype or 'unknown'), gain)
        except Exception:
            pass

        if answer_event_id and knowledge_graph is not None:
            knowledge_graph.finish_answer_event(
                answer_event_id,
                event_payload,
                denoiser_updates=dict(updates),
            )
        return updates

    def _process_factual_revision(
        self,
        question: Dict[str, Any],
        answer: str,
        knowledge_graph: KnowledgeGraph,
        *,
        dependency_graph: Optional[DependencyGraph] = None,
        factual_action: str,
        source_context: Optional[Dict[str, Any]],
        supersedes_stable_id: Optional[str],
        retracts_stable_id: Optional[str],
        contradicts_stable_id: Optional[str],
        answer_event_id: Optional[str],
    ) -> Dict[str, Any]:
        """Append a sourced correction, retraction, or contradiction without editing history."""
        from integrations.ipfs_datasets.types import build_user_assertion_envelope, locate_unique_byte_span

        action = str(factual_action or "").strip().lower()
        if action not in {"assert", "correct", "retract", "contradict"}:
            raise ValueError(f"unsupported factual action {factual_action}")
        context = dict(source_context or {})
        source_text = context.get("source_text")
        if not isinstance(source_text, str) or source_text == "":
            raise ValueError("a factual revision requires a new validated user source")
        span = context.get("source_span") if isinstance(context.get("source_span"), dict) else None
        if span is None:
            located = locate_unique_byte_span(source_text, str(answer or ""))
            if located.deficiency or located.start is None or located.end is None:
                raise ValueError(located.deficiency or "missing_source_span")
            span = {"start": located.start, "end": located.end, "text": located.text}
        envelope = build_user_assertion_envelope(
            source_text=source_text,
            source_kind=str(context.get("source_kind") or ""),
            source_id=str(context.get("source_id") or ""),
            message_id=str(context.get("message_id") or ""),
            document_id=str(context.get("document_id") or ""),
            assertion_status=str(context.get("assertion_status") or ""),
            extractor_version=str(context.get("extractor_version") or ""),
            source_hash=str(context.get("source_hash") or ""),
            source_span=span,
            role="fact",
            subject_key=str(context.get("subject_key") or "fact"),
            confidence=context.get("confidence"),
        )
        if not envelope.is_asserted_user_fact:
            raise ValueError(
                "a factual revision requires its own validated user source: "
                + ",".join(envelope.deficiencies)
            )
        target_id = {
            "correct": supersedes_stable_id,
            "retract": retracts_stable_id,
            "contradict": contradicts_stable_id,
        }.get(action)
        previous = None
        if action != "assert":
            # All source and target admission precedes entity/ledger mutation.
            previous = knowledge_graph.require_revision_target(target_id or "", envelope)
        span_text = envelope.source_span_text
        from integrations.ipfs_datasets.graphs import classify_epistemic_class
        question_context = question.get("context") if isinstance(question.get("context"), dict) else {}
        requested_class = str(question_context.get("epistemic_class") or "")
        if requested_class == "legal_authority":
            requested_class = ""
        epistemic_class = classify_epistemic_class(span_text, explicit=requested_class)
        entity = Entity(
            id=self._next_entity_id(knowledge_graph),
            type="fact",
            name=span_text,
            attributes={
                "description": span_text,
                "fact_type": str((question.get("context") or {}).get("fact_type") or "clarification")
                if isinstance(question.get("context"), dict) else "clarification",
                "factual_action": action,
                "epistemic_class": epistemic_class,
                "value_status": "contradiction" if action == "contradict" else "stated",
            },
            confidence=float(envelope.confidence if envelope.confidence is not None else 1.0),
            source="complaint",
            provenance={"user_assertion": envelope.as_dict()},
        )
        knowledge_graph.add_entity(entity)
        knowledge_graph.register_assertion(entity, envelope, status="active", event_id=answer_event_id or "")
        updates = {
            "entities_updated": 1,
            "relationships_added": 0,
            "requirements_satisfied": 0,
            "factual_action": action,
            "stable_id": envelope.stable_id,
            "entity_id": entity.id,
            "invalidated_support": [],
        }
        if action == "correct":
            if not supersedes_stable_id:
                raise ValueError("correction requires the assertion it supersedes")
            revision = knowledge_graph.supersede_assertion(
                supersedes_stable_id,
                entity,
                envelope,
                event_id=answer_event_id or "",
            )
            updates["revision"] = revision["revision_index"]
            updates["superseded_stable_id"] = supersedes_stable_id
        elif action == "retract":
            if not retracts_stable_id:
                raise ValueError("retraction requires the assertion it retracts")
            revision = knowledge_graph.retract_assertion(
                retracts_stable_id,
                entity,
                envelope,
                event_id=answer_event_id or "",
            )
            updates["revision"] = revision["revision_index"]
            updates["retracted_stable_id"] = retracts_stable_id
        elif action == "contradict":
            if not contradicts_stable_id:
                raise ValueError("contradiction requires the assertion it conflicts with")
            prior = knowledge_graph.entity_for_stable_id(contradicts_stable_id)
            revision = knowledge_graph.record_assertion_conflict(
                contradicts_stable_id,
                envelope.stable_id,
                event_id=answer_event_id or "",
                left_entity_id=prior.id if prior is not None else "",
                right_entity_id=entity.id,
            )
            updates["revision"] = revision["revision_index"]
            updates["conflict_stable_ids"] = [contradicts_stable_id, envelope.stable_id]
        else:
            knowledge_graph.append_revision({
                "action": "assert",
                "event_id": answer_event_id or "",
                "new_stable_id": envelope.stable_id,
                "new_entity_id": entity.id,
                "new_envelope": envelope.as_dict(),
            })
        updates["invalidated_support"] = [
            relationship.id
            for relationship in knowledge_graph.relationships.values()
            if (relationship.attributes or {}).get("activity_status") == "invalidated"
        ]
        if previous is not None and dependency_graph is not None:
            updates["dependency_nodes_invalidated"] = self._invalidate_factual_dependency_support(
                dependency_graph, question, previous, target_id or "", action,
                answer_event_id or "",
            )
        return updates

    @staticmethod
    def _invalidate_factual_dependency_support(
        dependency_graph: DependencyGraph, question: Dict[str, Any], previous: Entity,
        stable_id: str, reason: str, event_id: str,
    ) -> List[str]:
        """Reopen dependency state bound to a withdrawn or disputed source."""
        context = question.get("context") if isinstance(question.get("context"), dict) else {}
        target_ids = {str(context.get(key) or "") for key in
                      ("requirement_id", "node_id", "target_element_id")}
        previous_text = " ".join(str((previous.attributes or {}).get("description") or previous.name).split())
        invalidated = set()
        for node in dependency_graph.nodes.values():
            attrs = node.attributes if isinstance(node.attributes, dict) else {}
            refs = set()
            for key in ("source_entity_id", "fact_id", "source_fact_id", "assertion_stable_id"):
                value = attrs.get(key)
                if isinstance(value, str):
                    refs.add(value)
            for key in ("source_fact_ids", "supporting_fact_ids", "satisfied_fact_bundle", "event_support_refs"):
                values = attrs.get(key)
                if isinstance(values, list):
                    refs.update(value for value in values if isinstance(value, str))
            answer_text = " ".join(str(attrs.get("satisfied_answer_text") or "").split())
            if (node.id in target_ids or previous.id in refs or stable_id in refs
                    or (answer_text and answer_text == previous_text)):
                invalidated.add(node.id)
        # Dependents cannot retain derived satisfaction after their premise changes.
        pending = list(invalidated)
        while pending:
            source = pending.pop()
            for edge in dependency_graph.dependencies.values():
                kind = getattr(edge.dependency_type, "value", edge.dependency_type)
                if (kind in {"requires", "supports", "implies", "depends_on"}
                        and edge.source_id == source and edge.target_id not in invalidated):
                    invalidated.add(edge.target_id)
                    pending.append(edge.target_id)
        for node_id in sorted(invalidated):
            node = dependency_graph.get_node(node_id)
            if node is None:
                continue
            attrs = copy.deepcopy(node.attributes or {})
            history = list(attrs.get("factual_support_invalidations") or [])
            history.append({"event_id": event_id, "source_entity_id": previous.id,
                "assertion_stable_id": stable_id, "reason": reason,
                "previous_satisfied": bool(node.satisfied),
                "previous_satisfied_answer_text": attrs.get("satisfied_answer_text")})
            attrs["factual_support_invalidations"] = history
            attrs["support_invalidated"] = True
            attrs["satisfied_via_denoiser"] = False
            attrs.pop("satisfied_answer_text", None)
            node.attributes = attrs
            node.satisfied = False
        return sorted(invalidated)
    
    def calculate_noise_level(self, 
                             knowledge_graph: KnowledgeGraph,
                             dependency_graph: DependencyGraph) -> float:
        """
        Calculate current noise/uncertainty level.
        
        Lower values indicate less noise (more complete, confident information).
        
        Args:
            knowledge_graph: Current knowledge graph
            dependency_graph: Current dependency graph
            
        Returns:
            Noise level from 0.0 (no noise) to 1.0 (maximum noise)
        """
        # Calculate knowledge graph confidence
        kg_confidence = 0.0
        if knowledge_graph.entities:
            confidence_entities = [
                entity for entity in knowledge_graph.entities.values()
                if str(entity.type or '').strip().lower() != 'evidence'
            ]
            if not confidence_entities:
                confidence_entities = list(knowledge_graph.entities.values())
            total_confidence = sum(entity.confidence for entity in confidence_entities)
            kg_confidence = total_confidence / len(confidence_entities)
        
        # Calculate dependency satisfaction
        readiness = dependency_graph.get_claim_readiness()
        dep_satisfaction = readiness.get('overall_readiness', 0.0)
        
        # Calculate gap ratio
        kg_gaps = len(knowledge_graph.find_gaps())
        kg_entities = len(knowledge_graph.entities)
        gap_ratio = kg_gaps / max(kg_entities, 1)
        
        # Combine metrics (lower is better)
        noise = (
            (1.0 - kg_confidence) * 0.4 +  # 40% weight on entity confidence
            (1.0 - dep_satisfaction) * 0.4 +  # 40% weight on dependency satisfaction
            min(gap_ratio, 1.0) * 0.2  # 20% weight on gaps
        )
        
        return noise
    
    INTERVIEW_STOP_STATES = (
        "needs_answer",
        "saturated",
        "deferred_unknown",
        "provider_unavailable",
        "cancelled",
        "limit_reached",
        "no_progress",
        "needs_review",
    )
    STOPPING_OUTCOMES = (
        "saturated",
        "complete",
        "paused",
        "awaiting_user",
        "deferred_needs_evidence",
        "blocked_provider",
        "no_progress",
        "needs_review",
    )
    MAX_REPEAT_ATTEMPTS = 3
    MAX_NO_INFORMATION_ATTEMPTS = 3
    MAX_MODEL_RETRIES = 2
    _INCOMPLETE_INTERVIEW_STOPS = frozenset({
        "needs_answer",
        "deferred_unknown",
        "provider_unavailable",
        "cancelled",
        "limit_reached",
        "no_progress",
        "needs_review",
    })
    _PROVIDER_UNAVAILABLE_STATUSES = frozenset({
        "unavailable",
        "provider_unavailable",
        "error",
        "failed",
        "timeout",
        "backend_failure",
    })
    _UNKNOWN_DISPOSITIONS = frozenset({"unknown", "deferred"})
    QUESTION_COUNT_LIMIT = 50

    def is_exhausted(self) -> bool:
        """Return whether the interview itself is saturated.

        An empty question list, a loss plateau, or more than
        QUESTION_COUNT_LIMIT asked questions is not saturation.
        """
        stop = getattr(self, "last_interview_stop", None)
        return isinstance(stop, dict) and stop.get("state") == "saturated" and bool(stop.get("targets_accounted_for"))

    def assertion_rule_fingerprint(
        self,
        knowledge_graph: Optional[KnowledgeGraph] = None,
        dependency_graph: Optional[DependencyGraph] = None,
    ) -> str:
        """Stable fingerprint of assertion and rule truth, excluding wait flags."""
        entities = []
        if knowledge_graph is not None:
            for entity_id in sorted((getattr(knowledge_graph, "entities", {}) or {})):
                entity = knowledge_graph.entities[entity_id]
                entities.append({
                    "id": str(entity_id),
                    "type": str(getattr(entity, "type", "") or ""),
                    "name": str(getattr(entity, "name", "") or ""),
                    "confidence": getattr(entity, "confidence", None),
                })
        nodes = []
        if dependency_graph is not None:
            for node_id in sorted((getattr(dependency_graph, "nodes", {}) or {})):
                node = dependency_graph.nodes[node_id]
                attributes = node.attributes if isinstance(getattr(node, "attributes", None), dict) else {}
                nodes.append({
                    "id": str(node_id),
                    "name": str(getattr(node, "name", "") or ""),
                    "satisfied": bool(getattr(node, "satisfied", False)),
                    "value_status": str(attributes.get("value_status") or ""),
                    "description": str(attributes.get("description") or ""),
                })
        dispositions = []
        for record in self.question_disposition_records:
            if not isinstance(record, dict):
                continue
            dispositions.append({
                "target_id": str(record.get("target_id") or ""),
                "target_revision": str(record.get("target_revision") or ""),
                "disposition": str(record.get("disposition") or ""),
                "reopened": bool(record.get("reopened")),
            })
        payload = {"entities": entities, "nodes": nodes, "dispositions": dispositions}
        return json.dumps(payload, sort_keys=True, default=str)

    def pause_intentional_user_wait(
        self,
        *,
        reason: str = "user_pause",
        knowledge_graph: Optional[KnowledgeGraph] = None,
        dependency_graph: Optional[DependencyGraph] = None,
    ) -> Dict[str, Any]:
        """Pause for the user without rewriting assertions, rules, or iterations."""
        fingerprint = self.assertion_rule_fingerprint(knowledge_graph, dependency_graph)
        self.intentional_user_wait = {
            "status": "awaiting_user",
            "paused": True,
            "resumed": False,
            "intentional": True,
            "awaiting_user": True,
            "worker_stalled": False,
            "supervisory_restart": False,
            "reason": str(reason or "user_pause"),
            "assertion_rule_fingerprint": fingerprint,
        }
        return dict(self.intentional_user_wait)

    def resume_intentional_user_wait(
        self,
        *,
        knowledge_graph: Optional[KnowledgeGraph] = None,
        dependency_graph: Optional[DependencyGraph] = None,
    ) -> Dict[str, Any]:
        """Resume the same user wait. Do not restart supervision or mutate truth."""
        current = self.assertion_rule_fingerprint(knowledge_graph, dependency_graph)
        wait = getattr(self, "intentional_user_wait", None)
        if not isinstance(wait, dict) or not wait.get("intentional"):
            return {
                "status": "needs_answer",
                "paused": False,
                "resumed": False,
                "awaiting_user": False,
                "worker_stalled": False,
                "supervisory_restart": False,
                "assertion_rule_changed": False,
                "error": "no_intentional_wait",
            }
        changed = current != wait.get("assertion_rule_fingerprint")
        resumed = {
            "status": "awaiting_user",
            "paused": False,
            "resumed": not changed,
            "intentional": True,
            "awaiting_user": True,
            "worker_stalled": False,
            "supervisory_restart": False,
            "reason": wait.get("reason"),
            "assertion_rule_fingerprint": wait.get("assertion_rule_fingerprint"),
            "assertion_rule_changed": changed,
        }
        if changed:
            resumed["error"] = "assertion_rule_changed"
            return resumed
        self.intentional_user_wait = resumed
        return dict(resumed)

    def note_model_retry(self, reason: Any = None) -> int:
        """Count one model retry. The bound stops the interview without claiming progress."""
        self.model_retry_count = int(getattr(self, "model_retry_count", 0) or 0) + 1
        self._last_model_retry_reason = str(reason or "").strip() or None
        return self.model_retry_count

    def evaluate_interview_stop(
        self,
        *,
        open_questions: Optional[List[Dict[str, Any]]] = None,
        intake_case_file: Optional[Dict[str, Any]] = None,
        provider_status: Any = None,
        cancelled: bool = False,
        iteration_count: Optional[int] = None,
        iteration_cap: Optional[int] = None,
        question_limit: Optional[int] = None,
        loss_converged: bool = False,
        pool_empty: Optional[bool] = None,
        paused: bool = False,
        needs_review: bool = False,
        repeat_attempts: Optional[int] = None,
        no_information_attempts: Optional[int] = None,
        model_retries: Optional[int] = None,
        contradictions: Optional[List[Dict[str, Any]]] = None,
        open_dependencies: Optional[List[Dict[str, Any]]] = None,
        hook_completed: bool = False,
        budget_exhausted: bool = False,
        worker_stalled: bool = False,
    ) -> Dict[str, Any]:
        return denoiser_questions.evaluate_interview_stop(
            self,
            open_questions=open_questions,
            intake_case_file=intake_case_file,
            provider_status=provider_status,
            cancelled=cancelled,
            iteration_count=iteration_count,
            iteration_cap=iteration_cap,
            question_limit=question_limit,
            loss_converged=loss_converged,
            pool_empty=pool_empty,
            paused=paused,
            needs_review=needs_review,
            repeat_attempts=repeat_attempts,
            no_information_attempts=no_information_attempts,
            model_retries=model_retries,
            contradictions=contradictions,
            open_dependencies=open_dependencies,
            hook_completed=hook_completed,
            budget_exhausted=budget_exhausted,
            worker_stalled=worker_stalled,
        )

    @staticmethod
    def _interview_stop_message(state: str, intake_complete: bool) -> str:
        if state == "saturated" and intake_complete:
            return (
                "Relevant answerable targets are resolved. "
                "This is interview saturation, not filing readiness or legal sufficiency."
            )
        if state == "saturated":
            return (
                "Relevant answerable targets are resolved or explicitly disposed. "
                "Unresolved issues remain. Intake is not fully complete and the complaint is not ready to file."
            )
        if state == "deferred_unknown":
            return (
                "Remaining targets are unknown or deferred. "
                "Core facts are not complete and the complaint is not ready to file."
            )
        if state == "provider_unavailable":
            return "The interview backend is unavailable. Intake is not complete and the complaint is not ready to file."
        if state == "cancelled":
            return "The interview was cancelled. Intake is not complete and the complaint is not ready to file."
        if state == "limit_reached":
            return "The interview iteration or question limit was reached. Intake is not complete and the complaint is not ready to file."
        if state == "no_progress":
            return (
                "Repeat, no-information, or model-retry bounds stopped the interview. "
                "Unresolved issues remain. Intake is not complete and the complaint is not ready to file."
            )
        if state == "needs_review":
            return (
                "The interview needs review before it can continue. "
                "Intake is not complete and the complaint is not ready to file."
            )
        return "An answerable interview target still needs an answer. Intake is not complete and the complaint is not ready to file."
    
    def generate_evidence_questions(self,
                                   knowledge_graph: KnowledgeGraph,
                                   dependency_graph: DependencyGraph,
                                   evidence_gaps: List[Dict[str, Any]],
                                   alignment_evidence_tasks: Optional[List[Dict[str, Any]]] = None,
                                   evidence_workflow_action_queue: Optional[List[Dict[str, Any]]] = None,
                                   max_questions: int = 5) -> List[Dict[str, Any]]:
        return denoiser_questions.generate_evidence_questions(
            self,
            knowledge_graph,
            dependency_graph,
            evidence_gaps,
            alignment_evidence_tasks,
            evidence_workflow_action_queue,
            max_questions,
        )
    
    def generate_legal_matching_questions(self,
                                         matching_results: Dict[str, Any],
                                         max_questions: int = 5) -> List[Dict[str, Any]]:
        """
        Generate denoising questions for legal matching phase.
        
        Args:
            matching_results: Results from neurosymbolic matching
            max_questions: Maximum questions to generate
            
        Returns:
            List of legal-focused denoising questions
        """
        questions = []
        
        # Questions about unsatisfied legal requirements
        unmatched = matching_results.get('unmatched_requirements', [])
        for req in unmatched[:max_questions]:
            questions.append({
                'type': 'legal_requirement',
                'question': f"To satisfy the legal requirement '{req.get('name')}', can you provide: {req.get('missing_info', 'additional information')}?",
                'context': {
                    'requirement_id': req.get('id'),
                    'requirement_name': req.get('name'),
                    'legal_element': req.get('element_type')
                },
                'priority': 'high'
            })
        
        # Questions about weak matches
        weak_matches = [m for m in matching_results.get('matches', []) 
                       if m.get('confidence', 1.0) < 0.6]
        for match in weak_matches[:max(0, max_questions - len(questions))]:
            questions.append({
                'type': 'legal_strengthening',
                'question': f"Can you provide more information to strengthen the claim for: {match.get('claim_name')}?",
                'context': {
                    'claim_id': match.get('claim_id'),
                    'legal_requirement': match.get('requirement_name'),
                    'confidence': match.get('confidence')
                },
                'priority': 'medium'
            })
        
        return questions[:max_questions]
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of denoising progress."""
        return {
            'questions_asked': len(self.questions_asked),
            'questions_remaining': len(self.questions_pool),
            'exhausted': self.is_exhausted()
        }
    
    def synthesize_complaint_summary(self,
                                    knowledge_graph: KnowledgeGraph,
                                    conversation_history: List[Dict[str, Any]],
                                    evidence_list: List[Dict[str, Any]] = None) -> str:
        """
        Synthesize a human-readable summary from knowledge graph, chat transcripts, 
        and evidence without exposing raw graph structures.
        
        This implements the denoising diffusion pattern by progressively refining
        the narrative from structured data.
        
        Args:
            knowledge_graph: The complaint knowledge graph
            conversation_history: List of conversation exchanges
            evidence_list: Optional list of evidence items
            
        Returns:
            Human-readable complaint summary
        """
        summary_parts = []
        
        # Extract key entities
        people = knowledge_graph.get_entities_by_type('person')
        organizations = knowledge_graph.get_entities_by_type('organization')
        claims = knowledge_graph.get_entities_by_type('claim')
        facts = knowledge_graph.get_entities_by_type('fact')
        
        # Build narrative introduction
        if people or organizations:
            summary_parts.append("## Parties Involved")
            for person in people[:5]:  # Limit to key people
                summary_parts.append(f"- {person.name}: {person.attributes.get('role', 'individual')}")
            for org in organizations[:5]:
                summary_parts.append(f"- {org.name}: {org.attributes.get('role', 'organization')}")
            summary_parts.append("")
        
        # Summarize the complaint nature
        if claims:
            summary_parts.append("## Nature of Complaint")
            for claim in claims:
                claim_type = claim.attributes.get('claim_type', 'general')
                description = claim.attributes.get('description', claim.name)
                summary_parts.append(f"- **{claim.name}** ({claim_type}): {description}")
            summary_parts.append("")
        
        # Key facts from graph
        if facts:
            summary_parts.append("## Key Facts")
            high_conf_facts = [f for f in facts if f.confidence > 0.7]
            for fact in high_conf_facts[:10]:  # Top 10 confident facts
                summary_parts.append(f"- {fact.name}")
            summary_parts.append("")
        
        # Evidence summary
        if evidence_list and len(evidence_list) > 0:
            summary_parts.append("## Available Evidence")
            for evidence in evidence_list[:10]:
                ename = evidence.get('name', 'Evidence item')
                etype = evidence.get('type', 'document')
                summary_parts.append(f"- {ename} ({etype})")
            summary_parts.append("")
        
        # Key insights from conversation
        if conversation_history and len(conversation_history) > 0:
            summary_parts.append("## Additional Context from Discussion")
            # Extract key clarifications
            clarifications = [msg for msg in conversation_history 
                            if msg.get('type') == 'response' and len(msg.get('content', '')) > 50]
            for clarif in clarifications[:5]:  # Top 5 meaningful clarifications
                content = clarif.get('content', '')[:200]  # Limit length
                if len(clarif.get('content', '')) > 200:
                    content += "..."
                summary_parts.append(f"- {content}")
            summary_parts.append("")
        
        # Completeness assessment
        kg_summary = knowledge_graph.summary()
        completeness = "high" if kg_summary['total_entities'] > 10 else "moderate" if kg_summary['total_entities'] > 5 else "developing"
        summary_parts.append(f"**Complaint Status:** Information gathering {completeness}ly complete with {kg_summary['total_entities']} key elements identified.")
        
        return "\n".join(summary_parts)


    # ------------------------------------------------------------------ #
    # Batch 206: Question history and policy analysis methods            #
    # ------------------------------------------------------------------ #

    def total_questions_asked(self) -> int:
        """Return total number of questions asked during denoising.

        Returns:
            Count of questions in history.
        """
        return len(self.questions_asked)

    def question_pool_size(self) -> int:
        """Return current size of the question pool.

        Returns:
            Number of candidate questions available.
        """
        return len(self.questions_pool)

    def question_type_frequency(self) -> dict:
        """Count frequency of each question type asked.

        Returns:
            Dict mapping question types to occurrence counts.
        """
        type_counts: dict = {}
        for q in self.questions_asked:
            qtype = q.get('type', 'unknown')
            type_counts[qtype] = type_counts.get(qtype, 0) + 1
        return type_counts

    def most_frequent_question_type(self) -> str:
        """Identify the most frequently asked question type.

        Returns:
            Name of most common question type, or 'none' if no questions asked.
        """
        freq = self.question_type_frequency()
        if not freq:
            return 'none'
        return max(freq.items(), key=lambda x: x[1])[0]

    def average_gain_per_question(self) -> float:
        """Calculate average gain across recent questions.

        Returns:
            Mean of recent gains, or 0.0 if no gains recorded.
        """
        if not self._recent_gains:
            return 0.0
        return sum(self._recent_gains) / len(self._recent_gains)

    def gain_variance(self) -> float:
        """Calculate variance of gains across recent questions.

        Returns:
            Variance of _recent_gains, or 0.0 if fewer than 2 gains.
        """
        if len(self._recent_gains) < 2:
            return 0.0
        mean = sum(self._recent_gains) / len(self._recent_gains)
        variance = sum((g - mean) ** 2 for g in self._recent_gains) / len(self._recent_gains)
        return variance

    def momentum_enabled_for_types(self) -> list:
        """List question types with momentum tracking enabled.

        Returns:
            List of question types with EMA state.
        """
        return list(self._type_gain_ema.keys())

    def highest_momentum_type(self) -> str:
        """Identify question type with highest momentum (EMA gain).

        Returns:
            Question type with max EMA, or 'none' if no momentum tracked.
        """
        if not self._type_gain_ema:
            return 'none'
        return max(self._type_gain_ema.items(), key=lambda x: x[1])[0]

    def is_exploration_active(self) -> bool:
        """Check if exploration mode is currently enabled.

        Returns:
            True if exploration_enabled is True.
        """
        return self.exploration_enabled

    def stagnation_detection_window(self) -> int:
        """Return the configured stagnation detection window size.

        Returns:
            Number of recent gains to check for stagnation.
        """
        return self.stagnation_window


    # =====================================================================
    # Batch 219: Question-answer interaction analysis methods
    # =====================================================================
    
    def total_answers_received(self) -> int:
        """Return total number of answers received.
        
        Returns:
            Count of questions with answers in history.
        """
        return len(self.questions_asked)
    
    def questions_by_priority(self, priority: str) -> int:
        """Count questions asked with a specific priority level.
        
        Args:
            priority: Priority level to filter by (e.g., 'high', 'medium', 'low')
            
        Returns:
            Number of questions with that priority.
        """
        count = 0
        for item in self.questions_asked:
            q = item.get('question', {})
            if q.get('priority') == priority:
                count += 1
        return count
    
    def priority_distribution(self) -> Dict[str, int]:
        """Get frequency distribution of question priorities.
        
        Returns:
            Dict mapping priority levels to occurrence counts.
        """
        dist: Dict[str, int] = {}
        for item in self.questions_asked:
            q = item.get('question', {})
            priority = q.get('priority', 'unknown')
            dist[priority] = dist.get(priority, 0) + 1
        return dist
    
    def unanswered_pool_questions(self) -> int:
        """Return count of questions in pool waiting to be asked.
        
        Returns:
            Size of the questions_pool.
        """
        return len(self.questions_pool)
    
    def questions_with_context(self) -> int:
        """Count questions that have context information.
        
        Returns:
            Number of asked questions with non-empty context dict.
        """
        count = 0
        for item in self.questions_asked:
            q = item.get('question', {})
            context = q.get('context', {})
            if context:
                count += 1
        return count
    
    def average_answer_length(self) -> float:
        """Calculate average length of answers received.
        
        Returns:
            Mean normalized character count of answers, or 0.0 if none.
        """
        if not self.questions_asked:
            return 0.0

        total_length = sum(
            self._normalized_answer_length(item.get('answer', ''))
            for item in self.questions_asked
        )
        return total_length / len(self.questions_asked)

    @staticmethod
    def _normalized_answer_length(answer: str) -> int:
        """Return the raw character length for an answer."""
        if not answer:
            return 0
        return len(str(answer))
    
    def shortest_answer(self) -> int:
        """Find the length of the shortest answer received.
        
        Returns:
            Minimum answer length, or 0 if no answers.
        """
        if not self.questions_asked:
            return 0
        return min(
            self._normalized_answer_length(item.get('answer', ''))
            for item in self.questions_asked
        )
    
    def longest_answer(self) -> int:
        """Find the length of the longest answer received.
        
        Returns:
            Maximum answer length, or 0 if no answers.
        """
        if not self.questions_asked:
            return 0
        return max(
            self._normalized_answer_length(item.get('answer', ''))
            for item in self.questions_asked
        )
    
    def question_type_priority_matrix(self) -> Dict[str, Dict[str, int]]:
        """Build matrix showing priority distribution per question type.
        
        Returns:
            Nested dict: {question_type: {priority: count}}
        """
        matrix: Dict[str, Dict[str, int]] = {}
        for item in self.questions_asked:
            q = item.get('question', {})
            qtype = q.get('type', 'unknown')
            priority = q.get('priority', 'unknown')
            
            if qtype not in matrix:
                matrix[qtype] = {}
            matrix[qtype][priority] = matrix[qtype].get(priority, 0) + 1
        
        return matrix
    
    def recent_question_types(self, n: int = 5) -> List[str]:
        """Get the types of the most recent n questions.
        
        Args:
            n: Number of recent questions to examine
            
        Returns:
            List of question types in reverse chronological order.
        """
        recent = self.questions_asked[-n:] if n <= len(self.questions_asked) else self.questions_asked
        return [item.get('question', {}).get('type', 'unknown') for item in reversed(recent)]
