"""Tests for M5 Legal Proof And Contradiction Engine.

Covers:
- get_element_proof_card: required/satisfied/missing predicates, proof state,
  contradiction sources, next action, explanation
- get_element_proof_cards: builds proof cards for all elements of a claim type
- proof state classification: supported, partially_supported, missing,
  contradicted, uncertain, exception_barred
- get_question_recommendations: now includes proof_state_context per recommendation
- API routes: /api/claim-support/element-proof-cards, /api/claim-support/element-proof-card
"""
from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.no_auto_network


def _make_minimal_mediator() -> MagicMock:
    mediator = MagicMock()
    mediator.log = MagicMock()
    mediator.get_three_phase_status = MagicMock(return_value={})
    state = MagicMock()
    state.username = "test_user"
    mediator.state = state
    return mediator


def _make_hooks(db_path: str = None):
    from mediator.claim_support_hooks import ClaimSupportHook
    if db_path is None:
        db_path = _tmp_db_path()
    return ClaimSupportHook(_make_minimal_mediator(), db_path=db_path)


def _tmp_db_path() -> str:
    f = tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False)
    f.close()
    os.unlink(f.name)
    return f.name


# ---------------------------------------------------------------------------
# get_element_proof_card: basic structure
# ---------------------------------------------------------------------------

def test_get_element_proof_card_returns_required_keys():
    hooks = _make_hooks()
    card = hooks.get_element_proof_card(
        "user1",
        "employment_discrimination",
        claim_element_id="adverse_action",
        claim_element_text="adverse action",
    )
    required_keys = {
        "claim_type",
        "claim_element_id",
        "claim_element_text",
        "proof_state",
        "required_predicates",
        "satisfied_predicates",
        "missing_predicates",
        "supporting_facts",
        "contradiction_sources",
        "next_action",
        "explanation",
        "supporting_fact_count",
        "confirmed_fact_count",
        "contradiction_count",
    }
    for key in required_keys:
        assert key in card, f"Missing key: {key}"


def test_get_element_proof_card_proof_state_is_valid():
    hooks = _make_hooks()
    card = hooks.get_element_proof_card(
        "user1",
        "employment_discrimination",
        claim_element_id="adverse_action",
        claim_element_text="adverse action",
    )
    valid_states = {
        "supported", "partially_supported", "missing",
        "contradicted", "uncertain", "exception_barred", "unvalidated",
    }
    assert card["proof_state"] in valid_states


def test_get_element_proof_card_missing_with_no_facts():
    """An element with no persisted facts should have proof_state 'missing'."""
    hooks = _make_hooks()
    card = hooks.get_element_proof_card(
        "user_no_facts",
        "employment_discrimination",
        claim_element_id="adverse_action",
        claim_element_text="adverse action",
    )
    assert card["proof_state"] == "missing"
    assert card["supporting_fact_count"] == 0
    assert card["next_action"] == "gather_evidence"


def test_get_element_proof_card_next_action_present():
    hooks = _make_hooks()
    card = hooks.get_element_proof_card(
        "user1",
        "employment_discrimination",
        claim_element_id="protected_class",
        claim_element_text="protected class",
    )
    valid_actions = {
        "resolve_contradiction",
        "address_exception",
        "gather_evidence",
        "validate_facts",
        "complete_proof",
        "no_action_needed",
    }
    assert card["next_action"] in valid_actions


def test_get_element_proof_card_explanation_is_non_empty():
    hooks = _make_hooks()
    card = hooks.get_element_proof_card(
        "user1",
        "employment_discrimination",
        claim_element_id="adverse_action",
        claim_element_text="adverse action",
    )
    assert isinstance(card["explanation"], str)
    assert len(card["explanation"]) > 0


def test_get_element_proof_card_required_predicates_are_list():
    hooks = _make_hooks()
    card = hooks.get_element_proof_card(
        "user1",
        "employment_discrimination",
        claim_element_id="adverse_action",
        claim_element_text="adverse action",
    )
    assert isinstance(card["required_predicates"], list)
    assert isinstance(card["satisfied_predicates"], list)
    assert isinstance(card["missing_predicates"], list)


