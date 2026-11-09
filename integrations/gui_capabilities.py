"""Bind GUI capability records to the current mediator and SDK owners.

Symbol presence is read from canonical source text. An import, a browser
audit, or a historical 44-task completion is not operational proof and does
not satisfy new GUI behavior. This module does not install packages, update
pins, or call the owners it records.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from integrations.ipfs_datasets.capabilities import DECLARED_OWNER_PINS
from integrations.ipfs_datasets.loader import (
    classify_owner_checkout,
    declared_submodule_paths,
    get_repo_paths,
    observe_checked_out_commit,
)


SCHEMA_VERSION = "gui-owner-capabilities/v1"
TASK_ID = "CIMP-GUI-03"
SOURCE_BASELINE = "2c1439a7029eb9035338133210d8b43319add8a4"
EXECUTION_NOT_EXECUTED = "not_executed"
STATUS_AVAILABLE = "available"
STATUS_UNAVAILABLE = "unavailable"

_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_OWNER_ROOTS = {
    "ipfs_accelerate_py": "external/ipfs_accelerate_py",
    "ipfs_datasets_py": "external/ipfs_datasets_py",
    "ipfs_kit_py": "external/ipfs_kit_py",
}
_OWNER_CANONICAL = {
    "ipfs_accelerate_py": "ipfs_accelerate_py/__init__.py",
    "ipfs_datasets_py": "ipfs_datasets_py/__init__.py",
    "ipfs_kit_py": "ipfs_kit_py/__init__.py",
}
_HISTORICAL_KINDS = frozenset({
    "browser_audit",
    "pinned_manual_audit",
    "pinned_manual_dom_audit",
    "old44",
    "old44_completion",
    "completed44",
    "completed_44",
    "mediator-44",
    "mediator_44",
    "completed58",
    "completed_58",
    "intake-58",
})


@dataclass(frozen=True)
class OwnerSymbol:
    """One public owner symbol the GUI may bind, without calling it."""

    family: str
    module: str
    symbol: str
    owner: str
    relative_source: str


# Exact current public owners. Paths are repository-relative. SDK paths are
# relative to that owner's checkout root.
OWNER_SYMBOLS: tuple[OwnerSymbol, ...] = (
    OwnerSymbol("public_service", "applications.server", "SERVER", "first_party", "applications/server.py"),
    OwnerSymbol(
        "public_service",
        "applications.complaint_workspace",
        "ComplaintWorkspaceService",
        "first_party",
        "applications/complaint_workspace.py",
    ),
    OwnerSymbol(
        "public_service",
        "applications.complaint_workspace_api",
        "create_complaint_workspace_router",
        "first_party",
        "applications/complaint_workspace_api.py",
    ),
    OwnerSymbol("mediator", "mediator.mediator", "Mediator", "first_party", "mediator/mediator.py"),
    OwnerSymbol(
        "mediator",
        "mediator.workflow_service",
        "WorkflowActionService",
        "first_party",
        "mediator/workflow_service.py",
    ),
    OwnerSymbol(
        "data_kg",
        "ipfs_datasets_py.knowledge_graphs.extraction.extractor",
        "KnowledgeGraphExtractor",
        "ipfs_datasets_py",
        "ipfs_datasets_py/knowledge_graphs/extraction/extractor.py",
    ),
    OwnerSymbol(
        "data_legal",
        "ipfs_datasets_py.processors.legal_scrapers.legal_dataset_api",
        "search_us_code_corpus_from_parameters",
        "ipfs_datasets_py",
        "ipfs_datasets_py/processors/legal_scrapers/legal_dataset_api.py",
    ),
    OwnerSymbol(
        "data_formal",
        "integrations.ipfs_datasets.logic",
        "compile_canonical_legal_ir",
        "first_party",
        "integrations/ipfs_datasets/logic.py",
    ),
    OwnerSymbol(
        "kit_storage",
        "integrations.ipfs_datasets.storage",
        "store_private_artifact",
        "first_party",
        "integrations/ipfs_datasets/storage.py",
    ),
    OwnerSymbol(
        "kit_storage",
        "ipfs_kit_py.core.service_router",
        "ServiceRouter",
        "ipfs_kit_py",
        "ipfs_kit_py/core/service_router.py",
    ),
    OwnerSymbol(
        "router",
        "ipfs_accelerate_py.llm_router",
        "generate_text",
        "ipfs_accelerate_py",
        "ipfs_accelerate_py/llm_router.py",
    ),
    OwnerSymbol(
        "router",
        "integrations.ipfs_accelerate.routers",
        "pinned_grok47_dispatch_kwargs",
        "first_party",
        "integrations/ipfs_accelerate/routers.py",
    ),
)

REQUIRED_FAMILIES = (
    "public_service",
    "mediator",
    "data_kg",
    "data_legal",
    "data_formal",
    "kit_storage",
    "router",
)


def _repo_root() -> Path:
    return get_repo_paths().repo_root


def _source_path(spec: OwnerSymbol) -> Path:
    root = _repo_root()
    if spec.owner == "first_party":
        return root / spec.relative_source
    return root / _OWNER_ROOTS[spec.owner] / spec.relative_source


def _module_level_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in getattr(tree, "body", ()):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def probe_owner_symbol(spec: OwnerSymbol) -> dict[str, object]:
    """Record whether one public symbol exists. Do not import or call it."""

    path = _source_path(spec)
    canonical = path.relative_to(_repo_root()).as_posix() if path.is_absolute() else spec.relative_source
    try:
        canonical = path.resolve().relative_to(_repo_root().resolve()).as_posix()
    except (OSError, ValueError):
        canonical = spec.relative_source if spec.owner == "first_party" else f"{_OWNER_ROOTS[spec.owner]}/{spec.relative_source}"
    base = {
        "family": spec.family,
        "module": spec.module,
        "symbol": spec.symbol,
        "owner": spec.owner,
        "canonical_source_path": canonical,
        "resolution": "source_ast",
        "import_used": False,
        "operational_proof": False,
        "execution_status": EXECUTION_NOT_EXECUTED,
        "packages_installed": False,
    }
    try:
        present = path.is_file()
    except OSError:
        present = False
    if not present:
        base.update({
            "status": STATUS_UNAVAILABLE,
            "error_type": "FileNotFoundError",
            "symbol_present": False,
        })
        return base
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError, UnicodeError) as exc:
        base.update({
            "status": STATUS_UNAVAILABLE,
            "error_type": type(exc).__name__,
            "symbol_present": False,
        })
        return base
    found = spec.symbol in _module_level_names(tree)
    base.update({
        "status": STATUS_AVAILABLE if found else STATUS_UNAVAILABLE,
        "error_type": "" if found else "SymbolNotFound",
        "symbol_present": found,
    })
    return base


def _pin_record(name: str, relative_root: str, canonical_relative: str) -> dict[str, object]:
    root = _repo_root()
    owner_path = root / relative_root
    declared = declared_submodule_paths(root)
    classification = classify_owner_checkout(
        owner_path,
        canonical_relative=canonical_relative,
        declared_submodule=relative_root in declared,
    )
    observed = observe_checked_out_commit(owner_path)
    declared_pin = DECLARED_OWNER_PINS[name]
    commit = str(observed.get("commit") or "")
    status = str(observed.get("status") or STATUS_UNAVAILABLE)
    return {
        "name": name,
        "declared_pin": declared_pin,
        "relative_path": relative_root,
        "checkout_kind": classification["checkout_kind"],
        "populated": classification["populated"],
        "checked_out_commit": commit,
        "checked_out_commit_status": status,
        "checked_out_commit_error_type": str(observed.get("error_type") or ""),
        "pin_matches_observed_head": status == STATUS_AVAILABLE and commit == declared_pin,
        "submodule_updated": False,
    }


def record_pinned_revisions() -> dict[str, dict[str, object]]:
    """Record declared A/Data/Kit pins and the complaint-generator baseline.

    Observed heads are read when ``.git`` is readable. A missing observation
    stays unavailable and is not replaced by the declared pin.
    """

    revisions = {
        "complaint_generator": {
            "name": "complaint_generator",
            "declared_pin": SOURCE_BASELINE,
            "relative_path": "",
            "checkout_kind": "source_baseline",
            "populated": True,
            "checked_out_commit": "",
            "checked_out_commit_status": STATUS_UNAVAILABLE,
            "checked_out_commit_error_type": "NotProbed",
            "pin_matches_observed_head": False,
            "submodule_updated": False,
        }
    }
    for name, relative_root in _OWNER_ROOTS.items():
        revisions[name] = _pin_record(name, relative_root, _OWNER_CANONICAL[name])
    return revisions


def probe_gui_owner_capabilities() -> dict[str, object]:
    """Probe every declared owner symbol and attach pinned revisions.

    Every row stays ``not_executed``. Symbol presence is not a completed GUI
    behavior, a proof, or a live router or storage call.
    """

    symbols = [probe_owner_symbol(spec) for spec in OWNER_SYMBOLS]
    families = {spec.family for spec in OWNER_SYMBOLS}
    available = [row["symbol"] for row in symbols if row["status"] == STATUS_AVAILABLE]
    unavailable = [row["symbol"] for row in symbols if row["status"] == STATUS_UNAVAILABLE]
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "source_baseline": SOURCE_BASELINE,
        "pinned_revisions": record_pinned_revisions(),
        "families": list(REQUIRED_FAMILIES),
        "families_complete": families == set(REQUIRED_FAMILIES),
        "symbols": symbols,
        "available_symbols": available,
        "unavailable_symbols": unavailable,
        "not_executed_count": sum(1 for row in symbols if row["execution_status"] == EXECUTION_NOT_EXECUTED),
        "imports_used": False,
        "packages_installed": False,
        "operational_proof": False,
        "new_gui_behavior_satisfied": False,
        "known_limitations": [
            "source_symbol_presence_is_not_operational_proof",
            "router_storage_legal_and_formal_owners_were_not_executed",
            "browser_audit_and_old44_completion_do_not_satisfy_new_gui_behavior",
            "missing_accelerate_checkout_remains_unavailable",
        ],
    }


def gui_behavior_decision(evidence: Mapping[str, object] | None) -> dict[str, object]:
    """Refuse historical evidence as a substitute for new GUI behavior.

    This binder never certifies GUI behavior. Browser audits and old 44-task
    completions are named refusals. Any other payload is also refused.
    """

    if not isinstance(evidence, Mapping):
        return {"satisfied": False, "reason": "evidence_unavailable"}
    markers = {
        str(evidence.get("kind") or ""),
        str(evidence.get("evidence_kind") or ""),
        str(evidence.get("program") or ""),
        str(evidence.get("task_id") or ""),
    }
    if markers & _HISTORICAL_KINDS or evidence.get("browser_audit_completed") is True:
        if "browser_audit" in markers or "pinned_manual_audit" in markers or "pinned_manual_dom_audit" in markers or evidence.get("browser_audit_completed") is True:
            return {"satisfied": False, "reason": "browser_audit_cannot_satisfy_new_gui_behavior"}
        return {"satisfied": False, "reason": "old44_or_historical_completion_cannot_satisfy_new_gui_behavior"}
    if evidence.get("old44_complete") is True or evidence.get("old44_completion") is True:
        return {"satisfied": False, "reason": "old44_or_historical_completion_cannot_satisfy_new_gui_behavior"}
    if evidence.get("schema_version") == SCHEMA_VERSION:
        return {"satisfied": False, "reason": "capability_probe_is_not_gui_behavior"}
    return {"satisfied": False, "reason": "new_gui_behavior_not_certified"}


def evidence_satisfies_new_gui_behavior(evidence: Mapping[str, object] | None) -> bool:
    """Return whether evidence satisfies new GUI behavior. This module never does."""

    decision = gui_behavior_decision(evidence)
    if decision["satisfied"] is not False:
        return False
    return False


def assert_pin_shape(record: Mapping[str, object]) -> None:
    """Raise ValueError when a pin record is not a 40-hex declared revision."""

    pin = record.get("declared_pin")
    if not isinstance(pin, str) or _COMMIT.fullmatch(pin) is None:
        raise ValueError("declared_pin_unavailable")
