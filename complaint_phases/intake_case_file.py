"""
Helpers for building and summarizing the structured intake case file.
"""

from __future__ import annotations

import calendar
from datetime import UTC, datetime, timedelta
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


def _derive_temporal_issue_missing_predicates(
    issue_type: Any,
    fact_ids: Any,
    relative_markers: Any = None,
) -> List[str]:
    normalized_issue_type = _normalize_text(issue_type).lower()
    normalized_fact_ids = _unique_normalized_strings(fact_ids or [])
    normalized_relative_markers = _unique_normalized_strings(relative_markers or [])

    if normalized_issue_type == "missing_anchor":
        return [f"Anchored({normalized_fact_ids[0]})"] if normalized_fact_ids else []
    if normalized_issue_type == "relative_only_ordering" and len(normalized_fact_ids) >= 2:
        return [f"Before({normalized_fact_ids[0]},{normalized_fact_ids[-1]})"]
    if normalized_issue_type == "relative_only_ordering" and normalized_relative_markers and normalized_fact_ids:
        return [f"Anchored({normalized_fact_ids[0]})"]
    if normalized_issue_type.startswith("temporal") and len(normalized_fact_ids) >= 2:
        return [f"Before({normalized_fact_ids[0]},{normalized_fact_ids[-1]})"]
    return []


def _derive_temporal_issue_required_provenance_kinds(
    issue_type: Any,
    recommended_resolution_lane: Any,
) -> List[str]:
    normalized_issue_type = _normalize_text(issue_type).lower()
    normalized_lane = _normalize_text(recommended_resolution_lane).lower()

    lane_map = {
        "clarify_with_complainant": "testimony_record",
        "capture_testimony": "testimony_record",
        "request_document": "document_artifact",
        "seek_external_record": "external_institutional_record",
        "manual_review": "manual_review",
    }
    required_kinds: List[str] = []
    mapped_lane = lane_map.get(normalized_lane)
    if mapped_lane:
        required_kinds.append(mapped_lane)
    if normalized_issue_type == "missing_anchor" and "document_artifact" not in required_kinds:
        required_kinds.append("document_artifact")
    if normalized_issue_type == "relative_only_ordering" and "testimony_record" not in required_kinds:
        required_kinds.append("testimony_record")
    return required_kinds


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


_BLOCKER_METADATA: Dict[str, Dict[str, Any]] = {
    "missing_written_notice_chain": {
        "primary_objective": "exact_dates",
        "blocker_objectives": ["exact_dates", "response_dates"],
        "extraction_targets": ["notice_chain", "response_timeline", "timeline_anchors"],
        "workflow_phases": ["graph_analysis", "intake_questioning", "document_generation"],
        "issue_family": "notice_chain",
    },
    "missing_hearing_request_timing": {
        "primary_objective": "hearing_request_timing",
        "blocker_objectives": ["hearing_request_timing", "exact_dates"],
        "extraction_targets": ["hearing_process", "timeline_anchors"],
        "workflow_phases": ["graph_analysis", "intake_questioning", "document_generation"],
        "issue_family": "hearing_process",
    },
    "missing_response_timing": {
        "primary_objective": "response_dates",
        "blocker_objectives": ["response_dates", "exact_dates"],
        "extraction_targets": ["response_timeline", "timeline_anchors"],
        "workflow_phases": ["graph_analysis", "intake_questioning", "document_generation"],
        "issue_family": "response_timeline",
    },
    "missing_staff_name_title_mapping": {
        "primary_objective": "staff_names_titles",
        "blocker_objectives": ["staff_names_titles"],
        "extraction_targets": ["actor_role_mapping"],
        "workflow_phases": ["graph_analysis", "intake_questioning", "document_generation"],
        "issue_family": "actor_identity",
    },
    "missing_retaliation_causation_sequence": {
        "primary_objective": "causation_sequence",
        "blocker_objectives": ["causation_sequence", "exact_dates", "staff_names_titles"],
        "extraction_targets": ["retaliation_sequence", "timeline_anchors", "actor_role_mapping"],
        "workflow_phases": ["graph_analysis", "intake_questioning", "document_generation"],
        "issue_family": "retaliation_sequence",
    },
}


def _unique_metadata_strings(values: Any) -> List[str]:
    if isinstance(values, list):
        return _unique_normalized_strings(values)
    return _unique_normalized_strings(list(values or []))


