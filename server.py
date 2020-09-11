import os

from discord.ext.ipc import Client
from quart import Quart

app = Quart(__name__)
web_ipc = Client(secret_key=os.getenv("SECRET_KEY"))


def req(idx, endpoint, **kwargs):
    return web_ipc.request(endpoint, 8765 + idx, **kwargs)


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
async def all_reload():
    resp = {}
    for idx in range(100):
        try:
            resp[idx] = await req(idx, "reload")
        except OSError:
            break
    return resp


@app.route("/disableall")
async def all_disable():
    resp = {}
    for idx in range(100):
        try:
            resp[idx] = await req(idx, "disable")
        except OSError:
            break
    return resp


@app.route("/enableall")
async def all_enable():
    resp = {}
    for idx in range(100):
        try:
            resp[idx] = await req(idx, "enable")
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
async def cluster_reload(idx):
    try:
        return await req(idx, "reload")
    except OSError:
        return "Not Found", 404


@app.route("/<int:idx>/stop")
async def cluster_stop(idx):
    try:
        return await req(idx, "stop")
    except OSError:
        return "Not Found", 404


@app.route("/<int:idx>/disable")
async def cluster_disable(idx):
    try:
        return await req(idx, "disable")
    except OSError:
        return "Not Found", 404


@app.route("/<int:idx>/enable")
async def cluster_enable(idx):
    try:
        return await req(idx, "enable")
    except OSError:
        return "Not Found", 404


if __name__ == "__main__":
    app.run()
