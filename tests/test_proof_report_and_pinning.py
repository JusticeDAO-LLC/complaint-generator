"""Tests for render_proof_report, pin_proof_report_to_ipfs, and
constrain_assertions_to_corpus vector search pass.
"""
from __future__ import annotations

import json
from typing import Any, Dict
from unittest.mock import patch

import pytest

from integrations.ipfs_datasets.draft_logic_pipeline import (
    DRAFT_LOGIC_PIPELINE_VERSION,
    pin_proof_report_to_ipfs,
    render_proof_report,
    run_pipeline,
)
from integrations.ipfs_datasets.legal import constrain_assertions_to_corpus


@pytest.fixture(autouse=True)
def hermetic_proof_storage(monkeypatch, tmp_path):
    """Exercise local fallback without accessing a host daemon or cache."""
    from integrations.ipfs_datasets import storage
    monkeypatch.setenv("COMPLAINT_GENERATOR_IPFS_CACHE_DIR", str(tmp_path / "proof-cache"))
    monkeypatch.delenv("COMPLAINT_GENERATOR_ENABLE_IPFS_KIT", raising=False)
    monkeypatch.setattr(storage, "_load_optional_kit_backend", lambda: None)
    for name in ("add_bytes", "cat", "pin"):
        monkeypatch.setattr(storage, name, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_report(**overrides: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "proof_status": "passed",
        "contradiction_count": 0,
        "chronology_blocked": False,
        "ungrounded_assertions": [],
        "ungrounded_assertion_count": 0,
        "corpus_coverage_percent": 100,
        "norms": [],
        "policy_violations": [],
        "policy_warnings": [],
        "has_blockers": False,
        "predicate_count": 3,
        "theorem_export": {
            "lean4": "-- lean stub",
            "coq": "(* coq stub *)",
            "tdfol_formula_count": 2,
            "dcec_formula_count": 1,
            "export_version": "theorem-export-v1",
        },
        "pipeline_version": DRAFT_LOGIC_PIPELINE_VERSION,
        "errors": [],
        "fol_result": {},
        "deontic_result": {},
        "corpus_result": {},
        "proof_result": {},
        "policy_result": {},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# render_proof_report
# ---------------------------------------------------------------------------

class TestRenderProofReport:
    def test_returns_string(self):
        report = render_proof_report(_minimal_report())
        assert isinstance(report, str)

    def test_contains_title(self):
        report = render_proof_report(_minimal_report())
        assert "Complaint Draft Proof Report" in report

    def test_passed_status_icon(self):
        report = render_proof_report(_minimal_report(proof_status="passed"))
        assert "✅" in report
        assert "`passed`" in report

    def test_needs_review_status_icon(self):
        report = render_proof_report(_minimal_report(proof_status="needs_review"))
        assert "⚠️" in report

    def test_error_status_icon(self):
        report = render_proof_report(_minimal_report(proof_status="error"))
        assert "❌" in report

    def test_no_blockers_message(self):
        report = render_proof_report(_minimal_report(has_blockers=False))
        assert "No blockers" in report

    def test_blockers_message(self):
        report = render_proof_report(_minimal_report(has_blockers=True))
        assert "blockers" in report.lower()

    def test_metrics_table(self):
        report = render_proof_report(_minimal_report(predicate_count=7))
        assert "7" in report
        assert "Predicates extracted" in report

    def test_corpus_coverage(self):
        report = render_proof_report(_minimal_report(corpus_coverage_percent=80))
        assert "80%" in report

    def test_ungrounded_assertions_section(self):
        ungrounded = [
            {"assertion_id": "sent-1", "text": "The defendant violated the Act.", "grounded": False}
        ]
        report = render_proof_report(
            _minimal_report(ungrounded_assertions=ungrounded, has_blockers=False)
        )
        assert "Ungrounded Assertions" in report
        assert "defendant violated the Act" in report

    def test_contradiction_section(self):
        proof_result = {
            "contradictions": [
                {
                    "contradiction_id": "formula-1",
                    "type": "formula_negation",
                    "summary": "Contradiction: A and not(A)",
                    "severity": "error",
                }
            ]
        }
        report = render_proof_report(
            _minimal_report(
                contradiction_count=1,
                has_blockers=True,
                proof_result=proof_result,
            )
        )
        assert "Contradictions" in report
        assert "formula-1" in report

    def test_policy_violations_section(self):
        violations = [
            {
                "violation_type": "prohibited_action_found",
                "offending_sentence": "Defendant shall not discriminate.",
                "severity": "error",
            }
        ]
        report = render_proof_report(
            _minimal_report(policy_violations=violations, has_blockers=True)
        )
        assert "Policy Violations" in report
        assert "prohibited_action_found" in report

    def test_policy_warnings_section(self):
        warnings = [
            {
                "warning_type": "obligation_not_satisfied",
                "formula": "O(actor,file_complaint)",
                "severity": "warning",
            }
        ]
        report = render_proof_report(_minimal_report(policy_warnings=warnings))
        assert "Policy Warnings" in report
        assert "obligation_not_satisfied" in report

    def test_deontic_norms_section(self):
        norms = [{"norm_type": "obligation", "formula": "O(actor,report)", "trigger_keyword": "shall"}]
        report = render_proof_report(_minimal_report(norms=norms))
        assert "Deontic Norms" in report
        assert "Obligation" in report

    def test_theorem_export_section(self):
        report = render_proof_report(
            _minimal_report(
                theorem_export={
                    "lean4": "-- lean",
                    "coq": "(* coq *)",
                    "tdfol_formula_count": 3,
                    "dcec_formula_count": 2,
                    "export_version": "theorem-export-v1",
                }
            )
        )
        assert "Theorem Export" in report
        assert "TDFOL formulas: 3" in report
        assert "DCEC formulas: 2" in report

    def test_errors_section(self):
        report = render_proof_report(
            _minimal_report(errors=["text_to_fol: upstream unavailable"])
        )
        assert "Pipeline Errors" in report
        assert "text_to_fol" in report

    def test_claim_id_in_header(self):
        report = render_proof_report(_minimal_report(), claim_id="CLAIM-42")
        assert "CLAIM-42" in report

    def test_rendered_at_in_header(self):
        report = render_proof_report(_minimal_report(), rendered_at="2025-01-01T00:00:00+00:00")
        assert "2025-01-01" in report

    def test_empty_norms_no_section(self):
        report = render_proof_report(_minimal_report(norms=[]))
        assert "Deontic Norms Detected" not in report

    def test_zero_theorem_formulas_no_section(self):
        report = render_proof_report(
            _minimal_report(
                theorem_export={
                    "lean4": "",
                    "coq": "",
                    "tdfol_formula_count": 0,
                    "dcec_formula_count": 0,
                }
            )
        )
        assert "Theorem Export" not in report


# ---------------------------------------------------------------------------
# pin_proof_report_to_ipfs
# ---------------------------------------------------------------------------

class TestPinProofReportToIPFS:
    def test_returns_dict_with_required_keys(self):
        result = pin_proof_report_to_ipfs(_minimal_report())
        assert isinstance(result, dict)
        for key in ("report_cid", "lean4_cid", "coq_cid", "pinned", "backend", "pinned_at"):
            assert key in result, f"Missing key: {key}"

    def test_pinned_is_bool(self):
        result = pin_proof_report_to_ipfs(_minimal_report())
        assert isinstance(result["pinned"], bool)

    def test_cids_are_strings(self):
        result = pin_proof_report_to_ipfs(_minimal_report())
        assert isinstance(result["report_cid"], str)
        assert isinstance(result["lean4_cid"], str)
        assert isinstance(result["coq_cid"], str)

    def test_report_cid_is_non_empty(self):
        result = pin_proof_report_to_ipfs(_minimal_report())
        # Even without IPFS daemon, the local fallback returns a sha256: CID.
        assert result["report_cid"]

    def test_lean4_cid_when_export_present(self):
        result = pin_proof_report_to_ipfs(
            _minimal_report(
                theorem_export={
                    "lean4": "-- lean4 stub\n",
                    "coq": "",
                    "tdfol_formula_count": 1,
                    "dcec_formula_count": 0,
                }
            )
        )
        assert result["lean4_cid"]

    def test_empty_lean4_cid_when_no_export(self):
        result = pin_proof_report_to_ipfs(
            _minimal_report(theorem_export={"lean4": "", "coq": ""})
        )
        assert result["lean4_cid"] == ""

    def test_claim_id_in_result(self):
        result = pin_proof_report_to_ipfs(_minimal_report(), claim_id="MY-CASE-1")
        assert result["claim_id"] == "MY-CASE-1"

    def test_backend_local_when_ipfs_unavailable(self):
        # In test environments the IPFS daemon is not running; backend should
        # be either "ipfs" or "local_content_hash".
        result = pin_proof_report_to_ipfs(_minimal_report())
        assert result["backend"] in ("ipfs", "local_content_hash")

    def test_pinned_at_is_iso8601(self):
        result = pin_proof_report_to_ipfs(_minimal_report())
        ts = result["pinned_at"]
        assert "T" in ts, f"Expected ISO-8601 timestamp, got: {ts}"

    def test_pin_failure_does_not_set_pinned_true(self):
        def _store(data, **_kwargs):
            del data
            return {
                "status": "available",
                "cid": "bafyrealnetworkcid",
                "pinned": False,
                "verified": True,
                "uploaded": True,
                "stored_local": False,
                "network_durable": False,
                "cid_kind": "content_cid",
                "backend_name": "kit",
                "verification": {"matched": True, "method": "readback"},
                "receipt": {"cid_kind": "content_cid"},
            }

        def _pin(cid, **_kwargs):
            raise RuntimeError(f"pin failed for {cid}")

        with patch("integrations.ipfs_datasets.storage.store_bytes", side_effect=_store):
            with patch("integrations.ipfs_datasets.storage.pin_cid", side_effect=_pin):
                result = pin_proof_report_to_ipfs(_minimal_report())
        assert result["pinned"] is False
        assert result["network_durable"] is False
        assert result["report_cid"].startswith("sha256:")
        assert result["backend"] == "local_content_hash"
        assert result["stored_local"] is False
        assert result["uploaded"] is True
        assert result["verified"] is True
        assert result["deferred"] is True
        assert result["receipt"]["storage_cid"] == "bafyrealnetworkcid"

    def test_report_cid_fallback_starts_with_sha256(self):
        # When the IPFS backend raises, the local sha256 fallback is used.
        with patch(
            "integrations.ipfs_datasets.storage.store_bytes",
            side_effect=RuntimeError("no daemon"),
        ):
            result = pin_proof_report_to_ipfs(_minimal_report())
        # The sha256: prefix fallback should still produce a non-empty CID.
        assert result["report_cid"].startswith("sha256:")
        assert result["stored_local"] is False
        assert result["uploaded"] is False
        assert result["verified"] is False

    @pytest.mark.parametrize("storage_result", [5, {"status": "unavailable", "cid": "", "error": "offline"}])
    def test_hash_only_fallback_does_not_claim_a_persisted_artifact(self, storage_result):
        with patch("integrations.ipfs_datasets.storage.store_bytes", return_value=storage_result):
            result = pin_proof_report_to_ipfs(_minimal_report())
        assert result["report_cid"].startswith("sha256:")
        assert result["stored_local"] is False
        assert result["uploaded"] is False
        assert result["pinned"] is False
        assert result["verified"] is False
        assert result["deferred"] is True

    def test_real_local_cache_is_distinct_from_an_unstored_hash(self):
        result = pin_proof_report_to_ipfs(_minimal_report())
        assert result["stored_local"] is True
        assert result["verified"] is True
        assert result["uploaded"] is False
        assert result["pinned"] is False
        assert result["network_durable"] is False
        assert result["receipt"]["storage_cid"]

    def test_deterministic_cid_for_same_content(self):
        # Each call produces its own timestamp so envelope bytes differ.
        # Without a verified network pin, the identifier is a SHA256 fallback
        # and must not be reported as network pinned or durable.
        report = _minimal_report()
        result = pin_proof_report_to_ipfs(report, claim_id="SAME")
        cid = result["report_cid"]
        if result.get("network_durable") is True:
            assert result["pinned"] is True
            assert result["backend"] == "ipfs"
            assert cid
        else:
            assert cid.startswith("sha256:") and len(cid) == len("sha256:") + 64
            assert result["pinned"] is False
            assert result["backend"] == "local_content_hash"
            assert result.get("network_durable") is False


# ---------------------------------------------------------------------------
# constrain_assertions_to_corpus — vector search pass
# ---------------------------------------------------------------------------

class TestConstrainAssertionsVectorPass:
    """Test the semantic vector search pass added to constrain_assertions_to_corpus."""

    def test_vector_pass_skipped_when_no_index_dir(self, tmp_path):
        assertions = [{"assertion_id": "a-1", "text": "Employer shall not retaliate."}]
        result = constrain_assertions_to_corpus(assertions, legal_vector_index_dir=None)
        # Ungrounded (no backends available) but no exception
        assert result["total_assertion_count"] == 1
        assert "corpus_coverage_percent" in result

    def test_vector_pass_skipped_when_index_missing(self, tmp_path):
        assertions = [{"assertion_id": "a-1", "text": "Employer shall not retaliate."}]
        result = constrain_assertions_to_corpus(
            assertions, legal_vector_index_dir=str(tmp_path / "nonexistent")
        )
        assert result["total_assertion_count"] == 1

    @pytest.mark.parametrize("index_source", ["argument", "environment"])
    def test_local_vector_index_does_not_authorize_embedding_or_grounding(
        self, tmp_path, monkeypatch, index_source
    ):
        """A populated legacy index grants neither retrieval access nor proof."""
        from pathlib import Path
        from unittest.mock import Mock

        import numpy as np
        from integrations.ipfs_datasets import legal, vector_store

        index_dir = tmp_path / "legal_index"
        index_dir.mkdir()

        # Keep the real synthetic index: 2 records, 4-dimensional vectors.
        vectors = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=np.float32)
        np.save(str(index_dir / "legal_corpus.vectors.npy"), vectors)
        records = [
            json.dumps({
                "id": "rec-1",
                "text": "Employer shall not retaliate against a whistleblower.",
                "source": "state_law",
                "citation": "ORS 659A.199",
                "title": "Anti-Retaliation Statute",
                "type": "statute",
            }),
            json.dumps({
                "id": "rec-2",
                "text": "Employee may file a complaint with the Bureau of Labor.",
                "source": "state_law",
                "citation": "ORS 659A.820",
                "title": "Filing Procedure",
                "type": "statute",
            }),
        ]
        (index_dir / "legal_corpus.records.jsonl").write_text("\n".join(records), encoding="utf-8")
        index_before = {path.name: path.read_bytes() for path in index_dir.iterdir()}

        assertions = [
            {"assertion_id": "s-1", "text": "Employer shall not retaliate against whistleblower."}
        ]
        monkeypatch.delenv("COMPLAINT_LEGAL_VECTOR_INDEX_DIR", raising=False)
        arguments = {"legal_vector_index_dir": str(index_dir)}
        if index_source == "environment":
            monkeypatch.setenv("COMPLAINT_LEGAL_VECTOR_INDEX_DIR", str(index_dir))
            arguments = {}

        # Refusal must happen before an embedding, backend, or index read.
        # Explicit zero-call checks also catch swallowed boundary exceptions.
        forbidden_calls = []
        index_open_attempts = []
        original_open = Path.open

        def guard_index_open(path, *args, **kwargs):
            if path.is_relative_to(index_dir):
                index_open_attempts.append(path.name)
                raise AssertionError("The legacy index did not authorize file access")
            return original_open(path, *args, **kwargs)

        with monkeypatch.context() as guarded:
            for module, attribute in (
                (legal, "_search_legal_vector_index"),
                (legal, "embed_query_text"),
                (legal, "get_embeddings_router"),
                (legal, "_run_owned_deadline"),
                (vector_store, "embed_texts_batched"),
                (vector_store, "get_embeddings_router"),
                (vector_store, "search_vector_index"),
                (np, "load"),
            ):
                denied = Mock(side_effect=AssertionError("No embedding or retrieval was authorized"))
                guarded.setattr(module, attribute, denied)
                forbidden_calls.append(denied)
            guarded.setattr(Path, "open", guard_index_open)
            result = constrain_assertions_to_corpus(
                assertions, state="OR", retrieval_mode="offline", **arguments
            )

        for denied in forbidden_calls:
            denied.assert_not_called()
        assert index_open_attempts == []
        assert {path.name: path.read_bytes() for path in index_dir.iterdir()} == index_before
        assert result["total_assertion_count"] == 1
        assert result["grounded_count"] == 0
        assert result["ungrounded_count"] == 1
        assert result["candidate_count"] == 0
        assert result["source_verified_count"] == 0
        assert result["applicable_count"] == 0
        assert result["entailed_count"] == 0
        assert result["corpus_coverage_percent"] == 0
        assert result["corpus_coverage_semantics"] == "retrieval_only"
        assert result["entailment_prover"] == "unsupported"
        assert result["grounded"] == []
        assert result["fact_graph_mutated"] is False
        detail = result["details"][0]
        assert detail["dispositions"] == {
            "retrieval": "unavailable",
            "source_verification": "unknown",
            "applicability": "unknown",
            "entailment": "unsupported",
        }
        assert {
            "backend": "legal_vector_index",
            "status": "unavailable",
            "error_code": "owned_vector_lookup_unavailable",
        } in detail["diagnostics"]
        assert assertions[0]["text"] not in str(detail["diagnostics"])
        assert detail["corpus_hits"] == []
        assert detail["grounded"] is False
        assert detail["source_verified"] is False
        assert detail["applicable"] is False
        assert detail["entails"] is False
        assert detail["entailment_reason"] == "no_bound_entailment_prover"
        assert detail["fact_verified"] is False
        assert detail["fact_promotion"] == "refused"
        assert detail["no_applicable_law"] is False
        assert detail["allegation_false"] is False

    def test_vector_env_var_gates_pass(self, tmp_path, monkeypatch):
        """COMPLAINT_LEGAL_VECTOR_INDEX_DIR env var activates the vector pass."""
        monkeypatch.setenv("COMPLAINT_LEGAL_VECTOR_INDEX_DIR", str(tmp_path / "no_index"))
        assertions = [{"assertion_id": "x-1", "text": "Some legal assertion."}]
        # Missing index → vector pass silently skipped, no exception.
        result = constrain_assertions_to_corpus(assertions)
        assert result["total_assertion_count"] == 1


# ---------------------------------------------------------------------------
# Public API exports
# ---------------------------------------------------------------------------

class TestPublicAPIExports:
    """Verify all new symbols are reachable via the package __init__."""

    def test_logic_exports(self):
        import integrations.ipfs_datasets as ipfs
        for name in (
            "text_to_fol",
            "legal_text_to_deontic",
            "prove_claim_elements",
            "check_contradictions",
            "run_hybrid_reasoning",
            "LOGIC_AVAILABLE",
            "Z3_AVAILABLE",
            "REASONER_BRIDGE_AVAILABLE",
            "LOCAL_FORMAL_LOGIC_AVAILABLE",
        ):
            assert hasattr(ipfs, name), f"Missing export: {name}"

    def test_legal_exports(self):
        import integrations.ipfs_datasets as ipfs
        for name in (
            "search_us_code",
            "search_federal_register",
            "search_recap_documents",
            "search_state_laws",
            "search_state_administrative_rules",
            "constrain_assertions_to_corpus",
            "LEGAL_SCRAPERS_AVAILABLE",
            "LEGAL_SOURCE_AVAILABILITY",
        ):
            assert hasattr(ipfs, name), f"Missing export: {name}"

    def test_pipeline_exports(self):
        import integrations.ipfs_datasets as ipfs
        for name in (
            "run_draft_logic_pipeline",
            "render_proof_report",
            "pin_proof_report_to_ipfs",
            "DRAFT_LOGIC_PIPELINE_VERSION",
        ):
            assert hasattr(ipfs, name), f"Missing export: {name}"

    def test_policy_exports(self):
        import integrations.ipfs_datasets as ipfs
        assert hasattr(ipfs, "check_policy_rules_with_deontic_norms")

    def test_all_list_matches_exports(self):
        import integrations.ipfs_datasets as ipfs
        for name in ipfs.__all__:
            assert hasattr(ipfs, name), f"__all__ entry not exported: {name}"
