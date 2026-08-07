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

from agents.architecture_council import ARCHITECT_LABELS
from agents.global_geniuses import GLOBAL_LABELS
from agents.growth_team import GROWTH_LABELS
from agents.specialists import SPECIALIST_LABELS
from agents.roster import CODE_ACCESS_ROLES, build_full_roster
from config.client_factory import get_chat_client
from config.models import BOARD_MODEL_ASSIGNMENTS
from tools.repo_tools import git_log, grep_repo, list_repo_files, read_file
from workflows._common import ask, curate_knowledge, extract_next_step, fair_sample, looks_like_meta_complaint, notify_done, notify_failed, record_participation, run_free_conversation, safe_agent_run, sync_repos_or_alert
from workflows.cto_approval import cto_approval
from workflows.research_backlog import add_entry, format_entry_for_prompt, get_revisit_candidate, mark_revisited

MAX_TURNS = 10  # раунды разговора в паре/тройке — короче группового заседания

# Раньше идея, которая не привела прямо сейчас к коду (либо группа без
# доступа к коду обсуждала абстрактную проблему, либо CTO/секретарь не
# сочли задачу готовой), просто терялась — уходила в Telegram и одной
# строкой в вики, без малейшего способа "вернуться к этому через
# неделю". Теперь такие случаи сохраняются в research backlog (см.
# workflows/research_backlog.py), а НОВЫЕ сессии Лаборатории с шансом
# REVISIT_CHANCE (если есть подходящая "залежавшаяся" тема старше
# REVISIT_MIN_DAYS дней) сами возвращаются к ней, вместо того чтобы
# всегда придумывать проблему с нуля.
REVISIT_CHANCE = 0.5
REVISIT_MIN_DAYS = 5

ROLE_LABELS = {
    "mekhmat": "🔢 Мехмат", "fiztech": "⚙️  Физтех",
    "fizmat": "🎲 Физмат", "tehmat": "♟️  Техмат", "chief_scientist": "🔭 Chief Scientist", "ceo": "👑 CEO",
    "cto": "🧑‍💼 CTO", "backend_senior": "⌨️  Backend",
    "product_frontend": "🎨 Product/Frontend", "qa_security": "🔒 QA/Security",
    "coo": "🗂️  COO", "hr": "🧑‍🤝‍🧑 HR", "vp_engineering": "📐 VP Engineering", "squad_lead_alpha": "🅰️  Squad Lead Alpha", "squad_lead_bravo": "🅱️  Squad Lead Bravo", "squad_lead_platform": "🅿️  Squad Lead Platform", "squad_lead_product": "🎨 Squad Lead Product", "gtm_lead": "📈 GTM Lead",
    **GLOBAL_LABELS,
    **SPECIALIST_LABELS,
    **GROWTH_LABELS,
    **ARCHITECT_LABELS,
}

OPENING_TOOLS = [list_repo_files, read_file, git_log, grep_repo]


