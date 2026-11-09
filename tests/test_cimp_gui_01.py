"""Characterize the current GUI assembly and shared interview.

This module records fresh Python ASGI and service observations. It does not
qualify a browser DOM, and it does not accept the GUI as production-ready.
A pinned manual audit remains the DOM, accessibility, and browser-storage
evidence. Fresh DOM qualification belongs to CIMP-GUI-02.

Diagnostics keep counts, status codes, and classifications. They do not print
synthetic narrative text.
"""

from __future__ import annotations

import hashlib
import json
import socket
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.complaint_workspace import (
    ComplaintWorkspaceService,
    PrincipalRegistry,
    WorkspaceAccess,
    workspace_access_scope,
)
from applications.complaint_workspace_api import create_complaint_workspace_router
from applications.server import SERVER
from tests.private_session_assertions import assert_private_session_frame, private_session_path


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = ROOT / "docs" / "task_boards" / "complaint_gui_collaboration_baseline_receipt.json"
AUDIT_PATH = ROOT / "docs" / "task_boards" / "complaint_gui_collaboration_baseline_audit.json"
BASELINE_COMMIT = "2c1439a7029eb9035338133210d8b43319add8a4"
SOURCE_PATHS = (
    "applications/server.py",
    "applications/complaint_workspace.py",
    "applications/complaint_workspace_api.py",
    "applications/complaint_mcp_protocol.py",
    "static/complaint_mcp_sdk.js",
    "templates/workspace.html",
    "mediator/mediator.py",
    "mediator/workflow_service.py",
)
PASSPHRASE = "synthetic-gui-01-passphrase"
FIXED_USER = "synthetic-gui-01-fixed-fixture"
SHARED_USER = "synthetic-gui-01-shared-fixture"
FIXTURE_TOKEN = "fixture-token-gui-01"
WRONG_TOKEN = "not-the-fixture-token"
NARRATIVE = "On 4 March 2024 Alex Rivera ended the assignment after a safety report."
ANSWER = "The report was made to a supervisor."
FIXED_ANSWERS = {
    "party_name": "Jordan Example",
    "opposing_party": "Example Agency",
    "protected_activity": "Reported a safety concern",
    "adverse_action": "Assignment ended",
    "timeline": "4 March 2024",
    "harm": "Lost wages",
}
_GAP_CLASSIFICATIONS = frozenset({
    "observed_gap",
    "attributed_to_pinned_manual_audit",
    "dependency_unavailable",
    "not_qualified",
})
_MECHANIC_CLASSIFICATION = "characterization_mechanic"


def _fail(message: str) -> None:
    raise AssertionError(message)


def _source_generation() -> dict:
    digest = hashlib.sha256()
    files = []
    for relative in SOURCE_PATHS:
        data = (ROOT / relative).read_bytes()
        file_hash = hashlib.sha256(data).hexdigest()
        files.append({"path": relative, "sha256": file_hash, "bytes": len(data)})
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
    return {
        "name": "cimp-gui-01-asgi-assembly",
        "algorithm": "sha256",
        "baseline_commit": BASELINE_COMMIT,
        "digest": digest.hexdigest(),
        "files": files,
    }


def _rows(graph: object, *keys: str) -> list:
    if not isinstance(graph, dict):
        return []
    for key in keys:
        raw = graph.get(key)
        if isinstance(raw, dict) and raw:
            return [item for item in raw.values() if isinstance(item, dict)]
        if isinstance(raw, list) and raw:
            return [item for item in raw if isinstance(item, dict)]
    return []


def _install_synthetic_transport(monkeypatch: pytest.MonkeyPatch) -> dict:
    import integrations.ipfs_datasets.llm as llm_mod

    observed = {"calls": 0, "live_identity_verified": False, "installed": True}

    def generate(prompt, **kwargs):
        if not isinstance(prompt, str):
            _fail("synthetic_transport_prompt_unavailable")
        observed["calls"] += 1
        if kwargs.get("live_model_identity_verified") is True:
            observed["live_identity_verified"] = True
        return {
            "status": "available",
            "text": "{\"facts\":[],\"questions\":[],\"synthetic_transport\":true}",
            "error": None,
            "live_model_identity_verified": False,
            "invocation_label": "fake",
            "evidence_class": "synthetic_fixture",
        }

    monkeypatch.setattr(llm_mod, "generate_text_with_metadata", generate)
    return observed


def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*_args, **_kwargs):
        raise RuntimeError("network connect blocked")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(socket, "create_connection", blocked)


