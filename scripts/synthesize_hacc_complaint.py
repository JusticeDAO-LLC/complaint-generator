import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


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


def _conversation_facts(conversation_history: List[Dict[str, Any]], limit: int = 8) -> List[str]:
    facts: List[str] = []
    for entry in conversation_history:
        if entry.get("role") != "complainant":
            continue
        content = " ".join(str(entry.get("content") or "").split())
        if not content:
            continue
        facts.append(content)
        if len(facts) >= limit:
            break
    return facts


def _clean_policy_text(text: Any) -> str:
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return cleaned
    cleaned = re.sub(r"^The strongest supporting material is '([^']+)'\.\s*", "", cleaned)
    cleaned = re.sub(r"^For this question, the strongest supporting material is '([^']+)'\.\s*", "", cleaned)
    cleaned = re.sub(r"^HACC Policy\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bHACC Policy\b(?=\s+HACC\b)\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def _to_sentence(text: Any) -> str:
    cleaned = _clean_policy_text(text)
    if not cleaned:
        return ""
    return cleaned if cleaned.endswith(".") else f"{cleaned}."


def _summarize_policy_excerpt(text: Any, max_sentences: int = 2, max_chars: int = 360) -> str:
    cleaned = _clean_policy_text(text)
    if not cleaned:
        return ""

    clause_hits: List[str] = []
    normalized_clauses = (
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
    combined = " ".join(
        [
            str(cause.get("title") or ""),
            str(cause.get("theory") or ""),
        ]
    ).lower()
    tags: List[str] = []
    if any(term in combined for term in ("accommodation", "disability", "section 504", "ada")):
        tags.extend(["reasonable_accommodation", "contact"])
    if any(term in combined for term in ("notice", "process", "hearing", "review", "appeal", "adverse-action", "adverse action", "termination", "denial")):
        tags.extend(["notice", "hearing", "adverse_action"])
    if any(term in combined for term in ("selection", "criteria", "proxy")):
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
        if not inserted_claim_ref and item.startswith("The strongest policy support for these theories is:"):
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
            if summary and summary != snippet:
                lines.append(f"{title} [{section_labels}]: {tag_prefix}{summary} Full passage: {snippet}")
            else:
                lines.append(f"{title} [{section_labels}]: {tag_prefix}{snippet}")
        else:
            if summary and summary != snippet:
                lines.append(f"{title}: {tag_prefix}{summary} Full passage: {snippet}")
            else:
                lines.append(f"{title}: {tag_prefix}{snippet}")
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
        if summary and summary != snippet:
            line = f"{title}: {tag_prefix}{summary} Full passage: {snippet}"
        else:
            line = f"{title}: {tag_prefix}{snippet}"
        if source_path:
            line += f" ({source_path})"
        lines.append(line)
    return lines


def _factual_allegations(seed: Dict[str, Any], session: Dict[str, Any], limit: int = 6) -> List[str]:
    key_facts = dict(seed.get("key_facts") or {})
    allegations: List[str] = []
    description = str(seed.get("description") or key_facts.get("incident_summary") or "").strip()
    protected_bases = [str(item) for item in list(key_facts.get("protected_bases") or []) if str(item)]
    if description:
        allegations.append(f"The complaint centers on {description.rstrip('.')}")
    if protected_bases:
        allegations.append(f"The intake and evidence record suggest a dispute implicating protected basis concerns related to {', '.join(protected_bases)}")

    for section in [str(item) for item in list(key_facts.get("anchor_sections") or []) if str(item)]:
        if section == "appeal_rights":
            allegations.append("The complainant contends that appeal rights and due-process protections were not clearly honored")
        elif section == "grievance_hearing":
            allegations.append("The complainant contends that the grievance or hearing process was not handled in the manner described by HACC policy")
        elif section == "adverse_action":
            allegations.append("The complainant contends that HACC moved toward denial or termination of assistance without clear notice and documented process")
        elif section == "reasonable_accommodation":
            allegations.append("The complainant contends that accommodation-related concerns were not fairly addressed")
        elif section == "selection_criteria":
            allegations.append("The complainant contends that HACC relied on opaque or inconsistently applied criteria")

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
    if authority_hints:
        claims.append(f"Likely authority implicated by the current theory includes {', '.join(authority_hints[:3])}")
    if "adverse_action" in sections:
        claims.append("HACC appears to have pursued or upheld a denial or termination of assistance without a clearly documented and transparent adverse-action process")
    if "appeal_rights" in sections or "grievance_hearing" in sections:
        claims.append("The available policy language suggests the complainant should have received an informal review or hearing, written notice, and a review decision, but the intake narrative describes those protections as missing or unclear")
    if "reasonable_accommodation" in sections:
        claims.append("The intake and policy materials suggest a potential failure to provide or fairly evaluate reasonable accommodation within the adverse-action process")
    if "selection_criteria" in sections:
        claims.append("The record suggests HACC may have relied on opaque or inconsistently applied selection criteria")

    description = str(seed.get("description") or "").lower()
    intake_excerpt = " ".join(_conversation_facts(list(session.get("conversation_history") or []), limit=3)).lower()
    if "retaliat" in description or "retaliat" in intake_excerpt:
        claims.append("The complainant also describes a retaliation theory based on the timing of the adverse treatment after protected complaints or grievance activity")
    if evidence_summary:
        claims.append(f"The strongest policy support for these theories is: {evidence_summary}")

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
            if summary and summary != snippet:
                basis.append(f"{title} supports {labels}: {tag_prefix}{summary} Full passage: {snippet}")
            else:
                basis.append(f"{title} supports {labels}: {tag_prefix}{snippet}")
        else:
            if summary and summary != snippet:
                basis.append(f"{title}: {tag_prefix}{summary} Full passage: {snippet}")
            else:
                basis.append(f"{title}: {tag_prefix}{snippet}")
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
    incident_summary = str(key_facts.get("incident_summary") or seed.get("description") or "").strip()
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
    for section in list(key_facts.get("anchor_sections") or []):
        allegations.append(f"The intake record suggests a dispute involving {_humanize_section(section)}.")
    summarized_facts: List[str] = []
    for fact in _conversation_facts(list(session.get("conversation_history") or []), limit=5):
        summary = _summarize_intake_fact(fact)
        if summary:
            summarized_facts.append(summary)
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
    ]
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
    ordered_exhibits = _ordered_exhibit_index(all_exhibit_lines)
    lines.extend([
        "",
        "## Exhibit Index",
        "",
    ])
    lines.extend(f"- {exhibit_id}: {label}" for exhibit_id, label in ordered_exhibits)
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
        for support in list(cause.get("support") or []):
            lines.append(f"  - Support: {support}")
    lines.extend([
        "",
        f"## {section_labels['proposed_allegations']}",
        "",
    ])
    lines.extend(f"- {item}" for item in package["proposed_allegations"])
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
    lines.extend(f"- {item}" for item in package["requested_relief"])
    return "\n".join(lines) + "\n"


def main() -> int:
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
    args = parser.parse_args()

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
    best_session = _pick_best_session(results_payload, preset=args.preset)
    seed = dict(best_session.get("seed_complaint") or {})
    key_facts = dict(seed.get("key_facts") or {})
    anchor_sections = [str(item) for item in list(key_facts.get("anchor_sections") or []) if str(item)]
    cleaned_summary = _summarize_policy_excerpt(
        key_facts.get("evidence_summary") or seed.get("summary") or "No summary available."
    )

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
        "supporting_evidence": _evidence_lines(seed),
        "proposed_allegations": _proposed_allegations(seed, best_session, args.filing_forum),
        "requested_relief": _requested_relief_for_forum(args.filing_forum),
        "source_artifacts": {
            "results_json": str(results_path),
            "matrix_summary": str(Path(args.matrix_summary).resolve()) if args.matrix_summary else None,
            "selection_source": selection_source,
        },
    }
    _inject_exhibit_references(package)

    output_dir = Path(args.output_dir).resolve() if args.output_dir else results_path.parent / "complaint_synthesis"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "draft_complaint_package.json"
    md_path = output_dir / "draft_complaint_package.md"

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(package, handle, indent=2)
    md_path.write_text(_render_markdown(package), encoding="utf-8")

    print(f"Saved complaint synthesis artifacts to {output_dir}")
    print(f"Preset: {package['preset']}")
    print(f"Session ID: {package['session_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
