"""
Лаборатория — любые 2 (иногда 3) человека из ВСЕЙ компании (гении
совета директоров + код-ревью команда + COO/HR) сами берутся за
проблему и решают её вслух в паре.

Отличие от остальных режимов:
- Участники выбираются случайно из ПОЛНОГО ростера (не фиксированная
  команда под конкретную задачу).
- Тип проблемы выбирается сам: если у обоих/у кого-то из выбранных
  есть доступ к коду — можно взять реальную техническую проблему из
  bld-system/bld-panel; если нет — берётся абстрактная стратегическая/
  архитектурная проблема. Выбор делает сама пара (через открывающую
  реплику первого участника).
- Итоговый отчёт — не протокол дискуссии, а сравнение решений:
  что предложено, почему один вариант лучше другого, что можно
  добавить, стоит ли объединить два варианта в третий.
"""

import asyncio
import random
import sys

from agent_framework import Message

from agents.global_geniuses import GLOBAL_LABELS
from agents.growth_team import GROWTH_LABELS
from agents.specialists import SPECIALIST_LABELS
from agents.roster import CODE_ACCESS_ROLES, build_full_roster
from config.client_factory import get_chat_client
from config.models import BOARD_MODEL_ASSIGNMENTS
from tools.repo_tools import git_log, grep_repo, list_repo_files, read_file
from tools.telegram_report import send_telegram_report
from workflows._common import ask, curate_knowledge, run_free_conversation, sync_repos_or_alert

MAX_TURNS = 10  # раунды разговора в паре/тройке — короче группового заседания

ROLE_LABELS = {
    "mekhmat": "🔢 Мехмат", "fiztech": "⚙️  Физтех",
    "fizmat": "🎲 Физмат", "tehmat": "♟️  Техмат", "chief_scientist": "🔭 Chief Scientist",
    "cto": "🧑‍💼 CTO", "backend_senior": "⌨️  Backend",
    "product_frontend": "🎨 Product/Frontend", "qa_security": "🔒 QA/Security",
    "coo": "🗂️  COO", "hr": "🧑‍🤝‍🧑 HR", "vp_engineering": "📐 VP Engineering", "squad_lead_alpha": "🅰️  Squad Lead Alpha", "squad_lead_bravo": "🅱️  Squad Lead Bravo",
    **GLOBAL_LABELS,
    **SPECIALIST_LABELS,
    **GROWTH_LABELS,
}

OPENING_TOOLS = [list_repo_files, read_file, git_log, grep_repo]


def pick_group(roster: dict, size_hint: int | None = None) -> list[str]:
    """Выбирает 2 (с шансом 3) случайных участников из полного ростера."""
    size = size_hint or random.choices([2, 3], weights=[70, 30])[0]
    return random.sample(list(roster.keys()), k=min(size, len(roster)))


async def find_problem(group_names: list[str]) -> str:
    """Один из выбранной группы формулирует открывающую проблему — сам
    решает, взять что-то реальное из кода или абстрактную задачу,
    в зависимости от того, есть ли у группы доступ к коду."""

    has_code_access = any(name in CODE_ACCESS_ROLES for name in group_names)
    opener_role = group_names[0]

    client = get_chat_client(BOARD_MODEL_ASSIGNMENTS["agenda_setter"])
    tools = OPENING_TOOLS if has_code_access else None

    prompt = f"""
Ты сейчас в роли: {opener_role}. Ты начинаешь рабочую сессию с коллегой
(коллегами): {', '.join(n for n in group_names if n != opener_role)}.

{"У тебя есть доступ к реальному коду BLD System (bld-system, bld-panel) "
 "через tools (list_repo_files, read_file, git_log, grep_repo). Можешь "
 "либо покопаться в реальном коде и найти конкретную техническую "
 "проблему, требующую решения, либо взять абстрактную архитектурную/"
 "стратегическую проблему — выбор за тобой."
 if has_code_access else
 "У тебя нет доступа к коду — сформулируй абстрактную стратегическую "
 "или архитектурную проблему компании BLD System (мониторинг "
 "стройплощадок, единственный разработчик-основатель Валик, три "
 "параллельных проекта)."}

Сформулируй ОДНУ конкретную проблему, которую вы вдвоём (втроём)
сейчас решите. 2-4 предложения, разговорный тон — как будто ты реально
подошёл к коллеге и предложил вместе покопаться в этом.

ВАЖНО: вы разбираете код ТЕОРЕТИЧЕСКИ — смотрите, что не так, и
обсуждаете что делать словами. Никто не пишет код, патчи или диффы —
только текстовый разбор и рекомендации.
"""
    if tools:
        agent = client.as_agent(name="opener", instructions="Помогаешь сформулировать рабочую проблему.", tools=tools)
        response = await agent.run(prompt)
        return response.text.strip()
    return await ask(client, prompt)


