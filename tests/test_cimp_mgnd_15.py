"""Acquisition plans bind to explicit legal context.

Cases are synthetic private fixtures. No test is skipped. A request is built
only after jurisdiction, applicable-law date, and a supported claim are
explicit. Unknown context returns a targeted inquiry and does not fetch.
"""

from __future__ import annotations

import json

import pytest

from integrations.ipfs_datasets.legal import (
    build_bounded_legal_acquisition_request,
    empty_legal_context,
)
from mediator.mediator import Mediator
from tests.mgnd_fixtures import CASE_LABELS, meaningful_cases


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

_SEARCH_FLAGS = (
    "search_us_code",
    "search_federal_register",
    "search_state_laws",
    "search_state_administrative_rules",
    "search_case_law",
)


def _case_file(case, **overrides):
    file_overrides = {
        "jurisdiction": "Oregon" if case.narrative.jurisdiction == "US-OR" else case.narrative.jurisdiction,
        "applicable_law_date": "2024-03-15",
        "event_date": case.narrative.event_date,
        "filing_reference_date": "2024-04-02",
        "corpus_retrieval_date": "2024-06-01",
    }
    file_overrides.update(overrides)
    return {
        "source_complaint_text": case.narrative.text,
        "candidate_claims": [{"claim_type": "termination", "name": "Termination"}],
        "legal_context_overrides": file_overrides,
        "canonical_facts": [],
    }


def _assert_dates_separated(result: dict) -> None:
    dates = result["dates"]
    assert set(dates) == {
        "event_date",
        "applicable_law_date",
        "filing_reference_date",
        "corpus_retrieval_date",
    }
    assert dates["event_date"]["role"] == "event_date"
    assert dates["applicable_law_date"]["role"] == "applicable_law_date"
    assert dates["filing_reference_date"]["role"] == "filing_reference_date"
    assert dates["corpus_retrieval_date"]["role"] == "corpus_retrieval_date"
    assert result["law_query_date_satisfies_factual_chronology"] is False
    law_day = dates["applicable_law_date"].get("precise_date")
    if result["factual_chronology_gap"]:
        assert dates["event_date"].get("precise_date") in {None, ""}
        assert law_day != dates["event_date"].get("precise_date") or law_day in {None, ""}
    assert dates["corpus_retrieval_date"].get("precise_date") != law_day or law_day in {None, ""}
    assert dates["filing_reference_date"].get("precise_date") != law_day or law_day in {None, ""}


def _assert_not_fetched(result: dict, case) -> None:
    encoded = json.dumps(result, sort_keys=True, default=str)
    assert case.narrative.text not in encoded
    assert result["contains_private_narrative"] is False
    assert result["narrative_required"] is False
    assert result["execution"]["attempted"] is False
    assert result["execution"]["backend_invoked"] is False
    assert result["execution"]["results_claimed"] is False
    assert result["execution"]["results"] is None
    assert result["execution"]["status"] in {"blocked", "not_executed", "unavailable"}
    assert result["corpus_plan"]["default_applied"] is False
    assert result["corpus_plan"]["guessed_jurisdiction"] is False


def test_meaningful_cases_drive_acquisition_binding():
    cases = meaningful_cases()
    assert cases
    assert tuple(case.label for case in cases) == CASE_LABELS
    mediator = Mediator.__new__(Mediator)
    seen = []
    for case in cases:
        if case.narrative.jurisdiction == "unknown":
            case_file = {
                "source_complaint_text": case.narrative.text,
                "candidate_claims": [{"claim_type": "termination", "name": "Termination"}],
                "canonical_facts": [],
            }
        else:
            event = case.narrative.event_date
            case_file = _case_file(case, event_date="" if case.label == "baseline" else event)
        result = mediator.build_legal_acquisition_request(
            case_file,
            query_terms=["termination statute"],
            jurisdiction_default="federal",
            corpus_default="us_code",
            storage_available=case.storage_available,
        )
        seen.append(case.label)
        _assert_not_fetched(result, case)
        _assert_dates_separated(result)
        assert result["rejected_defaults"] == {
            "jurisdiction_default": "federal",
            "corpus_default": "us_code",
        }
        if case.narrative.jurisdiction == "unknown":
            assert result["ready"] is False
            assert result["request"] is None
            assert result["jurisdiction"] == "unknown"
            assert result["execution"]["status"] == "blocked"
            assert any(item["reason"] == "unresolved_jurisdiction" for item in result["questions"])
            assert all(result["corpus_plan"][flag] is False for flag in _SEARCH_FLAGS)
        elif case.label == "baseline":
            assert result["ready"] is True
            assert result["factual_chronology_gap"] is True
            assert any(item["reason"] == "missing_event_dates" for item in result["questions"])
            request = result["request"]
            assert request["jurisdiction"] == "OR"
            assert request["law_query_date"] == "2024-03-15"
            assert request["dates"]["event_date"]["precise_date"] in {None, ""}
            assert request["dates"]["event_date"]["raw_text"] == ""
            assert request["claim_targets"][0]["claim_type"] == "termination"
            assert request["requirement_targets"]
            assert "termination statute" in request["public_law_query_terms"]
            assert request["program"]["contains_private_facts"] is False
            assert request["corpus_plan"]["search_state_laws"] is True
            assert request["corpus_plan"]["search_us_code"] is False
            assert result["execution"]["status"] == "not_executed"
        else:
            assert result["ready"] is True
            assert result["request"]["jurisdiction"] == "OR"
            assert result["factual_chronology_gap"] is False
            assert result["request"]["dates"]["event_date"]["precise_date"] == case.narrative.event_date
            assert result["law_query_date"] == "2024-03-15"
            assert result["request"]["dates"]["event_date"]["precise_date"] != result["law_query_date"]
            if case.storage_available is False:
                assert result["execution"]["status"] == "unavailable"
            else:
                assert result["execution"]["status"] == "not_executed"
    assert seen == list(CASE_LABELS)


