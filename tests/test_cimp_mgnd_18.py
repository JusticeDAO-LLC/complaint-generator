"""Preserve legal editions and adverse treatment across acquisition.

Cases are synthetic private fixtures. No test is skipped. The handoff admits
only the edition whose effective interval covers the explicit applicable-law
day. Overlapping and unknown versions stay unresolved. Retrieval time is not
an applicable-law date. Empty treatment aliases do not erase adverse,
superseding, or repealing records. A later treatment or version change
invalidates legal support and leaves user facts unchanged.
"""

from __future__ import annotations

import pytest

from complaint_phases.dependency_graph import (
    DependencyGraph,
    DependencyGraphBuilder,
    DependencyNode,
    NodeType,
)
from complaint_phases.legal_graph import LegalGraphBuilder
from integrations.ipfs_datasets.legal import (
    acquire_bounded_canonical_legal_sources,
    build_bounded_legal_acquisition_request,
    classify_legal_date,
    handoff_acquired_legal_sources,
    retain_acquired_treatment_records,
)
from tests.mgnd_fixtures import CASE_LABELS, meaningful_cases


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

_OWNER = "synthetic-mgnd-18"
_LAW_DATE = "2024-03-15"


def _dated(value: str, role: str):
    return classify_legal_date(value, role=role)


def _context(case):
    if case.narrative.jurisdiction == "unknown":
        return {"jurisdiction": "unknown"}
    return {
        "jurisdiction": "Oregon",
        "applicable_law_date": _dated(_LAW_DATE, "applicable_law_date"),
        "event_date": _dated("" if case.label == "baseline" else case.narrative.event_date, "event_date"),
        "filing_reference_date": _dated("2024-04-02", "filing_reference_date"),
        "corpus_retrieval_date": _dated("2026-01-02", "corpus_retrieval_date"),
    }


def _binding(case):
    context = _context(case)
    if case.narrative.jurisdiction == "unknown":
        return build_bounded_legal_acquisition_request(
            context,
            [{"claim_type": "termination", "name": "Termination"}],
            query_terms=["termination statute"],
            narrative=case.narrative.text,
            storage_available=case.storage_available,
        )
    return build_bounded_legal_acquisition_request(
        context,
        [{"claim_type": "termination", "name": "Termination"}],
        query_terms=["termination statute"],
        narrative=case.narrative.text,
        storage_available=case.storage_available,
    )


def _rows_for(case):
    rows = []
    for source in case.sources:
        rows.append({
            "text": source.source_text,
            "citation": source.citation,
            "uri": "fixture://" + source.authority_id,
            "corpus_version": source.version,
            "jurisdiction": "OR",
            "effective_date": source.effective_date,
            "authority_id": source.authority_id,
        })
    return {"state_statute": rows}


def _acquire(case, **kwargs):
    payload = dict(
        owner_id=_OWNER,
        case_id=case.case_id,
        purpose="public_law_citation",
        data_class="public_legal_source_graph",
        provider_kind="local",
        retrieval_mode="cache",
        max_bytes=4096,
        deadline_seconds=2.0,
        max_results=5,
    )
    if case.label == "cancellation":
        payload["cancelled"] = True
    elif case.narrative.jurisdiction != "unknown" and case.storage_available is not False and case.label != "cancellation":
        payload["local_rows"] = kwargs.pop("local_rows", _rows_for(case))
    payload.update(kwargs)
    return acquire_bounded_canonical_legal_sources(_binding(case), **payload)


def _stamp_retrieval(candidate, retrieved_at="2026-01-02T15:04:05+00:00"):
    retrieval = dict(candidate.get("retrieval") or {})
    retrieval["retrieved_at"] = retrieved_at
    candidate["retrieval"] = retrieval
    candidate["authority_id"] = candidate.get("authority_id") or candidate.get("locator", "").removeprefix("fixture://")
    return candidate


def test_meaningful_cases_are_nonempty():
    cases = meaningful_cases()
    assert cases
    assert tuple(case.label for case in cases) == CASE_LABELS
    assert all(case.case_id and case.narrative.text for case in cases)


def test_selected_edition_keeps_retrieval_time_distinct():
    case = next(item for item in meaningful_cases() if item.label == "baseline")
    acquired = _acquire(case)
    assert acquired["status"] == "candidates"
    assert acquired["candidates"]
    for candidate in acquired["candidates"]:
        _stamp_retrieval(candidate)
    handoff = handoff_acquired_legal_sources(acquired, _context(case))
    assert handoff["proof"] is False
    assert handoff["retrieval_time_used_as_applicable_law"] is False
    assert handoff["worker_stalled"] is False
    if handoff["status"] == "unavailable":
        assert handoff["reason"] == "temporal_authority_api_unavailable"
        assert handoff["admitted"] == []
        assert handoff["unresolved"]
        assert handoff["unresolved"][0]["retrieved_at"] != handoff["applicable_law_date"]
        return
    assert handoff["status"] == "admitted"
    admitted = handoff["admitted"]
    assert len(admitted) == 1
    selected = admitted[0]
    assert selected["edition_selected"] is True
    assert selected["authority_version"] == case.sources[0].version
    assert selected["effective_date"] == case.sources[0].effective_date
    assert selected["applicable_law_date"] == _LAW_DATE
    assert selected["retrieved_at"] == "2026-01-02T15:04:05+00:00"
    assert selected["retrieved_at"] != selected["applicable_law_date"]
    assert selected["retrieved_at"] != selected["effective_date"]
    assert selected["source_text"] == case.sources[0].source_text
    assert selected["proof"] is False
    assert selected["mixed_with_other_version"] is False


