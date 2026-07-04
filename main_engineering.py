"""
Точка входа для инженерной задачи — реально пишет и коммитит код
в отдельную ветку bld-system/bld-panel.

Запуск:
    python main_engineering.py "Исправить логику Z-score в L4"
"""

from dotenv import load_dotenv

load_dotenv()

from workflows.engineering_task import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
