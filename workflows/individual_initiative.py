"""
Индивидуальная инициатива — не только 2 фиксированных отряда. ЛЮБОЙ
человек компании с реальным доступом к коду (9 глобальных гениев + 4
специалиста + 3 growth-роли + 10 expansion-гениев + 10 архитекторов +
550 Global Elite I/II/III/IV/V/VI = 586 человек) может сам заметить проблему в
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
import json
import os
import random
import sys
from pathlib import Path

from agents.architecture_council import ARCHITECT_BUILDERS, ARCHITECT_LABELS
from agents.architecture_council import SPECIALTY_KEYWORDS as ARCHITECT_KEYWORDS
from agents.expansion_geniuses import GENIUS_BUILDERS as EXPANSION_BUILDERS, GLOBAL_LABELS as EXPANSION_LABELS
from agents.expansion_geniuses import SPECIALTY_KEYWORDS as EXPANSION_KEYWORDS
from agents.global_elite import ELITE1_BUILDERS, ELITE1_LABELS
from agents.global_elite import ELITE1_SPECIALTY_KEYWORDS
from agents.global_elite_100 import ELITE2_BUILDERS, ELITE2_LABELS
from agents.global_elite_100 import ELITE2_SPECIALTY_KEYWORDS
from agents.global_elite_3 import ELITE3_BUILDERS, ELITE3_LABELS
from agents.global_elite_3 import ELITE3_SPECIALTY_KEYWORDS
from agents.global_elite_4 import ELITE4_BUILDERS, ELITE4_LABELS
from agents.global_elite_4 import ELITE4_SPECIALTY_KEYWORDS
from agents.global_elite_5 import ELITE5_BUILDERS, ELITE5_LABELS
from agents.global_elite_5 import ELITE5_SPECIALTY_KEYWORDS
from agents.global_elite_6 import ELITE6_BUILDERS, ELITE6_LABELS
from agents.global_elite_6 import ELITE6_SPECIALTY_KEYWORDS
from agents.global_geniuses import GENIUS_BUILDERS, GLOBAL_LABELS
from agents.global_geniuses import SPECIALTY_KEYWORDS as GENIUS_KEYWORDS
from agents.growth_team import GROWTH_BUILDERS, GROWTH_LABELS
from agents.growth_team import SPECIALTY_KEYWORDS as GROWTH_KEYWORDS
from agents.specialists import SPECIALIST_BUILDERS, SPECIALIST_LABELS
from agents.specialists import SPECIALTY_KEYWORDS as SPECIALIST_KEYWORDS
from tools.repo_tools import clone_or_update_repos, git_log, grep_repo
from tools.telegram_report import send_telegram_report
from workflows._common import compile_brief, curate_knowledge, fair_sample, format_notebook, load_notebook, record_participation, save_notebook_entry
from workflows.cto_approval import consult, cto_approval
from workflows.engineering_task import run_engineering_task
from workflows.task_board import add_task, can_take_more, get_board_summary, is_duplicate, update_task_status

ALL_BUILDERS = {
    **GENIUS_BUILDERS, **SPECIALIST_BUILDERS, **GROWTH_BUILDERS, **EXPANSION_BUILDERS,
    **ARCHITECT_BUILDERS, **ELITE1_BUILDERS, **ELITE2_BUILDERS, **ELITE3_BUILDERS, **ELITE4_BUILDERS,
    **ELITE5_BUILDERS, **ELITE6_BUILDERS,
}
ALL_LABELS = {
    **GLOBAL_LABELS, **SPECIALIST_LABELS, **GROWTH_LABELS, **EXPANSION_LABELS,
    **ARCHITECT_LABELS, **ELITE1_LABELS, **ELITE2_LABELS, **ELITE3_LABELS, **ELITE4_LABELS,
    **ELITE5_LABELS, **ELITE6_LABELS,
}

# Ключевые слова специализации каждого — те же самые, по которым в
# engineering_task.py находят помощников. Нужны здесь для ДРУГОЙ цели:
# сматчить человека с ветками Company Pulse / Chevruta по его теме,
# чтобы инициатива не изобреталась в вакууме, а могла подхватить то,
# что коллеги уже обсудили в общем чате, но никто не довёл до задачи.
ALL_MATCH_KEYWORDS = {
    **GENIUS_KEYWORDS, **SPECIALIST_KEYWORDS, **GROWTH_KEYWORDS, **EXPANSION_KEYWORDS,
    **ARCHITECT_KEYWORDS, **ELITE1_SPECIALTY_KEYWORDS, **ELITE2_SPECIALTY_KEYWORDS,
    **ELITE3_SPECIALTY_KEYWORDS, **ELITE4_SPECIALTY_KEYWORDS, **ELITE5_SPECIALTY_KEYWORDS,
    **ELITE6_SPECIALTY_KEYWORDS,
}


def get_relevant_pulse_threads(name: str, limit: int = 3) -> str:
    """Подтягивает недавние ветки общего чата компании (Company Pulse),
    пересекающиеся по теме со специализацией человека — раньше
    scout_and_propose вообще не знал, что там обсуждалось, и хорошие
    мысли коллег умирали в .state/company_threads.json, никем не
    подхваченные. Не требует "готовности" темы (в отличие от
    escalate_if_ready в company_pulse.py) — здесь достаточно
    пересечения по ключевым словам, решение брать её в работу или нет
    остаётся за самим человеком."""
    keywords = ALL_MATCH_KEYWORDS.get(name, [])
    if not keywords:
        return ""
    path = Path(".state/company_threads.json")
    if not path.exists():
        return ""
    try:
        threads = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""

    matches = []
    for t in threads:
        text = " ".join(m.get("text", "") for m in t.get("messages", [])).lower()
        if any(kw in text for kw in keywords):
            last_msgs = t["messages"][-3:]
            snippet = "\n".join(f"  {m['who']}: {m['text'][:220]}" for m in last_msgs)
            matches.append(f'• "{t["topic"]}":\n{snippet}')

    if not matches:
        return ""
    matches = matches[-limit:]
    return (
        "\n\nНЕДАВНИЕ ОБСУЖДЕНИЯ КОЛЛЕГ ПО ТВОЕЙ ТЕМЕ (общий чат компании, "
        "Company Pulse — ещё НЕ доведены ни до чьей конкретной задачи):\n"
        + "\n".join(matches)
        + "\n\nМожешь взять любую из этих мыслей и довести до конкретной задачи "
        "(это ничем не хуже находки в коде), или найти своё в реальном коде ниже.\n"
    )

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
    остальных. ВНУТРИ каждой группы — честный выбор через fair_sample
    (общий трекер участия по всей компании), чтобы внутри самой группы
    молодых/сеньоров тоже не было перекоса в пользу одних и тех же
    людей."""
    if random.random() < 0.65:
        return fair_sample(list(YOUNG_NAMES), k=1)[0]
    others = [n for n in ALL_BUILDERS if n not in YOUNG_NAMES]
    return fair_sample(others, k=1)[0]


