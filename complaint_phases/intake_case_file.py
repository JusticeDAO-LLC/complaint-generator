"""
Helpers for building and summarizing the structured intake case file.
"""

from __future__ import annotations

import calendar
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from itertools import combinations
import re
from typing import Any, Dict, List, Mapping, Optional

from integrations.ipfs_datasets.types import user_assertion_from_mapping

from .intake_claim_registry import normalize_claim_type, refresh_required_elements, registry_for_claim_type


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _status(has_value: bool) -> str:
    return "complete" if has_value else "missing"


def _coerce_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _coerce_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


QUESTION_DISPOSITIONS = (
    "answered",
    "unknown",
    "refused",
    "skipped",
    "deferred",
    "invalidated",
)
_NON_FACT_QUESTION_DISPOSITIONS = {
    "unknown",
    "refused",
    "skipped",
    "deferred",
    "invalidated",
}
_QUESTION_DISPOSITION_ALIASES = {
    "answered": "answered",
    "answer": "answered",
    "unknown": "unknown",
    "do_not_know": "unknown",
    "dont_know": "unknown",
    "don't_know": "unknown",
    "do-not-know": "unknown",
    "declined": "refused",
    "decline": "refused",
    "refused": "refused",
    "refuse": "refused",
    "refusal": "refused",
    "skipped": "skipped",
    "skip": "skipped",
    "deferred": "deferred",
    "defer": "deferred",
    "invalidated": "invalidated",
    "invalidate": "invalidated",
    "contradictory": "contradictory",
}
_CLOSED_QUESTION_DISPOSITIONS = _NON_FACT_QUESTION_DISPOSITIONS | {
    "answered",
    "declined",
    "contradictory",
}


def canonical_question_disposition(value: Any) -> str:
    """Map an answer label onto the persisted disposition vocabulary."""
    token = _normalize_text(value).lower().replace(" ", "_")
    if token in _QUESTION_DISPOSITION_ALIASES:
        return _QUESTION_DISPOSITION_ALIASES[token]
    return ""


def question_disposition_creates_fact(disposition: str) -> bool:
    """Unknown and refusal dispositions are not facts or requirement satisfaction."""
    return canonical_question_disposition(disposition) == "answered"


def _question_disposition_key(record: Mapping[str, Any]) -> tuple:
    return (
        _normalize_text(record.get("target_id")),
        _normalize_text(record.get("target_revision")),
        _normalize_text(record.get("disposition")).lower(),
        bool(record.get("reopened")),
        _normalize_text(record.get("reopen_reason")),
    )


def _normalize_question_disposition_record(record: Mapping[str, Any]) -> Dict[str, Any]:
    disposition = canonical_question_disposition(record.get("disposition")) or _normalize_text(
        record.get("disposition")
    ).lower()
    non_fact = disposition in _NON_FACT_QUESTION_DISPOSITIONS or disposition in {"declined", "contradictory"}
    creates_fact = False if non_fact else bool(record.get("creates_fact"))
    satisfies_requirement = False if non_fact else bool(record.get("satisfies_requirement"))
    contradictory_conclusion = False if non_fact else bool(record.get("contradictory_conclusion"))
    if disposition != "answered":
        creates_fact = False if non_fact else creates_fact
    return {
        "target_id": _normalize_text(record.get("target_id")),
        "target_revision": _normalize_text(record.get("target_revision")) or "unresolved",
        "target_kind": _normalize_text(record.get("target_kind")) or None,
        "disposition": disposition,
        "question": _normalize_text(record.get("question")) or None,
        "answer": None if non_fact and not _normalize_text(record.get("answer")) else record.get("answer"),
        "reason": _normalize_text(record.get("reason")) or None,
        "creates_fact": creates_fact,
        "satisfies_requirement": satisfies_requirement,
        "contradictory_conclusion": contradictory_conclusion,
        "reopened": bool(record.get("reopened")),
        "reopen_reason": _normalize_text(record.get("reopen_reason")) or None,
        "evidence_change": _normalize_text(record.get("evidence_change")) or None,
        "scope_change": _normalize_text(record.get("scope_change")) or None,
        "status": "reopened" if record.get("reopened") else "disposed",
    }


def question_disposition_records(intake_case_file: Any) -> List[Dict[str, Any]]:
    case_file = _coerce_dict(intake_case_file)
    records: List[Dict[str, Any]] = []
    seen = set()
    for item in _coerce_list(case_file.get("question_dispositions")):
        if not isinstance(item, dict):
            continue
        normalized = _normalize_question_disposition_record(item)
        if not normalized["target_id"] or not normalized["disposition"]:
            continue
        key = _question_disposition_key(normalized)
        if key in seen:
            continue
        seen.add(key)
        records.append(normalized)
    return records


def question_target_is_closed(
    intake_case_file: Any,
    target_id: Any,
    target_revision: Any = None,
) -> bool:
    """A disposed target stays closed across revisions until an explicit reopen."""
    wanted = _normalize_text(target_id)
    if not wanted:
        return False
    revision = _normalize_text(target_revision)
    closed = False
    for record in question_disposition_records(intake_case_file):
        if record["target_id"] != wanted:
            continue
        if record["reopened"]:
            reopen_revision = record.get("target_revision") or ""
            if not revision or not reopen_revision or reopen_revision in {revision, "unresolved"}:
                closed = False
            continue
        if record["disposition"] in _CLOSED_QUESTION_DISPOSITIONS:
            closed = True
    return closed


def record_question_disposition(
    intake_case_file: Dict[str, Any],
    *,
    target_id: Any,
    target_revision: Any,
    disposition: Any,
    target_kind: Any = None,
    question: Any = None,
    answer: Any = None,
    reason: Any = None,
    creates_fact: bool = False,
    satisfies_requirement: bool = False,
    contradictory_conclusion: bool = False,
) -> Dict[str, Any]:
    """Persist one stable target revision and its disposition on the case file."""
    case_file = _coerce_dict(intake_case_file)
    canonical = canonical_question_disposition(disposition)
    if not canonical:
        raise ValueError("question disposition must be answered, unknown, refused, skipped, deferred, or invalidated")
    record = _normalize_question_disposition_record({
        "target_id": target_id,
        "target_revision": target_revision,
        "target_kind": target_kind,
        "disposition": canonical,
        "question": question,
        "answer": answer,
        "reason": reason,
        "creates_fact": creates_fact,
        "satisfies_requirement": satisfies_requirement,
        "contradictory_conclusion": contradictory_conclusion,
        "reopened": False,
    })
    if not record["target_id"]:
        raise ValueError("question disposition requires a stable target_id")
    records = question_disposition_records(case_file)
    records = [
        item for item in records
        if not (
            item["target_id"] == record["target_id"]
            and item["target_revision"] == record["target_revision"]
            and not item["reopened"]
        )
    ]
    records.append(record)
    case_file["question_dispositions"] = records
    return record


def reopen_question_disposition(
    intake_case_file: Dict[str, Any],
    target_id: Any,
    *,
    reason: Any,
    target_revision: Any = None,
    evidence_change: Any = None,
    scope_change: Any = None,
) -> Dict[str, Any]:
    """Reopen a disposed question only when new evidence or scope is named."""
    why = _normalize_text(reason)
    evidence = _normalize_text(evidence_change) or None
    scope = _normalize_text(scope_change) or None
    if not why:
        raise ValueError("reopening a disposed question requires a reason")
    if not evidence and not scope:
        raise ValueError("reopening a disposed question requires new evidence or changed scope")
    case_file = _coerce_dict(intake_case_file)
    wanted = _normalize_text(target_id)
    records = question_disposition_records(case_file)
    disposed = [
        item for item in records
        if item["target_id"] == wanted and not item["reopened"] and item["disposition"] in _CLOSED_QUESTION_DISPOSITIONS
    ]
    if not wanted or not disposed:
        raise ValueError("no disposed question matches that target")
    revision = _normalize_text(target_revision) or disposed[-1]["target_revision"]
    reopened = _normalize_question_disposition_record({
        **disposed[-1],
        "target_revision": revision,
        "reopened": True,
        "reopen_reason": why,
        "evidence_change": evidence,
        "scope_change": scope,
        "creates_fact": False,
        "satisfies_requirement": False,
        "contradictory_conclusion": False,
        "answer": None,
    })
    records.append(reopened)
    case_file["question_dispositions"] = records
    return reopened


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


def _normalize_scope_key(value: Any) -> str:
    text = _normalize_text(value).lower()
    return "".join(ch if ch.isalnum() else "_" for ch in text).strip("_")


