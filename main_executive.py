"""
Точка входа для заседания правления (бизнес-сторона компании).

Запуск без темы (правление само предложит вопрос):
    python main_executive.py

Запуск с конкретной темой:
    python main_executive.py "Нужен ли сейчас первый наём?"
"""

from dotenv import load_dotenv

load_dotenv()

from workflows.executive_meeting import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
