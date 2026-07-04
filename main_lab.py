"""
Точка входа для Лаборатории — 2-3 случайных человека из всей компании
сами берутся за проблему (реальную из кода или абстрактную) и решают
её вслух.

Запуск:
    python main_lab.py
"""

from dotenv import load_dotenv

load_dotenv()

from workflows.lab_session import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
