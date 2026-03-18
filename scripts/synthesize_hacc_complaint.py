import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adversarial_harness.hacc_evidence import _extract_source_window as _extract_grounded_source_window


DEFAULT_RELIEF = [
    "Declaratory relief identifying the challenged conduct and policies.",
    "Injunctive relief requiring fair review, corrected process, and non-retaliation safeguards.",
    "Compensatory damages or other available monetary relief according to proof.",
    "Costs, fees, and any other relief authorized by law.",
]

DEFAULT_PARTIES = {
    "plaintiff": "Complainant / tenant or program participant (name to be inserted).",
    "defendant": "Housing Authority of Clackamas County (HACC).",
}

FILING_FORUM_CHOICES = ("court", "hud", "state_agency")


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _pick_best_session(results_payload: Dict[str, Any], preset: str | None = None) -> Dict[str, Any]:
    sessions = list(results_payload.get("results", []) or [])
    if preset:
        filtered = [
            session for session in sessions
            if ((session.get("seed_complaint", {}) or {}).get("_meta", {}) or {}).get("hacc_preset") == preset
        ]
        if filtered:
            sessions = filtered
    successful = [session for session in sessions if session.get("success") and isinstance(session.get("critic_score"), dict)]
    if not successful:
        raise ValueError("No successful session with critic_score found in results payload")
    return max(successful, key=lambda session: float((session.get("critic_score") or {}).get("overall_score", 0.0) or 0.0))


def _best_preset_from_matrix(matrix_payload: Dict[str, Any]) -> tuple[str | None, str]:
    champion = dict(matrix_payload.get("champion_challenger") or {})
    champion_recommendations = dict(champion.get("recommendations") or {})
    champion_best = dict(champion_recommendations.get("best_overall") or {})
    champion_preset = champion_best.get("preset")
    if champion_preset:
        return str(champion_preset), "champion_challenger"

    recommendations = dict(matrix_payload.get("recommendations") or {})
    best_overall = dict(recommendations.get("best_overall") or {})
    preset = best_overall.get("preset")
    return (str(preset), "matrix") if preset else (None, "unknown")


def _selection_rationale_from_matrix(matrix_payload: Dict[str, Any], selection_source: str) -> Dict[str, Any]:
    source_block = dict(matrix_payload.get("champion_challenger") or {}) if selection_source == "champion_challenger" else dict(matrix_payload)
    recommendations = dict(source_block.get("recommendations") or {})
    best_overall = dict(recommendations.get("best_overall") or {})
    winner_delta = dict(source_block.get("winner_delta") or {})
    if not best_overall and not winner_delta:
        return {}

    rationale: Dict[str, Any] = {
        "selection_source": selection_source,
        "selected_preset": str(best_overall.get("preset") or ""),
        "claim_theory_families": [str(item) for item in list(best_overall.get("claim_theory_families") or []) if str(item)],
        "tradeoff_note": str(best_overall.get("tradeoff_note") or "").strip(),
        "runner_up_preset": str(winner_delta.get("runner_up_preset") or ""),
        "winner_only_theory_families": [str(item) for item in list(winner_delta.get("winner_only_theory_families") or []) if str(item)],
        "runner_up_only_theory_families": [str(item) for item in list(winner_delta.get("runner_up_only_theory_families") or []) if str(item)],
        "shared_theory_families": [str(item) for item in list(winner_delta.get("shared_theory_families") or []) if str(item)],
        "winner_only_claims": [str(item) for item in list(winner_delta.get("winner_only_claims") or []) if str(item)],
        "runner_up_only_claims": [str(item) for item in list(winner_delta.get("runner_up_only_claims") or []) if str(item)],
        "winner_relief_overview": str(winner_delta.get("winner_relief_overview") or "").strip(),
        "runner_up_relief_overview": str(winner_delta.get("runner_up_relief_overview") or "").strip(),
        "winner_only_relief_families": [str(item) for item in list(winner_delta.get("winner_only_relief_families") or []) if str(item)],
        "runner_up_only_relief_families": [str(item) for item in list(winner_delta.get("runner_up_only_relief_families") or []) if str(item)],
        "shared_relief_families": [str(item) for item in list(winner_delta.get("shared_relief_families") or []) if str(item)],
        "winner_only_relief": [str(item) for item in list(winner_delta.get("winner_only_relief") or []) if str(item)],
        "runner_up_only_relief": [str(item) for item in list(winner_delta.get("runner_up_only_relief") or []) if str(item)],
    }
    return {key: value for key, value in rationale.items() if value}


def _summary_with_selection_rationale(summary: str, selection_rationale: Dict[str, Any]) -> str:
    base = str(summary or "").strip()
    if not selection_rationale:
        return base
    tradeoff_note = str(selection_rationale.get("tradeoff_note") or "").strip()
    selected_preset = str(selection_rationale.get("selected_preset") or "").strip()
    if not tradeoff_note:
        return base
    prefix = f"This draft follows the `{selected_preset}` path because {tradeoff_note}." if selected_preset else f"This draft was selected because {tradeoff_note}."
    claim_posture_note = _selection_claim_posture_note(selection_rationale)
    if claim_posture_note:
        prefix = f"{prefix} {claim_posture_note}"
    relief_similarity_note = _selection_relief_similarity_note(selection_rationale)
    if relief_similarity_note:
        prefix = f"{prefix} {relief_similarity_note}"
    if not base:
        return prefix
    if prefix in base:
        return base
    return f"{prefix} {base}"


def _extract_search_summary(
    seed: Dict[str, Any],
    grounding_bundle: Dict[str, Any] | None = None,
    evidence_upload_report: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    meta = dict(seed.get("_meta") or {})
    key_facts = dict(seed.get("key_facts") or {})
    candidates = (
        meta.get("search_summary"),
        key_facts.get("search_summary"),
        (grounding_bundle or {}).get("search_summary"),
        (evidence_upload_report or {}).get("search_summary"),
    )
    stored: Dict[str, Any] = {}
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate:
            stored = dict(candidate)
            break

    requested_mode = str(
        stored.get("requested_search_mode")
        or meta.get("hacc_search_mode")
        or ""
    )
    effective_mode = str(
        stored.get("effective_search_mode")
        or meta.get("hacc_effective_search_mode")
        or requested_mode
    )
    fallback_note = str(
        stored.get("fallback_note")
        or meta.get("hacc_search_fallback_note")
        or ""
    )
    summary = {
        "requested_search_mode": requested_mode,
        "effective_search_mode": effective_mode,
        "fallback_note": fallback_note,
    }
    return {key: value for key, value in summary.items() if value}


def _selection_relief_similarity_note(selection_rationale: Dict[str, Any]) -> str:
    winner_overview = str(selection_rationale.get("winner_relief_overview") or "").strip()
    runner_up_overview = str(selection_rationale.get("runner_up_relief_overview") or "").strip()
    winner_only_relief = [str(item) for item in list(selection_rationale.get("winner_only_relief") or []) if str(item)]
    runner_up_only_relief = [str(item) for item in list(selection_rationale.get("runner_up_only_relief") or []) if str(item)]
    winner_only_relief_families = [str(item) for item in list(selection_rationale.get("winner_only_relief_families") or []) if str(item)]
    runner_up_only_relief_families = [str(item) for item in list(selection_rationale.get("runner_up_only_relief_families") or []) if str(item)]
    if (
        winner_overview
        and winner_overview == runner_up_overview
        and not winner_only_relief
        and not runner_up_only_relief
        and not winner_only_relief_families
        and not runner_up_only_relief_families
    ):
        return "Relief posture was materially similar across the winner and runner-up, so the selection difference was driven mainly by claim posture."
    return ""


def _selection_claim_posture_note(selection_rationale: Dict[str, Any]) -> str:
    winner_only_families = [str(item) for item in list(selection_rationale.get("winner_only_theory_families") or []) if str(item)]
    runner_up_only_families = [str(item) for item in list(selection_rationale.get("runner_up_only_theory_families") or []) if str(item)]
    if not winner_only_families and not runner_up_only_families:
        return ""
    winner_phrase = _families_phrase(winner_only_families)
    runner_phrase = _families_phrase(runner_up_only_families)
    if winner_phrase and runner_phrase:
        return f"The winner added stronger {winner_phrase} theories, while the runner-up leaned more heavily on {runner_phrase} theories."
    if winner_phrase:
        return f"The winner added stronger {winner_phrase} theories."
    return f"The runner-up leaned more heavily on {runner_phrase} theories."


def _cause_semantic_families(cause: Dict[str, Any]) -> List[str]:
    combined = " ".join(
        [
            str(cause.get("title") or ""),
            str(cause.get("theory") or ""),
            " ".join(str(tag) for tag in list(cause.get("selection_tags") or [])),
        ]
    ).lower()
    families: List[str] = []
    checks = (
        ("process", ("process", "notice", "hearing", "appeal", "adverse action", "adverse_action")),
        ("accommodation", ("accommodation", "reasonable accommodation", "reasonable_accommodation", "contact", "section 504", "ada")),
        ("protected_basis", ("protected-basis", "protected basis", "protected_basis", "discrimination")),
        ("retaliation", ("retaliation", "retaliat")),
        ("selection_criteria", ("selection criteria", "selection_criteria", "criteria", "proxy")),
    )
    for label, patterns in checks:
        if any(pattern in combined for pattern in patterns):
            families.append(label)
    return families or ["other"]


def _annotate_causes_with_selection_rationale(
    causes: List[Dict[str, Any]],
    selection_rationale: Dict[str, Any],
) -> List[Dict[str, Any]]:
    if not selection_rationale:
        return causes

    winner_only_claims = {str(item) for item in list(selection_rationale.get("winner_only_claims") or []) if str(item)}
    runner_up_only_claims = {str(item) for item in list(selection_rationale.get("runner_up_only_claims") or []) if str(item)}
    shared_families = {str(item) for item in list(selection_rationale.get("shared_theory_families") or []) if str(item)}
    winner_only_families = {str(item) for item in list(selection_rationale.get("winner_only_theory_families") or []) if str(item)}

    annotated: List[Dict[str, Any]] = []
    for cause in causes:
        enriched = dict(cause)
        title = str(enriched.get("title") or "")
        families = _cause_semantic_families(enriched)
        enriched["strategic_families"] = families
        if title in winner_only_claims:
            enriched["strategic_role"] = "winner_unique_strength"
            enriched["strategic_note"] = "This claim reflects a winner-specific strength that helped this preset beat the runner-up."
        elif title in runner_up_only_claims:
            enriched["strategic_role"] = "runner_up_emphasis"
            enriched["strategic_note"] = "This claim more closely matches a runner-up emphasis and should be reviewed carefully in this selected draft."
        elif shared_families.intersection(families):
            enriched["strategic_role"] = "shared_baseline"
            enriched["strategic_note"] = "This claim reflects a shared baseline theory that appeared in both the selected preset and the runner-up."
        elif winner_only_families.intersection(families):
            enriched["strategic_role"] = "winner_family_strength"
            enriched["strategic_note"] = "This claim supports a theory family that was stronger in the selected preset than in the runner-up."
        annotated.append(enriched)
    return annotated


def _families_phrase(families: List[str]) -> str:
    labels = {
        "process": "process",
        "accommodation": "accommodation",
        "protected_basis": "protected-basis",
        "retaliation": "retaliation",
        "selection_criteria": "selection-criteria",
        "other": "supporting",
    }
    parts = [labels.get(item, str(item).replace("_", "-")) for item in families if item]
    if not parts:
        return "supporting"
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return f"{', '.join(parts[:-1])}, and {parts[-1]}"


def _relief_target_families(relief_text: str) -> List[str]:
    combined = str(relief_text or "").lower()
    families: List[str] = []
    checks = (
        ("process", ("investigation", "adverse-action", "adverse action", "clear notice", "fair review", "process", "hearing", "appeal")),
        ("accommodation", ("accommodation", "disability", "contact", "request-processing", "request processing")),
        ("protected_basis", ("fair housing law", "fair housing", "protected basis", "discrimination", "section 504", "ada")),
        ("retaliation", ("retaliation", "non-retaliation")),
        ("selection_criteria", ("eligibility", "criteria", "preference", "proxy")),
    )
    for label, patterns in checks:
        if any(pattern in combined for pattern in patterns):
            families.append(label)
    return families or ["other"]


def _annotate_requested_relief_with_selection_rationale(
    relief_items: List[str],
    causes: List[Dict[str, Any]],
    selection_rationale: Dict[str, Any],
) -> List[Dict[str, Any]]:
    if not selection_rationale:
        return [{"text": str(item)} for item in relief_items]

    annotations: List[Dict[str, Any]] = []
    for item in relief_items:
        relief_text = str(item or "").strip()
        families = _relief_target_families(relief_text)
        related_causes = []
        matched_families: List[str] = []
        for cause in causes:
            cause_families = [str(value) for value in list(cause.get("strategic_families") or []) if str(value)]
            overlap = [family for family in families if family in cause_families]
            if overlap:
                related_causes.append(cause)
                for family in overlap:
                    if family not in matched_families:
                        matched_families.append(family)

        note_families = matched_families or families

        role = ""
        note = ""
        if any(str(cause.get("strategic_role") or "") == "winner_unique_strength" for cause in related_causes):
            role = "winner_unique_strength"
            note = f"This relief item tracks the winner-specific {_families_phrase(note_families)} advantage that helped the selected preset beat the runner-up."
        elif any(str(cause.get("strategic_role") or "") == "winner_family_strength" for cause in related_causes):
            role = "winner_family_strength"
            note = f"This relief item supports a {_families_phrase(note_families)} theory family that was stronger in the selected preset than in the runner-up."
        elif any(str(cause.get("strategic_role") or "") == "shared_baseline" for cause in related_causes):
            role = "shared_baseline"
            note = f"This relief item tracks the shared {_families_phrase(note_families)} baseline that appeared in both the selected preset and the runner-up."
        elif any(str(cause.get("strategic_role") or "") == "runner_up_emphasis" for cause in related_causes):
            role = "runner_up_emphasis"
            note = f"This relief item aligns more closely with the runner-up's {_families_phrase(note_families)} emphasis and should be reviewed carefully in this selected draft."

        annotations.append(
            {
                "text": relief_text,
                "strategic_families": families,
                "strategic_role": role,
                "strategic_note": note,
                "related_claims": [str(cause.get("title") or "") for cause in related_causes if str(cause.get("title") or "")],
            }
        )
    return annotations


def _conversation_facts(conversation_history: List[Dict[str, Any]], limit: int = 8) -> List[str]:
    facts: List[str] = []
    for entry in conversation_history:
        if entry.get("role") != "complainant":
            continue
        content = " ".join(str(entry.get("content") or "").split())
        if not content:
            continue
        lowered = content.lower()
        if any(token in lowered for token in ("scores:", "feedback:", "strengths:", "weaknesses:", "suggestions:", "question_quality:", "information_extraction:", "coverage:")):
            continue
        if _is_irrelevant_non_housing_fact(content):
            continue
        facts.append(content)
        if len(facts) >= limit:
            break
    return facts


def _is_irrelevant_non_housing_fact(text: str) -> bool:
    lowered = " ".join(str(text or "").split()).lower()
    if not lowered:
        return False
    employment_markers = (
        "human resources",
        "supervisor",
        "promotion",
        "leadership",
        "coworker",
        "manager",
        "workplace",
        "employee",
        "employer",
    )
    housing_markers = (
        "hacc",
        "housing",
        "tenant",
        "voucher",
        "lease",
        "hud",
        "grievance",
        "informal review",
        "informal hearing",
        "assistance",
        "adverse action",
        "notice",
        "termination of assistance",
        "pha",
    )
    return any(marker in lowered for marker in employment_markers) and not any(
        marker in lowered for marker in housing_markers
    )


def _clean_policy_text(text: Any) -> str:
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return cleaned
    cleaned = re.sub(r"^The strongest supporting material is '([^']+)'\.\s*", "", cleaned)
    cleaned = re.sub(r"^For this question, the strongest supporting material is '([^']+)'\.\s*", "", cleaned)
    cleaned = re.sub(r"^HACC Policy\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bHACC Policy\b(?=\s+HACC\b)\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\d+\s+[A-Z][A-Z\s,&/-]{8,}\.{6,}\d+(?:-\d+)?\s*", "", cleaned)
    cleaned = re.sub(r"^ACOP\s+\d{1,2}/\d{1,2}/\d{2,4}\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^EXHIBIT\s+\d+(?:-\d+)?:\s*SAMPLE GRIEVANCE PROCEDURE\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"^Note:\s*The sample procedure provided below is a sample only and is designed to match up with the default policies in the model ACOP\.\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"^If HACC has made policy decisions that do not reflect the default policies in the ACOP,\s*you would need to ensure that the procedure matches those policy decisions\.\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def _is_probably_toc_text(text: str) -> bool:
    normalized = " ".join(str(text or "").split()).strip()
    if not normalized:
        return False
    dotted_leaders = len(re.findall(r"\.{8,}", normalized))
    page_refs = len(re.findall(r"\b\d{1,3}-\d{1,3}\b", normalized))
    heading_hits = len(re.findall(r"\b(?:PART|SECTION|INTRODUCTION|OVERVIEW|PROCEDURES?|APPEALS?|REQUIREMENTS)\b", normalized, flags=re.IGNORECASE))
    return dotted_leaders >= 2 or page_refs >= 4 or (heading_hits >= 3 and dotted_leaders >= 1)


def _to_sentence(text: Any) -> str:
    cleaned = _clean_policy_text(text)
    if not cleaned:
        return ""
    return cleaned if cleaned.endswith(".") else f"{cleaned}."


def _summarize_policy_excerpt(text: Any, max_sentences: int = 2, max_chars: int = 360) -> str:
    cleaned = _clean_policy_text(text)
    if not cleaned:
        return ""
    if _is_probably_toc_text(cleaned):
        sentence_match = re.search(
            r"([^.]*\b(?:written notice|informal review|informal hearing|hearing|appeal|grievance|adverse action|termination|reasonable accommodation|accommodation|review decision)\b[^.]*\.)",
            cleaned,
            flags=re.IGNORECASE,
        )
        if sentence_match:
            cleaned = " ".join(sentence_match.group(1).split()).strip()
        else:
            lowered = cleaned.lower()
            if any(term in lowered for term in ("grievance", "appeal", "hearing")):
                return "HACC policy materials reference grievance, appeal, and hearing procedures."
            if any(term in lowered for term in ("notice", "adverse action", "termination")):
                return "HACC policy materials reference notice and adverse-action procedures."
            if any(term in lowered for term in ("reasonable accommodation", "accommodation", "disability")):
                return "HACC policy materials reference accommodation-related procedures."
            return "HACC policy materials reference procedural protections relevant to the complaint theory."

    clause_hits: List[str] = []
    normalized_clauses = (
        (
            r"Grievance:\s*Any dispute a tenant may have with respect to HACC action or failure to",
            "HACC policy defines a grievance as a tenant dispute concerning HACC action or inaction.",
        ),
        (
            r"If HUD has issued a due process determination, HACC may exclude from HACC grievance",
            "HACC policy says some grievance procedures may be limited when HUD has issued a due process determination.",
        ),
        (
            r"In states without due process determinations, HACC must grant opportunity for grievance",
            "HACC policy says HACC must offer grievance procedures when HUD has not issued a due process determination.",
        ),
        (
            r"Appeals process:\s*Participants will be provided with a formal appeals process",
            "HACC policy says participants must be provided a formal appeals process.",
        ),
        (
            r"If termination is necessary, principles of due process must be followed",
            "HACC policy says due process must be followed before termination.",
        ),
        (
            r"Informal Hearing Process",
            "HACC policy describes an informal hearing process for applicants and residents.",
        ),
        (
            r"Scheduling an Informal Review",
            "HACC policy describes scheduling and procedures for informal review.",
        ),
        (
            r"Information of the availability of reasonable accommodation will be provided to all families at the time of application",
            "HACC policy says applicants must be informed at application that reasonable accommodation is available.",
        ),
        (
            r"HACC will ask all applicants and participants if they require any type of accommodations in writing",
            "HACC policy says applicants and participants must be asked in writing about accommodation needs on intake, reexamination, and adverse-action notices.",
        ),
        (
            r"HACC will also ask all applicants and participants if they require any type of accommodations, in writing",
            "HACC policy says applicants and participants must be asked in writing about accommodation needs on intake, reexamination, and adverse-action notices.",
        ),
        (
            r"A specific name and phone number of designated staff will be provided to process requests for accommodation",
            "HACC policy says designated staff contact information must be provided for accommodation requests.",
        ),
        (
            r"HACC will conduct an informal hearing remotely upon request as a reasonable accommodation for a person with a disability",
            "HACC policy says remote informal hearings must be provided as a reasonable accommodation when requested by a person with a disability.",
        ),
        (
            r"Written notice",
            None,
        ),
        (
            r"informal review or hearing",
            None,
        ),
        (
            r"review decision",
            None,
        ),
    )
    for pattern, replacement in normalized_clauses:
        match = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if not match:
            continue
        clause = replacement
        if clause is None:
            sentence_match = re.search(rf"([^.]*{pattern}[^.]*\.)", cleaned, flags=re.IGNORECASE)
            clause = " ".join(sentence_match.group(1).split()).strip() if sentence_match else ""
        if clause and clause not in clause_hits:
            clause_hits.append(clause)
        if len(clause_hits) >= max_sentences:
            break
    if clause_hits:
        summary = " ".join(clause_hits[:max_sentences]).strip()
        if len(summary) > max_chars:
            summary = summary[: max_chars - 3].rstrip(" ,;:.") + "..."
        return summary

    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]
    if not sentences:
        return cleaned[:max_chars].rstrip() + ("..." if len(cleaned) > max_chars else "")

    priority_patterns = (
        "written notice",
        "informal review",
        "informal hearing",
        "hearing",
        "review decision",
        "adverse action",
        "termination",
        "reasonable accommodation",
        "accommodation",
        "disabilities",
        "appeal",
        "grievance",
    )
    selected: List[str] = []
    for sentence in sentences:
        lowered = sentence.lower()
        if any(pattern in lowered for pattern in priority_patterns):
            selected.append(sentence.rstrip("."))
        if len(selected) >= max_sentences:
            break

    if not selected:
        selected = [sentence.rstrip(".") for sentence in sentences[:max_sentences]]

    summary = ". ".join(selected).strip(" .")
    if summary and not summary.endswith("."):
        summary += "."
    if len(summary) > max_chars:
        summary = summary[: max_chars - 3].rstrip(" ,;:.") + "..."
    return summary


def _humanize_section(label: str) -> str:
    return str(label or "").replace("_", " ").strip()


def _collect_timeline_points(conversation_history: List[Dict[str, Any]], limit: int = 4) -> List[str]:
    timeline_points: List[str] = []
    for fact in _conversation_facts(conversation_history, limit=limit * 2):
        lowered = fact.lower()
        if any(marker in lowered for marker in ("timeline", "late 20", "shortly after", "few weeks", "after that")):
            timeline_points.append(fact)
        if len(timeline_points) >= limit:
            break
    return timeline_points


def _summarize_timeline_fact(fact: str, max_events: int = 4) -> str:
    cleaned = " ".join(str(fact or "").split()).strip()
    if not cleaned:
        return ""

    marker_match = re.search(r"(?:Here(?:'s| is).{0,80}?timeline[^:]*:)\s*", cleaned, flags=re.IGNORECASE)
    if marker_match:
        cleaned = cleaned[marker_match.end():].strip()

    events = re.findall(r"(?:^|\s)(\d+)\.\s*(.*?)(?=(?:\s+\d+\.\s)|$)", cleaned)
    summarized_events: List[str] = []
    if events:
        for _, event_text in events[:max_events]:
            event_text = re.sub(r"\*+", "", event_text).strip(" -:;,.")
            if not event_text:
                continue
            sentences = re.split(r"(?<=[.!?])\s+", event_text)
            primary = sentences[0].strip() if sentences else event_text
            if primary:
                summarized_events.append(primary.rstrip("."))
    else:
        sentences = re.split(r"(?<=[.!?])\s+", cleaned)
        summarized_events = [sentence.strip().rstrip(".") for sentence in sentences[:max_events] if sentence.strip()]

    if not summarized_events:
        return ""

    compact = "; ".join(summarized_events[:max_events])
    compact = re.sub(r"\s+", " ", compact).strip(" ;,")
    return compact


def _dedupe_timeline_summaries(items: List[str], limit: int = 2) -> List[str]:
    deduped: List[str] = []
    seen = set()
    for item in items:
        normalized = re.sub(r"\([^)]*\)", "", item)
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized.lower()).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return deduped


