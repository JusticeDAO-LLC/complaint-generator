"""Bounded public journey for grounded intake.

Synthetic private fixtures only. The module drives the chat and complaint
service entrypoints through narrative intake, a source-bound factual graph,
explicit legal context, source acquisition and admission, dependency refresh,
/why, correction, and an encrypted cold resume. It is not Native completion
authority. Observed transports and ciphertext fixtures stay labeled synthetic.
No test is skipped.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest

from applications.complaint_cli import chat as terminal_chat
from applications.complaint_workspace import ComplaintWorkspaceService
from complaint_phases.phase_manager import ComplaintPhase
from tests.mgnd_fixtures import (
    PASSPHRASE,
    USER_ID,
    case_by_label,
    materialize_case,
    meaningful_cases,
)


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

_LAW_DATE = "2024-03-15"
_TOKEN = "SYNTHETIC-MGND43-NARRATIVE"
_FILING_ANSWER = "2024-06-01"
_ANSWER = "March 4, 2024"
_CORRECTION = "March 5, 2024"
_SOURCE_MODULES = (
    "applications/complaint_cli.py",
    "applications/complaint_workspace.py",
    "complaint_phases/dependency_graph.py",
    "complaint_phases/knowledge_graph.py",
    "integrations/private_storage.py",
    "tests/mgnd_fixtures.py",
    "tests/test_cimp_mgnd_43.py",
)
_JOURNEY = (
    ("baseline", "success_to_review"),
    ("unknown", "unknown"),
    ("contradiction", "contradiction"),
    ("missing_authority", "source_unavailable"),
)


def _ready_text(case) -> str:
    return case.narrative.text + " " + _TOKEN


def _rows_for(case) -> dict:
    rows = []
    for source in case.sources:
        rows.append({
            "text": source.source_text,
            "citation": source.citation,
            "uri": "fixture://" + source.authority_id,
            "corpus_version": source.version,
            "jurisdiction": "OR",
            "effective_date": source.effective_date,
        })
    return {"state_statute": rows}


def _source_identities() -> dict[str, str]:
    identities = {}
    root = Path(__file__).resolve().parents[1]
    for relative in _SOURCE_MODULES:
        path = root / relative
        identities[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return identities


def _drive(service, lines: list[str], *, privacy_mode: str = "") -> tuple[int, str]:
    import applications.complaint_cli as cli

    remaining = list(lines)

    def fake_input(prompt: str = "") -> str:
        sys.stdout.write(str(prompt))
        if not remaining:
            raise EOFError
        return remaining.pop(0)

    saved = cli.service
    saved_stdin = sys.stdin
    cli.service = service
    sys.stdin = io.StringIO("")
    buffer = io.StringIO()
    code = 0
    try:
        with patch("builtins.input", fake_input), redirect_stdout(buffer):
            try:
                terminal_chat(user_id=USER_ID, max_turns=0, privacy_mode=privacy_mode)
            except SystemExit as exc:
                code = int(exc.code or 0)
    finally:
        cli.service = saved
        sys.stdin = saved_stdin
    return code, buffer.getvalue()


def _graph_token(projection: dict) -> str:
    from complaint_phases.knowledge_graph import KnowledgeGraph
    from mediator.hook_runtime import graph_revision_token

    graph = projection.get("knowledge_graph") if isinstance(projection.get("knowledge_graph"), dict) else {}
    return graph_revision_token(KnowledgeGraph.from_dict(graph))


def _entities(projection: dict) -> list[dict]:
    graph = projection.get("knowledge_graph") if isinstance(projection.get("knowledge_graph"), dict) else {}
    entities = graph.get("entities") or {}
    if isinstance(entities, dict):
        return [item for item in entities.values() if isinstance(item, dict)]
    return [item for item in entities if isinstance(item, dict)]


def _dependency_graph(service):
    mediators = list(getattr(service, "_interview_mediators", {}).values())
    if not mediators:
        return None
    return mediators[-1].phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")


def _plaintext_hits(root: Path, token: str) -> list[str]:
    needle = token.encode("utf-8")
    hits = []
    for path in root.rglob("*"):
        if path.is_file() and needle in path.read_bytes():
            hits.append(path.relative_to(root).as_posix())
    return hits


def test_meaningful_cases_cover_the_public_journey():
    cases = meaningful_cases()
    assert cases
    labels = {case.label for case in cases}
    assert {label for label, _path in _JOURNEY} <= labels
    assert all(case.case_id and case.narrative.text for case in cases)
    assert _source_identities()


def test_public_journey_reaches_review_unknown_contradiction_and_unavailable(tmp_path, monkeypatch):
    identities = _source_identities()
    assert identities["tests/test_cimp_mgnd_43.py"]
    for label, path_name in _JOURNEY:
        case = case_by_label(label)
        materialized = materialize_case(tmp_path / label, monkeypatch, case)
        service = materialized.terminal
        unlocked = service.unlock_private_keys(passphrase=PASSPHRASE)
        assert unlocked.get("unlocked") is True
        prepared = service.prepare_private_terminal_case(USER_ID)
        assert prepared["unlock_is_remote_consent"] is False
        narrative = _ready_text(case)
        research_kwargs = {
            "effect_receipt": {
                "request_id": "effect-" + case.case_id,
                "source_preimage": "source-" + case.label,
                "context_preimage": "context-" + case.label,
                "operation": "refresh_verified_legal_dependencies",
                "proof": False,
            },
        }
        if label != "unknown":
            research_kwargs["context_updates"] = {
                "jurisdiction": "Oregon",
                "applicable_law_date": _LAW_DATE,
            }
        if case.sources and label != "unknown":
            research_kwargs["local_rows"] = _rows_for(case)
        observed = {}
        original_turn = service.run_intake_chat_turn

        def turn_with_acquisition(*args, **kwargs):
            result = original_turn(*args, **kwargs)
            message = kwargs.get("message")
            if message == "/why" and "receipt" not in observed:
                observed["receipt"] = service.run_legal_research(USER_ID, **research_kwargs)
                midpoint = service._load_state(USER_ID)
                midpoint_projection = midpoint.get("shared_interview") if isinstance(midpoint.get("shared_interview"), dict) else {}
                observed["token_before_correction"] = _graph_token(midpoint_projection)
            return result

        service.run_intake_chat_turn = turn_with_acquisition
        code, transcript = _drive(
            service,
            [narrative, narrative, "/why", "/edit " + _CORRECTION, "/quit"],
            privacy_mode="local",
        )
        service.run_intake_chat_turn = original_turn
        assert code == 0, transcript
        assert "Local processing selected" in transcript
        assert "Why this question" in transcript
        assert "does not satisfy" in transcript
        assert "prove" not in transcript.lower()
        receipt = observed["receipt"]
        state = service._load_state(USER_ID)
        assert state["original_complaint"]["text"] == narrative
        assert state["privacy_policy"]["processing_mode"] == "local_private"
        controls = state.get("terminal_controls") if isinstance(state.get("terminal_controls"), dict) else {}
        assert list(controls.get("skipped_answers") or []) == []
        projection = state.get("shared_interview") if isinstance(state.get("shared_interview"), dict) else {}
        assert int(projection.get("narrative_extraction_count") or 0) >= 1
        entities = _entities(projection)
        assert entities
        fact_ids = set()
        spanned = []
        for entity in entities:
            fact_ids.add(str(entity.get("id") or ""))
            assertion = (entity.get("provenance") or {}).get("user_assertion") or {}
            assert assertion.get("legal_hit") is not True
            assert assertion.get("is_asserted_user_fact") is not True or assertion.get("assertion_status") != "verified"
            span = assertion.get("source_span") if isinstance(assertion.get("source_span"), dict) else {}
            span_text = str(span.get("text") or assertion.get("source_span_text") or "")
            if span_text:
                assert span_text in narrative
                spanned.append(span_text)
            entity_name = str(entity.get("name") or "")
            if entity_name and entity_name in narrative:
                spanned.append(entity_name)
        assert spanned
        assert "" not in fact_ids
        for source in case.sources:
            assert source.version
            assert source.source_sha256 == hashlib.sha256(source.source_bytes).hexdigest()
            assert 0 <= len(source.source_bytes)
            assert source.authority_id not in fact_ids

        counts = receipt["counts"]
        assert receipt["stored_as_answer"] is False
        assert receipt["proves_complaint"] is False
        assert receipt["legal_sufficiency"] is False
        assert receipt["proof"] is False
        assert receipt["worker_stalled"] is False
        assert set(counts) == {"retrieved", "admitted", "rejected", "unavailable"}
        refresh = receipt["dependency_refresh"]
        assert refresh["graph_replaced"] is False
        assert refresh["empty_success"] is False
        assert refresh["atomic_case_revision"] is True
        assert isinstance(refresh["case_revision"], int) and refresh["case_revision"] >= 1
        assert refresh["effect_request_id"] == "effect-" + case.case_id
        graph = _dependency_graph(service)
        assert graph is not None and graph.nodes
        assert graph.metadata.get("empty_success") is not True
        legal_nodes = [
            node for node in graph.nodes.values()
            if isinstance(node.attributes, dict)
            and node.attributes.get("dependency_class") == "legally_sourced_requirement"
        ]
        assert all(not node.satisfied for node in legal_nodes)
        assert all(node.attributes.get("proof") is not True for node in legal_nodes)
        legal_ids = {node.id for node in legal_nodes}
        fact_nodes = [
            node for node in graph.nodes.values()
            if node not in legal_nodes and (
                str(getattr(node, "node_type", "")).lower().endswith("fact")
                or (isinstance(node.attributes, dict) and node.attributes.get("about_complainant") is True)
            )
        ]
        assert fact_nodes
        assert legal_ids.isdisjoint({node.id for node in fact_nodes})
        assert legal_ids.isdisjoint(fact_ids)
        if label == "baseline":
            assert counts["retrieved"] >= 1
            assert counts["admitted"] >= 1
            assert counts["unavailable"] == 0
            assert refresh["source_admission_reread"] is True
            assert receipt["next_action"] == "continue_pending_inquiry"
        elif label == "unknown":
            assert counts["admitted"] == 0
            assert receipt["status"] == "blocked"
            assert receipt["error_code"] == "legal_context_not_ready"
            assert receipt["next_action"] == "resolve_legal_context"
        elif label == "contradiction":
            assert counts["retrieved"] >= 2
            assert counts["admitted"] + counts["rejected"] >= 1
            assert "2024-03-04" in narrative and "2024-03-11" in narrative
        elif label == "missing_authority":
            assert counts["retrieved"] == 0
            assert counts["admitted"] == 0
            assert counts["unavailable"] >= 1
            assert receipt["status"] == "unavailable"

        corrected = service._load_state(USER_ID)
        corrected_controls = corrected.get("terminal_controls") if isinstance(corrected.get("terminal_controls"), dict) else {}
        assert list(corrected_controls.get("skipped_answers") or []) == []
        corrected_projection = corrected.get("shared_interview") if isinstance(corrected.get("shared_interview"), dict) else {}
        graph_text = json.dumps(corrected_projection.get("knowledge_graph"))
        if "Edited the last recorded answer" in transcript:
            assert _CORRECTION in graph_text
            assert _graph_token(corrected_projection) != observed["token_before_correction"]
        else:
            assert "Nothing to edit yet" in transcript
            refused = service.apply_terminal_graph_edit(USER_ID, _CORRECTION)
            assert refused["status"] == "refused"
            assert refused["error_code"] == "missing_target"
            assert _graph_token(corrected_projection) == observed["token_before_correction"]
        why_payload = service.run_intake_chat_turn(USER_ID, message="/why")
        assert why_payload["command"] == "/why"
        assert why_payload["stored_as_answer"] is False
        assert why_payload["legal_sufficiency"] is False
        assert why_payload["worker_stalled"] is False
        assert why_payload["awaiting_user"] is True
        support = why_payload["question_support"]
        assert support["legal_sufficiency"] is False
        assert support["proof_established"] is False
        assert support["retrieval_score_is_proof"] is False
        assert support["support_states"]["proof"] != "proved"
        for authority in support["admitted_authorities"]:
            assert authority.get("version")
            assert authority.get("span")

        session = service.get_session(USER_ID)
        review = session["review"]
        overview = review["overview"]
        assert overview["supported_elements"] == 0 or overview["missing_elements"] >= 1
        assert review["recommended_actions"]
        assert session.get("legal_sufficiency") is not True
        if path_name == "success_to_review":
            assert overview["missing_elements"] >= 1
            assert counts["admitted"] >= 1

        saved = service.commit_complete_grounded_snapshot(USER_ID)
        assert saved["network_durable"] is False
        assert saved["kit_durability_counts_as_replica"] is False
        assert saved["kit_durability"]["counts_as_replica"] is False
        assert saved["kit_durability"]["network_durable"] is False
        assert saved["kit_durability"]["live_qualification"] is False
        assert _TOKEN not in json.dumps(saved["kit_durability"])
        fresh = ComplaintWorkspaceService(root_dir=materialized.root.sessions)
        fresh.unlock_private_keys(passphrase=PASSPHRASE)
        loaded = fresh.load_complete_interview_snapshot(USER_ID)
        assert loaded["snapshot"]["revision"] == saved["snapshot"]["revision"]
        assert loaded["snapshot"]["grounding"] == saved["snapshot"]["grounding"]
        assert loaded["kit_durability"]["network_durable"] is False
        resumed = fresh.run_intake_chat_turn(USER_ID, interview_action="resume")
        assert resumed.get("legal_sufficiency") is not True
        assert _plaintext_hits(materialized.root.sessions, _TOKEN) == []

        result_identity = {
            "task_id": "CIMP-MGND-43",
            "path": path_name,
            "case_id": case.case_id,
            "case_label": case.label,
            "test_module": "tests/test_cimp_mgnd_43.py",
            "source_identities": identities,
            "research_status": receipt["status"],
            "research_counts": counts,
            "snapshot_revision": saved["snapshot"]["revision"],
            "transport": materialized.transport,
        }
        assert result_identity["transport"]["kind"] == "synthetic_private_fixture"
        assert result_identity["transport"]["live_route_observation"] is False
        assert result_identity["transport"]["verifies_live_grok_identity"] is False
        assert result_identity["transport"]["native_completion"] is False
        assert materialized.native_completion is False
        assert materialized.legal_graph is None
        encoded = json.dumps(result_identity)
        assert "live Grok" not in encoded
        assert case.case_id in encoded
