from pathlib import Path
from typing import Any, Mapping, Optional

from applications.complaint_workspace import (
    ComplaintWorkspaceService,
    DEFAULT_CLAIM_ELEMENTS,
    DEFAULT_INTAKE_QUESTIONS,
    WorkspaceAccess,
    generate_decentralized_id,
)


def _resolve_service(
    service: Optional[ComplaintWorkspaceService] = None,
    *,
    root_dir: Optional[str | Path] = None,
    access: Optional[WorkspaceAccess] = None,
) -> ComplaintWorkspaceService:
    if service is not None:
        return service
    # Ordinary CLI and TUI callers are local operators. Ownership is explicit
    # trusted-local and does not install an external identity provider.
    local_access = access if access is not None else WorkspaceAccess.trusted_local()
    if root_dir is not None:
        return ComplaintWorkspaceService(root_dir=Path(root_dir), access=local_access)
    return ComplaintWorkspaceService(access=local_access)


def create_identity(
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).call_mcp_tool("complaint.create_identity", {})


def attach_complaint_workspace_routes(*args, **kwargs):
    from applications.complaint_workspace_api import attach_complaint_workspace_routes as _attach_routes

    return _attach_routes(*args, **kwargs)


def create_complaint_workspace_router(*args, **kwargs):
    from applications.complaint_workspace_api import create_complaint_workspace_router as _create_router

    return _create_router(*args, **kwargs)


def list_intake_questions(
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).list_intake_questions()


def list_claim_elements(
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).list_claim_elements()


def start_session(
    user_id: Optional[str] = None,
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).get_session(user_id)


def submit_intake_answers(
    user_id: Optional[str],
    answers: dict[str, Any],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).submit_intake_answers(user_id, answers)


