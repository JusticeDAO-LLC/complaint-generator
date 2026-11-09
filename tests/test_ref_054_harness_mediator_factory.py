import logging

import pytest

from adversarial_harness.harness import AdversarialHarness


def _harness(factory):
    return AdversarialHarness(
        llm_backend_complainant=object(),
        llm_backend_critic=object(),
        mediator_factory=factory,
    )


def _create_mediator(harness):
    return harness._create_mediator_for_session(
        evidence_db_path="/sessions/ref-054/evidence.duckdb",
        legal_authority_db_path="/sessions/ref-054/legal.duckdb",
        claim_support_db_path="/sessions/ref-054/claim-support.duckdb",
        session_id="ref-054",
        session_dir="/sessions/ref-054",
    )


def test_create_mediator_forwards_only_supported_session_arguments():
    calls = []
    mediator = object()

    def factory(*, evidence_db_path, session_id):
        calls.append((evidence_db_path, session_id))
        return mediator

    result = _create_mediator(_harness(factory))

    assert result is mediator
    assert calls == [("/sessions/ref-054/evidence.duckdb", "ref-054")]


def test_create_mediator_does_not_retry_or_swallow_factory_failure():
    calls = []

    def factory(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("mediator initialization failed")

    with pytest.raises(RuntimeError, match="mediator initialization failed"):
        _create_mediator(_harness(factory))

    assert len(calls) == 1
    assert calls[0]["session_id"] == "ref-054"
    assert calls[0]["evidence_db_path"] == "/sessions/ref-054/evidence.duckdb"


def test_create_mediator_logs_uninspectable_factory_fallback(caplog):
    class UninspectableFactory:
        calls = 0

        @property
        def __signature__(self):
            raise ValueError("signature unavailable")

        def __call__(self):
            self.calls += 1
            return "mediator"

    factory = UninspectableFactory()

    with caplog.at_level(logging.WARNING, logger="adversarial_harness.harness"):
        result = _create_mediator(_harness(factory))

    assert result == "mediator"
    assert factory.calls == 1
    assert "Could not inspect mediator factory UninspectableFactory" in caplog.text
    assert "signature unavailable" in caplog.text


def test_create_mediator_does_not_swallow_unexpected_inspection_failure():
    class BrokenSignatureFactory:
        calls = 0

        @property
        def __signature__(self):
            raise RuntimeError("signature implementation failed")

        def __call__(self):
            self.calls += 1

    factory = BrokenSignatureFactory()

    with pytest.raises(RuntimeError, match="signature implementation failed"):
        _create_mediator(_harness(factory))

    assert factory.calls == 0


def test_create_mediator_does_not_pass_positional_only_parameter_by_keyword():
    calls = []

    def factory(session_id="default", /):
        calls.append(session_id)
        return "mediator"

    result = _create_mediator(_harness(factory))

    assert result == "mediator"
    assert calls == ["default"]
