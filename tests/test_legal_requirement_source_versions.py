"""Source-bound legal rule candidates and verified requirement promotion."""

from __future__ import annotations

import pytest
from unittest.mock import Mock

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

from complaint_phases.legal_graph import LegalGraphBuilder
from integrations.ipfs_datasets.logic import (
    evaluate_temporal_requirement_applicability,
    extract_source_bound_rule_candidates,
    is_applicable_legal_requirement,
    legacy_unverified_requirement_templates,
    sha256_utf8,
)
from mediator.legal_authority_hooks import gate_rule_use_by_temporal_authority


def _authority(text: str, **overrides):
    payload = {
        "source_text": text,
        "jurisdiction": "US-OR",
        "authority_id": "ors:659A.030",
        "citation": "ORS 659A.030",
        "authority_version": "2024-edition",
        "source_hash": sha256_utf8(text),
        "effective_date": "2024-01-01",
        "as_of_date": "2024-06-01",
    }
    payload.update(overrides)
    return payload


def _promoted(text: str, **overrides):
    result = extract_source_bound_rule_candidates(_authority(text, **overrides))
    promoted = result["promoted_requirements"]
    assert len(promoted) == 1
    return promoted[0], result


def test_claim_keyword_templates_stay_unverified_and_inapplicable():
    templates = legacy_unverified_requirement_templates(["employment_discrimination"])
    assert [item["name"] for item in templates] == [
        "Protected Class Membership",
        "Adverse Action",
        "Causal Connection",
    ]
    assert all(item["verification_status"] == "unverified_template" for item in templates)
    assert all(item["applicable"] is False for item in templates)
    assert all(not is_applicable_legal_requirement(item) for item in templates)

    graph = LegalGraphBuilder().build_from_statutes(
        [{"name": "Title VII", "citation": "42 USC 2000e", "description": "discrimination"}],
        ["discrimination"],
    )
    requirements = graph.get_elements_by_type("legal_requirement")
    assert requirements
    assert all(element.attributes["verification_status"] == "unverified_template" for element in requirements)
    assert graph.get_requirements_for_claim_type("discrimination") == []

    procedural = LegalGraphBuilder().build_rules_of_procedure()
    nodes = procedural.get_elements_by_type("procedural_requirement")
    assert nodes
    assert all(node.attributes["template_kind"] == "procedural_template" for node in nodes)
    assert all(not is_applicable_legal_requirement(node.attributes) for node in nodes)


def test_complete_coordinates_promote_exact_span_and_ignore_caller_flags():
    text = "An employer shall not retaliate against an employee for opposing an unlawful practice."
    promoted, result = _promoted(text, promoted=True, applicable=True, verification_status="promoted")
    span = promoted["source_span"]
    raw = text.encode("utf-8")
    assert raw[span["start"]:span["end"]].decode("utf-8") == text
    assert promoted["span_sha256"] == sha256_utf8(text)
    assert promoted["source_hash"] == sha256_utf8(text)
    assert promoted["jurisdiction"] == "US-OR"
    assert promoted["authority_identity"] == "ors:659A.030"
    assert promoted["authority_version"] == "2024-edition"
    assert promoted["applicable_date"]["effective_date"] == "2024-01-01"
    assert promoted["applicable_date"]["as_of_date"] == "2024-06-01"
    assert promoted["structure"]["deontic_operator"] == "prohibition"
    assert promoted["structure"]["rule_character"] == "substantive"
    assert promoted["deontic_operator_is_proof"] is False
    assert result["candidate_count"] == 1


def test_missing_version_date_hash_or_jurisdiction_stays_candidate():
    text = "An employer shall not retaliate against an employee."
    cases = [
        {"authority_version": ""},
        {"effective_date": "", "as_of_date": ""},
        {"source_hash": ""},
        {"jurisdiction": "unknown"},
        {"authority_id": "", "citation": ""},
        {"source_hash": sha256_utf8("different text")},
    ]
    expected = [
        "missing_authority_version",
        "missing_applicable_date",
        "missing_source_hash",
        "missing_jurisdiction",
        "missing_authority_identity",
        "source_hash_mismatch",
    ]
    for overrides, reason in zip(cases, expected):
        result = extract_source_bound_rule_candidates(_authority(text, **overrides))
        assert result["promoted_count"] == 0
        assert reason in result["candidates"][0]["review_reasons"]
        assert result["candidates"][0]["applicable"] is False


