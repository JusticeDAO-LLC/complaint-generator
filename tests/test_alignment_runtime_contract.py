"""Exercise alignment boundaries with local fakes rather than source matching."""

import importlib.util
import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from applications.complaint_mcp_protocol import handle_jsonrpc_message
from applications.complaint_workspace import ComplaintWorkspaceService
from integrations.ipfs_accelerate import routers
from integrations.ipfs_datasets import graphs, loader, storage
from integrations.mike.llm_patch import apply_mike_llm_router_patch


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]


@pytest.mark.parametrize("version", ["2024-11-05", "2025-03-26", "2025-06-18"])
def test_mcp_initialize_negotiates_each_supported_version(tmp_path, version):
    service = ComplaintWorkspaceService(root_dir=tmp_path)
    response = handle_jsonrpc_message(
        service,
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": version}},
    )
    assert response["result"]["protocolVersion"] == version


def test_mike_stamp_is_compatibility_metadata_on_the_handoff():
    payload = {"draft": "Existing draft"}
    assert apply_mike_llm_router_patch(payload) is payload
    assert payload["draft"] == "Existing draft"
    assert payload["mike_llm_patch"]["patch_version"] == "mike-llm-router-patch-v1"
    assert payload["mike_llm_patch"]["compatibility_only"] is True
    assert payload["mike_llm_patch"]["transport"] == "mcp_connector"


@pytest.mark.parametrize("setting", [None, "", "0", "false"])
def test_disabled_kit_gate_never_loads_or_constructs_kit(monkeypatch, setting):
    if setting is None:
        monkeypatch.delenv("COMPLAINT_GENERATOR_ENABLE_IPFS_KIT", raising=False)
    else:
        monkeypatch.setenv("COMPLAINT_GENERATOR_ENABLE_IPFS_KIT", setting)
    importer = Mock(side_effect=AssertionError("disabled kit must not be imported"))
    monkeypatch.setattr(storage, "import_attr_optional", importer)
    assert storage._load_optional_kit_backend() is None
    importer.assert_not_called()


def test_enabled_kit_gate_constructs_the_byte_api(monkeypatch):
    monkeypatch.setenv("COMPLAINT_GENERATOR_ENABLE_IPFS_KIT", "true")
    kit = object()
    constructor = Mock(return_value=kit)
    importer = Mock(side_effect=lambda module, name: (constructor if name == "IPFSSimpleAPI" else None, None))
    monkeypatch.setattr(storage, "import_attr_optional", importer)
    monkeypatch.setattr(loader, "ensure_import_paths", Mock())
    assert storage._load_optional_kit_backend() is kit
    constructor.assert_called_once_with()


def test_injected_storage_backend_takes_precedence_over_optional_backends(monkeypatch):
    backend = SimpleNamespace(add_bytes=Mock(return_value="bafy-injected"))
    kit_loader = Mock(side_effect=AssertionError("injected backend must take precedence"))
    monkeypatch.setattr(storage, "_load_optional_kit_backend", kit_loader)
    result = storage.store_bytes(b"evidence", backend=backend, backend_name="injected")
    assert result["cid"] == "bafy-injected"
    assert result["backend_name"] == "injected"
    backend.add_bytes.assert_called_once_with(b"evidence", pin=True)
    kit_loader.assert_not_called()


@pytest.mark.parametrize("kit_fails", [False, True])
def test_automatic_storage_prefers_kit_then_datasets_router(monkeypatch, kit_fails):
    backend = SimpleNamespace(add_bytes=Mock(side_effect=RuntimeError("kit offline") if kit_fails else None, return_value="bafy-kit"))
    router_add = Mock(return_value="bafy-router")
    monkeypatch.setattr(storage, "_load_optional_kit_backend", lambda: backend)
    monkeypatch.setattr(storage, "_storage_error_type", lambda: RuntimeError)
    monkeypatch.setattr(storage, "add_bytes", router_add)
    monkeypatch.setattr(storage, "_runtime_backend_probe", lambda: {"status": "available", "backend_name": "datasets_router", "reason": ""})
    result = storage.store_bytes(b"evidence", pin_content=False)
    backend.add_bytes.assert_called_once_with(b"evidence", pin=False)
    assert result["cid"] == ("bafy-router" if kit_fails else "bafy-kit")
    assert result["backend_name"] == ("datasets_router" if kit_fails else "kit")
    if kit_fails:
        router_add.assert_called_once_with(b"evidence", pin=False)
    else:
        router_add.assert_not_called()


