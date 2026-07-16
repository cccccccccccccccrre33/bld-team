"""
Точка входа для инициативы отрядов — независимый от совета директоров
цикл: отряд сам находит задачу, проходит approval CTO (или берёт
мелкую сам), выполняет.

Запуск всех отрядов (alpha, bravo, platform, product):
    python main_squad_initiative.py

Запуск одного отряда:
    python main_squad_initiative.py alpha
    python main_squad_initiative.py bravo
    python main_squad_initiative.py platform
    python main_squad_initiative.py product
"""

from dotenv import load_dotenv

load_dotenv()

from workflows.squad_initiative import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
