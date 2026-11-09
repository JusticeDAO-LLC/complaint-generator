from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Set


@dataclass(frozen=True)
class TemporalEventRequirement:
    """A role-tagged event a legal timing profile expects to find."""

    event_id: str
    role: str
    label: str
    required: bool = True
    accepted_element_tags: List[str] = field(default_factory=list)
    required_anchor: bool = True
    missing_issue_category: str = "missing_anchor"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LegalTemporalWindow:
    """A claim-specific timing window or ordering rule."""

    window_id: str
    label: str
    window_type: str
    source_event_role: str
    target_event_role: str
    relation: str = "before"
    min_days: Optional[int] = None
    max_days: Optional[int] = None
    violation_issue_category: str = "legal_window_violation"
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TemporalRuleProfileContract:
    """Stable, data-only contract for claim-type temporal rule evaluation."""

    profile_id: str
    rule_frame_id: str
    claim_type: str
    description: str
    required_events: List[TemporalEventRequirement] = field(default_factory=list)
    optional_events: List[TemporalEventRequirement] = field(default_factory=list)
    legal_windows: List[LegalTemporalWindow] = field(default_factory=list)
    defenses: List[str] = field(default_factory=list)
    issue_categories: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


RETALIATION_TEMPORAL_PROFILE_ID = "retaliation_temporal_profile_v1"
RETALIATION_TEMPORAL_RULE_FRAME_ID = "retaliation_temporal_frame"


_RETALIATION_TEMPORAL_PROFILE = TemporalRuleProfileContract(
    profile_id=RETALIATION_TEMPORAL_PROFILE_ID,
    rule_frame_id=RETALIATION_TEMPORAL_RULE_FRAME_ID,
    claim_type="retaliation",
    description=(
        "Evaluates whether protected activity, adverse action, and causal "
        "connection chronology are present and legally ordered."
    ),
    required_events=[
        TemporalEventRequirement(
            event_id="retaliation_protected_activity_event",
            role="protected_activity",
            label="Protected activity",
            accepted_element_tags=["protected_activity", "protectedactivity"],
            missing_issue_category="retaliation_missing_causation",
        ),
        TemporalEventRequirement(
            event_id="retaliation_adverse_action_event",
            role="adverse_action",
            label="Adverse action",
            accepted_element_tags=["adverse_action", "adverseaction"],
            missing_issue_category="missing_anchor",
        ),
    ],
    optional_events=[
        TemporalEventRequirement(
            event_id="retaliation_employer_knowledge_event",
            role="employer_knowledge",
            label="Employer knowledge of protected activity",
            required=False,
            accepted_element_tags=["employer_knowledge", "knowledge"],
            required_anchor=False,
            missing_issue_category="retaliation_missing_knowledge_timing",
        ),
        TemporalEventRequirement(
            event_id="retaliation_exhaustion_or_charge_event",
            role="administrative_charge",
            label="Administrative charge or agency filing",
            required=False,
            accepted_element_tags=["administrative_charge", "eeoc_charge", "filing"],
            required_anchor=True,
            missing_issue_category="limitations_risk",
        ),
    ],
    legal_windows=[
        LegalTemporalWindow(
            window_id="retaliation_protected_activity_before_adverse_action",
            label="Protected activity precedes adverse action",
            window_type="ordering",
            source_event_role="protected_activity",
            target_event_role="adverse_action",
            relation="before",
            violation_issue_category="retaliation_missing_sequence",
            description=(
                "Causation requires the protected activity to precede the adverse action "
                "or another legally sufficient causal sequence."
            ),
        ),
        LegalTemporalWindow(
            window_id="retaliation_eeoc_180_day_charge_window",
            label="EEOC 180-day non-deferral filing risk window",
            window_type="filing_deadline",
            source_event_role="adverse_action",
            target_event_role="administrative_charge",
            relation="within_days",
            max_days=180,
            violation_issue_category="limitations_risk",
            description=(
                "Flags non-deferral jurisdiction charge-timeliness risk when the adverse "
                "action is more than 180 days old."
            ),
        ),
        LegalTemporalWindow(
            window_id="retaliation_eeoc_300_day_deferral_charge_window",
            label="EEOC 300-day deferral filing risk window",
            window_type="filing_deadline",
            source_event_role="adverse_action",
            target_event_role="administrative_charge",
            relation="within_days",
            max_days=300,
            violation_issue_category="limitations_risk",
            description=(
                "Documents the longer deferral-state charge-timeliness window for "
                "review and proof explanations."
            ),
        ),
    ],
    defenses=[
        "same_decision_without_protected_activity",
        "legitimate_nonretaliatory_reason",
        "lack_of_employer_knowledge",
        "untimely_administrative_charge",
    ],
    issue_categories=[
        "retaliation_missing_causation",
        "retaliation_missing_causation_link",
        "retaliation_missing_sequence",
        "retaliation_missing_sequencing_dates",
        "temporal_reverse_before",
        "limitations_risk",
        "contradictory_dates",
    ],
)


