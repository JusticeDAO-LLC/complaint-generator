"""Focused current-source UX acceptance while CIMP-UX-68 is still pending.

The controller measures kernel, AST, DOM, private state, and source evidence.
The final selector matrix and the production Native verifier stay outside this
900-second task. Saved JSON and caller booleans do not grant a pass.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
from pathlib import Path

import pytest

from tests.gui_native_browser import probe_inherited_network_denial


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_complaint_ux_overhaul.py"
CONTRACT = ROOT / "docs" / "task_boards" / "complaint_gui_ux_overhaul_completion_contract.json"
BOARD = ROOT / "docs" / "task_boards" / "complaint_gui_ux_overhaul_task_board.md"
_SPEC = importlib.util.spec_from_file_location("validate_complaint_ux_overhaul", SCRIPT)
acceptance = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(acceptance)


def _private(path: Path) -> Path:
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return path


def test_declared_selectors_are_immutable_and_nonempty() -> None:
    groups = acceptance.required_groups()
    assert set(groups) == {"controller_focus", "screenshot_story", "journey_bindings", "historical_separation"}
    assert groups["controller_focus"]["executes_during_task68"] is True
    assert groups["controller_focus"]["selectors"] == [
        "kernel_policy",
        "ast_source_binding",
        "dom_same_origin_state",
        "private_state_binding",
        "source_story_binding",
    ]
    assert groups["controller_focus"]["evidence"] == ["kernel", "ast", "dom", "state", "source"]
    assert all(spec["selectors"] and spec["minimum_cases"] == len(spec["selectors"]) for spec in groups.values())
    assert all(0 < spec["timeout_seconds"] <= 900 for spec in groups.values())
    assert sum(spec["executes_during_task68"] for spec in groups.values()) == 1
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    constants = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    for spec in groups.values():
        assert set(spec["selectors"]) <= constants
    with pytest.raises(TypeError):
        acceptance._DECLARED["controller_focus"]["selectors"] = ()
    groups["controller_focus"]["selectors"].append("caller-added")
    assert acceptance.required_groups()["controller_focus"]["selectors"][-1] == "source_story_binding"


def test_contract_records_the_split_and_does_not_grant_authority() -> None:
    document = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert document["instructional_only"] is True
    assert document["completion_authority"] is False
    assert document["task_population"] == 68 and document["task_ids"][-1] == "CIMP-UX-68"
    assert document["native_history_verifier"] == acceptance.NATIVE_VERIFIER
    controller = document["controller"]
    assert controller["schema"] == acceptance.SCHEMA
    assert controller["focused_group"] == acceptance.FOCUSED_GROUP
    assert controller["focused_selectors"] == acceptance.required_groups()["controller_focus"]["selectors"]
    assert controller["executes_final_matrix_during_task68"] is False
    assert controller["invokes_native_verifier_during_task68"] is False
    assert controller["self_pending_circular_precondition"] is False
    assert controller["saved_json_authority"] is False
    assert controller["caller_boolean_authority"] is False
    assert controller["completion_authority"] is False
    with pytest.raises(acceptance.CurrentAcceptanceError, match="caller_or_saved_json_not_authority"):
        acceptance.accept_saved_report(document)
    with pytest.raises(acceptance.CurrentAcceptanceError, match="caller_or_saved_json_not_authority"):
        acceptance.accept_caller_boolean(True)


def test_self_pending_controller_measures_live_evidence_without_native_completion(tmp_path: Path, monkeypatch) -> None:
    section = BOARD.read_text(encoding="utf-8").split("## CIMP-UX-68", 1)[1].split("## ", 1)[0]
    assert "- Status: todo" in section
    import integrations.ipfs_accelerate.campaign_completion as completion

    def forbidden(*_args, **_kwargs):
        raise AssertionError("native verifier ran inside task 68")

    monkeypatch.setattr(completion, "verify_campaign_completion", forbidden)
    parent = _private(tmp_path / "private-parent")
    run = acceptance.run_focused_group(parent / "owned")
    body = run.to_dict()
    assert body["focused_controller_passed"] is True
    assert body["passed"] is True
    assert body["current_acceptance_passed"] is False
    assert body["final_matrix_executed"] is False
    assert body["native_verifier_invoked"] is False
    assert body["preconditions_checked"] == []
    assert body["required_completed_tasks"] == []
    assert body["self_pending_circular_precondition"] is False
    assert body["completion_authority"] is False
    assert body["skipped_required_cases"] == 0
    assert [case["outcome"] for case in body["cases"]] == ["passed"] * 5
    assert [case["evidence_kind"] for case in body["cases"]] == ["kernel", "ast", "dom", "state", "source"]
    kernel = body["cases"][0]["detail"]
    live = probe_inherited_network_denial()
    assert kernel["af_unix_only"] is live["af_unix_only"]
    assert kernel["af_unix_opened"] is True
    assert kernel["seccomp"] == live["seccomp"]["Seccomp"]
    assert kernel["caller_supplied"] is False
    dom = body["cases"][2]["detail"]
    assert dom["stale_access"] == "No case selected"
    assert dom["inquiry"] == "synthetic pending inquiry"
    assert dom["workspace_state"] == "authenticated_backend_with_existing_stale_workspace_header"
    assert dom["external_aborted"] == "external-origin"
    assert dom["websocket_aborted"] == "websocket-unqualified"
    assert dom["asgi_calls"] == 3
    assert dom["mock_api"] is False
    state = body["cases"][3]["detail"]
    assert state["stranger_denied"] is True and state["plaintext_hidden"] is True and state["bytes"] > 0
    source = body["cases"][4]["detail"]
    assert source["screenshot_count"] == 13 and source["completion_authority"] is False
    report = Path(body["report_path"])
    assert report.is_file() and report.stat().st_mode & 0o777 == 0o600
    summary = acceptance.aggregate_focused_groups([run])
    assert summary["focused_controller_passed"] is True
    assert summary["current_acceptance_passed"] is False
    assert summary["missing_groups"] == ["screenshot_story", "journey_bindings", "historical_separation"]
    assert summary["native_verifier_invoked"] is False
    with pytest.raises(acceptance.CurrentAcceptanceError, match="final_matrix_outside_task68_budget"):
        acceptance.run_final_matrix()
    with pytest.raises(acceptance.CurrentAcceptanceError, match="native_verifier_after_genuine_callback"):
        acceptance.invoke_native_verifier()


def test_saved_json_partial_and_relabel_are_not_acceptance(tmp_path: Path) -> None:
    parent = _private(tmp_path / "parent")
    run = acceptance.run_focused_group(parent / "first")
    saved = json.loads(Path(run.to_dict()["report_path"]).read_text(encoding="utf-8"))
    saved["passed"] = True
    saved["current_acceptance_passed"] = True
    with pytest.raises(acceptance.CurrentAcceptanceError, match="host_measurement_required"):
        acceptance.aggregate_focused_groups([saved])
    with pytest.raises(acceptance.CurrentAcceptanceError, match="caller_or_saved_json_not_authority"):
        acceptance.accept_saved_report(saved)
    with pytest.raises(acceptance.CurrentAcceptanceError, match="duplicate_group"):
        acceptance.aggregate_focused_groups([run, run])
    assert acceptance.aggregate_focused_groups([])["focused_controller_passed"] is False
    relabeled = dict(run.to_dict(), group="screenshot_story")
    wrapped = acceptance.FocusedGroupRun(acceptance._TOKEN, relabeled, run.to_dict()["source_before"])
    with pytest.raises(acceptance.CurrentAcceptanceError, match="host_measurement_required"):
        acceptance.aggregate_focused_groups([wrapped])
    acceptance._RUNS.add(wrapped)
    try:
        with pytest.raises(acceptance.CurrentAcceptanceError, match="group_contract_mismatch"):
            acceptance.aggregate_focused_groups([wrapped])
    finally:
        acceptance._RUNS.discard(wrapped)


def test_output_custody_refuses_source_aliases_and_replaced_parents(tmp_path: Path) -> None:
    with pytest.raises(acceptance.CurrentAcceptanceError, match="private_output_overlaps_source"):
        acceptance._Output(ROOT / "never-created-ux68-report")
    assert not (ROOT / "never-created-ux68-report").exists()
    state = _private(tmp_path / "campaign")
    with pytest.raises(acceptance.CurrentAcceptanceError, match="private_output_overlaps_control_state"):
        acceptance._Output(state / "never-created")
    assert not (state / "never-created").exists()
    parent = _private(tmp_path / "private-parent")
    alias = tmp_path / "alias"
    alias.symlink_to(parent, target_is_directory=True)
    with pytest.raises(acceptance.CurrentAcceptanceError, match="private_output_path"):
        acceptance._Output(alias / "never-created")
    assert not (parent / "never-created").exists()
    with acceptance._Output(parent / "moving") as held:
        moved = tmp_path / "original-parent"
        parent.rename(moved)
        replacement = _private(tmp_path / "private-parent")
        (replacement / "moving").mkdir(mode=0o700)
        with pytest.raises(acceptance.CurrentAcceptanceError, match="private_output_custody"):
            acceptance._write_report(held, {"passed": True, "completion_authority": False})
        assert not (replacement / "moving" / "report.json").exists()
        assert not (moved / "moving" / "report.json").exists()


def test_cli_runs_only_the_focused_group(tmp_path: Path) -> None:
    parent = _private(tmp_path / "cli-parent")
    output = parent / "cli-owned"
    assert acceptance.main(["--output-root", str(output)]) == 0
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["group"] == "controller_focus"
    assert report["focused_controller_passed"] is True
    assert report["current_acceptance_passed"] is False
    assert report["native_verifier_invoked"] is False
    assert len(report["cases"]) == 5
    with pytest.raises(acceptance.CurrentAcceptanceError, match="final_matrix_outside_task68_budget"):
        acceptance.main(["--output-root", str(parent / "unused-final"), "--final-matrix"])
    with pytest.raises(acceptance.CurrentAcceptanceError, match="native_verifier_after_genuine_callback"):
        acceptance.main(["--output-root", str(parent / "unused-native"), "--native-verifier"])
    assert not (parent / "unused-final").exists()
    assert not (parent / "unused-native").exists()
