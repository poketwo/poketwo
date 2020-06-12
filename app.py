import asyncio
import hmac
import os

from flask import Flask, abort, request

from cogs import mongo

secret = os.getenv("PATREON_SECRET").encode("ascii")

app = Flask(__name__)


@app.route("/patreon", methods=["POST"])
def webhook():
    digest = hmac.new(secret, request.data, digestmod="md5").hexdigest()
    given = request.headers.get("X-Patreon-Signature")

    if not hmac.compare_digest(digest, given):
        abort(403)

    user = [x for x in request.json["included"] if x["type"] == "user"][0]
    rewards = [x for x in request.json["included"] if x["type"] == "reward"]

    inc_redeems = 0

    for reward in rewards:
        if reward["id"] == "2608556":
            inc_redeems += 1
        if reward["id"] == "2610442":
            inc_redeems += 4
        if reward["id"] == "2611242":
            inc_redeems += 8

    update = mongo.db.member.update_one(
        {"_id": int(user["attributes"]["discord_id"])},
        {"$inc": {"redeems": inc_redeems}},
    )

    loop = asyncio.get_event_loop()
    loop.run_until_complete(update)

    return "", 200


if __name__ == "__main__":
    app.run()