def test_unicode_span_is_utf8_bytes_and_repeated_text_is_ambiguous():
    text = "An employer shall not retaliate against José."
    promoted, _ = _promoted(text)
    span = promoted["source_span"]
    assert span["end"] - span["start"] == len(text.encode("utf-8"))
    assert span["end"] - span["start"] != len(text)

    repeated = text + " " + text
    result = extract_source_bound_rule_candidates(_authority(repeated))
    assert result["promoted_count"] == 0
    assert result["candidates"][0]["review_reason"].find("ambiguous_source_span") >= 0
    assert len(result["candidates"]) == 1


def test_conditions_exceptions_and_connectives_are_preserved():
    conditional = (
        "If an employee opposes an unlawful practice, an employer shall not retaliate, "
        "except when the opposition is unlawful."
    )
    promoted, _ = _promoted(conditional)
    structure = promoted["structure"]
    assert structure["conditions"][0]["text"] == "an employee opposes an unlawful practice"
    assert structure["conditions"][0]["span_status"] == "exact"
    assert structure["exceptions"][0]["text"].startswith("except when")
    assert structure["rule_character"] == "substantive"
    assert structure["connective"] == "none"

    conjunction = "A charge shall be filed within 180 days and a notice shall be filed within 10 days."
    joined, _ = _promoted(conjunction)
    assert joined["structure"]["connective"] == "conjunction"
    assert joined["structure"]["rule_character"] == "procedural"
    assert len(joined["structure"]["conjuncts"]) == 2

    disjunction = "A party shall file a notice or a party shall file a statement of the delay."
    either, _ = _promoted(disjunction)
    assert either["structure"]["connective"] == "disjunction"
    assert either["rule_character"] == "procedural"
    assert len(either["structure"]["disjuncts"]) == 2

    mixed = (
        "An employer shall not retaliate against an employee, "
        "except that a charge shall be filed within 180 days."
    )
    mixed_rule, _ = _promoted(mixed)
    assert mixed_rule["structure"]["rule_character"] == "mixed"
    assert mixed_rule["structure"]["exceptions"]

    ambiguous = "A party shall file a notice and serve it or shall state the reason."
    result = extract_source_bound_rule_candidates(_authority(ambiguous))
    assert result["promoted_count"] == 0
    assert "ambiguous_connective" in result["candidates"][0]["review_reasons"]
    assert result["candidates"][0]["structure"]["conjunction_count"] == 1
    assert result["candidates"][0]["structure"]["disjunction_count"] == 1


def test_unsupported_sentence_and_span_mismatch_remain_candidates():
    narrative = "This chapter discusses employment."
    result = extract_source_bound_rule_candidates(_authority(narrative))
    assert result["promoted_count"] == 0
    assert "unsupported_deontic_extraction" in result["candidates"][0]["review_reasons"]

    text = "An employer shall not retaliate against an employee."
    mismatched = _authority(text, rule_text=text, source_span={"start": 1, "end": 4, "text": text})
    result = extract_source_bound_rule_candidates(mismatched)
    assert "source_span_mismatch" in result["candidates"][0]["review_reasons"]

    legacy = _authority(text, legacy_template=True, template_kind="claim_keyword_template")
    result = extract_source_bound_rule_candidates(legacy)
    assert result["promoted_count"] == 0
    assert "legacy_unverified_template" in result["candidates"][0]["review_reasons"]


def test_passage_hash_scope_promotes_when_span_bytes_match():
    text = "Intro. An employer shall not retaliate against an employee."
    rule = "An employer shall not retaliate against an employee."
    result = extract_source_bound_rule_candidates(_authority(
        text,
        rule_text=rule,
        source_hash=sha256_utf8(rule),
        content_hash_scope="source_passage",
    ))
    assert result["promoted_count"] == 1
    promoted = result["promoted_requirements"][0]
    assert promoted["source_hash_scope"] == "source_passage"
    assert promoted["span_sha256"] == sha256_utf8(rule)
    raw = text.encode("utf-8")
    span = promoted["source_span"]
    assert raw[span["start"]:span["end"]].decode("utf-8") == rule


