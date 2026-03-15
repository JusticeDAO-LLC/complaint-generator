import argparse
import json
import logging
import sys
from datetime import UTC, datetime
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
        description="Run a HACC evidence-backed adversarial harness batch and write JSON/CSV/Markdown reports."
    )
    parser.add_argument("--config", default="config.llm_router.json")
    parser.add_argument("--backend-id", default=None, help="Backend id from config.BACKENDS")
    parser.add_argument(
        "--preset",
        default="core_hacc_policies",
        help="Named HACC anchor preset to run",
    )
    parser.add_argument("--num-sessions", type=int, default=4)
    parser.add_argument("--hacc-count", type=int, default=4)
    parser.add_argument("--max-turns", type=int, default=6)
    parser.add_argument("--max-parallel", type=int, default=2)
    parser.add_argument("--use-vector-search", action="store_true")
    parser.add_argument("--disable-local-ipfs-fallback", action="store_true")
    parser.add_argument("--probe-llm-router", action="store_true")
    parser.add_argument("--probe-embeddings-router", action="store_true")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for outputs; defaults to output/hacc_adversarial/<timestamp>",
    )
    args = parser.parse_args()

    from adversarial_harness import AdversarialHarness, HACC_QUERY_PRESETS, Optimizer
    from backends import LLMRouterBackend
    from integrations.ipfs_datasets import ensure_ipfs_backend, get_router_status_report
    from mediator.mediator import Mediator

    if args.preset not in HACC_QUERY_PRESETS:
        raise ValueError(
            f"Unknown preset '{args.preset}'. Available presets: {', '.join(sorted(HACC_QUERY_PRESETS.keys()))}"
        )

    logging.basicConfig(level=logging.INFO)

    config = _load_config(args.config)
    backend_kwargs = _get_llm_router_backend_config(config, args.backend_id)
    if not args.disable_local_ipfs_fallback:
        ensure_ipfs_backend(prefer_local_fallback=True)
    router_report = get_router_status_report(
        llm_config=backend_kwargs,
        embeddings_config=config.get("EMBEDDINGS") if isinstance(config.get("EMBEDDINGS"), dict) else None,
        probe_llm=args.probe_llm_router,
        probe_embeddings=args.probe_embeddings_router,
        probe_text="HACC complaint-generation router health check",
    )

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir or (PROJECT_ROOT / "output" / "hacc_adversarial" / timestamp)).resolve()
    session_state_dir = output_dir / "sessions"
    output_dir.mkdir(parents=True, exist_ok=True)
    session_state_dir.mkdir(parents=True, exist_ok=True)

    logging.info("Output directory: %s", output_dir)
    logging.info("Preset: %s", args.preset)
    logging.info("Router status: %s", router_report.get("status"))

    complainant_backend = LLMRouterBackend(**backend_kwargs)
    critic_backend = LLMRouterBackend(**backend_kwargs)

    def mediator_factory(**kwargs):
        return Mediator(backends=[LLMRouterBackend(**backend_kwargs)], **kwargs)

    harness = AdversarialHarness(
        llm_backend_complainant=complainant_backend,
        llm_backend_critic=critic_backend,
        mediator_factory=mediator_factory,
        max_parallel=args.max_parallel,
        session_state_dir=str(session_state_dir),
    )

    results = harness.run_batch(
        num_sessions=args.num_sessions,
        max_turns_per_session=args.max_turns,
        include_hacc_evidence=True,
        hacc_count=args.hacc_count,
        hacc_preset=args.preset,
        use_hacc_vector_search=args.use_vector_search,
    )

    statistics = harness.get_statistics()
    optimizer_report = Optimizer().analyze(results).to_dict()

    results_path = output_dir / "adversarial_results.json"
    optimizer_path = output_dir / "optimizer_report.json"
    anchor_csv_path = output_dir / "anchor_section_coverage.csv"
    anchor_md_path = output_dir / "anchor_section_coverage.md"
    summary_path = output_dir / "run_summary.json"

    harness.save_results(str(results_path))
    harness.save_anchor_section_report(str(anchor_csv_path), format="csv")
    harness.save_anchor_section_report(str(anchor_md_path), format="markdown")

    summary_payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "preset": args.preset,
        "num_sessions": args.num_sessions,
        "hacc_count": args.hacc_count,
        "max_turns": args.max_turns,
        "use_vector_search": args.use_vector_search,
        "router_report": router_report,
        "statistics": statistics,
        "artifacts": {
            "results_json": str(results_path),
            "optimizer_report_json": str(optimizer_path),
            "anchor_section_coverage_csv": str(anchor_csv_path),
            "anchor_section_coverage_md": str(anchor_md_path),
            "session_state_dir": str(session_state_dir),
        },
    }

    with open(optimizer_path, "w", encoding="utf-8") as handle:
        json.dump(optimizer_report, handle, indent=2)
    with open(summary_path, "w", encoding="utf-8") as handle:
        json.dump(summary_payload, handle, indent=2)

    print(f"Saved run outputs to {output_dir}")
    print(f"Preset: {args.preset}")
    print(f"Router status: {router_report.get('status')}")
    print(f"Successful sessions: {statistics.get('successful_sessions', 0)}/{statistics.get('total_sessions', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
