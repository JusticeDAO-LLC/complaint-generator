"""Bind GUI capabilities to current owners without treating imports as proof.

Positive cases probe real public symbols and pinned revisions. Negative cases
cover a missing symbol and historical evidence that cannot satisfy new GUI
behavior. No package is installed and no owner is executed.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from integrations.gui_capabilities import (
    EXECUTION_NOT_EXECUTED,
    OWNER_SYMBOLS,
    REQUIRED_FAMILIES,
    SCHEMA_VERSION,
    SOURCE_BASELINE,
    TASK_ID,
    OwnerSymbol,
    evidence_satisfies_new_gui_behavior,
    gui_behavior_decision,
    probe_gui_owner_capabilities,
    probe_owner_symbol,
)
from integrations.ipfs_datasets.capabilities import DECLARED_OWNER_PINS


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "integrations" / "gui_capabilities.py"


def _report() -> dict:
    return probe_gui_owner_capabilities()


def _row(report: dict, symbol: str) -> dict:
    matches = [row for row in report["symbols"] if row["symbol"] == symbol]
    assert len(matches) == 1
    return matches[0]


def test_probe_records_available_symbols_pins_and_not_executed_state() -> None:
    report = _report()
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["task_id"] == TASK_ID
    assert report["source_baseline"] == SOURCE_BASELINE
    assert report["families"] == list(REQUIRED_FAMILIES)
    assert report["families_complete"] is True
    assert report["imports_used"] is False
    assert report["packages_installed"] is False
    assert report["operational_proof"] is False
    assert report["new_gui_behavior_satisfied"] is False
    assert report["not_executed_count"] == len(OWNER_SYMBOLS)
    assert evidence_satisfies_new_gui_behavior(report) is False
    assert gui_behavior_decision(report)["reason"] == "capability_probe_is_not_gui_behavior"

    pins = report["pinned_revisions"]
    assert pins["complaint_generator"]["declared_pin"] == SOURCE_BASELINE
    for name, pin in DECLARED_OWNER_PINS.items():
        assert pins[name]["declared_pin"] == pin
        assert pins[name]["submodule_updated"] is False
        assert isinstance(pins[name]["pin_matches_observed_head"], bool)

    for symbol in (
        "SERVER",
        "ComplaintWorkspaceService",
        "create_complaint_workspace_router",
        "Mediator",
        "WorkflowActionService",
        "compile_canonical_legal_ir",
        "store_private_artifact",
        "pinned_grok47_dispatch_kwargs",
    ):
        row = _row(report, symbol)
        assert row["status"] == "available"
        assert row["symbol_present"] is True
        assert row["execution_status"] == EXECUTION_NOT_EXECUTED
        assert row["import_used"] is False
        assert row["operational_proof"] is False
        assert row["resolution"] == "source_ast"
        assert (ROOT / row["canonical_source_path"]).is_file()

    for family in ("data_kg", "data_legal", "kit_storage", "router"):
        rows = [row for row in report["symbols"] if row["family"] == family]
        assert rows
        assert {row["status"] for row in rows} <= {"available", "unavailable"}
        assert all(row["execution_status"] == EXECUTION_NOT_EXECUTED for row in rows)


def test_router_owner_state_follows_source_and_is_not_execution() -> None:
    report = _report()
    row = _row(report, "generate_text")
    source = ROOT / str(row["canonical_source_path"])
    if source.is_file():
        assert row["status"] == "available"
    else:
        assert row["status"] == "unavailable"
        assert row["error_type"] == "FileNotFoundError"
    assert row["owner"] == "ipfs_accelerate_py"
    assert row["execution_status"] == EXECUTION_NOT_EXECUTED
    assert row["operational_proof"] is False
    pin = report["pinned_revisions"]["ipfs_accelerate_py"]
    assert pin["declared_pin"] == DECLARED_OWNER_PINS["ipfs_accelerate_py"]
    if pin["populated"] is not True:
        assert pin["pin_matches_observed_head"] is False


def test_missing_symbol_is_unavailable_and_not_executed() -> None:
    missing = probe_owner_symbol(OwnerSymbol(
        "public_service",
        "applications.server",
        "MissingGuiOwnerSymbol",
        "first_party",
        "applications/server.py",
    ))
    absent_file = probe_owner_symbol(OwnerSymbol(
        "router",
        "ipfs_accelerate_py.llm_router",
        "generate_text",
        "ipfs_accelerate_py",
        "ipfs_accelerate_py/does_not_exist_gui_03.py",
    ))
    assert missing["status"] == "unavailable"
    assert missing["error_type"] == "SymbolNotFound"
    assert missing["execution_status"] == EXECUTION_NOT_EXECUTED
    assert missing["operational_proof"] is False
    assert absent_file["status"] == "unavailable"
    assert absent_file["error_type"] == "FileNotFoundError"
    assert absent_file["import_used"] is False
    assert absent_file["packages_installed"] is False


def test_browser_audit_and_old44_cannot_satisfy_new_gui_behavior() -> None:
    audit = {"kind": "browser_audit", "browser_audit_completed": True, "task_id": "historical-dom"}
    manual = {"evidence_kind": "pinned_manual_dom_audit", "qualified": True}
    old44 = {"kind": "old44_completion", "old44_complete": True, "program": "mediator-44"}
    completed = {"task_id": "completed58", "program": "completed_58"}
    for evidence, reason in (
        (audit, "browser_audit_cannot_satisfy_new_gui_behavior"),
        (manual, "browser_audit_cannot_satisfy_new_gui_behavior"),
        (old44, "old44_or_historical_completion_cannot_satisfy_new_gui_behavior"),
        (completed, "old44_or_historical_completion_cannot_satisfy_new_gui_behavior"),
    ):
        decision = gui_behavior_decision(evidence)
        assert decision["satisfied"] is False
        assert decision["reason"] == reason
        assert evidence_satisfies_new_gui_behavior(evidence) is False
    assert evidence_satisfies_new_gui_behavior(None) is False
    assert gui_behavior_decision({"kind": "unrelated"})["reason"] == "new_gui_behavior_not_certified"


def test_binder_source_does_not_import_owners_or_install_packages() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imported: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                calls.add(func.id)
            elif isinstance(func, ast.Attribute):
                calls.add(func.attr)
    forbidden_imports = {
        "ipfs_accelerate_py",
        "ipfs_datasets_py",
        "ipfs_kit_py",
        "applications.server",
        "mediator.mediator",
        "subprocess",
    }
    assert imported.isdisjoint(forbidden_imports)
    assert calls.isdisjoint({"system", "check_call", "pip", "generate_text", "store_private_artifact"})
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "pip install" not in source
    assert "submodule update" not in source
