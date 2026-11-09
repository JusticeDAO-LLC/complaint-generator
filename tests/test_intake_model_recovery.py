"""Synthetic interview recovery for provider outages and schema drift.

Offline cases inject faults into the pinned Grok route. They do not open
sockets, start a provider process, or treat an optional canary as a live pass.
"""

from __future__ import annotations

import threading
import uuid

import pytest

from integrations.ipfs_accelerate.routers import PINNED_GROK_MODEL, PINNED_GROK_PROVIDER
from integrations.ipfs_datasets.llm import (
    RECOVERY_BACKOFF_CAP_S,
    RECOVERY_MAX_ATTEMPTS,
    intake_recovery_idempotency_key,
    qualify_intake_model_recovery,
)


def _state() -> dict:
    return {
        "facts": [{"field": "party", "value": "Ada"}],
        "questions": [{"question_id": "q1", "target_ref": "party.complainant"}],
        "revision": 3,
    }


def _run(script, **kwargs):
    state = kwargs.pop("state", None)
    if state is None:
        state = _state()
    before = {
        "facts": [dict(item) for item in state["facts"]],
        "questions": [dict(item) for item in state["questions"]],
        "revision": state["revision"],
    }
    calls = []

    def transport(**payload):
        calls.append(dict(payload))

    sleeper = kwargs.pop("sleeper", lambda delay: None)
    receipt = qualify_intake_model_recovery(
        state,
        provider=kwargs.pop("provider", PINNED_GROK_PROVIDER),
        model_name=kwargs.pop("model_name", PINNED_GROK_MODEL),
        request_id=kwargs.pop("request_id", uuid.uuid4().hex),
        script=script,
        transport=kwargs.pop("transport", transport),
        sleeper=sleeper,
        **kwargs,
    )
    return receipt, state, before, calls


@pytest.mark.parametrize(
    ("script", "disposition", "attempts"),
    [
        (["auth_failure"], "auth_failure", 0),
        (["quota"], "quota", 1),
        (["rate_limit"], "rate_limit", 1),
        (["malformed"], "malformed", 1),
        (["schema_drift"], "schema_drift", 1),
        (["delayed"], "delayed", 1),
        (["disconnect"], "disconnect", 1),
        (["cancelled"], "cancelled", 1),
    ],
)
def test_each_injection_preserves_state_and_reports_exact_disposition(script, disposition, attempts):
    receipt, state, before, calls = _run(script)
    assert receipt["disposition"] == disposition
    assert receipt["failure_kind"] == disposition
    assert receipt["attempts"] == attempts
    assert receipt["state_preserved"] is True
    assert receipt["offline_unit_complete"] is True
    assert receipt["live_canary"] is False
    assert state == before
    assert receipt["interview_state"] == before
    assert len(calls) == attempts
    if attempts:
        assert calls[0]["injection"] == disposition
        assert receipt["idempotency_keys"] == [receipt["idempotency_key"]] * attempts
    else:
        assert calls == []
        assert receipt["dispatch"] == "none"


def test_transient_faults_retry_with_capped_backoff_and_one_idempotency_key():
    request_id = uuid.uuid4().hex
    sleeps = []
    receipt, state, before, calls = _run(
        ["disconnect", "rate_limit", "available", "disconnect"],
        request_id=request_id,
        sleeper=sleeps.append,
    )
    assert receipt["disposition"] == "available"
    assert receipt["attempts"] == RECOVERY_MAX_ATTEMPTS
    assert len(calls) == RECOVERY_MAX_ATTEMPTS
    assert [item["injection"] for item in calls] == ["disconnect", "rate_limit", "available"]
    assert {item["idempotency_key"] for item in calls} == {intake_recovery_idempotency_key(request_id)}
    assert receipt["idempotency_key"] == intake_recovery_idempotency_key(request_id)
    assert sleeps
    assert all(0 < delay <= RECOVERY_BACKOFF_CAP_S for delay in sleeps)
    assert sleeps == [RECOVERY_BACKOFF_CAP_S, RECOVERY_BACKOFF_CAP_S]
    assert state == before
    exhausted, exhausted_state, exhausted_before, exhausted_calls = _run(
        ["disconnect", "disconnect", "disconnect", "available"],
        sleeper=sleeps.append,
    )
    assert exhausted["disposition"] == "disconnect"
    assert exhausted["attempts"] == RECOVERY_MAX_ATTEMPTS
    assert len(exhausted_calls) == RECOVERY_MAX_ATTEMPTS
    assert exhausted_state == exhausted_before


