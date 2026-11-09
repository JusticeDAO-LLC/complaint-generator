from copy import deepcopy
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import ChainableUndefined, Environment, FileSystemLoader, select_autoescape
from .fastapi_compat import attach_router_routes


@dataclass(frozen=True)
class DashboardEntry:
    slug: str
    title: str
    template_name: str
    summary: str
    category: str


@dataclass(frozen=True)
class DashboardFixtures:
    complaint_links: tuple[tuple[str, str], ...]
    ipfs_entries: tuple[DashboardEntry, ...]
    ipfs_entry_map: dict[str, DashboardEntry]
    layperson_hub_advanced_dashboard_slugs: frozenset[str]
    capability_cards: tuple[dict[str, Any], ...]
    journey_detail_panels: tuple[dict[str, Any], ...]
    package_capability_matrix: tuple[dict[str, Any], ...]
    improvement_plan_items: tuple[tuple[str, str], ...]
    entry_path_cards: tuple[dict[str, Any], ...]
    dashboard_subsection_index: tuple[dict[str, Any], ...]


def _first_present(candidates: tuple[Path, ...]) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


_COMPLAINT_REPO_ROOT = Path(__file__).resolve().parent.parent
_IPFS_DATASETS_REPO = _first_present(
    (
        _COMPLAINT_REPO_ROOT / "external" / "ipfs_datasets_py",
        _COMPLAINT_REPO_ROOT / "ipfs_datasets_py",
    )
)
_IPFS_DATASETS_TEMPLATES_DIR = _IPFS_DATASETS_REPO / "ipfs_datasets_py" / "templates"
_IPFS_DATASETS_STATIC_DIR = _IPFS_DATASETS_REPO / "ipfs_datasets_py" / "static"

_COMPLAINT_DASHBOARD_LINKS = [
    ("Start", "/"),
    ("Account", "/home"),
    ("Guided questions", "/chat"),
    ("Profile", "/profile"),
    ("Results", "/results"),
    ("Saved work", "/workspace"),
    ("Proof review", "/claim-support-review"),
    ("Build draft", "/document"),
    ("Edit document", "/wysiwyg"),
    ("Draft history", "/document/optimization-trace"),
    ("All dashboards", "/dashboards"),
]

_IPFS_DASHBOARD_ENTRIES = [
    DashboardEntry("mcp", "IPFS Datasets MCP Dashboard", "mcp_dashboard.html", "Primary MCP datasets console.", "IPFS Datasets"),
    DashboardEntry("mcp-clean", "IPFS Datasets MCP Dashboard Clean", "mcp_dashboard_clean.html", "Clean MCP datasets management surface.", "IPFS Datasets"),
    DashboardEntry("mcp-final", "IPFS Datasets MCP Dashboard Final", "mcp_dashboard_final.html", "Final MCP dashboard variant.", "IPFS Datasets"),
    DashboardEntry("software-mcp", "Software Engineering Dashboard", "software_dashboard_mcp.html", "Software workflow and theorem dashboard.", "IPFS Datasets"),
    DashboardEntry("investigation", "Unified Investigation Dashboard", "unified_investigation_dashboard.html", "Investigation dashboard template.", "IPFS Datasets"),
    DashboardEntry("investigation-mcp", "Unified Investigation Dashboard MCP", "unified_investigation_dashboard_mcp.html", "Investigation dashboard with MCP integration.", "IPFS Datasets"),
    DashboardEntry("news-analysis", "News Analysis Dashboard", "news_analysis_dashboard.html", "Original news analysis dashboard.", "IPFS Datasets"),
    DashboardEntry("news-analysis-improved", "News Analysis Dashboard Improved", "news_analysis_dashboard_improved.html", "Enhanced news analysis dashboard.", "IPFS Datasets"),
    DashboardEntry("admin-index", "Admin Dashboard Home", "admin/index.html", "Administrative dashboard landing page.", "Admin Dashboards"),
    DashboardEntry("admin-login", "Admin Dashboard Login", "admin/login.html", "Administrative authentication surface.", "Admin Dashboards"),
    DashboardEntry("admin-error", "Admin Dashboard Error", "admin/error.html", "Administrative error surface.", "Admin Dashboards"),
    DashboardEntry("admin-analytics", "Analytics Dashboard", "admin/analytics_dashboard.html", "Analytics dashboard entry point.", "Admin Dashboards"),
    DashboardEntry("admin-rag-query", "RAG Query Dashboard", "admin/rag_query_dashboard.html", "RAG query dashboard entry point.", "Admin Dashboards"),
    DashboardEntry("admin-investigation", "Admin Investigation Dashboard", "admin/investigation_dashboard.html", "Administrative investigation dashboard.", "Admin Dashboards"),
    DashboardEntry("admin-caselaw", "Caselaw Dashboard", "admin/caselaw_dashboard.html", "Caselaw dashboard entry point.", "Admin Dashboards"),
    DashboardEntry("admin-caselaw-mcp", "Caselaw MCP Dashboard", "admin/caselaw_dashboard_mcp.html", "Caselaw dashboard with MCP integration.", "Admin Dashboards"),
    DashboardEntry("admin-finance-mcp", "Finance MCP Dashboard", "admin/finance_dashboard_mcp.html", "Finance dashboard with MCP integration.", "Admin Dashboards"),
    DashboardEntry("admin-finance-workflow", "Finance Workflow Dashboard", "admin/finance_workflow_dashboard.html", "Finance workflow dashboard entry point.", "Admin Dashboards"),
    DashboardEntry("admin-medicine-mcp", "Medicine MCP Dashboard", "admin/medicine_dashboard_mcp.html", "Medicine dashboard with MCP integration.", "Admin Dashboards"),
    DashboardEntry("admin-patent", "Patent Dashboard", "admin/patent_dashboard.html", "Patent dashboard entry point.", "Admin Dashboards"),
    DashboardEntry("admin-discord", "Discord Dashboard", "admin/discord_dashboard.html", "Discord workflow dashboard.", "Admin Dashboards"),
    DashboardEntry("admin-graphrag", "GraphRAG Dashboard", "admin/graphrag_dashboard.html", "GraphRAG dashboard entry point.", "Admin Dashboards"),
    DashboardEntry("admin-mcp", "Admin MCP Dashboard", "admin/mcp_dashboard.html", "Administrative MCP dashboard.", "Admin Dashboards"),
]

_LAYPERSON_HUB_ADVANCED_DASHBOARD_SLUGS = {
    "mcp",
    "software-mcp",
    "investigation",
    "admin-index",
    "admin-analytics",
    "admin-rag-query",
    "admin-investigation",
    "admin-caselaw",
    "admin-caselaw-mcp",
    "admin-finance-mcp",
    "admin-finance-workflow",
    "admin-medicine-mcp",
    "admin-patent",
    "admin-discord",
    "admin-graphrag",
    "admin-mcp",
}

_CAPABILITY_CARDS = [
    {
        "anchor": "journey-intake-chat",
        "title": "Intake Chat and Guided Advice",
        "summary": "Start with the conversational intake surface when you need help turning a narrative into claims, facts, proof leads, and next questions.",
        "primary": ("Open Intake Chat", "/chat"),
        "secondary": ("Review Claim Support", "/claim-support-review"),
        "features": [
            "Guided intake prompts",
            "Claim-support review",
            "Follow-up question queue",
            "Formal complaint handoff",
        ],
        "subsections": [
            ("Workspace snapshot", "#dashboard-workspace-snapshot"),
            ("Heads-up display", "#heads-up-display-dashboard"),
            ("Document builder", "/document"),
        ],
    },
    {
        "anchor": "journey-workspace-evidence",
        "title": "Resume a Complaint and Marshal Evidence, Law, and Caselaw",
        "summary": "Resume an existing workspace, upload files, import local/Gmail evidence, annotate dataset documents, and package evidence, legal authority, and caselaw into workspace datasets.",
        "primary": ("Open Workspace", "/workspace"),
        "secondary": ("Upload Evidence", "#chat-upload-dashboard"),
        "features": [
            "Workspace session continuity",
            "Evidence, law, and caselaw marshalling",
            "Workspace dataset parquet review",
            "MCP tool calls through the browser SDK",
        ],
        "subsections": [
            ("Workspace dataset", "#workspace-dataset-parquet-dashboard"),
            ("Law and caselaw filters", "#workspace-law-caselaw-tools"),
            ("Document annotation", "#dataset-document-annotation-dashboard"),
            ("MCP tools", "/api/complaint-workspace/mcp/tools"),
        ],
    },
    {
        "anchor": "journey-docket-dataset",
        "title": "Inspect Dockets and Existing Complaints",
        "summary": "Load packaged dockets or docket dataset parquet files, search filings, extract calendar events, and inspect graph connections.",
        "primary": ("Open Docket Dataset", "#docket-dataset-parquet-dashboard"),
        "secondary": ("Packaged Docket", "#packaged-docket-dashboard"),
        "features": [
            "Packaged docket dashboards",
            "BM25 or vector dataset search",
            "Case calendar extraction",
            "Docket knowledge graph view",
        ],
        "subsections": [
            ("Packaged docket", "#packaged-docket-dashboard"),
            ("Docket parquet", "#docket-dataset-parquet-dashboard"),
            ("Operator queue", "#heads-up-display-dashboard"),
        ],
    },
    {
        "anchor": "journey-profile",
        "title": "Profile, Identity and Personal Context",
        "summary": "Manage personal/profile context, cookies, decentralized workspace identity, and the session data used to resume work safely.",
        "primary": ("Open Profile", "/profile"),
        "secondary": ("View Cookies", "/cookies"),
        "features": [
            "Profile and cookie surfaces",
            "Decentralized workspace IDs",
            "Reusable user/session query params",
            "Cross-tab MCP sync events",
        ],
        "subsections": [
            ("Workspace session", "#dashboard-workspace-snapshot"),
            ("SDK playground", "/ipfs-datasets/sdk-playground"),
            ("MCP dashboard", "/mcp"),
        ],
    },
]

_JOURNEY_DETAIL_PANELS = [
    {
        "anchor": "intake-chat-workflow-panel",
        "eyebrow": "Intake advice path",
        "title": "From story to reviewable claim theory",
        "description": "Use the intake chat when the user needs advice, fact gathering, claim disambiguation, and a clean handoff into evidence review or drafting.",
        "steps": [
            ("Start intake", "Open the chat surface and capture the narrative, parties, timeline, harms, and remedies."),
            ("Review support", "Move into claim-support review to identify missing elements, unresolved questions, and evidence tasks."),
            ("Draft handoff", "Send supported facts and remaining caveats to the document builder when the workspace is ready."),
        ],
        "links": [
            ("Open intake chat", "/chat"),
            ("Claim-support review", "/claim-support-review"),
            ("Complaint builder", "/document"),
            ("Heads-up display", "#heads-up-display-dashboard"),
        ],
    },
    {
        "anchor": "workspace-evidence-workflow-panel",
        "eyebrow": "Workspace evidence path",
        "title": "Resume a complaint and marshal evidence, law, and caselaw",
        "description": "Use the workspace path when the user has an existing session, files, notes, mail exports, legal authority, caselaw, or dataset documents that need to become structured workspace records.",
        "steps": [
            ("Load session", "Recover the workspace by user ID and show the current intake, evidence, draft, and readiness state."),
            ("Add records", "Upload files or annotate loaded dataset documents into the complaint workspace evidence and authority record."),
            ("Filter by legal role", "Separate factual evidence, legal authority, caselaw, and claim-support records before graph or drafting handoff."),
            ("Inspect dataset", "Search workspace parquet, graph links, vector documents, logic statements, proof artifacts, and ZK certificates."),
        ],
        "links": [
            ("Workspace snapshot", "#dashboard-workspace-snapshot"),
            ("Upload evidence", "#chat-upload-dashboard"),
            ("Workspace dataset", "#workspace-dataset-parquet-dashboard"),
            ("Law and caselaw filters", "#workspace-law-caselaw-tools"),
            ("Document annotation", "#dataset-document-annotation-dashboard"),
        ],
    },
    {
        "anchor": "docket-complaint-workflow-panel",
        "eyebrow": "Docket review path",
        "title": "Inspect an existing docket or complaint dataset",
        "description": "Use the docket path when the user wants to examine filings, packaged docket manifests, search results, hearing dates, deadlines, and graph projections.",
        "steps": [
            ("Load docket", "Open a packaged docket manifest or a docket dataset parquet file."),
            ("Search filings", "Query filings, motions, deadlines, orders, hearings, or due-process events from the dataset view."),
            ("Promote findings", "Use annotation and workspace handoffs to connect useful docket facts back to the active complaint."),
        ],
        "links": [
            ("Packaged docket", "#packaged-docket-dashboard"),
            ("Docket dataset", "#docket-dataset-parquet-dashboard"),
            ("Case calendar", "#dashboard-docket-calendar-list"),
            ("Annotate document", "#dataset-document-annotation-dashboard"),
        ],
    },
    {
        "anchor": "profile-identity-workflow-panel",
        "eyebrow": "Profile and identity path",
        "title": "Manage personal context and session continuity",
        "description": "Use the profile path when the user needs profile data, cookies, decentralized workspace IDs, SDK sync context, or a stable way to resume prior work.",
        "steps": [
            ("Check profile", "Open profile and cookie surfaces to confirm the user context that follows dashboard links."),
            ("Carry context", "Use the context bar and query-param links to keep user ID, claim type, and workspace state aligned."),
            ("Use MCP tools", "Inspect MCP tools, SDK playground behavior, and legacy IPFS dashboards from the same server shell."),
        ],
        "links": [
            ("Profile", "/profile"),
            ("Cookies", "/cookies"),
            ("MCP dashboard", "/mcp"),
            ("SDK playground", "/ipfs-datasets/sdk-playground"),
        ],
    },
]

_PACKAGE_CAPABILITY_MATRIX = [
    {
        "title": "Intake and Advice",
        "description": "Conversation, claim disambiguation, follow-up questions, readiness checks, and drafting handoff.",
        "links": [
            ("Chat", "/chat"),
            ("Review", "/claim-support-review"),
            ("Build draft", "/document"),
            ("Readiness API", "/api/complaint-workspace/session"),
        ],
    },
    {
        "title": "Workspace Evidence and Authority",
        "description": "Session recovery, uploads, Gmail/DuckDB imports, evidence annotations, legal authority DB paths, and workspace parquet search.",
        "links": [
            ("Workspace", "/workspace"),
            ("Upload", "#chat-upload-dashboard"),
            ("Workspace dataset", "#workspace-dataset-parquet-dashboard"),
            ("Annotation graph", "/api/complaint-workspace/document-annotations/graph"),
        ],
    },
    {
        "title": "Law, Caselaw, and Legal Graph",
        "description": "Legal authority/caselaw review, claim-to-law matching, graph analysis gates, deontic modalities, and authority-focused drafting blockers.",
        "links": [
            ("Caselaw dashboard", "/dashboards/ipfs-datasets/admin-caselaw"),
            ("Caselaw MCP", "/dashboards/ipfs-datasets/admin-caselaw-mcp"),
            ("Legal graph filters", "#workspace-knowledge-graph-tools"),
            ("Deontic analyzer", "#workspace-deontic-logic-tools"),
        ],
    },
    {
        "title": "Dockets and Existing Complaints",
        "description": "Packaged docket manifests, docket parquet search, case-calendar extraction, graph projection, and document annotation into a complaint workspace.",
        "links": [
            ("Packaged docket", "#packaged-docket-dashboard"),
            ("Docket dataset", "#docket-dataset-parquet-dashboard"),
            ("Docket graph API", "/api/complaint-workspace/docket-dataset/graph"),
            ("Calendar preview", "#dashboard-docket-calendar-list"),
        ],
    },
    {
        "title": "Profile, Identity, and MCP Operations",
        "description": "Profile data, cookies, decentralized workspace IDs, MCP tools, JSON-RPC calls, SDK playground, and legacy IPFS dashboards.",
        "links": [
            ("Profile", "/profile"),
            ("Cookies", "/cookies"),
            ("MCP dashboard", "/mcp"),
            ("SDK playground", "/ipfs-datasets/sdk-playground"),
        ],
    },
]

_IMPROVEMENT_PLAN_ITEMS = [
    (
        "Unify entry navigation",
        "Keep the dashboard organized by user journey first, then by lower-level data surfaces: intake, workspace evidence, law/caselaw, docket review, profile, graph/logic, and legacy IPFS dashboards.",
    ),
    (
        "Promote real package capabilities",
        "Expose existing APIs for intake chat, workspace uploads, Gmail/DuckDB ingestion, legal authority database paths, parquet dataset review, graph exploration, deontic analysis, caselaw dashboards, and formal complaint generation as visible actions.",
    ),
    (
        "Tie dashboards together with context",
        "Carry user_id, manifest_path, docket dataset path, and workspace dataset path through links so users can move between chat, workspace, review, builder, and dashboard cards without losing state.",
    ),
    (
        "Make graph and logic inspectable",
        "Split connections, duties, proof artifacts, and certificate counts into clear dashboard subsections with filters already backed by the workspace dataset graph endpoint.",
    ),
    (
        "Separate evidence, law, and caselaw lanes",
        "Add source/document-type presets so users can quickly inspect factual evidence, legal authority, caselaw, claim-support records, and graph/deontic consequences from the workspace dataset.",
    ),
    (
        "Keep legacy dashboards discoverable",
        "Mount every ipfs_datasets_py dashboard in the hub, but frame them as advanced/legacy package consoles instead of making users guess which template matters for a complaint workflow.",
    ),
]


_ENTRY_PATH_CARDS = [
    {
        "anchor": "entry-path-intake",
        "stage": "Path 1",
        "title": "Start your complaint",
        "description": "Answer guided questions, describe what happened, and turn your story into a clear timeline, people involved, harms, and possible claims.",
        "primary": ("Start with guided questions", "/chat"),
        "links": [
            ("Check what still needs proof", "/claim-support-review"),
            ("See next recommended step", "#heads-up-display-dashboard"),
            ("Build a draft later", "/document"),
        ],
    },
    {
        "anchor": "entry-path-workspace",
        "stage": "Path 2",
        "title": "Continue your complaint",
        "description": "Return to a saved complaint, add documents or messages, organize evidence, add laws and court cases, and keep everything together for review.",
        "primary": ("Continue saved complaint", "#dashboard-workspace-snapshot"),
        "links": [
            ("Add evidence", "#chat-upload-dashboard"),
            ("Organize materials", "#workspace-dataset-parquet-dashboard"),
            ("Add review notes", "#dataset-document-annotation-dashboard"),
        ],
    },
    {
        "anchor": "entry-path-docket",
        "stage": "Path 3",
        "title": "Review a court docket or response",
        "description": "Look through filings, deadlines, hearing dates, orders, or an existing complaint/response and bring useful facts back into your workspace.",
        "primary": ("Review docket or filing", "#docket-dataset-parquet-dashboard"),
        "links": [
            ("Load docket package", "#packaged-docket-dashboard"),
            ("Find hearing dates", "#dashboard-docket-calendar-list"),
            ("Map docket connections", "/api/complaint-workspace/docket-dataset/graph"),
        ],
    },
    {
        "anchor": "entry-path-profile",
        "stage": "Path 4",
        "title": "Manage your profile",
        "description": "Review the personal and session information used to resume your work. Technical tools stay separate so they do not interrupt the complaint path.",
        "primary": ("Open profile", "/profile"),
        "links": [
            ("Cookies", "/cookies"),
            ("Session tools", "/mcp"),
            ("Technical tools", "#dashboard-advanced-tools"),
        ],
    },
]

_DASHBOARD_SUBSECTION_INDEX = [
    {
        "title": "Start and Review",
        "description": "Guided questions, proof checks, next recommended action, and draft handoff.",
        "links": [
            ("Start guided questions", "/chat"),
            ("Check proof gaps", "/claim-support-review"),
            ("See next step", "#heads-up-display-dashboard"),
            ("Build draft", "/document"),
        ],
    },
    {
        "title": "Evidence, Laws, and Court Cases",
        "description": "Resume a complaint, upload files, organize source materials, find connections, and check duties or conflicts.",
        "links": [
            ("Saved complaint", "#dashboard-workspace-snapshot"),
            ("Add evidence", "#chat-upload-dashboard"),
            ("Organize materials", "#workspace-dataset-parquet-dashboard"),
            ("Find connections", "#workspace-knowledge-graph-tools"),
            ("Check duties/conflicts", "#workspace-deontic-logic-tools"),
        ],
    },
    {
        "title": "Court Dockets and Responses",
        "description": "Load docket records, search filings, preview calendar events, and save useful notes.",
        "links": [
            ("Load docket package", "#packaged-docket-dashboard"),
            ("Search docket", "#docket-dataset-parquet-dashboard"),
            ("Find dates", "#dashboard-docket-calendar-list"),
            ("Add notes", "#dataset-document-annotation-dashboard"),
        ],
    },
    {
        "title": "Profile and Technical Tools",
        "description": "Profile, cookies, session tools, and optional technical package consoles.",
        "links": [
            ("Profile", "/profile"),
            ("Cookies", "/cookies"),
            ("Technical tools", "/api/complaint-workspace/mcp/tools"),
            ("Package consoles", "#legacy-ipfs-dashboard-shells"),
        ],
    },
]


def build_complaint_dashboard_links_fixture() -> tuple[tuple[str, str], ...]:
    return tuple(_COMPLAINT_DASHBOARD_LINKS)


def build_ipfs_dashboard_entries_fixture() -> tuple[DashboardEntry, ...]:
    return tuple(_IPFS_DASHBOARD_ENTRIES)


def build_layperson_dashboard_hub_fixture() -> dict[str, Any]:
    return {
        "advanced_dashboard_slugs": frozenset(
            _LAYPERSON_HUB_ADVANCED_DASHBOARD_SLUGS
        ),
        "capability_cards": tuple(deepcopy(_CAPABILITY_CARDS)),
        "journey_detail_panels": tuple(deepcopy(_JOURNEY_DETAIL_PANELS)),
        "package_capability_matrix": tuple(deepcopy(_PACKAGE_CAPABILITY_MATRIX)),
        "improvement_plan_items": tuple(_IMPROVEMENT_PLAN_ITEMS),
        "entry_path_cards": tuple(deepcopy(_ENTRY_PATH_CARDS)),
        "dashboard_subsection_index": tuple(deepcopy(_DASHBOARD_SUBSECTION_INDEX)),
    }


def build_dashboard_fixture_data() -> DashboardFixtures:
    """Return the reusable fixture catalog used by dashboard routes and tests."""
    ipfs_entries = build_ipfs_dashboard_entries_fixture()
    hub_fixture = build_layperson_dashboard_hub_fixture()
    return DashboardFixtures(
        complaint_links=build_complaint_dashboard_links_fixture(),
        ipfs_entries=ipfs_entries,
        ipfs_entry_map={entry.slug: entry for entry in ipfs_entries},
        layperson_hub_advanced_dashboard_slugs=hub_fixture[
            "advanced_dashboard_slugs"
        ],
        capability_cards=hub_fixture["capability_cards"],
        journey_detail_panels=hub_fixture["journey_detail_panels"],
        package_capability_matrix=hub_fixture["package_capability_matrix"],
        improvement_plan_items=hub_fixture["improvement_plan_items"],
        entry_path_cards=hub_fixture["entry_path_cards"],
        dashboard_subsection_index=hub_fixture["dashboard_subsection_index"],
    )


_DASHBOARD_FIXTURES = build_dashboard_fixture_data()


def get_dashboard_fixtures() -> DashboardFixtures:
    """Return the process-wide fixture catalog used by the live dashboard routes."""
    return _DASHBOARD_FIXTURES


def _resolve_dashboard_fixtures(
    fixtures: DashboardFixtures | None,
) -> DashboardFixtures:
    return fixtures if fixtures is not None else get_dashboard_fixtures()


def get_ipfs_dashboard_entry(
    slug: str,
    *,
    fixtures: DashboardFixtures | None = None,
) -> DashboardEntry | None:
    return _resolve_dashboard_fixtures(fixtures).ipfs_entry_map.get(str(slug or ""))


def get_default_ipfs_dashboard_entry(
    *,
    fixtures: DashboardFixtures | None = None,
) -> DashboardEntry:
    resolved_fixtures = _resolve_dashboard_fixtures(fixtures)
    default_entry = resolved_fixtures.ipfs_entry_map.get("mcp")
    if default_entry is not None:
        return default_entry
    if resolved_fixtures.ipfs_entries:
        return resolved_fixtures.ipfs_entries[0]
    raise ValueError("Dashboard fixtures must define at least one IPFS dashboard entry")


def _render_feature_chips(features: list[str]) -> str:
    return "".join(f'<span class="chip">{escape(feature)}</span>' for feature in features)


def _render_link_row(links: list[tuple[str, str]]) -> str:
    return "".join(
        f'<a class="jump-link" href="{escape(href)}">{escape(label)}</a>'
        for label, href in links
    )


def _render_subsection_nav(label: str, links: list[tuple[str, str]]) -> str:
    return f"""
    <nav class="dashboard-subsection-nav" aria-label="{escape(label)}">
        <span>{escape(label)}</span>
        <div class="section-jump-row">{_render_link_row(links)}</div>
    </nav>
    """


def _render_entry_path_cards(fixtures: DashboardFixtures) -> str:
    cards = []
    for item in fixtures.entry_path_cards:
        primary_label, primary_href = item["primary"]
        cards.append(
            f"""
            <article class="entry-path-card" id="{escape(item["anchor"])}">
                <div class="entry-path-stage">{escape(item["stage"])}</div>
                <h3>{escape(item["title"])}</h3>
                <p>{escape(item["description"])}</p>
                <a class="primary-action" href="{escape(primary_href)}">{escape(primary_label)}</a>
                <div class="section-jump-row">{_render_link_row(list(item["links"]))}</div>
            </article>
            """
        )
    return "\n".join(cards)


def _render_dashboard_subsection_index(fixtures: DashboardFixtures) -> str:
    cards = []
    for item in fixtures.dashboard_subsection_index:
        cards.append(
            f"""
            <article class="subsection-index-card">
                <h3>{escape(item["title"])}</h3>
                <p>{escape(item["description"])}</p>
                <div class="section-jump-row">{_render_link_row(list(item["links"]))}</div>
            </article>
            """
        )
    return "\n".join(cards)


def _render_capability_cards(fixtures: DashboardFixtures) -> str:
    cards = []
    for item in fixtures.capability_cards:
        primary_label, primary_href = item["primary"]
        secondary_label, secondary_href = item["secondary"]
        cards.append(
            f"""
            <article class="capability-card" id="{escape(item["anchor"])}">
                <div class="capability-card-body">
                    <h3>{escape(item["title"])}</h3>
                    <p>{escape(item["summary"])}</p>
                    <div class="chip-row">{_render_feature_chips(list(item["features"]))}</div>
                </div>
                <div class="capability-actions">
                    <a class="primary-action" href="{escape(primary_href)}">{escape(primary_label)}</a>
                    <a class="secondary-action" href="{escape(secondary_href)}">{escape(secondary_label)}</a>
                </div>
                <div class="section-jump-row">{_render_link_row(list(item["subsections"]))}</div>
            </article>
            """
        )
    return "\n".join(cards)


def _render_improvement_plan(fixtures: DashboardFixtures) -> str:
    return "".join(
        f"""
        <li>
            <strong>{escape(title)}</strong>
            <span>{escape(description)}</span>
        </li>
        """
        for title, description in fixtures.improvement_plan_items
    )


def _render_journey_detail_panels(fixtures: DashboardFixtures) -> str:
    panels = []
    for panel in fixtures.journey_detail_panels:
        steps = "".join(
            f"""
            <li>
                <strong>{escape(title)}</strong>
                <span>{escape(description)}</span>
            </li>
            """
            for title, description in panel["steps"]
        )
        panels.append(
            f"""
            <article class="journey-detail-card" id="{escape(panel["anchor"])}">
                <div>
                    <div class="eyebrow" style="color: var(--accent);">{escape(panel["eyebrow"])}</div>
                    <h3>{escape(panel["title"])}</h3>
                    <p>{escape(panel["description"])}</p>
                </div>
                <ol>{steps}</ol>
                <div class="section-jump-row">{_render_link_row(list(panel["links"]))}</div>
            </article>
            """
        )
    return "\n".join(panels)


def _render_package_capability_matrix(fixtures: DashboardFixtures) -> str:
    cards = []
    for item in fixtures.package_capability_matrix:
        cards.append(
            f"""
            <article class="package-map-card">
                <h3>{escape(item["title"])}</h3>
                <p>{escape(item["description"])}</p>
                <div class="section-jump-row">{_render_link_row(list(item["links"]))}</div>
            </article>
            """
        )
    return "\n".join(cards)


def _render_dashboard_section_nav() -> str:
    return _render_link_row(
        [
            ("Start", "#dashboard-start-here"),
            ("Add evidence", "#chat-upload-dashboard"),
            ("Organize materials", "#workspace-dataset-parquet-dashboard"),
            ("Review proof", "/claim-support-review"),
            ("Build draft", "/document"),
            ("More tools", "#dashboard-subsection-index"),
            ("Saved complaint", "#dashboard-workspace-snapshot"),
            ("Review docket", "#docket-dataset-parquet-dashboard"),
            ("Find connections", "#workspace-knowledge-graph-tools"),
            ("Check duties", "#workspace-deontic-logic-tools"),
            ("Notes", "#dataset-document-annotation-dashboard"),
            ("Profile", "#profile-and-identity-dashboard"),
            ("Technical tools", "#dashboard-advanced-tools"),
        ]
    )


class _DashboardUndefined(ChainableUndefined):
    def __call__(self, *args: Any, **kwargs: Any) -> "_DashboardUndefined":
        return self

    def __iter__(self):
        return iter(())

    def __len__(self) -> int:
        return 0

    def items(self):
        return ()

    def keys(self):
        return ()

    def values(self):
        return ()


class _DashboardMetrics:
    def __init__(self) -> None:
        self.total_websites_processed = 27
        self.success_rate = 96.4
        self.total_rag_queries = 43
        self.average_query_time = 1.28
        self._custom_metrics = {
            "pipeline_runs": [
                {
                    "type": "counter",
                    "value": 14,
                    "labels": {"surface": "complaint-generator"},
                    "timestamp": "2026-03-22T12:00:00+00:00",
                }
            ]
        }

    def items(self):
        return self._custom_metrics.items()

    def keys(self):
        return self._custom_metrics.keys()

    def values(self):
        return self._custom_metrics.values()


_IPFS_DASHBOARD_ENV = Environment(
    loader=FileSystemLoader(str(_IPFS_DATASETS_TEMPLATES_DIR)),
    autoescape=select_autoescape(("html", "xml")),
    undefined=_DashboardUndefined,
)


def _static_url_for(endpoint: str, filename: str = "", **_: Any) -> str:
    if endpoint != "static":
        return "#"
    normalized_filename = str(filename or "").lstrip("/")
    return f"/ipfs-datasets-static/{quote(normalized_filename)}"


_IPFS_DASHBOARD_ENV.globals["url_for"] = _static_url_for


def _build_ipfs_dashboard_context(entry: DashboardEntry) -> dict[str, Any]:
    return {
        "title": entry.title,
        "dashboard_title": entry.title,
        "refresh_interval": 60,
        "last_updated": "2026-03-22T12:00:00+00:00",
        "uptime": "2 days, 4 hours",
        "base_url": "/api/ipfs-datasets",
        "api_key": "",
        "user_type": "general",
        "default_start_date": "2026-01-01",
        "default_end_date": "2026-03-22",
        "node_info": {
            "hostname": "complaint-generator-local",
            "platform": "linux",
            "python_version": "3.11",
            "ipfs_datasets_version": "preview",
            "start_time": "2026-03-20T08:00:00+00:00",
        },
        "system_stats": {
            "cpu_percent": 18,
            "memory_used": "1.2 GB",
            "memory_total": "8.0 GB",
            "memory_percent": 15,
            "disk_used": "12 GB",
            "disk_total": "128 GB",
            "disk_percent": 9,
        },
        "metrics": _DashboardMetrics(),
        "logs": [
            {
                "timestamp": "2026-03-22T12:00:00+00:00",
                "level": "INFO",
                "name": "dashboard_ui",
                "message": "Compatibility dashboard preview mounted successfully.",
            }
        ],
        "nodes": [
            {
                "id": "local-node",
                "status": "online",
                "address": "127.0.0.1",
                "last_seen": "2026-03-22T12:00:00+00:00",
            }
        ],
        "operations": [
            {
                "operation_id": "preview-1",
                "operation_type": "dashboard-preview",
                "status": "success",
                "start_time": "2026-03-22T12:00:00+00:00",
                "duration_ms": 12.5,
            }
        ],
        "dashboard_config": {
            "mode": "compatibility-preview",
            "template": entry.template_name,
            "slug": entry.slug,
        },
        "monitoring_config": {
            "refresh_interval_seconds": 60,
            "alerts_enabled": False,
        },
        "stats": {
            "articles_processed": 12,
            "articles_today": 2,
            "entities_extracted": 48,
            "entity_types": 6,
            "active_workflows": 3,
            "completed_workflows": 9,
            "sources_analyzed": 5,
            "reliability_avg": 92,
            "documents_processed": 16,
            "documents_today": 3,
            "relationships_mapped": 21,
            "strong_relationships": 7,
        },
        "system_status": {
            "system_ready": True,
            "last_updated": "2026-03-22T12:00:00+00:00",
            "available_tools": ["create_dataset", "search_graph", "run_dashboard_query"],
            "theorem_count": 3,
            "domains": ["legal", "news", "software"],
            "jurisdictions": ["federal", "state"],
        },
        "processing_stats": {
            "total_sessions": 4,
            "active_sessions": 1,
            "success_rate": 100.0,
            "average_processing_time": 1.2,
        },
    }


