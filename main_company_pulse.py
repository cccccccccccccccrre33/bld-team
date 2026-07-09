"""
Точка входа для Company Pulse — непрерывный тред-чат компании,
1-3 человека говорят каждый час, разговор живёт между запусками.

Запуск:
    python main_company_pulse.py
"""

from dotenv import load_dotenv

load_dotenv()

from workflows.company_pulse import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
