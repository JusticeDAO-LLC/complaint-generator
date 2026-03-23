from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from backends import LLMRouterBackend, MultimodalRouterBackend


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCREENSHOT_TEST = (
    "tests/test_website_cohesion_playwright.py::"
    "test_user_interfaces_capture_screenshots_and_preserve_coherent_layout"
)


def _read_text(path: Path, limit: int = 12000) -> str:
    text = path.read_text()
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]..."


def collect_screenshot_artifacts(screenshot_dir: str | Path) -> list[dict[str, Any]]:
    root = Path(screenshot_dir)
    artifacts: list[dict[str, Any]] = []
    for metadata_path in sorted(root.glob("*.json")):
        payload = json.loads(metadata_path.read_text())
        artifacts.append(payload)
    return artifacts


def _artifact_image_paths(artifacts: list[dict[str, Any]]) -> list[str]:
    image_paths: list[str] = []
    for artifact in artifacts:
        raw_path = str(artifact.get("screenshot_path", "") or "").strip()
        if raw_path:
            image_paths.append(raw_path)
    return image_paths


def run_playwright_screenshot_audit(
    *,
    screenshot_dir: str | Path,
    pytest_target: str = DEFAULT_SCREENSHOT_TEST,
    pytest_executable: str | Path | None = None,
    workdir: str | Path | None = None,
) -> dict[str, Any]:
    target_dir = Path(screenshot_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    for stale in list(target_dir.glob("*.png")) + list(target_dir.glob("*.json")):
        stale.unlink()

    pytest_cmd = str(pytest_executable or (REPO_ROOT / ".venv" / "bin" / "pytest"))
    env = dict(os.environ)
    env["COMPLAINT_UI_SCREENSHOT_DIR"] = str(target_dir)

    completed = subprocess.run(
        [pytest_cmd, "-q", pytest_target],
        cwd=str(workdir or REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    artifacts = collect_screenshot_artifacts(target_dir)
    return {
        "command": [pytest_cmd, "-q", pytest_target],
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "screenshot_dir": str(target_dir),
    }


def build_ui_ux_review_prompt(
    *,
    iteration: int,
    artifacts: list[dict[str, Any]],
    previous_review: str | None = None,
    notes: str | None = None,
    goals: list[str] | None = None,
) -> str:
    workspace_html = _read_text(REPO_ROOT / "templates" / "workspace.html", limit=14000)
    sdk_source = _read_text(REPO_ROOT / "static" / "complaint_mcp_sdk.js", limit=8000)
    artifact_blocks = []
    for artifact in artifacts:
        artifact_blocks.append(
            "\n".join(
                [
                    f"Surface: {artifact.get('name', 'unknown')}",
                    f"URL: {artifact.get('url', '')}",
                    f"Title: {artifact.get('title', '')}",
                    f"Screenshot path: {artifact.get('screenshot_path', '')}",
                    f"Viewport: {json.dumps(artifact.get('viewport', {}), sort_keys=True)}",
                    "Visible text excerpt:",
                    str(artifact.get("text_excerpt", "")).strip(),
                ]
            )
        )

    prompt_sections = [
        "You are reviewing the complaint-generator MCP workspace and related complaint site surfaces.",
        "Focus on UI/UX problems that would make the site poorly suited for real user complaints.",
        "Prioritize issues around trauma-informed wording, complaint triage clarity, evidence capture usability, navigation coherence, draft confidence, and MCP SDK transparency.",
        "Also check that the complaint generator functionality remains legible as package exports, CLI tools, MCP server tools, and a JavaScript MCP SDK workflow.",
        f"Iteration: {iteration}",
    ]
    if goals:
        prompt_sections.extend(
            [
                "Additional workflow goals:",
                "\n".join(f"- {goal}" for goal in goals),
            ]
        )
    if notes:
        prompt_sections.extend(
            [
                "Additional review notes:",
                notes,
            ]
        )
    if previous_review:
        prompt_sections.extend(
            [
                "Previous review summary:",
                previous_review,
            ]
        )
    prompt_sections.extend(
        [
            "Surface artifacts:",
            "\n\n".join(artifact_blocks) or "No screenshot artifacts were captured.",
            "External interface contract:",
            (
                "Package exports: complaint_generator.ComplaintWorkspaceService, "
                "complaint_generator.handle_jsonrpc_message, "
                "complaint_generator.run_iterative_ui_ux_workflow, "
                "complaint_generator.run_closed_loop_ui_ux_improvement, "
                "complaint_generator.create_ui_review_report\n"
                "CLI tools: complaint-generator, complaint-workspace, complaint-generator-workspace, complaint-mcp-server, complaint-workspace optimize-ui\n"
                "MCP server tools: complaint.create_identity, complaint.start_session, complaint.submit_intake, complaint.save_evidence, complaint.review_case, complaint.generate_complaint, complaint.update_draft, complaint.reset_session, complaint.review_ui, complaint.optimize_ui\n"
                "Browser SDK: window.ComplaintMcpSdk.ComplaintMcpClient with bootstrapWorkspace(), getOrCreateDid(), callTool(), and optimizeUiArtifacts()"
            ),
            "Current workspace HTML:",
            workspace_html,
            "Current JavaScript MCP SDK:",
            sdk_source,
            (
                "Return markdown with these sections: `Top Risks`, `High-Impact UX Fixes`, "
                "`MCP/SDK Workflow Improvements`, `Complaint Intake Language Fixes`, "
                "`Playwright Assertions To Add`, and `Implementation Order`."
            ),
        ]
    )
    return "\n\n".join(prompt_sections)


def review_screenshot_audit_with_llm_router(
    *,
    screenshot_dir: str | Path,
    iteration: int = 1,
    provider: str | None = None,
    model: str | None = None,
    previous_review: str | None = None,
    notes: str | None = None,
    goals: list[str] | None = None,
) -> dict[str, Any]:
    artifacts = collect_screenshot_artifacts(screenshot_dir)
    prompt = build_ui_ux_review_prompt(
        iteration=iteration,
        artifacts=artifacts,
        previous_review=previous_review,
        notes=notes,
        goals=goals,
    )
    image_paths = _artifact_image_paths(artifacts)
    backend = MultimodalRouterBackend(
        id=f"complaint-ui-ux-review-{iteration}",
        provider=provider,
        model=model,
    )
    try:
        review_text = backend(
            prompt,
            image_paths=image_paths,
            system_prompt=(
                "You are reviewing complaint intake and MCP dashboard screenshots. "
                "Use the images and prompt together to find concrete UI/UX issues."
            ),
        )
    except Exception:
        fallback_backend = LLMRouterBackend(
            id=f"complaint-ui-ux-review-{iteration}-fallback",
            provider=provider,
            model=model,
        )
        review_text = fallback_backend(prompt)
    return {
        "iteration": iteration,
        "artifact_count": len(artifacts),
        "review": review_text,
        "artifacts": artifacts,
    }


def run_iterative_ui_ux_workflow(
    *,
    screenshot_dir: str | Path,
    iterations: int = 1,
    provider: str | None = None,
    model: str | None = None,
    output_dir: str | Path | None = None,
    pytest_target: str = DEFAULT_SCREENSHOT_TEST,
    notes: str | None = None,
    goals: list[str] | None = None,
    initial_previous_review: str | None = None,
) -> dict[str, Any]:
    target_output_dir = Path(output_dir or (Path(screenshot_dir) / "reviews"))
    target_output_dir.mkdir(parents=True, exist_ok=True)

    previous_review: str | None = initial_previous_review
    run_reports: list[dict[str, Any]] = []

    for iteration in range(1, max(1, iterations) + 1):
        audit = run_playwright_screenshot_audit(
            screenshot_dir=screenshot_dir,
            pytest_target=pytest_target,
        )
        if audit["returncode"] != 0:
            raise RuntimeError(
                "Playwright screenshot audit failed.\n"
                f"stdout:\n{audit['stdout']}\n\nstderr:\n{audit['stderr']}"
            )

        review = review_screenshot_audit_with_llm_router(
            screenshot_dir=screenshot_dir,
            iteration=iteration,
            provider=provider,
            model=model,
            previous_review=previous_review,
            notes=notes,
            goals=goals,
        )
        markdown_path = target_output_dir / f"iteration-{iteration:02d}-review.md"
        json_path = target_output_dir / f"iteration-{iteration:02d}-review.json"
        markdown_path.write_text(review["review"])
        json_path.write_text(json.dumps(review, indent=2, sort_keys=True))
        previous_review = review["review"]
        run_reports.append(
            {
                "iteration": iteration,
                "audit": audit,
                "artifact_count": review["artifact_count"],
                "review_excerpt": str(review["review"] or "")[:600],
                "review_markdown_path": str(markdown_path),
                "review_json_path": str(json_path),
            }
        )

    return {
        "iterations": len(run_reports),
        "screenshot_dir": str(screenshot_dir),
        "output_dir": str(target_output_dir),
        "latest_review": previous_review,
        "latest_review_markdown_path": str(target_output_dir / f"iteration-{len(run_reports):02d}-review.md") if run_reports else None,
        "latest_review_json_path": str(target_output_dir / f"iteration-{len(run_reports):02d}-review.json") if run_reports else None,
        "runs": run_reports,
    }


def run_closed_loop_ui_ux_improvement(
    *,
    screenshot_dir: str | Path,
    output_dir: str | Path,
    pytest_target: str = DEFAULT_SCREENSHOT_TEST,
    max_rounds: int = 2,
    review_iterations: int = 1,
    provider: str | None = None,
    model: str | None = None,
    method: str = "actor_critic",
    priority: int = 80,
    notes: str | None = None,
    goals: list[str] | None = None,
    constraints: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    llm_router: Any = None,
    patch_optimizer: Any = None,
    optimizer: Any = None,
    agent_id: str = "complaint-ui-ux-optimizer",
    components: dict[str, Any] | None = None,
    stop_when_review_stable: bool = True,
    break_on_no_changes: bool = True,
) -> dict[str, Any]:
    from adversarial_harness import Optimizer

    resolved_optimizer = optimizer or Optimizer()
    return resolved_optimizer.run_agentic_ui_ux_feedback_loop(
        screenshot_dir=screenshot_dir,
        output_dir=output_dir,
        pytest_target=pytest_target,
        max_rounds=max_rounds,
        review_iterations=review_iterations,
        provider=provider,
        model=model,
        method=method,
        priority=priority,
        notes=notes,
        goals=goals,
        constraints=constraints,
        metadata=metadata,
        llm_router=llm_router,
        optimizer=patch_optimizer,
        agent_id=agent_id,
        components=components,
        stop_when_review_stable=stop_when_review_stable,
        break_on_no_changes=break_on_no_changes,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the complaint-generator screenshot audit and llm_router UX review workflow.",
    )
    parser.add_argument("--screenshot-dir", default=str(REPO_ROOT / "artifacts" / "ui-audit" / "screenshots"))
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "artifacts" / "ui-audit" / "reviews"))
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--provider", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--pytest-target", default=DEFAULT_SCREENSHOT_TEST)
    parser.add_argument("--notes", default=None)
    parser.add_argument("--max-rounds", type=int, default=0)
    args = parser.parse_args(argv)

    if args.max_rounds > 0:
        result = run_closed_loop_ui_ux_improvement(
            screenshot_dir=args.screenshot_dir,
            output_dir=args.output_dir,
            pytest_target=args.pytest_target,
            max_rounds=args.max_rounds,
            review_iterations=args.iterations,
            provider=args.provider,
            model=args.model,
            notes=args.notes,
        )
    else:
        result = run_iterative_ui_ux_workflow(
            screenshot_dir=args.screenshot_dir,
            output_dir=args.output_dir,
            iterations=args.iterations,
            provider=args.provider,
            model=args.model,
            pytest_target=args.pytest_target,
            notes=args.notes,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


__all__ = [
    "DEFAULT_SCREENSHOT_TEST",
    "build_ui_ux_review_prompt",
    "collect_screenshot_artifacts",
    "review_screenshot_audit_with_llm_router",
    "run_closed_loop_ui_ux_improvement",
    "run_iterative_ui_ux_workflow",
    "run_playwright_screenshot_audit",
    "main",
]