def _render_ipfs_dashboard(entry: DashboardEntry) -> str:
    try:
        template = _IPFS_DASHBOARD_ENV.get_template(entry.template_name)
        return template.render(**_build_ipfs_dashboard_context(entry))
    except Exception as exc:
        return f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
    <title>{escape(entry.title)} | Dashboard Preview</title>
    <style>
        body {{ font-family: 'Public Sans', Arial, sans-serif; margin: 0; background: #f7f7f4; color: #122033; }}
        main {{ max-width: 960px; margin: 0 auto; padding: 32px 24px 48px; }}
        h1 {{ margin-top: 0; }}
        pre {{ white-space: pre-wrap; overflow-wrap: anywhere; background: #f3f5f7; padding: 16px; border-radius: 12px; }}
        a {{ color: #0a4f66; font-weight: 600; }}
    </style>
</head>
<body>
    <main>
        <section>
            <h1>{escape(entry.title)}</h1>
            <p>{escape(entry.summary)}</p>
            <p>The optional ipfs_datasets dashboard template <code>{escape(entry.template_name)}</code> is not installed in this checkout, so the complaint-generator dashboard hub is serving a stable fallback page.</p>
            <p><a href=\"/dashboards\">Back to dashboard hub</a></p>
            <pre>{escape(str(exc))}</pre>
        </section>
    </main>
</body>
</html>
"""


def _render_shell_page(
    entry: DashboardEntry,
    fixtures: DashboardFixtures | None = None,
) -> str:
    fixtures = _resolve_dashboard_fixtures(fixtures)
    shell_links = "".join(
        f'<a class="shell-link{' is-active' if item.slug == entry.slug else ''}" href="/dashboards/ipfs-datasets/{escape(item.slug)}">{escape(item.title)}</a>'
        for item in fixtures.ipfs_entries
    )
    top_links = "".join(
        f'<a class="surface-link" href="{escape(path)}">{escape(label)}</a>'
        for label, path in fixtures.complaint_links
    )
    iframe_src = f"/dashboards/raw/ipfs-datasets/{quote(entry.slug)}"
    raw_src = iframe_src
    return f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
    <title>{escape(entry.title)} | Complaint Generator Dashboard Shell</title>
    <style>
        body {{ font-family: 'Public Sans', Arial, sans-serif; margin: 0; background: #f6f4ef; color: #122033; }}
        header {{ background: linear-gradient(135deg, #14324a, #204f6d); color: white; padding: 18px 24px; }}
        .surface-nav, .shell-nav {{ display: flex; flex-wrap: wrap; gap: 10px; }}
        .surface-nav {{ margin-top: 12px; }}
        .surface-link, .shell-link {{ text-decoration: none; border-radius: 999px; padding: 8px 14px; font-size: 14px; }}
        .surface-link {{ background: rgba(255,255,255,0.14); color: white; }}
        .shell-link {{ background: white; color: #14324a; border: 1px solid #c9d4df; }}
        .shell-link.is-active {{ background: #14324a; color: white; border-color: #14324a; }}
        main {{ display: grid; gap: 18px; padding: 20px 24px 28px; }}
        .shell-card {{ background: white; border-radius: 18px; padding: 18px; box-shadow: 0 12px 32px rgba(17, 34, 51, 0.08); }}
        .shell-card h1 {{ margin: 0 0 10px; font-size: 28px; }}
        .shell-card p {{ margin: 0; color: #425466; }}
        iframe {{ width: 100%; min-height: 1200px; border: 0; border-radius: 18px; background: white; box-shadow: 0 12px 32px rgba(17, 34, 51, 0.08); }}
        .raw-link {{ color: #14324a; font-weight: 600; }}
    </style>
</head>
<body>
    <header>
        <div><strong>Complaint Generator Unified Dashboards</strong></div>
        <div class=\"surface-nav\">{top_links}</div>
    </header>
    <main>
        <section class=\"shell-card\">
            <h1>{escape(entry.title)}</h1>
            <p>{escape(entry.summary)} This shell keeps the dashboard inside the complaint-generator site while sourcing the underlying HTML from ipfs_datasets_py.</p>
            <p style=\"margin-top: 10px;\"><a class=\"raw-link\" href=\"{escape(raw_src)}\" target=\"_blank\" rel=\"noopener\">Open raw dashboard</a></p>
        </section>
        <section class=\"shell-card\">
            <div class=\"shell-nav\">{shell_links}</div>
        </section>
        <iframe src=\"{escape(iframe_src)}\" title=\"{escape(entry.title)}\"></iframe>
    </main>
</body>
</html>
"""


def _render_dashboard_hub(
    *,
    default_user_id: str = "",
    default_manifest_path: str = "",
    default_docket_dataset_path: str = "",
    default_workspace_dataset_path: str = "",
    fixtures: DashboardFixtures | None = None,
) -> str:
    fixtures = _resolve_dashboard_fixtures(fixtures)
    complaint_links = "".join(
        f'<li><a href="{escape(path)}">{escape(label)}</a></li>'
        for label, path in fixtures.complaint_links
    )
    ipfs_sections: dict[str, list[DashboardEntry]] = {}
    for entry in fixtures.ipfs_entries:
        if entry.slug not in fixtures.layperson_hub_advanced_dashboard_slugs:
            continue
        ipfs_sections.setdefault(entry.category, []).append(entry)
    ipfs_markup = "".join(
        f"<section><h2>{escape(category)}</h2><ul>" + "".join(
            f'<li><a href="/dashboards/ipfs-datasets/{escape(entry.slug)}">{escape(entry.title)}</a> <span>{escape(entry.summary)}</span></li>'
            for entry in entries
        ) + "</ul></section>"
        for category, entries in ipfs_sections.items()
    )
    capability_cards = _render_capability_cards(fixtures)
    journey_detail_panels = _render_journey_detail_panels(fixtures)
    package_capability_matrix = _render_package_capability_matrix(fixtures)
    dashboard_section_nav = _render_dashboard_section_nav()
    improvement_plan = _render_improvement_plan(fixtures)
    entry_path_cards = _render_entry_path_cards(fixtures)
    dashboard_subsection_index = _render_dashboard_subsection_index(fixtures)
    docket_input_type = "single"
    normalized_docket_path = str(default_docket_dataset_path or "").strip().lower()
    if normalized_docket_path.endswith(".json") or "manifest" in normalized_docket_path:
        docket_input_type = "packaged" if "manifest" in normalized_docket_path else "json"
    return f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
    <title>Unified Dashboard Hub</title>
    <style>
        :root {{
            --bg: #f6f1e8;
            --surface: rgba(255, 252, 247, 0.96);
            --surface-strong: #fffdfa;
            --ink: #152230;
            --muted: #596978;
            --line: rgba(21, 34, 48, 0.12);
            --accent: #115c63;
            --accent-strong: #0c4247;
            --warm: #aa4d1d;
            --good: #1d6b4b;
            --shadow: 0 18px 40px rgba(21, 34, 48, 0.08);
            --radius-xl: 28px;
            --radius-lg: 20px;
            --radius-md: 16px;
        }}
        * {{ box-sizing: border-box; }}
        body {{ margin: 0; font-family: 'Public Sans', Arial, sans-serif; background: radial-gradient(circle at top left, rgba(17, 92, 99, 0.10), transparent 26%), linear-gradient(180deg, #fbf7f0, var(--bg)); color: var(--ink); }}
        header {{ padding: 32px; background: linear-gradient(135deg, #163a51, #1f6d68); color: white; }}
        main {{ padding: 28px 32px 44px; display: grid; gap: 24px; }}
        .grid {{ display: grid; gap: 24px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }}
        .card {{ background: var(--surface); border-radius: var(--radius-lg); padding: 22px; box-shadow: var(--shadow); border: 1px solid var(--line); }}
        h1, h2 {{ margin-top: 0; }}
        p, span, label {{ color: var(--muted); }}
        ul {{ margin: 0; padding-left: 18px; }}
        li {{ margin: 10px 0; }}
        a {{ color: #0a4f66; font-weight: 600; }}
        span {{ display: block; margin-top: 4px; }}
        .hero-grid {{ display: grid; gap: 24px; grid-template-columns: minmax(0, 1.3fr) minmax(320px, 0.7fr); }}
        .hero-card {{ background: linear-gradient(160deg, rgba(255, 252, 247, 0.95), rgba(247, 241, 232, 0.98)); border-radius: var(--radius-xl); padding: 28px; box-shadow: var(--shadow); border: 1px solid rgba(21, 34, 48, 0.08); }}
        .eyebrow {{ text-transform: uppercase; letter-spacing: 0.16em; font-size: 0.75rem; color: #d5f3ef; font-weight: 800; }}
        .header-copy p {{ color: rgba(255,255,255,0.84); max-width: 72ch; }}
        .surface-pills, .button-row, .stat-grid, .chip-row, .section-jump-row, .journey-nav, .decision-row, .context-actions, .preset-row, .stage-rail, .lane-grid, .mobile-action-rail {{ display: flex; flex-wrap: wrap; gap: 10px; }}
        .surface-pills a, button, .modal-link, .jump-link, .primary-action, .secondary-action, .mobile-action-rail a {{
            border: 0;
            border-radius: 999px;
            padding: 11px 16px;
            text-decoration: none;
            font-weight: 700;
        }}
        .surface-pills a {{ background: rgba(255,255,255,0.12); color: white; }}
        button {{ background: linear-gradient(135deg, var(--accent), var(--accent-strong)); color: white; cursor: pointer; }}
        button.secondary {{ background: rgba(17, 92, 99, 0.10); color: var(--accent-strong); border: 1px solid rgba(17, 92, 99, 0.16); }}
        button:disabled {{ opacity: 0.58; cursor: not-allowed; }}
        .is-disabled {{
            opacity: 0.58;
            cursor: not-allowed;
            pointer-events: none;
            filter: saturate(0.75);
        }}
        .dashboard-section-menu > summary {{
            display: none;
            cursor: pointer;
            font-weight: 800;
            color: var(--accent-strong);
            border: 1px solid var(--line);
            border-radius: var(--radius-md);
            padding: 12px 14px;
            background: rgba(251, 247, 240, 0.96);
            min-height: 48px;
        }}
        .journey-nav {{
            position: sticky;
            top: 0;
            z-index: 20;
            background: rgba(251, 247, 240, 0.94);
            backdrop-filter: blur(14px);
            border: 1px solid var(--line);
            border-radius: var(--radius-lg);
            padding: 12px;
            box-shadow: 0 10px 28px rgba(21, 34, 48, 0.06);
        }}
        .jump-link {{ background: rgba(17, 92, 99, 0.08); color: var(--accent-strong); border: 1px solid rgba(17, 92, 99, 0.12); }}
        .workflow-rail {{
            background: #ffffff;
            border-radius: var(--radius-xl);
            padding: 20px;
            box-shadow: var(--shadow);
            border: 1px solid rgba(17, 92, 99, 0.16);
        }}
        .workflow-rail-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 16px;
            flex-wrap: wrap;
        }}
        .workflow-rail h2 {{ margin-bottom: 6px; }}
        .stage-rail {{ margin-top: 16px; align-items: stretch; }}
        .stage-card {{
            position: relative;
            flex: 1 1 190px;
            min-width: 170px;
            border-radius: var(--radius-md);
            border: 1px solid rgba(21, 34, 48, 0.10);
            background: rgba(17, 92, 99, 0.045);
            padding: 14px;
        }}
        .stage-card.is-current {{ border-color: rgba(17, 92, 99, 0.42); background: rgba(17, 92, 99, 0.10); }}
        .stage-card[data-state="complete"] {{ border-color: rgba(29, 107, 75, 0.30); background: rgba(29, 107, 75, 0.08); }}
        .stage-card[data-state="blocked"] {{ border-color: rgba(170, 77, 29, 0.34); background: rgba(170, 77, 29, 0.08); }}
        .stage-card[data-state="ready"] {{ border-color: rgba(17, 92, 99, 0.30); }}
	        .stage-card strong {{ display: block; color: var(--ink); }}
	        .stage-card span {{ font-size: 0.9rem; }}
	        .stage-unlock {{
	            display: inline-flex;
	            margin-top: 8px;
	            color: var(--accent-strong);
	            font-size: 0.86rem;
	            font-weight: 900;
	            text-decoration: none;
	        }}
        .stage-state-badge {{
            position: absolute;
            top: 12px;
            right: 12px;
            border-radius: 999px;
            padding: 4px 8px;
            background: rgba(21, 34, 48, 0.07);
            color: var(--ink);
            font-size: 0.72rem;
            font-weight: 900;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }}
        .stage-card[data-state="current"] .stage-state-badge {{ background: rgba(17, 92, 99, 0.16); color: var(--accent-strong); }}
        .stage-card[data-state="complete"] .stage-state-badge {{ background: rgba(29, 107, 75, 0.14); color: var(--good); }}
        .stage-card[data-state="blocked"] .stage-state-badge {{ background: rgba(170, 77, 29, 0.14); color: var(--warm); }}
        .stage-number {{
            width: 28px;
            height: 28px;
            display: inline-grid;
            place-items: center;
            border-radius: 50%;
            background: var(--accent);
            color: white;
            font-weight: 800;
            margin-bottom: 10px;
        }}
        .stage-actions {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; }}
        .mobile-action-rail {{
            display: none;
            position: sticky;
            bottom: 12px;
            z-index: 25;
            background: rgba(255, 253, 250, 0.97);
            border: 1px solid rgba(17, 92, 99, 0.18);
            border-radius: var(--radius-lg);
            padding: 10px;
            box-shadow: 0 16px 38px rgba(21, 34, 48, 0.14);
        }}
        .mobile-action-rail a {{ flex: 1 1 140px; text-align: center; }}
        .start-here {{
            background: var(--surface);
            border-radius: var(--radius-xl);
            padding: 22px;
            box-shadow: var(--shadow);
            border: 1px solid var(--line);
        }}
        .start-here h2, .workspace-context-bar h2 {{ margin-bottom: 8px; }}
	        .decision-row {{ margin-top: 14px; }}
	        .recommended-action-panel {{
	            display: grid;
	            gap: 10px;
	            margin-top: 14px;
	            padding: 16px;
	            border-radius: var(--radius-lg);
	            background: #ffffff;
	            border: 1px solid rgba(17, 92, 99, 0.16);
	            box-shadow: 0 10px 26px rgba(21, 34, 48, 0.055);
	        }}
	        .recommended-action-panel h3 {{ margin: 0; font-size: 1.05rem; }}
	        .recommended-action-panel p {{ margin: 0; }}
	        .recommended-action-actions {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }}
	        .secondary-decision-row {{
	            display: flex;
	            flex-wrap: wrap;
	            gap: 10px;
	            margin-top: 12px;
	        }}
        .decision-link {{
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 11px 16px;
            background: rgba(21, 34, 48, 0.08);
            color: var(--ink);
            font-weight: 800;
            text-decoration: none;
            border: 1px solid rgba(21, 34, 48, 0.10);
        }}
        .decision-link.primary {{ background: linear-gradient(135deg, var(--accent), var(--accent-strong)); color: white; }}
        .workspace-context-bar {{
            display: grid;
            gap: 16px;
            grid-template-columns: minmax(0, 1fr) auto;
            align-items: center;
            position: sticky;
            top: 74px;
            z-index: 18;
            background: #ffffff;
            border-radius: var(--radius-lg);
            padding: 18px 20px;
            box-shadow: 0 14px 34px rgba(21, 34, 48, 0.07);
            border: 1px solid rgba(17, 92, 99, 0.16);
        }}
        .current-work-bar {{
            display: grid;
            gap: 14px;
            grid-template-columns: minmax(0, 1fr) auto;
            align-items: center;
            margin-bottom: 14px;
            padding: 16px 18px;
            border-radius: var(--radius-lg);
            background: linear-gradient(135deg, rgba(17, 92, 99, 0.11), rgba(255, 253, 250, 0.96));
            border: 2px solid rgba(17, 92, 99, 0.20);
        }}
        .current-work-main {{
            display: grid;
            gap: 8px;
        }}
        .current-work-title-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px 12px;
            align-items: center;
        }}
        .current-work-title-row h2 {{
            margin: 0;
            font-size: 1.28rem;
        }}
        .current-work-stage {{
            display: inline-flex;
            width: fit-content;
            border-radius: 999px;
            padding: 6px 10px;
            background: rgba(17, 92, 99, 0.14);
            color: var(--accent-strong);
            font-size: 0.76rem;
            font-weight: 900;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }}
        .current-work-detail {{
            margin: 0;
            color: var(--muted);
            line-height: 1.45;
        }}
        .current-work-status-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }}
        .context-status-pill {{
            display: inline-flex;
            align-items: center;
            min-height: 30px;
            border-radius: 999px;
            padding: 5px 10px;
            background: rgba(21, 34, 48, 0.07);
            color: var(--ink);
            font-size: 0.82rem;
            font-weight: 800;
        }}
        .context-status-pill.is-ready {{
            background: rgba(29, 107, 75, 0.12);
            color: var(--good);
        }}
        .context-status-pill.is-warning {{
            background: rgba(170, 77, 29, 0.12);
            color: var(--warm);
        }}
        .current-work-actions {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            justify-content: flex-end;
        }}
        .context-action-hint {{
            display: inline-flex;
            align-items: center;
            margin-top: 8px;
            font-size: 0.86rem;
            font-weight: 800;
            color: var(--accent-strong);
        }}
        .context-grid {{
            display: grid;
            gap: 10px;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            margin-top: 12px;
        }}
        .context-metric {{
            border-left: 3px solid rgba(17, 92, 99, 0.35);
            padding-left: 10px;
        }}
        .context-metric.is-active {{
            border-left-color: var(--accent);
            background: rgba(17, 92, 99, 0.055);
            border-radius: 12px;
            padding: 10px 12px;
        }}
        .context-metric.is-warning {{
            border-left-color: var(--warm);
            background: rgba(170, 77, 29, 0.065);
            border-radius: 12px;
            padding: 10px 12px;
        }}
        .context-metric span {{
            color: var(--muted);
            font-size: 0.78rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }}
        .context-metric strong {{
            display: block;
            color: var(--ink);
            margin-top: 4px;
        }}
        .legal-safety-note {{
            display: grid;
            gap: 6px;
            margin-top: 12px;
            padding: 12px 14px;
            border-radius: var(--radius-md);
            border: 1px solid rgba(170, 77, 29, 0.20);
            background: rgba(170, 77, 29, 0.08);
            color: var(--ink);
        }}
        .legal-safety-note strong {{ color: var(--warm); }}
        .entry-overview {{
            display: grid;
            gap: 18px;
            grid-template-columns: minmax(0, 0.95fr) minmax(320px, 1.05fr);
            align-items: stretch;
        }}
        .entry-overview-panel, .subsection-index {{
            background: var(--surface);
            border-radius: var(--radius-xl);
            padding: 24px;
            box-shadow: var(--shadow);
            border: 1px solid var(--line);
        }}
        .entry-path-grid {{ display: grid; gap: 14px; grid-template-columns: repeat(2, minmax(240px, 1fr)); }}
        .subsection-index-grid {{ display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }}
        .entry-path-card, .subsection-index-card {{
            display: grid;
            gap: 10px;
            align-content: start;
            background: #ffffff;
            border-radius: var(--radius-lg);
            border: 1px solid rgba(21, 34, 48, 0.10);
            padding: 18px;
        }}
        .entry-path-card h3, .subsection-index-card h3 {{ margin: 0; font-size: 1.05rem; }}
        .entry-path-card p, .subsection-index-card p {{ margin: 0; }}
        .entry-path-stage {{
            color: var(--accent-strong);
            font-size: 0.76rem;
            font-weight: 900;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }}
        .dashboard-subsection-nav {{
            margin: 12px 0;
            padding: 12px;
            border-radius: var(--radius-md);
            background: rgba(17, 92, 99, 0.055);
            border: 1px solid rgba(17, 92, 99, 0.10);
        }}
        .dashboard-subsection-nav > span {{
            display: block;
            margin: 0 0 8px;
            color: var(--accent-strong);
            font-size: 0.78rem;
            font-weight: 900;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }}
        .advanced-tools {{
            background: var(--surface);
            border-radius: var(--radius-xl);
            padding: 22px;
            box-shadow: var(--shadow);
            border: 1px solid var(--line);
        }}
        .advanced-tools > summary, .secondary-dashboard-details > summary {{
            cursor: pointer;
            color: var(--ink);
            font-size: 1.2rem;
            font-weight: 900;
        }}
        .secondary-dashboard-details {{
            background: var(--surface);
            border-radius: var(--radius-xl);
            padding: 22px;
            box-shadow: var(--shadow);
            border: 1px solid var(--line);
        }}
        .secondary-dashboard-details > summary {{
            list-style-position: inside;
        }}
        .secondary-dashboard-details .card {{
            margin-top: 16px;
            box-shadow: none;
            border-radius: var(--radius-lg);
        }}
        .advanced-tools-helper {{ margin: 10px 0 0; color: var(--muted); }}
        .advanced-tools-grid {{ display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); margin-top: 16px; }}
        .capability-grid {{ display: grid; gap: 18px; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }}
        .capability-card {{
            display: grid;
            gap: 16px;
            align-content: space-between;
            background: var(--surface);
            border-radius: var(--radius-xl);
            padding: 24px;
            box-shadow: var(--shadow);
            border: 1px solid var(--line);
        }}
        .capability-card h3 {{ margin: 0; font-size: 1.35rem; }}
        .capability-card p {{ margin: 8px 0 0; }}
        .capability-actions {{ display: flex; flex-wrap: wrap; gap: 10px; }}
        .primary-action {{ background: linear-gradient(135deg, var(--accent), var(--accent-strong)); color: white; }}
        .secondary-action {{ background: rgba(17, 92, 99, 0.10); color: var(--accent-strong); border: 1px solid rgba(17, 92, 99, 0.16); }}
        .journey-detail-grid {{ display: grid; gap: 18px; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }}
        .journey-detail-card {{
            display: grid;
            gap: 16px;
            background: var(--surface-strong);
            border-radius: var(--radius-lg);
            padding: 22px;
            box-shadow: var(--shadow);
            border: 1px solid var(--line);
        }}
        .journey-detail-card h3 {{ margin: 0; font-size: 1.2rem; }}
        .journey-detail-card ol {{ margin: 0; padding-left: 20px; }}
        .journey-detail-card li {{ padding-left: 4px; }}
        .journey-detail-card strong {{ display: block; color: var(--ink); }}
        .package-map-grid {{ display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }}
        .package-map-card {{
            background: #ffffff;
            border: 1px solid rgba(21, 34, 48, 0.10);
            border-radius: var(--radius-lg);
            padding: 20px;
            box-shadow: 0 10px 28px rgba(21, 34, 48, 0.055);
        }}
        .package-map-card h3 {{ margin: 0; font-size: 1.05rem; }}
        .package-map-card p {{ margin: 8px 0 14px; }}
        .capability-plan ul {{ padding-left: 20px; }}
        .capability-plan li {{ margin: 14px 0; }}
        .capability-plan strong {{ display: block; color: var(--ink); }}
        .workspace-cards {{ display: grid; gap: 24px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }}
        .dashboard-card {{ background: var(--surface); border-radius: var(--radius-xl); padding: 24px; box-shadow: var(--shadow); border: 1px solid var(--line); }}
        #workspace-dataset-parquet-dashboard {{ grid-column: 1 / -1; }}
        .dashboard-card h2 {{ margin-bottom: 10px; }}
        .dashboard-card:target, .capability-card:target, .journey-detail-card:target, #workspace-law-caselaw-tools:target, #workspace-knowledge-graph-tools:target, #workspace-deontic-logic-tools:target {{ outline: 3px solid rgba(17, 92, 99, 0.28); outline-offset: 4px; }}
        [id] {{ scroll-margin-top: 120px; }}
        .field-label {{ display: block; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 800; color: var(--muted); margin-bottom: 8px; }}
        .field-row {{ display: grid; gap: 12px; grid-template-columns: minmax(0, 1fr) auto; align-items: end; }}
	        input[type="text"], select, textarea, input[type="file"] {{
            width: 100%;
            border-radius: 16px;
            border: 1px solid rgba(21, 34, 48, 0.14);
            background: var(--surface-strong);
            padding: 13px 15px;
            color: var(--ink);
            font: inherit;
        }}
        textarea {{ min-height: 116px; resize: vertical; }}
        .stat-grid {{ margin-top: 16px; }}
        .stat-card {{
            flex: 1 1 120px;
            min-width: 120px;
            border-radius: var(--radius-md);
            padding: 14px 16px;
            background: rgba(17, 92, 99, 0.06);
            border: 1px solid rgba(17, 92, 99, 0.10);
        }}
        .stat-card strong {{ display: block; color: var(--ink); font-size: 1.2rem; }}
        .stat-card span {{ margin-top: 6px; }}
        .chip {{
            display: inline-flex;
            align-items: center;
            padding: 7px 11px;
            border-radius: 999px;
            background: rgba(21, 34, 48, 0.06);
            color: var(--ink);
            font-size: 0.86rem;
            font-weight: 700;
        }}
        .chip.good {{ background: rgba(29, 107, 75, 0.12); color: var(--good); }}
        .chip.warm {{ background: rgba(170, 77, 29, 0.12); color: var(--warm); }}
        .status-line {{
            min-height: 24px;
            margin-top: 14px;
            font-size: 0.95rem;
            font-weight: 700;
            color: var(--accent-strong);
        }}
        .preset-row {{ margin-top: 12px; }}
        .preset-button {{
            background: rgba(170, 77, 29, 0.10);
            color: #763612;
            border: 1px solid rgba(170, 77, 29, 0.18);
        }}
        .lane-grid {{ margin-top: 16px; }}
        .lane-card {{
            flex: 1 1 220px;
            min-width: 210px;
            border-radius: var(--radius-md);
            background: #ffffff;
            border: 1px solid rgba(21, 34, 48, 0.10);
            padding: 16px;
            cursor: pointer;
            transition: border-color 160ms ease, background 160ms ease, transform 160ms ease;
        }}
        .lane-card:hover, .lane-card:focus-visible {{
            border-color: rgba(17, 92, 99, 0.34);
            outline: none;
            transform: translateY(-1px);
        }}
        .lane-card strong {{ display: block; color: var(--ink); }}
        .lane-card p {{ margin: 8px 0 12px; }}
        .lane-status {{
            display: inline-flex;
            align-items: center;
            min-height: 28px;
            border-radius: 999px;
            padding: 5px 10px;
            background: rgba(21, 34, 48, 0.06);
            color: var(--ink);
            font-size: 0.8rem;
            font-weight: 800;
        }}
        .lane-card.is-selected {{
            border-color: rgba(17, 92, 99, 0.48);
            background: rgba(17, 92, 99, 0.08);
            box-shadow: inset 0 0 0 2px rgba(17, 92, 99, 0.10);
        }}
        .lane-card.is-selected .lane-status {{ background: rgba(17, 92, 99, 0.16); color: var(--accent-strong); }}
        .lane-summary {{
            margin-top: 12px;
            padding: 12px 14px;
            border-radius: var(--radius-md);
            background: rgba(17, 92, 99, 0.06);
            border: 1px solid rgba(17, 92, 99, 0.10);
            color: var(--accent-strong);
            font-weight: 800;
        }}
        .workspace-flow-status {{
            display: grid;
            gap: 10px;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            margin-top: 14px;
            padding: 14px;
            border-radius: var(--radius-lg);
            background: rgba(17, 92, 99, 0.055);
            border: 1px solid rgba(17, 92, 99, 0.14);
        }}
        .workspace-flow-status div {{
            border-left: 3px solid rgba(17, 92, 99, 0.32);
            padding-left: 10px;
        }}
        .workspace-flow-status span {{
            color: var(--muted);
            font-size: 0.76rem;
            font-weight: 900;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }}
        .workspace-flow-status strong {{
            display: block;
            color: var(--ink);
            margin-top: 4px;
        }}
        .workspace-empty-state {{
            margin-top: 14px;
            padding: 18px;
            border-radius: var(--radius-lg);
            background: #ffffff;
            border: 1px solid rgba(17, 92, 99, 0.14);
            box-shadow: 0 12px 28px rgba(21, 34, 48, 0.055);
        }}
	        .workspace-empty-state h3 {{ margin: 0 0 8px; }}
	        .workspace-empty-state p {{ margin: 0 0 12px; }}
	        .workspace-next-action-panel {{
	            display: grid;
	            gap: 10px;
	            margin-top: 14px;
	            padding: 16px;
	            border-radius: var(--radius-lg);
	            background: #ffffff;
	            border: 1px solid rgba(17, 92, 99, 0.16);
	            box-shadow: 0 10px 26px rgba(21, 34, 48, 0.055);
	        }}
	        input:disabled, select:disabled, textarea:disabled {{
	            opacity: 0.62;
	            cursor: not-allowed;
	            background: rgba(21, 34, 48, 0.045);
	        }}
	        .workspace-next-action-panel h3 {{ margin: 0; font-size: 1.05rem; }}
	        .workspace-next-action-panel p {{ margin: 0; }}
	        .workspace-path-status {{
	            display: grid;
	            gap: 8px;
	            margin-top: 12px;
	            padding: 12px 14px;
	            border-radius: var(--radius-md);
	            background: rgba(21, 34, 48, 0.045);
	            border: 1px solid rgba(21, 34, 48, 0.10);
	        }}
	        .workspace-path-status strong {{ color: var(--ink); }}
        .workspace-step-actions {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 12px;
        }}
        .guided-case-flow {{
            display: grid;
            gap: 12px;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            margin-top: 16px;
        }}
        .case-flow-step {{
            border-radius: var(--radius-lg);
            border: 1px solid rgba(21, 34, 48, 0.10);
            background: rgba(255, 253, 250, 0.76);
            padding: 16px;
        }}
        .case-flow-step strong {{
            display: block;
            color: var(--ink);
        }}
        .case-flow-step p {{
            margin: 8px 0 0;
        }}
        .case-flow-step .dataset-step-status {{
            margin-top: 10px;
        }}
        .docket-next-action-panel, .document-insight-panel {{
            display: grid;
            gap: 12px;
            margin-top: 16px;
            padding: 16px;
            border-radius: var(--radius-lg);
            background: #ffffff;
            border: 1px solid rgba(17, 92, 99, 0.16);
            box-shadow: 0 10px 26px rgba(21, 34, 48, 0.055);
        }}
        .docket-next-action-panel h3, .document-insight-panel h3 {{
            margin: 0;
            font-size: 1.05rem;
        }}
        .document-insight-grid {{
            display: grid;
            gap: 12px;
            grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
        }}
        .document-insight-item {{
            border-left: 3px solid rgba(17, 92, 99, 0.30);
            padding-left: 10px;
        }}
        .document-insight-item span {{
            display: block;
            color: var(--muted);
            font-size: 0.76rem;
            font-weight: 900;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }}
        .document-insight-item strong {{
            display: block;
            margin-top: 4px;
            color: var(--ink);
        }}
        .quick-search-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
        }}
        .quick-search-row button {{
            background: rgba(170, 77, 29, 0.10);
            color: #763612;
            border: 1px solid rgba(170, 77, 29, 0.18);
        }}
        .technical-details {{
            margin-top: 14px;
            padding: 14px;
            border-radius: var(--radius-md);
            background: rgba(21, 34, 48, 0.035);
            border: 1px solid rgba(21, 34, 48, 0.08);
        }}
        .technical-details > summary {{
            cursor: pointer;
            color: var(--accent-strong);
            font-weight: 900;
        }}
        .handoff-actions {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }}
        .docket-workspace-summary {{
            display: grid;
            gap: 12px;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            margin-top: 16px;
            padding: 14px;
            border-radius: var(--radius-lg);
            background: rgba(17, 92, 99, 0.055);
            border: 1px solid rgba(17, 92, 99, 0.14);
        }}
        .docket-summary-item {{
            border-left: 3px solid rgba(17, 92, 99, 0.34);
            padding-left: 10px;
        }}
        .docket-summary-item span {{
            display: block;
            color: var(--muted);
            font-size: 0.74rem;
            font-weight: 900;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }}
        .docket-summary-item strong {{
            display: block;
            color: var(--ink);
            margin-top: 4px;
            font-size: 1.02rem;
        }}
        .docket-current-task {{
            display: grid;
            gap: 14px;
            grid-template-columns: minmax(0, 1fr) auto;
            align-items: center;
            margin-top: 16px;
            padding: 18px;
            border-radius: var(--radius-lg);
            background: rgba(255, 253, 250, 0.98);
            border: 2px solid rgba(17, 92, 99, 0.24);
            box-shadow: 0 14px 34px rgba(21, 34, 48, 0.075);
        }}
        .docket-current-task h3 {{
            margin: 0;
            font-size: 1.18rem;
        }}
        .docket-current-task p {{
            margin: 6px 0 0;
        }}
        .docket-current-task .primary-action {{
            white-space: nowrap;
        }}
        .annotation-current-task {{
            display: grid;
            gap: 14px;
            grid-template-columns: minmax(0, 1fr) auto;
            align-items: center;
            margin: 16px 0;
            padding: 18px;
            border-radius: var(--radius-lg);
            background: rgba(17, 92, 99, 0.055);
            border: 2px solid rgba(17, 92, 99, 0.20);
        }}
        .annotation-current-task h3 {{
            margin: 0;
            font-size: 1.14rem;
        }}
        .annotation-current-task p {{
            margin: 6px 0 0;
        }}
        .selected-document-scope {{
            display: grid;
            gap: 10px;
            margin: 14px 0;
            padding: 14px 16px;
            border-radius: var(--radius-lg);
            background: rgba(255, 253, 250, 0.92);
            border: 1px solid rgba(17, 92, 99, 0.16);
        }}
        .selected-document-scope strong {{
            display: block;
            color: var(--ink);
        }}
        .selected-document-scope span {{
            color: var(--muted);
        }}
        .deadline-risk-grid {{
            display: grid;
            gap: 10px;
            grid-template-columns: repeat(auto-fit, minmax(135px, 1fr));
            margin-top: 12px;
        }}
        .deadline-risk-card {{
            border-radius: var(--radius-md);
            border: 1px solid rgba(21, 34, 48, 0.10);
            background: rgba(255, 253, 250, 0.86);
            padding: 12px;
        }}
        .deadline-risk-card span {{
            display: block;
            color: var(--muted);
            font-size: 0.74rem;
            font-weight: 900;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }}
        .deadline-risk-card strong {{
            display: block;
            margin-top: 4px;
            color: var(--ink);
            font-size: 1.05rem;
        }}
        .deadline-risk-card.is-urgent {{
            background: rgba(170, 77, 29, 0.12);
            border-color: rgba(170, 77, 29, 0.22);
        }}
        .deadline-risk-card.is-urgent strong {{ color: var(--warm); }}
        .docket-workflow-mode {{
            display: grid;
            gap: 12px;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            margin-top: 16px;
        }}
        .docket-mode-card {{
            border-radius: var(--radius-md);
            border: 1px solid rgba(21, 34, 48, 0.10);
            background: rgba(21, 34, 48, 0.035);
            padding: 14px;
        }}
        .docket-mode-card strong {{
            display: block;
            color: var(--ink);
        }}
        .docket-mode-card p {{
            margin: 6px 0 0;
        }}
        .filing-workspace-panel {{
            display: grid;
            gap: 14px;
            margin-top: 16px;
            padding: 16px;
            border-radius: var(--radius-lg);
            background: #ffffff;
            border: 1px solid rgba(21, 34, 48, 0.10);
            box-shadow: 0 10px 28px rgba(21, 34, 48, 0.055);
        }}
        .filing-workspace-header {{
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 14px;
            flex-wrap: wrap;
        }}
        .filing-workspace-header h3 {{
            margin: 0;
            font-size: 1.08rem;
        }}
        .filing-list {{
            display: grid;
            gap: 8px;
            max-height: 430px;
            overflow: auto;
            padding-right: 2px;
        }}
        .filing-row {{
            display: grid;
            gap: 10px;
            grid-template-columns: minmax(0, 1.5fr) minmax(110px, 0.6fr) minmax(130px, 0.8fr) auto;
            align-items: center;
            padding: 12px;
            border-radius: var(--radius-md);
            border: 1px solid rgba(21, 34, 48, 0.10);
            background: rgba(255, 253, 250, 0.92);
        }}
        .filing-row.is-selected {{
            border-color: rgba(17, 92, 99, 0.45);
            background: rgba(17, 92, 99, 0.08);
            box-shadow: inset 0 0 0 2px rgba(17, 92, 99, 0.08);
        }}
        .filing-title {{
            display: block;
            color: var(--ink);
            font-weight: 900;
        }}
        .filing-meta {{
            display: block;
            margin-top: 4px;
            color: var(--muted);
            font-size: 0.88rem;
            font-weight: 700;
        }}
        .filing-labels {{
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
        }}
        .filing-label {{
            display: inline-flex;
            align-items: center;
            min-height: 26px;
            border-radius: 999px;
            padding: 4px 8px;
            background: rgba(21, 34, 48, 0.06);
            color: var(--ink);
            font-size: 0.78rem;
            font-weight: 800;
        }}
        .filing-label.is-urgent {{
            background: rgba(170, 77, 29, 0.14);
            color: var(--warm);
        }}
        .filing-action {{
            white-space: nowrap;
            background: rgba(17, 92, 99, 0.10);
            color: var(--accent-strong);
            border: 1px solid rgba(17, 92, 99, 0.16);
        }}
        .selected-filing-banner {{
            display: grid;
            gap: 12px;
            margin-top: 14px;
            padding: 16px;
            border-radius: var(--radius-lg);
            background: rgba(17, 92, 99, 0.08);
            border: 1px solid rgba(17, 92, 99, 0.18);
        }}
        .selected-filing-banner h3 {{
            margin: 0;
            font-size: 1.12rem;
        }}
        .docket-action-strip {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }}
        .docket-action-strip a, .docket-action-strip button {{
            min-height: 42px;
        }}
        .label-suggestion-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 8px;
        }}
        .label-suggestion-row button {{
            background: rgba(17, 92, 99, 0.08);
            color: var(--accent-strong);
            border: 1px solid rgba(17, 92, 99, 0.14);
        }}
        .success-receipt {{
            display: none;
            margin-top: 12px;
            padding: 14px;
            border-radius: var(--radius-md);
            background: rgba(29, 107, 75, 0.10);
            border: 1px solid rgba(29, 107, 75, 0.18);
            color: var(--good);
            font-weight: 800;
        }}
        .success-receipt.is-visible {{
            display: block;
        }}
        .preflight-panel {{
            display: none;
            margin-top: 14px;
            padding: 16px;
            border-radius: var(--radius-lg);
            background: rgba(255, 253, 250, 0.96);
            border: 2px solid rgba(17, 92, 99, 0.18);
            box-shadow: 0 12px 30px rgba(21, 34, 48, 0.065);
        }}
        .preflight-panel.is-visible {{
            display: block;
        }}
        .preflight-panel[hidden] {{
            display: none;
        }}
        .preflight-panel-header {{
            display: flex;
            justify-content: space-between;
            gap: 14px;
            align-items: flex-start;
            flex-wrap: wrap;
        }}
        .preflight-panel-header h3 {{
            margin: 0;
            font-size: 1.08rem;
        }}
        .preflight-panel-header p {{
            margin: 6px 0 0;
        }}
        .preflight-summary {{
            display: grid;
            gap: 10px;
            margin-top: 16px;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        }}
        .preflight-summary div {{
            border-left: 3px solid rgba(17, 92, 99, 0.32);
            padding-left: 10px;
        }}
        .preflight-summary span {{
            display: block;
            color: var(--muted);
            font-size: 0.74rem;
            font-weight: 900;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }}
        .preflight-summary strong {{
            display: block;
            color: var(--ink);
            margin-top: 4px;
        }}
	        .field-helper {{
	            margin: 6px 0 0;
	            color: var(--muted);
	            font-size: 0.9rem;
	            font-weight: 700;
	        }}
	        .advanced-filter-field {{
	            opacity: 0.86;
	        }}
        .workspace-checklist {{
            display: grid;
            gap: 8px;
            margin: 14px 0 0;
        }}
        .workspace-checklist div {{
            display: grid;
            grid-template-columns: auto minmax(0, 1fr);
            gap: 10px;
            align-items: start;
            padding: 10px;
            border-radius: var(--radius-md);
            border: 1px solid rgba(21, 34, 48, 0.10);
            background: rgba(255, 253, 250, 0.76);
        }}
        .workspace-checklist span {{
            display: inline-grid;
            place-items: center;
            width: 28px;
            height: 28px;
            border-radius: 999px;
            background: rgba(17, 92, 99, 0.12);
            color: var(--accent-strong);
            font-weight: 900;
        }}
        .lane-help {{
            margin-top: 12px;
            color: var(--muted);
            font-weight: 700;
        }}
        .preflight-hint {{
            margin-top: 10px;
            color: var(--warm);
            font-weight: 800;
        }}
        .dataset-step {{
            margin-top: 18px;
            padding: 16px;
            border-radius: var(--radius-lg);
            border: 1px solid rgba(21, 34, 48, 0.10);
            background: rgba(255, 253, 250, 0.74);
        }}
        .dataset-step h3 {{ margin: 0 0 10px; font-size: 1.05rem; }}
	        .dataset-step-status {{
	            display: inline-flex;
	            align-items: center;
	            min-height: 30px;
            border-radius: 999px;
            padding: 6px 10px;
            background: rgba(21, 34, 48, 0.06);
            color: var(--ink);
            font-size: 0.82rem;
            font-weight: 900;
        }}
        pre {{
            margin: 16px 0 0;
            white-space: pre-wrap;
            overflow-wrap: anywhere;
            background: rgba(21, 34, 48, 0.04);
            padding: 16px;
            border-radius: var(--radius-md);
            border: 1px solid rgba(21, 34, 48, 0.08);
            color: var(--ink);
        }}
        .helper {{ font-size: 0.92rem; }}
        .legacy-grid {{ display: grid; gap: 24px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }}
        .modal[hidden] {{ display: none; }}
        .modal {{
            position: fixed;
            inset: 0;
            background: rgba(11, 18, 24, 0.52);
            display: grid;
            place-items: center;
            padding: 18px;
            z-index: 1000;
        }}
        .modal-panel {{
            width: min(760px, 100%);
            max-height: calc(100vh - 36px);
            overflow: auto;
            background: var(--surface-strong);
            border-radius: var(--radius-xl);
            padding: 24px;
            box-shadow: 0 30px 80px rgba(11, 18, 24, 0.24);
        }}
        .modal-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 16px;
        }}
        .modal-grid {{ display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); margin-top: 18px; }}
        .modal-actions {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; }}
        .modal-close {{ background: rgba(21, 34, 48, 0.08); color: var(--ink); }}
        @media (max-width: 900px) {{
            .hero-grid, .field-row, .workspace-context-bar, .entry-overview {{ grid-template-columns: 1fr; }}
        }}
	        @media (max-width: 640px) {{
		            header {{ padding: 24px 20px; }}
		            main {{ padding-left: 22px; padding-right: 22px; }}
		            .header-copy p {{ font-size: 1rem; }}
		            .surface-pills {{ display: none; }}
	            .surface-pills a, button, .modal-link, .jump-link, .primary-action, .secondary-action, .decision-link {{
	                min-height: 44px;
	                align-items: center;
	            }}
	            .dashboard-section-menu {{
	                position: static;
	                z-index: auto;
	            }}
	            .dashboard-section-menu > summary {{ display: block; }}
	            .dashboard-section-menu:not([open]) .journey-nav {{ display: none; }}
	            .journey-nav {{
	                position: static;
	                margin-top: 8px;
	                max-height: 46vh;
	                overflow: auto;
	                align-content: flex-start;
	                box-shadow: none;
	            }}
            .stage-card, .lane-card {{ flex-basis: 100%; }}
            .filing-row {{ grid-template-columns: 1fr; }}
            .docket-workspace-summary {{ grid-template-columns: 1fr 1fr; }}
            .docket-current-task {{ grid-template-columns: 1fr; }}
            .docket-current-task .primary-action {{ width: 100%; justify-content: center; }}
            .workspace-context-bar {{
                position: static;
                grid-template-columns: 1fr;
            }}
            .current-work-bar {{
                grid-template-columns: 1fr;
            }}
            .current-work-actions {{
                justify-content: stretch;
            }}
            .current-work-actions a {{
                flex: 1 1 100%;
                text-align: center;
            }}
            .primary-action, .secondary-action, .decision-link {{ justify-content: center; }}
            .context-actions a, .stage-actions a {{ flex: 1 1 100%; text-align: center; }}
	            .workflow-rail h2 {{ font-size: 1.45rem; }}
	            .workflow-rail-header .primary-action {{ width: 100%; text-align: center; justify-content: center; }}
		            .stage-actions {{ display: none; }}
	            .mobile-action-rail {{ display: flex; }}
	            .dashboard-section-menu[open] ~ .mobile-action-rail {{ display: none; }}
	            .entry-path-grid {{ grid-template-columns: 1fr; }}
	            .secondary-decision-row .decision-link {{ flex: 1 1 100%; justify-content: center; }}
	        }}
    </style>
