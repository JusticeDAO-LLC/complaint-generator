from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
IPFS_DATASETS_SRC = REPO_ROOT / "ipfs_datasets_py"
if IPFS_DATASETS_SRC.exists():
    sys.path.insert(0, str(IPFS_DATASETS_SRC))


def _fresh_import(module_name: str) -> object:
    for name in list(sys.modules):
        if name == module_name or name.startswith(module_name + "."):
            sys.modules.pop(name, None)
    importlib.invalidate_caches()
    return importlib.import_module(module_name)


def test_symbolicai_symai_import_is_configured_without_fallback_warning(caplog):
    caplog.set_level(logging.WARNING)

    from ipfs_datasets_py.logic.common.feature_detection import FeatureDetector
    from ipfs_datasets_py.utils.symai_config import ensure_symai_config_for_import

    assert ensure_symai_config_for_import() is not None
    assert FeatureDetector.has_symbolicai() is True

    bridge = _fresh_import("ipfs_datasets_py.logic.integration.bridges.symbolic_fol_bridge")
    verifier = _fresh_import("ipfs_datasets_py.logic.integration.reasoning.logic_verification")
    modal = _fresh_import("ipfs_datasets_py.logic.integration.converters.modal_logic_extension")
    prover = _fresh_import("ipfs_datasets_py.logic.external_provers.neural.symbolicai_prover_bridge")

    assert getattr(bridge, "SYMBOLIC_AI_AVAILABLE") is True
    assert getattr(verifier, "SYMBOLIC_AI_AVAILABLE") is True
    assert getattr(modal, "SYMBOLIC_AI_AVAILABLE") is True
    assert getattr(prover, "SYMBOLICAI_AVAILABLE") is True
    assert not [
        record.message
        for record in caplog.records
        if "SymbolicAI not available" in record.getMessage()
    ]
