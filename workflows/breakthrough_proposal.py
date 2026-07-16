"""
Breakthrough Proposal — механизм для Engineering Fellows Core
(agents/engineering_fellows.py). В отличие от Individual Initiative
(мелкие точечные фиксы) — здесь Fellow предлагает КРУПНЫЙ архитектурный
прорыв: что-то, что меняет качество системы в целом (физически
осмысленные модели, формальная верификация критичного пайплайна,
структурный передел хранения данных и т.п.), а не патч.

Фильтр — тройной, не один CTO:
- Chief Scientist: научная обоснованность (та ли задача, не ли это
  теоретически несостоятельный подход).
- Chief Architect: архитектурная совместимость (не сломает ли
  существующую систему, реалистично ли встроить).
- CEO: финальное слово / стратегическая ценность (и снимает
  разногласия, если два первых не совпали).

Логика решения: если хотя бы двое из трёх одобряют — approved. Если
CEO явно отклоняет — это финальное вето независимо от остальных
(тот же принцип реального веса мнения, что и в Review Gate/иерархии
компании).

После одобрения Fellow собирает небольшую команду (2-3 человека из
общего пула специалистов/архитекторов/молодых) и реализует идею сам,
оставаясь техническим лидером, а не менеджером — использует ту же
машинерию run_engineering_task (единая ветка, Review Gate, переделка
по вето), что и остальная инженерная работа.
"""

import asyncio
import random

from agents.board import build_board
from agents.ceo import build_ceo
from agents.engineering_fellows import FELLOW_BUILDERS, FELLOW_LABELS
from tools.telegram_report import send_telegram_report
from workflows._common import compile_brief, curate_knowledge, fair_sample, record_participation, sync_repos_or_alert
from workflows.engineering_task import run_engineering_task
from workflows.task_board import add_task, get_board_summary, is_duplicate, update_task_status


async def scout_breakthrough(fellow_key: str) -> dict | None:
    """Fellow ищет КРУПНУЮ идею — не мелкий баг, а то, что реально
    меняет качество системы. Явно просим не мелочь."""
    fellow = FELLOW_BUILDERS[fellow_key](can_write=False)
    board_summary = get_board_summary()

    prompt = f"""
Текущая доска активных задач компании (не дублируй):
{board_summary}

Загляни в реальный код bld-system (ТОЛЬКО bld-system — bld-panel не
твоя зона, ты никогда не трогаешь фронтенд/панель) через свои tools и
предложи Breakthrough Proposal — КРУПНУЮ архитектурную идею в твоей
области, которая реально изменит качество системы (сделает её точнее,
устойчивее к шуму, обдуманнее перед результатом, архитектурно выше
"среднего софта"). НЕ мелкий точечный баг — это не твой уровень, для
мелочей есть другие механизмы.

Если сейчас реально нечего предложить такого масштаба — ответь строго:
НЕТ ПРОРЫВА

Если есть — ответь СТРОГО в формате:
ИДЕЯ: [одна строка — суть прорыва]
ОБОСНОВАНИЕ: [3-4 предложения — почему это меняет качество системы,
не просто "было бы неплохо"]
СЛОЖНОСТЬ: [оценка: небольшая/средняя/крупная — честно, не занижай]
ПЕРВЫЙ ШАГ: [конкретный первый шаг реализации]
"""
    response = await fellow.run(prompt)
    text = response.text.strip()

    if "НЕТ ПРОРЫВА" in text.upper() or len(text) < 40:
        return None

    result = {}
    for line in text.split("\n"):
        up = line.upper()
        if up.startswith("ИДЕЯ:"):
            result["idea"] = line.split(":", 1)[-1].strip()
        elif up.startswith("ОБОСНОВАНИЕ:"):
            result["reason"] = line.split(":", 1)[-1].strip()
        elif up.startswith("СЛОЖНОСТЬ:"):
            result["complexity"] = line.split(":", 1)[-1].strip()
        elif up.startswith("ПЕРВЫЙ ШАГ:"):
            result["first_step"] = line.split(":", 1)[-1].strip()

    return result if result.get("idea") else None


