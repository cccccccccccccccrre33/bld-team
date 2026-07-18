"""
Инициатива отряда — независимый цикл работы без совета директоров.

Каждый отряд запускается 2-3 раза в день автономно:
1. Читает task board — что уже в работе, нет ли дублирования
2. Сканирует реальный код в своей зоне ответственности
3. Формулирует proposal (задача / почему / как)
4. Решает: мелкая (берёт сам) или серьёзная (идёт к CTO)
5. Если CTO одобрил (или взял сам) — выполняет через run_squad_task
6. Пишет в Telegram отчёт + обновляет task board + вики

Это и есть реальная автономная работа команды, а не просто реакция
на совет директоров.
"""

import asyncio
import json
import sys
from pathlib import Path

from agents.squads import SQUADS
from tools.repo_tools import clone_or_update_repos, grep_repo, git_log
from tools.telegram_report import send_telegram_report
from workflows._common import ask, compile_brief, curate_knowledge
from workflows.cto_approval import cto_approval
from workflows.squad_task import run_squad_task
from workflows.task_board import (
    add_task, can_take_more, get_board_summary,
    is_duplicate, update_task_status,
)

# Ключевые слова в задаче, которые указывают на "мелкую" — не требует
# approval CTO. Отряд сам решает, но культура честности обязательна.
MINOR_FIX_KEYWORDS = [
    "опечатк", "комментари", "docstring", "логирован",
    "print(", "todo", "fixme", "rename", "typo", "пробел",
]


def is_minor_fix(task_title: str) -> bool:
    return any(kw in task_title.lower() for kw in MINOR_FIX_KEYWORDS)


def get_relevant_pulse_threads(domain_keywords: list[str], limit: int = 3) -> str:
    """Та же логика, что в individual_initiative.py — не даёт хорошим
    мыслям из Company Pulse умирать в .state/company_threads.json
    непрочитанными отрядом, в чью зону они как раз попадают."""
    path = Path(".state/company_threads.json")
    if not path.exists() or not domain_keywords:
        return ""
    try:
        threads = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    matches = []
    for t in threads:
        text = " ".join(m.get("text", "") for m in t.get("messages", [])).lower()
        if any(kw.lower() in text for kw in domain_keywords):
            last_msgs = t["messages"][-3:]
            snippet = "\n".join(f"  {m['who']}: {m['text'][:220]}" for m in last_msgs)
            matches.append(f'• "{t["topic"]}":\n{snippet}')
    if not matches:
        return ""
    matches = matches[-limit:]
    return (
        "\n\nНЕДАВНИЕ ОБСУЖДЕНИЯ КОЛЛЕГ В ОБЩЕМ ЧАТЕ (Company Pulse) В ВАШЕЙ ЗОНЕ "
        "— ещё не доведены до задачи:\n" + "\n".join(matches)
        + "\n\nМожешь взять любую из этих мыслей вместо/вместе со сканированием кода.\n"
    )


async def squad_proposal_agent(squad_key: str) -> dict | None:
    """Лид отряда сканирует код в своей зоне и формулирует proposal.

    Возвращает dict с title/reason/how или None если нечего предложить
    (нет реальных проблем или лимит параллельных задач исчерпан).
    """
    squad = SQUADS[squad_key]

    if not can_take_more():
        print(f"[{squad_key}] Лимит параллельных задач ({4}) исчерпан — пропускаем")
        return None

    board_summary = get_board_summary()

    from config.client_factory import get_chat_client
    from config.models import BOARD_MODEL_ASSIGNMENTS

    client = get_chat_client(BOARD_MODEL_ASSIGNMENTS.get("agenda_setter", "gpt-5.2"))
    scout = client.as_agent(
        name=f"scout_{squad_key}",
        instructions=f"Ищешь конкретную техническую проблему в зоне {squad['label']}.",
        tools=[git_log, grep_repo],
    )

    domain_hint = ", ".join(squad["domain_keywords"][:6])

    prompt = f"""
Ты — scout отряда {squad['label']}. Зона ответственности: {domain_hint}.

Текущая доска задач (что уже в работе — НЕ дублируй это):
{board_summary}
{get_relevant_pulse_threads(squad["domain_keywords"])}
Посмотри реальный код через git_log/grep_repo в репозиториях bld-system
и bld-panel. Найди ОДНУ конкретную реальную проблему в твоей зоне
ответственности — баг, технический долг, слабое место — которой ещё нет
на доске.

Если ничего реального нет (всё в порядке или всё уже в работе) —
ответь строго: НЕТ ЗАДАЧИ

Иначе ответь строго в формате (без лишних слов):
ЗАДАЧА: [одна строка, конкретная]
ПОЧЕМУ: [2-3 предложения — реальная проблема, не теория]
КАК: [2-3 предложения — конкретный план исправления]
"""
    response = await scout.run(prompt)
    text = response.text.strip()

    if "НЕТ ЗАДАЧИ" in text.upper() or len(text) < 30:
        return None

    # Парсим
    result = {}
    for line in text.split("\n"):
        if line.upper().startswith("ЗАДАЧА:"):
            result["title"] = line.split(":", 1)[-1].strip()
        elif line.upper().startswith("ПОЧЕМУ:"):
            result["reason"] = line.split(":", 1)[-1].strip()
        elif line.upper().startswith("КАК:"):
            result["how"] = line.split(":", 1)[-1].strip()

    if not result.get("title"):
        return None

    # Проверка на дубль
    if is_duplicate(result["title"]):
        print(f"[{squad_key}] Дубль на доске — пропускаем: {result['title']}")
        return None

    return result


