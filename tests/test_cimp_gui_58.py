"""Qualify Native GUI monitoring and recovery.

Intentional user waits stay holds. Development stalls and idle-ready gaps keep
the real task, CID, attempt, and browser/validator deadlines, and they keep the
existing finite Native and watchdog budgets. Recovery does not rearm a paid
attempt or bypass a hold. Owned browser cleanup only waits. A missing
executable, a cancelled validation, and a stale source stay refused.

Metadata projection cases use an explicit unit runner; they cannot qualify
ownership or recovery effects. Separate cases exercise the genuine frozen
Native watchdog/finite ledger, actual owned Native executor, and Chromium DOM
with the inherited kernel fence. No model, completion, live campaign or paid
attempt is invoked. WebSocket, SSE and streaming remain unqualified.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from integrations.ipfs_accelerate import campaign_watchdog as watchdog
from integrations.ipfs_accelerate.improvement_runner import STARTUP_SECONDS, STALL_SECONDS, TIMEOUT_SECONDS
from tests.gui_native_browser import (
    BrowserCapabilityError,
    OWNED_BROWSER_CLEANUP_SECONDS,
    await_owned_browser_cleanup,
    discover_chromium,
)


pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

TASK_ID = "CIMP-GUI-58"
TASK_CID = "bafyrei-cimp-gui-58-synthetic"
ATTEMPT = 2
BROWSER_DEADLINE = 1_900.0
VALIDATOR_DEADLINE = 1_800.0


def _watcher(tmp_path, monkeypatch, *, state="stalled"):
    watcher = object.__new__(watchdog.ComplaintCampaignWatchdog)
    watcher.root = tmp_path
    watcher.state = tmp_path
    watcher.directory = tmp_path / "watchdog"
    watcher.spec_path = tmp_path / "spec.json"
    watcher.spec_path.write_text("{}\n", encoding="utf-8")
    watcher.spec_sha = watchdog.hashlib.sha256(b"{}\n").hexdigest()
    watcher.plan_id = "gui-58"
    watcher.artifacts = SimpleNamespace(board_relative="board.md")
    from ipfs_accelerate_py.agent_supervisor.prompt.prompt_workflow import prompt_workflow_cid
    watcher.scope = {key: prompt_workflow_cid({"kind": key, "plan": "gui-58"}) for key in ("repository_root_cid", "policy_root", "run_cid")}
    watcher.clock = lambda: 1_000.0
    watcher.latest_status = watcher.latest_observation = watcher.latest_completion = {}
    watcher.last_action = {}
    watcher.latest_preflight = {}
    task = SimpleNamespace(task_id=TASK_ID, status="todo")
    view = {
        "status": state,
        "healthy": False,
        "worker_liveness": "dead",
        "native_read_errors": {},
        "board": {"completed": 0, "count": 1, "ready_task_ids": [TASK_ID], "manual_hold_task_ids": []},
        "native_state": {
            "active_task_id": TASK_ID,
            "active_task_cid": TASK_CID,
            "active_attempt": ATTEMPT,
            "active_task_started_at": 0,
            "implementation_in_progress": False,
            "manual_hold": False,
        },
        # No browser-deadline producer exists in the actual runner.
        "browser_activity_evidence": {"deadline_at": BROWSER_DEADLINE, "task_id": TASK_ID},
        "validation_activity_evidence": {"deadline_at": VALIDATOR_DEADLINE, "state": "running", "task_id": TASK_ID},
        "provider_progress_verified": False,
        "validation_activity_verified": False,
    }
    accounting = {"implementation_attempts": {TASK_ID: ATTEMPT}, "implementation_attempts_by_cid": {TASK_CID: ATTEMPT}}
    runner = SimpleNamespace(
        status=lambda *_: deepcopy(view),
        _native_modules=lambda *_: (None, SimpleNamespace(parse_task_file=lambda *a, **k: [task])),
        TASK_PREFIX="## TASK-",
        STARTUP_SECONDS=STARTUP_SECONDS,
        STALL_SECONDS=STALL_SECONDS,
        TIMEOUT_SECONDS=TIMEOUT_SECONDS,
        _event_timestamp=lambda item: None,
        _claim_proof_conflict=lambda native: "stale_proof" if native.get("proof_stale") or native.get("stale_proof") else None,
        _atomic_json=lambda path, payload: path.write_text(json.dumps(payload), encoding="utf-8"),
        owns_process=lambda _: True,
        _read_native_state=lambda *_: (dict(accounting), {}),
        STATE_PREFIX="complaint",
    )
    watcher.runner = runner
    monkeypatch.setattr(watcher, "_mark_automatic_stop", lambda _token: None)
    monkeypatch.setattr(watcher, "_launch", lambda: ({"started_at": 0, "status": "running"}, True, "owner-gui-58"))
    return watcher, runner, view, accounting


def _assert_identity(observed, monitoring):
    assert monitoring["task_identity"] == {"task_id": TASK_ID, "cid": TASK_CID, "attempt": ATTEMPT}
    assert observed["active_task_id"] == TASK_ID
    assert observed["active_task_cid"] == TASK_CID
    assert observed["attempt"] == ATTEMPT
    assert monitoring["browser_deadline_at"] is None
    assert monitoring["validator_deadline_at"] is None
    assert monitoring["budgets"] == watchdog._PRESERVED_BUDGETS
    assert monitoring["paid_attempt_rearmed"] is False
    assert monitoring["hold_bypassed"] is False
    assert monitoring["completion_authority"] is False


def test_user_wait_is_not_a_development_stall(tmp_path, monkeypatch):
    watcher, runner, view, _accounting = _watcher(tmp_path, monkeypatch, state="stalled")
    view["application_interview_state"] = "awaiting_user"
    view["healthy"] = True
    observed = watcher.observe()
    _assert_identity(observed, watcher.latest_monitoring)
    assert watcher.latest_monitoring["monitor_class"] == "intentional_user_wait"
    assert observed["hold_reason"] == "awaiting_user"
    assert observed["recovery_permitted"] is False
    assert observed["manual_hold"] is True
    runner.stop = lambda *_a, **_k: pytest.fail("user wait stopped the lane")
    runner.start = lambda *_a, **_k: pytest.fail("user wait restarted the lane")
    result = watcher.recover(SimpleNamespace(deadline_at_ms=watcher.latest_monitoring["budgets"]["watchdog_action_deadline_ms"]))
    assert result.succeeded is False
    assert result.reason == "campaign_changed_before_stop"


def test_development_stall_keeps_task_deadlines_and_finite_budgets(tmp_path, monkeypatch):
    watcher, _runner, _view, _accounting = _watcher(tmp_path, monkeypatch, state="stalled")
    observed = watcher.observe()
    _assert_identity(observed, watcher.latest_monitoring)
    assert watcher.latest_monitoring["monitor_class"] == "development_worker_stall"
    assert observed["recovery_permitted"] is True
    assert watcher.latest_monitoring["browser_deadline_at"] is None
    assert watcher.latest_monitoring["validator_deadline_at"] is None
    assert watchdog.preserved_native_watchdog_budgets(watcher.runner) == watcher.latest_monitoring["budgets"]
    _view["validation_activity_verified"] = True
    watcher.observe()
    assert watcher.latest_monitoring["validator_deadline_at"] == VALIDATOR_DEADLINE


def test_cancelled_validation_does_not_rearm_or_restart(tmp_path, monkeypatch):
    watcher, runner, view, accounting = _watcher(tmp_path, monkeypatch, state="stalled")
    view["native_state"]["manual_cancellation"] = True
    watcher.observe()
    assert watcher.latest_monitoring["monitor_class"] == "cancelled_validation"
    assert watcher.latest_observation["recovery_permitted"] is False
    runner.stop = lambda *_a, **_k: pytest.fail("cancelled validation stopped the lane")
    runner.start = lambda *_a, **_k: pytest.fail("cancelled validation restarted the lane")
    result = watcher.recover(SimpleNamespace(deadline_at_ms=2_000_000))
    assert result.succeeded is False
    assert result.reason == "campaign_changed_before_stop"
    assert watcher._accounting()["implementation_attempts"] == accounting["implementation_attempts"]


def test_stale_source_blocks_recovery(tmp_path, monkeypatch):
    watcher, runner, view, _accounting = _watcher(tmp_path, monkeypatch, state="stalled")
    view["native_state"]["proof_stale"] = True
    observed = watcher.observe()
    assert watcher.latest_monitoring["monitor_class"] == "stale_source"
    assert watcher.latest_monitoring["source_stale"] is True
    assert observed["recovery_permitted"] is False
    runner.start = lambda *_a, **_k: pytest.fail("stale source restarted the lane")
    refused = watcher.recover(SimpleNamespace(deadline_at_ms=2_000_000))
    assert refused.succeeded is False
    watcher.spec_path.write_text('{"changed": true}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="watchdog_campaign_contract_changed"):
        watcher.observe()


def test_missing_watchdog_and_browser_executables_fail_closed(tmp_path, monkeypatch):
    environment = {"PATH": str(tmp_path / "empty-path"), "IPFS_ACCELERATE_AGENT_GROK_BIN": "grok"}
    (tmp_path / "empty-path").mkdir()
    with pytest.raises(ValueError, match="watchdog_grok_executable_unavailable"):
        watchdog._watchdog_executable_path(sys.executable, environment)
    missing = tmp_path / "missing-chromium"
    with pytest.raises(BrowserCapabilityError, match="Chromium executable is missing"):
        discover_chromium(missing)


def test_repeated_idle_ready_recovery_preserves_attempts_and_holds(tmp_path, monkeypatch):
    watcher, runner, view, accounting = _watcher(tmp_path, monkeypatch, state="blocked")
    view["native_state"]["active_task_id"] = ""
    view["native_state"]["active_task_cid"] = ""
    view["native_state"]["active_attempt"] = 0
    view["healthy"] = True
    calls = []
    runner.stop = lambda *_a, **_k: calls.append("stop") or {"status": "stopped"}
    runner.recover_stalled_worker = lambda *_a: calls.append("recover") or {"recovery": "reconciled"}
    runner.doctor = lambda *_a: calls.append("doctor") or {"status": "ready"}

    def start(*_a, **_k):
        calls.append("start")
        view.update(status="active", healthy=True, provider_progress_verified=True)
        view["native_state"].update(active_task_id=TASK_ID, active_task_cid=TASK_CID, active_attempt=ATTEMPT, implementation_in_progress=True)
        return {"status": "starting"}

    runner.start = start
    monkeypatch.setattr(watcher, "_accounting", lambda: dict(accounting))
    first = watcher.observe()
    assert watcher.latest_monitoring["monitor_class"] == "idle_ready"
    assert watcher.latest_monitoring["idle_ready"] is True
    assert first["recovery_permitted"] is True
    assert watcher.latest_monitoring["paid_attempt_rearmed"] is False
    recovered = watcher.recover(SimpleNamespace(deadline_at_ms=2_000_000))
    assert recovered.succeeded is True
    assert calls == ["stop", "recover", "doctor", "start"]
    assert watcher._accounting() == accounting

    view.update(status="blocked", healthy=True, provider_progress_verified=False, validation_activity_verified=False)
    view["native_state"].update(active_task_id="", active_task_cid="", active_attempt=0, implementation_in_progress=False, manual_hold=True)
    second = watcher.observe()
    assert watcher.latest_monitoring["monitor_class"] == "intentional_user_wait"
    assert second["recovery_permitted"] is False
    runner.stop = lambda *_a, **_k: pytest.fail("hold was bypassed on the repeated idle-ready pass")
    held = watcher.recover(SimpleNamespace(deadline_at_ms=2_000_000))
    assert held.succeeded is False
    assert watcher._accounting() == accounting


def test_owned_browser_cleanup_waits_and_does_not_signal(tmp_path):
    token = f"cimp-gui-58-{tmp_path.name}"
    held = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", token])
    try:
        waiting = await_owned_browser_cleanup({held.pid}, deadline_seconds=0.2)
        assert waiting["cleaned"] is False
        assert held.pid in waiting["remaining_pids"]
        assert waiting["signaled"] is False
        assert waiting["deadline_seconds"] == 0.2
    finally:
        held.terminate()
        held.wait(timeout=5)
    cleaned = await_owned_browser_cleanup({held.pid})
    assert cleaned["cleaned"] is True
    assert cleaned["remaining_pids"] == []
    assert cleaned["signaled"] is False
    assert cleaned["deadline_seconds"] == OWNED_BROWSER_CLEANUP_SECONDS
    with pytest.raises(BrowserCapabilityError, match="browser_cleanup_deadline_unbounded"):
        await_owned_browser_cleanup(set(), deadline_seconds=OWNED_BROWSER_CLEANUP_SECONDS + 1)


def test_changed_budget_is_rejected(monkeypatch):
    monkeypatch.setattr(watchdog, "_PRESERVED_BUDGETS", {**watchdog._PRESERVED_BUDGETS, "stall_seconds": 180})
    runner = SimpleNamespace(STARTUP_SECONDS=90, STALL_SECONDS=181, TIMEOUT_SECONDS=900)
    with pytest.raises(ValueError, match="watchdog_budget_changed"):
        watchdog.preserved_native_watchdog_budgets(runner)


def test_actual_frozen_native_accepts_exact_observation_and_keeps_two_action_cap(tmp_path, monkeypatch):
    """Real SDK schema/controller/ledger; the only callback is inert refusal.

    Unit ownership is deliberately confined to metadata projection. This case
    does not claim to qualify the application's stop/recover/start effects.
    """
    from ipfs_accelerate_py.agent_supervisor.rescue.campaign_watchdog import (
        CampaignProgressWatchdog, CampaignProgressWatchdogPolicy, _FIELDS)
    from ipfs_accelerate_py.agent_supervisor.rescue.supervisor_recovery import RecoveryActionObservation
    watcher, _runner, view, accounting = _watcher(tmp_path, monkeypatch)
    before = deepcopy(accounting)
    now = [1_000_000]
    calls = []
    def refuse(context):
        calls.append(context.deadline_at_ms)
        assert context.deadline_at_ms == now[0] + 1_200_000
        return RecoveryActionObservation(False, reason="synthetic_no_campaign_effect")
    policy = CampaignProgressWatchdogPolicy(deadline_ms=1_200_000)
    native = CampaignProgressWatchdog(tmp_path / "native-watchdog", repository_root=tmp_path,
        scope=watcher.scope, observe=watcher.observe, recover=refuse,
        policy=policy, clock_ms=lambda: now[0])
    assert policy.max_recovery_attempts == 2
    assert set(watcher.observe()) == _FIELDS
    assert "monitor_class" not in watcher.latest_observation
    for _ in range(12):
        result = native.run_once()
        assert result["status"] != "error", result
        now[0] += 61_000
    assert result["status"] == "exhausted", result
    assert len(calls) == 2
    durable = json.loads(native.state_path.read_bytes())
    assert len(durable["incidents"]) == 1
    assert next(iter(durable["incidents"].values()))["attempts"] == 2
    # An owner change requires reconfirmation, never a new action allowance.
    monkeypatch.setattr(watcher, "_launch", lambda: ({"started_at": 0,"status":"running"}, True, "changed-owner"))
    assert native.run_once()["status"] == "exhausted"
    view["native_state"]["manual_hold"] = True
    ledger = native.state_path.read_bytes()
    assert native.run_once()["status"] == "held"
    assert native.state_path.read_bytes() == ledger
    assert len(calls) == 2 and accounting == before


def _actual_owned_executor_status(tmp_path):
    """Real inert owned session, with explicit installed package origins.

    Native's sealed outer interpreter may be the base Python with explicit
    site-package roots. Its isolated nested Python must receive those actual
    roots explicitly too; no executable or ownership predicate is substituted.
    """
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import supervisor_runtime as runtime
    from integrations.ipfs_accelerate import improvement_runner as runner
    native_root = Path(native.__file__).resolve().parents[3]
    roots = [str(Path(runner.__file__).resolve().parents[2]), str(native_root),
        str(native_root.parent / "ipfs_datasets_py"), str(native_root.parent / "ipfs_kit_py"),
        str(Path(pytest.__file__).resolve().parents[1])]
    worker, parent, output = tmp_path/"native_worker.py", tmp_path/"native_parent.py", tmp_path/"closed-status.json"
    worker.write_text("import sys\nsys.path[:0]="+repr(roots)+"\n"+"""
