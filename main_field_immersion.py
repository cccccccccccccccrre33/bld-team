"""
Точка входа для Полевой практики (см. workflows/field_immersion.py).

Запуск:
    python main_field_immersion.py        # 3 человека за сессию (по умолчанию)
    python main_field_immersion.py 5      # 5 человек за сессию

Если context/construction_domain.md ещё пуст (нет ни одного реального
раздела) — ничего не выдумывает, вместо этого шлёт в Telegram конкретный
запрос Валику, какие данные нужны. Это ожидаемое, не аварийное
поведение — см. докстринг workflows/field_immersion.py.
"""

from dotenv import load_dotenv

load_dotenv()

from workflows.field_immersion import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
