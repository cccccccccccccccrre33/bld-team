"""
Назначение моделей по ролям.

ВАЖНО: значения ниже — это deployment names, которые ДОЛЖНЫ существовать
в твоём Azure AI Foundry проекте (как ты их назвал при деплое модели).

История: изначально тут были смешаны сторонние модели (grok-4.3,
DeepSeek-V4-Pro) с настоящими Azure OpenAI (gpt-5.4, gpt-5.5). На
практике сторонние модели через маркетплейс Foundry падают с 500-й
ошибкой — библиотека agent-framework обращается к ним через т.н.
Responses API, который сторонние модели (не-OpenAI) в большинстве
случаев не поддерживают, только настоящие Azure OpenAI deployment'ы.
Поэтому теперь везде используются ТОЛЬКО модели линейки gpt-5.x —
разного веса, чтобы держать баланс между качеством и стоимостью.

Уровни нагрузки (от дорогого к дешёвому):
- gpt-5.5       — самый дорогой и сильный. Только для ролей, где
                  реально нужна максимальная глубина рассуждений.
- gpt-5.4       — сильная модель, дешевле 5.5. Для ролей с серьёзной
                  содержательной нагрузкой, но не топовых.
- gpt-5.4-mini  — средний уровень. Для ролей, где нужна вменяемость,
                  но не крайняя строгость.
- gpt-5.4-nano  — самый дешёвый. Для чисто роутинговых/технических
                  ролей (модератор, секретарь, лёгкий чат).
- gpt-5.2  — отдельно для ролей, которым нужно РЕАЛЬНО читать код
                  через tools (git_log, grep_repo) — работает с этим
                  надёжно и дешевле топовых моделей.

Если задеплоишь другие названия — задай через переменные окружения
(см. .env.example), дефолты ниже менять не обязательно.
"""

import os

# Azure AI Foundry endpoint и креды берутся из переменных окружения,
# см. .env.example. Используем DefaultAzureCredential под капотом
# (см. client_factory.py) — никаких ключей в коде.

MODEL_ASSIGNMENTS = {
    # Архитектура, риски, приоритеты, технический долг
    "cto": os.getenv("MODEL_CTO", "gpt-5.4"),

    # Дотошный сильный синьор-бэкендер
    "backend_senior": os.getenv("MODEL_BACKEND", "gpt-5.4-mini"),

    # Продукт / фронт / UX — не нужна максимальная глубина
    "product_frontend": os.getenv("MODEL_PRODUCT", "gpt-5.4-nano"),

    # QA / Security — параноик, ищет edge-cases
    "qa_security": os.getenv("MODEL_QA", "gpt-5.4-mini"),

    # Не участник дискуссии — "руки", читающие репозиторий.
    "code_scout": os.getenv("MODEL_CODE_SCOUT", "gpt-5.2"),

    # Модератор GroupChat — чисто роутинг, дешёвая модель.
    "moderator": os.getenv("MODEL_MODERATOR", "gpt-5.4-nano"),
}

# Эндпоинт Azure AI Foundry (project endpoint, не resource endpoint!)
FOUNDRY_PROJECT_ENDPOINT = os.getenv("FOUNDRY_PROJECT_ENDPOINT", "")

# --- Офисные посиделки (agents/office_chat.py, workflows/office_chat.py) ---
# Неформальный чат — самая дешёвая ветка, тут не нужна глубина.
OFFICE_MODEL_ASSIGNMENTS = {
    "cto": os.getenv("MODEL_OFFICE_CTO", "gpt-5.4-nano"),
    "backend_senior": os.getenv("MODEL_OFFICE_BACKEND", "gpt-5.4-nano"),
    "product_frontend": os.getenv("MODEL_OFFICE_PRODUCT", "gpt-5.4-nano"),
    "qa_security": os.getenv("MODEL_OFFICE_QA", "gpt-5.4-nano"),
    "moderator": os.getenv("MODEL_OFFICE_MODERATOR", "gpt-5.4-nano"),
    # "Искра" реально копается в коде через tools — нужна модель получше
    "spark": os.getenv("MODEL_OFFICE_SPARK", "gpt-5.2"),
}