def _prepare_service(root: Path) -> ComplaintWorkspaceService:
    service = ComplaintWorkspaceService(root_dir=root)
    with workspace_access_scope(WorkspaceAccess.trusted_local()):
        service.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
        service.ensure_private_case_key(FIXED_USER, FIXED_USER)
        service.ensure_private_case_key(SHARED_USER, SHARED_USER)
    return service


def _interview_error(payload: dict) -> str:
    interview = payload.get("interview") if isinstance(payload.get("interview"), dict) else {}
    error = interview.get("error") if isinstance(interview.get("error"), dict) else {}
    return str(error.get("code") or "")


def _characterize(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    import applications.complaint_workspace as workspace_mod

    _block_network(monkeypatch)
    transport = _install_synthetic_transport(monkeypatch)
    session_root = tmp_path / "sessions"
    monkeypatch.setattr(workspace_mod, "_SESSION_DIR", session_root)

    class _LocalMediator:
        def io(self, _message: str) -> str:
            return ""

    server = SERVER(_LocalMediator())
    denied = TestClient(server.app)
    denied_session = denied.get(
        "/api/complaint-workspace/session",
        params={"user_id": "synthetic-gui-01-denied"},
    )
    denied_mcp = denied.post(
        "/api/complaint-workspace/mcp/call",
        json={"tool_name": "complaint.start_session", "arguments": {"user_id": "synthetic-gui-01-denied"}},
    )
    denied_rpc = denied.post(
        "/api/complaint-workspace/mcp/rpc",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "complaint.start_session",
                "arguments": {"user_id": "synthetic-gui-01-denied"},
            },
        },
    )
    workspace_page = denied.get("/workspace")
    route_paths = {getattr(route, "path", "") for route in server.app.routes}
    denied.close()

    registry = PrincipalRegistry()
    registry.register(FIXTURE_TOKEN, FIXED_USER, case_id=FIXED_USER)
    registry.register("fixture-token-gui-01-shared", SHARED_USER, case_id=SHARED_USER)
    service = _prepare_service(session_root / "fixture")
    app = FastAPI()
    app.include_router(
        create_complaint_workspace_router(
            service,
            principal_registry=registry,
            trusted_local=False,
        )
    )
    client = TestClient(app)
    fixed_headers = {"Authorization": f"Bearer {FIXTURE_TOKEN}"}
    shared_headers = {"Authorization": "Bearer fixture-token-gui-01-shared"}
    wrong = client.get(
        "/api/complaint-workspace/session",
        params={"user_id": FIXED_USER},
        headers={"Authorization": f"Bearer {WRONG_TOKEN}"},
    )
    fixed = client.post(
        "/api/complaint-workspace/intake",
        headers=fixed_headers,
        json={"user_id": FIXED_USER, "answers": FIXED_ANSWERS},
    )
    fixed_body = fixed.json()
    fixed_state = fixed_body.get("session") if isinstance(fixed_body.get("session"), dict) else {}
    review = fixed_body.get("review") if isinstance(fixed_body.get("review"), dict) else {}
    matrix = review.get("support_matrix") if isinstance(review.get("support_matrix"), list) else []
    started = client.post(
        "/api/complaint-workspace/intake-chat",
        headers=shared_headers,
        json={"user_id": SHARED_USER, "message": NARRATIVE, "question_id": "original_complaint"},
    )
    started_body = started.json()
    shared_state = started_body.get("session") if isinstance(started_body.get("session"), dict) else {}
    projection = shared_state.get("shared_interview") if isinstance(shared_state.get("shared_interview"), dict) else {}
    pending = projection.get("pending_inquiry") if isinstance(projection.get("pending_inquiry"), dict) else {}
    inquiry_id = str(pending.get("inquiry_id") or "")
    stale = client.post(
        "/api/complaint-workspace/intake-chat",
        headers=shared_headers,
        json={
            "user_id": SHARED_USER,
            "message": ANSWER,
            "question_id": inquiry_id,
            "expected_question_revision": 0,
        },
    )
    matching = client.post(
        "/api/complaint-workspace/intake-chat",
        headers=shared_headers,
        json={"user_id": SHARED_USER, "message": ANSWER, "question_id": inquiry_id},
    )
    why = client.post(
        "/api/complaint-workspace/intake-chat",
        headers=shared_headers,
        json={"user_id": SHARED_USER, "message": "/why"},
    )
    why_body = why.json()
    client.close()

    session_file = private_session_path(session_root / "fixture", SHARED_USER)
    raw_session = session_file.read_bytes()
    assert_private_session_frame(raw_session, NARRATIVE, ANSWER, PASSPHRASE)
    rpc_body = denied_rpc.json()
    rpc_result = rpc_body.get("result") if isinstance(rpc_body.get("result"), dict) else {}
    rpc_text = ""
    content = rpc_result.get("content")
    if isinstance(content, list) and content and isinstance(content[0], dict):
        rpc_text = str(content[0].get("text") or "")
    denied_mcp_body = denied_mcp.json()
    interview = started_body.get("interview") if isinstance(started_body.get("interview"), dict) else {}
    interview_error = interview.get("error") if isinstance(interview.get("error"), dict) else {}
    knowledge = projection.get("knowledge_graph") if isinstance(projection.get("knowledge_graph"), dict) else {}
    dependency = projection.get("dependency_graph") if isinstance(projection.get("dependency_graph"), dict) else {}
    sdk = (ROOT / "static" / "complaint_mcp_sdk.js").read_text(encoding="utf-8")
    audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    audit_ids = [
        item.get("finding", {}).get("id")
        for item in audit.get("findings", [])
        if isinstance(item, dict)
    ]
    flags = {
        "denied_session_status": denied_session.status_code,
        "denied_session_detail": denied_session.json().get("detail"),
        "denied_mcp_status": denied_mcp.status_code,
        "denied_mcp_error": denied_mcp_body.get("error"),
        "denied_mcp_is_error": denied_mcp_body.get("isError"),
        "denied_rpc_is_error": rpc_result.get("isError"),
        "denied_rpc_message": rpc_text,
        "wrong_bearer_status": wrong.status_code,
        "workspace_status": workspace_page.status_code,
        "workspace_route_present": "/workspace" in route_paths,
        "websocket_route_present": "/api/chat" in route_paths,
        "streaming_qualified": False,
        "fresh_dom_qualification": False,
        "fixture_evidence_class": "synthetic_fixture",
        "fixture_authorization": "injected_principal_registry",
        "production_session": False,
        "fixed_status": fixed.status_code,
        "fixed_shared_interview_present": bool(fixed_state.get("shared_interview")),
        "fixed_narrative_empty": not str((fixed_state.get("original_complaint") or {}).get("text") or ""),
        "fixed_answer_count": len(fixed_state.get("intake_answers") or {}),
        "fixed_matrix_len": len(matrix),
        "fixed_supported_elements": sum(1 for item in matrix if isinstance(item, dict) and item.get("supported") is True),
        "shared_status": started.status_code,
        "shared_interview_present": bool(projection),
        "shared_action": interview.get("action"),
        "shared_interview_status": interview.get("status"),
        "shared_legal_sufficiency": interview.get("legal_sufficiency") is True or projection.get("legal_sufficiency") is True,
        "shared_error_code": str(interview_error.get("code") or ""),
        "kg_entity_count": len(_rows(knowledge, "entities")),
        "kg_relationship_count": len(_rows(knowledge, "relationships")),
        "dg_node_count": len(_rows(dependency, "nodes", "requirements")),
        "pending_revision": pending.get("revision"),
        "pending_inquiry_prefix": inquiry_id[:4],
        "stale_status": _interview_error(stale.json()) if stale.status_code == 200 else str(stale.status_code),
        "stale_refused": (stale.json().get("interview") or {}).get("status") == "refused",
        "matching_id_without_revision_status": _interview_error(matching.json()) if matching.status_code == 200 else str(matching.status_code),
        "matching_id_refused_stale": _interview_error(matching.json()) == "stale_question",
        "why_status": why.status_code,
        "why_command": why_body.get("command"),
        "why_stored_as_answer": why_body.get("stored_as_answer"),
        "why_awaiting_user": why_body.get("awaiting_user"),
        "session_prefix": raw_session[:4].decode("ascii", errors="replace"),
        "transport_installed": transport["installed"],
        "transport_call_count": transport["calls"],
        "transport_evidence_class": "synthetic_fixture",
        "live_grok_call": bool(transport["live_identity_verified"]),
        "sdk_writes_sync_event_storage": "localStorage.setItem" in sdk and "complaintGenerator.sdkSyncEvent" in sdk,
        "audit_contains_plaintext_and_a11y": "GUI-BROWSER-PLAINTEXT" in audit_ids and "GUI-A11Y" in audit_ids,
        "product_acceptance": False,
        "gui_ready": False,
    }
    return flags