_TEMPORAL_RULE_PROFILE_REGISTRY: Dict[str, TemporalRuleProfileContract] = {
    _RETALIATION_TEMPORAL_PROFILE.profile_id: _RETALIATION_TEMPORAL_PROFILE,
}

_CLAIM_TYPE_PROFILE_ALIASES: Dict[str, str] = {
    "retaliation": RETALIATION_TEMPORAL_PROFILE_ID,
    "employment_retaliation": RETALIATION_TEMPORAL_PROFILE_ID,
    "employment_discrimination_retaliation": RETALIATION_TEMPORAL_PROFILE_ID,
}


def list_temporal_rule_profiles() -> List[Dict[str, Any]]:
    """Return all registered legal temporal rule profile contracts."""
    return [
        profile.to_dict()
        for profile in sorted(
            _TEMPORAL_RULE_PROFILE_REGISTRY.values(),
            key=lambda item: item.profile_id,
        )
    ]


def get_temporal_rule_profile_contract(profile_id: Any) -> Optional[Dict[str, Any]]:
    """Return a registered profile contract by profile id."""
    profile = _TEMPORAL_RULE_PROFILE_REGISTRY.get(str(profile_id or "").strip())
    return profile.to_dict() if profile else None


def get_temporal_rule_profile_for_claim_type(claim_type: Any) -> Optional[Dict[str, Any]]:
    """Return the explicit temporal rule profile contract for a claim type."""
    normalized = _normalize_key(claim_type)
    profile_id = _CLAIM_TYPE_PROFILE_ALIASES.get(normalized)
    if not profile_id and _is_retaliation_claim_type(claim_type):
        profile_id = RETALIATION_TEMPORAL_PROFILE_ID
    return get_temporal_rule_profile_contract(profile_id) if profile_id else None


def has_temporal_rule_profile(claim_type: Any) -> bool:
    """Return whether the claim type has an explicit legal timing profile."""
    return get_temporal_rule_profile_for_claim_type(claim_type) is not None


def get_temporal_event_roles(claim_type: Any) -> List[str]:
    """Return required and optional event roles for a claim type's profile."""
    profile = get_temporal_rule_profile_for_claim_type(claim_type) or {}
    roles: List[str] = []
    for event in list(profile.get("required_events", []) or []) + list(profile.get("optional_events", []) or []):
        role = str(event.get("role") or "").strip()
        if role and role not in roles:
            roles.append(role)
    return roles


