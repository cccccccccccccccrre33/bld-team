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

from agents.engineering import build_junior_engineer, build_lead_engineer
from config.models import BOARD_MODEL_ASSIGNMENTS
from tools.repo_tools import commit_and_push, create_branch
from tools.telegram_report import send_telegram_report
from workflows._common import sync_repos_or_alert

# Ключевые слова, по которым понимаем, что лид явно попросил помощи —
# простая эвристика, не идеальная, но рабочая без сложного парсинга
# структурированного вывода.
HELP_KEYWORDS = [
    "привлек", "привлёк", "нужна помощь", "разбил", "разбить",
    "второй инженер", "инженер 2", "junior", "ещё одного инженера",
    "потребуется ещё", "не справлюсь один",
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

    findings = [f"👷‍♂️ Ведущий инженер ({lead_model}):\n{lead_summary}"]

    if any(kw in lead_summary.lower() for kw in HELP_KEYWORDS):
        print("Ведущий инженер запросил помощь — привлекаем ещё инженера...")
        junior_model = BOARD_MODEL_ASSIGNMENTS.get("junior_engineer", "gpt-5.4-mini")
        junior = build_junior_engineer(junior_model, 2)
        junior_prompt = f"""
Ведущий инженер оставил такое описание задачи и своей части работы:

{lead_summary}

Полная исходная задача: {task}
Репозиторий: {repo_name}, ветка {branch_name} (уже текущая).

Определи, какая часть работы описана как оставшаяся, и реализуй её
через write_file.
"""
        junior_response = await junior.run(junior_prompt)
        findings.append(f"👷 Инженер #2 ({junior_model}):\n{junior_response.text.strip()}")

    print("Коммитим и пушим изменения...")
    push_result = commit_and_push(repo_name, branch_name, f"AI engineering: {task[:60]}")
    print(push_result)

    report = (
        f"👷‍♂️ ИНЖЕНЕРНАЯ ЗАДАЧА ВЫПОЛНЕНА\n\n"
        f"ЗАДАЧА:\n{task}\n\n"
        f"РЕПОЗИТОРИЙ: {repo_name}\n"
        f"ВЕТКА: {branch_name}\n\n"
        + "\n\n".join(findings)
        + f"\n\n{push_result}\n\n"
        "⚠️ Изменения НЕ в main — открой ветку, проверь и смержи сам, "
        "если всё устраивает."
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


if __name__ == "__main__":
    asyncio.run(main())
