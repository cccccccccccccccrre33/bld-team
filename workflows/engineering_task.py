"""
Инженерная команда реально пишет и коммитит код по задаче, поставленной
советом директоров или правлением. Работает в ОТДЕЛЬНОЙ ветке —
НИКОГДА не пушит напрямую в main (это защищено на уровне
tools/repo_tools.py). Мерж в main теперь тоже автоматический — Review
Gate даёт чистый вердикт → merge_branch_to_main() мержит сам, без
участия человека. Если вердикт остаётся плохим даже после одной
переделки — решение уходит к CTO (не к основателю), см. cto_approval().

Ведущий инженер (модель gpt-5.4 по умолчанию) сам решает, справится
один или нужно привлечь ещё инженеров — без фиксированных сроков,
по факту сложности того, что видно в реальном коде. Это решение
передаётся структурированным статус-блоком (см. STATUS_BLOCK_MARKER/
parse_help_signal ниже), а не угадывается по случайным словам в
свободном тексте отчёта.
"""

import asyncio
import re
import sys
import uuid

from agents.architecture_council import ARCHITECT_LABELS
from agents.architecture_council import SPECIALTY_KEYWORDS as ARCHITECT_KEYWORDS
from agents.engineering import build_lead_engineer, build_specialist_pool
from agents.expansion_geniuses import GLOBAL_LABELS as EXPANSION_LABELS
from agents.expansion_geniuses import SPECIALTY_KEYWORDS as EXPANSION_KEYWORDS
from agents.global_geniuses import GLOBAL_LABELS
from agents.global_geniuses import SPECIALTY_KEYWORDS as GENIUS_KEYWORDS
from agents.growth_team import GROWTH_LABELS
from agents.growth_team import SPECIALTY_KEYWORDS as GROWTH_KEYWORDS
from agents.review_gate import run_review_gate
from agents.specialists import SPECIALIST_LABELS
from agents.specialists import SPECIALTY_KEYWORDS as SPECIALIST_KEYWORDS
from config.models import BOARD_MODEL_ASSIGNMENTS, EXPANSION_MODEL_ASSIGNMENTS, GLOBAL_MODEL_ASSIGNMENTS, GROWTH_MODEL_ASSIGNMENTS, SPECIALIST_MODEL_ASSIGNMENTS
from tools.repo_tools import commit_and_push, create_branch, get_repo_write_lock, merge_branch_to_main
from tools.telegram_report import send_telegram_report
from workflows._common import compile_brief, curate_knowledge, safe_agent_run, sync_repos_or_alert
from workflows.cto_approval import cto_approval

ALL_SPECIALTY_KEYWORDS = {**GENIUS_KEYWORDS, **SPECIALIST_KEYWORDS, **GROWTH_KEYWORDS, **EXPANSION_KEYWORDS, **ARCHITECT_KEYWORDS}
ALL_SPECIALIST_LABELS = {**GLOBAL_LABELS, **SPECIALIST_LABELS, **GROWTH_LABELS, **EXPANSION_LABELS, **ARCHITECT_LABELS}
ALL_SPECIALIST_MODELS = {**GLOBAL_MODEL_ASSIGNMENTS, **SPECIALIST_MODEL_ASSIGNMENTS, **GROWTH_MODEL_ASSIGNMENTS, **EXPANSION_MODEL_ASSIGNMENTS}

# РАНЬШЕ: решение "звать ли помощь" принималось поиском подстрок вида
# "нужна помощь" в свободном тексте лида — если лид описывал ситуацию
# другими словами (что для 40+ разных моделей в ростере абсолютно
# нормально), помощь просто не звалась, хотя объективно была нужна. И
# наоборот — случайное упоминание "второй инженер" не по делу могло
# вызвать помощь зря. Это была имитация решения, а не решение.
#
# ТЕПЕРЬ: лида явно просят вернуть машинно-читаемый статус-блок
# (STATUS_BLOCK_MARKER ниже) — это его собственное структурированное
# решение, а не наша догадка по фразам. HELP_KEYWORDS оставлены только
# как ЯВНО помеченный запасной вариант на случай, если конкретная
# модель проигнорирует формат (см. parse_help_signal) — используется
# редко и всегда с пометкой в отчёте, чтобы это было видно, а не
# маскировалось под нормальную работу.
HELP_KEYWORDS = [
    "привлек", "привлёк", "нужна помощь", "разбил", "разбить",
    "второй инженер", "инженер 2", "junior", "ещё одного инженера",
    "потребуется ещё", "не справлюсь один", "нужен специалист",
]