# ---------------------------------------------------------------------------
# T4: Canonical issue-category → follow-up lane mapping.
#
# Each entry maps a normalised issue_category key to a dict with:
#   - follow_up_lane: canonical lane identifier for routing and deduplication
#   - follow_up_target: the kind of resource the follow-up seeks
#       "testimony"              — an oral or written statement from the complainant
#       "document_request"       — a dated document from the respondent or third party
#       "external_corroboration" — a public record, agency file, or external source
#       "clarification"          — a clarifying question back to the complainant
#   - proof_criticality: how urgently the gap blocks legal sufficiency
#       "high"   — blocks a required element; must be resolved before drafting
#       "medium" — weakens element satisfaction; should be resolved before filing
#       "low"    — informational; helps but does not block drafting readiness
#   - question_objective: the concrete goal of any follow-up question generated
#       "anchor_capture"         — get a specific date or time anchor
#       "contradiction_resolution" — resolve conflicting date records
#       "deadline_verification"  — verify whether a filing deadline has passed
#       "testimony_capture"      — collect the event narrative and date together
#       "document_verification"  — confirm a document and its date exist
#
# Only issue categories that require differentiated routing are listed.  All
# others fall back to the generic "clarify_with_complainant" / "clarification"
# profile so that new issue types degrade gracefully.
# ---------------------------------------------------------------------------
_TEMPORAL_ISSUE_FOLLOW_UP_PROFILES: Dict[str, Dict[str, str]] = {
    # ---- anchor gaps -------------------------------------------------------
    "missing_anchor": {
        "follow_up_lane": "anchor_capture",
        "follow_up_target": "testimony",
        "proof_criticality": "high",
        "question_objective": "anchor_capture",
    },
    "missing_start_date": {
        "follow_up_lane": "anchor_capture",
        "follow_up_target": "testimony",
        "proof_criticality": "high",
        "question_objective": "anchor_capture",
    },
    "missing_end_date": {
        "follow_up_lane": "anchor_capture",
        "follow_up_target": "testimony",
        "proof_criticality": "medium",
        "question_objective": "anchor_capture",
    },
    "relative_only_ordering": {
        "follow_up_lane": "anchor_capture",
        "follow_up_target": "document_request",
        "proof_criticality": "medium",
        "question_objective": "anchor_capture",
    },
    # ---- contradiction categories ------------------------------------------
    "contradictory_dates": {
        "follow_up_lane": "contradiction_resolution",
        "follow_up_target": "document_request",
        "proof_criticality": "high",
        "question_objective": "contradiction_resolution",
    },
    "temporal_reverse_before": {
        "follow_up_lane": "contradiction_resolution",
        "follow_up_target": "document_request",
        "proof_criticality": "high",
        "question_objective": "contradiction_resolution",
    },
    "conflicting_sequence": {
        "follow_up_lane": "contradiction_resolution",
        "follow_up_target": "document_request",
        "proof_criticality": "high",
        "question_objective": "contradiction_resolution",
    },
    # ---- limitations / deadline -------------------------------------------
    "limitations_risk": {
        "follow_up_lane": "deadline_verification",
        "follow_up_target": "external_corroboration",
        "proof_criticality": "high",
        "question_objective": "deadline_verification",
    },
    # ---- retaliation-specific gaps ----------------------------------------
    "retaliation_missing_causation": {
        "follow_up_lane": "anchor_capture",
        "follow_up_target": "testimony",
        "proof_criticality": "high",
        "question_objective": "testimony_capture",
    },
    "retaliation_missing_causation_link": {
        "follow_up_lane": "anchor_capture",
        "follow_up_target": "testimony",
        "proof_criticality": "high",
        "question_objective": "testimony_capture",
    },
    "retaliation_missing_sequence": {
        "follow_up_lane": "anchor_capture",
        "follow_up_target": "document_request",
        "proof_criticality": "high",
        "question_objective": "anchor_capture",
    },
    "retaliation_missing_sequencing_dates": {
        "follow_up_lane": "anchor_capture",
        "follow_up_target": "document_request",
        "proof_criticality": "high",
        "question_objective": "anchor_capture",
    },
    # ---- document-date gaps -----------------------------------------------
    "missing_hearing_request_date": {
        "follow_up_lane": "document_request",
        "follow_up_target": "document_request",
        "proof_criticality": "medium",
        "question_objective": "document_verification",
    },
    "missing_hearing_timing": {
        "follow_up_lane": "document_request",
        "follow_up_target": "document_request",
        "proof_criticality": "medium",
        "question_objective": "document_verification",
    },
    "missing_response_dates": {
        "follow_up_lane": "document_request",
        "follow_up_target": "document_request",
        "proof_criticality": "medium",
        "question_objective": "document_verification",
    },
    "missing_decision_timeline": {
        "follow_up_lane": "document_request",
        "follow_up_target": "document_request",
        "proof_criticality": "medium",
        "question_objective": "document_verification",
    },
    "missing_written_notice": {
        "follow_up_lane": "document_request",
        "follow_up_target": "document_request",
        "proof_criticality": "medium",
        "question_objective": "document_verification",
    },
}

