import json
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from lib.chat_payloads import build_chat_payload

try:
    from fastapi.templating import Jinja2Templates
except Exception:
    Jinja2Templates = None

app = FastAPI()
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# locate templates
templates = None
if Jinja2Templates is not None:
    try:
        templates = Jinja2Templates(directory="templates")
    except Exception:
        templates = None



@app.get("/home", response_class=HTMLResponse)
async def read_home(request: Request):
    template = ""
    filename = os.getcwd() + "/templates/home.html"
    if os.path.isfile(filename):
        with open(filename, "r") as f:
            template = f.read()
    return template


@app.get("/chat", response_class=HTMLResponse)
async def read_chat(request: Request):
    template = ""
    filename = os.getcwd() + "/templates/chat.html"

    if os.path.isfile(filename):
        with open(filename, "r") as f:
            template = f.read()
    return template


@app.get("/profile", response_class=HTMLResponse)
async def read_profile(request: Request):
    template = ""
    filename = os.getcwd() + "/templates/profile.html"

    if os.path.isfile(filename):
        with open(filename, "r") as f:
            template = f.read()
    return template


@app.get("/results", response_class=HTMLResponse)
async def read_results(request: Request):
    template = ""
    filename = os.getcwd() + "/templates/results.html"

    if os.path.isfile(filename):
        with open(filename, "r") as f:
            template = f.read()
    return template


@app.get("/mlwysiwyg", response_class=HTMLResponse)
async def read_mlwysiwyg(request: Request):
    template = ""
    filename = os.getcwd() + "/templates/MLWYSIWYG.html"

    if os.path.isfile(filename):
        with open(filename, "r") as f:
            template = f.read()
    return template


@app.get("/ipfs-datasets/sdk-playground", response_class=HTMLResponse)
async def read_sdk_playground(request: Request):
    template = ""
    filename = os.getcwd() + "/ipfs_datasets_py/ipfs_accelerate_py/SDK_PLAYGROUND_PREVIEW.html"

    if os.path.isfile(filename):
        with open(filename, "r") as f:
            template = f.read()
    return template


@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    template = ""
    filename = os.getcwd() + "/templates/index.html"

    if os.path.isfile(filename):
        with open(filename, "r") as f:
            template = f.read()
    return template


@app.get("", response_class=HTMLResponse)
async def read_root(request: Request):
    template = ""
    filename = os.getcwd() + "/templates/index.html"

    if os.path.isfile(filename):
        with open(filename, "r") as f:
            template = f.read()
    return template


@app.get("/cookies", response_class=HTMLResponse)
async def read_cookies(request: Request):
    cookie = request.cookies
    if cookie is not None:
        return json.dumps(cookie)
    else:
        return "No Cookie found"


@app.get("/test", response_class=HTMLResponse)
async def read_test(request: Request):
    cookie = request.cookies
    if cookie is not None:
        if "hashed_username" in cookie.keys():
            hashed_username = cookie["hashed_username"]
        if "hashed_password" in cookie.keys():
            hashed_password = cookie["hashed_password"]
        if hashed_username is not None and hashed_password is not None:
            results = load_profile(dict({"hashed_username": hashed_username, "hashed_password" : hashed_password}))
            if "Err" not in results.keys():
                return {"results": results}
            else:
                return {"Err": results["Err"]}
        # cookie = cookie.replace('"', '')
        # cookie = cookie.replace('"', '')
        # cookie = cookie.split(":")
        # cookie = {cookie[0]: cookie[1]}
        return json.dumps(cookie)
    else:
        return "No Cookie found"



class SocketManager:
    def __init__(self):
        self.active_connections: list[(WebSocket, str)] = []

    async def connect(self, websocket: WebSocket, user: str):
        await websocket.accept()
        self.active_connections.append((websocket, user))

    def disconnect(self, websocket: WebSocket, user: str):
        self.active_connections.remove((websocket, user))

    async def broadcast(self, data: dict):
        for connection in self.active_connections:
            await connection[0].send_json(data)

manager = SocketManager()


def test(data):
    return None


@app.websocket("/api/chat")
async def chat(websocket: WebSocket):
    token = websocket.cookies.get("Authorization")
    hashed_username = websocket.cookies.get("hashed_username")
    hashed_password = websocket.cookies.get("hashed_password")

    if token:
        await manager.connect(websocket, hashed_username)
        response = build_chat_payload(
            "got connected",
            sender="System:",
            hashed_username=hashed_username,
        )

        await manager.broadcast(response)
        try:
            while True:
                data = await websocket.receive_json()
                output = test({"token": "token", "data": data, "hashed_username": hashed_username, "hashed_password": hashed_password})
                message = data.get("message") if isinstance(data, dict) else str(data)
                await manager.broadcast(build_chat_payload(
                    message,
                    sender=hashed_username or "User:",
                    hashed_username=hashed_username,
                ))
                if isinstance(output, dict):
                    await manager.broadcast(build_chat_payload(
                        output.get("message") or "",
                        inquiry_payload=output,
                        sender=output.get("sender", "Bot:"),
                        hashed_username=hashed_username,
                    ))

        except WebSocketDisconnect:
            manager.disconnect(websocket, hashed_username)
            response['message'] = "left"
            await manager.broadcast(response)
