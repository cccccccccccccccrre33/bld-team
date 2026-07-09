"""
Company Pulse — единственный "постоянно живой" канал компании. Раньше
активность была россыпью несвязанных вспышек (Chevruta/Lab/Individual/
Squad Initiative — каждая начинала и заканчивала свою сессию за одну
минуту раз в несколько часов, с шансом пропуска). Ощущение было:
компания "работает" 10% дня, остальное — тишина.

Теперь есть ОДИН непрерывный тред (.state/company_thread.json,
коммитится в git между запусками — тот же паттерн, что и task board/
вики). Раз в час 1-3 случайных человека из всей компании (51 человек)
либо продолжают текущую тему, либо — если тема исчерпана или её ещё
не было — кто-то поднимает новую. Это ближе к тому, как реально
работает Slack-канал компании: сообщения появляются не залпом, а
растянуто во времени, кто-то отвечает через час.

Когда разговор реально доходит до готового к реализации решения —
уходит на approval к CTO (как и Squad/Individual Initiative), попадает
на task board, дальше по обычному циклу (реализация, Review Gate).
Большинство сообщений НЕ доходят до реализации — это нормально, живой
чат состоит по большей части из мыслей, а не из тикетов.
"""

import asyncio
import json
import random
import subprocess
from datetime import datetime
from pathlib import Path

from agents.roster import build_full_roster
from agents.team import build_team
from tools.telegram_report import send_telegram_report
from workflows._common import curate_knowledge
from workflows.cto_approval import cto_approval
from workflows.task_board import add_task, is_duplicate

STATE_DIR = Path(".state")
THREAD_PATH = STATE_DIR / "company_thread.json"

MAX_HISTORY_FOR_CONTEXT = 20
MAX_THREAD_LENGTH = 200
NEW_TOPIC_CHANCE = 0.35
DECISION_MARKERS = ["давайте реализуем", "готовы реализовать", "стоит внедрить", "предлагаю сделать это"]


def load_thread() -> list[dict]:
    if not THREAD_PATH.exists():
        return []
    try:
        return json.loads(THREAD_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_thread(thread: list[dict]) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    thread = thread[-MAX_THREAD_LENGTH:]
    THREAD_PATH.write_text(json.dumps(thread, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        subprocess.run(["git", "config", "user.name", "bld-team-bot"], check=True)
        subprocess.run(["git", "config", "user.email", "bld-team-bot@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", str(THREAD_PATH)], check=True)
        result = subprocess.run(
            ["git", "commit", "-m", "chore: company pulse — новые сообщения в треде"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            subprocess.run(["git", "push"], check=True)
    except Exception as e:
        print(f"[company_pulse] Не удалось сохранить тред в git: {e}")


def format_thread(thread: list[dict], limit: int = MAX_HISTORY_FOR_CONTEXT) -> str:
    if not thread:
        return "(тред пуст — ты первый, кто пишет сюда)"
    recent = thread[-limit:]
    return "\n".join(f"[{m['time']}] {m['who']}: {m['text']}" for m in recent)


async def pick_speakers(roster: dict, thread: list[dict]) -> list[str]:
    """1-3 человека говорят в этот час. Если тред активный — есть шанс,
    что ответит кто-то УЖЕ участвовавший (реалистичнее для продолжения
    мысли), плюс всегда есть шанс, что подключится кто-то новый."""
    count = random.choices([1, 2, 3], weights=[55, 30, 15])[0]
    recent_speakers = list({m["who"] for m in thread[-10:]}) if thread else []

    pool = list(roster.keys())
    speakers = []
    for _ in range(count):
        if recent_speakers and random.random() < 0.4:
            speakers.append(random.choice(recent_speakers))
        else:
            speakers.append(random.choice(pool))
    return speakers


async def run_pulse_tick() -> str | None:
    roster = build_full_roster()
    thread = load_thread()

    start_new_topic = not thread or random.random() < NEW_TOPIC_CHANCE
    speakers = await pick_speakers(roster, thread)

    context = format_thread(thread)
    new_messages = []

    for i, name in enumerate(speakers):
        person = roster[name]
        is_first_in_tick = i == 0

        if start_new_topic and is_first_in_tick and not thread:
            prompt = """
Ты в общем рабочем чате компании (тред, где все обсуждают систему —
идеи, наблюдения, "что если", предложения). Тред пока пуст. Начни
разговор — какая мысль о BLD System реально сейчас тебя занимает?
Пиши как в живом чате коллег — коротко, естественно, 1-3 предложения,
без формальных заголовков.
"""
        elif start_new_topic and is_first_in_tick:
            prompt = f"""
Вот последние сообщения в общем чате компании:
{context}

Текущая тема, кажется, исчерпана или ты хочешь поднять что-то новое.
Начни новую ветку разговора — идея, наблюдение, "что если" о BLD
System. Коротко, как в живом чате, 1-3 предложения.
"""
        else:
            prompt = f"""
Вот последние сообщения в общем чате компании:
{context}

Ответь в тему — согласись, поспорь, добавь деталь, задай вопрос,
предложи развитие мысли. Пиши как в живом чате коллег: коротко (1-3
предложения), естественно, не как отчёт.
"""
        response = await person.run(prompt)
        text = response.text.strip()
        msg = {"who": name, "text": text, "time": datetime.now().strftime("%H:%M")}
        new_messages.append(msg)
        thread.append(msg)
        context = format_thread(thread)

    save_thread(thread)

    combined_text = " ".join(m["text"].lower() for m in new_messages)
    decision_ready = any(marker in combined_text for marker in DECISION_MARKERS)

    telegram_lines = [f"💬 {m['who']}: {m['text']}" for m in new_messages]
    telegram_message = "\n\n".join(telegram_lines)
    send_telegram_report(telegram_message)

    if decision_ready:
        title = new_messages[-1]["text"][:120]
        if is_duplicate(title):
            print("[company_pulse] Похоже на дубль с task board — не эскалируем повторно")
            return telegram_message

        cto = build_team()["cto"]
        who = "+".join({m["who"] for m in new_messages})
        approved, comment = await cto_approval(
            f"Company Pulse ({who})", title,
            "Родилось из живого обсуждения в общем чате компании.",
            "См. контекст треда выше — конкретный план обсуждался в чате.",
        )
        verdict_msg = f"🧭 CTO по теме из чата: {'✅ ОДОБРЕНО' if approved else '❌ ОТКЛОНЕНО'} — {comment}"
        send_telegram_report(verdict_msg)

        if approved:
            add_task(title, f"pulse:{who}", status="in_progress", reason=comment)
            await curate_knowledge(f"Company Pulse → задача: {who}", f"{telegram_message}\n\n{verdict_msg}")

    return telegram_message


async def main():
    result = await run_pulse_tick()
    if result:
        print(result)


if __name__ == "__main__":
    asyncio.run(main())