# Map legacy lane names from proof-rule follow-ups to canonical follow_up_target values.
_LANE_TO_TARGET: Dict[str, str] = {
    "clarify_with_complainant": "clarification",
    "capture_testimony": "testimony",
    "request_document": "document_request",
    "seek_external_record": "external_corroboration",
    "anchor_capture": "testimony",
    "contradiction_resolution": "document_request",
    "deadline_verification": "external_corroboration",
    "document_request": "document_request",
}

# Criticality ordering for ranking (higher index = higher priority).
_CRITICALITY_ORDER = {"high": 2, "medium": 1, "low": 0}


def get_follow_up_profile(issue_category: str) -> Dict[str, str]:
    """Return the canonical follow-up profile for *issue_category*.

    Falls back to a generic clarification profile when the category is not
    registered in ``_TEMPORAL_ISSUE_FOLLOW_UP_PROFILES``.
    """
    normalised = _normalize_key(issue_category)
    if normalised in _TEMPORAL_ISSUE_FOLLOW_UP_PROFILES:
        return dict(_TEMPORAL_ISSUE_FOLLOW_UP_PROFILES[normalised])
    return {
        "follow_up_lane": "clarify_with_complainant",
        "follow_up_target": "clarification",
        "proof_criticality": "medium",
        "question_objective": "anchor_capture",
    }


def enrich_follow_up(follow_up: Dict[str, Any], issue_category: str = "") -> Dict[str, Any]:
    """Attach T4 enrichment fields to a follow-up dict if they are absent.

    Safe to call on already-enriched dicts; existing values are preserved.
    """
    profile = get_follow_up_profile(issue_category)
    enriched = dict(follow_up)
    if "follow_up_target" not in enriched:
        # Derive from existing lane if present, else use the canonical profile.
        existing_lane = str(enriched.get("lane") or enriched.get("follow_up_lane") or "").strip()
        enriched["follow_up_target"] = (
            _LANE_TO_TARGET.get(existing_lane)
            or _LANE_TO_TARGET.get(profile["follow_up_lane"])
            or profile["follow_up_target"]
        )
    if "follow_up_lane" not in enriched and "lane" in enriched:
        enriched["follow_up_lane"] = str(enriched["lane"])
    elif "follow_up_lane" not in enriched:
        enriched["follow_up_lane"] = profile["follow_up_lane"]
    if "proof_criticality" not in enriched:
        enriched["proof_criticality"] = profile["proof_criticality"]
    if "question_objective" not in enriched:
        enriched["question_objective"] = profile["question_objective"]
    return enriched


