import argparse
import csv
import json
import logging
import os
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


def _write_markdown_report(filepath: Path, rows: List[Dict[str, Any]]) -> None:
    lines = [
        "# HACC Preset Matrix",
        "",
        "| Preset | Avg Score | Success | Anchor Coverage | Top Missing Sections | Missing Sections | Output Dir |",
        "| --- | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {preset} | {average_score:.2f} | {successful_sessions}/{total_sessions} | {anchor_coverage:.2f} | {top_missing_sections} | {missing_sections} | {output_dir} |".format(
                preset=row["preset"],
                average_score=row["average_score"],
                successful_sessions=row["successful_sessions"],
                total_sessions=row["total_sessions"],
                anchor_coverage=row["anchor_coverage"],
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
    parser.add_argument("--use-vector-search", action="store_true")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for outputs; defaults to output/hacc_preset_matrix/<timestamp>",
    )
    args = parser.parse_args()

    from adversarial_harness import AdversarialHarness, HACC_QUERY_PRESETS, Optimizer
    from backends import LLMRouterBackend
    from mediator.mediator import Mediator

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

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir or (PROJECT_ROOT / "output" / "hacc_preset_matrix" / timestamp)).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    matrix_rows: List[Dict[str, Any]] = []
    full_results: List[Dict[str, Any]] = []

    for preset in requested_presets:
        preset_dir = output_dir / preset
        session_state_dir = preset_dir / "sessions"
        preset_dir.mkdir(parents=True, exist_ok=True)
        session_state_dir.mkdir(parents=True, exist_ok=True)

        complainant_backend = LLMRouterBackend(**backend_kwargs)
        critic_backend = LLMRouterBackend(**backend_kwargs)

        def mediator_factory(**kwargs):
            return Mediator(backends=[LLMRouterBackend(**backend_kwargs)], **kwargs)

        harness = AdversarialHarness(
            llm_backend_complainant=complainant_backend,
            llm_backend_critic=critic_backend,
            mediator_factory=mediator_factory,
            max_parallel=args.max_parallel,
            session_state_dir=str(session_state_dir),
        )

        results = harness.run_batch(
            num_sessions=args.num_sessions,
            max_turns_per_session=args.max_turns,
            include_hacc_evidence=True,
            hacc_count=args.hacc_count,
            hacc_preset=preset,
            use_hacc_vector_search=args.use_vector_search,
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

        row = {
            "preset": preset,
            "average_score": float(statistics.get("average_score", 0.0) or 0.0),
            "successful_sessions": int(statistics.get("successful_sessions", 0) or 0),
            "total_sessions": int(statistics.get("total_sessions", 0) or 0),
            "anchor_coverage": avg_anchor_coverage,
            "top_missing_sections": top_missing_sections,
            "missing_sections": missing_sections,
            "output_dir": str(preset_dir),
        }
        matrix_rows.append(row)
        full_results.append(
            {
                "preset": preset,
                "statistics": statistics,
                "optimizer_report": optimizer_report,
                "output_dir": str(preset_dir),
            }
        )

    matrix_rows.sort(key=lambda row: (-row["average_score"], -row["anchor_coverage"], row["preset"]))

    summary_json = output_dir / "preset_matrix_summary.json"
    summary_csv = output_dir / "preset_matrix_summary.csv"
    summary_md = output_dir / "preset_matrix_summary.md"

    with open(summary_json, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "presets": requested_presets,
                "rows": matrix_rows,
                "details": full_results,
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
                "top_missing_sections",
                "missing_sections",
                "output_dir",
            ],
        )
        writer.writeheader()
        for row in matrix_rows:
            writer.writerow(row)

    _write_markdown_report(summary_md, matrix_rows)

    print(f"Saved preset matrix outputs to {output_dir}")
    for row in matrix_rows:
        print(
            f"{row['preset']}: score={row['average_score']:.2f}, "
            f"anchor_coverage={row['anchor_coverage']:.2f}, "
            f"top_missing={row['top_missing_sections'] or '-'}, "
            f"success={row['successful_sessions']}/{row['total_sessions']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
