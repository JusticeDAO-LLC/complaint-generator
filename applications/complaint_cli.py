from __future__ import annotations

import argparse
import anyio
import json
import os
from pathlib import Path
from typing import Optional

import typer

from complaint_generator.email_credentials import resolve_gmail_credentials
from complaint_generator.email_import import import_gmail_evidence
from .complaint_workspace import ComplaintWorkspaceService
from .ui_review import run_ui_review_workflow


DEFAULT_UI_UX_SCREENSHOT_TARGET = (
    "tests/test_website_cohesion_playwright.py::"
    "test_homepage_navigation_can_drive_a_full_complaint_journey_with_real_handoffs"
)
DEFAULT_UI_UX_OPTIMIZER_METHOD = "actor_critic"
DEFAULT_UI_UX_OPTIMIZER_PRIORITY = 90


app = typer.Typer(help="Unified complaint workspace CLI.")
service = ComplaintWorkspaceService()


def _print(payload) -> None:
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


def _split_multiline_values(raw_value: Optional[str]) -> Optional[list[str]]:
    if not raw_value:
        return None
    values = [line.strip() for line in raw_value.splitlines() if line.strip()]
    return values or None


@app.command("session")
def session(user_id: str = "demo-user") -> None:
    _print(service.get_session(user_id))


@app.command("identity")
def identity() -> None:
    _print(service.call_mcp_tool("complaint.create_identity", {}))


@app.command("questions")
def questions() -> None:
    _print(service.list_intake_questions())


@app.command("claim-elements")
def claim_elements() -> None:
    _print(service.list_claim_elements())


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
    attachment_names: Optional[str] = None,
) -> None:
    _print(
        service.save_evidence(
            user_id,
            kind=kind,
            claim_element_id=claim_element_id,
            title=title,
            content=content,
            source=source,
            attachment_names=[item.strip() for item in str(attachment_names or "").split("|") if item.strip()],
        )
    )


@app.command("import-gmail-evidence")
def import_gmail_evidence_command(
    user_id: str = "demo-user",
    address: list[str] = typer.Option(..., "--address", help="Target address to match in From/To/Cc headers. Repeat for multiple addresses."),
    claim_element_id: str = "causation",
    folder: str = "INBOX",
    limit: Optional[int] = None,
    date_after: Optional[str] = None,
    date_before: Optional[str] = None,
    evidence_root: Optional[str] = None,
    gmail_user: Optional[str] = typer.Option(os.environ.get("GMAIL_USER") or os.environ.get("EMAIL_USER"), "--gmail-user"),
    gmail_app_password: Optional[str] = typer.Option(os.environ.get("GMAIL_APP_PASSWORD") or os.environ.get("EMAIL_PASS"), "--gmail-app-password"),
    prompt_for_credentials: bool = typer.Option(False, "--prompt-for-credentials"),
    use_keyring: bool = typer.Option(False, "--use-keyring"),
    save_to_keyring: bool = typer.Option(False, "--save-to-keyring"),
    use_ipfs_secrets_vault: bool = typer.Option(False, "--use-ipfs-secrets-vault"),
    save_to_ipfs_secrets_vault: bool = typer.Option(False, "--save-to-ipfs-secrets-vault"),
) -> None:
    parser = argparse.ArgumentParser(prog="complaint-workspace import-gmail-evidence")
    resolved_gmail_user, resolved_gmail_app_password = resolve_gmail_credentials(
        gmail_user=str(gmail_user or ""),
        gmail_app_password=str(gmail_app_password or ""),
        prompt_for_credentials=prompt_for_credentials,
        use_keyring=use_keyring,
        save_to_keyring_flag=save_to_keyring,
        use_ipfs_secrets_vault=use_ipfs_secrets_vault,
        save_to_ipfs_secrets_vault_flag=save_to_ipfs_secrets_vault,
        parser=parser,
    )

    async def _run_import() -> dict[str, object]:
        return await import_gmail_evidence(
            addresses=address,
            user_id=user_id,
            claim_element_id=claim_element_id,
            workspace_root=service._session_dir,
            evidence_root=Path(evidence_root) if evidence_root else None,
            folder=folder,
            limit=limit,
            date_after=date_after,
            date_before=date_before,
            gmail_user=resolved_gmail_user,
            gmail_app_password=resolved_gmail_app_password,
            service=service,
        )

    payload = anyio.run(_run_import)
    _print(payload)


@app.command("review")
def review(user_id: str = "demo-user") -> None:
    _print(service.call_mcp_tool("complaint.review_case", {"user_id": user_id}))


@app.command("mediator-prompt")
def mediator_prompt(user_id: str = "demo-user") -> None:
    _print(service.build_mediator_prompt(user_id))


@app.command("complaint-readiness")
def complaint_readiness(user_id: str = "demo-user") -> None:
    _print(service.get_complaint_readiness(user_id))


@app.command("ui-readiness")
def ui_readiness(user_id: str = "demo-user") -> None:
    _print(service.get_ui_readiness(user_id))


@app.command("client-release-gate")
def client_release_gate(user_id: str = "demo-user") -> None:
    _print(service.get_client_release_gate(user_id))


@app.command("capabilities")
def capabilities(user_id: str = "demo-user") -> None:
    _print(service.get_workflow_capabilities(user_id))


@app.command("tooling-contract")
def tooling_contract(user_id: str = "demo-user") -> None:
    _print(service.get_tooling_contract(user_id))


