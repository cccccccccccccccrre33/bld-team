"""
Отправка итогового отчёта заседания совета в Telegram.

Использует обычный Bot API напрямую через requests — без лишних
зависимостей. Нужны два значения в .env:

TELEGRAM_BOT_TOKEN — токен бота (создаётся у @BotFather в Telegram:
    /newbot -> следуешь шагам -> получаешь токен вида 123456:ABC-DEF...)
TELEGRAM_CHAT_ID — куда слать. Если хочешь получать себе в личку:
    1. Напиши своему боту любое сообщение (просто "старт").
    2. Открой в браузере:
       https://api.telegram.org/bot<TOKEN>/getUpdates
    3. Найди в ответе "chat":{"id": ...} — это и есть твой chat_id.
"""

import os
import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

MAX_TELEGRAM_LEN = 4000  # у Telegram лимит 4096, оставляем запас


def _chunk_text(text: str, limit: int = MAX_TELEGRAM_LEN) -> list[str]:
    """Режет длинный текст на части по границам строк, не разрывая слова."""
    if len(text) <= limit:
        return [text]
    chunks = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > limit:
            if current:
                chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks


def send_telegram_report(text: str) -> None:
    """Отправляет текст в Telegram, разбивая на части при необходимости.

    Если TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID не заданы — просто печатает
    предупреждение в консоль и ничего не отправляет (не роняет программу).
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(
            "[telegram] TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID не заданы в .env — "
            "отчёт не отправлен, только напечатан выше."
        )
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for chunk in _chunk_text(text):
        response = requests.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": chunk},
            timeout=15,
        )
        if response.status_code != 200:
            print(f"[telegram] Ошибка отправки: {response.status_code} {response.text}")
            return
    print("[telegram] Отчёт отправлен.")