def test_graph_promotion_keeps_candidate_distinct_from_requirement():
    text = "An employer shall not retaliate against an employee for opposing an unlawful practice."
    graph = LegalGraphBuilder().build_from_statutes(
        [{
            "name": "ORS 659A.030",
            "citation": "ORS 659A.030",
            "jurisdiction": "US-OR",
            "text": text,
            "authority_id": "ors:659A.030",
            "authority_version": "2024-edition",
            "source_hash": sha256_utf8(text),
            "effective_date": "2024-01-01",
            "as_of_date": "2024-06-01",
        }],
        ["retaliation"],
    )
    promoted = [
        element for element in graph.get_elements_by_type("legal_requirement")
        if element.attributes.get("promotion_status") == "promoted"
    ]
    assert len(promoted) == 1
    assert is_applicable_legal_requirement(promoted[0].attributes)
    span = promoted[0].attributes["source_span"]
    assert text.encode("utf-8")[span["start"]:span["end"]].decode("utf-8") == text
    assert graph.get_requirements_for_claim_type("discrimination") == []
    assert graph.get_requirements_for_claim_type("retaliation") == promoted

    authority_graph = LegalGraphBuilder().build_from_authorities([{
        "authority_id": "ors:659A.030",
        "name": "ORS 659A.030",
        "citation": "ORS 659A.030",
        "jurisdiction": "US-OR",
        "authority_version": "2024-edition",
        "source_text": text,
        "source_hash": sha256_utf8(text),
        "effective_date": "2024-01-01",
        "as_of_date": "2024-06-01",
        "claim_type": "retaliation",
        "rule_candidates": [{"rule_text": text, "rule_type": "prohibition", "claim_element_id": "element-1"}],
    }], claim_elements=[{"element_id": "element-1", "element_text": "retaliation"}])
    rule = next(element for element in authority_graph.elements.values() if element.element_type == "rule_candidate")
    requirement = next(
        element for element in authority_graph.elements.values()
        if element.element_type == "legal_requirement" and element.attributes.get("promoted") is True
    )
    assert rule.attributes["applicable"] is False
    assert requirement.attributes["authority_version"] == "2024-edition"
    assert requirement.attributes["source_hash"] == sha256_utf8(text)
    assert any(rel.relation_type == "promoted_from" for rel in authority_graph.relations.values())
    assert authority_graph.get_requirements_for_claim_type("retaliation") == [requirement]


_RULE = "An employer shall not retaliate against an employee for opposing an unlawful practice."


def _version_authority(version_id: str, *, version: str, effective: str, as_of: str = "2024-06-01", **extra):
    payload = _authority(
        _RULE,
        authority_version=version,
        law_version_id=version_id,
        effective_date=effective,
        as_of_date=as_of,
        law_versions=[{
            "law_version_id": version_id,
            "version": version,
            "effective_date": effective,
            "jurisdiction": extra.pop("jurisdiction", "US-OR"),
            "sunset_date": extra.pop("sunset_date", ""),
            "repeal_date": extra.pop("repeal_date", ""),
            "superseded_date": extra.pop("superseded_date", ""),
        }],
    )
    payload.update(extra)
    return payload


def test_temporal_fixtures_distinguish_version_dispositions():
    cases = {
        "effective": _version_authority("v-effective", version="2024-edition", effective="2024-01-01"),
        "future": _version_authority(
            "v-future", version="2026-edition", effective="2026-01-01", as_of="2024-06-01",
        ),
        "expired": _version_authority(
            "v-expired", version="2020-edition", effective="2020-01-01", sunset_date="2023-01-01",
        ),
        "repealed": _version_authority(
            "v-repealed", version="2018-edition", effective="2018-01-01", repeal_date="2022-01-01",
        ),
        "superseded": _version_authority(
            "v-superseded", version="2019-edition", effective="2019-01-01", superseded_date="2023-06-01",
        ),
    }
    amended = _version_authority("v-old", version="2019-edition", effective="2019-01-01")
    amended["law_versions"].append({
        "law_version_id": "v-new",
        "version": "2024-edition",
        "effective_date": "2024-01-01",
        "jurisdiction": "US-OR",
    })
    amended["changes"] = [{
        "change_kind": "amendment",
        "target_law_version_id": "v-old",
        "replacement_law_version_id": "v-new",
        "effective_date": "2024-01-01",
    }]
    cases["amended"] = amended
    mismatch = _version_authority("v-effective", version="2024-edition", effective="2024-01-01")
    mismatch["query_context"] = {"query_date": "2024-06-01", "jurisdiction": "US-CA", "law_version_id": "v-effective"}
    cases["wrong_jurisdiction"] = mismatch

    expected = {
        "effective": "effective",
        "future": "future",
        "expired": "expired",
        "amended": "amended",
        "repealed": "repealed",
        "superseded": "superseded",
        "wrong_jurisdiction": "wrong_jurisdiction",
    }
    for name, authority in cases.items():
        decision = evaluate_temporal_requirement_applicability(authority)
        gated = gate_rule_use_by_temporal_authority(authority)
        assert decision["applicability_status"] == expected[name]
        assert decision["guessed_current_rule"] is False
        assert gated["applicability_status"] == expected[name]
        assert gated["guessed_current_rule"] is False
        assert (decision["applicable"] is True) is (name == "effective")
        if name != "effective":
            result = extract_source_bound_rule_candidates(authority)
            assert result["promoted_count"] == 0
            assert result["candidates"][0]["temporal_applicability"]["applicability_status"] == expected[name]


