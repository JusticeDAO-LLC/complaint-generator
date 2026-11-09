"""Bind norm definitions and scope correspondence to synthetic source evidence.

Cases call the current definition-evidence and scope-correspondence owners.
No test is skipped. A replay does not select a governing definition, rewrite
admitted legal text, or satisfy a requirement proof.
"""

from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

from integrations.ipfs_datasets import definition_evidence
from ipfs_datasets_py.logic.autoformal import legal_norm_definition_evidence_v1 as definition_owner
from ipfs_datasets_py.logic.autoformal import legal_norm_scope_correspondence_v1 as scope_owner
from mediator.claim_support_hooks import ClaimSupportHook
from tests.mgnd_fixtures import CASE_LABELS, meaningful_cases


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

_FIXTURE_DIR = (
    Path(__file__).resolve().parents[1]
    / "external"
    / "ipfs_datasets_py"
    / "tests"
    / "unit"
    / "logic"
    / "autoformal"
)


def _load_fixture(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, _FIXTURE_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _scope_case():
    module = _load_fixture("test_legal_norm_scope_correspondence_v1.py", "mgnd23_scope_fixture")
    value = module.case(edition=2024)
    args, kwargs = module.arguments(value)
    return value, args, kwargs


def _definition_case():
    module = _load_fixture("test_legal_norm_definition_evidence_v1.py", "mgnd23_definition_fixture")
    case = module.build_case()
    return case


def _assert_no_grant(envelope: dict) -> None:
    for key in (
        "applicability_granted",
        "truth_granted",
        "training_authority_granted",
        "graph_authority_granted",
        "proof_authority_granted",
    ):
        assert envelope[key] is False
    assert envelope["fabricated"] is False
    assert envelope["legal_review_completed"] is False
    assert envelope["training_mask"] == 0
    assert envelope["evaluation_gold_mask"] == 0
    authority = envelope.get("owner_authority")
    if isinstance(authority, dict) and authority:
        assert all(flag is False for flag in authority.values())


class _Mediator:
    def log(self, *args, **kwargs):
        return None


@pytest.fixture(scope="module")
def scope_inputs():
    return _scope_case()


@pytest.fixture(scope="module")
def definition_inputs():
    return _definition_case()


@pytest.fixture(scope="module")
def scope_envelope(scope_inputs):
    _value, args, kwargs = scope_inputs
    prepared = definition_evidence.prepare_norm_scope_correspondence_v1(*args, **kwargs)
    assert prepared["status"] == "replayed", prepared.get("reason")
    return prepared


@pytest.fixture(scope="module")
def definition_envelope(definition_inputs):
    prepared = definition_evidence.prepare_norm_definition_evidence_v1(**definition_inputs)
    assert prepared["status"] == "replayed", prepared.get("reason")
    return prepared


def test_meaningful_cases_are_nonempty():
    cases = meaningful_cases()
    assert cases
    assert tuple(case.label for case in cases) == CASE_LABELS
    assert all(case.case_id for case in cases)


def test_scope_correspondence_preserves_source_identities(scope_inputs, scope_envelope):
    value, args, kwargs = scope_inputs
    report = scope_envelope["result"]
    assert report["schema"] == scope_owner.SCHEMA
    assert report["governing_definition_use"] is None
    assert report["selected_interpretation"] is None
    assert report["source_bound"] is False
    assert report["source_translation_performed"] is False
    assert scope_envelope["states"]["governing_definition_use"] is None
    assert scope_envelope["states"]["meaning_review"] == "unreviewed"
    identities = scope_envelope["identities"]
    assert "/occurrences/0/anchor" in identities["occurrences"]
    assert "/occurrences/1/anchor" in identities["occurrences"]
    assert identities["spans"]
    assert identities["entities"]
    assert 2024 in identities["editions"]
    assert value["scope_report"]["scope_declaration"]["unresolved"] == report["retained_unresolved"]
    _assert_no_grant(scope_envelope)
    checked = definition_evidence.validate_norm_scope_correspondence_v1(
        report,
        *args,
        expected_report_sha256=scope_owner.norm_scope_correspondence_sha256(report),
        **kwargs,
    )
    assert checked["status"] == "replayed", checked.get("reason")
    assert checked["result"] == report
    assert checked["identities"] == identities
    _assert_no_grant(checked)


def test_definition_evidence_keeps_two_asserted_uses_ungoverned(definition_inputs, definition_envelope):
    report = definition_envelope["result"]
    assert report["schema"] == definition_owner.SCHEMA
    assert report["governing_definition_use"] is None
    assert report["selected_interpretation"] is None
    assert report["counts"]["alternatives"] == 2
    assert report["counts"]["distinct_typed_uses"] == 2
    assert report["counts"]["links"] == 4
    uses = definition_envelope["definition_uses"]
    assert uses["governing_definition_use"] is None
    assert uses["model_filled_binding"] is False
    assert uses["alternative_ids"] == ["fictional-definition-0", "fictional-definition-1"]
    assert len(uses["asserted_uses"]) == 4
    typed_paths = {row["typed_path"] for row in uses["asserted_uses"]}
    assert len(typed_paths) == 2
    assert {row["alternative_id"] for row in uses["asserted_uses"]} == set(uses["alternative_ids"])
    assert all(row["governing_definition_use"] is None for row in uses["asserted_uses"])
    assert all(row["source_paths"] == ["/occurrences/0/anchor"] for row in uses["asserted_uses"])
    identities = definition_envelope["identities"]
    assert "/occurrences/0/anchor" in identities["occurrences"]
    assert identities["entities"]
    _assert_no_grant(definition_envelope)
    checked = definition_evidence.validate_norm_definition_evidence_v1(
        report,
        expected_report_sha256=definition_owner.norm_definition_evidence_sha256(report),
        **definition_inputs,
    )
    assert checked["status"] == "replayed", checked.get("reason")
    assert checked["result"] == report
    assert checked["definition_uses"]["alternative_ids"] == uses["alternative_ids"]
    assert checked["definition_uses"]["governing_definition_use"] is None
    _assert_no_grant(checked)


def test_conflict_and_absence_stay_unresolved_dependencies(definition_envelope, scope_envelope):
    conflict = definition_scope_copy(definition_envelope, scope_envelope)
    dependency = definition_evidence.definition_scope_dependency(conflict["definition"], conflict["scope"])
    assert dependency["status"] == "unresolved_dependency"
    assert dependency["governing_definition"] is None
    assert dependency["selected_alternative_id"] is None
    assert dependency["model_filled_binding"] is False
    assert "conflicting_governing_definition" in dependency["reasons"]
    assert "conflicting_scope_governing_use" in dependency["reasons"]
    assert "conflicting_edition_identity" in dependency["reasons"]
    assert "conflicting_occurrence_identity" in dependency["reasons"]
    assert "asserted_uses_without_governing_definition" in dependency["reasons"]
    assert len(dependency["distinct_typed_paths"]) == 2

    absent = definition_evidence.definition_scope_dependency(None, None)
    assert absent["status"] == "unresolved_dependency"
    assert absent["governing_definition"] is None
    assert absent["selected_alternative_id"] is None
    assert "absent_or_failed_definition_evidence" in absent["reasons"]
    assert "absent_or_failed_scope_evidence" in absent["reasons"]
    assert absent["model_filled_binding"] is False


def definition_scope_copy(definition_envelope, scope_envelope):
    definition = deepcopy(definition_envelope)
    scope = deepcopy(scope_envelope)
    definition["definition_uses"]["asserted_uses"][0]["governing_definition_use"] = "fictional-definition-0"
    definition["identities"]["occurrences"] = ["/occurrences/0/anchor"]
    definition["identities"]["editions"] = [2024]
    scope["result"]["governing_definition_use"] = "model-filled-use"
    scope["identities"]["occurrences"] = ["/occurrences/9/anchor"]
    scope["identities"]["editions"] = [1999]
    return {"definition": definition, "scope": scope}


def test_conditional_evidence_does_not_change_admitted_text_or_proof(
    tmp_path, definition_envelope, scope_envelope,
):
    requirement = {
        "requirement_id": "synthetic-requirement-23",
        "admitted_legal_text": "In this title, the term café filer means a registered person.",
        "proof": {"status": "unproved", "satisfied": False, "native_receipt": None},
        "proof_satisfied": False,
    }
    before = deepcopy(requirement)
    hook = ClaimSupportHook(_Mediator(), db_path=str(tmp_path / "claim_support.duckdb"))
    handoff = hook.forward_conditional_norm_evidence(requirement, definition_envelope, scope_envelope)
    assert requirement == before
    assert handoff["schema"] == definition_evidence._HANDOFF_SCHEMA
    assert handoff["requirement_id"] == requirement["requirement_id"]
    assert handoff["admitted_legal_text"] == before["admitted_legal_text"]
    assert handoff["admitted_legal_text_changed"] is False
    assert handoff["proof"] == before["proof"]
    assert handoff["proof_changed"] is False
    assert handoff["proof_satisfied"] is False
    assert handoff["governing_definition"] is None
    assert handoff["unresolved_dependency"]["status"] == "unresolved_dependency"
    assert handoff["conditional_evidence"]["definition"]["status"] == "replayed"
    assert handoff["conditional_evidence"]["scope"]["status"] == "replayed"
    assert len(handoff["asserted_uses"]) == 4
    assert {row["alternative_id"] for row in handoff["asserted_uses"]} == {
        "fictional-definition-0",
        "fictional-definition-1",
    }


def test_malformed_inputs_and_missing_owners_stay_truthful(monkeypatch):
    failed = definition_evidence.prepare_norm_scope_correspondence_v1(
        {},
        {},
        b"{}",
        expected_scope_report_sha256="ab" * 32,
        expected_relational_report_sha256="cd" * 32,
        expected_mapping_request_sha256="ef" * 32,
        scope_replay_inputs={},
        relational_request_raw=b"{}",
        expected_relational_request_sha256="11" * 32,
    )
    assert failed["status"] == "failed"
    assert failed["result"] is None
    assert failed["fabricated"] is False
    assert failed["proof_authority_granted"] is False
    assert failed["reason"]
    dependency = definition_evidence.definition_scope_dependency(failed, definition_evidence.absent_norm_evidence("scope"))
    assert dependency["status"] == "unresolved_dependency"
    assert dependency["model_filled_binding"] is False
    assert dependency["governing_definition"] is None

    monkeypatch.setattr(definition_evidence, "_definition_module", None)
    monkeypatch.setattr(definition_evidence, "_scope_module", None)
    unavailable = definition_evidence.prepare_norm_definition_evidence_v1(
        norm_preparation={},
        request_raw=b"{}",
        expected_norm_preparation_sha256="22" * 32,
        expected_request_sha256="33" * 32,
        norm_inputs={},
        definitions=[],
    )
    assert unavailable["status"] == "unavailable"
    assert unavailable["reason"] == "owner_unavailable"
    assert unavailable["result"] is None
    assert unavailable["fabricated"] is False
    scope = definition_evidence.validate_norm_scope_correspondence_v1(
        {},
        expected_report_sha256="44" * 32,
    )
    assert scope["status"] == "unavailable"
    assert scope["result"] is None
    assert scope["training_authority_granted"] is False
