"""Explicit jurisdiction and legally relevant dates stay unresolved until stated."""

import copy
from types import SimpleNamespace

import pytest

from complaint_phases import Entity, KnowledgeGraph
from complaint_phases.intake_case_file import (
    apply_explicit_legal_context,
    build_intake_case_file,
    extract_explicit_jurisdiction_from_text,
    refresh_explicit_legal_context,
    refresh_intake_case_file,
)
from integrations.ipfs_datasets.legal import (
    apply_legal_context_update,
    classify_legal_date,
    constrain_assertions_to_corpus,
    empty_legal_context,
    legal_requirement_search_plan,
    resolve_explicit_jurisdiction,
    search_legal_authority_program,
    select_requirement_applicability,
)
from mediator.mediator import Mediator


def test_unresolved_jurisdiction_is_unknown_not_oregon_or_federal():
    assert resolve_explicit_jurisdiction(None) == "unknown"
    assert resolve_explicit_jurisdiction("") == "unknown"
    assert resolve_explicit_jurisdiction("somewhere") == "unknown"
    assert resolve_explicit_jurisdiction("Oregon") == "OR"
    assert resolve_explicit_jurisdiction("federal") == "federal"
    assert legal_requirement_search_plan({"query_text": "retaliation", "authority_families": ["statute"]}) == {
        "jurisdiction": "unknown",
        "state_code": "",
        "context_status": "unknown",
        "selected_rule_applicability": "unknown",
        "search_us_code": False,
        "search_federal_register": False,
        "search_state_laws": False,
        "search_state_administrative_rules": False,
        "search_case_law": False,
        "authority_families": ["statute"],
    }


def test_authority_program_does_not_search_when_context_is_unresolved(monkeypatch):
    def _forbidden(*_args, **_kwargs):
        raise AssertionError("implicit legal search")

    monkeypatch.setattr("integrations.ipfs_datasets.legal.search_us_code", _forbidden)
    monkeypatch.setattr("integrations.ipfs_datasets.legal.search_federal_register", _forbidden)
    monkeypatch.setattr("integrations.ipfs_datasets.legal.search_state_laws", _forbidden)
    monkeypatch.setattr("integrations.ipfs_datasets.legal.search_state_administrative_rules", _forbidden)
    monkeypatch.setattr("integrations.ipfs_datasets.legal.search_recap_documents", _forbidden)

    result = search_legal_authority_program(
        {"query_text": "wage claim", "program_id": "prog-1", "authority_families": ["statute", "regulation"]}
    )
    assert result["metadata"]["jurisdiction"] == "unknown"
    assert result["metadata"]["state_code"] == ""
    assert result["metadata"]["context_status"] == "unknown"
    assert result["metadata"]["selected_rule_applicability"] == "unknown"
    assert result["result_count"] == 0


def test_corpus_constraint_leaves_unresolved_context_unknown(monkeypatch):
    monkeypatch.setattr(
        "integrations.ipfs_datasets.legal.search_us_code",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("implicit federal search")),
    )
    result = constrain_assertions_to_corpus([{"assertion_id": "a1", "text": "The employer retaliated."}])
    assert result["jurisdiction"] == "unknown"
    assert result["context_status"] == "unknown"
    assert result["selected_rule_applicability"] == "unknown"
    assert result["details"][0]["applicability"] == "unknown"
    assert result["details"][0]["reason"] == "unresolved_legal_context"
    assert result["grounded_count"] == 0


def test_date_roles_stay_distinct_and_uncertain_ranges_are_not_precise_days():
    event = classify_legal_date("early March 2024", role="event_date")
    applicable = classify_legal_date("2024-03-15", role="applicable_law_date")
    filing = classify_legal_date("March 2024 to May 2024", role="filing_reference_date")
    retrieval = classify_legal_date("2024-06-01", role="corpus_retrieval_date")

    assert event["role"] == "event_date"
    assert event["precision"] == "uncertain_range"
    assert event["precise_date"] is None
    assert event["raw_text"] == "early March 2024"
    assert applicable["role"] == "applicable_law_date"
    assert applicable["precise_date"] == "2024-03-15"
    assert filing["role"] == "filing_reference_date"
    assert filing["precision"] == "range"
    assert filing["precise_date"] is None
    assert filing["start_date"] == "2024-03-01"
    assert filing["end_date"] == "2024-05-31"
    assert retrieval["role"] == "corpus_retrieval_date"
    assert {event["role"], applicable["role"], filing["role"], retrieval["role"]} == {
        "event_date",
        "applicable_law_date",
        "filing_reference_date",
        "corpus_retrieval_date",
    }


