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
    "test_dashboard_end_to_end_complaint_journey_uses_chat_review_builder_and_optimizer"
)
DEFAULT_OPTIMIZER_METHOD = "actor_critic"
DEFAULT_OPTIMIZER_PRIORITY = 90
DEFAULT_UI_UX_REVIEW_GOALS = [
    "Make the complaint generator easier for first-time complainants to complete without legal coaching.",
    "Keep intake, evidence, review, draft, package, CLI, MCP, and JavaScript SDK paths visibly connected as one workflow.",
    "Expose every major complaint-generator capability with clearer next-step guidance so users can actually use the full system.",
    "Prefer calmer, trauma-informed language and remove friction that makes evidence capture or draft completion feel risky or confusing.",
    "Make the end-to-end actor journey work cleanly from testimony and intake through evidence upload, claim review, complaint generation, and final draft revision.",
]
DEFAULT_COMPLAINT_WORKFLOW_CAPABILITIES = [
    "Intake questions can be understood and completed without legal coaching.",
    "Evidence capture makes it clear what proof helps each claim element.",
    "Support review makes missing elements and next evidence steps obvious.",
    "Draft generation and editing feel like the natural continuation of intake and review.",
    "The workspace makes progress, readiness, and next-step guidance legible under stress.",
    "Package, CLI, MCP server, and JavaScript SDK entry points remain discoverable as first-class capabilities.",
    "The actor/critic optimizer path is clearly available, while adversarial pressure-testing remains discoverable as a secondary stress lane.",
]
DEFAULT_UI_UX_REVIEW_NOTES = (
    "Review the interface as if a stressed first-time complainant and a complaint operator both need to succeed without hand-holding. "
    "Actively look for places where the user could miss a required step, misunderstand what evidence helps prove, lose track of progress, "
    "or fail to discover package, CLI, MCP, and browser SDK capabilities that should remain part of one coherent complaint workflow."
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


def _resolve_review_goals(goals: list[str] | None) -> list[str]:
    cleaned = [goal.strip() for goal in (goals or []) if str(goal).strip()]
    return cleaned or list(DEFAULT_UI_UX_REVIEW_GOALS)


def _resolve_review_notes(notes: str | None) -> str:
    cleaned = str(notes or "").strip()
    return cleaned or DEFAULT_UI_UX_REVIEW_NOTES


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


def run_end_to_end_complaint_browser_audit(
    *,
    screenshot_dir: str | Path,
    pytest_executable: str | Path | None = None,
    workdir: str | Path | None = None,
    pytest_target: str = DEFAULT_SCREENSHOT_TEST,
) -> dict[str, Any]:
    return run_playwright_screenshot_audit(
        screenshot_dir=screenshot_dir,
        pytest_target=pytest_target,
        pytest_executable=pytest_executable,
        workdir=workdir,
    )


def build_ui_ux_review_prompt(
    *,
    iteration: int,
    artifacts: list[dict[str, Any]],
    previous_review: str | None = None,
    notes: str | None = None,
    goals: list[str] | None = None,
) -> str:
    resolved_goals = _resolve_review_goals(goals)
    resolved_notes = _resolve_review_notes(notes)
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
        "Treat this as an actor/critic workflow audit with adversarial pressure-testing: identify where a real user could fail to complete the full complaint journey, where the UI hides the next best step, or where major product capabilities disappear from view.",
        "Treat this as an adversarial workflow audit: identify where a real user could fail to complete the full complaint journey or miss major product capabilities.",
        "Explicitly audit visible buttons, links, tabs, and handoff controls. Treat any dead, misleading, duplicated, or context-losing control as a release blocker until proven otherwise.",
        "Use an actor/critic lens: the actor should propose the smallest high-impact UX repair sequence, and the critic should decide whether the dashboard is actually safe to send legal clients through.",
        f"Iteration: {iteration}",
    ]
    prompt_sections.extend(
        [
            "Workflow goals:",
            "\n".join(f"- {goal}" for goal in resolved_goals),
            "Review notes:",
            resolved_notes,
            "Required capability audit:",
            "\n".join(f"- {capability}" for capability in DEFAULT_COMPLAINT_WORKFLOW_CAPABILITIES),
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
                "complaint_generator.start_session, "
                "complaint_generator.submit_intake_answers, "
                "complaint_generator.save_evidence, "
                "complaint_generator.review_case, "
                "complaint_generator.build_mediator_prompt, "
                "complaint_generator.get_workflow_capabilities, "
                "complaint_generator.generate_complaint, "
                "complaint_generator.update_draft, "
                "complaint_generator.export_complaint_packet, "
                "complaint_generator.update_case_synopsis, "
                "complaint_generator.handle_jsonrpc_message, "
                "complaint_generator.run_iterative_ui_ux_workflow, "
                "complaint_generator.run_closed_loop_ui_ux_improvement, "
                "complaint_generator.run_end_to_end_complaint_browser_audit, "
                "complaint_generator.create_ui_review_report\n"
                "CLI tools: complaint-generator, complaint-workspace, complaint-generator-workspace, complaint-mcp-server, complaint-workspace review-ui, complaint-workspace optimize-ui, complaint-workspace browser-audit\n"
                "MCP server tools: complaint.create_identity, complaint.list_intake_questions, complaint.list_claim_elements, complaint.start_session, complaint.submit_intake, complaint.save_evidence, complaint.review_case, complaint.build_mediator_prompt, complaint.get_workflow_capabilities, complaint.generate_complaint, complaint.update_draft, complaint.export_complaint_packet, complaint.update_case_synopsis, complaint.reset_session, complaint.review_ui, complaint.optimize_ui, complaint.run_browser_audit\n"
                "Browser SDK: window.ComplaintMcpSdk.ComplaintMcpClient with bootstrapWorkspace(), getOrCreateDid(), callTool(), reviewUiArtifacts(), optimizeUiArtifacts(), and runBrowserAudit()"
            ),
            "Current workspace HTML:",
            workspace_html,
            "Current JavaScript MCP SDK:",
            sdk_source,
            (
                "Return markdown with these sections: `Top Risks`, `High-Impact UX Fixes`, "
                "`Complaint Journey Coverage`, `Hidden Or Missing Feature Paths`, `Stage Findings`, "
                "`Actor Journey Findings`, `Critic Test Obligations`, `MCP/SDK Workflow Improvements`, `Actor Plan`, `Critic Verdict`, `Complaint Intake Language Fixes`, "
                "`Playwright Assertions To Add`, and `Implementation Order`."
            ),
            (
                "Under `Stage Findings`, use explicit subsections named `Intake`, `Evidence`, `Review`, `Draft`, and `Integration Discovery`, "
                "each with concrete UX failures or fixes for that stage."
            ),
            (
                "Under `Actor Journey Findings`, explicitly state whether a user can complete intake, save a shared synopsis for the mediator path, add testimony, upload or attach evidence, review claim support, generate a complaint, and revise the final draft from the shared MCP SDK-driven workspace."
            ),
            (
                "Under `Critic Test Obligations`, list the exact Playwright end-to-end checks that should fail if buttons, navigation, shared state, SDK invocations, or stage transitions break."
            ),
            (
                "Under `Playwright Assertions To Add`, include a control audit matrix that names the exact button, link, or tab to click, the expected route or state transition, and the expected visible text confirming success."
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
    resolved_goals = _resolve_review_goals(goals)
    resolved_notes = _resolve_review_notes(notes)
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
            notes=resolved_notes,
            goals=resolved_goals,
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
    method: str = DEFAULT_OPTIMIZER_METHOD,
    priority: int = DEFAULT_OPTIMIZER_PRIORITY,
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

    resolved_goals = _resolve_review_goals(goals)
    resolved_notes = _resolve_review_notes(notes)
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
        notes=resolved_notes,
        goals=resolved_goals,
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
    parser.add_argument("--goal", dest="goals", action="append", default=None)
    parser.add_argument("--method", default=DEFAULT_OPTIMIZER_METHOD)
    parser.add_argument("--priority", type=int, default=DEFAULT_OPTIMIZER_PRIORITY)
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
            goals=args.goals,
            method=args.method,
            priority=args.priority,
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
            goals=args.goals,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


__all__ = [
    "DEFAULT_SCREENSHOT_TEST",
    "DEFAULT_COMPLAINT_WORKFLOW_CAPABILITIES",
    "DEFAULT_OPTIMIZER_PRIORITY",
    "build_ui_ux_review_prompt",
    "collect_screenshot_artifacts",
    "DEFAULT_UI_UX_REVIEW_GOALS",
    "DEFAULT_UI_UX_REVIEW_NOTES",
    "review_screenshot_audit_with_llm_router",
    "run_end_to_end_complaint_browser_audit",
    "run_closed_loop_ui_ux_improvement",
    "run_iterative_ui_ux_workflow",
    "run_playwright_screenshot_audit",
    "main",
]
