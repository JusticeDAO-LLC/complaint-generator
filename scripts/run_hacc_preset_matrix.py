import argparse
import csv
import importlib
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load_synthesis_module():
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    return importlib.import_module("synthesize_hacc_complaint")


def _load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _get_llm_router_backend_config(config: Dict[str, Any], backend_id: str | None) -> Dict[str, Any]:
    if not backend_id:
        raise ValueError("backend_id is required")

    backend_config = next(
        (backend for backend in config.get("BACKENDS", []) if backend.get("id") == backend_id),
        None,
    )
    if not backend_config:
        raise ValueError(f"Backend id not found in config.BACKENDS: {backend_id}")
    if backend_config.get("type") != "llm_router":
        raise ValueError(f"Backend {backend_id} must have type 'llm_router'")

    backend_kwargs = dict(backend_config)
    backend_kwargs.pop("type", None)
    return backend_kwargs


def _get_llm_router_backend_candidates(config: Dict[str, Any], backend_id: str | None) -> list[str]:
    if backend_id:
        return [backend_id]

    candidates = [value for value in config.get("MEDIATOR", {}).get("backends", []) if value]
    for backend in config.get("BACKENDS", []):
        candidate_id = str(backend.get("id") or "").strip()
        if candidate_id and backend.get("type") == "llm_router" and candidate_id not in candidates:
            candidates.append(candidate_id)
    return candidates


def _probe_backend_config(backend_kwargs: Dict[str, Any], probe_prompt: str) -> tuple[bool, str]:
    from backends import LLMRouterBackend

    try:
        response = LLMRouterBackend(**backend_kwargs)(probe_prompt)
    except Exception as exc:
        return False, str(exc)
    if not isinstance(response, str) or not response.strip():
        return False, "empty_generation"
    return True, ""


def _select_llm_router_backend_config(
    config: Dict[str, Any],
    backend_id: str | None,
    *,
    probe_prompt: str = "Reply with exactly OK.",
) -> tuple[str, Dict[str, Any], list[Dict[str, Any]], bool]:
    candidate_ids = _get_llm_router_backend_candidates(config, backend_id)
    if not candidate_ids:
        raise ValueError("No backend id specified and no llm_router backends are configured")

    probe_attempts: list[Dict[str, Any]] = []
    first_backend_id = candidate_ids[0]
    first_backend_kwargs = _get_llm_router_backend_config(config, first_backend_id)
    for candidate_id in candidate_ids:
        candidate_kwargs = _get_llm_router_backend_config(config, candidate_id)
        ok, error = _probe_backend_config(candidate_kwargs, probe_prompt)
        probe_attempts.append(
            {
                "backend_id": candidate_id,
                "ok": ok,
                "error": error,
            }
        )
        if ok:
            return candidate_id, candidate_kwargs, probe_attempts, True

    return first_backend_id, first_backend_kwargs, probe_attempts, False


