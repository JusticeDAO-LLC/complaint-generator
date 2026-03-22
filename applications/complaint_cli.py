from __future__ import annotations

import json
from typing import Optional

import typer

from .complaint_workspace import ComplaintWorkspaceService


app = typer.Typer(help="Unified complaint workspace CLI.")
service = ComplaintWorkspaceService()


def _print(payload) -> None:
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@app.command("session")
def session(user_id: str = "demo-user") -> None:
    _print(service.get_session(user_id))


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


def main() -> None:
    app()


if __name__ == "__main__":
    main()

