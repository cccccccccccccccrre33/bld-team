"""
Company Pulse — "постоянно живой" канал компании. Раньше был ОДИН
непрерывный тред с 2-4 говорящими за тик — по просьбе Валика теперь
за тик идёт НЕСКОЛЬКО (2-3) НЕЗАВИСИМЫХ параллельных мини-разговоров
на разные темы одновременно — заметно больше разных идей летает по
компании единовременно, а не одна тема за раз.

Все темы живут в .state/company_threads.json — список независимых
тредов (id, topic, messages, last_active), коммитится в git между
запусками. Каждый тик: часть тредов продолжается (кто-то отвечает в
уже начатый разговор), часть — новые (кто-то поднимает свежую тему).
Старые/затихшие треды архивируются в вики и не растут бесконечно.

Когда какой-то из тредов реально доходит до готового решения — уходит
на approval к CTO, попадает на task board, реализуется — как и раньше.
Каждый говорящий использует свою обычную модель (без экономии на
качестве мысли, по явному запросу Валика).
"""

import asyncio
import json
import random
import subprocess
from datetime import datetime
from pathlib import Path

from agents.roster import build_full_roster
from config.client_factory import get_chat_client
from config.models import BOARD_MODEL_ASSIGNMENTS
from tools.telegram_report import send_telegram_report
from workflows._common import ask, compile_brief, curate_knowledge, fair_sample, record_participation, safe_agent_run, sync_repos_or_alert
from workflows.cto_approval import cto_approval
from workflows.task_board import add_task, is_duplicate

STATE_DIR = Path(".state")
THREADS_PATH = STATE_DIR / "company_threads.json"

MAX_HISTORY_FOR_CONTEXT = 15
MAX_ACTIVE_THREADS = 6  # старые/затихшие архивируются, чтобы не расти бесконечно
THREADS_PER_TICK = None  # None = случайно 2-3, см. ниже
NEW_TOPIC_CHANCE = 0.4  # выше, чем раньше — больше новых тем, не только продолжение старых


