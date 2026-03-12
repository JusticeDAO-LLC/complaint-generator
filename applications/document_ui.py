from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import HTMLResponse


_DOCUMENT_TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "document.html"


def load_document_html() -> str:
	return _DOCUMENT_TEMPLATE.read_text()


def create_document_ui_router() -> APIRouter:
	router = APIRouter()

	@router.get("/document", response_class=HTMLResponse)
	async def document_page() -> str:
		return load_document_html()

	return router


def attach_document_ui_routes(app: FastAPI) -> FastAPI:
	app.include_router(create_document_ui_router())
	return app