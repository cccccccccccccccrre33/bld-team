"""
Точка входа для HR 1-на-1 — HR вызывает случайного человека из всей
компании на личный разговор, слушает, делится коротким выводом.

Запуск:
    python main_hr_checkin.py
"""

from dotenv import load_dotenv

load_dotenv()

from workflows.hr_checkin import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