def test_ambiguous_jurisdiction_uncertain_date_and_unsupported_claim_do_not_guess():
    mediator = Mediator.__new__(Mediator)
    ambiguous = mediator.build_legal_acquisition_request(
        {
            "source_complaint_text": "The forum was not chosen.",
            "candidate_claims": [{"claim_type": "termination"}],
            "legal_context_overrides": {
                "jurisdiction": "Oregon or Washington",
                "applicable_law_date": "2024-03-15",
                "event_date": "2024-03-04",
            },
        },
        jurisdiction_default="OR",
        corpus_default="state_statute",
    )
    assert ambiguous["ready"] is False
    assert ambiguous["request"] is None
    assert ambiguous["jurisdiction"] == "unknown"
    assert ambiguous["rejected_defaults"]["jurisdiction_default"] == "OR"
    assert all(ambiguous["corpus_plan"][flag] is False for flag in _SEARCH_FLAGS)
    assert any(item["reason"] == "unresolved_jurisdiction" for item in ambiguous["questions"])

    uncertain = build_bounded_legal_acquisition_request(
        {
            "jurisdiction": "federal",
            "applicable_law_date": "early March 2024",
            "event_date": "2024-03-04",
            "filing_reference_date": "2024-04-02",
            "corpus_retrieval_date": "2024-06-01",
        },
        [{"claim_type": "retaliation", "name": "Retaliation"}],
        query_terms=["retaliation statute"],
        corpus_default="us_code",
    )
    assert uncertain["ready"] is False
    assert uncertain["request"] is None
    assert uncertain["law_query_date"] in {None, ""}
    assert uncertain["dates"]["event_date"]["precise_date"] == "2024-03-04"
    assert uncertain["dates"]["corpus_retrieval_date"]["precise_date"] == "2024-06-01"
    assert uncertain["dates"]["applicable_law_date"]["is_uncertain"] is True
    assert any(item["reason"] == "uncertain_applicable_law_date" for item in uncertain["questions"])
    assert uncertain["corpus_plan"]["search_us_code"] is False
    assert uncertain["corpus_plan"]["jurisdiction"] == "federal"

    unsupported = build_bounded_legal_acquisition_request(
        {
            "jurisdiction": "OR",
            "applicable_law_date": "2024-03-15",
            "event_date": "2024-03-04",
        },
        [{"claim_type": "quantum_tort", "name": "Quantum tort"}],
        query_terms=["quantum tort narrative should not select a corpus"],
    )
    assert unsupported["ready"] is False
    assert unsupported["request"] is None
    assert "unsupported_claim" in unsupported["unresolved_reasons"]
    assert any(item["reason"] == "unsupported_claim" for item in unsupported["questions"])
    assert all(unsupported["corpus_plan"][flag] is False for flag in _SEARCH_FLAGS)

    direct = build_bounded_legal_acquisition_request(
        empty_legal_context(),
        [],
        narrative="On 2024-03-04 Alex Rivera ended the warehouse job.",
        jurisdiction_default="federal",
    )
    assert direct["ready"] is False
    assert direct["request"] is None
    assert "On 2024-03-04 Alex Rivera ended the warehouse job." not in json.dumps(direct)
    assert direct["factual_chronology_gap"] is True
    assert direct["law_query_date_satisfies_factual_chronology"] is False


def test_retrieval_date_does_not_fill_law_or_event_gaps():
    result = build_bounded_legal_acquisition_request(
        {
            "jurisdiction": "US-OR",
            "applicable_law_date": "",
            "event_date": "",
            "filing_reference_date": "March 2024",
            "corpus_retrieval_date": "2024-06-01",
        },
        [{"claim_type": "termination"}],
        query_terms=["termination statute"],
        narrative="private narrative that is not a citation query",
    )
    assert result["ready"] is False
    assert result["jurisdiction"] == "OR"
    assert result["law_query_date"] in {None, ""}
    assert result["dates"]["event_date"]["precise_date"] in {None, ""}
    assert result["dates"]["corpus_retrieval_date"]["precise_date"] == "2024-06-01"
    assert result["dates"]["filing_reference_date"]["precise_date"] in {None, ""}
    assert result["factual_chronology_gap"] is True
    assert result["law_query_date_satisfies_factual_chronology"] is False
    assert result["request"] is None
    encoded = json.dumps(result)
    assert "private narrative that is not a citation query" not in encoded