STATUS_BLOCK_MARKER = "===СТАТУС==="

STATUS_BLOCK_INSTRUCTIONS = f"""
В САМОМ КОНЦЕ ответа, отдельным блоком (не смешивай со свободным
описанием работы выше), добавь СТРОГО в таком формате:

{STATUS_BLOCK_MARKER}
ПОМОЩЬ_НУЖНА: ДА или НЕТ
ОБЛАСТИ: [если ДА — через запятую конкретные области оставшейся работы,
например "безопасность, база данных"; если НЕТ — оставь пустым]
{STATUS_BLOCK_MARKER}

Это машинно-читаемый статус, а не часть твоего рассказа о работе —
заполни его всегда, даже если помощь не нужна.
"""


def parse_help_signal(lead_summary: str) -> tuple[bool, list[str], str, bool]:
    """Извлекает структурированное решение лида о том, нужна ли помощь
    и в каких областях — вместо поиска случайных фраз по всему тексту.

    Возвращает (нужна_ли_помощь, области, текст_без_статус_блока,
    сработал_ли_запасной_вариант). Если лид проигнорировал формат
    (структурный блок не найден) — используется старый HELP_KEYWORDS
    как запасной вариант, а четвёртый элемент = True, чтобы вызывающий
    код мог явно пометить это в отчёте (см. run_engineering_task)."""
    match = re.search(
        rf"{re.escape(STATUS_BLOCK_MARKER)}(.*?){re.escape(STATUS_BLOCK_MARKER)}",
        lead_summary, re.IGNORECASE | re.DOTALL,
    )
    if match:
        block = match.group(1)
        clean_text = (lead_summary[:match.start()] + lead_summary[match.end():]).strip()
        needs_help = bool(re.search(r"ПОМОЩЬ_НУЖНА\s*:\s*ДА", block, re.IGNORECASE))
        areas: list[str] = []
        areas_match = re.search(r"ОБЛАСТИ\s*:\s*(.+)", block, re.IGNORECASE)
        if areas_match:
            areas = [a.strip() for a in areas_match.group(1).split(",") if a.strip()]
        return needs_help, areas, clean_text, False

    # Запасной вариант: модель проигнорировала формат статус-блока.
    # Не идеально, но лучше, чем полностью терять сигнал о помощи —
    # вызывающий код обязан пометить это как fallback в отчёте.
    legacy_needs_help = any(kw in lead_summary.lower() for kw in HELP_KEYWORDS)
    return legacy_needs_help, [], lead_summary, True


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len] or "task"


def make_branch_name(task: str, branch_prefix: str) -> str:
    """Уникальная ветка на задачу: читаемый слаг + короткий случайный
    суффикс (защита от коллизий, если два похожих по формулировке
    задания стартуют одновременно — например, два человека независимо
    друг от друга нашли одну и ту же проблему до того, как is_duplicate()
    на доске задач успела это заметить)."""
    return f"{branch_prefix}/{slugify(task)}-{uuid.uuid4().hex[:8]}"


def guess_repo(task: str) -> str:
    """Простая эвристика: если задача явно про фронт/панель — bld-panel,
    иначе по умолчанию bld-system."""
    lowered = task.lower()
    if any(kw in lowered for kw in ["панел", "фронт", "react", "ui", "интерфейс"]):
        return "bld-panel"
    return "bld-system"


def find_matching_specialists(text: str, max_specialists: int = 2) -> list[str]:
    """По ключевым словам определяет, чья специализация подходит под
    описанную лидом оставшуюся работу — максимум max_specialists штук,
    чтобы не разводить бесконечный найм."""
    lowered = text.lower()
    matches = [name for name, kws in ALL_SPECIALTY_KEYWORDS.items() if any(kw in lowered for kw in kws)]
    return matches[:max_specialists]


