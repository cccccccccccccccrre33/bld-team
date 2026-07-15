"""
Индивидуальная инициатива — не только 2 фиксированных отряда. ЛЮБОЙ
человек компании с реальным доступом к коду (9 глобальных гениев + 4
специалиста + 3 growth-роли + 10 expansion-гениев + 10 архитекторов +
150 Global Elite I/II = 186 человек) может сам заметить проблему в
СВОЕЙ специализации и предложить фикс. (Старая цифра "26" в этом же
комментарии была неточной ещё до Global Elite — не учитывала 10
expansion-гениев; посчитано заново по факту содержимого словарей, а не
по старой формуле.)

ВАЖНО: решение никогда не принимается одним человеком в одиночку, даже
если он сам уверен в своей области. Каждая инициатива проходит
консультацию — по возможности с профильным экспертом в этой же
области (архитектором из agents/architecture_council.py, если
специализация совпадает — это и есть его реальный "кумир", у кого он
спросит), а если профильного эксперта нет — с CTO. "Уверенность"
человека влияет не на то, спрашивать ли кого-то вообще, а на то, идёт
ли он к CTO формально или к более узкому специалисту рядом с собой —
консультация происходит всегда.

Может привлечь ещё людей себе в помощь — это уже встроено в
run_engineering_task (helper_pool по умолчанию = весь общий пул).
"""

import asyncio
import random
import sys

from agents.architecture_council import ARCHITECT_BUILDERS, ARCHITECT_LABELS
from agents.architecture_council import SPECIALTY_KEYWORDS as ARCHITECT_KEYWORDS
from agents.expansion_geniuses import GENIUS_BUILDERS as EXPANSION_BUILDERS, GLOBAL_LABELS as EXPANSION_LABELS
from agents.global_elite import ELITE1_BUILDERS, ELITE1_LABELS
from agents.global_elite import ELITE1_SPECIALTY_KEYWORDS
from agents.global_elite_100 import ELITE2_BUILDERS, ELITE2_LABELS
from agents.global_elite_100 import ELITE2_SPECIALTY_KEYWORDS
from agents.global_geniuses import GENIUS_BUILDERS, GLOBAL_LABELS
from agents.growth_team import GROWTH_BUILDERS, GROWTH_LABELS
from agents.specialists import SPECIALIST_BUILDERS, SPECIALIST_LABELS
from tools.repo_tools import clone_or_update_repos, git_log, grep_repo
from tools.telegram_report import send_telegram_report
from workflows._common import compile_brief, curate_knowledge, fair_sample, format_notebook, load_notebook, record_participation, save_notebook_entry
from workflows.cto_approval import consult, cto_approval
from workflows.engineering_task import run_engineering_task
from workflows.task_board import add_task, can_take_more, get_board_summary, is_duplicate, update_task_status

ALL_BUILDERS = {
    **GENIUS_BUILDERS, **SPECIALIST_BUILDERS, **GROWTH_BUILDERS, **EXPANSION_BUILDERS,
    **ARCHITECT_BUILDERS, **ELITE1_BUILDERS, **ELITE2_BUILDERS,
}
ALL_LABELS = {
    **GLOBAL_LABELS, **SPECIALIST_LABELS, **GROWTH_LABELS, **EXPANSION_LABELS,
    **ARCHITECT_LABELS, **ELITE1_LABELS, **ELITE2_LABELS,
}

# "Молодые" — те же 19 человек, что описаны как "молодые гении" в
# agents/global_geniuses.py (недавние выпускники) и
# agents/expansion_geniuses.py (10 новых вузов). У них персональный
# дневник (см. workflows/_common.py: load_notebook/save_notebook_entry)
# — по запросу Валика: "постоянная студенческая погружённость",
# непрерывная нить любопытства, а не разовые случайные вспышки.
YOUNG_NAMES = set(GENIUS_BUILDERS.keys()) | set(EXPANSION_BUILDERS.keys())


def weighted_pick() -> str:
    """Молодые выбираются заметно чаще (по просьбе Валика — они должны
    жить в системе), но не эксклюзивно — сеньоры/специалисты тоже
    иногда берут инициативу. ~65% попаданий на 19 молодых, ~35% на
    остальных 17. ВНУТРИ каждой группы — честный выбор через
    fair_sample (общий трекер участия по всей компании), чтобы внутри
    самой группы молодых/сеньоров тоже не было перекоса в пользу
    одних и тех же людей."""
    if random.random() < 0.65:
        return fair_sample(list(YOUNG_NAMES), k=1)[0]
    others = [n for n in ALL_BUILDERS if n not in YOUNG_NAMES]
    return fair_sample(others, k=1)[0]


def find_domain_consultant(name: str, title: str, reason: str):
    """Ищет профильного эксперта для консультации по теме задачи — по
    совпадению ключевых слов темы с зоной экспертизы. Сначала смотрит
    среди исходных 10 архитекторов (architecture_council.py, они и были
    задуманы как "кумиры"-консультанты), затем — среди 150 Global Elite
    I/II (там зачастую более узко релевантный эксперт, чем любой из
    10 генералистов-архитекторов). Исключает самого инициатора (нет
    смысла "спрашивать себя"). Если совпадений нигде нет — вернёт None,
    и тогда идём к CTO.

    Возвращает (consultant_key, consultant_agent, consultant_label)
    или (None, None, None)."""
    text = f"{title} {reason}".lower()
    for keywords_dict, builders_dict, labels_dict in (
        (ARCHITECT_KEYWORDS, ARCHITECT_BUILDERS, ARCHITECT_LABELS),
        (ELITE1_SPECIALTY_KEYWORDS, ELITE1_BUILDERS, ELITE1_LABELS),
        (ELITE2_SPECIALTY_KEYWORDS, ELITE2_BUILDERS, ELITE2_LABELS),
    ):
        for key, keywords in keywords_dict.items():
            if key == name:
                continue
            if any(kw in text for kw in keywords):
                builder = builders_dict[key]
                return key, builder(can_write=False), labels_dict[key]
    return None, None, None