def weighted_pick_many(k: int) -> list[str]:
    """Как weighted_pick(), но сразу k РАЗНЫХ человек — нужно, чтобы за
    один тик компания могла реально работать параллельно, а не по
    одному человеку за раз (см. комментарий у main() ниже про то,
    почему "один случайный человек несколько раз в день" ощущался как
    "просто говорящие головы", а не живая экосистема)."""
    chosen: list[str] = []
    seen: set[str] = set()
    attempts = 0
    # Немного попыток с запасом на случай коллизий fair_sample —
    # людей в ростере намного больше, чем реалистичный k, так что
    # переполнения на практике не будет.
    while len(chosen) < k and attempts < k * 5:
        attempts += 1
        candidate = weighted_pick()
        if candidate not in seen:
            seen.add(candidate)
            chosen.append(candidate)
    return chosen


def find_domain_consultant(name: str, title: str, reason: str):
    """Ищет профильного эксперта для консультации по теме задачи — по
    совпадению ключевых слов темы с зоной экспертизы. Сначала смотрит
    среди исходных 10 архитекторов (architecture_council.py, они и были
    задуманы как "кумиры"-консультанты), затем — среди 550 Global Elite
    I/II/III/IV/V/VI (там зачастую более узко релевантный эксперт, чем
    любой из 10 генералистов-архитекторов). Исключает самого инициатора
    (нет смысла "спрашивать себя"). Если совпадений нигде нет — вернёт
    None, и тогда идём к CTO.

    Побеждает самое специфичное (самое длинное) совпавшее ключевое
    слово среди ВСЕХ словарей — та же логика и та же причина, что и в
    agents/engineering.py::pick_specialist (иначе более общий keyword
    из architecture_council либо из более ранней волны Global Elite
    систематически перехватывал бы более узкое совпадение из поздней
    волны).

    Возвращает (consultant_key, consultant_agent, consultant_label)
    или (None, None, None)."""
    text = f"{title} {reason}".lower()
    best_key, best_dicts, best_score = None, None, 0
    for keywords_dict, builders_dict, labels_dict in (
        (ARCHITECT_KEYWORDS, ARCHITECT_BUILDERS, ARCHITECT_LABELS),
        (ELITE1_SPECIALTY_KEYWORDS, ELITE1_BUILDERS, ELITE1_LABELS),
        (ELITE2_SPECIALTY_KEYWORDS, ELITE2_BUILDERS, ELITE2_LABELS),
        (ELITE3_SPECIALTY_KEYWORDS, ELITE3_BUILDERS, ELITE3_LABELS),
        (ELITE4_SPECIALTY_KEYWORDS, ELITE4_BUILDERS, ELITE4_LABELS),
        (ELITE5_SPECIALTY_KEYWORDS, ELITE5_BUILDERS, ELITE5_LABELS),
        (ELITE6_SPECIALTY_KEYWORDS, ELITE6_BUILDERS, ELITE6_LABELS),
    ):
        for key, keywords in keywords_dict.items():
            if key == name:
                continue
            for kw in keywords:
                if len(kw) > best_score and kw in text:
                    best_key, best_dicts, best_score = key, (builders_dict, labels_dict), len(kw)
    if best_key is not None:
        builders_dict, labels_dict = best_dicts
        return best_key, builders_dict[best_key](can_write=False), labels_dict[best_key]
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

    # РАНЬШЕ личный дневник (непрерывная нить между запусками) был
    # только у 19 "молодых гениев" — у остальных ~167 человек компании
    # каждый запуск начинался с чистого листа, без памяти о том, что
    # сам делал вчера. Именно это и создавало ощущение "просто
    # говорящих голов", а не живых сотрудников: непрерывность — это
    # то, что отличает человека, реально погружённого в работу, от
    # того, кто отвечает на вопрос и забывает всё сразу после. Дневник
    # теперь у ВСЕХ — не только у молодых.
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
{get_relevant_pulse_threads(name)}
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

    # Дневник пишется ВСЕГДА, для любого человека — даже "ничего
    # конкретного не нашёл, но смотрел туда-то" — именно это создаёт
    # ощущение непрерывной вовлечённости, а не редких случайных
    # вспышек.
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

    # РАНЬШЕ: консультация была ОБЯЗАТЕЛЬНОЙ всегда, и "УВЕРЕН" влияло
    # только на то, к кому идти (эксперт или CTO) — не на то, идти ли
    # вообще. По прямому запросу Валика ("максимально свободно, не
    # всегда идти к сто или к кому-то старшему чтобы попросить
    # разрешения — можно самому брать и реализовывать") — теперь
    # "УВЕРЕН" значит именно это: человек сам себе даёт добро и сразу
    # переходит к реализации, без блокирующего разговора перед стартом.
    # Это НЕ отмена контроля качества — Review Gate (Chief Architect +
    # Reviewer + Failure Engineer + реальный прогон тестов, см.
    # workflows/engineering_task.py) всё равно проверяет готовый код
    # перед мержем и имеет реальное вето. Меняется только МОМЕНТ
    # проверки: не "разрешите начать" до того, как что-либо сделано, а
    # "проверьте результат" после. "СПРОСИТЬ CTO" по-прежнему уходит на
    # консультацию ДО реализации — это осталось для случаев, когда
    # сам человек не уверен, что тема целиком в его зоне.
    if confident:
        task_id = add_task(title, name, status="self_approved", reason=reason, how=how)
        approved, verdict_source = True, "самостоятельно"
        comment = (
            "Взял в работу сам, без предварительного согласования — "
            "уверен, что это чётко в своей специализации. Review Gate "
            "проверит готовый результат перед мержем."
        )
        print(f"[{name}] Уверен в своей зоне — берёт в работу самостоятельно, без approval")
    else:
        task_id = add_task(title, name, status="proposed", reason=reason, how=how)
        consultant_key, consultant_agent, consultant_label = find_domain_consultant(name, title, reason)
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
        save_notebook_entry(name, f"Предложил '{title}' — отклонили ({comment[:150]}). Подумаю дальше.")
        return

    update_task_status(task_id, "in_progress", comment)
    verdict_note = (
        f"🔓 Взял сам, без согласования: {comment}" if verdict_source == "самостоятельно"
        else f"✅ Одобрено ({verdict_source}): {comment}"
    )

    # Реализация — сам инициатор становится "лидом" этой задачи (со
    # своим полным write-доступом), может привлечь помощь из общего
    # пула специалистов через ту же машинерию, что и отряды.
    writer = ALL_BUILDERS[name](can_write=True)
    try:
        # individual_initiative.yml: timeout-minutes: 40 (2400с). Разные
        # люди обрабатываются параллельно через asyncio.gather (см.
        # main()), не последовательно — так что каждому можно отдать
        # почти весь бюджет, а не делить его на N.
        report = await run_engineering_task(title, lead_agent=writer, lead_label=label, soft_timeout_seconds=2000)
    except Exception as e:
        print(f"[{name}] run_engineering_task упал с исключением: {e}")
        update_task_status(task_id, "rejected", f"Упало с необработанным исключением: {e}")
        error_report = f"❌ ИНДИВИДУАЛЬНАЯ ИНИЦИАТИВА УПАЛА С ОШИБКОЙ\n\n{label}\nЗадача: {title}\n\nОшибка: {e}"
        print(error_report)
        send_telegram_report(error_report)
        return
    update_task_status(task_id, "done")

    full_report = f"🏁 ИНДИВИДУАЛЬНАЯ ИНИЦИАТИВА\n\n{label}\n{verdict_note}\n\n{report}"
    brief = await compile_brief(full_report)
    print(f"\n{brief}")
    send_telegram_report(brief)
    await curate_knowledge(f"Инициатива: {label}", full_report)
    save_notebook_entry(name, f"Реализовал '{title}' — довёл до кода. Дальше можно копать глубже в эту область или переключиться.")


