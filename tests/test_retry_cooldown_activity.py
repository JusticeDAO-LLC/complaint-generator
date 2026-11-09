"""Real inert process births and Native queue backoff; synthetic task outcomes.

No provider, browser, public launcher or task completion is exercised. The
journal/projection are explicit local fixtures; the cooldown formula comes from
the actual Native queue producer and is observed through production status.
"""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner
from integrations.ipfs_accelerate import retry_cooldown_activity as activity
from tests.test_campaign_watchdog import _adapter
from tests.test_improvement_runner import _spec

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _stamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


@pytest.fixture
def world(tmp_path):
    from integrations.ipfs_accelerate.improvement_plan import generate, source_generation
    from ipfs_accelerate_py.agent_supervisor.task_sources.persistent_task_queue import PersistentTaskQueue
    from ipfs_accelerate_py.agent_supervisor.task_sources.task_identity import canonical_task_identity
    root, state = tmp_path / "repo", tmp_path / "campaign"
    root.mkdir(); state.mkdir(mode=0o700)
    spec_path = root / runner.SPEC_RELATIVE
    spec_path.parent.mkdir(parents=True)
    spec_path.write_text(json.dumps(_spec()))
    generate(spec_path, root)
    spec, artifacts = runner._campaign_spec(root, spec_path)
    _, native = runner._native_modules(root)
    parsed = native.parse_task_file(root / artifacts.board_relative, task_header_prefix=runner.TASK_PREFIX)
    identities = {task.task_id: canonical_task_identity(task,
        board_namespace=Path(artifacts.board_relative).name, source_path=root / artifacts.board_relative)
        for task in parsed}
    task_id = parsed[0].task_id; identity = identities[task_id]; cid = identity.canonical_task_cid
    # An inert owner creates and reaps its own inert child. These births are
    # real Linux observations, separate from the synthetic outcome metadata.
    program = """import subprocess,sys,signal
child=subprocess.Popen([sys.executable,'-I','-B','-c','import time;time.sleep(120)'])
def stop(*args): raise SystemExit(0)
signal.signal(signal.SIGTERM,stop)
print(child.pid,flush=True)
try: sys.stdin.read(1)
finally:
 child.terminate()
 try: child.wait(timeout=5)
 except subprocess.TimeoutExpired: child.kill();child.wait()
"""
    owner = subprocess.Popen([sys.executable, "-I", "-B", "-c", program, "_run",
        "--owner-token", "explicit-private-inert-retry-test"], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        child_pid = int(owner.stdout.readline())
        owner_birth, child = runner.process_identity(owner.pid), runner.process_identity(child_pid)
        assert owner_birth and child and child["ppid"] == owner.pid
        now = time.time()
        record = {"schema_version":"complaint-improvement-launcher@1", "status":"running",
            "identity":owner_birth, "argv":owner_birth["argv"], "owner_token":"explicit-private-inert-retry-test",
            "repo_root":str(root), "state_dir":str(state), "spec_path":str(spec_path),
            "board_path":str(root/artifacts.board_relative), "started_at":now-800,
            "plan_id":runner._requested_plan_id(spec_path), "source_generation":source_generation(spec)}
        queue = PersistentTaskQueue(_path=state/"task_queue.json", _save_interval=0)
        for item in identities.values(): queue.register_task(item)
        for _ in range(2):
            queue.record_selection(cid); queue.record_failure(cid, reason="explicit synthetic failed validation")
        queue.save()
        entry = queue.entries[cid]
        finished = entry.cooldown_until - 600 + 0.01
        terminal = {"type":"implementation_finished", "timestamp":_stamp(finished),
            "task_id":task_id, "canonical_task_cid":cid,"canonical_task_key":identity.canonical_task_key,
            "board_namespace":identity.board_namespace, "attempt":2,"attempt_consumed":True,"returncode":78}
        body = {"heartbeat_at":_stamp(now),"last_progress_at":_stamp(now),
            "active_task_id":"","active_task_cid":"","active_attempt":0,"active_phase":"",
            "implementation_in_progress":False,"recommended_task_id":task_id,
            "ready_task_ids":[task_id],"selectable_ready_task_ids":[task_id],"eligible_ready_task_ids":[task_id],
            "task_identities":{key:item.to_dict() for key,item in identities.items()},
            "implementation_attempts":{task_id:2},"implementation_attempts_by_cid":{cid:2}}
        # Use the real Native projection schema, including settled-field
        # defaults, rather than adding observer-only fields to a fake row.
        body=asdict(native.PortalTaskState(**body))
        heartbeat = {"status":"running","updated_at":_stamp(now),"supervisor_pid":owner.pid,
            "daemon_pid":child_pid,"daemon_pid_alive":True,"active_worker_count":0,"active_worker_pids":[],
            "max_task_attempts":3}
        runner._atomic_json(state/(runner.STATE_PREFIX+"_managed_daemon.identity.json"),{
            "schema":"ipfs_accelerate_py.agent_supervisor.supervised-child-identity@1",
            "command":child["argv"],"process_birth":{"pid":child_pid,"parent_pid":owner.pid,
                "start_time_ticks":child["start_ticks"],"boot_id":child["boot_id"]},
            "owner_scope":{"repo_root":str(root),"state_dir":str(state),
                "todo_path":str(root/artifacts.board_relative)}})
        board = runner._validate_board(root,root/artifacts.board_relative,spec)
        assert board["ready_task_ids"] == [task_id]
        w = SimpleNamespace(root=root,state=state,spec_path=spec_path,spec=spec,artifacts=artifacts,
            record=record,body=body,heartbeat=heartbeat,board=board,terminal=terminal,task_id=task_id,cid=cid,
            identities=identities,queue=queue,deadline=entry.cooldown_until,now=time.time())
        def save():
            runner._atomic_json(state/"launcher.json",record)
            runner._atomic_json(state/(runner.STATE_PREFIX+"_task_state.json"),body)
            runner._atomic_json(state/(runner.STATE_PREFIX+"_supervisor_status.json"),heartbeat)
            journal=state/(runner.STATE_PREFIX+"_events.jsonl")
            journal.write_text(json.dumps(terminal)+"\n");journal.chmod(0o600)
        w.save=save;save()
        def observe(**overrides):
            return activity.observe(runner,root,state,record,body,heartbeat,board,
                spec=spec,artifacts=artifacts,current_state=True,now_ts=overrides.get("now_ts",time.time()))
        w.observe=observe
        yield w
    finally:
        if owner.poll() is None:
            owner.communicate(input="x",timeout=10)
        else:
            owner.communicate(timeout=5)
        assert owner.returncode == 0


def test_real_native_queue_deadline_is_fixed_and_status_reports_cooldown(world):
    w=world; queue_path=w.state/"task_queue.json"; original=queue_path.read_bytes()
    first=w.observe(); second=w.observe(now_ts=time.time()+1)
    assert first["verified"] is True,first
    assert first == second
    assert first["retry_at"] == w.deadline
    assert first["tasks"] == [{"task_id":w.task_id,"task_cid":w.cid,"attempt":2,
        "attempts_remaining":1,"retry_at":w.deadline}]
    assert first["progress_verified"] is False and first["completion_authority"] is False
    observed=runner.status(w.root,w.spec_path,w.state)
    assert observed["status"] == "retry_cooldown",observed
    assert observed["healthy"] is True and observed["retry_cooldown_verified"] is True
    assert observed["progress_verified"] is False and not observed["provider_progress_verified"]
    assert observed["retry_cooldown_evidence"]["retry_at"] == w.deadline
    assert queue_path.read_bytes() == original
    assert not w.observe(now_ts=w.deadline)["verified"]


@pytest.mark.parametrize("damage",["expired","far_deadline","nan_deadline","boolean_deadline",
    "attempt_exhausted","attempt_state","queue_cid","queue_alias","event_cid","event_attempt",
    "event_new_selection","host_slug_namespace","different_board","active","manual_hold","operator_hold","source_generation",
    "source_conflict","stale_heartbeat","daemon_birth","daemon_dead","daemon_command","queue_symlink",
    "uncooled_ready","no_change_without_receipt"])
def test_invalid_cooldown_does_not_suppress_stall_detection(world,damage):
    w=world; path=w.state/"task_queue.json"; queue=json.loads(path.read_text());entry=queue["entries"][w.cid]
    if damage=="expired":entry["cooldown_until"]=time.time()-1
    elif damage=="far_deadline":entry["cooldown_until"]+=600
    elif damage=="nan_deadline":entry["cooldown_until"]=float("nan")
    elif damage=="boolean_deadline":entry["cooldown_until"]=True
    elif damage=="attempt_exhausted":entry["attempt_count"]=3
    elif damage=="attempt_state":w.body["implementation_attempts_by_cid"][w.cid]=1
    elif damage=="queue_cid":entry["canonical_task_cid"]="bwrong"
    elif damage=="queue_alias":queue["aliases"][w.task_id]="bwrong"
    elif damage=="event_cid":w.terminal["canonical_task_cid"]="bwrong"
    elif damage=="event_attempt":w.terminal["attempt"]=1
    elif damage=="event_new_selection":w.terminal["type"]="task_selected"
    elif damage=="host_slug_namespace":w.terminal["board_namespace"]=w.artifacts.board_namespace
    elif damage=="different_board":entry["provenance"][0]["source_path"]="/different/board.md"
    elif damage=="active":w.body["active_task_id"]=w.task_id
    elif damage=="manual_hold":w.body["manual_hold"]=True
    elif damage=="operator_hold":
        (w.state/"watchdog").mkdir(mode=0o700);(w.state/"watchdog/HOLD").touch()
    elif damage=="source_generation":w.record["source_generation"]="0"*64
    elif damage=="source_conflict":w.body["proof_stale"]=True
    elif damage=="stale_heartbeat":w.heartbeat["updated_at"]=_stamp(time.time()-121)
    elif damage=="daemon_birth":
        child_path=w.state/(runner.STATE_PREFIX+"_managed_daemon.identity.json")
        child_record=json.loads(child_path.read_text());child_record["process_birth"]["start_time_ticks"]+=1
        runner._atomic_json(child_path,child_record)
    elif damage=="daemon_dead":w.heartbeat["daemon_pid_alive"]=False
    elif damage=="daemon_command":
        child_path=w.state/(runner.STATE_PREFIX+"_managed_daemon.identity.json")
        child_record=json.loads(child_path.read_text());child_record["command"]=["wrong-command"]
        runner._atomic_json(child_path,child_record)
    elif damage=="uncooled_ready":
        other=next(k for k in w.identities if k!=w.task_id)
        for key in ("ready_task_ids","selectable_ready_task_ids","eligible_ready_task_ids"):w.body[key].append(other)
        w.board["ready_task_ids"].append(other)
    elif damage=="no_change_without_receipt":entry["consecutive_no_change"]=1
    path.write_text(json.dumps(queue));path.chmod(0o600);w.save()
    if damage=="queue_symlink":
        target=path.with_suffix('.target');path.rename(target);path.symlink_to(target)
    assert w.observe()["verified"] is False,damage


def _watcher(w,tmp_path,monkeypatch):
    tmp_path.mkdir()
    watcher,fake,view=_adapter(tmp_path,monkeypatch,state="retry_cooldown")
    watcher.clock=time.time
    observed=runner.status(w.root,w.spec_path,w.state)
    assert observed["retry_cooldown_verified"] is True,observed
    view.update(deepcopy(observed))
    fake._native_modules=lambda *_:(None,SimpleNamespace(parse_task_file=lambda *a,**kw:[
        SimpleNamespace(task_id=w.task_id,status="todo")]))
    monkeypatch.setattr(watcher,"recover",lambda *_:pytest.fail("Scheduled retry dispatched recovery."))
    return watcher,view


def test_passive_watchdog_leaves_existing_incident_ledger_byte_identical(world,tmp_path,monkeypatch):
    from ipfs_accelerate_py.agent_supervisor.rescue import campaign_watchdog as sdk
    watcher,view=_watcher(world,tmp_path/"host",monkeypatch)
    watcher.directory.mkdir(mode=0o700)
    ledger=watcher.directory/"campaign-progress-watchdog.json"
    original=b'{"explicit_synthetic_uncertain_incident_budget":1}\n'
    ledger.write_bytes(original);ledger.chmod(0o600)
    monkeypatch.setattr(sdk.CampaignProgressWatchdog,"run_once",lambda *_:pytest.fail("Cooldown entered recovery policy."))
    report=watcher.run_once()
    assert report["status"]=="cooldown" and report["reason"]=="bounded_native_retry_cooldown"
    assert report["retry_at"]==world.deadline and report["progress_verified"] is False
    assert report["provider_calls_by_watchdog"]==0 and report["attempt_refunded"] is False
    assert report["monitoring"]["monitor_class"]=="bounded_native_retry_cooldown"
    assert ledger.read_bytes()==original


@pytest.mark.parametrize("damage",["expired","hold","not_owned","unknown_worker","source_conflict"])
def test_passive_override_refusal_returns_to_native_policy(world,tmp_path,monkeypatch,damage):
    from ipfs_accelerate_py.agent_supervisor.rescue import campaign_watchdog as sdk
    watcher,view=_watcher(world,tmp_path/"host",monkeypatch)
    if damage=="expired":watcher.clock=lambda:world.deadline
    elif damage=="hold":view["native_state"]["manual_hold"]=True
    elif damage=="not_owned":view["owned_process_alive"]=False
    elif damage=="unknown_worker":view["worker_liveness"]="unknown"
    else:watcher.runner._claim_proof_conflict=lambda *_:True
    calls=[];real=sdk.CampaignProgressWatchdog.run_once
    def run_once(instance):
        calls.append(True);return real(instance)
    monkeypatch.setattr(sdk.CampaignProgressWatchdog,"run_once",run_once)
    report=watcher.run_once()
    assert calls==[True]
    assert report["reason"]!="bounded_native_retry_cooldown"
    assert report["provider_calls_by_watchdog"]==0