def test_requirement_selection_requires_explicit_context_and_rejects_mismatch():
    context = empty_legal_context()
    unresolved = select_requirement_applicability({"jurisdiction": "OR", "requirement_id": "r1"}, context)
    assert unresolved["selected"] is False
    assert unresolved["applicability"] == "unknown"

    context = apply_legal_context_update(context, {
        "jurisdiction": "Oregon",
        "applicable_law_date": "March 1, 2024",
        "event_date": "sometime in spring 2024",
    })
    selected = select_requirement_applicability({"jurisdiction": "OR"}, context)
    assert selected["selected"] is True
    assert selected["event_date"]["precise_date"] is None
    assert selected["applicable_law_date"]["precise_date"] == "2024-03-01"
    federal = select_requirement_applicability({"jurisdiction": "federal"}, context)
    assert federal["selected"] is False
    assert federal["reason"] == "jurisdiction_not_selected"


def test_changing_context_invalidates_selected_rules_and_dependent_proof():
    context = apply_legal_context_update(empty_legal_context(), {
        "jurisdiction": "OR",
        "applicable_law_date": "2024-01-01",
        "event_date": "2024-02-02",
    })
    context["selected_rule_applicability"] = "selected"
    context["proof_state"] = "supported"
    context["dependent_proof"] = [{"lead_id": "lead-1", "proof_state": "supported"}]
    updated = apply_legal_context_update(
        context,
        {"jurisdiction": "WA", "event_date": "early 2024"},
        dependent_proof=context["dependent_proof"],
    )
    assert updated["jurisdiction"] == "WA"
    assert updated["context_revision"] == context["context_revision"] + 1
    assert updated["selected_rule_applicability"] == "invalidated"
    assert updated["proof_state"] == "invalidated"
    assert updated["dependent_proof"][0]["proof_state"] == "invalidated"
    assert updated["event_date"]["precision"] == "uncertain_range"
    assert updated["event_date"]["precise_date"] is None
    stale = select_requirement_applicability(
        {"jurisdiction": "WA", "context_revision": context["context_revision"]},
        updated,
    )
    assert stale["applicability"] == "invalidated"


def test_intake_asks_for_missing_jurisdiction_and_keeps_location_from_becoming_law():
    graph = KnowledgeGraph()
    graph.add_entity(Entity(
        id="fact:1",
        type="fact",
        name="Office event",
        attributes={
            "description": "The meeting happened at the Dallas office.",
            "fact_type": "timeline",
            "event_date_or_range": "sometime in spring 2024",
        },
    ))
    case_file = build_intake_case_file(graph, "The meeting happened at the Dallas office.")
    assert extract_explicit_jurisdiction_from_text(case_file["source_complaint_text"]) == "unknown"
    assert case_file["legal_context"]["jurisdiction"] == "unknown"
    assert case_file["legal_context"]["status"] == "unknown"
    event = case_file["legal_context"]["event_date"]
    assert event["raw_text"] == "sometime in spring 2024"
    assert event["precise_date"] is None
    question_ids = {item["open_item_id"] for item in case_file["open_items"]}
    assert "legal_context:legal_context.jurisdiction" in question_ids
    prompts = " ".join(item["reason"] for item in case_file["open_items"])
    assert "Oregon" in prompts
    assert "federal" in prompts.lower() or "Federal" in prompts