def test_unknown_version_or_date_is_unavailable_and_not_the_current_rule():
    current = {
        "law_version_id": "v-current",
        "version": "2024-edition",
        "effective_date": "2024-01-01",
        "jurisdiction": "US-OR",
    }
    unknown_version = _authority(
        _RULE,
        authority_version="current",
        as_of_date="2024-06-01",
        law_versions=[current],
    )
    decision = evaluate_temporal_requirement_applicability(unknown_version)
    assert decision["applicability_status"] == "unavailable"
    assert decision["reason"] == "unknown_source_version"
    assert decision["available"] is False
    assert decision["applicable"] is False
    assert decision["guessed_current_rule"] is False
    assert decision["selected_current_rule"] is False
    assert decision.get("law_version_id", "") != "v-current"
    assert "v-current" not in {item.get("law_version_id") for item in decision["decisions"]}

    unknown_date = _authority(_RULE, authority_version="2024-edition", effective_date="", as_of_date="")
    decision = evaluate_temporal_requirement_applicability(unknown_date)
    assert decision["applicability_status"] == "unavailable"
    assert decision["reason"] == "unknown_source_date"
    assert decision["query_date_source"] == "unavailable"
    assert decision["guessed_current_rule"] is False
    gated = gate_rule_use_by_temporal_authority(unknown_date)
    assert gated["support_eligible"] is False
    assert gated["available"] is False


def test_adverse_and_unconfirmed_treatment_stay_visible_and_block_support():
    text = _RULE
    for treatment_type in ("adverse", "good_law_unconfirmed"):
        authority = _authority(
            text,
            authority_treatment_edges=[{
                "source_authority_id": "case:1",
                "target_authority_id": "ors:659A.030",
                "relation_type": treatment_type,
                "explanation": "synthetic treatment",
            }],
        )
        result = extract_source_bound_rule_candidates(authority)
        candidate = result["candidates"][0]
        assert candidate["promoted"] is True
        assert candidate["support_eligible"] is False
        assert candidate["treatment_edges"][0]["treatment_type"] == treatment_type
        assert not is_applicable_legal_requirement(candidate)
        gated = gate_rule_use_by_temporal_authority(authority)
        assert gated["treatment_edges_visible"] is True
        assert gated["treatment_edges"][0]["treatment_type"] == treatment_type
        assert gated["support_eligible"] is False
        assert treatment_type in gated["blocking_treatments"]

        graph = LegalGraphBuilder().build_from_authorities([
            {
                "authority_id": "ors:659A.030",
                "name": "ORS 659A.030",
                "citation": "ORS 659A.030",
                "jurisdiction": "US-OR",
                "authority_version": "2024-edition",
                "source_text": text,
                "source_hash": sha256_utf8(text),
                "effective_date": "2024-01-01",
                "as_of_date": "2024-06-01",
                "claim_type": "retaliation",
                "authority_treatment_edges": [{
                    "source_authority_id": "case:1",
                    "target_authority_id": "ors:659A.030",
                    "relation_type": treatment_type,
                }],
                "rule_candidates": [{"rule_text": text, "rule_type": "prohibition"}],
            },
            {
                "authority_id": "case:1",
                "name": "Synthetic treatment case",
                "citation": "1 F. Supp. 1",
                "jurisdiction": "US-OR",
            },
        ])
        relations = [rel for rel in graph.relations.values() if rel.relation_type == treatment_type]
        assert relations
        requirement = next(
            element for element in graph.elements.values()
            if element.element_type == "legal_requirement" and element.attributes.get("promoted") is True
        )
        assert requirement.attributes["support_eligible"] is False
        assert treatment_type in requirement.attributes["visible_treatment_types"]
        assert graph.get_requirements_for_claim_type("retaliation") == []


