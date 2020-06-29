import asyncio
import hmac
import os

from datetime import datetime, timedelta
from flask import Flask, abort, request
from pymongo import MongoClient

# secret = os.getenv("PATREON_SECRET").encode("ascii")
db = MongoClient(os.getenv("DATABASE_URI"))[os.getenv("DATABASE_NAME")]

app = Flask(__name__)


@app.route("/dbl", methods=["POST"])
def dbl():
    print(request.json)

    res = db.member.find_one({"_id": int(request.json["user"])})

    streak = res.get("vote_streak", 0)
    last_voted = res.get("last_voted", datetime.min)

    if datetime.now() - last_voted < timedelta(days=2):
        streak += 1
    else:
        streak += 1

    box_type = "normal"

    if streak >= 14:
        box_type = "ultra"
    elif streak >= 7:
        box_type = "great"

    db.member.update_one(
        {"_id": int(request.json["user"])},
        {
            "$set": {"vote_streak": streak, "last_voted": datetime.now()},
            "$inc": {"vote_total": 1, f"gifts_{box_type}": 1},
        },
    )

    return "Success", 200


# @app.route("/patreon", methods=["POST"])
# def patreon():
#     if "delete" in request.headers.get("X-Patreon-Event"):
#         return "", 200

#     digest = hmac.new(secret, request.data, digestmod="md5").hexdigest()
#     given = request.headers.get("X-Patreon-Signature")

#     if not hmac.compare_digest(digest, given):
#         abort(403)

#     data = request.json["data"]
#     user = [x for x in request.json["included"] if x["type"] == "user"][0]
#     rewards = [x for x in request.json["included"] if x["type"] == "reward"]

#     inc_redeems = 0

#     for reward in rewards:
#         if reward["id"] == "2608556":
#             inc_redeems += 1
#         if reward["id"] == "2610442":
#             inc_redeems += 4
#         if reward["id"] == "2611242":
#             inc_redeems += 8

#     res = db.member.update_one(
#         {"_id": int(user["attributes"]["discord_id"])},
#         {"$inc": {"redeems": inc_redeems}},
#     )

#     print(
#         "Giving "
#         + user["attributes"]["discord_id"]
#         + " "
#         + str(inc_redeems)
#         + " redeems."
#     )

#     return "", 200


if __name__ == "__main__":
    app.run()
