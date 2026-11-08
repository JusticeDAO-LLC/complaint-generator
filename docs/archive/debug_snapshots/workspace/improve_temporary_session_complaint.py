#!/usr/bin/env python3
from __future__ import annotations

import runpy
import sys
from pathlib import Path


def main() -> int:
    canonical_script = Path(__file__).resolve().parents[2] / "workspace" / "improve_temporary_session_complaint.py"
    if not canonical_script.exists():
        raise FileNotFoundError(f"Canonical workspace generator not found: {canonical_script}")

    sys.argv[0] = str(canonical_script)
    runpy.run_path(str(canonical_script), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
