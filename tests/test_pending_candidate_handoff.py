"""Host handoff protocol tests; SDK custody and Git materialization have separate real tests."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner
from integrations.ipfs_accelerate import pending_claim_runtime as runtime
from integrations.ipfs_accelerate import preserved_candidate_runtime as materializer

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


@pytest.fixture
def handoff(tmp_path, monkeypatch):
    root = tmp_path / "root"; root.mkdir()
    state = tmp_path / "state"; state.mkdir(mode=0o700)
    directory = state / "pending-task-claim-recoveries"; directory.mkdir(mode=0o700)
    proof = directory / ("candidate-" + "a" * 64 + ".json")
    proof.write_text('{"protocol_fixture_only":true}'); proof.chmod(0o600)
    body = {"implementation_attempts": {"CIMP-SYNTHETIC": 1}, "task_statuses": {"CIMP-SYNTHETIC": "ready"}}
    monkeypatch.setattr(runner, "_read_native_state", lambda *_: (deepcopy(body), {"source": "synthetic_protocol_unit"}))
    calls = {"review": 0, "reconcile": 0, "materialize": 0}
    request = {"schema": "synthetic_review_protocol", "base": {"repo_head": "b" * 40, "task_id": "CIMP-SYNTHETIC"}}
    candidate = {"preservation_receipt_path": str(proof), "task_id": "CIMP-SYNTHETIC"}
    result = {"reconciled": True, "blocked": False, "reason": "preserved_candidate_pending_task_claim_released",
              "counters_preserved": True, "task_status_unchanged": True,
              "preserved_candidate": candidate, "receipt_id": "sha256:" + "c" * 64,
              **{k: False for k in ("completion_authority", "attempt_refunded", "provider_callback_settled", "new_attempt_authority")}}
    def review(*_a, **_kw): calls["review"] += 1; return deepcopy(request)
    def reconcile(*_a, **_kw): calls["reconcile"] += 1; return deepcopy(result)
    def materialize(*_a, **kwargs):
        calls["materialize"] += 1
        assert kwargs == {"root_base": "b" * 40, "receipt_id": result["receipt_id"],
                          "receipt_sha256": runtime._sha(proof.read_bytes())}
        return {"native_admission_claimed": False, "completion_authority": False}
    module = SimpleNamespace(review_recovery=review, reconcile_recovery=reconcile,
        review=lambda *_a, **_kw: pytest.fail("legacy API used"),
        reconcile=lambda *_a, **_kw: pytest.fail("legacy API used"))
    binding = {"mode": "pinned_companion", "source": "synthetic_protocol_fixture"}
    monkeypatch.setattr(runtime, "load_runtime", lambda *_: (module, deepcopy(binding)))
    monkeypatch.setattr(materializer, "materialize", materialize)
    daemon = SimpleNamespace(state_path=state / "synthetic.json")
    def run(): return runtime.reconcile_pending_claim(root, root / "spec.json", state, {}, None, daemon, "CIMP-SYNTHETIC")
    return SimpleNamespace(root=root, state=state, proof=proof, body=body, calls=calls, request=request,
        result=result, module=module, binding=binding, run=run)


def test_sdk_handoff_uses_additive_api_and_retains_false_authority(handoff):
    result = handoff.run()
    assert result["completion_authority"] is False
    assert result["candidate_materialization"]["native_admission_claimed"] is False
    assert handoff.calls == {"review": 1, "reconcile": 1, "materialize": 1}
    assert runtime.unfinished_handoff_task(handoff.state) is None
    assert handoff.body["implementation_attempts"] == {"CIMP-SYNTHETIC": 1}


def test_crash_after_sdk_release_replays_original_review(handoff, monkeypatch):
    write = runtime._handoff_write; crashed = False
    def crash_once(path, value):
        nonlocal crashed
        if value["phase"] == "preserved" and not crashed:
            crashed = True
            raise OSError("synthetic host interruption after SDK result")
        return write(path, value)
    monkeypatch.setattr(runtime, "_handoff_write", crash_once)
    with pytest.raises(OSError): handoff.run()
    assert runtime.unfinished_handoff_task(handoff.state) == "CIMP-SYNTHETIC"
    assert handoff.run()["reconciled"] is True
    assert handoff.calls == {"review": 1, "reconcile": 2, "materialize": 1}


def test_crash_during_materialization_does_not_repeat_sdk_mutation(handoff, monkeypatch):
    real = materializer.materialize; seen = 0
    def crash_once(*args, **kwargs):
        nonlocal seen
        seen += 1
        if seen == 1: raise OSError("synthetic materialization interruption")
        return real(*args, **kwargs)
    monkeypatch.setattr(materializer, "materialize", crash_once)
    with pytest.raises(OSError): handoff.run()
    assert runtime.unfinished_handoff_task(handoff.state) == "CIMP-SYNTHETIC"
    assert handoff.run()["reconciled"] is True
    assert handoff.calls == {"review": 2, "reconcile": 1, "materialize": 1}


@pytest.mark.parametrize("change", ["binding", "state", "journal"])
def test_changed_handoff_authority_refuses_before_sdk_or_materializer(handoff, monkeypatch, change):
    monkeypatch.setattr(materializer, "materialize", lambda *_a, **_kw: (_ for _ in ()).throw(OSError("pause")))
    with pytest.raises(OSError): handoff.run()
    if change == "binding": handoff.binding["source"] = "changed"
    elif change == "state": handoff.body["implementation_attempts"]["CIMP-SYNTHETIC"] = 2
    else:
        path = runtime._handoff_path(handoff.state, "CIMP-SYNTHETIC")
        value = json.loads(path.read_text()); value["request"]["base"]["repo_head"] = "d" * 40
        path.write_text(json.dumps(value))
    with pytest.raises(ValueError): handoff.run()
    assert handoff.calls["review"] == handoff.calls["reconcile"] == 1


def test_preserved_receipt_sha_is_pinned_across_materializer_retry(handoff, monkeypatch):
    seen = []
    def unavailable(*_a, **kwargs):
        seen.append(kwargs["receipt_sha256"])
        raise ValueError("synthetic receipt checker refuses changed bytes")
    monkeypatch.setattr(materializer, "materialize", unavailable)
    with pytest.raises(ValueError): handoff.run()
    handoff.proof.write_text('{"protocol_fixture_only":"changed"}')
    with pytest.raises(ValueError): handoff.run()
    assert seen[0] == seen[1] != runtime._sha(handoff.proof.read_bytes())
    assert handoff.calls["reconcile"] == 1


def test_receipt_outside_sdk_recovery_directory_is_never_read(handoff):
    handoff.result["preserved_candidate"]["preservation_receipt_path"] = str(handoff.state / "runner-home" / "profile.json")
    with pytest.raises(ValueError, match="receipt_scope"): handoff.run()
    assert handoff.calls["materialize"] == 0


@pytest.mark.parametrize("change", ["request", "candidate"])
def test_self_consistent_handoff_cannot_transfer_another_task(handoff, monkeypatch, change):
    monkeypatch.setattr(materializer, "materialize", lambda *_a, **_kw: (_ for _ in ()).throw(OSError("pause")))
    with pytest.raises(OSError): handoff.run()
    path = runtime._handoff_path(handoff.state, "CIMP-SYNTHETIC")
    value = runtime._handoff_read(path)
    if change == "request": value["request"]["base"]["task_id"] = "CIMP-FOREIGN"
    else: value["result"]["preserved_candidate"]["task_id"] = "CIMP-FOREIGN"
    runtime._handoff_write(path, value)  # Re-sign the fixture: digest validity alone is insufficient.
    with pytest.raises(ValueError): handoff.run()
    assert handoff.calls["reconcile"] == 1


def test_sdk_review_cannot_prepare_a_different_task(handoff):
    handoff.request["base"]["task_id"] = "CIMP-FOREIGN"
    with pytest.raises(ValueError, match="request_task_changed"): handoff.run()
    assert handoff.calls["reconcile"] == handoff.calls["materialize"] == 0
    assert runtime.unfinished_handoff_task(handoff.state) is None


def test_preserved_replay_reproves_native_custody_without_repeating_release(handoff, monkeypatch):
    monkeypatch.setattr(materializer, "materialize", lambda *_a, **_kw: (_ for _ in ()).throw(OSError("pause")))
    with pytest.raises(OSError): handoff.run()
    def refused(*_a, **_kw):
        raise ValueError("synthetic renewed claim or changed strategy")
    handoff.module.review_recovery = refused
    with pytest.raises(ValueError, match="renewed claim"): handoff.run()
    assert handoff.calls["reconcile"] == 1
    assert runtime.unfinished_handoff_task(handoff.state) == "CIMP-SYNTHETIC"


@pytest.mark.parametrize("sdk_reason,expected", [
    ("native_preservation_event_required", "pending_claim_sdk_blocked_native_preservation_event_required"),
    ("unsafe/path?secret=private", "pending_claim_runtime_reconciliation_unverified"),
])
def test_blocked_sdk_reason_is_visible_only_as_a_closed_identifier(handoff, sdk_reason, expected):
    handoff.result.update(reconciled=False, blocked=True, reason=sdk_reason)
    with pytest.raises(ValueError) as caught:
        handoff.run()
    assert str(caught.value) == expected
    assert handoff.calls == {"review": 1, "reconcile": 1, "materialize": 0}
    assert runtime.unfinished_handoff_task(handoff.state) == "CIMP-SYNTHETIC"


def test_sdk_refusal_cannot_conceal_changed_native_state(handoff):
    handoff.result.update(reconciled=False, blocked=True, reason="native_preservation_event_required")
    original = handoff.module.reconcile_recovery
    def changes_state(*args, **kwargs):
        handoff.body["implementation_attempts"]["CIMP-SYNTHETIC"] = 2
        return original(*args, **kwargs)
    handoff.module.reconcile_recovery = changes_state
    with pytest.raises(ValueError, match="pending_claim_runtime_native_state_changed"):
        handoff.run()
    assert handoff.calls["materialize"] == 0
