"""
Точка входа для Domain Scan — один шард полного ежедневного прохода по
всей компании (см. workflows/domain_scan.py).

Запуск конкретного шарда (0-индексация):
    python main_domain_scan.py 0 6      # шард 0 из 6
    python main_domain_scan.py 1 6      # шард 1 из 6
    ...

Или через переменные окружения SHARD_INDEX/SHARD_COUNT (так вызывает
.github/workflows/domain_scan.yml через matrix strategy).

Без аргументов — весь ростер одним шардом (SHARD_COUNT=1), удобно для
локального теста на пару человек через explicit shard, но НЕ для
прода — прод всегда идёт через матрицу в yml.
"""

from dotenv import load_dotenv

load_dotenv()

from workflows.domain_scan import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
