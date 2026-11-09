import pytest
from unittest.mock import patch

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

from integrations.ipfs_accelerate.supervisor import draft_repair, evidence_acquisition, graph_refresh


class _FakeSupervisor:
    def __init__(self):
        self.calls = []

    def execute(self, payload):
        self.calls.append(payload)
        return {"accepted": True, "operation": payload["operation"]}


def test_supervisor_jobs_record_on_an_injected_control_service():
    control = _FakeSupervisor()
    probe = {"available": False, "probed": False, "error": "not on the request path", "operations": []}
    with patch("integrations.ipfs_accelerate.supervisor.probe_agent_supervisor", return_value=probe):
        with patch(
            "integrations.ipfs_datasets.search.search_multi_engine_web",
            return_value=[{"title": "wage record"}],
        ):
            with patch(
                "integrations.ipfs_datasets.storage.store_bytes",
                return_value={"cid": "bafyevidence", "backend_name": "kit", "status": "available"},
            ):
                evidence = evidence_acquisition({"query": "wage theft"}, control_service=control)
        with patch(
            "integrations.ipfs_datasets.llm.generate_text_with_metadata",
            return_value={"status": "available", "text": "The employer terminated the worker."},
        ):
            with patch(
                "integrations.ipfs_datasets.logic.text_to_fol",
                return_value={"status": "success", "metadata": {"logic_path": "logic.fol"}},
            ):
                repair = draft_repair({"prompt": "Repair the count."}, control_service=control)
        with patch(
            "integrations.ipfs_datasets.graphs.extract_graph_from_text",
            return_value={"entities": [], "relationships": [], "source_id": "src"},
        ):
            with patch(
                "integrations.ipfs_datasets.graphs.persist_graph_snapshot",
                return_value={
                    "graph_id": "graph:1",
                    "status": "stored-fallback",
                    "metadata": {"graph_persist_path": "knowledge_graphs.Client"},
                },
            ):
                refreshed = graph_refresh({"text": "Protected activity."}, control_service=control)

    assert evidence["off_request_path"] is True
    assert evidence["status"] == "available"
    assert evidence["receipt"]["cid"] == "bafyevidence"
    assert repair["result"]["logic_path"] == "logic.fol"
    assert refreshed["receipt"]["backend_name"] == "knowledge_graphs.Client"
    assert [call["operation"] for call in control.calls] == [
        "evidence_acquisition",
        "draft_repair",
        "graph_refresh",
    ]
