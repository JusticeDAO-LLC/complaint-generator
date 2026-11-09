"""Guarded synthetic case fixtures stay private, labeled, and unsatisfied.

Cases are authored local fixtures. No test is skipped. A synthetic transport
record is not treated as a live route observation.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from applications.complaint_cli import TerminalComplaintWorkspaceService
from applications.complaint_workspace import ComplaintWorkspaceService
from tests.mgnd_fixtures import (
    CASE_LABELS,
    admit_source_record,
    case_by_label,
    case_catalog,
    install_provider_guards,
    marker_values_in_narrative,
    materialize_case,
    meaningful_cases,
    source_record_payload,
    assert_remote_socket_blocked,
)


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]


def test_catalog_has_authored_narratives_law_bytes_and_markers() -> None:
    cases = meaningful_cases()
    assert len(cases) == len(CASE_LABELS)
    assert tuple(case.label for case in cases) == CASE_LABELS
    seen_text = set()
    for case in cases:
        narrative = case.narrative
        assert narrative.text.strip()
        assert narrative.narrative_id
        assert narrative.jurisdiction
        marker_values_in_narrative(narrative)
        assert narrative.event_date or case.label == "unknown"
        seen_text.add(narrative.text)
        for source in case.sources:
            assert source.source_bytes
            assert source.source_text.encode("utf-8") == source.source_bytes
            assert len(source.source_sha256) == 64
            assert source.effective_date
            assert source.jurisdiction
            payload = source_record_payload(source)
            assert "satisfied" not in payload
            assert "verified" not in payload
            assert payload["source_text"].encode("utf-8") == source.source_bytes
            assert payload["source_hash"] == source.source_sha256
    assert len(seen_text) == len(cases)
    assert case_by_label("missing_authority").sources == ()
    contradiction = case_by_label("contradiction")
    assert len(contradiction.sources) == 2
    assert contradiction.sources[0].source_bytes != contradiction.sources[1].source_bytes
    dates = {marker.value for marker in contradiction.narrative.evidence_markers if marker.field == "event_date"}
    assert dates == {"2024-03-04", "2024-03-11"}
    unknown = case_by_label("unknown")
    assert unknown.narrative.jurisdiction == "unknown"
    assert unknown.narrative.event_date == ""
    assert unknown.sources[0].jurisdiction == "unknown"


def test_private_root_factories_keys_and_provider_guards(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    case = case_by_label("baseline")
    bundle = materialize_case(tmp_path, monkeypatch, case)
    root = bundle.root
    assert root.root.parent == tmp_path.resolve() or root.root.parent == tmp_path
    for path in root.contained_paths():
        path.resolve().relative_to(root.root.resolve())
    assert root.sessions.is_dir()
    assert root.keys.is_dir()
    assert root.index.is_dir()
    assert root.receipts.is_dir()
    assert any(root.keys.iterdir())
    assert type(bundle.service) is ComplaintWorkspaceService
    assert type(bundle.terminal) is TerminalComplaintWorkspaceService
    assert bundle.service._session_dir == root.sessions
    assert bundle.terminal._session_dir == root.sessions
    assert bundle.legal_graph is None
    assert bundle.native_completion is False
    assert bundle.awaiting_user is False
    assert bundle.worker_stalled is False
    receipt_path = root.receipts / "synthetic-transport.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["kind"] == "synthetic_private_fixture"
    assert receipt["live_route_observation"] is False
    assert receipt["verifies_live_grok_identity"] is False
    assert receipt["native_completion"] is False
    assert receipt["evidence_class"] == "synthetic_fixture"
    assert "native_final" not in receipt_path.read_text(encoding="utf-8")
    guard = install_provider_guards(monkeypatch)
    assert issubclass(subprocess.Popen, guard.original_popen)
    assert subprocess.Popen is guard.guarded_popen
    assert subprocess.Popen is not guard.original_popen
    completed = subprocess.run(["/usr/bin/true"], check=False)
    assert completed.returncode == 0
    with pytest.raises(RuntimeError, match="provider subprocess blocked"):
        subprocess.run(["grok", "--version"], check=False)
    assert_remote_socket_blocked()
    raw_receipt = receipt_path.read_bytes()
    assert b"synthetic-mgnd-04-passphrase" not in raw_receipt


def test_admission_uses_real_extractor_and_does_not_seed_a_graph() -> None:
    from integrations.ipfs_datasets.logic import extract_source_bound_rule_candidates

    baseline = case_by_label("baseline").sources[0]
    payload = source_record_payload(baseline)
    admission = admit_source_record(payload)
    assert admission["bounded"] is True
    assert admission["reason"] == "bounded_source_record"
    assert admission["legal_graph"] is None
    assert admission["native_completion"] is False
    assert admission["satisfied_seeded"] is False
    assert admission["fake_backend"] is False
    assert admission["extraction"] == extract_source_bound_rule_candidates(payload)
    extraction = admission["extraction"]
    assert extraction["contract"]
    assert extraction["candidate_count"] >= 1
    for candidate in extraction["candidates"]:
        assert candidate.get("satisfied") is None or "satisfied" not in candidate
    missing = admit_source_record(None)
    assert missing["admitted"] is False
    assert missing["reason"] == "missing_authority"
    assert missing["extraction"] is None
    assert missing["legal_graph"] is None
    spoofed = dict(payload)
    spoofed["satisfied"] = True
    rejected = admit_source_record(spoofed)
    assert rejected["admitted"] is False
    assert rejected["reason"] == "spoofed_satisfaction"
    unknown = admit_source_record(source_record_payload(case_by_label("unknown").sources[0]))
    reasons = []
    for candidate in unknown["extraction"]["candidates"]:
        reasons.extend(candidate.get("review_reasons") or [])
    assert "missing_jurisdiction" in reasons
    assert unknown["legal_graph"] is None


def test_labeled_failures_stay_truthful_and_unskipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    collected = []
    for case in case_catalog():
        bundle = materialize_case(tmp_path / case.label, monkeypatch, case)
        collected.append(bundle)
        assert bundle.case.label == case.label
        assert bundle.transport["live_route_observation"] is False
        assert bundle.transport["outcome"] == case.outcome
        assert bundle.native_completion is False
        assert bundle.legal_graph is None
        assert bundle.worker_stalled is False
        if case.label == "missing_authority":
            assert bundle.admissions[0]["reason"] == "missing_authority"
        elif case.label == "contradiction":
            assert len(bundle.admissions) == 2
            assert all(item["legal_graph"] is None for item in bundle.admissions)
            assert bundle.admissions[0]["extraction"]["candidates"][0]["rule_text"] != (
                bundle.admissions[1]["extraction"]["candidates"][0]["rule_text"]
            )
        elif case.label == "unknown":
            assert bundle.case.narrative.jurisdiction == "unknown"
            assert bundle.case.outcome == "unknown"
        elif case.label == "cancellation":
            assert bundle.case.outcome == "cancelled"
            assert bundle.awaiting_user is False
        elif case.label == "storage_outage":
            assert bundle.storage.available is False
            assert bundle.storage.reason == "storage_outage"
            assert bundle.storage.live_route_observation is False
            with pytest.raises(OSError, match="storage_outage"):
                from tests.mgnd_fixtures import require_index_directory
                require_index_directory(bundle.root)
        else:
            assert bundle.storage.available is True
            assert bundle.admissions[0]["bounded"] is True
    assert len(collected) == len(CASE_LABELS)
    assert all(item.transport["kind"] == "synthetic_private_fixture" for item in collected)
