"""Factual targets stay separate from law-derived support in /why.

Synthetic private fixtures only. No case is skipped. A retrieval score is not
proof, and diagnostic receipts keep complaint text out.
"""

from __future__ import annotations

import json

import pytest

from applications.complaint_cli import format_terminal_text
from applications.complaint_workspace import ComplaintWorkspaceRequestHandlers, format_terminal_why
from complaint_phases.denoiser import public_why_diagnostic_receipt, redact_diagnostic_value

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

PRIVATE_NARRATIVE = "On March 4, 2024 supervisor Alex Rivera reported a secret passphrase hunter2."
FACT_LABEL = "date the notice was received"
LAW_LABEL = "protected disclosure element"
CITATION = "Cal. Lab. Code 1102.5"
VERSION = "2024-ed"
SPAN = "span-1102-5-a"


def _cases():
    return (
        "factual-target-separate-from-law",
        "support-states-are-not-a-score",
        "unknown-authority-source-contradiction-definition-review",
        "narrow-ascii-receipt-hides-private-text",
        "outage-and-missing-question-stay-truthful",
        "workspace-why-publishes-support-without-storing-an-answer",
    )


def _inquiry():
    return {
        "inquiry_id": "inq-mgnd-37",
        "objective_id": "obj-notice-date",
        "target_id": "target-notice-date",
        "question": "What date did you receive the notice?",
        "why_it_matters": "The notice date is still missing from the complaint record.",
        "factual_target": {"target_id": "fact-notice-date", "label": FACT_LABEL, "kind": "factual"},
        "law_derived_requirement": {
            "requirement_id": "req-protected-disclosure",
            "label": LAW_LABEL,
            "law_derived": True,
        },
        "admitted_authorities": [
            {
                "admitted": True,
                "citation": CITATION,
                "version": VERSION,
                "span": SPAN,
                "span_text": PRIVATE_NARRATIVE,
            },
            {"admitted": False, "citation": "Unreviewed blog", "version": "n/a", "span": "span-reject"},
        ],
        "support_states": {
            "user_assertion": "asserted",
            "corroboration": "uncorroborated",
            "candidate": "candidate",
            "applicability": "unknown",
            "proof": "unproved",
        },
        "retrieval_score": 0.99,
        "narrative": PRIVATE_NARRATIVE,
        "expected_answer_contract": {"expected_information": "the notice date you observed"},
        "expected_update_contract": {"update_kind": "record_notice_date"},
    }


def test_case_list_is_nonempty():
    assert len(_cases()) >= 6


def test_factual_target_is_separate_from_law_and_authority():
    rendered = format_terminal_why(_inquiry())
    display = rendered["display"]
    support = rendered["question_support"]
    assert support["factual_target"]["label"] == FACT_LABEL
    assert support["law_derived_requirement"]["label"] == LAW_LABEL
    assert support["factual_target"]["target_id"] != support["law_derived_requirement"]["requirement_id"]
    assert f"Factual target: {FACT_LABEL}" in display
    assert f"Law-derived requirement: {LAW_LABEL}" in display
    assert f"citation={CITATION}; version={VERSION}; span={SPAN}" in display
    assert "Unreviewed blog" not in display
    assert PRIVATE_NARRATIVE not in display
    fact_at = display.index("Factual target:")
    law_at = display.index("Law-derived requirement:")
    authority_at = display.index("Admitted authority:")
    assert fact_at < law_at < authority_at
    assert support["legal_sufficiency"] is False


def test_support_states_stay_distinct_from_retrieval_score():
    inquiry = _inquiry()
    inquiry["proof"] = "0.99"
    inquiry["support_states"]["proof"] = "0.99"
    rendered = format_terminal_why(inquiry)
    states = rendered["question_support"]["support_states"]
    assert list(states) == ["user_assertion", "corroboration", "candidate", "applicability", "proof"]
    assert states["user_assertion"] == "asserted"
    assert states["corroboration"] == "uncorroborated"
    assert states["candidate"] == "candidate"
    assert states["applicability"] == "unknown"
    assert states["proof"] == "unknown"
    assert len(set(states.values())) > 1
    assert rendered["question_support"]["retrieval_score"] == "0.99"
    assert rendered["question_support"]["retrieval_score_is_proof"] is False
    assert "A retrieval score is not proof" in rendered["display"]
    assert "proof=0.99" not in rendered["display"]
    assert rendered["diagnostic_receipt"]["retrieval_score_is_proof"] is False


@pytest.mark.parametrize(
    ("field", "value", "kind", "action"),
    [
        ("authority_status", "unknown", "unknown_authority", "identify_or_research_admitted_authority"),
        ("source_status", "outage", "source_outage", "retry_when_source_available"),
        ("contradiction", True, "contradiction", "clarify_the_conflicting_accounts"),
        ("definition_status", "missing", "missing_definition", "review_the_element_definition"),
        ("review_status", "needs_review", "missing_review", "complete_manual_review"),
    ],
)
def test_support_conditions_name_a_next_action(field, value, kind, action):
    inquiry = {
        "question": "Which account should the record keep?",
        "why_it_matters": "Two dates conflict.",
        "objective_id": "obj-conflict",
        "target_id": "target-conflict",
        "admitted_authorities": [
            {"admitted": True, "citation": CITATION, "version": VERSION, "span": SPAN}
        ],
        "authority_status": "admitted",
        field: value,
    }
    if kind == "unknown_authority":
        inquiry["admitted_authorities"] = []
    rendered = format_terminal_why(inquiry)
    kinds = [item["kind"] for item in rendered["question_support"]["conditions"]]
    assert kind in kinds
    matched = next(item for item in rendered["question_support"]["conditions"] if item["kind"] == kind)
    assert matched["next_action"] == action
    assert action in rendered["display"]
    assert matched["message"]
    assert rendered["question_support"]["legal_sufficiency"] is False
    assert rendered["worker_stalled"] is False


