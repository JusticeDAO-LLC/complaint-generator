import inspect

import pytest

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]
from unittest.mock import patch

from applications.complaint_workspace import ComplaintWorkspaceService
from integrations.ipfs_accelerate import routers
from integrations.ipfs_datasets.graphs import extract_graph_from_text, persist_graph_snapshot
from integrations.ipfs_datasets.logic import text_to_fol
from integrations.ipfs_datasets.storage import store_bytes


def _intake(service: ComplaintWorkspaceService, user_id: str) -> None:
    service.submit_intake_answers(
        user_id,
        {
            "party_name": "Taylor Smith",
            "opposing_party": "Acme Logistics",
            "protected_activity": "Reported safety violations",
            "adverse_action": "Termination",
            "timeline": "Reported on April 2; terminated on April 5",
            "harm": "Lost wages",
        },
    )
    service.save_evidence(
        user_id,
        kind="testimony",
        claim_element_id="protected_activity",
        title="Safety report",
        content="Taylor reported safety violations on April 2.",
    )


class _FakeKit:
    def add_bytes(self, data, pin=True):
        return "bafykit"


def test_workspace_flow_uses_mcp_connector_accelerate_kit_graph_and_logic(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path)
    user_id = "alignment-user"
    _intake(service, user_id)
    graph = extract_graph_from_text("Taylor reported safety violations.", source_id="evidence-1")
    persisted = persist_graph_snapshot(graph, graph_id="graph:alignment", graph_changed=True)
    logic = text_to_fol("Taylor reported safety violations and was terminated.")
    handoff = service.build_mike_handoff(user_id, grounding_mode="legal_corpus_only")

    with patch("integrations.ipfs_datasets.llm.generate_text", return_value="Grounded retaliation count.") as generate:
        generated = service.call_mcp_tool(
            "complaint.generate_grounded_text",
            {
                "user_id": user_id,
                "prompt": "Draft the retaliation count.",
                "provider": "copilot_cli",
                "grounding_mode": "legal_corpus_only",
            },
        )
    synced = service.call_mcp_tool(
        "complaint.sync_draft",
        {
            "user_id": user_id,
            "title": "Complaint",
            "body": "Grounded retaliation count.",
        },
    )
    stored = store_bytes(b"alignment-evidence", backend=_FakeKit(), backend_name="kit")

    mike_integration = handoff["handoff_payload"]["mike_integration"]
    assert mike_integration["transport"] == "mcp_connector"
    assert mike_integration["tools"] == [
        "complaint.generate_grounded_text",
        "complaint.search_corpus",
        "complaint.get_handoff",
        "complaint.sync_draft",
    ]
    assert generate.called
    assert "ipfs_accelerate_py.llm_router" in inspect.getsource(routers.load_llm_symbols)
    assert "generate_text" in inspect.getsource(routers.load_llm_symbols)
    assert generated["generation"]["text"] == "Grounded retaliation count."
    assert stored["backend_name"] == "kit"
    assert persisted["status"] == "stored-fallback"
    assert persisted["metadata"]["persistence_scope"] == "adapter_memory"
    assert persisted["metadata"]["graph_persist_path"] == "knowledge_graphs.Client"
    assert logic["metadata"]["logic_path"] in {"logic.fol", "logic.deontic"}
    assert "logic.tools" not in inspect.getsource(text_to_fol)
    assert len(synced["document_version_content_sha256"]) == 64
    assert synced["sync_record"]["document_version_content_sha256"] == synced["document_version_content_sha256"]


def test_workspace_flow_degrades_when_routers_and_storage_imports_fail(tmp_path, monkeypatch):
    service = ComplaintWorkspaceService(root_dir=tmp_path)
    user_id = "alignment-degraded-user"
    _intake(service, user_id)
    monkeypatch.setenv("COMPLAINT_GENERATOR_IPFS_CACHE_DIR", str(tmp_path / "ipfs-cache"))
    monkeypatch.setattr("integrations.ipfs_datasets.llm.LLM_ROUTER_AVAILABLE", False)
    monkeypatch.setattr("integrations.ipfs_datasets.llm.generate_text", None)
    monkeypatch.setattr("integrations.ipfs_datasets.llm.LLM_ROUTER_ERROR", "accelerate routers unavailable")
    monkeypatch.setattr("integrations.ipfs_datasets.storage._load_optional_kit_backend", lambda: None)
    monkeypatch.setattr("integrations.ipfs_datasets.storage.add_bytes", None)

    handoff = service.build_mike_handoff(user_id, grounding_mode="legal_corpus_only")
    generated = service.call_mcp_tool(
        "complaint.generate_grounded_text",
        {"user_id": user_id, "prompt": "Draft the count.", "provider": "copilot_cli"},
    )
    stored = store_bytes(b"degraded-evidence")
    synced = service.sync_draft(user_id, body="Local draft body.", title="Complaint")

    setup = handoff["handoff_payload"]["mike_integration"]["setup_instructions"]
    assert "unavailable" in setup
    assert "connector" in setup
    assert "routers" in setup
    assert generated["generation"]["status"] == "unavailable"
    assert stored["backend_name"] == "local_cache"
    assert stored["status"] == "degraded"
    assert len(synced["document_version_content_sha256"]) == 64
