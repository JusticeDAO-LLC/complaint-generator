"""Private synthetic campaigns, real Native claims/events and inert Popen.

No model, task completion, merge, retry/refund or live campaign is invoked.
The provider emits synthetic NDJSON under Native's actual rescue producer.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import sys
import subprocess
import threading
import time

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner
from integrations.ipfs_accelerate import auto_rescue_activity as activity

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _stamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


@contextmanager
def _native_world(tmp_path, monkeypatch, *, frame_kind="thought", setup_seconds=0, selection_seconds=None):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import supervisor_runtime as runtime
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import portal_task_state_control_plane as plane
    from integrations.ipfs_accelerate.reconciliation_activity import catalog_path
    tmp_path.mkdir(parents=True,exist_ok=True)
    root = Path(runner.__file__).resolve().parents[2]
    native_root=Path(native.__file__).resolve().parents[3]
    expected=subprocess.check_output(['git','rev-parse','HEAD:external/ipfs_accelerate_py'],cwd=root,text=True).strip()
    actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=native_root,text=True).strip()
    assert actual==expected, 'The Native fixture must import the source pinned by this checkout.'
    assert Path(native.PortalImplementationDaemon._automatic_implementation_rescue.__code__.co_filename).resolve()==Path(native.__file__).resolve()
    (tmp_path/'native-origin.json').write_text(json.dumps({'module_path':str(Path(native.__file__).resolve()),
        'module_sha256':hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest(),'sdk_git_head':actual,
        'expected_root_gitlink':expected,'actual_producer_method_origin_matches':True})+'\n')
    spec = root / "docs/task_boards/complaint_gui_collaboration_spec.json"
    _, artifacts = runner._campaign_spec(root, spec)
    campaign = tmp_path / "campaign"; campaign.mkdir(mode=0o700)
    workspace = campaign / "worktrees/inert-rescue"; workspace.mkdir(parents=True)
    daemon = native.PortalImplementationDaemon(todo_path=root / artifacts.board_relative,
        state_path=campaign / (runner.STATE_PREFIX + "_task_state.json"),
        strategy_path=campaign / (runner.STATE_PREFIX + "_strategy.json"),
        events_path=campaign / (runner.STATE_PREFIX + "_events.jsonl"),
        repo_root=root, task_header_prefix=runner.TASK_PREFIX,
        worktree_root=campaign / "worktrees", board_namespace=artifacts.board_namespace,
        implementation_timeout=runner.TIMEOUT_SECONDS, implement=False)
    tasks = daemon._load_tasks(); daemon._register_task_identities(tasks)
    task = next(task for task in tasks if task.task_id == "CIMP-GUI-60")
    identity = daemon._identity_for_task(task)
    now = time.time(); started = _stamp(now - setup_seconds)
    lease = daemon._build_implementation_lock_metadata(task, 1, started)
    claim = daemon._build_implementation_task_claim_metadata(task, 1, started)
    lease_path = daemon._implementation_lock_path()
    claim_path = daemon._implementation_task_claim_path(task.task_id, canonical_task_cid=identity.canonical_task_cid)
    assert daemon._try_acquire_implementation_lock(lease_path, lease)[0]
    assert daemon._try_acquire_implementation_task_claim(claim_path, claim)[0]
    log = campaign / "implementation_logs" / (task.task_id.lower() + "-attempt-1-" + "a"*32 + ".log")
    log.parent.mkdir(); log.write_text(f"Task: {task.task_id} Synthetic inert repair\nStarted: {started}\nWorkspace: {workspace}\n")
    log.chmod(0o600)
    # A real inert primary stream, including its terminal frame, precedes the
    # real Native repair producer. These are not manufactured birth receipts.
    with log.open("a") as handle:
        runtime.run_process_group_stream([sys.executable, "-I", "-B", "-c",
            "import json; print(json.dumps({'type':'usage','usage':{}}),flush=True); print(json.dumps({'type':'end'}),flush=True)"],
            cwd=workspace, stdout=handle, env={}, inherit_environment=False, timeout_seconds=10)
    daemon._record_event("implementation_started", {"task_id": task.task_id, "attempt": 1,
        "worktree_path": str(workspace), "log_path": str(log), "execution_mode": "model-assisted"})
    validation_started = _stamp(time.time())
    state = native.PortalTaskState()
    for key, value in {"active_task_id":task.task_id,"active_task_cid":identity.canonical_task_cid,
        "active_task_key":identity.canonical_task_key,"active_attempt":1,"implementation_in_progress":True,
        "active_phase":"validating","active_task_started_at":_stamp(now-selection_seconds if selection_seconds is not None else now-setup_seconds-3 if setup_seconds else now-300),"active_phase_started_at":validation_started,
        "active_worktree_path":str(workspace),"active_log_path":str(log),
        "last_implementation_task_id":task.task_id,"last_implementation_task_cid":identity.canonical_task_cid,
        "last_implementation_task_key":identity.canonical_task_key,"last_implementation_started_at":started,
        "last_implementation_worktree_path":str(workspace),"last_implementation_log_path":str(log),
        "heartbeat_at":validation_started,"last_progress_at":validation_started}.items():
        setattr(state,key,value)
    state.implementation_attempts={task.task_id:1};state.implementation_attempts_by_cid={identity.canonical_task_cid:1}
    target,_ = catalog_path(runner,campaign);plane.bind_task_state_control_plane(daemon.state_path,str(target))
    state.save(daemon.state_path)
    body=runner._validation_activity_snapshot(campaign)["body"]
    parent = runner.process_identity(os.getppid())
    assert parent is not None
    launcher={"schema_version":"complaint-improvement-launcher@1","repo_root":str(root),
        "state_dir":str(campaign),"spec_path":str(spec),"board_path":str(root/artifacts.board_relative),
        "plan_id":runner._requested_plan_id(spec),"provider":"grok_cli","model":runner.MODEL,"allow_fallback":False,
        "identity":parent,"argv":parent["argv"],"status":"running","owner_token":"private-inert-fixture",
        "started_at":now-max(400,(selection_seconds or 0)+100)}
    runner._atomic_json(campaign/"launcher.json",launcher)
    runner._atomic_json(campaign/(runner.STATE_PREFIX+"_supervisor_status.json"),{
        "status":"running","supervisor_pid":parent["pid"],"daemon_pid":os.getpid(),
        "daemon_pid_alive":True,"updated_at":started})
    runtime.write_supervised_child_identity(campaign/(runner.STATE_PREFIX+"_managed_daemon.identity.json"),
        pid=os.getpid(), command=runtime.read_process_command_argv(os.getpid()), owner_scope={
        "repo_root":str(root),"state_dir":str(campaign),"state_prefix":runner.STATE_PREFIX,
        "todo_path":str(root/artifacts.board_relative),"daemon_entrypoint":str(Path(runner.__file__).resolve())})
    # Only planning/output-validation are synthetic here; the actual rescue
    # body owns its real start event, child, stdout, budget and cleanup.
    monkeypatch.setattr(daemon,"_expected_outputs_present_on_disk",lambda *a:True)
    monkeypatch.setattr(daemon,"_dirty_in_scope_declared_output_paths",lambda *a:())
    monkeypatch.setattr(daemon,"_stage_declared_candidate_outputs",lambda *a:())
    monkeypatch.setattr(daemon,"_run_validation_with_candidate_binding",lambda *a,**kw:{"passed":False,"reason":"synthetic_validation_not_performed"})
    monkeypatch.setattr(daemon,"_apply_implementation_failure_review",lambda **kw:dict(kw["validation_result"]))
    program = """import json,os,pathlib,sys,time
