"""
Точка входа для рабочего дня "20% времени" — компания посвящает весь
день одному крупному проекту (реестр в workflows/big_projects.py).

Запуск для конкретного проекта (по умолчанию — сезонный режим):
    python main_big_project_day.py
    python main_big_project_day.py seasonal_mode
"""

from dotenv import load_dotenv

load_dotenv()

from workflows.big_projects import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
