from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping

from .loader import import_attr_optional, import_failure_message, import_module_optional


def _upstream_legal_data_exports() -> tuple[Any | None, Any | None]:
    builder, builder_error = import_attr_optional(
        "ipfs_datasets_py.processors.legal_data",
        "DocketDatasetBuilder",
    )
    loader, loader_error = import_attr_optional(
        "ipfs_datasets_py.processors.legal_data",
        "load_packaged_docket_dataset",
    )
    return (builder, builder_error), (loader, loader_error)


class _CompatDocketDataset:
    def __init__(self, payload: Mapping[str, Any]) -> None:
        self._payload: Dict[str, Any] = dict(payload or {})
        self._payload.setdefault("metadata", {})
        self._payload.setdefault("documents", [])
        self.metadata = self._payload["metadata"]

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._payload)

    def write_package(
        self,
        output_dir: str | Path,
        *,
        package_name: str = "packaged_docket_bundle",
        include_car: bool = False,
    ) -> Dict[str, Any]:
        package_root = Path(output_dir).expanduser().resolve()
        package_root.mkdir(parents=True, exist_ok=True)
        manifest_path = package_root / "manifest.json"
        payload = self.to_dict()
        payload.setdefault("package_name", package_name)
        payload.setdefault("include_car", bool(include_car))
        manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
        return {
            "manifest_json_path": str(manifest_path),
            "package_root": str(package_root),
            "package_name": package_name,
        }


class DocketDatasetBuilder:
    def __init__(self) -> None:
        (builder, _), _loader = _upstream_legal_data_exports()
        self._delegate = builder() if builder is not None else None

    @staticmethod
    def _wrap(payload: Mapping[str, Any]) -> _CompatDocketDataset:
        return _CompatDocketDataset(payload)

    def build_from_docket(self, payload: Mapping[str, Any]) -> Any:
        if self._delegate is not None:
            return self._delegate.build_from_docket(payload)
        return self._wrap(payload)

    def build_from_json_file(self, path: str | Path) -> Any:
        if self._delegate is not None:
            return self._delegate.build_from_json_file(path)
        resolved_path = Path(path).expanduser().resolve()
        return self._wrap(json.loads(resolved_path.read_text()))


def load_packaged_docket_dataset(path: str | Path) -> Any:
    _builder_export, (loader, _) = _upstream_legal_data_exports()
    if loader is not None:
        return loader(path)
    resolved_path = Path(path).expanduser().resolve()
    manifest_path = resolved_path
    if resolved_path.is_dir():
        manifest_path = resolved_path / "manifest.json"
    return _CompatDocketDataset(json.loads(manifest_path.read_text()))


def get_packaged_docket_operator_dashboard(path: str | Path) -> Dict[str, Any]:
    (_builder, _), (loader, loader_error) = _upstream_legal_data_exports()
    upstream_dashboard, _dashboard_error = import_attr_optional(
        "ipfs_datasets_py.processors.legal_data",
        "get_packaged_docket_operator_dashboard",
    )
    if upstream_dashboard is not None:
        return dict(upstream_dashboard(path) or {})
    dataset = load_packaged_docket_dataset(path)
    payload = dict(dataset.to_dict() if hasattr(dataset, "to_dict") else dataset)
    routing = dict((payload.get("metadata") or {}).get("latest_proof_packet_routing_explanation") or {})
    return {
        "source": "packaged_operator_dashboard",
        "dataset_id": payload.get("dataset_id"),
        "docket_id": payload.get("docket_id"),
        "case_name": payload.get("case_name"),
        "inspection": {
            "latest_routing_reason": str(routing.get("routing_reason") or ""),
            "authority_backed": bool(routing.get("authority_backed")),
            "document_count": len(list(payload.get("documents") or [])),
            "loader_error": str(loader_error or ""),
        },
    }


def load_packaged_docket_operator_dashboard_report(
    path: str | Path,
    *,
    report_format: str = "parsed",
) -> Any:
    upstream_report_loader, _ = import_attr_optional(
        "ipfs_datasets_py.processors.legal_data",
        "load_packaged_docket_operator_dashboard_report",
    )
    if upstream_report_loader is not None:
        return upstream_report_loader(path, report_format=report_format)
    dashboard = get_packaged_docket_operator_dashboard(path)
    normalized_format = str(report_format or "parsed").strip().lower()
    if normalized_format == "text":
        return (
            "Packaged Docket Operator Dashboard\n\n"
            f"Latest routing reason: {dashboard['inspection'].get('latest_routing_reason') or 'Unavailable'}"
        )
    return dashboard


def legal_module(name: str = "") -> Any:
    """Import a legal_data submodule on demand.

    The package init hashes state-law producer sources, so callers should
    invoke this inside the function that needs the symbol.
    """

    suffix = str(name or "").strip().strip(".")
    module_name = "ipfs_datasets_py.processors.legal_data" if not suffix else (
        suffix if suffix.startswith("ipfs_datasets_py.") else f"ipfs_datasets_py.processors.legal_data.{suffix}"
    )
    module, error = import_module_optional(module_name)
    if module is None:
        raise ImportError(import_failure_message(error) or f"{module_name} unavailable")
    return module


def load_legal_symbol(name: str, *, module: str = "") -> Any:
    legal = legal_module(module)
    if not hasattr(legal, name):
        raise ImportError(f"{legal.__name__} has no attribute {name}")
    return getattr(legal, name)


def summarize_docket_dataset(payload: Mapping[str, Any]) -> Dict[str, Any]:
    upstream_summary, _ = import_attr_optional(
        "ipfs_datasets_py.processors.legal_data",
        "summarize_docket_dataset",
    )
    if upstream_summary is not None:
        return dict(upstream_summary(payload) or {})
    normalized = dict(payload or {})
    return {
        "dataset_id": normalized.get("dataset_id"),
        "docket_id": normalized.get("docket_id"),
        "case_name": normalized.get("case_name"),
        "court": normalized.get("court"),
        "document_count": len(list(normalized.get("documents") or [])),
        "metadata_keys": sorted(dict(normalized.get("metadata") or {}).keys()),
    }
