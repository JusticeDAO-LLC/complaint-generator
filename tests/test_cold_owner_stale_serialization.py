"""Cold graph hydration preserves JSON DTOs and real owner stale refusals."""
from copy import deepcopy
import json

from fastapi.testclient import TestClient
import pytest

from complaint_phases.dependency_graph import (
    Dependency, DependencyGraph, DependencyNode, DependencyType, NodeType,
)
from tests.test_cimp_gui_14 import (
    _composed_ciphertext_snapshot, _composed_headers, _composed_login,
)
from tests.test_cimp_gui_15 import _typed_world, MARKER


pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def test_dependency_graph_hydration_keeps_json_projection_detached():
    graph = DependencyGraph()
    graph.add_node(DependencyNode("fact", NodeType.FACT, "Synthetic fact",
        attributes={"source": {"identity": "synthetic-source"}}))
    graph.add_node(DependencyNode("requirement", NodeType.REQUIREMENT, "Synthetic requirement"))
    graph.add_dependency(Dependency("edge", "fact", "requirement", DependencyType.REQUIRES))
    projection = graph.to_dict()
    before = deepcopy(projection)
    encoded = json.dumps(projection, sort_keys=True)

    restored = DependencyGraph.from_dict(projection)

    assert projection == before
    assert json.dumps(projection, sort_keys=True) == encoded
    assert restored.nodes["fact"].node_type is NodeType.FACT
    assert restored.dependencies["edge"].dependency_type is DependencyType.REQUIRES
    assert restored.to_dict() == before
    restored.metadata["version"] = "synthetic-restored-only"
    restored.nodes["fact"].attributes["source"]["identity"] = "synthetic-restored-only"
    restored.dependencies["edge"].required = False
    assert projection == before


@pytest.mark.parametrize("transport", ["http", "mcp_call", "mcp_rpc"])
def test_real_cold_owner_stale_answer_stays_json_and_never_publishes(tmp_path, transport):
    world = _typed_world(tmp_path)
    with TestClient(world.application, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        headers = _composed_headers(world.case, csrf)
        authenticated = client.get("/api/complaint-workspace/auth/session")
        assert authenticated.status_code == 200
        assert authenticated.json()["principal_id"] == world.principal.principal_id

        def rpc(method, params):
            return client.post("/api/complaint-workspace/mcp/rpc", headers=headers,
                json={"jsonrpc": "2.0", "id": "synthetic-owner", "method": method, "params": params})

        for method, params in (
            ("initialize", {"clientInfo": {"name": "complaint-generator-browser-sdk", "version": "0.1.0"}}),
            ("tools/list", {}),
            ("tools/call", {"name": "complaint.start_session",
                "arguments": {"user_id": world.principal.principal_id}}),
        ):
            bootstrap = rpc(method, params)
            assert bootstrap.status_code == 200
            assert "error" not in bootstrap.json()
            assert bootstrap.json()["result"].get("isError") is not True

        # The SDK removes the canonical tenant from actor arguments.
        started = rpc("tools/call", {"name": "complaint.run_intake_chat_turn",
            "arguments": {"message": MARKER, "question_id": "original_complaint", "interview_action": "start"}})
        assert started.status_code == 200
        assert started.json()["result"]["isError"] is False
        initial = started.json()["result"]["structuredContent"]
        pending = initial["pending_inquiry_id"]
        revision = initial["expected_question_revision"]
        assert pending and isinstance(revision, int)
        projection = deepcopy(initial["session"]["shared_interview"])
        ciphertext = _composed_ciphertext_snapshot(world.service)
        assert ciphertext and world.service._interview_mediators == {}

        arguments = {"message": "synthetic stale answer", "question_id": pending,
            "expected_question_revision": revision + 1, "interview_action": "answer"}
        if transport == "mcp_rpc":
            stale = rpc("tools/call", {"name": "complaint.run_intake_chat_turn", "arguments": arguments})
            assert stale.status_code == 409
            result = stale.json()["result"]
            assert result["isError"] is True
            refused = result["structuredContent"]
        elif transport == "mcp_call":
            stale = client.post("/api/complaint-workspace/mcp/call", headers=headers,
                json={"tool_name": "complaint.run_intake_chat_turn", "arguments": arguments})
            assert stale.status_code == 409
            refused = stale.json()
            assert refused["isError"] is True
        else:
            stale = client.post("/api/complaint-workspace/intake-chat", headers=headers, json=arguments)
            assert stale.status_code == 409
            refused = stale.json()
        assert refused["conflict"] == "stale_question"
        assert refused["interview"]["status"] == "refused"
        assert refused["interview"]["error"]["code"] == "stale_question"
        assert refused["pending_inquiry_id"] == pending
        assert refused["expected_question_revision"] == revision
        assert refused["session"]["shared_interview"] == projection
        assert refused["legal_sufficiency"] is False
        assert _composed_ciphertext_snapshot(world.service) == ciphertext
        assert world.service._interview_mediators == {}
        reread = client.get("/api/complaint-workspace/session", headers=_composed_headers(world.case))
        assert reread.status_code == 200
        assert reread.json()["session"]["shared_interview"] == projection
        assert _composed_ciphertext_snapshot(world.service) == ciphertext
