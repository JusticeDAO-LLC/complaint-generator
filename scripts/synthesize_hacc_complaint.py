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
    return cleaned.strip()


def _to_sentence(text: Any) -> str:
    cleaned = _clean_policy_text(text)
    if not cleaned:
        return ""
    return cleaned if cleaned.endswith(".") else f"{cleaned}."


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


def _anchor_passage_lines(seed: Dict[str, Any], limit: int = 5) -> List[str]:
    key_facts = dict(seed.get("key_facts") or {})
    passages = list(key_facts.get("anchor_passages") or [])
    lines = []
    for passage in passages[:limit]:
        section_labels = ", ".join(list(passage.get("section_labels") or []))
        title = str(passage.get("title") or "Evidence")
        snippet = _clean_policy_text(passage.get("snippet") or "")
        if section_labels:
            lines.append(f"{title} [{section_labels}]: {snippet}")
        else:
            lines.append(f"{title}: {snippet}")
    return lines


def _evidence_lines(seed: Dict[str, Any], limit: int = 5) -> List[str]:
    evidence = list(seed.get("hacc_evidence") or [])
    lines = []
    for item in evidence[:limit]:
        title = str(item.get("title") or item.get("document_id") or "Evidence")
        snippet = _clean_policy_text(item.get("snippet") or "")
        source_path = str(item.get("source_path") or "")
        line = f"{title}: {snippet}"
        if source_path:
            line += f" ({source_path})"
        lines.append(line)
    return lines


def _factual_allegations(seed: Dict[str, Any], session: Dict[str, Any], limit: int = 6) -> List[str]:
    key_facts = dict(seed.get("key_facts") or {})
    allegations: List[str] = []
    description = str(seed.get("description") or key_facts.get("incident_summary") or "").strip()
    if description:
        allegations.append(f"The complaint centers on {description.rstrip('.')}")

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

    for fact in _collect_timeline_points(list(session.get("conversation_history") or []), limit=3):
        allegations.append(f"Timeline detail from intake: {fact}")

    return _dedupe_sentences(allegations, limit=limit)


def _claims_theory(seed: Dict[str, Any], session: Dict[str, Any], limit: int = 6) -> List[str]:
    key_facts = dict(seed.get("key_facts") or {})
    sections = [str(item) for item in list(key_facts.get("anchor_sections") or []) if str(item)]
    evidence_summary = _clean_policy_text(key_facts.get("evidence_summary") or seed.get("summary") or "")
    claims: List[str] = []

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
        if not snippet:
            continue
        if labels:
            basis.append(f"{title} supports {labels}: {snippet}")
        else:
            basis.append(f"{title}: {snippet}")
    return basis


def _draft_caption(seed: Dict[str, Any]) -> Dict[str, str]:
    complaint_type = str(seed.get("type") or "civil_action").replace("_", " ").title()
    title = str(seed.get("description") or "Evidence-backed complaint draft").strip().rstrip(".")
    return {
        "court": "Forum to be determined",
        "case_title": f"Complainant v. Housing Authority of Clackamas County",
        "document_title": f"Draft Complaint for {complaint_type}",
        "caption_note": title or "Draft complaint synthesized from HACC evidence",
    }


def _draft_parties() -> Dict[str, str]:
    return dict(DEFAULT_PARTIES)


def _jurisdiction_and_venue(seed: Dict[str, Any]) -> List[str]:
    description = str(seed.get("description") or "").lower()
    items = [
        "Jurisdiction and venue should be tailored to the final filing forum and the specific legal claims asserted.",
        "The current draft is grounded in HACC housing-policy evidence and is intended as a complaint-development scaffold rather than a filed pleading.",
    ]
    if "housing" in description:
        items.append("The dispute appears to arise from housing-program administration, adverse action, and procedural protections connected to HACC operations.")
    return items


