#!/usr/bin/env python3
"""Run one complaint supervisor job off the HTTP request path."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integrations.ipfs_accelerate.supervisor import (  # noqa: E402
    draft_repair,
    evidence_acquisition,
    graph_refresh,
)

_JOBS = {
    "draft_repair": draft_repair,
    "evidence_acquisition": evidence_acquisition,
    "graph_refresh": graph_refresh,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one off-request-path complaint supervisor job.")
    parser.add_argument("--operation", required=True, choices=sorted(_JOBS))
    parser.add_argument("--payload", required=True, help="JSON object file for the job.")
    args = parser.parse_args(argv)
    payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("payload JSON must be an object")
    result = _JOBS[args.operation](payload)
    json.dump(result, sys.stdout, indent=2, sort_keys=True, default=str)
    sys.stdout.write("\n")
    return 0 if result.get("status") == "available" else 2


if __name__ == "__main__":
    raise SystemExit(main())