from pathlib import Path
import json,pytest
from tests.test_owned_auto_rescue_activity import _native_world
from tests.test_owned_validation_status import observe_actual_executor
def main():
 with pytest.MonkeyPatch.context() as patch:
  with _native_world(Path(sys.argv[1]),patch) as world:
   result=observe_actual_executor(world,'validation_canonical')
   Path(sys.argv[2]).write_text(json.dumps(result))
if __name__=='__main__':main()
""")
    parent.write_text("import subprocess,sys\nraise SystemExit(subprocess.call(sys.argv[4:]))\n")
    with (tmp_path/"owned-child-output.log").open("w") as capture:
        completed = runtime.run_process_group_stream([sys.executable,"-I","-B",str(parent),
            "_run","--owner-token","private-inert-fixture",sys.executable,"-I","-B",str(worker),
            str(tmp_path/"native"),str(output)],cwd=tmp_path,stdout=capture,
            env=dict(os.environ),inherit_environment=False,timeout_seconds=60)
    assert completed.returncode == 0, "Inspect the authored fixture's owned-child-output.log."
    return json.loads(output.read_bytes())


def test_actual_owned_native_executor_and_deadline_controls(tmp_path):
    # Actual Native claims/leases/births, owned _run parent and sealed Python
    # executor. No authority monkeypatch, provider, validation success or merge.
    observations = _actual_owned_executor_status(tmp_path)
    current = observations["canonical_pulse"]
    assert current["validation_activity_verified"] is True and current["healthy"] is True
    assert current["status"] == "active" and current["scope_liveness"]["claim"] == "held"
    assert current["validation_activity_evidence"]["deadline_at"] > 0
    for damage in ("wrong_claim", "expired_phase", "stale_heartbeat"):
        assert observations[damage]["status"] == "stalled"
        assert observations[damage]["healthy"] is False
    for damage in ("wrong_claim", "expired_phase"):
        assert observations[damage]["validation_activity_verified"] is False


@contextmanager
def _browser_flag_diagnostics(path):
    """Observe original guard flags without replacing any guard or trace.

    Prior global/local Python traces are chained, profiles are untouched, and
    diagnostic failures never replace the qualification's return or exception.
    Only bounded flag counts and already-proved custody categories are written.
    """
    from tests import gui_native_browser as browser
    import dis
    import shlex
    previous = sys.gettrace()
    previous_profile = sys.getprofile()
    frames, records = {}, []
    yield_opcode = dis.opmap.get("YIELD_VALUE", -1)
    root_guard_code = browser._chromium_title_argv.__code__
    role_guard_code = browser._chromium_role_argv.__code__
    known = {"Chromium is not using the CDP pipe", "Chromium profile does not match the owned profile",
        "Chromium opened a TCP debugging port", "Chromium executable does not match the pin",
        "Chromium process arguments are invalid", "Chromium process title is malformed"}

    def observe(frame, event, arg):
        key = id(frame)
        existing = frames.get(key, (None, None))
        prior = previous if event == "call" else existing[1]
        # Preserve the original trace's local callback protocol and exceptions.
        next_prior = prior(frame, event, arg) if prior is not None else None
        if next_prior is None:
            # CPython leaves an existing local trace in place when it returns
            # None. A prior callback can explicitly assign f_trace instead.
            next_prior = (frame.f_trace if frame.f_trace is not observe
                else prior if event != "call" else existing[1])
        is_guard = frame.f_code is root_guard_code or frame.f_code is role_guard_code
        needs_local = is_guard or next_prior is not None
        if needs_local:
            frames[key] = (frame, next_prior)
        else:
            frames.pop(key, None)
        try:
            if (is_guard
                    and event in {"call", "exception"} and len(records) < 16):
                values = frame.f_locals
                argv, profile, pin = values["argv"], values["profile"], values["chromium"]
                if (not isinstance(argv, tuple) or not all(type(part) is str for part in argv)
                        or sum(len(part) for part in argv) > 65536):
                    raise ValueError("diagnostic_argv_bound")
                parts = tuple(shlex.split(argv[0])) if len(argv) == 1 else argv
                caller = frame.f_back
                owner = caller
                if (caller is not None and caller.f_code.co_name == "joined"
                        and caller.f_back is not None
                        and caller.f_back.f_code is browser._assert_process_custody.__code__):
                    owner = caller.f_back
                joined = owner is not None and owner.f_code is browser._assert_process_custody.__code__
                locals_ = caller.f_locals if joined else {}
                owner_locals = owner.f_locals if joined else {}
                root_record = owner_locals.get("root_record")
                root_record = root_record if isinstance(root_record, dict) else {}
                if caller is owner and root_record:
                    pid, birth, node_pid = owner_locals.get("root"), root_record.get("birth"), root_record.get("node")
                else:
                    pid, birth, node_pid = locals_.get("pid"), locals_.get("birth"), locals_.get("parent")
                row = {"event": event, "guard": "root" if frame.f_code is browser._chromium_title_argv.__code__ else "role",
                    "argc": len(argv), "single_title": len(argv) == 1,
                    "argv0_exact": bool(argv and argv[0] == pin.path),
                    "normalized_argc": len(parts), "pipe_exact_count": parts.count("--remote-debugging-pipe"),
                    "pipe_substring_arg_count": sum("--remote-debugging-pipe" in part for part in parts),
                    "nonexact_pipe_flag_count": sum(part.startswith("--remote-debugging-pipe")
                        and part != "--remote-debugging-pipe" for part in parts),
                    "exact_profile_count": parts.count("--user-data-dir=" + str(profile)),
                    "profile_flag_count": sum(part.startswith("--user-data-dir") for part in parts),
                    "child_type_flag_count": sum(part.startswith("--type=") for part in parts),
                    "original_guard_frame": joined,
                    "kernel_birth_still_current": type(pid) is int and browser._process_birth(pid) == birth,
                    "node_ancestry_joined": node_pid in owner_locals.get("node_births", {})}
                if event == "exception":
                    row["exception_type"] = arg[0].__name__
                    row["reason"] = str(arg[1]) if str(arg[1]) in known else "guard_exception"
                records.append(row)
        except Exception as exc:
            if len(records) < 16:
                records.append({"event": event, "diagnostic_error_type": type(exc).__name__})
        finally:
            if (event == "return" and not (0 <= frame.f_lasti < len(frame.f_code.co_code)
                    and frame.f_code.co_code[frame.f_lasti] == yield_opcode)):
                frames.pop(key, None)
        return observe if needs_local else None

    sys.settrace(observe)
    try:
        yield
    finally:
        if sys.gettrace() is observe:
            sys.settrace(previous)
        # Suspended frames may outlive this scope; restore their actual prior
        # local traces too. Never overwrite a trace installed by other code.
        for frame, prior in tuple(frames.values()):
            if frame.f_trace is observe:
                frame.f_trace = prior
        frames.clear()
        try:
            payload = {"schema": "gui58-original-browser-guard-diagnostic@1", "records": records,
                "record_limit": 16, "previous_trace_present": previous is not None,
                "original_trace_restored": sys.gettrace() is previous,
                "profile_unchanged": sys.getprofile() is previous_profile,
                "guard_replaced": False, "qualification_exception_suppressed": False,
                "completion_authority": False}
            raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
            if len(raw) <= 16384:
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(descriptor, "wb") as output:
                    output.write(raw + b"\n")
                    output.flush()
                    os.fsync(output.fileno())
        except Exception:
            pass  # Optional diagnostics cannot turn a failure into success.


def test_actual_chromium_dom_cookie_pipe_and_owned_cleanup(tmp_path, request):
    from tests.gui_native_browser import qualify_native_browser
    from tests.test_gui_native_browser_capability import assert_qualification_report
    manifest = request.config.getoption("--complaint-evidence-path", default=None)
    diagnostic = (Path(manifest).parent if manifest else tmp_path) / "closed-browser-custody.json"
    with _browser_flag_diagnostics(diagnostic):
        report = qualify_native_browser(tmp_path / "actual-browser")
    assert_qualification_report(report)
    assert report.child_cleanup["owned_count"] > 0 and report.child_cleanup["cleaned"] is True
    assert report.pipe_transport is True
    assert report.network_denial["af_unix_only"] is True
    assert report.network_denial["unchanged"] is True
    assert report.network_denial["before"]["af_unix"]["opened"] is True
    assert report.network_denial["before"]["af_inet"]["opened"] is False


@pytest.mark.parametrize("pids", [{True}, {-1}, {0}, [1], {"12"}])
def test_new_cleanup_wait_rejects_non_pid_inputs(pids):
    with pytest.raises(BrowserCapabilityError, match="browser_cleanup_pids_invalid"):
        await_owned_browser_cleanup(pids, deadline_seconds=0.01)


def test_completion_label_requires_verified_completion(tmp_path, monkeypatch):
    watcher, _runner, _view, _accounting = _watcher(tmp_path, monkeypatch, state="complete")
    result = watcher.observe()
    assert result["completion_verified"] is False and result["recovery_permitted"] is False
    assert watcher.latest_monitoring["monitor_class"] == "completion_unverified"


def test_optional_browser_observer_preserves_trace_profile_and_exceptions(tmp_path):
    """An inert isolated Python tests trace protocol without replacing seals."""
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    native_root = Path(native.__file__).resolve().parents[3]
    roots = [str(Path(__file__).resolve().parents[1]), str(native_root),
        str(native_root.parent / "ipfs_datasets_py"), str(native_root.parent / "ipfs_kit_py"),
        str(Path(pytest.__file__).resolve().parents[1])]
    program = "import sys\nsys.path[:0]=" + repr(roots) + "\n" + r"""
