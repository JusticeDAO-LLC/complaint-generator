"""Unit precedence controls; actual Native execution stays covered unchanged by58.

These explicit metadata/process seams test classification only and grant no
completion, ownership, provider, or recovery authority.
"""
from datetime import datetime, timezone
import json
import os
import time

import pytest
from tests.test_improvement_runner import campaign, _status_fixture, _identity
from integrations.ipfs_accelerate import improvement_runner as runner

pytestmark=[pytest.mark.no_auto_llm,pytest.mark.no_auto_network,pytest.mark.no_auto_heavy]
COMPLETE={'count':2,'completed':2,'ready_task_ids':[],'manual_hold_task_ids':[]}


@pytest.mark.parametrize('field,value',[
    ('implementation_in_progress',True),('active_task_id','CIMP-TUI-01'),
    ('active_task_cid','synthetic-current-cid'),('active_provider_runner',{'pid':991121}),
    ('active_phase','validating'),('active_worktree_path','synthetic/current-worktree')])
@pytest.mark.parametrize('fresh',[True,False])
def test_completed_markdown_never_masks_raw_native_activity(campaign,monkeypatch,field,value,fresh):
    root,spec,state,_=_status_fixture(campaign,monkeypatch,native_state={field:value},board=COMPLETE)
    if not fresh:
        path=state/f'{runner.STATE_PREFIX}_task_state.json'
        old=time.time()-500
        os.utime(path,(old,old))
    result=runner.status(root,spec,state)
    assert result['status']!='complete',(field,fresh,result)
    assert result['completion_authority'] is False


@pytest.mark.parametrize('damage,expected',[('identity','heartbeat_identity_mismatch'),('age','stalled')])
def test_completed_quiescent_board_keeps_heartbeat_failure_precedence(campaign,monkeypatch,damage,expected):
    root,spec,state,_=_status_fixture(campaign,monkeypatch,native_state={'implementation_in_progress':False},board=COMPLETE)
    heartbeat=state/f'{runner.STATE_PREFIX}_supervisor_status.json'
    if damage=='identity':
        body=json.loads(heartbeat.read_text());body['supervisor_pid']=991122
        runner._atomic_json(heartbeat,body)
    else:
        record=runner._read_json(state/'launcher.json');record['started_at']=time.time()-300
        runner._atomic_json(state/'launcher.json',record)
        old=time.time()-121;os.utime(heartbeat,(old,old))
    result=runner.status(root,spec,state)
    assert result['status']==expected and result['healthy'] is False


def test_genuine_quiescent_metadata_can_report_complete_without_clearing_row_owner(campaign,monkeypatch):
    # The real Native clear-active API retains lane owner/historical fields.
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    state=native.PortalTaskState()
    state.owner_process_birth=_identity(pid=991120)
    state.last_implementation_started_at=datetime.now(timezone.utc).isoformat()
    native.PortalImplementationDaemon._clear_active_execution_state(None,state,clear_task=True)
    root,spec,path,_=_status_fixture(campaign,monkeypatch,native_state=vars(state),board=COMPLETE)
    result=runner.status(root,spec,path)
    assert result['status']=='complete' and result['healthy'] is True
    assert result['completion_authority'] is False