def test_overlapping_and_unknown_versions_stay_unresolved():
    case = next(item for item in meaningful_cases() if item.label == "baseline")
    acquired = _acquire(case)
    first = _stamp_retrieval(dict(acquired["candidates"][0]))
    second = dict(first)
    second["version"] = "2023-edition"
    second["source_text"] = "A covered employer must keep a different edition of the safety record."
    second["retrieval"] = dict(first["retrieval"], effective_date="2023-01-01")
    second["law_version_id"] = second["authority_id"] + ":2023-edition"
    overlapping = dict(acquired, candidates=[first, second])
    handoff = handoff_acquired_legal_sources(overlapping, _context(case))
    assert handoff["admitted"] == []
    assert handoff["status"] == "unresolved"
    assert handoff["reason"] == "overlapping_versions"
    assert handoff["mixed_authority_versions"] is True
    assert {item["version"] for item in handoff["unresolved"]} == {"2024-edition", "2023-edition"}
    assert all(item["edition_selected"] is False for item in handoff["unresolved"])
    texts = {item["source_text"] for item in handoff["unresolved"]}
    assert len(texts) == 2

    unknown = dict(first)
    unknown["version"] = "current"
    unknown_handoff = handoff_acquired_legal_sources(dict(acquired, candidates=[unknown]), _context(case))
    assert unknown_handoff["admitted"] == []
    assert unknown_handoff["status"] == "unresolved"
    assert unknown_handoff["reason"] == "unknown_version"

    graph = LegalGraphBuilder().build_from_authorities([
        {
            "authority_id": first["authority_id"],
            "version": "2024-edition",
            "name": "2024 edition",
            "source_text": first["source_text"],
            "effective_date": "2024-01-01",
        },
        {
            "authority_id": first["authority_id"],
            "version": "2023-edition",
            "name": "2023 edition",
            "source_text": second["source_text"],
            "effective_date": "2023-01-01",
            "sunset_date": "2024-01-01",
        },
    ])
    sources = [element for element in graph.elements.values() if element.element_type == "authority_source"]
    assert len(sources) == 2
    assert {element.attributes["authority_version"] for element in sources} == {"2024-edition", "2023-edition"}
    assert {element.name for element in sources} == {"2024 edition", "2023 edition"}


def test_empty_alias_cannot_erase_adverse_or_repealing_treatment():
    case = next(item for item in meaningful_cases() if item.label == "baseline")
    acquired = _acquire(case)
    candidate = _stamp_retrieval(dict(acquired["candidates"][0]))
    candidate["authority_treatment_edges"] = [{"relation_type": "", "treatment_type": "", "type": ""}]
    candidate["treatment_records"] = []
    candidate["metadata"] = {
        "treatment_records": [
            {
                "treatment_type": "adverse",
                "target_authority_id": candidate["authority_id"],
                "source_authority_id": "synth-treatment-1",
                "explanation": "Later decision questions this edition.",
            }
        ],
        "treatment_summary": {
            "records": [
                {
                    "type": "",
                    "effect": "repealing",
                    "target_authority_id": candidate["authority_id"],
                    "source_authority_id": "synth-repeal-1",
                    "explanation": "A later act repeals the duty.",
                }
            ]
        },
    }
    retained = retain_acquired_treatment_records(candidate)
    labels = {item["treatment_type"] for item in retained}
    assert "adverse" in labels
    assert "repealing" in labels
    assert all(item["treatment_type"] for item in retained)

    acquired_with_treatment = dict(acquired, candidates=[candidate])
    handoff = handoff_acquired_legal_sources(acquired_with_treatment, _context(case))
    rows = handoff["admitted"] or handoff["unresolved"]
    assert rows
    kept = rows[0]["treatment_records"]
    assert {item["treatment_type"] for item in kept} >= {"adverse", "repealing"}
    if handoff["status"] == "admitted":
        assert handoff["admitted"][0]["support_eligible"] is False
        assert handoff["admitted"][0]["treatment_blocks_support"] is True
    else:
        assert handoff["status"] in {"unresolved", "unavailable"}
        assert handoff["admitted"] == []

    other = {
        "authority_id": "synth-treatment-1",
        "version": "2024-edition",
        "name": "Treatment source",
        "citation": "Synth. Treatment 1",
        "jurisdiction": "OR",
    }
    repeal = {
        "authority_id": "synth-repeal-1",
        "version": "2025-edition",
        "name": "Repealing act",
        "citation": "Synth. Repeal 1",
        "jurisdiction": "OR",
    }
    graph = LegalGraphBuilder().build_from_authorities([candidate, other, repeal])
    target = next(
        element for element in graph.elements.values()
        if element.attributes.get("source_authority_id") == candidate["authority_id"]
        and element.attributes.get("authority_version") == candidate["version"]
    )
    stored = {item["treatment_type"] for item in target.attributes["treatment_records"]}
    assert "adverse" in stored
    assert "repealing" in stored
    relation_types = {relation.relation_type for relation in graph.relations.values()}
    assert "adverse" in relation_types
    assert "repealed" in relation_types or "repealing" in relation_types


