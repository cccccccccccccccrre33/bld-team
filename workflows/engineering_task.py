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
from agents.review_gate import run_review_gate
from agents.specialists import SPECIALIST_LABELS
from agents.specialists import SPECIALTY_KEYWORDS as SPECIALIST_KEYWORDS
from config.models import BOARD_MODEL_ASSIGNMENTS, GLOBAL_MODEL_ASSIGNMENTS, SPECIALIST_MODEL_ASSIGNMENTS
from tools.repo_tools import commit_and_push, create_branch
from tools.telegram_report import send_telegram_report
from workflows._common import curate_knowledge, sync_repos_or_alert

ALL_SPECIALTY_KEYWORDS = {**GENIUS_KEYWORDS, **SPECIALIST_KEYWORDS}
ALL_SPECIALIST_LABELS = {**GLOBAL_LABELS, **SPECIALIST_LABELS}
ALL_SPECIALIST_MODELS = {**GLOBAL_MODEL_ASSIGNMENTS, **SPECIALIST_MODEL_ASSIGNMENTS}

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


async def run_engineering_task(task: str, repo_name: str | None = None) -> str:
    repo_name = repo_name or guess_repo(task)
    branch_name = f"ai-eng/{slugify(task)}-{datetime.now().strftime('%Y%m%d-%H%M')}"

    print(f"Создаём ветку {branch_name} в {repo_name}...")
    print(create_branch(repo_name, branch_name))

    lead_model = BOARD_MODEL_ASSIGNMENTS.get("lead_engineer", "gpt-5.5")
    lead = build_lead_engineer(lead_model)

    prompt = f"""
Задача: {task}

Репозиторий для работы: {repo_name}. Ветка {branch_name} уже создана
и является текущей — просто пиши файлы через write_file, изменения
автоматически попадут в неё.
"""
    print("Ведущий инженер разбирается с задачей и пишет код...")
    lead_response = await lead.run(prompt)
    lead_summary = lead_response.text.strip()

    if "ЗАДАЧА НЕ ОСМЫСЛЕН" in lead_summary.upper():
        return (
            f"⚠️ ИНЖЕНЕРНАЯ ЗАДАЧА ОТКЛОНЕНА ЛИДОМ\n\n"
            f"ЗАДАЧА: {task}\n\n"
            f"{lead_summary}\n\n"
            "Код не писался, ветка не тронута, review gate не запускался."
        )

    findings = [f"👷‍♂️ Ведущий инженер ({lead_model}):\n{lead_summary}"]

    if any(kw in lead_summary.lower() for kw in HELP_KEYWORDS):
        matched_names = find_matching_specialists(lead_summary, max_specialists=2)
        if not matched_names:
            import random
            matched_names = [random.choice(list(ALL_SPECIALTY_KEYWORDS.keys()))]

        print(f"Ведущий инженер запросил помощь — нанимаем: {', '.join(matched_names)}...")
        pool = build_specialist_pool()

        for name in matched_names:
            specialist = pool[name]
            label = ALL_SPECIALIST_LABELS.get(name, name)
            model_name = ALL_SPECIALIST_MODELS.get(name, "?")
            specialist_prompt = f"""
Ведущий инженер оставил такое описание задачи и своей части работы:

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
