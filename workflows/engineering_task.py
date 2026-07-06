"""
Инженерная команда реально пишет и коммитит код по задаче, поставленной
советом директоров или правлением. Работает в ОТДЕЛЬНОЙ ветке —
НИКОГДА не пушит напрямую в main (это защищено на уровне
tools/repo_tools.py). Валик сам ревьюит ветку и мержит, если согласен.

Ведущий инженер (модель gpt-5.5 по умолчанию) сам решает, справится
один или нужно привлечь ещё инженеров — без фиксированных сроков,
по факту сложности того, что видно в реальном коде.
"""

import asyncio
import re
import sys
from datetime import datetime

from agents.engineering import build_lead_engineer, build_specialist_pool
from agents.global_geniuses import GLOBAL_LABELS
from agents.global_geniuses import SPECIALTY_KEYWORDS as GENIUS_KEYWORDS
from agents.growth_team import GROWTH_LABELS
from agents.growth_team import SPECIALTY_KEYWORDS as GROWTH_KEYWORDS
from agents.review_gate import run_review_gate
from agents.specialists import SPECIALIST_LABELS
from agents.specialists import SPECIALTY_KEYWORDS as SPECIALIST_KEYWORDS
from config.models import BOARD_MODEL_ASSIGNMENTS, GLOBAL_MODEL_ASSIGNMENTS, GROWTH_MODEL_ASSIGNMENTS, SPECIALIST_MODEL_ASSIGNMENTS
from tools.repo_tools import commit_and_push, create_branch
from tools.telegram_report import send_telegram_report
from workflows._common import curate_knowledge, sync_repos_or_alert

ALL_SPECIALTY_KEYWORDS = {**GENIUS_KEYWORDS, **SPECIALIST_KEYWORDS, **GROWTH_KEYWORDS}
ALL_SPECIALIST_LABELS = {**GLOBAL_LABELS, **SPECIALIST_LABELS, **GROWTH_LABELS}
ALL_SPECIALIST_MODELS = {**GLOBAL_MODEL_ASSIGNMENTS, **SPECIALIST_MODEL_ASSIGNMENTS, **GROWTH_MODEL_ASSIGNMENTS}

# Ключевые слова, по которым понимаем, что лид явно попросил помощи —
# простая эвристика, не идеальная, но рабочая без сложного парсинга
# структурированного вывода.
HELP_KEYWORDS = [
    "привлек", "привлёк", "нужна помощь", "разбил", "разбить",
    "второй инженер", "инженер 2", "junior", "ещё одного инженера",
    "потребуется ещё", "не справлюсь один", "нужен специалист",
]


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len] or "task"


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
# переделать, прежде чем отчёт уйдёт Валику. Ограничено ОДНИМ циклом
# переделки, чтобы не уйти в бесконечный цикл и не разорить бюджет —
# если после переделки всё ещё есть проблемы, это уже честно
# показывается Валику как есть, а не скрывается.
NEGATIVE_VERDICT_MARKERS = ["ТРЕБУЕТ ПЕРЕДЕЛКИ", "REJECT", "ЛОМАЕТСЯ ЛЕГКО"]


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
) -> str:
    """Полный цикл: ветка -> лид пишет код -> (опционально) привлекает
    помощь -> коммит/пуш -> Review Gate -> (опционально) переделка по
    вето -> отчёт.

    По умолчанию (без доп. параметров) — старое поведение: одиночный
    лид-инженер (gpt-5.5) + полный пул из 13 специалистов. Параметры
    lead_agent/helper_pool позволяют переиспользовать эту же логику
    для постоянных отрядов (workflows/squad_task.py) — свой лид, свой
    ограниченный пул участников отряда.
    """
    repo_name = repo_name or guess_repo(task)
    branch_name = f"{branch_prefix}/{slugify(task)}-{datetime.now().strftime('%Y%m%d-%H%M')}"

    print(f"Создаём ветку {branch_name} в {repo_name}...")
    print(create_branch(repo_name, branch_name))

    lead_model = lead_model or BOARD_MODEL_ASSIGNMENTS.get("lead_engineer", "gpt-5.5")
    lead = lead_agent or build_lead_engineer(lead_model)
    pool = helper_pool if helper_pool is not None else build_specialist_pool()
    pool_keywords = {k: v for k, v in ALL_SPECIALTY_KEYWORDS.items() if k in pool} if helper_pool is not None else ALL_SPECIALTY_KEYWORDS

    prompt = f"""
Задача: {task}

Репозиторий для работы: {repo_name}. Ветка {branch_name} уже создана
и является текущей — просто пиши файлы через write_file, изменения
автоматически попадут в неё.
"""
    print(f"{lead_label} разбирается с задачей и пишет код...")
    lead_response = await lead.run(prompt)
    lead_summary = lead_response.text.strip()

    if "ЗАДАЧА НЕ ОСМЫСЛЕН" in lead_summary.upper():
        return (
            f"⚠️ ИНЖЕНЕРНАЯ ЗАДАЧА ОТКЛОНЕНА ЛИДОМ\n\n"
            f"ЗАДАЧА: {task}\n\n"
            f"{lead_summary}\n\n"
            "Код не писался, ветка не тронута, review gate не запускался."
        )

    findings = [f"👷‍♂️ {lead_label} ({lead_model}):\n{lead_summary}"]

    if any(kw in lead_summary.lower() for kw in HELP_KEYWORDS) and pool:
        matched_names = [n for n in find_matching_specialists(lead_summary, max_specialists=2) if n in pool]
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

{lead_summary}

Полная исходная задача: {task}
Репозиторий: {repo_name}, ветка {branch_name} (уже текущая).

Ты привлечён именно потому, что часть оставшейся работы совпадает с
твоей специализацией. Определи свою часть и реализуй её через
write_file.
"""
            specialist_response = await specialist.run(specialist_prompt)
            findings.append(f"{label} ({model_name}):\n{specialist_response.text.strip()}")

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
        rework_response = await lead.run(rework_prompt)
        findings.append(f"🔄 {lead_label} (доработка по вето Review Gate):\n{rework_response.text.strip()}")
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
        + "\n\n⚠️ Изменения НЕ в main — открой ветку, проверь и смержи сам, "
        "с учётом вердикта ревью выше."
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
    send_telegram_report(report)

    await curate_knowledge("Инженерная задача", report)


if __name__ == "__main__":
    asyncio.run(main())
