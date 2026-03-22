from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse


_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_SDK_PLAYGROUND_TEMPLATE = (
    Path(__file__).resolve().parent.parent
    / "ipfs_datasets_py"
    / "ipfs_accelerate_py"
    / "SDK_PLAYGROUND_PREVIEW.html"
)


def _load_template(name: str) -> str:
    return (_TEMPLATES_DIR / name).read_text()


def _load_sdk_playground_template() -> str:
    return _SDK_PLAYGROUND_TEMPLATE.read_text()


def create_core_site_ui_router() -> APIRouter:
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    async def landing_page() -> str:
        return _load_template("index.html")

    @router.get("/home", response_class=HTMLResponse)
    async def home_page() -> str:
        return _load_template("home.html")

    @router.get("/chat", response_class=HTMLResponse)
    async def chat_page() -> str:
        return _load_template("chat.html")

    @router.get("/profile", response_class=HTMLResponse)
    async def profile_page() -> str:
        return _load_template("profile.html")

    @router.get("/results", response_class=HTMLResponse)
    async def results_page() -> str:
        return _load_template("results.html")

    @router.get("/wysiwyg", response_class=HTMLResponse)
    async def wysiwyg_page() -> str:
        return _load_template("MLWYSIWYG.html")

    @router.get("/mlwysiwyg", response_class=HTMLResponse)
    async def wysiwyg_lowercase_page() -> str:
        return _load_template("MLWYSIWYG.html")

    @router.get("/MLWYSIWYG", response_class=HTMLResponse)
    async def wysiwyg_legacy_page() -> str:
        return _load_template("MLWYSIWYG.html")

    @router.get("/ipfs-datasets/sdk-playground", response_class=HTMLResponse)
    async def sdk_playground_page() -> str:
        return _load_sdk_playground_template()

    @router.get("/cookies")
    async def cookies_page(request: Request) -> dict:
        return dict(request.cookies or {})

    return router


def attach_core_site_ui_routes(app: FastAPI) -> FastAPI:
    app.include_router(create_core_site_ui_router())
    return app