</head>
<body>
    <header>
	        <div class="header-copy">
	            <div class="eyebrow">Complaint Operations Center</div>
	            <h1>Unified Dashboard Hub</h1>
	            <p>Start, continue, organize, review, and draft a legal complaint or response from one guided workspace.</p>
	        </div>
        <div class="surface-pills">{''.join(f'<a href="{escape(path)}">{escape(label)}</a>' for label, path in fixtures.complaint_links)}</div>
    </header>
    <main>
        <details class="dashboard-section-menu" id="dashboard-section-menu" open>
            <summary>Dashboard sections</summary>
            <nav class="journey-nav" aria-label="Dashboard section navigation" role="tablist">
                {dashboard_section_nav}
            </nav>
        </details>
        <section class="workflow-rail" id="dashboard-workflow-rail" aria-label="Complaint workflow rail">
            <div class="workflow-rail-header">
                <div>
                    <div class="eyebrow" style="color: var(--accent);">Guided Workflow</div>
                    <h2>Intake -> Evidence, Law, and Caselaw -> Review -> Draft</h2>
                    <p id="workflow-rail-summary">Load the workspace to align the dashboard around the next valid complaint step.</p>
                </div>
                <a class="primary-action" id="workflow-primary-action" href="/chat">Explain what happened</a>
            </div>
            <div class="stage-rail" aria-label="Workflow stages">
                <div class="stage-card is-current" id="workflow-stage-intake" data-state="current">
                    <span class="stage-state-badge" id="workflow-stage-intake-badge">Current</span>
                    <span class="stage-number">1</span>
                    <strong>Intake</strong>
                    <span id="workflow-stage-intake-status">Start or continue the story.</span>
                </div>
                <div class="stage-card" id="workflow-stage-evidence" data-state="ready">
                    <span class="stage-state-badge" id="workflow-stage-evidence-badge">Ready</span>
                    <span class="stage-number">2</span>
                    <strong>Evidence, Laws, and Court Cases</strong>
                    <span id="workflow-stage-evidence-status">Add and organize documents, messages, rules, and cases.</span>
                </div>
	                <div class="stage-card" id="workflow-stage-review" data-state="blocked">
	                    <span class="stage-state-badge" id="workflow-stage-review-badge">Blocked</span>
	                    <span class="stage-number">3</span>
	                    <strong>Review</strong>
	                    <span id="workflow-stage-review-status">Close support gaps before drafting.</span>
	                    <a class="stage-unlock" id="workflow-stage-review-unlock" href="/claim-support-review">Fix proof gaps</a>
	                </div>
	                <div class="stage-card" id="workflow-stage-draft" data-state="blocked">
	                    <span class="stage-state-badge" id="workflow-stage-draft-badge">Blocked</span>
	                    <span class="stage-number">4</span>
	                    <strong>Draft</strong>
	                    <span id="workflow-stage-draft-status">Generate or refine the complaint.</span>
	                    <a class="stage-unlock" id="workflow-stage-draft-unlock" href="#chat-upload-dashboard">Add evidence first</a>
	                </div>
            </div>
            <div class="stage-actions">
                <a class="secondary-action" href="/chat">Intake chat</a>
                <a class="secondary-action" href="#chat-upload-dashboard">Upload evidence</a>
                <a class="secondary-action" href="/claim-support-review">Review support</a>
	                <a class="secondary-action" href="/document">Build draft</a>
            </div>
        </section>
        <nav class="mobile-action-rail" id="mobile-action-rail" aria-label="Mobile workflow action rail">
            <a class="primary-action" id="mobile-workflow-primary-action" href="/chat">Explain what happened</a>
            <a class="secondary-action" href="#workspace-dataset-parquet-dashboard">Organize materials</a>
        </nav>
	        <section class="start-here" id="dashboard-start-here">
	            <div class="eyebrow" style="color: var(--accent);">Start Here</div>
	            <h2>What are you trying to do right now?</h2>
	            <p>Start with the safest next step for the current complaint record. Other tools stay nearby, but the dashboard will keep one recommended action in front.</p>
	            <div class="recommended-action-panel" id="dashboard-recommended-action-panel" aria-label="Recommended next action">
	                <div>
	                    <div class="eyebrow" style="color: var(--accent);">Recommended Next Step</div>
	                    <h3 id="dashboard-recommended-action-title">Explain what happened</h3>
	                    <p id="dashboard-recommended-action-reason">Begin with guided questions so the workspace has the story, people, dates, harms, and possible claims.</p>
	                </div>
	                <div class="recommended-action-actions">
	                    <a class="decision-link primary" id="dashboard-recommended-action-link" href="/chat">Explain what happened</a>
	                    <a class="decision-link" href="#heads-up-display-dashboard">Why this step?</a>
	                </div>
	            </div>
	            <div class="secondary-decision-row" aria-label="Other dashboard decisions">
	                <a class="decision-link" href="#dashboard-workspace-snapshot">Resume complaint</a>
	                <a class="decision-link" href="#chat-upload-dashboard">Add evidence</a>
	                <a class="decision-link" href="#docket-dataset-parquet-dashboard">Review docket</a>
	                <a class="decision-link" href="#dashboard-subsection-index">More tools</a>
	            </div>
	        </section>

        <section class="entry-overview" id="dashboard-entry-overview" aria-label="MCP dashboard package capabilities overview">
            <article class="entry-overview-panel">
                <div class="eyebrow" style="color: var(--accent);">What this dashboard helps with</div>
                <h2>Start, continue, organize, review, and draft legal complaints or responses.</h2>
                <p>This dashboard groups the package around ordinary complaint work: answer guided questions, continue a saved complaint, add evidence, organize laws and court cases, review docket filings, find important connections, and build a draft when the record is ready.</p>
                <div class="chip-row">
                    <span class="chip good">Guided questions</span>
                    <span class="chip warm">Evidence, laws, and court cases</span>
                    <span class="chip">Docket and response review</span>
                    <span class="chip">Connections and duty checks</span>
                    <span class="chip">Profile and saved sessions</span>
                </div>
                <div class="legal-safety-note">
                    <strong>Important</strong>
                    <span>This tool helps organize information and draft documents. It does not decide whether you should file, and it is not a substitute for legal advice.</span>
                </div>
            </article>
            <div class="entry-path-grid" id="dashboard-entry-paths">
                {entry_path_cards}
            </div>
        </section>

        <section class="subsection-index" id="dashboard-subsection-index">
            <div class="eyebrow" style="color: var(--accent);">Find the right tool</div>
            <h2>Jump to the part of the complaint workflow you need.</h2>
            <p>Use this index to add evidence, organize materials, review proof gaps, search docket filings, find important connections, check duties or conflicts, add notes, or open optional technical tools.</p>
            <div class="subsection-index-grid">
                {dashboard_subsection_index}
            </div>
        </section>

        <section class="workspace-context-bar" id="workspace-context-bar" aria-label="Loaded workspace context">
            <div>
                <div class="current-work-bar" id="current-work-bar" aria-label="Current work and selected document">
                    <div class="current-work-main">
                        <div class="current-work-title-row">
                            <span class="current-work-stage" id="current-work-stage">Current step: Intake</span>
                            <h2 id="current-work-title">Explain what happened</h2>
                        </div>
                        <p class="current-work-detail" id="current-work-detail">Start with guided questions so the complaint record has the story, people, dates, harms, and possible claims.</p>
                        <div class="current-work-status-row" aria-label="Current context status">
                            <span class="context-status-pill is-warning" id="current-work-selected-document">No document selected</span>
                            <span class="context-status-pill" id="current-work-router-status">Chat uses general intake context</span>
                            <span class="context-status-pill is-warning" id="current-work-prerequisite">Select a filing to enable document-aware chat</span>
                        </div>
                    </div>
                    <div class="current-work-actions">
                        <a class="primary-action" id="current-work-primary" href="/chat">Explain what happened</a>
                        <a class="secondary-action is-disabled" id="current-work-secondary" href="/chat" aria-disabled="true">Ask about selected filing</a>
                    </div>
                </div>
                <div class="eyebrow" style="color: var(--accent);">Workspace Context</div>
                <h2 id="context-next-action">Load workspace to get next action</h2>
                <div class="context-grid">
                    <div class="context-metric"><span>Workspace</span><strong id="context-workspace-id">not loaded</strong><a class="context-action-hint" id="context-workspace-hint" href="/workspace">Load workspace</a></div>
                    <div class="context-metric"><span>Claim type</span><strong id="context-claim-type">waiting</strong><a class="context-action-hint" id="context-claim-hint" href="/chat">Clarify claim</a></div>
                    <div class="context-metric"><span>Evidence</span><strong id="context-evidence-count">0 items</strong><a class="context-action-hint" id="context-evidence-hint" href="#chat-upload-dashboard">Upload evidence</a></div>
                    <div class="context-metric"><span>Draft</span><strong id="context-draft-status">not available</strong><a class="context-action-hint" id="context-draft-hint" href="/document">Open builder</a></div>
                    <div class="context-metric is-warning" id="context-selected-document-card"><span>Selected document</span><strong id="context-selected-document">none selected</strong><a class="context-action-hint is-disabled" id="context-selected-document-hint" href="#docket-dataset-parquet-dashboard" aria-disabled="true">Select a filing</a></div>
                    <div class="context-metric" id="context-router-card"><span>Chat mode</span><strong id="context-router-mode">general intake</strong><a class="context-action-hint" id="context-router-hint" href="/chat">Open chat</a></div>
                </div>
            </div>
            <div class="context-actions">
                <a class="secondary-action" id="context-open-workspace" href="/workspace">Workspace</a>
                <a class="secondary-action" id="context-open-review" href="/claim-support-review">Review</a>
                <a class="secondary-action" id="context-open-chat" href="/chat">Chat</a>
                <a class="secondary-action is-disabled" id="context-open-selected-chat" href="/chat" aria-disabled="true">Ask about selected filing</a>
                <a class="primary-action" id="context-open-builder" href="/document">Build draft</a>
            </div>
        </section>
        <section class="hero-grid">
            <article class="hero-card">
                <div class="eyebrow" style="color: #115c63;">Package Capability Map</div>
                <h2>Choose the workflow you need, then drill into the dashboard tools behind it.</h2>
                <p>The cards below connect the package tools to ordinary complaint tasks: start intake, resume a case, inspect a docket, organize evidence and law, or draft a document.</p>
                <div class="chip-row">
                    <span class="chip good">Intake chat and review</span>
                    <span class="chip warm">Workspace evidence, law, and caselaw datasets</span>
                    <span class="chip">Docket dataset search</span>
                    <span class="chip">Connections and duties</span>
                    <span class="chip">Profile and decentralized identity</span>
                </div>
            </article>
            <article class="card" id="profile-and-identity-dashboard">
                <h2>Quick Surface Links</h2>
                <p>Use these when you want to jump straight into the dedicated surface after choosing a workflow. Profile, cookies, workspace, and SDK routes share the same browser-side MCP sync context.</p>
                {_render_subsection_nav("Profile and session subsections", [("Profile", "/profile"), ("Cookies", "/cookies"), ("Workspace context", "#workspace-context-bar"), ("Advanced tools", "#dashboard-advanced-tools")])}
                <ul>{complaint_links}</ul>
            </article>
        </section>

        <section class="capability-grid" id="dashboard-capabilities">
            {capability_cards}
        </section>

        <section class="journey-detail-grid" id="dashboard-journey-details">
            {journey_detail_panels}
        </section>

        <details class="secondary-dashboard-details" id="dashboard-package-map">
            <summary>Package capability map and implementation plan</summary>
            <section class="card">
                <div class="eyebrow" style="color: var(--accent);">Package Capability Matrix</div>
                <h2>How the package capabilities connect to dashboard surfaces</h2>
                <p>This map keeps each user-facing path tied to concrete routes, MCP tools, dataset APIs, graph analyzers, legal authority/caselaw surfaces, and legacy ipfs_datasets_py dashboards.</p>
                <div class="package-map-grid">
                    {package_capability_matrix}
                </div>
            </section>
            <section class="card capability-plan" id="dashboard-improvement-plan">
                <div class="eyebrow" style="color: var(--accent);">Comprehensive Improvement Plan</div>
                <h2>How this dashboard ties the package together</h2>
                <p>This plan keeps the UI grounded in surfaces that already exist in the package while making the next implementation slices clear.</p>
                <ul>{improvement_plan}</ul>
            </section>
        </details>

        <details class="advanced-tools" id="dashboard-advanced-tools">
            <summary>Technical tools for administrators</summary>
            <p class="advanced-tools-helper">Most users do not need these to create or manage a complaint. Open this section only for diagnostics, package consoles, SDK behavior, cookies, raw MCP tools, or legacy ipfs_datasets_py dashboards.</p>
            <div class="advanced-tools-grid">
                <article class="package-map-card">
                    <h3>MCP and SDK Operations</h3>
                    <p>Inspect MCP tool metadata, browser sync behavior, JSON-compatible endpoints, and SDK playground wiring.</p>
                    <div class="section-jump-row">{_render_link_row([("MCP dashboard", "/mcp"), ("MCP tools JSON", "/api/complaint-workspace/mcp/tools"), ("SDK playground", "/ipfs-datasets/sdk-playground")])}</div>
                </article>
                <article class="package-map-card">
                    <h3>Profile and Session Context</h3>
                    <p>Open profile, cookies, workspace identity, and current context state used when moving between dashboards.</p>
                    <div class="section-jump-row">{_render_link_row([("Profile", "/profile"), ("Cookies", "/cookies"), ("Workspace context", "#workspace-context-bar")])}</div>
                </article>
                <article class="package-map-card">
                    <h3>Legacy ipfs_datasets_py Consoles</h3>
                    <p>Reach the mounted compatibility dashboards for package administration, graph tools, vector search, audit, and monitoring.</p>
                    <div class="section-jump-row">{_render_link_row([("Legacy dashboard list", "#legacy-ipfs-dashboard-shells"), ("Admin MCP dashboard", "/dashboards/ipfs-datasets/admin-mcp"), ("GraphRAG dashboard", "/dashboards/ipfs-datasets/admin-graphrag")])}</div>
                </article>
            </div>
        </details>

        <section class="workspace-cards">
            <article class="dashboard-card" id="dashboard-workspace-snapshot">
                <div class="eyebrow" style="color: var(--accent);">Workspace Card</div>
                <h2>Complaint Workspace Snapshot</h2>
                <p>Load the shared complaint session and see the intake, evidence, and draft state that currently gates review and builder handoffs.</p>
                {_render_subsection_nav("Workspace subsections", [("Intake chat", "/chat"), ("Upload evidence", "#chat-upload-dashboard"), ("Review support", "/claim-support-review"), ("Generate complaint", "/document")])}
                <div class="field-row">
                    <div>
                        <label class="field-label" for="dashboard-workspace-user-id">Workspace User ID</label>
                        <input id="dashboard-workspace-user-id" type="text" value="{escape(default_user_id)}" placeholder="demo-user">
                    </div>
                </div>
                <div class="button-row" style="margin-top: 12px;">
                    <button id="dashboard-load-workspace" type="button">Refresh Workspace</button>
                    <button id="dashboard-reset-workspace" type="button" class="secondary">Reset Workspace</button>
                    <button id="dashboard-unload-workspace" type="button" class="secondary">Unload Workspace</button>
                </div>
                <div class="stat-grid">
                    <div class="stat-card"><strong id="dashboard-workspace-answered">0</strong><span>Answered intake prompts</span></div>
                    <div class="stat-card"><strong id="dashboard-workspace-evidence">0</strong><span>Evidence items</span></div>
                    <div class="stat-card"><strong id="dashboard-workspace-missing">0</strong><span>Missing support elements</span></div>
                    <div class="stat-card"><strong id="dashboard-workspace-draft">No</strong><span>Draft available</span></div>
                </div>
                <div class="chip-row" style="margin-top: 14px;">
                    <span class="chip" id="dashboard-workspace-session-chip">session: waiting</span>
                    <span class="chip" id="dashboard-workspace-route-chip">next route: waiting</span>
                    <span class="chip" id="dashboard-workspace-mike-state-chip">mike: loading</span>
                    <span class="chip" id="dashboard-workspace-mike-conflict-chip">mike conflicts: n/a</span>
                </div>
                <div class="status-line" id="dashboard-workspace-status">Ready to load the complaint workspace session.</div>
                <pre id="dashboard-workspace-preview">Workspace session details will appear here.</pre>
            </article>

            <article class="dashboard-card" id="packaged-docket-dashboard">
                <div class="eyebrow" style="color: var(--accent);">Court Filings</div>
                <h2>Open a Saved Docket Package</h2>
                <p>Use this when you already have a prepared case-filing package. The dashboard will look for filings, hearing dates, deadlines, and items that may affect a complaint or response.</p>
                {_render_subsection_nav("Docket review steps", [("Load case filings", "#docket-dataset-parquet-dashboard"), ("Review dates", "#dashboard-docket-calendar-list"), ("Save useful note", "#dataset-document-annotation-dashboard"), ("Next action", "#heads-up-display-dashboard")])}
                <div class="docket-next-action-panel" aria-label="Packaged docket next step">
                    <div>
                        <div class="eyebrow" style="color: var(--accent);">What to do here</div>
                        <h3>Open the saved filing package, then inspect dates and useful filings</h3>
                        <p>This path is best for an already prepared docket package. If you only have a single saved filing dataset, use the docket review card below.</p>
                    </div>
                </div>
                <details class="technical-details">
                    <summary>Saved package location</summary>
                    <label class="field-label" for="dashboard-docket-manifest-path">Package file location</label>
                    <input id="dashboard-docket-manifest-path" type="text" value="{escape(default_manifest_path)}" placeholder="/absolute/path/to/docket-manifest.json">
                    <p class="field-helper">Advanced detail: this is the packaged docket manifest path used by the MCP docket tools.</p>
                </details>
                <div class="button-row" style="margin-top: 12px;">
                    <button id="dashboard-load-docket" type="button">Open Filing Package</button>
                    <button id="dashboard-load-docket-report" type="button" class="secondary">Preview Extracted Report</button>
                    <button id="dashboard-unload-docket" type="button" class="secondary">Clear Package</button>
                </div>
                <div class="stat-grid">
                    <div class="stat-card"><strong id="dashboard-docket-queue">0</strong><span>Items to inspect</span></div>
                    <div class="stat-card"><strong id="dashboard-docket-high">0</strong><span>Urgent items</span></div>
                    <div class="stat-card"><strong id="dashboard-docket-runs">0</strong><span>Review runs</span></div>
                    <div class="stat-card"><strong id="dashboard-docket-calendar-count">0</strong><span>Dates found</span></div>
                </div>
                <div class="chip-row" style="margin-top: 14px;">
                    <span class="chip" id="dashboard-docket-source-chip">filings: not loaded</span>
                    <span class="chip" id="dashboard-docket-manifest-chip">package: not selected</span>
                    <span class="chip" id="dashboard-docket-calendar-chip">dates: waiting</span>
                </div>
                <div class="status-line" id="dashboard-docket-status">Open a saved filing package to inspect dates, deadlines, and useful docket records.</div>
                <div style="margin-top: 14px;">
                    <div class="field-label">Important dates found</div>
                    <div class="chip-row" id="dashboard-docket-calendar-list">
                        <span class="chip">Load a docket to preview hearings, deadlines, and conferences.</span>
                    </div>
                </div>
                <details class="technical-details">
                    <summary>Technical docket payload</summary>
                    <pre id="dashboard-docket-preview">Packaged docket details will appear here.</pre>
                </details>
            </article>

            <article class="dashboard-card" id="docket-dataset-parquet-dashboard">
                <div class="eyebrow" style="color: var(--accent);">Docket Review</div>
                <h2>Review Court Filings and Existing Complaints</h2>
                <p>Load case filings, search for hearings or deadlines, inspect the most useful document, and save a note into the complaint workspace.</p>
                {_render_subsection_nav("Docket review steps", [("Load case filings", "#dashboard-docket-dataset-path"), ("Search filings", "#dashboard-docket-dataset-query"), ("Review dates", "#dashboard-docket-calendar-list"), ("Save useful note", "#dataset-document-annotation-dashboard")])}
                <div class="guided-case-flow" aria-label="Docket review workflow">
                    <div class="case-flow-step">
                        <strong>1. Load case filings</strong>
                        <p>Open a saved docket package or filing dataset.</p>
                        <span class="dataset-step-status" id="docket-flow-load-state">Not loaded</span>
                    </div>
                    <div class="case-flow-step">
                        <strong>2. Search and inspect</strong>
                        <p>Find filings, motions, hearings, orders, deadlines, or complaint allegations.</p>
                        <span class="dataset-step-status" id="docket-flow-search-state">Waiting for filings</span>
                    </div>
                    <div class="case-flow-step">
                        <strong>3. Save legal impact</strong>
                        <p>Send useful document notes to the complaint workspace for review or drafting.</p>
                        <span class="dataset-step-status" id="docket-flow-annotation-state">Waiting for selected document</span>
                    </div>
                </div>
                <div class="docket-next-action-panel" id="docket-next-action-panel" aria-label="Docket next safe action">
                    <div>
                        <div class="eyebrow" style="color: var(--accent);">Next Safe Action</div>
                        <h3 id="docket-next-action-title">Load case filings</h3>
                        <p id="docket-next-action-reason">Choose a saved filing set before searching, finding dates, or saving notes.</p>
                    </div>
                    <div class="button-row">
                        <button id="dashboard-load-docket-dataset" type="button">Load Case Filings</button>
                        <a class="secondary-action" id="docket-next-annotation-link" href="#dataset-document-annotation-dashboard">Save note from selected filing</a>
                    </div>
                </div>
                <div class="docket-current-task" id="docket-current-task" aria-label="Current docket task">
                    <div>
                        <div class="eyebrow" style="color: var(--accent);">Current Task</div>
                        <h3 id="docket-current-task-title">Load filings</h3>
                        <p id="docket-current-task-detail">Open the saved docket package, then select one filing before labels, notes, or workspace handoff.</p>
                    </div>
                    <a class="primary-action" id="docket-current-task-action" href="#dashboard-docket-dataset-path">Load filings</a>
                </div>
                <details class="technical-details">
                    <summary>Saved filing location and format</summary>
                    <label class="field-label" for="dashboard-docket-dataset-path">Saved filing set location</label>
                    <input id="dashboard-docket-dataset-path" type="text" value="{escape(default_docket_dataset_path)}" placeholder="/absolute/path/to/docket.dataset.parquet">
                    <p class="field-helper">Advanced detail: this can be one saved docket dataset, a packaged manifest, or source JSON.</p>
                    <div style="margin-top: 12px;">
                        <label class="field-label" for="dashboard-docket-dataset-input-type">Saved filing format</label>
                        <select id="dashboard-docket-dataset-input-type">
                            <option value="single" {'selected' if docket_input_type == 'single' else ''}>One saved filing dataset</option>
                            <option value="packaged" {'selected' if docket_input_type == 'packaged' else ''}>Packaged docket manifest</option>
                            <option value="json" {'selected' if docket_input_type == 'json' else ''}>Source JSON</option>
                        </select>
                    </div>
                </details>
                <div class="field-row" style="margin-top: 14px;">
                    <div>
                        <label class="field-label" for="dashboard-docket-dataset-query">What do you want to find?</label>
                        <input id="dashboard-docket-dataset-query" type="text" placeholder="Find hearing dates, deadlines, motions, orders, or service problems">
                        <p class="field-helper">Search in ordinary words. Good searches include deadlines, hearings, notices, dismissal motions, orders, retaliation, accommodation, or service.</p>
                    </div>
                </div>
                <div class="quick-search-row" aria-label="Suggested docket searches">
                    <button type="button" data-docket-query="hearing deadline court date">Find dates</button>
                    <button type="button" data-docket-query="motion dismissal answer response due">Find response issues</button>
                    <button type="button" data-docket-query="notice service summons complaint">Find service or notice problems</button>
                    <button type="button" data-docket-query="order judgment eviction possession">Find orders or judgments</button>
                </div>
                <div class="button-row" style="margin-top: 12px;">
                    <button id="dashboard-search-docket-dataset" type="button" class="secondary">Search Filings</button>
                    <button id="dashboard-load-docket-dataset-graph" type="button" class="secondary">Map Filing Connections</button>
                </div>
                <div class="stat-grid">
                    <div class="stat-card"><strong id="dashboard-docket-dataset-documents">0</strong><span>Filings found</span></div>
                    <div class="stat-card"><strong id="dashboard-docket-dataset-events">0</strong><span>Dates found</span></div>
                    <div class="stat-card"><strong id="dashboard-docket-dataset-results">0</strong><span>Search results</span></div>
                    <div class="stat-card"><strong id="dashboard-docket-dataset-graph-count">0</strong><span>Connections</span></div>
                </div>
                <div class="docket-workspace-summary" aria-label="Docket workspace summary">
                    <div class="docket-summary-item"><span>Filings loaded</span><strong id="docket-summary-filings">0</strong></div>
                    <div class="docket-summary-item"><span>Dates found</span><strong id="docket-summary-dates">0</strong></div>
                    <div class="docket-summary-item"><span>Selected filing</span><strong id="docket-summary-selected">none yet</strong></div>
                    <div class="docket-summary-item"><span>Notes sent</span><strong id="docket-summary-notes">0</strong></div>
                </div>
                <div class="deadline-risk-grid" aria-label="Deadline risk summary">
                    <div class="deadline-risk-card is-urgent"><span>Overdue</span><strong id="docket-deadline-overdue">0</strong></div>
                    <div class="deadline-risk-card is-urgent"><span>Due soon</span><strong id="docket-deadline-due-soon">0</strong></div>
                    <div class="deadline-risk-card"><span>Upcoming</span><strong id="docket-deadline-upcoming">0</strong></div>
                    <div class="deadline-risk-card"><span>Needs date review</span><strong id="docket-deadline-unparsed">0</strong></div>
                </div>
                <div class="chip-row" style="margin-top: 14px;">
                    <span class="chip" id="dashboard-docket-dataset-case-chip">case: waiting</span>
                    <span class="chip" id="dashboard-docket-dataset-source-chip">filings: waiting</span>
                </div>
                <div class="filing-workspace-panel" id="docket-filing-workspace" aria-label="Docket filing workspace">
                    <div class="filing-workspace-header">
                        <div>
                            <div class="eyebrow" style="color: var(--accent);">Filing Workspace</div>
                            <h3>Select a filing before labeling or sending notes</h3>
                            <p class="field-helper">Pick the court document you want to analyze. The selected filing stays visible while you search, label, annotate, and send a legal-impact note.</p>
                        </div>
                        <div class="docket-action-strip">
                            <a class="secondary-action" href="#dashboard-docket-dataset-query">Search within filings</a>
                            <a class="secondary-action" href="#dataset-document-annotation-dashboard">Add labels and note</a>
                        </div>
                    </div>
                    <div class="filing-list" id="docket-filing-list" role="list" aria-label="Loaded docket filings">
                        <div class="workspace-empty-state" id="docket-filing-empty-state">
                            <h3>No filings loaded yet</h3>
                            <p>Load case filings to see a selectable filing list with dates, labels, and review status.</p>
                        </div>
                    </div>
                </div>
                <div class="selected-filing-banner" id="docket-selected-filing-banner" aria-label="Persistent selected filing">
                    <div>
                        <div class="eyebrow" style="color: var(--accent);">Selected Filing</div>
                        <h3 id="docket-selected-banner-title">No filing selected</h3>
                        <p id="docket-selected-banner-meta">Select a filing from the list to keep its title, dates, labels, and review actions visible.</p>
                    </div>
                    <div class="filing-labels" id="docket-selected-banner-labels">
                        <span class="filing-label">waiting for selection</span>
                    </div>
                    <div class="docket-action-strip">
                        <a class="primary-action" id="docket-banner-note-link" href="#dataset-document-annotation-dashboard">Add legal-impact note</a>
                        <a class="secondary-action" href="#dashboard-docket-dataset-query">Search this docket</a>
                        <a class="secondary-action is-disabled" id="docket-banner-chat-link" href="/chat" aria-disabled="true">Ask chat about selected filing</a>
                    </div>
                </div>
                <div class="docket-workflow-mode" aria-label="Labels notes and handoff explanation">
                    <div class="docket-mode-card">
                        <strong>Labels classify the filing</strong>
                        <p>Use short labels like deadline, hearing, notice, or needs review so the filing can be found later.</p>
                    </div>
                    <div class="docket-mode-card">
                        <strong>Notes explain legal meaning</strong>
                        <p>Use notes to say what the filing changes about the complaint, response, timeline, or proof gaps.</p>
                    </div>
                    <div class="docket-mode-card">
                        <strong>Workspace handoff saves the insight</strong>
                        <p>Review the preflight summary before sending the selected filing note into the complaint workspace.</p>
                    </div>
                </div>
                <div class="document-insight-panel" id="docket-document-insight-panel" aria-label="Selected filing analysis">
                    <div>
                        <div class="eyebrow" style="color: var(--accent);">Selected Filing</div>
                        <h3 id="docket-selected-document-title">No filing selected yet</h3>
                        <p id="docket-selected-document-summary">Load or search filings. The first useful document will appear here with a suggested legal handoff.</p>
                    </div>
                    <div class="document-insight-grid">
                        <div class="document-insight-item"><span>Document</span><strong id="docket-selected-document-id">waiting</strong></div>
                        <div class="document-insight-item"><span>Suggested use</span><strong id="docket-selected-document-use">Review and save a note</strong></div>
                        <div class="document-insight-item"><span>Dates</span><strong id="docket-selected-document-date">not found yet</strong></div>
                    </div>
                    <div class="handoff-actions">
                        <a class="primary-action" id="docket-save-selected-document-link" href="#dataset-document-annotation-dashboard">Save note to workspace</a>
                        <a class="secondary-action is-disabled" id="docket-open-chat-about-document" href="/chat" aria-disabled="true">Ask case chat about this filing</a>
                    </div>
                </div>
                <div class="status-line" id="dashboard-docket-dataset-status">Choose a saved filing set, then load it to review docket filings.</div>
                <details class="technical-details">
                    <summary>Technical docket dataset payload</summary>
                    <pre id="dashboard-docket-dataset-preview">Docket dataset details will appear here.</pre>
                </details>
            </article>

            <article class="dashboard-card" id="workspace-dataset-parquet-dashboard">
                <div class="eyebrow" style="color: var(--accent);">Organize Materials</div>
                <h2>Organize Evidence, Laws, and Court Cases</h2>
                <p>Load or add materials for this complaint, choose what kind of material you want to work with, search it, then use connection and duty checks when the record is ready.</p>
                {_render_subsection_nav("Material organization steps", [("Search materials", "#dashboard-workspace-dataset-query"), ("Choose material type", "#workspace-law-caselaw-tools"), ("Find connections", "#workspace-knowledge-graph-tools"), ("Check duties/conflicts", "#workspace-deontic-logic-tools"), ("Add notes", "#dataset-document-annotation-dashboard")])}
                <div class="section-jump-row" aria-label="First-class analysis actions">
                    <a class="primary-action is-disabled" id="dashboard-open-dataset-graph" href="#workspace-knowledge-graph-tools" aria-disabled="true">Find connections</a>
                    <a class="secondary-action is-disabled" id="dashboard-run-deontic-check" href="#workspace-deontic-logic-tools" aria-disabled="true">Check duties and conflicts</a>
                </div>
                <div class="workspace-flow-status" id="workspace-dataset-flow-status" aria-label="Workspace dataset workflow status">
                    <div><span>Step 1</span><strong id="workspace-flow-dataset-readiness">Materials not loaded</strong></div>
                    <div><span>Step 2</span><strong id="workspace-flow-lane-readiness">Choose material type</strong></div>
                    <div><span>Step 3</span><strong id="workspace-flow-graph-readiness">Connections not ready</strong></div>
                    <div><span>Next action</span><strong id="workspace-flow-next-action">Load or add materials</strong></div>
                </div>
	                <div class="workspace-empty-state" id="workspace-materials-empty-state">
	                    <h3>No materials are loaded yet</h3>
	                    <p>Add or load documents, messages, rules, or court cases before searching or checking legal duties. If you are not sure what to add, start with evidence such as emails, notices, PDFs, photos, messages, or testimony.</p>
                    <div class="button-row">
                        <a class="primary-action" href="#chat-upload-dashboard">Add evidence files</a>
                        <a class="secondary-action" href="#dashboard-workspace-dataset-path">Load saved materials</a>
                    </div>
                    <div class="workspace-checklist" aria-label="Material organization checklist">
                        <div><span>1</span><p><strong>Load or add materials.</strong> Bring in evidence, laws, court cases, or proof notes.</p></div>
                        <div><span>2</span><p><strong>Choose material type.</strong> Pick the category you want to work with first.</p></div>
                        <div><span>3</span><p><strong>Search and organize.</strong> Find the records that support or challenge the complaint.</p></div>
                        <div><span>4</span><p><strong>Check duties and conflicts.</strong> Look for requirements, permissions, prohibitions, and contradictions.</p></div>
                        <div><span>5</span><p><strong>Send to review or draft.</strong> Use the organized record to check proof gaps or build a draft.</p></div>
	                    </div>
	                </div>
	                <div class="workspace-next-action-panel" id="workspace-materials-next-action-panel" aria-label="Materials next safe action">
	                    <div>
	                        <div class="eyebrow" style="color: var(--accent);">Next Safe Action</div>
	                        <h3 id="workspace-materials-next-action-title">Add evidence files</h3>
	                        <p id="workspace-materials-next-action-reason">Add documents or choose a saved materials file before searching, finding connections, or checking duties.</p>
	                    </div>
	                    <div class="button-row">
	                        <a class="primary-action" id="workspace-materials-next-action-link" href="#chat-upload-dashboard">Add evidence files</a>
	                    </div>
	                </div>
	                <div class="preflight-hint" id="workspace-action-preflight">Load or add materials and choose a material type before finding connections or checking duties.</div>
                <p class="lane-help">Choose what kind of material you want to work with first. This changes the filters used for search, connection checks, and duty/conflict checks.</p>
                <div class="lane-grid" id="workspace-lane-cards" role="radiogroup" aria-label="Workspace evidence law and caselaw lanes">
                    <article class="lane-card" id="workspace-lane-evidence" role="radio" tabindex="0" aria-checked="false" data-lane-source-type="evidence">
                        <strong>Evidence</strong>
                        <p>Documents, emails, photos, notices, messages, PDFs, and testimony.</p>
                        <span class="lane-status" id="workspace-lane-evidence-status">not selected</span>
                    </article>
                    <article class="lane-card" id="workspace-lane-law" role="radio" tabindex="0" aria-checked="false" data-lane-source-type="legal_authority">
                        <strong>Rules and laws</strong>
                        <p>Statutes, regulations, policies, agency rules, ordinances, and standards.</p>
                        <span class="lane-status" id="workspace-lane-law-status">not selected</span>
                    </article>
                    <article class="lane-card" id="workspace-lane-caselaw" role="radio" tabindex="0" aria-checked="false" data-lane-source-type="caselaw">
                        <strong>Court cases</strong>
                        <p>Past court decisions, opinions, holdings, and precedent that may support or limit an argument.</p>
                        <span class="lane-status" id="workspace-lane-caselaw-status">not selected</span>
                    </article>
	                    <article class="lane-card" id="workspace-lane-claim-support" role="radio" tabindex="0" aria-checked="false" data-lane-source-type="claim_support">
	                        <strong>Proof checklist</strong>
	                        <p>Missing facts and claim elements to review before drafting.</p>
	                        <span class="lane-status" id="workspace-lane-claim-support-status">not selected</span>
	                    </article>
                </div>
	                <div class="lane-summary" id="workspace-lane-summary">No material type selected.</div>
	                <section class="dataset-step" id="workspace-dataset-step-load">
	                    <h3 id="workspace-step-load-title">Step 1: Load or add materials</h3>
	                    <span class="dataset-step-status" id="workspace-dataset-load-state">Not loaded</span>
	                    <div class="workspace-path-status" id="workspace-materials-path-status">
	                        <strong id="workspace-materials-path-title">No saved materials file selected</strong>
	                        <span id="workspace-materials-path-detail">Upload evidence files, or paste the path to a saved workspace materials file.</span>
	                    </div>
	                    <div class="workspace-step-actions" aria-label="Load materials actions">
	                        <a class="primary-action" href="#chat-upload-dashboard">Upload evidence files</a>
	                        <button id="dashboard-load-workspace-dataset-step1" type="button" class="secondary">Open saved file</button>
	                    </div>
	                    <label class="field-label" for="dashboard-workspace-dataset-path">Saved materials file</label>
	                    <input id="dashboard-workspace-dataset-path" type="text" value="{escape(default_workspace_dataset_path)}" placeholder="Paste saved file path">
	                    <p class="field-helper">Use this only if you already have a saved workspace materials file.</p>
	                </section>
                <section class="dataset-step" id="workspace-dataset-step-filter">
                    <h3>Step 2: Choose material type and search filters</h3>
	                    <span class="dataset-step-status" id="workspace-dataset-filter-state">Choose one material type so search and checks use the right records.</span>
                <div class="modal-grid" id="workspace-law-caselaw-tools">
	                    <div>
	                        <label class="field-label" for="dashboard-workspace-dataset-input-type">Saved material format</label>
	                        <select id="dashboard-workspace-dataset-input-type">
	                            <option value="single" selected>One saved materials file</option>
	                            <option value="packaged">Saved package folder</option>
	                            <option value="json">Source JSON file</option>
	                        </select>
	                    </div>
                    <div>
                        <label class="field-label" for="dashboard-workspace-dataset-query">Words to search for</label>
                        <input id="dashboard-workspace-dataset-query" type="text" placeholder="accommodation, retaliation, notice">
                    </div>
                    <div>
	                        <label class="field-label" for="dashboard-workspace-dataset-claim-type">Claim type</label>
	                        <input id="dashboard-workspace-dataset-claim-type" type="text" placeholder="Housing discrimination">
	                    </div>
                    <div>
                        <label class="field-label" for="dashboard-workspace-dataset-document-type">Document Type</label>
                        <input id="dashboard-workspace-dataset-document-type" type="text" placeholder="email, pdf, notice">
                    </div>
	                    <div class="advanced-filter-field">
	                        <label class="field-label" for="dashboard-workspace-dataset-source-type">Advanced material filter</label>
	                        <select id="dashboard-workspace-dataset-source-type">
	                            <option value="">Use selected material card</option>
	                            <option value="evidence">Evidence</option>
	                            <option value="legal_authority">Rules and laws</option>
	                            <option value="caselaw">Court cases</option>
	                            <option value="claim_support">Proof checklist</option>
	                            <option value="gmail">Gmail / mailbox</option>
	                            <option value="docket">Docket</option>
	                        </select>
	                        <p class="field-helper">The cards above are the main way to choose what you are working with.</p>
	                    </div>
	                </div>
	                </section>
                <section class="dataset-step" id="workspace-dataset-step-run">
                    <h3>Step 3: Search, find connections, or check duties</h3>
                    <span class="dataset-step-status" id="workspace-dataset-run-state">Load materials, then search or check connections and duties.</span>
                <div class="button-row" style="margin-top: 12px;">
                    <button id="dashboard-load-workspace-dataset" type="button">Load Saved Materials</button>
                    <button id="dashboard-search-workspace-dataset" type="button" class="secondary">Search Materials</button>
                </div>
                <div class="modal-grid" id="workspace-knowledge-graph-tools" style="margin-top: 14px;">
                    <div>
                        <label class="field-label" for="dashboard-workspace-graph-query">Graph / Logic Query</label>
                        <input id="dashboard-workspace-graph-query" type="text" placeholder="HACC, accommodation, family, agent">
                    </div>
                    <div>
                        <label class="field-label" for="dashboard-workspace-graph-relationship-type">Relationship Type</label>
                        <input id="dashboard-workspace-graph-relationship-type" type="text" placeholder="CONTAINS_DOCUMENT, IMPOSES_NORM">
                    </div>
                    <div>
                        <label class="field-label" for="dashboard-workspace-graph-document-id">Document ID</label>
                        <input id="dashboard-workspace-graph-document-id" type="text" placeholder="Optional document id">
                    </div>
                    <div id="workspace-deontic-logic-tools">
                        <label class="field-label" for="dashboard-workspace-graph-modality">Allowed / Required / Prohibited</label>
                        <select id="dashboard-workspace-graph-modality">
                            <option value="">All modalities</option>
                            <option value="allowed">Allowed</option>
                            <option value="required">Required</option>
                            <option value="prohibited">Prohibited</option>
                            <option value="conditional">Conditional</option>
                        </select>
                    </div>
                    <div>
                        <label class="field-label" for="dashboard-workspace-graph-limit">Explorer Limit</label>
                        <input id="dashboard-workspace-graph-limit" type="text" value="60" placeholder="60">
                    </div>
                </div>
                <div class="preset-row" aria-label="Connection and duty check presets">
                    <button class="preset-button" type="button" data-dashboard-graph-preset data-graph-query="" data-graph-relationship="" data-graph-modality="required">What was required?</button>
                    <button class="preset-button" type="button" data-dashboard-graph-preset data-graph-query="" data-graph-relationship="" data-graph-modality="prohibited">What was prohibited?</button>
                    <button class="preset-button" type="button" data-dashboard-graph-preset data-graph-query="notice accommodation retaliation" data-graph-relationship="IMPOSES_NORM" data-graph-modality="">Which facts impose duties?</button>
                    <button class="preset-button" type="button" data-dashboard-graph-preset data-graph-query="conflict exception condition" data-graph-relationship="" data-graph-modality="conditional">Find conditions and conflicts</button>
                    <button class="preset-button" type="button" data-dashboard-graph-preset data-graph-query="document evidence support" data-graph-relationship="SUPPORTS" data-graph-modality="">Find supporting documents</button>
                </div>
                <div class="button-row" style="margin-top: 12px;">
                    <button id="dashboard-load-workspace-graph" type="button" class="secondary">Find Connections and Duties</button>
                </div>
                </section>
                <div class="stat-grid">
                    <div class="stat-card"><strong id="dashboard-workspace-dataset-documents">0</strong><span>Workspace documents</span></div>
                    <div class="stat-card"><strong id="dashboard-workspace-dataset-collections">0</strong><span>Collections</span></div>
                    <div class="stat-card"><strong id="dashboard-workspace-dataset-results">0</strong><span>Search results</span></div>
                    <div class="stat-card"><strong id="dashboard-workspace-dataset-entities">0</strong><span>Graph entities</span></div>
                    <div class="stat-card"><strong id="dashboard-workspace-dataset-relationships">0</strong><span>Graph relationships</span></div>
                    <div class="stat-card"><strong id="dashboard-workspace-dataset-vectors">0</strong><span>Vector documents</span></div>
                    <div class="stat-card"><strong id="dashboard-workspace-dataset-logic">0</strong><span>Logic statements</span></div>
                    <div class="stat-card"><strong id="dashboard-workspace-dataset-proofs">0</strong><span>Theorem proofs</span></div>
                    <div class="stat-card"><strong id="dashboard-workspace-graph-matches">0</strong><span>Matched graph edges</span></div>
                    <div class="stat-card"><strong id="dashboard-workspace-flow-statements">0</strong><span>Flow statements</span></div>
                    <div class="stat-card"><strong id="dashboard-workspace-flow-events">0</strong><span>Governed events</span></div>
                    <div class="stat-card"><strong id="dashboard-workspace-flow-prohibited">0</strong><span>Prohibited rows</span></div>
                    <div class="stat-card"><strong id="dashboard-workspace-flow-conflicts">0</strong><span>Logic conflicts</span></div>
                    <div class="stat-card"><strong id="dashboard-workspace-flow-tdfol">0</strong><span>TDFOL formulas</span></div>
                    <div class="stat-card"><strong id="dashboard-workspace-flow-dcec">0</strong><span>DCEC formulas</span></div>
                    <div class="stat-card"><strong id="dashboard-workspace-flow-zkp">0</strong><span>ZK certificates</span></div>
                </div>
                <div class="chip-row" style="margin-top: 14px;">
                    <span class="chip" id="dashboard-workspace-dataset-workspace-chip">workspace: waiting</span>
                    <span class="chip" id="dashboard-workspace-dataset-source-chip">source: waiting</span>
                </div>
                <div class="status-line" id="dashboard-workspace-dataset-status">Add or load saved materials before searching this complaint record.</div>
                <pre id="dashboard-workspace-dataset-preview">Saved material details will appear here.</pre>
                <div class="status-line" id="dashboard-workspace-graph-status">Load materials first, then find connections and check duties or conflicts.</div>
                <pre id="dashboard-workspace-graph-preview">Connection and duty-check details will appear here.</pre>
            </article>

            <article class="dashboard-card" id="dataset-document-annotation-dashboard">
                <div class="eyebrow" style="color: var(--accent);">Save a Useful Note</div>
                <h2>Send a Filing or Document Note to the Complaint Workspace</h2>
                <p>Use this when a docket filing, evidence file, law, or court case changes what the complaint or response should say. The note becomes part of the workspace record for review and drafting.</p>
                {_render_subsection_nav("Annotation subsections", [("Review docket filings", "#docket-dataset-parquet-dashboard"), ("Organize evidence and law", "#workspace-dataset-parquet-dashboard"), ("Workspace session", "#dashboard-workspace-snapshot"), ("Proof review", "/claim-support-review")])}
                <div class="document-insight-panel" aria-label="Annotation guidance">
                    <div>
                        <div class="eyebrow" style="color: var(--accent);">What makes a useful note</div>
                        <h3>Explain what the document proves and what should happen next</h3>
                        <p>Good notes identify the filing, the fact or deadline it shows, the claim element it affects, and whether the draft, evidence list, timeline, or case chat should use it.</p>
                    </div>
                    <div class="document-insight-grid">
                        <div class="document-insight-item"><span>Step 1</span><strong>Pick the document</strong></div>
                        <div class="document-insight-item"><span>Step 2</span><strong>Choose claim impact</strong></div>
                        <div class="document-insight-item"><span>Step 3</span><strong>Save to workspace</strong></div>
                    </div>
                </div>
                <div class="selected-document-scope" id="annotation-selected-document-scope" aria-live="polite">
                    <span>Current document scope</span>
                    <strong id="annotation-selected-document-title">No document selected yet</strong>
                    <span id="annotation-selected-document-detail">Load or search filings/materials, then choose a document before saving a note or asking chat about it.</span>
                </div>
                <div class="annotation-current-task" id="annotation-current-task" aria-label="Current annotation task">
                    <div>
                        <div class="eyebrow" style="color: var(--accent);">Current Annotation Task</div>
                        <h3 id="annotation-current-task-title">Select a document first</h3>
                        <p id="annotation-current-task-detail">Choose a docket filing or workspace material so labels, notes, and chat questions attach to the right source.</p>
                    </div>
                    <a class="primary-action" id="annotation-current-task-action" href="#docket-dataset-parquet-dashboard">Review docket filings</a>
                </div>
                <div class="modal-grid">
                    <div>
                        <label class="field-label" for="dashboard-dataset-annotation-user-id">Workspace user</label>
                        <input id="dashboard-dataset-annotation-user-id" type="text" value="{escape(default_user_id)}" placeholder="dashboard-review-user">
                        <p class="field-helper">This keeps the note attached to the right saved complaint.</p>
                    </div>
                    <div>
                        <label class="field-label" for="dashboard-dataset-annotation-user-name">Reviewer name</label>
                        <input id="dashboard-dataset-annotation-user-name" type="text" placeholder="Reviewer name">
                    </div>
                    <div>
                        <label class="field-label" for="dashboard-dataset-annotation-user-role">Reviewer role</label>
                        <input id="dashboard-dataset-annotation-user-role" type="text" value="workspace reviewer" placeholder="workspace reviewer">
                    </div>
                    <div>
                        <label class="field-label" for="dashboard-dataset-annotation-document-id">Selected document</label>
                        <input id="dashboard-dataset-annotation-document-id" type="text" placeholder="Load or search a dataset to choose a document">
                        <p class="field-helper">This fills in automatically after loading or searching docket/workspace materials.</p>
                    </div>
                    <div>
                        <label class="field-label" for="dashboard-dataset-annotation-claim-element">How this affects the case</label>
                        <select id="dashboard-dataset-annotation-claim-element">
                            <option value="protected_activity">Protected activity</option>
                            <option value="employer_knowledge">Employer knowledge</option>
                            <option value="adverse_action">Adverse action</option>
                            <option value="causation" selected>Causal link</option>
                            <option value="harm">Damages</option>
                        </select>
                        <p class="field-helper">Choose the legal point this document helps prove, challenge, or explain.</p>
                    </div>
                    <div>
                        <label class="field-label" for="dashboard-dataset-annotation-title">Note title</label>
                        <input id="dashboard-dataset-annotation-title" type="text" value="Dataset document annotation">
                    </div>
                    <div>
                        <label class="field-label" for="dashboard-dataset-annotation-tags">Tags</label>
                        <input id="dashboard-dataset-annotation-tags" type="text" placeholder="causation, accommodation, hearing">
                        <p class="field-helper">Separate tags with commas, such as hearing, deadline, notice, retaliation, accommodation, service.</p>
                        <div class="label-suggestion-row" aria-label="Suggested filing labels">
                            <button type="button" data-annotation-tag="deadline">deadline</button>
                            <button type="button" data-annotation-tag="hearing">hearing</button>
                            <button type="button" data-annotation-tag="notice">notice</button>
                            <button type="button" data-annotation-tag="service issue">service issue</button>
                            <button type="button" data-annotation-tag="supports claim">supports claim</button>
                            <button type="button" data-annotation-tag="hurts claim">hurts claim</button>
                            <button type="button" data-annotation-tag="needs review">needs review</button>
                            <button type="button" data-annotation-tag="add to timeline">add to timeline</button>
                        </div>
                    </div>
                </div>
                <div style="margin-top: 14px;">
                    <label class="field-label" for="dashboard-dataset-annotation-note">What this document shows</label>
                    <textarea id="dashboard-dataset-annotation-note" placeholder="Example: This filing sets a hearing date, shows the landlord knew about the accommodation request, or creates a response deadline. Explain how the complaint or response should use it."></textarea>
                </div>
                <div class="button-row" style="margin-top: 12px;">
                    <button id="dashboard-save-dataset-annotation" type="button">Review and Save Note</button>
                    <button id="dashboard-use-loaded-document" type="button" class="secondary">Use Selected Document</button>
                    <a class="secondary-action" href="/claim-support-review">Open Proof Review</a>
                </div>
                <div class="status-line" id="dashboard-dataset-annotation-status">Load or search a dataset document before saving an annotation.</div>
                <div class="preflight-panel" id="dashboard-note-preflight-modal" aria-live="polite" hidden>
                    <div class="preflight-panel-header">
                        <div>
                            <div class="eyebrow" style="color: var(--accent);">Workspace Handoff Check</div>
                            <h3 id="dashboard-note-preflight-title">Review this note before saving</h3>
                            <p class="field-helper">These checks are advisory. You can save the note, keep editing, or ask chat about the selected filing before saving.</p>
                        </div>
                        <button type="button" class="secondary" id="dashboard-close-note-preflight-modal">Hide check</button>
                    </div>
                    <div class="preflight-summary" id="dashboard-note-preflight-summary">
                        <div><span>Selected filing</span><strong id="preflight-selected-filing">None selected</strong></div>
                        <div><span>Labels</span><strong id="preflight-labels">None</strong></div>
                        <div><span>Deadline review</span><strong id="preflight-deadline-review">No date review available</strong></div>
                        <div><span>Note summary</span><strong id="preflight-note-summary">No note entered</strong></div>
                    </div>
                    <div class="modal-actions">
                        <button id="dashboard-confirm-note-preflight" type="button">Save to Complaint Workspace</button>
                        <a class="secondary-action" id="dashboard-note-preflight-chat-link" href="/chat">Ask chat before saving</a>
                        <button type="button" class="secondary" id="dashboard-cancel-note-preflight">Keep Editing</button>
                    </div>
                </div>
                <div class="success-receipt" id="dashboard-dataset-annotation-receipt" role="status">No note has been sent yet.</div>
                <details class="technical-details">
                    <summary>Saved annotation payload</summary>
                    <pre id="dashboard-dataset-annotation-preview">The saved annotation payload will appear here.</pre>
                </details>
            </article>

            <article class="dashboard-card" id="chat-upload-dashboard">
                <div class="eyebrow" style="color: var(--accent);">Chat Card</div>
                <h2>Chat Upload Modal</h2>
                <p>Open a modal that lets intake staff or operators attach photos, videos, PDFs, mailbox exports, or notes directly into the complaint workspace evidence flow.</p>
                {_render_subsection_nav("Upload subsections", [("Intake chat", "/chat"), ("Workspace", "#dashboard-workspace-snapshot"), ("Evidence annotation", "#dataset-document-annotation-dashboard")])}
                <div class="chip-row">
                    <span class="chip">Accepts image, video, PDF, text, archive, and message files</span>
                    <span class="chip good">Uses complaint workspace evidence storage</span>
                </div>
                <div class="button-row" style="margin-top: 16px;">
                    <button id="dashboard-open-upload-modal" type="button">Open Chat Upload Modal</button>
                    <a class="modal-link" href="/chat">Open Full Chat</a>
                    <a class="modal-link" href="/workspace">Open Workspace</a>
                </div>
                <div class="status-line" id="dashboard-chat-upload-status">No upload has been submitted from the dashboard yet.</div>
                <pre id="dashboard-chat-upload-preview">The latest upload response will appear here.</pre>
            </article>

            <article class="dashboard-card" id="heads-up-display-dashboard">
                <div class="eyebrow" style="color: var(--accent);">Heads-Up Display</div>
                <h2>Heads-Up Display Dashboard</h2>
                <p>Get a front-page glance at the next legal action to perform, where to continue the case conversation, whether the workspace record is ready, and whether the docket exposes any calendar or hearing events.</p>
                {_render_subsection_nav("Heads-up subsections", [("Workspace", "#dashboard-workspace-snapshot"), ("Review", "/claim-support-review"), ("Docket", "#packaged-docket-dashboard"), ("Build draft", "/document")])}
                <div class="stat-grid">
                    <div class="stat-card"><strong id="dashboard-heads-up-action">Waiting</strong><span>Next action</span></div>
                    <div class="stat-card"><strong id="dashboard-heads-up-calendar-count">0</strong><span>Calendar events</span></div>
                    <div class="stat-card"><strong id="dashboard-heads-up-readiness">Early</strong><span>Case phase</span></div>
                </div>
                <div class="chip-row" style="margin-top: 14px;">
                    <span class="chip" id="dashboard-heads-up-claim-chip">claim: waiting</span>
                    <span class="chip" id="dashboard-heads-up-focus-chip">focus: waiting</span>
                </div>
                <div class="button-row" style="margin-top: 16px;">
                    <a class="modal-link" id="dashboard-heads-up-open-workspace" href="/workspace">Open Workspace</a>
                    <a class="modal-link" id="dashboard-heads-up-open-review" href="/claim-support-review">Open Review</a>
                    <a class="modal-link" id="dashboard-heads-up-open-chat" href="/chat">Open Case Chat</a>
                    <a class="modal-link" id="dashboard-heads-up-open-docket" href="#dashboard-docket-preview">Open Docket View</a>
                </div>
                <div class="status-line" id="dashboard-heads-up-status">Load the workspace session or docket to populate the case heads-up display.</div>
                <div style="margin-top: 14px;">
                    <div class="field-label">Operator Queue</div>
                    <div class="chip-row" id="dashboard-heads-up-queue">
                        <span class="chip">Load workspace and docket data to build the next-action queue.</span>
                    </div>
                </div>
                <pre id="dashboard-heads-up-preview">Heads-up summary, recommended action, and case-calendar cues will appear here.</pre>
            </article>
        </section>

        <section class="legacy-grid" id="legacy-ipfs-dashboard-shells">
            <section class="card">
                <h2>Complaint Generator Surfaces</h2>
                <p>Dedicated surfaces for the complaint workflow: intake chat, profile, workspace, support review, builder, and trace views.</p>
                <ul>{complaint_links}</ul>
            </section>
            <section class="card">
                <h2>ipfs_datasets_py Dashboards</h2>
                <p>Advanced package dashboards exposed through the same MCP server dashboard shell.</p>
                {ipfs_markup}
            </section>
        </section>
