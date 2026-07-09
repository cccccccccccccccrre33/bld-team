"""
Точка входа для Хевруты — свободное совместное изучение идей 2-4
человеками, не обязательно привязанное к текущему коду.

Запуск:
    python main_chevruta.py
"""

from dotenv import load_dotenv

load_dotenv()

from workflows.chevruta import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
