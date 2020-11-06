import asyncio
import hashlib
import hmac
from datetime import datetime, timedelta
from functools import wraps

import config
import stripe
from discord.ext.ipc import Client, ServerConnectionRefusedError
from motor.motor_asyncio import AsyncIOMotorClient
from quart import Quart, abort, request

# Constants

purchase_amounts = {
    500: 500,
    1000: 1100,
    2000: 2400,
    4000: 5600,
}

# Setup

stripe.api_key = config.STRIPE_KEY
stripe_secret = config.STRIPE_WEBHOOK_SECRET
github_secret = config.GITHUB_WEBHOOK_SECRET.encode("utf-8")

app = Quart(__name__)
web_ipc = Client(secret_key=config.SECRET_KEY)

loop = asyncio.get_event_loop()
db = AsyncIOMotorClient(config.DATABASE_URI, io_loop=loop)[config.DATABASE_NAME]


# IPC Routes


async def req(idx, endpoint, **kwargs):
    try:
        resp = await asyncio.wait_for(
            web_ipc.request(endpoint, 8765 + idx, **kwargs), timeout=5.0
        )
        return resp
    except asyncio.TimeoutError:
        return {"success": False, "error": "ipc_timeout"}


def login_required(func):
    @wraps(func)
    async def pred(*args, **kwargs):
        key = request.args.get("key", "")
        hashed = hashlib.sha224(key.encode("utf-8")).hexdigest()
        if hashed != config.LOGIN_KEY:
            abort(401)
        return await func(*args, **kwargs)

    return pred


@app.route("/stats")
async def all_stats():
    resp = {}
    for idx in range(100):
        try:
            resp[idx] = await req(idx, "stats")
        except ServerConnectionRefusedError:
            break
    return resp


@app.route("/reloadall")
@login_required
async def all_reload():
    resp = {}
    for idx in range(100):
        try:
            resp[idx] = await req(idx, "reload")
        except ServerConnectionRefusedError:
            break
    return resp


@app.route("/disableall")
@login_required
async def all_disable():
    resp = {}
    message = request.args.get("message", None)
    for idx in range(100):
        try:
            resp[idx] = await req(idx, "disable", message=message)
        except ServerConnectionRefusedError:
            break
    return resp


@app.route("/enableall")
@login_required
async def all_enable():
    resp = {}
    for idx in range(100):
        try:
            resp[idx] = await req(idx, "enable")
        except ServerConnectionRefusedError:
            break
    return resp


@app.route("/eval")
@login_required
async def all_eval():
    code = request.args.get("code")
    resp = {}
    for idx in range(100):
        try:
            resp[idx] = await req(idx, "eval", code=code)
        except ServerConnectionRefusedError:
            break
    return resp


@app.route("/<int:idx>/stats")
async def cluster_stats(idx):
    try:
        return await req(idx, "stats")
    except ServerConnectionRefusedError:
        abort(404)


@app.route("/<int:idx>/reload")
@login_required
async def cluster_reload(idx):
    try:
        return await req(idx, "reload")
    except ServerConnectionRefusedError:
        abort(404)


@app.route("/<int:idx>/stop")
@login_required
async def cluster_stop(idx):
    try:
        return await req(idx, "stop")
    except ServerConnectionRefusedError:
        abort(404)


@app.route("/<int:idx>/disable")
@login_required
async def cluster_disable(idx):
    message = request.args.get("message", None)
    try:
        return await req(idx, "disable", message=message)
    except ServerConnectionRefusedError:
        abort(404)


@app.route("/<int:idx>/enable")
@login_required
async def cluster_enable(idx):
    try:
        return await req(idx, "enable")
    except ServerConnectionRefusedError:
        abort(404)


@app.route("/<int:idx>/eval")
@login_required
async def cluster_eval(idx):
    code = request.args.get("code")
    try:
        return await req(idx, "eval", code=code)
    except ServerConnectionRefusedError:
        abort(404)


@app.route("/dm/<int:user>")
@login_required
async def send_dm(user):
    message = request.args.get("message")
    try:
        return await req(0, "send_dm", user=user, message=message)
    except ServerConnectionRefusedError:
        return "Not Found", 404


# Webhooks


@app.route("/dbl", methods=["POST"])
async def dbl():
    json = await request.get_json()
    uid = int(json["user"])

    res = await db.member.find_one({"_id": uid})

    if res is None:
        print(f"VOTING: User {uid} not found")
        abort(400, description="Invalid User")

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
        {"_id": uid},
        {
            "$set": {
                "vote_streak": streak,
                "last_voted": datetime.utcnow(),
                "need_vote_reminder": True,
            },
            "$inc": {
                "vote_total": 1,
                f"gifts_{box_type}": 1,
            },
        },
    )

    article = "an" if box_type == "ultra" else "a"

    try:
        await req(
            0,
            "send_dm",
            user=uid,
            message=f"Thanks for voting! You received {article} **{box_type} box**.",
        )
    except ServerConnectionRefusedError:
        pass

    return "Success", 200


@app.route("/purchase", methods=["POST"])
async def purchase():
    try:
        event = stripe.Webhook.construct_event(
            await request.get_data(),
            request.headers["Stripe-Signature"],
            stripe_secret,
        )
    except ValueError as e:
        abort(400, description="Invalid Payload")
    except stripe.error.SignatureVerificationError as e:
        abort(400, description="Invalid Signature")

    if event.type != "payment_intent.succeeded":
        abort(400, description="Invalid Event")

    session = event.data.object
    uid = int(session["metadata"]["id"])
    amount = session["amount"]
    shards = purchase_amounts[amount]

    await db.member.update_one({"_id": uid}, {"$inc": {"premium_balance": shards}})

    try:
        await req(
            0,
            "send_dm",
            user=uid,
            message=f"Thanks for donating! You received **{shards}** shards.",
        )
    except ServerConnectionRefusedError:
        pass

    return "Success", 200


def add_month(dt: datetime, months=1):
    return dt.replace(month=(dt.month + months - 1) % 12 + 1)


@app.route("/sponsor", methods=["POST"])
async def sponsor():
    payload = await request.get_data()

    digest = "sha1=" + hmac.new(github_secret, payload, digestmod="sha1").hexdigest()
    given = request.headers.get("X-Hub-Signature")

    if not hmac.compare_digest(digest, given):
        abort(403, description="Invalid Signature")

    data = await request.get_json()

    sponsorship = data["sponsorship"]
    gh_id = sponsorship["sponsor"]["id"]
    tier = sponsorship["tier"]["monthly_price_in_dollars"]

    now = datetime.utcnow()
    nextm = add_month(now)

    if data["action"] == "created":
        await db.sponsor.update_one(
            {"_id": gh_id},
            {"$set": {"sponsorship_date": now, "reward_tier": tier}},
            upsert=True,
        )

    elif data["action"] == "pending_cancellation":
        await db.sponsor.update_one(
            {"_id": gh_id},
            {"$set": {"reward_date": nextm, "reward_tier": None}},
            upsert=True,
        )

    elif data["action"] == "pending_tier_change":
        await db.sponsor.update_one(
            {"_id": gh_id},
            {"$set": {"reward_date": nextm, "reward_tier": tier}},
            upsert=True,
        )

    return "Success", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", loop=loop)