def _summarize_intake_fact(fact: str, max_sentences: int = 2) -> str:
    cleaned = " ".join(str(fact or "").split()).strip()
    if not cleaned:
        return ""

    if any(marker in cleaned.lower() for marker in ("timeline", "late 20", "shortly after", "few weeks", "after that")):
        return _summarize_timeline_fact(cleaned)

    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]
    if not sentences:
        return ""

    selected: List[str] = []
    priority_patterns = (
        "retaliat",
        "written notice",
        "hearing decision",
        "informal review",
        "informal hearing",
        "appeal rights",
        "due process",
        "denying or terminating",
        "adverse action",
        "stress",
        "destabil",
    )
    for sentence in sentences:
        lowered = sentence.lower()
        if any(pattern in lowered for pattern in priority_patterns):
            selected.append(sentence.rstrip("."))
        if len(selected) >= max_sentences:
            break

    if not selected:
        selected = [sentence.rstrip(".") for sentence in sentences[:max_sentences]]

    compact = "; ".join(selected[:max_sentences]).strip(" ;,")
    return re.sub(r"\s+", " ", compact)


def _dedupe_fact_summaries(items: List[str], limit: int = 3) -> List[str]:
    deduped: List[str] = []
    seen = set()
    for item in items:
        normalized = re.sub(r"\([^)]*\)", "", item)
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized.lower()).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return deduped


def _dedupe_sentences(items: List[str], limit: int) -> List[str]:
    deduped: List[str] = []
    seen = set()
    for item in items:
        sentence = _to_sentence(item)
        if not sentence:
            continue
        key = sentence.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(sentence)
        if len(deduped) >= limit:
            break
    return deduped


def _evidence_tags(*texts: Any, limit: int = 4) -> List[str]:
    combined = " ".join(str(text or "") for text in texts).lower()
    tag_patterns = (
        ("reasonable_accommodation", ("reasonable accommodation", "accommodation", "disabilities")),
        ("notice", ("written notice", "notice of adverse action", "adverse action notice", "notice")),
        ("contact", ("contact person", "contact information", "phone number", "designated staff")),
        ("hearing", ("informal hearing", "informal review", "hearing", "review decision", "appeal", "grievance")),
        ("adverse_action", ("adverse action", "termination", "denial")),
        ("selection_criteria", ("selection criteria", "criteria", "preferences", "eligibility")),
    )
    tags: List[str] = []
    for tag, patterns in tag_patterns:
        if any(pattern in combined for pattern in patterns):
            tags.append(tag)
        if len(tags) >= limit:
            break
    return tags


def _extract_tags_from_line(line: str) -> List[str]:
    match = re.search(r": \[([^\]]+)\] ", str(line or ""))
    if not match:
        return []
    return [part.strip() for part in match.group(1).split(",") if part.strip()]


def _tag_heading(tag: str) -> str:
    mapping = {
        "reasonable_accommodation": "Accommodation",
        "notice": "Notice",
        "contact": "Contact",
        "hearing": "Hearing",
        "adverse_action": "Adverse Action",
        "selection_criteria": "Selection Criteria",
    }
    return mapping.get(tag, _humanize_section(tag).title())


def _tag_intro(heading: str, section_kind: str) -> str:
    intro_map = {
        "Accommodation": {
            "basis": "These policy excerpts frame the accommodation theory and summarize what HACC policy appears to require on accommodations.",
            "anchor": "These passages support the accommodation theory and show what HACC policy says should have been provided or evaluated.",
            "supporting": "These materials support the accommodation theory and identify the policy language tied to accommodation duties.",
        },
        "Notice": {
            "basis": "These policy excerpts frame the notice theory and summarize what HACC policy appears to require for written notice or adverse-action disclosures.",
            "anchor": "These passages support the notice theory and show what written notice or adverse-action disclosures HACC policy appears to require.",
            "supporting": "These materials support the notice theory and identify policy language about written notice and adverse-action disclosures.",
        },
        "Contact": {
            "basis": "These policy excerpts frame the contact-information theory and summarize what HACC policy appears to require for staff contacts.",
            "anchor": "These passages support the contact-information theory and show what staff contact details HACC policy appears to require.",
            "supporting": "These materials support the contact-information theory and identify policy language about designated staff contacts.",
        },
        "Hearing": {
            "basis": "These policy excerpts frame the hearing theory and summarize what HACC policy appears to require for reviews, grievances, or hearings.",
            "anchor": "These passages support the hearing theory and show what review, grievance, or hearing protections HACC policy appears to require.",
            "supporting": "These materials support the hearing theory and identify policy language about reviews, grievances, and hearings.",
        },
        "Adverse Action": {
            "basis": "These policy excerpts frame the adverse-action theory and summarize what HACC policy appears to require before denial or termination.",
            "anchor": "These passages support the adverse-action theory and show what process HACC policy appears to require before denial or termination.",
            "supporting": "These materials support the adverse-action theory and identify policy language tied to denial or termination procedures.",
        },
        "Selection Criteria": {
            "basis": "These policy excerpts frame the selection-criteria theory and summarize what HACC policy appears to require for criteria or eligibility standards.",
            "anchor": "These passages support the selection-criteria theory and show what criteria or eligibility standards HACC policy appears to use.",
            "supporting": "These materials support the selection-criteria theory and identify policy language about criteria or eligibility standards.",
        },
        "Other Evidence": {
            "basis": "These policy excerpts provide additional context that does not fit neatly into the primary issue headings.",
            "anchor": "These passages provide additional source support that does not fit neatly into the primary issue headings.",
            "supporting": "These materials provide additional source support that does not fit neatly into the primary issue headings.",
        },
    }
    return intro_map.get(heading, {}).get(section_kind, "These materials provide supporting policy context for the current complaint theory.")


def _group_lines_by_tag(lines: List[str], max_groups: int = 3, max_repeat_groups: int = 2) -> List[tuple[str, List[str]]]:
    preferred_order = [
        "reasonable_accommodation",
        "notice",
        "contact",
        "hearing",
        "adverse_action",
        "selection_criteria",
    ]
    grouped: List[tuple[str, List[str]]] = []
    usage_counts = {line: 0 for line in lines}

    for tag in preferred_order:
        matching = [
            line
            for line in lines
            if tag in _extract_tags_from_line(line) and usage_counts.get(line, 0) < max_repeat_groups
        ]
        if not matching:
            continue
        grouped.append((_tag_heading(tag), matching))
        for line in matching:
            usage_counts[line] = usage_counts.get(line, 0) + 1
        if len(grouped) >= max_groups:
            break

    remaining = [line for line in lines if usage_counts.get(line, 0) == 0]
    if remaining:
        grouped.append(("Other Evidence", remaining))
    return grouped