sys.stdin.read()
root=pathlib.Path.cwd()
kind=sys.argv[1]
if kind=='redirect_stdout':
 descriptor=os.open(root/'other-output.log',os.O_WRONLY|os.O_CREAT,0o600)
 os.dup2(descriptor,1);os.close(descriptor);kind='thought'
if kind=='different_cwd':
 (root/'other-cwd').mkdir();os.chdir(root/'other-cwd');kind='thought'
while not (root/'release').exists():
 frame={'type':kind,'text':'synthetic inert provider output'}
 if kind=='usage':frame['usage']={}
 print(json.dumps(frame),flush=True)
 (root/'ready').touch()
 time.sleep(0.025)
print(json.dumps({'type':'end'}),flush=True)
"""
    results, errors = [], []
    def run():
        try:
            results.append(daemon._automatic_implementation_rescue(task=task,attempt=1,workspace_path=workspace,
                branch_name="synthetic-inert-rescue",baseline_ref="a"*40,
                validation_result={"passed":False,"reason":"declared_validation_failed","error":"validation_command_failed",
                    "failed_commands":["synthetic validation"],"failure_review":{"decision":"guide_rescue","reason_codes":["validation_command_failed"]}},
                log_path=log,state=state,command=[sys.executable,"-I","-B","-c",program,frame_kind],
                base_prompt="Synthetic inert provider fixture; no model.",provider_deadline=time.monotonic()+runner.TIMEOUT_SECONDS))
        except BaseException as exc:errors.append(exc)
    worker=threading.Thread(target=run,daemon=True);worker.start()
    deadline=time.monotonic()+15
    while not (workspace/"ready").exists() and worker.is_alive() and time.monotonic()<deadline:time.sleep(.01)
    try:
        assert (workspace/"ready").exists(), errors
        yield {"root":root,"campaign":campaign,"workspace":workspace,"daemon":daemon,"task":task,
            "body":body,"log":log,"lease_path":lease_path,"claim_path":claim_path,"worker":worker,"spec":spec}
    finally:
        (workspace/"release").touch();worker.join(15)
        assert not worker.is_alive() and not errors, errors
        assert results and not results[0].get("passed"), "Fixture cannot manufacture completion."
        assert daemon._release_implementation_task_claim(claim_path,claim)
        assert daemon._release_implementation_lock(lease_path,lease)


@pytest.mark.parametrize("kind",["thought","text","usage","tool_call","tool_call_update"])
def test_actual_native_rescue_producer_has_owned_bounded_activity(tmp_path,monkeypatch,kind):
    with _native_world(tmp_path,monkeypatch,frame_kind=kind) as world:
        result=activity.observe(runner,world["root"],world["campaign"],world["body"],now_ts=time.time())
        assert result["activity_verified"] is True,json.dumps(result,sort_keys=True)
        assert result["work_progress_verified"] is (kind in activity._WORK)
        assert result["reason"]=="bounded_native_rescue_activity"
        primary = next(json.loads(line) for line in world["daemon"].events_path.read_text().splitlines()
                       if json.loads(line).get("type") == "implementation_started")
        assert result["deadline_at"] <= runner._event_timestamp(primary) + runner.TIMEOUT_SECONDS
        assert result["provider_birth"]["parent_pid"]==os.getpid()
        assert result["completion_authority"] is False


def test_actual_rescue_deadline_starts_after_checkout_not_at_selection(tmp_path, monkeypatch):
    """Real Native repair after a synthetic 51-second setup, with actual births."""
    with _native_world(tmp_path, monkeypatch, frame_kind="tool_call", setup_seconds=51) as world:
        result = activity.observe(runner, world["root"], world["campaign"], world["body"], now_ts=time.time())
        assert result["activity_verified"] is True, result
        old_start = runner._event_timestamp({"timestamp": world["body"]["last_implementation_started_at"]})
        rows = [json.loads(line) for line in world["daemon"].events_path.read_text().splitlines()]
        primary = next(row for row in rows if row["type"] == "implementation_started")
        actual_start = runner._event_timestamp(primary)
        phase_start = runner._event_timestamp({"timestamp": world["body"]["active_phase_started_at"]})
        assert result["deadline_at"] == min(actual_start, phase_start) + runner.TIMEOUT_SECONDS
        assert result["deadline_at"] > old_start + runner.TIMEOUT_SECONDS + 40
        first_deadline = result["deadline_at"]
        time.sleep(.05)
        fresh = activity.observe(runner, world["root"], world["campaign"], world["body"], now_ts=time.time())
        assert fresh["activity_verified"] is True and fresh["deadline_at"] == first_deadline
        assert fresh["log_bytes"] >= result["log_bytes"]


def test_actual_growing_stdout_preserves_complete_owned_prefix(tmp_path,monkeypatch):
    with _native_world(tmp_path,monkeypatch) as world:
        real=os.pread; appended=[]
        def read(descriptor,size,offset):
            data=real(descriptor,size,offset)
            if not appended:
                current=world["log"].stat().st_size
                deadline=time.monotonic()+2
                while world["log"].stat().st_size==current and time.monotonic()<deadline:time.sleep(.005)
                assert world["log"].stat().st_size>current
                appended.append(True)
            return data
        monkeypatch.setattr(activity.os,"pread",read)
        raw, info=activity._append_prefix(world["log"])
        assert len(raw)==info.st_size and appended
        assert world["log"].stat().st_size>len(raw)


def test_primary_terminal_followed_by_real_native_thought_is_not_work_progress(tmp_path,monkeypatch):
    with _native_world(tmp_path,monkeypatch) as world:
        binding=runner._attempt_binding(world["body"])
        original=runner._owned_attempt_log_evidence(world["daemon"].events_path,world["campaign"],binding,
            started_at=runner._event_timestamp({"timestamp":world["body"]["active_task_started_at"]})-1,now=time.time())
        # This is a real producer reproduction of the old reader's condition,
        # not a claim about the uncaptured actual Task35 rejection branch.
        assert original is None or original["provider_terminal_observed"] is True
        current=activity.observe(runner,world["root"],world["campaign"],world["body"],now_ts=time.time())
        assert current["activity_verified"] is True and current["work_progress_verified"] is False,current


def _status_in_owned_parent(tmp_path, mode, *, setup_seconds=0, selection_seconds=None):
    """Actual session-leading parent argv, actual Native worker/repair child.

    The parent is inert (not public start/Docker qualification). Its real
    _run/owner-token argv satisfies the existing ownership reader unchanged.
    Selection/header ages are explicit synthetic metadata; execution and
    rescue events, process births and streams come from actual Native owners.
    """
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import supervisor_runtime as runtime
    native_root=Path(native.__file__).resolve().parents[3]
    paths=[str(Path(runner.__file__).resolve().parents[2]),str(native_root),
        str(native_root.parent/'ipfs_datasets_py'),str(native_root.parent/'ipfs_kit_py')]
    worker=tmp_path/'worker.py';parent=tmp_path/'parent.py';output=tmp_path/'closed-status.json'
    worker.write_text('import sys\nsys.path[:0]='+repr(paths)+'\n'+'''
from pathlib import Path
import json,time,pytest
from tests.test_owned_auto_rescue_activity import _native_world
from integrations.ipfs_accelerate import improvement_runner as runner
from ipfs_accelerate_py.agent_supervisor.todo_daemon import supervisor_runtime as runtime
def main():
 with pytest.MonkeyPatch.context() as patch:
  with _native_world(Path(sys.argv[1]),patch,setup_seconds=float(sys.argv[4]),
       selection_seconds=float(sys.argv[5]) if sys.argv[5] else None) as world:
   if sys.argv[2] in {'finished','dead_clock_window'}:
    (world['workspace']/'release').touch();world['worker'].join(10)
    assert not world['worker'].is_alive()
    with world['log'].open('a') as log:
     runtime.run_process_group_stream([sys.executable,'-I','-B','-c','import json; print(json.dumps(dict(type="tool_call")),flush=True)'],
      cwd=world['workspace'],stdout=log,env={},inherit_environment=False,timeout_seconds=10)
   if sys.argv[2].startswith('validation_'):
    from tests.test_owned_validation_status import observe_actual_executor
    closed=observe_actual_executor(world,sys.argv[2])
    Path(sys.argv[3]).write_text(json.dumps(closed))
    return
   original_claim=None
   try:
    if sys.argv[2]=='foreign_clock_window':
     original_claim=world['claim_path'].read_bytes()
     claim=json.loads(original_claim);claim['canonical_task_cid']='explicit-synthetic-foreign-cid'
     world['claim_path'].write_text(json.dumps(claim))
    if sys.argv[2]=='paused_clock_window':
     from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
     state=native.PortalTaskState.load(world['daemon'].state_path)
     state.active_phase='paused'
     state.save(world['daemon'].state_path)
    if sys.argv[2] in {'execution_deadline','execution_expired','phase_expired'}:
     primary=next(json.loads(line) for line in world['daemon'].events_path.read_text().splitlines()
                  if json.loads(line).get('type')=='implementation_started')
     if sys.argv[2] in {'execution_deadline','execution_expired'}:
      observed_now=runner._event_timestamp(primary)+runner.TIMEOUT_SECONDS+(0 if sys.argv[2]=='execution_deadline' else .01)
      # Simulate validation beginning near the actual execution deadline:
      # its separate phase cap is still open when the provider cap expires.
      from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
      state=native.PortalTaskState.load(world['daemon'].state_path)
      from tests.test_owned_auto_rescue_activity import _stamp
      state.active_phase_started_at=_stamp(observed_now-10)
      state.save(world['daemon'].state_path)
     else:
      observed_now=runner._event_timestamp({'timestamp':world['body']['active_phase_started_at']})+runner.TIMEOUT_SECONDS+.01
     # Only the observation clock is controlled, never Native's monotonic
     # provider budget, child birth, event timestamp or progress flags.
     with pytest.MonkeyPatch.context() as clock:
      clock.setattr(runner.time,'time',lambda:observed_now)
      value=runner.status(world['root'],world['spec'],world['campaign'])
    else:
     value=runner.status(world['root'],world['spec'],world['campaign'])
   finally:
    if original_claim is not None:world['claim_path'].write_bytes(original_claim)
   allowed=('status','healthy','native_read_errors','worker_liveness','auto_rescue_activity_verified','auto_rescue_activity_evidence',
    'provider_progress_verified','validation_activity_verified','progress_verified','scope_liveness')
   closed={key:value.get(key) for key in allowed}
   Path(sys.argv[3]).write_text(json.dumps(closed))
if __name__=='__main__':main()
''')
    parent.write_text('import subprocess,sys\nraise SystemExit(subprocess.call(sys.argv[4:]))\n')
    with (tmp_path/'child-output.log').open('w') as capture:
        completed=runtime.run_process_group_stream([sys.executable,'-I','-B',str(parent),'_run','--owner-token',
            'private-inert-fixture',sys.executable,'-I','-B',str(worker),str(tmp_path/'native'),mode,str(output),
            str(setup_seconds),str(selection_seconds) if selection_seconds is not None else ''],
            cwd=tmp_path,stdout=capture,env=dict(os.environ),inherit_environment=False,timeout_seconds=45)
    assert completed.returncode==0, 'Inert Native worker failed; inspect its private child-output.log.'
    return json.loads(output.read_text())


@pytest.mark.parametrize('mode',['running','finished'])
def test_actual_native_rescue_status_keeps_original_owned_parent_guard(tmp_path,mode):
    result=_status_in_owned_parent(tmp_path,mode)
    assert result['native_read_errors']=={},result
    assert result['status']==('active' if mode=='running' else 'stalled'),result
    assert result['healthy'] is (mode=='running'),result
    assert result['auto_rescue_activity_verified'] is (mode=='running'),result
    assert result['provider_progress_verified'] is False and result['progress_verified'] is False
    assert result['validation_activity_verified'] is False
    if mode=='running':
        assert result['scope_liveness']['provider']=='fresh' and result['scope_liveness']['validation']=='idle'


@pytest.mark.parametrize('mode,expected_status,expected_reason',[
    ('running_clock_window','active','bounded_native_rescue_activity'),
    ('foreign_clock_window','stalled','native_binding_unavailable'),
    ('execution_deadline','stalled','provider_deadline_expired'),
    ('execution_expired','stalled','provider_deadline_expired'),
    ('phase_expired','stalled','native_binding_unavailable'),
])
def test_actual_public_status_uses_verified_rescue_clock_and_preserves_refusals(
    tmp_path,mode,expected_status,expected_reason,
):
    result=_status_in_owned_parent(tmp_path,mode,setup_seconds=51,selection_seconds=901)
    assert result['native_read_errors']=={},result
    assert result['status']==expected_status,result
    assert result['healthy'] is (mode=='running_clock_window'),result
    assert result['auto_rescue_activity_verified'] is (mode=='running_clock_window'),result
    # Selection/header clocks may precede checkout. A re-proved Native repair
    # remains bounded by the original execution event and validation phase,
    # even after the earlier selection clock has crossed 900 seconds.
    assert result['scope_liveness']['claim']==('held' if mode=='running_clock_window' else 'expired'),result
    assert result['auto_rescue_activity_evidence']['reason']==expected_reason,result
    assert result['provider_progress_verified'] is False and result['progress_verified'] is False
    assert result['validation_activity_verified'] is False


@pytest.mark.parametrize('mode',['paused_clock_window','dead_clock_window'])
def test_expired_selection_cannot_borrow_paused_or_finished_rescue(tmp_path,mode):
    result=_status_in_owned_parent(tmp_path,mode,setup_seconds=51,selection_seconds=901)
    assert result['native_read_errors']=={},result
    assert result['status']=='stalled' and result['healthy'] is False,result
    assert result['scope_liveness']['claim']=='expired',result
    assert result['auto_rescue_activity_verified'] is False,result
    assert result['provider_progress_verified'] is False and result['progress_verified'] is False,result
    assert result['validation_activity_verified'] is False,result


@pytest.mark.parametrize("damage",["cid","key","attempt","workspace","phase","hold","deadline"])
def test_real_native_producer_cannot_cross_current_scope_or_deadline(tmp_path,monkeypatch,damage):
    from copy import deepcopy
    with _native_world(tmp_path,monkeypatch) as world:
        state=deepcopy(world["body"]); now=time.time()
        if damage=="cid":state["active_task_cid"]+="foreign"
        elif damage=="key":state["active_task_key"]+="foreign"
        elif damage=="attempt":state["active_attempt"]=2
        elif damage=="workspace":state["active_worktree_path"]=str(world["root"])
        elif damage=="phase":state["active_phase"]="implementing"
        elif damage=="hold":state["manual_hold"]=True
        else:
            primary = next(json.loads(line) for line in world["daemon"].events_path.read_text().splitlines()
                           if json.loads(line).get("type") == "implementation_started")
            now = runner._event_timestamp(primary) + runner.TIMEOUT_SECONDS + .01
        result=activity.observe(runner,world["root"],world["campaign"],state,now_ts=now)
        assert result["activity_verified"] is False and result["work_progress_verified"] is False
        assert result["reason"] in activity._REASONS


@pytest.mark.parametrize("kind", ["implementation_started", "implementation_finished"])
def test_later_start_or_terminal_cannot_renew_the_same_provider_window(tmp_path, monkeypatch, kind):
    with _native_world(tmp_path, monkeypatch, setup_seconds=51) as world:
        first = activity.observe(runner, world["root"], world["campaign"], world["body"], now_ts=time.time())
        assert first["activity_verified"] is True
        world["daemon"]._record_event(kind, {"task_id": world["task"].task_id, "attempt": 1,
            "worktree_path": str(world["workspace"]), "log_path": str(world["log"]),
            "execution_mode": "model-assisted"})
        refused = activity.observe(runner, world["root"], world["campaign"], world["body"], now_ts=time.time())
        assert refused["activity_verified"] is False and refused["work_progress_verified"] is False
        assert refused["reason"] in {"primary_start_unbound", "attempt_finished"}


def test_real_native_finished_provider_and_later_validation_output_are_not_rescue_activity(tmp_path,monkeypatch):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import supervisor_runtime as runtime
    with _native_world(tmp_path,monkeypatch) as world:
        (world["workspace"]/"release").touch();world["worker"].join(10)
        assert not world["worker"].is_alive()
        with world["log"].open("a") as output:
            runtime.run_process_group_stream([sys.executable,"-I","-B","-c",
                "print('{\"type\":\"tool_call\"}',flush=True)"],cwd=world["workspace"],stdout=output,
                env={},inherit_environment=False,timeout_seconds=10)
        result=activity.observe(runner,world["root"],world["campaign"],world["body"],now_ts=time.time())
        assert result["activity_verified"] is False


@pytest.mark.parametrize("kind",["available_commands","watchdog_heartbeat","validation_activity"])
def test_real_native_generic_or_validation_frames_cannot_renew_activity(tmp_path,monkeypatch,kind):
    with _native_world(tmp_path,monkeypatch,frame_kind=kind) as world:
        result=activity.observe(runner,world["root"],world["campaign"],world["body"],now_ts=time.time())
        assert result["activity_verified"] is False and result["work_progress_verified"] is False


def test_closed_summary_never_retains_arbitrary_private_fields_or_reason_text():
    value={"reason":"private-provider-text","activity_verified":"true","work_progress_verified":1,
        "argv":["private-token"],"text":"private-provider-text","log_path":"/private/path",
        "lease_id":"private-lease","frame_counts":{"thought":3,"private-provider-text":17},
        "owner_birth":{"pid":12,"start_time_ticks":13,"parent_pid":14,"argv":"private-token","boot_id":"private-token"}}
    closed=activity.summary(value)
    assert closed=={"reason":"rescue_observation_unavailable","activity_verified":False,"work_progress_verified":False,
        "owner_birth":{"pid":12,"start_time_ticks":13,"parent_pid":14},"frame_counts":{"thought":3}}
    assert "private" not in json.dumps(closed)
    assert activity.summary({"reason":[],"last_frame_kind":{}})["reason"]=="rescue_observation_unavailable"


@pytest.mark.parametrize('mode,reason',[('redirect_stdout','provider_stdout_unbound'),('different_cwd','provider_workspace_unbound')])
def test_real_native_child_must_keep_actual_stdout_and_workspace(tmp_path,monkeypatch,mode,reason):
    with _native_world(tmp_path,monkeypatch,frame_kind=mode) as world:
        result=activity.observe(runner,world['root'],world['campaign'],world['body'],now_ts=time.time())
        assert not result['activity_verified'] and result['reason']==reason,result


@pytest.mark.parametrize('which',['lease','claim'])
def test_real_current_native_claim_and_lease_are_reproved(tmp_path,monkeypatch,which):
    with _native_world(tmp_path,monkeypatch) as world:
        path=world[which+'_path'];original=path.read_bytes();document=json.loads(original)
        document['canonical_task_cid']='explicit-private-fixture-foreign-cid'
        try:
            path.write_text(json.dumps(document))
            result=activity.observe(runner,world['root'],world['campaign'],world['body'],now_ts=time.time())
            assert not result['activity_verified'] and not result['work_progress_verified']
        finally:path.write_bytes(original)


def test_real_birth_cannot_be_borrowed_by_an_older_provider_event(tmp_path,monkeypatch):
    with _native_world(tmp_path,monkeypatch) as world:
        result=activity.observe(runner,world['root'],world['campaign'],world['body'],now_ts=time.time())
        assert result['activity_verified'],result
        _,native,_=runner._validation_activity_modules()
        with pytest.raises(activity._Unavailable,match='provider_event_birth_unbound'):
            activity._provider_birth(native,result['provider_birth']['pid'],
                native.ProcessBirthIdentity.from_dict(result['owner_birth']),world['workspace'],
                (result['log_device'],result['log_inode']),result['rescue_started_at']-60)


@pytest.mark.parametrize('damage',['symlink','hardlink','replace','truncate','rewrite'])
def test_append_reader_rejects_alias_replacement_truncation_or_changed_prefix(tmp_path,monkeypatch,damage):
    path=tmp_path/'owned-live-log';path.write_bytes(b'{"type":"thought"}\n');path.chmod(0o600)
    other=tmp_path/'other'
    if damage=='symlink':path.rename(other);path.symlink_to(other)
    elif damage=='hardlink':os.link(path,other)
    else:
        actual=os.pread;changed=[]
        def read(descriptor,size,offset):
            data=actual(descriptor,size,offset)
            if not changed:
                changed.append(True)
                if damage=='replace':path.rename(other);path.write_bytes(data);path.chmod(0o600)
                elif damage=='truncate':path.write_bytes(b'x')
                else:
                    with path.open('r+b') as output:output.write(b'X')
            return data
        monkeypatch.setattr(activity.os,'pread',read)
    with pytest.raises((OSError,activity._Unavailable)):
        activity._append_prefix(path)
