from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
IPFS_DATASETS_SRC = REPO_ROOT / "ipfs_datasets_py"
if IPFS_DATASETS_SRC.exists():
    sys.path.insert(0, str(IPFS_DATASETS_SRC))


def test_ipld_logic_storage_uses_real_ipld_components(caplog, tmp_path):
    caplog.set_level(logging.WARNING)
    module_name = "ipfs_datasets_py.logic.integration.caching.ipld_logic_storage"
    sys.modules.pop(module_name, None)
    importlib.invalidate_caches()

    storage_module = importlib.import_module(module_name)
    storage = storage_module.LogicIPLDStorage(str(tmp_path / "logic-ipld"))

    assert storage_module.IPLD_AVAILABLE is True
    assert storage.use_ipld is True
    assert type(storage.block_manager).__name__ == "IPLDStorage"
    assert not [
        record.getMessage()
        for record in caplog.records
        if "IPLD components not available" in record.getMessage()
    ]
