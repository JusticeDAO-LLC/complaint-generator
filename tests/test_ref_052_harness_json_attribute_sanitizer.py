import logging

import pytest

from adversarial_harness.harness import _sanitize_for_json


class _RejectedAttributeAccess:
    def __init__(self):
        self._attribute_requests = 0

    def __getattribute__(self, name):
        if name == "__dict__":
            requests = object.__getattribute__(self, "_attribute_requests")
            object.__setattr__(self, "_attribute_requests", requests + 1)
            if requests:
                raise TypeError("object attributes are unavailable")
        return object.__getattribute__(self, name)

    def __str__(self):
        return "fallback-object"


class _BrokenAttributeValue:
    def isoformat(self):
        raise RuntimeError("unexpected nested serializer defect")


class _ObjectWithBrokenAttribute:
    def __init__(self):
        self.created_at = _BrokenAttributeValue()


def test_sanitize_for_json_logs_unavailable_attributes_and_uses_fallback(caplog):
    with caplog.at_level(logging.WARNING, logger="adversarial_harness.harness"):
        result = _sanitize_for_json(_RejectedAttributeAccess())

    assert result == "fallback-object"
    assert "Could not inspect _RejectedAttributeAccess attributes" in caplog.text
    assert "object attributes are unavailable" in caplog.text


def test_sanitize_for_json_does_not_swallow_nested_attribute_failure():
    with pytest.raises(RuntimeError, match="unexpected nested serializer defect"):
        _sanitize_for_json(_ObjectWithBrokenAttribute())
