
import threading
import logging
import os
import base64
import hashlib
import hmac
import json
import io
from urllib.parse import parse_qsl
 
import cv2
import numpy as np
from PIL import Image
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
 
 
def analyze_drawing(image_bytes: bytes) -> int:
    img = Image.open(io.BytesIO(image_bytes)).convert("L")
    arr = np.array(img)
 
    _, thresh = cv2.threshold(arr, 200, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    num_contours = len([c for c in contours if cv2.contourArea(c) > 15])
 
    fill_ratio = float(np.mean(thresh > 0))
 
    h, w = thresh.shape
    left = thresh[:, :w // 2]
    right = cv2.flip(thresh[:, w // 2:], 1)
    min_w = min(left.shape[1], right.shape[1])
    diff = np.abs(left[:, :min_w].astype(int) - right[:, :min_w].astype(int))
    symmetry = 1.0 - float(np.mean(diff) / 255.0)
 
    # Переводим в очки 1-10
    # контуры: 0-5 = 1, 5-10 = 2, ..., 45+ = 10
    contour_score = min(10, max(1, int(num_contours / 5)))
    # заполненность: 0-2% = 1, 2-4% = 2, ..., 18%+ = 10
    fill_score = min(10, max(1, int(fill_ratio * 120)))
    # симметрия: всегда примерно 0.5-0.8, нормализуем от 0.4 до 0.9
    symmetry_score = min(10, max(1, int((symmetry - 0.4) / 0.05) + 1))
 
    score = round(contour_score * 0.6 + fill_score * 0.3 + symmetry_score * 0.1)
    return max(1, min(10, score))
 
 
def format_result(score: int) -> str:
    _, level_name, level_desc = LEVELS[score - 1]
    bar = "█" * score + "░" * (10 - score)
    return (
        f"{level_name}\n\n"
        f"🎯 Счёт: {score}/10\n"
        f"[{bar}]\n\n"
        f"_{level_desc}_"
    )
 
 
# ── Flask ──────────────────────────────────────────────────────────
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
        score = analyze_drawing(image_bytes)
        text = format_result(score)
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
 
 
# ── Telegram bot ───────────────────────────────────────────────────
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
    try:
        score = analyze_drawing(bytes(image_bytes))
        text = format_result(score)
    except Exception as e:
        logging.exception(e)
        text = "Не получилось оценить 😅 Попробуй ещё раз!"
    await update.message.reply_text(text, parse_mode="Markdown")
 
 
async def handle_other(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Пришли фото рисунка! 🖼️")
 
 
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
 
