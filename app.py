from flask import Flask, request, abort
import hmac
import os

secret = os.getenv("PATREON_SECRET").encode("ascii")

app = Flask(__name__)

@app.route("/patreon", methods=["POST"])
def webhook():
    if request.method == "POST":
        digest = hmac.new(secret, request.data, digestmod="md5")
        if not hmac.compare_digest(digest.hexdigest(), request.headers.get("X-Patreon-Signature")):
            abort(403)

        print(request.json)

        return "", 200
    else:
        abort(400)


if __name__ == "__main__":
    app.run()
