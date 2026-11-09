import pytest
from pathlib import Path

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

from applications.complaint_workspace import ComplaintWorkspaceService


ROOT = Path(__file__).resolve().parents[1]
ADAPTERS = ROOT / "integrations"


def test_deprecated_upstream_symbols_stay_out_of_adapters():
    graphs = (ADAPTERS / "ipfs_datasets" / "graphs.py").read_text(encoding="utf-8")
    logic = (ADAPTERS / "ipfs_datasets" / "logic.py").read_text(encoding="utf-8")
    assert "GraphEngine(" not in graphs
    assert "GraphDatabase(" not in graphs
    assert "logic.tools" not in logic
    assert "ipfs_datasets_py.logic.fol" in logic
    assert "ipfs_datasets_py.logic.deontic" in logic
    assert "ipfs_datasets_py.logic.integration" in logic
    assert "ipfs_datasets_py.logic.external_provers" in logic
    assert "ipfs_datasets_py.logic.TDFOL" in logic


def test_kit_import_stays_inside_the_storage_adapter():
    allowed = {
        ADAPTERS / "ipfs_datasets" / "storage.py",
        ADAPTERS / "ipfs_datasets" / "capabilities.py",
    }
    offenders = []
    for path in ADAPTERS.rglob("*.py"):
        if path in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        if "import ipfs_kit_py" in text or "from ipfs_kit_py" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_operator_scripts_stay_on_the_legal_adapter():
    offenders = []
    for path in (ROOT / "scripts").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "ipfs_datasets_py.processors.legal_data" in text:
            offenders.append(path.name)
    assert offenders == []
    workspace_api = (ROOT / "applications" / "complaint_workspace_api.py").read_text(encoding="utf-8")
    assert "evidence_acquisition" not in workspace_api
    assert "draft_repair" not in workspace_api
    assert "graph_refresh" not in workspace_api


def test_mike_stamp_does_not_rewrite_the_mike_checkout():
    patch = (ADAPTERS / "mike" / "llm_patch.py").read_text(encoding="utf-8")
    assert "mike-llm-router-patch-v1" in patch
    assert "external/mike" not in patch
    assert "compatibility" in patch.lower()
    workspace_api = (ROOT / "applications" / "complaint_workspace_api.py").read_text(encoding="utf-8")
    assert "evidence_acquisition" not in workspace_api
    assert "draft_repair" not in workspace_api
    assert "graph_refresh" not in workspace_api


def test_submodule_inventory_records_external_main_and_missing_editor_paths():
    inventory = ComplaintWorkspaceService._build_mike_submodule_inventory()
    strategy = inventory["strategy"]
    assert strategy["mike"] == "external/mike@origin/main"
    assert strategy["ipfs_datasets_py"] == "external/ipfs_datasets_py@origin/main"
    assert strategy["ipfs_accelerate_py"] == "external/ipfs_accelerate_py@origin/main"
    assert strategy["ipfs_kit_py"] == "external/ipfs_kit_py@origin/main"
    rows = {row["path"]: row["path_found"] for row in inventory["mike"]["editor_module_inventory"]}
    assert "frontend/src/app/lib/mikeApi.ts" in rows
    assert isinstance(rows["frontend/src/app/lib/mikeApi.ts"], bool)
    matrix = ComplaintWorkspaceService._build_mike_compatibility_target_matrix()
    shas = matrix["submodule_shas"]
    for key in (
        "mike_commit",
        "mike_origin_main_commit",
        "ipfs_datasets_py_commit",
        "ipfs_datasets_py_origin_main_commit",
        "ipfs_accelerate_py_commit",
        "ipfs_accelerate_py_origin_main_commit",
        "ipfs_kit_py_commit",
        "ipfs_kit_py_origin_main_commit",
    ):
        assert len(shas[key]) == 40
        int(shas[key], 16)
