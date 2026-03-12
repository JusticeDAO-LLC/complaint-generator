from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from document_pipeline import DEFAULT_OUTPUT_DIR


class FormalComplaintDocumentRequest(BaseModel):
    user_id: Optional[str] = None
    court_name: str = "United States District Court"
    district: str = ""
    division: Optional[str] = None
    court_header_override: Optional[str] = None
    case_number: Optional[str] = None
    title_override: Optional[str] = None
    plaintiff_names: List[str] = Field(default_factory=list)
    defendant_names: List[str] = Field(default_factory=list)
    requested_relief: List[str] = Field(default_factory=list)
    output_dir: Optional[str] = None
    output_formats: List[str] = Field(default_factory=lambda: ["docx", "pdf"])


def _default_generated_documents_root() -> Path:
    return DEFAULT_OUTPUT_DIR.resolve()


def _is_allowed_download_path(path: Path) -> bool:
    try:
        path.resolve().relative_to(_default_generated_documents_root())
        return True
    except ValueError:
        return False


def _build_download_url(path: str) -> Optional[str]:
    resolved = Path(path).resolve()
    if not _is_allowed_download_path(resolved):
        return None
    return f"/api/documents/download?path={resolved}"


def _annotate_artifacts_with_download_urls(payload: Dict[str, Any]) -> Dict[str, Any]:
    artifacts = payload.get("artifacts") if isinstance(payload, dict) else None
    if not isinstance(artifacts, dict):
        return payload
    for artifact in artifacts.values():
        if not isinstance(artifact, dict):
            continue
        artifact_path = artifact.get("path")
        if artifact_path:
            download_url = _build_download_url(str(artifact_path))
            if download_url:
                artifact["download_url"] = download_url
    return payload


def create_document_router(mediator: Any) -> APIRouter:
    router = APIRouter()

    @router.post("/api/documents/formal-complaint")
    async def build_formal_complaint_document(
        request: FormalComplaintDocumentRequest,
    ) -> Dict[str, Any]:
        if not request.output_formats:
            raise HTTPException(status_code=400, detail="At least one output format is required")
        payload = mediator.build_formal_complaint_document_package(
            user_id=request.user_id,
            court_name=request.court_name,
            district=request.district,
            division=request.division,
            court_header_override=request.court_header_override,
            case_number=request.case_number,
            title_override=request.title_override,
            plaintiff_names=request.plaintiff_names,
            defendant_names=request.defendant_names,
            requested_relief=request.requested_relief,
            output_dir=request.output_dir,
            output_formats=request.output_formats,
        )
        return _annotate_artifacts_with_download_urls(payload)

    @router.get("/api/documents/download")
    async def download_generated_document(path: str = Query(...)) -> FileResponse:
        file_path = Path(path).resolve()
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="Generated document not found")
        if not _is_allowed_download_path(file_path):
            raise HTTPException(status_code=403, detail="Requested path is outside the generated documents directory")
        return FileResponse(path=str(file_path), filename=file_path.name)

    return router


def attach_document_routes(app: FastAPI, mediator: Any) -> FastAPI:
    app.include_router(create_document_router(mediator))
    return app