def test_intake_context_change_invalidates_proof_and_records_separate_dates():
    graph = KnowledgeGraph()
    graph.add_entity(Entity(
        id="fact:1",
        type="fact",
        name="Termination",
        attributes={
            "description": "Employer terminated Plaintiff on January 20, 2026.",
            "fact_type": "timeline",
            "event_date_or_range": "January 20, 2026",
        },
    ))
    case_file = build_intake_case_file(
        graph,
        "Under Oregon law. Applicable law date: January 1, 2024. Filed on March 1, 2024.",
    )
    assert case_file["legal_context"]["jurisdiction"] == "OR"
    assert case_file["legal_context"]["event_date"]["precise_date"] == "2026-01-20"
    assert case_file["legal_context"]["applicable_law_date"]["precise_date"] == "2024-01-01"
    assert case_file["legal_context"]["filing_reference_date"]["precise_date"] == "2024-03-01"
    assert case_file["legal_context"]["event_date"]["role"] != case_file["legal_context"]["filing_reference_date"]["role"]
    case_file["legal_context"]["selected_rule_applicability"] = "selected"
    case_file["legal_context"]["proof_state"] = "supported"
    case_file["proof_leads"] = [{"lead_id": "lead-9", "proof_state": "supported", "text": "letter"}]
    updated = apply_explicit_legal_context(
        case_file,
        jurisdiction="Washington",
        corpus_retrieval_date="2026-04-04",
    )
    assert updated["legal_context"]["jurisdiction"] == "WA"
    assert updated["legal_context"]["selected_rule_applicability"] == "invalidated"
    assert updated["legal_context"]["proof_state"] == "invalidated"
    assert updated["proof_leads"][0]["proof_state"] == "invalidated"
    assert updated["legal_context"]["corpus_retrieval_date"]["role"] == "corpus_retrieval_date"
    assert updated["legal_context"]["corpus_retrieval_date"]["precise_date"] == "2026-04-04"
    assert updated["legal_context"]["event_date"]["precise_date"] == "2026-01-20"


def test_mediator_does_not_default_jurisdiction_to_federal():
    mediator = Mediator.__new__(Mediator)
    empty = SimpleNamespace(elements={})
    assert mediator._determine_jurisdiction(empty) == "unknown"
    labeled = SimpleNamespace(elements={
        "e1": SimpleNamespace(jurisdiction=""),
        "e2": SimpleNamespace(jurisdiction="federal"),
        "e3": SimpleNamespace(jurisdiction="federal"),
    })
    assert mediator._determine_jurisdiction(labeled) == "federal"
    mixed = SimpleNamespace(elements={
        "e1": SimpleNamespace(jurisdiction="OR"),
        "e2": SimpleNamespace(jurisdiction="WA"),
    })
    assert mediator._determine_jurisdiction(mixed) == "unknown"
    questions = mediator.legal_context_questions({"canonical_facts": [], "source_complaint_text": ""})
    assert any(item["field"] == "jurisdiction" for item in questions)
    assert any(item["field"] == "event_date" for item in questions)


# These are conservative context-admission regressions, not corpus entailment tests.


@pytest.mark.parametrize('value', ['ZZ', 'FD', 'UK', 'AB'])
def test_regression_unknown_two_letter_jurisdiction_cannot_select_or_search(value):
    assert resolve_explicit_jurisdiction(value) == 'unknown'
    context = apply_legal_context_update(empty_legal_context(), {
        'jurisdiction': value, 'applicable_law_date': '2024-01-01',
    })
    assert select_requirement_applicability({'jurisdiction': value}, context)['selected'] is False
    plan = legal_requirement_search_plan({'jurisdiction': value})
    assert plan['context_status'] == 'unknown'
    assert not any(plan[name] for name in ('search_us_code', 'search_state_laws', 'search_case_law'))


@pytest.mark.parametrize('value', [
    'I do not know', '2024-02-31', '2024-13-01', 'January 99, 2024',
    '2024-03-01 or 2025-04-02', 'not 2024-03-01',
    '2025-05-20 to 2024-01-01',
])
def test_regression_invalid_or_ambiguous_date_is_not_applicable_law(value):
    context = apply_legal_context_update(empty_legal_context(), {
        'jurisdiction': 'OR', 'applicable_law_date': value,
    })
    classified = context['applicable_law_date']
    assert classified['raw_text'] == value
    assert classified['precise_date'] is None
    selected = select_requirement_applicability({'jurisdiction': 'OR'}, context)
    assert selected['selected'] is False
    assert selected['applicability'] == 'unknown'
    assert any(q['field'] == 'applicable_law_date' for q in context['questions'])


