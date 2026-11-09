import logging

import pytest

from adversarial_harness.harness import AdversarialHarness
from adversarial_harness.session import SessionResult


def _result(seed_complaint):
    return SessionResult(
        session_id="session-ref-053",
        timestamp="2026-07-22T00:00:00+00:00",
        seed_complaint=seed_complaint,
        initial_complaint_text="Complaint",
        conversation_history=[],
        num_questions=0,
        num_turns=0,
        final_state={},
    )


def test_malformed_optional_seed_metadata_is_logged_and_left_unchanged(caplog):
    seed = {
        "source": "external-package",
        # A non-mapping key_facts value cannot supply search or anchor metadata.
        "key_facts": ["malformed"],
    }
    result = _result(seed)

    with caplog.at_level(logging.WARNING, logger="adversarial_harness.harness"):
        returned = AdversarialHarness._attach_result_spec_metadata(
            result,
            {"hacc_search_mode": "hybrid"},
        )

    assert returned is result
    assert result.seed_complaint is seed
    assert result.seed_complaint == {
        "source": "external-package",
        "key_facts": ["malformed"],
    }
    assert "Could not attach optional specification metadata to session session-ref-053" in caplog.text
    assert "dictionary update sequence element" in caplog.text


class _UnexpectedSeedFailure(dict):
    def get(self, key, default=None):
        raise RuntimeError("unexpected seed metadata defect")


def test_unexpected_metadata_failure_is_not_swallowed():
    result = _result(_UnexpectedSeedFailure())

    with pytest.raises(RuntimeError, match="unexpected seed metadata defect"):
        AdversarialHarness._attach_result_spec_metadata(result, {})
