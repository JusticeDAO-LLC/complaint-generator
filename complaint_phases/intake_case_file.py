"""
Helpers for building and summarizing the structured intake case file.
"""

from __future__ import annotations

import calendar
from datetime import UTC, datetime
from itertools import combinations
import re
from typing import Any, Dict, List

from .intake_claim_registry import normalize_claim_type, refresh_required_elements, registry_for_claim_type


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _status(has_value: bool) -> str:
    return "complete" if has_value else "missing"


def _coerce_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _coerce_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _coerce_provenance_refs(value: Any) -> List[Any]:
    refs: List[Any] = []
    seen = set()
    for item in value if isinstance(value, list) else []:
        if isinstance(item, dict):
            normalized_item = {
                key: (_normalize_text(val) if isinstance(val, str) else val)
                for key, val in item.items()
            }
            marker = tuple(sorted(normalized_item.items()))
            if marker in seen:
                continue
            seen.add(marker)
            refs.append(normalized_item)
            continue
        normalized = _normalize_text(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        refs.append(normalized)
    return refs


def _unique_normalized_strings(values: Any) -> List[str]:
    normalized_values: List[str] = []
    for value in values if isinstance(values, list) else []:
        normalized = _normalize_text(value)
        if normalized and normalized not in normalized_values:
            normalized_values.append(normalized)
    return normalized_values


def _coerce_confirmation_record(value: Any) -> Dict[str, Any]:
    record = _coerce_dict(value)
    return {
        "status": _normalize_text(record.get("status") or ""),
        "confirmed": bool(record.get("confirmed", False)),
        "confirmed_at": _normalize_text(record.get("confirmed_at") or "") or None,
        "confirmation_source": _normalize_text(record.get("confirmation_source") or "complainant") or "complainant",
        "confirmation_note": _normalize_text(record.get("confirmation_note") or ""),
        "summary_snapshot_index": record.get("summary_snapshot_index"),
        "current_summary_snapshot": _coerce_dict(record.get("current_summary_snapshot")),
        "confirmed_summary_snapshot": _coerce_dict(record.get("confirmed_summary_snapshot")),
    }


_MONTH_NAME_TO_NUMBER = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

_APPROXIMATE_TEMPORAL_MARKERS = (
    "about",
    "approximately",
    "approx",
    "around",
    "circa",
    "early",
    "mid",
    "late",
)

_RELATIVE_TEMPORAL_MARKERS = (
    "before",
    "after",
    "during",
    "same day",
    "next day",
    "previous day",
    "later",
    "earlier",
    "by",
    "until",
    "since",
)


def _normalize_date_iso(year: int, month: int, day: int) -> str:
    return f"{year:04d}-{month:02d}-{day:02d}"


def _month_bounds(year: int, month: int) -> tuple[str, str]:
    last_day = calendar.monthrange(year, month)[1]
    return _normalize_date_iso(year, month, 1), _normalize_date_iso(year, month, last_day)


def _year_bounds(year: int) -> tuple[str, str]:
    return _normalize_date_iso(year, 1, 1), _normalize_date_iso(year, 12, 31)


def _coerce_two_digit_year(year: int) -> int:
    if year >= 100:
        return year
    return 2000 + year if year < 70 else 1900 + year


def _extract_temporal_markers(value: str, markers: tuple[str, ...]) -> List[str]:
    normalized = _normalize_text(value).lower()
    matched: List[str] = []
    for marker in markers:
        if re.search(rf"\b{re.escape(marker)}\b", normalized):
            matched.append(marker)
    return matched


def _merge_temporal_granularity(start_granularity: str, end_granularity: str) -> str:
    if start_granularity == end_granularity:
        return start_granularity
    if not start_granularity:
        return end_granularity or "unknown"
    if not end_granularity:
        return start_granularity or "unknown"
    return "mixed"


def _split_temporal_range(value: str) -> tuple[str, str] | None:
    normalized = _normalize_text(value)
    if not normalized:
        return None

    from_match = re.search(r"\bfrom\s+(.+?)\s+(?:to|through|until)\s+(.+)$", normalized, flags=re.IGNORECASE)
    if from_match:
        return from_match.group(1), from_match.group(2)

    plain_match = re.search(r"(.+?)\s+(?:to|through|until|-)\s+(.+)", normalized, flags=re.IGNORECASE)
    if plain_match:
        return plain_match.group(1), plain_match.group(2)
    return None


def _parse_single_temporal_expression(value: str) -> Dict[str, Any]:
    normalized = _normalize_text(value)
    if not normalized:
        return {
            "start_date": None,
            "end_date": None,
            "granularity": "unknown",
            "matched_text": "",
        }

    month_names = "|".join(_MONTH_NAME_TO_NUMBER)

    iso_match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", normalized)
    if iso_match:
        year, month, day = (int(item) for item in iso_match.groups())
        iso_date = _normalize_date_iso(year, month, day)
        return {
            "start_date": iso_date,
            "end_date": iso_date,
            "granularity": "day",
            "matched_text": iso_match.group(0),
        }

    month_day_year_match = re.search(
        rf"\b({month_names})\s+(\d{{1,2}}),\s*(\d{{4}})\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if month_day_year_match:
        month_name, day_text, year_text = month_day_year_match.groups()
        month = _MONTH_NAME_TO_NUMBER[month_name.lower()]
        day = int(day_text)
        year = int(year_text)
        iso_date = _normalize_date_iso(year, month, day)
        return {
            "start_date": iso_date,
            "end_date": iso_date,
            "granularity": "day",
            "matched_text": month_day_year_match.group(0),
        }

    numeric_date_match = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", normalized)
    if numeric_date_match:
        month_text, day_text, year_text = numeric_date_match.groups()
        month = int(month_text)
        day = int(day_text)
        year = _coerce_two_digit_year(int(year_text))
        iso_date = _normalize_date_iso(year, month, day)
        return {
            "start_date": iso_date,
            "end_date": iso_date,
            "granularity": "day",
            "matched_text": numeric_date_match.group(0),
        }

    month_year_match = re.search(
        rf"\b({month_names})\s+(\d{{4}})\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if month_year_match:
        month_name, year_text = month_year_match.groups()
        month = _MONTH_NAME_TO_NUMBER[month_name.lower()]
        year = int(year_text)
        start_date, end_date = _month_bounds(year, month)
        return {
            "start_date": start_date,
            "end_date": end_date,
            "granularity": "month",
            "matched_text": month_year_match.group(0),
        }

    year_match = re.search(r"\b(19\d{2}|20\d{2}|21\d{2})\b", normalized)
    if year_match:
        year = int(year_match.group(1))
        start_date, end_date = _year_bounds(year)
        return {
            "start_date": start_date,
            "end_date": end_date,
            "granularity": "year",
            "matched_text": year_match.group(0),
        }

    return {
        "start_date": None,
        "end_date": None,
        "granularity": "unknown",
        "matched_text": "",
    }


def _build_temporal_context(raw_value: Any, *, fallback_text: str = "") -> Dict[str, Any]:
    raw_text = _normalize_text(raw_value or fallback_text)
    if not raw_text:
        return {
            "raw_text": "",
            "start_date": None,
            "end_date": None,
            "granularity": "unknown",
            "is_approximate": False,
            "is_range": False,
            "relative_markers": [],
            "sortable_date": None,
            "matched_text": "",
        }

    approximate_markers = _extract_temporal_markers(raw_text, _APPROXIMATE_TEMPORAL_MARKERS)
    relative_markers = _extract_temporal_markers(raw_text, _RELATIVE_TEMPORAL_MARKERS)
    range_parts = _split_temporal_range(raw_text)

    if range_parts is not None:
        start_expression, end_expression = range_parts
        start_info = _parse_single_temporal_expression(start_expression)
        end_info = _parse_single_temporal_expression(end_expression)
        if start_info.get("start_date") or end_info.get("end_date"):
            return {
                "raw_text": raw_text,
                "start_date": start_info.get("start_date"),
                "end_date": end_info.get("end_date") or start_info.get("end_date"),
                "granularity": _merge_temporal_granularity(
                    str(start_info.get("granularity") or "unknown"),
                    str(end_info.get("granularity") or "unknown"),
                ),
                "is_approximate": bool(approximate_markers),
                "is_range": True,
                "relative_markers": relative_markers,
                "sortable_date": start_info.get("start_date") or end_info.get("start_date"),
                "matched_text": raw_text,
            }

    parsed = _parse_single_temporal_expression(raw_text)
    return {
        "raw_text": raw_text,
        "start_date": parsed.get("start_date"),
        "end_date": parsed.get("end_date"),
        "granularity": parsed.get("granularity") or "unknown",
        "is_approximate": bool(approximate_markers),
        "is_range": False,
        "relative_markers": relative_markers,
        "sortable_date": parsed.get("start_date"),
        "matched_text": parsed.get("matched_text") or "",
    }


def _normalize_canonical_fact_record(record: Any) -> Dict[str, Any]:
    fact = _coerce_dict(record)
    normalized_text = _normalize_text(fact.get("text") or "")
    fact_type = _normalize_text(fact.get("fact_type") or "general").lower() or "general"
    raw_event_date_or_range = _normalize_text(
        fact.get("event_date_or_range")
        or _coerce_dict(fact.get("temporal_context")).get("raw_text")
        or ""
    ) or None
    temporal_context = _build_temporal_context(
        raw_event_date_or_range,
        fallback_text=normalized_text if fact_type == "timeline" else "",
    )
    source_artifact_ids = _unique_normalized_strings(
        list(fact.get("source_artifact_ids") or [])
        + ([fact.get("source_artifact_id")] if str(fact.get("source_artifact_id") or "").strip() else [])
    )
    testimony_record_ids = _unique_normalized_strings(
        list(fact.get("testimony_record_ids") or [])
        + ([fact.get("testimony_record_id")] if str(fact.get("testimony_record_id") or "").strip() else [])
    )
    return {
        **fact,
        "text": normalized_text,
        "fact_type": fact_type,
        "event_date_or_range": raw_event_date_or_range,
        "actor_ids": list(fact.get("actor_ids") or []),
        "target_ids": list(fact.get("target_ids") or []),
        "claim_types": list(fact.get("claim_types") or []),
        "element_tags": list(fact.get("element_tags") or []),
        "location": _normalize_text(fact.get("location") or "") or None,
        "fact_participants": _coerce_dict(fact.get("fact_participants")),
        "event_label": _normalize_text(fact.get("event_label") or normalized_text) or None,
        "predicate_family": _normalize_text(fact.get("predicate_family") or fact_type).lower() or fact_type,
        "source_artifact_ids": source_artifact_ids,
        "testimony_record_ids": testimony_record_ids,
        "source_span_refs": _coerce_provenance_refs(fact.get("source_span_refs")),
        "confidence": fact.get("confidence"),
        "validation_status": _normalize_text(
            fact.get("validation_status") or fact.get("status") or "accepted"
        ).lower() or "accepted",
        "temporal_context": temporal_context,
    }


def _normalize_proof_lead_record(record: Any) -> Dict[str, Any]:
    lead = _coerce_dict(record)
    raw_temporal_scope = _normalize_text(
        lead.get("temporal_scope")
        or _coerce_dict(lead.get("temporal_context")).get("raw_text")
        or ""
    ) or None
    return {
        **lead,
        "lead_type": _normalize_text(lead.get("lead_type") or "evidence").lower() or "evidence",
        "description": _normalize_text(lead.get("description") or ""),
        "related_fact_ids": list(lead.get("related_fact_ids") or []),
        "fact_targets": list(lead.get("fact_targets") or []),
        "element_targets": list(lead.get("element_targets") or []),
        "timeline_anchor_ids": list(lead.get("timeline_anchor_ids") or []),
        "source_artifact_ids": _unique_normalized_strings(
            list(lead.get("source_artifact_ids") or [])
            + ([lead.get("source_artifact_id")] if str(lead.get("source_artifact_id") or "").strip() else [])
        ),
        "testimony_record_ids": _unique_normalized_strings(
            list(lead.get("testimony_record_ids") or [])
            + ([lead.get("testimony_record_id")] if str(lead.get("testimony_record_id") or "").strip() else [])
        ),
        "source_span_refs": _coerce_provenance_refs(lead.get("source_span_refs")),
        "temporal_scope": raw_temporal_scope,
        "temporal_context": _build_temporal_context(raw_temporal_scope),
    }


def _link_proof_leads_to_timeline_anchors(
    proof_leads: List[Dict[str, Any]],
    timeline_anchors: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    anchor_ids_by_fact_id: Dict[str, List[str]] = {}
    for anchor in timeline_anchors if isinstance(timeline_anchors, list) else []:
        if not isinstance(anchor, dict):
            continue
        fact_id = _normalize_text(anchor.get("fact_id") or "")
        anchor_id = _normalize_text(anchor.get("anchor_id") or "")
        if not fact_id or not anchor_id:
            continue
        anchor_ids_by_fact_id.setdefault(fact_id, []).append(anchor_id)

    linked_leads: List[Dict[str, Any]] = []
    for record in proof_leads if isinstance(proof_leads, list) else []:
        lead = _normalize_proof_lead_record(record)
        timeline_anchor_ids = list(lead.get("timeline_anchor_ids") or [])
        for fact_id in lead.get("related_fact_ids") or []:
            timeline_anchor_ids.extend(anchor_ids_by_fact_id.get(_normalize_text(fact_id), []))
        lead["timeline_anchor_ids"] = list(dict.fromkeys(item for item in timeline_anchor_ids if item))
        linked_leads.append(lead)
    return linked_leads


def _timeline_capable_facts(canonical_facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    timeline_facts: List[Dict[str, Any]] = []
    for record in canonical_facts if isinstance(canonical_facts, list) else []:
        fact = _normalize_canonical_fact_record(record)
        temporal_context = _coerce_dict(fact.get("temporal_context"))
        if (
            fact.get("fact_type") == "timeline"
            or temporal_context.get("start_date")
            or temporal_context.get("relative_markers")
        ):
            timeline_facts.append(fact)
    return timeline_facts


def _temporal_relation_between(left_fact: Dict[str, Any], right_fact: Dict[str, Any]) -> Dict[str, Any] | None:
    left_context = _coerce_dict(left_fact.get("temporal_context"))
    right_context = _coerce_dict(right_fact.get("temporal_context"))
    left_start = str(left_context.get("start_date") or "")
    left_end = str(left_context.get("end_date") or left_start)
    right_start = str(right_context.get("start_date") or "")
    right_end = str(right_context.get("end_date") or right_start)
    if not left_start or not right_start:
        return None

    left_fact_id = _normalize_text(left_fact.get("fact_id") or "")
    right_fact_id = _normalize_text(right_fact.get("fact_id") or "")
    confidence = "medium" if (
        bool(left_context.get("is_approximate"))
        or bool(right_context.get("is_approximate"))
        or left_context.get("granularity") != "day"
        or right_context.get("granularity") != "day"
    ) else "high"

    if left_end < right_start:
        source_fact, target_fact = left_fact, right_fact
        relation_type = "before"
    elif right_end < left_start:
        source_fact, target_fact = right_fact, left_fact
        relation_type = "before"
    elif left_start == right_start and left_end == right_end:
        if left_fact_id <= right_fact_id:
            source_fact, target_fact = left_fact, right_fact
        else:
            source_fact, target_fact = right_fact, left_fact
        relation_type = "same_time"
    else:
        if left_fact_id <= right_fact_id:
            source_fact, target_fact = left_fact, right_fact
        else:
            source_fact, target_fact = right_fact, left_fact
        relation_type = "overlaps"

    source_context = _coerce_dict(source_fact.get("temporal_context"))
    target_context = _coerce_dict(target_fact.get("temporal_context"))
    return {
        "relation_id": "",
        "source_fact_id": _normalize_text(source_fact.get("fact_id") or ""),
        "target_fact_id": _normalize_text(target_fact.get("fact_id") or ""),
        "relation_type": relation_type,
        "source_start_date": source_context.get("start_date"),
        "source_end_date": source_context.get("end_date"),
        "target_start_date": target_context.get("start_date"),
        "target_end_date": target_context.get("end_date"),
        "confidence": confidence,
    }


def build_timeline_relations(canonical_facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    relations: List[Dict[str, Any]] = []
    for left_fact, right_fact in combinations(_timeline_capable_facts(canonical_facts), 2):
        relation = _temporal_relation_between(left_fact, right_fact)
        if relation is None:
            continue
        relation["relation_id"] = f"timeline_relation_{len(relations) + 1:03d}"
        relations.append(relation)
    return relations


def build_temporal_fact_registry(
    canonical_facts: List[Dict[str, Any]],
    timeline_anchors: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    anchor_ids_by_fact_id: Dict[str, List[str]] = {}
    for anchor in timeline_anchors if isinstance(timeline_anchors, list) else []:
        if not isinstance(anchor, dict):
            continue
        fact_id = _normalize_text(anchor.get("fact_id") or "")
        anchor_id = _normalize_text(anchor.get("anchor_id") or "")
        if not fact_id or not anchor_id:
            continue
        anchor_ids_by_fact_id.setdefault(fact_id, []).append(anchor_id)

    registry: List[Dict[str, Any]] = []
    for index, fact in enumerate(_timeline_capable_facts(canonical_facts), start=1):
        fact_id = _normalize_text(fact.get("fact_id") or "") or f"temporal_fact_{index:03d}"
        temporal_context = _coerce_dict(fact.get("temporal_context"))
        if temporal_context.get("start_date"):
            temporal_status = "anchored"
        elif temporal_context.get("relative_markers"):
            temporal_status = "relative_only"
        else:
            temporal_status = "missing_anchor"

        registry.append(
            {
                **fact,
                "fact_id": fact_id,
                "temporal_fact_id": fact_id,
                "registry_version": "temporal_fact_registry.v1",
                "claim_types": _unique_normalized_strings(fact.get("claim_types") or []),
                "element_tags": _unique_normalized_strings(fact.get("element_tags") or []),
                "actor_ids": _unique_normalized_strings(fact.get("actor_ids") or []),
                "target_ids": _unique_normalized_strings(fact.get("target_ids") or []),
                "event_label": _normalize_text(fact.get("event_label") or fact.get("text") or fact_id) or fact_id,
                "predicate_family": _normalize_text(fact.get("predicate_family") or fact.get("fact_type") or "timeline").lower() or "timeline",
                "start_time": temporal_context.get("start_date"),
                "end_time": temporal_context.get("end_date"),
                "granularity": temporal_context.get("granularity") or "unknown",
                "is_approximate": bool(temporal_context.get("is_approximate", False)),
                "is_range": bool(temporal_context.get("is_range", False)),
                "relative_markers": _unique_normalized_strings(temporal_context.get("relative_markers") or []),
                "timeline_anchor_ids": list(anchor_ids_by_fact_id.get(fact_id, [])),
                "temporal_context": temporal_context,
                "temporal_status": temporal_status,
                "source_artifact_ids": _unique_normalized_strings(fact.get("source_artifact_ids") or []),
                "testimony_record_ids": _unique_normalized_strings(fact.get("testimony_record_ids") or []),
                "source_span_refs": _coerce_provenance_refs(fact.get("source_span_refs")),
                "confidence": fact.get("confidence"),
                "validation_status": _normalize_text(
                    fact.get("validation_status") or fact.get("status") or "accepted"
                ).lower() or "accepted",
                "source_kind": _normalize_text(fact.get("source_kind") or "") or None,
                "source_ref": _normalize_text(fact.get("source_ref") or "") or None,
            }
        )
    return registry


def build_temporal_relation_registry(
    canonical_facts: List[Dict[str, Any]],
    timeline_relations: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    fact_index = {
        _normalize_text(fact.get("fact_id") or ""): fact
        for fact in _timeline_capable_facts(canonical_facts)
        if _normalize_text(fact.get("fact_id") or "")
    }
    registry: List[Dict[str, Any]] = []
    for index, relation in enumerate(timeline_relations if isinstance(timeline_relations, list) else [], start=1):
        if not isinstance(relation, dict):
            continue
        relation_id = _normalize_text(relation.get("relation_id") or "") or f"timeline_relation_{index:03d}"
        source_fact_id = _normalize_text(relation.get("source_fact_id") or "")
        target_fact_id = _normalize_text(relation.get("target_fact_id") or "")
        source_fact = _coerce_dict(fact_index.get(source_fact_id))
        target_fact = _coerce_dict(fact_index.get(target_fact_id))
        claim_types = _unique_normalized_strings(
            list(source_fact.get("claim_types") or []) + list(target_fact.get("claim_types") or [])
        )
        element_tags = _unique_normalized_strings(
            list(source_fact.get("element_tags") or []) + list(target_fact.get("element_tags") or [])
        )
        source_artifact_ids = _unique_normalized_strings(
            list(source_fact.get("source_artifact_ids") or [])
            + list(target_fact.get("source_artifact_ids") or [])
        )
        testimony_record_ids = _unique_normalized_strings(
            list(source_fact.get("testimony_record_ids") or [])
            + list(target_fact.get("testimony_record_ids") or [])
        )
        registry.append(
            {
                **relation,
                "relation_id": relation_id,
                "registry_version": "temporal_relation_registry.v1",
                "source_fact_id": source_fact_id,
                "target_fact_id": target_fact_id,
                "source_temporal_fact_id": str(source_fact.get("temporal_fact_id") or source_fact_id or "") or None,
                "target_temporal_fact_id": str(target_fact.get("temporal_fact_id") or target_fact_id or "") or None,
                "claim_types": claim_types,
                "element_tags": element_tags,
                "source_fact_text": _normalize_text(source_fact.get("text") or "") or None,
                "target_fact_text": _normalize_text(target_fact.get("text") or "") or None,
                "source_artifact_ids": source_artifact_ids,
                "testimony_record_ids": testimony_record_ids,
                "source_span_refs": _coerce_provenance_refs(
                    list(source_fact.get("source_span_refs") or [])
                    + list(target_fact.get("source_span_refs") or [])
                ),
                "inference_mode": "derived_from_temporal_context",
                "inference_basis": "normalized_temporal_context",
                "explanation": (
                    f"{source_fact_id or 'unknown_fact'} {str(relation.get('relation_type') or 'related_to')} "
                    f"{target_fact_id or 'unknown_fact'} based on normalized temporal context."
                ),
            }
        )
    return registry


def build_temporal_issue_registry(
    canonical_facts: List[Dict[str, Any]],
    contradiction_queue: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    registry: List[Dict[str, Any]] = []
    seen_issue_ids = set()

    for fact in _timeline_capable_facts(canonical_facts):
        fact_id = _normalize_text(fact.get("fact_id") or "")
        temporal_context = _coerce_dict(fact.get("temporal_context"))
        if temporal_context.get("start_date"):
            continue

        relative_markers = _unique_normalized_strings(temporal_context.get("relative_markers") or [])
        issue_type = "relative_only_ordering" if relative_markers else "missing_anchor"
        issue_id = f"temporal_issue:{issue_type}:{fact_id or len(registry) + 1}"
        if issue_id in seen_issue_ids:
            continue
        seen_issue_ids.add(issue_id)

        summary = (
            f"Timeline fact {fact_id or 'unidentified_fact'} only has relative ordering and still needs anchoring."
            if relative_markers
            else f"Timeline fact {fact_id or 'unidentified_fact'} still lacks a normalized temporal anchor."
        )
        registry.append(
            {
                "issue_id": issue_id,
                "registry_version": "temporal_issue_registry.v1",
                "issue_type": issue_type,
                "category": issue_type,
                "summary": summary,
                "severity": "blocking",
                "blocking": True,
                "recommended_resolution_lane": "clarify_with_complainant",
                "fact_ids": [fact_id] if fact_id else [],
                "claim_types": _unique_normalized_strings(fact.get("claim_types") or []),
                "element_tags": _unique_normalized_strings(fact.get("element_tags") or []),
                "left_node_name": _normalize_text(fact.get("text") or "") or None,
                "right_node_name": None,
                "status": "open",
                "relative_markers": relative_markers,
                "source_kind": "temporal_fact_registry",
                "source_ref": fact_id or None,
                "inference_mode": "derived_from_temporal_context",
            }
        )

    for contradiction in contradiction_queue if isinstance(contradiction_queue, list) else []:
        candidate = _coerce_dict(contradiction)
        category = _normalize_text(candidate.get("category") or candidate.get("type") or "").lower()
        if not category.startswith("temporal"):
            continue
        issue_id = _normalize_text(candidate.get("contradiction_id") or candidate.get("dependency_id") or "")
        issue_id = issue_id or f"temporal_issue:{category}:{len(registry) + 1}"
        if issue_id in seen_issue_ids:
            continue
        seen_issue_ids.add(issue_id)
        registry.append(
            {
                "issue_id": issue_id,
                "registry_version": "temporal_issue_registry.v1",
                "issue_type": category,
                "category": category,
                "summary": _normalize_text(candidate.get("summary") or candidate.get("topic") or category),
                "severity": _normalize_text(candidate.get("severity") or "important").lower() or "important",
                "blocking": _normalize_text(candidate.get("severity") or "").lower() == "blocking",
                "recommended_resolution_lane": _normalize_text(
                    candidate.get("recommended_resolution_lane") or "clarify_with_complainant"
                ).lower() or "clarify_with_complainant",
                "fact_ids": _unique_normalized_strings(candidate.get("fact_ids") or []),
                "claim_types": _unique_normalized_strings(
                    candidate.get("affected_claim_types") or candidate.get("claim_types") or []
                ),
                "element_tags": _unique_normalized_strings(
                    candidate.get("affected_element_ids") or candidate.get("element_tags") or []
                ),
                "left_node_name": _normalize_text(candidate.get("left_node_name") or "") or None,
                "right_node_name": _normalize_text(candidate.get("right_node_name") or "") or None,
                "status": _normalize_text(candidate.get("current_resolution_status") or candidate.get("status") or "open").lower() or "open",
                "source_kind": "contradiction_queue",
                "source_ref": _normalize_text(candidate.get("contradiction_id") or candidate.get("dependency_id") or "") or None,
                "inference_mode": "imported_temporal_contradiction",
            }
        )

    return registry


def build_timeline_consistency_summary(
    canonical_facts: List[Dict[str, Any]],
    timeline_anchors: List[Dict[str, Any]],
    timeline_relations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    timeline_facts = _timeline_capable_facts(canonical_facts)
    relation_type_counts: Dict[str, int] = {}
    for relation in timeline_relations if isinstance(timeline_relations, list) else []:
        if not isinstance(relation, dict):
            continue
        relation_type = _normalize_text(relation.get("relation_type") or "")
        if relation_type:
            relation_type_counts[relation_type] = relation_type_counts.get(relation_type, 0) + 1

    missing_temporal_fact_ids: List[str] = []
    relative_only_fact_ids: List[str] = []
    approximate_fact_ids: List[str] = []
    range_fact_ids: List[str] = []
    ordered_fact_count = 0

    for fact in timeline_facts:
        fact_id = _normalize_text(fact.get("fact_id") or "")
        temporal_context = _coerce_dict(fact.get("temporal_context"))
        start_date = temporal_context.get("start_date")
        end_date = temporal_context.get("end_date")
        relative_markers = list(temporal_context.get("relative_markers") or [])
        if start_date:
            ordered_fact_count += 1
        else:
            missing_temporal_fact_ids.append(fact_id)
            if relative_markers:
                relative_only_fact_ids.append(fact_id)
        if bool(temporal_context.get("is_approximate", False)):
            approximate_fact_ids.append(fact_id)
        if bool(temporal_context.get("is_range", False)) or (start_date and end_date and start_date != end_date):
            range_fact_ids.append(fact_id)

    warnings: List[str] = []
    if missing_temporal_fact_ids:
        warnings.append("Some timeline facts still lack normalized dates or ranges.")
    if relative_only_fact_ids:
        warnings.append("Some timeline facts only express relative ordering and still need anchoring.")

    return {
        "event_count": len(timeline_facts),
        "anchor_count": len(timeline_anchors) if isinstance(timeline_anchors, list) else 0,
        "ordered_fact_count": ordered_fact_count,
        "unsequenced_fact_count": len(missing_temporal_fact_ids),
        "approximate_fact_count": len(approximate_fact_ids),
        "range_fact_count": len(range_fact_ids),
        "relation_count": len(timeline_relations) if isinstance(timeline_relations, list) else 0,
        "relation_type_counts": relation_type_counts,
        "missing_temporal_fact_ids": missing_temporal_fact_ids,
        "relative_only_fact_ids": relative_only_fact_ids,
        "warnings": warnings,
        "partial_order_ready": bool(timeline_facts) and not missing_temporal_fact_ids,
    }


def _contradiction_support_kind(resolution_lane: str) -> str:
    normalized = _normalize_text(resolution_lane).lower()
    if normalized == "capture_testimony":
        return "testimony"
    if normalized in {"request_document", "seek_external_record"}:
        return "evidence"
    if normalized == "manual_review":
        return "manual_review"
    return "intake_clarification"


def _derive_expected_format(lead_type: str) -> str:
    normalized = _normalize_text(lead_type).lower()
    if "email" in normalized:
        return "email"
    if "text" in normalized or "message" in normalized:
        return "message export"
    if "photo" in normalized or "image" in normalized or "picture" in normalized:
        return "image"
    if "witness" in normalized:
        return "testimony"
    if "letter" in normalized or "notice" in normalized:
        return "document"
    return "document or testimony"


def _derive_retrieval_path(lead_type: str) -> str:
    normalized = _normalize_text(lead_type).lower()
    if "email" in normalized:
        return "complainant_email_account"
    if "text" in normalized or "message" in normalized:
        return "complainant_mobile_device"
    if "witness" in normalized:
        return "witness_follow_up"
    if "photo" in normalized or "image" in normalized:
        return "complainant_device_gallery"
    return "complainant_possession"


def _derive_lead_priority(lead_type: str) -> str:
    normalized = _normalize_text(lead_type).lower()
    if any(token in normalized for token in ("termination", "notice", "email", "text", "message", "letter")):
        return "high"
    if "witness" in normalized:
        return "medium"
    return "medium"


def build_candidate_claims(knowledge_graph) -> List[Dict[str, Any]]:
    """Build initial candidate claim records from claim entities."""
    if knowledge_graph is None:
        return []

    candidates: List[Dict[str, Any]] = []
    for entity in knowledge_graph.get_entities_by_type("claim"):
        claim_type = normalize_claim_type(entity.attributes.get("claim_type") or "unknown")
        registry = registry_for_claim_type(claim_type)
        candidates.append(
            {
                "claim_id": entity.id,
                "claim_type": claim_type,
                "label": _normalize_text(entity.name or registry.get("label") or claim_type.replace("_", " ").title()),
                "description": _normalize_text(entity.attributes.get("description") or entity.name),
                "confidence": float(entity.confidence),
                "source": entity.source,
                "required_elements": [],
            }
        )
    return candidates


def build_canonical_facts(knowledge_graph) -> List[Dict[str, Any]]:
    """Build initial canonical facts from fact entities already extracted into the graph."""
    if knowledge_graph is None:
        return []

    canonical_facts: List[Dict[str, Any]] = []
    for entity in knowledge_graph.get_entities_by_type("fact"):
        fact_text = _normalize_text(entity.attributes.get("description") or entity.name)
        if not fact_text:
            continue
        canonical_facts.append(
            _normalize_canonical_fact_record(
                {
                    "fact_id": entity.id,
                    "text": fact_text,
                    "fact_type": _normalize_text(entity.attributes.get("fact_type") or "general").lower() or "general",
                    "claim_types": [],
                    "element_tags": [],
                    "event_date_or_range": _normalize_text(
                        entity.attributes.get("event_date_or_range")
                        or entity.attributes.get("event_date")
                        or entity.attributes.get("date")
                        or ""
                    ) or None,
                    "actor_ids": [],
                    "target_ids": [],
                    "location": _normalize_text(entity.attributes.get("location") or "") or None,
                    "source_kind": "knowledge_graph_entity",
                    "source_ref": entity.id,
                    "confidence": float(entity.confidence),
                    "status": "accepted",
                    "needs_corroboration": entity.confidence < 0.85,
                    "corroboration_priority": "high" if entity.confidence < 0.7 else "medium",
                    "materiality": "medium",
                    "fact_participants": {},
                    "contradiction_group_id": None,
                }
            )
        )
    return canonical_facts


def build_proof_leads(knowledge_graph) -> List[Dict[str, Any]]:
    """Build initial proof leads from evidence entities already extracted into the graph."""
    if knowledge_graph is None:
        return []

    proof_leads: List[Dict[str, Any]] = []
    for entity in knowledge_graph.get_entities_by_type("evidence"):
        description = _normalize_text(entity.attributes.get("description") or entity.name)
        evidence_type = _normalize_text(entity.attributes.get("evidence_type") or entity.name).lower() or "evidence"
        proof_leads.append(
            _normalize_proof_lead_record(
                {
                    "lead_id": entity.id,
                    "lead_type": evidence_type,
                    "description": description,
                    "related_fact_ids": [],
                    "fact_targets": [],
                    "element_targets": [],
                    "availability": "mentioned_in_initial_complaint",
                    "availability_details": "Referenced in initial complaint narrative",
                    "owner": "complainant",
                    "custodian": "complainant",
                    "expected_format": _derive_expected_format(evidence_type),
                    "retrieval_path": _derive_retrieval_path(evidence_type),
                    "authenticity_risk": "unknown",
                    "privacy_risk": "review_required",
                    "priority": _derive_lead_priority(evidence_type),
                    "recommended_support_kind": "testimony" if "witness" in evidence_type else "evidence",
                    "source_quality_target": "credible" if "witness" in evidence_type else "high_quality_document",
                    "acquisition_notes": "Needs complainant confirmation and collection path review",
                    "source_kind": "knowledge_graph_entity",
                    "source_ref": entity.id,
                    "temporal_scope": _normalize_text(
                        entity.attributes.get("temporal_scope")
                        or entity.attributes.get("event_date_or_range")
                        or entity.attributes.get("event_date")
                        or entity.attributes.get("date")
                        or ""
                    ) or None,
                }
            )
        )
    return proof_leads


def build_open_items(intake_case_file: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build the unresolved-work queue for the current intake record."""
    case_file = _coerce_dict(intake_case_file)
    sections = _coerce_dict(case_file.get("intake_sections"))
    candidate_claims = _coerce_list(case_file.get("candidate_claims"))
    contradiction_queue = _coerce_list(case_file.get("contradiction_queue"))
    open_items: List[Dict[str, Any]] = []

    for section_name, section in sections.items():
        section_dict = _coerce_dict(section)
        status = _normalize_text(section_dict.get("status")).lower() or "missing"
        if status == "complete":
            continue
        open_items.append(
            {
                "open_item_id": f"section:{section_name}",
                "kind": "section_gap",
                "status": "open",
                "blocking_level": "blocking" if section_name in {"chronology", "actors", "conduct", "claim_elements"} else "important",
                "section": section_name,
                "reason": "; ".join(_coerce_list(section_dict.get("missing_items"))) or f"{section_name} is incomplete",
                "target_claim_type": "",
                "target_element_id": "",
                "next_question_strategy": f"fill_{section_name}",
                "recommended_support_kind": "evidence" if section_name == "proof_leads" else "intake_clarification",
                "proof_path_status": "missing",
            }
        )

    for claim in candidate_claims:
        claim_dict = _coerce_dict(claim)
        claim_type = _normalize_text(claim_dict.get("claim_type"))
        claim_label = _normalize_text(claim_dict.get("label") or claim_type)
        for element in _coerce_list(claim_dict.get("required_elements")):
            element_dict = _coerce_dict(element)
            if _normalize_text(element_dict.get("status")).lower() == "present":
                continue
            element_id = _normalize_text(element_dict.get("element_id"))
            element_label = _normalize_text(element_dict.get("label") or element_id)
            open_items.append(
                {
                    "open_item_id": f"element:{claim_type}:{element_id}",
                    "kind": "claim_element_gap",
                    "status": "open",
                    "blocking_level": "blocking" if bool(element_dict.get("blocking", False)) else "important",
                    "section": "claim_elements",
                    "reason": f"{claim_label} is still missing {element_label}.",
                    "target_claim_type": claim_type,
                    "target_element_id": element_id,
                    "next_question_strategy": "satisfy_claim_element",
                    "evidence_classes": list(element_dict.get("evidence_classes", []) or []),
                    "recommended_support_kind": "testimony" if any("testimony" in str(item).lower() for item in (element_dict.get("evidence_classes", []) or [])) else "evidence",
                    "proof_path_status": "missing",
                }
            )

    for contradiction in contradiction_queue:
        contradiction_dict = _coerce_dict(contradiction)
        if _normalize_text(contradiction_dict.get("status") or "open").lower() == "resolved":
            continue
        contradiction_id = _normalize_text(contradiction_dict.get("contradiction_id") or "contradiction")
        topic = _normalize_text(contradiction_dict.get("topic") or "intake contradiction")
        resolution_lane = _normalize_text(
            contradiction_dict.get("recommended_resolution_lane") or "clarify_with_complainant"
        ).lower() or "clarify_with_complainant"
        external_corroboration_required = bool(
            contradiction_dict.get("external_corroboration_required", False)
        )
        open_items.append(
            {
                "open_item_id": f"contradiction:{contradiction_id}",
                "kind": "contradiction",
                "status": "open",
                "blocking_level": _normalize_text(contradiction_dict.get("severity") or "important").lower() or "important",
                "section": "contradictions",
                "reason": f"Resolve contradiction about {topic}.",
                "target_claim_type": "",
                "target_element_id": "",
                "next_question_strategy": resolution_lane,
                "recommended_support_kind": _contradiction_support_kind(resolution_lane),
                "recommended_resolution_lane": resolution_lane,
                "external_corroboration_required": external_corroboration_required,
                "proof_path_status": "conflicted_external_corroboration_required" if external_corroboration_required else "conflicted",
            }
        )

    seen_ids = set()
    deduped_items: List[Dict[str, Any]] = []
    for item in open_items:
        item_id = _normalize_text(item.get("open_item_id"))
        if not item_id or item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        deduped_items.append(item)
    return deduped_items


def build_summary_snapshot(intake_case_file: Dict[str, Any]) -> Dict[str, Any]:
    """Build a compact summary snapshot for the current intake record."""
    case_file = _coerce_dict(intake_case_file)
    candidate_claims = _coerce_list(case_file.get("candidate_claims"))
    canonical_facts = _coerce_list(case_file.get("canonical_facts"))
    proof_leads = _coerce_list(case_file.get("proof_leads"))
    timeline_anchors = _coerce_list(case_file.get("timeline_anchors"))
    open_items = _coerce_list(case_file.get("open_items"))
    contradiction_queue = _coerce_list(case_file.get("contradiction_queue"))
    harm_profile = _coerce_dict(case_file.get("harm_profile"))
    remedy_profile = _coerce_dict(case_file.get("remedy_profile"))
    sections = _coerce_dict(case_file.get("intake_sections"))
    unresolved_contradictions = [
        item for item in contradiction_queue
        if isinstance(item, dict) and _normalize_text(item.get("status") or "open").lower() != "resolved"
    ]
    return {
        "candidate_claim_count": len(candidate_claims),
        "canonical_fact_count": len(canonical_facts),
        "proof_lead_count": len(proof_leads),
        "timeline_anchor_count": len(timeline_anchors),
        "open_item_count": len(open_items),
        "unresolved_contradiction_count": len(unresolved_contradictions),
        "harm_category_count": len(_coerce_list(harm_profile.get("categories"))),
        "remedy_category_count": len(_coerce_list(remedy_profile.get("categories"))),
        "section_statuses": {
            name: _normalize_text(_coerce_dict(section).get("status") or "missing").lower() or "missing"
            for name, section in sections.items()
        },
    }


def refresh_summary_confirmation(intake_case_file: Dict[str, Any]) -> Dict[str, Any]:
    """Keep the complainant summary confirmation aligned with the latest snapshot."""
    case_file = _coerce_dict(intake_case_file)
    summary_snapshots = _coerce_list(case_file.get("summary_snapshots"))
    current_summary_snapshot = _coerce_dict(summary_snapshots[-1]) if summary_snapshots else {}
    existing = _coerce_confirmation_record(case_file.get("complainant_summary_confirmation"))
    confirmed_snapshot = existing.get("confirmed_summary_snapshot") or {}
    summary_confirmed = bool(existing.get("confirmed")) and bool(current_summary_snapshot) and confirmed_snapshot == current_summary_snapshot

    case_file["complainant_summary_confirmation"] = {
        "status": "confirmed" if summary_confirmed else ("pending" if current_summary_snapshot else "not_available"),
        "confirmed": summary_confirmed,
        "confirmed_at": existing.get("confirmed_at") if summary_confirmed else None,
        "confirmation_source": existing.get("confirmation_source") or "complainant",
        "confirmation_note": existing.get("confirmation_note") or "",
        "summary_snapshot_index": (len(summary_snapshots) - 1) if current_summary_snapshot else None,
        "current_summary_snapshot": current_summary_snapshot,
        "confirmed_summary_snapshot": confirmed_snapshot if summary_confirmed else {},
    }
    return case_file


def confirm_intake_summary(
    intake_case_file: Dict[str, Any],
    *,
    confirmation_source: str = "complainant",
    confirmation_note: str = "",
) -> Dict[str, Any]:
    """Mark the latest intake summary snapshot as confirmed by the complainant."""
    case_file = _coerce_dict(intake_case_file)
    snapshot = build_summary_snapshot(case_file)
    summary_snapshots = _coerce_list(case_file.get("summary_snapshots"))
    if not summary_snapshots:
        summary_snapshots = [snapshot]
    else:
        summary_snapshots[-1] = snapshot
    case_file["summary_snapshots"] = summary_snapshots
    case_file["complainant_summary_confirmation"] = {
        "status": "confirmed",
        "confirmed": True,
        "confirmed_at": datetime.now(UTC).isoformat(),
        "confirmation_source": _normalize_text(confirmation_source) or "complainant",
        "confirmation_note": _normalize_text(confirmation_note),
        "summary_snapshot_index": len(summary_snapshots) - 1,
        "current_summary_snapshot": snapshot,
        "confirmed_summary_snapshot": snapshot,
    }
    return case_file


def build_timeline_anchors(canonical_facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    anchors: List[Dict[str, Any]] = []
    seen_keys = set()
    for fact in canonical_facts if isinstance(canonical_facts, list) else []:
        normalized_fact = _normalize_canonical_fact_record(fact)
        fact_type = _normalize_text(normalized_fact.get("fact_type") or "").lower()
        event_date = _normalize_text(normalized_fact.get("event_date_or_range") or "")
        if fact_type != "timeline" and not event_date:
            continue
        anchor_text = event_date or _normalize_text(fact.get("text") or "")
        if not anchor_text:
            continue
        temporal_context = _coerce_dict(normalized_fact.get("temporal_context"))
        start_date = temporal_context.get("start_date")
        end_date = temporal_context.get("end_date")
        key = (
            str(start_date or ""),
            str(end_date or ""),
            anchor_text.lower(),
            _normalize_text(normalized_fact.get("location") or "").lower(),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        anchors.append(
            {
                "anchor_id": f"timeline_anchor_{len(anchors) + 1:03d}",
                "fact_id": _normalize_text(normalized_fact.get("fact_id") or ""),
                "anchor_text": anchor_text,
                "location": _normalize_text(normalized_fact.get("location") or "") or None,
                "fact_type": fact_type or "timeline",
                "start_date": start_date,
                "end_date": end_date,
                "granularity": temporal_context.get("granularity") or "unknown",
                "is_approximate": bool(temporal_context.get("is_approximate", False)),
                "relative_markers": list(temporal_context.get("relative_markers") or []),
                "sort_key": temporal_context.get("sortable_date") or anchor_text.lower(),
            }
        )
    anchors.sort(key=lambda anchor: (str(anchor.get("sort_key") or "9999-99-99"), str(anchor.get("anchor_id") or "")))
    return anchors


def _classify_harm_text(text: str) -> List[str]:
    normalized = _normalize_text(text).lower()
    categories: List[str] = []
    if any(token in normalized for token in ("wages", "salary", "pay", "income", "money", "rent", "cost")):
        categories.append("economic")
    if any(token in normalized for token in ("job", "career", "promotion", "termination", "fired", "discipline")):
        categories.append("professional")
    if any(token in normalized for token in ("stress", "anxiety", "humiliation", "emotional", "distress")):
        categories.append("emotional")
    if any(token in normalized for token in ("injury", "pain", "medical", "hospital", "physical")):
        categories.append("physical")
    if any(token in normalized for token in ("process", "hearing", "appeal", "complaint handling", "procedure")):
        categories.append("procedural")
    return categories or ["general"]


def build_harm_profile(canonical_facts: List[Dict[str, Any]]) -> Dict[str, Any]:
    impact_facts = [
        fact for fact in (canonical_facts if isinstance(canonical_facts, list) else [])
        if isinstance(fact, dict) and _normalize_text(fact.get("fact_type") or "").lower() == "impact"
    ]
    categories: List[str] = []
    for fact in impact_facts:
        for category in _classify_harm_text(_normalize_text(fact.get("text") or "")):
            if category not in categories:
                categories.append(category)
    return {
        "count": len(impact_facts),
        "categories": categories,
        "fact_ids": [
            _normalize_text(fact.get("fact_id") or "")
            for fact in impact_facts
            if _normalize_text(fact.get("fact_id") or "")
        ],
    }


def _classify_remedy_text(text: str) -> List[str]:
    normalized = _normalize_text(text).lower()
    categories: List[str] = []
    if any(token in normalized for token in ("damages", "compensation", "money", "lost wages", "refund")):
        categories.append("monetary")
    if any(token in normalized for token in ("reinstatement", "job back", "return to work")):
        categories.append("reinstatement")
    if any(token in normalized for token in ("injunction", "stop", "prevent", "order")):
        categories.append("injunctive")
    if any(token in normalized for token in ("correct", "records", "expunge", "remove discipline")):
        categories.append("records_correction")
    if any(token in normalized for token in ("declare", "declaratory", "finding")):
        categories.append("declaratory")
    return categories or ["general"]


def build_remedy_profile(canonical_facts: List[Dict[str, Any]]) -> Dict[str, Any]:
    remedy_facts = [
        fact for fact in (canonical_facts if isinstance(canonical_facts, list) else [])
        if isinstance(fact, dict) and _normalize_text(fact.get("fact_type") or "").lower() == "remedy"
    ]
    categories: List[str] = []
    for fact in remedy_facts:
        for category in _classify_remedy_text(_normalize_text(fact.get("text") or "")):
            if category not in categories:
                categories.append(category)
    return {
        "count": len(remedy_facts),
        "categories": categories,
        "fact_ids": [
            _normalize_text(fact.get("fact_id") or "")
            for fact in remedy_facts
            if _normalize_text(fact.get("fact_id") or "")
        ],
    }


def build_intake_sections(
    knowledge_graph,
    *,
    candidate_claims: List[Dict[str, Any]],
    canonical_facts: List[Dict[str, Any]],
    proof_leads: List[Dict[str, Any]],
    source_text: str = "",
) -> Dict[str, Dict[str, Any]]:
    """Build a lightweight first-pass section coverage snapshot."""
    has_dates = False
    has_people = False
    has_organizations = False
    if knowledge_graph is not None:
        has_dates = bool(knowledge_graph.get_entities_by_type("date"))
        has_people = bool(knowledge_graph.get_entities_by_type("person"))
        has_organizations = bool(knowledge_graph.get_entities_by_type("organization"))

    has_impact = any(fact.get("fact_type") == "impact" for fact in canonical_facts)
    has_remedy = any(fact.get("fact_type") == "remedy" for fact in canonical_facts)
    missing_claim_elements: List[str] = []
    claim_elements_present = False
    for claim in candidate_claims:
        if not isinstance(claim, dict):
            continue
        required_elements = refresh_required_elements(claim, canonical_facts, source_text)
        claim["required_elements"] = required_elements
        if required_elements:
            if any(str(element.get("status") or "").strip().lower() == "present" for element in required_elements):
                claim_elements_present = True
            for element in required_elements:
                if str(element.get("status") or "").strip().lower() != "present":
                    label = _normalize_text(element.get("label") or element.get("element_id"))
                    if label and label not in missing_claim_elements:
                        missing_claim_elements.append(label)

    return {
        "chronology": {
            "status": _status(has_dates),
            "missing_items": [] if has_dates else ["event dates or timeline anchors"],
        },
        "actors": {
            "status": _status(has_people or has_organizations),
            "missing_items": [] if (has_people or has_organizations) else ["people or organizations involved"],
        },
        "conduct": {
            "status": _status(bool(candidate_claims)),
            "missing_items": [] if candidate_claims else ["core alleged conduct"],
        },
        "harm": {
            "status": _status(has_impact),
            "missing_items": [] if has_impact else ["harm suffered"],
        },
        "remedy": {
            "status": _status(has_remedy),
            "missing_items": [] if has_remedy else ["requested outcome or remedy"],
        },
        "proof_leads": {
            "status": _status(bool(proof_leads)),
            "missing_items": [] if proof_leads else ["documents, witnesses, or other supporting proof leads"],
        },
        "claim_elements": {
            "status": "complete" if candidate_claims and not missing_claim_elements else ("partial" if claim_elements_present else "missing"),
            "missing_items": missing_claim_elements if missing_claim_elements else [],
        },
    }


def build_intake_case_file(knowledge_graph, complaint_text: str = "") -> Dict[str, Any]:
    """Build the initial structured intake case file from current graph state."""
    candidate_claims = build_candidate_claims(knowledge_graph)
    canonical_facts = build_canonical_facts(knowledge_graph)
    proof_leads = build_proof_leads(knowledge_graph)
    timeline_anchors = build_timeline_anchors(canonical_facts)
    timeline_relations = build_timeline_relations(canonical_facts)
    temporal_fact_registry = build_temporal_fact_registry(canonical_facts, timeline_anchors)
    temporal_relation_registry = build_temporal_relation_registry(canonical_facts, timeline_relations)
    temporal_issue_registry = build_temporal_issue_registry(canonical_facts, [])
    proof_leads = _link_proof_leads_to_timeline_anchors(proof_leads, timeline_anchors)
    intake_sections = build_intake_sections(
        knowledge_graph,
        candidate_claims=candidate_claims,
        canonical_facts=canonical_facts,
        proof_leads=proof_leads,
        source_text=complaint_text,
    )

    normalized_complaint_text = _normalize_text(complaint_text)
    intake_case_file = {
        "candidate_claims": candidate_claims,
        "intake_sections": intake_sections,
        "canonical_facts": canonical_facts,
        "timeline_anchors": timeline_anchors,
        "timeline_relations": timeline_relations,
        "temporal_fact_registry": temporal_fact_registry,
        "temporal_relation_registry": temporal_relation_registry,
        "temporal_issue_registry": temporal_issue_registry,
        "timeline_consistency_summary": build_timeline_consistency_summary(
            canonical_facts,
            timeline_anchors,
            timeline_relations,
        ),
        "harm_profile": build_harm_profile(canonical_facts),
        "remedy_profile": build_remedy_profile(canonical_facts),
        "proof_leads": proof_leads,
        "contradiction_queue": [],
        "open_items": [],
        "summary_snapshots": [],
        "complainant_summary_confirmation": {},
        "source_complaint_text": normalized_complaint_text,
    }
    intake_case_file["open_items"] = build_open_items(intake_case_file)
    intake_case_file["summary_snapshots"] = [build_summary_snapshot(intake_case_file)]
    return refresh_summary_confirmation(intake_case_file)


def refresh_intake_sections(intake_case_file: Dict[str, Any], knowledge_graph) -> Dict[str, Dict[str, Any]]:
    """Recompute section coverage from the latest structured intake state."""
    candidate_claims = intake_case_file.get("candidate_claims", [])
    canonical_facts = intake_case_file.get("canonical_facts", [])
    proof_leads = intake_case_file.get("proof_leads", [])
    source_text = intake_case_file.get("source_complaint_text", "")
    return build_intake_sections(
        knowledge_graph,
        candidate_claims=candidate_claims if isinstance(candidate_claims, list) else [],
        canonical_facts=canonical_facts if isinstance(canonical_facts, list) else [],
        proof_leads=proof_leads if isinstance(proof_leads, list) else [],
        source_text=str(source_text or ""),
    )


def refresh_intake_case_file(intake_case_file: Dict[str, Any], knowledge_graph, *, append_snapshot: bool = False) -> Dict[str, Any]:
    """Refresh derived intake sections, open items, and summary snapshots."""
    case_file = _coerce_dict(intake_case_file)
    case_file["canonical_facts"] = [
        _normalize_canonical_fact_record(record)
        for record in _coerce_list(case_file.get("canonical_facts"))
        if isinstance(record, dict)
    ]
    case_file["proof_leads"] = [
        _normalize_proof_lead_record(record)
        for record in _coerce_list(case_file.get("proof_leads"))
        if isinstance(record, dict)
    ]
    case_file["intake_sections"] = refresh_intake_sections(case_file, knowledge_graph)
    case_file["timeline_anchors"] = build_timeline_anchors(_coerce_list(case_file.get("canonical_facts")))
    case_file["timeline_relations"] = build_timeline_relations(_coerce_list(case_file.get("canonical_facts")))
    case_file["temporal_fact_registry"] = build_temporal_fact_registry(
        _coerce_list(case_file.get("canonical_facts")),
        _coerce_list(case_file.get("timeline_anchors")),
    )
    case_file["temporal_relation_registry"] = build_temporal_relation_registry(
        _coerce_list(case_file.get("canonical_facts")),
        _coerce_list(case_file.get("timeline_relations")),
    )
    case_file["temporal_issue_registry"] = build_temporal_issue_registry(
        _coerce_list(case_file.get("canonical_facts")),
        _coerce_list(case_file.get("contradiction_queue")),
    )
    case_file["proof_leads"] = _link_proof_leads_to_timeline_anchors(
        _coerce_list(case_file.get("proof_leads")),
        _coerce_list(case_file.get("timeline_anchors")),
    )
    case_file["timeline_consistency_summary"] = build_timeline_consistency_summary(
        _coerce_list(case_file.get("canonical_facts")),
        _coerce_list(case_file.get("timeline_anchors")),
        _coerce_list(case_file.get("timeline_relations")),
    )
    case_file["harm_profile"] = build_harm_profile(_coerce_list(case_file.get("canonical_facts")))
    case_file["remedy_profile"] = build_remedy_profile(_coerce_list(case_file.get("canonical_facts")))
    case_file["open_items"] = build_open_items(case_file)

    summary_snapshots = _coerce_list(case_file.get("summary_snapshots"))
    snapshot = build_summary_snapshot(case_file)
    if append_snapshot:
        if not summary_snapshots or summary_snapshots[-1] != snapshot:
            summary_snapshots.append(snapshot)
    elif not summary_snapshots:
        summary_snapshots.append(snapshot)
    else:
        summary_snapshots[-1] = snapshot
    case_file["summary_snapshots"] = summary_snapshots
    return refresh_summary_confirmation(case_file)