def test_narrow_ascii_rendering_and_private_receipt(monkeypatch):
    inquiry = _inquiry()
    inquiry["question"] = "What date did you receive the notice? " + ("detail " * 40)
    inquiry["factual_target"]["label"] = FACT_LABEL + " " + "x" * 400
    rendered = format_terminal_why(inquiry)
    assert len(rendered["display"]) <= 3500
    assert "\033" not in rendered["display"]
    monkeypatch.setenv("COMPLAINT_CLI_ASCII", "1")
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("COLUMNS", "20")
    monkeypatch.delenv("COMPLAINT_CLI_NO_COLOR", raising=False)
    wrapped = format_terminal_text(rendered["display"])
    assert all(len(line) <= 20 for line in wrapped.splitlines())
    assert all(ord(char) < 128 for char in wrapped)
    receipt = rendered["diagnostic_receipt"]
    encoded = json.dumps(redact_diagnostic_value(receipt), sort_keys=True)
    assert PRIVATE_NARRATIVE not in encoded
    assert "hunter2" not in encoded
    assert "Alex Rivera" not in encoded
    assert "What date did you receive" not in encoded
    assert receipt["contains_private_content"] is False
    assert receipt["authority_citations"] == [CITATION]
    assert receipt["support_states"]["proof"] == "unproved"
    again = public_why_diagnostic_receipt(rendered)
    assert again == receipt
    dirty = redact_diagnostic_value({
        "status": "configured",
        "prompt": PRIVATE_NARRATIVE,
        "narrative": PRIVATE_NARRATIVE,
        "nested": {"answer": PRIVATE_NARRATIVE, "error_code": "source_outage"},
    })
    assert "prompt" not in dirty
    assert "narrative" not in dirty
    assert "answer" not in dirty["nested"]
    assert dirty["nested"]["error_code"] == "source_outage"


def test_outage_and_missing_question_remain_truthful():
    outage = format_terminal_why({
        "question": "Which statute edition applies?",
        "why_it_matters": "The source could not be read.",
        "objective_id": "obj-statute",
        "target_id": "target-statute",
        "source_status": "unavailable",
        "retrieval_score": 1,
    })
    assert outage["legal_sufficiency"] is False
    assert outage["question_support"]["proof_established"] is False
    assert "source_outage" in outage["diagnostic_receipt"]["condition_kinds"]
    assert "retry_when_source_available" in outage["diagnostic_receipt"]["next_actions"]
    assert "not legal sufficiency" in outage["display"]
    assert outage["awaiting_user"] is True
    assert outage["worker_stalled"] is False

    missing = format_terminal_why(None)
    assert "no current question" in missing["display"]
    assert "not a stalled worker" in missing["display"]
    assert missing["stored_as_answer"] is False
    assert missing["legal_sufficiency"] is False
    assert missing["diagnostic_receipt"]["contains_private_content"] is False
    assert "identify_or_research_admitted_authority" in missing["display"]


def test_workspace_why_publishes_support_without_storing_an_answer():
    inquiry = _inquiry()
    state = {
        "user_id": "synthetic-mgnd-37",
        "intake_answers": {},
        "intake_history": [],
        "explained_inquiry": inquiry,
        "shared_interview": {"pending_inquiry": inquiry},
    }

    class _Workspace:
        def _load_state(self, user_id):
            return state

        def _build_intake_chat_payload(self, loaded, **kwargs):
            return {"message": "pending question", "session": {"router_trace": {"diagnostics": {
                "prompt_logged": False,
                "prompt": PRIVATE_NARRATIVE,
            }}}}

        def _save_state(self, loaded):
            raise AssertionError("/why must not be stored as an answer")

    payload = ComplaintWorkspaceRequestHandlers(_Workspace()).run_intake_chat_turn(
        "synthetic-mgnd-37", message="/why"
    )
    assert payload["stored_as_answer"] is False
    assert payload["command"] == "/why"
    assert payload["legal_sufficiency"] is False
    assert payload["question_support"]["factual_target"]["target_id"] == "fact-notice-date"
    assert payload["question_support"]["law_derived_requirement"]["requirement_id"] == "req-protected-disclosure"
    assert payload["diagnostic_receipt"]["schema"] == "why-diagnostic-receipt-v1"
    assert PRIVATE_NARRATIVE not in json.dumps(payload["diagnostic_receipt"])
    assert state["intake_answers"] == {}
    assert state["intake_history"] == []
    direct = format_terminal_why(inquiry)
    assert payload["message"] == direct["display"]


def test_same_label_is_not_copied_into_both_roles():
    rendered = format_terminal_why({
        "question": "When did the meeting end?",
        "why_it_matters": "The end time is still open.",
        "objective_id": "obj-end",
        "target_id": "fact-end",
        "gap_family": "factual_uncertainty",
        "factual_target": {"target_id": "fact-end", "label": "meeting end time"},
        "retrieval_score": 0.2,
    })
    support = rendered["question_support"]
    assert support["factual_target"]["target_id"] == "fact-end"
    assert support["law_derived_requirement"]["requirement_id"] == "unknown"
    assert support["law_derived_requirement"]["law_derived"] == "false"
    assert support["support_states"]["proof"] == "unknown"
    assert "Law-derived requirement: unknown" in rendered["display"]
