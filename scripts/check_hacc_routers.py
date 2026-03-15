import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _get_llm_router_backend_config(config: Dict[str, Any], backend_id: str | None) -> Dict[str, Any]:
    backend_ids = config.get("MEDIATOR", {}).get("backends", [])
    if not backend_id:
        backend_id = backend_ids[0] if backend_ids else None
    if not backend_id:
        raise ValueError("No backend id specified and config.MEDIATOR.backends is empty")

    backend_config = next(
        (backend for backend in config.get("BACKENDS", []) if backend.get("id") == backend_id),
        None,
    )
    if not backend_config:
        raise ValueError(f"Backend id not found in config.BACKENDS: {backend_id}")
    if backend_config.get("type") != "llm_router":
        raise ValueError(f"Backend {backend_id} must have type 'llm_router'")

    backend_kwargs = dict(backend_config)
    backend_kwargs.pop("type", None)
    return backend_kwargs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check llm_router, ipfs_router, and embeddings_router availability for the HACC complaint workflow."
    )
    parser.add_argument("--config", default="config.llm_router.json")
    parser.add_argument("--backend-id", default=None, help="Backend id from config.BACKENDS")
    parser.add_argument("--disable-local-ipfs-fallback", action="store_true")
    parser.add_argument("--probe-llm-router", action="store_true")
    parser.add_argument("--probe-embeddings-router", action="store_true")
    parser.add_argument("--output", default=None, help="Optional path to write the JSON report")
    args = parser.parse_args()

    from integrations.ipfs_datasets import ensure_ipfs_backend, get_router_status_report

    config = _load_config(args.config)
    backend_kwargs = _get_llm_router_backend_config(config, args.backend_id)
    embeddings_config = config.get("EMBEDDINGS") if isinstance(config.get("EMBEDDINGS"), dict) else None
    if not args.disable_local_ipfs_fallback:
        ensure_ipfs_backend(prefer_local_fallback=True)
    report = get_router_status_report(
        llm_config=backend_kwargs,
        embeddings_config=embeddings_config,
        probe_llm=args.probe_llm_router,
        probe_embeddings=args.probe_embeddings_router,
        probe_text="HACC complaint-generation router health check",
    )

    if args.output:
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Saved router report to {output_path}")

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
