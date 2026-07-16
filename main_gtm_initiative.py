"""
Точка входа для GTM-инициативы — департамент готовит черновики
документов (сегментация рынка, sales-скрипт, outreach-материалы) в
gtm-materials/, никогда не пишет код и явно помечает всё, что требует
реального действия Валика лично (см. agents/gtm.py).

Запуск:
    python main_gtm_initiative.py
"""

from dotenv import load_dotenv

load_dotenv()

from workflows.gtm_initiative import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