@pytest.mark.parametrize(
    "load_name,module_name,symbols",
    [
        ("load_llm_symbols", "ipfs_accelerate_py.llm_router", ("generate_text", "get_last_generation_trace")),
        ("load_embedding_symbols", "ipfs_accelerate_py.embeddings_router", ("embed_text", "embed_texts", "embed_texts_batched", "EmbeddingsRouter")),
        ("load_multimodal_symbols", "ipfs_accelerate_py.multimodal_router", ("generate_multimodal_text", "build_multimodal_messages", "encode_image_as_data_url")),
    ],
)
def test_facade_returns_symbols_from_each_accelerate_router(monkeypatch, load_name, module_name, symbols):
    expected = {name: Mock(name=name) for name in symbols}
    module = SimpleNamespace(**expected)
    attr_importer = Mock(side_effect=lambda module_path, name: (expected[name], None))
    module_importer = Mock(return_value=(module, None))
    monkeypatch.setattr(routers, "ensure_import_paths", Mock())
    monkeypatch.setattr(routers, "import_attr_optional", attr_importer)
    monkeypatch.setattr(loader, "import_module_optional", module_importer)
    result = getattr(routers, load_name)()
    assert tuple(result[:len(symbols)]) == tuple(expected.values())
    assert result[-1] is None
    assert attr_importer.call_args_list == [call(module_name, name) for name in symbols]
    if load_name == "load_embedding_symbols":
        assert result[-2] is module
        module_importer.assert_called_once_with(module_name)


def test_legal_symbol_loader_defers_upstream_import_until_requested(monkeypatch):
    symbol = object()
    upstream = SimpleNamespace(__name__="ipfs_datasets_py.processors.legal_data.example", Example=symbol)
    importer = Mock(return_value=(upstream, None))
    monkeypatch.setattr(loader, "import_module_optional", importer)
    source = Path(__file__).resolve().parents[1] / "integrations/ipfs_datasets/legal_data.py"
    spec = importlib.util.spec_from_file_location("integrations.ipfs_datasets._alignment_legal_probe", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    importer.assert_not_called()
    assert module.load_legal_symbol("Example", module="example") is symbol
    importer.assert_called_once_with("ipfs_datasets_py.processors.legal_data.example")


def test_graph_snapshot_creates_and_writes_through_the_client(monkeypatch):
    target = object()
    target_factory = Mock(return_value=target)
    client = SimpleNamespace(create=Mock(), write=Mock(return_value=SimpleNamespace(ok=True)))
    monkeypatch.setattr(graphs, "_GRAPH_CLIENT", client)
    monkeypatch.setattr(graphs, "_GRAPH_CLIENT_VERSIONS", {"client_api_version": "test", "contract_version": "1"})
    monkeypatch.setattr(graphs, "_GRAPH_SNAPSHOT_REGISTRY", {})
    monkeypatch.setattr(loader, "import_attr_optional", Mock(return_value=(target_factory, None)))
    payload = {"entities": [{"id": "worker"}], "relationships": [], "source_id": "evidence"}
    result = graphs.persist_graph_snapshot(payload, graph_id="graph:client-test")
    client_id = "graph-" + hashlib.sha256(b"graph:client-test").hexdigest()[:48]
    target_factory.assert_called_once_with(tenant="complaint-generator", graph_id=client_id, branch="main")
    client.create.assert_called_once_with(target, idempotency_key=f"create-{client_id}", raise_on_error=False)
    assert client.write.call_args.args == (target,)
    assert client.write.call_args.kwargs["params"] == {"entities": payload["entities"], "relationships": []}
    assert result["metadata"]["client_write_ok"] is True
    assert result["metadata"]["graph_persist_path"] == "knowledge_graphs.Client"


def test_graph_client_persists_colon_ids_and_updates_with_same_entity_count(monkeypatch, tmp_path):
    module, error = loader.import_module_optional("ipfs_datasets_py.knowledge_graphs")
    if module is None or not hasattr(module, "Client"):
        pytest.skip(str(error or "optional knowledge graph Client unavailable"))
    monkeypatch.setenv("COMPLAINT_GENERATOR_GRAPH_CATALOG", str(tmp_path))
    monkeypatch.setattr(graphs, "_GRAPH_CLIENT", None)
    monkeypatch.setattr(graphs, "_GRAPH_CLIENT_VERSIONS", {})
    monkeypatch.setattr(graphs, "_GRAPH_SNAPSHOT_REGISTRY", {})
    graph_id = "graph:durable-client-test"
    client_id = "graph-" + hashlib.sha256(graph_id.encode()).hexdigest()[:48]
    target = module.GraphTarget(tenant="complaint-generator", graph_id=client_id, branch="main")
    try:
        for name in ("Original worker", "Updated worker"):
            result = graphs.persist_graph_snapshot(
                {"entities": [{"id": "worker", "type": "person", "name": name}], "relationships": []},
                graph_id=graph_id,
            )
            assert result["metadata"]["client_write_ok"] is True, result["metadata"]
    finally:
        if graphs._GRAPH_CLIENT is not None:
            graphs._GRAPH_CLIENT.close()
    with module.Client.open(tmp_path / "catalog", storage_path=tmp_path / "store") as reopened:
        queried = reopened.query(target, params={"language": "scan"})
        assert queried.ok, queried.error
        assert queried.result["rows"] == [["worker", "person", "Updated worker", {}]]
