
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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

BOT_TOKEN = "8568388774:AAE410jVSLbC5e-7jqMNuGdDAN__xBzWoHw"
WEBAPP_URL = os.environ.get("WEBAPP_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

LEVELS = [
    (1,  "🥚 Яйцо Пикассо",               "Ну... начало положено. Главное — не продолжать!"),
    (2,  "🖍️ Дошкольник-экспрессионист",  "кринж! Очень... смело..."),
    (3,  "✏️ Подающий надежды",            "Что-то уже угадывается. Кажется. новорожденый рисовал будто"),
    (4,  "🎨 Художник выходного дня",      "Неплохо для человека без мозгов!"),
    (5,  "🖌️ Крепкий середнячок",         "Норм. но лучше спрячь."),
    (6,  "⭐ Звезда арт-кружка",           "Учительница рисования обосрала бы!"),
    (7,  "🏆 Топ класса",                  "Серьёзно, это уже что-то!"),
    (8,  "🎭 Местный Да Винчи",            "Люди оборачиваются на улице. Ну, могли бы."),
    (9,  "🔥 Почти гений",                 "Лувр пока не звонил, но скоро."),
    (10, "👑 Абсолютный чемпион",          "Микеланджело нервно курит в сторонке."),
]


def ask_gemini(image_b64: str) -> tuple[int, str]:
    prompt = """Ты весёлый и добродушный критик рисунков. Тебе прислали рисунок.

Оцени его по шкале от 1 до 10, где:
1 = просто каракули
10 = удивительно детализированный рисунок

Ответь СТРОГО в формате JSON (без markdown, без лишних слов):
{"score": 7, "comment": "твой весёлый комментарий на русском, 1-2 предложения, без занудства"}

Комментарий должен быть живым, с юмором, как будто друг смотрит на рисунок."""

    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}",
        headers={"Content-Type": "application/json"},
        json={
            "contents": [{
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": image_b64
                        }
                    },
                    {"text": prompt}
                ]
            }]
        },
        timeout=30,
    )
    data = response.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    text = text.replace("```json", "").replace("```", "").strip()
    parsed = json.loads(text)
    score = max(1, min(10, int(parsed["score"])))
    comment = parsed["comment"]
    return score, comment


def format_result(score: int, comment: str) -> str:
    _, level_name, level_desc = LEVELS[score - 1]
    bar = "█" * score + "░" * (10 - score)
    return (
        f"{level_name}\n\n"
        f"🎯 Счёт: {score}/10\n"
        f"[{bar}]\n\n"
        f"💬 {comment}\n\n"
        f"_{level_desc}_"
    )


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
    image_b64 = image_data_url.split(",", 1)[1]
    image_bytes = base64.b64decode(image_b64)
    try:
        score, comment = ask_gemini(image_b64)
        text = format_result(score, comment)
    except Exception as e:
        logging.exception(e)
        text = "Не получилось оценить 😅 Попробуй ещё раз!"
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                  data={"chat_id": chat_id},
                  files={"photo": ("drawing.png", image_bytes, "image/png")}, timeout=15)
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                  data={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=15)
    return jsonify(ok=True)


def run_flask():
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Привет! 👋 Пришли мне фото своего рисунка, "
        "и я скажу что думаю 🎨\n\nБез занудства, обещаю 😄"
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
    await update.message.reply_text("Смотрю... 🧐")
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = await file.download_as_bytearray()
    image_b64 = base64.b64encode(bytes(image_bytes)).decode()
    try:
        score, comment = ask_gemini(image_b64)
        text = format_result(score, comment)
    except Exception as e:
        logging.exception(e)
        text = "Не получилось оценить 😅 Попробуй ещё раз!"
    await update.message.reply_text(text,