def test_get_element_proof_card_missing_predicates_subset_of_required():
    hooks = _make_hooks()
    card = hooks.get_element_proof_card(
        "user1",
        "retaliation",
        claim_element_id="protected_activity",
        claim_element_text="protected activity",
    )
    # missing_predicates must be a subset of required_predicates
    for pred in card["missing_predicates"]:
        assert pred in card["required_predicates"], (
            f"missing predicate '{pred}' not in required_predicates"
        )


def test_get_element_proof_card_unknown_claim_type_degrades_gracefully():
    hooks = _make_hooks()
    card = hooks.get_element_proof_card(
        "user1",
        "unknown_claim_type_xyz",
        claim_element_id="some_element",
        claim_element_text="some element",
    )
    assert card["proof_state"] in {"missing", "unvalidated"}
    assert card["next_action"] in {"gather_evidence", "validate_facts"}


# ---------------------------------------------------------------------------
# get_element_proof_card: with persisted facts
# ---------------------------------------------------------------------------

def test_get_element_proof_card_with_confirmed_fact_is_not_missing():
    """After persisting a confirmed fact for an element, proof state should not be 'missing'."""
    db_path = _tmp_db_path()
    hooks = _make_hooks(db_path)
    user_id = "user_confirmed"
    claim_type = "employment_discrimination"
    element_id = "adverse_action"

    hooks.persist_fact_record(
        user_id=user_id,
        claim_type=claim_type,
        claim_element_id=element_id,
        claim_element_text="adverse action",
        proposition_text="Employer terminated complainant on March 15.",
        source_artifact_id="doc:001",
        confidence=0.9,
        validation_state="confirmed",
    )

    card = hooks.get_element_proof_card(
        user_id,
        claim_type,
        claim_element_id=element_id,
        claim_element_text="adverse action",
    )
    assert card["proof_state"] != "missing", f"Expected non-missing, got: {card['proof_state']}"
    assert card["supporting_fact_count"] >= 1


def test_get_element_proof_card_with_contradicted_fact_is_contradicted():
    """A fact with validation_state=contradicted should drive proof_state to 'contradicted'."""
    db_path = _tmp_db_path()
    hooks = _make_hooks(db_path)
    user_id = "user_contradicted"
    claim_type = "employment_discrimination"
    element_id = "adverse_action"

    hooks.persist_fact_record(
        user_id=user_id,
        claim_type=claim_type,
        claim_element_id=element_id,
        claim_element_text="adverse action",
        proposition_text="Employer did not terminate complainant.",
        source_artifact_id="doc:002",
        confidence=0.7,
        validation_state="contradicted",
    )

    card = hooks.get_element_proof_card(
        user_id,
        claim_type,
        claim_element_id=element_id,
        claim_element_text="adverse action",
    )
    assert card["proof_state"] == "contradicted"
    assert card["next_action"] == "resolve_contradiction"


def test_get_element_proof_card_with_exception_barred_fact():
    """A fact with validation_state=exception_barred should drive proof_state accordingly."""
    db_path = _tmp_db_path()
    hooks = _make_hooks(db_path)
    user_id = "user_exception"
    claim_type = "employment_discrimination"
    element_id = "adverse_action"

    hooks.persist_fact_record(
        user_id=user_id,
        claim_type=claim_type,
        claim_element_id=element_id,
        claim_element_text="adverse action",
        proposition_text="Claim barred by statute of limitations.",
        source_artifact_id="doc:003",
        confidence=0.8,
        validation_state="exception_barred",
    )

    card = hooks.get_element_proof_card(
        user_id,
        claim_type,
        claim_element_id=element_id,
        claim_element_text="adverse action",
    )
    assert card["proof_state"] == "exception_barred"
    assert card["next_action"] == "address_exception"


