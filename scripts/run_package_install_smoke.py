#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run an install-smoke check for packaged complaint-generator console scripts.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the collected smoke-check summary as JSON.",
    )
    return parser


def installed_script_path(script_name: str, python_executable: Optional[str] = None) -> Path:
    executable = Path(python_executable or sys.executable)
    suffix = ".exe" if sys.platform.startswith("win") else ""
    return executable.parent / f"{script_name}{suffix}"


def extract_json_payload(stdout: str) -> dict:
    lines = [line for line in (stdout or "").splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if line.lstrip().startswith("{"):
            return json.loads("\n".join(lines[index:]))
    raise ValueError(f"No JSON payload found in stdout: {stdout!r}")


def _run_command(
    command: Sequence[str],
    *,
    env: dict[str, str],
    input_text: Optional[str] = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=PROJECT_ROOT,
        env=env,
        input=input_text,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def run_install_smoke(*, python_executable: Optional[str] = None) -> dict:
    workspace_script = installed_script_path("complaint-workspace", python_executable)
    workspace_alias_script = installed_script_path("complaint-generator-workspace", python_executable)
    generator_script = installed_script_path("complaint-generator", python_executable)
    mcp_script = installed_script_path("complaint-mcp-server", python_executable)
    mcp_alias_script = installed_script_path("complaint-generator-mcp", python_executable)

    env = dict(os.environ)
    env.setdefault("PYTHONPATH", str(PROJECT_ROOT))

    workspace_result = _run_command(
        [str(workspace_script), "session", "--user-id", "install-smoke-user"],
        env=env,
    )
    workspace_alias_result = _run_command(
        [str(workspace_alias_script), "session", "--user-id", "install-smoke-alias-user"],
        env=env,
    )
    generator_help_result = _run_command(
        [str(generator_script), "--help"],
        env=env,
    )
    mcp_result = _run_command(
        [str(mcp_script)],
        env=env,
        input_text='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n{"jsonrpc":"2.0","id":2,"method":"exit","params":{}}\n',
    )
    mcp_alias_result = _run_command(
        [str(mcp_alias_script)],
        env=env,
        input_text='{"jsonrpc":"2.0","id":3,"method":"initialize","params":{}}\n{"jsonrpc":"2.0","id":4,"method":"exit","params":{}}\n',
    )

    workspace_payload = extract_json_payload(workspace_result.stdout)
    workspace_alias_payload = extract_json_payload(workspace_alias_result.stdout)
    mcp_initialize_payload = extract_json_payload(mcp_result.stdout)
    mcp_alias_initialize_payload = extract_json_payload(mcp_alias_result.stdout)

    return {
        "scripts": {
            "complaint-generator": str(generator_script),
            "complaint-workspace": str(workspace_script),
            "complaint-generator-workspace": str(workspace_alias_script),
            "complaint-mcp-server": str(mcp_script),
            "complaint-generator-mcp": str(mcp_alias_script),
        },
        "workspace_user_id": workspace_payload["session"]["user_id"],
        "workspace_alias_user_id": workspace_alias_payload["session"]["user_id"],
        "generator_help_contains": "Complaint Generator" in generator_help_result.stdout,
        "mcp_server_name": mcp_initialize_payload["result"]["serverInfo"]["name"],
        "mcp_alias_server_name": mcp_alias_initialize_payload["result"]["serverInfo"]["name"],
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)

    payload = run_install_smoke()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            "Install smoke passed: "
            f"workspace={payload['workspace_user_id']}, "
            f"workspace_alias={payload['workspace_alias_user_id']}, "
            f"mcp={payload['mcp_server_name']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())