from pathlib import Path
import json
from tests.test_cimp_gui_58 import _browser_flag_diagnostics
root=Path(sys.argv[1]);checks=[]
for mode in ('none_local','switch_local','target_exception','trace_exception'):
 def sample():
  value=1
  if mode=='target_exception': raise ValueError('authored-target-exception')
  return value+1
 rows=[];profiles=[]
 def profile(frame,event,arg):
  if frame.f_code is sample.__code__:profiles.append(event)
 def local2(frame,event,arg):
  if frame.f_code is sample.__code__:rows.append('local2:'+event)
  return None
 def local(frame,event,arg):
  if frame.f_code is sample.__code__:
   rows.append('local:'+event)
   if mode=='trace_exception' and event=='line':raise RuntimeError('authored-trace-exception')
  return local2 if mode=='switch_local' else None
 def prior(frame,event,arg):
  if frame.f_code is sample.__code__:
   rows.append('global:'+event)
   return local
  return None
 def execute(observed):
  rows.clear();profiles.clear();sys.settrace(prior);sys.setprofile(profile)
  error=None
  try:
   if observed:
    with _browser_flag_diagnostics(root/(mode+'.json')):result=sample()
   else:result=sample()
  except (ValueError,RuntimeError) as exc:error=(type(exc).__name__,str(exc))
  finally:
   trace_unchanged=sys.gettrace() is prior
   profile_unchanged=sys.getprofile() is profile
   sys.settrace(None);sys.setprofile(None)
  return (list(rows),list(profiles),error,trace_unchanged,profile_unchanged)
 baseline=execute(False);observed=execute(True)
 assert baseline==observed,(mode,baseline,observed)
 assert observed[-1] is True
 checks.append({'mode':mode,'trace_events_preserved':True,'profile_events_preserved':True,
  'exception_preserved':True,'profile_restored':True})
