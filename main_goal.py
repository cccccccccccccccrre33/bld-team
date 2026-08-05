"""
Точка входа для /goal — единая точка входа, вместо того чтобы каждый
раз вручную писать промпт и запускать нужный воркфлоу самому.

Запуск:
    python main_goal.py "текст цели свободной формой"

Пример:
    python main_goal.py "клиенты жалуются, что бот теряется, если фото отчёта отправлено без подписи"
    python main_goal.py "хочу автоматический экспорт отчётов в Excel для менеджеров"

Реалистичный канал ввода — GitHub Actions workflow_dispatch с текстовым
полем (.github/workflows/goal.yml) или прямой запуск отсюда; см.
workflows/goal_intake.py про то, почему это не буквальная Telegram-
команда /goal (у bld-team нет живого сервера-приёмника вебхуков).

Статус цели после запуска — main_goal_status.py <goal_id> (goal_id
печатается в конце этого скрипта).
"""

from dotenv import load_dotenv

load_dotenv()

from workflows.goal_intake import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
