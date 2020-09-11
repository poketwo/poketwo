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


@app.route("/<int:idx>/move")
async def cluster_battle_move(idx):
    try:
        return await req(idx, "battle_move", action={"test": 1})
    except OSError:
        return "Not Found", 404


if __name__ == "__main__":
    app.run()