@pytest.mark.parametrize(('value', 'expected'), [
    ('I do not know whether federal law applies.', 'unknown'),
    ('This is not under federal law. Under Oregon law.', 'OR'),
    ('Under Oregon law or Washington law.', 'unknown'),
    ('Under Oregon law and under Washington law.', 'unknown'),
    ('The employer cited federal law, but I dispute its applicability.', 'unknown'),
    ('Does federal law apply?', 'unknown'),
    ('Is this under Oregon law?', 'unknown'),
    ('Should I file in federal court?', 'unknown'),
    ('I am a federal employee.', 'unknown'),
    ('I mailed a federal office.', 'unknown'),
    ('I work at a federal court.', 'unknown'),
    ('I received a letter from a federal court clerk.', 'unknown'),
    ('Under Oregon law on May 5, 2024.', 'OR'),
    ('Federal law may apply.', 'unknown'),
    ('The case is pending in federal court.', 'federal'),
    ('Jurisdiction: Oregon.', 'OR'),
])
def test_regression_negated_or_ambiguous_jurisdiction_cannot_select(value, expected):
    jurisdiction = extract_explicit_jurisdiction_from_text(value)
    assert jurisdiction == expected
    context = apply_legal_context_update(empty_legal_context(), {
        'jurisdiction': jurisdiction, 'applicable_law_date': '2024-01-01',
    })
    assert select_requirement_applicability({'jurisdiction': 'federal'}, context)['selected'] is (expected == 'federal')


def _selected_case_file():
    case = {
        'source_complaint_text': 'Under Oregon law. Applicable law date: 2024-01-01.',
        'canonical_facts': [{'fact_id': 'fact:1', 'text': 'Synthetic meeting.', 'event_date_or_range': '2024-03-15'}],
        'proof_leads': [{'lead_id': 'lead:1', 'text': 'Synthetic letter', 'proof_state': 'supported'}],
    }
    case['legal_context'] = refresh_explicit_legal_context(case)
    case['legal_context']['selected_rule_applicability'] = 'selected'
    case['legal_context']['proof_state'] = 'supported'
    case['proof_leads'][0]['proof_state'] = 'supported'
    case['legal_context']['dependent_proof'][0]['proof_state'] = 'supported'
    return case


@pytest.mark.parametrize('clear', ['', None])
def test_regression_explicit_clear_overrides_source_and_invalidates_proof(clear):
    case = _selected_case_file()
    previous_revision = case['legal_context']['context_revision']
    updated = apply_explicit_legal_context(case, jurisdiction=clear, applicable_law_date=clear, event_date=clear)
    context = updated['legal_context']
    assert context['jurisdiction'] == 'unknown'
    assert context['applicable_law_date']['raw_text'] == ''
    assert context['event_date']['raw_text'] == ''
    assert context['event_dates'] == []
    assert context['context_revision'] > previous_revision
    assert context['selected_rule_applicability'] == 'invalidated'
    assert updated['proof_leads'][0]['proof_state'] == 'invalidated'
    assert not select_requirement_applicability({'jurisdiction': 'OR'}, context)['selected']


def test_regression_withdrawn_source_context_drops_old_selected_proof():
    case = _selected_case_file()
    old_revision = case['legal_context']['context_revision']
    case['source_complaint_text'] = 'No governing law or date has been established.'
    case['canonical_facts'] = []
    context = refresh_explicit_legal_context(case)
    assert context['jurisdiction'] == 'unknown'
    assert context['applicable_law_date']['raw_text'] == ''
    assert context['event_date']['raw_text'] == ''
    assert context['context_revision'] > old_revision
    assert context['selected_rule_applicability'] == 'invalidated'
    assert case['proof_leads'][0]['proof_state'] == 'invalidated'
    assert not select_requirement_applicability({'jurisdiction': 'OR', 'context_revision': old_revision}, context)['selected']


