"""
Точка входа для Breakthrough Proposal — Engineering Fellow предлагает
крупный архитектурный прорыв, фильтруется Chief Scientist + Chief
Architect + CEO, при одобрении собирает команду и реализует.

Запуск случайного Fellow:
    python main_breakthrough_proposal.py

Запуск конкретного:
    python main_breakthrough_proposal.py physics_informed_ml_engineer
"""

from dotenv import load_dotenv

load_dotenv()

import asyncio
import sys

from workflows.breakthrough_proposal import run_breakthrough_cycle
from agents.engineering_fellows import FELLOW_BUILDERS


async def main():
    key = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in FELLOW_BUILDERS else None
    await run_breakthrough_cycle(key)


if __name__ == "__main__":
    asyncio.run(main())
