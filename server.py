import asyncio
import hashlib
import os
from datetime import datetime, timedelta
from functools import wraps

from discord.ext.ipc import Client
from motor.motor_asyncio import AsyncIOMotorClient
from quart import Quart, request

loop = asyncio.get_event_loop()


app = Quart(__name__)
web_ipc = Client(secret_key=os.getenv("SECRET_KEY"))
db = AsyncIOMotorClient(os.getenv("DATABASE_URI"), io_loop=loop)[
    os.getenv("DATABASE_NAME")
]


# IPC Routes


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


# Webhooks


@app.route("/dbl", methods=["POST"])
async def dbl():
    json = await request.get_json()
    res = await db.member.find_one({"_id": int(json["user"])})

    streak = res.get("vote_streak", 0)
    last_voted = res.get("last_voted", datetime.min)

    if datetime.utcnow() - last_voted > timedelta(days=2):
        streak = 0

    streak += 1

    if streak >= 40 and streak % 10 == 0:
        box_type = "master"
    elif streak >= 14:
        box_type = "ultra"
    elif streak >= 7:
        box_type = "great"
    else:
        box_type = "normal"

    await db.member.update_one(
        {"_id": int(json["user"])},
        {
            "$set": {"vote_streak": streak, "last_voted": datetime.utcnow()},
            "$inc": {"vote_total": 1, f"gifts_{box_type}": 1},
        },
    )

    return "Success", 200


if __name__ == "__main__":
    app.run(loop=loop)
