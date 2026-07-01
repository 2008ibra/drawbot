import base64
import hashlib
import hmac
import json
import os
from urllib.parse import parse_qsl

import requests
from flask import Flask, request, jsonify, send_from_directory

from analysis import analyze_drawing, score_to_text

BOT_TOKEN = "8568388774:AAELegEnda9VKtMgkOazs4VMCTWqYBM1G5M"

app = Flask(__name__, static_folder=None)
WEBAPP_DIR = os.path.join(os.path.dirname(__file__), "webapp")


def validate_init_data(init_data: str):
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed_hash, received_hash):
        return None
    return parsed


@app.route("/")
def index():
    return send_from_directory(WEBAPP_DIR, "index.html")


@app.route("/submit", methods=["POST"])
def submit():
    body = request.get_json(force=True, silent=True) or {}
    init_data = body.get("initData", "")
    image_data_url = body.get("image", "")

    parsed = validate_init_data(init_data)
    if not parsed:
        return jsonify(ok=False, error="invalid initData"), 403

    user = json.loads(parsed.get("user", "{}"))
    chat_id = user.get("id")

    if not image_data_url.startswith("data:image/png;base64,"):
        return jsonify(ok=False, error="bad image format"), 400
    image_bytes = base64.b64decode(image_data_url.split(",", 1)[1])

    try:
        metrics = analyze_drawing(image_bytes)
        text = score_to_text(metrics)
    except Exception as e:
        text = f"Не получилось проанализировать: {e}"

    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
        data={"chat_id": chat_id},
        files={"photo": ("drawing.png", image_bytes, "image/png")},
        timeout=15,
    )
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": chat_id, "text": text},
        timeout=15,
    )
    return jsonify(ok=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