# --- Совет директоров (agents/board.py, workflows/board_meeting.py) ---
# Чисто техническая экспертиза по BLD System. Мехмат — самый строгий
# теоретик, ему топовая модель; остальным — по убыванию нагрузки.
BOARD_MODEL_ASSIGNMENTS = {
    "mekhmat": os.getenv("MODEL_BOARD_MEKHMAT", "gpt-5.5"),
    "fiztech": os.getenv("MODEL_BOARD_FIZTECH", "gpt-5.4"),
    "fizmat": os.getenv("MODEL_BOARD_FIZMAT", "gpt-5.4"),
    "tehmat": os.getenv("MODEL_BOARD_TEHMAT", "gpt-5.4-mini"),
    # Секретарь: ведёт заседание и сжимает итог в отчёт для Telegram.
    "secretary": os.getenv("MODEL_BOARD_SECRETARY", "gpt-5.4-mini"),
    # Формулирует повестку — реально копается в коде через tools,
    # нужна модель, которая нормально работает с git_log/grep_repo.
    "agenda_setter": os.getenv("MODEL_BOARD_AGENDA", "gpt-5.2"),

    # "Новый сотрудник" — берётся за конкретную задачу со "следующего
    # шага" заседания, реально копается в коде и пишет детальный отчёт.
    "worker": os.getenv("MODEL_BOARD_WORKER", "gpt-5.4-mini"),

    # Инженерная команда (agents/engineering.py) — РЕАЛЬНО пишет и
    # коммитит код (в отдельную ветку). Лид — топовая модель, ему
    # доверена вся техническая глубина; привлечённые инженеры дешевле.
    "lead_engineer": os.getenv("MODEL_BOARD_LEAD_ENGINEER", "gpt-5.5"),
    "junior_engineer": os.getenv("MODEL_BOARD_JUNIOR_ENGINEER", "gpt-5.4-mini"),
}

# --- Правление (agents/executive_board.py, workflows/executive_meeting.py) ---
# Только COO и HR — остальные бизнес-роли убраны по фидбеку.
EXEC_MODEL_ASSIGNMENTS = {
    "coo": os.getenv("MODEL_EXEC_COO", "gpt-5.4-mini"),
    "hr": os.getenv("MODEL_EXEC_HR", "gpt-5.4-mini"),
    "secretary": os.getenv("MODEL_EXEC_SECRETARY", "gpt-5.4-nano"),
    "agenda_setter": os.getenv("MODEL_EXEC_AGENDA", "gpt-5.4-nano"),
    "worker": os.getenv("MODEL_EXEC_WORKER", "gpt-5.4-mini"),
}

# --- Глобальные гении (agents/global_geniuses.py) ---
# Архетипы по мировым топ-вузам — используются И в общем ростере
# (Лаборатория, HR 1-на-1), И как пул специалистов, которых лид-инженер
# может "нанять" под конкретную задачу (agents/engineering.py).
# gpt-5.5 сознательно не раздаём сюда — он остаётся эксклюзивным для
# Мехмата (совет) и Лид-инженера, чтобы не взорвать косты.
GLOBAL_MODEL_ASSIGNMENTS = {
    "mit": os.getenv("MODEL_GENIUS_MIT", "gpt-5.4"),          # быстрый прототип, широкий инженерный охват
    "caltech": os.getenv("MODEL_GENIUS_CALTECH", "gpt-5.4"),  # предельная теоретическая строгость
    "stanford": os.getenv("MODEL_GENIUS_STANFORD", "gpt-5.4-mini"),  # прикладной AI/стата, продуктовое чутьё
    "cmu": os.getenv("MODEL_GENIUS_CMU", "gpt-5.4-mini"),     # чистый CS, формальные методы, робастность
    "tsinghua": os.getenv("MODEL_GENIUS_TSINGHUA", "gpt-5.4-mini"),  # элитный CS, распределённые системы
    "pku": os.getenv("MODEL_GENIUS_PKU", "gpt-5.4-nano"),     # чистая математика, криптография
    "ustc": os.getenv("MODEL_GENIUS_USTC", "gpt-5.4-nano"),   # скорость, производительность, AI-вычисления
    "eth": os.getenv("MODEL_GENIUS_ETH", "gpt-5.4-mini"),     # надёжность, формальная верификация
}
