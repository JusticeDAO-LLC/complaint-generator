#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Optional, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]

HACC_UNIT_TESTS = [
    "tests/test_hacc_evidence_loader.py",
    "tests/test_synthesize_hacc_complaint.py",
    "tests/test_run_hacc_adversarial_report.py",
    "tests/test_run_hacc_unit_regression_cli.py",
    "tests/test_run_hacc_grounding_regression_cli.py",
    "tests/test_run_hacc_grounded_pipeline_cli.py",
]


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the lightweight HACC unit regression slice."
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the resolved pytest command without executing it.",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable to use for the regression run.",
    )
    return parser


def resolve_test_targets() -> list[str]:
    return list(HACC_UNIT_TESTS)


def build_pytest_command(
    *,
    pytest_args: Optional[Sequence[str]] = None,
    python_executable: Optional[str] = None,
) -> list[str]:
    command = [python_executable or sys.executable, "-m", "pytest", "-q"]
    command.extend(list(pytest_args or ()))
    command.extend(resolve_test_targets())
    return command


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = create_parser()
    args, passthrough = parser.parse_known_args(argv)

    command = build_pytest_command(
        pytest_args=passthrough,
        python_executable=args.python,
    )
    if args.list:
        print(" ".join(command))
        return 0

    completed = subprocess.run(command, cwd=PROJECT_ROOT)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
