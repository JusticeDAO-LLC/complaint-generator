"""Runtime module ownership and entrypoint map.

This registry is intentionally data-only. Refactor tasks can import it without
constructing FastAPI apps, mediator services, browser fixtures, or CLI parsers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List, Mapping, Tuple


RUNTIME_ROLE_CLI = "cli"
RUNTIME_ROLE_WEB = "web"
RUNTIME_ROLE_MEDIATOR = "mediator"
RUNTIME_ROLE_WORKFLOW = "workflow"

VALID_RUNTIME_ROLES: Tuple[str, ...] = (
    RUNTIME_ROLE_CLI,
    RUNTIME_ROLE_WEB,
    RUNTIME_ROLE_MEDIATOR,
    RUNTIME_ROLE_WORKFLOW,
)


@dataclass(frozen=True)
class RuntimeEntrypoint:
    """Named runtime entrypoint owned by a module."""

    name: str
    target: str
    kind: str
    description: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class ModuleOwnership:
    """Boundary record for a large runtime module."""

    module_path: str
    role: str
    owner: str
    primary_responsibility: str
    entrypoints: Tuple[RuntimeEntrypoint, ...]
    boundary_notes: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, object]:
        payload = asdict(self)
        payload["entrypoints"] = [entrypoint.to_dict() for entrypoint in self.entrypoints]
        return payload


_OWNERSHIP_ROWS: Tuple[ModuleOwnership, ...] = (
    ModuleOwnership(
        module_path="applications.complaint_workspace",
        role=RUNTIME_ROLE_WEB,
        owner="workspace application surface",
        primary_responsibility=(
            "Owns persisted workspace session state and the service methods used "
            "by the web routes, package wrappers, CLI wrappers, and MCP protocol."
        ),
        entrypoints=(
            RuntimeEntrypoint(
                name="ComplaintWorkspaceService",
                target="applications.complaint_workspace.ComplaintWorkspaceService",
                kind="service",
                description="Canonical workspace service for session, evidence, review, export, and docket operations.",
            ),
            RuntimeEntrypoint(
                name="workspace package wrappers",
                target="complaint_generator.workspace",
                kind="package-api",
                description="Stable import surface that delegates to ComplaintWorkspaceService.",
            ),
        ),
        boundary_notes=(
            "HTTP route registration stays in applications.complaint_workspace_api.",
            "Protocol translation stays in applications.complaint_mcp_protocol.",
        ),
    ),
    ModuleOwnership(
        module_path="applications.review_api",
        role=RUNTIME_ROLE_WEB,
        owner="claim-support review API surface",
        primary_responsibility="Owns FastAPI JSON routes for claim-support and document review payloads.",
        entrypoints=(
            RuntimeEntrypoint(
                name="attach_claim_support_review_routes",
                target="applications.review_api.attach_claim_support_review_routes",
                kind="fastapi-router",
                description="Mounts review API routes onto an existing FastAPI app.",
            ),
            RuntimeEntrypoint(
                name="create_review_api_app",
                target="applications.review_api.create_review_api_app",
                kind="fastapi-app",
                description="Builds the standalone review API app.",
            ),
        ),
        boundary_notes=("Business orchestration remains on the mediator and claim_support_review payload builders.",),
    ),
    ModuleOwnership(
        module_path="applications.review_ui",
        role=RUNTIME_ROLE_WEB,
        owner="operator review UI surface",
        primary_responsibility="Owns FastAPI route composition for browser-facing review and document workflows.",
        entrypoints=(
            RuntimeEntrypoint(
                name="create_review_dashboard_app",
                target="applications.review_ui.create_review_dashboard_app",
                kind="fastapi-app",
                description="Builds the review dashboard app.",
            ),
            RuntimeEntrypoint(
                name="create_review_surface_app",
                target="applications.review_ui.create_review_surface_app",
                kind="fastapi-app",
                description="Builds the combined review surface app.",
            ),
        ),
    ),
    ModuleOwnership(
        module_path="applications.complaint_cli",
        role=RUNTIME_ROLE_CLI,
        owner="workspace CLI surface",
        primary_responsibility="Owns Typer command registration for packaged complaint workspace commands.",
        entrypoints=(
            RuntimeEntrypoint(
                name="main",
                target="applications.complaint_cli.main",
                kind="console-script",
                description="Target for complaint-workspace and complaint-generator-workspace console scripts.",
            ),
        ),
        boundary_notes=("Command handlers delegate to ComplaintWorkspaceService instead of storing state directly.",),
    ),
    ModuleOwnership(
        module_path="scripts.synthesize_hacc_complaint",
        role=RUNTIME_ROLE_CLI,
        owner="HACC synthesis CLI workflow",
        primary_responsibility=(
            "Owns command-line synthesis of a grounded HACC complaint from adversarial run outputs, "
            "matrix summaries, and intake worksheets."
        ),
        entrypoints=(
            RuntimeEntrypoint(
                name="main",
                target="scripts.synthesize_hacc_complaint.main",
                kind="script-main",
                description="CLI parser and execution entrypoint for HACC complaint synthesis.",
            ),
        ),
        boundary_notes=("Reusable evidence extraction remains in adversarial_harness and complaint_phases helpers.",),
    ),
    ModuleOwnership(
        module_path="mediator.mediator",
        role=RUNTIME_ROLE_MEDIATOR,
        owner="mediator orchestration layer",
        primary_responsibility=(
            "Owns the Mediator facade, hook composition, three-phase workflow coordination, "
            "and backward-compatible mediator method surface."
        ),
        entrypoints=(
            RuntimeEntrypoint(
                name="Mediator",
                target="mediator.mediator.Mediator",
                kind="service-facade",
                description="Runtime facade used by CLI, server, review API, and workflow tests.",
            ),
        ),
        boundary_notes=(
            "Hook implementation details stay in mediator.*_hooks modules.",
            "Phase-specific graph and denoising behavior stays in complaint_phases.",
        ),
    ),
    ModuleOwnership(
        module_path="complaint_phases.denoiser",
        role=RUNTIME_ROLE_WORKFLOW,
        owner="intake denoising workflow",
        primary_responsibility=(
            "Owns question generation, answer digestion, gap closure scoring, and workflow-phase "
            "ranking for the intake denoising loop."
        ),
        entrypoints=(
            RuntimeEntrypoint(
                name="ComplaintDenoiser",
                target="complaint_phases.denoiser.ComplaintDenoiser",
                kind="workflow-service",
                description="Three-phase intake denoising service instantiated by the Mediator.",
            ),
        ),
        boundary_notes=(
            "Graph persistence belongs to complaint_phases.knowledge_graph and integration adapters.",
            "Mediator-specific lifecycle orchestration remains in mediator.mediator.",
        ),
    ),
)


MODULE_OWNERSHIP_BY_MODULE: Mapping[str, ModuleOwnership] = {
    row.module_path: row for row in _OWNERSHIP_ROWS
}

RUNTIME_ENTRYPOINT_GROUPS: Mapping[str, Tuple[ModuleOwnership, ...]] = {
    role: tuple(row for row in _OWNERSHIP_ROWS if row.role == role)
    for role in VALID_RUNTIME_ROLES
}


def get_module_ownership(module_path: str) -> ModuleOwnership | None:
    """Return the ownership record for a module path, if one is registered."""

    return MODULE_OWNERSHIP_BY_MODULE.get(str(module_path or "").strip())


def require_module_ownership(module_path: str) -> ModuleOwnership:
    """Return a registered ownership record or raise a clear configuration error."""

    ownership = get_module_ownership(module_path)
    if ownership is None:
        raise KeyError(f"No runtime ownership registered for {module_path!r}")
    return ownership


def entrypoint_groups_by_role() -> Dict[str, List[Dict[str, object]]]:
    """Return a serializable entrypoint map grouped by CLI, web, mediator, and workflow role."""

    return {
        role: [ownership.to_dict() for ownership in RUNTIME_ENTRYPOINT_GROUPS[role]]
        for role in VALID_RUNTIME_ROLES
    }


def iter_module_ownership() -> Iterable[ModuleOwnership]:
    """Yield ownership rows in stable declaration order."""

    return iter(_OWNERSHIP_ROWS)


def module_ownership_summary() -> List[Dict[str, object]]:
    """Return a compact serializable ownership summary for tests and diagnostics."""

    return [ownership.to_dict() for ownership in _OWNERSHIP_ROWS]
