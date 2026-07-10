"""
Отправка отчётов в Telegram.

ВАЖНО: любое сообщение длиннее ~200 слов автоматически сжимается через
лёгкую модель до короткого summary (100-200 слов, без воды) ПЕРЕД
отправкой — по запросу Валика: "пускай думает сколько надо внутри, а
в отчёт пусть приходит коротко по сути". Внутренние рассуждения
(обсуждения совета, Review Gate, дискуссии) остаются полными и никуда
не теряются — они по-прежнему целиком пишутся в вики компании через
curate_knowledge(), просто в Telegram теперь всегда уходит сжатая
версия, а не полный текст.

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

import asyncio
import os

import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

MAX_TELEGRAM_LEN = 4000  # у Telegram лимит 4096, оставляем запас

# Сообщения короче этого не сжимаются — короткие реплики чата, алерты
# об ошибках и т.п. уже итак по сути, незачем гонять их через модель.
SUMMARIZE_THRESHOLD_CHARS = 900  # примерно 150-200 слов


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


async def _summarize(text: str) -> str:
    """Сжимает длинный текст до 100-200 слов, без воды, по сути."""
    from config.client_factory import get_chat_client
    from config.models import TELEGRAM_SUMMARIZER_MODEL
    from workflows._common import ask

    client = get_chat_client(TELEGRAM_SUMMARIZER_MODEL)
    prompt = f"""
Вот подробное сообщение/отчёт:

{text}

Сожми до 100-200 слов — коротко, по сути, без воды и без
бюрократических заголовков-простыней. Сохрани самое важное: что
произошло/решено, ключевой вывод или вердикт, что делать дальше (если
применимо). Если это был диалог/дискуссия — передай суть позиций, а
не пересказывай реплику за репликой. Без markdown-звёздочек, простой
текст для Telegram.
"""
    return await ask(client, prompt)


def _maybe_summarize(text: str) -> str:
    """Синхронная обёртка — send_telegram_report сама синхронная и
    вызывается из множества мест без await, поэтому короткий async
    вызов сжатия оборачиваем в asyncio.run() здесь же."""
    if len(text) <= SUMMARIZE_THRESHOLD_CHARS:
        return text
    try:
        return asyncio.run(_summarize(text))
    except Exception as e:
        # Если сжатие само упало (сбой модели/сети) — лучше отправить
        # длинный оригинал, чем не отправить ничего.
        print(f"[telegram] Не удалось сжать отчёт ({e}) — отправляю как есть.")
        return text


def send_telegram_report(text: str) -> None:
    """Отправляет текст в Telegram — длинные сообщения автоматически
    сжимаются до короткого summary перед отправкой (см. модуль выше).

    Если TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID не заданы — просто печатает
    предупреждение в консоль и ничего не отправляет (не роняет программу).
    """
    text = _maybe_summarize(text)

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
