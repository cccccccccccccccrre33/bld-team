"""
Индивидуальная инициатива — не только 2 фиксированных отряда. ЛЮБОЙ
человек компании с реальным доступом к коду (9 молодых глобальных
гениев, 4 специалиста, 3 роли роста — итого 16 человек) может сам
заметить проблему в СВОЕЙ специализации и предложить фикс.

Бюрократия масштабируется по уверенности, а не по должности:
- Уверен, что это чётко его специализация → берёт сам, без CTO.
- Сомневается или это не совсем его зона → идёт к CTO за approval,
  как и отряды (workflows/cto_approval.py).

Может привлечь ещё людей себе в помощь — это уже встроено в
run_engineering_task (helper_pool по умолчанию = весь общий пул).
"""

import asyncio
import random
import sys

from agents.architecture_council import ARCHITECT_BUILDERS, ARCHITECT_LABELS
from agents.expansion_geniuses import GENIUS_BUILDERS as EXPANSION_BUILDERS, GLOBAL_LABELS as EXPANSION_LABELS
from agents.global_geniuses import GENIUS_BUILDERS, GLOBAL_LABELS
from agents.growth_team import GROWTH_BUILDERS, GROWTH_LABELS
from agents.specialists import SPECIALIST_BUILDERS, SPECIALIST_LABELS
from tools.repo_tools import clone_or_update_repos, git_log, grep_repo
from tools.telegram_report import send_telegram_report
from workflows._common import compile_brief, curate_knowledge
from workflows.cto_approval import cto_approval
from workflows.engineering_task import run_engineering_task
from workflows.task_board import add_task, can_take_more, get_board_summary, is_duplicate, update_task_status

ALL_BUILDERS = {**GENIUS_BUILDERS, **SPECIALIST_BUILDERS, **GROWTH_BUILDERS, **EXPANSION_BUILDERS, **ARCHITECT_BUILDERS}
ALL_LABELS = {**GLOBAL_LABELS, **SPECIALIST_LABELS, **GROWTH_LABELS, **EXPANSION_LABELS, **ARCHITECT_LABELS}


async def scout_and_propose(name: str) -> dict | None:
    """Человек сканирует код в СВОЕЙ специализации (read-only) и сам
    оценивает, уверен ли он взять это на себя, или стоит спросить CTO."""
    if not can_take_more():
        print(f"[{name}] Лимит параллельных задач исчерпан")
        return None

    board_summary = get_board_summary()
    person = ALL_BUILDERS[name](can_write=False)

    prompt = f"""
Доска активных задач компании (не дублируй то, что уже в работе):
{board_summary}

Загляни в реальный код (git_log, grep_repo по bld-system и bld-panel)
и найди ОДНУ конкретную проблему именно в твоей специализации — не
общую, а такую, в которой ты реально эксперт.

Если ничего реального не нашёл — ответь строго: НЕТ ЗАДАЧИ

Если нашёл — ответь СТРОГО в этом формате:
ЗАДАЧА: [одна строка]
ПОЧЕМУ: [2-3 предложения, по существу]
КАК: [2-3 предложения, конкретный план]
УВЕРЕННОСТЬ: УВЕРЕН или СПРОСИТЬ CTO

УВЕРЕН — если это чётко твоя специализация и ты готов взять полную
ответственность сам, без чужого одобрения. СПРОСИТЬ CTO — если
сомневаешься, или задача выходит за границы твоей конкретной
экспертизы, или может затронуть что-то более широкое.
"""
    response = await person.run(prompt)
    text = response.text.strip()

    if "НЕТ ЗАДАЧИ" in text.upper() or len(text) < 30:
        return None

    result = {"name": name}
    for line in text.split("\n"):
        up = line.upper()
        if up.startswith("ЗАДАЧА:"):
            result["title"] = line.split(":", 1)[-1].strip()
        elif up.startswith("ПОЧЕМУ:"):
            result["reason"] = line.split(":", 1)[-1].strip()
        elif up.startswith("КАК:"):
            result["how"] = line.split(":", 1)[-1].strip()
        elif up.startswith("УВЕРЕННОСТЬ:"):
            result["confident"] = "УВЕРЕН" in up and "СПРОСИТЬ" not in up

    if not result.get("title"):
        return None
    if is_duplicate(result["title"]):
        print(f"[{name}] Дубль на доске — пропускаем: {result['title']}")
        return None
    return result


async def run_individual_initiative(name: str | None = None) -> None:
    name = name or random.choice(list(ALL_BUILDERS.keys()))
    label = ALL_LABELS.get(name, name)

    print(f"\n{'=' * 60}\nИНДИВИДУАЛЬНАЯ ИНИЦИАТИВА: {label}\n{'=' * 60}")

    proposal = await scout_and_propose(name)
    if not proposal:
        print(f"[{name}] Нечего предложить — пропускаем")
        return

    title = proposal["title"]
    reason = proposal.get("reason", "")
    how = proposal.get("how", "")
    confident = proposal.get("confident", False)

    print(f"[{name}] Proposal: {title} (уверенность: {'сам' if confident else 'спросить CTO'})")

    if confident:
        task_id = add_task(title, name, status="self_approved", reason=reason, how=how)
        update_task_status(task_id, "in_progress")
        verdict_note = f"🔓 {label} взял(а) сам(а) — уверен(а), что это его/её специализация"
    else:
        task_id = add_task(title, name, status="proposed", reason=reason, how=how)
        print(f"[{name}] Не уверен(а) — спрашивает CTO...")
        approved, cto_comment = await cto_approval(label, title, reason, how)

        if not approved:
            update_task_status(task_id, "rejected", cto_comment)
            report = (
                f"❌ CTO ОТКЛОНИЛ ИНИЦИАТИВУ\n\n"
                f"{label}\nЗадача: {title}\n\nКомментарий CTO: {cto_comment}"
            )
            print(report)
            send_telegram_report(report)
            return

        update_task_status(task_id, "in_progress", cto_comment)
        verdict_note = f"✅ Одобрено CTO: {cto_comment}"

    # Реализация — сам инициатор становится "лидом" этой задачи (со
    # своим полным write-доступом), может привлечь помощь из общего
    # пула специалистов через ту же машинерию, что и отряды.
    writer = ALL_BUILDERS[name](can_write=True)
    report = await run_engineering_task(title, lead_agent=writer, lead_label=label)
    update_task_status(task_id, "done")

    full_report = f"🏁 ИНДИВИДУАЛЬНАЯ ИНИЦИАТИВА\n\n{label}\n{verdict_note}\n\n{report}"
    brief = await compile_brief(full_report)
    print(f"\n{brief}")
    send_telegram_report(brief)
    await curate_knowledge(f"Инициатива: {label}", full_report)


async def main():
    name = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in ALL_BUILDERS else None

    print("Синхронизация репозиториев...")
    print(clone_or_update_repos())

    await run_individual_initiative(name)


if __name__ == "__main__":
    asyncio.run(main())
