"""Scoped watchdog recovery reaps only the owned tree inside current deadlines."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

import pytest

from integrations.ipfs_accelerate import campaign_watchdog as watchdog
from integrations.ipfs_accelerate import improvement_runner as runner


pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

_SLEEP = (
    "import time,sys\n"
    "sys.stdout.write(sys.argv[1] if len(sys.argv)>1 else '')\n"
    "sys.stdout.flush()\n"
    "time.sleep(120)\n"
)


def _alive(pid):
    identity = runner.process_identity(pid)
    return identity is not None


def _spawn(argv, *, new_session):
    return subprocess.Popen(
        argv, start_new_session=new_session, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _tree(scope):
    """Owner, nested owned child and grandchild, plus one nested foreign validator."""
    foreign_scope = scope + "-foreign"
    child = (
        "import subprocess,sys,time\n"
        "scope,foreign,py=sys.argv[1],sys.argv[2],sys.executable\n"
        "sleep=%r\n"
        "subprocess.Popen([py,'-c',sleep,'owned-grandchild','--watchdog-scope',scope])\n"
        "subprocess.Popen([py,'-c',sleep,'foreign-validator','--watchdog-scope',foreign])\n"
        "time.sleep(120)\n"
    ) % _SLEEP
    owner = _spawn([
        sys.executable, "-c",
        "import subprocess,sys,time\n"
        "scope,foreign,py=sys.argv[1],sys.argv[2],sys.executable\n"
        "child=%r\n"
        "subprocess.Popen([py,'-c',child,scope,foreign])\n"
        "time.sleep(120)\n" % child,
        scope, foreign_scope,
    ], new_session=True)
    outside = _spawn([
        sys.executable, "-c", _SLEEP, "foreign-validator", "--watchdog-scope", foreign_scope,
    ], new_session=True)
    deadline = time.time() + 5
    nested = []
    while time.time() < deadline and len(nested) < 3:
        found = []
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            identity = runner.process_identity(int(entry))
            if not identity or identity.get("session") != owner.pid or identity["pid"] == owner.pid:
                continue
            found.append(identity)
        nested = found
        if len(nested) >= 3:
            break
        time.sleep(0.05)
    roles = {}
    for identity in nested:
        argv = identity.get("argv") or []
        if "foreign-validator" in argv:
            roles["nested_foreign"] = identity
        elif "owned-grandchild" in argv:
            roles["grandchild"] = identity
        elif "--watchdog-scope" not in argv:
            roles["child"] = identity
    if set(roles) != {"child", "grandchild", "nested_foreign"} or not _alive(outside.pid):
        _cleanup(owner, outside, nested)
        raise AssertionError("owned tree or foreign validator was not born")
    owner_identity = runner.process_identity(owner.pid)
    return {
        "owner": owner, "outside": outside, "owner_identity": owner_identity,
        "descendants": nested, "roles": roles, "scope": scope,
    }


def _cleanup(owner, outside, descendants):
    pids = []
    if owner is not None and owner.poll() is None:
        pids.append(owner.pid)
    if outside is not None and outside.poll() is None:
        pids.append(outside.pid)
    for identity in descendants or []:
        if _alive(identity["pid"]):
            pids.append(identity["pid"])
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if owner is not None:
        owner.wait(timeout=2)
    if outside is not None:
        outside.wait(timeout=2)


def _qualify(tree, **overrides):
    phase_started = overrides.pop("phase_started", 1_000.0)
    arguments = {
        "kind": "development_worker_stall",
        "owner_identity": tree["owner_identity"],
        "scope_token": tree["scope"],
        "phase_started_at": phase_started,
        "now": phase_started + 180,
        "descendant_identities": tree["descendants"],
        "attempt": 2,
        "turns": 4,
        "recovery_actions": 0,
        "ledger": {"implementation_attempts": {"CIMP-UX-66": 2}, "uncertain": False},
    }
    arguments.update(overrides)
    return watchdog.qualify_scoped_owned_recovery(**arguments)


def test_budgets_stay_at_the_existing_native_ceilings():
    budgets = watchdog.preserved_native_watchdog_budgets(runner)
    assert runner.STARTUP_SECONDS == 90
    assert runner.STALL_SECONDS == 180
    assert runner.TIMEOUT_SECONDS == 900
    assert budgets == {
        "startup_seconds": 90,
        "stall_seconds": 180,
        "implementation_timeout_seconds": 900,
        "watchdog_action_deadline_ms": 1_200_000,
        "max_recoveries_per_incident": 2,
    }
    assert watchdog._ATTEMPT_CAP == 3 and watchdog._TURN_CAP == 64


def test_stall_reaps_nested_owned_children_and_spares_foreign_validators():
    tree = _tree("ux66-stall")
    ledger = {"implementation_attempts": {"CIMP-UX-66": 2}, "holds": ["historical"]}
    try:
        result = _qualify(tree, ledger=ledger)
        assert result["status"] == "recovered"
        assert result["reason"] == "development_worker_stall"
        assert result["recovery_actions"] == 1
        assert result["attempt"] == 2 and result["turns"] == 4
        assert result["attempt_refunded"] is False
        assert result["phase_deadline"] == 1_000.0 + 900
        assert result["foreign_validator_adopted"] is False
        reaped = set(result["reaped_pids"])
        assert tree["owner"].pid in reaped
        assert tree["roles"]["child"]["pid"] in reaped
        assert tree["roles"]["grandchild"]["pid"] in reaped
        assert tree["roles"]["nested_foreign"]["pid"] not in reaped
        assert tree["outside"].pid not in reaped
        assert not _alive(tree["owner"].pid)
        assert not _alive(tree["roles"]["grandchild"]["pid"])
        assert _alive(tree["roles"]["nested_foreign"]["pid"])
        assert _alive(tree["outside"].pid)
        assert ledger == {"implementation_attempts": {"CIMP-UX-66": 2}, "holds": ["historical"]}
    finally:
        _cleanup(tree["owner"], tree["outside"], tree["descendants"])


def test_idle_validation_and_owner_death_use_the_current_phase_deadline():
    phase = 5_000.0
    idle = _tree("ux66-idle")
    try:
        early = _qualify(idle, kind="idle_ready", attempt=0, turns=0, phase_started=phase, now=phase + 89)
        assert early["status"] == "refused" and early["reason"] == "within_grace_or_stall"
        assert _alive(idle["owner"].pid) and _alive(idle["roles"]["grandchild"]["pid"])
        ready = _qualify(idle, kind="idle_ready", attempt=0, turns=0, phase_started=phase, now=phase + 180,
                         descendant_identities=idle["descendants"])
        assert ready["status"] == "recovered" and ready["stall_until"] == phase + 180
        assert not _alive(idle["roles"]["child"]["pid"])
        assert _alive(idle["roles"]["nested_foreign"]["pid"])
    finally:
        _cleanup(idle["owner"], idle["outside"], idle["descendants"])

    validation = _tree("ux66-validation")
    try:
        scope = {"campaign": "ux66", "task": "CIMP-UX-66", "attempt": 1}
        refused = _qualify(
            validation, kind="validation_activity", phase_started=phase, now=phase + 30,
            validation_scope={"campaign": "other"}, active_scope=scope, claimed_deadline=phase + 900)
        assert refused["status"] == "refused" and refused["reason"] == "foreign_validator_contamination"
        assert refused["phase_deadline"] == phase + 900
        assert _alive(validation["owner"].pid)
        stale = _qualify(
            validation, kind="validation_activity", phase_started=phase, now=phase + 30,
            validation_scope=scope, active_scope=scope, claimed_deadline=phase + 5000)
        assert stale["reason"] == "stale_phase_deadline" and _alive(validation["roles"]["grandchild"]["pid"])
        current = _qualify(
            validation, kind="validation_activity", phase_started=phase, now=phase + 30,
            validation_scope=scope, active_scope=scope, claimed_deadline=phase + 900)
        assert current["status"] == "recovered"
        assert current["phase_deadline"] == phase + 900
        assert not _alive(validation["owner"].pid)
        assert _alive(validation["roles"]["nested_foreign"]["pid"])
        assert _alive(validation["outside"].pid)
    finally:
        _cleanup(validation["owner"], validation["outside"], validation["descendants"])

    death = _tree("ux66-owner-death")
    try:
        os.kill(death["owner"].pid, signal.SIGKILL)
        death["owner"].wait(timeout=2)
        assert not _alive(death["owner"].pid)
        assert _alive(death["roles"]["grandchild"]["pid"])
        expired = _qualify(death, kind="owner_death", phase_started=phase, now=phase + 900)
        assert expired["reason"] == "phase_deadline_expired"
        assert _alive(death["roles"]["grandchild"]["pid"])
        recovered = _qualify(death, kind="owner_death", phase_started=phase, now=phase + 10)
        assert recovered["status"] == "recovered" and recovered["reason"] == "owner_death"
        assert death["roles"]["grandchild"]["pid"] in recovered["reaped_pids"]
        assert death["roles"]["nested_foreign"]["pid"] in recovered["spared_pids"]
        assert not _alive(death["roles"]["child"]["pid"])
        assert _alive(death["roles"]["nested_foreign"]["pid"])
        assert _alive(death["outside"].pid)
    finally:
        _cleanup(death["owner"], death["outside"], death["descendants"])


@pytest.mark.parametrize("overrides,reason", [
    ({"awaiting_user": True, "attempt": 0, "turns": 0}, "awaiting_user"),
    ({"hold": "manual_hold"}, "hold_preserved"),
    ({"hold": "paused"}, "hold_preserved"),
    ({"ledger_uncertain": True}, "uncertain_ledger"),
    ({"attempt": 4}, "attempt_or_turn_cap"),
    ({"turns": 65}, "attempt_or_turn_cap"),
    ({"recovery_actions": 2}, "recovery_actions_exhausted"),
])
def test_holds_uncertain_ledgers_and_caps_do_not_reap(overrides, reason):
    tree = _tree("ux66-" + reason)
    ledger = {"implementation_attempts": {"CIMP-UX-66": 3}, "state": "uncertain"}
    try:
        result = _qualify(tree, ledger=ledger, **overrides)
        assert result["status"] in {"preserved", "refused"}
        assert result["reason"] == reason
        assert result["reaped_pids"] == []
        assert result["recovery_actions"] == overrides.get("recovery_actions", 0)
        assert ledger["state"] == "uncertain"
        assert _alive(tree["owner"].pid)
        assert _alive(tree["roles"]["child"]["pid"])
        assert _alive(tree["roles"]["grandchild"]["pid"])
        assert _alive(tree["roles"]["nested_foreign"]["pid"])
        assert _alive(tree["outside"].pid)
    finally:
        _cleanup(tree["owner"], tree["outside"], tree["descendants"])


def test_second_recovery_is_allowed_and_a_third_action_is_not():
    first = _tree("ux66-action-1")
    try:
        once = _qualify(first, recovery_actions=0)
        assert once["status"] == "recovered" and once["recovery_actions"] == 1
        assert once["max_recoveries_per_incident"] == 2
    finally:
        _cleanup(first["owner"], first["outside"], first["descendants"])
    second = _tree("ux66-action-2")
    try:
        twice = _qualify(second, recovery_actions=1)
        assert twice["status"] == "recovered" and twice["recovery_actions"] == 2
        assert not _alive(second["roles"]["grandchild"]["pid"])
        assert _alive(second["outside"].pid)
    finally:
        _cleanup(second["owner"], second["outside"], second["descendants"])
