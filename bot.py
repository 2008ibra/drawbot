import logging
import os

from telegram import Update, WebAppInfo, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from analysis import analyze_drawing, score_to_text, DISCLAIMER

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8568388774:AAELegEnda9VKtMgkOazs4VMCTWqYBM1G5M"
WEBAPP_URL = os.environ.get("WEBAPP_URL")  # Railway выдаст этот адрес


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Привет! Можно:\n"
        "1) Прислать фото готового рисунка человека.\n"
        "2) Нажать кнопку «Нарисовать», чтобы рисовать прямо здесь.\n\n"
        + DISCLAIMER
    )
    if WEBAPP_URL:
        keyboard = ReplyKeyboardMarkup.from_button(
            KeyboardButton(
                text="🎨 Нарисовать",
                web_app=WebAppInfo(url=WEBAPP_URL),
            ),
            resize_keyboard=True,
        )
        await update.message.reply_text(text, reply_markup=keyboard)
    else:
        await update.message.reply_text(text)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start — начать\n"
        "/help — помощь\n\n"
        "Нажми «Нарисовать» или пришли фото рисунка."
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = await file.download_as_bytearray()

    await update.message.reply_text("Анализирую рисунок...")

    try:
        metrics = analyze_drawing(bytes(image_bytes))
        text = score_to_text(metrics)
    except Exception:
        logger.exception("Ошибка анализа")
        text = "Не получилось проанализировать. Пришли более чёткое фото."

    await update.message.reply_text(text)


async def handle_other(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Пришли фото рисунка или нажми «Нарисовать»."
    )


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(~filters.PHOTO, handle_other))
    logger.info("Бот запущен")
    app.run_polling()


if __name__ == "__main__":
    main()