def test_regression_standard_intake_refresh_propagates_rule_invalidation_to_proof():
    case = _selected_case_file()
    case['source_complaint_text'] = 'Under Washington law. Applicable law date: 2024-01-01.'
    updated = refresh_intake_case_file(case, None)
    assert updated['legal_context']['jurisdiction'] == 'WA'
    assert updated['legal_context']['selected_rule_applicability'] == 'invalidated'
    assert updated['legal_context']['dependent_proof'][0]['proof_state'] == 'invalidated'
    assert updated['proof_leads'][0]['proof_state'] == 'invalidated'
    # A second refresh must not copy the old supported record back into context.
    refreshed = refresh_intake_case_file(updated, None)
    assert refreshed['proof_leads'][0]['proof_state'] == 'invalidated'
    assert refreshed['legal_context']['dependent_proof'][0]['proof_state'] == 'invalidated'


def test_regression_multiple_event_dates_cannot_keep_stale_single_day():
    previous = apply_legal_context_update(empty_legal_context(), {'jurisdiction': 'OR', 'event_date': '2024-03-15'})
    previous['selected_rule_applicability'] = 'selected'
    previous['proof_state'] = 'supported'
    changed = apply_legal_context_update(previous, {'event_dates': ['2025-01-01', '2025-02-01']})
    assert changed['event_date']['precise_date'] is None
    assert [record['precise_date'] for record in changed['event_dates']] == ['2025-01-01', '2025-02-01']
    assert changed['selected_rule_applicability'] == 'invalidated'


@pytest.mark.parametrize('identities', [{}, {'lead_id': 'duplicate'}])
def test_regression_context_change_preserves_distinct_legacy_proof_records(identities):
    case = _selected_case_file()
    case['proof_leads'] = [
        {**identities, 'text': 'Synthetic letter A', 'source_span_refs': ['span:A'], 'proof_state': 'supported'},
        {**identities, 'text': 'Synthetic letter B', 'source_span_refs': ['span:B'], 'proof_state': 'supported'},
    ]
    updated = apply_explicit_legal_context(case, jurisdiction='WA')
    assert [item['text'] for item in updated['proof_leads']] == ['Synthetic letter A', 'Synthetic letter B']
    assert [item['source_span_refs'] for item in updated['proof_leads']] == [['span:A'], ['span:B']]
    assert all(item['proof_state'] == 'invalidated' for item in updated['proof_leads'])


def test_regression_real_ranges_keep_bounds_and_cannot_be_forged_by_metadata():
    valid = classify_legal_date('March 2024 to May 2024', role='applicable_law_date')
    assert valid['precise_date'] is None
    assert (valid['start_date'], valid['end_date']) == ('2024-03-01', '2024-05-31')
    context = apply_legal_context_update(empty_legal_context(), {'jurisdiction': 'OR', 'applicable_law_date': valid})
    assert select_requirement_applicability({'jurisdiction': 'OR'}, context)['selected']
    forged = copy.deepcopy(context)
    forged['applicable_law_date'].update(raw_text='I do not know', precise_date='2024-01-01', precision='day')
    assert not select_requirement_applicability({'jurisdiction': 'OR'}, forged)['selected']


def test_regression_explicit_state_court_discovery_does_not_select_federal_law(monkeypatch):
    calls = []
    monkeypatch.setattr('integrations.ipfs_datasets.legal.search_recap_documents',
                        lambda query, **kwargs: calls.append(query) or [{'citation': 'Synthetic court candidate'}])
    monkeypatch.setattr('integrations.ipfs_datasets.legal.search_us_code',
                        lambda *_args, **_kwargs: pytest.fail('Implicit federal statutory lookup'))
    result = search_legal_authority_program({
        'query_text': 'Synthetic state claim', 'jurisdiction': 'OR',
        'authority_families': ['case_law', 'docket_material'],
    })
    assert calls == ['Synthetic state claim', 'Synthetic state claim']
    assert result['result_count'] == 2
    assert result['metadata']['jurisdiction'] == 'OR'
    assert result['metadata']['selected_rule_applicability'] == 'unselected'
    context = apply_legal_context_update(empty_legal_context(), {'jurisdiction': 'OR'})
    assert not select_requirement_applicability({'jurisdiction': 'OR'}, context)['selected']
    assert not select_requirement_applicability({'jurisdiction': 'federal'}, context)['selected']


