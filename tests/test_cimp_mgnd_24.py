"""Preserve independent norm-review and bound-variable decisions.

Cases call the current review and bound-variable owners through the
first-party adapter. Unsigned reviews are not signed here. Generated Lean
stays unbuilt and unproved unless the owner report and a matching declared
prover result both exist. No test is skipped.
"""

from __future__ import annotations

import hashlib
import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

from integrations.ipfs_datasets import definition_evidence
from ipfs_datasets_py.logic.autoformal import legal_bound_variable_definition_v1 as bound_owner
from ipfs_datasets_py.logic.autoformal import legal_norm_interpretation_review_v1 as review_owner
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
    assert envelope["reviews_synthesized"] is False
    assert envelope["training_mask"] == 0
    assert envelope["evaluation_gold_mask"] == 0
    authority = envelope.get("owner_authority")
    if isinstance(authority, dict) and authority:
        assert all(flag is False for flag in authority.values())
    permissions = envelope["permissions"]
    assert permissions["source"]["granted"] is False
    assert permissions["edition"]["granted"] is False
    assert permissions["meaning"]["granted"] is False
    assert permissions["context"]["granted"] is False
    assert permissions["context"]["closes_meaning"] is False


class _Mediator:
    def log(self, *args, **kwargs):
        return None


@pytest.fixture(scope="module")
def review_case():
    module = _load_fixture("test_legal_norm_interpretation_review_v1.py", "mgnd24_review_fixture")
    materialized = module.materialize(review_owner)
    data = module.pending(review_owner, materialized)
    args, kwargs = module.assessment_arguments(review_owner, data)
    preparation = definition_evidence.prepare_norm_review_evidence_v1(**data["arguments"])
    assert preparation["status"] == "replayed", preparation.get("reason")
    build_kwargs = dict(data["build_arguments"])
    subject = definition_evidence.build_norm_review_subject_v1(
        data["preparation"],
        data["manifest"],
        **build_kwargs,
    )
    assert subject["status"] == "replayed", subject.get("reason")
    return {
        "module": module,
        "data": data,
        "args": args,
        "kwargs": kwargs,
        "preparation": preparation,
        "subject": subject,
    }


@pytest.fixture(scope="module")
def review_assessment(review_case):
    assessed = definition_evidence.assess_norm_reviews_v1(*review_case["args"], **review_case["kwargs"])
    assert assessed["status"] == "replayed", assessed.get("reason")
    return assessed


@pytest.fixture(scope="module")
def bound_case():
    module = _load_fixture("test_legal_bound_variable_definition_v1.py", "mgnd24_bound_fixture")
    helper = module.fixtures()
    inputs = helper.build_case()
    companion = helper.prepare(inputs)
    data = {
        "inputs": inputs,
        "companion": companion,
        "companion_sha256": helper.evidence.norm_definition_evidence_sha256(companion)
        if hasattr(helper, "evidence") else None,
    }
    from ipfs_datasets_py.logic.autoformal import legal_norm_definition_evidence_v1 as evidence

    data["companion_sha256"] = evidence.norm_definition_evidence_sha256(companion)
    request = module.declaration(data)
    raw = module.wire(request)
    prepared = definition_evidence.prepare_bound_variable_definition_v1(
        companion,
        raw,
        expected_companion_sha256=data["companion_sha256"],
        expected_request_sha256=module.sha(raw),
        companion_inputs=inputs,
    )
    assert prepared["status"] == "replayed", prepared.get("reason")
    data.update(request=request, raw=raw, prepared=prepared, module=module)
    return data


def test_meaningful_cases_are_nonempty():
    cases = meaningful_cases()
    assert cases
    assert tuple(case.label for case in cases) == CASE_LABELS
    assert all(case.case_id for case in cases)


def test_adapter_does_not_contain_a_review_signer():
    source = Path(definition_evidence.__file__).read_text(encoding="utf-8")
    assert "Ed25519" not in source
    assert "synthetic_fixture" not in source
    assert "def sign" not in source