def _same_recorded_source_generation() -> bool:
    """The committed observation is historical; it never qualifies changed code."""
    receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    generation = receipt.get("source_generation") or {}
    assert receipt.get("baseline_commit") == BASELINE_COMMIT
    assert receipt.get("product_acceptance") is False
    assert receipt.get("gui_ready") is False
    assert receipt.get("fresh_dom_qualification") is False
    # This is the exact scoped entrypoint digest recorded by GUI01, not a
    # claim that NLP/runtime identity or the whole source tree is equivalent.
    assert generation.get("digest") == "b9c8c4da1096723cff8ba08215cee2a71d0c56126a3131fdba0fff793ffdd8f2"
    if any(not (ROOT / path).is_file() for path in SOURCE_PATHS):
        return False
    return _source_generation()["digest"] == generation["digest"]


def _fresh_unauthenticated_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Fresh real ASGI checks remain mandatory after historical source drift."""
    import applications.complaint_workspace as workspace_mod

    _block_network(monkeypatch)
    monkeypatch.setattr(workspace_mod, "_SESSION_DIR", tmp_path / "fresh-denial-sessions")

    class _LocalMediator:
        def io(self, _message: str) -> str:
            return ""

    with TestClient(SERVER(_LocalMediator()).app) as client:
        health = client.get("/health")
        denied = client.get("/api/complaint-workspace/session", params={"user_id": FIXED_USER})
    assert health.status_code == 200 and health.json().get("status") == "healthy"
    assert denied.status_code in {401, 403}
    assert NARRATIVE not in denied.text and PASSPHRASE not in denied.text
    return {"health": health.status_code, "denied": denied.status_code}


def test_actual_app_denies_bootstrap_and_labels_injected_fixtures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Denied bootstrap stays denied. Authorized access here is an injected fixture."""

    _fresh_unauthenticated_api(tmp_path / "stable-boundary", monkeypatch)
    if not _same_recorded_source_generation():
        # The assertions above are fresh. The old fixed-form/plaintext-cache
        # defects below are historical and must not be required to survive.
        return
    flags = _characterize(tmp_path, monkeypatch)
    if flags["denied_session_status"] != 403 or flags["denied_session_detail"] != "authorization_denied":
        _fail("denied_bootstrap_not_denied")
    if flags["denied_mcp_is_error"] is not True or flags["denied_mcp_error"] != "authorization_denied":
        _fail("denied_mcp_bootstrap_not_denied")
    if flags["denied_rpc_is_error"] is not True or flags["denied_rpc_message"] != "authorization_denied":
        _fail("denied_rpc_bootstrap_not_denied")
    if flags["wrong_bearer_status"] != 403:
        _fail("wrong_bearer_not_denied")
    if flags["fixture_evidence_class"] != "synthetic_fixture" or flags["production_session"] is not False:
        _fail("authorized_fixture_unlabeled")
    if flags["fixed_status"] != 200 or flags["shared_status"] != 200:
        _fail("fixture_routes_unavailable")
    if flags["fixed_shared_interview_present"] is not False or flags["fixed_narrative_empty"] is not True:
        _fail("fixed_form_observation_mismatch")
    if flags["fixed_answer_count"] != 6 or flags["fixed_supported_elements"] != 5:
        _fail("fixed_form_support_observation_mismatch")
    if flags["shared_interview_present"] is not True or flags["shared_legal_sufficiency"] is not False:
        _fail("shared_interview_observation_mismatch")
    if flags["kg_entity_count"] < 1 or flags["dg_node_count"] < 1:
        _fail("graph_effect_absent")
    if flags["pending_revision"] != 1 or flags["pending_inquiry_prefix"] != "inq-":
        _fail("pending_revision_observation_mismatch")
    if flags["why_stored_as_answer"] is not False or flags["why_command"] != "/why" or flags["why_awaiting_user"] is not True:
        _fail("why_stored_or_not_awaiting")
    if flags["stale_refused"] is not True or flags["stale_status"] != "stale_question":
        _fail("stale_revision_not_refused")
    if flags["matching_id_refused_stale"] is not False:
        _fail("matching_id_without_revision_refused")
    if flags["session_prefix"] not in {"CGPE", "CGJH"}:
        _fail("session_not_encrypted_frame")
    if flags["transport_installed"] is not True or flags["live_grok_call"] is not False:
        _fail("synthetic_transport_not_observed")
    if flags["transport_evidence_class"] != "synthetic_fixture":
        _fail("synthetic_transport_unlabeled")
    if flags["fresh_dom_qualification"] is not False or flags["streaming_qualified"] is not False:
        _fail("unqualified_surface_claimed")
    if flags["sdk_writes_sync_event_storage"] is not True or flags["audit_contains_plaintext_and_a11y"] is not True:
        _fail("pinned_audit_attribution_missing")
    if flags["product_acceptance"] is not False or flags["gui_ready"] is not False:
        _fail("characterization_claimed_readiness")
    if flags["websocket_route_present"] is not True or flags["workspace_route_present"] is not True:
        _fail("actual_app_routes_missing")