</main>

    <div class="modal" id="dashboard-chat-upload-modal" hidden>
        <div class="modal-panel" role="dialog" aria-modal="true" aria-labelledby="dashboard-chat-upload-title">
            <div class="modal-header">
                <div>
                    <div class="eyebrow" style="color: var(--accent);">Dashboard Intake</div>
                    <h2 id="dashboard-chat-upload-title">Chat Upload Modal</h2>
                    <p class="helper">This modal saves uploaded files into the complaint workspace evidence flow and can also attach a short narrative note tied to the same files.</p>
                </div>
                <button type="button" class="modal-close" id="dashboard-close-upload-modal">Close</button>
            </div>
            <form id="dashboard-chat-upload-form">
                <div class="modal-grid">
                    <div>
                        <label class="field-label" for="dashboard-chat-upload-user-id">Workspace User ID</label>
                        <input id="dashboard-chat-upload-user-id" name="user_id" type="text" value="{escape(default_user_id)}" placeholder="demo-user">
                    </div>
                    <div>
                        <label class="field-label" for="dashboard-chat-upload-kind">Evidence Kind</label>
                        <select id="dashboard-chat-upload-kind" name="kind">
                            <option value="document" selected>Document</option>
                            <option value="testimony">Testimony</option>
                        </select>
                    </div>
                    <div>
                        <label class="field-label" for="dashboard-chat-upload-claim-element">Claim Element</label>
                        <select id="dashboard-chat-upload-claim-element" name="claim_element_id">
                            <option value="auto">Auto-suggest from content</option>
                            <option value="protected_activity">Protected activity</option>
                            <option value="employer_knowledge">Employer knowledge</option>
                            <option value="adverse_action">Adverse action</option>
                            <option value="causation" selected>Causal link</option>
                            <option value="harm">Damages</option>
                        </select>
                    </div>
                    <div>
                        <label class="field-label" for="dashboard-chat-upload-note-title">Note Title</label>
                        <input id="dashboard-chat-upload-note-title" name="note_title" type="text" value="Chat upload note" placeholder="Chat upload note">
                    </div>
                </div>
                <div style="margin-top: 14px;">
                    <label class="field-label" for="dashboard-chat-upload-note">Narrative Note</label>
                    <textarea id="dashboard-chat-upload-note" name="note" placeholder="Add context for why these files matter to the complaint, what they show, or what follow-up is needed."></textarea>
                </div>
                <div style="margin-top: 14px;">
                    <label class="field-label" for="dashboard-chat-upload-files">Files</label>
                    <input id="dashboard-chat-upload-files" name="files" type="file" multiple accept=".jpg,.jpeg,.png,.gif,.webp,.heic,.mp4,.mov,.avi,.mkv,.pdf,.txt,.md,.json,.csv,.eml,.msg,.zip,.mbox,.mbx,.pst,.doc,.docx,.rtf,.html,.htm,.xml">
                </div>
                <div class="modal-actions">
                    <button id="dashboard-submit-upload-modal" type="submit">Upload Into Workspace</button>
                    <button type="button" class="secondary" id="dashboard-cancel-upload-modal">Cancel</button>
                </div>
            </form>
        </div>
    </div>

    <script src="/static/complaint_mcp_sdk.js"></script>
    <script>
        (function() {{
            const syncEventName = (window.ComplaintMcpSdk && window.ComplaintMcpSdk.SYNC_EVENT_NAME) || 'complaint-mcp-sync';
            const syncEventStorageKey = (window.ComplaintMcpSdk && window.ComplaintMcpSdk.DEFAULT_SYNC_EVENT_STORAGE_KEY) || 'complaintGenerator.sdkSyncEvent';
            const dashboardState = {{
	                workspacePayload: null,
                    workspaceMikeStatusUpdatedAt: null,
                    workspaceMikeRouteHint: '',
                    workspaceMikeStale: false,
                    workspaceMikeStatusContractVersion: '',
	                docketPayload: null,
	                docketViewPayload: null,
	                selectedDatasetDocument: null,
	                docketDatasetLoaded: false,
	                docketDatasetStatus: 'idle',
	                docketDatasetError: '',
	                docketDatasetCalendarEvents: [],
	                docketDatasetSearchCount: 0,
	                docketDocuments: [],
	                selectedDocketDocumentIndex: -1,
	                docketNotesSent: 0,
	                notePreflightApproved: false,
	                workspaceDatasetLoaded: false,
	                workspaceDatasetStatus: 'idle',
	                workspaceDatasetError: '',
	                workspaceGraphReady: false,
	                selectedWorkspaceLane: '',
	            }};

            function parseCount(value, fallback) {{
                const numeric = Number(value);
                return Number.isFinite(numeric) ? numeric : fallback;
            }}

            const MIKE_STATUS_STALE_MS = 5 * 60 * 1000;

            function isTimestampStale(isoValue, maxAgeMs) {{
                if (!isoValue) {{
                    return false;
                }}
                const parsed = Date.parse(String(isoValue));
                if (!Number.isFinite(parsed)) {{
                    return false;
                }}
                const ageMs = Date.now() - parsed;
                return Number.isFinite(ageMs) && ageMs > (Number(maxAgeMs) || MIKE_STATUS_STALE_MS);
            }}

            async function fetchJson(url, options) {{
                const response = await fetch(url, options || {{}});
                if (!response.ok) {{
                    const text = await response.text();
                    throw new Error(text || `Request failed with ${{response.status}}`);
                }}
                return response.json();
            }}

            function setText(id, value) {{
                const node = document.getElementById(id);
                if (node) {{
                    node.textContent = value;
                }}
            }}

            function escapeHtml(value) {{
                return String(value || '')
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#39;');
            }}

	            function setHref(id, value) {{
	                const node = document.getElementById(id);
	                if (node) {{
	                    node.href = value;
	                }}
	            }}

	            function userFacingMaterialsError(message) {{
	                const raw = String(message || '').trim();
	                if (!raw || /internal server error|request failed|500|not found|no such file|does not exist|failed/i.test(raw)) {{
	                    return 'We could not open this saved materials file. Check that the file exists, choose a different file, or upload evidence instead.';
	                }}
	                return raw;
	            }}

            function setButtonEnabled(id, enabled, reason) {{
                const node = document.getElementById(id);
                if (!node) {{
                    return;
                }}
                node.disabled = !enabled;
                node.setAttribute('aria-disabled', enabled ? 'false' : 'true');
                if (reason) {{
                    node.title = reason;
                }} else {{
                    node.removeAttribute('title');
                }}
            }}

            function setLinkEnabled(id, enabled, reason) {{
                const node = document.getElementById(id);
                if (!node) {{
                    return;
                }}
                node.classList.toggle('is-disabled', !enabled);
                node.setAttribute('aria-disabled', enabled ? 'false' : 'true');
                if (reason) {{
                    node.title = reason;
                }} else {{
                    node.removeAttribute('title');
                }}
            }}

            function selectedDocumentTitle(documentValue) {{
                const selected = documentValue && typeof documentValue === 'object' ? documentValue : dashboardState.selectedDatasetDocument;
                if (!selected) {{
                    return '';
                }}
                return String(
                    selected.title
                    || selected.source_document_title
                    || selected.document_title
                    || selected.document_id
                    || selected.id
                    || selected.row_id
                    || 'selected document'
                ).trim();
            }}

            function selectedDocumentId(documentValue) {{
                const selected = documentValue && typeof documentValue === 'object' ? documentValue : dashboardState.selectedDatasetDocument;
                if (!selected) {{
                    return '';
                }}
                return String(
                    selected.document_id
                    || selected.id
                    || selected.row_id
                    || selected.source_document_id
                    || ''
                ).trim();
            }}

            function activeDashboardUserId() {{
                return String(
                    (document.getElementById('dashboard-workspace-user-id') || {{}}).value
                    || (document.getElementById('dashboard-dataset-annotation-user-id') || {{}}).value
                    || ''
                ).trim();
            }}

            function setStageCurrent(stageName) {{
                ['intake', 'evidence', 'review', 'draft'].forEach(function(name) {{
                    const node = document.getElementById(`workflow-stage-${{name}}`);
                    if (node) {{
                        node.classList.toggle('is-current', name === stageName);
                    }}
                }});
            }}

            function setWorkflowStageState(stageName, state) {{
                const normalizedState = String(state || 'ready').trim() || 'ready';
                const node = document.getElementById(`workflow-stage-${{stageName}}`);
                const badge = document.getElementById(`workflow-stage-${{stageName}}-badge`);
                if (node) {{
                    node.dataset.state = normalizedState;
                    node.classList.toggle('is-current', normalizedState === 'current');
                }}
                if (badge) {{
                    badge.textContent = normalizedState.charAt(0).toUpperCase() + normalizedState.slice(1);
                }}
            }}

	            function setWorkflowPrimaryAction(label, href, reason) {{
	                setText('workflow-primary-action', label);
	                setHref('workflow-primary-action', href);
	                setText('mobile-workflow-primary-action', label);
	                setHref('mobile-workflow-primary-action', href);
	                setText('dashboard-recommended-action-title', label);
	                setText('dashboard-recommended-action-link', label);
	                setHref('dashboard-recommended-action-link', href);
	                setText('dashboard-recommended-action-reason', reason || 'Use this step to move the complaint record forward without skipping prerequisites.');
	                setText('current-work-title', label);
	                setText('current-work-detail', reason || 'Use this step to move the complaint record forward without skipping prerequisites.');
	                setText('current-work-primary', label);
	                setHref('current-work-primary', href);
	            }}

	            function setControlEnabled(id, enabled, reason) {{
	                const node = document.getElementById(id);
	                if (!node) {{
	                    return;
	                }}
	                node.disabled = !enabled;
	                node.setAttribute('aria-disabled', enabled ? 'false' : 'true');
	                if (reason) {{
	                    node.title = reason;
	                }} else {{
	                    node.removeAttribute('title');
	                }}
	            }}

            function updateWorkflowRail(payload) {{
                const session = payload && payload.session ? payload.session : {{}};
                const review = payload && payload.review ? payload.review : {{}};
                const overview = review && review.overview ? review.overview : {{}};
                const evidence = session && session.evidence ? session.evidence : {{}};
                const evidenceCount = parseCount((evidence.testimony || []).length, 0) + parseCount((evidence.documents || []).length, 0);
                const missingCount = parseCount(overview.missing_elements, 0);
                const hasDraft = Boolean(payload && payload.draft) || Boolean(session && session.draft);
                const userId = String(session.user_id || '').trim();
                const claimType = String(session.claim_type || '').trim();
                let stage = 'intake';
                let primaryLabel = 'Explain what happened';
	                let primaryHref = buildSurfaceUrl('/chat', {{
	                    user_id: userId,
	                    source: 'dashboard-workflow-rail',
	                    return_to: buildSurfaceUrl('/dashboards', {{ user_id: userId }}),
	                }});
	                let summary = 'Start with intake, then add evidence, laws, and court cases before review and drafting.';
	                let primaryReason = 'Begin with guided questions so the workspace has the story, people, dates, harms, and possible claims.';
	                if (userId && evidenceCount === 0) {{
	                    stage = 'evidence';
	                    primaryLabel = 'Upload evidence';
	                    primaryHref = '#chat-upload-dashboard';
	                    summary = 'The workspace is loaded. Add evidence, law, or caselaw records next.';
	                    primaryReason = 'The workspace is loaded, but it needs supporting records before review or drafting will be reliable.';
	                }} else if (userId && missingCount > 0) {{
	                    stage = 'review';
	                    primaryLabel = `Review ${{missingCount}} support gap${{missingCount === 1 ? '' : 's'}}`;
                    primaryHref = buildSurfaceUrl('/claim-support-review', {{
                        user_id: userId,
                        workspace_user_id: userId,
                        claim_type: claimType,
	                    }});
	                    summary = 'Evidence exists, but support gaps still need review before a filing-quality draft.';
	                    primaryReason = 'Some claim elements still need proof or review. Close those gaps before treating the draft as ready.';
	                }} else if (userId && (hasDraft || evidenceCount > 0)) {{
	                    stage = 'draft';
	                    primaryLabel = hasDraft ? 'Refine draft' : 'Generate complaint';
                    primaryHref = buildSurfaceUrl('/document', {{
                        user_id: userId,
                        workspace_user_id: userId,
                        claim_type: claimType,
	                    }});
	                    summary = hasDraft ? 'A draft exists. Continue refinement, validation, and export.' : 'The record is ready for a complaint draft handoff.';
	                    primaryReason = hasDraft ? 'A draft already exists, so the next safe step is refinement, validation, or export.' : 'The workspace has evidence and no loaded support gaps, so it can move into drafting.';
	                }}
	                const stageLabels = {{
	                    intake: 'Current step: Intake',
	                    evidence: 'Current step: Evidence, law, and caselaw',
	                    review: 'Current step: Review support gaps',
	                    draft: 'Current step: Draft',
	                }};
                setWorkflowStageState('intake', userId ? 'complete' : (stage === 'intake' ? 'current' : 'ready'));
                setWorkflowStageState('evidence', stage === 'evidence' ? 'current' : (evidenceCount > 0 ? 'complete' : (userId ? 'ready' : 'blocked')));
                setWorkflowStageState('review', stage === 'review' ? 'current' : (missingCount > 0 ? 'blocked' : (userId && evidenceCount > 0 ? 'complete' : 'blocked')));
                setWorkflowStageState('draft', stage === 'draft' ? 'current' : (hasDraft ? 'complete' : (missingCount > 0 || evidenceCount === 0 ? 'blocked' : 'ready')));
	                setText('current-work-stage', stageLabels[stage] || 'Current step');
                setText('workflow-rail-summary', summary);
                setText('workflow-stage-intake-status', userId ? 'Intake context is loaded.' : 'Start or continue the story.');
                setText('workflow-stage-evidence-status', evidenceCount ? `${{evidenceCount}} record${{evidenceCount === 1 ? '' : 's'}} saved.` : 'Add documents, messages, laws, or court cases.');
	                setText('workflow-stage-review-status', missingCount ? `${{missingCount}} proof item${{missingCount === 1 ? '' : 's'}} need review before drafting.` : 'No loaded proof gaps.');
	                setText('workflow-stage-draft-status', hasDraft ? 'Draft available.' : (evidenceCount === 0 ? 'Blocked until evidence is added.' : (missingCount > 0 ? 'Blocked until proof items are reviewed.' : 'Ready to build a draft.')));
	                setText('workflow-stage-review-unlock', missingCount ? 'Review required proof' : 'Open proof review');
	                setHref('workflow-stage-review-unlock', buildSurfaceUrl('/claim-support-review', {{
	                    user_id: userId,
	                    workspace_user_id: userId,
	                    claim_type: claimType,
	                }}));
	                setText('workflow-stage-draft-unlock', evidenceCount === 0 ? 'Add evidence first' : (missingCount > 0 ? 'Fix proof gaps first' : 'Build draft'));
	                setHref('workflow-stage-draft-unlock', evidenceCount === 0 ? '#chat-upload-dashboard' : (missingCount > 0 ? buildSurfaceUrl('/claim-support-review', {{
	                    user_id: userId,
	                    workspace_user_id: userId,
	                    claim_type: claimType,
	                }}) : buildSurfaceUrl('/document', {{
	                    user_id: userId,
	                    workspace_user_id: userId,
	                    claim_type: claimType,
	                }})));
	                setWorkflowPrimaryAction(primaryLabel, primaryHref, primaryReason);
	            }}

            function resetWorkflowRail() {{
                setWorkflowStageState('intake', 'current');
                setWorkflowStageState('evidence', 'ready');
                setWorkflowStageState('review', 'blocked');
                setWorkflowStageState('draft', 'blocked');
                setText('workflow-rail-summary', 'Load the workspace to align the dashboard around the next valid complaint step.');
                setText('workflow-stage-intake-status', 'Start or continue the story.');
	                setText('workflow-stage-evidence-status', 'Add documents, messages, laws, or court cases.');
	                setText('workflow-stage-review-status', 'Close support gaps before drafting.');
	                setText('workflow-stage-draft-status', 'Generate or refine the complaint.');
	                setText('workflow-stage-review-unlock', 'Review required proof');
	                setHref('workflow-stage-review-unlock', '/claim-support-review');
	                setText('workflow-stage-draft-unlock', 'Add evidence first');
	                setHref('workflow-stage-draft-unlock', '#chat-upload-dashboard');
	                setText('current-work-stage', 'Current step: Intake');
	                setWorkflowPrimaryAction('Explain what happened', '/chat', 'Begin with guided questions so the workspace has the story, people, dates, harms, and possible claims.');
	            }}

            function setWorkspaceLane(sourceType) {{
                const normalized = String(sourceType || '').trim();
                const laneBySource = {{
                    evidence: 'evidence',
                    legal_authority: 'law',
                    caselaw: 'caselaw',
                    claim_support: 'claim-support',
                }};
                const activeLane = laneBySource[normalized] || '';
                const labelByLane = {{
                    evidence: 'Evidence',
                    law: 'Rules and laws',
                    caselaw: 'Court cases',
                    'claim-support': 'Proof checklist',
                }};
                if (dashboardState.selectedWorkspaceLane !== activeLane) {{
                    dashboardState.workspaceGraphReady = false;
                }}
                dashboardState.selectedWorkspaceLane = activeLane;
                ['evidence', 'law', 'caselaw', 'claim-support'].forEach(function(name) {{
                    const card = document.getElementById(`workspace-lane-${{name}}`);
                    const status = document.getElementById(`workspace-lane-${{name}}-status`);
                    const isActive = name === activeLane;
                    if (card) {{
                        card.classList.toggle('is-selected', isActive);
                        card.setAttribute('aria-checked', isActive ? 'true' : 'false');
                    }}
                    if (status) {{
                        status.textContent = isActive ? 'selected' : 'not selected';
                    }}
                }});
                document.querySelectorAll('[data-workspace-dataset-preset]').forEach(function(button) {{
                    const buttonLane = laneBySource[String(button.dataset.datasetSourceType || '').trim()] || '';
                    button.setAttribute('aria-pressed', buttonLane && buttonLane === activeLane ? 'true' : 'false');
                }});
	                setText('workspace-lane-summary', activeLane ? `Selected material type: ${{labelByLane[activeLane] || activeLane}}` : 'No material type selected.');
	                setText('workspace-dataset-filter-state', activeLane ? `${{labelByLane[activeLane] || activeLane}} filters are selected.` : 'Choose one material type so search and checks use the right records.');
	                updateWorkspaceDatasetReadiness();
	            }}

	            function getWorkspaceDatasetPreflight() {{
	                const pathValue = String((document.getElementById('dashboard-workspace-dataset-path') || {{}}).value || '').trim();
	                const labelByLane = {{
	                    evidence: 'Evidence',
	                    law: 'Rules and laws',
	                    caselaw: 'Court cases',
	                    'claim-support': 'Proof checklist',
	                }};
	                const activeLaneLabel = dashboardState.selectedWorkspaceLane ? labelByLane[dashboardState.selectedWorkspaceLane] || dashboardState.selectedWorkspaceLane : '';
	                if (!pathValue) {{
	                    return {{
	                        canLoad: false,
	                        canSearch: false,
	                        canGraph: false,
	                        canDeontic: false,
	                        reason: 'Upload evidence files or choose a saved materials file first.',
	                        state: 'missing_path',
	                        actionLabel: 'Add evidence files',
	                        actionHref: '#chat-upload-dashboard',
	                        pathTitle: 'No saved materials file selected',
	                        pathDetail: 'Upload evidence files, or paste the path to a saved workspace materials file.',
	                    }};
	                }}
	                if (!dashboardState.workspaceDatasetLoaded) {{
	                    return {{
	                        canLoad: true,
                        canSearch: false,
	                        canGraph: false,
	                        canDeontic: false,
	                        reason: 'Open the saved materials file before searching or checking connections.',
	                        state: 'path_set_unloaded',
	                        actionLabel: activeLaneLabel ? `Open ${{activeLaneLabel.toLowerCase()}}` : 'Open saved file',
	                        actionHref: '#workspace-dataset-step-run',
	                        pathTitle: 'Saved materials file selected',
	                        pathDetail: `Path selected, not loaded: ${{pathValue}}`,
	                    }};
	                }}
	                if (!dashboardState.selectedWorkspaceLane) {{
	                    return {{
	                        canLoad: true,
                        canSearch: false,
	                        canGraph: false,
	                        canDeontic: false,
	                        reason: 'Choose whether you want to work with evidence, rules and laws, court cases, or the proof checklist.',
	                        state: 'loaded_no_lane',
	                        actionLabel: 'Choose material type',
	                        actionHref: '#workspace-lane-cards',
	                        pathTitle: 'Materials loaded',
	                        pathDetail: `Loaded from: ${{pathValue}}`,
	                    }};
	                }}
	                if (!dashboardState.workspaceGraphReady) {{
	                    return {{
	                        canLoad: true,
                        canSearch: true,
	                        canGraph: true,
	                        canDeontic: false,
	                        reason: 'Find connections before checking duties and conflicts.',
	                        state: 'loaded_lane_selected',
	                        actionLabel: 'Find connections',
	                        actionHref: '#workspace-knowledge-graph-tools',
	                        pathTitle: `${{activeLaneLabel}} loaded`,
	                        pathDetail: `Search and connection checks now use ${{activeLaneLabel.toLowerCase()}} from the selected materials file.`,
	                    }};
	                }}
	                return {{
	                    canLoad: true,
	                    canSearch: true,
	                    canGraph: true,
	                    canDeontic: true,
	                    reason: 'Ready to check duties, permissions, prohibitions, and conflicts.',
	                    state: 'graph_ready',
	                    actionLabel: 'Check duties and conflicts',
	                    actionHref: '#workspace-deontic-logic-tools',
	                    pathTitle: `${{activeLaneLabel}} ready`,
	                    pathDetail: `Connections are ready for ${{activeLaneLabel.toLowerCase()}}. You can now check duties, permissions, prohibitions, and conflicts.`,
	                }};
	            }}

            function updateWorkspaceDatasetReadiness() {{
                const labelByLane = {{
                    evidence: 'Evidence',
                    law: 'Rules and laws',
                    caselaw: 'Court cases',
                    'claim-support': 'Proof checklist',
                }};
                const loadTitleByLane = {{
                    evidence: 'Step 1: Load evidence materials',
                    law: 'Step 1: Load rules and laws',
                    caselaw: 'Step 1: Load court cases',
                    'claim-support': 'Step 1: Load proof checklist',
                }};
                const preflight = getWorkspaceDatasetPreflight();
                const activeLaneLabel = dashboardState.selectedWorkspaceLane ? labelByLane[dashboardState.selectedWorkspaceLane] || dashboardState.selectedWorkspaceLane : 'No material type selected';
                setText('workspace-flow-dataset-readiness', dashboardState.workspaceDatasetLoaded ? 'Materials loaded' : 'Materials not loaded');
                setText('workspace-flow-lane-readiness', activeLaneLabel);
                setText('workspace-flow-graph-readiness', dashboardState.workspaceGraphReady ? 'Connections ready' : 'Connections not ready');
	                setText('workspace-flow-next-action', preflight.reason);
	                setText('workspace-action-preflight', preflight.reason);
	                setText('workspace-step-load-title', loadTitleByLane[dashboardState.selectedWorkspaceLane] || 'Step 1: Load or add materials');
	                setText('workspace-materials-next-action-title', preflight.actionLabel);
	                setText('workspace-materials-next-action-link', preflight.actionLabel);
	                setHref('workspace-materials-next-action-link', preflight.actionHref || '#workspace-dataset-parquet-dashboard');
	                setText('workspace-materials-next-action-reason', preflight.reason);
	                setText('workspace-materials-path-title', preflight.pathTitle || 'Materials file status unavailable');
	                setText('workspace-materials-path-detail', preflight.pathDetail || preflight.reason);
	                const loadStateText = dashboardState.workspaceDatasetStatus === 'loading'
	                    ? 'Loading materials...'
	                    : dashboardState.workspaceDatasetStatus === 'error'
	                        ? dashboardState.workspaceDatasetError
	                        : dashboardState.workspaceDatasetLoaded
	                            ? 'Loaded successfully'
	                            : (preflight.state === 'path_set_unloaded' ? 'Path selected, not loaded' : 'Not loaded');
	                setText('workspace-dataset-load-state', loadStateText);
	                setButtonEnabled('dashboard-load-workspace-dataset', preflight.canLoad, preflight.canLoad ? '' : preflight.reason);
	                setButtonEnabled('dashboard-load-workspace-dataset-step1', preflight.canLoad, preflight.canLoad ? '' : preflight.reason);
	                setButtonEnabled('dashboard-search-workspace-dataset', preflight.canSearch, preflight.canSearch ? '' : preflight.reason);
	                setButtonEnabled('dashboard-load-workspace-graph', preflight.canGraph, preflight.canGraph ? '' : preflight.reason);
	                ['dashboard-workspace-dataset-input-type', 'dashboard-workspace-dataset-query', 'dashboard-workspace-dataset-claim-type', 'dashboard-workspace-dataset-document-type', 'dashboard-workspace-dataset-source-type'].forEach(function(id) {{
	                    setControlEnabled(id, dashboardState.workspaceDatasetLoaded, dashboardState.workspaceDatasetLoaded ? '' : 'Open a saved materials file before changing search filters.');
	                }});
	                setLinkEnabled('dashboard-open-dataset-graph', preflight.canGraph, preflight.canGraph ? '' : preflight.reason);
                setLinkEnabled('dashboard-run-deontic-check', preflight.canDeontic, preflight.canDeontic ? '' : preflight.reason);
            }}

            function getDocketDatasetPreflight() {{
                const pathValue = String((document.getElementById('dashboard-docket-dataset-path') || {{}}).value || '').trim();
                const queryValue = String((document.getElementById('dashboard-docket-dataset-query') || {{}}).value || '').trim();
                if (!pathValue) {{
                    return {{
                        canLoad: false,
                        canSearch: false,
                        canGraph: false,
                        canAnnotate: false,
                        title: 'Load case filings',
                        reason: 'Choose a saved filing set before searching, finding dates, or saving notes.',
                        loadState: 'Choose filing set',
                        searchState: 'Waiting for filings',
                        annotationState: 'Waiting for selected document',
                    }};
                }}
                if (!dashboardState.docketDatasetLoaded) {{
                    return {{
                        canLoad: true,
                        canSearch: false,
                        canGraph: false,
                        canAnnotate: false,
                        title: 'Load case filings',
                        reason: 'Open the selected filing set first. Search and connection mapping will turn on after it loads.',
                        loadState: dashboardState.docketDatasetStatus === 'loading' ? 'Loading filings...' : 'Ready to load',
                        searchState: 'Waiting for filings',
                        annotationState: 'Waiting for selected document',
                    }};
                }}
                if (!queryValue) {{
                    return {{
                        canLoad: true,
                        canSearch: true,
                        canGraph: true,
                        canAnnotate: Boolean(dashboardState.selectedDatasetDocument),
                        title: 'Search or review dates',
                        reason: 'Filings are loaded. Search for a deadline, hearing, motion, notice, order, or issue that affects the complaint or response.',
                        loadState: 'Filings loaded',
                        searchState: 'Ready for search',
                        annotationState: dashboardState.selectedDatasetDocument ? 'Document selected' : 'Choose a filing to save',
                    }};
                }}
                return {{
                    canLoad: true,
                    canSearch: true,
                    canGraph: true,
                    canAnnotate: Boolean(dashboardState.selectedDatasetDocument),
                    title: 'Search filings',
                    reason: 'Run the search, then save a note from the most useful filing into the complaint workspace.',
                    loadState: 'Filings loaded',
                    searchState: dashboardState.docketDatasetSearchCount ? `${{dashboardState.docketDatasetSearchCount}} result${{dashboardState.docketDatasetSearchCount === 1 ? '' : 's'}} found` : 'Ready for search',
                    annotationState: dashboardState.selectedDatasetDocument ? 'Ready to save note' : 'Waiting for selected filing',
                }};
            }}

            function updateDocketDatasetReadiness() {{
                const preflight = getDocketDatasetPreflight();
                setText('docket-next-action-title', preflight.title);
                setText('docket-next-action-reason', preflight.reason);
                setText('docket-flow-load-state', preflight.loadState);
                setText('docket-flow-search-state', preflight.searchState);
                setText('docket-flow-annotation-state', preflight.annotationState);
                setButtonEnabled('dashboard-load-docket-dataset', preflight.canLoad, preflight.canLoad ? '' : preflight.reason);
                setButtonEnabled('dashboard-search-docket-dataset', preflight.canSearch, preflight.canSearch ? '' : preflight.reason);
                setButtonEnabled('dashboard-load-docket-dataset-graph', preflight.canGraph, preflight.canGraph ? '' : preflight.reason);
                setLinkEnabled('docket-next-annotation-link', preflight.canAnnotate, preflight.canAnnotate ? '' : 'Load or search filings before saving a note.');
                setLinkEnabled('docket-save-selected-document-link', preflight.canAnnotate, preflight.canAnnotate ? '' : 'Load or search filings before saving a note.');
            }}

            function updateDocketSummaryStrip(documentCount, calendarEvents) {{
                const events = Array.isArray(calendarEvents) ? calendarEvents : dashboardState.docketDatasetCalendarEvents || [];
                const selected = dashboardState.selectedDatasetDocument || null;
                const selectedTitle = selected ? String(selected.title || selected.source_document_title || selected.document_title || selected.document_id || selected.id || 'selected filing') : '';
                setText('docket-summary-filings', String(Number(documentCount || dashboardState.docketDocuments.length || 0)));
                setText('docket-summary-dates', String(events.length || 0));
                setText('docket-summary-selected', selectedTitle ? (selectedTitle.length > 34 ? `${{selectedTitle.slice(0, 31)}}...` : selectedTitle) : 'none yet');
                setText('docket-summary-notes', String(dashboardState.docketNotesSent || 0));
                updateDeadlineRiskSummary(events);
                updateDocketCurrentTask();
            }}

            function deadlineRiskBuckets(events) {{
                const buckets = {{ overdue: 0, dueSoon: 0, upcoming: 0, unparsed: 0 }};
                const now = new Date();
                const dayMs = 24 * 60 * 60 * 1000;
                (Array.isArray(events) ? events : []).forEach(function(event) {{
                    const parsed = normalizeEventDate(event);
                    if (!parsed) {{
                        buckets.unparsed += 1;
                        return;
                    }}
                    const diffDays = Math.ceil((parsed.getTime() - now.getTime()) / dayMs);
                    if (diffDays < 0) {{
                        buckets.overdue += 1;
                    }} else if (diffDays <= 7) {{
                        buckets.dueSoon += 1;
                    }} else {{
                        buckets.upcoming += 1;
                    }}
                }});
                return buckets;
            }}

            function updateDeadlineRiskSummary(events) {{
                const buckets = deadlineRiskBuckets(events || dashboardState.docketDatasetCalendarEvents || []);
                setText('docket-deadline-overdue', String(buckets.overdue));
                setText('docket-deadline-due-soon', String(buckets.dueSoon));
                setText('docket-deadline-upcoming', String(buckets.upcoming));
                setText('docket-deadline-unparsed', String(buckets.unparsed));
            }}

            function currentAnnotationTags() {{
                return String((document.getElementById('dashboard-dataset-annotation-tags') || {{}}).value || '')
                    .split(/[,;\\n]+/)
                    .map((tag) => tag.trim())
                    .filter(Boolean);
            }}

            function updateDocketCurrentTask() {{
                const selected = dashboardState.selectedDatasetDocument || null;
                const note = String((document.getElementById('dashboard-dataset-annotation-note') || {{}}).value || '').trim();
                const tags = currentAnnotationTags();
                let title = 'Load filings';
                let detail = 'Open the saved docket package, then select one filing before labels, notes, or workspace handoff.';
                let href = '#dashboard-docket-dataset-path';
                let label = 'Load filings';
                if (dashboardState.docketDatasetLoaded && !selected) {{
                    title = 'Select a filing';
                    detail = 'Choose one filing from the list so searches, labels, and notes attach to the right document.';
                    href = '#docket-filing-workspace';
                    label = 'Select filing';
                }} else if (selected && !tags.length) {{
                    title = 'Add labels';
                    detail = 'Classify this filing with labels such as deadline, hearing, notice, or needs review.';
                    href = '#dashboard-dataset-annotation-tags';
                    label = 'Add labels';
                }} else if (selected && !note) {{
                    title = 'Write legal-impact note';
                    detail = 'Explain what this filing changes about the complaint, response, deadline, or proof record.';
                    href = '#dashboard-dataset-annotation-note';
                    label = 'Write note';
                }} else if (selected && note) {{
                    title = 'Review and save note';
                    detail = 'Use the preflight check before saving this filing insight into the complaint workspace.';
                    href = '#dataset-document-annotation-dashboard';
                    label = 'Review handoff';
                }}
                setText('docket-current-task-title', title);
                setText('docket-current-task-detail', detail);
                setText('docket-current-task-action', label);
                setHref('docket-current-task-action', href);
                updateAnnotationTaskState();
            }}

            function updateDocumentContextBar() {{
                const selected = dashboardState.selectedDatasetDocument || null;
                const title = selectedDocumentTitle(selected);
                const id = selectedDocumentId(selected);
                const datasetKind = String(selected && selected.dataset_kind || 'document').trim();
                const userId = activeDashboardUserId();
                const selectedContext = selected ? JSON.stringify(buildDocketChatContext(selected, userId, 'dashboard-selected-document-context')) : '';
                const selectedChatHref = selected ? buildSurfaceUrl('/chat', {{
                    user_id: userId,
                    source: 'dashboard-selected-document-context',
                    prefill_message: title
                        ? `Help me label and analyze this selected filing or document: ${{title}}`
                        : 'Help me label and analyze this selected filing or document.',
                    return_to: buildSurfaceUrl('/dashboards', {{ user_id: userId }}),
                    chat_context: selectedContext,
                }}) : '/chat';
                setText('context-selected-document', title ? (title.length > 42 ? `${{title.slice(0, 39)}}...` : title) : 'none selected');
                setText('context-router-mode', selected ? 'document Q&A ready' : 'general intake');
                setText('context-selected-document-hint', selected ? 'Change selection' : 'Select a filing');
                setHref('context-selected-document-hint', selected ? '#docket-filing-workspace' : '#docket-dataset-parquet-dashboard');
                setHref('context-router-hint', selectedChatHref);
                setHref('context-open-selected-chat', selectedChatHref);
                setHref('current-work-secondary', selectedChatHref);
                setText('current-work-secondary', selected ? 'Ask about selected filing' : 'Ask about selected filing');
                setText('current-work-selected-document', title ? `Selected: ${{title.length > 54 ? title.slice(0, 51) + '...' : title}}` : 'No document selected');
                setText('current-work-router-status', selected ? 'Document context will be sent to chat router' : 'Chat uses general intake context');
                setText('current-work-prerequisite', selected ? 'Ready for document Q&A and annotation' : 'Select a filing to enable document-aware chat');
                setLinkEnabled('context-open-selected-chat', Boolean(selected), selected ? '' : 'Select a filing or document before asking chat about it.');
                setLinkEnabled('current-work-secondary', Boolean(selected), selected ? '' : 'Select a filing or document before asking chat about it.');
                const selectedCard = document.getElementById('context-selected-document-card');
                if (selectedCard) {{
                    selectedCard.classList.toggle('is-active', Boolean(selected));
                    selectedCard.classList.toggle('is-warning', !selected);
                }}
                const routerCard = document.getElementById('context-router-card');
                if (routerCard) {{
                    routerCard.classList.toggle('is-active', Boolean(selected));
                }}
                const selectedPill = document.getElementById('current-work-selected-document');
                if (selectedPill) {{
                    selectedPill.classList.toggle('is-ready', Boolean(selected));
                    selectedPill.classList.toggle('is-warning', !selected);
                }}
                const routerPill = document.getElementById('current-work-router-status');
                if (routerPill) {{
                    routerPill.classList.toggle('is-ready', Boolean(selected));
                }}
                const prerequisitePill = document.getElementById('current-work-prerequisite');
                if (prerequisitePill) {{
                    prerequisitePill.classList.toggle('is-ready', Boolean(selected));
                    prerequisitePill.classList.toggle('is-warning', !selected);
                }}
                setText('annotation-selected-document-title', title || 'No document selected yet');
                setText(
                    'annotation-selected-document-detail',
                    selected
                        ? `${{titleCase(datasetKind, 'Document')}} ${{id ? '(' + id + ')' : ''}} is the active source for labels, notes, and document-aware chat.`
                        : 'Load or search filings/materials, then choose a document before saving a note or asking chat about it.'
                );
                setLinkEnabled('docket-banner-chat-link', Boolean(selected), selected ? '' : 'Select a filing before asking chat about it.');
                setLinkEnabled('docket-open-chat-about-document', Boolean(selected), selected ? '' : 'Select a filing before asking chat about it.');
                setLinkEnabled('dashboard-note-preflight-chat-link', Boolean(selected), selected ? '' : 'Select a filing before asking chat about it.');
            }}

            function updateAnnotationTaskState() {{
                const selected = dashboardState.selectedDatasetDocument || null;
                const tags = currentAnnotationTags();
                const note = String((document.getElementById('dashboard-dataset-annotation-note') || {{}}).value || '').trim();
                let title = 'Select a document first';
                let detail = 'Choose a docket filing or workspace material so labels, notes, and chat questions attach to the right source.';
                let href = '#docket-dataset-parquet-dashboard';
                let label = 'Review docket filings';
                if (selected && !tags.length) {{
                    title = 'Add labels to this document';
                    detail = 'Use short labels such as deadline, hearing, notice, contradiction, supports claim, or needs review.';
                    href = '#dashboard-dataset-annotation-tags';
                    label = 'Add labels';
                }} else if (selected && !note) {{
                    title = 'Write what this document shows';
                    detail = 'Explain the legal impact in plain language before saving it into the complaint workspace.';
                    href = '#dashboard-dataset-annotation-note';
                    label = 'Write note';
                }} else if (selected && note) {{
                    title = 'Review and save this note';
                    detail = 'Run the handoff check, then save the document insight into the complaint workspace.';
                    href = '#dashboard-save-dataset-annotation';
                    label = 'Review and save note';
                }}
                setText('annotation-current-task-title', title);
                setText('annotation-current-task-detail', detail);
                setText('annotation-current-task-action', label);
                setHref('annotation-current-task-action', href);
                updateDocumentContextBar();
            }}

	            function collapseMobileSectionMenu() {{
	                const menu = document.getElementById('dashboard-section-menu');
	                if (!menu || !window.matchMedia) {{
	                    return;
	                }}
                if (window.matchMedia('(max-width: 640px)').matches) {{
                    menu.removeAttribute('open');
                }} else {{
	                    menu.setAttribute('open', 'open');
	                }}
	            }}

	            function collapseMobileSectionMenuAfterChoice() {{
	                const menu = document.getElementById('dashboard-section-menu');
	                if (menu && window.matchMedia && window.matchMedia('(max-width: 640px)').matches) {{
	                    menu.removeAttribute('open');
	                }}
	            }}

	            function handleWorkspaceMaterialsNextAction(event) {{
	                const preflight = getWorkspaceDatasetPreflight();
	                if (preflight.state === 'path_set_unloaded') {{
	                    event.preventDefault();
	                    loadWorkspaceDatasetDashboard('view');
	                }} else if (preflight.state === 'loaded_lane_selected') {{
	                    event.preventDefault();
	                    loadWorkspaceGraphExplorer();
	                }}
	            }}

	            function renderChipList(id, values, fallback) {{
                const node = document.getElementById(id);
                if (!node) {{
                    return;
                }}
                const items = Array.isArray(values) ? values.filter(Boolean) : [];
                const chips = items.length ? items : [fallback];
                node.innerHTML = chips.map((item) => `<span class="chip">${{String(item)}}</span>`).join('');
            }}

            function publishSharedSyncEvent(detail) {{
                if (window.ComplaintMcpSdk && typeof window.ComplaintMcpSdk.publishSyncEvent === 'function') {{
                    return window.ComplaintMcpSdk.publishSyncEvent(detail);
                }}
                const payload = Object.assign({{
                    emitted_at: new Date().toISOString(),
                }}, detail || {{}});
                if (typeof window.localStorage !== 'undefined') {{
                    try {{
                        window.localStorage.setItem(syncEventStorageKey, JSON.stringify(payload));
                    }} catch (error) {{
                        // Ignore storage failures and still dispatch the event locally.
                    }}
                }}
                if (typeof window.dispatchEvent === 'function' && typeof CustomEvent === 'function') {{
                    window.dispatchEvent(new CustomEvent(syncEventName, {{ detail: payload }}));
                }}
                return payload;
            }}

	            function buildSurfaceUrl(path, params) {{
	                const query = new URLSearchParams();
	                Object.entries(params || {{}}).forEach(([key, value]) => {{
	                    if (value === null || value === undefined || value === '') {{
	                        return;
                    }}
                    query.set(key, String(value));
                }});
	                const serialized = query.toString();
	                return serialized ? `${{path}}?${{serialized}}` : path;
	            }}

	            function buildDocketChatContext(selected, userId, sourceSurface) {{
	                const filing = selected && typeof selected === 'object' ? selected : {{}};
	                const id = String(
	                    filing.document_id
	                    || filing.id
	                    || filing.row_id
	                    || filing.source_document_id
	                    || ''
	                ).trim();
	                const title = String(
	                    filing.title
	                    || filing.source_document_title
	                    || filing.document_title
	                    || id
	                    || ''
	                ).trim();
	                const text = String(filing.text || filing.snippet || filing.preview || filing.summary || '').trim();
	                const labels = filingLabelsForDocument(filing);
	                const dates = extractDatesFromText(`${{title}} ${{text}}`);
	                return {{
	                    kind: 'selected-docket-filing',
	                    source_surface: sourceSurface || 'dashboard-docket',
	                    user_id: userId || '',
	                    router_mode: 'llm_router or multimodal_router, depending on available filing text and page images',
	                    status: 'Selected filing context attached for case chat.',
	                    filing: {{
	                        id,
	                        title,
	                        date: dates.length ? dates[0] : String(filing.date_filed || '').trim(),
	                        use: classifyDocumentUse(filing),
	                    }},
	                    labels,
	                    excerpt: summarizeDocumentText(filing),
	                }};
	            }}

            function titleCase(value, fallback) {{
                const text = String(value || '').trim();
                if (!text) {{
                    return fallback;
                }}
                return text
                    .replace(/_/g, ' ')
                    .split(/\\s+/)
                    .filter(Boolean)
                    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
                    .join(' ');
            }}

            function extractDatesFromText(text) {{
                const raw = String(text || '');
                const datePattern = /\b(?:\d{{1,2}}\/\d{{1,2}}\/\d{{2,4}}|[A-Z][a-z]+ \d{{1,2}}, \d{{4}}|\d{{4}}-\d{{2}}-\d{{2}})\b/g;
                return Array.from(new Set((raw.match(datePattern) || []).map((value) => String(value).trim()).filter(Boolean)));
            }}

            function summarizeDocumentText(document) {{
                if (!document || typeof document !== 'object') {{
                    return 'No filing is selected yet. Load or search filings to choose a document.';
                }}
                const text = String(document.text || document.snippet || document.preview || document.summary || '').replace(/\s+/g, ' ').trim();
                if (text) {{
                    return text.length > 240 ? `${{text.slice(0, 237)}}...` : text;
                }}
                const title = String(document.title || document.source_document_title || document.document_title || '').trim();
                return title ? `Selected filing: ${{title}}. Add a note explaining why it matters to the complaint or response.` : 'Selected filing loaded. Add a note explaining why it matters to the complaint or response.';
            }}

            function classifyDocumentUse(document) {{
                const combined = String(
                    [
                        document && document.title,
                        document && document.source_document_title,
                        document && document.document_title,
                        document && document.text,
                        document && document.snippet,
                    ].filter(Boolean).join(' ')
                ).toLowerCase();
                if (/hearing|trial|conference|court date/.test(combined)) {{
                    return 'Add to timeline and prepare for scheduled event';
                }}
                if (/deadline|due|answer|response/.test(combined)) {{
                    return 'Check response deadline and add to timeline';
                }}
                if (/notice|summons|service/.test(combined)) {{
                    return 'Review notice or service issue';
                }}
                if (/order|judgment|dismiss/.test(combined)) {{
                    return 'Review order impact on complaint or response';
                }}
                return 'Save legal impact note for review or drafting';
            }}

            function filingLabelsForDocument(document) {{
                const text = String([
                    document && document.title,
                    document && document.source_document_title,
                    document && document.document_title,
                    document && document.text,
                    document && document.snippet,
                    document && document.preview,
                ].filter(Boolean).join(' ')).toLowerCase();
                const labels = [];
                if (/hearing|trial|conference|court date/.test(text)) {{
                    labels.push('hearing');
                }}
                if (/deadline|due|answer|response/.test(text)) {{
                    labels.push('deadline');
                }}
                if (/notice|summons|service/.test(text)) {{
                    labels.push('notice');
                }}
                if (/order|judgment|dismiss/.test(text)) {{
                    labels.push('order');
                }}
                if (/eviction|possession|tenant|landlord/.test(text)) {{
                    labels.push('eviction');
                }}
                if (/accommodation|retaliation|discrimination|causation/.test(text)) {{
                    labels.push('claim issue');
                }}
                if (!labels.length) {{
                    labels.push('needs review');
                }}
                return Array.from(new Set(labels)).slice(0, 4);
            }}

            function normalizeDocketDocument(document, index) {{
                const raw = document && typeof document === 'object' ? document : {{}};
                const metadata = raw.metadata || {{}};
                const classification = metadata.classification || {{}};
                const id = String(raw.document_id || raw.id || raw.row_id || raw.source_document_id || metadata.document_id || metadata.id || `filing-${{index + 1}}`).trim();
                const title = String(raw.title || raw.source_document_title || raw.document_title || raw.name || id || `Filing ${{index + 1}}`).trim();
                const text = String(raw.text || raw.snippet || raw.preview || raw.summary || '').trim();
                const dates = extractDatesFromText(`${{title}} ${{text}}`);
                const filed = String(raw.date_filed || raw.filing_date || metadata.date_filed || metadata.filing_date || dates[0] || '').trim();
                const documentType = String(raw.document_type || metadata.document_type || classification.label || 'filing').replace(/_/g, ' ');
                return Object.assign({{}}, raw, {{
                    document_id: id,
                    id,
                    title,
                    text,
                    date_filed: filed,
                    document_type: documentType,
                    docket_labels: filingLabelsForDocument(raw),
                    detected_dates: dates,
                    dataset_kind: raw.dataset_kind || 'docket',
                }});
            }}

            function documentsFromDocketPayload(payload, label) {{
                const documents = Array.isArray(payload && payload.documents) ? payload.documents : [];
                const searchResults = (payload && payload.search_results) || {{}};
                const results = Array.isArray(searchResults.results) ? searchResults.results : [];
                const source = label === 'search' && results.length ? results : documents;
                return source.map((item, index) => {{
                    const normalized = normalizeDocketDocument(item, index);
                    if (label === 'search') {{
                        normalized.search_rank = index + 1;
                        normalized.search_score = item && (item.score || item.rank_score || item.bm25_score || '');
                    }}
                    return normalized;
                }});
            }}

            function renderDocketFilingList(documents) {{
                const node = document.getElementById('docket-filing-list');
                if (!node) {{
                    return;
                }}
                const items = Array.isArray(documents) ? documents : [];
                if (!items.length) {{
                    node.innerHTML = `
                        <div class="workspace-empty-state" id="docket-filing-empty-state">
                            <h3>No filings loaded yet</h3>
                            <p>Load case filings to see a selectable filing list with dates, labels, and review status.</p>
                        </div>
                    `;
                    return;
                }}
                node.innerHTML = items.map((document, index) => {{
                    const title = String(document.title || document.document_id || `Filing ${{index + 1}}`);
                    const dateText = String(document.date_filed || (document.detected_dates || [])[0] || 'date not found');
                    const typeText = titleCase(document.document_type || 'filing', 'Filing');
                    const labels = Array.isArray(document.docket_labels) ? document.docket_labels : filingLabelsForDocument(document);
                    const labelHtml = labels.map((label) => `<span class="filing-label${{/deadline|hearing/i.test(label) ? ' is-urgent' : ''}}">${{escapeHtml(label)}}</span>`).join('');
                    const isSelected = index === dashboardState.selectedDocketDocumentIndex;
                    return `
                        <div class="filing-row${{isSelected ? ' is-selected' : ''}}" role="listitem" data-docket-document-index="${{index}}">
                            <div>
                                <span class="filing-title">${{escapeHtml(title)}}</span>
                                <span class="filing-meta">${{escapeHtml(typeText)}}${{document.search_rank ? ` - search result ${{document.search_rank}}` : ''}}</span>
                            </div>
                            <div><span class="filing-meta">Date</span><strong>${{escapeHtml(dateText)}}</strong></div>
                            <div class="filing-labels">${{labelHtml}}</div>
                            <button class="filing-action" type="button" data-select-docket-document="${{index}}">${{isSelected ? 'Selected' : 'Select filing'}}</button>
                        </div>
                    `;
                }}).join('');
            }}

            function selectDocketDocumentByIndex(index) {{
                const numericIndex = Number(index);
                if (!Number.isInteger(numericIndex) || numericIndex < 0 || numericIndex >= dashboardState.docketDocuments.length) {{
                    return;
                }}
                dashboardState.selectedDocketDocumentIndex = numericIndex;
                selectDatasetDocument(dashboardState.docketDocuments[numericIndex], 'docket');
                renderDocketFilingList(dashboardState.docketDocuments);
                updateDocketDatasetReadiness();
                updateDocketSummaryStrip(dashboardState.docketDocuments.length, dashboardState.docketDatasetCalendarEvents);
            }}

            function updateSelectedDocketDocumentPanel(docketDocument) {{
                const selected = docketDocument && typeof docketDocument === 'object' ? docketDocument : dashboardState.selectedDatasetDocument;
                const id = String(
                    selected && (
                        selected.document_id
                        || selected.id
                        || selected.row_id
                        || selected.source_document_id
                        || ''
                    ) || ''
                ).trim();
                const title = String(selected && (selected.title || selected.source_document_title || selected.document_title || '') || '').trim();
                const text = String(selected && (selected.text || selected.snippet || selected.preview || selected.summary || '') || '').trim();
                const dates = extractDatesFromText(`${{title}} ${{text}}`);
                setText('docket-selected-document-title', title || (id ? `Selected filing ${{id}}` : 'No filing selected yet'));
                setText('docket-selected-document-summary', summarizeDocumentText(selected));
                setText('docket-selected-document-id', id || 'waiting');
                setText('docket-selected-document-use', classifyDocumentUse(selected || {{}}));
                setText('docket-selected-document-date', dates.length ? dates.slice(0, 3).join(', ') : 'not found yet');
                setText('docket-selected-banner-title', title || (id ? `Selected filing ${{id}}` : 'No filing selected'));
                setText('docket-selected-banner-meta', selected ? `${{id || 'filing'}} - ${{classifyDocumentUse(selected)}}` : 'Select a filing from the list to keep its title, dates, labels, and review actions visible.');
                const bannerLabels = document.getElementById('docket-selected-banner-labels');
	                if (bannerLabels) {{
	                    const labels = selected ? filingLabelsForDocument(selected) : ['waiting for selection'];
	                    bannerLabels.innerHTML = labels.map((label) => `<span class="filing-label${{/deadline|hearing/i.test(label) ? ' is-urgent' : ''}}">${{escapeHtml(label)}}</span>`).join('');
	                }}
	                const userId = activeDashboardUserId();
	                const documentChatContext = selected ? JSON.stringify(buildDocketChatContext(selected, userId, 'dashboard-docket-document')) : '';
	                const bannerChatContext = selected ? JSON.stringify(buildDocketChatContext(selected, userId, 'dashboard-docket-selected-filing')) : '';
	                setHref('docket-open-chat-about-document', buildSurfaceUrl('/chat', {{
	                    user_id: userId,
	                    source: 'dashboard-docket-document',
	                    prefill_message: title
	                        ? `Help me understand how this docket filing affects my complaint or response: ${{title}}`
	                        : 'Help me understand how this docket filing affects my complaint or response.',
	                    return_to: buildSurfaceUrl('/dashboards', {{ user_id: userId }}),
	                    chat_context: documentChatContext,
	                }}));
	                setHref('docket-banner-chat-link', buildSurfaceUrl('/chat', {{
	                    user_id: userId,
	                    source: 'dashboard-docket-selected-filing',
	                    prefill_message: title
	                        ? `Help me label and analyze this docket filing for my complaint or response: ${{title}}`
	                        : 'Help me label and analyze this docket filing for my complaint or response.',
	                    return_to: buildSurfaceUrl('/dashboards', {{ user_id: userId }}),
	                    chat_context: bannerChatContext,
	                }}));
                updateDocumentContextBar();
                updateAnnotationTaskState();
	            }}

            function selectDatasetDocument(datasetDocument, datasetKind) {{
                const normalizedDocument = datasetDocument && typeof datasetDocument === 'object' ? datasetDocument : null;
                dashboardState.selectedDatasetDocument = normalizedDocument
                    ? Object.assign({{}}, normalizedDocument, {{ dataset_kind: datasetKind || normalizedDocument.dataset_kind || 'dataset' }})
                    : null;
                const documentId = String(
                    normalizedDocument && (
                        normalizedDocument.document_id
                        || normalizedDocument.id
                        || normalizedDocument.row_id
                        || normalizedDocument.source_document_id
                        || ''
                    ) || ''
                ).trim();
                const title = String(normalizedDocument && (normalizedDocument.title || normalizedDocument.source_document_title || '') || '').trim();
                setText(
                    'dashboard-dataset-annotation-status',
                    documentId
                        ? `Selected ${{datasetKind || 'dataset'}} document ${{documentId}} for annotation.`
                        : 'Loaded dataset data, but no document ID was available for annotation.'
                );
                const idNode = document.getElementById('dashboard-dataset-annotation-document-id');
                const titleNode = document.getElementById('dashboard-dataset-annotation-title');
                const graphDocumentNode = document.getElementById('dashboard-workspace-graph-document-id');
                if (idNode && documentId) {{
                    idNode.value = documentId;
                }}
                if (graphDocumentNode && documentId && (datasetKind || '').toLowerCase() === 'workspace') {{
                    graphDocumentNode.value = documentId;
                }}
                if (titleNode && title) {{
                    titleNode.value = `${{title}} annotation`;
                }}
                if ((datasetKind || '').toLowerCase() === 'docket') {{
                    updateSelectedDocketDocumentPanel(dashboardState.selectedDatasetDocument);
                    updateDocketCurrentTask();
                }} else {{
                    updateDocumentContextBar();
                    updateAnnotationTaskState();
                }}
            }}

            function firstDocumentFromPayload(payload) {{
                const documents = Array.isArray(payload && payload.documents) ? payload.documents : [];
                if (documents.length) {{
                    return documents[0];
                }}
                const searchResults = (payload && payload.search_results) || {{}};
                const results = Array.isArray(searchResults.results) ? searchResults.results : [];
                if (!results.length) {{
                    return null;
                }}
                const firstResult = results[0];
                return Object.assign({{}}, firstResult, {{
                    id: firstResult.document_id || firstResult.id || firstResult.row_id || '',
                    title: firstResult.title || firstResult.document_title || '',
                    text: firstResult.text || firstResult.snippet || firstResult.preview || '',
                }});
            }}

            function extractCalendarEvents(payload) {{
                const candidates = [
                    payload && payload.case_calendar,
                    payload && payload.calendar,
                    payload && payload.upcoming_events,
                    payload && payload.hearings,
                    payload && payload.deadlines,
                    payload && payload.events,
                    payload && payload.report && payload.report.case_calendar,
                    payload && payload.report && payload.report.calendar,
                    payload && payload.report && payload.report.upcoming_events,
                    payload && payload.report && payload.report.hearings,
                    payload && payload.report && payload.report.deadlines,
                    payload && payload.report && payload.report.events,
                ];
                for (const candidate of candidates) {{
                    if (Array.isArray(candidate) && candidate.length) {{
                        return candidate;
                    }}
                }}
                return [];
            }}

            function extractCalendarEventsFromDocketView(payload) {{
                const normalizedCalendar = Array.isArray(payload && payload.case_calendar) ? payload.case_calendar : [];
                if (normalizedCalendar.length) {{
                    return normalizedCalendar;
                }}
                const documents = Array.isArray(payload && payload.documents) ? payload.documents : [];
                const events = [];
                const datePattern = /\\b(?:\\d{{1,2}}\\/\\d{{1,2}}\\/\\d{{2,4}}|[A-Z][a-z]+ \\d{{1,2}}, \\d{{4}}|\\d{{4}}-\\d{{2}}-\\d{{2}})\\b/g;
                documents.forEach((document) => {{
                    const title = String(document && document.title || '').trim();
                    const text = String(document && document.text || '').trim();
                    const combined = `${{title}} ${{text}}`.toLowerCase();
                    const explicitFiledDate = String(document && document.date_filed || '').trim();
                    const matchedDates = Array.from(
                        new Set(
                            ((title + ' ' + text).match(datePattern) || [])
                                .map((value) => String(value).trim())
                                .filter(Boolean)
                        )
                    );

                    function pushEvent(kind, label) {{
                        events.push({{
                            kind,
                            title: label,
                            date: matchedDates[0] || explicitFiledDate || '',
                            source_document_id: document && document.id || '',
                            source_document_title: title,
                            document_number: document && document.document_number || '',
                            source: 'packaged_docket_view',
                        }});
                    }}

                    if (combined.includes('hearing')) {{
                        pushEvent('hearing', title || 'Hearing event');
                    }}
                    if (combined.includes('deadline') || combined.includes('due ') || combined.includes(' due') || combined.includes('must respond') || combined.includes('initial disclosures due')) {{
                        pushEvent('deadline', title || 'Deadline event');
                    }}
                    if (combined.includes('conference') || combined.includes('trial')) {{
                        pushEvent('calendar_event', title || 'Court calendar event');
                    }}
                }});
                return events;
            }}

            function summarizeCalendarEvent(event) {{
                if (!event || typeof event !== 'object') {{
                    return 'No scheduled item details available.';
                }}
                const label = String(
                    event.title
                    || event.label
                    || event.event
                    || event.name
                    || event.description
                    || event.kind
                    || 'Scheduled item'
                ).trim();
                const date = String(
                    event.date
                    || event.when
                    || event.datetime
                    || event.starts_at
                    || event.start
                    || event.deadline
                    || ''
                ).trim();
                return date ? `${{label}} on ${{date}}` : label;
            }}

            function normalizeEventDate(event) {{
                const rawValue = String(
                    event && (
                        event.date
                        || event.when
                        || event.datetime
                        || event.starts_at
                        || event.start
                        || event.deadline
                        || ''
                    )
                ).trim();
                if (!rawValue) {{
                    return null;
                }}
                const timestamp = Date.parse(rawValue);
                return Number.isFinite(timestamp) ? new Date(timestamp) : null;
            }}

            function prioritizeCalendarEvents(events) {{
                const now = new Date();
                return [...(Array.isArray(events) ? events : [])].sort((left, right) => {{
                    const leftDate = normalizeEventDate(left);
                    const rightDate = normalizeEventDate(right);
                    if (leftDate && rightDate) {{
                        const leftDelta = Math.abs(leftDate.getTime() - now.getTime());
                        const rightDelta = Math.abs(rightDate.getTime() - now.getTime());
                        if (leftDelta !== rightDelta) {{
                            return leftDelta - rightDelta;
                        }}
                    }} else if (leftDate || rightDate) {{
                        return leftDate ? -1 : 1;
                    }}
                    return summarizeCalendarEvent(left).localeCompare(summarizeCalendarEvent(right));
                }});
            }}

            function describeCalendarUrgency(event) {{
                const normalizedDate = normalizeEventDate(event);
                if (!normalizedDate) {{
                    return 'date not parsed';
                }}
                const now = new Date();
                const dayMs = 24 * 60 * 60 * 1000;
                const diffDays = Math.round((normalizedDate.getTime() - now.getTime()) / dayMs);
                if (diffDays < 0) {{
                    return `${{Math.abs(diffDays)}} day${{Math.abs(diffDays) === 1 ? '' : 's'}} ago`;
                }}
                if (diffDays === 0) {{
                    return 'today';
                }}
                if (diffDays === 1) {{
                    return 'tomorrow';
                }}
                return `in ${{diffDays}} days`;
            }}

            function updateWorkspaceContextBar(payload) {{
                const session = payload && payload.session ? payload.session : {{}};
                const review = payload && payload.review ? payload.review : {{}};
                const overview = review && review.overview ? review.overview : {{}};
                const readiness = payload && payload.complaint_readiness ? payload.complaint_readiness : {{}};
                const evidence = session && session.evidence ? session.evidence : {{}};
                const evidenceCount = parseCount((evidence.testimony || []).length, 0) + parseCount((evidence.documents || []).length, 0);
                const missingCount = parseCount(overview.missing_elements, 0);
                const hasDraft = Boolean(payload && payload.draft) || Boolean(session && session.draft);
                const userId = String(session.user_id || '').trim();
                const claimType = String(session.claim_type || '').trim();
                let nextAction = 'Load workspace to get next action';
                if (userId) {{
                    if (missingCount > 0) {{
                        nextAction = `Review ${{missingCount}} support gap${{missingCount === 1 ? '' : 's'}}`;
                    }} else if (!hasDraft && evidenceCount > 0) {{
                        nextAction = 'Generate complaint draft';
                    }} else if (hasDraft) {{
                        nextAction = 'Refine existing draft';
                    }} else {{
                        nextAction = 'Continue intake and add evidence';
                    }}
                }}
                const routeHint = String(readiness.recommended_route || '').trim();
                setText('context-next-action', routeHint ? `${{nextAction}} - ${{routeHint}}` : nextAction);
                setText('context-workspace-id', userId || 'not loaded');
                setText('context-claim-type', claimType ? titleCase(claimType, 'Waiting') : 'waiting');
                setText('context-evidence-count', `${{evidenceCount}} item${{evidenceCount === 1 ? '' : 's'}}`);
                setText('context-draft-status', hasDraft ? 'available' : 'not available');
                setHref('context-open-workspace', buildSurfaceUrl('/workspace', {{
                    user_id: userId,
                    target_tab: missingCount > 0 ? 'review' : 'intake',
                }}));
                setHref('context-open-review', buildSurfaceUrl('/claim-support-review', {{
                    user_id: userId,
                    workspace_user_id: userId,
                    claim_type: claimType,
                }}));
                setHref('context-open-chat', buildSurfaceUrl('/chat', {{
                    user_id: userId,
                    source: 'dashboard-context-bar',
                    return_to: buildSurfaceUrl('/dashboards', {{ user_id: userId }}),
                }}));
                setHref('context-open-builder', buildSurfaceUrl('/document', {{
                    user_id: userId,
                    workspace_user_id: userId,
                    claim_type: claimType,
                }}));
                setHref('context-workspace-hint', buildSurfaceUrl('/workspace', {{ user_id: userId }}));
                setHref('context-claim-hint', buildSurfaceUrl('/chat', {{ user_id: userId, source: 'dashboard-context-claim' }}));
                setHref('context-evidence-hint', '#chat-upload-dashboard');
                setHref('context-draft-hint', buildSurfaceUrl('/document', {{ user_id: userId, workspace_user_id: userId, claim_type: claimType }}));
                updateWorkflowRail(payload || null);
                updateDocumentContextBar();
            }}

            function clearWorkspaceContextBar() {{
                setText('context-next-action', 'Load workspace to get next action');
                setText('context-workspace-id', 'not loaded');
                setText('context-claim-type', 'waiting');
                setText('context-evidence-count', '0 items');
                setText('context-draft-status', 'not available');
                setHref('context-open-workspace', '/workspace');
                setHref('context-open-review', '/claim-support-review');
                setHref('context-open-chat', '/chat');
                setHref('context-open-builder', '/document');
                setHref('context-workspace-hint', '/workspace');
                setHref('context-claim-hint', '/chat');
                setHref('context-evidence-hint', '#chat-upload-dashboard');
                setHref('context-draft-hint', '/document');
                resetWorkflowRail();
                updateDocumentContextBar();
            }}

            function deriveMikeUiState(mikeStatus) {{
                const status = mikeStatus && typeof mikeStatus === 'object' ? mikeStatus : {{}};
                const workflowState = status.workflow_state && typeof status.workflow_state === 'object'
                    ? status.workflow_state
                    : null;
                if (workflowState && String(workflowState.key || '').trim()) {{
                    return {{
                        key: String(workflowState.key || '').trim(),
                        label: String(workflowState.label || '').trim() || 'unknown',
                        severity: String(workflowState.severity || '').trim() || 'warn',
                    }};
                }}
                const pendingSync = Boolean(status.pending_sync);
                const hasSyncedDraft = Boolean(status.has_mike_synced_draft);
                const hasConflicts = Boolean(status.has_citation_link_conflicts);
                const latestHandoffId = String(status.latest_handoff_id || '').trim();
                if (!latestHandoffId) {{
                    return {{ key: 'not_handed_off', label: 'not handed off', severity: 'warn' }};
                }}
                if (pendingSync) {{
                    return {{ key: 'handoff_pending_sync', label: 'handoff pending sync', severity: 'warn' }};
                }}
                if (hasSyncedDraft && hasConflicts) {{
                    return {{ key: 'synced_with_conflicts', label: 'synced with conflicts', severity: 'warn' }};
                }}
                if (hasSyncedDraft) {{
                    return {{ key: 'synced_clean', label: 'synced clean', severity: 'good' }};
                }}
                return {{ key: 'handoff_pending_sync', label: 'handoff pending sync', severity: 'warn' }};
            }}

            function renderWorkspaceCard(payload, mikeStatus) {{
                const session = payload && payload.session ? payload.session : {{}};
                const review = payload && payload.review ? payload.review : {{}};
                const overview = review && review.overview ? review.overview : {{}};
                const answers = session && session.intake_answers ? Object.keys(session.intake_answers).length : 0;
                const evidence = session && session.evidence ? session.evidence : {{}};
                const evidenceCount = parseCount((evidence.testimony || []).length, 0) + parseCount((evidence.documents || []).length, 0);
                const hasDraft = Boolean(payload && payload.draft) || Boolean(session && session.draft);
                const mike = mikeStatus && typeof mikeStatus === 'object' ? mikeStatus : {{}};
                const mikeState = deriveMikeUiState(mike);
                const mikeConflictCount = parseCount(mike.citation_link_conflict_count, 0);
                const mikeUnknownCount = parseCount(mike.citation_link_unknown_element_count, 0);
                const mikeStatusContractVersion = String(mike.status_contract_version || '').trim();
                const isMikeStatusStale = isTimestampStale(dashboardState.workspaceMikeStatusUpdatedAt, MIKE_STATUS_STALE_MS);
                setText('dashboard-workspace-answered', String(answers));
                setText('dashboard-workspace-evidence', String(evidenceCount));
                setText('dashboard-workspace-missing', String(parseCount(overview.missing_elements, 0)));
                setText('dashboard-workspace-draft', hasDraft ? 'Yes' : 'No');
                setText('dashboard-workspace-session-chip', `session: ${{String(session.user_id || 'unknown')}}`);
                const readiness = payload && payload.complaint_readiness ? payload.complaint_readiness : {{}};
                const mikeRecommendedAction = String(mike.recommended_action || '').trim();
                let mikeRouteHint = String(readiness.recommended_route || '/workspace');
                if (isMikeStatusStale || !mikeStatusContractVersion) {{
                    mikeRouteHint = '/workspace?target_tab=draft&focus=mike-integration-card';
                }} else if (mikeState.key === 'synced_with_conflicts') {{
                    mikeRouteHint = '/workspace?target_tab=draft&focus=mike-integration-card';
                }} else if (mikeState.key === 'handoff_pending_sync' || mikeState.key === 'not_handed_off') {{
                    mikeRouteHint = '/document?focus=mike-workflow-journey';
                }}
                dashboardState.workspaceMikeRouteHint = mikeRouteHint;
                dashboardState.workspaceMikeStale = isMikeStatusStale;
                dashboardState.workspaceMikeStatusContractVersion = mikeStatusContractVersion;
                setText('dashboard-workspace-route-chip', `next route: ${{mikeRouteHint}}`);
                const mikeStateChip = document.getElementById('dashboard-workspace-mike-state-chip');
                if (mikeStateChip) {{
                    mikeStateChip.className = `chip ${{mikeState.severity}}`;
                }}
                setText('dashboard-workspace-mike-state-chip', `mike: ${{mikeState.label}}`);
                const mikeConflictChip = document.getElementById('dashboard-workspace-mike-conflict-chip');
                if (mikeConflictChip) {{
                    mikeConflictChip.className = `chip ${{mikeConflictCount > 0 || mikeUnknownCount > 0 ? 'warn' : 'good'}}`;
                }}
                setText('dashboard-workspace-mike-conflict-chip', `mike conflicts: ${{mikeConflictCount}} | unknown links: ${{mikeUnknownCount}}`);
                setText(
                    'dashboard-workspace-status',
                    isMikeStatusStale || !mikeStatusContractVersion
                        ? `Loaded workspace session for ${{String(session.user_id || 'default user')}}. Mike status is stale or missing contract metadata, so refresh the workspace Mike panel before export.`
                        : mikeState.key === 'synced_with_conflicts'
                        ? `Loaded workspace session for ${{String(session.user_id || 'default user')}}. High-priority: resolve Mike citation-link conflicts and sync again before export.`
                        : `Loaded workspace session for ${{String(session.user_id || 'default user')}}.`
                );
                setText(
                    'dashboard-workspace-preview',
                    JSON.stringify({{
                        session: {{
                            user_id: session.user_id,
                            claim_type: session.claim_type,
                            case_synopsis: session.case_synopsis,
                        }},
                        review_overview: overview,
                        complaint_readiness: readiness,
                        mike_integration_status: mike,
                        mike_status_updated_at: dashboardState.workspaceMikeStatusUpdatedAt,
                        mike_status_stale: isMikeStatusStale,
                        mike_status_contract_version: mikeStatusContractVersion || null,
                        mike_recommended_action: mikeRecommendedAction,
                    }}, null, 2)
                );
                dashboardState.workspacePayload = payload || null;
                updateWorkspaceContextBar(payload || null);
                renderHeadsUpCard();
            }}

            function clearWorkspaceCard(reason) {{
                dashboardState.workspacePayload = null;
                dashboardState.workspaceMikeStatusUpdatedAt = null;
                dashboardState.workspaceMikeRouteHint = '';
                dashboardState.workspaceMikeStale = false;
                dashboardState.workspaceMikeStatusContractVersion = '';
                setText('dashboard-workspace-answered', '0');
                setText('dashboard-workspace-evidence', '0');
                setText('dashboard-workspace-missing', '0');
                setText('dashboard-workspace-draft', 'No');
                setText('dashboard-workspace-session-chip', 'session: not loaded');
                setText('dashboard-workspace-route-chip', 'next route: waiting');
                const mikeStateChip = document.getElementById('dashboard-workspace-mike-state-chip');
                if (mikeStateChip) {{
                    mikeStateChip.className = 'chip';
                }}
                setText('dashboard-workspace-mike-state-chip', 'mike: waiting');
                const mikeConflictChip = document.getElementById('dashboard-workspace-mike-conflict-chip');
                if (mikeConflictChip) {{
                    mikeConflictChip.className = 'chip';
                }}
                setText('dashboard-workspace-mike-conflict-chip', 'mike conflicts: waiting');
                setText('dashboard-workspace-status', reason || 'Workspace session unloaded.');
                setText('dashboard-workspace-preview', 'Workspace session details will appear here.');
                clearWorkspaceContextBar();
                renderHeadsUpCard();
            }}

            async function fetchMikeIntegrationStatus(userId) {{
                const query = userId ? `?user_id=${{encodeURIComponent(userId)}}` : '';
                return fetchJson(`/api/complaint-workspace/mike/status${{query}}`);
            }}

            function deriveDocketStats(payload) {{
                const queue = payload && (payload.queue || payload.revalidation_queue || payload.items || []);
                const priorityCounts = payload && (payload.priority_counts || payload.queue_priority_counts || {{}});
                const runHistory = payload && (payload.runs || payload.run_history || payload.executions || []);
                return {{
                    queueCount: Array.isArray(queue) ? queue.length : parseCount(payload && payload.queue_count, 0),
                    highPriority: parseCount(priorityCounts.high, parseCount(payload && payload.high_priority_count, 0)),
                    runCount: Array.isArray(runHistory) ? runHistory.length : parseCount(payload && payload.run_count, 0),
                }};
            }}

            function renderDocketCard(payload, label) {{
                const stats = deriveDocketStats(payload || {{}});
                const reportCalendarEvents = extractCalendarEvents(payload || {{}});
                const docketViewCalendarEvents = extractCalendarEventsFromDocketView(dashboardState.docketViewPayload || {{}});
                const calendarEvents = prioritizeCalendarEvents(docketViewCalendarEvents.length ? docketViewCalendarEvents : reportCalendarEvents);
                setText('dashboard-docket-queue', String(stats.queueCount));
                setText('dashboard-docket-high', String(stats.highPriority));
                setText('dashboard-docket-runs', String(stats.runCount));
                setText('dashboard-docket-calendar-count', String(calendarEvents.length));
                setText('dashboard-docket-source-chip', `filings: ${{String((payload && payload.source) || label || 'loaded')}}`);
                setText('dashboard-docket-manifest-chip', `package: ${{String((payload && payload.manifest_path) || 'not set')}}`);
                setText(
                    'dashboard-docket-calendar-chip',
                    calendarEvents.length
                        ? `next date: ${{summarizeCalendarEvent(calendarEvents[0])}}`
                        : 'dates: none found'
                );
                setText(
                    'dashboard-docket-status',
                    calendarEvents.length
                        ? `Loaded docket payload from ${{label}} with ${{calendarEvents.length}} calendar event${{calendarEvents.length === 1 ? '' : 's'}}.`
                        : `Loaded docket payload from ${{label}}.`
                );
                renderChipList(
                    'dashboard-docket-calendar-list',
                    calendarEvents.slice(0, 3).map((event) => `${{summarizeCalendarEvent(event)}} (${{describeCalendarUrgency(event)}})`),
                    'No hearing, deadline, or conference event detected in the loaded docket.'
                );
                setText(
                    'dashboard-docket-preview',
                    JSON.stringify(Object.assign({{}}, payload || {{}}, {{
                        extracted_calendar_events: calendarEvents,
                        docket_view_summary: (dashboardState.docketViewPayload || {{}}).summary || null,
                    }}), null, 2)
                );
                dashboardState.docketPayload = payload || null;
                renderHeadsUpCard();
            }}

            function datasetQueryParams(pathInputId, typeInputId, extra) {{
                const pathNode = document.getElementById(pathInputId);
                const typeNode = document.getElementById(typeInputId);
                const inputPath = String((pathNode && pathNode.value) || '').trim();
                if (!inputPath) {{
                    throw new Error('Add a dataset path first.');
                }}
                const params = new URLSearchParams();
                params.set('input_path', inputPath);
                params.set('input_type', String((typeNode && typeNode.value) || 'single'));
                Object.entries(extra || {{}}).forEach(([key, value]) => {{
                    if (value !== null && value !== undefined && String(value).trim() !== '') {{
                        params.set(key, String(value).trim());
                    }}
                }});
                return params;
            }}

            function renderDocketDatasetCard(payload, label) {{
                const summary = (payload && payload.summary) || {{}};
                const documents = Array.isArray(payload && payload.documents) ? payload.documents : [];
                const searchResults = (payload && payload.search_results) || {{}};
                const results = Array.isArray(searchResults.results) ? searchResults.results : [];
                const docketDocuments = documentsFromDocketPayload(payload || {{}}, label || 'view');
                const extractedCalendarEvents = prioritizeCalendarEvents(extractCalendarEvents(payload || {{}}).length ? extractCalendarEvents(payload || {{}}) : extractCalendarEventsFromDocketView(payload || {{}}));
                const calendarEvents = extractedCalendarEvents.length
                    ? extractedCalendarEvents
                    : (Array.isArray(dashboardState.docketDatasetCalendarEvents) ? dashboardState.docketDatasetCalendarEvents : []);
                const graph = (payload && payload.knowledge_graph) || {{}};
                const issueLinkCount = Number(graph.issue_link_count || graph.relationship_count || 0);
                setText('dashboard-docket-dataset-documents', String(Number(summary.document_count || documents.length || docketDocuments.length || 0)));
                setText('dashboard-docket-dataset-events', String(calendarEvents.length));
                setText('dashboard-docket-dataset-results', String(Number(searchResults.result_count || results.length || 0)));
                setText('dashboard-docket-dataset-graph-count', String(issueLinkCount));
                setText('dashboard-docket-dataset-case-chip', `case: ${{String((payload && (payload.case_name || payload.docket_id)) || summary.case_name || summary.docket_id || 'unknown')}}`);
                setText('dashboard-docket-dataset-source-chip', `filings: ${{String((payload && payload.source) || label || 'loaded')}}`);
                if (label === 'search') {{
                    setText('dashboard-docket-dataset-status', results.length ? `Search complete. Review the first useful filing, then save a note to the workspace.` : 'Search complete. No matching filing was returned; try a broader search such as hearing, deadline, notice, order, or response.');
                }} else if (label === 'graph') {{
                    setText('dashboard-docket-dataset-status', issueLinkCount ? `Mapped ${{issueLinkCount}} filing connection${{issueLinkCount === 1 ? '' : 's'}}. Use the selected filing panel to save the legal impact.` : 'Connection map loaded, but no filing links were returned.');
                }} else {{
                    setText('dashboard-docket-dataset-status', calendarEvents.length ? `Loaded filings and found ${{calendarEvents.length}} possible date${{calendarEvents.length === 1 ? '' : 's'}}. Review dates, search filings, or save a note from the selected filing.` : 'Loaded filings. Search for dates, motions, orders, notice problems, or response issues.');
                }}
                setText('dashboard-docket-dataset-preview', JSON.stringify(Object.assign({{}}, payload || {{}}, {{
                    extracted_calendar_events: calendarEvents.slice(0, 10),
                }}), null, 2));
                dashboardState.docketPayload = payload || dashboardState.docketPayload || null;
                dashboardState.docketDatasetLoaded = true;
                dashboardState.docketDatasetStatus = 'loaded';
                dashboardState.docketDatasetError = '';
                dashboardState.docketDatasetCalendarEvents = calendarEvents;
                dashboardState.docketDatasetSearchCount = Number(searchResults.result_count || results.length || 0);
                dashboardState.docketDocuments = docketDocuments;
                dashboardState.selectedDocketDocumentIndex = docketDocuments.length ? 0 : -1;
                renderDocketFilingList(docketDocuments);
                if (docketDocuments.length) {{
                    selectDocketDocumentByIndex(0);
                }} else {{
                    selectDatasetDocument(firstDocumentFromPayload(payload || {{}}), 'docket');
                }}
                updateDocketSummaryStrip(Number(summary.document_count || documents.length || docketDocuments.length || 0), calendarEvents);
                renderChipList(
                    'dashboard-docket-calendar-list',
                    calendarEvents.slice(0, 3).map((event) => `${{summarizeCalendarEvent(event)}} (${{describeCalendarUrgency(event)}})`),
                    'No hearing, deadline, or conference event detected in the loaded docket.'
                );
                updateDocketDatasetReadiness();
                renderHeadsUpCard();
            }}

            function renderWorkspaceDatasetCard(payload, label) {{
                const summary = (payload && payload.summary) || {{}};
                const documents = Array.isArray(payload && payload.documents) ? payload.documents : [];
                const collections = Array.isArray(payload && payload.collections) ? payload.collections : [];
                const searchResults = (payload && payload.search_results) || {{}};
                const results = Array.isArray(searchResults.results) ? searchResults.results : [];
                const vectorItems = Array.isArray(payload && payload.vector_index && payload.vector_index.items) ? payload.vector_index.items : [];
                setText('dashboard-workspace-dataset-documents', String(Number(summary.document_count || documents.length || 0)));
                setText('dashboard-workspace-dataset-collections', String(Number(summary.collection_count || collections.length || 0)));
                setText('dashboard-workspace-dataset-results', String(Number(searchResults.result_count || results.length || 0)));
                setText('dashboard-workspace-dataset-entities', String(Number(summary.knowledge_graph_entity_count || 0)));
                setText('dashboard-workspace-dataset-relationships', String(Number(summary.knowledge_graph_relationship_count || 0)));
                setText('dashboard-workspace-dataset-vectors', String(Number(summary.vector_document_count || vectorItems.length || 0)));
                setText('dashboard-workspace-dataset-logic', String(Number(summary.deontic_statement_count || 0)));
                setText('dashboard-workspace-dataset-proofs', String(Number(summary.proof_count || 0)));
                setText('dashboard-workspace-dataset-workspace-chip', `workspace: ${{String(summary.workspace_name || summary.workspace_id || 'unknown')}}`);
                setText('dashboard-workspace-dataset-source-chip', `source: ${{String((payload && payload.source) || label || 'dataset')}}`);
                setText('dashboard-workspace-dataset-status', `Loaded saved materials for ${{label || 'view'}}. You can now choose a material type, search, or find connections.`);
                setText('dashboard-workspace-dataset-preview', JSON.stringify(payload || {{}}, null, 2));
                selectDatasetDocument(firstDocumentFromPayload(payload || {{}}), 'workspace');
            }}

            function renderWorkspaceGraphExplorer(payload) {{
                const graph = (payload && payload.knowledge_graph) || {{}};
                const logicalFlow = (payload && payload.logical_flow) || {{}};
                const statements = Array.isArray(logicalFlow.statements) ? logicalFlow.statements : [];
                const flowEdges = Array.isArray(logicalFlow.flow_edges) ? logicalFlow.flow_edges : [];
                const events = Array.isArray(logicalFlow.events) ? logicalFlow.events : [];
                const eventFlowEdges = Array.isArray(logicalFlow.event_flow_edges) ? logicalFlow.event_flow_edges : [];
                const deonticAnalysis = Array.isArray(logicalFlow.deontic_analysis) ? logicalFlow.deontic_analysis : [];
                const statusCounts = (logicalFlow && logicalFlow.deontic_status_counts) || {{}};
                const conflicts = Array.isArray(logicalFlow.conflicts) ? logicalFlow.conflicts : [];
                const logicSystems = (logicalFlow && logicalFlow.logic_systems) || {{}};
                const proofSystem = (logicalFlow && logicalFlow.proof_system) || {{}};
                const tdfol = logicSystems.deontic_temporal_first_order_logic || {{}};
                const dcec = logicSystems.deontic_cognitive_event_calculus || {{}};
                const zkp = proofSystem.zero_knowledge_proofs || {{}};
                const relationships = Array.isArray(graph.relationships) ? graph.relationships : [];
                const entities = Array.isArray(graph.entities) ? graph.entities : [];
                setText('dashboard-workspace-graph-matches', String(Number(graph.matched_relationship_count || relationships.length || 0)));
                setText('dashboard-workspace-flow-statements', String(Number(logicalFlow.returned_statement_count || statements.length || 0)));
                setText('dashboard-workspace-flow-events', String(Number(logicalFlow.returned_event_count || events.length || 0)));
                setText('dashboard-workspace-flow-prohibited', String(Number(statusCounts.prohibited || 0)));
                setText('dashboard-workspace-flow-conflicts', String(Number(logicalFlow.returned_conflict_count || conflicts.length || 0)));
                setText('dashboard-workspace-flow-tdfol', String(Number(tdfol.formula_count || 0)));
                setText('dashboard-workspace-flow-dcec', String(Number(dcec.formula_count || 0)));
                setText('dashboard-workspace-flow-zkp', String(Number(zkp.certificate_count || 0)));
                setText(
                    'dashboard-workspace-graph-status',
                    `Loaded workspace graph explorer with ${{entities.length}} returned entities, ${{relationships.length}} returned relationships, ${{events.length}} governed event(s), ${{eventFlowEdges.length}} event-flow edge(s), and ${{Number(zkp.certificate_count || 0)}} ZK certificate(s).`
                );
                setText('dashboard-workspace-graph-preview', JSON.stringify({{
                    filters: (payload && payload.filters) || {{}},
                    graph_totals: {{
                        entity_count: Number(graph.entity_count || 0),
                        relationship_count: Number(graph.relationship_count || 0),
                        matched_entity_count: Number(graph.matched_entity_count || 0),
                        matched_relationship_count: Number(graph.matched_relationship_count || 0),
                    }},
                    entities,
                    relationships,
                    logical_flow: {{
                        summary: logicalFlow.summary || {{}},
                        deontic_status_counts: statusCounts,
                        deontic_analysis: deonticAnalysis,
                        statements,
                        flow_edges: flowEdges,
                        events,
                        event_flow_edges: eventFlowEdges,
                        conflicts,
                        formulas: logicalFlow.formulas || {{}},
                        logic_systems: logicSystems,
                        proof_system: proofSystem,
                    }},
                    metadata: (payload && payload.metadata) || {{}},
                }}, null, 2));
            }}

            function useLoadedDatasetDocument() {{
                selectDatasetDocument(dashboardState.selectedDatasetDocument, dashboardState.selectedDatasetDocument && dashboardState.selectedDatasetDocument.dataset_kind || 'dataset');
            }}

            async function saveDatasetDocumentAnnotation() {{
                const userId = String((document.getElementById('dashboard-dataset-annotation-user-id') || {{}}).value || '').trim();
                const userName = String((document.getElementById('dashboard-dataset-annotation-user-name') || {{}}).value || '').trim();
                const userRole = String((document.getElementById('dashboard-dataset-annotation-user-role') || {{}}).value || 'workspace reviewer').trim();
                const documentId = String((document.getElementById('dashboard-dataset-annotation-document-id') || {{}}).value || '').trim();
                const claimElementId = String((document.getElementById('dashboard-dataset-annotation-claim-element') || {{}}).value || 'causation').trim();
                const title = String((document.getElementById('dashboard-dataset-annotation-title') || {{}}).value || 'Dataset document annotation').trim();
                const tags = String((document.getElementById('dashboard-dataset-annotation-tags') || {{}}).value || '')
                    .split(/[,;\\n]+/)
                    .map((tag) => tag.trim())
                    .filter(Boolean);
                const note = String((document.getElementById('dashboard-dataset-annotation-note') || {{}}).value || '').trim();
                if (!documentId) {{
                    setText('dashboard-dataset-annotation-status', 'Choose or load a dataset document before saving an annotation.');
                    return;
                }}
                if (!note) {{
                    setText('dashboard-dataset-annotation-status', 'Add a review note before saving the annotation.');
                    return;
                }}
                const selected = dashboardState.selectedDatasetDocument || {{}};
                const sourceKind = String(selected.dataset_kind || 'dataset');
	                if (sourceKind === 'docket' && !dashboardState.notePreflightApproved) {{
	                    populateNotePreflight();
	                    toggleNotePreflightModal(true);
	                    setText('dashboard-dataset-annotation-status', 'Preflight check is visible below. You can save, keep editing, or ask chat about this filing before saving.');
	                    return;
	                }}
                dashboardState.notePreflightApproved = false;
                setText('dashboard-dataset-annotation-status', 'Saving dataset document annotation into the complaint workspace...');
                try {{
                    const endpoint = sourceKind === 'workspace'
                        ? '/api/complaint-workspace/workspace-dataset/annotations/tag'
                        : '/api/complaint-workspace/document-annotations/tag';
                    const metadata = selected.metadata || {{}};
                    const requestBody = {{
                        user_id: userId || undefined,
                        document_id: documentId,
                        tags,
                        note,
                        claim_element_id: claimElementId || selected.claim_element_id || metadata.claim_element_id || 'causation',
                        title,
                        document_title: selected.title || selected.source_document_title || '',
                        document_text_preview: selected.text ? String(selected.text).slice(0, 500) : '',
                        document_metadata: metadata,
                        user_metadata: {{
                            user_id: userId || undefined,
                            display_name: userName || userId || 'workspace reviewer',
                            role: userRole || 'workspace reviewer',
                        }},
                        source: `dashboard-${{sourceKind}}-dataset-annotation`,
                    }};
                    if (sourceKind === 'workspace') {{
                        requestBody.collection_id = selected.collection_id || metadata.collection_id || '';
                        requestBody.document_type = selected.document_type || metadata.document_type || '';
                        requestBody.claim_type = selected.claim_type || metadata.claim_type || '';
                        requestBody.source_type = selected.source_type || metadata.source_type || metadata.source_family || '';
                    }} else {{
                        requestBody.dataset_kind = sourceKind;
                    }}
                    const payload = await fetchJson(endpoint, {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify(requestBody),
                    }});
                    setText('dashboard-dataset-annotation-status', `Saved note for ${{documentId}} into the complaint workspace.`);
                    const receipt = document.getElementById('dashboard-dataset-annotation-receipt');
                    if (receipt) {{
                        receipt.classList.add('is-visible');
                        receipt.textContent = `Saved to complaint workspace: ${{title}}. Labels: ${{tags.length ? tags.join(', ') : 'none'}}. Next step: open proof review or continue reviewing filings.`;
                    }}
                    if (sourceKind === 'docket') {{
                        dashboardState.docketNotesSent = Number(dashboardState.docketNotesSent || 0) + 1;
                        updateDocketSummaryStrip(dashboardState.docketDocuments.length, dashboardState.docketDatasetCalendarEvents);
                    }}
                    setText('dashboard-dataset-annotation-preview', JSON.stringify(payload, null, 2));
                    publishSharedSyncEvent({{
                        event_type: 'workspace.updated',
                        source: 'dashboard-dataset-document-annotation',
                        user_id: String(((payload || {{}}).session || {{}}).user_id || userId || ''),
                        payload: payload || null,
                    }});
                    if (payload && payload.session) {{
                        renderWorkspaceCard(payload);
                    }}
                }} catch (error) {{
                    setText('dashboard-dataset-annotation-status', `Annotation save failed: ${{error.message}}`);
                }}
            }}

            async function loadDocketDatasetDashboard(mode) {{
                const statusId = 'dashboard-docket-dataset-status';
                const preflight = getDocketDatasetPreflight();
                if (mode === 'search' && !preflight.canSearch) {{
                    setText(statusId, preflight.reason);
                    updateDocketDatasetReadiness();
                    return;
                }}
                if (mode === 'graph' && !preflight.canGraph) {{
                    setText(statusId, preflight.reason);
                    updateDocketDatasetReadiness();
                    return;
                }}
                setText(statusId, mode === 'search' ? 'Searching filings...' : mode === 'graph' ? 'Mapping filing connections...' : 'Loading case filings...');
                if (mode !== 'search' && mode !== 'graph') {{
                    dashboardState.docketDatasetLoaded = false;
                    dashboardState.docketDatasetStatus = 'loading';
                    dashboardState.docketDatasetError = '';
                    dashboardState.docketDatasetSearchCount = 0;
                    updateDocketDatasetReadiness();
                }}
                try {{
                    let endpoint = '/api/complaint-workspace/docket-dataset/view';
                    const extra = {{
                        include_document_text: 'true',
                        document_limit: '40',
                    }};
                    if (mode === 'search') {{
                        const query = String((document.getElementById('dashboard-docket-dataset-query') || {{}}).value || '').trim();
                        if (!query) {{
                            throw new Error('Enter a docket dataset query before searching.');
                        }}
                        endpoint = '/api/complaint-workspace/docket-dataset/search';
                        extra.query = query;
                        extra.top_k = '10';
                    }} else if (mode === 'graph') {{
                        endpoint = '/api/complaint-workspace/docket-dataset/graph';
                    }}
                    const params = datasetQueryParams('dashboard-docket-dataset-path', 'dashboard-docket-dataset-input-type', extra);
                    const payload = await fetchJson(`${{endpoint}}?${{params.toString()}}`);
                    renderDocketDatasetCard(payload, mode || 'view');
                }} catch (error) {{
                    dashboardState.docketDatasetLoaded = false;
                    dashboardState.docketDatasetStatus = 'error';
                    dashboardState.docketDatasetError = String(error.message || 'Unable to load filings.');
                    setText(statusId, `Filing review failed: ${{error.message}}`);
                    updateDocketDatasetReadiness();
                }}
            }}

            async function loadWorkspaceDatasetDashboard(mode) {{
                const statusId = 'dashboard-workspace-dataset-status';
                const preflight = getWorkspaceDatasetPreflight();
                if (mode === 'search' && !preflight.canSearch) {{
                    setText(statusId, preflight.reason);
                    setText('workspace-dataset-run-state', preflight.reason);
                    updateWorkspaceDatasetReadiness();
                    return;
                }}
                setText(statusId, mode === 'search' ? 'Searching workspace dataset parquet...' : 'Loading workspace dataset parquet...');
                if (mode === 'search') {{
                    setText('workspace-dataset-run-state', 'Searching workspace dataset...');
	                }} else {{
	                    dashboardState.workspaceDatasetLoaded = false;
	                    dashboardState.workspaceDatasetStatus = 'loading';
	                    dashboardState.workspaceDatasetError = '';
	                    dashboardState.workspaceGraphReady = false;
	                    setText('workspace-dataset-load-state', 'Loading dataset...');
	                }}
                updateWorkspaceDatasetReadiness();
                try {{
                    const extra = {{
                        include_document_text: 'true',
                        document_limit: '40',
                        claim_type: String((document.getElementById('dashboard-workspace-dataset-claim-type') || {{}}).value || '').trim(),
                        document_type: String((document.getElementById('dashboard-workspace-dataset-document-type') || {{}}).value || '').trim(),
                        source_type: String((document.getElementById('dashboard-workspace-dataset-source-type') || {{}}).value || '').trim(),
                    }};
                    let endpoint = '/api/complaint-workspace/workspace-dataset/view';
                    if (mode === 'search') {{
                        const query = String((document.getElementById('dashboard-workspace-dataset-query') || {{}}).value || '').trim();
                        if (!query) {{
                            throw new Error('Enter words to search for before searching materials.');
                        }}
                        endpoint = '/api/complaint-workspace/workspace-dataset/search';
                        extra.query = query;
                        extra.top_k = '10';
                    }}
                    const params = datasetQueryParams('dashboard-workspace-dataset-path', 'dashboard-workspace-dataset-input-type', extra);
                    const payload = await fetchJson(`${{endpoint}}?${{params.toString()}}`);
	                    renderWorkspaceDatasetCard(payload, mode || 'view');
	                    dashboardState.workspaceDatasetLoaded = true;
	                    dashboardState.workspaceDatasetStatus = 'loaded';
	                    dashboardState.workspaceDatasetError = '';
	                    dashboardState.workspaceGraphReady = false;
                    if (mode === 'search') {{
                        setText('workspace-dataset-run-state', 'Search complete. Results are reflected below.');
                    }} else {{
                        setText('workspace-dataset-load-state', 'Materials loaded');
                        setText('workspace-dataset-run-state', 'Materials loaded. Search or find connections next.');
                    }}
                    updateWorkspaceDatasetReadiness();
	                }} catch (error) {{
	                    dashboardState.workspaceDatasetLoaded = false;
	                    dashboardState.workspaceDatasetStatus = 'error';
		                    dashboardState.workspaceDatasetError = userFacingMaterialsError(error.message);
		                    dashboardState.workspaceGraphReady = false;
	                    setText(statusId, dashboardState.workspaceDatasetError);
	                    if (mode === 'search') {{
	                        setText('workspace-dataset-run-state', dashboardState.workspaceDatasetError);
	                    }} else {{
	                        setText('workspace-dataset-load-state', dashboardState.workspaceDatasetError);
	                    }}
                    updateWorkspaceDatasetReadiness();
                }}
            }}

            function applyWorkspaceDatasetPreset(event) {{
                const button = event && event.currentTarget ? event.currentTarget : null;
                if (!button) {{
                    return;
                }}
                const queryInput = document.getElementById('dashboard-workspace-dataset-query');
                const documentTypeInput = document.getElementById('dashboard-workspace-dataset-document-type');
                const sourceTypeInput = document.getElementById('dashboard-workspace-dataset-source-type');
                if (queryInput) {{
                    queryInput.value = String(button.dataset.datasetQuery || '');
                }}
                if (documentTypeInput) {{
                    documentTypeInput.value = String(button.dataset.datasetDocumentType || '');
                }}
                if (sourceTypeInput) {{
                    sourceTypeInput.value = String(button.dataset.datasetSourceType || '');
                }}
                setWorkspaceLane(button.dataset.datasetSourceType || '');
                setText('dashboard-workspace-dataset-status', `Material type selected: ${{String(button.textContent || '').trim()}}. Load materials, then search or find connections.`);
            }}

            function applyGraphPreset(event) {{
                const button = event && event.currentTarget ? event.currentTarget : null;
                if (!button) {{
                    return;
                }}
                const queryInput = document.getElementById('dashboard-workspace-graph-query');
                const relationshipInput = document.getElementById('dashboard-workspace-graph-relationship-type');
                const modalityInput = document.getElementById('dashboard-workspace-graph-modality');
                const presetQuery = String(button.dataset.graphQuery || '');
                const presetRelationship = String(button.dataset.graphRelationship || '');
                const presetModality = String(button.dataset.graphModality || '');
                if (queryInput) {{
                    queryInput.value = presetQuery;
                }}
                if (relationshipInput) {{
                    relationshipInput.value = presetRelationship;
                }}
                if (modalityInput) {{
                    modalityInput.value = presetModality;
                }}
                setText('dashboard-workspace-graph-status', `Check selected: ${{String(button.textContent || '').trim()}}`);
                updateWorkspaceDatasetReadiness();
            }}

            function applyDocketQuickSearch(event) {{
                const button = event && event.currentTarget ? event.currentTarget : null;
                const queryInput = document.getElementById('dashboard-docket-dataset-query');
                if (!button || !queryInput) {{
                    return;
                }}
                queryInput.value = String(button.dataset.docketQuery || '');
                setText('dashboard-docket-dataset-status', `Search selected: ${{String(button.textContent || '').trim()}}. Run search to inspect matching filings.`);
                updateDocketDatasetReadiness();
            }}

            function addAnnotationTag(event) {{
                const button = event && event.currentTarget ? event.currentTarget : null;
                const input = document.getElementById('dashboard-dataset-annotation-tags');
                if (!button || !input) {{
                    return;
                }}
                const tag = String(button.dataset.annotationTag || '').trim();
                if (!tag) {{
                    return;
                }}
                const tags = String(input.value || '')
                    .split(/[,;\\n]+/)
                    .map((item) => item.trim())
                    .filter(Boolean);
                if (!tags.some((item) => item.toLowerCase() === tag.toLowerCase())) {{
                    tags.push(tag);
                }}
                input.value = tags.join(', ');
                updateDocketCurrentTask();
            }}

            function handleDocketFilingListClick(event) {{
                const button = event && event.target ? event.target.closest('[data-select-docket-document]') : null;
                if (!button) {{
                    return;
                }}
                selectDocketDocumentByIndex(button.dataset.selectDocketDocument);
            }}

	            function toggleNotePreflightModal(forceOpen) {{
	                const panel = document.getElementById('dashboard-note-preflight-modal');
	                if (!panel) {{
	                    return;
	                }}
	                const shouldOpen = typeof forceOpen === 'boolean' ? forceOpen : !panel.classList.contains('is-visible');
	                panel.classList.toggle('is-visible', shouldOpen);
	                panel.hidden = !shouldOpen;
	            }}

	            function populateNotePreflight() {{
	                const selected = dashboardState.selectedDatasetDocument || null;
	                const selectedTitle = String(selected && (selected.title || selected.source_document_title || selected.document_title || selected.document_id || selected.id) || 'No filing selected').trim();
                const tags = currentAnnotationTags();
                const note = String((document.getElementById('dashboard-dataset-annotation-note') || {{}}).value || '').trim();
                const buckets = deadlineRiskBuckets(dashboardState.docketDatasetCalendarEvents || []);
                setText('preflight-selected-filing', selectedTitle);
	                setText('preflight-labels', tags.length ? tags.join(', ') : 'No labels added');
	                setText('preflight-deadline-review', `${{buckets.overdue}} overdue, ${{buckets.dueSoon}} due soon, ${{buckets.upcoming}} upcoming, ${{buckets.unparsed}} need date review`);
	                setText('preflight-note-summary', note ? (note.length > 220 ? `${{note.slice(0, 217)}}...` : note) : 'No note entered');
	                const userId = activeDashboardUserId();
	                const chatContext = selected ? JSON.stringify(buildDocketChatContext(selected, userId, 'dashboard-docket-note-preflight')) : '';
	                setHref('dashboard-note-preflight-chat-link', buildSurfaceUrl('/chat', {{
	                    user_id: userId,
	                    source: 'dashboard-docket-note-preflight',
	                    prefill_message: selectedTitle
	                        ? `Before I save this note, ask me the best questions to clarify the deadline, legal impact, and labels for this filing: ${{selectedTitle}}`
	                        : 'Before I save this note, ask me the best questions to clarify this filing.',
	                    return_to: buildSurfaceUrl('/dashboards', {{ user_id: userId }}),
	                    chat_context: chatContext,
	                }}));
                    setLinkEnabled('dashboard-note-preflight-chat-link', Boolean(selected), selected ? '' : 'Select a filing before asking chat about it.');
	            }}

            async function loadWorkspaceGraphExplorer() {{
                const preflight = getWorkspaceDatasetPreflight();
                if (!preflight.canGraph) {{
                    setText('dashboard-workspace-graph-status', preflight.reason);
                    setText('workspace-dataset-run-state', preflight.reason);
                    updateWorkspaceDatasetReadiness();
                    return;
                }}
                dashboardState.workspaceGraphReady = false;
                setText('dashboard-workspace-graph-status', 'Finding connections and checking duties...');
                setText('workspace-dataset-run-state', 'Finding connections and checking duties...');
                updateWorkspaceDatasetReadiness();
                try {{
                    const extra = {{
                        entity_query: String((document.getElementById('dashboard-workspace-graph-query') || {{}}).value || '').trim(),
                        relationship_type: String((document.getElementById('dashboard-workspace-graph-relationship-type') || {{}}).value || '').trim(),
                        document_id: String((document.getElementById('dashboard-workspace-graph-document-id') || {{}}).value || '').trim(),
                        modality: String((document.getElementById('dashboard-workspace-graph-modality') || {{}}).value || '').trim(),
                        limit: String((document.getElementById('dashboard-workspace-graph-limit') || {{}}).value || '60').trim(),
                    }};
                    const params = datasetQueryParams('dashboard-workspace-dataset-path', 'dashboard-workspace-dataset-input-type', extra);
                    const payload = await fetchJson(`/api/complaint-workspace/workspace-dataset/graph?${{params.toString()}}`);
                    renderWorkspaceGraphExplorer(payload);
                    dashboardState.workspaceGraphReady = true;
                    setText('workspace-dataset-run-state', 'Connections and duty checks loaded.');
                    updateWorkspaceDatasetReadiness();
                }} catch (error) {{
                    dashboardState.workspaceGraphReady = false;
                    setText('dashboard-workspace-graph-status', `Connection and duty check failed: ${{error.message}}`);
                    setText('workspace-dataset-run-state', `Connection and duty check failed: ${{error.message}}`);
                    updateWorkspaceDatasetReadiness();
                }}
            }}

            function clearDocketCard(reason) {{
                dashboardState.docketPayload = null;
                dashboardState.docketViewPayload = null;
                setText('dashboard-docket-queue', '0');
                setText('dashboard-docket-high', '0');
                setText('dashboard-docket-runs', '0');
                setText('dashboard-docket-calendar-count', '0');
                setText('dashboard-docket-source-chip', 'filings: not loaded');
                setText('dashboard-docket-manifest-chip', 'package: not selected');
                setText('dashboard-docket-calendar-chip', 'dates: waiting');
                setText('dashboard-docket-status', reason || 'Saved filing package cleared.');
                renderChipList(
                    'dashboard-docket-calendar-list',
                    [],
                    'Load a docket to preview hearings, deadlines, and conferences.'
                );
                setText('dashboard-docket-preview', 'Packaged docket details will appear here.');
                renderHeadsUpCard();
            }}

            function renderHeadsUpCard() {{
                const workspacePayload = dashboardState.workspacePayload || {{}};
                const session = workspacePayload && workspacePayload.session ? workspacePayload.session : {{}};
                const readiness = workspacePayload && workspacePayload.complaint_readiness ? workspacePayload.complaint_readiness : {{}};
                const docketPayload = dashboardState.docketPayload || null;
                const docketViewPayload = dashboardState.docketViewPayload || null;
                const dashboardCalendarEvents = extractCalendarEvents(docketPayload || {{}});
                const docketViewCalendarEvents = extractCalendarEventsFromDocketView(docketViewPayload || {{}});
                const docketDatasetCalendarEvents = Array.isArray(dashboardState.docketDatasetCalendarEvents) ? dashboardState.docketDatasetCalendarEvents : [];
                const calendarEvents = prioritizeCalendarEvents(
                    docketDatasetCalendarEvents.length
                        ? docketDatasetCalendarEvents
                        : (docketViewCalendarEvents.length ? docketViewCalendarEvents : dashboardCalendarEvents)
                );
                const review = workspacePayload && workspacePayload.review ? workspacePayload.review : {{}};
                const overview = review && review.overview ? review.overview : {{}};
                const evidence = session && session.evidence ? session.evidence : {{}};
                const evidenceCount = parseCount((evidence.testimony || []).length, 0) + parseCount((evidence.documents || []).length, 0);
                const missingCount = parseCount(overview.missing_elements, 0);
                const hasDraft = Boolean(workspacePayload && workspacePayload.draft) || Boolean(session && session.draft);
                const userId = String(session.user_id || '');
                const claimType = String(session.claim_type || 'retaliation');
                const synopsis = String(session.case_synopsis || '');
                const firstCalendarEvent = calendarEvents.length ? calendarEvents[0] : null;
                let nextAction = 'Load workspace';
                let focus = 'Start by loading the workspace session.';
                if (userId) {{
                    if (missingCount > 0 && evidenceCount === 0) {{
                        nextAction = 'Add evidence';
                        focus = `The case still has ${{missingCount}} unsupported element${{missingCount === 1 ? '' : 's'}} and no saved evidence.`;
                    }} else if (missingCount > 0) {{
                        nextAction = 'Review gaps';
                        focus = `Open review to close ${{missingCount}} remaining support gap${{missingCount === 1 ? '' : 's'}}.`;
                    }} else if (!hasDraft && evidenceCount > 0) {{
                        nextAction = 'Draft complaint';
                        focus = 'The record has evidence and looks ready for formal drafting.';
                    }} else if (hasDraft) {{
                        nextAction = 'Refine draft';
                        focus = 'A complaint draft already exists; continue refinement, export, or validation.';
                    }} else {{
                        nextAction = 'Continue intake';
                        focus = 'Keep building the history of the controversy so the workspace record becomes review-ready.';
                    }}
                }}
                const calendarSummary = calendarEvents.length
                    ? summarizeCalendarEvent(calendarEvents[0])
                    : 'No case-calendar event found in the loaded docket payload.';
                const calendarUrgency = firstCalendarEvent ? describeCalendarUrgency(firstCalendarEvent) : '';
                if (calendarEvents.length && userId) {{
                    if (String(nextAction) === 'Load workspace') {{
                        nextAction = 'Review calendar';
                    }}
                    focus = `${{focus}} Next scheduled item: ${{calendarSummary}}`;
                }}
                if (firstCalendarEvent && (calendarUrgency === 'today' || calendarUrgency === 'tomorrow')) {{
                    nextAction = 'Prepare scheduled event';
                    focus = `A docket event is due ${{calendarUrgency}}. ${{calendarSummary}}`;
                }}
                const operatorQueue = [];
                if (!userId) {{
                    operatorQueue.push('Load the workspace session to recover the case history.');
                }}
                if (firstCalendarEvent) {{
                    operatorQueue.push(`Review the next calendar item: ${{calendarSummary}} (${{calendarUrgency || 'timing unknown'}}).`);
                }} else {{
                    operatorQueue.push('Inspect the docket for hearings, deadlines, or conference settings.');
                }}
                if (missingCount > 0) {{
                    operatorQueue.push(`Close ${{missingCount}} remaining support gap${{missingCount === 1 ? '' : 's'}} in review.`);
                }} else if (evidenceCount === 0 && userId) {{
                    operatorQueue.push('Add supporting evidence or testimony into the workspace record.');
                }}
                if (!hasDraft && evidenceCount > 0 && missingCount === 0) {{
                    operatorQueue.push('Generate or refine the complaint draft while the record is fully supported.');
                }}
                if (hasDraft) {{
                    operatorQueue.push('Re-open the draft and prepare the next filing or export step.');
                }}
                const routeHint = String(readiness.recommended_route || '/workspace');
                const effectiveRouteHint = String(dashboardState.workspaceMikeRouteHint || '').trim() || routeHint;
                const workflowState = userId
                    ? (hasDraft ? 'Draft active' : (missingCount > 0 ? 'Support building' : 'Workspace loaded'))
                    : 'No workspace loaded';
                setText('dashboard-heads-up-action', nextAction);
                setText('dashboard-heads-up-calendar-count', String(calendarEvents.length));
                setText('dashboard-heads-up-readiness', titleCase(hasDraft ? 'draft_ready' : (missingCount > 0 ? 'support_building' : (userId ? 'intake_or_review' : 'not_loaded')), 'Waiting'));
                setText('dashboard-heads-up-claim-chip', `claim: ${{titleCase(claimType, 'Retaliation')}}`);
                setText('dashboard-heads-up-focus-chip', `focus: ${{focus}} | state: ${{workflowState}}`);
                setText(
                    'dashboard-heads-up-status',
                    userId
                        ? `Next action: ${{nextAction}}. Recommended route: ${{effectiveRouteHint}}.`
                        : 'Load the workspace session to get a live action recommendation.'
                );
                renderChipList(
                    'dashboard-heads-up-queue',
                    operatorQueue.slice(0, 4),
                    'Load workspace and docket data to build the next-action queue.'
                );
                setText(
                    'dashboard-heads-up-preview',
                    JSON.stringify({{
                        next_action: nextAction,
                        focus,
                        recommended_route: effectiveRouteHint,
                        mike_status_stale: Boolean(dashboardState.workspaceMikeStale),
                        mike_status_contract_version: dashboardState.workspaceMikeStatusContractVersion || null,
                        claim_type: claimType,
                        case_synopsis: synopsis,
                        first_calendar_event: calendarEvents.length ? calendarSummary : null,
                    }}, null, 2)
                );
                setHref('dashboard-heads-up-open-workspace', buildSurfaceUrl('/workspace', {{
                    user_id: userId,
                    target_tab: missingCount > 0 ? 'review' : 'intake',
                    status_message: 'Opened workspace from the heads-up display.',
                }}));
                setHref('dashboard-heads-up-open-review', buildSurfaceUrl('/claim-support-review', {{
                    user_id: userId,
                    workspace_user_id: userId,
                    claim_type: claimType,
                    section: missingCount > 0 ? 'claims_for_relief' : 'overview',
                }}));
                setHref('dashboard-heads-up-open-chat', buildSurfaceUrl('/chat', {{
                    user_id: userId,
                    source: 'dashboards-heads-up',
                    case_synopsis: synopsis,
                    prefill_message: `Let's review the history of this case and identify the next action. Current focus: ${{focus}}`,
                    return_to: buildSurfaceUrl('/dashboards', {{ user_id: userId }}),
                }}));
                setHref('dashboard-heads-up-open-docket', docketPayload && docketPayload.manifest_path
                    ? buildSurfaceUrl('/dashboards', {{
                        user_id: userId,
                        manifest_path: docketPayload.manifest_path,
                    }})
                    : '#dashboard-docket-preview');
            }}

            async function loadDocketView(manifestPath) {{
                if (!manifestPath) {{
                    dashboardState.docketViewPayload = null;
                    return null;
                }}
                const payload = await fetchJson(`/api/complaint-workspace/packaged-docket/view?manifest_path=${{encodeURIComponent(manifestPath)}}&include_document_text=true&document_limit=40`);
                dashboardState.docketViewPayload = payload || null;
                return payload;
            }}

            async function loadWorkspaceDashboard() {{
                const input = document.getElementById('dashboard-workspace-user-id');
                const userId = String((input && input.value) || '').trim();
                setText('dashboard-workspace-status', 'Loading workspace session...');
                const query = userId ? `?user_id=${{encodeURIComponent(userId)}}` : '';
                try {{
                    const [payload, mikeStatus] = await Promise.all([
                        fetchJson(`/api/complaint-workspace/session${{query}}`),
                        fetchMikeIntegrationStatus(userId).catch(() => null),
                    ]);
                    dashboardState.workspaceMikeStatusUpdatedAt = new Date().toISOString();
                    renderWorkspaceCard(payload, mikeStatus);
                    const modalUser = document.getElementById('dashboard-chat-upload-user-id');
                    if (modalUser && !String(modalUser.value || '').trim()) {{
                        modalUser.value = String(((payload || {{}}).session || {{}}).user_id || userId || '');
                    }}
                }} catch (error) {{
                    setText('dashboard-workspace-status', `Workspace load failed: ${{error.message}}`);
                }}
            }}

            async function resetWorkspaceDashboard() {{
                const input = document.getElementById('dashboard-workspace-user-id');
                const userId = String((input && input.value) || '').trim();
                setText('dashboard-workspace-status', 'Resetting workspace session...');
                try {{
                    const payload = await fetchJson('/api/complaint-workspace/reset', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                        }},
                        body: JSON.stringify({{ user_id: userId || undefined }}),
                    }});
                    publishSharedSyncEvent({{
                        event_type: 'workspace.reset',
                        source: 'dashboard-reset-workspace',
                        user_id: userId,
                        payload: payload || null,
                    }});
                    await loadWorkspaceDashboard();
                    setText('dashboard-chat-upload-status', 'Workspace reset completed. Upload state now reflects the clean session.');
                }} catch (error) {{
                    setText('dashboard-workspace-status', `Workspace reset failed: ${{error.message}}`);
                }}
            }}

            async function loadDocketDashboard(reportOnly) {{
                const input = document.getElementById('dashboard-docket-manifest-path');
                const manifestPath = String((input && input.value) || '').trim();
                if (!manifestPath) {{
                    setText('dashboard-docket-status', 'Add a docket manifest path first.');
                    return;
                }}
                setText('dashboard-docket-status', reportOnly ? 'Loading parsed docket report...' : 'Loading docket dashboard...');
                const route = reportOnly
                    ? '/api/complaint-workspace/packaged-docket/operator-dashboard-report'
                    : '/api/complaint-workspace/packaged-docket/operator-dashboard';
                const suffix = reportOnly ? `&report_format=parsed` : '';
                try {{
                    const [payload] = await Promise.all([
                        fetchJson(`${{route}}?manifest_path=${{encodeURIComponent(manifestPath)}}${{suffix}}`),
                        loadDocketView(manifestPath),
                    ]);
                    renderDocketCard(payload, reportOnly ? 'parsed report' : 'operator dashboard');
                }} catch (error) {{
                    setText('dashboard-docket-status', `Docket load failed: ${{error.message}}`);
                }}
            }}

            function toggleUploadModal(forceOpen) {{
                const modal = document.getElementById('dashboard-chat-upload-modal');
                if (!modal) {{
                    return;
                }}
                const shouldOpen = typeof forceOpen === 'boolean' ? forceOpen : Boolean(modal.hidden);
                modal.hidden = !shouldOpen;
            }}

            async function submitUploadModal(event) {{
                event.preventDefault();
                const fileInput = document.getElementById('dashboard-chat-upload-files');
                const files = fileInput && fileInput.files ? Array.from(fileInput.files) : [];
                if (!files.length) {{
                    setText('dashboard-chat-upload-status', 'Choose at least one file before uploading.');
                    return;
                }}
                const form = document.getElementById('dashboard-chat-upload-form');
                const formData = new FormData();
                files.forEach((file) => formData.append('files', file));
                ['user_id', 'claim_element_id', 'kind', 'note_title', 'note'].forEach((name) => {{
                    const field = form.querySelector(`[name="${{name}}"]`);
                    if (field && String(field.value || '').trim()) {{
                        formData.append(name, String(field.value).trim());
                    }}
                }});
                formData.append('source', 'dashboard-chat-upload');
                setText('dashboard-chat-upload-status', 'Uploading files into the complaint workspace...');
                try {{
                    const payload = await fetchJson('/api/complaint-workspace/upload-local-evidence', {{
                        method: 'POST',
                        body: formData,
                    }});
                    setText('dashboard-chat-upload-status', `Uploaded ${{String(payload.imported_count || files.length)}} file(s) into the complaint workspace.`);
                    setText('dashboard-chat-upload-preview', JSON.stringify(payload, null, 2));
                    publishSharedSyncEvent({{
                        event_type: 'workspace.updated',
                        source: 'dashboard-chat-upload',
                        user_id: String((payload && payload.session && payload.session.user_id) || formData.get('user_id') || ''),
                        payload: payload || null,
                    }});
                    if (payload && payload.session) {{
                        renderWorkspaceCard(payload);
                    }} else {{
                        await loadWorkspaceDashboard();
                    }}
                    fileInput.value = '';
                    toggleUploadModal(false);
                }} catch (error) {{
                    setText('dashboard-chat-upload-status', `Upload failed: ${{error.message}}`);
                }}
            }}

            async function handleSharedSyncEvent(detail) {{
                const syncDetail = detail && typeof detail === 'object' ? detail : {{}};
                const eventType = String(syncDetail.event_type || '').trim();
                if (!eventType) {{
                    return;
                }}
                if (eventType === 'workspace.updated' || eventType === 'workspace.reset') {{
                    const incomingUserId = String(syncDetail.user_id || (((syncDetail.payload || {{}}).session || {{}}).user_id) || '').trim();
                    const currentUserId = String((document.getElementById('dashboard-workspace-user-id').value || '')).trim();
                    const payload = syncDetail.payload && typeof syncDetail.payload === 'object' ? syncDetail.payload : null;
                    const payloadSession = payload && payload.session && typeof payload.session === 'object' ? payload.session : null;
                    if (!currentUserId || !incomingUserId || incomingUserId === currentUserId) {{
                        if (payloadSession) {{
                            const userInput = document.getElementById('dashboard-workspace-user-id');
                            if (userInput && !String(userInput.value || '').trim() && incomingUserId) {{
                                userInput.value = incomingUserId;
                            }}
                            const mikeStatus = payload && payload.mike_integration_status && typeof payload.mike_integration_status === 'object'
                                ? payload.mike_integration_status
                                : await fetchMikeIntegrationStatus(incomingUserId || currentUserId).catch(() => null);
                            dashboardState.workspaceMikeStatusUpdatedAt = new Date().toISOString();
                            renderWorkspaceCard(payload, mikeStatus);
                        }} else {{
                            await loadWorkspaceDashboard();
                        }}
                    }}
                }}
                if (eventType === 'docket.updated' || eventType === 'docket.persisted') {{
                    const incomingManifestPath = String(syncDetail.manifest_path || ((syncDetail.payload || {{}}).manifest_path) || ((syncDetail.payload || {{}}).manifest_json_path) || '').trim();
                    const currentManifestPath = String((document.getElementById('dashboard-docket-manifest-path').value || '')).trim();
                    if (!currentManifestPath || !incomingManifestPath || incomingManifestPath === currentManifestPath) {{
                        if (incomingManifestPath && currentManifestPath !== incomingManifestPath) {{
                            document.getElementById('dashboard-docket-manifest-path').value = incomingManifestPath;
                        }}
                        await loadDocketDashboard(false);
                    }}
                }}
            }}

            document.getElementById('dashboard-load-workspace').addEventListener('click', loadWorkspaceDashboard);
            document.getElementById('dashboard-reset-workspace').addEventListener('click', resetWorkspaceDashboard);
            document.getElementById('dashboard-unload-workspace').addEventListener('click', function() {{
                clearWorkspaceCard('Workspace session unloaded from the dashboard.');
            }});
            document.getElementById('dashboard-load-docket').addEventListener('click', function() {{ loadDocketDashboard(false); }});
            document.getElementById('dashboard-load-docket-report').addEventListener('click', function() {{ loadDocketDashboard(true); }});
            document.getElementById('dashboard-unload-docket').addEventListener('click', function() {{
                clearDocketCard('Packaged docket unloaded from the dashboard.');
            }});
            document.getElementById('dashboard-load-docket-dataset').addEventListener('click', function() {{ loadDocketDatasetDashboard('view'); }});
            document.getElementById('dashboard-search-docket-dataset').addEventListener('click', function() {{ loadDocketDatasetDashboard('search'); }});
	            document.getElementById('dashboard-load-docket-dataset-graph').addEventListener('click', function() {{ loadDocketDatasetDashboard('graph'); }});
	            document.querySelectorAll('[data-docket-query]').forEach(function(button) {{
	                button.addEventListener('click', applyDocketQuickSearch);
	            }});
	            document.querySelectorAll('[data-annotation-tag]').forEach(function(button) {{
	                button.addEventListener('click', addAnnotationTag);
	            }});
	            const docketFilingList = document.getElementById('docket-filing-list');
	            if (docketFilingList) {{
	                docketFilingList.addEventListener('click', handleDocketFilingListClick);
	            }}
	            const docketDatasetPathInput = document.getElementById('dashboard-docket-dataset-path');
	            if (docketDatasetPathInput) {{
	                docketDatasetPathInput.addEventListener('input', function() {{
	                    dashboardState.docketDatasetLoaded = false;
	                    dashboardState.docketDatasetStatus = 'idle';
	                    dashboardState.docketDatasetError = '';
	                    dashboardState.docketDatasetCalendarEvents = [];
	                    dashboardState.docketDatasetSearchCount = 0;
	                    dashboardState.docketDocuments = [];
	                    dashboardState.selectedDocketDocumentIndex = -1;
	                    dashboardState.selectedDatasetDocument = null;
	                    renderDocketFilingList([]);
	                    updateSelectedDocketDocumentPanel(null);
	                    updateDocketSummaryStrip(0, []);
	                    setText('dashboard-docket-dataset-status', 'Choose a saved filing set, then load it to review docket filings.');
	                    updateDocketDatasetReadiness();
	                    renderHeadsUpCard();
	                }});
	            }}
	            const docketDatasetQueryInput = document.getElementById('dashboard-docket-dataset-query');
	            if (docketDatasetQueryInput) {{
	                docketDatasetQueryInput.addEventListener('input', updateDocketDatasetReadiness);
	            }}
		            document.getElementById('dashboard-load-workspace-dataset').addEventListener('click', function() {{ loadWorkspaceDatasetDashboard('view'); }});
		            document.getElementById('dashboard-load-workspace-dataset-step1').addEventListener('click', function() {{ loadWorkspaceDatasetDashboard('view'); }});
		            document.getElementById('dashboard-search-workspace-dataset').addEventListener('click', function() {{ loadWorkspaceDatasetDashboard('search'); }});
	            document.getElementById('workspace-materials-next-action-link').addEventListener('click', handleWorkspaceMaterialsNextAction);
	            document.querySelectorAll('#dashboard-section-menu .jump-link').forEach(function(link) {{
	                link.addEventListener('click', collapseMobileSectionMenuAfterChoice);
	            }});
	            document.querySelectorAll('[data-workspace-dataset-preset]').forEach(function(button) {{
	                button.addEventListener('click', applyWorkspaceDatasetPreset);
	            }});
            document.querySelectorAll('[data-lane-source-type]').forEach(function(card) {{
                const chooseLane = function() {{
                    const sourceType = String(card.dataset.laneSourceType || '');
                    const sourceTypeInput = document.getElementById('dashboard-workspace-dataset-source-type');
                    if (sourceTypeInput) {{
                        sourceTypeInput.value = sourceType;
                    }}
                    setWorkspaceLane(sourceType);
                }};
                card.addEventListener('click', chooseLane);
                card.addEventListener('keydown', function(event) {{
                    if (event.key === 'Enter' || event.key === ' ') {{
                        event.preventDefault();
                        chooseLane();
                    }}
                }});
            }});
            const workspaceSourceType = document.getElementById('dashboard-workspace-dataset-source-type');
            if (workspaceSourceType) {{
                workspaceSourceType.addEventListener('change', function(event) {{
                    setWorkspaceLane(event.currentTarget && event.currentTarget.value);
                }});
            }}
            const workspaceDatasetPathInput = document.getElementById('dashboard-workspace-dataset-path');
            if (workspaceDatasetPathInput) {{
	                workspaceDatasetPathInput.addEventListener('input', function() {{
	                    dashboardState.workspaceDatasetLoaded = false;
	                    dashboardState.workspaceDatasetStatus = 'idle';
	                    dashboardState.workspaceDatasetError = '';
	                    dashboardState.workspaceGraphReady = false;
                    setText('workspace-dataset-load-state', 'Not loaded');
                    setText('workspace-dataset-run-state', 'Open a saved file, then search or check connections and duties.');
                    updateWorkspaceDatasetReadiness();
                }});
            }}
            document.getElementById('dashboard-load-workspace-graph').addEventListener('click', loadWorkspaceGraphExplorer);
            document.getElementById('dashboard-open-dataset-graph').addEventListener('click', function(event) {{
                const preflight = getWorkspaceDatasetPreflight();
                if (!preflight.canGraph) {{
                    event.preventDefault();
                    setText('workspace-action-preflight', preflight.reason);
                    setText('dashboard-workspace-graph-status', preflight.reason);
                }}
            }});
            document.getElementById('dashboard-run-deontic-check').addEventListener('click', function(event) {{
                const preflight = getWorkspaceDatasetPreflight();
                if (!preflight.canDeontic) {{
                    event.preventDefault();
                    setText('workspace-action-preflight', preflight.reason);
                    setText('dashboard-workspace-graph-status', preflight.reason);
                }}
            }});
            document.querySelectorAll('[data-dashboard-graph-preset]').forEach(function(button) {{
                button.addEventListener('click', applyGraphPreset);
            }});
            document.getElementById('dashboard-save-dataset-annotation').addEventListener('click', saveDatasetDocumentAnnotation);
            document.getElementById('dashboard-use-loaded-document').addEventListener('click', useLoadedDatasetDocument);
            const annotationTagsInput = document.getElementById('dashboard-dataset-annotation-tags');
            if (annotationTagsInput) {{
                annotationTagsInput.addEventListener('input', updateDocketCurrentTask);
            }}
            const annotationNoteInput = document.getElementById('dashboard-dataset-annotation-note');
            if (annotationNoteInput) {{
                annotationNoteInput.addEventListener('input', updateDocketCurrentTask);
            }}
            document.getElementById('dashboard-open-upload-modal').addEventListener('click', function() {{ toggleUploadModal(true); }});
            document.getElementById('dashboard-close-upload-modal').addEventListener('click', function() {{ toggleUploadModal(false); }});
            document.getElementById('dashboard-cancel-upload-modal').addEventListener('click', function() {{ toggleUploadModal(false); }});
            document.getElementById('dashboard-chat-upload-form').addEventListener('submit', submitUploadModal);
            document.getElementById('dashboard-chat-upload-modal').addEventListener('click', function(event) {{
                if (event.target === event.currentTarget) {{
                    toggleUploadModal(false);
                }}
            }});
            document.getElementById('dashboard-close-note-preflight-modal').addEventListener('click', function() {{ toggleNotePreflightModal(false); }});
            document.getElementById('dashboard-cancel-note-preflight').addEventListener('click', function() {{ toggleNotePreflightModal(false); }});
            document.getElementById('dashboard-confirm-note-preflight').addEventListener('click', function() {{
                dashboardState.notePreflightApproved = true;
                toggleNotePreflightModal(false);
                saveDatasetDocumentAnnotation();
            }});
            window.__complaintDashboardUI = {{
                selectDatasetDocument: selectDatasetDocument,
                updateDocumentContextBar: updateDocumentContextBar,
                state: dashboardState,
            }};
            window.addEventListener(syncEventName, function(event) {{
                handleSharedSyncEvent(event && event.detail ? event.detail : null);
            }});
            window.addEventListener('storage', function(event) {{
                if (!event || event.key !== syncEventStorageKey || !event.newValue) {{
                    return;
                }}
                try {{
                    handleSharedSyncEvent(JSON.parse(event.newValue));
                }} catch (error) {{
                    // Ignore malformed cross-tab sync payloads.
                }}
            }});
            window.addEventListener('resize', collapseMobileSectionMenu);

            collapseMobileSectionMenu();
            resetWorkflowRail();
            setWorkspaceLane('');
            updateSelectedDocketDocumentPanel(null);
            renderDocketFilingList([]);
            updateDocketSummaryStrip(0, []);
            updateDeadlineRiskSummary([]);
            updateDocketCurrentTask();
            updateDocketDatasetReadiness();
            loadWorkspaceDashboard();
            if (String(document.getElementById('dashboard-docket-manifest-path').value || '').trim()) {{
                loadDocketDashboard(false);
            }}
            if (String(document.getElementById('dashboard-docket-dataset-path').value || '').trim()) {{
                loadDocketDatasetDashboard('view');
            }}
            if (String(document.getElementById('dashboard-workspace-dataset-path').value || '').trim()) {{
                loadWorkspaceDatasetDashboard('view');
            }}
        }})();
    </script>
