"""Explicit synthetic custody fixtures, real Git and bounded Native execution.

These tests qualify Host observation predicates, never task completion. Native
births/claims/state here are declared fakes; one test delegates a real local
sleep command to the actual Native canonical executor under those fake owners.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner
from integrations.ipfs_accelerate import reconciliation_activity
from tests.test_improvement_validation_activity import ownership, _write

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _events(path, rows):
    previous = ""
    raw = []
    for sequence, body in enumerate(rows, 1):
        value = {**body, "sequence": sequence, "previous_event_id": previous}
        canonical = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
        previous = "sha256:" + hashlib.sha256(canonical).hexdigest()
        value["event_id"] = previous
        raw.append(json.dumps(value))
    path.write_text("\n".join(raw) + "\n"); path.chmod(0o600)


@pytest.fixture
def reconciled(ownership, monkeypatch):
    c = ownership
    now = time.time()
    stamp = lambda value: datetime.fromtimestamp(value, timezone.utc).isoformat()
    def git(*args):
        return subprocess.check_output(["git", "-c", "core.hooksPath=/dev/null", *args], cwd=c.workspace, text=True).strip()
    git("init", "-q"); git("config", "user.name", "Synthetic custody fixture")
    git("config", "user.email", "synthetic@example.invalid")
    source = c.workspace / "fixture.py"; source.write_text("VALUE = 1\n")
    git("add", "fixture.py"); git("commit", "-qm", "Synthetic baseline")
    baseline = git("rev-parse", "HEAD")
    source.write_text("VALUE = 2\n"); git("add", "fixture.py"); git("commit", "-qm", "Synthetic candidate")
    candidate = git("rev-parse", "HEAD"); branch = git("symbolic-ref", "--short", "HEAD")
    c.log.unlink()
    c.log = c.campaign / "implementation_logs" / (c.task["id"].lower()+"-reconciliation-validation-"+candidate[:12]+"-"+"a"*16+".log")
    c.log.write_text("Explicit synthetic reconciliation metadata.\n"); c.log.chmod(0o600)
    c.body.update(active_phase=reconciliation_activity.PHASE, active_attempt=0,
        active_phase_started_at=stamp(now-120), active_task_started_at=stamp(now-120),
        active_branch=branch, active_log_path=str(c.log), heartbeat_at=stamp(now), last_progress_at=stamp(now))
    c.lease.update(lease_role="supervisor_maintenance", state_path=str(c.campaign / (runner.STATE_PREFIX+"_task_state.json")))
    _write(c.campaign / "implementation.lock", c.lease)
    c.launcher = {"repo_root":str(c.target), "state_dir":str(c.campaign), "spec_path":str(c.target/"spec.json"),
        "started_at":now-200, "identity":{"pid":c.birth.pid,"start_ticks":c.birth.start_time_ticks,"boot_id":c.birth.boot_id}}
    _write(c.campaign/"launcher.json",c.launcher)
    window = {"schema":"ipfs_accelerate_py/agent-supervisor/supervisor-maintenance@1",
        "started_at":stamp(now-150),"timeout_seconds":900.0,"deadline_at":stamp(now+750),"phase":"running","finished_at":None}
    c.heartbeat = {"status":"agentic_maintenance_started","updated_at":stamp(now),"supervisor_pid":c.birth.pid,
        "daemon_pid":None,"last_agentic_maintenance_status":"running","last_agentic_maintenance_error":"",
        "last_agentic_maintenance_phase":"synthetic_reconciliation","supervisor_maintenance":window,
        "active_agentic_maintenance_started_at":window["started_at"],"active_agentic_maintenance_timeout_seconds":900.0}
    _write(c.campaign/(runner.STATE_PREFIX+"_supervisor_status.json"),c.heartbeat)
    c.receipt = {"schema":"ipfs_accelerate_py/agent-supervisor/supervisor-maintenance-receipt@1",
        "status":"running","completed_at":"","updated_at":stamp(now),"supervisor_pid":c.birth.pid,
        "process_birth":c.birth.to_dict(),"maintenance_started_at":window["started_at"],
        "phase":"synthetic_reconciliation","repo_root":str(c.target),"state_dir":str(c.campaign),
        "state_path":str(c.campaign/(runner.STATE_PREFIX+"_task_state.json"))}
    _write(c.campaign/(runner.STATE_PREFIX+"_supervisor_maintenance_receipt.json"),c.receipt)
    c.native.SUPERVISOR_MAINTENANCE_RECEIPT_SCHEMA=c.receipt["schema"]
    c.start = {"type":"worktree_reconciliation_validation_started","timestamp":stamp(now-119),
        "task_id":c.task["id"],"canonical_task_cid":c.context["task_cid"],"canonical_task_key":c.context["task_key"],
        "attempt":1,"worktree_path":str(c.workspace),"branch":branch,"baseline_ref":baseline,
        "implementation_commit":candidate,"log_path":str(c.log),"attempt_consumed":False,"provider_dispatched":False}
    c.accepted = {"type":"implementation_proposal_validated","timestamp":stamp(now-118),
        "task_id":c.task["id"],"canonical_task_cid":c.context["task_cid"],"canonical_task_key":c.context["task_key"],
        "accepted":True,"attempted":True,"reason_codes":[],"repository_tree_id":baseline,
        "proposal_id":"a"*64,"receipt_id":"b"*64,"policy_id":"c"*64}
    c.event_path=c.campaign/(runner.STATE_PREFIX+"_events.jsonl")
    _events(c.event_path,[c.start,c.accepted])
    monkeypatch.setattr(runner,"owns_process",lambda launch:launch==c.launcher)
    monkeypatch.setattr(runner,"_campaign_tuple_matches",lambda launch,target,spec,state:launch==c.launcher and target==c.target and state==c.campaign)
    monkeypatch.setattr(runner,"_read_native_state",lambda *_:(deepcopy(c.body),{"source":"native_control_plane"}))
    monkeypatch.setattr(runner,"_campaign_spec",lambda *_:(SimpleNamespace(),runner.DEFAULT_ARTIFACTS))
    monkeypatch.setattr(runner,"_validate_board",lambda *_:{"count":2,"completed":0,"ready_task_ids":[c.task["id"]],"manual_hold_task_ids":[]})
    return c


def _binding(c, *, now=None):
    return runner._validation_activity_binding(c.workspace,c.task,c.context,now_ts=time.time() if now is None else now)


def test_synthetic_reconciliation_binding_keeps_zero_paid_ordinal_and_original_deadline(reconciled):
    c=reconciled;b=_binding(c)
    assert b and b["attempt"]==0 and b["validation_ordinal"]==1
    assert b["proposal_id"]==c.accepted["proposal_id"] and b["candidate_commit"]==c.start["implementation_commit"]
    assert b["owner_birth"]==c.birth.to_dict()
    assert b["phase_deadline"]==datetime.fromisoformat(c.heartbeat["supervisor_maintenance"]["deadline_at"]).timestamp()
    assert b["phase_deadline"] <= datetime.fromisoformat(c.body["active_phase_started_at"]).timestamp()+900


def test_reconciliation_file_reads_after_caller_clock_keep_original_bounds(reconciled):
    """Explicit synthetic custody; real Git/files, no validation authority."""
    c=reconciled;before=deepcopy(c.body)
    original=_binding(c);assert original is not None
    captured=time.time()
    time.sleep(.002)
    published=datetime.now(timezone.utc).isoformat()
    assert captured < datetime.fromisoformat(published).timestamp()
    c.heartbeat['updated_at']=c.receipt['updated_at']=published
    heartbeat=c.campaign/(runner.STATE_PREFIX+'_'+ 'supervisor_status.json')
    receipt=c.campaign/(runner.STATE_PREFIX+'_'+ 'supervisor_maintenance_receipt.json')
    _write(heartbeat,c.heartbeat);_write(receipt,c.receipt)
    observed=_binding(c,now=captured)
    assert observed==original
    future=datetime.fromtimestamp(time.time()+60,timezone.utc).isoformat()
    _write(heartbeat,{**c.heartbeat,'updated_at':future});_write(receipt,{**c.receipt,'updated_at':future})
    assert _binding(c) is None
    _write(heartbeat,c.heartbeat);_write(receipt,c.receipt)
    assert _binding(c,now=original['phase_deadline']) is None
    assert _binding(c,now=datetime.fromisoformat(published).timestamp()+121) is None
    assert c.body==before


@pytest.mark.parametrize("damage",["paid_attempt","ordinary_phase","wrong_cid","wrong_key","workspace","owner","lease",
    "claim","receipt","heartbeat_only","expiry","deadline_widened","rejected","proposal_baseline","missing_proposal",
    "candidate_dirty","candidate_changed","branch","terminal","event_chain","log_replaced","log_mode",
    "claim_bool_ordinal","start_bool_ordinal","manual_hold"])
def test_synthetic_reconciliation_refuses_unbound_or_expired_activity(reconciled,damage):
    c=reconciled
    if damage=="paid_attempt":c.body["active_attempt"]=1
    elif damage=="ordinary_phase":c.body["active_phase"]="validating"
    elif damage=="wrong_cid":c.body["active_task_cid"]="other-cid"
    elif damage=="wrong_key":c.body["active_task_key"]="other-key"
    elif damage=="workspace":c.body["active_worktree_path"]=str(c.target)
    elif damage=="owner":c.launcher["identity"]["start_ticks"]+=1;_write(c.campaign/"launcher.json",c.launcher)
    elif damage=="lease":_write(c.campaign/"implementation.lock",{**c.lease,"lease_role":"ordinary"})
    elif damage=="claim":_write(c.claim_path,{**c.claim,"attempt":2})
    elif damage=="claim_bool_ordinal":_write(c.claim_path,{**c.claim,"attempt":True})
    elif damage=="start_bool_ordinal":c.start["attempt"]=True;_events(c.event_path,[c.start,c.accepted])
    elif damage=="manual_hold":c.body['manual_hold']=True
    elif damage=="receipt":_write(c.campaign/(runner.STATE_PREFIX+"_supervisor_maintenance_receipt.json"),{**c.receipt,"status":"completed"})
    elif damage=="heartbeat_only":c.event_path.unlink()
    elif damage=="expiry":c.body["active_phase_started_at"]=datetime.fromtimestamp(time.time()-901,timezone.utc).isoformat()
    elif damage=="deadline_widened":
        h=deepcopy(c.heartbeat);h["supervisor_maintenance"]["timeout_seconds"]=901;_write(c.campaign/(runner.STATE_PREFIX+"_supervisor_status.json"),h)
    elif damage=="rejected":c.accepted["accepted"]=False;_events(c.event_path,[c.start,c.accepted])
    elif damage=="proposal_baseline":c.accepted["repository_tree_id"]="d"*40;_events(c.event_path,[c.start,c.accepted])
    elif damage=="missing_proposal":_events(c.event_path,[c.start])
    elif damage=="candidate_dirty":(c.workspace/"fixture.py").write_text("VALUE = 3\n")
    elif damage=="candidate_changed":subprocess.run(["git","checkout","-q","--detach",c.start["baseline_ref"]],cwd=c.workspace,check=True)
    elif damage=="branch":c.body["active_branch"]="other"
    elif damage=="terminal":_events(c.event_path,[c.start,c.accepted,{**c.start,"type":"worktree_reconciliation_validation_finished"}])
    elif damage=="event_chain":
        with c.event_path.open("a") as handle:handle.write('{"sequence":99}\n')
    elif damage=="log_replaced":c.log.unlink();c.log.symlink_to(c.workspace/"fixture.py")
    else:c.log.chmod(0o644)
    assert _binding(c) is None


def test_synthetic_status_does_not_treat_fresh_maintenance_heartbeat_as_progress(reconciled):
    c=reconciled
    result=runner.status(c.target,c.target/"spec.json",c.campaign)
    assert result["status"]=="daemon_failed" and result["validation_activity_verified"] is False
    assert result["progress_verified"] is False and result["provider_progress_verified"] is False


def test_actual_bounded_native_executor_is_observable_under_synthetic_reconciliation_custody(reconciled,monkeypatch):
    c=reconciled
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import PortalImplementationDaemon
    from ipfs_accelerate_py.agent_supervisor.validation.validation_runtime import build_validation_environment, validation_environment_for_runner
    executor=PortalImplementationDaemon._validation_command_runner
    c.daemon.PortalImplementationDaemon._validation_command_runner=staticmethod(executor)
    monkeypatch.setattr(runner,"_VALIDATION_ACTIVITY_INTERVAL_SECONDS",0.05)
    observed=[];stopped=threading.Event()
    def observe():
        while not stopped.wait(0.02):
            result=runner.status(c.target,c.target/"spec.json",c.campaign)
            if result["validation_activity_verified"]:
                observed.append(result);return
    worker=threading.Thread(target=observe,daemon=True);worker.start()
    before=deepcopy(c.body)
    environment=validation_environment_for_runner(build_validation_environment({
        "PATH":"/usr/bin:/bin", "LANG":"C.UTF-8", "IPFS_ACCELERATE_AGENT_VALIDATION_PYTHON":sys.executable}),executor)
    try:
        result=runner._call_validation_with_activity(executor=executor,
            spec=SimpleNamespace(command="sleep 1",raw_command="sleep 1"),workspace_path=c.workspace,
            timeout_seconds=5,environment=environment,task=c.task,context=c.context)
    finally:
        stopped.set();worker.join(timeout=3)
    assert result["returncode"]==0, {key:result.get(key) for key in ("returncode","error","reason")}
    assert observed
    assert observed[0]["status"]=="active" and observed[0]["healthy"] is True
    assert observed[0]["worker_liveness"]=="alive" and observed[0]["progress_verified"] is True
    assert observed[0]["provider_progress_verified"] is False and observed[0]["provider_execution_verified"] is False
    assert observed[0]["validation_activity_evidence"]["attempt"]==0
    assert c.body==before and not runner._validation_activity_path(_binding(c)).exists()
    settled=reconciliation_activity.evidence(runner,c.target,c.campaign,c.launcher,c.body,now_ts=time.time())
    assert settled["type"]=="canonical_reconciled_validation_finalizing"
    assert settled["attempt"]==0 and settled["completion_authority"] is False
    assert reconciliation_activity.evidence(runner,c.target,c.campaign,c.launcher,c.body,
        now_ts=settled["deadline_at"]) is None
    assert c.body==before


def _native_catalog(campaign, body):
    import duckdb
    path, board = reconciliation_activity.catalog_path(runner, campaign)
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    connection=duckdb.connect(str(path))
    try:
        if board:
            connection.execute("CREATE TABLE artefact_generic(board_namespace VARCHAR, kind VARCHAR, artefact_id VARCHAR, payload_json VARCHAR, updated_at_ms BIGINT)")
            connection.execute("INSERT INTO artefact_generic VALUES (?, ?, ?, ?, ?)",
                ['portal-task-state','portal_task_state',runner.STATE_PREFIX+'_task_state',json.dumps(body),123])
        else:
            from ipfs_accelerate_py.agent_supervisor.todo_daemon.portal_task_state_control_plane import DDL
            connection.execute(DDL)
            connection.execute("INSERT INTO portal_task_state VALUES (?, ?, ?, ?, ?)",
                [runner.STATE_PREFIX+'_task_state',json.dumps(body),123,False,'synthetic-clock'])
    finally:connection.close()
    return path


def test_scoped_native_catalog_reader_ignores_ambient_authority_and_never_creates_catalog(tmp_path,monkeypatch):
    outer=tmp_path/'outer';outer.mkdir()
    subprocess.run(['git','init','-q',str(outer)],check=True)
    campaign=outer/'campaign';campaign.mkdir(mode=0o700)
    missing_path,_=reconciliation_activity.catalog_path(runner,campaign)
    assert reconciliation_activity.snapshot(runner,campaign) is None and not missing_path.parent.exists()
    body={'active_task_id':'SYNTHETIC-ONLY','active_attempt':1,'completion_authority':False}
    path=_native_catalog(campaign,body)
    decoy=tmp_path/'unrelated-global.duckdb'
    monkeypatch.setenv('IPFS_ACCELERATE_AGENT_CONTROL_DUCKDB',str(decoy))
    monkeypatch.setenv(runner.ORCHESTRATION_DIR_ENV,str(tmp_path/'unrelated-orchestration'))
    before=(path.stat().st_mtime_ns,path.stat().st_size)
    value=reconciliation_activity.snapshot(runner,campaign)
    assert value=={'body':body,'revision':123,'authority_path':str(path)}
    assert (path.stat().st_mtime_ns,path.stat().st_size)==before and not decoy.exists()
    assert os.environ[runner.ORCHESTRATION_DIR_ENV]==str(tmp_path/'unrelated-orchestration')


@pytest.fixture
def ordinary(ownership,monkeypatch):
    c=ownership;now=time.time()
    c.body.update(active_task_started_at=datetime.fromtimestamp(now-200,timezone.utc).isoformat(),
        heartbeat_at=datetime.now(timezone.utc).isoformat(),last_progress_at=datetime.now(timezone.utc).isoformat())
    launcher={'repo_root':str(c.target),'state_dir':str(c.campaign),'started_at':now-300,'identity':{'pid':991120}}
    _write(c.campaign/'launcher.json',launcher)
    _write(c.campaign/(runner.STATE_PREFIX+'_supervisor_status.json'),{'status':'running','supervisor_pid':991120,
        'daemon_pid':c.birth.pid,'daemon_pid_alive':True,'updated_at':datetime.now(timezone.utc).isoformat()})
    monkeypatch.setattr(runner,'owns_process',lambda value:value==launcher)
    monkeypatch.setattr(runner,'process_identity',lambda pid:{'pid':c.birth.pid,'ppid':991120} if pid==c.birth.pid else None)
    monkeypatch.setattr(runner,'_read_native_state',lambda *_:(deepcopy(c.body),{'source':'native_control_plane'}))
    monkeypatch.setattr(runner,'_campaign_spec',lambda *_:(SimpleNamespace(),runner.DEFAULT_ARTIFACTS))
    monkeypatch.setattr(runner,'_validate_board',lambda *_:{'count':2,'completed':0,'ready_task_ids':[c.task['id']],'manual_hold_task_ids':[]})
    monkeypatch.setattr(runner,'_owned_attempt_log_evidence',lambda *_a,**_kw:{'provider_terminal_observed':True,'progress_fresh':False})
    c.launcher=launcher
    return c


def test_synthetic_ordinary_private_executor_activity_dominates_provider_end_without_budget_change(ordinary):
    c=ordinary;before=deepcopy(c.body)
    quiet=runner.status(c.target,c.target/'spec.json',c.campaign)
    assert quiet['status']=='stalled' and quiet['healthy'] is False and quiet['validation_activity_verified'] is False
    b=_binding(c);assert b and b['attempt']==1
    now=time.time()
    assert runner._publish_validation_activity(b,activity_id='f'*32,started_at=now,deadline_at=min(b['phase_deadline'],now+20))
    current=runner.status(c.target,c.target/'spec.json',c.campaign)
    assert current['status']=='active' and current['healthy'] is True
    assert current['validation_activity_evidence']['type']=='canonical_native_validation_in_flight'
    assert current['provider_progress_verified'] is False and c.body==before
    runner._clear_validation_activity(b,'f'*32)
    assert runner.status(c.target,c.target/'spec.json',c.campaign)['status']=='stalled'


@pytest.mark.parametrize('damage',['parent','claim','expiry','overall_deadline'])
def test_synthetic_ordinary_observer_cannot_borrow_another_owner_or_renew_deadline(ordinary,monkeypatch,damage):
    c=ordinary;b=_binding(c);now=time.time()
    assert runner._publish_validation_activity(b,activity_id='e'*32,started_at=now,deadline_at=min(b['phase_deadline'],now+20))
    if damage=='parent':monkeypatch.setattr(runner,'process_identity',lambda pid:{'pid':c.birth.pid,'ppid':123456})
    elif damage=='claim':_write(c.claim_path,{**c.claim,'lease_id':'replacement-claim'})
    elif damage=='expiry':
        path=runner._validation_activity_path(b);value=runner._read_validation_activity(path);value['observed_at']=now-100;_write(path,value)
    else:c.body['active_task_started_at']=datetime.fromtimestamp(now-901,timezone.utc).isoformat()
    value=runner.status(c.target,c.target/'spec.json',c.campaign)
    if damage=='overall_deadline':
        # Provider time does not consume the separate existing validation
        # window. The exact pulse retains its original deadline unchanged.
        assert value['status']=='active' and value['healthy'] is True
        assert value['scope_liveness']['claim']=='held'
        assert value['validation_activity_evidence']['deadline_at']==runner._read_validation_activity(
            runner._validation_activity_path(b))['deadline_at']
    else:
        assert value['status']!='active' and value['healthy'] is False


@pytest.mark.parametrize('flag',['manual_hold','manual_cancellation'])
def test_synthetic_private_activity_cannot_mask_an_explicit_application_hold(ordinary,flag):
    c=ordinary;b=_binding(c);now=time.time()
    assert runner._publish_validation_activity(b,activity_id='d'*32,started_at=now,deadline_at=min(b['phase_deadline'],now+20))
    c.body[flag]=True
    result=runner.status(c.target,c.target/'spec.json',c.campaign)
    assert result['application_interview_state'] in {'manual_hold','cancelled'}
    assert result['validation_activity_verified'] is False and result['progress_verified'] is False