def load_threads() -> list[dict]:
    if not THREADS_PATH.exists():
        return []
    try:
        return json.loads(THREADS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_threads(threads: list[dict]) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    # Архивируем самые старые сверх лимита — не теряем их: то, что
    # реально решилось, уже ушло в вики через curate_knowledge при
    # эскалации; то, что просто затихло, отваливается молча, как в
    # реальном чате старые ветки уходят вниз и забываются.
    threads = sorted(threads, key=lambda t: t["last_active"], reverse=True)[:MAX_ACTIVE_THREADS]
    THREADS_PATH.write_text(json.dumps(threads, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        subprocess.run(["git", "config", "user.name", "bld-team-bot"], check=True)
        subprocess.run(["git", "config", "user.email", "bld-team-bot@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", str(THREADS_PATH)], check=True)
        result = subprocess.run(
            ["git", "commit", "-m", "chore: company pulse — новые сообщения"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            subprocess.run(["git", "push"], check=True)
    except Exception as e:
        print(f"[company_pulse] Не удалось сохранить треды в git: {e}")


def format_thread_messages(messages: list[dict], limit: int = MAX_HISTORY_FOR_CONTEXT) -> str:
    if not messages:
        return "(эта ветка только начинается)"
    recent = messages[-limit:]
    return "\n".join(f"[{m['time']}] {m['who']}: {m['text']}" for m in recent)


async def assess_readiness(messages: list[dict]) -> dict | None:
    """Смотрит на ВЕСЬ виток разговора конкретной ветки (не только
    последнее сообщение) и решает, выкристаллизовалась ли там
    конкретная задача — даже без явных слов "давайте реализуем"."""
    context = format_thread_messages(messages, limit=15)
    client = get_chat_client(BOARD_MODEL_ASSIGNMENTS.get("agenda_setter", "gpt-5.2"))

    prompt = f"""
Вот разговор в одной из веток чата компании:
{context}

Оцени: выкристаллизовалась ли здесь КОНКРЕТНАЯ задача, готовая к
реализации (не абстрактный риск, а понятный следующий шаг) — даже
если участники не произносили буквально "давайте реализуем". Учитывай
совокупность реплик.

Если да — ответь строго:
ГОТОВО: ДА
ЗАДАЧА: [одна конкретная формулировка для инженера]

Если нет:
ГОТОВО: НЕТ
"""
    response = await ask(client, prompt)
    if "ГОТОВО: ДА" not in response.upper():
        return None
    title = ""
    for line in response.split("\n"):
        if line.upper().startswith("ЗАДАЧА:"):
            title = line.split(":", 1)[-1].strip()
            break
    return {"title": title} if title else None


async def run_one_thread(roster: dict, thread: dict | None, excluded: set[str]) -> tuple[dict | None, list[dict]]:
    """Прогоняет ОДНУ независимую мини-ветку (1-2 реплики за тик).
    excluded — люди, уже занятые в других ветках этого же тика (чтобы
    один человек не говорил одновременно в двух разных разговорах).
    Возвращает (обновлённый thread-объект или None, новые сообщения
    этого тика). None означает "в этот тик эта ветка молчит" (например,
    несколько случайных людей подряд оказались на временно недоступной
    модели) — это НЕ ошибка, вызывающий код просто пропускает слот."""
    pool = [p for p in roster if p not in excluded]
    if not pool:
        pool = list(roster.keys())

    is_new = thread is None
    if is_new:
        prompt = """
Ты в одном из рабочих чатов компании — свободная ветка для новых
мыслей о системе. Начни разговор — какая мысль о BLD System реально
сейчас тебя занимает? Пиши как в живом чате: коротко, естественно,
1-3 предложения, без формальных заголовков.
"""
        # Пробуем нескольких разных случайных людей подряд — если у
        # первого модель временно недоступна, берём другого, а не
        # роняем весь тик из-за одного невезучего randomly picked агента.
        candidates = fair_sample(pool, k=min(3, len(pool)))
        for starter in candidates:
            person = roster[starter]
            text = await safe_agent_run(person, prompt, person_label=starter)
            if text is None:
                continue
            msg = {"who": starter, "text": text, "time": datetime.now().strftime("%H:%M")}
            new_thread = {
                "id": f"t{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(10,99)}",
                "topic": text[:80],
                "messages": [msg],
                "last_active": datetime.now().isoformat(),
            }
            return new_thread, [msg]
        print("[company_pulse] Все кандидаты на старт новой ветки временно недоступны — пропускаем слот в этом тике.")
        return None, []

    # Продолжение существующей ветки — 1 ответ за тик (не залпом,
    # чтобы разговор тянулся во времени, как реальный Slack-тред).
    context = format_thread_messages(thread["messages"])
    prompt = f"""
Вот разговор в одной из веток чата компании:
{context}

Ответь в тему — согласись, поспорь, добавь деталь, задай вопрос,
предложи развитие мысли. Коротко (1-3 предложения), как в живом чате.
"""
    candidates = fair_sample(pool, k=min(3, len(pool)))
    for speaker in candidates:
        person = roster[speaker]
        text = await safe_agent_run(person, prompt, person_label=speaker)
        if text is None:
            continue
        msg = {"who": speaker, "text": text, "time": datetime.now().strftime("%H:%M")}
        thread["messages"].append(msg)
        thread["messages"] = thread["messages"][-60:]
        thread["last_active"] = datetime.now().isoformat()
        return thread, [msg]
    print(f"[company_pulse] Все кандидаты на ответ в ветке '{thread['topic']}' временно недоступны — ветка молчит в этом тике.")
    return thread, []


async def escalate_if_ready(thread: dict) -> str | None:
    """Проверяет готовность конкретной ветки и, если да, гонит её через
    CTO approval -> реализация. Возвращает отдельный отчёт или None."""
    readiness = await assess_readiness(thread["messages"])
    if not readiness:
        return None
    title = readiness["title"]
    if is_duplicate(title):
        print(f"[company_pulse] '{title}' похоже на дубль с task board — не эскалируем")
        return None

    who = "+".join({m["who"] for m in thread["messages"][-6:]})
    approved, comment = await cto_approval(
        f"Company Pulse ({who})", title,
        "Родилось из живого обсуждения в одной из веток чата компании.",
        "См. контекст ветки — участники обсуждали конкретный подход.",
    )
    verdict_msg = f"🧭 CTO по теме из ветки \"{thread['topic']}\": {'✅ ОДОБРЕНО' if approved else '❌ ОТКЛОНЕНО'} — {comment}"
    send_telegram_report(verdict_msg)

    if not approved:
        return verdict_msg

    from workflows.task_board import can_take_more, update_task_status

    if not can_take_more():
        print(f"[company_pulse] Лимит одновременных задач (MAX_CONCURRENT) исчерпан — '{title}' ждёт своей очереди, не запускаем сейчас")
        return f"{verdict_msg}\n\n⏳ Лимит параллельных задач исчерпан — реализация отложена до освобождения слота."

    task_id = add_task(title, f"pulse:{who}", status="in_progress", reason=comment)
    print(f"[company_pulse] Задача одобрена — запускаем реализацию: {title}")

    if not await sync_repos_or_alert():
        update_task_status(task_id, "rejected", "sync_repos_or_alert не прошёл")
        return verdict_msg

    from workflows.engineering_task import run_engineering_task

    try:
        engineering_report = await run_engineering_task(title)
    except Exception as e:
        print(f"[company_pulse] run_engineering_task упал с исключением: {e}")
        update_task_status(task_id, "rejected", f"Упало с необработанным исключением: {e}")
        send_telegram_report(f"❌ Реализация \"{title}\" (из ветки \"{thread['topic']}\") упала с ошибкой: {e}")
        return f"{verdict_msg}\n\n❌ Реализация упала с ошибкой: {e}"

    update_task_status(task_id, "done")

    full = f"👷 РЕАЛИЗАЦИЯ ПО ИТОГАМ ВЕТКИ \"{thread['topic']}\"\n\n{engineering_report}"
    brief = await compile_brief(full, context_hint="реализация по итогам обсуждения в Company Pulse")
    send_telegram_report(brief)
    await curate_knowledge(f"Company Pulse → реализовано: {who}", f"{verdict_msg}\n\n{full}")
    return full


async def run_pulse_tick() -> str | None:
    try:
        from tools.repo_tools import clone_or_update_repos
        print(clone_or_update_repos())
    except Exception as e:
        print(f"[company_pulse] Синхронизация репо не удалась (продолжаем без неё): {e}")

    roster = build_full_roster()
    threads = load_threads()

    n_slots = THREADS_PER_TICK or random.choices([2, 3], weights=[55, 45])[0]
    excluded: set[str] = set()
    all_new_messages: list[tuple[str, dict]] = []  # (topic, msg)
    updated_threads: dict[str, dict] = {t["id"]: t for t in threads}

    for i in range(n_slots):
        # Выбираем: продолжить существующую ветку или начать новую.
        existing = list(updated_threads.values())
        pick_new = not existing or random.random() < NEW_TOPIC_CHANCE
        thread = None if pick_new else random.choice(existing)

        updated_thread, new_msgs = await run_one_thread(roster, thread, excluded)
        if updated_thread is None:
            # Все кандидаты на этот слот были временно недоступны —
            # пропускаем слот целиком, не крашим весь тик.
            continue
        updated_threads[updated_thread["id"]] = updated_thread
        for m in new_msgs:
            excluded.add(m["who"])
            all_new_messages.append((updated_thread["topic"], m))
            record_participation(m["who"])

    save_threads(list(updated_threads.values()))

    if not all_new_messages:
        return None

    lines_by_topic: dict[str, list[str]] = {}
    for topic, m in all_new_messages:
        lines_by_topic.setdefault(topic, []).append(f"💬 {m['who']}: {m['text']}")

    telegram_message = "\n\n".join(
        f"📌 {topic}\n" + "\n".join(lines) for topic, lines in lines_by_topic.items()
    )
    send_telegram_report(telegram_message)

    # Проверяем готовность у ВСЕХ веток, что получили сообщение в этот
    # тик (не только у одной, как раньше) — каждая независима.
    touched_thread_ids = {tid for tid, t in updated_threads.items() if t["topic"] in lines_by_topic}
    for tid in touched_thread_ids:
        await escalate_if_ready(updated_threads[tid])

    return telegram_message


async def main():
    result = await run_pulse_tick()
    if result:
        print(result)


if __name__ == "__main__":
    asyncio.run(main())
