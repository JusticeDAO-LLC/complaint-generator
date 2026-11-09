"""Role handoff contract: assertions, law, support, and proof stay separate.

Cases use compact synthetic payloads. No test is skipped.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from complaint_phases.dependency_graph import DependencyGraph
from integrations.ipfs_datasets.types import USER_ASSERTION_CONTRACT_VERSION
from mediator.integrations.contracts import (
    GROUNDING_ROLE_CONTRACT_VERSION,
    GROUNDING_ROLES,
    PRESERVED_ASSERTION_CONTRACT_REF,
    PRESERVED_DEPENDENCY_CONTRACT_REF,
    PRESERVED_STOP_CONTRACT_REF,
    ROLE_APPLICABLE_REQUIREMENT,
    ROLE_CONDITIONAL_IR,
    ROLE_CORROBORATING_EVIDENCE,
    ROLE_EXTRACTED_CANDIDATE,
    ROLE_PROOF_RESULT,
    ROLE_RETRIEVED_PUBLIC_LAW,
    ROLE_USER_ASSERTION,
    CapabilityCatalog,
    CapabilityStatus,
    NormalizedRetrievalBundle,
    NormalizedRetrievalRecord,
    admit_grounding_role,
    admit_grounding_role_set,
    grounding_role_examples,
)

_THIS_FILE = Path(__file__)


def _base() -> dict:
    return {
        "owner_id": "owner-synthetic",
        "case_id": "case-synthetic",
        "graph_revision": "graph-rev-1",
    }


def test_examples_cover_roles_and_match_admission_reasons():
    examples = grounding_role_examples()
    assert len(examples) >= 7
    reasons = set()
    for example in examples:
        admission = admit_grounding_role(example["payload"])
        reasons.add(admission.reason)
        assert admission.reason == example["expect"]
        if example["expect"] == "admitted":
            assert admission.record is not None
            assert admission.record.contract_version == GROUNDING_ROLE_CONTRACT_VERSION
            assert "verified" not in admission.record.as_dict()
            assert "satisfied" not in admission.record.as_dict()
        else:
            assert admission.record is None
    assert "spoofed_verified_flag" in reasons
    assert "spoofed_satisfied_flag" in reasons
    assert set(GROUNDING_ROLES) >= {
        ROLE_USER_ASSERTION,
        ROLE_EXTRACTED_CANDIDATE,
        ROLE_RETRIEVED_PUBLIC_LAW,
        ROLE_APPLICABLE_REQUIREMENT,
        ROLE_CORROBORATING_EVIDENCE,
        ROLE_CONDITIONAL_IR,
        ROLE_PROOF_RESULT,
    }


def test_unknown_decisions_and_references_stay_uninferred(tmp_path: Path):
    fixture = {
        **_base(),
        "role": ROLE_USER_ASSERTION,
        "source_id": "msg-7",
        "source_version": "",
        "content_hash": "",
    }
    path = tmp_path / "user-assertion.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    admission = admit_grounding_role(loaded)
    assert admission.admitted is True
    record = admission.record
    assert record is not None
    assert record.owner_id == "owner-synthetic"
    assert record.case_id == "case-synthetic"
    assert record.graph_revision == "graph-rev-1"
    assert record.source_decision == "unknown"
    assert record.edition_decision == "unknown"
    assert record.applicability_decision == "unknown"
    assert record.meaning_decision == "unknown"
    assert record.governs_law is False
    assert record.as_dict()["user_statement_governs"] is False
    assert record.as_dict()["span"]["known"] is False
    assert record.assertion_contract_ref == PRESERVED_ASSERTION_CONTRACT_REF
    assert record.dependency_contract_ref == PRESERVED_DEPENDENCY_CONTRACT_REF
    assert record.stop_contract_ref == PRESERVED_STOP_CONTRACT_REF


def test_retrieval_score_does_not_become_governing_law():
    scored = admit_grounding_role({
        **_base(),
        "role": ROLE_RETRIEVED_PUBLIC_LAW,
        "source_id": "statute-1",
        "content_hash": "ab" * 32,
        "retrieval_score": 0.99,
    })
    assert scored.admitted is True
    assert scored.record is not None
    assert scored.record.governs_law is False
    assert scored.record.edition_decision == "unknown"
    assert scored.record.as_dict()["retrieval_score_governs"] is False

    pinned = admit_grounding_role({
        **_base(),
        "role": ROLE_RETRIEVED_PUBLIC_LAW,
        "source_id": "statute-1",
        "source_version": "ed-2024",
        "span_start": 0,
        "span_end": 8,
        "content_hash": "cd" * 32,
        "source_decision": "admitted",
        "edition_decision": "pinned",
        "meaning_decision": "unknown",
        "retrieval_score": 0.01,
    })
    assert pinned.admitted is True
    assert pinned.record is not None
    assert pinned.record.governs_law is True
    assert pinned.record.meaning_decision == "unknown"
    assert pinned.record.applicability_decision == "unknown"

    laundered = admit_grounding_role({
        **_base(),
        "role": ROLE_RETRIEVED_PUBLIC_LAW,
        "retrieval_score": 1.0,
        "governs_law": True,
    })
    assert laundered.admitted is False
    assert laundered.reason == "retrieval_score_cannot_govern"
    assert laundered.record is None


def test_requirement_evidence_ir_and_proof_stay_distinct():
    requirement = admit_grounding_role({
        **_base(),
        "role": ROLE_APPLICABLE_REQUIREMENT,
        "source_id": "req-1",
    })
    assert requirement.admitted is True
    assert requirement.record is not None
    assert requirement.record.applicability_decision == "unknown"
    assert requirement.record.governs_law is False

    applicable = admit_grounding_role({
        **_base(),
        "role": ROLE_APPLICABLE_REQUIREMENT,
        "source_id": "req-1",
        "applicability_decision": "applicable",
    })
    assert applicable.admitted is True
    assert applicable.record is not None
    assert applicable.record.applicability_decision == "applicable"
    assert applicable.record.governs_law is False

    evidence = admit_grounding_role({
        **_base(),
        "role": ROLE_CORROBORATING_EVIDENCE,
        "source_id": "doc-1",
        "corroborates_ref": "assertion:abc",
        "source_decision": "admitted",
        "source_version": "v1",
        "span_start": 1,
        "span_end": 4,
        "content_hash": "ef" * 32,
    })
    assert evidence.admitted is True
    assert evidence.record is not None
    assert evidence.record.governs_law is False
    assert evidence.record.corroborates_ref == "assertion:abc"

    candidate = admit_grounding_role({
        **_base(),
        "role": ROLE_EXTRACTED_CANDIDATE,
        "candidate_extractor_ref": "extractor.v1",
        "retrieval_score": 0.4,
    })
    assert candidate.admitted is True
    assert candidate.record is not None
    assert candidate.record.role == ROLE_EXTRACTED_CANDIDATE
    assert candidate.record.governs_law is False

    ir_record = admit_grounding_role({
        **_base(),
        "role": ROLE_CONDITIONAL_IR,
        "conditional_ir_status": "conditional",
    })
    assert ir_record.admitted is True
    assert ir_record.record is not None
    assert ir_record.record.conditional_ir_status == "conditional"
    assert ir_record.record.actual_proof_outcome == ""
    assert ir_record.record.governs_law is False

    missing_proof = admit_grounding_role({**_base(), "role": ROLE_PROOF_RESULT})
    assert missing_proof.admitted is True
    assert missing_proof.record is not None
    assert missing_proof.record.actual_proof_outcome == "unavailable"
    assert missing_proof.record.proof_receipt_ref == ""

    failed_proof = admit_grounding_role({
        **_base(),
        "role": ROLE_PROOF_RESULT,
        "actual_proof_outcome": "failed",
    })
    assert failed_proof.admitted is True
    assert failed_proof.record is not None
    assert failed_proof.record.actual_proof_outcome == "failed"

    proved_without_receipt = admit_grounding_role({
        **_base(),
        "role": ROLE_PROOF_RESULT,
        "actual_proof_outcome": "proved",
    })
    assert proved_without_receipt.admitted is False
    assert proved_without_receipt.reason == "proof_receipt_required"

    role_set = admit_grounding_role_set([
        {**_base(), "role": ROLE_USER_ASSERTION, "source_id": "msg-1"},
        {
            **_base(),
            "role": ROLE_EXTRACTED_CANDIDATE,
            "candidate_extractor_ref": "extractor.v1",
        },
        {**_base(), "role": ROLE_PROOF_RESULT, "actual_proof_outcome": "not_run"},
    ])
    assert role_set.admitted is True
    assert role_set.role_set is not None
    assert set(role_set.role_set.records) == {
        ROLE_USER_ASSERTION,
        ROLE_EXTRACTED_CANDIDATE,
        ROLE_PROOF_RESULT,
    }
    duplicate = admit_grounding_role_set([
        {**_base(), "role": ROLE_USER_ASSERTION},
        {**_base(), "role": ROLE_USER_ASSERTION},
    ])
    assert duplicate.admitted is False
    assert duplicate.reason == "duplicate_role"


def test_spoofed_flags_and_replacements_fail_closed():
    verified = admit_grounding_role({**_base(), "role": ROLE_PROOF_RESULT, "verified": False})
    assert verified.admitted is False
    assert verified.reason == "spoofed_verified_flag"
    satisfied = admit_grounding_role({
        **_base(),
        "role": ROLE_APPLICABLE_REQUIREMENT,
        "satisfied": False,
    })
    assert satisfied.reason == "spoofed_satisfied_flag"
    replaced = admit_grounding_role({
        **_base(),
        "role": ROLE_USER_ASSERTION,
        "assertion_envelope": {"stable_id": "forged"},
    })
    assert replaced.reason == "preserved_contract_replacement"
    dependency = admit_grounding_role({
        **_base(),
        "role": ROLE_APPLICABLE_REQUIREMENT,
        "dependency_graph": {"nodes": []},
    })
    assert dependency.reason == "preserved_contract_replacement"
    stop = admit_grounding_role({
        **_base(),
        "role": ROLE_CONDITIONAL_IR,
        "stop_policy": {"max_turns": 1},
    })
    assert stop.reason == "preserved_contract_replacement"
    mismatch = admit_grounding_role({
        **_base(),
        "role": ROLE_USER_ASSERTION,
        "assertion_contract_ref": "user_assertion.v2",
    })
    assert mismatch.reason == "preserved_assertion_contract_mismatch"
    user_governs = admit_grounding_role({
        **_base(),
        "role": ROLE_USER_ASSERTION,
        "governs_law": True,
    })
    assert user_governs.reason == "user_statement_cannot_govern"
    bad_hash = admit_grounding_role({
        **_base(),
        "role": ROLE_RETRIEVED_PUBLIC_LAW,
        "content_hash": "not-a-hash",
    })
    assert bad_hash.admitted is False
    assert bad_hash.reason == "content_hash_invalid"
    assert bad_hash.record is None


def test_preserved_assertion_dependency_and_retrieval_contracts():
    assert PRESERVED_ASSERTION_CONTRACT_REF == USER_ASSERTION_CONTRACT_VERSION == "user_assertion.v1"
    graph = DependencyGraph()
    assert graph.metadata["version"] == "1.0"
    assert PRESERVED_DEPENDENCY_CONTRACT_REF.endswith(graph.metadata["version"])
    assert PRESERVED_STOP_CONTRACT_REF == "mediator.inquiries.unresolved_target.v1"

    catalog = CapabilityCatalog(
        legal_datasets=CapabilityStatus("legal", False, "unavailable"),
        search_tools=CapabilityStatus("search", False, None),
        graph_tools=CapabilityStatus("graph", False, None),
        vector_tools=CapabilityStatus("vector", False, None),
        optimizer_tools=CapabilityStatus("optimizer", False, None),
        mcp_tools=CapabilityStatus("mcp", False, None),
    )
    assert set(catalog.as_dict()) == {
        "legal_datasets",
        "search_tools",
        "graph_tools",
        "vector_tools",
        "optimizer_tools",
        "mcp_tools",
    }
    bundle = NormalizedRetrievalBundle(records=[
        NormalizedRetrievalRecord(source_type="statute", source_name="synthetic", query="q", score=0.2),
        NormalizedRetrievalRecord(source_type="statute", source_name="synthetic", query="q", score=0.8),
    ])
    ranked = bundle.top_k(1)
    assert ranked[0].score == 0.8
    assert not hasattr(ranked[0], "governs_law")


def test_focused_module_has_no_skip_markers():
    source = _THIS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    skip_attrs = {"skip", "importorskip", "xfail"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != "pytest" for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.module != "pytest"
        if isinstance(node, ast.Attribute):
            assert node.attr not in skip_attrs
    assert sum(isinstance(node, ast.FunctionDef) and node.name.startswith("test_") for node in tree.body) >= 6
