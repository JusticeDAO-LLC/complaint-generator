"""CIMP-UX-55: bounded web evidence acquisition, custody, and explicit adoption."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from integrations.ipfs_datasets.search import bounded_web_custody_id, dispatch_bounded_web_adapter
from mediator.hook_runtime import qualify_web_evidence_hooks


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

PRIVATE = "The employee was dismissed the morning after the internal report, case note 55."
PUBLIC_QUERY = "ORS retaliation notice archive"


def _asset(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "assets"
    root.mkdir(exist_ok=True)
    body = "Public archive notice: an employer shall not retaliate for a report."
    path = root / "notice.txt"
    path.write_text(body, encoding="utf-8")
    return root, body


def _request(tmp_path: Path, **overrides):
    root, body = _asset(tmp_path)
    payload = {
        "actor_id": "actor-55",
        "case_id": "case-55",
        "adapter": "offline_asset",
        "operation": "bounded_search",
        "public_query": PUBLIC_QUERY,
        "private_complaint": PRIVATE,
        "asset_root": str(root),
        "offline_asset": "notice.txt",
        "custody_directory": str(tmp_path / "custody"),
        "remote_permission": "gap",
        "caller_flags": {"adopt_as_fact": True, "verified_support": True, "auto_adopt": True},
    }
    payload.update(overrides)
    return payload, root, body


def _custody_id(root: Path, body: str) -> str:
    source_url = (root / "notice.txt").resolve().as_uri()
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return bounded_web_custody_id("offline_asset", source_url, digest)


def test_offline_acquisition_keeps_custody_review_and_support_distinct(tmp_path):
    payload, root, body = _request(tmp_path)
    snapshot = json.dumps(payload)
    receipt = qualify_web_evidence_hooks(payload)
    assert json.dumps(payload) == snapshot
    assert receipt["status"] == "qualified"
    assert receipt["code"] == "reviewed"
    assert receipt["workflow"] == "qualify_web_evidence_hooks"
    assert receipt["owners"] == ["WebEvidenceSearchHook", "WebEvidenceIntegrationHook"]
    assert receipt["provider_invoked"] is False
    assert receipt["handler_enabled_by_caller"] is False
    assert receipt["caller_flags_applied"] is False
    assert receipt["network_invoked"] is False
    assert receipt["commoncrawl_mutated"] is False
    assert receipt["private_complaint_egress"] is False
    assert receipt["fact_adopted"] is False
    assert receipt["facts"] == []
    assert receipt["automatic_fact_adoption"] is False
    assert receipt["support"]["code"] == "automatic_fact_adoption_refused"
    assert receipt["support"]["fact_adopted"] is False
    acquisition = receipt["acquisition"]
    assert acquisition["stage"] == "acquisition"
    assert acquisition["query_dispatched"] == PUBLIC_QUERY
    assert acquisition["content_sha256"] == hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert acquisition["byte_length"] == len(body.encode("utf-8"))
    assert acquisition["custody_id"] == _custody_id(root, body)
    assert acquisition["review_status"] == "unreviewed"
    assert acquisition["support_status"] == "not_support"
    assert PRIVATE not in acquisition["query_dispatched"]
    review = receipt["review"]
    assert review["stage"] == "review"
    assert review["review_status"] == "reviewed"
    assert review["support_status"] == "not_support"
    assert review["fact_adopted"] is False
    assert review["text"] == body
    files = receipt["effects"]["files"]
    assert receipt["effects"]["log_count"] >= 1
    assert "support" not in files
    stored_acquisition = json.loads(Path(files["acquisition"]).read_text(encoding="utf-8"))
    stored_review = json.loads(Path(files["review"]).read_text(encoding="utf-8"))
    assert stored_acquisition["stage"] == "acquisition"
    assert stored_review["stage"] == "review"
    assert stored_acquisition["content_sha256"] == acquisition["content_sha256"]
    assert PRIVATE not in Path(files["acquisition"]).read_text(encoding="utf-8")
    assert PRIVATE not in Path(files["review"]).read_text(encoding="utf-8")
    direct = dispatch_bounded_web_adapter(payload)
    assert direct["custody"]["custody_id"] == acquisition["custody_id"]
    assert direct["network_invoked"] is False


def test_explicit_adoption_creates_support_without_a_fact(tmp_path):
    payload, root, body = _request(tmp_path, caller_flags={})
    discovered = qualify_web_evidence_hooks(payload)
    payload["adoption"] = {
        "intent": "adopt_source_not_fact",
        "actor_id": "actor-55",
        "custody_id": discovered["acquisition"]["custody_id"],
    }
    receipt = qualify_web_evidence_hooks(payload)
    assert receipt["status"] == "qualified"
    assert receipt["code"] == "explicit_support"
    assert receipt["fact_adopted"] is False
    assert receipt["facts"] == []
    support = receipt["support"]
    assert support["stage"] == "adoption"
    assert support["support_status"] == "explicit_support"
    assert support["fact_adopted"] is False
    assert support["facts"] == []
    assert support["custody_id"] == _custody_id(root, body)
    assert support["content_sha256"] == hashlib.sha256(body.encode("utf-8")).hexdigest()
    stored = json.loads(Path(receipt["effects"]["files"]["support"]).read_text(encoding="utf-8"))
    assert stored["support_status"] == "explicit_support"
    assert stored["fact_adopted"] is False
    assert stored["stage"] != receipt["review"]["stage"]
    assert receipt["acquisition"]["stage"] != support["stage"]
    assert PRIVATE not in Path(receipt["effects"]["files"]["support"]).read_text(encoding="utf-8")


def test_mismatched_adoption_does_not_create_support(tmp_path):
    payload, _root, _body = _request(tmp_path, caller_flags={})
    payload["adoption"] = {
        "intent": "adopt_source_not_fact",
        "actor_id": "actor-55",
        "custody_id": "custody-not-this-source",
    }
    receipt = qualify_web_evidence_hooks(payload)
    assert receipt["support"]["status"] == "refused"
    assert receipt["support"]["code"] == "missing_explicit_adoption"
    assert receipt["support"]["fact_adopted"] is False
    assert receipt["facts"] == []
    assert "support" not in receipt["effects"]["files"]
    assert receipt["review"]["support_status"] == "not_support"


def test_missing_offline_asset_is_unavailable(tmp_path):
    payload, _root, _body = _request(tmp_path, offline_asset="missing-notice.txt")
    receipt = qualify_web_evidence_hooks(payload)
    assert receipt["status"] == "unavailable"
    assert receipt["code"] == "offline_asset_missing"
    assert receipt["review"] is None
    assert receipt["support"] is None
    assert receipt["facts"] == []
    assert receipt["fact_adopted"] is False
    assert receipt["effects"]["files"] == {}
    assert not (tmp_path / "custody").exists()


def test_remote_permission_gap_does_not_call_the_network(tmp_path, monkeypatch):
    payload, _root, _body = _request(tmp_path, adapter="brave_search", remote_permission="gap")

    def _explode(*_args, **_kwargs):
        raise AssertionError("remote adapter was called")

    monkeypatch.setattr("integrations.ipfs_datasets.search.requests.Session", _explode)
    monkeypatch.setattr("integrations.ipfs_datasets.search.search_brave_web", _explode)
    monkeypatch.setattr("integrations.ipfs_datasets.search.fetch_commoncrawl_index_candidates", _explode)
    receipt = qualify_web_evidence_hooks(payload)
    assert receipt["status"] == "unavailable"
    assert receipt["code"] == "remote_permission_gap"
    assert receipt["network_invoked"] is False
    assert receipt["acquisition"]["query_dispatched"] == PUBLIC_QUERY
    assert receipt["private_complaint_egress"] is False
    assert receipt["facts"] == []
    assert receipt["effects"]["files"] == {}


def test_commoncrawl_reset_and_unbounded_crawl_are_refused(tmp_path, monkeypatch):
    def _explode(*_args, **_kwargs):
        raise AssertionError("common crawl mutation was attempted")

    monkeypatch.setattr("integrations.ipfs_datasets.search.fetch_commoncrawl_index_candidates", _explode)
    monkeypatch.setattr("integrations.ipfs_datasets.search.discover_seeded_commoncrawl", _explode)
    reset_payload, _root, _body = _request(tmp_path, operation="reset_commoncrawl", adapter="common_crawl_index")
    reset = qualify_web_evidence_hooks(reset_payload)
    assert reset["status"] == "refused"
    assert reset["code"] == "commoncrawl_mutation_refused"
    assert reset["commoncrawl_mutated"] is False
    assert reset["network_invoked"] is False
    assert reset["facts"] == []
    crawl_payload, _root, _body = _request(tmp_path, operation="unbounded_crawl")
    crawl = qualify_web_evidence_hooks(crawl_payload)
    assert crawl["status"] == "refused"
    assert crawl["code"] == "uncontrolled_crawl"
    assert crawl["uncontrolled_crawl"] is True
    assert crawl["effects"]["files"] == {}


def test_private_complaint_is_not_dispatched(tmp_path):
    payload, _root, _body = _request(tmp_path, public_query=PUBLIC_QUERY + " " + PRIVATE)
    receipt = qualify_web_evidence_hooks(payload)
    assert receipt["status"] == "refused"
    assert receipt["code"] == "private_complaint_egress"
    assert receipt["private_complaint_egress"] is True
    assert receipt["acquisition"]["query_dispatched"] == ""
    assert receipt["facts"] == []
    assert receipt["network_invoked"] is False
    included, _root, _body = _request(tmp_path, include_private_complaint=True)
    included_receipt = qualify_web_evidence_hooks(included)
    assert included_receipt["code"] == "private_complaint_egress"
    assert included_receipt["fact_adopted"] is False


def test_fact_adoption_flag_on_the_decision_is_refused(tmp_path):
    payload, root, body = _request(tmp_path, caller_flags={})
    payload["adoption"] = {
        "intent": "adopt_source_not_fact",
        "actor_id": "actor-55",
        "custody_id": _custody_id(root, body),
        "adopt_as_fact": True,
    }
    receipt = qualify_web_evidence_hooks(payload)
    assert receipt["support"]["code"] == "automatic_fact_adoption_refused"
    assert receipt["fact_adopted"] is False
    assert receipt["facts"] == []
    assert "support" not in receipt["effects"]["files"]
    assert receipt["review"]["stage"] == "review"
    assert receipt["acquisition"]["stage"] == "acquisition"