def test_receipt_pins_this_generation_without_future_source_comparison() -> None:
    """The receipt is bound to this source generation and the declared baseline.

    A later edit to those sources must not be forced to reproduce these counts.
    The historical pin stays the receipt digest, not a blind tree-wide compare.
    """

    if not RECEIPT_PATH.is_file():
        _fail("baseline_receipt_absent")
    receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    if receipt.get("schema_version") != "complaint-generator.gui-baseline-receipt.v1":
        _fail("baseline_receipt_schema")
    if receipt.get("task_id") != "CIMP-GUI-01":
        _fail("baseline_receipt_task")
    if receipt.get("product_acceptance") is not False or receipt.get("gui_ready") is not False:
        _fail("baseline_receipt_claims_readiness")
    if receipt.get("fresh_dom_qualification") is not False:
        _fail("baseline_receipt_claims_fresh_dom")
    if receipt.get("fresh_dom_owner") != "CIMP-GUI-02":
        _fail("baseline_receipt_dom_owner")
    if receipt.get("baseline_commit") != BASELINE_COMMIT:
        _fail("baseline_receipt_commit")
    if receipt.get("live_grok_call") is not False or receipt.get("synthetic_only") is not True:
        _fail("baseline_receipt_live_claim")
    fixture = receipt.get("authorized_fixture")
    if not isinstance(fixture, dict) or fixture.get("evidence_class") != "synthetic_fixture":
        _fail("baseline_receipt_fixture_unlabeled")
    if fixture.get("production_session") is not False or fixture.get("live_login") is not False:
        _fail("baseline_receipt_fixture_promoted")
    audit_ref = receipt.get("pinned_manual_audit")
    if not isinstance(audit_ref, dict) or audit_ref.get("evidence_class") != "pinned_manual_audit":
        _fail("baseline_receipt_audit_unlabeled")
    if audit_ref.get("fresh_dom_qualification") is not False:
        _fail("baseline_receipt_audit_promoted_to_dom")
    if "GUI-A11Y" not in audit_ref.get("finding_ids", []) or "GUI-BROWSER-PLAINTEXT" not in audit_ref.get("finding_ids", []):
        _fail("baseline_receipt_audit_findings")
    generation = receipt.get("source_generation")
    if not isinstance(generation, dict):
        _fail("baseline_receipt_generation")
    current = _source_generation()
    listed = generation.get("files")
    if not isinstance(listed, list) or [item.get("path") for item in listed] != list(SOURCE_PATHS):
        _fail("baseline_receipt_source_paths")
    recomputed = hashlib.sha256()
    for item in listed:
        recomputed.update(str(item.get("path") or "").encode("utf-8"))
        recomputed.update(b"\0")
        recomputed.update(str(item.get("sha256") or "").encode("ascii"))
    if generation.get("algorithm") != "sha256" or generation.get("digest") != recomputed.hexdigest():
        _fail("baseline_receipt_digest_inconsistent")
    if generation.get("baseline_commit") != BASELINE_COMMIT:
        _fail("baseline_receipt_generation_commit")
    observations = receipt.get("observations")
    if not isinstance(observations, list) or len(observations) < 4:
        _fail("baseline_receipt_observations")
    mechanics = []
    gaps = []
    for item in observations:
        if not isinstance(item, dict) or not str(item.get("id") or "").strip():
            _fail("baseline_receipt_observation_identity")
        if not str(item.get("observation") or "").strip():
            _fail("baseline_receipt_observation_empty")
        if item.get("product_acceptance") is not False:
            _fail("baseline_receipt_observation_accepts_product")
        classification = item.get("classification")
        if classification == _MECHANIC_CLASSIFICATION:
            mechanics.append(item)
        elif classification in _GAP_CLASSIFICATIONS:
            gaps.append(item)
            if item.get("counts_as_characterization_pass") is not False:
                _fail("baseline_receipt_gap_folded_into_pass")
        else:
            _fail("baseline_receipt_classification")
    if not mechanics or not gaps:
        _fail("baseline_receipt_gaps_not_separate")
    if any(item.get("counts_as_characterization_pass") is not True for item in mechanics):
        _fail("baseline_receipt_mechanic_not_marked")
    flags = receipt.get("observed_flags")
    if not isinstance(flags, dict):
        _fail("baseline_receipt_flags")
    if flags.get("fixture_evidence_class") != "synthetic_fixture":
        _fail("baseline_receipt_flags_unlabeled")
    if flags.get("denied_session_detail") != "authorization_denied":
        _fail("baseline_receipt_flags_not_denied")
    if flags.get("product_acceptance") is not False or flags.get("fresh_dom_qualification") is not False:
        _fail("baseline_receipt_flags_overclaim")
    if current["digest"] != generation.get("digest"):
        return
    if generation.get("files") != current["files"]:
        _fail("baseline_receipt_files_mismatch")
    if flags.get("kg_entity_count") != 3 or flags.get("dg_node_count") != 7:
        _fail("baseline_receipt_graph_counts")
    if flags.get("transport_call_count") != 0 or flags.get("shared_error_code") != "provider_unavailable":
        _fail("baseline_receipt_transport_counts")
    if flags.get("fixed_shared_interview_present") is not False or flags.get("shared_interview_present") is not True:
        _fail("baseline_receipt_interview_split")


