"""Real compiler publication preserves the Native protected-file identity."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

from integrations.ipfs_accelerate import improvement_plan as compiler
from integrations.ipfs_accelerate.campaign import campaign_artifacts


ROOT = Path(__file__).resolve().parents[1]
SPEC_RELATIVE = "docs/task_boards/complaint_gui_ux_overhaul_spec.json"
PLAN_ID = "baguqeeragyltexzene6bsp4ex5n7yqlspa622ld65argizkxfralwyxfqkxa"
GENERATION = "77690f838bbc481fb95a0e7f78495221c9b3889dd743abd15ecb587ccaf115f5"
pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _git(root, *arguments):
    return subprocess.check_output(
        ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-C", str(root), *arguments],
        text=True,
    ).strip()


def _repository(root, *, changed=False):
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    source = root / SPEC_RELATIVE
    source.parent.mkdir(parents=True)
    raw = (ROOT / SPEC_RELATIVE).read_bytes()
    if changed:
        specification = json.loads(raw)
        specification["title"] += " — synthetic output migration"
        raw = (json.dumps(specification, indent=2) + "\n").encode()
    source.write_bytes(raw)
    return source


def _native_snapshotter(root, spec):
    # Construct only the real filesystem observation surface. No daemon run,
    # store, claim, provider, recovery, or completion callback is instantiated.
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import PortalImplementationDaemon

    observer = object.__new__(PortalImplementationDaemon)
    observer.repo_root = root
    observer.implementation_protected_paths = campaign_artifacts(spec).protected_paths
    return observer


def _identity(path):
    value = path.lstat()
    return tuple(getattr(value, field) for field in (
        "st_dev", "st_ino", "st_mode", "st_nlink", "st_uid", "st_gid",
        "st_size", "st_mtime_ns", "st_ctime_ns",
    ))


@pytest.mark.parametrize("mode", [0o600, 0o640, 0o644, 0o660, 0o664])
def test_generate_twice_keeps_68_task_plan_and_native_protected_snapshot(tmp_path, mode):
    source = _repository(tmp_path / "repository")
    specification = compiler.load_spec(source)
    first = compiler.generate(source, source.parents[2])
    root = source.parents[2]
    plan, board = Path(first["plan_path"]), Path(first["board_path"])
    plan.chmod(mode)
    _git(root, "add", "docs")
    _git(root, "-c", "user.name=Synthetic compiler fixture", "-c", "user.email=compiler@example.invalid",
         "commit", "-q", "-m", "Record the private synthetic plan")
    observer = _native_snapshotter(root, specification)
    before = observer._implementation_protected_path_snapshot(root)
    identities = {str(path): _identity(path) for path in (source, plan, board)}
    content = plan.read_bytes()

    second = compiler.generate(source, root)

    from ipfs_accelerate_py.agent_supervisor.planning.formal_planning_contracts import FormalWorkPlan

    actual = FormalWorkPlan.from_dict(json.loads(plan.read_text()))
    assert first["receipt"]["plan_id"] == second["receipt"]["plan_id"] == actual.plan_id == PLAN_ID
    assert compiler.source_generation(specification) == actual.metadata["spec_sha256"] == GENERATION
    assert (len(actual.goals), len(actual.subgoals), len(actual.tasks)) == (9, 22, 68)
    assert plan.read_bytes() == content
    assert {str(path): _identity(path) for path in (source, plan, board)} == identities
    after = observer._implementation_protected_path_snapshot(root)
    assert after == before
    assert observer._implementation_protected_path_mutations(before, after) == []
    assert second["receipt"]["tasks_completed_by_ingestion"] == 0
    assert second["receipt"]["validations_executed"] == []
    assert second["receipt"]["board_preserved"] is True


def test_actual_changed_spec_output_replaces_stale_formal_plan(tmp_path):
    original_source = _repository(tmp_path / "original")
    original = compiler.generate(original_source, original_source.parents[2])
    source = _repository(tmp_path / "changed", changed=True)
    root = source.parents[2]
    changed = compiler.generate(source, root)
    plan, board = Path(changed["plan_path"]), Path(changed["board_path"])
    wanted = plan.read_bytes()
    plan.write_bytes(Path(original["plan_path"]).read_bytes())
    observer = _native_snapshotter(root, compiler.load_spec(source))
    before = observer._implementation_protected_path_snapshot(root)
    stale_identity, board_identity = _identity(plan), _identity(board)

    regenerated = compiler.generate(source, root)

    assert regenerated["receipt"]["plan_id"] == changed["receipt"]["plan_id"] != PLAN_ID
    assert compiler.source_generation(compiler.load_spec(source)) != GENERATION
    assert plan.read_bytes() == wanted
    assert _identity(plan)[1] != stale_identity[1]
    assert stat.S_IMODE(plan.stat().st_mode) == 0o600
    assert _identity(board) == board_identity
    after = observer._implementation_protected_path_snapshot(root)
    assert {item["path"] for item in observer._implementation_protected_path_mutations(before, after)} == {
        campaign_artifacts(compiler.load_spec(source)).plan_relative
    }
    assert (ROOT / SPEC_RELATIVE).read_bytes() == original_source.read_bytes()


def test_same_size_changed_content_is_atomically_replaced(tmp_path):
    path = tmp_path / "plan.json"
    path.write_text("old plan\n")
    path.chmod(0o600)
    before = _identity(path)
    compiler._atomic_write(path, "new plan\n")
    assert path.read_text() == "new plan\n"
    assert _identity(path)[1] != before[1]


def test_equal_hardlinked_content_is_published_as_an_independent_file(tmp_path):
    original = tmp_path / "original.json"
    original.write_text("reviewed plan\n")
    original.chmod(0o600)
    path = tmp_path / "plan.json"
    os.link(original, path)
    before = _identity(path)
    compiler._atomic_write(path, "reviewed plan\n")
    assert path.read_text() == original.read_text() == "reviewed plan\n"
    assert path.stat().st_nlink == original.stat().st_nlink == 1
    assert path.stat().st_ino != before[1] == original.stat().st_ino


def test_symlink_leaf_is_replaced_without_opening_its_target(tmp_path, monkeypatch):
    original = tmp_path / "outside.json"
    original.write_text("reviewed plan\n")
    path = tmp_path / "plan.json"
    path.symlink_to(original)
    before = _identity(original)
    real_open = os.open

    def no_leaf_open(value, *args, **kwargs):
        assert Path(value) != path, "symlink publication opened the alias"
        return real_open(value, *args, **kwargs)

    monkeypatch.setattr(compiler.os, "open", no_leaf_open)
    compiler._atomic_write(path, "reviewed plan\n")
    assert path.is_file() and not path.is_symlink()
    assert path.read_text() == original.read_text() == "reviewed plan\n"
    assert _identity(original) == before


def test_parent_alias_is_refused_without_changing_the_real_document(tmp_path):
    directory = tmp_path / "actual"
    directory.mkdir()
    original = directory / "plan.json"
    original.write_text("reviewed plan\n")
    alias = tmp_path / "alias"
    alias.symlink_to(directory, target_is_directory=True)
    before = _identity(original)
    with pytest.raises(ValueError, match="parent traverses an alias"):
        compiler._atomic_write(alias / "plan.json", "reviewed plan\n")
    assert _identity(original) == before


@pytest.mark.parametrize("mode", [0o606, 0o666, 0o700, 0o4600])
def test_unsafe_document_mode_cannot_take_the_identity_reuse_path(tmp_path, mode):
    path = tmp_path / "plan.json"
    path.write_text("reviewed plan\n")
    path.chmod(mode)
    before = _identity(path)
    compiler._atomic_write(path, "reviewed plan\n")
    assert path.stat().st_ino != before[1]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_different_operator_uid_cannot_reuse_equal_document(tmp_path, monkeypatch):
    path = tmp_path / "plan.json"
    path.write_text("reviewed plan\n")
    path.chmod(0o600)
    before = _identity(path)
    # The physical file has the real uid; vary only the observer's operator
    # identity rather than requiring chown privileges or skipping this guard.
    monkeypatch.setattr(compiler.os, "getuid", lambda: before[4] + 1)
    compiler._atomic_write(path, "reviewed plan\n")
    assert path.stat().st_ino != before[1]
    assert path.stat().st_uid == before[4]


def test_concurrent_name_replacement_during_compare_is_preserved(tmp_path, monkeypatch):
    path, winner = tmp_path / "plan.json", tmp_path / "winner.json"
    path.write_text("reviewed plan\n")
    path.chmod(0o600)
    real_read = os.read
    replaced = []

    def replace_after_read(fd, count):
        data = real_read(fd, count)
        if not replaced:
            winner.write_text("concurrent writer\n")
            os.replace(winner, path)
            replaced.append(True)
        return data

    monkeypatch.setattr(compiler.os, "read", replace_after_read)
    with pytest.raises(ValueError, match="changed while comparing"):
        compiler._atomic_write(path, "reviewed plan\n")
    assert path.read_text() == "concurrent writer\n"


def test_fifo_is_replaced_without_waiting_for_a_writer(tmp_path):
    path = tmp_path / "plan.json"
    os.mkfifo(path, mode=0o600)
    bootstrap = (
        "import sys;sys.path.insert(0," + repr(str(ROOT)) + ");"
        "from pathlib import Path;"
        "from integrations.ipfs_accelerate.improvement_plan import _atomic_write;"
        "_atomic_write(Path(sys.argv[1]),'reviewed plan\\n')"
    )
    completed = subprocess.run([sys.executable, "-I", "-B", "-c", bootstrap, str(path)],
                               text=True, capture_output=True, timeout=10)
    assert completed.returncode == 0, completed.stderr
    assert stat.S_ISREG(path.lstat().st_mode)
    assert path.read_text() == "reviewed plan\n"
