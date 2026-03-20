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
    if not backend_id:
        raise ValueError("backend_id is required")

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


def _get_llm_router_backend_candidates(config: Dict[str, Any], backend_id: str | None) -> list[str]:
    backend_ids = config.get("MEDIATOR", {}).get("backends", [])
    if backend_id:
        return [backend_id]
    candidates = [value for value in backend_ids if value]
    for backend in config.get("BACKENDS", []):
        candidate_id = str(backend.get("id") or "").strip()
        if candidate_id and backend.get("type") == "llm_router" and candidate_id not in candidates:
            candidates.append(candidate_id)
    return candidates


def _probe_backend_config(backend_kwargs: Dict[str, Any], probe_prompt: str) -> tuple[bool, str]:
    from backends import LLMRouterBackend

    try:
        response = LLMRouterBackend(**backend_kwargs)(probe_prompt)
    except Exception as exc:
        return False, str(exc)
    if not isinstance(response, str) or not response.strip():
        return False, "empty_generation"
    return True, ""


def _select_llm_router_backend_config(
    config: Dict[str, Any],
    backend_id: str | None,
    *,
    probe_prompt: str = "Reply with exactly OK.",
) -> tuple[str, Dict[str, Any], list[Dict[str, Any]], bool]:
    candidate_ids = _get_llm_router_backend_candidates(config, backend_id)
    if not candidate_ids:
        raise ValueError("No backend id specified and no llm_router backends are configured")

    probe_attempts: list[Dict[str, Any]] = []
    first_backend_id = candidate_ids[0]
    first_backend_kwargs = _get_llm_router_backend_config(config, first_backend_id)

    for candidate_id in candidate_ids:
        candidate_kwargs = _get_llm_router_backend_config(config, candidate_id)
        ok, error = _probe_backend_config(candidate_kwargs, probe_prompt)
        probe_attempts.append(
            {
                "backend_id": candidate_id,
                "ok": ok,
                "error": error,
            }
        )
        if ok:
            return candidate_id, candidate_kwargs, probe_attempts, True

    return first_backend_id, first_backend_kwargs, probe_attempts, False


def _serialize_phase_patch_tasks(optimizer: Any, results: list[Any], report: Any) -> list[Dict[str, Any]]:
    fallback_components_getter = getattr(optimizer, "_fallback_agentic_optimizer_components", None)
    components = fallback_components_getter() if callable(fallback_components_getter) else None
    phase_tasks, _ = optimizer.build_phase_patch_tasks(
        results,
        report=report,
        components=components,
    )
    payloads: list[Dict[str, Any]] = []
    for task in list(phase_tasks or []):
        payloads.append(
            {
                "task_id": str(getattr(task, "task_id", "") or ""),
                "description": str(getattr(task, "description", "") or ""),
                "target_files": [str(path) for path in list(getattr(task, "target_files", []) or [])],
                "method": str(getattr(task, "method", "") or ""),
                "priority": int(getattr(task, "priority", 0) or 0),
                "metadata": dict(getattr(task, "metadata", {}) or {}),
            }
        )
    return payloads


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
    selected_backend_id, backend_kwargs, probe_attempts, selected_backend_healthy = _select_llm_router_backend_config(
        config,
        args.backend_id,
    )
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
    logging.info("Selected backend: %s (healthy=%s)", selected_backend_id, selected_backend_healthy)
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
    optimizer = Optimizer()
    optimizer_report = optimizer.analyze(results)
    optimizer_payload = optimizer_report.to_dict()
    workflow_phase_tasks = _serialize_phase_patch_tasks(optimizer, results, optimizer_report)

    results_path = output_dir / "adversarial_results.json"
    optimizer_path = output_dir / "optimizer_report.json"
    workflow_tasks_path = output_dir / "workflow_phase_tasks.json"
    anchor_csv_path = output_dir / "anchor_section_coverage.csv"
    anchor_md_path = output_dir / "anchor_section_coverage.md"
    summary_path = output_dir / "run_summary.json"

    harness.save_results(str(results_path))
    harness.save_anchor_section_report(str(anchor_csv_path), format="csv")
    harness.save_anchor_section_report(str(anchor_md_path), format="markdown")

    summary_payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "preset": args.preset,
        "selected_backend_id": selected_backend_id,
        "selected_backend_healthy": selected_backend_healthy,
        "backend_probe_attempts": probe_attempts,
        "num_sessions": args.num_sessions,
        "hacc_count": args.hacc_count,
        "max_turns": args.max_turns,
        "use_vector_search": args.use_vector_search,
        "router_report": router_report,
        "statistics": statistics,
        "workflow_phase_plan": optimizer_payload.get("workflow_phase_plan") or {},
        "workflow_phase_task_count": len(workflow_phase_tasks),
        "artifacts": {
            "results_json": str(results_path),
            "optimizer_report_json": str(optimizer_path),
            "workflow_phase_tasks_json": str(workflow_tasks_path),
            "anchor_section_coverage_csv": str(anchor_csv_path),
            "anchor_section_coverage_md": str(anchor_md_path),
            "session_state_dir": str(session_state_dir),
        },
    }

    with open(optimizer_path, "w", encoding="utf-8") as handle:
        json.dump(optimizer_payload, handle, indent=2)
    with open(workflow_tasks_path, "w", encoding="utf-8") as handle:
        json.dump(workflow_phase_tasks, handle, indent=2)
    with open(summary_path, "w", encoding="utf-8") as handle:
        json.dump(summary_payload, handle, indent=2)

    print(f"Saved run outputs to {output_dir}")
    print(f"Preset: {args.preset}")
    print(f"Selected backend: {selected_backend_id} (healthy={selected_backend_healthy})")
    print(f"Router status: {router_report.get('status')}")
    print(f"Successful sessions: {statistics.get('successful_sessions', 0)}/{statistics.get('total_sessions', 0)}")
    print(f"Workflow phase tasks: {len(workflow_phase_tasks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
