#!/usr/bin/env python3
"""Run repository-grounded HACC evidence upload plus adversarial optimization."""

from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Optional, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent
HACC_REPO_ROOT = WORKSPACE_ROOT / "HACC"
DEFAULT_PROVIDER = "codex"
DEFAULT_MODEL = "gpt-5.3-codex"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output" / "hacc_grounded" / datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _load_hacc_engine() -> Any:
    if str(HACC_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(HACC_REPO_ROOT))
    hacc_research = importlib.import_module("hacc_research")
    return getattr(hacc_research, "HACCResearchEngine")


def _load_complaint_synthesis_module() -> Any:
    scripts_dir = PROJECT_ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    return importlib.import_module("synthesize_hacc_complaint")


def _load_query_specs(preset: str) -> list[dict[str, Any]]:
    from adversarial_harness.hacc_evidence import get_hacc_query_specs

    return list(get_hacc_query_specs(preset=preset))


def _default_grounding_request(hacc_preset: str) -> Dict[str, str]:
    specs = _load_query_specs(hacc_preset)
    if not specs:
        return {"query": hacc_preset.replace("_", " "), "claim_type": "housing_discrimination"}
    first = dict(specs[0] or {})
    return {
        "query": str(first.get("query") or hacc_preset.replace("_", " ")),
        "claim_type": str(first.get("type") or "housing_discrimination"),
    }


def _grounding_overview(grounding_bundle: Dict[str, Any], upload_report: Dict[str, Any]) -> Dict[str, Any]:
    anchor_sections = [str(item) for item in list(grounding_bundle.get("anchor_sections") or []) if str(item)]
    anchor_passages = [dict(item) for item in list(grounding_bundle.get("anchor_passages") or []) if isinstance(item, dict)]
    upload_candidates = [dict(item) for item in list(grounding_bundle.get("upload_candidates") or []) if isinstance(item, dict)]
    mediator_packets = [dict(item) for item in list(grounding_bundle.get("mediator_evidence_packets") or []) if isinstance(item, dict)]
    top_documents: list[str] = []
    for item in upload_candidates[:3]:
        title = str(item.get("title") or item.get("relative_path") or item.get("source_path") or "").strip()
        if title and title not in top_documents:
            top_documents.append(title)
    return {
        "evidence_summary": str(grounding_bundle.get("evidence_summary") or "").strip(),
        "anchor_sections": anchor_sections,
        "anchor_passage_count": len(anchor_passages),
        "upload_candidate_count": len(upload_candidates),
        "mediator_packet_count": len(mediator_packets),
        "uploaded_evidence_count": int(upload_report.get("upload_count") or 0),
        "top_documents": top_documents,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def _run_adversarial_report(
    *,
    output_dir: Path,
    preset: str,
    num_sessions: int,
    hacc_count: int,
    max_turns: int,
    max_parallel: int,
    use_hacc_vector_search: bool,
    config_path: Optional[str],
    backend_id: Optional[str],
) -> Dict[str, Any]:
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "run_hacc_adversarial_report.py"),
        "--preset",
        preset,
        "--num-sessions",
        str(num_sessions),
        "--hacc-count",
        str(hacc_count),
        "--max-turns",
        str(max_turns),
        "--max-parallel",
        str(max_parallel),
        "--output-dir",
        str(output_dir),
    ]
    if use_hacc_vector_search:
        command.append("--use-vector-search")
    if config_path:
        command.extend(["--config", str(config_path)])
    if backend_id:
        command.extend(["--backend-id", str(backend_id)])
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    summary_path = output_dir / "run_summary.json"
    return json.loads(summary_path.read_text(encoding="utf-8"))


