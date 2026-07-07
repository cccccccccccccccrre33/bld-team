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


def _env(key: str, default: str) -> str:
    """Как os.getenv, но пустая строка тоже считается 'не задано'.

    GitHub Actions передаёт ${{ vars.X }} как ПУСТУЮ строку, если такой
    Variable не существует в репозитории — переменная окружения при
    этом всё равно СОЗДАЁТСЯ (просто пустой), поэтому _env(key,
    default) не срабатывает — он берёт default только когда переменной
    нет вообще, а не когда она пустая. Из-за этого дефолты в этом файле
    тихо перезаписывались пустыми строками везде, где в .yml есть
    vars.MODEL_XXX, а сама Variable не создана."""
    value = os.getenv(key, "")
    return value if value else default

# Azure AI Foundry endpoint и креды берутся из переменных окружения,
# см. .env.example. Используем DefaultAzureCredential под капотом
# (см. client_factory.py) — никаких ключей в коде.

MODEL_ASSIGNMENTS = {
    # Архитектура, риски, приоритеты, технический долг
    "cto": _env("MODEL_CTO", "gpt-5.5"),

    # Дотошный сильный синьор-бэкендер
    "backend_senior": _env("MODEL_BACKEND", "gpt-5.4"),

    # Продукт / фронт / UX — не нужна максимальная глубина
    "product_frontend": _env("MODEL_PRODUCT", "gpt-5.4-nano"),

    # QA / Security — параноик, ищет edge-cases
    "qa_security": _env("MODEL_QA", "gpt-5.4"),

    # Не участник дискуссии — "руки", читающие репозиторий.
    "code_scout": _env("MODEL_CODE_SCOUT", "gpt-5.2"),

    # Модератор GroupChat — чисто роутинг, дешёвая модель.
    "moderator": _env("MODEL_MODERATOR", "gpt-5.4-nano"),
}

# Эндпоинт Azure AI Foundry (project endpoint, не resource endpoint!)
FOUNDRY_PROJECT_ENDPOINT = _env("FOUNDRY_PROJECT_ENDPOINT", "")

# --- Офисные посиделки (agents/office_chat.py, workflows/office_chat.py) ---
# Неформальный чат — самая дешёвая ветка, тут не нужна глубина.
OFFICE_MODEL_ASSIGNMENTS = {
    "cto": _env("MODEL_OFFICE_CTO", "gpt-5.4-mini"),
    "backend_senior": _env("MODEL_OFFICE_BACKEND", "gpt-5.4-mini"),
    "product_frontend": _env("MODEL_OFFICE_PRODUCT", "gpt-5.4-mini"),
    "qa_security": _env("MODEL_OFFICE_QA", "gpt-5.4-mini"),
    "moderator": _env("MODEL_OFFICE_MODERATOR", "gpt-5.4-nano"),
    # "Искра" реально копается в коде через tools — нужна модель получше
    "spark": _env("MODEL_OFFICE_SPARK", "gpt-5.2"),
}

# --- Совет директоров (agents/board.py, workflows/board_meeting.py) ---
# Чисто техническая экспертиза по BLD System. Мехмат — самый строгий
# теоретик, ему топовая модель; остальным — по убыванию нагрузки.
BOARD_MODEL_ASSIGNMENTS = {
    "mekhmat": _env("MODEL_BOARD_MEKHMAT", "gpt-5.5"),
    "fiztech": _env("MODEL_BOARD_FIZTECH", "gpt-5.4"),
    "fizmat": _env("MODEL_BOARD_FIZMAT", "gpt-5.4"),
    "tehmat": _env("MODEL_BOARD_TEHMAT", "gpt-5.4-mini"),
    # Секретарь: ведёт заседание и сжимает итог в отчёт для Telegram.
    "secretary": _env("MODEL_BOARD_SECRETARY", "gpt-5.4-mini"),
    # Формулирует повестку — реально копается в коде через tools,
    # нужна модель, которая нормально работает с git_log/grep_repo.
    "agenda_setter": _env("MODEL_BOARD_AGENDA", "gpt-5.2"),

    # "Новый сотрудник" — берётся за конкретную задачу со "следующего
    # шага" заседания, реально копается в коде и пишет детальный отчёт.
    "worker": _env("MODEL_BOARD_WORKER", "gpt-5.4-mini"),

    # Инженерная команда (agents/engineering.py) — РЕАЛЬНО пишет и
    # коммитит код (в отдельную ветку). Лид — топовая модель, ему
    # доверена вся техническая глубина; привлечённые инженеры дешевле.
    "lead_engineer": _env("MODEL_BOARD_LEAD_ENGINEER", "gpt-5.5"),
    "junior_engineer": _env("MODEL_BOARD_JUNIOR_ENGINEER", "gpt-5.4-mini"),
}

# --- Правление (agents/executive_board.py, workflows/executive_meeting.py) ---
# Только COO и HR — остальные бизнес-роли убраны по фидбеку.
EXEC_MODEL_ASSIGNMENTS = {
    "coo": _env("MODEL_EXEC_COO", "gpt-5.4"),
    "hr": _env("MODEL_EXEC_HR", "gpt-5.4"),
    # ВАЖНО: используется как orchestrator_agent в GroupChatBuilder
    # (executive_meeting.py) — сторонние модели через Chat Completions
    # API падают с "Messages are required for chat completions" на
    # внутренней механике оркестрации GroupChat (Responses API у
    # gpt-моделей такое терпит молча, Chat Completions — нет). Поэтому
    # здесь ТОЛЬКО gpt-модель, независимо от остального тюнинга.
    "secretary": _env("MODEL_EXEC_SECRETARY", "gpt-5.4-mini"),
    "agenda_setter": _env("MODEL_EXEC_AGENDA", "DeepSeek-V4-Flash"),
    "worker": _env("MODEL_EXEC_WORKER", "gpt-5.4-mini"),
}

