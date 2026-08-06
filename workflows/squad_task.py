"""
Инженерные отряды работают ПАРАЛЛЕЛЬНО над РАЗНЫМИ задачами.

Автономный цикл (workflows/squad_autonomous.py дальше по коду):
1. Отряд сканирует свою зону, учитывая общую доску задач (не дублирует
   то, что уже в работе/сделано другим отрядом).
2. Составляет ПРЕДЛОЖЕНИЕ (что/почему/как) — не сразу пишет код.
3. Если задача рискованная (миграции, breaking changes) — реальное
   одобрение CTO обязательно. Если нет — отряд решает сам.
4. Выполняет, обновляет доску задач.
"""

import asyncio

from agents.engineering import build_specialist_pool
from agents.squads import SQUADS
from config.client_factory import get_chat_client
from config.models import BOARD_MODEL_ASSIGNMENTS
from tools.repo_tools import git_log, grep_repo
from workflows._common import record_participation, safe_agent_run
from workflows.engineering_task import run_engineering_task
from workflows.task_board import record_task_participants

RISK_KEYWORDS = [
    "миграц", "удалить", "удаление", "breaking", "переписать полностью",
    "критичн", "необратим", "схему бд", "схема бд", "production",
    "прод базу", "изменить api", "сломает", "несовместим",
]


def needs_approval(proposal_text: str) -> bool:
    """Низкий риск — отряд решает сам. Высокий риск (миграции, breaking
    changes, необратимые изменения) — нужно реальное одобрение CTO."""
    lowered = proposal_text.lower()
    return any(kw in lowered for kw in RISK_KEYWORDS)


async def find_squad_problem(squad_key: str, recent_context: str = "") -> str:
    """Лид отряда сам сканирует код в своей зоне (domain_keywords) и
    формулирует конкретную задачу. Учитывает доску задач, чтобы не
    предлагать то, что уже в работе или недавно сделано."""
    squad = SQUADS[squad_key]
    domain_hint = ", ".join(squad["domain_keywords"][:6])

    client = get_chat_client(BOARD_MODEL_ASSIGNMENTS.get("agenda_setter", "gpt-5.2"))
    scout_agent = client.as_agent(
        name=f"{squad_key}_scout",
        instructions=f"Ищешь конкретную техническую проблему в зоне ответственности {squad['label']}.",
        tools=[git_log, grep_repo],
    )

    board_note = (
        f"\nУже в работе/недавно сделано (не предлагай то же самое, если "
        f"это ещё актуально):\n{recent_context}\n" if recent_context else ""
    )

    prompt = f"""
Ты ищешь задачу для {squad['label']} — зона ответственности этой
команды: {domain_hint}.
{board_note}
Посмотри git_log и grep_repo по репозиториям bld-system/bld-panel и
найди ОДНУ конкретную проблему или улучшение именно в этой зоне
ответственности — новую, не дублирующую то, что уже в работе.
Сформулируй как одну конкретную задачу, 1-2 предложения, без преамбулы.
"""
    response = await scout_agent.run(prompt)
    return response.text.strip()


async def draft_proposal(squad_key: str, task: str) -> str:
    """Отряд формулирует предложение (что/почему/как) ДО того, как
    начинает писать код — шаг 'подходят к CTO'."""
    squad = SQUADS[squad_key]
    lead = squad["lead_builder"]()
    prompt = f"""
Ты нашёл задачу в зоне ответственности своего отряда: {task}

Прежде чем начать реализацию, составь короткое предложение: ЧТО не
так, ПОЧЕМУ стоит чинить именно сейчас, и КАК именно планируешь
исправить (план в 2-4 пункта). Не пиши код — только план. 5-8
предложений, по делу.
"""
    response = await lead.run(prompt)
    return response.text.strip()


async def seek_approval(proposal_text: str, squad_label: str) -> tuple[bool, str]:
    """CTO реально решает, одобрить или нет — не декоративная роль."""
    from agents.team import build_team

    cto = build_team()["cto"]
    prompt = f"""
{squad_label} нашёл задачу, которую относит к рискованным (миграция/
breaking change/необратимое изменение), и просит твоего одобрения
прежде чем начинать. Вот их предложение:

{proposal_text}

Оцени: стоит ли им браться за это именно сейчас, реалистичен ли план,
нет ли более безопасного пути. Заверши явным вердиктом ПЕРВЫМ СЛОВОМ:
ОДОБРЕНО или ОТКЛОНЕНО — затем 2-3 предложения обоснования.
"""
    response = await cto.run(prompt)
    text = response.text.strip()
    approved = text.upper().startswith("ОДОБРЕНО")
    return approved, text


