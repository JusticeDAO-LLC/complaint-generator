import argparse
import json
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


def _anchor_passage_lines(seed: Dict[str, Any], limit: int = 5) -> List[str]:
    key_facts = dict(seed.get("key_facts") or {})
    passages = list(key_facts.get("anchor_passages") or [])
    lines = []
    for passage in passages[:limit]:
        section_labels = ", ".join(list(passage.get("section_labels") or []))
        title = str(passage.get("title") or "Evidence")
        snippet = " ".join(str(passage.get("snippet") or "").split())
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
        snippet = " ".join(str(item.get("snippet") or "").split())
        source_path = str(item.get("source_path") or "")
        line = f"{title}: {snippet}"
        if source_path:
            line += f" ({source_path})"
        lines.append(line)
    return lines


def _proposed_allegations(seed: Dict[str, Any], session: Dict[str, Any], limit: int = 8) -> List[str]:
    allegations: List[str] = []
    key_facts = dict(seed.get("key_facts") or {})
    incident_summary = str(key_facts.get("incident_summary") or seed.get("description") or "").strip()
    evidence_summary = str(key_facts.get("evidence_summary") or seed.get("summary") or "").strip()
    if incident_summary:
        allegations.append(f"Plaintiff challenges conduct arising from {incident_summary}.")
    if evidence_summary:
        allegations.append(f"The available HACC materials indicate that {evidence_summary}")
    for section in list(key_facts.get("anchor_sections") or []):
        allegations.append(f"The intake record suggests a dispute involving {str(section).replace('_', ' ')}.")
    for fact in _conversation_facts(list(session.get("conversation_history") or []), limit=4):
        allegations.append(f"During intake, the complainant stated: {fact}")

    deduped: List[str] = []
    seen = set()
    for allegation in allegations:
        cleaned = allegation.strip()
        if not cleaned:
            continue
        marker = cleaned.lower()
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(cleaned if cleaned.endswith(".") else f"{cleaned}.")
        if len(deduped) >= limit:
            break
    return deduped


def _render_markdown(package: Dict[str, Any]) -> str:
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
        "## Proposed Allegations",
        "",
    ]
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

    package = {
        "generated_at": datetime.now(UTC).isoformat(),
        "preset": args.preset or ((seed.get("_meta", {}) or {}).get("hacc_preset")) or "unknown",
        "session_id": best_session.get("session_id"),
        "critic_score": float((best_session.get("critic_score") or {}).get("overall_score", 0.0) or 0.0),
        "summary": str(key_facts.get("evidence_summary") or seed.get("summary") or "No summary available."),
        "anchor_sections": anchor_sections,
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