@pytest.mark.parametrize(
    "script",
    [
        ["auth_failure", "available"],
        ["quota", "available"],
        ["malformed", "available"],
        ["schema_drift", "available"],
        ["cancelled", "available"],
    ],
)
def test_terminal_faults_do_not_retry(script):
    receipt, state, before, calls = _run(script, sleeper=lambda delay: (_ for _ in ()).throw(AssertionError("backoff")))
    assert receipt["disposition"] == script[0]
    assert receipt["backoff_seconds"] == []
    assert len(calls) == (0 if script[0] == "auth_failure" else 1)
    assert state == before


@pytest.mark.parametrize(
    ("provider", "model", "disposition"),
    [
        (PINNED_GROK_PROVIDER, "grok-4", "wrong_model"),
        (PINNED_GROK_PROVIDER, "grok-4.7-build", "wrong_model"),
        ("openai", PINNED_GROK_MODEL, "wrong_provider"),
        ("xai", "grok-4", "wrong_provider"),
        ("", "", "wrong_provider"),
    ],
)
def test_wrong_model_or_provider_is_rejected_before_transport(provider, model, disposition):
    def transport(**_payload):
        raise AssertionError("transport")

    receipt, state, before, calls = _run([ "available" ], provider=provider, model_name=model, transport=transport)
    assert calls == []
    assert receipt["disposition"] == disposition
    assert receipt["dispatch"] == "none"
    assert receipt["provider"] == ""
    assert receipt["model_name"] == ""
    assert receipt["live_canary"] is False
    assert state == before


def test_cancellation_between_retries_stops_without_another_dispatch():
    event = threading.Event()

    def transport(**payload):
        if payload["attempt"] == 1:
            event.set()

    receipt, state, before, _calls = _run(
        ["disconnect", "available"],
        transport=transport,
        cancel_event=event,
    )
    assert receipt["disposition"] == "cancelled"
    assert receipt["attempts"] == 1
    assert receipt["backoff_seconds"] == []
    assert state == before


def test_pre_set_cancellation_does_not_dispatch():
    event = threading.Event()
    event.set()
    receipt, state, before, calls = _run(["disconnect", "available"], cancel_event=event)
    assert receipt["disposition"] == "cancelled"
    assert receipt["attempts"] == 0
    assert calls == []
    assert state == before


def test_optional_canary_is_labeled_and_cannot_fabricate_a_live_pass():
    def explode(**_kwargs):
        raise RuntimeError("canary transport failed")

    failed, state, before, _calls = _run(
        ["quota"],
        include_live_canary=True,
        canary_transport=explode,
    )
    assert failed["disposition"] == "quota"
    assert failed["offline_unit_complete"] is True
    assert failed["live_canary"] is False
    assert failed["optional_live_canary"]["label"] == "optional_live_canary"
    assert failed["optional_live_canary"]["blocks_offline_completion"] is False
    assert failed["optional_live_canary"]["status"] == "unavailable"
    assert failed["optional_live_canary"]["live_canary"] is False
    assert state == before

    fabricated, _state, _before, _calls = _run(
        ["available"],
        include_live_canary=True,
        canary_transport=lambda **_kwargs: {"live_canary": True, "status": "available", "text": "GROK47_CANARY_OK"},
    )
    assert fabricated["disposition"] == "available"
    assert fabricated["offline_unit_complete"] is True
    assert fabricated["live_canary"] is False
    assert fabricated["optional_live_canary"]["live_canary"] is False
    assert fabricated["optional_live_canary"]["fabricated_pass"] is False
    assert fabricated["optional_live_canary"]["status"] == "unverified"

    offline, _state, _before, _calls = _run(["malformed"])
    assert offline["optional_live_canary"]["label"] == "not_requested"
    assert offline["optional_live_canary"]["status"] == "not_requested"
    assert offline["live_canary"] is False
    assert offline["offline_unit_complete"] is True


def test_same_request_keeps_the_same_idempotency_key_across_qualifications():
    request_id = "a" * 32
    first, *_rest = _run(["disconnect", "available"], request_id=request_id)
    second, *_rest = _run(["rate_limit", "delayed", "available"], request_id=request_id)
    assert first["idempotency_key"] == second["idempotency_key"] == intake_recovery_idempotency_key(request_id)
    assert set(first["idempotency_keys"] + second["idempotency_keys"]) == {first["idempotency_key"]}