def _build_blocker_record(blocker_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    metadata = _coerce_dict(_BLOCKER_METADATA.get(blocker_id))
    return {
        **payload,
        "primary_objective": _normalize_text(
            payload.get("primary_objective") or metadata.get("primary_objective") or ""
        ),
        "blocker_objectives": _unique_metadata_strings(
            list(metadata.get("blocker_objectives") or []) + list(payload.get("blocker_objectives") or [])
        ),
        "extraction_targets": _unique_metadata_strings(
            list(metadata.get("extraction_targets") or []) + list(payload.get("extraction_targets") or [])
        ),
        "workflow_phases": _unique_metadata_strings(
            list(metadata.get("workflow_phases") or []) + list(payload.get("workflow_phases") or [])
        ),
        "issue_family": _normalize_text(payload.get("issue_family") or metadata.get("issue_family") or ""),
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

_QUANTIFIED_RELATIVE_TEMPORAL_PATTERNS = (
    r"\b\d+\s+(?:day|week|month|year)s?\s+(?:after|before|later|earlier)\b",
    r"\b(?:a|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:day|week|month|year)s?\s+(?:after|before|later|earlier)\b",
)

_NUMBER_WORDS = {
    "a": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


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
    for pattern in _QUANTIFIED_RELATIVE_TEMPORAL_PATTERNS:
        for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
            phrase = _normalize_text(match.group(0)).lower()
            if phrase and phrase not in matched:
                matched.append(phrase)
    for marker in markers:
        if re.search(rf"\b{re.escape(marker)}\b", normalized):
            if marker not in matched:
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


def _parse_relative_offset(relative_markers: List[str]) -> Dict[str, Any] | None:
    for marker in relative_markers if isinstance(relative_markers, list) else []:
        normalized_marker = _normalize_text(marker).lower()
        if not normalized_marker:
            continue
        if normalized_marker == "same day":
            return {"quantity": 0, "unit": "day", "direction": "after", "marker": normalized_marker}
        if normalized_marker == "next day":
            return {"quantity": 1, "unit": "day", "direction": "after", "marker": normalized_marker}
        if normalized_marker == "previous day":
            return {"quantity": 1, "unit": "day", "direction": "before", "marker": normalized_marker}
        match = re.search(
            r"\b(?P<quantity>\d+|a|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
            r"(?P<unit>day|week|month|year)s?\s+(?P<direction>after|before|later|earlier)\b",
            normalized_marker,
            flags=re.IGNORECASE,
        )
        if not match:
            continue
        quantity_token = match.group("quantity").lower()
        quantity = int(quantity_token) if quantity_token.isdigit() else _NUMBER_WORDS.get(quantity_token)
        if quantity is None:
            continue
        direction = match.group("direction").lower()
        if direction == "later":
            direction = "after"
        elif direction == "earlier":
            direction = "before"
        return {
            "quantity": quantity,
            "unit": match.group("unit").lower(),
            "direction": direction,
            "marker": normalized_marker,
        }
    return None


def _relative_reference_families(fact: Dict[str, Any]) -> List[str]:
    text_value = _normalize_text(fact.get("text") or "").lower()
    families: List[str] = []

    if any(token in text_value for token in ("complained", "complaint", "reported", "grievance", "hr", "human resources", "requested accommodation", "whistlebl")):
        families.append("protected_activity")
    if any(token in text_value for token in ("hearing", "appeal", "review", "grievance")):
        families.append("hearing_process")
    if any(token in text_value for token in ("notice", "letter", "email", "text", "message", "voicemail")):
        families.append("notice_chain")
    if any(token in text_value for token in ("response", "responded", "replied", "decision", "denied", "approved", "upheld", "rejected")):
        families.append("response_timeline")

    return _unique_normalized_strings(families)


def _derive_relative_temporal_context_from_anchor(
    fact: Dict[str, Any],
    anchor_fact: Dict[str, Any],
    relative_offset: Dict[str, Any],
) -> Dict[str, Any] | None:
    anchor_context = _coerce_dict(anchor_fact.get("temporal_context"))
    anchor_start = _normalize_text(anchor_context.get("start_date") or "")
    if not anchor_start or (anchor_context.get("granularity") or "") != "day":
        return None

    unit = _normalize_text(relative_offset.get("unit") or "").lower()
    quantity = int(relative_offset.get("quantity") or 0)
    direction = _normalize_text(relative_offset.get("direction") or "").lower()
    if unit not in {"day", "week"} or direction not in {"after", "before"}:
        return None

    anchor_date = datetime.strptime(anchor_start, "%Y-%m-%d").date()
    delta_days = quantity if unit == "day" else quantity * 7
    if direction == "before":
        delta_days *= -1
    derived_date = anchor_date + timedelta(days=delta_days)
    derived_iso = derived_date.isoformat()

    original_context = _coerce_dict(fact.get("temporal_context"))
    return {
        **original_context,
        "raw_text": _normalize_text(original_context.get("raw_text") or fact.get("event_date_or_range") or fact.get("text") or ""),
        "start_date": derived_iso,
        "end_date": derived_iso,
        "granularity": "day",
        "is_approximate": bool(original_context.get("is_approximate", False)),
        "is_range": False,
        "relative_markers": _unique_normalized_strings(original_context.get("relative_markers") or []),
        "sortable_date": derived_iso,
        "matched_text": _normalize_text(original_context.get("matched_text") or relative_offset.get("marker") or ""),
        "derived_from_relative_anchor": True,
        "anchor_fact_id": _normalize_text(anchor_fact.get("fact_id") or "") or None,
        "anchor_predicate_family": _normalize_text(anchor_fact.get("predicate_family") or "").lower() or None,
        "derivation_mode": "relative_anchor_offset",
    }


def _enrich_canonical_facts_with_relative_anchor_dates(canonical_facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized_facts = [
        _normalize_canonical_fact_record(record)
        for record in canonical_facts if isinstance(record, dict)
    ]
    anchored_by_family: Dict[str, List[Dict[str, Any]]] = {}
    for fact in normalized_facts:
        predicate_family = _normalize_text(fact.get("predicate_family") or "").lower()
        start_date = _coerce_dict(fact.get("temporal_context")).get("start_date")
        if predicate_family and start_date:
            anchored_by_family.setdefault(predicate_family, []).append(fact)

    enriched_facts: List[Dict[str, Any]] = []
    for fact in normalized_facts:
        temporal_context = _coerce_dict(fact.get("temporal_context"))
        if temporal_context.get("start_date") or not temporal_context.get("relative_markers"):
            enriched_facts.append(fact)
            continue

        relative_offset = _parse_relative_offset(list(temporal_context.get("relative_markers") or []))
        reference_families = _relative_reference_families(fact)
        predicate_family = _normalize_text(fact.get("predicate_family") or "").lower()
        if not relative_offset or not reference_families:
            enriched_facts.append(fact)
            continue

        candidate_anchors: List[Dict[str, Any]] = []
        for family in reference_families:
            if family == predicate_family:
                continue
            candidate_anchors.extend(anchored_by_family.get(family, []))

        if not candidate_anchors:
            enriched_facts.append(fact)
            continue

        candidate_anchors = sorted(
            candidate_anchors,
            key=lambda anchor: _normalize_text(_coerce_dict(anchor.get("temporal_context")).get("start_date") or ""),
        )
        anchor_fact = candidate_anchors[-1] if relative_offset.get("direction") == "after" else candidate_anchors[0]
        derived_context = _derive_relative_temporal_context_from_anchor(fact, anchor_fact, relative_offset)
        if not derived_context:
            enriched_facts.append(fact)
            continue

        enriched_facts.append({
            **fact,
            "temporal_context": derived_context,
        })

    anchored_protected_activity_exists = any(
        _normalize_text(fact.get("predicate_family") or "").lower() == "protected_activity"
        and bool(_coerce_dict(fact.get("temporal_context")).get("start_date"))
        for fact in enriched_facts
    )
    if not anchored_protected_activity_exists:
        return enriched_facts

    collapsed_facts: List[Dict[str, Any]] = []
    for fact in enriched_facts:
        predicate_family = _normalize_text(fact.get("predicate_family") or "").lower()
        temporal_context = _coerce_dict(fact.get("temporal_context"))
        text_value = _normalize_text(fact.get("text") or "")
        if (
            predicate_family == "protected_activity"
            and not temporal_context.get("start_date")
            and temporal_context.get("relative_markers")
            and any(
                _normalize_text(other.get("text") or "") == text_value
                and _normalize_text(other.get("predicate_family") or "").lower() in {"adverse_action", "causation"}
                and bool(_coerce_dict(other.get("temporal_context")).get("start_date"))
                for other in enriched_facts
                if other is not fact
            )
        ):
            continue
        collapsed_facts.append(fact)

    return collapsed_facts


def _normalize_canonical_fact_record(record: Any) -> Dict[str, Any]:
    fact = _coerce_dict(record)
    normalized_text = _normalize_text(fact.get("text") or "")
    fact_type = _normalize_text(fact.get("fact_type") or "general").lower() or "general"
    existing_temporal_context = _coerce_dict(fact.get("temporal_context"))
    reusable_temporal_raw_text = ""
    if (
        existing_temporal_context.get("start_date")
        or existing_temporal_context.get("end_date")
        or existing_temporal_context.get("relative_markers")
        or existing_temporal_context.get("matched_text")
    ):
        reusable_temporal_raw_text = _normalize_text(existing_temporal_context.get("raw_text") or "")
    raw_event_date_or_range = _normalize_text(
        fact.get("event_date_or_range")
        or reusable_temporal_raw_text
        or ""
    ) or None
    temporal_context = _build_temporal_context(
        raw_event_date_or_range,
        fallback_text=(
            normalized_text
            if fact_type == "timeline" and not _normalize_text(fact.get("structured_timeline_group") or "")
            else ""
        ),
    )
    if (
        not temporal_context.get("start_date")
        and existing_temporal_context.get("start_date")
        and _normalize_text(existing_temporal_context.get("raw_text") or raw_event_date_or_range or normalized_text)
    ):
        temporal_context = {
            **temporal_context,
            **existing_temporal_context,
            "raw_text": _normalize_text(existing_temporal_context.get("raw_text") or raw_event_date_or_range or normalized_text),
            "relative_markers": _unique_normalized_strings(existing_temporal_context.get("relative_markers") or []),
        }
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
        "event_id": _normalize_text(fact.get("event_id") or "") or None,
        "sequence_index": fact.get("sequence_index") if isinstance(fact.get("sequence_index"), int) else None,
        "structured_timeline_group": _normalize_text(fact.get("structured_timeline_group") or "") or None,
        "actor_ids": list(fact.get("actor_ids") or []),
        "target_ids": list(fact.get("target_ids") or []),
        "claim_types": list(fact.get("claim_types") or []),
        "element_tags": list(fact.get("element_tags") or []),
        "location": _normalize_text(fact.get("location") or "") or None,
        "fact_participants": _coerce_dict(fact.get("fact_participants")),
        "event_label": _normalize_text(fact.get("event_label") or normalized_text) or None,
        "predicate_family": _normalize_text(fact.get("predicate_family") or fact_type).lower() or fact_type,
        "timeline_anchor_ids": _unique_normalized_strings(fact.get("timeline_anchor_ids") or []),
        "event_support_refs": _unique_normalized_strings(fact.get("event_support_refs") or []),
        "source_artifact_ids": source_artifact_ids,
        "testimony_record_ids": testimony_record_ids,
        "source_span_refs": _coerce_provenance_refs(fact.get("source_span_refs")),
        "confidence": fact.get("confidence"),
        "validation_status": _normalize_text(
            fact.get("validation_status") or fact.get("status") or "accepted"
        ).lower() or "accepted",
        "source_kind": _normalize_text(fact.get("source_kind") or "") or None,
        "source_ref": _normalize_text(fact.get("source_ref") or "") or None,
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


def _is_actionable_undated_timeline_fact(fact: Dict[str, Any]) -> bool:
    text_value = _normalize_text(fact.get("text") or "")
    lowered = text_value.lower()
    predicate_family = _normalize_text(fact.get("predicate_family") or "").lower()
    if not text_value:
        return False
    meta_prefixes = (
        "my understanding",
        "from what i understand",
        "i understand",
        "i also understand",
        "i am asking for",
        "i want hacc to",
        "key facts that still need",
        "the exact dates of",
        "the names/titles of",
        "what written notice",
        "the specific adverse action",
        "the final remedy timeline",
    )
    if any(lowered.startswith(prefix) for prefix in meta_prefixes):
        return False
    if any(token in lowered for token in ("policy", "24 cfr", "must get notice", "should be given", "supposed to")):
        return False
    actionable_families = {
        "protected_activity",
        "adverse_action",
        "hearing_process",
        "notice_chain",
        "response_timeline",
        "decision_timeline",
        "causation",
    }
    if predicate_family in actionable_families:
        return True
    event_tokens = (
        "requested",
        "received",
        "responded",
        "replied",
        "denied",
        "terminated",
        "evicted",
        "complained",
        "reported",
        "appealed",
        "filed",
        "submitted",
        "told me",
        "sent me",
        "communicated",
    )
    return any(token in lowered for token in event_tokens)


def _timeline_capable_facts(canonical_facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    timeline_facts: List[Dict[str, Any]] = []
    for record in canonical_facts if isinstance(canonical_facts, list) else []:
        fact = _normalize_canonical_fact_record(record)
        temporal_context = _coerce_dict(fact.get("temporal_context"))
        if (
            (
                fact.get("fact_type") == "timeline"
                and (
                    temporal_context.get("start_date")
                    or temporal_context.get("relative_markers")
                    or _is_actionable_undated_timeline_fact(fact)
                )
            )
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


def _sequence_relation_between(left_fact: Dict[str, Any], right_fact: Dict[str, Any]) -> Dict[str, Any] | None:
    left_group = _normalize_text(left_fact.get("structured_timeline_group") or "")
    right_group = _normalize_text(right_fact.get("structured_timeline_group") or "")
    left_sequence = left_fact.get("sequence_index")
    right_sequence = right_fact.get("sequence_index")
    if not left_group or left_group != right_group:
        return None
    if not isinstance(left_sequence, int) or not isinstance(right_sequence, int) or left_sequence == right_sequence:
        return None
    if left_sequence < right_sequence:
        source_fact, target_fact = left_fact, right_fact
    else:
        source_fact, target_fact = right_fact, left_fact
    source_context = _coerce_dict(source_fact.get("temporal_context"))
    target_context = _coerce_dict(target_fact.get("temporal_context"))
    return {
        "relation_id": "",
        "source_fact_id": _normalize_text(source_fact.get("fact_id") or ""),
        "target_fact_id": _normalize_text(target_fact.get("fact_id") or ""),
        "relation_type": "before",
        "source_start_date": source_context.get("start_date"),
        "source_end_date": source_context.get("end_date"),
        "target_start_date": target_context.get("start_date"),
        "target_end_date": target_context.get("end_date"),
        "confidence": "medium",
        "inference_mode": "derived_from_structured_sequence",
        "inference_basis": "structured_timeline_sequence",
    }


def build_timeline_relations(canonical_facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    relations: List[Dict[str, Any]] = []
    seen_relation_keys = set()
    for left_fact, right_fact in combinations(_timeline_capable_facts(canonical_facts), 2):
        relation = _temporal_relation_between(left_fact, right_fact) or _sequence_relation_between(left_fact, right_fact)
        if relation is None:
            continue
        relation_key = (
            _normalize_text(relation.get("source_fact_id") or ""),
            _normalize_text(relation.get("target_fact_id") or ""),
            _normalize_text(relation.get("relation_type") or ""),
            _normalize_text(relation.get("inference_basis") or "normalized_temporal_context"),
        )
        if relation_key in seen_relation_keys:
            continue
        seen_relation_keys.add(relation_key)
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
                "event_support_refs": _unique_normalized_strings(
                    list(fact.get("event_support_refs") or [])
                    + ([f"fact:{fact_id}"] if fact_id else [])
                ),
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


def build_event_ledger(temporal_fact_registry: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ledger: List[Dict[str, Any]] = []
    for index, record in enumerate(temporal_fact_registry if isinstance(temporal_fact_registry, list) else [], start=1):
        fact = _coerce_dict(record)
        event_id = _normalize_text(
            fact.get("event_id")
            or fact.get("temporal_fact_id")
            or fact.get("fact_id")
            or f"event_{index:03d}"
        )
        ledger.append(
            {
                **fact,
                "event_id": event_id,
                "temporal_fact_id": _normalize_text(fact.get("temporal_fact_id") or event_id) or event_id,
                "ledger_version": "event_ledger.v1",
            }
        )
    return ledger


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
                "inference_mode": _normalize_text(relation.get("inference_mode") or "derived_from_temporal_context"),
                "inference_basis": _normalize_text(relation.get("inference_basis") or "normalized_temporal_context"),
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
    issue_index_by_signature: Dict[tuple[str, str, tuple[str, ...]], int] = {}

    for fact in _timeline_capable_facts(canonical_facts):
        fact_id = _normalize_text(fact.get("fact_id") or "")
        temporal_context = _coerce_dict(fact.get("temporal_context"))
        if temporal_context.get("start_date"):
            continue

        relative_markers = _unique_normalized_strings(temporal_context.get("relative_markers") or [])
        issue_type = "relative_only_ordering" if relative_markers else "missing_anchor"
        left_node_name = _normalize_text(fact.get("text") or "") or None
        signature = (issue_type, (left_node_name or "").lower(), tuple(relative_markers))
        if signature in issue_index_by_signature:
            existing_issue = registry[issue_index_by_signature[signature]]
            existing_issue["fact_ids"] = _unique_normalized_strings(
                list(existing_issue.get("fact_ids") or []) + ([fact_id] if fact_id else [])
            )
            existing_issue["claim_types"] = _unique_normalized_strings(
                list(existing_issue.get("claim_types") or []) + list(fact.get("claim_types") or [])
            )
            existing_issue["element_tags"] = _unique_normalized_strings(
                list(existing_issue.get("element_tags") or []) + list(fact.get("element_tags") or [])
            )
            existing_issue["missing_temporal_predicates"] = _derive_temporal_issue_missing_predicates(
                existing_issue.get("issue_type"),
                existing_issue.get("fact_ids") or [],
                existing_issue.get("relative_markers") or [],
            )
            existing_issue["required_provenance_kinds"] = _derive_temporal_issue_required_provenance_kinds(
                existing_issue.get("issue_type"),
                existing_issue.get("recommended_resolution_lane"),
            )
            continue
        issue_id = f"temporal_issue:{issue_type}:{fact_id or len(registry) + 1}"
        if issue_id in seen_issue_ids:
            continue
        seen_issue_ids.add(issue_id)

        summary = (
            (
                f"Timeline fact {fact_id or 'unidentified_fact'} only has relative ordering "
                f"({next((marker for marker in relative_markers if 'day' in marker or 'week' in marker or 'month' in marker or 'year' in marker), relative_markers[0])}) and still needs anchoring."
            )
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
                "left_node_name": left_node_name,
                "right_node_name": None,
                "status": "open",
                "current_resolution_status": "open",
                "relative_markers": relative_markers,
                "missing_temporal_predicates": _derive_temporal_issue_missing_predicates(
                    issue_type,
                    [fact_id] if fact_id else [],
                    relative_markers,
                ),
                "required_provenance_kinds": _derive_temporal_issue_required_provenance_kinds(
                    issue_type,
                    "clarify_with_complainant",
                ),
                "source_kind": "temporal_fact_registry",
                "source_ref": fact_id or None,
                "inference_mode": "derived_from_temporal_context",
            }
        )
        issue_index_by_signature[signature] = len(registry) - 1

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
                "current_resolution_status": _normalize_text(candidate.get("current_resolution_status") or candidate.get("status") or "open").lower() or "open",
                "missing_temporal_predicates": _unique_normalized_strings(candidate.get("missing_temporal_predicates") or [])
                or _derive_temporal_issue_missing_predicates(category, candidate.get("fact_ids") or []),
                "required_provenance_kinds": _unique_normalized_strings(candidate.get("required_provenance_kinds") or [])
                or _derive_temporal_issue_required_provenance_kinds(
                    category,
                    candidate.get("recommended_resolution_lane") or "clarify_with_complainant",
                ),
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


def merge_preserved_temporal_issue_registry(
    current_registry: List[Dict[str, Any]],
    previous_registry: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Preserve resolved temporal issue entries as historical records across refreshes."""
    merged_registry = [
        _coerce_dict(issue)
        for issue in current_registry
        if isinstance(issue, dict)
    ]
    current_issue_ids = {
        _normalize_text(issue.get("issue_id") or "")
        for issue in merged_registry
        if _normalize_text(issue.get("issue_id") or "")
    }

    for issue in previous_registry if isinstance(previous_registry, list) else []:
        issue_dict = _coerce_dict(issue)
        issue_id = _normalize_text(issue_dict.get("issue_id") or "")
        issue_status = _normalize_text(
            issue_dict.get("current_resolution_status") or issue_dict.get("status") or ""
        ).lower()
        if not issue_id or issue_id in current_issue_ids or issue_status != "resolved":
            continue
        preserved_issue = dict(issue_dict)
        preserved_issue["status"] = "resolved"
        preserved_issue["current_resolution_status"] = "resolved"
        merged_registry.append(preserved_issue)
        current_issue_ids.add(issue_id)

    return merged_registry
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
                    "predicate_family": _normalize_text(
                        entity.attributes.get("predicate_family") or entity.attributes.get("fact_type") or ""
                    ).lower() or None,
                    "event_label": _normalize_text(entity.attributes.get("event_label") or "") or None,
                    "event_id": _normalize_text(entity.attributes.get("event_id") or "") or None,
                    "sequence_index": entity.attributes.get("sequence_index") if isinstance(entity.attributes.get("sequence_index"), int) else None,
                    "structured_timeline_group": _normalize_text(entity.attributes.get("structured_timeline_group") or "") or None,
                    "claim_types": [],
                    "element_tags": [],
                    "event_date_or_range": _normalize_text(
                        entity.attributes.get("event_date_or_range")
                        or entity.attributes.get("event_date")
                        or entity.attributes.get("date")
                        or ""
                    ) or None,
                    "actor_ids": list(entity.attributes.get("actor_ids") or []),
                    "target_ids": list(entity.attributes.get("target_ids") or []),
                    "location": _normalize_text(entity.attributes.get("location") or "") or None,
                    "source_kind": "knowledge_graph_entity",
                    "source_ref": entity.id,
                    "confidence": float(entity.confidence),
                    "status": "accepted",
                    "needs_corroboration": entity.confidence < 0.85,
                    "corroboration_priority": "high" if entity.confidence < 0.7 else "medium",
                    "materiality": "medium",
                    "fact_participants": _coerce_dict(entity.attributes.get("fact_participants")),
                    "event_support_refs": _unique_normalized_strings(entity.attributes.get("event_support_refs") or []),
                    "source_artifact_ids": _unique_normalized_strings(entity.attributes.get("source_artifact_ids") or []),
                    "testimony_record_ids": _unique_normalized_strings(entity.attributes.get("testimony_record_ids") or []),
                    "source_span_refs": _coerce_provenance_refs(entity.attributes.get("source_span_refs")),
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
    blocker_follow_up_summary = _coerce_dict(case_file.get("blocker_follow_up_summary"))
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

    for blocker in _coerce_list(blocker_follow_up_summary.get("blocking_items")):
        blocker_dict = _coerce_dict(blocker)
        blocker_id = _normalize_text(blocker_dict.get("blocker_id") or "")
        reason = _normalize_text(blocker_dict.get("reason") or "Critical intake blocker requires follow-up.")
        section = _normalize_text(blocker_dict.get("section") or "chronology").lower() or "chronology"
        question_strategy = _normalize_text(
            blocker_dict.get("next_question_strategy")
            or blocker_dict.get("question_strategy")
            or "targeted_blocker_follow_up"
        ).lower() or "targeted_blocker_follow_up"
        support_kind = _normalize_text(
            blocker_dict.get("recommended_support_kind")
            or ("evidence" if section in {"proof_leads", "chronology"} else "intake_clarification")
        ).lower() or "intake_clarification"
        open_items.append(
            {
                "open_item_id": f"blocker:{blocker_id or len(open_items) + 1}",
                "kind": "blocker_follow_up",
                "status": "open",
                "blocking_level": "blocking",
                "section": section,
                "reason": reason,
                "target_claim_type": _normalize_text(blocker_dict.get("target_claim_type") or ""),
                "target_element_id": _normalize_text(blocker_dict.get("target_element_id") or ""),
                "next_question_strategy": question_strategy,
                "recommended_support_kind": support_kind,
                "proof_path_status": _normalize_text(blocker_dict.get("proof_path_status") or "missing").lower() or "missing",
                "blocker_tags": _unique_normalized_strings(blocker_dict.get("blocker_tags") or []),
                "primary_objective": _normalize_text(blocker_dict.get("primary_objective") or ""),
                "blocker_objectives": _unique_normalized_strings(blocker_dict.get("blocker_objectives") or []),
                "extraction_targets": _unique_normalized_strings(blocker_dict.get("extraction_targets") or []),
                "workflow_phases": _unique_normalized_strings(blocker_dict.get("workflow_phases") or []),
                "issue_family": _normalize_text(blocker_dict.get("issue_family") or ""),
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
    blocker_follow_up_summary = _coerce_dict(case_file.get("blocker_follow_up_summary"))
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
        "blocker_count": len(_coerce_list(blocker_follow_up_summary.get("blocking_items"))),
        "unresolved_contradiction_count": len(unresolved_contradictions),
        "harm_category_count": len(_coerce_list(harm_profile.get("categories"))),
        "remedy_category_count": len(_coerce_list(remedy_profile.get("categories"))),
        "section_statuses": {
            name: _normalize_text(_coerce_dict(section).get("status") or "missing").lower() or "missing"
            for name, section in sections.items()
        },
    }


def build_blocker_follow_up_summary(
    *,
    candidate_claims: List[Dict[str, Any]],
    canonical_facts: List[Dict[str, Any]],
    proof_leads: List[Dict[str, Any]],
    source_text: str,
) -> Dict[str, Any]:
    """Build explicit follow-up blockers for intake questioning and document generation."""
    facts = [_normalize_canonical_fact_record(item) for item in canonical_facts if isinstance(item, dict)]
    leads = [_normalize_proof_lead_record(item) for item in proof_leads if isinstance(item, dict)]
    full_text = _normalize_text(source_text).lower()

    def _fact_text(fact: Dict[str, Any]) -> str:
        return _normalize_text(fact.get("text") or fact.get("event_label") or "").lower()

    def _has_day_level_date(value: str) -> bool:
        return bool(
            re.search(
                (
                    r"\b(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|"
                    r"sep|sept|september|oct|october|nov|november|dec|december)\s+\d{1,2},\s+\d{4}\b"
                    r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b"
                    r"|\b\d{4}-\d{2}-\d{2}\b"
                ),
                value or "",
                flags=re.IGNORECASE,
            )
        )

    blocking_items: List[Dict[str, Any]] = []
    seen_ids = set()

    def _add_blocker(blocker: Dict[str, Any]) -> None:
        blocker_id = _normalize_text(blocker.get("blocker_id") or "")
        if not blocker_id or blocker_id in seen_ids:
            return
        seen_ids.add(blocker_id)
        blocking_items.append(blocker)

    has_notice_reference = any(token in full_text for token in ("notice", "letter", "email", "message"))
    notice_lead_present = any(
        any(token in _normalize_text(lead.get("description") or "").lower() for token in ("notice", "letter", "email", "message"))
        for lead in leads
    )
    if has_notice_reference and not notice_lead_present:
        _add_blocker(
            _build_blocker_record("missing_written_notice_chain", {
                "blocker_id": "missing_written_notice_chain",
                "section": "proof_leads",
                "reason": "Written notice chain is referenced but the sending party/date/source artifact is still missing.",
                "next_question_strategy": "capture_notice_chain",
                "recommended_support_kind": "evidence",
                "proof_path_status": "missing",
                "blocker_tags": ["notice_chain", "exact_dates"],
            })
        )

    hearing_reference = any(token in full_text for token in ("hearing", "appeal", "grievance"))
    hearing_facts = [fact for fact in facts if any(token in _fact_text(fact) for token in ("hearing", "appeal", "grievance"))]
    hearing_has_date = any(
        _has_day_level_date(_normalize_text(fact.get("event_date_or_range") or ""))
        or bool(_coerce_dict(fact.get("temporal_context")).get("start_date"))
        for fact in hearing_facts
    )
    if hearing_reference and not hearing_has_date:
        _add_blocker(
            _build_blocker_record("missing_hearing_request_timing", {
                "blocker_id": "missing_hearing_request_timing",
                "section": "chronology",
                "reason": "Hearing/appeal request timing is missing day-level anchors.",
                "next_question_strategy": "capture_hearing_timeline",
                "recommended_support_kind": "intake_clarification",
                "proof_path_status": "missing",
                "blocker_tags": ["exact_dates", "hearing_timeline"],
            })
        )

    response_reference = any(token in full_text for token in ("response", "responded", "replied", "denied", "approved", "ignored", "no response"))
    response_facts = [fact for fact in facts if any(token in _fact_text(fact) for token in ("response", "responded", "replied", "denied", "approved", "ignored"))]
    response_has_date = any(
        _has_day_level_date(_normalize_text(fact.get("event_date_or_range") or ""))
        or bool(_coerce_dict(fact.get("temporal_context")).get("start_date"))
        for fact in response_facts
    )
    if response_reference and not response_has_date:
        _add_blocker(
            _build_blocker_record("missing_response_timing", {
                "blocker_id": "missing_response_timing",
                "section": "chronology",
                "reason": "Response or non-response events are described without date anchors.",
                "next_question_strategy": "capture_response_timeline",
                "recommended_support_kind": "intake_clarification",
                "proof_path_status": "missing",
                "blocker_tags": ["exact_dates", "response_timeline"],
            })
        )

    staff_name_pattern = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")
    has_named_staff = bool(staff_name_pattern.search(source_text or ""))
    has_staff_title = bool(
        re.search(r"\b(manager|supervisor|director|officer|specialist|landlord|owner|hr)\b", full_text)
    )
    if has_named_staff and not has_staff_title:
        _add_blocker(
            _build_blocker_record("missing_staff_name_title_mapping", {
                "blocker_id": "missing_staff_name_title_mapping",
                "section": "actors",
                "reason": "Named staff are present but title/role mapping is incomplete.",
                "next_question_strategy": "capture_staff_identity",
                "recommended_support_kind": "intake_clarification",
                "proof_path_status": "missing",
                "blocker_tags": ["staff_identity"],
            })
        )

    retaliation_claim = any(
        _normalize_text(_coerce_dict(claim).get("claim_type") or "").lower() == "retaliation"
        for claim in candidate_claims if isinstance(candidate_claims, list)
    )
    if retaliation_claim:
        protected_present = any(
            "protected activity" in _fact_text(fact)
            or "complain" in _fact_text(fact)
            or "reported" in _fact_text(fact)
            or _normalize_text(fact.get("predicate_family") or "").lower() == "protected_activity"
            for fact in facts
        ) or any(token in full_text for token in ("protected activity", "complained", "reported", "grievance"))
        adverse_present = any(
            any(token in _fact_text(fact) for token in ("fired", "terminated", "demoted", "disciplined", "evicted", "reduced hours", "cut hours"))
            or _normalize_text(fact.get("predicate_family") or "").lower() == "adverse_action"
            for fact in facts
        ) or any(token in full_text for token in ("fired", "terminated", "demoted", "disciplined", "evicted", "reduced hours", "cut hours"))
        causation_connector = any(
            any(token in _fact_text(fact) for token in ("because", "after", "soon after", "in response to", "due to"))
            or _normalize_text(fact.get("predicate_family") or "").lower() == "causation"
            for fact in facts
        ) or any(token in full_text for token in ("because", "after", "soon after", "in response to", "due to"))
        if not (protected_present and adverse_present and causation_connector):
            _add_blocker(
                _build_blocker_record("missing_retaliation_causation_sequence", {
                    "blocker_id": "missing_retaliation_causation_sequence",
                    "section": "conduct",
                    "reason": "Retaliation theory still lacks protected-activity to adverse-action sequencing and causation links.",
                    "next_question_strategy": "capture_retaliation_sequence",
                    "recommended_support_kind": "intake_clarification",
                    "proof_path_status": "missing",
                    "blocker_tags": ["retaliation_sequence", "exact_dates", "staff_identity"],
                })
            )

    summary_objectives = _unique_metadata_strings([
        objective
        for blocker in blocking_items
        for objective in _coerce_list(_coerce_dict(blocker).get("blocker_objectives"))
    ])
    summary_targets = _unique_metadata_strings([
        target
        for blocker in blocking_items
        for target in _coerce_list(_coerce_dict(blocker).get("extraction_targets"))
    ])
    summary_phases = _unique_metadata_strings([
        phase
        for blocker in blocking_items
        for phase in _coerce_list(_coerce_dict(blocker).get("workflow_phases"))
    ])
    return {
        "blocking_items": blocking_items,
        "blocking_item_count": len(blocking_items),
        "blocking_objectives": summary_objectives,
        "extraction_targets": summary_targets,
        "workflow_phases": summary_phases,
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
        temporal_context = _coerce_dict(normalized_fact.get("temporal_context"))
        if (
            fact_type == "timeline"
            and not event_date
            and not temporal_context.get("start_date")
            and not temporal_context.get("relative_markers")
            and not _is_actionable_undated_timeline_fact(normalized_fact)
        ):
            continue
        if fact_type != "timeline" and not event_date:
            continue
        anchor_text = event_date or _normalize_text(fact.get("text") or "")
        if not anchor_text:
            continue
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


def _has_actor_by_actor_timeline(canonical_facts: List[Dict[str, Any]]) -> bool:
    for fact_record in canonical_facts if isinstance(canonical_facts, list) else []:
        fact = _normalize_canonical_fact_record(fact_record)
        if _normalize_text(fact.get("fact_type") or "").lower() != "timeline":
            continue
        text_value = _normalize_text(fact.get("text") or "")
        predicate_family = _normalize_text(fact.get("predicate_family") or "").lower()
        has_actor = bool(_unique_normalized_strings(fact.get("actor_ids") or []))
        if not has_actor:
            has_actor = any(
                token in text_value.lower()
                for token in ("who", "manager", "supervisor", "hr", "landlord", "owner", "agency")
            )
        has_decision_signal = any(
            token in text_value.lower()
            for token in ("decision", "decided", "approved", "denied", "terminated", "disciplined", "evicted")
        ) or predicate_family in {"decision_timeline", "causation", "adverse_action", "protected_activity"}
        has_anchor = bool(_coerce_dict(fact.get("temporal_context")).get("start_date"))
        if has_actor and has_decision_signal and has_anchor:
            return True
    return False


def _has_retaliation_causation_link(
    candidate_claims: List[Dict[str, Any]],
    canonical_facts: List[Dict[str, Any]],
    source_text: str,
) -> bool:
    has_retaliation_claim = any(
        _normalize_text(_coerce_dict(claim).get("claim_type") or "").lower() == "retaliation"
        for claim in candidate_claims if isinstance(candidate_claims, list)
    )
    if not has_retaliation_claim:
        return True

    full_text = _normalize_text(source_text).lower()
    has_text_link = (
        any(token in full_text for token in ("protected activity", "complained", "reported", "grievance"))
        and any(token in full_text for token in ("fired", "terminated", "demoted", "disciplined", "evicted", "reduced hours", "cut hours"))
        and any(token in full_text for token in ("because", "after", "soon after", "in response to", "due to"))
    )
    if has_text_link:
        return True

    for fact_record in canonical_facts if isinstance(canonical_facts, list) else []:
        fact = _normalize_canonical_fact_record(fact_record)
        text_value = _normalize_text(fact.get("text") or "").lower()
        predicate_family = _normalize_text(fact.get("predicate_family") or "").lower()
        has_protected = (
            "protected activity" in text_value
            or "complained" in text_value
            or "reported" in text_value
            or predicate_family == "protected_activity"
        )
        has_adverse = (
            "fired" in text_value
            or "terminated" in text_value
            or "demoted" in text_value
            or "disciplined" in text_value
            or "evicted" in text_value
            or predicate_family == "adverse_action"
        )
        has_causal_connector = (
            "because" in text_value
            or "after" in text_value
            or "soon after" in text_value
            or "in response to" in text_value
            or "due to" in text_value
            or predicate_family == "causation"
        )
        if has_protected and has_adverse and has_causal_connector:
            return True
    return False


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
    has_actor_decision_timeline = _has_actor_by_actor_timeline(canonical_facts)
    has_retaliation_causation_link = _has_retaliation_causation_link(
        candidate_claims,
        canonical_facts,
        source_text,
    )
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

    chronology_missing_items: List[str] = []
    if not has_dates:
        chronology_missing_items.append("event dates or timeline anchors")
        if not has_actor_decision_timeline:
            chronology_missing_items.append("actor-by-actor decision timeline with date anchors")
    chronology_status = "complete" if has_dates else "missing"

    conduct_missing_items: List[str] = []
    if not candidate_claims:
        conduct_missing_items.append("core alleged conduct")
    if not has_retaliation_causation_link:
        conduct_missing_items.append(
            "causation facts linking protected activity to adverse treatment"
        )
    conduct_status = (
        "complete"
        if not conduct_missing_items
        else ("partial" if candidate_claims else "missing")
    )

    return {
        "chronology": {
            "status": chronology_status,
            "missing_items": chronology_missing_items,
        },
        "actors": {
            "status": _status(has_people or has_organizations),
            "missing_items": [] if (has_people or has_organizations) else ["people or organizations involved"],
        },
        "conduct": {
            "status": conduct_status,
            "missing_items": conduct_missing_items,
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
    canonical_facts = _enrich_canonical_facts_with_relative_anchor_dates(build_canonical_facts(knowledge_graph))
    proof_leads = build_proof_leads(knowledge_graph)
    timeline_anchors = build_timeline_anchors(canonical_facts)
    timeline_relations = build_timeline_relations(canonical_facts)
    temporal_fact_registry = build_temporal_fact_registry(canonical_facts, timeline_anchors)
    temporal_relation_registry = build_temporal_relation_registry(canonical_facts, timeline_relations)
    temporal_issue_registry = build_temporal_issue_registry(canonical_facts, [])
    event_ledger = build_event_ledger(temporal_fact_registry)
    proof_leads = _link_proof_leads_to_timeline_anchors(proof_leads, timeline_anchors)
    intake_sections = build_intake_sections(
        knowledge_graph,
        candidate_claims=candidate_claims,
        canonical_facts=canonical_facts,
        proof_leads=proof_leads,
        source_text=complaint_text,
    )
    blocker_follow_up_summary = build_blocker_follow_up_summary(
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
        "event_ledger": event_ledger,
        "timeline_consistency_summary": build_timeline_consistency_summary(
            canonical_facts,
            timeline_anchors,
            timeline_relations,
        ),
        "harm_profile": build_harm_profile(canonical_facts),
        "remedy_profile": build_remedy_profile(canonical_facts),
        "proof_leads": proof_leads,
        "blocker_follow_up_summary": blocker_follow_up_summary,
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
    previous_temporal_issue_registry = _coerce_list(case_file.get("temporal_issue_registry"))
    if knowledge_graph is not None:
        case_file["candidate_claims"] = build_candidate_claims(knowledge_graph)
        case_file["canonical_facts"] = _enrich_canonical_facts_with_relative_anchor_dates(
            build_canonical_facts(knowledge_graph)
        )
        case_file["proof_leads"] = build_proof_leads(knowledge_graph)
    else:
        case_file["canonical_facts"] = _enrich_canonical_facts_with_relative_anchor_dates([
            _normalize_canonical_fact_record(record)
            for record in _coerce_list(case_file.get("canonical_facts"))
            if isinstance(record, dict)
        ])
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
    case_file["event_ledger"] = build_event_ledger(
        _coerce_list(case_file.get("temporal_fact_registry"))
    )
    case_file["temporal_relation_registry"] = build_temporal_relation_registry(
        _coerce_list(case_file.get("canonical_facts")),
        _coerce_list(case_file.get("timeline_relations")),
    )
    case_file["temporal_issue_registry"] = merge_preserved_temporal_issue_registry(
        build_temporal_issue_registry(
            _coerce_list(case_file.get("canonical_facts")),
            _coerce_list(case_file.get("contradiction_queue")),
        ),
        previous_temporal_issue_registry,
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
    case_file["blocker_follow_up_summary"] = build_blocker_follow_up_summary(
        candidate_claims=_coerce_list(case_file.get("candidate_claims")),
        canonical_facts=_coerce_list(case_file.get("canonical_facts")),
        proof_leads=_coerce_list(case_file.get("proof_leads")),
        source_text=str(case_file.get("source_complaint_text") or ""),
    )
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