def pick_group(roster: dict, size_hint: int | None = None) -> list[str]:
    """Выбирает 2 (с шансом 3) случайных участников из полного ростера."""
    size = size_hint or random.choices([2, 3], weights=[70, 30])[0]
    return fair_sample(list(roster.keys()), k=min(size, len(roster)))


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
        text = await safe_agent_run(agent, prompt, person_label=f"{opener_role} (lab opener, with tools)")
        if text is not None:
            return text
        # Модель с tools временно недоступна — пробуем без tools как
        # запасной вариант, чем падать всю сессию из-за одной проблемы.
        print("Опенер с доступом к коду недоступен — пробуем без tools...")
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
    record_participation(*group_names)
    print(f"Группа: {', '.join(group_names)}")

    has_code_access = any(n in CODE_ACCESS_ROLES for n in group_names)

    # Если в группу попал кто-то с доступом к коду — на всякий случай
    # синхронизируем репозитории (могут понадобиться tools).
    if has_code_access and not repo_hint:
        print("Синхронизация репозиториев...")
        if not await sync_repos_or_alert():
            return

    backlog_candidate = None
    if random.random() < REVISIT_CHANCE:
        backlog_candidate = get_revisit_candidate(min_age_days=REVISIT_MIN_DAYS, origin="lab_session")

    if backlog_candidate:
        print(f"Возвращаемся к теме из research backlog: {backlog_candidate['topic']}")
        problem = (
            f"{format_entry_for_prompt(backlog_candidate)}\n\n"
            "Это тема, к которой компания решила вернуться спустя время, а не "
            "новая находка прямо сейчас — покопайтесь глубже, посмотрите, "
            "изменилось ли что-то с прошлого раза, и постарайтесь довести "
            "мысль дальше, чем получилось в прошлый заход."
        )
    else:
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
    # РАНЬШЕ уходило в Telegram — убрано: сравнение вариантов, не
    # готовая работа. Полный текст в вики через curate_knowledge ниже.

    await curate_knowledge("Лаборатория", report)

    # Раньше на этом всё заканчивалось — отчёт уходил в Telegram, и
    # даже если пара пришла к конкретной рекомендации, реализация не
    # запускалась НИКЕМ. Теперь: если у группы был доступ к коду и
    # рекомендация конкретна — это уходит на решение CTO (без участия
    # основателя), и при одобрении реализуется реальной инженерной
    # командой, как и любая другая задача в компании.
    def _stash_or_touch_backlog(reason_note: str) -> None:
        """Если сессия началась с возврата к backlog-теме — просто
        обновляет её (не создаёт дубль). Если началась с чистого
        листа — кладёт НОВУЮ запись, чтобы мысль не потерялась."""
        if backlog_candidate:
            mark_revisited(backlog_candidate["id"], note=reason_note)
        else:
            entry_id = add_entry(topic=problem[:200], summary=f"{report[:500]}\n{reason_note}",
                                  origin="lab_session", participants=group_names)
            print(f"Сохранено в research backlog для возврата позже: {entry_id}")

    if not has_code_access:
        _stash_or_touch_backlog("Абстрактная тема без доступа к коду — не эскалируется автоматически.")
        return

    secretary_client = get_chat_client(BOARD_MODEL_ASSIGNMENTS["secretary"])
    task = await extract_next_step(report, secretary_client)
    print(f"\nВозможная задача для реализации: {task}")

    if looks_like_meta_complaint(task):
        print("Похоже на неосмысленную задачу (жалоба модели на нехватку данных) — не эскалируем.")
        _stash_or_touch_backlog("Извлечённый 'следующий шаг' выглядел неосмысленным — не эскалирована, тема остаётся открытой.")
        return

    approved, comment = await cto_approval(
        squad_label=f"Лаборатория ({', '.join(group_names)})",
        task_title=task,
        reason="Родилось из рабочей сессии в паре/тройке — см. рекомендацию в отчёте выше.",
        how="См. полный отчёт выше — там сравнение вариантов и обоснование.",
    )
    verdict_msg = f"🧭 CTO по итогам Лаборатории: {'✅ ОДОБРЕНО' if approved else '❌ ОТКЛОНЕНО'} — {comment}"
    print(verdict_msg)
    if not approved:
        _stash_or_touch_backlog(f"CTO пока не одобрил ({comment[:200]}) — тема остаётся открытой для следующего захода.")
        return

    print("CTO одобрил — запускаем реализацию...")
    from workflows.engineering_task import run_engineering_task

    try:
        # lab_session.yml: timeout-minutes: 15 (900с), из которых сама
        # рабочая сессия в паре/тройке + CTO approval уже прошли до
        # этой точки. 500с оставляет запас на wrap-up.
        engineering_report = await run_engineering_task(task, soft_timeout_seconds=500)
    except Exception as e:
        print(f"[lab_session] run_engineering_task упал с исключением: {e}")
        notify_failed(f"Лаборатория ({', '.join(group_names)}): {task[:100]}", str(e))
        _stash_or_touch_backlog(f"Одобрено CTO, но реализация упала с ошибкой ({e}) — стоит вернуться.")
        return
    full = f"👷 РЕАЛИЗАЦИЯ ПО ИТОГАМ ЛАБОРАТОРИИ\n\n{engineering_report}"
    notify_done(task[:150])
    await curate_knowledge(f"Лаборатория → реализовано: {', '.join(group_names)}", f"{verdict_msg}\n\n{full}")
    if backlog_candidate:
        mark_revisited(backlog_candidate["id"], note="Доведено до реализации через Лабораторию.", close=True)


if __name__ == "__main__":
    asyncio.run(main())