async def filter_proposal(fellow_label: str, proposal: dict) -> tuple[bool, str]:
    """Тройной фильтр: Chief Scientist + Chief Architect + CEO."""
    board = build_board()
    chief_scientist = board["chief_scientist"]
    chief_architect_pool = None
    from agents.review_gate import build_chief_architect
    chief_architect = build_chief_architect()
    ceo = build_ceo()

    prompt = f"""
{fellow_label} принёс Breakthrough Proposal:

Идея: {proposal['idea']}
Обоснование: {proposal.get('reason', '')}
Сложность: {proposal.get('complexity', '')}
Первый шаг: {proposal.get('first_step', '')}

Дай свою оценку СО СВОЕЙ КОЛОКОЛЬНИ. Ответь строго:
РЕШЕНИЕ: APPROVE или REJECT
КОММЕНТАРИЙ: [2-3 предложения]
"""
    scientist_resp = await chief_scientist.run(
        prompt + "\n\nОцени НАУЧНУЮ ОБОСНОВАННОСТЬ — та ли это задача, состоятелен ли подход теоретически."
    )
    architect_resp = await chief_architect.run(
        prompt + "\n\nОцени АРХИТЕКТУРНУЮ СОВМЕСТИМОСТЬ — не сломает ли систему, реалистично ли встроить."
    )
    ceo_resp = await ceo.run(
        prompt + "\n\nДай ФИНАЛЬНОЕ СЛОВО — стратегическая ценность. Если два предыдущих голоса "
        "разошлись, у тебя решающий голос. Если считаешь идею несвоевременной "
        "или несоразмерной ресурсам компании — прямо скажи REJECT, это твоё вето."
    )

    def parse(text: str) -> tuple[bool, str]:
        text = text.strip()
        approved = "РЕШЕНИЕ: APPROVE" in text.upper()
        comment = text
        for line in text.split("\n"):
            if line.upper().startswith("КОММЕНТАРИЙ:"):
                comment = line.split(":", 1)[-1].strip()
                break
        return approved, comment

    sci_ok, sci_comment = parse(scientist_resp.text)
    arch_ok, arch_comment = parse(architect_resp.text)
    ceo_ok, ceo_comment = parse(ceo_resp.text)

    combined = (
        f"🔭 Chief Scientist: {'✅' if sci_ok else '❌'} {sci_comment}\n"
        f"🏛️  Chief Architect: {'✅' if arch_ok else '❌'} {arch_comment}\n"
        f"👑 CEO: {'✅' if ceo_ok else '❌'} {ceo_comment}"
    )

    if not ceo_ok:
        return False, combined  # CEO вето — финально, независимо от остальных
    approved = sum([sci_ok, arch_ok, ceo_ok]) >= 2
    return approved, combined


async def run_breakthrough_cycle(fellow_key: str | None = None) -> str | None:
    if not await sync_repos_or_alert():
        return None

    fellow_key = fellow_key or fair_sample(list(FELLOW_BUILDERS.keys()), k=1)[0]
    record_participation(fellow_key)
    label = FELLOW_LABELS.get(fellow_key, fellow_key)

    print(f"{label} ищет Breakthrough Proposal...")
    proposal = await scout_breakthrough(fellow_key)
    if not proposal:
        print(f"{label}: сейчас нечего предложить такого масштаба.")
        return None

    if is_duplicate(proposal["idea"]):
        print(f"{label}: похоже на дубль с task board — пропускаем.")
        return None

    print(f"{label} предлагает: {proposal['idea']}")
    approved, filter_report = await filter_proposal(label, proposal)

    verdict_msg = (
        f"💡 BREAKTHROUGH PROPOSAL — {label}\n\n"
        f"ИДЕЯ: {proposal['idea']}\n"
        f"ОБОСНОВАНИЕ: {proposal.get('reason', '')}\n"
        f"СЛОЖНОСТЬ: {proposal.get('complexity', '')}\n\n"
        f"ФИЛЬТР:\n{filter_report}\n\n"
        f"{'✅ ОДОБРЕНО' if approved else '❌ ОТКЛОНЕНО'}"
    )
    verdict_brief = await compile_brief(verdict_msg, context_hint="вердикт фильтра Breakthrough Proposal (Chief Scientist + Chief Architect + CEO)")
    send_telegram_report(verdict_brief)

    task_id = add_task(proposal["idea"], f"fellow:{fellow_key}", status="proposed", reason=proposal.get("reason", ""))

    if not approved:
        update_task_status(task_id, "rejected", filter_report)
        await curate_knowledge(f"Breakthrough Proposal отклонён: {label}", verdict_msg)
        return verdict_msg

    update_task_status(task_id, "in_progress", filter_report)

    # Fellow собирает небольшую команду (2-3 человека из общего пула,
    # исключая самого себя) и реализует, оставаясь техлидом.
    from agents.engineering import build_specialist_pool

    full_pool = build_specialist_pool()
    full_pool.pop(fellow_key, None)
    team_size = random.choice([2, 3])
    helper_names = fair_sample(list(full_pool.keys()), k=min(team_size, len(full_pool)))
    helper_pool = {n: full_pool[n] for n in helper_names}
    record_participation(*helper_names)

    print(f"{label} собирает команду: {', '.join(helper_names)}")
    fellow_writer = FELLOW_BUILDERS[fellow_key](can_write=True)

    report = await run_engineering_task(
        proposal["idea"],
        repo_name="bld-system",  # Fellows работают ТОЛЬКО с bld-system, никогда с bld-panel
        lead_agent=fellow_writer,
        lead_label=f"{label} (тех. лид, команда: {', '.join(helper_names)})",
        helper_pool=helper_pool,
    )
    update_task_status(task_id, "done")

    full_report = f"🚀 BREAKTHROUGH РЕАЛИЗОВАН — {label}\n\n{report}"
    brief = await compile_brief(full_report, context_hint="реализация Breakthrough Proposal")
    send_telegram_report(brief)
    await curate_knowledge(f"Breakthrough Proposal реализован: {label}", f"{verdict_msg}\n\n{full_report}")
    return full_report


async def main():
    await run_breakthrough_cycle()


if __name__ == "__main__":
    asyncio.run(main())
