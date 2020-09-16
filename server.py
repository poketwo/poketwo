import hashlib
import os

from discord.ext.ipc import Client
from quart import Quart, request
from functools import wraps

app = Quart(__name__)

web_ipc = Client(secret_key=os.getenv("SECRET_KEY"))


def req(idx, endpoint, **kwargs):
    return web_ipc.request(endpoint, 8765 + idx, **kwargs)


def login_required(func):
    @wraps(func)
    async def pred():
        key = request.args.get("key", "")
        hashed = hashlib.sha224(key.encode("utf-8")).hexdigest()
        if hashed != os.getenv("LOGIN_KEY"):
            return "Unauthorized", 401
        return await func()

    return pred


@app.route("/stats")
async def all_stats():
    resp = {}
    for idx in range(100):
        try:
            resp[idx] = await req(idx, "stats")
        except OSError:
            break
    return resp


@app.route("/reloadall")
@login_required
async def all_reload():
    resp = {}
    for idx in range(100):
        try:
            resp[idx] = await req(idx, "reload")
        except OSError:
            break
    return resp


@app.route("/disableall")
@login_required
async def all_disable():
    resp = {}
    for idx in range(100):
        try:
            resp[idx] = await req(idx, "disable")
        except OSError:
            break
    return resp


@app.route("/enableall")
@login_required
async def all_enable():
    resp = {}
    for idx in range(100):
        try:
            resp[idx] = await req(idx, "enable")
        except OSError:
            break
    return resp


@app.route("/eval")
@login_required
async def all_eval():
    code = request.args.get("code")
    print(code)
    resp = {}
    for idx in range(100):
        try:
            resp[idx] = await req(idx, "eval", code=code)
        except OSError:
            break
    return resp


@app.route("/<int:idx>/stats")
async def cluster_stats(idx):
    try:
        return await req(idx, "stats")
    except OSError:
        return "Not Found", 404


@app.route("/<int:idx>/reload")
@login_required
async def cluster_reload(idx):
    try:
        return await req(idx, "reload")
    except OSError:
        return "Not Found", 404


@app.route("/<int:idx>/stop")
@login_required
async def cluster_stop(idx):
    try:
        return await req(idx, "stop")
    except OSError:
        return "Not Found", 404


@app.route("/<int:idx>/disable")
@login_required
async def cluster_disable(idx):
    try:
        return await req(idx, "disable")
    except OSError:
        return "Not Found", 404


@app.route("/<int:idx>/enable")
@login_required
async def cluster_enable(idx):
    try:
        return await req(idx, "enable")
    except OSError:
        return "Not Found", 404


@app.route("/<int:idx>/eval")
@login_required
async def cluster_eval(idx):
    code = request.args.get("code")
    try:
        return await req(idx, "eval", code=code)
    except OSError:
        return "Not Found", 404


if __name__ == "__main__":
    app.run()
