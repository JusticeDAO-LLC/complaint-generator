from re import search
from urllib import request
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
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
import jwt
import this
import uvicorn 
class SERVER:
       
    def __init__( mediator):
 
        app = FastAPI()
        
        hostname = "http://10.10.0.10:1792"

        SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
        ALGORITHM = "HS256"
        ACCESS_TOKEN_EXPIRE_MINUTES = 30

        def create_access_token(*, data: dict, expires_delta: timedelta = None):
            to_encode = data.copy()
            if expires_delta:
                expire = datetime.utcnow() + expires_delta
            else:
                expire = datetime.utcnow() + timedelta(minutes=15)
            to_encode.update({"exp": expire})
            encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
            return encoded_jwt

        @app.get("/home", response_class=HTMLResponse)
        async def read_items(request: Request ):
            template = ""
            filename = os.getcwd() + "/templates/home.html"
            if os.path.isfile(filename):
                with open(filename, "r") as f:
                    template = f.read()
            return template

        @app.get("/profile", response_class=HTMLResponse)
        async def read_items(request: Request ):
            template = ""
            filename = os.getcwd() + "/templates/profile.html"
            if os.path.isfile(filename):
                with open(filename, "r") as f:
                    template = f.read()
            return template

        @app.get("/document", response_class=HTMLResponse)
        async def read_items(request: Request ):
            template = ""
            filename = os.getcwd() + "/templates/document.html"
            if os.path.isfile(filename):
                with open(filename, "r") as f:
                    template = f.read()
            return template
    
        @app.get("/results", response_class=HTMLResponse)
        async def read_items(request: Request ):
            template = ""
            filename = os.getcwd() + "/templates/results.html"
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
            params_json = await request.json()
            cookie = request.cookies
            if cookie is not None and not ("hashed_username" not in params_json or "hashed_password" not in params_json or "username" not in params_json or "password" not in params_json):
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

                    result = r.text
                    if "{" in r.text:
                        result = json.loads(r.text)[0]

                    if "data" not in result.keys():
                        return {"Err": result}
                    else:
                        if "hashed_username" not in json.loads(result["data"]).keys() or "hashed_password" not in json.loads(result["data"]).keys():
                            return {"Err": "Invalid Credentials"}
                        else:
                            hashed_username = json.loads(result["data"])["hashed_username"]
                            hashed_password = json.loads(result["data"])["hashed_password"]
                    
                        
                    if "Err" not in result.keys():
                        # results = RedirectResponse(url="/test")
                        response =  Response(status_code=200, content=json.dumps(result))
                        access_token_expires = timedelta(minutes=1440)
                        access_token = create_access_token(
                            data={"hashed_username": hashed_username  , "hashed_password" : hashed_password }, expires_delta=access_token_expires
                        )
                        token = jsonable_encoder(access_token)
                        # cookies =set_cookie({"hashed_username": hashed_username, "hash_password" : hashed_password, "token", token})
                        response.set_cookie(key="token", value=token)
                        response.set_cookie(key="hashed_username", value=hashed_username)
                        response.set_cookie(key="hashed_password", value=hashed_password)
                        response.data = json.dumps(result)
                        return  {response}
                    else:
                        return {"results" : {"Err": result["Err"]}}
            else:
                if "hashed_username" in params_json["request"].keys() and "hashed_password" in params_json["request"].keys():
                    r = requests.post(
                        hostname + '/load_profile', 
                        headers={
                            'Content-Type': 'application/json',
                        }, 
                        data=json.dumps({"request" : {"hashed_password": params_json["request"]["hashed_password"], "hashed_username" : params_json["request"]["hashed_username"]}})
                    )
                    pass

                elif "username" in params_json["request"].keys() and "password" in params_json["request"].keys():
                    r = requests.post(
                        hostname + '/load_profile', 
                        headers={
                            'Content-Type': 'application/json',
                        }, 
                        data=json.dumps({"request" : {"username": params_json["request"]["username"], "password" : params_json["request"]["password"]}})
                    )
                    pass

            result = r.text
            if type(result) is str:
                if "{" in r.text:
                    result = json.loads(r.text)
            if type(result) is dict:
                if "Err" in result.keys():
                    return result
            if type(result) is list:
                result = result[0]
                pass

            result_data = json.loads(result["data"])
            mediator.state.data = result_data
            access_token_expires = timedelta(minutes=1440)
            access_token = create_access_token(
                data={"hashed_username": result_data["hashed_username"]  , "hashed_password" : result_data["hashed_password"] }, expires_delta=access_token_expires
            )
            token = jsonable_encoder(access_token)
            result["token"] = token
            response =  Response(status_code=200, content=json.dumps(result))

            # cookies =set_cookie({"hashed_username": hashed_username, "hash_password" : hashed_password, "token", token})
            response.set_cookie(key="token", value=token)
            response.set_cookie(key="hashed_username", value=result_data["hashed_username"])
            response.set_cookie(key="hashed_password", value=result_data["hashed_password"])
            response.data = json.dumps(result_data)
            return(response)
    
            
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
            result = r.text
            if type(result) is str:
                if "{" in r.text:
                    result = json.loads(r.text)
            if type(result) is dict:
                if "Err" in result.keys():
                    return result
            if type(result) is list:
                result = result[0]
                pass

            result_data = json.loads(result["data"])

            if "hashed_username" in result_data.keys():
                hashed_username = result_data["hashed_username"]

            if "hashed_password" in result_data.keys():
                hashed_password = result_data["hashed_password"]

            access_token_expires = timedelta(minutes=1440)
            access_token = create_access_token(
                data={"hashed_username": hashed_username  , "hashed_password" : hashed_password }, expires_delta=access_token_expires
            )

            token = jsonable_encoder(access_token)
            result_data["token"] = token
            response =  Response(status_code=200, content=json.dumps(result_data))

            # cookies =set_cookie({"hashed_username": hashed_username, "hash_password" : hashed_password, "token", token})
            response.set_cookie(key="token", value=token)
            response.set_cookie(key="hashed_username", value=result_data["hashed_username"])
            response.set_cookie(key="hashed_password", value=result_data["hashed_password"])
            response.data = json.dumps(result_data)
            return(response)



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
            token = websocket.cookies.get("token")
            hashed_username = websocket.cookies.get("hashed_username")
            hashed_password = websocket.cookies.get("hashed_password")

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

            if token:
                await manager.connect(websocket, hashed_username)
                response = {
                    "sender": "Bot:",
                    "message": "Please state your legal complaint"
                }

                await manager.broadcast(response)
                try:
                    while True:
                        reply = ""
                        data = await websocket.receive_json()
                        mediator.state.load_profile(dict({"results":{ "hashed_username": hashed_username, "hashed_password":hashed_password}}))
                        mediator.state.message(data)
                        await manager.broadcast(data)
                        await manager.broadcast(mediator.state.response())
                        mediator.state.store_profile(dict({"results":{ "hashed_username": hashed_username, "hashed_password":hashed_password}}))
                        

                except WebSocketDisconnect:
                    manager.disconnect(websocket, token)
                    response['message'] = "left"
                    await manager.broadcast(response)


        uvicorn.run(app, host="0.0.0.0", port=19000)
        
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
#lambda expression

