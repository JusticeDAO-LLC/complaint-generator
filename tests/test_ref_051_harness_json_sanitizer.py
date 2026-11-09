import logging

import pytest

from adversarial_harness.harness import _sanitize_for_json


class _RejectedIsoformat:
    __slots__ = ()

    def isoformat(self):
        raise ValueError("timestamp is outside the supported range")

    def __str__(self):
        return "fallback-timestamp"


class _BrokenIsoformat:
    __slots__ = ()

    def isoformat(self):
        raise RuntimeError("unexpected serializer defect")


def test_sanitize_for_json_logs_rejected_isoformat_and_uses_fallback(caplog):
    with caplog.at_level(logging.WARNING, logger="adversarial_harness.harness"):
        result = _sanitize_for_json(_RejectedIsoformat())

    assert result == "fallback-timestamp"
    assert "Could not serialize _RejectedIsoformat with isoformat()" in caplog.text
    assert "timestamp is outside the supported range" in caplog.text


def test_sanitize_for_json_does_not_swallow_unexpected_isoformat_failure():
    with pytest.raises(RuntimeError, match="unexpected serializer defect"):
        _sanitize_for_json(_BrokenIsoformat())