# A generator that remains suspended at scope exit must recover its exact
# prior local trace; changing global trace alone is not sufficient.
events=[]
def suspended():
 yield 1
 yield 2
def suspended_local(frame,event,arg):
 if frame.f_code is suspended.__code__:events.append(event)
 return None
def suspended_prior(frame,event,arg):
 if frame.f_code is suspended.__code__:
  events.append(event)
  return suspended_local
 return None
sys.settrace(suspended_prior)
with _browser_flag_diagnostics(root/'suspended.json'):
 generator=suspended()
 assert next(generator)==1
assert sys.gettrace() is suspended_prior
assert generator.gi_frame.f_trace is suspended_local
assert next(generator)==2
generator.close();sys.settrace(None)
checks.append({'mode':'suspended_generator','trace_events_preserved':True,'profile_events_preserved':True,
 'exception_preserved':True,'profile_restored':True})
(root/'trace-contract.json').write_text(json.dumps(checks))
"""
    result = subprocess.run([sys.executable,"-I","-B","-c",program,str(tmp_path)],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30)
    assert result.returncode == 0, "Read the authored child's bounded diagnostic below: " + result.stderr[-2000:]
    checks=json.loads((tmp_path/"trace-contract.json").read_bytes())
    assert len(checks)==5 and all(row["trace_events_preserved"] and row["profile_restored"] for row in checks)