def _looks_like_staff_person_name(value: Any) -> bool:
    text = _normalize_text(value)
    if not text:
        return False
    disallowed_tokens = {
        "administrative",
        "plan",
        "policy",
        "housing authority",
        "clackamas",
        "county",
        "continued occupancy",
        "admissions",
        "program",
        "nondiscrimination",
        "housing",
        "authority",
    }
    for match in re.finditer(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", text):
        matched_text = match.group(0).strip()
        matched_lowered = matched_text.lower()
        if any(token in matched_lowered for token in disallowed_tokens):
            continue
        return True
    return False


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


def _structured_timeline_text_signature(text: Any) -> Set[str]:
    normalized = _normalize_text(text or "").lower()
    normalized = re.sub(r"artifact\s*:\s*.*", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\([^()]*\)", "", normalized)
    normalized = re.sub(r"\b(?:19|20)\d{2}\b", " ", normalized)
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    stopwords = {
        "a", "an", "and", "after", "at", "by", "for", "from", "hacc", "i", "in", "is", "it", "me",
        "my", "not", "of", "on", "or", "staff", "tenant", "that", "the", "their", "this", "to", "was",
        "were", "with", "yet", "still", "unconfirmed", "confirmed", "estimate",
    }
    return {
        token
        for token in normalized.split()
        if len(token) > 2 and token not in stopwords
    }


def _structured_timeline_group_similarity(
    left_facts: List[Dict[str, Any]],
    right_facts: List[Dict[str, Any]],
) -> float:
    if len(left_facts) != len(right_facts) or not left_facts:
        return 0.0
    overlap_scores: List[float] = []
    for left_fact, right_fact in zip(left_facts, right_facts):
        left_tokens = _structured_timeline_text_signature(left_fact.get("text") or left_fact.get("event_label") or "")
        right_tokens = _structured_timeline_text_signature(right_fact.get("text") or right_fact.get("event_label") or "")
        if not left_tokens and not right_tokens:
            overlap_scores.append(1.0)
            continue
        union = left_tokens | right_tokens
        if not union:
            overlap_scores.append(0.0)
            continue
        overlap_scores.append(len(left_tokens & right_tokens) / len(union))
    return sum(overlap_scores) / len(overlap_scores)


def _structured_timeline_group_score(facts: List[Dict[str, Any]]) -> tuple[int, int, int]:
    anchored_count = 0
    dated_count = 0
    text_length = 0
    for fact in facts:
        temporal_context = _coerce_dict(fact.get("temporal_context"))
        if temporal_context.get("start_date"):
            anchored_count += 1
        if _normalize_text(fact.get("event_date_or_range") or ""):
            dated_count += 1
        text_length += len(_normalize_text(fact.get("text") or ""))
    return (anchored_count, dated_count, text_length)


def _has_structured_timeline_counterpart(
    fact: Dict[str, Any],
    structured_group_facts: Dict[str, List[Dict[str, Any]]],
) -> bool:
    predicate_family = _normalize_text(fact.get("predicate_family") or "").lower()
    text_value = _normalize_text(fact.get("text") or "").lower()
    for facts in structured_group_facts.values():
        for grouped_fact in facts:
            if not isinstance(grouped_fact, dict):
                continue
            grouped_family = _normalize_text(grouped_fact.get("predicate_family") or "").lower()
            grouped_text = _normalize_text(grouped_fact.get("text") or "").lower()
            if predicate_family and grouped_family == predicate_family:
                return True
            if predicate_family == "causation" and grouped_family in {"protected_activity", "adverse_action", "response_timeline", "hearing_process"}:
                return True
            if predicate_family in {"hearing_process", "response_timeline"} and grouped_family in {"hearing_process", "response_timeline"}:
                if any(token in text_value for token in ("hearing", "review", "response", "rights", "notice")):
                    return True
            if predicate_family == "protected_activity" and grouped_family == "hearing_process" and "protected activity" in text_value:
                return True
            if predicate_family == "protected_activity" and grouped_family == "hearing_process":
                if any(token in text_value for token in ("complaint", "review", "grievance", "raised concerns", "spoke up", "disputed")):
                    return True
            if grouped_text and text_value and grouped_text in text_value:
                return True
    return False


def _is_summary_like_timeline_fact(
    fact: Dict[str, Any],
    structured_group_facts: Dict[str, List[Dict[str, Any]]],
) -> bool:
    if _normalize_text(fact.get("structured_timeline_group") or ""):
        return False
    text_value = _normalize_text(fact.get("text") or "").lower()
    if not text_value:
        return False
    meta_prefixes = (
        "i am filing this complaint",
        "i want this complaint to include",
        "the unresolved facts are",
        "key facts that still need",
        "the dates of each event",
        "the exact adverse action",
        "the hacc staff names and titles",
    )
    if any(text_value.startswith(prefix) for prefix in meta_prefixes):
        return True
    summary_relative_prefixes = (
        "after i made my complaint",
        "after i made my complaint/request for review",
        "after i requested review",
        "after i asked for review",
    )
    if structured_group_facts and any(
        token in text_value
        for token in (
            "best timeline anchor i can give right now is",
            "still needs confirmation:",
            "`who:`",
            "`action:`",
            "`date:`",
            "`artifact:`",
        )
    ):
        return True
    if _has_structured_timeline_counterpart(fact, structured_group_facts):
        if any(
            token in text_value
            for token in (
                "best timeline anchor i can give right now is",
                "still needs confirmation:",
                "`who:`",
                "`action:`",
                "`date:`",
                "`artifact:`",
                "timing felt connected",
                "once i complained",
            )
        ):
            return True
        if any(text_value.startswith(prefix) for prefix in summary_relative_prefixes):
            return True
        if any(
            token in text_value
            for token in (
                "retaliated against me",
                "raised concerns",
                "grievance process",
                "hearing rights",
                "appeal rights",
                "adverse treatment",
                "housing at risk",
                "fair response",
            )
        ):
            return True
        if len(text_value) >= 90 and "after" in text_value:
            return True
    return False


def _dedupe_structured_timeline_groups(canonical_facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    ungrouped: List[Dict[str, Any]] = []
    for fact in canonical_facts:
        if not isinstance(fact, dict):
            continue
        group_id = _normalize_text(fact.get("structured_timeline_group") or "")
        if not group_id:
            ungrouped.append(fact)
            continue
        groups.setdefault(group_id, []).append(fact)

    if len(groups) < 2:
        return list(canonical_facts)

    sorted_groups = {
        group_id: sorted(
            [item for item in facts if isinstance(item, dict)],
            key=lambda item: (item.get("sequence_index") or 0, _normalize_text(item.get("fact_id") or "")),
        )
        for group_id, facts in groups.items()
    }
    drop_groups: Set[str] = set()
    group_ids = list(sorted_groups.keys())
    for index, left_group_id in enumerate(group_ids):
        if left_group_id in drop_groups:
            continue
        left_facts = sorted_groups[left_group_id]
        left_signature = tuple(_normalize_text(item.get("predicate_family") or "").lower() for item in left_facts)
        for right_group_id in group_ids[index + 1:]:
            if right_group_id in drop_groups:
                continue
            right_facts = sorted_groups[right_group_id]
            right_signature = tuple(_normalize_text(item.get("predicate_family") or "").lower() for item in right_facts)
            if left_signature != right_signature or not left_signature:
                continue
            if _structured_timeline_group_similarity(left_facts, right_facts) < 0.3:
                continue
            if _structured_timeline_group_score(left_facts) >= _structured_timeline_group_score(right_facts):
                drop_groups.add(right_group_id)
            else:
                drop_groups.add(left_group_id)
                break

    deduped: List[Dict[str, Any]] = []
    for fact in canonical_facts:
        if not isinstance(fact, dict):
            continue
        group_id = _normalize_text(fact.get("structured_timeline_group") or "")
        if group_id and group_id in drop_groups:
            continue
        deduped.append(fact)
    return deduped


def _normalize_canonical_fact_record(record: Any) -> Dict[str, Any]:
    fact = _coerce_dict(record)
    normalized_text = _normalize_text(fact.get("text") or "")
    fact_type = _normalize_text(fact.get("fact_type") or "general").lower() or "general"
    claim_types = _unique_normalized_strings(
        list(fact.get("claim_types") or [])
        + ([fact.get("target_claim_type")] if str(fact.get("target_claim_type") or "").strip() else [])
    )
    element_tags = _unique_normalized_strings(
        list(fact.get("element_tags") or [])
        + list(fact.get("target_element_ids") or [])
        + ([fact.get("target_element_id")] if str(fact.get("target_element_id") or "").strip() else [])
    )
    element_links = _normalize_intake_target_links(
        fact.get("element_links") or fact.get("target_links"),
        claim_types=claim_types,
        element_ids=element_tags,
    )
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
        "claim_types": claim_types,
        "element_tags": element_tags,
        "target_claim_types": claim_types,
        "target_element_ids": element_tags,
        "element_links": element_links,
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


def _normalize_intake_target_links(
    value: Any,
    *,
    claim_types: List[str] | None = None,
    element_ids: List[str] | None = None,
    fact_ids: List[str] | None = None,
) -> List[Dict[str, str]]:
    links: List[Dict[str, str]] = []
    seen = set()

    def _append_link(
        *,
        claim_type: Any = "",
        element_id: Any = "",
        fact_id: Any = "",
    ) -> None:
        normalized_claim_type = _normalize_text(claim_type)
        normalized_element_id = _normalize_text(element_id)
        normalized_fact_id = _normalize_text(fact_id)
        if not normalized_claim_type and not normalized_element_id and not normalized_fact_id:
            return
        marker = (normalized_claim_type, normalized_element_id, normalized_fact_id)
        if marker in seen:
            return
        seen.add(marker)
        link: Dict[str, str] = {}
        if normalized_claim_type:
            link["claim_type"] = normalized_claim_type
        if normalized_element_id:
            link["element_id"] = normalized_element_id
        if normalized_fact_id:
            link["fact_id"] = normalized_fact_id
        links.append(link)

    for item in value if isinstance(value, list) else []:
        if isinstance(item, dict):
            _append_link(
                claim_type=item.get("claim_type") or item.get("target_claim_type"),
                element_id=item.get("element_id") or item.get("target_element_id") or item.get("claim_element_id"),
                fact_id=item.get("fact_id") or item.get("target_fact_id"),
            )
            continue
        normalized_item = _normalize_text(item)
        if normalized_item:
            _append_link(element_id=normalized_item)

    normalized_claim_types = _unique_normalized_strings(claim_types or [])
    normalized_element_ids = _unique_normalized_strings(element_ids or [])
    normalized_fact_ids = _unique_normalized_strings(fact_ids or [])
    if normalized_claim_types and normalized_element_ids and normalized_fact_ids:
        for claim_type in normalized_claim_types:
            for element_id in normalized_element_ids:
                for fact_id in normalized_fact_ids:
                    _append_link(claim_type=claim_type, element_id=element_id, fact_id=fact_id)
    elif normalized_claim_types and normalized_element_ids:
        for claim_type in normalized_claim_types:
            for element_id in normalized_element_ids:
                _append_link(claim_type=claim_type, element_id=element_id)
    else:
        for claim_type in normalized_claim_types:
            _append_link(claim_type=claim_type)
        for element_id in normalized_element_ids:
            _append_link(element_id=element_id)
    for fact_id in normalized_fact_ids:
        _append_link(fact_id=fact_id)
    return links


def _normalize_proof_lead_record(record: Any) -> Dict[str, Any]:
    lead = _coerce_dict(record)
    lead_type = _normalize_text(lead.get("lead_type") or "evidence").lower() or "evidence"
    related_fact_ids = _unique_normalized_strings(lead.get("related_fact_ids") or [])
    fact_targets = _unique_normalized_strings(
        list(lead.get("fact_targets") or [])
        + list(lead.get("target_fact_ids") or [])
        + related_fact_ids
    )
    element_targets = _unique_normalized_strings(
        list(lead.get("element_targets") or [])
        + list(lead.get("target_element_ids") or [])
        + ([lead.get("target_element_id")] if str(lead.get("target_element_id") or "").strip() else [])
    )
    target_claim_types = _unique_normalized_strings(
        list(lead.get("target_claim_types") or [])
        + list(lead.get("claim_types") or [])
        + ([lead.get("target_claim_type")] if str(lead.get("target_claim_type") or "").strip() else [])
    )
    target_links = _normalize_intake_target_links(
        lead.get("target_links") or lead.get("element_links"),
        claim_types=target_claim_types,
        element_ids=element_targets,
        fact_ids=fact_targets,
    )
    raw_temporal_scope = _normalize_text(
        lead.get("temporal_scope")
        or _coerce_dict(lead.get("temporal_context")).get("raw_text")
        or ""
    ) or None
    return {
        **lead,
        "lead_type": lead_type,
        "description": _normalize_text(lead.get("description") or ""),
        "related_fact_ids": related_fact_ids,
        "fact_targets": fact_targets,
        "element_targets": element_targets,
        "target_claim_types": target_claim_types,
        "target_element_ids": element_targets,
        "target_fact_ids": fact_targets,
        "target_links": target_links,
        "timeline_anchor_ids": _unique_normalized_strings(lead.get("timeline_anchor_ids") or []),
        "availability": _normalize_text(lead.get("availability") or "availability_unknown").lower() or "availability_unknown",
        "availability_details": _normalize_text(lead.get("availability_details") or ""),
        "owner": _normalize_text(lead.get("owner") or "unknown") or "unknown",
        "custodian": _normalize_text(lead.get("custodian") or lead.get("owner") or "unknown") or "unknown",
        "expected_format": _normalize_text(lead.get("expected_format") or _derive_expected_format(lead_type)),
        "retrieval_path": _normalize_text(lead.get("retrieval_path") or _derive_retrieval_path(lead_type)),
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


def _ensure_stable_intake_record_ids(
    records: Any,
    *,
    id_key: str,
    prefix: str,
) -> List[Dict[str, Any]]:
    normalized_records = [
        dict(record)
        for record in (records if isinstance(records, list) else [])
        if isinstance(record, dict)
    ]
    seen_ids = {
        _normalize_text(record.get(id_key) or "")
        for record in normalized_records
        if _normalize_text(record.get(id_key) or "")
    }
    next_index = 1
    for record in normalized_records:
        if _normalize_text(record.get(id_key) or ""):
            continue
        while f"{prefix}_{next_index:03d}" in seen_ids:
            next_index += 1
        record[id_key] = f"{prefix}_{next_index:03d}"
        seen_ids.add(record[id_key])
        next_index += 1
    return normalized_records


def _merge_normalized_string_lists(*values: Any) -> List[str]:
    merged: List[str] = []
    for value in values:
        for item in value if isinstance(value, list) else []:
            normalized = _normalize_text(item)
            if normalized and normalized not in merged:
                merged.append(normalized)
    return merged


def _merge_temporal_context_records(base: Any, overlay: Any) -> Dict[str, Any]:
    base_context = _coerce_dict(base)
    overlay_context = _coerce_dict(overlay)
    merged = {**base_context, **overlay_context}
    for key in ("start_date", "end_date", "matched_text", "raw_text", "granularity"):
        merged[key] = overlay_context.get(key) or base_context.get(key)
    merged["relative_markers"] = _merge_normalized_string_lists(
        base_context.get("relative_markers"),
        overlay_context.get("relative_markers"),
    )
    return merged


def _canonical_fact_match_keys(record: Any) -> List[tuple[Any, ...]]:
    fact = _normalize_canonical_fact_record(record)
    keys: List[tuple[Any, ...]] = []
    fact_id = _normalize_text(fact.get("fact_id") or "")
    if fact_id:
        keys.append(("fact_id", fact_id))
    fact_type = _normalize_text(fact.get("fact_type") or "").lower()
    text = _normalize_text(fact.get("text") or "")
    if fact_type and text:
        keys.append(("fact", fact_type, text))
    return keys


def _merge_canonical_fact_records(base: Any, overlay: Any) -> Dict[str, Any]:
    base_fact = _normalize_canonical_fact_record(base)
    overlay_fact = _normalize_canonical_fact_record(overlay)
    merged_claim_types = _merge_normalized_string_lists(base_fact.get("claim_types"), overlay_fact.get("claim_types"))
    merged_element_tags = _merge_normalized_string_lists(base_fact.get("element_tags"), overlay_fact.get("element_tags"))
    return {
        **base_fact,
        **overlay_fact,
        "actor_ids": _merge_normalized_string_lists(base_fact.get("actor_ids"), overlay_fact.get("actor_ids")),
        "target_ids": _merge_normalized_string_lists(base_fact.get("target_ids"), overlay_fact.get("target_ids")),
        "claim_types": merged_claim_types,
        "element_tags": merged_element_tags,
        "target_claim_types": merged_claim_types,
        "target_element_ids": merged_element_tags,
        "element_links": _normalize_intake_target_links(
            list(base_fact.get("element_links") or []) + list(overlay_fact.get("element_links") or []),
            claim_types=merged_claim_types,
            element_ids=merged_element_tags,
        ),
        "timeline_anchor_ids": _merge_normalized_string_lists(
            base_fact.get("timeline_anchor_ids"),
            overlay_fact.get("timeline_anchor_ids"),
        ),
        "event_support_refs": _merge_normalized_string_lists(
            base_fact.get("event_support_refs"),
            overlay_fact.get("event_support_refs"),
        ),
        "source_artifact_ids": _merge_normalized_string_lists(
            base_fact.get("source_artifact_ids"),
            overlay_fact.get("source_artifact_ids"),
        ),
        "testimony_record_ids": _merge_normalized_string_lists(
            base_fact.get("testimony_record_ids"),
            overlay_fact.get("testimony_record_ids"),
        ),
        "source_span_refs": _coerce_provenance_refs(
            list(base_fact.get("source_span_refs") or []) + list(overlay_fact.get("source_span_refs") or [])
        ),
        "fact_participants": {
            **_coerce_dict(base_fact.get("fact_participants")),
            **_coerce_dict(overlay_fact.get("fact_participants")),
        },
        "temporal_context": _merge_temporal_context_records(
            base_fact.get("temporal_context"),
            overlay_fact.get("temporal_context"),
        ),
    }


def _merge_preserved_canonical_facts(graph_records: Any, existing_records: Any) -> List[Dict[str, Any]]:
    merged_records = [
        _normalize_canonical_fact_record(record)
        for record in graph_records if isinstance(graph_records, list)
        if isinstance(record, dict)
    ]
    index_by_key: Dict[tuple[Any, ...], int] = {}
    for index, record in enumerate(merged_records):
        for key in _canonical_fact_match_keys(record):
            index_by_key[key] = index

    for record in existing_records if isinstance(existing_records, list) else []:
        if not isinstance(record, dict):
            continue
        match_index = None
        for key in _canonical_fact_match_keys(record):
            if key in index_by_key:
                match_index = index_by_key[key]
                break
        if match_index is None:
            merged_records.append(_normalize_canonical_fact_record(record))
            match_index = len(merged_records) - 1
        else:
            merged_records[match_index] = _merge_canonical_fact_records(merged_records[match_index], record)
        for key in _canonical_fact_match_keys(merged_records[match_index]):
            index_by_key[key] = match_index
    return merged_records


def _proof_lead_match_keys(record: Any) -> List[tuple[Any, ...]]:
    lead = _normalize_proof_lead_record(record)
    keys: List[tuple[Any, ...]] = []
    lead_id = _normalize_text(lead.get("lead_id") or "")
    if lead_id:
        keys.append(("lead_id", lead_id))
    lead_type = _normalize_text(lead.get("lead_type") or "").lower()
    description = _normalize_text(lead.get("description") or "")
    if lead_type and description:
        keys.append(("lead", lead_type, description))
    elif description:
        keys.append(("lead_description", description))
    return keys


def _merge_proof_lead_records(base: Any, overlay: Any) -> Dict[str, Any]:
    base_lead = _normalize_proof_lead_record(base)
    overlay_lead = _normalize_proof_lead_record(overlay)
    merged_related_fact_ids = _merge_normalized_string_lists(
        base_lead.get("related_fact_ids"),
        overlay_lead.get("related_fact_ids"),
    )
    merged_fact_targets = _merge_normalized_string_lists(
        base_lead.get("fact_targets"),
        overlay_lead.get("fact_targets"),
        merged_related_fact_ids,
    )
    merged_element_targets = _merge_normalized_string_lists(
        base_lead.get("element_targets"),
        overlay_lead.get("element_targets"),
    )
    merged_claim_types = _merge_normalized_string_lists(
        base_lead.get("target_claim_types"),
        overlay_lead.get("target_claim_types"),
    )
    return {
        **base_lead,
        **overlay_lead,
        "related_fact_ids": merged_related_fact_ids,
        "fact_targets": merged_fact_targets,
        "element_targets": merged_element_targets,
        "target_claim_types": merged_claim_types,
        "target_element_ids": merged_element_targets,
        "target_fact_ids": merged_fact_targets,
        "target_links": _normalize_intake_target_links(
            list(base_lead.get("target_links") or []) + list(overlay_lead.get("target_links") or []),
            claim_types=merged_claim_types,
            element_ids=merged_element_targets,
            fact_ids=merged_fact_targets,
        ),
        "timeline_anchor_ids": _merge_normalized_string_lists(
            base_lead.get("timeline_anchor_ids"),
            overlay_lead.get("timeline_anchor_ids"),
        ),
        "source_artifact_ids": _merge_normalized_string_lists(
            base_lead.get("source_artifact_ids"),
            overlay_lead.get("source_artifact_ids"),
        ),
        "testimony_record_ids": _merge_normalized_string_lists(
            base_lead.get("testimony_record_ids"),
            overlay_lead.get("testimony_record_ids"),
        ),
        "source_span_refs": _coerce_provenance_refs(
            list(base_lead.get("source_span_refs") or []) + list(overlay_lead.get("source_span_refs") or [])
        ),
        "temporal_context": _merge_temporal_context_records(
            base_lead.get("temporal_context"),
            overlay_lead.get("temporal_context"),
        ),
    }


def _merge_preserved_proof_leads(graph_records: Any, existing_records: Any) -> List[Dict[str, Any]]:
    merged_records = [
        _normalize_proof_lead_record(record)
        for record in graph_records if isinstance(graph_records, list)
        if isinstance(record, dict)
    ]
    index_by_key: Dict[tuple[Any, ...], int] = {}
    for index, record in enumerate(merged_records):
        for key in _proof_lead_match_keys(record):
            index_by_key[key] = index

    for record in existing_records if isinstance(existing_records, list) else []:
        if not isinstance(record, dict):
            continue
        match_index = None
        for key in _proof_lead_match_keys(record):
            if key in index_by_key:
                match_index = index_by_key[key]
                break
        if match_index is None:
            merged_records.append(_normalize_proof_lead_record(record))
            match_index = len(merged_records) - 1
        else:
            merged_records[match_index] = _merge_proof_lead_records(merged_records[match_index], record)
        for key in _proof_lead_match_keys(merged_records[match_index]):
            index_by_key[key] = match_index
    return merged_records


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

    # Track explicit fact pairs so inferred relations only fill gaps.
    explicit_pairs: set = set()

    for index, relation in enumerate(timeline_relations if isinstance(timeline_relations, list) else [], start=1):
        if not isinstance(relation, dict):
            continue
        raw_relation_id = _normalize_text(relation.get("relation_id") or "")
        relation_id = raw_relation_id or f"timeline_relation_{index:03d}"
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
        raw_inference_basis = _normalize_text(relation.get("inference_basis") or "")
        relation_id_looks_generated = bool(raw_relation_id and raw_relation_id.startswith("timeline_relation_"))
        inference_basis = raw_inference_basis or (
            "normalized_temporal_context" if relation_id_looks_generated else "explicit_relation"
        )
        inference_mode = _normalize_text(relation.get("inference_mode") or "")
        if not inference_mode:
            inference_mode = (
                "derived_from_structured_sequence"
                if inference_basis == "structured_timeline_sequence"
                else (
                    "derived_from_temporal_context"
                    if inference_basis == "normalized_temporal_context"
                    else "explicit"
                )
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
                "inference_mode": inference_mode,
                "inference_basis": inference_basis,
                "explanation": (
                    f"{source_fact_id or 'unknown_fact'} {str(relation.get('relation_type') or 'related_to')} "
                    f"{target_fact_id or 'unknown_fact'} based on normalized temporal context."
                ),
            }
        )
        if source_fact_id and target_fact_id:
            explicit_pairs.add((source_fact_id, target_fact_id))
            explicit_pairs.add((target_fact_id, source_fact_id))

    # T1: Infer ordering relations from date anchors for pairs without an explicit relation.
    # When two timeline-capable facts both carry a start_date, derive before/same_time/after
    # so that proof-bundle and rule-profile evaluation can use a complete partial-order graph
    # even when the upstream relation extractor missed the pair.
    #
    # Guard: skip inference when the anchored-fact set is large to avoid O(n²) overhead.
    # Typical temporal-capable sets are small (≤ ~20 facts); a 50-fact ceiling keeps the
    # worst-case below 1 250 pairs while protecting against degenerate inputs.
    _MAX_INFERRED_ANCHOR_FACTS = 50
    anchored_facts = [
        (
            _normalize_text(fact.get("fact_id") or ""),
            str(_coerce_dict(fact.get("temporal_context")).get("start_date") or "").strip(),
            fact,
        )
        for fact in _timeline_capable_facts(canonical_facts)
        if _normalize_text(fact.get("fact_id") or "")
        and str(_coerce_dict(fact.get("temporal_context")).get("start_date") or "").strip()
    ]
    inferred_index = len(registry)
    if len(anchored_facts) <= _MAX_INFERRED_ANCHOR_FACTS:
        for (id_a, date_a, fact_a), (id_b, date_b, fact_b) in combinations(anchored_facts, 2):
            pair_key = (id_a, id_b)
            if pair_key in explicit_pairs:
                continue
            if date_a < date_b:
                relation_type = "before"
                source_fact_id, target_fact_id = id_a, id_b
                source_fact, target_fact = fact_a, fact_b
                source_date, target_date = date_a, date_b
            elif date_a > date_b:
                relation_type = "before"
                source_fact_id, target_fact_id = id_b, id_a
                source_fact, target_fact = fact_b, fact_a
                source_date, target_date = date_b, date_a
            else:
                relation_type = "same_time"
                source_fact_id, target_fact_id = id_a, id_b
                source_fact, target_fact = fact_a, fact_b
                source_date, target_date = date_a, date_b
            inferred_index += 1
            relation_id = f"inferred_relation_{inferred_index:03d}"
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
                    "relation_id": relation_id,
                    "registry_version": "temporal_relation_registry.v1",
                    "relation_type": relation_type,
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
                    "inference_mode": "derived_from_date_anchors",
                    "inference_basis": (
                        f"{source_fact_id}.start_date:{source_date} vs {target_fact_id}.start_date:{target_date}"
                    ),
                    "explanation": (
                        f"{source_fact_id} {relation_type} {target_fact_id} inferred from date anchors "
                        f"({source_date} vs {target_date})."
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
    structured_group_facts: Dict[str, List[Dict[str, Any]]] = {}
    duplicate_timeline_text_counts: Dict[str, int] = {}

    for fact in _timeline_capable_facts(canonical_facts):
        structured_group = _normalize_text(fact.get("structured_timeline_group") or "")
        if structured_group:
            structured_group_facts.setdefault(structured_group, []).append(fact)
        text_value = _normalize_text(fact.get("text") or "").lower()
        if text_value:
            duplicate_timeline_text_counts[text_value] = duplicate_timeline_text_counts.get(text_value, 0) + 1

    for fact in _timeline_capable_facts(canonical_facts):
        fact_id = _normalize_text(fact.get("fact_id") or "")
        temporal_context = _coerce_dict(fact.get("temporal_context"))
        if temporal_context.get("start_date"):
            continue
        if _is_summary_like_timeline_fact(fact, structured_group_facts):
            continue
        normalized_text = _normalize_text(fact.get("text") or "").lower()
        if (
            normalized_text
            and duplicate_timeline_text_counts.get(normalized_text, 0) > 1
            and _normalize_text(fact.get("structured_timeline_group") or "") == ""
            and not _unique_normalized_strings(temporal_context.get("relative_markers") or [])
        ):
            continue

        relative_markers = _unique_normalized_strings(temporal_context.get("relative_markers") or [])
        issue_type = "relative_only_ordering" if relative_markers else "missing_anchor"
        left_node_name = _normalize_text(fact.get("text") or "") or None
        structured_group = _normalize_text(fact.get("structured_timeline_group") or "")
        grouped_facts = structured_group_facts.get(structured_group, []) if structured_group else []
        has_structured_sequence_support = (
            bool(structured_group)
            and len(grouped_facts) > 1
            and isinstance(fact.get("sequence_index"), int)
        )
        group_has_any_anchor = any(
            bool(_coerce_dict(item.get("temporal_context")).get("start_date"))
            for item in grouped_facts
            if isinstance(item, dict)
        )
        group_has_relative_support = any(
            bool(_coerce_dict(item.get("temporal_context")).get("relative_markers"))
            for item in grouped_facts
            if isinstance(item, dict)
        )
        issue_severity = "blocking"
        issue_blocking = True
        recommended_resolution_lane = "clarify_with_complainant"
        if has_structured_sequence_support and (group_has_any_anchor or group_has_relative_support):
            issue_severity = "warning"
            issue_blocking = False
            recommended_resolution_lane = "capture_testimony"
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
                "severity": issue_severity,
                "blocking": issue_blocking,
                "recommended_resolution_lane": recommended_resolution_lane,
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
                    recommended_resolution_lane,
                ),
                "source_kind": "temporal_fact_registry",
                "source_ref": fact_id or None,
                "inference_mode": "derived_from_temporal_context",
            }
        )
        issue_index_by_signature[signature] = len(registry) - 1

    # T1: canonical issue type aliases so that contradiction-queue entries tagged with
    # the "temporal_" prefix resolve to the same canonical category that rule profiles
    # and downstream consumers (e.g. evaluate_temporal_rule_profile) expect.
    # Entries not present in this mapping pass through unchanged — they are already
    # in canonical form (e.g. "temporal_reverse_before" is not normalised further).
    _TEMPORAL_ISSUE_CATEGORY_ALIASES: Dict[str, str] = {
        "temporal_contradictory_dates": "contradictory_dates",
        "temporal_limitations_risk": "limitations_risk",
        "temporal_missing_anchor": "missing_anchor",
        "temporal_relative_only_ordering": "relative_only_ordering",
    }

    for contradiction in contradiction_queue if isinstance(contradiction_queue, list) else []:
        candidate = _coerce_dict(contradiction)
        raw_category = _normalize_text(candidate.get("category") or candidate.get("type") or "").lower()
        if not raw_category.startswith("temporal"):
            continue
        # Normalise to the canonical category expected by rule profiles.
        category = _TEMPORAL_ISSUE_CATEGORY_ALIASES.get(raw_category, raw_category)
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
    anchors = _coerce_list(timeline_anchors)
    relations = _coerce_list(timeline_relations)

    relation_type_counts: Dict[str, int] = {}
    temporal_conflict_relation_count = 0
    for relation in relations:
        relation_dict = _coerce_dict(relation)
        if not relation_dict:
            continue
        relation_type = _normalize_text(relation_dict.get("relation_type") or "").lower()
        if not relation_type:
            continue
        relation_type_counts[relation_type] = relation_type_counts.get(relation_type, 0) + 1
        if relation_type in {"temporal_conflict", "contradiction", "overlap_conflict"}:
            temporal_conflict_relation_count += 1

    timeline_fact_ids = {
        _normalize_text(_coerce_dict(fact).get("fact_id") or "") or f"timeline_fact_{index}"
        for index, fact in enumerate(timeline_facts, start=1)
        if isinstance(fact, dict)
    }
    anchored_fact_ids = {
        _normalize_text(_coerce_dict(anchor).get("source_fact_id") or _coerce_dict(anchor).get("fact_id") or "")
        for anchor in anchors
        if isinstance(anchor, dict)
    }
    anchored_fact_ids.discard("")

    missing_temporal_fact_ids: List[str] = []
    relative_only_fact_ids: List[str] = []
    approximate_fact_ids: List[str] = []
    range_fact_ids: List[str] = []
    non_day_precision_fact_ids: List[str] = []
    day_precision_fact_ids: List[str] = []
    ordered_fact_count = 0

    for index, fact in enumerate(timeline_facts, start=1):
        fact_dict = _coerce_dict(fact)
        if not fact_dict:
            continue
        fact_id = _normalize_text(fact_dict.get("fact_id") or "") or f"timeline_fact_{index}"
        temporal_context = _coerce_dict(fact_dict.get("temporal_context"))
        start_date = _normalize_text(temporal_context.get("start_date") or "")
        end_date = _normalize_text(temporal_context.get("end_date") or "")
        granularity = _normalize_text(temporal_context.get("granularity") or "").lower()
        relative_markers = _unique_normalized_strings(temporal_context.get("relative_markers") or [])
        has_anchor = bool(start_date)

        if has_anchor:
            ordered_fact_count += 1
            if granularity == "day" and len(start_date) == 10:
                day_precision_fact_ids.append(fact_id)
            else:
                non_day_precision_fact_ids.append(fact_id)
        else:
            missing_temporal_fact_ids.append(fact_id)
            if relative_markers:
                relative_only_fact_ids.append(fact_id)

        if bool(temporal_context.get("is_approximate", False)):
            approximate_fact_ids.append(fact_id)
        if bool(temporal_context.get("is_range", False)) or (start_date and end_date and start_date != end_date):
            range_fact_ids.append(fact_id)

    orphan_anchor_count = sum(
        1
        for anchor in anchors
        if _normalize_text(_coerce_dict(anchor).get("source_fact_id") or _coerce_dict(anchor).get("fact_id") or "")
        and _normalize_text(_coerce_dict(anchor).get("source_fact_id") or _coerce_dict(anchor).get("fact_id") or "")
        not in timeline_fact_ids
    )

    warnings: List[str] = []
    if missing_temporal_fact_ids:
        warnings.append("Some timeline facts still lack normalized dates or ranges.")
    if relative_only_fact_ids:
        warnings.append("Some timeline facts only express relative ordering and still need anchoring.")
    if temporal_conflict_relation_count:
        warnings.append("Timeline relations include unresolved temporal conflicts.")
    if non_day_precision_fact_ids:
        warnings.append("Some anchored facts are only month/year precision and may still need day-level dates.")

    return {
        "event_count": len(timeline_facts),
        "anchor_count": len(anchors),
        "ordered_fact_count": ordered_fact_count,
        "unsequenced_fact_count": len(missing_temporal_fact_ids),
        "approximate_fact_count": len(approximate_fact_ids),
        "range_fact_count": len(range_fact_ids),
        "relation_count": len(relations),
        "relation_type_counts": relation_type_counts,
        "missing_temporal_fact_ids": missing_temporal_fact_ids,
        "relative_only_fact_ids": relative_only_fact_ids,
        "warnings": warnings,
        "partial_order_ready": bool(timeline_facts) and not missing_temporal_fact_ids and not temporal_conflict_relation_count,
        "day_precision_fact_count": len(day_precision_fact_ids),
        "non_day_precision_fact_ids": non_day_precision_fact_ids,
        "temporal_conflict_relation_count": temporal_conflict_relation_count,
        "orphan_anchor_count": orphan_anchor_count,
    }


def _temporal_record_claim_keys(record: Dict[str, Any]) -> set[str]:
    values: List[Any] = []
    for field_name in ("claim_types", "affected_claim_types"):
        field_value = record.get(field_name)
        if isinstance(field_value, list):
            values.extend(field_value)
    for field_name in ("claim_type", "target_claim_type"):
        field_value = record.get(field_name)
        if _normalize_text(field_value):
            values.append(field_value)
    intent = record.get("intake_question_intent") if isinstance(record.get("intake_question_intent"), dict) else {}
    if _normalize_text(intent.get("target_claim_type")):
        values.append(intent.get("target_claim_type"))
    return {_normalize_scope_key(value) for value in values if _normalize_scope_key(value)}


def _temporal_record_element_keys(record: Dict[str, Any]) -> set[str]:
    values: List[Any] = []
    for field_name in ("element_tags", "affected_element_ids", "target_element_ids", "element_targets"):
        field_value = record.get(field_name)
        if isinstance(field_value, list):
            values.extend(field_value)
    for field_name in ("claim_element_id", "target_element_id"):
        field_value = record.get(field_name)
        if _normalize_text(field_value):
            values.append(field_value)
    intent = record.get("intake_question_intent") if isinstance(record.get("intake_question_intent"), dict) else {}
    if _normalize_text(intent.get("target_element_id")):
        values.append(intent.get("target_element_id"))
    return {_normalize_scope_key(value) for value in values if _normalize_scope_key(value)}


def _temporal_issue_id(issue: Dict[str, Any]) -> str:
    return _normalize_text(issue.get("issue_id") or issue.get("contradiction_id") or issue.get("dependency_id") or "")


def _temporal_relation_preview(relation: Dict[str, Any]) -> str:
    source_fact_id = _normalize_text(relation.get("source_fact_id") or relation.get("source_temporal_fact_id") or "")
    target_fact_id = _normalize_text(relation.get("target_fact_id") or relation.get("target_temporal_fact_id") or "")
    relation_type = _normalize_text(relation.get("relation_type") or "").replace("_", " ")
    return " ".join(part for part in [source_fact_id, relation_type, target_fact_id] if part).strip()


def _build_temporal_graph_record(
    *,
    graph_id: str,
    claim_type: str,
    facts: List[Dict[str, Any]],
    relations: List[Dict[str, Any]],
    issues: List[Dict[str, Any]],
    element_id: str = "",
    element_label: str = "",
) -> Dict[str, Any]:
    fact_ids = [
        _normalize_text(fact.get("fact_id") or fact.get("temporal_fact_id") or "")
        for fact in facts
        if _normalize_text(fact.get("fact_id") or fact.get("temporal_fact_id") or "")
    ]
    relation_ids = [
        _normalize_text(relation.get("relation_id") or "")
        for relation in relations
        if _normalize_text(relation.get("relation_id") or "")
    ]
    issue_ids: List[str] = []
    open_issue_ids: List[str] = []
    blocking_issue_ids: List[str] = []
    issue_type_counts: Dict[str, int] = {}
    issue_status_counts: Dict[str, int] = {}
    severity_counts: Dict[str, int] = {}
    missing_temporal_predicates: List[str] = []
    required_provenance_kinds: List[str] = []
    warnings: List[str] = []

    for issue in issues:
        issue_id = _temporal_issue_id(issue)
        if issue_id and issue_id not in issue_ids:
            issue_ids.append(issue_id)
        issue_type = _normalize_text(issue.get("issue_type") or issue.get("category") or "").lower()
        if issue_type:
            issue_type_counts[issue_type] = issue_type_counts.get(issue_type, 0) + 1
        status_value = _normalize_text(issue.get("current_resolution_status") or issue.get("status") or "open").lower() or "open"
        issue_status_counts[status_value] = issue_status_counts.get(status_value, 0) + 1
        severity = _normalize_text(issue.get("severity") or "").lower()
        if severity:
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        if status_value != "resolved" and issue_id:
            open_issue_ids.append(issue_id)
        if status_value != "resolved" and (bool(issue.get("blocking")) or severity == "blocking") and issue_id:
            blocking_issue_ids.append(issue_id)
        for predicate in issue.get("missing_temporal_predicates") if isinstance(issue.get("missing_temporal_predicates"), list) else []:
            normalized_predicate = _normalize_text(predicate)
            if normalized_predicate and normalized_predicate not in missing_temporal_predicates:
                missing_temporal_predicates.append(normalized_predicate)
        for provenance_kind in issue.get("required_provenance_kinds") if isinstance(issue.get("required_provenance_kinds"), list) else []:
            normalized_kind = _normalize_text(provenance_kind)
            if normalized_kind and normalized_kind not in required_provenance_kinds:
                required_provenance_kinds.append(normalized_kind)
        if status_value != "resolved":
            summary = _normalize_text(issue.get("summary") or issue_type or issue_id)
            if summary and summary not in warnings:
                warnings.append(summary)

    relation_type_counts: Dict[str, int] = {}
    relation_preview: List[str] = []
    for relation in relations:
        relation_type = _normalize_text(relation.get("relation_type") or "").lower()
        if relation_type:
            relation_type_counts[relation_type] = relation_type_counts.get(relation_type, 0) + 1
        preview = _temporal_relation_preview(relation)
        if preview and preview not in relation_preview:
            relation_preview.append(preview)

    anchored_fact_ids: List[str] = []
    unanchored_fact_ids: List[str] = []
    timeline_anchor_ids: List[str] = []
    for fact in facts:
        fact_id = _normalize_text(fact.get("fact_id") or fact.get("temporal_fact_id") or "")
        temporal_context = _coerce_dict(fact.get("temporal_context"))
        has_anchor = bool(
            temporal_context.get("start_date")
            or fact.get("start_time")
            or _coerce_list(fact.get("timeline_anchor_ids"))
        )
        if fact_id and has_anchor:
            anchored_fact_ids.append(fact_id)
        elif fact_id:
            unanchored_fact_ids.append(fact_id)
        for anchor_id in fact.get("timeline_anchor_ids") if isinstance(fact.get("timeline_anchor_ids"), list) else []:
            normalized_anchor_id = _normalize_text(anchor_id)
            if normalized_anchor_id and normalized_anchor_id not in timeline_anchor_ids:
                timeline_anchor_ids.append(normalized_anchor_id)

    partial_order_ready = bool(facts) and not open_issue_ids and not blocking_issue_ids and not unanchored_fact_ids
    graph_record = {
        "contract_version": "claim_temporal_graph.v1",
        "graph_id": graph_id,
        "claim_type": claim_type,
        "claim_key": _normalize_scope_key(claim_type),
        "element_id": element_id,
        "element_key": _normalize_scope_key(element_id or element_label),
        "element_label": element_label,
        "fact_count": len(facts),
        "relation_count": len(relations),
        "issue_count": len(issues),
        "fact_ids": fact_ids,
        "temporal_fact_ids": fact_ids,
        "anchored_fact_ids": anchored_fact_ids,
        "unanchored_fact_ids": unanchored_fact_ids,
        "relation_ids": relation_ids,
        "temporal_relation_ids": relation_ids,
        "issue_ids": issue_ids,
        "temporal_issue_ids": issue_ids,
        "open_issue_ids": open_issue_ids,
        "blocking_issue_ids": blocking_issue_ids,
        "timeline_anchor_ids": timeline_anchor_ids,
        "relation_type_counts": relation_type_counts,
        "relation_preview": relation_preview[:10],
        "issue_type_counts": issue_type_counts,
        "issue_status_counts": issue_status_counts,
        "severity_counts": severity_counts,
        "missing_temporal_predicates": missing_temporal_predicates,
        "required_provenance_kinds": required_provenance_kinds,
        "warning_count": len(warnings),
        "warnings": warnings,
        "partial_order_ready": partial_order_ready,
        "readiness": {
            "ready_for_temporal_formalization": partial_order_ready,
            "trace_fact_ids": fact_ids,
            "trace_relation_ids": relation_ids,
            "trace_issue_ids": issue_ids,
            "blocking_issue_ids": blocking_issue_ids,
            "missing_temporal_predicates": missing_temporal_predicates,
            "required_provenance_kinds": required_provenance_kinds,
        },
        "facts": facts,
        "relations": relations,
        "issues": issues,
    }
    return graph_record


def build_claim_temporal_graphs(
    temporal_fact_registry: List[Dict[str, Any]],
    temporal_relation_registry: List[Dict[str, Any]],
    temporal_issue_registry: List[Dict[str, Any]],
    candidate_claims: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Assemble deterministic claim and element temporal partial-order graphs.

    The graph is intentionally derived from the canonical temporal registries so
    packet readiness, proof bundles, and review payloads can all trace back to the
    same fact/relation/issue IDs.
    """
    facts = [
        _coerce_dict(fact)
        for fact in (temporal_fact_registry if isinstance(temporal_fact_registry, list) else [])
        if isinstance(fact, dict)
    ]
    relations = [
        _coerce_dict(relation)
        for relation in (temporal_relation_registry if isinstance(temporal_relation_registry, list) else [])
        if isinstance(relation, dict)
    ]
    issues = [
        _coerce_dict(issue)
        for issue in (temporal_issue_registry if isinstance(temporal_issue_registry, list) else [])
        if isinstance(issue, dict)
    ]
    facts_by_id = {
        _normalize_text(fact.get("fact_id") or fact.get("temporal_fact_id") or ""): fact
        for fact in facts
        if _normalize_text(fact.get("fact_id") or fact.get("temporal_fact_id") or "")
    }

    claim_labels_by_key: Dict[str, str] = {}
    for claim in candidate_claims if isinstance(candidate_claims, list) else []:
        if not isinstance(claim, dict):
            continue
        label = _normalize_text(claim.get("claim_type") or claim.get("label") or claim.get("claim_id") or "")
        key = _normalize_scope_key(label)
        if key:
            claim_labels_by_key.setdefault(key, label)
    for record in [*facts, *relations, *issues]:
        for claim_key in _temporal_record_claim_keys(record):
            claim_labels_by_key.setdefault(claim_key, claim_key)
    if not claim_labels_by_key and facts:
        claim_labels_by_key["unscoped_claim"] = "unscoped_claim"

    single_claim_key = next(iter(claim_labels_by_key)) if len(claim_labels_by_key) == 1 else ""
    claim_graphs: Dict[str, Dict[str, Any]] = {}
    aggregate_fact_ids: List[str] = []
    aggregate_relation_ids: List[str] = []
    aggregate_issue_ids: List[str] = []

    for claim_key in sorted(claim_labels_by_key):
        claim_type = claim_labels_by_key[claim_key]
        selected_fact_ids = {
            _normalize_text(fact.get("fact_id") or fact.get("temporal_fact_id") or "")
            for fact in facts
            if (
                claim_key in _temporal_record_claim_keys(fact)
                or (single_claim_key == claim_key and not _temporal_record_claim_keys(fact))
            )
            and _normalize_text(fact.get("fact_id") or fact.get("temporal_fact_id") or "")
        }
        selected_relations: List[Dict[str, Any]] = []
        for relation in relations:
            relation_claim_keys = _temporal_record_claim_keys(relation)
            source_fact_id = _normalize_text(relation.get("source_fact_id") or relation.get("source_temporal_fact_id") or "")
            target_fact_id = _normalize_text(relation.get("target_fact_id") or relation.get("target_temporal_fact_id") or "")
            relation_matches_claim = claim_key in relation_claim_keys or (single_claim_key == claim_key and not relation_claim_keys)
            relation_touches_claim_fact = bool(selected_fact_ids & {source_fact_id, target_fact_id})
            if relation_matches_claim or relation_touches_claim_fact:
                selected_relations.append(relation)
                if source_fact_id:
                    selected_fact_ids.add(source_fact_id)
                if target_fact_id:
                    selected_fact_ids.add(target_fact_id)

        selected_facts = [
            facts_by_id[fact_id]
            for fact_id in sorted(selected_fact_ids)
            if fact_id in facts_by_id
        ]
        selected_fact_labels = {
            _normalize_text(fact.get("text") or fact.get("event_label") or "").lower()
            for fact in selected_facts
            if _normalize_text(fact.get("text") or fact.get("event_label") or "")
        }
        selected_issues: List[Dict[str, Any]] = []
        for issue in issues:
            issue_claim_keys = _temporal_record_claim_keys(issue)
            issue_fact_ids = {
                _normalize_text(fact_id)
                for fact_id in _coerce_list(issue.get("fact_ids"))
                if _normalize_text(fact_id)
            }
            issue_node_labels = {
                _normalize_text(issue.get("left_node_name") or "").lower(),
                _normalize_text(issue.get("right_node_name") or "").lower(),
            }
            issue_node_labels.discard("")
            issue_matches_claim = claim_key in issue_claim_keys or (single_claim_key == claim_key and not issue_claim_keys)
            if (
                issue_matches_claim
                or (issue_fact_ids and bool(issue_fact_ids & selected_fact_ids))
                or (issue_node_labels and bool(issue_node_labels & selected_fact_labels))
            ):
                selected_issues.append(issue)

        element_keys: Dict[str, str] = {}
        for record in [*selected_facts, *selected_relations, *selected_issues]:
            for element_key in _temporal_record_element_keys(record):
                element_keys.setdefault(element_key, element_key)

        element_graphs: Dict[str, Dict[str, Any]] = {}
        for element_key in sorted(element_keys):
            element_seed_fact_ids = {
                _normalize_text(fact.get("fact_id") or fact.get("temporal_fact_id") or "")
                for fact in selected_facts
                if element_key in _temporal_record_element_keys(fact)
                and _normalize_text(fact.get("fact_id") or fact.get("temporal_fact_id") or "")
            }
            element_relations: List[Dict[str, Any]] = []
            for relation in selected_relations:
                source_fact_id = _normalize_text(relation.get("source_fact_id") or relation.get("source_temporal_fact_id") or "")
                target_fact_id = _normalize_text(relation.get("target_fact_id") or relation.get("target_temporal_fact_id") or "")
                if element_key in _temporal_record_element_keys(relation) or element_seed_fact_ids & {source_fact_id, target_fact_id}:
                    element_relations.append(relation)
                    if source_fact_id:
                        element_seed_fact_ids.add(source_fact_id)
                    if target_fact_id:
                        element_seed_fact_ids.add(target_fact_id)
            element_facts = [
                facts_by_id[fact_id]
                for fact_id in sorted(element_seed_fact_ids)
                if fact_id in facts_by_id
            ]
            element_fact_labels = {
                _normalize_text(fact.get("text") or fact.get("event_label") or "").lower()
                for fact in element_facts
                if _normalize_text(fact.get("text") or fact.get("event_label") or "")
            }
            element_issues = []
            for issue in selected_issues:
                issue_fact_ids = {
                    _normalize_text(fact_id)
                    for fact_id in _coerce_list(issue.get("fact_ids"))
                    if _normalize_text(fact_id)
                }
                issue_node_labels = {
                    _normalize_text(issue.get("left_node_name") or "").lower(),
                    _normalize_text(issue.get("right_node_name") or "").lower(),
                }
                issue_node_labels.discard("")
                if (
                    element_key in _temporal_record_element_keys(issue)
                    or (issue_fact_ids and bool(issue_fact_ids & element_seed_fact_ids))
                    or (issue_node_labels and bool(issue_node_labels & element_fact_labels))
                ):
                    element_issues.append(issue)
            if not element_facts and not element_relations and not element_issues:
                continue
            element_graphs[element_key] = _build_temporal_graph_record(
                graph_id=f"claim_temporal_graph:{claim_key}:{element_key}",
                claim_type=claim_type,
                element_id=element_key,
                element_label=element_keys[element_key],
                facts=element_facts,
                relations=element_relations,
                issues=element_issues,
            )

        claim_graph = _build_temporal_graph_record(
            graph_id=f"claim_temporal_graph:{claim_key}",
            claim_type=claim_type,
            facts=selected_facts,
            relations=selected_relations,
            issues=selected_issues,
        )
        claim_graph["elements"] = element_graphs
        claim_graphs[claim_key] = claim_graph
        for fact_id in claim_graph.get("fact_ids", []):
            if fact_id not in aggregate_fact_ids:
                aggregate_fact_ids.append(fact_id)
        for relation_id in claim_graph.get("relation_ids", []):
            if relation_id not in aggregate_relation_ids:
                aggregate_relation_ids.append(relation_id)
        for issue_id in claim_graph.get("issue_ids", []):
            if issue_id not in aggregate_issue_ids:
                aggregate_issue_ids.append(issue_id)

    return {
        "contract_version": "claim_temporal_graph_assembly.v1",
        "claim_count": len(claim_graphs),
        "claims": claim_graphs,
        "claim_keys": list(claim_graphs.keys()),
        "fact_ids": aggregate_fact_ids,
        "relation_ids": aggregate_relation_ids,
        "issue_ids": aggregate_issue_ids,
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
                "epistemic_class": _normalize_text(entity.attributes.get("epistemic_class") or "") or None,
                "narrative_kind": _normalize_text(entity.attributes.get("narrative_kind") or "") or None,
            }
        )
    return candidates


def _user_assertion_payload(provenance: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(provenance, Mapping):
        return None
    payload = provenance.get("user_assertion")
    if not isinstance(payload, Mapping) or not _normalize_text(payload.get("contract_version") or ""):
        return None
    return user_assertion_from_mapping(payload).as_dict()


def _project_user_assertion(provenance: Any, *, legacy_ref: str, expected_text: Optional[str] = None) -> Dict[str, Any]:
    """Project an assertion envelope. Records without one keep the legacy case-file shape."""
    envelope_payload = _user_assertion_payload(provenance)
    if envelope_payload is None:
        return {
            "source_kind": "knowledge_graph_entity",
            "source_ref": legacy_ref,
            "status": "accepted",
            "assertion_status": "unverified",
            "source_span_refs": [],
        }
    envelope = user_assertion_from_mapping(envelope_payload)
    if (expected_text is not None and envelope.is_asserted_user_fact
            and " ".join(expected_text.split()) != " ".join(envelope.source_span_text.split())):
        envelope = replace(envelope, record_type="unverified_candidate", source_kind="unverified",
            assertion_status="unverified", deficiencies=("unsupported_extracted_content",))
    identity = envelope.source_identity
    source_kind = envelope.source_kind if envelope.is_asserted_user_fact else (envelope.record_type or envelope.source_kind or "unverified")
    if envelope.is_asserted_user_fact:
        status = envelope.assertion_status
    elif envelope.record_type == "legal_text":
        status = "legal_text"
    elif envelope.record_type in {"model_suggestion", "inferred_claim_label"}:
        status = "suggestion"
    else:
        status = "unverified"
    span_refs: List[Dict[str, Any]] = []
    if envelope.source_span_start is not None and envelope.source_span_end is not None:
        span_refs.append(
            {
                "kind": "user_source_span",
                "source_kind": source_kind,
                "source_id": identity,
                "start": envelope.source_span_start,
                "end": envelope.source_span_end,
                "source_hash": envelope.source_hash,
                "text": envelope.source_span_text,
                "assertion_status": status,
                "stable_id": envelope.stable_id,
            }
        )
    return {
        "source_kind": source_kind,
        "source_ref": identity if envelope.is_asserted_user_fact and identity else legacy_ref,
        "status": status,
        "assertion_status": status,
        "extractor_version": envelope.extractor_version,
        "stable_id": envelope.stable_id,
        "source_hash": envelope.source_hash,
        "source_id": envelope.source_id,
        "message_id": envelope.message_id,
        "document_id": envelope.document_id,
        "source_span": {
            "start": envelope.source_span_start,
            "end": envelope.source_span_end,
            "text": envelope.source_span_text,
            "unit": "byte",
        },
        "source_span_refs": span_refs,
        "user_assertion": envelope.as_dict(),
        "source_assertions": [user_assertion_from_mapping(item).as_dict()
            for item in (provenance.get("user_assertions") or [])
            if isinstance(item, Mapping) and user_assertion_from_mapping(item).is_asserted_user_fact],
        "record_type": envelope.record_type,
        "contract_version": envelope.contract_version,
        "jurisdiction": envelope.jurisdiction,
        "actor": envelope.actor,
        "asserted_name": envelope.name,
        "asserted_event_date": envelope.event_date,
    }


def build_canonical_facts(knowledge_graph) -> List[Dict[str, Any]]:
    """Build initial canonical facts from fact entities already extracted into the graph."""
    if knowledge_graph is None:
        return []

    canonical_facts: List[Dict[str, Any]] = []
    for entity in knowledge_graph.get_entities_by_type("fact"):
        fact_text = _normalize_text(entity.attributes.get("description") or entity.name)
        if not fact_text:
            continue
        provenance_projection = _project_user_assertion(getattr(entity, "provenance", {}), legacy_ref=entity.id,
                                                       expected_text=fact_text)
        existing_span_refs = _coerce_provenance_refs(entity.attributes.get("source_span_refs"))
        provenance_projection["source_span_refs"] = _coerce_provenance_refs(
            existing_span_refs + list(provenance_projection.get("source_span_refs") or [])
        )
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
                    "confidence": float(entity.confidence),
                    "epistemic_class": _normalize_text(entity.attributes.get("epistemic_class") or "") or None,
                    "value_status": _normalize_text(entity.attributes.get("value_status") or "") or None,
                    "needs_corroboration": entity.confidence < 0.85,
                    "corroboration_priority": "high" if entity.confidence < 0.7 else "medium",
                    "materiality": "medium",
                    "fact_participants": _coerce_dict(entity.attributes.get("fact_participants")),
                    "event_support_refs": _unique_normalized_strings(entity.attributes.get("event_support_refs") or []),
                    "source_artifact_ids": _unique_normalized_strings(entity.attributes.get("source_artifact_ids") or []),
                    "testimony_record_ids": _unique_normalized_strings(entity.attributes.get("testimony_record_ids") or []),
                    "contradiction_group_id": None,
                    **provenance_projection,
                }
            )
        )
    return canonical_facts


def build_canonical_fact_edges(knowledge_graph) -> List[Dict[str, Any]]:
    """Project graph edges with their assertion envelopes.

    source_id and target_id stay node endpoints. User message and document
    identity stays inside the assertion envelope.
    """
    if knowledge_graph is None:
        return []
    edges: List[Dict[str, Any]] = []
    relationships = getattr(knowledge_graph, "relationships", {})
    relationship_values = relationships.values() if isinstance(relationships, Mapping) else relationships
    for relationship in relationship_values:
        # Revalidate mutable graph records before projecting their assertion.
        serializer = getattr(relationship, "to_dict", None)
        serialized = serializer() if callable(serializer) else {}
        provenance = serialized.get("provenance", getattr(relationship, "provenance", {}))
        projection = _project_user_assertion(
            provenance,
            legacy_ref=str(getattr(relationship, "id", "") or ""),
        )
        edges.append(
            {
                **projection,
                "relationship_id": getattr(relationship, "id", ""),
                "source_id": getattr(relationship, "source_id", ""),
                "target_id": getattr(relationship, "target_id", ""),
                "relation_type": getattr(relationship, "relation_type", ""),
                "confidence": getattr(relationship, "confidence", None),
            }
        )
    return edges


def restore_entity_from_canonical_fact(fact: Mapping[str, Any]):
    """Rebuild a fact entity from a canonical projection without inventing fields."""
    from complaint_phases.knowledge_graph import Entity

    record = dict(fact or {})
    assertion = record.get("user_assertion") if isinstance(record.get("user_assertion"), Mapping) else {}
    attributes = {
        "description": record.get("text") or "",
        "fact_type": record.get("fact_type") or "general",
        "predicate_family": record.get("predicate_family") or "",
        "event_label": record.get("event_label") or "",
        "event_id": record.get("event_id") or "",
        "event_date_or_range": record.get("event_date_or_range") or "",
        "source_span_refs": list(record.get("source_span_refs") or []),
    }
    if isinstance(record.get("sequence_index"), int):
        attributes["sequence_index"] = record.get("sequence_index")
    provenance: Dict[str, Any] = {}
    if assertion:
        provenance["user_assertion"] = dict(assertion)
    history = record.get("source_assertions")
    if isinstance(history, list):
        provenance["user_assertions"] = [user_assertion_from_mapping(item).as_dict()
            for item in history if isinstance(item, Mapping) and user_assertion_from_mapping(item).is_asserted_user_fact]
    confidence = record.get("confidence")
    return Entity(
        id=str(record.get("fact_id") or record.get("stable_id") or ""),
        type="fact",
        name=str(record.get("name") or record.get("text") or ""),
        attributes=attributes,
        confidence=float(0.0 if confidence is None else confidence),
        source="complaint",
        provenance=provenance,
    )


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
    canonical_facts = _coerce_list(case_file.get("canonical_facts"))
    proof_leads = _coerce_list(case_file.get("proof_leads"))
    timeline_consistency_summary = _coerce_dict(case_file.get("timeline_consistency_summary"))
    temporal_issue_registry = _coerce_list(case_file.get("temporal_issue_registry"))
    source_text = _normalize_text(case_file.get("source_complaint_text") or "").lower()
    contradiction_queue = _coerce_list(case_file.get("contradiction_queue"))
    blocker_follow_up_summary = _coerce_dict(case_file.get("blocker_follow_up_summary"))
    open_item_by_id: Dict[str, Dict[str, Any]] = {}

    blocking_rank = {"blocking": 0, "important": 1}
    support_rank = {"intake_clarification": 0, "testimony": 1, "evidence": 2, "manual_review": 3}
    strategy_rank = {
        "capture_hearing_timeline": 0,
        "capture_appeal_rights_timeline": 1,
        "capture_response_timeline": 2,
        "capture_staff_identity": 3,
        "capture_causation_sequence": 4,
        "capture_exact_date_for_timeline_fact": 5,
        "anchor_relative_timeline_fact": 6,
        "capture_policy_document_evidence": 7,
        "capture_file_evidence": 8,
        "targeted_blocker_follow_up": 9,
        "satisfy_claim_element": 10,
    }
    kind_rank = {
        "blocker_follow_up": 0,
        "timeline_anchor_gap": 1,
        "anchor_gap": 2,
        "temporal_issue_gap": 3,
        "claim_element_gap": 4,
        "contradiction": 5,
        "evidence_modality_gap": 6,
        "section_gap": 7,
    }

    def _sort_key(item: Dict[str, Any]) -> tuple[int, int, int, int, str]:
        return (
            blocking_rank.get(_normalize_text(item.get("blocking_level") or "").lower(), 2),
            kind_rank.get(_normalize_text(item.get("kind") or "").lower(), 50),
            strategy_rank.get(_normalize_text(item.get("next_question_strategy") or "").lower(), 50),
            support_rank.get(_normalize_text(item.get("recommended_support_kind") or "").lower(), 10),
            _normalize_text(item.get("open_item_id") or ""),
        )

    def _add_item(item: Dict[str, Any]) -> None:
        normalized_id = _normalize_text(item.get("open_item_id") or "")
        if not normalized_id:
            return
        target_claim_type = _normalize_text(item.get("target_claim_type") or "")
        target_element_id = _normalize_text(item.get("target_element_id") or "")
        evidence_classes = _unique_normalized_strings(item.get("evidence_classes") or [])
        # Build target_element_metadata: look up the matching element in candidate_claims so the
        # caller gets a richer object with label, blocking status, and evidence classes.
        resolved_element_metadata: Dict[str, Any] = {}
        if target_element_id and target_claim_type:
            for claim in candidate_claims:
                if not isinstance(claim, dict):
                    continue
                if _normalize_text(str(claim.get("claim_type") or "")).lower() != target_claim_type.lower():
                    continue
                for element in (claim.get("required_elements") or []):
                    if not isinstance(element, dict):
                        continue
                    if _normalize_text(str(element.get("element_id") or "")).lower() == target_element_id.lower():
                        resolved_element_metadata = {
                            "element_id": _normalize_text(str(element.get("element_id") or "")),
                            "label": _normalize_text(str(element.get("label") or element.get("element_id") or "")),
                            "blocking": bool(element.get("blocking", True)),
                            "evidence_classes": _unique_normalized_strings(
                                evidence_classes + list(element.get("evidence_classes") or [])
                            ),
                            "claim_type": target_claim_type,
                        }
                        break
                if resolved_element_metadata:
                    break
        if not resolved_element_metadata and target_element_id:
            resolved_element_metadata = {
                "element_id": target_element_id,
                "label": target_element_id,
                "claim_type": target_claim_type,
                "evidence_classes": evidence_classes,
            }
        normalized_item = {
            **item,
            "open_item_id": normalized_id,
            "kind": _normalize_text(item.get("kind") or "gap").lower() or "gap",
            "status": "open",
            "blocking_level": _normalize_text(item.get("blocking_level") or "important").lower() or "important",
            "section": _normalize_text(item.get("section") or "general").lower() or "general",
            "reason": _normalize_text(item.get("reason") or "Follow-up required."),
            "target_claim_type": target_claim_type,
            "target_element_id": target_element_id,
            "target_claim_types": [target_claim_type] if target_claim_type else [],
            "target_element_ids": [target_element_id] if target_element_id else [],
            "target_element_metadata": resolved_element_metadata,
            "element_links": _normalize_intake_target_links(
                item.get("element_links"),
                claim_types=[target_claim_type] if target_claim_type else [],
                element_ids=[target_element_id] if target_element_id else [],
            ),
            "next_question_strategy": _normalize_text(item.get("next_question_strategy") or "targeted_blocker_follow_up").lower() or "targeted_blocker_follow_up",
            "recommended_support_kind": _normalize_text(item.get("recommended_support_kind") or "intake_clarification").lower() or "intake_clarification",
            "proof_path_status": _normalize_text(item.get("proof_path_status") or "missing").lower() or "missing",
        }
        existing = open_item_by_id.get(normalized_id)
        if existing is None or _sort_key(normalized_item) < _sort_key(existing):
            open_item_by_id[normalized_id] = normalized_item

    normalized_facts = [
        _normalize_canonical_fact_record(fact)
        for fact in canonical_facts
        if isinstance(fact, dict)
    ]
    fact_texts: List[str] = []
    hearing_fact_ids = set()
    hearing_dated_fact_ids = set()
    response_dated_fact_ids = set()
    staff_title_pattern = re.compile(r"\b(manager|supervisor|director|officer|specialist|coordinator|landlord|owner|hr)\b", flags=re.IGNORECASE)
    has_named_staff = _looks_like_staff_person_name(case_file.get("source_complaint_text") or "")
    has_staff_title = bool(staff_title_pattern.search(case_file.get("source_complaint_text") or ""))
    has_causation_sequence = _has_retaliation_causation_link(candidate_claims, normalized_facts, source_text)

    for index, fact in enumerate(normalized_facts, start=1):
        fact_dict = _coerce_dict(fact)
        fact_id = _normalize_text(fact_dict.get("fact_id") or "") or f"timeline_fact_{index}"
        text_value = _normalize_text(fact_dict.get("text") or fact_dict.get("event_label") or "").lower()
        predicate_family = _normalize_text(fact_dict.get("predicate_family") or "").lower()
        temporal_context = _coerce_dict(fact_dict.get("temporal_context"))
        start_date = _normalize_text(temporal_context.get("start_date") or "")
        fact_texts.append(text_value)
        if any(token in text_value for token in ("grievance", "hearing", "appeal")) or predicate_family == "hearing_process":
            hearing_fact_ids.add(fact_id)
            if start_date:
                hearing_dated_fact_ids.add(fact_id)
        if predicate_family == "response_timeline" or any(token in text_value for token in ("respond", "denied", "approved", "ignored", "no response", "decision")):
            if start_date:
                response_dated_fact_ids.add(fact_id)
        if _looks_like_staff_person_name(_normalize_text(fact_dict.get("text") or fact_dict.get("event_label") or "")):
            has_named_staff = True
        if staff_title_pattern.search(_normalize_text(fact_dict.get("text") or fact_dict.get("event_label") or "")):
            has_staff_title = True

    legal_context = case_file.get("legal_context")
    if not isinstance(legal_context, dict):
        legal_context = refresh_explicit_legal_context(case_file)
        case_file["legal_context"] = legal_context
    for question in _coerce_list(legal_context.get("questions")):
        question_dict = _coerce_dict(question)
        question_id = _normalize_text(question_dict.get("question_id") or "")
        if not question_id:
            continue
        _add_item(
            {
                "open_item_id": f"legal_context:{question_id}",
                "kind": "legal_context_gap",
                "blocking_level": "blocking" if question_dict.get("field") == "jurisdiction" else "important",
                "section": "legal_context",
                "reason": _normalize_text(question_dict.get("prompt") or "Legal context is unresolved."),
                "next_question_strategy": f"ask_{_normalize_text(question_dict.get('field') or 'legal_context')}",
                "recommended_support_kind": "intake_clarification",
                "proof_path_status": "missing",
                "question": question_dict,
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
            evidence_classes = list(element_dict.get("evidence_classes", []) or [])
            next_strategy = "satisfy_claim_element"
            if element_id in {"grievance_hearing", "hearing_request_timing"}:
                next_strategy = "capture_hearing_timeline"
            elif element_id in {"appeal_rights", "appeal_timing"}:
                next_strategy = "capture_appeal_rights_timeline"
            elif element_id in {"causation", "retaliation_causation_sequence"}:
                next_strategy = "capture_causation_sequence"
            _add_item(
                {
                    "open_item_id": f"element:{claim_type}:{element_id}",
                    "kind": "claim_element_gap",
                    "blocking_level": "blocking" if bool(element_dict.get("blocking", False)) else "important",
                    "section": "claim_elements",
                    "reason": f"{claim_label} is still missing {element_label}.",
                    "target_claim_type": claim_type,
                    "target_element_id": element_id,
                    "next_question_strategy": next_strategy,
                    "evidence_classes": evidence_classes,
                    "recommended_support_kind": "testimony" if any("testimony" in str(item).lower() for item in evidence_classes) else "evidence",
                    "proof_path_status": "missing",
                }
            )

    for contradiction in contradiction_queue:
        contradiction_dict = _coerce_dict(contradiction)
        if _normalize_text(contradiction_dict.get("status") or "open").lower() == "resolved":
            continue
        contradiction_id = _normalize_text(contradiction_dict.get("contradiction_id") or "contradiction")
        resolution_lane = _normalize_text(
            contradiction_dict.get("recommended_resolution_lane") or "clarify_with_complainant"
        ).lower() or "clarify_with_complainant"
        external_corroboration_required = bool(contradiction_dict.get("external_corroboration_required", False))
        _add_item(
            {
                "open_item_id": f"contradiction:{contradiction_id}",
                "kind": "contradiction",
                "blocking_level": _normalize_text(contradiction_dict.get("severity") or "important").lower() or "important",
                "section": "contradictions",
                "reason": f"Resolve contradiction about {_normalize_text(contradiction_dict.get('topic') or 'intake contradiction')}.",
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
        section = _normalize_text(blocker_dict.get("section") or "chronology").lower() or "chronology"
        _add_item(
            {
                "open_item_id": f"blocker:{blocker_id or len(open_item_by_id) + 1}",
                "kind": "blocker_follow_up",
                "blocking_level": "blocking",
                "section": section,
                "reason": _normalize_text(blocker_dict.get("reason") or "Critical intake blocker requires follow-up."),
                "target_claim_type": _normalize_text(blocker_dict.get("target_claim_type") or ""),
                "target_element_id": _normalize_text(blocker_dict.get("target_element_id") or ""),
                "next_question_strategy": _normalize_text(
                    blocker_dict.get("next_question_strategy")
                    or blocker_dict.get("question_strategy")
                    or "targeted_blocker_follow_up"
                ).lower() or "targeted_blocker_follow_up",
                "recommended_support_kind": _normalize_text(
                    blocker_dict.get("recommended_support_kind")
                    or ("evidence" if section in {"proof_leads", "chronology"} else "intake_clarification")
                ).lower() or "intake_clarification",
                "proof_path_status": _normalize_text(blocker_dict.get("proof_path_status") or "missing").lower() or "missing",
                "blocker_tags": _unique_normalized_strings(blocker_dict.get("blocker_tags") or []),
                "primary_objective": _normalize_text(blocker_dict.get("primary_objective") or ""),
                "blocker_objectives": _unique_normalized_strings(blocker_dict.get("blocker_objectives") or []),
                "extraction_targets": _unique_normalized_strings(blocker_dict.get("extraction_targets") or []),
                "workflow_phases": _unique_normalized_strings(blocker_dict.get("workflow_phases") or []),
                "issue_family": _normalize_text(blocker_dict.get("issue_family") or ""),
            }
        )

    for issue in temporal_issue_registry:
        issue_dict = _coerce_dict(issue)
        issue_status = _normalize_text(
            issue_dict.get("current_resolution_status") or issue_dict.get("status") or "open"
        ).lower()
        if issue_status == "resolved":
            continue
        issue_id = _normalize_text(issue_dict.get("issue_id") or "")
        if not issue_id:
            continue
        issue_type = _normalize_text(issue_dict.get("issue_type") or "").lower()
        resolution_lane = _normalize_text(
            issue_dict.get("recommended_resolution_lane")
            or ("anchor_relative_timeline_fact" if issue_type == "relative_only_ordering" else "capture_exact_date_for_timeline_fact")
        ).lower() or "clarify_with_complainant"
        _add_item(
            {
                "open_item_id": f"temporal_issue:{issue_id}",
                "kind": "temporal_issue_gap",
                "blocking_level": _normalize_text(issue_dict.get("severity") or "blocking").lower() or "blocking",
                "section": "chronology",
                "reason": _normalize_text(issue_dict.get("summary") or "Timeline sequencing still needs anchoring."),
                "next_question_strategy": resolution_lane,
                "recommended_support_kind": _contradiction_support_kind(resolution_lane),
                "proof_path_status": "relative_only" if issue_type == "relative_only_ordering" else "missing",
                "issue_type": issue_type,
                "fact_ids": _unique_normalized_strings(issue_dict.get("fact_ids") or []),
                "relative_markers": _unique_normalized_strings(issue_dict.get("relative_markers") or []),
            }
        )

    missing_temporal_fact_ids = _unique_normalized_strings(
        timeline_consistency_summary.get("missing_temporal_fact_ids") or []
    )
    relative_only_fact_ids = set(
        _unique_normalized_strings(timeline_consistency_summary.get("relative_only_fact_ids") or [])
    )
    for fact_id in missing_temporal_fact_ids:
        is_relative_only = fact_id in relative_only_fact_ids
        _add_item(
            {
                "open_item_id": f"timeline_fact:{fact_id}",
                "kind": "timeline_anchor_gap",
                "blocking_level": "blocking",
                "section": "chronology",
                "reason": (
                    f"Timeline fact {fact_id} only has relative ordering and needs anchoring."
                    if is_relative_only
                    else f"Timeline fact {fact_id} needs an exact date anchor."
                ),
                "next_question_strategy": "anchor_relative_timeline_fact" if is_relative_only else "capture_exact_date_for_timeline_fact",
                "recommended_support_kind": "intake_clarification",
                "proof_path_status": "relative_only" if is_relative_only else "missing",
                "target_fact_id": fact_id,
            }
        )

    weak_claim_types = {"housing_discrimination", "hacc_research_engine"}
    active_weak_claim_types = {
        _normalize_text(_coerce_dict(claim).get("claim_type") or "").lower()
        for claim in candidate_claims
        if isinstance(claim, dict)
    }.intersection(weak_claim_types)
    if active_weak_claim_types:
        lead_texts = [
            f"{_normalize_text(_coerce_dict(lead).get('lead_type') or '').lower()} {_normalize_text(_coerce_dict(lead).get('description') or '').lower()}"
            for lead in proof_leads
            if isinstance(lead, dict)
        ]
        has_policy_document = any(any(token in lead_text for token in ("policy_document", "policy", "handbook", "procedure")) for lead_text in lead_texts)
        has_file_evidence = any(any(token in lead_text for token in ("file_evidence", "file", "attachment", "record", "document")) for lead_text in lead_texts)
        primary_claim_type = sorted(active_weak_claim_types)[0]
        if not has_policy_document:
            _add_item(
                {
                    "open_item_id": "evidence_modality:policy_document",
                    "kind": "evidence_modality_gap",
                    "blocking_level": "important",
                    "section": "proof_leads",
                    "reason": "Add a policy_document source with policy language, issue date, and issuing authority.",
                    "target_claim_type": primary_claim_type,
                    "next_question_strategy": "capture_policy_document_evidence",
                    "recommended_support_kind": "evidence",
                    "proof_path_status": "missing",
                }
            )
        if not has_file_evidence:
            _add_item(
                {
                    "open_item_id": "evidence_modality:file_evidence",
                    "kind": "evidence_modality_gap",
                    "blocking_level": "important",
                    "section": "proof_leads",
                    "reason": "Add file_evidence records with document title, date, source, and custodian details.",
                    "target_claim_type": primary_claim_type,
                    "next_question_strategy": "capture_file_evidence",
                    "recommended_support_kind": "evidence",
                    "proof_path_status": "missing",
                }
            )

    hearing_referenced = (
        any(token in source_text for token in ("grievance hearing", "hearing request", "hearing", "appeal"))
        or any(any(token in text for token in ("grievance", "hearing", "appeal")) for text in fact_texts)
    )
    if hearing_referenced and not hearing_dated_fact_ids:
        _add_item(
            {
                "open_item_id": "anchor:grievance_hearing",
                "kind": "anchor_gap",
                "blocking_level": "blocking",
                "section": "chronology",
                "reason": "Confirm grievance_hearing request date, request method, decision-maker name/title, and source record.",
                "target_element_id": "grievance_hearing",
                "next_question_strategy": "capture_hearing_timeline",
                "recommended_support_kind": "intake_clarification",
                "proof_path_status": "missing",
            }
        )
    if hearing_referenced and not response_dated_fact_ids:
        _add_item(
            {
                "open_item_id": "anchor:appeal_rights",
                "kind": "anchor_gap",
                "blocking_level": "blocking",
                "section": "chronology",
                "reason": "Confirm appeal_rights notice date, filing deadline, agency response date, and supporting record.",
                "target_element_id": "appeal_rights",
                "next_question_strategy": "capture_appeal_rights_timeline",
                "recommended_support_kind": "intake_clarification",
                "proof_path_status": "missing",
            }
        )

    if has_named_staff and not has_staff_title:
        _add_item(
            {
                "open_item_id": "actors:staff_name_title_mapping",
                "kind": "anchor_gap",
                "blocking_level": "blocking",
                "section": "actors",
                "reason": "Map each named staff person to role/title and decision authority.",
                "next_question_strategy": "capture_staff_identity",
                "recommended_support_kind": "intake_clarification",
                "proof_path_status": "missing",
            }
        )

    if not has_causation_sequence:
        _add_item(
            {
                "open_item_id": "conduct:causation_sequence",
                "kind": "anchor_gap",
                "blocking_level": "blocking",
                "section": "conduct",
                "reason": "Capture sequence linking protected activity, actor knowledge, adverse action, and timing.",
                "next_question_strategy": "capture_causation_sequence",
                "recommended_support_kind": "intake_clarification",
                "proof_path_status": "missing",
            }
        )

    section_strategy_map = {
        "chronology": "fill_chronology_with_exact_dates",
        "actors": "fill_actors_and_titles",
        "conduct": "fill_conduct_and_causation_sequence",
        "claim_elements": "satisfy_claim_element",
        "proof_leads": "fill_evidence_paths",
    }
    concrete_sections = {
        _normalize_text(item.get("section") or "").lower()
        for item in open_item_by_id.values()
        if _normalize_text(item.get("kind") or "").lower() != "section_gap"
    }
    for section_name, section in sections.items():
        normalized_section_name = _normalize_text(section_name).lower()
        section_dict = _coerce_dict(section)
        status = _normalize_text(section_dict.get("status")).lower() or "missing"
        if status == "complete" or normalized_section_name in concrete_sections:
            continue
        missing_items = _coerce_list(section_dict.get("missing_items"))
        _add_item(
            {
                "open_item_id": f"section:{normalized_section_name}",
                "kind": "section_gap",
                "blocking_level": "blocking" if normalized_section_name in {"chronology", "actors", "conduct", "claim_elements"} else "important",
                "section": normalized_section_name,
                "reason": "; ".join(missing_items) or f"{normalized_section_name} is incomplete",
                "next_question_strategy": section_strategy_map.get(normalized_section_name, f"fill_{normalized_section_name}"),
                "recommended_support_kind": "evidence" if normalized_section_name == "proof_leads" else "intake_clarification",
                "proof_path_status": "missing",
            }
        )

    deduped_items = list(open_item_by_id.values())
    deduped_items.sort(key=_sort_key)
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

    def _has_structured_artifact_backed_sequence(fact: Dict[str, Any], families: set[str], tokens: tuple[str, ...]) -> bool:
        predicate_family = _normalize_text(fact.get("predicate_family") or "").lower()
        text_value = _fact_text(fact)
        structured_group = _normalize_text(fact.get("structured_timeline_group") or "")
        sequence_index = fact.get("sequence_index")
        source_artifact_ids = _unique_normalized_strings(fact.get("source_artifact_ids") or [])
        event_support_refs = _unique_normalized_strings(fact.get("event_support_refs") or [])
        return bool(
            structured_group
            and isinstance(sequence_index, int)
            and (predicate_family in families or any(token in text_value for token in tokens))
            and (source_artifact_ids or event_support_refs)
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
    hearing_has_structured_sequence_support = any(
        _has_structured_artifact_backed_sequence(fact, {"hearing_process"}, ("hearing", "appeal", "grievance", "review"))
        for fact in hearing_facts
    )
    if hearing_reference and not hearing_has_date and not hearing_has_structured_sequence_support:
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
    response_has_structured_sequence_support = any(
        _has_structured_artifact_backed_sequence(fact, {"response_timeline"}, ("response", "responded", "replied", "denied", "approved", "ignored"))
        for fact in response_facts
    )
    if response_reference and not response_has_date and not response_has_structured_sequence_support:
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

    has_named_staff = _looks_like_staff_person_name(source_text or "") or any(
        _looks_like_staff_person_name(fact.get("text") or fact.get("event_label") or "")
        for fact in facts
    )
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


def _legal_context_helpers():
    from integrations.ipfs_datasets.legal import (
        apply_legal_context_update,
        classify_legal_date,
        empty_legal_context,
        questions_for_legal_context,
        resolve_explicit_jurisdiction,
    )
    return {
        "apply_legal_context_update": apply_legal_context_update,
        "classify_legal_date": classify_legal_date,
        "empty_legal_context": empty_legal_context,
        "questions_for_legal_context": questions_for_legal_context,
        "resolve_explicit_jurisdiction": resolve_explicit_jurisdiction,
    }


def extract_explicit_jurisdiction_from_text(text: Any) -> str:
    """Require an unambiguous affirmative statement, rather than the first hit."""
    helpers = _legal_context_helpers()
    raw = _normalize_text(text)
    if not raw:
        return "unknown"
    selected = set()
    uncertain = re.compile(
        r"\b(?:not|never|no|unsure|uncertain|whether|maybe|perhaps|might|could|"
        r"possibly|dispute|disputed|cited|claimed|claims|don't|doesn't|isn't)\b",
        re.IGNORECASE,
    )
    for clause in re.findall(r"[^.;!?\n]+[.;!?\n]?", raw):
        if clause.rstrip().endswith("?") or re.match(
            r"\s*(?:do|does|is|are|should|can|would|will|which|what|how|where|when)\b",
            clause, re.IGNORECASE,
        ) or uncertain.search(clause) or re.search(r"\bmay\s+(?:be|apply|govern)\b", clause, re.IGNORECASE):
            continue
        candidates = []
        if re.search(
            r"\bfederal\s+law\s+(?:applies|governs)\b|"
            r"\b(?:filed|pending)\s+in\s+(?:(?:a|the)\s+)?federal\s+court\b",
            clause, re.IGNORECASE,
        ):
            candidates.append("federal")
        labeled = re.search(r"\bjurisdiction\s*:\s*([A-Za-z][A-Za-z ]{1,40})", clause, re.IGNORECASE)
        if labeled:
            candidates.append(labeled.group(1).strip(" ."))
        candidates.extend(match.group(1).strip() for match in re.finditer(
            r"\b(?:under|pursuant to|state of|or|and)\s+(?:(?:under|pursuant to)\s+)?([A-Za-z][A-Za-z ]{1,30}?)\s+(?:law|statute|court)\b",
            clause, re.IGNORECASE,
        ))
        for candidate in candidates:
            resolved = helpers["resolve_explicit_jurisdiction"](candidate)
            if resolved != "unknown":
                selected.add(resolved)
    return next(iter(selected)) if len(selected) == 1 else "unknown"


def _extract_labeled_legal_date(text: str, labels: tuple[str, ...], role: str) -> Dict[str, Any] | None:
    helpers = _legal_context_helpers()
    for label in labels:
        match = re.search(rf"\b{label}\s*[: ]\s*([^.;\n]+)", text, flags=re.IGNORECASE)
        if match:
            return helpers["classify_legal_date"](match.group(1).strip(), role=role)
    return None


def derive_explicit_legal_context(intake_case_file: Dict[str, Any]) -> Dict[str, Any]:
    """Build legal context from explicit user text and dated facts."""
    helpers = _legal_context_helpers()
    case_file = _coerce_dict(intake_case_file)
    source_text = _normalize_text(case_file.get("source_complaint_text") or "")
    context = helpers["empty_legal_context"]()
    jurisdiction = extract_explicit_jurisdiction_from_text(source_text)
    context["jurisdiction"] = jurisdiction
    context["jurisdiction_explicit"] = jurisdiction != "unknown"
    context["status"] = "unknown" if jurisdiction == "unknown" else "explicit"

    applicable = _extract_labeled_legal_date(
        source_text,
        ("applicable law date", "law in effect on", "law applicable on"),
        "applicable_law_date",
    )
    if applicable:
        context["applicable_law_date"] = applicable
    filing = _extract_labeled_legal_date(
        source_text,
        ("filing date", "filed on", "reference date"),
        "filing_reference_date",
    )
    if filing:
        context["filing_reference_date"] = filing
    retrieval_raw = _normalize_text(
        case_file.get("corpus_retrieved_at") or case_file.get("corpus_retrieval_date") or ""
    )
    if retrieval_raw:
        context["corpus_retrieval_date"] = helpers["classify_legal_date"](
            retrieval_raw,
            role="corpus_retrieval_date",
        )

    event_dates: List[Dict[str, Any]] = []
    for fact in _coerce_list(case_file.get("canonical_facts")):
        if not isinstance(fact, dict):
            continue
        raw_event = _normalize_text(fact.get("event_date_or_range") or "")
        if not raw_event:
            continue
        event_dates.append(helpers["classify_legal_date"](raw_event, role="event_date"))
    context["event_dates"] = event_dates
    if len(event_dates) == 1:
        context["event_date"] = event_dates[0]
    context["questions"] = helpers["questions_for_legal_context"](
        context,
        selecting_rules=bool(_coerce_list(case_file.get("candidate_claims"))),
    )
    return context


def refresh_explicit_legal_context(intake_case_file: Dict[str, Any]) -> Dict[str, Any]:
    """Recompute context and invalidate selected rules when the user changes it."""
    helpers = _legal_context_helpers()
    case_file = _coerce_dict(intake_case_file)
    previous = case_file.get("legal_context")
    if not isinstance(previous, dict):
        previous = helpers["empty_legal_context"]()
    derived = derive_explicit_legal_context(case_file)
    overrides = _coerce_dict(case_file.get("legal_context_overrides"))
    # Presence, including an explicit blank, matters. Missing source context
    # cannot silently retain a previously selected jurisdiction or date.
    updates: Dict[str, Any] = {
        "jurisdiction": overrides.get("jurisdiction") if "jurisdiction" in overrides else derived.get("jurisdiction"),
    }
    for role in ("applicable_law_date", "event_date", "filing_reference_date", "corpus_retrieval_date"):
        if role in overrides:
            updates[role] = overrides.get(role)
        else:
            updates[role] = derived.get(role)
    if "event_dates" in overrides:
        updates["event_dates"] = overrides.get("event_dates")
    elif "event_date" in overrides:
        updates["event_dates"] = [overrides["event_date"]] if overrides["event_date"] else []
    else:
        updates["event_dates"] = derived.get("event_dates") or []
    proof = [
        item for item in _coerce_list(case_file.get("proof_leads"))
        if isinstance(item, dict)
    ]
    updated = helpers["apply_legal_context_update"](previous, updates, dependent_proof=proof)
    updated["questions"] = helpers["questions_for_legal_context"](
        updated,
        selecting_rules=bool(_coerce_list(case_file.get("candidate_claims"))),
    )
    # Ordinary intake refresh and mediator question refresh use this path too;
    # invalidation must reach the actual proof records, not only a nested copy.
    if updated.get("changed_fields"):
        invalidated = _coerce_list(updated.get("dependent_proof"))
        if len(invalidated) != len(proof) or not all(isinstance(item, dict) for item in invalidated):
            raise ValueError("Legal context changed the dependent proof projection shape")
        # The update preserves order/cardinality. Identity indexing would merge
        # distinct legacy records with absent or duplicate proof identifiers.
        case_file["proof_leads"] = [dict(item) for item in invalidated]
    case_file["legal_context"] = updated
    return updated


def apply_explicit_legal_context(intake_case_file: Dict[str, Any], **updates: Any) -> Dict[str, Any]:
    """Record user answers and drop rule applicability that depended on the old context."""
    case_file = _coerce_dict(intake_case_file)
    overrides = _coerce_dict(case_file.get("legal_context_overrides"))
    for key, value in updates.items():
        overrides[key] = value
    case_file["legal_context_overrides"] = overrides
    case_file["legal_context"] = refresh_explicit_legal_context(case_file)
    return case_file


def project_graph_revision_view(case_file: Dict[str, Any], knowledge_graph) -> Dict[str, Any]:
    """Expose narrative nodes, revisions, unknowns, and contradictions without dropping history."""
    if not isinstance(case_file, dict) or knowledge_graph is None:
        return case_file
    from complaint_phases.knowledge_graph import inspect_graph_revisions

    narrative_nodes = []
    unknowns = []
    contradictions = []
    support_edges = []
    for entity in getattr(knowledge_graph, "entities", {}).values():
        attributes = entity.attributes if isinstance(getattr(entity, "attributes", None), dict) else {}
        epistemic_class = _normalize_text(attributes.get("epistemic_class") or "") or None
        if attributes.get("narrative_source_linked") or attributes.get("narrative_kind"):
            envelope = _user_assertion_payload(getattr(entity, "provenance", {})) or {}
            narrative_nodes.append({
                "entity_id": entity.id,
                "entity_type": entity.type,
                "narrative_kind": attributes.get("narrative_kind"),
                "name": entity.name,
                "epistemic_class": epistemic_class or "user_allegation",
                "stable_id": envelope.get("stable_id"),
                "source_span": envelope.get("source_span"),
                "source_hash": envelope.get("source_hash"),
                "statement": envelope.get("source_span_text") or attributes.get("description") or entity.name,
            })
        value_status = _normalize_text(attributes.get("value_status") or "")
        if value_status == "unknown":
            unknowns.append({"entity_id": entity.id, "statement": attributes.get("description") or entity.name, "value_status": "unknown"})
        if value_status == "contradiction":
            contradictions.append({"entity_id": entity.id, "statement": attributes.get("description") or entity.name, "value_status": "contradiction"})
    ledger = knowledge_graph.factual_ledger() if hasattr(knowledge_graph, "factual_ledger") else {}
    for conflict in ledger.get("conflicts") or []:
        if isinstance(conflict, dict):
            contradictions.append(dict(conflict))
    for revision in ledger.get("revisions") or []:
        if not isinstance(revision, dict):
            continue
        revision_status = _normalize_text(revision.get("value_status") or "")
        statement = revision.get("statement") or (revision.get("provenance") or {}).get("statement")
        if revision_status == "unknown" and statement:
            unknowns.append({
                "entity_id": revision.get("entity_id") or "",
                "statement": statement,
                "value_status": "unknown",
                "event_id": revision.get("event_id") or "",
            })
        if revision_status == "contradiction" and statement:
            contradictions.append({
                "entity_id": revision.get("entity_id") or "",
                "statement": statement,
                "value_status": "contradiction",
                "event_id": revision.get("event_id") or "",
            })
    for relationship in getattr(knowledge_graph, "relationships", {}).values():
        attributes = relationship.attributes if isinstance(getattr(relationship, "attributes", None), dict) else {}
        if attributes.get("epistemic_class"):
            support_edges.append({
                "relationship_id": relationship.id,
                "relation_type": relationship.relation_type,
                "epistemic_class": attributes.get("epistemic_class"),
                "source_id": relationship.source_id,
                "target_id": relationship.target_id,
                "statement": attributes.get("statement"),
            })
    case_file["graph_revisions"] = inspect_graph_revisions(knowledge_graph)
    case_file["narrative_source_nodes"] = narrative_nodes
    case_file["visible_unknowns"] = unknowns
    case_file["visible_contradictions"] = contradictions
    case_file["epistemic_support_edges"] = support_edges
    return case_file


def build_intake_case_file(knowledge_graph, complaint_text: str = "") -> Dict[str, Any]:
    """Build the initial structured intake case file from current graph state."""
    candidate_claims = [
        _coerce_dict(claim)
        for claim in build_candidate_claims(knowledge_graph)
        if isinstance(claim, dict)
    ]
    canonical_facts = _dedupe_structured_timeline_groups(_enrich_canonical_facts_with_relative_anchor_dates(
        [
            _normalize_canonical_fact_record(fact)
            for fact in build_canonical_facts(knowledge_graph)
            if isinstance(fact, dict)
        ]
    ))
    canonical_facts = _ensure_stable_intake_record_ids(
        canonical_facts,
        id_key="fact_id",
        prefix="fact",
    )
    proof_leads = [
        _normalize_proof_lead_record(lead)
        for lead in build_proof_leads(knowledge_graph)
        if isinstance(lead, dict)
    ]
    proof_leads = _ensure_stable_intake_record_ids(
        proof_leads,
        id_key="lead_id",
        prefix="lead",
    )

    timeline_anchors = build_timeline_anchors(canonical_facts)
    timeline_relations = build_timeline_relations(canonical_facts)
    temporal_fact_registry = build_temporal_fact_registry(canonical_facts, timeline_anchors)
    temporal_relation_registry = build_temporal_relation_registry(canonical_facts, timeline_relations)
    temporal_issue_registry = build_temporal_issue_registry(canonical_facts, [])
    claim_temporal_graphs = build_claim_temporal_graphs(
        temporal_fact_registry,
        temporal_relation_registry,
        temporal_issue_registry,
        candidate_claims,
    )
    event_ledger = build_event_ledger(temporal_fact_registry)
    proof_leads = _link_proof_leads_to_timeline_anchors(proof_leads, timeline_anchors)
    timeline_consistency_summary = build_timeline_consistency_summary(
        canonical_facts,
        timeline_anchors,
        temporal_relation_registry,
    )
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
    intake_case_file: Dict[str, Any] = {
        "candidate_claims": candidate_claims,
        "intake_sections": intake_sections,
        "canonical_facts": canonical_facts,
        "timeline_anchors": timeline_anchors,
        "timeline_relations": timeline_relations,
        "temporal_fact_registry": temporal_fact_registry,
        "temporal_relation_registry": temporal_relation_registry,
        "temporal_issue_registry": temporal_issue_registry,
        "timeline_issues": temporal_issue_registry,
        "claim_temporal_graphs": claim_temporal_graphs,
        "event_ledger": event_ledger,
        "timeline_consistency_summary": timeline_consistency_summary,
        "harm_profile": build_harm_profile(canonical_facts),
        "remedy_profile": build_remedy_profile(canonical_facts),
        "proof_leads": proof_leads,
        "blocker_follow_up_summary": blocker_follow_up_summary,
        "contradiction_queue": [],
        "question_dispositions": [],
        "open_items": [],
        "summary_snapshots": [],
        "complainant_summary_confirmation": {},
        "source_complaint_text": normalized_complaint_text,
    }
    intake_case_file["legal_context"] = refresh_explicit_legal_context(intake_case_file)
    intake_case_file = project_graph_revision_view(intake_case_file, knowledge_graph)

    open_items = build_open_items(intake_case_file)
    intake_case_file["open_items"] = open_items
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
    previous_temporal_issue_registry = (
        _coerce_list(case_file.get("temporal_issue_registry"))
        or _coerce_list(case_file.get("timeline_issues"))
    )
    previous_canonical_facts = _coerce_list(case_file.get("canonical_facts"))
    previous_proof_leads = _coerce_list(case_file.get("proof_leads"))
    if knowledge_graph is not None:
        case_file["candidate_claims"] = build_candidate_claims(knowledge_graph)
        case_file["canonical_facts"] = _dedupe_structured_timeline_groups(_enrich_canonical_facts_with_relative_anchor_dates(
            _merge_preserved_canonical_facts(
                build_canonical_facts(knowledge_graph),
                previous_canonical_facts,
            )
        ))
        case_file["canonical_facts"] = _ensure_stable_intake_record_ids(
            _coerce_list(case_file.get("canonical_facts")),
            id_key="fact_id",
            prefix="fact",
        )
        case_file["proof_leads"] = _merge_preserved_proof_leads(
            build_proof_leads(knowledge_graph),
            previous_proof_leads,
        )
        case_file["proof_leads"] = _ensure_stable_intake_record_ids(
            _coerce_list(case_file.get("proof_leads")),
            id_key="lead_id",
            prefix="lead",
        )
    else:
        case_file["canonical_facts"] = _dedupe_structured_timeline_groups(_enrich_canonical_facts_with_relative_anchor_dates([
            _normalize_canonical_fact_record(record)
            for record in _coerce_list(case_file.get("canonical_facts"))
            if isinstance(record, dict)
        ]))
        case_file["canonical_facts"] = _ensure_stable_intake_record_ids(
            _coerce_list(case_file.get("canonical_facts")),
            id_key="fact_id",
            prefix="fact",
        )
        case_file["proof_leads"] = [
            _normalize_proof_lead_record(record)
            for record in _coerce_list(case_file.get("proof_leads"))
            if isinstance(record, dict)
        ]
        case_file["proof_leads"] = _ensure_stable_intake_record_ids(
            _coerce_list(case_file.get("proof_leads")),
            id_key="lead_id",
            prefix="lead",
        )
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
    case_file["timeline_issues"] = _coerce_list(case_file.get("temporal_issue_registry"))
    case_file["claim_temporal_graphs"] = build_claim_temporal_graphs(
        _coerce_list(case_file.get("temporal_fact_registry")),
        _coerce_list(case_file.get("temporal_relation_registry")),
        _coerce_list(case_file.get("temporal_issue_registry")),
        _coerce_list(case_file.get("candidate_claims")),
    )
    case_file["proof_leads"] = _link_proof_leads_to_timeline_anchors(
        _coerce_list(case_file.get("proof_leads")),
        _coerce_list(case_file.get("timeline_anchors")),
    )
    case_file["timeline_consistency_summary"] = build_timeline_consistency_summary(
        _coerce_list(case_file.get("canonical_facts")),
        _coerce_list(case_file.get("timeline_anchors")),
        _coerce_list(case_file.get("temporal_relation_registry")),
    )
    case_file["harm_profile"] = build_harm_profile(_coerce_list(case_file.get("canonical_facts")))
    case_file["remedy_profile"] = build_remedy_profile(_coerce_list(case_file.get("canonical_facts")))
    case_file["legal_context"] = refresh_explicit_legal_context(case_file)
    case_file["blocker_follow_up_summary"] = build_blocker_follow_up_summary(
        candidate_claims=_coerce_list(case_file.get("candidate_claims")),
        canonical_facts=_coerce_list(case_file.get("canonical_facts")),
        proof_leads=_coerce_list(case_file.get("proof_leads")),
        source_text=str(case_file.get("source_complaint_text") or ""),
    )
    case_file["question_dispositions"] = question_disposition_records(case_file)
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
