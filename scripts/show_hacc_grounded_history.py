#!/usr/bin/env python3

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any, Optional, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GROUNDED_ROOT = PROJECT_ROOT / "output" / "hacc_grounded"


def _load_grounded_pipeline_module() -> Any:
    module_path = PROJECT_ROOT / "scripts" / "run_hacc_grounded_pipeline.py"
    spec = importlib.util.spec_from_file_location("run_hacc_grounded_pipeline", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Show the latest grounded HACC workflow history without rerunning the pipeline."
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "Specific grounded run directory or alias to inspect. "
            "Supported aliases: latest, previous, last-successful. "
            "Defaults to the latest child of --grounded-root."
        ),
    )
    parser.add_argument(
        "--grounded-root",
        default=str(DEFAULT_GROUNDED_ROOT),
        help="Root directory containing grounded HACC run folders.",
    )
    parser.add_argument("--list-runs", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def _latest_grounded_run_dir(grounded_root: Path) -> Path:
    children = _grounded_run_children(grounded_root)
    if children:
        return children[0]
    return grounded_root


def _grounded_run_children(grounded_root: Path) -> list[Path]:
    if grounded_root.is_dir():
        children = [path for path in grounded_root.iterdir() if path.is_dir()]
        return sorted(
            children,
            key=lambda path: (path.stat().st_mtime, path.name),
            reverse=True,
        )
    return []


def _last_successful_grounded_run_dir(grounded_root: Path) -> Path:
    for child in _grounded_run_children(grounded_root):
        if (child / "refreshed_grounding_state.json").is_file():
            return child
    return _latest_grounded_run_dir(grounded_root)


def resolve_grounded_run_dir(*, output_dir: Optional[str], grounded_root: str) -> Path:
    grounded_root_path = Path(grounded_root).resolve()
    if not output_dir:
        return _latest_grounded_run_dir(grounded_root_path)
    if output_dir == "latest":
        return _latest_grounded_run_dir(grounded_root_path)
    if output_dir == "previous":
        children = _grounded_run_children(grounded_root_path)
        if len(children) >= 2:
            return children[1]
        return _latest_grounded_run_dir(grounded_root_path)
    if output_dir == "last-successful":
        return _last_successful_grounded_run_dir(grounded_root_path)
    return Path(output_dir).resolve()


def _list_grounded_runs(grounded_root: Path) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for child in _grounded_run_children(grounded_root):
        status_path = child / "grounded_workflow_status.json"
        status: dict[str, Any] = {}
        if status_path.is_file():
            try:
                loaded = json.loads(status_path.read_text(encoding="utf-8"))
            except Exception:
                loaded = {}
            if isinstance(loaded, dict):
                status = loaded
        effective_next_action = dict(status.get("effective_next_action") or {})
        runs.append(
            {
                "run_dir": str(child.resolve()),
                "run_name": child.name,
                "workflow_stage": str(status.get("workflow_stage") or ""),
                "has_refreshed_grounding_state": bool(status.get("has_refreshed_grounding_state")),
                "has_persisted_completed_grounded_worksheet": bool(
                    status.get("has_persisted_completed_grounded_worksheet")
                ),
                "grounded_follow_up_answer_count": int(status.get("grounded_follow_up_answer_count", 0) or 0),
                "next_action": str(effective_next_action.get("action") or ""),
            }
        )
    return runs


def _resolve_grounded_run_aliases(grounded_root: Path) -> dict[str, str]:
    aliases: dict[str, str] = {}
    children = _grounded_run_children(grounded_root)
    if children:
        aliases["latest"] = children[0].name
        aliases["previous"] = children[1].name if len(children) >= 2 else children[0].name
    else:
        aliases["latest"] = ""
        aliases["previous"] = ""
    last_successful = _last_successful_grounded_run_dir(grounded_root)
    aliases["last-successful"] = (
        last_successful.name if last_successful != grounded_root and last_successful.exists() else aliases.get("latest", "")
    )
    return aliases


def _best_resume_candidate(runs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    ordered_runs = [dict(run) for run in runs if isinstance(run, dict)]
    if not ordered_runs:
        return {}

    def _score(run: dict[str, Any]) -> tuple[int, int, int, int]:
        return (
            1 if run.get("has_persisted_completed_grounded_worksheet") else 0,
            1 if run.get("has_refreshed_grounding_state") else 0,
            int(run.get("grounded_follow_up_answer_count", 0) or 0),
            1 if str(run.get("workflow_stage") or "") == "post_grounded_follow_up" else 0,
        )

    best_run = max(ordered_runs, key=_score)
    reason_parts: list[str] = []
    if best_run.get("has_persisted_completed_grounded_worksheet"):
        reason_parts.append("has completed grounded worksheet")
    if best_run.get("has_refreshed_grounding_state"):
        reason_parts.append("has refreshed grounding state")
    answer_count = int(best_run.get("grounded_follow_up_answer_count", 0) or 0)
    if answer_count:
        reason_parts.append(f"{answer_count} grounded follow-up answers")
    if str(best_run.get("workflow_stage") or "") == "post_grounded_follow_up":
        reason_parts.append("already reached post-grounded follow-up")
    return {
        "run_name": str(best_run.get("run_name") or ""),
        "run_dir": str(best_run.get("run_dir") or ""),
        "reason": ", ".join(reason_parts) or "most recent grounded run",
    }


def _render_grounded_run_list(
    runs: Sequence[dict[str, Any]],
    grounded_root: Path,
    aliases: Optional[dict[str, str]] = None,
    resume_candidate: Optional[dict[str, Any]] = None,
) -> str:
    lines = [
        f"Grounded root: {grounded_root}",
        f"Available runs: {len(list(runs))}",
    ]
    alias_map = dict(aliases or {})
    if alias_map:
        lines.append(
            "Alias targets: "
            f"latest={alias_map.get('latest', '') or '-'}, "
            f"previous={alias_map.get('previous', '') or '-'}, "
            f"last-successful={alias_map.get('last-successful', '') or '-'}"
        )
    candidate = dict(resume_candidate or {})
    if candidate:
        lines.append(
            f"Best candidate to resume: {candidate.get('run_name', '') or '-'}"
            f" ({candidate.get('reason', '') or 'recommended resume target'})"
        )
    if not runs:
        lines.append("No grounded runs found.")
        return "\n".join(lines)
    for run in runs:
        lines.append(
            f"- {run.get('run_name', '')}: {run.get('workflow_stage', '')} "
            f"(next={run.get('next_action', '')}, answers={run.get('grounded_follow_up_answer_count', 0)}, "
            f"refreshed={'yes' if run.get('has_refreshed_grounding_state') else 'no'})"
        )
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = create_parser().parse_args(argv)
    grounded_root = Path(args.grounded_root).resolve()
    if args.list_runs:
        runs = _list_grounded_runs(grounded_root)
        aliases = _resolve_grounded_run_aliases(grounded_root)
        resume_candidate = _best_resume_candidate(runs)
        if args.json:
            print(
                json.dumps(
                    {
                        "grounded_root": str(grounded_root),
                        "runs": runs,
                        "recommended_aliases": aliases,
                        "best_resume_candidate": resume_candidate,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(_render_grounded_run_list(runs, grounded_root, aliases, resume_candidate))
        return 0
    grounded_run_dir = resolve_grounded_run_dir(
        output_dir=args.output_dir,
        grounded_root=args.grounded_root,
    )
    grounded_cli = _load_grounded_pipeline_module()
    inspection = grounded_cli._load_grounded_workflow_inspection(grounded_run_dir)
    if args.json:
        print(json.dumps(grounded_cli._json_safe(inspection), ensure_ascii=False, indent=2))
    else:
        print(grounded_cli._render_grounded_workflow_history_inspection(inspection))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
