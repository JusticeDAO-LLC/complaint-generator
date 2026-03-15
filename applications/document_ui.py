from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import HTMLResponse


_DOCUMENT_TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "document.html"
_OPTIMIZATION_TRACE_TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "optimization_trace.html"


def load_document_html() -> str:
	return _DOCUMENT_TEMPLATE.read_text()


def load_optimization_trace_html() -> str:
	return _OPTIMIZATION_TRACE_TEMPLATE.read_text()


def create_document_ui_router() -> APIRouter:
	router = APIRouter()

	@router.get("/document", response_class=HTMLResponse)
	async def document_page() -> str:
		return load_document_html()

	@router.get("/document/optimization-trace", response_class=HTMLResponse)
	async def optimization_trace_page() -> str:
		return load_optimization_trace_html()

	return router


def attach_document_ui_routes(app: FastAPI) -> FastAPI:
	app.include_router(create_document_ui_router())
	return app