def test_pending_review_keeps_permissions_independent(review_case, review_assessment):
    preparation = review_case["preparation"]
    subject = review_case["subject"]
    report = review_assessment["result"]
    assert preparation["result"]["schema"] == review_owner.PREPARATION_SCHEMA
    assert preparation["result"]["governing_definition_use"] is None
    assert preparation["result"]["status"] == "unsigned_interpretation_review_evidence_prepared"
    assert 2024 in preparation["identities"]["editions"]
    assert subject["result"]["schema"] == review_owner.SUBJECT_SCHEMA
    assert subject["result"]["graph_sha256"] == review_case["data"]["arguments"]["expected_correspondence_sha256"]
    assert report["schema"] == review_owner.SCHEMA
    assert report["evidence_assessment_status"] == "pending"
    assert report["review_count"] == 0
    assert report["authenticated_evidence_count"] == 0
    assert report["norm_interpretation_ready"] is False
    assert report["governing_definition_use"] is None
    assert report["original_signatures_cover_norm_review"] is False
    _assert_no_grant(preparation)
    _assert_no_grant(subject)
    _assert_no_grant(review_assessment)
    permissions = review_assessment["permissions"]
    assert permissions["source"] is not permissions["edition"]
    assert permissions["meaning"] is not permissions["context"]
    assert permissions["meaning"]["norm_interpretation_ready"] is False
    assert permissions["context"]["slot_count"] > 0
    assert permissions["context"]["closes_meaning"] is False
    assert permissions["edition"]["granted"] is False
    assert 2024 in preparation["permissions"]["edition"]["editions"]
    assert preparation["permissions"]["edition"]["granted"] is False
    assert preparation["permissions"]["edition"] is not preparation["permissions"]["source"]
    isolated = deepcopy(permissions)
    isolated["source"]["granted"] = True
    assert review_assessment["permissions"]["source"]["granted"] is False
    assert review_assessment["permissions"]["edition"]["granted"] is False
    assert review_assessment["permissions"]["meaning"]["granted"] is False
    assert review_assessment["permissions"]["context"]["granted"] is False
    assert isolated["edition"]["granted"] is False
    assert isolated["meaning"]["granted"] is False
    assert isolated["context"]["granted"] is False
    checked = definition_evidence.validate_norm_review_assessment_v1(
        report,
        *review_case["args"],
        **review_case["kwargs"],
    )
    assert checked["status"] == "replayed", checked.get("reason")
    assert checked["result"] == report
    assert checked["reviews_synthesized"] is False
    _assert_no_grant(checked)