def test_get_element_proof_card_with_uncertain_fact():
    """A fact with validation_state=uncertain should drive proof_state to 'uncertain'."""
    db_path = _tmp_db_path()
    hooks = _make_hooks(db_path)
    user_id = "user_uncertain"
    claim_type = "employment_discrimination"
    element_id = "adverse_action"

    hooks.persist_fact_record(
        user_id=user_id,
        claim_type=claim_type,
        claim_element_id=element_id,
        claim_element_text="adverse action",
        proposition_text="Employer may have terminated complainant.",
        source_artifact_id="doc:004",
        confidence=0.4,
        validation_state="uncertain",
    )

    card = hooks.get_element_proof_card(
        user_id,
        claim_type,
        claim_element_id=element_id,
        claim_element_text="adverse action",
    )
    assert card["proof_state"] in {"uncertain", "partially_supported"}
    assert card["next_action"] in {"validate_facts", "complete_proof"}


# ---------------------------------------------------------------------------
# get_element_proof_cards: all elements for a claim
# ---------------------------------------------------------------------------

def test_get_element_proof_cards_returns_required_keys():
    hooks = _make_hooks()
    result = hooks.get_element_proof_cards("user1", claim_type="employment_discrimination")
    required = {
        "available",
        "user_id",
        "claim_type",
        "total_elements",
        "total_cards",
        "proof_state_totals",
        "overall_proof_readiness",
        "supported_count",
        "missing_count",
        "contradicted_count",
        "exception_barred_count",
        "incomplete_count",
        "cards",
    }
    for key in required:
        assert key in result, f"Missing key: {key}"


def test_get_element_proof_cards_available_is_true():
    hooks = _make_hooks()
    result = hooks.get_element_proof_cards("user1")
    assert result["available"] is True


def test_get_element_proof_cards_overall_proof_readiness_valid():
    hooks = _make_hooks()
    result = hooks.get_element_proof_cards("user1")
    valid_readiness = {
        "ready", "incomplete", "missing", "contradicted", "exception_barred", "unknown"
    }
    assert result["overall_proof_readiness"] in valid_readiness


def test_get_element_proof_cards_counts_are_non_negative():
    hooks = _make_hooks()
    result = hooks.get_element_proof_cards("user1")
    assert result["supported_count"] >= 0
    assert result["missing_count"] >= 0
    assert result["contradicted_count"] >= 0
    assert result["exception_barred_count"] >= 0
    assert result["incomplete_count"] >= 0


def test_get_element_proof_cards_cards_is_dict():
    hooks = _make_hooks()
    result = hooks.get_element_proof_cards("user1")
    assert isinstance(result["cards"], dict)


def test_get_element_proof_cards_unknown_claim_type():
    hooks = _make_hooks()
    result = hooks.get_element_proof_cards("user1", claim_type="unknown_claim_xyz")
    assert result["available"] is True
    assert result["overall_proof_readiness"] in {
        "ready", "incomplete", "missing", "contradicted", "exception_barred", "unknown"
    }


# ---------------------------------------------------------------------------
# proof state classification: _derive_element_proof_state
# ---------------------------------------------------------------------------

def test_derive_proof_state_contradicted_takes_priority():
    hooks = _make_hooks()
    ledger = {
        "overall_status": "contradicted",
        "total_facts": 2,
        "confirmed_count": 1,
        "contradicted_count": 1,
        "exception_barred_count": 0,
        "uncertain_count": 0,
        "unvalidated_count": 0,
    }
    prove_result = {"provable_elements": [], "unprovable_elements": []}
    contradiction_result = {"contradiction_count": 1, "has_contradictions": True, "contradictions": []}
    predicate = {"claim_element_id": "e1"}
    state = hooks._derive_element_proof_state(ledger, prove_result, contradiction_result, predicate)
    assert state == "contradicted"


def test_derive_proof_state_exception_barred_priority():
    hooks = _make_hooks()
    ledger = {
        "overall_status": "exception_barred",
        "total_facts": 1,
        "confirmed_count": 0,
        "contradicted_count": 0,
        "exception_barred_count": 1,
        "uncertain_count": 0,
        "unvalidated_count": 0,
    }
    prove_result = {"provable_elements": [], "unprovable_elements": []}
    contradiction_result = {"contradiction_count": 0, "has_contradictions": False, "contradictions": []}
    predicate = {"claim_element_id": "e1"}
    state = hooks._derive_element_proof_state(ledger, prove_result, contradiction_result, predicate)
    assert state == "exception_barred"


