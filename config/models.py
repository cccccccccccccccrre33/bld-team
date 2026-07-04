"""
Назначение моделей по ролям.

ВАЖНО: значения ниже — это deployment names, которые ДОЛЖНЫ существовать
в твоём Azure AI Foundry проекте (как ты их назвал при деплое модели).
Если у тебя deployment называется иначе (например "gpt-51-prod" вместо
"gpt-5.1") — поправь строки ниже, а не код агентов.

Логика распределения:
- CTO / Backend / QA — нужна максимальная глубина рассуждений, споры идут
  на уровне архитектурных решений и рисков => топовые reasoning-модели.
- Frontend/Product — нужна скорость и "человеческий" продуктовый голос,
  не обязательна максимальная глубина => быстрая, но грамотная модель.
- Code Scout — не участвует в споре, его работа — копаться в репо
  (читать файлы, диффы, грепать) => модель, заточенная под код,
  а не под "красивые" рассуждения.
- Moderator (manager в GroupChat) — не имеет своего мнения о проекте,
  просто решает кто говорит следующим => дешёвая/быстрая модель достаточно.
"""

import os

# Azure AI Foundry endpoint и креды берутся из переменных окружения,
# см. .env.example. Используем DefaultAzureCredential под капотом
# (см. client_factory.py) — никаких ключей в коде.

MODEL_ASSIGNMENTS = {
    # Архитектура, риски, приоритеты, технический долг
    "cto": os.getenv("MODEL_CTO", "grok-4.3"),

    # Дотошный сильный синьор-бэкендер — ищет логические дыры,
    # любит математически обосновывать возражения
    "backend_senior": os.getenv("MODEL_BACKEND", "gpt-5.5"),

    # Продукт / фронт / UX — топит за пользователя и скорость выхода
    "product_frontend": os.getenv("MODEL_PRODUCT", "gpt-5.4"),

    # QA / Security — параноик, ищет edge-cases и дыры в безопасности
    "qa_security": os.getenv("MODEL_QA", "DeepSeek-V4-Pro"),

    # Не участник дискуссии — "руки", читающие репозиторий по запросу
    # любого агента. Заточен под код, не под рассуждения.
    "code_scout": os.getenv("MODEL_CODE_SCOUT", "DeepSeek-V4-Pro"),

    # Модератор GroupChat — выбирает кто говорит следующим.
    # Не должен быть дорогой моделью, это чисто роутинг.
    "moderator": os.getenv("MODEL_MODERATOR", "gpt-5.4"),
}

# Эндпоинт Azure AI Foundry (project endpoint, не resource endpoint!)
FOUNDRY_PROJECT_ENDPOINT = os.getenv("FOUNDRY_PROJECT_ENDPOINT", "")

# --- Офисные посиделки (agents/office_chat.py, workflows/office_chat.py) ---
# Неформальный чат с РЕАЛЬНЫМ доступом к коду (те же tools что у team.py),
# но без структуры формального код-ревью — просто "коллеги обсуждают
# что-то интересное в проекте". По умолчанию использует модели, которые
# уже задеплоены (grok-4.3, DeepSeek-V4-Pro, gpt-5.5, gpt-5.4) — чтобы
# работало сразу без дополнительных деплоев в Foundry.
OFFICE_MODEL_ASSIGNMENTS = {
    "cto": os.getenv("MODEL_OFFICE_CTO", "grok-4.3"),
    "backend_senior": os.getenv("MODEL_OFFICE_BACKEND", "gpt-5.5"),
    "product_frontend": os.getenv("MODEL_OFFICE_PRODUCT", "gpt-5.4"),
    "qa_security": os.getenv("MODEL_OFFICE_QA", "DeepSeek-V4-Pro"),
    # Ведёт очередность реплик в чате — дешёвая роутинг-роль
    "moderator": os.getenv("MODEL_OFFICE_MODERATOR", "gpt-5.4"),
    # "Искра" — тот, кто первым копается в репо и находит повод для разговора
    "spark": os.getenv("MODEL_OFFICE_SPARK", "DeepSeek-V4-Pro"),
}

# --- Совет директоров (agents/board.py, workflows/board_meeting.py) ---
# Отдельная команда, не трогает код — только стратегическое обсуждение.
# Всем ролям тут не нужна codex-модель (нет grep/diff), но нужна
# сильная рассуждающая модель — споры содержательные, не косметические.
BOARD_MODEL_ASSIGNMENTS = {
    "mekhmat": os.getenv("MODEL_BOARD_MEKHMAT", "grok-4.3"),
    "fiztech": os.getenv("MODEL_BOARD_FIZTECH", "gpt-5.5"),
    "fizmat": os.getenv("MODEL_BOARD_FIZMAT", "DeepSeek-V4-Pro"),
    "tehmat": os.getenv("MODEL_BOARD_TEHMAT", "gpt-5.4"),
    # Секретарь: ведёт заседание (кто говорит следующим) и в конце сam
    # сжимает итог в отчёт для Telegram — не должен быть дорогой моделью.
    "secretary": os.getenv("MODEL_BOARD_SECRETARY", "gpt-5.4"),
    # Формулирует повестку дня (тему заседания), если не задана вручную.
    "agenda_setter": os.getenv("MODEL_BOARD_AGENDA", "DeepSeek-V4-Pro"),
}

# --- Правление (agents/executive_board.py, workflows/executive_meeting.py) ---
# Только COO и HR — остальные бизнес-роли (Sales/Marketing/CFO/Legal)
# оказались избыточны на практике, убраны по фидбеку.
EXEC_MODEL_ASSIGNMENTS = {
    "coo": os.getenv("MODEL_EXEC_COO", "gpt-5.4"),
    "hr": os.getenv("MODEL_EXEC_HR", "gpt-5.5"),
    "secretary": os.getenv("MODEL_EXEC_SECRETARY", "gpt-5.4"),
    "agenda_setter": os.getenv("MODEL_EXEC_AGENDA", "DeepSeek-V4-Pro"),
}