async def scout_and_propose(name: str) -> dict | None:
    """Человек сканирует код в СВОЕЙ специализации (read-only) и сам
    оценивает, уверен ли он взять это на себя, или стоит спросить CTO.

    Для молодых (YOUNG_NAMES) — видит свою историю из личного дневника
    перед сканированием, чтобы разговор ощущался как продолжение одной
    непрерывной нити любопытства, а не разовый случайный заход."""
    if not can_take_more():
        print(f"[{name}] Лимит параллельных задач исчерпан")
        return None

    board_summary = get_board_summary()
    person = ALL_BUILDERS[name](can_write=False)
    is_young = name in YOUNG_NAMES

    notebook_block = ""
    if is_young:
        notebook_entries = load_notebook(name)
        notebook_block = f"""
Твой личный дневник (что тебя занимало в прошлые разы — продолжай
эту нить, если она ещё актуальна, или переключись на новое, если
исчерпал тему):
{format_notebook(notebook_entries)}
"""

    prompt = f"""
Доска активных задач компании (не дублируй то, что уже в работе):
{board_summary}
{notebook_block}
Загляни в реальный код (git_log, grep_repo по bld-system и bld-panel)
и найди ОДНУ конкретную проблему именно в твоей специализации — не
общую, а такую, в которой ты реально эксперт.

Если ничего реального не нашёл — ответь строго: НЕТ ЗАДАЧИ
[и одной строкой добавь, куда смотрел и что примерно видел — это
уйдёт в твой личный дневник, даже отсутствие готовой задачи — это
часть твоего непрерывного исследования]

Если нашёл — ответь СТРОГО в этом формате:
ЗАДАЧА: [одна строка]
ПОЧЕМУ: [2-3 предложения, по существу]
КАК: [2-3 предложения, конкретный план]
УВЕРЕННОСТЬ: УВЕРЕН или СПРОСИТЬ CTO

УВЕРЕН — если это чётко твоя специализация и у тебя есть ясный план.
СПРОСИТЬ CTO — если сомневаешься, или задача выходит за границы твоей
конкретной экспертизы, или может затронуть что-то более широкое.
В любом случае ты обсудишь это с кем-то перед реализацией — "уверен"
влияет на то, к кому идти (профильный эксперт рядом или CTO), а не на
то, спрашивать ли вообще.
"""
    response = await person.run(prompt)
    text = response.text.strip()

    if is_young:
        # Дневник пишется ВСЕГДА — даже "ничего конкретного не нашёл,
        # но смотрел туда-то" — именно это создаёт ощущение непрерывной
        # вовлечённости, а не редких случайных вспышек.
        diary_entry = text[:400] if len(text) > 30 else "Заходил посмотреть код, пока без конкретных зацепок."
        save_notebook_entry(name, diary_entry)

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
    name = name or weighted_pick()
    record_participation(name)
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

    print(f"[{name}] Proposal: {title} (склонность: {'к профильному эксперту' if confident else 'к CTO'})")

    task_id = add_task(title, name, status="proposed", reason=reason, how=how)

    # Всегда консультируемся — "уверенность" влияет только на то, к
    # кому идти. Сначала пробуем найти профильного эксперта (его
    # реального "кумира" в этой области); если такого нет — CTO.
    consultant_key, consultant_agent, consultant_label = (
        find_domain_consultant(name, title, reason) if confident else (None, None, None)
    )

    if consultant_agent:
        print(f"[{name}] Идёт посоветоваться с профильным экспертом: {consultant_label}")
        approved, comment = await consult(consultant_agent, consultant_label, label, title, reason, how)
        verdict_source = consultant_label
    else:
        print(f"[{name}] Идёт советоваться с CTO...")
        approved, comment = await cto_approval(label, title, reason, how)
        verdict_source = "🧑‍💼 CTO"

    if not approved:
        update_task_status(task_id, "rejected", comment)
        report = (
            f"❌ ИНИЦИАТИВА ОТКЛОНЕНА ({verdict_source})\n\n"
            f"{label}\nЗадача: {title}\n\nКомментарий: {comment}"
        )
        print(report)
        send_telegram_report(report)
        if name in YOUNG_NAMES:
            save_notebook_entry(name, f"Предложил '{title}' — отклонили ({comment[:150]}). Подумаю дальше.")
        return

    update_task_status(task_id, "in_progress", comment)
    verdict_note = f"✅ Одобрено ({verdict_source}): {comment}"

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
    if name in YOUNG_NAMES:
        save_notebook_entry(name, f"Реализовал '{title}' — одобрили и довёл до кода. Дальше можно копать глубже в эту область или переключиться.")


async def main():
    name = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in ALL_BUILDERS else None

    print("Синхронизация репозиториев...")
    print(clone_or_update_repos())

    try:
        await run_individual_initiative(name)
    except Exception as e:
        error_alert = (
            "🔴 СБОЙ В INDIVIDUAL INITIATIVE\n\n"
            f"{type(e).__name__}: {e}\n\n"
            "Проверь полный лог этого запуска в GitHub Actions для деталей."
        )
        print(error_alert)
        send_telegram_report(error_alert)


if __name__ == "__main__":
    asyncio.run(main())
