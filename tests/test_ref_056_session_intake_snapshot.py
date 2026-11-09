import logging

from adversarial_harness.session import AdversarialSession


class _FailingPhaseManager:
    def get_phase_data(self, phase, key):
        raise RuntimeError("snapshot refresh failed")


class _Mediator:
    def __init__(self, phase_manager=None):
        self.phase_manager = phase_manager


def _make_session(mediator):
    return AdversarialSession(
        session_id="ref-056-session",
        complainant=object(),
        mediator=mediator,
        critic=object(),
    )


def test_final_intake_snapshot_refresh_failure_is_logged_and_non_fatal(caplog):
    session = _make_session(_Mediator(_FailingPhaseManager()))

    with caplog.at_level(logging.WARNING, logger="adversarial_harness.session"):
        snapshot = session._refresh_final_intake_case_file_snapshot()

    assert snapshot is None
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelno == logging.WARNING
    assert "ref-056-session" in record.getMessage()
    assert "using the mediator's existing snapshot" in record.getMessage()
    assert record.exc_info is not None
    assert record.exc_info[0] is RuntimeError


def test_final_intake_snapshot_refresh_without_phase_manager_is_quiet(caplog):
    session = _make_session(_Mediator())

    with caplog.at_level(logging.WARNING, logger="adversarial_harness.session"):
        snapshot = session._refresh_final_intake_case_file_snapshot()

    assert snapshot is None
    assert caplog.records == []