def _assert_live_contract_matches_recorded_observation(flags: dict, expected: dict) -> None:
    """Source identity does not establish interpreter/NLP runtime equivalence."""

    runtime_metrics = {"kg_entity_count", "kg_relationship_count", "dg_node_count"}
    for key in runtime_metrics:
        value = flags[key]
        assert type(value) is int and 0 <= value <= 10000
    assert flags["kg_entity_count"] > 0 and flags["dg_node_count"] > 0
    changed = sorted(key for key in set(flags) | set(expected)
                     if key not in runtime_metrics and flags.get(key) != expected.get(key))
    if changed:
        _fail("live_flags_differ:" + ",".join(changed))


def test_same_generation_live_flags_match_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Check stable contracts; exact historical counts are runtime observations."""

    receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    generation = receipt.get("source_generation") if isinstance(receipt.get("source_generation"), dict) else {}
    current = _source_generation()
    if current["digest"] != generation.get("digest"):
        if receipt.get("baseline_commit") != BASELINE_COMMIT:
            _fail("historical_receipt_lost_baseline")
        return
    flags = _characterize(tmp_path, monkeypatch)
    expected = receipt.get("observed_flags")
    _assert_live_contract_matches_recorded_observation(flags, expected)


def test_source_drift_keeps_fresh_denial_without_old_characterization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    observed = []
    fresh = _fresh_unauthenticated_api

    def observe(*args, **kwargs):
        result = fresh(*args, **kwargs)
        observed.append(result)
        return result

    def old_characterization_must_not_run(*args, **kwargs):
        raise AssertionError("historical characterization called after source drift")

    monkeypatch.setitem(globals(), "_fresh_unauthenticated_api", observe)
    monkeypatch.setitem(globals(), "_source_generation", lambda: {"digest": "changed-entrypoint-generation"})
    monkeypatch.setitem(globals(), "_characterize", old_characterization_must_not_run)
    test_actual_app_denies_bootstrap_and_labels_injected_fixtures(tmp_path, monkeypatch)
    assert len(observed) == 1
    assert observed[0]["health"] == 200 and observed[0]["denied"] in {401, 403}


def test_runtime_metric_variation_cannot_hide_denied_or_empty_graphs() -> None:
    expected = {"kg_entity_count": 3, "kg_relationship_count": 1,
                "dg_node_count": 7, "denied_session_status": 403}
    observed = {**expected, "kg_entity_count": 12, "kg_relationship_count": 4}
    _assert_live_contract_matches_recorded_observation(observed, expected)
    with pytest.raises(AssertionError):
        _assert_live_contract_matches_recorded_observation({**observed, "kg_entity_count": 0}, expected)
    with pytest.raises(AssertionError, match="denied_session_status"):
        _assert_live_contract_matches_recorded_observation({**observed, "denied_session_status": 200}, expected)
