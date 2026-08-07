"""
Отправка отчётов в Telegram.

РАНЬШЕ здесь был отдельный LLM-вызов (_summarize), который сжимал любое
сообщение длиннее ~900 символов до 100-200 слов ПЕРЕД отправкой — и
это был уже ВТОРОЙ слой сжатия: вызывающий код (workflows/_common.py)
до недавнего времени тоже гонял полный отчёт через compile_brief()
(ещё один LLM-вызов) прежде чем передать сюда. То есть на каждый
отчёт — до двух вызовов модели ТОЛЬКО ради форматирования текста, не
считая саму работу, которая этот текст породила. По прямому запросу
Валика ('не тратить токены ещё и на отчёты, мне не надо километровые
отчёты, коротко по сути и то по делу когда реально готово') оба слоя
убраны:
- compile_brief() в _common.py заменён на notify_done()/notify_failed()
  — без единого LLM-вызова, просто название + короткая пометка.
- Здесь _summarize() удалён целиком — если что-то всё же пришло длинным
  (не должно происходить при новых вызовах, но защита от старого кода/
  ошибки), текст просто обрезается по границе строки, без модели.

Подробности произошедшего никуда не делись — они как и раньше целиком
уходят в вики компании (.state/company_wiki.md) через
workflows/_common.py::curate_knowledge(), это дешёвая суммаризация
одной записи, не про Telegram. Что-то не дотянувшее до реального
завершения (обсуждения, промежуточные вердикты, статусы "начал
работу") в Telegram теперь вообще не уходит — это шум, который
Валику не нужен, а данные всё равно остаются в task_board.json /
company_threads.json / product_backlog.json — доступны по запросу,
просто не летят уведомлением на каждый чих.

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

# Если текст всё же пришёл длиннее этого — просто режем по границе
# строки (см. _chunk_text), без модели. При новых, минимальных вызовах
# (notify_done/notify_failed) это практически никогда не должно
# случаться — эта константа теперь просто страховка от забытого старого
# вызова где-то в коде, а не рабочий механизм сжатия.
HARD_TRUNCATE_CHARS = 1200


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


def _hard_truncate(text: str) -> str:
    if len(text) <= HARD_TRUNCATE_CHARS:
        return text
    return text[:HARD_TRUNCATE_CHARS].rsplit(" ", 1)[0] + "… (обрезано, полное — в вики компании)"


def send_telegram_report(text: str) -> None:
    """Отправляет текст в Telegram. Никакого LLM-сжатия — вызывающий
    код (notify_done/notify_failed в _common.py) уже отвечает за то,
    чтобы текст был коротким по смыслу, не только по символам.

    Если TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID не заданы — просто печатает
    предупреждение в консоль и ничего не отправляет (не роняет программу).
    """
    text = _hard_truncate(text)

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