@app.command("generate")
def generate(
    user_id: str = "demo-user",
    requested_relief: str = "",
    title_override: Optional[str] = None,
    use_llm: bool = False,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    config_path: Optional[str] = None,
    backend_id: Optional[str] = None,
) -> None:
    relief_items = [line.strip() for line in requested_relief.split("|") if line.strip()]
    _print(
        service.generate_complaint(
            user_id,
            requested_relief=relief_items or None,
            title_override=title_override,
            use_llm=use_llm,
            provider=provider,
            model=model,
            config_path=config_path,
            backend_id=backend_id,
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


@app.command("export-packet")
def export_packet(user_id: str = "demo-user") -> None:
    _print(service.export_complaint_packet(user_id))


@app.command("export-markdown")
def export_markdown(user_id: str = "demo-user") -> None:
    _print(service.export_complaint_markdown(user_id))


@app.command("export-docx")
def export_docx(user_id: str = "demo-user") -> None:
    _print(service.export_complaint_docx(user_id))


@app.command("export-pdf")
def export_pdf(user_id: str = "demo-user") -> None:
    _print(service.export_complaint_pdf(user_id))


@app.command("analyze-output")
def analyze_output(user_id: str = "demo-user") -> None:
    _print(service.analyze_complaint_output(user_id))


@app.command("formal-diagnostics")
def formal_diagnostics(user_id: str = "demo-user") -> None:
    _print(service.get_formal_diagnostics(user_id))


@app.command("filing-provenance")
def filing_provenance(user_id: str = "demo-user") -> None:
    _print(service.get_filing_provenance(user_id))


@app.command("provider-diagnostics")
def provider_diagnostics(user_id: str = "demo-user") -> None:
    _print(service.get_provider_diagnostics(user_id))


@app.command("review-exports")
def review_exports(
    user_id: str = "demo-user",
    artifact_path: Optional[str] = None,
    artifact_dir: Optional[str] = None,
    notes: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    config_path: Optional[str] = None,
    backend_id: Optional[str] = None,
) -> None:
    _print(
        service.review_generated_exports(
            user_id,
            artifact_path=artifact_path,
            artifact_dir=artifact_dir,
            notes=notes,
            provider=provider,
            model=model,
            config_path=config_path,
            backend_id=backend_id,
        )
    )


@app.command("set-claim-type")
def set_claim_type(user_id: str = "demo-user", claim_type: str = "retaliation") -> None:
    _print(service.update_claim_type(user_id, claim_type))


@app.command("update-synopsis")
def update_synopsis(user_id: str = "demo-user", synopsis: str = "") -> None:
    _print(service.update_case_synopsis(user_id, synopsis))


@app.command("reset")
def reset(user_id: str = "demo-user") -> None:
    _print(service.reset_session(user_id))


@app.command("review-ui")
def review_ui(
    screenshot_dir: str,
    user_id: str = "demo-user",
    artifact_path: str = "artifacts/ui_review/latest.json",
    iterations: int = 0,
    notes: Optional[str] = None,
    goals: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    config_path: str = "config.llm_router.json",
    backend_id: Optional[str] = None,
    pytest_target: str = DEFAULT_UI_UX_SCREENSHOT_TARGET,
) -> None:
    goal_items = _split_multiline_values(goals)
    if iterations > 0:
        from complaint_generator.ui_ux_workflow import run_iterative_ui_ux_workflow

        supplemental_artifacts = service._build_complaint_output_review_artifacts(user_id)
        result = run_iterative_ui_ux_workflow(
            screenshot_dir=screenshot_dir,
            output_dir=str(Path(artifact_path).expanduser().resolve().parent),
            iterations=iterations,
            provider=provider,
            model=model,
            pytest_target=pytest_target,
            notes=notes,
            goals=goal_items,
            supplemental_artifacts=supplemental_artifacts,
        )
        service._persist_ui_readiness(user_id, result)
        _print(result)
        return
    result = run_ui_review_workflow(
        screenshot_dir,
        notes=notes,
        goals=goal_items,
        provider=provider,
        model=model,
        config_path=config_path,
        backend_id=backend_id,
        output_path=artifact_path,
    )
    service._persist_ui_readiness(user_id, result)
    _print(result)


@app.command("optimize-ui")
def optimize_ui(
    screenshot_dir: str,
    user_id: str = "demo-user",
    output_path: str = "artifacts/ui_review/closed-loop",
    max_rounds: int = 2,
    iterations: int = 1,
    notes: Optional[str] = None,
    goals: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    method: str = DEFAULT_UI_UX_OPTIMIZER_METHOD,
    priority: int = DEFAULT_UI_UX_OPTIMIZER_PRIORITY,
    pytest_target: str = DEFAULT_UI_UX_SCREENSHOT_TARGET,
) -> None:
    from complaint_generator.ui_ux_workflow import run_closed_loop_ui_ux_improvement

    goal_items = _split_multiline_values(goals)
    supplemental_artifacts = service._build_complaint_output_review_artifacts(user_id)
    result = run_closed_loop_ui_ux_improvement(
        screenshot_dir=screenshot_dir,
        output_dir=output_path,
        pytest_target=pytest_target,
        max_rounds=max_rounds,
        review_iterations=iterations,
        provider=provider,
        model=model,
        method=method,
        priority=priority,
        notes=notes,
        goals=goal_items,
        supplemental_artifacts=supplemental_artifacts,
    )
    service._persist_ui_readiness(user_id, result)
    _print(result)


@app.command("browser-audit")
def browser_audit(
    screenshot_dir: str = typer.Argument("artifacts/ui-audit/browser-audit"),
    pytest_target: str = DEFAULT_UI_UX_SCREENSHOT_TARGET,
) -> None:
    from complaint_generator.ui_ux_workflow import run_end_to_end_complaint_browser_audit

    _print(
        run_end_to_end_complaint_browser_audit(
            screenshot_dir=screenshot_dir,
            pytest_target=pytest_target,
        )
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