def rank_follow_ups(follow_ups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return *follow_ups* sorted by proof_criticality (high first), stable."""
    return sorted(
        follow_ups,
        key=lambda fu: _CRITICALITY_ORDER.get(str(fu.get("proof_criticality") or "medium"), 1),
        reverse=True,
    )


def _normalize_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    return "".join(ch if ch.isalnum() else "_" for ch in text).strip("_")


def _latest_anchored_date(facts: List[Dict[str, Any]]) -> Optional[str]:
    """Return the latest start_date found across a list of temporal facts, or None."""
    best: Optional[str] = None
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        tc = fact.get("temporal_context") if isinstance(fact.get("temporal_context"), dict) else {}
        start = str(tc.get("start_date") or "").strip()
        if not start:
            continue
        if best is None or start > best:
            best = start
    return best


def _is_retaliation_claim_type(claim_type: Any) -> bool:
    normalized = _normalize_key(claim_type)
    return normalized == "retaliation" or normalized.endswith("retaliation") or "retaliation" in normalized.split("_")


def _element_role(element: Dict[str, Any]) -> str:
    candidates = [
        _normalize_key(element.get("element_id")),
        _normalize_key(element.get("element_text")),
    ]
    for candidate in candidates:
        if candidate in {"protected_activity", "protectedactivity"}:
            return "protected_activity"
        if candidate in {"adverse_action", "adverseaction"}:
            return "adverse_action"
        if candidate in {"causal_connection", "causation", "causal_link", "causal_nexus"}:
            return "causal_connection"
    return ""


def _record_tags(record: Dict[str, Any]) -> Set[str]:
    tags: Set[str] = set()
    for field_name in ("element_tags", "affected_element_ids"):
        values = record.get(field_name)
        if isinstance(values, list):
            for value in values:
                normalized = _normalize_key(value)
                if normalized:
                    tags.add(normalized)
    return tags


def evaluate_temporal_rule_profile(
    claim_type: Any,
    element: Dict[str, Any],
    temporal_context: Dict[str, Any],
    *,
    reference_date: Optional[date] = None,
) -> Dict[str, Any]:
    if not _is_retaliation_claim_type(claim_type):
        return {
            "available": False,
            "evaluated": False,
            "profile_id": "",
            "rule_frame_id": "",
            "status": "not_applicable",
            "reason": "No temporal rule profile for this claim type.",
        }

    role = _element_role(element if isinstance(element, dict) else {})
    if not role:
        return {
            "available": True,
            "evaluated": False,
            "profile_id": RETALIATION_TEMPORAL_PROFILE_ID,
            "rule_frame_id": RETALIATION_TEMPORAL_RULE_FRAME_ID,
            "status": "not_targeted",
            "reason": "Element is not covered by the retaliation temporal profile.",
        }

    facts = temporal_context.get("temporal_facts", []) if isinstance(temporal_context, dict) else []
    relations = temporal_context.get("temporal_relations", []) if isinstance(temporal_context, dict) else []
    issues = temporal_context.get("temporal_issues", []) if isinstance(temporal_context, dict) else []

    protected_facts = [fact for fact in facts if isinstance(fact, dict) and "protected_activity" in _record_tags(fact)]
    adverse_facts = [fact for fact in facts if isinstance(fact, dict) and "adverse_action" in _record_tags(fact)]
    protected_fact_ids = [str(fact.get("fact_id") or "").strip() for fact in protected_facts if str(fact.get("fact_id") or "").strip()]
    adverse_fact_ids = [str(fact.get("fact_id") or "").strip() for fact in adverse_facts if str(fact.get("fact_id") or "").strip()]
    anchored_protected_fact_ids = [
        fact_id
        for fact_id, fact in ((str(fact.get("fact_id") or "").strip(), fact) for fact in protected_facts if isinstance(fact, dict))
        if fact_id and isinstance(fact.get("temporal_context"), dict) and fact["temporal_context"].get("start_date")
    ]
    anchored_adverse_fact_ids = [
        fact_id
        for fact_id, fact in ((str(fact.get("fact_id") or "").strip(), fact) for fact in adverse_facts if isinstance(fact, dict))
        if fact_id and isinstance(fact.get("temporal_context"), dict) and fact["temporal_context"].get("start_date")
    ]

    before_relations: List[Dict[str, Any]] = []
    reverse_before_relations: List[Dict[str, Any]] = []
    partial_relations: List[Dict[str, Any]] = []
    for relation in relations:
        if not isinstance(relation, dict):
            continue
        source_fact_id = str(relation.get("source_fact_id") or "").strip()
        target_fact_id = str(relation.get("target_fact_id") or "").strip()
        relation_type = _normalize_key(relation.get("relation_type"))
        if source_fact_id in protected_fact_ids and target_fact_id in adverse_fact_ids:
            if relation_type == "before":
                before_relations.append(relation)
            elif relation_type in {"same_time", "overlaps"}:
                partial_relations.append(relation)
        elif source_fact_id in adverse_fact_ids and target_fact_id in protected_fact_ids and relation_type == "before":
            reverse_before_relations.append(relation)

    relevant_issue_types = {
        _normalize_key(issue.get("issue_type") or issue.get("category"))
        for issue in issues
        if isinstance(issue, dict)
    }

    blocking_reasons: List[str] = []
    warnings: List[str] = []
    recommended_follow_ups: List[Dict[str, str]] = []
    matched_fact_ids: List[str] = []
    matched_relation_ids: List[str] = []
    status = "missing"

    if role == "protected_activity":
        matched_fact_ids = protected_fact_ids
        if anchored_protected_fact_ids:
            status = "satisfied"
        elif protected_fact_ids:
            status = "partial"
            blocking_reasons.append("Protected activity is identified but lacks a normalized time anchor.")
            recommended_follow_ups.append(enrich_follow_up({
                "lane": "clarify_with_complainant",
                "reason": "Anchor when the protected activity occurred.",
            }, issue_category="missing_anchor"))
        else:
            blocking_reasons.append("No temporally identified protected activity event is present.")
            recommended_follow_ups.append(enrich_follow_up({
                "lane": "capture_testimony",
                "reason": "Identify the protected activity and when it occurred.",
            }, issue_category="retaliation_missing_causation"))
    elif role == "adverse_action":
        matched_fact_ids = adverse_fact_ids
        if anchored_adverse_fact_ids:
            status = "satisfied"
        elif adverse_fact_ids:
            status = "partial"
            blocking_reasons.append("Adverse action is identified but lacks a normalized time anchor.")
            recommended_follow_ups.append(enrich_follow_up({
                "lane": "request_document",
                "reason": "Anchor the adverse action with a dated document or testimony.",
            }, issue_category="missing_anchor"))
        else:
            blocking_reasons.append("No temporally identified adverse action event is present.")
            recommended_follow_ups.append(enrich_follow_up({
                "lane": "request_document",
                "reason": "Collect dated records showing the adverse action.",
            }, issue_category="missing_anchor"))
    else:
        matched_fact_ids = list(dict.fromkeys(protected_fact_ids + adverse_fact_ids))
        matched_relation_ids = [
            str(relation.get("relation_id") or "").strip()
            for relation in before_relations + reverse_before_relations + partial_relations
            if str(relation.get("relation_id") or "").strip()
        ]
        if reverse_before_relations or "temporal_reverse_before" in relevant_issue_types:
            status = "failed"
            blocking_reasons.append("Available chronology places the adverse action before the protected activity.")
            recommended_follow_ups.append(enrich_follow_up({
                "lane": "request_document",
                "reason": "Resolve the reverse-order chronology with dated records.",
            }, issue_category="temporal_reverse_before"))
        elif before_relations:
            status = "satisfied"
        elif protected_fact_ids and adverse_fact_ids:
            status = "partial"
            if partial_relations:
                warnings.append("Protected activity and adverse action are only tied by overlapping or same-time chronology.")
            else:
                warnings.append("Protected activity and adverse action are both present but lack an ordering relation.")
            blocking_reasons.append("Retaliation causation lacks a clear temporal ordering from protected activity to adverse action.")
            recommended_follow_ups.append(enrich_follow_up({
                "lane": "clarify_with_complainant",
                "reason": "Clarify whether the protected activity occurred before the adverse action.",
            }, issue_category="retaliation_missing_sequence"))
        else:
            if not protected_fact_ids:
                blocking_reasons.append("Retaliation chronology is missing a protected activity event.")
            if not adverse_fact_ids:
                blocking_reasons.append("Retaliation chronology is missing an adverse action event.")
            recommended_follow_ups.append(enrich_follow_up({
                "lane": "capture_testimony",
                "reason": "Collect the missing retaliation chronology events and their dates.",
            }, issue_category="retaliation_missing_causation"))

    if role in {"protected_activity", "adverse_action"} and "relative_only_ordering" in relevant_issue_types:
        warnings.append("Relevant chronology still relies on relative-only ordering.")

    # T2: Contradictory-dates detection — applies primarily to causal_connection but checked for all roles.
    has_contradictory_dates = "contradictory_dates" in relevant_issue_types
    if has_contradictory_dates:
        warnings.append("Contradictory date records are present; chronological ordering is uncertain.")
        if role not in {"protected_activity", "adverse_action"} and status == "satisfied":
            # A satisfied causal ordering claim is weakened when dates contradict.
            status = "partial"
            blocking_reasons.append("Contradictory dates prevent confident ordering confirmation.")
        if role not in {"protected_activity", "adverse_action"}:
            recommended_follow_ups.append(enrich_follow_up({
                "lane": "request_document",
                "reason": "Resolve date contradictions with a dated document or authoritative record.",
            }, issue_category="contradictory_dates"))

    # T2: Limitations-risk detection.  Check both the issue registry and, where anchored
    # adverse-action dates are available, compute the elapsed days against the EEOC filing
    # window.  Two thresholds exist in practice: 180 days in non-deferral states (no state
    # or local fair employment practices agency) and 300 days in deferral states (where a
    # state or local agency exists).  We flag the risk at 180 days so that both non-deferral
    # and deferral cases are caught early; callers can inspect limitations_risk_days to
    # determine which window applies.  This is a warning, not a hard blocker, because the
    # exact limitations period depends on jurisdiction and filing date facts that may not
    # always be in the record.
    has_limitations_risk = "limitations_risk" in relevant_issue_types
    limitations_risk_days: Optional[int] = None
    if not has_limitations_risk and reference_date is not None and anchored_adverse_fact_ids:
        latest_adverse_date = _latest_anchored_date(adverse_facts)
        if latest_adverse_date:
            try:
                event_date = date.fromisoformat(latest_adverse_date[:10])
                days_elapsed = (reference_date - event_date).days
                if days_elapsed > 180:
                    has_limitations_risk = True
                    limitations_risk_days = days_elapsed
            except (ValueError, TypeError):
                pass
    if has_limitations_risk:
        if limitations_risk_days is not None:
            warnings.append(
                f"Adverse action occurred approximately {limitations_risk_days} days ago, "
                "which may be outside the standard EEOC filing window (300 days in deferral "
                "states, 180 days in non-deferral states)."
            )
        else:
            warnings.append(
                "A limitations risk issue is present; the adverse action may be outside the "
                "standard EEOC filing window (300 days in deferral states, 180 days in "
                "non-deferral states)."
            )
        recommended_follow_ups.append(enrich_follow_up({
            "lane": "seek_external_record",
            "reason": "Verify the adverse action date against applicable filing deadlines to assess limitations risk.",
        }, issue_category="limitations_risk"))

    # T4: rank follow-ups by proof criticality (high first) before returning.
    ranked_follow_ups = rank_follow_ups(recommended_follow_ups)

    return {
        "available": True,
        "evaluated": True,
        "profile_id": RETALIATION_TEMPORAL_PROFILE_ID,
        "rule_frame_id": RETALIATION_TEMPORAL_RULE_FRAME_ID,
        "claim_type": str(claim_type or ""),
        "element_role": role,
        "status": status,
        "matched_fact_ids": matched_fact_ids,
        "matched_relation_ids": matched_relation_ids,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
        "recommended_follow_ups": ranked_follow_ups,
        "has_contradictory_dates": has_contradictory_dates,
        "has_limitations_risk": has_limitations_risk,
    }