def _select_matrix_recommendations(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    if not rows:
        return {}

    best_overall = max(rows, key=lambda row: (row["average_score"], row["anchor_coverage"]))
    best_anchor = max(rows, key=lambda row: (row["anchor_coverage"], row["average_score"]))
    best_balanced = max(
        rows,
        key=lambda row: ((row["average_score"] + row["anchor_coverage"]) / 2.0, row["average_score"]),
    )
    return {
        "best_overall": {
            "preset": best_overall["preset"],
            "average_score": best_overall["average_score"],
            "anchor_coverage": best_overall["anchor_coverage"],
        },
        "best_anchor_coverage": {
            "preset": best_anchor["preset"],
            "average_score": best_anchor["average_score"],
            "anchor_coverage": best_anchor["anchor_coverage"],
        },
        "best_balanced": {
            "preset": best_balanced["preset"],
            "average_score": best_balanced["average_score"],
            "anchor_coverage": best_balanced["anchor_coverage"],
        },
    }


def _attach_recommendation_claim_snapshots(
    recommendations: Dict[str, Dict[str, Any]],
    rows: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    if not recommendations:
        return {}

    row_by_preset = {str(row.get("preset") or ""): row for row in rows}
    enriched: Dict[str, Dict[str, Any]] = {}
    for key, payload in recommendations.items():
        item = dict(payload or {})
        preset = str(item.get("preset") or "")
        row = row_by_preset.get(preset, {})
        if row.get("claim_selection_overview"):
            item["claim_selection_overview"] = row["claim_selection_overview"]
        if row.get("synthesis_output_dir"):
            item["synthesis_output_dir"] = row["synthesis_output_dir"]
        enriched[key] = item
    return enriched


def _write_markdown_report(
    filepath: Path,
    rows: List[Dict[str, Any]],
    recommendations: Dict[str, Dict[str, Any]],
    champion_challenger: Dict[str, Any] | None = None,
) -> None:
    lines = [
        "# HACC Preset Matrix",
        "",
    ]
    if recommendations:
        lines.extend([
            "## Recommendations",
            "",
            f"- Best overall: `{recommendations['best_overall']['preset']}`",
            f"- Best anchor coverage: `{recommendations['best_anchor_coverage']['preset']}`",
            f"- Best balanced: `{recommendations['best_balanced']['preset']}`",
            "",
        ])
        best_overall = dict(recommendations.get("best_overall") or {})
        if best_overall.get("claim_selection_overview"):
            lines.extend([
                "### Best Overall Claim Snapshot",
                "",
                f"- Overview: {best_overall['claim_selection_overview']}",
            ])
            if best_overall.get("synthesis_output_dir"):
                lines.append(f"- Complaint synthesis: `{best_overall['synthesis_output_dir']}`")
            lines.extend(["",])
    lines.extend([
        "| Preset | Backend | Avg Score | Success | Anchor Coverage | Router | Top Missing Sections | Missing Sections | Output Dir |",
        "| --- | --- | ---: | ---: | ---: | --- | --- | --- | --- |",
    ])
    for row in rows:
        lines.append(
            "| {preset} | {backend_id} | {average_score:.2f} | {successful_sessions}/{total_sessions} | {anchor_coverage:.2f} | {router_status} | {top_missing_sections} | {missing_sections} | {output_dir} |".format(
                preset=row["preset"],
                backend_id=row.get("backend_id") or "-",
                average_score=row["average_score"],
                successful_sessions=row["successful_sessions"],
                total_sessions=row["total_sessions"],
                anchor_coverage=row["anchor_coverage"],
                router_status=row.get("router_status") or "-",
                top_missing_sections=row["top_missing_sections"] or "-",
                missing_sections=row["missing_sections"] or "-",
                output_dir=row["output_dir"],
            )
        )
    claim_snapshot_rows = [row for row in rows if row.get("claim_selection_overview")]
    if claim_snapshot_rows:
        lines.extend([
            "",
            "## Claim Selection Snapshots",
            "",
        ])
        for row in claim_snapshot_rows:
            lines.extend([
                f"### {row['preset']}",
                "",
                f"- Overview: {row['claim_selection_overview']}",
            ])
            synthesis_dir = row.get("synthesis_output_dir")
            if synthesis_dir:
                lines.append(f"- Complaint synthesis: `{synthesis_dir}`")
            lines.append("")
    champion = dict(champion_challenger or {})
    champion_recommendations = dict(champion.get("recommendations") or {})
    if champion_recommendations:
        lines.extend([
            "## Champion Challenger",
            "",
            f"- Reran top {champion.get('top_k_rerun')} presets with {champion.get('num_sessions')} sessions each.",
            f"- Best overall: `{champion_recommendations['best_overall']['preset']}`",
            f"- Best anchor coverage: `{champion_recommendations['best_anchor_coverage']['preset']}`",
            f"- Best balanced: `{champion_recommendations['best_balanced']['preset']}`",
        ])
        champion_best = dict(champion_recommendations.get("best_overall") or {})
        if champion_best.get("claim_selection_overview"):
            lines.extend([
                "",
                "### Champion Claim Snapshot",
                "",
                f"- Overview: {champion_best['claim_selection_overview']}",
            ])
            if champion_best.get("synthesis_output_dir"):
                lines.append(f"- Complaint synthesis: `{champion_best['synthesis_output_dir']}`")
        lines.append("")
    filepath.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _top_missing_sections(anchor_sections: Dict[str, Any], limit: int = 3) -> str:
    missing_counts = dict(anchor_sections.get("missing_counts", {}) or {})
    ranked = sorted(
        ((section, int(count or 0)) for section, count in missing_counts.items()),
        key=lambda item: (-item[1], item[0]),
    )
    top = ranked[:limit]
    return ", ".join(f"{section} ({count})" for section, count in top)


def _compact_claim_selection_summary(summary: List[Dict[str, Any]], limit: int = 3) -> str:
    parts: List[str] = []
    for item in summary[:limit]:
        title = str(item.get("title") or "Untitled claim").strip()
        tags = [str(tag) for tag in list(item.get("selection_tags") or []) if str(tag)]
        exhibits = [
            f"{entry.get('exhibit_id')}: {entry.get('label')}"
            for entry in list(item.get("selected_exhibits") or [])
            if entry.get("exhibit_id") and entry.get("label")
        ]
        rationale = str(item.get("selection_rationale") or "").strip()
        detail_parts = []
        if tags:
            detail_parts.append(f"tags={','.join(tags)}")
        if exhibits:
            detail_parts.append(f"exhibits={'; '.join(exhibits)}")
        if rationale:
            detail_parts.append(f"rationale={rationale}")
        if detail_parts:
            parts.append(f"{title} [{'; '.join(detail_parts)}]")
        else:
            parts.append(title)
    return " | ".join(parts)


def _synthesize_claim_selection_snapshot(
    *,
    preset: str,
    preset_dir: Path,
    filing_forum: str,
) -> Dict[str, Any]:
    synthesis = _load_synthesis_module()
    results_path = preset_dir / "adversarial_results.json"
    results_payload = synthesis._load_json(results_path)
    best_session = synthesis._pick_best_session(results_payload, preset=preset)
    seed = dict(best_session.get("seed_complaint") or {})
    key_facts = dict(seed.get("key_facts") or {})
    anchor_sections = [str(item) for item in list(key_facts.get("anchor_sections") or []) if str(item)]
    cleaned_summary = synthesis._summarize_policy_excerpt(
        key_facts.get("evidence_summary") or seed.get("summary") or "No summary available."
    )

    package = {
        "generated_at": datetime.now(UTC).isoformat(),
        "preset": preset or ((seed.get("_meta", {}) or {}).get("hacc_preset")) or "unknown",
        "filing_forum": filing_forum,
        "session_id": best_session.get("session_id"),
        "critic_score": float((best_session.get("critic_score") or {}).get("overall_score", 0.0) or 0.0),
        "summary": cleaned_summary,
        "caption": synthesis._draft_caption(seed, filing_forum),
        "parties": synthesis._draft_parties(filing_forum),
        "jurisdiction_and_venue": synthesis._jurisdiction_and_venue(seed, filing_forum),
        "legal_theory_summary": synthesis._legal_theory_summary(seed, filing_forum),
        "anchor_sections": anchor_sections,
        "factual_allegations": synthesis._factual_allegations(seed, best_session),
        "claims_theory": synthesis._claims_theory(seed, best_session, filing_forum),
        "policy_basis": synthesis._policy_basis(seed),
        "causes_of_action": synthesis._causes_of_action(seed, best_session, filing_forum),
        "anchor_passages": synthesis._anchor_passage_lines(seed),
        "supporting_evidence": synthesis._evidence_lines(seed),
        "proposed_allegations": synthesis._proposed_allegations(seed, best_session, filing_forum),
        "requested_relief": synthesis._requested_relief_for_forum(filing_forum),
        "source_artifacts": {
            "results_json": str(results_path),
            "matrix_summary": None,
            "selection_source": "matrix_preset_best_session",
        },
    }
    synthesis._inject_exhibit_references(package)
    package["claim_selection_summary"] = synthesis._claim_selection_summary(list(package.get("causes_of_action") or []))

    output_dir = preset_dir / "complaint_synthesis"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "draft_complaint_package.json").write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
    (output_dir / "draft_complaint_package.md").write_text(synthesis._render_markdown(package), encoding="utf-8")

    return {
        "claim_selection_summary": package["claim_selection_summary"],
        "claim_selection_overview": _compact_claim_selection_summary(package["claim_selection_summary"]),
        "synthesis_output_dir": str(output_dir),
    }


def _run_preset_batch(
    *,
    preset: str,
    preset_dir: Path,
    backend_id: str,
    backend_kwargs: Dict[str, Any],
    backend_probe_attempts: List[Dict[str, Any]],
    selected_backend_healthy: bool,
    embeddings_config: Dict[str, Any] | None,
    num_sessions: int,
    hacc_count: int,
    max_turns: int,
    max_parallel: int,
    use_vector_search: bool,
    probe_llm_router: bool,
    probe_embeddings_router: bool,
    disable_local_ipfs_fallback: bool,
    synthesis_filing_forum: str,
) -> Dict[str, Any]:
    from adversarial_harness import AdversarialHarness, Optimizer
    from backends import LLMRouterBackend
    from integrations.ipfs_datasets import ensure_ipfs_backend, get_router_status_report
    from mediator.mediator import Mediator

    session_state_dir = preset_dir / "sessions"
    preset_dir.mkdir(parents=True, exist_ok=True)
    session_state_dir.mkdir(parents=True, exist_ok=True)
    if not disable_local_ipfs_fallback:
        ensure_ipfs_backend(prefer_local_fallback=True)
    router_report = get_router_status_report(
        llm_config=backend_kwargs,
        embeddings_config=embeddings_config,
        probe_llm=probe_llm_router,
        probe_embeddings=probe_embeddings_router,
        probe_text=f"HACC preset matrix router health check for {preset}",
    )

    complainant_backend = LLMRouterBackend(**backend_kwargs)
    critic_backend = LLMRouterBackend(**backend_kwargs)

    def mediator_factory(**kwargs):
        return Mediator(backends=[LLMRouterBackend(**backend_kwargs)], **kwargs)

    harness = AdversarialHarness(
        llm_backend_complainant=complainant_backend,
        llm_backend_critic=critic_backend,
        mediator_factory=mediator_factory,
        max_parallel=max_parallel,
        session_state_dir=str(session_state_dir),
    )

    results = harness.run_batch(
        num_sessions=num_sessions,
        max_turns_per_session=max_turns,
        include_hacc_evidence=True,
        hacc_count=hacc_count,
        hacc_preset=preset,
        use_hacc_vector_search=use_vector_search,
    )

    statistics = harness.get_statistics()
    optimizer_report = Optimizer().analyze(results).to_dict()
    harness.save_results(str(preset_dir / "adversarial_results.json"))
    harness.save_anchor_section_report(str(preset_dir / "anchor_section_coverage.csv"), format="csv")
    harness.save_anchor_section_report(str(preset_dir / "anchor_section_coverage.md"), format="markdown")
    with open(preset_dir / "optimizer_report.json", "w", encoding="utf-8") as handle:
        json.dump(optimizer_report, handle, indent=2)

    anchor_sections = statistics.get("anchor_sections", {}) or {}
    coverage_by_section = anchor_sections.get("coverage_by_section", {}) or {}
    coverage_rates = [
        float(payload.get("coverage_rate", 0.0))
        for payload in coverage_by_section.values()
        if isinstance(payload, dict)
    ]
    avg_anchor_coverage = sum(coverage_rates) / len(coverage_rates) if coverage_rates else 0.0
    missing_sections = ",".join(sorted((anchor_sections.get("missing_counts", {}) or {}).keys()))
    top_missing_sections = _top_missing_sections(anchor_sections)
    synthesis_snapshot = _synthesize_claim_selection_snapshot(
        preset=preset,
        preset_dir=preset_dir,
        filing_forum=synthesis_filing_forum,
    )

    return {
        "preset": preset,
        "backend_id": backend_id,
        "selected_backend_healthy": selected_backend_healthy,
        "average_score": float(statistics.get("average_score", 0.0) or 0.0),
        "successful_sessions": int(statistics.get("successful_sessions", 0) or 0),
        "total_sessions": int(statistics.get("total_sessions", 0) or 0),
        "anchor_coverage": avg_anchor_coverage,
        "top_missing_sections": top_missing_sections,
        "missing_sections": missing_sections,
        "output_dir": str(preset_dir),
        "router_status": str(router_report.get("status") or ""),
        "backend_probe_attempts": backend_probe_attempts,
        "router_report": router_report,
        "statistics": statistics,
        "optimizer_report": optimizer_report,
        "claim_selection_summary": synthesis_snapshot["claim_selection_summary"],
        "claim_selection_overview": synthesis_snapshot["claim_selection_overview"],
        "synthesis_output_dir": synthesis_snapshot["synthesis_output_dir"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run multiple HACC adversarial presets and write a comparison report."
    )
    parser.add_argument("--config", default="config.llm_router.json")
    parser.add_argument("--backend-id", default=None, help="Backend id from config.BACKENDS")
    parser.add_argument(
        "--presets",
        default="core_hacc_policies,accommodation_focus,administrative_plan_retaliation",
        help="Comma-separated HACC presets to compare",
    )
    parser.add_argument("--num-sessions", type=int, default=3)
    parser.add_argument("--hacc-count", type=int, default=3)
    parser.add_argument("--max-turns", type=int, default=6)
    parser.add_argument("--max-parallel", type=int, default=2)
    parser.add_argument("--disable-local-ipfs-fallback", action="store_true")
    parser.add_argument("--probe-llm-router", action="store_true")
    parser.add_argument("--probe-embeddings-router", action="store_true")
    parser.add_argument(
        "--top-k-rerun",
        type=int,
        default=0,
        help="Rerun the top K presets from the initial matrix as champion/challenger candidates",
    )
    parser.add_argument(
        "--champion-sessions",
        type=int,
        default=0,
        help="If > 0, use this session count for the champion/challenger rerun",
    )
    parser.add_argument("--use-vector-search", action="store_true")
    parser.add_argument(
        "--synthesis-filing-forum",
        default="hud",
        choices=("court", "hud", "state_agency"),
        help="Forum style used for the per-preset synthesized complaint snapshots.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for outputs; defaults to output/hacc_preset_matrix/<timestamp>",
    )
    args = parser.parse_args()

    from adversarial_harness import HACC_QUERY_PRESETS

    requested_presets = [value.strip() for value in args.presets.split(",") if value.strip()]
    invalid_presets = [preset for preset in requested_presets if preset not in HACC_QUERY_PRESETS]
    if invalid_presets:
        raise ValueError(
            "Unknown presets: " + ", ".join(invalid_presets) +
            ". Available presets: " + ", ".join(sorted(HACC_QUERY_PRESETS.keys()))
        )

    logging.basicConfig(level=logging.INFO)
    config = _load_config(args.config)
    selected_backend_id, backend_kwargs, probe_attempts, selected_backend_healthy = _select_llm_router_backend_config(
        config,
        args.backend_id,
    )
    embeddings_config = config.get("EMBEDDINGS") if isinstance(config.get("EMBEDDINGS"), dict) else None

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir or (PROJECT_ROOT / "output" / "hacc_preset_matrix" / timestamp)).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    matrix_rows: List[Dict[str, Any]] = []
    full_results: List[Dict[str, Any]] = []

    for preset in requested_presets:
        preset_dir = output_dir / preset
        batch_result = _run_preset_batch(
            preset=preset,
            preset_dir=preset_dir,
            backend_id=selected_backend_id,
            backend_kwargs=backend_kwargs,
            backend_probe_attempts=probe_attempts,
            selected_backend_healthy=selected_backend_healthy,
            embeddings_config=embeddings_config,
            num_sessions=args.num_sessions,
            hacc_count=args.hacc_count,
            max_turns=args.max_turns,
            max_parallel=args.max_parallel,
            use_vector_search=args.use_vector_search,
            probe_llm_router=args.probe_llm_router,
            probe_embeddings_router=args.probe_embeddings_router,
            disable_local_ipfs_fallback=args.disable_local_ipfs_fallback,
            synthesis_filing_forum=args.synthesis_filing_forum,
        )
        row = {
            "preset": batch_result["preset"],
            "backend_id": batch_result["backend_id"],
            "average_score": batch_result["average_score"],
            "successful_sessions": batch_result["successful_sessions"],
            "total_sessions": batch_result["total_sessions"],
            "anchor_coverage": batch_result["anchor_coverage"],
            "router_status": batch_result["router_status"],
            "top_missing_sections": batch_result["top_missing_sections"],
            "missing_sections": batch_result["missing_sections"],
            "output_dir": batch_result["output_dir"],
            "claim_selection_overview": batch_result["claim_selection_overview"],
            "synthesis_output_dir": batch_result["synthesis_output_dir"],
        }
        matrix_rows.append(row)
        full_results.append(
            {
                "preset": preset,
                "backend_id": batch_result["backend_id"],
                "selected_backend_healthy": batch_result["selected_backend_healthy"],
                "backend_probe_attempts": batch_result["backend_probe_attempts"],
                "statistics": batch_result["statistics"],
                "optimizer_report": batch_result["optimizer_report"],
                "output_dir": batch_result["output_dir"],
                "router_report": batch_result["router_report"],
                "claim_selection_summary": batch_result["claim_selection_summary"],
                "claim_selection_overview": batch_result["claim_selection_overview"],
                "synthesis_output_dir": batch_result["synthesis_output_dir"],
            }
        )

    matrix_rows.sort(key=lambda row: (-row["average_score"], -row["anchor_coverage"], row["preset"]))
    recommendations = _select_matrix_recommendations(matrix_rows)
    recommendations = _attach_recommendation_claim_snapshots(recommendations, matrix_rows)

    summary_json = output_dir / "preset_matrix_summary.json"
    summary_csv = output_dir / "preset_matrix_summary.csv"
    summary_md = output_dir / "preset_matrix_summary.md"
    challenger_summary = None

    if args.top_k_rerun > 0 and args.champion_sessions > 0 and matrix_rows:
        rerun_dir = output_dir / "champion_challenger"
        rerun_dir.mkdir(parents=True, exist_ok=True)
        challenger_rows: List[Dict[str, Any]] = []
        top_presets = [row["preset"] for row in matrix_rows[: args.top_k_rerun]]
        for preset in top_presets:
            batch_result = _run_preset_batch(
                preset=preset,
                preset_dir=rerun_dir / preset,
                backend_id=selected_backend_id,
                backend_kwargs=backend_kwargs,
                backend_probe_attempts=probe_attempts,
                selected_backend_healthy=selected_backend_healthy,
                embeddings_config=embeddings_config,
                num_sessions=args.champion_sessions,
                hacc_count=args.hacc_count,
                max_turns=args.max_turns,
                max_parallel=args.max_parallel,
                use_vector_search=args.use_vector_search,
                probe_llm_router=args.probe_llm_router,
                probe_embeddings_router=args.probe_embeddings_router,
                disable_local_ipfs_fallback=args.disable_local_ipfs_fallback,
                synthesis_filing_forum=args.synthesis_filing_forum,
            )
            challenger_rows.append(
                {
                    key: batch_result[key]
                    for key in (
                        "preset",
                        "backend_id",
                        "average_score",
                        "successful_sessions",
                        "total_sessions",
                        "anchor_coverage",
                        "top_missing_sections",
                        "missing_sections",
                        "output_dir",
                        "router_status",
                        "claim_selection_overview",
                        "synthesis_output_dir",
                    )
                }
            )
        challenger_rows.sort(key=lambda row: (-row["average_score"], -row["anchor_coverage"], row["preset"]))
        challenger_summary = {
            "num_sessions": args.champion_sessions,
            "top_k_rerun": args.top_k_rerun,
            "rows": challenger_rows,
            "recommendations": _attach_recommendation_claim_snapshots(
                _select_matrix_recommendations(challenger_rows),
                challenger_rows,
            ),
            "output_dir": str(rerun_dir),
        }

    with open(summary_json, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "presets": requested_presets,
                "recommendations": recommendations,
                "rows": matrix_rows,
                "details": full_results,
                "champion_challenger": challenger_summary,
            },
            handle,
            indent=2,
        )

    with open(summary_csv, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "preset",
                "backend_id",
                "average_score",
                "successful_sessions",
                "total_sessions",
                "anchor_coverage",
                "router_status",
                "top_missing_sections",
                "missing_sections",
                "output_dir",
                "claim_selection_overview",
                "synthesis_output_dir",
            ],
        )
        writer.writeheader()
        for row in matrix_rows:
            writer.writerow(row)

    _write_markdown_report(summary_md, matrix_rows, recommendations, challenger_summary)

    print(f"Saved preset matrix outputs to {output_dir}")
    if recommendations:
        print(
            "Recommendations: "
            f"best_overall={recommendations['best_overall']['preset']}, "
            f"best_anchor_coverage={recommendations['best_anchor_coverage']['preset']}, "
            f"best_balanced={recommendations['best_balanced']['preset']}"
        )
    for row in matrix_rows:
        print(
            f"{row['preset']}: score={row['average_score']:.2f}, "
            f"backend={row.get('backend_id') or '-'}, "
            f"anchor_coverage={row['anchor_coverage']:.2f}, "
            f"router={row.get('router_status') or '-'}, "
            f"top_missing={row['top_missing_sections'] or '-'}, "
            f"success={row['successful_sessions']}/{row['total_sessions']}"
        )
    if challenger_summary:
        challenger_recs = challenger_summary.get("recommendations") or {}
        print(
            "Champion/challenger: "
            f"reran top {args.top_k_rerun} presets with {args.champion_sessions} sessions each"
        )
        if challenger_recs:
            print(
                "Champion/challenger recommendations: "
                f"best_overall={challenger_recs['best_overall']['preset']}, "
                f"best_anchor_coverage={challenger_recs['best_anchor_coverage']['preset']}, "
                f"best_balanced={challenger_recs['best_balanced']['preset']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
