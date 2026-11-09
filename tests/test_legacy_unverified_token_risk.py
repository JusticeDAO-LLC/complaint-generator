"""Reproduce, do not repair, the legacy token/budget risk in actual SDK policy.

Ownership observation is supplied by the real inert Native fixture. The Host
carrier, clock and recovery callbacks are explicitly synthetic policy doubles.
No live ledger, task counter or provider is used or edited.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time

import pytest

from integrations.ipfs_accelerate import auto_rescue_activity as activity
from integrations.ipfs_accelerate import improvement_runner as runner
from tests.test_auto_rescue_watchdog_policy import _carrier
from tests.test_owned_auto_rescue_activity import _native_world

pytestmark=[pytest.mark.no_auto_llm,pytest.mark.no_auto_network,pytest.mark.no_auto_heavy]


def test_actual_sdk_legacy_unverified_bytes_can_open_new_budget_after_activity(tmp_path,monkeypatch):
    from ipfs_accelerate_py.agent_supervisor.rescue import campaign_watchdog as sdk
    from ipfs_accelerate_py.agent_supervisor.rescue.supervisor_recovery import RecoveryActionObservation
    with _native_world(tmp_path/'native',monkeypatch) as world:
        evidence=activity.observe(runner,world['root'],world['campaign'],world['body'],now_ts=time.time())
        assert evidence['activity_verified'] and not evidence['work_progress_verified'],evidence
        watcher,view=_carrier(tmp_path/'host',monkeypatch,evidence,world['body'])
        now=[time.time()];watcher.clock=lambda:now[0]
        real=sdk.CampaignProgressWatchdog
        monkeypatch.setattr(sdk,'CampaignProgressWatchdog',lambda *a,**kw:real(*a,**kw,clock_ms=lambda:int(now[0]*1000)))
        calls=[]
        def recovery(_context):
            calls.append(True)
            return RecoveryActionObservation(False,(),{'healthy':False},reason='synthetic_proven_no_effect',partial=False)
        monkeypatch.setattr(watcher,'recover',recovery)
        view.update(status='stalled',healthy=False,auto_rescue_activity_verified=False)
        view['provider_execution_evidence']={'frame_counts':{'usage':1},'log_bytes':100,'provider_terminal_observed':False}
        for _ in range(2):
            assert watcher.run_once()['status']=='confirming'
            now[0]+=31
            watcher.run_once()
            now[0]+=61
        exhausted=watcher.run_once()
        assert exhausted['status']=='exhausted' and len(calls)==2,exhausted
        ledger=watcher.directory/'campaign-progress-watchdog.json'
        original=ledger.read_bytes();old=json.loads(original)
        assert len(old['incidents'])==1 and next(iter(old['incidents'].values()))['attempts']==2
        # Only thought bytes change; tool/usage counts and the task/attempt do
        # not. The passive path must not call the SDK or touch its ledger.
        view.update(status='active',healthy=True,auto_rescue_activity_verified=True,
            auto_rescue_activity_evidence=deepcopy(evidence))
        view['provider_execution_evidence']['log_bytes']=evidence['log_bytes']
        thought=watcher.run_once()
        assert thought['reason']=='bounded_native_rescue_activity' and not thought['progress_verified']
        assert ledger.read_bytes()==original and len(calls)==2
        view.update(status='stalled',healthy=False,auto_rescue_activity_verified=False)
        later=watcher.run_once()
        assert later['status']=='confirming',later
        now[0]+=31
        watcher.run_once()
        after=json.loads(ledger.read_text())
        assert len(calls)==3 and len(after['incidents'])==2
        assert sorted(row['attempts'] for row in after['incidents'].values())==[1,2]
        report={'schema':'legacy-unverified-progress-token-risk-reproduction@1','synthetic_policy_fixture':True,
            'native_ownership_fixture':'actual6af_claims_events_inert_rescue_Popen',
            'model_calls':0,'live_effects':False,'manual_ledger_edits':False,
            'same_task_attempt':True,'same_work_frame_counts':True,'only_unverified_log_bytes_changed':True,
            'activity_ledger_bytes_unchanged':True,'old_incident_attempts':2,'later_total_inert_callbacks':len(calls),
            'later_incident_attempts':sorted(row['attempts'] for row in after['incidents'].values()),
            'risk_reproduced':True,'sdk_source':str(Path(sdk.__file__).resolve()),
            'sdk_source_sha256':hashlib.sha256(Path(sdk.__file__).read_bytes()).hexdigest(),
            'before_ledger_sha256':hashlib.sha256(original).hexdigest(),
            'after_ledger_sha256':hashlib.sha256(ledger.read_bytes()).hexdigest()}
        (tmp_path/'legacy-token-risk.json').write_text(json.dumps(report,indent=2)+'\n')
