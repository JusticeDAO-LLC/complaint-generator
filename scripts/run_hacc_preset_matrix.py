import argparse
import csv
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _get_llm_router_backend_config(config: Dict[str, Any], backend_id: str | None) -> Dict[str, Any]:
    backend_ids = config.get("MEDIATOR", {}).get("backends", [])
    if not backend_id:
        backend_id = backend_ids[0] if backend_ids else None
    if not backend_id:
        raise ValueError("No backend id specified and config.MEDIATOR.backends is empty")

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


def _write_markdown_report(filepath: Path, rows: List[Dict[str, Any]], recommendations: Dict[str, Dict[str, Any]]) -> None:
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
    lines.extend([
        "| Preset | Avg Score | Success | Anchor Coverage | Router | Top Missing Sections | Missing Sections | Output Dir |",
        "| --- | ---: | ---: | ---: | --- | --- | --- | --- |",
    ])
    for row in rows:
        lines.append(
            "| {preset} | {average_score:.2f} | {successful_sessions}/{total_sessions} | {anchor_coverage:.2f} | {router_status} | {top_missing_sections} | {missing_sections} | {output_dir} |".format(
                preset=row["preset"],
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
    filepath.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _top_missing_sections(anchor_sections: Dict[str, Any], limit: int = 3) -> str:
    missing_counts = dict(anchor_sections.get("missing_counts", {}) or {})
    ranked = sorted(
        ((section, int(count or 0)) for section, count in missing_counts.items()),
        key=lambda item: (-item[1], item[0]),
    )
    top = ranked[:limit]
    return ", ".join(f"{section} ({count})" for section, count in top)


def _run_preset_batch(
    *,
    preset: str,
    preset_dir: Path,
    backend_kwargs: Dict[str, Any],
    embeddings_config: Dict[str, Any] | None,
    num_sessions: int,
    hacc_count: int,
    max_turns: int,
    max_parallel: int,
    use_vector_search: bool,
    probe_llm_router: bool,
    probe_embeddings_router: bool,
) -> Dict[str, Any]:
    from adversarial_harness import AdversarialHarness, Optimizer
    from backends import LLMRouterBackend
    from integrations.ipfs_datasets import get_router_status_report
    from mediator.mediator import Mediator

    session_state_dir = preset_dir / "sessions"
    preset_dir.mkdir(parents=True, exist_ok=True)
    session_state_dir.mkdir(parents=True, exist_ok=True)
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

    return {
        "preset": preset,
        "average_score": float(statistics.get("average_score", 0.0) or 0.0),
        "successful_sessions": int(statistics.get("successful_sessions", 0) or 0),
        "total_sessions": int(statistics.get("total_sessions", 0) or 0),
        "anchor_coverage": avg_anchor_coverage,
        "top_missing_sections": top_missing_sections,
        "missing_sections": missing_sections,
        "output_dir": str(preset_dir),
        "router_status": str(router_report.get("status") or ""),
        "router_report": router_report,
        "statistics": statistics,
        "optimizer_report": optimizer_report,
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
    backend_kwargs = _get_llm_router_backend_config(config, args.backend_id)
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
            backend_kwargs=backend_kwargs,
            embeddings_config=embeddings_config,
            num_sessions=args.num_sessions,
            hacc_count=args.hacc_count,
            max_turns=args.max_turns,
            max_parallel=args.max_parallel,
            use_vector_search=args.use_vector_search,
            probe_llm_router=args.probe_llm_router,
            probe_embeddings_router=args.probe_embeddings_router,
        )
        row = {
            key: batch_result[key]
            for key in (
                "preset",
                "average_score",
                "successful_sessions",
                "total_sessions",
                "anchor_coverage",
                "router_status",
                "top_missing_sections",
                "missing_sections",
                "output_dir",
                "router_status",
            )
        }
        matrix_rows.append(row)
        full_results.append(
            {
                "preset": preset,
                "statistics": batch_result["statistics"],
                "optimizer_report": batch_result["optimizer_report"],
                "output_dir": batch_result["output_dir"],
                "router_report": batch_result["router_report"],
            }
        )

    matrix_rows.sort(key=lambda row: (-row["average_score"], -row["anchor_coverage"], row["preset"]))
    recommendations = _select_matrix_recommendations(matrix_rows)

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
                backend_kwargs=backend_kwargs,
                embeddings_config=embeddings_config,
                num_sessions=args.champion_sessions,
                hacc_count=args.hacc_count,
                max_turns=args.max_turns,
                max_parallel=args.max_parallel,
                use_vector_search=args.use_vector_search,
                probe_llm_router=args.probe_llm_router,
                probe_embeddings_router=args.probe_embeddings_router,
            )
            challenger_rows.append(
                {
                    key: batch_result[key]
                    for key in (
                        "preset",
                        "average_score",
                        "successful_sessions",
                        "total_sessions",
                        "anchor_coverage",
                        "top_missing_sections",
                        "missing_sections",
                        "output_dir",
                        "router_status",
                    )
                }
            )
        challenger_rows.sort(key=lambda row: (-row["average_score"], -row["anchor_coverage"], row["preset"]))
        challenger_summary = {
            "num_sessions": args.champion_sessions,
            "top_k_rerun": args.top_k_rerun,
            "rows": challenger_rows,
            "recommendations": _select_matrix_recommendations(challenger_rows),
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
                "average_score",
                "successful_sessions",
                "total_sessions",
                "anchor_coverage",
                "router_status",
                "top_missing_sections",
                "missing_sections",
                "output_dir",
            ],
        )
        writer.writeheader()
        for row in matrix_rows:
            writer.writerow(row)

    _write_markdown_report(summary_md, matrix_rows, recommendations)

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
