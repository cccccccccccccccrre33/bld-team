"""
Инженерные отряды работают ПАРАЛЛЕЛЬНО над РАЗНЫМИ задачами — это и
задействует специалистов, которые раньше почти не участвовали в
реальной работе с кодом, и увеличивает пропускную способность вдвое.

Если для отряда явно передана задача — он берётся за неё. Если нет —
лид отряда сам сканирует код в своей зоне ответственности (domain_keywords)
и находит проблему сам, как и агент-скаут в других режимах.
"""

import asyncio

from agents.engineering import build_specialist_pool
from agents.squads import SQUADS
from tools.repo_tools import git_log, grep_repo
from workflows._common import ask
from workflows.engineering_task import run_engineering_task

# Модель для самостоятельного поиска проблемы, если отряду не дали
# явную задачу — используем ту же лёгкую модель, что и agenda_setter
# совета директоров (agenda_setter реально копается в коде).
from config.models import BOARD_MODEL_ASSIGNMENTS
from config.client_factory import get_chat_client


async def find_squad_problem(squad_key: str) -> str:
    """Лид отряда сам сканирует код в своей зоне (domain_keywords) и
    формулирует конкретную задачу — используется, когда отряду не
    передали явную задачу извне."""
    squad = SQUADS[squad_key]
    domain_hint = ", ".join(squad["domain_keywords"][:6])

    client = get_chat_client(BOARD_MODEL_ASSIGNMENTS.get("agenda_setter", "gpt-5.2"))
    scout_agent = client.as_agent(
        name=f"{squad_key}_scout",
        instructions=f"Ищешь конкретную техническую проблему в зоне ответственности {squad['label']}.",
        tools=[git_log, grep_repo],
    )

    prompt = f"""
Ты ищешь задачу для {squad['label']} — зона ответственности этой
команды: {domain_hint}.

Посмотри git_log и grep_repo по репозиториям bld-system/bld-panel и
найди ОДНУ конкретную проблему или улучшение именно в этой зоне
ответственности. Сформулируй как одну конкретную задачу, 1-2
предложения, без преамбулы.
"""
    response = await scout_agent.run(prompt)
    return response.text.strip()


async def run_squad_task(squad_key: str, task: str | None = None) -> str:
    """Прогоняет одну задачу через один отряд — переиспользует
    run_engineering_task с лидом и пулом этого отряда."""
    squad = SQUADS[squad_key]

    if not task:
        print(f"[{squad_key}] Задача не передана — лид сам ищет проблему в своей зоне...")
        task = await find_squad_problem(squad_key)
        print(f"[{squad_key}] Найдена задача: {task}")

    lead = squad["lead_builder"]()

    # Пул отряда — только его штатные участники (не весь пул из 13).
    full_pool = build_specialist_pool()
    squad_pool = {name: full_pool[name] for name in squad["member_names"] if name in full_pool}

    report = await run_engineering_task(
        task,
        lead_agent=lead,
        lead_label=f"Squad Lead ({squad['label']})",
        helper_pool=squad_pool,
        branch_prefix=f"ai-eng-{squad_key}",
    )
    return f"{squad['label']}\n\n{report}"


async def dispatch_squads(tasks_by_squad: dict[str, str | None]) -> list[str]:
    """Запускает оба (или сколько передано) отряда ПАРАЛЛЕЛЬНО.

    tasks_by_squad: {"alpha": "задача или None", "bravo": "задача или None"}
    Если для какого-то отряда task is None — он сам ищет себе задачу
    в своей зоне ответственности (см. find_squad_problem).
    """
    coros = [run_squad_task(squad_key, task) for squad_key, task in tasks_by_squad.items()]
    return await asyncio.gather(*coros)


def task_spans_both_domains(task: str) -> bool:
    """True, если задача реально задевает зоны ОБОИХ отрядов (например
    'надёжность БД под нагрузкой') — в этом случае их лучше не пускать
    параллельно на разные ветки (риск рассинхрона), а провести эстафету
    на одной ветке."""
    lowered = task.lower()
    alpha_hit = any(kw in lowered for kw in SQUADS["alpha"]["domain_keywords"])
    bravo_hit = any(kw in lowered for kw in SQUADS["bravo"]["domain_keywords"])
    return alpha_hit and bravo_hit


async def run_squad_relay(task: str, order: list[str] = ("alpha", "bravo")) -> str:
    """Оба отряда работают НАД ОДНОЙ задачей ПОСЛЕДОВАТЕЛЬНО на одной
    ветке — каждый берёт свою часть, второй продолжает поверх первого.
    Никакого риска рассинхрона: одна ветка, чёткая передача эстафеты,
    единый Review Gate в конце.
    """
    from datetime import datetime

    from agents.review_gate import run_review_gate
    from tools.repo_tools import commit_and_push, create_branch
    from workflows.engineering_task import guess_repo, slugify

    repo_name = guess_repo(task)
    branch_name = f"ai-eng-relay/{slugify(task)}-{datetime.now().strftime('%Y%m%d-%H%M')}"

    print(f"[relay] Создаём общую ветку {branch_name} в {repo_name}...")
    print(create_branch(repo_name, branch_name))

    findings = []
    for squad_key in order:
        squad = SQUADS[squad_key]
        lead = squad["lead_builder"]()
        prev_summary = "\n\n".join(findings) if findings else "(это первая часть работы — ты начинаешь)"

        prompt = f"""
Общая задача (вы работаете последовательно с другим отрядом на одной
ветке): {task}

Репозиторий: {repo_name}, ветка {branch_name} (текущая).

Что уже сделано другим отрядом до тебя:
{prev_summary}

Реализуй ИМЕННО свою часть — ту, что в зоне ответственности твоего
отряда — через write_file, опираясь на уже сделанное. Не переделывай
чужую часть, дополняй её. В конце — короткое резюме, что сделал.
"""
        print(f"[relay] {squad['label']} берётся за свою часть...")
        response = await lead.run(prompt)
        findings.append(f"{squad['label']}:\n{response.text.strip()}")

    engineering_summary = "\n\n".join(findings)

    print("[relay] Коммитим объединённое изменение...")
    push_result = commit_and_push(repo_name, branch_name, f"AI engineering (relay): {task[:60]}")
    print(push_result)

    print("[relay] Review Gate проверяет результат обеих команд разом...")
    review_verdict = await run_review_gate(task, repo_name, branch_name, engineering_summary)
    print(review_verdict)

    return (
        f"🔗 СОВМЕСТНАЯ ЗАДАЧА — ЭСТАФЕТА ({SQUADS['alpha']['label']} → {SQUADS['bravo']['label']})\n\n"
        f"ЗАДАЧА:\n{task}\n\n"
        f"РЕПОЗИТОРИЙ: {repo_name}\nВЕТКА: {branch_name}\n\n"
        + engineering_summary
        + f"\n\n{push_result}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nREVIEW GATE\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        + review_verdict
        + "\n\n⚠️ Изменения НЕ в main — открой ветку, проверь и смержи сам."
    )
