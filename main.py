"""
Точка входа. Запуск: python main.py
"""

from dotenv import load_dotenv

load_dotenv()

from workflows.discussion import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
