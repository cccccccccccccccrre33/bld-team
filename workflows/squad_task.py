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
from datetime import datetime

from agents.engineering import build_specialist_pool
from agents.squads import SQUADS
from config.client_factory import get_chat_client
from config.models import BOARD_MODEL_ASSIGNMENTS
from tools.repo_tools import git_log, grep_repo
from workflows._common import load_task_board, save_task_board_entry
from workflows.engineering_task import run_engineering_task

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


async def run_squad_task(squad_key: str, task: str | None = None) -> str:
    """Прогоняет одну задачу через один отряд — переиспользует
    run_engineering_task с лидом и пулом этого отряда."""
    squad = SQUADS[squad_key]

    if not task:
        print(f"[{squad_key}] Задача не передана — лид сам ищет проблему в своей зоне...")
        task = await find_squad_problem(squad_key)
        print(f"[{squad_key}] Найдена задача: {task}")

    lead = squad["lead_builder"]()
    full_pool = build_specialist_pool()
    squad_pool = {name: full_pool[name] for name in squad["member_names"] if name in full_pool}

    report = await run_engineering_task(
        task,
        lead_agent=lead,
        lead_label=f"Squad Lead ({squad['label']})",
        helper_pool=squad_pool,
    )
    return f"{squad['label']}\n\n{report}"


async def run_squad_autonomous_cycle(squad_key: str) -> str:
    """Полный автономный цикл отряда: сканирует зону (учитывая доску
    задач), составляет предложение, при необходимости проходит
    одобрение CTO, выполняет, обновляет доску задач."""
    squad = SQUADS[squad_key]
    label = squad["label"]

    board = load_task_board()
    recent_context = (
        "\n".join(f"- [{e.get('status')}] {e.get('squad')}: {e.get('task')}" for e in board)
        or "(доска пока пуста)"
    )

    task = await find_squad_problem(squad_key, recent_context=recent_context)
    proposal = await draft_proposal(squad_key, task)

    if needs_approval(proposal):
        print(f"[{squad_key}] Задача рискованная — запрашиваем одобрение CTO...")
        approved, verdict = await seek_approval(proposal, label)
        approval_block = f"🧑‍💼 CTO:\n{verdict}\n\n"

        if not approved:
            save_task_board_entry({"squad": squad_key, "task": task, "status": "rejected"})
            return (
                f"{label}\n\n📋 ПРЕДЛОЖЕНИЕ (требовало одобрения):\n{task}\n\n{proposal}\n\n"
                f"{approval_block}❌ CTO отклонил — работа не начата."
            )
        header = f"{label}\n\n📋 ПРЕДЛОЖЕНИЕ (одобрено CTO):\n{task}\n\n{proposal}\n\n{approval_block}✅ Приступаем.\n\n"
    else:
        header = (
            f"{label}\n\n📋 РЕШЕНИЕ ОТРЯДА (низкий риск — не требует одобрения):\n"
            f"{task}\n\n{proposal}\n\n"
        )

    save_task_board_entry({"squad": squad_key, "task": task, "status": "in_progress"})
    engineering_report = await run_squad_task(squad_key, task)
    save_task_board_entry({"squad": squad_key, "task": task, "status": "done"})

    return header + engineering_report


async def dispatch_squads(tasks_by_squad: dict[str, str | None]) -> list[str]:
    """Запускает оба (или сколько передано) отряда ПАРАЛЛЕЛЬНО.

    tasks_by_squad: {"alpha": "задача или None", "bravo": "задача или None"}
    Если для какого-то отряда task is None — он сам ищет себе задачу.
    """
    coros = [run_squad_task(squad_key, task) for squad_key, task in tasks_by_squad.items()]
    return await asyncio.gather(*coros)


def task_spans_both_domains(task: str) -> bool:
    """True, если задача реально задевает зоны ОБОИХ отрядов — тогда
    их лучше не пускать параллельно на разные ветки (риск рассинхрона),
    а провести эстафету на одной ветке."""
    lowered = task.lower()
    alpha_hit = any(kw in lowered for kw in SQUADS["alpha"]["domain_keywords"])
    bravo_hit = any(kw in lowered for kw in SQUADS["bravo"]["domain_keywords"])
    return alpha_hit and bravo_hit


async def run_squad_relay(task: str, order: list[str] = ("alpha", "bravo")) -> str:
    """Оба отряда работают НАД ОДНОЙ задачей ПОСЛЕДОВАТЕЛЬНО на одной
    ветке — каждый берёт свою часть, второй продолжает поверх первого.
    """
    from agents.review_gate import run_review_gate
    from tools.repo_tools import commit_and_push, create_branch, merge_branch_to_main
    from tools.repo_tools import AI_BRANCH_NAME
    from workflows.cto_approval import cto_approval
    from workflows.engineering_task import guess_repo, needs_rework

    repo_name = guess_repo(task)
    branch_name = AI_BRANCH_NAME

    print(f"[relay] Переключаемся на общую ветку {branch_name} в {repo_name}...")
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

    # Тот же принцип, что и в run_engineering_task: мерж автоматический
    # при чистом вердикте, иначе решение за CTO, не за основателем. У
    # эстафеты нет своего цикла переделки (два отряда уже последовательно
    # правили друг за другом) — поэтому при проблемах сразу к CTO, без
    # промежуточного rework-шага.
    if not needs_rework(review_verdict):
        print("[relay] Review Gate: вердикт чист — мержим в main автоматически...")
        merge_result = merge_branch_to_main(repo_name, branch_name, task)
        print(merge_result)
        merge_note = f"\n\n{merge_result}"
    else:
        print("[relay] Review Gate: есть замечания — решение за CTO...")
        cto_approved, cto_comment = await cto_approval(
            squad_label=f"Эстафета {SQUADS['alpha']['label']} → {SQUADS['bravo']['label']}",
            task_title=task,
            reason=f"Review Gate дал замечания по совместной работе:\n{review_verdict}",
            how="Оба отряда уже закончили свои части последовательно на одной ветке.",
        )
        if cto_approved:
            print(f"[relay] CTO решил мержить несмотря на замечания: {cto_comment}")
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
        f"🔗 СОВМЕСТНАЯ ЗАДАЧА — ЭСТАФЕТА ({SQUADS['alpha']['label']} → {SQUADS['bravo']['label']})\n\n"
        f"ЗАДАЧА:\n{task}\n\n"
        f"РЕПОЗИТОРИЙ: {repo_name}\nВЕТКА: {branch_name}\n\n"
        + engineering_summary
        + f"\n\n{push_result}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nREVIEW GATE\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        + review_verdict
        + merge_note
    )
