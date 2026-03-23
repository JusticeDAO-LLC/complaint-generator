#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Optional, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]

REGRESSION_SLICES = {
    "lean": [
        "tests/test_run_package_install_smoke_cli.py",
        "tests/test_cli_commands.py",
        "tests/test_intake_status.py",
        "tests/test_mediator_three_phase.py",
        "tests/test_complaint_phases.py",
        "tests/test_phase_manager_temporal_registry.py",
        "tests/test_mediator.py",
    ],
    "review": [
        "tests/test_complaint_generator_package.py",
        "tests/test_complaint_generator_package_surface.py",
        "tests/test_review_api.py",
        "tests/test_claim_support_review_dashboard_flow.py",
        "tests/test_claim_support_hooks.py",
        "tests/test_backfill_claim_testimony_links_cli.py",
        "tests/test_claim_support_review_template.py",
        "tests/test_document_pipeline.py",
        "tests/test_document_pipeline_fallbacks.py",
        "tests/test_formal_document_pipeline.py",
    ],
    "full": [
        "tests/test_complaint_generator_package.py",
        "tests/test_complaint_generator_package_surface.py",
        "tests/test_review_api.py",
        "tests/test_claim_support_review_dashboard_flow.py",
        "tests/test_claim_support_hooks.py",
        "tests/test_backfill_claim_testimony_links_cli.py",
        "tests/test_claim_support_review_template.py",
        "tests/test_document_pipeline.py",
        "tests/test_document_pipeline_fallbacks.py",
        "tests/test_formal_document_pipeline.py",
        "tests/test_claim_support_review_playwright_smoke.py",
        "tests/test_complaint_generator_site_playwright.py",
        "tests/test_phase_manager_temporal_registry.py",
    ],
}


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one of the standard complaint-generator regression slices."
    )
    parser.add_argument(
        "--slice",
        choices=tuple(REGRESSION_SLICES.keys()),
        default="full",
        help="Regression slice to run.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the resolved pytest command without executing it.",
    )
    return parser


def resolve_test_targets(slice_name: str = "full") -> list[str]:
    normalized = str(slice_name or "full").strip().lower()
    if normalized not in REGRESSION_SLICES:
        raise ValueError(f"Unsupported regression slice: {slice_name}")
    return list(REGRESSION_SLICES[normalized])


def build_pytest_command(
    *,
    slice_name: str = "full",
    pytest_args: Optional[Sequence[str]] = None,
    python_executable: Optional[str] = None,
) -> list[str]:
    command = [python_executable or sys.executable, "-m", "pytest", "-q"]
    command.extend(list(pytest_args or ()))
    command.extend(resolve_test_targets(slice_name))
    return command


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = create_parser()
    args, passthrough = parser.parse_known_args(argv)

    command = build_pytest_command(
        slice_name=args.slice,
        pytest_args=passthrough,
    )
    if args.list:
        print(" ".join(command))
        return 0

    completed = subprocess.run(command, cwd=PROJECT_ROOT)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
