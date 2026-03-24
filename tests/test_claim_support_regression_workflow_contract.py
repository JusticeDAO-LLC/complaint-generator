import json
from pathlib import Path

import pytest


pytestmark = pytest.mark.no_auto_network


def test_claim_support_workflow_includes_browser_network_lane():
    workflow_path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "claim-support-regression.yml"
    workflow_text = workflow_path.read_text(encoding="utf-8")

    assert "- label: browser-network" in workflow_text
    assert "network_mode: on" in workflow_text
    assert "--network ${{ matrix.network_mode }}" in workflow_text


def test_pull_request_template_mentions_browser_network_claim_support_gate():
    template_path = Path(__file__).resolve().parents[1] / ".github" / "pull_request_template.md"
    template_text = template_path.read_text(encoding="utf-8")

    assert "run_claim_support_review_regression.py --browser on --network on" in template_text


def test_vscode_tasks_include_browser_network_claim_support_variant():
    tasks_path = Path(__file__).resolve().parents[1] / ".vscode" / "tasks.json"
    tasks_payload = json.loads(tasks_path.read_text(encoding="utf-8"))

    matching_tasks = [
        task for task in tasks_payload.get("tasks", [])
        if task.get("label") == "Claim Support Regression (Browser + Network)"
    ]

    assert matching_tasks
    assert matching_tasks[0].get("args") == [
        "scripts/run_claim_support_review_regression.py",
        "--browser",
        "on",
        "--network",
        "on",
    ]


def test_vscode_launch_config_includes_browser_network_claim_support_variant():
    launch_path = Path(__file__).resolve().parents[1] / ".vscode" / "launch.json"
    launch_payload = json.loads(launch_path.read_text(encoding="utf-8"))

    matching_configs = [
        config for config in launch_payload.get("configurations", [])
        if config.get("name") == "Claim Support Regression (Browser + Network)"
    ]

    assert matching_configs
    assert matching_configs[0].get("args") == [
        "--browser",
        "on",
        "--network",
        "on",
    ]