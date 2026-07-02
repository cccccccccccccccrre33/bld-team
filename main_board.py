"""
Точка входа для заседания совета директоров.

Запуск без темы (совет сам предложит вопрос):
    python main_board.py

Запуск с конкретной темой:
    python main_board.py "Стоит ли сейчас искать первого сотрудника?"
"""

from dotenv import load_dotenv

load_dotenv()

from workflows.board_meeting import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
