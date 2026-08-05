"""
Точка входа для статуса целей, заведённых через /goal.

Обзор всех незавершённых целей сразу:
    python main_goal_status.py

Конкретная цель:
    python main_goal_status.py goal-hochu-eksport-v-excel-a1b2c3
"""

from dotenv import load_dotenv

load_dotenv()

from workflows.goal_status import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
