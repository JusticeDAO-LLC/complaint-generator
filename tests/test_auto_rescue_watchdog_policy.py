"""Host policy doubles carry a separately real Native provider observation.

The Host adapter itself remains an explicitly synthetic unit fixture. It
does not claim public launcher/Docker/start qualification or perform effects.
"""
from copy import deepcopy
import json
from types import SimpleNamespace
import time

import pytest

from integrations.ipfs_accelerate import auto_rescue_activity as activity
from integrations.ipfs_accelerate import improvement_runner as runner
from tests.test_campaign_watchdog import _adapter
from tests.test_owned_auto_rescue_activity import _native_world

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _carrier(tmp_path,monkeypatch,evidence,body):
    tmp_path.mkdir()
    watcher, fake, view=_adapter(tmp_path,monkeypatch,state="active")
    watcher.clock=time.time
    view.update(status="active",healthy=True,owned_process_alive=True,worker_liveness="alive",
        auto_rescue_activity_verified=True,auto_rescue_activity_evidence=deepcopy(evidence),
        provider_progress_verified=False,validation_activity_verified=False,
        provider_execution_evidence={"frame_counts":{},"log_bytes":evidence["log_bytes"]})
    view["native_state"]=deepcopy(body)
    fake._native_modules=lambda *_:(None,SimpleNamespace(parse_task_file=lambda *a,**kw:[
        SimpleNamespace(task_id=body["active_task_id"],status="todo")]))
    monkeypatch.setattr(watcher,"recover",lambda *_:pytest.fail("An activity-only observation dispatched recovery."))
    return watcher,view


def test_real_native_thought_is_passive_without_reading_or_changing_recovery_budget(tmp_path,monkeypatch):
    from ipfs_accelerate_py.agent_supervisor.rescue import campaign_watchdog as sdk
    with _native_world(tmp_path/"native",monkeypatch) as world:
        evidence=activity.observe(runner,world["root"],world["campaign"],world["body"],now_ts=time.time())
        assert evidence["activity_verified"] is True,evidence
        watcher,view=_carrier(tmp_path/"host",monkeypatch,evidence,world["body"])
        watcher.directory.mkdir(mode=0o700)
        ledger=watcher.directory/"campaign-progress-watchdog.json"
        original=b'{"explicit_synthetic_preexisting_finite_budget":2}\n'
        ledger.write_bytes(original);ledger.chmod(0o600)
        monkeypatch.setattr(sdk.CampaignProgressWatchdog,"run_once",lambda *_:pytest.fail("Activity-only path entered SDK policy."))
        result=watcher.run_once()
        assert result["status"]=="healthy" and result["reason"]=="bounded_native_rescue_activity"
        assert result["progress_verified"] is False
        assert result["provider_calls_by_watchdog"]==0 and result["attempt_refunded"] is False
        assert ledger.read_bytes()==original
        assert result["activity_evidence"]["auto_rescue"]["work_progress_verified"] is False


@pytest.mark.parametrize("damage",["expired","refused","hold","different_task","work_progress","not_owned","dead_worker"])
def test_activity_override_refusal_returns_to_unchanged_sdk_policy(tmp_path,monkeypatch,damage):
    from ipfs_accelerate_py.agent_supervisor.rescue import campaign_watchdog as sdk
    # Policy-only payloads are explicit doubles; the real producer positive
    # above separately proves that production can supply the required shape.
    evidence={"activity_verified":True,"work_progress_verified":False,"reason":"bounded_native_rescue_activity",
        "task_id":"TASK-1","task_cid":"bafy-explicit-synthetic-policy","deadline_at":time.time()+30,"log_bytes":1}
    body={"active_task_id":"TASK-1","active_task_cid":evidence["task_cid"],"active_attempt":1,"active_phase":"validating"}
    watcher,view=_carrier(tmp_path/"host",monkeypatch,evidence,body)
    if damage=="expired":view["auto_rescue_activity_evidence"]["deadline_at"]=time.time()-1
    elif damage=="refused":view["auto_rescue_activity_verified"]=False
    elif damage=="hold":view["native_state"]["manual_hold"]=True
    elif damage=="different_task":view["auto_rescue_activity_evidence"]["task_id"]="other-task"
    elif damage=="work_progress":
        view["provider_progress_verified"]=True
        view["auto_rescue_activity_evidence"]["work_progress_verified"]=True
    elif damage=="not_owned":view["owned_process_alive"]=False
    else:view["worker_liveness"]="dead"
    real=sdk.CampaignProgressWatchdog.run_once;calls=[]
    def run_once(instance):
        calls.append(True)
        return real(instance)
    monkeypatch.setattr(sdk.CampaignProgressWatchdog,"run_once",run_once)
    result=watcher.run_once()
    assert calls==[True]
    assert result["reason"]!="bounded_native_rescue_activity"
    assert result["provider_calls_by_watchdog"]==0


def test_closed_watchdog_report_omits_freeform_provider_fields(tmp_path,monkeypatch):
    watcher,_,view=_adapter(tmp_path,monkeypatch,state="stalled",hold=True)
    view["auto_rescue_activity_evidence"]={"reason":"secret-freeform-provider-output","argv":["secret-argv"],
        "text":"secret-text","log_path":"/secret/path","lease_id":"secret-lease"}
    result=watcher.run_once()
    assert result["status"]=="held"
    encoded=json.dumps(result["activity_evidence"])
    assert "secret" not in encoded and "argv" not in encoded and "log_path" not in encoded