def _run_complaint_synthesis(
    *,
    grounded_run_dir: Path,
    filing_forum: str,
    preset: str,
    completed_intake_worksheet: Optional[str] = None,
) -> Dict[str, Any]:
    synthesis_module = _load_complaint_synthesis_module()
    output_dir = grounded_run_dir / "synthesized_complaint"
    argv = [
        "--results-json",
        str(grounded_run_dir / "adversarial" / "adversarial_results.json"),
        "--grounded-run-dir",
        str(grounded_run_dir),
        "--filing-forum",
        filing_forum,
        "--output-dir",
        str(output_dir),
        "--preset",
        preset,
    ]
    if completed_intake_worksheet:
        argv.extend(["--completed-intake-worksheet", completed_intake_worksheet])
    synthesis_module.main(argv)
    return {
        "output_dir": str(output_dir),
        "draft_complaint_package_json": str(output_dir / "draft_complaint_package.json"),
        "draft_complaint_package_md": str(output_dir / "draft_complaint_package.md"),
        "intake_follow_up_worksheet_json": str(output_dir / "intake_follow_up_worksheet.json"),
        "intake_follow_up_worksheet_md": str(output_dir / "intake_follow_up_worksheet.md"),
    }


def run_hacc_grounded_pipeline(
    *,
    output_dir: str | Path,
    query: Optional[str] = None,
    hacc_preset: str = "core_hacc_policies",
    claim_type: Optional[str] = None,
    top_k: int = 5,
    num_sessions: int = 3,
    max_turns: int = 4,
    max_parallel: int = 1,
    use_hacc_vector_search: bool = False,
    hacc_search_mode: str = "package",
    config_path: Optional[str] = None,
    backend_id: Optional[str] = None,
    synthesize_complaint: bool = False,
    filing_forum: str = "court",
    completed_intake_worksheet: Optional[str] = None,
) -> Dict[str, Any]:
    output_root = Path(output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    default_request = _default_grounding_request(hacc_preset)
    resolved_query = str(query or default_request["query"])
    resolved_claim_type = str(claim_type or default_request["claim_type"] or "housing_discrimination")

    engine_cls = _load_hacc_engine()
    engine = engine_cls(repo_root=HACC_REPO_ROOT)
    grounding_bundle = engine.build_grounding_bundle(
        resolved_query,
        top_k=top_k,
        claim_type=resolved_claim_type,
        search_mode=hacc_search_mode,
        use_vector=use_hacc_vector_search,
    )
    upload_report = engine.simulate_evidence_upload(
        resolved_query,
        top_k=top_k,
        claim_type=resolved_claim_type,
        user_id="complaint-generator-grounded",
        search_mode=hacc_search_mode,
        use_vector=use_hacc_vector_search,
        db_dir=output_root / "mediator_state",
    )
    adversarial_summary = _run_adversarial_report(
        output_dir=output_root / "adversarial",
        preset=hacc_preset,
        num_sessions=num_sessions,
        hacc_count=top_k,
        max_turns=max_turns,
        max_parallel=max_parallel,
        use_hacc_vector_search=use_hacc_vector_search,
        config_path=config_path,
        backend_id=backend_id,
    )
    grounding_overview = _grounding_overview(
        grounding_bundle if isinstance(grounding_bundle, dict) else {},
        upload_report if isinstance(upload_report, dict) else {},
    )

    _write_json(output_root / "grounding_bundle.json", grounding_bundle)
    _write_json(output_root / "grounding_overview.json", grounding_overview)
    _write_json(output_root / "anchor_passages.json", dict(grounding_bundle or {}).get("anchor_passages", []))
    _write_json(output_root / "upload_candidates.json", dict(grounding_bundle or {}).get("upload_candidates", []))
    _write_json(output_root / "mediator_evidence_packets.json", dict(grounding_bundle or {}).get("mediator_evidence_packets", []))
    _write_json(output_root / "synthetic_prompts.json", dict(grounding_bundle or {}).get("synthetic_prompts", {}))
    _write_json(output_root / "evidence_upload_report.json", upload_report)
    _write_json(output_root / "adversarial_summary.json", adversarial_summary)

    synthesis_summary: Dict[str, Any] = {}
    if synthesize_complaint:
        synthesis_summary = _run_complaint_synthesis(
            grounded_run_dir=output_root,
            filing_forum=filing_forum,
            preset=hacc_preset,
            completed_intake_worksheet=completed_intake_worksheet,
        )

    summary = {
        "timestamp": datetime.now(UTC).isoformat(),
        "grounding_query": resolved_query,
        "claim_type": resolved_claim_type,
        "hacc_preset": hacc_preset,
        "use_hacc_vector_search": bool(use_hacc_vector_search),
        "hacc_search_mode": hacc_search_mode,
        "search_summary": {
            "grounding": dict(grounding_bundle or {}).get("search_summary", {}),
            "evidence_upload": dict(upload_report or {}).get("search_summary", {}),
            "adversarial": dict(adversarial_summary or {}).get("search_summary", {}),
        },
        "grounding_overview": grounding_overview,
        "grounding": grounding_bundle,
        "evidence_upload": upload_report,
        "adversarial": adversarial_summary,
        "complaint_synthesis": synthesis_summary,
        "artifacts": {
            "output_dir": str(output_root),
            "grounding_bundle_json": str(output_root / "grounding_bundle.json"),
            "grounding_overview_json": str(output_root / "grounding_overview.json"),
            "anchor_passages_json": str(output_root / "anchor_passages.json"),
            "upload_candidates_json": str(output_root / "upload_candidates.json"),
            "mediator_evidence_packets_json": str(output_root / "mediator_evidence_packets.json"),
            "synthetic_prompts_json": str(output_root / "synthetic_prompts.json"),
            "evidence_upload_report_json": str(output_root / "evidence_upload_report.json"),
            "adversarial_summary_json": str(output_root / "adversarial_summary.json"),
            "adversarial_output_dir": str(output_root / "adversarial"),
            "complaint_synthesis_dir": synthesis_summary.get("output_dir", ""),
            "draft_complaint_package_json": synthesis_summary.get("draft_complaint_package_json", ""),
            "draft_complaint_package_md": synthesis_summary.get("draft_complaint_package_md", ""),
            "intake_follow_up_worksheet_json": synthesis_summary.get("intake_follow_up_worksheet_json", ""),
            "intake_follow_up_worksheet_md": synthesis_summary.get("intake_follow_up_worksheet_md", ""),
        },
    }
    _write_json(output_root / "run_summary.json", summary)
    return _json_safe(summary)


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run grounded HACC evidence upload simulation plus the complaint-generator adversarial workflow.",
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--query", default=None)
    parser.add_argument("--hacc-preset", default="core_hacc_policies")
    parser.add_argument("--claim-type", default=None)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--num-sessions", type=int, default=3)
    parser.add_argument("--max-turns", type=int, default=4)
    parser.add_argument("--max-parallel", type=int, default=1)
    parser.add_argument("--use-hacc-vector-search", action="store_true")
    parser.add_argument(
        "--hacc-search-mode",
        choices=("auto", "lexical", "hybrid", "vector", "package"),
        default="package",
    )
    parser.add_argument("--config", default=None)
    parser.add_argument("--backend-id", default=None)
    parser.add_argument("--synthesize-complaint", action="store_true")
    parser.add_argument("--filing-forum", default="court", choices=("court", "hud", "state_agency"))
    parser.add_argument("--completed-intake-worksheet", default=None)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = create_parser().parse_args(argv)
    summary = run_hacc_grounded_pipeline(
        output_dir=args.output_dir,
        query=args.query,
        hacc_preset=args.hacc_preset,
        claim_type=args.claim_type,
        top_k=args.top_k,
        num_sessions=args.num_sessions,
        max_turns=args.max_turns,
        max_parallel=args.max_parallel,
        use_hacc_vector_search=args.use_hacc_vector_search,
        hacc_search_mode=args.hacc_search_mode,
        config_path=args.config,
        backend_id=args.backend_id,
        synthesize_complaint=args.synthesize_complaint,
        filing_forum=args.filing_forum,
        completed_intake_worksheet=args.completed_intake_worksheet,
    )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"Output directory: {summary['artifacts']['output_dir']}")
        print(f"Grounding query: {summary['grounding_query']}")
        print(f"Uploaded evidence count: {summary['evidence_upload']['upload_count']}")
        print(f"Adversarial output directory: {summary['artifacts']['adversarial_output_dir']}")
        print(f"Synthetic prompts: {summary['artifacts']['synthetic_prompts_json']}")
        if summary["artifacts"].get("draft_complaint_package_json"):
            print(f"Draft complaint package: {summary['artifacts']['draft_complaint_package_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