</body>
</html>
"""


def create_dashboard_ui_router(
    *,
    fixtures: DashboardFixtures | None = None,
) -> APIRouter:
    """Create dashboard routes bound to one explicit fixture catalog.

    The default catalog is resolved when the router is created. Tests and preview
    servers can inject a freshly built catalog without mutating live module state.
    """
    route_fixtures = _resolve_dashboard_fixtures(fixtures)
    router = APIRouter()

    @router.get("/mcp", response_class=HTMLResponse)
    async def legacy_mcp_dashboard_root() -> str:
        return _render_shell_page(
            get_default_ipfs_dashboard_entry(fixtures=route_fixtures),
            route_fixtures,
        )

    @router.get("/api/mcp/analytics/history")
    async def mcp_analytics_history() -> dict[str, Any]:
        return {
            "history": [
                {
                    "last_updated": "2026-03-22T09:00:00+00:00",
                    "success_rate": 91.2,
                    "average_query_time": 1.42,
                },
                {
                    "last_updated": "2026-03-22T10:00:00+00:00",
                    "success_rate": 94.8,
                    "average_query_time": 1.35,
                },
                {
                    "last_updated": "2026-03-22T11:00:00+00:00",
                    "success_rate": 96.4,
                    "average_query_time": 1.28,
                },
            ]
        }

    @router.get("/dashboards", response_class=HTMLResponse)
    async def dashboard_hub(
        user_id: str = "",
        manifest_path: str = "",
        docket_dataset_path: str = "",
        workspace_dataset_path: str = "",
    ) -> str:
        return _render_dashboard_hub(
            default_user_id=str(user_id or "").strip(),
            default_manifest_path=str(manifest_path or "").strip(),
            default_docket_dataset_path=str(docket_dataset_path or "").strip(),
            default_workspace_dataset_path=str(workspace_dataset_path or "").strip(),
            fixtures=route_fixtures,
        )

    @router.get("/dashboards/ipfs-datasets/{slug}", response_class=HTMLResponse)
    async def ipfs_datasets_dashboard_shell(slug: str) -> str:
        entry = get_ipfs_dashboard_entry(slug, fixtures=route_fixtures)
        if entry is None:
            raise HTTPException(status_code=404, detail="Dashboard not found")
        return _render_shell_page(entry, route_fixtures)

    @router.get("/dashboards/raw/ipfs-datasets/{slug}", response_class=HTMLResponse)
    async def ipfs_datasets_dashboard_raw(slug: str) -> str:
        entry = get_ipfs_dashboard_entry(slug, fixtures=route_fixtures)
        if entry is None:
            raise HTTPException(status_code=404, detail="Dashboard not found")
        return _render_ipfs_dashboard(entry)

    return router


def attach_dashboard_ui_routes(
    app: FastAPI,
    *,
    fixtures: DashboardFixtures | None = None,
) -> FastAPI:
    if not any(
        getattr(route, "path", None) == "/ipfs-datasets-static" for route in app.routes
    ):
        app.mount(
            "/ipfs-datasets-static",
            StaticFiles(directory=str(_IPFS_DATASETS_STATIC_DIR), check_dir=False),
            name="ipfs-datasets-static",
        )
    return attach_router_routes(
        app,
        create_dashboard_ui_router(fixtures=fixtures),
    )