@pytest.mark.parametrize("mismatch", ["sole_other_version", "explicit_id_other_version", "requested_other_version"])
def test_temporal_admission_never_substitutes_a_different_source_version(monkeypatch, mismatch):
    from integrations.ipfs_datasets import logic
    authority = _version_authority("v-source", version="2024-edition", effective="2024-01-01")
    if mismatch == "requested_other_version":
        authority["query_context"] = {"version": "2023-edition", "query_date": "2024-06-01"}
    else:
        authority["law_versions"][0]["version"] = "2023-edition"
        if mismatch == "explicit_id_other_version":
            authority["query_context"] = {"law_version_id": "v-source", "query_date": "2024-06-01"}
    called = Mock(side_effect=AssertionError("mismatched source must not enter LegalIR"))
    monkeypatch.setattr(logic, "_temporal_authority_api", called)
    decision = evaluate_temporal_requirement_applicability(authority)
    assert decision["available"] is False and decision["applicable"] is False
    assert decision["applicability_status"] == "unavailable"
    assert decision["guessed_current_rule"] is False and decision["decisions"] == []
    assert extract_source_bound_rule_candidates(authority)["promoted_count"] == 0
    called.assert_not_called()


@pytest.mark.parametrize("date_field,value", [
    ("effective_date", ""), ("effective_date", "unknown"),
    ("effective_date", "2024-02-30"), ("effective_date", "2024-13-01"),
    ("sunset_date", "2024-02-30"), ("repeal_date", "not-a-date"),
    ("superseded_date", "2024-99-01"),
])
def test_temporal_admission_rejects_missing_or_impossible_source_dates(monkeypatch, date_field, value):
    from integrations.ipfs_datasets import logic
    authority = _version_authority("v-source", version="2024-edition", effective="2024-01-01")
    authority["law_versions"][0][date_field] = value
    if date_field == "effective_date":
        authority["effective_date"] = value
    called = Mock(side_effect=AssertionError("invalid source dates must not enter LegalIR"))
    monkeypatch.setattr(logic, "_temporal_authority_api", called)
    decision = evaluate_temporal_requirement_applicability(authority)
    assert decision["available"] is False and decision["applicable"] is False
    assert decision["applicability_status"] == "unavailable"
    assert decision["guessed_current_rule"] is False
    assert extract_source_bound_rule_candidates(authority)["promoted_count"] == 0
    called.assert_not_called()


@pytest.mark.parametrize("conflict", ["query_aliases", "source_context", "end_before_start", "change_date"])
def test_temporal_admission_rejects_contradictory_or_invalid_date_context(monkeypatch, conflict):
    from integrations.ipfs_datasets import logic
    authority = _version_authority("v-source", version="2024-edition", effective="2024-01-01")
    if conflict == "query_aliases":
        authority["query_context"] = {"query_date": "2024-06-01", "as_of_date": "2025-06-01"}
    elif conflict == "source_context":
        authority["date_context"] = {"effective_date": "2023-01-01"}
    elif conflict == "end_before_start":
        authority["law_versions"][0]["sunset_date"] = "2023-01-01"
    else:
        authority["changes"] = [{"change_kind": "repeal", "target_law_version_id": "v-source", "effective_date": "2024-02-30"}]
    called = Mock(side_effect=AssertionError("contradictory context must not enter LegalIR"))
    monkeypatch.setattr(logic, "_temporal_authority_api", called)
    decision = evaluate_temporal_requirement_applicability(authority)
    assert decision["available"] is False and decision["applicable"] is False
    assert decision["reason"] in {"contradictory_date_context", "invalid_source_date"}
    assert extract_source_bound_rule_candidates(authority)["promoted_count"] == 0
    called.assert_not_called()


@pytest.mark.parametrize("failure", ["build", "query", "serialization"])
def test_temporal_api_exceptions_are_typed_unavailable_without_error_payload(monkeypatch, failure):
    from types import SimpleNamespace
    from integrations.ipfs_datasets import logic
    module, error = logic._temporal_authority_api()
    assert module is not None and error == ""
    marker = "SYNTHETIC-PRIVATE-TEMPORAL-ERROR-MARKER"
    def fail(*args, **kwargs):
        raise RuntimeError(marker)
    api = SimpleNamespace(
        build_legal_ir_temporal_authority_graph=module.build_legal_ir_temporal_authority_graph,
        query_legal_ir_temporal_applicability=module.query_legal_ir_temporal_applicability,
        LegalIRTemporalQueryContext=module.LegalIRTemporalQueryContext,
    )
    if failure == "build":
        api.build_legal_ir_temporal_authority_graph = fail
    elif failure == "query":
        api.query_legal_ir_temporal_applicability = fail
    else:
        api.query_legal_ir_temporal_applicability = lambda *args, **kwargs: SimpleNamespace(to_dict=fail)
    monkeypatch.setattr(logic, "_temporal_authority_api", lambda: (api, ""))
    authority = _authority(_RULE)
    decision = evaluate_temporal_requirement_applicability(authority)
    assert decision["available"] is False and decision["applicable"] is False
    assert decision["reason"] == "temporal_authority_evaluation_failed"
    assert decision["diagnostic"] == "legal_ir_temporal_api_failure"
    assert marker not in str(decision)
    result = extract_source_bound_rule_candidates(authority)
    assert result["promoted_count"] == 0 and not is_applicable_legal_requirement(result["candidates"][0])
    assert marker not in str(result)