async def run_squad_task(squad_key: str, task: str | None = None, task_id: str | None = None) -> str:
    """Прогоняет одну задачу через один отряд — переиспользует
    run_engineering_task с лидом и пулом этого отряда.

    task_id — опционально: если передан (вызывающий код уже завёл
    запись на доске задач через workflows.task_board.add_task), сюда же
    прикрепляются фактические участники через record_task_participants
    — используется потом в get_specialist_stats()/hr_rotation_review.py.
    Без task_id функция работает ровно как раньше."""
    squad = SQUADS[squad_key]

    if not task:
        print(f"[{squad_key}] Задача не передана — лид сам ищет проблему в своей зоне...")
        task = await find_squad_problem(squad_key)
        print(f"[{squad_key}] Найдена задача: {task}")

    lead = squad["lead_builder"]()
    full_pool = build_specialist_pool()
    squad_pool = {name: full_pool[name] for name in squad["member_names"] if name in full_pool}

    if task_id:
        record_task_participants(task_id, [lead.name, *squad_pool.keys()])

    # squad_initiative.yml: timeout-minutes: 25 (1500с). Отряды тоже
    # идут параллельно через asyncio.gather (см. run_squad_initiative в
    # squad_initiative.py и dispatch_squads() выше в этом файле) — не
    # делим бюджет на N отрядов.
    report = await run_engineering_task(
        task,
        lead_agent=lead,
        lead_label=f"Squad Lead ({squad['label']})",
        helper_pool=squad_pool,
        force_consult=True,
        soft_timeout_seconds=1200,
    )
    record_participation(lead.name, *squad_pool.keys())
    return f"{squad['label']}\n\n{report}"


# Раньше здесь был run_squad_autonomous_cycle() — полный автономный
# цикл отряда, дублирующий workflows/squad_initiative.py:
# run_squad_initiative(). Он нигде не вызывался (мёртвый код), а его
# load_task_board/save_task_board_entry были импортированы из
# workflows._common — модуля, где эти функции пишут ПРОСТОЙ СПИСОК в
# .state/task_board.json, тогда как реальная доска задач
# (workflows/task_board.py, которую читают company_pulse,
# individual_initiative, squad_initiative, big_projects,
# breakthrough_proposal, gtm_initiative, chevruta) хранит там СЛОВАРЬ
# {"tasks": [...], "last_updated": ...}. Если бы кто-то — включая саму
# инженерную команду при рефакторинге — когда-нибудь вызвал эту
# функцию, один запуск тихо переписал бы task_board.json в
# несовместимый формат и уронил бы ВСЕ остальные воркфлоу компании с
# `TypeError: list indices must be integers, not str` при следующем
# чтении доски. Удалено целиком, а не просто исправлен импорт — раз
# squad_initiative.py уже делает то же самое, но правильно (с dedup,
# различением мелких/крупных задач и консистентным трекингом доски),
# держать вторую, более слабую и потенциально опасную реализацию рядом
# не было смысла.


async def dispatch_squads(tasks_by_squad: dict[str, str | None]) -> list[str]:
    """Запускает оба (или сколько передано) отряда ПАРАЛЛЕЛЬНО.

    tasks_by_squad: {"alpha": "задача или None", "bravo": "задача или None"}
    Если для какого-то отряда task is None — он сам ищет себе задачу.
    """
    coros = [run_squad_task(squad_key, task) for squad_key, task in tasks_by_squad.items()]
    return await asyncio.gather(*coros)


def detect_relevant_squads(task: str) -> list[str]:
    """Возвращает ключи ВСЕХ департаментов (agents/squads.py::SQUADS),
    чья зона (domain_keywords) реально задета текстом задачи — порядок
    как в SQUADS (стабильный, не случайный, чтобы order у run_squad_relay
    был воспроизводим при повторном вызове с тем же текстом).

    РАНЬШЕ (task_spans_both_domains ниже) смотрела ТОЛЬКО на alpha/bravo
    — жёстко зашитую пару из эпохи, когда отрядов было всего 2. При 7
    департаментах это значило, что кросс-департаментная задача —
    например, Product + Anomaly & Trust Engine (как показать аномалию
    менеджеру в панели) — никогда не распознавалась как совместная:
    целиком уезжала в один департамент, вторая грань терялась, либо
    кто-то должен был вручную вызвать run_squad_relay() с правильным
    order. Теперь любое совпадение по любому департаменту учитывается
    автоматически — и для решения "нужна ли эстафета", и как готовый
    order для run_squad_relay().
    """
    lowered = task.lower()
    return [
        key for key, squad in SQUADS.items()
        if any(kw in lowered for kw in squad["domain_keywords"])
    ]


def task_spans_both_domains(task: str) -> bool:
    """Сохранено для обратной совместимости старых вызовов, ожидавших
    именно alpha+bravo — теперь тонкая обёртка над
    detect_relevant_squads(), а не отдельная реализация. Новый код
    должен звать detect_relevant_squads() напрямую — она даёт полный
    список причастных департаментов (может быть 0, 1, 2 или больше),
    а не просто да/нет по одной жёстко зашитой паре."""
    matched = detect_relevant_squads(task)
    return "alpha" in matched and "bravo" in matched


