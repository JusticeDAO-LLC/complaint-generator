#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SMOKE_OUTPUT_DIR = WORKSPACE_ROOT / "research_results" / "adversarial_runs" / "core_hacc_policies_regression"


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the focused HACC grounding/adversarial regression slice."
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the resolved commands without executing them.",
    )
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="Skip the live demo smoke run and only execute pytest validations.",
    )
    parser.add_argument(
        "--smoke-output-dir",
        default=str(DEFAULT_SMOKE_OUTPUT_DIR),
        help="Directory where the live smoke artifacts should be written.",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable to use for all regression steps.",
    )
    return parser


def build_hacc_seed_test_command(python_executable: str) -> list[str]:
    return [
        python_executable,
        "-m",
        "pytest",
        "-q",
        str(WORKSPACE_ROOT / "tests" / "test_hacc_evidence_seed_generation.py"),
        str(PROJECT_ROOT / "tests" / "test_hacc_evidence_loader.py"),
    ]


def build_harness_test_command(python_executable: str) -> list[str]:
    return [
        python_executable,
        "-m",
        "pytest",
        "-q",
        "complaint-generator/tests/test_adversarial_harness.py",
    ]


def build_smoke_command(python_executable: str, output_dir: str) -> list[str]:
    return [
        python_executable,
        str(PROJECT_ROOT / "scripts" / "run_hacc_grounded_pipeline.py"),
        "--hacc-preset",
        "core_hacc_policies",
        "--top-k",
        "1",
        "--num-sessions",
        "1",
        "--max-turns",
        "2",
        "--max-parallel",
        "1",
        "--output-dir",
        output_dir,
    ]


def _format_command(command: Sequence[str]) -> str:
    return " ".join(command)


def _run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    env: Optional[dict[str, str]] = None,
) -> None:
    completed = subprocess.run(list(command), cwd=cwd, env=env)
    if completed.returncode != 0:
        raise SystemExit(int(completed.returncode))


def _load_coverage_rows(output_dir: Path) -> list[dict[str, str]]:
    coverage_path = output_dir / "adversarial" / "anchor_section_coverage.csv"
    if not coverage_path.is_file():
        raise SystemExit(f"Smoke run did not produce {coverage_path}")
    with coverage_path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _validate_smoke_output(output_dir: Path) -> dict[str, object]:
    grounding_bundle_path = output_dir / "grounding_bundle.json"
    if not grounding_bundle_path.is_file():
        raise SystemExit(f"Smoke run did not produce {grounding_bundle_path}")
    with grounding_bundle_path.open("r", encoding="utf-8") as handle:
        grounding_bundle = json.load(handle)

    upload_report_path = output_dir / "evidence_upload_report.json"
    if not upload_report_path.is_file():
        raise SystemExit(f"Smoke run did not produce {upload_report_path}")
    with upload_report_path.open("r", encoding="utf-8") as handle:
        upload_report = json.load(handle)

    anchor_sections = list(grounding_bundle.get("anchor_sections") or [])
    if anchor_sections != ["grievance_hearing", "appeal_rights"]:
        raise SystemExit(
            "Unexpected core_hacc_policies anchor sections: "
            f"{anchor_sections}"
        )

    coverage_rows = _load_coverage_rows(output_dir)
    coverage_by_section = {
        str(row.get("section") or ""): float(row.get("coverage_rate") or 0.0)
        for row in coverage_rows
    }
    for section in ("grievance_hearing", "appeal_rights"):
        if coverage_by_section.get(section) != 1.0:
            raise SystemExit(
                f"Expected smoke coverage_rate 1.0 for {section}, got {coverage_by_section.get(section)}"
            )

    return {
        "anchor_sections": anchor_sections,
        "coverage_by_section": coverage_by_section,
        "grounding_bundle": str(grounding_bundle_path),
        "evidence_upload_report": str(upload_report_path),
        "coverage_report": str(output_dir / "adversarial" / "anchor_section_coverage.csv"),
        "upload_count": int(upload_report.get("upload_count") or 0),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)

    python_executable = str(args.python or sys.executable)
    smoke_output_dir = str(args.smoke_output_dir)

    hacc_seed_test_command = build_hacc_seed_test_command(python_executable)
    harness_test_command = build_harness_test_command(python_executable)
    smoke_command = build_smoke_command(python_executable, smoke_output_dir)

    if args.list:
        print(_format_command(hacc_seed_test_command))
        print(_format_command(harness_test_command))
        if not args.skip_smoke:
            print(_format_command(smoke_command))
        return 0

    print(f"[1/3] HACC seed tests: {_format_command(hacc_seed_test_command)}")
    _run_command(hacc_seed_test_command, cwd=WORKSPACE_ROOT)

    harness_env = dict(os.environ)
    harness_env["RUN_HEAVY_TESTS"] = "1"
    print(f"[2/3] Complaint-generator harness tests: {_format_command(harness_test_command)}")
    _run_command(harness_test_command, cwd=WORKSPACE_ROOT, env=harness_env)

    if args.skip_smoke:
        print("[3/3] Live smoke run skipped")
        return 0

    print(f"[3/3] Live smoke run: {_format_command(smoke_command)}")
    _run_command(smoke_command, cwd=WORKSPACE_ROOT)

    summary = _validate_smoke_output(Path(smoke_output_dir))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
