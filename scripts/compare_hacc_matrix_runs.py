import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


def _load_summary(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _session_count(summary: Dict[str, Any]) -> int:
    rows = list(summary.get("rows") or [])
    if not rows:
        return 0
    counts = [int(row.get("total_sessions", 0) or 0) for row in rows if row.get("total_sessions") is not None]
    return max(counts) if counts else 0


def _winner(summary: Dict[str, Any]) -> str:
    recs = dict(summary.get("recommendations") or {})
    best = dict(recs.get("best_overall") or {})
    return str(best.get("preset") or "")


def _row_index(summary: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(row.get("preset") or ""): row for row in list(summary.get("rows") or [])}


def _search_modes(summary: Dict[str, Any]) -> List[Dict[str, str]]:
    modes: List[Dict[str, str]] = []
    for row in list(summary.get("rows") or []):
        modes.append(
            {
                "preset": str(row.get("preset") or ""),
                "requested": str(row.get("hacc_search_mode") or ""),
                "effective": str(row.get("effective_hacc_search_mode") or row.get("hacc_search_mode") or ""),
            }
        )
    return modes


def _compare_runs(run_specs: List[Dict[str, str]]) -> Dict[str, Any]:
    loaded_runs: List[Dict[str, Any]] = []
    all_presets: List[str] = []
    seen_presets = set()

    for spec in run_specs:
        summary_path = Path(spec["summary_path"]).resolve()
        summary = _load_summary(summary_path)
        rows = _row_index(summary)
        for preset in rows:
            if preset and preset not in seen_presets:
                seen_presets.add(preset)
                all_presets.append(preset)
        loaded_runs.append(
            {
                "label": spec["label"],
                "summary_path": str(summary_path),
                "session_count": _session_count(summary),
                "winner": _winner(summary),
                "rows": rows,
                "search_modes": _search_modes(summary),
            }
        )

    score_table: List[Dict[str, Any]] = []
    for preset in all_presets:
        row: Dict[str, Any] = {"preset": preset}
        for run in loaded_runs:
            payload = dict(run["rows"].get(preset) or {})
            row[run["label"]] = {
                "average_score": payload.get("average_score"),
                "successful_sessions": payload.get("successful_sessions"),
                "total_sessions": payload.get("total_sessions"),
                "anchor_coverage": payload.get("anchor_coverage"),
                "requested_search_mode": payload.get("hacc_search_mode"),
                "effective_search_mode": payload.get("effective_hacc_search_mode"),
                "claim_theory_families": payload.get("claim_theory_families") or [],
            }
        score_table.append(row)

    winner_sequence = [run["winner"] for run in loaded_runs if run["winner"]]
    comparison = {
        "runs": loaded_runs,
        "score_table": score_table,
        "winner_sequence": winner_sequence,
        "winner_changed": len(set(winner_sequence)) > 1,
        "consistent_search_modes": all(
            mode.get("requested") == "package" and mode.get("effective") == "package"
            for run in loaded_runs
            for mode in run["search_modes"]
        ),
    }
    return comparison


def _format_score(value: Any) -> str:
    if value is None:
        return "-"
    return f"{float(value):.4f}"


def _write_markdown(output_path: Path, comparison: Dict[str, Any]) -> None:
    runs = list(comparison.get("runs") or [])
    score_table = list(comparison.get("score_table") or [])
    winner_sequence = list(comparison.get("winner_sequence") or [])

    lines = [
        "# HACC Matrix Run Comparison",
        "",
        f"- Winner changed across runs: {'yes' if comparison.get('winner_changed') else 'no'}",
        f"- Search mode stayed package->package in all compared rows: {'yes' if comparison.get('consistent_search_modes') else 'no'}",
    ]
    if winner_sequence:
        lines.append(f"- Winner sequence: {' -> '.join(winner_sequence)}")
    lines.extend(["", "## Run Summary", ""])
    lines.extend([
        "| Run | Sessions | Winner | Summary Path |",
        "| --- | ---: | --- | --- |",
    ])
    for run in runs:
        lines.append(
            f"| {run['label']} | {run['session_count']} | {run['winner'] or '-'} | {run['summary_path']} |"
        )

    if runs and score_table:
        lines.extend(["", "## Preset Scores", ""])
        header = ["Preset"] + [run["label"] for run in runs]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join(["---"] + ["---:"] * len(runs)) + " |")
        for row in score_table:
            values = [row["preset"]]
            for run in runs:
                payload = dict(row.get(run["label"]) or {})
                score = _format_score(payload.get("average_score"))
                coverage = payload.get("anchor_coverage")
                coverage_text = "-" if coverage is None else f"{float(coverage):.2f}"
                search = payload.get("requested_search_mode") or "-"
                effective = payload.get("effective_search_mode") or search
                values.append(f"{score} / cov={coverage_text} / {search}->{effective}")
            lines.append("| " + " | ".join(values) + " |")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare HACC preset matrix summary runs.")
    parser.add_argument(
        "--run",
        action="append",
        required=True,
        help="Run spec in the form label=/absolute/path/to/preset_matrix_summary.json",
    )
    parser.add_argument("--output-json", required=True, help="Path to write the comparison JSON")
    parser.add_argument("--output-md", required=True, help="Path to write the comparison markdown")
    args = parser.parse_args()

    run_specs: List[Dict[str, str]] = []
    for entry in args.run:
        if "=" not in entry:
            raise ValueError(f"Invalid --run value: {entry}")
        label, summary_path = entry.split("=", 1)
        run_specs.append({"label": label.strip(), "summary_path": summary_path.strip()})

    comparison = _compare_runs(run_specs)
    output_json = Path(args.output_json).resolve()
    output_md = Path(args.output_md).resolve()
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")
    _write_markdown(output_md, comparison)
    print(f"Wrote comparison JSON to {output_json}")
    print(f"Wrote comparison markdown to {output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())