def test_derive_proof_state_missing_when_no_facts():
    hooks = _make_hooks()
    ledger = {
        "overall_status": "missing",
        "total_facts": 0,
        "confirmed_count": 0,
        "contradicted_count": 0,
        "exception_barred_count": 0,
        "uncertain_count": 0,
        "unvalidated_count": 0,
    }
    prove_result = {"provable_elements": [], "unprovable_elements": []}
    contradiction_result = {"contradiction_count": 0, "has_contradictions": False, "contradictions": []}
    predicate = {"claim_element_id": "e1"}
    state = hooks._derive_element_proof_state(ledger, prove_result, contradiction_result, predicate)
    assert state == "missing"


def test_derive_proof_state_supported_when_confirmed():
    hooks = _make_hooks()
    ledger = {
        "overall_status": "confirmed",
        "total_facts": 2,
        "confirmed_count": 2,
        "contradicted_count": 0,
        "exception_barred_count": 0,
        "uncertain_count": 0,
        "unvalidated_count": 0,
    }
    prove_result = {
        "provable_elements": [{"claim_element_id": "e1"}],
        "unprovable_elements": [],
    }
    contradiction_result = {"contradiction_count": 0, "has_contradictions": False, "contradictions": []}
    predicate = {"claim_element_id": "e1"}
    state = hooks._derive_element_proof_state(ledger, prove_result, contradiction_result, predicate)
    assert state == "supported"


# ---------------------------------------------------------------------------
# _build_element_proof_explanation
# ---------------------------------------------------------------------------

def test_proof_explanation_contradicted_mentions_contradiction():
    hooks = _make_hooks()
    explanation = hooks._build_element_proof_explanation(
        "adverse action", "contradicted",
        [], [{"contradiction_id": "c1"}], 1
    )
    assert "contradict" in explanation.lower() or "conflict" in explanation.lower()


def test_proof_explanation_missing_mentions_evidence():
    hooks = _make_hooks()
    explanation = hooks._build_element_proof_explanation(
        "adverse action", "missing", ["Employ(P,D)"], [], 0
    )
    assert len(explanation) > 0
    assert "adverse action" in explanation


def test_proof_explanation_supported_mentions_facts():
    hooks = _make_hooks()
    explanation = hooks._build_element_proof_explanation(
        "adverse action", "supported", [], [], 3
    )
    assert "3 confirmed fact" in explanation or "supported" in explanation.lower()


# ---------------------------------------------------------------------------
# get_question_recommendations: proof_state_context included
# ---------------------------------------------------------------------------

def test_question_recommendations_include_proof_state_context():
    hooks = _make_hooks()
    result = hooks.get_question_recommendations("user1", claim_type="employment_discrimination")
    for rec in result.get("recommendations", []):
        assert "proof_state_context" in rec, "Each recommendation should include proof_state_context"
        psc = rec["proof_state_context"]
        assert "proof_state" in psc
        assert "next_action" in psc
        assert "missing_predicates" in psc
        assert "contradiction_count" in psc
        assert "proof_explanation" in psc


def test_question_recommendations_proof_state_is_valid():
    hooks = _make_hooks()
    valid_states = {
        "supported", "partially_supported", "missing",
        "contradicted", "uncertain", "exception_barred", "unvalidated",
    }
    result = hooks.get_question_recommendations("user1", claim_type="employment_discrimination")
    for rec in result.get("recommendations", []):
        psc = rec.get("proof_state_context", {})
        if psc.get("proof_state"):
            assert psc["proof_state"] in valid_states


# ---------------------------------------------------------------------------
# API route smoke tests
# ---------------------------------------------------------------------------

def _make_test_mediator_with_hooks() -> MagicMock:
    """Make a mediator mock that delegates proof card calls to real ClaimSupportHook."""
    from mediator.claim_support_hooks import ClaimSupportHook
    db_path = _tmp_db_path()
    hook = ClaimSupportHook(_make_minimal_mediator(), db_path=db_path)
    mediator = MagicMock()
    mediator.log = MagicMock()
    state = MagicMock()
    state.username = "api_test_user"
    mediator.state = state
    mediator.get_element_proof_cards = hook.get_element_proof_cards
    mediator.get_element_proof_card = hook.get_element_proof_card
    return mediator


