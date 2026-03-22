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
        help="Specific grounded run directory to inspect. Defaults to the latest child of --grounded-root.",
    )
    parser.add_argument(
        "--grounded-root",
        default=str(DEFAULT_GROUNDED_ROOT),
        help="Root directory containing grounded HACC run folders.",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def _latest_grounded_run_dir(grounded_root: Path) -> Path:
    if grounded_root.is_dir():
        children = [path for path in grounded_root.iterdir() if path.is_dir()]
        if children:
            return max(children, key=lambda path: path.stat().st_mtime)
    return grounded_root


def resolve_grounded_run_dir(*, output_dir: Optional[str], grounded_root: str) -> Path:
    if output_dir:
        return Path(output_dir).resolve()
    return _latest_grounded_run_dir(Path(grounded_root).resolve())


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = create_parser().parse_args(argv)
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