@pytest.mark.parametrize("bound", ["versions", "changes", "source_text", "rule_count"])
def test_temporal_input_bounds_refuse_before_api_dispatch(monkeypatch, bound):
    from integrations.ipfs_datasets import logic
    authority = _version_authority("v-source", version="2024-edition", effective="2024-01-01")
    if bound == "versions":
        authority["law_versions"] *= logic._TEMPORAL_MAX_VERSIONS + 1
    elif bound == "changes":
        authority["changes"] = [{"change_kind": "repeal"}] * (logic._TEMPORAL_MAX_CHANGES + 1)
    else:
        text = "X" * (logic._TEMPORAL_MAX_TEXT + 1) if bound == "source_text" else "An employer shall preserve records. " * (logic._TEMPORAL_MAX_RULES + 1)
        authority["source_text"] = text
        authority["source_hash"] = sha256_utf8(text)
    called = Mock(side_effect=AssertionError("over-bound authority must not enter LegalIR"))
    monkeypatch.setattr(logic, "_temporal_authority_api", called)
    result = extract_source_bound_rule_candidates(authority)
    assert result["promoted_count"] == 0 and result["candidate_count"] == 1
    candidate = result["candidates"][0]
    assert candidate["temporal_applicability"]["available"] is False
    assert "bound_exceeded" in candidate["temporal_applicability"]["reason"]
    assert candidate["support_eligible"] is False and candidate["applicable"] is False
    called.assert_not_called()


def test_real_temporal_api_accepts_exact_historical_version_and_valid_leap_date():
    authority = _version_authority("v-historical", version="2020-edition", effective="2020-02-29", as_of="2020-06-01")
    authority["query_context"] = {"law_version_id": "v-historical", "version": "2020-edition", "query_date": "2020-06-01"}
    decision = evaluate_temporal_requirement_applicability(authority)
    assert decision["available"] is True and decision["applicable"] is True
    assert decision["authority_version"] == "2020-edition" and decision["law_version_id"] == "v-historical"
    assert decision["effective_date"] == "2020-02-29" and decision["query_date"] == "2020-06-01"
    assert decision["guessed_current_rule"] is False
    assert extract_source_bound_rule_candidates(authority)["promoted_count"] == 1


def test_real_temporal_api_preserves_explicit_source_expiration_for_selected_version():
    authority = _version_authority("v-source", version="2024-edition", effective="2024-01-01")
    authority["expiration_date"] = "2024-05-01"
    decision = evaluate_temporal_requirement_applicability(authority)
    assert decision["available"] is True and decision["applicable"] is False
    assert decision["applicability_status"] == "expired" and decision["end_date"] == "2024-05-01"
    assert extract_source_bound_rule_candidates(authority)["promoted_count"] == 0


def test_temporal_graph_evaluation_is_once_per_authority_with_detached_candidate_results(monkeypatch):
    from integrations.ipfs_datasets import logic
    authority = _authority("An employer shall preserve records. An employee may inspect copies.")
    real = logic.evaluate_temporal_requirement_applicability
    calls = []
    def observe(payload, query_context=None):
        calls.append(payload["authority_version"])
        return real(payload, query_context=query_context)
    monkeypatch.setattr(logic, "evaluate_temporal_requirement_applicability", observe)
    result = extract_source_bound_rule_candidates(authority)
    assert calls == ["2024-edition"]
    assert result["candidate_count"] == result["promoted_count"] == 2
    first, second = result["candidates"]
    assert first["temporal_applicability"] is not second["temporal_applicability"]
    first["temporal_applicability"]["applicable"] = False
    assert second["temporal_applicability"]["applicable"] is True


@pytest.mark.parametrize("query_date", ["", "unknown"])
def test_temporal_query_date_is_not_guessed_from_the_source_effective_date(monkeypatch, query_date):
    from integrations.ipfs_datasets import logic
    authority = _authority(_RULE, as_of_date=query_date)
    called = Mock(side_effect=AssertionError("an unknown query date must not select the source start date"))
    monkeypatch.setattr(logic, "_temporal_authority_api", called)
    decision = evaluate_temporal_requirement_applicability(authority)
    assert decision["available"] is False and decision["applicable"] is False
    assert decision["query_date_source"] == "unavailable"
    assert decision["guessed_current_rule"] is False
    assert extract_source_bound_rule_candidates(authority)["promoted_count"] == 0
    called.assert_not_called()


