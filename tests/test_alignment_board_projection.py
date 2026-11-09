"""The visible alignment board preserves and reflects durable runtime work."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from integrations.ipfs_accelerate.alignment_plan import (
    BOARD_RELATIVE,
    PLAN_RELATIVE,
    STATE_RELATIVE,
    build_alignment_work_plan,
    publish_alignment_execution_board,
    write_alignment_artifacts,
)
from integrations.ipfs_accelerate.watchdog import _state_lock, initial_execution_board, save_state


pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def plan():
    return build_alignment_work_plan()


def _progress(plan):
    board = initial_execution_board(plan)
    record = board["tasks"]["task.llm_router_facade"]
    record.update(
        status="completed", attempts=1, heartbeat_unix=500,
        receipts=[{"kind": "check", "ok": True, "detail": "router facade verified", "at_unix": 500}],
    )
    board["supervisor"].update(status="paused", blocked_reason="operator maintenance")
    board["source_fingerprint"] = "verified-source"
    return board


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_publishing_standard_runtime_preserves_receipts_and_holds(tmp_path, plan):
    write_alignment_artifacts(tmp_path, plan=plan)
    progress = _progress(plan)
    save_state(tmp_path / STATE_RELATIVE, progress)

    published = publish_alignment_execution_board(tmp_path)

    assert published == tmp_path / BOARD_RELATIVE
    assert _read(published) == progress
    assert _read(tmp_path / STATE_RELATIVE) == progress


@pytest.mark.parametrize("custom_argument", ["plan_path", "state_path"])
def test_custom_run_cannot_publish_over_standard_board(tmp_path, plan, custom_argument):
    write_alignment_artifacts(tmp_path, plan=plan)
    target = tmp_path / BOARD_RELATIVE
    original = target.read_bytes()
    save_state(tmp_path / STATE_RELATIVE, _progress(plan))

    assert publish_alignment_execution_board(
        tmp_path, **{custom_argument: tmp_path / "custom.json"},
    ) is None
    assert target.read_bytes() == original


@pytest.mark.parametrize("invalid", ["plan", "tasks", "dependencies", "malformed"])
def test_invalid_runtime_cannot_replace_visible_progress(tmp_path, plan, invalid):
    write_alignment_artifacts(tmp_path, plan=plan)
    target = tmp_path / BOARD_RELATIVE
    save_state(target, _progress(plan))
    original = target.read_bytes()
    state = initial_execution_board(plan)
    if invalid == "plan":
        state["plan_id"] = "another-plan"
    elif invalid == "tasks":
        state["tasks"].pop("task.llm_router_facade")
    elif invalid == "dependencies":
        state["tasks"]["task.llm_router_facade"]["depends_on"] = ["task.unknown"]
    save_state(tmp_path / STATE_RELATIVE, state)
    if invalid == "malformed":
        (tmp_path / STATE_RELATIVE).write_text("{", encoding="utf-8")

    assert publish_alignment_execution_board(tmp_path) is None
    assert target.read_bytes() == original


def test_publication_waits_for_runtime_owner_without_rewriting_board(tmp_path, plan):
    write_alignment_artifacts(tmp_path, plan=plan)
    target = tmp_path / BOARD_RELATIVE
    original = target.read_bytes()
    state_path = tmp_path / STATE_RELATIVE
    save_state(state_path, _progress(plan))

    with _state_lock(state_path) as owned:
        assert owned
        assert publish_alignment_execution_board(tmp_path) is None
    assert target.read_bytes() == original


@pytest.mark.parametrize("invalid_status", [[], {}])
def test_malformed_runtime_status_cannot_replace_visible_progress(tmp_path, plan, invalid_status):
    write_alignment_artifacts(tmp_path, plan=plan)
    target = tmp_path / BOARD_RELATIVE
    save_state(target, _progress(plan))
    original = target.read_bytes()
    malformed = initial_execution_board(plan)
    malformed["tasks"]["task.llm_router_facade"]["status"] = invalid_status
    save_state(tmp_path / STATE_RELATIVE, malformed)

    assert publish_alignment_execution_board(tmp_path) is None
    write_alignment_artifacts(tmp_path, plan=plan)
    assert target.read_bytes() == original


@pytest.mark.parametrize("progress_location", ["runtime", "visible"])
def test_regeneration_preserves_matching_progress_and_receipts(tmp_path, plan, progress_location):
    write_alignment_artifacts(tmp_path, plan=plan)
    progress = _progress(plan)
    progress_path = tmp_path / (STATE_RELATIVE if progress_location == "runtime" else BOARD_RELATIVE)
    save_state(progress_path, progress)

    write_alignment_artifacts(tmp_path, plan=plan)

    assert _read(tmp_path / BOARD_RELATIVE) == progress
    assert _read(progress_path) == progress


def test_regeneration_preserves_visible_board_when_runtime_has_other_plan(tmp_path, plan):
    write_alignment_artifacts(tmp_path, plan=plan)
    progress = _progress(plan)
    save_state(tmp_path / BOARD_RELATIVE, progress)
    unrelated = initial_execution_board(plan)
    unrelated["plan_id"] = "another-plan"
    save_state(tmp_path / STATE_RELATIVE, unrelated)

    write_alignment_artifacts(tmp_path, plan=plan)

    assert _read(tmp_path / BOARD_RELATIVE) == progress
    assert _read(tmp_path / STATE_RELATIVE) == unrelated


def test_regeneration_fails_without_erasing_an_active_monitors_artifacts(tmp_path, plan):
    write_alignment_artifacts(tmp_path, plan=plan)
    original_plan = (tmp_path / PLAN_RELATIVE).read_bytes()
    original_board = (tmp_path / BOARD_RELATIVE).read_bytes()
    with _state_lock(tmp_path / STATE_RELATIVE) as owned:
        assert owned
        with pytest.raises(RuntimeError, match="owned by a running watchdog"):
            write_alignment_artifacts(tmp_path, plan=plan)
    assert (tmp_path / PLAN_RELATIVE).read_bytes() == original_plan
    assert (tmp_path / BOARD_RELATIVE).read_bytes() == original_board


def _load_cli():
    spec = importlib.util.spec_from_file_location("alignment_projection_cli", ROOT / "scripts/run_alignment_watchdog.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("custom_state", [False, True])
def test_cli_only_projects_standard_run(tmp_path, plan, monkeypatch, capsys, custom_state):
    from integrations.ipfs_accelerate.alignment_checks import CHECKERS
    from integrations.ipfs_accelerate.watchdog import run_watchdog

    write_alignment_artifacts(tmp_path, plan=plan)
    original = (tmp_path / BOARD_RELATIVE).read_bytes()
    cli = _load_cli()
    monkeypatch.setattr(cli, "ROOT", tmp_path)

    def verified_run(**kwargs):
        return run_watchdog(**kwargs, checkers={task_id: lambda _root: (True, "verified") for task_id in CHECKERS})

    monkeypatch.setattr(cli, "run_watchdog", verified_run)
    state_path = tmp_path / ("custom-state.json" if custom_state else STATE_RELATIVE)
    argv = ["--state", str(state_path)] if custom_state else []

    assert cli.main(argv) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["completed"] is True
    if custom_state:
        assert output["execution_board"] is None
        assert (tmp_path / BOARD_RELATIVE).read_bytes() == original
    else:
        assert output["execution_board"] == str(tmp_path / BOARD_RELATIVE)
        assert _read(tmp_path / BOARD_RELATIVE) == _read(state_path)
        assert all(record["status"] == "completed" for record in _read(state_path)["tasks"].values())