async def compile_solution_report(group_names: list[str], problem: str, transcript: list[Message]) -> str:
    """Не протокол, а сравнение решений: что предложено, почему лучше,
    что добавить, стоит ли объединить варианты."""
    client = get_chat_client(BOARD_MODEL_ASSIGNMENTS["secretary"])

    lines = [f"Проблема: {problem}"]
    for m in transcript:
        label = ROLE_LABELS.get(m.author_name or "", m.author_name or "?")
        lines.append(f"{label}: {m.text.strip()}")
    conv = "\n\n".join(lines)

    prompt = f"""
Вот рабочая сессия двух-трёх специалистов, решавших конкретную проблему:

{conv}

Составь отчёт для Валика (без markdown-звёздочек, простой текст для
Telegram) строго в таком формате:

🔬 ЛАБОРАТОРИЯ: {', '.join(ROLE_LABELS.get(n, n) for n in group_names)}

ПРОБЛЕМА:
[одна-две строки]

ПРЕДЛОЖЕННЫЕ РЕШЕНИЯ:
[если было больше одного варианта — опиши каждый кратко с указанием,
чьё это решение. Если пришли к одному решению совместно — так и напиши]

ПОЧЕМУ ЛУЧШЕ:
[аргументация — почему рекомендуемое решение лучше альтернативы(-тив),
конкретно, без воды]

МОЖНО ДОБАВИТЬ / ОБЪЕДИНИТЬ:
[если есть смысл усилить решение деталью от другого варианта, или
объединить два предложения в одно — напиши как именно. Если нет —
честно напиши "объединять нечего, решение самодостаточно"]

РЕКОМЕНДАЦИЯ:
[итоговое конкретное решение, 1-3 предложения]

Пиши по-русски, конкретно, без воды. НЕ включай фрагменты кода, патчи
или диффы — только текстовые аргументы и рекомендации, Валик сам решит
как это реализовать. Общий объём — не больше 900 символов.
"""
    return await ask(client, prompt)


async def main():
    repo_hint = sys.argv[1] if len(sys.argv) > 1 else None
    if repo_hint:
        print("Синхронизация репозиториев (запрошен доступ к коду)...")
        if not await sync_repos_or_alert():
            return

    roster = build_full_roster()
    group_names = pick_group(roster)
    print(f"Группа: {', '.join(group_names)}")

    # Если в группу попал кто-то с доступом к коду — на всякий случай
    # синхронизируем репозитории (могут понадобиться tools).
    if any(n in CODE_ACCESS_ROLES for n in group_names) and not repo_hint:
        print("Синхронизация репозиториев...")
        if not await sync_repos_or_alert():
            return

    problem = await find_problem(group_names)
    print(f"\nПроблема:\n{problem}\n{'=' * 60}")

    participants = [roster[n] for n in group_names]
    transcript = await run_free_conversation(participants, problem, max_turns=MAX_TURNS)

    for msg in transcript:
        label = ROLE_LABELS.get(msg.author_name or "", msg.author_name or "?")
        print(f"\n{label}: {msg.text}")

    print(f"\n{'=' * 60}\nСоставляем отчёт...")
    report = await compile_solution_report(group_names, problem, transcript)

    print(f"\n{'=' * 60}\n{report}")
    send_telegram_report(report)

    await curate_knowledge("Лаборатория", report)


if __name__ == "__main__":
    asyncio.run(main())