async def run_squad_initiative(squad_key: str) -> None:
    """Полный цикл инициативы одного отряда."""
    squad = SQUADS[squad_key]
    squad_label = squad["label"]

    print(f"\n{'='*60}")
    print(f"[{squad_key}] ИНИЦИАТИВА — {squad_label}")
    print(f"{'='*60}")

    proposal = await squad_proposal_agent(squad_key)
    if not proposal:
        print(f"[{squad_key}] Нечего предлагать — пропускаем")
        return

    title = proposal["title"]
    reason = proposal.get("reason", "")
    how = proposal.get("how", "")

    print(f"[{squad_key}] Proposal: {title}")

    minor = is_minor_fix(title)

    if minor:
        task_id = add_task(title, squad_key, status="self_approved",
                           reason=reason, how=how)
        update_task_status(task_id, "in_progress")
        print(f"[{squad_key}] Мелкая задача — берём без approval CTO")
        cto_comment = "Взято самостоятельно как мелкое исправление."
        approved = True
    else:
        print(f"[{squad_key}] Запрашиваем approval у CTO...")
        task_id = add_task(title, squad_key, status="proposed",
                           reason=reason, how=how)
        approved, cto_comment = await cto_approval(squad_label, title, reason, how)

        if approved:
            update_task_status(task_id, "in_progress", cto_comment)
            print(f"[{squad_key}] CTO одобрил: {cto_comment}")
        else:
            update_task_status(task_id, "rejected", cto_comment)
            report = (
                f"❌ CTO ОТКЛОНИЛ ЗАДАЧУ\n\n"
                f"Отряд: {squad_label}\n"
                f"Задача: {title}\n\n"
                f"Комментарий CTO: {cto_comment}"
            )
            print(report)
            send_telegram_report(report)
            return

    # Выполняем
    try:
        report = await run_squad_task(squad_key, title)
    except Exception as e:
        print(f"[{squad_key}] run_squad_task упал с исключением: {e}")
        update_task_status(task_id, "rejected", f"Упало с необработанным исключением: {e}")
        error_report = f"❌ ИНИЦИАТИВА ОТРЯДА УПАЛА С ОШИБКОЙ\n\nОтряд: {squad_label}\nЗадача: {title}\n\nОшибка: {e}"
        print(error_report)
        send_telegram_report(error_report)
        return

    update_task_status(task_id, "done")

    full_report = (
        f"🏁 ИНИЦИАТИВА ОТРЯДА\n\n"
        f"Отряд: {squad_label}\n"
        f"{'🔓 Взято самостоятельно (мелкое)' if minor else f'✅ Одобрено CTO: {cto_comment}'}\n\n"
        + report
    )
    brief = await compile_brief(full_report)
    print(f"\n[ПОЛНЫЙ ОТЧЁТ]\n{full_report}")
    print(f"\n[КОРОТКО В TELEGRAM]\n{brief}")
    send_telegram_report(brief)
    await curate_knowledge(f"Инициатива: {squad_label}", full_report)


async def run_all_squads_initiative(squad_keys: list[str] | None = None) -> None:
    """Все переданные отряды (по умолчанию — все из SQUADS) ищут и
    выполняют задачи параллельно — каждый на своей ветке, через свой
    CTO-approval, без дублирования (task board + is_duplicate)."""
    print("Синхронизация репозиториев...")
    print(clone_or_update_repos())

    keys = squad_keys if squad_keys else list(SQUADS.keys())
    await asyncio.gather(*(run_squad_initiative(key) for key in keys))


# Обратная совместимость со старым именем.
run_both_squads_initiative = run_all_squads_initiative


async def main():
    squad_key = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in SQUADS else None

    print("Синхронизация репозиториев...")
    print(clone_or_update_repos())

    if squad_key:
        await run_squad_initiative(squad_key)
    else:
        await run_both_squads_initiative()


if __name__ == "__main__":
    asyncio.run(main())