def test_api_element_proof_cards_route_returns_200():
    """GET /api/claim-support/element-proof-cards returns 200."""
    from fastapi.testclient import TestClient
    from applications.review_api import create_claim_support_review_router
    from fastapi import FastAPI

    mediator = _make_test_mediator_with_hooks()
    app = FastAPI()
    app.include_router(create_claim_support_review_router(mediator))
    client = TestClient(app)

    response = client.get(
        "/api/claim-support/element-proof-cards",
        params={"user_id": "api_test_user", "claim_type": "employment_discrimination"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "cards" in data
    assert "overall_proof_readiness" in data


def test_api_element_proof_card_route_returns_200():
    """GET /api/claim-support/element-proof-card returns 200."""
    from fastapi.testclient import TestClient
    from applications.review_api import create_claim_support_review_router
    from fastapi import FastAPI

    mediator = _make_test_mediator_with_hooks()
    app = FastAPI()
    app.include_router(create_claim_support_review_router(mediator))
    client = TestClient(app)

    response = client.get(
        "/api/claim-support/element-proof-card",
        params={
            "user_id": "api_test_user",
            "claim_type": "employment_discrimination",
            "claim_element_id": "adverse_action",
            "claim_element_text": "adverse action",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "proof_state" in data
    assert "explanation" in data
    assert "next_action" in data


def test_api_element_proof_card_missing_claim_type_returns_422():
    """GET /api/claim-support/element-proof-card without claim_type returns 422."""
    from fastapi.testclient import TestClient
    from applications.review_api import create_claim_support_review_router
    from fastapi import FastAPI

    mediator = _make_test_mediator_with_hooks()
    app = FastAPI()
    app.include_router(create_claim_support_review_router(mediator))
    client = TestClient(app)

    response = client.get(
        "/api/claim-support/element-proof-card",
        params={"user_id": "api_test_user"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Normalization: law-element and predicate references
# ---------------------------------------------------------------------------

def test_predicate_templates_wired_for_known_claim_types():
    """Proof cards for known claim types should have template_matched=True."""
    from integrations.ipfs_datasets.logic import get_predicate_templates, _COMPLAINT_PREDICATE_TEMPLATES

    known_types = list(_COMPLAINT_PREDICATE_TEMPLATES.keys())
    for ct in known_types:
        result = get_predicate_templates(ct)
        assert result["status"] == "success"
        assert len(result["elements"]) > 0, f"No elements for {ct}"


def test_map_claim_elements_to_predicates_round_trip():
    """map_claim_elements_to_predicates returns a predicate per element."""
    from integrations.ipfs_datasets.logic import map_claim_elements_to_predicates
    elements = [
        {"element_id": "adverse_action", "element_text": "adverse action"},
        {"element_id": "protected_class", "element_text": "protected class"},
    ]
    result = map_claim_elements_to_predicates("employment_discrimination", elements)
    assert result["predicate_count"] == 2
    for pred in result["predicates"]:
        assert "predicate_type" in pred
        assert pred["predicate_type"] == "claim_element"


def test_proof_card_contains_fol_template_for_known_element():
    """For a known claim type + element, the proof card should expose a non-empty fol_template."""
    from integrations.ipfs_datasets.logic import _COMPLAINT_PREDICATE_TEMPLATES

    # Find a claim type and an element ID from the templates
    ct = "employment_discrimination"
    template_elements = _COMPLAINT_PREDICATE_TEMPLATES.get(ct, {}).get("elements", [])
    if not template_elements:
        pytest.skip("No template elements available for employment_discrimination")

    first_elem = template_elements[0]
    elem_id = first_elem.get("element_id", "")
    if not elem_id:
        pytest.skip("Template element has no element_id")

    hooks = _make_hooks()
    card = hooks.get_element_proof_card(
        "user_template_test",
        ct,
        claim_element_id=elem_id,
        claim_element_text=first_elem.get("element_text", elem_id),
    )
    assert card.get("fol_template") or card.get("template_matched") is not None
