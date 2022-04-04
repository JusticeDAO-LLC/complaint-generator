from re import search
from urllib import request
import requests
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
       
    def __init__( mediator):
 
        app = FastAPI()
        
        hostname = "10.10.0.10:1792"

        @app.get("/home", response_class=HTMLResponse)
        async def read_items(request: Request ):
            template = ""
            filename = os.getcwd() + "/templates/home.html"
            if os.path.isfile(filename):
                with open(filename, "r") as f:
                    template = f.read()
            return template

        
        @app.get("/chat", response_class=HTMLResponse)
        async def read_items(request: Request ):
            template = ""
            filename = os.getcwd() + "/templates/chat.html"

            if os.path.isfile(filename):
                with open(filename, "r") as f:
                    template = f.read()
            return template

        @app.get("/", response_class=HTMLResponse)
        async def read_items(request: Request ):
            template = ""
            filename = os.getcwd() + "/templates/index.html"

            if os.path.isfile(filename):
                with open(filename, "r") as f:
                    template = f.read()
            return template

        @app.get("", response_class=HTMLResponse)
        async def read_items(request: Request ):
            template = ""
            filename = os.getcwd() + "/templates/index.html"

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

        @app.post("/load_profile")
        async def root(request: Request, response: Response):
            cookie = request.cookies
            if cookie is not None:
                if "hashed_username" in cookie.keys():
                    hashed_username = cookie["hashed_username"]
                if "hashed_password" in cookie.keys():
                    hashed_password = cookie["hashed_password"]
                if hashed_username is not None and hashed_password is not None:
                    r = requests.post(
                        hostname + '/load_profile', 
                        headers={
                            'Content-Type': 'application/json',
                        }, 
                        data=json.dumps({"request" : {"hashed_username": hashed_username, "hashed_password" : hashed_password}})
                    )
                    results = json.loads(r.text)
                    if "Err" not in results.keys():
                        return {"results": results}
                    else:
                        return {"Err": results["Err"]}
                else:
                    params_json = await request.json()
                    r = requests.post(
                        hostname + '/load_profile', 
                        headers={
                            'Content-Type': 'application/json',
                        }, 
                        data=json.dumps({"request" : {"hashed_username": params_json["hashed_username"], "hashed_password" : params_json["hashed_password"]}})
                    )
                    results = json.loads(r.text)
                    return(results)

        @app.post("/create_profile")
        async def root(request: Request, response: Response):
            params_json = await request.json()
            results = dict()
            if "username" not in params_json["request"]:
                raise HTTPException(status_code=400, detail="you need to provide a username")
            elif "password" not in params_json["request"]:
                raise HTTPException(status_code=400, detail="you need to provide a password")
            elif "email" not in params_json["request"]:
                raise HTTPException(status_code=400, detail="you need to provide a email")
                pass
            params_json = await request.json()
            r = requests.post(
                hostname + '/create_profile', 
                headers={
                    'Content-Type': 'application/json',
                }, 
                data=json.dumps({"request" : params_json["request"]})
            )
            results = json.loads(r.text)
            return {"results": results}

        @app.post("/store_profile")
        async def root(request: Request, response: Response):
            params_json = await request.json()
            
            if "request" not in params_json:
                raise HTTPException(status_code=400, detail="Request is empty")
            if "username" not in params_json["request"] and "hashed_username" not in params_json["request"]:
                raise HTTPException(status_code=400, detail="you need to provide a username or hashed username")
            if "password" not in params_json["request"] and "hashed_password" not in params_json["request"]:
                raise HTTPException(status_code=400, detail="you need to provide a password or hashed password")
            params_json = await request.json()
            r = requests.post(
                hostname + '/load_profile', 
                headers={
                    'Content-Type': 'application/json',
                }, 
                data=json.dumps({"request" : params_json["request"]})
            )
            results = json.loads(r.text)
            return {"results": results}

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


        uvicorn.run(app, host="0.0.0.0", port=666)
        
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

    app = FastAPI()


    


    ###################################
    #  								  #
    #   Do not copy this text below	  #
    # 								  #
    ###################################



