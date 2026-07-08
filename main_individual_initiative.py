"""
Точка входа для индивидуальной инициативы — любой человек компании
(не только 2 отряда) сам находит проблему в своей специализации.

Запуск случайного человека:
    python main_individual_initiative.py

Запуск конкретного человека:
    python main_individual_initiative.py mit
"""

from dotenv import load_dotenv

load_dotenv()

from workflows.individual_initiative import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
