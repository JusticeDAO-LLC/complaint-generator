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


def _render_dashboard_hub() -> str:
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
        body {{ margin: 0; font-family: 'Public Sans', Arial, sans-serif; background: #f7f7f2; color: #122033; }}
        header {{ padding: 28px 32px; background: linear-gradient(135deg, #1d4d5f, #217b74); color: white; }}
        main {{ padding: 24px 32px 40px; display: grid; gap: 24px; }}
        .grid {{ display: grid; gap: 24px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }}
        .card {{ background: white; border-radius: 18px; padding: 22px; box-shadow: 0 12px 28px rgba(18, 32, 51, 0.08); }}
        h1, h2 {{ margin-top: 0; }}
        ul {{ margin: 0; padding-left: 18px; }}
        li {{ margin: 10px 0; }}
        a {{ color: #0a4f66; font-weight: 600; }}
        span {{ color: #536471; display: block; margin-top: 4px; }}
    </style>
</head>
<body>
    <header>
        <h1>Unified Dashboard Hub</h1>
        <p>One complaint-generator website entry point for complaint-generator dashboards, legacy compatibility surfaces, and ipfs_datasets_py dashboards.</p>
    </header>
    <main>
        <div class=\"grid\">
            <section class=\"card\">
                <h2>Complaint Generator Surfaces</h2>
                <ul>{complaint_links}</ul>
            </section>
            <section class=\"card\">
                <h2>ipfs_datasets_py Dashboards</h2>
                {ipfs_markup}
            </section>
        </div>
    </main>
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
    async def dashboard_hub() -> str:
        return _render_dashboard_hub()

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