@pytest.mark.parametrize("jurisdiction", [None, "unknown", "ZZ"])
@pytest.mark.parametrize("index_source", ["argument", "environment"])
def test_unresolved_context_cannot_be_grounded_by_vector_candidates(
    monkeypatch, jurisdiction, index_source,
):
    """Retrieval similarity cannot supply a missing legal jurisdiction."""
    from integrations.ipfs_datasets import legal

    calls = []
    def statutes(*args, **kwargs):
        calls.append("statutes")
        return []
    def vectors(*args, **kwargs):
        calls.append("vectors")
        return [{"citation": "Synthetic vector candidate", "jurisdiction": "OR"}]
    for name in ("search_us_code", "search_federal_register", "search_state_laws"):
        monkeypatch.setattr(legal, name, statutes)
    monkeypatch.setattr(legal, "_search_legal_vector_index", vectors)
    monkeypatch.setattr(legal, "lookup_bounded_legal_corpus", statutes)
    monkeypatch.delenv("COMPLAINT_LEGAL_VECTOR_INDEX_DIR", raising=False)
    arguments = {"legal_vector_index_dir": "synthetic-vector-index"}
    if index_source == "environment":
        monkeypatch.setenv("COMPLAINT_LEGAL_VECTOR_INDEX_DIR", "synthetic-vector-index")
        arguments = {}
    assertion = {
        "assertion_id": "synthetic-unresolved", "text": "Synthetic legal assertion.",
        "grounded": True, "applicability": "selected", "source_message_id": "synthetic-source",
    }
    before = copy.deepcopy(assertion)
    result = constrain_assertions_to_corpus([assertion], state=jurisdiction, **arguments)

    assert calls == []
    assert assertion == before
    assert result["jurisdiction"] == "unknown"
    assert result["context_status"] == "unknown"
    assert result["selected_rule_applicability"] == "unknown"
    assert result["grounded"] == []
    assert result["grounded_count"] == 0
    assert result["ungrounded_count"] == 1
    assert result["details"] == [{
        "assertion_id": "synthetic-unresolved", "text": assertion["text"],
        "grounded": False, "applicability": "unknown",
        "reason": "unresolved_legal_context", "corpus_hits": [],
    }]
    assert result["ungrounded"] == [{
        **assertion, "grounded": False, "applicability": "unknown", "corpus_hits": [],
    }]


@pytest.mark.parametrize("jurisdiction", ["OR", "federal"])
def test_explicit_context_vector_candidates_remain_retrieval_not_rule_selection(monkeypatch, jurisdiction):
    from integrations.ipfs_datasets import legal

    calls = []
    def statutes(*args, **kwargs):
        return []
    def vectors(query, **kwargs):
        calls.append((query, kwargs["index_dir"]))
        return [{"citation": "Synthetic vector candidate", "jurisdiction": jurisdiction}]
    for name in ("search_us_code", "search_federal_register", "search_state_laws"):
        monkeypatch.setattr(legal, name, statutes)
    monkeypatch.setattr(legal, "_search_legal_vector_index", vectors)
    monkeypatch.setattr(legal, "lookup_bounded_legal_corpus", statutes)
    assertion = {"assertion_id": "synthetic-explicit", "text": "Synthetic legal assertion."}
    result = constrain_assertions_to_corpus(
        [assertion], state=jurisdiction, legal_vector_index_dir="synthetic-vector-index",
    )
    assert calls == []
    assert result["grounded_count"] == 0
    assert result["candidate_count"] == 0
    assert result["corpus_coverage_percent"] == 0
    assert result["corpus_coverage_semantics"] == "retrieval_only"
    assert result["details"][0]["source_verified"] is False
    assert result["details"][0]["applicable"] is False
    assert result["details"][0]["entails"] is False
    assert result["details"][0]["fact_verified"] is False
    assert result["details"][0]["dispositions"]["retrieval"] == "unavailable"
    assert any(row["backend"] == "legal_vector_index"
               and row["error_code"] == "owned_vector_lookup_unavailable"
               for row in result["details"][0]["diagnostics"])
    assert result["jurisdiction"] == jurisdiction
    assert result["selected_rule_applicability"] == "unknown"
    context = apply_legal_context_update(empty_legal_context(), {"jurisdiction": jurisdiction})
    assert select_requirement_applicability({"jurisdiction": jurisdiction}, context)["selected"] is False