def test_bound_variable_retains_alternatives_assumptions_and_carrier(bound_case):
    report = bound_case["prepared"]["result"]
    request = bound_case["request"]
    assert report["schema"] == bound_owner.SCHEMA
    assert report["status"] == "conditional_unverified_instance_prepared"
    assert report["governing_definition_use"] is None
    assert report["selected_interpretation"] is None
    assert report["backend_executed"] is False
    assert report["lean_compilation_verified"] is False
    retained = bound_case["prepared"]["retained"]
    assert retained["alternative_ids"] == ["fictional-definition-0", "fictional-definition-1"]
    assert len(retained["alternatives"]) == 2
    assert retained["assumptions"]
    assert any("unverified" in item for item in retained["assumptions"])
    assert any("have not been executed" in item for item in retained["assumptions"])
    assert any("no governing applicability" in item for item in retained["assumptions"])
    assert retained["carrier_map"] == request["carrier_map"] == bound_owner.CARRIER_MAP
    assert retained["carrier_map"]["mapping"] == "same_carrier"
    assert retained["carrier_map"]["typed_sort"] == "Object"
    assert retained["carrier_map"]["definition_carrier"] == "Entity"
    assert retained["evaluation_context"] == bound_owner.EVALUATION_CONTEXT
    assert retained["occurrence_binding"]["target"] == request["target"]
    assert retained["occurrence_binding"]["binding"] == request["binding"]
    pins = retained["source_pins"]
    assert pins["companion_sha256"] == bound_case["companion_sha256"]
    assert pins["request_sha256"] == bound_case["module"].sha(bound_case["raw"])
    assert pins["original_norm"]["unchanged"] is True
    assert pins["original_norm"]["preparation_sha256"] == bound_case["companion"]["norm_preparation_sha256"]
    lean = bound_case["prepared"]["conditional_lean"]
    assert lean["generated"] is True
    assert lean["built"] is False
    assert lean["proved"] is False
    assert lean["reason"] == "no_declared_prover_result"
    assert "theorem" in report["lean_source"]
    _assert_no_grant(bound_case["prepared"])
    checked = definition_evidence.validate_bound_variable_definition_v1(
        report,
        bound_case["companion"],
        bound_case["raw"],
        expected_report_sha256=bound_owner.bound_variable_definition_sha256(report),
        expected_companion_sha256=bound_case["companion_sha256"],
        expected_request_sha256=bound_case["module"].sha(bound_case["raw"]),
        companion_inputs=bound_case["inputs"],
    )
    assert checked["status"] == "replayed", checked.get("reason")
    assert checked["result"] == report
    assert checked["conditional_lean"]["proved"] is False
    _assert_no_grant(checked)


def test_fake_prover_declaration_does_not_build_or_prove(bound_case):
    report = bound_case["prepared"]["result"]
    source = report["lean_source"]
    declared = {
        "status": "proved",
        "kernel_checked": True,
        "lean_source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "companion_sha256": report["companion_sha256"],
        "request_sha256": report["request_sha256"],
        "theorems": list(report["conditional_theorems"]),
    }
    disposition = definition_evidence.conditional_lean_disposition(bound_case["prepared"], declared)
    assert disposition["declared_prover_result_matches"] is True
    assert disposition["built"] is False
    assert disposition["proved"] is False
    assert disposition["reason"] == "owner_execution_absent"
    mismatched = deepcopy(declared)
    mismatched["companion_sha256"] = "ab" * 32
    rejected = definition_evidence.conditional_lean_disposition(bound_case["prepared"], mismatched)
    assert rejected["declared_prover_result_matches"] is False
    assert rejected["proved"] is False
    assert rejected["built"] is False
    assert rejected["reason"] == "declared_prover_result_does_not_match_source_pins"


def test_malformed_reviews_and_missing_owners_stay_truthful(monkeypatch):
    failed = definition_evidence.prepare_norm_review_evidence_v1(
        {},
        expected_correspondence_sha256="ab" * 32,
        correspondence_inputs={},
        context_inputs=None,
    )
    assert failed["status"] == "failed"
    assert failed["result"] is None
    assert failed["reviews_synthesized"] is False
    assert failed["proof_authority_granted"] is False
    assert failed["permissions"]["meaning"]["granted"] is False
    assert failed["conditional_lean"]["proved"] is False

    refused = definition_evidence.prepare_bound_variable_definition_v1(
        {},
        b"{}",
        expected_companion_sha256="cd" * 32,
        expected_request_sha256="ef" * 32,
        companion_inputs={},
    )
    assert refused["status"] == "failed"
    assert refused["result"] is None
    assert refused["reviews_synthesized"] is False
    assert refused["conditional_lean"]["built"] is False
    assert refused["conditional_lean"]["proved"] is False

    absent_review = definition_evidence.absent_norm_evidence("review")
    assert absent_review["status"] == "unavailable"
    assert absent_review["reason"] == "evidence_not_supplied"
    assert absent_review["result"] is None
    assert absent_review["reviews_synthesized"] is False
    assert absent_review["permissions"]["source"]["granted"] is False

    monkeypatch.setattr(definition_evidence, "_norm_review_module", None)
    monkeypatch.setattr(definition_evidence, "_bound_variable_module", None)
    unavailable = definition_evidence.assess_norm_reviews_v1()
    assert unavailable["status"] == "unavailable"
    assert unavailable["reason"] == "owner_unavailable"
    assert unavailable["result"] is None
    assert unavailable["reviews_synthesized"] is False
    assert unavailable["fabricated"] is False
    missing_bound = definition_evidence.validate_bound_variable_definition_v1(
        {},
        expected_report_sha256="11" * 32,
    )
    assert missing_bound["status"] == "unavailable"
    assert missing_bound["reason"] == "owner_unavailable"
    assert missing_bound["conditional_lean"]["proved"] is False
    assert missing_bound["training_authority_granted"] is False