def _line_label(line: str) -> str:
    text = str(line or "")
    if " supports " in text:
        return text.split(" supports ", 1)[0].strip()
    if ":" in text:
        return text.split(":", 1)[0].strip()
    return text[:80].strip()


def _line_exhibit_key(line: str) -> str:
    label = _line_label(line)
    return re.sub(r"\s*\[[^\]]+\]$", "", label).strip()


def _exhibit_id(index: int) -> str:
    return f"Exhibit {chr(ord('A') + index)}"


def _build_exhibit_index(lines: List[str]) -> Dict[str, str]:
    exhibit_index: Dict[str, str] = {}
    ordered_keys: List[str] = []
    for line in lines:
        key = _line_exhibit_key(line)
        if key and key not in ordered_keys:
            ordered_keys.append(key)
    for index, key in enumerate(ordered_keys):
        exhibit_index[key] = _exhibit_id(index)
    return exhibit_index


def _ordered_exhibit_index(lines: List[str]) -> List[tuple[str, str]]:
    exhibit_index = _build_exhibit_index(lines)
    ordered = sorted(exhibit_index.items(), key=lambda item: item[1])
    return [(exhibit_id, label) for label, exhibit_id in ordered]


def _format_exhibit_reference_list(exhibits: List[tuple[str, str]], limit: int = 2) -> str:
    items = [f"{exhibit_id} ({label})" for exhibit_id, label in exhibits[:limit]]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def _cause_target_tags(cause: Dict[str, Any]) -> List[str]:
    title_and_theory = " ".join(
        [
            str(cause.get("title") or ""),
            str(cause.get("theory") or ""),
        ]
    ).lower()
    title_only = str(cause.get("title") or "").lower()
    if any(term in title_and_theory for term in ("protected-basis", "protected basis", "discrimination")):
        return ["protected_basis"]
    if any(term in title_only for term in ("accommodation theory", "accommodation claim", "accommodation rights")):
        return ["reasonable_accommodation", "contact"]
    tags: List[str] = []
    if any(term in title_and_theory for term in ("accommodation", "disability", "section 504", "ada")):
        tags.extend(["reasonable_accommodation", "contact"])
    if any(term in title_and_theory for term in ("notice", "process", "hearing", "review", "appeal", "adverse-action", "adverse action", "termination", "denial")):
        tags.extend(["notice", "hearing", "adverse_action"])
    if any(term in title_and_theory for term in ("selection", "criteria", "proxy")):
        tags.append("selection_criteria")

    deduped: List[str] = []
    for tag in tags:
        if tag not in deduped:
            deduped.append(tag)
    return deduped


def _cause_text(cause: Dict[str, Any]) -> str:
    return " ".join(
        [
            str(cause.get("title") or ""),
            str(cause.get("theory") or ""),
            " ".join(str(item) for item in list(cause.get("support") or [])),
        ]
    ).lower()


def _cause_title_and_theory(cause: Dict[str, Any]) -> str:
    return " ".join(
        [
            str(cause.get("title") or ""),
            str(cause.get("theory") or ""),
        ]
    ).lower()


def _single_exhibit_margin_for_cause(cause: Dict[str, Any]) -> int:
    combined = _cause_text(cause)
    if "retaliat" in combined:
        return 1
    if any(term in combined for term in ("accommodation", "disability", "section 504", "ada", "protected-basis", "protected basis")):
        return 1
    if any(term in combined for term in ("notice", "process", "hearing", "review", "appeal", "adverse-action", "adverse action", "termination", "denial")):
        return 3
    return 2


def _select_exhibit_refs_for_tags(
    tag_targets: List[str],
    line_tag_map: Dict[str, List[str]],
    exhibit_index: Dict[str, str],
    line_text_map: Dict[str, str],
    cause_text: str = "",
    limit: int = 2,
    single_exhibit_margin: int = 2,
) -> List[tuple[str, str]]:
    scored_matches: List[tuple[int, str, str]] = []
    cause_terms = {term for term in re.findall(r"[a-z0-9_]+", cause_text.lower()) if len(term) > 4}
    accommodation_focus = any(tag == "reasonable_accommodation" for tag in tag_targets)
    process_focus = any(tag in {"notice", "hearing", "adverse_action"} for tag in tag_targets)
    for line_key, tags in line_tag_map.items():
        exhibit_id = exhibit_index.get(line_key)
        if not exhibit_id:
            continue
        score = 0
        for index, tag in enumerate(tag_targets):
            if tag in tags:
                score += max(1, len(tag_targets) - index)
        line_text = line_text_map.get(line_key, "").lower()
        line_terms = {term for term in re.findall(r"[a-z0-9_]+", line_text) if len(term) > 4}
        score += len(cause_terms & line_terms)
        if accommodation_focus and any(term in line_text for term in ("designated staff", "contact information", "process requests", "phone number")):
            score += 2
        if process_focus and any(term in line_text for term in ("written notice", "review decision", "informal review", "informal hearing")):
            score += 2
        if tag_targets and score == 0:
            continue
        scored_matches.append((score, exhibit_id, line_key))

    best_by_exhibit: Dict[str, tuple[int, str]] = {}
    for score, exhibit_id, line_key in scored_matches:
        current = best_by_exhibit.get(exhibit_id)
        if current is None or score > current[0] or (score == current[0] and line_key < current[1]):
            best_by_exhibit[exhibit_id] = (score, line_key)

    unique_matches = sorted(
        [(score, exhibit_id, line_key) for exhibit_id, (score, line_key) in best_by_exhibit.items()],
        key=lambda item: (-item[0], item[1], item[2]),
    )

    if process_focus and unique_matches:
        top_score, top_exhibit_id, top_line_key = unique_matches[0]
        next_score = unique_matches[1][0] if len(unique_matches) > 1 else -1
        if top_score > next_score and top_score > 0:
            return [(top_exhibit_id, top_line_key)]

    if len(unique_matches) >= 2 and unique_matches[0][0] >= unique_matches[1][0] + single_exhibit_margin:
        top_score, top_exhibit_id, top_line_key = unique_matches[0]
        if top_score > 0:
            return [(top_exhibit_id, top_line_key)]

    matches: List[tuple[str, str]] = []
    for score, exhibit_id, line_key in unique_matches:
        if score <= 0:
            continue
        matches.append((exhibit_id, line_key))
        if len(matches) >= limit:
            break
    return matches


def _exhibit_rationale_for_cause(cause: Dict[str, Any], selected_refs: List[tuple[str, str]], tag_targets: List[str]) -> str:
    title_and_theory = _cause_title_and_theory(cause)
    labels = [label for _, label in selected_refs]
    label_text = " ".join(labels).lower()

    if not labels:
        return ""
    if any(term in title_and_theory for term in ("protected-basis", "protected basis", "discrimination")):
        return "selected for strongest overlap with the protected-basis theory"
    if "retaliat" in title_and_theory and any(
        term in label_text for term in ("administrative plan", "grievance", "notice")
    ):
        return "selected for the strongest overlap with grievance activity and adverse-process protections tied to the retaliation theory"
    if "reasonable_accommodation" in tag_targets and any(
        term in label_text for term in ("administrative plan", "designated staff", "contact")
    ):
        return "selected for stronger accommodation contact-language"
    if any(tag in tag_targets for tag in ("notice", "hearing", "adverse_action")) and any(
        term in label_text for term in ("administrative plan", "notice")
    ):
        return "selected for stronger notice and process language"
    return "selected as the closest documentary match for this claim"


def _inject_exhibit_references(package: Dict[str, Any]) -> None:
    all_exhibit_lines = (
        list(package.get("policy_basis") or [])
        + list(package.get("anchor_passages") or [])
        + list(package.get("supporting_evidence") or [])
    )
    exhibit_index = _build_exhibit_index(all_exhibit_lines)
    exhibit_refs = _ordered_exhibit_index(all_exhibit_lines)
    line_tag_map: Dict[str, List[str]] = {}
    line_text_map: Dict[str, str] = {}
    for line in all_exhibit_lines:
        key = _line_exhibit_key(line)
        if key not in line_tag_map:
            line_tag_map[key] = _extract_tags_from_line(line)
            line_text_map[key] = str(line)
    reference_text = _format_exhibit_reference_list(exhibit_refs)
    if not reference_text:
        return

    claims = list(package.get("claims_theory") or [])
    updated_claims: List[str] = []
    inserted_claim_ref = False
    for item in claims:
        if not inserted_claim_ref and (
            item.startswith("The strongest policy support for these theories is:")
            or item.startswith("The policy theory is grounded in HACC language stating that")
        ):
            updated_claims.append(f"{item} That documentary support is reflected in {reference_text}.")
            inserted_claim_ref = True
        else:
            updated_claims.append(item)
    if not inserted_claim_ref:
        updated_claims.append(f"The primary documentary support for these theories appears in {reference_text}.")
    package["claims_theory"] = updated_claims

    allegations = list(package.get("factual_allegations") or [])
    reference_sentence = f"The core documentary support for these allegations appears in {reference_text}."
    if reference_sentence not in allegations:
        allegations.append(reference_sentence)
    package["factual_allegations"] = allegations

    causes = list(package.get("causes_of_action") or [])
    for cause in causes:
        support_items = list(cause.get("support") or [])
        tag_targets = _cause_target_tags(cause)
        targeted_refs = _select_exhibit_refs_for_tags(
            tag_targets,
            line_tag_map,
            exhibit_index,
            line_text_map,
            _cause_text(cause),
            single_exhibit_margin=_single_exhibit_margin_for_cause(cause),
        )
        cause_reference_text = _format_exhibit_reference_list(targeted_refs) or reference_text
        rationale = _exhibit_rationale_for_cause(cause, targeted_refs, tag_targets)
        cause["selected_exhibits"] = [
            {
                "exhibit_id": exhibit_id,
                "label": label,
            }
            for exhibit_id, label in targeted_refs
        ]
        cause["selection_rationale"] = rationale
        cause["selection_tags"] = tag_targets
        cause_support_reference = f"Documentary support: {cause_reference_text}."
        if rationale:
            cause_support_reference += f" Rationale: {rationale}."
        if cause_support_reference not in support_items:
            support_items.append(cause_support_reference)
        cause["support"] = support_items
    package["causes_of_action"] = causes


