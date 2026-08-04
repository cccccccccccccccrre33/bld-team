"""
Точка входа для инициативы отрядов — независимый от совета директоров
цикл: отряд сам находит задачу, проходит approval CTO (или берёт
мелкую сам), выполняет.

Запуск всех департаментов (alpha, bravo, platform, product, anomaly,
nlu, qra — полный список всегда см. agents/squads.py::SQUADS):
    python main_squad_initiative.py

Запуск одного департамента (пример; ключ должен быть в SQUADS):
    python main_squad_initiative.py alpha
    python main_squad_initiative.py anomaly
    python main_squad_initiative.py nlu
    python main_squad_initiative.py qra
"""

from dotenv import load_dotenv

load_dotenv()

from workflows.squad_initiative import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
