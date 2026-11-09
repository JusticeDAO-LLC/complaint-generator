"""Focused regression coverage for REF-132's Kubo command probe."""

from unittest.mock import Mock, patch

import pytest

from integrations.ipfs_datasets import storage


pytestmark = pytest.mark.no_auto_network


class KuboCLIBackend:
    """Kubo-shaped test backend whose configured command is immutable."""

    __slots__ = ("_cmd",)

    def __init__(self) -> None:
        object.__setattr__(self, "_cmd", "ipfs")

    def __setattr__(self, name: str, value: object) -> None:
        if name == "_cmd":
            raise RuntimeError("backend command is immutable")
        object.__setattr__(self, name, value)


def test_kubo_probe_reports_discovered_command_assignment_failure() -> None:
    backend = KuboCLIBackend()
    discovered_cmd = "/opt/repo/ipfs/bin/ipfs"

    with patch.object(storage, "IPFS_AVAILABLE", True), patch.object(
        storage,
        "_ensure_local_kubo_environment",
        return_value=discovered_cmd,
    ), patch.object(storage, "get_ipfs_backend", return_value=backend), patch.object(
        storage.shutil,
        "which",
        return_value=None,
    ):
        result = storage.storage_backend_status()

    assert result["status"] == "unavailable"
    assert result["backend_name"] == "KuboCLIBackend"
    assert result["backend_present"] is True
    assert result["error"] == (
        "failed to configure discovered ipfs CLI binary "
        "'/opt/repo/ipfs/bin/ipfs': RuntimeError: backend command is immutable"
    )
    assert result["metadata"]["backend_available"] is False
    assert result["metadata"]["degraded_reason"] == result["error"]


def test_store_bytes_does_not_call_router_after_kubo_assignment_failure() -> None:
    backend = KuboCLIBackend()
    add_bytes = Mock(return_value="unexpected-cid")

    with patch.object(storage, "IPFS_AVAILABLE", True), patch.object(
        storage,
        "_ensure_local_kubo_environment",
        return_value="/opt/repo/ipfs/bin/ipfs",
    ), patch.object(storage, "get_ipfs_backend", return_value=backend), patch.object(
        storage.shutil,
        "which",
        return_value=None,
    ), patch.object(storage, "add_bytes", add_bytes):
        result = storage.store_bytes(b"complaint evidence")

    assert result["status"] == "unavailable"
    assert result["cid"] == ""
    assert "backend command is immutable" in result["error"]
    assert result["metadata"]["backend_available"] is False
    add_bytes.assert_not_called()