def test_hook_forwards_decisions_without_changing_text_or_proof(tmp_path, review_assessment, bound_case):
    requirement = {
        "requirement_id": "synthetic-requirement-24",
        "admitted_legal_text": "In this title, the term café filer means a registered person.",
        "proof": {"status": "unproved", "satisfied": False, "native_receipt": None},
        "proof_satisfied": False,
    }
    before = deepcopy(requirement)
    hook = ClaimSupportHook(_Mediator(), db_path=str(tmp_path / "claim_support.duckdb"))
    declared = {"status": "proved", "kernel_checked": True, "theorems": ["not-the-source"]}
    handoff = hook.forward_independent_norm_decisions(
        requirement,
        review_envelope=review_assessment,
        bound_variable_envelope=bound_case["prepared"],
        declared_prover_result=declared,
    )
    assert requirement == before
    assert handoff["schema"] == definition_evidence._DECISION_HANDOFF_SCHEMA
    assert handoff["admitted_legal_text"] == before["admitted_legal_text"]
    assert handoff["admitted_legal_text_changed"] is False
    assert handoff["proof"] == before["proof"]
    assert handoff["proof_changed"] is False
    assert handoff["proof_satisfied"] is False
    assert handoff["reviews_synthesized"] is False
    assert handoff["governing_definition"] is None
    assert handoff["review"]["result"]["evidence_assessment_status"] == "pending"
    assert handoff["review"]["result"]["review_count"] == 0
    assert handoff["bound_variable"]["status"] == "replayed"
    assert handoff["retained"]["alternative_ids"] == ["fictional-definition-0", "fictional-definition-1"]
    assert handoff["retained"]["assumptions"]
    assert handoff["retained"]["carrier_map"]["mapping"] == "same_carrier"
    assert handoff["retained"]["source_pins"]["bound_variable"]["companion_sha256"] == bound_case["companion_sha256"]
    assert handoff["conditional_lean"]["generated"] is True
    assert handoff["conditional_lean"]["built"] is False
    assert handoff["conditional_lean"]["proved"] is False
    permissions = handoff["permissions"]
    assert permissions["source"]["granted"] is False
    assert permissions["edition"]["granted"] is False
    assert permissions["meaning"]["granted"] is False
    assert permissions["context"]["granted"] is False
    assert permissions["context"]["slot_count"] > 0
    isolated = deepcopy(permissions)
    isolated["meaning"]["granted"] = True
    assert handoff["permissions"]["source"]["granted"] is False
    assert handoff["permissions"]["meaning"]["granted"] is False
    assert handoff["permissions"]["context"]["granted"] is False
    assert isolated["source"]["granted"] is False
    assert isolated["context"]["granted"] is False
    assert handoff["permissions"]["bound_variable"]["meaning"]["granted"] is False

    absent = hook.forward_independent_norm_decisions(requirement)
    assert requirement == before
    assert absent["review"]["status"] == "unavailable"
    assert absent["review"]["reviews_synthesized"] is False
    assert absent["review"]["result"] is None
    assert absent["bound_variable"]["status"] == "unavailable"
    assert absent["conditional_lean"]["proved"] is False
    assert absent["conditional_lean"]["built"] is False
    assert absent["reviews_synthesized"] is False