def run_intake_chat_turn(
    user_id: Optional[str],
    *,
    message: Optional[str] = None,
    question_id: Optional[str] = None,
    expected_question_revision: Optional[int] = None,
    interview_action: Optional[str] = None,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    """Advance one intake turn and return the next typed inquiry.

    The first turn stores ``message`` on ``original_complaint`` (versioned
    narrative and revisions). Later structured ``question_id`` answers stay in
    ``intake_answers``. Graph start, answer, and resume use the same mediator
    transition for package, API, and MCP callers.
    """

    return _resolve_service(service, root_dir=root_dir).run_intake_chat_turn(
        user_id,
        message=message,
        question_id=question_id,
        expected_question_revision=expected_question_revision,
        interview_action=interview_action,
    )


def save_evidence(
    user_id: Optional[str],
    *,
    kind: str,
    claim_element_id: str,
    title: str,
    content: str,
    source: Optional[str] = None,
    attachment_names: Optional[list[str]] = None,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).save_evidence(
        user_id,
        kind=kind,
        claim_element_id=claim_element_id,
        title=title,
        content=content,
        source=source,
        attachment_names=attachment_names,
    )


def import_gmail_evidence(
    user_id: Optional[str],
    *,
    addresses: list[str],
    collect_all_messages: bool = False,
    claim_element_id: str = "causation",
    folder: str = "INBOX",
    folders: Optional[list[str]] = None,
    limit: Optional[int] = None,
    date_after: Optional[str] = None,
    date_before: Optional[str] = None,
    years_back: Optional[int] = None,
    evidence_root: Optional[str | Path] = None,
    gmail_user: Optional[str] = None,
    gmail_app_password: Optional[str] = None,
    use_gmail_oauth: bool = False,
    gmail_oauth_client_secrets: Optional[str] = None,
    gmail_oauth_token_cache: Optional[str] = None,
    gmail_oauth_open_browser: bool = True,
    complaint_query: Optional[str] = None,
    complaint_keywords: Optional[list[str]] = None,
    min_relevance_score: float = 0.0,
    use_uid_checkpoint: bool = False,
    checkpoint_name: Optional[str] = None,
    uid_window_size: Optional[int] = None,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).import_gmail_evidence(
        user_id,
        addresses=list(addresses or []),
        collect_all_messages=bool(collect_all_messages),
        claim_element_id=claim_element_id,
        folder=folder,
        folders=folders or [],
        limit=limit,
        date_after=date_after,
        date_before=date_before,
        years_back=years_back,
        evidence_root=str(evidence_root) if evidence_root is not None else None,
        gmail_user=gmail_user,
        gmail_app_password=gmail_app_password,
        use_gmail_oauth=use_gmail_oauth,
        gmail_oauth_client_secrets=gmail_oauth_client_secrets,
        gmail_oauth_token_cache=gmail_oauth_token_cache,
        gmail_oauth_open_browser=gmail_oauth_open_browser,
        complaint_query=complaint_query,
        complaint_keywords=complaint_keywords or [],
        min_relevance_score=min_relevance_score,
        use_uid_checkpoint=use_uid_checkpoint,
        checkpoint_name=checkpoint_name,
        uid_window_size=uid_window_size,
    )


def import_local_evidence(
    user_id: Optional[str],
    *,
    paths: list[str | Path],
    claim_element_id: str = "causation",
    kind: str = "document",
    evidence_root: Optional[str | Path] = None,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).import_local_evidence(
        user_id,
        paths=[str(item) for item in list(paths or []) if str(item).strip()],
        claim_element_id=claim_element_id,
        kind=kind,
        evidence_root=str(evidence_root) if evidence_root is not None else None,
    )


def run_gmail_duckdb_pipeline(
    user_id: Optional[str],
    *,
    addresses: list[str],
    collect_all_messages: bool = False,
    claim_element_id: str = "causation",
    folder: str = "INBOX",
    folders: Optional[list[str]] = None,
    years_back: Optional[int] = 2,
    date_after: Optional[str] = None,
    date_before: Optional[str] = None,
    complaint_query: Optional[str] = None,
    complaint_keywords: Optional[list[str]] = None,
    min_relevance_score: float = 0.0,
    evidence_root: Optional[str | Path] = None,
    gmail_user: Optional[str] = None,
    gmail_app_password: Optional[str] = None,
    use_gmail_oauth: bool = False,
    gmail_oauth_client_secrets: Optional[str] = None,
    gmail_oauth_token_cache: Optional[str] = None,
    gmail_oauth_open_browser: bool = True,
    checkpoint_name: str = "gmail-duckdb-pipeline",
    uid_window_size: int = 500,
    duckdb_build_every_batches: int = 10,
    max_batches: int = 20,
    duckdb_output_dir: Optional[str | Path] = None,
    append_to_existing_corpus: bool = False,
    bm25_search_query: Optional[str] = None,
    bm25_search_limit: int = 20,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).run_gmail_duckdb_pipeline(
        user_id,
        addresses=list(addresses or []),
        collect_all_messages=bool(collect_all_messages),
        claim_element_id=claim_element_id,
        folder=folder,
        folders=folders or [],
        years_back=years_back,
        date_after=date_after,
        date_before=date_before,
        complaint_query=complaint_query,
        complaint_keywords=complaint_keywords or [],
        min_relevance_score=min_relevance_score,
        evidence_root=str(evidence_root) if evidence_root is not None else None,
        gmail_user=gmail_user,
        gmail_app_password=gmail_app_password,
        use_gmail_oauth=use_gmail_oauth,
        gmail_oauth_client_secrets=gmail_oauth_client_secrets,
        gmail_oauth_token_cache=gmail_oauth_token_cache,
        gmail_oauth_open_browser=gmail_oauth_open_browser,
        checkpoint_name=checkpoint_name,
        uid_window_size=uid_window_size,
        duckdb_build_every_batches=duckdb_build_every_batches,
        max_batches=max_batches,
        duckdb_output_dir=str(duckdb_output_dir) if duckdb_output_dir is not None else None,
        append_to_existing_corpus=append_to_existing_corpus,
        bm25_search_query=bm25_search_query,
        bm25_search_limit=bm25_search_limit,
    )


def search_email_duckdb_corpus(
    *,
    index_path: str | Path,
    query: str,
    limit: int = 20,
    ranking: str = "bm25",
    bm25_k1: float = 1.2,
    bm25_b: float = 0.75,
) -> dict[str, Any]:
    from .email_pipeline import search_email_duckdb_corpus as _search_email_duckdb_corpus

    return _search_email_duckdb_corpus(
        index_path=index_path,
        query=query,
        limit=limit,
        ranking=ranking,
        bm25_k1=bm25_k1,
        bm25_b=bm25_b,
    )


def review_case(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).call_mcp_tool("complaint.review_case", {"user_id": user_id})


def build_mediator_prompt(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).build_mediator_prompt(user_id)


def get_complaint_readiness(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).get_complaint_readiness(user_id)


def get_ui_readiness(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).get_ui_readiness(user_id)


def get_client_release_gate(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).get_client_release_gate(user_id)


def get_workflow_capabilities(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).get_workflow_capabilities(user_id)


def get_tooling_contract(
    user_id: Optional[str] = None,
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).get_tooling_contract(user_id)


def get_workspace_data_schema(
    user_id: Optional[str] = None,
    *,
    manifest_path: Optional[str | Path] = None,
    statefile_path: Optional[str | Path] = None,
    evidence_db_path: Optional[str | Path] = None,
    legal_authority_db_path: Optional[str | Path] = None,
    claim_support_db_path: Optional[str | Path] = None,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).get_workspace_data_schema(
        user_id,
        manifest_path=str(manifest_path) if manifest_path is not None else None,
        statefile_path=str(statefile_path) if statefile_path is not None else None,
        evidence_db_path=str(evidence_db_path) if evidence_db_path is not None else None,
        legal_authority_db_path=str(legal_authority_db_path) if legal_authority_db_path is not None else None,
        claim_support_db_path=str(claim_support_db_path) if claim_support_db_path is not None else None,
    )


def migrate_legacy_workspace_data(
    user_id: Optional[str] = None,
    *,
    output_dir: Optional[str | Path] = None,
    statefile_path: Optional[str | Path] = None,
    evidence_db_path: Optional[str | Path] = None,
    legal_authority_db_path: Optional[str | Path] = None,
    claim_support_db_path: Optional[str | Path] = None,
    package_name: Optional[str] = None,
    include_car: bool = True,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).migrate_legacy_workspace_data(
        user_id,
        output_dir=str(output_dir) if output_dir is not None else None,
        statefile_path=str(statefile_path) if statefile_path is not None else None,
        evidence_db_path=str(evidence_db_path) if evidence_db_path is not None else None,
        legal_authority_db_path=str(legal_authority_db_path) if legal_authority_db_path is not None else None,
        claim_support_db_path=str(claim_support_db_path) if claim_support_db_path is not None else None,
        package_name=package_name,
        include_car=include_car,
    )


def search_workspace_dataset(
    input_path: str | Path,
    *,
    query: str,
    input_type: str = "packaged",
    search_backend: str = "bm25",
    top_k: int = 10,
    vector_dimension: int = 32,
    collection_id: Optional[str] = None,
    document_type: Optional[str] = None,
    claim_type: Optional[str] = None,
    claim_element_id: Optional[str] = None,
    source_type: Optional[str] = None,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).search_workspace_dataset(
        str(input_path),
        input_type=input_type,
        query=query,
        search_backend=search_backend,
        top_k=top_k,
        vector_dimension=vector_dimension,
        collection_id=collection_id,
        document_type=document_type,
        claim_type=claim_type,
        claim_element_id=claim_element_id,
        source_type=source_type,
    )


def view_workspace_dataset(
    input_path: str | Path,
    *,
    input_type: str = "packaged",
    include_document_text: bool = False,
    document_limit: int = 25,
    collection_id: Optional[str] = None,
    document_type: Optional[str] = None,
    claim_type: Optional[str] = None,
    claim_element_id: Optional[str] = None,
    source_type: Optional[str] = None,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).view_workspace_dataset(
        str(input_path),
        input_type=input_type,
        include_document_text=include_document_text,
        document_limit=document_limit,
        collection_id=collection_id,
        document_type=document_type,
        claim_type=claim_type,
        claim_element_id=claim_element_id,
        source_type=source_type,
    )


def get_draft_proof_report(
    user_id: Optional[str],
    *,
    state_code: Optional[str] = None,
    allow_live_scrape_fallback: bool = False,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).get_draft_proof_report(
        user_id,
        state_code=state_code,
        allow_live_scrape_fallback=allow_live_scrape_fallback,
    )


def render_draft_proof_report(
    user_id: Optional[str],
    *,
    state_code: Optional[str] = None,
    claim_id: str = "",
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).render_draft_proof_report(
        user_id, state_code=state_code, claim_id=claim_id,
    )


def pin_draft_proof_report(
    user_id: Optional[str],
    *,
    state_code: Optional[str] = None,
    claim_id: str = "",
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).pin_draft_proof_report(
        user_id, state_code=state_code, claim_id=claim_id,
    )


def score_draft_quality(
    user_id: Optional[str],
    *,
    state_code: Optional[str] = None,
    persist: bool = True,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).score_draft_quality(
        user_id, state_code=state_code, persist=persist,
    )


def get_privacy_policy(
    user_id: Optional[str] = None,
    case_id: Optional[str] = None,
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).get_privacy_policy(user_id, case_id=case_id)


def set_privacy_policy(
    user_id: Optional[str],
    mode: str,
    case_id: Optional[str] = None,
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).set_privacy_policy(
        user_id,
        mode,
        case_id=case_id,
    )


def dispatch_private_llm_turn(
    user_id: Optional[str],
    *,
    relevant_facts: list,
    rule_gaps: list,
    unrelated_evidence: list | None = None,
    sensitive_literals: list | None = None,
    key: bytes,
    key_id: str,
    provider: str | None = None,
    model_name: str | None = None,
    timeout: Any = None,
    campaign_settings: Mapping[str, Any] | None = None,
    stored_user_complaint: bool = False,
    turn_id: str = "",
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
    **options: Any,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).dispatch_private_llm_turn(
        user_id,
        relevant_facts=relevant_facts,
        rule_gaps=rule_gaps,
        unrelated_evidence=unrelated_evidence,
        sensitive_literals=sensitive_literals,
        key=key,
        key_id=key_id,
        provider=provider,
        model_name=model_name,
        timeout=timeout,
        campaign_settings=campaign_settings,
        stored_user_complaint=stored_user_complaint,
        turn_id=turn_id,
        **options,
    )


def inventory_private_data_classes(
    user_id: Optional[str] = None,
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).inventory_private_data_classes(user_id)


def improve_draft(
    user_id: Optional[str],
    *,
    state_code: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    config_path: Optional[str] = None,
    backend_id: Optional[str] = None,
    max_suggestions: int = 3,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).improve_draft(
        user_id,
        state_code=state_code,
        provider=provider,
        model=model,
        config_path=config_path,
        backend_id=backend_id,
        max_suggestions=max_suggestions,
    )


def get_proof_history(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).get_proof_history(user_id)


def generate_complaint(
    user_id: Optional[str],
    *,
    requested_relief: Optional[list[str]] = None,
    title_override: Optional[str] = None,
    use_llm: bool = False,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    config_path: Optional[str] = None,
    backend_id: Optional[str] = None,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).generate_complaint(
        user_id,
        requested_relief=requested_relief,
        title_override=title_override,
        use_llm=use_llm,
        provider=provider,
        model=model,
        config_path=config_path,
        backend_id=backend_id,
    )


def update_draft(
    user_id: Optional[str],
    *,
    title: Optional[str] = None,
    body: Optional[str] = None,
    requested_relief: Optional[list[str]] = None,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).update_draft(
        user_id,
        title=title,
        body=body,
        requested_relief=requested_relief,
    )


def build_mike_handoff(
    user_id: Optional[str],
    *,
    mike_base_url: Optional[str] = None,
    project_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    generate_draft_if_missing: bool = True,
    grounding_mode: Optional[str] = None,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).build_mike_handoff(
        user_id,
        mike_base_url=mike_base_url,
        project_id=project_id,
        workspace_id=workspace_id,
        generate_draft_if_missing=generate_draft_if_missing,
        grounding_mode=grounding_mode,
    )


def get_mike_integration_status(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).get_mike_integration_status(user_id)


def sync_mike_final_draft(
    user_id: Optional[str],
    *,
    body: str,
    title: Optional[str] = None,
    requested_relief: Optional[list[str]] = None,
    handoff_id: Optional[str] = None,
    project_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    mike_document_id: Optional[str] = None,
    citation_links: Optional[list[dict[str, Any]]] = None,
    redline_summary: Optional[str] = None,
    source_updated_at: Optional[str] = None,
    structured_deltas: Optional[list[dict[str, Any]]] = None,
    editor_metadata: Optional[dict[str, Any]] = None,
    grounding_mode: Optional[str] = None,
    assertion_annotations: Optional[list[dict[str, Any]]] = None,
    authority_links: Optional[list[dict[str, Any]]] = None,
    sync_provenance: Optional[dict[str, Any]] = None,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).sync_mike_final_draft(
        user_id,
        body=body,
        title=title,
        requested_relief=requested_relief,
        handoff_id=handoff_id,
        project_id=project_id,
        workspace_id=workspace_id,
        mike_document_id=mike_document_id,
        citation_links=citation_links,
        redline_summary=redline_summary,
        source_updated_at=source_updated_at,
        structured_deltas=structured_deltas,
        editor_metadata=editor_metadata,
        grounding_mode=grounding_mode,
        assertion_annotations=assertion_annotations,
        authority_links=authority_links,
        sync_provenance=sync_provenance,
    )


def export_encrypted_workspace(
    repository: str | Path,
    export_dir: str | Path,
    recovery_path: str | Path,
    session: Any,
    *,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    recovery_passphrase: str,
) -> dict[str, Any]:
    """Export ciphertext plus a versioned manifest, with recovery kept separate."""

    from integrations.private_storage import export_encrypted_workspace as _export

    return _export(
        repository,
        export_dir,
        recovery_path,
        session,
        tenant_id=tenant_id,
        case_id=case_id,
        principal_id=principal_id,
        recovery_passphrase=recovery_passphrase,
    )


def import_encrypted_workspace(
    repository: str | Path,
    export_dir: str | Path,
    recovery_path: str | Path,
    store_dir: str | Path,
    *,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    recovery_passphrase: str,
    store_passphrase: str | None = None,
) -> dict[str, Any]:
    """Restore a ciphertext archive in this process. A fresh process can call it too."""

    from integrations.private_storage import import_encrypted_workspace as _import

    return _import(
        repository,
        export_dir,
        recovery_path,
        store_dir,
        tenant_id=tenant_id,
        case_id=case_id,
        principal_id=principal_id,
        recovery_passphrase=recovery_passphrase,
        store_passphrase=store_passphrase,
    )


def rotate_wrapping_key(session: Any, new_passphrase: str, *, policy: str = "retain", crash_at: str | None = None) -> dict[str, Any]:
    """Rewrap the master key without reencrypting case ciphertext."""

    return session.rotate_wrapping_key(new_passphrase, policy=policy, crash_at=crash_at)


def rotate_data_key(
    session: Any,
    tenant_id: str,
    case_id: str,
    repository: str | Path,
    principal_id: str,
    *,
    policy: str = "retain",
    crash_at: str | None = None,
) -> dict[str, Any]:
    """Reencrypt the workspace under a new data key and retain the previous generation."""

    return session.rotate_data_key(
        tenant_id,
        case_id,
        repository,
        principal_id,
        policy=policy,
        crash_at=crash_at,
    )


def revoke_retained_keys(session: Any, tenant_id: str, case_id: str, repository: str | Path, **options: Any) -> dict[str, Any]:
    """Apply explicit retention policy. Rotation does not erase the only recovery path."""

    return session.revoke_retained_keys(tenant_id, case_id, repository, **options)


def delete_private_case(
    repository: str | Path,
    session: Any,
    *,
    tenant_id: str,
    case_id: str,
    policy: str,
    legal_hold: bool = False,
    workspace_required: bool = False,
    providers: Any = None,
    timeout_seconds: float | None = None,
    crash_at: str | None = None,
) -> dict[str, Any]:
    """Delete one case and return the scoped unpin, remote, and key receipts."""

    from integrations.private_storage import delete_private_case as _delete

    return _delete(
        repository,
        session,
        tenant_id=tenant_id,
        case_id=case_id,
        policy=policy,
        legal_hold=legal_hold,
        workspace_required=workspace_required,
        providers=providers,
        timeout_seconds=timeout_seconds,
        crash_at=crash_at,
    )


def normal_reset_retention_receipt() -> dict[str, Any]:
    """Show that a normal reset leaves encryption keys and recovery in place."""

    from integrations.private_storage import normal_reset_retention_receipt as _receipt

    return _receipt()


def export_complaint_packet(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).export_complaint_packet(user_id)


def export_complaint_markdown(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).export_complaint_markdown(user_id)


def export_complaint_pdf(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).export_complaint_pdf(user_id)


def export_complaint_docx(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).export_complaint_docx(user_id)


def analyze_complaint_output(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).analyze_complaint_output(user_id)


def get_formal_diagnostics(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).get_formal_diagnostics(user_id)


def get_filing_provenance(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).get_filing_provenance(user_id)


def get_provider_diagnostics(
    user_id: Optional[str] = None,
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).get_provider_diagnostics(user_id)


def view_docket_dataset(
    input_path: str | Path,
    *,
    input_type: str = "packaged",
    include_document_text: bool = False,
    document_limit: int = 25,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).view_docket_dataset(
        input_path,
        input_type=input_type,
        include_document_text=include_document_text,
        document_limit=document_limit,
    )


def search_docket_dataset(
    input_path: str | Path,
    *,
    query: str,
    input_type: str = "packaged",
    search_backend: str = "bm25",
    top_k: int = 10,
    vector_dimension: int = 32,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).search_docket_dataset(
        input_path,
        input_type=input_type,
        query=query,
        search_backend=search_backend,
        top_k=top_k,
        vector_dimension=vector_dimension,
    )


def get_docket_dataset_metadata(
    input_path: str | Path,
    *,
    input_type: str = "packaged",
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).get_docket_dataset_metadata(
        input_path,
        input_type=input_type,
    )


def get_docket_dataset_graph(
    input_path: str | Path,
    *,
    input_type: str = "packaged",
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).get_docket_dataset_graph(
        input_path,
        input_type=input_type,
    )


def get_packaged_docket_operator_dashboard(
    manifest_path: str | Path,
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).get_packaged_docket_operator_dashboard(manifest_path)


def load_packaged_docket_operator_dashboard_report(
    manifest_path: str | Path,
    *,
    report_format: str = "parsed",
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).load_packaged_docket_operator_dashboard_report(
        manifest_path,
        report_format=report_format,
    )


def execute_packaged_docket_proof_revalidation_queue(
    manifest_path: str | Path,
    *,
    top_k: int = 10,
    min_priority: str = "low",
    queue_limit: Optional[int] = None,
    execution_top_k: int = 10,
    chain_until_satisfied: bool = True,
    attach_refreshed_packets: bool = False,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).execute_packaged_docket_proof_revalidation_queue(
        manifest_path,
        top_k=top_k,
        min_priority=min_priority,
        queue_limit=queue_limit,
        execution_top_k=execution_top_k,
        chain_until_satisfied=chain_until_satisfied,
        attach_refreshed_packets=attach_refreshed_packets,
    )


def persist_packaged_docket_proof_revalidation_queue(
    manifest_path: str | Path,
    output_dir: str | Path,
    *,
    package_name: Optional[str] = None,
    include_car: bool = True,
    top_k: int = 10,
    min_priority: str = "low",
    queue_limit: Optional[int] = None,
    execution_top_k: int = 10,
    chain_until_satisfied: bool = True,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).persist_packaged_docket_proof_revalidation_queue(
        manifest_path,
        output_dir,
        package_name=package_name,
        include_car=include_car,
        top_k=top_k,
        min_priority=min_priority,
        queue_limit=queue_limit,
        execution_top_k=execution_top_k,
        chain_until_satisfied=chain_until_satisfied,
    )


def review_generated_exports(
    user_id: Optional[str] = None,
    *,
    artifact_path: Optional[str | Path] = None,
    artifact_dir: Optional[str | Path] = None,
    notes: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    config_path: Optional[str] = None,
    backend_id: Optional[str] = None,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).review_generated_exports(
        user_id,
        artifact_path=str(artifact_path) if artifact_path is not None else None,
        artifact_dir=str(artifact_dir) if artifact_dir is not None else None,
        notes=notes,
        provider=provider,
        model=model,
        config_path=config_path,
        backend_id=backend_id,
    )


def update_claim_type(
    user_id: Optional[str],
    claim_type: str,
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).update_claim_type(user_id, claim_type)


def update_case_synopsis(
    user_id: Optional[str],
    synopsis: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).update_case_synopsis(user_id, synopsis)


def reset_session(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).reset_session(user_id)


def list_mcp_tools(
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).list_mcp_tools()


def review_ui(
    *,
    screenshot_paths: Optional[list[str]] = None,
    screenshot_dir: Optional[str | Path] = None,
    user_id: Optional[str] = None,
    notes: Optional[str] = None,
    goals: Optional[list[str]] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    config_path: Optional[str] = None,
    backend_id: Optional[str] = None,
    output_path: Optional[str | Path] = None,
    iterations: int = 0,
    pytest_target: Optional[str] = None,
    reuse_existing_screenshots: bool = False,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "user_id": user_id,
        "notes": notes,
        "goals": goals,
        "provider": provider,
        "model": model,
        "config_path": config_path,
        "backend_id": backend_id,
        "iterations": iterations,
        "pytest_target": pytest_target,
        "reuse_existing_screenshots": reuse_existing_screenshots,
    }
    if screenshot_paths is not None:
        arguments["screenshot_paths"] = screenshot_paths
    if screenshot_dir is not None:
        arguments["screenshot_dir"] = str(screenshot_dir)
    if output_path is not None:
        arguments["output_path"] = str(output_path)
    return _resolve_service(service, root_dir=root_dir).call_mcp_tool("complaint.review_ui", arguments)


def optimize_ui(
    *,
    screenshot_dir: str | Path,
    user_id: Optional[str] = None,
    output_path: Optional[str | Path] = None,
    max_rounds: int = 2,
    iterations: int = 1,
    notes: Optional[str] = None,
    goals: Optional[list[str]] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    method: Optional[str] = None,
    priority: Optional[int] = None,
    pytest_target: Optional[str] = None,
    reuse_existing_screenshots: bool = False,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "screenshot_dir": str(screenshot_dir),
        "user_id": user_id,
        "max_rounds": max_rounds,
        "iterations": iterations,
        "notes": notes,
        "goals": goals,
        "provider": provider,
        "model": model,
        "method": method,
        "priority": priority,
        "pytest_target": pytest_target,
        "reuse_existing_screenshots": reuse_existing_screenshots,
    }
    if output_path is not None:
        arguments["output_path"] = str(output_path)
    return _resolve_service(service, root_dir=root_dir).call_mcp_tool("complaint.optimize_ui", arguments)


def run_browser_audit(
    *,
    screenshot_dir: str | Path,
    pytest_target: Optional[str] = None,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).call_mcp_tool(
        "complaint.run_browser_audit",
        {
            "screenshot_dir": str(screenshot_dir),
            "pytest_target": pytest_target,
        },
    )


def run_closed_loop_ui_ux_improvement(*args, **kwargs):
    from complaint_generator.ui_ux_workflow import run_closed_loop_ui_ux_improvement as _run_closed_loop

    return _run_closed_loop(*args, **kwargs)


def run_end_to_end_complaint_browser_audit(*args, **kwargs):
    from complaint_generator.ui_ux_workflow import (
        run_end_to_end_complaint_browser_audit as _run_end_to_end_browser_audit,
    )

    return _run_end_to_end_browser_audit(*args, **kwargs)


def run_iterative_ui_ux_workflow(*args, **kwargs):
    from complaint_generator.ui_ux_workflow import run_iterative_ui_ux_workflow as _run_iterative_workflow

    return _run_iterative_workflow(*args, **kwargs)

__all__ = [
    "ComplaintWorkspaceService",
    "DEFAULT_CLAIM_ELEMENTS",
    "DEFAULT_INTAKE_QUESTIONS",
    "attach_complaint_workspace_routes",
    "build_mediator_prompt",
    "get_complaint_readiness",
    "get_ui_readiness",
    "get_client_release_gate",
    "get_tooling_contract",
    "get_workspace_data_schema",
    "create_identity",
    "create_complaint_workspace_router",
    "export_encrypted_workspace",
    "import_encrypted_workspace",
    "rotate_wrapping_key",
    "rotate_data_key",
    "revoke_retained_keys",
    "export_complaint_packet",
    "export_complaint_markdown",
    "export_complaint_pdf",
    "export_complaint_docx",
    "analyze_complaint_output",
    "get_formal_diagnostics",
    "get_draft_proof_report",
    "render_draft_proof_report",
    "pin_draft_proof_report",
    "score_draft_quality",
    "improve_draft",
    "get_proof_history",
    "get_filing_provenance",
    "get_provider_diagnostics",
    "get_privacy_policy",
    "set_privacy_policy",
    "dispatch_private_llm_turn",
    "inventory_private_data_classes",
    "get_packaged_docket_operator_dashboard",
    "load_packaged_docket_operator_dashboard_report",
    "execute_packaged_docket_proof_revalidation_queue",
    "persist_packaged_docket_proof_revalidation_queue",
    "review_generated_exports",
    "update_claim_type",
    "generate_decentralized_id",
    "generate_complaint",
    "build_mike_handoff",
    "get_mike_integration_status",
    "get_workflow_capabilities",
    "migrate_legacy_workspace_data",
    "search_workspace_dataset",
    "view_workspace_dataset",
    "import_gmail_evidence",
    "list_claim_elements",
    "list_intake_questions",
    "list_mcp_tools",
    "optimize_ui",
    "reset_session",
    "review_ui",
    "review_case",
    "run_intake_chat_turn",
    "run_gmail_duckdb_pipeline",
    "run_browser_audit",
    "run_closed_loop_ui_ux_improvement",
    "run_end_to_end_complaint_browser_audit",
    "run_iterative_ui_ux_workflow",
    "save_evidence",
    "search_email_duckdb_corpus",
    "start_session",
    "submit_intake_answers",
    "sync_mike_final_draft",
    "update_case_synopsis",
    "update_draft",
]
