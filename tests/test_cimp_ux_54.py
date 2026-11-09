"""CIMP-UX-54: formal and neurosymbolic analysis stays on actual producers."""

from __future__ import annotations

import copy

import pytest

from integrations.ipfs_datasets import logic
from integrations.ipfs_datasets.logic import sha256_utf8
from mediator.hook_runtime import ground_formal_neurosymbolic_analysis


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

STATUTE = "An employer shall not retaliate against an employee for opposing an unlawful practice."
PREMISE = "The employee opposed an unlawful practice on March 3, 2024."


def _payload(**overrides):
    body = {
        "source_text": STATUTE,
        "source_hash": sha256_utf8(STATUTE),
        "source_version": "2024-edition",
        "current_source_version": "2024-edition",
        "definition_identity": "def-retaliation-3",
        "current_definition_identity": "def-retaliation-3",
        "requirement_id": "req-retaliation",
        "citation": "ORS 659A.030",
        "premises": [{
            "premise_id": "premise-opposed",
            "text": PREMISE,
            "revision": "rev-1",
        }],
        "current_premises": [{
            "premise_id": "premise-opposed",
            "revision": "rev-1",
            "text_sha256": sha256_utf8(PREMISE),
        }],
        "parsed_formula": {
            "formula": "forall x. Employer(x) -> Obligation(x)",
            "status": "proved",
            "legal_sufficiency": True,
        },
        "structural_graph": {"status": "proved", "legal_sufficiency": True},
        "classifier_score": 0.99,
        "training_metric": {"accuracy": 1.0, "status": "proved"},
        "fake_producer": {"outcome": "proved", "substantive_trust_satisfied": True, "legal_sufficiency": True},
        "claims": [{
            "id": "claim-retaliation",
            "name": "Retaliation claim",
            "claim_type": "retaliation",
        }],
        "requirements": [{
            "id": "req-protected-activity",
            "name": "protected activity notice",
            "claim_type": "retaliation",
            "satisfied": True,
            "confidence": 0.97,
            "citation": "ORS 659A.030",
            "source_version": "2024-edition",
            "definition_identity": "def-retaliation-3",
        }],
    }
    body.update(overrides)
    return body


def _assert_not_sufficiency(receipt):
    assert receipt["executed_proof"] is False
    assert receipt["legal_sufficiency"] is False
    assert receipt["parsed_formula_is_proof"] is False
    assert receipt["structural_graph_is_proof"] is False
    assert receipt["classifier_score_is_proof"] is False
    assert receipt["training_metric_is_proof"] is False
    assert receipt["fake_producer_is_proof"] is False
    assert receipt["provider_invoked"] is False
    assert receipt["handler_enabled_by_caller"] is False
    assert receipt["caller_flags_applied"] is False
    nonproof = receipt["nonproof"]
    assert nonproof["parsed_formula"]["executed_proof"] is False
    assert nonproof["fake_producer"]["rejected"] is True
    assert nonproof["fake_producer"]["caller_outcome"] == "proved"
    assert nonproof["classifier_score"]["value_ignored"] is True
    assert nonproof["training_metric"]["value_ignored"] is True
    assert receipt["structural"]["executed_proof"] is False
    assert receipt["structural"]["legal_sufficiency"] is False
    assert receipt["structural"]["satisfied_is_proof"] is False


def test_current_bindings_use_live_producers_without_promoting_nonproof_artifacts():
    payload = _payload()
    snapshot = copy.deepcopy(payload)
    receipt = ground_formal_neurosymbolic_analysis(payload)
    assert payload == snapshot
    assert receipt["workflow"] == "ground_formal_neurosymbolic_analysis"
    assert receipt["status"] == "grounded"
    assert receipt["code"] == "producer_result"
    assert receipt["producer_invoked"] is True
    assert receipt["source_version"] == "2024-edition"
    assert receipt["definition_identity"] == "def-retaliation-3"
    assert receipt["requirement_id"] == "req-retaliation"
    assert receipt["source_hash"] == sha256_utf8(STATUTE)
    assert receipt["fol"]["producer"] == "text_to_fol"
    assert receipt["fol"]["converter"] in {"FOLConverter", "local_regex_fallback"}
    assert receipt["fol"]["executed_proof"] is False
    assert receipt["neurosymbolic"]["producer"].endswith("NeurosymbolicReasoner") or receipt["neurosymbolic"]["producer"] == "NeurosymbolicReasoner.parse"
    assert receipt["neurosymbolic"]["executed_proof"] is False
    assert receipt["neurosymbolic"]["execution"] in {"unexecuted", "parsed_not_proved"}
    assert receipt["canonical"]["producer"] == "compile_canonical_legal_ir"
    assert receipt["canonical"]["executed_proof"] is False
    assert receipt["canonical"]["status"] not in (None, "")
    assert receipt["obligations"]["producer"] == "generate_bound_legal_ir_proof_obligations"
    assert receipt["obligations"]["structural_validation_is_entailment"] is False
    assert receipt["obligations"]["executed_proof"] is False
    route = receipt["route"]
    assert route["producer"] == "route_bound_legal_ir_proof"
    assert route["producer_invoked"] is True
    assert route["outcome"] in logic.PROOF_ROUTING_OUTCOMES
    assert receipt["execution"] == route["outcome"]
    assert route["legal_sufficiency"] is False
    assert route["substantive_trust_satisfied"] is (route["outcome"] == "proved")
    assert receipt["executed_proof"] is (
        route["outcome"] == "proved" and route["substantive_trust_satisfied"] is True
    )
    assert route["similarity_score_ignored"] is True
    assert route["model_assertion_ignored"] is True
    assert route["structural_proof_is_substantive"] is False
    structural = receipt["structural"]
    assert structural["status"] == "checked"
    assert structural["execution"] == "structural_only"
    assert structural["producer"] == "NeurosymbolicMatcher.match_claims_to_law"
    assert structural["structural_match"] is True
    assert structural["satisfied_claims"] == 1
    assert structural["caller_graph_status"] == "proved"
    assert structural["caller_graph_ignored"] is True
    _assert_not_sufficiency(receipt)