# Иерархия принятия решений: у Review Gate РЕАЛЬНОЕ право вето, не
# просто совещательный голос. Если хотя бы один из трёх ревьюеров
# выносит серьёзный негативный вердикт — лид-инженер ОБЯЗАН
# переделать, прежде чем изменения смержатся в main. Ограничено ОДНИМ
# циклом переделки, чтобы не уйти в бесконечный цикл и не разорить
# бюджет — если после переделки всё ещё есть проблемы, решение, мержить
# ли всё равно, отдаётся CTO (см. cto_approval), а не основателю.
#
# Первые два маркера ("❌ ЕСТЬ УПАВШИЕ ТЕСТЫ", "❌ ТЕСТЫ НЕ ЗАВЕРШИЛИСЬ")
# — из tools.repo_tools.run_test_suite(), т.е. РЕАЛЬНЫЙ факт выполнения
# кода, а не мнение модели. Они принципиально важнее остальных трёх
# (текстовые вердикты LLM-ревьюеров) — сильная модель на ревью не
# заменяет тесты/CI/fuzzing, а дополняет их; факт падения теста не
# может быть "переспорен" тем, что diff выглядит чисто на глаз.
NEGATIVE_VERDICT_MARKERS = [
    "❌ ЕСТЬ УПАВШИЕ ТЕСТЫ", "❌ ТЕСТЫ НЕ ЗАВЕРШИЛИСЬ",
    "ТРЕБУЕТ ПЕРЕДЕЛКИ", "REJECT", "ЛОМАЕТСЯ ЛЕГКО",
]


def needs_rework(verdict_text: str) -> bool:
    upper = verdict_text.upper()
    return any(marker in upper for marker in NEGATIVE_VERDICT_MARKERS)