@pytest.mark.parametrize("container,field", [
    ("metadata", "source_text"), ("metadata", "text"), ("metadata", "rule_text"),
    ("provenance", "source_text"), ("provenance", "text"), ("provenance", "rule_text"),
    ("date_context", "source_text"), ("applicable_date", "source_text"),
    ("temporal_window", "source_text"),
])
def test_nested_temporal_source_text_limits_precede_coordinate_extraction(monkeypatch, container, field):
    from integrations.ipfs_datasets import logic
    authority = _authority(_RULE)
    authority[container] = {field: "X" * (logic._TEMPORAL_MAX_TEXT + 1)}
    original_coordinates = logic._authority_coordinates
    coordinates = Mock(side_effect=AssertionError("over-bound nested source must not be normalized"))
    api = Mock(side_effect=AssertionError("over-bound nested source must not enter LegalIR"))
    monkeypatch.setattr(logic, "_authority_coordinates", coordinates)
    monkeypatch.setattr(logic, "_temporal_authority_api", api)
    decision = evaluate_temporal_requirement_applicability(authority)
    assert decision["reason"] == "source_text_bound_exceeded"
    assert decision["available"] is False and decision["applicable"] is False
    coordinates.assert_not_called()
    monkeypatch.setattr(logic, "_authority_coordinates", original_coordinates)
    result = extract_source_bound_rule_candidates(authority)
    assert result["promoted_count"] == 0
    assert result["candidates"][0]["support_eligible"] is False
    coordinates.assert_not_called()
    api.assert_not_called()


@pytest.mark.parametrize("container,field", [
    ("metadata", "id"), ("provenance", "corpus_version"),
    ("date_context", "cite"), ("applicable_date", "release"),
])
def test_nested_temporal_identity_limits_precede_coordinate_extraction(monkeypatch, container, field):
    from integrations.ipfs_datasets import logic
    authority = _authority(_RULE)
    authority[container] = {field: "X" * 1025}
    original_coordinates = logic._authority_coordinates
    coordinates = Mock(side_effect=AssertionError("over-bound nested identity must not be normalized"))
    monkeypatch.setattr(logic, "_authority_coordinates", coordinates)
    decision = evaluate_temporal_requirement_applicability(authority)
    assert decision["reason"] == "authority_field_bound_exceeded"
    assert decision["available"] is False and decision["applicable"] is False
    coordinates.assert_not_called()
    monkeypatch.setattr(logic, "_authority_coordinates", original_coordinates)
    assert extract_source_bound_rule_candidates(authority)["promoted_count"] == 0
    coordinates.assert_not_called()


@pytest.mark.parametrize("location", ["effective_date", "provenance_expiration", "query_date"])
def test_temporal_dates_reject_oversized_raw_strings_before_whitespace_normalization(monkeypatch, location):
    from integrations.ipfs_datasets import logic
    authority = _version_authority("v-source", version="2024-edition", effective="2024-01-01")
    padded_date = " " * 65 + "2024-06-01"
    if location == "effective_date":
        authority["effective_date"] = padded_date
    elif location == "provenance_expiration":
        authority["provenance"] = {"expiration_date": padded_date}
    else:
        authority["query_context"] = {"query_date": padded_date}
    api = Mock(side_effect=AssertionError("oversized raw date must not enter LegalIR"))
    monkeypatch.setattr(logic, "_temporal_authority_api", api)
    decision = evaluate_temporal_requirement_applicability(authority)
    assert decision["reason"] == "invalid_source_date"
    assert decision["available"] is False and decision["applicable"] is False
    assert extract_source_bound_rule_candidates(authority)["promoted_count"] == 0
    api.assert_not_called()


def test_temporal_date_parser_never_stringifies_non_string_input():
    from integrations.ipfs_datasets import logic
    class NotADate:
        def __str__(self):
            raise AssertionError("date parser must not stringify arbitrary input")
    assert logic._iso_date(NotADate()) == ""
    assert logic._iso_date(" " * 65 + "2024-02-29") == ""
    assert logic._iso_date("2024-02-29") == "2024-02-29"


