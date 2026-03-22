import json
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles


ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"

PROFILE_DATA = {
    "hashed_username": "demo-user",
    "hashed_password": "demo-password",
    "username": "demo-user",
    "chat_history": {
        "2026-03-22T09:00:00Z": {
            "sender": "System:",
            "message": "Welcome back to Lex Publicus.",
        },
        "2026-03-22T09:01:00Z": {
            "sender": "demo-user",
            "message": "I need help drafting a retaliation complaint.",
            "explanation": {
                "summary": "This anchors the complaint generation workflow."
            },
        },
    },
    "complaint_summary": {
        "claim_type": "retaliation",
        "summary_of_facts": [
            "Jane Doe reported discrimination to HR.",
            "Acme terminated Jane Doe shortly after the report.",
        ],
    },
}


app = FastAPI(title="Complaint Generator Playwright Surface")

if STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")


def load_template(name: str) -> str:
    return (TEMPLATES / name).read_text()


@app.get("/health")
async def health() -> dict:
    return {"status": "healthy"}


@app.get("/", response_class=HTMLResponse)
@app.get("", response_class=HTMLResponse)
async def index() -> str:
    return load_template("index.html")


@app.get("/home", response_class=HTMLResponse)
async def home() -> str:
    return load_template("home.html")


@app.get("/chat", response_class=HTMLResponse)
async def chat() -> str:
    return load_template("chat.html")


@app.get("/profile", response_class=HTMLResponse)
async def profile() -> str:
    return load_template("profile.html")


@app.get("/results", response_class=HTMLResponse)
async def results() -> str:
    return load_template("results.html")


@app.get("/document", response_class=HTMLResponse)
async def document() -> str:
    return load_template("document.html")


@app.get("/document/optimization-trace", response_class=HTMLResponse)
async def optimization_trace() -> str:
    return load_template("optimization_trace.html")


@app.get("/claim-support-review", response_class=HTMLResponse)
async def claim_support_review() -> str:
    return load_template("claim_support_review.html")


@app.get("/cookies")
async def cookies() -> PlainTextResponse:
    return PlainTextResponse(
        json.dumps(
            {
                "hashed_username": PROFILE_DATA["hashed_username"],
                "hashed_password": PROFILE_DATA["hashed_password"],
                "token": "playwright-token",
            }
        )
    )


@app.post("/load_profile")
async def load_profile(request: Request) -> JSONResponse:
    payload = await request.json()
    request_payload = payload.get("request") if isinstance(payload, dict) else {}
    result = {
        "hashed_username": request_payload.get("hashed_username") or PROFILE_DATA["hashed_username"],
        "hashed_password": request_payload.get("hashed_password") or PROFILE_DATA["hashed_password"],
        "data": json.dumps(PROFILE_DATA),
    }
    return JSONResponse({"results": result} if "username" in request_payload else result)


@app.post("/create_profile")
async def create_profile() -> JSONResponse:
    return JSONResponse(
        {
            "hashed_username": PROFILE_DATA["hashed_username"],
            "hashed_password": PROFILE_DATA["hashed_password"],
            "data": json.dumps(PROFILE_DATA),
        }
    )


@app.get("/api/documents/download")
async def download_document(path: str = "") -> PlainTextResponse:
    return PlainTextResponse(f"download stub for {path}")


@app.get("/api/documents/optimization-trace")
async def optimization_trace_payload(cid: str = "") -> JSONResponse:
    return JSONResponse({"cid": cid, "changes": []})


@app.websocket("/api/chat")
async def websocket_chat(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.send_json(
        {
            "sender": "System:",
            "message": "Connected to the test chat surface.",
        }
    )
    try:
        while True:
            payload = await websocket.receive_json()
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        return
