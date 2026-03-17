#!/usr/bin/env python3
"""Summarize mediator reranker metrics exports for canary rollout monitoring.

Input format is the JSON payload produced by:
    mediator.export_reranker_metrics_json(...)

Example:
    python scripts/summarize_reranker_metrics.py \
        --input statefiles/reranker_metrics_latest.json \
        --summary-out statefiles/reranker_metrics_latest.summary.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _pct(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return (numerator / denominator) * 100.0


def _fmt_ts(epoch: int) -> str:
    if epoch <= 0:
        return "unknown"
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def load_export(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Metrics payload must be a JSON object")
    if not isinstance(payload.get("metrics"), dict):
        raise ValueError("Metrics payload missing 'metrics' object")
    return payload


def build_summary(payload: Dict[str, Any], top_sources: int = 5) -> Dict[str, Any]:
    metrics = payload.get("metrics", {})
    by_source = metrics.get("by_source", {})

    total_runs = _safe_int(metrics.get("total_runs"))
    applied_runs = _safe_int(metrics.get("applied_runs"))
    skipped_runs = _safe_int(metrics.get("skipped_runs"))
    canary_runs = _safe_int(metrics.get("canary_enabled_runs"))
    latency_guard_runs = _safe_int(metrics.get("latency_guard_runs"))

    source_rows: List[Tuple[str, Dict[str, Any]]] = []
    if isinstance(by_source, dict):
        for source_name, row in by_source.items():
            if isinstance(row, dict):
                source_rows.append((str(source_name), row))

    source_rows.sort(
        key=lambda item: (
            -_safe_int(item[1].get("total_runs")),
            -_safe_int(item[1].get("applied_runs")),
            item[0],
        )
    )

    top_source_summaries = []
    for source_name, row in source_rows[: max(0, int(top_sources))]:
        src_total = _safe_int(row.get("total_runs"))
        src_applied = _safe_int(row.get("applied_runs"))
        src_skipped = _safe_int(row.get("skipped_runs"))
        top_source_summaries.append(
            {
                "source": source_name,
                "total_runs": src_total,
                "applied_runs": src_applied,
                "skipped_runs": src_skipped,
                "applied_rate_pct": round(_pct(src_applied, src_total), 2),
            }
        )

    summary = {
        "exported_at": _safe_int(payload.get("exported_at")),
        "window_resets": _safe_int(payload.get("window_resets")),
        "totals": {
            "total_runs": total_runs,
            "applied_runs": applied_runs,
            "skipped_runs": skipped_runs,
            "applied_rate_pct": round(_pct(applied_runs, total_runs), 2),
            "canary_enabled_runs": canary_runs,
            "canary_rate_pct": round(_pct(canary_runs, total_runs), 2),
            "latency_guard_runs": latency_guard_runs,
            "latency_guard_rate_pct": round(_pct(latency_guard_runs, total_runs), 2),
            "avg_boost": round(_safe_float(metrics.get("avg_boost")), 6),
            "avg_elapsed_ms": round(_safe_float(metrics.get("avg_elapsed_ms")), 3),
        },
        "timestamps": {
            "first_seen_at": _safe_int(metrics.get("first_seen_at")),
            "last_updated_at": _safe_int(metrics.get("last_updated_at")),
            "last_reset_at": _safe_int(metrics.get("last_reset_at")),
            "first_seen_at_iso": _fmt_ts(_safe_int(metrics.get("first_seen_at"))),
            "last_updated_at_iso": _fmt_ts(_safe_int(metrics.get("last_updated_at"))),
            "last_reset_at_iso": _fmt_ts(_safe_int(metrics.get("last_reset_at"))),
            "exported_at_iso": _fmt_ts(_safe_int(payload.get("exported_at"))),
        },
        "top_sources": top_source_summaries,
    }

    return summary


def render_text(summary: Dict[str, Any]) -> str:
    totals = summary.get("totals", {})
    timestamps = summary.get("timestamps", {})
    lines = [
        "Reranker Metrics Summary",
        "========================",
        f"Total runs:           {totals.get('total_runs', 0)}",
        f"Applied runs:         {totals.get('applied_runs', 0)} ({totals.get('applied_rate_pct', 0.0):.2f}%)",
        f"Skipped runs:         {totals.get('skipped_runs', 0)}",
        f"Canary enabled runs:  {totals.get('canary_enabled_runs', 0)} ({totals.get('canary_rate_pct', 0.0):.2f}%)",
        f"Latency-guard runs:   {totals.get('latency_guard_runs', 0)} ({totals.get('latency_guard_rate_pct', 0.0):.2f}%)",
        f"Average boost:        {totals.get('avg_boost', 0.0):.6f}",
        f"Average elapsed ms:   {totals.get('avg_elapsed_ms', 0.0):.3f}",
        f"Window resets:        {summary.get('window_resets', 0)}",
        "",
        f"First seen:           {timestamps.get('first_seen_at_iso', 'unknown')}",
        f"Last updated:         {timestamps.get('last_updated_at_iso', 'unknown')}",
        f"Last reset:           {timestamps.get('last_reset_at_iso', 'unknown')}",
        f"Exported at:          {timestamps.get('exported_at_iso', 'unknown')}",
        "",
        "Top sources:",
    ]

    top_sources = summary.get("top_sources", [])
    if not top_sources:
        lines.append("  - none")
    else:
        for row in top_sources:
            lines.append(
                "  - {source}: total={total_runs}, applied={applied_runs}, skipped={skipped_runs}, "
                "applied_rate={applied_rate_pct:.2f}%".format(**row)
            )

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize reranker metrics exports")
    parser.add_argument("--input", required=True, help="Path to exported reranker metrics JSON")
    parser.add_argument(
        "--summary-out",
        default=None,
        help="Optional path to write summary JSON (default: no file write)",
    )
    parser.add_argument(
        "--top-sources",
        type=int,
        default=5,
        help="Number of top sources to include in summary (default: 5)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)

    if not input_path.exists():
        raise FileNotFoundError(f"Input metrics JSON not found: {input_path}")

    payload = load_export(input_path)
    summary = build_summary(payload, top_sources=args.top_sources)

    print(render_text(summary))

    if args.summary_out:
        output_path = Path(args.summary_out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2)
        print(f"\nWrote summary JSON: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