def test_actual_statute_builder_does_not_invent_missing_jurisdiction():
    text = "An employer shall not retaliate against an employee."
    statute = _authority(text)
    del statute["jurisdiction"]

    graph = LegalGraphBuilder().build_from_statutes([statute], ["retaliation"])

    source = graph.get_elements_by_type("statute")[0]
    candidate = graph.get_elements_by_type("rule_candidate")[0]
    assert source.jurisdiction == ""
    assert candidate.attributes["source_hash"] == sha256_utf8(text)
    assert candidate.attributes["source_span"]["text"] == text
    assert candidate.attributes["authority_version"] == "2024-edition"
    assert "missing_jurisdiction" in candidate.attributes["review_reasons"]
    assert candidate.attributes["applicable"] is False
    assert graph.get_elements_by_type("legal_requirement") == []
    assert graph.get_requirements_for_claim_type("retaliation") == []


@pytest.mark.parametrize("candidate_text_field", ["rule_text", "text"])
def test_authority_candidate_cannot_promote_an_unrelated_source_sentence(candidate_text_field):
    source_text = "An employer shall preserve records."
    candidate_text = "An employer may destroy records."
    authority = _authority(source_text)
    authority.update({
        "claim_type": "retaliation",
        "rule_candidates": [{candidate_text_field: candidate_text}],
    })

    graph = LegalGraphBuilder().build_from_authorities([authority])

    candidate = graph.get_elements_by_type("rule_candidate")[0]
    assert candidate.description == candidate_text
    assert candidate.attributes["promoted_to_requirement"] is False
    assert "missing_source_span" in candidate.attributes["review_reasons"]
    assert candidate.attributes["applicable"] is False
    assert graph.get_elements_by_type("legal_requirement") == []
    assert graph.get_requirements_for_claim_type("retaliation") == []
    assert not any(edge.relation_type == "promoted_from" for edge in graph.relations.values())


@pytest.mark.parametrize("candidate_text_field", ["rule_text", "text"])
def test_authority_candidate_rejects_a_mismatched_exact_source_span(candidate_text_field):
    source_text = "An employer shall not retaliate against José."
    authority = _authority(source_text)
    authority.update({
        "claim_type": "retaliation",
        "rule_candidates": [{
            candidate_text_field: source_text,
            "source_span": {"start": 1, "end": len(source_text.encode("utf-8")), "text": source_text},
        }],
    })

    graph = LegalGraphBuilder().build_from_authorities([authority])

    candidate = graph.get_elements_by_type("rule_candidate")[0]
    assert candidate.description == source_text
    assert candidate.attributes["promoted_to_requirement"] is False
    assert "source_span_mismatch" in candidate.attributes["review_reasons"]
    assert candidate.attributes["applicable"] is False
    assert graph.get_elements_by_type("legal_requirement") == []
    assert graph.get_requirements_for_claim_type("retaliation") == []
    assert not any(edge.relation_type == "promoted_from" for edge in graph.relations.values())


def test_exact_legacy_text_candidate_promotes_its_own_second_utf8_source_span():
    rule_text = "An employer shall not retaliate against José."
    prefix = "An employer shall preserve records. "
    source_text = prefix + rule_text
    start = len(prefix.encode("utf-8"))
    end = start + len(rule_text.encode("utf-8"))
    authority = _authority(source_text)
    authority.update({
        "claim_type": "retaliation",
        "rule_candidates": [{
            "text": rule_text,
            "source_span": {"start": start, "end": end, "text": rule_text, "unit": "utf-8-bytes"},
        }],
    })

    graph = LegalGraphBuilder().build_from_authorities([authority])

    requirement = graph.get_elements_by_type("legal_requirement")[0]
    candidate = graph.get_elements_by_type("rule_candidate")[0]
    span = requirement.attributes["source_span"]
    assert requirement.description == rule_text == candidate.description
    assert span == {"start": start, "end": end, "text": rule_text, "unit": "utf-8-bytes"}
    assert source_text.encode("utf-8")[start:end].decode("utf-8") == rule_text
    assert requirement.attributes["source_hash"] == sha256_utf8(source_text)
    assert requirement.attributes["span_sha256"] == sha256_utf8(rule_text)
    assert requirement.attributes["authority_version"] == "2024-edition"
    assert requirement.jurisdiction == "US-OR"
    assert candidate.attributes["applicable"] is False
    assert candidate.attributes["promoted_to_requirement"] is True
    assert graph.get_requirements_for_claim_type("retaliation") == [requirement]
    assert any(edge.relation_type == "promoted_from" and edge.source_id == requirement.id
               and edge.target_id == candidate.id for edge in graph.relations.values())
