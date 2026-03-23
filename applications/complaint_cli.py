from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from .complaint_workspace import ComplaintWorkspaceService
from .ui_review import run_ui_review_workflow


app = typer.Typer(help="Unified complaint workspace CLI.")
service = ComplaintWorkspaceService()


def _print(payload) -> None:
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@app.command("session")
def session(user_id: str = "demo-user") -> None:
    _print(service.get_session(user_id))


@app.command("identity")
def identity() -> None:
    _print(service.call_mcp_tool("complaint.create_identity", {}))


@app.command("tools")
def tools() -> None:
    _print(service.list_mcp_tools())


@app.command("answer")
def answer(user_id: str = "demo-user", question_id: str = "", answer_text: str = "") -> None:
    _print(service.submit_intake_answers(user_id, {question_id: answer_text}))


@app.command("add-evidence")
def add_evidence(
    user_id: str = "demo-user",
    kind: str = "testimony",
    claim_element_id: str = "causation",
    title: str = "Untitled evidence",
    content: str = "",
    source: Optional[str] = None,
) -> None:
    _print(
        service.save_evidence(
            user_id,
            kind=kind,
            claim_element_id=claim_element_id,
            title=title,
            content=content,
            source=source,
        )
    )


@app.command("review")
def review(user_id: str = "demo-user") -> None:
    _print(service.call_mcp_tool("complaint.review_case", {"user_id": user_id}))


@app.command("generate")
def generate(
    user_id: str = "demo-user",
    requested_relief: str = "",
    title_override: Optional[str] = None,
) -> None:
    relief_items = [line.strip() for line in requested_relief.split("|") if line.strip()]
    _print(
        service.generate_complaint(
            user_id,
            requested_relief=relief_items or None,
            title_override=title_override,
        )
    )


@app.command("update-draft")
def update_draft(
    user_id: str = "demo-user",
    title: Optional[str] = None,
    body: Optional[str] = None,
    requested_relief: str = "",
) -> None:
    relief_items = [line.strip() for line in requested_relief.split("|") if line.strip()]
    _print(service.update_draft(user_id, title=title, body=body, requested_relief=relief_items or None))


@app.command("reset")
def reset(user_id: str = "demo-user") -> None:
    _print(service.reset_session(user_id))


@app.command("review-ui")
def review_ui(
    screenshot_dir: str,
    artifact_path: str = "artifacts/ui_review/latest.json",
    iterations: int = 0,
    notes: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    config_path: str = "config.llm_router.json",
    backend_id: Optional[str] = None,
    pytest_target: str = "tests/test_website_cohesion_playwright.py::test_user_interfaces_capture_screenshots_and_preserve_coherent_layout",
) -> None:
    if iterations > 0:
        from complaint_generator.ui_ux_workflow import run_iterative_ui_ux_workflow

        _print(
            run_iterative_ui_ux_workflow(
                screenshot_dir=screenshot_dir,
                output_dir=str(Path(artifact_path).expanduser().resolve().parent),
                iterations=iterations,
                provider=provider,
                model=model,
                pytest_target=pytest_target,
            )
        )
        return
    _print(
        run_ui_review_workflow(
            screenshot_dir,
            notes=notes,
            provider=provider,
            model=model,
            config_path=config_path,
            backend_id=backend_id,
            output_path=artifact_path,
        )
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
