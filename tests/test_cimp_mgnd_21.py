"""Carry admitted source identities into canonical LegalIR stages.

Cases are synthetic private fixtures. No test is skipped. Admitted law is
compiled through compile_canonical_legal_ir. Factual premises stay outside
that source. A formula or source map does not prove a claim.
"""

from __future__ import annotations

import hashlib

import pytest

from integrations.ipfs_datasets import logic
from mediator.mediator import Mediator
from tests.mgnd_fixtures import CASE_LABELS, meaningful_cases


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

_VOCABULARY = {
    "actors": ("company_a", "covered_employer"),
    "actions": ("submit", "keep"),
    "objects": ("backup_report", "safety_report"),
    "qualifiers": ("within_10_days", "emergency"),
}
_LAW = "Company A shall submit backup report within 10 days unless emergency."
_LAW_UTF8 = _LAW + " café"
_PREMISE = "The complainant missed a filing on 1 March 2024."
_ASSUMPTION = "Whether the filing office was closed is unresolved."


class _SilentBackend:
    id = "synthetic-mgnd-21"

    def __call__(self, prompt):
        return ""


@pytest.fixture(autouse=True)
def _clear_canonical_cache() -> None:
    logic.reset_canonical_formalization_cache()
    yield
    logic.reset_canonical_formalization_cache()


def _mediator(tmp_path):
    mediator = Mediator(
        [_SilentBackend()],
        evidence_db_path=str(tmp_path / "evidence.duckdb"),
        legal_authority_db_path=str(tmp_path / "authority.duckdb"),
        claim_support_db_path=str(tmp_path / "support.duckdb"),
    )
    mediator.state.username = "synthetic-mgnd-21"
    return mediator


def _admitted(text: str, **extra):
    raw = text.encode("utf-8")
    record = {
        "source_text": text,
        "citation": "Synthetic Authority §1",
        "authority_id": "synthetic-authority-1",
        "authority_version": "mgnd21-synthetic-1",
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_character_length": len(text),
        "source_byte_length": len(raw),
    }
    record.update(extra)
    return record


def _premises():
    text = _PREMISE
    return [{
        "premise_id": "premise-filing",
        "text": text,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }]


def _assumptions():
    return [{
        "assumption_id": "assumption-office-hours",
        "statement": _ASSUMPTION,
        "source_ref_ids": ["premise-filing"],
        "resolved": False,
    }]


def _carry(tmp_path, text=_LAW, **kwargs):
    mediator = _mediator(tmp_path)
    handoff = mediator.carry_admitted_source_legal_ir(
        kwargs.pop("admitted_law", _admitted(text)),
        kwargs.pop("factual_premises", _premises()),
        kwargs.pop("request_id", "mgnd21-synthetic"),
        vocabulary=kwargs.pop("vocabulary", _VOCABULARY),
        unresolved_assumptions=kwargs.pop("unresolved_assumptions", _assumptions()),
        **kwargs,
    )
    return mediator, handoff


def test_meaningful_cases_are_nonempty():
    cases = meaningful_cases()
    assert cases
    assert tuple(case.label for case in cases) == CASE_LABELS
    assert all(case.case_id for case in cases)


def test_admitted_law_keeps_premises_and_stage_identities_separate(tmp_path):
    mediator, handoff = _carry(tmp_path)
    assert handoff["status"] == "success"
    assert handoff["source_text"] == _LAW
    assert _PREMISE not in handoff["source_text"]
    assert handoff["factual_premises"][0]["bound_separately"] is True
    assert handoff["factual_premises"][0]["included_in_legal_source"] is False
    assert handoff["factual_premises"][0]["text"] == _PREMISE
    retained = handoff["retained_stage_identities"]
    for stage_id in ("typed_family_parse", "elaboration", "formalization", "bridge"):
        stage = retained[stage_id]
        assert stage["stage_id"] == stage_id
        assert stage["identity_cid"]
        assert stage["interface"]
    assert retained["source_map"]["schema_version"]
    assert retained["source_map"]["source_map_id"]
    assert handoff["unresolved_assumptions"][0]["resolved"] is False
    assert handoff["unresolved_assumptions"][0]["statement"] == _ASSUMPTION
    assert handoff["proves_claim"] is False
    assert handoff["establishes_governing_law_meaning"] is False
    assert handoff["entails_claim"] is False
    assert handoff["entails_applicability"] is False
    assert handoff["fabricated_ir"] is False
    stored = mediator.phase_manager.get_phase_data(
        mediator.phase_manager.current_phase, "canonical_legal_ir_handoff",
    )
    assert stored["receipt_id"] == handoff["receipt_id"]
    assert stored["proves_claim"] is False


def test_utf8_character_spans_match_admitted_bytes(tmp_path):
    _mediator_unused, handoff = _carry(tmp_path, _LAW_UTF8, request_id="mgnd21-utf8")
    assert handoff["status"] == "success"
    text = handoff["source_text"]
    assert text.encode("utf-8").decode("utf-8") == text
    assert handoff["source_character_length"] == len(text)
    assert handoff["source_byte_length"] == len(text.encode("utf-8"))
    assert handoff["source_character_length"] != handoff["source_byte_length"]
    assert handoff["span_unit"] == "character"
    assert text[text.index("café"):text.index("café") + len("café")] == "café"
    receipt = logic.inspect_canonical_formalization_receipt(handoff["receipt_id"])
    for passage in receipt["passages"]:
        assert text[passage["start"]:passage["end"]] == passage["passage"]
        assert passage["end"] <= len(text)


