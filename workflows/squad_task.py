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