def _causes_of_action(seed: Dict[str, Any], session: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
    key_facts = dict(seed.get("key_facts") or {})
    sections = [str(item) for item in list(key_facts.get("anchor_sections") or []) if str(item)]
    claims_theory = _claims_theory(seed, session, limit=limit)
    causes: List[Dict[str, Any]] = []

    if "adverse_action" in sections or "appeal_rights" in sections or "grievance_hearing" in sections:
        causes.append(
            {
                "title": "Failure to Provide Required Notice and Process",
                "theory": "The draft facts suggest denial or termination activity without the clear notice, review, or hearing process described by HACC policy.",
                "support": claims_theory[:2],
            }
        )
    if "retaliat" in str(seed.get("description") or "").lower() or any("retaliation" in item.lower() for item in claims_theory):
        causes.append(
            {
                "title": "Retaliation for Protected Complaint Activity",
                "theory": "The complainant narrative suggests adverse treatment after raising concerns or invoking grievance protections.",
                "support": [item for item in claims_theory if "retaliation" in item.lower()] or claims_theory[:1],
            }
        )
    if "reasonable_accommodation" in sections:
        causes.append(
            {
                "title": "Failure to Fairly Address Accommodation Rights",
                "theory": "The available record suggests accommodation-related issues may have intersected with adverse-action or review procedures.",
                "support": [item for item in claims_theory if "accommodation" in item.lower()] or claims_theory[:1],
            }
        )
    if not causes:
        causes.append(
            {
                "title": "Policy and Process Violations Requiring Further Legal Framing",
                "theory": "The current evidence supports further complaint development, but the final causes of action should be tailored to the filing forum and legal theory.",
                "support": claims_theory[:2],
            }
        )
    return causes[:limit]


def _proposed_allegations(seed: Dict[str, Any], session: Dict[str, Any], limit: int = 8) -> List[str]:
    allegations: List[str] = []
    key_facts = dict(seed.get("key_facts") or {})
    incident_summary = str(key_facts.get("incident_summary") or seed.get("description") or "").strip()
    evidence_summary = _clean_policy_text(key_facts.get("evidence_summary") or seed.get("summary") or "")
    if incident_summary:
        allegations.append(f"Plaintiff challenges conduct arising from {incident_summary}.")
    if evidence_summary:
        allegations.append(f"The available HACC materials indicate that {evidence_summary}")
    for section in list(key_facts.get("anchor_sections") or []):
        allegations.append(f"The intake record suggests a dispute involving {_humanize_section(section)}.")
    for fact in _conversation_facts(list(session.get("conversation_history") or []), limit=3):
        allegations.append(f"During intake, the complainant stated that {fact}")

    return _dedupe_sentences(allegations, limit=limit)


def _render_markdown(package: Dict[str, Any]) -> str:
    caption = dict(package.get("caption") or {})
    parties = dict(package.get("parties") or {})
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
        f"- Plaintiff: {parties.get('plaintiff', '')}",
        f"- Defendant: {parties.get('defendant', '')}",
        "",
        "## Jurisdiction And Venue",
        "",
    ]
    lines.extend(f"- {item}" for item in package["jurisdiction_and_venue"])
    lines.extend([
        "",
        "## Factual Allegations",
        "",
    ])
    lines.extend(f"- {item}" for item in package["factual_allegations"])
    lines.extend([
        "",
        "## Claims Theory",
        "",
    ])
    lines.extend(f"- {item}" for item in package["claims_theory"])
    lines.extend([
        "",
        "## Policy Basis",
        "",
    ])
    lines.extend(f"- {item}" for item in package["policy_basis"])
    lines.extend([
        "",
        "## Causes Of Action",
        "",
    ])
    for cause in package["causes_of_action"]:
        lines.append(f"- {cause['title']}: {cause['theory']}")
        for support in list(cause.get("support") or []):
            lines.append(f"  - Support: {support}")
    lines.extend([
        "",
        "## Proposed Allegations",
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
    lines.extend(f"- {item}" for item in package["anchor_passages"])
    lines.extend([
        "",
        "## Supporting Evidence",
        "",
    ])
    lines.extend(f"- {item}" for item in package["supporting_evidence"])
    lines.extend([
        "",
        "## Requested Relief",
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
    cleaned_summary = _clean_policy_text(key_facts.get("evidence_summary") or seed.get("summary") or "No summary available.")

    package = {
        "generated_at": datetime.now(UTC).isoformat(),
        "preset": args.preset or ((seed.get("_meta", {}) or {}).get("hacc_preset")) or "unknown",
        "session_id": best_session.get("session_id"),
        "critic_score": float((best_session.get("critic_score") or {}).get("overall_score", 0.0) or 0.0),
        "summary": cleaned_summary,
        "caption": _draft_caption(seed),
        "parties": _draft_parties(),
        "jurisdiction_and_venue": _jurisdiction_and_venue(seed),
        "anchor_sections": anchor_sections,
        "factual_allegations": _factual_allegations(seed, best_session),
        "claims_theory": _claims_theory(seed, best_session),
        "policy_basis": _policy_basis(seed),
        "causes_of_action": _causes_of_action(seed, best_session),
        "anchor_passages": _anchor_passage_lines(seed),
        "supporting_evidence": _evidence_lines(seed),
        "proposed_allegations": _proposed_allegations(seed, best_session),
        "requested_relief": list(DEFAULT_RELIEF),
        "source_artifacts": {
            "results_json": str(results_path),
            "matrix_summary": str(Path(args.matrix_summary).resolve()) if args.matrix_summary else None,
            "selection_source": selection_source,
        },
    }

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