def test_treatment_or_version_change_invalidates_legal_support_only():
    graph = DependencyGraph()
    fact = DependencyNode(
        id="fact-user-1",
        node_type=NodeType.FACT,
        name="Alex Rivera ended the warehouse job",
        description="User fact dated 2024-03-04.",
        satisfied=True,
        attributes={"about_complainant": True, "user_fact": "Alex Rivera ended the warehouse job"},
    )
    legal = DependencyNode(
        id="legal-support-1",
        node_type=NodeType.LEGAL_ELEMENT,
        name="Safety record duty",
        description="A covered employer must keep a written record of a safety report for four years.",
        satisfied=True,
        attributes={
            "dependency_class": "legally_sourced_requirement",
            "authority_id": "synth-or-safety-1",
            "authority_version": "2024-edition",
            "support_eligible": True,
            "satisfaction_state": "satisfied",
            "rule_id": "synth-or-safety-1:2024-edition",
            "dependency_scope": {"rule_id": "synth-or-safety-1:2024-edition", "fact_ids": ["fact-user-1"]},
            "user_fact": "Alex Rivera ended the warehouse job",
        },
    )
    graph.add_node(fact)
    graph.add_node(legal)
    report = DependencyGraphBuilder().refresh_affected_dependencies(graph, {"treatment_changed": True})
    assert "legal-support-1" in report["invalidated_node_ids"]
    assert "fact-user-1" in report["preserved_node_ids"]
    assert "fact-user-1" not in report["affected_node_ids"]
    assert report["user_facts_modified"] is False
    assert fact.name == "Alex Rivera ended the warehouse job"
    assert fact.description == "User fact dated 2024-03-04."
    assert fact.satisfied is True
    assert fact.attributes["user_fact"] == "Alex Rivera ended the warehouse job"
    assert legal.satisfied is False
    assert legal.attributes["satisfaction_state"] == "invalidated"
    assert legal.attributes["support_eligible"] is False
    assert legal.attributes["invalidation_reason"] == "treatment_changed"
    assert legal.description == "A covered employer must keep a written record of a safety report for four years."
    assert legal.attributes["user_fact"] == "Alex Rivera ended the warehouse job"

    legal.satisfied = True
    legal.attributes["satisfaction_state"] = "satisfied"
    legal.attributes["support_eligible"] = True
    version_report = DependencyGraphBuilder().refresh_affected_dependencies(graph, {"version_changed": True})
    assert "legal-support-1" in version_report["invalidated_node_ids"]
    assert fact.satisfied is True
    assert fact.name == "Alex Rivera ended the warehouse job"
    assert legal.attributes["invalidation_reason"] == "authority_version_changed"
    assert version_report["user_facts_modified"] is False


def test_each_case_handoff_stays_truthful():
    seen = []
    for case in meaningful_cases():
        acquired = _acquire(case)
        if acquired.get("candidates"):
            for candidate in acquired["candidates"]:
                _stamp_retrieval(candidate)
        handoff = handoff_acquired_legal_sources(acquired, _context(case))
        seen.append(case.label)
        assert handoff["proof"] is False
        assert handoff["worker_stalled"] is False
        assert handoff["retrieval_time_used_as_applicable_law"] is False
        assert handoff["stage"] == "acquired_source_handoff"
        encoded = str(handoff)
        assert case.narrative.text not in encoded
        if case.label == "cancellation":
            assert handoff["status"] == "cancelled"
            assert handoff["admitted"] == []
        elif case.label == "storage_outage":
            assert handoff["status"] == "unavailable"
            assert handoff["admitted"] == []
        elif case.label == "unknown":
            assert handoff["status"] == "unresolved"
            assert handoff["admitted"] == []
        elif case.label == "missing_authority":
            assert handoff["admitted"] == []
            assert handoff["status"] in {"empty", "unavailable", "incomplete", "missing_edition", "unresolved"}
        elif handoff["status"] == "unavailable":
            assert handoff["admitted"] == []
            assert handoff["reason"]
        elif handoff["status"] == "admitted":
            assert handoff["admitted"]
            assert all(item["edition_selected"] is True for item in handoff["admitted"])
            assert all(item["applicable_law_date"] == _LAW_DATE for item in handoff["admitted"])
            assert all(item["retrieved_at"] != item["applicable_law_date"] for item in handoff["admitted"])
    assert seen == list(CASE_LABELS)