def _claim_selection_summary(causes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    summary: List[Dict[str, Any]] = []
    for cause in causes:
        summary.append(
            {
                "title": str(cause.get("title") or ""),
                "selection_tags": [str(item) for item in list(cause.get("selection_tags") or []) if str(item)],
                "selected_exhibits": [
                    {
                        "exhibit_id": str(item.get("exhibit_id") or ""),
                        "label": str(item.get("label") or ""),
                    }
                    for item in list(cause.get("selected_exhibits") or [])
                ],
                "selection_rationale": str(cause.get("selection_rationale") or ""),
            }
        )
    return summary


def _relief_selection_summary(relief_annotations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    summary: List[Dict[str, Any]] = []
    for item in relief_annotations:
        summary.append(
            {
                "text": str(item.get("text") or ""),
                "strategic_families": [str(value) for value in list(item.get("strategic_families") or []) if str(value)],
                "strategic_role": str(item.get("strategic_role") or ""),
                "strategic_note": str(item.get("strategic_note") or ""),
                "related_claims": [str(value) for value in list(item.get("related_claims") or []) if str(value)],
            }
        )
    return summary


def _render_grouped_lines(lines: List[str], section_kind: str, exhibit_index: Dict[str, str]) -> List[str]:
    rendered: List[str] = []
    grouped = _group_lines_by_tag(lines)
    first_heading_for_line: Dict[str, str] = {}

    for heading, items in grouped:
        rendered.append(f"### {heading}")
        rendered.append("")
        rendered.append(_tag_intro(heading, section_kind))
        rendered.append("")
        for item in items:
            if item not in first_heading_for_line:
                first_heading_for_line[item] = heading
                exhibit_id = exhibit_index.get(_line_exhibit_key(item))
                if exhibit_id:
                    rendered.append(f"- {exhibit_id}: {item}")
                else:
                    rendered.append(f"- {item}")
            else:
                exhibit_id = exhibit_index.get(_line_exhibit_key(item))
                exhibit_text = f"{exhibit_id} ({_line_label(item)})" if exhibit_id else _line_label(item)
                rendered.append(f"- See also {exhibit_text} under {first_heading_for_line[item]}.")
        rendered.append("")
    return rendered


def _should_include_full_passage(snippet: str, summary: str) -> bool:
    cleaned_snippet = _clean_policy_text(snippet)
    cleaned_summary = _clean_policy_text(summary)
    if not cleaned_snippet or cleaned_snippet == cleaned_summary:
        return False
    if _is_probably_toc_text(cleaned_snippet) or _is_placeholder_policy_text(cleaned_snippet) or _is_generic_chapter_intro_text(cleaned_snippet):
        return False
    return True


def _anchor_passage_lines(seed: Dict[str, Any], limit: int = 5) -> List[str]:
    key_facts = dict(seed.get("key_facts") or {})
    passages = list(key_facts.get("anchor_passages") or [])
    lines = []
    for passage in passages[:limit]:
        section_labels = ", ".join(list(passage.get("section_labels") or []))
        title = str(passage.get("title") or "Evidence")
        snippet = _clean_policy_text(passage.get("snippet") or "")
        summary = _summarize_policy_excerpt(snippet)
        tags = _evidence_tags(section_labels, summary, snippet)
        tag_prefix = f"[{', '.join(tags)}] " if tags else ""
        if section_labels:
            if summary and _should_include_full_passage(snippet, summary):
                lines.append(f"{title} [{section_labels}]: {tag_prefix}{summary} Full passage: {snippet}")
            else:
                lines.append(f"{title} [{section_labels}]: {tag_prefix}{summary or snippet}")
        else:
            if summary and _should_include_full_passage(snippet, summary):
                lines.append(f"{title}: {tag_prefix}{summary} Full passage: {snippet}")
            else:
                lines.append(f"{title}: {tag_prefix}{summary or snippet}")
    return lines


def _evidence_lines(seed: Dict[str, Any], limit: int = 5) -> List[str]:
    evidence = list(seed.get("hacc_evidence") or [])
    lines = []
    for item in evidence[:limit]:
        title = str(item.get("title") or item.get("document_id") or "Evidence")
        snippet = _clean_policy_text(item.get("snippet") or "")
        summary = _summarize_policy_excerpt(snippet)
        tags = _evidence_tags(title, summary, snippet)
        tag_prefix = f"[{', '.join(tags)}] " if tags else ""
        source_path = str(item.get("source_path") or "")
        if summary and _should_include_full_passage(snippet, summary):
            line = f"{title}: {tag_prefix}{summary} Full passage: {snippet}"
        else:
            line = f"{title}: {tag_prefix}{summary or snippet}"
        if source_path:
            line += f" ({source_path})"
        lines.append(line)
    return lines


def _load_optional_json(path: Path | None) -> Dict[str, Any]:
    if path is None or not path.exists() or not path.is_file():
        return {}
    return _load_json(path)


def _refresh_anchor_terms(anchor_terms: List[str], fallback_snippet: str) -> List[str]:
    terms: List[str] = []

    cleaned_snippet = " ".join(str(fallback_snippet or "").split()).strip()
    if cleaned_snippet:
        heading_candidates = [
            re.split(r"\.{6,}|\[[^\]]+\]|;|:", cleaned_snippet, maxsplit=1)[0].strip(),
            cleaned_snippet,
        ]
        for candidate in heading_candidates:
            candidate = re.sub(r"^\d{1,3}(?:-\d{1,3})?\s+", "", candidate).strip(" -.:")
            if not candidate:
                continue
            if len(candidate.split()) >= 3:
                terms.append(candidate)

    terms.extend(anchor_terms)

    deduped: List[str] = []
    seen = set()
    for term in terms:
        normalized = term.lower()
        if normalized not in seen:
            seen.add(normalized)
            deduped.append(term)
    return deduped


def _specific_refresh_terms(
    fallback_snippet: str,
    *,
    title: str = "",
    section_labels: Sequence[str] | None = None,
    anchor_terms: Sequence[str] | None = None,
) -> List[str]:
    preferred_terms: List[str] = []
    if title:
        preferred_terms.append(title)
    title_lower = title.lower()
    for label in list(section_labels or []):
        humanized = _humanize_section(str(label))
        if humanized:
            preferred_terms.append(humanized)
    if "administrative plan" in title_lower and any(
        label in {"grievance_hearing", "appeal_rights", "adverse_action"} for label in list(section_labels or [])
    ):
        curated_terms = [
            "Notice to the Applicant",
            "Scheduling an Informal Review",
            "Informal Review Procedures",
            "Informal Review Decision",
            "Notice of Denial or Termination of Assistance",
        ]
        for term in list(anchor_terms or []):
            normalized = str(term).strip()
            if not normalized:
                continue
            if len(normalized.split()) >= 2 or len(normalized) >= 12:
                curated_terms.append(normalized)
        deduped: List[str] = []
        seen = set()
        for term in curated_terms:
            normalized = term.lower()
            if normalized not in seen:
                seen.add(normalized)
                deduped.append(term)
        return deduped
    for term in list(anchor_terms or []):
        normalized = str(term).strip()
        if not normalized:
            continue
        if len(normalized.split()) >= 2 or len(normalized) >= 12:
            preferred_terms.append(normalized)
    terms = _refresh_anchor_terms(preferred_terms, fallback_snippet)
    if terms:
        return terms
    return _refresh_anchor_terms([str(term).strip() for term in list(anchor_terms or []) if str(term).strip()], fallback_snippet)


def _policy_text_quality(text: str) -> int:
    cleaned = _clean_policy_text(text)
    if not cleaned:
        return -10

    score = 0
    if _is_probably_toc_text(cleaned):
        score -= 8
    if _is_placeholder_policy_text(cleaned):
        score -= 6
    if _is_complaint_process_text(cleaned):
        score -= 5
    if _is_generic_chapter_intro_text(cleaned):
        score -= 4
    if "HACC Policy" in str(text):
        score += 4
    if re.search(r"\b(?:must|shall|will|may request|written notice|informal review|informal hearing|grievance)\b", cleaned, flags=re.IGNORECASE):
        score += 3
    if re.search(r"[.!?]", cleaned):
        score += 2
    score += min(len(cleaned) // 180, 3)
    return score


def _is_placeholder_policy_text(text: str) -> bool:
    normalized = _clean_policy_text(text)
    if not normalized:
        return False
    return bool(
        re.search(
            r"\[(?:INSERT|The following is an optional section|Optional)",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def _is_complaint_process_text(text: str) -> bool:
    normalized = _clean_policy_text(text)
    if not normalized:
        return False
    lowered = normalized.lower()
    return any(
        phrase in lowered
        for phrase in (
            "vawa complaint",
            "file a complaint with fheo",
            "office of fair housing and equal opportunity",
            "fheo",
            "equal access final rule",
        )
    )


def _is_generic_chapter_intro_text(text: str) -> bool:
    normalized = _clean_policy_text(text)
    if not normalized:
        return False
    return bool(
        re.search(
            r"\b(?:GRIEVANCES AND APPEALS INTRODUCTION|This chapter discusses grievances and appeals|The policies are discussed in the following three parts)\b",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def _trim_admin_plan_complaint_preamble(text: str) -> str:
    cleaned = _clean_policy_text(text)
    if not cleaned:
        return cleaned
    heading_terms = (
        "Notice to the Applicant",
        "Scheduling an Informal Review",
        "Informal Review Procedures",
        "Notice of Denial or Termination of Assistance",
        "Informal Hearing Procedures",
    )
    heading_matches = [cleaned.lower().find(term.lower()) for term in heading_terms]
    heading_matches = [idx for idx in heading_matches if idx >= 0]
    if not heading_matches:
        return cleaned
    first_heading = min(heading_matches)
    lowered = cleaned.lower()
    has_denial_leadin = lowered.startswith("denial of assistance includes")
    if not _is_complaint_process_text(cleaned) and not has_denial_leadin and first_heading > 160:
        return cleaned
    start = first_heading
    trimmed = cleaned[start:].strip()
    return trimmed or cleaned


def _refresh_snippet_from_source(
    source_path: str,
    *,
    anchor_terms: List[str],
    fallback_snippet: str,
) -> str:
    refresh_terms = _refresh_anchor_terms(anchor_terms, fallback_snippet)
    if not source_path or not refresh_terms:
        return _clean_policy_text(fallback_snippet)
    window_chars = 520
    combined_terms = " ".join(refresh_terms).lower()
    if any(term in combined_terms for term in ("definitions applicable to the grievance procedure", "elements of due process", "grievance procedure")):
        window_chars = 900
    refreshed = _extract_grounded_source_window(
        source_path=source_path,
        anchor_terms=refresh_terms,
        fallback_snippet=fallback_snippet,
        window_chars=window_chars,
    )
    refreshed = _trim_admin_plan_complaint_preamble(refreshed or fallback_snippet)
    return _clean_policy_text(refreshed or fallback_snippet)


def _should_replace_snippet(current_snippet: str, refreshed_snippet: str) -> bool:
    current_clean = _clean_policy_text(current_snippet)
    refreshed_clean = _clean_policy_text(refreshed_snippet)
    if not refreshed_clean or refreshed_clean == current_clean:
        return False
    if (
        current_clean.lower().startswith("denial of assistance includes")
        and refreshed_clean.lower().startswith("notice to the applicant")
    ):
        return True
    if _is_probably_toc_text(current_clean) and not _is_probably_toc_text(refreshed_clean):
        return True
    if "HACC Policy" in refreshed_snippet and "HACC Policy" not in current_snippet:
        return True
    if len(refreshed_clean) > len(current_clean) and not _is_probably_toc_text(refreshed_clean):
        return True
    return False


def _should_promote_grounded_snippet(current_snippet: str, evidence_snippet: str) -> bool:
    current_clean = _clean_policy_text(current_snippet)
    evidence_clean = _clean_policy_text(evidence_snippet)
    if not evidence_clean or evidence_clean == current_clean:
        return False
    if _should_replace_snippet(current_snippet, evidence_snippet):
        return True
    if "elements of due process" in evidence_clean.lower() and "elements of due process" not in current_clean.lower():
        return True
    if _policy_text_quality(evidence_clean) > _policy_text_quality(current_clean):
        return True
    if len(evidence_clean) >= len(current_clean) + 80 and not _is_probably_toc_text(evidence_clean):
        return True
    return False


def _refresh_seed_source_snippets(seed: Dict[str, Any]) -> Dict[str, Any]:
    refreshed_seed = dict(seed or {})
    key_facts = dict(refreshed_seed.get("key_facts") or {})
    anchor_terms = [str(item).strip() for item in list(key_facts.get("anchor_terms") or []) if str(item).strip()]
    if not anchor_terms:
        refreshed_seed["key_facts"] = key_facts
        return refreshed_seed

    refreshed_passages: List[Dict[str, Any]] = []
    for passage in list(key_facts.get("anchor_passages") or []):
        updated = dict(passage)
        current_snippet = str(updated.get("snippet") or "")
        refresh_terms = _specific_refresh_terms(
            current_snippet,
            title=str(updated.get("title") or ""),
            section_labels=list(updated.get("section_labels") or []),
            anchor_terms=anchor_terms,
        )
        refreshed_snippet = _refresh_snippet_from_source(
            str(updated.get("source_path") or ""),
            anchor_terms=refresh_terms,
            fallback_snippet=current_snippet,
        )
        if _should_replace_snippet(current_snippet, refreshed_snippet):
            updated["snippet"] = refreshed_snippet
        refreshed_passages.append(updated)
    if refreshed_passages:
        key_facts["anchor_passages"] = refreshed_passages

    refreshed_evidence: List[Dict[str, Any]] = []
    for item in list(refreshed_seed.get("hacc_evidence") or []):
        updated = dict(item)
        current_snippet = str(updated.get("snippet") or "")
        refresh_terms = _specific_refresh_terms(
            current_snippet,
            title=str(updated.get("title") or ""),
            anchor_terms=anchor_terms,
        )
        refreshed_snippet = _refresh_snippet_from_source(
            str(updated.get("source_path") or ""),
            anchor_terms=refresh_terms,
            fallback_snippet=current_snippet,
        )
        if _should_replace_snippet(current_snippet, refreshed_snippet):
            updated["snippet"] = refreshed_snippet
        if _is_placeholder_policy_text(str(updated.get("snippet") or "")) or _is_generic_chapter_intro_text(str(updated.get("snippet") or "")):
            matched_rule_excerpt = _clean_policy_text(_best_grounding_result_excerpt(updated))
            if matched_rule_excerpt and not _is_placeholder_policy_text(matched_rule_excerpt):
                updated["snippet"] = matched_rule_excerpt
        refreshed_evidence.append(updated)
    if refreshed_evidence:
        refreshed_seed["hacc_evidence"] = refreshed_evidence

    if refreshed_passages and refreshed_evidence:
        evidence_by_key = {
            (
                str(item.get("title") or "").strip().lower(),
                str(item.get("source_path") or "").strip().lower(),
            ): str(item.get("snippet") or "")
            for item in refreshed_evidence
        }
        updated_passages: List[Dict[str, Any]] = []
        for passage in refreshed_passages:
            updated = dict(passage)
            key = (
                str(updated.get("title") or "").strip().lower(),
                str(updated.get("source_path") or "").strip().lower(),
            )
            evidence_snippet = evidence_by_key.get(key, "")
            if evidence_snippet and _should_promote_grounded_snippet(str(updated.get("snippet") or ""), evidence_snippet):
                updated["snippet"] = evidence_snippet
            updated_passages.append(updated)
        key_facts["anchor_passages"] = updated_passages

        passage_by_key = {
            (
                str(item.get("title") or "").strip().lower(),
                str(item.get("source_path") or "").strip().lower(),
            ): str(item.get("snippet") or "")
            for item in updated_passages
        }
        updated_evidence: List[Dict[str, Any]] = []
        for item in refreshed_evidence:
            updated = dict(item)
            key = (
                str(updated.get("title") or "").strip().lower(),
                str(updated.get("source_path") or "").strip().lower(),
            )
            passage_snippet = passage_by_key.get(key, "")
            if passage_snippet and _should_promote_grounded_snippet(str(updated.get("snippet") or ""), passage_snippet):
                updated["snippet"] = passage_snippet
            updated_evidence.append(updated)
        refreshed_seed["hacc_evidence"] = updated_evidence

    refreshed_seed["key_facts"] = key_facts
    return refreshed_seed


def _auto_discover_grounded_artifacts(results_path: Path) -> Dict[str, Path]:
    candidates = []
    parent = results_path.parent
    candidates.append(parent)
    if parent.name == "adversarial":
        candidates.append(parent.parent)

    discovered: Dict[str, Path] = {}
    for base in candidates:
        grounding = base / "grounding_bundle.json"
        upload = base / "evidence_upload_report.json"
        if grounding.exists():
            discovered["grounding_bundle"] = grounding
        if upload.exists():
            discovered["evidence_upload_report"] = upload
    return discovered


def _grounded_supporting_evidence(
    grounding_bundle: Dict[str, Any],
    upload_report: Dict[str, Any],
    *,
    limit: int = 5,
) -> List[str]:
    grouped: Dict[tuple[str, str], Dict[str, Any]] = {}
    for packet in list(grounding_bundle.get("mediator_evidence_packets") or [])[:limit]:
        label = str(packet.get("document_label") or packet.get("filename") or "Mediator evidence packet")
        relative_path = str(packet.get("relative_path") or packet.get("filename") or "").strip()
        source_path = str(packet.get("source_path") or "").strip()
        location = relative_path or source_path
        key = (label, location)
        grouped.setdefault(
            key,
            {
                "label": label,
                "location": location,
                "prepared": False,
                "uploaded": False,
                "claim_types": [],
            },
        )
        grouped[key]["prepared"] = True

    for upload in list(upload_report.get("uploads") or [])[:limit]:
        title = str(upload.get("title") or upload.get("relative_path") or "Uploaded evidence")
        relative_path = str(upload.get("relative_path") or "").strip()
        source_path = str(upload.get("source_path") or "").strip()
        result = dict(upload.get("result") or {})
        claim_type = str(result.get("claim_type") or "").strip()
        location = relative_path or source_path
        key = (title, location)
        grouped.setdefault(
            key,
            {
                "label": title,
                "location": location,
                "prepared": False,
                "uploaded": False,
                "claim_types": [],
            },
        )
        grouped[key]["uploaded"] = True
        if claim_type and claim_type not in grouped[key]["claim_types"]:
            grouped[key]["claim_types"].append(claim_type)

    lines: List[str] = []
    for item in grouped.values():
        status_parts: List[str] = []
        if item["prepared"]:
            status_parts.append("prepared as mediator evidence for grounded intake")
        if item["uploaded"]:
            upload_text = "uploaded into mediator evidence store"
            if item["claim_types"]:
                upload_text += f" for {', '.join(item['claim_types'])}"
            status_parts.append(upload_text)
        if not status_parts:
            continue
        line = f"{item['label']}: {'; '.join(status_parts)}"
        if item["location"]:
            line += f" ({item['location']})"
        lines.append(line)

    deduped: List[str] = []
    seen = set()
    for line in lines:
        normalized = re.sub(r"[^a-z0-9]+", " ", line.lower()).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(line)
        if len(deduped) >= limit:
            break
    return deduped


def _grounded_summary_lines(
    grounding_bundle: Dict[str, Any],
    upload_report: Dict[str, Any],
) -> List[str]:
    lines: List[str] = []
    query = str(grounding_bundle.get("query") or "").strip()
    claim_type = str(grounding_bundle.get("claim_type") or "").strip()
    if query:
        lines.append(f"Grounding query: {query}")
    if claim_type:
        lines.append(f"Grounding claim type: {claim_type}")
    upload_count = int(upload_report.get("upload_count") or 0)
    if upload_count:
        lines.append(f"Mediator preload / upload count: {upload_count}")
    support_summary = dict(upload_report.get("support_summary") or {})
    total_links = support_summary.get("total_links")
    if total_links not in (None, ""):
        lines.append(f"Claim-support links recorded: {total_links}")
    synthetic_prompts = dict(grounding_bundle.get("synthetic_prompts") or {})
    complaint_chatbot_prompt = str(synthetic_prompts.get("complaint_chatbot_prompt") or "").strip()
    if complaint_chatbot_prompt:
        lines.append(complaint_chatbot_prompt)
    return lines


def _looks_truncated_rule_text(text: str) -> bool:
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return False
    if len(cleaned) < 90:
        return True
    return bool(re.search(r"\b(?:may|must|shall|of|to|from|for|on|with|that|which|if|when|because|under)\.?$", cleaned, flags=re.IGNORECASE))


def _grounding_item_anchor_terms(item: Dict[str, Any], fallback_excerpt: str) -> List[str]:
    anchor_terms: List[str] = []
    title = str(item.get("title") or "").strip().lower()
    admin_plan_complaint_fallback = "administrative plan" in title and _is_complaint_process_text(fallback_excerpt)
    if admin_plan_complaint_fallback:
        curated_terms = [
            "Notice to the Applicant",
            "Scheduling an Informal Review",
            "Informal Review Procedures",
            "Informal Review Decision",
            "Notice of Denial or Termination of Assistance",
        ]
        deduped: List[str] = []
        seen = set()
        for term in curated_terms:
            normalized = term.lower()
            if normalized not in seen:
                seen.add(normalized)
                deduped.append(term)
        return deduped

    for rule in list(item.get("matched_rules") or [])[:4]:
        section_title = str(rule.get("section_title") or "").strip()
        rule_text = str(rule.get("text") or "").strip()
        if section_title:
            anchor_terms.append(section_title)
        if rule_text:
            anchor_terms.append(rule_text)

    if not anchor_terms:
        fallback_lower = fallback_excerpt.lower()
        if "informal review" in fallback_lower or "informal hearing" in fallback_lower:
            anchor_terms.extend(
                [
                    "Scheduling an Informal Review",
                    "Informal Review Procedures",
                    "Informal Hearing Process",
                ]
            )

    return _refresh_anchor_terms(anchor_terms, fallback_excerpt)


def _expand_grounding_result_from_source(item: Dict[str, Any], fallback_excerpt: str) -> str:
    source_path = str(item.get("source_path") or "").strip()
    if not source_path:
        return ""

    anchor_terms = _grounding_item_anchor_terms(item, fallback_excerpt)
    if not anchor_terms:
        return ""

    expanded = _extract_grounded_source_window(
        source_path=source_path,
        anchor_terms=anchor_terms,
        fallback_snippet=fallback_excerpt,
    )
    expanded = _trim_admin_plan_complaint_preamble(expanded)
    if not expanded or _is_probably_toc_text(expanded) or _is_placeholder_policy_text(expanded):
        return ""
    return expanded


def _best_grounding_result_excerpt(item: Dict[str, Any], max_chars: int = 420) -> str:
    snippet = " ".join(str(item.get("snippet") or "").split()).strip()
    rule_texts = [
        " ".join(str(rule.get("text") or "").split()).strip()
        for rule in list(item.get("matched_rules") or [])
        if str(rule.get("text") or "").strip()
    ]
    candidate_parts: List[str] = []
    if snippet and not _is_probably_toc_text(snippet) and not _is_placeholder_policy_text(snippet) and not _is_generic_chapter_intro_text(snippet):
        candidate_parts.append(snippet)
    for rule_text in rule_texts[:4]:
        if rule_text and rule_text not in candidate_parts:
            candidate_parts.append(rule_text)

    if not candidate_parts:
        candidate_parts = [snippet] if snippet else []

    if len(candidate_parts) >= 2 and _looks_truncated_rule_text(candidate_parts[0]):
        combined = "; ".join(candidate_parts[:2]).strip()
    elif candidate_parts:
        combined = candidate_parts[0]
    else:
        combined = ""

    expanded = _expand_grounding_result_from_source(item, combined)
    if expanded and _policy_text_quality(expanded) >= _policy_text_quality(combined) and len(expanded) > len(combined):
        combined = expanded

    effective_max_chars = max_chars
    if any(term in combined.lower() for term in ("definitions applicable to the grievance procedure", "elements of due process")):
        effective_max_chars = max(max_chars, 760)

    combined = re.sub(r"\s{2,}", " ", combined).strip(" ;,")
    if len(combined) > effective_max_chars:
        combined = combined[: effective_max_chars - 3].rstrip(" ,;:.") + "..."
    return combined


def _grounding_results_to_seed_evidence(grounding_bundle: Dict[str, Any], limit: int = 3) -> List[Dict[str, Any]]:
    search_payload = dict(grounding_bundle.get("search_payload") or {})
    results = list(search_payload.get("results") or [])
    evidence: List[Dict[str, Any]] = []
    for item in results[:limit]:
        excerpt = _best_grounding_result_excerpt(item)
        refreshed_excerpt = _refresh_snippet_from_source(
            str(item.get("source_path") or "").strip(),
            anchor_terms=_grounding_item_anchor_terms(item, excerpt),
            fallback_snippet=excerpt,
        )
        if _policy_text_quality(refreshed_excerpt) > _policy_text_quality(excerpt):
            excerpt = refreshed_excerpt
        evidence.append(
            {
                "title": str(item.get("title") or item.get("document_id") or "Grounding evidence"),
                "snippet": excerpt,
                "source_path": str(item.get("source_path") or "").strip(),
            }
        )
    return evidence


def _filter_grounding_evidence_for_seed(seed: Dict[str, Any], evidence_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    key_facts = dict(seed.get("key_facts") or {})
    anchor_titles = {str(item).strip().lower() for item in list(key_facts.get("anchor_titles") or []) if str(item).strip()}
    anchor_paths = {str(item).strip().lower() for item in list(key_facts.get("anchor_source_paths") or []) if str(item).strip()}
    if not anchor_titles and not anchor_paths:
        return evidence_items

    filtered: List[Dict[str, Any]] = []
    for item in evidence_items:
        title = str(item.get("title") or "").strip().lower()
        source_path = str(item.get("source_path") or "").strip().lower()
        if anchor_titles and title in anchor_titles:
            filtered.append(item)
            continue
        if anchor_paths and any(path and path in source_path for path in anchor_paths):
            filtered.append(item)
            continue
    return filtered or evidence_items
def _merge_seed_with_grounding(seed: Dict[str, Any], grounding_bundle: Dict[str, Any]) -> Dict[str, Any]:
    merged = _refresh_seed_source_snippets(dict(seed or {}))
    if not grounding_bundle:
        return merged

    key_facts = dict(merged.get("key_facts") or {})
    grounding_evidence = _filter_grounding_evidence_for_seed(
        merged,
        _grounding_results_to_seed_evidence(grounding_bundle),
    )
    current_summary = str(key_facts.get("evidence_summary") or merged.get("summary") or "").strip()

    if _is_probably_toc_text(current_summary):
        for item in grounding_evidence:
            candidate_summary = str(item.get("snippet") or "").strip()
            if candidate_summary and not _is_probably_toc_text(candidate_summary):
                key_facts["evidence_summary"] = candidate_summary
                merged["summary"] = candidate_summary
                break

    existing_evidence = list(merged.get("hacc_evidence") or [])
    if grounding_evidence:
        existing_by_key = {
            (
                str(item.get("title") or "").strip().lower(),
                str(item.get("source_path") or "").strip().lower(),
            ): dict(item)
            for item in existing_evidence
        }
        for item in grounding_evidence:
            key = (str(item.get("title") or "").strip().lower(), str(item.get("source_path") or "").strip().lower())
            current_item = existing_by_key.get(key)
            if current_item is None:
                existing_by_key[key] = dict(item)
                continue
            if _should_promote_grounded_snippet(str(current_item.get("snippet") or ""), str(item.get("snippet") or "")):
                updated_item = dict(current_item)
                updated_item["snippet"] = str(item.get("snippet") or "")
                if item.get("matched_rules"):
                    updated_item["matched_rules"] = list(item.get("matched_rules") or [])
                existing_by_key[key] = updated_item
        merged["hacc_evidence"] = list(existing_by_key.values())
        if merged["hacc_evidence"]:
            refreshed_by_key = {
                (
                    str(item.get("title") or "").strip().lower(),
                    str(item.get("source_path") or "").strip().lower(),
                ): str(item.get("snippet") or "")
                for item in merged["hacc_evidence"]
            }
            updated_passages: List[Dict[str, Any]] = []
            for passage in list(key_facts.get("anchor_passages") or []):
                updated = dict(passage)
                key = (
                    str(updated.get("title") or "").strip().lower(),
                    str(updated.get("source_path") or "").strip().lower(),
                )
                evidence_snippet = refreshed_by_key.get(key, "")
                if evidence_snippet and _should_promote_grounded_snippet(str(updated.get("snippet") or ""), evidence_snippet):
                    updated["snippet"] = evidence_snippet
                updated_passages.append(updated)
            if updated_passages:
                key_facts["anchor_passages"] = updated_passages
                passage_by_key = {
                    (
                        str(item.get("title") or "").strip().lower(),
                        str(item.get("source_path") or "").strip().lower(),
                    ): str(item.get("snippet") or "")
                    for item in updated_passages
                }
                synced_evidence: List[Dict[str, Any]] = []
                for item in list(merged.get("hacc_evidence") or []):
                    updated_item = dict(item)
                    key = (
                        str(updated_item.get("title") or "").strip().lower(),
                        str(updated_item.get("source_path") or "").strip().lower(),
                    )
                    passage_snippet = passage_by_key.get(key, "")
                    if passage_snippet and _should_promote_grounded_snippet(str(updated_item.get("snippet") or ""), passage_snippet):
                        updated_item["snippet"] = passage_snippet
                    synced_evidence.append(updated_item)
                merged["hacc_evidence"] = synced_evidence

    merged["key_facts"] = key_facts
    return merged


def _factual_allegations(seed: Dict[str, Any], session: Dict[str, Any], limit: int = 6) -> List[str]:
    key_facts = dict(seed.get("key_facts") or {})
    allegations: List[str] = []
    description = _normalize_incident_summary(seed.get("description") or key_facts.get("incident_summary") or "")
    protected_bases = [str(item) for item in list(key_facts.get("protected_bases") or []) if str(item)]
    if description:
        allegations.append(f"The complaint centers on {description.rstrip('.')}")
    if protected_bases:
        allegations.append(f"The intake and evidence record suggest a dispute implicating protected basis concerns related to {', '.join(protected_bases)}")

    for section in [str(item) for item in list(key_facts.get("anchor_sections") or []) if str(item)]:
        allegation = _section_allegation(section)
        if allegation:
            allegations.append(allegation)

    timeline_summaries: List[str] = []
    for fact in _collect_timeline_points(list(session.get("conversation_history") or []), limit=3):
        summarized_fact = _summarize_timeline_fact(fact)
        if summarized_fact:
            timeline_summaries.append(summarized_fact)

    for summarized_fact in _dedupe_timeline_summaries(timeline_summaries, limit=1):
        allegations.append(f"Timeline detail from intake: {summarized_fact}")

    return _dedupe_sentences(allegations, limit=limit)


def _claims_theory(seed: Dict[str, Any], session: Dict[str, Any], filing_forum: str = "court", limit: int = 6) -> List[str]:
    key_facts = dict(seed.get("key_facts") or {})
    sections = [str(item) for item in list(key_facts.get("anchor_sections") or []) if str(item)]
    theory_labels = [str(item) for item in list(key_facts.get("theory_labels") or []) if str(item)]
    protected_bases = [str(item) for item in list(key_facts.get("protected_bases") or []) if str(item)]
    authority_hints = _authority_hints_for_forum(seed, filing_forum)
    evidence_summary = _summarize_policy_excerpt(key_facts.get("evidence_summary") or seed.get("summary") or "")
    claims: List[str] = []

    if "proxy_discrimination" in theory_labels:
        claims.append("The current evidence suggests a proxy or criteria-based discrimination theory requiring closer review of how HACC framed and applied its policies")
    if "disparate_treatment" in theory_labels:
        claims.append("The current evidence suggests potentially unequal treatment in the way HACC applied policy or process requirements")
    if "reasonable_accommodation" in theory_labels or "disability_discrimination" in theory_labels:
        claims.append("The current evidence suggests a disability-related accommodation or fair-housing theory connected to the challenged process")
    if protected_bases:
        claims.append(f"The available record suggests the dispute may implicate protected basis concerns related to {', '.join(protected_bases)}")
    description = str(seed.get("description") or "").lower()
    intake_excerpt = " ".join(_conversation_facts(list(session.get("conversation_history") or []), limit=3)).lower()
    retaliation_flag = "retaliat" in description or "retaliat" in intake_excerpt
    authority_line = _authority_claim_line(authority_hints, sections, retaliation=retaliation_flag)
    if authority_line:
        claims.append(authority_line)
    combined_process_claim = _combined_process_claim(sections)
    if combined_process_claim:
        claims.append(combined_process_claim)
    else:
        if "adverse_action" in sections:
            claims.append("HACC appears to have pursued or upheld a denial or termination of assistance without a clearly documented and transparent adverse-action process")
        if "appeal_rights" in sections or "grievance_hearing" in sections:
            claims.append("The available policy language suggests the complainant should have received an informal review or hearing, written notice, and a review decision, but the intake narrative describes those protections as missing or unclear")
    if "reasonable_accommodation" in sections:
        claims.append("The intake and policy materials suggest a potential failure to provide or fairly evaluate reasonable accommodation within the adverse-action process")
    if "selection_criteria" in sections:
        claims.append("The record suggests HACC may have relied on opaque or inconsistently applied selection criteria")

    if retaliation_flag:
        claims.append("The complainant also describes a retaliation theory based on the timing of the adverse treatment after protected complaints or grievance activity")
    if evidence_summary:
        claims.append(f"The policy theory is grounded in HACC language stating that {evidence_summary}")

    return _dedupe_sentences(claims, limit=limit)


def _policy_basis(seed: Dict[str, Any], limit: int = 4) -> List[str]:
    key_facts = dict(seed.get("key_facts") or {})
    basis: List[str] = []
    for passage in list(key_facts.get("anchor_passages") or [])[:limit]:
        title = str(passage.get("title") or "Evidence")
        labels = ", ".join(_humanize_section(label) for label in list(passage.get("section_labels") or []))
        snippet = _clean_policy_text(passage.get("snippet") or "")
        summary = _summarize_policy_excerpt(snippet)
        tags = _evidence_tags(labels, summary, snippet)
        tag_prefix = f"[{', '.join(tags)}] " if tags else ""
        if not snippet:
            continue
        if labels:
            if summary and _should_include_full_passage(snippet, summary):
                basis.append(f"{title} supports {labels}: {tag_prefix}{summary} Full passage: {snippet}")
            else:
                basis.append(f"{title} supports {labels}: {tag_prefix}{summary or snippet}")
        else:
            if summary and _should_include_full_passage(snippet, summary):
                basis.append(f"{title}: {tag_prefix}{summary} Full passage: {snippet}")
            else:
                basis.append(f"{title}: {tag_prefix}{summary or snippet}")
    return basis


def _authority_hints_for_forum(seed: Dict[str, Any], filing_forum: str, limit: int = 3) -> List[str]:
    key_facts = dict(seed.get("key_facts") or {})
    hints = [str(item) for item in list(key_facts.get("authority_hints") or []) if str(item)]
    if filing_forum == "hud":
        preferred: List[str] = []
        remaining: List[str] = []
        for hint in hints:
            lowered = hint.lower()
            if "fair housing act" in lowered or "24 c.f.r." in lowered or "hud" in lowered:
                preferred.append(hint)
            else:
                remaining.append(hint)
        hints = preferred + remaining
    elif filing_forum == "court":
        primary = []
        secondary = []
        tertiary = []
        for hint in hints:
            lowered = hint.lower()
            if "section 504" in lowered or "americans with disabilities act" in lowered or lowered == "ada":
                if "section 504" in lowered:
                    primary.append(hint)
                else:
                    tertiary.append(hint)
            elif "fair housing act" in lowered or "24 c.f.r." in lowered or "hud" in lowered:
                secondary.append(hint)
            else:
                primary.append(hint)
        hints = primary + secondary + tertiary
    return hints[:limit]


def _authority_family(authority_hints: List[str]) -> str:
    normalized = " | ".join(authority_hints).lower()
    has_fha = "fair housing act" in normalized or "24 c.f.r. part 100" in normalized
    has_504 = "section 504" in normalized
    has_ada = "americans with disabilities act" in normalized or normalized == "ada"

    if has_fha and has_504 and has_ada:
        return "fha_504_ada"
    if has_fha and has_504:
        return "fha_504"
    if has_504 and has_ada:
        return "504_ada"
    if has_fha:
        return "fha"
    if has_504:
        return "504"
    if has_ada:
        return "ada"
    return "generic"


def _authority_key(authority_hint: str) -> str:
    lowered = str(authority_hint or "").lower()
    if "fair housing act" in lowered or "24 c.f.r." in lowered or "hud" in lowered:
        return "fha"
    if "section 504" in lowered:
        return "504"
    if "americans with disabilities act" in lowered or lowered.strip() == "ada":
        return "ada"
    return "generic"


def _dominant_authority_family(authority_hints: List[str], filing_forum: str) -> str:
    ordered = [_authority_key(hint) for hint in authority_hints if _authority_key(hint) != "generic"]
    if not ordered:
        return "generic"

    first = ordered[0]
    second = ordered[1] if len(ordered) > 1 else None

    if filing_forum == "hud":
        if first == "fha":
            if second == "504":
                return "fha_504"
            return "fha"
        if first == "504":
            if second == "ada":
                return "504_ada"
            if second == "fha":
                return "504_fha"
            return "504"
        if first == "ada":
            if second == "504":
                return "ada_504"
            return "ada"
    else:
        if first == "504":
            if second == "ada":
                return "504_ada"
            if second == "fha":
                return "504_fha"
            return "504"
        if first == "ada":
            if second == "504":
                return "ada_504"
            return "ada"
        if first == "fha":
            if second == "504":
                return "fha_504"
            return "fha"

    return first


def _normalize_incident_summary(text: str) -> str:
    cleaned = " ".join(str(text or "").split()).strip().rstrip(".")
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    if lowered == "retaliation complaint anchored to hacc core housing policies":
        return "a retaliation and grievance-related housing complaint involving HACC notice and review protections"
    if "anchored to hacc core housing policies" in lowered:
        return re.sub(
            r"\banchored to HACC core housing policies\b",
            "concerning HACC notice, grievance, and hearing protections",
            cleaned,
            flags=re.IGNORECASE,
        )
    if "anchored to the hacc administrative plan" in lowered:
        return re.sub(
            r"\banchored to the HACC Administrative Plan\b",
            "concerning HACC Administrative Plan grievance and notice protections",
            cleaned,
            flags=re.IGNORECASE,
        )
    return cleaned


def _section_allegation(section: str, *, narrative: bool = False) -> str:
    if section == "appeal_rights":
        if narrative:
            return "The intake record suggests HACC did not clearly provide the appeal rights and due-process protections described by policy."
        return "The complainant contends that appeal rights and due-process protections were not clearly honored"
    if section == "grievance_hearing":
        if narrative:
            return "The intake record suggests the grievance or hearing process was not handled in the manner described by HACC policy."
        return "The complainant contends that the grievance or hearing process was not handled in the manner described by HACC policy"
    if section == "adverse_action":
        if narrative:
            return "The intake record suggests HACC moved toward denial or termination of assistance without clear notice and documented process."
        return "The complainant contends that HACC moved toward denial or termination of assistance without clear notice and documented process"
    if section == "reasonable_accommodation":
        if narrative:
            return "The intake record suggests accommodation-related concerns were not fairly addressed within the HACC process."
        return "The complainant contends that accommodation-related concerns were not fairly addressed"
    if section == "selection_criteria":
        if narrative:
            return "The intake record suggests HACC relied on opaque or inconsistently applied criteria."
        return "The complainant contends that HACC relied on opaque or inconsistently applied criteria"
    if narrative:
        return f"The intake record suggests a dispute involving {_humanize_section(section)}."
    return ""


def _combined_section_narrative(sections: Sequence[str]) -> str:
    section_set = {str(section) for section in sections if str(section)}
    if {"grievance_hearing", "appeal_rights", "adverse_action"}.issubset(section_set):
        return (
            "The intake record suggests HACC moved toward denial or termination of assistance without clearly providing "
            "the grievance, appeal, and due-process protections described by policy."
        )
    narrative_items = [_section_allegation(section, narrative=True) for section in sections if _section_allegation(section, narrative=True)]
    if not narrative_items:
        return ""
    if len(narrative_items) == 1:
        return narrative_items[0]
    return narrative_items[0]


def _combined_process_claim(sections: Sequence[str]) -> str:
    section_set = {str(section) for section in sections if str(section)}
    if {"grievance_hearing", "appeal_rights", "adverse_action"}.issubset(section_set):
        return (
            "HACC appears to have pursued or upheld a denial or termination of assistance without clearly providing the "
            "written notice, grievance, informal review, and due-process protections described by policy."
        )
    return ""


def _missing_case_facts_line(sections: Sequence[str]) -> str:
    section_set = {str(section) for section in sections if str(section)}
    prompts: List[str] = ["the date and nature of the adverse action"]
    if "adverse_action" in section_set:
        prompts.append("the exact denial, termination, or loss of assistance that occurred")
    if {"grievance_hearing", "appeal_rights"} & section_set:
        prompts.append("whether written notice, an informal review, a grievance hearing, or an appeal was requested or denied")
    prompts.append("who at HACC made or communicated the decision")
    prompts.append("the resulting housing harm and requested remedy")

    ordered: List[str] = []
    seen = set()
    for item in prompts:
        if item not in seen:
            seen.add(item)
            ordered.append(item)

    return "Case-specific facts still need confirmation, including " + ", ".join(ordered) + "."


def _session_intake_priority_summary(session: Dict[str, Any]) -> Dict[str, Any]:
    final_state = session.get("final_state") if isinstance(session.get("final_state"), dict) else {}
    summary = final_state.get("adversarial_intake_priority_summary")
    return summary if isinstance(summary, dict) else {}


def _missing_case_facts_from_intake_priorities(session: Dict[str, Any]) -> List[str]:
    summary = _session_intake_priority_summary(session)
    uncovered = [
        str(item).strip()
        for item in list(summary.get("uncovered_objectives") or [])
        if str(item).strip()
    ]
    if not uncovered:
        return []

    mapping = {
        "anchor_adverse_action": "the exact denial, termination, threatened loss of assistance, or other adverse action HACC took or threatened",
        "timeline": "when the key events happened, including the complaint, notice, review or hearing request, and any denial or termination decision",
        "actors": "who at HACC made, communicated, or carried out each decision",
        "anchor_appeal_rights": "whether written notice, an informal review, a grievance hearing, or an appeal was provided, requested, denied, or ignored",
        "harm_remedy": "the resulting housing harm and the remedy now being requested",
        "intake_follow_up": "the additional case-specific details needed to complete the intake record",
    }
    prompts: List[str] = []
    for objective in uncovered:
        prompt = mapping.get(objective)
        if prompt and prompt not in prompts:
            prompts.append(prompt)
    return prompts


def _outstanding_intake_gaps(session: Dict[str, Any], limit: int = 5) -> List[str]:
    prompts = _missing_case_facts_from_intake_priorities(session)
    if not prompts:
        return []
    return prompts[:limit]


def _classify_intake_question_objective(question_text: Any) -> str:
    lowered = " ".join(str(question_text or "").split()).lower()
    if not lowered:
        return ""
    if any(token in lowered for token in ("when", "date", "timeline")):
        return "timeline"
    if any(token in lowered for token in ("who", "which person", "made, communicated", "carried out", "decision")):
        return "actors"
    if any(token in lowered for token in ("harm", "remedy", "loss", "relief")):
        return "harm_remedy"
    if any(token in lowered for token in ("written notice", "informal review", "grievance hearing", "appeal", "requested or denied")):
        return "anchor_appeal_rights"
    if any(token in lowered for token in ("adverse action", "denial", "termination", "loss of assistance")):
        return "anchor_adverse_action"
    return "intake_follow_up"


def _outstanding_intake_follow_up_questions(seed: Dict[str, Any], session: Dict[str, Any], limit: int = 5) -> List[str]:
    summary = _session_intake_priority_summary(session)
    uncovered = [
        str(item).strip()
        for item in list(summary.get("uncovered_objectives") or [])
        if str(item).strip()
    ]
    if not uncovered:
        return []

    key_facts = dict(seed.get("key_facts") or {})
    synthetic_prompts = dict(key_facts.get("synthetic_prompts") or {})
    intake_questions = [
        " ".join(str(item or "").split()).strip()
        for item in list(synthetic_prompts.get("intake_questions") or [])
        if " ".join(str(item or "").split()).strip()
    ]
    matched: List[str] = []
    for objective in uncovered:
        for question in intake_questions:
            if _classify_intake_question_objective(question) != objective:
                continue
            if question not in matched:
                matched.append(question)
            break
    return matched[:limit]


def _answered_intake_follow_up_items(worksheet: Dict[str, Any]) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for item in list(worksheet.get("follow_up_items") or []):
        if not isinstance(item, dict):
            continue
        question = " ".join(str(item.get("question") or "").split()).strip()
        answer = " ".join(str(item.get("answer") or "").split()).strip()
        if not question or not answer:
            continue
        items.append({"question": question, "answer": answer})
    return items


def _merge_completed_intake_worksheet(session: Dict[str, Any], worksheet: Dict[str, Any]) -> Dict[str, Any]:
    answered_items = _answered_intake_follow_up_items(worksheet)
    if not answered_items:
        return session

    merged_session = dict(session or {})
    conversation_history = list(merged_session.get("conversation_history") or [])
    final_state = dict(merged_session.get("final_state") or {})
    summary = dict(final_state.get("adversarial_intake_priority_summary") or {})
    covered = [str(item).strip() for item in list(summary.get("covered_objectives") or []) if str(item).strip()]
    uncovered = [str(item).strip() for item in list(summary.get("uncovered_objectives") or []) if str(item).strip()]
    counts = {
        str(key).strip(): int(value or 0)
        for key, value in dict(summary.get("objective_question_counts") or {}).items()
        if str(key).strip()
    }

    for item in answered_items:
        conversation_history.append(
            {
                "role": "complainant",
                "content": item["answer"],
                "source": "completed_intake_follow_up_worksheet",
                "question": item["question"],
            }
        )
        objective = _classify_intake_question_objective(item["question"])
        if objective:
            counts[objective] = counts.get(objective, 0) + 1
            if objective not in covered:
                covered.append(objective)
            uncovered = [value for value in uncovered if value != objective]

    summary["covered_objectives"] = covered
    summary["uncovered_objectives"] = uncovered
    summary["objective_question_counts"] = counts
    final_state["adversarial_intake_priority_summary"] = summary
    merged_session["conversation_history"] = conversation_history
    merged_session["final_state"] = final_state
    return merged_session


def _authority_claim_line(authority_hints: Sequence[str], sections: Sequence[str], *, retaliation: bool = False) -> str:
    hints = [str(item) for item in authority_hints if str(item)]
    if not hints:
        return ""
    hint_text = ", ".join(hints[:3])
    section_set = {str(section) for section in sections if str(section)}
    if retaliation and {"grievance_hearing", "appeal_rights", "adverse_action"} & section_set:
        return (
            f"{hint_text} may be implicated if HACC used grievance, review, or adverse-action procedures to respond to "
            "protected complaints or protected activity."
        )
    if {"grievance_hearing", "appeal_rights", "adverse_action"} & section_set:
        return f"{hint_text} may be implicated by the way HACC handled notice, grievance, review, and adverse-action protections."
    return f"Likely authority implicated by the current theory includes {hint_text}."


def _legal_theory_summary(seed: Dict[str, Any], filing_forum: str = "court") -> Dict[str, List[str]]:
    key_facts = dict(seed.get("key_facts") or {})
    return {
        "theory_labels": [str(item) for item in list(key_facts.get("theory_labels") or []) if str(item)],
        "protected_bases": [str(item) for item in list(key_facts.get("protected_bases") or []) if str(item)],
        "authority_hints": _authority_hints_for_forum(seed, filing_forum),
    }


def _draft_caption(seed: Dict[str, Any], filing_forum: str) -> Dict[str, str]:
    complaint_type = str(seed.get("type") or "civil_action").replace("_", " ").title()
    title = str(seed.get("description") or "Evidence-backed complaint draft").strip().rstrip(".")
    if filing_forum == "hud":
        return {
            "court": "HUD, U.S. Department of Housing and Urban Development, Office of Fair Housing and Equal Opportunity",
            "case_title": "Administrative Fair Housing Complaint",
            "document_title": f"Draft HUD Housing Discrimination Complaint",
            "caption_note": title or "Draft administrative housing complaint synthesized from HACC evidence",
        }
    if filing_forum == "state_agency":
        return {
            "court": "State civil rights or fair housing enforcement agency",
            "case_title": "Administrative Civil Rights Complaint",
            "document_title": f"Draft State Agency Complaint for {complaint_type}",
            "caption_note": title or "Draft state-agency complaint synthesized from HACC evidence",
        }
    return {
        "court": "Court to be determined",
        "case_title": f"Complainant v. Housing Authority of Clackamas County",
        "document_title": f"Draft Complaint for {complaint_type}",
        "caption_note": title or "Draft complaint synthesized from HACC evidence",
    }


def _draft_parties(filing_forum: str) -> Dict[str, str]:
    parties = dict(DEFAULT_PARTIES)
    if filing_forum in {"hud", "state_agency"}:
        parties["plaintiff"] = "Aggrieved person / complainant (name to be inserted)."
        parties["defendant"] = "Housing Authority of Clackamas County (HACC), respondent."
    return parties


def _section_labels_for_forum(filing_forum: str) -> Dict[str, str]:
    if filing_forum == "hud":
        return {
            "parties_plaintiff": "Complainant",
            "parties_defendant": "Respondent",
            "jurisdiction": "Administrative Jurisdiction",
            "claims_theory": "Administrative Theory",
            "policy_basis": "Administrative Basis",
            "causes": "Administrative Claims",
            "proposed_allegations": "Complainant Narrative",
            "relief": "Requested Administrative Relief",
        }
    if filing_forum == "state_agency":
        return {
            "parties_plaintiff": "Complainant",
            "parties_defendant": "Respondent",
            "jurisdiction": "Agency Jurisdiction",
            "claims_theory": "Agency Theory",
            "policy_basis": "Administrative Basis",
            "causes": "Administrative Claims",
            "proposed_allegations": "Complainant Narrative",
            "relief": "Requested Administrative Relief",
        }
    return {
        "parties_plaintiff": "Plaintiff",
        "parties_defendant": "Defendant",
        "jurisdiction": "Jurisdiction And Venue",
        "claims_theory": "Claims Theory",
        "policy_basis": "Policy Basis",
        "causes": "Causes Of Action",
        "proposed_allegations": "Proposed Allegations",
        "relief": "Requested Relief",
    }


def _jurisdiction_and_venue(seed: Dict[str, Any], filing_forum: str) -> List[str]:
    description = str(seed.get("description") or "").lower()
    if filing_forum == "hud":
        items = [
            "This draft is structured as an administrative housing-discrimination intake for HUD and should be tailored to the final statutory basis asserted.",
            "HUD jurisdiction and timeliness should be confirmed against the final incident dates, protected-basis theory, and requested relief.",
        ]
    elif filing_forum == "state_agency":
        items = [
            "This draft is structured as an administrative civil rights or fair housing complaint for a state enforcement agency.",
            "State filing deadlines, exhaustion rules, and venue requirements should be tailored to the specific agency and legal theory selected.",
        ]
    else:
        items = [
            "Jurisdiction and venue should be tailored to the final filing forum and the specific legal claims asserted.",
            "The current draft is grounded in HACC housing-policy evidence and is intended as a complaint-development scaffold rather than a filed pleading.",
        ]
    if "housing" in description:
        items.append("The dispute appears to arise from housing-program administration, adverse action, and procedural protections connected to HACC operations.")
    return items


def _causes_of_action(seed: Dict[str, Any], session: Dict[str, Any], filing_forum: str, limit: int = 5) -> List[Dict[str, Any]]:
    key_facts = dict(seed.get("key_facts") or {})
    sections = [str(item) for item in list(key_facts.get("anchor_sections") or []) if str(item)]
    theory_labels = [str(item) for item in list(key_facts.get("theory_labels") or []) if str(item)]
    protected_bases = [str(item) for item in list(key_facts.get("protected_bases") or []) if str(item)]
    authority_hints = _authority_hints_for_forum(seed, filing_forum)
    authority_family = _authority_family(authority_hints)
    dominant_authority_family = _dominant_authority_family(authority_hints, filing_forum)
    claims_theory = _claims_theory(seed, session, filing_forum, limit=limit)
    causes: List[Dict[str, Any]] = []

    notice_title = "Failure to Provide Required Notice and Process"
    retaliation_title = "Retaliation for Protected Complaint Activity"
    accommodation_title = "Failure to Fairly Address Accommodation Rights"
    fallback_title = "Policy and Process Violations Requiring Further Legal Framing"
    if filing_forum == "hud":
        notice_title = "Administrative Fair Housing Process Failure"
        retaliation_title = "Retaliation for Protected Fair Housing Activity"
        accommodation_title = "Failure to Reasonably Accommodate Disability-Related Rights"
        fallback_title = "Administrative Housing Rights Violations Requiring Further Legal Framing"
    elif filing_forum == "state_agency":
        notice_title = "State Civil Rights Process Failure"
        retaliation_title = "Retaliation for Protected Civil Rights Activity"
        accommodation_title = "Failure to Reasonably Accommodate Disability-Related Rights"
        fallback_title = "Administrative Civil Rights Violations Requiring Further Legal Framing"

    if "reasonable_accommodation" in sections:
        if filing_forum == "hud":
            if dominant_authority_family == "fha_504":
                accommodation_title = "Fair Housing Act / Section 504 Accommodation Theory"
            elif dominant_authority_family == "504_ada":
                accommodation_title = "Section 504 / ADA Accommodation Theory"
            elif dominant_authority_family == "504_fha":
                accommodation_title = "Section 504 / Fair Housing Accommodation Theory"
            elif dominant_authority_family == "ada_504":
                accommodation_title = "ADA / Section 504 Accommodation Theory"
            elif authority_family == "fha":
                accommodation_title = "Fair Housing Act Accommodation Theory"
            elif authority_family == "504":
                accommodation_title = "Section 504 Accommodation Theory"
            elif authority_family == "ada":
                accommodation_title = "ADA Accommodation Theory"
        else:
            if dominant_authority_family == "504_ada":
                accommodation_title = "Section 504 / ADA Accommodation Claim"
            elif dominant_authority_family == "504_fha":
                accommodation_title = "Section 504 / Fair Housing Accommodation Claim"
            elif dominant_authority_family == "fha_504":
                accommodation_title = "Fair Housing Act / Section 504 Accommodation Claim"
            elif dominant_authority_family == "ada_504":
                accommodation_title = "ADA / Section 504 Accommodation Claim"
            elif authority_family == "fha":
                accommodation_title = "Fair Housing Act Accommodation Claim"
            elif authority_family == "504":
                accommodation_title = "Section 504 Accommodation Claim"
            elif authority_family == "ada":
                accommodation_title = "ADA Accommodation Claim"

    if "adverse_action" in sections or "appeal_rights" in sections or "grievance_hearing" in sections:
        causes.append(
            {
                "title": notice_title,
                "theory": "The draft facts suggest denial or termination activity without the clear notice, review, or hearing process described by HACC policy.",
                "support": claims_theory[:2],
            }
        )
    if "retaliat" in str(seed.get("description") or "").lower() or any("retaliation" in item.lower() for item in claims_theory):
        causes.append(
            {
                "title": retaliation_title,
                "theory": "The complainant narrative suggests adverse treatment after raising concerns or invoking grievance protections.",
                "support": [item for item in claims_theory if "retaliation" in item.lower()] or claims_theory[:1],
            }
        )
    if "reasonable_accommodation" in sections:
        causes.append(
            {
                "title": accommodation_title,
                "theory": "The available record suggests accommodation-related issues may have intersected with adverse-action or review procedures.",
                "support": [item for item in claims_theory if "accommodation" in item.lower()] or claims_theory[:1],
            }
        )
    if "disparate_treatment" in theory_labels or "proxy_discrimination" in theory_labels or protected_bases:
        basis_text = f" involving {', '.join(protected_bases)}" if protected_bases else ""
        authority_text = f" Likely authority includes {', '.join(authority_hints[:2])}." if authority_hints else ""
        protected_basis_title = "Protected-Basis Discrimination Theory" if filing_forum == "court" else "Protected-Basis Administrative Theory"
        if protected_bases and dominant_authority_family in {"fha", "fha_504"}:
            protected_basis_title = (
                "Fair Housing Act Protected-Basis Theory"
                if filing_forum == "court"
                else "Fair Housing Act Protected-Basis Administrative Theory"
            )
        elif protected_bases and dominant_authority_family in {"504", "504_ada", "504_fha", "ada_504", "ada"}:
            protected_basis_title = (
                "Section 504 Protected-Basis Theory"
                if filing_forum == "court"
                else "Section 504 Protected-Basis Administrative Theory"
            )
        causes.append(
            {
                "title": protected_basis_title,
                "theory": f"The current evidence suggests HACC may have applied housing policy or process in a manner that warrants review for protected-basis discrimination{basis_text}.{authority_text}",
                "support": [item for item in claims_theory if "protected basis" in item.lower() or "unequal treatment" in item.lower() or "proxy" in item.lower()] or claims_theory[:2],
            }
        )
    if not causes:
        causes.append(
            {
                "title": fallback_title,
                "theory": "The current evidence supports further complaint development, but the final causes of action should be tailored to the filing forum and legal theory.",
                "support": claims_theory[:2],
            }
        )
    return causes[:limit]


def _requested_relief_for_forum(filing_forum: str) -> List[str]:
    if filing_forum == "hud":
        return [
            "Administrative investigation of the challenged housing practices and adverse-action process.",
            "Corrective action requiring clear notice, fair review, and non-retaliation safeguards.",
            "Appropriate administrative remedies, damages, and other relief authorized by fair housing law.",
            "Any additional relief HUD is authorized to obtain or recommend.",
        ]
    if filing_forum == "state_agency":
        return [
            "Agency investigation of the challenged housing or civil rights practices.",
            "Corrective action requiring clear notice, fair review, and non-retaliation safeguards.",
            "Available administrative damages, penalties, training, or policy changes authorized by state law.",
            "Any additional relief the agency is authorized to order or recommend.",
        ]
    return list(DEFAULT_RELIEF)


def _proposed_allegations(seed: Dict[str, Any], session: Dict[str, Any], filing_forum: str, limit: int = 8) -> List[str]:
    allegations: List[str] = []
    key_facts = dict(seed.get("key_facts") or {})
    incident_summary = _normalize_incident_summary(key_facts.get("incident_summary") or seed.get("description") or "")
    evidence_summary = _summarize_policy_excerpt(key_facts.get("evidence_summary") or seed.get("summary") or "")
    complainant_label = "Plaintiff"
    evidence_label = "The available HACC materials indicate"
    if filing_forum == "hud":
        complainant_label = "Complainant"
        evidence_label = "The available HACC materials suggest"
    elif filing_forum == "state_agency":
        complainant_label = "Complainant"
        evidence_label = "The available HACC materials indicate"
    if incident_summary:
        allegations.append(f"{complainant_label} alleges conduct arising from {incident_summary}.")
    if evidence_summary:
        allegations.append(f"{evidence_label} that {evidence_summary}")
    combined_narrative = _combined_section_narrative(list(key_facts.get("anchor_sections") or []))
    if combined_narrative:
        allegations.append(combined_narrative)
    summarized_facts: List[str] = []
    for fact in _conversation_facts(list(session.get("conversation_history") or []), limit=5):
        summary = _summarize_intake_fact(fact)
        if summary:
            summarized_facts.append(summary)
    if not summarized_facts:
        intake_priority_prompts = _missing_case_facts_from_intake_priorities(session)
        if intake_priority_prompts:
            allegations.append(
                "Case-specific facts still need confirmation, especially "
                + ", ".join(intake_priority_prompts)
                + "."
            )
        else:
            allegations.append(_missing_case_facts_line(list(key_facts.get("anchor_sections") or [])))
    for summary in _dedupe_fact_summaries(summarized_facts, limit=3):
        allegations.append(f"During intake, the complainant stated that {summary}")

    return _dedupe_sentences(allegations, limit=limit)


def _render_markdown(package: Dict[str, Any]) -> str:
    caption = dict(package.get("caption") or {})
    parties = dict(package.get("parties") or {})
    section_labels = _section_labels_for_forum(str(package.get("filing_forum") or "court"))
    all_exhibit_lines = (
        list(package["policy_basis"])
        + list(package["anchor_passages"])
        + list(package["supporting_evidence"])
    )
    exhibit_index = _build_exhibit_index(all_exhibit_lines)
    lines = [
        "# Draft Complaint Synthesis",
        "",
        f"- Generated: {package['generated_at']}",
        f"- Preset: {package['preset']}",
        f"- Session ID: {package['session_id']}",
        f"- Score: {package['critic_score']:.2f}",
        "",
        "## Summary",
        "",
        package["summary"],
        "",
    ]
    selection_rationale = dict(package.get("selection_rationale") or {})
    if selection_rationale:
        lines.extend([
            "## Selection Rationale",
            "",
        ])
        if selection_rationale.get("selected_preset"):
            lines.append(f"- Selected preset: {selection_rationale['selected_preset']}")
        if selection_rationale.get("claim_theory_families"):
            lines.append(f"- Selected theory families: {', '.join(selection_rationale['claim_theory_families'])}")
        if selection_rationale.get("tradeoff_note"):
            lines.append(f"- Why this preset won: {selection_rationale['tradeoff_note']}")
        if selection_rationale.get("runner_up_preset"):
            lines.append(f"- Runner-up preset: {selection_rationale['runner_up_preset']}")
        if selection_rationale.get("winner_only_theory_families"):
            lines.append(f"- Winner-only theory families: {', '.join(selection_rationale['winner_only_theory_families'])}")
        if selection_rationale.get("runner_up_only_theory_families"):
            lines.append(f"- Runner-up-only theory families: {', '.join(selection_rationale['runner_up_only_theory_families'])}")
        if selection_rationale.get("shared_theory_families"):
            lines.append(f"- Shared theory families: {', '.join(selection_rationale['shared_theory_families'])}")
        claim_posture_note = _selection_claim_posture_note(selection_rationale)
        if claim_posture_note:
            lines.append(f"- Claim posture note: {claim_posture_note}")
        relief_similarity_note = _selection_relief_similarity_note(selection_rationale)
        if relief_similarity_note:
            lines.append(f"- Relief posture note: {relief_similarity_note}")
        else:
            if selection_rationale.get("winner_relief_overview"):
                lines.append(f"- Winner relief overview: {selection_rationale['winner_relief_overview']}")
            if selection_rationale.get("runner_up_relief_overview"):
                lines.append(f"- Runner-up relief overview: {selection_rationale['runner_up_relief_overview']}")
        if selection_rationale.get("winner_only_relief_families"):
            lines.append(f"- Winner-only relief families: {', '.join(selection_rationale['winner_only_relief_families'])}")
        if selection_rationale.get("runner_up_only_relief_families"):
            lines.append(f"- Runner-up-only relief families: {', '.join(selection_rationale['runner_up_only_relief_families'])}")
        shared_relief_families = [str(item) for item in list(selection_rationale.get("shared_relief_families") or []) if str(item)]
        if shared_relief_families and shared_relief_families != ["other"]:
            lines.append(f"- Shared relief families: {', '.join(shared_relief_families)}")
        if selection_rationale.get("winner_only_claims"):
            lines.append(f"- Winner-only claims: {', '.join(selection_rationale['winner_only_claims'])}")
        if selection_rationale.get("runner_up_only_claims"):
            lines.append(f"- Runner-up-only claims: {', '.join(selection_rationale['runner_up_only_claims'])}")
        if selection_rationale.get("winner_only_relief"):
            lines.append(f"- Winner-only relief items: {', '.join(selection_rationale['winner_only_relief'])}")
        if selection_rationale.get("runner_up_only_relief"):
            lines.append(f"- Runner-up-only relief items: {', '.join(selection_rationale['runner_up_only_relief'])}")
        lines.extend([
            "",
        ])
    lines.extend([
        "## Draft Caption",
        "",
        f"- Court: {caption.get('court', '')}",
        f"- Case Title: {caption.get('case_title', '')}",
        f"- Document Title: {caption.get('document_title', '')}",
        f"- Note: {caption.get('caption_note', '')}",
        "",
        "## Parties",
        "",
        f"- {section_labels['parties_plaintiff']}: {parties.get('plaintiff', '')}",
        f"- {section_labels['parties_defendant']}: {parties.get('defendant', '')}",
        "",
        f"## {section_labels['jurisdiction']}",
        "",
    ])
    lines.extend(f"- {item}" for item in package["jurisdiction_and_venue"])
    lines.extend([
        "",
        "## Legal Theory Summary",
        "",
    ])
    theory_summary = dict(package.get("legal_theory_summary") or {})
    theory_labels = list(theory_summary.get("theory_labels") or [])
    protected_bases = list(theory_summary.get("protected_bases") or [])
    authority_hints = list(theory_summary.get("authority_hints") or [])
    lines.extend([f"- Theory Labels: {', '.join(theory_labels) if theory_labels else 'None identified'}"])
    lines.extend([f"- Protected Bases: {', '.join(protected_bases) if protected_bases else 'None identified'}"])
    lines.extend([f"- Authority Hints: {', '.join(authority_hints) if authority_hints else 'None identified'}"])
    grounded_summary = list(package.get("grounded_evidence_summary") or [])
    if grounded_summary:
        lines.extend([
            "",
            "## Grounded Evidence Run",
            "",
        ])
        lines.extend(f"- {item}" for item in grounded_summary)
    search_summary = dict(package.get("search_summary") or {})
    if search_summary:
        lines.extend([
            "",
            "## Search Summary",
            "",
        ])
        if search_summary.get("requested_search_mode") or search_summary.get("effective_search_mode"):
            lines.append(
                "- Search mode: requested={requested}; effective={effective}".format(
                    requested=search_summary.get("requested_search_mode") or "-",
                    effective=search_summary.get("effective_search_mode") or search_summary.get("requested_search_mode") or "-",
                )
            )
        if search_summary.get("fallback_note"):
            lines.append(f"- Search fallback: {search_summary['fallback_note']}")
    ordered_exhibits = _ordered_exhibit_index(all_exhibit_lines)
    claim_selection_summary = list(package.get("claim_selection_summary") or [])
    relief_selection_summary = list(package.get("relief_selection_summary") or [])
    lines.extend([
        "",
        "## Exhibit Index",
        "",
    ])
    lines.extend(f"- {exhibit_id}: {label}" for exhibit_id, label in ordered_exhibits)
    lines.extend([
        "",
        "## Claim Selection Summary",
        "",
    ])
    for item in claim_selection_summary:
        exhibits = [f"{entry.get('exhibit_id')}: {entry.get('label')}" for entry in list(item.get("selected_exhibits") or [])]
        tags = ", ".join(list(item.get("selection_tags") or [])) or "none"
        rationale = str(item.get("selection_rationale") or "none")
        lines.append(f"- {item.get('title', '')}: tags={tags}; exhibits={'; '.join(exhibits) if exhibits else 'none'}; rationale={rationale}")
    lines.extend([
        "",
    ])
    if relief_selection_summary:
        lines.extend([
            "## Relief Selection Summary",
            "",
        ])
        for item in relief_selection_summary:
            families = ", ".join(list(item.get("strategic_families") or [])) or "none"
            related_claims = ", ".join(list(item.get("related_claims") or [])) or "none"
            role = str(item.get("strategic_role") or "none")
            rationale = str(item.get("strategic_note") or "none")
            lines.append(
                f"- {item.get('text', '')}: families={families}; role={role}; related_claims={related_claims}; rationale={rationale}"
            )
        lines.extend([
            "",
        ])
    lines.extend([
        "## Factual Allegations",
        "",
    ])
    lines.extend(f"- {item}" for item in package["factual_allegations"])
    lines.extend([
        "",
        f"## {section_labels['claims_theory']}",
        "",
    ])
    lines.extend(f"- {item}" for item in package["claims_theory"])
    lines.extend([
        "",
        f"## {section_labels['policy_basis']}",
        "",
    ])
    lines.extend(_render_grouped_lines(list(package["policy_basis"]), "basis", exhibit_index))
    lines.extend([
        f"## {section_labels['causes']}",
        "",
    ])
    for cause in package["causes_of_action"]:
        lines.append(f"- {cause['title']}: {cause['theory']}")
        strategic_note = str(cause.get("strategic_note") or "").strip()
        if strategic_note:
            lines.append(f"  - Selection role: {strategic_note}")
        for support in list(cause.get("support") or []):
            lines.append(f"  - Support: {support}")
    lines.extend([
        "",
        f"## {section_labels['proposed_allegations']}",
        "",
    ])
    lines.extend(f"- {item}" for item in package["proposed_allegations"])
    outstanding_intake_gaps = [str(item) for item in list(package.get("outstanding_intake_gaps") or []) if str(item)]
    if outstanding_intake_gaps:
        lines.extend([
            "",
            "## Outstanding Intake Gaps",
            "",
        ])
        lines.extend(f"- {item}" for item in outstanding_intake_gaps)
    follow_up_questions = [str(item) for item in list(package.get("outstanding_intake_follow_up_questions") or []) if str(item)]
    if follow_up_questions:
        lines.extend([
            "",
            "## Follow-Up Questions",
            "",
        ])
        lines.extend(f"- {item}" for item in follow_up_questions)
    lines.extend([
        "",
        "## Anchor Sections",
        "",
    ])
    lines.extend(f"- {item}" for item in package["anchor_sections"])
    lines.extend([
        "",
        "## Anchor Passages",
        "",
    ])
    lines.extend(_render_grouped_lines(list(package["anchor_passages"]), "anchor", exhibit_index))
    lines.extend([
        "## Supporting Evidence",
        "",
    ])
    lines.extend(_render_grouped_lines(list(package["supporting_evidence"]), "supporting", exhibit_index))
    lines.extend([
        f"## {section_labels['relief']}",
        "",
    ])
    relief_annotations = list(package.get("requested_relief_annotations") or [])
    if relief_annotations:
        for item in relief_annotations:
            lines.append(f"- {item.get('text', '')}")
            strategic_note = str(item.get("strategic_note") or "").strip()
            if strategic_note:
                lines.append(f"  - Strategic role: {strategic_note}")
    else:
        lines.extend(f"- {item}" for item in package["requested_relief"])
    return "\n".join(lines) + "\n"


def _build_intake_follow_up_worksheet(package: Dict[str, Any]) -> Dict[str, Any]:
    gaps = [str(item) for item in list(package.get("outstanding_intake_gaps") or []) if str(item)]
    questions = [
        str(item)
        for item in list(package.get("outstanding_intake_follow_up_questions") or [])
        if str(item)
    ]
    follow_up_items: List[Dict[str, Any]] = []
    for index, question in enumerate(questions, start=1):
        gap = gaps[index - 1] if index - 1 < len(gaps) else ""
        follow_up_items.append(
            {
                "id": f"follow_up_{index:02d}",
                "gap": gap,
                "question": question,
                "answer": "",
                "status": "open",
            }
        )
    return {
        "generated_at": str(package.get("generated_at") or ""),
        "preset": str(package.get("preset") or ""),
        "session_id": str(package.get("session_id") or ""),
        "filing_forum": str(package.get("filing_forum") or ""),
        "summary": str(package.get("summary") or ""),
        "outstanding_intake_gaps": gaps,
        "follow_up_items": follow_up_items,
    }


def _render_intake_follow_up_worksheet_markdown(worksheet: Dict[str, Any]) -> str:
    lines = [
        "# Intake Follow-Up Worksheet",
        "",
        f"- Generated: {worksheet.get('generated_at', '')}",
        f"- Preset: {worksheet.get('preset', '')}",
        f"- Session ID: {worksheet.get('session_id', '')}",
        f"- Filing Forum: {worksheet.get('filing_forum', '')}",
        "",
    ]
    summary = str(worksheet.get("summary") or "").strip()
    if summary:
        lines.extend([
            "## Summary",
            "",
            summary,
            "",
        ])
    gaps = [str(item) for item in list(worksheet.get("outstanding_intake_gaps") or []) if str(item)]
    if gaps:
        lines.extend([
            "## Outstanding Intake Gaps",
            "",
        ])
        lines.extend(f"- {item}" for item in gaps)
        lines.append("")
    lines.extend([
        "## Follow-Up Items",
        "",
    ])
    items = list(worksheet.get("follow_up_items") or [])
    if not items:
        lines.append("- No additional follow-up questions were generated.")
    else:
        for item in items:
            lines.append(f"- {item.get('id', '')}: {item.get('question', '')}")
            gap = str(item.get("gap") or "").strip()
            if gap:
                lines.append(f"  - Gap: {gap}")
            lines.append(f"  - Status: {item.get('status', 'open')}")
            lines.append("  - Answer: ")
    return "\n".join(lines) + "\n"
def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Synthesize a draft complaint package from HACC adversarial matrix or results artifacts."
    )
    parser.add_argument(
        "--matrix-summary",
        default=None,
        help="Path to preset_matrix_summary.json; if provided, the script prefers the champion/challenger best_overall preset when available.",
    )
    parser.add_argument(
        "--results-json",
        default=None,
        help="Path to adversarial_results.json; required if --matrix-summary is not provided.",
    )
    parser.add_argument("--preset", default=None, help="Optional preset override when selecting the best session.")
    parser.add_argument(
        "--filing-forum",
        default="court",
        choices=FILING_FORUM_CHOICES,
        help="Target output style for the synthesized complaint.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for outputs; defaults next to the source artifact.",
    )
    parser.add_argument(
        "--completed-intake-worksheet",
        default=None,
        help="Optional completed intake_follow_up_worksheet.json whose answers should be merged back into the synthesized draft.",
    )
    parser.add_argument("--grounded-run-dir", default=None, help="Optional grounded pipeline run directory containing grounding_bundle.json and evidence_upload_report.json.")
    parser.add_argument("--grounding-bundle", default=None, help="Optional explicit grounding_bundle.json path.")
    parser.add_argument("--evidence-upload-report", default=None, help="Optional explicit evidence_upload_report.json path.")
    args = parser.parse_args(argv)

    matrix_payload = {}
    selection_source = "results_json"
    if args.matrix_summary:
        matrix_path = Path(args.matrix_summary).resolve()
        matrix_payload = _load_json(matrix_path)
        if not args.results_json:
            best_preset, selection_source = _best_preset_from_matrix(matrix_payload)
            best_preset = args.preset or best_preset
            if not best_preset:
                raise ValueError("Could not determine best preset from matrix summary")
            args.preset = best_preset
            if selection_source == "champion_challenger":
                args.results_json = str(matrix_path.parent / "champion_challenger" / best_preset / "adversarial_results.json")
            else:
                args.results_json = str(matrix_path.parent / best_preset / "adversarial_results.json")
    if not args.results_json:
        raise ValueError("Either --results-json or --matrix-summary must be provided")

    results_path = Path(args.results_json).resolve()
    results_payload = _load_json(results_path)
    grounded_run_dir = Path(args.grounded_run_dir).resolve() if args.grounded_run_dir else None
    auto_discovered = _auto_discover_grounded_artifacts(results_path if grounded_run_dir is None else grounded_run_dir / "adversarial" / "adversarial_results.json")
    grounding_bundle_path = (
        Path(args.grounding_bundle).resolve()
        if args.grounding_bundle
        else (grounded_run_dir / "grounding_bundle.json" if grounded_run_dir else auto_discovered.get("grounding_bundle"))
    )
    evidence_upload_report_path = (
        Path(args.evidence_upload_report).resolve()
        if args.evidence_upload_report
        else (grounded_run_dir / "evidence_upload_report.json" if grounded_run_dir else auto_discovered.get("evidence_upload_report"))
    )
    grounding_bundle = _load_optional_json(grounding_bundle_path)
    evidence_upload_report = _load_optional_json(evidence_upload_report_path)
    completed_intake_worksheet_path = Path(args.completed_intake_worksheet).resolve() if args.completed_intake_worksheet else None
    completed_intake_worksheet = _load_optional_json(completed_intake_worksheet_path)
    best_session = _pick_best_session(results_payload, preset=args.preset)
    best_session = _merge_completed_intake_worksheet(best_session, completed_intake_worksheet)
    seed = _merge_seed_with_grounding(dict(best_session.get("seed_complaint") or {}), grounding_bundle)
    search_summary = _extract_search_summary(seed, grounding_bundle, evidence_upload_report)
    key_facts = dict(seed.get("key_facts") or {})
    anchor_sections = [str(item) for item in list(key_facts.get("anchor_sections") or []) if str(item)]
    selection_rationale = _selection_rationale_from_matrix(matrix_payload, selection_source) if matrix_payload else {}
    cleaned_summary = _summarize_policy_excerpt(
        key_facts.get("evidence_summary") or seed.get("summary") or "No summary available."
    )
    cleaned_summary = _summary_with_selection_rationale(cleaned_summary, selection_rationale)

    package = {
        "generated_at": datetime.now(UTC).isoformat(),
        "preset": args.preset or ((seed.get("_meta", {}) or {}).get("hacc_preset")) or "unknown",
        "filing_forum": args.filing_forum,
        "session_id": best_session.get("session_id"),
        "critic_score": float((best_session.get("critic_score") or {}).get("overall_score", 0.0) or 0.0),
        "summary": cleaned_summary,
        "caption": _draft_caption(seed, args.filing_forum),
        "parties": _draft_parties(args.filing_forum),
        "jurisdiction_and_venue": _jurisdiction_and_venue(seed, args.filing_forum),
        "legal_theory_summary": _legal_theory_summary(seed, args.filing_forum),
        "anchor_sections": anchor_sections,
        "factual_allegations": _factual_allegations(seed, best_session),
        "claims_theory": _claims_theory(seed, best_session, args.filing_forum),
        "policy_basis": _policy_basis(seed),
        "causes_of_action": _causes_of_action(seed, best_session, args.filing_forum),
        "anchor_passages": _anchor_passage_lines(seed),
        "supporting_evidence": _dedupe_sentences(
            _evidence_lines(seed) + _grounded_supporting_evidence(grounding_bundle, evidence_upload_report),
            limit=8,
        ),
        "proposed_allegations": _proposed_allegations(seed, best_session, args.filing_forum),
        "outstanding_intake_gaps": _outstanding_intake_gaps(best_session),
        "outstanding_intake_follow_up_questions": _outstanding_intake_follow_up_questions(seed, best_session),
        "requested_relief": _requested_relief_for_forum(args.filing_forum),
        "grounded_evidence_summary": _grounded_summary_lines(grounding_bundle, evidence_upload_report),
        "search_summary": search_summary,
        "selection_rationale": selection_rationale,
        "source_artifacts": {
            "results_json": str(results_path),
            "matrix_summary": str(Path(args.matrix_summary).resolve()) if args.matrix_summary else None,
            "selection_source": selection_source,
            "grounded_run_dir": str(grounded_run_dir) if grounded_run_dir else None,
            "grounding_bundle_json": str(grounding_bundle_path) if grounding_bundle_path else None,
            "evidence_upload_report_json": str(evidence_upload_report_path) if evidence_upload_report_path else None,
            "completed_intake_worksheet_json": str(completed_intake_worksheet_path) if completed_intake_worksheet_path else None,
            "search_summary": search_summary,
        },
    }
    _inject_exhibit_references(package)
    package["causes_of_action"] = _annotate_causes_with_selection_rationale(
        list(package.get("causes_of_action") or []),
        selection_rationale,
    )
    package["requested_relief_annotations"] = _annotate_requested_relief_with_selection_rationale(
        list(package.get("requested_relief") or []),
        list(package.get("causes_of_action") or []),
        selection_rationale,
    )
    package["claim_selection_summary"] = _claim_selection_summary(list(package.get("causes_of_action") or []))
    package["relief_selection_summary"] = _relief_selection_summary(
        list(package.get("requested_relief_annotations") or [])
    )

    output_dir = Path(args.output_dir).resolve() if args.output_dir else results_path.parent / "complaint_synthesis"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "draft_complaint_package.json"
    md_path = output_dir / "draft_complaint_package.md"
    worksheet_json_path = output_dir / "intake_follow_up_worksheet.json"
    worksheet_md_path = output_dir / "intake_follow_up_worksheet.md"
    worksheet = _build_intake_follow_up_worksheet(package)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(package, handle, indent=2)
    md_path.write_text(_render_markdown(package), encoding="utf-8")
    with worksheet_json_path.open("w", encoding="utf-8") as handle:
        json.dump(worksheet, handle, indent=2)
    worksheet_md_path.write_text(_render_intake_follow_up_worksheet_markdown(worksheet), encoding="utf-8")

    print(f"Saved complaint synthesis artifacts to {output_dir}")
    print(f"Preset: {package['preset']}")
    print(f"Session ID: {package['session_id']}")
    print(f"Intake worksheet JSON: {worksheet_json_path}")
    print(f"Intake worksheet Markdown: {worksheet_md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
