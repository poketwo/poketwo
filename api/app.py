import asyncio
import hmac
import os

from flask import Flask, abort, request
from pymongo import MongoClient

secret = os.getenv("PATREON_SECRET").encode("ascii")
db = MongoClient(os.getenv("DATABASE_URI"))[os.getenv("DATABASE_NAME")]

app = Flask(__name__)


@app.route("/dbl", methods=["POST"])
def dbl():
    print(request.json)


@app.route("/patreon", methods=["POST"])
def patreon():
    if "delete" in request.headers.get("X-Patreon-Event"):
        return "", 200

    digest = hmac.new(secret, request.data, digestmod="md5").hexdigest()
    given = request.headers.get("X-Patreon-Signature")

    if not hmac.compare_digest(digest, given):
        abort(403)

    data = request.json["data"]
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

    res = db.member.update_one(
        {"_id": int(user["attributes"]["discord_id"])},
        {"$inc": {"redeems": inc_redeems}},
    )

    print(
        "Giving "
        + user["attributes"]["discord_id"]
        + " "
        + str(inc_redeems)
        + " redeems."
    )

    return "", 200


if __name__ == "__main__":
    app.run()
