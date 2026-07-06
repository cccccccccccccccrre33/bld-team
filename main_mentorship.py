"""
Точка входа для менторства — Engineering Mentor даёт персональную
обратную связь одному случайному молодому специалисту.

Запуск:
    python main_mentorship.py
"""

from dotenv import load_dotenv

load_dotenv()

from workflows.mentorship import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
