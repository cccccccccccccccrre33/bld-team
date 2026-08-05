"""
Точка входа для HR Rotation Review — периодический пересмотр
распределения специалистов по департаментам на основе факта задач
(НЕ путать с main_hr_checkin.py — это тёплый 1-на-1 про самочувствие,
не про штат).

Обзор кандидатов (ничего не меняет, только отчёт в Telegram):
    python main_hr_rotation_review.py

Применить конкретное решение (после того как Валик увидел отчёт и
согласился с конкретным переносом):
    python main_hr_rotation_review.py --apply "database_engineer" "qra"
"""

from dotenv import load_dotenv

load_dotenv()

from workflows.hr_rotation_review import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
