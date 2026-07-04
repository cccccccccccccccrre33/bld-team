"""
Точка входа для офисных посиделок — неформальный чат команды о проекте.

Запуск со случайным репозиторием и случайным зачинщиком:
    python main_office_chat.py

Запуск с конкретным репозиторием (bld-system или bld-panel):
    python main_office_chat.py bld-system
"""

from dotenv import load_dotenv

load_dotenv()

from workflows.office_chat import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
