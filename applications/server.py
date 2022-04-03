from re import search
import jwt
from jwt import PyJWTError
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Cookie, WebSocket, WebSocketDisconnect, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse
from datetime import datetime, timedelta
from starlette.status import HTTP_403_FORBIDDEN
from starlette.responses import RedirectResponse, Response, JSONResponse
from starlette.requests import Request
import sys
import os
import json
import this
import uvicorn

class SERVER:
    
    
    def __init__(self, app):
        self.app = app
        uvicorn.run(app, host="0.0.0.0", port=1792)

    app = FastAPI()


    @app.get("/home", response_class=HTMLResponse)
    async def read_items(request: Request ):
        template = ""
        filename = os.getcwd() + "/complaint-generator/templates/home.html"
        if os.path.isfile(filename):
            with open(filename, "r") as f:
                template = f.read()
        return template

    @app.get("/chat", response_class=HTMLResponse)
    async def read_items(request: Request ):
        template = ""
        filename = os.getcwd() + "/complaint-generator/templates/chat.html"

        if os.path.isfile(filename):
            with open(filename, "r") as f:
                template = f.read()
        return template

    @app.get("/", response_class=HTMLResponse)
    async def read_items(request: Request ):
        template = ""
        filename = os.getcwd() + "/complaint-generator/templates/index.html"

        if os.path.isfile(filename):
            with open(filename, "r") as f:
                template = f.read()
        return template

    @app.get("", response_class=HTMLResponse)
    async def read_items(request: Request ):
        template = ""
        filename = os.getcwd() + "/complaint-generator/templates/index.html"

        if os.path.isfile(filename):
            with open(filename, "r") as f:
                template = f.read()
        return template

    @app.get("/cookies", response_class=HTMLResponse)
    async def read_items( request: Request ):
        cookie = request.cookies
        if cookie is not None:
            return json.dumps(cookie)
        else:
            return "No Cookie found"


    @app.get("/test", response_class=HTMLResponse)
    async def read_items( request: Request ):
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
            response = {
                "hashed_username": hashed_username,
                "user": "bot",
                "message": "got connected"
            }

            await manager.broadcast(response)
            try:
                while True:
                    data = await websocket.receive_json()
                    output = test({"token": "token", "data": data, "hashed_username": hashed_username, "hashed_password": hashed_password})
                    await manager.broadcast(data)

            except WebSocketDisconnect:
                manager.disconnect(websocket, token)
                response['message'] = "left"
                await manager.broadcast(response)



    manager = SocketManager()



    ###################################
    #  								  #
    #   Do not copy this text below	  #
    # 								  #
    ###################################