async def run_engineering_task(
    task: str,
    repo_name: str | None = None,
    lead_agent=None,
    lead_label: str = "Ведущий инженер",
    lead_model: str | None = None,
    helper_pool: dict | None = None,
    branch_prefix: str = "ai-eng",
    force_consult: bool = False,
) -> str:
    """Полный цикл: ветка -> лид пишет код -> (опционально) привлекает
    помощь -> коммит/пуш -> Review Gate -> (опционально) переделка по
    вето -> отчёт.

    По умолчанию (без доп. параметров) — старое поведение: одиночный
    лид-инженер (gpt-5.4) + полный пул из 13 специалистов. Параметры
    lead_agent/helper_pool позволяют переиспользовать эту же логику
    для постоянных отрядов (workflows/squad_task.py) — свой лид, свой
    ограниченный пул участников отряда.

    force_consult: если True — привлечь пул отряда независимо от того,
    упомянул ли лид ключевые слова HELP_KEYWORDS (используется squad_task.py,
    чтобы отряд всегда работал как команда, а не только лид в одиночку).

    Ветка — уникальная на эту задачу (create_branch создаёт для неё
    отдельную изолированную git worktree, см. tools/repo_tools.py) — это
    и позволяет нескольким людям одновременно вызывать эту функцию с
    одним и тем же repo_name безопасно (см.
    workflows/individual_initiative.py: несколько человек за один тик).
    Единственное место, где параллельные вызовы всё ещё могут
    столкнуться — сам merge_branch_to_main (он трогает общий клон, а
    не per-task worktree) — поэтому именно вокруг него, а не вокруг
    всей функции, стоит get_repo_write_lock(repo_name)."""
    repo_name = repo_name or guess_repo(task)
    branch_name = make_branch_name(task, branch_prefix)

    print(f"Создаём изолированную ветку {branch_name} в {repo_name}...")
    print(create_branch(repo_name, branch_name))

    lead_model = lead_model or BOARD_MODEL_ASSIGNMENTS.get("lead_engineer", "gpt-5.4")
    lead = lead_agent or build_lead_engineer(lead_model)
    pool = helper_pool if helper_pool is not None else build_specialist_pool()
    pool_keywords = {k: v for k, v in ALL_SPECIALTY_KEYWORDS.items() if k in pool} if helper_pool is not None else ALL_SPECIALTY_KEYWORDS

    prompt = f"""
Задача: {task}

Репозиторий для работы: {repo_name}. Ветка {branch_name} уже создана
и является текущей — просто пиши файлы через write_file, изменения
автоматически попадут в неё.
{STATUS_BLOCK_INSTRUCTIONS}"""
    print(f"{lead_label} разбирается с задачей и пишет код...")
    lead_summary = await safe_agent_run(lead, prompt, person_label=f"{lead_label} ({lead_model})")

    if lead_summary is None:
        return (
            f"⚠️ ИНЖЕНЕРНАЯ ЗАДАЧА НЕ ВЫПОЛНЕНА — МОДЕЛЬ НЕДОСТУПНА\n\n"
            f"ЗАДАЧА: {task}\n\n"
            f"{lead_label} ({lead_model}) не ответил после нескольких попыток "
            "(транзиентная недоступность бэкенда, см. лог safe_agent_run). "
            "Код не писался, ветка не тронута, review gate не запускался. "
            "Нужно перезапустить задачу вручную."
        )

    if "ЗАДАЧА НЕ ОСМЫСЛЕН" in lead_summary.upper():
        return (
            f"⚠️ ИНЖЕНЕРНАЯ ЗАДАЧА ОТКЛОНЕНА ЛИДОМ\n\n"
            f"ЗАДАЧА: {task}\n\n"
            f"{lead_summary}\n\n"
            "Код не писался, ветка не тронута, review gate не запускался."
        )

    needs_help, help_areas, clean_lead_summary, used_fallback = parse_help_signal(lead_summary)

    findings = [f"👷‍♂️ {lead_label} ({lead_model}):\n{clean_lead_summary}"]
    if used_fallback:
        findings.append(
            "⚠️ Лид не вернул структурированный статус-блок — решение о помощи "
            "принято резервной эвристикой по ключевым словам (менее надёжно, "
            "стоит обратить внимание, если это повторяется у этой модели)."
        )

    if (force_consult or needs_help) and pool:
        # Если лид явно назвал области (структурный сигнал) — матчим
        # специалистов по НИМ, а не по всему свободному тексту: короче,
        # точнее, меньше случайных ложных срабатываний на непричастные
        # слова из середины рассказа о работе.
        match_source = ", ".join(help_areas) if help_areas else clean_lead_summary
        matched_names = [n for n in find_matching_specialists(match_source, max_specialists=2) if n in pool]
        if not matched_names:
            import random
            matched_names = [random.choice(list(pool.keys()))]

        print(f"{lead_label} запросил помощь — привлекаем: {', '.join(matched_names)}...")

        for name in matched_names:
            specialist = pool[name]
            label = ALL_SPECIALIST_LABELS.get(name, name)
            model_name = ALL_SPECIALIST_MODELS.get(name, "?")
            specialist_prompt = f"""
{lead_label} оставил такое описание задачи и своей части работы:

{clean_lead_summary}

Полная исходная задача: {task}
Репозиторий: {repo_name}, ветка {branch_name} (уже текущая).

Ты привлечён именно потому, что часть оставшейся работы совпадает с
твоей специализацией. Определи свою часть и реализуй её через
write_file.
"""
            specialist_text = await safe_agent_run(specialist, specialist_prompt, person_label=f"{label} ({model_name})")
            if specialist_text is None:
                findings.append(f"{label} ({model_name}): не ответил после нескольких попыток — пропущен, часть работы могла остаться нереализованной.")
                continue
            findings.append(f"{label} ({model_name}):\n{specialist_text}")

    print("Коммитим и пушим изменения...")
    push_result = commit_and_push(repo_name, branch_name, f"AI engineering: {task[:60]}")
    print(push_result)

    engineering_summary = "\n\n".join(findings)

    print("Review Gate: Chief Architect, Reviewer и Failure Engineer проверяют изменение...")
    review_verdict = await run_review_gate(task, repo_name, branch_name, engineering_summary)
    print(review_verdict)

    rework_note = ""
    if needs_rework(review_verdict):
        print("Review Gate потребовал переделки — это ВЕТО, лид обязан исправить...")
        rework_prompt = f"""
Review Gate (Chief Architect / Reviewer / Failure Engineer — все
сеньоры с реальным опытом) проверил твою работу и вернул серьёзные
замечания. Это не совет, а обязательное требование — переделай:

{review_verdict}

Исходная задача: {task}
Репозиторий: {repo_name}, ветка {branch_name} (текущая, изменения уже
внесены тобой ранее).

Через write_file внеси точечные правки, устраняющие именно эти
замечания — не переписывай всё с нуля без необходимости. В конце
кратко опиши, что именно исправил по каждому замечанию.
"""
        rework_text = await safe_agent_run(lead, rework_prompt, person_label=f"{lead_label} (доработка)")
        if rework_text is None:
            findings.append(f"🔄 {lead_label} (доработка по вето Review Gate): не ответил после нескольких попыток — доработка не выполнена, замечания Review Gate остались неисправленными.")
        else:
            findings.append(f"🔄 {lead_label} (доработка по вето Review Gate):\n{rework_text}")
        engineering_summary = "\n\n".join(findings)

        push_result_2 = commit_and_push(repo_name, branch_name, "AI engineering: доработка по замечаниям Review Gate")
        print(push_result_2)
        push_result = push_result + "\n\n(после доработки)\n" + push_result_2

        print("Повторная проверка Review Gate после доработки...")
        review_verdict_2 = await run_review_gate(task, repo_name, branch_name, engineering_summary)
        print(review_verdict_2)

        rework_note = (
            "🔄 ПОТРЕБОВАЛАСЬ ОДНА ПЕРЕДЕЛКА — Review Gate изначально не пропустил "
            "первую версию (вердикт ниже — ДО переделки), лид исправил, вот "
            "вердикт ПОСЛЕ.\n\n"
            f"ВЕРДИКТ ДО ПЕРЕДЕЛКИ:\n{review_verdict}\n\n"
        )
        review_verdict = review_verdict_2

    # Мерж — БЕЗ участия человека. Если после (максимум одной) переделки
    # вердикт чист — мержим автоматически. Если всё ещё есть проблемы —
    # решение принимает CTO (эскалирует к CEO сам, если не уверен), а не
    # основатель: см. workflows/cto_approval.py.
    if not needs_rework(review_verdict):
        print("Review Gate: вердикт чист — мержим в main автоматически...")
        async with get_repo_write_lock(repo_name):
            merge_result = merge_branch_to_main(repo_name, branch_name, task)
        print(merge_result)
        merge_note = f"\n\n{merge_result}"
    else:
        print("Review Gate: проблемы остались даже после переделки — решение за CTO...")
        cto_approved, cto_comment = await cto_approval(
            squad_label=f"{lead_label} (Review Gate, после переделки)",
            task_title=task,
            reason=f"Review Gate не пропустил дважды подряд:\n{review_verdict}",
            how="Лид уже сделал одну переделку по замечаниям — эскалируем, "
                "т.к. повторной переделки этот пайплайн не делает (см. NEGATIVE_VERDICT_MARKERS).",
        )
        if cto_approved:
            print(f"CTO решил мержить несмотря на замечания: {cto_comment}")
            async with get_repo_write_lock(repo_name):
                merge_result = merge_branch_to_main(repo_name, branch_name, f"{task} (approved by CTO despite review notes)")
            print(merge_result)
            merge_note = f"\n\n🧑‍💼 CTO решил смержить несмотря на замечания: {cto_comment}\n\n{merge_result}"
        else:
            print(f"CTO заблокировал мерж: {cto_comment}")
            merge_note = (
                f"\n\n🧑‍💼 CTO НЕ дал добро на мерж: {cto_comment}\n\n"
                f"⚠️ Изменения остаются в ветке {branch_name} — нужна ручная разборка "
                "(не обязательно основателем, любым, у кого есть контекст по задаче)."
            )

    report = (
        f"👷‍♂️ ИНЖЕНЕРНАЯ ЗАДАЧА ВЫПОЛНЕНА\n\n"
        f"ЗАДАЧА:\n{task}\n\n"
        f"РЕПОЗИТОРИЙ: {repo_name}\n"
        f"ВЕТКА: {branch_name}\n\n"
        + engineering_summary
        + f"\n\n{push_result}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "REVIEW GATE\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        + rework_note
        + review_verdict
        + merge_note
    )
    return report


async def main():
    task = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
    if not task:
        print('Использование: python main_engineering.py "текст задачи"')
        return

    print("Синхронизация репозиториев...")
    if not await sync_repos_or_alert():
        return

    report = await run_engineering_task(task)
    print(f"\n{report}")

    brief = await compile_brief(report)
    print(f"\n[КОРОТКО]\n{brief}")
    send_telegram_report(brief)

    await curate_knowledge("Инженерная задача", report)


if __name__ == "__main__":
    asyncio.run(main())