def test_missing_compiler_is_unavailable_and_unexecuted(monkeypatch):
    monkeypatch.setattr(logic, "canonical_compiler_identities", lambda: None)
    calls = {"route": 0}
    original = logic.route_bound_legal_ir_proof

    def _route(*args, **kwargs):
        calls["route"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(logic, "route_bound_legal_ir_proof", _route)
    receipt = ground_formal_neurosymbolic_analysis(_payload())
    assert calls["route"] == 0
    assert receipt["status"] == "unavailable"
    assert receipt["code"] == "missing_producer"
    assert receipt["execution"] == "unexecuted"
    assert receipt["producer_invoked"] is False
    assert receipt["canonical"]["status"] == "unavailable"
    assert receipt["route"]["outcome"] == "unavailable"
    assert receipt["route"]["producer_invoked"] is False
    assert receipt["fol"]["executed_proof"] is False
    assert receipt["neurosymbolic"]["executed_proof"] is False
    _assert_not_sufficiency(receipt)


def test_stale_definition_does_not_execute_producers(monkeypatch):
    calls = {"compile": 0}
    original = logic.compile_canonical_legal_ir

    def _compile(*args, **kwargs):
        calls["compile"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(logic, "compile_canonical_legal_ir", _compile)
    receipt = ground_formal_neurosymbolic_analysis(_payload(current_definition_identity="def-retaliation-4"))
    assert calls["compile"] == 0
    assert receipt["status"] == "unexecuted"
    assert receipt["code"] == "stale_binding"
    assert receipt["execution"] == "unexecuted"
    assert receipt["producer_invoked"] is False
    assert receipt["canonical"] is None
    assert receipt["route"] is None
    _assert_not_sufficiency(receipt)


def test_premise_revision_drift_stays_unexecuted():
    receipt = ground_formal_neurosymbolic_analysis(_payload(
        premises=[{
            "premise_id": "premise-opposed",
            "text": PREMISE,
            "revision": "rev-2",
        }],
    ))
    assert receipt["status"] == "unexecuted"
    assert receipt["code"] == "premise_drift"
    assert receipt["execution"] == "unexecuted"
    assert receipt["producer_invoked"] is False
    assert receipt["executed_proof"] is False
    assert receipt["legal_sufficiency"] is False


def test_source_hash_mismatch_is_not_executed_proof():
    receipt = ground_formal_neurosymbolic_analysis(_payload(source_hash="0" * 64))
    assert receipt["code"] == "source_drift"
    assert receipt["execution"] == "unexecuted"
    assert receipt["producer_invoked"] is False
    assert receipt["executed_proof"] is False
    assert receipt["structural"]["structural_match"] is True
    assert receipt["structural"]["executed_proof"] is False


def test_structural_satisfaction_without_claims_is_unexecuted():
    receipt = ground_formal_neurosymbolic_analysis(_payload(
        claims=[],
        current_definition_identity="def-other",
    ))
    assert receipt["status"] == "unexecuted"
    assert receipt["structural"]["status"] == "unexecuted"
    assert receipt["structural"]["execution"] == "unexecuted"
    assert receipt["structural"]["structural_match"] is False
    assert receipt["executed_proof"] is False


def test_missing_source_and_malformed_payload_are_refused():
    missing = ground_formal_neurosymbolic_analysis(_payload(source_text="  "))
    assert missing["status"] == "refused"
    assert missing["code"] == "missing_source_text"
    assert missing["execution"] == "unexecuted"
    assert missing["executed_proof"] is False
    malformed = ground_formal_neurosymbolic_analysis(["not", "a", "mapping"])  # type: ignore[arg-type]
    assert malformed["status"] == "refused"
    assert malformed["code"] == "malformed_input"
    assert malformed["legal_sufficiency"] is False
    assert malformed["provider_invoked"] is False