async def run_squad_relay(task: str, order: list[str] | None = None, task_id: str | None = None) -> str:
    """Все переданные в order отряды работают НАД ОДНОЙ задачей
    ПОСЛЕДОВАТЕЛЬНО на одной (своей, изолированной через git worktree)
    ветке — каждый берёт свою часть, следующий продолжает поверх
    предыдущего. order может быть любой длины (2+), не только пара
    alpha/bravo — см. detect_relevant_squads().

    Если order не передан явно, определяется автоматически через
    detect_relevant_squads(task) — на случай, если вызывающий код
    просто хочет "проведи эстафету по фактическим зонам этой задачи",
    не выясняя заранее, какие именно департаменты задеты.

    task_id — опционально: если передан (вызывающий код уже завёл
    запись на доске задач через workflows.task_board.add_task), сюда
    прикрепляются лиды-участники эстафеты через record_task_participants
    — используется потом в get_specialist_stats()/hr_rotation_review.py.
    Без task_id функция работает ровно как раньше.
    """
    from agents.review_gate import run_review_gate
    from tools.repo_tools import commit_and_push, create_branch, get_repo_write_lock, merge_branch_to_main
    from workflows.cto_approval import cto_approval
    from workflows.engineering_task import guess_repo, make_branch_name, needs_rework

    if not order:
        order = detect_relevant_squads(task)
    order = list(order)
    if len(order) < 2:
        # Вырожденный случай (детект не нашёл 2+ зоны, а вызывающий код
        # всё равно попросил эстафету) — не падаем, просто эстафета из
        # одного отряда фактически равносильна run_squad_task. Решение
        # "с кем" принадлежит вызывающему коду, не этой функции — она
        # не пытается сама дополнить order до валидной пары.
        print(f"[relay] Внимание: order содержит меньше 2 отрядов ({order}) — эстафета вырождается в один отряд.")

    relay_label = " → ".join(SQUADS[k]["label"] for k in order)

    repo_name = guess_repo(task)
    branch_name = make_branch_name(task, "ai-relay")

    print(f"[relay] Создаём изолированную ветку {branch_name} в {repo_name}...")
    print(create_branch(repo_name, branch_name))

    findings = []
    leads_by_squad = {}
    for squad_key in order:
        squad = SQUADS[squad_key]
        lead = squad["lead_builder"]()
        leads_by_squad[squad_key] = lead
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
        part_text = await safe_agent_run(lead, prompt, person_label=f"{squad['label']} (relay)")
        if part_text is None:
            findings.append(f"{squad['label']}: не ответил после нескольких попыток — эта часть работы не выполнена.")
            continue
        findings.append(f"{squad['label']}:\n{part_text}")

    engineering_summary = "\n\n".join(findings)
    record_participation(*(leads_by_squad[k].name for k in order))
    if task_id:
        record_task_participants(task_id, [leads_by_squad[k].name for k in order])

    print("[relay] Коммитим объединённое изменение...")
    push_result = commit_and_push(repo_name, branch_name, f"AI engineering (relay): {task[:60]}")
    print(push_result)

    print("[relay] Review Gate проверяет результат обеих команд разом...")
    review_verdict = await run_review_gate(task, repo_name, branch_name, engineering_summary)
    print(review_verdict)

    # Тот же принцип, что и в run_engineering_task: мерж автоматический
    # при чистом вердикте, иначе решение за CTO, не за основателем. У
    # эстафеты нет своего цикла переделки (два отряда уже последовательно
    # правили друг за другом) — поэтому при проблемах сразу к CTO, без
    # промежуточного rework-шага.
    if not needs_rework(review_verdict):
        print("[relay] Review Gate: вердикт чист — мержим в main автоматически...")
        async with get_repo_write_lock(repo_name):
            merge_result = merge_branch_to_main(repo_name, branch_name, task)
        print(merge_result)
        merge_note = f"\n\n{merge_result}"
    else:
        print("[relay] Review Gate: есть замечания — решение за CTO...")
        cto_approved, cto_comment = await cto_approval(
            squad_label=f"Эстафета {relay_label}",
            task_title=task,
            reason=f"Review Gate дал замечания по совместной работе:\n{review_verdict}",
            how="Оба отряда уже закончили свои части последовательно на одной ветке.",
        )
        if cto_approved:
            print(f"[relay] CTO решил мержить несмотря на замечания: {cto_comment}")
            async with get_repo_write_lock(repo_name):
                merge_result = merge_branch_to_main(repo_name, branch_name, f"{task} (approved by CTO despite review notes)")
            print(merge_result)
            merge_note = f"\n\n🧑‍💼 CTO решил смержить несмотря на замечания: {cto_comment}\n\n{merge_result}"
        else:
            print(f"[relay] CTO заблокировал мерж: {cto_comment}")
            merge_note = (
                f"\n\n🧑‍💼 CTO НЕ дал добро на мерж: {cto_comment}\n\n"
                f"⚠️ Изменения остаются в ветке {branch_name} — нужна ручная разборка."
            )

    return (
        f"🔗 СОВМЕСТНАЯ ЗАДАЧА — ЭСТАФЕТА ({relay_label})\n\n"
        f"ЗАДАЧА:\n{task}\n\n"
        f"РЕПОЗИТОРИЙ: {repo_name}\nВЕТКА: {branch_name}\n\n"
        + engineering_summary
        + f"\n\n{push_result}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nREVIEW GATE\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        + review_verdict
        + merge_note
    )