# --- Глобальные гении (agents/global_geniuses.py) ---
# Архетипы по мировым топ-вузам — используются И в общем ростере
# (Лаборатория, HR 1-на-1), И как пул специалистов, которых лид-инженер
# может "нанять" под конкретную задачу (agents/engineering.py).
# gpt-5.5 сознательно не раздаём сюда — он остаётся эксклюзивным для
# Мехмата (совет) и Лид-инженера, чтобы не взорвать косты.
GLOBAL_MODEL_ASSIGNMENTS = {
    "mit": _env("MODEL_GENIUS_MIT", "gpt-5.4"),          # быстрый прототип, широкий инженерный охват
    "caltech": _env("MODEL_GENIUS_CALTECH", "gpt-5.4"),  # предельная теоретическая строгость
    "stanford": _env("MODEL_GENIUS_STANFORD", "Llama-4-Maverick-17B-128E-Instruct-FP8"),  # прикладной AI/стата, продуктовое чутьё
    "cmu": _env("MODEL_GENIUS_CMU", "Kimi-K2.7-Code"),     # чистый CS, формальные методы, робастность — реально пишет код
    "tsinghua": _env("MODEL_GENIUS_TSINGHUA", "gpt-5.4-mini"),  # элитный CS, распределённые системы
    "pku": _env("MODEL_GENIUS_PKU", "gpt-5.4-mini"),     # чистая математика, криптография
    "ustc": _env("MODEL_GENIUS_USTC", "gpt-5.4-mini"),   # скорость, производительность, AI-вычисления
    "eth": _env("MODEL_GENIUS_ETH", "gpt-5.4-mini"),     # надёжность, формальная верификация
    "kaist": _env("MODEL_GENIUS_KAIST", "gpt-5.4-mini"), # HCI, AI-агенты, UX-мышление
}

# --- Лидерство (agents/leadership.py) ---
# Chief Scientist — 5-й член совета директоров ("ту ли задачу решаем").
# VP Engineering — 3-й член правления (приоритизация инженерных задач).
CHIEF_SCIENTIST_MODEL = _env("MODEL_CHIEF_SCIENTIST", "gpt-5.5")
VP_ENGINEERING_MODEL = _env("MODEL_VP_ENGINEERING", "gpt-5.4")

# --- Review Gate (agents/review_gate.py) ---
# Проверяют результат инженерной задачи ПЕРЕД тем как отчёт уйдёт
# Валику — архитектурное вето, качество кода, попытка сломать решение.
REVIEW_GATE_MODEL_ASSIGNMENTS = {
    "chief_architect": _env("MODEL_CHIEF_ARCHITECT", "gpt-5.5"),
    "reviewer": _env("MODEL_REVIEWER", "DeepSeek-V4-Pro"),  # силён в логике/сложности — Big O
    "failure_engineer": _env("MODEL_FAILURE_ENGINEER", "grok-4.3"),  # дерзкий стиль — специально всё ломает
}

# --- Инженерный спецназ (agents/specialists.py) ---
# Дополняют пул глобальных гениев в инженерной команде — узкие,
# практические специализации, которых не было.
SPECIALIST_MODEL_ASSIGNMENTS = {
    "database_engineer": _env("MODEL_DATABASE_ENGINEER", "gpt-5.4"),
    "performance_engineer": _env("MODEL_PERFORMANCE_ENGINEER", "gpt-5.4"),
    "security_engineer": _env("MODEL_SECURITY_ENGINEER", "gpt-5.4"),
    "reliability_engineer": _env("MODEL_RELIABILITY_ENGINEER", "gpt-5.4"),
}

# --- Knowledge Curator (agents/knowledge_curator.py) ---
# Ведёт постоянную "вики компании" — дешёвая модель, чисто суммаризация.
KNOWLEDGE_CURATOR_MODEL = _env("MODEL_KNOWLEDGE_CURATOR", "gpt-5.4-nano")

# --- Инженерные отряды (agents/squads.py, workflows/squad_task.py) ---
# Постоянные команды (не ad-hoc подбор) — работают параллельно над
# РАЗНЫМИ задачами. Лиды на проверенных gpt-моделях (эти роли реально
# пишут код через write_file — надёжность tool-calling тут важнее
# экспериментов с новыми провайдерами).
SQUAD_LEAD_ALPHA_MODEL = _env("MODEL_SQUAD_LEAD_ALPHA", "gpt-5.5")
SQUAD_LEAD_BRAVO_MODEL = _env("MODEL_SQUAD_LEAD_BRAVO", "gpt-5.5")

# --- Рост команды (agents/growth_team.py) ---
# 4 новые роли под конкретные пробелы: эксплуатация AI-пайплайна,
# инфраструктура/деплой, дизайн интерфейсов, и менторство молодых
# гениев (развитие людей — то, чего не хватало как процесса).
GROWTH_MODEL_ASSIGNMENTS = {
    "mlops_engineer": _env("MODEL_MLOPS_ENGINEER", "gpt-5.4"),
    "devops_engineer": _env("MODEL_DEVOPS_ENGINEER", "gpt-5.4"),
    "product_designer": _env("MODEL_PRODUCT_DESIGNER", "gpt-5.4-mini"),
    "engineering_mentor": _env("MODEL_ENGINEERING_MENTOR", "gpt-5.4-mini"),
}
