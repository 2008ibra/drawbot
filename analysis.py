import io
import cv2
import numpy as np
from PIL import Image

DISCLAIMER = (
    "⚠️ Это упрощённая игровая оценка по простым параметрам изображения "
    "(детализация, симметрия, заполненность листа), а НЕ настоящий "
    "психологический тест. Она не отражает реальный уровень развития "
    "и не заменяет консультацию специалиста."
)


def analyze_drawing(image_bytes: bytes) -> dict:
    """Считает простые метрики изображения: количество контуров,
    степень заполненности листа линиями, симметрию по вертикали."""
    img = Image.open(io.BytesIO(image_bytes)).convert("L")
    arr = np.array(img)

    _, thresh = cv2.threshold(arr, 200, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(
        thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
    )
    num_contours = len([c for c in contours if cv2.contourArea(c) > 15])

    fill_ratio = float(np.mean(thresh > 0))

    h, w = thresh.shape
    left = thresh[:, : w // 2]
    right = cv2.flip(thresh[:, w // 2 :], 1)
    min_w = min(left.shape[1], right.shape[1])
    diff = np.abs(
        left[:, :min_w].astype(int) - right[:, :min_w].astype(int)
    )
    symmetry_score = 1.0 - float(np.mean(diff) / 255.0)

    return {
        "num_contours": num_contours,
        "fill_ratio": fill_ratio,
        "symmetry_score": symmetry_score,
    }


def score_to_text(metrics: dict) -> str:
    contours = metrics["num_contours"]
    fill = metrics["fill_ratio"]
    symmetry = metrics["symmetry_score"]

    if contours < 8:
        detail_comment = "рисунок довольно лаконичный, мало отдельных элементов"
    elif contours < 25:
        detail_comment = "средняя детализация — есть основные элементы фигуры"
    else:
        detail_comment = "высокая детализация, много отдельных штрихов и элементов"

    if fill < 0.03:
        fill_comment = "лист используется слабо, рисунок занимает мало места"
    elif fill < 0.12:
        fill_comment = "умеренное заполнение листа"
    else:
        fill_comment = "лист заполнен плотно"

    symmetry_comment = (
        "хорошая визуальная симметрия" if symmetry > 0.7
        else "симметрия средняя" if symmetry > 0.5
        else "заметная асимметрия (что нормально для рисунков от руки)"
    )

    return (
        f"📊 Результаты анализа:\n"
        f"• Контуров/деталей: {contours} — {detail_comment}\n"
        f"• Заполненность листа: {fill*100:.1f}% — {fill_comment}\n"
        f"• Симметрия: {symmetry*100:.0f}% — {symmetry_comment}\n\n"
        f"{DISCLAIMER}"
    )