# РАНЬШЕ каждый тик этого воркфлоу (3 раза в день по cron) запускал
# РОВНО ОДНОГО случайного человека — то есть даже если "людей много",
# в моменте компанией была буквально одна голова. Именно это и
# выглядело как "по одному вызываются по расписанию", а не как живая
# экосистема, где много людей одновременно заняты каждый своим делом.
# Дефолт батча читается из INDIVIDUAL_INITIATIVE_BATCH_SIZE (GitHub
# Actions vars, без правки кода) — можно тюнить под факт: сколько
# реально стоит один тик и не начинает ли параллельный git push/merge
# в main из нескольких веток одновременно конфликтовать чаще, чем
# приемлемо. Явное имя человека в CLI (ручной workflow_dispatch с
# конкретным person) по-прежнему запускает ровно одного — это осознанный
# точечный режим, не тянет за собой остальных.
DEFAULT_BATCH_SIZE = int(os.getenv("INDIVIDUAL_INITIATIVE_BATCH_SIZE", "4"))


async def main():
    explicit_name = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in ALL_BUILDERS else None

    print("Синхронизация репозиториев...")
    print(clone_or_update_repos())

    if explicit_name:
        names = [explicit_name]
    else:
        # available_capacity() уже учитывает MAX_CONCURRENT_TASKS — не
        # смысла заводить больше людей за тик, чем есть реальных слотов
        # на доске, они всё равно упрутся в can_take_more() внутри
        # scout_and_propose и просто ничего не предложат.
        from workflows.task_board import available_capacity
        batch_size = max(1, min(DEFAULT_BATCH_SIZE, available_capacity() or 1))
        names = weighted_pick_many(batch_size)

    print(f"Запускаем параллельно: {', '.join(names)}")

    results = await asyncio.gather(
        *(run_individual_initiative(n) for n in names),
        return_exceptions=True,
    )

    for name, result in zip(names, results):
        if isinstance(result, Exception):
            error_alert = (
                f"🔴 СБОЙ В INDIVIDUAL INITIATIVE ({name})\n\n"
                f"{type(result).__name__}: {result}\n\n"
                "Проверь полный лог этого запуска в GitHub Actions для деталей."
            )
            print(error_alert)
            send_telegram_report(error_alert)


if __name__ == "__main__":
    asyncio.run(main())