def test_malformed_admitted_law_is_failed_stage_evidence(tmp_path):
    bad_hash = _admitted(_LAW, source_sha256="0" * 64)
    _, handoff = _carry(tmp_path, admitted_law=bad_hash, request_id="mgnd21-bad-hash")
    assert handoff["status"] == "failed"
    assert handoff["reason"] == "admitted_source_hash_mismatch"
    assert handoff["source_text"] is None
    assert handoff["stage_evidence"]["fabricated_ir"] is False
    assert handoff["stage_evidence"]["source_map_present"] is False
    assert handoff["retained_stage_identities"]["formalization"] is None
    assert handoff["proves_claim"] is False

    _, replaced = _carry(
        tmp_path,
        admitted_law=_admitted(_PREMISE),
        factual_premises=_premises(),
        request_id="mgnd21-premise-as-law",
    )
    assert replaced["status"] == "failed"
    assert replaced["reason"] == "factual_premise_replaced_admitted_law"
    assert replaced["fabricated_ir"] is False

    _, resolved = _carry(
        tmp_path,
        unresolved_assumptions=[{
            "assumption_id": "assumption-closed",
            "statement": _ASSUMPTION,
            "resolved": True,
        }],
        request_id="mgnd21-resolved-assumption",
    )
    assert resolved["status"] == "failed"
    assert resolved["reason"] == "assumption_resolution_unsupported"
    assert resolved["establishes_governing_law_meaning"] is False


def test_missing_compiler_is_unavailable(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(logic, "_canonical_pipeline_module", None)
    monkeypatch.setattr(logic, "_canonical_pipeline_error", RuntimeError("canonical pipeline missing"))
    monkeypatch.setattr(logic, "_canonical_contracts_module", None)
    monkeypatch.setattr(logic, "_canonical_compiler_module", None)
    monkeypatch.setattr(logic, "_canonical_source_map_module", None)
    _, handoff = _carry(tmp_path, request_id="mgnd21-unavailable")
    assert handoff["status"] == "unavailable"
    assert handoff["fabricated_ir"] is False
    assert handoff["proves_claim"] is False
    assert handoff["establishes_governing_law_meaning"] is False
    assert "canonical pipeline missing" in handoff["reason"]
    receipt = logic.inspect_canonical_formalization_receipt(handoff["receipt_id"])
    assert receipt["status"] == "unavailable"
    assert receipt["source_map"] is None


def test_compilable_text_does_not_prove_the_claim(tmp_path):
    _, handoff = _carry(tmp_path, request_id="mgnd21-no-proof")
    assert handoff["status"] == "success"
    receipt = logic.inspect_canonical_formalization_receipt(handoff["receipt_id"])
    assert receipt["formula_ids"]
    assert receipt["source_map"]
    assert receipt["entails_claim"] is False
    assert receipt["entails_applicability"] is False
    assert receipt["establishes_governing_law_meaning"] is False
    assert receipt["proves_claim"] is False
    assert receipt["compiler_result"]
    assert handoff["proves_claim"] is False


def test_each_meaningful_case_reports_truthful_stage_evidence(tmp_path):
    seen = []
    for case in meaningful_cases():
        if case.sources:
            text = case.sources[0].source_text
            admitted = _admitted(
                text,
                citation=case.sources[0].citation,
                authority_id=case.sources[0].authority_id,
                authority_version=case.sources[0].version,
            )
        else:
            admitted = {"source_text": ""}
        premise = {
            "premise_id": case.case_id + "-narrative",
            "text": case.narrative.text,
            "text_sha256": hashlib.sha256(case.narrative.text.encode("utf-8")).hexdigest(),
        }
        _, handoff = _carry(
            tmp_path,
            admitted_law=admitted,
            factual_premises=[premise],
            unresolved_assumptions=[{
                "assumption_id": case.case_id + "-assumption",
                "statement": "Synthetic case " + case.label + " leaves this assumption unresolved.",
            }],
            request_id="mgnd21-" + case.label,
        )
        assert handoff["status"] in {"success", "failed", "unavailable", "abstained", "partial", "schema_mismatch"}
        assert handoff["proves_claim"] is False
        assert handoff["establishes_governing_law_meaning"] is False
        assert handoff["fabricated_ir"] is False
        assert handoff["entails_claim"] is False
        if handoff["status"] != "success":
            assert handoff["stage_evidence"]["source_map_present"] is False or handoff["status"] == "unavailable"
        if handoff["factual_premises"]:
            assert handoff["factual_premises"][0]["text"] not in (handoff.get("source_text") or "")
        if handoff["status"] != "failed" or handoff["unresolved_assumptions"]:
            if handoff["unresolved_assumptions"]:
                assert handoff["unresolved_assumptions"][0]["resolved"] is False
        seen.append(case.label)
    assert seen == list(CASE_LABELS)
