from __future__ import annotations

import pytest

from complaint_analysis import research_bootstrap_workflow

pytestmark = pytest.mark.no_auto_network


def test_normalize_external_url_rejects_malformed_url() -> None:
    assert (
        research_bootstrap_workflow.normalize_external_url(
            "http://[invalid-ipv6",
            "https://quantumresidential.com/source",
        )
        is None
    )


def test_normalize_external_url_does_not_swallow_unexpected_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_url_join(_base_url: str, _raw_url: str) -> str:
        raise RuntimeError("unexpected URL normalizer failure")

    monkeypatch.setattr(research_bootstrap_workflow, "urljoin", fail_url_join)

    with pytest.raises(RuntimeError, match="unexpected URL normalizer failure"):
        research_bootstrap_workflow.normalize_external_url(
            "/documents/report.pdf",
            "https://quantumresidential.com/source",
        )


def test_score_candidate_url_rejects_malformed_url() -> None:
    assert research_bootstrap_workflow.score_candidate_url("http://[invalid-ipv6/report.pdf") is None


def test_score_candidate_url_does_not_swallow_unexpected_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_url_parse(_url: str) -> object:
        raise RuntimeError("unexpected URL scorer failure")

    monkeypatch.setattr(research_bootstrap_workflow, "urlparse", fail_url_parse)

    with pytest.raises(RuntimeError, match="unexpected URL scorer failure"):
        research_bootstrap_workflow.score_candidate_url("https://example.com/report.pdf")
