"""
Запускает server.py (Flask) и bot.py (Telegram) в одном процессе.
Railway поддерживает только один процесс на сервис.
"""
import threading
import logging
import os
import base64
import hashlib
import hmac
import json
from urllib.parse import parse_qsl

import requests
from flask import Flask, request, jsonify, send_from_directory
from telegram import Update, WebAppInfo, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, ContextTypes, filters,
)
from analysis import analyze_drawing, score_to_text, DISCLAIMER

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

BOT_TOKEN = "8568388774:AAE410jVSLbC5e-7jqMNuGdDAN__xBzWoHw"
WEBAPP_URL = os.environ.get("WEBAPP_URL")

flask_app = Flask(__name__, static_folder=None)
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


@flask_app.route("/")
def index():
    return send_from_directory(WEBAPP_DIR, "index.html")


@flask_app.route("/submit", methods=["POST"])
def submit():
    body = request.get_json(force=True, silent=True) or {}
    parsed = validate_init_data(body.get("initData", ""))
    if not parsed:
        return jsonify(ok=False, error="invalid initData"), 403
    user = json.loads(parsed.get("user", "{}"))
    chat_id = user.get("id")
    image_data_url = body.get("image", "")
    if not image_data_url.startswith("data:image/png;base64,"):
        return jsonify(ok=False, error="bad image format"), 400
    image_bytes = base64.b64decode(image_data_url.split(",", 1)[1])
    try:
        metrics = analyze_drawing(image_bytes)
        text = score_to_text(metrics)
    except Exception as e:
        text = f"Не получилось проанализировать: {e}"
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                  data={"chat_id": chat_id},
                  files={"photo": ("drawing.png", image_bytes, "image/png")}, timeout=15)
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                  data={"chat_id": chat_id, "text": text}, timeout=15)
    return jsonify(ok=True)


def run_flask():
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Привет! Можно:\n"
        "1) Прислать фото готового рисунка человека.\n"
        "2) Нажать кнопку «Нарисовать», чтобы рисовать прямо здесь.\n\n"
        + DISCLAIMER
    )
    if WEBAPP_URL:
        keyboard = ReplyKeyboardMarkup.from_button(
            KeyboardButton(text="🎨 Нарисовать", web_app=WebAppInfo(url=WEBAPP_URL)),
            resize_keyboard=True,
        )
        await update.message.reply_text(text, reply_markup=keyboard)
    else:
        await update.message.reply_text(text)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = await file.download_as_bytearray()
    await update.message.reply_text("Анализирую рисунок...")
    try:
        metrics = analyze_drawing(bytes(image_bytes))
        text = score_to_text(metrics)
    except Exception:
        text = "Не получилось проанализировать. Пришли более чёткое фото."
    await update.message.reply_text(text)


async def handle_other(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Пришли фото рисунка или нажми «Нарисовать»."
    )


def run_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(~filters.PHOTO, handle_other))
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    run_bot()
