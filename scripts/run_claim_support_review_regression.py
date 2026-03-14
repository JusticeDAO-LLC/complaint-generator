#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Optional, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]

BASE_TESTS = [
    "tests/test_claim_support_hooks.py",
    "tests/test_review_api.py",
    "tests/test_claim_support_review_dashboard_flow.py",
    "tests/test_backfill_claim_testimony_links_cli.py",
]

BROWSER_SMOKE_TEST = "tests/test_claim_support_review_playwright_smoke.py"


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the focused claim-support review regression slice."
    )
    parser.add_argument(
        "--browser",
        choices=("auto", "on", "off"),
        default="auto",
        help="Include the Playwright browser smoke automatically, always, or never.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the resolved pytest command without executing it.",
    )
    return parser


def playwright_chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return False

    try:
        playwright = sync_playwright().start()
        executable_path = Path(playwright.chromium.executable_path)
        return executable_path.exists()
    except Exception:
        return False
    finally:
        try:
            playwright.stop()
        except Exception:
            pass


def resolve_test_targets(
    browser_mode: str = "auto",
    *,
    browser_available: Optional[bool] = None,
) -> list[str]:
    normalized_mode = str(browser_mode or "auto").strip().lower()
    if normalized_mode not in {"auto", "on", "off"}:
        raise ValueError(f"Unsupported browser mode: {browser_mode}")

    targets = list(BASE_TESTS)
    resolved_browser_available = browser_available
    if resolved_browser_available is None:
        resolved_browser_available = playwright_chromium_available()

    include_browser = normalized_mode == "on" or (
        normalized_mode == "auto" and resolved_browser_available
    )
    if include_browser:
        targets.append(BROWSER_SMOKE_TEST)
    return targets


def build_pytest_command(
    *,
    browser_mode: str = "auto",
    browser_available: Optional[bool] = None,
    pytest_args: Optional[Sequence[str]] = None,
    python_executable: Optional[str] = None,
) -> list[str]:
    targets = resolve_test_targets(
        browser_mode,
        browser_available=browser_available,
    )
    command = [python_executable or sys.executable, "-m", "pytest", "-q"]
    command.extend(list(pytest_args or ()))
    command.extend(targets)
    return command


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = create_parser()
    args, passthrough = parser.parse_known_args(argv)

    command = build_pytest_command(
        browser_mode=args.browser,
        pytest_args=passthrough,
    )
    if args.list:
        print(" ".join(command))
        return 0

    completed = subprocess.run(command, cwd=PROJECT_ROOT)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())