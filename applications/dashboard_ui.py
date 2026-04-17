from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import ChainableUndefined, Environment, FileSystemLoader, select_autoescape


@dataclass(frozen=True)
class DashboardEntry:
    slug: str
    title: str
    template_name: str
    summary: str
    category: str


_IPFS_DATASETS_TEMPLATES_DIR = (
    Path(__file__).resolve().parent.parent
    / "ipfs_datasets_py"
    / "ipfs_datasets_py"
    / "templates"
)
_IPFS_DATASETS_STATIC_DIR = (
    Path(__file__).resolve().parent.parent
    / "ipfs_datasets_py"
    / "ipfs_datasets_py"
    / "static"
)

_COMPLAINT_DASHBOARD_LINKS = [
    ("Landing", "/"),
    ("Account", "/home"),
    ("Chat", "/chat"),
    ("Profile", "/profile"),
    ("Results", "/results"),
    ("Workspace", "/workspace"),
    ("Review", "/claim-support-review"),
    ("Builder", "/document"),
    ("WYSIWYG", "/wysiwyg"),
    ("Trace", "/document/optimization-trace"),
    ("Dashboards", "/dashboards"),
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

_IPFS_DASHBOARD_MAP = {entry.slug: entry for entry in _IPFS_DASHBOARD_ENTRIES}

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
    template = _IPFS_DASHBOARD_ENV.get_template(entry.template_name)
    try:
        return template.render(**_build_ipfs_dashboard_context(entry))
    except Exception as exc:
        return f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
    <title>{escape(entry.title)} | Compatibility Preview</title>
    <style>
        body {{ font-family: 'Public Sans', Arial, sans-serif; margin: 0; background: #f6f4ef; color: #122033; }}
        main {{ max-width: 960px; margin: 0 auto; padding: 32px 24px 48px; }}
        .card {{ background: white; border-radius: 18px; padding: 24px; box-shadow: 0 12px 32px rgba(17, 34, 51, 0.08); }}
        h1 {{ margin-top: 0; }}
        pre {{ white-space: pre-wrap; overflow-wrap: anywhere; background: #f3f5f7; padding: 16px; border-radius: 12px; }}
        a {{ color: #0a4f66; font-weight: 600; }}
    </style>
</head>
<body>
    <main>
        <section class=\"card\">
            <h1>{escape(entry.title)}</h1>
            <p>{escape(entry.summary)} This legacy template is mounted through the complaint-generator dashboard hub in compatibility-preview mode.</p>
            <p><a href=\"/dashboards\">Back to dashboard hub</a></p>
            <pre>{escape(str(exc))}</pre>
        </section>
    </main>
</body>
</html>
"""


def _render_shell_page(entry: DashboardEntry) -> str:
    shell_links = "".join(
        f'<a class="shell-link{' is-active' if item.slug == entry.slug else ''}" href="/dashboards/ipfs-datasets/{escape(item.slug)}">{escape(item.title)}</a>'
        for item in _IPFS_DASHBOARD_ENTRIES
    )
    top_links = "".join(
        f'<a class="surface-link" href="{escape(path)}">{escape(label)}</a>'
        for label, path in _COMPLAINT_DASHBOARD_LINKS
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
) -> str:
    complaint_links = "".join(
        f'<li><a href="{escape(path)}">{escape(label)}</a></li>'
        for label, path in _COMPLAINT_DASHBOARD_LINKS
    )
    ipfs_sections: dict[str, list[DashboardEntry]] = {}
    for entry in _IPFS_DASHBOARD_ENTRIES:
        ipfs_sections.setdefault(entry.category, []).append(entry)
    ipfs_markup = "".join(
        f"<section><h2>{escape(category)}</h2><ul>" + "".join(
            f'<li><a href="/dashboards/ipfs-datasets/{escape(entry.slug)}">{escape(entry.title)}</a> <span>{escape(entry.summary)}</span></li>'
            for entry in entries
        ) + "</ul></section>"
        for category, entries in ipfs_sections.items()
    )
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
        .surface-pills, .button-row, .stat-grid, .chip-row {{ display: flex; flex-wrap: wrap; gap: 10px; }}
        .surface-pills a, button, .modal-link {{
            border: 0;
            border-radius: 999px;
            padding: 11px 16px;
            text-decoration: none;
            font-weight: 700;
        }}
        .surface-pills a {{ background: rgba(255,255,255,0.12); color: white; }}
        button {{ background: linear-gradient(135deg, var(--accent), var(--accent-strong)); color: white; cursor: pointer; }}
        button.secondary {{ background: rgba(17, 92, 99, 0.10); color: var(--accent-strong); border: 1px solid rgba(17, 92, 99, 0.16); }}
        button:disabled {{ opacity: 0.65; cursor: wait; }}
        .workspace-cards {{ display: grid; gap: 24px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }}
        .dashboard-card {{ background: var(--surface); border-radius: var(--radius-xl); padding: 24px; box-shadow: var(--shadow); border: 1px solid var(--line); }}
        .dashboard-card h2 {{ margin-bottom: 10px; }}
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
            .hero-grid, .field-row {{ grid-template-columns: 1fr; }}
        }}
    </style>
</head>
<body>
    <header>
        <div class="header-copy">
            <div class="eyebrow">Complaint Operations Center</div>
            <h1>Unified Dashboard Hub</h1>
            <p>One complaint-generator entry point for live workspace state, packaged docket status, chat upload intake, and the legacy dashboard shells that already ship with the app.</p>
        </div>
        <div class="surface-pills">{''.join(f'<a href="{escape(path)}">{escape(label)}</a>' for label, path in _COMPLAINT_DASHBOARD_LINKS)}</div>
    </header>
    <main>
        <section class="hero-grid">
            <article class="hero-card">
                <div class="eyebrow" style="color: #115c63;">Live Complaint Cards</div>
                <h2>Workspaces, dockets, and chat uploads now belong on the same screen.</h2>
                <p>The complaint-native cards below read from the same workspace session APIs, packaged docket tools, and evidence intake flow used elsewhere in the app. This makes the dashboard a working surface instead of a link directory.</p>
                <div class="chip-row">
                    <span class="chip good">Workspace session continuity</span>
                    <span class="chip warm">Packaged docket monitoring</span>
                    <span class="chip">Chat upload modal for files and notes</span>
                    <span class="chip">Heads-up display for next actions and case calendar</span>
                </div>
            </article>
            <article class="card">
                <h2>Quick Surface Links</h2>
                <p>Use these when you want to jump straight into the richer dedicated surface after checking the dashboard card.</p>
                <ul>{complaint_links}</ul>
            </article>
        </section>

        <section class="workspace-cards">
            <article class="dashboard-card">
                <div class="eyebrow" style="color: var(--accent);">Workspace Card</div>
                <h2>Complaint Workspace Snapshot</h2>
                <p>Load the shared complaint session and see the intake, evidence, and draft state that currently gates review and builder handoffs.</p>
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
                </div>
                <div class="status-line" id="dashboard-workspace-status">Ready to load the complaint workspace session.</div>
                <pre id="dashboard-workspace-preview">Workspace session details will appear here.</pre>
            </article>

            <article class="dashboard-card">
                <div class="eyebrow" style="color: var(--accent);">Docket Card</div>
                <h2>Packaged Docket Dashboard</h2>
                <p>Load the packaged docket operator dashboard from a manifest path without leaving the complaint-generator shell.</p>
                <label class="field-label" for="dashboard-docket-manifest-path">Manifest Path</label>
                <input id="dashboard-docket-manifest-path" type="text" value="{escape(default_manifest_path)}" placeholder="/absolute/path/to/docket-manifest.json">
                <div class="button-row" style="margin-top: 12px;">
                    <button id="dashboard-load-docket" type="button">Load Docket Dashboard</button>
                    <button id="dashboard-load-docket-report" type="button" class="secondary">Load Parsed Report</button>
                    <button id="dashboard-unload-docket" type="button" class="secondary">Unload Docket</button>
                </div>
                <div class="stat-grid">
                    <div class="stat-card"><strong id="dashboard-docket-queue">0</strong><span>Queue items</span></div>
                    <div class="stat-card"><strong id="dashboard-docket-high">0</strong><span>High priority items</span></div>
                    <div class="stat-card"><strong id="dashboard-docket-runs">0</strong><span>Recorded runs</span></div>
                    <div class="stat-card"><strong id="dashboard-docket-calendar-count">0</strong><span>Calendar events</span></div>
                </div>
                <div class="chip-row" style="margin-top: 14px;">
                    <span class="chip" id="dashboard-docket-source-chip">source: waiting</span>
                    <span class="chip" id="dashboard-docket-manifest-chip">manifest: waiting</span>
                    <span class="chip" id="dashboard-docket-calendar-chip">calendar: waiting</span>
                </div>
                <div class="status-line" id="dashboard-docket-status">Add a packaged docket manifest path to inspect the operator dashboard.</div>
                <div style="margin-top: 14px;">
                    <div class="field-label">Case Calendar Preview</div>
                    <div class="chip-row" id="dashboard-docket-calendar-list">
                        <span class="chip">Load a docket to preview hearings, deadlines, and conferences.</span>
                    </div>
                </div>
                <pre id="dashboard-docket-preview">Packaged docket details will appear here.</pre>
            </article>

            <article class="dashboard-card" id="docket-dataset-parquet-dashboard">
                <div class="eyebrow" style="color: var(--accent);">Docket Dataset</div>
                <h2>Docket Dataset Parquet Dashboard</h2>
                <p>Review docket dataset parquet files through the same ipfs_datasets_py dataset loader, search index, graph projection, and case-calendar extraction used by the MCP tools.</p>
                <label class="field-label" for="dashboard-docket-dataset-path">Docket Dataset Path</label>
                <input id="dashboard-docket-dataset-path" type="text" value="{escape(default_docket_dataset_path)}" placeholder="/absolute/path/to/docket.dataset.parquet">
                <div class="field-row" style="margin-top: 12px;">
                    <div>
                        <label class="field-label" for="dashboard-docket-dataset-query">Search Query</label>
                        <input id="dashboard-docket-dataset-query" type="text" placeholder="hearing, deadline, motion, due process">
                    </div>
                    <div>
                        <label class="field-label" for="dashboard-docket-dataset-input-type">Input</label>
                        <select id="dashboard-docket-dataset-input-type">
                            <option value="single" selected>Single parquet</option>
                            <option value="packaged">Packaged manifest</option>
                            <option value="json">Source JSON</option>
                        </select>
                    </div>
                </div>
                <div class="button-row" style="margin-top: 12px;">
                    <button id="dashboard-load-docket-dataset" type="button">Load Docket Dataset</button>
                    <button id="dashboard-search-docket-dataset" type="button" class="secondary">Search Docket Dataset</button>
                    <button id="dashboard-load-docket-dataset-graph" type="button" class="secondary">Load Graph</button>
                </div>
                <div class="stat-grid">
                    <div class="stat-card"><strong id="dashboard-docket-dataset-documents">0</strong><span>Docket documents</span></div>
                    <div class="stat-card"><strong id="dashboard-docket-dataset-events">0</strong><span>Calendar events</span></div>
                    <div class="stat-card"><strong id="dashboard-docket-dataset-results">0</strong><span>Search results</span></div>
                    <div class="stat-card"><strong id="dashboard-docket-dataset-graph-count">0</strong><span>Graph links</span></div>
                </div>
                <div class="chip-row" style="margin-top: 14px;">
                    <span class="chip" id="dashboard-docket-dataset-case-chip">case: waiting</span>
                    <span class="chip" id="dashboard-docket-dataset-source-chip">source: waiting</span>
                </div>
                <div class="status-line" id="dashboard-docket-dataset-status">Add a docket dataset parquet path to review docket filings.</div>
                <pre id="dashboard-docket-dataset-preview">Docket dataset details will appear here.</pre>
            </article>

            <article class="dashboard-card" id="workspace-dataset-parquet-dashboard">
                <div class="eyebrow" style="color: var(--accent);">Workspace Dataset</div>
                <h2>Workspace Dataset Parquet Entry Point</h2>
                <p>Browse and search ipfs_datasets_py workspace dataset parquet files, then use filters that match the stored workspace schema.</p>
                <label class="field-label" for="dashboard-workspace-dataset-path">Workspace Dataset Path</label>
                <input id="dashboard-workspace-dataset-path" type="text" value="{escape(default_workspace_dataset_path)}" placeholder="/absolute/path/to/workspace.dataset.parquet">
                <div class="modal-grid">
                    <div>
                        <label class="field-label" for="dashboard-workspace-dataset-input-type">Input</label>
                        <select id="dashboard-workspace-dataset-input-type">
                            <option value="single" selected>Single parquet</option>
                            <option value="packaged">Packaged manifest</option>
                            <option value="json">Source JSON</option>
                        </select>
                    </div>
                    <div>
                        <label class="field-label" for="dashboard-workspace-dataset-query">Search Query</label>
                        <input id="dashboard-workspace-dataset-query" type="text" placeholder="accommodation, retaliation, notice">
                    </div>
                    <div>
                        <label class="field-label" for="dashboard-workspace-dataset-claim-type">Claim Type</label>
                        <input id="dashboard-workspace-dataset-claim-type" type="text" placeholder="housing_discrimination">
                    </div>
                    <div>
                        <label class="field-label" for="dashboard-workspace-dataset-document-type">Document Type</label>
                        <input id="dashboard-workspace-dataset-document-type" type="text" placeholder="email, pdf, notice">
                    </div>
                </div>
                <div class="button-row" style="margin-top: 12px;">
                    <button id="dashboard-load-workspace-dataset" type="button">Load Workspace Dataset</button>
                    <button id="dashboard-search-workspace-dataset" type="button" class="secondary">Search Workspace Dataset</button>
                </div>
                <div class="stat-grid">
                    <div class="stat-card"><strong id="dashboard-workspace-dataset-documents">0</strong><span>Workspace documents</span></div>
                    <div class="stat-card"><strong id="dashboard-workspace-dataset-collections">0</strong><span>Collections</span></div>
                    <div class="stat-card"><strong id="dashboard-workspace-dataset-results">0</strong><span>Search results</span></div>
                    <div class="stat-card"><strong id="dashboard-workspace-dataset-entities">0</strong><span>Graph entities</span></div>
                </div>
                <div class="chip-row" style="margin-top: 14px;">
                    <span class="chip" id="dashboard-workspace-dataset-workspace-chip">workspace: waiting</span>
                    <span class="chip" id="dashboard-workspace-dataset-source-chip">source: waiting</span>
                </div>
                <div class="status-line" id="dashboard-workspace-dataset-status">Add a workspace dataset parquet path to enter the dataset workspace.</div>
                <pre id="dashboard-workspace-dataset-preview">Workspace dataset details will appear here.</pre>
            </article>

            <article class="dashboard-card">
                <div class="eyebrow" style="color: var(--accent);">Chat Card</div>
                <h2>Chat Upload Modal</h2>
                <p>Open a modal that lets intake staff or operators attach photos, videos, PDFs, mailbox exports, or notes directly into the complaint workspace evidence flow.</p>
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

            <article class="dashboard-card">
                <div class="eyebrow" style="color: var(--accent);">Heads-Up Display</div>
                <h2>Heads-Up Display Dashboard</h2>
                <p>Get a front-page glance at the next legal action to perform, where to continue the case conversation, whether the workspace record is ready, and whether the docket exposes any calendar or hearing events.</p>
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

        <section class="legacy-grid">
            <section class="card">
                <h2>Complaint Generator Surfaces</h2>
                <ul>{complaint_links}</ul>
            </section>
            <section class="card">
                <h2>ipfs_datasets_py Dashboards</h2>
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
                docketPayload: null,
                docketViewPayload: null,
            }};

            function parseCount(value, fallback) {{
                const numeric = Number(value);
                return Number.isFinite(numeric) ? numeric : fallback;
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

            function setHref(id, value) {{
                const node = document.getElementById(id);
                if (node) {{
                    node.href = value;
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

            function renderWorkspaceCard(payload) {{
                const session = payload && payload.session ? payload.session : {{}};
                const review = payload && payload.review ? payload.review : {{}};
                const overview = review && review.overview ? review.overview : {{}};
                const answers = session && session.intake_answers ? Object.keys(session.intake_answers).length : 0;
                const evidence = session && session.evidence ? session.evidence : {{}};
                const evidenceCount = parseCount((evidence.testimony || []).length, 0) + parseCount((evidence.documents || []).length, 0);
                const hasDraft = Boolean(payload && payload.draft) || Boolean(session && session.draft);
                setText('dashboard-workspace-answered', String(answers));
                setText('dashboard-workspace-evidence', String(evidenceCount));
                setText('dashboard-workspace-missing', String(parseCount(overview.missing_elements, 0)));
                setText('dashboard-workspace-draft', hasDraft ? 'Yes' : 'No');
                setText('dashboard-workspace-session-chip', `session: ${{String(session.user_id || 'unknown')}}`);
                const readiness = payload && payload.complaint_readiness ? payload.complaint_readiness : {{}};
                setText('dashboard-workspace-route-chip', `next route: ${{String(readiness.recommended_route || '/workspace')}}`);
                setText('dashboard-workspace-status', `Loaded workspace session for ${{String(session.user_id || 'default user')}}.`);
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
                    }}, null, 2)
                );
                dashboardState.workspacePayload = payload || null;
                renderHeadsUpCard();
            }}

            function clearWorkspaceCard(reason) {{
                dashboardState.workspacePayload = null;
                setText('dashboard-workspace-answered', '0');
                setText('dashboard-workspace-evidence', '0');
                setText('dashboard-workspace-missing', '0');
                setText('dashboard-workspace-draft', 'No');
                setText('dashboard-workspace-session-chip', 'session: not loaded');
                setText('dashboard-workspace-route-chip', 'next route: waiting');
                setText('dashboard-workspace-status', reason || 'Workspace session unloaded.');
                setText('dashboard-workspace-preview', 'Workspace session details will appear here.');
                renderHeadsUpCard();
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
                setText('dashboard-docket-source-chip', `source: ${{String((payload && payload.source) || label || 'unknown')}}`);
                setText('dashboard-docket-manifest-chip', `manifest: ${{String((payload && payload.manifest_path) || 'not set')}}`);
                setText(
                    'dashboard-docket-calendar-chip',
                    calendarEvents.length
                        ? `calendar: ${{summarizeCalendarEvent(calendarEvents[0])}}`
                        : 'calendar: no events found'
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
                const calendarEvents = prioritizeCalendarEvents(extractCalendarEvents(payload || {{}}).length ? extractCalendarEvents(payload || {{}}) : extractCalendarEventsFromDocketView(payload || {{}}));
                const graph = (payload && payload.knowledge_graph) || {{}};
                const issueLinkCount = Number(graph.issue_link_count || graph.relationship_count || 0);
                setText('dashboard-docket-dataset-documents', String(Number(summary.document_count || documents.length || 0)));
                setText('dashboard-docket-dataset-events', String(calendarEvents.length));
                setText('dashboard-docket-dataset-results', String(Number(searchResults.result_count || results.length || 0)));
                setText('dashboard-docket-dataset-graph-count', String(issueLinkCount));
                setText('dashboard-docket-dataset-case-chip', `case: ${{String((payload && (payload.case_name || payload.docket_id)) || summary.case_name || summary.docket_id || 'unknown')}}`);
                setText('dashboard-docket-dataset-source-chip', `source: ${{String((payload && payload.source) || label || 'dataset')}}`);
                setText('dashboard-docket-dataset-status', `Loaded docket dataset ${{label || 'view'}} through ipfs_datasets_py.`);
                setText('dashboard-docket-dataset-preview', JSON.stringify(Object.assign({{}}, payload || {{}}, {{
                    extracted_calendar_events: calendarEvents.slice(0, 10),
                }}), null, 2));
            }}

            function renderWorkspaceDatasetCard(payload, label) {{
                const summary = (payload && payload.summary) || {{}};
                const documents = Array.isArray(payload && payload.documents) ? payload.documents : [];
                const collections = Array.isArray(payload && payload.collections) ? payload.collections : [];
                const searchResults = (payload && payload.search_results) || {{}};
                const results = Array.isArray(searchResults.results) ? searchResults.results : [];
                setText('dashboard-workspace-dataset-documents', String(Number(summary.document_count || documents.length || 0)));
                setText('dashboard-workspace-dataset-collections', String(Number(summary.collection_count || collections.length || 0)));
                setText('dashboard-workspace-dataset-results', String(Number(searchResults.result_count || results.length || 0)));
                setText('dashboard-workspace-dataset-entities', String(Number(summary.knowledge_graph_entity_count || 0)));
                setText('dashboard-workspace-dataset-workspace-chip', `workspace: ${{String(summary.workspace_name || summary.workspace_id || 'unknown')}}`);
                setText('dashboard-workspace-dataset-source-chip', `source: ${{String((payload && payload.source) || label || 'dataset')}}`);
                setText('dashboard-workspace-dataset-status', `Loaded workspace dataset ${{label || 'view'}} through ipfs_datasets_py.`);
                setText('dashboard-workspace-dataset-preview', JSON.stringify(payload || {{}}, null, 2));
            }}

            async function loadDocketDatasetDashboard(mode) {{
                const statusId = 'dashboard-docket-dataset-status';
                setText(statusId, mode === 'search' ? 'Searching docket dataset parquet...' : mode === 'graph' ? 'Loading docket dataset graph...' : 'Loading docket dataset parquet...');
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
                    setText(statusId, `Docket dataset load failed: ${{error.message}}`);
                }}
            }}

            async function loadWorkspaceDatasetDashboard(mode) {{
                const statusId = 'dashboard-workspace-dataset-status';
                setText(statusId, mode === 'search' ? 'Searching workspace dataset parquet...' : 'Loading workspace dataset parquet...');
                try {{
                    const extra = {{
                        include_document_text: 'true',
                        document_limit: '40',
                        claim_type: String((document.getElementById('dashboard-workspace-dataset-claim-type') || {{}}).value || '').trim(),
                        document_type: String((document.getElementById('dashboard-workspace-dataset-document-type') || {{}}).value || '').trim(),
                    }};
                    let endpoint = '/api/complaint-workspace/workspace-dataset/view';
                    if (mode === 'search') {{
                        const query = String((document.getElementById('dashboard-workspace-dataset-query') || {{}}).value || '').trim();
                        if (!query) {{
                            throw new Error('Enter a workspace dataset query before searching.');
                        }}
                        endpoint = '/api/complaint-workspace/workspace-dataset/search';
                        extra.query = query;
                        extra.top_k = '10';
                    }}
                    const params = datasetQueryParams('dashboard-workspace-dataset-path', 'dashboard-workspace-dataset-input-type', extra);
                    const payload = await fetchJson(`${{endpoint}}?${{params.toString()}}`);
                    renderWorkspaceDatasetCard(payload, mode || 'view');
                }} catch (error) {{
                    setText(statusId, `Workspace dataset load failed: ${{error.message}}`);
                }}
            }}

            function clearDocketCard(reason) {{
                dashboardState.docketPayload = null;
                dashboardState.docketViewPayload = null;
                setText('dashboard-docket-queue', '0');
                setText('dashboard-docket-high', '0');
                setText('dashboard-docket-runs', '0');
                setText('dashboard-docket-calendar-count', '0');
                setText('dashboard-docket-source-chip', 'source: not loaded');
                setText('dashboard-docket-manifest-chip', 'manifest: not set');
                setText('dashboard-docket-calendar-chip', 'calendar: waiting');
                setText('dashboard-docket-status', reason || 'Packaged docket unloaded.');
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
                const calendarEvents = prioritizeCalendarEvents(docketViewCalendarEvents.length ? docketViewCalendarEvents : dashboardCalendarEvents);
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
                        ? `Next action: ${{nextAction}}. Recommended route: ${{routeHint}}.`
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
                        recommended_route: routeHint,
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
                    const payload = await fetchJson(`/api/complaint-workspace/session${{query}}`);
                    renderWorkspaceCard(payload);
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
                    if (!currentUserId || !incomingUserId || incomingUserId === currentUserId) {{
                        if (syncDetail.payload && syncDetail.payload.session) {{
                            renderWorkspaceCard(syncDetail.payload);
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
            document.getElementById('dashboard-load-workspace-dataset').addEventListener('click', function() {{ loadWorkspaceDatasetDashboard('view'); }});
            document.getElementById('dashboard-search-workspace-dataset').addEventListener('click', function() {{ loadWorkspaceDatasetDashboard('search'); }});
            document.getElementById('dashboard-open-upload-modal').addEventListener('click', function() {{ toggleUploadModal(true); }});
            document.getElementById('dashboard-close-upload-modal').addEventListener('click', function() {{ toggleUploadModal(false); }});
            document.getElementById('dashboard-cancel-upload-modal').addEventListener('click', function() {{ toggleUploadModal(false); }});
            document.getElementById('dashboard-chat-upload-form').addEventListener('submit', submitUploadModal);
            document.getElementById('dashboard-chat-upload-modal').addEventListener('click', function(event) {{
                if (event.target === event.currentTarget) {{
                    toggleUploadModal(false);
                }}
            }});
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


def create_dashboard_ui_router() -> APIRouter:
    router = APIRouter()

    @router.get("/mcp", response_class=HTMLResponse)
    async def legacy_mcp_dashboard_root() -> str:
        return _render_shell_page(_IPFS_DASHBOARD_MAP["mcp"])

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
        )

    @router.get("/dashboards/ipfs-datasets/{slug}", response_class=HTMLResponse)
    async def ipfs_datasets_dashboard_shell(slug: str) -> str:
        entry = _IPFS_DASHBOARD_MAP.get(slug)
        if entry is None:
            raise HTTPException(status_code=404, detail="Dashboard not found")
        return _render_shell_page(entry)

    @router.get("/dashboards/raw/ipfs-datasets/{slug}", response_class=HTMLResponse)
    async def ipfs_datasets_dashboard_raw(slug: str) -> str:
        entry = _IPFS_DASHBOARD_MAP.get(slug)
        if entry is None:
            raise HTTPException(status_code=404, detail="Dashboard not found")
        return _render_ipfs_dashboard(entry)

    return router


def attach_dashboard_ui_routes(app: FastAPI) -> FastAPI:
    if _IPFS_DATASETS_STATIC_DIR.is_dir() and not any(
        getattr(route, "path", None) == "/ipfs-datasets-static" for route in app.routes
    ):
        app.mount(
            "/ipfs-datasets-static",
            StaticFiles(directory=str(_IPFS_DATASETS_STATIC_DIR)),
            name="ipfs-datasets-static",
        )
    app.include_router(create_dashboard_ui_router())
    return app
